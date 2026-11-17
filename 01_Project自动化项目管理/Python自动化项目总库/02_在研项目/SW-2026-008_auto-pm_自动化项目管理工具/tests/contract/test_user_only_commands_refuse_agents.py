"""K6：命令分类表里“只听用户本人”（user_only）的每一条命令，都写明在哪里拦 agent，而且真拦。

起因（审计 ``audits/用户专属命令_拦agent核实_20261115.md``）：pm accept、pm confirm-start、release rollback、
continuity restore-backup 四条什么都不核，claim reclaim、release deploy 两条只核前缀和长度。根因是“只听用户”只写在
分类表（``scripts/cockpit_board/flow/commands_map.json``）和 AGENTS.md 的名单里，命令有没有真拦，没有任何检查把两边接起来，
所以新加或漏改一条谁也看不见。这个文件把两边接起来：

1. 分类表里每一条 user_only 命令，再加上按参数只听用户的 ``change transition``（推到批准、有条件批准、推到完成，
   FLOW-001 和 AGENTS.md 交卷到收口第 8 步），都在 ``GUARDS`` 里写明“在哪个函数、靠哪一次调用拦”。表里新加一条
   user_only 却没写拦法，或写了的命令已经不在表里，都红。
2. 写明的函数真有那一次调用：改名、删掉、挪走都红。
3. 这张单补过的命令实跑：带 agent 标记、不带用户原话 → 退出码非 0、出这条命令自己的拒绝原文、临时目录里一个文件都没多；
   带合格的用户原话，或者根本没有 agent 标记（用户本人的终端、看板上用户点的按钮）→ 走得过这一步。
4. 看板上不带用户原话的按钮（“确认验收”“确认开工”）背后的命令，只能按 agent 标记拦，不能要求人人带原话，
   不然用户自己点也会被拒。

三种拦法：
- ``marker``：带 agent 标记又没带合格的用户原话就拒（``refuse_agent_approval``，用户 10-31 定的 A）；用户本人不用带。
- ``always``：带 agent 标记一律拒，带原话也不行（口令、签风险、项目删改、旧格式实施卡）。
- ``words``：谁来跑都要带合格的用户原话（``user_evidence_problem`` 那一套格式）。``pm park`` 不带原话只能放进“等你”，
  这是 WS-002 的设计（agent 可以停自己手上的卡），不算漏拦。

凭据只核格式，挡不住 agent 自己编一句格式合格的话，这是单用户信任模型下的设计（审计同表口径），这里不假装更多。
"""

from __future__ import annotations

import ast
import inspect
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import change as change_cli
from auto_pm.ui.cli import continuity_backup as continuity_backup_cli
from auto_pm.ui.cli import implementation_card as implementation_card_cli
from auto_pm.ui.cli import pm as pm_cli
from auto_pm.ui.cli import release as release_cli
from auto_pm.ui.cli.__main__ import cli

PROJECT = Path(__file__).resolve().parents[2]
PACKAGE = PROJECT / "auto_pm"
SCRIPTS = PROJECT / "scripts"
COMMANDS_MAP = SCRIPTS / "cockpit_board" / "flow" / "commands_map.json"
USER_WORDS = "user-confirmation:2026-11-16T00:47:31Z"  # 格式合格的用户原话位置（时间），不点名任何 agent

MARKER = "marker"
ALWAYS = "always"
WORDS = "words"


@dataclass(frozen=True)
class Guard:
    kind: str
    source: str  # "包内相对路径::函数名"（方法写成 类名.方法名）
    call: str  # 这个函数里必须有的那一次调用


