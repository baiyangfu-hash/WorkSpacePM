"""Run, checkpoint, lease, and handoff orchestration for continuity v2."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

from auto_pm.application.core.evidence_collection_service import (
    EvidenceCollection,
    EvidenceCollectionError,
    EvidenceCollectionService,
)
from auto_pm.contracts.continuity import (
    CheckpointItem,
    HandoffV2,
    LeaseItem,
    LeaseRenewalReceipt,
    RunItem,
    RunState,
    WorkState,
)
from auto_pm.contracts.decision_package import (
    RuntimeDecisionAction,
    RuntimeDecisionOutcome,
    is_canonical_decision_id,
)
from auto_pm.contracts.execution_adapter import ExecutionDispatchReceipt, ExecutionStartEvidence
from auto_pm.domain.change.decision_service import DecisionError, DecisionService
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    authority_path_parts,
    governed_worktree_snapshot,
)


class ContinuityExecutionError(RuntimeError):
    """Raised when execution continuity would become ambiguous or unsafe."""


_RUN_TRANSITIONS = {
    RunState.READY: {RunState.RUNNING, RunState.BLOCKED, RunState.CANCELLED},
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
        self._now = now or (lambda: datetime.now(UTC))
        self._store = store or ContinuityStore(self._root)

    def replay_run_start(
        self,
        *,
        run_id: str,
        work_id: str,
        executor_id: str,
        adapter: str,
        owned_paths: list[str],
        declared_dirty_paths: list[str],
        worktree_path: str,
        lease_token: str,
        lease_seconds: int,
        idempotency_key: str,
    ) -> RunItem | None:
        """Replay prior CLI start intent before sampling mutable Git facts."""

        if not all(
            isinstance(value, str) and value and value == value.strip()
            for value in (run_id, work_id, executor_id, adapter)
        ):
            raise ContinuityExecutionError(
                "Run 身份、Work、executor 与 adapter 必须是 canonical 非空文本"
            )
        if (
            not isinstance(lease_token, str)
            or lease_token != lease_token.strip()
            or not lease_token
            or any(not character.isprintable() for character in lease_token)
        ):
            raise ContinuityExecutionError("lease_token 必须是非空 canonical 可打印文本")
        if type(lease_seconds) is not int or not 60 <= lease_seconds <= 86_400:
            raise ContinuityExecutionError("lease_seconds 必须在 60 到 86400 之间")
        if (
            not isinstance(idempotency_key, str)
            or idempotency_key != idempotency_key.strip()
            or not 1 <= len(idempotency_key) <= 255
            or any(not character.isprintable() for character in idempotency_key)
        ):
            raise ContinuityExecutionError(
                "idempotency_key 必须是 1 到 255 个 canonical 可打印字符"
            )
        owned = self._normalize_paths(owned_paths)
        declared = self._normalize_paths(declared_dirty_paths, allow_empty=True)
        if not self._paths_covered(declared, owned):
            raise ContinuityExecutionError("declared_dirty_paths 超出 owned_paths")
        try:
            return self._store.run_creation_intent_replay(
                run_id=run_id,
                work_id=work_id,
                executor_id=executor_id,
                adapter=adapter,
                owned_paths=owned,
                declared_dirty_paths=declared,
                worktree_path=worktree_path,
                lease_token=lease_token,
                lease_seconds=lease_seconds,
                idempotency_key=idempotency_key,
            )
        except ContinuityStoreError as error:
            raise ContinuityExecutionError(str(error)) from error

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
        if not all(
            isinstance(value, str) and value and value == value.strip()
            for value in (run_id, work_id, executor_id, adapter, git_head)
        ):
            raise ContinuityExecutionError(
                "Run 身份、Work、executor、adapter 与 Git HEAD 必须是 canonical 非空文本"
            )
        if (
            not isinstance(lease_token, str)
            or lease_token != lease_token.strip()
            or not lease_token
            or any(not character.isprintable() for character in lease_token)
        ):
            raise ContinuityExecutionError("lease_token 必须是非空 canonical 可打印文本")
        if type(lease_seconds) is not int or not 60 <= lease_seconds <= 86_400:
            raise ContinuityExecutionError("lease_seconds 必须在 60 到 86400 之间")
        if (
            not isinstance(idempotency_key, str)
            or idempotency_key != idempotency_key.strip()
            or not 1 <= len(idempotency_key) <= 255
            or any(not character.isprintable() for character in idempotency_key)
        ):
            raise ContinuityExecutionError(
                "idempotency_key 必须是 1 到 255 个 canonical 可打印字符"
            )
        owned = self._normalize_paths(owned_paths)
        declared = self._normalize_paths(declared_dirty_paths, allow_empty=True)
        observed = self._normalize_paths(observed_dirty_paths, allow_empty=True)
        if not self._paths_covered(observed, declared):
            raise ContinuityExecutionError("存在未声明的 dirty path")
        try:
            replay = self._store.run_creation_replay(
                run_id=run_id,
                work_id=work_id,
                executor_id=executor_id,
                adapter=adapter,
                owned_paths=owned,
                declared_dirty_paths=declared,
                observed_dirty_paths=observed,
                git_head=git_head,
                worktree_path=worktree_path,
                lease_token=lease_token,
                lease_seconds=lease_seconds,
                idempotency_key=idempotency_key,
            )
            if replay is not None:
                return replay
            now = self._utc_now()
            governed_worktree, actual_head, actual_dirty = governed_worktree_snapshot(
                self._root,
                worktree_path,
            )
            if actual_head != git_head:
                raise ContinuityExecutionError("Run git_head 与受管 worktree 当前 HEAD 不一致")
            actual_observed = tuple(
                path for path in actual_dirty if self._paths_covered((path,), owned)
            )
            requested_dirty_keys = {authority_path_parts(path) for path in observed}
            actual_dirty_keys = {authority_path_parts(path) for path in actual_observed}
            if requested_dirty_keys != actual_dirty_keys:
                raise ContinuityExecutionError("Run observed_dirty_paths 与受管 worktree 不一致")
            work = self._store.get_work(work_id)
            if work.state.value not in {"READY", "IN_PROGRESS"}:
                raise ContinuityExecutionError("只有 READY/IN_PROGRESS Work 可以创建 Run")
            self._reject_existing_active_run(work_id, run_id)
            if not self._paths_covered(owned, work.scope_paths):
                raise ContinuityExecutionError("owned_paths 超出 Work scope")
            if not self._paths_covered(declared, owned):
                raise ContinuityExecutionError("declared_dirty_paths 超出 owned_paths")
            values = {
                "run_id": run_id,
                "work_id": work_id,
                "state": RunState.READY.value,
                "executor_id": executor_id,
                "adapter": adapter,
                "owned_paths_json": json.dumps(owned, ensure_ascii=False),
                "declared_dirty_paths_json": json.dumps(declared, ensure_ascii=False),
                "git_head": git_head,
                "worktree_path": str(governed_worktree),
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
            return self._store.create_run(
                values,
                lease,
                actual_observed,
                lease_seconds,
                idempotency_key,
            )
        except (ContinuityStoreError, ControlRootGuardError) as error:
            raise ContinuityExecutionError(str(error)) from error

    def renew_lease(
        self,
        run_id: str,
        owner_id: str,
        lease_token: str,
        lease_seconds: int,
        idempotency_key: str,
        *,
        expected_version: int | None = None,
    ) -> LeaseRenewalReceipt:
        if type(lease_seconds) is not int or not 60 <= lease_seconds <= 86_400:
            raise ContinuityExecutionError("lease_seconds 必须在 60 到 86400 之间")
        try:
            lease = self._store.renew_lease(
                run_id,
                owner_id,
                lease_token,
                lease_seconds,
                idempotency_key,
                expected_version=expected_version,
            )
            return LeaseRenewalReceipt(
                run_id=lease.run_id,
                owner_id=lease.owner_id,
                expires_at=lease.expires_at,
                version=lease.version,
                updated_at=lease.updated_at,
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

    def append_verified_checkpoint(
        self,
        *,
        checkpoint_id: str,
        run_id: str,
        owner_id: str,
        lease_token: str,
        project_root: str | Path,
    ) -> CheckpointItem:
        """Append one system-generated, content-bound checkpoint for a Run.

        No caller-supplied result document, summary, dirty path, Git baseline,
        or evidence is accepted.  The service derives all of those values from
        fresh Run-scoped Git evidence and the real C02 Python quality receipt.
        Existing identities replay only when their canonical stored payload is
        still intact and proves the current evidence.
        """

        now = self._utc_now()
        try:
            run = self._store.get_run(run_id)
            lease = self._store.get_lease(run_id)
            self._require_active_lease(lease, owner_id, lease_token, now)
            existing = self._existing_checkpoint(checkpoint_id)
        except ContinuityStoreError as error:
            raise ContinuityExecutionError(str(error)) from error

        collector = EvidenceCollectionService(self._root)
        summary = self._auto_checkpoint_summary(run)
        try:
            collector.validate_c03_checkpoint_project_root(run, project_root)
        except EvidenceCollectionError as error:
            raise ContinuityExecutionError(
                f"自动 Checkpoint C03 profile 无法验证: {error}"
            ) from error
        if existing is not None:
            try:
                collection = collector.collect(run)
            except EvidenceCollectionError as error:
                raise ContinuityExecutionError(
                    f"自动 Checkpoint 无法复核当前 evidence: {error}"
                ) from error
            dirty_paths = self._checkpoint_dirty_paths(collection)
            if (
                existing.run_id != run.run_id
                or existing.summary != summary
                or existing.git_head != run.git_head
                or existing.dirty_paths != tuple(dirty_paths)
                or len(existing.evidence) != 1
                or not collector.checkpoint_evidence_is_current(
                    existing.evidence[0], collection, run, project_root
                )
            ):
                raise ContinuityExecutionError(
                    "Checkpoint identity 已存在，但自动证据或当前 Run 内容不一致"
                )
            replay = self.checkpoint(
                checkpoint_id=checkpoint_id,
                run_id=run_id,
                owner_id=owner_id,
                lease_token=lease_token,
                summary=summary,
                git_head=collection.git_head,
                dirty_paths=dirty_paths,
                evidence=list(existing.evidence),
                idempotency_key=self._c03_checkpoint_idempotency_key(
                    run, checkpoint_id, collection.content_hash
                ),
            )
            return self._require_matching_c03_checkpoint(
                replay,
                checkpoint_id=checkpoint_id,
                run_id=run_id,
                summary=summary,
                collection=collection,
                evidence=existing.evidence[0],
            )

        try:
            receipt = collector.run_c03_checkpoint_quality_gates(run, project_root)
            if receipt.status != "PASS":
                raise ContinuityExecutionError("自动 Checkpoint 要求 Python 质量收据为 PASS")
            if not collector.c03_checkpoint_receipt_matches_profile(receipt):
                raise ContinuityExecutionError(
                    "自动 Checkpoint 要求固定 C03 pytest profile 与收据 hash"
                )
            if not collector.quality_receipt_is_current(run, project_root, receipt):
                raise ContinuityExecutionError("自动 Checkpoint 的 Python 质量收据已失效")
            collection = collector.collect(run)
            evidence = collector.build_checkpoint_evidence(collection, receipt)
        except EvidenceCollectionError as error:
            raise ContinuityExecutionError(
                f"自动 Checkpoint evidence 或质量门无法验证: {error}"
            ) from error

        checkpoint = self.checkpoint(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            owner_id=owner_id,
            lease_token=lease_token,
            summary=summary,
            git_head=collection.git_head,
            dirty_paths=self._checkpoint_dirty_paths(collection),
            evidence=[evidence],
            idempotency_key=self._c03_checkpoint_idempotency_key(
                run, checkpoint_id, collection.content_hash
            ),
        )
        return self._require_matching_c03_checkpoint(
            checkpoint,
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            summary=summary,
            collection=collection,
            evidence=evidence,
        )

    def _existing_checkpoint(self, checkpoint_id: str) -> CheckpointItem | None:
        """Load an existing identity without conflating corruption with absence."""

        try:
            return self._store.get_checkpoint(checkpoint_id)
        except ContinuityStoreError as error:
            if str(error).startswith("Checkpoint 不存在:"):
                return None
            raise

    @staticmethod
    def _checkpoint_dirty_paths(collection: EvidenceCollection) -> list[str]:
        """Derive the immutable checkpoint path set from all Git dirty classes."""

        return sorted(
            {
                *collection.staged_paths,
                *collection.unstaged_paths,
                *collection.untracked_paths,
            }
        )

    @staticmethod
    def _auto_checkpoint_summary(run: RunItem) -> str:
        """Return a fixed, non-user-controlled summary suitable for replay checks."""

        return f"System-generated content-bound checkpoint for Run {run.run_id}"

    @staticmethod
    def _c03_checkpoint_idempotency_key(
        run: RunItem, checkpoint_id: str, collection_hash: str
    ) -> str:
        """Derive C03's immutable idempotency identity after fresh collection.

        A caller cannot select this key.  Its stable C03 schema identity, Run,
        checkpoint id, and exact collection content hash make replay possible
        only for the same persisted C03 checkpoint evidence.
        """

        payload = {
            "schema_version": "c03-auto-checkpoint-key.v1",
            "run_id": run.run_id,
            "checkpoint_id": checkpoint_id,
            "collection_hash": collection_hash,
        }
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return "c03-auto-checkpoint:" + hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()

    @classmethod
    def _require_matching_c03_checkpoint(
        cls,
        checkpoint: CheckpointItem,
        *,
        checkpoint_id: str,
        run_id: str,
        summary: str,
        collection: EvidenceCollection,
        evidence: str,
    ) -> CheckpointItem:
        """Fail closed if Store replay does not return C03's exact constructed CP.

        The generic Store owns its idempotency index and can only return a
        checkpoint object through its public API.  C03 therefore treats every
        return as untrusted until all immutable fields derived above match the
        current content-bound construction exactly.
        """

        if (
            checkpoint.checkpoint_id != checkpoint_id
            or checkpoint.run_id != run_id
            or checkpoint.summary != summary
            or checkpoint.git_head != collection.git_head
            or checkpoint.dirty_paths != tuple(cls._checkpoint_dirty_paths(collection))
            or checkpoint.evidence != (evidence,)
        ):
            raise ContinuityExecutionError(
                "持久化 Checkpoint 与 C03 自动构造的 identity 或 evidence 不一致"
            )
        return checkpoint

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
        if not handoff_id.strip() or not to_owner.strip() or from_owner == to_owner:
            raise ContinuityExecutionError("Handoff 身份与不同的接收 owner 均为必填")
        try:
            return self._store.create_handoff(
                handoff_id=handoff_id,
                checkpoint_id=checkpoint_id,
                from_owner=from_owner,
                to_owner=to_owner,
                lease_token=lease_token,
                idempotency_key=idempotency_key,
            )
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
        if type(lease_seconds) is not int or not 60 <= lease_seconds <= 86_400:
            raise ContinuityExecutionError("lease_seconds 必须在 60 到 86400 之间")
        if not new_lease_token.strip():
            raise ContinuityExecutionError("new_lease_token 不能为空")
        try:
            return self._store.transfer_lease(
                handoff_id,
                receiver_id,
                new_lease_token,
                lease_seconds,
                idempotency_key,
            )
        except ContinuityStoreError as error:
            raise ContinuityExecutionError(str(error)) from error

    def create_checkpoint_bound_handoff(
        self,
        *,
        checkpoint_id: str,
        from_owner: str,
        to_owner: str,
        lease_token: str,
        new_lease_token: str,
        lease_seconds: int,
        idempotency_key: str,
    ) -> tuple[HandoffV2, LeaseItem]:
        """Create and accept one deterministic v2 handoff from a Checkpoint.

        The durable handoff snapshot is created by the Store from the referenced
        Checkpoint, so its Work scope, Git baseline and worktree are never
        caller-provided.  The previous lease token is consumed only by the
        creation call and is not returned or persisted in the Handoff payload.
        """

        if not checkpoint_id.strip() or not idempotency_key.strip():
            raise ContinuityExecutionError("Checkpoint 与幂等键均为必填")
        digest = hashlib.sha256(
            f"{checkpoint_id}\x00{to_owner}".encode()
        ).hexdigest()[:24].upper()
        handoff = self.create_handoff(
            handoff_id=f"HO-{digest}",
            checkpoint_id=checkpoint_id,
            from_owner=from_owner,
            to_owner=to_owner,
            lease_token=lease_token,
            idempotency_key=f"{idempotency_key}:create",
        )
        lease = self.accept_handoff(
            handoff_id=handoff.handoff_id,
            receiver_id=to_owner,
            new_lease_token=new_lease_token,
            lease_seconds=lease_seconds,
            idempotency_key=f"{idempotency_key}:accept",
        )
        return handoff, lease

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

    def record_start_evidence(
        self,
        *,
        run_id: str,
        owner_id: str,
        lease_token: str,
        evidence: ExecutionStartEvidence,
        idempotency_key: str,
    ) -> RunItem:
        """Atomically persist trusted evidence and move exactly READY -> RUNNING."""

        now = self._utc_now()
        try:
            run = self._store.get_run(run_id)
            lease = self._store.get_lease(run_id)
            self._require_active_lease(lease, owner_id, lease_token, now)
            if run.executor_id != owner_id:
                raise ContinuityExecutionError("启动证据 owner 与 Run executor 不一致")
            return self._store.record_run_started(
                run_id=run_id,
                expected_version=run.version,
                owner_id=owner_id,
                lease_token=lease_token,
                evidence=evidence,
                idempotency_key=idempotency_key,
            )
        except ContinuityStoreError as error:
            raise ContinuityExecutionError(str(error)) from error

    def resolve_started_run(
        self, operation_id: str
    ) -> tuple[ExecutionDispatchReceipt, RunItem, ExecutionStartEvidence]:
        """Reconcile one durable operation with its only trusted started Run."""

        try:
            intent = self._store.get_execution_intent(operation_id)
            if intent is None:
                raise ContinuityExecutionError("ExecutionIntent 不存在")
            receipt = intent.receipt
            run = self._store.get_run(receipt.run_id)
            if (
                run.work_id != receipt.work_id
                or run.executor_id != receipt.executor_id
                or run.state not in {RunState.RUNNING, RunState.VERIFYING}
            ):
                raise ContinuityExecutionError("ExecutionIntent 与活动 Run 身份不一致")
            owner_id, evidence = self._store.get_run_started_evidence(receipt.run_id)
            if owner_id != receipt.owner_id:
                raise ContinuityExecutionError("RUN_STARTED owner 与派发回执不一致")
            return receipt, run, evidence
        except ContinuityStoreError as error:
            raise ContinuityExecutionError(str(error)) from error

    def settle_expired_run(
        self,
        *,
        target_run_id: str,
        recovery_run_id: str,
        recovery_owner_id: str,
        recovery_lease_token: str,
        decision_id: str,
        outcome: RunState,
        reason: str,
        idempotency_key: str,
    ) -> RunItem:
        """Close an abandoned Run under a separate live recovery authority chain."""

        normalized_reason = reason.strip()
        required = (
            target_run_id,
            recovery_run_id,
            recovery_owner_id,
            recovery_lease_token,
            decision_id,
            idempotency_key,
        )
        if not all(value.strip() for value in required):
            raise ContinuityExecutionError("结算身份、Decision、恢复 lease 与幂等键均不能为空")
        if (
            reason != normalized_reason
            or not normalized_reason
            or len(normalized_reason) > 1000
            or any(not character.isprintable() for character in normalized_reason)
        ):
            raise ContinuityExecutionError("结算原因必须为 1 到 1000 个字符")
        normalized_key = idempotency_key.strip()
        if (
            idempotency_key != normalized_key
            or len(normalized_key) > 255
            or any(not character.isprintable() for character in normalized_key)
        ):
            raise ContinuityExecutionError("idempotency_key 必须为 1 到 255 个可打印字符")
        if recovery_lease_token in normalized_reason:
            raise ContinuityExecutionError("结算原因不得包含恢复 lease token")
        if target_run_id == recovery_run_id:
            raise ContinuityExecutionError("目标 Run 与恢复 Run 必须不同")
        if outcome is not RunState.CANCELLED:
            raise ContinuityExecutionError("过期 Run 只能前向结算为 CANCELLED")

        try:
            replay = self._store.expired_run_settlement_replay(
                target_run_id=target_run_id,
                recovery_run_id=recovery_run_id,
                recovery_owner_id=recovery_owner_id,
                recovery_lease_token=recovery_lease_token,
                decision_id=decision_id,
                outcome=outcome.value,
                reason=normalized_reason,
                idempotency_key=idempotency_key,
            )
            if replay is not None:
                return replay
            runtime_target_path = self._store.runtime_target_path()
            decisions = DecisionService(self._root)
            decision, decision_sha256 = decisions.get_decision_with_sha256(decision_id)
            capability = decision.runtime_capability
            if decision.decision_conclusion != "approved" or decision.conditions:
                raise ContinuityExecutionError("运行态 Decision 必须是无条件 approved")
            if capability is None:
                raise ContinuityExecutionError("Decision 未声明 runtime_capability")
            if RuntimeDecisionAction.SETTLE_EXPIRED_RUN not in capability.allowed_runtime_actions:
                raise ContinuityExecutionError("Decision 未授权 settle_expired_run")
            if target_run_id not in capability.target_run_ids:
                raise ContinuityExecutionError("Decision 未授权目标 Run")
            authorized_outcome = RuntimeDecisionOutcome(outcome.value)
            if authorized_outcome not in capability.allowed_outcomes:
                raise ContinuityExecutionError("Decision 未授权目标结算状态")

            target = self._store.get_run(target_run_id)
            recovery = self._store.get_run(recovery_run_id)
            target_work = self._store.get_work(target.work_id)
            recovery_work = self._store.get_work(recovery.work_id)

            if target.work_id == recovery.work_id:
                raise ContinuityExecutionError("目标 Run 与恢复 Run 必须属于独立 Work")
            if target_work.read_only or not is_canonical_decision_id(target_work.authorization_ref):
                raise ContinuityExecutionError("目标 Work 必须绑定 canonical immutable Decision")
            target_decision_id = target_work.authorization_ref
            target_decision, target_decision_sha256 = decisions.get_decision_with_sha256(
                target_decision_id
            )
            if not is_canonical_decision_id(recovery_work.authorization_ref):
                raise ContinuityExecutionError("恢复 Work 必须绑定 canonical immutable Decision")
            if recovery_work.authorization_ref != decision_id:
                raise ContinuityExecutionError("恢复 Work 未绑定指定 Decision")
            if target_decision_id == decision_id:
                raise ContinuityExecutionError("恢复 Decision 不得复用目标 Work 的授权链")
            if target_decision.change_id == decision.change_id:
                raise ContinuityExecutionError("恢复 CHG 必须独立于目标 Work 的原 CHG")
            if target_work.subject_project_id != recovery_work.subject_project_id:
                raise ContinuityExecutionError("目标 Run 与恢复 Work 不属于同一项目")
            if decision.project_id != recovery_work.subject_project_id:
                raise ContinuityExecutionError("Decision 项目与恢复 Work 不一致")
            if target_decision.project_id != target_work.subject_project_id:
                raise ContinuityExecutionError("目标 Decision 项目与目标 Work 不一致")
            target_approved = self._normalize_paths(target_decision.approved_files)
            if not self._paths_covered(target_work.scope_paths, target_approved):
                raise ContinuityExecutionError("目标 Work scope 超出原 Decision approved_files")

            now = self._utc_now()
            target_lease = self._store.get_lease(target_run_id)
            recovery_lease = self._store.get_lease(recovery_run_id)
            if target.state in {RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED}:
                raise ContinuityExecutionError("目标 Run 已处于终态")
            if self._lease_expiry(target_lease, "目标 Run lease") > now:
                raise ContinuityExecutionError("目标 Run lease 尚未过期")
            if recovery.state is not RunState.RUNNING:
                raise ContinuityExecutionError("恢复 Run 必须处于 RUNNING")
            self._require_active_lease(
                recovery_lease,
                recovery_owner_id,
                recovery_lease_token,
                now,
            )
            if recovery_work.read_only or recovery_work.state is not WorkState.IN_PROGRESS:
                raise ContinuityExecutionError("恢复 Work 必须是 IN_PROGRESS 写入型 Work")
            approved = self._normalize_paths(decision.approved_files)
            recovery_scope = self._normalize_paths(list(recovery_work.scope_paths))
            recovery_owned = self._normalize_paths(list(recovery.owned_paths))
            runtime_target = (runtime_target_path,)
            if not self._paths_covered(runtime_target, approved):
                raise ContinuityExecutionError("Decision 未覆盖 canonical continuity.db")
            if not self._paths_covered(recovery_scope, approved):
                raise ContinuityExecutionError("恢复 Work scope 超出 Decision approved_files")
            if not self._paths_covered(runtime_target, recovery_scope):
                raise ContinuityExecutionError("恢复 Work scope 未覆盖 canonical continuity.db")
            if not self._paths_covered(runtime_target, recovery_owned):
                raise ContinuityExecutionError(
                    "恢复 Run owned_paths 未覆盖 canonical continuity.db"
                )

            return self._store.settle_expired_run(
                target_run_id=target_run_id,
                expected_target_state=target.state.value,
                expected_target_version=target.version,
                expected_target_lease_version=target_lease.version,
                expected_target_work_id=target_work.work_id,
                expected_target_work_version=target_work.version,
                expected_target_work_scope_hash=self._store.authority_paths_hash(
                    target_work.scope_paths
                ),
                recovery_run_id=recovery_run_id,
                expected_recovery_run_version=recovery.version,
                recovery_work_id=recovery_work.work_id,
                expected_recovery_work_version=recovery_work.version,
                expected_recovery_work_scope_hash=self._store.authority_paths_hash(
                    recovery_work.scope_paths
                ),
                expected_recovery_owned_paths_hash=self._store.authority_paths_hash(
                    recovery.owned_paths
                ),
                expected_recovery_git_head=recovery.git_head,
                recovery_owner_id=recovery_owner_id,
                recovery_lease_token=recovery_lease_token,
                expected_recovery_lease_version=recovery_lease.version,
                target_decision_id=target_decision_id,
                target_decision_sha256=target_decision_sha256,
                target_change_id=target_decision.change_id,
                decision_id=decision_id,
                decision_sha256=decision_sha256,
                decision_change_id=decision.change_id,
                decision_project_id=decision.project_id,
                decision_approved_paths=approved,
                runtime_target_path=runtime_target_path,
                outcome=outcome.value,
                reason=normalized_reason,
                idempotency_key=idempotency_key,
            )
        except (ContinuityStoreError, DecisionError) as error:
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
        expires_at = ContinuityExecutionService._lease_expiry(lease, "lease")
        if lease.owner_id != owner_id or lease.lease_token != lease_token:
            raise ContinuityExecutionError("lease ownership 不匹配")
        if expires_at <= now:
            raise ContinuityExecutionError("lease 已过期")

    @staticmethod
    def _lease_expiry(lease: LeaseItem, label: str) -> datetime:
        try:
            expires_at = datetime.fromisoformat(lease.expires_at)
        except ValueError as error:
            raise ContinuityExecutionError(f"{label} 时间戳非法") from error
        if expires_at.tzinfo is None:
            raise ContinuityExecutionError(f"{label} 时间戳必须包含时区")
        return expires_at.astimezone(UTC)

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise ContinuityExecutionError("now 必须是带时区时间")
        return value.astimezone(UTC)

    def _reject_existing_active_run(self, work_id: str, run_id: str) -> None:
        for candidate in self._store.list_runs(work_id):
            if candidate.run_id == run_id:
                raise ContinuityExecutionError("Run 已存在；精确重放必须使用原 idempotency_key")
            raise ContinuityExecutionError("Work 已有非终态 Run")

    @staticmethod
    def _normalize_paths(paths: list[str], *, allow_empty: bool = False) -> tuple[str, ...]:
        result: list[str] = []
        seen: set[tuple[str, ...]] = set()
        for raw in paths:
            text = str(raw).replace("\\", "/")
            raw_segments = text.split("/")
            path = PurePosixPath(text)
            if (
                path.is_absolute()
                or any(part in {".", ".."} for part in raw_segments)
                or str(path) in {"", "."}
                or any(part != part.rstrip(" .") for part in path.parts)
            ):
                raise ContinuityExecutionError(f"非法 path: {raw}")
            normalized = path.as_posix()
            key = authority_path_parts(normalized)
            if key not in seen:
                seen.add(key)
                result.append(normalized)
        if not result and not allow_empty:
            raise ContinuityExecutionError("paths 不能为空")
        return tuple(result)

    @staticmethod
    def _paths_covered(paths: tuple[str, ...], roots: tuple[str, ...]) -> bool:
        normalized_roots = tuple(authority_path_parts(root) for root in roots)
        return all(
            any(authority_path_parts(path)[: len(root)] == root for root in normalized_roots)
            for path in paths
        )
