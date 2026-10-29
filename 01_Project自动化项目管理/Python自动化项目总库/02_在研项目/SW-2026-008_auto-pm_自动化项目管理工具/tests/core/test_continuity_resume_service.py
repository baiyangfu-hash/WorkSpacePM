"""Resume v2 and PM_SESSION projection boundary tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from auto_pm.application.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.application.core.continuity_resume_service import (
    ContinuityResumeError,
    ContinuityResumeService,
)
from auto_pm.application.core.mission_service import MissionService
from auto_pm.application.core.pm_session_projection_service import (
    PmSessionProjectionError,
    PmSessionProjectionService,
)
from auto_pm.application.core.work_registry_service import WorkRegistryService
from auto_pm.contracts.continuity import RunState, WorkKind, WorkState
from auto_pm.contracts.decision_package import (
    RUNTIME_CAPABILITY_KEY,
    DecisionPackageDTO,
    RuntimeDecisionAction,
    RuntimeDecisionCapability,
    RuntimeDecisionOutcome,
)
from auto_pm.contracts.execution_adapter import ExecutionStartEvidence
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope, MissionState
from auto_pm.infrastructure.continuity_store import (
    ContinuityStore,
    ContinuityStoreError,
    _StoreInventory,
)


def _workspace(root: Path) -> Path:
    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    (root / "README.md").write_text("baseline\n", encoding="utf-8", errors="replace")
    (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8", errors="replace")
    subprocess.run(
        ["git", "-C", str(root), "add", "README.md", ".gitignore"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Resume Test",
            "-c",
            "user.email=resume@example.invalid",
            "commit",
            "-m",
            "baseline",
        ],
        check=True,
        capture_output=True,
    )
    project = root / "SW-2026-008"
    project.mkdir()
    (project / ".copier-answers.yml").write_text(
        "project_id: SW-2026-008\nproject_name: Resume Test\nstack: python\n",
        encoding="utf-8",
    )
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": "SW-2026-008",
                        "project_root": "SW-2026-008",
                        "development_root": "SW-2026-008",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return project


def _git_head(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()


def _work(root: Path, work_id: str) -> None:
    service = WorkRegistryService(root, now=lambda: "2026-09-09T12:00:00+00:00")
    service.initialize("test")
    service.create_work(
        work_id=work_id,
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title=work_id,
        owner="architect",
        scope_paths=["auto_pm/a.py"],
        source_fingerprint="sha256:abc",
        idempotency_key=f"create-{work_id}",
        read_only=True,
    )


def _accept_read_only_work(root: Path, work_id: str) -> None:
    _work(root, work_id)
    service = WorkRegistryService(root, now=lambda: "2026-09-09T12:00:00+00:00")
    service.transition(work_id, WorkState.IN_PROGRESS, f"start-{work_id}")
    service.transition(work_id, WorkState.VERIFYING, f"verify-{work_id}")
    service.transition(work_id, WorkState.ACCEPTED, f"accept-{work_id}")


def _authorized_target_work(root: Path, work_id: str) -> None:
    service = WorkRegistryService(root, now=lambda: "2026-09-09T12:00:00+00:00")
    service.initialize("test")
    decision_id = "DEC-20260909-A2TARGT1"
    decision = DecisionPackageDTO(
        decision_id=decision_id,
        project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-213",
        approved_scope="MODULE",
        approved_files=["auto_pm/a.py"],
        approver="fubai",
        approved_at="2026-09-09T12:00:00+00:00",
    )
    path = root / ".auto-pm" / "decisions" / f"{decision_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2).encode("utf-8"))
    service.create_work(
        work_id=work_id,
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title=work_id,
        owner="architect",
        scope_paths=["auto_pm/a.py"],
        source_fingerprint="sha256:abc",
        idempotency_key=f"create-{work_id}",
    )
    service.authorize(work_id, decision_id, f"authorize-{work_id}")


def _run(
    root: Path,
    *,
    work_id: str = "WORK-001",
    run_id: str = "RUN-001",
    lease_token: str = "lease-secret",
) -> None:
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    execution = ContinuityExecutionService(
        root,
        store=ContinuityStore(root, _clock=lambda: now),
        now=lambda: now,
    )
    execution.start_run(
        run_id=run_id,
        work_id=work_id,
        executor_id="agent-a",
        adapter="codex",
        owned_paths=["auto_pm/a.py"],
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head=_git_head(root),
        worktree_path=str(root),
        lease_token=lease_token,
        lease_seconds=900,
        idempotency_key="create-run",
    )
    execution.record_start_evidence(
        run_id=run_id,
        owner_id="agent-a",
        lease_token=lease_token,
        evidence=ExecutionStartEvidence(
            process_id=1001,
            session_id=f"session-{run_id}",
            started_at=now,
        ),
        idempotency_key=f"start-evidence-{run_id}",
    )


def _mission(root: Path, mission_id: str = "MISSION-001") -> None:
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    service = MissionService(root, now=lambda: now)
    service.initialize("test")
    authority = AuthorityEnvelope(
        envelope_id=f"AUTH-{mission_id}",
        subject_project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-200",
        decision_id="DEC-20260910-7421E80D",
        scope_paths=("auto_pm/a.py",),
        valid_from=now - timedelta(hours=1),
        expires_at=now + timedelta(days=1),
        audit=AuthorityAudit(
            created_by="Codex PM",
            created_at=now,
            approved_by="fubai",
            approved_at=now,
            source_fingerprint=f"sha256:{'a' * 64}",
        ),
    )
    service.create(
        mission_id=mission_id,
        subject_project_id="SW-2026-008",
        title="Resume mission",
        objective="Recover a user-approved mission.",
        acceptance_criteria=["Mission is visible on resume."],
        authority=authority,
        created_by="Codex PM",
        idempotency_key=f"create-{mission_id}",
    )
    service.transition(
        mission_id=mission_id,
        expected_version=1,
        new_state=MissionState.AWAITING_APPROVAL,
        root_work_id=None,
        idempotency_key=f"submit-{mission_id}",
    )


def _active_mission_with_root(root: Path, root_work_id: str) -> None:
    _mission(root)
    MissionService(root, now=lambda: datetime(2026, 9, 9, 12, 0, tzinfo=UTC)).transition(
        mission_id="MISSION-001",
        expected_version=2,
        new_state=MissionState.ACTIVE,
        root_work_id=root_work_id,
        idempotency_key="activate-MISSION-001",
    )


def test_empty_store_returns_explicitly_empty_execution_state(tmp_path: Path) -> None:
    _workspace(tmp_path)

    result = ContinuityResumeService(
        tmp_path, now=lambda: datetime(2026, 9, 9, 12, 1, tzinfo=UTC)
    ).collect(project_id="SW-2026-008")

    assert result.schema_version == "continuity-resume.v2"
    assert result.mission is None
    assert result.work is None
    assert result.run is None
    assert result.checkpoint is None
    assert result.lease is None
    assert result.work_candidates == ()
    assert result.run_candidates == ()
    assert result.next_legal_action == ""
    assert not (tmp_path / ".auto-pm" / "continuity.db").exists()


def test_resume_returns_one_unambiguous_work_and_run(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _run(tmp_path)

    result = ContinuityResumeService(
        tmp_path, now=lambda: datetime(2026, 9, 9, 12, 1, tzinfo=UTC)
    ).collect(project_id="SW-2026-008")

    assert result.work and result.work.work_id == "WORK-001"
    assert tuple(candidate.work_id for candidate in result.work_candidates) == ("WORK-001",)
    assert result.run and result.run.run_id == "RUN-001"
    assert tuple(candidate.run.run_id for candidate in result.run_candidates) == ("RUN-001",)
    assert result.lease and result.lease.owner_id == "agent-a"
    assert result.lease.schema_version == "lease-view.v1"
    assert "lease_token" not in result.lease.model_dump(mode="json")
    payload = result.model_dump(mode="json")
    assert "lease_token" not in payload
    assert "lease-secret" not in json.dumps(payload, ensure_ascii=False)
    assert result.checkpoint is None
    assert result.next_legal_action == "CONTINUE_RUN"


def test_accepted_work_is_not_a_default_resume_candidate(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-ACCEPTED")
    registry = WorkRegistryService(tmp_path, now=lambda: "2026-09-09T12:00:00+00:00")
    registry.transition("WORK-ACCEPTED", WorkState.IN_PROGRESS, "start-accepted")
    registry.transition("WORK-ACCEPTED", WorkState.VERIFYING, "verify-accepted")
    registry.transition("WORK-ACCEPTED", WorkState.ACCEPTED, "accept-accepted")
    _work(tmp_path, "WORK-READY")

    result = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")

    assert result.work and result.work.work_id == "WORK-READY"
    assert tuple(candidate.work_id for candidate in result.work_candidates) == ("WORK-READY",)
    assert result.conflicts == ()
    assert result.next_legal_action == "CREATE_RUN"


def test_resume_projects_mission_and_user_approval_boundary(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _mission(tmp_path)

    result = ContinuityResumeService(
        tmp_path, now=lambda: datetime(2026, 9, 9, 12, 1, tzinfo=UTC)
    ).collect(project_id="SW-2026-008")

    assert result.mission and result.mission.mission_id == "MISSION-001"
    assert result.work is None
    assert result.next_legal_action == "AWAIT_USER_APPROVAL"


def test_active_mission_selects_only_its_root_work(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-ROOT")
    _work(tmp_path, "WORK-OTHER")
    WorkRegistryService(tmp_path).transition("WORK-OTHER", WorkState.BLOCKED, "block-other")
    _active_mission_with_root(tmp_path, "WORK-ROOT")

    resume = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")

    assert resume.mission and resume.mission.root_work_id == "WORK-ROOT"
    assert resume.work and resume.work.work_id == "WORK-ROOT"
    assert resume.conflicts == ()
    with pytest.raises(ContinuityResumeError, match="root Work 不一致"):
        ContinuityResumeService(tmp_path).collect(
            project_id="SW-2026-008", work_id="WORK-OTHER"
        )


def test_accepted_mission_root_does_not_splice_unrelated_blocked_work(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _accept_read_only_work(tmp_path, "WORK-ROOT")
    _work(tmp_path, "WORK-OTHER")
    WorkRegistryService(tmp_path).transition("WORK-OTHER", WorkState.BLOCKED, "block-other")
    _active_mission_with_root(tmp_path, "WORK-ROOT")

    resume = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")

    assert resume.mission and resume.mission.root_work_id == "WORK-ROOT"
    assert resume.work and resume.work.work_id == "WORK-ROOT"
    assert tuple(candidate.work_id for candidate in resume.work_candidates) == ("WORK-OTHER",)
    assert resume.run is None and resume.lease is None
    assert resume.conflicts == ("MISSION_ROOT_NOT_EXECUTION_ACTIVE",)
    assert resume.next_legal_action == ""
    with pytest.raises(ContinuityResumeError, match="root Work 不一致"):
        ContinuityResumeService(tmp_path).collect(
            project_id="SW-2026-008", work_id="WORK-OTHER"
        )


def _copy_mission(tmp_path: Path, state_sql: str = "state") -> None:
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("DROP INDEX idx_one_active_mission_per_project")
        conn.execute(
            f"""INSERT INTO mission_items
            SELECT 'MISSION-002', subject_project_id, title, objective, {state_sql}, root_work_id,
                   acceptance_criteria_json, authority_json, version, created_by, created_at, updated_at
            FROM mission_items WHERE mission_id='MISSION-001'"""
        )


def test_two_active_missions_are_damaged_data_and_fail_closed(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _mission(tmp_path, "MISSION-001")
    _copy_mission(tmp_path)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("UPDATE mission_items SET state='ACTIVE', root_work_id='WORK-001'")
    result = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")

    assert result.mission is None
    assert result.conflicts == ("MULTIPLE_ACTIVE_MISSIONS",)
    assert result.next_legal_action == ""


def test_several_open_cards_and_none_in_hand_wait_for_the_user_without_guessing(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _mission(tmp_path, "MISSION-001")
    _copy_mission(tmp_path)
    result = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")

    assert result.mission is None and result.work is None and result.run is None
    assert [m.mission_id for m in result.mission_candidates] == ["MISSION-001", "MISSION-002"]
    assert result.conflicts == ()
    assert result.next_legal_action == "AWAIT_USER_SWITCH"


def test_resume_must_not_recommend_replacement_for_expired_nonterminal_run(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _run(tmp_path)

    result = ContinuityResumeService(
        tmp_path, now=lambda: datetime(2026, 9, 9, 12, 16, tzinfo=UTC)
    ).collect(project_id="SW-2026-008")

    assert result.run and result.run.run_id == "RUN-001"
    assert result.conflicts == ("LEASE_EXPIRED",)
    assert result.next_legal_action == "RECLAIM_EXPIRED_RUN"  # 不留空，也不推荐新建替代 Run
    payload = result.model_dump(mode="json")
    assert "lease_token" not in payload
    assert "lease-secret" not in json.dumps(payload, ensure_ascii=False)


def test_expired_nonterminal_run_blocks_replacement(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _run(tmp_path)

    replacement = ContinuityExecutionService(
        tmp_path, now=lambda: datetime(2026, 9, 9, 12, 16, tzinfo=UTC)
    )
    with pytest.raises(ContinuityExecutionError, match="非终态 Run"):
        replacement.start_run(
            run_id="RUN-002",
            work_id="WORK-001",
            executor_id="agent-b",
            adapter="codex",
            owned_paths=["auto_pm/a.py"],
            declared_dirty_paths=[],
            observed_dirty_paths=[],
            git_head=_git_head(tmp_path),
            worktree_path=str(tmp_path),
            lease_token="replacement-secret",
            lease_seconds=900,
            idempotency_key="create-replacement-run",
        )
    assert len(replacement._store.list_runs("WORK-001")) == 1


def test_resume_uses_recovery_run_after_expired_target_is_settled(tmp_path: Path) -> None:
    project = _workspace(tmp_path)
    _authorized_target_work(tmp_path, "WORK-001")
    _run(tmp_path)
    change_path = (
        project / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-SCPT" / "CHG-SCPT-2026-214.md"
    )
    change_path.parent.mkdir(parents=True, exist_ok=True)
    change_path.write_text(
        """# CHG-SCPT-2026-214
