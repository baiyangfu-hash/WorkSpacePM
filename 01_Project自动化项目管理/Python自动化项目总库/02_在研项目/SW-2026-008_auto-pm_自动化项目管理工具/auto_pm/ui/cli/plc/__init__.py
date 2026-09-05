"""PLC-HMI 概念映射：程序入口（PLC CLI 子命令（PLC 项目操作））

像 PLC 的启动流程，程序的上电入口点。

--- 原始注释 ---

plc 子命令组 - PLC 项目管理（LSP-907 907_项目配置规范_LSP）

Commands:
    init <ID>                    创建 PLC 项目骨架（Copier 模板）
    check <ID>                   检查项目结构（LSP-907）
    check --all                  检查工作空间所有项目
    repair <ID> [--rename]       自动修复项目结构
    standardize <ID> [--apply]   文档命名标准化
"""

from __future__ import annotations

import json
import os

import click
from rich.console import Console
from rich.table import Table

from auto_pm.app_context import AppContext
from auto_pm.core.project_service import ProjectService
from auto_pm.core.template_service import TemplateService
from auto_pm.plc.checker import PlcChecker
from auto_pm.plc.models import CheckResult, RepairResult
from auto_pm.plc.service import PlcService

console = Console()


@click.group(name="plc")
@click.pass_context
def plc_group(ctx: click.Context) -> None:
    """PLC 项目管理 - 初始化/检查/修复/标准化（LSP-907）"""


@plc_group.command(name="init")
@click.argument("project_id")
@click.option("--name", "project_name", required=True, help="项目名称")
@click.option("--desc", "description", default="", help="项目描述")
@click.option(
    "--mode",
    type=click.Choice(["shared-library", "test-suite", "standard-project"]),
    default="standard-project",
    help="PLC 项目模式（默认 standard-project）",
)
@click.pass_context
def cmd_init(
    ctx: click.Context, project_id: str, project_name: str, description: str, mode: str
) -> None:
    """创建 PLC 项目骨架（调用 Copier 模板）

    也可使用: project create --stack plc --mode <MODE>
    """
    app_ctx: AppContext = ctx.obj

    project_dir = f"{project_id}_{project_name}"
    dest_path = os.path.join(app_ctx.workspace_root, project_dir)

    if os.path.exists(dest_path):
        console.print(f"[red]错误: 目标路径已存在: {dest_path}[/red]")
        ctx.exit(1)

    from auto_pm.core.constants import get_template_name

    template_name = get_template_name("plc", mode)

    tpl_svc = TemplateService(app_ctx.templates_dir)
    data = {
        "project_id": project_id,
        "project_name": project_name,
        "description": description or project_name,
        "version": "V1.0.0",
    }

    try:
        tpl_svc.copy_template(template_name, dest_path, data)
        console.print(f"[green]PLC 项目创建成功: {dest_path}[/green]")
        console.print(f"[dim]模式: {mode} | 模板: {template_name}[/dim]")
    except FileNotFoundError as e:
        console.print(f"[red]错误: 模板不存在 - {e}[/red]")
        console.print(
            f"[yellow]提示: 模板 {template_name} 可能尚未创建，请检查 templates/ 目录[/yellow]"
        )
        ctx.exit(1)
    except Exception as e:
        console.print(f"[red]创建失败: {e}[/red]")
        ctx.exit(1)


