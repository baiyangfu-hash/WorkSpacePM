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

Start times are compared in one canonical form, never as raw text: a decimal tick count (the platform's own process start counter) or a
timezone-aware ISO-8601 timestamp. Two start times of different kinds, an unparseable one, or two timestamps that agree at the coarser of their
two precisions but differ at the finer one prove nothing: the verdict is ``UNKNOWN``, never ``PROVEN_DEAD``. Every ``datetime`` passed in must be
timezone-aware.

Nothing here edits ``expires_at``, returns a lease token, or runs a process probe: callers pass in the facts they observed. The only look at a
token is ``lease_is_held``, which reads nothing but its fence prefix (``RELEASED:`` for a terminal Run, ``PARKED:`` for a parked Mission, TD-071).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final

GRACE_SECONDS: Final = 120
MAX_TICK_DIGITS: Final = 30  # a 64-bit platform tick count has at most 20 digits; a longer all-digit value is malformed, never a number worth converting


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
    same_start = _same_start_time(recorded.start_time, observation.start_time)
    if same_start is None:
        return ProcessVerdict.UNKNOWN  # the two start times cannot be compared: not proof of anything
    if not same_start:
        return ProcessVerdict.PROVEN_DEAD  # the pid now belongs to a different process (reuse)
    if recorded.image_sha256 is None or recorded.cmdline_sha256 is None or observation.image_sha256 is None or observation.cmdline_sha256 is None:
        return ProcessVerdict.UNKNOWN
    if observation.image_sha256 == recorded.image_sha256 and observation.cmdline_sha256 == recorded.cmdline_sha256:
        return ProcessVerdict.ALIVE
    return ProcessVerdict.UNKNOWN  # same start time but a different image or command line: not proven either way


def _canonical_start(value: str) -> int | datetime | None:
    """A decimal tick count, a timezone-aware timestamp in UTC, or ``None`` when ``value`` is neither."""

    text = value.strip()
    if text.isascii() and text.isdigit():
        if len(text) > MAX_TICK_DIGITS:
            return None  # also keeps ``int()`` away from the interpreter's integer-conversion limit (4300 digits), which would raise instead of giving UNKNOWN
        return int(text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _same_start_time(recorded: str, observed: str) -> bool | None:
    """``True`` or ``False`` when the two start times can be compared; ``None`` when they cannot."""

    left, right = _canonical_start(recorded), _canonical_start(observed)
    if left is None or right is None:
        return None
    if isinstance(left, int) and isinstance(right, int):
        return left == right
    if not isinstance(left, datetime) or not isinstance(right, datetime):
        return None  # a tick count and a timestamp are different clocks
    if left == right:
        return True
    coarse = timedelta(seconds=1) if left.microsecond == 0 or right.microsecond == 0 else timedelta(microseconds=1)
    if coarse > timedelta(microseconds=1) and abs(left - right) < coarse:
        return None  # equal at the coarser precision: the difference may be precision loss, not another process
    return False


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be a timezone-aware datetime")


def lease_is_live(expires_at: datetime, now: datetime, grace_seconds: int = GRACE_SECONDS) -> bool:
    """A lease still counts as live until ``expires_at`` plus the grace period (ordinary clock skew between machines)."""

    _require_aware(expires_at, "expires_at")
    _require_aware(now, "now")
    return now < expires_at + timedelta(seconds=grace_seconds)


RELEASED_TOKEN_PREFIX: Final = "RELEASED:"
PARKED_TOKEN_PREFIX: Final = "PARKED:"
FENCED_TOKEN_PREFIXES: Final = (RELEASED_TOKEN_PREFIX, PARKED_TOKEN_PREFIX)


def lease_token_is_fenced(lease_token: str) -> bool:
    """A released (terminal Run) or parked (TD-071) lease row keeps its audit row but no longer has a holder."""

    return lease_token.startswith(FENCED_TOKEN_PREFIXES)


def lease_is_held(*, lease_token: str, expires_at: datetime, now: datetime, grace_seconds: int = GRACE_SECONDS) -> bool:
    """The one test for "somebody holds this lease" (TD-071): not fenced, and still live including the grace period.

    A parked Mission's lease is fenced with ``PARKED:`` and is never held, whatever its ``expires_at`` says.
    """

    return not lease_token_is_fenced(lease_token) and lease_is_live(expires_at, now, grace_seconds)


def decide_reclaim(*, lease_expires_at: datetime, now: datetime, process: ProcessVerdict, forced_by_decision: bool = False,
                   unknown_risk_accepted_by_decision: bool = False, grace_seconds: int = GRACE_SECONDS) -> ReclaimResult:
    """Whether a started Run may be reclaimed from its holder.

    ``forced_by_decision`` lets a Decision reclaim a live lease from a holder proven dead; it never touches an unknown holder.
    ``unknown_risk_accepted_by_decision`` is the separate, explicit exit of a PENDING reclaim: a Decision that accepts the
    risk of pre-empting a holder nobody could identify. It never overrides ``ALIVE``.
    """

    live = lease_is_live(lease_expires_at, now, grace_seconds)
    if process is ProcessVerdict.ALIVE:
        return ReclaimResult(ReclaimDecision.REFUSE_PROCESS_ALIVE, "the holder's process is still running")
    if process is ProcessVerdict.UNKNOWN:
        if unknown_risk_accepted_by_decision:
            return ReclaimResult(ReclaimDecision.ALLOW, "the holder's process cannot be established and a decision accepts the risk of pre-empting it")
        return ReclaimResult(ReclaimDecision.PENDING, "the holder's process cannot be established; an unknown process is never pre-empted",
                             "exit: the user signs a Decision that accepts the risk (unknown_risk_accepted_by_decision) of pre-empting a process nobody could identify; until then nothing changes")
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
