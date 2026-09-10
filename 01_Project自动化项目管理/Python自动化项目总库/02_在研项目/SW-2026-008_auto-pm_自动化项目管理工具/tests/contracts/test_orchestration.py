"""Contract tests for deterministic A3 orchestration inputs and results."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.orchestration import (
    OrchestrationAction,
    OrchestrationEscalationReason,
    OrchestrationFinding,
    OrchestrationOutcome,
)

NOW = datetime(2026, 9, 10, 4, 0, tzinfo=UTC)


def _finding(**overrides: object) -> OrchestrationFinding:
    values: dict[str, object] = {
        "finding_id": "FND-A3-001",
        "mission_id": "MISSION-A3-001",
        "parent_work_id": "WORK-A3-ROOT",
        "subject_project_id": "SW-2026-008",
        "kind": WorkKind.BUG,
        "title": "Gate failure",
        "summary": "A typed test gate reported a failure.",
        "scope_paths": ("auto_pm/core/example.py",),
        "source_fingerprint": f"sha256:{'a' * 64}",
    }
    values.update(overrides)
    return OrchestrationFinding.model_validate(values)


def test_finding_is_typed_and_path_bounded() -> None:
    finding = _finding()

    assert finding.kind is WorkKind.BUG
    with pytest.raises(ValidationError, match="scope_paths"):
        _finding(scope_paths=("../outside.py",))
    with pytest.raises(ValidationError, match="forward slashes"):
        _finding(scope_paths=("auto_pm\\example.py",))


def test_escalation_outcome_requires_explicit_user_attention() -> None:
    with pytest.raises(ValidationError, match="require attention"):
        OrchestrationOutcome(
            mission_id="MISSION-A3-001",
            action=OrchestrationAction.ESCALATED,
            correlation_id="FND-A3-001",
            created_at=NOW,
        )

    outcome = OrchestrationOutcome(
        mission_id="MISSION-A3-001",
        action=OrchestrationAction.ESCALATED,
        correlation_id="FND-A3-001",
        user_attention_required=True,
        escalation_reason=OrchestrationEscalationReason.SCOPE_EXIT,
        created_at=NOW,
    )

    assert outcome.escalation_reason is OrchestrationEscalationReason.SCOPE_EXIT
