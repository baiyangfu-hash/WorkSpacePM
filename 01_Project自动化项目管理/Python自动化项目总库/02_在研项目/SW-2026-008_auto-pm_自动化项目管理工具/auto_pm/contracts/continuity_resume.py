"""Provider-neutral Resume v2 contract compiled from bounded sources of truth."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from auto_pm.contracts.continuity import CheckpointItem, LeaseItem, RunItem, WorkItem
from auto_pm.contracts.workspace_context import WorkspaceContext


class ContinuityResume(BaseModel):
    """Identity plus an optional, unambiguous execution chain."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["continuity-resume.v2"] = "continuity-resume.v2"
    context: WorkspaceContext
    work: WorkItem | None = None
    run: RunItem | None = None
    checkpoint: CheckpointItem | None = None
    lease: LeaseItem | None = None
    conflicts: tuple[str, ...] = ()
    next_legal_action: str = ""
    read_set: tuple[str, ...] = ()
    evidence_id: str
