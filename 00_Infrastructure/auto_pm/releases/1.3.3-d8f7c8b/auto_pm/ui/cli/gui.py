"""PLC-HMI 概念映射：CLI 命令行入口（GUI 启动命令（启动 HMI 画面））

像 PLC 的调试终端/工程师站，通过命令行直接操作功能块。
不经过 HMI 画面，直接调用 FB 或 SFB。

--- 原始注释 ---

GUI CLI 命令

启动 QML 桌面 GUI 应用。

Usage:
    auto-pm gui                       # 启动 QML GUI
    auto-pm gui --debug
    auto-pm gui -w <workspace_root>
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path
from types import TracebackType

import click
from rich.console import Console

from auto_pm.app_context import AppContext

console = Console()


def _install_crash_handler() -> None:
    """安装 GUI 崩溃捕获（sys.excepthook + crash.log）

    电气部门试用期间如遇 GUI 崩溃，未捕获的异常会写入
    ``~/.auto-pm/logs/crash.log``，含时间戳 + 完整 traceback，便于问题追溯。
    """
    crash_log_path = Path.home() / ".auto-pm" / "logs" / "crash.log"
    try:
        crash_log_path.parent.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        return  # 目录创建失败时静默跳过，不阻断 GUI 启动

    def _crash_excepthook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        # 先写 crash.log
        try:
            ts = datetime.now().isoformat()
            tb_lines = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            with open(crash_log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'=' * 80}\n")
                f.write(f"[{ts}] GUI 未捕获异常\n")
                f.write(f"{'=' * 80}\n")
                f.write(tb_lines)
        except (OSError, PermissionError):
            pass
        # 再调用默认 excepthook 输出到 stderr
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _crash_excepthook


@click.command("gui")
@click.option("--debug", is_flag=True, help="调试模式（开启 DevTools / 控制台输出）")
@click.pass_context
def gui_command(ctx: click.Context, debug: bool) -> None:
    """启动 GUI 桌面应用（QML）"""
    app_ctx: AppContext = ctx.obj
    workspace = app_ctx.workspace_root

    # 安装 GUI 崩溃捕获（电气部门试用期间问题追溯）
    _install_crash_handler()

    console.print(f"[cyan]启动 QML GUI: {workspace}[/cyan]")
    _run_qml_gui(workspace, debug)


def _run_qml_gui(workspace: str, debug: bool) -> None:
    """启动 QML GUI"""
    try:
        from auto_pm.ui.qml_main_window import run_qml_gui
    except ImportError as e:
        console.print(f"[red]QML 模块加载失败: {e}[/red]")
        console.print("[yellow]请确认 PySide6 ≥ 6.5 已安装[/yellow]")
        raise click.ClickException("QML 模块加载失败") from e

    exit_code = run_qml_gui(workspace_root=workspace, debug=debug)
    if exit_code != 0:
        raise click.ClickException(f"QML GUI 异常退出: exit_code={exit_code}")
