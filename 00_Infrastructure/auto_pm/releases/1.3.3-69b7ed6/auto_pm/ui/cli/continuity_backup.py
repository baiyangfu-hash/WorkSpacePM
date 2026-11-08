"""``continuity backup`` / ``verify-backup`` / ``restore-backup`` / ``list-backups``: the ledger's spare copy."""

from __future__ import annotations

import json
from pathlib import Path

import click

from auto_pm.app_context import AppContext
from auto_pm.infrastructure.continuity_backup import (
    ContinuityBackupService,
    LedgerReport,
    manifest_path,
    verify_backup_file,
)
from auto_pm.infrastructure.continuity_store import ContinuityStoreError
from auto_pm.ui.cli.caller_path import CallerPath


def _service(ctx: click.Context) -> ContinuityBackupService:
    app_ctx: AppContext = ctx.find_root().obj
    try:
        return ContinuityBackupService(Path(app_ctx.workspace_root).resolve())
    except ContinuityStoreError as error:
        raise click.ClickException(str(error)) from error


def _shown(service: ContinuityBackupService, path: Path) -> str:
    try:
        return path.resolve().relative_to(service.workspace_root).as_posix()
    except ValueError:
        return str(path)


def _summary(report: LedgerReport) -> str:
    head = report.head_event_id or "（无事件）"
    integrity = "ok" if report.integrity == "ok" else "失败"
    return f"{report.events} 条事件，链头 {head}，完整性 {integrity}"


def _emit_report(ctx: click.Context, service: ContinuityBackupService, report: LedgerReport, *, as_json: bool, title: str) -> None:
    if as_json:
        payload = report.as_dict()
        payload["path"] = _shown(service, report.path)
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    elif report.ok:
        click.echo(f"{title}：{_summary(report)}，链完整，0 处断裂")
    else:
        click.echo(f"{title}未通过：{_summary(report)}", err=True)
        for finding in report.findings:
            click.echo(f"  - {finding}", err=True)
    if not report.ok:
        ctx.exit(1)


@click.command(name="backup")
@click.option("--keep", type=click.IntRange(min=1), default=None, help="只保留最近 N 份备份（不填则一份都不删）。")
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出结果。")
@click.pass_context
def backup_command(ctx: click.Context, keep: int | None, as_json: bool) -> None:
    """Take an online, self-verified copy of .auto-pm/continuity.db; the live ledger is only read."""

    service = _service(ctx)
    try:
        path, report = service.backup(keep=keep)
    except ContinuityStoreError as error:
        raise click.ClickException(str(error)) from error
    if as_json:
        payload = report.as_dict()
        payload["path"] = _shown(service, path)
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    click.echo(f"备份完成：{_summary(report)}")
    click.echo(f"文件：{_shown(service, path)}")


@click.command(name="verify-backup")
@click.argument("backup_file", required=False, type=CallerPath(path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出结果。")
@click.pass_context
def verify_backup_command(ctx: click.Context, backup_file: Path | None, as_json: bool) -> None:
    """Verify a backup file (or, without an argument, the live ledger): integrity and the whole event chain."""

    service = _service(ctx)
    try:
        if backup_file is None:
            report = service.verify_live()
            title = "账本校验"
        else:
            report = verify_backup_file(backup_file)
            title = "备份校验"
    except ContinuityStoreError as error:
        raise click.ClickException(str(error)) from error
    _emit_report(ctx, service, report, as_json=as_json, title=title)


@click.command(name="restore-backup")
@click.argument("backup_file", type=CallerPath(path_type=Path))
@click.option("--yes", is_flag=True, help="不再询问，直接恢复。")
@click.pass_context
def restore_backup_command(ctx: click.Context, backup_file: Path, yes: bool) -> None:
    """Replace the live ledger with a verified backup; the replaced files are kept, never deleted."""

    service = _service(ctx)
    if not yes:
        click.confirm(
            f"将用 {backup_file.name} 替换当前账本（原账本会移到备份目录保存，不删除）。请先关掉驾驶舱。继续吗？",
            abort=True,
        )
    try:
        result = service.restore(backup_file)
    except ContinuityStoreError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"恢复完成：{_summary(result.report)}")
    if result.replaced_dir is not None:
        click.echo(f"原账本已保存到：{_shown(service, result.replaced_dir)}")


@click.command(name="list-backups")
@click.pass_context
def list_backups_command(ctx: click.Context) -> None:
    """List the backups taken by ``continuity backup``, newest last."""

    service = _service(ctx)
    backups = service.list_backups()
    if not backups:
        click.echo("还没有备份。")
        return
    for path in backups:
        detail = ""
        manifest = manifest_path(path)
        if manifest.is_file():
            try:
                recorded = json.loads(manifest.read_text(encoding="utf-8", errors="replace"))
                detail = f"  {recorded.get('events')} 条事件，链头 {recorded.get('head_event_id') or '（无）'}"
            except json.JSONDecodeError:
                detail = "  （清单无法读取）"
        click.echo(f"{_shown(service, path)}{detail}")


BACKUP_COMMANDS = (backup_command, verify_backup_command, restore_backup_command, list_backups_command)