@plc_group.command(name="check")
@click.argument("project_id", required=False)
@click.option("--all", "check_all", is_flag=True, help="检查工作空间所有项目")
@click.option("--json", "output_json", is_flag=True, help="以JSON格式输出结果")
@click.option("--substance", is_flag=True, help="执行文档实质化检查（V2.0.1-B）")
@click.option("--fix", is_flag=True, help="检查后自动修复非破坏性问题")
@click.option("--list", "list_items", is_flag=True, help="列出所有检查项及说明")
@click.pass_context
def cmd_check(
    ctx: click.Context,
    project_id: str | None,
    check_all: bool,
    output_json: bool,
    substance: bool,
    fix: bool,
    list_items: bool,
) -> None:
    """检查项目结构是否符合 LSP-907 规范"""
    app_ctx: AppContext = ctx.obj

    if list_items:
        _print_check_items()
        return

    svc = PlcService(app_ctx.workspace_root)

    if check_all:
        results = svc.check_workspace()
        if not results:
            if output_json:
                print(json.dumps([], ensure_ascii=False, indent=2))  # noqa: T201
            else:
                console.print("[yellow]未发现 PLC 项目[/yellow]")
            return
        if output_json:
            print(json.dumps([r.model_dump() for r in results], ensure_ascii=False, indent=2))  # noqa: T201
        else:
            _print_check_summary(results)
        return

    if not project_id:
        console.print("[red]错误: 请指定项目ID 或使用 --all[/red]")
        ctx.exit(1)

    # 查找项目路径
    proj_svc = ProjectService(app_ctx.workspace_root)
    proj = proj_svc.get_project(project_id)
    if proj is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)

    if substance:
        result = svc.check_substance(proj.path)
    else:
        result = svc.check(proj.path, fix=fix)

    # V0.4.1 Step 3: Python 项目不适用 PLC 检查时输出友好提示
    if result.not_applicable:
        if output_json:
            print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))  # noqa: T201
        else:
            console.print(f"[blue]PLC 检查不适用: {project_id}[/blue]")
            console.print(f"[dim]{result.not_applicable_reason}[/dim]")
            console.print(
                "[dim]提示: Python 项目（无 .plc.json + 有 pyproject.toml）"
                "无需执行 PLC 检查；驾驶舱会自动跳过该项目。[/dim]"
            )
        return

    if output_json:
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))  # noqa: T201
    else:
        _print_check_detail(result)

    # P3-8: 自动生成 ai_context.json 供 cockpit/AI 技能恢复上下文
    if not result.not_applicable:
        from auto_pm.cli import write_ai_context

        write_ai_context(
            workspace_root=app_ctx.workspace_root,
            project_id=project_id,
            project_name=proj.name,
            stack=proj.stack,
            phase=proj.phase or "",
        )


@plc_group.command(name="repair")
@click.argument("project_id")
@click.option("--rename", "rename_confirm", is_flag=True, help="确认文件重命名（破坏性操作）")
@click.option("--dry-run", is_flag=True, help="仅预览不执行")
@click.pass_context
def cmd_repair(ctx: click.Context, project_id: str, rename_confirm: bool, dry_run: bool) -> None:
    """自动修复项目结构问题"""
    app_ctx: AppContext = ctx.obj

    proj_svc = ProjectService(app_ctx.workspace_root)
    proj = proj_svc.get_project(project_id)
    if proj is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)

    svc = PlcService(app_ctx.workspace_root)
    result = svc.repair(proj.path, dry_run=dry_run, rename_confirm=rename_confirm)

    _print_repair_result(result)


@plc_group.command(name="ingest")
@click.option("--src", "source_dir", required=True, help="PLC 源工程根目录绝对/相对路径")
@click.option("--pid", "project_id", required=True, help="目标 PLC 项目编号 (如 DJ-2026-009)")
@click.option("--stage-only", is_flag=True, help="仅提取至 .ingest_staging 暂存区，不污染正式工程")
@click.pass_context
def cmd_ingest(ctx: click.Context, source_dir: str, project_id: str, stage_only: bool) -> None:
    """工业源工程全量逆向摄取与资产灌入 (AutoShop / TIA Portal)"""
    app_ctx: AppContext = ctx.obj
    ws = app_ctx.workspace_root

    plc_svc = PlcService(workspace_root=ws)
    try:
        target_path = plc_svc.resolve_project_path(project_id)
    except Exception:
        target_path = os.path.join(ws, "0100_PLC自动化", project_id)

    from auto_pm.application.plc.ingest_service import PlcIngestService

    console.print("[bold cyan]正在启动 PLC 逆向摄取流水线 (ETL)...[/bold cyan]")
    console.print(f"  • 源工程: {source_dir}")
    console.print(f"  • 目标工程: {target_path}")
    console.print(
        f"  • 模式: {'[yellow]暂存隔离提取 (--stage-only)[/yellow]' if stage_only else '[green]全量提取并投影[/green]'}"
    )

    ingest_svc = PlcIngestService(workspace_root=ws)
    try:
        if stage_only:
            res = ingest_svc.ingest_to_staging(
                source_dir=source_dir,
                target_project_path=target_path,
                project_id=project_id,
                project_name="工业设备",
            )
            console.print(
                "\n[bold green]✓ 逆向数据已安全提取至 .ingest_staging/ 暂存区！[/bold green]"
            )
            console.print(f"  • 提取变量总数: [bold yellow]{res.total_variables}[/bold yellow] 个")
            console.print(f"  • 报警矩阵点位: [bold red]{res.total_alarms}[/bold red] 个")
            console.print(f"  • 伺服轴控点位: [bold cyan]{res.total_servos}[/bold cyan] 个")
            console.print(f"  • 硬件 IO 点位: [bold magenta]{res.total_ios}[/bold magenta] 个")
            console.print(f"  • 暂存报告: {target_path}/.ingest_staging/staging_report.md")
            console.print(
                f"[dim]提示: 请在驾驶舱审核点表后，执行 auto-pm plc promote {project_id} 投影到正式工程[/dim]"
            )
        else:
            res = ingest_svc.ingest_autoshop_project(
                source_dir=source_dir,
                target_project_path=target_path,
                project_id=project_id,
                project_name="工业设备",
            )
            console.print("\n[bold green]✓ 逆向摄取与标准化资产生成成功！[/bold green]")
            console.print(f"  • 提取变量总数: [bold yellow]{res.total_variables}[/bold yellow] 个")
            console.print(f"  • 累计生成黄金工程文档与资产: {len(res.generated_files)} 份")
    except Exception as e:
        console.print(f"[bold red]✗ 逆向摄取失败: {e}[/bold red]")
        raise click.Abort()


