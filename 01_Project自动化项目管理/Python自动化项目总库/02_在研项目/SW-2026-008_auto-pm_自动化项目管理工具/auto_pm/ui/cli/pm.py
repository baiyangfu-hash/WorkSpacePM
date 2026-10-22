"""Compact PM cold-start commands."""

from __future__ import annotations

import hmac
import json
import os
from collections.abc import Callable
from typing import Any, TypeVar, cast

import click
from click.core import ParameterSource

from auto_pm.app_context import AppContext
from auto_pm.change.change_service import ChangeService
from auto_pm.change.constants import TransitionGuardError
from auto_pm.contracts.continuity_query import QueriedAction
from auto_pm.contracts.continuity_resume import ContinuityResume, validate_query_resume
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.intake import (
    ChangeAction,
    Disposition,
    IntakeClassification,
    IntakeKind,
    IntakeStatus,
    TriageTicket,
    UrgentCriterion,
)
from auto_pm.contracts.plan_checklist import (
    SAFETY_CIRCUIT_CHOICES,
    PlanChecklist,
    parse_acceptance_check,
)
from auto_pm.contracts.pm_facade import PlanningExecutionGrant, PlanningScopeCard, PmIntent
from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.core.pm_intake_service import PmIntakeError, PmIntakeService
from auto_pm.core.pm_resume_service import PmResumeError, PmResumeService
from auto_pm.core.workspace_context_service import WorkspaceContextError, WorkspaceContextService
from auto_pm.core.worktree_policy_service import WorktreePolicyError, WorktreePolicyService
from auto_pm.domain.change.decision_service import DecisionError, DecisionService
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.ui.cli.approval_pin import approval_pin_enforced, read_approval_pin

_F = TypeVar("_F", bound=Callable[..., Any])
_KIND_CHOICES = tuple(item.value.lower() for item in IntakeKind)
_ACTION_CHOICES = tuple(item.value.lower() for item in ChangeAction)


@click.group(name="pm")
def pm_group() -> None:
    """面向用户的 PM 门面：计划、确认、执行、恢复与验收。"""


def _facade(ctx: click.Context) -> PmFacadeService:
    app_ctx: AppContext = ctx.find_root().obj
    return PmFacadeService(
        app_ctx.control_root,
        execution_root=app_ctx.workspace_root,
    )


def _control_root_path(ctx: click.Context) -> str:
    """The root the Facade writes to; the approval PIN is looked up in the same root (audit 72, high-2)."""

    app_ctx: AppContext = ctx.find_root().obj
    return str(app_ctx.control_root)


def _require_control_root(ctx: click.Context) -> None:
    app_ctx: AppContext = ctx.find_root().obj
    WorktreePolicyService(app_ctx.control_root).require_control_root()


def _classification_options(function: _F) -> _F:
    """Add the options that classify a plan request (shared by ``plan`` and ``approve``)."""

    options = (
        click.option(
            "--kind",
            type=click.Choice(_KIND_CHOICES, case_sensitive=False),
            default=None,
            help="分类：iteration 正常迭代 | bug 缺陷 | change 功能变更 | urgent 紧急 | debt 技术债",
        ),
        click.option(
            "--change-action",
            type=click.Choice(_ACTION_CHOICES, case_sensitive=False),
            default=None,
            help="功能变更的动作（仅 --kind change）：add 增加 | modify 修改 | reduce 减少 | freeze 冻结 | remove 移除",
        ),
        click.option("--domain", default="", help="技术领域；缺省时按项目技术栈推断"),
        click.option(
            "--impact-scope", "impact_scope", multiple=True, help="影响范围，可重复；缺省 MODULE"
        ),
        click.option("--inbox-id", default="", help="把一条已确认的收件箱条目转为本计划"),
    )
    for option in reversed(options):
        function = option(function)
    return function


def _checklist_options(function: _F) -> _F:
    """Add the plan poka-yoke fields (计划防呆必填栏) shared by ``plan`` and ``approve``."""

    options = (
        click.option("--original-request", default="", help="①需求原文：一字不改照抄用户原话"),
        click.option(
            "--safety-circuit", default="", help="④是否涉及安全回路（急停/安全门/光栅/联锁等）：只能填 是 或 否"
        ),
        click.option(
            "--check",
            "checks",
            multiple=True,
            help="⑤验收命令，格式“命令 => 退出码”，按 --acceptance 的顺序一条对一条，可重复",
        ),
        click.option("--rollback", default="", help="⑦回退办法：出问题时怎么退回去"),
    )
    for option in reversed(options):
        function = option(function)
    return function


def _plan_checklist(
    original_request: str, safety_circuit: str, checks: tuple[str, ...], rollback: str
) -> PlanChecklist:
    try:
        parsed = tuple(parse_acceptance_check(raw) for raw in checks)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    safety = safety_circuit.strip()
    return PlanChecklist(
        original_request=original_request,
        safety_circuit=safety if safety in SAFETY_CIRCUIT_CHOICES else "",
        acceptance_checks=parsed,
        rollback=rollback,
    )


def _enum_or_none(enum_type: Any, value: str | None) -> Any:
    return None if value is None else enum_type(value.upper())


