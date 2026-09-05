"""PLC-HMI 概念映射：CLI 命令行入口（规范命令组（check/index/frontmatter/report））

像 PLC 的调试终端/工程师站，通过命令行直接操作功能块。
不经过 HMI 画面，直接调用 FB 或 SFB。

--- 原始注释 ---

规范管理命令组 - 整合自 specmgr 工具（SW-2026-006）

提供规范检查、索引生成、frontmatter 同步、健康报告能力。

每个子命令的 --workspace/-w 参数为可选，未指定时回退到全局 auto-pm -w
（通过 ctx.obj/AppContext 继承），统一 -w 语义。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console

from auto_pm.spec.core.checker_base import CheckResult, Severity
from auto_pm.spec.core.config import CHECK_SCOPES, WorkspaceConfig, load_config
from auto_pm.spec.services.check_svc import CheckService
from auto_pm.spec.services.fix_svc import FixResult, can_auto_fix
from auto_pm.spec.services.frontmatter_svc import FrontmatterService
from auto_pm.spec.services.index_svc import IndexService
from auto_pm.spec.services.report_svc import ReportService

console = Console()

_SEVERITY_ICONS = {Severity.ERROR: "🔴", Severity.WARNING: "🟡", Severity.INFO: "🟢"}
_SEVERITY_COLORS = {Severity.ERROR: "red", Severity.WARNING: "yellow", Severity.INFO: "green"}
_SEVERITY_LABELS = {Severity.ERROR: "错误", Severity.WARNING: "警告", Severity.INFO: "提示"}
_ASCII_SEVERITY_ICONS = {
    Severity.ERROR: "[ERR]",
    Severity.WARNING: "[WARN]",
    Severity.INFO: "[INFO]",
}


def _iter_registry_specs(registry: dict[str, object]) -> list[tuple[str, dict[str, object]]]:
    specs = registry.get("specs", {})
    if not isinstance(specs, dict):
        return []
    return [
        (spec_id, spec)
        for spec_id, spec in specs.items()
        if isinstance(spec_id, str) and isinstance(spec, dict)
    ]


def _supports_unicode_output() -> bool:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "🟡✅⏭️🔧".encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def _is_non_spec_artifact(md_file: Path) -> bool:
    normalized_parts = {part.replace("\\", "/") for part in md_file.parts}
    return bool(
        {
            "04_变更管理",
            "01_变更单",
            "02_变更记录",
        }
        & normalized_parts
    )


def _should_skip_schema_mismatch(spec: dict[str, object]) -> bool:
    lifecycle = str(spec.get("lifecycle", "")).lower()
    canonical_path = str(spec.get("canonical_path", "")).replace("\\", "/")
    return (
        lifecycle in {"deprecated", "archived", "history"} or "/_archive/" in f"/{canonical_path}"
    )


def _is_allowed_duplicate_dir(prefix: str, dirs: list[str]) -> bool:
    return prefix == "01" and set(dirs).issubset({"01_启动", "01_需求与设计"})


def _resolve_workspace(workspace: str | None, ctx: click.Context | None = None) -> Path:
    """解析工作空间路径并校验存在性。

    支持从 ctx.obj (AppContext) 回退全局 -w，统一 -w 语义：
    spec 子命令 -w 优先 > 全局 -w > 报错。
    """
    if workspace is None and ctx is not None:
        # spec 子命令未指定 -w 时，回退到全局 -w（通过 AppContext）
        app_ctx = ctx.obj
        if app_ctx is not None and hasattr(app_ctx, "workspace_root"):
            workspace = app_ctx.workspace_root
    if workspace is None:
        console.print(
            "[red]错误: 必须通过 -w 指定工作空间根目录（全局 auto-pm -w 或 spec 子命令 -w）[/red]"
        )
        raise SystemExit(1)
    ws = Path(workspace).resolve()
    if not ws.exists():
        console.print(f"[red]错误: 工作空间路径不存在: {workspace}[/red]")
        raise SystemExit(1)
    return ws


def _load_ws_config(config_path: Path | None, workspace: Path) -> WorkspaceConfig | None:
    """加载工作空间配置文件(YAML)。返回 None 表示用默认配置。"""
    if config_path is None:
        return None
    if not config_path.exists():
        console.print(f"[red]错误: 配置文件不存在: {config_path}[/red]")
        raise SystemExit(1)
    cfg = load_config(config_path)
    # 用 -w 指定的 workspace 覆盖 config 中的 workspace(-w 优先)
    cfg.workspace = workspace
    return cfg


@click.group(name="spec")
def spec_group() -> None:
    """规范管理 - 检查/索引/frontmatter/报告（整合自 specmgr）"""


@spec_group.command(name="check")
@click.option("--workspace", "-w", default=None, help="工作空间根目录（未指定时回退全局 -w）")
@click.option("--fix", "auto_fix", is_flag=True, help="自动修复可修复的问题（SHC-002/007）")
@click.option("--dry-run", is_flag=True, help="仅预览修复操作，不实际修改文件")
@click.option(
    "--format", "fmt", type=click.Choice(["table", "json"]), default="table", help="输出格式"
)
@click.option("--check-id", "-c", multiple=True, help="只运行指定检查项（如 -c SHC-001）")
@click.option(
    "--severity",
    type=click.Choice(["error", "warning", "info"]),
    default="info",
    help="最低严重级别",
)
@click.option("--scope", type=click.Choice(CHECK_SCOPES), default="workspace", help="检查范围")
@click.option(
    "--project-root",
    type=click.Path(path_type=Path),
    help="项目根目录，scope=project 时必填",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="工作空间配置文件路径(YAML，含 spec_dirs/registry_path/output_paths)",
)
@click.option("--quiet", is_flag=True, help="只输出 ERROR 级别结果 + 退出码")
@click.option("--verbose", "-v", is_flag=True, help="显示详细 diff 信息（版本差异/文件路径等）")
@click.pass_context
def cmd_check(
    ctx: click.Context,
    workspace: str | None,
    auto_fix: bool,
    dry_run: bool,
    fmt: str,
    check_id: tuple[str, ...],
    severity: str,
    scope: str,
    project_root: Path | None,
    config_path: Path | None,
    quiet: bool,
    verbose: bool,
) -> None:
    """运行规范健康检查（SHC-001~010）"""
    ws = _resolve_workspace(workspace, ctx)
    ws_config = _load_ws_config(config_path, ws)

    resolved_project_root: Path | None = None
    if scope == "project":
        if project_root is None:
            console.print("[red]错误: scope=project 时必须通过 --project-root 指定项目根目录[/red]")
            raise SystemExit(1)
        resolved_project_root = project_root.resolve()
        if not resolved_project_root.exists():
            console.print(f"[red]错误: 项目根目录不存在: {project_root}[/red]")
            raise SystemExit(1)
        try:
            resolved_project_root.relative_to(ws)
        except ValueError:
            console.print("[red]错误: 项目根目录必须位于工作空间内部[/red]")
            raise SystemExit(1)

    svc = CheckService(ws, config=ws_config)
    output = svc.run(
        check_ids=list(check_id) or None,
        min_severity=Severity[severity.upper()],
        auto_fix=auto_fix,
        dry_run=dry_run,
        scope=scope,
        project_root=resolved_project_root,
    )

    if quiet:
        # quiet 模式:只输出 ERROR 级别结果
        error_results = [r for r in output.results if r.severity == Severity.ERROR]
        if fmt == "json":
            _output_check_json(error_results, None)
        else:
            for r in error_results:
                console.print(f"[red]ERROR [{r.check_id}]: {r.message}[/red]")
    elif fmt == "json":
        _output_check_json(output.results, output.fix_results, verbose=verbose)
    else:
        _output_check_table(output.results, output.fix_results, auto_fix, verbose=verbose)

    raise SystemExit(output.exit_code)


def _output_check_json(
    results: list[CheckResult],
    fix_results: list[FixResult] | None = None,
    verbose: bool = False,
) -> None:
    data: list[dict[str, object]] = [
        {
            "check_id": r.check_id,
            "severity": r.severity.name,
            "message": r.message,
            "details": r.details,
            "fix_suggestion": r.fix_suggestion,
            "auto_fixable": can_auto_fix(r),
        }
        for r in results
    ]
    out: dict[str, object] = {"check_results": data}
    if verbose:
        out["verbose"] = True
        out["summary"] = {
            "total": len(results),
            "error": sum(1 for r in results if r.severity == Severity.ERROR),
            "warning": sum(1 for r in results if r.severity == Severity.WARNING),
            "info": sum(1 for r in results if r.severity == Severity.INFO),
        }
    if fix_results is not None:
        out["fix_results"] = [
            {"check_id": fr.check_id, "applied": fr.applied, "message": fr.message}
            for fr in fix_results
        ]
    click.echo(json.dumps(out, ensure_ascii=False, indent=2))


def _output_check_table(
    results: list[CheckResult],
    fix_results: list[FixResult] | None = None,
    show_fix: bool = False,
    verbose: bool = False,
) -> None:
    unicode_output = _supports_unicode_output()
    severity_icons = _SEVERITY_ICONS if unicode_output else _ASCII_SEVERITY_ICONS
    summary_icons = ("🔴", "🟡", "🟢") if unicode_output else ("E", "W", "I")
    status_icons = ("✅", "⏭️") if unicode_output else ("OK", "SKIP")

    if not results:
        console.print(
            "[green]✅ 所有检查通过！[/green]" if unicode_output else "[green]所有检查通过[/green]"
        )
        return

    # verbose 模式：按 check_id 分组显示
    if verbose:
        from collections import defaultdict

        grouped: dict[str, list[CheckResult]] = defaultdict(list)
        for r in results:
            grouped[r.check_id].append(r)

        for check_id, items in sorted(grouped.items()):
            console.print(f"\n[bold cyan]{'─' * 60}[/bold cyan]")
            console.print(f"[bold cyan]  [{check_id}] 共 {len(items)} 项[/bold cyan]")
            for i, r in enumerate(items, 1):
                icon = severity_icons[r.severity]
                color = _SEVERITY_COLORS[r.severity]
                console.print(f"  [{color}]{icon} #{i} {r.message}[/{color}]")
                if r.details:
                    for detail_line in r.details.split("\n"):
                        console.print(f"     [dim]│ {detail_line}[/dim]")
                if r.fix_suggestion:
                    console.print(f"     [cyan]└ 建议: {r.fix_suggestion}[/cyan]")
        console.print(f"\n[bold cyan]{'─' * 60}[/bold cyan]")
    else:
        for r in results:
            icon = severity_icons[r.severity]
            label = _SEVERITY_LABELS[r.severity]
            color = _SEVERITY_COLORS[r.severity]
            fixable_tag = " [可自动修复]" if show_fix and can_auto_fix(r) else ""
            console.print(f"[{color}]  {icon} {label}: {r.message}{fixable_tag}[/{color}]")
            if r.details:
                console.print(f"[dim]    详情: {r.details}[/dim]")
            if r.fix_suggestion:
                console.print(f"[cyan]    建议: {r.fix_suggestion}[/cyan]")

    console.print("")
    console.print("-" * 60)

    error_count = sum(1 for r in results if r.severity == Severity.ERROR)
    warning_count = sum(1 for r in results if r.severity == Severity.WARNING)
    info_count = sum(1 for r in results if r.severity == Severity.INFO)

    console.print(
        f"  汇总: {summary_icons[0]} 错误 {error_count} | {summary_icons[1]} 警告 {warning_count} | "
        f"{summary_icons[2]} 提示 {info_count} | 共 {len(results)} 项"
    )

    if fix_results is not None:
        console.print("")
        fix_title = "  🔧 修复结果:" if unicode_output else "  修复结果:"
        console.print(f"[bright_cyan]{fix_title}[/bright_cyan]")
        applied_count = 0
        for fr in fix_results:
            status_icon = status_icons[0] if fr.applied else status_icons[1]
            console.print(f"    {status_icon} [{fr.check_id}] {fr.message}")
            if fr.applied:
                applied_count += 1
        console.print(
            f"  修复汇总: {status_icons[0]} 已修复 {applied_count} | "
            f"{status_icons[1]} 跳过 {len(fix_results) - applied_count}"
        )


@spec_group.command(name="index")
@click.option("--workspace", "-w", default=None, help="工作空间根目录（未指定时回退全局 -w）")
@click.option(
    "--domain",
    type=click.Choice(["pm", "plc", "python", "all"]),
    default="all",
    help="只生成指定域（默认 all）",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="工作空间配置文件路径(YAML，含 spec_dirs/registry_path/output_paths)",
)
@click.option("--quiet", is_flag=True, help="只输出错误信息，不输出成功生成结果")
@click.pass_context
def cmd_index(
    ctx: click.Context, workspace: str | None, domain: str, config_path: Path | None, quiet: bool
) -> None:
    """生成规范索引文件"""
    ws = _resolve_workspace(workspace, ctx)
    ws_config = _load_ws_config(config_path, ws)
    svc = IndexService(ws, config=ws_config)
    domains = None if domain == "all" else [domain]
    output = svc.run(domains=domains)

    if quiet:
        # quiet 模式:只输出错误
        for err in output.errors:
            console.print(f"[red]{err}[/red]")
        return

    unicode_output = _supports_unicode_output()
    ok_icon = "✅" if unicode_output else "[OK]"
    fail_icon = "❌" if unicode_output else "[FAIL]"

    for f in output.generated_files:
        console.print(f"[green]{ok_icon} 已生成: {f}[/green]")

    for err in output.errors:
        console.print(f"[red]{fail_icon} 生成失败: {err}[/red]")


@spec_group.command(name="frontmatter")
@click.option("--workspace", "-w", default=None, help="工作空间根目录（未指定时回退全局 -w）")
@click.option("--fix", is_flag=True, help="实际执行写入（默认仅预览）")
@click.option("--spec-id", default=None, help="只处理指定规范")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="工作空间配置文件路径(YAML，含 spec_dirs/registry_path/output_paths)",
)
@click.option("--quiet", is_flag=True, help="只输出错误信息，不输出扫描/预览结果")
@click.pass_context
def cmd_frontmatter(
    ctx: click.Context,
    workspace: str | None,
    fix: bool,
    spec_id: str | None,
    config_path: Path | None,
    quiet: bool,
) -> None:
    """检查/同步规范 frontmatter

    默认仅预览将添加的 frontmatter；使用 --fix 实际写入。
    """
    ws = _resolve_workspace(workspace, ctx)
    ws_config = _load_ws_config(config_path, ws)
    svc = FrontmatterService(ws, config=ws_config)
    items = svc.preview(spec_id=spec_id)

    if quiet:
        # quiet 模式:只输出 error 项
        for item in items:
            if item.status == "error":
                console.print(f"[red]ERROR: {item.spec_id} 处理失败[/red]")
        return

    if not items:
        console.print("[yellow]没有需要处理的规范文件[/yellow]")
        return

    unicode_output = _supports_unicode_output()
    warn_icon = "⚠️" if unicode_output else "[WARN]"
    fail_icon = "❌" if unicode_output else "[FAIL]"
    write_icon = "📝" if unicode_output else "[WRITE]"

    mode = "实际修改" if fix else "DRY-RUN（仅预览）"
    pending_count = sum(1 for i in items if i.status == "pending")
    console.print(f"扫描到 {len(items)} 个规范，其中 {pending_count} 个需要添加frontmatter")
    console.print(f"模式: {mode}")
    console.print("-" * 50)

    for item in items:
        if item.status == "skipped":
            if item.is_deprecated:
                continue
            if item.has_frontmatter:
                continue
            if not item.file_exists:
                console.print(f"[yellow]  {warn_icon} 文件不存在: {item.file_path}[/yellow]")
            continue

        if item.status == "error":
            console.print(f"[red]  {fail_icon} 处理失败: {item.spec_id}[/red]")
            continue

        if item.status == "pending":
            if not fix:
                console.print(f"[cyan]  [DRY-RUN] 将添加frontmatter到: {item.spec_id}[/cyan]")
                preview = item.new_frontmatter[:80]
                console.print(f"    {preview}...")
            else:
                console.print(f"[green]  {write_icon} 添加frontmatter到: {item.spec_id}[/green]")

    if fix and pending_count > 0:
        pending_items = [i for i in items if i.status == "pending"]
        result = svc.apply(pending_items)
        console.print("-" * 50)
        console.print(
            f"[green]完成！修改: {result.modified_count}, "
            f"跳过: {result.skipped_count}, "
            f"错误: {result.error_count}[/green]"
        )
    else:
        skipped = sum(1 for i in items if i.status == "skipped")
        errors = sum(1 for i in items if i.status == "error")
        console.print("-" * 50)
        console.print(
            f"[cyan]预览完成！待修改: {pending_count}, 跳过: {skipped}, 错误: {errors}[/cyan]"
        )


@spec_group.command(name="report")
@click.option("--workspace", "-w", default=None, help="工作空间根目录（未指定时回退全局 -w）")
@click.option("--output", "-o", default=None, help="输出文件路径")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    help="输出格式",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="工作空间配置文件路径(YAML，含 spec_dirs/registry_path/output_paths)",
)
@click.option("--quiet", is_flag=True, help="成功时不输出，仅失败时输出错误")
@click.pass_context
def cmd_report(
    ctx: click.Context,
    workspace: str | None,
    output: str | None,
    fmt: str,
    config_path: Path | None,
    quiet: bool,
) -> None:
    """生成规范元数据汇总报告"""
    ws = _resolve_workspace(workspace, ctx)
    ws_config = _load_ws_config(config_path, ws)
    svc = ReportService(ws, config=ws_config)
    output_path = Path(output) if output else None
    result = svc.generate(fmt=fmt, output_path=output_path)

    if quiet:
        # quiet 模式:成功时无输出
        return

    ok_icon = "✅" if _supports_unicode_output() else "[OK]"
    console.print(f"[green]{ok_icon} 报告已生成: {result.output_path}[/green]")


@spec_group.command(name="lint")
@click.option("--workspace", "-w", default=None, help="工作空间根目录（未指定时回退全局 -w）")
@click.option(
    "--rule",
    "-r",
    multiple=True,
    type=click.Choice(
        ["orphan_file", "path_drift", "schema_mismatch", "duplicate_dir", "stale_root", "all"]
    ),
    default=("all",),
    help="指定检查规则（默认 all）",
)
@click.option(
    "--format", "fmt", type=click.Choice(["table", "json"]), default="table", help="输出格式"
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="工作空间配置文件路径",
)
@click.pass_context
def cmd_lint(
    ctx: click.Context,
    workspace: str | None,
    rule: tuple[str, ...],
    fmt: str,
    config_path: Path | None,
) -> None:
    """规范注册表专项 lint 检查（5条注册表级规则）

    \b
    规则说明:
      orphan_file    - 物理存在但未在 spec_registry.json 注册的 .md 文件
      path_drift     - canonical_path 与实际物理文件位置不一致的规范
      schema_mismatch- frontmatter 缺少必要字段（spec_id/title/lifecycle）的规范
      duplicate_dir  - 项目目录中存在重复编号目录（如 3个 04_前缀）
      stale_root     - spec_registry.json 中 workspace_root 与实际工作空间不符
    """
    ws = _resolve_workspace(workspace, ctx)
    ws_config = _load_ws_config(config_path, ws)

    # 加载 spec_registry.json
    registry_path = ws / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
    if ws_config and hasattr(ws_config, "registry_path") and ws_config.registry_path:
        registry_path = ws_config.registry_path

    if not registry_path.exists():
        console.print(f"[red]错误: 找不到 spec_registry.json: {registry_path}[/red]")
        raise SystemExit(1)

    registry: dict[str, object] = json.loads(registry_path.read_text(encoding="utf-8"))
    run_all = "all" in rule
    issues: list[dict[str, str]] = []

    # ── LINT-001: stale_root ──────────────────────────────────────────────
    if run_all or "stale_root" in rule:
        stored_root = registry.get("workspace_root", "")
        stored_path = Path(str(stored_root))
        if stored_path != ws:
            issues.append(
                {
                    "rule": "LINT-001/stale_root",
                    "severity": "ERROR",
                    "message": "workspace_root 路径过期",
                    "detail": f"registry 中: {stored_root!r} | 实际应为: {ws}",
                    "suggestion": f'将 spec_registry.json 中 workspace_root 改为 "{ws}"',
                }
            )

    # ── LINT-002: orphan_file ─────────────────────────────────────────────
    if run_all or "orphan_file" in rule:
        spec_dirs = [
            ws / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域",
            ws / "00_Obsidian_Base全局规范文件仓库" / "02_Python开发域",
            ws / "00_Obsidian_Base全局规范文件仓库" / "03_PLC自动化域",
            ws / "00_Obsidian_Base全局规范文件仓库" / "04_驾驶舱与全栈域",
            ws / "00_Obsidian_Base全局规范文件仓库" / "05_跨域工具规范",
        ]
        registered_paths: set[Path] = set()
        for _spec_id, spec in _iter_registry_specs(registry):
            cp = spec.get("canonical_path", "")
            if cp:
                registered_paths.add((ws / str(cp)).resolve())

        for spec_dir in spec_dirs:
            if not spec_dir.exists():
                continue
            for md_file in spec_dir.rglob("*.md"):
                if md_file.name.startswith("00_INDEX"):
                    continue
                if _is_non_spec_artifact(md_file):
                    continue
                resolved = md_file.resolve()
                if resolved not in registered_paths:
                    issues.append(
                        {
                            "rule": "LINT-002/orphan_file",
                            "severity": "WARNING",
                            "message": "孤立规范文件（未在 registry 注册）",
                            "detail": str(md_file.relative_to(ws)),
                            "suggestion": "在 spec_registry.json 中添加对应注册条目，或移入 _archive/",
                        }
                    )

    # ── LINT-003: path_drift ──────────────────────────────────────────────
    if run_all or "path_drift" in rule:
        for spec_id, spec in _iter_registry_specs(registry):
            cp = spec.get("canonical_path", "")
            if not cp:
                continue
            full_path = (ws / str(cp)).resolve()
            if not full_path.exists():
                issues.append(
                    {
                        "rule": "LINT-003/path_drift",
                        "severity": "ERROR",
                        "message": f"[{spec_id}] canonical_path 对应文件不存在（路径漂移）",
                        "detail": str(cp),
                        "suggestion": "更新 canonical_path 到文件实际位置，或恢复文件",
                    }
                )

    # ── LINT-004: schema_mismatch ─────────────────────────────────────────
    if run_all or "schema_mismatch" in rule:
        import re

        required_fields = {"spec_id", "title", "lifecycle"}
        # 同时接受新旧字段名
        field_aliases = {
            "spec_id": {"spec_id", "id"},
            "title": {"title", "name"},
            "lifecycle": {"lifecycle", "status"},
        }

        for spec_id, spec in _iter_registry_specs(registry):
            cp = spec.get("canonical_path", "")
            if not cp:
                continue
            if _should_skip_schema_mismatch(spec):
                continue
            full_path = (ws / str(cp)).resolve()
            if not full_path.exists():
                continue
            text = full_path.read_text(encoding="utf-8", errors="ignore")
            if not text.startswith("---"):
                issues.append(
                    {
                        "rule": "LINT-004/schema_mismatch",
                        "severity": "WARNING",
                        "message": f"[{spec_id}] 缺少 YAML frontmatter",
                        "detail": str(cp),
                        "suggestion": "运行 `auto-pm spec frontmatter --fix` 自动添加",
                    }
                )
                continue
            fm_end = text.find("---", 3)
            if fm_end == -1:
                continue
            fm_text = text[3:fm_end]
            for field in required_fields:
                aliases = field_aliases[field]
                found = any(
                    re.search(rf"^\s*{alias}\s*:", fm_text, re.MULTILINE) for alias in aliases
                )
                if not found:
                    issues.append(
                        {
                            "rule": "LINT-004/schema_mismatch",
                            "severity": "WARNING",
                            "message": f"[{spec_id}] frontmatter 缺少必要字段: {field}（或其别名 {aliases}）",
                            "detail": str(cp),
                            "suggestion": f"在 frontmatter 中添加 {field}: 字段",
                        }
                    )

    # ── LINT-005: duplicate_dir ───────────────────────────────────────────
    if run_all or "duplicate_dir" in rule:
        project_roots = [
            ws / "0100_PLC自动化",
        ]
        import re as _re

        for proj_root in project_roots:
            if not proj_root.exists():
                continue
            for project_dir in proj_root.iterdir():
                if not project_dir.is_dir():
                    continue
                prefix_counter: dict[str, list[str]] = {}
                for sub in project_dir.iterdir():
                    if not sub.is_dir():
                        continue
                    m = _re.match(r"^(\d+)_", sub.name)
                    if m:
                        prefix = m.group(1)
                        prefix_counter.setdefault(prefix, []).append(sub.name)
                for prefix, dirs in prefix_counter.items():
                    if len(dirs) > 1 and not _is_allowed_duplicate_dir(prefix, dirs):
                        issues.append(
                            {
                                "rule": "LINT-005/duplicate_dir",
                                "severity": "WARNING",
                                "message": f"[{project_dir.name}] 目录编号 {prefix}_ 重复",
                                "detail": "重复目录: " + ", ".join(dirs),
                                "suggestion": "参照 PROJ-016 规范，将重复目录重命名为唯一编号",
                            }
                        )

    # ── 输出 ──────────────────────────────────────────────────────────────
    unicode_output = _supports_unicode_output()
    severity_icons = {
        "ERROR": ("🔴" if unicode_output else "[ERR]"),
        "WARNING": ("🟡" if unicode_output else "[WARN]"),
    }
    severity_colors = {"ERROR": "red", "WARNING": "yellow"}

    if fmt == "json":
        click.echo(
            json.dumps({"lint_results": issues, "total": len(issues)}, ensure_ascii=False, indent=2)
        )
    else:
        if not issues:
            ok_icon = "✅" if unicode_output else "[OK]"
            console.print(f"[green]{ok_icon} 所有 lint 规则通过！[/green]")
        else:
            console.print(
                f"\n[bold]规范注册表 Lint 报告[/bold] — 共发现 [bold red]{len(issues)}[/bold red] 个问题\n"
            )
            console.print("─" * 70)
            for issue in issues:
                sev = issue["severity"]
                icon = severity_icons.get(sev, "")
                color = severity_colors.get(sev, "white")
                console.print(f"[{color}]{icon} [{issue['rule']}] {issue['message']}[/{color}]")
                if issue.get("detail"):
                    console.print(f"   [dim]路径: {issue['detail']}[/dim]")
                if issue.get("suggestion"):
                    console.print(f"   [cyan]建议: {issue['suggestion']}[/cyan]")
                console.print()

        error_count = sum(1 for i in issues if i["severity"] == "ERROR")
        warning_count = sum(1 for i in issues if i["severity"] == "WARNING")
        console.print("─" * 70)
        console.print(
            f"  汇总: 🔴 ERROR {error_count} | 🟡 WARNING {warning_count} | 共 {len(issues)} 项"
        )

    raise SystemExit(1 if any(i["severity"] == "ERROR" for i in issues) else 0)


# ── sync 子命令 ─────────────────────────────────────────────────────────────


@spec_group.command("sync")
@click.option("-w", "--workspace", default=None, help="工作空间根目录（未指定时回退全局 -w）")
@click.option(
    "--config", "config_path", default=None, type=click.Path(), help="工作空间配置文件路径"
)
@click.pass_context
def sync(ctx: click.Context, workspace: str | None, config_path: str | None) -> None:
    """一键全量同步与重构 Obsidian 全局规范仓库 (DEV-030 V2.2.0)

    流水线原子操作：
    1. 重新生成 00_INDEX_全局规范索引.md 及各业务线通用规范 README
    2. 执行全局规范健康检查 (SHC-001~014)
    """
    ws = _resolve_workspace(workspace, ctx)
    ws_config = _load_ws_config(Path(config_path) if config_path else None, ws)
    unicode_output = _supports_unicode_output()

    console.print("[bold cyan]==================================================[/bold cyan]")
    console.print("[bold cyan]  auto-pm Obsidian 全局规范仓库自动同步流水线     [/bold cyan]")
    console.print("[bold cyan]==================================================[/bold cyan]")

    # 1. 重构索引
    idx_svc = IndexService(ws, config=ws_config)
    idx_output = idx_svc.run(domains=None)
    for gen_f in idx_output.generated_files:
        ok_icon = "✅" if unicode_output else "[OK]"
        console.print(f"[green]{ok_icon} 已生成索引:[/green] {gen_f}")

    if idx_output.errors:
        err_icon = "🔴" if unicode_output else "[ERR]"
        for err in idx_output.errors:
            console.print(f"[red]{err_icon} 索引错误: {err}[/red]")

    # 2. 健康检查
    chk_svc = CheckService(ws, config=ws_config)
    chk_output = chk_svc.run(scope="workspace")

    console.print("─" * 50)
    console.print(
        f"  规范健康自检汇总: 🔴 错误 {chk_output.error_count} | 🟡 警告 {chk_output.warning_count} | 🟢 提示 {chk_output.info_count}"
    )

    if chk_output.error_count == 0 and not idx_output.errors:
        ok_icon = "✅" if unicode_output else "[OK]"
        console.print(
            f"[bold green]{ok_icon} Obsidian 规范知识库与索引已成功同步且 100% 健康！[/bold green]"
        )
        raise SystemExit(0)
    else:
        warn_icon = "⚠️" if unicode_output else "[WARN]"
        console.print(
            f"[bold yellow]{warn_icon} 同步已完成，但存在部分需要整改的规范项。[/bold yellow]"
        )
        raise SystemExit(1 if chk_output.error_count > 0 else 0)
