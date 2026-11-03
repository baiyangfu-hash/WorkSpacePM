"""交出去的东西：GitHub 上开着的 PR · 门禁 · 安全签字 · 审计。首页和项目页“依赖与交付”共用。只读。

每格是一个标签片，颜色由 viewmodel 的 sev 决定；没真读到的格子 viewmodel 已经给成“未知”+ 灰色，这里不再判断。
链接只显示文字（纯文本标签），不能点开，不起浏览器。
"""

from __future__ import annotations

from cockpit_board.viewmodel import Cell, GithubVM, PrRow
from cockpit_board.widgets import common as c
from PySide6.QtWidgets import QFrame, QLabel, QWidget


def cell_chip(cell: Cell) -> QLabel:
    item = c.chip(cell.text, cell.sev)
    if cell.tip:
        item.setToolTip(cell.tip)
    return item


def ci_pairs(items: list[tuple[str, Cell]]) -> list[QWidget]:
    return [c.pair(c.label(name, "small", wrap=False), cell_chip(cell)) for name, cell in items]


def pr_line(row: PrRow) -> QFrame:
    frame, layout = c.inner()
    frame.setProperty("pr", row.number)
    frame.setProperty("gate", row.gate.text)
    title = c.label(row.title, tip=row.url)  # 标题长就换行，不能把整页撑宽
    head = c.hrow(c.label(f"#{row.number}", "mono", wrap=False), title, c.label(" · ".join(row.projects), "mono", wrap=False))
    c.fill(head, title)
    layout.addWidget(head)
    # 门禁 / CI 各项 / 安全签字 / 审计：一行放不下就换行（PR 上有十几项检查，横排会把整页撑出窗口）
    layout.addWidget(
        c.flow(
            c.pair(c.label("门禁", "q", wrap=False), cell_chip(row.gate)),
            *ci_pairs(row.ci),
            c.pair(c.label("安全签字", "q", wrap=False), cell_chip(row.safety)),
            c.pair(c.label("规则批准", "q", wrap=False), cell_chip(row.rules)),
            c.pair(c.label("审计", "q", wrap=False), cell_chip(row.audit)),
        )
    )
    if row.note:
        layout.addWidget(c.label(row.note, "small"))
    return frame


def github_block(github: GithubVM, rows: list[PrRow], empty: str) -> QFrame:
    frame, layout = c.card(dashed=not github.fresh)
    frame.setProperty("github_state", github.state)
    layout.addWidget(c.hrow(c.label(github.headline, "muted", wrap=False), 1, c.label(github.as_of, "mono", wrap=False)))
    if github.main_ci:
        layout.addWidget(c.flow(c.label("main 上最近一次", "q", wrap=False), *ci_pairs(github.main_ci)))
    if not rows:
        layout.addWidget(c.label(empty, "muted"))
    for row in rows:
        layout.addWidget(pr_line(row))
    layout.addWidget(c.label(" · ".join(github.notes), "small"))
    return frame
