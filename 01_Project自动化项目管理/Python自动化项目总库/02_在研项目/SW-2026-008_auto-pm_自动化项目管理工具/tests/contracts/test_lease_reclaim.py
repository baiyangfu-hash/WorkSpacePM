"""V04-R1 card 1: the lease reclaim and write-epoch contract (pure functions; no store, no process probe)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from auto_pm.contracts.lease_reclaim import (
    GRACE_SECONDS,
    EpochVerdict,
    LeaseEvent,
    ProcessFingerprint,
    ProcessObservation,
    ProcessVerdict,
    ReclaimDecision,
    check_write_epoch,
    decide_reclaim,
    epoch_after,
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
        assert not check_write_epoch(3, bad).accepted
        assert not check_write_epoch(3, bad, compatibility_period=False).accepted
    with pytest.raises(ValueError):
        check_write_epoch(0, 1)


def test_only_a_change_of_ownership_raises_the_epoch_and_a_renewal_never_does() -> None:
    assert epoch_after(3, LeaseEvent.GRANT) == 4
    assert epoch_after(3, LeaseEvent.TRANSFER) == 4
    assert epoch_after(3, LeaseEvent.RECLAIM) == 4
    assert epoch_after(3, LeaseEvent.RENEW) == 3
    with pytest.raises(ValueError):
        epoch_after(0, LeaseEvent.RENEW)
    with pytest.raises(ValueError):
        epoch_after(0, LeaseEvent.GRANT)


def test_an_in_flight_write_of_the_holder_is_not_refused_after_any_number_of_renewals() -> None:
    epoch = 3
    for _heartbeat in range(5):
        epoch = epoch_after(epoch, LeaseEvent.RENEW)
        assert check_write_epoch(epoch, 3, compatibility_period=False).accepted


def test_after_a_transfer_or_a_reclaim_the_former_holders_write_is_refused() -> None:
    for event in (LeaseEvent.TRANSFER, LeaseEvent.RECLAIM):
        epoch = epoch_after(3, event)
        refused = check_write_epoch(epoch, 3, compatibility_period=False)
        assert not refused.accepted and refused.verdict is EpochVerdict.STALE


def test_a_pending_reclaim_names_its_exit_and_the_other_decisions_do_not_need_one() -> None:
    pending = decide_reclaim(lease_expires_at=NOW - timedelta(minutes=10), now=NOW, process=ProcessVerdict.UNKNOWN)
    assert pending.decision is ReclaimDecision.PENDING and "Decision" in pending.exit_path and "risk" in pending.exit_path
    allowed = decide_reclaim(lease_expires_at=NOW - timedelta(minutes=10), now=NOW, process=ProcessVerdict.PROVEN_DEAD)
    assert allowed.exit_path == ""


def test_the_pending_exit_is_reachable_only_through_its_own_explicit_decision() -> None:
    expired = NOW - timedelta(minutes=10)
    assert decide_reclaim(lease_expires_at=expired, now=NOW, process=ProcessVerdict.UNKNOWN, forced_by_decision=True).decision is ReclaimDecision.PENDING
    accepted = decide_reclaim(lease_expires_at=expired, now=NOW, process=ProcessVerdict.UNKNOWN, unknown_risk_accepted_by_decision=True)
    assert accepted.decision is ReclaimDecision.ALLOW and "risk" in accepted.reason
    live = decide_reclaim(lease_expires_at=NOW + timedelta(minutes=10), now=NOW, process=ProcessVerdict.UNKNOWN, unknown_risk_accepted_by_decision=True)
    assert live.decision is ReclaimDecision.ALLOW
    alive = decide_reclaim(lease_expires_at=expired, now=NOW, process=ProcessVerdict.ALIVE, unknown_risk_accepted_by_decision=True, forced_by_decision=True)
    assert alive.decision is ReclaimDecision.REFUSE_PROCESS_ALIVE


def test_the_same_start_instant_written_two_ways_is_the_same_process() -> None:
    other_spelling = ProcessObservation(pid_exists=True, start_time="2026-10-16T10:00:00+00:00", image_sha256=FP.image_sha256, cmdline_sha256=FP.cmdline_sha256)
    other_zone = ProcessObservation(pid_exists=True, start_time="2026-10-16T12:00:00+02:00", image_sha256=FP.image_sha256, cmdline_sha256=FP.cmdline_sha256)
    assert judge_process(FP, other_spelling, local_host_id=HOST) is ProcessVerdict.ALIVE
    assert judge_process(FP, other_zone, local_host_id=HOST) is ProcessVerdict.ALIVE


def test_tick_counts_are_compared_as_integers() -> None:
    ticks = ProcessFingerprint(host_id=HOST, pid=4242, start_time="133000000000000000", image_sha256="a" * 64, cmdline_sha256="b" * 64)
    same = ProcessObservation(pid_exists=True, start_time=" 133000000000000000", image_sha256="a" * 64, cmdline_sha256="b" * 64)
    other = ProcessObservation(pid_exists=True, start_time="133000000000000001")
    assert judge_process(ticks, same, local_host_id=HOST) is ProcessVerdict.ALIVE
    assert judge_process(ticks, other, local_host_id=HOST) is ProcessVerdict.PROVEN_DEAD


def test_start_times_that_cannot_be_compared_are_unknown_never_dead() -> None:
    cases = (
        "not a time",  # unparseable
        "2026-10-16T10:00:00",  # no timezone
        "133000000000000000",  # a tick count against a recorded timestamp: different clocks
        "-5",  # not a tick count
        "",
    )
    for observed in cases:
        observation = ProcessObservation(pid_exists=True, start_time=observed, image_sha256=FP.image_sha256, cmdline_sha256=FP.cmdline_sha256)
        assert judge_process(FP, observation, local_host_id=HOST) is ProcessVerdict.UNKNOWN, observed


def test_an_oversized_numeric_start_time_is_unknown_and_never_raises() -> None:
    for digits in (31, 4301, 5000):
        observation = ProcessObservation(pid_exists=True, start_time="9" * digits, image_sha256=FP.image_sha256, cmdline_sha256=FP.cmdline_sha256)
        assert judge_process(FP, observation, local_host_id=HOST) is ProcessVerdict.UNKNOWN, digits
    ticks = ProcessFingerprint(host_id=HOST, pid=4242, start_time="9" * 5000, image_sha256="a" * 64, cmdline_sha256="b" * 64)
    assert judge_process(ticks, ProcessObservation(pid_exists=True, start_time="133000000000000000"), local_host_id=HOST) is ProcessVerdict.UNKNOWN
    limit = ProcessFingerprint(host_id=HOST, pid=4242, start_time="1" * 30, image_sha256="a" * 64, cmdline_sha256="b" * 64)
    assert judge_process(limit, ProcessObservation(pid_exists=True, start_time="1" * 30, image_sha256="a" * 64, cmdline_sha256="b" * 64), local_host_id=HOST) is ProcessVerdict.ALIVE


def test_a_difference_explained_by_precision_loss_is_unknown_but_a_real_difference_is_reuse() -> None:
    finer = ProcessObservation(pid_exists=True, start_time="2026-10-16T10:00:00.700000+00:00")
    earlier_rounding = ProcessObservation(pid_exists=True, start_time="2026-10-16T09:59:59.600000+00:00")
    a_second_later = ProcessObservation(pid_exists=True, start_time="2026-10-16T10:00:01.200000+00:00")
    assert judge_process(FP, finer, local_host_id=HOST) is ProcessVerdict.UNKNOWN
    assert judge_process(FP, earlier_rounding, local_host_id=HOST) is ProcessVerdict.UNKNOWN
    assert judge_process(FP, a_second_later, local_host_id=HOST) is ProcessVerdict.PROVEN_DEAD
    fine = ProcessFingerprint(host_id=HOST, pid=4242, start_time="2026-10-16T10:00:00.100000+00:00")
    assert judge_process(fine, ProcessObservation(pid_exists=True, start_time="2026-10-16T10:00:00.100001+00:00"), local_host_id=HOST) is ProcessVerdict.PROVEN_DEAD


def test_naive_datetimes_are_rejected_with_a_contract_error() -> None:
    naive = datetime(2026, 10, 16, 12, 0, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        lease_is_live(naive, NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        lease_is_live(NOW, naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        decide_reclaim(lease_expires_at=naive, now=NOW, process=ProcessVerdict.PROVEN_DEAD)
