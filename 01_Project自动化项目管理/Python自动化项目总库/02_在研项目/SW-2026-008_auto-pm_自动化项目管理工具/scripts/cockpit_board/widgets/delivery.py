"""交出去的东西：GitHub 上开着的 PR · 门禁 · 安全签字 · 审计。首页和项目页“依赖与交付”共用。只读。

每格是一个标签片，颜色由 viewmodel 的 sev 决定；没真读到的格子 viewmodel 已经给成“未知”+ 灰色，这里不再判断。
链接只显示文字（纯文本标签），不能点开，不起浏览器。
"""

from __future__ import annotations

from cockpit_board.viewmodel import Cell, GithubVM, PrRow
from cockpit_board.widgets import common as c
from PySide6.QtWidgets import QFrame, QLabel


def cell_chip(cell: Cell) -> QLabel:
    item = c.chip(cell.text, cell.sev)
    if cell.tip:
        item.setToolTip(cell.tip)
    return item


def pr_line(row: PrRow) -> QFrame:
    frame, layout = c.inner()
    frame.setProperty("pr", row.number)
    frame.setProperty("gate", row.gate.text)
    layout.addWidget(
        c.hrow(c.label(f"#{row.number}", "mono", wrap=False), c.label(row.title, wrap=False, tip=row.url), 1,
               c.label(" · ".join(row.projects), "mono", wrap=False))
    )
    ci = [w for name, cell in row.ci for w in (c.label(name, "small", wrap=False), cell_chip(cell))]
    layout.addWidget(
        c.hrow(c.label("门禁", "q", wrap=False), cell_chip(row.gate), *ci, 1,
               c.label("安全签字", "q", wrap=False), cell_chip(row.safety),
               c.label("审计", "q", wrap=False), cell_chip(row.audit))
    )
    if row.note:
        layout.addWidget(c.label(row.note, "small"))
    return frame


def github_block(github: GithubVM, rows: list[PrRow], empty: str) -> QFrame:
    frame, layout = c.card(dashed=not github.fresh)
    frame.setProperty("github_state", github.state)
    layout.addWidget(c.hrow(c.label(github.headline, "muted", wrap=False), 1, c.label(github.as_of, "mono", wrap=False)))
    if github.main_ci:
        main = [w for name, cell in github.main_ci for w in (c.label(name, "small", wrap=False), cell_chip(cell))]
        layout.addWidget(c.hrow(c.label("main 上最近一次", "q", wrap=False), *main, 1))
    if not rows:
        layout.addWidget(c.label(empty, "muted"))
    for row in rows:
        layout.addWidget(pr_line(row))
    layout.addWidget(c.label(" · ".join(github.notes), "small"))
    return frame
