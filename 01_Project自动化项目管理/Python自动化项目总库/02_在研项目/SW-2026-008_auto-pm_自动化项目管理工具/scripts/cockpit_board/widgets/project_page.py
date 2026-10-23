"""项目页：头 + 六个页签（概览 / 卡片 / 证据 / 变更记录 / 依赖与交付 / 规范与模板）。只读。"""

from __future__ import annotations

from collections.abc import Callable

from cockpit_board.viewmodel import PHASES, ProjectVM
from cockpit_board.widgets import common as c
from cockpit_board.widgets.delivery import github_block
from cockpit_board.widgets.home import decision_card
from cockpit_board.widgets.issues import issue_card
from PySide6.QtWidgets import QButtonGroup, QVBoxLayout, QWidget

TABS = (("overview", "概览"), ("board", "卡片"), ("evidence", "证据"), ("changes", "变更记录"),
        ("io", "依赖与交付"), ("recipe", "规范与模板"))


class ProjectPage(QWidget):
    def __init__(self, on_back: Callable[[], None], on_copy: Callable[[str], None]) -> None:
        super().__init__()
        self.on_back, self.on_copy = on_back, on_copy
        self.tab = "overview"
        self.vm: ProjectVM | None = None
        self.now = None
        self.online: bool | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll, self.layout_ = c.page()
        outer.addWidget(self.scroll)

    def set_tab(self, key: str) -> None:
        self.tab = key
        if self.vm is not None:
            self.render(self.vm, self.now, self.online)

    def render(self, vm: ProjectVM, now, online: bool | None) -> None:  # noqa: ANN001
        self.vm, self.now, self.online = vm, now, online
        c.clear(self.layout_)
        lay, card = self.layout_, vm.card
        back = c.button("‹ 今天", "ghost", "回首页")
        back.clicked.connect(self.on_back)
        lay.addWidget(c.hrow(back, c.label(card.project_id, "mono", wrap=False), c.label(card.name, "title"),
                             c.chip(card.health_label, card.health if card.health in ("ok", "risk", "block") else "na"), 1))
        lay.addWidget(c.hrow(c.label(card.milestone, "muted", wrap=False), c.label("到期 " + card.due_text, "muted", wrap=False),
                             c.label("数据覆盖 " + card.coverage.text(), "muted", wrap=False),
                             c.label("最后动静 " + card.last_text, "muted", wrap=False), 1))
        lay.addWidget(c.label("阶段：" + " › ".join(PHASES) + "（按 PM_SESSION 里人填的字段显示，v1 不自动推算）", "small"))
        group = QButtonGroup(self)
        buttons = []
        for key, text in TABS:
            item = c.button(text, "tab", text)
            item.setCheckable(True)
            item.setChecked(key == self.tab)
            item.clicked.connect(lambda _checked=False, k=key: self.set_tab(k))
            group.addButton(item)
            buttons.append(item)
        lay.addWidget(c.hrow(*buttons, 1))
        getattr(self, "_" + self.tab)(vm, now)

    def _overview(self, vm: ProjectVM, now) -> None:  # noqa: ANN001
        lay = self.layout_
        if vm.card.decisions:
            lay.addWidget(c.section("要你出手"))
            for item in vm.card.decisions:
                lay.addWidget(decision_card(item, now, lambda _pid: None, self.on_copy))
        frame, inner = c.card()
        inner.addWidget(c.label("现在在干", "section"))
        inner.addWidget(c.kv([("卡", vm.card.now_card), ("谁", vm.card.now_who), ("最后断点", vm.card.now_step or "—")]))
        lay.addWidget(frame)
        lay.addWidget(c.section(f"问题（{len(vm.card.issues)}）"))
        if not vm.card.issues:
            lay.addWidget(c.label("没有问题", "muted"))
        for issue in vm.card.issues:
            lay.addWidget(issue_card(issue, now, None))
        lay.addWidget(c.section("最近发生了什么"))
        frame, inner = c.card()
        if not vm.activity:
            inner.addWidget(c.label("无", "muted"))
        for stamp, text, who, example in vm.activity:
            row = c.hrow(c.label(stamp, "mono", wrap=False), c.label(text), c.label(who, "small", wrap=False), 1)
            if example:
                row.layout().insertWidget(2, c.example_tag())
            inner.addWidget(row)
        lay.addWidget(frame)

    def _board(self, vm: ProjectVM, _now) -> None:  # noqa: ANN001
        holder, grid = c.grid(len(vm.columns))
        widgets = []
        for column in vm.columns:
            frame, inner = c.inner()
            frame.setProperty("column", column.name)
            inner.addWidget(c.hrow(c.label(column.name, "section", wrap=False), 1, c.label(str(len(column.cards)), "mono", wrap=False)))
            if column.note:
                inner.addWidget(c.label(column.note, "small"))
            if not column.cards and not column.note:
                inner.addWidget(c.label("—", "small"))
            for mission_id, title, meta, example in column.cards:
                box, box_layout = c.card()
                head = c.hrow(c.label(mission_id, "mono", wrap=False), 1)
                if example:
                    head.layout().insertWidget(1, c.example_tag())
                box_layout.addWidget(head)
                box_layout.addWidget(c.label(title))
                box_layout.addWidget(c.label(meta, "small"))
                inner.addWidget(box)
            inner.addStretch(1)
            widgets.append(frame)
        c.fill_grid(grid, widgets, len(vm.columns))
        self.layout_.addWidget(holder)
        self.layout_.addWidget(c.label("四栏照挂起设计稿：在干 = ACTIVE；等你 = 草稿 / 待批 / 待验收 / 卡住；已关 = 近 14 天验收或收口的。", "small"))

    def _evidence(self, vm: ProjectVM, _now) -> None:  # noqa: ANN001
        frame, inner = c.card()
        inner.addWidget(c.label("机器检查结果", "section"))
        inner.addWidget(c.label("这页回答“AI 说做完了，到底过没过”。每一行三态：过 / 没过 / 没检查。没检查的灰色，不算过。", "small"))
        for row in vm.evidence:
            line = c.hrow(c.mark(row.state), c.label(row.title, "", wrap=False), c.label(row.detail, "small"), 1,
                          c.label("没检查" if row.state == "na" else "", "small", wrap=False))
            line.setProperty("evidence", row.state)
            inner.addWidget(line)
        self.layout_.addWidget(frame)

    def _changes(self, vm: ProjectVM, _now) -> None:  # noqa: ANN001
        frame, inner = c.card()
        inner.addWidget(c.hrow(c.label("编号", "q", wrap=False), c.label("日期", "q", wrap=False), c.label("类型", "q", wrap=False),
                               c.label("改了什么", "q"), c.label("状态", "q", wrap=False)))
        if not vm.changes:
            inner.addWidget(c.label("无", "muted"))
        for row in vm.changes:
            status = c.chip(row.status, "hint") if row.status.startswith("待批") else c.label(row.status or "—", "", wrap=False)
            inner.addWidget(c.hrow(c.label(row.change_id, "mono", wrap=False), c.label(row.date, "mono", wrap=False),
                                   c.label(row.kind, "", wrap=False), c.label(row.what), 1, status))
        self.layout_.addWidget(frame)
        self.layout_.addWidget(c.label("BC = 业务变更（客户改需求、领导砍需求、参数变化），CARD = 实施卡，CHG = 收口变更单。三种合一张表。", "small"))

    def _io(self, vm: ProjectVM, _now) -> None:  # noqa: ANN001
        frame, inner = c.card()
        inner.addWidget(c.label("它在等谁", "section"))
        inner.addWidget(c.label("依赖栏来自计划防呆七栏（PR #36 合并后才有数据）；现在没有。", "muted"))
        self.layout_.addWidget(frame)
        self.layout_.addWidget(c.section("交出去的东西（PR · 门禁 · 安全签字 · 审计）"))
        if vm.github is None:
            frame, inner = c.card(dashed=True)
            inner.addWidget(c.label("没开 GitHub 采集：PR、门禁、安全签字都没检查。", "muted"))
            self.layout_.addWidget(frame)
        else:
            self.layout_.addWidget(github_block(vm.github, vm.prs, "没有改到这个项目的开着的 PR。"))

    def _recipe(self, vm: ProjectVM, _now) -> None:  # noqa: ANN001
        frame, inner = c.card()
        inner.addWidget(c.label("这个项目照哪份规范和模板干活", "section"))
        inner.addWidget(c.kv(vm.recipe))
        self.layout_.addWidget(frame)
