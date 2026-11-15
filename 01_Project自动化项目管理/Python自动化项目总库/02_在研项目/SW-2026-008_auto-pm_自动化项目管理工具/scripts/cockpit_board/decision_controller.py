"""“决定”页的接线：读只读命令、拼命令、后台跑、把回执交给页面。

app.py 接这个页面只需要三件事（S0 合并后再动 app.py）：
    controller = DecisionController(root, on_copy, on_changed)   # on_changed：命令成功后让主窗口重新读账本
    stack.addWidget(controller.page)                              # 顶栏加一个“决定”页签
    controller.changes = ...                                      # （项目号, 变更单）；主窗口读完账本后先放这里
    controller.refresh(project_ids, missions)                     # 每次主窗口读完账本后调一次

项目详情页也借用这个控制器（CHG-SCPT-2026-654）：探测本机有没有 project archive / reactivate、register 有没有 --kind
（probe_lifecycle），跑不带 --confirm 的预演（dry_run），弹确认框再运行（confirm_project）。回执两边都显示：
项目详情页的“项目状态”一块，和“决定”页的记录。

本文件不直接起子进程：只调 actions.run_cli / actions.run_read / actions.open_console（整个包里唯一允许起子进程的地方）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QDialog, QWidget

from cockpit_board import actions, decisions
from cockpit_board.widgets.decisions import ConfirmDialog, DecisionsPage

PROBING_TEXT = "正在探测本机有没有这条命令……"
PROBE_FAILED_PREFIX = "没探测成，不当成有这条命令："
NO_ENTRY_TEXT = "控制根里没有 main.py"
REGISTER_KIND_MISSING = "发版切换后可填；现在登记后显示‘未分类’"


@dataclass(frozen=True)
class DryRun:
    """一次预演的结果，和它是哪个项目的绑在一起：确认时项目号取这里记下的，不取页面当时显示的。"""

    key: str  # decisions.LIFECYCLES 的键：archive / reactivate
    project_id: str
    receipt: actions.Receipt
    passed: bool


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
                 runner: Callable[..., Any] | None = None, now: Callable[[], datetime] = datetime.now,
                 markers: Callable[[], Sequence[str] | None] = actions.board_agent_markers) -> None:
        super().__init__()
        self.markers = markers  # 这个看板进程带着哪些 AI 标记；测试注入
        self.root, self.on_copy, self.on_changed, self.now = root, on_copy, on_changed, now
        self.runner = runner  # 测试注入；None 用 actions 里的默认运行器
        self.pin_mode = "unknown"
        self._reading = False
        self.missions: Sequence[Any] = ()
        self.project_ids: Sequence[str] = ()
        self.changes: Sequence[tuple[str, Any]] = ()
        self._jobs: list[QThread] = []
        # 项目生命周期：三条 --help 探测的结果在这个窗口里记着（None＝还没探测）；点“重新读取”才清掉重探
        self.lifecycle_probe: dict[str, actions.ReadOutcome] | None = None
        self._probing = False
        self.lifecycle_listeners: list[Callable[[], None]] = []
        self.last_dialog: ConfirmDialog | None = None
        self.page = DecisionsPage(on_copy, self.preview)
        self.page.run_requested.connect(self.run_decision)

    # ------------------------------------------------ 拼命令（对话框实时调）

    def preview(self, decision: decisions.Decision, target: decisions.Target, values: Mapping[str, str],
                approver: str, pin_enforced: bool) -> str:
        args = decisions.build_args(decision, target, values, approver=approver, pin_enforced=pin_enforced, now=self.now())
        return decisions.shown_command(args)

    # ------------------------------------------------ 读

    def refresh(self, project_ids: Sequence[str], missions: Sequence[Any], changes: Sequence[tuple[str, Any]] | None = None) -> None:
        self.project_ids, self.missions = tuple(project_ids), tuple(missions)
        if changes is not None:  # 不给就用 self.changes 里记着的
            self.changes = tuple(changes)
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
        vm = decisions.build_vm(self.missions, pending, inbox, pin, failures=failures, changes=self.changes,
                                human_only_block=decisions.human_only_block(self.markers()))
        self.page.show_view(vm)

    # ------------------------------------------------ 运行

    def run_decision(self, decision: decisions.Decision, target: decisions.Target, values: Mapping[str, str],
                     via_terminal: bool, on_receipt: Callable[[actions.Receipt], None] | None = None) -> None:
        pin = self.pin_mode == "enforced"
        try:
            blocked = decisions.human_only_block(self.markers()) if decision.human_only else ""
            if blocked:  # 按钮本来就灰着；这里再拦一道，别的入口调进来也不运行
                raise decisions.DecisionError(blocked)
            args = decisions.build_args(decision, target, values, approver=self.page.approver(), pin_enforced=pin, now=self.now())
        except decisions.DecisionError as error:  # 对话框已拦过，这里兜底，不静默
            refused = actions.Receipt(self.now().strftime("%H:%M"), decision.label, "(未运行)", 1, False, str(error))
            self.page.add_receipt(refused)
            if on_receipt is not None:
                on_receipt(refused)
            return
        extra: dict[str, Any] = {"runner": self.runner} if self.runner else {}
        if via_terminal:
            job: Callable[[], Any] = lambda: actions.open_console(self.root, decision.label, args)  # noqa: E731
        else:
            job = lambda: actions.run_cli(self.root, decision.label, args, **extra)  # noqa: E731
        self._spawn(job, self._run_done if on_receipt is None else lambda result: self._run_done(result, on_receipt))

    def _run_done(self, receipt: actions.Receipt | Exception, on_receipt: Callable[[actions.Receipt], None] | None = None) -> None:
        if isinstance(receipt, Exception):
            self._failed("运行决定", receipt)
            return
        self.page.add_receipt(receipt)
        if actions.needs_terminal(receipt):
            self.pin_mode = "enforced"  # 命令说口令已生效：下次点同一个按钮就改走终端窗口
        if on_receipt is not None:  # 项目详情页起的：回执两边都显示
            on_receipt(receipt)
        if receipt.rc == 0:
            self.on_changed()

    # ------------------------------------------------ 项目生命周期（项目详情页、工具页“项目”页签借用）

    def probe_lifecycle(self) -> None:
        """后台探测一次：project archive / reactivate / register 的 --help。探测过（或正在探测）就不再起。"""
        if self.lifecycle_probe is not None or self._probing:
            return
        self._probing = True
        if self.runner is None and not (self.root / "main.py").is_file():  # 连入口都没有，一定起不来：不起进程，照实记“没读成”
            self._probe_done({key: actions.ReadOutcome("spawn_failed", decisions.shown_command(decisions.READ_ONLY_COMMANDS[key]), None,
                                                       detail=NO_ENTRY_TEXT) for key in decisions.LIFECYCLE_PROBES})
            return
        self._spawn(self._probe_all, self._probe_done)

    def _probe_all(self) -> dict[str, actions.ReadOutcome]:
        extra: dict[str, Any] = {"runner": self.runner} if self.runner else {}
        return {key: actions.run_read(self.root, decisions.READ_ONLY_COMMANDS[key], **extra) for key in decisions.LIFECYCLE_PROBES}

    def _probe_done(self, result: Any) -> None:
        self._probing = False
        if isinstance(result, Exception):  # 探测本身出错：每条都记成“没读成”，不当成有这条命令
            detail = f"{type(result).__name__}: {result}"[:120]
            result = {key: actions.ReadOutcome("spawn_failed", decisions.shown_command(decisions.READ_ONLY_COMMANDS[key]), None,
                                               detail=detail) for key in decisions.LIFECYCLE_PROBES}
        self.lifecycle_probe = result
        for listener in list(self.lifecycle_listeners):
            listener()

    def reset_lifecycle_probe(self) -> None:
        """点“重新读取”时调：忘掉探测结果，下次打开项目详情页或“项目”页签时重探。正在探测的那一轮照常记结果。"""
        self.lifecycle_probe = None
        for listener in list(self.lifecycle_listeners):
            listener()

    def _probe_state(self, probe_key: str) -> tuple[actions.ReadOutcome | None, str]:
        """（读到了的那次结果，没读到时给人看的原因）。"""
        if self.lifecycle_probe is None:
            return None, PROBING_TEXT
        outcome = self.lifecycle_probe[probe_key]
        if outcome.kind == "ok":
            return outcome, ""
        if outcome.kind == "missing_command":
            return None, outcome.text  # “本机发布版太旧：没有这条命令（等部署新版本后再看）”
        return None, PROBE_FAILED_PREFIX + outcome.text

    def lifecycle_available(self, key: str) -> tuple[bool, str]:
        """“归档…”“重新激活…”能不能点；不能点时第二项是旁边要写的原因。"""
        outcome, reason = self._probe_state(decisions.LIFECYCLES[key].probe)
        return outcome is not None, reason

    def register_kind(self) -> tuple[bool, str]:
        """登记表单的“性质”能不能填：本机的 project register --help 里有 --kind 才能。"""
        outcome, reason = self._probe_state("project_register_help")
        if outcome is None:
            return False, reason
        if decisions.REGISTER_KIND_OPTION not in outcome.stdout:
            return False, REGISTER_KIND_MISSING
        return True, ""

    def dry_run(self, key: str, project_id: str, done: Callable[[DryRun], None]) -> None:
        """预演：只跑 ``project archive <项目号>`` / ``project reactivate <项目号>``，不带 --confirm，什么都不改。

        口令状态还没读过时顺带读一次（只读命令），好让确认框知道该不该改走终端窗口。
        """
        lifecycle = decisions.LIFECYCLES[key]
        label = lifecycle.dry_label.rstrip("…") + "预演"
        try:
            args = decisions.dry_run_args(key, project_id)
        except decisions.DecisionError as error:
            done(DryRun(key, project_id, actions.Receipt(self.now().strftime("%H:%M"), label, "(未运行)", 1, False, str(error)), False))
            return
        extra: dict[str, Any] = {"runner": self.runner} if self.runner else {}

        def job() -> tuple[str, actions.Receipt]:
            pin = self.pin_mode
            if pin == "unknown":
                got = actions.run_cli(self.root, "口令状态", decisions.READ_ONLY_COMMANDS["pin_status"], timeout=actions.READ_TIMEOUT, **extra)
                pin = decisions.parse_pin_status(got.stdout) if got.rc == 0 else "unknown"
            return pin, actions.run_cli(self.root, label, args, timeout=actions.WRITE_TIMEOUT, **extra)

        def finished(result: Any) -> None:
            if isinstance(result, Exception):
                receipt = actions.Receipt(self.now().strftime("%H:%M"), label, decisions.shown_command(args), None, False,
                                          f"{type(result).__name__}: {result}")
            else:
                self.pin_mode, receipt = result
            self.page.receipts.append(receipt)  # 记进“决定”页的记录；预演不过不是“决定没成功”，不亮那条红条
            self.page.show_view(self.page.vm)
            done(DryRun(key, project_id, receipt, decisions.dry_run_passed(receipt.rc, receipt.output)))

        self._spawn(job, finished)

    def confirm_project(self, run: DryRun, title: str, on_receipt: Callable[[actions.Receipt], None],
                        parent: QWidget | None = None, *, execute: bool = True) -> ConfirmDialog:
        """预演通过后点“确认归档”/“确认重新激活”：弹现成的确认框，里面写着整条命令；项目号取预演记下的那个。

        口令没启用：点“确认并运行”，后台跑；口令已启用：只有“在终端窗口里运行”，口令在那个窗口里输，这里不收。
        """
        decision = decisions.BY_KEY[decisions.LIFECYCLES[run.key].decision]
        target = decisions.Target(project_id=run.project_id, title=title or run.project_id)
        pin = self.pin_mode == "enforced"
        blocked = decisions.human_only_block(self.markers()) if decision.human_only else ""
        dialog = ConfirmDialog(decision, target, pin, lambda values: self.preview(decision, target, values, "", pin), self.on_copy, parent,
                               blocked=blocked)
        self.last_dialog = dialog
        if execute and dialog.exec() == QDialog.DialogCode.Accepted:
            self.run_decision(decision, target, dialog.values(), dialog.via_terminal, on_receipt)
        return dialog

    def _spawn(self, job: Callable[[], Any], done: Callable[[Any], None]) -> None:
        thread = _Job(job, self)
        thread.done.connect(done)
        thread.finished.connect(lambda t=thread: self._jobs.remove(t) if t in self._jobs else None)
        self._jobs.append(thread)
        thread.start()
