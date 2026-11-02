"""Role pack CLI: list and check the job descriptions the cockpit keeps for its digital staff.

Read-only; needs no ledger and no network.  Exit codes: 0 no FAIL, 1 at least one FAIL.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from auto_pm.app_context import AppContext
from auto_pm.application.core.role_pack_service import RolePackService


def _service(ctx: click.Context) -> RolePackService:
    app_ctx: AppContext = ctx.obj
    root = app_ctx.control_root or app_ctx.workspace_root
    return RolePackService(workspace_root=Path(root) if root else None)


@click.group("role")
def role_group() -> None:
    """角色包：驾驶舱保管的岗位说明（产品经理、各类编程工程师）；只读，断网可用"""


@role_group.command("list")
@click.pass_context
def list_cmd(ctx: click.Context) -> None:
    """列出驾驶舱里的角色包"""
    for pack in _service(ctx).role_dirs():
        click.echo(pack.name)


@role_group.command("check")
@click.option("--json", "as_json", is_flag=True, help="机器可读输出")
@click.pass_context
def check_cmd(ctx: click.Context, as_json: bool) -> None:
    """检查角色包：文件齐全、角色号合法、规范编号存在、指针不死链、与旧技能逐字一致"""
    result = _service(ctx).check()
    if as_json:
        click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        for finding in result.findings:
            click.echo(f"[{finding.level}] {finding.code} {finding.role}: {finding.message}")
        verdict = "通过" if result.ok else "不通过"
        click.echo(f"角色包检查{verdict}：共 {len(result.roles)} 个角色包，{len(result.findings)} 条发现")
    raise SystemExit(0 if result.ok else 1)
