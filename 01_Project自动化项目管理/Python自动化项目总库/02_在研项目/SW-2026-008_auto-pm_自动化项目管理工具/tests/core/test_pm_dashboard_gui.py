"""驾驶舱总控屏桌面界面 ``scripts/pm_dashboard_gui.py`` → ``scripts/cockpit_board/``：

项目经理看板只读（按钮只在 policy.PM_BUTTONS 里）、工程工位按钮只在 policy.STATION_BUTTONS 里且
批准 / 开工 / 提交灰着、输入框只在 BC 表单里、不写工作空间、纯文本标签、没检查显示“没检查”不显示 0、
先快读再接老后台（TD-105 已合并，默认接；--no-legacy 可关）、读失败窗口不挂、双击 bat 不在 releases/ 里、
子进程和写文件只在 actions.py；GitHub 区块显示“数据截至”，没真读到时一格绿都没有。
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from datetime import timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

pytestmark = pytest.mark.external_reads  # D-200: reads real files outside the project

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

from tests.core import test_pm_dashboard as base  # noqa: E402 - 复用原型测试的假工作空间

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pm_dashboard_gui.py"
PACKAGE = Path(__file__).resolve().parents[2] / "scripts" / "cockpit_board"
REPO_ROOT = Path(__file__).resolve().parents[6]
BAT_DIR = REPO_ROOT / "00_Infrastructure" / "auto_pm" / "environment"
BAT = BAT_DIR / "双击打开驾驶舱看板.bat"
BC_TEMPLATE = REPO_ROOT / "0100_PLC自动化" / "00_通用规范" / "项目文档模板" / "02_业务变更记录模板.md"
NOW = base.NOW
WRITES = r"(?<![\w.])open\(|write_bytes\(|write_text\("


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pm_dashboard_gui_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gui = _load()
sys.path.insert(0, str(PACKAGE.parent))
import pm_dashboard as pd_module  # noqa: E402
from cockpit_board import app as app_module  # noqa: E402
from cockpit_board import policy, tool_policy


def _options(root: Path, db: Path, **extra: object) -> argparse.Namespace:
    options = cast(argparse.Namespace, gui.parse_options(
        ["--root", str(root), "--db", str(db), "--now", NOW.isoformat(), "--no-git", "--no-net",
         "--station-project", "DJ-2026-101", "--source-version", "1.3.3", "--effective-version", "1.3.3"]
        + ["--no-legacy"] * (not extra.pop("legacy", False))
        + ["--utc-offset", "-7", "--github-cache", str(root.parent / "github_cache_test.json")]
    ))
    for key, value in extra.items():
        setattr(options, key, value)
    return options


def _window(qapp: QApplication, root: Path, db: Path, **extra: object) -> Any:
    options = _options(root, db, **extra)
    window = gui.CockpitWindow(options)
    window.show_board(gui.load_board(options, use_legacy=not options.no_legacy))
    qapp.processEvents()
    return window


def _buttons(widget: QWidget) -> list[QAbstractButton]:
    # 去掉安全区自查的勾选框和表格左上角自带的无字小按钮
    return [b for b in widget.findChildren(QAbstractButton) if not isinstance(b, QCheckBox) and b.text()]


def _texts(widget: QWidget) -> list[str]:
    return [label.text() for label in widget.findChildren(QLabel)]


def _inside(widget: QWidget, name: str) -> bool:
    parent = widget.parentWidget()
    while parent is not None and parent.objectName() != name:
        parent = parent.parentWidget()
    return parent is not None


def _in_flow_or_tools(window: Any, widget: QWidget) -> bool:
    return bool(window.flow.isAncestorOf(widget) or window.tools.isAncestorOf(widget))


def _files(root: Path) -> dict[str, int]:
    return {str(path): path.stat().st_mtime_ns for path in root.rglob("*") if path.is_file()}


def test_pm_board_is_read_only(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "AWAITING_APPROVAL", "待批准", 1)])
    window = _window(qapp, root, db, examples=True)
    window.open_project("DJ-2026-101")  # 项目详情页也要画出来一起清点
    qapp.processEvents()
    seen: set[str] = set()
    for page in (window.home, window.issues, window.projects, window.project):
        for button in _buttons(page):
            seen.add(button.text())
            lowered = (button.text() + button.toolTip()).lower()
            assert not any(word in lowered for word in policy.PM_FORBIDDEN_WORDS), button.text()
    for button in _buttons(window):
        # 流程图页、工具页自己的按钮由 test_cockpit_board_flow / _tools 按各自的清单清点；这里只数顶栏和上面五页
        if button.objectName() in ("tab", "mode", "refresh") and not _in_flow_or_tools(window, button):
            seen.add(button.text())
    assert seen <= policy.PM_BUTTONS | tool_policy.NAV_BUTTONS, seen - policy.PM_BUTTONS - tool_policy.NAV_BUTTONS
    assert tool_policy.NAV_BUTTONS <= seen
    assert window.menuBar().actions() == []
    for kind in (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox):
        for page in (window.home, window.issues, window.projects, window.project):
            assert page.findChildren(kind) == [], kind.__name__
        # 整个窗口里能打字的地方只有两处：工程工位第 4 步的 BC 表单，和“决定”页顶上的“批准人”一栏
        # （决定页的其余输入都在点按钮后才弹出的确认对话框里，对话框不是主窗口的内容）
        for widget in window.findChildren(kind):
            if _in_flow_or_tools(window, widget):  # 流程图页、工具页的输入框由各自的测试清点（只在 tool_form 里，或是选图选卡的下拉框）
                continue
            assert _inside(widget, "bc_form") or (_inside(widget, "decisions_page") and widget.objectName() == "approver"), (
                kind.__name__, widget.objectName())
    assert window.projects.table.editTriggers() == window.projects.table.EditTrigger.NoEditTriggers
    window.close()


def test_flow_and_tools_pages_are_wired_and_fed_from_the_ledger(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = _window(qapp, root, db)
    assert window.tools.root == window.options.root
    # 顶栏有两个入口，点了切到对应页；工位模式下也能进（这两页和模式无关）
    for mode in ("pm", "ws"):
        window.set_mode(mode)
        for key, page in (("flow", window.flow), ("tools", window.tools), ("home", window.station if mode == "ws" else window.home)):
            window.goto(key)
            assert window.stack.currentWidget() is page
            assert window.page_buttons[key].isChecked()
    # 账本读完：工具页的项目下拉框是板上的项目，流程图页的卡下拉框是板上的任务
    assert "DJ-2026-101" in [window.tools.project_box.itemText(i) for i in range(window.tools.project_box.count())]
    assert any("写通讯层" in window.flow.card_box.itemText(i) for i in range(window.flow.card_box.count()))
    # 同样的数据再画一遍不重填：用户在流程图页选的卡、工具页选的项目都保持
    window.flow.card_box.setCurrentIndex(1)
    chosen = window.flow.card_box.currentData()
    window._render()
    window._render()
    assert chosen is not None and window.flow.card_box.currentData() == chosen
    window.close()


def test_unchanged_data_does_not_refill_flow_and_tools_but_changed_data_does(qapp: QApplication, tmp_path: Path) -> None:
    """定时刷新、GitHub 或联网状态回来都会重画；数据没变就不能重填，否则用户刚点的“预览命令”会被冲掉。"""
    root, db = base._workspace(tmp_path / "a", [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = _window(qapp, root, db)
    params = {"pid": "DJ-2026-101", "number": "CHG-DJ-2026-101-001", "to": "submitted"}
    window.tools.preview_command("change_transition", params)
    assert window.tools.preview is not None
    window.flow.card_box.setCurrentIndex(1)
    chosen = window.flow.card_box.currentData()
    for _ in range(3):  # 不变的数据重画多次
        window._render()
    assert window.tools.preview is not None  # 预览还在，还能点“转状态”
    assert window.flow.card_box.currentData() == chosen
    # 数据真变了（换了一张任务）：重填，旧预览作废（项目或任务变了，旧命令不能再点）
    root2, db2 = base._workspace(tmp_path / "b", [("DJ-2026-101", "ACTIVE", "改了名的任务", 0.1)])
    window.show_board(gui.load_board(_options(root2, db2), use_legacy=False))
    assert window.tools.preview is None
    assert any("改了名的任务" in window.flow.card_box.itemText(i) for i in range(window.flow.card_box.count()))
    window.close()


def test_station_buttons_are_listed_and_gated(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = _window(qapp, root, db)
    window._refresh_decisions = lambda: None  # 本测试只看工位按钮；决定页读命令的接线在 test_decisions_tab_* 里测
    window.set_mode("ws")
    qapp.processEvents()
    buttons = {b.text(): b for b in _buttons(window.station)}
    assert set(buttons) <= policy.STATION_BUTTONS, set(buttons) - policy.STATION_BUTTONS
    for text in buttons:  # 工位的提示文字可以解释“要等接上批准口令才开放”，按钮本身不许带禁用词
        assert not any(word in text.lower() for word in policy.STATION_FORBIDDEN_WORDS), text
    for text in ("提交",):
        assert not buttons[text].isEnabled(), text
    # S1b 已接线：批准范围 / 开工亮着，点它们只是带你去“决定”页，不在这里直接运行任何命令
    assert app_module.DECISION_BUTTONS_WIRED
    for text in ("批准范围", "开工"):
        assert buttons[text].isEnabled(), text
        buttons[text].click()
        assert window.stack.currentWidget() is window.decisions.page
        window.set_mode("ws")
        qapp.processEvents()
        buttons = {b.text(): b for b in _buttons(window.station)}
    # 离线：推送、开 PR 灰；本机检查可点
    assert not buttons["推送 manual/ 分支"].isEnabled() and not buttons["打开 GitHub 开 PR"].isEnabled()
    assert buttons["重新跑 plc check"].isEnabled()
    # 写入 BC 行没预览前灰着
    assert not buttons["写入 02_业务变更记录.md"].isEnabled()
    for word in policy.NEVER:
        assert not any(word.lower() in text.lower() for text in buttons), word
    window.close()


def test_recent_activity_text_is_not_squeezed_into_a_narrow_column(qapp: QApplication, tmp_path: Path) -> None:
    """“最近发生了什么”的说明文字要吃满行宽：行尾曾放了弹簧，把长说明挤成窄窄一列、示例标签被拉高。"""
    long_title = "握手中途断线撤销允许信号并补写回读校验和超时处理"
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", long_title, 0.1)])
    window = _window(qapp, root, db)
    window.resize(1360, 900)
    window.show()
    qapp.processEvents()
    for page in (window.home,):
        label = next(item for item in page.findChildren(QLabel) if item.text().startswith("在干：") and long_title[:6] in item.text())
        assert label.width() > 400, label.width()  # 窄一列时只有 100 来像素
        assert label.height() < 40, label.height()  # 没被挤成好几行
    window.open_project("DJ-2026-101")
    qapp.processEvents()
    label = next(item for item in window.project.findChildren(QLabel) if item.text().startswith("在干：") and long_title[:6] in item.text())
    assert label.width() > 400 and label.height() < 40, (label.width(), label.height())
    window.close()


def test_window_and_screenshot_never_write_the_workspace(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    before = _files(root)
    window = _window(qapp, root, db)
    window.set_mode("ws")
    qapp.processEvents()
    window.close()
    shots = tmp_path / "shots"
    shots.mkdir()
    argv = ["--root", str(root), "--now", NOW.isoformat(), "--no-git", "--no-legacy", "--no-net",
            "--github-cache", str(tmp_path / "github_cache_test.json")]
    assert gui.main([*argv, "--screenshot", str(shots / "看板.png")]) == 0
    assert _files(root) == before  # 账本哈希、修改时间都不变，旁边也不多出 -shm / -wal
    assert sorted(path.name for path in shots.iterdir()) == [
        "看板_全部项目.png",
        "看板_工具.png",
        "看板_工程工位.png",
        "看板_流程图.png",
        "看板_问题.png",
        "看板_项目经理.png",
    ]


def test_bc_write_only_after_preview_and_appends_one_line(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    relative = Path("0100_PLC自动化") / "DJ-2026-101_甲" / "11_监控" / "01_变更管理" / "02_变更记录" / "02_业务变更记录.md"
    control = root / relative  # 控制根 main 上的那份：永远不写
    control_before = control.read_bytes()
    window = _window(qapp, root, db)
    window.set_mode("ws")
    # 还没开人工工位：不预览、不写，提示先开 manual/ 分支（Codex 评审 #52：BC 行要跟 manual/ 分支一起提交）
    window.run_action("bc_preview")
    assert window.station.bc_preview_text == "" and "没有人工工位" in window.status.text()
    record = window.options.manual_worktree / relative
    record.parent.mkdir(parents=True)
    record.write_bytes(BC_TEMPLATE.read_bytes())  # 现行 11 栏模板
    before = record.read_bytes()
    window.run_action("bc_write")  # 没预览：拒绝
    assert window.status.text() == "先预览，再写入"
    assert record.read_bytes() == before
    # 表单没填：拒绝预览，说清缺什么；提出时间进工位时已按现在填到分钟
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", window.station.bc_values["raised"])
    window.run_action("bc_preview")
    assert window.station.bc_preview_text == "" and "“提出人”没填" in window.station.bc_note
    inputs = window.station.bc_inputs
    inputs["raised"].setText("2026-10-23 14:05")
    inputs["channel"].setCurrentText("电话")
    inputs["who"].setText("张工（客户设备科）")
    inputs["kind"].setCurrentText("参数")
    inputs["what"].setText("上料节拍 30 s → 28 s")
    inputs["why"].setText("客户要提产")
    inputs["impact"].setText("FB_2001 节拍计时")
    window.run_action("bc_preview")
    qapp.processEvents()
    cells = [cell.strip() for cell in window.station.bc_preview_text.strip().strip("|").split("|")]
    assert cells == ["BC-DJ-2026-101-2026_10_000", "2026-10-23 14:05（电话）", "张工（客户设备科）", "参数",
                     "上料节拍 30 s → 28 s", "客户要提产", "FB_2001 节拍计时", "", "", "待批", ""]
    assert len(window.station.bc_preview.columns) == 11  # 预览里 11 栏逐栏给人看
    assert "预览：要往表末追加的一行，共 11 栏" in _texts(window.station)
    assert record.read_bytes() == before  # 预览不写
    # 预览后又改了表单：预览作废、写入变灰
    inputs["why"].setText("客户要提产到 28 s")
    buttons = {b.text(): b for b in _buttons(window.station)}
    assert window.station.bc_preview_text == "" and not buttons["写入 02_业务变更记录.md"].isEnabled()
    window.run_action("bc_preview")
    qapp.processEvents()
    assert "客户要提产到 28 s" in window.station.bc_preview_text
    buttons = {b.text(): b for b in _buttons(window.station)}
    assert buttons["写入 02_业务变更记录.md"].isEnabled()
    line = window.station.bc_preview_text
    window.run_action("bc_write")
    # 写入一开始就清掉预览，按钮变灰；连点第二下被拒
    buttons = {b.text(): b for b in _buttons(window.station)}
    assert not buttons["写入 02_业务变更记录.md"].isEnabled()
    window.run_action("bc_write")
    assert window.status.text() == "先预览，再写入"
    for thread in list(window._threads):
        thread.wait(5000)
    qapp.processEvents()
    after = record.read_bytes()
    assert after.startswith(before) and after.count(b"\n") == before.count(b"\n") + 1
    assert after.decode("utf-8").splitlines()[-1] == line  # 写进去的就是预览的那 11 栏
    assert window.station.receipts[0].action == "写入 BC 行" and window.station.receipts[0].rc == 0
    assert control.read_bytes() == control_before  # 控制根那份一字没动
    window.close()


def test_checks_show_unchecked_not_zero(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [])
    window = _window(qapp, root, db)
    values = [label for label in window.home.findChildren(QLabel) if label.objectName() == "check"]
    assert len(values) == 6
    states = {label.property("state") for label in values}
    assert "unchecked" in states
    for label in values:
        if label.property("state") != "number":
            assert label.text() in policy.UNCHECKED_TEXTS
            assert label.text() != "0"
    assert any("没检查的灰色，不是 0" in text for text in _texts(window.home))
    window.close()


def test_ledger_text_is_shown_as_plain_text(qapp: QApplication, tmp_path: Path) -> None:
    sneaky = '<a href="file:///C:/">点我</a><b>粗</b>'
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", sneaky, 0.1)])
    window = _window(qapp, root, db)
    window.open_project("DJ-2026-101")
    window.set_mode("ws")
    qapp.processEvents()
    labels = window.findChildren(QLabel)
    assert any(sneaky in label.text() for label in labels)
    for label in labels:
        if label.text():
            assert label.textFormat() == Qt.TextFormat.PlainText, label.text()
            assert not label.openExternalLinks()
    window.close()


def test_fast_read_first_then_legacy_wording(qapp: QApplication, tmp_path: Path) -> None:
    """TD-105 已合并：先快读出第一版（不带老后台），读完再接老后台措辞；--no-legacy 时永远不接。"""
    assert app_module.LEGACY_ALLOWED
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACCEPTANCE_PENDING", "握手断线", 1)])
    assert db == root / pd_module.DB_RELATIVE
    base._FakeLegacyService.calls = []
    options = _options(root, db, legacy=True, legacy_factory=base._FakeLegacyService)
    window = gui.CockpitWindow(options)
    started: list[bool] = []
    window._start = lambda use_legacy: started.append(use_legacy)  # 不真开线程，只看顺序
    window.reload()
    assert started == [False]  # 先快读，不带老后台
    window._on_loaded(gui.load_board(options, use_legacy=False), False)
    assert started == [False, True]  # 第一版出来后才接老后台
    assert not window.refresh_button.isEnabled()  # 老后台读完前“重新读取”仍灰着，防重入
    window._on_loaded(gui.load_board(options, use_legacy=True), True)  # 老后台那一版回来
    assert started == [False, True]
    assert window.refresh_button.isEnabled()
    assert base._FakeLegacyService.calls == ["snapshot"]  # 只调只读的 snapshot()，别的方法一个不碰
    window.close()


def test_timer_refresh_never_calls_the_old_backend(qapp: QApplication, tmp_path: Path) -> None:
    """10 分钟定时刷新只快读；老后台（约 20 秒）只在首次加载和手动“重新读取”时接。钉住定时器接线本身。"""
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACCEPTANCE_PENDING", "握手断线", 1)])
    base._FakeLegacyService.calls = []
    options = _options(root, db, legacy=True, legacy_factory=base._FakeLegacyService)
    window = gui.CockpitWindow(options)
    started: list[bool] = []
    window._start = lambda use_legacy: started.append(use_legacy)
    window.timer.timeout.emit()  # 定时器到点，走的是真接线
    assert started == [False]
    window._on_loaded(gui.load_board(options, use_legacy=False), False)
    assert started == [False] and window.refresh_button.isEnabled()
    assert base._FakeLegacyService.calls == []
    window.refresh_button.click()  # 手动“重新读取”：快读后才接老后台
    assert started == [False, False]
    window._on_loaded(gui.load_board(options, use_legacy=False), False)
    assert started == [False, False, True]
    window.close()


def test_no_legacy_flag_never_touches_the_old_backend(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACCEPTANCE_PENDING", "握手断线", 1)])
    base._FakeLegacyService.calls = []
    options = _options(root, db, legacy_factory=base._FakeLegacyService)  # 默认带 --no-legacy
    window = gui.CockpitWindow(options)
    started: list[bool] = []
    window._start = lambda use_legacy: started.append(use_legacy)
    window.reload()
    window._on_loaded(gui.load_board(options, use_legacy=False), False)
    assert started == [False] and base._FakeLegacyService.calls == []
    assert window.refresh_button.isEnabled()
    window.close()


@pytest.mark.parametrize("reader", ["copy", "store"])
def test_read_failure_keeps_the_window_alive(qapp: QApplication, tmp_path: Path, reader: str) -> None:
    """账本坏了：copy 读法报 sqlite 的 DatabaseError，store 读法报 Store 包过的 ContinuityStoreError；窗口都不挂。"""
    root, db = base._workspace(tmp_path, [])
    db.write_bytes(b"not a database")
    options = _options(root, db, ledger_reader=reader)
    loader = gui.BoardLoader(options, False, None)
    failures: list[str] = []
    loader.failed.connect(failures.append)
    loader.run()
    assert failures and any(name in failures[0] for name in ("DatabaseError", "ContinuityStoreError")), failures
    window = gui.CockpitWindow(options)
    window._on_failed(failures[0])
    assert window.status.text().startswith("这次没读成")
    assert window.refresh_button.isEnabled()
    window.close()


def test_ledger_reader_flag_reaches_build_board(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    options = _options(root, db)
    assert options.ledger_reader == "auto"
    seen: list[str] = []
    real = pd_module.build_board

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs["ledger_reader"])
        return real(*args, **kwargs)

    monkeypatch.setattr(pd_module, "build_board", spy)
    gui.load_board(options, use_legacy=False)
    options = gui.parse_options(["--root", str(root), "--no-git", "--no-legacy", "--no-net", "--ledger-reader", "store"])
    board = gui.load_board(options, use_legacy=False)
    assert seen == ["auto", "store"]
    assert "TD-105 严格只读快照" in board.ledger_note


def test_double_click_launcher_is_outside_releases() -> None:
    assert BAT.is_file()
    raw = BAT.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    text = raw.decode("utf-8")
    assert "releases" not in text.replace("不在 releases\\ 里", "")
    assert "main.py" not in text
    assert "codex" not in text.lower()
    assert "-B" in text and "pm_dashboard_gui.py" in text
    # 控制根白名单（governance_service.ROOT_WHITELIST）不收新文件：bat 不放控制根，往上三级回到控制根再找脚本
    assert not (REPO_ROOT / BAT.name).exists()
    assert BAT_DIR.parent.parent.parent == REPO_ROOT and 'cd /d "%~dp0..\\..\\.."' in text
    assert '--root "%ROOT%"' in text and "%~dp001_Project" not in text
    matches = [
        path
        for a in REPO_ROOT.glob("01_Project*")
        for b in a.glob("Python*")
        for c in b.glob("02_*")
        for d in c.glob("SW-2026-008_*")
        if (path := d / "scripts" / "pm_dashboard_gui.py").is_file()
    ]
    assert matches == [SCRIPT]
    assert "releases" not in SCRIPT.relative_to(REPO_ROOT).parts


def test_process_and_file_writes_live_only_in_actions() -> None:
    sources = {path: path.read_text(encoding="utf-8") for path in [SCRIPT, *PACKAGE.rglob("*.py")]}
    for path, source in sources.items():
        for forbidden in ("urllib", "requests", "socket", "QNetwork", "QProcess", "os.system"):
            assert forbidden not in source, (path.name, forbidden)
        for forbidden in ("start_execution", "confirm_start", "approve_scope", "close_accepted"):
            assert forbidden not in source, (path.name, forbidden)
        if path.name != "policy.py":  # 规矩文件列的是禁用词本身
            assert "no-verify" not in source, path.name
        # 起子进程的只有 actions.py（决定类按钮）和 tool_actions.py（工程工具）；后者另有 test_cockpit_board_tools 逐文件数
        if path.name not in ("actions.py", "tool_actions.py"):
            assert "subprocess" not in source, path.name
        if path.name not in ("actions.py", "app.py"):
            assert not re.search(WRITES, source), path.name
    # 唯一的写文件：actions.py 追加一行 BC（带预览）；app.py 只在启动出错时写系统临时目录
    app_source = sources[PACKAGE / "app.py"]
    assert app_source.count("write_text(") == 1
    assert "tempfile.gettempdir()" in app_source.split("def _crash_report", 1)[1]
    assert len(re.findall(WRITES, sources[PACKAGE / "actions.py"])) == 1
    assert len(re.findall(WRITES, app_source)) == 1


def test_github_block_shows_as_of_and_never_green_when_stale(qapp: QApplication, tmp_path: Path) -> None:
    import github_collector as gh

    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = _window(qapp, root, db)
    pull = gh.PullInfo(7, "改 OB1", "u", "baiyangfu-hash", "a" * 40, "claude/x", False, "2026-10-22T09:00:00Z",
                       projects=["DJ-2026-101"], plc=True, ci=[gh.CiState("plc-ci", "pass", "过")],
                       safety=gh.Safety("signed", "是", "已签"))
    fresh = gh.Snapshot("o/r", "ok", NOW, NOW, pulls=[pull], main_ci=[gh.CiState("plc-ci", "pass", "过")],
                        authenticated=True)
    stale = gh.Snapshot("o/r", "offline", NOW, NOW - timedelta(hours=3), from_cache=True, pulls=[pull],
                        main_ci=[gh.CiState("plc-ci", "pass", "过")], errors=["断网：timed out"])
    for snapshot, green in ((fresh, True), (stale, False)):
        window.github = snapshot
        window._render()
        window.goto("home")
        window.open_project("DJ-2026-101")
        window.project.set_tab("io")
        qapp.processEvents()
        for page in (window.home, window.project):
            blocks = [f for f in page.findChildren(QFrame) if f.property("github_state")]
            assert len(blocks) == 1
            texts = _texts(blocks[0])
            assert any(t.startswith("数据截至 ") for t in texts)
            chips = [lab for lab in blocks[0].findChildren(QLabel) if lab.objectName() == "chip"]
            assert chips and any(lab.property("sev") == "ok" for lab in chips) is green
            if not green:
                assert all(lab.text() in ("未知", "没审计记录") and lab.property("sev") == "na" for lab in chips)
                assert any("3 小时前" in t for t in texts), texts
    window.close()


def test_issues_page_in_the_real_window_says_not_checked_when_github_was_not_read(qapp: QApplication, tmp_path: Path) -> None:
    """端到端：真窗口 → 真 _render → 问题页。把 app.py 里往问题页传说明的那一行删掉，这条必须红（#475 审计 535）。"""
    import github_collector as gh

    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = _window(qapp, root, db)
    red = gh.PullInfo(9, "改 IO 表", "u", "baiyangfu-hash", "b" * 40, "claude/x", False, "2026-10-22T09:00:00Z",
                      projects=["DJ-2026-101"], ci=[gh.CiState("gate", "fail", "红")])
    stale = gh.Snapshot("o/r", "offline", NOW, NOW - timedelta(hours=3), from_cache=True, pulls=[red],
                        errors=["断网：timed out"])
    fresh_ok = gh.Snapshot("o/r", "ok", NOW, NOW, pulls=[gh.PullInfo(
        10, "好的", "u", "baiyangfu-hash", "c" * 40, "claude/y", False, "2026-10-22T09:00:00Z",
        projects=["DJ-2026-101"], ci=[gh.CiState("gate", "pass", "过")])])
    fresh_red = gh.Snapshot("o/r", "ok", NOW, NOW, pulls=[red])
    cases = (
        (None, True, False),  # 没开采集：写“没检查”，不报警
        (stale, True, False),  # 只有旧缓存：写“没检查”，不凭旧数据报警（缓存里那条红 PR 不许出现）
        (fresh_ok, False, False),  # 读到了、全绿：什么说明都不加
        (fresh_red, False, True),  # 读到了、有红：问题页出现这条红 PR
    )
    for snapshot, expect_note, expect_red in cases:
        window.github = snapshot
        window._render()
        window.goto("issues")
        qapp.processEvents()
        texts = _texts(window.issues)
        assert any(t.startswith("没检查：") for t in texts) is expect_note, (snapshot and snapshot.state, texts)
        assert any("PR #9 门禁红" in t for t in texts) is expect_red, (snapshot and snapshot.state, texts)
    window.close()


