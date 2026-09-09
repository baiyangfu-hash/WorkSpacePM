"""PLC-HMI 概念映射：CLI 命令行入口（项目命令组（create/list/edit/delete））

像 PLC 的调试终端/工程师站，通过命令行直接操作功能块。
不经过 HMI 画面，直接调用 FB 或 SFB。

--- 原始注释 ---

project 子命令组 - 项目 CRUD

Commands:
    list                          列出工作空间内所有项目
    create --stack --id --name    创建新项目（调用 Copier 模板）
    show <ID> [--json]            查看项目详情
    edit <ID> [--phase] [--desc]  编辑项目元数据
    delete <ID> --confirm         删除项目
    retrofit <ID>                 补全 .copier-answers.yml 元数据文件
    import <PATH> [--move]        导入外部项目目录到工作空间
    snapshot <ID> [--dry-run]     刷新 PM_SESSION 的 Spec Snapshot 版本号
"""

from __future__ import annotations

import json
import os
import shutil

import click
from rich.console import Console
from rich.table import Table
from yaml import dump as yaml_dump

from auto_pm.app_context import AppContext
from auto_pm.core.constants import (
    EQUIPMENT_TYPE_CODES,
    PLC_VENDOR_CODES,
    PROJECT_TYPE_CODES,
    get_equipment_type_label,
    get_project_type_label,
    get_template_name,
)
from auto_pm.core.paths import WORKSPACE_PROJECTS_SUBDIR
from auto_pm.core.project_service import ProjectService
from auto_pm.core.template_service import TemplateService

console = Console()


def _format_asset_summary_status(status: str) -> str:
    mapping = {
        "healthy": "健康",
        "warning": "需补齐",
        "missing": "缺失",
        "not_applicable": "不适用",
    }
    return mapping.get(status, status or "-")


def _print_asset_summary(extra: dict[str, object]) -> None:
    """输出工程资产摘要"""
    asset_summary = extra.get("asset_summary")
    if not isinstance(asset_summary, dict):
        return

    console.print(
        f"[cyan]工程资产:[/cyan] {_format_asset_summary_status(str(asset_summary.get('status', '')))}"
    )

    if asset_summary.get("status") == "not_applicable":
        messages = asset_summary.get("issue_messages") or []
        if messages:
            console.print(f"[cyan]资产说明:[/cyan] {messages[0]}")
        return

    console.print(
        f"[cyan]资产目录:[/cyan] {'已就绪' if asset_summary.get('asset_dir_exists') else '缺失'}"
    )

    io_points = asset_summary.get("io_points") or {}
    program_blocks = asset_summary.get("program_blocks") or {}
    communications = asset_summary.get("communications") or {}
    if isinstance(io_points, dict):
        console.print(f"[cyan]IO点表:[/cyan] {io_points.get('count', 0)} 条")
    if isinstance(program_blocks, dict):
        console.print(f"[cyan]程序块:[/cyan] {program_blocks.get('count', 0)} 个")
    if isinstance(communications, dict):
        console.print(f"[cyan]通讯对象:[/cyan] {communications.get('count', 0)} 个")

    issue_messages = asset_summary.get("issue_messages") or []
    if isinstance(issue_messages, list) and issue_messages:
        console.print(f"[cyan]资产问题:[/cyan] {len(issue_messages)} 项")
        for message in issue_messages[:3]:
            console.print(f"  - {message}")


@click.group(name="project")
@click.pass_context
def project_group(ctx: click.Context) -> None:
    """项目管理 - 列表/创建/查看/编辑/删除"""


