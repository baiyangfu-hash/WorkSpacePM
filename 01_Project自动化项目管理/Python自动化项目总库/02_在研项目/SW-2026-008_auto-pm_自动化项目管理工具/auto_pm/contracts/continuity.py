"""Platform-neutral continuity contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class WorkState(StrEnum):
    PLANNED = "PLANNED"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    VERIFYING = "VERIFYING"
    ACCEPTED = "ACCEPTED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class WorkKind(StrEnum):
    WBS = "WBS"
    BUG = "BUG"
    DEBT = "DEBT"
    TEST = "TEST"
    GOVERNANCE = "GOVERNANCE"


class WorkItem(BaseModel):
    """One independently authorized logical unit of work."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "work.v1"
    work_id: str
    subject_project_id: str
    kind: WorkKind
    title: str
    state: WorkState
    owner: str
    read_only: bool
    authorization_ref: str
    scope_paths: tuple[str, ...]
    scope_hash: str
    source_fingerprint: str
    version: int
    created_at: str
    updated_at: str
