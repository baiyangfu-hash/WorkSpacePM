from __future__ import annotations

import json
import os
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from auto_pm.app_context import AppContext
from auto_pm.core.doc_inject_service import DocInjectService
from auto_pm.core.doc_refresh_service import DocRefreshService
from auto_pm.core.project_service import ProjectService
from auto_pm.domain.doc.services import DocCheckService, DocSyncService

console = Console()


@click.group("doc")
def doc_group() -> None:
    """Doc-as-Code 文档自省、一致性门禁与自动区维护工具"""


@doc_group.command("sync")
@click.pass_context
def doc_sync_cmd(ctx: click.Context) -> None:
    """自动自省提取代码元数据并无损注入 Markdown 活文档"""
    app_ctx: AppContext = ctx.obj
    workspace_root = Path(app_ctx.workspace_root or os.getcwd())

    service = DocSyncService(workspace_root=workspace_root)
    logs = service.sync_all()

    console.print(Panel("[bold green]✨ Doc-as-Code 自动同步完成！[/bold green]", title="Doc Sync 结果"))
    table = Table(title="注入记录", show_header=True, header_style="bold cyan")
    table.add_column("状态", style="green")
    table.add_column("详细信息")

    for log in logs:
        table.add_row("✅ 注入", log)
    console.print(table)


@doc_group.command("check")
@click.pass_context
def doc_check_cmd(ctx: click.Context) -> None:
    """静态审计文档与代码的一致性及版本锁"""
    app_ctx: AppContext = ctx.obj
    workspace_root = Path(app_ctx.workspace_root or os.getcwd())

    service = DocCheckService(workspace_root=workspace_root)
    results = service.check_all()

    all_passed = True
    table = Table(title="文档门禁检查报告", show_header=True, header_style="bold cyan")
    table.add_column("门禁编号", style="bold")
    table.add_column("检查项")
    table.add_column("状态")
    table.add_column("说明")

    for r in results:
        status_str = "[bold green]PASS[/bold green]" if r.passed else "[bold red]FAIL[/bold red]"
        table.add_row(r.check_id, r.name, status_str, r.message)
        if not r.passed:
            all_passed = False

    console.print(table)
    if all_passed:
        console.print(Panel("[bold green]🎉 所有文档一致性门禁检查 100% 通过！[/bold green]", title="Doc Check 结果"))
    else:
        console.print(Panel("[bold red]❌ 存在未同步的文档滞后项，请先执行 auto-pm doc sync 修复！[/bold red]", title="Doc Check 结果"))
        raise click.exceptions.Exit(1)


@doc_group.command("inject")
@click.argument("project_id")
@click.option("--dry-run", is_flag=True, default=False, help="仅预览注入效果，不修改文件")
@click.option("--json", "json_output", is_flag=True, default=False, help="以 JSON 格式输出结果")
@click.pass_context
def doc_inject_cmd(ctx: click.Context, project_id: str, dry_run: bool, json_output: bool) -> None:
    """为历史 PLC 项目文档注入 AUTO_PM 自动区标记"""
    app_ctx: AppContext = ctx.obj
    workspace_root = Path(app_ctx.workspace_root or os.getcwd())

    project_service = ProjectService(workspace_root=str(workspace_root))
    project = project_service.get_project(project_id)
    if not project:
        console.print(f"[bold red]错误：[/bold red]未找到项目 '{project_id}'（项目不存在）")
        raise click.exceptions.Exit(1)

    service = DocInjectService(workspace_root=str(workspace_root))
    result = service.inject_markers(project, dry_run=dry_run)

    if json_output:
        click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    prefix = "[DRY-RUN] " if dry_run else ""
    console.print(f"[bold green]{prefix}文档自动区标记注入完成！[/bold green]")
    console.print(f"共处理 {len(result.injected_files)} 个文档：")

    for doc in result.injected_files:
        console.print(f"  • [bold]{Path(doc.file_path).name}[/bold]:")
        for key in doc.injected_keys:
            console.print(f"    - [green]注入标记:[/green] {escape(key)}")
        for key in doc.skipped_keys:
            console.print(f"    - [yellow]已存在跳过:[/yellow] {escape(key)}")
        for key in doc.missing_anchors:
            console.print(f"    - [red]锚点缺失:[/red] [{key}] (未注入)")

    for issue in result.issues:
        console.print(f"  [yellow]⚠️ 提示:[/yellow] {escape(issue)}")


@doc_group.command("refresh")
@click.argument("project_id")
@click.option("--dry-run", is_flag=True, default=False, help="仅预览刷新效果，不修改文件")
@click.option("--json", "json_output", is_flag=True, default=False, help="以 JSON 格式输出结果")
@click.pass_context
def doc_refresh_cmd(ctx: click.Context, project_id: str, dry_run: bool, json_output: bool) -> None:
    """根据工程资产刷新 PLC 文档中的自动区内容"""
    app_ctx: AppContext = ctx.obj
    workspace_root = Path(app_ctx.workspace_root or os.getcwd())

    project_service = ProjectService(workspace_root=str(workspace_root))
    project = project_service.get_project(project_id)
    if not project:
        console.print(f"[bold red]错误：[/bold red]未找到项目 '{project_id}'（项目不存在）")
        raise click.exceptions.Exit(1)

    service = DocRefreshService(workspace_root=str(workspace_root))
    result = service.refresh_project_documents(project, dry_run=dry_run)

    if json_output:
        click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    prefix = "[DRY-RUN] " if dry_run else ""
    console.print(f"[bold green]{prefix}文档自动区处理完成！[/bold green]")
    console.print(f"共刷新 {len(result.refreshed_files)} 个文档：")

    for doc in result.refreshed_files:
        status_text = "[green]已更新[/green]" if doc.changed else "[dim]无变更[/dim]"
        console.print(f"  • [bold]{Path(doc.file_path).name}[/bold] ({status_text}):")
        for key in doc.block_keys:
            console.print(f"    - [cyan]区块:[/cyan] {escape(key)}")

    for issue in result.issues:
        console.print(f"  [yellow]⚠️ 提示:[/yellow] {escape(issue)}")

