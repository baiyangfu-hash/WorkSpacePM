"""Stable, user-facing cards emitted by the PM Facade."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from auto_pm.contracts.mission import MissionState


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
