"""Compact PM cold-start commands."""

from __future__ import annotations

import click

from auto_pm.app_context import AppContext
from auto_pm.core.pm_resume_service import PmResumeError, PmResumeService


@click.group(name="pm")
def pm_group() -> None:
    """PM control-plane commands that return bounded AI context."""


@pm_group.command(name="resume")
@click.argument("project_id")
@click.option("--control-pid", default="", help="可选的治理控制面项目编号")
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出 pm-resume.v1")
@click.pass_context
def resume_pm(ctx: click.Context, project_id: str, control_pid: str, as_json: bool) -> None:
    """编译新会话必须先消费的紧凑 PM 上下文。"""
    app_ctx: AppContext = ctx.find_root().obj
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
