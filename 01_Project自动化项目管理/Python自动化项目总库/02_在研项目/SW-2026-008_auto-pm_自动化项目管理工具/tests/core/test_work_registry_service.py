"""Work Registry transaction, authorization, and state-machine tests."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from auto_pm.core.mission_service import MissionService
from auto_pm.core.work_registry_service import WorkRegistryError, WorkRegistryService

from auto_pm.contracts.continuity import (
    EXECUTION_ACTIVE_WORK_STATES,
    POST_ACCEPTANCE_WORK_STATES,
    TERMINAL_WORK_STATES,
    WorkItem,
    WorkKind,
    WorkState,
)
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


def test_work_lifecycle_state_classes_partition_the_enum() -> None:
    groups = (
        EXECUTION_ACTIVE_WORK_STATES,
        POST_ACCEPTANCE_WORK_STATES,
        TERMINAL_WORK_STATES,
    )
    assert set().union(*groups) == set(WorkState)
    assert all(
        not first.intersection(second)
        for index, first in enumerate(groups)
        for second in groups[index + 1 :]
    )


@pytest.mark.parametrize(
    ("existing_state", "existing_path", "conflicts"),
    [
        (WorkState.ACCEPTED, "auto_pm/core/example.py", False),
        (WorkState.BLOCKED, "auto_pm/core/example.py", True),
        (WorkState.BLOCKED, "auto_pm/core/other.py", False),
    ],
)
def test_scope_conflicts_only_consider_execution_active_overlaps(
    tmp_path: Path, existing_state: WorkState, existing_path: str, conflicts: bool
) -> None:
    service = _service(tmp_path)
    mission_id = _mission(tmp_path)
    existing = service.create_work(
        work_id="WORK-EXISTING",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Existing",
        owner="agent-a",
        scope_paths=[existing_path],
        source_fingerprint="sha256:existing",
        idempotency_key="create-existing",
        read_only=True,
    )
    if existing_state is WorkState.ACCEPTED:
        service.transition(existing.work_id, WorkState.IN_PROGRESS, "start-existing")
        service.transition(existing.work_id, WorkState.VERIFYING, "verify-existing")
    service.transition(existing.work_id, existing_state, "settle-existing")

    def create_direct() -> WorkItem:
        return cast(WorkItem, service.create_work(
            work_id="WORK-DIRECT",
            subject_project_id="SW-2026-008",
            kind=WorkKind.GOVERNANCE,
            title="Direct",
            owner="agent-b",
            scope_paths=["auto_pm/core/example.py"],
            source_fingerprint="sha256:direct",
            idempotency_key="create-direct",
            read_only=True,
        ))

    # Direct Work creation remains available for governed recovery chains;
    # scope exclusion belongs to Mission-derived child Work selection.
    assert create_direct().state is WorkState.READY
    if conflicts:
        with pytest.raises(WorkRegistryError, match="active Work 路径冲突"):
            service.create_from_mission(
                mission_id=mission_id,
                owner="agent-b",
                scope_paths=["auto_pm/core/example.py"],
            )
    else:
        created = service.create_from_mission(
            mission_id=mission_id,
            owner="agent-b",
            scope_paths=["auto_pm/core/example.py"],
        )
        assert created.state is WorkState.READY
    assert service.get_work(existing.work_id).state is existing_state
    assert any(
        work.work_id == existing.work_id
        for work in service._store.list_works("SW-2026-008", include_terminal=True)
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


def test_accepted_work_only_allows_administrative_close(tmp_path: Path) -> None:
    service = _service(tmp_path)
    created = service.create_work(
        work_id="WORK-ACCEPTED",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Accepted",
        owner="architect",
        scope_paths=["auto_pm/core/example.py"],
        source_fingerprint="sha256:accepted",
        idempotency_key="create-accepted",
        read_only=True,
    )
    service.transition(created.work_id, WorkState.IN_PROGRESS, "start-accepted")
    service.transition(created.work_id, WorkState.VERIFYING, "verify-accepted")
    accepted = service.transition(created.work_id, WorkState.ACCEPTED, "accept-work")

    with pytest.raises(WorkRegistryError, match="非法 Work 状态迁移"):
        service.transition(accepted.work_id, WorkState.IN_PROGRESS, "reopen-accepted")
    assert service.get_work(accepted.work_id) == accepted
    closed = service.transition(accepted.work_id, WorkState.CLOSED, "close-accepted")
    assert closed.state is WorkState.CLOSED


def test_terminal_transition_exact_replay_preserves_version_and_event_count(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    _planned(service)
    _decision(tmp_path, "DEC-GOOD", "SW-2026-008", ["auto_pm/core/example.py"])
    ready = service.authorize("WORK-001", "DEC-GOOD", "authorize")
    in_progress = service.transition(ready.work_id, WorkState.IN_PROGRESS, "start")
    cancelled = service.transition(in_progress.work_id, WorkState.CANCELLED, "cancel")

    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM events WHERE aggregate_id=? AND event_type='WORK_TRANSITIONED'",
            (cancelled.work_id,),
        ).fetchone()[0]

    replayed = service.transition(cancelled.work_id, WorkState.CANCELLED, "cancel")

    assert replayed == cancelled
    assert replayed.version == cancelled.version
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
        after = conn.execute(
            "SELECT COUNT(*) FROM events WHERE aggregate_id=? AND event_type='WORK_TRANSITIONED'",
            (cancelled.work_id,),
        ).fetchone()[0]
    assert after == before


def test_transition_idempotency_key_cannot_cross_work(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = _planned(service, "WORK-001")
    second = _planned(service, "WORK-002")
    service.transition(first.work_id, WorkState.CANCELLED, "cancel-first")
    service.transition(second.work_id, WorkState.CANCELLED, "cancel-second")

    with pytest.raises(WorkRegistryError, match="其他 Work"):
        service.transition(second.work_id, WorkState.CANCELLED, "cancel-first")


def test_terminal_transition_rejects_new_key_and_retargeted_replay(tmp_path: Path) -> None:
    service = _service(tmp_path)
    work = _planned(service)
    cancelled = service.transition(work.work_id, WorkState.CANCELLED, "cancel")

    with pytest.raises(WorkRegistryError, match="非法"):
        service.transition(cancelled.work_id, WorkState.CANCELLED, "cancel-again")
    with pytest.raises(WorkRegistryError, match="绑定不同"):
        service.transition(cancelled.work_id, WorkState.CLOSED, "cancel")


def test_transition_replay_rejects_old_target_even_when_current_state_matches_request(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    _planned(service)
    _decision(tmp_path, "DEC-GOOD", "SW-2026-008", ["auto_pm/core/example.py"])
    ready = service.authorize("WORK-001", "DEC-GOOD", "authorize")
    in_progress = service.transition(ready.work_id, WorkState.IN_PROGRESS, "start")
    cancelled = service.transition(in_progress.work_id, WorkState.CANCELLED, "cancel")

    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
        before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    with pytest.raises(WorkRegistryError, match="绑定不同"):
        service.transition(cancelled.work_id, WorkState.CANCELLED, "start")

    assert service.get_work(cancelled.work_id).version == cancelled.version
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before


def test_transition_replay_rejects_same_work_key_from_another_event_type(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    work = _planned(service)

    with pytest.raises(WorkRegistryError, match="不属于 Work 状态迁移"):
        service.transition(work.work_id, WorkState.PLANNED, "create-WORK-001")


def test_store_transition_replay_requires_exact_persisted_payload(tmp_path: Path) -> None:
    service = _service(tmp_path)
    work = _planned(service)
    cancelled = service.transition(work.work_id, WorkState.CANCELLED, "cancel")
    store = ContinuityStore(tmp_path)

    replayed = store.transition(
        work.work_id,
        work.version,
        WorkState.CANCELLED.value,
        work.authorization_ref,
        "cancel",
        "2026-09-11T01:00:00+00:00",
    )

    assert replayed == cancelled
    with pytest.raises(ContinuityStoreError, match="绑定不同"):
        store.transition(
            work.work_id,
            work.version,
            WorkState.CANCELLED.value,
            "DEC-DIFFERENT",
            "cancel",
            "2026-09-11T01:00:00+00:00",
        )
    assert store.get_work(work.work_id).version == cancelled.version


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


# --- H11A: Work administrative adjudication (BLOCKED -> CANCELLED) -------------------------

ADJ_TARGET_DECISION = "DEC-20260910-A2TARGT1"
ADJ_DECISION = "DEC-20260911-5C37A985"
ADJ_RECOVERY_TOKEN = "recovery-secret"


def _adjudication_ready(
    root: Path,
    clock: Any,
    *,
    terminal_run: bool = True,
    capability_targets: tuple[str, ...] = ("WORK-TARGET",),
    decision_conditions: list[str] | None = None,
    reuse_original_chain: bool = False,
    tracked: tuple[str, ...] = (ADJ_TARGET_DECISION, ADJ_DECISION),
) -> tuple[WorkRegistryService, Any]:
    """Build one historical BLOCKED Work plus an independent, live adjudication authority.

    ``tracked`` selects which Decision files are committed before the recovery Run starts.
    """

    from auto_pm.contracts.continuity import RunState
    from auto_pm.contracts.decision_package import (
        RUNTIME_CAPABILITY_KEY,
        DecisionPackageDTO,
        RuntimeDecisionAction,
        RuntimeDecisionCapability,
        RuntimeDecisionOutcome,
    )
    from tests.core.test_continuity_execution_service import (
        _runtime_change,
        _services,
        _start,
        _start_evidence,
    )

    _works, execution = _services(root, clock)
    works = WorkRegistryService(root, store=execution._store, now=lambda: clock().isoformat())
    _runtime_change(root)
    canonical_paths = ["auto_pm/core/a.py", ".auto-pm/continuity.db"]
    decisions = root / ".auto-pm" / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    original = DecisionPackageDTO(
        decision_id=ADJ_TARGET_DECISION,
        project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-214" if reuse_original_chain else "CHG-SCPT-2026-213",
        approved_scope="MODULE",
        approved_files=["auto_pm/core/a.py"],
        approver="fubai",
        approved_at=clock().isoformat(),
        decision_conclusion="approved",
    )
    adjudication = DecisionPackageDTO(
        decision_id=ADJ_DECISION,
        project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-214",
        approved_scope="MODULE",
        approved_files=canonical_paths,
        approver="fubai",
        approved_at=clock().isoformat(),
        decision_conclusion="approved",
        conditions=list(decision_conditions or []),
        metadata={
            RUNTIME_CAPABILITY_KEY: RuntimeDecisionCapability(
                allowed_runtime_actions=(RuntimeDecisionAction.ADJUDICATE_BLOCKED_WORK,),
                target_run_ids=(),
                allowed_outcomes=(RuntimeDecisionOutcome.CANCELLED,),
                target_work_ids=capability_targets,
            )
        },
    )
    for item in (original, adjudication):
        (decisions / f"{item.decision_id}.json").write_bytes(
            json.dumps(item.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
        )
    for decision_id in tracked:
        _git(root, "add", "-f", "--", f".auto-pm/decisions/{decision_id}.json")
    _git(
        root,
        "-c",
        "user.name=Continuity Test",
        "-c",
        "user.email=continuity@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "bind decisions",
    )

    works.create_work(
        work_id="WORK-TARGET",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Historical target",
        owner="legacy-agent",
        scope_paths=["auto_pm/core/a.py"],
        source_fingerprint="sha256:target",
        idempotency_key="create-target-work",
    )
    works.authorize("WORK-TARGET", ADJ_TARGET_DECISION, "authorize-target-work")
    _start(
        execution,
        run_id="RUN-TARGET",
        work_id="WORK-TARGET",
        executor_id="legacy-agent",
        lease_token="target-secret",
        lease_seconds=900,
        idempotency_key="create-target-run",
    )
    _start_evidence(
        execution,
        run_id="RUN-TARGET",
        owner_id="legacy-agent",
        lease_token="target-secret",
        idempotency_key="record-target-start",
    )
    if terminal_run:
        execution.transition_run(
            "RUN-TARGET", RunState.FAILED, "legacy-agent", "target-secret", "fail-target"
        )
    works.transition("WORK-TARGET", WorkState.IN_PROGRESS, "target-in-progress")
    works.transition("WORK-TARGET", WorkState.BLOCKED, "target-blocked")

    works.create_work(
        work_id="WORK-RECOVERY",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Authorized adjudication",
        owner="recovery-agent",
        scope_paths=canonical_paths,
        source_fingerprint="sha256:recovery",
        idempotency_key="create-recovery-work",
    )
    works.authorize("WORK-RECOVERY", ADJ_DECISION, "authorize-recovery-work")
    works.transition("WORK-RECOVERY", WorkState.IN_PROGRESS, "start-recovery-work")
    _start(
        execution,
        run_id="RUN-RECOVERY",
        work_id="WORK-RECOVERY",
        executor_id="recovery-agent",
        lease_token=ADJ_RECOVERY_TOKEN,
        lease_seconds=900,
        idempotency_key="create-recovery-run",
        owned_paths=canonical_paths,
    )
    _start_evidence(
        execution,
        run_id="RUN-RECOVERY",
        owner_id="recovery-agent",
        lease_token=ADJ_RECOVERY_TOKEN,
        idempotency_key="record-recovery-start",
    )
    return works, execution


def _adjudicate(works: WorkRegistryService, **changes: Any) -> WorkItem:
    evidence, original_sha = works.adjudication_evidence("WORK-TARGET")
    values: dict[str, Any] = {
        "target_work_id": "WORK-TARGET",
        "expected_work_version": evidence.version,
        "expected_original_decision_sha256": original_sha,
        "expected_run_set_sha256": evidence.run_set_sha256,
        "expected_lease_set_sha256": evidence.lease_set_sha256,
        "recovery_run_id": "RUN-RECOVERY",
        "recovery_owner_id": "recovery-agent",
        "recovery_lease_token": ADJ_RECOVERY_TOKEN,
        "decision_id": ADJ_DECISION,
        "outcome": WorkState.CANCELLED,
        "reason": "Superseded historical Work; preserve evidence and retire from active index.",
        "idempotency_key": "adjudicate-target-work",
    }
    values.update(changes)
    return cast(WorkItem, works.adjudicate_blocked_work(**values))


def _history_snapshot(root: Path) -> dict[str, list[tuple[Any, ...]]]:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        return {
            "runs": conn.execute("SELECT * FROM run_items ORDER BY run_id").fetchall(),
            "leases": conn.execute("SELECT * FROM execution_leases ORDER BY run_id").fetchall(),
            "checkpoints": conn.execute("SELECT * FROM checkpoints ORDER BY rowid").fetchall(),
            "events": conn.execute("SELECT * FROM events ORDER BY rowid").fetchall(),
        }


def test_adjudication_evidence_is_read_only_and_reports_exact_bindings(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, _execution = _adjudication_ready(tmp_path, Clock())
    before = _history_snapshot(tmp_path)

    evidence, original_sha = works.adjudication_evidence("WORK-TARGET")

    assert _history_snapshot(tmp_path) == before
    assert evidence.adjudicable and evidence.blockers == ()
    assert evidence.state == "BLOCKED" and evidence.authorization_ref == ADJ_TARGET_DECISION
    assert evidence.run_states == (("RUN-TARGET", "FAILED", 3),)
    assert evidence.lease_states[0][0] == "RUN-TARGET" and evidence.lease_states[0][2] is True
    assert len(evidence.run_set_sha256) == 64 and len(evidence.lease_set_sha256) == 64
    assert len(original_sha) == 64


def test_adjudication_cancels_work_and_preserves_all_history(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, _execution = _adjudication_ready(tmp_path, Clock())
    before = _history_snapshot(tmp_path)
    blocked = works.get_work("WORK-TARGET")

    cancelled = _adjudicate(works)

    after = _history_snapshot(tmp_path)
    assert cancelled.state is WorkState.CANCELLED
    assert cancelled.version == blocked.version + 1
    assert cancelled.authorization_ref == ADJ_DECISION
    # Runs, leases, checkpoints and every earlier event are byte-identical.
    assert after["runs"] == before["runs"]
    assert after["leases"] == before["leases"]
    assert after["checkpoints"] == before["checkpoints"]
    assert after["events"][: len(before["events"])] == before["events"]
    appended = after["events"][len(before["events"]) :]
    assert len(appended) == 1 and appended[0][3] == "WORK_ADJUDICATED"
    payload = json.loads(appended[0][4])
    assert payload["target"]["previous_authorization_ref"] == ADJ_TARGET_DECISION
    assert payload["request"]["decision_id"] == ADJ_DECISION
    assert ADJ_RECOVERY_TOKEN not in appended[0][4]
    assert works.get_work("WORK-TARGET").state is WorkState.CANCELLED


def test_adjudication_replay_is_idempotent_and_rejects_semantic_drift(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, _execution = _adjudication_ready(tmp_path, Clock())
    evidence, original_sha = works.adjudication_evidence("WORK-TARGET")
    first = _adjudicate(works)
    events_after_first = _history_snapshot(tmp_path)["events"]

    replay = works.adjudicate_blocked_work(
        target_work_id="WORK-TARGET",
        expected_work_version=evidence.version,
        expected_original_decision_sha256=original_sha,
        expected_run_set_sha256=evidence.run_set_sha256,
        expected_lease_set_sha256=evidence.lease_set_sha256,
        recovery_run_id="RUN-RECOVERY",
        recovery_owner_id="recovery-agent",
        recovery_lease_token=ADJ_RECOVERY_TOKEN,
        decision_id=ADJ_DECISION,
        outcome=WorkState.CANCELLED,
        reason="Superseded historical Work; preserve evidence and retire from active index.",
        idempotency_key="adjudicate-target-work",
    )

    assert replay == first
    assert _history_snapshot(tmp_path)["events"] == events_after_first
    with pytest.raises(WorkRegistryError):
        works.adjudicate_blocked_work(
            target_work_id="WORK-TARGET",
            expected_work_version=evidence.version,
            expected_original_decision_sha256=original_sha,
            expected_run_set_sha256=evidence.run_set_sha256,
            expected_lease_set_sha256=evidence.lease_set_sha256,
            recovery_run_id="RUN-RECOVERY",
            recovery_owner_id="recovery-agent",
            recovery_lease_token=ADJ_RECOVERY_TOKEN,
            decision_id=ADJ_DECISION,
            outcome=WorkState.CANCELLED,
            reason="A different reason under the same idempotency key.",
            idempotency_key="adjudicate-target-work",
        )


def test_adjudication_rejects_non_terminal_run_without_any_write(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, _execution = _adjudication_ready(tmp_path, Clock(), terminal_run=False)
    before = _history_snapshot(tmp_path)
    evidence, _sha = works.adjudication_evidence("WORK-TARGET")
    assert not evidence.adjudicable
    assert any("非终态 Run" in item for item in evidence.blockers)

    with pytest.raises(WorkRegistryError, match="非终态 Run"):
        _adjudicate(works)

    assert _history_snapshot(tmp_path) == before
    assert works.get_work("WORK-TARGET").state is WorkState.BLOCKED


def test_adjudication_rejects_unreleased_terminal_lease(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, _execution = _adjudication_ready(tmp_path, Clock())
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
        conn.execute(
            "UPDATE execution_leases SET lease_token='legacy-token' WHERE run_id='RUN-TARGET'"
        )
        conn.commit()

    evidence, _sha = works.adjudication_evidence("WORK-TARGET")
    assert not evidence.adjudicable
    with pytest.raises(WorkRegistryError, match="lease 未释放"):
        _adjudicate(works)
    assert works.get_work("WORK-TARGET").state is WorkState.BLOCKED


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"expected_work_version": 1}, "版本"),
        ({"expected_run_set_sha256": "0" * 64}, "摘要"),
        ({"expected_lease_set_sha256": "0" * 64}, "摘要"),
        ({"expected_original_decision_sha256": "0" * 64}, "SHA-256"),
        ({"recovery_lease_token": "wrong-token"}, "恢复"),
        ({"recovery_owner_id": "someone-else"}, "恢复"),
    ],
)
def test_adjudication_binds_version_digests_and_recovery_lease(
    tmp_path: Path, change: dict[str, Any], message: str
) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, _execution = _adjudication_ready(tmp_path, Clock())
    before = _history_snapshot(tmp_path)

    with pytest.raises(WorkRegistryError, match=message):
        _adjudicate(works, **change)

    assert _history_snapshot(tmp_path) == before
    assert works.get_work("WORK-TARGET").state is WorkState.BLOCKED


def test_adjudication_requires_exact_decision_authority(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, _execution = _adjudication_ready(
        tmp_path, Clock(), capability_targets=("WORK-OTHER",)
    )
    with pytest.raises(WorkRegistryError, match="未授权目标 Work"):
        _adjudicate(works)
    assert works.get_work("WORK-TARGET").state is WorkState.BLOCKED


def test_adjudication_rejects_conditional_decision(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, _execution = _adjudication_ready(
        tmp_path, Clock(), decision_conditions=["only if reviewed"]
    )
    with pytest.raises(WorkRegistryError, match="无条件"):
        _adjudicate(works)


def test_adjudication_requires_change_independent_of_original_chain(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, _execution = _adjudication_ready(tmp_path, Clock(), reuse_original_chain=True)
    with pytest.raises(WorkRegistryError, match="独立于目标 Work 的原 CHG"):
        _adjudicate(works)


def test_adjudication_rejects_expired_recovery_lease(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    clock = Clock()
    works, _execution = _adjudication_ready(tmp_path, clock)
    clock.value += timedelta(seconds=901)

    with pytest.raises(WorkRegistryError, match="恢复"):
        _adjudicate(works)
    assert works.get_work("WORK-TARGET").state is WorkState.BLOCKED


def test_adjudication_rejects_secret_in_reason_and_non_cancelled_outcome(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, _execution = _adjudication_ready(tmp_path, Clock())
    with pytest.raises(WorkRegistryError, match="token"):
        _adjudicate(works, reason=f"leaks {ADJ_RECOVERY_TOKEN}")
    with pytest.raises(WorkRegistryError, match="CANCELLED"):
        _adjudicate(works, outcome=WorkState.CLOSED)
    assert works.get_work("WORK-TARGET").state is WorkState.BLOCKED


def test_adjudication_rolls_back_work_when_event_append_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, execution = _adjudication_ready(tmp_path, Clock())
    before = _history_snapshot(tmp_path)

    def broken(*_args: object, **_kwargs: object) -> None:
        raise ContinuityStoreError("simulated event failure")

    monkeypatch.setattr(execution._store, "_append_event", broken)
    with pytest.raises(WorkRegistryError, match="simulated"):
        _adjudicate(works)

    monkeypatch.undo()
    assert _history_snapshot(tmp_path) == before
    assert works.get_work("WORK-TARGET").state is WorkState.BLOCKED


# M2-GOV-ADJ (card 026 §5.1, §6 G2): first adjudication binds both Decisions to the recovery Run's
# control-root commit with the same strength as settle_expired_run; replay precedes every Git check.

_H11_ADJUDICATION_REQUEST_KEYS = frozenset(
    {
        "schema_version",
        "target_work_id",
        "expected_work_version",
        "expected_original_decision_id",
        "original_decision_sha256",
        "expected_run_set_sha256",
        "expected_lease_set_sha256",
        "recovery_run_id",
        "expected_recovery_run_version",
        "expected_recovery_lease_version",
        "recovery_work_id",
        "expected_recovery_work_version",
        "recovery_owner_id",
        "decision_id",
        "decision_sha256",
        "outcome",
        "reason",
    }
)


def _git_out(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout.strip()


def _advance_head(root: Path) -> None:
    _git(
        root,
        "-c",
        "user.name=Continuity Test",
        "-c",
        "user.email=continuity@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "advance control-root HEAD",
    )


def _adjudicated_payloads(root: Path) -> list[dict[str, Any]]:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        rows = conn.execute(
            "SELECT payload_json FROM events WHERE event_type='WORK_ADJUDICATED' ORDER BY rowid"
        ).fetchall()
    return [cast(dict[str, Any], json.loads(row[0])) for row in rows]


def _assert_nothing_written(root: Path, works: WorkRegistryService, before: Any) -> None:
    assert _history_snapshot(root) == before
    assert works.get_work("WORK-TARGET").state is WorkState.BLOCKED


@pytest.mark.parametrize(
    "tracked",
    [(ADJ_DECISION,), (ADJ_TARGET_DECISION,)],
    ids=["original-untracked", "adjudication-untracked"],
)
def test_adjudication_rejects_untracked_decision_and_rolls_back(
    tmp_path: Path, tracked: tuple[str, ...]
) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, _execution = _adjudication_ready(tmp_path, Clock(), tracked=tracked)
    before = _history_snapshot(tmp_path)
    evidence, _sha = works.adjudication_evidence("WORK-TARGET")
    if ADJ_TARGET_DECISION not in tracked:
        assert any("未被控制根 Git 跟踪" in item for item in evidence.blockers)

    # An untracked file makes `git ls-files --error-unmatch` itself fail (same fail-closed path
    # as settle_expired_run); a tracked-but-not-exact path reports 精确跟踪.
    with pytest.raises(WorkRegistryError, match="Decision Git commit/blob 不存在|精确跟踪"):
        _adjudicate(works)

    _assert_nothing_written(tmp_path, works, before)


@pytest.mark.parametrize(
    "decision_id", [ADJ_TARGET_DECISION, ADJ_DECISION], ids=["original", "adjudication"]
)
def test_adjudication_rejects_decision_dirty_against_head(
    tmp_path: Path, decision_id: str
) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, _execution = _adjudication_ready(tmp_path, Clock())
    path = tmp_path / ".auto-pm" / "decisions" / f"{decision_id}.json"
    # Same JSON content, different bytes: the file no longer matches the committed blob.
    path.write_text(
        json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False, indent=4),
        encoding="utf-8",
    )
    before = _history_snapshot(tmp_path)

    with pytest.raises(WorkRegistryError, match="脏改"):
        _adjudicate(works)

    _assert_nothing_written(tmp_path, works, before)


def test_adjudication_rejects_control_root_head_moved_before_first_execution(
    tmp_path: Path,
) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, _execution = _adjudication_ready(tmp_path, Clock())
    _advance_head(tmp_path)
    before = _history_snapshot(tmp_path)

    with pytest.raises(WorkRegistryError, match="精确匹配恢复 Run git_head"):
        _adjudicate(works)

    _assert_nothing_written(tmp_path, works, before)


def test_adjudication_rejects_decision_drift_during_recheck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, execution = _adjudication_ready(tmp_path, Clock())
    store = execution._store
    real_snapshot = store._decision_snapshot
    calls = {"count": 0}

    def drifting(decision_id: str) -> Any:
        dto, digest = real_snapshot(decision_id)
        calls["count"] += 1
        # The two post-check re-reads observe different bytes than the two pre-check reads.
        return (dto, "f" * 64) if calls["count"] > 2 else (dto, digest)

    before = _history_snapshot(tmp_path)
    monkeypatch.setattr(store, "_decision_snapshot", drifting)
    with pytest.raises(WorkRegistryError, match="漂移"):
        _adjudicate(works)
    monkeypatch.undo()

    _assert_nothing_written(tmp_path, works, before)


def test_adjudication_records_git_authority_and_keeps_request_fields(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, execution = _adjudication_ready(tmp_path, Clock())
    head = _git_out(tmp_path, "rev-parse", "HEAD")
    assert execution._store.get_run("RUN-RECOVERY").git_head == head

    _adjudicate(works)

    payload = _adjudicated_payloads(tmp_path)[-1]
    assert set(payload["request"]) == _H11_ADJUDICATION_REQUEST_KEYS
    assert payload["authority"] == {
        "schema_version": "decision-git-binding.v1",
        "git_head": head,
        "original_decision_id": ADJ_TARGET_DECISION,
        "original_decision_blob": _git_out(
            tmp_path, "rev-parse", f"{head}:.auto-pm/decisions/{ADJ_TARGET_DECISION}.json"
        ),
        "decision_id": ADJ_DECISION,
        "decision_blob": _git_out(
            tmp_path, "rev-parse", f"{head}:.auto-pm/decisions/{ADJ_DECISION}.json"
        ),
    }


def _replay_after(works: WorkRegistryService, evidence: Any, original_sha: str) -> WorkItem:
    return _adjudicate(
        works,
        expected_work_version=evidence.version,
        expected_original_decision_sha256=original_sha,
        expected_run_set_sha256=evidence.run_set_sha256,
        expected_lease_set_sha256=evidence.lease_set_sha256,
    )


def test_adjudication_replay_survives_head_moving_forward(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, _execution = _adjudication_ready(tmp_path, Clock())
    evidence, original_sha = works.adjudication_evidence("WORK-TARGET")
    first = _replay_after(works, evidence, original_sha)
    events = _history_snapshot(tmp_path)["events"]
    _advance_head(tmp_path)

    replay = _replay_after(works, evidence, original_sha)

    assert replay == first
    assert _history_snapshot(tmp_path)["events"] == events


def test_adjudication_replay_accepts_h11_event_without_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, execution = _adjudication_ready(tmp_path, Clock())
    store = execution._store
    evidence, original_sha = works.adjudication_evidence("WORK-TARGET")
    real_append = store._append_event

    def h11_writer(
        conn: Any, aggregate_id: str, event_type: str, payload: Any, *args: Any, **kwargs: Any
    ) -> Any:
        # Reproduce the pre-binding (H11) event shape: no ``authority`` sub-object.
        if event_type == "WORK_ADJUDICATED":
            payload = {key: value for key, value in payload.items() if key != "authority"}
        return real_append(conn, aggregate_id, event_type, payload, *args, **kwargs)

    monkeypatch.setattr(store, "_append_event", h11_writer)
    first = _replay_after(works, evidence, original_sha)
    monkeypatch.undo()
    assert "authority" not in _adjudicated_payloads(tmp_path)[-1]
    events = _history_snapshot(tmp_path)["events"]
    _advance_head(tmp_path)

    replay = _replay_after(works, evidence, original_sha)

    assert replay == first
    assert _history_snapshot(tmp_path)["events"] == events


def test_mission_derivation_rejects_a_path_outside_the_mission_authority_and_creates_nothing(tmp_path: Path) -> None:
    service = _service(tmp_path)
    mission_id = _mission(tmp_path)

    with pytest.raises(WorkRegistryError, match="超出 Mission authority"):
        service.create_from_mission(
            mission_id=mission_id, owner="agent-a", scope_paths=["auto_pm/core/example.py", "auto_pm/other.py"]
        )
    assert service._store.list_works("SW-2026-008") == ()


def test_mission_derivation_rejects_a_path_the_decision_no_longer_approves(tmp_path: Path) -> None:
    service = _service(tmp_path)
    mission_id = _mission(tmp_path, decision_id="DEC-NARROWED")
    _decision(tmp_path, "DEC-NARROWED", "SW-2026-008", ["auto_pm/core/unrelated.py"])

    with pytest.raises(WorkRegistryError, match="Decision approved_files"):
        service.create_from_mission(
            mission_id=mission_id, owner="agent-a", scope_paths=["auto_pm/core/example.py"]
        )
    assert service._store.list_works("SW-2026-008") == ()


def test_only_governed_entries_create_write_work() -> None:
    """TD-SW008-012: a new caller of WorkRegistryService.create_work must be reviewed, not slip in unguarded.

    Governed entries today: the CLI (implementation-card precheck), Mission derivation (authority + Decision scope,
    inside work_registry_service itself) and the Mission orchestrator (Decision scope + Mission scope escalation).
    """
    import re

    package = Path(__file__).resolve().parents[2] / "auto_pm"
    callers = sorted(
        path.relative_to(package).as_posix()
        for path in package.rglob("*.py")
        if re.search(r"\.create_work\(", path.read_text(encoding="utf-8", errors="replace"))
    )
    assert callers == [
        "application/core/mission_orchestrator.py",
        "application/core/work_registry_service.py",
        "ui/cli/continuity.py",
    ]
