"""Read-only and privacy boundary tests for the default PM cockpit projection."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from auto_pm.application.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.application.core.mission_service import MissionService
from auto_pm.application.core.pm_closure_service import PmClosureService
from auto_pm.application.core.pm_cockpit_service import (
    PmCockpitError,
    PmCockpitService,
    _ProjectFacts,
)
from auto_pm.application.core.pm_facade_service import PmFacadeService
from auto_pm.application.core.work_registry_service import WorkRegistryService
from auto_pm.contracts.continuity import RunItem, RunState, WorkItem, WorkKind, WorkState
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind, WorktreeMode
from auto_pm.contracts.mission import (
    AuthorityAudit,
    AuthorityEnvelope,
    InternalRoutingPolicy,
    Mission,
    MissionState,
)
from auto_pm.contracts.pm_cockpit import (
    CockpitUserAction,
    PmCockpitCompletion,
    PmCockpitCompletionState,
    PmCockpitEvidence,
    PmCockpitEvidenceCurrency,
    PmCockpitFocus,
    PmCockpitResumeState,
)
from auto_pm.domain.change.ledger_reconciler import ReconcileDiff
from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.core.test_pm_closure_service import _MISSION_ID as _CLOSE_MISSION
from tests.core.test_pm_closure_service import _RUN_ID as _CLOSE_RUN
from tests.core.test_pm_closure_service import _WORK_ID as _CLOSE_WORK
from tests.core.test_pm_closure_service import (
    _accepted_lineage,
    _lineage_states,
    _ProjectionReconciler,
)
from tests.core.test_pm_facade_service import (
    _commit_baseline,
    _setup,
    _verified_acceptance_ready,
)
from tests.git_support import run_git


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run_git(root, *args)


def _git_root(root: Path) -> None:
    _git(root, "init")
    (root / "README.md").write_text("baseline\n", encoding="utf-8", errors="replace")
    _git(root, "add", "README.md")
    _git(
        root,
        "-c",
        "user.name=Cockpit Test",
        "-c",
        "user.email=cockpit@example.invalid",
        "commit",
        "-m",
        "baseline",
    )


def _registry(root: Path) -> None:
    path = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": "SW-2026-008",
                        "project_root": "projects/SW-2026-008_自动化项目管理工具",
                        "development_root": "projects/SW-2026-008_自动化项目管理工具",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _authority(now: datetime) -> AuthorityEnvelope:
    return AuthorityEnvelope(
        envelope_id="AUTH-COCKPIT-001",
        subject_project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-207",
        decision_id="DEC-20260910-1B4F38FD",
        scope_paths=("auto_pm/core/pm_cockpit_service.py",),
        valid_from=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=1),
        audit=AuthorityAudit(
            created_by="Codex PM",
            created_at=now,
            approved_by="fubai",
            approved_at=now,
            source_fingerprint=f"sha256:{'d' * 64}",
        ),
    )


def _flush_continuity_wal(root: Path) -> None:
    db_path = root / ".auto-pm" / "continuity.db"
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _seed_authorized_mission(root: Path) -> None:
    _git_root(root)
    now = datetime.now(UTC)
    works = WorkRegistryService(root)
    works.initialize("test")
    works.create_work(
        work_id="WORK-COCKPIT-001",
        subject_project_id="SW-2026-008",
        kind=WorkKind.WBS,
        title="老板驾驶舱",
        owner="Codex fullstack-engineer",
        scope_paths=["auto_pm/core/pm_cockpit_service.py"],
        source_fingerprint="sha256:test",
        idempotency_key="create-work",
        read_only=True,
    )
    missions = MissionService(root)
    missions.initialize("test")
    missions.create(
        mission_id="MISSION-COCKPIT-001",
        subject_project_id="SW-2026-008",
        title="面向用户的老板驾驶舱",
        objective="只向用户展示可决策的信息。",
        acceptance_criteria=["默认入口无写入副作用。"],
        authority=_authority(now),
        created_by="Codex PM",
        idempotency_key="create-mission",
        root_work_id="WORK-COCKPIT-001",
    )
    mission = missions.get("MISSION-COCKPIT-001")
    missions.transition(
        mission_id=mission.mission_id,
        expected_version=mission.version,
        new_state=MissionState.AWAITING_APPROVAL,
        root_work_id=None,
        idempotency_key="await-approval",
    )
    execution = ContinuityExecutionService(root)
    git_head = _git(root, "rev-parse", "HEAD").stdout.strip()
    run = execution.start_run(
        run_id="RUN-COCKPIT-001",
        work_id="WORK-COCKPIT-001",
        executor_id="Codex fullstack-engineer",
        adapter="codex",
        owned_paths=["auto_pm/core/pm_cockpit_service.py"],
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head=git_head,
        worktree_path=str(root),
        lease_token="must-not-leak",
        lease_seconds=900,
        idempotency_key="start-run",
    )
    execution.checkpoint(
        checkpoint_id="CP-COCKPIT-001",
        run_id=run.run_id,
        owner_id="Codex fullstack-engineer",
        lease_token="must-not-leak",
        summary="已建立只读证据投影。",
        git_head=git_head,
        dirty_paths=[],
        evidence=["pytest: focused pass"],
        idempotency_key="checkpoint",
    )
    _flush_continuity_wal(root)


def test_missing_continuity_store_is_friendly_and_creates_nothing(tmp_path: Path) -> None:
    _registry(tmp_path)

    snapshot = PmCockpitService(tmp_path).snapshot()

    assert len(snapshot.projects) == 1
    assert snapshot.projects[0].project_id == "SW-2026-008"
    assert "未建立连续性记录" in snapshot.notices[0]
    assert not (tmp_path / ".auto-pm").exists()


def test_cockpit_reads_evidence_without_lease_or_write_side_effects(tmp_path: Path) -> None:
    _registry(tmp_path)
    _seed_authorized_mission(tmp_path)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    baseline = db_path.read_bytes()

    service = PmCockpitService(tmp_path)
    snapshot = service.snapshot()
    evidence = service.evidence("SW-2026-008")

    card = snapshot.projects[0]
    assert card.user_action is CockpitUserAction.CONFIRM_START
    assert card.next_user_action == "确认开始执行"
    assert card.current_owner == "Codex fullstack-engineer"
    assert evidence.decision_id == "DEC-20260910-1B4F38FD"
    assert evidence.checkpoints[0].checkpoint_id == "CP-COCKPIT-001"
    rendered = evidence.model_dump_json().lower()
    assert "must-not-leak" not in rendered
    assert "lease" not in rendered
    assert db_path.read_bytes() == baseline


def test_cockpit_snapshot_reads_linked_worktree_without_side_effects(tmp_path: Path) -> None:
    _registry(tmp_path)
    _seed_authorized_mission(tmp_path)
    _git(tmp_path, "add", ".")
    _git(
        tmp_path,
        "-c",
        "user.name=Cockpit Test",
        "-c",
        "user.email=cockpit@example.invalid",
        "commit",
        "-m",
        "cockpit snapshot",
    )
    linked = tmp_path.parent / f"{tmp_path.name}-cockpit-linked"
    _git(tmp_path, "worktree", "add", "--detach", str(linked), "HEAD")
    before = {
        path.relative_to(linked).as_posix(): path.read_bytes()
        for path in linked.rglob("*")
        if path.is_file() and path.name != ".git"
    }

    snapshot = PmCockpitService(linked).snapshot()

    after = {
        path.relative_to(linked).as_posix(): path.read_bytes()
        for path in linked.rglob("*")
        if path.is_file() and path.name != ".git"
    }
    assert snapshot.projects[0].project_id == "SW-2026-008"
    assert after == before
    assert not _git(linked, "status", "--porcelain").stdout.strip()


def test_primary_work_ignores_accepted_history(tmp_path: Path) -> None:
    _git_root(tmp_path)
    work = WorkRegistryService(tmp_path, now=lambda: "2026-09-09T12:00:00+00:00")
    work.initialize("test")
    work.create_work(
        work_id="WORK-ACCEPTED",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Accepted history",
        owner="Codex",
        scope_paths=["auto_pm/example.py"],
        source_fingerprint="sha256:test",
        idempotency_key="create-accepted",
        read_only=True,
    )
    work.transition("WORK-ACCEPTED", WorkState.IN_PROGRESS, "start-accepted")
    work.transition("WORK-ACCEPTED", WorkState.VERIFYING, "verify-accepted")
    accepted = work.transition("WORK-ACCEPTED", WorkState.ACCEPTED, "accept-accepted")

    assert PmCockpitService._primary_work(None, (accepted,)) is None


def test_progress_requires_trusted_started_evidence_and_ignores_unrelated_blocked_run(
    tmp_path: Path,
) -> None:
    _registry(tmp_path)
    _seed_authorized_mission(tmp_path)
    store = PmCockpitService(tmp_path)._store
    mission = MissionService(tmp_path).get("MISSION-COCKPIT-001").model_copy(
        update={"state": MissionState.ACTIVE}
    )
    work = WorkRegistryService(tmp_path).get_work("WORK-COCKPIT-001").model_copy(
        update={"state": WorkState.IN_PROGRESS}
    )
    run = store.get_run("RUN-COCKPIT-001")
    runs = {work.work_id: (run,)}

    assert PmCockpitService._progress(mission, work, runs, frozenset()) == "系统执行"
    assert PmCockpitService._progress(
        mission, work, runs, frozenset({run.run_id})
    ) == "执行中"
    unrelated = run.model_copy(update={"run_id": "RUN-HISTORY", "state": RunState.BLOCKED})
    assert not PmCockpitService._is_blocked(
        mission, work, {work.work_id: (run,), "WORK-HISTORY": (unrelated,)}
    )


def test_activity_timeline_uses_only_current_mission_root_run(tmp_path: Path) -> None:
    _registry(tmp_path)
    _seed_authorized_mission(tmp_path)
    works = WorkRegistryService(tmp_path)
    works.create_work(
        work_id="WORK-HISTORY-001",
        subject_project_id="SW-2026-008",
        kind=WorkKind.WBS,
        title="历史辅助任务",
        owner="historical",
        scope_paths=["README.md"],
        source_fingerprint="sha256:history",
        idempotency_key="history-work",
        read_only=True,
    )
    head = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    ContinuityExecutionService(tmp_path).start_run(
        run_id="RUN-HISTORY-001",
        work_id="WORK-HISTORY-001",
        executor_id="historical",
        adapter="codex",
        owned_paths=["README.md"],
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head=head,
        worktree_path=str(tmp_path),
        lease_token="history-token",
        lease_seconds=900,
        idempotency_key="history-run",
    )
    _flush_continuity_wal(tmp_path)

    snapshot = PmCockpitService(tmp_path).snapshot()

    assert snapshot.activities
    assert {item.mission_id for item in snapshot.activities} == {"MISSION-COCKPIT-001"}
    assert {item.work_id for item in snapshot.activities} == {"WORK-COCKPIT-001"}
    assert {item.run_id for item in snapshot.activities} == {"RUN-COCKPIT-001"}
    assert {item.stage.value for item in snapshot.activities} >= {"READY", "CHECKPOINTED"}
    serialized = snapshot.model_dump_json().lower()
    assert "history-token" not in serialized
    assert "must-not-leak" not in serialized


# --- U05: reopen the same task, evidence currency and the single legal next step -------------


def _registry_for(root: Path, project_id: str) -> None:
    path = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": project_id,
                        "project_root": f"projects/{project_id}_cockpit",
                        "development_root": f"projects/{project_id}_cockpit",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _event_count(root: Path) -> int:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])


def _new_fields_text(evidence: PmCockpitEvidence) -> str:
    """Serialise only the U05 fields so privacy checks do not trip on legacy evidence text."""
    return json.dumps(
        [
            evidence.focus.model_dump(mode="json"),
            evidence.evidence_currency_reason,
            evidence.resume.model_dump(mode="json"),
        ],
        ensure_ascii=False,
    )


def test_reopened_cockpit_points_at_the_same_mission_work_and_run(tmp_path: Path) -> None:
    _registry(tmp_path)
    _seed_authorized_mission(tmp_path)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    baseline = db_path.read_bytes()
    git_status = _git(tmp_path, "status", "--porcelain").stdout

    first = PmCockpitService(tmp_path)
    before_close = first.evidence("SW-2026-008")
    snapshot = first.snapshot()
    del first
    after_reopen = PmCockpitService(tmp_path).evidence("SW-2026-008")

    expected = PmCockpitFocus(
        mission_id="MISSION-COCKPIT-001",
        work_id="WORK-COCKPIT-001",
        run_id="RUN-COCKPIT-001",
        run_state="已授权",
    )
    assert before_close.focus == after_reopen.focus == expected
    assert snapshot.projects[0].mission_id == expected.mission_id
    assert {item.work_id for item in snapshot.activities} == {expected.work_id}
    assert {item.run_id for item in snapshot.activities} == {expected.run_id}
    checkpoint = after_reopen.checkpoints[0]
    assert (checkpoint.run_id, checkpoint.is_current_run) == ("RUN-COCKPIT-001", True)
    assert after_reopen.resume.user_action is CockpitUserAction.CONFIRM_START
    assert after_reopen.evidence_currency is PmCockpitEvidenceCurrency.NOT_APPLICABLE
    assert db_path.read_bytes() == baseline
    assert _git(tmp_path, "status", "--porcelain").stdout == git_status


def test_focus_follows_the_newest_non_terminal_run_and_is_empty_without_a_mission(
    tmp_path: Path,
) -> None:
    _registry(tmp_path)
    _seed_authorized_mission(tmp_path)
    execution = ContinuityExecutionService(tmp_path)
    execution.transition_run(
        "RUN-COCKPIT-001",
        RunState.CANCELLED,
        "Codex fullstack-engineer",
        "must-not-leak",
        "cancel-first-run",
    )
    execution.start_run(
        run_id="RUN-COCKPIT-002",
        work_id="WORK-COCKPIT-001",
        executor_id="Codex fullstack-engineer",
        adapter="codex",
        owned_paths=["auto_pm/core/pm_cockpit_service.py"],
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head=_git(tmp_path, "rev-parse", "HEAD").stdout.strip(),
        worktree_path=str(tmp_path),
        lease_token="must-not-leak-either",
        lease_seconds=900,
        idempotency_key="start-second-run",
    )
    _flush_continuity_wal(tmp_path)

    focus = PmCockpitService(tmp_path).evidence("SW-2026-008").focus

    assert (focus.mission_id, focus.work_id, focus.run_id) == (
        "MISSION-COCKPIT-001",
        "WORK-COCKPIT-001",
        "RUN-COCKPIT-002",
    )

    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    _registry(empty_root)
    _git_root(empty_root)
    WorkRegistryService(empty_root).initialize("test")
    _flush_continuity_wal(empty_root)
    evidence = PmCockpitService(empty_root).evidence("SW-2026-008")
    assert evidence.focus == PmCockpitFocus()
    assert evidence.resume.state is PmCockpitResumeState.NO_ACTIVE_WORK
    assert evidence.checkpoints == ()


def _resume_inputs(
    root: Path,
) -> tuple[PmCockpitService, Mission, WorkItem, RunItem]:
    _registry(root)
    _seed_authorized_mission(root)
    service = PmCockpitService(root)
    mission = MissionService(root).get("MISSION-COCKPIT-001")
    work = WorkRegistryService(root).get_work("WORK-COCKPIT-001")
    run = service._store.get_run("RUN-COCKPIT-001")
    return service, mission, work, run


_NO_ACTION = CockpitUserAction.NONE
_REVIEW = CockpitUserAction.REVIEW_ESCALATION


@pytest.mark.parametrize(
    ("mission_state", "run_state", "started", "expected_state", "expected_action", "fragment"),
    [
        (MissionState.ACCEPTED, None, False, PmCockpitResumeState.WAITING_FOR_USER, CockpitUserAction.RETRY_SYNC, "尚未同步完成"),
        (MissionState.CLOSED, None, False, PmCockpitResumeState.NO_ACTIVE_WORK, _NO_ACTION, "暂无进行中"),
        (MissionState.CANCELLED, None, False, PmCockpitResumeState.NO_ACTIVE_WORK, _NO_ACTION, "暂无进行中"),
        (MissionState.BLOCKED, None, False, PmCockpitResumeState.NEEDS_REVIEW, _REVIEW, "阻塞"),
        (MissionState.AWAITING_APPROVAL, None, False, PmCockpitResumeState.WAITING_FOR_USER, CockpitUserAction.CONFIRM_START, "确认前不会创建"),
        (MissionState.DRAFT, None, False, PmCockpitResumeState.NO_ACTIVE_WORK, _NO_ACTION, "准备阶段"),
        (MissionState.ACTIVE, RunState.READY, False, PmCockpitResumeState.MONITORING, _NO_ACTION, "正在启动"),
        (MissionState.ACTIVE, RunState.PENDING, False, PmCockpitResumeState.NEEDS_REVIEW, _REVIEW, "待核验"),
        (MissionState.ACTIVE, RunState.RUNNING, True, PmCockpitResumeState.MONITORING, _NO_ACTION, "已启动"),
        (MissionState.ACTIVE, RunState.RUNNING, False, PmCockpitResumeState.NEEDS_REVIEW, _REVIEW, "无法证明进程已启动"),
        (MissionState.ACTIVE, RunState.VERIFYING, False, PmCockpitResumeState.NEEDS_REVIEW, _REVIEW, "不会自动重启"),
        (MissionState.ACTIVE, RunState.FAILED, True, PmCockpitResumeState.NEEDS_REVIEW, _REVIEW, "不会自动重试"),
        (MissionState.ACTIVE, RunState.CANCELLED, True, PmCockpitResumeState.NEEDS_REVIEW, _REVIEW, "不会自动重试"),
        (MissionState.ACTIVE, RunState.SUCCEEDED, True, PmCockpitResumeState.MONITORING, _NO_ACTION, "等待执行或验证流转"),
        (MissionState.ACTIVE, None, False, PmCockpitResumeState.MONITORING, _NO_ACTION, "等待执行或验证流转"),
    ],
)
def test_resume_table_gives_only_the_legal_next_step(
    tmp_path: Path,
    mission_state: MissionState,
    run_state: RunState | None,
    started: bool,
    expected_state: PmCockpitResumeState,
    expected_action: CockpitUserAction,
    fragment: str,
) -> None:
    service, mission, work, run = _resume_inputs(tmp_path)
    mission = mission.model_copy(update={"state": mission_state})
    focus_run = run.model_copy(update={"state": run_state}) if run_state else None
    facts = _ProjectFacts(
        missions=(mission,),
        works=(work,),
        runs_by_work={work.work_id: (focus_run,) if focus_run else ()},
        checkpoints=(),
        started_run_ids=frozenset({run.run_id}) if started else frozenset(),
    )

    resume = service._resume(
        mission, work, focus_run, facts, PmCockpitEvidenceCurrency.NOT_APPLICABLE, ""
    )

    assert (resume.state, resume.user_action) == (expected_state, expected_action)
    assert fragment in resume.reason
    assert len(resume.reason) <= 200


def test_resume_never_offers_a_start_or_restart_for_an_unproven_run(tmp_path: Path) -> None:
    service, mission, work, run = _resume_inputs(tmp_path)
    mission = mission.model_copy(update={"state": MissionState.ACTIVE})
    for state in (RunState.RUNNING, RunState.VERIFYING, RunState.FAILED, RunState.PENDING):
        facts = _ProjectFacts(
            missions=(mission,),
            works=(work,),
            runs_by_work={work.work_id: (run.model_copy(update={"state": state}),)},
            checkpoints=(),
            started_run_ids=frozenset(),
        )
        resume = service._resume(
            mission,
            work,
            run.model_copy(update={"state": state}),
            facts,
            PmCockpitEvidenceCurrency.NOT_APPLICABLE,
            "",
        )
        assert resume.user_action is not CockpitUserAction.CONFIRM_START
        assert resume.user_action is CockpitUserAction.REVIEW_ESCALATION


def test_resume_falls_back_to_review_for_an_unknown_mission_state(tmp_path: Path) -> None:
    service, mission, work, run = _resume_inputs(tmp_path)
    unknown = mission.model_copy(update={"state": "UNMAPPED"})
    facts = _ProjectFacts(
        missions=(unknown,),
        works=(work,),
        runs_by_work={work.work_id: (run,)},
        checkpoints=(),
        started_run_ids=frozenset(),
    )

    resume = service._resume(
        unknown, work, run, facts, PmCockpitEvidenceCurrency.NOT_APPLICABLE, ""
    )

    assert resume.state is PmCockpitResumeState.NEEDS_REVIEW
    assert resume.user_action is CockpitUserAction.REVIEW_ESCALATION
    assert "已保留现场" in resume.reason


def test_resume_reason_is_clipped_to_the_contract_limit(tmp_path: Path) -> None:
    service, mission, work, run = _resume_inputs(tmp_path)
    pending = mission.model_copy(update={"state": MissionState.ACCEPTANCE_PENDING})
    facts = _ProjectFacts(
        missions=(pending,),
        works=(work,),
        runs_by_work={work.work_id: (run,)},
        checkpoints=(),
        started_run_ids=frozenset(),
    )

    resume = service._resume(
        pending, work, run, facts, PmCockpitEvidenceCurrency.NOT_CURRENT, "很长的原因" * 80
    )

    assert len(resume.reason) == 200
    assert resume.reason.endswith("…")
    assert resume.reason.startswith("验收证据不能确认：")


def _accepting_cockpit(root: Path) -> tuple[MissionService, PmCockpitService, PmFacadeService]:
    """Build a real, content-bound verified Run and register its project with the cockpit."""
    _registry_for(root, "SW-C04-001")
    missions, facade, _ = _verified_acceptance_ready(root)
    return missions, PmCockpitService(root, store=facade._store), facade


def _pending_acceptance(missions: MissionService, key: str) -> None:
    pending = missions.get("MISSION-C04-001")
    missions.transition(
        mission_id=pending.mission_id,
        expected_version=pending.version,
        new_state=MissionState.ACCEPTANCE_PENDING,
        root_work_id=pending.root_work_id,
        idempotency_key=key,
    )


def test_current_checkpoint_makes_final_acceptance_the_legal_next_step(tmp_path: Path) -> None:
    missions, service, _ = _accepting_cockpit(tmp_path)
    _pending_acceptance(missions, "u05-current")
    events_before = _event_count(tmp_path)
    git_status = _git(tmp_path, "status", "--porcelain").stdout

    evidence = service.evidence("SW-C04-001")

    assert evidence.evidence_currency is PmCockpitEvidenceCurrency.CURRENT
    assert evidence.evidence_currency_reason == ""
    assert evidence.resume.state is PmCockpitResumeState.WAITING_FOR_USER
    assert evidence.resume.user_action is CockpitUserAction.CONFIRM_ACCEPTANCE
    assert (evidence.focus.mission_id, evidence.focus.work_id, evidence.focus.run_id) == (
        "MISSION-C04-001",
        "WORK-C04-001",
        "RUN-C04-001",
    )
    assert [(item.checkpoint_id, item.is_current_run) for item in evidence.checkpoints] == [
        ("CP-C04-001", True)
    ]
    assert _event_count(tmp_path) == events_before
    assert _git(tmp_path, "status", "--porcelain").stdout == git_status
    new_fields = _new_fields_text(evidence)
    assert "lease" not in new_fields.lower()
    assert "token" not in new_fields.lower()
    assert str(tmp_path) not in new_fields


def test_changed_content_makes_the_evidence_not_current_and_requires_review(
    tmp_path: Path,
) -> None:
    missions, service, facade = _accepting_cockpit(tmp_path)
    (tmp_path / "project" / "auto_pm" / "core" / "target.py").write_text(
        "def value() -> int:\n    return 2\n", encoding="utf-8"
    )
    _pending_acceptance(missions, "u05-stale")

    evidence = service.evidence("SW-C04-001")

    assert evidence.evidence_currency is PmCockpitEvidenceCurrency.NOT_CURRENT
    assert evidence.evidence_currency_reason == facade.acceptance_gate_reason("MISSION-C04-001")
    assert evidence.resume.state is PmCockpitResumeState.NEEDS_REVIEW
    assert evidence.resume.user_action is CockpitUserAction.REVIEW_ESCALATION
    assert evidence.resume.reason.startswith("验收证据不能确认：")
    new_fields = _new_fields_text(evidence)
    assert str(tmp_path) not in new_fields
    assert "Traceback" not in new_fields


def test_failed_latest_run_makes_the_evidence_not_current(tmp_path: Path) -> None:
    missions, service, facade = _accepting_cockpit(tmp_path)
    ContinuityExecutionService(tmp_path, store=facade._store).transition_run(
        "RUN-C04-001", RunState.FAILED, "c04-test", "c04-test-lease", "u05-failed"
    )
    _pending_acceptance(missions, "u05-failed-pending")

    evidence = service.evidence("SW-C04-001")

    assert evidence.evidence_currency is PmCockpitEvidenceCurrency.NOT_CURRENT
    assert "Run" in evidence.evidence_currency_reason
    assert evidence.resume.user_action is CockpitUserAction.REVIEW_ESCALATION


def test_evidence_is_not_applicable_before_the_acceptance_gate(tmp_path: Path) -> None:
    _, service, _ = _accepting_cockpit(tmp_path)

    evidence = service.evidence("SW-C04-001")

    assert evidence.evidence_currency is PmCockpitEvidenceCurrency.NOT_APPLICABLE
    assert evidence.evidence_currency_reason == "尚未进入验收阶段，暂无需核验。"
    assert evidence.resume.user_action is not CockpitUserAction.CONFIRM_ACCEPTANCE


def test_verification_failure_gives_a_fixed_reason_without_exception_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missions, service, _ = _accepting_cockpit(tmp_path)
    _pending_acceptance(missions, "u05-unreadable")

    def unreadable(self: PmFacadeService, mission_id: str) -> str:
        raise OSError(f"cannot read {tmp_path} secret-detail")

    monkeypatch.setattr(PmFacadeService, "acceptance_gate_reason", unreadable)

    evidence = service.evidence("SW-C04-001")

    assert evidence.evidence_currency is PmCockpitEvidenceCurrency.NOT_CURRENT
    assert evidence.evidence_currency_reason == "无法核验验收证据：读取失败，未做任何修复。"
    new_fields = _new_fields_text(evidence)
    assert "secret-detail" not in new_fields
    assert str(tmp_path) not in new_fields
    assert evidence.resume.user_action is CockpitUserAction.REVIEW_ESCALATION


def test_unverifying_run_or_missing_checkpoint_makes_the_evidence_not_current(
    tmp_path: Path,
) -> None:
    _registry_for(tmp_path, "SW-TEST-001")
    missions, facade = _setup(tmp_path)
    (tmp_path / ".gitignore").write_text(".auto-pm/\n__pycache__/\n", encoding="utf-8")
    (tmp_path / "pm.py").write_text("VALUE = 1\n", encoding="utf-8")
    facade.plan("MISSION-PM-001")
    facade.approve("MISSION-PM-001", "WORK-PM-001")
    head = _commit_baseline(tmp_path)
    execution = ContinuityExecutionService(tmp_path, store=facade._store)
    execution.start_run(
        run_id="RUN-GATE-001",
        work_id="WORK-PM-001",
        executor_id="gate-test",
        adapter="test",
        owned_paths=["pm.py"],
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head=head,
        worktree_path=str(tmp_path),
        lease_token="gate-lease",
        lease_seconds=900,
        idempotency_key="gate-run-create",
    )
    execution.transition_run(
        "RUN-GATE-001", RunState.RUNNING, "gate-test", "gate-lease", "gate-run-running"
    )
    active = missions.get("MISSION-PM-001")
    missions.transition(
        mission_id=active.mission_id,
        expected_version=active.version,
        new_state=MissionState.ACCEPTANCE_PENDING,
        root_work_id=active.root_work_id,
        idempotency_key="gate-pending",
    )
    service = PmCockpitService(tmp_path, store=facade._store)

    running = service.evidence("SW-TEST-001")
    execution.transition_run(
        "RUN-GATE-001", RunState.VERIFYING, "gate-test", "gate-lease", "gate-run-verifying"
    )
    verifying = service.evidence("SW-TEST-001")

    assert running.evidence_currency is PmCockpitEvidenceCurrency.NOT_CURRENT
    assert "VERIFYING" in running.evidence_currency_reason
    assert verifying.evidence_currency is PmCockpitEvidenceCurrency.NOT_CURRENT
    assert "Checkpoint" in verifying.evidence_currency_reason
    for evidence in (running, verifying):
        assert evidence.resume.user_action is CockpitUserAction.REVIEW_ESCALATION
        assert evidence.focus.run_id == "RUN-GATE-001"


# --- U06: accepted work is only "completed" once the closure service really closed it --------


def _closing_cockpit(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    result: ReconcileDiff | Exception | None = None,
) -> tuple[PmCockpitService, ContinuityStore, Path, _ProjectionReconciler]:
    """An ACCEPTED lineage whose ledger projection is a controllable stand-in."""
    _registry(root)
    store, database = _accepted_lineage(root)
    reconciler = _ProjectionReconciler(ReconcileDiff() if result is None else result)
    closure = PmClosureService(
        root,
        now=lambda: datetime(2026, 9, 20, 12, 10, tzinfo=UTC),
        store=store,
        ledger_reconciler=reconciler,
    )
    monkeypatch.setattr(closure, "inject_prepared_change_substance", lambda _id: root / "CHG.md")
    return PmCockpitService(root, store=store, closure_service=closure), store, database, reconciler


def _all_event_count(database: Path) -> int:
    with closing(sqlite3.connect(database)) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])


def _completed_events(database: Path) -> int:
    with closing(sqlite3.connect(database)) as connection:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='CLOSURE_COMPLETED'"
            ).fetchone()[0]
        )


def test_only_a_closed_mission_is_shown_as_completed(tmp_path: Path) -> None:
    _registry(tmp_path)
    _seed_authorized_mission(tmp_path)
    service = PmCockpitService(tmp_path)
    base = MissionService(tmp_path).get("MISSION-COCKPIT-001")
    expected = {
        MissionState.DRAFT: (PmCockpitCompletionState.NOT_STARTED, ""),
        MissionState.AWAITING_APPROVAL: (PmCockpitCompletionState.NOT_STARTED, ""),
        MissionState.ACTIVE: (PmCockpitCompletionState.NOT_STARTED, ""),
        MissionState.BLOCKED: (PmCockpitCompletionState.NOT_STARTED, ""),
        MissionState.ACCEPTANCE_PENDING: (PmCockpitCompletionState.NOT_STARTED, ""),
        MissionState.ACCEPTED: (PmCockpitCompletionState.PENDING_SYNC, "尚未同步完成"),
        MissionState.CLOSED: (PmCockpitCompletionState.COMPLETED, "已验收并完成"),
        MissionState.CANCELLED: (PmCockpitCompletionState.NOT_STARTED, ""),
    }

    for state, (completion, fragment) in expected.items():
        mission = base.model_copy(update={"state": state})
        got_state, note = service._completion(mission)
        assert got_state is completion, state
        assert fragment in note
        assert (got_state is PmCockpitCompletionState.COMPLETED) == (state is MissionState.CLOSED)
    assert service._completion(None) == (PmCockpitCompletionState.NOT_STARTED, "")
    assert service._milestone(base.model_copy(update={"state": MissionState.ACCEPTED})) == (
        "验收已记录，待同步"
    )
    assert service._next_action(
        base.model_copy(update={"state": MissionState.ACCEPTED}), False
    ) == (CockpitUserAction.RETRY_SYNC, "重试台账同步")
    assert service._next_action(
        base.model_copy(update={"state": MissionState.CLOSED}), False
    )[0] is CockpitUserAction.NONE


def test_snapshot_of_an_accepted_mission_offers_a_sync_retry_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _, database, _ = _closing_cockpit(tmp_path, monkeypatch)
    before = database.read_bytes()

    card = service.snapshot().projects[0]

    assert card.completion_state is PmCockpitCompletionState.PENDING_SYNC
    assert "尚未同步完成" in card.completion_note
    assert card.user_action is CockpitUserAction.RETRY_SYNC
    assert card.next_user_action == "重试台账同步"
    assert card.milestone == "验收已记录，待同步"
    assert card.risk.startswith("中：")
    assert database.read_bytes() == before


def test_close_accepted_closes_run_work_and_mission_only_after_a_clean_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _, database, reconciler = _closing_cockpit(tmp_path, monkeypatch)

    result = service.close_accepted(_CLOSE_MISSION)

    assert result == PmCockpitCompletion(
        mission_id=_CLOSE_MISSION,
        state=PmCockpitCompletionState.COMPLETED,
        message="已完成：变更单与台账已同步。",
    )
    assert _lineage_states(database) == (
        "SUCCEEDED", "CLOSED", "CLOSED", "COMPLETED", 2, "COMPLETED", 1, True
    )
    assert _completed_events(database) == 1
    assert len(reconciler.calls) == 1
    card = service.snapshot().projects[0]
    assert card.completion_state is PmCockpitCompletionState.COMPLETED
    assert card.user_action is CockpitUserAction.NONE
    assert service.evidence("SW-2026-008").resume.state is PmCockpitResumeState.NO_ACTIVE_WORK


@pytest.mark.parametrize(
    "failure",
    [
        OSError("ledger share \\\\server\\secret-path unavailable"),
        ReconcileDiff(missing_in_ledger=["CHG-SCPT-2026-999"]),
    ],
)
def test_projection_failure_stays_pending_sync_with_a_fixed_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: ReconcileDiff | Exception
) -> None:
    service, _, database, _ = _closing_cockpit(tmp_path, monkeypatch, failure)

    result = service.close_accepted(_CLOSE_MISSION)

    assert result.state is PmCockpitCompletionState.PENDING_SYNC
    assert result.message == "台账同步未完成，已保留现场；可稍后重试。"
    assert "secret-path" not in result.model_dump_json()
    assert "CHG-SCPT-2026-999" not in result.model_dump_json()
    assert _lineage_states(database) == (
        "VERIFYING", "IN_PROGRESS", "ACCEPTED", "PREPARED", 1, "PENDING", 0, False
    )
    assert _completed_events(database) == 0
    card = service.snapshot().projects[0]
    assert card.completion_state is PmCockpitCompletionState.PENDING_SYNC


def test_retry_after_a_failed_sync_completes_and_replays_add_no_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _, database, reconciler = _closing_cockpit(
        tmp_path, monkeypatch, OSError("ledger unavailable")
    )
    first = service.close_accepted(_CLOSE_MISSION)
    events_after_failure = _all_event_count(database)
    again = service.close_accepted(_CLOSE_MISSION)
    assert (first.state, again.state) == (
        PmCockpitCompletionState.PENDING_SYNC,
        PmCockpitCompletionState.PENDING_SYNC,
    )
    assert _all_event_count(database) == events_after_failure

    reconciler.result = ReconcileDiff()
    done = service.close_accepted(_CLOSE_MISSION)
    events_after_success = _all_event_count(database)
    replay = service.close_accepted(_CLOSE_MISSION)
    replay_again = service.close_accepted(_CLOSE_MISSION)

    assert done.state is PmCockpitCompletionState.COMPLETED
    assert replay == replay_again == done
    assert _all_event_count(database) == events_after_success
    assert _completed_events(database) == 1
    assert _lineage_states(database)[:3] == ("SUCCEEDED", "CLOSED", "CLOSED")


def test_missing_evidence_refuses_the_closure_and_never_reports_completed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, store, database, reconciler = _closing_cockpit(tmp_path, monkeypatch)
    # The store now judges the lease inside its own write transaction with its own clock, so the lineage's fixed 2026-09-20 clock must be the store's clock too.
    monkeypatch.setattr(store, "_clock", lambda: datetime(2026, 9, 20, 12, 5, tzinfo=UTC))
    ContinuityExecutionService(
        tmp_path, store=store, now=lambda: datetime(2026, 9, 20, 12, 5, tzinfo=UTC)
    ).transition_run(
        _CLOSE_RUN, RunState.FAILED, "c05-test", "closure-secret", "u06-run-failed"
    )
    before = _all_event_count(database)

    result = service.close_accepted(_CLOSE_MISSION)

    assert result.state is PmCockpitCompletionState.PENDING_SYNC
    assert result.message == (
        "收尾失败：必要证据或状态未就绪，这次没有写入。"
        "验收记录已保存；请关闭驾驶舱窗口，由主执行查明原因后重试收口。"
    )
    assert reconciler.calls == []
    assert _all_event_count(database) == before
    assert _completed_events(database) == 0
    with closing(sqlite3.connect(database)) as connection:
        states = connection.execute(
            "SELECT (SELECT state FROM work_items WHERE work_id=?), "
            "(SELECT state FROM mission_items WHERE mission_id=?)",
            (_CLOSE_WORK, _CLOSE_MISSION),
        ).fetchone()
    assert tuple(states) == ("IN_PROGRESS", "ACCEPTED")


def test_work_that_is_not_in_progress_refuses_the_closure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, store, database, _ = _closing_cockpit(tmp_path, monkeypatch)
    WorkRegistryService(tmp_path, store=store).transition(
        _CLOSE_WORK, WorkState.BLOCKED, "u06-work-blocked"
    )
    before = _all_event_count(database)

    result = service.close_accepted(_CLOSE_MISSION)

    assert result.state is PmCockpitCompletionState.PENDING_SYNC
    assert "必要证据或状态未就绪" in result.message
    assert _all_event_count(database) == before
    assert _completed_events(database) == 0


def test_close_accepted_refuses_a_mission_that_is_not_accepted_without_writing(
    tmp_path: Path,
) -> None:
    _registry(tmp_path)
    _seed_authorized_mission(tmp_path)
    service = PmCockpitService(tmp_path)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    before = db_path.read_bytes()

    with pytest.raises(PmCockpitError, match="尚未验收"):
        service.close_accepted("MISSION-COCKPIT-001")
    with pytest.raises(PmCockpitError):
        service.close_accepted("   ")
    with pytest.raises(PmCockpitError):
        service.close_accepted("MISSION-DOES-NOT-EXIST")

    assert db_path.read_bytes() == before


def test_resume_and_currency_treat_an_accepted_mission_as_waiting_for_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _, _, _ = _closing_cockpit(tmp_path, monkeypatch)

    evidence = service.evidence("SW-2026-008")

    assert evidence.resume.state is PmCockpitResumeState.WAITING_FOR_USER
    assert evidence.resume.user_action is CockpitUserAction.RETRY_SYNC
    assert "尚未同步完成" in evidence.resume.reason
    assert evidence.evidence_currency is PmCockpitEvidenceCurrency.NOT_APPLICABLE
    assert evidence.evidence_currency_reason == "验收已记录，验证证据已封存。"
    new_fields = _new_fields_text(evidence).lower()
    assert "lease" not in new_fields and "token" not in new_fields


def test_closure_messages_never_expose_lease_token_or_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _, _, _ = _closing_cockpit(
        tmp_path, monkeypatch, OSError(f"cannot write {tmp_path} closure-secret")
    )

    result = service.close_accepted(_CLOSE_MISSION)

    dumped = result.model_dump_json().lower()
    assert "closure-secret" not in dumped
    assert "token" not in dumped and "lease" not in dumped
    assert str(tmp_path).lower() not in dumped


def _planning_approved(
    mission: Mission,
    *,
    adapters: frozenset[ExecutionAdapterKind] = frozenset({ExecutionAdapterKind.CODEX}),
    model: str = "agent-a",
    mode: WorktreeMode = WorktreeMode.ISOLATED,
) -> Mission:
    """A Mission as materialised from an approved planning card (ISOLATED, model, adapter)."""

    policy = InternalRoutingPolicy(
        allowed_execution_adapters=adapters,
        approved_model=model,
        required_worktree_mode=mode,
        declared_dirty_paths=("auto_pm/core/pm_cockpit_service.py",),
    )
    return mission.model_copy(
        update={"authority": mission.authority.model_copy(update={"routing": policy})}
    )


def test_a_planning_approved_draft_mission_offers_confirm_start(tmp_path: Path) -> None:
    service, mission, work, run = _resume_inputs(tmp_path)
    ready = _planning_approved(mission.model_copy(update={"state": MissionState.DRAFT}))
    facts = _ProjectFacts(
        missions=(ready,),
        works=(work,),
        runs_by_work={work.work_id: ()},
        checkpoints=(),
        started_run_ids=frozenset(),
    )

    resume = service._resume(
        ready, work, None, facts, PmCockpitEvidenceCurrency.NOT_APPLICABLE, ""
    )

    assert (resume.state, resume.user_action) == (
        PmCockpitResumeState.WAITING_FOR_USER,
        CockpitUserAction.CONFIRM_START,
    )
    assert resume.reason == "等待您确认开工；确认前不会创建或启动任何执行。"
    assert PmCockpitService._next_action(ready, False) == (
        CockpitUserAction.CONFIRM_START,
        "确认开始执行",
    )
    assert run.run_id


@pytest.mark.parametrize(
    ("adapters", "model", "mode"),
    [
        (frozenset({ExecutionAdapterKind.CODEX}), "", WorktreeMode.ISOLATED),
        (frozenset({ExecutionAdapterKind.CODEX}), "agent-a", WorktreeMode.CURRENT),
        (frozenset[ExecutionAdapterKind](), "agent-a", WorktreeMode.ISOLATED),
    ],
    ids=["no-model", "not-isolated", "no-adapter"],
)
def test_a_draft_mission_without_a_complete_planning_grant_never_offers_start(
    tmp_path: Path,
    adapters: frozenset[ExecutionAdapterKind],
    model: str,
    mode: WorktreeMode,
) -> None:
    service, mission, work, _ = _resume_inputs(tmp_path)
    draft = _planning_approved(
        mission.model_copy(update={"state": MissionState.DRAFT}),
        adapters=adapters,
        model=model,
        mode=mode,
    )
    facts = _ProjectFacts(
        missions=(draft,),
        works=(work,),
        runs_by_work={work.work_id: ()},
        checkpoints=(),
        started_run_ids=frozenset(),
    )

    resume = service._resume(
        draft, work, None, facts, PmCockpitEvidenceCurrency.NOT_APPLICABLE, ""
    )

    assert (resume.state, resume.user_action) == (
        PmCockpitResumeState.NO_ACTIVE_WORK,
        CockpitUserAction.NONE,
    )
    assert PmCockpitService._next_action(draft, False)[0] is CockpitUserAction.NONE


def test_only_a_draft_mission_is_start_ready_even_with_a_planning_grant(tmp_path: Path) -> None:
    _, mission, _, _ = _resume_inputs(tmp_path)

    for state in (MissionState.ACTIVE, MissionState.ACCEPTANCE_PENDING, MissionState.CLOSED):
        granted = _planning_approved(mission.model_copy(update={"state": state}))
        assert PmCockpitService._is_start_ready(granted) is False


@pytest.mark.parametrize(
    ("mission_state", "message"),
    [
        (MissionState.ACCEPTANCE_PENDING, "该需求已执行并验证，等待验收；请直接确认验收，不要重复执行。"),
        (MissionState.ACCEPTED, "该需求当前不能开始执行。"),
        (MissionState.CLOSED, "该需求当前不能开始执行。"),
        (MissionState.CANCELLED, "该需求当前不能开始执行。"),
    ],
)
def test_start_execution_refuses_a_mission_that_cannot_start_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mission_state: MissionState,
    message: str,
) -> None:
    service, mission, _, _ = _resume_inputs(tmp_path)
    monkeypatch.setattr(
        service._store, "get_mission", lambda _id: mission.model_copy(update={"state": mission_state})
    )
    before = _event_count(tmp_path)

    with pytest.raises(PmCockpitError) as refusal:
        service.start_execution(mission.mission_id)

    assert str(refusal.value) == message
    assert _event_count(tmp_path) == before


def test_start_execution_refuses_blank_unknown_and_unapproved_missions(tmp_path: Path) -> None:
    service, mission, _, _ = _resume_inputs(tmp_path)
    before = _event_count(tmp_path)

    with pytest.raises(PmCockpitError, match="未找到可启动的需求"):
        service.start_execution("   ")
    with pytest.raises(PmCockpitError, match="无法读取该需求"):
        service.start_execution("MISSION-NOT-THERE")
    # A legacy Mission has no planning approval, so there is nothing the Facade may run.
    with pytest.raises(PmCockpitError):
        service.start_execution(mission.mission_id)

    assert _event_count(tmp_path) == before
