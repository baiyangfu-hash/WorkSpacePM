"""Work Registry transaction, authorization, and state-machine tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from auto_pm.core.work_registry_service import WorkRegistryError, WorkRegistryService

from auto_pm.contracts.continuity import WorkKind, WorkState


def _service(root: Path) -> WorkRegistryService:
    service = WorkRegistryService(root, now=lambda: "2026-09-09T12:00:00+00:00")
    service.initialize("test")
    return service


def _decision(root: Path, decision_id: str, project_id: str, files: list[str]) -> None:
    path = root / ".auto-pm" / "decisions" / f"{decision_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "decision_package.v1",
                "decision_id": decision_id,
                "project_id": project_id,
                "change_id": "CHG-SCPT-TEST",
                "approved_scope": "MODULE",
                "approved_files": files,
                "approver": "architect",
                "approved_at": "2026-09-09T11:00:00+00:00",
                "decision_conclusion": "approved",
            }
        ),
        encoding="utf-8",
    )


def _planned(service: WorkRegistryService, work_id: str = "WORK-001"):
    return service.create_work(
        work_id=work_id,
        subject_project_id="SW-2026-008",
        kind=WorkKind.WBS,
        title="Context follow-up",
        owner="agent-a",
        scope_paths=["auto_pm/core/example.py"],
        source_fingerprint="sha256:abc",
        idempotency_key=f"create-{work_id}",
    )


def test_initializes_separate_wal_database(tmp_path: Path) -> None:
    _service(tmp_path)

    db = tmp_path / ".auto-pm" / "continuity.db"
    assert db.is_file()
    assert not (tmp_path / ".auto-pm" / "index.db").exists()
    with sqlite3.connect(db) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert {"schema_meta", "work_items", "work_relations", "events"} <= tables
    assert mode == "wal"


def test_write_work_starts_planned_until_decision_is_verified(tmp_path: Path) -> None:
    service = _service(tmp_path)
    work = _planned(service)

    assert work.state == WorkState.PLANNED
    assert work.authorization_ref == ""
    assert work.version == 1


def test_read_only_work_is_ready_without_decision(tmp_path: Path) -> None:
    service = _service(tmp_path)
    work = service.create_work(
        work_id="WORK-READ",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Read-only audit",
        owner="agent-a",
        scope_paths=["README.md"],
        source_fingerprint="sha256:def",
        idempotency_key="create-read",
        read_only=True,
    )

    assert work.state == WorkState.READY
    assert work.authorization_ref == "READ_ONLY"


def test_authorize_requires_matching_project_and_scope(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _planned(service)
    _decision(tmp_path, "DEC-GOOD", "SW-2026-008", ["auto_pm/core/example.py"])

    work = service.authorize("WORK-001", "DEC-GOOD", "authorize-good")

    assert work.state == WorkState.READY
    assert work.authorization_ref == "DEC-GOOD"
    assert work.version == 2


@pytest.mark.parametrize(
    ("project_id", "files", "message"),
    [
        ("SYS-2026-001", ["auto_pm/core/example.py"], "项目"),
        ("SW-2026-008", ["other.py"], "scope"),
    ],
)
def test_authorize_rejects_mismatched_decision(
    tmp_path: Path,
    project_id: str,
    files: list[str],
    message: str,
) -> None:
    service = _service(tmp_path)
    _planned(service)
    _decision(tmp_path, "DEC-BAD", project_id, files)

    with pytest.raises(WorkRegistryError, match=message):
        service.authorize("WORK-001", "DEC-BAD", "authorize-bad")


def test_state_machine_rejects_skipping_verification(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _planned(service)
    _decision(tmp_path, "DEC-GOOD", "SW-2026-008", ["auto_pm/core/example.py"])
    service.authorize("WORK-001", "DEC-GOOD", "authorize")

    with pytest.raises(WorkRegistryError, match="非法"):
        service.transition("WORK-001", WorkState.ACCEPTED, "skip")


def test_idempotent_create_does_not_duplicate_event(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = _planned(service)
    second = _planned(service)

    assert first == second
    with sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db") as conn:
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert count == 1


def test_idempotency_key_cannot_be_reused_for_another_work(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _planned(service)

    with pytest.raises(WorkRegistryError, match="其他 Work"):
        service.create_work(
            work_id="WORK-002",
            subject_project_id="SW-2026-008",
            kind=WorkKind.BUG,
            title="Other",
            owner="agent-b",
            scope_paths=["other.py"],
            source_fingerprint="sha256:xyz",
            idempotency_key="create-WORK-001",
        )


def test_relation_is_typed_and_idempotent(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _planned(service, "WORK-001")
    _planned(service, "WORK-002")

    service.add_relation("WORK-001", "WORK-002", "blocks", "rel-1")
    service.add_relation("WORK-001", "WORK-002", "blocks", "rel-1")

    with sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM work_relations").fetchone()[0] == 1


def test_relation_idempotency_key_cannot_cross_work(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _planned(service, "WORK-001")
    _planned(service, "WORK-002")
    service.add_relation("WORK-001", "WORK-002", "blocks", "rel-1")

    with pytest.raises(WorkRegistryError, match="其他 Work"):
        service.add_relation("WORK-002", "WORK-001", "blocks", "rel-1")


def test_scope_paths_must_be_relative_and_contained(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(WorkRegistryError, match="非法 scope"):
        service.create_work(
            work_id="WORK-001",
            subject_project_id="SW-2026-008",
            kind=WorkKind.BUG,
            title="Escape",
            owner="agent-a",
            scope_paths=["../outside.py"],
            source_fingerprint="sha256:abc",
            idempotency_key="escape",
        )
