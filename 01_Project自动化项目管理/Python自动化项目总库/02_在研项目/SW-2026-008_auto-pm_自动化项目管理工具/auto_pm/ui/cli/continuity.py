"""Platform-neutral Work/Run/Checkpoint/Handoff v2 CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import click
from pydantic import BaseModel, ValidationError

from auto_pm import __version__
from auto_pm.app_context import AppContext
from auto_pm.contracts.continuity import RunState, WorkKind, WorkState
from auto_pm.contracts.mission import AuthorityEnvelope, MissionState
from auto_pm.contracts.orchestration import OrchestrationFinding, RepairAttempt
from auto_pm.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.core.mission_orchestrator import (
    MissionOrchestrator,
    MissionOrchestratorError,
)
from auto_pm.core.mission_service import MissionService, MissionServiceError
from auto_pm.core.work_registry_service import WorkRegistryError, WorkRegistryService


def _workspace(ctx: click.Context) -> Path:
    app_ctx: AppContext = ctx.find_root().obj
    return Path(app_ctx.workspace_root).resolve()


def _work_service(ctx: click.Context) -> WorkRegistryService:
    service = WorkRegistryService(_workspace(ctx))
    service.initialize(__version__)
    return service


def _execution_service(ctx: click.Context) -> ContinuityExecutionService:
    root = _workspace(ctx)
    WorkRegistryService(root).initialize(__version__)
    return ContinuityExecutionService(root)


def _mission_service(ctx: click.Context) -> MissionService:
    service = MissionService(_workspace(ctx))
    service.initialize(__version__)
    return service


def _orchestrator(ctx: click.Context) -> MissionOrchestrator:
    service = MissionOrchestrator(_workspace(ctx))
    service.initialize(__version__)
    return service


def _emit(item: BaseModel) -> None:
    click.echo(item.model_dump_json(indent=2))


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise click.ClickException(f"Git 事实采集失败: {message or 'unknown error'}")
    return result.stdout


def _git_snapshot(root: Path) -> tuple[str, tuple[str, ...]]:
    head = _git(root, "rev-parse", "HEAD").decode("ascii", errors="replace").strip()
    dirty: set[str] = set()
    commands = (
        ("diff", "--name-only", "-z"),
        ("diff", "--cached", "--name-only", "-z"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    )
    for command in commands:
        output = _git(root, *command).decode("utf-8", errors="replace")
        dirty.update(path.replace("\\", "/") for path in output.split("\0") if path)
    return head, tuple(sorted(dirty))


def _within(paths: tuple[str, ...], roots: tuple[str, ...]) -> list[str]:
    return [
        path
        for path in paths
        if any(path == root or path.startswith(f"{root.rstrip('/')}/") for root in roots)
    ]


@click.group(name="continuity")
def continuity_group() -> None:
    """Transactional continuity v2; legacy handoff remains read-only."""


@continuity_group.group(name="mission")
def mission_group() -> None:
    """Low-level Mission truth commands; PM-friendly orchestration is a later phase."""


@mission_group.command(name="create")
@click.option("--mission-id", required=True)
@click.option("--pid", "project_id", required=True)
@click.option("--title", required=True)
@click.option("--objective", required=True)
@click.option("--acceptance", "acceptance_criteria", multiple=True, required=True)
@click.option("--authority-json", required=True)
@click.option("--created-by", required=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def create_mission(
    ctx: click.Context,
    mission_id: str,
    project_id: str,
    title: str,
    objective: str,
    acceptance_criteria: tuple[str, ...],
    authority_json: str,
    created_by: str,
    idempotency_key: str,
) -> None:
    """Create a DRAFT Mission from an explicit, validated authority envelope."""
    try:
        authority = AuthorityEnvelope.model_validate(json.loads(authority_json))
        item = _mission_service(ctx).create(
            mission_id=mission_id,
            subject_project_id=project_id,
            title=title,
            objective=objective,
            acceptance_criteria=list(acceptance_criteria),
            authority=authority,
            created_by=created_by,
            idempotency_key=idempotency_key,
        )
    except (json.JSONDecodeError, ValidationError, MissionServiceError) as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@mission_group.command(name="show")
@click.option("--mission-id", required=True)
@click.pass_context
def show_mission(ctx: click.Context, mission_id: str) -> None:
    """Read one persisted Mission without changing it."""
    try:
        item = _mission_service(ctx).get(mission_id)
    except MissionServiceError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@mission_group.command(name="transition")
@click.option("--mission-id", required=True)
@click.option("--to", "new_state", type=click.Choice([item.value for item in MissionState]), required=True)
@click.option("--expected-version", type=click.IntRange(1), required=True)
@click.option("--root-work", "root_work_id")
@click.option("--idempotency-key", required=True)
@click.pass_context
def transition_mission(
    ctx: click.Context,
    mission_id: str,
    new_state: str,
    expected_version: int,
    root_work_id: str | None,
    idempotency_key: str,
) -> None:
    """Apply one legal Mission transition using optimistic locking."""
    try:
        item = _mission_service(ctx).transition(
            mission_id=mission_id,
            expected_version=expected_version,
            new_state=MissionState(new_state),
            root_work_id=root_work_id,
            idempotency_key=idempotency_key,
        )
    except MissionServiceError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@continuity_group.group(name="work")
def work_group() -> None:
    """Create, authorize, relate, and transition Work."""


@work_group.command(name="create")
@click.option("--work-id", required=True)
@click.option("--pid", "project_id", required=True)
@click.option("--kind", type=click.Choice([item.value for item in WorkKind]), required=True)
@click.option("--title", required=True)
@click.option("--owner", required=True)
@click.option("--scope", "scope_paths", multiple=True, required=True)
@click.option("--source-fingerprint", default="")
@click.option("--idempotency-key", required=True)
@click.option("--read-only", is_flag=True)
@click.pass_context
def create_work(
    ctx: click.Context,
    work_id: str,
    project_id: str,
    kind: str,
    title: str,
    owner: str,
    scope_paths: tuple[str, ...],
    source_fingerprint: str,
    idempotency_key: str,
    read_only: bool,
) -> None:
    """Create one logical Work item; write Work remains PLANNED until authorized."""
    try:
        if not source_fingerprint:
            source_fingerprint = f"git:{_git_snapshot(_workspace(ctx))[0]}"
        item = _work_service(ctx).create_work(
            work_id=work_id,
            subject_project_id=project_id,
            kind=WorkKind(kind),
            title=title,
            owner=owner,
            scope_paths=list(scope_paths),
            source_fingerprint=source_fingerprint,
            idempotency_key=idempotency_key,
            read_only=read_only,
        )
    except WorkRegistryError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@work_group.command(name="authorize")
@click.option("--work-id", required=True)
@click.option("--decision-id", required=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def authorize_work(ctx: click.Context, work_id: str, decision_id: str, idempotency_key: str) -> None:
    """Authorize PLANNED Work with a matching Decision package."""
    try:
        item = _work_service(ctx).authorize(work_id, decision_id, idempotency_key)
    except WorkRegistryError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@work_group.command(name="transition")
@click.option("--work-id", required=True)
@click.option("--to", "new_state", type=click.Choice([item.value for item in WorkState]), required=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def transition_work(ctx: click.Context, work_id: str, new_state: str, idempotency_key: str) -> None:
    """Apply one legal Work state transition."""
    try:
        item = _work_service(ctx).transition(work_id, WorkState(new_state), idempotency_key)
    except WorkRegistryError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@work_group.command(name="relate")
@click.option("--from-work", required=True)
@click.option("--to-work", required=True)
@click.option("--relation", required=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def relate_work(
    ctx: click.Context,
    from_work: str,
    to_work: str,
    relation: str,
    idempotency_key: str,
) -> None:
    """Create one typed relation between Work items."""
    try:
        _work_service(ctx).add_relation(from_work, to_work, relation, idempotency_key)
    except WorkRegistryError as error:
        raise click.ClickException(str(error)) from error
    click.echo('{"status":"ok"}')


@continuity_group.group(name="orchestration")
def orchestration_group() -> None:
    """Internal A3 finding routing; future UI projects only its safe outcomes."""


@orchestration_group.command(name="report-finding")
@click.option("--finding-id", required=True)
@click.option("--mission-id", required=True)
@click.option("--parent-work-id", required=True)
@click.option("--pid", "project_id", required=True)
@click.option("--kind", type=click.Choice([item.value for item in WorkKind]), required=True)
@click.option("--title", required=True)
@click.option("--summary", required=True)
@click.option("--scope", "scope_paths", multiple=True, required=True)
@click.option("--source-fingerprint", required=True)
@click.option("--business-line-reroute", is_flag=True)
@click.option("--execution-branch-change", is_flag=True)
@click.option("--physical-or-safety-decision", is_flag=True)
@click.option("--external-action", is_flag=True)
@click.pass_context
def report_finding(
    ctx: click.Context,
    finding_id: str,
    mission_id: str,
    parent_work_id: str,
    project_id: str,
    kind: str,
    title: str,
    summary: str,
    scope_paths: tuple[str, ...],
    source_fingerprint: str,
    business_line_reroute: bool,
    execution_branch_change: bool,
    physical_or_safety_decision: bool,
    external_action: bool,
) -> None:
    """Route a typed internal finding without creating a hidden parallel queue."""
    try:
        finding = OrchestrationFinding(
            finding_id=finding_id,
            mission_id=mission_id,
            parent_work_id=parent_work_id,
            subject_project_id=project_id,
            kind=WorkKind(kind),
            title=title,
            summary=summary,
            scope_paths=scope_paths,
            source_fingerprint=source_fingerprint,
            requires_business_line_reroute=business_line_reroute,
            requires_execution_branch_change=execution_branch_change,
            requires_physical_or_safety_decision=physical_or_safety_decision,
            requires_external_action=external_action,
        )
        _emit(_orchestrator(ctx).report_finding(finding))
    except (MissionOrchestratorError, ValidationError) as error:
        raise click.ClickException(str(error)) from error


@orchestration_group.command(name="report-repair")
@click.option("--attempt-id", required=True)
@click.option("--mission-id", required=True)
@click.option("--child-work-id", required=True)
@click.option("--result", type=click.Choice(["succeeded", "failed"]), required=True)
@click.option("--elapsed-seconds", type=click.IntRange(0), required=True)
@click.pass_context
def report_repair(
    ctx: click.Context,
    attempt_id: str,
    mission_id: str,
    child_work_id: str,
    result: str,
    elapsed_seconds: int,
) -> None:
    """Record an adapter-observed repair attempt against the explicit A3 budget."""
    try:
        attempt = RepairAttempt(
            attempt_id=attempt_id,
            mission_id=mission_id,
            child_work_id=child_work_id,
            succeeded=result == "succeeded",
            elapsed_seconds=elapsed_seconds,
        )
        _emit(_orchestrator(ctx).report_repair_attempt(attempt))
    except (MissionOrchestratorError, ValidationError) as error:
        raise click.ClickException(str(error)) from error


@continuity_group.group(name="run")
def run_group() -> None:
    """Start and transition execution Runs."""


@run_group.command(name="start")
@click.option("--run-id", required=True)
@click.option("--work-id", required=True)
@click.option("--executor", "executor_id", required=True)
@click.option("--adapter", required=True)
@click.option("--owned", "owned_paths", multiple=True, required=True)
@click.option("--declared-dirty", "declared_dirty_paths", multiple=True)
@click.option("--worktree", type=click.Path(exists=True, file_okay=False, path_type=Path), default=None)
@click.option("--lease-token", required=True)
@click.option("--lease-seconds", type=click.IntRange(60, 86_400), default=1800, show_default=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def start_run(
    ctx: click.Context,
    run_id: str,
    work_id: str,
    executor_id: str,
    adapter: str,
    owned_paths: tuple[str, ...],
    declared_dirty_paths: tuple[str, ...],
    worktree: Path | None,
    lease_token: str,
    lease_seconds: int,
    idempotency_key: str,
) -> None:
    """Start a Run after independently observing Git HEAD and owned-path dirtiness."""
    root = (worktree or _workspace(ctx)).resolve()
    git_head, all_dirty = _git_snapshot(root)
    owned = tuple(path.replace("\\", "/") for path in owned_paths)
    observed = _within(all_dirty, owned)
    try:
        item = _execution_service(ctx).start_run(
            run_id=run_id,
            work_id=work_id,
            executor_id=executor_id,
            adapter=adapter,
            owned_paths=list(owned),
            declared_dirty_paths=list(declared_dirty_paths),
            observed_dirty_paths=observed,
            git_head=git_head,
            worktree_path=str(root),
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            idempotency_key=idempotency_key,
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@run_group.command(name="transition")
@click.option("--run-id", required=True)
@click.option("--to", "new_state", type=click.Choice([item.value for item in RunState]), required=True)
@click.option("--owner", "owner_id", required=True)
@click.option("--lease-token", required=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def transition_run(
    ctx: click.Context,
    run_id: str,
    new_state: str,
    owner_id: str,
    lease_token: str,
    idempotency_key: str,
) -> None:
    """Apply one legal Run state transition under an active lease."""
    try:
        item = _execution_service(ctx).transition_run(
            run_id, RunState(new_state), owner_id, lease_token, idempotency_key
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@continuity_group.group(name="lease")
def lease_group() -> None:
    """Renew active Run ownership leases."""


@lease_group.command(name="renew")
@click.option("--run-id", required=True)
@click.option("--owner", "owner_id", required=True)
@click.option("--lease-token", required=True)
@click.option("--lease-seconds", type=click.IntRange(60, 86_400), default=1800, show_default=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def renew_lease(
    ctx: click.Context,
    run_id: str,
    owner_id: str,
    lease_token: str,
    lease_seconds: int,
    idempotency_key: str,
) -> None:
    """Renew a lease held by the same owner and token."""
    try:
        item = _execution_service(ctx).renew_lease(
            run_id, owner_id, lease_token, lease_seconds, idempotency_key
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@continuity_group.group(name="checkpoint")
def checkpoint_group() -> None:
    """Create immutable Run recovery checkpoints."""


@checkpoint_group.command(name="create")
@click.option("--checkpoint-id", required=True)
@click.option("--run-id", required=True)
@click.option("--owner", "owner_id", required=True)
@click.option("--lease-token", required=True)
@click.option("--summary", required=True)
@click.option("--evidence", multiple=True, required=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def create_checkpoint(
    ctx: click.Context,
    checkpoint_id: str,
    run_id: str,
    owner_id: str,
    lease_token: str,
    summary: str,
    evidence: tuple[str, ...],
    idempotency_key: str,
) -> None:
    """Checkpoint current Git baseline and dirty paths from the Run worktree."""
    service = _execution_service(ctx)
    try:
        run = service.get_run(run_id)
        git_head, all_dirty = _git_snapshot(Path(run.worktree_path))
        item = service.checkpoint(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            owner_id=owner_id,
            lease_token=lease_token,
            summary=summary,
            git_head=git_head,
            dirty_paths=_within(all_dirty, run.owned_paths),
            evidence=list(evidence),
            idempotency_key=idempotency_key,
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@continuity_group.group(name="handoff")
def handoff_v2_group() -> None:
    """Create and accept checkpoint-bound handoff.v2 snapshots."""


@handoff_v2_group.command(name="create")
@click.option("--handoff-id", required=True)
@click.option("--checkpoint-id", required=True)
@click.option("--from-owner", required=True)
@click.option("--to-owner", required=True)
@click.option("--lease-token", required=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def create_handoff(
    ctx: click.Context,
    handoff_id: str,
    checkpoint_id: str,
    from_owner: str,
    to_owner: str,
    lease_token: str,
    idempotency_key: str,
) -> None:
    """Create an immutable handoff.v2 from an active lease and checkpoint."""
    try:
        item = _execution_service(ctx).create_handoff(
            handoff_id=handoff_id,
            checkpoint_id=checkpoint_id,
            from_owner=from_owner,
            to_owner=to_owner,
            lease_token=lease_token,
            idempotency_key=idempotency_key,
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@handoff_v2_group.command(name="accept")
@click.option("--handoff-id", required=True)
@click.option("--receiver", "receiver_id", required=True)
@click.option("--new-lease-token", required=True)
@click.option("--lease-seconds", type=click.IntRange(60, 86_400), default=1800, show_default=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def accept_handoff(
    ctx: click.Context,
    handoff_id: str,
    receiver_id: str,
    new_lease_token: str,
    lease_seconds: int,
    idempotency_key: str,
) -> None:
    """Atomically transfer the Run lease to the named receiver."""
    try:
        item = _execution_service(ctx).accept_handoff(
            handoff_id=handoff_id,
            receiver_id=receiver_id,
            new_lease_token=new_lease_token,
            lease_seconds=lease_seconds,
            idempotency_key=idempotency_key,
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)
