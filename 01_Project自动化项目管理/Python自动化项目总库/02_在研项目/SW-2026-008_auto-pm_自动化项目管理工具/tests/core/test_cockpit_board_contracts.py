"""骨架 C 的契约对账（CHG-SCPT-2026-628）：命令分类表、页面读命令声明、脊柱十步，都和真实代码逐条对上。

- ``flow/commands_map.json``：驾驶舱命令行每一条叶子命令都要分类（read / write / user_only / never）。
  新加命令没分类、删了命令表里还留着，都红（含变异测试：往命令树里塞一条假命令，必须被点名）。
- 按钮 ↔ 命令：“决定”页、“工具”页、PLC 证据按钮背后的命令，分类必须和按钮性质一致；never 类不许有按钮。
- ``flow/pages.json``：页面只能读 read 类命令，参数里不许带该命令的写开关，读法必须在 ``readers.READERS`` 里登记。
- ``flow/spine.json``：十步齐、每步的命令都登记过、引用的页面真存在。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click
import pytest

from auto_pm.ui.cli.__main__ import cli

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import actions, decisions, policy, readers, tool_actions  # noqa: E402

FLOW = SCRIPTS / "cockpit_board" / "flow"
CLASSES = ("read", "write", "user_only", "never")


def _load(name: str) -> dict[str, Any]:
    data = json.loads((FLOW / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


COMMANDS: dict[str, dict[str, Any]] = _load("commands_map.json")["commands"]
PAGES: dict[str, Any] = _load("pages.json")
SPINE: dict[str, Any] = _load("spine.json")


def leaf_commands(root: click.Command) -> dict[str, click.Command]:
    """命令树里每一条叶子命令，键是空格连起来的路径（如 ``pm inbox list``）。"""
    found: dict[str, click.Command] = {}

    def walk(command: click.Command, path: list[str]) -> None:
        if isinstance(command, click.Group):
            context = click.Context(command)
            for name in command.list_commands(context):
                child = command.get_command(context, name)
                assert child is not None, " ".join([*path, name])
                walk(child, [*path, name])
        else:
            found[" ".join(path)] = command

    walk(root, [])
    return found


def classification_gaps(tree: dict[str, click.Command], table: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(命令树里有、表里没分类的, 表里有、命令树里已经没了的)。"""
    return sorted(set(tree) - set(table)), sorted(set(table) - set(tree))


LEAVES = leaf_commands(cli)


def _options(command: click.Command) -> set[str]:
    return {opt for param in command.params for opt in (*param.opts, *param.secondary_opts)}


def _command_of(args: tuple[str, ...] | list[str]) -> str:
    """按钮或页面的参数开头对应哪条叶子命令（最长匹配）。"""
    words = [word for word in args if not word.startswith("-")]
    for size in range(len(words), 0, -1):
        name = " ".join(words[:size])
        if name in LEAVES:
            return name
    raise AssertionError(f"参数 {list(args)} 不是任何一条命令")


# ---- 命令分类表 ---------------------------------------------------------------------------------


def test_every_command_is_classified_and_no_stale_entries() -> None:
    missing, stale = classification_gaps(LEAVES, COMMANDS)
    assert missing == [], f"新命令没分类，先在 flow/commands_map.json 里登记：{missing}"
    assert stale == [], f"命令已经不在了，从分类表里删掉：{stale}"


def test_mutation_an_unclassified_command_is_named() -> None:
    """变异测试：往命令树里塞一条假命令、再拿掉一条真命令，检查必须两头都点名。"""
    fake_tree = dict(LEAVES)
    fake_tree["pm brand-new-command"] = click.Command("brand-new-command")
    removed = "claim list"
    del fake_tree[removed]
    missing, stale = classification_gaps(fake_tree, COMMANDS)
    assert missing == ["pm brand-new-command"]
    assert stale == [removed]


def test_entries_are_well_formed_and_counts_match() -> None:
    data = _load("commands_map.json")
    assert tuple(data["classes"]) == CLASSES
    counts: dict[str, int] = {}
    for name, entry in COMMANDS.items():
        assert entry["class"] in CLASSES, name
        assert set(entry) <= {"class", "note", "write_flags"}, name
        if entry["class"] in ("user_only", "never"):
            assert entry.get("note", "").strip(), f"{name}：只听用户本人 / 不放进界面，要写明理由"
        if "write_flags" in entry:
            assert entry["class"] == "read", f"{name}：只有只读命令才需要列出写开关"
        counts[entry["class"]] = counts.get(entry["class"], 0) + 1
    assert data["counts"] == dict(sorted(counts.items()))


def test_write_flags_are_real_options() -> None:
    for name, entry in COMMANDS.items():
        for flag in entry.get("write_flags", []):
            assert flag in _options(LEAVES[name]), f"{name} 没有 {flag} 这个选项"


