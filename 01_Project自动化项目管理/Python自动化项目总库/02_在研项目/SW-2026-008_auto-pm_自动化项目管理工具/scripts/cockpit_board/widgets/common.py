"""通用小部件：纯文本标签、卡片、标签片、分节标题。只用 objectName 和动态属性，不写颜色。"""

from __future__ import annotations

from collections.abc import Sequence

from cockpit_board import theme
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def label(text: str, name: str = "", wrap: bool = True, tip: str = "") -> QLabel:
    """纯文本标签：账本和文件夹里的字一律不当富文本解释，也不能点开链接。"""
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setWordWrap(wrap and name != "section")  # 标题不换行，否则横排里会把整行撑高
    item.setOpenExternalLinks(False)
    item.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if name:
        item.setObjectName(name)
    if tip:
        item.setToolTip(tip)
    return item


def chip(text: str, sev: str = "") -> QLabel:
    item = label(text, "chip", wrap=False)
    item.setProperty("sev", sev)
    return item


def mark(sev: str) -> QLabel:
    glyph = {"ok": "✓", "block": "✕", "risk": "!", "hint": "i", "na": "–"}[sev]
    item = label(glyph, "mark", wrap=False)
    item.setProperty("sev", sev)
    return item


def example_tag() -> QLabel:
    return label("示例", "example", wrap=False)


def card(sev: str = "", dashed: bool = False) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    frame.setProperty("sev", sev)
    frame.setProperty("dashed", "true" if dashed else "false")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(theme.SPACE * 2, theme.SPACE + 2, theme.SPACE * 2, theme.SPACE + 2)
    layout.setSpacing(theme.SPACE // 2)
    return frame, layout


def inner(name: str = "inner") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(name)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(theme.SPACE, theme.SPACE, theme.SPACE, theme.SPACE)
    layout.setSpacing(theme.SPACE // 2)
    return frame, layout


def section(title: str, question: str = "") -> QWidget:
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, theme.SPACE, 0, 0)
    row.setSpacing(theme.SPACE)
    row.addWidget(label(title, "section", wrap=False))
    if question:
        row.addWidget(label(question, "q"), 1)
    else:
        row.addStretch(1)
    return holder


def hrow(*widgets: QWidget | int, spacing: int = theme.SPACE) -> QWidget:
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(spacing)
    for item in widgets:
        if isinstance(item, int):
            row.addStretch(item)
        else:
            row.addWidget(item)
    return holder


def button(text: str, name: str = "", tip: str = "", enabled: bool = True) -> QPushButton:
    item = QPushButton(text)
    if name:
        item.setObjectName(name)
    item.setToolTip(tip)
    item.setEnabled(enabled)
    item.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor)
    return item


class FlowLayout(QLayout):
    """从左到右排，放不下就换行；最小宽度只取最宽的那一个控件。

    一行里有十几个检查标签（门禁、CI 各项）时，普通横排（QHBoxLayout）的最小宽度是全部标签宽度之和，
    会把整页撑得比窗口宽、右半边被切掉（用户 2026-11-01 试用截图）。需要“可能很多个”的一行都用这个。
    """

    def __init__(self, parent: QWidget | None = None, h_spacing: int = theme.SPACE, v_spacing: int = theme.SPACE // 2) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h = h_spacing
        self._v = v_spacing

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 - Qt 接口名
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._place(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._place(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _place(self, rect: QRect, apply: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, line = area.x(), area.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x > area.x() and x + hint.width() > area.right() + 1:
                x = area.x()
                y += line + self._v
                line = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._h
            line = max(line, hint.height())
        return y + line - rect.y() + margins.bottom()


def flow(*widgets: QWidget) -> QWidget:
    """一行放不下就自动换行的一组控件（成对的“名字 + 标签片”先用 pair 捆在一起，免得换行拆开）。"""
    holder = QWidget()
    layout = FlowLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    for item in widgets:
        layout.addWidget(item)
    return holder


def pair(name: QWidget, value: QWidget) -> QWidget:
    """名字和它的标签片绑成一格，换行时不拆开。"""
    return hrow(name, value, spacing=theme.SPACE // 2)


def page() -> tuple[QScrollArea, QVBoxLayout]:
    body = QWidget()
    body.setObjectName("page")
    layout = QVBoxLayout(body)
    layout.setContentsMargins(theme.SPACE * 2, theme.SPACE, theme.SPACE * 2, theme.SPACE * 2)
    layout.setSpacing(theme.SPACE)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(body)
    return scroll, layout


def insert_widget(holder: QWidget, index: int, widget: QWidget) -> None:
    """往 hrow 造出来的一行里插控件；那一行没有盒布局就直接报错，不悄悄丢掉。"""
    layout = holder.layout()
    if not isinstance(layout, QBoxLayout):
        raise TypeError("insert_widget: 这一行没有盒布局")
    layout.insertWidget(index, widget)


def fill(holder: QWidget, widget: QWidget) -> None:
    """让 hrow 里这一格吃掉这一行剩下的宽度。长文字（会换行的标签）放在行尾又后面跟了弹簧时，
    弹簧会把标签挤成窄窄一列；用这个把剩余宽度判给文字，行里就不要再放弹簧。"""
    layout = holder.layout()
    if not isinstance(layout, QBoxLayout):
        raise TypeError("fill: 这一行没有盒布局")
    layout.setStretchFactor(widget, 1)


def grid(columns: int) -> tuple[QWidget, QGridLayout]:
    holder = QWidget()
    layout = QGridLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(theme.SPACE)
    for index in range(columns):
        layout.setColumnStretch(index, 1)
    return holder, layout


def fill_grid(layout: QGridLayout, widgets: Sequence[QWidget], columns: int) -> None:
    for index, widget in enumerate(widgets):
        widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        layout.addWidget(widget, index // columns, index % columns)


def clear(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item is None:  # count() > 0 时取不到就别空转
            break
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)  # 立刻摘下来，不等事件循环，否则截图里新旧画面叠在一起
            widget.deleteLater()
        else:
            child = item.layout()
            if child is not None:
                clear(child)


def kv(rows: list[tuple[str, str]]) -> QWidget:
    holder, layout = grid(2)
    layout.setColumnStretch(0, 0)
    layout.setColumnStretch(1, 1)
    for index, (key, value) in enumerate(rows):
        layout.addWidget(label(key, "muted", wrap=False), index, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(label(value), index, 1)
    return holder
