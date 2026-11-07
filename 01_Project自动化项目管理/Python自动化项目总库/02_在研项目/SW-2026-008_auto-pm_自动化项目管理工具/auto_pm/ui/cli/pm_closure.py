"""IDE-agent closing commands: ``pm verify`` and ``pm close`` (gap 8).

Before these commands an IDE agent (Trae and the like) had no command after ``pm confirm-start``: quality verification
(``verify_for_acceptance``) and closure (``close_accepted``) were reachable only from the GUI or by writing a temporary
Python script, which in D08 left ``__pycache__`` in the release folder and made the launcher fall back to the old release.

Both commands call the very services the cockpit uses, so no gate is relaxed: ``pm verify`` produces the system-bound
quality Checkpoint with the Run's own lease (read from the local wallet, never printed); ``pm close`` runs
``close_accepted`` (C05 to C08, including bringing an isolated Run's accepted bytes back into the control root) and only
for a Mission the user has already accepted.  Acceptance itself stays the user's act.
"""

from __future__ import annotations

import json
from typing import Any

import click

from auto_pm.app_context import AppContext
from auto_pm.application.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.application.core.control_root_sync import ControlRootSyncService
from auto_pm.application.core.lease_keepalive import LeaseKeepAlive
from auto_pm.application.core.pm_closure_service import PmClosureError
from auto_pm.application.core.pm_cockpit_service import PmCockpitError, PmCockpitService
from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.application.core.worktree_policy_service import (
    WorktreePolicyError,
    WorktreePolicyService,
)
from auto_pm.contracts.mission import Mission
from auto_pm.contracts.pm_cockpit import PmCockpitCompletionState
from auto_pm.infrastructure import lease_wallet, memory_preflight
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.ui.cli.continuity import _secret_from_environment
from auto_pm.ui.cli.runtime_identity_guard import require_runtime_identity


