"""PmIntent contract tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from auto_pm.contracts.pm_facade import PmIntent


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
