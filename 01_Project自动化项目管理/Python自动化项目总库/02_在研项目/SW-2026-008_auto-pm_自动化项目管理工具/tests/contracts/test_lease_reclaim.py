"""V04-R1 card 1: the lease reclaim and write-epoch contract (pure functions; no store, no process probe)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from auto_pm.contracts.lease_reclaim import (
    GRACE_SECONDS,
    EpochVerdict,
    ProcessFingerprint,
    ProcessObservation,
    ProcessVerdict,
    ReclaimDecision,
    check_write_epoch,
    decide_reclaim,
    judge_process,
    lease_is_live,
    next_epoch,
)

HOST = "baiyang-laptop"
NOW = datetime(2026, 10, 16, 12, 0, 0, tzinfo=UTC)
FP = ProcessFingerprint(host_id=HOST, pid=4242, start_time="2026-10-16T10:00:00Z", image_sha256="a" * 64, cmdline_sha256="b" * 64)
SAME = ProcessObservation(pid_exists=True, start_time=FP.start_time, image_sha256=FP.image_sha256, cmdline_sha256=FP.cmdline_sha256)


def test_a_process_with_the_recorded_start_time_image_and_command_line_is_alive() -> None:
    assert judge_process(FP, SAME, local_host_id=HOST) is ProcessVerdict.ALIVE


def test_a_missing_pid_is_proven_dead() -> None:
    assert judge_process(FP, ProcessObservation(pid_exists=False), local_host_id=HOST) is ProcessVerdict.PROVEN_DEAD


def test_a_reused_pid_with_another_start_time_is_proven_dead() -> None:
    reused = ProcessObservation(pid_exists=True, start_time="2026-10-16T11:30:00Z", image_sha256="c" * 64, cmdline_sha256="d" * 64)
    assert judge_process(FP, reused, local_host_id=HOST) is ProcessVerdict.PROVEN_DEAD


def test_another_host_no_fingerprint_or_no_observation_is_unknown() -> None:
    assert judge_process(FP, SAME, local_host_id="colleague-pc") is ProcessVerdict.UNKNOWN
    assert judge_process(None, SAME, local_host_id=HOST) is ProcessVerdict.UNKNOWN
    assert judge_process(FP, None, local_host_id=HOST) is ProcessVerdict.UNKNOWN
    assert judge_process(FP, SAME, local_host_id="") is ProcessVerdict.UNKNOWN


def test_the_same_start_time_with_an_unreadable_or_different_image_is_unknown_not_dead() -> None:
    unreadable = ProcessObservation(pid_exists=True, start_time=FP.start_time)
    other_image = ProcessObservation(pid_exists=True, start_time=FP.start_time, image_sha256="e" * 64, cmdline_sha256=FP.cmdline_sha256)
    no_start = ProcessObservation(pid_exists=True)
    assert judge_process(FP, unreadable, local_host_id=HOST) is ProcessVerdict.UNKNOWN
    assert judge_process(FP, other_image, local_host_id=HOST) is ProcessVerdict.UNKNOWN
    assert judge_process(FP, no_start, local_host_id=HOST) is ProcessVerdict.UNKNOWN
    partial = ProcessFingerprint(host_id=HOST, pid=1, start_time=FP.start_time)
    assert judge_process(partial, SAME, local_host_id=HOST) is ProcessVerdict.UNKNOWN
    assert judge_process(partial, unreadable, local_host_id=HOST) is ProcessVerdict.UNKNOWN  # None == None must not count as a match


def test_a_lease_is_live_until_it_has_expired_plus_the_grace_period() -> None:
    expires = NOW - timedelta(seconds=GRACE_SECONDS - 1)
    assert lease_is_live(expires, NOW) is True
    assert lease_is_live(NOW - timedelta(seconds=GRACE_SECONDS), NOW) is False
    assert lease_is_live(NOW + timedelta(minutes=5), NOW) is True


def test_an_expired_lease_with_a_dead_holder_is_reclaimed() -> None:
    result = decide_reclaim(lease_expires_at=NOW - timedelta(minutes=10), now=NOW, process=ProcessVerdict.PROVEN_DEAD)
    assert result.decision is ReclaimDecision.ALLOW


def test_an_expired_lease_with_a_living_holder_is_refused() -> None:
    result = decide_reclaim(lease_expires_at=NOW - timedelta(minutes=10), now=NOW, process=ProcessVerdict.ALIVE)
    assert result.decision is ReclaimDecision.REFUSE_PROCESS_ALIVE


def test_an_expired_lease_with_an_unknown_holder_stays_pending() -> None:
    result = decide_reclaim(lease_expires_at=NOW - timedelta(minutes=10), now=NOW, process=ProcessVerdict.UNKNOWN)
    assert result.decision is ReclaimDecision.PENDING


def test_a_live_lease_is_refused_even_when_the_holder_is_dead_unless_a_decision_forces_it() -> None:
    expires = NOW + timedelta(minutes=10)
    assert decide_reclaim(lease_expires_at=expires, now=NOW, process=ProcessVerdict.PROVEN_DEAD).decision is ReclaimDecision.REFUSE_LIVE_LEASE
    forced = decide_reclaim(lease_expires_at=expires, now=NOW, process=ProcessVerdict.PROVEN_DEAD, forced_by_decision=True)
    assert forced.decision is ReclaimDecision.ALLOW and "decision" in forced.reason


def test_a_decision_never_forces_a_reclaim_from_a_living_or_unknown_holder() -> None:
    expires = NOW + timedelta(minutes=10)
    assert decide_reclaim(lease_expires_at=expires, now=NOW, process=ProcessVerdict.ALIVE, forced_by_decision=True).decision is ReclaimDecision.REFUSE_PROCESS_ALIVE
    assert decide_reclaim(lease_expires_at=expires, now=NOW, process=ProcessVerdict.UNKNOWN, forced_by_decision=True).decision is ReclaimDecision.PENDING


def test_the_grace_period_keeps_a_just_expired_lease_live() -> None:
    expires = NOW - timedelta(seconds=30)
    assert decide_reclaim(lease_expires_at=expires, now=NOW, process=ProcessVerdict.PROVEN_DEAD).decision is ReclaimDecision.REFUSE_LIVE_LEASE
    assert decide_reclaim(lease_expires_at=expires, now=NOW, process=ProcessVerdict.PROVEN_DEAD, grace_seconds=0).decision is ReclaimDecision.ALLOW


def test_the_next_epoch_is_exactly_one_more_and_bad_values_are_rejected() -> None:
    assert next_epoch(1) == 2 and next_epoch(41) == 42
    for bad in (0, -1):
        with pytest.raises(ValueError):
            next_epoch(bad)
    with pytest.raises(ValueError):
        next_epoch(True)


def test_a_write_with_the_current_epoch_is_accepted() -> None:
    result = check_write_epoch(3, 3)
    assert result.verdict is EpochVerdict.OK and result.accepted


def test_a_write_with_an_older_epoch_is_refused_as_stale() -> None:
    result = check_write_epoch(3, 2)
    assert result.verdict is EpochVerdict.STALE and not result.accepted and "older" in result.reason


def test_a_write_with_an_epoch_ahead_of_the_current_one_is_refused() -> None:
    result = check_write_epoch(3, 4)
    assert result.verdict is EpochVerdict.FUTURE and not result.accepted


def test_a_write_without_an_epoch_is_accepted_with_a_warning_only_in_the_compatibility_period() -> None:
    during = check_write_epoch(3, None)
    after = check_write_epoch(3, None, compatibility_period=False)
    assert during.verdict is EpochVerdict.OK_WITH_WARNING and during.accepted
    assert after.verdict is EpochVerdict.MISSING and not after.accepted


def test_a_non_positive_or_non_integer_presented_epoch_is_refused_in_every_period() -> None:
    for bad in (0, -5, True):
        assert not check_write_epoch(3, bad).accepted  # type: ignore[arg-type]
        assert not check_write_epoch(3, bad, compatibility_period=False).accepted  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        check_write_epoch(0, 1)
