"""状态图的数据层（不依赖 Qt）：读 flow/graphs.json，校验，回答“现在在哪、下一步能去哪”。

画图的代码（widgets/flow.py）只读这里给出的 Graph，不在代码里写死任何节点或连线。
以后要“编排”，第一步是改 graphs.json（仍走 PR 和独立审计），第二步才是界面上拖出这个文件。

JSON 里的节点和连线必须和 source 字段指的真实状态表一致，tests/core/test_cockpit_board_flow.py 逐条对账：
状态表变了、图没跟着改，测试就红。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GRAPHS_PATH = Path(__file__).resolve().parent / "flow" / "graphs.json"
FORMAT = "cockpit-flow-graphs.v1"
ACTORS = ("", "user")  # 空＝系统或 agent 都可；user＝只听用户本人


class GraphError(ValueError):
    """graphs.json 不合规；文字直接给人看，不猜。"""


@dataclass(frozen=True)
class Node:
    id: str
    label: str  # 中文名
    x: int
    y: int


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    label: str = ""  # 对应的命令（可空）
    actor: str = ""
    minor: bool = False  # 取消/废弃这类“随时可退出”的线，画得浅一些，不抢主线


@dataclass(frozen=True)
class Graph:
    id: str
    title: str
    english: str
    intro: str
    source: str
    hint: str
    width: int
    height: int
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    node_width: int
    node_height: int

    def node(self, node_id: str) -> Node | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def label_of(self, node_id: str) -> str:
        found = self.node(node_id)
        return found.label if found else node_id

    def next_states(self, node_id: str) -> tuple[str, ...]:
        """从这个状态一步能到的状态（按 JSON 里连线的顺序）。"""
        return tuple(e.target for e in self.edges if e.source == node_id)

    def edges_from(self, node_id: str) -> tuple[Edge, ...]:
        return tuple(e for e in self.edges if e.source == node_id)

    def is_terminal(self, node_id: str) -> bool:
        return not self.next_states(node_id)

    def transitions(self) -> dict[str, set[str]]:
        """{状态: {下一状态}}，用来和代码里的状态表对账。"""
        table: dict[str, set[str]] = {n.id: set() for n in self.nodes}
        for edge in self.edges:
            table[edge.source].add(edge.target)
        return table


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GraphError(message)


def _parse_graph(raw: dict[str, Any], node_width: int, node_height: int) -> Graph:
    gid = str(raw.get("id", ""))
    _require(bool(gid), "有一张图没有 id")
    nodes = tuple(Node(str(n["id"]), str(n["label"]), int(n["x"]), int(n["y"])) for n in raw.get("nodes", []))
    ids = [n.id for n in nodes]
    _require(bool(nodes), f"图 {gid} 没有节点")
    _require(len(set(ids)) == len(ids), f"图 {gid} 有重复的节点 id")
    edges = []
    for e in raw.get("edges", []):
        edge = Edge(str(e["from"]), str(e["to"]), str(e.get("label", "")), str(e.get("actor", "")), bool(e.get("minor", False)))
        _require(edge.source in ids and edge.target in ids, f"图 {gid} 的连线 {edge.source}→{edge.target} 指向不存在的节点")
        _require(edge.source != edge.target, f"图 {gid} 的连线 {edge.source} 指向自己")
        _require(edge.actor in ACTORS, f"图 {gid} 的连线 {edge.source}→{edge.target} 的 actor 只能是 {ACTORS}")
        edges.append(edge)
    pairs = [(e.source, e.target) for e in edges]
    _require(len(set(pairs)) == len(pairs), f"图 {gid} 有重复的连线")
    width, height = int(raw["width"]), int(raw["height"])
    for node in nodes:
        _require(0 <= node.x and node.x + node_width <= width and 0 <= node.y and node.y + node_height <= height,
                 f"图 {gid} 的节点 {node.id} 画到了画布外面")
    boxes = [(n.x, n.y, n.x + node_width, n.y + node_height) for n in nodes]
    for i, a in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            _require(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], f"图 {gid} 的节点 {nodes[i].id} 和 {nodes[j].id} 叠在一起")
    return Graph(
        gid, str(raw["title"]), str(raw.get("english", "")), str(raw.get("intro", "")), str(raw.get("source", "")),
        str(raw.get("hint", "")), width, height, nodes, tuple(edges), node_width, node_height,
    )


def load_graphs(path: Path = GRAPHS_PATH) -> tuple[Graph, ...]:
    """读并校验。文件缺、JSON 坏、字段缺都抛 GraphError，不返回半张图。"""
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError) as error:
        raise GraphError(f"读不了状态图数据 {path.name}：{error}") from error
    _require(isinstance(raw, dict) and raw.get("format") == FORMAT, f"{path.name} 的 format 不是 {FORMAT}")
    size = raw.get("node") or {}
    try:
        node_width, node_height = int(size["width"]), int(size["height"])
        graphs = tuple(_parse_graph(g, node_width, node_height) for g in raw["graphs"])
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, GraphError):
            raise
        raise GraphError(f"{path.name} 缺字段或类型不对：{type(error).__name__} {error}") from error
    _require(bool(graphs), f"{path.name} 里没有图")
    _require(len({g.id for g in graphs}) == len(graphs), f"{path.name} 里有重复的图 id")
    return graphs


# ---------------------------------------------------------------- 板上的卡 → 图上亮哪个点


@dataclass(frozen=True)
class CardPosition:
    """一张卡现在在哪：任务状态 + 它最近一次执行的状态（没有就空）。"""

    project_id: str
    mission_id: str
    title: str
    mission_state: str
    run_state: str

    def current(self, graph_id: str) -> str | None:
        """这张卡在某张图上亮哪个节点；账本里没带这项状态就返回 None（图只显示流程，不乱亮）。"""
        if graph_id == "mission":
            return self.mission_state or None
        if graph_id == "run":
            return self.run_state or None
        return None  # 工作项、变更单：本版账本读取还没带上，不猜


def card_positions(projects: list[Any]) -> list[CardPosition]:
    """从 pm_dashboard.Board.projects 取每个项目的任务；只读它们已有的字段，按“没关的在前”排。"""
    cards: list[CardPosition] = []
    for project in projects:
        for mission in getattr(project, "missions", []):
            run = getattr(mission, "run", None)
            cards.append(CardPosition(
                project.project_id, mission.mission_id, mission.title, mission.state,
                getattr(run, "state", "") if run is not None else "",
            ))
    done = {"CLOSED", "CANCELLED", "ACCEPTED"}
    cards.sort(key=lambda c: (c.mission_state in done, c.project_id, c.mission_id))
    return cards
