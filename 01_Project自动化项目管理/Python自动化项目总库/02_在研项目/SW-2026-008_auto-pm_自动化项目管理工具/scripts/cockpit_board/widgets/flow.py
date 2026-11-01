"""流程图页（L1 固定状态图）：把任务、工作项、执行、变更单的状态流转画出来，当前在哪一步就亮哪一步。

只读：这里没有任何会改状态的按钮。节点、连线、位置全部来自 flowgraph.load_graphs()（flow/graphs.json），
本文件不写死任何一个状态。颜色取自 theme 的令牌（按系统明暗自动选），不写十六进制。
"""

from __future__ import annotations

import math

from cockpit_board import theme
from cockpit_board.flowgraph import CardPosition, Edge, Graph, GraphError, load_graphs
from cockpit_board.widgets import common as c
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QButtonGroup, QComboBox, QSizePolicy, QVBoxLayout, QWidget

MIN_SCALE = 0.62  # 再小字就看不清，改成横向滚动
PARALLEL_OFFSET = 9.0  # 来回两条线之间错开的距离（画布单位）


def _tokens_for(widget: QWidget) -> theme.Tokens:
    return theme.DARK if widget.palette().color(widget.backgroundRole()).lightness() < 128 else theme.LIGHT


class FlowGraphWidget(QWidget):
    """用 QPainter 画一张 Graph。current＝现在所处的状态（来自账本），focus＝用户点中的状态。"""

    node_clicked = Signal(str)

    def __init__(self, graph: Graph | None = None) -> None:
        super().__init__()
        self.graph: Graph | None = None
        self.current: str | None = None
        self.focus: str | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setObjectName("flow_graph")
        if graph is not None:
            self.set_graph(graph)

    # ------------------------------------------------ 数据

    def set_graph(self, graph: Graph) -> None:
        self.graph = graph
        self.current = self.focus = None
        self.setMinimumWidth(int(graph.width * MIN_SCALE))
        self.updateGeometry()
        self.update()

    def set_current(self, state: str | None) -> None:
        self.current = state if self.graph and self.graph.node(state or "") else None
        self.update()

    def set_focus(self, state: str | None) -> None:
        self.focus = state if self.graph and self.graph.node(state or "") else None
        self.update()

    # ------------------------------------------------ 几何

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt 接口名
        return self.graph is not None

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        if self.graph is None:
            return 0
        return int(width * self.graph.height / self.graph.width)

    def sizeHint(self) -> QSize:  # noqa: N802
        if self.graph is None:
            return QSize(600, 200)
        return QSize(self.graph.width, self.graph.height)

    def _scale(self) -> tuple[float, float, float]:
        assert self.graph is not None
        scale = min(self.width() / self.graph.width, self.height() / self.graph.height)
        return scale, (self.width() - self.graph.width * scale) / 2, (self.height() - self.graph.height * scale) / 2

    def node_rect(self, node_id: str) -> QRectF | None:
        if self.graph is None:
            return None
        node = self.graph.node(node_id)
        if node is None:
            return None
        scale, ox, oy = self._scale()
        return QRectF(ox + node.x * scale, oy + node.y * scale, self.graph.node_width * scale, self.graph.node_height * scale)

    def node_at(self, point: QPointF) -> str | None:
        if self.graph is None:
            return None
        for node in self.graph.nodes:
            rect = self.node_rect(node.id)
            if rect is not None and rect.contains(point):
                return node.id
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        hit = self.node_at(event.position())
        if hit is not None:
            self.set_focus(hit)
            self.node_clicked.emit(hit)

    # ------------------------------------------------ 画

    def paintEvent(self, _event: QPaintEvent) -> None:  # noqa: N802
        if self.graph is None:
            return
        tokens = _tokens_for(self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale, _ox, _oy = self._scale()
        graph = self.graph
        pairs = {(e.source, e.target) for e in graph.edges}
        highlight = {e.target for e in graph.edges_from(self.current)} if self.current else set()
        labelled = {(e.source, e.target) for e in graph.edges if _edge_text(e) and (not e.minor or self._emphasised(e))}
        labels: list[tuple[QPointF, QPointF, str, float, QPointF]] = []
        for edge in graph.edges:
            mutual = (edge.target, edge.source) in pairs
            ends = self._draw_edge(painter, tokens, scale, edge, mutual)
            text = _edge_text(edge)
            if ends is not None and text and (not edge.minor or self._emphasised(edge)):
                at = (0.38 if edge.source < edge.target else 0.62) if mutual else 0.5
                both_labelled = mutual and (edge.target, edge.source) in labelled  # 来回都有字才挪开，免得压在一起
                labels.append((ends[0], ends[1], text, at if both_labelled else 0.5, ends[2] if both_labelled else QPointF(0, 0)))
        for node in graph.nodes:
            self._draw_node(painter, tokens, scale, node.id, node.label, node.id in highlight)
        for start, end, text, at, nudge in labels:  # 文字最后画：不被节点盖住
            self._draw_edge_label(painter, tokens, scale, start, end, text, at, nudge)
        painter.end()

    def _edge_color(self, tokens: theme.Tokens, source: str) -> tuple[QColor, float]:
        if self.current is not None and source == self.current:
            return QColor(tokens.accent), 2.2
        if self.focus is not None and source == self.focus:
            return QColor(tokens.hint), 2.0
        return QColor(tokens.line2), 1.2

    def _emphasised(self, edge: Edge) -> bool:
        return edge.source in (self.current, self.focus)

    def _draw_edge(self, painter: QPainter, tokens: theme.Tokens, scale: float, edge: Edge, mutual: bool) -> tuple[QPointF, QPointF, QPointF] | None:
        a, b = self.node_rect(edge.source), self.node_rect(edge.target)
        if a is None or b is None:
            return None
        color, width = self._edge_color(tokens, edge.source)
        emphasised = width > 1.5
        if edge.minor and not emphasised:
            color = QColor(tokens.line)
            width = 1.0
        pen = QPen(color, width * max(scale, 0.8))
        if edge.minor:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        start, end = _clip(a, b)
        shift_vec = QPointF(0, 0)
        if mutual:  # 来回两条线：各往自己右手边错开一点，不叠在一起
            dx, dy = end.x() - start.x(), end.y() - start.y()
            length = math.hypot(dx, dy) or 1.0
            shift = PARALLEL_OFFSET * scale
            nx, ny = -dy / length * shift, dx / length * shift
            shift_vec = QPointF(nx * 2.4, ny * 2.4)  # 文字再往自己这一侧挪远些，来回两条线的字不互相压
            start, end = QPointF(start.x() + nx, start.y() + ny), QPointF(end.x() + nx, end.y() + ny)
        painter.drawLine(start, end)
        _arrow(painter, start, end, color, 7.0 * max(scale, 0.8))
        return start, end, shift_vec

    def _draw_edge_label(self, painter: QPainter, tokens: theme.Tokens, scale: float, start: QPointF, end: QPointF,
                         text: str, at: float = 0.5, nudge: QPointF | None = None) -> None:
        font = QFont(painter.font())
        font.setPixelSize(max(9, int(11 * scale)))
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        lines = text.split("\n")
        width = max(metrics.horizontalAdvance(line) for line in lines) + 8
        height = metrics.height() * len(lines) + 2
        mid = QPointF(start.x() + (end.x() - start.x()) * at, start.y() + (end.y() - start.y()) * at)
        if nudge is not None:
            mid = QPointF(mid.x() + nudge.x(), mid.y() + nudge.y())
        box = QRectF(mid.x() - width / 2, mid.y() - height / 2, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tokens.bg))
        painter.drawRoundedRect(box, 3, 3)
        painter.setPen(QColor(tokens.fg2))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_node(self, painter: QPainter, tokens: theme.Tokens, scale: float, node_id: str, label: str, is_next: bool) -> None:
        assert self.graph is not None
        rect = self.node_rect(node_id)
        if rect is None:
            return
        is_current, is_focus = node_id == self.current, node_id == self.focus
        fill, border, border_w = QColor(tokens.card), QColor(tokens.line2), 1.2
        style = Qt.PenStyle.SolidLine
        if is_next:
            border, border_w, style = QColor(tokens.accent), 1.6, Qt.PenStyle.DashLine
        if is_focus:
            border, border_w, style = QColor(tokens.hint), 2.2, Qt.PenStyle.SolidLine
        if is_current:
            fill, border, border_w, style = QColor(tokens.accent_soft), QColor(tokens.accent), 2.6, Qt.PenStyle.SolidLine
        pen = QPen(border, border_w * max(scale, 0.8))
        pen.setStyle(style)
        painter.setPen(pen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 8 * scale, 8 * scale)
        if self.graph.is_terminal(node_id):  # 终态：里面再套一圈
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(border, 1.0))
            painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 6 * scale, 6 * scale)
        big, small = QFont(painter.font()), QFont(painter.font())
        big.setPixelSize(max(10, int(14 * scale)))
        big.setBold(True)
        small.setPixelSize(max(8, int(10 * scale)))
        inner = rect.adjusted(6, 2, -6, -2)
        top = QRectF(inner.x(), inner.y(), inner.width(), inner.height() * 0.55)
        bottom = QRectF(inner.x(), inner.y() + inner.height() * 0.55, inner.width(), inner.height() * 0.45)
        painter.setFont(big)
        painter.setPen(QColor(tokens.accent if is_current else tokens.fg))
        painter.drawText(top, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                         QFontMetricsF(big).elidedText(label, Qt.TextElideMode.ElideRight, top.width()))
        painter.setFont(small)
        painter.setPen(QColor(tokens.fg3))
        painter.drawText(bottom, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         QFontMetricsF(small).elidedText(node_id, Qt.TextElideMode.ElideRight, bottom.width()))


