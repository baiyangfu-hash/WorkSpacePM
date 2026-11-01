"""总控屏“流程图”页：状态图的数据必须和真实状态机一致（TD：为以后编排留口子，先保证“看”）。

- flow/graphs.json 的节点、连线逐条对账代码里的状态表：状态表变了、图没跟着改，这里就红；
- 对账函数自己也有变异测试，防止“比较永远通过”；
- 画图控件只读数据，亮的点来自账本里的状态，读不到就不亮、不猜。
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import flowgraph, theme, tool_policy  # noqa: E402
from cockpit_board.flowgraph import CardPosition, Graph, GraphError  # noqa: E402
from cockpit_board.widgets.flow import FlowGraphWidget, FlowPage  # noqa: E402

from auto_pm.application.core.continuity_execution_service import _RUN_TRANSITIONS  # noqa: E402
from auto_pm.application.core.mission_service import _TRANSITIONS as MISSION_TRANSITIONS  # noqa: E402
from auto_pm.application.core.work_registry_service import _TRANSITIONS as WORK_TRANSITIONS  # noqa: E402
from auto_pm.contracts.continuity import RunState, WorkState  # noqa: E402
from auto_pm.contracts.mission import MissionState  # noqa: E402
from auto_pm.domain.change.constants import STATUS_FLOW  # noqa: E402
from auto_pm.infrastructure.continuity_store import _STORE_RUN_TRANSITIONS  # noqa: E402


def _as_names(table: dict[Any, Any]) -> dict[str, set[str]]:
    return {getattr(key, "value", key): {getattr(v, "value", v) for v in values} for key, values in table.items()}


def diff_tables(graph: Graph, table: dict[Any, Any]) -> list[str]:
    """图和代码状态表的差别，空表示一致。"""
    expected, drawn = _as_names(table), graph.transitions()
    problems = [f"代码里有、图里没有的状态：{sorted(set(expected) - set(drawn))}"] if set(expected) - set(drawn) else []
    problems += [f"图里有、代码里没有的状态：{sorted(set(drawn) - set(expected))}"] if set(drawn) - set(expected) else []
    for state in sorted(set(expected) & set(drawn)):
        if expected[state] != drawn[state]:
            problems.append(f"{state}：代码 {sorted(expected[state])}，图 {sorted(drawn[state])}")
    return problems


@pytest.fixture(scope="module")
def graphs() -> dict[str, Graph]:
    return {g.id: g for g in flowgraph.load_graphs()}


# ---------------------------------------------------------------- 数据和代码对账


def test_there_are_four_graphs(graphs: dict[str, Graph]) -> None:
    assert list(graphs) == ["mission", "work", "run", "change"]


@pytest.mark.parametrize(("graph_id", "table"), [
    ("mission", MISSION_TRANSITIONS), ("work", WORK_TRANSITIONS), ("run", _RUN_TRANSITIONS), ("change", STATUS_FLOW),
])
def test_graph_matches_the_real_state_machine(graphs: dict[str, Graph], graph_id: str, table: dict[Any, Any]) -> None:
    assert diff_tables(graphs[graph_id], table) == []


def test_run_tables_in_service_and_store_are_the_same_so_one_graph_is_enough() -> None:
    assert _as_names(_RUN_TRANSITIONS) == _as_names(_STORE_RUN_TRANSITIONS)


def test_nodes_are_exactly_the_enum_members(graphs: dict[str, Graph]) -> None:
    for graph_id, enum in (("mission", MissionState), ("work", WorkState), ("run", RunState)):
        assert {n.id for n in graphs[graph_id].nodes} == {m.value for m in enum}


def test_diff_tables_catches_a_missing_extra_or_changed_edge(graphs: dict[str, Graph]) -> None:
    mission = graphs["mission"]
    dropped = dict(MISSION_TRANSITIONS)
    dropped[MissionState.ACTIVE] = frozenset(MISSION_TRANSITIONS[MissionState.ACTIVE] - {MissionState.PARKED})
    assert any("ACTIVE" in p for p in diff_tables(mission, dropped))
    extra = dict(MISSION_TRANSITIONS)
    extra[MissionState.CLOSED] = frozenset({MissionState.ACTIVE})
    assert any("CLOSED" in p for p in diff_tables(mission, extra))
    removed = {k: v for k, v in MISSION_TRANSITIONS.items() if k is not MissionState.PARKED}
    assert any("图里有" in p for p in diff_tables(mission, removed))
    assert diff_tables(mission, MISSION_TRANSITIONS) == []


def test_edge_commands_name_real_cli_commands(graphs: dict[str, Graph]) -> None:
    """线上标的 pm 命令必须是真有的子命令（防标错、防命令改名后图还留着旧名）。"""
    from auto_pm.cli.__main__ import cli

    pm = cli.commands["pm"].commands
    for graph in graphs.values():
        for edge in graph.edges:
            match = re.match(r"^pm (\S+)$", edge.label)
            if match:
                assert match.group(1) in pm, (graph.id, edge)


def test_user_only_edges_are_the_ones_that_need_the_users_own_word(graphs: dict[str, Graph]) -> None:
    user_edges = {(g.id, e.source, e.target) for g in graphs.values() for e in g.edges if e.actor == "user"}
    assert user_edges == {
        ("mission", "ACTIVE", "PARKED"), ("mission", "PARKED", "ACTIVE"), ("mission", "ACCEPTANCE_PENDING", "ACCEPTED"),
        ("work", "VERIFYING", "ACCEPTED"),
        ("change", "under_review", "approved"), ("change", "under_review", "conditionally_approved"),
    }


# ---------------------------------------------------------------- 数据文件校验


def _write(tmp_path: Path, mutate: Callable[[dict[str, Any]], object]) -> Path:
    raw = json.loads(flowgraph.GRAPHS_PATH.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "g.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def test_the_shipped_file_loads_and_every_node_fits_the_canvas(graphs: dict[str, Graph]) -> None:
    for graph in graphs.values():
        for node in graph.nodes:
            assert node.x + graph.node_width <= graph.width and node.y + graph.node_height <= graph.height


@pytest.mark.parametrize(("name", "mutate", "needle"), [
    ("edge-to-nowhere", lambda r: r["graphs"][0]["edges"].append({"from": "DRAFT", "to": "NOPE"}), "不存在的节点"),
    ("self-loop", lambda r: r["graphs"][0]["edges"].append({"from": "DRAFT", "to": "DRAFT"}), "指向自己"),
    ("dup-edge", lambda r: r["graphs"][0]["edges"].append(dict(r["graphs"][0]["edges"][0])), "重复的连线"),
    ("dup-node", lambda r: r["graphs"][0]["nodes"].append(dict(r["graphs"][0]["nodes"][0])), "重复的节点"),
    ("off-canvas", lambda r: r["graphs"][0]["nodes"][0].update(x=99999), "画布外"),
    ("overlap", lambda r: r["graphs"][0]["nodes"][1].update(x=r["graphs"][0]["nodes"][0]["x"], y=r["graphs"][0]["nodes"][0]["y"]), "叠在一起"),
    ("bad-actor", lambda r: r["graphs"][0]["edges"][0].update(actor="root"), "actor"),
    ("bad-format", lambda r: r.update(format="v0"), "format"),
    ("no-graphs", lambda r: r.update(graphs=[]), "没有图"),
    ("missing-field", lambda r: r["graphs"][0].pop("width"), "缺字段"),
])
def test_bad_data_is_refused_with_a_readable_reason(tmp_path: Path, name: str, mutate: Callable[[dict[str, Any]], object], needle: str) -> None:
    with pytest.raises(GraphError, match=needle):
        flowgraph.load_graphs(_write(tmp_path, mutate))


def test_missing_or_broken_file_is_a_graph_error_not_a_crash(tmp_path: Path) -> None:
    with pytest.raises(GraphError):
        flowgraph.load_graphs(tmp_path / "none.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(GraphError):
        flowgraph.load_graphs(broken)


def test_next_states_and_terminals(graphs: dict[str, Graph]) -> None:
    mission = graphs["mission"]
    assert set(mission.next_states("ACTIVE")) == {"BLOCKED", "PARKED", "ACCEPTANCE_PENDING", "CANCELLED"}
    assert mission.is_terminal("CLOSED") and mission.is_terminal("CANCELLED") and not mission.is_terminal("ACTIVE")
    assert graphs["change"].is_terminal("abandoned") and graphs["change"].is_terminal("archived")


# ---------------------------------------------------------------- 板上的卡


def _project(project_id: str, *missions: tuple[str, str, str, str | None]) -> SimpleNamespace:
    return SimpleNamespace(project_id=project_id, missions=[
        SimpleNamespace(mission_id=m, title=t, state=s, run=SimpleNamespace(state=r) if r else None) for m, t, s, r in missions])


def test_card_positions_put_unfinished_cards_first_and_carry_run_state() -> None:
    projects = [_project("B-1", ("M3", "done", "CLOSED", None)), _project("A-1", ("M2", "going", "ACTIVE", "RUNNING"), ("M1", "wait", "PARKED", None))]
    cards = flowgraph.card_positions(projects)
    assert [c.mission_id for c in cards] == ["M1", "M2", "M3"]
    assert cards[1].current("mission") == "ACTIVE" and cards[1].current("run") == "RUNNING"
    assert cards[0].current("run") is None  # 没有 Run 就不亮
    assert cards[1].current("work") is None and cards[1].current("change") is None  # 账本没带的状态不猜


# ---------------------------------------------------------------- 画图


def test_widget_paints_and_the_current_node_changes_the_picture(qapp: QApplication, graphs: dict[str, Graph]) -> None:
    widget = FlowGraphWidget(graphs["mission"])
    widget.resize(1300, 400)
    plain = widget.grab().toImage()
    assert not plain.isNull() and plain.width() == 1300
    widget.set_current("ACTIVE")
    lit = widget.grab().toImage()
    assert lit != plain  # 亮了一个节点
    widget.set_current("NOT_A_STATE")
    assert widget.current is None  # 不认识的状态不亮
    assert widget.grab().toImage() == plain


def test_clicking_a_node_focuses_it_and_other_clicks_do_nothing(qapp: QApplication, graphs: dict[str, Graph]) -> None:
    widget = FlowGraphWidget(graphs["mission"])
    widget.resize(1300, 400)
    clicked: list[str] = []
    widget.node_clicked.connect(clicked.append)
    rect = widget.node_rect("PARKED")
    assert rect is not None and widget.node_at(rect.center()) == "PARKED"
    assert widget.node_at(QPointF(2, 2)) is None
    widget.set_focus("PARKED")
    assert widget.focus == "PARKED"
    widget.set_graph(graphs["work"])
    assert widget.focus is None and widget.current is None  # 换图清掉


def test_widget_without_a_graph_does_not_paint_or_divide_by_zero(qapp: QApplication) -> None:
    widget = FlowGraphWidget()
    widget.resize(300, 100)
    assert widget.heightForWidth(300) == 0 and not widget.grab().isNull()


def test_painting_code_has_no_colors_of_its_own() -> None:
    source = (SCRIPTS / "cockpit_board" / "widgets" / "flow.py").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{6}\b", source) and "QColor(" in source
    used = set(re.findall(r"QColor\(tokens\.(\w+)\)", source))
    assert used and used <= set(theme.token_names())  # 每个颜色都取自主题令牌


# ---------------------------------------------------------------- 页面


def test_page_buttons_are_the_graph_titles_and_nothing_forbidden(qapp: QApplication, graphs: dict[str, Graph]) -> None:
    page = FlowPage()
    texts = {b.text() for b in page.findChildren(QPushButton)}
    assert texts == {g.title for g in graphs.values()}
    for text in texts:
        assert not any(word in text for word in tool_policy.TOOL_FORBIDDEN_WORDS), text


def _lit(page: FlowPage) -> str | None:
    """图上现在亮的节点（经函数取一次，免得类型检查把属性当成“断言过就不会变”）。"""
    current: str | None = page.widget.current
    return current


def test_page_lights_the_selected_card_and_lists_next_steps(qapp: QApplication) -> None:
    page = FlowPage()
    page.show_cards(flowgraph.card_positions([_project("DJ-1", ("M1", "写通讯层", "ACTIVE", "RUNNING"))]))
    assert _lit(page) is None  # 默认“不指定”，不替用户选
    page.card_box.setCurrentIndex(1)
    assert _lit(page) == "ACTIVE"
    page.select_graph("run")
    assert _lit(page) == "RUNNING"
    page.select_graph("work")
    assert _lit(page) is None  # 工作项账本没带：不亮
    page.select_graph("mission")
    page.widget.set_focus("ACCEPTANCE_PENDING")
    page._render_panel()
    shown = " ".join(label.text() for label in page.panel_holder.findChildren(QLabel))
    assert "pm accept" in shown and "只听用户本人" in shown


def test_page_keeps_the_chosen_card_across_a_refresh(qapp: QApplication) -> None:
    page = FlowPage()
    cards = flowgraph.card_positions([_project("DJ-1", ("M1", "a", "ACTIVE", None), ("M2", "b", "PARKED", None))])
    page.show_cards(cards)
    page.card_box.setCurrentIndex(2)
    selected = page.selected_card()
    page.show_cards(cards)
    assert page.selected_card() == selected


def test_page_with_bad_data_says_so_and_does_not_crash(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> tuple[Graph, ...]:
        raise GraphError("读不了状态图数据 x.json")

    monkeypatch.setattr("cockpit_board.widgets.flow.load_graphs", boom)
    page = FlowPage()
    shown = " ".join(label.text() for label in page.findChildren(QLabel))
    assert page.error and "读不了状态图数据" in shown  # 页面上写明原因，而不是空白
    page.show_cards([CardPosition("P", "M", "t", "ACTIVE", "")])  # 不炸
    page.select_graph("mission")
    assert page.error and not page.picker_buttons
