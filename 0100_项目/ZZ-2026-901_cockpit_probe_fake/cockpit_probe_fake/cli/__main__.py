"""cockpit-probe-fake CLI 主入口

Usage:
    cockpit-probe-fake --help
    cockpit-probe-fake hello
"""

from __future__ import annotations

import click
from rich.console import Console

from cockpit_probe_fake.app_context import AppContext

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

console = Console()


@click.version_option(None, "--version", "-v")
@click.group(context_settings=CONTEXT_SETTINGS)
@click.option(
    "--workspace",
    "-w",
    envvar="COCKPIT_PROBE_FAKE_WORKSPACE",
    default=None,
    help="工作空间根目录（默认: 当前目录）",
)
@click.pass_context
def cli(ctx: click.Context, workspace: str | None) -> None:
    """cockpit_probe_fake - cockpit-probe 一次性假项目，只用于命令探测"""
    ctx.ensure_object(AppContext)
    app_ctx: AppContext = ctx.obj
    if workspace:
        app_ctx.workspace_root = workspace


@cli.command()
@click.pass_context
def hello(ctx: click.Context) -> None:
    """示例命令：打印欢迎信息"""
    app_ctx: AppContext = ctx.obj
    console.print("[green]Hello from cockpit_probe_fake![/green]")
    console.print(f"workspace: {app_ctx.workspace_root}")


if __name__ == "__main__":
    cli()
