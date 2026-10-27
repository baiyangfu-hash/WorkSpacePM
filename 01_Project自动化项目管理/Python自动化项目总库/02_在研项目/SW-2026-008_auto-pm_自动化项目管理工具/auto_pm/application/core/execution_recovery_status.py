"""Read-only verdict on a started Run's executor process after the controller restarted (TD-SW008-074, step 1).

``ExecutionSupervisorService.recover_started_session`` trusts a caller-supplied liveness probe.  This module is the real, side-effect-free judge:
it compares the process the ledger recorded (pid and ``thread.started`` time) with what this host shows now.  The ``thread.started`` event comes
after the process was created, so a process whose creation time is *later* than the recorded start is a different process that reuses the pid.
It never writes the ledger and never launches or kills anything; settling a dead Run is a separate step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from auto_pm.contracts.execution_adapter import ExecutionStartEvidence
from auto_pm.contracts.lease_reclaim import ProcessObservation
from auto_pm.infrastructure import process_probe

# Clock and tick rounding between the process table and the executor's own timestamp.
START_SKEW = timedelta(seconds=2)


class RecoveryVerdict(str, Enum):
    ALIVE = "ALIVE"
    DEAD = "DEAD"
    PID_REUSED = "PID_REUSED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RecoveryStatus:
    verdict: RecoveryVerdict
    reason: str


def judge_started_process(
    evidence: ExecutionStartEvidence,
    observation: ProcessObservation | None,
    created_at: datetime | None,
) -> RecoveryStatus:
    """Classify the recorded executor process; anything that cannot be observed is UNKNOWN, never DEAD."""

    if observation is None:
        return RecoveryStatus(RecoveryVerdict.UNKNOWN, "本机进程表读不出来，不能判断")
    if not observation.pid_exists:
        return RecoveryStatus(RecoveryVerdict.DEAD, "记录的进程已不在运行")
    if created_at is None:
        return RecoveryStatus(RecoveryVerdict.UNKNOWN, "进程在运行但读不到创建时刻，不能排除进程号被复用")
    if created_at.tzinfo is None:
        return RecoveryStatus(RecoveryVerdict.UNKNOWN, "进程创建时刻缺少时区")
    if created_at > evidence.started_at + START_SKEW:
        return RecoveryStatus(RecoveryVerdict.PID_REUSED, "该进程号现在属于更晚创建的进程，原执行进程已不在")
    return RecoveryStatus(RecoveryVerdict.ALIVE, "进程仍在运行，创建时刻不晚于记录的启动时刻")


def inspect_started_process(evidence: ExecutionStartEvidence) -> tuple[RecoveryStatus, datetime | None]:
    """Observe the recorded executor process on this host and judge it; also returns the creation time that was read (``None`` if unavailable)."""

    observation = process_probe.observe(evidence.process_id)
    created_at = process_probe.start_time_to_datetime(observation.start_time) if observation is not None else None
    return judge_started_process(evidence, observation, created_at), created_at
