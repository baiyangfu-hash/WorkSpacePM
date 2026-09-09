"""Doctor 环境与依赖自检 CLI 命令 (CHG-SCPT-2026-155 纯净度防守升级)"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from auto_pm.core.governance_service import GovernanceService

console = Console()


def resolve_workspace(workspace_root: str | None = None) -> str:
    if workspace_root:
        return os.path.abspath(workspace_root)
    from auto_pm.app_context import AppContext
    return AppContext().workspace_root


def run_doctor_check(workspace_root: str | None = None) -> dict[str, Any]:
    """执行综合环境健康诊断

    Returns:
        包含诊断结果的字典
    """
    root = resolve_workspace(workspace_root)

    # 1. Python 版本检查
    py_ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 11)

    # 2. 核心依赖检查
    dependencies = ["rich", "click", "pydantic", "PySide6", "copier", "yaml", "ruff", "pytest", "mypy"]
    dep_results: dict[str, bool] = {}
    for dep in dependencies:
        spec = importlib.util.find_spec(dep)
        dep_results[dep] = spec is not None

    # 3. pyproject.toml 版本
    pyproject_path = Path(root) / "pyproject.toml"
    version_str = "1.1.0"
    if pyproject_path.exists():
        try:
            import tomli as tomllib
        except ImportError:
            import tomllib
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                version_str = data.get("project", {}).get("version", "1.1.0")
        except Exception:
            pass

    # 4. Git 工作区检查
    git_dir = Path(root) / ".git"
    git_ok = git_dir.exists()

    # 5. 工作空间纯净度守卫
    gov_service = GovernanceService(workspace_root=root)
    sanitation_report = gov_service.inspect_sanitation()

    all_passed = py_ok and git_ok and sanitation_report.is_pure and all(dep_results.values())

    return {
        "workspace_root": str(root),
        "python_version": py_ver,
        "python_ok": py_ok,
        "dependencies": dep_results,
        "project_version": version_str,
        "git_found": git_ok,
        "sanitation_pure": sanitation_report.is_pure,
        "sanitation_issues": sanitation_report.total_issues,
        "all_passed": all_passed,
    }


@click.command("doctor")
@click.option("-w", "--workspace", type=click.Path(exists=True), help="工作空间根目录")
def doctor_command(workspace: str | None) -> None:
    """执行 auto-pm 环境与依赖健康诊断"""
    console.print(Panel.fit("[bold blue]auto-pm 环境与依赖健康诊断[/bold blue]", border_style="blue"))

    res = run_doctor_check(workspace)

    table = Table(title="诊断明细", show_header=True, header_style="bold magenta")
    table.add_column("检查项", style="cyan")
    table.add_column("状态", style="bold")
    table.add_column("说明", style="dim")

    # Python
    py_status = "[green]✅ PASS[/green]" if res["python_ok"] else "[red]❌ FAIL[/red]"
    table.add_row("Python 版本", py_status, f"{res['python_version']} (要求 >= 3.11)")

    # 版本
    table.add_row("源码版本号", "[blue]ℹ INFO[/blue]", f"pyproject.toml version: {res['project_version']}")

    # 依赖项
    for dep, ok in res["dependencies"].items():
        dep_status = "[green]✅ 已安装[/green]" if ok else "[yellow]⚠️ 未找到[/yellow]"
        table.add_row(f"依赖: {dep}", dep_status, "可用" if ok else "开发环境建议安装")

    # 工作空间
    table.add_row("工作空间根目录", "[blue]ℹ INFO[/blue]", res["workspace_root"])
    git_status = "[green]✅ PASS[/green]" if res["git_found"] else "[yellow]⚠️ 未找到[/yellow]"
    table.add_row("Git 仓库", git_status, "已检测到 .git" if res["git_found"] else "未检测到 .git")

    # 根目录纯净度守卫
    sani_status = "[green]✅ 根目录纯净[/green]" if res["sanitation_pure"] else f"[bold yellow]⚠️ 存在 {res['sanitation_issues']} 个游离文件[/bold yellow]"
    sani_msg = "符合根目录白名单规范" if res["sanitation_pure"] else "建议运行 'auto-pm clean' 进行自动清扫"
    table.add_row("工作空间纯净度守卫", sani_status, sani_msg)

    console.print(table)

    if res["all_passed"]:
        console.print("\n[bold green]🎉 恭喜！当前环境一切正常，可顺畅运行与开发 auto-pm！[/bold green]\n")
    else:
        console.print("\n[bold yellow]⚠️ 注意：存在非标准或缺失依赖，请参考表项修复建议。[/bold yellow]\n")