GUARDS: dict[str, Guard] = {
    "agent register": Guard(ALWAYS, "ui/cli/agent.py::agent_register", "agent_markers"),
    "agent unregister": Guard(ALWAYS, "ui/cli/agent.py::agent_unregister", "agent_markers"),
    "claim reclaim": Guard(WORDS, "application/core/claim_service.py::ClaimService.reclaim", "user_evidence_problem"),
    "continuity lease extend-hold": Guard(WORDS, "ui/cli/continuity.py::extend_lease_hold", "user_evidence_problem"),
    "continuity restore-backup": Guard(MARKER, "ui/cli/continuity_backup.py::restore_backup_command", "refuse_agent_approval"),
    "decision create": Guard(MARKER, "ui/cli/decision.py::create_decision", "refuse_agent_approval"),
    "implementation-card approve": Guard(ALWAYS, "ui/cli/implementation_card.py::approve_card", "agent_markers"),
    "pm accept": Guard(MARKER, "ui/cli/pm.py::accept_pm", "refuse_agent_approval"),
    "pm approve": Guard(WORDS, "domain/change/decision_service.py::DecisionService.validate_planning_approval", "is_user_confirmation"),
    "pm approver-pin init": Guard(ALWAYS, "ui/cli/approval_pin.py::approver_pin_init", "agent_markers"),
    "pm confirm-start": Guard(MARKER, "ui/cli/pm.py::confirm_start_pm", "refuse_agent_approval"),
    "pm inbox confirm": Guard(WORDS, "domain/change/decision_service.py::DecisionService.validate_planning_approval", "is_user_confirmation"),
    "pm inbox reject": Guard(WORDS, "domain/change/decision_service.py::DecisionService.validate_planning_approval", "is_user_confirmation"),
    "pm park": Guard(WORDS, "infrastructure/continuity_store.py::ContinuityStore.park_mission", "user_evidence_problem"),
    "pm sign-risk": Guard(ALWAYS, "application/core/lease_handover_service.py::LeaseHandoverService.signature_refusal", "agent_markers"),
    "pm switch": Guard(WORDS, "application/core/mission_switch_service.py::_require_user_words", "user_evidence_problem"),
    "pm unpark": Guard(WORDS, "infrastructure/continuity_store.py::ContinuityStore.unpark_mission", "user_evidence_problem"),
    "project archive": Guard(ALWAYS, "ui/cli/project.py::cmd_archive", "_refuse_agent_or_continue"),
    "project delete": Guard(ALWAYS, "ui/cli/project.py::cmd_delete", "agent_markers"),
    "project reactivate": Guard(ALWAYS, "ui/cli/project.py::cmd_reactivate", "_refuse_agent_or_continue"),
    "project restore": Guard(ALWAYS, "ui/cli/project.py::cmd_restore", "agent_markers"),
    "release deploy": Guard(WORDS, "ui/cli/release.py::release_deploy", "user_evidence_problem"),
    "release rollback": Guard(MARKER, "ui/cli/release.py::release_rollback", "refuse_agent_approval"),
    "release ship": Guard(WORDS, "ui/cli/release.py::release_ship", "user_evidence_problem"),
    # 分类表里是 write（别的几步由 agent 推），只有这三个目标只听用户；分类表还没有按参数分的字段，先写在这里。
    "change transition": Guard(MARKER, "ui/cli/change.py::cmd_transition", "refuse_agent_approval"),
}
PARAMETER_USER_ONLY = {"change transition": ("--to", ("approved", "conditionally_approved", "completed"))}


def _classification() -> dict[str, dict[str, str]]:
    data = json.loads(COMMANDS_MAP.read_text(encoding="utf-8"))
    commands = data["commands"]
    assert isinstance(commands, dict)
    return commands


def user_only_commands(table: dict[str, dict[str, str]]) -> set[str]:
    return {name for name, entry in table.items() if entry.get("class") == "user_only"} | set(PARAMETER_USER_ONLY)


def guard_gaps(user_only: set[str], guards: dict[str, Guard]) -> tuple[list[str], list[str]]:
    """(只听用户、却没写拦法的, 写了拦法、表里已经不是只听用户的)。"""
    return sorted(user_only - set(guards)), sorted(set(guards) - user_only)


def test_every_user_only_command_says_where_it_refuses_an_agent() -> None:
    missing, stale = guard_gaps(user_only_commands(_classification()), GUARDS)
    assert missing == [], f"分类表里只听用户的命令没写拦法（先补拦截，再登记到 GUARDS）：{missing}"
    assert stale == [], f"这些命令已经不是只听用户的了，从 GUARDS 删掉：{stale}"


def test_mutation_a_new_user_only_command_without_a_guard_is_named() -> None:
    table = dict(_classification())
    table["pm brand-new-approval"] = {"class": "user_only", "note": "变异测试"}
    missing, stale = guard_gaps(user_only_commands(table), GUARDS)
    assert missing == ["pm brand-new-approval"]
    assert stale == []


def _function(source: str) -> ast.FunctionDef:
    relative, qualname = source.split("::")
    path = PACKAGE / relative
    assert path.is_file(), f"{source}：文件不存在"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    scope: list[ast.stmt] = list(tree.body)
    *owners, name = qualname.split(".")
    for owner in owners:
        classes = [node for node in scope if isinstance(node, ast.ClassDef) and node.name == owner]
        assert classes, f"{source}：没有类 {owner}"
        scope = list(classes[0].body)
    functions = [node for node in scope if isinstance(node, ast.FunctionDef) and node.name == name]
    assert functions, f"{source}：没有函数 {qualname}"
    return functions[0]


def _calls(function: ast.FunctionDef) -> list[str]:
    names: list[str] = []
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            func = node.func
            names.append(func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else "")
    return names


