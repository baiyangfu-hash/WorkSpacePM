"""工程工位：身份条、错误横条、接着干、人工路线六步、安全区自查、回来要补记、控制台抽屉。

按钮只做本机的事；写文件只有“写入 BC 行”（用户 10-22 批准，带预览）；批准 / 开工灰到缺口⑨合并。
真正起子进程、写文件的代码在 actions.py，这里只发信号。
"""

from __future__ import annotations

from collections.abc import Callable

from cockpit_board import theme
from cockpit_board.actions import BC_REQUIRED, Receipt
from cockpit_board.viewmodel import StationVM, Step
from cockpit_board.widgets import common as c
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

SAFETY_CHECKLIST = (
    "急停、安全门、光栅、联锁、安全继电器、双手启动的逻辑，改了先 PLCSIM / InoProShop 仿真",
    "没有 OR TRUE 一类旁路；安全点没有漏接",
    "下载前校验码和上次上载记录对得上",
    "有网后 PR 上写“安全签字 + 提交号”，再合并",
)

# 记 BC 行时要你填的四栏（输入框里的灰字只是提示，不会写进文件）
BC_HINTS = {
    "类型": "需求 / 硬件 / 参数 / 工艺",
    "改了什么": "原来 → 改成，例如：急停复位 → 加 2 s 延时",
    "为什么": "谁提的、什么原因",
    "影响": "要改的程序、图纸、参数；涉及安全区写“安全区，待仿真 + 签字”",
}


def pre(text: str) -> QFrame:
    """等宽文本块（命令、预览行）。用标签而不是文本框，高度跟内容走。"""
    frame, layout = c.inner("pre")
    layout.addWidget(c.label(text, "mono"))
    return frame


