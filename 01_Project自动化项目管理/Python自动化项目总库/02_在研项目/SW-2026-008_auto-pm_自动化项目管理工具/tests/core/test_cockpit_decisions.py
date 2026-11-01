"""总控屏“决定”页（S1）：每个按钮背后是哪条命令、命令存不存在、选项对不对、不碰护栏。

纯 Python 部分不需要 Qt；控件部分用离屏 Qt。真正的命令行用 click 的命令树核对选项名，
所以 CLI 改了选项名而按钮没跟着改，这里会红。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click
import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
GUIDE = SCRIPTS / "cockpit_board" / "DECISIONS.md"

from cockpit_board import actions, decisions  # noqa: E402

from auto_pm.contracts.user_evidence import user_evidence_problem  # noqa: E402
from auto_pm.ui.cli.pm import pm_group  # noqa: E402

DECISIONS_ALL = decisions.DECISIONS
NOW = datetime(2026, 11, 1, 13, 30, 5)
TARGET = decisions.Target(project_id="DJ-2026-009", mission_id="M-0001", request_id="REQ-1", plan_hash="a" * 64,
                          item_id="INB-1", ticket_hash="b" * 64, title="改 IO 表")
VALUES = {"reason": "客户急改", "summary": "干到第3步，下一步写 IO", "as_owner": "claude:cloud", "note": "ok",
          "admission_release_ref": ""}


def _args(decision: decisions.Decision, *, pin: bool = False, approver: str = "baiyang", values: dict[str, str] | None = None) -> list[str]:
    return decisions.build_args(decision, TARGET, values or VALUES, approver=approver, pin_enforced=pin, now=NOW)


def _resolve(args: list[str]) -> tuple[click.Command, list[str]]:
    """沿命令树往下找到被调用的那条命令，返回 (命令, 剩下的参数)。"""
    command: click.Command = pm_group
    rest = list(args[1:])  # 第一个词是 pm
    while isinstance(command, click.Group) and rest and not rest[0].startswith("-"):
        sub = command.get_command(click.Context(command), rest[0])
        assert sub is not None, f"命令行里没有 {' '.join(args[:2])}"
        command, rest = sub, rest[1:]
    return command, rest


@pytest.mark.parametrize("decision", decisions.DECISIONS, ids=lambda d: d.key)
def test_every_decision_builds_a_command_the_cli_accepts(decision: decisions.Decision) -> None:
    for pin in (False, True):
        args = _args(decision, pin=pin)
        command, rest = _resolve(args)
        options = {opt for param in command.params if isinstance(param, click.Option) for opt in param.opts}
        used = [item for item in rest if item.startswith("--")]
        assert used, "命令行至少带一个选项"
        for option in used:
            assert option in options, f"{decision.key}: {' '.join(args[:3])} 没有选项 {option}"
        required = {param.opts[0] for param in command.params if isinstance(param, click.Option) and param.required}
        if not (decision.key == "approve_card" and pin):  # 口令生效时批准人和凭据由口令决定，命令也允许不传
            assert required <= set(used) | {a for a in rest if a == "--pid"}, f"{decision.key} 缺必填选项 {required - set(used)}"


def test_decision_keys_are_unique_and_labels_are_whitelisted() -> None:
    keys = [d.key for d in DECISIONS_ALL]
    assert len(keys) == len(set(keys))
    for decision in DECISIONS_ALL:
        assert decision.label in decisions.DECISION_BUTTONS



def test_no_forbidden_word_in_any_button_or_dialog_text() -> None:
    texts = list(decisions.DECISION_BUTTONS)
    for d in DECISIONS_ALL:
        texts += [d.label, d.summary, d.danger] + [f.label + f.hint for f in d.fields]
    for text in texts:
        for word in decisions.NEVER_WORDS:
            assert word not in text.lower(), f"“{text}” 里出现了永远不加的 {word}"


def test_click_evidence_is_accepted_as_the_users_words_and_never_names_an_agent() -> None:
    for d in DECISIONS_ALL:
        evidence = decisions.click_evidence(d.key, "M-0001", NOW)
        assert user_evidence_problem(evidence) == "", evidence
    assert decisions.click_evidence("park", "M-1", NOW) == decisions.click_evidence("park", "M-1", NOW)  # 同一次点击可重放


def test_park_always_carries_the_evidence_so_it_lands_in_parked_not_waiting() -> None:
    args = _args(decisions.BY_KEY["park"])
    assert "--approval-evidence-ref" in args
    assert args[args.index("--approval-evidence-ref") + 1].startswith("user-confirmation:")


def test_approve_card_with_pin_does_not_pass_approver_or_evidence() -> None:
    off = _args(decisions.BY_KEY["approve_card"], pin=False)
    on = _args(decisions.BY_KEY["approve_card"], pin=True, approver="")
    assert "--approver" in off and "--approval-evidence-ref" in off
    assert "--approver" not in on and "--approval-evidence-ref" not in on
    assert on[on.index("--plan-hash") + 1] == "a" * 64  # 批准的是用户看到的那一版


def test_missing_pieces_stop_before_any_command_is_built() -> None:
    with pytest.raises(decisions.DecisionError, match="批准人"):
        _args(decisions.BY_KEY["approve_card"], approver="")
    with pytest.raises(decisions.DecisionError, match="还没填"):
        _args(decisions.BY_KEY["park"], values={"reason": "", "summary": "x"})
    with pytest.raises(decisions.DecisionError, match="任务编号"):
        decisions.build_args(decisions.BY_KEY["close"], decisions.Target(), {}, approver="a", pin_enforced=False, now=NOW)
    with pytest.raises(decisions.DecisionError, match="哈希"):
        decisions.build_args(decisions.BY_KEY["inbox_confirm"], decisions.Target(item_id="I-1"), {}, approver="a",
                             pin_enforced=False, now=NOW)


def test_the_gui_never_builds_a_forbidden_command() -> None:
    for d in DECISIONS_ALL:
        flat = " ".join(_args(d)).lower()
        for banned in ("--no-verify", "--force", "execute", "codex", "--fix", "merge", "delete"):
            assert banned not in flat, (d.key, banned)


def test_shown_command_quotes_spaces() -> None:
    shown = decisions.shown_command(["pm", "park", "--reason", "客户 急改"])
    assert shown == 'main.py pm park --reason "客户 急改"'


# ---------------------------------------------------------------- 读只读命令的输出


def test_parse_pin_status() -> None:
    assert decisions.parse_pin_status("批准口令：已生效；批准人 baiyang（ab12）") == "enforced"
    assert decisions.parse_pin_status("批准口令：未生效（Git HEAD 里没有 x），批准只做格式检查") == "off"
    assert decisions.parse_pin_status("批准口令：所有批准暂停。登记文件未提交") == "suspended"
    assert decisions.parse_pin_status("") == "unknown"
    assert decisions.parse_pin_status("Traceback ...") == "unknown"


def test_parse_pending_skips_superseded_and_broken() -> None:
    text = json.dumps({"cards": [
        {"card": {"request_id": "R1", "plan_hash": "h1"}, "objective": "改 IO", "superseded": False},
        {"card": {"request_id": "R2", "plan_hash": "h2"}, "objective": "旧版", "superseded": True},
        {"card": {"request_id": "", "plan_hash": "h3"}, "objective": "坏的", "superseded": False},
    ]})
    got = decisions.parse_pending(text, "DJ-1")
    assert [(t.request_id, t.plan_hash, t.title) for t in got] == [("R1", "h1", "改 IO")]
    assert decisions.parse_pending("not json", "DJ-1") == []
    assert decisions.parse_pending("[]", "DJ-1") == []


def test_parse_inbox_only_proposed() -> None:
    text = json.dumps({"items": [
        {"item_id": "I1", "ticket_hash": "t1", "title": "加报警", "status": "PROPOSED"},
        {"item_id": "I2", "ticket_hash": "t2", "title": "已确认", "status": "CONFIRMED"},
    ]})
    assert [t.item_id for t in decisions.parse_inbox(text, "DJ-1")] == ["I1"]


# ---------------------------------------------------------------- 版面数据


def _mission(mid: str, state: str, column: str, pid: str = "DJ-1") -> Any:
    return SimpleNamespace(mission_id=mid, project_id=pid, title="标题" + mid, state=state, column=column)


def test_buttons_follow_mission_state() -> None:
    missions = [_mission("M1", "ACTIVE", "在干"), _mission("M2", "PARKED", "搁着"), _mission("M3", "ACCEPTANCE_PENDING", "等你"),
                _mission("M4", "ACCEPTED", "已关"), _mission("M5", "CLOSED", "已关"), _mission("M6", "BLOCKED", "等你"),
                _mission("M7", "DRAFT", "等你")]
    vm = decisions.build_vm(missions, {}, {}, "off")
    by_mission = {c.target.mission_id: [d.key for d in c.decisions] for c in vm.cards}
    assert by_mission["M1"] == ["park"]
    assert by_mission["M2"] == ["unpark", "switch"]
    assert by_mission["M3"] == ["accept"]
    assert by_mission["M4"] == ["close"]
    assert "M5" not in by_mission  # 已收口的不带按钮，免得误点
    assert by_mission["M6"] == ["unpark"]
    assert by_mission["M7"] == ["begin_work", "switch"]  # 同项目有 M1 在干，才有东西可搁，所以出现“插急活”
    assert vm.pin_text.startswith("批准口令：未生效")


def test_switch_is_offered_only_when_something_is_active_in_that_project() -> None:
    parked = _mission("M2", "PARKED", "搁着", "DJ-2")
    assert [d.key for d in decisions.build_vm([parked], {}, {}, "off").cards[0].decisions] == ["unpark"]
    active_elsewhere = [parked, _mission("M1", "ACTIVE", "在干", "DJ-1")]
    assert [d.key for d in decisions.build_vm(active_elsewhere, {}, {}, "off").cards[-1].decisions] == ["unpark"]
    active_same = [parked, _mission("M1", "ACTIVE", "在干", "DJ-2")]
    assert any("switch" in [d.key for d in c.decisions] for c in decisions.build_vm(active_same, {}, {}, "off").cards)


def test_scope_cards_and_inbox_come_first() -> None:
    pending = {"DJ-1": [decisions.Target(project_id="DJ-1", request_id="R1", plan_hash="h" * 20, title="改 IO")]}
    inbox = {"DJ-1": [decisions.Target(project_id="DJ-1", item_id="I1", ticket_hash="t" * 20, title="加报警")]}
    vm = decisions.build_vm([_mission("M1", "ACTIVE", "在干")], pending, inbox, "enforced")
    assert [c.column for c in vm.cards] == ["范围卡", "收件箱", "在干"]
    assert [d.key for d in vm.cards[1].decisions] == ["inbox_confirm", "inbox_reject"]


# ---------------------------------------------------------------- 运行器


def test_run_cli_runs_in_the_control_root_without_stdin_and_keeps_the_exit_code(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(command=command, **kwargs)
        return subprocess.CompletedProcess(command, 2, "", "Error: 租约已过期")

    receipt = actions.run_cli(tmp_path, "收口", ("pm", "close", "--mission-id", "M-1"), runner=runner)
    assert seen["command"][1:] == ["-B", str(tmp_path / "main.py"), "pm", "close", "--mission-id", "M-1"]
    assert seen["cwd"] == str(tmp_path)
    assert seen["stdin"] == subprocess.DEVNULL
    assert "AUTO_PM_AGENT" not in {k for k in seen["env"] if k not in os.environ}  # 不替谁加 agent 标记，也不抹掉
    assert receipt.rc == 2 and "租约已过期" in receipt.output and "pm close --mission-id M-1" in receipt.command


def test_run_cli_reports_unverified_when_it_cannot_start(tmp_path: Path) -> None:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise FileNotFoundError("python")

    receipt = actions.run_cli(tmp_path, "收口", ("pm", "close"), runner=boom)
    assert receipt.rc is None and receipt.rc_text == "未验证" and "FileNotFoundError" in receipt.output


def test_needs_terminal_detects_the_pin_refusal() -> None:
    refused = actions.Receipt("13:30", "批准范围", "x", 1, False, "Error: 已启用批准口令：这一步必须由用户本人在自己的终端运行这条命令并输入口令")
    assert actions.needs_terminal(refused)
    assert not actions.needs_terminal(actions.Receipt("13:30", "x", "x", 1, False, "Error: 别的错"))
    assert not actions.needs_terminal(actions.Receipt("13:30", "x", "x", 0, False, ""))


def test_open_console_off_windows_says_so_and_runs_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions.os, "name", "posix")
    called: list[Any] = []
    receipt = actions.open_console(tmp_path, "批准范围", ("pm", "approve"), opener=lambda *a, **k: called.append(a))
    assert called == [] and receipt.rc is None and "复制" in receipt.output


def test_open_console_on_windows_opens_a_new_console_with_the_same_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions.os, "name", "nt")
    monkeypatch.setattr(actions.subprocess, "CREATE_NEW_CONSOLE", 16, raising=False)
    called: list[Any] = []
    receipt = actions.open_console(tmp_path, "确认验收", ("pm", "accept", "--mission-id", "M-1"),
                                   opener=lambda *a, **k: called.append((a, k)))
    (command,), kwargs = called[0]
    assert command[:2] == ["cmd", "/c"] and "pm accept --mission-id M-1" in command[2] and kwargs["creationflags"] == 16
    assert receipt.rc is None and "新的终端窗口" in receipt.output


# ---------------------------------------------------------------- 对照表文档


def test_guide_lists_every_button_and_its_command() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    for d in DECISIONS_ALL:
        assert d.label in text, f"DECISIONS.md 没写按钮“{d.label}”"
        assert " ".join(d.command) in text, f"DECISIONS.md 没写 {d.key} 的命令 {' '.join(d.command)}"
