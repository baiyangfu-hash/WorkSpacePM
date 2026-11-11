"""骨架 B 的只读命令运行器（actions.run_read / classify_read / write_snapshot）。

超时、退出码、命令不存在、只有启动提示、断网、没起来，各归一类；界面线程不等它（放进 app.ActionRunner 后台跑）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cockpit_board"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import actions, readers, snapshot  # noqa: E402


def _fake(rc: int = 0, out: str = "", err: str = "", raises: BaseException | None = None) -> Any:
    calls: list[dict[str, Any]] = []

    def runner(command: list[str], **kwargs: Any) -> Any:
        calls.append({"command": command, **kwargs})
        if raises is not None:
            raise raises
        return SimpleNamespace(returncode=rc, stdout=out, stderr=err)

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_ok_read_runs_main_py_in_control_root_read_only(tmp_path: Path) -> None:
    runner = _fake(0, _fixture("pm_inbox.json"))
    outcome = actions.run_read(tmp_path, ["pm", "inbox", "list", "--project-id", "SW-2026-008"], runner=runner)
    assert outcome.kind == "ok" and outcome.rc == 0 and outcome.text == "读到了"
    call = runner.calls[0]
    assert call["command"][-5:] == ["pm", "inbox", "list", "--project-id", "SW-2026-008"]
    assert call["command"][2] == str(tmp_path / "main.py")
    assert call["cwd"] == str(tmp_path) and call["timeout"] == actions.READ_TIMEOUT == 30
    assert call["stdin"] is subprocess.DEVNULL and call["check"] is False  # 要口令的命令立刻失败，不挂住
    assert readers.parse("inbox", outcome.stdout).ok


def test_missing_command_says_release_too_old(tmp_path: Path) -> None:
    outcome = actions.run_read(tmp_path, ["pm", "orient", "X"], runner=_fake(2, "", _fixture("stderr_missing_command.txt")))
    assert outcome.kind == "missing_command"
    assert outcome.text.startswith("本机发布版太旧") and "No such command" in outcome.text


def test_nonzero_exit_keeps_rc_and_first_error_line(tmp_path: Path) -> None:
    outcome = actions.run_read(tmp_path, ["pm", "missions", "--pid", "X"], runner=_fake(1, "", _fixture("stderr_no_ledger.txt")))
    assert outcome.kind == "exit_nonzero" and outcome.rc == 1
    assert outcome.text == "命令报错（退出码 1）：Error: Continuity Store 必需文件不存在: continuity.db"


def test_banner_only_is_not_ok(tmp_path: Path) -> None:
    outcome = actions.run_read(tmp_path, ["pm", "orient", "X", "--json"], runner=_fake(0, "  \n", _fixture("stderr_orient_banner.txt")))
    assert outcome.kind == "banner_only" and outcome.text == "只有启动提示，没有结果"


def test_banner_plus_result_is_ok(tmp_path: Path) -> None:
    outcome = actions.run_read(tmp_path, ["pm", "orient", "X", "--json"],
                               runner=_fake(0, _fixture("orient.json"), _fixture("stderr_orient_banner.txt")))
    assert outcome.kind == "ok" and readers.parse("orient", outcome.stdout).ok


def test_timeout_and_spawn_failure(tmp_path: Path) -> None:
    timed = actions.run_read(tmp_path, ["long-run", "status"], runner=_fake(raises=subprocess.TimeoutExpired("x", 30)))
    assert timed.kind == "timeout" and timed.rc is None and "30 秒" in timed.text
    failed = actions.run_read(tmp_path, ["long-run", "status"], runner=_fake(raises=FileNotFoundError("python")))
    assert failed.kind == "spawn_failed" and "FileNotFoundError" in failed.text


def test_network_error_is_offline_and_credentials_are_scrubbed(tmp_path: Path) -> None:
    # 凭据形状在运行时拼出来，源码里不出现完整的“地址带口令”写法（sw008-ci 的 Secret scan 会拦）
    url = "https://" + "user" + ":" + "tok3n" + "@github.com/x/y/"
    err = f"fatal: unable to access '{url}': Could not resolve host: github.com\n"
    outcome = actions.run_read(tmp_path, ["pm", "pr", "list"], runner=_fake(1, "", err))
    assert outcome.kind == "offline" and outcome.text.startswith("断网")
    assert "tok3n" not in outcome.text and "***@" in outcome.text


@pytest.mark.parametrize(("rc", "out", "err", "kind"), [
    (0, "{}", "", "ok"),
    (0, "", "", "banner_only"),
    (2, "", "Error: No such command 'orient'.", "missing_command"),
    (1, "", "Error: 运行身份未通过校验", "exit_nonzero"),
    (1, "", "Connection refused", "offline"),
    (0, "{}", "Error: No such command 'x'.", "missing_command"),  # 有输出也先认“命令不存在”
])
def test_classify_read_table(rc: int, out: str, err: str, kind: str) -> None:
    assert actions.classify_read(rc, out, err) == kind
    assert kind in actions.READ_TEXT


def test_snapshot_is_written_only_for_ok_reads_and_reads_back(tmp_path: Path) -> None:
    now = datetime(2026, 11, 11, 14, 0, tzinfo=UTC)
    key = snapshot.key_for("inbox", "SW-2026-008")
    bad = actions.ReadOutcome("exit_nonzero", "cmd", 1, "", "Error: x")
    assert actions.write_snapshot(tmp_path, key, bad, now) is None
    assert not (tmp_path / ".auto-pm").exists()
    good = actions.ReadOutcome("ok", "cmd", 0, _fixture("pm_inbox.json"), "")
    path = actions.write_snapshot(tmp_path, key, good, now)
    assert path == snapshot.path_for(tmp_path, key) and path.is_file()
    assert not path.with_name(path.name + ".tmp").exists()
    loaded = snapshot.load(tmp_path, key)
    assert loaded is not None and loaded.saved_at == now and loaded.stdout == good.stdout


def test_snapshot_write_failure_returns_none(tmp_path: Path) -> None:
    blocker = tmp_path / ".auto-pm"
    blocker.write_text("不是目录", encoding="utf-8")  # 缓存目录建不出来
    outcome = actions.ReadOutcome("ok", "cmd", 0, "{}", "")
    assert actions.write_snapshot(tmp_path, "orient", outcome, datetime.now(UTC)) is None


def test_slow_read_runs_off_the_ui_thread(qapp: Any, tmp_path: Path) -> None:
    """放进 app.ActionRunner（QThread）跑：start() 立刻返回，界面线程不等；跑完 done 信号带回结果。"""
    pytest.importorskip("PySide6")
    from cockpit_board.app import ActionRunner

    release = threading.Event()

    def slow(command: list[str], **kwargs: Any) -> Any:
        release.wait(5)
        return SimpleNamespace(returncode=0, stdout="[]", stderr="")

    results: list[Any] = []
    runner = ActionRunner(lambda: actions.run_read(tmp_path, ["worktree", "list", "--json"], runner=slow), None)
    runner.done.connect(results.append)
    started = time.monotonic()
    runner.start()
    assert time.monotonic() - started < 1 and runner.isRunning() and results == []
    release.set()
    assert runner.wait(5000)
    qapp.processEvents()
    assert len(results) == 1 and results[0].kind == "ok"