def _edge_text(edge: Edge) -> str:
    if edge.label and edge.actor == "user":
        return edge.label + "\n用户"
    return edge.label or ("用户" if edge.actor == "user" else "")


def _clip(a: QRectF, b: QRectF) -> tuple[QPointF, QPointF]:
    """两个节点中心连线，在各自矩形边上截断。"""
    ca, cb = a.center(), b.center()
    return _boundary(a, cb), _boundary(b, ca)


def _boundary(rect: QRectF, toward: QPointF) -> QPointF:
    center = rect.center()
    dx, dy = toward.x() - center.x(), toward.y() - center.y()
    if dx == 0 and dy == 0:
        return center
    half_w, half_h = rect.width() / 2, rect.height() / 2
    t = min(half_w / abs(dx) if dx else math.inf, half_h / abs(dy) if dy else math.inf)
    return QPointF(center.x() + dx * t, center.y() + dy * t)


def _arrow(painter: QPainter, start: QPointF, end: QPointF, color: QColor, size: float) -> None:
    angle = math.atan2(end.y() - start.y(), end.x() - start.x())
    left = QPointF(end.x() - size * math.cos(angle - 0.4), end.y() - size * math.sin(angle - 0.4))
    right = QPointF(end.x() - size * math.cos(angle + 0.4), end.y() - size * math.sin(angle + 0.4))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF([end, left, right]))