## 3. 变更基本信息
### 3.0 编号与项目
| 变更编号 | CHG-SCPT-2026-214 |
| 项目编号 | SW-2026-008 |
### 3.3 影响范围
| 影响范围 | MODULE |
### 3.4 申请信息
| 变更状态 | approved |
""",
        encoding="utf-8",
    )
    decision_id = "DEC-20260911-5C37A985"
    decision = DecisionPackageDTO(
        decision_id=decision_id,
        project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-214",
        approved_scope="MODULE",
        approved_files=["auto_pm/a.py", ".auto-pm/continuity.db"],
        approver="fubai",
        approved_at="2026-09-09T12:16:00+00:00",
        metadata={
            RUNTIME_CAPABILITY_KEY: RuntimeDecisionCapability(
                allowed_runtime_actions=(RuntimeDecisionAction.SETTLE_EXPIRED_RUN,),
                target_run_ids=("RUN-001",),
                allowed_outcomes=(RuntimeDecisionOutcome.CANCELLED,),
            )
        },
    )
    decision_path = tmp_path / ".auto-pm" / "decisions" / f"{decision_id}.json"
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_bytes(
        json.dumps(decision.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "add",
            "-f",
            "--",
            ".auto-pm/decisions/DEC-20260909-A2TARGT1.json",
            f".auto-pm/decisions/{decision_id}.json",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Resume Test",
            "-c",
            "user.email=resume@example.invalid",
            "commit",
            "-m",
            "bind runtime decisions",
        ],
        check=True,
        capture_output=True,
    )
    works = WorkRegistryService(tmp_path, now=lambda: "2026-09-09T12:16:00+00:00")
    works.create_work(
        work_id="WORK-RECOVERY",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Recovery",
        owner="agent-b",
        scope_paths=["auto_pm/a.py", ".auto-pm/continuity.db"],
        source_fingerprint="sha256:recovery",
        idempotency_key="create-recovery-work",
    )
    works.authorize("WORK-RECOVERY", decision_id, "authorize-recovery-work")
    works.transition("WORK-RECOVERY", WorkState.IN_PROGRESS, "start-recovery-work")
    now = datetime(2026, 9, 9, 12, 16, tzinfo=UTC)
    execution = ContinuityExecutionService(
        tmp_path,
        store=ContinuityStore(tmp_path, _clock=lambda: now),
        now=lambda: now,
    )
    execution.start_run(
        run_id="RUN-RECOVERY",
        work_id="WORK-RECOVERY",
        executor_id="agent-b",
        adapter="codex",
        owned_paths=["auto_pm/a.py", ".auto-pm/continuity.db"],
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head=_git_head(tmp_path),
        worktree_path=str(tmp_path),
        lease_token="recovery-secret",
        lease_seconds=900,
        idempotency_key="create-recovery-run",
    )
    execution.record_start_evidence(
        run_id="RUN-RECOVERY",
        owner_id="agent-b",
        lease_token="recovery-secret",
        evidence=ExecutionStartEvidence(
            process_id=1002,
            session_id="session-RUN-RECOVERY",
            started_at=now,
        ),
        idempotency_key="start-evidence-recovery-run",
    )
    execution.settle_expired_run(
        target_run_id="RUN-001",
        recovery_run_id="RUN-RECOVERY",
        recovery_owner_id="agent-b",
        recovery_lease_token="recovery-secret",
        decision_id=decision_id,
        outcome=RunState.CANCELLED,
        reason="Close the historical expired Run forward.",
        idempotency_key="settle-expired-run",
    )

    result = ContinuityResumeService(tmp_path, now=lambda: now).collect(
        project_id="SW-2026-008", work_id="WORK-RECOVERY"
    )

    assert result.run and result.run.run_id == "RUN-RECOVERY"
    assert result.lease and result.lease.owner_id == "agent-b"
    assert "lease_token" not in result.lease.model_dump(mode="json")
    assert result.next_legal_action == "CONTINUE_RUN"
    assert execution._store.list_runs("WORK-001") == ()
    target_history = execution._store.list_runs("WORK-001", include_terminal=True)
    assert target_history[0].state is RunState.CANCELLED
    historical = ContinuityResumeService(tmp_path, now=lambda: now).collect(
        project_id="SW-2026-008", work_id="WORK-001", run_id="RUN-001"
    )
    assert historical.run and historical.run.run_id == "RUN-001"
    assert "LEASE_EXPIRED" not in historical.conflicts
    assert historical.next_legal_action == ""
    assert historical.run_candidates == ()
    ambiguous = ContinuityResumeService(tmp_path, now=lambda: now).collect(project_id="SW-2026-008")
    assert ambiguous.conflicts == ("MULTIPLE_ACTIVE_WORKS",)


def test_multiple_active_works_fail_closed_without_guessing(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _work(tmp_path, "WORK-002")

    result = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")

    assert result.work is None
    assert result.run is None
    assert tuple(candidate.work_id for candidate in result.work_candidates) == (
        "WORK-001",
        "WORK-002",
    )
    assert result.run_candidates == ()
    assert result.conflicts == ("MULTIPLE_ACTIVE_WORKS",)
    assert result.next_legal_action == ""


def test_accepted_works_are_terminal_for_resume_selection(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _accept_read_only_work(tmp_path, "WORK-001")
    _accept_read_only_work(tmp_path, "WORK-002")

    result = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")

    assert result.work is None
    assert result.conflicts == ()


@pytest.mark.parametrize("blocked_count", [1, 2])
def test_accepted_history_does_not_mask_blocked_execution_candidates(
    tmp_path: Path, blocked_count: int
) -> None:
    _workspace(tmp_path)
    for index in range(83):
        _accept_read_only_work(tmp_path, f"WORK-ACCEPTED-{index:03d}")
    registry = WorkRegistryService(tmp_path, now=lambda: "2026-09-09T12:00:00+00:00")
    for index in range(blocked_count):
        work_id = f"WORK-BLOCKED-{index:03d}"
        _work(tmp_path, work_id)
        registry.transition(work_id, WorkState.BLOCKED, f"block-{work_id}")

    result = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")

    assert tuple((item.work_id, item.state) for item in result.work_candidates) == tuple(
        (f"WORK-BLOCKED-{index:03d}", WorkState.BLOCKED)
        for index in range(blocked_count)
    )
    assert (result.work.work_id if result.work else None) == (
        "WORK-BLOCKED-000" if blocked_count == 1 else None
    )
    assert result.conflicts == (() if blocked_count == 1 else ("MULTIPLE_ACTIVE_WORKS",))
    assert "lease_token" not in json.dumps(result.model_dump(mode="json"))


def test_explicit_accepted_work_is_admin_only_even_with_a_live_run(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-ACCEPTED")
    _run(tmp_path, work_id="WORK-ACCEPTED", run_id="RUN-ACCEPTED")
    registry = WorkRegistryService(tmp_path, now=lambda: "2026-09-09T12:00:00+00:00")
    registry.transition("WORK-ACCEPTED", WorkState.IN_PROGRESS, "start-accepted")
    registry.transition("WORK-ACCEPTED", WorkState.VERIFYING, "verify-accepted")
    registry.transition("WORK-ACCEPTED", WorkState.ACCEPTED, "accept-accepted")

    resume = ContinuityResumeService(tmp_path).collect(
        project_id="SW-2026-008", work_id="WORK-ACCEPTED"
    )
    assert resume.work and resume.work.state is WorkState.ACCEPTED
    assert resume.run is None and resume.lease is None and resume.run_candidates == ()
    assert resume.next_legal_action == "ADMIN_REVIEW_OR_CLOSE"
    with pytest.raises(ContinuityResumeError, match="不可恢复非终态 Run"):
        ContinuityResumeService(tmp_path).collect(
            project_id="SW-2026-008", work_id="WORK-ACCEPTED", run_id="RUN-ACCEPTED"
        )

    registry.transition("WORK-ACCEPTED", WorkState.CLOSED, "close-accepted")
    closed = ContinuityResumeService(tmp_path).collect(
        project_id="SW-2026-008", work_id="WORK-ACCEPTED"
    )
    assert closed.work and closed.work.state is WorkState.CLOSED
    assert closed.next_legal_action == "" and closed.run is None


def test_explicit_unknown_work_fails_closed(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-KNOWN")
    with pytest.raises(ContinuityResumeError, match="Work 不存在"):
        ContinuityResumeService(tmp_path).collect(
            project_id="SW-2026-008", work_id="WORK-UNKNOWN"
        )


def test_explicit_work_disambiguates_but_cross_project_fails(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _work(tmp_path, "WORK-002")
    _run(tmp_path, work_id="WORK-002", run_id="RUN-002", lease_token="lease-secret-2")
    result = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008", work_id="WORK-002")
    assert result.work and result.work.work_id == "WORK-002"

    with pytest.raises(ContinuityResumeError, match="Run 不属于选定 Work"):
        ContinuityResumeService(tmp_path).collect(
            project_id="SW-2026-008", work_id="WORK-001", run_id="RUN-002"
        )

    service = WorkRegistryService(tmp_path, now=lambda: "2026-09-09T12:00:00+00:00")
    service.create_work(
        work_id="WORK-OTHER",
        subject_project_id="SYS-2026-001",
        kind=WorkKind.GOVERNANCE,
        title="Other",
        owner="architect",
        scope_paths=["x.py"],
        source_fingerprint="sha256:def",
        idempotency_key="create-other",
        read_only=True,
    )
    with pytest.raises(ContinuityResumeError, match="subject project"):
        ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008", work_id="WORK-OTHER")


def test_multiple_nonterminal_runs_for_selected_work_fail_closed_without_guessing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _run(tmp_path)
    service = ContinuityResumeService(
        tmp_path, now=lambda: datetime(2026, 9, 9, 12, 1, tzinfo=UTC)
    )
    original_run = service._store.list_runs("WORK-001")[0]
    synthetic_run = original_run.model_copy(update={"run_id": "RUN-002"})
    original_get_lease = service._store.get_lease

    monkeypatch.setattr(
        service._store,
        "list_runs",
        lambda work_id: (original_run, synthetic_run),
    )
    monkeypatch.setattr(
        service._store,
        "get_lease",
        lambda run_id: original_get_lease("RUN-001").model_copy(
            update={"run_id": run_id}
        ),
    )

    result = service.collect(project_id="SW-2026-008", work_id="WORK-001")

    assert result.run is None
    assert tuple(candidate.run.run_id for candidate in result.run_candidates) == (
        "RUN-001",
        "RUN-002",
    )
    assert result.conflicts == ("MULTIPLE_ACTIVE_RUNS",)
    assert result.next_legal_action == ""
    payload = result.model_dump(mode="json")
    assert "lease_token" not in payload
    assert "lease-secret" not in json.dumps(payload, ensure_ascii=False)


def test_corrupt_continuity_store_fails_closed(tmp_path: Path) -> None:
    _workspace(tmp_path)
    path = tmp_path / ".auto-pm" / "continuity.db"
    path.parent.mkdir()
    path.write_text("not sqlite", encoding="utf-8")

    with pytest.raises(ContinuityResumeError, match="无法读取"):
        ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")


def test_future_continuity_schema_fails_closed_on_resume(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _mission(tmp_path)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("UPDATE schema_meta SET schema_version='continuity-store.v999'")

    with pytest.raises(ContinuityResumeError, match="未知或未来"):
        ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")


def _store_snapshot(db_path: Path) -> tuple[tuple[str, ...], dict[str, tuple[int, int, str]]]:
    tracked = tuple(
        path
        for path in (
            db_path,
            Path(f"{db_path}-wal"),
            Path(f"{db_path}-shm"),
            Path(f"{db_path}-journal"),
        )
        if path.exists()
    )
    entries = tuple(sorted(path.name for path in db_path.parent.iterdir()))
    files = {
        path.name: (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in tracked
    }
    return entries, files


def test_resume_succeeds_without_unmerged_wal_and_preserves_empty_sidecars(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _run(tmp_path)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    wal_path = Path(f"{db_path}-wal")
    shm_path = Path(f"{db_path}-shm")
    wal_path.touch()
    shm_path.touch()
    before = _store_snapshot(db_path)

    result = ContinuityResumeService(
        tmp_path, now=lambda: datetime(2026, 9, 9, 12, 1, tzinfo=UTC)
    ).collect(project_id="SW-2026-008")

    assert result.run and result.run.run_id == "RUN-001"
    assert _store_snapshot(db_path) == before


def test_resume_reads_latest_committed_wal_without_mutating_source(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    script = (
        "import os, sqlite3, sys; "
        "conn=sqlite3.connect(sys.argv[1]); "
        "conn.execute('PRAGMA journal_mode=WAL'); "
        "conn.execute('PRAGMA wal_autocheckpoint=0'); "
        "conn.execute(\"UPDATE work_items SET title='WAL committed' "
        "WHERE work_id='WORK-001'\"); "
        "conn.commit(); os._exit(0)"
    )
    subprocess.run([sys.executable, "-c", script, str(db_path)], check=True)
    wal_path = Path(f"{db_path}-wal")
    assert wal_path.is_file() and wal_path.stat().st_size > 0
    before = _store_snapshot(db_path)

    result = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")

    assert result.work is not None
    assert result.work.title == "WAL committed"
    assert _store_snapshot(db_path) == before


def test_strict_read_rejects_hot_rollback_journal_without_mutating_source(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    journal = Path(f"{db_path}-journal")
    journal.write_bytes(b"hot rollback journal sentinel")
    before = _store_snapshot(db_path)

    with pytest.raises(ContinuityStoreError, match="rollback journal"):
        ContinuityStore(tmp_path).get_work("WORK-001")

    assert _store_snapshot(db_path) == before


def test_strict_read_retries_drift_then_fails_busy_without_temp_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    store = ContinuityStore(tmp_path)
    snapshot_parent = tmp_path.parent / f"{tmp_path.name}-snapshot-temp"
    snapshot_parent.mkdir()
    original_inventory = ContinuityStore._source_inventory
    calls = 0

    def drifting_inventory(_cls: type[ContinuityStore], db_path: Path) -> _StoreInventory:
        nonlocal calls
        calls += 1
        inventory = original_inventory(db_path)
        # Each attempt takes two inventories (before and after the copy); the second always drifts.
        if calls % 2 != 0:
            return inventory
        database = inventory[0]
        drifted_database = (
            database[0],
            database[1],
            database[2] + 1,
            database[3],
            database[4],
            database[5],
        )
        return (drifted_database, *inventory[1:])

    monkeypatch.setattr(
        tempfile,
        "tempdir",
        str(snapshot_parent),
    )
    monkeypatch.setattr(
        ContinuityStore,
        "_source_inventory",
        classmethod(drifting_inventory),
    )

    with pytest.raises(ContinuityStoreError, match="BUSY"):
        store.get_work("WORK-001")
    assert list(snapshot_parent.iterdir()) == []


def test_strict_read_rejects_temp_root_inside_workspace_before_creating_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    in_workspace_temp = tmp_path / "caller-temp"
    in_workspace_temp.mkdir()
    monkeypatch.setattr(
        tempfile,
        "tempdir",
        str(in_workspace_temp),
    )

    with pytest.raises(ContinuityStoreError, match="workspace 外"):
        ContinuityStore(tmp_path).get_work("WORK-001")
    assert list(in_workspace_temp.iterdir()) == []


def _snapshot_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    parent = tmp_path.parent / f"{tmp_path.name}-snapshot-temp"
    parent.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(parent))
    return parent


def _count_copies(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    copied: list[str] = []
    original = shutil.copyfile

    def counting(source: Path, target: Path) -> object:
        copied.append(Path(source).name)
        return original(source, target)

    monkeypatch.setattr(shutil, "copyfile", counting)
    return copied


def _write_title(db_path: Path, title: str) -> None:
    """Write the way every store transaction does (WAL, BEGIN IMMEDIATE) on a connection of its own."""
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE work_items SET title=? WHERE work_id='WORK-001'", (title,))
        conn.commit()
    finally:
        conn.close()


def test_td105_a_write_that_starts_while_the_strict_read_copies_is_never_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TD-105: the copy once held share-deny handles on Windows, so this write was opened read-only ("readonly database")."""
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _snapshot_temp(tmp_path, monkeypatch)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    original = shutil.copyfile
    writes: list[str] = []

    def copy_with_a_concurrent_write(source: Path, target: Path) -> object:
        if not writes:
            writes.append("written during the copy")
            _write_title(db_path, writes[0])
        return original(source, target)

    monkeypatch.setattr(shutil, "copyfile", copy_with_a_concurrent_write)

    work = ContinuityStore(tmp_path).get_work("WORK-001")

    assert writes == ["written during the copy"]
    assert work.title == "written during the copy"


