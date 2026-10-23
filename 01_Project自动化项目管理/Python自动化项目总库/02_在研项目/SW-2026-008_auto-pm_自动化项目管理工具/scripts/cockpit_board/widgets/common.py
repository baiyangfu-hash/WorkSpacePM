"""通用小部件：纯文本标签、卡片、标签片、分节标题。只用 objectName 和动态属性，不写颜色。"""

from __future__ import annotations

from cockpit_board import theme
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
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


def grid(columns: int) -> tuple[QWidget, QGridLayout]:
    holder = QWidget()
    layout = QGridLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(theme.SPACE)
    for index in range(columns):
        layout.setColumnStretch(index, 1)
    return holder, layout


def fill_grid(layout: QGridLayout, widgets: list[QWidget], columns: int) -> None:
    for index, widget in enumerate(widgets):
        widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        layout.addWidget(widget, index // columns, index % columns)


def clear(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)  # 立刻摘下来，不等事件循环，否则截图里新旧画面叠在一起
            widget.deleteLater()
        elif item.layout() is not None:
            clear(item.layout())


def kv(rows: list[tuple[str, str]]) -> QWidget:
    holder, layout = grid(2)
    layout.setColumnStretch(0, 0)
    layout.setColumnStretch(1, 1)
    for index, (key, value) in enumerate(rows):
        layout.addWidget(label(key, "muted", wrap=False), index, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(label(value), index, 1)
    return holder
