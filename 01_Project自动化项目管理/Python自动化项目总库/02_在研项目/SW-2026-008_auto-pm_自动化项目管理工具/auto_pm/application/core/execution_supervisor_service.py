"""Map trusted executor startup evidence into one lease-bound Continuity Run."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import cast

from auto_pm.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)

from auto_pm.contracts.continuity import RunItem, RunState
from auto_pm.contracts.execution_adapter import ExecutionStartEvidence


class ExecutionSupervisorError(RuntimeError):
    """Raised when trusted startup evidence cannot safely become Run state."""


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

    @staticmethod
    def _blocked_key(idempotency_key: str) -> str:
        digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return f"execution-start-blocked:{digest}"


__all__ = ["ExecutionSupervisorError", "ExecutionSupervisorService"]
