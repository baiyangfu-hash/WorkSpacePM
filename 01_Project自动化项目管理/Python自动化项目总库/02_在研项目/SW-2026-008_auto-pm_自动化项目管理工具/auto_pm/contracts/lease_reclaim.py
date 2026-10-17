"""Lease reclaim and write-epoch contract (V04-R1, card 1: the contract only; nothing here touches the store).

Rules, independent of where a lease is arbitrated (the local SQLite store today, a Git reference later):

- **epoch is the ownership number of a Run's lease, NOT the lease version**: per Run, strictly increasing, raised only when ownership changes (a grant, a transfer, a reclaim) by whoever arbitrates the lease.
  A renewal never changes it. (The store's ``version`` is bumped by every renewal and serves only as the compare-and-swap of the renewal itself: a write that had to carry ``epoch == version`` would reject the
  holder's own in-flight writes after each heartbeat.) A holder records the epoch it was granted.
- A started Run may be reclaimed from its holder only with evidence about the holder's process: ``PROVEN_DEAD`` allows it, ``ALIVE`` refuses it, ``UNKNOWN`` (another host, no fingerprint recorded, the process
  table could not be read, same start time but unverifiable image) is **PENDING** - an unknown process is never pre-empted.
- A live lease (not yet expired plus a grace period) is reclaimed only by an explicit decision and only when the holder's process is proven dead.
- The write check must happen inside the same write transaction as the write itself (a check made earlier, in another transaction, can be overtaken by a reclaim): that is the job of the storage card.
- A write that carries an epoch older than the current one is refused; an epoch ahead of the current one is refused too (it cannot have been granted); a write without an epoch is accepted with a
  warning only during the compatibility period.

Nothing here edits ``expires_at``, reads or returns a lease token, or runs a process probe: callers pass in the facts they observed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

GRACE_SECONDS: Final = 120


class ProcessVerdict(StrEnum):
    PROVEN_DEAD = "PROVEN_DEAD"
    ALIVE = "ALIVE"
    UNKNOWN = "UNKNOWN"


class ReclaimDecision(StrEnum):
    ALLOW = "ALLOW"
    REFUSE_LIVE_LEASE = "REFUSE_LIVE_LEASE"
    REFUSE_PROCESS_ALIVE = "REFUSE_PROCESS_ALIVE"
    PENDING = "PENDING"


class LeaseEvent(StrEnum):
    """What happened to a lease; only a change of ownership raises the epoch."""

    GRANT = "GRANT"
    TRANSFER = "TRANSFER"
    RECLAIM = "RECLAIM"
    RENEW = "RENEW"


class EpochVerdict(StrEnum):
    OK = "OK"
    OK_WITH_WARNING = "OK_WITH_WARNING"
    STALE = "STALE"
    FUTURE = "FUTURE"
    MISSING = "MISSING"


@dataclass(frozen=True)
class ProcessFingerprint:
    """What was recorded about the holder's process when the lease was granted."""

    host_id: str
    pid: int
    start_time: str
    image_sha256: str | None = None
    cmdline_sha256: str | None = None


@dataclass(frozen=True)
class ProcessObservation:
    """What the reclaiming side observes now for ``pid`` on its own host; ``None`` fields mean the table could be read but the value is not available."""

    pid_exists: bool
    start_time: str | None = None
    image_sha256: str | None = None
    cmdline_sha256: str | None = None


@dataclass(frozen=True)
class ReclaimResult:
    decision: ReclaimDecision
    reason: str
    exit_path: str = ""


@dataclass(frozen=True)
class EpochResult:
    verdict: EpochVerdict
    reason: str

    @property
    def accepted(self) -> bool:
        return self.verdict in (EpochVerdict.OK, EpochVerdict.OK_WITH_WARNING)


