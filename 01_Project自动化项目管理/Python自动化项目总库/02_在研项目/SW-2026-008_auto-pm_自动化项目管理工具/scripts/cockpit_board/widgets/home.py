"""项目经理首页：要你出手 → 六项机器检查 → 要留意的项目（其余折叠）→ 最近发生了什么。只读。"""

from __future__ import annotations

from collections.abc import Callable

from cockpit_board import theme
from cockpit_board.viewmodel import Check, Decision, HomeVM, ProjectCard, waited
from cockpit_board.widgets import common as c
from cockpit_board.widgets.delivery import github_block
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

CARD_COLUMNS = 3


def decision_card(item: Decision, now, on_project: Callable[[str], None], on_copy: Callable[[str], None]) -> QFrame:  # noqa: ANN001
    frame, layout = c.card(item.sev)
    head = c.hrow(c.label(item.project_id, "mono", wrap=False), c.label(item.ask, "section"), 1)
    if item.example:
        head.layout().insertWidget(2, c.example_tag())
    layout.addWidget(head)
    layout.addWidget(c.label(item.why, "muted"))
    reply = c.label(item.reply, "mono", wrap=False)
    copy = c.button("复制", "ghost", "把这句话放进剪贴板；真正的回复在线程里发")
    copy.clicked.connect(lambda: on_copy(item.reply))
    see = c.button("看项目", "", "打开这个项目的详情")
    see.clicked.connect(lambda: on_project(item.project_id))
    layout.addWidget(
        c.hrow(c.label("在线程里回一句：", "small", wrap=False), reply, copy,
               c.label("依据 " + item.basis, "small", wrap=False), 1,
               c.label(waited(now, item.since), "mono", wrap=False), see)
    )
    return frame


def check_tile(check: Check) -> QFrame:
    frame, layout = c.card(dashed=check.state != "number")
    frame.setProperty("check_key", check.key)
    layout.addWidget(c.label(check.label, "muted", wrap=False))
    value = c.label(check.text, "check", wrap=False)
    value.setProperty("sev", check.sev)
    value.setProperty("state", check.state)
    font = value.font()
    font.setPointSize(theme.FONT_SIZE_TITLE_PT + 3)
    font.setBold(True)
    value.setFont(font)
    layout.addWidget(value)
    layout.addWidget(c.label(check.note, "small"))
    return frame


def project_tile(card: ProjectCard, on_project: Callable[[str], None]) -> QFrame:
    frame, layout = c.card(dashed=card.health == "off")
    frame.setProperty("project_id", card.project_id)
    frame.setProperty("health", card.health)
    frame.setCursor(Qt.CursorShape.PointingHandCursor)
    frame.mouseReleaseEvent = lambda _event: on_project(card.project_id)  # type: ignore[method-assign]
    head = c.hrow(
        c.label(card.project_id + ("  工具" if card.tool else ""), "mono", wrap=False), 1,
        c.chip(card.health_label, "ok" if card.health == "ok" else card.health if card.health in ("risk", "block") else "na"),
    )
    layout.addWidget(head)
    layout.addWidget(c.label(card.name, "section"))
    if card.registered:
        layout.addWidget(c.hrow(c.label(card.milestone, "muted", wrap=False), 1, c.label(card.due_text, "mono", wrap=False)))
        layout.addWidget(c.label("数据覆盖 " + card.coverage.text(), "small", wrap=False))
    layout.addWidget(c.label("现在在干", "q", wrap=False))
    layout.addWidget(c.label(f"{card.now_card} · {card.now_who}" if card.now_who != "—" else card.now_card))
    chips = [c.chip(i.title, i.sev) for i in card.issues[:2]]
    if len(card.issues) > 2:
        chips.append(c.chip(f"+{len(card.issues) - 2}"))
    if not card.issues:
        chips.append(c.chip("没有问题", "ok"))
    layout.addWidget(c.hrow(*chips, 1, c.label("最后动静 " + card.last_text, "small", wrap=False)))
    return frame