def test_td105_writes_on_one_thread_never_fail_while_another_thread_keeps_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The TD-SW008-105 acceptance: one thread reads snapshots non-stop, another creates and moves Work; no write may fail."""
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _snapshot_temp(tmp_path, monkeypatch)
    reader_store = ContinuityStore(tmp_path)
    stop = threading.Event()
    reads: list[str] = []
    read_errors: list[str] = []

    def keep_reading() -> None:
        while not stop.is_set():
            try:
                reads.append(reader_store.get_work("WORK-001").title)
            except ContinuityStoreError as error:
                if "BUSY" not in str(error):
                    read_errors.append(str(error))

    # Two readers share one store, as the cockpit's refresh and its own closure worker do.
    readers = [threading.Thread(target=keep_reading, daemon=True) for _ in range(2)]
    for reader in readers:
        reader.start()
    try:
        writer = WorkRegistryService(tmp_path, now=lambda: "2026-09-09T12:00:00+00:00")
        for index in range(2, 14):
            work_id = f"WORK-{index:03d}"
            _work(tmp_path, work_id)
            writer.transition(work_id, WorkState.IN_PROGRESS, f"start-{work_id}")
    finally:
        stop.set()
        for reader in readers:
            reader.join(timeout=30)
        reader_store.close_read_snapshot()

    assert not any(reader.is_alive() for reader in readers)
    assert read_errors == []
    assert reads, "the reader never got a snapshot"
    assert ContinuityStore(tmp_path).get_work("WORK-013").state is WorkState.IN_PROGRESS


def test_td105_the_strict_read_reuses_its_copy_while_the_source_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    snapshot_parent = _snapshot_temp(tmp_path, monkeypatch)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    before = _store_snapshot(db_path)
    copied = _count_copies(monkeypatch)
    store = ContinuityStore(tmp_path)

    for _ in range(5):
        assert store.get_work("WORK-001").title == "WORK-001"

    assert copied.count(db_path.name) == 1
    assert len(list(snapshot_parent.iterdir())) == 1
    assert _store_snapshot(db_path) == before
    store.close_read_snapshot()
    assert list(snapshot_parent.iterdir()) == []


def test_td105_a_committed_write_retires_the_reused_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    snapshot_parent = _snapshot_temp(tmp_path, monkeypatch)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    copied = _count_copies(monkeypatch)
    store = ContinuityStore(tmp_path)
    assert store.get_work("WORK-001").title == "WORK-001"
    first = list(snapshot_parent.iterdir())

    _write_title(db_path, "changed by another process")

    assert store.get_work("WORK-001").title == "changed by another process"
    assert copied.count(db_path.name) == 2
    second = list(snapshot_parent.iterdir())
    assert len(second) == 1 and second != first


def test_td105_a_retired_copy_stays_until_its_last_open_read_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    snapshot_parent = _snapshot_temp(tmp_path, monkeypatch)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    store = ContinuityStore(tmp_path)

    with store._read_connection() as held:
        (first,) = list(snapshot_parent.iterdir())
        with store._read_connection() as also_held:
            _write_title(db_path, "newer")
            assert store.get_work("WORK-001").title == "newer"
            assert first.is_dir() and len(list(snapshot_parent.iterdir())) == 2
        assert first.is_dir(), "one read still has the retired copy open"
        row = held.execute("SELECT title FROM work_items WHERE work_id='WORK-001'").fetchone()
        assert row["title"] == "WORK-001"
        assert also_held is not held

    assert not first.exists()
    assert len(list(snapshot_parent.iterdir())) == 1


def test_td105_a_copy_that_changed_on_disk_is_taken_again_not_reused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    snapshot_parent = _snapshot_temp(tmp_path, monkeypatch)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    copied = _count_copies(monkeypatch)
    store = ContinuityStore(tmp_path)
    store.get_work("WORK-001")
    (first,) = list(snapshot_parent.iterdir())
    copy = first / db_path.name
    copy.write_bytes(copy.read_bytes() + b"\0")

    assert store.get_work("WORK-001").title == "WORK-001"
    assert copied.count(db_path.name) == 2
    assert not first.exists()


def test_td105_a_new_copy_that_fails_the_integrity_check_is_refused_without_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    snapshot_parent = _snapshot_temp(tmp_path, monkeypatch)
    original = shutil.copyfile

    def corrupting(source: Path, target: Path) -> object:
        result = original(source, target)
        data = bytearray(Path(target).read_bytes())
        if Path(target).suffix == ".db" and len(data) > 8192:
            data[4096:8192] = b"\xff" * 4096
            Path(target).write_bytes(bytes(data))
        return result

    monkeypatch.setattr(shutil, "copyfile", corrupting)

    with pytest.raises(ContinuityStoreError):
        ContinuityStore(tmp_path).get_work("WORK-001")
    assert list(snapshot_parent.iterdir()) == []


def test_pm_session_projection_contains_no_execution_queue(tmp_path: Path) -> None:
    project = _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    result = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")
    target = project / "PM_SESSION_SW-2026-008.md"

    PmSessionProjectionService().write(result, target)
    content = target.read_text(encoding="utf-8")

    assert "pm-session-projection.v1" in content
    assert "source_of_truth: .auto-pm/continuity.db" in content
    assert "WORK-001" not in content
    assert "current_focus" not in content
    with pytest.raises(PmSessionProjectionError, match="subject project"):
        PmSessionProjectionService().write(result, tmp_path / "outside.md")


def test_a_permission_error_while_copying_counts_as_drift_and_is_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows: a writer that holds the file for a moment makes the copy raise PermissionError; that is drift, not a failed read."""
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    temp_parent = _snapshot_temp(tmp_path, monkeypatch)
    original = shutil.copyfile
    refused: list[str] = []

    def held_once(source: Path, target: Path) -> object:
        if not refused:
            refused.append(Path(source).name)
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        return original(source, target)

    monkeypatch.setattr(shutil, "copyfile", held_once)

    assert ContinuityStore(tmp_path).get_work("WORK-001").title == "WORK-001"
    assert refused == ["continuity.db"]
    assert list(temp_parent.iterdir()) == []


