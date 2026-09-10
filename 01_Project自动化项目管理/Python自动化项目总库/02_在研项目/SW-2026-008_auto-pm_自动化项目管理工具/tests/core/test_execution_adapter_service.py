"""Integration tests for A5 local adapter dispatch and cross-provider continuity."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from auto_pm.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.core.continuity_resume_service import ContinuityResumeService
from auto_pm.core.execution_adapter_service import ExecutionDispatchError, ExecutionDispatchService
from auto_pm.core.mission_service import MissionService
from auto_pm.core.work_registry_service import WorkRegistryService

from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind, ExecutionRole, WorktreeMode
from auto_pm.contracts.mission import (
    AuthorityAudit,
    AuthorityEnvelope,
    InternalRoutingPolicy,
    MissionState,
)

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


def _ready(root: Path) -> tuple[MissionService, WorkRegistryService, ExecutionDispatchService]:
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
    draft = missions.create(
        mission_id="MISSION-A5-001",
        subject_project_id=PROJECT_ID,
        title="A5 adapter handoff",
        objective="Prepare a safe provider-neutral execution package.",
        acceptance_criteria=["Codex can hand off the same Run to Trae."],
        authority=_authority(now),
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
