"""项目页：头 + 六个页签（概览 / 卡片 / 证据 / 变更记录 / 依赖与交付 / 规范与模板）。

除概览里“项目状态”一块外只读（CHG-SCPT-2026-654）。那一块是命令行的另一层皮：
    “归档…”/“重新激活…”/“重新检查” 只跑不带 --confirm 的预演（只查不改），输出原样摆出来；
    预演通过（退出码 0 并且有“预演（没加 --confirm）”一句）才出现“确认归档”/“确认重新激活”，点它弹确认框，里面写着整条命令；
    确认键和预演绑在同一个项目上：换项目、点“重新读取”，预演作废，确认键消失；
    本机发布版没有这条命令时按钮灰着，旁边写明原因。口令只在终端窗口里输，这一页没有任何输入框。
真正起命令的是 decision_controller（经 actions.py），这里只画、只转达。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

from cockpit_board import decisions, theme
from cockpit_board.actions import Receipt
from cockpit_board.viewmodel import PHASES, ProjectVM, change_status_text
from cockpit_board.widgets import common as c
from cockpit_board.widgets.delivery import github_block
from cockpit_board.widgets.home import decision_card
from cockpit_board.widgets.issues import issue_card
from PySide6.QtWidgets import QButtonGroup, QVBoxLayout, QWidget

TABS = (("overview", "概览"), ("board", "卡片"), ("evidence", "证据"), ("changes", "变更记录"),
        ("io", "依赖与交付"), ("recipe", "规范与模板"))


class LifecyclePort(Protocol):
    """项目详情页向 decision_controller.DecisionController 借的四样；页面自己不拼命令、不起进程。"""

    lifecycle_listeners: list[Callable[[], None]]

    def probe_lifecycle(self) -> None: ...

    def lifecycle_available(self, key: str) -> tuple[bool, str]: ...

    def dry_run(self, key: str, project_id: str, done: Callable[[Any], None]) -> None: ...

    def confirm_project(self, run: Any, title: str, on_receipt: Callable[[Receipt], None], parent: QWidget | None = None) -> Any: ...


class ProjectPage(QWidget):
    def __init__(self, on_back: Callable[[], None], on_copy: Callable[[str], None]) -> None:
        super().__init__()
        self.on_back, self.on_copy = on_back, on_copy
        self.lifecycle: LifecyclePort | None = None  # app 接线后才有；没有时“项目状态”一块只写状态，没有按钮
        self.dry_run: Any = None  # decision_controller.DryRun：最近一次预演（连同它是哪个项目的）
        self.dry_running = ""  # 正在预演的项目号；空＝没在跑
        self.lifecycle_receipt: tuple[str, Receipt] | None = None  # （项目号, 确认后那条命令的回执）
        self.tab = "overview"
        self.vm: ProjectVM | None = None
        self.now: datetime | None = None
        self.online: bool | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area, self.layout_ = c.page()
        outer.addWidget(self.scroll_area)

    # ------------------------------------------------ 项目状态：归档、重新激活

    def set_lifecycle(self, lifecycle: LifecyclePort) -> None:
        self.lifecycle = lifecycle
        lifecycle.lifecycle_listeners.append(self._redraw)

    def _redraw(self) -> None:
        if self.vm is not None and self.now is not None:
            self.show_view(self.vm, self.now, self.online)

    def void_dry_run(self) -> None:
        """点“重新读取”时调：这份预演作废，确认键消失，要重新点“归档…”。"""
        self.dry_run, self.dry_running = None, ""
        self._redraw()

    def start_dry_run(self, key: str) -> None:
        if self.lifecycle is None or self.vm is None:
            return
        project_id = self.vm.card.project_id
        self.dry_run, self.dry_running, self.lifecycle_receipt = None, project_id, None
        self._redraw()
        self.lifecycle.dry_run(key, project_id, self._dry_run_done)

    def _dry_run_done(self, run: Any) -> None:
        if run.project_id != self.dry_running:  # 预演跑着的时候换了项目或点了“重新读取”：这份结果不算
            return
        self.dry_running = ""
        self.dry_run = run
        self._redraw()

    def confirm(self) -> None:
        """点“确认归档”/“确认重新激活”：项目号取预演记下的那个。一次预演只确认一次。"""
        run = self.dry_run
        if self.lifecycle is None or run is None or not run.passed:
            return
        title = f"{run.project_id} {self.vm.card.name}" if self.vm is not None and self.vm.card.project_id == run.project_id else run.project_id
        project_id = str(run.project_id)

        def confirmed(receipt: Receipt) -> None:
            self._confirmed(project_id, receipt)

        self.lifecycle.confirm_project(run, title, confirmed, self)

    def _confirmed(self, project_id: str, receipt: Receipt) -> None:
        self.dry_run = None  # 命令已经起了：这份预演用掉了
        self.lifecycle_receipt = (project_id, receipt)
        self._redraw()

    def _lifecycle_block(self, vm: ProjectVM) -> None:
        card = vm.card
        frame, inner = c.card()
        frame.setProperty("role", "lifecycle")
        inner.addWidget(c.hrow(c.label("项目状态", "section"), c.chip(card.status_label, "na" if card.archived else ""), 1))
        if not card.registered:
            inner.addWidget(c.label("这个项目还没登记，没有状态；登记在“工具”页的“项目”页签。", "muted"))
        elif self.lifecycle is not None:
            key = "reactivate" if card.archived else "archive"
            entry = decisions.LIFECYCLES[key]
            available, reason = self.lifecycle.lifecycle_available(key)
            run = self.dry_run if self.dry_run is not None and self.dry_run.project_id == card.project_id else None
            command = decisions.shown_command([*decisions.READ_ONLY_COMMANDS[entry.dry_run], card.project_id])
            tip = f"先预演：{command}（不带 --confirm），只查不改"
            buttons: list[QWidget | int] = []
            if run is None:
                first = c.button(entry.dry_label, "", tip, enabled=available and not self.dry_running)
                first.clicked.connect(lambda _checked=False, k=key: self.start_dry_run(k))
                buttons.append(first)
            else:
                if run.passed and available:
                    confirm = c.button(decisions.BY_KEY[entry.decision].label, "", "弹出确认框，里面写着整条命令；确认后才运行")
                    confirm.clicked.connect(lambda _checked=False: self.confirm())
                    buttons.append(confirm)
                again = c.button(decisions.RECHECK_LABEL, "", f"再跑一遍预演：{command}，只查不改", enabled=available)
                again.clicked.connect(lambda _checked=False, k=key: self.start_dry_run(k))
                buttons.append(again)
            inner.addWidget(c.hrow(*buttons, 1))
            if not available:
                inner.addWidget(c.label(reason, "muted"))
            if self.dry_running:
                inner.addWidget(c.label("正在预演……（只查不改）", "muted"))
            if run is not None:
                inner.addWidget(c.label(f"{run.receipt.command}\n退出码：{run.receipt.rc_text}", "mono"))
                output = c.label(run.receipt.output or "（命令没有输出）", "mono")
                output.setProperty("role", "dry_run_output")
                inner.addWidget(output)
                if not run.passed:
                    inner.addWidget(c.label("预演没通过，所以没有确认键；照上面的“怎么办”处理后点“重新检查”。", "muted"))
        if self.lifecycle_receipt is not None and self.lifecycle_receipt[0] == card.project_id:
            receipt = self.lifecycle_receipt[1]
            inner.addWidget(c.label(f"{receipt.action}：{receipt.command}\n退出码：{receipt.rc_text}", "mono"))
            result = c.label(receipt.output or "（命令没有输出）", "mono")
            result.setProperty("role", "lifecycle_receipt")
            inner.addWidget(result)
        self.layout_.addWidget(frame)

    def set_tab(self, key: str) -> None:
        self.tab = key
        if self.vm is not None and self.now is not None:
            self.show_view(self.vm, self.now, self.online)

    def show_view(self, vm: ProjectVM, now: datetime, online: bool | None) -> None:
        if self.vm is not None and self.vm.card.project_id != vm.card.project_id:
            # 换到另一个项目：上一个项目的预演和回执都不带过来，确认键消失
            self.dry_run, self.dry_running, self.lifecycle_receipt = None, "", None
        self.vm, self.now, self.online = vm, now, online
        c.clear(self.layout_)
        lay, card = self.layout_, vm.card
        back = c.button("‹ 今天", "ghost", "回首页")
        back.clicked.connect(self.on_back)
        lay.addWidget(c.hrow(back, c.label(card.project_id, "mono", wrap=False), c.label(card.name, "title"),
                             c.chip(card.health_label, theme.HEALTH_SEV.get(card.health, "na")), 1))
        lay.addWidget(c.hrow(c.label(card.milestone, "muted", wrap=False), c.label("到期 " + card.due_text, "muted", wrap=False),
                             c.label("数据覆盖 " + card.coverage.text(), "muted", wrap=False),
                             c.label("最后动静 " + card.last_text, "muted", wrap=False), 1))
        lay.addWidget(c.label("阶段：" + " › ".join(PHASES) + "（只列阶段名；当前在哪个阶段没有从任何文件读，也不自动推算）", "small"))
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

    def _overview(self, vm: ProjectVM, now: datetime) -> None:
        lay = self.layout_
        if vm.card.decisions:
            lay.addWidget(c.section("要你出手"))
            for item in vm.card.decisions:
                lay.addWidget(decision_card(item, now, lambda _pid: None, self.on_copy))
        frame, inner = c.card()
        inner.addWidget(c.label("现在在干", "section"))
        inner.addWidget(c.kv([("卡", vm.card.now_card), ("谁", vm.card.now_who), ("最后断点", vm.card.now_step or "—")]))
        lay.addWidget(frame)
        self._lifecycle_block(vm)
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
            text_label = c.label(text)
            row = c.hrow(c.label(stamp, "mono", wrap=False), text_label, c.label(who, "small", wrap=False))
            c.fill(row, text_label)  # 文字吃满剩余宽度；行里不放弹簧，否则文字被挤成一窄列
            if example:
                c.insert_widget(row, 2, c.example_tag())
            inner.addWidget(row)
        lay.addWidget(frame)

    def _board(self, vm: ProjectVM, _now: datetime) -> None:
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
                    c.insert_widget(head, 1, c.example_tag())
                box_layout.addWidget(head)
                box_layout.addWidget(c.label(title))
                box_layout.addWidget(c.label(meta, "small"))
                inner.addWidget(box)
            inner.addStretch(1)
            widgets.append(frame)
        c.fill_grid(grid, widgets, len(vm.columns))
        self.layout_.addWidget(holder)
        self.layout_.addWidget(c.label("四栏照挂起设计稿：在干 = ACTIVE；等你 = 草稿 / 等批准 / 等验收 / 受阻；已关 = 近 14 天验收或收口的。", "small"))

    def _evidence(self, vm: ProjectVM, _now: datetime) -> None:
        frame, inner = c.card()
        inner.addWidget(c.label("机器检查结果", "section"))
        inner.addWidget(c.label("这页回答“AI 说做完了，到底过没过”。每一行三态：过 / 没过 / 没检查。没检查的灰色，不算过。", "small"))
        for row in vm.evidence:
            line = c.hrow(c.mark(row.state), c.label(row.title, "", wrap=False), c.label(row.detail, "small"), 1,
                          c.label("没检查" if row.state == "na" else "", "small", wrap=False))
            line.setProperty("evidence", row.state)
            inner.addWidget(line)
        self.layout_.addWidget(frame)

    def _changes(self, vm: ProjectVM, _now: datetime) -> None:
        frame, inner = c.card()
        inner.addWidget(c.hrow(c.label("编号", "q", wrap=False), c.label("日期", "q", wrap=False), c.label("类型", "q", wrap=False),
                               c.label("改了什么", "q"), c.label("状态", "q", wrap=False)))
        if not vm.changes:
            inner.addWidget(c.label("无", "muted"))
        for row in vm.changes:
            status = c.chip(row.status, "hint") if row.status.startswith("待批") else c.label(change_status_text(row) or "—", "", wrap=False)
            inner.addWidget(c.hrow(c.label(row.change_id, "mono", wrap=False), c.label(row.date, "mono", wrap=False),
                                   c.label(row.kind, "", wrap=False), c.label(row.what), 1, status))
        if vm.changes_more:
            inner.addWidget(c.label(vm.changes_more, "muted"))
        self.layout_.addWidget(frame)
        self.layout_.addWidget(c.label("BC = 业务变更（客户改需求、领导砍需求、参数变化），CARD = 实施卡，CHG = 收口变更单。三种合一张表。"
                                       "还没收口的变更都在最上面；已收口的从新到旧只列最近 30 条；实施卡没有日期，列在最后。", "small"))

    def _io(self, vm: ProjectVM, _now: datetime) -> None:
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

    def _recipe(self, vm: ProjectVM, _now: datetime) -> None:
        frame, inner = c.card()
        inner.addWidget(c.label("这个项目照哪份规范和模板干活", "section"))
        inner.addWidget(c.kv(vm.recipe))
        self.layout_.addWidget(frame)