class FlowPage(QWidget):
    """流程图页：上面选图，中间选卡，下面是图，最下面说“现在在哪、下一步能去哪”。"""

    def __init__(self) -> None:
        super().__init__()
        self.graphs: tuple[Graph, ...] = ()
        self.cards: list[CardPosition] = []
        self.graph_id = ""
        self.error = ""
        try:
            self.graphs = load_graphs()
        except GraphError as error:
            self.error = str(error)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area, self.layout_ = c.page()
        outer.addWidget(self.scroll_area)
        self.picker_buttons: dict[str, object] = {}
        self.card_box = QComboBox()
        self.card_box.setObjectName("flow_card_box")
        self.card_box.currentIndexChanged.connect(self._card_changed)
        self.widget = FlowGraphWidget()
        self.widget.node_clicked.connect(lambda _node: self._render_panel())
        self._build()

    # ------------------------------------------------ 搭

    def _build(self) -> None:
        lay = self.layout_
        c.clear(lay)
        lay.addWidget(c.section("流程图", "各条线的状态怎么流转，当前在哪一步就亮哪一步；点一个状态看它的下一步"))
        if self.error:
            frame, inner = c.card("block")
            inner.addWidget(c.label("状态图数据读不了，本页不画图：" + self.error))
            lay.addWidget(frame)
            return
        group = QButtonGroup(self)
        row_items: list[QWidget | int] = []
        for graph in self.graphs:
            item = c.button(graph.title, "tab", f"{graph.title}（{graph.english}）：{graph.intro}")
            item.setCheckable(True)
            item.clicked.connect(lambda _checked=False, g=graph.id: self.select_graph(g))
            group.addButton(item)
            row_items.append(item)
            self.picker_buttons[graph.id] = item
        row_items.append(1)
        lay.addWidget(c.hrow(*row_items))
        self.intro = c.label("", "muted")
        lay.addWidget(self.intro)
        self.card_row = c.hrow(c.label("看哪张卡", "muted", wrap=False), self.card_box, 1)
        lay.addWidget(self.card_row)
        frame, inner = c.card()
        inner.addWidget(self.widget)
        lay.addWidget(frame)
        self.panel_holder = QWidget()
        self.panel_layout = QVBoxLayout(self.panel_holder)
        self.panel_layout.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.panel_holder)
        self.foot = c.label("", "small")
        lay.addWidget(self.foot)
        self.select_graph(self.graphs[0].id)

    # ------------------------------------------------ 数据进来

    def show_cards(self, cards: list[CardPosition]) -> None:
        """账本读完后调：把板上的卡放进下拉框；原来选的卡还在就保持。"""
        self.cards = cards
        if self.error:
            return
        previous = self.card_box.currentData()
        self.card_box.blockSignals(True)
        self.card_box.clear()
        self.card_box.addItem("（不指定，只看流程）", None)
        for card in cards:
            self.card_box.addItem(f"{card.project_id} · {card.mission_id} · {card.title} · {card.mission_state}", card.mission_id)
        index = self.card_box.findData(previous) if previous else -1
        self.card_box.setCurrentIndex(index if index >= 0 else 0)
        self.card_box.blockSignals(False)
        self._apply_current()

    # ------------------------------------------------ 动作

    def select_graph(self, graph_id: str) -> None:
        graph = next((g for g in self.graphs if g.id == graph_id), None)
        if graph is None or self.error:
            return
        self.graph_id = graph_id
        for key, button in self.picker_buttons.items():
            button.setChecked(key == graph_id)  # type: ignore[attr-defined]
        self.widget.set_graph(graph)
        self.intro.setText(f"{graph.title}（{graph.english}）：{graph.intro}")
        self.foot.setText(f"{graph.hint}\n图的数据：scripts/cockpit_board/flow/graphs.json；与代码对照：{graph.source}。本页只读，不能在这里改状态。")
        self._apply_current()

    def _card_changed(self, _index: int) -> None:
        self._apply_current()

    def selected_card(self) -> CardPosition | None:
        mission_id = self.card_box.currentData()
        return next((card for card in self.cards if card.mission_id == mission_id), None)

    def _apply_current(self) -> None:
        card = self.selected_card()
        self.widget.set_current(card.current(self.graph_id) if card else None)
        self._render_panel()

    def _render_panel(self) -> None:
        if self.error:
            return
        c.clear(self.panel_layout)
        graph = next((g for g in self.graphs if g.id == self.graph_id), None)
        if graph is None:
            return
        frame, inner = c.card()
        card = self.selected_card()
        current = self.widget.current
        if card is not None:
            if not current:
                inner.addWidget(c.label(f"{card.mission_id}（{card.title}）：这张图的状态账本里还没带上，只显示流程，不乱亮。", "muted"))
        subject = self.widget.focus or current
        if subject:
            who = "你点的" if subject == self.widget.focus and subject != current else (f"{card.mission_id} 现在" if card else "现在")
            inner.addWidget(self._next_block(graph, subject, who))
        else:
            inner.addWidget(c.label("点图上的一个状态，这里列出它下一步能去哪。亮色实线框＝这张卡现在在的位置；"
                                    "虚线框＝它的下一步；双层框＝终态；浅色虚线＝随时可取消 / 废弃。", "small"))
        self.panel_layout.addWidget(frame)

    def _next_block(self, graph: Graph, node_id: str, who: str) -> QWidget:
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.SPACE // 2)
        edges = graph.edges_from(node_id)
        head = f"{who}：{graph.label_of(node_id)}（{node_id}）"
        lay.addWidget(c.label(head + ("，下一步能去：" if edges else " —— 终态，没有下一步"), "section"))
        for edge in edges:
            parts = [f"→ {graph.label_of(edge.target)}（{edge.target}）"]
            if edge.label:
                parts.append(f"命令：{edge.label}")
            if edge.actor == "user":
                parts.append("只听用户本人")
            if edge.minor:
                parts.append("随时可退出")
            lay.addWidget(c.label("　".join(parts)))
        return holder
