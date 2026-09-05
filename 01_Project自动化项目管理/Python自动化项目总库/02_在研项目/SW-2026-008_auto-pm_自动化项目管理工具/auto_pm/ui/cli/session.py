"""PLC-HMI 概念映射：CLI 命令行入口（会话命令组（PM_SESSION 查看/编辑））

像 PLC 的调试终端/工程师站，通过命令行直接操作功能块。
不经过 HMI 画面，直接调用 FB 或 SFB。

--- 原始注释 ---

PM_SESSION 管理命令组 - CHG-088 Stage 2

提供 PM_SESSION 文件的章节级解析、归档和健康检查能力。

子命令：
- check：检查 PM_SESSION 文件健康状态（规模门禁 + 章节完整性）
- archive：归档指定章节的早期内容到归档文件
- view：从 PM_SESSION 生成只读视图

三层真源架构（CHG-087 Stage 1 建立，CHG-088 Stage 2 自动化）：
1. Active 主文件：保留最新迭代状态
2. Historical 归档：archive_V*.md 完整保留历史
3. Event 实体：CHG-*.md 变更单
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from auto_pm.core.pm_session_service import (
    ARCHIVE_DIR_NAME,
    ARCHIVE_DIR_PARENT,
    MAX_FILE_LINES,
    MAX_FILE_SIZE_KB,
    PmSessionArchiveService,
    PmSessionCheckService,
    PmSessionParser,
    generate_view,
)

console = Console()


def _supports_unicode_output() -> bool:
    """检测终端是否支持 Unicode 输出（emoji/中文符号）"""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "✅❌⚠".encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def _resolve_workspace(workspace: str | None, ctx: click.Context | None = None) -> Path:
    """解析工作空间路径并校验存在性。

    支持从 ctx.obj (AppContext) 回退全局 -w，统一 -w 语义。
    """
    if workspace is None and ctx is not None:
        app_ctx = ctx.obj
        if app_ctx is not None and hasattr(app_ctx, "workspace_root"):
            workspace = app_ctx.workspace_root
    if workspace is None:
        console.print(
            "[red]错误: 必须通过 -w 指定工作空间根目录（全局 auto-pm -w 或子命令 -w）[/red]"
        )
        raise SystemExit(1)
    ws = Path(workspace).resolve()
    if not ws.exists():
        console.print(f"[red]错误: 工作空间路径不存在: {workspace}[/red]")
        raise SystemExit(1)
    return ws


def _find_pm_session_files(root: Path) -> list[Path]:
    """递归查找所有 PM_SESSION 文件（排除 backup 和 archive）"""
    candidates = list(root.rglob("PM_SESSION_*.md"))
    # 排除备份文件和归档文件
    candidates = [c for c in candidates if ".bak" not in c.name and "archive" not in c.name.lower()]
    return sorted(candidates)


def _find_pm_session_file(project_root: Path, project_id: str | None = None) -> Path:
    """查找项目目录下的 PM_SESSION 文件"""
    if project_id:
        target = project_root / f"PM_SESSION_{project_id}.md"
        if target.exists():
            return target
    # 模糊查找
    candidates = list(project_root.glob("PM_SESSION_*.md"))
    # 排除备份文件
    candidates = [c for c in candidates if ".bak" not in c.name and "archive" not in c.name]
    if not candidates:
        raise FileNotFoundError(f"在 {project_root} 下未找到 PM_SESSION_*.md 文件")
    if len(candidates) > 1:
        raise ValueError(
            f"在 {project_root} 下找到多个 PM_SESSION 文件: {candidates}，请通过 --project-id 指定"
        )
    return candidates[0]


@click.group(name="pm-session")
def pm_session_group() -> None:
    """PM_SESSION 管理 - 检查/归档/视图（CHG-088 Stage 2）"""


@pm_session_group.command(name="check")
@click.option("--workspace", "-w", default=None, help="工作空间根目录（未指定时回退全局 -w）")
@click.option(
    "--project-root",
    type=click.Path(path_type=Path),
    default=None,
    help="项目根目录（未指定时使用 -w 作为项目根）",
)
@click.option("--project-id", default=None, help="项目编号（如 SW-2026-008）")
@click.option("--quiet", is_flag=True, help="只输出问题，健康时无输出")
@click.pass_context
def cmd_check(
    ctx: click.Context,
    workspace: str | None,
    project_root: Path | None,
    project_id: str | None,
    quiet: bool,
) -> None:
    """检查 PM_SESSION 文件健康状态

    检查项：
    1. 文件大小是否超过阈值（150KB / 300 行）
    2. 必须章节是否齐全（§0/§1/§2/§3/§4/§5/§6/§8/§9）
    3. 已归档章节是否回归（§7 应不存在）
    """
    ws = _resolve_workspace(workspace, ctx)
    root = project_root if project_root else ws

    # 当未指定 --project-root 时，递归扫描工作空间中的所有 PM_SESSION 文件
    if project_root is None:
        pm_files = _find_pm_session_files(ws)
        if not pm_files:
            console.print(f"[red]错误: 在 {ws} 及子目录中未找到 PM_SESSION_*.md 文件[/red]")
            raise SystemExit(2)
        # 检查所有文件
        svc = PmSessionCheckService()
        all_healthy = True
        for pm_file in pm_files:
            result = svc.check(pm_file)
            if quiet and result.is_healthy:
                continue
            if result.is_healthy:
                ok_icon = "OK" if not _supports_unicode_output() else "✅"
                console.print(
                    f"[green]{ok_icon} {pm_file.relative_to(ws)}: "
                    f"{result.file_size_kb}KB / {result.total_lines}行[/green]"
                )
            else:
                all_healthy = False
                fail_icon = "FAIL" if not _supports_unicode_output() else "❌"
                warn_icon = "WARN" if not _supports_unicode_output() else "⚠"
                console.print(f"[red]{fail_icon} {pm_file.relative_to(ws)}[/red]")
                for w in result.warnings:
                    console.print(f"  [yellow]{warn_icon} {w}[/yellow]")
        if not all_healthy:
            raise SystemExit(1)
        return

    # 指定了 --project-root 时，单文件检查
    try:
        pm_file = _find_pm_session_file(root, project_id)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]错误: {e}[/red]")
        raise SystemExit(2) from e

    svc = PmSessionCheckService()
    result = svc.check(pm_file)

    if quiet and result.is_healthy:
        return

    if result.is_healthy:
        ok_icon = "✅" if _supports_unicode_output() else "[OK]"
        console.print(
            f"[green]{ok_icon} PM_SESSION 健康: {pm_file.name}[/green]\n"
            f"  大小: {result.file_size_kb}KB / {MAX_FILE_SIZE_KB}KB\n"
            f"  行数: {result.total_lines} / {MAX_FILE_LINES}\n"
            f"  章节数: {len(result.missing_required)} 缺失, "
            f"{len(result.deprecated_present)} 回归"
        )
    else:
        fail_icon = "❌" if _supports_unicode_output() else "[FAIL]"
        warn_icon = "⚠" if _supports_unicode_output() else "[WARN]"
        console.print(f"[red]{fail_icon} PM_SESSION 不健康: {pm_file.name}[/red]")
        for w in result.warnings:
            console.print(f"  [yellow]{warn_icon} {w}[/yellow]")
        console.print(
            f"  大小: {result.file_size_kb}KB / {MAX_FILE_SIZE_KB}KB\n"
            f"  行数: {result.total_lines} / {MAX_FILE_LINES}"
        )
        raise SystemExit(1)


@pm_session_group.command(name="archive")
@click.option("--workspace", "-w", default=None, help="工作空间根目录（未指定时回退全局 -w）")
@click.option(
    "--project-root",
    type=click.Path(path_type=Path),
    default=None,
    help="项目根目录（未指定时使用 -w 作为项目根）",
)
@click.option("--project-id", default=None, help="项目编号（如 SW-2026-008）")
@click.option(
    "--section",
    "section_number",
    default=None,
    help="要归档的章节号（如 6/7/8），--auto 模式下忽略",
)
@click.option(
    "--keep-recent",
    type=int,
    default=0,
    help="主文件保留该章节最近 N 行内容（0=整章归档）；§8 中表示保留最新 N 条 skill_handoff 条目",
)
@click.option(
    "--archive-file",
    type=click.Path(path_type=Path),
    default=None,
    help="归档文件路径（未指定时自动生成）",
)
@click.option("--dry-run", is_flag=True, help="仅预览归档操作，不实际修改文件")
@click.option("--no-backup", is_flag=True, help="不创建主文件备份")
@click.option(
    "--auto",
    "auto_mode",
    is_flag=True,
    help="自动批量归档：扫描工作空间所有 PM_SESSION，对超 150 行的文件自动归档 §5/§6/§8",
)
@click.pass_context
def cmd_archive(
    ctx: click.Context,
    workspace: str | None,
    project_root: Path | None,
    project_id: str | None,
    section_number: str | None,
    keep_recent: int,
    archive_file: Path | None,
    dry_run: bool,
    no_backup: bool,
    auto_mode: bool,
) -> None:
    """归档指定章节的早期内容到归档文件

    示例：
        auto-pm pm-session archive -w . --section 7
        auto-pm pm-session archive -w . --section 6 --keep-recent 20
        auto-pm pm-session archive -w . --section 8 --keep-recent 8
        auto-pm pm-session archive -w . --auto --dry-run   # 预览批量归档
        auto-pm pm-session archive -w . --auto              # 执行批量归档

    §8 特殊处理（CHG-109）：--keep-recent N 表示保留最新 N 条 skill_handoff 条目，
    current_state* 和归档说明始终保留，其余旧 skill_handoff 条目归档。
    """
    ws = _resolve_workspace(workspace, ctx)

    if auto_mode:
        _cmd_archive_auto(ws, dry_run, not no_backup)
        return

    if section_number is None:
        console.print("[red]错误: 必须指定 --section 或使用 --auto 模式[/red]")
        raise SystemExit(2)

    root = project_root if project_root else ws
    try:
        pm_file = _find_pm_session_file(root, project_id)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]错误: {e}[/red]")
        raise SystemExit(2) from e

    # 自动生成归档文件路径
    if archive_file is None:
        archive_dir = root / ARCHIVE_DIR_PARENT / ARCHIVE_DIR_NAME
        # 从 PM_SESSION 文件名提取 project_id
        stem = pm_file.stem  # PM_SESSION_SW-2026-008
        pid = stem.replace("PM_SESSION_", "") if stem.startswith("PM_SESSION_") else "PROJECT"
        archive_file = archive_dir / f"PM_SESSION_{pid}_archive_auto.md"

    parser = PmSessionParser()
    parse_result = parser.parse_file(pm_file)
    section = parse_result.get_section(section_number)
    if section is None:
        console.print(f"[red]错误: 章节 §{section_number} 不存在于 {pm_file.name}[/red]")
        raise SystemExit(2)

    section_lines = section.end_line - section.start_line
    archive_lines = max(0, section_lines - keep_recent)
    is_section_8 = section_number == "8"

    console.print("[cyan]PM_SESSION 归档预览[/cyan]")
    console.print(f"  主文件: {pm_file}")
    console.print(f"  归档文件: {archive_file}")
    console.print(f"  章节: §{section_number} {section.title}")
    console.print(f"  章节总行数: {section_lines}")
    if is_section_8:
        console.print("  归档模式: 条目级（§8 倒序结构，CHG-109）")
        console.print(f"  保留最新: {keep_recent} 条 skill_handoff")
    else:
        console.print(f"  归档行数: {archive_lines}")
        console.print(f"  保留最近: {keep_recent} 行")
    console.print(f"  创建备份: {'否' if no_backup else '是'}")

    if dry_run:
        console.print("[yellow]DRY-RUN 模式，未实际修改文件[/yellow]")
        return

    svc = PmSessionArchiveService()
    if is_section_8:
        result = svc.archive_section_8(
            main_file=pm_file,
            archive_file=archive_file,
            keep_entries=keep_recent,
            create_backup=not no_backup,
        )
    else:
        result = svc.archive_section(
            main_file=pm_file,
            archive_file=archive_file,
            section_number=section_number,
            keep_recent=keep_recent,
            create_backup=not no_backup,
        )

    ok_icon = "✅" if _supports_unicode_output() else "[OK]"
    console.print(f"\n[green]{ok_icon} 归档完成[/green]")
    console.print(f"  归档行数: {result.archived_line_count}")
    console.print(
        f"  主文件行数: {result.main_file_lines_before} -> {result.main_file_lines_after}"
    )
    if result.backup_file:
        console.print(f"  备份文件: {result.backup_file}")


def _cmd_archive_auto(
    ws: Path,
    dry_run: bool,
    create_backup: bool,
) -> None:
    """--auto 批量归档：扫描所有 PM_SESSION，对超 150 行的自动归档 §5/§6/§8

    CHG-SCPT-2026-153: P1-3，基于 DJ-2026-005 实战中 PM_SESSION 膨胀问题，
    提供 --auto 批量归档模式，避免逐个手动归档。
    """
    pm_files = _find_pm_session_files(ws)
    if not pm_files:
        console.print(f"[yellow]在 {ws} 及子目录中未找到 PM_SESSION_*.md 文件[/yellow]")
        return

    console.print(f"[cyan]--auto 批量归档: 扫描到 {len(pm_files)} 个 PM_SESSION 文件[/cyan]\n")

    auto_sections = ["5", "6", "8"]  # 自动归档的章节
    auto_threshold = 150  # 行数阈值
    svc = PmSessionArchiveService()
    total_archived = 0
    total_files = 0

    for pm_file in pm_files:
        # 统计行数
        line_count = 0
        try:
            with open(pm_file, encoding="utf-8", errors="ignore") as f:
                for _ in f:
                    line_count += 1
        except OSError:
            continue

        if line_count <= auto_threshold:
            rel_path = pm_file.relative_to(ws)
            console.print(f"  [dim]{rel_path}: {line_count} 行，无需归档[/dim]")
            continue

        total_files += 1
        rel_path = pm_file.relative_to(ws)
        console.print(f"  [yellow]{rel_path}: {line_count} 行 -> 需归档[/yellow]")

        # 自动生成归档文件路径
        stem = pm_file.stem
        pid = stem.replace("PM_SESSION_", "") if stem.startswith("PM_SESSION_") else "PROJECT"
        archive_dir = pm_file.parent / ARCHIVE_DIR_PARENT / ARCHIVE_DIR_NAME
        archive_file = archive_dir / f"PM_SESSION_{pid}_archive_auto.md"

        file_archived = 0
        for sec in auto_sections:
            parser = PmSessionParser()
            parse_result = parser.parse_file(pm_file)
            section = parse_result.get_section(sec)
            if section is None:
                continue

            section_lines = section.end_line - section.start_line
            if section_lines <= 5:  # 章节太短，不归档
                continue

            # §8 保留最新 1 条 skill_handoff，§5/§6 保留最近 10 行
            keep = 1 if sec == "8" else 10

            if dry_run:
                console.print(
                    f"    [dim]§{sec}: {section_lines} 行 -> 保留 {keep} 行（dry-run）[/dim]"
                )
                file_archived += section_lines - keep
                continue

            try:
                if sec == "8":
                    result = svc.archive_section_8(
                        main_file=pm_file,
                        archive_file=archive_file,
                        keep_entries=keep,
                        create_backup=create_backup,
                    )
                else:
                    result = svc.archive_section(
                        main_file=pm_file,
                        archive_file=archive_file,
                        section_number=sec,
                        keep_recent=keep,
                        create_backup=create_backup,
                    )
                console.print(f"    [green]§{sec}: {result.archived_line_count} 行已归档[/green]")
                file_archived += result.archived_line_count
            except Exception as e:
                console.print(f"    [red]§{sec}: 归档失败 - {e}[/red]")

        total_archived += file_archived

    if dry_run:
        console.print(
            f"\n[yellow]DRY-RUN 完成: {total_files} 个文件需归档，"
            f"预计归档 {total_archived} 行[/yellow]"
        )
    else:
        ok_icon = "✅" if _supports_unicode_output() else "[OK]"
        console.print(
            f"\n[green]{ok_icon} 批量归档完成: {total_files} 个文件，"
            f"共归档 {total_archived} 行[/green]"
        )


@pm_session_group.command(name="view")
@click.option("--workspace", "-w", default=None, help="工作空间根目录（未指定时回退全局 -w）")
@click.option(
    "--project-root",
    type=click.Path(path_type=Path),
    default=None,
    help="项目根目录（未指定时使用 -w 作为项目根）",
)
@click.option("--project-id", default=None, help="项目编号（如 SW-2026-008）")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="输出文件路径（未指定时输出到 stdout）",
)
@click.pass_context
def cmd_view(
    ctx: click.Context,
    workspace: str | None,
    project_root: Path | None,
    project_id: str | None,
    output: Path | None,
) -> None:
    """从 PM_SESSION 生成只读视图

    提取 §2 Current Focus + §3 Status Summary + §9 Next Actions，
    生成简洁的只读 markdown 视图。
    """
    ws = _resolve_workspace(workspace, ctx)
    root = project_root if project_root else ws
    try:
        pm_file = _find_pm_session_file(root, project_id)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]错误: {e}[/red]")
        raise SystemExit(2) from e

    parser = PmSessionParser()
    parse_result = parser.parse_file(pm_file)
    view_content = generate_view(parse_result)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(view_content, encoding="utf-8")
        ok_icon = "✅" if _supports_unicode_output() else "[OK]"
        console.print(f"[green]{ok_icon} 视图已生成: {output}[/green]")
    else:
        console.print(view_content)
