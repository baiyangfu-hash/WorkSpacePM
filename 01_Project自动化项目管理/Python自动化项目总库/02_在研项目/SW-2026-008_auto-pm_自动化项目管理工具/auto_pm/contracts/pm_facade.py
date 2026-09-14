"""Stable, user-facing cards emitted by the PM Facade."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from auto_pm.contracts.mission import MissionState


class PmIntent(BaseModel):
    """Immutable, serializable user intent submitted to the PM Facade."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_project_id: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    request_id: str

    @field_validator("subject_project_id", "objective", "request_id")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("required intent text must not be blank")
        return cleaned

    @field_validator("acceptance_criteria")
    @classmethod
    def _validate_acceptance_criteria(cls, criteria: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(item.strip() for item in criteria)
        if not cleaned or any(not item for item in cleaned) or len(set(cleaned)) != len(cleaned):
            raise ValueError("acceptance_criteria must be non-empty, unique, and explicit")
        return cleaned


class PmConfirmationKind(StrEnum):
    """The only two human confirmation moments plus the safe execution handoff."""

    APPROVAL = "APPROVAL"
    EXECUTION = "EXECUTION"
    ACCEPTANCE = "ACCEPTANCE"


class PmConfirmationCard(BaseModel):
    """A bounded presentation model; it never owns workflow state."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pm-confirmation-card.v1"] = "pm-confirmation-card.v1"
    kind: PmConfirmationKind
    mission_id: str
    title: str
    mission_state: MissionState
    summary: str
    acceptance_criteria: tuple[str, ...]
    next_actions: tuple[str, ...]
