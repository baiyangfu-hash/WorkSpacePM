"""run_until_done_or_stopped: the command's own exit code, or a stop (125) / time-limit (124) kill."""

from __future__ import annotations

import sys
import threading
import time

from auto_pm.application.core.bounded_command import run_until_done_or_stopped

_SLEEP = [sys.executable, "-c", "import time; time.sleep(300)"]


def test_the_commands_own_exit_code_is_returned_untouched() -> None:
    outcome = run_until_done_or_stopped(
        [sys.executable, "-c", "import sys; sys.exit(7)"], {}, 60, threading.Event()
    )
    assert (outcome.returncode, outcome.stopped_by) == (7, "")


def test_a_command_that_outlives_its_time_limit_is_killed() -> None:
    started = time.monotonic()
    outcome = run_until_done_or_stopped(_SLEEP, {}, 1, threading.Event())
    assert (outcome.returncode, outcome.stopped_by) == (124, "timeout")
    assert time.monotonic() - started < 30


def test_a_stop_request_kills_the_command_and_exits_125() -> None:
    stop = threading.Event()
    threading.Timer(0.5, stop.set).start()
    started = time.monotonic()
    outcome = run_until_done_or_stopped(_SLEEP, {}, 600, stop)
    assert (outcome.returncode, outcome.stopped_by) == (125, "stop")
    assert time.monotonic() - started < 30