@pytest.mark.parametrize("name", sorted(GUARDS))
def test_the_named_function_really_makes_the_refusing_call(name: str) -> None:
    guard = GUARDS[name]
    assert guard.kind in (MARKER, ALWAYS, WORDS), name
    assert guard.call in _calls(_function(guard.source)), f"{name}：{guard.source} 里找不到对 {guard.call} 的调用，拦截被删了或挪走了"


def _leaves(root: click.Command) -> dict[str, click.Command]:
    found: dict[str, click.Command] = {}

    def walk(command: click.Command, path: list[str]) -> None:
        if isinstance(command, click.Group):
            context = click.Context(command)
            for child_name in command.list_commands(context):
                child = command.get_command(context, child_name)
                assert child is not None
                walk(child, [*path, child_name])
        else:
            found[" ".join(path)] = command

    walk(root, [])
    return found


@pytest.mark.parametrize("name", sorted(name for name, guard in GUARDS.items() if guard.source.startswith("ui/cli/")))
def test_a_command_level_guard_sits_in_that_command_itself(name: str) -> None:
    """拦截写在命令层的，写明的函数就是这条命令的回调，不是旁边一个同名的。"""
    callback = _leaves(cli)[name].callback
    assert callback is not None, name
    original = inspect.unwrap(callback)
    relative, qualname = GUARDS[name].source.split("::")
    assert original.__name__ == qualname, (name, original.__name__)
    assert Path(inspect.getfile(original)).resolve() == (PACKAGE / relative).resolve(), name


def test_board_buttons_without_user_words_run_commands_the_user_can_run_bare() -> None:
    """看板上不带用户原话的按钮背后若是只听用户的命令，只能按 agent 标记拦；按 ``words`` 拦的话用户自己点也会被拒。"""
    sys.path.insert(0, str(SCRIPTS))
    try:
        from cockpit_board import decisions
    finally:
        sys.path.remove(str(SCRIPTS))
    for decision in decisions.DECISIONS:
        name = " ".join(decision.command)
        if name in GUARDS and not decision.user_words and decision.kind != "change":
            assert GUARDS[name].kind == MARKER, f"{decision.label}：{name} 不能要求人人带原话"


# ---- 这张单补过的命令：实跑 -----------------------------------------------------------------------------


class _Reached(click.ClickException):
    """过了拦截、走到下一步的记号：每条命令的下一步换成抛它，什么都不碰。"""

    def __init__(self) -> None:
        super().__init__("K6-REACHED-NEXT-STEP")


def _reach(*_args: object, **_kwargs: object) -> None:
    raise _Reached()


@dataclass(frozen=True)
class Probe:
    args: tuple[str, ...]  # main.py 后面的参数；{tmp} 换成临时目录
    refusal: str  # 被拒时输出里一定有的原文
    evidence_flag: str  # 这条命令带用户原话的选项
    next_step: tuple[object, str]  # (模块或类, 属性名)：拦截之后的第一步，换成 _reach
    bare_user_passes: bool = True  # 没有 agent 标记、不带原话的人能不能过这一步（words 类不能）


PROBES: dict[str, Probe] = {
    "pm accept": Probe(("pm", "accept", "--mission-id", "M-K6"), "不能记最终验收", "--approval-evidence-ref",
                       (pm_cli, "_require_control_root")),
    "pm confirm-start": Probe(("pm", "confirm-start", "--mission-id", "M-K6"), "不能确认开工", "--approval-evidence-ref",
                              (pm_cli, "_emit_card")),
    "release rollback": Probe(("release", "rollback", "{tmp}/pointer_backup"), "不能退回发布版本", "--approval-evidence-ref",
                              (release_cli, "warn_runtime_identity")),
    "continuity restore-backup": Probe(("continuity", "restore-backup", "{tmp}/continuity.db.bak", "--yes"), "不能用备份替换在用账本",
                                       "--approval-evidence-ref", (continuity_backup_cli, "_service")),
    "implementation-card approve": Probe(("implementation-card", "approve", "CARD-K6", "--approver", "baiyang", "--approval-evidence", "DEC-K6"),
                                         "不能给实施卡", "", (implementation_card_cli, "require_approval_pin")),
    "change transition --to approved": Probe(("change", "transition", "CHG-SCPT-2026-999", "--to", "approved", "--pid", "SW-2026-008"),
                                             "不能批准变更单", "--approval-evidence-ref", (change_cli, "require_runtime_identity_for_change")),
    "change transition --to conditionally_approved": Probe(
        ("change", "transition", "CHG-SCPT-2026-999", "--to", "conditionally_approved", "--pid", "SW-2026-008"),
        "不能批准变更单", "--approval-evidence-ref", (change_cli, "require_runtime_identity_for_change")),
    "change transition --to completed": Probe(("change", "transition", "CHG-SCPT-2026-999", "--to", "completed", "--pid", "SW-2026-008"),
                                              "推到完成", "--approval-evidence-ref", (change_cli, "require_runtime_identity_for_change")),
    "claim reclaim": Probe(("claim", "reclaim", "999", "--reason", "K6 实跑"), "收回别人的占位只听用户的", "--approval-evidence-ref",
                           (None, "claim_find"), bare_user_passes=False),
    "release deploy": Probe(("release", "deploy", "abc1234", "--no-check-only", "--approver", "baiyang",
                             "--card-file", "{tmp}/card.md", "--drill-script", "{tmp}/drill.py"),
                            "--confirm-ref", "--confirm-ref", (release_cli, "require_runtime_identity_for_workspace"), bare_user_passes=False),
    "release ship": Probe(("release", "ship", "abc1234", "--no-check-only", "--approver", "baiyang"),
                          "--confirm-ref", "--confirm-ref", (release_cli, "require_runtime_identity_for_workspace"), bare_user_passes=False),
}


