"""workflow CLI 命令组 - Phase 2 (CST-CLI-WORKFLOW)

提供 workflow list / run / status / history 命令
"""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from auto_pm.constraint.workflow import WorkflowEngine

console = Console()


def _resolve_workspace(ctx: click.Context) -> Path:
    if ctx.obj and isinstance(ctx.obj, dict) and "workspace" in ctx.obj:
        return Path(ctx.obj["workspace"])
    return Path.cwd()


@click.group(name="workflow", help="工作流编排与执行管理")
def workflow_group() -> None:
    pass


@workflow_group.command(name="list", help="列出所有可用的工作流定义")
@click.pass_context
def list_workflows(ctx: click.Context) -> None:
    workspace_root = _resolve_workspace(ctx)
    engine = WorkflowEngine(workspace_root)
    workflows = engine.load_all()

    if not workflows:
        console.print("[yellow]未找到工作流定义[/yellow]")
        return

    table = Table(title=f"工作流定义列表 (工作空间: {workspace_root.name})")
    table.add_column("名称", style="cyan", no_wrap=True)
    table.add_column("描述", style="magenta")
    table.add_column("步骤数", style="green")

    for wf in workflows:
        table.add_row(wf.name, wf.description, str(len(wf.steps)))

    console.print(table)
    console.print(f"[dim]共 {len(workflows)} 个工作流定义[/dim]")


@workflow_group.command(name="run", help="运行指定工作流")
@click.argument("name")
@click.option("--file", "-f", "file_path", type=click.Path(exists=True), help="目标文件路径")
@click.pass_context
def run_workflow(ctx: click.Context, name: str, file_path: str | None) -> None:
    workspace_root = _resolve_workspace(ctx)
    engine = WorkflowEngine(workspace_root)

    target_file = Path(file_path).resolve() if file_path else None

    try:
        run_record = engine.run(name, file_path=target_file)
        if run_record.status == "success":
            console.print(
                f"[green]✅ 工作流 '{name}' 执行成功 (run_id: {run_record.run_id})[/green]"
            )
        else:
            console.print(
                f"[red]❌ 工作流 '{name}' 执行失败 (run_id: {run_record.run_id})[/red]"
            )
            click.get_current_context().exit(1)
    except Exception as e:
        console.print(f"[bold red]错误:[/bold red] {e}")
        click.get_current_context().exit(1)


@workflow_group.command(name="history", help="查看工作流执行历史")
@click.option("--limit", "-n", default=10, help="显示最近 N 条记录")
@click.option("--json", "json_format", is_flag=True, help="以 JSON 格式输出")
@click.pass_context
def workflow_history(ctx: click.Context, limit: int, json_format: bool) -> None:
    workspace_root = _resolve_workspace(ctx)
    engine = WorkflowEngine(workspace_root)
    runs = engine.list_runs()[-limit:]

    if json_format:
        click.echo(json.dumps(runs, ensure_ascii=False, indent=2))
        return

    if not runs:
        console.print("[dim]尚无工作流执行历史[/dim]")
        return

    table = Table(title="工作流执行历史记录")
    table.add_column("Run ID", style="cyan")
    table.add_column("工作流名称", style="blue")
    table.add_column("状态", style="green")
    table.add_column("开始时间", style="magenta")

    for r in runs:
        status_str = "[green]成功[/green]" if r["status"] == "success" else "[red]失败[/red]"
        table.add_row(r["run_id"], r["workflow_name"], status_str, r["started_at"])

    console.print(table)


@workflow_group.command(name="status", help="查看指定工作流运行详情")
@click.argument("run_id")
@click.pass_context
def workflow_status(ctx: click.Context, run_id: str) -> None:
    workspace_root = _resolve_workspace(ctx)
    engine = WorkflowEngine(workspace_root)
    runs = engine.list_runs()

    matched = [r for r in runs if r["run_id"] == run_id]
    if not matched:
        console.print(f"[yellow]未找到运行记录: {run_id}[/yellow]")
        click.get_current_context().exit(1)

    r = matched[-1]
    console.print(f"[bold]Run ID:[/bold] {r['run_id']}")
    console.print(f"[bold]工作流:[/bold] {r['workflow_name']}")
    console.print(f"[bold]状态:[/bold] {r['status']}")
    console.print(f"[bold]时间:[/bold] {r['started_at']} -> {r.get('completed_at', '-')}")
    console.print("[bold]步骤日志:[/bold]")
    for log in r.get("step_logs", []):
        console.print(f"  {log}")