@project_group.command(name="list")
@click.option(
    "--business-line",
    "-bl",
    type=click.Choice(["SW", "DJ", "ZD", "XT", "WX"]),
    default=None,
    help="按业务线筛选（从项目编号前缀提取）",
)
@click.option(
    "--stack",
    type=click.Choice(["plc", "python", "unknown"]),
    default=None,
    help="按技术栈筛选",
)
@click.option(
    "--phase",
    type=click.Choice(["developing", "commissioning", "production", "archived", ""]),
    default=None,
    help="按项目阶段筛选",
)
@click.option(
    "--search",
    default=None,
    help="关键字搜索（匹配项目编号/名称/描述）",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="以JSON格式输出结果",
)
@click.pass_context
def cmd_list(
    ctx: click.Context,
    business_line: str | None,
    stack: str | None,
    phase: str | None,
    search: str | None,
    output_json: bool,
) -> None:
    """列出工作空间内所有项目"""
    app_ctx: AppContext = ctx.obj
    svc = ProjectService(app_ctx.workspace_root)
    projects = svc.list_projects()

    if business_line is not None:
        projects = [p for p in projects if p.project_id.split("-", 1)[0] == business_line]
    if stack is not None:
        projects = [p for p in projects if p.stack == stack]
    if phase is not None:
        projects = [p for p in projects if p.phase == phase]
    if search is not None:
        search_lower = search.lower()
        projects = [
            p
            for p in projects
            if search_lower in p.project_id.lower()
            or search_lower in p.name.lower()
            or search_lower in p.description.lower()
        ]

    if not projects:
        if output_json:
            click.echo("[]")
        else:
            console.print("[yellow]未发现项目[/yellow]")
        return

    if output_json:
        click.echo(json.dumps([p.model_dump() for p in projects], ensure_ascii=False, indent=2))
        return

    table = Table(title=f"项目列表 ({len(projects)} 个)")
    table.add_column("项目ID", style="cyan")
    table.add_column("名称", style="white")
    table.add_column("技术栈", style="green")
    table.add_column("版本", style="yellow")
    table.add_column("阶段", style="magenta")
    table.add_column("业务线", style="blue")
    table.add_column("来源", style="dim")
    table.add_column("路径", style="dim")

    for p in projects:
        table.add_row(
            p.project_id,
            p.name,
            p.stack,
            p.version,
            p.phase or "-",
            p.business_line or "-",
            p.source,
            os.path.relpath(p.path, app_ctx.workspace_root),
        )

    console.print(table)