def _resolve_filing(
    ctx: click.Context,
    *,
    project_id: str,
    request_id: str,
    kind: str | None,
    change_action: str | None,
    domain: str,
    impact_scope: tuple[str, ...],
    inbox_id: str,
    from_draft: bool,
) -> tuple[IntakeClassification, str]:
    """Decide how a plan request is filed; a request nothing classifies is refused."""

    app_ctx: AppContext = ctx.find_root().obj
    try:
        _require_control_root(ctx)
        if from_draft:
            project_id = (
                ContinuityStore(app_ctx.control_root).get_planning_draft(request_id).subject_project_id
            )
        classification, item_id = PmIntakeService(app_ctx.control_root).plan_classification(
            project_id,
            request_id=request_id,
            kind=_enum_or_none(IntakeKind, kind),
            change_action=_enum_or_none(ChangeAction, change_action),
            domain=domain,
            impact_scope=impact_scope,
            inbox_id=inbox_id,
        )
    except (PmIntakeError, ContinuityStoreError, ValueError, WorktreePolicyError) as error:
        raise click.ClickException(str(error)) from error
    if classification is None:
        raise click.ClickException(
            "新需求必须分类：请给出 --kind（iteration|bug|change|urgent|debt）或 --inbox-id"
        )
    return classification, item_id


