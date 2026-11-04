"""``pm state-backup push|pull|status``: the ledger's off-site copy in the user's private repository."""

from __future__ import annotations

from pathlib import Path

import click

from auto_pm.app_context import AppContext
from auto_pm.infrastructure.continuity_store import ContinuityStoreError
from auto_pm.infrastructure.state_backup import StateBackupService, read_state_backup_status


def _service(ctx: click.Context) -> StateBackupService:
    app_ctx: AppContext = ctx.find_root().obj
    return StateBackupService(Path(app_ctx.workspace_root).resolve())


@click.group(name="state-backup")
def state_backup_group() -> None:
    """账本异地备份：把去掉租约口令的账本副本推到私有仓库，或取回一份（换电脑用）。"""


@state_backup_group.command(name="push")
@click.option("--dry-run", is_flag=True, help="只做到“副本已去口令并通过扫描”，不写仓库、不推送、不记备份时间。")
@click.pass_context
def push_command(ctx: click.Context, dry_run: bool) -> None:
    """Take a sanitised copy of the ledger and push it to the private repository."""

    try:
        result = _service(ctx).push(dry_run=dry_run)
    except ContinuityStoreError as error:
        raise click.ClickException(str(error)) from error
    size = f"{result.gz_size / 1024:.0f} KiB"
    if result.dry_run:
        click.echo(f"演练通过（没有推送）：{result.name}，{result.events} 条事件，去掉 {result.redacted_tokens} 个租约口令，压缩后 {size}。")
        return
    click.echo(f"异地备份完成：{result.name}，{result.events} 条事件，去掉 {result.redacted_tokens} 个租约口令，压缩后 {size}。")
    click.echo(f"远程提交：{result.remote_commit[:12]}（已核对远程分支头）")


@state_backup_group.command(name="pull")
@click.option("--name", default=None, help="备份目录名或文件名前缀（不填取最新）。")
@click.pass_context
def pull_command(ctx: click.Context, name: str | None) -> None:
    """Bring a backup home (verified); prints the restore command and never replaces the live ledger."""

    try:
        result = _service(ctx).pull(name)
    except ContinuityStoreError as error:
        raise click.ClickException(str(error)) from error
    app_ctx: AppContext = ctx.find_root().obj
    try:
        shown = result.path.resolve().relative_to(Path(app_ctx.workspace_root).resolve()).as_posix()
    except ValueError:
        shown = str(result.path)
    click.echo(f"已取回并校验：{shown}（{result.report.events} 条事件，链完整）")
    click.echo("要用它替换当前账本（先关掉驾驶舱；原账本会被移到备份目录，不删除），运行：")
    click.echo(f"  python main.py continuity restore-backup {shown}")


@state_backup_group.command(name="status")
@click.pass_context
def status_command(ctx: click.Context) -> None:
    """Show when the last off-site backup was pushed from this computer (reads a local file only)."""

    app_ctx: AppContext = ctx.find_root().obj
    click.echo(read_state_backup_status(Path(app_ctx.control_root)).line())
