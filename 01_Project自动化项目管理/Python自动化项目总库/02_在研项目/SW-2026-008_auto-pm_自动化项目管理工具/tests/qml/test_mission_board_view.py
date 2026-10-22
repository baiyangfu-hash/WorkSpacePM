"""TD-071 card 4: the four-column board in the cockpit is read-only, names no internal id and flags a stale parked card."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PySide6.QtQml import QQmlEngine
from PySide6.QtQuick import QQuickItem

from tests.qml.test_boss_cockpit_view import _QML, _items_named, _load, _QtMessages, _texts

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


def _card(mission_id: str, title: str, label: str, note: str = "", stale: bool = False) -> dict[str, object]:
    return {"mission_id": mission_id, "title": title, "state_label": label, "note": note, "stale": stale}


def _board(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "pm-cockpit-mission-board.v1",
        "project_id": "DJ-2026-009",
        "project_name": "3Sun 打胶线",
        "open_count": 3,
        "open_limit": 8,
        "active": [_card("MISSION-B", "客户急改 IO 表", "系统执行")],
        "waiting": [_card("MISSION-C", "报警汇总", "等待开工确认")],
        "parked": [_card("MISSION-A", "OB1 接线", "搁着（断点已记）", "为什么放下：客户急改 IO 表；断点：OB1 改完，差测试", stale=True)],
        "closed": [],
        "closed_hidden": 0,
    }
    payload.update(changes)
    return payload


def _component(engine: QQmlEngine, qapp: QApplication, board: dict[str, object]) -> QQuickItem:
    item = cast(QQuickItem, _load(engine, _QML / "components" / "MissionBoard.qml"))
    item.setProperty("board", board)
    qapp.processEvents()
    return item


def test_the_board_shows_four_columns_with_counts_and_no_internal_id(qapp: QApplication, qml_engine: QQmlEngine) -> None:
    with _QtMessages() as warnings:
        item = _component(qml_engine, qapp, _board())
    texts = " ".join(_texts(item))

    for expected in ("3Sun 打胶线 · 开着 3 / 8 张", "在干（1）", "等你（1）", "搁着（1）", "已关（0）", "客户急改 IO 表", "OB1 改完，差测试"):
        assert expected in texts
    assert "MISSION-" not in texts
    assert [message for message in warnings if "qml" in message.lower()] == []


def test_a_stale_parked_card_is_drawn_apart_and_there_is_no_button(qapp: QApplication, qml_engine: QQmlEngine) -> None:
    item = _component(qml_engine, qapp, _board())
    assert len(_items_named(item, "boardCardStale")) == 1 and len(_items_named(item, "boardCard")) == 2
    assert not any(child.metaObject().className().startswith("Button") for child in _all(item))


def test_the_limit_line_shows_only_at_the_limit(qapp: QApplication, qml_engine: QQmlEngine) -> None:
    below = _component(qml_engine, qapp, _board())
    at = _component(qml_engine, qapp, _board(open_count=8))
    assert _items_named(below, "boardOverLimit")[0].isVisible() is False
    assert _items_named(at, "boardOverLimit")[0].isVisible() is True


def test_the_cockpit_view_renders_one_board_per_project(qapp: QApplication, qml_engine: QQmlEngine) -> None:
    view = cast(QQuickItem, _load(qml_engine, _QML / "views" / "BossCockpitView.qml"))
    view.setProperty("boards", [_board(), _board(project_id="DJ-2026-005", project_name="老线改造", open_count=0, active=[], waiting=[], parked=[])])
    qapp.processEvents()
    titles = [title.property("text") for title in _items_named(view, "boardTitle")]
    assert titles == ["3Sun 打胶线 · 开着 3 / 8 张", "老线改造 · 开着 0 / 8 张"]


def _all(item: QQuickItem) -> list[QQuickItem]:
    found: list[QQuickItem] = []
    for child in item.childItems():
        found.append(child)
        found.extend(_all(child))
    return found
