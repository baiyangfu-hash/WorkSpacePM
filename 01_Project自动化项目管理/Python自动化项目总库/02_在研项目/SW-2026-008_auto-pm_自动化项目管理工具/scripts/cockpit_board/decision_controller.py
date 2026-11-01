"""“决定”页的接线：读只读命令、拼命令、后台跑、把回执交给页面。

app.py 接这个页面只需要三件事（S0 合并后再动 app.py）：
    controller = DecisionController(root, on_copy, on_changed)   # on_changed：命令成功后让主窗口重新读账本
    stack.addWidget(controller.page)                              # 顶栏加一个“决定”页签
    controller.refresh(project_ids, missions)                     # 每次主窗口读完账本后调一次

本文件不直接起子进程：只调 actions.run_cli / actions.open_console（整个包里唯一允许起子进程的地方）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from cockpit_board import actions, decisions
from cockpit_board.widgets.decisions import DecisionsPage


class _Job(QThread):
    done = Signal(object)

    def __init__(self, job: Callable[[], Any], parent: QObject | None) -> None:
        super().__init__(parent)
        self.job = job

    def run(self) -> None:
        self.done.emit(self.job())


class DecisionController(QObject):
    def __init__(self, root: Path, on_copy: Callable[[str], None], on_changed: Callable[[], None],
                 runner: Callable[..., Any] | None = None, now: Callable[[], datetime] = datetime.now) -> None:
        super().__init__()
        self.root, self.on_changed, self.now = root, on_changed, now
        self.runner = runner  # 测试注入；None 用 actions 里的默认运行器
        self.pin_mode = "unknown"
        self.missions: Sequence[Any] = ()
        self.project_ids: Sequence[str] = ()
        self._jobs: list[QThread] = []
        self.page = DecisionsPage(on_copy, self.preview)
        self.page.run_requested.connect(self.run_decision)
        self.page.reload_requested.connect(self.on_changed)

    # ------------------------------------------------ 拼命令（对话框实时调）

    def preview(self, decision: decisions.Decision, target: decisions.Target, values: Mapping[str, str],
                approver: str, pin_enforced: bool) -> str:
        args = decisions.build_args(decision, target, values, approver=approver, pin_enforced=pin_enforced, now=self.now())
        return decisions.shown_command(args)

    # ------------------------------------------------ 读

    def refresh(self, project_ids: Sequence[str], missions: Sequence[Any]) -> None:
        self.project_ids, self.missions = tuple(project_ids), tuple(missions)
        self._spawn(self._read_all, self._read_done)

    def _read_all(self) -> tuple[str, dict[str, list[decisions.Target]], dict[str, list[decisions.Target]]]:
        extra: dict[str, Any] = {"runner": self.runner} if self.runner else {}
        pin = decisions.parse_pin_status(actions.run_cli(self.root, "口令状态", ("pm", "approver-pin", "status"), **extra).output)
        pending: dict[str, list[decisions.Target]] = {}
        inbox: dict[str, list[decisions.Target]] = {}
        for pid in self.project_ids:
            got = actions.run_cli(self.root, "读待批准范围卡", (*decisions.READ_ONLY_COMMANDS["pending"], pid), **extra)
            pending[pid] = decisions.parse_pending(got.output, pid) if got.rc == 0 else []
            got = actions.run_cli(self.root, "读收件箱", (*decisions.READ_ONLY_COMMANDS["inbox"], pid), **extra)
            inbox[pid] = decisions.parse_inbox(got.output, pid) if got.rc == 0 else []
        return pin, pending, inbox

    def _read_done(self, result: Any) -> None:
        pin, pending, inbox = result
        self.pin_mode = pin
        vm = decisions.build_vm(self.missions, pending, inbox, pin)
        self.page.show_view(vm)

    # ------------------------------------------------ 运行

    def run_decision(self, decision: decisions.Decision, target: decisions.Target, values: Mapping[str, str],
                     via_terminal: bool) -> None:
        pin = self.pin_mode == "enforced"
        try:
            args = decisions.build_args(decision, target, values, approver=self.page.approver(), pin_enforced=pin, now=self.now())
        except decisions.DecisionError as error:  # 对话框已拦过，这里兜底，不静默
            self.page.add_receipt(actions.Receipt(self.now().strftime("%H:%M"), decision.label, "(未运行)", 1, False, str(error)))
            return
        extra: dict[str, Any] = {"runner": self.runner} if self.runner else {}
        if via_terminal:
            job: Callable[[], Any] = lambda: actions.open_console(self.root, decision.label, args)  # noqa: E731
        else:
            job = lambda: actions.run_cli(self.root, decision.label, args, **extra)  # noqa: E731
        self._spawn(job, self._run_done)

    def _run_done(self, receipt: actions.Receipt) -> None:
        self.page.add_receipt(receipt)
        if actions.needs_terminal(receipt):
            self.pin_mode = "enforced"  # 命令说口令已生效：下次点同一个按钮就改走终端窗口
        if receipt.rc == 0:
            self.on_changed()

    def _spawn(self, job: Callable[[], Any], done: Callable[[Any], None]) -> None:
        thread = _Job(job, self)
        thread.done.connect(done)
        thread.finished.connect(lambda t=thread: self._jobs.remove(t) if t in self._jobs else None)
        self._jobs.append(thread)
        thread.start()