@plc_group.command(name="promote")
@click.argument("project_id")
@click.pass_context
def cmd_promote(ctx: click.Context, project_id: str) -> None:
    """将 .ingest_staging 暂存区中审核通过的草案正式投影到工程资产与文档"""
    app_ctx: AppContext = ctx.obj
    ws = app_ctx.workspace_root

    plc_svc = PlcService(workspace_root=ws)
    try:
        target_path = plc_svc.resolve_project_path(project_id)
    except Exception:
        target_path = os.path.join(ws, "0100_PLC自动化", project_id)

    from auto_pm.application.plc.ingest_service import PlcIngestService

    ingest_svc = PlcIngestService(workspace_root=ws)
    try:
        res = ingest_svc.promote_staging(
            target_project_path=target_path,
            project_id=project_id,
            project_name="工业设备",
        )
        console.print("\n[bold green]✓ 暂存资产成功正式投影至工程！[/bold green]")
        console.print(f"  • 变量总数: {res.total_variables} 个")
        console.print("  • 正式点表: 02_PLC程序/工程资产/io_points.csv")
        console.print("  • 自动派生文档: 015_IO分配表_IO.md, PLC变量定义文档_VAR.md")
    except Exception as e:
        console.print(f"[bold red]✗ 资产投影失败: {e}[/bold red]")
        raise click.Abort()


@plc_group.command(name="standardize")
@click.argument("project_id")
@click.option("--apply", is_flag=True, help="执行重命名（默认仅预览）")
@click.pass_context
def cmd_standardize(ctx: click.Context, project_id: str, apply: bool) -> None:
    """检测并修正 PRD 文档命名"""
    app_ctx: AppContext = ctx.obj

    proj_svc = ProjectService(app_ctx.workspace_root)
    proj = proj_svc.get_project(project_id)
    if proj is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)

    svc = PlcService(app_ctx.workspace_root)
    result = svc.standardize(proj.path, dry_run=not apply)

    if not result.plans:
        console.print("[green]无需标准化：所有文档命名已符合规范[/green]")
        return

    table = Table(title=f"文档标准化结果 ({'已执行' if apply else '仅预览'})")
    table.add_column("原文件名", style="red")
    table.add_column("标准文件名", style="green")
    table.add_column("类型", style="cyan")
    table.add_column("状态", style="yellow")

    for plan in result.plans:
        status = "已重命名" if plan.applied else "待确认"
        table.add_row(
            os.path.basename(plan.old_path),
            os.path.basename(plan.new_path),
            plan.doc_type,
            status,
        )

    console.print(table)
    if not apply and result.plans:
        console.print("[yellow]使用 --apply 执行重命名[/yellow]")


# ── 输出辅助 ──────────────────────────────────────────────


def _print_check_items() -> None:
    """打印所有检查项清单（--list 模式）"""
    from auto_pm.plc.checker import PlcChecker

    # 按 category 分组
    categories: dict[str, list[dict[str, str]]] = {}
    for item in PlcChecker.CHECK_ITEMS:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    table = Table(title="PLC 检查项清单 (plc check)")
    table.add_column("#", style="dim", width=3)
    table.add_column("分类", style="cyan", width=6)
    table.add_column("检查项", style="bold", width=22)
    table.add_column("说明", style="white")
    table.add_column("规范引用", style="dim", width=18)

    # 按分类排序输出
    cat_order = ["配置", "文档", "结构", "规范"]
    for cat in cat_order:
        items = categories.get(cat, [])
        for item in items:
            table.add_row(
                item["id"],
                item["category"],
                item["item"],
                item["description"],
                item["spec"],
            )

    console.print(table)
    console.print(
        f"\n[dim]共 {len(PlcChecker.CHECK_ITEMS)} 项检查，覆盖 4 个分类（配置/文档/结构/规范）[/dim]"
    )
    console.print("[dim]使用: auto-pm -w <工作空间根> plc check <项目ID> 执行检查[/dim]")


