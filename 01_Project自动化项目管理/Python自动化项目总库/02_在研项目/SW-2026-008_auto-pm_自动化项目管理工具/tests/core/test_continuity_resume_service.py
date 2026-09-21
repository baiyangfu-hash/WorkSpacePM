"""Resume v2 and PM_SESSION projection boundary tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from auto_pm.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.core.continuity_resume_service import ContinuityResumeError, ContinuityResumeService
from auto_pm.core.mission_service import MissionService
from auto_pm.core.pm_session_projection_service import (
    PmSessionProjectionError,
    PmSessionProjectionService,
)
from auto_pm.core.work_registry_service import WorkRegistryService

import auto_pm.infrastructure.continuity_store as continuity_store_module
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
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


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


def test_multiple_active_missions_fail_closed_without_guessing(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _mission(tmp_path, "MISSION-001")
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("DROP INDEX idx_one_open_mission_per_project")
        conn.execute(
            """INSERT INTO mission_items
            SELECT 'MISSION-002', subject_project_id, title, objective, state, root_work_id,
                   acceptance_criteria_json, authority_json, version, created_by, created_at, updated_at
            FROM mission_items WHERE mission_id='MISSION-001'"""
        )
    result = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")

    assert result.mission is None
    assert result.conflicts == ("MULTIPLE_ACTIVE_MISSIONS",)
    assert result.next_legal_action == ""


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
    assert result.next_legal_action == ""
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
    original_inventory = ContinuityStore._source_inventory.__func__
    calls = 0

    def drifting_inventory(cls, db_path):
        nonlocal calls
        calls += 1
        inventory = original_inventory(cls, db_path)
        if calls % 3 != 0:
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
        continuity_store_module.tempfile,
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
        continuity_store_module.tempfile,
        "tempdir",
        str(in_workspace_temp),
    )

    with pytest.raises(ContinuityStoreError, match="workspace 外"):
        ContinuityStore(tmp_path).get_work("WORK-001")
    assert list(in_workspace_temp.iterdir()) == []


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
