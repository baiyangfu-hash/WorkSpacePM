"""Prepare bounded local execution packages without creating a parallel ledger."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.core.workspace_context_service import WorkspaceContextError, WorkspaceContextService
from auto_pm.core.worktree_policy_service import (
    WorktreePlan,
    WorktreePolicyError,
    WorktreePolicyService,
)

from auto_pm.contracts.execution_adapter import (
    ExecutionAdapterKind,
    ExecutionDispatchReceipt,
    ExecutionIntent,
    ExecutionRole,
    execution_role_for_stack,
)
from auto_pm.contracts.mission import Mission
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


class ExecutionDispatchError(RuntimeError):
    """Raised when a provider package would exceed the Mission's explicit authority."""


@dataclass(frozen=True)
class LeaseCapability:
    """An in-process capability; it is intentionally absent from public receipts."""

    owner_id: str
    token: str = field(repr=False)


@dataclass(frozen=True)
class ExecutionDispatchResult:
    """Keep the safe receipt separate from the one-time lease capability."""

    receipt: ExecutionDispatchReceipt
    intent: ExecutionIntent
    lease: LeaseCapability = field(repr=False)


@dataclass(frozen=True)
class _LocalExecutionAdapter:
    """Build a local, honest receipt and never call a provider or external service."""

    kind: ExecutionAdapterKind

    def prepare_receipt(
        self,
        *,
        mission: Mission,
        work_id: str,
        run_id: str,
        owned_paths: tuple[str, ...],
        executor_id: str,
        role: ExecutionRole,
        plan: WorktreePlan,
    ) -> ExecutionDispatchReceipt:
        return ExecutionDispatchReceipt(
            mission_id=mission.mission_id,
            work_id=work_id,
            run_id=run_id,
            subject_project_id=mission.subject_project_id,
            adapter=self.kind,
            executor_id=executor_id,
            owner_id=f"{self.kind.value}:{executor_id}",
            role=role,
            worktree_mode=plan.worktree_mode,
            worktree_path=str(plan.worktree_path),
            branch_name=plan.branch_name,
            git_head=plan.git_head,
            owned_paths=owned_paths,
        )


class ExecutionAdapterRegistry:
    """A closed local registry; adapter selection never imports legacy skills."""

    def __init__(self) -> None:
        self._adapters = {
            kind: _LocalExecutionAdapter(kind)
            for kind in ExecutionAdapterKind
        }

    def resolve(self, adapter: ExecutionAdapterKind) -> _LocalExecutionAdapter:
        try:
            return self._adapters[adapter]
        except KeyError as error:
            raise ExecutionDispatchError(f"未登记的执行适配器: {adapter}") from error


