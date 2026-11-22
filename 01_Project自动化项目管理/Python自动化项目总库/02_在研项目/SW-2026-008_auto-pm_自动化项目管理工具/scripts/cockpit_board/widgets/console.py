"""全局顶部失败常驻条与底部可折叠回执终端（收拢原本散落在各页的回执堆栈）。"""

from __future__ import annotations

from collections.abc import Callable

from cockpit_board import theme
from cockpit_board.actions import Receipt
from cockpit_board.widgets import common as c
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

MAX_RECEIPTS = 24
SHOWN_RECEIPTS = 12
TAIL_LINES = 8


def _tail(text: str, max_lines: int = TAIL_LINES) -> str:
    lines = [line for line in (text or "").strip().splitlines() if line.strip()]
    return "\n".join(lines[-max_lines:])


class GlobalFailureBar(QFrame):
    """全局常驻失败红条：任一非预览命令失败（rc 非 0）时弹出，点“知道了”才收起。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("global_failure_bar")
        self.setProperty("sev", "block")
        self.setProperty("role", "failure")
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(theme.SPACE * 2, theme.SPACE, theme.SPACE * 2, theme.SPACE)
        self.outer.setSpacing(theme.SPACE // 2)
        self.receipt: Receipt | None = None
        self.setVisible(False)

    def show_failure(self, receipt: Receipt) -> None:
        self.receipt = receipt
        c.clear(self.outer)
        self.outer.addWidget(c.label(f"没成功：{receipt.action}（{receipt.rc_text}）", "section"))
        tail = _tail(receipt.output, 4)
        if tail:
            self.outer.addWidget(c.label(tail))
        self.outer.addWidget(c.label(receipt.command, "mono"))
        ok = c.button("知道了", "", "关掉这条提示；原文仍留在底部回执终端里")
        ok.clicked.connect(self.dismiss)
        self.outer.addWidget(c.hrow(ok, 1))
        self.setVisible(True)

    def dismiss(self) -> None:
        self.receipt = None
        self.setVisible(False)


class GlobalConsoleDrawer(QFrame):
    """窗口底部全局可折叠回执终端（默认收起，显示最近 1 条动作、时间与 rc，点击展开看最近 12 条）。"""

    def __init__(self, on_copy: Callable[[str], None] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("console_drawer")
        self.on_copy = on_copy or (lambda _t: None)
        self.opened = False
        self.receipts: list[Receipt] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.SPACE * 2, theme.SPACE // 2, theme.SPACE * 2, theme.SPACE // 2)
        outer.setSpacing(theme.SPACE // 2)
        self.head_holder = QWidget()
        self.head_layout = QVBoxLayout(self.head_holder)
        self.head_layout.setContentsMargins(0, 0, 0, 0)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, theme.SPACE // 2, 0, theme.SPACE // 2)
        self.body_layout.setSpacing(theme.SPACE // 2)
        self.body.setVisible(False)
        outer.addWidget(self.head_holder)
        outer.addWidget(self.body)
        self._render()

    def set_open(self, opened: bool) -> None:
        self.opened = opened
        self.body.setVisible(opened)
        self._render()

    def toggle(self) -> None:
        self.set_open(not self.opened)

    def add_receipt(self, receipt: Receipt) -> None:
        if receipt.rc is not None:
            self.receipts = [r for r in self.receipts if not (r.rc is None and r.action == receipt.action)]
        self.receipts.append(receipt)
        self.receipts = self.receipts[-MAX_RECEIPTS:]
        self._render()

    def _render(self) -> None:
        c.clear(self.head_layout)
        c.clear(self.body_layout)
        arrow = c.FOLD_OPEN if self.opened else c.FOLD_CLOSED
        title = f"{arrow} 回执终端（{len(self.receipts)} 条）" if self.opened else f"{arrow} 回执终端"
        widgets: list[QWidget | int] = [c.quiet(title, "section")]
        if self.receipts:
            last = self.receipts[-1]
            sev = "ok" if last.rc == 0 else ("na" if last.rc is None or last.preview else "block")
            widgets += [
                c.chip(last.rc_text, sev),
                c.quiet(last.when, "mono"),
                c.quiet(last.action, "muted"),
                c.quiet(last.command, "mono"),
                1,
            ]
        else:
            widgets += [c.quiet("还没有命令回执 · 所有操作都会先展示等价命令行", "small"), 1]
        bar = c.click_row("console_toggle", "回执终端开关", "展开或收起全局命令执行回执历史", *widgets)
        bar.activated.connect(self.toggle)
        self.head_layout.addWidget(bar)
        if not self.opened:
            return
        if not self.receipts:
            self.body_layout.addWidget(c.label("还没有运行过任何命令。", "small"))
            return
        for receipt in reversed(self.receipts[-SHOWN_RECEIPTS:]):
            sev = "ok" if receipt.rc == 0 else ("na" if receipt.rc is None or receipt.preview else "block")
            copy_box = c.click_row("copy_cmd", "复制命令", "复制这条命令行", c.quiet("复制", "small"))
            copy_box.activated.connect(lambda cmd=receipt.command: self.on_copy(cmd))
            row = c.hrow(
                c.label(receipt.when, "mono", wrap=False),
                c.label(receipt.action, "section", wrap=False),
                c.chip(receipt.rc_text, sev),
                c.label(receipt.command, "mono"),
                1,
                copy_box,
            )
            self.body_layout.addWidget(row)
            tail = _tail(receipt.output, 3)
            if tail:
                self.body_layout.addWidget(c.label(tail, "small"))
