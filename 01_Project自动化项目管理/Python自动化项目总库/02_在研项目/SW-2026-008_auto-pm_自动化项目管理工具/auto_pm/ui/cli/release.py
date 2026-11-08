"""Release CLI (D-146, card 1): ``release status`` and ``release deploy <commit> --check-only``.  Read-only; the real deploy comes in a later card.

退出码：0 可以部署／状态已打印；1 用法错误或真部署尚未实现；2 预检没通过（有失败或没法核实的项）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from auto_pm.app_context import AppContext
from auto_pm.application.core import release_deploy_check as check
from auto_pm.ui.cli.caller_path import CallerPath


def _root(ctx: click.Context) -> Path:
    app_ctx: AppContext = ctx.obj
    return Path(app_ctx.control_root or app_ctx.workspace_root or os.getcwd())


@click.group(name="release")
def release_group() -> None:
    """发版：状态与部署前预检（只读）。"""


@release_group.command(name="status")
@click.option("--json", "as_json", is_flag=True, help="机器可读输出")
@click.pass_context
def release_status(ctx: click.Context, as_json: bool) -> None:
    """配置的有效版本与上一版、已装发布、发布记录是否互相一致、最近一次部署回执。"""

    info = check.status(_root(ctx))
    if as_json:
        click.echo(json.dumps(info, ensure_ascii=False, indent=2))
        return
    for slot, pointer in info["pointers"].items():
        click.echo(f"{slot}: {pointer['release_id'] or '读不出'}（{pointer['updated_at'] or '无时间'}）")
    click.echo(f"已装发布 {len(info['installed_releases'])} 个；发布记录一致性：{info['consistency']['status']}")
    for failure in info["consistency"]["failures"][:5]:
        click.echo(f"  ✗ {failure}")
    click.echo(f"最近部署回执：{info['last_receipt'] or '没有'}")


@release_group.command(name="deploy")
@click.argument("commit")
@click.option("--check-only/--no-check-only", default=True, help="只做预检，什么都不写（现在只支持这个）")
@click.option("--gate-verdict", type=CallerPath(path_type=Path, dir_okay=False), help="这个提交的全量门禁判决 JSON")
@click.option("--audit-signoff", type=CallerPath(path_type=Path, dir_okay=False), help="独立审计的放行记录")
@click.option("--json", "as_json", is_flag=True, help="机器可读输出")
@click.pass_context
def release_deploy(
    ctx: click.Context, commit: str, check_only: bool, gate_verdict: Path | None, audit_signoff: Path | None, as_json: bool
) -> None:
    """部署前预检：这个提交现在能不能发布。真部署还没做（D-146 卡4），不带 --check-only 会被拒。"""

    if not check_only:
        raise click.ClickException("真部署还没实现（D-146 卡4）；现在只有 --check-only 预检")
    report = check.preflight(_root(ctx), commit, gate_verdict=gate_verdict, audit_signoff=audit_signoff)
    if as_json:
        click.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        for line in report.render():
            click.echo(line)
    ctx.exit(0 if report.ok else 2)
