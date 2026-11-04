"""Platform-neutral continuity contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

# 租约默认秒数的唯一来源：CLI 选项与服务默认值都引用它，避免 900/1800 两套口径。
DEFAULT_LEASE_SECONDS = 1800


class WorkState(StrEnum):
    PLANNED = "PLANNED"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    VERIFYING = "VERIFYING"
    ACCEPTED = "ACCEPTED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


EXECUTION_ACTIVE_WORK_STATES: frozenset[WorkState] = frozenset(
    {
        WorkState.PLANNED,
        WorkState.READY,
        WorkState.IN_PROGRESS,
        WorkState.BLOCKED,
        WorkState.VERIFYING,
    }
)
POST_ACCEPTANCE_WORK_STATES: frozenset[WorkState] = frozenset({WorkState.ACCEPTED})
TERMINAL_WORK_STATES: frozenset[WorkState] = frozenset(
    {WorkState.CLOSED, WorkState.CANCELLED}
)


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
    PENDING = "PENDING"
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


class LeaseHoldReceipt(BaseModel):
    """Public proof of one Run's current total-hold deadline (after a user extension or a status read)."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["lease-hold-receipt.v1"] = "lease-hold-receipt.v1"
    run_id: str
    hold_end: str


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
