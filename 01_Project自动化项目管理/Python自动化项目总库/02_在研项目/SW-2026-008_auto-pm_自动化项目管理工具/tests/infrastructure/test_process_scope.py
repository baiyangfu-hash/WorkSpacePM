"""TD-SW008-188: a gate abandoned after its time limit takes its child processes (and theirs) with it, and starts no new ones."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from auto_pm.application.core import evidence_collection_service as ecs
from auto_pm.infrastructure.process_scope import (
    GateAbandonedError,
    GateCancelledError,
    ProcessScope,
    run_in_scope,
)

# The child starts a grandchild that touches a heartbeat file every 50 ms, then waits; the heartbeat stops only when the whole tree is gone.
_GRANDCHILD = "import pathlib, sys, time\nbeat = pathlib.Path(sys.argv[1])\nwhile True:\n    beat.write_text(str(time.time()))\n    time.sleep(0.05)\n"
_CHILD = (
    "import subprocess, sys, time\n"
    "subprocess.Popen([sys.executable, '-c', sys.argv[2], sys.argv[1]])\n"
    "time.sleep(120)\n"
)


def _tree_command(beat: Path) -> list[str]:
    return [sys.executable, "-c", _CHILD, str(beat), _GRANDCHILD]


def _wait_for(path: Path, seconds: float = 20.0) -> None:
    deadline = time.monotonic() + seconds
    while not path.exists():
        assert time.monotonic() < deadline, f"{path.name} never appeared"
        time.sleep(0.05)


def _heartbeat_is_dead(path: Path) -> bool:
    """True once the heartbeat file has not been rewritten for a full second."""

    last = path.read_text(encoding="utf-8")
    time.sleep(1.0)
    return path.read_text(encoding="utf-8") == last


def test_without_a_scope_the_runner_behaves_like_subprocess_run(tmp_path: Path) -> None:
    # the child writes UTF-8 whatever the console code page is (Windows runners default to cp1252); the runner decodes UTF-8
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    done = run_in_scope(
        [sys.executable, "-c", "print('héllo'); import sys; sys.stderr.write('e'); sys.exit(3)"],
        tmp_path,
        env,
        30,
    )

    assert (done.returncode, done.stdout.strip(), done.stderr) == (3, "héllo", "e")


def test_a_timeout_kills_the_child_and_its_grandchild(tmp_path: Path) -> None:
    beat = tmp_path / "beat.txt"

    with pytest.raises(subprocess.TimeoutExpired):
        run_in_scope(_tree_command(beat), tmp_path, {}, 3)

    _wait_for(beat)
    assert _heartbeat_is_dead(beat)


def test_cancelling_the_scope_kills_the_running_tree_and_the_call_reports_cancelled(
    tmp_path: Path,
) -> None:
    beat = tmp_path / "beat.txt"
    scope = ProcessScope()
    outcome: list[BaseException] = []

    def worker() -> None:
        scope.enter()
        try:
            run_in_scope(_tree_command(beat), tmp_path, {}, 120)
        except BaseException as error:  # collected for the assertion below
            outcome.append(error)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    _wait_for(beat)

    assert scope.cancel() == 1
    thread.join(30)

    assert not thread.is_alive()
    assert len(outcome) == 1 and isinstance(outcome[0], GateCancelledError)
    assert _heartbeat_is_dead(beat)


def test_after_the_cancel_no_new_child_is_started(tmp_path: Path) -> None:
    marker = tmp_path / "started.txt"
    scope = ProcessScope()
    scope.cancel()
    errors: list[BaseException] = []

    def worker() -> None:
        scope.enter()
        try:
            run_in_scope(
                [
                    sys.executable,
                    "-c",
                    f"import pathlib; pathlib.Path({str(marker)!r}).write_text('x')",
                ],
                tmp_path,
                {},
                30,
            )
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(30)

    assert len(errors) == 1 and isinstance(errors[0], GateCancelledError)
    assert not marker.exists()


def test_a_cancel_between_the_child_start_and_its_registration_still_kills_the_whole_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TD-SW008-251: the race branch of ``register`` -- ``cancel`` ran after the child started but before it was registered.

    ``cancel`` only kills the children it already knows, so this child would be missed.  ``register`` has to notice the cancel, kill the
    child's tree itself and refuse the call; otherwise the tree would run on for as long as it likes.
    """

    from auto_pm.infrastructure import process_scope as module

    beat = tmp_path / "beat.txt"
    scope = ProcessScope()
    real_start = module._start
    started: list[subprocess.Popen[str]] = []

    def start_then_cancel(args: list[str], cwd: Path, env: object) -> subprocess.Popen[str]:
        process = real_start(args, cwd, env)  # type: ignore[arg-type]
        started.append(process)
        _wait_for(
            beat
        )  # the grandchild is running, so there is a whole tree to kill (and a heartbeat that can stop)
        assert scope.cancel() == 0  # the child is not registered yet, so the cancel cannot see it
        return process

    monkeypatch.setattr(module, "_start", start_then_cancel)
    errors: list[BaseException] = []

    def worker() -> None:
        scope.enter()
        try:
            run_in_scope(_tree_command(beat), tmp_path, {}, 120)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(60)

    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], GateCancelledError)
    assert (
        len(started) == 1 and started[0].wait(timeout=30) is not None
    )  # the direct child is gone, not left running
    assert _heartbeat_is_dead(
        beat
    )  # the grandchild was alive before the cancel; it has to stop with the tree, not be left running


