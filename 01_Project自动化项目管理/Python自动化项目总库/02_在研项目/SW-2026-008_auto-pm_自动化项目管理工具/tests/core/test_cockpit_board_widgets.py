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
from typing import Any

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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
    """D-324（TD-SW008-589）：卡全关了的项目，项目页挂“旧账”标签，颜色走提示，不走风险。
    CHG-SCPT-2026-655：首页不再有项目小方块；这种项目收在“其余 N 个项目没有开着的卡”里，写明留有旧账几条，四个数里计在“旧账”。"""
    from cockpit_board.widgets.home import HomePage

    board = board_tests._edited_board(
        tmp_path, [("DJ-2026-101", "CLOSED", "早关了的一张", 20)], "UPDATE work_items SET state = 'BLOCKED'"
    )
    home = vm.home_vm(board, board_tests.OFFSET, online=False, use_git=False)
    card = next(c for c in home.hot + home.rest if c.project_id == "DJ-2026-101")
    page = ProjectPage(lambda: None, lambda _text: None)
    page.show_view(vm.project_vm(board, card, board_tests.OFFSET, False), board_tests.NOW, False)
    chips = [label for label in page.findChildren(QLabel) if label.text() == "旧账"]
    assert [label.property("sev") for label in chips] == ["hint"]
    old = sum(1 for issue in card.issues if issue.basis == vm.OLD_BASIS)
    front = HomePage(lambda _pid: None, lambda _text: None)
    front.show_board(home, board_tests.NOW)
    texts = [label.text() for label in front.findChildren(QLabel)]
    assert old >= 1 and f"其余 3 个项目没有开着的卡；其中 1 个留有旧账 {old} 条" in texts
    assert f"DJ-2026-101 甲 · 旧账 {old} 条" in texts
    assert next(n for n in home.numbers if n.key == "old").value == old
    box = next(f for f in front.findChildren(c.ClickBox) if f.property("number_key") == "old")
    assert box.property("sev") == "na"  # 旧账是灰的，不走风险色


def test_a_tile_shows_kind_and_status_and_the_fold_counts_archived(qapp: QApplication, tmp_path: Path) -> None:
    """CHG-SCPT-2026-650：项目卡带“性质”“状态”两个词，不再按名单挂“工具”。
    CHG-SCPT-2026-655：首页不再有项目小方块（性质、状态在“全部项目”页和项目详情页看）；首页折叠行末尾单独点出已归档几个。"""
    from cockpit_board.widgets.home import HomePage

    root, db = base._workspace(tmp_path, [])
    registry = root / pd.REGISTRY_RELATIVE
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["projects"][0].update({"kind": "equipment", "status": "archived"})
    registry.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    board = pd.build_board(root, db, board_tests.NOW, use_git=False, use_legacy=False)
    home = vm.home_vm(board, board_tests.OFFSET, online=False, use_git=False)
    card = next(c for c in home.rest if c.project_id == "DJ-2026-101")
    assert (card.kind_label, card.status_label) == ("设备", "已归档")
    tool = next(c for c in home.hot + home.rest if c.project_id == "SW-2026-008")
    assert (tool.kind_label, tool.status_label) == ("工具", "在研")
    front = HomePage(lambda _pid: None, lambda _text: None)
    front.show_board(home, board_tests.NOW)
    texts = [label.text() for label in front.findChildren(QLabel)]
    assert "另有 1 个已归档（到「全部项目」页勾选“显示已归档”可看）" in texts
    assert not any(t.endswith("  工具") for t in texts)
    # 已归档的不进“项目和卡”，也不进“其余 N 个项目”（它那条待批的业务变更照旧算在“要你办”里，判定没改）
    assert [g.project_id for g in home.groups] == [] and "DJ-2026-101" not in [pid for pid, _name, _old in home.quiet]
    assert not any(t.startswith("DJ-2026-101 ") for t in texts)
    assert front.findChildren(c.ClickBox, "projectrow") == []
    home.archived_count = 0
    front.show_board(home, board_tests.NOW)
    texts = [label.text() for label in front.findChildren(QLabel)]
    assert "没有已归档的项目" in texts and not any(t.startswith("另有") for t in texts)


