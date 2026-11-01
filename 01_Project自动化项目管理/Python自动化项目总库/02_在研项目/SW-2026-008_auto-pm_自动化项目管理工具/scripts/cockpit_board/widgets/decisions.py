"""“决定”页：批准范围、确认开工、确认验收、收口、搁着、拿回、插急活、确认/驳回入箱。

每个按钮点开一个确认对话框，对话框里先写清“会发生什么”和“等价的命令行”，用户再点“确认并运行”。
命令怎么拼见 decisions.py；真正起子进程在 actions.py。这里只画和发信号，不算业务、不起子进程。
失败不静默：回执失败时页顶红色横条常驻，写明命令、退出码和原文，用户点“知道了”才收起。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from cockpit_board import theme
from cockpit_board.actions import Receipt
from cockpit_board.decisions import (
    PIN_TEXT,
    CardVM,
    Decision,
    DecisionError,
    DecisionsVM,
    Target,
)
from cockpit_board.widgets import common as c
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

APPROVER_ENV = "AUTO_PM_COCKPIT_APPROVER"
RECEIPT_LIMIT = 8
OUTPUT_TAIL_LINES = 12


class ConfirmDialog(QDialog):
    """点按钮后的确认框。``preview`` 按当前填的内容返回等价命令；填得不对返回报错文字，确认键灰着。"""

    def __init__(self, decision: Decision, target: Target, pin_enforced: bool,
                 preview: Callable[[Mapping[str, str]], str], on_copy: Callable[[str], None],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.decision, self.target, self.preview, self.on_copy = decision, target, preview, on_copy
        self.via_terminal = pin_enforced and decision.pin
        self.command_text = ""
        self.inputs: dict[str, QLineEdit | QPlainTextEdit] = {}
        self.setObjectName("decision_dialog")
        self.setWindowTitle(decision.label)
        self.setMinimumWidth(560)
        outer = QVBoxLayout(self)
        outer.setSpacing(theme.SPACE)
        outer.addWidget(c.label(decision.label, "title", wrap=False))
        outer.addWidget(c.label(target.title or target.mission_id or target.request_id or target.item_id, "section"))
        outer.addWidget(c.label(decision.summary))
        if decision.danger:
            frame = QFrame()
            frame.setObjectName("bar")
            frame.setProperty("sev", "risk")
            QVBoxLayout(frame).addWidget(c.label(decision.danger))
            outer.addWidget(frame)
        for item in decision.fields:
            outer.addWidget(c.label(item.label + ("" if item.required else "（可空）"), "muted", wrap=False))
            box: QLineEdit | QPlainTextEdit = QPlainTextEdit() if item.multiline else QLineEdit()
            if item.multiline:
                box.setFixedHeight(64)
            box.setPlaceholderText(item.hint)
            box.setObjectName(f"field_{item.key}")
            box.textChanged.connect(self._refresh)
            self.inputs[item.key] = box
            outer.addWidget(box)
        outer.addWidget(c.label("等价的命令行（点“复制命令”可以拿到终端里自己运行）", "q"))
        self.command_label = c.label("", "mono")
        outer.addWidget(self.command_label)
        self.problem = c.label("", "muted")
        outer.addWidget(self.problem)
        if self.via_terminal:
            outer.addWidget(c.label("批准口令已生效：点下面的键会弹出一个新的终端窗口，口令只在那个窗口里输入，本程序看不到。", "small"))
        row = QHBoxLayout()
        self.copy_button = c.button("复制命令")
        self.copy_button.clicked.connect(lambda: self.on_copy(self.command_text))
        self.cancel_button = c.button("取消")
        self.cancel_button.clicked.connect(self.reject)
        self.run_button = c.button("在终端窗口里运行" if self.via_terminal else "确认并运行")
        self.run_button.setObjectName("run")
        self.run_button.clicked.connect(self.accept)
        row.addWidget(self.copy_button)
        row.addStretch(1)
        row.addWidget(self.cancel_button)
        row.addWidget(self.run_button)
        outer.addLayout(row)
        self._refresh()

    def values(self) -> dict[str, str]:
        return {key: (box.toPlainText() if isinstance(box, QPlainTextEdit) else box.text()).strip()
                for key, box in self.inputs.items()}

    def _refresh(self) -> None:
        try:
            self.command_text = self.preview(self.values())
            ok, message = True, ""
        except DecisionError as error:
            self.command_text, ok, message = "", False, str(error)
        self.command_label.setText(self.command_text or "（填好后显示）")
        self.problem.setText(message)
        self.run_button.setEnabled(ok)
        self.copy_button.setEnabled(ok)


class DecisionsPage(QWidget):
    run_requested = Signal(object, object, object, bool)  # Decision, Target, values, 是否改走终端窗口

    def __init__(self, on_copy: Callable[[str], None],
                 preview: Callable[[Decision, Target, Mapping[str, str], str, bool], str]) -> None:
        """``preview(decision, target, values, approver, pin_enforced)`` 拼等价命令，由 app 提供，页面不碰 actions。"""
        super().__init__()
        self.setObjectName("decisions_page")
        self.on_copy, self.preview = on_copy, preview
        self.vm = DecisionsVM()
        self.receipts: list[Receipt] = []
        self.failure: Receipt | None = None
        self.last_dialog: ConfirmDialog | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll_area, self.layout_ = c.page()
        outer.addWidget(self.scroll_area, 1)
        self.approver_input = QLineEdit(os.environ.get(APPROVER_ENV, ""))
        self.approver_input.setObjectName("approver")
        self.approver_input.setPlaceholderText("你的名字（批准记录里显示的批准人）")
        self.show_view(self.vm)

    # ------------------------------------------------ 画

    def approver(self) -> str:
        return self.approver_input.text().strip()

    def show_view(self, vm: DecisionsVM) -> None:
        self.vm = vm
        lay = self.layout_
        self.approver_input.setParent(None)
        c.clear(lay)
        lay.addWidget(c.label("决定", "title", wrap=False))
        lay.addWidget(c.label("这里每个按钮背后都是同一条命令行；点开能看到命令，运行后退出码和原文留在下面。"
                              "命令自己判门禁、租约和口令，这里不替它放行。", "muted"))
        if self.failure is not None:
            lay.addWidget(self._failure_bar(self.failure))
        lay.addWidget(c.label(vm.pin_text or PIN_TEXT["unknown"], "small"))
        lay.addWidget(c.hrow(c.label("批准人", "muted", wrap=False), self.approver_input, spacing=theme.SPACE))
        if not vm.cards:
            lay.addWidget(c.label("现在没有要你决定的事。", "muted"))
        column = ""
        for card in vm.cards:
            if card.column != column:
                column = card.column
                lay.addWidget(c.section(column))
            lay.addWidget(self._card(card))
        lay.addWidget(c.section("刚才运行过的命令", f"最近 {RECEIPT_LIMIT} 条，命令、退出码和原文输出"))
        if not self.receipts:
            lay.addWidget(c.label("还没有运行过。", "muted"))
        for receipt in reversed(self.receipts[-RECEIPT_LIMIT:]):
            lay.addWidget(self._receipt(receipt))

    def _card(self, card: CardVM) -> QFrame:
        frame, inner = c.card(card.sev)
        frame.setProperty("column", card.column)
        inner.addWidget(c.label(card.heading, "section"))
        inner.addWidget(c.label(card.detail, "mono"))
        buttons = []
        for decision in card.decisions:
            item = c.button(decision.label, "", decision.summary)
            item.setProperty("decision", decision.key)
            item.clicked.connect(lambda _checked=False, d=decision, t=card.target: self.open_dialog(d, t))
            buttons.append(item)
        inner.addWidget(c.hrow(*buttons, 1))
        return frame

    def _failure_bar(self, receipt: Receipt) -> QFrame:
        frame = QFrame()
        frame.setObjectName("bar")
        frame.setProperty("sev", "block")
        frame.setProperty("role", "failure")
        box = QVBoxLayout(frame)
        box.addWidget(c.label(f"没成功：{receipt.action}（{receipt.rc_text}）", "section"))
        box.addWidget(c.label(_tail(receipt.output) or "命令没有输出。"))
        box.addWidget(c.label(receipt.command, "mono"))
        ok = c.button("知道了", "", "关掉这条提示；原文仍留在下面的记录里")
        ok.clicked.connect(self.dismiss_failure)
        box.addWidget(c.hrow(ok, 1))
        return frame

    def _receipt(self, receipt: Receipt) -> QFrame:
        frame, inner = c.card("ok" if receipt.rc == 0 else ("block" if receipt.rc else "hint"))
        inner.addWidget(c.hrow(c.label(receipt.when, "mono", wrap=False), c.label(receipt.action, "section"),
                               c.chip(receipt.rc_text, "ok" if receipt.rc == 0 else ("block" if receipt.rc else "hint")), 1))
        inner.addWidget(c.label(receipt.command, "mono"))
        if receipt.output.strip():
            inner.addWidget(c.label(_tail(receipt.output), "small"))
        return frame

    # ------------------------------------------------ 动作

    def open_dialog(self, decision: Decision, target: Target, *, run: bool = True) -> ConfirmDialog:
        pin = self.vm.pin_mode == "enforced"
        dialog = ConfirmDialog(decision, target, pin,
                               lambda values: self.preview(decision, target, values, self.approver(), pin),
                               self.on_copy, self)
        self.last_dialog = dialog
        if run and dialog.exec() == QDialog.DialogCode.Accepted:
            self.run_requested.emit(decision, target, dialog.values(), dialog.via_terminal)
        return dialog

    def add_receipt(self, receipt: Receipt) -> None:
        self.receipts.append(receipt)
        self.receipts = self.receipts[-RECEIPT_LIMIT * 2:]
        self.failure = receipt if receipt.rc not in (0,) and receipt.rc is not None else None
        self.show_view(self.vm)

    def dismiss_failure(self) -> None:
        self.failure = None
        self.show_view(self.vm)


def _tail(text: str) -> str:
    lines = [line for line in (text or "").strip().splitlines() if line.strip()]
    return "\n".join(lines[-OUTPUT_TAIL_LINES:])

