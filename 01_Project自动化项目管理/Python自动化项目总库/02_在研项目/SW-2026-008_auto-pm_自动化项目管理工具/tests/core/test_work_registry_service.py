"""Work Registry transaction, authorization, and state-machine tests."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from auto_pm.core.mission_service import MissionService
from auto_pm.core.work_registry_service import WorkRegistryError, WorkRegistryService

from auto_pm.contracts.continuity import WorkItem, WorkKind, WorkState
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _directory_link(link: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            pytest.skip(f"junction unavailable: {result.stderr or result.stdout}")
    else:
        link.symlink_to(target, target_is_directory=True)


def _service(root: Path) -> WorkRegistryService:
    _git(root, "init")
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


def _planned(service: WorkRegistryService, work_id: str = "WORK-001") -> WorkItem:
    return cast(
        WorkItem,
        service.create_work(
            work_id=work_id,
            subject_project_id="SW-2026-008",
            kind=WorkKind.WBS,
            title="Context follow-up",
            owner="agent-a",
            scope_paths=["auto_pm/core/example.py"],
            source_fingerprint="sha256:abc",
            idempotency_key=f"create-{work_id}",
        ),
    )


def _mission(
    root: Path, *, decision_id: str = "DEC-MISSION", allowed: frozenset[WorkKind] | None = None
) -> str:
    files = ["auto_pm/core/example.py"]
    _decision(root, decision_id, "SW-2026-008", files)
    instant = datetime(2026, 9, 9, 12, tzinfo=UTC)
    authority = AuthorityEnvelope(
        envelope_id="AUTH-TEST",
        subject_project_id="SW-2026-008",
        change_id="CHG-SCPT-TEST",
        decision_id=decision_id,
        scope_paths=tuple(files),
        allowed_child_work_kinds=allowed if allowed is not None else frozenset({WorkKind.WBS}),
        valid_from=instant - timedelta(hours=1),
        expires_at=instant + timedelta(hours=1),
        audit=AuthorityAudit(
            created_by="architect", created_at=instant, approved_by="architect",
            approved_at=instant, source_fingerprint="sha256:" + "a" * 64,
        ),
    )
    mission_id = f"MISSION-{decision_id.removeprefix('DEC-')}"
    MissionService(root, now=lambda: instant).create(
        mission_id=mission_id, subject_project_id="SW-2026-008", title="Test Mission",
        objective="Test Mission", acceptance_criteria=["safe"], authority=authority,
        created_by="architect", idempotency_key=f"mission-{decision_id}",
    )
    return mission_id


def test_mission_derives_one_authorized_wbs_work_and_replays(tmp_path: Path) -> None:
    service = _service(tmp_path)
    mission_id = _mission(tmp_path)

    first = service.create_from_mission(
        mission_id=mission_id, owner="agent-a", scope_paths=["auto_pm/core/example.py"]
    )
    second = service.create_from_mission(
        mission_id=mission_id, owner="agent-a", scope_paths=["auto_pm/core/example.py"]
    )

    assert first == second
    assert first.kind is WorkKind.WBS
    assert first.authorization_ref == "DEC-MISSION"


def test_mission_derivation_rejects_missing_wbs_authority(tmp_path: Path) -> None:
    service = _service(tmp_path)
    mission_id = _mission(tmp_path, allowed=frozenset())

    with pytest.raises(WorkRegistryError, match="WBS"):
        service.create_from_mission(
            mission_id=mission_id, owner="agent-a", scope_paths=["auto_pm/core/example.py"]
        )
    assert service._store.list_works("SW-2026-008") == ()

def test_mission_derivation_rejects_other_owner_path_conflict(tmp_path: Path) -> None:
    service = _service(tmp_path)
    mission_id = _mission(tmp_path, decision_id="DEC-CONFLICT")
    _planned(service, "WORK-OTHER")
    with pytest.raises(WorkRegistryError, match="owner=agent-a"):
        service.create_from_mission(
            mission_id=mission_id, owner="agent-b", scope_paths=["auto_pm/core/example.py"]
        )


def test_initializes_separate_wal_database(tmp_path: Path) -> None:
    _service(tmp_path)

    db = tmp_path / ".auto-pm" / "continuity.db"
    assert db.is_file()
    assert not (tmp_path / ".auto-pm" / "index.db").exists()
    with sqlite3.connect(db) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
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


def test_work_graph_rejects_cross_project_and_cycle_relations(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _planned(service, "WORK-001")
    _planned(service, "WORK-002")
    service.add_relation("WORK-001", "WORK-002", "blocks", "rel-forward")

    with pytest.raises(WorkRegistryError, match="循环"):
        service.add_relation("WORK-002", "WORK-001", "blocks", "rel-cycle")

    service.create_work(
        work_id="WORK-OTHER",
        subject_project_id="SYS-2026-001",
        kind=WorkKind.GOVERNANCE,
        title="Other project",
        owner="agent-b",
        scope_paths=["other.py"],
        source_fingerprint="sha256:other",
        idempotency_key="create-other",
    )
    with pytest.raises(WorkRegistryError, match="跨项目"):
        service.add_relation("WORK-001", "WORK-OTHER", "blocks", "rel-cross-project")


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


def test_store_write_boundaries_reject_linked_worktree_before_side_effect(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Store Test",
            "-c",
            "user.email=store@example.invalid",
            "commit",
            "-m",
            "baseline",
        ],
        check=True,
        capture_output=True,
    )
    linked = tmp_path.parent / f"{tmp_path.name}-linked"
    _git(tmp_path, "worktree", "add", "--detach", str(linked), "HEAD")
    store = ContinuityStore(linked)

    with pytest.raises(ContinuityStoreError, match="linked worktree"):
        store.initialize("2026-09-11T00:00:00+00:00", "test")
    with pytest.raises(ContinuityStoreError, match="linked worktree"):
        store.create_work({}, "direct-transaction", "2026-09-11T00:00:00+00:00")
    with pytest.raises(ContinuityStoreError, match="linked worktree"):
        store._checkpoint_completed_migration()
    assert not (linked / ".auto-pm").exists()


def test_store_revalidates_late_runtime_junction_before_every_write(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    store = ContinuityStore(tmp_path)
    external = tmp_path.parent / f"{tmp_path.name}-external-runtime"
    _directory_link(tmp_path / ".auto-pm", external)

    with pytest.raises(ContinuityStoreError, match="symlink/junction"):
        store.initialize("2026-09-11T00:00:00+00:00", "test")
    with pytest.raises(ContinuityStoreError, match="symlink/junction"):
        store.create_work({}, "late-junction", "2026-09-11T00:00:00+00:00")
    with pytest.raises(ContinuityStoreError, match="symlink/junction"):
        store._checkpoint_completed_migration()
    assert list(external.iterdir()) == []


def test_store_rejects_sqlite_sidecar_junction_before_connect(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    runtime_dir = tmp_path / ".auto-pm"
    runtime_dir.mkdir()
    store = ContinuityStore(tmp_path)
    external = tmp_path.parent / f"{tmp_path.name}-external-sidecar"
    _directory_link(runtime_dir / "continuity.db-wal", external)

    with pytest.raises(ContinuityStoreError, match="sidecar|symlink/junction"):
        store.initialize("2026-09-11T00:00:00+00:00", "test")
    with pytest.raises(ContinuityStoreError, match="sidecar|symlink/junction"):
        store.create_work({}, "sidecar-junction", "2026-09-11T00:00:00+00:00")

    assert list(external.iterdir()) == []
    assert not (runtime_dir / "continuity.db").exists()


def test_store_strict_reads_do_not_invoke_mutation_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path)
    expected = _planned(service)

    def forbidden_guard(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("read path invoked mutation guard")

    monkeypatch.setattr(
        "auto_pm.infrastructure.continuity_store.require_control_root",
        forbidden_guard,
    )

    assert service.get_work(expected.work_id) == expected


def test_store_rejects_hardlinked_database_before_read_or_write(tmp_path: Path) -> None:
    service = _service(tmp_path)
    expected = _planned(service)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    alias = tmp_path / "continuity-external-alias.db"
    before = db_path.read_bytes()
    try:
        os.link(db_path, alias)
    except OSError as error:
        pytest.skip(f"hardlink unavailable: {error}")
    store = ContinuityStore(tmp_path)

    with pytest.raises(ContinuityStoreError, match="唯一链接"):
        store.get_work(expected.work_id)
    with pytest.raises(ContinuityStoreError, match="唯一链接"):
        store.create_work({}, "hardlink-write", "2026-09-11T00:00:00+00:00")

    assert db_path.read_bytes() == before
    assert alias.read_bytes() == before
    alias.unlink()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM work_items").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
