"""全部项目：一张表，30 个项目时用。只读；顶上的“新建项目…”只跳到工具页的“项目”页签，自己不起任何命令。"""

from __future__ import annotations

from collections.abc import Callable

from cockpit_board import theme
from cockpit_board.viewmodel import ProjectCard
from cockpit_board.widgets import common as c
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

HEADERS = ("项目", "性质", "状态", "健康", "里程碑", "到期", "数据覆盖", "现在在干", "问题", "最后动静")
HEALTH_COLUMN = HEADERS.index("健康")


class ProjectsPage(QWidget):
    def __init__(self, on_project: Callable[[str], None], on_new_project: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.on_project = on_project
        self.kind_filter = "all"
        self.health_filter = "all"
        self.view_mode = "table"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.addWidget(
            c.section("全部项目", "挡路和有风险的排前，未接入的排后；已归档的默认不列，勾上才列在最后；性质、状态读登记表；双击或点卡片进项目页")
        )
        # CHG-SCPT-2026-652：默认不列已归档的；只读，勾选只改这一页显示哪些行
        self.show_archived = QCheckBox(self._archived_text(0))
        self.show_archived.setObjectName("show_archived")
        self.show_archived.setChecked(False)
        self.show_archived.toggled.connect(lambda _checked: self._render())
        # CHG-SCPT-2026-654：只跳页（工具页“项目”页签），新建、登记都在那边先预览再运行
        self.new_button = c.button("新建项目…", "", "去“工具”页的“项目”页签：新建项目、登记都在那里", enabled=on_new_project is not None)
        if on_new_project is not None:
            self.new_button.clicked.connect(lambda _checked=False: on_new_project())
        self.mode_pills: dict[str, c.ClickBox] = {}
        mode_widgets: list[QWidget | int] = [self.show_archived, 1]
        for mkey, mlabel in (("table", "表格"), ("cards", "卡片")):
            pill = c.click_row("pill_filter", f"按{mlabel}看", f"用{mlabel}方式浏览项目", c.quiet(mlabel, "small"))
            pill.setProperty("active", "true" if mkey == "table" else "false")
            pill.activated.connect(lambda k=mkey: self.set_view_mode(k))
            self.mode_pills[mkey] = pill
            mode_widgets.append(pill)
        mode_widgets.append(self.new_button)
        layout.addWidget(c.hrow(*mode_widgets))
        # 快筛行：使用 ClickBox（不增设 QPushButton，保持全部项目页按钮白名单与只读不变式）
        self.kind_pills: dict[str, c.ClickBox] = {}
        self.health_pills: dict[str, c.ClickBox] = {}
        filter_widgets: list[QWidget | int] = []
        for kkey, klabel in (("all", "全部性质"), ("equipment", "设备"), ("library", "公共库"), ("tool", "工具"), ("test", "测试")):
            kp = c.click_row("pill_filter", f"按{klabel}筛", "按项目性质过滤", c.quiet(klabel, "small"))
            kp.setProperty("active", "true" if kkey == "all" else "false")
            kp.activated.connect(lambda k=kkey: self.set_kind_filter(k))
            self.kind_pills[kkey] = kp
            filter_widgets.append(kp)
        filter_widgets.append(1)
        for hkey, hlabel in (("all", "全部健康"), ("block", "挡路"), ("risk", "有风险"), ("ok", "正常")):
            hp = c.click_row("pill_filter", f"按{hlabel}筛", "按健康状态过滤", c.quiet(hlabel, "small"))
            hp.setProperty("active", "true" if hkey == "all" else "false")
            hp.activated.connect(lambda k=hkey: self.set_health_filter(k))
            self.health_pills[hkey] = hp
            filter_widgets.append(hp)
        layout.addWidget(c.hrow(*filter_widgets))

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setObjectName("projects")
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setWordWrap(True)
        self.table.cellDoubleClicked.connect(self._open)
        layout.addWidget(self.table, 1)

        self.cards_scroll, self.cards_body = c.page()
        self.cards_scroll.setVisible(False)
        layout.addWidget(self.cards_scroll, 1)

        self.all_cards: list[ProjectCard] = []
        self.cards: list[ProjectCard] = []  # 只放显示出来的那些行，双击按它找项目

    @staticmethod
    def _archived_text(count: int) -> str:
        return f"显示已归档（{count} 个）"

    @staticmethod
    def _sync_pills(pills: dict[str, c.ClickBox], active: str) -> None:
        for k, box in pills.items():
            box.setProperty("active", "true" if k == active else "false")
            box.style().unpolish(box)
            box.style().polish(box)

    def set_kind_filter(self, key: str) -> None:
        self.kind_filter = key
        self._sync_pills(self.kind_pills, key)
        self._render()

    def set_health_filter(self, key: str) -> None:
        self.health_filter = key
        self._sync_pills(self.health_pills, key)
        self._render()

    def set_view_mode(self, mode: str) -> None:
        self.view_mode = mode
        self._sync_pills(self.mode_pills, mode)
        self.table.setVisible(mode == "table")
        self.cards_scroll.setVisible(mode == "cards")
        self._render()

    def show_view(self, cards: list[ProjectCard]) -> None:
        self.all_cards = list(cards)
        self.show_archived.setText(self._archived_text(sum(1 for card in cards if card.archived)))
        self._render()

    _KIND_LABEL = {
        "equipment": "设备",
        "library": "公共库",
        "tool": "工具",
        "test": "测试",
    }

    def _matches(self, card: ProjectCard) -> bool:
        if not self.show_archived.isChecked() and card.archived:
            return False
        if self.kind_filter != "all" and card.kind_label != self._KIND_LABEL.get(self.kind_filter, self.kind_filter):
            return False
        if self.health_filter != "all" and card.health != self.health_filter:
            return False
        return True

    def _render(self) -> None:
        cards = [card for card in self.all_cards if self._matches(card)]
        self.cards = cards
        self.table.setRowCount(len(cards))
        for row, card in enumerate(cards):
            cells = [
                f"{card.project_id}\n{card.name}",
                card.kind_label,
                card.status_label,
                card.health_label,
                card.milestone,
                card.due_text,
                card.coverage.text(),
                card.now_card,
                "、".join(i.title for i in card.issues) or "—",
                card.last_text,
            ]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                if column == HEALTH_COLUMN:
                    item.setData(Qt.ItemDataRole.UserRole, card.health)
                self.table.setItem(row, column, item)
        self.table.resizeRowsToContents()
        c.clear(self.cards_body)
        if not cards:
            self.cards_body.addWidget(c.label("当前筛选下没有项目。", "muted"))
            return
        holder, grid_lay = c.grid(2)
        tiles: list[QWidget] = []
        for card in cards:
            tiles.append(self._card_tile(card))
        c.fill_grid(grid_lay, tiles, 2)
        self.cards_body.addWidget(holder)

    def _card_tile(self, card: ProjectCard) -> QFrame:
        frame = c.ClickBox("project_bay", f"打开 {card.project_id}", "进入项目舱详情")
        frame.activated.connect(lambda pid=card.project_id: self.on_project(pid))
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(theme.SPACE * 2, theme.SPACE + 2, theme.SPACE * 2, theme.SPACE + 2)
        lay.setSpacing(theme.SPACE // 2)
        sev = {"block": "block", "risk": "risk", "ok": "ok", "old": "hint"}.get(card.health, "na")
        lay.addWidget(c.hrow(
            c.quiet(card.project_id, "mono"),
            c.chip(card.kind_label, "hint" if card.kind_label in self._KIND_LABEL.values() else "na"),
            c.chip(card.status_label, "na" if card.archived else ""),
            1,
            c.chip(card.health_label, sev),
        ))
        lay.addWidget(c.quiet(card.name, "section"))
        lay.addWidget(c.quiet(f"在干：{card.now_card} · 里程碑：{card.milestone} · 到期：{card.due_text}", "small"))
        lay.addWidget(c.quiet(f"问题：{'、'.join(i.title for i in card.issues[:3]) or '无'} · 覆盖：{card.coverage.text()}", "small"))
        return frame

    def _open(self, row: int, _column: int) -> None:
        if 0 <= row < len(self.cards):
            self.on_project(self.cards[row].project_id)
