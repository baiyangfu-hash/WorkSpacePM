"""问题页：阻塞 / 风险 / 提醒三档，每条写谁动手、等了多久、依据。没有确认、屏蔽按钮。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from cockpit_board.viewmodel import SEV_LABEL, Issue, waited
from cockpit_board.widgets import common as c
from PySide6.QtWidgets import QButtonGroup, QVBoxLayout, QWidget


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
    return frame


class IssuesPage(QWidget):
    FILTERS = (("all", "全部"), ("block", "阻塞"), ("risk", "风险"), ("hint", "提醒"))

    def __init__(self, on_project: Callable[[str], None]) -> None:
        super().__init__()
        self.on_project = on_project
        self.filter = "all"
        self.issues: list[Issue] = []
        self.now: datetime | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area, self.layout_ = c.page()
        outer.addWidget(self.scroll_area)

    def set_filter(self, key: str) -> None:
        self.filter = key
        if self.now is not None:  # 还没画过就没有“现在”，等第一次 show_view
            self.show_view(self.issues, self.now)

    def show_view(self, issues: list[Issue], now: datetime) -> None:
        self.issues, self.now = issues, now
        c.clear(self.layout_)
        lay = self.layout_
        lay.addWidget(c.section("问题", "阻塞 = 不处理会延期；风险 = 要留意，还不挡路；提醒 = 排班时顺手处理。每条写明谁动手、依据是什么。"))
        counts = {key: sum(1 for i in issues if key == "all" or i.sev == key) for key, _ in self.FILTERS}
        group = QButtonGroup(self)
        group.setExclusive(True)
        buttons: list[QWidget | int] = []
        for key, text in self.FILTERS:
            item = c.button(text, "tab", f"只看{text}（{counts[key]} 条）")
            item.setCheckable(True)
            item.setChecked(key == self.filter)
            item.setProperty("filter", key)
            item.clicked.connect(lambda _checked=False, k=key: self.set_filter(k))
            group.addButton(item)
            buttons.append(item)
            buttons.append(c.label(str(counts[key]), "mono", wrap=False))
        lay.addWidget(c.hrow(*buttons, 1))
        shown = [i for i in issues if self.filter == "all" or i.sev == self.filter]
        if not shown:
            lay.addWidget(c.label("这一档没有问题。", "muted"))
        for issue in shown:
            lay.addWidget(issue_card(issue, now, self.on_project))
        lay.addWidget(
            c.label("“等了多久”从账本里进入该状态的时间算起；变更记录里没写提出日期的显示“日期待补”，不算等待。"
                    "问题不是 AI 写的，每条都来自一个机器判定。条件消失，问题自动从这页走掉。"
                    "这页不提供“确认”或“屏蔽”按钮：看板只负责让你看见。", "small")
        )
