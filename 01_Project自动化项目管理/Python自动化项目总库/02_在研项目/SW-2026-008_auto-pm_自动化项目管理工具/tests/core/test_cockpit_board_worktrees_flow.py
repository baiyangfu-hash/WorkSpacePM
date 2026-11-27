"""总控屏“工作树与分支”页走真命令（看板工位管理单，2026-11-16）：在一次性的沙盒仓库里开几个工位，在页上点按钮收掉。

和 test_cockpit_board_full_flow.py 同一套台架（make_drill、沙盒控制根的 main.py、真窗口、真子进程），按钮用 ``click()`` 点，
确认框里点框里的“确认并运行”：

* 收一个会话工位（claude-1b7302，已推送、干净）：目录没了，页上那一行也没了；
* 清一个名册外目录（gate-formal，已并进 main）：同上；
* 清一条残留持有记录（claude-abcdef：目录早就没了，三天没心跳）：先只列，确认后才清，记录文件没了；
* 有未提交改动的 trae：按钮灰着，旁边是命令自己的原话；点不了，什么都不动；
* 看板带 AI 标记：所有按钮灰着；就算绕过按钮直接调运行入口，也一条命令都不起。

每条测试一个用完就丢的仓库和账本，不碰真账本、不连 GitHub（origin 是本机的裸仓库）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QLabel, QPushButton  # noqa: E402

from tests.core.test_cockpit_board_full_flow import PROJECT_DIR, SANDBOX_MAIN, WAIT_MS  # noqa: E402
from tests.e2e.test_closure_drill import make_drill  # noqa: E402
from tests.e2e.test_pmf_plc import (  # noqa: E402,F401 - benchmark_tar 是按名字复用的夹具
    PROJECT,
    benchmark_tar,
    git,
)

SCRIPTS = PROJECT_DIR / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from cockpit_board import app as board_app  # noqa: E402
from cockpit_board import decisions as board_decisions  # noqa: E402
from cockpit_board import stations  # noqa: E402

REGISTRY = "SYS-2026-001_WorkspaceGovernance/workspace_registry.json"
ORPHAN = "claude-abcdef"


def _sandbox(root: Path, tmp_path: Path) -> Path:
    """登记驾驶舱项目（命令认运行身份要它）、配一个本机裸仓库当 origin，开三个工位、留一条残留持有记录。"""
    registry = root / REGISTRY
    data = json.loads(registry.read_text(encoding="utf-8"))
    (root / "sw8").mkdir()
    plc = json.loads((root / PROJECT / ".plc.json").read_text(encoding="utf-8"))
    plc["name"] = "SW-2026-008"
    (root / "sw8" / ".plc.json").write_text(json.dumps(plc), encoding="utf-8")
    data["projects"].append({"project_id": "SW-2026-008", "project_root": "sw8", "development_root": "sw8"})
    registry.write_text(json.dumps(data), encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "登记驾驶舱项目")
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(root, "remote", "add", "origin", str(bare))
    git(root, "push", "-q", "origin", "HEAD:main")
    git(root, "fetch", "-q", "origin")
    stations_dir = root / ".auto-pm" / "worktrees"
    gate = stations_dir / "gate-formal"  # 手工 git worktree add 开、在分支上、已并进 main 的名册外目录
    git(root, "worktree", "add", "-q", "-b", "gate/formal", str(gate), "origin/main")
    (gate / "x.txt").write_text("x", encoding="utf-8")
    git(gate, "add", "x.txt")
    git(gate, "commit", "-q", "-m", "门禁")
    git(gate, "push", "-q", "origin", "gate/formal:main")
    git(root, "fetch", "-q", "origin")
    claude = stations_dir / "claude-1b7302"  # 别的对话的会话工位：已推送、干净
    git(root, "worktree", "add", "-q", "-b", "claude/111-x", str(claude), "origin/main")
    git(claude, "push", "-q", "-u", "origin", "claude/111-x")
    trae = stations_dir / "trae"  # 有未提交改动：收不了
    git(root, "worktree", "add", "-q", "-b", "trae/112-y", str(trae), "origin/main")
    git(trae, "push", "-q", "-u", "origin", "trae/112-y")
    (trae / "dirty.txt").write_text("没提交", encoding="utf-8")
    (stations_dir / "cursor-abcdef").mkdir()  # 747：收工位删到一半的空壳，Git 里没有登记
    holders = root / ".auto-pm" / "station-holders"
    holders.mkdir(parents=True, exist_ok=True)
    old = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    (holders / f"{ORPHAN}.json").write_text(json.dumps({"agent": ORPHAN, "pid": 0, "title": "早关了的对话", "opened_at": old,
                                                         "heartbeat_at": old}), encoding="utf-8")
    return stations_dir


class Screen:
    def __init__(self, window: Any, qtbot: Any, root: Path) -> None:
        self.window, self.qtbot, self.root = window, qtbot, root

    @property
    def page(self) -> Any:
        return self.window.worktrees

    def idle(self) -> None:
        def quiet() -> bool:
            return (not self.window._threads and not self.window._reading_pages and not self.window.worktree_actions._jobs
                    and not self.window.decisions._jobs)

        self.qtbot.waitUntil(quiet, timeout=WAIT_MS)

    def open(self) -> None:
        self.idle()
        self.window.page_buttons["worktrees"].click()
        self.idle()
        expected = {"close:claude-1b7302", "close:trae", "clean_residue:cursor-abcdef", "sweep_one:gate-formal",
                    "reclaim:", "registry:"}

        def controls_ready() -> None:
            missing = expected.difference(self.buttons())
            assert self.window.current == "worktrees" and not missing, (
                f"工位页按钮尚未显示：{sorted(missing)}。当前页：{self.window.current}。"
                f"读取状态：{self.page.status}。提示：{self.page.view.notes}"
            )

        self.qtbot.waitUntil(controls_ready, timeout=10_000)

    def buttons(self) -> dict[str, QPushButton]:
        return {f"{b.property('worktree_action')}:{b.property('target') or ''}": b
                for b in self.page.findChildren(QPushButton) if b.property("worktree_action") and b.isVisible()}

    def station_names(self) -> list[str]:
        return [row.name for row in self.page.view.rows]

    def click_and_confirm(self, key: str) -> Any:
        """点页上一个按钮，确认框一出来就点框里的“确认并运行”；等命令跑完、页面重读完。返回回执。"""
        from PySide6.QtCore import QTimer

        self.qtbot.waitUntil(lambda: key in self.buttons(), timeout=10_000)
        button = self.buttons()[key]
        assert button.isEnabled(), f"{key} 灰着：{self.reasons()}"
        before = len(self.page.receipts)
        problems: list[str] = []
        tries = [0]

        def press() -> None:
            dialog = self.page.last_dialog
            if dialog is None or not dialog.isVisible():
                tries[0] += 1
                if tries[0] < 3000:  # “清残留持有记录”先在后台只列一遍，框要等它跑完才弹
                    QTimer.singleShot(20, press)
                return
            if not dialog.run_button.isEnabled():
                problems.append(f"确认键灰着：{dialog.blocked}")
                dialog.cancel_button.click()
                return
            dialog.run_button.click()

        QTimer.singleShot(0, press)
        button.click()
        self.qtbot.waitUntil(lambda: bool(problems) or any(r.action == self._label(key) and "（未运行）" not in r.command
                                                           and r.rc is not None for r in self.page.receipts[before:]
                                                           if "只列" not in r.action), timeout=WAIT_MS)
        assert not problems, problems
        self.idle()
        return next(r for r in reversed(self.page.receipts) if r.action == self._label(key))

    @staticmethod
    def _label(key: str) -> str:
        return {"close": "收工位", "clean_residue": "清理残留", "sweep_one": "清理", "reclaim": "清残留持有记录",
                "sweep_all": "清理全部可清项"}[key.split(":")[0]]

    def reasons(self) -> dict[str, str]:
        return {label.property("blocked_reason"): label.text() for label in self.page.findChildren(QLabel)
                if label.property("blocked_reason")}


@pytest.fixture
def screen(tmp_path: Path, benchmark_tar: bytes, qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Screen]:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    (drill.root / "main.py").write_text(SANDBOX_MAIN, encoding="utf-8")
    with (drill.root / ".git" / "info" / "exclude").open("a", encoding="utf-8") as exclude:
        exclude.write("/main.py\n")
    _sandbox(drill.root, tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(PROJECT_DIR))
    options = board_app.parse_options([
        "--root", str(drill.root), "--no-git", "--no-net", "--no-github", "--no-legacy",
        "--github-cache", str(tmp_path / "github_cache.json"),
    ])
    window = board_app.CockpitWindow(options)
    qtbot.addWidget(window)
    window.show()
    current = Screen(window, qtbot, drill.root)
    current.idle()
    yield current
    current.idle()


def test_close_a_station_clean_an_off_roster_dir_and_a_leftover_record_on_the_page(screen: Screen) -> None:
    stations_dir = screen.root / ".auto-pm" / "worktrees"
    screen.open()
    assert set(screen.station_names()) == {"claude-1b7302", "gate-formal", "trae", "cursor-abcdef"}, screen.page.view.notes
    # trae 有未提交的改动：按钮灰着，旁边是命令自己的原话（清理清单里那一项的原因，和 worktree close 拒绝时同一句）
    assert not screen.buttons()["close:trae"].isEnabled()
    assert screen.reasons()["trae"].startswith("有未提交的改动"), screen.reasons()

    receipt = screen.click_and_confirm("close:claude-1b7302")
    assert receipt.rc == 0, receipt.output
    assert not (stations_dir / "claude-1b7302").exists() and "claude-1b7302" not in screen.station_names()

    # 747：Git 里没有登记的会话工位空壳显示“清理残留”，点了清掉空目录（不是“收工位”）
    screen.qtbot.waitUntil(lambda: "clean_residue:cursor-abcdef" in screen.buttons(), timeout=10_000)
    assert screen.buttons()["clean_residue:cursor-abcdef"].isEnabled()
    receipt = screen.click_and_confirm("clean_residue:cursor-abcdef")
    assert receipt.rc == 0, receipt.output
    assert not (stations_dir / "cursor-abcdef").exists() and "cursor-abcdef" not in screen.station_names()

    receipt = screen.click_and_confirm("sweep_one:gate-formal")
    assert receipt.rc == 0, receipt.output
    assert not (stations_dir / "gate-formal").exists() and "gate-formal" not in screen.station_names()

    record = screen.root / ".auto-pm" / "station-holders" / f"{ORPHAN}.json"
    assert record.is_file()
    receipt = screen.click_and_confirm("reclaim:")
    assert receipt.rc == 0, receipt.output
    previews = [r for r in screen.page.receipts if r.action == "清残留持有记录（只列）"]
    assert previews and ORPHAN in previews[-1].output  # 先只列了一遍，确认框里列的就是它
    assert not record.exists()
    assert (stations_dir / "trae" / "dirty.txt").is_file(), "有改动的工位不许被动到"


def test_with_an_ai_marker_buttons_are_grey_and_nothing_runs(screen: Screen, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")  # 看板进程带上 AI 标记（和 AI 会话打开看板一样）
    stations_dir = screen.root / ".auto-pm" / "worktrees"
    screen.open()
    buttons = screen.buttons()
    assert buttons and not any(b.isEnabled() for b in buttons.values())
    marker = board_decisions.human_only_block(("CLAUDECODE",))
    assert any(label.text() == marker for label in screen.page.findChildren(QLabel))
    before = len(screen.page.receipts)
    action = stations.Action("close", "收工位", "", ("worktree", "close", "claude-1b7302"), "claude-1b7302")
    screen.window.worktree_actions.dialog_on_preview = False  # 万一真跑了只列，也别弹出没人点的模态框把测试卡住
    screen.window.worktree_actions.run(action)  # 绕过按钮直接调运行入口
    screen.window.worktree_actions.preview_reclaim()
    screen.idle()
    assert screen.page.pending_reclaim is None
    assert (stations_dir / "claude-1b7302").is_dir() and (screen.root / ".auto-pm" / "station-holders" / f"{ORPHAN}.json").is_file()
    # 两张回执都只是“未运行”：一条命令都没起
    assert [r.command.endswith("（未运行）") for r in screen.page.receipts[before:]] == [True, True]
