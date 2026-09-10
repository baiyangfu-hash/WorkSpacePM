"""Run, checkpoint, lease, and handoff orchestration for continuity v2."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

from auto_pm.contracts.continuity import CheckpointItem, HandoffV2, LeaseItem, RunItem, RunState
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


class ContinuityExecutionError(RuntimeError):
    """Raised when execution continuity would become ambiguous or unsafe."""


_RUN_TRANSITIONS = {
    RunState.READY: {RunState.RUNNING, RunState.CANCELLED},
    RunState.RUNNING: {RunState.BLOCKED, RunState.VERIFYING, RunState.FAILED},
    RunState.BLOCKED: {RunState.RUNNING, RunState.CANCELLED},
    RunState.VERIFYING: {RunState.RUNNING, RunState.SUCCEEDED, RunState.FAILED},
    RunState.SUCCEEDED: set(),
    RunState.FAILED: set(),
    RunState.CANCELLED: set(),
}


class ContinuityExecutionService:
    """Maintain one recoverable execution chain without using adapter state as truth."""

    def __init__(
        self,
        workspace_root: str | Path,
        store: ContinuityStore | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._root = Path(workspace_root).resolve()
        self._store = store or ContinuityStore(self._root)
        self._now = now or (lambda: datetime.now(UTC))

    def start_run(
        self,
        *,
        run_id: str,
        work_id: str,
        executor_id: str,
        adapter: str,
        owned_paths: list[str],
        declared_dirty_paths: list[str],
        observed_dirty_paths: list[str],
        git_head: str,
        worktree_path: str,
        lease_token: str,
        lease_seconds: int,
        idempotency_key: str,
    ) -> RunItem:
        now = self._utc_now()
        if not all(value.strip() for value in (run_id, work_id, executor_id, adapter, git_head)):
            raise ContinuityExecutionError("Run 身份、Work、executor、adapter 与 Git HEAD 不能为空")
        if not lease_token.strip():
            raise ContinuityExecutionError("lease_token 不能为空")
        if lease_seconds < 60 or lease_seconds > 86_400:
            raise ContinuityExecutionError("lease_seconds 必须在 60 到 86400 之间")
        owned = self._normalize_paths(owned_paths)
        declared = self._normalize_paths(declared_dirty_paths, allow_empty=True)
        observed = self._normalize_paths(observed_dirty_paths, allow_empty=True)
        if not self._paths_covered(observed, declared):
            raise ContinuityExecutionError("存在未声明的 dirty path")
        try:
            work = self._store.get_work(work_id)
            if work.state.value not in {"READY", "IN_PROGRESS"}:
                raise ContinuityExecutionError("只有 READY/IN_PROGRESS Work 可以创建 Run")
            if not self._paths_covered(owned, work.scope_paths):
                raise ContinuityExecutionError("owned_paths 超出 Work scope")
            if not self._paths_covered(declared, owned):
                raise ContinuityExecutionError("declared_dirty_paths 超出 owned_paths")
            values = {
                "run_id": run_id,
                "work_id": work_id,
                "state": RunState.RUNNING.value,
                "executor_id": executor_id,
                "adapter": adapter,
                "owned_paths_json": json.dumps(owned, ensure_ascii=False),
                "declared_dirty_paths_json": json.dumps(declared, ensure_ascii=False),
                "git_head": git_head,
                "worktree_path": worktree_path,
                "version": 1,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            lease = {
                "run_id": run_id,
                "owner_id": executor_id,
                "lease_token": lease_token,
                "expires_at": (now + timedelta(seconds=lease_seconds)).isoformat(),
                "version": 1,
                "updated_at": now.isoformat(),
            }
            return self._store.create_run(values, lease, idempotency_key, now.isoformat())
        except ContinuityStoreError as error:
            raise ContinuityExecutionError(str(error)) from error

    def renew_lease(
        self,
        run_id: str,
        owner_id: str,
        lease_token: str,
        lease_seconds: int,
        idempotency_key: str,
    ) -> LeaseItem:
        now = self._utc_now()
        if lease_seconds < 60 or lease_seconds > 86_400:
            raise ContinuityExecutionError("lease_seconds 必须在 60 到 86400 之间")
        try:
            lease = self._store.get_lease(run_id)
            self._require_active_lease(lease, owner_id, lease_token, now)
            return self._store.renew_lease(
                run_id,
                owner_id,
                lease_token,
                lease.version,
                (now + timedelta(seconds=lease_seconds)).isoformat(),
                idempotency_key,
                now.isoformat(),
            )
        except ContinuityStoreError as error:
            raise ContinuityExecutionError(str(error)) from error

    def checkpoint(
        self,
        *,
        checkpoint_id: str,
        run_id: str,
        owner_id: str,
        lease_token: str,
        summary: str,
        git_head: str,
        dirty_paths: list[str],
        evidence: list[str],
        idempotency_key: str,
    ) -> CheckpointItem:
        now = self._utc_now()
        try:
            run = self._store.get_run(run_id)
            lease = self._store.get_lease(run_id)
            self._require_active_lease(lease, owner_id, lease_token, now)
            if run.git_head != git_head:
                raise ContinuityExecutionError("Git baseline drift")
            dirty = self._normalize_paths(dirty_paths, allow_empty=True)
            if not self._paths_covered(dirty, run.owned_paths):
                raise ContinuityExecutionError("Checkpoint 包含超出 owned_paths 的 dirty path")
            clean_evidence = tuple(item.strip() for item in evidence if item.strip())
            if not summary.strip() or not clean_evidence:
                raise ContinuityExecutionError("Checkpoint 必须包含摘要和 evidence")
            values = {
                "checkpoint_id": checkpoint_id,
                "run_id": run_id,
                "summary": summary,
                "git_head": git_head,
                "dirty_paths_json": json.dumps(dirty, ensure_ascii=False),
                "evidence_json": json.dumps(clean_evidence, ensure_ascii=False),
                "created_at": now.isoformat(),
            }
            return self._store.create_checkpoint(values, idempotency_key, now.isoformat())
        except ContinuityStoreError as error:
            raise ContinuityExecutionError(str(error)) from error

    def create_handoff(
        self,
        *,
        handoff_id: str,
        checkpoint_id: str,
        from_owner: str,
        to_owner: str,
        lease_token: str,
        idempotency_key: str,
    ) -> HandoffV2:
        now = self._utc_now()
        if not handoff_id.strip() or not to_owner.strip() or from_owner == to_owner:
            raise ContinuityExecutionError("Handoff 身份与不同的接收 owner 均为必填")
        try:
            checkpoint = self._store.get_checkpoint(checkpoint_id)
            run = self._store.get_run(checkpoint.run_id)
            lease = self._store.get_lease(run.run_id)
            self._require_active_lease(lease, from_owner, lease_token, now)
            if checkpoint.git_head != run.git_head:
                raise ContinuityExecutionError("Handoff checkpoint 与 Run baseline 不一致")
            unsigned = {
                "handoff_id": handoff_id,
                "work_id": run.work_id,
                "run_id": run.run_id,
                "checkpoint_id": checkpoint.checkpoint_id,
                "from_owner": from_owner,
                "to_owner": to_owner,
                "owned_paths_json": json.dumps(run.owned_paths, ensure_ascii=False),
                "git_head": run.git_head,
                "worktree_path": run.worktree_path,
                "lease_expires_at": lease.expires_at,
                "created_at": now.isoformat(),
            }
            canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            values = {**unsigned, "snapshot_hash": hashlib.sha256(canonical.encode()).hexdigest()}
            return self._store.create_handoff(values, idempotency_key, now.isoformat())
        except ContinuityStoreError as error:
            raise ContinuityExecutionError(str(error)) from error

    def accept_handoff(
        self,
        *,
        handoff_id: str,
        receiver_id: str,
        new_lease_token: str,
        lease_seconds: int,
        idempotency_key: str,
    ) -> LeaseItem:
        """Atomically transfer the Run lease to the named handoff receiver."""
        now = self._utc_now()
        if lease_seconds < 60 or lease_seconds > 86_400:
            raise ContinuityExecutionError("lease_seconds 必须在 60 到 86400 之间")
        if not new_lease_token.strip():
            raise ContinuityExecutionError("new_lease_token 不能为空")
        try:
            handoff = self._store.get_handoff(handoff_id)
            if handoff.to_owner != receiver_id:
                raise ContinuityExecutionError("接收方与 Handoff to_owner 不一致")
            lease = self._store.get_lease(handoff.run_id)
            if lease.owner_id != handoff.from_owner:
                raise ContinuityExecutionError("Handoff 源 owner 已失去 lease")
            if datetime.fromisoformat(lease.expires_at) <= now:
                raise ContinuityExecutionError("Handoff lease 已过期")
            return self._store.transfer_lease(
                handoff.run_id,
                handoff.from_owner,
                receiver_id,
                new_lease_token,
                lease.version,
                (now + timedelta(seconds=lease_seconds)).isoformat(),
                idempotency_key,
                now.isoformat(),
            )
        except ContinuityStoreError as error:
            raise ContinuityExecutionError(str(error)) from error

    def load_legacy_handoff(self, path: str | Path) -> dict[str, object]:
        """Read legacy v1 evidence without importing it into mutable continuity state."""
        candidate = Path(path).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as error:
            raise ContinuityExecutionError("legacy handoff 必须位于工作空间内") from error
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as error:
            raise ContinuityExecutionError("legacy handoff 无法读取") from error
        if payload.get("schema_version") != "handoff.v1":
            raise ContinuityExecutionError("未知 handoff schema")
        return {"compatibility": "READ_ONLY", "payload": payload}

    def transition_run(
        self,
        run_id: str,
        new_state: RunState,
        owner_id: str,
        lease_token: str,
        idempotency_key: str,
    ) -> RunItem:
        try:
            run = self._store.get_run(run_id)
            lease = self._store.get_lease(run_id)
            self._require_active_lease(lease, owner_id, lease_token, self._utc_now())
            if new_state not in _RUN_TRANSITIONS[run.state]:
                raise ContinuityExecutionError(f"非法 Run 状态迁移: {run.state} -> {new_state}")
            return self._store.transition_run(
                run_id, run.version, new_state.value, idempotency_key, self._utc_now().isoformat()
            )
        except ContinuityStoreError as error:
            raise ContinuityExecutionError(str(error)) from error

    def get_run(self, run_id: str) -> RunItem:
        """Return one Run for CLI-side physical Git verification."""
        try:
            return self._store.get_run(run_id)
        except ContinuityStoreError as error:
            raise ContinuityExecutionError(str(error)) from error

    @staticmethod
    def _require_active_lease(
        lease: LeaseItem, owner_id: str, lease_token: str, now: datetime
    ) -> None:
        expires_at = datetime.fromisoformat(lease.expires_at)
        if lease.owner_id != owner_id or lease.lease_token != lease_token:
            raise ContinuityExecutionError("lease ownership 不匹配")
        if expires_at <= now:
            raise ContinuityExecutionError("lease 已过期")

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise ContinuityExecutionError("now 必须是带时区时间")
        return value.astimezone(UTC)

    @staticmethod
    def _normalize_paths(paths: list[str], *, allow_empty: bool = False) -> tuple[str, ...]:
        result: list[str] = []
        for raw in paths:
            path = PurePosixPath(str(raw).replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
                raise ContinuityExecutionError(f"非法 path: {raw}")
            normalized = path.as_posix()
            if normalized not in result:
                result.append(normalized)
        if not result and not allow_empty:
            raise ContinuityExecutionError("paths 不能为空")
        return tuple(result)

    @staticmethod
    def _paths_covered(paths: tuple[str, ...], roots: tuple[str, ...]) -> bool:
        return all(
            any(path == root or path.startswith(f"{root.rstrip('/')}/") for root in roots)
            for path in paths
        )
