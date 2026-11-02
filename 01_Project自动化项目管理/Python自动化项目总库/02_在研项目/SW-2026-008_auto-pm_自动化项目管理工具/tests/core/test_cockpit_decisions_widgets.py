"""“决定”页的控件：卡片和按钮、确认对话框、失败横条常驻、控制器端到端（用假的命令运行器，不碰真账本）。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QFrame,
    QLabel,
    QPlainTextEdit,
    QPushButton,
)

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import actions, decisions, theme  # noqa: E402
from cockpit_board.decision_controller import DecisionController  # noqa: E402
from cockpit_board.widgets.decisions import ConfirmDialog, DecisionsPage  # noqa: E402

NOW = datetime(2026, 11, 1, 13, 30, 5)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    app.setStyleSheet(theme.build_qss(theme.LIGHT))
    return app


def _mission(mid: str, state: str, column: str) -> Any:
    return SimpleNamespace(mission_id=mid, project_id="DJ-1", title="标题" + mid, state=state, column=column)


def _preview(decision: decisions.Decision, target: decisions.Target, values: Any, approver: str, pin: bool) -> str:
    return str(decisions.shown_command(decisions.build_args(decision, target, values, approver=approver, pin_enforced=pin, now=NOW)))


def _texts(page: DecisionsPage, kind: type[QLabel] | type[QPushButton]) -> list[str]:
    return [str(w.text()) for w in page.findChildren(kind)]


def _fill(dialog: ConfirmDialog, key: str, text: str) -> None:
    box = dialog.inputs[key]
    if isinstance(box, QPlainTextEdit):
        box.setPlainText(text)
    else:
        box.setText(text)


def test_page_draws_a_button_per_decision_and_only_whitelisted_words(qapp: QApplication) -> None:
    page = DecisionsPage(lambda _t: None, _preview)
    vm = decisions.build_vm([_mission("M1", "ACTIVE", "在干"), _mission("M3", "ACCEPTANCE_PENDING", "等你"),
                             _mission("M4", "ACCEPTED", "已关")], {}, {}, "off")
    page.show_view(vm)
    buttons = _texts(page, QPushButton)
    assert {"搁着", "确认验收", "收口"} <= set(buttons)
    assert set(buttons) <= decisions.DECISION_BUTTONS
    everything = " ".join(_texts(page, QLabel) + buttons)
    for word in decisions.NEVER_WORDS:
        assert word not in everything.lower()


def test_empty_state_says_nothing_is_waiting(qapp: QApplication) -> None:
    page = DecisionsPage(lambda _t: None, _preview)
    page.show_view(decisions.build_vm([], {}, {}, "off"))
    assert "现在没有要你决定的事。" in _texts(page, QLabel)


def test_dialog_shows_the_equivalent_command_and_blocks_until_filled(qapp: QApplication) -> None:
    page = DecisionsPage(lambda _t: None, _preview)
    page.approver_input.setText("baiyang")
    target = decisions.Target(project_id="DJ-1", mission_id="M1", title="标题M1")
    dialog = page.open_dialog(decisions.BY_KEY["park"], target, run=False)
    assert not dialog.run_button.isEnabled() and "还没填" in dialog.problem.text()
    _fill(dialog, "reason", "客户急改")
    _fill(dialog, "summary", "干到第3步")
    assert dialog.run_button.isEnabled()
    assert "pm park --mission-id M1" in dialog.command_label.text()
    assert dialog.run_button.text() == "确认并运行" and not dialog.via_terminal


def test_dialog_switches_to_a_terminal_window_when_the_pin_is_enforced(qapp: QApplication) -> None:
    target = decisions.Target(project_id="DJ-1", mission_id="M3", title="x")
    dialog = ConfirmDialog(decisions.BY_KEY["accept"], target, True, lambda v: "main.py pm accept --mission-id M3", lambda _t: None)
    assert dialog.via_terminal and dialog.run_button.text() == "在终端窗口里运行"
    plain = ConfirmDialog(decisions.BY_KEY["close"], target, True, lambda v: "main.py pm close", lambda _t: None)
    assert not plain.via_terminal and plain.run_button.text() == "确认并运行"  # 收口不问口令


def test_a_failed_command_leaves_a_red_bar_until_the_user_dismisses_it(qapp: QApplication) -> None:
    page = DecisionsPage(lambda _t: None, _preview)
    page.show_view(decisions.build_vm([_mission("M4", "ACCEPTED", "已关")], {}, {}, "off"))
    page.add_receipt(actions.Receipt("13:31", "收口", "main.py pm close --mission-id M4", 1, False, "Error: 隔离工作树在质量验证之后又被改动"))
    bars = [f for f in page.findChildren(QFrame) if f.property("role") == "failure"]
    assert len(bars) == 1 and bars[0].property("sev") == "block"
    assert "隔离工作树在质量验证之后又被改动" in " ".join(_texts(page, QLabel))
    page.show_view(page.vm)  # 刷新页面，横条仍在
    assert any(f.property("role") == "failure" for f in page.findChildren(QFrame))
    page.dismiss_failure()
    assert not any(f.property("role") == "failure" for f in page.findChildren(QFrame))
    assert "Error: 隔离工作树在质量验证之后又被改动" in " ".join(_texts(page, QLabel))  # 记录里仍留着原文


def test_a_success_clears_the_bar_and_keeps_the_record(qapp: QApplication) -> None:
    page = DecisionsPage(lambda _t: None, _preview)
    page.add_receipt(actions.Receipt("13:31", "收口", "main.py pm close", 1, False, "Error: x"))
    page.add_receipt(actions.Receipt("13:32", "收口", "main.py pm close", 0, False, "{}"))
    assert not any(f.property("role") == "failure" for f in page.findChildren(QFrame))
    assert len(page.receipts) == 2


def test_unverified_receipt_is_not_painted_as_failure_or_success(qapp: QApplication) -> None:
    page = DecisionsPage(lambda _t: None, _preview)
    page.add_receipt(actions.Receipt("13:31", "确认验收", "cmd", None, False, "已在新的终端窗口打开"))
    assert not any(f.property("role") == "failure" for f in page.findChildren(QFrame))
    assert "未验证" in " ".join(_texts(page, QLabel))


# ---------------------------------------------------------------- 控制器端到端


class FakeCli:
    """假的命令运行器：按命令内容回话，记下每一次调用。"""

    def __init__(self, pin_text: str = "批准口令：未生效（Git HEAD 里没有 x），批准只做格式检查") -> None:
        self.calls: list[list[str]] = []
        self.pin_text = pin_text
        self.write_rc = 0
        self.write_out = "{}"

    def __call__(self, command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        args = command[3:]
        self.calls.append(args)
        if args[:2] == ["pm", "approver-pin"]:
            return subprocess.CompletedProcess(command, 0, self.pin_text, "")
        if args[:2] == ["pm", "pending"]:
            body = {"cards": [{"card": {"request_id": "R1", "plan_hash": "h" * 64}, "objective": "改 IO 表", "superseded": False}]}
            return subprocess.CompletedProcess(command, 0, json.dumps(body, ensure_ascii=False), "")
        if args[:3] == ["pm", "inbox", "list"]:
            return subprocess.CompletedProcess(command, 0, json.dumps({"items": []}), "")
        return subprocess.CompletedProcess(command, self.write_rc, self.write_out, "")


def _wait(controller: DecisionController, qapp: QApplication) -> None:
    for _ in range(200):
        for job in list(controller._jobs):
            job.wait(2000)
        qapp.processEvents()
        if not controller._jobs:
            break
    qapp.processEvents()


def test_controller_reads_then_runs_the_same_command_and_asks_the_window_to_reload(qapp: QApplication, tmp_path: Path) -> None:
    fake, changed = FakeCli(), []
    controller = DecisionController(tmp_path, lambda _t: None, lambda: changed.append(1), runner=fake, now=lambda: NOW)
    controller.page.approver_input.setText("baiyang")
    controller.refresh(["DJ-1"], [_mission("M4", "ACCEPTED", "已关")])
    _wait(controller, qapp)
    assert [c.column for c in controller.page.vm.cards] == ["范围卡", "已关"]
    scope = controller.page.vm.cards[0]
    controller.page.run_requested.emit(decisions.BY_KEY["approve_card"], scope.target, {"admission_release_ref": ""}, False)
    _wait(controller, qapp)
    approve = next(c for c in fake.calls if c[:2] == ["pm", "approve"])
    assert approve[approve.index("--plan-hash") + 1] == "h" * 64 and "--approver" in approve
    assert approve[approve.index("--approver") + 1] == "baiyang"
    assert changed == [1] and controller.page.receipts[-1].rc == 0


def test_controller_surfaces_a_refusal_and_does_not_reload(qapp: QApplication, tmp_path: Path) -> None:
    fake, changed = FakeCli(), []
    fake.write_rc, fake.write_out = 1, ""
    controller = DecisionController(tmp_path, lambda _t: None, lambda: changed.append(1), runner=fake, now=lambda: NOW)
    controller.refresh(["DJ-1"], [_mission("M4", "ACCEPTED", "已关")])
    _wait(controller, qapp)
    close = next(c for c in controller.page.vm.cards if c.column == "已关")
    controller.page.run_requested.emit(decisions.BY_KEY["close"], close.target, {}, False)
    _wait(controller, qapp)
    assert changed == [] and controller.page.failure is not None and controller.page.failure.rc == 1


def test_controller_learns_the_pin_is_on_when_the_command_says_so(qapp: QApplication, tmp_path: Path) -> None:
    fake = FakeCli()
    fake.write_rc = 1
    fake.write_out = "Error: 已启用批准口令：这一步必须由用户本人在自己的终端运行这条命令并输入口令（当前不是交互终端）"
    controller = DecisionController(tmp_path, lambda _t: None, lambda: None, runner=fake, now=lambda: NOW)
    controller.refresh(["DJ-1"], [_mission("M3", "ACCEPTANCE_PENDING", "等你")])
    _wait(controller, qapp)
    accept = next(c for c in controller.page.vm.cards if c.column == "等你")
    controller.page.run_requested.emit(decisions.BY_KEY["accept"], accept.target, {}, False)
    _wait(controller, qapp)
    assert controller.pin_mode == "enforced"


def test_controller_with_a_live_pin_opens_a_terminal_instead_of_capturing(qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeCli(pin_text="批准口令：已生效；批准人 baiyang（ab12cd34）")
    opened: list[Any] = []

    def fake_console(_root: Path, label: str, args: Any, **_k: Any) -> actions.Receipt:
        opened.append((label, list(args)))
        return actions.Receipt("13:40", label, "cmd", None, False, "已在新的终端窗口打开")

    monkeypatch.setattr(actions, "open_console", fake_console)
    controller = DecisionController(tmp_path, lambda _t: None, lambda: None, runner=fake, now=lambda: NOW)
    controller.refresh(["DJ-1"], [_mission("M3", "ACCEPTANCE_PENDING", "等你")])
    _wait(controller, qapp)
    assert controller.pin_mode == "enforced"
    accept = next(c for c in controller.page.vm.cards if c.column == "等你")
    controller.page.run_requested.emit(decisions.BY_KEY["accept"], accept.target, {}, True)
    _wait(controller, qapp)
    assert opened == [("确认验收", ["pm", "accept", "--mission-id", "M3"])]
    assert not any(c[:2] == ["pm", "accept"] for c in fake.calls)  # 没有在后台悄悄再跑一遍


def test_controller_does_not_stack_reads_and_survives_a_job_that_raises(qapp: QApplication, tmp_path: Path) -> None:
    """#455 预审 514：上一轮没读完不叠新一批；后台任务抛错要显示出来，“读取中”标记不能卡死。"""
    calls: list[list[str]] = []
    boom = {"on": True}

    def runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command[3:])
        if boom["on"]:
            raise RuntimeError("读管道炸了")
        return subprocess.CompletedProcess(command, 0, "{}", "")

    controller = DecisionController(tmp_path, lambda _t: None, lambda: None, runner=runner, now=lambda: NOW)
    controller.refresh(["DJ-1"], [])
    controller.refresh(["DJ-1"], [])  # 第一轮还在读：第二次直接忽略
    _wait(controller, qapp)
    assert controller.page.failure is not None and "读管道炸了" in controller.page.failure.output
    assert controller._reading is False
    boom["on"] = False
    before = len(calls)
    controller.refresh(["DJ-1"], [])  # 出错后能再读
    _wait(controller, qapp)
    assert len(calls) > before


