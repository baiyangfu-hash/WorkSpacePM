"""驾驶舱总控屏桌面界面 ``scripts/pm_dashboard_gui.py`` → ``scripts/cockpit_board/``：

项目经理看板除决定类按钮外只读（按钮只在 policy.PM_BUTTONS 里；CHG-SCPT-2026-654 起项目详情页多出归档、重新激活的
预演和确认键，全部项目页多一个只跳页的“新建项目…”，各页有哪些键由下面的测试逐页清点）、工程工位按钮只在 policy.STATION_BUTTONS 里且
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

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
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
from cockpit_board import viewmodel as vm_module
from cockpit_board.widgets import common as board_widgets


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
    """规矩（policy.py，CHG-SCPT-2026-654 改）：项目经理看板除决定类按钮外只读。这里清点的仍是同一件事：
    这几页上的按钮文字只能取自 PM_BUTTONS、没有禁用词、没有任何能打字的地方、没有菜单。"""
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
        # 流程图页、工具页自己的按钮由 test_cockpit_board_flow / _tools 按各自的清单清点；这里只数侧栏（nav）、顶栏和上面五页
        if button.objectName() in ("nav", "tab", "mode", "refresh") and not _in_flow_or_tools(window, button):
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
        # CHG-SCPT-2026-655：首页的“最近 7 天发生了什么”默认收起，先点开再量
        fold = next(f for f in page.findChildren(board_widgets.Fold) if f.property("fold") == "activity")
        assert not fold.body.isVisible()
        QTest.mouseClick(fold.head, Qt.MouseButton.LeftButton)
        qapp.processEvents()
        assert fold.body.isVisible()
        label = next(item for item in page.findChildren(QLabel) if item.text().startswith("进行中：") and long_title[:6] in item.text())
        assert label.width() > 400, label.width()  # 窄一列时只有 100 来像素
        assert label.height() < 40, label.height()  # 没被挤成好几行
    window.open_project("DJ-2026-101")
    qapp.processEvents()
    label = next(item for item in window.project.findChildren(QLabel) if item.text().startswith("进行中：") and long_title[:6] in item.text())
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
        "看板_PR与审计.png",  # 骨架 D 加的三页不起命令，可以离屏截（读命令的四页要真账本，不截）
        "看板_全部项目.png",
        "看板_命令与契约.png",
        "看板_工具.png",
        "看板_工程工位.png",
        "看板_流程图.png",
        "看板_脊柱图.png",
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
    # CHG-SCPT-2026-655：六项检查从格子改成一行灯，另加一盏 GitHub 汇总灯
    lamps = [frame for frame in window.home.findChildren(board_widgets.ClickBox) if frame.objectName() == "lamp"]
    assert len(lamps) == 7 and [lamp.property("lamp_key") for lamp in lamps][-1] == "github"
    values = [label for lamp in lamps for label in lamp.findChildren(QLabel) if label.objectName() == "lampvalue"]
    assert len(values) == 7
    states = {label.property("state") for label in values}
    assert "unchecked" in states
    for lamp, label in zip(lamps, values, strict=True):
        assert lamp.property("state") == label.property("state")
        if label.property("state") != "number":
            assert label.text() in policy.UNCHECKED_TEXTS
            assert label.text() != "0"
            assert lamp.property("sev") == "na"  # 没检查的不标色，更不是绿
            dot = next(item for item in lamp.findChildren(QLabel) if item.objectName() == "dot")
            assert dot.text() == "○"
    assert any("空心灰圈是没检查，不是 0" in text for text in _texts(window.home))
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
    # 写文件只有三处：actions.py 追加一行 BC（带预览）、actions.write_snapshot 存“上次读取”快照（只写
    # .auto-pm/cache/cockpit_board/，CHG-SCPT-2026-628 骨架 B）；app.py 只在启动出错时写系统临时目录
    app_source = sources[PACKAGE / "app.py"]
    assert app_source.count("write_text(") == 1
    assert "tempfile.gettempdir()" in app_source.split("def _crash_report", 1)[1]
    actions_source = sources[PACKAGE / "actions.py"]
    assert len(re.findall(WRITES, actions_source)) == 2
    assert len(re.findall(WRITES, actions_source.split("def write_snapshot", 1)[1])) == 1  # 快照那一处在 write_snapshot 里
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
        # CHG-SCPT-2026-655：“交出去的东西”那一块从首页搬到了“PR 与审计”页，首页只留一盏汇总灯
        assert [f for f in window.home.findChildren(QFrame) if f.property("github_state")] == []
        assert any(t == "交出去的东西" for t in _texts(window.prs))
        for page in (window.prs, window.project):
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


# ---------------------------------------------------------------- 项目生命周期入口（CHG-SCPT-2026-654）

LIFECYCLE_WORDS = {"归档…", "重新激活…", "确认归档", "确认重新激活", "重新检查"}
NEW_PROJECT = "新建项目…"


def _archive_first_project(root: Path) -> None:
    import json

    registry = root / pd_module.REGISTRY_RELATIVE
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["projects"][0].update({"kind": "equipment", "status": "archived"})  # DJ-2026-101
    registry.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _wait_decisions(window: Any, qapp: QApplication) -> None:
    for _ in range(200):
        for job in list(window.decisions._jobs):
            job.wait(2000)
        qapp.processEvents()
        if not window.decisions._jobs:
            break
    qapp.processEvents()


def _click(page: QWidget, text: str) -> None:
    button = next(b for b in _buttons(page) if b.text() == text)
    assert button.isEnabled(), text
    button.click()


def test_lifecycle_buttons_only_appear_on_their_own_page(qapp: QApplication, tmp_path: Path) -> None:
    """验收第 12 条：PM_BUTTONS 是几页共用的白名单，拦不住按钮跑错页，所以逐页清点：
    “归档…”“重新激活…”“确认归档”“确认重新激活”“重新检查”只在项目详情页；“新建项目…”只在全部项目页。"""
    from tests.core import test_cockpit_decisions_widgets as dw

    root, db = base._workspace(tmp_path, [("SW-2026-008", "ACTIVE", "写通讯层", 0.1)])
    _archive_first_project(root)
    window = _window(qapp, root, db, no_github=True)
    fake = dw.LifecycleCli()
    window.decisions.runner = fake
    seen: dict[str, set[str]] = {"home": set(), "issues": set(), "projects": set(), "project": set()}

    def count() -> None:
        for key in seen:
            page = getattr(window, key)
            seen[key] |= {b.text() for b in _buttons(page)}
            for button in _buttons(page):
                lowered = (button.text() + button.toolTip()).lower()
                assert not any(word in lowered for word in policy.PM_FORBIDDEN_WORDS), button.text()

    count()
    window.open_project("SW-2026-008")  # 在研的项目：归档…
    _wait_decisions(window, qapp)
    count()
    _click(window.project, "归档…")
    _wait_decisions(window, qapp)
    count()
    window.open_project("DJ-2026-101")  # 已归档的项目：重新激活…
    count()
    _click(window.project, "重新激活…")
    _wait_decisions(window, qapp)
    count()
    for key in ("home", "issues", "projects", "tools", "decisions"):
        window.goto(key)
        qapp.processEvents()
        count()
    assert seen["project"] & LIFECYCLE_WORDS == LIFECYCLE_WORDS  # 五个键都真的画出来过，不是空清点
    for key in ("home", "issues", "projects"):
        assert not seen[key] & LIFECYCLE_WORDS, (key, seen[key] & LIFECYCLE_WORDS)
    assert NEW_PROJECT in seen["projects"]
    for key in ("home", "issues", "project"):
        assert NEW_PROJECT not in seen[key], key
    everywhere = {b.text() for b in _buttons(window)}
    assert not {text for text in everywhere if "删除" in text or "恢复" in text}  # 删除、恢复两个动作没有任何入口
    assert not (LIFECYCLE_WORDS | {NEW_PROJECT}) & {b.text() for b in _buttons(window.tools)}
    assert not (LIFECYCLE_WORDS | {NEW_PROJECT}) & {b.text() for b in _buttons(window.decisions.page)}
    assert seen["home"] | seen["issues"] | seen["projects"] | seen["project"] <= policy.PM_BUTTONS
    assert not any("--confirm" in call for call in fake.calls)  # 只点了预演：没有任何一条带 --confirm 的命令
    for kind in (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox):
        assert window.project.findChildren(kind) == [], kind.__name__  # 预演之后项目详情页也没有任何能输字的地方
    window.close()


def test_new_project_button_jumps_to_the_project_tab_and_asks_for_a_probe(qapp: QApplication, tmp_path: Path) -> None:
    from tests.core import test_cockpit_decisions_widgets as dw

    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = _window(qapp, root, db, no_github=True)
    fake = dw.LifecycleCli(help_kind=False)
    window.decisions.runner = fake
    window.goto("projects")
    _click(window.projects, NEW_PROJECT)
    _wait_decisions(window, qapp)
    assert window.current == "tools" and window.stack.currentWidget() is window.tools
    assert window.tools.tab_buttons["project"].isChecked() and window.tools.pages["project"].isVisibleTo(window.tools)
    assert [call for call in fake.calls if "--help" in call] == [
        ["project", "archive", "--help"], ["project", "reactivate", "--help"], ["project", "register", "--help"]]
    assert all("--help" in call for call in fake.calls)  # 跳页只探测，不起别的命令
    # 本机的 register 没有 --kind：登记表单的“性质”灰着，写明原因
    assert not window.tools.inputs["register_kind"].isEnabled()
    assert window.tools.register_kind_note.text() == "发版切换后可填；现在登记后显示‘未分类’"
    # 工作区里找到、还没登记的项目递进了登记表单的下拉
    pick = window.tools.inputs["register_pick"]
    assert [pick.itemData(i) for i in range(pick.count())] == ["", "DJ-2026-102"]
    window.close()


def test_missing_commands_grey_the_lifecycle_buttons_until_a_manual_reload_finds_them(qapp: QApplication, tmp_path: Path) -> None:
    """验收第 8 条（整窗）：探测报 No such command → 两个键灰着，旁边有“本机发布版太旧”那句；探测超时也灰着；
    换成正常的命令后点“重新读取”，重探，变亮。10 分钟定时那一轮不重探。"""
    from tests.core import test_cockpit_decisions_widgets as dw

    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = _window(qapp, root, db, no_github=True)

    def archive_button() -> Any:
        return next(b for b in _buttons(window.project) if b.text() == "归档…")

    window.decisions.runner = dw.LifecycleCli(missing=("archive", "reactivate"))
    window.open_project("DJ-2026-101")
    _wait_decisions(window, qapp)
    assert not archive_button().isEnabled()
    assert any(t.startswith("本机发布版太旧：没有这条命令（等部署新版本后再看）") for t in _texts(window.project))
    window.tools.select_tab("project")
    assert window.tools.inputs["register_kind"].isEnabled()  # register 这条有 --kind：性质可填

    window.decisions.runner = dw.LifecycleCli(timeout=True)
    window.auto_reload()  # 定时刷新：不重探，仍是上一轮的结果
    _wait_threads(window, qapp)
    _wait_decisions(window, qapp)
    assert any(t.startswith("本机发布版太旧") for t in _texts(window.project))
    window.reload()  # 手动“重新读取”：重探；这回超时，照样灰着，不当成有这条命令
    _wait_threads(window, qapp)
    _wait_decisions(window, qapp)
    assert not archive_button().isEnabled()
    assert any(t.startswith("没探测成，不当成有这条命令：") and "超时" in t for t in _texts(window.project))
    assert not window.tools.inputs["register_kind"].isEnabled() and "超时" in window.tools.register_kind_note.text()

    fake = dw.LifecycleCli()
    window.decisions.runner = fake
    window.reload()
    _wait_threads(window, qapp)
    _wait_decisions(window, qapp)
    assert archive_button().isEnabled() and window.tools.inputs["register_kind"].isEnabled()
    assert window.tools.register_kind_note.text() == ""
    window.close()


def test_manual_reload_voids_the_dry_run_but_the_timer_round_does_not(qapp: QApplication, tmp_path: Path) -> None:
    from tests.core import test_cockpit_decisions_widgets as dw

    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = _window(qapp, root, db, no_github=True)
    window.decisions.runner = dw.LifecycleCli()
    window.open_project("DJ-2026-101")
    _wait_decisions(window, qapp)
    _click(window.project, "归档…")
    _wait_decisions(window, qapp)
    assert {"确认归档", "重新检查"} <= {b.text() for b in _buttons(window.project)}
    window.auto_reload()
    _wait_threads(window, qapp)
    _wait_decisions(window, qapp)
    assert "确认归档" in {b.text() for b in _buttons(window.project)}  # 定时刷新、别的重画：预演还在
    window.reload()
    _wait_threads(window, qapp)
    _wait_decisions(window, qapp)
    texts = {b.text() for b in _buttons(window.project)}
    assert "确认归档" not in texts and "重新检查" not in texts and "归档…" in texts  # 点了“重新读取”：要重新点“归档…”
    window.close()


def test_without_an_entry_script_the_window_never_spawns_a_probe(qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """控制根里没有 main.py（测试用的假工作区就是这样）：探测不起进程，按钮灰着并写明原因。"""
    from cockpit_board import actions as actions_module

    monkeypatch.setattr(actions_module, "run_read", lambda *_a, **_k: pytest.fail("不该起进程"))
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = _window(qapp, root, db, no_github=True)
    window.open_project("DJ-2026-101")
    assert window.decisions._jobs == []
    button = next(b for b in _buttons(window.project) if b.text() == "归档…")
    assert not button.isEnabled() and any("控制根里没有 main.py" in t for t in _texts(window.project))
    window.close()


# ---------------------------------------------------------------- 首页按方案丙重做（CHG-SCPT-2026-655）

SIX_L_WORDS = ("归档…", "重新激活…", "确认归档", "确认重新激活", "重新检查", "新建项目…")


def _boxes(window: Any, name: str = "") -> list[Any]:
    return [box for box in window.home.findChildren(board_widgets.ClickBox) if not name or box.objectName() == name]


def _number(window: Any, key: str) -> Any:
    return next(f for f in window.home.findChildren(QFrame) if f.objectName() == "numbox" and f.property("number_key") == key)


def _number_text(window: Any, key: str) -> str:
    return str(next(label.text() for label in _number(window, key).findChildren(QLabel) if label.objectName() == "num"))


def _numbers_workspace(tmp_path: Path) -> tuple[Path, Path]:
    """四个数各不为 0（同 test_cockpit_board._numbers_board）：101 一张等你的、一张真在跑的、一张失联的；008 全关了留旧账。"""
    import sqlite3

    root, db = base._workspace(
        tmp_path,
        [("DJ-2026-101", "AWAITING_APPROVAL", "等批的", 1), ("DJ-2026-101", "ACTIVE", "真在跑的", 0.005),
         ("DJ-2026-101", "ACTIVE", "失联的", 2 / 24), ("SW-2026-008", "CLOSED", "早关了的", 20)],
    )
    connection = sqlite3.connect(db)
    connection.execute("UPDATE work_items SET state = 'BLOCKED' WHERE title = '早关了的'")
    connection.commit()
    connection.close()
    return root, db


def _waiting_signature() -> Any:
    import github_collector as gh

    pull = gh.PullInfo(7, "改 OB1", "https://example.invalid/pull/7", "baiyangfu-hash", "a" * 40, "claude/x", False, "2026-10-22T09:00:00Z",
                       projects=["DJ-2026-101"], plc=True, ci=[gh.CiState("plc-ci", "pass", "过")], safety=gh.Safety("waiting", "是", "等签"))
    return gh.Snapshot("o/r", "ok", NOW, NOW, pulls=[pull], authenticated=True)


def test_655_home_buttons_are_two_fixed_words_and_none_runs_a_command(qapp: QApplication, tmp_path: Path) -> None:
    """验收 5、6、14：首页真按钮只有“去「决定」页办”“复制”，都在白名单里、没有禁用词；单 L 的六个词不上首页。"""
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "AWAITING_APPROVAL", "等批的", 5)])
    copied: list[str] = []
    window = _window(qapp, root, db)
    window.copy_text = copied.append
    window.home.on_copy = copied.append
    window._refresh_decisions = lambda: None  # 只看跳没跳到那一页；决定页自己读什么由它的测试管
    window._render()
    buttons = {b.text(): b for b in _buttons(window.home)}
    assert set(buttons) == {"去「决定」页办", "复制"} and set(buttons) <= policy.PM_BUTTONS
    for button in buttons.values():
        lowered = (button.text() + button.toolTip()).lower()
        assert not any(word in lowered for word in policy.PM_FORBIDDEN_WORDS), button.text()
    assert not set(SIX_L_WORDS) & set(_texts(window.home)) and not set(SIX_L_WORDS) & set(buttons)
    assert window.home_vm.focus.decision.kind == "mission"
    texts = _texts(window.home)
    assert "要你定：范围认不认" in texts and any(t.startswith("等了 5 天 · 从卡停到这一步那天算") for t in texts)
    assert f"共 {window.home_vm.decisions_total} 件" in texts and "这件事不对应某一张卡" not in texts
    # mission 类的事指的那张卡是红格
    red = [box.property("mission_id") for box in _boxes(window, "cardrow") if box.property("strip_sev") == "block"]
    assert window.home_vm.focus.decision.mission_id in red
    buttons["复制"].click()
    assert copied == [window.home_vm.focus.decision.reply] and window.stack.currentWidget() is window.home
    buttons["去「决定」页办"].click()
    assert window.stack.currentWidget() is window.decisions.page
    window.close()


def test_655_focus_block_other_kind_empty_and_unread_ledger(qapp: QApplication, tmp_path: Path) -> None:
    """验收 5：other 类的事不出现“去「决定」页办”；没有要办的写“现在没有要你办的。”；账本读不到写“没检查”。"""
    root, db = base._workspace(tmp_path / "other", [("DJ-2026-101", "ACTIVE", "真在跑的", 0.005)])
    window = _window(qapp, root, db)  # 假工作空间自带一条待批的业务变更：other 类
    assert window.home_vm.focus.decision.kind == "other"
    assert {b.text() for b in _buttons(window.home)} == {"复制"}
    texts = _texts(window.home)
    assert "这件事在线程里回一句话，由主执行去办" in texts and "这件事不对应某一张卡" in texts
    # 没有要办的
    for project in window.board.projects:
        project.changes.clear()
    window._render()
    assert window.home_vm.decisions_total == 0
    assert "现在没有要你办的。" in _texts(window.home) and _buttons(window.home) == []
    window.close()
    # 账本读不到：不能写“没有要你办的”
    root, db = base._workspace(tmp_path / "unread", [])
    db.unlink()
    for suffix in ("-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    window = _window(qapp, root, db)
    for project in window.board.projects:
        project.changes.clear()
    window._render()
    texts = _texts(window.home)
    assert "现在没有要你办的。" not in texts and "现在没有开着的卡。" not in texts
    focus_block = window.home.blocks[1]
    assert [label.text() for label in focus_block.findChildren(QLabel) if label.objectName() == "state"] == ["没检查"]
    assert not any(t.startswith("其余 ") for t in texts)  # 哪些项目没有开着的卡也不知道
    # 四个数都写“没检查”，四个数里没有“0”
    for key in ("user", "running", "lead", "old"):
        assert _number_text(window, key) == "没检查"
        assert not any(ch.isdigit() for label in _number(window, key).findChildren(QLabel) for ch in label.text())
        assert _number(window, key).property("sev") == "na"
    window.close()


def test_655_the_three_numbers_jump_to_the_issues_page_with_the_same_counts(qapp: QApplication, tmp_path: Path) -> None:
    """验收 3：四个数各不为 0；点“旧账”问题页只列旧账、条数相同；“AI 那边要收拾”同理；
    点“要你办”那一行写的 N 等于首页的数，列出的 M 条加写明的 K 件等于 N（造数里有一条 PR 等签字，K 不为 0）。"""
    root, db = _numbers_workspace(tmp_path)
    window = _window(qapp, root, db)
    window.github = _waiting_signature()
    window._render()
    shown = {key: int(_number_text(window, key)) for key in ("user", "running", "lead", "old")}
    assert all(value > 0 for value in shown.values()), shown
    assert not isinstance(_number(window, "running"), board_widgets.ClickBox)  # “AI 在干”不可点
    assert "真在跑的" in _number(window, "running").toolTip()

    def issue_cards() -> list[Any]:
        return [f for f in window.issues.findChildren(QFrame) if f.objectName() == "card" and f.property("sev") in ("block", "risk", "hint")]

    QTest.mouseClick(_number(window, "old"), Qt.MouseButton.LeftButton)
    assert window.stack.currentWidget() is window.issues
    assert len(window.issues.shown) == len(issue_cards()) == shown["old"]
    assert all(issue.basis == vm_module.OLD_BASIS for issue in window.issues.shown)
    assert any(t.startswith("现在只列旧账") for t in _texts(window.issues))

    window.goto("home")
    QTest.mouseClick(_number(window, "lead"), Qt.MouseButton.LeftButton)
    assert window.stack.currentWidget() is window.issues
    assert len(window.issues.shown) == len(issue_cards()) == shown["lead"]
    assert all(i.owner == vm_module.OWNER_LEAD and i.basis != vm_module.OLD_BASIS for i in window.issues.shown)

    window.goto("home")
    QTest.mouseClick(_number(window, "user"), Qt.MouseButton.LeftButton)
    assert window.stack.currentWidget() is window.issues
    line = next(label.text() for label in window.issues.findChildren(QLabel) if label.property("user_line"))
    found = re.fullmatch(r"要你办共 (\d+) 件：这页列 (\d+) 条；另有 (\d+) 件是 PR 上等你签的、老后台补的，在「要你出手」页和「PR 与审计」页", line)
    assert found is not None, line
    total, listed, elsewhere = (int(group) for group in found.groups())
    assert total == shown["user"] == window.home_vm.decisions_total
    assert listed == len(window.issues.shown) == len(issue_cards()) and all(i.owner == vm_module.OWNER_USER for i in window.issues.shown)
    assert elsewhere == 1 and listed + elsewhere == total
    # 没有 PR 等签字时不写后半句
    window.github = None
    window._render()
    line = next(label.text() for label in window.issues.findChildren(QLabel) if label.property("user_line"))
    assert re.fullmatch(r"要你办共 (\d+) 件：这页列 \1 条", line), line
    window.close()


def _first_screen_window(qapp: QApplication, tmp_path: Path) -> Any:
    """验收 8 的固定造数：1 件要办（假工作空间自带的那条业务变更）、2 个项目各 1 张卡。标题不含编号和英文。"""
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.005), ("SW-2026-008", "ACTIVE", "改看板首页", 0.005)])
    window = _window(qapp, root, db)
    assert window.home_vm.decisions_total == 1 and [len(g.cards) for g in window.home_vm.groups] == [1, 1]
    window.resize(1366, 768)
    window.show()
    qapp.processEvents()
    qapp.processEvents()
    return window


def test_655_first_screen_needs_no_scrolling_at_1366_by_768(qapp: QApplication, tmp_path: Path) -> None:
    """验收 8：窗口 1366×768，第 1～4 块每块的底边都在滚动区可见范围内，并留 24 像素余量。按几何位置判，不比像素。"""
    window = _first_screen_window(qapp, tmp_path)
    assert (window.width(), window.height()) == (1366, 768)
    viewport = window.home.scroll_area.viewport()
    assert window.home.scroll_area.verticalScrollBar().value() == 0
    previous = -1
    for number in (1, 2, 3, 4):
        block = window.home.blocks[number]
        assert block.isVisible() and block.height() > 0
        bottom = block.mapTo(viewport, QPoint(0, block.height())).y()
        assert previous < bottom <= viewport.height() - 24, (number, bottom, viewport.height())
        previous = bottom
    assert window.home.blocks[5].isVisible()
    window.close()


def test_655_first_screen_shows_no_internal_ids_and_no_placeholder(qapp: QApplication, tmp_path: Path) -> None:
    """验收 9：首页没有占位卡；首屏看得见的字里没有 CLOSURE- 这类编号、没有 --xxx 命令参数、没有连写三个以上的大写英文。"""
    window = _first_screen_window(qapp, tmp_path)
    assert [f for f in window.home.findChildren(QFrame) if f.property("placeholder")] == []
    visible = [label.text() for label in window.home.findChildren(QLabel) if label.isVisible()]
    assert len(visible) > 30
    for pattern in (r"[A-Z]{3,}-[A-Z0-9]", r"--[a-z]", r"[A-Z]{3,}"):
        assert [t for t in visible if re.search(pattern, t)] == [], pattern
    assert not any("这一块还没做" in t for t in _texts(window.home))
    window.close()


def test_655_every_click_box_takes_keyboard_focus_and_enter_equals_a_click(qapp: QApplication, tmp_path: Path) -> None:
    """验收 11：首页每个可点的框都能拿到键盘焦点；对着“旧账”那个数按回车，和鼠标点它一样跳到问题页并只列旧账。"""
    root, db = _numbers_workspace(tmp_path)
    window = _window(qapp, root, db)
    window.show()
    qapp.processEvents()
    boxes = _boxes(window)
    assert {box.objectName() for box in boxes} == {"numbox", "lamp", "cardrow", "projectrow", "foldhead"}
    for box in boxes:
        assert box.focusPolicy() == Qt.FocusPolicy.StrongFocus, box.objectName()
        box.setFocus()
        qapp.processEvents()
        assert box.hasFocus(), box.objectName()
    old = _number(window, "old")
    old.setFocus()
    QTest.keyClick(old, Qt.Key.Key_Return)
    assert window.stack.currentWidget() is window.issues
    assert window.issues.shown and all(issue.basis == vm_module.OLD_BASIS for issue in window.issues.shown)
    by_mouse = list(window.issues.shown)
    window.issues.set_old("hide")
    window.goto("home")
    QTest.keyClick(_number(window, "old"), Qt.Key.Key_Space)
    assert window.stack.currentWidget() is window.issues and window.issues.shown == by_mouse
    window.goto("home")
    QTest.keyClick(_number(window, "old"), Qt.Key.Key_A)  # 别的键不算
    assert window.stack.currentWidget() is window.home
    window.close()


@pytest.mark.parametrize("how", ["mouse", "keyboard"])
def test_655_click_boxes_only_change_page_or_fold(qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, how: str) -> None:
    """验收 12：首页所有可点的框逐个点一遍（鼠标）、逐个触发一遍（键盘）。每次之后：只换了页、设了筛选或展开收起；
    没有起任何命令（起命令的入口全换成一碰就记账并报错的替身）；工作区每个文件的修改时间都没变；
    框自己的提示和无障碍名称里没有禁用词。"""
    from cockpit_board import actions as actions_module
    from cockpit_board import tool_actions as tool_actions_module

    spawned: list[str] = []

    def trap(name: str) -> Any:
        def boom(*_args: Any, **_kwargs: Any) -> Any:
            spawned.append(name)
            raise AssertionError(f"首页可点的框不该起命令：{name}")
        return boom

    for name in ("run_cli", "run_read", "open_console", "run_check"):
        monkeypatch.setattr(actions_module, name, trap(name))
    for name in ("run_tool", "open_workbench"):
        monkeypatch.setattr(tool_actions_module, name, trap(name))
    root, db = _numbers_workspace(tmp_path)
    window = _window(qapp, root, db)
    window.github = _waiting_signature()
    window._render()
    window.show()
    qapp.processEvents()
    before = _files(root)
    count = len(_boxes(window))
    kinds: set[str] = set()
    assert count >= 15
    for index in range(count):
        window.goto("home")
        box = _boxes(window)[index]
        kind = box.objectName()
        kinds.add(kind)
        for text in (box.toolTip(), box.accessibleName()):
            assert text and not any(word in text.lower() for word in policy.PM_FORBIDDEN_WORDS), (kind, text)
        folded = {fold.property("fold"): fold.opened for fold in window.home.findChildren(board_widgets.Fold)}
        if how == "mouse":
            QTest.mouseClick(box, Qt.MouseButton.LeftButton)
        else:
            box.setFocus()
            QTest.keyClick(box, Qt.Key.Key_Return)
        qapp.processEvents()
        current = window.stack.currentWidget()
        if kind == "numbox":
            assert current is window.issues
            wanted = {"user": ("user", "hide"), "lead": ("lead", "hide"), "old": ("all", "only")}[box.property("number_key")]
            assert (window.issues.who, window.issues.old) == wanted and window.issues.filter == "all"
        elif kind == "lamp" and box.property("lamp_key") == "github":
            assert current is window.prs
        elif kind == "lamp":
            # 点一盏灯：下面展开这项检查的说明；再点同一盏收起。别的什么都不动
            check = next(k for k in window.home_vm.checks if k.key == box.property("lamp_key"))
            assert current is window.home and window.home.lamp_note.isVisible()
            assert window.home.lamp_note.text() == f"{check.label}：{check.note}"
            QTest.mouseClick(box, Qt.MouseButton.LeftButton)
            assert window.stack.currentWidget() is window.home and not window.home.lamp_note.isVisible()
        elif kind == "cardrow":
            assert current is window.flow and window.flow.card_box.currentData() == box.property("mission_id")
            assert window.flow.graph_id == "mission"
        elif kind == "projectrow":
            assert current is window.project and window.project.vm.card.project_id == box.property("project_id")
        else:
            assert kind == "foldhead" and current is window.home
            now = {fold.property("fold"): fold.opened for fold in window.home.findChildren(board_widgets.Fold)}
            assert sum(1 for key in now if now[key] != folded[key]) == 1
        assert spawned == []
        assert window.decisions._jobs == []
        assert _files(root) == before, kind
    assert kinds == {"numbox", "lamp", "cardrow", "projectrow", "foldhead"}
    window.close()


def test_655_archived_projects_are_only_counted_on_the_home_page(qapp: QApplication, tmp_path: Path) -> None:
    """验收 7：已归档的项目不进“项目和卡”，折叠行末尾写“另有 N 个已归档”。"""
    import json

    root, db = base._workspace(tmp_path, [("DJ-2026-101", "AWAITING_APPROVAL", "等批的", 1), ("SW-2026-008", "ACTIVE", "真在跑的", 0.005)])
    registry = root / pd_module.REGISTRY_RELATIVE
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["projects"][0]["status"] = "archived"
    registry.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    window = _window(qapp, root, db)
    assert [box.property("project_id") for box in _boxes(window, "projectrow")] == ["SW-2026-008"]
    texts = _texts(window.home)
    assert "另有 1 个已归档（到「全部项目」页勾选“显示已归档”可看）" in texts
    assert not any("等批的" in t for t in _texts(window.home.blocks[3]))  # “项目和卡”那一块里没有已归档项目的卡
    window.close()


def test_655_projects_and_cards_block_rows_strip_and_quiet_fold(qapp: QApplication, tmp_path: Path) -> None:
    root, db = _numbers_workspace(tmp_path)
    window = _window(qapp, root, db)
    rows = {next(label.text() for label in box.findChildren(QLabel)): box for box in _boxes(window, "cardrow")}
    assert set(rows) == {"等批的", "真在跑的", "失联的"}

    def cells(box: Any) -> list[tuple[str, str, str]]:
        return [(label.text(), label.property("at"), label.property("sev") or "")
                for label in box.findChildren(QLabel) if label.objectName() == "cell"]

    assert cells(rows["等批的"]) == [("✓ 草稿", "done", ""), ("■ 等批准", "current", "block"), ("进行中", "todo", ""),
                                  ("等验收", "todo", ""), ("已验收", "todo", ""), ("已关闭", "todo", "")]
    assert cells(rows["失联的"])[2] == ("● 进行中", "current", "risk")
    assert cells(rows["真在跑的"])[2] == ("进行中", "current", "")
    texts = _texts(window.home)
    assert "开着 3 张卡" in texts and "主执行：执行者失联" in texts and any(t.startswith("等你：批准范围 · 等了") for t in texts)
    assert "其余 2 个项目没有开着的卡；其中 1 个留有旧账 2 条" in texts and "没有已归档的项目" in texts
    fold = next(f for f in window.home.findChildren(board_widgets.Fold) if f.property("fold") == "quiet")
    assert not fold.body.isVisible()
    fold.set_open(True)
    window._render()  # 重画以后折叠项还开着
    fold = next(f for f in window.home.findChildren(board_widgets.Fold) if f.property("fold") == "quiet")
    assert fold.opened and "SW-2026-008 SW-2026-008 · 旧账 2 条" in _texts(fold.body)
    window.close()


def test_655_no_open_cards_says_so(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [])
    window = _window(qapp, root, db)
    assert "现在没有开着的卡。" in _texts(window.home) and _boxes(window, "cardrow") == []
    window.close()


def test_655_focus_fold_shows_card_id_basis_and_the_display_only_command(qapp: QApplication, tmp_path: Path) -> None:
    """用户亲手验第 3 步：点“依据和编号”，能看到卡号和要办时用的命令；命令只是字，后面跟固定的那句提醒。"""
    from cockpit_board import viewmodel
    from cockpit_board.widgets import home as home_module

    decision = viewmodel.Decision("block", "DJ-2026-101", "等你超过 3 天：已批准，还没开工", "批了还没开工", "批了还没开工 看过了", "依据句",
                                  NOW - timedelta(days=6), kind="mission", mission_id="MISSION-0", change_id="CHG-DOCU-2026-055",
                                  command="main.py pm retire --pid DJ-2026-101 --mission-id MISSION-0")
    rows = dict(home_module.focus_details(viewmodel.focus_of(decision, {"DJ-2026-101": "甲"})))
    assert rows["卡号"] == "MISSION-0" and rows["变更单号"] == "CHG-DOCU-2026-055" and rows["依据"] == "依据句"
    command = rows["要收掉这张卡，在终端运行（这里只显示）"]
    assert command == "main.py pm retire --pid DJ-2026-101 --mission-id MISSION-0（这条命令要本机发布版在 647 之后才有；报 No such command 就先别收）"
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "AWAITING_APPROVAL", "等批的", 5)])
    window = _window(qapp, root, db)
    window.show()
    qapp.processEvents()
    fold = next(f for f in window.home.findChildren(board_widgets.Fold) if f.property("fold") == "focus")
    assert not fold.body.isVisible() and "MISSION-0" in _texts(fold.body)
    QTest.mouseClick(fold.head, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert fold.body.isVisible() and _buttons(fold) == []
    window.close()