class ExecutionDispatchService:
    """Bind a Mission, Work, Git baseline, and local adapter into one recoverable Run."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        store: ContinuityStore | None = None,
        worktrees: WorktreePolicyService | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._root = Path(workspace_root).resolve()
        self._store = store or ContinuityStore(self._root)
        self._now = now or (lambda: datetime.now(UTC))
        self._execution = ContinuityExecutionService(self._root, self._store, self._now)
        self._worktrees = worktrees or WorktreePolicyService(self._root)
        self._adapters = ExecutionAdapterRegistry()

    def prepare(
        self,
        *,
        mission: Mission,
        work_id: str,
        run_id: str,
        adapter: ExecutionAdapterKind | str,
        executor_id: str,
        lease_token: str,
        lease_seconds: int,
        idempotency_key: str,
        operation_id: str | None = None,
        stack: str | None = None,
        force_isolation: bool = False,
    ) -> ExecutionDispatchResult:
        """Persist an intent before allocating a local worktree and Run lease.

        Replays return the original unstarted intent without repeating side effects,
        including after a crash between reservation and Run creation. Reconciliation
        and real provider startup belong to the subsequent supervision phase.
        Legacy callers use idempotency_key as their operation_id.
        """

        now = self._utc_now()
        kind = self._adapter_kind(adapter)
        owner_id = self._owner_id(kind, executor_id)
        self._assert_lease_request(lease_token, lease_seconds)
        role = execution_role_for_stack(stack or self._project_stack(mission.subject_project_id))
        operation = operation_id if operation_id is not None else idempotency_key
        request_sha256 = self._request_fingerprint(
            {
                "mission": mission.model_dump(mode="python"),
                "work_id": work_id,
                "run_id": run_id,
                "adapter": kind,
                "executor_id": executor_id,
                "lease_token": lease_token,
                "lease_seconds": lease_seconds,
                "role": role,
                "force_isolation": force_isolation,
            }
        )
        try:
            self._worktrees.require_control_root()
            if self._store.workspace_root != self._root:
                raise ExecutionDispatchError("ExecutionIntent Store 与控制工作树不一致")
            existing = self._store.get_execution_intent(operation)
            if existing is not None:
                return self._existing_result(existing, request_sha256, lease_token)
            work = self._store.get_work(work_id)
        except (ContinuityStoreError, WorktreePolicyError) as error:
            raise ExecutionDispatchError(str(error)) from error
        self._assert_authority(mission, now)
        self._assert_adapter_authorized(mission, kind)
        if work.subject_project_id != mission.subject_project_id:
            raise ExecutionDispatchError("Work 与 Mission subject project 不一致")
        if not self._paths_covered(work.scope_paths, mission.authority.scope_paths):
            raise ExecutionDispatchError("Work scope 超出 Mission AuthorityEnvelope")
        if work.authorization_ref != mission.authority.decision_id:
            raise ExecutionDispatchError("Work 与 Mission Decision 不一致")
        self._assert_parallel_capacity(mission, run_id, now)
        try:
            plan = self._worktrees.select(
                run_id=run_id,
                allow_branch_creation=mission.authority.routing.allow_execution_branch_changes,
                force_isolation=force_isolation,
            )
        except WorktreePolicyError as error:
            # A competing caller may have committed and materialized while select
            # sampled Git. Re-read the durable reservation before reporting failure.
            try:
                existing = self._store.get_execution_intent(operation)
            except ContinuityStoreError as store_error:
                raise ExecutionDispatchError(str(store_error)) from store_error
            if existing is not None:
                return self._existing_result(existing, request_sha256, lease_token)
            raise ExecutionDispatchError(str(error)) from error
        receipt = self._adapters.resolve(kind).prepare_receipt(
            mission=mission,
            work_id=work_id,
            run_id=run_id,
            owned_paths=work.scope_paths,
            executor_id=executor_id,
            role=role,
            plan=plan,
        )
        intent = ExecutionIntent(
            operation_id=operation,
            request_sha256=request_sha256,
            receipt=receipt,
            created_at=now,
        )
        try:
            intent, created = self._store.reserve_execution_intent(intent)
            if not created:
                return self._existing_result(intent, request_sha256, lease_token)
            # reserve_execution_intent returns only after the transaction commits.
            # No worktree, Run, or provider may be created before this boundary.
            plan = self._worktrees.materialize(plan)
            # E03B deliberately leaves this lease-bound Run in READY.  Only trusted
            # executor-control evidence may later move it to RUNNING.
            self._execution.start_run(
                run_id=run_id,
                work_id=work_id,
                executor_id=owner_id,
                adapter=kind.value,
                owned_paths=list(work.scope_paths),
                declared_dirty_paths=[],
                observed_dirty_paths=[],
                git_head=plan.git_head,
                worktree_path=str(plan.worktree_path),
                lease_token=lease_token,
                lease_seconds=lease_seconds,
                idempotency_key=f"execution-run:{hashlib.sha256(operation.encode('utf-8')).hexdigest()}",
            )
        except (ContinuityStoreError, ContinuityExecutionError, WorktreePolicyError) as error:
            raise ExecutionDispatchError(str(error)) from error
        return ExecutionDispatchResult(
            receipt=intent.receipt,
            intent=intent,
            lease=LeaseCapability(owner_id, lease_token),
        )

    @staticmethod
    def _existing_result(
        intent: ExecutionIntent,
        request_sha256: str,
        lease_token: str,
    ) -> ExecutionDispatchResult:
        if intent.request_sha256 != request_sha256:
            raise ExecutionDispatchError("operation_id 已绑定不同载荷")
        return ExecutionDispatchResult(
            receipt=intent.receipt,
            intent=intent,
            lease=LeaseCapability(intent.receipt.owner_id, lease_token),
        )

    @staticmethod
    def _assert_lease_request(lease_token: str, lease_seconds: int) -> None:
        if (
            not isinstance(lease_token, str)
            or not lease_token
            or lease_token != lease_token.strip()
            or any(not character.isprintable() for character in lease_token)
        ):
            raise ExecutionDispatchError("lease_token 必须是 canonical 非空可打印文本")
        if type(lease_seconds) is not int or not 60 <= lease_seconds <= 86400:
            raise ExecutionDispatchError("lease_seconds 必须在 60 到 86400 之间")

    @staticmethod
    def _request_fingerprint(payload: dict[str, object]) -> str:
        """Include immutable authority and every caller-controlled dispatch input."""
        def encode(value: object) -> object:
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, (set, frozenset)):
                return sorted(value)
            raise TypeError(f"Unsupported dispatch value: {type(value).__name__}")

        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=encode
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _assert_parallel_capacity(self, mission: Mission, run_id: str, now: datetime) -> None:
        active = 0
        try:
            for work in self._store.list_works(mission.subject_project_id):
                for run in self._store.list_runs(work.work_id):
                    if run.run_id == run_id:
                        continue
                    lease = self._store.get_lease(run.run_id)
                    if datetime.fromisoformat(lease.expires_at) > now:
                        active += 1
        except ContinuityStoreError as error:
            raise ExecutionDispatchError(str(error)) from error
        if active >= mission.authority.routing.max_parallel_runs:
            raise ExecutionDispatchError("Mission 已达到 max_parallel_runs，拒绝隐式并发执行")

    @staticmethod
    def _adapter_kind(adapter: ExecutionAdapterKind | str) -> ExecutionAdapterKind:
        try:
            return ExecutionAdapterKind(adapter)
        except ValueError as error:
            raise ExecutionDispatchError(f"未登记的执行适配器: {adapter}") from error

    @staticmethod
    def _owner_id(adapter: ExecutionAdapterKind, executor_id: str) -> str:
        cleaned = executor_id.strip()
        if not cleaned or ":" in cleaned:
            raise ExecutionDispatchError("executor_id 必须非空且不得包含 ':'")
        return f"{adapter.value}:{cleaned}"

    @staticmethod
    def _paths_covered(paths: tuple[str, ...], roots: tuple[str, ...]) -> bool:
        return all(
            any(path == root or path.startswith(f"{root.rstrip('/')}/") for root in roots)
            for path in paths
        )

    @staticmethod
    def _assert_adapter_authorized(mission: Mission, adapter: ExecutionAdapterKind) -> None:
        if adapter not in mission.authority.routing.allowed_execution_adapters:
            raise ExecutionDispatchError("该执行适配器未获 AuthorityEnvelope 授权")

    @staticmethod
    def _assert_authority(mission: Mission, now: datetime) -> None:
        authority = mission.authority
        if now < authority.valid_from or now > authority.expires_at:
            raise ExecutionDispatchError("AuthorityEnvelope 不在有效期内")

    def _project_stack(self, project_id: str) -> str:
        try:
            context = WorkspaceContextService(str(self._root)).resolve(project_id=project_id)
        except WorkspaceContextError as error:
            raise ExecutionDispatchError(str(error)) from error
        stack = context.subject.stack
        if not isinstance(stack, str) or not stack.strip():
            raise ExecutionDispatchError("项目技术栈缺失或无效")
        return stack

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise ExecutionDispatchError("now 必须是带时区时间")
        return value.astimezone(UTC)


__all__ = [
    "ExecutionAdapterRegistry",
    "ExecutionDispatchError",
    "ExecutionDispatchResult",
    "ExecutionDispatchService",
    "LeaseCapability",
]
