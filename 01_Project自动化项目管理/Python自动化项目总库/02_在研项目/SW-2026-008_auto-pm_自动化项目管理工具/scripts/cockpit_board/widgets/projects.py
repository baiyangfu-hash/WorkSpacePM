"""全部项目：一张表，30 个项目时用。只读。"""

from __future__ import annotations

from collections.abc import Callable

from cockpit_board.viewmodel import ProjectCard
from cockpit_board.widgets import common as c
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

HEADERS = ("项目", "健康", "里程碑", "到期", "数据覆盖", "现在在干", "问题", "最后动静")


class ProjectsPage(QWidget):
    def __init__(self, on_project: Callable[[str], None]) -> None:
        super().__init__()
        self.on_project = on_project
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.addWidget(c.section("全部项目", "受阻和有风险的排前，未接入的排后；双击一行进项目页"))
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
        self.cards: list[ProjectCard] = []

    def render(self, cards: list[ProjectCard]) -> None:
        self.cards = cards
        self.table.setRowCount(len(cards))
        for row, card in enumerate(cards):
            cells = [
                f"{card.project_id}\n{card.name}",
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
                if column == 1:
                    item.setData(Qt.ItemDataRole.UserRole, card.health)
                self.table.setItem(row, column, item)
        self.table.resizeRowsToContents()

    def _open(self, row: int, _column: int) -> None:
        if 0 <= row < len(self.cards):
            self.on_project(self.cards[row].project_id)
