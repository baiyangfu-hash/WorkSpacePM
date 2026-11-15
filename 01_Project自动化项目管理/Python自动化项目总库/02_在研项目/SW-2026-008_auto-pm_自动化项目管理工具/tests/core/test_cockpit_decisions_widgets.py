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


# ---------------------------------------------------------------- 启动器横幅在 stderr：只解析 stdout（试用 11-01 决定页“都是空的”）

LAUNCHER_BANNER = "launcher: release verified via active_release.json: C:/ws/00_Infrastructure/auto_pm/releases/1.3.3-6a9f127\n"


class BannerCli(BrokenReads):
    """真实形状：数据在 stdout，每条命令的 stderr 都带一行启动器横幅。"""

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        done = super().__call__(command, **kwargs)
        return subprocess.CompletedProcess(command, done.returncode, done.stdout, (done.stderr or "") + LAUNCHER_BANNER)


def test_banner_on_stderr_does_not_blank_the_page(qapp: QApplication, tmp_path: Path) -> None:
    fake = BannerCli()
    fake.pending_out = json.dumps(
        {"cards": [{"card": {"request_id": "R1", "plan_hash": "h" * 64}, "objective": "改 IO 表", "superseded": False}]}, indent=2
    )
    controller = _read(qapp, tmp_path, fake)
    assert controller.page.vm.failures == ()
    assert controller.pin_mode == "off"
    assert any("改 IO 表" in t for t in _texts(controller.page, QLabel))
    assert EMPTY_TEXT not in _texts(controller.page, QLabel)


def test_only_stdout_is_parsed_never_stderr(qapp: QApplication, tmp_path: Path) -> None:
    """stdout 是真正的“没有”，stderr 里恰好有一段像数据的 JSON：不许当数据读。"""

    class Noisy(BrokenReads):
        def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            done = super().__call__(command, **kwargs)
            stray = json.dumps({"cards": [{"card": {"request_id": "X9", "plan_hash": "z" * 64}, "objective": "杂音"}]})
            return subprocess.CompletedProcess(command, done.returncode, done.stdout, stray)

    controller = _read(qapp, tmp_path, Noisy())
    assert not any("杂音" in t for t in _texts(controller.page, QLabel))
    assert EMPTY_TEXT in _texts(controller.page, QLabel)


def test_failed_read_shows_stderr_not_the_banner_only(qapp: QApplication, tmp_path: Path) -> None:
    fake = BannerCli()
    fake.pending_rc, fake.pending_out = 1, ""
    controller = _read(qapp, tmp_path, fake)
    assert [(f.what, f.rc_text) for f in controller.page.vm.failures] == [("读待批准范围卡 DJ-1", "rc 1")]


# ---------------------------------------------------------------- 审计 534 存活变异：读不懂也要说“没读到”


def test_unreadable_pin_status_shows_a_read_failure_bar(qapp: QApplication, tmp_path: Path) -> None:
    """口令状态命令退出码 0、第一行却认不出：页面除了写“口令状态未知”，还要有“没读到”红条（原先没有）。"""
    controller = _read(qapp, tmp_path, FakeCli(pin_text="完全认不出的一行输出\n第二行"))
    assert controller.pin_mode == "unknown"
    assert [(f.what, f.rc_text) for f in controller.page.vm.failures] == [("口令状态", "输出读不懂")]
    assert "第二行" in controller.page.vm.failures[0].detail  # 红条引输出的末行
    assert len(_failure_bars(controller)) == 1


@pytest.mark.parametrize("body", [{"cards": {"x": 1}}, {"cards": "none"}, {"cards": None}, {"cards": 3}, {"other": []}])
def test_a_cards_value_that_is_not_a_list_is_not_a_successful_read(qapp: QApplication, tmp_path: Path, body: dict[str, object]) -> None:
    fake = BrokenReads()
    fake.pending_out = json.dumps(body)
    controller = _read(qapp, tmp_path, fake)
    assert [(f.what, f.rc_text) for f in controller.page.vm.failures] == [("读待批准范围卡 DJ-1", "输出读不懂")]
    assert EMPTY_TEXT not in _texts(controller.page, QLabel)  # 没读懂不能说“没有要你决定的事”


