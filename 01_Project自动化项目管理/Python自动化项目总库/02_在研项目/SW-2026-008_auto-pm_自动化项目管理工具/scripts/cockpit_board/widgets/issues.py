"""问题页：阻塞 / 风险 / 提醒三档，每条写谁动手、等了多久、依据。没有确认、屏蔽按钮。

两排筛选（CHG-SCPT-2026-655）：严重度（全部 / 阻塞 / 风险 / 提醒）和谁来办（全部 / 要你办 / AI 那边要收拾）；
旧账（项目下已没有开着的卡时留下的）默认不列，勾“显示旧账”才列。首页的数点过来时由 set_view 设好筛选。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from cockpit_board.viewmodel import OLD_BASIS, OWNER_LEAD, OWNER_USER, SEV_LABEL, Issue, waited
from cockpit_board.widgets import common as c
from PySide6.QtWidgets import QButtonGroup, QCheckBox, QVBoxLayout, QWidget


def issue_card(issue: Issue, now: datetime, on_project: Callable[[str], None] | None) -> QWidget:
    frame, layout = c.card(issue.sev)
    frame.setProperty("sev", issue.sev)
    head = c.hrow(c.chip(SEV_LABEL[issue.sev], issue.sev), c.label(issue.project_id, "mono", wrap=False),
                  c.label(issue.title, "section"), 1)
    if issue.example:
        c.insert_widget(head, 3, c.example_tag())
    layout.addWidget(head)
    layout.addWidget(c.label(issue.detail, "muted"))
    foot: list[QWidget | int] = [c.label("谁动手：" + issue.who, "small", wrap=False), c.label(waited(now, issue.since), "small", wrap=False),
            c.label("依据：" + issue.basis, "small", wrap=False), 1]
    if on_project is not None:
        see = c.button("看项目", "", "打开这个项目")
        see.clicked.connect(lambda: on_project(issue.project_id))
        foot.append(see)
    layout.addWidget(c.hrow(*foot))
    if issue.ref:  # 内部编号不进说明句，留在卡的最下面查（CHG-SCPT-2026-653）
        layout.addWidget(c.label("编号：" + issue.ref, "small"))
    return frame


class IssuesPage(QWidget):
    FILTERS = (("all", "全部"), ("block", "阻塞"), ("risk", "风险"), ("hint", "提醒"))
    WHO = (("all", "全部"), ("user", "要你办"), ("lead", "AI 那边要收拾"))
    OWNER_OF = {"user": OWNER_USER, "lead": OWNER_LEAD}
    OLD_MODES = ("hide", "show", "only")  # 旧账：不列（默认）/ 一起列 / 只列旧账（首页“旧账”那个数点过来）

    def __init__(self, on_project: Callable[[str], None]) -> None:
        super().__init__()
        self.on_project = on_project
        self.filter = "all"
        self.who = "all"
        self.old = "hide"
        self.issues: list[Issue] = []
        self.now: datetime | None = None
        self.notes: tuple[str, ...] = ()
        self.user_total: int | None = None  # 首页“要你办”的总件数；没给就不写那一行
        self.user_elsewhere = 0  # 其中在这页没有对应行的件数（PR 上等你签的、老后台补的）
        self.shown: list[Issue] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area, self.layout_ = c.page()
        outer.addWidget(self.scroll_area)

    def _redraw(self) -> None:
        if self.now is not None:  # 还没画过就没有“现在”，等第一次 show_view
            self.show_view(self.issues, self.now, self.notes, self.user_total, self.user_elsewhere)

    def set_filter(self, key: str) -> None:
        self.filter = key
        self._redraw()

    def set_who(self, key: str) -> None:
        self.who = key
        self._redraw()

    def set_old(self, mode: str) -> None:
        if mode not in self.OLD_MODES:
            raise ValueError(f"set_old: 不认识的旧账显示方式 {mode!r}")
        self.old = mode
        self._redraw()

    def set_view(self, key: str) -> None:
        """从外面设筛选（首页的数点过来）：user 要你办 / lead AI 那边要收拾 / old 只看旧账。严重度回到“全部”。"""
        if key not in ("user", "lead", "old"):
            raise ValueError(f"set_view: 不认识的筛选 {key!r}")
        self.filter = "all"
        self.who = "all" if key == "old" else key
        self.old = "only" if key == "old" else "hide"
        self._redraw()

    def _base(self, issues: list[Issue]) -> list[Issue]:
        """过了“谁来办”和“旧账”两道筛选的问题；严重度那一排的条数按它数。"""
        return [i for i in self._aged(issues) if self.who == "all" or i.owner == self.OWNER_OF[self.who]]

    def _aged(self, issues: list[Issue]) -> list[Issue]:
        """只过“旧账”这一道：不列旧账 / 一起列 / 只列旧账。"""
        if self.old == "show":
            return list(issues)
        return [i for i in issues if (i.basis == OLD_BASIS) == (self.old == "only")]

    def _tabs(self, items: Sequence[tuple[str, str]], current: str, counts: dict[str, int], pick: Callable[[str], None],
              prop: str) -> list[QWidget | int]:
        group = QButtonGroup(self)
        group.setExclusive(True)
        buttons: list[QWidget | int] = []
        for key, text in items:
            item = c.button(text, "tab", f"只看{text}（{counts[key]} 条）")
            item.setCheckable(True)
            item.setChecked(key == current)
            item.setProperty(prop, key)
            item.clicked.connect(lambda _checked=False, k=key: pick(k))
            group.addButton(item)
            buttons.append(item)
            buttons.append(c.label(str(counts[key]), "mono", wrap=False))
        return buttons

    def show_view(self, issues: list[Issue], now: datetime, notes: Sequence[str] = (), user_total: int | None = None,
                  user_elsewhere: int = 0) -> None:
        self.issues, self.now, self.notes = issues, now, tuple(notes)
        self.user_total, self.user_elsewhere = user_total, user_elsewhere
        c.clear(self.layout_)
        lay = self.layout_
        lay.addWidget(c.section("问题", "阻塞 = 不处理会延期；风险 = 要留意，还不挡路；提醒 = 排班时顺手处理。每条写明谁动手、依据是什么。"))
        for note in self.notes:  # 哪一类没检查、条数不含它：放在计数前面，空白不能被当成“没有”
            lay.addWidget(c.label("没检查：" + note, "small"))
        base = self._base(issues)
        counts = {key: sum(1 for i in base if key == "all" or i.sev == key) for key, _ in self.FILTERS}
        lay.addWidget(c.hrow(*self._tabs(self.FILTERS, self.filter, counts, self.set_filter, "filter"), 1))
        aged = self._aged(issues)
        who_counts = {key: sum(1 for i in aged if key == "all" or i.owner == self.OWNER_OF[key]) for key, _ in self.WHO}
        old_total = sum(1 for i in issues if i.basis == OLD_BASIS)
        old_box = QCheckBox(f"显示旧账（{old_total} 条）")
        old_box.setObjectName("show_old")
        old_box.setToolTip("旧账＝项目下已没有开着的卡时，账本一致性检查留下的问题；默认不列")
        old_box.setChecked(self.old != "hide")
        old_box.toggled.connect(lambda checked: self.set_old("show" if checked else "hide"))
        lay.addWidget(c.hrow(c.label("谁来办", "muted", wrap=False), *self._tabs(self.WHO, self.who, who_counts, self.set_who, "who"),
                             old_box, 1))
        if self.old == "only":
            lay.addWidget(c.label("现在只列旧账。去掉“显示旧账”的勾回到平常的样子。", "small"))
        shown = [i for i in base if self.filter == "all" or i.sev == self.filter]
        self.shown = shown
        if self.who == "user" and self.user_total is not None:
            text = f"要你办共 {self.user_total} 件：这页列 {len(base)} 条"
            if self.user_elsewhere:
                text += f"；另有 {self.user_elsewhere} 件是 PR 上等你签的、老后台补的，在「要你出手」页和「PR 与审计」页"
            line = c.label(text, "small")
            line.setProperty("user_line", "true")
            lay.addWidget(line)
        if not shown:
            lay.addWidget(c.label("这一档没有问题。", "muted"))
        for issue in shown:
            lay.addWidget(issue_card(issue, now, self.on_project))
        lay.addWidget(
            c.label("“等了多久”从账本里进入该状态的时间算起；变更记录里没写提出日期的显示“日期待补”，不算等待。"
                    "问题不是 AI 写的，每条都来自一个机器判定。条件消失，问题自动从这页走掉。"
                    "这页不提供“确认”或“屏蔽”按钮：看板只负责让你看见。", "small")
        )
