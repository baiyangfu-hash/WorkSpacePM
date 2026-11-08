"""long-run core: the worker's final status, the guard's pause/resume trail, and real detached processes (11-03 laptop memory P1)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from auto_pm.infrastructure import long_run_core as core

PY = sys.executable


def _spec(run_dir: Path, argv: list[str], *, timeout: float = 60, cwd: Path | None = None) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "spec.json").write_text(
        json.dumps({"argv": argv, "cwd": str(cwd or run_dir), "timeout_seconds": timeout, "guard_poll_seconds": 0.2}), encoding="utf-8"
    )
    (run_dir / "status.json").write_text(json.dumps({"schema_version": core.SCHEMA, "name": run_dir.name, "state": "STARTING"}), encoding="utf-8")


# D-158: process start-up on a loaded Windows machine takes seconds to minutes.  The waits below are polls that return the moment the
# condition holds, so a generous ceiling costs nothing on a healthy machine and only stops a slow one from failing a correct run.
_STARTUP_CEILING = 300.0


def _guard_diagnostics(run_dir: Path) -> str:
    out = run_dir / "guard.out"
    return out.read_text(encoding="utf-8", errors="replace") if out.exists() else "(no guard.out yet)"


def _wait(predicate, seconds: float = 30.0) -> bool:  # type: ignore[no-untyped-def]
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.1)
    return False


# ------------------------------------------------------------------ worker
def test_the_worker_records_a_successful_command_with_the_log_hash_and_a_done_marker(tmp_path: Path) -> None:
    run_dir = tmp_path / "ok"
    _spec(run_dir, [PY, "-c", "print('hello from the job')"])

    code = core.worker_main(run_dir)

    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    log = (run_dir / "run.log").read_bytes()
    assert code == 0 and status["state"] == "DONE" and status["exit_code"] == 0
    assert b"hello from the job" in log
    assert status["log_sha256"] == hashlib.sha256(log).hexdigest() and status["log_bytes"] == len(log)
    assert (run_dir / "DONE").exists() and not (run_dir / "FAILED").exists()
    assert status["child_pid"] and status["worker_pid"] == os.getpid() and status["ended_at"] >= status["running_at"]
    assert (run_dir / "worker.pid").read_text(encoding="ascii") == str(os.getpid())


def test_the_worker_records_a_failing_command_as_failed_with_its_exit_code(tmp_path: Path) -> None:
    run_dir = tmp_path / "bad"
    _spec(run_dir, [PY, "-c", "import sys; sys.exit(3)"])

    code = core.worker_main(run_dir)

    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert code == 3 and status["state"] == "FAILED" and status["exit_code"] == 3
    assert (run_dir / "FAILED").exists() and not (run_dir / "DONE").exists()


def test_the_worker_kills_a_command_that_runs_past_its_timeout(tmp_path: Path) -> None:
    run_dir = tmp_path / "slow"
    _spec(run_dir, [PY, "-c", "import time; time.sleep(60)"], timeout=1)

    code = core.worker_main(run_dir)

    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert code == 124 and core.TIMEOUT_EXIT == 124 and status["state"] == "FAILED"  # 124 is what timeout(1) uses; the number is part of the record's meaning
    assert not core.pid_alive(status["child_pid"])


def test_the_worker_records_a_command_that_cannot_start(tmp_path: Path) -> None:
    run_dir = tmp_path / "missing"
    _spec(run_dir, ["definitely-not-a-program-xyz"])

    code = core.worker_main(run_dir)

    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert code == 127 and status["state"] == "FAILED"
    assert b"cannot start the command" in (run_dir / "run.log").read_bytes()


def test_a_stop_marker_makes_the_final_state_stopped(tmp_path: Path) -> None:
    run_dir = tmp_path / "stopped"
    _spec(run_dir, [PY, "-c", "import sys; sys.exit(9)"])
    (run_dir / "STOP").write_text("x", encoding="utf-8")

    core.worker_main(run_dir)

    assert json.loads((run_dir / "status.json").read_text(encoding="utf-8"))["state"] == "STOPPED"


# ------------------------------------------------------------------ guard
class _World:
    """A fake clock and process table: readings come from a list, one per poll; markers can be dropped at a given poll."""

    def __init__(self, run_dir: Path, readings: list[float | None], *, end_after: int | None = None, resume_at: int | None = None) -> None:
        self.run_dir, self.readings, self.end_after, self.resume_at = run_dir, readings, end_after, resume_at
        self.now = 0.0
        self.polls = 0
        self.paused_calls: list[list[int]] = []
        self.resumed_calls: list[list[int]] = []
        self.awake: list[bool] = []
        self.tree_of: Callable[[int], list[int]] = lambda root: [root, root + 1]

    def read(self) -> float | None:
        value = self.readings[min(self.polls, len(self.readings) - 1)]
        return value

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        self.polls += 1
        if self.resume_at is not None and self.polls == self.resume_at:
            (self.run_dir / "RESUME").write_text("x", encoding="utf-8")
        if self.end_after is not None and self.polls >= self.end_after:
            (self.run_dir / "DONE").write_text("x", encoding="utf-8")

    def _pause(self, pids: list[int]) -> int:
        self.paused_calls.append(list(pids))
        return len(pids)

    def _unpause(self, pids: list[int]) -> int:
        self.resumed_calls.append(list(pids))
        return len(pids)

    def run(self, **kwargs: float) -> None:
        core.guard_loop(
            self.run_dir,
            read_committed_gib=self.read,
            sleep=self.sleep,
            clock=lambda: self.now,
            tree=lambda root: self.tree_of(root),
            pause=self._pause,
            unpause=self._unpause,
            awake=self.awake.append,
            **kwargs,  # type: ignore[arg-type]
        )


def _guard_dir(tmp_path: Path, pid: int | None = 4242) -> Path:
    run_dir = tmp_path / "guarded"
    run_dir.mkdir()
    if pid is not None:
        (run_dir / "worker.pid").write_text(str(pid), encoding="ascii")
    return run_dir


def test_the_guard_pauses_the_worker_tree_at_the_limit_and_resumes_below_the_resume_level(tmp_path: Path) -> None:
    run_dir = _guard_dir(tmp_path)
    world = _World(run_dir, [10.0, 41.0, 41.0, 35.0, 30.0], end_after=6)

    world.run(limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000)

    guard = json.loads((run_dir / "guard.json").read_text(encoding="utf-8"))
    assert world.paused_calls == [[4242, 4243]] and world.resumed_calls == [[4242, 4243]]
    assert list(run_dir.glob("ALERT_*.txt")) and list(run_dir.glob("RESUMED_*.txt")) and not (run_dir / "PAUSED").exists()
    assert guard["peak_committed_gib"] == 41.0 and guard["samples"] >= 5 and len(guard["alerts"]) == 1
    assert "paused 2 processes" in guard["alerts"][0]
    assert world.awake[0] is True and world.awake[-1] is False  # keeps the machine awake while it watches, lets go at the end


def test_the_guard_pauses_only_once_while_paused_and_a_resume_file_forces_the_resume(tmp_path: Path) -> None:
    run_dir = _guard_dir(tmp_path)
    world = _World(run_dir, [45.0], end_after=6, resume_at=3)

    world.run(limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000)

    # the charge never fell, so only the RESUME file resumed it; the next reading (still hot) pauses it again
    assert len(world.paused_calls) >= 1 and len(world.resumed_calls) >= 1
    assert not (run_dir / "RESUME").exists()


def test_the_guard_never_leaves_the_job_frozen_when_it_goes_away(tmp_path: Path) -> None:
    run_dir = _guard_dir(tmp_path)
    world = _World(run_dir, [50.0])

    world.run(limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=100)  # ends by the time limit, still hot

    assert world.paused_calls and world.resumed_calls[-1] == world.paused_calls[-1]


def test_the_guard_does_nothing_without_a_worker_pid_and_survives_unreadable_memory(tmp_path: Path) -> None:
    run_dir = _guard_dir(tmp_path, pid=None)
    world = _World(run_dir, [None, 99.0], end_after=4)

    world.run(limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000)

    guard = json.loads((run_dir / "guard.json").read_text(encoding="utf-8"))
    assert world.paused_calls == [] and guard["samples"] >= 1 and guard["peak_committed_gib"] == 99.0 and guard["alerts"] == []


def test_the_guard_survives_an_unreadable_worker_pid_when_memory_is_hot_and_pauses_on_a_later_round(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard is most needed when the commit is over the limit: a worker.pid that cannot be read for a moment must not end the loop."""

    run_dir = _guard_dir(tmp_path)
    world = _World(run_dir, [45.0], end_after=8)
    real = Path.read_text

    def read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name == "worker.pid" and world.polls < 2:
            raise PermissionError(13, "denied")  # held by someone else for the first rounds (every retry fails)
        return real(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", read_text)
    fake_sleep = world.sleep

    def sleep_over_a_second_boundary(seconds: float) -> None:
        # ALERT_<epoch seconds>.txt: the alert of the unreadable round and the alert of the pause (a later round) are 20 s apart in real life;
        # the fake clock makes the rounds instant, so on a fast machine both landed in the same second and the pause alert replaced the other.
        if world.polls < 2:
            time.sleep(1.05)
        fake_sleep(seconds)

    world.sleep = sleep_over_a_second_boundary  # type: ignore[method-assign]

    world.run(limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000)  # must not raise

    guard = json.loads(real(run_dir / "guard.json", encoding="utf-8"))
    assert world.polls >= 8  # it kept looping to the end instead of dying on the first hot round
    assert world.paused_calls and world.paused_calls[0] == [4242, 4243]  # a later round found the tree and paused it
    assert world.resumed_calls  # and never leaves it frozen
    errors = [alert for alert in guard["alerts"] if "worker.pid" in alert]
    assert len(errors) == 1 and "下一轮重试" in errors[0]  # noted once, not once per round
    assert guard["worker_pid_error"]
    alert_files = list(run_dir.glob("ALERT_*.txt"))
    assert any("worker.pid" in path.read_text(encoding="utf-8") for path in alert_files)  # an ALERT file somebody can see, like for a pause


def test_the_guard_keeps_noting_nothing_new_while_worker_pid_stays_unreadable_and_does_not_pause(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = _guard_dir(tmp_path)
    world = _World(run_dir, [45.0], end_after=5)
    real = Path.read_text

    def read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name == "worker.pid":
            raise PermissionError(13, "denied")
        return real(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", read_text)

    world.run(limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000)

    guard = json.loads(real(run_dir / "guard.json", encoding="utf-8"))
    assert world.paused_calls == [] and world.polls >= 5 and guard["samples"] >= 5
    assert len([alert for alert in guard["alerts"] if "worker.pid" in alert]) == 1
    worker_pid_alerts = [path for path in run_dir.glob("ALERT_*.txt") if "worker.pid" in path.read_text(encoding="utf-8")]
    assert len(worker_pid_alerts) == 1 and "没有挂起" in worker_pid_alerts[0].read_text(encoding="utf-8")  # one file for one message, not one per round


def test_the_guard_looks_once_even_when_the_job_has_already_ended_but_never_pauses_it(tmp_path: Path) -> None:
    run_dir = _guard_dir(tmp_path)
    (run_dir / "FAILED").write_text("x", encoding="utf-8")
    world = _World(run_dir, [99.0])

    world.run(limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000)

    guard = json.loads((run_dir / "guard.json").read_text(encoding="utf-8"))
    assert world.paused_calls == [] and world.polls == 0  # no pause on a finished job, no waiting
    assert guard["samples"] == 1 and guard["peak_committed_gib"] == 99.0  # but the record shows that the guard looked


def test_a_short_job_that_ends_before_the_guard_starts_still_leaves_a_sample(tmp_path: Path) -> None:
    """11-03 Windows run: a 1.5 s job ended before the guard process was up; the guard saw DONE first and left samples=0 (evidence refused)."""

    run_dir = _guard_dir(tmp_path)
    (run_dir / "DONE").write_text("x", encoding="utf-8")
    world = _World(run_dir, [12.5])

    world.run(limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000)

    guard = json.loads((run_dir / "guard.json").read_text(encoding="utf-8"))
    assert guard["samples"] == 1 and guard["last_committed_gib"] == 12.5 and world.awake[-1] is False


def test_the_first_sample_is_written_before_the_slow_process_listing_runs(tmp_path: Path) -> None:
    run_dir = _guard_dir(tmp_path)
    world = _World(run_dir, [10.0], end_after=2)
    seen: list[int] = []

    def slow_unowned() -> float:
        seen.append(json.loads((run_dir / "guard.json").read_text(encoding="utf-8"))["samples"])
        return 17.5

    world.run(limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000, read_unowned_gib=slow_unowned)  # type: ignore[arg-type]

    assert seen and seen[0] == 1  # guard.json already said "1 sample" when the listing started


def test_a_dead_worker_is_neither_paused_nor_alerted_about_again_and_again(tmp_path: Path) -> None:
    run_dir = _guard_dir(tmp_path)
    world = _World(run_dir, [99.0], end_after=4)
    world.tree_of = lambda _root: []  # the worker pid no longer exists: no tree

    world.run(limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000)

    assert world.paused_calls == [] and not list(run_dir.glob("ALERT_*.txt"))


def test_the_guard_alerts_each_time_the_unowned_commit_grows_8_gib_over_the_start_and_does_not_pause(tmp_path: Path) -> None:
    run_dir = _guard_dir(tmp_path)
    world = _World(run_dir, [10.0], end_after=8)
    unowned = [17.5, 20.0, 25.4, 25.5, 33.6, 34.0, 41.6, 41.6]  # rise: 0, 2.5, 7.9, 8.0 (alert), 16.1 (alert), 16.5, 24.1 (alert)

    world.run(
        limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000,
        read_unowned_gib=lambda: unowned[min(world.polls, len(unowned) - 1)],  # type: ignore[arg-type]
    )

    guard = json.loads((run_dir / "guard.json").read_text(encoding="utf-8"))
    alerts = [text for text in guard["alerts"] if "unowned" in text]
    assert len(alerts) == 3 and "25.5 GiB" in alerts[0] and "33.6 GiB" in alerts[1] and "41.6 GiB" in alerts[2]
    assert len(list(run_dir.glob("ALERT_UNOWNED_*.txt"))) >= 1
    assert guard["unowned_baseline_gib"] == 17.5 and guard["peak_unowned_gib"] == 41.6
    assert world.paused_calls == []  # an alert only: the unowned growth is not something suspending the job would cure


def test_the_guard_keeps_quiet_when_the_unowned_commit_stays_within_8_gib_or_cannot_be_read(tmp_path: Path) -> None:
    run_dir = _guard_dir(tmp_path)
    world = _World(run_dir, [10.0], end_after=5)
    values: list[float | None] = [None, 17.5, 20.0, 24.0, 25.4]

    world.run(
        limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000,
        read_unowned_gib=lambda: values[min(world.polls, len(values) - 1)],  # type: ignore[arg-type]
    )

    guard = json.loads((run_dir / "guard.json").read_text(encoding="utf-8"))
    assert guard["alerts"] == [] and guard["unowned_baseline_gib"] == 17.5  # the unreadable first reading is not taken as the baseline


def test_the_guard_pauses_at_exactly_the_limit_and_resumes_only_below_the_resume_level(tmp_path: Path) -> None:
    run_dir = _guard_dir(tmp_path)
    world = _World(run_dir, [39.99, 40.0, 36.0, 36.0, 35.99], end_after=6)

    world.run(limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000)

    assert len(world.paused_calls) == 1  # 39.99 does not pause, exactly 40.0 does
    # exactly 36.0 (polls 3 and 4) does not resume; 35.99 (poll 5) does, and that is a resume by reading, so it leaves a RESUMED file
    assert len(world.resumed_calls) == 1 and list(run_dir.glob("RESUMED_*.txt"))


def test_the_guard_stays_frozen_at_exactly_the_resume_level(tmp_path: Path) -> None:
    run_dir = _guard_dir(tmp_path)
    world = _World(run_dir, [40.0, 36.0], end_after=4)  # 36.0 forever after the pause

    world.run(limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000)

    assert len(world.paused_calls) == 1
    assert len(world.resumed_calls) == 1  # only the final "never leave it frozen" unfreeze, not a resume by reading
    assert not list(run_dir.glob("RESUMED_*.txt"))


def test_the_guard_stops_watching_once_a_stop_was_asked_and_lets_the_job_go(tmp_path: Path) -> None:
    run_dir = _guard_dir(tmp_path)
    (run_dir / "STOP").write_text("x", encoding="utf-8")
    world = _World(run_dir, [99.0])

    world.run(limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000)

    assert world.paused_calls == [] and world.polls == 0


# ------------------------------------------------------------------ start / status / stop with real processes
def test_start_runs_the_command_detached_under_a_worker_and_a_guard_and_leaves_the_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    started = core.start(
        tmp_path, "job-1", [PY, "-c", "import time; time.sleep(1.5); print('done')"], cwd=repo, timeout_minutes=5, poll_seconds=0.3
    )
    run_dir = core.run_directory(tmp_path, "job-1")

    assert started["state"] == "STARTING" and started["detached"] is True and started["cwd"] == str(repo.resolve())
    assert started["command_text"].startswith(PY) or "time.sleep" in started["command_text"]
    assert _wait(lambda: core.read_status(run_dir)["state"] == "DONE", _STARTUP_CEILING), core.read_status(run_dir)
    assert _wait(lambda: core.read_status(run_dir)["worker_alive"] is False, _STARTUP_CEILING)  # DONE is written a moment before the worker exits
    final = core.read_status(run_dir)
    assert final["exit_code"] == 0 and final["detached"] is True and final["mem_guard"] is True and final["git_dirty"] in (False, None)
    assert _wait(lambda: core.read_status(run_dir)["guard"]["samples"] >= 1, _STARTUP_CEILING), _guard_diagnostics(run_dir)
    guard_pid = json.loads((run_dir / "guard.json").read_text(encoding="utf-8"))["guard_pid"]
    assert _wait(lambda: not core.pid_alive(guard_pid), _STARTUP_CEILING)  # the guard ends after the job
    assert b"done" in (run_dir / "run.log").read_bytes()
    assert final["peak_committed_gib"] is None or final["peak_committed_gib"] >= 0


@pytest.mark.parametrize("project_importable", [True, False], ids=["PYTHONPATH-at-project-root", "no-PYTHONPATH-fallback"])
def test_the_guard_starts_whether_or_not_auto_pm_is_importable_for_the_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project_importable: bool
) -> None:
    """D-123: run as a plain script the guard must not put auto_pm/infrastructure/ on sys.path (its logging/ would shadow the stdlib)."""

    project_root = Path(core.__file__).resolve().parents[2]
    if project_importable:
        monkeypatch.setenv("PYTHONPATH", str(project_root))
    else:
        monkeypatch.delenv("PYTHONPATH", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    core.start(tmp_path, "shadow", [PY, "-c", "import time; time.sleep(2)"], cwd=repo, timeout_minutes=5, poll_seconds=0.3)
    run_dir = core.run_directory(tmp_path, "shadow")

    assert _wait(lambda: (run_dir / "guard.json").exists(), _STARTUP_CEILING), _guard_diagnostics(run_dir)
    assert b"Traceback" not in (run_dir / "guard.out").read_bytes()
    assert _wait(lambda: core.read_status(run_dir)["state"] == "DONE", _STARTUP_CEILING)


def test_start_refuses_a_name_that_was_used_an_empty_command_a_bad_name_and_a_missing_directory(tmp_path: Path) -> None:
    core.start(tmp_path, "once", [PY, "-c", "pass"], cwd=tmp_path, poll_seconds=0.2)

    with pytest.raises(core.LongRunError, match="已经用过"):
        core.start(tmp_path, "once", [PY, "-c", "pass"], cwd=tmp_path)
    with pytest.raises(core.LongRunError, match="没有给出要跑的命令"):
        core.start(tmp_path, "empty", [], cwd=tmp_path)
    with pytest.raises(core.LongRunError, match="任务名只能用"):
        core.start(tmp_path, "../escape", [PY, "-c", "pass"], cwd=tmp_path)
    with pytest.raises(core.LongRunError, match="工作目录不存在"):
        core.start(tmp_path, "nodir", [PY, "-c", "pass"], cwd=tmp_path / "nope")
    assert not core.run_directory(tmp_path, "nodir").exists()


def test_start_is_refused_by_the_memory_preflight_before_anything_is_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class RefusedError(RuntimeError):
        pass

    def refuse() -> str:
        raise RefusedError("拒绝启动：已提交内存 40.0 GiB ≥ 35 GiB")

    monkeypatch.setattr(core, "_preflight_module", lambda: SimpleNamespace(require_headroom=refuse, MemoryPreflightRefusedError=RefusedError))

    with pytest.raises(core.LongRunError, match="拒绝启动"):
        core.start(tmp_path, "hot", [PY, "-c", "pass"], cwd=tmp_path)

    assert not (tmp_path / core.RUN_ROOT).exists()


def test_stop_kills_a_running_job_and_records_stopped(tmp_path: Path) -> None:
    core.start(tmp_path, "long", [PY, "-c", "import time; time.sleep(120)"], cwd=tmp_path, poll_seconds=0.3)
    run_dir = core.run_directory(tmp_path, "long")
    assert _wait(lambda: core.read_status(run_dir).get("child_pid"), _STARTUP_CEILING)
    child = int(core.read_status(run_dir)["child_pid"])

    stopped = core.stop(run_dir)

    assert stopped["state"] == "STOPPED" and not core.pid_alive(child)
    assert core.stop(run_dir)["state"] == "STOPPED"  # a second stop is a no-op
    with pytest.raises(core.LongRunError, match="没有这个任务"):
        core.stop(tmp_path / "nothing")


def test_the_status_of_an_unreadable_or_foreign_file_is_an_error_not_a_guess(tmp_path: Path) -> None:
    run_dir = tmp_path / "broken"
    run_dir.mkdir()
    (run_dir / "status.json").write_bytes(b"\xff\xfe not json")

    with pytest.raises(core.LongRunError, match="读不了 status.json"):
        core.read_status(run_dir)
    (run_dir / "status.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(core.LongRunError, match="格式不对"):
        core.read_status(run_dir)


class _Flaky:
    """Make ``Path.read_text`` of files with a given name fail ``times`` times with ``error`` (None: for ever), then work again."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, name: str, error: OSError, times: int | None) -> None:
        self.calls = 0
        real = Path.read_text

        def read_text(path: Path, *args: object, **kwargs: object) -> str:
            if path.name == name:
                self.calls += 1
                if times is None or self.calls <= times:
                    raise error
            return real(path, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "read_text", read_text)
        monkeypatch.setattr(core, "READ_RETRY_SECONDS", 0.0)


class _SharingViolationError(OSError):
    """What Windows raises for a file another process holds open without sharing (``winerror`` 32); Linux has no such attribute, so it is a class attribute."""

    winerror = 32


def _sharing_violation() -> OSError:
    return _SharingViolationError("being used by another process")


@pytest.mark.parametrize("failures", [1, 3, core.READ_RETRIES])
@pytest.mark.parametrize("error", [PermissionError(13, "denied"), _sharing_violation()], ids=["winerror5-or-permission", "winerror32"])
def test_a_read_that_hits_the_instant_of_an_atomic_replace_is_retried_and_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failures: int, error: OSError
) -> None:
    (tmp_path / "status.json").write_text(json.dumps({"state": "RUNNING"}), encoding="utf-8")
    flaky = _Flaky(monkeypatch, "status.json", error, failures)

    assert core.read_json_file(tmp_path / "status.json") == {"state": "RUNNING"}
    assert flaky.calls == failures + 1


def test_a_read_that_keeps_failing_raises_and_says_how_often_it_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "status.json").write_text("{}", encoding="utf-8")
    flaky = _Flaky(monkeypatch, "status.json", PermissionError(13, "denied"), None)

    with pytest.raises(core.LongRunError, match=f"已重试 {core.READ_RETRIES} 次") as caught:
        core.read_json_file(tmp_path / "status.json")

    assert not isinstance(caught.value, core.LongRunMissingError)  # present but unreadable is not "absent"
    assert flaky.calls == core.READ_RETRIES + 1 and core.READ_RETRIES == 8


def test_other_read_errors_are_not_retried_and_a_missing_file_is_told_apart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "status.json").write_text("{}", encoding="utf-8")
    flaky = _Flaky(monkeypatch, "status.json", OSError(5, "input/output error"), None)

    with pytest.raises(core.LongRunError, match="未重试"):
        core.read_json_file(tmp_path / "status.json")
    assert flaky.calls == 1

    with pytest.raises(core.LongRunMissingError, match="没有 nothing.json"):
        core.read_json_file(tmp_path / "nothing.json")


def test_the_status_report_names_an_unreadable_guard_file_instead_of_showing_zero_samples(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "job"
    _spec(run_dir, [PY, "-c", "pass"])
    (run_dir / "guard.json").write_text(json.dumps({"samples": 4}), encoding="utf-8")
    _Flaky(monkeypatch, "guard.json", PermissionError(13, "denied"), None)

    guard = core.read_status(run_dir)["guard"]

    assert "已重试 8 次" in guard["error"]
    monkeypatch.undo()
    (run_dir / "guard.json").unlink()
    assert "error" not in core.read_status(run_dir)["guard"]  # absent: simply no guard file yet


def test_the_module_is_standard_library_only_so_the_worker_runs_as_a_plain_script() -> None:
    source = Path(core.__file__).read_text(encoding="utf-8")

    assert "from auto_pm" not in source and "import auto_pm" not in source


def test_the_preflight_falls_back_to_the_sibling_file_when_the_package_is_not_importable(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    real = importlib.import_module

    def refuse(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "auto_pm.infrastructure.memory_preflight":
            raise ImportError(name)
        return real(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib, "import_module", refuse)

    module = core._preflight_module()

    assert callable(module.require_headroom) and module.__name__ == "long_run_memory_preflight"


def test_git_head_and_dirty_describe_the_working_tree_the_job_ran_in(tmp_path: Path) -> None:
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for args in (["init", "-q"], ["config", "commit.gpgsign", "false"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, env=env)
    (repo / "a.txt").write_text("1", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "a.txt"], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "x"], check=True, env=env)

    head = core._git_head(repo)
    assert len(head) == 40 and core._git_dirty(repo) is False

    (repo / "a.txt").write_text("2", encoding="utf-8")
    (repo / "untracked.txt").write_text("u", encoding="utf-8")
    assert core._git_dirty(repo) is True and core._git_head(repo) == head  # same HEAD, different code: the flag is what tells them apart

    assert core._git_head(tmp_path) == "" and core._git_dirty(tmp_path) is None  # not a repository


def test_the_job_gets_the_requested_environment_but_never_a_lease_credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_PM_LEASE_TOKEN", "very-secret-token")
    code = "import os; print('X=' + os.environ.get('LR_X', '-')); print('L=' + os.environ.get('AUTO_PM_LEASE_TOKEN', '-'))"
    core.start(tmp_path, "envjob", [PY, "-c", code], cwd=tmp_path, poll_seconds=0.2, env={"LR_X": "from-spec"})
    run_dir = core.run_directory(tmp_path, "envjob")

    assert _wait(lambda: core.read_status(run_dir)["state"] == "DONE", _STARTUP_CEILING)
    log = (run_dir / "run.log").read_text(encoding="utf-8")
    assert "X=from-spec" in log and "L=-" in log and "very-secret-token" not in log
    assert "very-secret-token" not in (run_dir / "spec.json").read_text(encoding="utf-8")


def test_a_governed_worktree_is_recorded_instead_of_the_directory_the_job_runs_in(tmp_path: Path) -> None:
    import subprocess

    tree = tmp_path / "tree"
    tree.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "-C", str(tree), "init", "-q"], check=True, env=env)
    subprocess.run(["git", "-C", str(tree), "config", "commit.gpgsign", "false"], check=True, env=env)
    subprocess.run(["git", "-C", str(tree), "commit", "-q", "--allow-empty", "-m", "x"], check=True, env=env)
    head = core._git_head(tree)

    status = core.start(tmp_path, "wt", [PY, "-c", "pass"], cwd=tmp_path, worktree=tree, poll_seconds=0.2)

    assert status["worktree"] == str(tree.resolve()) and status["git_head"] == head and status["cwd"] == str(tmp_path.resolve())
    with pytest.raises(core.LongRunError, match="工作树不存在"):
        core.start(tmp_path, "wt2", [PY, "-c", "pass"], cwd=tmp_path, worktree=tmp_path / "nope")
    assert not core.run_directory(tmp_path, "wt2").exists()


def test_a_pid_that_does_not_exist_has_no_tree_and_is_not_alive() -> None:
    import subprocess

    child = subprocess.Popen([PY, "-c", "pass"])
    child.wait()  # reaped: the pid is gone

    assert core.process_tree(child.pid) == [] and core.pid_alive(child.pid) is False
    assert core.process_tree(0) == [] and core.pid_alive(0) is False
    assert core.process_tree(os.getpid())[0] == os.getpid() and core.pid_alive(os.getpid()) is True


def test_stop_unfreezes_a_job_the_guard_has_paused_and_ends_it_at_once(tmp_path: Path) -> None:
    core.start(tmp_path, "frozen", [PY, "-c", "import time; time.sleep(120)"], cwd=tmp_path, poll_seconds=0.2)
    run_dir = core.run_directory(tmp_path, "frozen")
    assert _wait(lambda: core.read_status(run_dir)["state"] == "RUNNING", _STARTUP_CEILING)
    worker = core._worker_pid(run_dir)
    core.suspend(core.process_tree(worker))  # what the guard does when the machine is full: freeze the worker with the job
    (run_dir / "PAUSED").write_text("x", encoding="utf-8")

    started = time.monotonic()
    final = core.stop(run_dir)

    assert final["state"] == "STOPPED" and final["worker_alive"] is False
    assert time.monotonic() - started < 10 and not (run_dir / "PAUSED").exists()


def test_a_guard_that_cannot_start_means_no_job_and_a_failed_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    launched: list[str] = []

    def launch(argv: list[str], log: Path, cwd: Path) -> int:
        launched.append(argv[-2])
        raise core.LongRunError("no process for you")

    monkeypatch.setattr(core, "launch_detached", launch)

    with pytest.raises(core.LongRunError, match="内存守卫起不来"):
        core.start(tmp_path, "noguard", [PY, "-c", "pass"], cwd=tmp_path)

    assert launched == ["guard"]  # the worker was never started
    status = json.loads((core.run_directory(tmp_path, "noguard") / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "FAILED" and status["mem_guard"] is False and status["detached"] is False and status["exit_code"] is None
    assert (core.run_directory(tmp_path, "noguard") / "FAILED").exists()


def test_a_worker_that_cannot_start_takes_the_guard_down_with_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    killed: list[int] = []

    def launch(argv: list[str], log: Path, cwd: Path) -> int:
        if argv[-2] == "worker":
            raise core.LongRunError("no process for you")
        return 4242

    monkeypatch.setattr(core, "launch_detached", launch)
    monkeypatch.setattr(core, "kill_tree", killed.append)

    with pytest.raises(core.LongRunError, match="工作进程起不来"):
        core.start(tmp_path, "noworker", [PY, "-c", "pass"], cwd=tmp_path)

    assert killed == [4242]
    status = json.loads((core.run_directory(tmp_path, "noworker") / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "FAILED" and status["mem_guard"] is True and status["detached"] is False


def test_the_status_file_only_claims_what_was_started(tmp_path: Path) -> None:
    core.start(tmp_path, "claims", [PY, "-c", "pass"], cwd=tmp_path, poll_seconds=0.2)
    run_dir = core.run_directory(tmp_path, "claims")

    assert _wait(lambda: core.read_status(run_dir)["state"] == "DONE", _STARTUP_CEILING)
    final = core.read_status(run_dir)
    assert final["mem_guard"] is True and final["detached"] is True  # both really started


def test_two_starts_with_the_same_name_at_once_give_one_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    taken = core.run_directory(tmp_path, "race")
    taken.mkdir(parents=True)

    class Hidden(type(Path())):  # type: ignore[misc]
        def exists(self, *args: object, **kwargs: object) -> bool:
            return False  # the loser looked a moment before the winner created it

    monkeypatch.setattr(core, "run_directory", lambda root, name: Hidden(taken))

    with pytest.raises(core.LongRunError, match="刚被另一个启动占用"):
        core.start(tmp_path, "race", [PY, "-c", "pass"], cwd=tmp_path)


def test_a_task_directory_that_cannot_be_created_is_reported_in_plain_words(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_mkdir = Path.mkdir

    def refuse(self: Path, *args: object, **kwargs: object) -> None:
        if self.name == "reserved":
            raise PermissionError("reserved name")
        real_mkdir(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "mkdir", refuse)

    with pytest.raises(core.LongRunError, match="建不了任务目录"):
        core.start(tmp_path, "reserved", [PY, "-c", "pass"], cwd=tmp_path)


def test_the_worker_removes_the_pytest_variables_that_select_or_change_a_suite_and_records_what_it_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit 578: ``PYTEST_ADDOPTS="-k test_1"`` made a long-run run a few cases; the record must not be able to carry it."""

    monkeypatch.setenv("PYTEST_PLUGINS", "from_the_caller")
    code = "import os; print('SEEN=' + ','.join(sorted(k for k in os.environ if k.upper() in ('PYTEST_ADDOPTS', 'PYTEST_PLUGINS', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD'))) + '|KEPT=' + os.environ.get('KEEP_ME', ''))"
    started = core.start(
        tmp_path, "stripped", [PY, "-c", code], cwd=tmp_path, poll_seconds=0.2,
        env={"PYTEST_ADDOPTS": "-k test_1", "pytest_disable_plugin_autoload": "1", "KEEP_ME": "yes"},
    )  # fmt: skip
    assert started["name"] == "stripped"
    end = time.monotonic() + 60
    while time.monotonic() < end and core.read_status(core.run_directory(tmp_path, "stripped"))["state"] not in {"DONE", "FAILED"}:
        time.sleep(0.1)

    status = core.read_status(core.run_directory(tmp_path, "stripped"))
    log = (core.run_directory(tmp_path, "stripped") / "run.log").read_text(encoding="utf-8")

    assert status["state"] == "DONE" and "SEEN=|KEPT=yes" in log
    assert sorted(status["env_stripped"], key=str.upper) == ["PYTEST_ADDOPTS", "pytest_disable_plugin_autoload", "PYTEST_PLUGINS"]


@pytest.mark.real_machine
@pytest.mark.skipif(sys.platform != "win32", reason="compares the reading with the Windows performance counter")
def test_the_committed_reading_matches_the_windows_system_counter() -> None:
    """Real-machine step 2 of the long-run check: the guard's number is the system's ``\\Memory\\Committed Bytes``, within half a GiB."""

    import re
    import subprocess

    from auto_pm.infrastructure import memory_preflight as mp

    counter = subprocess.run(["typeperf", r"\Memory\Committed Bytes", "-sc", "1"], capture_output=True, check=True, timeout=120).stdout
    values = re.findall(rb'"([0-9]+(?:\.[0-9]+)?)"', counter)
    assert values, counter  # the sample row: "date time","bytes"
    counter_gib = float(values[-1]) / mp.GIB

    snapshot = mp.read_commit()

    assert snapshot is not None and abs(snapshot.committed / mp.GIB - counter_gib) <= 0.5
