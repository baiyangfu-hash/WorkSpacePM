"""long-run core: the worker's final status, the guard's pause/resume trail, and real detached processes (11-03 laptop memory P1)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
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
    assert code == core.TIMEOUT_EXIT and status["state"] == "FAILED"
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

    def run(self, **kwargs: float) -> None:
        core.guard_loop(
            self.run_dir,
            read_committed_gib=self.read,
            sleep=self.sleep,
            clock=lambda: self.now,
            tree=lambda root: [root, root + 1],
            pause=lambda pids: (self.paused_calls.append(list(pids)), len(pids))[1],
            unpause=lambda pids: (self.resumed_calls.append(list(pids)), len(pids))[1],
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


def test_the_guard_stops_at_once_when_the_job_has_already_ended(tmp_path: Path) -> None:
    run_dir = _guard_dir(tmp_path)
    (run_dir / "FAILED").write_text("x", encoding="utf-8")
    world = _World(run_dir, [99.0])

    world.run(limit_gib=40.0, resume_gib=36.0, poll_seconds=20, max_seconds=10_000)

    assert world.paused_calls == [] and world.polls == 0


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
    assert _wait(lambda: core.read_status(run_dir)["state"] == "DONE"), core.read_status(run_dir)
    assert _wait(lambda: core.read_status(run_dir)["worker_alive"] is False)  # DONE is written a moment before the worker exits
    final = core.read_status(run_dir)
    assert final["exit_code"] == 0 and final["detached"] is True and final["mem_guard"] is True and final["git_dirty"] in (False, None)
    assert _wait(lambda: core.read_status(run_dir)["guard"]["samples"] >= 1)
    guard_pid = json.loads((run_dir / "guard.json").read_text(encoding="utf-8"))["guard_pid"]
    assert _wait(lambda: not core.pid_alive(guard_pid), 20)  # the guard ends after the job
    assert b"done" in (run_dir / "run.log").read_bytes()
    assert final["peak_committed_gib"] is None or final["peak_committed_gib"] >= 0


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
    assert _wait(lambda: core.read_status(run_dir).get("child_pid"))
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

    assert _wait(lambda: core.read_status(run_dir)["state"] == "DONE")
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