def test_decisions_tab_reads_only_read_commands_and_lists_buttons_by_state(qapp: QApplication, tmp_path: Path) -> None:
    """“决定”页签：打开时用只读命令读口令状态、待批准卡、收件箱；每个状态出现对应按钮；点按钮才会运行写命令。"""
    import subprocess

    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACCEPTANCE_PENDING", "待验收", 1), ("DJ-2026-101", "ACCEPTED", "已验收", 2)])
    window = _window(qapp, root, db)
    calls: list[list[str]] = []

    def fake(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command[3:])
        return subprocess.CompletedProcess(command, 0, "批准口令：未生效（Git HEAD 里没有 x）" if "approver-pin" in command else "{}", "")

    window.decisions.runner = fake
    window.goto("decisions")
    for _ in range(100):
        for job in list(window.decisions._jobs):
            job.wait(2000)
        qapp.processEvents()
        if not window.decisions._jobs:
            break
    assert window.stack.currentWidget() is window.decisions.page
    assert ["pm", "approver-pin", "status"] in calls
    assert ["pm", "pending", "--project-id", "DJ-2026-101"] in calls and ["pm", "inbox", "list", "--project-id", "DJ-2026-101"] in calls
    assert all(c[:2] in (["pm", "approver-pin"], ["pm", "pending"], ["pm", "inbox"]) for c in calls)  # 只读命令，没有任何写命令
    texts = {b.text() for b in _buttons(window.decisions.page)}
    assert {"确认验收", "收口"} <= texts
    assert "批准口令：未生效" in " ".join(_texts(window.decisions.page))
    window.close()