# ---------------------------------------------------------------- 读失败不能显示成“没有”（试用 11-01 决定页空白）


class BrokenReads(FakeCli):
    """只读命令按要求失败：``pending_rc`` / ``pending_out`` 管“读待批准范围卡”，``pin_rc`` 管口令状态。"""

    def __init__(self) -> None:
        super().__init__()
        self.pending_rc, self.pending_out = 0, json.dumps({"cards": []})
        self.inbox_rc, self.inbox_out = 0, json.dumps({"items": []})
        self.pin_rc = 0

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        args = command[3:]
        if args[:2] == ["pm", "approver-pin"] and self.pin_rc:
            self.calls.append(args)
            return subprocess.CompletedProcess(command, self.pin_rc, "", "No such command 'approver-pin'")
        if args[:2] == ["pm", "pending"]:
            self.calls.append(args)
            return subprocess.CompletedProcess(command, self.pending_rc, self.pending_out, "")
        if args[:3] == ["pm", "inbox", "list"]:
            self.calls.append(args)
            return subprocess.CompletedProcess(command, self.inbox_rc, self.inbox_out, "")
        return super().__call__(command, **kwargs)


EMPTY_TEXT = "现在没有要你决定的事。"


def _read(qapp: QApplication, tmp_path: Path, fake: FakeCli) -> DecisionController:
    controller = DecisionController(tmp_path, lambda _t: None, lambda: None, runner=fake, now=lambda: NOW)
    controller.refresh(["DJ-1"], [])
    _wait(controller, qapp)
    return controller


