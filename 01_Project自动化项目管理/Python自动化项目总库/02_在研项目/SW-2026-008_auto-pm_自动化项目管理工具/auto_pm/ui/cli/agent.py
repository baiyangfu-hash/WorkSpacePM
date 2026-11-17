"""AI 登记表命令（CHG-SCPT-2026-712）：内置五个以外的 AI 由用户本人在本机登记，登记后马上能开工位、声明身份、开分支。

* ``agent register <名字>``：只限用户本人（带任何 agent 标记都拒）；分支前缀固定是 ``<名字>/``；
* ``agent unregister <名字>``：只限用户本人；这个名字还有工位或有效占位就拒；
* ``agent list``：只读，列内置的和登记的（``--all`` 连已注销的一起列）。

登记表在本机账本里（``R/.auto-pm/continuity.db``），每台电脑各登记一次；只在控制根跑。

退出码：0 成功；1 被安全检查拒绝（说明里写了原因和下一步）；2 用法或账本出错。
"""

from __future__ import annotations

import json
import os

import click

from auto_pm.app_context import AppContext
from auto_pm.application.core.agent_registry import (
    VIA,
    AgentRegistration,
    AgentRegistryError,
    AgentRegistryRefusedError,
    AgentRegistryService,
    user_only_refusal,
)
from auto_pm.application.core.agent_worktree_service import BUILTIN_ROSTER
from auto_pm.application.core.lease_handover_service import agent_markers
from auto_pm.ui.cli.runtime_identity_guard import require_runtime_identity_for_workspace


def _root(ctx: click.Context) -> str:
    app_ctx: AppContext = ctx.find_root().obj
    return app_ctx.control_root or app_ctx.workspace_root or os.getcwd()


def _fail(error: AgentRegistryError) -> None:
    refused = isinstance(error, AgentRegistryRefusedError)
    click.echo(f"{'拒绝' if refused else '错误'} {error}", err=True)
    raise SystemExit(1 if refused else 2)


def _shown(item: AgentRegistration) -> str:
    line = f"{item.name}  分支前缀 {item.branch_prefix}  登记：{item.registered_by}，{item.registered_at}（{item.source_ref}）"
    if not item.active:
        line += f"  已注销：{item.retired_by}，{item.retired_at}"
    return line


@click.group(name="agent")
def agent_group() -> None:
    """AI 登记表：内置五个以外的 AI 由用户本人登记（只在控制根；登记、注销只限用户本人）"""


@agent_group.command("register")
@click.argument("name")
@click.option("--via", type=click.Choice(VIA), default="terminal", show_default=True, help="从哪里登记的（看板按钮传 board）")
@click.pass_context
def agent_register(ctx: click.Context, name: str, via: str) -> None:
    """登记一个新 AI：名字小写字母开头、2～20 位小写字母和数字，分支前缀自动是 <名字>/（只限用户本人）"""

    if agent_markers(os.environ):  # 只限用户本人：带任何 agent 标记一律拒（命令层先拦一道，服务层再拦一道）
        _fail(AgentRegistryRefusedError(user_only_refusal("登记新 AI")))
    require_runtime_identity_for_workspace(ctx)
    try:
        done = AgentRegistryService(_root(ctx)).register(name, via=via)
    except AgentRegistryError as error:
        _fail(error)
        return
    click.echo(f"已登记 {done.name}：分支前缀 {done.branch_prefix}，登记人 {done.registered_by}，{done.registered_at}")
    click.echo(
        f"这个 AI 现在可以：用 AUTO_PM_AGENT={done.name}（Windows 用 pm-as-agent.ps1 {done.name}）运行驾驶舱命令，"
        f"main.py worktree open {done.name} <卡号> 开工位，分支名 {done.branch_prefix}<卡号>"
    )


@agent_group.command("unregister")
@click.argument("name")
@click.pass_context
def agent_unregister(ctx: click.Context, name: str) -> None:
    """注销一个登记的 AI：还有工位或有效占位就拒；登记记录留着（只限用户本人）"""

    if agent_markers(os.environ):  # 只限用户本人：带任何 agent 标记一律拒（命令层先拦一道，服务层再拦一道）
        _fail(AgentRegistryRefusedError(user_only_refusal("注销 AI")))
    require_runtime_identity_for_workspace(ctx)
    try:
        done = AgentRegistryService(_root(ctx)).unregister(name)
    except AgentRegistryError as error:
        _fail(error)
        return
    click.echo(f"已注销 {done.name}（{done.retired_by}，{done.retired_at}）；以后带这个名字的 AI 会被拒，登记记录留着")


@agent_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="机器可读输出")
@click.option("--all", "include_retired", is_flag=True, help="连已注销的一起列")
@click.pass_context
def agent_list(ctx: click.Context, as_json: bool, include_retired: bool) -> None:
    """列出名册：内置的五个和本机登记的 AI（只读）"""

    try:
        registered = AgentRegistryService(_root(ctx)).list(include_retired=include_retired)
    except AgentRegistryError as error:
        _fail(error)
        return
    if as_json:
        click.echo(
            json.dumps(
                {
                    "builtin": [{"name": name, "branch_prefix": prefix} for name, prefix in BUILTIN_ROSTER.items()],
                    "registered": [item.as_json() for item in registered],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    click.echo("内置：" + "、".join(f"{name}（{prefix}）" for name, prefix in BUILTIN_ROSTER.items()))
    if not registered:
        click.echo("登记的：还没有（用户本人在看板“工作树与分支”页点“登记新 AI”，或运行 main.py agent register <名字>）")
        return
    click.echo(f"登记的：{len(registered)} 个")
    for item in registered:
        click.echo("  " + _shown(item))