def test_every_command_this_card_guards_is_probed() -> None:
    probed = {key.split(" --to ")[0] for key in PROBES}
    assert probed == {
        "pm accept", "pm confirm-start", "release rollback", "continuity restore-backup", "claim reclaim", "release deploy", "release ship",
        "implementation-card approve", "change transition",
    }
    targets = {key.split(" --to ")[1] for key in PROBES if " --to " in key}
    assert targets == set(PARAMETER_USER_ONLY["change transition"][1])


def _files(root: Path) -> dict[str, tuple[int, int]]:
    return {str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns) for path in root.rglob("*")}


def _run(probe: Probe, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, agent: bool, words: str) -> tuple[int, str]:
    (tmp_path / "pointer_backup").mkdir(exist_ok=True)  # release rollback 的参数要求目录存在
    owner, attribute = probe.next_step
    if owner is None:  # claim reclaim：核过原话后第一步是去远程找这张卡
        from auto_pm.application.core.claim_service import ClaimError, ClaimService

        def _find(*_args: object, **_kwargs: object) -> None:
            raise ClaimError("K6-REACHED-NEXT-STEP")

        monkeypatch.setattr(ClaimService, "_find", _find)
    else:
        monkeypatch.setattr(owner, attribute, _reach)
    if agent:
        monkeypatch.setenv("CLAUDECODE", "1")
    args = [part.replace("{tmp}", str(tmp_path)) for part in probe.args]
    if words:
        args += [probe.evidence_flag or "--approval-evidence-ref", words]
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["-w", str(tmp_path), *args], catch_exceptions=False)
    return result.exit_code, result.output


@pytest.mark.parametrize("key", sorted(PROBES))
def test_an_agent_without_the_users_words_is_refused_before_anything_is_touched(
    key: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = PROBES[key]
    (tmp_path / "pointer_backup").mkdir()
    before = _files(tmp_path)
    code, output = _run(probe, tmp_path, monkeypatch, agent=True, words="")
    assert code != 0, (key, output)
    assert probe.refusal in output, (key, output)
    assert "K6-REACHED-NEXT-STEP" not in output, f"{key}：没拦住，走到了下一步"
    assert _files(tmp_path) == before, f"{key}：被拒之前写了文件"


@pytest.mark.parametrize("key", sorted(key for key, probe in PROBES.items() if probe.evidence_flag))
def test_an_agent_with_the_users_words_gets_past_the_guard(key: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, output = _run(PROBES[key], tmp_path, monkeypatch, agent=True, words=USER_WORDS)
    assert "K6-REACHED-NEXT-STEP" in output, (key, code, output)


@pytest.mark.parametrize("key", sorted(PROBES))
def test_the_user_in_person_needs_no_words_only_where_the_command_says_so(
    key: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """没有 agent 标记（用户本人的终端、看板上用户点的按钮）：按 agent 标记拦的命令直接过；人人要原话的命令照样要。"""
    probe = PROBES[key]
    code, output = _run(probe, tmp_path, monkeypatch, agent=False, words="")
    if probe.bare_user_passes:
        assert "K6-REACHED-NEXT-STEP" in output, (key, code, output)
    else:
        assert code != 0 and probe.refusal in output and "K6-REACHED-NEXT-STEP" not in output, (key, code, output)


@pytest.mark.parametrize("key", ["claim reclaim", "release deploy", "release rollback", "pm accept"])
def test_a_reference_an_agent_wrote_is_refused_too(key: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """只核前缀和长度时这种也能过（claim reclaim、release deploy 原来的写法）；现在和别的批准用同一个格式核对。"""
    code, output = _run(PROBES[key], tmp_path, monkeypatch, agent=True, words="user-confirmation:claude-ok")
    assert code != 0 and "K6-REACHED-NEXT-STEP" not in output, (key, output)
