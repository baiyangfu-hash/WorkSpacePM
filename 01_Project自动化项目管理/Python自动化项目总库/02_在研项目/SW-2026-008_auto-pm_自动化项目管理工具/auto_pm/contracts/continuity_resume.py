"""Provider-neutral Resume v2 contract compiled from bounded sources of truth."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from auto_pm.contracts.continuity import CheckpointItem, RunItem, WorkItem
from auto_pm.contracts.continuity_query import ContinuityQuery, plain_payload, validation_summary
from auto_pm.contracts.intake import IntakeSummary
from auto_pm.contracts.mission import Mission
from auto_pm.contracts.workspace_context import WorkspaceContext


class LeaseView(BaseModel):
    """Read-only lease metadata without the execution capability token."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["lease-view.v1"] = "lease-view.v1"
    run_id: str
    owner_id: str
    expires_at: str
    version: int
    updated_at: str


class ResumeRunCandidate(BaseModel):
    """A nonterminal Run with token-free lease metadata for safe disambiguation."""

    model_config = ConfigDict(frozen=True)

    run: RunItem
    lease: LeaseView


class ContinuityResume(BaseModel):
    """Identity plus an optional, unambiguous execution chain."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["continuity-resume.v2"] = "continuity-resume.v2"
    context: WorkspaceContext
    mission: Mission | None = None
    work: WorkItem | None = None
    work_candidates: tuple[WorkItem, ...] = ()
    # TD-071: the other open cards (parked or waiting) when the project holds more than one.
    mission_candidates: tuple[Mission, ...] = ()
    run: RunItem | None = None
    run_candidates: tuple[ResumeRunCandidate, ...] = ()
    checkpoint: CheckpointItem | None = None
    lease: LeaseView | None = None
    conflicts: tuple[str, ...] = ()
    next_legal_action: str = ""
    read_set: tuple[str, ...] = ()
    intake: IntakeSummary = Field(default_factory=IntakeSummary)
    evidence_id: str
    query: ContinuityQuery | None = None


def validate_query_resume(value: object, *, require_query: bool) -> ContinuityResume:
    """Re-validate a Resume v2 taken from outside, query block included.

    A query block that is present must be complete and carry both versions (an empty block or a missing version is refused, never read as the old format). Only the
    historical read of a Resume without any query block passes ``require_query=False``; every modern entry (pm resume, pm orient, the SDK) passes ``True``.
    """

    try:
        resume = ContinuityResume.model_validate(plain_payload(value))
    except ValidationError as error:
        raise ValueError(f"连续性查询未通过校验: {validation_summary(error)}") from error
    if require_query and resume.query is None:
        raise ValueError("连续性查询缺少 query 块；现代入口不接受旧格式的 Resume")
    return resume
