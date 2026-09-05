"""PLC-HMI 概念映射：程序入口（Python CLI 子命令（Python 项目操作））

像 PLC 的启动流程，程序的上电入口点。

--- 原始注释 ---

python 子命令组 - Python 项目管理

Commands:
    init <ID> --name <NAME>   创建 Python 项目骨架（Copier python-tool 模板）
    check <ID>                检查 Python 项目规范（210/211/220）
"""

from __future__ import annotations

import json
import os
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from auto_pm.app_context import AppContext
from auto_pm.core.paths import PYTHON_REQUIRED_DIRS
from auto_pm.core.project_service import ProjectService
from auto_pm.core.template_service import TemplateService

console = Console()


# Python 项目规范必需文件（210 规范）
_REQUIRED_FILES = [
    "pyproject.toml",
    "README.md",
    ".copier-answers.yml",
    ".ruff.toml",
    ".pre-commit-config.yaml",
    "Taskfile.yml",
]

# Python 项目规范必需目录（CHG-SCPT-2026-144: 引用集中常量）
_REQUIRED_DIRS = PYTHON_REQUIRED_DIRS


@click.group(name="python")
@click.pass_context
def python_group(ctx: click.Context) -> None:
    """Python 项目管理 - 初始化/检查（210/211/220 规范）"""


@python_group.command(name="init")
@click.argument("project_id")
@click.option("--name", "project_name", required=True, help="项目名称")
@click.option("--desc", "description", default="", help="项目描述")
@click.option("--package", "package_name", default=None, help="Python 包名（默认从项目名生成）")
@click.option("--author", default="fubai", help="作者名")
@click.option("--dry-run", is_flag=True, help="仅预览，不实际创建")
@click.pass_context
def cmd_init(
    ctx: click.Context,
    project_id: str,
    project_name: str,
    description: str,
    package_name: str | None,
    author: str,
    dry_run: bool,
) -> None:
    """创建 Python 项目骨架（调用 Copier python-tool 模板）"""
    app_ctx: AppContext = ctx.obj

    # 推导 package_name 和 cli_command
    if package_name is None:
        package_name = project_name.replace(" ", "_").lower()
    cli_command = package_name.replace("_", "-")

    # 目标路径
    project_dir = f"{project_id}_{project_name}"
    dest_path = os.path.join(app_ctx.workspace_root, project_dir)

    if os.path.exists(dest_path):
        console.print(f"[red]错误: 目标路径已存在: {dest_path}[/red]")
        ctx.exit(1)

    if dry_run:
        console.print(f"[yellow][DRY-RUN] 将创建 Python 项目: {dest_path}[/yellow]")
        console.print("  模板: python-tool")
        console.print(f"  编号: {project_id}")
        console.print(f"  名称: {project_name}")
        console.print(f"  包名: {package_name}")
        console.print(f"  CLI 命令: {cli_command}")
        return

    # 调用 Copier 模板
    tpl_svc = TemplateService(app_ctx.templates_dir)
    data: dict[str, Any] = {
        "project_id": project_id,
        "project_name": project_name,
        "package_name": package_name,
        "cli_command": cli_command,
        "description": description or project_name,
        "author": author,
        "version": "0.1.0",
    }

    try:
        tpl_svc.copy_template("python-tool", dest_path, data)
        console.print(f"[green]Python 项目创建成功: {dest_path}[/green]")
        console.print(f"  项目编号: {project_id}")
        console.print(f"  项目名称: {project_name}")
        console.print(f"  包名: {package_name}")
        console.print(f"  CLI 命令: {cli_command}")
    except FileNotFoundError as e:
        console.print(f"[red]错误: 模板不存在 - {e}[/red]")
        ctx.exit(1)
    except Exception as e:
        console.print(f"[red]创建失败: {e}[/red]")
        ctx.exit(1)