def _print_check_summary(results: list[CheckResult]) -> None:
    """打印批量检查摘要

    V0.2.1-P2-4: 项目列使用 project_id（与 project show 一致），
    而非目录名。

    V0.4.1 Step 3: not_applicable 项目（Python 项目）从 PASS/FAIL 统计中分离，
    单独以「PLC 检查不适用」展示，避免计入 FAIL 误报。
    """
    # V0.4.1 Step 3: 分离 not_applicable 项目（Python 项目）
    applicable = [r for r in results if not r.not_applicable]
    not_applicable = [r for r in results if r.not_applicable]

    table = Table(title=f"PLC 项目检查摘要 ({len(applicable)} 个)")
    table.add_column("项目", style="cyan")
    table.add_column("类型", style="dim")
    table.add_column("Pass", style="green", justify="right")
    table.add_column("Warn", style="yellow", justify="right")
    table.add_column("Fail", style="red", justify="right")
    table.add_column("状态", style="bold")

    total_pass = 0
    for r in applicable:
        status = "[green]PASS[/green]" if r.all_pass else "[red]FAIL[/red]"
        if r.all_pass:
            total_pass += 1
        table.add_row(
            PlcChecker.resolve_project_id(r.project_path),
            r.project_type,
            str(r.pass_count),
            str(r.warn_count),
            str(r.fail_count),
            status,
        )

    console.print(table)
    console.print(
        f"\n合计: {len(applicable)} 个项目, {total_pass} 个 PASS, "
        f"{len(applicable) - total_pass} 个 FAIL"
    )

    # V0.4.1 Step 3: not_applicable 项目单独展示
    if not_applicable:
        console.print(
            f"\n[blue]PLC 检查不适用项目: {len(not_applicable)} 个（Python 项目，已跳过检查）[/blue]"
        )
        for r in not_applicable:
            pid = PlcChecker.resolve_project_id(r.project_path)
            console.print(f"  [dim]- {pid}: {r.not_applicable_reason}[/dim]")


def _print_check_detail(result: CheckResult) -> None:
    """打印单项目检查详情

    V0.2.1-P2-4: 标题使用 project_id（与 project show 一致）。
    """
    project_id = PlcChecker.resolve_project_id(result.project_path)
    table = Table(title=f"检查结果: {project_id}")
    table.add_column("检查项", style="cyan")
    table.add_column("状态", style="bold")
    table.add_column("说明", style="white")

    for item in result.items:
        if item.status == "pass":
            status_str = "[green]PASS[/green]"
        elif item.status == "warn":
            status_str = "[yellow]WARN[/yellow]"
        else:
            status_str = "[red]FAIL[/red]"
        table.add_row(item.item, status_str, item.message)

    console.print(table)
    console.print(
        f"\nPass={result.pass_count} "
        f"Warn={result.warn_count} "
        f"Fail={result.fail_count} "
        f"-> {'[green]ALL PASS[/green]' if result.all_pass else '[red]HAS FAIL[/red]'}"
    )


def _print_repair_result(result: RepairResult) -> None:
    """打印修复结果

    V0.2.1-P2-4: 标题使用 project_id（与 project show 一致）。
    """
    project_id = PlcChecker.resolve_project_id(result.project_path)
    table = Table(title=f"修复结果: {project_id}")
    table.add_column("修复项", style="cyan")
    table.add_column("动作", style="white")
    table.add_column("破坏性", style="dim")
    table.add_column("状态", style="bold")
    table.add_column("说明", style="dim")

    for action in result.actions:
        if action.status == "fixed":
            status_str = "[green]FIXED[/green]"
        elif action.status == "skipped":
            status_str = "[yellow]SKIPPED[/yellow]"
        else:
            status_str = "[red]FAILED[/red]"
        destructive = "是" if action.destructive else "否"
        table.add_row(action.item, action.action, destructive, status_str, action.detail)

    console.print(table)
    console.print(
        f"\nFixed={result.fixed_count} Skipped={result.skipped_count} Failed={result.failed_count}"
    )

    if result.after_check is not None:
        console.print(
            f"修复后检查: Pass={result.after_check.pass_count} "
            f"Warn={result.after_check.warn_count} "
            f"Fail={result.after_check.fail_count} "
            f"-> {'[green]ALL PASS[/green]' if result.after_check.all_pass else '[red]HAS FAIL[/red]'}"
        )