def test_the_projects_page_hides_archived_until_the_box_is_ticked(qapp: QApplication, tmp_path: Path) -> None:
    """CHG-SCPT-2026-652：“全部项目”页默认不列已归档的；勾上才列；双击打开的是显示出来的那一行。"""
    from cockpit_board.widgets.projects import ProjectsPage

    root, db = base._workspace(tmp_path, [])
    registry = root / pd.REGISTRY_RELATIVE
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["projects"][0].update({"kind": "equipment", "status": "archived"})  # DJ-2026-101
    registry.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    board = pd.build_board(root, db, board_tests.NOW, use_git=False, use_legacy=False)
    home = vm.home_vm(board, board_tests.OFFSET, online=False, use_git=False)
    cards = home.hot + home.rest
    assert [card.project_id for card in cards if card.archived] == ["DJ-2026-101"]

    opened: list[str] = []
    page = ProjectsPage(opened.append)
    page.show_view(cards)

    def shown() -> list[str]:
        return [page.table.item(row, 0).text().split("\n")[0] for row in range(page.table.rowCount())]

    assert not page.show_archived.isChecked() and page.show_archived.text() == "显示已归档（1 个）"
    assert "DJ-2026-101" not in shown() and shown() == [card.project_id for card in cards if not card.archived]
    for row, project_id in enumerate(shown()):  # 过滤后每一行双击打开的都是它自己
        page._open(row, 0)
        assert opened[-1] == project_id

    page.show_archived.setChecked(True)
    assert shown() == [card.project_id for card in cards]
    row = shown().index("DJ-2026-101")
    page.table.cellDoubleClicked.emit(row, 0)
    assert opened[-1] == "DJ-2026-101"

    page.show_archived.setChecked(False)
    assert "DJ-2026-101" not in shown() and len(page.cards) == page.table.rowCount()
    page._open(len(page.cards), 0)  # 行号越界不打开任何项目
    assert opened[-1] == "DJ-2026-101"

    page.show_view([card for card in cards if not card.archived])
    assert page.show_archived.text() == "显示已归档（0 个）"


# ---------------------------------------------------------------- 项目详情页“项目状态”一块、全部项目页的跳页按钮（CHG-SCPT-2026-654）


def _lifecycle_page(qapp: QApplication, tmp_path: Path, fake: Any, *, archived: bool = False, probe: bool = True) -> tuple[Any, Any, dict[str, Any]]:
    """项目详情页 + 真的“决定”控制器（命令运行器是假的）；返回 (页面, 控制器, 各项目的 ProjectVM)。"""
    from cockpit_board.decision_controller import DecisionController

    from tests.core import test_cockpit_decisions_widgets as dw

    root, db = base._workspace(tmp_path, [])
    if archived:
        registry = root / pd.REGISTRY_RELATIVE
        data = json.loads(registry.read_text(encoding="utf-8"))
        data["projects"][0].update({"kind": "equipment", "status": "archived"})  # DJ-2026-101
        registry.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    board = pd.build_board(root, db, board_tests.NOW, use_git=False, use_legacy=False)
    home = vm.home_vm(board, board_tests.OFFSET, online=False, use_git=False)
    views = {card.project_id: vm.project_vm(board, card, board_tests.OFFSET, False) for card in home.hot + home.rest}
    controller = DecisionController(tmp_path, lambda _t: None, lambda: None, runner=fake, now=lambda: dw.NOW)
    page = ProjectPage(lambda: None, lambda _text: None)
    page.set_lifecycle(controller)
    if probe:
        controller.probe_lifecycle()
        dw._wait(controller, qapp)
    return page, controller, views