def test_a_copy_whose_bytes_differ_from_the_source_is_taken_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The copied bytes are hashed against the source inventory: a torn copy is never opened."""
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _snapshot_temp(tmp_path, monkeypatch)
    original = shutil.copyfile
    copies: list[str] = []

    def torn_once(source: Path, target: Path) -> object:
        copies.append(Path(source).name)
        result = original(source, target)
        if copies.count("continuity.db") == 1 and Path(source).name == "continuity.db":
            with open(target, "r+b") as stream:  # one flipped byte in the header area, as a tear would leave
                stream.seek(100)
                byte = stream.read(1)
                stream.seek(100)
                stream.write(bytes([byte[0] ^ 0xFF]))
        return result

    monkeypatch.setattr(shutil, "copyfile", torn_once)

    assert ContinuityStore(tmp_path).get_work("WORK-001").title == "WORK-001"
    assert copies.count("continuity.db") == 2


def test_a_write_that_lands_after_the_copy_but_before_the_second_inventory_is_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The copy matches the first inventory, but the source moved on before the second one: take it again, so the read is current."""
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _snapshot_temp(tmp_path, monkeypatch)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    original_inventory = ContinuityStore._file_inventory
    copied_inventories: list[str] = []

    def write_after_copy(path: Path, *, required: bool, transient: bool = False) -> object:
        # the first inventory of a copied file (not under the workspace) runs right after the copy: write then, once
        if not Path(path).is_relative_to(tmp_path) and not copied_inventories:
            copied_inventories.append(path.name)
            _write_title(db_path, "written after the copy")
        return original_inventory(path, required=required, transient=transient)

    monkeypatch.setattr(ContinuityStore, "_file_inventory", staticmethod(write_after_copy))

    assert ContinuityStore(tmp_path).get_work("WORK-001").title == "written after the copy"
    assert copied_inventories == ["continuity.db"]



def test_an_expired_lease_plus_another_conflict_still_gives_no_next_action(tmp_path: Path) -> None:
    """RECLAIM_EXPIRED_RUN 只在租约过期是唯一冲突时给；并存别的冲突（如身份未核实）仍留空（预审 #350）。"""
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _run(tmp_path)
    service = ContinuityResumeService(tmp_path, now=lambda: datetime(2026, 9, 9, 12, 16, tzinfo=UTC))
    real_resolve = service._contexts.resolve

    def resolve_with_identity_conflict(**kwargs: object) -> object:
        context = real_resolve(**kwargs)  # type: ignore[arg-type]
        return context.model_copy(update={"conflicts": (*context.conflicts, "RUNTIME_IDENTITY_UNVERIFIED")})

    service._contexts.resolve = resolve_with_identity_conflict  # type: ignore[method-assign,assignment]

    result = service.collect(project_id="SW-2026-008")

    assert set(result.conflicts) == {"LEASE_EXPIRED", "RUNTIME_IDENTITY_UNVERIFIED"}
    assert result.next_legal_action == ""