def test_a_gate_that_runs_out_of_time_kills_its_children_through_the_real_supervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the time limit the whole tree is dead and the worker thread has ended with one of the two abandon errors.

    Which error the worker sees first depends on scheduling: the scope's cancel makes a worker waiting on the killed child raise
    ``GateCancelledError``, while ``reclaim_thread`` injects ``GateAbandonedError`` once the half-second settle window is over.  On a loaded
    Windows runner the injection sometimes wins (CI of integration batch four).  Both are correct for the product (``_run_bounded`` treats
    them alike, and the tree is killed either way), so the type is not what this test pins.  What it does pin: the direct child was
    killed, the grandchild's heartbeat stopped, and the worker ended with one of the two.
    """

    from auto_pm.infrastructure import process_scope as module

    beat = tmp_path / "beat.txt"
    seen: list[BaseException] = []
    started: list[subprocess.Popen[str]] = []
    real_start = module._start

    def recording_start(args: list[str], cwd: Path, env: object) -> subprocess.Popen[str]:
        process = real_start(args, cwd, env)  # type: ignore[arg-type]
        started.append(process)
        return process

    monkeypatch.setattr(module, "_start", recording_start)

    def work() -> tuple[str, int | None]:
        try:
            run_in_scope(_tree_command(beat), tmp_path, {}, 120)
        except BaseException as error:
            seen.append(error)
            raise
        return "unreachable", 0

    with pytest.raises(ecs._PlcGateTimeoutError):
        ecs._run_bounded(work, 3)

    assert (
        len(started) == 1 and beat.exists()
    )  # one tree was started and its grandchild really ran before the limit
    assert started[0].wait(timeout=30) is not None  # the direct child was killed, not left running
    assert _heartbeat_is_dead(beat)  # and so was the grandchild
    deadline = time.monotonic() + 30
    while not seen and time.monotonic() < deadline:
        time.sleep(0.05)
    assert seen and isinstance(seen[0], (GateCancelledError, GateAbandonedError))


class _FakeProcess:
    pid = 4242

    def __init__(self) -> None:
        self.killed = False

    def kill(self) -> None:
        self.killed = True


def test_a_taskkill_that_hangs_does_not_escape_and_the_direct_child_is_still_killed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # reviewer finding (reviews/457): on Windows a stuck taskkill raised TimeoutExpired out of the cleanup, hiding the gate's own timeout
    # error and skipping the kill; both the hang and a failure to start taskkill must be absorbed and fall back to killing the child
    from auto_pm.infrastructure import process_scope as module

    monkeypatch.setattr(module, "_WINDOWS", True)

    def hang(command: list[str], **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(command, 30)

    monkeypatch.setattr(subprocess, "run", hang)
    stuck = _FakeProcess()
    module.kill_process_tree(stuck)  # type: ignore[arg-type]

    assert stuck.killed

    def missing(command: list[str], **_kwargs: object) -> object:
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(subprocess, "run", missing)
    absent = _FakeProcess()
    module.kill_process_tree(absent)  # type: ignore[arg-type]

    assert absent.killed
