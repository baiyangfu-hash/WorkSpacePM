"""Provider-neutral, secret-free contracts for A5 execution dispatch."""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class ExecutionAdapterKind(StrEnum):
    """Locally supported delivery channels; none performs remote I/O by itself."""

    CODEX = "codex"
    TRAE = "trae"
    MANUAL = "manual"


class ExecutionRole(StrEnum):
    """The bounded specialist selected from a registered project stack."""

    FULLSTACK_ENGINEER = "fullstack-engineer"
    PLC_ELECTRICAL_ENGINEER = "plc-electrical-engineer"


class WorktreeMode(StrEnum):
    """Whether a Run keeps a clean controlled tree or receives an isolated one."""

    CURRENT = "CURRENT"
    ISOLATED = "ISOLATED"


class ExecutionStartEvidence(BaseModel):
    """Canonical start evidence emitted by the executor control channel only.

    This is intentionally distinct from ``ExecutionIntent`` and its PREPARED
    receipt: it exists only after the current executor process has emitted the
    canonical ``thread.started`` event.  A later Continuity mapping owns the
    READY-to-RUNNING transition and therefore is not part of this contract.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["execution-start-evidence.v1"] = "execution-start-evidence.v1"
    event_type: Literal["thread.started"] = "thread.started"
    source: Literal["executor-control"] = "executor-control"
    process_id: int = Field(gt=0)
    session_id: str = Field(min_length=1, max_length=255)
    started_at: AwareDatetime

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: str) -> str:
        if value != value.strip() or any(not character.isprintable() for character in value):
            raise ValueError("session_id must be canonical printable text")
        return value


def execution_role_for_stack(stack: str) -> ExecutionRole:
    """Resolve the only two registered execution roles without inferring from chat text."""

    normalized = stack.strip().lower()
    if normalized == "python":
        return ExecutionRole.FULLSTACK_ENGINEER
    if normalized == "plc":
        return ExecutionRole.PLC_ELECTRICAL_ENGINEER
    raise ValueError(f"未登记的执行技术栈: {stack}")


class ExecutionDispatchReceipt(BaseModel):
    """Unstarted execution targets; neither a provider session nor a live process."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["execution-dispatch-receipt.v1"] = "execution-dispatch-receipt.v1"
    status: Literal["PREPARED"] = "PREPARED"
    mission_id: str = Field(min_length=1)
    work_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    subject_project_id: str = Field(min_length=1)
    adapter: ExecutionAdapterKind
    executor_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    role: ExecutionRole
    worktree_mode: WorktreeMode
    worktree_path: str = Field(min_length=1)
    branch_name: str = ""
    git_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    owned_paths: tuple[str, ...]

    @field_validator("executor_id")
    @classmethod
    def _validate_executor_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or ":" in cleaned:
            raise ValueError("executor_id must be non-empty and must not contain ':'")
        return cleaned

    @field_validator("owned_paths")
    @classmethod
    def _validate_owned_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for raw in values:
            path = PurePosixPath(raw)
            if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
                raise ValueError(f"invalid owned path: {raw}")
            value = path.as_posix()
            if value in normalized:
                raise ValueError(f"duplicate owned path: {value}")
            normalized.append(value)
        if not normalized:
            raise ValueError("owned_paths must not be empty")
        return tuple(normalized)

    @model_validator(mode="after")
    def _validate_owner_and_worktree(self) -> Self:
        if self.owner_id != f"{self.adapter.value}:{self.executor_id}":
            raise ValueError("owner_id must be the canonical adapter:executor identity")
        if self.worktree_mode is WorktreeMode.CURRENT and self.branch_name:
            raise ValueError("CURRENT worktree receipts must not declare a branch_name")
        if self.worktree_mode is WorktreeMode.ISOLATED and not self.branch_name:
            raise ValueError("ISOLATED worktree receipts require a branch_name")
        return self


class ExecutionIntent(BaseModel):
    """Immutable Continuity reservation persisted before any dispatch side effect.

    The receipt names the intended Run and worktree. PREPARED never asserts that
    either resource exists or that execution started; recovery must inspect them.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["execution-intent.v1"] = "execution-intent.v1"
    operation_id: str = Field(min_length=1, max_length=255)
    status: Literal["PREPARED"] = "PREPARED"
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt: ExecutionDispatchReceipt
    created_at: AwareDatetime

    @field_validator("operation_id")
    @classmethod
    def _validate_operation_id(cls, value: str) -> str:
        if value != value.strip() or any(not character.isprintable() for character in value):
            raise ValueError("operation_id must be canonical printable text")
        return value


__all__ = [
    "ExecutionAdapterKind",
    "ExecutionDispatchReceipt",
    "ExecutionIntent",
    "ExecutionRole",
    "ExecutionStartEvidence",
    "WorktreeMode",
    "execution_role_for_stack",
]
