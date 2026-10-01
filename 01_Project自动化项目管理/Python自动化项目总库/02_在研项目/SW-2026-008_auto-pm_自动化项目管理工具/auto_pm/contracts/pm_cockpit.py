"""Read-only presentation contracts for the user-facing PM cockpit.

The cockpit deliberately projects only decision-ready information.  It is not
an alternate workflow store and it never carries execution lease credentials.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from auto_pm.contracts.execution_adapter import (
    ExecutionActivityStage,
    ExecutionFailureCode,
)


class CockpitUserAction(StrEnum):
    """The small, user-visible action set exposed by the boss cockpit."""

    NONE = "NONE"
    CONFIRM_START = "CONFIRM_START"
    CONFIRM_ACCEPTANCE = "CONFIRM_ACCEPTANCE"
    REVIEW_ESCALATION = "REVIEW_ESCALATION"


class PmCockpitEvidenceCurrency(StrEnum):
    """Whether the newest verification evidence still matches the current content."""

    CURRENT = "CURRENT"
    NOT_CURRENT = "NOT_CURRENT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PmCockpitResumeState(StrEnum):
    """Where a re-opened cockpit finds the selected project's task."""

    NO_ACTIVE_WORK = "NO_ACTIVE_WORK"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    MONITORING = "MONITORING"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class PmCockpitFocus(BaseModel):
    """The one Mission, root Work and Run the cockpit currently points at."""

    model_config = ConfigDict(frozen=True)

    mission_id: str = ""
    work_id: str = ""
    run_id: str = ""
    run_state: str = ""


class PmCockpitResume(BaseModel):
    """The only next step the service considers legal, with a fixed reason."""

    model_config = ConfigDict(frozen=True)

    state: PmCockpitResumeState = PmCockpitResumeState.NO_ACTIVE_WORK
    user_action: CockpitUserAction = CockpitUserAction.NONE
    reason: str = Field(default="", max_length=200)


class PmCockpitProjectCard(BaseModel):
    """One concise project status card containing the nine requested fields."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pm-cockpit-project-card.v1"] = "pm-cockpit-project-card.v1"
    project_id: str = Field(min_length=1)
    project_name: str = Field(min_length=1)
    mission_id: str = ""
    mission: str
    milestone: str
    progress: str
    blocked: bool
    verification: str
    risk: str
    current_owner: str
    next_user_action: str
    user_action: CockpitUserAction = CockpitUserAction.NONE


class PmCockpitWorkNode(BaseModel):
    """A non-secret node in the evidence drawer's Work Graph."""

    model_config = ConfigDict(frozen=True)

    work_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    state: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    runs: tuple[str, ...] = ()


class PmCockpitCheckpointEvidence(BaseModel):
    """Immutable verification evidence safe to show to the final decision maker."""

    model_config = ConfigDict(frozen=True)

    checkpoint_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    evidence: tuple[str, ...]
    created_at: str = Field(min_length=1)
    run_id: str = ""
    is_current_run: bool = False


class PmCockpitEvidence(BaseModel):
    """Bounded provenance for a project card; never includes lease data."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pm-cockpit-evidence.v1"] = "pm-cockpit-evidence.v1"
    project_id: str = Field(min_length=1)
    decision_id: str = ""
    change_id: str = ""
    read_set: tuple[str, ...]
    work_graph: tuple[PmCockpitWorkNode, ...]
    checkpoints: tuple[PmCockpitCheckpointEvidence, ...]
    verification_evidence: tuple[str, ...]
    status_note: str
    focus: PmCockpitFocus = PmCockpitFocus()
    evidence_currency: PmCockpitEvidenceCurrency = PmCockpitEvidenceCurrency.NOT_APPLICABLE
    evidence_currency_reason: str = Field(default="", max_length=200)
    resume: PmCockpitResume = PmCockpitResume()


class PmCockpitActivity(BaseModel):
    """One secret-free canonical activity for the currently selected Mission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["pm-cockpit-activity.v1"] = "pm-cockpit-activity.v1"
    project_id: str = Field(min_length=1)
    mission_id: str = Field(min_length=1)
    work_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    operation_id: str = ""
    stage: ExecutionActivityStage
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    occurred_at: str = Field(min_length=1)
    tone: Literal["default", "success", "warning", "error"] = "default"
    failure_code: ExecutionFailureCode | None = None


class PmCockpitSnapshot(BaseModel):
    """A single immutable response for the safe default cockpit screen."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pm-cockpit-snapshot.v1"] = "pm-cockpit-snapshot.v1"
    projects: tuple[PmCockpitProjectCard, ...]
    activities: tuple[PmCockpitActivity, ...] = ()
    notices: tuple[str, ...] = ()
