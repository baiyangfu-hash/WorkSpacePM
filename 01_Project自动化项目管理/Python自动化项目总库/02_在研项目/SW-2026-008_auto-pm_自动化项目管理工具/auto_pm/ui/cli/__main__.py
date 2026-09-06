"""PLC-HMI 概念映射：CLI 命令行入口（CLI 主入口（命令路由/参数解析））

像 PLC 的调试终端/工程师站，通过命令行直接操作功能块。
不经过 HMI 画面，直接调用 FB 或 SFB。

--- 原始注释 ---

auto-pm CLI 主入口

统一管理 PLC/Python 多技术栈项目。

Usage:
    auto-pm project list
    auto-pm project create --stack plc --id DJ-2026-010 --name 边框缓存机
    auto-pm plc init DJ-2026-010
    auto-pm plc check DJ-2026-010
    auto-pm plc check --all
    auto-pm plc repair DJ-2026-010 --rename
"""

from __future__ import annotations

import os
import sys


def _fix_windows_encoding() -> None:
    """Windows 终端编码修复：强制 stdout/stderr 为 UTF-8

    避免与 pytest capture 机制冲突。
    """
    if sys.platform != "win32":
        return
    try:
        if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr is not None and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        # pytest capture（StringIO 无 reconfigure）或旧 Python，静默跳过
        pass

_fix_windows_encoding()


import click  # noqa: E402
from rich.console import Console  # noqa: E402

from auto_pm import __version__  # noqa: E402
from auto_pm.app_context import AppContext  # noqa: E402
from auto_pm.cli.change import change_group  # noqa: E402
from auto_pm.cli.clean import clean_cmd  # noqa: E402
from auto_pm.cli.constraint import constraint_group  # noqa: E402
from auto_pm.cli.decision import decision_group  # noqa: E402
from auto_pm.cli.delivery import delivery_group  # noqa: E402
from auto_pm.cli.doc import doc_group  # noqa: E402
from auto_pm.cli.doctor import doctor_command  # noqa: E402
from auto_pm.cli.dogfood import dogfood_group  # noqa: E402
from auto_pm.cli.git_hook import git_hook_group  # noqa: E402
from auto_pm.cli.gui import gui_command  # noqa: E402
from auto_pm.cli.handoff import handoff_group  # noqa: E402
from auto_pm.cli.ledger import ledger_group  # noqa: E402
from auto_pm.cli.plc import plc_group  # noqa: E402
from auto_pm.cli.pm import pm_group  # noqa: E402
from auto_pm.cli.project import project_group  # noqa: E402
from auto_pm.cli.prototype import prototype_cmd  # noqa: E402
from auto_pm.cli.python import python_group  # noqa: E402
from auto_pm.cli.session import pm_session_group  # noqa: E402
from auto_pm.cli.spec import spec_group  # noqa: E402
from auto_pm.cli.template import template_group  # noqa: E402
from auto_pm.cli.vartable import vartable_group  # noqa: E402
from auto_pm.cli.workflow import workflow_group  # noqa: E402

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])

console = Console()


@click.version_option(version=__version__, package_name="auto_pm", message="auto-pm, version %(version)s")
@click.group(context_settings=CONTEXT_SETTINGS)
@click.option(
    "--workspace",
    "-w",
    envvar="AUTO_PM_WORKSPACE",
    default=None,
    help="工作空间根目录（默认: 当前目录）",
)
@click.pass_context
def cli(ctx: click.Context, workspace: str | None) -> None:
    """auto-pm - 自动化项目管理工具

    统一 CLI 管理 PLC/Python 多技术栈项目。
    """
    ctx.ensure_object(AppContext)
    app_ctx: AppContext = ctx.obj
    if workspace:
        app_ctx.workspace_root = os.path.abspath(workspace)


# 挂载子命令组
cli.add_command(project_group)
cli.add_command(change_group)
cli.add_command(delivery_group)
cli.add_command(doc_group)
cli.add_command(plc_group)
cli.add_command(python_group)
cli.add_command(spec_group)
cli.add_command(template_group)
cli.add_command(vartable_group)
cli.add_command(gui_command)
cli.add_command(handoff_group)
cli.add_command(decision_group)
cli.add_command(git_hook_group)
cli.add_command(pm_group)
cli.add_command(pm_session_group)
cli.add_command(ledger_group)
cli.add_command(constraint_group)
cli.add_command(workflow_group)
cli.add_command(prototype_cmd)
cli.add_command(doctor_command)
cli.add_command(dogfood_group)
cli.add_command(clean_cmd)


if __name__ == "__main__":
    _fix_windows_encoding()
    cli()