@project_group.command(name="create")
@click.option("--stack", type=click.Choice(["plc", "python"]), required=True, help="技术栈")
@click.option("--id", "project_id", required=False, default=None, help="项目编号（如 DJ-2026-010），与 --auto-id 互斥")
@click.option("--auto-id", is_flag=True, default=False, help="自动生成项目编号（{业务线}-{年份}-{序号:03d}），与 --id 互斥")
@click.option("--name", "project_name", required=True, help="项目名称")
@click.option("--desc", "description", default="", help="项目描述")
@click.option(
    "--business-line",
    "-bl",
    type=click.Choice(["SW", "DJ", "ZD", "XT", "WX"]),
    default=None,
    help="指定业务线（默认从项目编号前缀推断，不一致时警告）",
)
@click.option(
    "--mode",
    type=click.Choice(["shared-library", "test-suite", "standard-project"]),
    default="standard-project",
    help="PLC 项目模式（仅 --stack=plc 时有效）",
)
@click.option(
    "--library-name",
    "library_name",
    default=None,
    help="共享库名称（仅 --mode=shared-library 时有效，默认从项目名称推断）",
)
@click.option(
    "--project-type",
    type=click.Choice(PROJECT_TYPE_CODES),
    default=None,
    help="项目类型（如 single_machine/line_project）",
)
@click.option(
    "--equipment-type",
    type=click.Choice(EQUIPMENT_TYPE_CODES),
    default=None,
    help="设备类型（如 conveyor/packaging）",
)
@click.option(
    "--plc-vendor",
    type=click.Choice(PLC_VENDOR_CODES),
    default=None,
    help="PLC 品牌（如 Siemens/Mitsubishi）",
)
@click.option("--plc-model", default=None, help="PLC 型号（如 S7-1200）")
@click.option("--dest-dir", "dest_dir", default=None, help="项目存放目录（默认: 动态解析到工作区分类目录）")
@click.option("--base-project", "base_project", default=None, help="溯源父项目（例如用于改造类项目时传入原项目编号）")
@click.option("--dry-run", is_flag=True, help="仅预览，不实际创建")
@click.pass_context
def cmd_create(
    ctx: click.Context,
    stack: str,
    project_id: str | None,
    auto_id: bool,
    project_name: str,
    description: str,
    business_line: str | None,
    mode: str,
    library_name: str | None,
    project_type: str | None,
    equipment_type: str | None,
    plc_vendor: str | None,
    plc_model: str | None,
    dest_dir: str | None,
    base_project: str | None,
    dry_run: bool,
) -> None:
    """创建新项目（调用 Copier 模板生成骨架）"""
    app_ctx: AppContext = ctx.obj

    # 互斥校验：--id 和 --auto-id 不能同时使用
    if project_id and auto_id:
        console.print("[red]错误: --id 和 --auto-id 不能同时使用[/red]")
        ctx.exit(1)

    # 自动生成项目编号
    if auto_id:
        bl = business_line or "SW"
        try:
            from auto_pm.core.project_service import ProjectService

            svc = ProjectService(app_ctx.workspace_root)
            project_id = svc.generate_project_code(bl)
            console.print(f"[green]自动生成项目编号: {project_id}[/green]")
        except Exception as e:
            console.print(f"[red]错误: 自动生成项目编号失败: {e}[/red]")
            ctx.exit(1)

    # 必填校验：必须提供 --id 或 --auto-id
    if not project_id:
        console.print("[red]错误: 必须提供 --id 或 --auto-id[/red]")
        ctx.exit(1)

    # 业务线推断：未指定时从项目编号前缀提取
    if business_line is None:
        business_line = project_id.split("-", 1)[0] if "-" in project_id else ""
    else:
        inferred = project_id.split("-", 1)[0] if "-" in project_id else ""
        if inferred != business_line:
            console.print(
                f"[yellow]提示: 指定业务线 {business_line} 与项目编号前缀 {inferred} 不一致[/yellow]"
            )

    if stack == "plc" and project_type is None:
        default_project_types = {
            "standard-project": "single_machine",
            "shared-library": "shared_library",
            "test-suite": "test_suite",
        }
        project_type = default_project_types.get(mode, "single_machine")

    # 根据技术栈选择模板（M3-Iter7: 统一从 core.constants 读取；H-2: 支持 mode 参数）
    template_name = get_template_name(stack, mode if stack == "plc" else "")

    # 默认项目存放目录：优先使用工作区下的分类目录，废除写死在 auto-pm 源码包的逻辑
    if dest_dir:
        dest_root = os.path.abspath(dest_dir)
    else:
        if stack == "plc":
            dest_root = os.path.join(app_ctx.workspace_root, "0100_PLC自动化")
        else:
            dest_root = os.path.join(app_ctx.workspace_root, "0100_项目")

    # 目标路径
    project_dir = f"{project_id}_{project_name}"
    dest_path = os.path.join(dest_root, project_dir)

    if os.path.exists(dest_path):
        console.print(f"[red]错误: 目标路径已存在: {dest_path}[/red]")
        ctx.exit(1)

    # V0.2.1-P1-4: shared-library 模式需要 library_name 参数
    if stack == "plc" and mode == "shared-library":
        if library_name is None:
            # 从项目名称推断：移除空格，首字母大写（如 "系统库" → "系统库"）
            # 若项目名称是英文则直接使用，否则提示用户指定
            inferred_lib = project_name.replace(" ", "").replace("_", "")
            if inferred_lib and inferred_lib[0].isalpha():
                library_name = inferred_lib
                console.print(
                    f"[yellow]提示: shared-library 模式未指定 --library-name，"
                    f"从项目名称推断为 '{library_name}'[/yellow]"
                )
            else:
                console.print("[red]错误: shared-library 模式需要 --library-name 参数[/red]")
                ctx.exit(1)

    if dry_run:
        console.print(f"[yellow][DRY-RUN] 将创建项目: {dest_path}[/yellow]")
        console.print(f"  模板: {template_name}")
        console.print(f"  编号: {project_id}")
        console.print(f"  名称: {project_name}")
        console.print(f"  技术栈: {stack}")
        console.print(f"  模式: {mode}")
        console.print(f"  业务线: {business_line}")
        console.print(f"  项目类型: {project_type or '-'}")
        console.print(f"  设备类型: {equipment_type or '-'}")
        console.print(f"  PLC 品牌: {plc_vendor or '-'}")
        console.print(f"  PLC 型号: {plc_model or '-'}")
        if library_name:
            console.print(f"  库名称: {library_name}")
        return

    # 调用 Copier 模板
    tpl_svc = TemplateService(app_ctx.templates_dir)
    # V0.2.1-P1-3: data 字典增加 stack/mode/business_line 字段
    # V0.2.1-P1-4: shared-library 模式增加 library_name 字段
    data: dict[str, str] = {
        "project_id": project_id,
        "project_name": project_name,
        "description": description or project_name,
        "version": "V1.0.0",
        "stack": stack,
        "mode": mode if stack == "plc" else "",
        "business_line": business_line,
        "phase": "initiating",
    }
    if base_project:
        data["base_project"] = base_project
    if library_name:
        data["library_name"] = library_name
    for key, value in (
        ("project_type", project_type),
        ("equipment_type", equipment_type),
        ("plc_vendor", plc_vendor),
        ("plc_model", plc_model),
    ):
        if value:
            data[key] = value

    try:
        # 确保目标根目录存在
        os.makedirs(dest_root, exist_ok=True)
        tpl_svc.copy_template(template_name, dest_path, data)
        # 审计日志：记录项目创建操作（电气部门试用期间操作追溯）
        from auto_pm.logging.audit import audit_log
        audit_log(
            "project_create",
            project_id=project_id,
            project_name=project_name,
            stack=stack,
            mode=mode if stack == "plc" else "",
            business_line=business_line,
            path=dest_path,
        )
        console.print(f"[green]项目创建成功: {dest_path}[/green]")
        console.print(f"  项目编号: {project_id}")
        console.print(f"  项目名称: {project_name}")
        console.print(f"  技术栈: {stack}")
        console.print(f"  模式: {mode if stack == 'plc' else '-'}")
        console.print(f"  业务线: {business_line}")
        console.print(f"  项目类型: {project_type or '-'}")
        console.print(f"  设备类型: {equipment_type or '-'}")
        console.print(f"  PLC 品牌: {plc_vendor or '-'}")
        console.print(f"  PLC 型号: {plc_model or '-'}")
        if library_name:
            console.print(f"  库名称: {library_name}")
    except FileNotFoundError as e:
        console.print(f"[red]错误: 模板不存在 - {e}[/red]")
        ctx.exit(1)
    except Exception as e:
        console.print(f"[red]创建失败: {e}[/red]")
        ctx.exit(1)


