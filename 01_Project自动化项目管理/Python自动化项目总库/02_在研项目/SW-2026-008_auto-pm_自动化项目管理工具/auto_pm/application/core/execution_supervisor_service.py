"""Map trusted executor startup evidence into one lease-bound Continuity Run."""

from __future__ import annotations

import hashlib
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
from auto_pm.contracts.execution_adapter import ExecutionStartEvidence
from auto_pm.infrastructure.local_executor import (
    LocalExecutionResult,
    LocalExecutionStatus,
)


class ExecutionSupervisorError(RuntimeError):
    """Raised when trusted startup evidence cannot safely become Run state."""


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
    "ExecutionSupervisorError",
    "ExecutionSupervisorService",
    "ExecutionCompletionOutcome",
    "LeaseCapability",
    "LeaseRenewalOutcome",
]
