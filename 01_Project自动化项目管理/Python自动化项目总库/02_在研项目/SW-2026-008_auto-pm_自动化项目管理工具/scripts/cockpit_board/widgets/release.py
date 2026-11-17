"""发版页（CHG-SCPT-2026-628 骨架 D；CHG-SCPT-2026-707 加“同意切换”）：有哪些候选版本、各改了什么、门禁和审计放没放行，
用户本人点“同意切换到 <发布号>”换成新版本；底下照旧是长任务（全量门禁等）现在的状态。

候选版本来自控制根 ``.auto-pm/release-candidates/<发布号>/``；每个候选版本的结论来自 ``main.py release ship <提交> --json``（只看，不写），
由 release_controller.py 在后台跑。长任务读 `long-run status`（只读，flow/pages.json 登记）。
“同意切换”是 policy.py 里写明的例外（RELEASE_BUTTONS），按钮亮不亮按 release_ship.blocked_reason 一条条判，带 AI 标记的看板一律灰着。
这里只画、只发信号，不起子进程、不写文件。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from cockpit_board import decisions, release_ship, shell, theme
from cockpit_board.actions import Receipt
from cockpit_board.release_ship import Candidate, Check
from cockpit_board.widgets import common as c
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

RECEIPT_LIMIT = 6
OUTPUT_TAIL_LINES = 12
RUNNING = "正在运行……演练、部署、失败时自动退回都在这一条命令里，可能要几分钟；跑完这里会写切换成了没有"
NO_ROOT = "没有控制根：不列候选版本"
NO_CANDIDATES = "没有候选版本：控制根 .auto-pm/release-candidates/ 下没有按发布号命名的文件夹（打包后才会有）"
RECORD_NOTE = ("点“确认并运行”那一刻，看板生成凭据（user-confirmation:board-click:<UTC 时间>:<看板会话号>），"
               "先把谁、何时点的写进 .auto-pm/reports/board_approvals/release_ship.jsonl，写成了才运行；"
               "命令自己再判一遍门禁和审计，先演练再换，失败自动退回旧版本。")

STATE_ZH = {"STARTING": "正在起", "RUNNING": "在跑", "DONE": "跑完", "FAILED": "跑完没过或没跑起来", "STOPPED": "被停了", "UNREADABLE": "读不懂"}


def _task(row: dict[str, Any]) -> str:
    state = str(row.get("state") or "")
    parts = [STATE_ZH.get(state, state or "（没写状态）")]
    if row.get("exit_code") is not None:
        parts.append(f"退出码 {row['exit_code']}")
    if row.get("started_at"):
        parts.append("开始于 " + str(row["started_at"]))
    if row.get("error"):
        parts.append(str(row["error"]))
    return " · ".join(parts)


def summarize(reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
    if reader == "long_run":
        tasks = data.get("tasks") or []
        return [("长任务", c.count_text(tasks, "个")), *((str(row.get("name")), _task(row)) for row in tasks)]
    return []


def is_empty(reader: str, data: dict[str, Any]) -> bool | None:
    """没有 STARTING 或 RUNNING 的长任务就算空（跑完的照样列在下面）。"""
    if reader == "long_run":
        return not [row for row in data.get("tasks") or [] if str(row.get("state") or "") in ("STARTING", "RUNNING")]
    return None


class ReleaseDialog(QDialog):
    """点“同意切换到 <发布号>”弹出的确认框：版本、门禁、审计、预检、改了什么、批准人、等价命令。

    ``blocked`` 非空或批准人没填时“确认并运行”一直灰着。凭据在这里不生成（点了确认才由控制器生成），命令里先放占位。
    """

    def __init__(self, check: Check, blocked: str, approver: str, on_copy: Callable[[str], None],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.check, self.blocked = check, blocked
        title = release_ship.SWITCH_PREFIX + check.candidate.release_id
        self.setObjectName("release_dialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(600)
        outer = QVBoxLayout(self)
        outer.setSpacing(theme.SPACE)
        outer.addWidget(c.label(title, "title", wrap=False))
        outer.addWidget(c.kv(_facts(check)))
        outer.addWidget(c.label(RECORD_NOTE, "small"))
        outer.addWidget(c.label(decisions.APPROVER_LABEL, "q"))
        self.approver_input = QLineEdit(approver)
        self.approver_input.setObjectName("approver")
        outer.addWidget(self.approver_input)
        outer.addWidget(c.label("等价的命令行", "q"))
        self.command_text = _shown_switch(check, self.approver_input.text())
        self.command_label = c.label(self.command_text, "mono")
        outer.addWidget(self.command_label)
        if blocked:
            outer.addWidget(c.label(blocked, "small"))
        row = QHBoxLayout()
        self.copy_button = c.button("复制命令")
        self.copy_button.clicked.connect(lambda: on_copy(self.command_text))
        self.cancel_button = c.button("取消")
        self.cancel_button.clicked.connect(self.reject)
        self.run_button = c.button("确认并运行")
        self.run_button.setObjectName("run")
        self.run_button.clicked.connect(self.accept)
        row.addWidget(self.copy_button)
        row.addStretch(1)
        row.addWidget(self.cancel_button)
        row.addWidget(self.run_button)
        outer.addLayout(row)
        self.approver_input.textChanged.connect(self._approver_changed)
        self._approver_changed(self.approver_input.text())

    def approver(self) -> str:
        return self.approver_input.text().strip()

    def _approver_changed(self, _text: str) -> None:
        self.command_text = _shown_switch(self.check, self.approver())
        self.command_label.setText(self.command_text)
        self.run_button.setEnabled(not self.blocked and bool(self.approver()))


def _shown_switch(check: Check, approver: str) -> str:
    commit = check.commit if release_ship.COMMIT.fullmatch(check.commit or "") else check.candidate.commit
    args = release_ship.switch_args(commit, release_ship.REF_PLACEHOLDER, approver or "<批准人>")
    return release_ship.shown_command(args)


def _facts(check: Check) -> list[tuple[str, str]]:
    rows = [("发布号", check.candidate.release_id), ("提交", check.commit or check.candidate.commit),
            ("现在生效的版本", check.active_release or "（命令没写）"), ("门禁", release_ship.gate_text(check)),
            ("审计", release_ship.audit_text(check)),
            ("预检", "通过" if check.preflight.get("ok") is True else "没过或没写")]
    rows += release_ship.preflight_rows(check)
    changes = release_ship.change_lines(check)
    rows.append(("改了什么", "\n".join(changes) if changes else "命令没列出 PR"))
    return rows


class ReleasePage(c.ReadPage):
    check_requested = Signal()  # 点了“重新检查候选版本”
    switch_requested = Signal(str, str)  # （发布号，批准人）：用户在确认框里点了“确认并运行”

    def __init__(self, root: Path | None = None, markers: Callable[[], Sequence[str] | None] | None = None,
                 on_copy: Callable[[str], None] | None = None, approver: Callable[[], str] | None = None) -> None:
        empty_text, error_text = shell.page_texts()["release"]
        super().__init__("release", "发版", "有哪些候选版本、门禁和审计放没放行、要不要换成新版本", (), empty_text, error_text)
        self.root = root
        self.markers = markers or (lambda: None)
        self.on_copy = on_copy or (lambda _text: None)
        self.approver = approver or (lambda: "")
        self.candidates: list[Candidate] = []
        self.checks: dict[str, Check] = {}
        self.checking = False
        self.busy = False  # 真发版那条命令正在跑
        self.receipts: list[Receipt] = []
        self.results_text: dict[str, tuple[str, str]] = {}  # 发布号 → （切换结果一句话，sev）
        self.human_block = ""
        self.check_block = ""  # 这次没跑检查的原因（看板带 AI 标记时只看那条也不跑）
        self.last_dialog: ReleaseDialog | None = None
        box = QWidget()
        self.ship = QVBoxLayout(box)
        self.ship.setContentsMargins(0, 0, 0, 0)
        self.ship.setSpacing(theme.SPACE)
        parent = self.project_line.parentWidget()
        body = parent.layout() if parent is not None else None
        if isinstance(body, QVBoxLayout):  # 候选版本放在长任务那几块上面
            body.insertWidget(body.indexOf(self.project_line) + 1, box)
        self.render_ship()

    def summary(self, reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
        return summarize(reader, data)

    def is_empty(self, reader: str, data: dict[str, Any]) -> bool | None:
        return is_empty(reader, data)

    # ------------------------------------------------ 控制器喂数据

    def set_candidates(self, candidates: Sequence[Candidate], checking: bool, check_block: str = "") -> None:
        """新列出的候选版本；旧结论只留还在的那几个（正在检查时照样显示上一次的，按钮按上一次的判）。

        ``check_block`` 非空：这次没跑检查（release ship 是 user_only，看板带 AI 标记），旧结论也不留，写原因。"""
        self.candidates = list(candidates)
        self.check_block = check_block
        if check_block:
            self.checks = {}
        ids = {item.release_id for item in self.candidates}
        self.checks = {key: value for key, value in self.checks.items() if key in ids}
        self.checking = checking
        self.render_ship()

    def set_checks(self, checks: Sequence[Check]) -> None:
        self.checks.update({item.candidate.release_id: item for item in checks})
        self.checking = False
        self.render_ship()

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.render_ship()

    def set_result(self, release_id: str, text: str, sev: str) -> None:
        self.results_text[release_id] = (text, sev)
        self.render_ship()

    def add_receipt(self, receipt: Receipt) -> None:
        self.receipts.append(receipt)
        self.receipts = self.receipts[-RECEIPT_LIMIT * 2:]
        self.render_ship()

    def blocked(self, release_id: str) -> str:
        """这个候选版本的“同意切换”为什么灰着；空串＝可以点。点开那一刻、运行之前都再算一次。"""
        return release_ship.blocked_reason(self.checks.get(release_id), decisions.human_only_block(self.markers()), self.busy)

    # ------------------------------------------------ 画

    def render_ship(self) -> None:
        c.clear(self.ship)
        if self.root is None:
            return
        self.human_block = decisions.human_only_block(self.markers())
        self.ship.addWidget(c.section("候选版本", "每个版本改了什么、门禁和审计放没放行；按钮灰着时旁边写着差哪一条"))
        if not self.candidates:
            self.ship.addWidget(c.label(NO_CANDIDATES, "muted"))
        else:
            if self.human_block:
                self.ship.addWidget(c.label(self.human_block, "small"))
            again = c.button("重新检查候选版本", "", "对每个候选版本再跑一遍 release ship <提交> --json（只看，不写）")
            again.setProperty("release_action", "check")
            again.setEnabled(not self.checking and not self.check_block)
            again.clicked.connect(self.check_requested.emit)
            note = "正在检查……" if self.checking else ""
            self.ship.addWidget(c.hrow(again, c.label(note, "small"), 1) if note else c.hrow(again, 1))
            for candidate in self.candidates:
                self.ship.addWidget(self._candidate(candidate))
        if self.receipts:
            self.ship.addWidget(c.section("刚才运行过的切换", f"最近 {RECEIPT_LIMIT} 条，命令、退出码和原文输出"))
            for receipt in reversed(self.receipts[-RECEIPT_LIMIT:]):
                self.ship.addWidget(self._receipt(receipt))

    def _candidate(self, candidate: Candidate) -> QFrame:
        check = self.checks.get(candidate.release_id)
        blocked = self.blocked(candidate.release_id)
        frame, inner = c.card("" if not blocked else ("hint" if check is None else "block"))
        frame.setProperty("candidate", candidate.release_id)
        inner.addWidget(c.label(candidate.release_id, "section"))
        if check is None and self.check_block:
            inner.addWidget(c.label("没跑 release ship（只看那条也只许你本人打开的看板跑）", "muted"))
        elif check is None:
            inner.addWidget(c.label("还没读到 release ship 的结论" + ("（正在检查）" if self.checking else ""), "muted"))
        elif check.problem:
            inner.addWidget(c.label("没读懂 release ship 的输出：" + check.problem, "small"))
            if check.output.strip():
                lines = [line for line in check.output.strip().splitlines() if line.strip()]
                inner.addWidget(c.label("\n".join(lines[-OUTPUT_TAIL_LINES:]), "small"))
        else:
            inner.addWidget(c.kv(_facts(check)))
        result = self.results_text.get(candidate.release_id)
        if result is not None:
            bar = QFrame()
            bar.setObjectName("bar")
            bar.setProperty("sev", result[1])
            bar.setProperty("switch_result", candidate.release_id)
            QVBoxLayout(bar).addWidget(c.label(result[0]))
            inner.addWidget(bar)
        item = c.button(release_ship.SWITCH_PREFIX + candidate.release_id, "",
                        "先弹确认框：版本、门禁、审计、等价命令；点“确认并运行”才会生成凭据并运行")
        item.setProperty("release_action", "switch")
        item.setProperty("target", candidate.release_id)
        item.setEnabled(not blocked)
        item.clicked.connect(lambda _checked=False, r=candidate.release_id: self.open_dialog(r))
        widgets: list[QWidget | int] = [item]
        if blocked:
            reason = c.label(blocked, "small")
            reason.setProperty("blocked_reason", candidate.release_id)
            widgets.append(reason)
        inner.addWidget(c.hrow(*widgets, 1))
        return frame

    def _receipt(self, receipt: Receipt) -> QFrame:
        sev = "ok" if receipt.rc == 0 else ("block" if receipt.rc else "hint")
        frame, inner = c.card(sev)
        frame.setProperty("receipt", receipt.action)
        inner.addWidget(c.hrow(c.label(receipt.when, "mono", wrap=False), c.label(receipt.action, "section"),
                               c.chip(receipt.rc_text, sev), 1))
        inner.addWidget(c.label(receipt.command, "mono"))
        if receipt.output.strip():
            lines = [line for line in receipt.output.strip().splitlines() if line.strip()]
            inner.addWidget(c.label("\n".join(lines[-OUTPUT_TAIL_LINES:]), "small"))
        return frame

    # ------------------------------------------------ 动作

    def open_dialog(self, release_id: str, *, run: bool = True) -> ReleaseDialog | None:
        check = self.checks.get(release_id)
        if check is None:
            return None
        dialog = ReleaseDialog(check, self.blocked(release_id), self.approver(), self.on_copy, self)
        self.last_dialog = dialog
        if run and dialog.exec() == QDialog.DialogCode.Accepted and not dialog.blocked:
            self.switch_requested.emit(release_id, dialog.approver())
        return dialog
