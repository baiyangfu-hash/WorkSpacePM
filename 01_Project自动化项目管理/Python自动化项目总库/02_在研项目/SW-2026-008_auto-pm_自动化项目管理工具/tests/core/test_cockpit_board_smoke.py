"""看板冒烟（scripts/cockpit_board/smoke.py）：挨页点一遍，不报错、不卡“正在读”、不空白。

假工作空间 + 假运行器（回 tests/fixtures/cockpit_board 里的真样本），不起真子进程、不连网。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cockpit_board"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import shell, smoke  # noqa: E402

from tests.core import test_pm_dashboard as base  # noqa: E402 - 复用假工作空间
from tests.core import test_pm_dashboard_gui as gui_tests  # noqa: E402 - 复用窗口工厂

SAMPLES = {
    "orient": "orient.json", "missions": "pm_missions.json", "pending": "pm_pending.json", "inbox": "pm_inbox.json",
    "worktree_list": "worktree_list.json", "worktree_sweep": "worktree_sweep.json", "long_run": "long_run_status.json",
}
# 侧栏上的页：功能 1 今天、2 任务、3 PR 与审计、4 问题、8 工作树与分支、13 要你出手都在里面
FUNCTION_PAGES = {"home", "tasks", "prs", "issues", "worktrees", "attention"}


def _runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
    """页面和“决定”页的只读命令都回真样本；认不出的（如口令状态）回空 JSON，和没设口令时一样。"""
    args = command[3:]  # [python, -B, main.py, ...]
    for reads in shell.page_reads().values():
        for read in reads:
            if args[: len(read.command.split())] == read.command.split():
                return subprocess.CompletedProcess(command, 0, (FIXTURES / SAMPLES[read.reader]).read_text(encoding="utf-8"), "")
    return subprocess.CompletedProcess(command, 0, "{}", "")


def _window(qapp: QApplication, tmp_path: Path) -> Any:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1), ("DJ-2026-101", "AWAITING_APPROVAL", "等批", 4)])
    window = gui_tests._window(qapp, root, db, read_runner=_runner)
    window.decisions.runner = _runner
    return window


def test_every_nav_page_and_the_station_pass_the_smoke(qapp: QApplication, tmp_path: Path) -> None:
    window = _window(qapp, tmp_path)
    report = smoke.run(window, qapp, wait=20, out=tmp_path / "shots")
    window.close()
    assert report.ok, "\n".join(report.lines())
    keys = [p.key for p in report.pages]
    assert FUNCTION_PAGES <= set(keys) and keys[-1] == "ws"
    assert all(p.labels > 0 for p in report.pages)
    assert sorted(path.name for path in (tmp_path / "shots").iterdir()) == sorted(p.shot for p in report.pages)
    assert report.lines()[-1] == f"合计 {len(keys)}/{len(keys)} 页过"


def test_a_page_that_throws_is_named_and_the_rest_still_run(qapp: QApplication, tmp_path: Path) -> None:
    window = _window(qapp, tmp_path)
    real_goto = window.goto

    def goto(key: str) -> None:
        if key == "issues":
            raise RuntimeError("问题页坏了")
        real_goto(key)

    window.goto = goto
    report = smoke.run(window, qapp, wait=20)
    window.close()
    assert not report.ok
    bad = [p for p in report.pages if not p.ok]
    assert [p.key for p in bad] == ["issues"] and "问题页坏了" in bad[0].problems[0]
    assert len(report.pages) == len(smoke.nav_pages())  # 坏一页不停，后面的照样点检


def test_an_exception_raised_inside_a_slot_is_caught(qapp: QApplication, tmp_path: Path) -> None:
    """槽函数里抛的异常不会打断事件循环，只会走 sys.excepthook；冒烟要把它记到当时那一页上。"""
    window = _window(qapp, tmp_path)
    real_goto = window.goto

    def goto(key: str) -> None:
        real_goto(key)
        if key == "prs":
            sys.excepthook(ValueError, ValueError("槽里坏了"), None)

    window.goto = goto
    report = smoke.run(window, qapp, wait=20)
    window.close()
    assert [p.key for p in report.pages if not p.ok] == ["prs"]


def test_a_page_stuck_reading_fails_with_the_wait_named(qapp: QApplication, tmp_path: Path) -> None:
    window = _window(qapp, tmp_path)
    smoke.settle(qapp, window, 20)
    window._reading_pages.add("tasks")  # 模拟后台读一直不回来
    report = smoke.run(window, qapp, wait=0.2, pages=[("tasks", "任务")])
    window._reading_pages.discard("tasks")
    window.close()
    assert not report.ok and report.startup_errors == ["首次读取 0 秒没读完"]
    assert report.pages[0].problems[0] == "0 秒还在读"


def test_a_page_header_left_on_reading_fails_even_when_nothing_is_running(qapp: QApplication, tmp_path: Path) -> None:
    """后台读都结束了，页头却还写着“正在读”（结果回来了、页头没刷新）：只看后台忙不忙抓不到，要单独查页头。"""
    window = _window(qapp, tmp_path)
    page = window.read_pages["tasks"]
    real_show = page.show_results

    def show_results(scope: str, results: Any) -> None:
        real_show(scope, results)
        page.project_line.setText(scope + " · 正在读……")  # 模拟刷新页头的那一步漏了

    page.show_results = show_results
    report = smoke.run(window, qapp, wait=20)
    window.close()
    bad = [p for p in report.pages if not p.ok]
    assert [p.key for p in bad] == ["tasks"]
    assert bad[0].problems == ["页头还写着“正在读”"]


def test_the_smoke_script_starts_no_process_itself() -> None:
    text = (SCRIPTS / "cockpit_board" / "smoke.py").read_text(encoding="utf-8")
    for word in ("subprocess", "os.system", "QProcess", "write_text", "unlink", "rmtree"):
        assert word not in text, word