class StationPage(QWidget):
    action = Signal(str)  # 动作键，由 app 交给 actions.py 在后台线程执行

    def __init__(self, on_project: Callable[[str], None], on_copy: Callable[[str], None]) -> None:
        super().__init__()
        self.on_project, self.on_copy = on_project, on_copy
        self.receipts: list[Receipt] = []
        self.drawer_open = True
        self.banner_dismissed = False
        self.checks_state = [False] * len(SAFETY_CHECKLIST)
        self.bc_preview_text = ""
        self.bc_fields: dict[str, str] = dict.fromkeys(BC_REQUIRED, "")
        self._bc_preview_frame: QFrame | None = None
        self._bc_write_button = None
        self.commit_text = ""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll, self.layout_ = c.page()
        outer.addWidget(self.scroll, 1)
        self.drawer = QFrame()
        self.drawer.setObjectName("idbar")
        self.drawer_layout = QVBoxLayout(self.drawer)
        self.drawer_layout.setContentsMargins(theme.SPACE * 2, theme.SPACE // 2, theme.SPACE * 2, theme.SPACE // 2)
        outer.addWidget(self.drawer)
        self.vm: StationVM | None = None

    # ------------------------------------------------ 画

    def render(self, vm: StationVM) -> None:
        self.vm = vm
        c.clear(self.layout_)
        lay = self.layout_
        bar = QFrame()
        bar.setObjectName("idbar")
        bar.setProperty("warn", "true" if vm.warn else "false")
        row = QHBoxLayout(bar)
        row.setContentsMargins(theme.SPACE * 2, theme.SPACE, theme.SPACE * 2, theme.SPACE)
        for key, value in vm.identity:
            row.addWidget(c.label(f"{key} {value}", "", wrap=False))
        row.addStretch(1)
        row.addWidget(c.label("两版本不一致或 RUNTIME_IDENTITY_DIVERGENCE 时整条变橙", "small", wrap=False))
        lay.addWidget(bar)
        if vm.banner and not self.banner_dismissed:
            frame = QFrame()
            frame.setObjectName("bar")
            frame.setProperty("sev", "risk")
            inner = QHBoxLayout(frame)
            inner.addWidget(c.label(vm.banner), 1)
            ok = c.button("知道了", "", "关掉这条提示")
            ok.clicked.connect(self._dismiss)
            inner.addWidget(ok)
            lay.addWidget(frame)

        lay.addWidget(c.section("接着干", "上次干到哪、下一步、要打开的文件、人工工位分支"))
        if not vm.projects:
            lay.addWidget(c.label("没有登记进驾驶舱的客户项目。", "muted"))
        for card, left, nxt, files, branch, safety in vm.projects:
            frame, inner = c.card()
            frame.setProperty("project_id", card.project_id)
            inner.addWidget(c.hrow(c.label(card.project_id, "mono", wrap=False), c.label(card.name, "section"), 1,
                                   c.chip("涉及安全区", "risk") if safety else c.chip("不涉及安全区", "ok")))
            inner.addWidget(c.kv([("上次干到", left), ("下一步", nxt), ("打开", "\n".join(files)),
                                  ("人工工位", f"{branch}（.auto-pm/worktrees/manual，不登记 Run）")]))
            see = c.button("看卡和变更记录", "", "打开这个项目")
            see.clicked.connect(lambda _checked=False, pid=card.project_id: self.on_project(pid))
            inner.addWidget(c.hrow(see, 1))
            lay.addWidget(frame)

        lay.addWidget(c.section("人工路线", "照《无 AI 离线手册》六步；每步的按钮只做本机的事，命令和退出码进底部控制台"))
        for step in vm.steps:
            lay.addWidget(self._step(step, vm))

        lay.addWidget(c.section("安全区自查", "勾选只在本机记着，提醒你自己，不进账本"))
        frame, inner = c.card()
        for index, text in enumerate(SAFETY_CHECKLIST):
            box = QCheckBox(text)
            box.setObjectName("safety_check")
            box.setChecked(self.checks_state[index])
            box.toggled.connect(lambda checked, i=index: self.checks_state.__setitem__(i, checked))
            inner.addWidget(box)
        lay.addWidget(frame)

        lay.addWidget(c.section("回来要补记的", "离线干的活，这些记录要你手写，AI 回来才接得上"))
        frame, inner = c.card()
        if not vm.records:
            inner.addWidget(c.label("无", "muted"))
        for pid, items in vm.records:
            inner.addWidget(c.label(pid, "mono", wrap=False))
            for item in items:
                inner.addWidget(c.label("· " + item))
        inner.addWidget(c.label("提交 .scl 时我们加的联锁会挡（要已批变更单）。离线时照常在 manual/ 分支本机提交，有网再推；"
                                "绕过联锁只限你本人在命令提示符里做。详见 0100_PLC自动化/00_通用规范/无AI离线手册.md", "small"))
        lay.addWidget(frame)
        lay.addWidget(c.label("工程工位是你当工程师时的页面；项目经理看板仍然只读。写文件只有“写入 BC 行”一处；"
                              "批准 / 开工要等缺口⑨合并；合并、删除、切换、代签永远不加。", "small"))
        self._render_drawer()

    def _step(self, step: Step, vm: StationVM) -> QFrame:
        frame, inner = c.card()
        frame.setProperty("step", str(step.number))
        frame.setProperty("state", step.state)
        number = c.label(str(step.number), "mark", wrap=False)
        number.setProperty("sev", {"done": "ok", "cur": "hint", "todo": "na"}[step.state])
        state_chip = {"done": c.chip("已完成", "ok"), "cur": c.chip("进行中", "hint"), "todo": c.chip("待做")}[step.state]
        inner.addWidget(c.hrow(number, c.label(step.title, "section"), state_chip, 1))
        inner.addWidget(c.label(step.detail, "muted"))
        if step.command:
            inner.addWidget(pre(step.command))
        if step.number == 2 and vm.safety_hits:
            hit, hit_layout = c.card("block")
            hit_layout.addWidget(c.label("安全区命中：" + "；".join(vm.safety_hits), "section"))
            hit_layout.addWidget(c.label("必须先仿真；BC“影响”栏写“安全区，待签字”；有网后补 CHG，签字前不合并。"
                                         "发现 OR TRUE 旁路直接判不合格。只提醒，不阻断。", "small"))
            inner.addWidget(hit)
        if step.number == 4:
            for key in BC_REQUIRED:
                field = QLineEdit(self.bc_fields[key])
                field.setObjectName("bc_field")
                field.setProperty("bc_key", key)
                field.setPlaceholderText(BC_HINTS[key])
                field.textChanged.connect(lambda text, k=key: self._bc_edited(k, text))
                name = c.label(key, "q", wrap=False)
                name.setMinimumWidth(name.fontMetrics().horizontalAdvance("改了什么") + theme.SPACE)  # 四栏对齐
                inner.addWidget(c.hrow(name, field, spacing=theme.SPACE))
            inner.addWidget(c.label("提出人从配置读（--operator / 环境变量 WORKSPACEPM_OPERATOR / git user.name），"
                                    "提出时间到分钟；批准人、批准日期、关联写“待补”，批了以后人工补。", "small"))
            self._bc_preview_frame = pre(self.bc_preview_text) if self.bc_preview_text else None
            if self._bc_preview_frame is not None:
                inner.addWidget(self._bc_preview_frame)
        if step.number == 5 and self.commit_text:
            inner.addWidget(pre(self.commit_text))
        if step.buttons:
            widgets = []
            for text, key, enabled, reason in step.buttons:
                enabled = enabled and not (key == "bc_write" and not self.bc_preview_text)
                reason = reason if not enabled else ""
                item = c.button(text, "", reason or text, enabled)
                item.setProperty("action", key)
                if key == "bc_write":
                    self._bc_write_button = item
                if key == "copy_commit":
                    item.clicked.connect(lambda: self.on_copy(self.commit_text))
                else:
                    item.clicked.connect(lambda _checked=False, k=key: self.action.emit(k))
                widgets.append(item)
            if step.number == 6:
                widgets.append(c.label("永远不会有：合并、删除、切换发布、替你签字、跑全量门禁", "small", wrap=False))
            inner.addWidget(c.hrow(*widgets, 1))
        return frame

    def _render_drawer(self) -> None:
        c.clear(self.drawer_layout)
        toggle = c.button("收起控制台" if self.drawer_open else "展开控制台", "ghost", "每个按钮对应的命令和退出码")
        toggle.clicked.connect(self._toggle_drawer)
        self.drawer_layout.addWidget(c.hrow(c.label("控制台", "section", wrap=False),
                                            c.label(f"{len(self.receipts)} 条回执 · CLI 和界面一致", "small", wrap=False), 1, toggle))
        if self.drawer_open:
            for receipt in self.receipts[:8]:
                self.drawer_layout.addWidget(
                    c.hrow(c.label(receipt.when, "mono", wrap=False), c.label(receipt.action, "", wrap=False),
                           c.label(receipt.command, "mono"), 1,
                           c.chip(receipt.rc_text, "ok" if receipt.rc == 0 else ("na" if receipt.rc is None or receipt.preview else "block")))
                )
            if not self.receipts:
                self.drawer_layout.addWidget(c.label("还没有动作。", "small"))

    # ------------------------------------------------ 状态

    def add_receipt(self, receipt: Receipt) -> None:
        self.receipts.insert(0, receipt)
        self._render_drawer()

    def set_bc_preview(self, text: str) -> None:
        self.bc_preview_text = text
        if self.vm is not None:
            self.render(self.vm)

    def _bc_edited(self, key: str, text: str) -> None:
        """改了任何一栏，之前的预览就作废：写入按钮立刻变灰，要重新预览（不整页重画，输入框不丢焦点）。"""
        self.bc_fields[key] = text
        if not self.bc_preview_text:
            return
        self.bc_preview_text = ""
        if self._bc_preview_frame is not None:
            self._bc_preview_frame.setVisible(False)
        if self._bc_write_button is not None:
            self._bc_write_button.setEnabled(False)
            self._bc_write_button.setToolTip("改过内容，先重新预览")

    def set_commit_text(self, text: str) -> None:
        self.commit_text = text

    def _toggle_drawer(self) -> None:
        self.drawer_open = not self.drawer_open
        self._render_drawer()

    def _dismiss(self) -> None:
        self.banner_dismissed = True
        if self.vm is not None:
            self.render(self.vm)