@pytest.mark.parametrize("body", [{"items": {"x": 1}}, {"items": "none"}, {"items": None}])
def test_an_items_value_that_is_not_a_list_is_not_a_successful_read(qapp: QApplication, tmp_path: Path, body: dict[str, object]) -> None:
    fake = BrokenReads()
    fake.inbox_out = json.dumps(body)
    controller = _read(qapp, tmp_path, fake)
    assert [(f.what, f.rc_text) for f in controller.page.vm.failures] == [("读收件箱 DJ-1", "输出读不懂")]


class StderrOnlyJson(BrokenReads):
    """退出码 0、stdout 是空的，数据样子的 JSON 只出现在 stderr：真实命令不会这样，出现了就是没读对。"""

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        done = super().__call__(command, **kwargs)
        if command[3:5] == ["pm", "pending"]:
            stray = json.dumps({"cards": [{"card": {"request_id": "X9", "plan_hash": "z" * 64}, "objective": "杂音"}]})
            return subprocess.CompletedProcess(command, 0, "", stray)
        return done


def test_json_shaped_text_on_stderr_is_neither_data_nor_a_successful_read(qapp: QApplication, tmp_path: Path) -> None:
    """判读和取数必须用同一份文字：stdout 空、stderr 有像数据的 JSON → 不当数据，也不能判“读成功”再显示“没有”。"""
    controller = _read(qapp, tmp_path, StderrOnlyJson())
    texts = _texts(controller.page, QLabel)
    assert not any("杂音" in t for t in texts)
    assert [(f.what, f.rc_text) for f in controller.page.vm.failures] == [("读待批准范围卡 DJ-1", "输出读不懂")]
    assert "X9" in controller.page.vm.failures[0].detail  # 红条的原文用 stderr 末行，不是空白
    assert EMPTY_TEXT not in texts


def test_stdout_data_wins_over_a_different_json_on_stderr(qapp: QApplication, tmp_path: Path) -> None:
    class Both(BrokenReads):
        def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            done = super().__call__(command, **kwargs)
            if command[3:5] == ["pm", "pending"]:
                stray = json.dumps({"cards": [{"card": {"request_id": "X9", "plan_hash": "z" * 64}, "objective": "杂音"}]})
                return subprocess.CompletedProcess(command, 0, done.stdout, stray)
            return done

    fake = Both()
    fake.pending_out = json.dumps({"cards": [{"card": {"request_id": "R1", "plan_hash": "h" * 64}, "objective": "真数据"}]})
    controller = _read(qapp, tmp_path, fake)
    texts = _texts(controller.page, QLabel)
    assert any("真数据" in t for t in texts) and not any("杂音" in t for t in texts)
    assert controller.page.vm.failures == ()


# ---------------------------------------------------------------- 项目生命周期：探测、预演、确认（CHG-SCPT-2026-654）

from cockpit_board import decision_controller as controller_module  # noqa: E402
from PySide6.QtWidgets import QComboBox, QDialog, QLineEdit, QTextEdit  # noqa: E402

DRY_PASS = ("归档前的五项检查（项目 DJ-1）：\n  [通过] 卡全关\n  [通过] 收口走完\n将要改的那一行：DJ-1 状态 在研 → 已归档\n"
            "预演（没加 --confirm）：什么都没改。要真的归档，请用户本人加 --confirm 再运行。\n")
DRY_BLOCKED = ("归档前的五项检查（项目 DJ-1）：\n  [不过] 卡全关\n      - M-0007 还开着\n      先把这张卡收口或作废\n"
               "拒绝: 项目 DJ-1 现在不能归档，先处理下面的事：\n  - M-0007 还开着\n")
HELP_WITH_KIND = "Usage: main.py project register [OPTIONS] PROJECT_ID\n  --path TEXT\n  --kind [equipment|library|test|tool]\n  --dry-run\n"
HELP_WITHOUT_KIND = "Usage: main.py project register [OPTIONS] PROJECT_ID\n  --path TEXT\n  --dry-run\n"