class HomePage(QWidget):
    def __init__(self, on_project: Callable[[str], None], on_copy: Callable[[str], None]) -> None:
        super().__init__()
        self.on_project = on_project
        self.on_copy = on_copy
        self.fold_open = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll, self.layout_ = c.page()
        outer.addWidget(self.scroll)
        self.vm: HomeVM | None = None

    def render(self, vm: HomeVM, now) -> None:  # noqa: ANN001
        self.vm = vm
        c.clear(self.layout_)
        lay = self.layout_
        total = vm.decisions_total
        lay.addWidget(c.section("要你出手", f"{total} 件 · 严重的在前，等得久的在前 · 每件给一句回复"))
        if vm.decisions:
            for item in vm.decisions:
                lay.addWidget(decision_card(item, now, self.on_project, self.on_copy))
            if total > len(vm.decisions):
                lay.addWidget(c.label(f"还有 {total - len(vm.decisions)} 件排在后面，前面定完再给你。", "small"))
        else:
            frame, inner = c.card(dashed=True)
            inner.addWidget(c.label("账本、变更记录、PR 签字里没有要你定的事。", "muted"))
            lay.addWidget(frame)
        lay.addWidget(
            c.label(
                "只覆盖三类：账本里等你的卡、变更记录里待批的、PR 上等你签字的。"
                "线程里的待办（回“合并”、确认 .trae/、答问）这里算不出，由协调者汇报。",
                "small",
            )
        )

        lay.addWidget(c.section("AI 有没有越界、有没有谎报",
                                f"六项机器检查 · 本次实际执行 {vm.checks_ran} / {len(vm.checks)} · 没检查的灰色，不是 0，更不是绿"))
        holder, grid = c.grid(CARD_COLUMNS)
        c.fill_grid(grid, [check_tile(k) for k in vm.checks], CARD_COLUMNS)
        lay.addWidget(holder)

        if vm.github is not None:
            lay.addWidget(c.section("交出去的东西", "GitHub 上开着的 PR · 门禁 · 安全签字 · 审计 · 没读到就写“未知”"))
            lay.addWidget(github_block(vm.github, vm.github.rows, "没有开着的 PR。"))

        lay.addWidget(c.section("要留意的项目", f"{len(vm.hot)} 个受阻或有风险 · 点进去看详情"))
        if vm.hot:
            holder, grid = c.grid(CARD_COLUMNS)
            c.fill_grid(grid, [project_tile(p, self.on_project) for p in vm.hot], CARD_COLUMNS)
            lay.addWidget(holder)
        else:
            lay.addWidget(c.label("没有受阻或有风险的项目。", "muted"))
        fold = c.button("收起" if self.fold_open else "展开", "ghost",
                        f"另有 {len(vm.rest)} 个正常、无数据或未接入的项目")
        fold.setObjectName("fold")
        fold.clicked.connect(self._toggle)
        lay.addWidget(c.hrow(c.label(f"另有 {len(vm.rest)} 个正常、无数据或未接入的项目", "muted", wrap=False), fold, 1))
        self.rest_holder, grid = c.grid(CARD_COLUMNS)
        c.fill_grid(grid, [project_tile(p, self.on_project) for p in vm.rest], CARD_COLUMNS)
        self.rest_holder.setVisible(self.fold_open)
        lay.addWidget(self.rest_holder)

        lay.addWidget(c.section("最近发生了什么", "最近 7 天 · 只用账本和变更记录里真有的时间"))
        frame, inner = c.card()
        if vm.activity:
            for stamp, pid, text, example in vm.activity:
                row = c.hrow(c.label(stamp, "mono", wrap=False), c.label(pid, "mono", wrap=False), c.label(text), 1)
                if example:
                    row.layout().insertWidget(3, c.example_tag())
                inner.addWidget(row)
        else:
            inner.addWidget(c.label("这 7 天账本和变更记录里都没有新动静。", "muted"))
        lay.addWidget(frame)
        lay.addWidget(c.section("谁在干活", "预留 · 现在没有数据源（Trae 和云端线程不写账本）"))
        frame, inner = c.card(dashed=True)
        inner.addWidget(c.label("主执行 · 云端线程 · Trae 工位 · 虚拟机：下一版接入，现在不显示任何数。", "muted"))
        lay.addWidget(frame)
        lay.addWidget(c.label(" · ".join(vm.notes), "small"))
        lay.addWidget(
            c.label("这页没有任何执行按钮。要定的事你在线程里回一句话，由主执行去办；"
                    "“复制”只是把那句话放进剪贴板。完整数据只在账本主机上有。", "small")
        )

    def _toggle(self) -> None:
        self.fold_open = not self.fold_open
        if self.vm is not None:
            self.render(self.vm, self.vm_now)

    def show_board(self, vm: HomeVM, now) -> None:  # noqa: ANN001
        self.vm_now = now
        self.render(vm, now)
