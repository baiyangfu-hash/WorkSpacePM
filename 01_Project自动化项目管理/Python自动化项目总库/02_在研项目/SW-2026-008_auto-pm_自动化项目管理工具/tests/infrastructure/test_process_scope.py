"""TD-SW008-188: a gate abandoned after its time limit takes its child processes (and theirs) with it, and starts no new ones."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from auto_pm.application.core import evidence_collection_service as ecs
from auto_pm.infrastructure.process_scope import GateCancelledError, ProcessScope, run_in_scope

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
    done = run_in_scope([sys.executable, "-c", "print('héllo'); import sys; sys.stderr.write('e'); sys.exit(3)"], tmp_path, {}, 30)

    assert (done.returncode, done.stdout.strip(), done.stderr) == (3, "héllo", "e")


def test_a_timeout_kills_the_child_and_its_grandchild(tmp_path: Path) -> None:
    beat = tmp_path / "beat.txt"

    with pytest.raises(subprocess.TimeoutExpired):
        run_in_scope(_tree_command(beat), tmp_path, {}, 3)

    _wait_for(beat)
    assert _heartbeat_is_dead(beat)


def test_cancelling_the_scope_kills_the_running_tree_and_the_call_reports_cancelled(tmp_path: Path) -> None:
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
            run_in_scope([sys.executable, "-c", f"import pathlib; pathlib.Path({str(marker)!r}).write_text('x')"], tmp_path, {}, 30)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(30)

    assert len(errors) == 1 and isinstance(errors[0], GateCancelledError)
    assert not marker.exists()


def test_a_gate_that_runs_out_of_time_kills_its_children_through_the_real_supervisor(tmp_path: Path) -> None:
    beat = tmp_path / "beat.txt"
    seen: list[BaseException] = []

    def work() -> tuple[str, int | None]:
        try:
            run_in_scope(_tree_command(beat), tmp_path, {}, 120)
        except BaseException as error:
            seen.append(error)
            raise
        return "unreachable", 0

    with pytest.raises(ecs._PlcGateTimeoutError):
        ecs._run_bounded(work, 3)

    assert _heartbeat_is_dead(beat)
    deadline = time.monotonic() + 30
    while not seen and time.monotonic() < deadline:
        time.sleep(0.05)
    assert seen and isinstance(seen[0], GateCancelledError)


class _FakeProcess:
    pid = 4242

    def __init__(self) -> None:
        self.killed = False

    def kill(self) -> None:
        self.killed = True


def test_a_taskkill_that_hangs_does_not_escape_and_the_direct_child_is_still_killed(monkeypatch: pytest.MonkeyPatch) -> None:
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