def _lifecycle_buttons(page: ProjectPage) -> dict[str, QPushButton]:
    words = {"归档…", "重新激活…", "重新检查", "确认归档", "确认重新激活"}
    found = {str(b.text()): b for b in page.findChildren(QPushButton) if str(b.text()) in words}
    assert len(found) == len([b for b in page.findChildren(QPushButton) if str(b.text()) in words])  # 没有重复的键
    return found


def _show(page: ProjectPage, views: dict[str, Any], project_id: str) -> None:
    page.show_view(views[project_id], board_tests.NOW, False)


def _texts_of(page: ProjectPage) -> list[str]:
    return [str(label.text()) for label in page.findChildren(QLabel)]


def test_project_state_block_without_a_controller_only_tells_the_status(qapp: QApplication, tmp_path: Path) -> None:
    page, _controller, views = _lifecycle_page(qapp, tmp_path, None, probe=False)
    plain = ProjectPage(lambda: None, lambda _text: None)  # 没接线的页面（别的测试里就是这样用的）：只写状态，没有按钮
    _show(plain, views, "DJ-2026-101")
    assert "项目状态" in _texts_of(plain) and "在研" in _texts_of(plain) and _lifecycle_buttons(plain) == {}


def test_archive_entry_is_grey_until_probed_and_grey_with_a_reason_when_the_command_is_missing(qapp: QApplication, tmp_path: Path) -> None:
    """验收第 8 条（项目详情页一侧）：没探测到、命令不存在都灰着并写明原因；探测到了才可点。"""
    from tests.core import test_cockpit_decisions_widgets as dw

    page, controller, views = _lifecycle_page(qapp, tmp_path, dw.LifecycleCli(missing=("archive", "reactivate")), probe=False)
    _show(page, views, "DJ-2026-101")
    buttons = _lifecycle_buttons(page)
    assert list(buttons) == ["归档…"] and not buttons["归档…"].isEnabled()
    assert "正在探测本机有没有这条命令……" in _texts_of(page)
    controller.probe_lifecycle()
    dw._wait(controller, qapp)  # 探测完页面自己重画
    buttons = _lifecycle_buttons(page)
    assert list(buttons) == ["归档…"] and not buttons["归档…"].isEnabled()
    assert any(t.startswith("本机发布版太旧：没有这条命令（等部署新版本后再看）") for t in _texts_of(page))
    page.start_dry_run("archive")  # 灰着的键就算被调到，命令那头也只会照实报没有这条命令；这里确认页面没有亮出确认键
    dw._wait(controller, qapp)
    assert "确认归档" not in _lifecycle_buttons(page)
    controller.runner = dw.LifecycleCli()
    controller.reset_lifecycle_probe()
    controller.probe_lifecycle()
    dw._wait(controller, qapp)
    page.void_dry_run()
    buttons = _lifecycle_buttons(page)
    assert list(buttons) == ["归档…"] and buttons["归档…"].isEnabled()
    for button in buttons.values():  # 按钮文字和提示里没有项目经理看板的禁用词
        from cockpit_board import policy

        assert not any(word in (button.text() + button.toolTip()).lower() for word in policy.PM_FORBIDDEN_WORDS)
        assert button.text() in policy.PM_BUTTONS


def test_archived_project_offers_reactivate_and_unregistered_offers_nothing(qapp: QApplication, tmp_path: Path) -> None:
    from tests.core import test_cockpit_decisions_widgets as dw

    fake = dw.LifecycleCli(dry_out="将要改的那一行：DJ-2026-101 状态 已归档 → 在研\n预演（没加 --confirm）：什么都没改。要真的改回在研，请用户本人加 --confirm 再运行。\n")
    page, controller, views = _lifecycle_page(qapp, tmp_path, fake, archived=True)
    _show(page, views, "DJ-2026-101")
    assert list(_lifecycle_buttons(page)) == ["重新激活…"] and "已归档" in _texts_of(page)
    _lifecycle_buttons(page)["重新激活…"].click()
    dw._wait(controller, qapp)
    assert fake.calls[-1] == ["project", "reactivate", "DJ-2026-101"]
    assert set(_lifecycle_buttons(page)) == {"确认重新激活", "重新检查"}
    _show(page, views, "DJ-2026-102")  # 只有文件夹、没登记的项目
    assert _lifecycle_buttons(page) == {} and any("还没登记" in t for t in _texts_of(page))


