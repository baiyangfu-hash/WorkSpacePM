"""Compact, provider-neutral context returned to an AI PM at session start."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from auto_pm.contracts.project_fact_snapshot import FileFingerprint


class ResumeHandoff(BaseModel):
    """The smallest actionable projection of an execution request."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    status: str
    lifecycle_state: str
    executor_skill: str
    summary: str


class ResumeBudget(BaseModel):
    """A bounded retrieval budget rather than an unenforceable prompt request."""

    model_config = ConfigDict(frozen=True)

    max_output_bytes: int = Field(default=12_288, ge=1)
    max_evidence_files: int = Field(default=3, ge=1)
    suggested_max_tool_calls: int = Field(default=5, ge=1)


class PmResumeContext(BaseModel):
    """Versioned context compiler output for a PM cold start."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pm-resume.v1"] = "pm-resume.v1"
    evidence_id: str
    collected_at: datetime
    subject_project_id: str
    control_project_id: str
    fact_evidence_id: str
    git_head: str
    git_clean: bool
    control_pm_session: FileFingerprint
    active_change_numbers: list[str] = Field(default_factory=list)
    current_focus: str = ""
    active_wbs: list[str] = Field(default_factory=list)
    active_handoffs: list[ResumeHandoff] = Field(default_factory=list)
    next_legal_action: str
    read_set: list[str] = Field(default_factory=list)
    expansion_triggers: list[str] = Field(default_factory=list)
    budget: ResumeBudget = Field(default_factory=ResumeBudget)
