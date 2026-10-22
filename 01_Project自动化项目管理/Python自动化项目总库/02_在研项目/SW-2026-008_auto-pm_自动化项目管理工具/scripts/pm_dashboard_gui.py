"""驾驶舱看板 v1（PySide6 桌面界面，只读）- 把多项目安灯板原型做成真正的窗口

数据层全部复用同目录的 ``pm_dashboard.py``（build_board / lamp / recent_events），本文件只管画界面。
设计稿：/mnt/project-files/plans/驾驶舱看板设计_20261022.md（共享文件夹）。

两个页签：
    - 项目经理：顶上“要你定”最多 3 件；下面一行一个项目一盏灯，点开看这个项目的全部业务变更和实施卡；
      工具与验证项目收在最后一组；底部最近 7 天动态和灯色说明。
    - 开发人员：每个项目五栏 —— 在干 / 等你 / 搁着 / 已关（近两周）/ 账本遗留。

只读保证（和原型一样，另加界面层的）：
    - 账本先拷到临时目录，再 SQLite 只读打开（mode=ro + PRAGMA query_only），由 pm_dashboard 负责；
    - 老驾驶舱后台只调 snapshot()；
    - 窗口里唯一的按钮是“重新读取”（再读一遍，不写任何东西）。没有开始执行、启动 Codex、合并、删除、
      切换发布这类按钮，以后也不加。测试会把窗口里所有按钮、菜单、可编辑框都清点一遍；
    - 所有文字都按纯文本显示，账本里的标题再怪也不会变成链接或富文本。

运行方式（控制根下，或双击控制根的“双击打开驾驶舱看板.bat”）：
    python -B <本脚本> --root .
    python -B <本脚本> --root . --screenshot 看板.png   # 离屏截两张图后退出（自查用）
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import traceback
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pm_dashboard as pd  # noqa: E402 - 和本文件同目录的数据层
from PySide6.QtCore import QObject, QSize, Qt, QThread, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

WINDOW_TITLE = "驾驶舱看板（只读）"
REFRESH_TEXT = "重新读取"
# 窗口里允许出现的按钮文字只有这一个；测试按这张表清点。
ALLOWED_BUTTON_TEXTS = frozenset({REFRESH_TEXT})
AUTO_REFRESH_MINUTES = 10
CARDS_PER_COLUMN = 6
DEV_COLUMNS = (*pd.COLUMNS, "账本遗留")

LAMP_COLOR = {"red": "#d93025", "amber": "#e8a200", "green": "#1e8e3e", "idle": "#9aa0a6"}
LAMP_WORD = {"red": "红", "amber": "黄", "green": "绿", "idle": "灰"}
LAMP_RANK = {"red": 0, "amber": 1, "green": 2, "idle": 3}

STYLE = """
QMainWindow, QWidget#page { background: #f4f5f7; }
QLabel { color: #1f2328; }
QLabel#title { font-size: 20px; font-weight: 700; }
QLabel#meta, QLabel#small { color: #5f6368; }
QLabel#section { font-size: 15px; font-weight: 700; margin-top: 6px; }
QLabel#example { color: #8a5a00; background: #fff3cd; padding: 0 4px; }
QFrame#ask { background: #ffffff; border: 1px solid #f1b8b4; border-left: 5px solid #d93025;
    border-radius: 6px; }
