"""全部项目：一张表，30 个项目时用。只读；顶上的“新建项目…”只跳到工具页的“项目”页签，自己不起任何命令。"""

from __future__ import annotations

from collections.abc import Callable

from cockpit_board.viewmodel import ProjectCard
from cockpit_board.widgets import common as c
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.addWidget(
            c.section("全部项目", "挡路和有风险的排前，未接入的排后；已归档的默认不列，勾上才列在最后；性质、状态读登记表；双击一行进项目页")
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
        layout.addWidget(c.hrow(self.show_archived, 1, self.new_button))
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
        self.all_cards: list[ProjectCard] = []
        self.cards: list[ProjectCard] = []  # 只放显示出来的那些行，双击按它找项目

    @staticmethod
    def _archived_text(count: int) -> str:
        return f"显示已归档（{count} 个）"

    def show_view(self, cards: list[ProjectCard]) -> None:
        self.all_cards = list(cards)
        self.show_archived.setText(self._archived_text(sum(1 for card in cards if card.archived)))
        self._render()

    def _render(self) -> None:
        cards = [card for card in self.all_cards if self.show_archived.isChecked() or not card.archived]
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

    def _open(self, row: int, _column: int) -> None:
        if 0 <= row < len(self.cards):
            self.on_project(self.cards[row].project_id)
