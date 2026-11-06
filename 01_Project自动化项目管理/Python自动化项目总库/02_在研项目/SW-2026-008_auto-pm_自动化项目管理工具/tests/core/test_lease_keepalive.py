"""LeaseKeepAlive: renew while a long command runs, never extend the cap, never swallow a refused first renewal."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pytest

from auto_pm.application.core.lease_keepalive import LeaseKeepAlive, LeaseKeepAliveError
from tests.core.test_continuity_execution_service import Clock, _services, _start


def _keepalive(service: object, **changes: object) -> LeaseKeepAlive:
    values: dict[str, object] = {
        "run_id": "RUN-001",
        "owner_id": "agent-a",
        "token": "lease-secret",
        "lease_seconds": 900,
        "interval_seconds": 0.02,
    }
    values.update(changes)
    return LeaseKeepAlive(service, **values)  # type: ignore[arg-type]


def _wait_for(predicate: object, timeout: float = 60.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if predicate():  # type: ignore[operator]
            return
        time.sleep(0.01)
    raise AssertionError("condition not reached in time")


def test_the_lease_is_renewed_repeatedly_while_the_block_runs(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=900)
    before = service.current_lease("RUN-001").version
    with _keepalive(service) as keepalive:
        _wait_for(lambda: keepalive.renewals >= 3)
    assert service.current_lease("RUN-001").version >= before + 3
    assert keepalive.error == ""


def test_renewal_stops_when_the_block_ends(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=900)
    with _keepalive(service) as keepalive:
        _wait_for(lambda: keepalive.renewals >= 2)
    version = service.current_lease("RUN-001").version
    time.sleep(0.2)
    assert service.current_lease("RUN-001").version == version


def test_a_failed_first_renewal_stops_a_strict_keepalive_before_the_command(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=900)
    entered = False
    with pytest.raises(LeaseKeepAliveError, match="命令没有启动"):
        with _keepalive(service, token="wrong-secret"):
            entered = True
    assert not entered


def test_a_non_strict_keepalive_records_the_failure_and_lets_the_block_run(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=900)
    with _keepalive(service, token="wrong-secret", strict=False) as keepalive:
        assert keepalive.error
        assert keepalive.renewals == 0


def test_a_refusal_in_the_middle_ends_the_loop_and_is_reported_not_raised(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=900)
    with _keepalive(service) as keepalive:
        _wait_for(lambda: keepalive.renewals >= 1)
        clock.value += timedelta(hours=4)  # lease dead and far past the 3 h hold cap
        _wait_for(lambda: bool(keepalive.error))
    assert "过期" in keepalive.error or "上限" in keepalive.error


def test_a_transient_failure_does_not_end_the_keepalive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.continuity_execution_service import ContinuityExecutionError

    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=900)
    real = service.renew_lease
    calls = {"n": 0}

    def flaky(*args: object, **kwargs: object) -> object:
        calls["n"] += 1
        if 2 <= calls["n"] <= 3:  # the entry renewal (1) works; the next two attempts fail, then it recovers
            raise ContinuityExecutionError("lease version 冲突")
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(service, "renew_lease", flaky)
    monkeypatch.setattr("auto_pm.application.core.lease_keepalive.MAX_RETRY_SECONDS", 0.02)
    with _keepalive(service) as keepalive:
        _wait_for(lambda: keepalive.renewals >= 3)
    assert calls["n"] >= 5 and keepalive.error == ""


def test_the_keepalive_gives_up_only_when_the_lease_is_nearly_gone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.continuity_execution_service import ContinuityExecutionError

    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=900)
    real = service.renew_lease
    state = {"fail": False, "attempts": 0}

    def switchable(*args: object, **kwargs: object) -> object:
        if state["fail"]:
            state["attempts"] += 1
            raise ContinuityExecutionError("ledger busy")
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(service, "renew_lease", switchable)
    monkeypatch.setattr("auto_pm.application.core.lease_keepalive.MAX_RETRY_SECONDS", 0.02)
    gave_up: list[str] = []
    with _keepalive(service, on_give_up=lambda: gave_up.append("called")) as keepalive:
        _wait_for(lambda: keepalive.renewals >= 1)
        assert gave_up == []
        state["fail"] = True
        _wait_for(lambda: state["attempts"] >= 4)  # still plenty of lease: keeps retrying, no error yet
        assert keepalive.error == ""
        clock.value += timedelta(seconds=880)  # 20 s left: below the give-up floor
        _wait_for(lambda: bool(keepalive.error))
    assert keepalive.error == "ledger busy"
    assert gave_up == ["called"]


def test_the_machine_is_kept_awake_for_the_block_by_the_keepalive_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TD-SW008-160: a sleeping laptop suspends the keep-alive and the lease runs out.

    The request must be made, and released, by the thread that lives as long as the block (the OS ties it to the thread).
    """

    events: list[tuple[str, int]] = []

    @contextmanager
    def recording() -> Iterator[bool]:
        events.append(("on", threading.get_ident()))
        try:
            yield True
        finally:
            events.append(("off", threading.get_ident()))

    monkeypatch.setattr("auto_pm.application.core.lease_keepalive.keep_system_awake", recording)
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=900)
    with _keepalive(service) as keepalive:
        _wait_for(lambda: keepalive.renewals >= 2)
        assert [kind for kind, _ in events] == ["on"]
    assert [kind for kind, _ in events] == ["on", "off"]
    assert events[0][1] == events[1][1] != threading.get_ident()


def test_d31_a_longer_lease_is_never_shortened_by_the_keepalive(tmp_path: Path) -> None:
    """``pm verify`` wraps the Run's 30-minute lease in a 15-minute keep-alive; the lease must not drop to 15 minutes."""

    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=1800)
    before = service.current_lease("RUN-001")
    with _keepalive(service, lease_seconds=900):
        time.sleep(0.2)  # several 0.02 s intervals
    after = service.current_lease("RUN-001")
    assert after.expires_at >= before.expires_at
    assert after.version == before.version  # nothing was written at all