class LifecycleCli(FakeCli):
    """在 FakeCli 上加 project 这一组：--help 探测、预演、确认；记下每次调用带的环境变量。"""

    def __init__(self, *, missing: tuple[str, ...] = (), help_kind: bool = True, dry_rc: int = 0, dry_out: str = DRY_PASS,
                 timeout: bool = False, pin_text: str = "批准口令：未生效（Git HEAD 里没有 x），批准只做格式检查") -> None:
        super().__init__(pin_text=pin_text)
        self.missing, self.help_kind, self.dry_rc, self.dry_out, self.timeout = missing, help_kind, dry_rc, dry_out, timeout
        self.envs: list[dict[str, str]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        args = command[3:]
        if args[:1] != ["project"]:
            self.envs.append(dict(kwargs.get("env") or {}))
            return super().__call__(command, **kwargs)
        self.calls.append(args)
        self.envs.append(dict(kwargs.get("env") or {}))
        if "--help" in args:
            if self.timeout:
                raise subprocess.TimeoutExpired(command, 30)
            if args[1] in self.missing:
                return subprocess.CompletedProcess(command, 2, "", f"Usage: main.py project [OPTIONS] COMMAND [ARGS]...\nError: No such command '{args[1]}'.")
            text = (HELP_WITH_KIND if self.help_kind else HELP_WITHOUT_KIND) if args[1] == "register" else f"Usage: main.py project {args[1]} [OPTIONS] PROJECT_ID"
            return subprocess.CompletedProcess(command, 0, text, "launcher: release verified via manifest")
        if "--confirm" in args:
            return subprocess.CompletedProcess(command, self.write_rc, self.write_out, "")
        return subprocess.CompletedProcess(command, self.dry_rc, self.dry_out, "")


def _lifecycle(tmp_path: Path, fake: LifecycleCli, changed: list[int] | None = None) -> DecisionController:
    return DecisionController(tmp_path, lambda _t: None, lambda: (changed if changed is not None else []).append(1), runner=fake, now=lambda: NOW)


def _dry(controller: DecisionController, qapp: QApplication, key: str = "archive", project_id: str = "DJ-1") -> Any:
    got: list[Any] = []
    controller.dry_run(key, project_id, got.append)
    _wait(controller, qapp)
    assert len(got) == 1
    return got[0]


def test_probe_runs_three_help_commands_once_and_everything_lights_up(qapp: QApplication, tmp_path: Path) -> None:
    fake, told = LifecycleCli(), []
    controller = _lifecycle(tmp_path, fake)
    controller.lifecycle_listeners.append(lambda: told.append(1))
    assert controller.lifecycle_available("archive") == (False, controller_module.PROBING_TEXT)  # 还没探测：不亮
    assert controller.register_kind() == (False, controller_module.PROBING_TEXT)
    controller.probe_lifecycle()
    controller.probe_lifecycle()  # 正在探测：不叠第二轮
    _wait(controller, qapp)
    assert fake.calls == [["project", "archive", "--help"], ["project", "reactivate", "--help"], ["project", "register", "--help"]]
    assert told == [1]
    assert controller.lifecycle_available("archive") == (True, "") and controller.lifecycle_available("reactivate") == (True, "")
    assert controller.register_kind() == (True, "")
    controller.probe_lifecycle()  # 探测过了：这个窗口里记着，不再起
    _wait(controller, qapp)
    assert len(fake.calls) == 3
    controller.reset_lifecycle_probe()  # 点“重新读取”：忘掉，重探
    assert controller.lifecycle_available("archive") == (False, controller_module.PROBING_TEXT) and told == [1, 1]
    controller.probe_lifecycle()
    _wait(controller, qapp)
    assert len(fake.calls) == 6 and controller.lifecycle_available("archive") == (True, "")


def test_a_missing_command_keeps_its_button_grey_with_the_old_release_sentence(qapp: QApplication, tmp_path: Path) -> None:
    """验收第 8 条：--help 报 No such command → 灰着，旁边是“本机发布版太旧”那句；另一条有的命令照常亮。"""
    controller = _lifecycle(tmp_path, LifecycleCli(missing=("archive", "reactivate")))
    controller.probe_lifecycle()
    _wait(controller, qapp)
    for key in ("archive", "reactivate"):
        ok, reason = controller.lifecycle_available(key)
        assert not ok and reason.startswith(actions.READ_TEXT["missing_command"]) and "本机发布版太旧：没有这条命令" in reason
    assert controller.register_kind() == (True, "")
    only_one = _lifecycle(tmp_path, LifecycleCli(missing=("reactivate",)))
    only_one.probe_lifecycle()
    _wait(only_one, qapp)
    assert only_one.lifecycle_available("archive") == (True, "") and not only_one.lifecycle_available("reactivate")[0]


def test_register_without_the_kind_option_greys_the_kind_field(qapp: QApplication, tmp_path: Path) -> None:
    controller = _lifecycle(tmp_path, LifecycleCli(help_kind=False))
    controller.probe_lifecycle()
    _wait(controller, qapp)
    assert controller.register_kind() == (False, "发版切换后可填；现在登记后显示‘未分类’")
    assert controller.lifecycle_available("archive") == (True, "")


def test_a_probe_that_times_out_or_cannot_start_is_never_taken_as_available(qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _lifecycle(tmp_path, LifecycleCli(timeout=True))
    controller.probe_lifecycle()
    _wait(controller, qapp)
    for ok, reason in (controller.lifecycle_available("archive"), controller.lifecycle_available("reactivate"), controller.register_kind()):
        assert not ok and reason.startswith(controller_module.PROBE_FAILED_PREFIX) and "超时" in reason

    def broken(command: list[str], **_kwargs: Any) -> Any:
        raise OSError("没有这个解释器")

    spawn = DecisionController(tmp_path, lambda _t: None, lambda: None, runner=broken, now=lambda: NOW)
    spawn.probe_lifecycle()
    _wait(spawn, qapp)
    ok, reason = spawn.lifecycle_available("archive")
    assert not ok and "命令没起来" in reason and "没有这个解释器" in reason
    # 没给假的运行器、控制根里又没有 main.py：一定起不来，不起进程，照实记“没读成”
    monkeypatch.setattr(actions, "run_read", lambda *_a, **_k: pytest.fail("不该起进程"))
    bare = DecisionController(tmp_path, lambda _t: None, lambda: None, now=lambda: NOW)
    bare.probe_lifecycle()
    assert bare._jobs == []
    ok, reason = bare.lifecycle_available("archive")
    assert not ok and controller_module.NO_ENTRY_TEXT in reason and bare.register_kind()[0] is False


def test_dry_run_is_the_bare_command_and_a_pass_needs_the_sentence(qapp: QApplication, tmp_path: Path) -> None:
    """验收第 4 条：点“归档…”起的命令里没有 --confirm，也没有 --approval-evidence-ref。"""
    fake = LifecycleCli()
    controller = _lifecycle(tmp_path, fake)
    run = _dry(controller, qapp)
    assert fake.calls == [["pm", "approver-pin", "status"], ["project", "archive", "DJ-1"]]
    assert not any(word in call for call in fake.calls for word in ("--confirm", "--approval-evidence-ref", "--apply"))
    assert (run.key, run.project_id, run.passed, run.receipt.rc) == ("archive", "DJ-1", True, 0)
    assert run.receipt.output == DRY_PASS and run.receipt.action == "归档预演"
    assert controller.pin_mode == "off" and controller.page.receipts[-1] is run.receipt
    again = _dry(controller, qapp, "reactivate", "DJ-2")
    assert fake.calls[2:] == [["project", "reactivate", "DJ-2"]] and again.receipt.action == "重新激活预演"  # 口令状态读过了，不再读


def test_a_blocked_dry_run_does_not_pass_and_is_not_painted_as_a_failed_decision(qapp: QApplication, tmp_path: Path) -> None:
    controller = _lifecycle(tmp_path, LifecycleCli(dry_rc=1, dry_out=DRY_BLOCKED))
    run = _dry(controller, qapp)
    assert not run.passed and run.receipt.rc == 1 and run.receipt.output == DRY_BLOCKED  # 输出一行不少
    assert controller.page.failure is None and controller.page.receipts[-1] is run.receipt
    silent = _lifecycle(tmp_path, LifecycleCli(dry_rc=0, dry_out="将要改的那一行：…\n"))  # 退出码 0 但没有那一句：也不算通过
    assert not _dry(silent, qapp).passed
    refused: list[Any] = []
    controller.dry_run("archive", "--confirm", refused.append)  # 项目号不合格：不起任何命令
    assert len(refused) == 1 and not refused[0].passed and refused[0].receipt.command == "(未运行)"


def test_confirm_dialog_shows_the_whole_command_and_has_no_place_to_type(qapp: QApplication, tmp_path: Path) -> None:
    """验收第 6 条：口令没启用 → “确认并运行”，凭据是 gui-click 开头；确认框里没有任何输入框（没有口令框，也没有预填的用户原话）。"""
    controller = _lifecycle(tmp_path, LifecycleCli())
    run = _dry(controller, qapp)
    dialog = controller.confirm_project(run, "DJ-1 上料机", lambda _r: None, execute=False)
    assert dialog.run_button.text() == "确认并运行" and not dialog.via_terminal and dialog.run_button.isEnabled()
    assert dialog.command_text.startswith("main.py project archive DJ-1 --confirm --approval-evidence-ref user-confirmation:gui-click-")
    assert dialog.command_label.text() == dialog.command_text
    for kind in (QLineEdit, QPlainTextEdit, QTextEdit, QComboBox):
        assert dialog.findChildren(kind) == [], kind.__name__
    assert dialog.inputs == {} and dialog.values() == {}
    labels = [str(w.text()) for w in dialog.findChildren(QLabel)]
    assert "确认归档" in labels and "DJ-1 上料机" in labels
    assert {str(b.text()) for b in dialog.findChildren(QPushButton)} == {"复制命令", "取消", "确认并运行"}


def test_with_a_live_pin_the_dialog_only_offers_the_terminal_and_the_board_takes_no_password(
        qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """验收第 6 条：口令启用时确认框里只有“在终端窗口里运行”，起的是 open_console；没有任何能输口令的输入框。"""
    fake = LifecycleCli(pin_text="批准口令：已生效；批准人 baiyang（ab12cd34）")
    opened: list[Any] = []

    def fake_console(_root: Path, label: str, args: Any, **_k: Any) -> actions.Receipt:
        opened.append((label, list(args)))
        return actions.Receipt("13:40", label, "cmd", None, False, "已在新的终端窗口打开")

    monkeypatch.setattr(actions, "open_console", fake_console)
    monkeypatch.setattr(ConfirmDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)
    changed: list[int] = []
    controller = _lifecycle(tmp_path, fake, changed)
    run = _dry(controller, qapp, "reactivate")
    assert controller.pin_mode == "enforced"  # 预演时顺带读到的口令状态
    got: list[actions.Receipt] = []
    dialog = controller.confirm_project(run, "", got.append)
    _wait(controller, qapp)
    assert dialog.via_terminal and {str(b.text()) for b in dialog.findChildren(QPushButton)} == {"复制命令", "取消", "在终端窗口里运行"}
    for kind in (QLineEdit, QPlainTextEdit, QTextEdit):
        assert dialog.findChildren(kind) == [], kind.__name__
    assert len(opened) == 1 and opened[0][0] == "确认重新激活"
    assert opened[0][1][:5] == ["project", "reactivate", "DJ-1", "--confirm", "--approval-evidence-ref"]
    assert not any("--confirm" in call for call in fake.calls)  # 没有在后台悄悄再跑一遍
    assert len(got) == 1 and got[0].rc is None and changed == []  # 终端里的结果界面看不到：不当成成功，不自动重读


def test_confirm_runs_the_recorded_project_and_shows_the_receipt_on_both_pages(
        qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ConfirmDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)
    fake = LifecycleCli()
    changed: list[int] = []
    fake.write_out = "项目已归档: DJ-1"
    controller = _lifecycle(tmp_path, fake, changed)
    run = _dry(controller, qapp)
    got: list[actions.Receipt] = []
    controller.confirm_project(run, "DJ-1 上料机", got.append)
    _wait(controller, qapp)
    confirm = fake.calls[-1]
    assert confirm[:5] == ["project", "archive", "DJ-1", "--confirm", "--approval-evidence-ref"]
    assert confirm[5].startswith("user-confirmation:gui-click-") and len(confirm) == 6
    assert len(got) == 1 and got[0].rc == 0 and controller.page.receipts[-1] is got[0] and changed == [1]
    fake.write_rc, fake.write_out = 1, "拒绝: 归档项目只听用户本人，当前环境带 agent 标记（CLAUDECODE）。"
    controller.confirm_project(_dry(controller, qapp), "", got.append)
    _wait(controller, qapp)
    assert got[-1].rc == 1 and "agent 标记" in got[-1].output and changed == [1]  # 命令自己拒绝：回执照实显示，不重读
    assert controller.page.failure is got[-1]


def test_cancelling_the_dialog_runs_nothing(qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ConfirmDialog, "exec", lambda _self: QDialog.DialogCode.Rejected)
    fake = LifecycleCli()
    controller = _lifecycle(tmp_path, fake)
    got: list[actions.Receipt] = []
    controller.confirm_project(_dry(controller, qapp), "", got.append)
    _wait(controller, qapp)
    assert got == [] and not any("--confirm" in call for call in fake.calls)


def test_dry_run_passes_the_agent_markers_through_untouched_and_the_board_refuses_the_confirm(
        qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """验收第 7 条：子进程的环境里 AUTO_PM_AGENT、CLAUDECODE 都在、值没变，看板不替命令摘掉 agent 标记。
    M8 的 8.1 起：带标记打开的看板，“确认归档”这种只许你本人点的按钮看板自己就不运行（确认框的确认键灰着，控制器再拦一道）。"""
    monkeypatch.setenv("AUTO_PM_AGENT", "trae:cn")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CODEX_SANDBOX", "seatbelt")
    monkeypatch.setattr(ConfirmDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)
    fake = LifecycleCli()
    controller = _lifecycle(tmp_path, fake)
    controller.probe_lifecycle()
    _wait(controller, qapp)
    got: list[actions.Receipt] = []
    dialog = controller.confirm_project(_dry(controller, qapp), "", got.append)
    _wait(controller, qapp)
    assert len(fake.envs) == 5  # 三条探测、口令状态、预演；确认没有起进程
    assert not any("--confirm" in call for call in fake.calls)
    assert not dialog.run_button.isEnabled() and "AUTO_PM_AGENT" in dialog.blocked
    assert got and got[-1].command == "(未运行)" and got[-1].rc == 1
    for env in fake.envs:
        assert (env["AUTO_PM_AGENT"], env["CLAUDECODE"], env["CODEX_SANDBOX"]) == ("trae:cn", "1", "seatbelt")
        extra = {"PYTHONUTF8", "PYTHONIOENCODING"}
        assert {k: v for k, v in env.items() if k not in extra} == {k: v for k, v in os.environ.items() if k not in extra}


def test_the_users_own_board_started_like_the_bat_can_read_the_markers_and_is_not_locked_out(tmp_path: Path) -> None:
    """你本人双击 bat：新进程、sys.path 里只有 scripts 目录、环境里没有任何 AI 标记。看板要认得出“这是人”（返回空），不能落进“认不出”。"""
    from auto_pm.application.core.lease_handover_service import AGENT_MARKERS

    env = {k: v for k, v in os.environ.items() if k not in AGENT_MARKERS and k != "PYTHONPATH"}
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from cockpit_board import actions, decisions; "
            "m = actions.board_agent_markers(); print(repr(m)); print(repr(decisions.human_only_block(m)))")
    # -I 会忽略 PYTHONUTF8、PYTHONIOENCODING，子进程按系统代码页输出（中文 Windows 是 GBK）；第二次的第二行是中文，
    # 父进程按 utf-8 读就读不出来。所以用 -X utf8 让子进程也按 utf-8 输出（命令行开关，-I 不忽略它）。
    argv = [sys.executable, "-I", "-X", "utf8", "-c", code, str(SCRIPTS)]
    done = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["()", "''"]
    env["CLAUDECODE"] = "1"  # 同样的启动方式，AI 会话拉起的：认得出是 AI
    done = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[0] == "('CLAUDECODE',)"


# ---------------------------------------------------------------- 变更单的两个按钮（M8 的 8.1）


def _order(change_id: str, status: str) -> Any:
    return SimpleNamespace(change_id=change_id, domain="SCPT", what="改 IO 表", status=status, raised="2026-11-13")


CHANGES = [("SW-2026-008", _order("CHG-SCPT-2026-700", "under_review")), ("SW-2026-008", _order("CHG-SCPT-2026-701", "accepting")),
           ("SW-2026-008", _order("CHG-SCPT-2026-702", "draft"))]


def _change_buttons(page: DecisionsPage) -> dict[str, QPushButton]:
    return {str(b.property("decision")): b for b in page.findChildren(QPushButton) if str(b.property("decision")).startswith("change_")}


def test_change_cards_are_drawn_with_their_buttons_and_the_not_yet_line(qapp: QApplication) -> None:
    page = DecisionsPage(lambda _t: None, _preview)
    page.show_view(decisions.build_vm([], {}, {}, "off", changes=CHANGES))
    buttons = _change_buttons(page)
    assert {k: (b.text(), b.isEnabled()) for k, b in buttons.items()} == {
        "change_approve": ("批准变更单", True), "change_complete": ("推到完成", True)}
    labels = " ".join(_texts(page, QLabel))
    assert "CHG-SCPT-2026-700" in labels and "另有 1 张变更单还是草稿或已提交" in labels
    assert set(_texts(page, QPushButton)) <= decisions.DECISION_BUTTONS
    for word in decisions.NEVER_WORDS:
        assert word not in (labels + " ".join(_texts(page, QPushButton))).lower()


def test_change_buttons_are_grey_with_the_reason_when_an_agent_session_opened_the_board(qapp: QApplication) -> None:
    page = DecisionsPage(lambda _t: None, _preview)
    reason = decisions.human_only_block(("CLAUDECODE",))
    page.show_view(decisions.build_vm([_mission("M4", "ACCEPTED", "已关")], {}, {}, "off", changes=CHANGES, human_only_block=reason))
    assert [b.isEnabled() for b in _change_buttons(page).values()] == [False, False]
    assert _texts(page, QLabel).count(reason) == 2  # 每张变更单卡上都写原因
    close = next(b for b in page.findChildren(QPushButton) if b.property("decision") == "close")
    assert close.isEnabled()  # 别的按钮照旧


def test_complete_dialog_comes_prefilled_and_blocks_when_the_conclusion_is_cleared(qapp: QApplication) -> None:
    page = DecisionsPage(lambda _t: None, _preview)
    page.approver_input.setText("baiyang")
    target = decisions.Target(project_id="SW-2026-008", change_id="CHG-SCPT-2026-701", title="CHG-SCPT-2026-701 改 IO 表")
    dialog = page.open_dialog(decisions.BY_KEY["change_complete"], target, run=False)
    assert dialog.values() == {"verification_conclusion": "全部通过"} and dialog.run_button.isEnabled()
    assert "change transition CHG-SCPT-2026-701 --to completed --pid SW-2026-008 --approver baiyang" in dialog.command_label.text()
    assert dialog.command_label.text().endswith('--verification-conclusion "全部通过"')
    _fill(dialog, "verification_conclusion", "")
    assert not dialog.run_button.isEnabled() and "验证结论" in dialog.problem.text()
    approve = page.open_dialog(decisions.BY_KEY["change_approve"], target, run=False)
    assert approve.run_button.isEnabled() and "--to approved" in approve.command_label.text()
    page.approver_input.setText("")
    assert "批准人" in page.open_dialog(decisions.BY_KEY["change_approve"], target, run=False).problem.text()


def test_controller_runs_the_change_command_for_a_human_and_refuses_for_an_agent_session(qapp: QApplication, tmp_path: Path) -> None:
    fake, changed = FakeCli(), []
    human = DecisionController(tmp_path, lambda _t: None, lambda: changed.append(1), runner=fake, now=lambda: NOW, markers=lambda: ())
    human.page.approver_input.setText("baiyang")
    human.refresh([], [], CHANGES)
    _wait(human, qapp)
    card = next(c for c in human.page.vm.cards if c.target.change_id == "CHG-SCPT-2026-700")
    assert card.blocked == "" and [c.column for c in human.page.vm.cards] == ["变更单", "变更单"]
    human.page.run_requested.emit(decisions.BY_KEY["change_approve"], card.target, {"comment": ""}, False)
    _wait(human, qapp)
    ran = next(c for c in fake.calls if c[:2] == ["change", "transition"])
    assert ran[2:5] == ["CHG-SCPT-2026-700", "--to", "approved"] and ran[ran.index("--approver") + 1] == "baiyang"
    assert ran[ran.index("--approval-evidence-ref") + 1].startswith("user-confirmation:gui-click-") and changed == [1]

    for markers in (("CLAUDECODE",), None):  # 带 AI 标记；认不出带没带
        fake2 = FakeCli()
        changed2: list[int] = []
        agent = DecisionController(tmp_path, lambda _t: None, lambda c=changed2: c.append(1), runner=fake2, now=lambda: NOW,
                                   markers=lambda m=markers: m)
        agent.page.approver_input.setText("baiyang")
        agent.refresh([], [], CHANGES)
        _wait(agent, qapp)
        assert all(c.blocked for c in agent.page.vm.cards) and not any(b.isEnabled() for b in _change_buttons(agent.page).values())
        agent.page.run_requested.emit(decisions.BY_KEY["change_approve"], card.target, {"comment": ""}, False)  # 绕过灰按钮直接发信号
        _wait(agent, qapp)
        assert not any(c[:1] == ["change"] for c in fake2.calls) and changed2 == []
        refused = agent.page.receipts[-1]
        assert refused.command == "(未运行)" and refused.rc == 1 and agent.page.failure is refused


def test_the_window_hands_every_projects_change_orders_to_the_decisions_page() -> None:
    from cockpit_board import app as app_module

    seen: list[tuple[list[str], list[Any]]] = []
    stub = SimpleNamespace(changes=(), refresh=lambda ids, missions: seen.append((list(ids), list(missions))))
    order = _order("CHG-PLC-2026-001", "under_review")
    projects = [SimpleNamespace(project_id="DJ-1", missions=[], change_orders=[order]), SimpleNamespace(project_id="DJ-2", missions=[])]
    window = SimpleNamespace(board=SimpleNamespace(projects=projects), home_vm=None, decisions=stub)
    app_module.CockpitWindow._refresh_decisions(window)
    assert stub.changes == (("DJ-1", order),) and seen == [([], [])]  # 没有开着的卡的项目，变更单也照样交过去


def test_every_human_only_button_is_grey_on_an_agent_board_and_the_two_ai_steps_stay_lit(qapp: QApplication) -> None:
    page = DecisionsPage(lambda _t: None, _preview)
    reason = decisions.human_only_block(("AI_AGENT",))
    missions = [_mission("M1", "ACTIVE", "在干"), _mission("M2", "DRAFT", "等你"), _mission("M3", "ACCEPTANCE_PENDING", "等你"),
                _mission("M4", "ACCEPTED", "已关"), _mission("M5", "PARKED", "搁着")]
    scope = decisions.Target(project_id="DJ-1", request_id="R1", plan_hash="h" * 64)
    item = decisions.Target(project_id="DJ-1", item_id="I1", ticket_hash="k" * 64)
    page.show_view(decisions.build_vm(missions, {"DJ-1": [scope]}, {"DJ-1": [item]}, "off", changes=CHANGES, human_only_block=reason))
    drawn = {str(b.property("decision")): b.isEnabled() for b in page.findChildren(QPushButton) if b.property("decision")}
    assert {k for k, lit in drawn.items() if lit} == {"begin_work", "close"}
    assert {k for k, lit in drawn.items() if not lit} == {"approve_card", "inbox_confirm", "inbox_reject", "accept", "park", "unpark",
                                                         "switch", "change_approve", "change_complete"}
    dialog = page.open_dialog(decisions.BY_KEY["accept"], decisions.Target(project_id="DJ-1", mission_id="M3", title="x"), run=False)
    assert not dialog.run_button.isEnabled() and reason in " ".join(str(w.text()) for w in dialog.findChildren(QLabel))
    human = DecisionsPage(lambda _t: None, _preview)
    human.show_view(decisions.build_vm(missions, {"DJ-1": [scope]}, {"DJ-1": [item]}, "off", changes=CHANGES))
    assert all(b.isEnabled() for b in human.findChildren(QPushButton) if b.property("decision"))  # 你本人打开的：全亮
