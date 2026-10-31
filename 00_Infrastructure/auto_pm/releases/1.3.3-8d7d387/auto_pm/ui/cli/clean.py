"""Clean CLI 命令：一键清扫工作区根目录游离临时日志、脚本及缓存 (CHG-SCPT-2026-155)"""

from __future__ import annotations

import os

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from auto_pm.app_context import AppContext
from auto_pm.core.governance_service import GovernanceService

console = Console()


@click.command("clean")
@click.option("--cache", "-c", is_flag=True, help="同时清理 Python/ruff/pytest 缓存目录")
@click.option("--dry-run", is_flag=True, help="仅预览要清理的文件，不执行删除")
@click.pass_context
def clean_cmd(ctx: click.Context, cache: bool, dry_run: bool) -> None:
    """一键清扫工作区游离日志、散装脚本及临时编译产物"""
    app_ctx: AppContext = ctx.obj
    workspace_root = app_ctx.workspace_root or os.getcwd()

    service = GovernanceService(workspace_root=workspace_root)
    report = service.inspect_sanitation()

    if report.is_pure and not cache:
        console.print(Panel("[bold green]✨ 工作区状态极佳！根目录纯净，无可清理的游离临时文件。[/bold green]", title="Clean 结果"))
        return

    table = Table(title="待清理文件清单", show_header=True, header_style="bold cyan")
    table.add_column("路径", style="dim")
    table.add_column("类型")
    table.add_column("说明")

    for issue in report.temp_files:
        table.add_row(issue.relative_path, issue.issue_type, issue.description)

    for issue in report.unauthorized_files:
        table.add_row(issue.relative_path, f"[bold red]{issue.issue_type}[/bold red]", issue.description)

    console.print(table)

    if dry_run:
        console.print("[yellow]🔍 处于 --dry-run 模式，未实际删除文件。[/yellow]")
        return

    cleaned = service.clean_workspace(clean_cache=cache)
    console.print(Panel(f"[bold green]✅ 清理完成！已清除 {len(cleaned)} 个游离临时文件与缓存。[/bold green]", title="Clean 完成"))
