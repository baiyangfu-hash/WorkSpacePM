"""总控屏“决定”页（S1）：每个按钮背后是哪条命令、命令存不存在、选项对不对、不碰护栏。

纯 Python 部分不需要 Qt；控件部分用离屏 Qt。真正的命令行用 click 的命令树核对选项名，
所以 CLI 改了选项名而按钮没跟着改，这里会红。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
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
                          item_id="INB-1", ticket_hash="b" * 64, title="改 IO 表", change_id="CHG-SCPT-2026-700")
VALUES = {"reason": "客户急改", "summary": "干到第3步，下一步写 IO", "as_owner": "claude:cloud", "note": "ok",
          "admission_release_ref": "", "verification_conclusion": "全部通过", "comment": ""}


def _args(decision: decisions.Decision, *, pin: bool = False, approver: str = "baiyang", values: dict[str, str] | None = None) -> list[str]:
    return list(decisions.build_args(decision, TARGET, values or VALUES, approver=approver, pin_enforced=pin, now=NOW))


def _root_cli() -> click.Group:
    from auto_pm.ui.cli.__main__ import cli

    assert isinstance(cli, click.Group)
    return cli


def _resolve(args: list[str]) -> tuple[click.Command, list[str]]:
    """从命令行的根沿命令树往下找到被调用的那条命令，返回 (命令, 剩下的参数)。第一个词不限于 pm（CHG-SCPT-2026-654 起有 project）。"""
    root = _root_cli()
    assert root.get_command(click.Context(root), "pm") is pm_group  # 根上的 pm 就是原来核对的那一组
    command: click.Command = root
    rest = list(args)
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


# ---------------------------------------------------------------- 项目生命周期：归档、重新激活（CHG-SCPT-2026-654）

PROJECT_CLI = Path(__file__).resolve().parents[2] / "auto_pm" / "ui" / "cli" / "project.py"
POLICY_FILE = SCRIPTS / "cockpit_board" / "policy.py"


@pytest.mark.parametrize(("key", "word"), [("project_archive", "archive"), ("project_reactivate", "reactivate")])
def test_project_decisions_build_the_confirm_command_with_click_evidence(key: str, word: str) -> None:
    decision = decisions.BY_KEY[key]
    assert decision.kind == "project" and decision.pin and decision.user_words and decision.fields == ()
    for pin in (False, True):
        args = _args(decision, pin=pin, approver="")
        assert args[:5] == ["project", word, "DJ-2026-009", "--confirm", "--approval-evidence-ref"] and len(args) == 6
        assert args[5] == decisions.click_evidence(key, "DJ-2026-009", NOW)
        assert args[5].startswith("user-confirmation:gui-click-") and not user_evidence_problem(args[5])
    with pytest.raises(decisions.DecisionError, match="项目编号"):
        decisions.build_args(decision, decisions.Target(), {}, approver="", pin_enforced=False, now=NOW)
    with pytest.raises(decisions.DecisionError, match="格式不对"):
        decisions.build_args(decision, decisions.Target(project_id="--confirm"), {}, approver="", pin_enforced=False, now=NOW)


def test_the_decisions_page_never_draws_the_project_buttons() -> None:
    """“决定”页只挑 mission、scope_card、inbox 三类；归档、重新激活只在项目详情页。"""
    missions = [SimpleNamespace(mission_id=f"M{i}", project_id="DJ-1", title="t", state=state, column="在干")
                for i, state in enumerate(sorted({s for d in DECISIONS_ALL for s in d.states}))]
    target = decisions.Target(project_id="DJ-1", request_id="R1", plan_hash="h" * 64, item_id="I1", ticket_hash="k" * 64)
    view = decisions.build_vm(missions, {"DJ-1": [target]}, {"DJ-1": [target]}, "off")
    drawn = {d.key for card in view.cards for d in card.decisions}
    assert drawn and not drawn & {"project_archive", "project_reactivate"}
    assert {d.kind for card in view.cards for d in card.decisions} == {"mission", "scope_card", "inbox"}


def test_dry_runs_and_probes_are_registered_read_only_commands() -> None:
    """验收第 14 条：两条预演和三条 --help 探测都登记在 READ_ONLY_COMMANDS；这张表里任何一条都不带会改东西的选项。"""
    table = decisions.READ_ONLY_COMMANDS
    assert table["project_archive_dry_run"] == ("project", "archive")
    assert table["project_reactivate_dry_run"] == ("project", "reactivate")
    assert table["project_archive_help"] == ("project", "archive", "--help")
    assert table["project_reactivate_help"] == ("project", "reactivate", "--help")
    assert table["project_register_help"] == ("project", "register", "--help")
    assert decisions.LIFECYCLE_PROBES == ("project_archive_help", "project_reactivate_help", "project_register_help")
    for name, command in table.items():
        for word in ("--confirm", "--apply", "--approval-evidence-ref"):
            assert word not in command, (name, command)
    for key, word in (("archive", "archive"), ("reactivate", "reactivate")):
        args = decisions.dry_run_args(key, "DJ-2026-009")
        assert args == ["project", word, "DJ-2026-009"]  # 预演：只有项目号，没有任何选项
        entry = decisions.LIFECYCLES[key]
        assert entry.dry_run in table and entry.probe in table and entry.decision in decisions.BY_KEY
        resolved, rest = _resolve(args)
        assert resolved.name == word and rest == ["DJ-2026-009"]
    with pytest.raises(decisions.DecisionError):
        decisions.dry_run_args("archive", "--confirm")  # 项目号冒充选项：不拼
    for name in decisions.LIFECYCLE_PROBES:  # 探测的三条命令在真实命令行里都有
        resolved, rest = _resolve(list(table[name]))
        assert resolved.name == table[name][1] and rest == ["--help"]
    comment = "".join(line for line in POLICY_FILE.read_text(encoding="utf-8").splitlines(keepends=True) if line.startswith("#"))
    assert "除决定类按钮外只读" in comment and "只跑预演（不带 --confirm）" in comment and "decisions.READ_ONLY_COMMANDS" in comment
    for label in ("归档…", "重新激活…", "重新检查"):
        assert label in comment and label not in {d.label for d in DECISIONS_ALL}


def test_the_dry_run_sentence_matches_the_real_command_source() -> None:
    """验收第 15 条：看板认“预演通过”的那句话，在 project.py 的源文本里正好出现两次（归档、重新激活各一次）。
    只读源文本，不真跑命令；命令那头哪天改了这句话，这里会红，提醒看板跟着改。"""
    assert decisions.DRY_RUN_MARK == "预演（没加 --confirm）"
    source = PROJECT_CLI.read_text(encoding="utf-8")
    assert source.count(decisions.DRY_RUN_MARK) == 2
    lines = [line for line in source.splitlines() if decisions.DRY_RUN_MARK in line]
    assert any("要真的归档" in line for line in lines) and any("要真的改回在研" in line for line in lines)


@pytest.mark.parametrize(("rc", "output", "expected"), [
    (0, "将要改的那一行：x\n预演（没加 --confirm）：什么都没改。", True),
    (1, "预演（没加 --confirm）：什么都没改。", False),  # 退出码不是 0
    (0, "归档前的五项检查：\n  [通过] 卡全关\n  [通过] 收口走完", False),  # 没有那一句：不靠数“通过”有几个
    (None, "预演（没加 --confirm）", False),
    (0, "", False),
])
def test_a_dry_run_passes_only_with_exit_code_zero_and_the_sentence(rc: int | None, output: str, expected: bool) -> None:
    assert decisions.dry_run_passed(rc, output) is expected


def test_register_help_really_lists_the_kind_option_the_board_looks_for() -> None:
    """降级靠在 --help 输出里找 --kind：真实命令里这个选项的名字得是它。"""
    register, _rest = _resolve(["project", "register"])
    options = {opt for param in register.params if isinstance(param, click.Option) for opt in param.opts}
    assert decisions.REGISTER_KIND_OPTION in options


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


BANNER = "launcher: release verified via active_release.json: C:/ws/00_Infrastructure/auto_pm/releases/1.3.3-6a9f127\n"


def _banner_after(body: str) -> str:
    return body + "\n" + BANNER


def _banner_before(body: str) -> str:
    return BANNER + body


def _plain(body: str) -> str:
    return body


def test_json_reads_survive_the_launcher_banner() -> None:
    """真实命令输出＝stdout 的 JSON 后面接 stderr 的启动器横幅；整段交 json.loads 会失败，页面就一片“没有”。"""
    pending = json.dumps({"cards": [{"card": {"request_id": "R1", "plan_hash": "h1"}, "objective": "改 IO"}]}, indent=2)
    inbox = json.dumps({"items": [{"item_id": "I1", "ticket_hash": "t1", "title": "加报警", "status": "PROPOSED"}]}, indent=2)
    for wrap in (_banner_after, _banner_before, _plain):
        assert [t.request_id for t in decisions.parse_pending(wrap(pending), "DJ-1")] == ["R1"]
        assert [t.item_id for t in decisions.parse_inbox(wrap(inbox), "DJ-1")] == ["I1"]
        assert decisions.read_failure("读待批准范围卡", "x", 0, wrap(pending), key="cards") is None
    # 没有 JSON 的输出照旧当“读不懂”，不因为容错变成“没有”
    assert decisions._json(BANNER + "Error: 出错了") == {}
    assert decisions.read_failure("读收件箱", "x", 0, BANNER, key="items") is not None


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
    monkeypatch.setattr(actions, "console_flag", lambda: 0)
    called: list[Any] = []

    def opener(*a: Any, **_k: Any) -> None:
        called.append(a)

    receipt = actions.open_console(tmp_path, "批准范围", ("pm", "approve"), opener=opener)
    assert called == [] and receipt.rc is None and "复制" in receipt.output


def test_open_console_on_windows_opens_a_new_console_with_the_same_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions, "console_flag", lambda: 16)
    monkeypatch.setattr(actions.sys, "executable", "C:\\Python 312\\python.exe")
    called: list[Any] = []

    def opener(*a: Any, **k: Any) -> None:
        called.append((a, k))

    receipt = actions.open_console(tmp_path, "确认验收", ("pm", "accept", "--mission-id", "M-1"), opener=opener)
    (command,), kwargs = called[0]
    assert "cmd" not in command[0].lower() and command[1:3] == ["-B", "-c"]  # 不经过 shell
    assert command[4:] == actions.cli_command(tmp_path, ("pm", "accept", "--mission-id", "M-1"))  # 同一条命令，参数一项不拆不并
    assert kwargs["creationflags"] == 16
    assert receipt.rc is None and "新的终端窗口" in receipt.output


# ---------------------------------------------------------------- 对照表文档


def test_guide_lists_every_button_and_its_command() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    for d in DECISIONS_ALL:
        assert d.label in text, f"DECISIONS.md 没写按钮“{d.label}”"
        assert " ".join(d.command) in text, f"DECISIONS.md 没写 {d.key} 的命令 {' '.join(d.command)}"


# ---------------------------------------------------------------- 注入：每个进命令行的值都过白名单/黑名单（预审 510 a）

HOSTILE = ['x" & calc', "100%PATH%", "a ^ b", "$(rm -rf /)", "`id`", "第一行\n第二行", "a\rb", "a\x00b", "x" * 501]
PASS_THROUGH = ["a & b", "a | b", "a&b"]  # & 和 | 在命令里只是普通字符：放行，但必须原样作为单个参数
FREE_TEXT_KEYS = {"park": ("reason", "summary"), "switch": ("reason", "summary"), "inbox_reject": ("note",),
                  "inbox_confirm": ("note",), "approve_card": ("admission_release_ref",)}


@pytest.mark.parametrize("bad", HOSTILE)
def test_hostile_free_text_is_refused_before_any_command_is_built(bad: str) -> None:
    for key, fields in FREE_TEXT_KEYS.items():
        for field in fields:
            with pytest.raises(decisions.DecisionError):
                _args(decisions.BY_KEY[key], values={**VALUES, field: bad})
    with pytest.raises(decisions.DecisionError):  # 批准人也一样
        _args(decisions.BY_KEY["approve_card"], approver=bad)


@pytest.mark.parametrize("ok", PASS_THROUGH)
def test_ampersand_and_pipe_are_plain_characters_and_stay_one_argument(ok: str) -> None:
    for key, fields in FREE_TEXT_KEYS.items():
        for field in fields:
            assert ok in _args(decisions.BY_KEY[key], values={**VALUES, field: ok})
    assert ok in _args(decisions.BY_KEY["approve_card"], approver=ok)


@pytest.mark.parametrize("bad", ['claude" & calc', "claude cloud", "a&b", "x|y", "a^b", "%PATH%", "a\nb", ""])
def test_agent_identity_is_a_whitelist(bad: str) -> None:
    with pytest.raises(decisions.DecisionError):
        _args(decisions.BY_KEY["unpark"], values={**VALUES, "as_owner": bad})
    for good in ("claude:cloud", "trae:cn", "claude-code"):
        assert good in _args(decisions.BY_KEY["unpark"], values={**VALUES, "as_owner": good})


@pytest.mark.parametrize("bad", ['M-1" & calc', "M 1", "M-1&x", "M-1|x", "M^1", "%X%", "M-1\nM-2", "-M1", ""])
def test_ids_from_the_ledger_are_a_whitelist(bad: str) -> None:
    cases: list[tuple[str, Callable[[str], decisions.Target]]] = [
        ("close", lambda b: decisions.Target(mission_id=b)),
        ("switch", lambda b: decisions.Target(project_id="DJ-1", mission_id=b)),
        ("switch", lambda b: decisions.Target(project_id=b, mission_id="M-1")),
        ("approve_card", lambda b: decisions.Target(request_id=b, plan_hash="a" * 64)),
        ("inbox_confirm", lambda b: decisions.Target(item_id=b, ticket_hash="b" * 64)),
    ]
    for key, make in cases:
        with pytest.raises(decisions.DecisionError):
            decisions.build_args(decisions.BY_KEY[key], make(bad), VALUES, approver="baiyang", pin_enforced=False, now=NOW)


@pytest.mark.parametrize("bad", ['a" & calc', "a b", "a&b", "a|b", "a^b", "%X%", "abc", "", "a" * 129])
def test_hashes_are_a_whitelist(bad: str) -> None:
    with pytest.raises(decisions.DecisionError):
        decisions.build_args(decisions.BY_KEY["approve_card"], decisions.Target(request_id="R1", plan_hash=bad), VALUES,
                             approver="baiyang", pin_enforced=False, now=NOW)
    with pytest.raises(decisions.DecisionError):
        decisions.build_args(decisions.BY_KEY["inbox_reject"], decisions.Target(item_id="I1", ticket_hash=bad), VALUES,
                             approver="baiyang", pin_enforced=False, now=NOW)


def test_ampersand_and_pipe_stay_one_argument_and_the_copied_command_quotes_them() -> None:
    values = {**VALUES, "reason": "客户 A & B | C", "summary": "x&y"}
    args = _args(decisions.BY_KEY["park"], values=values)
    assert args[args.index("--reason") + 1] == "客户 A & B | C" and args[args.index("--summary") + 1] == "x&y"
    shown = decisions.shown_command(args)
    assert '"客户 A & B | C"' in shown and '"x&y"' in shown  # 复制到终端也被引号包住


def test_open_console_never_goes_through_a_shell_even_with_hostile_arguments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions, "console_flag", lambda: 16)
    seen: list[list[str]] = []

    def opener(command: list[str], **_k: Any) -> None:
        seen.append(command)

    hostile = ["pm", "park", "--reason", 'x" & calc | echo ^ %PATH%']
    actions.open_console(tmp_path, "搁着", hostile, opener=opener)
    (command,) = seen
    assert command[-len(hostile):] == hostile  # 恶意参数原样是 argv 里的一项
    assert not any("cmd" == Path(item).stem.lower() for item in command[:1]) and "/c" not in command
    assert "shell" not in actions._CONSOLE_WRAPPER.lower() and "os.system" not in actions._CONSOLE_WRAPPER


def test_run_cli_never_uses_a_shell(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(command=command, **kwargs)
        return subprocess.CompletedProcess(command, 0, "", "")

    actions.run_cli(tmp_path, "搁着", ("pm", "park", "--reason", 'x" & calc'), runner=runner)
    assert isinstance(seen["command"], list) and not seen.get("shell") and seen["command"][-1] == 'x" & calc'


@pytest.mark.parametrize("text", ['{"cards": {"x": 1}}', '{"cards": "abc"}', '{"cards": null}', '{"cards": 3}', '{"cards": ["x", 1, null, {"card": 5}]}', "", "not json"])
def test_parse_pending_never_crashes_on_unexpected_shapes(text: str) -> None:
    """命令输出的形状不对时返回空列表，不抛异常（读没读懂由 read_failure 另外判）。"""
    assert decisions.parse_pending(text, "DJ-1") == []


@pytest.mark.parametrize("text", ['{"items": {"x": 1}}', '{"items": "abc"}', '{"items": null}', '{"items": 3}', '{"items": ["x", 1, null]}', "", "not json"])
def test_parse_inbox_never_crashes_on_unexpected_shapes(text: str) -> None:
    assert decisions.parse_inbox(text, "DJ-1") == []


# ---------------------------------------------------------------- 变更单的两个按钮：批准变更单、推到完成（M8 的 8.1）


def _order(change_id: str, status: str, what: str = "改 IO 表") -> SimpleNamespace:
    return SimpleNamespace(change_id=change_id, domain="SCPT", what=what, status=status, raised="2026-11-13")


def _change_view(statuses: list[str], block: str = "") -> decisions.DecisionsVM:
    orders = [("SW-2026-008", _order(f"CHG-SCPT-2026-{700 + i}", status)) for i, status in enumerate(statuses)]
    return decisions.build_vm([], {}, {}, "off", changes=orders, human_only_block=block)


def test_change_buttons_build_one_change_transition_step_with_click_evidence() -> None:
    approve, complete = decisions.BY_KEY["change_approve"], decisions.BY_KEY["change_complete"]
    assert approve.human_only and complete.human_only and approve.user_words and complete.user_words
    got = _args(approve)
    assert got[:9] == ["change", "transition", "CHG-SCPT-2026-700", "--to", "approved", "--pid", "DJ-2026-009", "--approver", "baiyang"]
    assert got[9] == "--approval-evidence-ref" and got[10] == decisions.click_evidence("change_approve", "CHG-SCPT-2026-700", NOW)
    assert not user_evidence_problem(got[10]) and "--comment" not in got and len(got) == 11
    assert _args(approve, values={"comment": "只批第 2 节"})[-2:] == ["--comment", "只批第 2 节"]
    got = _args(complete)
    assert got[3:5] == ["--to", "completed"] and got[-2:] == ["--verification-conclusion", "全部通过"]
    assert "--allow-partial-verification" not in got  # 放过没过的验证项不上看板
    with pytest.raises(decisions.DecisionError, match="验证结论"):
        _args(complete, values={"verification_conclusion": ""})
    with pytest.raises(decisions.DecisionError, match="批准人"):
        _args(approve, approver="")
    with pytest.raises(decisions.DecisionError, match="变更单号"):
        decisions.build_args(approve, decisions.Target(project_id="DJ-1"), {}, approver="a", pin_enforced=False, now=NOW)


def test_change_buttons_follow_the_real_status_flow_and_labels() -> None:
    """按钮出现的状态、推到的状态、状态的白话，都和主程序的状态流对得上；主程序改了这里会红。"""
    from auto_pm.domain.change.constants import STATUS_FLOW, STATUS_LABELS
    from auto_pm.ui.cli.change import cmd_transition

    for key, target in decisions.CHANGE_TARGET.items():
        for state in decisions.BY_KEY[key].states:
            assert target in STATUS_FLOW[state], f"{key}: {state} 不能一步推到 {target}"
    for status, label in decisions.CHANGE_STATUS_LABEL.items():
        assert STATUS_LABELS[status] == label
    before = set(decisions.CHANGE_BEFORE_APPROVE) | set(decisions.CHANGE_BEFORE_COMPLETE)
    assert before <= set(STATUS_FLOW) and not before & {s for d in DECISIONS_ALL if d.kind == "change" for s in d.states}
    default = next(p.default for p in cmd_transition.params if p.name == "verification_conclusion")
    field = decisions.BY_KEY["change_complete"].fields[0]
    assert field.default == default and "通过" in field.default  # 先填上的字就是命令自己的缺省值


def test_change_cards_show_a_button_only_at_its_own_step_and_count_the_rest() -> None:
    view = _change_view(["draft", "submitted", "under_review", "approved", "implementing", "accepting", "completed", "未读到状态"])
    assert [(c.column, [d.key for d in c.decisions]) for c in view.cards] == [("变更单", ["change_approve"]), ("变更单", ["change_complete"])]
    assert [c.target.change_id for c in view.cards] == ["CHG-SCPT-2026-702", "CHG-SCPT-2026-705"]
    assert "审核中" in view.cards[0].detail and "验收中" in view.cards[1].detail
    assert len(view.notes) == 2 and "另有 2 张" in view.notes[0] and "另有 2 张" in view.notes[1]
    assert _change_view(["completed", "rejected"]).notes == () and _change_view([]).cards == ()
    scope = decisions.Target(project_id="DJ-1", request_id="R1", plan_hash="h" * 64)
    mixed = decisions.build_vm([], {"DJ-1": [scope]}, {}, "off", changes=[("DJ-1", _order("CHG-PLC-2026-001", "under_review"))])
    assert [c.column for c in mixed.cards] == ["变更单", "范围卡"]


def test_human_only_buttons_are_blocked_when_the_board_carries_an_agent_marker_or_cannot_tell() -> None:
    from auto_pm.application.core.lease_handover_service import AGENT_MARKERS

    assert decisions.human_only_block(()) == ""
    assert "CLAUDECODE" in decisions.human_only_block(("CLAUDECODE",)) and "你本人" in decisions.human_only_block(("CLAUDECODE",))
    assert decisions.human_only_block(None) == decisions.HUMAN_ONLY_UNKNOWN
    assert _change_view(["under_review"], block="原因").cards[0].blocked == "原因"
    assert actions.board_agent_markers({}) == ()
    for marker in AGENT_MARKERS:  # 名单取主程序的那一份：主程序多认一个标记，看板跟着认
        assert actions.board_agent_markers({marker: "x"}) == (marker,)
    # 只许你本人点的：要用户原话的、要口令的（含确认验收），一个不漏；确认开工、收口 AI 也可以做（cockpit-entry 第 6、8 步）
    assert {d.key for d in DECISIONS_ALL if d.human_only} == {d.key for d in DECISIONS_ALL if d.user_words or d.pin}
    assert {d.key for d in DECISIONS_ALL if not d.human_only} == {"begin_work", "close"}


@pytest.mark.usefixtures("identity_guard_off")
def test_a_real_change_order_goes_from_the_file_to_the_button_to_the_real_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """真文件走一遍：看板读到“审核中”的单 → 出“批准变更单” → 拼出的命令交给真命令 → 文件里变成已批准。"""
    import pm_dashboard as pd
    from click.testing import CliRunner

    from auto_pm.application.core.lease_handover_service import AGENT_MARKERS
    from tests.infrastructure.test_git_hook_enforcer import _make_dual_root_fixture

    for marker in AGENT_MARKERS:  # 这条测试演的是“你本人打开的看板”
        monkeypatch.delenv(marker, raising=False)
    _cand, ctrl, _msg = _make_dual_root_fixture(tmp_path, chg_status="under_review")
    project_root = ctrl / "01_Project" / "SW-2026-008"
    orders = pd.read_change_orders(project_root)
    assert [(o.change_id, o.status) for o in orders] == [("CHG-SCPT-2026-346", "under_review")]
    view = decisions.build_vm([], {}, {}, "off", changes=[("SW-2026-008", o) for o in orders])
    card = view.cards[0]
    assert [d.key for d in card.decisions] == ["change_approve"] and card.blocked == ""
    args = decisions.build_args(card.decisions[0], card.target, {}, approver="baiyang", pin_enforced=False, now=NOW)
    obj = SimpleNamespace(control_root=ctrl, workspace_root=str(ctrl), templates_dir=str(ctrl))
    result = CliRunner().invoke(_root_cli().get_command(click.Context(_root_cli()), "change"), args[1:], obj=obj)  # type: ignore[arg-type]
    assert result.exit_code == 0, result.output
    assert [(o.change_id, o.status) for o in pd.read_change_orders(project_root)] == [("CHG-SCPT-2026-346", "approved")]
    assert decisions.build_vm([], {}, {}, "off", changes=[("SW-2026-008", o) for o in pd.read_change_orders(project_root)]).cards == ()


def test_the_command_itself_still_refuses_an_agent_without_evidence_and_the_known_gap_is_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """命令的拒绝没变：带 AI 标记、不带凭据，批准被拒。带 AI 标记又带一条格式对的凭据，命令放行（用户 2026-10-31 定的 A）——
    所以看板自己必须把 human_only 的按钮关掉，不能指望命令替它拦。"""
    from click.testing import CliRunner

    from auto_pm.ui.cli import change as change_cli

    reached: list[str] = []
    monkeypatch.setattr(change_cli, "require_runtime_identity_for_change", lambda *a, **k: reached.append("past the agent refusal"))
    monkeypatch.setattr(change_cli, "ChangeService", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("stop here")))
    monkeypatch.setenv("CLAUDECODE", "1")
    obj = SimpleNamespace(control_root=tmp_path, workspace_root=str(tmp_path), templates_dir=str(tmp_path))
    args = _args(decisions.BY_KEY["change_approve"])
    bare = [a for a in args[1:] if a != "--approval-evidence-ref" and not a.startswith("user-confirmation:")]
    refused = CliRunner().invoke(change_cli.change_group, bare, obj=obj)
    assert refused.exit_code != 0 and "agent 会话" in refused.output and reached == []
    CliRunner().invoke(change_cli.change_group, args[1:], obj=obj)
    assert reached == ["past the agent refusal"]


@pytest.mark.usefixtures("identity_guard_off")
def test_complete_goes_through_the_real_command_and_a_refusal_keeps_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """“推到完成”真跑一遍：停在“验收中”的单出按钮，拼出的命令交给真命令；命令说行就变“已完成”，说不行文件不变。"""
    import pm_dashboard as pd
    from click.testing import CliRunner

    from auto_pm.application.core.lease_handover_service import AGENT_MARKERS
    from tests.infrastructure.test_git_hook_enforcer import _make_dual_root_fixture

    for marker in AGENT_MARKERS:
        monkeypatch.delenv(marker, raising=False)
    _cand, ctrl, _msg = _make_dual_root_fixture(tmp_path, chg_status="accepting")
    project_root = ctrl / "01_Project" / "SW-2026-008"
    orders = pd.read_change_orders(project_root)
    card = decisions.build_vm([], {}, {}, "off", changes=[("SW-2026-008", o) for o in orders]).cards[0]
    assert [d.key for d in card.decisions] == ["change_complete"]
    obj = SimpleNamespace(control_root=ctrl, workspace_root=str(ctrl), templates_dir=str(ctrl))
    group = _root_cli().get_command(click.Context(_root_cli()), "change")
    chg_file = next(ctrl.rglob("CHG-SCPT-2026-346.md"))
    before = chg_file.read_bytes()
    bad = decisions.build_args(card.decisions[0], card.target, {"verification_conclusion": "还没验"}, approver="baiyang", pin_enforced=False, now=NOW)
    refused = CliRunner().invoke(group, bad[1:], obj=obj)  # type: ignore[arg-type]
    assert refused.exit_code == 1 and "验证结论" in refused.output and chg_file.read_bytes() == before
    good = decisions.build_args(card.decisions[0], card.target, {"verification_conclusion": "全部通过"}, approver="baiyang", pin_enforced=False, now=NOW)
    done = CliRunner().invoke(group, good[1:], obj=obj)  # type: ignore[arg-type]
    assert done.exit_code == 0, done.output
    assert [(o.change_id, o.status) for o in pd.read_change_orders(project_root)] == [("CHG-SCPT-2026-346", "completed")]


def test_the_guide_names_every_marker_and_every_human_only_button() -> None:
    from auto_pm.application.core.lease_handover_service import AGENT_MARKERS

    text = GUIDE.read_text(encoding="utf-8")
    section = text[text.index("## 只许你本人点"):]
    for marker in AGENT_MARKERS:  # 主程序多认一个标记，说明里也得写上
        assert f"`{marker}`" in section, marker
    listed = next(line for line in section.splitlines() if line.startswith("- **哪些按钮**"))
    listed = listed.split("：", 1)[1].split("。", 1)[0].split("：", 1)[1]  # “……共 11 个：批准范围、……、推到完成”
    assert listed.split("、") == [d.label for d in DECISIONS_ALL if d.human_only]
    assert f"共 {sum(d.human_only for d in DECISIONS_ALL)} 个" in section


def test_markers_are_none_not_empty_when_the_main_program_cannot_be_imported(monkeypatch: pytest.MonkeyPatch) -> None:
    """找不到主程序时必须是“认不出”（None），不能当成“没带标记”（空）——否则按钮会对 AI 拉起的看板也亮。"""
    monkeypatch.setitem(sys.modules, "auto_pm.application.core.lease_handover_service", None)  # 再 import 就报 ImportError
    assert actions.board_agent_markers({"CLAUDECODE": "1"}) is None
    assert actions.board_agent_markers({}) is None
    assert decisions.human_only_block(actions.board_agent_markers({})) == decisions.HUMAN_ONLY_UNKNOWN
