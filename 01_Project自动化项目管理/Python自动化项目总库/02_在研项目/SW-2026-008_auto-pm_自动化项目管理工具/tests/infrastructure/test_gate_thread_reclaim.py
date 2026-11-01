"""TD-SW008-188 (remainder): a gate abandoned after its time limit has its thread stopped, not just forgotten.

Python cannot kill a thread, but it can raise an exception in one.  Pure-Python work ends at once; a thread stuck inside one C call (here: a
lock wait) cannot be reached, and must be counted and reported instead of silently dropped.  The Windows ``taskkill`` side is NOT covered
here (it needs a real Windows machine; see the PR text).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest

from auto_pm.application.core import evidence_collection_service as ecs
from auto_pm.infrastructure import process_scope
from auto_pm.infrastructure.process_scope import leaked_threads, reclaim_thread

_GATE_THREAD = "plc-quality-gate"


@pytest.fixture(autouse=True)
def _clean_leak_list() -> Iterator[None]:
    process_scope._LEAKED.clear()
    yield
    process_scope._LEAKED.clear()


def _gate_threads() -> list[threading.Thread]:
    return [
        thread
        for thread in threading.enumerate()
        if thread.name == _GATE_THREAD and thread.is_alive()
    ]


def _wait_until_gone(seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while _gate_threads() and time.monotonic() < deadline:
        time.sleep(0.02)
    return not _gate_threads()


def test_a_gate_stuck_in_a_pure_python_loop_is_stopped_when_it_times_out() -> None:
    started = threading.Event()

    def work() -> tuple[str, int | None]:
        started.set()
        counter = 0
        while True:  # never ends on its own
            counter += 1

    with pytest.raises(ecs._PlcGateTimeoutError) as caught:
        ecs._run_bounded(work, 0.5)

    assert started.is_set()
    assert "已中止" in str(caught.value)
    assert _wait_until_gone(), "the abandoned thread must really have ended"
    assert leaked_threads() == []


def test_a_loop_that_swallows_ordinary_exceptions_is_still_stopped() -> None:
    # the checker code has `except Exception` blocks ("the baseline run must never hide a current failure"): they must not eat the stop
    def work() -> tuple[str, int | None]:
        while True:
            try:
                while (
                    True
                ):  # nearly all of the time is spent inside the try, so the stop lands there
                    sum(range(10))
            except Exception:
                pass

    with pytest.raises(ecs._PlcGateTimeoutError):
        ecs._run_bounded(work, 0.5)

    assert _wait_until_gone()
    assert leaked_threads() == []


def test_a_thread_stuck_in_a_c_call_is_counted_and_the_message_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(process_scope, "RECLAIM_GRACE_SECONDS", 0.3)
    blocker = threading.Event()

    def work() -> tuple[str, int | None]:
        blocker.wait()  # a lock wait: the interpreter cannot interrupt it
        return "late", 0

    try:
        with pytest.raises(ecs._PlcGateTimeoutError) as caught:
            ecs._run_bounded(work, 0.3)

        assert "无法中断" in str(caught.value) and "累计遗留 1 个" in str(caught.value)
        assert len(leaked_threads()) == 1
    finally:
        blocker.set()  # the call returns; the pending stop is delivered and the thread ends
    assert _wait_until_gone()
    assert leaked_threads() == []  # ended threads drop out of the list


def test_reclaiming_a_thread_that_already_ended_is_a_clean_true() -> None:
    thread = threading.Thread(target=lambda: None)
    thread.start()
    thread.join()

    assert reclaim_thread(thread) is True
    assert leaked_threads() == []


def test_stopping_one_gate_does_not_touch_another_thread() -> None:
    bystander_stop = threading.Event()
    bystander_hit: list[BaseException] = []

    def bystander() -> None:
        try:
            while not bystander_stop.is_set():
                time.sleep(0.01)
        except BaseException as error:
            bystander_hit.append(error)

    other = threading.Thread(target=bystander, daemon=True)
    other.start()

    def work() -> tuple[str, int | None]:
        while True:
            pass

    try:
        with pytest.raises(ecs._PlcGateTimeoutError):
            ecs._run_bounded(work, 0.3)
        assert _wait_until_gone()
        time.sleep(0.2)
        assert other.is_alive() and bystander_hit == []
    finally:
        bystander_stop.set()
        other.join(5)


def test_a_gate_that_finishes_in_time_is_left_alone() -> None:
    assert ecs._run_bounded(lambda: ("ok", 0), 5) == ("ok", 0)
    assert leaked_threads() == []
