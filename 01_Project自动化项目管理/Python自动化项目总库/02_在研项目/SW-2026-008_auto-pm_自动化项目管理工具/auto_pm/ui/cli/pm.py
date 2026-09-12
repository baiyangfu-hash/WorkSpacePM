"""Compact PM cold-start commands."""

from __future__ import annotations

import click

from auto_pm.app_context import AppContext
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


@pm_group.command(name="plan")
@click.option("--mission-id", required=True, help="由驾驶舱创建的 Mission 编号")
@click.pass_context
def plan_pm(ctx: click.Context, mission_id: str) -> None:
    """展示开工确认卡；不读取旧技能，也不创建隐式执行状态。"""
    _emit_card(ctx, "plan", mission_id)


@pm_group.command(name="approve")
@click.option("--mission-id", required=True)
@click.option(
    "--root-work-id",
    default="",
    help="兼容旧入口；新 Mission 已在创建时绑定内部授权，无需填写。",
)
@click.pass_context
def approve_pm(ctx: click.Context, mission_id: str, root_work_id: str) -> None:
    """记录第一次用户确认，并允许驾驶舱在既定边界内执行。"""
    _emit_card(ctx, "approve", mission_id, root_work_id)


@pm_group.command(name="confirm-start")
@click.option("--mission-id", required=True)
@click.pass_context
def confirm_start_pm(ctx: click.Context, mission_id: str) -> None:
    """执行用户的唯一开工确认；内部授权编号不会暴露给用户。"""
    _emit_card(ctx, "confirm-start", mission_id)


@pm_group.command(name="execute")
@click.option("--mission-id", required=True)
@click.pass_context
def execute_pm(ctx: click.Context, mission_id: str) -> None:
    """启动已授权根 Work；后续内部编排不再要求用户分发任务。"""
    _emit_card(ctx, "execute", mission_id)


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
