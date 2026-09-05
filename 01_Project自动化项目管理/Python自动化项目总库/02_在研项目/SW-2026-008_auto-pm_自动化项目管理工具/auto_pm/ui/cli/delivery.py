"""交付物管理 CLI 命令组

提供交付物构建、打包、归档管理和状态查询功能。
替代旧版 scripts/build_delivery.py，集成到 auto-pm CLI。

Commands:
    build       # 构建交付物（编译 + 归档旧版 + 复制新版）
    package     # 打包 ZIP（归档旧 ZIP + 创建新 ZIP + 验证）
    archive     # 归档管理
    ├── list    # 列出归档版本
    └── clean   # 清理旧归档（保留最近 N 个）
    status      # 查看当前交付物状态
"""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from auto_pm.app_context import AppContext
from auto_pm.delivery.archive_manager import ArchiveManager
from auto_pm.delivery.constants import DEFAULT_ARCHIVE_KEEP, DEFAULT_PRODUCT_NAME
from auto_pm.delivery.delivery_service import DeliveryService

console = Console()


# ════════════════════════════════════════════════════════════
#  delivery 主命令组
# ════════════════════════════════════════════════════════════


@click.group(name="delivery")
@click.pass_context
def delivery_group(ctx: click.Context) -> None:
    """交付物管理 - 构建/打包/归档/状态查询"""


# ════════════════════════════════════════════════════════════
#  delivery build — 构建交付物
# ════════════════════════════════════════════════════════════


@delivery_group.command(name="build")
@click.option("--version", required=True, help="目标版本号（如 V1.0.1）")
@click.option(
    "--skip-pyinstaller", is_flag=True, default=True, help="跳过 PyInstaller 编译（默认跳过）"
)
@click.option("--auto-package", is_flag=True, default=False, help="构建后自动打包 ZIP")
@click.option("--dist-dir", default=None, help="PyInstaller 输出目录（默认 dist/{product_name}）")
@click.option("--product-name", default=DEFAULT_PRODUCT_NAME, help="产品名称")
@click.option("--summary", default="", help="变更摘要")
@click.option("--project-root", "-p", default=None, help="项目根目录（默认自动检测）")
@click.pass_context
def cmd_build(
    ctx: click.Context,
    version: str,
    skip_pyinstaller: bool,
    auto_package: bool,
    dist_dir: str | None,
    product_name: str,
    summary: str,
    project_root: str | None,
) -> None:
    """构建交付物。

    流程:
      1. 归档旧版交付物 → 06_交付物/archive/
      2. 复制新 exe + _internal → 06_交付物/01_可执行文件/
      3. 复制发布文档 → 06_交付物/02_发布说明/
      4. 执行 D-checks 校验
      5. [--auto-package] 自动打包 ZIP

    示例:
      auto-pm delivery build --version V1.0.1 --skip-pyinstaller
      auto-pm delivery build --version V1.0.1 --auto-package
    """
    app_ctx: AppContext = ctx.obj

    if project_root:
        root = project_root
    else:
        root = app_ctx.workspace_root

    svc = DeliveryService(root)

    console.print(f"[cyan]▶ 构建交付物: {version}[/cyan]")
    console.print(f"[dim]  项目根目录: {root}[/dim]")

    result = svc.build(
        version=version,
        skip_pyinstaller=skip_pyinstaller,
        auto_package=auto_package,
        dist_dir=dist_dir,
        product_name=product_name,
        summary=summary,
    )

    if not result["success"]:
        console.print(f"[red]✗ 构建失败: {result['message']}[/red]")
        ctx.exit(1)

    console.print(f"[green]✓ 构建成功: {version}[/green]")

    if result.get("archive_path"):
        console.print(f"[dim]  旧版已归档: {result['archive_path']}[/dim]")

    if result.get("package_result"):
        pkg = result["package_result"]
        if pkg.get("success"):
            console.print(f"[green]✓ 自动打包完成: {pkg.get('zip_path', '')}[/green]")
            if pkg.get("size_mb"):
                console.print(
                    f"[dim]  大小: {pkg['size_mb']} MB, 文件数: {pkg.get('file_count', 0)}[/dim]"
                )
        else:
            console.print(f"[red]✗ 自动打包失败: {pkg.get('message', '')}[/red]")
            ctx.exit(1)


# ════════════════════════════════════════════════════════════
#  delivery package — 打包 ZIP
# ════════════════════════════════════════════════════════════


@delivery_group.command(name="package")
@click.option("--version", required=True, help="版本号")
@click.option("--product-name", default=DEFAULT_PRODUCT_NAME, help="产品名称")
@click.option("--verify-only", is_flag=True, default=False, help="仅验证已有 ZIP")
@click.option("--summary", default="", help="变更摘要")
@click.option("--project-root", "-p", default=None, help="项目根目录（默认自动检测）")
@click.pass_context
def cmd_package(
    ctx: click.Context,
    version: str,
    product_name: str,
    verify_only: bool,
    summary: str,
    project_root: str | None,
) -> None:
    """打包交付物为 ZIP。

    流程:
      1. 归档旧 ZIP → 06_交付物/archive/
      2. 从 06_交付物/ 创建新 ZIP
      3. 执行 CHK-checks 验证

    示例:
      auto-pm delivery package --version V1.0.1
      auto-pm delivery package --version V1.0.1 --verify-only
    """
    app_ctx: AppContext = ctx.obj

    if project_root:
        root = project_root
    else:
        root = app_ctx.workspace_root

    svc = DeliveryService(root)

    console.print(f"[cyan]▶ 打包交付物: {version}[/cyan]")

    result = svc.package(
        version=version,
        product_name=product_name,
        verify_only=verify_only,
        summary=summary,
    )

    if not result["success"]:
        console.print(f"[red]✗ 打包失败: {result.get('message', '')}[/red]")
        if result.get("report"):
            console.print(result["report"])
        ctx.exit(1)

    console.print(f"[green]✓ 打包完成: {result.get('zip_path', '')}[/green]")
    if result.get("size_mb"):
        console.print(
            f"[dim]  大小: {result['size_mb']} MB, 文件数: {result.get('file_count', 0)}[/dim]"
        )

    if result.get("report"):
        console.print(result["report"])


