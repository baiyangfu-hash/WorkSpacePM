"""项目经理首页（方案丙，CHG-SCPT-2026-655）：从上到下五块，只读。

1. 现在最该你办的一件（大卡）  2. 总览四个数  3. 项目和卡（每张卡一条六格工位条）
4. 机器检查灯  5. 折叠的“最近 7 天发生了什么”

首页没有任何会运行命令的按钮。真按钮只有两个，文字固定：“去「决定」页办”（只跳页）、“复制”（只进剪贴板）。
其余能点的（数、灯、卡行、项目行、折叠项）都是 widgets/common.ClickBox：只换页，或者展开收起。
`decision_card` 留给项目详情页用，首页自己不再用它。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from cockpit_board import theme
from cockpit_board.viewmodel import (
    RETIRE_NOTE,
    CardRow,
    Decision,
    Focus,
    GithubVM,
    HomeVM,
    Number,
    ProjectGroup,
    waited,
)
from cockpit_board.widgets import common as c
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

NUMBER_FILTER = {"user": "user", "lead": "lead", "old": "old"}  # 能点的三个数 → 问题页的筛选；“AI 在干”不可点
WAIT_FROM = "从卡停到这一步那天算"
NO_CARD = "这件事不对应某一张卡"
IN_THREAD = "这件事在线程里回一句话，由主执行去办"
GO_TEXT = "去「决定」页办"
GITHUB_LAMP = "github"
RIGHT_WIDTH = theme.SPACE * 34  # 卡行右边那句字留的宽度，让各行的格子条上下对齐


def decision_card(item: Decision, now: datetime, on_project: Callable[[str], None], on_copy: Callable[[str], None]) -> QFrame:
    frame, layout = c.card(item.sev)
    head = c.hrow(c.label(item.project_id, "mono", wrap=False), c.label(item.ask, "section"), 1)
    if item.example:
        c.insert_widget(head, 2, c.example_tag())
    layout.addWidget(head)
    layout.addWidget(c.label(item.why, "muted"))
    reply = c.label(item.reply, "mono", wrap=False)
    copy = c.button("复制", "ghost", "把这句话放进剪贴板；真正的回复要你自己发出去")
    copy.clicked.connect(lambda: on_copy(item.reply))
    see = c.button("看项目", "", "打开这个项目的详情")
    see.clicked.connect(lambda: on_project(item.project_id))
    where = "在 PR 页面评论这一行：" if item.link else "在线程里回一句："
    layout.addWidget(
        c.hrow(c.label(where, "small", wrap=False), reply, copy,
               c.label("依据 " + item.basis, "small", wrap=False), 1,
               c.label(waited(now, item.since), "mono", wrap=False), see)
    )
    if item.link:
        # 链接只显示文字（总控屏不起浏览器）：可以选中，或点“复制链接”再贴进浏览器
        link = c.label(item.link, "mono", wrap=False)
        link.setProperty("pr_link", item.link)
        copy_link = c.button("复制链接", "ghost", "把 PR 网址放进剪贴板，贴进浏览器打开")
        copy_link.clicked.connect(lambda: on_copy(item.link))
        layout.addWidget(c.hrow(c.label("PR 页面：", "small", wrap=False), link, 1, copy_link))
    return frame


def _wait_text(decision: Decision, now: datetime) -> str:
    text = waited(now, decision.since)
    return f"{text} · {WAIT_FROM}" if decision.kind == "mission" and decision.since is not None else text


def focus_details(focus: Focus) -> list[tuple[str, str]]:
    """“依据和编号”里的几行：卡号、变更单号、原来的依据句、要在终端办时的完整命令（只显示，不运行）。"""
    d = focus.decision
    rows = [("这件事", f"{d.ask}：{d.why}")]
    if d.mission_id:
        rows.append(("卡号", d.mission_id))
    if d.change_id:
        rows.append(("变更单号", d.change_id))
    rows.append(("依据", d.basis))
    rows.append(("“复制”放进剪贴板的那句话", d.reply))
    if d.link:
        rows.append(("PR 页面", d.link))
    if d.command:
        rows.append(("要收掉这张卡，在终端运行（这里只显示）", f"{d.command}{RETIRE_NOTE}"))
    return rows


def lamp_of_github(github: GithubVM | None) -> tuple[str, str, str]:
    """GitHub 汇总灯：（灯上的字, 语义色, 三态）。没真读到就是没检查 / 断网未知，不写数。"""
    if github is None or not github.fresh:
        state = "offline" if github is not None and github.state == "offline" else "unchecked"
        return c.STATES[state], "na", state
    red = sum(1 for row in github.rows if row.gate.sev == "block")
    text = f"开着 {len(github.rows)} 个" + (f"，门禁红 {red} 个" if red else "")
    return text, "block" if red else "ok", "number"


class HomePage(QWidget):
    def __init__(
        self,
        on_project: Callable[[str], None],
        on_copy: Callable[[str], None],
        on_page: Callable[[str], None] | None = None,
        on_issues: Callable[[str], None] | None = None,
        on_card: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_project = on_project
        self.on_copy = on_copy
        self.on_page = on_page or (lambda _key: None)  # 换到某一页
        self.on_issues = on_issues or (lambda _key: None)  # 换到问题页并带筛选
        self.on_card = on_card or (lambda _mission_id: None)  # 换到流程图页并选中这张卡
        self.folds: dict[str, bool] = {}  # 各折叠项开着没有（重画后保持）
        self.lamp_key = ""  # 点开了哪盏灯的说明
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area, self.layout_ = c.page()
        outer.addWidget(self.scroll_area)
        self.vm: HomeVM | None = None
        self.vm_now: datetime | None = None
        self.blocks: dict[int, QWidget] = {}

    # ------------------------------------------------ 小工具

    def _fold(self, key: str, title: str) -> c.Fold:
        fold = c.Fold(title, self.folds.get(key, False), key)
        fold.toggled.connect(lambda opened, k=key: self.folds.__setitem__(k, opened))
        return fold

    def _block(self, number: int, widget: QWidget) -> QWidget:
        widget.setProperty("block", number)
        self.blocks[number] = widget
        self.layout_.addWidget(widget)
        return widget

    # ------------------------------------------------ 第 1 块：现在最该你办的一件

    def _focus_block(self, vm: HomeVM, now: datetime) -> QFrame:
        focus = vm.focus
        if focus is None:
            frame, layout = c.card(dashed=True)
            if vm.ledger_ok:
                layout.addWidget(c.label("现在没有要你办的。", "muted"))
            else:  # 账本没读到：不能说“没有”
                layout.addWidget(c.state_line("unchecked", "账本这次没读到，有没有要你办的事不知道。"))
            return frame
        d = focus.decision
        frame, layout = c.card(d.sev)
        frame.setProperty("focus_kind", d.kind)
        matter = c.label(focus.matter, "section")
        head = c.hrow(c.label(d.project_id, "mono", wrap=False), c.label(focus.project_name, "muted", wrap=False), matter, 1,
                      c.label(_wait_text(d, now), "small", wrap=False), c.label(f"共 {vm.decisions_total} 件", "small", wrap=False))
        if d.example:
            c.insert_widget(head, 3, c.example_tag())
        layout.addWidget(head)
        layout.addWidget(c.label("要你定：" + focus.ask))
        if d.kind != "mission":
            layout.addWidget(c.label(NO_CARD, "small"))
        buttons: list[QWidget | int] = []
        if focus.page:
            go = c.button(GO_TEXT, "", "跳到能办这件事的那一页")
            go.clicked.connect(lambda _checked=False, key=focus.page: self.on_page(key))
            buttons.append(go)
        copy = c.button("复制", "ghost", "把回复的那句话放进剪贴板；真正的回复要你自己发出去")
        copy.clicked.connect(lambda _checked=False, text=d.reply: self.on_copy(text))
        buttons.append(copy)
        if not focus.page:
            buttons.append(c.label(IN_THREAD, "small", wrap=False))
        fold = self._fold("focus", "依据和编号")
        fold.box.addWidget(c.kv(focus_details(focus)))
        buttons += [fold.head, 1]
        layout.addWidget(c.hrow(*buttons))
        layout.addWidget(fold)
        fold.head_row.setVisible(False)  # 标题那一格已经放进按钮那一行，折叠块自己那一行不再占高度
        if vm.focus_next:
            layout.addWidget(c.label("接下来", "q", wrap=False))
            for item in vm.focus_next:
                line = c.label(f"{item.decision.project_id} · {item.matter} · {waited(now, item.decision.since)}", "muted", wrap=False)
                line.setProperty("focus_next", "true")
                layout.addWidget(line)
        return frame

    # ------------------------------------------------ 第 2 块：总览四个数

    def _number_box(self, number: Number) -> QFrame:
        target = NUMBER_FILTER.get(number.key, "")
        sev = number.sev if number.read and number.value else "na"  # 没读到、或者是 0，都不标色
        if target:
            box = c.number_box(number.key, number.label, number.text, sev, "跳到问题页，只看这一类", True)
            assert isinstance(box, c.ClickBox)
            box.activated.connect(lambda key=target: self.on_issues(key))
            return box
        tip = "、".join(number.cards) if number.cards else "停在“进行中”那一格、没有标色的卡"
        return c.number_box(number.key, number.label, number.text, sev, tip, False)

    def _numbers_block(self, vm: HomeVM) -> QWidget:
        holder, grid = c.grid(max(len(vm.numbers), 1))
        c.fill_grid(grid, [self._number_box(n) for n in vm.numbers], max(len(vm.numbers), 1))
        return holder

    # ------------------------------------------------ 第 3 块：项目和卡

    def _card_row(self, row: CardRow, index: int) -> c.ClickBox:
        title = c.quiet(row.title)
        right = c.quiet(row.right, "small")
        right.setMinimumWidth(RIGHT_WIDTH)
        strip = c.strip(row.strip.cells, row.strip.current, row.strip.text, row.strip.sev, row.strip.shape)
        items: list[QWidget | int] = [title, 1, strip, right]
        if row.example:
            items.insert(1, c.example_tag())
        box = c.click_row("cardrow", f"第 {index} 张卡", "到流程图页看这张卡走到哪一步", *items)
        box.setProperty("mission_id", row.mission_id)
        box.setProperty("strip_sev", row.strip.sev)
        box.activated.connect(lambda mission_id=row.mission_id: self.on_card(mission_id))
        return box

    def _group(self, group: ProjectGroup, start: int) -> list[QWidget]:
        head = c.click_row(
            "projectrow", f"项目 {group.project_id}", "打开这个项目的详情",
            c.quiet(group.project_id, "mono"), c.quiet(group.name, "heading"), c.quiet(f"开着 {group.open_count} 张卡", "small"), 1,
        )
        head.setProperty("project_id", group.project_id)
        head.activated.connect(lambda pid=group.project_id: self.on_project(pid))
        rows: list[QWidget] = [head]
        rows += [self._card_row(row, start + offset) for offset, row in enumerate(group.cards)]
        if group.more:
            rows.append(c.label(f"还有 {group.more} 张", "small"))
        return rows

    def _projects_block(self, vm: HomeVM) -> QFrame:
        frame, layout = c.card()
        layout.addWidget(c.hrow(c.label("项目和卡", "section"), c.label("■ 要你办 · ● 主执行要收拾 · ✓ 状态走过", "q", wrap=False), 1))
        index = 1
        for group in vm.groups:
            for widget in self._group(group, index):
                layout.addWidget(widget)
            index += len(group.cards)
        if not vm.groups:
            layout.addWidget(c.label("现在没有开着的卡。" if vm.ledger_ok else "账本这次没读到，开着哪些卡不知道。", "muted"))
        archived = c.label(
            f"另有 {vm.archived_count} 个已归档（到「全部项目」页勾选“显示已归档”可看）" if vm.archived_count else "没有已归档的项目",
            "small", wrap=False,
        )
        if not vm.ledger_ok:  # 账本没读到：哪些项目没有开着的卡也不知道，不写“其余 N 个”
            layout.addWidget(archived)
            return frame
        with_old = [(pid, name, old) for pid, name, old in vm.quiet if old]
        text = f"其余 {len(vm.quiet)} 个项目没有开着的卡"
        if with_old:
            text += f"；其中 {len(with_old)} 个留有旧账 {sum(old for _pid, _name, old in with_old)} 条"
        fold = self._fold("quiet", text)
        for pid, name, old in vm.quiet:
            fold.box.addWidget(c.label(f"{pid} {name} · " + (f"旧账 {old} 条" if old else "没有旧账"), "small"))
        c.insert_widget(fold.head_row, 1, archived)
        layout.addWidget(fold)
        return frame

    # ------------------------------------------------ 第 4 块：机器检查灯

    def _lamps_block(self, vm: HomeVM) -> QFrame:
        frame, layout = c.card()
        layout.addWidget(c.hrow(c.label("机器检查", "section"),
                                c.label(f"本次实际检查 {vm.checks_ran} / {len(vm.checks)} 项 · 空心灰圈是没检查，不是 0，更不是绿 · 点一盏灯看说明",
                                        "q", wrap=False), 1))
        lamps: list[QWidget] = []
        notes: dict[str, str] = {}
        for index, check in enumerate(vm.checks, start=1):
            box = c.lamp(check.key, check.label, check.text, check.sev, check.state, f"第 {index} 盏检查灯", "点开看这项检查的说明")
            box.activated.connect(lambda key=check.key: self._toggle_lamp(key))
            notes[check.key] = f"{check.label}：{check.note}"
            lamps.append(box)
        if vm.github is not None:
            text, sev, state = lamp_of_github(vm.github)
            box = c.lamp(GITHUB_LAMP, "GitHub 上的 PR", text, sev, state, "PR 汇总灯", "跳到「PR 与审计」页")
            box.activated.connect(lambda: self.on_page("prs"))
            lamps.append(box)
        holder, grid = c.grid(max(len(lamps), 1))
        c.fill_grid(grid, lamps, max(len(lamps), 1))
        layout.addWidget(holder)
        self.lamp_notes = notes
        self.lamp_note = c.label(notes.get(self.lamp_key, ""), "small")
        self.lamp_note.setProperty("lamp_note", "true")
        self.lamp_note.setVisible(self.lamp_key in notes)
        layout.addWidget(self.lamp_note)
        return frame

    def _toggle_lamp(self, key: str) -> None:
        self.lamp_key = "" if self.lamp_key == key else key
        self.lamp_note.setText(self.lamp_notes.get(self.lamp_key, ""))
        self.lamp_note.setVisible(bool(self.lamp_key))

    # ------------------------------------------------ 第 5 块：最近 7 天

    def _activity_block(self, vm: HomeVM) -> c.Fold:
        fold = self._fold("activity", "最近 7 天发生了什么")
        frame, inner = c.card()
        if vm.activity:
            for stamp, pid, text, example in vm.activity:
                text_label = c.label(text)
                row = c.hrow(c.label(stamp, "mono", wrap=False), c.label(pid, "mono", wrap=False), text_label)
                c.fill(row, text_label)  # 文字吃满剩余宽度；行尾不放弹簧，否则文字被挤成一窄列
                if example:
                    c.insert_widget(row, 2, c.example_tag())
                inner.addWidget(row)
        else:
            inner.addWidget(c.label("这 7 天账本和变更记录里都没有新动静。", "muted"))
        fold.box.setContentsMargins(0, 0, 0, 0)
        fold.box.addWidget(frame)
        fold.box.addWidget(c.label("只用账本和变更记录里真有的时间。" + " · ".join(vm.notes), "small"))
        fold.box.addWidget(
            c.label("“要你办”只覆盖三类：账本里等你的卡（含等你点头的范围卡、等确认的收件箱条目）、变更记录里待你定的、PR 上等你评论那一行的。"
                    "线程里的待办这里算不出，由协调者汇报。这页没有任何会运行命令的按钮：要定的事到「决定」页办，或者在线程里回一句话；"
                    "“复制”只是把那句话放进剪贴板。完整数据只在账本主机上有。", "small")
        )
        return fold

    # ------------------------------------------------ 画

    def show_view(self, vm: HomeVM, now: datetime) -> None:
        self.vm, self.vm_now = vm, now
        c.clear(self.layout_)
        self.blocks = {}
        self._block(1, self._focus_block(vm, now))
        self._block(2, self._numbers_block(vm))
        self._block(3, self._projects_block(vm))
        self._block(4, self._lamps_block(vm))
        self._block(5, self._activity_block(vm))

    def show_board(self, vm: HomeVM, now: datetime) -> None:
        self.show_view(vm, now)