def test_a_blocked_dry_run_shows_the_output_verbatim_and_only_offers_a_recheck(qapp: QApplication, tmp_path: Path) -> None:
    """验收第 5 条：预演不过，页面上没有“确认归档”，只有“重新检查”；输出原样显示，一行不少。页面上没有任何输入框。"""
    from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit

    from tests.core import test_cockpit_decisions_widgets as dw

    fake = dw.LifecycleCli(dry_rc=1, dry_out=dw.DRY_BLOCKED)
    page, controller, views = _lifecycle_page(qapp, tmp_path, fake)
    _show(page, views, "DJ-2026-101")
    _lifecycle_buttons(page)["归档…"].click()
    assert page.dry_running == "DJ-2026-101" and not _lifecycle_buttons(page)["归档…"].isEnabled()  # 正在预演：不能连点
    dw._wait(controller, qapp)
    assert fake.calls[-1] == ["project", "archive", "DJ-2026-101"]
    assert list(_lifecycle_buttons(page)) == ["重新检查"]
    outputs = [label for label in page.findChildren(QLabel) if label.property("role") == "dry_run_output"]
    assert [str(label.text()) for label in outputs] == [dw.DRY_BLOCKED]
    assert any("退出码：rc 1" in t for t in _texts_of(page))
    for kind in (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox):
        assert page.findChildren(kind) == [], kind.__name__
    fake.dry_rc, fake.dry_out = 0, dw.DRY_PASS  # 处理完再点“重新检查”：这回通过，出现确认键
    _lifecycle_buttons(page)["重新检查"].click()
    dw._wait(controller, qapp)
    assert set(_lifecycle_buttons(page)) == {"确认归档", "重新检查"}
    silent = dw.LifecycleCli(dry_rc=0, dry_out="将要改的那一行：…\n")  # 退出码 0 但没有“预演”那一句：也没有确认键
    controller.runner = silent
    _lifecycle_buttons(page)["重新检查"].click()
    dw._wait(controller, qapp)
    assert list(_lifecycle_buttons(page)) == ["重新检查"]


