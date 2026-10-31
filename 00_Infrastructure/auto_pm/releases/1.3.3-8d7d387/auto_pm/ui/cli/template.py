"""PLC-HMI 概念映射：CLI 命令行入口（模板命令组（模板列表/应用））

像 PLC 的调试终端/工程师站，通过命令行直接操作功能块。
不经过 HMI 画面，直接调用 FB 或 SFB。

--- 原始注释 ---

template 子命令组 - Copier 模板管理

Commands:
    list                列出可用模板
    update <ID>         对已有项目执行 Copier 模板增量更新
"""

from __future__ import annotations

import os

import click
from rich.console import Console
from rich.table import Table

from auto_pm.app_context import AppContext
from auto_pm.core.project_service import ProjectService
from auto_pm.core.template_service import TemplateService

console = Console()


@click.group(name="template")
@click.pass_context
def template_group(ctx: click.Context) -> None:
    """模板管理 - 列表/更新（Copier）"""


@template_group.command(name="list")
@click.pass_context
def cmd_list(ctx: click.Context) -> None:
    """列出可用模板"""
    app_ctx: AppContext = ctx.obj
    tpl_svc = TemplateService(app_ctx.templates_dir)

    templates = tpl_svc.list_templates()
    if not templates:
        console.print(f"[yellow]未发现模板（模板目录: {app_ctx.templates_dir}）[/yellow]")
        return

    table = Table(title=f"可用模板 ({len(templates)} 个)")
    table.add_column("模板名称", style="cyan")
    table.add_column("路径", style="dim")

    for name in templates:
        table.add_row(name, os.path.join(app_ctx.templates_dir, name))

    console.print(table)


@template_group.command(name="update")
@click.argument("project_id")
@click.option("--overwrite", is_flag=True, help="覆盖冲突文件")
@click.pass_context
def cmd_update(
    ctx: click.Context, project_id: str, overwrite: bool
) -> None:
    """对已有项目执行 Copier 模板增量更新"""
    app_ctx: AppContext = ctx.obj

    proj_svc = ProjectService(app_ctx.workspace_root)
    proj = proj_svc.get_project(project_id)
    if proj is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)

    tpl_svc = TemplateService(app_ctx.templates_dir)
    try:
        tpl_svc.update_template(proj.path, overwrite=overwrite)
        console.print(f"[green]模板更新成功: {proj.path}[/green]")
    except FileNotFoundError as e:
        console.print(f"[red]错误: {e}[/red]")
        console.print("[yellow]项目缺少 .copier-answers.yml，无法增量更新[/yellow]")
        ctx.exit(1)
    except Exception as e:
        console.print(f"[red]更新失败: {e}[/red]")
        ctx.exit(1)