@project_group.command(name="show")
@click.argument("project_id")
@click.option("--json", "output_json", is_flag=True, help="以JSON格式输出结果")
@click.pass_context
def cmd_show(ctx: click.Context, project_id: str, output_json: bool) -> None:
    """查看项目详情"""
    app_ctx: AppContext = ctx.obj
    svc = ProjectService(app_ctx.workspace_root)
    proj = svc.get_project(project_id)

    if proj is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)

    if output_json:
        click.echo(json.dumps(proj.model_dump(), ensure_ascii=False, indent=2))
    else:
        console.print(f"[cyan]项目ID:[/cyan] {proj.project_id}")
        console.print(f"[cyan]名称:[/cyan]   {proj.name}")
        console.print(f"[cyan]技术栈:[/cyan] {proj.stack}")
        console.print(f"[cyan]版本:[/cyan]   {proj.version}")
        console.print(f"[cyan]阶段:[/cyan]   {proj.phase or '-'}")
        console.print(f"[cyan]业务线:[/cyan] {proj.business_line or '-'}")
        console.print(
            f"[cyan]项目类型:[/cyan] {get_project_type_label(proj.project_type) if proj.project_type else '-'}"
        )
        console.print(
            f"[cyan]设备类型:[/cyan] {get_equipment_type_label(proj.equipment_type) if proj.equipment_type else '-'}"
        )
        console.print(f"[cyan]PLC品牌:[/cyan] {proj.plc_vendor or '-'}")
        console.print(f"[cyan]PLC型号:[/cyan] {proj.plc_model or '-'}")
        console.print(f"[cyan]描述:[/cyan]   {proj.description}")
        console.print(f"[cyan]来源:[/cyan]   {proj.source}")
        console.print(f"[cyan]路径:[/cyan]   {proj.path}")
        _print_asset_summary(proj.extra)

    # P3-8: 自动生成 ai_context.json 供 cockpit/AI 技能恢复上下文
    from auto_pm.cli import write_ai_context
    write_ai_context(
        workspace_root=app_ctx.workspace_root,
        project_id=proj.project_id,
        project_name=proj.name,
        stack=proj.stack,
        phase=proj.phase or "",
    )


