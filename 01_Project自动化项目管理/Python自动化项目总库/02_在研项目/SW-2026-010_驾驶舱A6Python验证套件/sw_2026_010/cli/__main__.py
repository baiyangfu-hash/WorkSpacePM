"""sw-2026-010 CLI 主入口

Usage:
    sw-2026-010 --help
    sw-2026-010 hello
"""

from __future__ import annotations

import click
from rich.console import Console

from sw_2026_010.app_context import AppContext
from sw_2026_010.core.rated_current import calculate_rated_current

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

console = Console()


@click.version_option(None, "--version", "-v")
@click.group(context_settings=CONTEXT_SETTINGS)
@click.option(
    "--workspace",
    "-w",
    envvar="SW_2026_010_WORKSPACE",
    default=None,
    help="工作空间根目录（默认: 当前目录）",
)
@click.pass_context
def cli(ctx: click.Context, workspace: str | None) -> None:
    """驾驶舱A6Python验证套件 - 驾驶舱A6Python验证套件"""
    ctx.ensure_object(AppContext)
    app_ctx: AppContext = ctx.obj
    if workspace:
        app_ctx.workspace_root = workspace


@cli.command()
@click.pass_context
def hello(ctx: click.Context) -> None:
    """示例命令：打印欢迎信息"""
    app_ctx: AppContext = ctx.obj
    console.print("[green]Hello from 驾驶舱A6Python验证套件![/green]")
    console.print(f"workspace: {app_ctx.workspace_root}")


@cli.command("rated-current")
@click.option("--power-kw", type=float, required=True, help="额定功率（kW）")
@click.option("--voltage-v", type=float, required=True, help="线电压（V）")
@click.option("--power-factor", type=float, required=True, help="功率因数 cosφ")
@click.option("--efficiency", type=float, required=True, help="效率 η")
def rated_current(
    power_kw: float,
    voltage_v: float,
    power_factor: float,
    efficiency: float,
) -> None:
    """按额定功率、线电压、功率因数、效率计算三相电机额定电流（A）"""
    try:
        current = calculate_rated_current(power_kw, voltage_v, power_factor, efficiency)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    console.print(f"三相电机额定电流: {current:.1f} A")


if __name__ == "__main__":
    cli()
