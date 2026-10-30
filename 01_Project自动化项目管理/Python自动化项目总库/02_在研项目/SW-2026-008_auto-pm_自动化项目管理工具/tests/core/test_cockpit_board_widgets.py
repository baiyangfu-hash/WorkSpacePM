"""总控屏小部件的判空与重名修复（TD-SW008-178）：

- ``insert_widget`` 往一行里插控件，没有盒布局就报错，不再靠 ``layout().insertWidget`` 碰运气；
- ``clear`` 连嵌套布局一起清；
- 页面类不再占用 ``QWidget.scroll`` / ``QWidget.render`` 这两个 Qt 自带名字；
- 还没画过的问题页 / 项目页切过滤、切标签不炸。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board.widgets import common as c  # noqa: E402
from cockpit_board.widgets.issues import IssuesPage  # noqa: E402
from cockpit_board.widgets.project_page import ProjectPage  # noqa: E402


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
