"""看板点了按钮“没反应”（卡 283）：动作做成了，页面却停在动作之前的样子。

用户 2026-11-16 14:04 在“工作树与分支”页点了两次“收工位”，驾驶舱记录里两次都是 removed，页面上那两行却一直在，
也没有任何回音。原因两处：
1. 点下去到命令跑完有好几秒，页上什么都不变；
2. 命令跑完要页面重读，可上一轮读取还没结束，重读就被“上一轮还没读完，不叠新的”直接丢掉了，
   页面画的是动作之前读到的样子，要等 10 分钟自动刷新或用户换页才变。“决定”页批准后重读也是同一种写法。
"""

from __future__ import annotations

import sys
import threading
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from cockpit_board import actions, stations, worktree_controller  # noqa: E402
from cockpit_board import app as board_app  # noqa: E402
from cockpit_board.decision_controller import DecisionController  # noqa: E402
from cockpit_board.widgets.worktrees import WorktreesPage  # noqa: E402

NO_MARKERS: list[str] = []


def _close_action(name: str = "claude-1b7302") -> stations.Action:
    return stations.Action("close", "收工位", "收掉这个工位", ("worktree", "close", name), name)


def test_clicking_run_shows_a_running_receipt_before_the_command_finishes(qtbot: Any, tmp_path: Path) -> None:
    release = threading.Event()

    def slow_runner(command: list[str], **_: object) -> Any:
        release.wait(10)
        return SimpleNamespace(returncode=0, stdout="已收工位", stderr="")

    page = WorktreesPage(tmp_path, lambda: NO_MARKERS)
    qtbot.addWidget(page)
    controller = worktree_controller.WorktreeController(page, tmp_path, lambda: None, runner=slow_runner,
                                                        markers=lambda: NO_MARKERS)
    controller.run(_close_action())
    # 命令还在跑：页上已经有一张“正在运行”的回执
    assert page.receipts and page.receipts[-1].output == worktree_controller.RUNNING
    assert page.receipts[-1].command == "main.py worktree close claude-1b7302"
    release.set()
    qtbot.waitUntil(lambda: not controller.busy(), timeout=10_000)
    assert page.receipts[-1].rc == 0


def test_a_decisions_refresh_asked_for_while_reading_is_not_dropped(qtbot: Any, tmp_path: Path) -> None:
    rounds: list[int] = []
    first_round_started = threading.Event()
    let_first_round_finish = threading.Event()

    def runner(command: list[str], **_: object) -> Any:
        if "approver-pin" in command:
            rounds.append(1)
            if len(rounds) == 1:
                first_round_started.set()
                let_first_round_finish.wait(10)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    controller = DecisionController(tmp_path, lambda _text: None, lambda: None, runner=runner, now=datetime.now,
                                    markers=lambda: NO_MARKERS)
    qtbot.addWidget(controller.page)
    controller.refresh([], [])
    assert first_round_started.wait(10)
    controller.refresh([], [])  # 读的过程中又要求读（比如刚批完一张）
    let_first_round_finish.set()
    qtbot.waitUntil(lambda: len(rounds) == 2 and not controller._reading, timeout=10_000)
    assert len(rounds) == 2


def test_a_page_reread_asked_for_while_reading_runs_right_after(monkeypatch: pytest.MonkeyPatch) -> None:
    """骨架页（工作树与分支等）：读的过程中又要求重读，这一轮读完不画旧的，马上再读一次。"""
    started: list[str] = []
    shown: list[str] = []
    page = SimpleNamespace(project_line=SimpleNamespace(setText=lambda _t: None),
                           show_results=lambda scope, results: shown.append(scope))
    window: Any = SimpleNamespace(
        page_reads={"worktrees": (SimpleNamespace(needs_project=False),)},
        _reading_pages=set(), _reread_pages=set(),
        options=SimpleNamespace(station_project="", root=Path("."), now=None, read_runner=None),
        read_pages={"worktrees": page}, board=None,
        _track=lambda thread: started.append("read"),
        _on_reads=lambda payload: None,
    )
    window._refresh_reads = lambda key: board_app.CockpitWindow._refresh_reads(cast(Any, window), key)
    monkeypatch.setattr(board_app, "ActionRunner", lambda job, parent: SimpleNamespace(done=SimpleNamespace(connect=lambda _f: None)))

    window._refresh_reads("worktrees")  # 第一轮开读
    window._refresh_reads("worktrees")  # 收工位成功后要求重读：上一轮还在读
    assert started == ["read"]
    board_app.CockpitWindow._on_reads(cast(Any, window), ("worktrees", "范围：本机控制根", []))
    assert started == ["read", "read"], "第一轮读完必须马上再读一次"
    assert shown == [], "第一轮读到的可能是收工位之前的样子，不能画出来"
    board_app.CockpitWindow._on_reads(cast(Any, window), ("worktrees", "范围：本机控制根", []))
    assert shown == ["范围：本机控制根"]
    assert started == ["read", "read"]


def test_running_text_is_not_a_command_receipt_users_could_copy() -> None:
    assert "正在运行" in worktree_controller.RUNNING
    assert actions.Receipt("00:00", "收工位", "main.py worktree close x", None, False, worktree_controller.RUNNING).rc_text == "未验证"
