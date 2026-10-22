"""Plan poka-yoke (计划防呆): seven mandatory fields, refused all at once.

The counter-example is MISSION-D053E7A789FF5928 (DJ-2026-011 报警汇总、复位熄灭,
真 Trae 试跑 2026-10-22): empty declaration, no safety-circuit answer, text-only
acceptance and no rollback.  Such a plan must now be refused with exactly those
four fields named, and the same plan with the fields filled must pass.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli
from auto_pm.core.pm_facade_service import PmFacadeError
from click.testing import CliRunner

from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.plan_checklist import (
    AcceptanceCheck,
    PlanChecklist,
    parse_acceptance_check,
    plan_checklist_problems,
)
from auto_pm.contracts.pm_facade import PlanningExecutionGrant, PmIntent
from auto_pm.domain.change.decision_service import DecisionService, DecisionValidationError
from tests.cli.test_pm_facade import _setup_planning
from tests.core.test_pm_facade_service import _audit_scene, _p10_facade
from tests.plan_checklist_support import full_checklist

SCOPE = ("DJ-2026-011/src/FB_AlarmSummary.st", "DJ-2026-011/docs/变量定义.md")
DJ011_INTENT = PmIntent(
    request_id="REQ-DJ011-ALARM",
    subject_project_id="SW-TEST-001",
    objective="报警汇总，复位后熄灭",
    acceptance_criteria=("任一报警激活时汇总灯亮", "复位且报警消失后汇总灯灭"),
)
DJ011_WORDS = "加一个报警汇总，复位以后灯要灭"
ROLLBACK = "git revert 本次提交，PLC 下载上一版程序"


def _dj011_grant(checklist: PlanChecklist | None, declared: tuple[str, ...] = ()) -> PlanningExecutionGrant:
    return PlanningExecutionGrant(
        adapter=ExecutionAdapterKind.CODEX,
        approved_model="agent-a",
        declared_dirty_paths=declared,
        plan_checklist=checklist,
    )


def _filled(**overrides: object) -> PlanChecklist:
    values: dict[str, object] = {
        "original_request": DJ011_WORDS,
        "safety_circuit": "否",
        "acceptance_checks": (
            AcceptanceCheck(command="python main.py plc check DJ-2026-011", expected_exit_code=0),
            AcceptanceCheck(command="python -m pytest tests/test_alarm_reset.py", expected_exit_code=0),
        ),
        "rollback": ROLLBACK,
    }
    values.update(overrides)
    return PlanChecklist.model_validate(values)


def _problems(checklist: PlanChecklist | None, **kwargs: object) -> tuple[str, ...]:
    arguments: dict[str, object] = {
        "declared": SCOPE,
        "scope": SCOPE,
        "risks": ("复位逻辑改动可能影响其他报警复位",),
        "acceptance_criteria": DJ011_INTENT.acceptance_criteria,
    }
    arguments.update(kwargs)
    return plan_checklist_problems(checklist, **arguments)  # type: ignore[arg-type]


# ── the interlock list itself ────────────────────────────────────────────────


def test_the_dj011_plan_is_refused_with_exactly_its_four_missing_fields() -> None:
    legacy = PlanChecklist(original_request=DJ011_WORDS)

    problems = _problems(legacy, declared=())

    assert [problem[0] for problem in problems] == ["③", "④", "⑤", "⑦"]
    assert "改动声明为空" in problems[0]
    assert "验收 2 条，命令 0 条" in problems[2]


def test_the_dj011_plan_with_every_field_filled_passes() -> None:
    assert _problems(_filled()) == ()


def test_no_checklist_at_all_names_every_missing_field() -> None:
    problems = _problems(None, declared=(), risks=())
    assert [problem[0] for problem in problems] == ["①", "③", "④", "⑤", "⑥", "⑦"]


@pytest.mark.parametrize(
    "placeholder", ["", "  ", "无", "N/A", "none", "-", "待定", "TODO", "无。", "N/A.", "暂无！", "none;", "。"]
)
def test_placeholder_risk_and_rollback_do_not_count(placeholder: str) -> None:
    problems = _problems(_filled(rollback=placeholder), risks=(placeholder,))
    assert [problem[0] for problem in problems] == ["⑥", "⑦"]


def test_a_real_risk_next_to_a_placeholder_is_enough() -> None:
    assert _problems(_filled(), risks=("无", "复位可能误灭其他报警")) == ()


@pytest.mark.parametrize("count", [0, 1, 3])
def test_one_command_per_acceptance_criterion(count: int) -> None:
    checks = tuple(AcceptanceCheck(command=f"cmd {index}", expected_exit_code=0) for index in range(count))
    problems = _problems(_filled(acceptance_checks=checks))
    assert len(problems) == 1 and problems[0].startswith("⑤") and f"命令 {count} 条" in problems[0]


def test_a_blank_command_does_not_count() -> None:
    checks = (
        AcceptanceCheck(command="cmd", expected_exit_code=0),
        AcceptanceCheck(command="  ", expected_exit_code=0),
    )
    assert [problem[0] for problem in _problems(_filled(acceptance_checks=checks))] == ["⑤"]


def test_safety_circuit_accepts_only_yes_or_no() -> None:
    assert _problems(_filled(safety_circuit="是")) == ()
    with pytest.raises(ValueError):
        PlanChecklist(safety_circuit="不确定")  # type: ignore[arg-type]
    assert [problem[0] for problem in _problems(_filled(safety_circuit=""))] == ["④"]


def test_retired_session_file_in_scope_is_named() -> None:
    scope = (*SCOPE, "DJ-2026-011/PM_SESSION_DJ-2026-011.md")
    problems = _problems(_filled(), scope=scope)
    assert [problem[0] for problem in problems] == ["②", "③"]


def test_original_words_must_match_the_inbox_exactly() -> None:
    assert _problems(_filled(), original_words=DJ011_WORDS) == ()
    paraphrased = _problems(_filled(original_request="做报警汇总，复位灭灯"), original_words=DJ011_WORDS)
    assert len(paraphrased) == 1 and "一字不改" in paraphrased[0]


def test_original_words_ignore_only_whitespace_layout() -> None:
    respaced = f"  {DJ011_WORDS[:4]} {DJ011_WORDS[4:]}\n"
    assert _problems(_filled(original_request=respaced), original_words=DJ011_WORDS) == ()
    repunctuated = DJ011_WORDS.replace("，", ",")
    assert len(_problems(_filled(original_request=repunctuated), original_words=DJ011_WORDS)) == 1


def test_a_risk_ending_in_punctuation_is_still_a_real_risk() -> None:
    assert _problems(_filled(rollback="git revert 本次提交。"), risks=("复位可能误灭其他报警。",)) == ()


@pytest.mark.parametrize(
    ("raw", "command", "code"),
    [("python -m pytest => 0", "python -m pytest", 0), ("a => b => 3", "a => b", 3), ("x=>255", "x", 255)],
)
def test_check_parsing(raw: str, command: str, code: int) -> None:
    assert parse_acceptance_check(raw) == AcceptanceCheck(command=command, expected_exit_code=code)


@pytest.mark.parametrize("raw", ["python -m pytest", "cmd => ", "cmd => -1", "cmd => 256", "cmd => zero"])
def test_bad_check_format_is_refused(raw: str) -> None:
    with pytest.raises(ValueError, match="验收命令"):
        parse_acceptance_check(raw)


# ── compatibility of the stored authority ────────────────────────────────────


def test_a_grant_without_checklist_serializes_exactly_as_before() -> None:
    legacy = PlanningExecutionGrant(adapter=ExecutionAdapterKind.CODEX, approved_model="m", declared_dirty_paths=("a.py",))
    assert legacy.model_dump(mode="json") == {
        "adapter": "codex",
        "approved_model": "m",
        "required_worktree_mode": "ISOLATED",
        "declared_dirty_paths": ["a.py"],
    }
    filled = legacy.model_copy(update={"plan_checklist": _filled()})
    assert PlanningExecutionGrant.model_validate(filled.model_dump(mode="json")) == filled


def test_decision_accepts_only_the_old_or_the_checklist_grant_shape() -> None:
    base = {"adapter": "codex", "approved_model": "m", "required_worktree_mode": "ISOLATED", "declared_dirty_paths": []}
    for grant in (base, {**base, "plan_checklist": {}}):
        DecisionService.validate_planning_approval(
            "fubai", "a" * 64, "user-confirmation:chat-20261022-unit", request_id="REQ-1", execution_grant=grant
        )
    with pytest.raises(DecisionValidationError, match="schema"):
        DecisionService.validate_planning_approval(
            "fubai", "a" * 64, "user-confirmation:chat-20261022-unit", request_id="REQ-1", execution_grant={**base, "extra": 1}
        )


# ── the facade entries ───────────────────────────────────────────────────────


def _rows(database: Path) -> dict[str, int]:
    with closing(sqlite3.connect(database)) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("planning_drafts", "planning_scope_cards", "events")
        }


def test_facade_refuses_the_dj011_plan_before_any_write(tmp_path: Path) -> None:
    facade, database, _changes = _p10_facade(tmp_path)
    before = _rows(database)

    with pytest.raises(PmFacadeError) as refusal:
        facade.create_planning_scope_card(
            DJ011_INTENT,
            scope_paths=SCOPE,
            risks=("复位逻辑改动可能影响其他报警复位",),
            non_goals=("不改安全回路",),
            execution_grant=_dj011_grant(PlanChecklist(original_request=DJ011_WORDS)),
        )

    message = str(refusal.value)
    assert message.startswith("计划防呆未通过，缺 4 栏")
    for field in ("③", "④", "⑤", "⑦"):
        assert field in message
    assert _rows(database) == before


def test_facade_accepts_the_same_plan_once_filled_and_records_the_safety_answer(tmp_path: Path) -> None:
    facade, _database, changes = _p10_facade(tmp_path)
    card = facade.create_planning_scope_card(
        DJ011_INTENT,
        scope_paths=SCOPE,
        risks=("复位逻辑改动可能影响其他报警复位",),
        non_goals=("不改安全回路",),
        execution_grant=_dj011_grant(_filled(safety_circuit="是"), declared=SCOPE),
    )
    for state in ("submitted", "under_review", "approved"):
        changes.transition_status(card.change_id, state, approver="fubai", comment="human", project_id="SW-TEST-001")

    decision = facade.approve_planning_scope_card(
        card,
        expected_plan_hash=card.plan_hash,
        approver="fubai",
        approval_evidence_ref="user-confirmation:plan-poka-yoke",
    )

    assert any(item.startswith("safety-circuit: 是") and "安全签字" in item for item in decision.conditions)
    recovered = facade.recover_planning_scope_card(facade.materialize_planning_mission(card).mission_id)
    assert recovered == card
    assert recovered.execution_grant.plan_checklist == _filled(safety_circuit="是")


def test_facade_refuses_a_paraphrased_original_request_from_the_inbox(tmp_path: Path) -> None:
    facade, database, item = _audit_scene(tmp_path)
    before = _rows(database)
    intent = PmIntent(
        request_id="REQ-P03-001",
        subject_project_id="SW-TEST-001",
        objective="Persist a pre-authorization plan.",
        acceptance_criteria=("Replay must be idempotent.",),
    )
    grant = PlanningExecutionGrant(
        adapter=ExecutionAdapterKind.CODEX,
        approved_model="gpt-approved",
        declared_dirty_paths=("auto_pm/example.py",),
        plan_checklist=full_checklist(original="Audit failure, paraphrased"),
    )

    with pytest.raises(PmFacadeError, match="一字不改"):
        facade.create_planning_scope_card(
            intent,
            scope_paths=("auto_pm/example.py",),
            risks=("Drift",),
            non_goals=("No deployment",),
            execution_grant=grant,
            classification=item.classification,
            intake_item_id=item.item_id,
        )
    assert _rows(database) == before


# ── the command line ─────────────────────────────────────────────────────────


def _plan_args(*extra: str) -> list[str]:
    return [
        "plan", "--project-id", "SW-TEST-001", "--request-id", "REQ-CLI-POKA",
        "--objective", "报警汇总", "--acceptance", "汇总灯亮", "--scope", "auto_pm/example.py",
        "--declared-dirty", "auto_pm/example.py", "--risk", "复位可能误灭其他报警",
        "--non-goal", "不改安全回路", "--adapter", "codex", "--approved-model", "agent-a",
        "--kind", "bug", "--domain", "SCPT", *extra,
    ]


def test_pm_plan_without_the_new_fields_lists_them(tmp_path: Path) -> None:
    _setup_planning(tmp_path)
    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "pm", *_plan_args()])

    assert result.exit_code == 1
    assert "计划防呆未通过，缺 4 栏" in result.output
    for field in ("①需求原文", "④是否涉及安全回路", "⑤每条验收标准", "⑦回退办法"):
        assert field in result.output


def test_pm_plan_refuses_an_undecided_safety_answer_and_a_bad_check(tmp_path: Path) -> None:
    _setup_planning(tmp_path)
    base = ("--original-request", "加报警汇总", "--rollback", ROLLBACK)
    undecided = CliRunner().invoke(
        cli, ["-w", str(tmp_path), "pm", *_plan_args(*base, "--safety-circuit", "不确定", "--check", "pytest => 0")]
    )
    bad_check = CliRunner().invoke(
        cli, ["-w", str(tmp_path), "pm", *_plan_args(*base, "--safety-circuit", "否", "--check", "pytest")]
    )

    assert undecided.exit_code == 1 and "缺 1 栏：④" in undecided.output
    assert bad_check.exit_code == 1 and "命令 => 退出码" in bad_check.output


def test_pm_plan_with_all_seven_fields_passes(tmp_path: Path) -> None:
    _setup_planning(tmp_path)
    result = CliRunner().invoke(
        cli,
        [
            "-w", str(tmp_path), "pm",
            *_plan_args(
                "--original-request", "加报警汇总", "--safety-circuit", "否",
                "--check", "python -m pytest tests/test_alarm.py => 0", "--rollback", ROLLBACK,
            ),
        ],
    )

    assert result.exit_code == 0, result.output
    assert '"safety_circuit": "否"' in result.output