@project_group.command(name="edit")
@click.argument("project_id")
@click.option("--phase", default=None, help="更新项目阶段")
@click.option("--desc", "description", default=None, help="更新项目描述")
@click.option("--version", default=None, help="更新项目版本")
@click.option(
    "--business-line",
    "-bl",
    type=click.Choice(["SW", "DJ", "ZD", "XT", "WX"]),
    default=None,
    help="更新业务线（写入 .copier-answers.yml 覆盖从编号前缀提取的值）",
)
@click.pass_context
def cmd_edit(
    ctx: click.Context,
    project_id: str,
    phase: str | None,
    description: str | None,
    version: str | None,
    business_line: str | None,
) -> None:
    """编辑项目元数据（写入 .copier-answers.yml）"""
    app_ctx: AppContext = ctx.obj
    svc = ProjectService(app_ctx.workspace_root)

    kwargs: dict[str, str] = {}
    if phase is not None:
        kwargs["phase"] = phase
    if description is not None:
        kwargs["description"] = description
    if version is not None:
        kwargs["version"] = version
    if business_line is not None:
        kwargs["business_line"] = business_line

    if not kwargs:
        console.print(
            "[yellow]未指定更新字段（使用 --phase/--desc/--version/--business-line）[/yellow]"
        )
        return

    try:
        svc.update_project_meta(project_id, **kwargs)
        console.print(f"[green]项目元数据已更新: {project_id}[/green]")
        console.print(f"  更新字段: {', '.join(kwargs.keys())}")
    except FileNotFoundError as e:
        console.print(f"[red]错误: {e}[/red]")
        ctx.exit(1)


@project_group.command(name="delete")
@click.argument("project_id")
@click.option("--confirm", is_flag=True, help="确认删除（破坏性操作）")
@click.pass_context
def cmd_delete(ctx: click.Context, project_id: str, confirm: bool) -> None:
    """删除项目（破坏性操作，需 --confirm）"""
    app_ctx: AppContext = ctx.obj
    svc = ProjectService(app_ctx.workspace_root)
    proj = svc.get_project(project_id)

    if proj is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)

    if not confirm:
        console.print(f"[yellow]警告: 即将删除项目: {proj.path}[/yellow]")
        console.print("[yellow]请使用 --confirm 确认删除[/yellow]")
        ctx.exit(1)

    try:
        shutil.rmtree(proj.path)
        # 审计日志：记录项目删除操作（破坏性操作必须审计）
        from auto_pm.logging.audit import audit_log
        audit_log(
            "project_delete",
            project_id=project_id,
            project_name=proj.name,
            path=proj.path,
        )
        console.print(f"[green]项目已删除: {proj.path}[/green]")
    except OSError as e:
        console.print(f"[red]删除失败: {e}[/red]")
        ctx.exit(1)


