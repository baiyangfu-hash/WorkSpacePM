"""auto_pm.ui.cli.decision - 决策包（Decision Package）命令行工具"""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from auto_pm.app_context import AppContext
from auto_pm.domain.change.decision_service import (
    DecisionError,
    DecisionService,
)

console = Console()


def _workspace(ctx: click.Context) -> Path:
    app_ctx: AppContext = ctx.obj
    return Path(app_ctx.workspace_root)


@click.group(name="decision")
def decision_group() -> None:
    """阶段 1 审批结构化决策包管理 (Decision Package)"""


@decision_group.command(name="create")
@click.option("--change-id", required=True, help="关联变更单编号（如 CHG-PLC-2026-012）")
@click.option("--approver", required=True, help="审批人（PM / 架构师）")
@click.option("--pid", "project_id", default="", help="可选的项目编号")
@click.option("--file", "approved_files", multiple=True, help="允许修改的文件相对路径，可重复指定")
@click.option("--condition", "conditions", multiple=True, help="有条件批准的附加条件说明，可重复指定")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def create_decision(
    ctx: click.Context,
    change_id: str,
    approver: str,
    project_id: str,
    approved_files: tuple[str, ...],
    conditions: tuple[str, ...],
    as_json: bool,
) -> None:
    """从已批准的变更单创建结构化决策包。"""
    service = DecisionService(_workspace(ctx))
    try:
        dto = service.create_decision(
            change_id=change_id,
            approver=approver,
            project_id=project_id,
            approved_files=list(approved_files) if approved_files else None,
            conditions=list(conditions) if conditions else None,
        )
    except DecisionError as e:
        console.print(f"[red]错误: {e}[/red]")
        ctx.exit(1)

    if as_json:
        click.echo(json.dumps(dto.to_dict(), ensure_ascii=False, indent=2))
    else:
        console.print(f"[green]✅ 决策包已成功创建并固化: {dto.decision_id}[/green]")
        console.print(f"  [cyan]关联变更单:[/cyan] {dto.change_id}")
        console.print(f"  [cyan]审批结论:[/cyan] {dto.decision_conclusion}")
        console.print(f"  [cyan]批准范围:[/cyan] {dto.approved_scope}")
        console.print(f"  [cyan]批准文件清单:[/cyan] {', '.join(dto.approved_files) or '无特异性限定'}")


@decision_group.command(name="show")
@click.argument("decision_id")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def show_decision(ctx: click.Context, decision_id: str, as_json: bool) -> None:
    """查看指定决策包详情。"""
    service = DecisionService(_workspace(ctx))
    try:
        dto = service.get_decision(decision_id)
    except DecisionError as e:
        console.print(f"[red]错误: {e}[/red]")
        ctx.exit(1)

    if as_json:
        click.echo(json.dumps(dto.to_dict(), ensure_ascii=False, indent=2))
    else:
        console.print(f"[bold cyan]═══ 决策包详情: {dto.decision_id} ═══[/bold cyan]")
        console.print(f"  [bold]项目编号:[/bold] {dto.project_id}")
        console.print(f"  [bold]变更单号:[/bold] {dto.change_id}")
        console.print(f"  [bold]审批人:[/bold] {dto.approver}")
        console.print(f"  [bold]审批时间:[/bold] {dto.approved_at}")
        console.print(f"  [bold]审批结论:[/bold] {dto.decision_conclusion}")
        console.print(f"  [bold]批准范围:[/bold] {dto.approved_scope}")
        console.print("  [bold]批准文件白名单:[/bold]")
        for f in dto.approved_files:
            console.print(f"    - {f}")
        if dto.conditions:
            console.print("  [bold]附加条件:[/bold]")
            for c in dto.conditions:
                console.print(f"    - {c}")


@decision_group.command(name="list")
@click.option("--pid", "project_id", default="", help="按项目编号过滤")
@click.option("--change-id", default="", help="按变更单编号过滤")
@click.pass_context
def list_decisions(
    ctx: click.Context,
    project_id: str,
    change_id: str,
) -> None:
    """列出工作空间内的所有决策包。"""
    service = DecisionService(_workspace(ctx))
    dtos = service.list_decisions(project_id=project_id, change_id=change_id)
    if not dtos:
        console.print("[dim]未找到匹配的决策包[/dim]")
        return

    table = Table(title="已固化决策包清单")
    table.add_column("决策编号", style="cyan")
    table.add_column("项目编号", style="green")
    table.add_column("变更单号", style="magenta")
    table.add_column("审批结论")
    table.add_column("审批人")
    table.add_column("批准文件数", justify="right")

    for d in dtos:
        table.add_row(
            d.decision_id,
            d.project_id,
            d.change_id,
            d.decision_conclusion,
            d.approver,
            str(len(d.approved_files)),
        )

    console.print(table)