@python_group.command(name="check")
@click.argument("project_id", required=False)
@click.option("--all", "check_all", is_flag=True, help="检查工作空间所有 Python 项目")
@click.option("--json", "output_json", is_flag=True, help="以JSON格式输出结果")
@click.pass_context
def cmd_check(
    ctx: click.Context,
    project_id: str | None,
    check_all: bool,
    output_json: bool,
) -> None:
    """检查 Python 项目规范（210/211/220）"""
    app_ctx: AppContext = ctx.obj
    svc = ProjectService(app_ctx.workspace_root)

    # 确定检查目标
    if check_all:
        all_projects = svc.list_projects()
        python_candidates = [p for p in all_projects if p.stack == "python"]
        # V0.5.4: 过滤非 Python 项目（无 pyproject.toml 且 .copier-answers.yml 中无 python stack）
        targets = [p for p in python_candidates if _is_python_project(p.path)]
        if not targets:
            if python_candidates:
                skipped = len(python_candidates) - len(targets)
                console.print(
                    f"[yellow]未发现 Python 项目（跳过 {skipped} 个非 Python 项目）[/yellow]"
                )
            else:
                console.print("[yellow]未发现 Python 项目[/yellow]")
            return
    elif project_id:
        proj = svc.get_project(project_id)
        if proj is None:
            console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
            ctx.exit(1)
        if proj.stack != "python":
            console.print(
                f"[red]错误: 项目 {project_id} 不是 Python 项目（stack={proj.stack}）[/red]"
            )
            ctx.exit(1)
        # V0.5.4: 单项目模式也检查是否为实际 Python 项目
        if not _is_python_project(proj.path):
            console.print(
                f"[yellow]警告: 项目 {project_id} 缺少 pyproject.toml 且 .copier-answers.yml 中无 python stack，"
                f"可能不是 Python 项目[/yellow]"
            )
            console.print(
                "[dim]仍将执行检查，但结果可能不准确。建议使用 --all 模式自动过滤。[/dim]"
            )
        targets = [proj]
    else:
        console.print("[red]错误: 请指定项目编号或使用 --all[/red]")
        ctx.exit(1)

    results: list[dict[str, Any]] = []
    for proj in targets:
        result = _check_python_project(proj.path, proj.project_id)
        results.append(result)

    if output_json:
        click.echo(json.dumps(results, ensure_ascii=False, indent=2))
        return

    # 表格输出
    for result in results:
        table = Table(title=f"Python 项目检查: {result['project_id']}")
        table.add_column("检查项", style="cyan")
        table.add_column("状态", style="white")
        table.add_column("说明", style="dim")

        for item in result["checks"]:
            status = "[green]✓[/green]" if item["ok"] else "[red]✗[/red]"
            table.add_row(item["name"], status, item.get("detail", ""))

        console.print(table)
        console.print()


@python_group.command(name="repair")
@click.argument("project_id")
@click.option("--dry-run", is_flag=True, help="仅预览修复，不实际写入文件")
@click.pass_context
def cmd_repair(
    ctx: click.Context,
    project_id: str,
    dry_run: bool,
) -> None:
    """修复 Python 项目规范问题"""
    app_ctx: AppContext = ctx.obj
    proj_svc = ProjectService(app_ctx.workspace_root)
    proj = proj_svc.get_project(project_id)
    if proj is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)
    if proj.stack != "python":
        console.print(f"[red]错误: 项目 {project_id} 不是 Python 项目（stack={proj.stack}）[/red]")
        ctx.exit(1)

    from auto_pm.core.python_service import PythonProjectService

    package_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    templates_dir = os.path.join(package_dir, "templates")
    py_svc = PythonProjectService(app_ctx.workspace_root, templates_dir=templates_dir)

    repaired = py_svc.repair_project_spec(proj.path, project_id, dry_run=dry_run)
    if dry_run:
        console.print("[yellow][DRY-RUN] 将执行以下修复工作：[/yellow]")
    else:
        console.print("[green]成功修复以下规范项目：[/green]")
    for item in repaired:
        console.print(f"  - {item}")
    if not repaired:
        console.print("[green]项目完全合规，无需修复。[/green]")


def _check_python_project(project_path: str, project_id: str) -> dict[str, Any]:
    """检查单个 Python 项目规范"""
    from auto_pm.core.python_service import PythonProjectService

    package_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    templates_dir = os.path.join(package_dir, "templates")
    svc = PythonProjectService(os.path.dirname(project_path), templates_dir=templates_dir)
    return dict(svc.check_project_spec(project_path, project_id))


def _is_python_project(project_path: str) -> bool:
    """判断项目是否为 Python 项目（V0.5.4）

    判断规则：
    - 有 pyproject.toml → Python 项目
    - 有 .copier-answers.yml 且 _src_path 含 "python" → Python 项目
    - 其他 → 非 Python 项目（如遗留 PLC 项目、仅含 PM_SESSION 的混合项目）
    """
    # 有 pyproject.toml → 确定是 Python 项目
    if os.path.isfile(os.path.join(project_path, "pyproject.toml")):
        return True

    # 有 .copier-answers.yml 且 _src_path 含 python → Python 项目
    copier_path = os.path.join(project_path, ".copier-answers.yml")
    if os.path.isfile(copier_path):
        try:
            import yaml

            with open(copier_path, encoding="utf-8") as f:
                answers = yaml.safe_load(f) or {}
            src_path = answers.get("_src_path", "")
            if "python" in src_path.lower():
                return True
        except Exception:
            pass

    return False
