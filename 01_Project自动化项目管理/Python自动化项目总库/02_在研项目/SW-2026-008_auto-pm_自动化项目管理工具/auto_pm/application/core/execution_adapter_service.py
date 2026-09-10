"""Prepare bounded local execution packages without creating a parallel ledger."""

from __future__ import annotations

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

from auto_pm.contracts.continuity import RunItem
from auto_pm.contracts.execution_adapter import (
    ExecutionAdapterKind,
    ExecutionDispatchReceipt,
    ExecutionRole,
    WorktreeMode,
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
    lease: LeaseCapability = field(repr=False)


@dataclass(frozen=True)
class _LocalExecutionAdapter:
    """Build a local, honest receipt and never call a provider or external service."""

    kind: ExecutionAdapterKind

    def prepare_receipt(
        self,
        *,
        mission: Mission,
        run: RunItem,
        executor_id: str,
        role: ExecutionRole,
        plan: WorktreePlan,
    ) -> ExecutionDispatchReceipt:
        return ExecutionDispatchReceipt(
            mission_id=mission.mission_id,
            work_id=run.work_id,
            run_id=run.run_id,
            subject_project_id=mission.subject_project_id,
            adapter=self.kind,
            executor_id=executor_id,
            owner_id=f"{self.kind.value}:{executor_id}",
            role=role,
            worktree_mode=plan.worktree_mode,
            worktree_path=str(plan.worktree_path),
            branch_name=plan.branch_name,
            git_head=run.git_head,
            owned_paths=run.owned_paths,
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
        stack: str | None = None,
        force_isolation: bool = False,
    ) -> ExecutionDispatchResult:
        """Allocate a local Run and a secret-free receipt after all fail-closed checks.

        ``PREPARED`` means only that a local execution package and Run lease exist.
        It never claims that Codex, Trae, or a human received or started remote work.
        """

        now = self._utc_now()
        kind = self._adapter_kind(adapter)
        self._assert_authority(mission, now)
        self._assert_adapter_authorized(mission, kind)
        owner_id = self._owner_id(kind, executor_id)
        try:
            work = self._store.get_work(work_id)
        except ContinuityStoreError as error:
            raise ExecutionDispatchError(str(error)) from error
        if work.subject_project_id != mission.subject_project_id:
            raise ExecutionDispatchError("Work 与 Mission subject project 不一致")
        if not self._paths_covered(work.scope_paths, mission.authority.scope_paths):
            raise ExecutionDispatchError("Work scope 超出 Mission AuthorityEnvelope")
        role = execution_role_for_stack(stack or self._project_stack(mission.subject_project_id))
        existing = self._existing_run(work_id, run_id)
        if existing is not None:
            return self._existing_result(existing, mission, kind, executor_id, lease_token, role)
        self._assert_parallel_capacity(mission, run_id, now)
        try:
            plan = self._worktrees.select(
                run_id=run_id,
                allow_branch_creation=mission.authority.routing.allow_execution_branch_changes,
                force_isolation=force_isolation,
            )
            plan = self._worktrees.materialize(plan)
            run = self._execution.start_run(
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
                idempotency_key=idempotency_key,
            )
        except (ContinuityExecutionError, WorktreePolicyError) as error:
            raise ExecutionDispatchError(str(error)) from error
        receipt = self._adapters.resolve(kind).prepare_receipt(
            mission=mission,
            run=run,
            executor_id=executor_id,
            role=role,
            plan=plan,
        )
        return ExecutionDispatchResult(receipt=receipt, lease=LeaseCapability(owner_id, lease_token))

    def _existing_result(
        self,
        run: RunItem,
        mission: Mission,
        adapter: ExecutionAdapterKind,
        executor_id: str,
        lease_token: str,
        role: ExecutionRole,
    ) -> ExecutionDispatchResult:
        owner_id = self._owner_id(adapter, executor_id)
        if run.adapter != adapter.value or run.executor_id != owner_id:
            raise ExecutionDispatchError("run_id 已绑定其他执行适配器或 owner")
        try:
            lease = self._store.get_lease(run.run_id)
        except ContinuityStoreError as error:
            raise ExecutionDispatchError(str(error)) from error
        if lease.owner_id != owner_id or lease.lease_token != lease_token:
            raise ExecutionDispatchError("run_id 已存在，但 lease capability 不匹配")
        worktree_path = Path(run.worktree_path).resolve()
        mode = WorktreeMode.CURRENT if worktree_path == self._root else WorktreeMode.ISOLATED
        try:
            branch_name = "" if mode is WorktreeMode.CURRENT else self._worktrees.branch_name_for(worktree_path)
            plan = WorktreePlan(mode, worktree_path, run.git_head, branch_name, ())
        except WorktreePolicyError as error:
            raise ExecutionDispatchError(str(error)) from error
        receipt = self._adapters.resolve(adapter).prepare_receipt(
            mission=mission,
            run=run,
            executor_id=executor_id,
            role=role,
            plan=plan,
        )
        return ExecutionDispatchResult(receipt=receipt, lease=LeaseCapability(owner_id, lease_token))

    def _existing_run(self, work_id: str, run_id: str) -> RunItem | None:
        try:
            return next(
                (item for item in self._store.list_runs(work_id, include_terminal=True) if item.run_id == run_id),
                None,
            )
        except ContinuityStoreError as error:
            raise ExecutionDispatchError(str(error)) from error

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
