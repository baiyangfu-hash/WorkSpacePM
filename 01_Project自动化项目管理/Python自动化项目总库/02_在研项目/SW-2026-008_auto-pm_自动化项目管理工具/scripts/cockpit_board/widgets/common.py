"""通用小部件：纯文本标签、卡片、标签片、分节标题。只用 objectName 和动态属性，不写颜色。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

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


# ---------------------------------------------------------------- 骨架通用件（CHG-SCPT-2026-628 A）

# 三态标签：读不到数的三种说法。汇总数没数据源时画面只许出现这三个字样之一，不许画 0 或绿。
STATES = {"unchecked": "没检查", "offline": "断网未知", "unreadable": "读不懂"}
RAW_LIMIT = 4000  # “原文”块最多显示这么多字，再多截断并写明截断了多少


def state_tag(state: str, tip: str = "") -> QLabel:
    """三态标签。state 只能是 STATES 里的键，写错直接报错，不悄悄画成别的。"""
    if state not in STATES:
        raise ValueError(f"state_tag: 不认识的状态 {state!r}")
    item = label(STATES[state], "state", wrap=False, tip=tip)
    item.setProperty("state", state)
    return item


def placeholder(title: str, reason: str, command: str = "") -> QFrame:
    """统一占位卡：功能还没做的地方都用它，虚线框、没有按钮。command 写这一块以后要读的命令（只显示，不运行）。"""
    frame, layout = card(dashed=True)
    frame.setProperty("placeholder", "true")
    layout.addWidget(label(title, "heading", wrap=False))
    layout.addWidget(label("这一块还没做：" + reason, "muted"))
    if command:
        layout.addWidget(label("以后读：" + command, "mono"))
    return frame


def read_block(status: str, raw: str, state: str = "") -> QFrame:
    """“读取状态 + 原文”块：上面一行写读得怎么样（state 给了就配三态标签），下面原样放命令输出（纯文本、可选中）。"""
    frame, layout = inner("pre")
    head = [label(status, "muted")]
    if state:
        head.insert(0, state_tag(state))
    row = hrow(*head)
    fill(row, head[-1])
    layout.addWidget(row)
    shown = raw if len(raw) <= RAW_LIMIT else raw[:RAW_LIMIT] + f"\n……（截断，后面还有 {len(raw) - RAW_LIMIT} 字）"
    layout.addWidget(label(shown or "（没有输出）", "mono"))
    return frame


# ---------------------------------------------------------------- 骨架页底板（CHG-SCPT-2026-628 D）
#
# 新页每读一条只读命令，就交来一份 ReadResult；页面按它画“读取状态 + 读出来的要点 + 原文”。
# 像 HMI 上一个通讯点：先看通讯状态灯，再看数值，最后才是原始报文。


@dataclass(frozen=True)
class ReadResult:
    reader: str  # readers.READERS 的键
    command: str  # 给人看的命令，如 main.py pm missions --pid SW-2026-008
    outcome: Any = None  # actions.ReadOutcome；None = 还没读
    parsed: Any = None  # readers.Parsed：这次读到了就是这次的，没读到但有快照就是快照的
    last_note: str = ""  # 用了快照时写“上次读取：几分钟前”
    skipped: str = ""  # 没去读的原因（如没有受管项目）


def read_state(result: ReadResult) -> tuple[str, str]:
    """（三态标签的键或空串, 一句读取状态）。空串＝读到了且读得懂，其余都配三态标签之一，不画成读到了。"""
    if result.skipped:
        return "unchecked", "没读：" + result.skipped
    outcome = result.outcome
    if outcome is None:
        return "unchecked", "还没读：打开本页或点“重新读取”时读"
    if outcome.kind == "ok":
        if result.parsed is not None and result.parsed.ok:
            return "", "读到了"
        note = result.parsed.note if result.parsed is not None else ""
        return "unreadable", "命令有输出，但不是认得的格式" + (f"：{note}" if note else "")
    state = {"offline": "offline", "banner_only": "unreadable"}.get(outcome.kind, "unchecked")
    status = outcome.text
    if result.last_note and result.parsed is not None and result.parsed.ok:
        status += f"；下面的要点是{result.last_note}的结果"
    return state, status


def state_line(state: str, status: str) -> QWidget:
    """一行“三态标签 + 一句话”；state 为空串就只有那句话（读到了）。"""
    head: list[QWidget] = [label(status, "muted")]
    if state:
        head.insert(0, state_tag(state))
    row = hrow(*head)
    fill(row, head[-1])
    return row


# 页面顶上一行总状态（CHG-SCPT-2026-637）：像 HMI 画面顶上的一行总状态。几条命令里最差的那个三态排在前面。
STATE_ORDER = ("offline", "unreadable", "unchecked")


def page_status(results: Sequence[ReadResult], is_empty: Callable[[str, dict[str, Any]], bool | None]) -> tuple[str, str]:
    """（"error", 最差三态） / （"empty", ""） / （"", ""）。纯函数，测试直接调。

    - 有任何一条没读到（三态之一，含用快照顶上的）→ 错态，配最差的三态：断网未知 > 读不懂 > 没检查。快照是旧数据，不能让整页显示成“没事”。
    - 全部读到，参与判空的命令（is_empty 返回 True/False 的）都空、且至少有一条参与 → 空态，不配标签。
      is_empty 返回 None 的命令不参与判空（如进门定位、清理清单：它们“没有东西”不代表这一页没事）。
    - 其余不画。
    """
    states = [read_state(result)[0] for result in results]
    bad = {state for state in states if state}
    if bad:
        return "error", next(state for state in STATE_ORDER if state in bad)
    votes = [is_empty(result.reader, result.parsed.data) for result in results]
    judged = [vote for vote in votes if vote is not None]
    if judged and all(judged):
        return "empty", ""
    return "", ""


def shows_values(result: ReadResult) -> bool:
    """要点（数目、名字）只在读得懂时画：这次读到的，或这次没读到但有能读懂的快照（状态行写明是上次的）。"""
    return result.parsed is not None and result.parsed.ok and (result.outcome is not None or bool(result.last_note))


class ReadPage(QWidget):
    """骨架页：顶上标题和一句话，中间每条命令一块（状态、要点、原文），底下是还没做的功能占位卡。

    子类写 summary()：把 readers 解析出的 data 变成几行“名字 → 值”；写 is_empty()：这条命令读到的算不算“空”。
    不起子进程、不写文件，命令由 app 在后台线程跑完后调用 show_results()。
    empty_text、error_text 取自 flow/pages.json（shell.page_texts），画在各条命令的块上面一行（page_status）。
    """

    def __init__(
        self,
        key: str,
        title: str,
        question: str,
        todo: Sequence[tuple[str, str, str]] = (),
        empty_text: str = "",
        error_text: str = "",
    ) -> None:
        super().__init__()
        self.key = key
        self.empty_text = empty_text
        self.error_text = error_text
        self.status: tuple[str, str] = ("", "")
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, body = page()
        outer.addWidget(scroll)
        body.addWidget(section(title, question))
        self.project_line = label("", "muted")
        body.addWidget(self.project_line)
        top = QWidget()  # 顶上一行总状态单独一格，不混进下面各条命令的块
        self.top = QVBoxLayout(top)
        self.top.setContentsMargins(0, 0, 0, 0)
        body.addWidget(top)
        holder = QWidget()
        self.reads = QVBoxLayout(holder)
        self.reads.setContentsMargins(0, 0, 0, 0)
        self.reads.setSpacing(theme.SPACE)
        body.addWidget(holder)
        for name, reason, command in todo:
            body.addWidget(placeholder(name, reason, command))
        self.results: list[ReadResult] = []

    def summary(self, reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
        return []

    def is_empty(self, reader: str, data: dict[str, Any]) -> bool | None:
        """这条命令读到的是不是“空”；None＝这条命令不参与判空。默认不参与。"""
        return None

    def show_results(self, scope: str, results: Sequence[ReadResult]) -> None:
        self.results = list(results)
        self.project_line.setText(scope)
        clear(self.reads)
        clear(self.top)
        self.status = page_status(results, self.is_empty)
        kind, state = self.status
        if kind == "error" and self.error_text:
            self.top.addWidget(page_line(state, self.error_text))
        elif kind == "empty" and self.empty_text:
            self.top.addWidget(page_line("", self.empty_text))
        for result in results:
            frame, layout = card()
            layout.addWidget(label(result.command, "heading"))
            state, status = read_state(result)
            if shows_values(result):
                rows = self.summary(result.reader, result.parsed.data)
                if rows:
                    layout.addWidget(kv(rows))
            outcome = result.outcome
            raw = "" if outcome is None else (outcome.stdout if outcome.kind == "ok" else (outcome.stderr or outcome.stdout))
            layout.addWidget(read_block(status, raw, state))
            self.reads.addWidget(frame)


def page_line(state: str, text: str) -> QFrame:
    """页面顶上那一行总状态：一张卡里一行“三态标签 + 文案”（空态不配标签）。"""
    frame, layout = card()
    frame.setProperty("pagestatus", "true")
    layout.addWidget(state_line(state, text))
    return frame


def count_text(rows: Sequence[Any], unit: str) -> str:
    """读到了才数：列表本身是真数据，空列表就是“没有”，写“没有”而不是 0。"""
    return f"{len(rows)} {unit}" if rows else "没有"


def flag_text(value: Any, yes: str, no: str) -> str:
    """命令的 true / false / null 三态：null（命令自己说没查）一律写“没检查”，不当成“没有”。"""
    if value is None:
        return STATES["unchecked"]
    if isinstance(value, bool):
        return yes if value else no
    return f"{yes} {value}" if value else no
