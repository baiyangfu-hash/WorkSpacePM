"""总控屏“一行放不下就换行”（用户 2026-11-01 S3 试用截图）：

“今天”页的 PR 行里有十几项检查标签，原来排成一整行（QHBoxLayout），最小宽度是全部标签之和，
整页被撑得比窗口宽，要左右拖滚动条才看得全。改成 ``common.flow``（FlowLayout）后：
- 一行放不下就换行，页面最小宽度只取最宽的一个控件；
- “名字 + 标签片”成对不拆开；
- 工程工位的身份条、第 6 步按钮行同理。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QWidget  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board.viewmodel import Cell, GithubVM, PrRow, StationVM, Step  # noqa: E402
from cockpit_board.widgets import common as c  # noqa: E402
from cockpit_board.widgets.delivery import github_block  # noqa: E402
from cockpit_board.widgets.station import StationPage  # noqa: E402

CI_NAMES = [
    "CI - PLC项目管理工具", "bat-guard", "ci-aggregate", "gitignore-guard", "hook-replay", "plc-ci", "pr-gate",
    "reviews-tools-ci", "root-tests", "safety-gate", "sample-drill", "sw008-ci", "windows-cli",
]


def _github(rows: int = 2) -> GithubVM:
    ci = [(name, Cell("过", "ok")) for name in CI_NAMES]
    title = "【草稿，PLC 恢复前不合并】plc ingest/promote 按登记表找项目目录，不再编路径" * 2
    row = PrRow(463, title, "https://example.invalid/pr/463", "a", ["SW-2026-008"], Cell("红", "block"), ci,
                Cell("没检查", "na"), Cell("未知", "na"))
    return GithubVM("ok", True, "已从 GitHub 读到", "11-01 19:25", list(ci), [row] * rows, ["说明"])


def test_many_ci_chips_do_not_widen_the_page(qapp: QApplication) -> None:
    gh = _github()
    scroll, layout = c.page()
    layout.addWidget(github_block(gh, gh.rows, "无"))
    scroll.resize(900, 700)
    scroll.show()
    qapp.processEvents()
    try:
        assert scroll.widget().minimumSizeHint().width() < 700  # 以前是全部标签之和，1900 以上
        assert scroll.horizontalScrollBar().maximum() == 0  # 窗口再窄也不用左右拖
    finally:
        scroll.close()


def test_flow_wraps_when_narrow_and_keeps_one_line_when_wide(qapp: QApplication) -> None:
    items = [c.label(f"项目{index}", wrap=False) for index in range(12)]
    holder = c.flow(*items)
    layout = holder.layout()
    assert layout is not None and layout.hasHeightForWidth()
    wide = layout.heightForWidth(4000)
    narrow = layout.heightForWidth(200)
    assert narrow > wide  # 窄了就多出几行
    widest = max(item.sizeHint().width() for item in items)
    assert layout.minimumSize().width() == widest  # 最小宽度只取最宽的一个


def test_a_pair_is_never_split_across_lines(qapp: QApplication) -> None:
    holder = c.flow(*[c.pair(c.label(f"名字{i}", wrap=False), c.chip("过", "ok")) for i in range(8)])
    holder.resize(260, 400)
    holder.show()
    qapp.processEvents()
    try:
        for pair in holder.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            labels = pair.findChildren(QLabel)
            assert len(labels) == 2
            # 名字和它的标签片在同一行（竖向位置对得上）
            tops = {label.mapTo(holder, label.rect().center()).y() for label in labels}
            assert max(tops) - min(tops) < 12
            assert pair.geometry().right() <= holder.width()  # 没有伸出窗口
    finally:
        holder.close()


def _station_vm() -> StationVM:
    """身份条各项都很长、第 6 步四个按钮加一句说明：这两处以前各是一整行横排。"""
    identity = [
        ("身份", "工程工位 · 人工"), ("源码", "1.3.3-163c7a3-dirty-很长的版本说明"), ("生效版本", "1.3.3-163c7a3"),
        ("控制根", r"C:\Users\fubai\Documents\My_Workspace"), ("网络", "离线（git ls-remote 3 秒超时）"),
        ("采集", "11-02 02:34"),
    ]
    steps = [
        Step(1, "开分支", "从 origin/main 切人工分支", "done", "git switch -c manual/x origin/main"),
        Step(
            6, "有网之后", "推 manual/ 分支、开 PR", "todo", "",
            [("推送 manual/ 分支", "push", False, "本版不做"), ("打开 GitHub 开 PR", "open_pr", False, "本版不做"),
             ("批准范围", "approve", True, ""), ("开工", "start", True, "")],
        ),
    ]
    return StationVM(identity, True, False, "", [], steps, [], [])


def test_station_identity_bar_and_last_step_buttons_do_not_widen_the_page(qapp: QApplication) -> None:
    page = StationPage(lambda _pid: None, lambda _text: None)
    page.show_view(_station_vm())
    page.resize(800, 800)
    page.show()
    qapp.processEvents()
    try:
        # 页面里还有别的不换行控件（如第 4 步表单里的安全勾选，约 570），所以不拿整页最小宽度判，
        # 而是分别量“身份条”和“第 6 步按钮行”这两处：新写法只取最宽的一个控件（约 380 以内）；
        # 身份条改回整行横排约 1500、按钮行改回整行横排约 790，Windows 字体只会更宽，两处回退都红。
        # 抽屉也叫 idbar，身份条是带 warn 属性的那一个
        bars = [f for f in page.findChildren(QFrame, "idbar") if f.property("warn") is not None]
        assert len(bars) == 1
        idbar = bars[0]
        assert idbar.minimumSizeHint().width() < 560
        button = next(b for b in page.findChildren(QPushButton) if b.property("action") == "push")
        row = button.parentWidget()
        assert row is not None and row.layout() is not None and row.layout().hasHeightForWidth()  # 是 flow，不是横排
        assert row.minimumSizeHint().width() < 560
        assert page.scroll_area.horizontalScrollBar().maximum() == 0  # 800 宽的窗口里不用左右拖
    finally:
        page.close()
