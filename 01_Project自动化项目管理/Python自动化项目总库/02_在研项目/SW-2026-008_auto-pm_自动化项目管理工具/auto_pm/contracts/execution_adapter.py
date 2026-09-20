"""Provider-neutral, secret-free contracts for A5 execution dispatch."""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

_SECRET_ASSIGNMENT = re.compile(
    r"\b(?:openai[\s_-]*api[\s_-]*key|api[\s_-]*key|access[\s_-]*token|"
    r"refresh[\s_-]*token|token|password|passwd|pwd)\b\s*(?:=|:)\s*"
    r"[\"']?[^\s,;\"']+",
    re.IGNORECASE,
)
_BEARER_SECRET = re.compile(r"\bbearer\s+[^\s,;]+", re.IGNORECASE)
_OPENAI_SECRET = re.compile(r"\bsk-(?:proj-|svcacct-)?[a-z0-9_-]{8,}\b", re.IGNORECASE)


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
    declared_dirty_paths: tuple[str, ...]

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

    @field_validator("declared_dirty_paths")
    @classmethod
    def _validate_declared_dirty_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for raw in values:
            if "\\" in raw:
                raise ValueError("declared_dirty_paths must use forward slashes")
            path = PurePosixPath(raw)
            if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
                raise ValueError(f"invalid declared dirty path: {raw}")
            value = path.as_posix()
            if value in normalized:
                raise ValueError(f"duplicate declared dirty path: {value}")
            normalized.append(value)
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


class ExecutionMicrotaskFile(BaseModel):
    """One regular baseline blob copied into a standalone microtask repository."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    git_mode: Literal["100644", "100755"]
    blob_oid: str = Field(pattern=r"^[0-9a-f]{40}$")
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        if "\\" in value:
            raise ValueError("microtask paths must use forward slashes")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
            raise ValueError("microtask path must be workspace-relative")
        normalized = path.as_posix()
        if normalized in {".codex-microtask.json", ".git"} or normalized.startswith(".git/"):
            raise ValueError("microtask path is reserved")
        return normalized


class ExecutionMicrotaskPlan(BaseModel):
    """Append-only reservation that must commit before repository materialization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["execution-microtask-plan.v1"] = "execution-microtask-plan.v1"
    operation_id: str = Field(min_length=1, max_length=255)
    mission_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    approved_model: str = Field(min_length=1, max_length=255)
    objective: str = Field(min_length=1, max_length=8192)
    owned_paths: tuple[str, ...]
    declared_dirty_paths: tuple[str, ...]
    source_worktree_path: str = Field(min_length=1)
    baseline_git_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    repository_path: str = Field(min_length=1)
    manifest: tuple[ExecutionMicrotaskFile, ...]
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    marker_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: AwareDatetime

    @field_validator("operation_id")
    @classmethod
    def _validate_operation_id(cls, value: str) -> str:
        if value != value.strip() or any(not character.isprintable() for character in value):
            raise ValueError("operation_id must be canonical printable text")
        return value

    @field_validator("approved_model")
    @classmethod
    def _validate_approved_model(cls, value: str) -> str:
        if value != value.strip() or any(not character.isprintable() for character in value):
            raise ValueError("approved_model must be canonical printable text")
        return value

    @field_validator("objective")
    @classmethod
    def _validate_secret_safe_objective(cls, value: str) -> str:
        if value != value.strip() or any(not character.isprintable() for character in value):
            raise ValueError("objective must be canonical printable text")
        if any(
            pattern.search(value)
            for pattern in (_SECRET_ASSIGNMENT, _BEARER_SECRET, _OPENAI_SECRET)
        ):
            raise ValueError("objective contains a secret-shaped credential")
        return value

    @field_validator("owned_paths", "declared_dirty_paths")
    @classmethod
    def _validate_bound_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for raw in values:
            if "\\" in raw:
                raise ValueError("bound paths must use forward slashes")
            path = PurePosixPath(raw)
            if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
                raise ValueError(f"invalid bound path: {raw}")
            value = path.as_posix()
            if value in normalized:
                raise ValueError(f"duplicate bound path: {value}")
            normalized.append(value)
        if not normalized:
            raise ValueError("bound paths must not be empty")
        return tuple(normalized)

    @field_validator("manifest")
    @classmethod
    def _validate_manifest(
        cls, values: tuple[ExecutionMicrotaskFile, ...]
    ) -> tuple[ExecutionMicrotaskFile, ...]:
        paths = tuple(item.path for item in values)
        if not paths or paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise ValueError("microtask manifest must be non-empty, unique, and sorted")
        return values

    @model_validator(mode="after")
    def _validate_content_hashes(self) -> Self:
        manifest = [item.model_dump(mode="json") for item in self.manifest]
        if self.manifest_sha256 != self._hash(manifest):
            raise ValueError("manifest_sha256 must bind the exact canonical manifest")
        request = {
            "operation_id": self.operation_id,
            "mission_id": self.mission_id,
            "run_id": self.run_id,
            "approved_model": self.approved_model,
            "objective": self.objective,
            "owned_paths": list(self.owned_paths),
            "declared_dirty_paths": list(self.declared_dirty_paths),
            "source_worktree_path": self.source_worktree_path,
            "baseline_git_head": self.baseline_git_head,
            "repository_path": self.repository_path,
            "manifest": manifest,
            "manifest_sha256": self.manifest_sha256,
        }
        if self.request_sha256 != self._hash(request):
            raise ValueError("request_sha256 must bind the exact microtask request")
        marker = {
            "schema_version": "codex-microtask.v1",
            **request,
            "request_sha256": self.request_sha256,
        }
        if self.marker_sha256 != self._hash(marker):
            raise ValueError("marker_sha256 must bind the exact marker")
        return self

    @staticmethod
    def _hash(payload: object) -> str:
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


