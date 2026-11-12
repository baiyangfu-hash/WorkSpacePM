"""总控屏小部件的判空与重名修复（TD-SW008-178）：

- ``insert_widget`` 往一行里插控件，没有盒布局就报错，不再靠 ``layout().insertWidget`` 碰运气；
- ``clear`` 连嵌套布局一起清；
- 页面类不再占用 ``QWidget.scroll`` / ``QWidget.render`` 这两个 Qt 自带名字；
- 还没画过的问题页 / 项目页切过滤、切标签不炸。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pm_dashboard as pd  # noqa: E402
from cockpit_board import viewmodel as vm  # noqa: E402
from cockpit_board.widgets import common as c  # noqa: E402
from cockpit_board.widgets.issues import IssuesPage  # noqa: E402
from cockpit_board.widgets.project_page import ProjectPage  # noqa: E402

from tests.core import test_cockpit_board as board_tests  # noqa: E402
from tests.core import test_pm_dashboard as base  # noqa: E402


def _order(holder: QWidget) -> list[str]:
    layout = holder.layout()
    assert layout is not None
    labels = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        assert item is not None
        widget = item.widget()
        assert isinstance(widget, QLabel)
        labels.append(widget.text())
    return labels


def test_insert_widget_puts_the_tag_at_the_requested_slot(qapp: QApplication) -> None:
    row = c.hrow(c.label("a"), c.label("b"), c.label("c"))
    c.insert_widget(row, 1, c.example_tag())
    assert _order(row) == ["a", "示例", "b", "c"]


def test_insert_widget_refuses_a_holder_without_a_box_layout(qapp: QApplication) -> None:
    bare = QWidget()
    with pytest.raises(TypeError):
        c.insert_widget(bare, 0, c.label("x"))
    grid_holder, _grid = c.grid(2)
    with pytest.raises(TypeError):
        c.insert_widget(grid_holder, 0, c.label("x"))


def test_clear_empties_nested_layouts_too(qapp: QApplication) -> None:
    host = QWidget()
    outer = QVBoxLayout(host)
    outer.addWidget(c.label("top"))
    inner = QHBoxLayout()
    inner.addWidget(c.label("nested"))
    outer.addLayout(inner)
    assert outer.count() == 2
    c.clear(outer)
    assert outer.count() == 0
    assert inner.count() == 0


def test_page_classes_do_not_shadow_qt_names(qapp: QApplication) -> None:
    for page in (IssuesPage(lambda _pid: None), ProjectPage(lambda: None, lambda _text: None)):
        assert callable(page.scroll)  # 还是 Qt 自带的 QWidget.scroll
        assert page.scroll_area is not None
        assert type(page).render is QWidget.render  # 没被页面类盖掉


def test_issue_filter_before_first_render_does_nothing_and_does_not_raise(qapp: QApplication) -> None:
    page = IssuesPage(lambda _pid: None)
    page.set_filter("block")
    assert page.filter == "block"
    assert page.layout_.count() == 0  # 还没有“现在”，不画；第一次 show_view 才画


def test_project_tab_before_first_render_does_nothing_and_does_not_raise(qapp: QApplication) -> None:
    page = ProjectPage(lambda: None, lambda _text: None)
    page.set_tab("board")
    assert page.tab == "board"
    assert page.layout_.count() == 0


def test_issues_page_says_which_kinds_were_not_checked_before_the_counts(qapp: QApplication) -> None:
    from datetime import datetime

    page = IssuesPage(lambda _pid: None)
    page.show_view([], datetime(2026, 11, 1, 12, 0), ["GitHub 这次没读到（断网）：PR 门禁红这类问题没检查，这页的条数不含它们。"])
    texts = [str(label.text()) for label in page.findChildren(QLabel)]
    assert any(text.startswith("没检查：GitHub 这次没读到") for text in texts)
    page.set_filter("risk")  # 换档重画时说明不能丢
    assert any(str(label.text()).startswith("没检查：GitHub") for label in page.findChildren(QLabel))
    page.show_view([], datetime(2026, 11, 1, 12, 0))
    assert not any(str(label.text()).startswith("没检查：") for label in page.findChildren(QLabel))


def test_the_project_page_shows_the_more_line_and_newest_first(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [])
    board_tests._many_orders(root, [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(33)])
    board = pd.build_board(root, db, board_tests.NOW, use_git=False, use_legacy=False)
    home = vm.home_vm(board, board_tests.OFFSET, online=False, use_git=False)
    card = next(c for c in home.hot + home.rest if c.project_id == "DJ-2026-101")
    page = ProjectPage(lambda: None, lambda _text: None)
    page.show_view(vm.project_vm(board, card, board_tests.OFFSET, False), board_tests.NOW, False)
    page.set_tab("changes")
    texts = [label.text() for label in page.findChildren(QLabel)]
    assert any(t.startswith("还有 3 条") for t in texts)  # 33 张已收口的单，列最近 30，余 3；没收口的业务变更另外列
    ids = [t for t in texts if t.startswith("CHG-PLC-2026-")]
    assert ids[0] == "CHG-PLC-2026-033" and len(ids) == 30


def test_b1_05_a_closed_project_shows_an_old_records_chip_on_both_pages(qapp: QApplication, tmp_path: Path) -> None:
    """D-324（TD-SW008-589）：卡全关了的项目，首页小方块和项目页都挂“旧账”标签，颜色走提示，不走风险。"""
    from cockpit_board.widgets.home import project_tile

    board = board_tests._edited_board(
        tmp_path, [("DJ-2026-101", "CLOSED", "早关了的一张", 20)], "UPDATE work_items SET state = 'BLOCKED'"
    )
    home = vm.home_vm(board, board_tests.OFFSET, online=False, use_git=False)
    card = next(c for c in home.hot + home.rest if c.project_id == "DJ-2026-101")
    tile = project_tile(card, lambda _pid: None)
    page = ProjectPage(lambda: None, lambda _text: None)
    page.show_view(vm.project_vm(board, card, board_tests.OFFSET, False), board_tests.NOW, False)
    for holder in (tile, page):
        chips = [label for label in holder.findChildren(QLabel) if label.text() == "旧账"]
        assert [label.property("sev") for label in chips] == ["hint"]


def test_a_tile_shows_kind_and_status_and_the_fold_counts_archived(qapp: QApplication, tmp_path: Path) -> None:
    """CHG-SCPT-2026-650：小方块写“性质 · 状态”，不再按名单挂“工具”；折叠那一句单独点出已归档几个。"""
    from cockpit_board.widgets.home import project_tile, rest_summary

    root, db = base._workspace(tmp_path, [])
    registry = root / pd.REGISTRY_RELATIVE
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["projects"][0].update({"kind": "equipment", "status": "archived"})
    registry.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    board = pd.build_board(root, db, board_tests.NOW, use_git=False, use_legacy=False)
    home = vm.home_vm(board, board_tests.OFFSET, online=False, use_git=False)
    card = next(c for c in home.rest if c.project_id == "DJ-2026-101")
    tile = project_tile(card, lambda _pid: None)
    texts = [label.text() for label in tile.findChildren(QLabel)]
    assert "设备 · 已归档" in texts
    tool = next(c for c in home.hot + home.rest if c.project_id == "SW-2026-008")
    tool_tile = project_tile(tool, lambda _pid: None)
    tool_texts = [label.text() for label in tool_tile.findChildren(QLabel)]
    assert "工具 · 在研" in tool_texts and not any(t.endswith("  工具") for t in tool_texts)
    assert rest_summary(home.rest).endswith("，1 个已归档")
    assert "已归档" not in rest_summary([c for c in home.rest if not c.archived])
