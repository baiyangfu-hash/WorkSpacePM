"""Typed, deterministic contracts for bounded Mission orchestration."""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from auto_pm.contracts.continuity import WorkKind


class OrchestrationAction(StrEnum):
    """One append-only result emitted by the bounded orchestration engine."""

    ROUTED = "ROUTED"
    BLOCKING = "BLOCKING"
    ESCALATED = "ESCALATED"
    REPAIR_ALLOWED = "REPAIR_ALLOWED"
    REPAIR_COMPLETED = "REPAIR_COMPLETED"
    REPAIR_EXHAUSTED = "REPAIR_EXHAUSTED"


class OrchestrationEscalationReason(StrEnum):
    """Fail-closed reasons that require renewed PM or user authority."""

    AUTHORITY_EXPIRED = "AUTHORITY_EXPIRED"
    SUBJECT_PROJECT_EXIT = "SUBJECT_PROJECT_EXIT"
    SCOPE_EXIT = "SCOPE_EXIT"
    UNAUTHORIZED_WORK_KIND = "UNAUTHORIZED_WORK_KIND"
    BUSINESS_LINE_REROUTE = "BUSINESS_LINE_REROUTE"
    EXECUTION_BRANCH_CHANGE = "EXECUTION_BRANCH_CHANGE"
    PHYSICAL_OR_SAFETY_DECISION = "PHYSICAL_OR_SAFETY_DECISION"
    EXTERNAL_ACTION = "EXTERNAL_ACTION"
    PARENT_NOT_ATTACHED = "PARENT_NOT_ATTACHED"
    DECISION_SCOPE_EXIT = "DECISION_SCOPE_EXIT"
    REPAIR_BUDGET_DISABLED = "REPAIR_BUDGET_DISABLED"
    REPAIR_BUDGET_EXHAUSTED = "REPAIR_BUDGET_EXHAUSTED"


class OrchestrationFinding(BaseModel):
    """A typed executor or gate finding; natural-language inference is out of scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["orchestration-finding.v1"] = "orchestration-finding.v1"
    finding_id: str = Field(pattern=r"^FND-[A-Z0-9-]+$")
    mission_id: str = Field(pattern=r"^MISSION-[A-Z0-9-]+$")
    parent_work_id: str = Field(pattern=r"^WORK-[A-Z0-9-]+$")
    subject_project_id: str = Field(min_length=1)
    kind: WorkKind
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    scope_paths: tuple[str, ...]
    source_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    requires_business_line_reroute: bool = False
    requires_execution_branch_change: bool = False
    requires_physical_or_safety_decision: bool = False
    requires_external_action: bool = False

    @field_validator("scope_paths")
    @classmethod
    def _validate_scope_paths(cls, paths: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for raw in paths:
            if "\\" in raw:
                raise ValueError("scope_paths must use platform-neutral forward slashes")
            path = PurePosixPath(raw)
            if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
                raise ValueError(f"invalid scope path: {raw}")
            value = path.as_posix()
            if value in normalized:
                raise ValueError(f"duplicate scope path: {value}")
            normalized.append(value)
        if not normalized:
            raise ValueError("scope_paths must not be empty")
        return tuple(normalized)


class RepairAttempt(BaseModel):
    """An already-observed repair attempt reported by a future execution adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["repair-attempt.v1"] = "repair-attempt.v1"
    attempt_id: str = Field(pattern=r"^ATT-[A-Z0-9-]+$")
    mission_id: str = Field(pattern=r"^MISSION-[A-Z0-9-]+$")
    child_work_id: str = Field(pattern=r"^WORK-[A-Z0-9-]+$")
    succeeded: bool
    elapsed_seconds: int = Field(ge=0)


class OrchestrationOutcome(BaseModel):
    """A replayable engine result that future PM views can project without inference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["orchestration-outcome.v1"] = "orchestration-outcome.v1"
    mission_id: str = Field(pattern=r"^MISSION-[A-Z0-9-]+$")
    action: OrchestrationAction
    correlation_id: str = Field(min_length=1)
    child_work_id: str = ""
    parent_work_id: str = ""
    blocks_parent: bool = False
    user_attention_required: bool = False
    escalation_reason: OrchestrationEscalationReason | None = None
    attempt_count: int = Field(default=0, ge=0)
    cumulative_elapsed_seconds: int = Field(default=0, ge=0)
    next_legal_action: str = ""
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _validate_escalation_shape(self) -> OrchestrationOutcome:
        is_escalation = self.action in {
            OrchestrationAction.ESCALATED,
            OrchestrationAction.REPAIR_EXHAUSTED,
        }
        if is_escalation and (
            not self.user_attention_required or self.escalation_reason is None
        ):
            raise ValueError("escalation outcomes require attention and a reason")
        if not is_escalation and self.escalation_reason is not None:
            raise ValueError("non-escalation outcomes must not carry an escalation reason")
        return self
