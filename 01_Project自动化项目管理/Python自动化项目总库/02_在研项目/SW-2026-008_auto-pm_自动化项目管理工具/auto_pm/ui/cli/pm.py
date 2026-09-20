"""Compact PM cold-start commands."""

from __future__ import annotations

import json
import os
from typing import cast

import click

from auto_pm.app_context import AppContext
from auto_pm.change.change_service import ChangeService
from auto_pm.change.constants import TransitionGuardError
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.pm_facade import PlanningExecutionGrant, PlanningScopeCard, PmIntent
from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.core.pm_resume_service import PmResumeError, PmResumeService
from auto_pm.core.workspace_context_service import WorkspaceContextError, WorkspaceContextService
from auto_pm.core.worktree_policy_service import WorktreePolicyError, WorktreePolicyService


@click.group(name="pm")
def pm_group() -> None:
    """面向用户的 PM 门面：计划、确认、执行、恢复与验收。"""


def _facade(ctx: click.Context) -> PmFacadeService:
    app_ctx: AppContext = ctx.find_root().obj
    return PmFacadeService(app_ctx.workspace_root)


def _emit_card(ctx: click.Context, action: str, mission_id: str, root_work_id: str = "") -> None:
    try:
        app_ctx: AppContext = ctx.find_root().obj
        WorktreePolicyService(app_ctx.workspace_root).require_control_root()
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
    app_ctx: AppContext = ctx.find_root().obj
    try:
        WorktreePolicyService(app_ctx.workspace_root).require_control_root()
        intent = PmIntent(
            subject_project_id=project_id,
            request_id=request_id,
            objective=objective,
            acceptance_criteria=acceptance,
        )
        return cast(
            PlanningScopeCard,
            _facade(ctx).create_planning_scope_card(
                intent,
                scope_paths=scope_paths,
                risks=risks,
                non_goals=non_goals,
                execution_grant=PlanningExecutionGrant(
                    adapter=ExecutionAdapterKind(cast(str, adapter)),
                    approved_model=approved_model,
                    declared_dirty_paths=declared_dirty_paths,
                ),
            ),
        )
    except (PmFacadeError, ValueError, WorktreePolicyError) as error:
        raise click.ClickException(str(error)) from error


def _approve_planning_change(ctx: click.Context, card: PlanningScopeCard, approver: str) -> None:
    app_ctx: AppContext = ctx.find_root().obj
    changes = ChangeService(str(app_ctx.workspace_root))
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
) -> None:
    """创建/恢复新需求范围卡，或兼容已有 Mission 调用。"""
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
    )
    if mission_id:
        if any(new_values):
            raise click.ClickException("--mission-id 不能与新需求参数混用")
        _emit_card(ctx, "plan", mission_id)
        return
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
    )
    click.echo(card.model_dump_json(indent=2))


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
@click.option("--approver", default="", help="真实人类审批人")
@click.option(
    "--approval-evidence-ref",
    default="",
    help="非模型自签的 user-confirmation 证据引用",
)
@click.option("--owner", default="PM Facade", show_default=True, help="内部 Work owner")
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
    )
    if mission_id:
        if any(new_values) or any((plan_hash, approver, approval_evidence_ref)):
            raise click.ClickException("--mission-id 不能与新需求批准参数混用")
        _emit_card(ctx, "approve", mission_id, root_work_id)
        return
    if root_work_id:
        raise click.ClickException("新需求批准不允许手工传入 --root-work-id")
    missing = [
        name
        for name, value in (
            ("--plan-hash", plan_hash),
            ("--approver", approver),
            ("--approval-evidence-ref", approval_evidence_ref),
        )
        if not value
    ]
    if missing:
        raise click.ClickException("新需求批准缺少必填参数: " + ", ".join(missing))
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
    )
    _approve_planning_change(ctx, card, approver)
    facade = _facade(ctx)
    try:
        facade.approve_planning_scope_card(
            card,
            expected_plan_hash=plan_hash,
            approver=approver,
            approval_evidence_ref=approval_evidence_ref,
        )
        facade.materialize_planning_mission(card, created_by="PM Facade")
        work = facade.create_planning_work(card, owner=owner)
    except PmFacadeError as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        json.dumps(
            {
                "schema_version": "pm-plan-approval.v1",
                "request_id": card.request_id,
                "subject_project_id": card.subject_project_id,
                "change_id": card.change_id,
                "plan_hash": card.plan_hash,
                "authorization_status": "AUTHORIZED",
                "work_state": work.state.value,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


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
    """从完整批准卡冷启动恢复，并仅准备 PREPARED intent / READY Run。"""

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
        result = _facade(ctx).prepare_planning_execution(
            card,
            expected_plan_hash=plan_hash,
            lease_token=lease_token,
        )
    except PmFacadeError as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        json.dumps(
            {
                "schema_version": "pm-approved-dispatch.v1",
                "request_id": request_id,
                "plan_hash": plan_hash,
                "status": result.intent.status,
                "run_state": "READY",
                "receipt": result.receipt.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@pm_group.command(name="accept")
@click.option("--mission-id", required=True)
@click.pass_context
def accept_pm(ctx: click.Context, mission_id: str) -> None:
    """记录最终用户验收；关闭动作仍受治理门禁约束。"""
    _emit_card(ctx, "accept", mission_id)


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
        payload = PmFacadeService(app_ctx.workspace_root).resume(
            project_id=project_id,
            invocation_path=start_path,
            work_id=work_id,
            run_id=run_id,
        )
    except PmFacadeError as error:
        raise click.ClickException(str(error)) from error
    if as_json:
        click.echo(payload.model_dump_json(indent=2))
        return
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
    for path in payload.read_set:
        click.echo(f"证据: {path}")


def _emit_context(ctx: click.Context, project_id: str, start_path: str | None) -> None:
    app_ctx: AppContext = ctx.find_root().obj
    try:
        payload = WorkspaceContextService(app_ctx.workspace_root).resolve(
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
