"""plc docs 子命令组 - PLC 文档与代码一致性核对、自动补全、确认（REQ-SW008-M2-DOCSYNC，V01B）

Commands:
    check <ID> [--json] [--strict-markers]      核对接口文档/变量定义文档与 SCL 代码，并检查里程碑表计划日期（有失败项退出码为 1）
    sync <ID> [--dry-run] [--apply-suggestions] 按代码补全文档（补入的行带“待确认”标记，只写文档）
    confirm <ID>                                去掉已与代码对上的行上的“待确认”标记
    plan <ID> --start --type --scale [--with] [--write]  按项目周期规范推里程碑计划日期（只填空着的计划日期）

``<ID>`` 也可以换成 ``--project-path <项目目录>``（用于隔离副本）。
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import asdict

import click

from auto_pm.app_context import AppContext
from auto_pm.application.core.project_service import ProjectService
from auto_pm.domain.plc import cycle_plan as cp
from auto_pm.domain.plc import doc_consistency as dc
from auto_pm.domain.plc import milestones as ms
from auto_pm.ui.cli.caller_path import CallerPath
from auto_pm.ui.cli.runtime_identity_guard import require_runtime_identity


def _resolve(ctx: click.Context, project_id: str | None, project_path: str | None) -> str:
    if project_path:
        return project_path
    if not project_id:
        raise click.UsageError("请指定项目ID，或使用 --project-path 指定项目目录")
    app_ctx: AppContext = ctx.obj
    project = ProjectService(app_ctx.workspace_root).get_project(project_id)
    if project is None:
        raise click.ClickException(f"项目不存在: {project_id}")
    return str(project.path)


def _require_identity(ctx: click.Context, project_id: str | None, project_path: str | None) -> None:
    """Refuse a write on a registered project whose runtime identity has a conflict.

    ``--project-path`` names an isolated copy chosen by the caller, not a registered project, so it is not checked.
    """
    if project_id and not project_path:
        require_runtime_identity(ctx, project_id)


_ID = click.argument("project_id", required=False)
_PATH = click.option("--project-path", type=CallerPath(file_okay=False, exists=True), default=None,
                     help="直接指定项目目录（用于隔离副本）")


@click.group(name="docs")
def docs_group() -> None:
    """文档与代码一致性：核对、自动补全、确认"""


@docs_group.command(name="check")
@_ID
@_PATH
@click.option("--json", "output_json", is_flag=True, help="以JSON格式输出结果")
@click.option("--strict-markers", is_flag=True, help="仍有“待确认”标记时也按失败处理（退出码 1）")
@click.pass_context
def cmd_check(ctx: click.Context, project_id: str | None, project_path: str | None,
              output_json: bool, strict_markers: bool) -> None:
    """核对接口文档/变量定义文档与 SCL 代码（名称、类型、方向、注释），并检查里程碑表的计划日期
    （新项目没填直接拦，老项目迁入先只提示）。有失败项退出码为 1。"""
    path = _resolve(ctx, project_id, project_path)
    analysis = dc.analyze_project(path)
    failing = [f for f in analysis.findings if f.severity == "fail"]
    warnings = [f for f in analysis.findings if f.severity == "warn"]
    marked = analysis.marked_rows
    milestones = ms.check_project(path)
    ms_failing = [f for f in milestones.findings if f.severity == "fail"]
    if output_json:
        payload = {
            "schema_version": "plc-docs-check.v1",
            "project_path": analysis.project_path,
            "objects": [{"kind": r.obj.kind, "name": r.obj.name, "variables": len(r.obj.variables),
                         "doc_state": r.doc_state, "status": r.status} for r in analysis.reports],
            "findings": [asdict(f) for f in analysis.findings],
            "marked_rows": len(marked),
            "milestones": {
                "applicable": milestones.applicable,
                "path": milestones.path,
                "origin": milestones.origin,
                "rows": [asdict(row) for row in milestones.rows],
                "findings": [asdict(f) for f in milestones.findings],
            },
        }
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for report in analysis.reports:
            if not report.findings:
                continue
            click.echo(f"[{report.status}] {report.obj.kind} {report.obj.name}")
            for finding in report.findings:
                click.echo(f"    {finding.severity}: {finding.render()}")
        click.echo(f"拦住项 {len(failing)}、警告 {len(warnings)}、待确认 {len(marked)}")
        if failing:
            click.echo("提示：运行 plc docs sync 按代码补全文档，补全后审核并运行 plc docs confirm")
        if milestones.findings:
            origin = milestones.origin or "未写"
            click.echo(f"[{'fail' if ms_failing else 'warn'}] 里程碑表（项目来源：{origin}）")
            for finding in milestones.findings:
                click.echo(f"    {finding.severity}: {finding.render()}")
        if milestones.applicable:
            click.echo(f"里程碑表：拦住项 {len(ms_failing)}、提示 {len(milestones.findings) - len(ms_failing)}")
        else:
            click.echo("里程碑表：不适用（共享库）")
    if failing or ms_failing or (strict_markers and marked):
        ctx.exit(1)


@docs_group.command(name="sync")
@_ID
@_PATH
@click.option("--dry-run", is_flag=True, help="只显示将要做什么，不写文件")
@click.option("--apply-suggestions", is_flag=True,
              help="同时按代码改写不一致的行，并把代码里已不存在的旧条目移到文末归档小节（不删除）")
@click.pass_context
def cmd_sync(ctx: click.Context, project_id: str | None, project_path: str | None,
             dry_run: bool, apply_suggestions: bool) -> None:
    """按 SCL 代码补全接口文档与变量定义文档（只写文档，从不写 SCL；补入的行带“待确认”标记）。"""
    if not dry_run:
        _require_identity(ctx, project_id, project_path)
    path = _resolve(ctx, project_id, project_path)
    result = dc.sync_project(path, write=not dry_run, apply_suggestions=apply_suggestions)
    prefix = "（预览，未写文件）" if dry_run else ""
    click.echo(f"{prefix}新建文档 {len(result.created)} 份，修改文档 {len(result.written)} 份，补入 {result.added_rows} 行，"
               f"按建议改动 {result.applied} 处")
    for item in [*result.created, *result.written]:
        click.echo(f"    {item}")
    if result.suggestions and not apply_suggestions:
        click.echo(f"还有 {len(result.suggestions)} 处需要人工处理或使用 --apply-suggestions：")
        for line in result.suggestions[:10]:
            click.echo(f"    {line}")
    click.echo("补入的行带“【待确认】”标记；审核后运行 plc docs confirm")


@docs_group.command(name="confirm")
@_ID
@_PATH
@click.pass_context
def cmd_confirm(ctx: click.Context, project_id: str | None, project_path: str | None) -> None:
    """去掉已与代码对上的行上的“待确认”标记；仍与代码不一致的行保持标记。"""
    _require_identity(ctx, project_id, project_path)
    path = _resolve(ctx, project_id, project_path)
    result = dc.confirm_project(path)
    click.echo(f"已确认 {result.confirmed} 行")
    for line in result.skipped:
        click.echo(f"    未确认: {line}")


@docs_group.command(name="plan")
@_ID
@_PATH
@click.option("--start", "start_text", required=True, help="需求确认日 YYYY-MM-DD")
@click.option("--type", "main_type", required=True, type=click.Choice(list(cp.MAIN_TYPES)), help="主类型")
@click.option("--with", "addons", multiple=True, type=click.Choice(list(cp.ADDONS)), help="附加项，可写多次")
@click.option("--scale", required=True, help="规模（按规范里的规模表：单机 / 小线 / 整线）")
@click.option("--spec", "spec_path", type=CallerPath(dir_okay=False, exists=True), default=None,
              help="周期规范文件（默认在项目上级目录里找 0100_PLC自动化/00_通用规范/项目周期规范.md）")
@click.option("--write", is_flag=True, help="把推算日期写进里程碑表里空着的计划日期（已有日期不改）")
@click.pass_context
def cmd_plan(ctx: click.Context, project_id: str | None, project_path: str | None, start_text: str,
             main_type: str, addons: tuple[str, ...], scale: str, spec_path: str | None, write: bool) -> None:
    """按项目周期规范推里程碑计划日期。默认只显示；加 --write 才写，且只填空着的计划日期。"""
    if write:
        _require_identity(ctx, project_id, project_path)
    path = _resolve(ctx, project_id, project_path)
    try:
        start = _dt.date.fromisoformat(start_text)
    except ValueError:
        raise click.BadParameter("要写 YYYY-MM-DD", param_hint="--start") from None
    if not ms._DATE.match(start_text):
        raise click.BadParameter("要写 YYYY-MM-DD", param_hint="--start")
    found = spec_path or cp.find_spec(path)
    if not found:
        raise click.ClickException(f"找不到周期规范 {cp.SPEC_RELATIVE}，用 --spec 指定")
    try:
        spec = cp.read_spec(found)
        dates = cp.plan(spec, start, main_type, tuple(addons), scale)
    except cp.CycleSpecError as exc:
        raise click.ClickException(str(exc)) from None
    note = cp.describe(spec, main_type, tuple(addons), scale)
    click.echo(f"{note}（需求确认日 {start.isoformat()}）")
    for stage, date in dates.items():
        click.echo(f"    {stage}  {date.isoformat()}")
    files = ms.find_milestone_files(path)
    if not files:
        click.echo("项目里没有里程碑表，没有写入；先按模板 11_里程碑表模板.md 建表")
        return
    result = cp.fill_milestone_file(files[0], dates, note, write=write)
    prefix = "已写入" if write else "（预览，未写文件）将写入"
    click.echo(f"{prefix} {len(result.filled)} 个空着的计划日期：{'、'.join(result.filled) or '无'}")
    if result.kept:
        click.echo(f"已有日期或不适用、没动：{'、'.join(result.kept)}")