class ExecutionMicrotaskMaterialization(BaseModel):
    """Secret-free proof of one committed, unstarted standalone microtask repository."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["execution-microtask-materialization.v1"] = (
        "execution-microtask-materialization.v1"
    )
    status: Literal["PREPARED"] = "PREPARED"
    plan: ExecutionMicrotaskPlan
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")


class ExecutionStartClaim(BaseModel):
    """Secret-free, append-only winner proof created before local process start."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["execution-start-claim.v1"] = "execution-start-claim.v1"
    operation_id: str = Field(min_length=1, max_length=255)
    run_id: str = Field(min_length=1)
    expected_run_version: int = Field(ge=1)
    owner_id: str = Field(min_length=1)
    plan_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    marker_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    repository_path: str = Field(min_length=1)
    microtask_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    claim_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    claimed_at: AwareDatetime

    @model_validator(mode="after")
    def _validate_claim_hash(self) -> Self:
        request = {
            "operation_id": self.operation_id,
            "run_id": self.run_id,
            "expected_run_version": self.expected_run_version,
            "owner_id": self.owner_id,
            "plan_request_sha256": self.plan_request_sha256,
            "marker_sha256": self.marker_sha256,
            "repository_path": self.repository_path,
            "microtask_commit": self.microtask_commit,
        }
        if self.claim_sha256 != ExecutionMicrotaskPlan._hash(request):
            raise ValueError("claim_sha256 must bind the exact execution start claim")
        return self


class ExecutionProjectionFile(BaseModel):
    """One approved file copied from the microtask repository to its candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    baseline_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    projected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return ExecutionMicrotaskFile._validate_path(value)


class ExecutionProjectionReceipt(BaseModel):
    """Append-only, secret-free proof of an approved candidate projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["execution-projection-receipt.v1"] = (
        "execution-projection-receipt.v1"
    )
    operation_id: str = Field(min_length=1, max_length=255)
    run_id: str = Field(min_length=1)
    source_repository: str = Field(min_length=1)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    target_worktree: str = Field(min_length=1)
    baseline_git_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    files: tuple[ExecutionProjectionFile, ...]
    projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _validate_projection_hash(self) -> Self:
        paths = tuple(item.path for item in self.files)
        if not paths or paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise ValueError("projection files must be non-empty, unique, and sorted")
        request = {
            "operation_id": self.operation_id,
            "run_id": self.run_id,
            "source_repository": self.source_repository,
            "source_commit": self.source_commit,
            "target_worktree": self.target_worktree,
            "baseline_git_head": self.baseline_git_head,
            "files": [item.model_dump(mode="json") for item in self.files],
        }
        if self.projection_sha256 != ExecutionMicrotaskPlan._hash(request):
            raise ValueError("projection_sha256 must bind the exact projection receipt")
        return self


class ForegroundExecutionReceipt(BaseModel):
    """Bounded public result for one foreground local execution Saga."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["foreground-execution-receipt.v1"] = (
        "foreground-execution-receipt.v1"
    )
    operation_id: str = Field(min_length=1, max_length=255)
    run_id: str = Field(min_length=1)
    status: Literal["VERIFYING", "FAILED", "PENDING"]
    claim_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    process_id: int | None = Field(default=None, gt=0)
    session_id: str | None = None
    exit_code: int | None = None
    projection_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        if self.status == "VERIFYING" and (
            self.process_id is None
            or not self.session_id
            or self.exit_code != 0
            or self.projection_sha256 is None
        ):
            raise ValueError("VERIFYING requires start, zero exit, and projection proof")
        if self.status == "PENDING" and (
            self.process_id is not None
            or self.session_id is not None
            or self.exit_code is not None
            or self.projection_sha256 is not None
        ):
            raise ValueError("PENDING cannot claim process or projection evidence")
        return self


__all__ = [
    "ExecutionAdapterKind",
    "ExecutionDispatchReceipt",
    "ExecutionIntent",
    "ExecutionMicrotaskFile",
    "ExecutionMicrotaskMaterialization",
    "ExecutionMicrotaskPlan",
    "ExecutionProjectionFile",
    "ExecutionProjectionReceipt",
    "ExecutionRole",
    "ExecutionStartClaim",
    "ExecutionStartEvidence",
    "ForegroundExecutionReceipt",
    "WorktreeMode",
    "execution_role_for_stack",
]
