"""Runtime-identity refusal for command-line write commands (TD-SW008-174).

The thin SDK (``auto_pm.api``) re-resolves the runtime identity before every write and refuses on any conflict
(``RUNTIME_IDENTITY_DIVERGENCE`` / ``RUNTIME_IDENTITY_UNVERIFIED``).  The ``pm`` command line used to write anyway;
these helpers give each write command the same refusal, keyed by the project the write belongs to.
"""

from __future__ import annotations

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


def project_of_planning_request(ctx: click.Context, request_id: str) -> str:
    """The project a saved planning request (draft) belongs to."""

    app_ctx: AppContext = ctx.find_root().obj
    try:
        return ContinuityStore(app_ctx.control_root).get_planning_draft(request_id).subject_project_id
    except (ContinuityStoreError, ValueError) as error:
        raise click.ClickException(str(error)) from error