def _echo(payload: dict[str, Any]) -> None:
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _guarded_mission(ctx: click.Context, mission_id: str) -> Mission:
    """Control root only, and the same runtime-identity refusal the thin SDK applies before any write."""

    app_ctx: AppContext = ctx.find_root().obj
    try:
        WorktreePolicyService(app_ctx.control_root).require_control_root()
        mission = ContinuityStore(app_ctx.control_root).get_mission(mission_id.strip())
    except (WorktreePolicyError, ContinuityStoreError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    require_runtime_identity(ctx, mission.subject_project_id)
    return mission

def _echo_run_drift_hint(app_ctx: AppContext, run: object) -> None:
    """Print the control-root drift preview to stderr; a hint must never stop verification."""
    try:
        owned = tuple(getattr(run, "owned_paths", ()) or ())
        git_head = str(getattr(run, "git_head", "") or "")
        lines = ControlRootSyncService(app_ctx.control_root).run_drift_lines(owned, git_head)
    except Exception as error:  # noqa: BLE001 - a preview that cannot be computed is "unverified", not a failure
        click.echo(f"⚠️ [控制根同步] 未核实：{type(error).__name__}", err=True)
        return
    for line in lines:
        click.echo(f"⚠️ [控制根同步] {line}", err=True)



@click.command(name="verify")
@click.option("--mission-id", required=True, help="要做质量验证的 Mission")
@click.option(
    "--lease-wallet",
    "use_wallet",
    is_flag=True,
    help="从本机钱包读取本 Run 当前持有者的口令（推荐）",
)
@click.option(
    "--lease-token-env", default=None, metavar="ENV_NAME", help="口令所在环境变量；读取后立即删除"
)
@click.pass_context
def verify_pm(
    ctx: click.Context, mission_id: str, use_wallet: bool, lease_token_env: str | None
) -> None:
    """质量验证：对最新 VERIFYING 的 Run 生成系统证据检查点，通过后进入“等待用户验收”。"""

    if use_wallet == (lease_token_env is not None):
        raise click.UsageError("必须且只能给出一个口令来源：--lease-wallet 或 --lease-token-env")
    # Before anything is read or written: a verification runs ~15 min of real tests, and a machine near its commit limit must not
    # start one (11-03 laptop memory P1).  There is no option to continue anyway.
    try:
        unverified = memory_preflight.require_headroom()
    except memory_preflight.MemoryPreflightRefusedError as error:
        raise click.ClickException(str(error)) from error
    if unverified:
        click.echo(f"⚠️ [内存预检] {unverified}", err=True)
    app_ctx: AppContext = ctx.find_root().obj
    mission = _guarded_mission(ctx, mission_id)
    if not mission.root_work_id:
        raise click.ClickException("Mission 缺少根 Work，不能验证")
    store = ContinuityStore(app_ctx.control_root)
    try:
        runs = store.list_runs(mission.root_work_id, include_terminal=True)
        if not runs:
            raise click.ClickException("该 Mission 还没有 Run，不能验证")
        run_id = runs[0].run_id
        owner_id = store.get_lease(run_id).owner_id
    except ContinuityStoreError as error:
        raise click.ClickException(str(error)) from error
    # Say it before the ~15 minute verification: a control root changed since the Run started makes the closure refuse.
    _echo_run_drift_hint(app_ctx, runs[0])
    if lease_token_env is not None:
        token = _secret_from_environment(lease_token_env)
    else:
        try:
            token = lease_wallet.load(app_ctx.control_root, run_id=run_id, owner_id=owner_id)
        except lease_wallet.LeaseWalletError as error:
            raise click.ClickException(str(error)) from error
    # One verify runs ~15 min: keep the Run's lease alive meanwhile. Not strict: verify has its own lease checks, and a
    # refused renewal (for example at the 3 h hold cap) is reported in the result instead of blocking it.
    keepalive = LeaseKeepAlive(
        ContinuityExecutionService(app_ctx.control_root),
        run_id=run_id,
        owner_id=owner_id,
        token=token,
        strict=False,
    )
    try:
        with keepalive:
            outcome, reason = PmFacadeService(
                app_ctx.control_root, execution_root=app_ctx.workspace_root
            ).verify_for_acceptance_with_reason(mission.mission_id, lease_token=token)
    except PmFacadeError as error:
        raise click.ClickException(str(error)) from error
    payload = outcome.model_dump(mode="json")
    if reason:
        payload["reason"] = reason
    if keepalive.error:
        payload["lease_keepalive_warning"] = keepalive.error
    try:
        # D-31: say when the Run's lease now ends, so nobody works on past a deadline they were never shown.
        payload["lease_expires_at"] = store.get_lease(run_id).expires_at
    except ContinuityStoreError:
        pass  # the verdict is what counts; a lease that cannot be read here is reported by the next command
    _echo(payload)
    if not outcome.verified:
        ctx.exit(1)


@click.command(name="close")
@click.option("--mission-id", required=True, help="用户已验收、要收口的 Mission")
@click.pass_context
def close_pm(ctx: click.Context, mission_id: str) -> None:
    """一步收口：与驾驶舱“确认验收/重试同步”同一个 close_accepted；只收用户已验收的 Mission。"""

    app_ctx: AppContext = ctx.find_root().obj
    mission = _guarded_mission(ctx, mission_id)
    try:
        completion, reason = PmCockpitService(app_ctx.control_root).close_accepted_with_reason(
            mission.mission_id
        )
    except (PmCockpitError, PmClosureError) as error:
        raise click.ClickException(str(error)) from error
    payload = completion.model_dump(mode="json")
    if reason:
        payload["reason"] = reason
    _echo(payload)
    if completion.state is not PmCockpitCompletionState.COMPLETED:
        ctx.exit(1)


@click.command(name="acceptance-scan")
@click.option("--pid", "project_id", required=True, help="项目编号，例如 DJ-2026-009")
@click.pass_context
def acceptance_scan_pm(ctx: click.Context, project_id: str) -> None:
    """只读：列出这个项目进行中的任务里，``pm verify`` 会拒绝执行的已批准验收命令（发版前在账本所在电脑上跑）。

    只检查、不执行、不写账。有任何一条会被拒就以退出码 1 结束；被点名的任务要重新 ``pm plan`` 并由用户批准。
    """

    app_ctx: AppContext = ctx.find_root().obj
    try:
        scan = PmFacadeService(app_ctx.control_root, execution_root=app_ctx.workspace_root).scan_approved_acceptance_commands(
            project_id
        )
    except (PmFacadeError, ContinuityStoreError) as error:
        raise click.ClickException(str(error)) from error
    _echo(
        {
            "project_id": project_id,
            "missions_with_commands": scan.missions_scanned,
            "commands_checked": scan.commands_scanned,
            "would_refuse": [
                {"mission_id": item.mission_id, "index": item.index, "command": item.command, "reason": item.reason}
                for item in scan.findings
            ],
            # Still run by ``pm verify``, but a new plan with the same text would be refused (PowerShell changes it when pasted).
            "would_be_refused_at_plan": [
                {"mission_id": item.mission_id, "index": item.index, "command": item.command, "reason": item.reason}
                for item in scan.fragile
            ],
        }
    )
    if scan.findings:
        ctx.exit(1)
