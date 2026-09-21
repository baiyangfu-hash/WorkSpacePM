"""Mission and AuthorityEnvelope contract tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind, WorktreeMode
from auto_pm.contracts.mission import (
    AuthorityAudit,
    AuthorityEnvelope,
    EscalationTrigger,
    InternalRoutingPolicy,
    Mission,
    MissionState,
    RestrictedAction,
)
from auto_pm.contracts.pm_facade import (
    PlanningDraft,
    PlanningExecutionGrant,
    PlanningScopeCard,
    PmIntent,
)

NOW = datetime(2026, 9, 10, 1, 0, tzinfo=UTC)


def _envelope(**overrides: object) -> AuthorityEnvelope:
    values: dict[str, object] = {
        "envelope_id": "AUTH-SW008-001",
        "subject_project_id": "SW-2026-008",
        "change_id": "CHG-SCPT-2026-198",
        "decision_id": "DEC-20260910-5EE749DF",
        "scope_paths": ("auto_pm/contracts/mission.py", "tests/contracts/test_mission.py"),
        "valid_from": NOW,
        "expires_at": NOW + timedelta(days=7),
        "audit": AuthorityAudit(
            created_by="Codex-PM",
            created_at=NOW,
            approved_by="fubai",
            approved_at=NOW,
            source_fingerprint=f"sha256:{'a' * 64}",
        ),
    }
    values.update(overrides)
    return AuthorityEnvelope.model_validate(values)


def _mission(**overrides: object) -> Mission:
    values: dict[str, object] = {
        "mission_id": "MISSION-SW008-001",
        "subject_project_id": "SW-2026-008",
        "title": "Cockpit A0",
        "objective": "Establish a bounded mission contract.",
        "acceptance_criteria": ("Contract rejects undeclared authority.",),
        "authority": _envelope(),
        "created_by": "Codex-PM",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return Mission.model_validate(values)


def test_authority_envelope_defaults_fail_closed() -> None:
    envelope = _envelope()

    assert envelope.allowed_child_work_kinds == frozenset()
    assert envelope.routing == InternalRoutingPolicy()
    assert envelope.forbidden_actions == frozenset(RestrictedAction)
    assert envelope.escalation_triggers == frozenset(EscalationTrigger)
    assert envelope.authorization_source == "CHG_DECISION"
    assert envelope.routing.max_auto_repair_attempts == 0
    assert envelope.routing.max_auto_repair_seconds == 0
    assert envelope.routing.allowed_execution_adapters == frozenset()
    assert envelope.routing.max_parallel_runs == 1
    assert not envelope.routing.auto_repair_enabled
    assert "lease_token" not in envelope.model_dump(mode="json")


def test_planning_scope_card_hash_binds_exact_execution_grant() -> None:
    draft = PlanningDraft.from_intent(
        PmIntent(
            subject_project_id="SW-2026-008",
            objective="Prepare one approved dispatch.",
            acceptance_criteria=("Run remains READY.",),
            request_id="REQ-E08A-001",
        )
    )
    grant = PlanningExecutionGrant(
        adapter=ExecutionAdapterKind.CODEX,
        approved_model="gpt-approved",
        required_worktree_mode=WorktreeMode.ISOLATED,
        declared_dirty_paths=("auto_pm/a.py",),
    )
    card = PlanningScopeCard.from_draft(
        draft,
        change_id="CHG-SCPT-2026-276",
        scope_paths=("auto_pm/a.py",),
        risks=("dispatch drift",),
        non_goals=("no model startup",),
        spec_sources=(("DEV-300", "specs/dev-300.md", "V1"),),
        execution_grant=grant,
    )
    changed = PlanningScopeCard.from_draft(
        draft,
        change_id=card.change_id,
        scope_paths=card.scope_paths,
        risks=card.risks,
        non_goals=card.non_goals,
        spec_sources=card.spec_sources,
        execution_grant=grant.model_copy(update={"approved_model": "gpt-other"}),
    )

    assert card.execution_grant.required_worktree_mode is WorktreeMode.ISOLATED
    assert card.plan_hash != changed.plan_hash
    with pytest.raises(ValidationError, match="Extra inputs"):
        PlanningExecutionGrant.model_validate({**grant.model_dump(), "lease_token": "secret"})


def test_authority_envelope_rejects_unsafe_or_ambiguous_boundaries() -> None:
    with pytest.raises(ValidationError, match="scope_paths"):
        _envelope(scope_paths=("../outside.py",))
    with pytest.raises(ValidationError, match="external and irreversible"):
        _envelope(forbidden_actions=frozenset({RestrictedAction.DATA_DELETION}))
    with pytest.raises(ValidationError, match="escalation triggers"):
        _envelope(escalation_triggers=frozenset({EscalationTrigger.SCOPE_EXIT}))
    with pytest.raises(ValidationError, match="allowed child Work kinds"):
        _envelope(routing=InternalRoutingPolicy(allow_business_line_reroute=True))
    with pytest.raises(ValidationError, match="enabled together"):
        InternalRoutingPolicy(max_auto_repair_attempts=1)
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        InternalRoutingPolicy(max_parallel_runs=0)
    with pytest.raises(ValidationError, match="auto repair requires BUG"):
        _envelope(
            allowed_child_work_kinds=frozenset({WorkKind.TEST}),
            routing=InternalRoutingPolicy(
                max_auto_repair_attempts=1,
                max_auto_repair_seconds=60,
            ),
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        AuthorityEnvelope.model_validate({**_envelope().model_dump(), "lease_token": "secret"})


def test_authority_envelope_allows_only_explicit_internal_routing() -> None:
    envelope = _envelope(
        allowed_child_work_kinds=frozenset(
            {WorkKind.WBS, WorkKind.BUG, WorkKind.DEBT, WorkKind.TEST, WorkKind.GOVERNANCE}
        ),
        routing=InternalRoutingPolicy(
            allow_reschedule=True,
            allow_execution_branch_changes=True,
            allow_business_line_reroute=True,
            allowed_execution_adapters=frozenset(
                {ExecutionAdapterKind.CODEX, ExecutionAdapterKind.TRAE}
            ),
            max_parallel_runs=2,
            max_auto_repair_attempts=2,
            max_auto_repair_seconds=600,
        ),
    )

    assert envelope.routing.same_subject_project_only is True
    assert envelope.routing.within_scope_paths_only is True
    assert envelope.routing.auto_repair_enabled
    assert envelope.routing.allowed_execution_adapters == frozenset(
        {ExecutionAdapterKind.CODEX, ExecutionAdapterKind.TRAE}
    )
    assert envelope.routing.max_parallel_runs == 2
    assert envelope.allowed_child_work_kinds == frozenset(WorkKind)


def test_mission_is_frozen_and_bound_to_envelope_subject_and_validity() -> None:
    mission = _mission()

    assert mission.state == MissionState.DRAFT
    assert mission.root_work_id is None
    assert mission.version == 1
    with pytest.raises(ValidationError, match="frozen"):
        mission.__setattr__("title", "changed")
    with pytest.raises(ValidationError, match="subject_project_id"):
        _mission(subject_project_id="DJ-2026-005")
    with pytest.raises(ValidationError, match="validity window"):
        _mission(created_at=NOW + timedelta(days=8), updated_at=NOW + timedelta(days=8))
    with pytest.raises(ValidationError, match="acceptance_criteria"):
        _mission(acceptance_criteria=())


@pytest.mark.parametrize(
    ("state", "root_work_id"),
    [
        (MissionState.DRAFT, None),
        (MissionState.AWAITING_APPROVAL, None),
        (MissionState.ACTIVE, "WORK-SW008-001"),
        (MissionState.BLOCKED, "WORK-SW008-001"),
        (MissionState.ACCEPTANCE_PENDING, "WORK-SW008-001"),
        (MissionState.ACCEPTED, "WORK-SW008-001"),
        (MissionState.CLOSED, "WORK-SW008-001"),
        (MissionState.CANCELLED, None),
    ],
)
def test_mission_accepts_legal_lifecycle_state(
    state: MissionState, root_work_id: str | None
) -> None:
    mission = _mission(state=state, root_work_id=root_work_id, version=2, updated_at=NOW)

    assert mission.state == state
    assert mission.root_work_id == root_work_id
    assert mission.version == 2


@pytest.mark.parametrize(
    "state",
    sorted(
        state.value
        for state in {
            MissionState.ACTIVE,
            MissionState.BLOCKED,
            MissionState.ACCEPTANCE_PENDING,
            MissionState.ACCEPTED,
            MissionState.CLOSED,
        }
    ),
)
def test_mission_requires_root_work_for_active_and_later_states(state: str) -> None:
    with pytest.raises(ValidationError, match="require root_work_id"):
        _mission(state=state)


def test_mission_rejects_invalid_version_or_timestamp_order() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        _mission(version=0)
    with pytest.raises(ValidationError, match="created_at"):
        _mission(created_at=NOW + timedelta(hours=1), updated_at=NOW)
    with pytest.raises(ValidationError, match="validity window"):
        _mission(updated_at=NOW + timedelta(days=8))
