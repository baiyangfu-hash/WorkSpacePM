"""Platform-neutral continuity contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

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


class RunState(StrEnum):
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


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


class RunItem(BaseModel):
    """One execution attempt for an authorized Work item."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["run.v1"] = "run.v1"
    run_id: str
    work_id: str
    state: RunState
    executor_id: str
    adapter: str
    owned_paths: tuple[str, ...]
    declared_dirty_paths: tuple[str, ...]
    git_head: str
    worktree_path: str
    version: int
    created_at: str
    updated_at: str


class CheckpointItem(BaseModel):
    """Immutable, evidence-bearing recovery point for a Run."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["checkpoint.v1"] = "checkpoint.v1"
    checkpoint_id: str
    run_id: str
    sequence: int
    summary: str
    git_head: str
    dirty_paths: tuple[str, ...]
    evidence: tuple[str, ...]
    created_at: str


class LeaseItem(BaseModel):
    """Exclusive, expiring ownership of one Run."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["lease.v1"] = "lease.v1"
    run_id: str
    owner_id: str
    lease_token: str
    expires_at: str
    version: int
    updated_at: str


class LeaseRenewalReceipt(BaseModel):
    """Public, secret-free proof that one lease renewal committed."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["lease-renewal-receipt.v1"] = "lease-renewal-receipt.v1"
    run_id: str
    owner_id: str
    expires_at: str
    version: int
    updated_at: str


class HandoffV2(BaseModel):
    """Signed snapshot that points to transactional continuity state."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["handoff.v2"] = "handoff.v2"
    handoff_id: str
    work_id: str
    run_id: str
    checkpoint_id: str
    from_owner: str
    to_owner: str
    owned_paths: tuple[str, ...]
    git_head: str
    worktree_path: str
    lease_expires_at: str
    snapshot_hash: str
    created_at: str
