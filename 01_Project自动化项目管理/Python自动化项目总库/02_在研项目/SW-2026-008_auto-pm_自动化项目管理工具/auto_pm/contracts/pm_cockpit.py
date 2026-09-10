"""Read-only presentation contracts for the user-facing PM cockpit.

The cockpit deliberately projects only decision-ready information.  It is not
an alternate workflow store and it never carries execution lease credentials.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CockpitUserAction(StrEnum):
    """The small, user-visible action set exposed by the boss cockpit."""

    NONE = "NONE"
    CONFIRM_START = "CONFIRM_START"
    CONFIRM_ACCEPTANCE = "CONFIRM_ACCEPTANCE"
    REVIEW_ESCALATION = "REVIEW_ESCALATION"


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


class PmCockpitSnapshot(BaseModel):
    """A single immutable response for the safe default cockpit screen."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pm-cockpit-snapshot.v1"] = "pm-cockpit-snapshot.v1"
    projects: tuple[PmCockpitProjectCard, ...]
    notices: tuple[str, ...] = ()