def _failure_bars(controller: DecisionController) -> list[QFrame]:
    return [f for f in controller.page.findChildren(QFrame) if f.property("role") == "read_failure"]


def test_a_real_empty_read_still_says_nothing_to_decide(qapp: QApplication, tmp_path: Path) -> None:
    controller = _read(qapp, tmp_path, BrokenReads())
    assert controller.page.vm.failures == ()
    assert EMPTY_TEXT in _texts(controller.page, QLabel)
    assert not _failure_bars(controller)


def test_a_failed_pending_read_says_not_read_and_never_says_nothing(qapp: QApplication, tmp_path: Path) -> None:
    fake = BrokenReads()
    fake.pending_rc, fake.pending_out = 1, "Error: 未找到命令"
    controller = _read(qapp, tmp_path, fake)
    assert [(f.what, f.rc_text) for f in controller.page.vm.failures] == [("读待批准范围卡 DJ-1", "rc 1")]
    texts = _texts(controller.page, QLabel)
    assert EMPTY_TEXT not in texts  # 读失败时不能说“没有”
    assert any("没读到：读待批准范围卡 DJ-1（rc 1）" in t for t in texts)
    assert any("pm pending" in t for t in texts)  # 带上命令名
    assert len(_failure_bars(controller)) == 1


def test_an_unreadable_inbox_output_with_exit_code_zero_is_also_not_read(qapp: QApplication, tmp_path: Path) -> None:
    fake = BrokenReads()
    fake.inbox_out = "这是旧版的纯文字输出，不是 JSON"
    controller = _read(qapp, tmp_path, fake)
    assert [(f.what, f.rc_text) for f in controller.page.vm.failures] == [("读收件箱 DJ-1", "输出读不懂")]
    assert EMPTY_TEXT not in _texts(controller.page, QLabel)


def test_a_failed_pin_status_read_shows_the_command_and_exit_code(qapp: QApplication, tmp_path: Path) -> None:
    fake = BrokenReads()
    fake.pin_rc = 2
    controller = _read(qapp, tmp_path, fake)
    assert controller.pin_mode == "unknown"
    assert [(f.what, f.rc_text) for f in controller.page.vm.failures] == [("口令状态", "rc 2")]
    texts = _texts(controller.page, QLabel)
    assert any("approver-pin" in t for t in texts) and any("No such command" in t for t in texts)
