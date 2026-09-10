"""Platform-neutral contracts for one approved business mission."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from auto_pm.contracts.continuity import WorkKind


class RestrictedAction(StrEnum):
    """External or irreversible actions that an envelope can explicitly forbid."""

    EXTERNAL_COMMUNICATION = "EXTERNAL_COMMUNICATION"
    PRODUCTION_DEPLOYMENT = "PRODUCTION_DEPLOYMENT"
    HARDWARE_OR_CONTROLLER_WRITE = "HARDWARE_OR_CONTROLLER_WRITE"
    CREDENTIAL_OR_PERMISSION_CHANGE = "CREDENTIAL_OR_PERMISSION_CHANGE"
    DATA_DELETION = "DATA_DELETION"
    HISTORY_REWRITE = "HISTORY_REWRITE"
    PURCHASE_OR_FINANCIAL_COMMITMENT = "PURCHASE_OR_FINANCIAL_COMMITMENT"


class EscalationTrigger(StrEnum):
    """Conditions that require renewed user authority."""

    SCOPE_EXIT = "SCOPE_EXIT"
    ACCEPTANCE_CRITERIA_CHANGE = "ACCEPTANCE_CRITERIA_CHANGE"
    AUTHORIZATION_CONFLICT = "AUTHORIZATION_CONFLICT"
    AUTHORITY_EXPIRED = "AUTHORITY_EXPIRED"
    PHYSICAL_OR_SAFETY_DECISION = "PHYSICAL_OR_SAFETY_DECISION"
    EXTERNAL_ACTION = "EXTERNAL_ACTION"
    IRREVERSIBLE_ACTION = "IRREVERSIBLE_ACTION"


_ALL_RESTRICTED_ACTIONS = frozenset(RestrictedAction)
_REQUIRED_ESCALATIONS = frozenset(EscalationTrigger)


class MissionState(StrEnum):
    """Lifecycle state of a recoverable business mission."""

    DRAFT = "DRAFT"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    ACCEPTANCE_PENDING = "ACCEPTANCE_PENDING"
    ACCEPTED = "ACCEPTED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


_ROOT_WORK_REQUIRED_STATES = frozenset(
    {
        MissionState.ACTIVE,
        MissionState.BLOCKED,
        MissionState.ACCEPTANCE_PENDING,
        MissionState.ACCEPTED,
        MissionState.CLOSED,
    }
)


class InternalRoutingPolicy(BaseModel):
    """Bounded authority for internal replanning; all capabilities default to denied."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allow_reschedule: bool = False
    allow_execution_branch_changes: bool = False
    allow_business_line_reroute: bool = False
    same_subject_project_only: Literal[True] = True
    within_scope_paths_only: Literal[True] = True


class AuthorityAudit(BaseModel):
    """Immutable approval and provenance fields for an authority envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    created_by: str = Field(min_length=1)
    created_at: AwareDatetime
    approved_by: str = Field(min_length=1)
    approved_at: AwareDatetime
    source_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class AuthorityEnvelope(BaseModel):
    """Explicit authority granted by CHG and Decision records for one subject project."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["authority-envelope.v1"] = "authority-envelope.v1"
    envelope_id: str = Field(min_length=1)
    subject_project_id: str = Field(min_length=1)
    change_id: str = Field(pattern=r"^CHG-[A-Z0-9-]+$")
    decision_id: str = Field(pattern=r"^DEC-[A-Z0-9-]+$")
    authorization_source: Literal["CHG_DECISION"] = "CHG_DECISION"
    scope_paths: tuple[str, ...]
    allowed_child_work_kinds: frozenset[WorkKind] = Field(default_factory=frozenset)
    routing: InternalRoutingPolicy = Field(default_factory=InternalRoutingPolicy)
    forbidden_actions: frozenset[RestrictedAction] = Field(
        default_factory=lambda: _ALL_RESTRICTED_ACTIONS
    )
    escalation_triggers: frozenset[EscalationTrigger] = Field(
        default_factory=lambda: _REQUIRED_ESCALATIONS
    )
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    version: int = Field(default=1, ge=1)
    audit: AuthorityAudit

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

    @model_validator(mode="after")
    def _validate_fail_closed_boundaries(self) -> Self:
        if self.expires_at <= self.valid_from:
            raise ValueError("expires_at must be later than valid_from")
        if not _ALL_RESTRICTED_ACTIONS.issubset(self.forbidden_actions):
            raise ValueError("all external and irreversible actions must remain forbidden")
        if not _REQUIRED_ESCALATIONS.issubset(self.escalation_triggers):
            raise ValueError("all fail-closed escalation triggers are required")
        if (
            self.routing.allow_execution_branch_changes
            or self.routing.allow_business_line_reroute
        ) and not self.allowed_child_work_kinds:
            raise ValueError("branch changes and rerouting require allowed child Work kinds")
        return self


class Mission(BaseModel):
    """One user-approved business objective governed by an authority envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["mission.v1"] = "mission.v1"
    mission_id: str = Field(min_length=1)
    subject_project_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    state: MissionState = MissionState.DRAFT
    root_work_id: str | None = Field(default=None, pattern=r"^WORK-[A-Z0-9-]+$")
    acceptance_criteria: tuple[str, ...]
    authority: AuthorityEnvelope
    version: int = Field(default=1, ge=1)
    created_by: str = Field(min_length=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("acceptance_criteria")
    @classmethod
    def _validate_acceptance_criteria(cls, criteria: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(item.strip() for item in criteria if item.strip())
        if not cleaned or len(cleaned) != len(criteria) or len(set(cleaned)) != len(cleaned):
            raise ValueError("acceptance_criteria must be non-empty, unique, and explicit")
        return cleaned

    @model_validator(mode="after")
    def _match_subject_and_time(self) -> Self:
        if self.subject_project_id != self.authority.subject_project_id:
            raise ValueError("Mission and AuthorityEnvelope subject_project_id must match")
        created_at = datetime.fromisoformat(self.created_at.isoformat())
        updated_at = datetime.fromisoformat(self.updated_at.isoformat())
        if created_at > updated_at:
            raise ValueError("Mission created_at must not be later than updated_at")
        if not (
            self.authority.valid_from
            <= created_at
            <= updated_at
            <= self.authority.expires_at
        ):
            raise ValueError("Mission timestamps must be inside the authority validity window")
        if self.state in _ROOT_WORK_REQUIRED_STATES and self.root_work_id is None:
            raise ValueError("ACTIVE and later non-cancelled Mission states require root_work_id")
        return self