def judge_process(recorded: ProcessFingerprint | None, observation: ProcessObservation | None, *, local_host_id: str) -> ProcessVerdict:
    """Decide whether the recorded holder process still exists; anything that cannot be established is ``UNKNOWN``."""

    if recorded is None or observation is None:
        return ProcessVerdict.UNKNOWN
    if not local_host_id or recorded.host_id != local_host_id:
        return ProcessVerdict.UNKNOWN
    if not observation.pid_exists:
        return ProcessVerdict.PROVEN_DEAD
    if observation.start_time is None:
        return ProcessVerdict.UNKNOWN
    if observation.start_time != recorded.start_time:
        return ProcessVerdict.PROVEN_DEAD  # the pid now belongs to a different process (reuse)
    if recorded.image_sha256 is None or recorded.cmdline_sha256 is None or observation.image_sha256 is None or observation.cmdline_sha256 is None:
        return ProcessVerdict.UNKNOWN
    if observation.image_sha256 == recorded.image_sha256 and observation.cmdline_sha256 == recorded.cmdline_sha256:
        return ProcessVerdict.ALIVE
    return ProcessVerdict.UNKNOWN  # same start time but a different image or command line: not proven either way


def lease_is_live(expires_at: datetime, now: datetime, grace_seconds: int = GRACE_SECONDS) -> bool:
    """A lease still counts as live until ``expires_at`` plus the grace period (ordinary clock skew between machines)."""

    return now < expires_at + timedelta(seconds=grace_seconds)


def decide_reclaim(*, lease_expires_at: datetime, now: datetime, process: ProcessVerdict, forced_by_decision: bool = False, grace_seconds: int = GRACE_SECONDS) -> ReclaimResult:
    """Whether a started Run may be reclaimed from its holder."""

    live = lease_is_live(lease_expires_at, now, grace_seconds)
    if process is ProcessVerdict.ALIVE:
        return ReclaimResult(ReclaimDecision.REFUSE_PROCESS_ALIVE, "the holder's process is still running")
    if process is ProcessVerdict.UNKNOWN:
        return ReclaimResult(ReclaimDecision.PENDING, "the holder's process cannot be established; an unknown process is never pre-empted",
                             "exit: the user signs a Decision that forces the reclaim and accepts the risk of pre-empting a process nobody could identify; until then nothing changes")
    if live and not forced_by_decision:
        return ReclaimResult(ReclaimDecision.REFUSE_LIVE_LEASE, "the lease has not expired (plus grace) and no decision forces the reclaim")
    return ReclaimResult(ReclaimDecision.ALLOW, "the holder's process is proven dead" + (" and a decision forces the reclaim" if live else " and the lease has expired"))


def next_epoch(current: int) -> int:
    """The epoch after a change of ownership (a grant, a transfer or a reclaim); a renewal does not use it (see ``epoch_after``)."""

    if type(current) is not int or current < 1:
        raise ValueError("epoch must be a positive integer")
    return current + 1


def epoch_after(current: int, event: LeaseEvent) -> int:
    """The epoch of a lease after ``event``: raised by a grant, a transfer or a reclaim, unchanged by a renewal."""

    if event is LeaseEvent.RENEW:
        if type(current) is not int or current < 1:
            raise ValueError("epoch must be a positive integer")
        return current
    return next_epoch(current)


def check_write_epoch(current: int, presented: int | None, *, compatibility_period: bool = True) -> EpochResult:
    """Whether a mutating call that presents ``presented`` may proceed against a lease whose epoch is ``current``."""

    if type(current) is not int or current < 1:
        raise ValueError("epoch must be a positive integer")
    if presented is None:
        if compatibility_period:
            return EpochResult(EpochVerdict.OK_WITH_WARNING, "no epoch presented; accepted only during the compatibility period")
        return EpochResult(EpochVerdict.MISSING, "a mutating call must present the lease epoch")
    if type(presented) is not int or presented < 1:
        return EpochResult(EpochVerdict.MISSING, "the presented epoch is not a positive integer")
    if presented < current:
        return EpochResult(EpochVerdict.STALE, f"epoch {presented} is older than the current epoch {current}: the lease was granted again since")
    if presented > current:
        return EpochResult(EpochVerdict.FUTURE, f"epoch {presented} is ahead of the current epoch {current}: it cannot have been granted")
    return EpochResult(EpochVerdict.OK, "epoch matches")