def _emit_card(ctx: click.Context, action: str, mission_id: str, root_work_id: str = "") -> None:
    try:
        _require_control_root(ctx)
        facade = _facade(ctx)
        if action == "plan":
            card = facade.plan(mission_id)
        elif action == "approve":
            card = facade.approve(mission_id, root_work_id)
        elif action == "confirm-start":
            card = facade.confirm_start(mission_id)
        elif action == "execute":
            card = facade.execute(mission_id)
        elif action == "accept":
            card = facade.accept(mission_id)
        else:  # pragma: no cover - static command wiring
            raise RuntimeError(f"unknown PM action: {action}")
    except (PmFacadeError, WorktreePolicyError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(card.model_dump_json(indent=2))


def _planning_scope_card(
    ctx: click.Context,
    *,
    project_id: str,
    request_id: str,
    objective: str,
    acceptance: tuple[str, ...],
    scope_paths: tuple[str, ...],
    risks: tuple[str, ...],
    non_goals: tuple[str, ...],
    adapter: str | None,
    approved_model: str,
    declared_dirty_paths: tuple[str, ...],
    plan_checklist: PlanChecklist,
    classification: IntakeClassification | None = None,
    intake_item_id: str = "",
    preview_only: bool = False,
) -> PlanningScopeCard:
    missing = [
        name
        for name, value in (
            ("--project-id", project_id),
            ("--request-id", request_id),
            ("--objective", objective),
            ("--acceptance", acceptance),
            ("--scope", scope_paths),
            ("--risk", risks),
            ("--non-goal", non_goals),
            ("--adapter", adapter),
            ("--approved-model", approved_model),
        )
        if not value
    ]
    if missing:
        raise click.ClickException(
            "新需求 plan 缺少必填参数: " + ", ".join(missing)
        )
    try:
        _require_control_root(ctx)
        intent = PmIntent(
            subject_project_id=project_id,
            request_id=request_id,
            objective=objective,
            acceptance_criteria=acceptance,
        )
        facade = _facade(ctx)
        build = (
            facade.preview_planning_scope_card if preview_only else facade.create_planning_scope_card
        )
        return cast(
            PlanningScopeCard,
            build(
                intent,
                scope_paths=scope_paths,
                risks=risks,
                non_goals=non_goals,
                execution_grant=PlanningExecutionGrant(
                    adapter=ExecutionAdapterKind(cast(str, adapter)),
                    approved_model=approved_model,
                    declared_dirty_paths=declared_dirty_paths,
                    plan_checklist=plan_checklist,
                ),
                classification=classification,
                intake_item_id=intake_item_id,
            ),
        )
    except (PmFacadeError, ValueError, WorktreePolicyError) as error:
        raise click.ClickException(str(error)) from error


def _submit_scope_card(
    ctx: click.Context,
    *,
    request_id: str,
    project_id: str,
    objective: str,
    acceptance: tuple[str, ...],
    scope_paths: tuple[str, ...],
    risks: tuple[str, ...],
    non_goals: tuple[str, ...],
    adapter: str | None,
    approved_model: str,
    declared_dirty_paths: tuple[str, ...],
    plan_checklist: PlanChecklist,
    submitted_by: str,
    from_draft: bool,
    classification: IntakeClassification,
    intake_item_id: str,
) -> PlanningScopeCard:
    """Persist the scope card of a draft (creating the draft first unless it already exists)."""
    try:
        _require_control_root(ctx)
        facade = _facade(ctx)
        if not from_draft:
            facade.create_planning_draft(
                PmIntent(
                    subject_project_id=project_id,
                    request_id=request_id,
                    objective=objective,
                    acceptance_criteria=acceptance,
                )
            )
        submitted = facade.submit_planning_scope_card(
            request_id,
            scope_paths=scope_paths,
            risks=risks,
            non_goals=non_goals,
            execution_grant=PlanningExecutionGrant(
                adapter=ExecutionAdapterKind(cast(str, adapter)),
                approved_model=approved_model,
                declared_dirty_paths=declared_dirty_paths,
                plan_checklist=plan_checklist,
            ),
            submitted_by=submitted_by,
            classification=classification,
            intake_item_id=intake_item_id,
        )
    except (PmFacadeError, ValueError, WorktreePolicyError) as error:
        raise click.ClickException(str(error)) from error
    return cast(PlanningScopeCard, submitted.card)


def _emit_plan_approval(card: PlanningScopeCard, work_state: str) -> None:
    click.echo(
        json.dumps(
            {
                "schema_version": "pm-plan-approval.v1",
                "request_id": card.request_id,
                "subject_project_id": card.subject_project_id,
                "change_id": card.change_id,
                "plan_hash": card.plan_hash,
                "authorization_status": "AUTHORIZED",
                "work_state": work_state,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _approve_planning_change(ctx: click.Context, card: PlanningScopeCard, approver: str) -> None:
    app_ctx: AppContext = ctx.find_root().obj
    changes = ChangeService(str(app_ctx.control_root))
    change = changes.get_change_request(card.change_id, project_id=card.subject_project_id)
    if change is None:
        raise click.ClickException("PlanningScopeCard 绑定的 CHG 不存在")
    remaining = {
        "draft": ("submitted", "under_review", "approved"),
        "submitted": ("under_review", "approved"),
        "under_review": ("approved",),
    }
    try:
        for state in remaining.get(change.status, ()):
            change = changes.transition_status(
                card.change_id,
                state,
                approver=approver,
                comment=f"user approved planning scope {card.plan_hash}",
                project_id=card.subject_project_id,
            )
    except (TransitionGuardError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    if change.status not in {
        "approved",
        "implementing",
        "pending_acceptance",
        "accepting",
        "completed",
    }:
        raise click.ClickException(f"PlanningScopeCard 绑定的 CHG 不可批准: {change.status}")


@pm_group.command(name="plan")
@click.option("--mission-id", default="", help="兼容旧入口：已有 Mission 编号")
@click.option("--project-id", default="", help="新需求所属项目 PID")
@click.option("--request-id", default="", help="用户请求幂等标识")
@click.option("--objective", default="", help="新需求目标")
@click.option("--acceptance", multiple=True, help="验收条件，可重复")
@click.option("--scope", "scope_paths", multiple=True, help="精确文件范围，可重复")
@click.option("--risk", "risks", multiple=True, help="明确风险，可重复")
@click.option("--non-goal", "non_goals", multiple=True, help="非目标，可重复")
@click.option(
    "--adapter",
    type=click.Choice(tuple(item.value for item in ExecutionAdapterKind)),
    default=None,
)
@click.option("--approved-model", default="")
@click.option("--declared-dirty", "declared_dirty_paths", multiple=True)
@click.option("--submitted-by", default="pm-cli", show_default=True, help="范围卡提交者标识，写入事件链")
@_checklist_options
@_classification_options
@click.pass_context
def plan_pm(
    ctx: click.Context,
    mission_id: str,
    project_id: str,
    request_id: str,
    objective: str,
    acceptance: tuple[str, ...],
    scope_paths: tuple[str, ...],
    risks: tuple[str, ...],
    non_goals: tuple[str, ...],
    adapter: str | None,
    approved_model: str,
    declared_dirty_paths: tuple[str, ...],
    submitted_by: str,
    original_request: str,
    safety_circuit: str,
    checks: tuple[str, ...],
    rollback: str,
    kind: str | None,
    change_action: str | None,
    domain: str,
    impact_scope: tuple[str, ...],
    inbox_id: str,
) -> None:
    """创建/恢复并持久化新需求范围卡，或兼容已有 Mission 调用。

    只给 --request-id（不给 --project-id/--objective/--acceptance）时，为已保存的草稿
    （例如驾驶舱保存的草稿）起草并持久化范围卡。新需求必须分类（--kind 或 --inbox-id）。
    """
    new_values = (
        project_id,
        request_id,
        objective,
        acceptance,
        scope_paths,
        risks,
        non_goals,
        adapter,
        approved_model,
        declared_dirty_paths,
        kind,
        change_action,
        domain,
        impact_scope,
        inbox_id,
        original_request,
        safety_circuit,
        checks,
        rollback,
    )
    if mission_id:
        if any(new_values):
            raise click.ClickException("--mission-id 不能与新需求参数混用")
        _emit_card(ctx, "plan", mission_id)
        return
    from_draft = bool(request_id) and not any((project_id, objective, acceptance))
    required = [
        ("--scope", scope_paths),
        ("--risk", risks),
        ("--non-goal", non_goals),
        ("--adapter", adapter),
        ("--approved-model", approved_model),
    ]
    if not from_draft:
        required = [
            ("--project-id", project_id),
            ("--request-id", request_id),
            ("--objective", objective),
            ("--acceptance", acceptance),
            *required,
        ]
    missing = [name for name, value in required if not value]
    if missing:
        raise click.ClickException(
            ("按已保存草稿提交范围卡缺少必填参数: " if from_draft else "新需求 plan 缺少必填参数: ")
            + ", ".join(missing)
        )
    classification, intake_item_id = _resolve_filing(
        ctx,
        project_id=project_id,
        request_id=request_id,
        kind=kind,
        change_action=change_action,
        domain=domain,
        impact_scope=impact_scope,
        inbox_id=inbox_id,
        from_draft=from_draft,
    )
    card = _submit_scope_card(
        ctx,
        request_id=request_id,
        project_id=project_id,
        objective=objective,
        acceptance=acceptance,
        scope_paths=scope_paths,
        risks=risks,
        non_goals=non_goals,
        adapter=adapter,
        approved_model=approved_model,
        declared_dirty_paths=declared_dirty_paths,
        plan_checklist=_plan_checklist(original_request, safety_circuit, checks, rollback),
        submitted_by=submitted_by,
        from_draft=from_draft,
        classification=classification,
        intake_item_id=intake_item_id,
    )
    click.echo(card.model_dump_json(indent=2))


@pm_group.command(name="drafts")
@click.option("--project-id", required=True, help="项目 PID")
@click.pass_context
def drafts_pm(ctx: click.Context, project_id: str) -> None:
    """列出项目的全部规划草稿（含驾驶舱保存的草稿）及其范围卡阶段。"""
    try:
        _require_control_root(ctx)
        overview = _facade(ctx).list_planning_drafts(project_id)
    except (PmFacadeError, WorktreePolicyError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        json.dumps(
            {
                "schema_version": "pm-planning-drafts.v1",
                "project_id": project_id,
                "drafts": [item.model_dump(mode="json") for item in overview],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@pm_group.command(name="pending")
@click.option("--project-id", required=True, help="项目 PID")
@click.pass_context
def pending_pm(ctx: click.Context, project_id: str) -> None:
    """列出项目中等待批准的最新范围卡。"""
    try:
        _require_control_root(ctx)
        cards = _facade(ctx).list_pending_planning_scope_cards(project_id)
    except (PmFacadeError, WorktreePolicyError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        json.dumps(
            {
                "schema_version": "pm-pending-scope-cards.v1",
                "project_id": project_id,
                "cards": [item.model_dump(mode="json") for item in cards],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


_STATUS_CHOICES = tuple(item.value.lower() for item in IntakeStatus)
_DISPOSITION_CHOICES = tuple(item.value.lower() for item in Disposition)
_CRITERION_CHOICES = tuple(item.value.lower() for item in UrgentCriterion)


@pm_group.group(name="inbox")
def inbox_group() -> None:
    """收件箱：新需求、bug、想法先入箱并附分诊单；入箱不改变当前焦点。"""


def _intake(ctx: click.Context) -> PmIntakeService:
    app_ctx: AppContext = ctx.find_root().obj
    _require_control_root(ctx)
    return PmIntakeService(app_ctx.control_root)


def _emit_item(item_json: dict[str, Any], *, created: bool | None = None) -> None:
    payload: dict[str, Any] = {"schema_version": "pm-inbox-item.v1"}
    if created is not None:
        payload["created"] = created
    payload["item"] = item_json
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@inbox_group.command(name="add")
@click.option("--project-id", required=True, help="项目 PID")
@click.option("--request-id", required=True, help="幂等标识；同一标识重放同一内容不会重复入箱")
@click.option("--title", required=True, help="一行标题（至多 120 字）")
@click.option("--kind", required=True, type=click.Choice(_KIND_CHOICES, case_sensitive=False))
@click.option("--change-action", type=click.Choice(_ACTION_CHOICES, case_sensitive=False), default=None)
@click.option("--domain", default="", help="技术领域；缺省时按项目技术栈推断")
@click.option("--impact-scope", "impact_scope", multiple=True, help="影响范围，可重复；缺省 MODULE")
@click.option("--original-words", required=True, help="用户原话")
@click.option("--affects", required=True, help="影响了什么（项目、WBS 行、文件、依赖）")
@click.option("--duplicate-check", required=True, help="查重做了什么、结论是什么")
@click.option("--duplicate-of", "duplicate_of", multiple=True, help="与之重复的条目、台账或变更单编号")
@click.option("--evidence", "evidence", multiple=True, help="取证，可重复：file:|cmd:|ledger:|chg:|commit:")
@click.option(
    "--urgent-criterion",
    type=click.Choice(_CRITERION_CHOICES, case_sensitive=False),
    default=None,
    help="仅 urgent：safety|data_loss|blocks_all|wrong_output",
)
@click.option(
    "--disposition",
    required=True,
    type=click.Choice(_DISPOSITION_CHOICES, case_sensitive=False),
    help="建议处置：interrupt_now|after_current|inbox_wait|reject",
)
@click.option("--rationale", required=True, help="建议的理由")
@click.option("--alternative", "alternatives", multiple=True, help="备选方案，至少一个")
@click.option("--cost-risk", required=True, help="成本与风险估计")
@click.option("--ask", "decisions_for_user", multiple=True, help="需要用户决定的点，可重复")
@click.option("--proposed-by", default="pm-cli", show_default=True, help="提出者标识")
@click.pass_context
def inbox_add(
    ctx: click.Context,
    project_id: str,
    request_id: str,
    title: str,
    kind: str,
    change_action: str | None,
    domain: str,
    impact_scope: tuple[str, ...],
    original_words: str,
    affects: str,
    duplicate_check: str,
    duplicate_of: tuple[str, ...],
    evidence: tuple[str, ...],
    urgent_criterion: str | None,
    disposition: str,
    rationale: str,
    alternatives: tuple[str, ...],
    cost_risk: str,
    decisions_for_user: tuple[str, ...],
    proposed_by: str,
) -> None:
    """把一条新事项连同分诊单记入收件箱（状态 PROPOSED，等待用户确认）。"""
    try:
        service = _intake(ctx)
        classification = service.classify(
            project_id,
            kind=IntakeKind(kind.upper()),
            change_action=_enum_or_none(ChangeAction, change_action),
            domain=domain,
            impact_scope=impact_scope,
        )
        ticket = TriageTicket(
            original_words=original_words,
            affects=affects,
            duplicate_check=duplicate_check,
            duplicate_of=duplicate_of,
            evidence=evidence,
            urgent_criterion=_enum_or_none(UrgentCriterion, urgent_criterion),
            disposition=Disposition(disposition.upper()),
            rationale=rationale,
            alternatives=alternatives,
            cost_risk=cost_risk,
            decisions_for_user=decisions_for_user,
        )
        item, created = service.propose(
            request_id=request_id,
            project_id=project_id,
            title=title,
            classification=classification,
            ticket=ticket,
            proposed_by=proposed_by,
        )
    except (PmIntakeError, ValueError, WorktreePolicyError) as error:
        raise click.ClickException(str(error)) from error
    _emit_item(item.model_dump(mode="json"), created=created)


@inbox_group.command(name="list")
@click.option("--project-id", required=True, help="项目 PID")
@click.option(
    "--status",
    "statuses",
    multiple=True,
    type=click.Choice(_STATUS_CHOICES, case_sensitive=False),
    help="按状态过滤，可重复；缺省列出未处理的（proposed、confirmed）",
)
@click.pass_context
def inbox_list(ctx: click.Context, project_id: str, statuses: tuple[str, ...]) -> None:
    """列出项目的收件箱条目。"""
    try:
        service = _intake(ctx)
        wanted = tuple(IntakeStatus(item.upper()) for item in statuses)
        items = service.list_items(project_id, wanted) if wanted else service.list_items(project_id)
    except (PmIntakeError, WorktreePolicyError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        json.dumps(
            {
                "schema_version": "pm-inbox.v1",
                "project_id": project_id,
                "items": [item.model_dump(mode="json") for item in items],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@inbox_group.command(name="show")
@click.argument("item_id")
@click.pass_context
def inbox_show(ctx: click.Context, item_id: str) -> None:
    """显示一条收件箱条目的完整分诊单与 ticket_hash。"""
    try:
        item = _intake(ctx).get(item_id)
    except (PmIntakeError, WorktreePolicyError) as error:
        raise click.ClickException(str(error)) from error
    _emit_item(item.model_dump(mode="json"))


def _decide_options(function: _F) -> _F:
    options = (
        click.argument("item_id"),
        click.option("--ticket-hash", required=True, help="用户看到并确认的条目内容哈希"),
        click.option("--approver", required=True, help="真实人类审批人"),
        click.option(
            "--approval-evidence-ref",
            required=True,
            help="非模型自签的 user-confirmation 证据引用",
        ),
        click.option("--note", default="", help="一行备注"),
    )
    for option in reversed(options):
        function = option(function)
    return function


@inbox_group.command(name="confirm")
@_decide_options
@click.pass_context
def inbox_confirm(
    ctx: click.Context,
    item_id: str,
    ticket_hash: str,
    approver: str,
    approval_evidence_ref: str,
    note: str,
) -> None:
    """记录用户对该分诊单的确认（须引用 user-confirmation 证据）。"""
    try:
        item = _intake(ctx).confirm(
            item_id,
            ticket_hash=ticket_hash,
            approver=approver,
            approval_evidence_ref=approval_evidence_ref,
            note=note,
        )
    except (PmIntakeError, WorktreePolicyError) as error:
        raise click.ClickException(str(error)) from error
    _emit_item(item.model_dump(mode="json"))


@inbox_group.command(name="reject")
@_decide_options
@click.pass_context
def inbox_reject(
    ctx: click.Context,
    item_id: str,
    ticket_hash: str,
    approver: str,
    approval_evidence_ref: str,
    note: str,
) -> None:
    """记录用户对该分诊单的驳回（须引用 user-confirmation 证据）。"""
    try:
        item = _intake(ctx).reject(
            item_id,
            ticket_hash=ticket_hash,
            approver=approver,
            approval_evidence_ref=approval_evidence_ref,
            note=note,
        )
    except (PmIntakeError, WorktreePolicyError) as error:
        raise click.ClickException(str(error)) from error
    _emit_item(item.model_dump(mode="json"))


@pm_group.command(name="approve")
@click.option("--mission-id", default="", help="兼容旧入口：已有 Mission 编号")
@click.option(
    "--root-work-id",
    default="",
    help="兼容旧入口；新 Mission 已在创建时绑定内部授权，无需填写。",
)
@click.option("--project-id", default="", help="新需求所属项目 PID")
@click.option("--request-id", default="", help="用户请求幂等标识")
@click.option("--objective", default="", help="新需求目标")
@click.option("--acceptance", multiple=True, help="验收条件，可重复")
@click.option("--scope", "scope_paths", multiple=True, help="精确文件范围，可重复")
@click.option("--risk", "risks", multiple=True, help="明确风险，可重复")
@click.option("--non-goal", "non_goals", multiple=True, help="非目标，可重复")
@click.option(
    "--adapter",
    type=click.Choice(tuple(item.value for item in ExecutionAdapterKind)),
    default=None,
)
@click.option("--approved-model", default="")
@click.option("--declared-dirty", "declared_dirty_paths", multiple=True)
@click.option("--plan-hash", default="", help="plan 输出的不可变方案哈希")
@click.option("--approver", default="", help="真实人类审批人（已启用批准口令时由口令决定，可不填）")
@click.option(
    "--approval-evidence-ref",
    default="",
    help="非模型自签的 user-confirmation 证据引用（已启用批准口令时由口令生成，可不填）",
)
@click.option("--owner", default="PM Facade", show_default=True, help="内部 Work owner")
@_checklist_options
@_classification_options
@click.pass_context
def approve_pm(
    ctx: click.Context,
    mission_id: str,
    root_work_id: str,
    project_id: str,
    request_id: str,
    objective: str,
    acceptance: tuple[str, ...],
    scope_paths: tuple[str, ...],
    risks: tuple[str, ...],
    non_goals: tuple[str, ...],
    adapter: str | None,
    approved_model: str,
    declared_dirty_paths: tuple[str, ...],
    plan_hash: str,
    approver: str,
    approval_evidence_ref: str,
    owner: str,
    original_request: str,
    safety_circuit: str,
    checks: tuple[str, ...],
    rollback: str,
    kind: str | None,
    change_action: str | None,
    domain: str,
    impact_scope: tuple[str, ...],
    inbox_id: str,
) -> None:
    """批准新需求并内部形成授权链，或兼容已有 Mission 调用。"""
    new_values = (
        project_id,
        request_id,
        objective,
        acceptance,
        scope_paths,
        risks,
        non_goals,
        adapter,
        approved_model,
        declared_dirty_paths,
        original_request,
        safety_circuit,
        checks,
        rollback,
    )
    classified = any((kind, change_action, domain, impact_scope, inbox_id))
    if mission_id:
        if any(new_values) or classified or any((plan_hash, approver, approval_evidence_ref)):
            raise click.ClickException("--mission-id 不能与新需求批准参数混用")
        _emit_card(ctx, "approve", mission_id, root_work_id)
        return
    if root_work_id:
        raise click.ClickException("新需求批准不允许手工传入 --root-work-id")
    # With a committed approver PIN the approver and evidence come from the PIN, so only the hash is required.
    pin_required = approval_pin_enforced(_control_root_path(ctx))
    missing = [
        name
        for name, value in (
            ("--plan-hash", plan_hash),
            ("--approver", approver or pin_required),
            ("--approval-evidence-ref", approval_evidence_ref or pin_required),
        )
        if not value
    ]
    if missing:
        raise click.ClickException("新需求批准缺少必填参数: " + ", ".join(missing))
    by_hash = request_id and not any(
        (
            project_id,
            objective,
            acceptance,
            scope_paths,
            risks,
            non_goals,
            adapter,
            approved_model,
            declared_dirty_paths,
            original_request,
            safety_circuit,
            checks,
            rollback,
        )
    )
    if by_hash and pin_required:
        # The user should not type the PIN only to learn the saved card cannot be approved anyway.
        try:
            _facade(ctx).check_pending_planning_scope_card(request_id, expected_plan_hash=plan_hash)
        except PmFacadeError as error:
            raise click.ClickException(str(error)) from error
    approval_pin = read_approval_pin(
        _control_root_path(ctx), summary=f"批准范围卡：请求 {request_id or '(新需求)'}，方案哈希 {plan_hash[:16]}…（确认这就是你看过的那张卡）"
    )
    if by_hash:
        if ctx.get_parameter_source("owner") is ParameterSource.COMMANDLINE:
            raise click.ClickException("按哈希批准已保存范围卡时不支持 --owner")
        if classified:
            raise click.ClickException("按哈希批准已保存范围卡时不支持分类参数；分类在 plan 时已绑定")
        try:
            _require_control_root(ctx)
            short_facade = _facade(ctx)
            result = short_facade.approve_pending_planning_scope_card(
                request_id,
                expected_plan_hash=plan_hash,
                approver=approver,
                approval_evidence_ref=approval_evidence_ref,
                approval_pin=approval_pin,
            )
            approved_card = short_facade.recover_planning_scope_card(result.mission_id)
            approved_work = short_facade.create_planning_work(approved_card)
        except (PmFacadeError, WorktreePolicyError) as error:
            raise click.ClickException(str(error)) from error
        _emit_plan_approval(approved_card, approved_work.state.value)
        return
    try:
        approver, approval_evidence_ref = _facade(ctx).resolve_approval(
            approval_pin=approval_pin,
            approver=approver,
            approval_evidence_ref=approval_evidence_ref,
            purpose="approve-scope",
            subject=plan_hash,
        )
        DecisionService.validate_planning_approval(approver, plan_hash, approval_evidence_ref)
    except (DecisionError, PmFacadeError) as error:
        raise click.ClickException(str(error)) from error
    classification, intake_item_id = _resolve_filing(
        ctx,
        project_id=project_id,
        request_id=request_id,
        kind=kind,
        change_action=change_action,
        domain=domain,
        impact_scope=impact_scope,
        inbox_id=inbox_id,
        from_draft=False,
    )
    checklist = _plan_checklist(original_request, safety_circuit, checks, rollback)
    preview = _planning_scope_card(
        ctx,
        project_id=project_id,
        request_id=request_id,
        objective=objective,
        acceptance=acceptance,
        scope_paths=scope_paths,
        risks=risks,
        non_goals=non_goals,
        adapter=adapter,
        approved_model=approved_model,
        declared_dirty_paths=declared_dirty_paths,
        plan_checklist=checklist,
        classification=classification,
        intake_item_id=intake_item_id,
        preview_only=True,
    )
    if not hmac.compare_digest(preview.plan_hash, plan_hash):
        raise click.ClickException("PlanningScopeCard plan_hash 已过期或内容发生漂移")
    card = _planning_scope_card(
        ctx,
        project_id=project_id,
        request_id=request_id,
        objective=objective,
        acceptance=acceptance,
        scope_paths=scope_paths,
        risks=risks,
        non_goals=non_goals,
        adapter=adapter,
        approved_model=approved_model,
        declared_dirty_paths=declared_dirty_paths,
        plan_checklist=checklist,
        classification=classification,
        intake_item_id=intake_item_id,
    )
    _approve_planning_change(ctx, card, approver)
    facade = _facade(ctx)
    try:
        facade.approve_planning_scope_card(
            card,
            expected_plan_hash=plan_hash,
            approver=approver,
            approval_evidence_ref=approval_evidence_ref,
            approval_pin=approval_pin,
        )
        facade.materialize_planning_mission(card, created_by="PM Facade")
        work = facade.create_planning_work(card, owner=owner)
    except PmFacadeError as error:
        raise click.ClickException(str(error)) from error
    _emit_plan_approval(card, work.state.value)


@pm_group.command(name="confirm-start")
@click.option("--mission-id", required=True)
@click.pass_context
def confirm_start_pm(ctx: click.Context, mission_id: str) -> None:
    """执行用户的唯一开工确认；内部授权编号不会暴露给用户。"""
    _emit_card(ctx, "confirm-start", mission_id)


@pm_group.command(name="execute")
@click.option("--request-id", required=True, help="批准范围卡绑定的请求标识")
@click.option(
    "--card-json",
    "card_json",
    required=True,
    help="plan 输出的完整 PlanningScopeCard JSON",
)
@click.option("--plan-hash", required=True, help="批准的不可变范围卡哈希")
@click.option(
    "--lease-token-env",
    required=True,
    metavar="ENV_NAME",
    help="一次性 lease capability 所在环境变量；读取后立即删除",
)
@click.pass_context
def execute_pm(
    ctx: click.Context,
    request_id: str,
    card_json: str,
    plan_hash: str,
    lease_token_env: str,
) -> None:
    """从完整批准卡冷启动并在前台阻塞执行唯一 local Saga。"""

    lease_token = os.environ.pop(lease_token_env, None)
    if lease_token is None:
        raise click.ClickException(f"环境变量不存在: {lease_token_env}")
    try:
        card = PlanningScopeCard.model_validate_json(card_json)
    except ValueError as error:
        raise click.ClickException("--card-json 不是有效的 PlanningScopeCard") from error
    if request_id != card.request_id:
        raise click.ClickException("--request-id 与 PlanningScopeCard 不一致")
    try:
        result = _facade(ctx).execute_planning_foreground(
            card,
            expected_plan_hash=plan_hash,
            lease_token=lease_token,
            lease_token_environment=lease_token_env,
        )
    except PmFacadeError as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        json.dumps(
            {
                "schema_version": "pm-foreground-execution.v1",
                "request_id": request_id,
                "plan_hash": plan_hash,
                "status": result.status,
                "run_state": result.status,
                "receipt": result.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@pm_group.command(name="accept")
@click.option("--mission-id", required=True)
@click.pass_context
def accept_pm(ctx: click.Context, mission_id: str) -> None:
    """记录最终用户验收；已启用批准口令时须用户本人在终端输入口令。关闭动作仍受治理门禁约束。"""
    approval_pin = read_approval_pin(_control_root_path(ctx), summary=f"最终验收：任务 {mission_id}（确认你已经看过结果）")
    try:
        _require_control_root(ctx)
        card = _facade(ctx).accept(mission_id, approval_pin=approval_pin)
    except (PmFacadeError, WorktreePolicyError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(card.model_dump_json(indent=2))


@pm_group.command(name="workflow")
@click.pass_context
def workflow_compat(ctx: click.Context) -> None:
    """保留历史名称的可发现性，不加载已隔离的旧技能。"""
    click.echo(_facade(ctx).compatibility_notice())


@click.group(name="context")
def context_group() -> None:
    """Platform-neutral, read-only invocation context commands."""


@pm_group.command(name="resume")
@click.argument("project_id", required=False, default="")
@click.option("--control-pid", default="", help="可选的治理控制面项目编号")
@click.option("--work-id", default="", help="显式选择 Work；多活时必须提供")
@click.option("--run-id", default="", help="显式选择 Run；多活时必须提供")
@click.option("--legacy-v1", is_flag=True, help="只读调用旧 pm-resume.v1 兼容路径")
@click.option(
    "--path",
    "start_path",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    default=None,
    help="自动识别项目时的调用目录（默认：当前目录）",
)
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出 continuity-resume.v2")
@click.pass_context
def resume_pm(
    ctx: click.Context,
    project_id: str,
    control_pid: str,
    work_id: str,
    run_id: str,
    legacy_v1: bool,
    start_path: str | None,
    as_json: bool,
) -> None:
    """编译新会话必须先消费的权威连续性上下文。"""
    app_ctx: AppContext = ctx.find_root().obj
    if legacy_v1:
        if not project_id:
            try:
                project_id = (
                    WorkspaceContextService(app_ctx.workspace_root)
                    .resolve(start_path=start_path)
                    .subject.project_id
                )
            except WorkspaceContextError as error:
                raise click.ClickException(str(error)) from error
        service = PmResumeService(app_ctx.workspace_root)
        try:
            legacy = service.collect(project_id, control_pid)
        except PmResumeError as error:
            raise click.ClickException(str(error)) from error
        if as_json:
            click.echo(legacy.model_dump_json(indent=2))
            return
        click.echo(f"evidence_id: {legacy.evidence_id}")
        click.echo(f"控制面: {legacy.control_project_id} | Git: {legacy.git_head[:12]}")
        click.echo(f"下一合法动作: {legacy.next_legal_action}")
        return
    if control_pid:
        raise click.ClickException("--control-pid 仅适用于 --legacy-v1；v2 控制面来自 Registry")
    try:
        payload = PmFacadeService(
            app_ctx.control_root,
            execution_root=app_ctx.workspace_root,
        ).resume(
            project_id=project_id,
            invocation_path=start_path,
            work_id=work_id,
            run_id=run_id,
        )
    except PmFacadeError as error:
        raise click.ClickException(str(error)) from error
    _emit_query(payload, as_json)


def _emit_query(payload: ContinuityResume, as_json: bool) -> None:
    """Check the answer once more at this consumer (a replaced facade must not slip through), then print it; nothing is printed when the check fails."""
    try:
        checked = validate_query_resume(payload, require_query=True)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    if as_json:
        click.echo(checked.model_dump_json(indent=2))
        return
    _echo_resume_text(checked)


def _echo_resume_text(payload: ContinuityResume) -> None:
    """Shared text rendering of the versioned query for ``pm resume`` and ``pm orient``."""
    click.echo(f"evidence_id: {payload.evidence_id}")
    click.echo(
        f"subject: {payload.context.subject_project_id} | "
        f"control: {payload.context.control_project_id or '-'} | "
        f"release: {payload.context.release_id or '-'}"
    )
    click.echo(f"work: {payload.work.work_id if payload.work else '-'}")
    click.echo(f"run: {payload.run.run_id if payload.run else '-'}")
    click.echo(f"下一合法动作: {payload.next_legal_action or '-'}")
    for conflict in payload.conflicts:
        click.echo(f"冲突: {conflict}")
    if not payload.intake.is_empty:
        click.echo(
            f"收件箱: 待确认 {payload.intake.awaiting_confirmation} 条 | "
            f"已确认待排 {payload.intake.confirmed_waiting} 条"
        )
        for brief in payload.intake.queue:
            click.echo(
                f"  {brief.item_id} [{brief.kind.value}] {brief.title}"
                f"（{brief.status.value}，建议 {brief.disposition.value}）"
            )
    for path in payload.read_set:
        click.echo(f"证据: {path}")
    query = payload.query
    if query is not None:
        click.echo(f"查询合同: {query.schema_version} | 能力合同: {query.capabilities.contract_version} | query: {query.evidence_id}")
        click.echo(
            f"挂起: {'支持' if query.capabilities.parking_supported else '不支持'} | "
            f"插队: {'支持' if query.capabilities.preemption_supported else '不支持'}"
        )
        if query.requested_action is not None:
            asked = query.requested_action
            click.echo(f"所问动作 {asked.action.value}: {asked.status}（{asked.reason}）")


@pm_group.command(name="orient")
@click.argument("project_id", required=False, default="")
@click.option("--work-id", default="", help="显式选择 Work；多活时必须提供")
@click.option("--run-id", default="", help="显式选择 Run；多活时必须提供")
@click.option(
    "--requested-action",
    type=click.Choice([action.value for action in QueriedAction]),
    default=None,
    help="询问某个动作的能力：M2 对 PARK、RESUME_PARKED、PREEMPT 一律明确回答 UNSUPPORTED（查询不是执行授权）",
)
@click.option(
    "--path",
    "start_path",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    default=None,
    help="自动识别项目时的调用目录（默认：当前目录）",
)
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出带 query 块的 continuity-resume.v2")
@click.pass_context
def orient_pm(
    ctx: click.Context,
    project_id: str,
    work_id: str,
    run_id: str,
    requested_action: str | None,
    start_path: str | None,
    as_json: bool,
) -> None:
    """只读定位：与 resume 共用同一份版本化查询，并可询问某个动作的能力。"""
    app_ctx: AppContext = ctx.find_root().obj
    try:
        payload = PmFacadeService(
            app_ctx.control_root,
            execution_root=app_ctx.workspace_root,
        ).orient(
            project_id=project_id,
            invocation_path=start_path,
            work_id=work_id,
            run_id=run_id,
            requested_action=requested_action or "",
        )
    except PmFacadeError as error:
        raise click.ClickException(str(error)) from error
    _emit_query(payload, as_json)


def _emit_context(ctx: click.Context, project_id: str, start_path: str | None) -> None:
    app_ctx: AppContext = ctx.find_root().obj
    try:
        payload = WorkspaceContextService(
            app_ctx.control_root,
            execution_root=app_ctx.workspace_root,
        ).resolve(
            project_id=project_id,
            start_path=start_path,
        )
    except WorkspaceContextError as error:
        raise click.ClickException(str(error)) from error
    click.echo(payload.model_dump_json(indent=2))


@context_group.command(name="resolve")
@click.option("--project-id", default="", help="显式项目编号（优先于目录发现）")
@click.option(
    "--path",
    "start_path",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    default=None,
    help="待解析的目录（默认：当前目录）",
)
@click.pass_context
def resolve_context(ctx: click.Context, project_id: str, start_path: str | None) -> None:
    """输出当前调用的只读项目上下文卡，不写入全局活动项目。"""
    _emit_context(ctx, project_id, start_path)


@pm_group.command(name="context")
@click.option("--project-id", default="", help="显式项目编号（优先于目录发现）")
@click.option(
    "--path",
    "start_path",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    default=None,
    help="待解析的目录（默认：当前目录）",
)
@click.pass_context
def resolve_context_compat(ctx: click.Context, project_id: str, start_path: str | None) -> None:
    """兼容入口；请迁移到 `context resolve`。"""
    _emit_context(ctx, project_id, start_path)


# Agent swap commands (M3-HANDOFF card): kept in their own module, registered here so they appear under `pm`.
from auto_pm.ui.cli.approval_pin import approver_pin_group  # noqa: E402
from auto_pm.ui.cli.pm_handoff import handoff_pm, sign_risk_pm, takeover_pm  # noqa: E402

pm_group.add_command(approver_pin_group)

pm_group.add_command(handoff_pm)
pm_group.add_command(takeover_pm)
pm_group.add_command(sign_risk_pm)

# IDE-agent closing commands (gap 8): quality verification and one-step closure without a temporary script.
from auto_pm.ui.cli.pm_closure import close_pm, verify_pm  # noqa: E402

pm_group.add_command(verify_pm)
pm_group.add_command(close_pm)
