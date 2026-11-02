"""Plan poka-yoke (计划防呆): seven mandatory fields, all checked at once.

Like a machine's start permissives, a plan may only be planned or approved
when every interlock is made; otherwise the refusal lists each missing field
by number, the way an HMI lists unmet start conditions.  Plan, preview,
submit, approve and approve-by-hash all call :func:`plan_checklist_problems`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from auto_pm.contracts.declared_dirty import declared_dirty_problem, retired_session_paths

__all__ = [
    "SAFETY_CIRCUIT_CHOICES",
    "AcceptanceCheck",
    "PlanChecklist",
    "parse_acceptance_check",
    "plan_checklist_problems",
    "plan_checklist_refusal",
]

SAFETY_CIRCUIT_CHOICES = ("是", "否")
_PLACEHOLDERS = frozenset(
    {"无", "没有", "暂无", "无风险", "略", "同上", "待定", "待补", "-", "—", "--", "/",
     "none", "n/a", "na", "nil", "tbd", "todo", "null"}
)


class AcceptanceCheck(BaseModel):
    """One machine-judged acceptance: a command and the exit code that means pass."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    command: str
    expected_exit_code: int = Field(ge=0, le=255)


class PlanChecklist(BaseModel):
    """The plan fields that used to be free text in chat (④⑤⑦ plus ① the user's words).

    Fields stay lenient here so one check can report every missing field at once.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    original_request: str = ""
    safety_circuit: Literal["", "是", "否"] = ""
    acceptance_checks: tuple[AcceptanceCheck, ...] = ()
    rollback: str = ""


def parse_acceptance_check(raw: str) -> AcceptanceCheck:
    """Parse ``"命令 => 退出码"``; raise ValueError with a readable reason."""

    command, separator, code = raw.rpartition("=>")
    if not separator:
        raise ValueError(f"验收命令格式应为“命令 => 退出码”: {raw}")
    code = code.strip()
    if not code.isdigit() or not 0 <= int(code) <= 255:
        raise ValueError(f"验收命令的退出码必须是 0～255 的整数: {raw}")
    return AcceptanceCheck(command=command.strip(), expected_exit_code=int(code))


_TRAILING_PUNCTUATION = "。．.，,；;！!？?、…~～ "


def _blank(value: str) -> bool:
    text = value.strip().rstrip(_TRAILING_PUNCTUATION).strip().lower()
    return not text or text in _PLACEHOLDERS


def _same_words(left: str, right: str) -> bool:
    """Compare the user's words verbatim except for whitespace layout."""

    return "".join(left.split()) == "".join(right.split())


def plan_checklist_problems(
    checklist: PlanChecklist | None,
    *,
    declared: Iterable[str],
    scope: Iterable[str],
    risks: Iterable[str],
    acceptance_criteria: Iterable[str],
    original_words: str | None = None,
) -> tuple[str, ...]:
    """Return one line per unmet field, numbered ①～⑦; empty when the plan may proceed."""

    items = checklist or PlanChecklist()
    scope_paths = tuple(scope)
    criteria = tuple(acceptance_criteria)
    problems: list[str] = []
    if _blank(items.original_request):
        problems.append("①需求原文（--original-request，照抄用户原话）")
    elif original_words is not None and not _same_words(items.original_request, original_words):
        problems.append("①需求原文与收件箱里登记的用户原话不一致，须一字不改照抄")
    if not scope_paths:
        problems.append("②可改范围（--scope）")
    elif retired_session_paths(scope_paths):
        problems.append("②可改范围含已退役的 PM_SESSION_*.md")
    declared_problem = declared_dirty_problem(tuple(declared), scope=scope_paths)
    if declared_problem:
        problems.append(f"③{declared_problem}")
    if items.safety_circuit not in SAFETY_CIRCUIT_CHOICES:
        problems.append("④是否涉及安全回路（--safety-circuit 只能填 是 或 否）")
    checks = items.acceptance_checks
    if len(checks) != len(criteria) or any(not check.command.strip() for check in checks):
        problems.append(
            f"⑤每条验收标准的命令和退出码（--check \"命令 => 退出码\"；"
            f"验收 {len(criteria)} 条，命令 {len(checks)} 条）"
        )
    risk_items = tuple(risks)
    if not risk_items or all(_blank(risk) for risk in risk_items):
        problems.append("⑥风险（--risk，不能只写“无”）")
    if _blank(items.rollback):
        problems.append("⑦回退办法（--rollback）")
    return tuple(problems)


def plan_checklist_refusal(problems: tuple[str, ...]) -> str:
    """Render all unmet fields in one message."""

    return f"计划防呆未通过，缺 {len(problems)} 栏：" + "；".join(problems)
