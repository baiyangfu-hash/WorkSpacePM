"""End-to-end application tests for the A3 Mission orchestration engine."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from auto_pm.core.mission_orchestrator import MissionOrchestrator
from auto_pm.core.mission_service import MissionService
from auto_pm.core.work_registry_service import WorkRegistryService

from auto_pm.contracts.continuity import WorkKind, WorkState
from auto_pm.contracts.mission import (
    AuthorityAudit,
    AuthorityEnvelope,
    InternalRoutingPolicy,
    MissionState,
)
from auto_pm.contracts.orchestration import (
    OrchestrationAction,
    OrchestrationEscalationReason,
    OrchestrationFinding,
    RepairAttempt,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore

NOW = datetime(2026, 9, 10, 6, 0, tzinfo=UTC)
MISSION_ID = "MISSION-A3-001"
ROOT_WORK_ID = "WORK-A3-ROOT"
DECISION_ID = "DEC-20260910-5786E126"


def _decision(root: Path, files: list[str]) -> None:
    path = root / ".auto-pm" / "decisions" / f"{DECISION_ID}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "decision_package.v1",
                "decision_id": DECISION_ID,
                "project_id": "SW-2026-008",
                "change_id": "CHG-SCPT-2026-206",
                "approved_scope": "SYSTEM",
                "approved_files": files,
                "approver": "fubai",
                "approved_at": NOW.isoformat(),
                "decision_conclusion": "approved",
            }
        ),
        encoding="utf-8",
    )


def _setup(
    root: Path,
    *,
    now: datetime = NOW,
    decision_files: list[str] | None = None,
) -> MissionOrchestrator:
    files = decision_files or ["auto_pm/root.py", "auto_pm/bug.py", "auto_pm/debt.py"]
    _decision(root, files)
    works = WorkRegistryService(root, now=lambda: NOW.isoformat())
    works.initialize("test")
    works.create_work(
        work_id=ROOT_WORK_ID,
        subject_project_id="SW-2026-008",
        kind=WorkKind.WBS,
        title="A3 root",
        owner="Codex",
        scope_paths=["auto_pm/root.py"],
        source_fingerprint="sha256:root",
        idempotency_key="root-create",
    )
    works.authorize(ROOT_WORK_ID, DECISION_ID, "root-authorize")
    works.transition(ROOT_WORK_ID, WorkState.IN_PROGRESS, "root-start")

    missions = MissionService(root, now=lambda: NOW)
    missions.initialize("test")
    authority = AuthorityEnvelope(
        envelope_id="AUTH-A3-001",
        subject_project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-206",
        decision_id=DECISION_ID,
        scope_paths=("auto_pm",),
        allowed_child_work_kinds=frozenset(
            {WorkKind.BUG, WorkKind.DEBT, WorkKind.TEST, WorkKind.GOVERNANCE}
        ),
        routing=InternalRoutingPolicy(
            max_auto_repair_attempts=2,
            max_auto_repair_seconds=300,
        ),
        valid_from=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=1),
        audit=AuthorityAudit(
            created_by="Codex PM",
            created_at=NOW,
            approved_by="fubai",
            approved_at=NOW,
            source_fingerprint=f"sha256:{'a' * 64}",
        ),
    )
    created = missions.create(
        mission_id=MISSION_ID,
        subject_project_id="SW-2026-008",
        title="A3 engine",
        objective="Route typed findings without user task distribution.",
        acceptance_criteria=["Only authorized work is automatically routed."],
        authority=authority,
        created_by="Codex PM",
        idempotency_key="mission-create",
    )
    awaiting = missions.transition(
        mission_id=created.mission_id,
        expected_version=created.version,
        new_state=MissionState.AWAITING_APPROVAL,
        root_work_id=None,
        idempotency_key="mission-submit",
    )
    missions.transition(
        mission_id=awaiting.mission_id,
        expected_version=awaiting.version,
        new_state=MissionState.ACTIVE,
        root_work_id=ROOT_WORK_ID,
        idempotency_key="mission-activate",
    )
    engine = MissionOrchestrator(root, now=lambda: now)
    engine.initialize("test")
    return engine


def _finding(
    *,
    finding_id: str = "FND-A3-BUG-001",
    kind: WorkKind = WorkKind.BUG,
    scope_path: str = "auto_pm/bug.py",
) -> OrchestrationFinding:
    return OrchestrationFinding(
        finding_id=finding_id,
        mission_id=MISSION_ID,
        parent_work_id=ROOT_WORK_ID,
        subject_project_id="SW-2026-008",
        kind=kind,
        title=f"{kind.value} finding",
        summary="Typed gate output.",
        scope_paths=(scope_path,),
        source_fingerprint=f"sha256:{'b' * 64}",
    )


def test_bug_finding_creates_idempotent_child_and_blocks_parent(tmp_path: Path) -> None:
    engine = _setup(tmp_path)

    first = engine.report_finding(_finding())
    second = engine.report_finding(_finding())
    store = ContinuityStore(tmp_path)

    assert first == second
    assert first.action is OrchestrationAction.BLOCKING
    assert first.blocks_parent
    assert first.child_work_id == "WORK-A3-A3-BUG-001"
    assert store.get_work(ROOT_WORK_ID).state is WorkState.BLOCKED
    assert store.get_work(first.child_work_id).state is WorkState.READY
    assert len(store.list_work_relations()) == 3
    assert len(store.list_orchestration_outcomes(MISSION_ID)) == 1
    assert store.get_mission(MISSION_ID).state is MissionState.ACTIVE


def test_debt_finding_is_routed_without_falsely_blocking_delivery(tmp_path: Path) -> None:
    engine = _setup(tmp_path)

    outcome = engine.report_finding(
        _finding(finding_id="FND-A3-DEBT-001", kind=WorkKind.DEBT, scope_path="auto_pm/debt.py")
    )

    assert outcome.action is OrchestrationAction.ROUTED
    assert not outcome.blocks_parent
    assert ContinuityStore(tmp_path).get_work(ROOT_WORK_ID).state is WorkState.IN_PROGRESS


def test_scope_exit_blocks_mission_and_records_a_user_escalation(tmp_path: Path) -> None:
    engine = _setup(tmp_path)

    outcome = engine.report_finding(_finding(scope_path="outside.py"))
    store = ContinuityStore(tmp_path)

    assert outcome.action is OrchestrationAction.ESCALATED
    assert outcome.user_attention_required
    assert outcome.escalation_reason is OrchestrationEscalationReason.SCOPE_EXIT
    assert store.get_mission(MISSION_ID).state is MissionState.BLOCKED


def test_decision_file_exit_does_not_create_an_unauthorized_partial_child(tmp_path: Path) -> None:
    engine = _setup(tmp_path, decision_files=["auto_pm/root.py"])

    outcome = engine.report_finding(_finding())

    assert outcome.escalation_reason is OrchestrationEscalationReason.DECISION_SCOPE_EXIT
    assert len(ContinuityStore(tmp_path).list_works("SW-2026-008")) == 1


def test_repair_budget_allows_one_retry_then_blocks_for_user_attention(tmp_path: Path) -> None:
    engine = _setup(tmp_path)
    child = engine.report_finding(_finding()).child_work_id

    first = engine.report_repair_attempt(
        RepairAttempt(
            attempt_id="ATT-A3-001",
            mission_id=MISSION_ID,
            child_work_id=child,
            succeeded=False,
            elapsed_seconds=10,
        )
    )
    second = engine.report_repair_attempt(
        RepairAttempt(
            attempt_id="ATT-A3-002",
            mission_id=MISSION_ID,
            child_work_id=child,
            succeeded=False,
            elapsed_seconds=10,
        )
    )

    assert first.action is OrchestrationAction.REPAIR_ALLOWED
    assert first.attempt_count == 1
    assert second.action is OrchestrationAction.REPAIR_EXHAUSTED
    assert second.escalation_reason is OrchestrationEscalationReason.REPAIR_BUDGET_EXHAUSTED
    assert ContinuityStore(tmp_path).get_mission(MISSION_ID).state is MissionState.BLOCKED


def test_expired_authority_can_only_escalate_to_the_safe_blocked_state(tmp_path: Path) -> None:
    engine = _setup(tmp_path, now=NOW + timedelta(days=1))

    outcome = engine.report_finding(_finding())

    assert outcome.escalation_reason is OrchestrationEscalationReason.AUTHORITY_EXPIRED
    assert ContinuityStore(tmp_path).get_mission(MISSION_ID).state is MissionState.BLOCKED
