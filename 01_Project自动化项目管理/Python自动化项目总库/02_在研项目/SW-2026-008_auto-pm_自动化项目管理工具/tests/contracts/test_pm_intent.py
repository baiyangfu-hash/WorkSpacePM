"""PmIntent contract tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.pm_facade import PlanningDraft, PlanningDraftState, PmIntent


def _intent_data() -> dict[str, object]:
    return {
        "subject_project_id": "SW-2026-008",
        "objective": "Add an immutable PM intent contract.",
        "acceptance_criteria": (
            "The intent validates required fields.",
            "The intent round-trips through JSON.",
        ),
        "request_id": "human-readable-request-01",
    }


def test_pm_intent_json_round_trip_is_frozen() -> None:
    intent = PmIntent.model_validate(_intent_data())

    round_tripped = PmIntent.model_validate_json(intent.model_dump_json())

    assert round_tripped == intent
    assert round_tripped.model_dump(mode="json") == {
        "subject_project_id": "SW-2026-008",
        "objective": "Add an immutable PM intent contract.",
        "acceptance_criteria": [
            "The intent validates required fields.",
            "The intent round-trips through JSON.",
        ],
        "request_id": "human-readable-request-01",
    }
    with pytest.raises(ValidationError, match="frozen"):
        intent.__setattr__("objective", "Changed objective.")


@pytest.mark.parametrize(
    "field",
    ("subject_project_id", "objective", "acceptance_criteria", "request_id"),
)
def test_pm_intent_rejects_missing_required_fields(field: str) -> None:
    values = _intent_data()
    values.pop(field)

    with pytest.raises(ValidationError, match=field):
        PmIntent.model_validate(values)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("subject_project_id", "  "),
        ("objective", "  "),
        ("acceptance_criteria", ()),
        ("acceptance_criteria", ("  ",)),
        ("request_id", "  "),
    ),
)
def test_pm_intent_rejects_blank_required_values(field: str, value: object) -> None:
    values = _intent_data()
    values[field] = value

    with pytest.raises(ValidationError, match=field):
        PmIntent.model_validate(values)


def test_pm_intent_rejects_duplicate_acceptance_criteria_after_trim() -> None:
    values = _intent_data()
    values["acceptance_criteria"] = ("Document the contract.", "  Document the contract.  ")

    with pytest.raises(ValidationError, match="acceptance_criteria"):
        PmIntent.model_validate(values)


def test_planning_draft_is_immutable_and_round_trips_from_intent() -> None:
    intent = PmIntent.model_validate(_intent_data())

    draft = PlanningDraft.from_intent(intent)
    round_tripped = PlanningDraft.model_validate_json(draft.model_dump_json())

    assert round_tripped == draft
    assert draft.state is PlanningDraftState.PRE_AUTH
    assert draft.model_dump(mode="json") == {
        "schema_version": "planning-draft.v1",
        "request_id": "human-readable-request-01",
        "subject_project_id": "SW-2026-008",
        "objective": "Add an immutable PM intent contract.",
        "acceptance_criteria": [
            "The intent validates required fields.",
            "The intent round-trips through JSON.",
        ],
        "input_fingerprint": "e7b8e95ad0b82768a854c017c334a88ac29227a3cf23effda712b489e47f023c",
        "state": "PRE_AUTH",
    }
    with pytest.raises(ValidationError, match="frozen"):
        draft.__setattr__("objective", "Create an executable Mission.")


def test_planning_draft_rejects_tampered_payload_or_execution_state() -> None:
    draft = PlanningDraft.from_intent(PmIntent.model_validate(_intent_data()))

    tampered_payload = draft.model_dump()
    tampered_payload["objective"] = "Create an executable Mission."
    with pytest.raises(ValidationError, match="input_fingerprint"):
        PlanningDraft.model_validate(tampered_payload)

    execution_payload = draft.model_dump()
    execution_payload["state"] = "READY"
    with pytest.raises(ValidationError, match="state"):
        PlanningDraft.model_validate(execution_payload)


def test_planning_draft_has_no_authority_or_execution_identity() -> None:
    draft = PlanningDraft.from_intent(PmIntent.model_validate(_intent_data()))

    serialized = draft.model_dump(mode="json")

    assert set(serialized).isdisjoint(
        {"authority", "change_id", "decision_id", "mission_id", "work_id", "run_id"}
    )
    assert set(PlanningDraftState).isdisjoint(set(MissionState))