@project_group.command(name="retrofit")
@click.argument("project_id")
@click.pass_context
def cmd_retrofit(ctx: click.Context, project_id: str) -> None:
    """为已有项目补全元数据文件（.copier-answers.yml 及 PLC 标志文件）"""
    app_ctx: AppContext = ctx.obj
    svc = ProjectService(app_ctx.workspace_root)
    proj = svc.get_project(project_id)

    if proj is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)

    # 1. 补全 .copier-answers.yml
    copier_answers_path = os.path.join(proj.path, ".copier-answers.yml")
    if os.path.isfile(copier_answers_path):
        console.print("[yellow]项目已有 .copier-answers.yml，跳过[/yellow]")
    else:
        # Generate .copier-answers.yml content
        # M3-Iter7: 统一从 core.constants 读取模板名映射
        template_name = get_template_name(proj.stack)
        content = {
            "_commit": "HEAD",
            "_src_path": f"templates/{template_name}",
            "project_id": proj.project_id,
            "project_name": proj.name,
            "description": proj.description,
            "version": proj.version,
        }
        try:
            from auto_pm.utils.file_utils import write_file
            write_file(copier_answers_path, yaml_dump(content, default_flow_style=False, allow_unicode=True))
            console.print(f"[green].copier-answers.yml 已创建: {copier_answers_path}[/green]")
        except Exception as e:
            console.print(f"[red]创建 .copier-answers.yml 失败: {e}[/red]")
            ctx.exit(1)

    # 2. 对 PLC 项目，补全标志文件（.plc.json/PM_SESSION/PRD）
    # H-8: 使用 PlcService 层而非直接调用 PlcRepairer（遵循 Phase 1 的 C-3 修复原则）
    if proj.stack == "plc":
        try:
            from auto_pm.plc.service import PlcService

            plc_svc = PlcService(app_ctx.workspace_root)
            repair_result = plc_svc.repair(proj.path, dry_run=False)
            console.print(
                f"[green]PLC 标志文件补全完成: "
                f"fixed={repair_result.fixed_count}, "
                f"skipped={repair_result.skipped_count}[/green]"
            )
        except Exception as e:
            console.print(f"[red]PLC 标志文件补全失败: {e}[/red]")


