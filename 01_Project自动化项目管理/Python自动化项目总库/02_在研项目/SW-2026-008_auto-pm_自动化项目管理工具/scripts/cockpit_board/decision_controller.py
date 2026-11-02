"""“决定”页的接线：读只读命令、拼命令、后台跑、把回执交给页面。

app.py 接这个页面只需要三件事（S0 合并后再动 app.py）：
    controller = DecisionController(root, on_copy, on_changed)   # on_changed：命令成功后让主窗口重新读账本
    stack.addWidget(controller.page)                              # 顶栏加一个“决定”页签
    controller.refresh(project_ids, missions)                     # 每次主窗口读完账本后调一次

本文件不直接起子进程：只调 actions.run_cli / actions.open_console（整个包里唯一允许起子进程的地方）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from cockpit_board import actions, decisions
from cockpit_board.widgets.decisions import DecisionsPage


def _judged(got: actions.Receipt) -> str:
    """交给 read_failure 判读的文字，和下面取数用的是同一份：读成功（rc 0）只看 stdout，stderr 里有启动器横幅，不是数据，
    就算 stderr 恰好有一段像数据的 JSON 也不算；失败时给 stdout 接 stderr，好让红条引到错误原文的末行。"""

    return got.stdout if got.rc == 0 else got.output


def _read_failure(label: str, got: actions.Receipt, key: str | None) -> decisions.ReadFailure | None:
    bad = decisions.read_failure(label, got.command, got.rc, _judged(got), key=key)
    if bad is not None and not bad.detail:  # 例如 stdout 空、原因只在 stderr：别让红条的原文是空白
        bad = replace(bad, detail=decisions.last_line(got.stderr))
    return bad


class _Job(QThread):
    done = Signal(object)

    def __init__(self, job: Callable[[], Any], parent: QObject | None) -> None:
        super().__init__(parent)
        self.job = job

    def run(self) -> None:
        try:
            result = self.job()
        except Exception as error:  # noqa: BLE001 - 后台任务出任何错都交回主线程显示，不让“读取中”标记卡死、也不静默
            result = error
        self.done.emit(result)


class DecisionController(QObject):
    def __init__(self, root: Path, on_copy: Callable[[str], None], on_changed: Callable[[], None],
                 runner: Callable[..., Any] | None = None, now: Callable[[], datetime] = datetime.now) -> None:
        super().__init__()
        self.root, self.on_changed, self.now = root, on_changed, now
        self.runner = runner  # 测试注入；None 用 actions 里的默认运行器
        self.pin_mode = "unknown"
        self._reading = False
        self.missions: Sequence[Any] = ()
        self.project_ids: Sequence[str] = ()
        self._jobs: list[QThread] = []
        self.page = DecisionsPage(on_copy, self.preview)
        self.page.run_requested.connect(self.run_decision)

    # ------------------------------------------------ 拼命令（对话框实时调）

    def preview(self, decision: decisions.Decision, target: decisions.Target, values: Mapping[str, str],
                approver: str, pin_enforced: bool) -> str:
        args = decisions.build_args(decision, target, values, approver=approver, pin_enforced=pin_enforced, now=self.now())
        return decisions.shown_command(args)

    # ------------------------------------------------ 读

    def refresh(self, project_ids: Sequence[str], missions: Sequence[Any]) -> None:
        self.project_ids, self.missions = tuple(project_ids), tuple(missions)
        if self._reading:  # 上一轮还没读完：不叠起新的一批命令，读完后页面用的就是上一轮读到的
            return
        self._reading = True
        self._spawn(self._read_all, self._read_done)

    def _read_all(self) -> tuple[
        str, dict[str, list[decisions.Target]], dict[str, list[decisions.Target]], list[decisions.ReadFailure]
    ]:
        extra: dict[str, Any] = {"runner": self.runner} if self.runner else {}
        failures: list[decisions.ReadFailure] = []

        def read(label: str, args: Sequence[str], key: str | None) -> actions.Receipt:
            got = actions.run_cli(self.root, label, args, **extra)
            bad = _read_failure(label, got, key)
            if bad is not None:  # 没读成就记下来，页面写“没读到”；不能当成“没有”
                failures.append(bad)
            return got

        got = read("口令状态", ("pm", "approver-pin", "status"), None)
        pin = decisions.parse_pin_status(got.stdout) if got.rc == 0 else "unknown"
        pending: dict[str, list[decisions.Target]] = {}
        inbox: dict[str, list[decisions.Target]] = {}
        for pid in self.project_ids:
            got = read(f"读待批准范围卡 {pid}", (*decisions.READ_ONLY_COMMANDS["pending"], pid), "cards")
            pending[pid] = decisions.parse_pending(got.stdout, pid) if got.rc == 0 else []
            got = read(f"读收件箱 {pid}", (*decisions.READ_ONLY_COMMANDS["inbox"], pid), "items")
            inbox[pid] = decisions.parse_inbox(got.stdout, pid) if got.rc == 0 else []
        return pin, pending, inbox, failures

    def _failed(self, label: str, error: Exception) -> None:
        self.page.add_receipt(actions.Receipt(self.now().strftime("%H:%M"), label, "(未运行)", 1, False, f"{type(error).__name__}: {error}"))

    def _read_done(self, result: Any) -> None:
        self._reading = False
        if isinstance(result, Exception):
            self._failed("读决定页数据", result)
            return
        pin, pending, inbox, failures = result
        self.pin_mode = pin
        vm = decisions.build_vm(self.missions, pending, inbox, pin, failures=failures)
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

    def _run_done(self, receipt: actions.Receipt | Exception) -> None:
        if isinstance(receipt, Exception):
            self._failed("运行决定", receipt)
            return
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
