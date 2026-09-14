"""Stable, user-facing cards emitted by the PM Facade."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

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


class PlanningDraftState(StrEnum):
    """A pre-authorization plan is deliberately outside Mission execution states."""

    PRE_AUTH = "PRE_AUTH"


class PlanningDraft(BaseModel):
    """Immutable, non-executable plan derived from a validated user intent.

    A PlanningDraft is intentionally not a Mission: it has no AuthorityEnvelope,
    CHG, Decision, Work, Run, or execution state. P03 persists this request-keyed
    contract; only P08 may materialize an authorized Mission.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["planning-draft.v1"] = "planning-draft.v1"
    request_id: str
    subject_project_id: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    input_fingerprint: str
    state: Literal[PlanningDraftState.PRE_AUTH] = PlanningDraftState.PRE_AUTH

    @classmethod
    def from_intent(cls, intent: PmIntent) -> PlanningDraft:
        """Build the only valid pre-authorization representation of an intent."""

        return cls(
            request_id=intent.request_id,
            subject_project_id=intent.subject_project_id,
            objective=intent.objective,
            acceptance_criteria=intent.acceptance_criteria,
            input_fingerprint=cls.fingerprint_for(intent),
        )

    @staticmethod
    def fingerprint_for(intent: PmIntent) -> str:
        """Return a canonical content hash used by P03 replay protection."""

        payload = json.dumps(
            intent.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def _validate_intent_fingerprint(self) -> PlanningDraft:
        intent = PmIntent(
            request_id=self.request_id,
            subject_project_id=self.subject_project_id,
            objective=self.objective,
            acceptance_criteria=self.acceptance_criteria,
        )
        if self.input_fingerprint != self.fingerprint_for(intent):
            raise ValueError("input_fingerprint must match the immutable intent payload")
        return self


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
