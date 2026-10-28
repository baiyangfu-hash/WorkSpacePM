"""Runtime-identity refusal for command-line write commands (TD-SW008-174).

The thin SDK (``auto_pm.api``) re-resolves the runtime identity before every write and refuses on any conflict
(``RUNTIME_IDENTITY_DIVERGENCE`` / ``RUNTIME_IDENTITY_UNVERIFIED``).  The ``pm`` command line used to write anyway;
these helpers give each write command the same refusal, keyed by the project the write belongs to.
"""

from __future__ import annotations

from collections.abc import Callable

import click

from auto_pm.app_context import AppContext
from auto_pm.core.workspace_context_service import WorkspaceContextError, WorkspaceContextService
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


def require_runtime_identity(ctx: click.Context, project_id: str) -> None:
    """Refuse the write (``ClickException``) when the runtime identity for ``project_id`` has any conflict."""

    app_ctx: AppContext = ctx.find_root().obj
    try:
        context = WorkspaceContextService(
            str(app_ctx.control_root), execution_root=app_ctx.workspace_root
        ).resolve(project_id=project_id, start_path=app_ctx.control_root)
    except WorkspaceContextError as error:
        raise click.ClickException(str(error)) from error
    if context.conflicts:
        raise click.ClickException("运行身份未通过校验，已拒绝写入：" + "；".join(context.conflicts))


WARNINGS_META_KEY = "runtime_identity_warnings"
WARNINGS_FIELD = "runtime_identity_warnings"


def recorded_warnings(ctx: click.Context | None) -> list[str]:
    """The identity warnings this command invocation raised, for its JSON receipt (empty when there were none)."""

    return list(ctx.find_root().meta.get(WARNINGS_META_KEY, [])) if ctx is not None else []


def _warn(ctx: click.Context, text: str) -> None:
    click.echo(text, err=True)
    ctx.find_root().meta.setdefault(WARNINGS_META_KEY, []).append(text)


def warn_runtime_identity(ctx: click.Context, project_id: str | Callable[[], str]) -> None:
    """Recovery commands never refuse (they are what repairs a broken runtime); a conflict is reported on stderr and in the JSON receipt.

    ``project_id`` may be a callable so that a failed lookup (the very Run being repaired may be unreadable) also only warns.
    """

    try:
        resolved = project_id() if callable(project_id) else project_id
        app_ctx: AppContext = ctx.find_root().obj
        context = WorkspaceContextService(
            str(app_ctx.control_root), execution_root=app_ctx.workspace_root
        ).resolve(project_id=resolved, start_path=app_ctx.control_root)
        conflicts = tuple(context.conflicts)
    except Exception as error:  # the guard's own failure must never stop a command that repairs a broken runtime
        _warn(ctx, f"警告：运行身份无法核对，命令照常执行：{error}")
        return
    if conflicts:
        _warn(ctx, "警告：运行身份有冲突，命令照常执行：" + "；".join(conflicts))


def project_of_mission(ctx: click.Context, mission_id: str) -> str:
    """The project a Mission belongs to, for commands that are given only a Mission."""

    app_ctx: AppContext = ctx.find_root().obj
    try:
        return ContinuityStore(app_ctx.control_root).get_mission(mission_id.strip()).subject_project_id
    except (ContinuityStoreError, ValueError) as error:
        raise click.ClickException(str(error)) from error


def project_of_run(ctx: click.Context, run_id: str) -> str:
    """The project a Run belongs to (Run -> Work -> project)."""

    app_ctx: AppContext = ctx.find_root().obj
    store = ContinuityStore(app_ctx.control_root)
    try:
        return store.get_work(store.get_run(run_id.strip()).work_id).subject_project_id
    except (ContinuityStoreError, ValueError) as error:
        raise click.ClickException(str(error)) from error


def project_of_work(ctx: click.Context, work_id: str) -> str:
    """The project a Work item belongs to."""

    app_ctx: AppContext = ctx.find_root().obj
    try:
        return ContinuityStore(app_ctx.control_root).get_work(work_id.strip()).subject_project_id
    except (ContinuityStoreError, ValueError) as error:
        raise click.ClickException(str(error)) from error


def project_of_checkpoint(ctx: click.Context, checkpoint_id: str) -> str:
    """The project a checkpoint belongs to (checkpoint -> Run -> Work)."""

    app_ctx: AppContext = ctx.find_root().obj
    store = ContinuityStore(app_ctx.control_root)
    try:
        return store.get_work(store.get_run(store.get_checkpoint(checkpoint_id.strip()).run_id).work_id).subject_project_id
    except (ContinuityStoreError, ValueError) as error:
        raise click.ClickException(str(error)) from error


def project_of_handoff(ctx: click.Context, handoff_id: str) -> str:
    """The project a v2 handoff belongs to (handoff -> Work)."""

    app_ctx: AppContext = ctx.find_root().obj
    store = ContinuityStore(app_ctx.control_root)
    try:
        return store.get_work(store.get_handoff(handoff_id.strip()).work_id).subject_project_id
    except (ContinuityStoreError, ValueError) as error:
        raise click.ClickException(str(error)) from error


def require_runtime_identity_for_change(ctx: click.Context, change_number: str, project_id: str | None) -> None:
    """Guard a command that is given a change number and maybe a project.

    The project comes from ``--pid`` or from the change order itself.  A change order that cannot be found (or is ambiguous) has
    no project to check: the command reports that itself and writes nothing, so there is nothing to refuse.
    """

    from auto_pm.domain.change.change_service import ChangeService

    resolved = (project_id or "").strip()
    if not resolved:
        app_ctx: AppContext = ctx.find_root().obj
        try:
            change = ChangeService(app_ctx.workspace_root).get_change_request(change_number)
        except Exception:  # ambiguous or unreadable: the command itself reports it, and it writes nothing
            return
        resolved = getattr(change, "project_id", "") if change is not None else ""
    if resolved:
        require_runtime_identity(ctx, resolved)


def project_of_planning_request(ctx: click.Context, request_id: str) -> str:
    """The project a saved planning request (draft) belongs to."""

    app_ctx: AppContext = ctx.find_root().obj
    try:
        return ContinuityStore(app_ctx.control_root).get_planning_draft(request_id).subject_project_id
    except (ContinuityStoreError, ValueError) as error:
        raise click.ClickException(str(error)) from error
