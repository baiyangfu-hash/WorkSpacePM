"""
Prototype CLI Command Group for auto-pm (SW-2026-008).
Provides prototype bundle, check, archive, and init commands exclusively for pm-workflow skill.
"""

from __future__ import annotations

import os
from pathlib import Path

import click
from rich.console import Console

from auto_pm.core.prototype_service import PrototypeService

console = Console()

def _resolve_project_dir(workspace_root: str, pid: str) -> str:
    """Find project folder by PID or name"""
    ws = Path(workspace_root)
    # Search for folder with PID or match directly
    for item in ws.glob(f"**/*{pid}*"):
        if item.is_dir() and not item.name.startswith("."):
            return str(item)
    return str(ws)

@click.group(name="prototype", help="通用原型管理命令组 (pm-workflow 专属)")
def prototype_cmd() -> None:
    """Prototype command group."""
    pass

@prototype_cmd.command(name="bundle", help="合并打包 HTML/CSS/JS 原型为单文件离线发布包")
@click.option("--pid", "-p", required=True, help="项目 ID (如 DJ-2026-005 或 SW-2026-008)")
@click.option("--version", "-v", help="版本号 tag (如 V1.6.1，用于版本备份)")
@click.option("--output", "-o", help="自定义输出文件名")
@click.pass_context
def bundle_cmd(ctx: click.Context, pid: str, version: str | None, output: str | None) -> None:
    workspace_root = os.getcwd()
    if ctx.obj and hasattr(ctx.obj, "workspace_root"):
        workspace_root = ctx.obj.workspace_root

    proj_dir = _resolve_project_dir(workspace_root, pid)
    service = PrototypeService(workspace_root)
    res = service.bundle(proj_dir, version=version, output_filename=output)

    if res.success:
        console.print(f"[green]✓ 原型打包成功: {res.output_path}[/green]")
    else:
        console.print(f"[red]✗ 原型打包失败: {res.message}[/red]")

@prototype_cmd.command(name="check", help="校验原型完整性、BOM 及 PLC 变量映射")
@click.option("--pid", "-p", required=True, help="项目 ID (如 DJ-2026-005)")
@click.pass_context
def check_cmd(ctx: click.Context, pid: str) -> None:
    workspace_root = os.getcwd()
    if ctx.obj and hasattr(ctx.obj, "workspace_root"):
        workspace_root = ctx.obj.workspace_root

    proj_dir = _resolve_project_dir(workspace_root, pid)
    service = PrototypeService(workspace_root)
    res = service.check(proj_dir)

    for i in res.info:
        console.print(f"[cyan][INFO][/cyan] {i}")
    for w in res.warnings:
        console.print(f"[yellow][WARN][/yellow] {w}")
    for e in res.errors:
        console.print(f"[red][ERROR][/red] {e}")

    if res.passed:
        console.print("[green]✓ 原型检查全部通过[/green]")
    else:
        console.print("[red]✗ 原型检查发现未通过项[/red]")
        raise click.exceptions.Exit(1)

@prototype_cmd.command(name="archive", help="快照归档当前原型")
@click.option("--pid", "-p", required=True, help="项目 ID")
@click.option("--version", "-v", required=True, help="版本号 tag")
@click.pass_context
def archive_cmd(ctx: click.Context, pid: str, version: str) -> None:
    workspace_root = os.getcwd()
    if ctx.obj and hasattr(ctx.obj, "workspace_root"):
        workspace_root = ctx.obj.workspace_root

    proj_dir = _resolve_project_dir(workspace_root, pid)
    service = PrototypeService(workspace_root)
    res = service.archive(proj_dir, version=version)

    if res.success:
        console.print(f"[green]✓ 原型版本 {version} 归档成功: {res.output_path}[/green]")
    else:
        console.print(f"[red]✗ 原型归档失败: {res.message}[/red]")

@prototype_cmd.command(name="init", help="初始化全新的原型脚手架骨架")
@click.option("--pid", "-p", required=True, help="项目 ID")
@click.option("--template", "-t", default="hmi", help="模板类型 (hmi / industrial-hmi / web)")
@click.option(
    "--topology",
    type=click.Choice(["both", "infeed", "outfeed"]),
    default="both",
    help="流水线拓扑: both(上游+下游双向), infeed(仅上游进料/末端码垛), outfeed(仅下游出料/首端上料)",
)
@click.pass_context
def init_cmd(ctx: click.Context, pid: str, template: str, topology: str) -> None:
    workspace_root = os.getcwd()
    if ctx.obj and hasattr(ctx.obj, "workspace_root"):
        workspace_root = ctx.obj.workspace_root

    proj_dir = _resolve_project_dir(workspace_root, pid)
    service = PrototypeService(workspace_root)
    res = service.init(proj_dir, template=template, topology=topology)

    if res.success:
        console.print(f"[green]✓ 原型脚手架初始化成功: {res.output_path}[/green]")
    else:
        console.print(f"[red]✗ 初始化失败: {res.message}[/red]")
