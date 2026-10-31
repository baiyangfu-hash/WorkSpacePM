"""PLC-HMI 概念映射：CLI 命令行入口（约束命令组（guard/verify/check/heal/list））

像 PLC 的调试终端/工程师站，通过命令行直接操作功能块。
不经过 HMI 画面，直接调用 FB 或 SFB。

--- 原始注释 ---

约束管理命令组 - CHG-SCPT-2026-137 Phase 1

提供约束检查、文件守护、自愈修复能力。

子命令：
- list：列出所有已加载的约束定义
- check：检查约束合规性（全量/单文件/门禁模式）
- guard：文件操作前登记哈希快照
- verify：文件操作后验证哈希一致性
- heal：自愈修复（剥离多余 BOM 等）

Usage:
    auto-pm -w "." constraint list
    auto-pm -w "." constraint check [--file <path>] [--json] [--gate]
    auto-pm -w "." constraint guard <file>
    auto-pm -w "." constraint verify <file>
    auto-pm -w "." constraint heal [--file <path>] [--all] [--dry-run]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from auto_pm.constraint.guard import FileGuard
from auto_pm.constraint.loader import ConstraintLoader, ConstraintLoadError
from auto_pm.constraint.models import Constraint, Violation

console = Console()


def _resolve_workspace(ctx: click.Context) -> Path:
    """从 Click Context 解析工作空间路径"""
    app_ctx = ctx.obj
    if app_ctx is not None and hasattr(app_ctx, "workspace_root"):
        ws = app_ctx.workspace_root
        if ws:
            return Path(ws)
    return Path.cwd()


def _icon(ok: bool) -> str:
    """根据终端支持返回 emoji 或 ASCII 图标"""
    if _supports_unicode():
        return "✅" if ok else "❌"
    return "[OK]" if ok else "[FAIL]"


def _supports_unicode() -> bool:
    """检测终端是否支持 Unicode 输出"""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "✅❌⚠".encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


# ── constraint 命令组 ──

@click.group(name="constraint")
def constraint_group() -> None:
    """约束管理：检查/守护/自愈项目文件约束合规性

    Phase 1 支持的约束：
    - CST-FILE-001: 禁止 Python 脚本直接写磁盘（文件守护）
    - CST-FILE-002: 文件编码完整性（BOM 检测 + 自愈）
    """
    pass


@constraint_group.command("list")
@click.pass_context
def list_constraints(ctx: click.Context) -> None:
    """列出所有已加载的约束定义"""
    workspace = _resolve_workspace(ctx)

    try:
        loader = ConstraintLoader(workspace)
        constraints = loader.load_all()
    except ConstraintLoadError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise SystemExit(1)

    if not constraints:
        console.print("[yellow]未找到约束定义文件[/yellow]")
        return

    table = Table(title="约束定义列表")
    table.add_column("ID", style="cyan")
    table.add_column("名称", style="white")
    table.add_column("类型", style="magenta")
    table.add_column("严重级别", style="yellow")
    table.add_column("自愈", style="green")

    for cst in constraints:
        table.add_row(
            cst.id,
            cst.name,
            cst.type,
            cst.severity.upper(),
            _icon(cst.auto_fix),
        )

    console.print(table)
    console.print(f"\n共 {len(constraints)} 个约束定义")


@constraint_group.command("check")
@click.option("--file", "-f", "file_path", default=None, help="检查单个文件")
@click.option("--json", "json_output", is_flag=True, default=False, help="JSON 格式输出")
@click.option("--gate", is_flag=True, default=False, help="门禁模式：有违规时返回非零退出码")
@click.pass_context
def check_constraints(
    ctx: click.Context,
    file_path: str | None,
    json_output: bool,
    gate: bool,
) -> None:
    """检查约束合规性

    全量模式：扫描所有约束定义作用域内的文件。
    单文件模式：仅检查指定文件。
    门禁模式：发现违规时返回退出码 1。
    """
    workspace = _resolve_workspace(ctx)

    try:
        loader = ConstraintLoader(workspace)
        constraints = loader.load_all()
    except ConstraintLoadError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise SystemExit(1)

    if not constraints:
        console.print("[yellow]未找到约束定义文件[/yellow]")
        return

    guard = FileGuard(workspace)
    violations: list[Violation] = []

    # ── 单文件模式 ──
    if file_path:
        fp = workspace / file_path
        if not fp.is_file():
            console.print(f"[red]文件不存在: {fp}[/red]")
            raise SystemExit(1)

        violations.extend(_check_file_encoding(fp, guard, constraints))
        violations.extend(_check_file_guard(fp, guard, constraints))

    # ── 全量模式 ──
    else:
        for cst in constraints:
            if cst.type == "file_encoding":
                violations.extend(_check_encoding_scope(cst, workspace, guard))
            elif cst.type == "file_guard":
                violations.extend(_check_guard_scope(cst, workspace, guard))

    # ── 输出 ──
    if json_output:
        result = {
            "total_constraints": len(constraints),
            "violations_count": len(violations),
            "violations": [
                {
                    "constraint_id": v.constraint_id,
                    "file_path": v.file_path,
                    "rule_type": v.rule_type,
                    "message": v.message,
                    "severity": v.severity,
                }
                for v in violations
            ],
        }
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not violations:
            console.print(f"[green]{_icon(True)} 所有约束检查通过[/green]")
        else:
            console.print(f"[red]{_icon(False)} 发现 {len(violations)} 个违规:[/red]")
            for v in violations:
                console.print(f"  [{v.severity}] {v.constraint_id}: {v.message}")
                console.print(f"    文件: {v.file_path}")

    if gate and violations:
        raise SystemExit(1)


@constraint_group.command("guard")
@click.argument("file", type=click.Path(exists=True))
@click.pass_context
def guard_file(ctx: click.Context, file: str) -> None:
    """文件操作前登记哈希快照

    FILE: 要守护的文件路径
    """
    workspace = _resolve_workspace(ctx)
    fp = Path(file).resolve()

    guard = FileGuard(workspace)
    try:
        snap = guard.take_snapshot(fp)
    except FileNotFoundError:
        console.print(f"[red]文件不存在: {fp}[/red]")
        raise SystemExit(1)

    console.print(f"[green]{_icon(True)} 快照已登记[/green]")
    console.print(f"  snapshot_id: {snap['snapshot_id']}")
    console.print(f"  sha256: {snap['sha256'][:32]}...")
    console.print(f"  size: {snap['size']} bytes")
    console.print(f"  bom_count: {snap['bom_count']}")


@constraint_group.command("verify")
@click.argument("file", type=click.Path(exists=True))
@click.pass_context
def verify_file(ctx: click.Context, file: str) -> None:
    """文件操作后验证哈希一致性

    FILE: 要验证的文件路径
    """
    workspace = _resolve_workspace(ctx)
    fp = Path(file).resolve()

    guard = FileGuard(workspace)
    result = guard.verify_snapshot(fp)

    if result["verified"]:
        console.print(f"[green]{_icon(True)} 文件完整，未检测到外部修改[/green]")
    else:
        console.print(f"[red]{_icon(False)} 文件已被修改![/red]")
        if result.get("error"):
            console.print(f"  错误: {result['message']}")
        else:
            console.print(f"  hash_changed: {result['hash_changed']}")
            console.print(f"  size_delta: {result['size_delta']} bytes")
            console.print(f"  bom_delta: {result['bom_delta']}")
            if result["bom_accumulated"]:
                console.print("  [yellow]⚠ BOM 累积检测到![/yellow]")
        raise SystemExit(1)


@constraint_group.command("heal")
@click.option("--file", "-f", "file_path", default=None, help="修复单个文件")
@click.option("--all", "heal_all", is_flag=True, default=False, help="修复所有文件")
@click.option("--dry-run", is_flag=True, default=False, help="预览模式，不实际修改")
@click.pass_context
def heal_files(
    ctx: click.Context,
    file_path: str | None,
    heal_all: bool,
    dry_run: bool,
) -> None:
    """自愈修复：剥离多余 BOM 等

    支持单文件修复（--file）和全量扫描修复（--all）。
    使用 --dry-run 预览将要修复的内容。
    """
    workspace = _resolve_workspace(ctx)
    guard = FileGuard(workspace)

    # ── 单文件模式 ──
    if file_path:
        fp = workspace / file_path
        if not fp.is_file():
            console.print(f"[red]文件不存在: {fp}[/red]")
            raise SystemExit(1)

        encoding_result = guard.check_encoding(fp)
        if encoding_result["is_healthy"]:
            console.print(f"[green]{_icon(True)} 文件编码正常 (BOM: {encoding_result['bom_count']})[/green]")
            return

        if dry_run:
            console.print(f"[yellow]🔍 预览: {fp}[/yellow]")
            console.print(f"   BOM 数量: {encoding_result['bom_count']} → 将剥离 {encoding_result['bom_count']} 个")
            return

        result = guard.heal_bom(fp)
        if result["healed"]:
            console.print(f"[green]🔧 {result['message']}[/green]")
            console.print(f"   释放: {result['bytes_removed']} bytes")
        else:
            console.print(f"[yellow]{result['message']}[/yellow]")
        return

    # ── 全量模式 ──
    if heal_all:
        # 扫描所有约束定义的文件
        try:
            loader = ConstraintLoader(workspace)
            constraints = loader.load_all()
        except ConstraintLoadError as e:
            console.print(f"[red]错误: {e}[/red]")
            raise SystemExit(1)

        # 收集所有需要检查的文件
        all_files: set[Path] = set()
        for cst in constraints:
            if cst.type == "file_encoding":
                for pattern in cst.scope.patterns:
                    for matched in workspace.glob(pattern):
                        if matched.is_file():
                            # 排除检查
                            excluded = False
                            for exc in cst.scope.exclude:
                                if matched.match(exc):
                                    excluded = True
                                    break
                            if not excluded:
                                all_files.add(matched)

        if not all_files:
            console.print("[yellow]未找到需要检查的文件[/yellow]")
            return

        files_to_heal: list[Path] = []
        healthy_count = 0

        for fp in sorted(all_files):
            result = guard.check_encoding(fp)
            if result["is_healthy"]:
                healthy_count += 1
            else:
                files_to_heal.append(fp)

        if dry_run:
            console.print(f"[yellow]🔍 扫描 {len(all_files)} 个文件...[/yellow]")
            for fp in files_to_heal:
                result = guard.check_encoding(fp)
                console.print(f"   {fp}: {result['bom_count']} BOM → 将剥离")
            console.print(f"   正常: {healthy_count} 个, 待修复: {len(files_to_heal)} 个")
            return

        if not files_to_heal:
            console.print(f"[green]{_icon(True)} 所有 {len(all_files)} 个文件编码正常[/green]")
            return

        healed_count = 0
        for fp in files_to_heal:
            result = guard.heal_bom(fp)
            if result["healed"]:
                console.print(f"[green]🔧 {fp.name}: {result['message']}[/green]")
                healed_count += 1

        console.print(f"\n修复 {healed_count} 个文件，跳过 {healthy_count} 个正常文件")
        return

    # 未指定模式
    console.print("[yellow]请指定 --file <path> 或 --all[/yellow]")
    console.print("示例: auto-pm constraint heal --file PM_SESSION_SW-2026-008.md")
    console.print("示例: auto-pm constraint heal --all --dry-run")


# ── 内部检查函数 ──

def _check_file_encoding(
    fp: Path, guard: FileGuard, constraints: list[Constraint]
) -> list[Violation]:
    """检查单个文件的编码完整性"""
    violations: list[Violation] = []
    for cst in constraints:
        if cst.type != "file_encoding":
            continue
        result = guard.check_encoding(fp)
        if not result["is_healthy"]:
            violations.append(Violation(
                constraint_id=cst.id,
                file_path=str(fp),
                rule_type="bom_count",
                message=f"文件包含 {result['bom_count']} 个 BOM（正常为 0-1）",
                severity=cst.severity,
                evidence=result,
            ))
    return violations


def _check_file_guard(
    fp: Path, guard: FileGuard, constraints: list[Constraint]
) -> list[Violation]:
    """检查单个文件是否有未登记的修改"""
    violations: list[Violation] = []
    for cst in constraints:
        if cst.type != "file_guard":
            continue
        if guard.has_snapshot(fp):
            result = guard.verify_snapshot(fp)
            if not result["verified"]:
                violations.append(Violation(
                    constraint_id=cst.id,
                    file_path=str(fp),
                    rule_type="no_external_write",
                    message=f"文件哈希不匹配，可能被外部修改: {result.get('message', '')}",
                    severity=cst.severity,
                    evidence=result,
                ))
    return violations


def _check_encoding_scope(
    cst: Constraint, workspace: Path, guard: FileGuard
) -> list[Violation]:
    """扫描约束作用域内所有文件的编码完整性"""
    violations: list[Violation] = []
    for pattern in cst.scope.patterns:
        for fp in workspace.glob(pattern):
            if not fp.is_file():
                continue
            excluded = any(fp.match(exc) for exc in cst.scope.exclude)
            if excluded:
                continue
            result = guard.check_encoding(fp)
            if not result["is_healthy"]:
                violations.append(Violation(
                    constraint_id=cst.id,
                    file_path=str(fp),
                    rule_type="bom_count",
                    message=f"文件包含 {result['bom_count']} 个 BOM（正常为 0-1）",
                    severity=cst.severity,
                    evidence=result,
                ))
    return violations


def _check_guard_scope(
    cst: Constraint, workspace: Path, guard: FileGuard
) -> list[Violation]:
    """扫描约束作用域内所有文件的守护状态"""
    violations: list[Violation] = []
    for pattern in cst.scope.patterns:
        for fp in workspace.glob(pattern):
            if not fp.is_file():
                continue
            excluded = any(fp.match(exc) for exc in cst.scope.exclude)
            if excluded:
                continue
            if guard.has_snapshot(fp):
                result = guard.verify_snapshot(fp)
                if not result["verified"]:
                    violations.append(Violation(
                        constraint_id=cst.id,
                        file_path=str(fp),
                        rule_type="no_external_write",
                        message=f"文件哈希不匹配: {result.get('message', '')}",
                        severity=cst.severity,
                        evidence=result,
                    ))
    return violations
