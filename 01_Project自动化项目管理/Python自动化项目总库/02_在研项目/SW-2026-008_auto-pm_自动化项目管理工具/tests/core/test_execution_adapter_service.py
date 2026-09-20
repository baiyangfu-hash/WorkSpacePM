"""Integration tests for A5 local adapter dispatch and cross-provider continuity."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from auto_pm.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.core.continuity_resume_service import ContinuityResumeService
from auto_pm.core.execution_adapter_service import (
    ExecutionDispatchError,
    ExecutionDispatchResult,
    ExecutionDispatchService,
)
from auto_pm.core.mission_service import MissionService
from auto_pm.core.work_registry_service import WorkRegistryService
from auto_pm.core.worktree_policy_service import WorktreePlan, WorktreePolicyService

from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.execution_adapter import (
    ExecutionAdapterKind,
    ExecutionRole,
    ExecutionStartEvidence,
    WorktreeMode,
)
from auto_pm.contracts.mission import (
    AuthorityAudit,
    AuthorityEnvelope,
    InternalRoutingPolicy,
    MissionState,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError

PROJECT_ID = "SW-TEST-001"
PROJECT_PATH = f"{PROJECT_ID}/README.md"
DECISION_ID = "DEC-20260910-A5TEST01"


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _workspace(root: Path) -> None:
    project = root / PROJECT_ID
    project.mkdir()
    (project / ".copier-answers.yml").write_text(
        "project_id: SW-TEST-001\nproject_name: Adapter Test\nstack: python\n",
        encoding="utf-8",
    )
    (project / "README.md").write_text("baseline\n", encoding="utf-8")
    control = root / "SYS-2026-001_WorkspaceGovernance"
    control.mkdir()
    (control / "PM_SESSION_SYS-2026-001.md").write_text("control\n", encoding="utf-8")
    runtime = root / "00_Infrastructure" / "auto_pm"
    (runtime / "releases" / "test-release").mkdir(parents=True)
    (runtime / "active_release.json").write_text(
        json.dumps({"release_id": "test-release"}), encoding="utf-8"
    )
    (control / "workspace_registry.json").write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": PROJECT_ID,
                        "project_root": PROJECT_ID,
                        "development_root": PROJECT_ID,
                        "control_project_id": "SYS-2026-001",
                        "control_pm_session": (
                            "SYS-2026-001_WorkspaceGovernance/PM_SESSION_SYS-2026-001.md"
                        ),
                        "runtime_root": "00_Infrastructure/auto_pm",
                    },
                    {
                        "project_id": "SYS-2026-001",
                        "project_root": "SYS-2026-001_WorkspaceGovernance",
                        "development_root": "SYS-2026-001_WorkspaceGovernance",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    _git(root, "init")
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.name=Adapter Test",
        "-c",
        "user.email=adapter@example.invalid",
        "commit",
        "-m",
        "baseline",
    )


def _authority(now: datetime) -> AuthorityEnvelope:
    return AuthorityEnvelope(
        envelope_id="AUTH-A5-001",
        subject_project_id=PROJECT_ID,
        change_id="CHG-SCPT-2026-208",
        decision_id=DECISION_ID,
        scope_paths=(PROJECT_PATH,),
        allowed_child_work_kinds=frozenset({WorkKind.WBS}),
        routing=InternalRoutingPolicy(
            allow_execution_branch_changes=True,
            allowed_execution_adapters=frozenset(
                {ExecutionAdapterKind.CODEX, ExecutionAdapterKind.TRAE}
            ),
            max_parallel_runs=1,
        ),
        valid_from=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=1),
        audit=AuthorityAudit(
            created_by="Codex PM",
            created_at=now,
            approved_by="fubai",
            approved_at=now,
            source_fingerprint=f"sha256:{'a' * 64}",
        ),
    )


def _write_decision(root: Path, now: datetime) -> None:
    path = root / ".auto-pm" / "decisions" / f"{DECISION_ID}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "decision_package.v1",
                "decision_id": DECISION_ID,
                "project_id": PROJECT_ID,
                "change_id": "CHG-SCPT-2026-208",
                "approved_scope": "SYSTEM",
                "approved_files": [PROJECT_PATH],
                "approver": "fubai",
                "approved_at": now.isoformat(),
                "decision_conclusion": "approved",
            }
        ),
        encoding="utf-8",
    )


def _ready(
    root: Path,
    *,
    routing: InternalRoutingPolicy | None = None,
) -> tuple[MissionService, WorkRegistryService, ExecutionDispatchService]:
    _workspace(root)
    now = datetime.now(UTC)
    _write_decision(root, now)
    works = WorkRegistryService(root)
    works.initialize("test")
    created = works.create_work(
        work_id="WORK-A5-001",
        subject_project_id=PROJECT_ID,
        kind=WorkKind.WBS,
        title="A5 adapter dispatch",
        owner="codex:agent-a",
        scope_paths=[PROJECT_PATH],
        source_fingerprint="sha256:test",
        idempotency_key="work-create-1",
    )
    works.authorize(created.work_id, DECISION_ID, "work-authorize-1")
    missions = MissionService(root)
    missions.initialize("test")
    authority = _authority(now)
    if routing is not None:
        authority = authority.model_copy(update={"routing": routing})
    draft = missions.create(
        mission_id="MISSION-A5-001",
        subject_project_id=PROJECT_ID,
        title="A5 adapter handoff",
        objective="Prepare a safe provider-neutral execution package.",
        acceptance_criteria=["Codex can hand off the same Run to Trae."],
        authority=authority,
        created_by="Codex PM",
        idempotency_key="mission-create-1",
        root_work_id=created.work_id,
    )
    awaiting = missions.transition(
        mission_id=draft.mission_id,
        expected_version=draft.version,
        new_state=MissionState.AWAITING_APPROVAL,
        root_work_id=None,
        idempotency_key="mission-awaiting-1",
    )
    missions.transition(
        mission_id=awaiting.mission_id,
        expected_version=awaiting.version,
        new_state=MissionState.ACTIVE,
        root_work_id=awaiting.root_work_id,
        idempotency_key="mission-active-1",
    )
    return missions, works, ExecutionDispatchService(root)


def test_codex_preparation_hands_the_same_run_to_trae_and_resume_is_exact(tmp_path: Path) -> None:
    missions, _, dispatch = _ready(tmp_path)
    mission = missions.get("MISSION-A5-001")

    prepared = dispatch.prepare(
        mission=mission,
        work_id="WORK-A5-001",
        run_id="RUN-A5-001",
        adapter=ExecutionAdapterKind.CODEX,
        executor_id="agent-a",
        lease_token="codex-lease-secret",
        lease_seconds=900,
        idempotency_key="dispatch-1",
        stack="python",
        force_isolation=True,
    )

    receipt = prepared.receipt
    assert receipt.status == "PREPARED"
    assert receipt.role is ExecutionRole.FULLSTACK_ENGINEER
    assert receipt.worktree_mode is WorktreeMode.ISOLATED
    assert receipt.branch_name == "codex/run-a5-001"
    assert "codex-lease-secret" not in receipt.model_dump_json()
    assert "codex-lease-secret" not in repr(prepared)

    execution = ContinuityExecutionService(tmp_path)
    run = execution.get_run("RUN-A5-001")
    assert run.state.value == "READY"
    run = execution.record_start_evidence(
        run_id=run.run_id,
        owner_id="codex:agent-a",
        lease_token="codex-lease-secret",
        evidence=ExecutionStartEvidence(
            process_id=4321,
            session_id="thread-a5-test",
            started_at=datetime.now(UTC),
        ),
        idempotency_key="record-start-evidence-1",
    )
    child_readme = Path(run.worktree_path) / PROJECT_PATH
    child_readme.write_text("changed\n", encoding="utf-8")
    checkpoint = execution.checkpoint(
        checkpoint_id="CP-A5-001",
        run_id=run.run_id,
        owner_id="codex:agent-a",
        lease_token="codex-lease-secret",
        summary="Prepared package verified before provider handoff.",
        git_head=run.git_head,
        dirty_paths=[PROJECT_PATH],
        evidence=["pytest:0"],
        idempotency_key="checkpoint-1",
    )
    handoff = execution.create_handoff(
        handoff_id="HO-A5-001",
        checkpoint_id=checkpoint.checkpoint_id,
        from_owner="codex:agent-a",
        to_owner="trae:agent-b",
        lease_token="codex-lease-secret",
        idempotency_key="handoff-1",
    )
    lease = execution.accept_handoff(
        handoff_id=handoff.handoff_id,
        receiver_id="trae:agent-b",
        new_lease_token="trae-lease-secret",
        lease_seconds=900,
        idempotency_key="handoff-accept-1",
    )

    resumed = ContinuityResumeService(tmp_path).collect(
        project_id=PROJECT_ID,
        work_id="WORK-A5-001",
        run_id="RUN-A5-001",
    )
    assert lease.owner_id == "trae:agent-b"
    assert resumed.run is not None and resumed.run.run_id == "RUN-A5-001"
    assert resumed.checkpoint is not None and resumed.checkpoint.checkpoint_id == "CP-A5-001"
    assert resumed.lease is not None and resumed.lease.owner_id == "trae:agent-b"


def test_dispatch_rejects_unapproved_adapter_and_implicit_parallel_run(tmp_path: Path) -> None:
    missions, works, dispatch = _ready(tmp_path)
    mission = missions.get("MISSION-A5-001")

    with pytest.raises(ExecutionDispatchError, match="未获"):
        dispatch.prepare(
            mission=mission,
            work_id="WORK-A5-001",
            run_id="RUN-A5-MANUAL",
            adapter=ExecutionAdapterKind.MANUAL,
            executor_id="operator-a",
            lease_token="manual-secret",
            lease_seconds=900,
            idempotency_key="dispatch-manual",
            stack="python",
            force_isolation=True,
        )

    dispatch.prepare(
        mission=mission,
        work_id="WORK-A5-001",
        run_id="RUN-A5-PRIMARY",
        adapter=ExecutionAdapterKind.CODEX,
        executor_id="agent-a",
        lease_token="primary-secret",
        lease_seconds=900,
        idempotency_key="dispatch-primary",
        stack="python",
        force_isolation=True,
    )
    second = works.create_work(
        work_id="WORK-A5-002",
        subject_project_id=PROJECT_ID,
        kind=WorkKind.WBS,
        title="Second A5 work",
        owner="trae:agent-b",
        scope_paths=[PROJECT_PATH],
        source_fingerprint="sha256:second",
        idempotency_key="work-create-2",
    )
    works.authorize(second.work_id, DECISION_ID, "work-authorize-2")

    with pytest.raises(ExecutionDispatchError, match="max_parallel_runs"):
        dispatch.prepare(
            mission=mission,
            work_id=second.work_id,
            run_id="RUN-A5-SECOND",
            adapter=ExecutionAdapterKind.TRAE,
            executor_id="agent-b",
            lease_token="second-secret",
            lease_seconds=900,
            idempotency_key="dispatch-second",
            stack="python",
            force_isolation=True,
        )


def test_dispatch_from_linked_worktree_fails_before_any_mutation(tmp_path: Path) -> None:
    missions, _, _ = _ready(tmp_path)
    linked = tmp_path.parent / f"{tmp_path.name}-dispatch-linked"
    _git(tmp_path, "worktree", "add", "--detach", str(linked), "HEAD")
    shared_store = ContinuityStore(tmp_path)
    dispatch = ExecutionDispatchService(linked, store=shared_store)

    with pytest.raises(ExecutionDispatchError, match="linked worktree"):
        dispatch.prepare(
            mission=missions.get("MISSION-A5-001"),
            work_id="WORK-A5-001",
            run_id="RUN-A5-LINKED-REJECT",
            adapter=ExecutionAdapterKind.CODEX,
            executor_id="agent-linked",
            lease_token="linked-secret",
            lease_seconds=900,
            idempotency_key="dispatch-linked-reject",
            stack="python",
            force_isolation=True,
        )

    assert not (linked / ".auto-pm").exists()
    assert shared_store.list_runs("WORK-A5-001", include_terminal=True) == ()


def _prepare(root: Path, **overrides: Any) -> ExecutionDispatchResult:
    values: dict[str, Any] = {
        "mission": MissionService(root).get("MISSION-A5-001"),
        "work_id": "WORK-A5-001",
        "run_id": "RUN-E02-001",
        "adapter": ExecutionAdapterKind.CODEX,
        "executor_id": "agent-a",
        "lease_token": "e02-test-capability",
        "lease_seconds": 900,
        "idempotency_key": "dispatch-e02",
        "operation_id": "OP-E02-001",
        "stack": "python",
        "force_isolation": True,
    }
    dispatch = overrides.pop("dispatch", ExecutionDispatchService(root))
    values.update(overrides)
    return dispatch.prepare(**values)


def _counts(root: Path) -> tuple[int, int, int]:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        return tuple(
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("events", "run_items", "execution_leases")
        )


def test_execution_intent_survives_cold_process_replay(tmp_path: Path) -> None:
    _ready(tmp_path)
    prepared = _prepare(tmp_path)
    before = _counts(tmp_path)
    script = (
        "import sys\n"
        "from auto_pm.core.execution_adapter_service import ExecutionDispatchService\n"
        "from auto_pm.core.mission_service import MissionService\n"
        "root = sys.argv[1]\n"
        "result = ExecutionDispatchService(root).prepare("
        "mission=MissionService(root).get('MISSION-A5-001'),"
        "work_id='WORK-A5-001', run_id='RUN-E02-001', adapter='codex',"
        "executor_id='agent-a', lease_token='e02-test-capability', lease_seconds=900,"
        "idempotency_key='transport-retry', operation_id='OP-E02-001',"
        "stack='python', force_isolation=True)\n"
        "print(result.intent.model_dump_json())\n"
    )
    replay = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert json.loads(replay.stdout) == prepared.intent.model_dump(mode="json")
    assert _counts(tmp_path) == before
    store = ContinuityStore(tmp_path)
    assert store.get_execution_intent("OP-E02-001") == prepared.intent
    with closing(sqlite3.connect(store.db_path)) as conn:
        rows = conn.execute(
            "SELECT event_type, payload_json FROM events "
            "WHERE event_type IN ('EXECUTION_INTENT_PREPARED', 'RUN_CREATED') ORDER BY rowid"
        ).fetchall()
    assert [row[0] for row in rows] == ["EXECUTION_INTENT_PREPARED", "RUN_CREATED"]
    assert "e02-test-capability" not in rows[0][1]
    assert not list(tmp_path.rglob("*intent*.json"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"run_id": "RUN-E02-OTHER"},
        {"work_id": "WORK-OTHER"},
        {"adapter": ExecutionAdapterKind.TRAE},
        {"executor_id": "agent-b"},
        {"lease_seconds": 1200},
        {"force_isolation": False},
        {"stack": "plc"},
    ],
)
def test_execution_operation_rejects_changed_payload_before_effects(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    _ready(tmp_path)
    prepared = _prepare(tmp_path)
    before = _counts(tmp_path)
    with pytest.raises(ExecutionDispatchError, match="operation_id.*不同载荷"):
        _prepare(tmp_path, **overrides)
    assert _counts(tmp_path) == before
    assert ContinuityStore(tmp_path).get_execution_intent("OP-E02-001") == prepared.intent


def test_execution_operation_binds_full_mission_authority(tmp_path: Path) -> None:
    missions, _, _ = _ready(tmp_path)
    mission = missions.get("MISSION-A5-001")
    _prepare(tmp_path, mission=mission)
    changed = mission.model_copy(update={"objective": "Another objective"})
    before = _counts(tmp_path)
    with pytest.raises(ExecutionDispatchError, match="operation_id.*不同载荷"):
        _prepare(tmp_path, mission=changed)
    assert _counts(tmp_path) == before


def test_approved_dispatch_enforces_model_isolation_and_exact_declared_dirty_paths(
    tmp_path: Path,
) -> None:
    missions, _, dispatch = _ready(tmp_path)
    mission = missions.get("MISSION-A5-001")
    routing = mission.authority.routing.model_copy(
        update={
            "approved_model": "agent-a",
            "required_worktree_mode": WorktreeMode.ISOLATED,
            "declared_dirty_paths": (PROJECT_PATH,),
        }
    )
    approved = mission.model_copy(
        update={"authority": mission.authority.model_copy(update={"routing": routing})}
    )
    before = _counts(tmp_path)
    with pytest.raises(ExecutionDispatchError, match="executor/model"):
        dispatch.prepare(
            mission=approved,
            work_id="WORK-A5-001",
            run_id="RUN-E08A-WRONG",
            adapter=ExecutionAdapterKind.CODEX,
            executor_id="agent-other",
            lease_token="never-persist-this",
            lease_seconds=900,
            idempotency_key="dispatch-e08a-wrong",
            operation_id="OP-E08A-WRONG",
            stack="python",
        )
    assert _counts(tmp_path) == before

    prepared = dispatch.prepare(
        mission=approved,
        work_id="WORK-A5-001",
        run_id="RUN-E08A-001",
        adapter=ExecutionAdapterKind.CODEX,
        executor_id="agent-a",
        lease_token="approved-secret",
        lease_seconds=900,
        idempotency_key="dispatch-e08a",
        operation_id="OP-E08A-001",
        stack="python",
    )
    run = ContinuityStore(tmp_path).get_run("RUN-E08A-001")
    assert prepared.intent.status == "PREPARED"
    assert prepared.receipt.worktree_mode is WorktreeMode.ISOLATED
    assert run.state.value == "READY"
    assert run.declared_dirty_paths == (PROJECT_PATH,)
    assert "approved-secret" not in prepared.intent.model_dump_json()
    assert ContinuityStore(tmp_path).get_execution_microtask_plan("OP-E08A-001") is None
    assert not (tmp_path / ".auto-pm" / "microtasks").exists()


def test_lease_token_is_excluded_from_dispatch_fingerprint_and_persistence(
    tmp_path: Path,
) -> None:
    _ready(tmp_path)
    first = _prepare(tmp_path, lease_token="first-secret")
    before = _counts(tmp_path)
    replay = _prepare(tmp_path, lease_token="second-secret")

    assert replay.intent == first.intent
    assert replay.lease.token == "second-secret"
    assert _counts(tmp_path) == before
    serialized = first.intent.model_dump_json()
    assert "first-secret" not in serialized
    assert "second-secret" not in serialized


def test_intent_persistence_failure_rolls_back_before_git_or_run_effects(tmp_path: Path) -> None:
    _ready(tmp_path)
    database = tmp_path / ".auto-pm" / "continuity.db"
    with closing(sqlite3.connect(database)) as conn:
        conn.execute(
            "CREATE TRIGGER reject_execution_intent BEFORE INSERT ON events "
            "WHEN NEW.event_type='EXECUTION_INTENT_PREPARED' "
            "BEGIN SELECT RAISE(ABORT, 'injected disk write failure'); END"
        )
        conn.commit()
    before = _counts(tmp_path)
    with pytest.raises(ExecutionDispatchError, match="持久化失败"):
        _prepare(tmp_path)
    assert _counts(tmp_path) == before
    assert ContinuityStore(tmp_path).get_execution_intent("OP-E02-001") is None
    assert not (tmp_path / ".auto-pm" / "worktrees").exists()
    branches = subprocess.run(
        ["git", "-C", str(tmp_path), "branch", "--list", "codex/*"],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert not branches.stdout.strip()


class _CrashAtMaterialization(WorktreePolicyService):
    """Observe a real committed DB, then simulate process loss at an I/O boundary."""

    def __init__(self, root: Path, *, after: bool) -> None:
        super().__init__(root)
        self.root = root
        self.after = after

    def materialize(self, plan: WorktreePlan) -> WorktreePlan:
        intent = ContinuityStore(self.root).get_execution_intent("OP-E02-001")
        assert intent is not None
        assert not plan.worktree_path.exists()
        assert intent.receipt.worktree_path == str(plan.worktree_path)
        assert _counts(self.root)[1:] == (0, 0)
        if self.after:
            super().materialize(plan)
        raise SystemExit("simulated process loss")


@pytest.mark.parametrize("after", [False, True])
def test_crash_replay_preserves_intent_without_repeating_dispatch(
    tmp_path: Path, after: bool
) -> None:
    _ready(tmp_path)
    dispatch = ExecutionDispatchService(
        tmp_path, worktrees=_CrashAtMaterialization(tmp_path, after=after)
    )
    with pytest.raises(SystemExit, match="process loss"):
        _prepare(tmp_path, dispatch=dispatch)
    store = ContinuityStore(tmp_path)
    intent = store.get_execution_intent("OP-E02-001")
    assert intent is not None
    target = Path(intent.receipt.worktree_path)
    assert target.exists() is after
    before = _counts(tmp_path)
    replay = _prepare(tmp_path)
    assert replay.intent == intent
    assert replay.receipt.status == "PREPARED"
    assert target.exists() is after
    assert _counts(tmp_path) == before
    assert store.list_runs("WORK-A5-001", include_terminal=True) == ()


def test_concurrent_operation_has_one_durable_winner(tmp_path: Path) -> None:
    _ready(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(_prepare, tmp_path) for _ in range(2)]
        results = [future.result(timeout=45) for future in futures]
    assert results[0].intent == results[1].intent
    assert results[0].receipt == results[1].receipt
    assert _counts(tmp_path)[1:] == (1, 1)
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM events WHERE aggregate_type='execution_intent'"
        ).fetchone()[0] == 1


def test_store_refuses_same_id_changed_receipt_and_same_run_other_operation(tmp_path: Path) -> None:
    _ready(tmp_path)
    prepared = _prepare(tmp_path)
    store = ContinuityStore(tmp_path)
    changed = prepared.intent.model_copy(
        update={"receipt": prepared.receipt.model_copy(update={"run_id": "RUN-OTHER"})}
    )
    with pytest.raises(ContinuityStoreError, match="不同载荷"):
        store.reserve_execution_intent(changed)
    with pytest.raises(ContinuityStoreError, match="run_id 已存在"):
        store.reserve_execution_intent(
            prepared.intent.model_copy(update={"operation_id": "OP-OTHER"})
        )


def test_replay_after_authority_expiry_is_read_only(tmp_path: Path) -> None:
    missions, _, _ = _ready(tmp_path)
    mission = missions.get("MISSION-A5-001")
    prepared = _prepare(tmp_path, mission=mission)
    before = _counts(tmp_path)
    later = ExecutionDispatchService(
        tmp_path, now=lambda: mission.authority.expires_at + timedelta(days=1)
    )
    replay = _prepare(tmp_path, mission=mission, dispatch=later)
    assert replay.intent == prepared.intent
    assert _counts(tmp_path) == before