@pytest.mark.parametrize("name", [
    "pm approve", "pm accept", "pm confirm-start", "pm approver-pin init", "pm sign-risk",
    "pm park", "pm unpark", "pm switch", "pm inbox confirm", "pm inbox reject",
    "decision create", "project delete", "release deploy", "release rollback", "claim reclaim",
])
def test_user_only_commands_stay_user_only(name: str) -> None:
    """这些命令要口令或用户原话（AGENTS.md 阶段 3、WS-002、D-101），表里不许被改成别的类。"""
    assert COMMANDS[name]["class"] == "user_only"


# ---- 按钮 ↔ 命令 ---------------------------------------------------------------------------------


def test_decision_buttons_run_write_or_user_only_commands() -> None:
    for decision in decisions.DECISIONS:
        name = _command_of(decision.command)
        assert COMMANDS[name]["class"] in ("write", "user_only"), (decision.command, COMMANDS[name])
        if decision.pin or decision.user_words:
            assert COMMANDS[name]["class"] == "user_only", f"{name}：按钮要口令或用户原话，表里也该是 user_only"


def test_tool_buttons_match_their_write_flag() -> None:
    for key, spec in tool_actions.TOOLS.items():
        entry = COMMANDS[spec.label]  # ToolSpec.label 就是命令名（如 "change list"）
        expected = ("write", "user_only") if spec.writes else ("read",)
        assert entry["class"] in expected, (key, spec, entry)


def test_plc_evidence_buttons_are_read_commands() -> None:
    for key, (_label, args) in actions.CHECKS.items():
        name = _command_of(args)
        entry = COMMANDS[name]
        if entry["class"] == "read":
            continue
        # docs sync 本身会写文档；按钮只跑它的 --dry-run 预览
        assert "--dry-run" in args and "--dry-run" in _options(LEAVES[name]), (key, args, entry)


def test_workbench_button_command_is_classified_not_never() -> None:
    assert COMMANDS["gui"]["class"] != "never"


def test_never_commands_have_no_buttons() -> None:
    used = {_command_of(d.command) for d in decisions.DECISIONS}
    used |= {spec.label for spec in tool_actions.TOOLS.values()}
    used |= {_command_of(args) for _label, args in actions.CHECKS.values()}
    never = {name for name, entry in COMMANDS.items() if entry["class"] == "never"}
    assert used & never == set()


# ---- 页面声明 -------------------------------------------------------------------------------------


def test_pages_only_read_read_commands_without_write_flags() -> None:
    keys = [page["key"] for page in PAGES["pages"]]
    assert len(keys) == len(set(keys))
    for page in PAGES["pages"]:
        assert page["group"] in policy.SIDEBAR_GROUPS, page["key"]
        for read in page["reads"]:
            name = read["command"]
            assert name in COMMANDS, (page["key"], name)
            assert COMMANDS[name]["class"] == "read", f"{page['key']} 页读了不是只读的命令 {name}"
            args = read["args"]
            assert not set(args) & set(COMMANDS[name].get("write_flags", [])), (page["key"], name, args)
            for word in args:
                if word.startswith("--"):
                    assert word in _options(LEAVES[name]), f"{name} 没有 {word} 这个选项"
            assert read["reader"] in readers.READERS, (page["key"], read["reader"])
        for data_file in page.get("data_files", []):
            assert (FLOW / data_file).is_file(), (page["key"], data_file)


def test_pages_never_show_zero_or_green_for_unknown() -> None:
    """空态、错态文案不许出现“0”或“正常/通过”之类的绿字，读不到就按三态标签显示。"""
    for page in PAGES["pages"]:
        for text in (page["empty_text"], page["error_text"]):
            assert "0" not in text and "通过" not in text and "正常" not in text, (page["key"], text)


# ---- 脊柱十步 -------------------------------------------------------------------------------------


def test_spine_has_ten_steps_with_known_commands() -> None:
    steps = SPINE["steps"]
    assert [step["n"] for step in steps] == list(range(1, 11))
    external = set(SPINE["external"])
    touch_ids = {item["id"] for item in SPINE["touchpoints"]}
    lane_ids = {item["id"] for item in SPINE["lanes"]}
    for step in [*steps, *SPINE["off_spine"]]:
        for command in step["commands"]:
            assert command in COMMANDS or command in external, (step.get("n", step.get("id")), command)
        assert set(step.get("lanes", [])) <= lane_ids
        if step.get("touch"):
            assert step["touch"] in touch_ids
        assert step["pages"], step


def test_spine_pages_exist() -> None:
    pytest.importorskip("PySide6")
    from cockpit_board import shell

    known = {item.key for item in shell.PAGES} | {page["key"] for page in PAGES["pages"]}
    for step in [*SPINE["steps"], *SPINE["off_spine"]]:
        for key in step["pages"]:
            assert key in known, (step.get("n", step.get("id")), key)
