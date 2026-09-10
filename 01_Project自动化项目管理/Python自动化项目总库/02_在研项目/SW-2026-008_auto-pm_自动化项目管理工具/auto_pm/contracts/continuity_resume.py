"""Provider-neutral Resume v2 contract compiled from bounded sources of truth."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from auto_pm.contracts.continuity import CheckpointItem, RunItem, WorkItem
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


class ContinuityResume(BaseModel):
    """Identity plus an optional, unambiguous execution chain."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["continuity-resume.v2"] = "continuity-resume.v2"
    context: WorkspaceContext
    mission: Mission | None = None
    work: WorkItem | None = None
    run: RunItem | None = None
    checkpoint: CheckpointItem | None = None
    lease: LeaseView | None = None
    conflicts: tuple[str, ...] = ()
    next_legal_action: str = ""
    read_set: tuple[str, ...] = ()
    evidence_id: str
