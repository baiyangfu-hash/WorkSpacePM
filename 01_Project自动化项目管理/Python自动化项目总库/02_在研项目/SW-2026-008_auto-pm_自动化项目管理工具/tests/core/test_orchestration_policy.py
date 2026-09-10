"""Unit tests for the deterministic A3 policy layer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from auto_pm.core.orchestration_policy import OrchestrationPolicy

from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.mission import (
    AuthorityAudit,
    AuthorityEnvelope,
    InternalRoutingPolicy,
    Mission,
    MissionState,
)
from auto_pm.contracts.orchestration import (
    OrchestrationEscalationReason,
    OrchestrationFinding,
)

NOW = datetime(2026, 9, 10, 5, 0, tzinfo=UTC)


def _mission() -> Mission:
    authority = AuthorityEnvelope(
        envelope_id="AUTH-A3-001",
        subject_project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-206",
        decision_id="DEC-20260910-5786E126",
        scope_paths=("auto_pm/",),
        allowed_child_work_kinds=frozenset({WorkKind.BUG, WorkKind.TEST}),
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
    return Mission(
        mission_id="MISSION-A3-001",
        subject_project_id="SW-2026-008",
        title="A3 policy",
        objective="Verify bounded routing.",
        state=MissionState.ACTIVE,
        root_work_id="WORK-A3-ROOT",
        acceptance_criteria=("Only authorized child Work is routed.",),
        authority=authority,
        created_by="Codex PM",
        created_at=NOW,
        updated_at=NOW,
    )


def _finding(**overrides: object) -> OrchestrationFinding:
    values: dict[str, object] = {
        "finding_id": "FND-A3-001",
        "mission_id": "MISSION-A3-001",
        "parent_work_id": "WORK-A3-ROOT",
        "subject_project_id": "SW-2026-008",
        "kind": WorkKind.BUG,
        "title": "A3 defect",
        "summary": "A typed defect finding.",
        "scope_paths": ("auto_pm/core/a.py",),
        "source_fingerprint": f"sha256:{'b' * 64}",
    }
    values.update(overrides)
    return OrchestrationFinding.model_validate(values)


def test_policy_routes_only_authorized_same_project_scope() -> None:
    mission = _mission()

    assert OrchestrationPolicy.finding_escalation(mission, _finding(), NOW) is None
    assert OrchestrationPolicy.blocks_parent(WorkKind.BUG)
    assert OrchestrationPolicy.blocks_parent(WorkKind.TEST)
    assert not OrchestrationPolicy.blocks_parent(WorkKind.DEBT)
    assert (
        OrchestrationPolicy.finding_escalation(
            mission, _finding(scope_paths=("outside.py",)), NOW
        )
        is OrchestrationEscalationReason.SCOPE_EXIT
    )
    assert (
        OrchestrationPolicy.finding_escalation(
            mission, _finding(subject_project_id="DJ-2026-005"), NOW
        )
        is OrchestrationEscalationReason.SUBJECT_PROJECT_EXIT
    )


def test_policy_enforces_explicit_repair_attempt_and_time_budgets() -> None:
    authority = _mission().authority

    assert (
        OrchestrationPolicy.repair_start_escalation(
            authority,
            attempts_used=0,
            elapsed_seconds_used=0,
            current_elapsed_seconds=60,
        )
        is None
    )
    assert (
        OrchestrationPolicy.repair_start_escalation(
            authority,
            attempts_used=2,
            elapsed_seconds_used=0,
            current_elapsed_seconds=1,
        )
        is OrchestrationEscalationReason.REPAIR_BUDGET_EXHAUSTED
    )
    assert (
        OrchestrationPolicy.retry_escalation(authority, attempt_count=2)
        is OrchestrationEscalationReason.REPAIR_BUDGET_EXHAUSTED
    )