@project_group.command(name="snapshot")
@click.argument("project_id")
@click.option("--dry-run", is_flag=True, help="仅预览漂移项，不实际更新版本号")
@click.option("--json", "output_json", is_flag=True, help="以JSON格式输出漂移详情")
@click.pass_context
def cmd_snapshot(
    ctx: click.Context,
    project_id: str,
    dry_run: bool,
    output_json: bool,
) -> None:
    """刷新 PM_SESSION 的 Spec Snapshot 版本号（对齐 spec_registry.json）

    从 spec_registry.json 读取最新版本号，更新 PM_SESSION 中 Spec Snapshot 表格的版本号列。
    不限技术栈（PLC/Python 均可），复用 auto_pm.plc.spec_snapshot 模块的解析与对比逻辑。

    \b
    行为：
    - 无漂移 → 输出"已是最新，无需更新"
    - 有漂移 + --dry-run → 输出漂移项预览（不修改文件）
    - 有漂移（默认）→ 更新 PM_SESSION 表格版本号，输出更新结果
    """
    from auto_pm.plc.spec_snapshot import (
        compare_versions,
        load_spec_registry,
        parse_spec_snapshot,
        update_spec_snapshot,
    )

    app_ctx: AppContext = ctx.obj
    svc = ProjectService(app_ctx.workspace_root)
    proj = svc.get_project(project_id)

    if proj is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)

    # 定位 PM_SESSION 文件
    pm_session_path = os.path.join(proj.path, f"PM_SESSION_{project_id}.md")
    if not os.path.isfile(pm_session_path):
        # 尝试模糊匹配
        found = None
        try:
            for f in os.listdir(proj.path):
                if f.startswith("PM_SESSION_") and f.endswith(".md"):
                    found = f
                    break
        except OSError:
            pass
        if found:
            pm_session_path = os.path.join(proj.path, found)
        else:
            console.print(f"[red]错误: PM_SESSION 文件不存在: {pm_session_path}[/red]")
            console.print("[yellow]提示: 请先使用 `auto-pm project retrofit` 补全项目结构[/yellow]")
            ctx.exit(1)

    # 加载 spec_registry.json
    registry = load_spec_registry(app_ctx.workspace_root)
    if registry is None:
        console.print("[red]错误: spec_registry.json 不存在或格式错误[/red]")
        console.print(f"[yellow]提示: 确认工作空间路径正确: {app_ctx.workspace_root}[/yellow]")
        ctx.exit(1)

    # 解析 Spec Snapshot 表格
    snapshot = parse_spec_snapshot(pm_session_path)
    if not snapshot:
        console.print(
            f"[yellow]PM_SESSION 缺少 Spec Snapshot 表格: {os.path.basename(pm_session_path)}[/yellow]"
        )
        console.print(
            "[yellow]提示: 请先使用 `auto-pm project retrofit` 补全 Spec Snapshot 区块[/yellow]"
        )
        ctx.exit(1)

    # 对比版本
    drifts = compare_versions(snapshot, registry)

    if not drifts:
        if output_json:
            click.echo(json.dumps({"drifts": [], "updated": False}, ensure_ascii=False))
        else:
            console.print("[green]Spec Snapshot 已是最新，无需更新[/green]")
        return

    # 有漂移：构造漂移详情
    drift_details = [
        {
            "spec_id": d.spec_id,
            "snapshot_version": d.snapshot_version,
            "registry_version": d.registry_version,
            "drift_level": d.drift_level,
        }
        for d in drifts
    ]

    if dry_run:
        if output_json:
            click.echo(
                json.dumps(
                    {"drifts": drift_details, "updated": False, "dry_run": True},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            console.print(f"[yellow][DRY-RUN] 检测到 {len(drifts)} 条规范版本漂移:[/yellow]")
            table = Table(title="Spec Snapshot 漂移预览")
            table.add_column("规范ID", style="cyan")
            table.add_column("当前版本", style="red")
            table.add_column("最新版本", style="green")
            table.add_column("漂移级别", style="yellow")
            for d in drifts:
                level_names = {
                    "major": "主版本漂移",
                    "minor": "次版本漂移",
                    "patch": "补丁漂移",
                }
                table.add_row(
                    d.spec_id,
                    d.snapshot_version,
                    d.registry_version,
                    level_names.get(d.drift_level, d.drift_level),
                )
            console.print(table)
        return

    # 执行更新
    success = update_spec_snapshot(pm_session_path, drifts)
    if success:
        if output_json:
            click.echo(
                json.dumps(
                    {"drifts": drift_details, "updated": True},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            console.print(
                f"[green]Spec Snapshot 已更新: {os.path.basename(pm_session_path)}[/green]"
            )
            console.print(f"  更新 {len(drifts)} 条规范版本:")
            for d in drifts:
                console.print(f"    {d.spec_id}: {d.snapshot_version} → {d.registry_version}")
    else:
        console.print("[red]错误: 更新失败（写入 PM_SESSION 失败或无内容变更）[/red]")
        ctx.exit(1)


_PROJECTS_SUBDIR = WORKSPACE_PROJECTS_SUBDIR  # M3-Iter6: 从 core.paths 读取


@project_group.command(name="import")
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@click.option("--move", is_flag=True, help="移动而非复制（默认复制）")
@click.option("--force", is_flag=True, help="强制覆盖已存在的目标目录")
@click.option(
    "--business-line",
    "-bl",
    type=click.Choice(["SW", "DJ", "ZD", "XT", "WX"]),
    default=None,
    help="指定业务线（默认从项目编号前缀推断）",
)
@click.pass_context
def cmd_import(
    ctx: click.Context,
    path: str,
    move: bool,
    force: bool,
    business_line: str | None,
) -> None:
    """导入外部项目目录到工作空间的 02_在研项目/ 下"""
    app_ctx: AppContext = ctx.obj
    source_path = os.path.abspath(path)
    dirname = os.path.basename(source_path)
    dest_path = os.path.join(app_ctx.workspace_root, _PROJECTS_SUBDIR, dirname)

    if os.path.exists(dest_path):
        if not force:
            console.print(f"[red]错误: 目标路径已存在: {dest_path}（使用 --force 覆盖）[/red]")
            ctx.exit(1)
        console.print(f"[yellow]强制覆盖: {dest_path}[/yellow]")
        shutil.rmtree(dest_path, ignore_errors=True)

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    try:
        if move:
            shutil.move(source_path, dest_path)
            console.print(f"[green]项目已移动: {dest_path}[/green]")
        else:
            shutil.copytree(source_path, dest_path)
            console.print(f"[green]项目已复制: {dest_path}[/green]")
    except OSError as e:
        console.print(f"[red]导入失败: {e}[/red]")
        ctx.exit(1)

    # 导入后补全 .copier-answers.yml（如果仍缺少）
    svc = ProjectService(app_ctx.workspace_root)
    try:
        svc.retrofit_project_by_path(dest_path)
        console.print("[green].copier-answers.yml 已补全[/green]")
    except FileExistsError:
        pass  # 已有 .copier-answers.yml，正常
    except Exception as e:
        console.print(f"[yellow]补全元数据失败: {e}[/yellow]")

    project_id = ProjectService._extract_id_from_dirname(dest_path)
    if business_line is not None:
        inferred = project_id.split("-", 1)[0] if "-" in project_id else ""
        if inferred != business_line:
            console.print(
                f"[yellow]提示: 指定业务线 {business_line} 与项目编号前缀 {inferred} 不一致[/yellow]"
            )

    console.print(f"  项目编号: {project_id}")
    console.print(f"  导入路径: {dest_path}")

    # 同步到 DB 缓存（如果 DB 已存在）
    db_path = os.path.join(app_ctx.workspace_root, ".auto-pm", "index.db")
    if os.path.isfile(db_path):
        try:
            from auto_pm.db.connection import DatabaseManager

            db = DatabaseManager(app_ctx.workspace_root)
            db.init_schema()
            svc_with_db = ProjectService(app_ctx.workspace_root, db=db)
            svc_with_db.sync_to_cache(force_full=True)
            console.print("[green]DB 缓存已同步[/green]")
        except Exception as e:
            console.print(f"[yellow]DB 缓存同步失败（不影响导入）: {e}[/yellow]")


@project_group.group(name="hooks")
def hooks_group() -> None:
    """管理项目的 Git Pre-commit 提交门禁与自愈钩子"""
    pass


@hooks_group.command(name="install")
@click.argument("project_id")
@click.pass_context
def cmd_hooks_install(ctx: click.Context, project_id: str) -> None:
    """为已有项目安装 Git Pre-commit 提交门禁与自愈钩子"""
    app_ctx: AppContext = ctx.obj
    svc = ProjectService(app_ctx.workspace_root)
    proj = svc.get_project(project_id)

    if proj is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)

    result = svc.install_git_hooks(proj.path)
    if result["success"]:
        console.print(f"[green]{result['message']}[/green]")
    else:
        console.print(f"[red]安装失败: {result['message']}[/red]")
        ctx.exit(1)


@hooks_group.command(name="uninstall")
@click.argument("project_id")
@click.pass_context
def cmd_hooks_uninstall(ctx: click.Context, project_id: str) -> None:
    """为已有项目卸载 Git Pre-commit 提交门禁钩子"""
    app_ctx: AppContext = ctx.obj
    svc = ProjectService(app_ctx.workspace_root)
    proj = svc.get_project(project_id)

    if proj is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)

    result = svc.uninstall_git_hooks(proj.path)
    if result["success"]:
        console.print(f"[green]{result['message']}[/green]")
    else:
        console.print(f"[red]卸载失败: {result['message']}[/red]")
        ctx.exit(1)


@hooks_group.command(name="status")
@click.argument("project_id")
@click.pass_context
def cmd_hooks_status(ctx: click.Context, project_id: str) -> None:
    """查看项目 Git Pre-commit 提交门禁的安装状态"""
    app_ctx: AppContext = ctx.obj
    svc = ProjectService(app_ctx.workspace_root)
    proj = svc.get_project(project_id)

    if proj is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)

    installed = svc.is_git_hooks_installed(proj.path)
    if installed:
        console.print("[green]🟢 已激活 (auto-pm Pre-commit 提交门禁已装配)[/green]")
    else:
        console.print("[yellow]🟡 未激活 (未装配 Git 提交门禁)[/yellow]")
