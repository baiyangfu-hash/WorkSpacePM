"""Map trusted executor startup evidence into one lease-bound Continuity Run."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from auto_pm.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)

from auto_pm.contracts.continuity import LeaseRenewalReceipt, RunItem, RunState
from auto_pm.contracts.execution_adapter import (
    ExecutionProjectionReceipt,
    ExecutionStartEvidence,
)
from auto_pm.infrastructure.local_executor import (
    LocalExecutionResult,
    LocalExecutionStatus,
)


class ExecutionSupervisorError(RuntimeError):
    """Raised when trusted startup evidence cannot safely become Run state."""


class ExecutionCollectionPendingError(ExecutionSupervisorError):
    """Raised after collection loses authority and must remain pending."""


@dataclass(frozen=True)
class LeaseCapability:
    """In-memory lease authority whose representation never reveals its secret."""

    run_id: str
    owner_id: str
    version: int
    expires_at: datetime
    token: str = field(repr=False)


@dataclass(frozen=True)
class LeaseRenewalOutcome:
    """Renewal result plus the capability that must be used for the next CAS."""

    capability: LeaseCapability
    receipt: LeaseRenewalReceipt | None


@dataclass(frozen=True)
class ExecutionCompletionOutcome:
    """A collected executor result and the truthful Continuity disposition."""

    result: LocalExecutionResult
    capability: LeaseCapability
    run_state: RunState
    disposition: str


@dataclass(frozen=True)
class ExecutionCollectedOutcome:
    """A collected child result with no Run finalization side effect."""

    result: LocalExecutionResult
    capability: LeaseCapability
    disposition: str


class ExecutionSupervisorService:
    """Persist E03A evidence before declaring a lease-bound Run as running.

    The caller owns the already-started child and supplies its reaper.  A failed
    persistence attempt therefore never licenses a second start: a successful
    reap leaves the Run READY for an explicit retry; an unreaped child is marked
    BLOCKED under the same lease.
    """

    def __init__(
        self,
        workspace_root: str | Path,
        execution: ContinuityExecutionService | None = None,
    ) -> None:
        self._execution = execution or ContinuityExecutionService(workspace_root)

    def record_started(
        self,
        *,
        run_id: str,
        owner_id: str,
        lease_token: str,
        evidence: ExecutionStartEvidence,
        idempotency_key: str,
        reap_current: Callable[[], None],
    ) -> RunItem:
        """CAS-map canonical evidence; reap the current child before any retry."""

        try:
            return cast(
                RunItem,
                self._execution.record_start_evidence(
                    run_id=run_id,
                    owner_id=owner_id,
                    lease_token=lease_token,
                    evidence=evidence,
                    idempotency_key=idempotency_key,
                ),
            )
        except ContinuityExecutionError as error:
            try:
                reap_current()
            except Exception as reap_error:
                blocked_key = self._blocked_key(idempotency_key)
                try:
                    self._execution.transition_run(
                        run_id,
                        RunState.BLOCKED,
                        owner_id,
                        lease_token,
                        blocked_key,
                    )
                except ContinuityExecutionError as transition_error:
                    raise ExecutionSupervisorError(
                        "启动证据落账失败且子进程无法回收；Run 状态未能安全封锁"
                    ) from transition_error
                raise ExecutionSupervisorError(
                    "启动证据落账失败，子进程无法回收；Run 已标记 BLOCKED"
                ) from reap_error
            raise ExecutionSupervisorError("启动证据落账失败，当前子进程已回收") from error

    def renew_if_due(
        self,
        capability: LeaseCapability,
        *,
        lease_seconds: int,
        renew_before_seconds: int,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> LeaseRenewalOutcome:
        """Renew when due and advance the in-memory capability for the next CAS."""

        observed_at = now or datetime.now(UTC)
        if observed_at.tzinfo is None or capability.expires_at.tzinfo is None:
            raise ExecutionSupervisorError("lease 时间必须包含时区")
        if renew_before_seconds < 0 or renew_before_seconds >= lease_seconds:
            raise ExecutionSupervisorError("续租安全窗口无效")
        if capability.expires_at - observed_at > timedelta(seconds=renew_before_seconds):
            return LeaseRenewalOutcome(capability=capability, receipt=None)
        try:
            receipt = cast(
                LeaseRenewalReceipt,
                self._execution.renew_lease(
                    capability.run_id,
                    capability.owner_id,
                    capability.token,
                    lease_seconds,
                    idempotency_key,
                    expected_version=capability.version,
                ),
            )
        except ContinuityExecutionError as error:
            raise ExecutionSupervisorError("lease 自动续租失败") from error
        try:
            expires_at = datetime.fromisoformat(receipt.expires_at)
        except ValueError as error:
            raise ExecutionSupervisorError("lease 续租回执时间无效") from error
        if expires_at.tzinfo is None:
            raise ExecutionSupervisorError("lease 续租回执时间必须包含时区")
        next_capability = LeaseCapability(
            run_id=receipt.run_id,
            owner_id=receipt.owner_id,
            version=receipt.version,
            expires_at=expires_at,
            token=capability.token,
        )
        return LeaseRenewalOutcome(capability=next_capability, receipt=receipt)

    def wait_for_completion(
        self,
        capability: LeaseCapability,
        *,
        wait_and_collect: Callable[[], LocalExecutionResult],
        lease_seconds: int,
        renew_before_seconds: int,
        idempotency_key: str,
    ) -> ExecutionCompletionOutcome:
        """Collect one E03A process only while its E04 lease remains current.

        The executor is the sole source of process completion.  In particular,
        model stdout is deliberately never inspected when deciding whether a
        completed process may enter ``VERIFYING``.
        """

        before_wait = self.renew_if_due(
            capability,
            lease_seconds=lease_seconds,
            renew_before_seconds=renew_before_seconds,
            idempotency_key=self._completion_key(idempotency_key, "before-wait"),
        )
        try:
            result = wait_and_collect()
        except Exception as error:
            raise ExecutionSupervisorError("执行结果 collect 失败") from error
        after_wait = self.renew_if_due(
            before_wait.capability,
            lease_seconds=lease_seconds,
            renew_before_seconds=renew_before_seconds,
            idempotency_key=self._completion_key(idempotency_key, "after-wait"),
        )
        disposition = self._completion_disposition(result)
        target_state = (
            RunState.VERIFYING if disposition == "ZERO_EXIT" else RunState.FAILED
        )
        try:
            self._execution.transition_run(
                after_wait.capability.run_id,
                target_state,
                after_wait.capability.owner_id,
                after_wait.capability.token,
                self._completion_key(idempotency_key, disposition.lower()),
            )
        except ContinuityExecutionError as error:
            raise ExecutionSupervisorError("执行结束状态无法安全落账") from error
        return ExecutionCompletionOutcome(
            result=result,
            capability=after_wait.capability,
            run_state=target_state,
            disposition=disposition,
        )

    def collect_completion(
        self,
        capability: LeaseCapability,
        *,
        wait_and_collect: Callable[[], LocalExecutionResult],
        reap_current: Callable[[], None],
        lease_seconds: int,
        renew_before_seconds: int,
        renewal_interval_seconds: float,
        idempotency_key: str,
    ) -> ExecutionCollectedOutcome:
        """Collect in the foreground while periodically renewing; never finalize a Run."""

        if not 0 < renewal_interval_seconds < lease_seconds:
            raise ExecutionSupervisorError("periodic renewal interval 无效")
        try:
            current = self.renew_if_due(
                capability,
                lease_seconds=lease_seconds,
                renew_before_seconds=renew_before_seconds,
                idempotency_key=self._completion_key(idempotency_key, "before-collect"),
            ).capability
        except ExecutionSupervisorError as error:
            self._abort_collection(reap_current, error=error)
        results: list[LocalExecutionResult] = []
        failures: list[Exception] = []

        def collect() -> None:
            try:
                results.append(wait_and_collect())
            except Exception as error:  # pragma: no cover - re-raised on caller thread
                failures.append(error)

        thread = threading.Thread(target=collect, daemon=True)
        thread.start()
        cycle = 0
        try:
            while thread.is_alive():
                thread.join(timeout=renewal_interval_seconds)
                if thread.is_alive():
                    cycle += 1
                    current = self.renew_if_due(
                        current,
                        lease_seconds=lease_seconds,
                        renew_before_seconds=renew_before_seconds,
                        idempotency_key=self._completion_key(
                            idempotency_key, f"periodic-{cycle}"
                        ),
                    ).capability
        except ExecutionSupervisorError as error:
            self._abort_collection(reap_current, error=error, thread=thread)
        thread.join()
        if failures or len(results) != 1:
            raise ExecutionSupervisorError("执行结果 collect 失败") from (
                failures[0] if failures else None
            )
        current = self.renew_if_due(
            current,
            lease_seconds=lease_seconds,
            renew_before_seconds=renew_before_seconds,
            idempotency_key=self._completion_key(idempotency_key, "after-collect"),
        ).capability
        result = results[0]
        return ExecutionCollectedOutcome(
            result=result,
            capability=current,
            disposition=self._completion_disposition(result),
        )

    @staticmethod
    def _abort_collection(
        reap_current: Callable[[], None],
        *,
        error: ExecutionSupervisorError,
        thread: threading.Thread | None = None,
    ) -> None:
        """Stop the owned child after authority loss, or surface a pending boundary."""

        try:
            reap_current()
        except Exception as reap_error:
            raise ExecutionCollectionPendingError(
                "lease 续租失败且 child 无法证明已回收；保持 PENDING"
            ) from reap_error
        if thread is not None:
            thread.join(timeout=5.0)
            if thread.is_alive():
                raise ExecutionCollectionPendingError(
                    "lease 续租失败且 collector 无法证明已停止；保持 PENDING"
                ) from error
        raise ExecutionCollectionPendingError(
            "lease 续租失败；child 已回收且 Run 保持 PENDING"
        ) from error

    def finalize_collected(
        self,
        collected: ExecutionCollectedOutcome,
        *,
        projection_receipt: ExecutionProjectionReceipt | None,
        idempotency_key: str,
    ) -> ExecutionCompletionOutcome:
        """Finalize only zero-exit results with an exact append-only projection proof."""

        projection_valid = (
            projection_receipt is not None
            and projection_receipt.run_id == collected.capability.run_id
        )
        if collected.disposition == "ZERO_EXIT" and projection_valid:
            target_state = RunState.VERIFYING
            disposition = "ZERO_EXIT_PROJECTED"
        elif collected.disposition == "ZERO_EXIT":
            target_state = RunState.FAILED
            disposition = "PROJECTION_FAILED"
        else:
            target_state = RunState.FAILED
            disposition = collected.disposition
        try:
            self._execution.transition_run(
                collected.capability.run_id,
                target_state,
                collected.capability.owner_id,
                collected.capability.token,
                self._completion_key(idempotency_key, disposition.lower()),
            )
        except ContinuityExecutionError as error:
            raise ExecutionSupervisorError("执行结束状态无法安全落账") from error
        return ExecutionCompletionOutcome(
            result=collected.result,
            capability=collected.capability,
            run_state=target_state,
            disposition=disposition,
        )

    def fail_claimed_ready(
        self,
        capability: LeaseCapability,
        *,
        idempotency_key: str,
    ) -> RunItem:
        """Record a pre-handshake local start failure without inventing RUN_STARTED."""

        try:
            return cast(
                RunItem,
                self._execution.transition_run(
                    capability.run_id,
                    RunState.FAILED,
                    capability.owner_id,
                    capability.token,
                    self._completion_key(idempotency_key, "pre-handshake-failed"),
                ),
            )
        except ContinuityExecutionError as error:
            raise ExecutionSupervisorError("pre-handshake failure 无法安全落账") from error

    def recover_started_session(
        self,
        operation_id: str,
        *,
        observed_process_id: int,
        observed_session_id: str,
        observed_started_at: datetime,
        is_process_alive: Callable[[int], bool],
    ) -> ExecutionStartEvidence:
        """Return a prior session only after complete Continuity identity matching.

        This intentionally has no start side effect.  A mismatch is a recovery
        boundary, never a licence to guess from a reused PID or launch again.
        """

        if observed_started_at.tzinfo is None:
            raise ExecutionSupervisorError("观察到的 started_at 必须包含时区")
        try:
            _, _, evidence = self._execution.resolve_started_run(operation_id)
        except ContinuityExecutionError as error:
            raise ExecutionSupervisorError("运行身份不可恢复，必须 BLOCKED/待恢复") from error
        if (
            not is_process_alive(evidence.process_id)
            or observed_process_id != evidence.process_id
            or observed_session_id != evidence.session_id
            or observed_started_at != evidence.started_at
        ):
            raise ExecutionSupervisorError("运行身份不可恢复，必须 BLOCKED/待恢复")
        return cast(ExecutionStartEvidence, evidence)

    @staticmethod
    def _completion_disposition(result: LocalExecutionResult) -> str:
        """Classify exit truth without trusting model text or a claimed status."""

        if result.timed_out or result.exit_code is None or result.exit_code < 0:
            return "TERMINATED"
        if result.exit_code != 0:
            return "NONZERO_EXIT"
        if result.status is not LocalExecutionStatus.SUCCEEDED:
            return "EXECUTOR_FAILED"
        return "ZERO_EXIT"

    @staticmethod
    def _blocked_key(idempotency_key: str) -> str:
        digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return f"execution-start-blocked:{digest}"

    @staticmethod
    def _completion_key(idempotency_key: str, phase: str) -> str:
        digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return f"execution-completion-{phase}:{digest}"


__all__ = [
    "ExecutionCollectionPendingError",
    "ExecutionSupervisorError",
    "ExecutionSupervisorService",
    "ExecutionCompletionOutcome",
    "ExecutionCollectedOutcome",
    "LeaseCapability",
    "LeaseRenewalOutcome",
]