# ════════════════════════════════════════════════════════════
#  delivery archive 子命令组
# ════════════════════════════════════════════════════════════


@delivery_group.group(name="archive")
@click.pass_context
def archive_group(ctx: click.Context) -> None:
    """归档管理 - 列出/清理归档版本"""


@archive_group.command(name="list")
@click.option(
    "--type",
    "archive_type",
    type=click.Choice(["delivery", "package"]),
    default="delivery",
    help="归档类型",
)
@click.option("--project-root", "-p", default=None, help="项目根目录（默认自动检测）")
@click.pass_context
def cmd_archive_list(
    ctx: click.Context,
    archive_type: str,
    project_root: str | None,
) -> None:
    """列出归档版本及说明。

    示例:
      auto-pm delivery archive list
      auto-pm delivery archive list --type package
    """
    app_ctx: AppContext = ctx.obj

    if project_root:
        root = project_root
    else:
        root = app_ctx.workspace_root

    am = ArchiveManager(root)
    archives = am.list_archives(archive_type)

    if not archives:
        console.print("[yellow]无归档记录[/yellow]")
        return

    type_label = "交付物" if archive_type == "delivery" else "交付物打包"
    table = Table(title=f"归档 {type_label} ({len(archives)} 条)")
    table.add_column("版本", style="cyan", no_wrap=True)
    table.add_column("日期", style="white", no_wrap=True)
    table.add_column("大小", style="green", no_wrap=True)
    table.add_column("替代版本", style="yellow", no_wrap=True)
    table.add_column("摘要", style="dim")

    for a in archives:
        table.add_row(
            a.get("version", "?"),
            a.get("date", "?"),
            f"{a.get('size_mb', 0)} MB",
            a.get("replaced_by", "—"),
            a.get("summary", "—"),
        )

    console.print(table)


@archive_group.command(name="clean")
@click.option(
    "--type",
    "archive_type",
    type=click.Choice(["delivery", "package"]),
    default="delivery",
    help="归档类型",
)
@click.option(
    "--keep",
    type=int,
    default=DEFAULT_ARCHIVE_KEEP,
    help=f"保留最近 N 个（默认 {DEFAULT_ARCHIVE_KEEP}）",
)
@click.option("--dry-run", is_flag=True, default=False, help="预览模式，不实际删除")
@click.option("--project-root", "-p", default=None, help="项目根目录（默认自动检测）")
@click.pass_context
def cmd_archive_clean(
    ctx: click.Context,
    archive_type: str,
    keep: int,
    dry_run: bool,
    project_root: str | None,
) -> None:
    """清理旧归档，保留最近 N 个。

    示例:
      auto-pm delivery archive clean --keep 3 --dry-run
      auto-pm delivery archive clean --type package --keep 5
    """
    app_ctx: AppContext = ctx.obj

    if project_root:
        root = project_root
    else:
        root = app_ctx.workspace_root

    am = ArchiveManager(root)
    removed = am.clean_archives(archive_type=archive_type, keep=keep, dry_run=dry_run)

    if dry_run:
        console.print(f"[cyan]▶ 预览清理（--dry-run），将移除 {len(removed)} 个归档:[/cyan]")
    else:
        console.print(f"[cyan]▶ 已清理 {len(removed)} 个归档:[/cyan]")

    for r in removed:
        console.print(f"  [dim]{r.name}[/dim]")

    if not removed:
        console.print("[yellow]无需清理[/yellow]")


# ════════════════════════════════════════════════════════════
#  delivery status — 查看状态
# ════════════════════════════════════════════════════════════


@delivery_group.command(name="status")
@click.option("--project-root", "-p", default=None, help="项目根目录（默认自动检测）")
@click.pass_context
def cmd_status(
    ctx: click.Context,
    project_root: str | None,
) -> None:
    """查看当前交付物状态。

    示例:
      auto-pm delivery status
    """
    app_ctx: AppContext = ctx.obj

    if project_root:
        root = project_root
    else:
        root = app_ctx.workspace_root

    svc = DeliveryService(root)
    status = svc.status()

    console.print("[bold cyan]═══ 交付物状态 ═══[/bold cyan]")

    # 交付物信息
    delivery = status.get("delivery")
    if delivery:
        console.print("\n[bold]06_交付物/[/bold]")
        console.print(f"  总文件数: {delivery.get('total_files', 0)}")
        exe_files = delivery.get("exe_files", [])
        if exe_files:
            console.print(f"  可执行文件: {', '.join(exe_files)}")
        console.print(f"  归档数: {delivery.get('archive_count', 0)}")
    else:
        console.print("\n[dim]06_交付物/ 不存在[/dim]")

    # 打包信息（CHG-SCPT-2026-145: 合并后 ZIP 与交付物同在 06_交付物/ 根目录）
    package = status.get("package")
    if package:
        console.print("\n[bold]06_交付物/ ZIP 打包[/bold]")
        console.print(f"  当前 ZIP: {package.get('name', '—')}")
        console.print(f"  大小: {package.get('size_mb', 0)} MB")
        console.print(f"  归档数: {status.get('package_archive_count', 0)}")
    else:
        console.print("\n[dim]06_交付物/ 无 ZIP[/dim]")

    console.print()
