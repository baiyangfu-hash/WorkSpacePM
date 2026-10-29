"""工程工位：身份条、错误横条、接着干、人工路线六步、安全区自查、回来要补记、控制台抽屉。

按钮只做本机的事；写文件只有“写入 BC 行”（用户 10-22 批准，带预览）；批准 / 开工灰到缺口⑨合并。
真正起子进程、写文件的代码在 actions.py，这里只发信号。
"""

from __future__ import annotations

from collections.abc import Callable

from cockpit_board import theme
from cockpit_board.actions import BC_CHANNELS, BC_TYPES, BcForm, BcPreview, Receipt
from cockpit_board.viewmodel import StationVM, Step
from cockpit_board.widgets import common as c
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# 第 4 步表单的栏（键, 标签, 提示）。栏名和说明照 02_业务变更记录模板.md 的填写说明。
BC_FIELDS = (
    ("raised", "提出时间", "YYYY-MM-DD HH:MM，对方提出的时间，写到分钟"),
    ("channel", "渠道", ""),
    ("who", "提出人", "姓名 + 单位或岗位，例如：张工（客户设备科）"),
    ("kind", "类型", ""),
    ("what", "改了什么", "原来 → 改成，写具体值"),
    ("why", "为什么", "对方给的原因，不要自己推测"),
    ("impact", "影响", "会动到的程序块、图纸、IO、节拍、成本、交期；没有就写“无”"),
)
BC_CHOICES = {"channel": BC_CHANNELS, "kind": BC_TYPES}
BC_NOTE_EMPTY = "全部填好后点“预览”，看过整行再点“写入”。批准人、批准日期、关联留空，状态写“待批”。"
BC_NOTE_READY = "确认下面每一栏都对，再点“写入”。写入后表单若再改，要重新预览。"

SAFETY_CHECKLIST = (
    "急停、安全门、光栅、联锁、安全继电器、双手启动的逻辑，改了先 PLCSIM / InoProShop 仿真",
    "没有 OR TRUE 一类旁路；安全点没有漏接",
    "下载前校验码和上次上载记录对得上",
    "有网后 PR 上写“安全签字 + 提交号”，再合并",
)


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
        self.bc_preview: BcPreview | None = None
        self.bc_values: dict[str, str] = {}
        self.bc_note = BC_NOTE_EMPTY
        self.bc_inputs: dict[str, QLineEdit | QComboBox] = {}
        self._bc_note: QLabel | None = None
        self._bc_preview_box: QWidget | None = None
        self._bc_write_button: QPushButton | None = None
        self.commit_text = ""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll_area, self.layout_ = c.page()
        outer.addWidget(self.scroll_area, 1)
        self.drawer = QFrame()
        self.drawer.setObjectName("idbar")
        self.drawer_layout = QVBoxLayout(self.drawer)
        self.drawer_layout.setContentsMargins(theme.SPACE * 2, theme.SPACE // 2, theme.SPACE * 2, theme.SPACE // 2)
        outer.addWidget(self.drawer)
        self.vm: StationVM | None = None

    # ------------------------------------------------ 画

    def show_view(self, vm: StationVM) -> None:
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
            banner_row = QHBoxLayout(frame)
            banner_row.addWidget(c.label(vm.banner), 1)
            ok = c.button("知道了", "", "关掉这条提示")
            ok.clicked.connect(self._dismiss)
            banner_row.addWidget(ok)
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
            inner.addWidget(self._bc_form())
        if step.number == 5 and self.commit_text:
            inner.addWidget(pre(self.commit_text))
        if step.buttons:
            widgets: list[QWidget | int] = []
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

    # ------------------------------------------------ 第 4 步：业务变更表单

    def _bc_form(self) -> QFrame:
        """提出时间 / 渠道 / 提出人 / 类型 / 改了什么 / 为什么 / 影响，全由你填；预览把整行 11 栏逐栏列出来。"""
        frame, layout = c.inner("bc_form")
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.SPACE)
        grid.setVerticalSpacing(theme.SPACE // 2)
        self.bc_inputs = {}
        for row, (key, label, hint) in enumerate(BC_FIELDS):
            grid.addWidget(c.label(label, "muted", wrap=False), row, 0)
            if key in BC_CHOICES:
                box = QComboBox()
                box.addItems(BC_CHOICES[key])
                box.setCurrentText(self.bc_values.get(key) or BC_CHOICES[key][0])
                box.currentTextChanged.connect(lambda text, k=key: self._bc_edited(k, text))
                widget: QLineEdit | QComboBox = box
            else:
                edit = QLineEdit(self.bc_values.get(key, ""))
                edit.setPlaceholderText(hint)
                edit.textChanged.connect(lambda text, k=key: self._bc_edited(k, text))
                widget = edit
            widget.setObjectName("bc_" + key)
            self.bc_inputs[key] = widget
            grid.addWidget(widget, row, 1)
        holder = QWidget()
        holder.setLayout(grid)
        layout.addWidget(holder)
        self._bc_note = c.label(self.bc_note, "small")
        layout.addWidget(self._bc_note)
        self._bc_preview_box = QWidget()
        box_layout = QVBoxLayout(self._bc_preview_box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        if self.bc_preview is not None:
            box_layout.addWidget(c.label(f"预览：要往表末追加的一行，共 {len(self.bc_preview.columns)} 栏", "small"))
            box_layout.addWidget(c.kv([(name, cell or "（空）") for name, cell in self.bc_preview.columns]))
            box_layout.addWidget(pre(self.bc_preview.line))
        layout.addWidget(self._bc_preview_box)
        return frame

    def bc_form(self) -> BcForm:
        v = self.bc_values
        return BcForm(v.get("raised", ""), v.get("channel", BC_CHANNELS[0]), v.get("who", ""),
                      v.get("kind", BC_TYPES[0]), v.get("what", ""), v.get("why", ""), v.get("impact", ""))

    def set_bc_time(self, text: str) -> None:
        """进工位时给“提出时间”填上现在（到分钟），你可以改成对方实际提出的时间。"""
        self.bc_values.setdefault("raised", text)

    def _bc_edited(self, key: str, text: str) -> None:
        self.bc_values[key] = text
        if self.bc_preview is not None:  # 预览后又改了表单：预览作废，写入变灰，要重新预览
            self.bc_preview = None
            self.bc_preview_text = ""
            self._set_bc_note("表单改过了，请重新预览再写入。")
            if self._bc_preview_box is not None:
                self._bc_preview_box.setVisible(False)
            if self._bc_write_button is not None:
                self._bc_write_button.setEnabled(False)

    def _set_bc_note(self, text: str) -> None:
        self.bc_note = text
        if self._bc_note is not None:
            self._bc_note.setText(text)

    def set_bc_preview(self, preview: BcPreview | None, note: str = "") -> None:
        self.bc_preview = preview
        self.bc_preview_text = preview.line if preview else ""
        self.bc_note = note or (BC_NOTE_READY if preview else BC_NOTE_EMPTY)
        if self.vm is not None:
            self.show_view(self.vm)

    def set_commit_text(self, text: str) -> None:
        self.commit_text = text

    def _toggle_drawer(self) -> None:
        self.drawer_open = not self.drawer_open
        self._render_drawer()

    def _dismiss(self) -> None:
        self.banner_dismissed = True
        if self.vm is not None:
            self.show_view(self.vm)
