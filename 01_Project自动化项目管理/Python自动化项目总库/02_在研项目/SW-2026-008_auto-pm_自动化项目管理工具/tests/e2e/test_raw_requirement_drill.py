"""Raw-requirement scenario: the user gives one sentence, the IDE agent must get from there to a closed Mission by the cockpit alone.

The D08 prompts spelled out goal, scope, every command and every prohibition.  The user cannot write prompts like that; the
field input is one sentence.  This scenario checks the parts a machine can check: the route the entry skill describes uses
commands that exist, the command-line lane from the sentence to an approved scope card works, and the two gaps found while an
AI played Trae with only the sentence and the skill (no command-line verify/close for an IDE agent; approval evidence that is
only format-checked) are pinned as known defects.  Whether a real Trae finds its way is decided by the field trial
(``/mnt/project-files/plans/原始需求直接交给Trae_评估_20261021.md`` §4), not here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.e2e.test_closure_drill import APPROVER, MAIN_DOMAIN, comment_files, make_drill
from tests.e2e.test_pmf_plc import (
    PROJECT,
    PROJECT_ID,
    benchmark_tar,  # noqa: F401 - module fixture re-used by name
    git,
)

SENTENCE = "公共报警加一个蜂鸣器输出，任意报警激活时响"
NO_IDE_LANE = (
    "缺口⑧（原始需求场景新发现，技术债候选，未开卡）：批准之后，IDE 里的 agent（Trae 等，40 号文定的主路径）没有命令可走："
    "pm execute / CockpitClient.run 只会启动 Codex 执行器（已挂起），核验 verify_for_acceptance 与收口 close_accepted 没有命令行入口，"
    "agent 只能写临时 Python 调内部函数（D08 第 2 道因此把 __pycache__ 写进发布目录、自己手工拷回控制根）"
)
SELF_SIGNED = (
    "缺口⑨（原始需求场景新发现，技术债候选，未开卡）：命令行批准只检查证据引用的格式（user-confirmation: 加 8 个字符以上）和批准人名字里"
    "不含 agent/model 等字样；agent 填用户名和自编的引用就能批准，用户本人没有说过“开工”也拦不住。界面按钮生成的证据才是用户亲手点的"
)


def _skill_text() -> str:
    repository = Path(git(Path(__file__).resolve().parent, "rev-parse", "--show-toplevel"))
    return (repository / ".trae" / "skills" / "cockpit-entry" / "SKILL.md").read_text(encoding="utf-8")


def _pm_commands(drill) -> set[str]:  # type: ignore[no-untyped-def]
    listed = drill.cli("pm", "--help")
    assert listed.returncode == 0, drill.transcript()
    section = listed.stdout.split("Commands:", 1)[1]
    return {match.group(1) for match in re.finditer(r"^\s{2}([a-z][a-z-]*)\s", section, re.MULTILINE)}


def _approve_from_one_sentence(drill, request_id: str):  # type: ignore[no-untyped-def]
    """What the skill's route makes an agent do with the sentence, using command-line calls only."""

    files = comment_files(drill.root, "原始需求")
    added = drill.cli(
        "pm", "inbox", "add", "--project-id", PROJECT_ID, "--request-id", request_id, "--title", "公共报警加蜂鸣器输出",
        "--kind", "iteration", "--domain", MAIN_DOMAIN, "--original-words", SENTENCE, "--affects", "公共报警块 FB_2001",
        "--duplicate-check", "查过收件箱与台账，没有同类条目", "--evidence", f"file:{PROJECT}/.plc.json",
        "--disposition", "after_current", "--rationale", "用户提出", "--alternative", "不做", "--cost-risk", "低：只改一个块",
    )
    assert added.returncode == 0, drill.transcript()
    item = added.json()["item"]
    confirmed = drill.cli(
        "pm", "inbox", "confirm", item["item_id"], "--ticket-hash", item["ticket_hash"], "--approver", APPROVER,
        "--approval-evidence-ref", f"user-confirmation:chat-{request_id}",
    )
    assert confirmed.returncode == 0, drill.transcript()
    plan = [
        "pm", "plan", "--project-id", PROJECT_ID, "--request-id", request_id, "--objective", SENTENCE,
        "--acceptance", f"main.py plc check {PROJECT_ID} 退出码 0", "--risk", "只动公共报警块", "--non-goal", "不下载到控制器",
        "--adapter", "trae", "--approved-model", "trae", "--inbox-id", item["item_id"],
    ]
    for path in files:
        plan += ["--scope", path, "--declared-dirty", path]
    planned = drill.cli(*plan)
    assert planned.returncode == 0, drill.transcript()
    card = planned.json()
    approved = drill.cli(
        "pm", "approve", "--request-id", request_id, "--plan-hash", card["plan_hash"], "--approver", APPROVER,
        "--approval-evidence-ref", f"user-confirmation:chat-{request_id}",
    )
    return card, approved


def test_r05_every_pm_command_the_entry_skill_names_exists(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    commands = _pm_commands(drill)
    named = set(re.findall(r"pm ([a-z][a-z-]*)", _skill_text()))
    assert {"orient", "inbox", "plan", "approve", "handoff", "takeover"} <= named, named
    assert named <= commands, f"技能里写了但驾驶舱没有的 pm 命令: {sorted(named - commands)}"
    for phrase in ("--original-words", "--pid", "close_accepted", "ledger reconcile", "plc check", "user-confirmation:"):
        assert phrase in _skill_text(), phrase


def test_r06_one_sentence_reaches_an_approved_scope_card_by_command_line_alone(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    card, approved = _approve_from_one_sentence(drill, "REQ-RAW-R06")
    assert approved.returncode == 0, drill.transcript()
    assert approved.json()["authorization_status"] == "AUTHORIZED"
    assert card["change_id"].startswith(f"CHG-{MAIN_DOMAIN}-")


@pytest.mark.xfail(strict=True, reason=NO_IDE_LANE)
def test_r07_an_ide_agent_can_verify_and_close_by_command_line(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    commands = _pm_commands(drill)
    missing = {"verify", "close"} - commands
    assert not missing, f"pm 下没有 IDE agent 用的命令: {sorted(missing)}"


@pytest.mark.xfail(strict=True, reason=SELF_SIGNED)
def test_r08_command_line_approval_needs_the_users_own_act(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    _card, approved = _approve_from_one_sentence(drill, "REQ-RAW-R08")
    # The drill runs without a terminal and without a cockpit click, so nothing proves a human approved.
    assert approved.returncode != 0, "没有用户亲手操作的证据，批准却被接受了"