QFrame#none { background: #ffffff; border: 1px dashed #c4c7cc; border-radius: 6px; }
QFrame#column { background: #eceef1; border-radius: 6px; }
QFrame#card { background: #ffffff; border: 1px solid #d5d8dc; border-radius: 5px; }
QFrame#leftover { background: #fff8e1; border: 1px solid #f0d58a; border-radius: 5px; }
QFrame#project { background: #ffffff; border: 1px solid #d5d8dc; border-radius: 8px; }
QTreeWidget, QListWidget { background: #ffffff; border: 1px solid #d5d8dc; border-radius: 6px; }
QTreeWidget::item { padding: 4px 2px; }
QTabBar::tab { padding: 8px 22px; font-size: 14px; }
QTabBar::tab:selected { font-weight: 700; }
"""


# ---------------------------------------------------------------- 小部件


def lamp_icon(color: str, size: int = 18) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(LAMP_COLOR[color]))
    painter.setPen(QColor("#00000030"))
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.end()
    return QIcon(pixmap)


def text_label(text: str, name: str = "", wrap: bool = True, tip: str = "") -> QLabel:
    """纯文本标签：账本和文件夹里的字一律不当富文本解释，也不能点开链接。"""
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(wrap)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if name:
        label.setObjectName(name)
    if tip:
        label.setToolTip(tip)
    return label


def framed(name: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(name)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(3)
    return frame, layout


def clear_layout(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def example_mark(flag: bool) -> str:
    return "【示例】" if flag else ""


def column_counts(project: pd.Project, now: datetime) -> dict[str, int]:
    counts = dict.fromkeys(pd.COLUMNS, 0)
    for mission in project.missions:
        if mission.column != "已关":
            counts[mission.column] += 1
    counts["已关"] = len(pd._recent_closed(project, now))
    return counts


def last_moved(project: pd.Project) -> datetime | None:
    moments = [m.updated_at for m in project.missions if m.updated_at]
    if project.last_commit:
        moments.append(project.last_commit)
    return max(moments, default=None)


# ---------------------------------------------------------------- 后台读数据


class BoardLoader(QThread):
    """在后台线程里读一遍（老驾驶舱后台一次要十几秒，不能卡住窗口）。只读。"""

    loaded = Signal(object, bool)
    failed = Signal(str)

    def __init__(self, options: argparse.Namespace, use_legacy: bool, parent: QObject | None):
        super().__init__(parent)
        self.options = options
        self.use_legacy = use_legacy

    def run(self) -> None:
        try:
            self.loaded.emit(load_board(self.options, self.use_legacy), self.use_legacy)
        except Exception as error:  # noqa: BLE001 - 读失败只在状态栏说一声，窗口不挂
            self.failed.emit(f"{type(error).__name__}: {error}")


def load_board(options: argparse.Namespace, use_legacy: bool) -> pd.Board:
    now = options.now or datetime.now(UTC)
    board = pd.build_board(
        options.root,
        options.db,
        now,
        use_git=not options.no_git,
        use_legacy=use_legacy,
        legacy_factory=getattr(options, "legacy_factory", None),
    )
    if options.examples:
        board = pd.add_examples(board, now)
    return board


# ---------------------------------------------------------------- 主窗口


class DashboardWindow(QMainWindow):
    def __init__(self, options: argparse.Namespace) -> None:
        super().__init__()
        self.options = options
        self.offset: timezone = options.offset
        self.board: pd.Board | None = None
        self._loaders: list[BoardLoader] = []
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1360, 860)

        central = QWidget()
        central.setObjectName("page")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(16, 12, 16, 12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(text_label("驾驶舱看板 · 多项目安灯板", "title", wrap=False))
        self.meta = text_label("正在读取账本和项目文件夹……", "meta")
        titles.addWidget(self.meta)
        header.addLayout(titles, 1)
        self.status = text_label("", "small")
        header.addWidget(self.status)
        self.refresh_button = QPushButton(REFRESH_TEXT)
        self.refresh_button.setObjectName("refresh")
        self.refresh_button.setToolTip("把账本和项目文件夹再读一遍，不写任何东西")
        self.refresh_button.clicked.connect(self.reload)
        header.addWidget(self.refresh_button)
        outer.addLayout(header)

        self.tabs = QTabWidget()
        self.pm_page, self.pm_layout = self._page()
        self.dev_page, self.dev_layout = self._page()
        self.tabs.addTab(self._scroll(self.pm_page), "项目经理")
        self.tabs.addTab(self._scroll(self.dev_page), "开发人员")
        outer.addWidget(self.tabs, 1)
        outer.addWidget(
            text_label(
                "只读看板：读账本和项目文件夹，不写任何东西；窗口里没有执行按钮。"
                "要定的事在线程里回一句话，由主执行去办。",
                "small",
            )
        )
        self.setCentralWidget(central)

        self.timer = QTimer(self)
        self.timer.setInterval(AUTO_REFRESH_MINUTES * 60 * 1000)
        self.timer.timeout.connect(self.reload)

    @staticmethod
    def _page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(8)
        return page, layout

    @staticmethod
    def _scroll(page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        return scroll

    # ------------------------------------------------ 读取

    def reload(self) -> None:
        """先不带老后台快读一遍（不到 1 秒），再在后台接老驾驶舱后台的措辞（十几秒）。"""
        if any(loader.isRunning() for loader in self._loaders):
            return
        self.refresh_button.setEnabled(False)
        self.status.setText("正在读取……")
        self._start(use_legacy=False)

    def _start(self, use_legacy: bool) -> None:
        loader = BoardLoader(self.options, use_legacy, self)
        loader.loaded.connect(self._on_loaded)
        loader.failed.connect(self._on_failed)
        loader.finished.connect(lambda: self._loaders.remove(loader))
        self._loaders.append(loader)
        loader.start()

    def _on_loaded(self, board: pd.Board, with_legacy: bool) -> None:
        self.show_board(board)
        if not with_legacy and not self.options.no_legacy:
            self.status.setText("正在接老驾驶舱后台的措辞（约 20 秒），先看这一版……")
            self._start(use_legacy=True)
            return
        self.status.setText("")
        self.refresh_button.setEnabled(True)
        self.timer.start()

    def _on_failed(self, message: str) -> None:
        self.status.setText("这次没读成：" + pd._short(message, 80))
        self.refresh_button.setEnabled(True)

    # ------------------------------------------------ 画

    def show_board(self, board: pd.Board) -> None:
        self.board = board
        stamp = pd._when(board.generated_at, self.offset)
        notes = [f"数据截至 {stamp}", board.ledger_note]
        if board.legacy_note:
            notes.append(board.legacy_note)
        if board.example:
            notes.append("含示例卡（标【示例】的不是真数据）")
        self.meta.setText(" · ".join(notes))
        clear_layout(self.pm_layout)
        clear_layout(self.dev_layout)
        self._fill_pm(board)
        self._fill_dev(board)

    def _fill_pm(self, board: pd.Board) -> None:
        now = board.generated_at
        layout = self.pm_layout
        layout.addWidget(
            text_label(f"要你定（最多 {pd.MAX_DECISIONS} 件，最久的排前面）", "section")
        )
        if board.decisions:
            row = QHBoxLayout()
            for item in board.decisions:
                frame, inner = framed("ask")
                head = text_label(f"{item.project_id}  {item.ask}{example_mark(item.example)}")
                head.setFont(QFont(head.font().family(), -1, QFont.Weight.Bold))
                inner.addWidget(head)
                inner.addWidget(text_label(item.subject))
                waited = "等了 " + pd._ago(now, item.since) if item.since else "日期未记"
                inner.addWidget(text_label(f"{waited} · 在线程里回一句话，不在这里点", "small"))
                row.addWidget(frame, 1)
            for _ in range(pd.MAX_DECISIONS - len(board.decisions)):
                row.addStretch(1)
            holder = QWidget()
            holder.setLayout(row)
            layout.addWidget(holder)
            if board.decision_overflow:
                layout.addWidget(
                    text_label(
                        f"还有 {board.decision_overflow} 件排在后面，前面定完再给你。", "small"
                    )
                )
        else:
            frame, inner = framed("none")
            inner.addWidget(text_label("目前没有要你定的事。"))
            layout.addWidget(frame)

        business = [p for p in board.projects if not p.tool]
        tools = [p for p in board.projects if p.tool]
        layout.addWidget(
            text_label("项目（红灯排前，灰灯排后；点开一行看全部业务变更）", "section")
        )
        self.project_tree = self._project_tree(business, tools, now)
        layout.addWidget(self.project_tree, 1)

        bottom = QHBoxLayout()
        events_box = QVBoxLayout()
        events_box.addWidget(text_label("最近 7 天动态", "section"))
        events = QListWidget()
        events.setObjectName("events")
        events.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        events.setWordWrap(True)
        events.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for moment, project_id, text, example, date_only in pd.recent_events(board):
            stamp = moment.strftime("%m-%d") if date_only else pd._when(moment, self.offset)
            events.addItem(QListWidgetItem(f"{stamp}  {project_id}  {text}{example_mark(example)}"))
        if events.count() == 0:
            events.addItem(QListWidgetItem("这 7 天账本和变更记录里都没有新动静。"))
        events.setFixedHeight(min(200, 30 + 24 * events.count()))
        events_box.addWidget(events)
        bottom.addLayout(events_box, 3)
        bottom.addWidget(self._legend(), 2, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(bottom)

    def _project_tree(
        self, business: list[pd.Project], tools: list[pd.Project], now: datetime
    ) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setObjectName("projects")
        tree.setColumnCount(4)
        tree.setHeaderLabels(
            ["项目", "情况", "四栏：在干 / 等你 / 搁着 / 近两周已关", "最近一条业务变更"]
        )
        tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tree.setWordWrap(True)
        tree.setUniformRowHeights(False)
        header = tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((300, 330, 300)):
            tree.setColumnWidth(column, width)
        header.setStretchLastSection(True)
        for project in self._sorted(business, now):
            tree.addTopLevelItem(self._project_item(project, now))
        if tools:
            group = QTreeWidgetItem([f"工具与验证项目（{len(tools)} 个，驾驶舱自己和测试台）"])
            group.setForeground(0, QBrush(QColor("#5f6368")))
            group.setFirstColumnSpanned(True)
            for project in self._sorted(tools, now):
                group.addChild(self._project_item(project, now))
            tree.addTopLevelItem(group)
            group.setFirstColumnSpanned(True)
            group.setExpanded(False)
        if not business and not tools:
            tree.addTopLevelItem(QTreeWidgetItem(["没找到项目"]))
        tree.setMinimumHeight(min(520, 80 + 46 * (len(business) + 1)))
        return tree

    @staticmethod
    def _sorted(projects: list[pd.Project], now: datetime) -> list[pd.Project]:
        return sorted(projects, key=lambda p: (LAMP_RANK[pd.lamp(p, now)[0]], p.project_id))

    def _project_item(self, project: pd.Project, now: datetime) -> QTreeWidgetItem:
        color, reason = pd.lamp(project, now)
        counts = column_counts(project, now)
        chips = "  ".join(f"{column} {counts[column]}" for column in pd.COLUMNS)
        doing = [m for m in project.missions if m.column == "在干"]
        if doing:
            chips += "\n在干：" + pd._short(doing[0].title, 34) + example_mark(doing[0].example)
        situation = (
            f"{LAMP_WORD[color]}灯：{reason}\n最后动静 {pd._when(last_moved(project), self.offset)}"
        )
        legacy = project.legacy
        if legacy and legacy.readable:
            situation += f"\n阶段 {legacy.milestone} · 风险 {legacy.risk}"
        latest = project.changes[-1] if project.changes else None
        change = (
            f"{latest.change_id} {pd._short(latest.what, 60)}\n{pd._short(latest.status, 40)}"
            if latest
            else "还没有业务变更记录"
        )
        item = QTreeWidgetItem(
            [f"{project.project_id}\n{project.name}".strip(), situation, chips, change]
        )
        item.setIcon(0, lamp_icon(color))
        item.setData(0, Qt.ItemDataRole.UserRole, color)
        item.setToolTip(1, reason)
        lines = max(cell.count("\n") + 1 for cell in (situation, chips, change))
        item.setSizeHint(1, QSize(100, 12 + 21 * lines))
        if counts["等你"]:
            item.setForeground(2, QBrush(QColor("#b3261e")))
        # 点开：这个项目的全部业务变更（参考旧原型 V13 的变更矩阵）、实施卡、所在文件夹。
        for record in reversed(project.changes):
            child = QTreeWidgetItem(
                [
                    record.change_id,
                    f"{pd._short(record.raised, 12)} · {record.kind}",
                    pd._short(record.status, 60),
                    pd._short(record.what, 160),
                ]
            )
            child.setToolTip(3, record.what)
            item.addChild(child)
        if not project.changes:
            item.addChild(QTreeWidgetItem(["", "这个项目还没有业务变更记录"]))
        for card in project.cards:
            item.addChild(
                QTreeWidgetItem(
                    [card.card_id, "实施卡", card.status or "状态未写", pd._short(card.title, 100)]
                )
            )
        if project.root:
            path = QTreeWidgetItem(["文件夹", project.root])
            path.setForeground(1, QBrush(QColor("#5f6368")))
            item.addChild(path)
        return item

    @staticmethod
    def _legend() -> QWidget:
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(1, 1)
        lines = (
            ("red", f"红：有卡住的，或等你超过 {pd.WAITING_RED_DAYS} 天"),
            (
                "amber",
                f"黄：搁着超过 {pd.PARKED_YELLOW_DAYS} 天、开着超过 {pd.OPEN_SOFT_LIMIT} 张、"
                f"账本有遗留，或 {pd.QUIET_YELLOW_DAYS} 天没动静",
            ),
            ("green", "绿：正常"),
            ("idle", "灰：还没接入驾驶舱"),
        )
        for row, (color, text) in enumerate(lines):
            dot = QLabel()
            dot.setPixmap(lamp_icon(color, 14).pixmap(14, 14))
            grid.addWidget(dot, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(text_label(text, "small"), row, 1)
        return box

    def _fill_dev(self, board: pd.Board) -> None:
        now = board.generated_at
        layout = self.dev_layout
        issues = [item for project in board.projects for item in project.attention]
        layout.addWidget(
            text_label(
                f"每个项目五栏：在干 / 等你 / 搁着 / 已关（近 {pd.RECENT_CLOSED_DAYS} 天）/ 账本遗留。"
                f"账本遗留共 {len(issues)} 条，交主执行清理，不在看板上动。",
                "small",
            )
        )
        if board.legacy_notices:
            layout.addWidget(
                text_label("老驾驶舱后台的提示：" + "；".join(board.legacy_notices), "small")
            )
        shown = [
            p
            for p in sorted(board.projects, key=lambda p: (p.tool, p.project_id))
            if any(m.column != "已关" for m in p.missions)
            or pd._recent_closed(p, now)
            or p.cards
            or p.attention
        ]
        if not shown:
            frame, inner = framed("none")
            inner.addWidget(
                text_label(
                    f"账本里没有开着的卡，近 {pd.RECENT_CLOSED_DAYS} 天也没有收口，也没有遗留。"
                )
            )
            layout.addWidget(frame)
        for project in shown:
            layout.addWidget(self._dev_project(project, now))
        layout.addStretch(1)

    def _dev_project(self, project: pd.Project, now: datetime) -> QFrame:
        frame, inner = framed("project")
        frame.setProperty("project_id", project.project_id)
        color, _ = pd.lamp(project, now)
        head = QHBoxLayout()
        dot = QLabel()
        dot.setPixmap(lamp_icon(color, 14).pixmap(14, 14))
        head.addWidget(dot)
        title = text_label(f"{project.project_id} {project.name}", wrap=False)
        title.setFont(QFont(title.font().family(), -1, QFont.Weight.Bold))
        head.addWidget(title)
        head.addWidget(text_label(project.root, "small", wrap=False), 1)
        inner.addLayout(head)
        if project.legacy is not None:
            legacy = project.legacy
            inner.addWidget(
                text_label(
                    "老驾驶舱后台："
                    + (
                        f"{legacy.progress} · 验证 {legacy.verification} · 负责 {legacy.owner}"
                        if legacy.readable
                        else "这个项目的记录它读不了，下面几栏来自账本只读数据"
                    ),
                    "small",
                )
            )
        columns = QHBoxLayout()
        for column in DEV_COLUMNS:
            columns.addWidget(self._dev_column(project, column, now), 1)
        inner.addLayout(columns)
        if project.cards:
            inner.addWidget(
                text_label(
                    "实施卡（文件夹）："
                    + "；".join(
                        f"{card.card_id} {pd._short(card.status, 24) or '状态未写'}"
                        for card in project.cards
                    ),
                    "small",
                )
            )
        return frame

    def _dev_column(self, project: pd.Project, column: str, now: datetime) -> QFrame:
        frame, inner = framed("column")
        frame.setProperty("column", column)
        if column == "账本遗留":
            entries = sorted(project.attention, key=lambda item: item.since or now)
            inner.addWidget(text_label(f"{column} · {len(entries)}", "section"))
            for entry in entries[:CARDS_PER_COLUMN]:
                card, lines = framed("leftover")
                lines.addWidget(text_label(f"{entry.what} · {pd._when(entry.since, self.offset)}"))
                lines.addWidget(text_label(entry.detail, "small"))
                inner.addWidget(card)
            remaining = len(entries) - CARDS_PER_COLUMN
        else:
            missions = (
                pd._recent_closed(project, now)
                if column == "已关"
                else [m for m in project.missions if m.column == column]
            )
            missions.sort(key=lambda m: m.updated_at or now, reverse=True)
            inner.addWidget(text_label(f"{column} · {len(missions)}", "section"))
            for mission in missions[:CARDS_PER_COLUMN]:
                inner.addWidget(self._dev_card(mission, now))
            remaining = len(missions) - CARDS_PER_COLUMN
        if remaining > 0:
            inner.addWidget(text_label(f"另有 {remaining} 张", "small"))
        inner.addStretch(1)
        return frame

    def _dev_card(self, mission: pd.MissionInfo, now: datetime) -> QFrame:
        card, lines = framed("card")
        title = text_label(pd._short(mission.title, 70) + example_mark(mission.example))
        title.setFont(QFont(title.font().family(), -1, QFont.Weight.DemiBold))
        lines.addWidget(title)
        state = pd.STATE_LABEL.get(mission.state, mission.state)
        lines.addWidget(text_label(f"{mission.mission_id} · {state}", "small"))
        run = mission.run
        if run is not None and mission.column != "已关":
            lease = (
                "租约到 " + pd._when(run.lease_expires, self.offset)
                if run.lease_expires and run.lease_expires > now
                else "未持租约"
            )
            lines.addWidget(text_label(f"{run.executor} · {run.state} · {lease}", "small"))
            if run.checkpoint:
                lines.addWidget(text_label("断点：" + pd._short(run.checkpoint, 60), "small"))
        if mission.change_id:
            lines.addWidget(
                text_label(
                    f"{mission.change_id} · 收口 {mission.closure_state or '未开始'}", "small"
                )
            )
        lines.addWidget(text_label("更新 " + pd._when(mission.updated_at, self.offset), "small"))
        return card


# ---------------------------------------------------------------- 命令行


def parse_options(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="驾驶舱看板 v1（只读桌面界面）")
    parser.add_argument("--root", default=".", help="工作空间根（控制根）")
    parser.add_argument("--db", default="", help="账本路径，默认 <root>/.auto-pm/continuity.db")
    parser.add_argument("--now", default="", help="按这个时刻判灯（ISO 时间），默认现在")
    parser.add_argument("--utc-offset", type=float, default=None, help="显示用时区，如 -7")
    parser.add_argument("--examples", action="store_true", help="叠加几张示例卡（只在内存里）")
    parser.add_argument("--no-git", action="store_true", help="不读 git 最后提交时间")
    parser.add_argument("--no-legacy", action="store_true", help="不调老驾驶舱后台（快）")
    parser.add_argument(
        "--screenshot", default="", help="离屏画好后把两个页签各截一张 PNG 再退出（自查用）"
    )
    options = parser.parse_args(argv)
    options.root = Path(options.root).resolve()
    options.db = Path(options.db) if options.db else options.root / pd.DB_RELATIVE
    options.now = pd.parse_time(options.now) if options.now else None
    options.offset = (
        timezone(timedelta(hours=options.utc_offset))
        if options.utc_offset is not None
        else datetime.now().astimezone().tzinfo
    )
    return options


def screenshot(window: DashboardWindow, target: Path) -> list[Path]:
    """把两个页签各截一张图，文件名加 _项目经理 / _开发人员。"""
    saved = []
    for index in range(window.tabs.count()):
        window.tabs.setCurrentIndex(index)
        QApplication.processEvents()
        path = target.with_name(f"{target.stem}_{window.tabs.tabText(index)}{target.suffix}")
        window.grab().save(str(path))
        saved.append(path)
    return saved


def main(argv: list[str] | None = None) -> int:
    options = parse_options(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyleSheet(STYLE)
    font = app.font()
    font.setFamilies(["Microsoft YaHei UI", "Noto Sans CJK SC", "PingFang SC", font.family()])
    font.setPointSize(10)
    app.setFont(font)
    window = DashboardWindow(options)
    if options.screenshot:
        window.show_board(load_board(options, use_legacy=not options.no_legacy))
        first = window.project_tree.topLevelItem(0)
        if first is not None:
            first.setExpanded(True)  # 截图里顺带演示“点开一行看全部业务变更”
        window.show()
        QApplication.processEvents()
        for path in screenshot(window, Path(options.screenshot)):
            print(str(path))
        return 0
    window.show()
    QTimer.singleShot(0, window.reload)
    return app.exec()


def _crash_report() -> None:
    """双击启动没有黑窗口，出错时把原因写到系统临时目录（不写进工作空间）。"""
    path = Path(tempfile.gettempdir()) / "驾驶舱看板_启动错误.txt"
    path.write_text(traceback.format_exc(), encoding="utf-8")
    print(f"启动出错，原因已写到 {path}", file=sys.stderr)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        _crash_report()
        sys.exit(1)