def _wait_threads(window: Any, qapp: QApplication) -> None:
    for _ in range(200):
        for thread in list(window._threads):
            thread.wait(2000)
        qapp.processEvents()
        if not window._threads:
            break


def test_timer_round_does_not_refresh_the_decisions_page_but_manual_reload_does(qapp: QApplication, tmp_path: Path) -> None:
    """#455 预审 514 a：10 分钟定时那一轮只快读，不连决定页一起读；手动“重新读取”才读。"""
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = _window(qapp, root, db, no_github=True)
    refreshed: list[int] = []
    window.decisions.refresh = lambda *_a: refreshed.append(1)
    window.goto("decisions")
    assert refreshed == [1]  # 打开页签：读一次
    window.auto_reload()  # 定时刷新
    _wait_threads(window, qapp)
    assert refreshed == [1]
    window.reload()  # 手动“重新读取”
    _wait_threads(window, qapp)
    assert refreshed == [1, 1]
    window.close()


def test_decisions_page_reads_at_most_the_project_limit(qapp: QApplication, tmp_path: Path) -> None:
    """#455 预审 514 b：一次最多读 DECISION_PROJECT_LIMIT 个项目，按“有开着的卡的项目在前”的顺序截断，不重复。"""
    from types import SimpleNamespace

    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = _window(qapp, root, db)
    limit = app_module.DECISION_PROJECT_LIMIT

    def project(index: int, column: str) -> Any:
        mission = SimpleNamespace(column=column, state="ACTIVE" if column == "在干" else "CLOSED")
        return SimpleNamespace(project_id=f"DJ-2026-{200 + index}", missions=[mission])

    window.board = SimpleNamespace(projects=[project(i, "已关" if i == 0 else "在干") for i in range(limit + 5)])
    window.home_vm = None
    got: list[Any] = []
    window.decisions.refresh = lambda ids, missions: got.append((list(ids), list(missions)))
    window._refresh_decisions()
    ids, missions = got[0]
    assert len(ids) == limit and len(set(ids)) == limit
    assert ids[0] == "DJ-2026-201" and "DJ-2026-200" not in ids  # 只有已关的卡的项目不读
    assert len(missions) == limit + 5  # 看板里的卡全部交给页面，只有“要读的项目”被截断
    window.close()
