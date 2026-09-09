"""Compact PM cold-start commands."""

from __future__ import annotations

import click

from auto_pm.app_context import AppContext
from auto_pm.core.pm_resume_service import PmResumeError, PmResumeService
from auto_pm.core.workspace_context_service import WorkspaceContextError, WorkspaceContextService


@click.group(name="pm")
def pm_group() -> None:
    """PM control-plane commands that return bounded AI context."""


@click.group(name="context")
def context_group() -> None:
    """Platform-neutral, read-only invocation context commands."""


@pm_group.command(name="resume")
@click.argument("project_id", required=False, default="")
@click.option("--control-pid", default="", help="可选的治理控制面项目编号")
@click.option(
    "--path",
    "start_path",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    default=None,
    help="自动识别项目时的调用目录（默认：当前目录）",
)
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出 pm-resume.v1")
@click.pass_context
def resume_pm(
    ctx: click.Context,
    project_id: str,
    control_pid: str,
    start_path: str | None,
    as_json: bool,
) -> None:
    """编译新会话必须先消费的紧凑 PM 上下文。"""
    app_ctx: AppContext = ctx.find_root().obj
    if not project_id:
        try:
            project_id = WorkspaceContextService(app_ctx.workspace_root).resolve(
                start_path=start_path
            ).subject.project_id
        except WorkspaceContextError as error:
            raise click.ClickException(str(error)) from error
    service = PmResumeService(app_ctx.workspace_root)
    try:
        payload = service.collect(project_id, control_pid)
    except PmResumeError as error:
        raise click.ClickException(str(error)) from error
    if as_json:
        click.echo(payload.model_dump_json(indent=2))
        return
    click.echo(f"evidence_id: {payload.evidence_id}")
    click.echo(f"控制面: {payload.control_project_id} | Git: {payload.git_head[:12]}")
    click.echo(f"下一合法动作: {payload.next_legal_action}")
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
