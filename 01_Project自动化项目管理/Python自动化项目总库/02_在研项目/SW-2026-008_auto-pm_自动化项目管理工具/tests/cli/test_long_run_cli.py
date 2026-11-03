"""``main.py long-run`` command line: start refuses on a hot machine, status lists and reads, stop ends the job (11-03 memory P1, PR-B)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.infrastructure import long_run_core as core
from auto_pm.infrastructure import memory_preflight as mp
from auto_pm.ui.cli.__main__ import cli

pytestmark = pytest.mark.usefixtures("identity_guard_off")

GIB = mp.GIB
PY = sys.executable


def _run(workspace: Path, *args: str):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(cli, ["-w", str(workspace), "long-run", *args], catch_exceptions=False)


def _wait_state(workspace: Path, name: str, wanted: set[str], seconds: float = 30.0) -> dict[str, object]:
    end = time.monotonic() + seconds
    last: dict[str, object] = {}
    while time.monotonic() < end:
        last = core.read_status(core.run_directory(workspace, name))
        if last.get("state") in wanted:
            return last
        time.sleep(0.1)
    raise AssertionError(f"任务没有到 {wanted}：{last}")


def test_start_runs_the_command_detached_and_status_reports_the_exit_code(tmp_path: Path) -> None:
    result = _run(tmp_path, "start", "--name", "ok1", "--cwd", str(tmp_path), "--", PY, "-c", "print('hi')")

    assert result.exit_code == 0, result.output
    started = json.loads(result.output)
    assert started["name"] == "ok1" and started["detached"] is True and "long-run status --name ok1" in started["next"]
    _wait_state(tmp_path, "ok1", {"DONE"})

    shown = json.loads(_run(tmp_path, "status", "--name", "ok1").output)
    assert shown["state"] == "DONE" and shown["exit_code"] == 0


def test_a_failing_command_is_recorded_as_failed_with_its_exit_code(tmp_path: Path) -> None:
    assert _run(tmp_path, "start", "--name", "bad1", "--cwd", str(tmp_path), "--", PY, "-c", "raise SystemExit(3)").exit_code == 0
    final = _wait_state(tmp_path, "bad1", {"FAILED"})

    assert final["exit_code"] == 3


def test_start_is_refused_on_a_hot_machine_and_creates_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mp, "read_commit", lambda: mp.CommitSnapshot(40 * GIB, 64 * GIB, 32 * GIB))
    monkeypatch.setattr(mp, "all_processes", lambda: (mp.ProcessUse(7, "pytest.exe", 12 * GIB),))

    result = _run(tmp_path, "start", "--name", "hot", "--cwd", str(tmp_path), "--", PY, "-c", "pass")

    assert result.exit_code == 1
    assert "拒绝启动" in result.output and "pytest.exe（PID 7）" in result.output
    assert not (tmp_path / core.RUN_ROOT).exists()


def test_a_used_name_is_not_reused_and_the_old_record_is_untouched(tmp_path: Path) -> None:
    assert _run(tmp_path, "start", "--name", "once", "--cwd", str(tmp_path), "--", PY, "-c", "pass").exit_code == 0
    _wait_state(tmp_path, "once", {"DONE"})
    before = (core.run_directory(tmp_path, "once") / "status.json").read_text(encoding="utf-8")

    again = _run(tmp_path, "start", "--name", "once", "--cwd", str(tmp_path), "--", PY, "-c", "print(1)")

    assert again.exit_code == 1 and "已经用过" in again.output
    assert (core.run_directory(tmp_path, "once") / "status.json").read_text(encoding="utf-8") == before


def test_start_without_a_command_or_with_a_bad_name_is_refused(tmp_path: Path) -> None:
    no_command = CliRunner().invoke(cli, ["-w", str(tmp_path), "long-run", "start", "--name", "x"])
    bad_name = CliRunner().invoke(cli, ["-w", str(tmp_path), "long-run", "start", "--name", "../evil", "--cwd", str(tmp_path), "--", PY, "-c", "pass"])

    assert no_command.exit_code != 0
    assert bad_name.exit_code != 0 and not (tmp_path / "evil").exists()


def test_status_without_a_name_lists_every_task_and_survives_a_broken_one(tmp_path: Path) -> None:
    assert json.loads(_run(tmp_path, "status").output) == {"tasks": []}
    assert _run(tmp_path, "start", "--name", "a1", "--cwd", str(tmp_path), "--", PY, "-c", "pass").exit_code == 0
    _wait_state(tmp_path, "a1", {"DONE"})
    broken = tmp_path / core.RUN_ROOT / "broken"
    broken.mkdir(parents=True)
    (broken / "status.json").write_text("{not json", encoding="utf-8")

    rows = {row["name"]: row for row in json.loads(_run(tmp_path, "status").output)["tasks"]}

    assert rows["a1"]["state"] == "DONE" and rows["a1"]["exit_code"] == 0
    assert rows["broken"]["state"] == "UNREADABLE"


def test_status_of_an_unknown_task_says_so(tmp_path: Path) -> None:
    result = _run(tmp_path, "status", "--name", "nobody")

    assert result.exit_code == 1 and "nobody" in result.output


def test_stop_ends_a_running_job_and_marks_it_stopped(tmp_path: Path) -> None:
    assert _run(tmp_path, "start", "--name", "slow", "--cwd", str(tmp_path), "--", PY, "-c", "import time; time.sleep(120)").exit_code == 0
    _wait_state(tmp_path, "slow", {"RUNNING"})

    stopped = json.loads(_run(tmp_path, "stop", "--name", "slow").output)

    assert stopped["state"] == "STOPPED"
    assert not core.pid_alive(core._worker_pid(core.run_directory(tmp_path, "slow")))


def test_every_subcommand_checks_the_runtime_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from auto_pm.ui.cli import long_run

    seen: list[str] = []
    monkeypatch.setattr(long_run, "require_runtime_identity_for_workspace", lambda _ctx: seen.append("x"))

    _run(tmp_path, "status")
    CliRunner().invoke(cli, ["-w", str(tmp_path), "long-run", "stop", "--name", "nobody"])
    CliRunner().invoke(cli, ["-w", str(tmp_path), "long-run", "start", "--name", "idc", "--cwd", str(tmp_path), "--", PY, "-c", "pass"])

    assert len(seen) == 3