def test_the_confirm_key_belongs_to_the_project_of_the_dry_run(qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """验收第 13 条：甲预演通过、出现“确认归档”后，换到乙的详情页，确认键没有了；回到甲点“重新读取”，确认键也没有了；
    不换页直接确认时，起的命令里的项目号等于预演的项目号。"""
    from cockpit_board.widgets.decisions import ConfirmDialog
    from PySide6.QtWidgets import QDialog

    from tests.core import test_cockpit_decisions_widgets as dw

    monkeypatch.setattr(ConfirmDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)
    fake = dw.LifecycleCli()
    fake.write_out = "项目已归档"
    page, controller, views = _lifecycle_page(qapp, tmp_path, fake)
    first, second = "DJ-2026-101", "SW-2026-008"

    def dry_run_first() -> None:
        _show(page, views, first)
        _lifecycle_buttons(page)["归档…"].click()
        dw._wait(controller, qapp)
        assert set(_lifecycle_buttons(page)) == {"确认归档", "重新检查"} and page.dry_run.project_id == first

    dry_run_first()
    _show(page, views, first)  # 同一个项目重画（比如网络探测回来）：预演还在
    assert "确认归档" in _lifecycle_buttons(page)
    _show(page, views, second)  # 换到乙：确认键没有了，乙要自己从“归档…”点起
    assert list(_lifecycle_buttons(page)) == ["归档…"] and page.dry_run is None
    assert not [label for label in page.findChildren(QLabel) if label.property("role") == "dry_run_output"]
    _show(page, views, first)  # 再回到甲：那份预演不会回来
    assert list(_lifecycle_buttons(page)) == ["归档…"]

    dry_run_first()
    page.void_dry_run()  # app.reload()（“重新读取”）调的就是它
    assert list(_lifecycle_buttons(page)) == ["归档…"] and page.dry_run is None

    dry_run_first()
    before = len(fake.calls)
    _lifecycle_buttons(page)["确认归档"].click()
    dw._wait(controller, qapp)
    assert len(fake.calls) == before + 1 and fake.calls[-1][:4] == ["project", "archive", first, "--confirm"]
    assert "确认归档" not in _lifecycle_buttons(page)  # 一次预演只确认一次
    receipts = [str(label.text()) for label in page.findChildren(QLabel) if label.property("role") == "lifecycle_receipt"]
    assert receipts == ["项目已归档"]  # 回执也显示在项目详情页
    assert controller.page.receipts[-1].output == "项目已归档"  # “决定”页的记录里也有

    # 项目号取预演记下的那个，不取页面当时显示的：就算页面上的项目被换掉（没经过 show_view），命令里仍是预演的项目
    dry_run_first()
    page.vm = views[second]
    page.confirm()
    dw._wait(controller, qapp)
    assert fake.calls[-1][:4] == ["project", "archive", first, "--confirm"]


def test_a_dry_run_that_finishes_after_the_page_moved_on_is_dropped(qapp: QApplication, tmp_path: Path) -> None:
    from tests.core import test_cockpit_decisions_widgets as dw

    page, controller, views = _lifecycle_page(qapp, tmp_path, dw.LifecycleCli())
    _show(page, views, "DJ-2026-101")
    page.start_dry_run("archive")
    _show(page, views, "SW-2026-008")  # 预演还在跑就换了项目
    dw._wait(controller, qapp)
    assert page.dry_run is None and list(_lifecycle_buttons(page)) == ["归档…"]
    _show(page, views, "DJ-2026-101")
    page.start_dry_run("archive")
    page.void_dry_run()  # 预演还在跑就点了“重新读取”
    dw._wait(controller, qapp)
    assert page.dry_run is None and list(_lifecycle_buttons(page)) == ["归档…"]


def test_projects_page_has_one_jump_button_that_only_calls_back(qapp: QApplication, tmp_path: Path) -> None:
    from cockpit_board import policy
    from cockpit_board.widgets.projects import ProjectsPage

    jumped: list[int] = []
    page = ProjectsPage(lambda _pid: None, lambda: jumped.append(1))
    buttons = [b for b in page.findChildren(QPushButton) if b.text()]
    assert [str(b.text()) for b in buttons] == ["新建项目…"] and buttons[0].isEnabled()
    assert not any(word in (buttons[0].text() + buttons[0].toolTip()).lower() for word in policy.PM_FORBIDDEN_WORDS)
    buttons[0].click()
    assert jumped == [1]
    alone = ProjectsPage(lambda _pid: None)  # 没接跳页（旧的用法）：键在，但灰着
    assert [b.isEnabled() for b in alone.findChildren(QPushButton) if b.text()] == [False]


def test_a_dry_run_of_another_project_never_lights_this_projects_confirm_key(qapp: QApplication, tmp_path: Path) -> None:
    """第二道闸：就算页面手里留着别的项目的预演（换项目时本该清掉），这个项目的“项目状态”一块也不认它。"""
    from tests.core import test_cockpit_decisions_widgets as dw

    page, controller, views = _lifecycle_page(qapp, tmp_path, dw.LifecycleCli())
    _show(page, views, "DJ-2026-101")
    _lifecycle_buttons(page)["归档…"].click()
    dw._wait(controller, qapp)
    kept = page.dry_run
    assert kept.passed and "确认归档" in _lifecycle_buttons(page)
    _show(page, views, "SW-2026-008")
    page.dry_run = kept  # 硬塞回去
    page._redraw()
    assert list(_lifecycle_buttons(page)) == ["归档…"]
    assert not [label for label in page.findChildren(QLabel) if label.property("role") == "dry_run_output"]


def test_confirm_does_nothing_when_the_dry_run_did_not_pass(qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """第二道闸：预演不过时页面上本来就没有确认键；就算 confirm() 被调到，也不弹确认框、不起命令。"""
    from cockpit_board.widgets.decisions import ConfirmDialog
    from PySide6.QtWidgets import QDialog

    from tests.core import test_cockpit_decisions_widgets as dw

    opened: list[int] = []

    def accept(_self: Any) -> Any:
        opened.append(1)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ConfirmDialog, "exec", accept)
    fake = dw.LifecycleCli(dry_rc=1, dry_out=dw.DRY_BLOCKED)
    page, controller, views = _lifecycle_page(qapp, tmp_path, fake)
    _show(page, views, "DJ-2026-101")
    _lifecycle_buttons(page)["归档…"].click()
    dw._wait(controller, qapp)
    assert page.dry_run is not None and not page.dry_run.passed
    before = len(fake.calls)
    page.confirm()
    dw._wait(controller, qapp)
    assert opened == [] and len(fake.calls) == before and controller.last_dialog is None


# ---------------------------------------------------------------- 首页小部件和问题页筛选（CHG-SCPT-2026-655）


def test_655_click_box_fires_on_left_click_enter_and_space_only(qapp: QApplication) -> None:
    box = c.click_row("cardrow", "第 1 张卡", "到流程图页看这张卡走到哪一步", c.quiet("写通讯层"), 1)
    fired: list[int] = []
    box.activated.connect(lambda: fired.append(1))
    box.resize(300, 30)
    box.show()
    qapp.processEvents()
    assert box.focusPolicy() == Qt.FocusPolicy.StrongFocus and box.accessibleName() == "第 1 张卡"
    QTest.mouseClick(box, Qt.MouseButton.LeftButton)
    assert len(fired) == 1
    QTest.mouseClick(box, Qt.MouseButton.RightButton)
    assert len(fired) == 1
    for key, total in ((Qt.Key.Key_Return, 2), (Qt.Key.Key_Enter, 3), (Qt.Key.Key_Space, 4), (Qt.Key.Key_A, 4), (Qt.Key.Key_Escape, 4)):
        QTest.keyClick(box, key)
        assert len(fired) == total, key
    # 框里的字不拦鼠标：点在字上也算点框
    label = box.findChildren(QLabel)[0]
    assert label.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    QTest.mouseClick(box, Qt.MouseButton.LeftButton, pos=label.geometry().center())
    assert len(fired) == 5
    assert box.findChildren(QPushButton) == []  # 框不是按钮，里面也没有按钮


def test_655_fold_opens_and_closes_and_reports_it(qapp: QApplication) -> None:
    fold = c.Fold("依据和编号", key="focus")
    fold.box.addWidget(c.label("卡号"))
    seen: list[bool] = []
    fold.toggled.connect(seen.append)
    fold.show()
    qapp.processEvents()
    assert not fold.opened and not fold.body.isVisible() and fold.arrow.text() == "▸"
    QTest.mouseClick(fold.head, Qt.MouseButton.LeftButton)
    assert fold.opened and fold.body.isVisible() and fold.arrow.text() == "▾"
    QTest.keyClick(fold.head, Qt.Key.Key_Space)
    assert not fold.opened and not fold.body.isVisible() and seen == [True, False]
    opened = c.Fold("最近 7 天发生了什么", opened=True)
    assert opened.opened and opened.arrow.text() == "▾"


def test_655_strip_draws_ticks_before_and_shape_on_the_current_cell(qapp: QApplication) -> None:
    cells = ("草稿", "等批准", "进行中", "等验收", "已验收", "已关闭")

    def drawn(holder: QWidget) -> list[tuple[str, str, str]]:
        return [(label.text(), label.property("at"), label.property("sev") or "") for label in holder.findChildren(QLabel)]

    assert drawn(c.strip(cells, 3, "受阻", "block", "■")) == [
        ("✓ 草稿", "done", ""), ("✓ 等批准", "done", ""), ("■ 受阻", "current", "block"),
        ("等验收", "todo", ""), ("已验收", "todo", ""), ("已关闭", "todo", "")]
    assert drawn(c.strip(cells, 1, "草稿"))[:2] == [("草稿", "current", ""), ("等批准", "todo", "")]  # 草稿不给第 2 格画“✓”
    assert drawn(c.strip(cells, 6, "收口没走完", "risk", "●"))[-1] == ("● 收口没走完", "current", "risk")
    assert [text for text, at, _sev in drawn(c.strip(cells, 6, "收口没走完", "risk", "●")) if at == "done"] == [
        "✓ 草稿", "✓ 等批准", "✓ 进行中", "✓ 等验收", "✓ 已验收"]


def test_655_lamp_is_hollow_and_grey_when_not_checked(qapp: QApplication) -> None:
    def dot(box: QWidget) -> tuple[str, str]:
        label = next(item for item in box.findChildren(QLabel) if item.objectName() == "dot")
        return label.text(), label.property("sev")

    ok = c.lamp("lost", "名字", "0 个", "ok", "number", "第 1 盏检查灯", "点开看这项检查的说明")
    bad = c.lamp("lost", "名字", "1 个", "block", "number", "第 1 盏检查灯", "点开看这项检查的说明")
    unchecked = c.lamp("scope", "名字", "没检查", "na", "unchecked", "第 2 盏检查灯", "点开看这项检查的说明")
    offline = c.lamp("gate_red", "名字", "断网未知", "na", "offline", "第 3 盏检查灯", "点开看这项检查的说明")
    assert (dot(ok), dot(bad), dot(unchecked), dot(offline)) == (("●", "ok"), ("●", "block"), ("○", "na"), ("○", "na"))
    assert (bad.property("sev"), unchecked.property("state")) == ("block", "unchecked")
    from cockpit_board import theme

    qss = theme.build_qss(theme.LIGHT)
    assert f'QFrame#lamp[sev="block"] {{ background: {theme.LIGHT.block_soft}; border: 1px solid {theme.LIGHT.block}; }}' in qss
    assert f'QLabel#cell[at="current"][sev="risk"] {{ background: {theme.LIGHT.risk_soft}; border: 1px solid {theme.LIGHT.risk}; }}' in qss
    # 风险色只当底色和图形，不当正文字色：格子里的字、数的字都用正文色
    assert f'QLabel#cell[at="current"] {{ color: {theme.LIGHT.fg};' in qss
    assert 'QLabel#num[' not in qss and 'QLabel#lampvalue[sev' not in qss


def _filter_issues() -> list[Any]:
    from datetime import datetime

    when = datetime(2026, 11, 1, 12, 0)

    def issue(sev: str, title: str, owner: str, basis: str = "依据") -> Any:
        return vm.Issue(sev, "DJ-2026-101", title, "说明", "谁", basis, when, owner=owner)

    return [issue("block", "受阻，要拿主意", vm.OWNER_USER), issue("hint", "批准范围", vm.OWNER_USER),
            issue("block", "执行者失联", vm.OWNER_LEAD), issue("hint", "草稿，没有工作项，也没有批准记录", vm.OWNER_LEAD),
            issue("risk", "PR #470 门禁红", ""),
            issue("hint", "账本遗留", vm.OWNER_LEAD, vm.OLD_BASIS), issue("hint", "工作项受阻", vm.OWNER_LEAD, vm.OLD_BASIS)]


def _issue_titles(page: IssuesPage) -> list[str]:
    return [issue.title for issue in page.shown]


def _tab(page: IssuesPage, prop: str, key: str) -> QPushButton:
    found: QPushButton = next(b for b in page.findChildren(QPushButton) if b.property(prop) == key)
    return found


def test_655_issues_page_hides_old_records_until_the_box_is_ticked(qapp: QApplication) -> None:
    """问题页默认只藏旧账，“提醒”档不藏；勾“显示旧账（N 条）”才列。"""
    from datetime import datetime

    from cockpit_board import policy

    page = IssuesPage(lambda _pid: None)
    page.show_view(_filter_issues(), datetime(2026, 11, 1, 12, 0))
    box = page.findChild(QCheckBox, "show_old")
    assert box is not None and box.text() == "显示旧账（2 条）" and not box.isChecked()
    assert len(page.shown) == 5 and "账本遗留" not in _issue_titles(page) and "批准范围" in _issue_titles(page)
    counts = {b.property("filter"): b.toolTip() for b in page.findChildren(QPushButton) if b.property("filter")}
    assert counts == {"all": "只看全部（5 条）", "block": "只看阻塞（2 条）", "risk": "只看风险（1 条）", "hint": "只看提醒（2 条）"}
    box.click()
    box = page.findChild(QCheckBox, "show_old")
    assert box is not None and box.isChecked() and len(page.shown) == 7 and page.old == "show"
    box.click()
    assert page.old == "hide" and len(page.shown) == 5
    # “谁来办”那一排是三个固定文字的键，都在白名单里，没有禁用词
    who = [b for b in page.findChildren(QPushButton) if b.property("who")]
    assert [b.text() for b in who] == ["全部", "要你办", "AI 那边要收拾"]
    for button in who:
        assert button.text() in policy.PM_BUTTONS
        assert not any(word in (button.text() + button.toolTip()).lower() for word in policy.PM_FORBIDDEN_WORDS)


def test_655_issues_page_who_filter_and_the_outside_entry(qapp: QApplication) -> None:
    from datetime import datetime

    page = IssuesPage(lambda _pid: None)
    page.set_view("lead")  # 还没画过：只记下，不炸
    assert (page.who, page.old) == ("lead", "hide") and page.layout_.count() == 0
    page.show_view(_filter_issues(), datetime(2026, 11, 1, 12, 0), (), 5, 3)
    assert _issue_titles(page) == ["执行者失联", "草稿，没有工作项，也没有批准记录"]
    assert _tab(page, "who", "lead").isChecked() and not any(label.property("user_line") for label in page.findChildren(QLabel))
    _tab(page, "who", "user").click()
    assert _issue_titles(page) == ["受阻，要拿主意", "批准范围"]
    line = next(label.text() for label in page.findChildren(QLabel) if label.property("user_line"))
    assert line == "要你办共 5 件：这页列 2 条；另有 3 件是 PR 上等你签的、老后台补的，在「要你出手」页和「PR 与审计」页"
    _tab(page, "filter", "block").click()  # 两排筛选一起生效
    assert _issue_titles(page) == ["受阻，要拿主意"]
    page.set_view("old")  # 首页“旧账”那个数点过来：只列旧账，严重度回到全部
    assert (page.filter, page.who, page.old) == ("all", "all", "only")
    assert _issue_titles(page) == ["账本遗留", "工作项受阻"]
    box = page.findChild(QCheckBox, "show_old")
    assert box is not None and box.isChecked()
    box.click()  # 去掉勾回到平常的样子
    assert page.old == "hide" and len(page.shown) == 5
    page.set_view("user")
    page.show_view(_filter_issues(), datetime(2026, 11, 1, 12, 0), (), 2, 0)
    line = next(label.text() for label in page.findChildren(QLabel) if label.property("user_line"))
    assert line == "要你办共 2 件：这页列 2 条"  # K 为 0 时不写后半句
    _tab(page, "who", "all").click()
    assert len(page.shown) == 5 and not any(label.property("user_line") for label in page.findChildren(QLabel))
    for bad in ("", "all", "block", "running"):
        with pytest.raises(ValueError, match="不认识的筛选"):
            page.set_view(bad)
    with pytest.raises(ValueError, match="旧账"):
        page.set_old("sometimes")
