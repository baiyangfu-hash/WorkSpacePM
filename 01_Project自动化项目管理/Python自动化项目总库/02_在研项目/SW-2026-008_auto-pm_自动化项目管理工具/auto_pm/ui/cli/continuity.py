"""Platform-neutral Work/Run/Checkpoint/Handoff v2 CLI."""

from __future__ import annotations

import dataclasses
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import click
from pydantic import BaseModel, ValidationError

from auto_pm import __version__
from auto_pm.app_context import AppContext
from auto_pm.application.core.implementation_card_precheck import (
    format_findings,
    precheck_markdown_card,
    scopes_outside_card,
)
from auto_pm.contracts.continuity import RunState, WorkKind, WorkState
from auto_pm.contracts.declared_dirty import declared_dirty_problem
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.mission import AuthorityEnvelope, MissionState
from auto_pm.contracts.orchestration import OrchestrationFinding, RepairAttempt
from auto_pm.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.core.execution_adapter_service import (
    ExecutionDispatchError,
    ExecutionDispatchService,
)
from auto_pm.core.lease_handover_service import LeaseHandoverError, LeaseHandoverService
from auto_pm.core.mission_orchestrator import (
    MissionOrchestrator,
    MissionOrchestratorError,
)
from auto_pm.core.mission_service import MissionService, MissionServiceError
from auto_pm.core.work_registry_service import WorkRegistryError, WorkRegistryService
from auto_pm.core.worktree_policy_service import WorktreePolicyError, WorktreePolicyService
from auto_pm.infrastructure import lease_wallet, process_probe
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    authority_path_parts,
    clean_git_environment,
    require_governed_worktree,
)
from auto_pm.ui.cli.implementation_card import command_tree_from_click

_Command = TypeVar("_Command", bound=Callable[..., Any])

def _workspace(ctx: click.Context) -> Path:
    app_ctx: AppContext = ctx.find_root().obj
    return Path(app_ctx.workspace_root).resolve()


def _require_mutation_root(ctx: click.Context) -> None:
    try:
        WorktreePolicyService(_workspace(ctx)).require_control_root()
    except WorktreePolicyError as error:
        raise click.ClickException(str(error)) from error


def _governed_worktree(ctx: click.Context, path: Path) -> Path:
    try:
        return require_governed_worktree(_workspace(ctx), path)
    except ControlRootGuardError as error:
        raise click.ClickException(str(error)) from error


def _work_service(ctx: click.Context) -> WorkRegistryService:
    _require_mutation_root(ctx)
    service = WorkRegistryService(_workspace(ctx))
    service.initialize(__version__)
    return service


def _execution_service(ctx: click.Context) -> ContinuityExecutionService:
    _require_mutation_root(ctx)
    root = _workspace(ctx)
    WorkRegistryService(root).initialize(__version__)
    return ContinuityExecutionService(root)


def _handover(ctx: click.Context) -> LeaseHandoverService:
    _require_mutation_root(ctx)
    root = _workspace(ctx)
    WorkRegistryService(root).initialize(__version__)
    return LeaseHandoverService(root)


def _dispatch_service(ctx: click.Context) -> ExecutionDispatchService:
    _require_mutation_root(ctx)
    root = _workspace(ctx)
    WorkRegistryService(root).initialize(__version__)
    return ExecutionDispatchService(root)


def _mission_service(ctx: click.Context, *, mutating: bool) -> MissionService:
    service = MissionService(_workspace(ctx))
    if mutating:
        _require_mutation_root(ctx)
        service.initialize(__version__)
    return service


def _orchestrator(ctx: click.Context) -> MissionOrchestrator:
    _require_mutation_root(ctx)
    service = MissionOrchestrator(_workspace(ctx))
    service.initialize(__version__)
    return service


def _emit(item: BaseModel) -> None:
    click.echo(item.model_dump_json(indent=2))


def _secret_from_environment(variable_name: str) -> str:
    """Resolve a secret by name without accepting its value in argv."""

    if re.fullmatch(r"[A-Z_][A-Z0-9_]{0,127}", variable_name) is None:
        raise click.ClickException("lease token 环境变量名无效")
    value = os.environ.pop(variable_name, None)
    if value is None or value != value.strip() or not value:
        raise click.ClickException("lease token 安全秘密源不可用")
    if any(not character.isprintable() for character in value):
        raise click.ClickException("lease token 安全秘密源无效")
    return value


_ARGV_TOKEN_WARNING = (
    "警告：{option} 已弃用：口令会留在进程列表与 shell 历史里；请改用 {env_option}（环境变量名）"
    "或 --lease-wallet（本机钱包）"
)


def _lease_token(
    ctx: click.Context,
    *,
    argv_value: str | None,
    env_name: str | None,
    use_wallet: bool = False,
    run_id: str = "",
    owner_id: str = "",
    option: str = "--lease-token",
    env_option: str = "--lease-token-env",
) -> str:
    """Exactly one token source: an environment variable (preferred), the local wallet, or the deprecated argv option (TD-SW008-064)."""

    sources = sum(1 for given in (argv_value is not None, env_name is not None, use_wallet) if given)
    if sources != 1:
        wallet_hint = " 或 --lease-wallet" if use_wallet or run_id else ""
        raise click.UsageError(f"必须且只能给出一个口令来源：{env_option}{wallet_hint}（{option} 已弃用）")
    if env_name is not None:
        return _secret_from_environment(env_name)
    if use_wallet:
        try:
            return lease_wallet.load(_workspace(ctx), run_id=run_id, owner_id=owner_id)
        except lease_wallet.LeaseWalletError as error:
            raise click.ClickException(str(error)) from error
    assert argv_value is not None
    if sys.stderr.isatty():  # only an interactive user sees it; scripts and tests parse unchanged output
        click.echo(_ARGV_TOKEN_WARNING.format(option=option, env_option=env_option), err=True)
    return argv_value


def _holder_pid(value: str) -> int | None:
    """``auto`` = the long-lived process behind this call (the agent's shell or IDE), ``none`` = record nothing, or an explicit pid."""

    if value == "none":
        return None
    if value == "auto":
        return process_probe.holder_process_pid()
    if value.isdigit() and int(value) > 0:
        return int(value)
    raise click.BadParameter("--holder-pid 必须是 auto、none 或正整数")


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=False,
        env=clean_git_environment(),
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise click.ClickException(f"Git 事实采集失败: {message or 'unknown error'}")
    diagnostic = result.stderr.decode("utf-8", errors="replace").strip()
    if diagnostic:
        raise click.ClickException(f"Git 事实采集包含诊断: {diagnostic}")
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
        if any(
            authority_path_parts(path)[: len(authority_path_parts(root))]
            == authority_path_parts(root)
            for root in roots
        )
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
        item = _mission_service(ctx, mutating=True).create(
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
        item = _mission_service(ctx, mutating=False).get(mission_id)
    except MissionServiceError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@mission_group.command(name="transition")
@click.option("--mission-id", required=True)
@click.option(
    "--to", "new_state", type=click.Choice([item.value for item in MissionState]), required=True
)
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
        item = _mission_service(ctx, mutating=True).transition(
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
@click.option(
    "--card-file",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help=(
        "Implementation card that must pass the pre-start precheck; required for write Work. "
        "Every --scope must lie inside the card's path table."
    ),
)
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
    card_file: Path | None,
) -> None:
    """Create one logical Work item; write Work remains PLANNED until authorized.

    A write Work (no --read-only) must reference an implementation card that passes the
    precheck in this very process (no receipt file is trusted, no bypass switch exists), and
    its scope must stay inside the card's path table (card 027 §5.4).
    """
    try:
        _require_mutation_root(ctx)
        if not read_only:
            if card_file is None:
                raise click.ClickException(
                    "写入型 Work 必须提供 --card-file：实施卡须先通过开工前预检（只读 Work 可用 --read-only）"
                )
            if not card_file.is_file():
                raise click.ClickException(f"实施卡文件不存在: {card_file}")
            report = precheck_markdown_card(
                card_file,
                workspace_root=_workspace(ctx),
                command_tree=command_tree_from_click(ctx),
            )
            if not report.passed:
                raise click.ClickException(f"实施卡开工前预检失败: {format_findings(report)}")
            outside = scopes_outside_card(scope_paths, report)
            if outside:
                raise click.ClickException(
                    "Work scope 超出实施卡路径表: " + ", ".join(outside)
                )
            if not source_fingerprint:
                source_fingerprint = f"card:{report.card_sha256}"
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
def authorize_work(
    ctx: click.Context, work_id: str, decision_id: str, idempotency_key: str
) -> None:
    """Authorize PLANNED Work with a matching Decision package."""
    try:
        item = _work_service(ctx).authorize(work_id, decision_id, idempotency_key)
    except WorkRegistryError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@work_group.command(name="transition")
@click.option("--work-id", required=True)
@click.option(
    "--to", "new_state", type=click.Choice([item.value for item in WorkState]), required=True
)
@click.option("--idempotency-key", required=True)
@click.pass_context
def transition_work(ctx: click.Context, work_id: str, new_state: str, idempotency_key: str) -> None:
    """Apply one legal Work state transition."""
    try:
        item = _work_service(ctx).transition(work_id, WorkState(new_state), idempotency_key)
    except WorkRegistryError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@work_group.command(name="adjudication-evidence")
@click.option("--work-id", required=True)
@click.pass_context
def adjudication_evidence(ctx: click.Context, work_id: str) -> None:
    """Print the read-only facts a Decision must bind before adjudicating one BLOCKED Work."""

    try:
        evidence, original_sha256 = WorkRegistryService(_workspace(ctx)).adjudication_evidence(
            work_id
        )
    except WorkRegistryError as error:
        raise click.ClickException(str(error)) from error
    payload = dataclasses.asdict(evidence)
    payload["adjudicable"] = evidence.adjudicable
    payload["original_decision_sha256"] = original_sha256
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@work_group.command(name="adjudicate")
@click.option("--work-id", required=True)
@click.option("--expected-version", type=click.IntRange(min=1), required=True)
@click.option("--original-decision-sha256", required=True)
@click.option("--run-set-sha256", required=True)
@click.option("--lease-set-sha256", required=True)
@click.option("--recovery-run-id", required=True)
@click.option("--recovery-owner", "recovery_owner_id", required=True)
@click.option(
    "--recovery-lease-stdin",
    is_flag=True,
    required=True,
    help="Read the recovery lease token from standard input; tokens are never CLI arguments.",
)
@click.option("--decision-id", required=True)
@click.option("--outcome", type=click.Choice([WorkState.CANCELLED.value]), required=True)
@click.option("--reason", required=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def adjudicate_blocked_work(
    ctx: click.Context,
    work_id: str,
    expected_version: int,
    original_decision_sha256: str,
    run_set_sha256: str,
    lease_set_sha256: str,
    recovery_run_id: str,
    recovery_owner_id: str,
    recovery_lease_stdin: bool,
    decision_id: str,
    outcome: str,
    reason: str,
    idempotency_key: str,
) -> None:
    """Forward-cancel one historical BLOCKED Work under an exact adjudication Decision."""

    del recovery_lease_stdin
    recovery_lease_token = click.get_text_stream("stdin").read().strip()
    try:
        item = _work_service(ctx).adjudicate_blocked_work(
            target_work_id=work_id,
            expected_work_version=expected_version,
            expected_original_decision_sha256=original_decision_sha256,
            expected_run_set_sha256=run_set_sha256,
            expected_lease_set_sha256=lease_set_sha256,
            recovery_run_id=recovery_run_id,
            recovery_owner_id=recovery_owner_id,
            recovery_lease_token=recovery_lease_token,
            decision_id=decision_id,
            outcome=WorkState(outcome),
            reason=reason,
            idempotency_key=idempotency_key,
        )
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
@click.option(
    "--worktree", type=click.Path(exists=True, file_okay=False, path_type=Path), default=None
)
@click.option("--lease-token", default=None, help="已弃用：口令会留在进程列表里；请用 --lease-token-env 或 --lease-wallet")
@click.option("--lease-token-env", default=None, metavar="ENV_NAME", help="从该环境变量读取口令（读后即清除）")
@click.option(
    "--lease-wallet",
    is_flag=True,
    help="本命令自己生成口令并存入本机钱包（.auto-pm/cache/lease-wallet/），用户与 agent 都不必经手口令",
)
@click.option(
    "--holder-pid",
    default="auto",
    show_default=True,
    help="与 --lease-wallet 一起：记录持有者的长驻进程（auto=agent 宿主进程（IDE 或 agent 本身，跳过每条命令新开的 shell）；人在终端里手敲时是那个终端的 shell；none=不记录；或给出 pid），供日后回收判定",
)
@click.option("--lease-seconds", type=click.IntRange(60, 3_600), default=900, show_default=True)
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
    lease_token: str | None,
    lease_token_env: str | None,
    lease_wallet: bool,
    holder_pid: str,
    lease_seconds: int,
    idempotency_key: str,
) -> None:
    """Start a Run after independently observing Git HEAD and owned-path dirtiness."""
    _require_mutation_root(ctx)
    if lease_wallet:
        if lease_token is not None or lease_token_env is not None:
            raise click.UsageError("--lease-wallet 不能与 --lease-token 或 --lease-token-env 同用")
        handover = _handover(ctx)
        try:
            lease_token = handover.reusable_token(run_id, executor_id)
        except LeaseHandoverError as error:
            raise click.ClickException(str(error)) from error
    else:
        lease_token = _lease_token(ctx, argv_value=lease_token, env_name=lease_token_env)
    owned = tuple(path.replace("\\", "/") for path in owned_paths)
    declared = tuple(path.replace("\\", "/") for path in declared_dirty_paths)
    requested_worktree = worktree or _workspace(ctx)
    try:
        replay = ContinuityExecutionService(_workspace(ctx)).replay_run_start(
            run_id=run_id,
            work_id=work_id,
            executor_id=executor_id,
            adapter=adapter,
            owned_paths=list(owned),
            declared_dirty_paths=list(declared),
            worktree_path=str(requested_worktree),
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            idempotency_key=idempotency_key,
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    if replay is not None:
        if lease_wallet:
            _remember_started(ctx, replay.run_id, executor_id, lease_token, holder_pid, idempotency_key)
        _emit(replay)
        return
    problem = declared_dirty_problem(declared, scope=owned)
    if problem:
        raise click.ClickException(problem)
    root = _governed_worktree(ctx, requested_worktree)
    git_head, all_dirty = _git_snapshot(root)
    observed = _within(all_dirty, owned)
    try:
        item = _execution_service(ctx).start_run(
            run_id=run_id,
            work_id=work_id,
            executor_id=executor_id,
            adapter=adapter,
            owned_paths=list(owned),
            declared_dirty_paths=list(declared),
            observed_dirty_paths=observed,
            git_head=git_head,
            worktree_path=str(root),
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            idempotency_key=idempotency_key,
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    if lease_wallet:
        _remember_started(ctx, item.run_id, executor_id, lease_token, holder_pid, idempotency_key)
    _emit(item)


def _remember_started(
    ctx: click.Context, run_id: str, owner_id: str, lease_token: str, holder_pid: str, idempotency_key: str
) -> None:
    handover = _handover(ctx)
    try:
        handover.remember(run_id, owner_id, lease_token)
        handover.record_holder(run_id, owner_id, lease_token, _holder_pid(holder_pid), f"{idempotency_key}:holder")
    except LeaseHandoverError as error:
        raise click.ClickException(str(error)) from error


def _token_options(function: _Command) -> _Command:
    """The three token sources of a write made by the current holder (TD-SW008-064)."""

    function = click.option(
        "--lease-wallet", is_flag=True, help="从本机钱包读取本 Run 当前持有者的口令"
    )(function)
    function = click.option(
        "--lease-token-env", default=None, metavar="ENV_NAME", help="从该环境变量读取口令（读后即清除）"
    )(function)
    return click.option(
        "--lease-token", default=None, help="已弃用：口令会留在进程列表里；请用 --lease-token-env 或 --lease-wallet"
    )(function)


@run_group.command(name="transition")
@click.option("--run-id", required=True)
@click.option(
    "--to", "new_state", type=click.Choice([item.value for item in RunState]), required=True
)
@click.option("--owner", "owner_id", required=True)
@_token_options
@click.option("--idempotency-key", required=True)
@click.pass_context
def transition_run(
    ctx: click.Context,
    run_id: str,
    new_state: str,
    owner_id: str,
    lease_token: str | None,
    lease_token_env: str | None,
    lease_wallet: bool,
    idempotency_key: str,
) -> None:
    """Apply one legal Run state transition under an active lease."""
    lease_token = _lease_token(
        ctx, argv_value=lease_token, env_name=lease_token_env, use_wallet=lease_wallet, run_id=run_id, owner_id=owner_id
    )
    try:
        item = _execution_service(ctx).transition_run(
            run_id, RunState(new_state), owner_id, lease_token, idempotency_key
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@run_group.command(name="settle-expired")
@click.option("--target-run-id", required=True)
@click.option("--recovery-run-id", required=True)
@click.option("--recovery-owner", "recovery_owner_id", required=True)
@click.option(
    "--recovery-lease-token", default=None, help="已弃用：口令会留在进程列表里；请用 --recovery-lease-token-env"
)
@click.option("--recovery-lease-token-env", default=None, metavar="ENV_NAME", help="从该环境变量读取恢复 Run 的口令")
@click.option("--decision-id", required=True)
@click.option(
    "--outcome",
    type=click.Choice([RunState.CANCELLED.value]),
    required=True,
)
@click.option("--reason", required=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def settle_expired_run(
    ctx: click.Context,
    target_run_id: str,
    recovery_run_id: str,
    recovery_owner_id: str,
    recovery_lease_token: str | None,
    recovery_lease_token_env: str | None,
    decision_id: str,
    outcome: str,
    reason: str,
    idempotency_key: str,
) -> None:
    """Settle one abandoned Run through an explicit live recovery authority."""

    recovery_lease_token = _lease_token(
        ctx,
        argv_value=recovery_lease_token,
        env_name=recovery_lease_token_env,
        option="--recovery-lease-token",
        env_option="--recovery-lease-token-env",
    )
    try:
        item = _execution_service(ctx).settle_expired_run(
            target_run_id=target_run_id,
            recovery_run_id=recovery_run_id,
            recovery_owner_id=recovery_owner_id,
            recovery_lease_token=recovery_lease_token,
            decision_id=decision_id,
            outcome=RunState(outcome),
            reason=reason,
            idempotency_key=idempotency_key,
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@run_group.command(name="fence-terminal-lease")
@click.option("--target-run-id", required=True)
@click.option("--expected-settlement-event-id", required=True)
@click.option("--expected-target-lease-version", type=click.IntRange(min=1), required=True)
@click.option("--recovery-run-id", required=True)
@click.option("--recovery-owner", "recovery_owner_id", required=True)
@click.option(
    "--recovery-lease-stdin",
    is_flag=True,
    required=True,
    help="Read the recovery lease token from standard input; tokens are never CLI arguments.",
)
@click.option("--decision-id", required=True)
@click.option("--reason", required=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def fence_terminal_lease(
    ctx: click.Context,
    target_run_id: str,
    expected_settlement_event_id: str,
    expected_target_lease_version: int,
    recovery_run_id: str,
    recovery_owner_id: str,
    recovery_lease_stdin: bool,
    decision_id: str,
    reason: str,
    idempotency_key: str,
) -> None:
    """Fence one legacy terminal lease through an independently approved recovery Run."""

    del recovery_lease_stdin
    recovery_lease_token = click.get_text_stream("stdin").read().strip()
    try:
        item = _execution_service(ctx).fence_terminal_lease(
            target_run_id=target_run_id,
            expected_settlement_event_id=expected_settlement_event_id,
            expected_target_lease_version=expected_target_lease_version,
            recovery_run_id=recovery_run_id,
            recovery_owner_id=recovery_owner_id,
            recovery_lease_token=recovery_lease_token,
            decision_id=decision_id,
            reason=reason,
            idempotency_key=idempotency_key,
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@run_group.command(name="reconcile-terminal-lease")
@click.option("--target-run-id", required=True)
@click.option("--expected-terminal-event-id", required=True)
@click.option("--expected-target-lease-version", type=click.IntRange(min=1), required=True)
@click.option("--recovery-run-id", required=True)
@click.option("--recovery-owner", "recovery_owner_id", required=True)
@click.option(
    "--recovery-lease-stdin",
    is_flag=True,
    required=True,
    help="Read the recovery lease token from standard input; tokens are never CLI arguments.",
)
@click.option("--decision-id", required=True)
@click.option("--reason", required=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def reconcile_terminal_lease(
    ctx: click.Context,
    target_run_id: str,
    expected_terminal_event_id: str,
    expected_target_lease_version: int,
    recovery_run_id: str,
    recovery_owner_id: str,
    recovery_lease_stdin: bool,
    decision_id: str,
    reason: str,
    idempotency_key: str,
) -> None:
    """Release a lease omitted by an exact legacy v2 terminal transition."""

    del recovery_lease_stdin
    recovery_lease_token = click.get_text_stream("stdin").read().strip()
    try:
        item = _execution_service(ctx).reconcile_terminal_lease(
            target_run_id=target_run_id,
            expected_terminal_event_id=expected_terminal_event_id,
            expected_target_lease_version=expected_target_lease_version,
            recovery_run_id=recovery_run_id,
            recovery_owner_id=recovery_owner_id,
            recovery_lease_token=recovery_lease_token,
            decision_id=decision_id,
            reason=reason,
            idempotency_key=idempotency_key,
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@run_group.command(name="legacy-terminal-evidence")
@click.option("--run-id", required=True)
@click.pass_context
def legacy_terminal_evidence(ctx: click.Context, run_id: str) -> None:
    """Print the read-only facts a Decision must bind before fencing a legacy terminal lease."""

    try:
        evidence = ContinuityExecutionService(_workspace(ctx)).legacy_terminal_lease_evidence(run_id)
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    payload = dataclasses.asdict(evidence)
    payload["fenceable"] = evidence.fenceable
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@run_group.command(name="fence-legacy-terminal")
@click.option("--target-run-id", required=True)
@click.option("--expected-state", required=True)
@click.option("--expected-version", type=click.IntRange(min=1), required=True)
@click.option("--expected-lease-version", type=click.IntRange(min=1), required=True)
@click.option("--terminal-evidence-kind", required=True)
@click.option("--event-set-sha256", required=True)
@click.option("--checkpoint-set-sha256", required=True)
@click.option("--recovery-run-id", required=True)
@click.option("--recovery-owner", "recovery_owner_id", required=True)
@click.option(
    "--recovery-lease-stdin",
    is_flag=True,
    required=True,
    help="Read the recovery lease token from standard input; tokens are never CLI arguments.",
)
@click.option("--decision-id", required=True)
@click.option("--reason", required=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def fence_legacy_terminal(
    ctx: click.Context,
    target_run_id: str,
    expected_state: str,
    expected_version: int,
    expected_lease_version: int,
    terminal_evidence_kind: str,
    event_set_sha256: str,
    checkpoint_set_sha256: str,
    recovery_run_id: str,
    recovery_owner_id: str,
    recovery_lease_stdin: bool,
    decision_id: str,
    reason: str,
    idempotency_key: str,
) -> None:
    """Invalidate one expired legacy terminal lease token without rewriting Run history."""

    del recovery_lease_stdin
    recovery_lease_token = click.get_text_stream("stdin").read().strip()
    try:
        item = _execution_service(ctx).fence_legacy_terminal_lease(
            target_run_id=target_run_id,
            expected_run_state=expected_state,
            expected_run_version=expected_version,
            expected_lease_version=expected_lease_version,
            expected_terminal_evidence_kind=terminal_evidence_kind,
            expected_event_set_sha256=event_set_sha256,
            expected_checkpoint_set_sha256=checkpoint_set_sha256,
            recovery_run_id=recovery_run_id,
            recovery_owner_id=recovery_owner_id,
            recovery_lease_token=recovery_lease_token,
            decision_id=decision_id,
            reason=reason,
            idempotency_key=idempotency_key,
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@run_group.command(name="revoke-unstarted")
@click.option("--target-run-id", required=True)
@click.option("--recovery-run-id", required=True)
@click.option("--recovery-owner", "recovery_owner_id", required=True)
@click.option(
    "--recovery-lease-stdin",
    is_flag=True,
    required=True,
    help="Read the recovery lease token from standard input; tokens are never CLI arguments.",
)
@click.option("--decision-id", required=True)
@click.option("--reason", required=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def revoke_unstarted_run(
    ctx: click.Context,
    target_run_id: str,
    recovery_run_id: str,
    recovery_owner_id: str,
    recovery_lease_stdin: bool,
    decision_id: str,
    reason: str,
    idempotency_key: str,
) -> None:
    """Revoke a live Run only when its durable record has no Popen evidence."""

    del recovery_lease_stdin
    recovery_lease_token = click.get_text_stream("stdin").read().strip()
    try:
        item = _execution_service(ctx).revoke_unstarted_run(
            target_run_id=target_run_id,
            recovery_run_id=recovery_run_id,
            recovery_owner_id=recovery_owner_id,
            recovery_lease_token=recovery_lease_token,
            decision_id=decision_id,
            reason=reason,
            idempotency_key=idempotency_key,
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


RECLAIM_EXIT_CODES = {"ALLOW": 0, "REFUSE_LIVE_LEASE": 1, "REFUSE_PROCESS_ALIVE": 1, "PENDING": 3}


@run_group.command(name="reclaim")
@click.option("--run-id", required=True)
@click.option("--claimant", "claimant_id", required=True, help="接手的 agent 身份（将成为新持有者）")
@click.option("--reason", required=True, help="为什么要回收（写进事件）")
@click.option("--lease-seconds", type=click.IntRange(60, 3_600), default=900, show_default=True)
@click.option("--holder-pid", default="auto", show_default=True, help="接手后记录新持有者的长驻进程：auto、none 或 pid")
@click.pass_context
def reclaim_run(
    ctx: click.Context, run_id: str, claimant_id: str, reason: str, lease_seconds: int, holder_pid: str
) -> None:
    """Take over a started Run whose holder vanished: only after the lease expired (plus grace) and the holder's process is proven gone.

    Exit 0 = taken over (new token in the local wallet); 1 = refused (live lease or holder alive); 3 = PENDING (the holder's process
    cannot be identified: only the user's own `pm sign-risk` opens it).  A refusal and PENDING write nothing.
    """

    _require_mutation_root(ctx)
    service = _handover(ctx)
    try:
        outcome = service.reclaim(
            run_id=run_id, claimant_id=claimant_id, lease_seconds=lease_seconds, reason=reason, holder_pid=_holder_pid(holder_pid)
        )
    except LeaseHandoverError as error:
        raise click.ClickException(str(error)) from error
    payload: dict[str, object] = {
        "schema_version": "lease-reclaim-outcome.v1",
        "run_id": run_id,
        "decision": outcome.decision.value,
        "reason": outcome.reason,
        "exit_path": outcome.exit_path,
        "holder_owner_id": outcome.holder_owner_id,
        "lease_expires_at": outcome.lease_expires_at,
        "lease_expires_local": ContinuityStore.local_time_text(outcome.lease_expires_at),
        "process_verdict": outcome.process_verdict.value if outcome.process_verdict else None,
        "wait_seconds": outcome.wait_seconds,
    }
    if outcome.lease is not None:
        payload.update(
            owner_id=outcome.lease.owner_id,
            epoch=outcome.lease.epoch,
            expires_at=outcome.lease.expires_at,
            wallet_path=outcome.lease.wallet_path,
            holder_process_recorded=outcome.lease.holder_process_recorded,
        )
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    ctx.exit(RECLAIM_EXIT_CODES[outcome.decision.value])


@continuity_group.group(name="dispatch")
def dispatch_group() -> None:
    """Prepare local, secret-free execution packages without provider side effects."""


@dispatch_group.command(name="prepare")
@click.option("--mission-id", required=True)
@click.option("--work-id", required=True)
@click.option("--run-id", required=True)
@click.option(
    "--adapter",
    type=click.Choice([item.value for item in ExecutionAdapterKind]),
    required=True,
)
@click.option("--executor", "executor_id", required=True)
@click.option("--lease-token", default=None, help="已弃用：口令会留在进程列表里；请用 --lease-token-env")
@click.option("--lease-token-env", default=None, metavar="ENV_NAME", help="从该环境变量读取口令（读后即清除）")
@click.option("--lease-seconds", type=click.IntRange(60, 3_600), default=900, show_default=True)
@click.option("--stack", default=None, help="已验证项目技术栈；省略时从 Workspace Registry 读取。")
@click.option("--force-isolation", is_flag=True, help="即使控制工作树干净也创建隔离分支。")
@click.option("--idempotency-key", required=True)
@click.pass_context
def prepare_dispatch(
    ctx: click.Context,
    mission_id: str,
    work_id: str,
    run_id: str,
    adapter: str,
    executor_id: str,
    lease_token: str | None,
    lease_token_env: str | None,
    lease_seconds: int,
    stack: str | None,
    force_isolation: bool,
    idempotency_key: str,
) -> None:
    """Allocate a local Run and emit only a desensitized PREPARED receipt."""

    lease_token = _lease_token(ctx, argv_value=lease_token, env_name=lease_token_env)
    try:
        mission = _mission_service(ctx, mutating=False).get(mission_id)
        result = _dispatch_service(ctx).prepare(
            mission=mission,
            work_id=work_id,
            run_id=run_id,
            adapter=ExecutionAdapterKind(adapter),
            executor_id=executor_id,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
            stack=stack,
            force_isolation=force_isolation,
            idempotency_key=idempotency_key,
        )
    except (ExecutionDispatchError, MissionServiceError) as error:
        raise click.ClickException(str(error)) from error
    _emit(result.receipt)


@continuity_group.group(name="lease")
def lease_group() -> None:
    """Renew active Run ownership leases."""


@lease_group.command(name="renew")
@click.option("--run-id", required=True)
@click.option("--owner", "owner_id", required=True)
@click.option("--lease-token-env", default=None, metavar="ENV_NAME")
@click.option("--lease-wallet", is_flag=True, help="从本机钱包读取本 Run 当前持有者的口令")
@click.option("--expected-version", type=click.IntRange(min=1), required=True)
@click.option("--lease-seconds", type=click.IntRange(60, 3_600), default=900, show_default=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def renew_lease(
    ctx: click.Context,
    run_id: str,
    owner_id: str,
    lease_token_env: str | None,
    lease_wallet: bool,
    expected_version: int,
    lease_seconds: int,
    idempotency_key: str,
) -> None:
    """Renew a lease held by the same owner and token."""
    if (lease_token_env is None) == (not lease_wallet):
        raise click.UsageError("必须且只能给出一个口令来源：--lease-token-env 或 --lease-wallet")
    lease_token = _lease_token(
        ctx, argv_value=None, env_name=lease_token_env, use_wallet=lease_wallet, run_id=run_id, owner_id=owner_id
    )
    try:
        item = _execution_service(ctx).renew_lease(
            run_id,
            owner_id,
            lease_token,
            lease_seconds,
            idempotency_key,
            expected_version=expected_version,
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(str(error)) from error
    _emit(item)


@lease_group.command(name="record-holder")
@click.option("--run-id", required=True)
@click.option("--owner", "owner_id", required=True)
@_token_options
@click.option("--holder-pid", default="auto", show_default=True, help="持有者的长驻进程：auto（agent 宿主进程，跳过每条命令新开的 shell；人手敲时是终端的 shell）或 pid")
@click.option("--idempotency-key", required=True)
@click.pass_context
def record_holder(
    ctx: click.Context,
    run_id: str,
    owner_id: str,
    lease_token: str | None,
    lease_token_env: str | None,
    lease_wallet: bool,
    holder_pid: str,
    idempotency_key: str,
) -> None:
    """Record the holder's long-lived process (for example a renewal loop) so that a later reclaim can prove it gone."""

    lease_token = _lease_token(
        ctx, argv_value=lease_token, env_name=lease_token_env, use_wallet=lease_wallet, run_id=run_id, owner_id=owner_id
    )
    _require_mutation_root(ctx)
    pid = _holder_pid(holder_pid)
    if pid is None:
        raise click.ClickException("找不到可记录的持有者进程；请用 --holder-pid 给出 pid")
    try:
        recorded = _handover(ctx).record_holder(run_id, owner_id, lease_token, pid, idempotency_key)
    except LeaseHandoverError as error:
        raise click.ClickException(str(error)) from error
    if not recorded:
        raise click.ClickException(f"进程 {pid} 不在运行或读不到启动时间，未记录")
    click.echo(json.dumps({"run_id": run_id, "owner_id": owner_id, "holder_pid": pid, "recorded": True}, ensure_ascii=False))


@continuity_group.group(name="checkpoint")
def checkpoint_group() -> None:
    """Create immutable Run recovery checkpoints."""


@checkpoint_group.command(name="create")
@click.option("--checkpoint-id", required=True)
@click.option("--run-id", required=True)
@click.option("--owner", "owner_id", required=True)
@_token_options
@click.option("--summary", required=True)
@click.option("--evidence", multiple=True, required=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def create_checkpoint(
    ctx: click.Context,
    checkpoint_id: str,
    run_id: str,
    owner_id: str,
    lease_token: str | None,
    lease_token_env: str | None,
    lease_wallet: bool,
    summary: str,
    evidence: tuple[str, ...],
    idempotency_key: str,
) -> None:
    """Checkpoint current Git baseline and dirty paths from the Run worktree."""
    lease_token = _lease_token(
        ctx, argv_value=lease_token, env_name=lease_token_env, use_wallet=lease_wallet, run_id=run_id, owner_id=owner_id
    )
    service = _execution_service(ctx)
    try:
        run = service.get_run(run_id)
        run_worktree = _governed_worktree(ctx, Path(run.worktree_path))
        git_head, all_dirty = _git_snapshot(run_worktree)
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
@click.option("--lease-token", default=None, help="已弃用：口令会留在进程列表里；请用 --lease-token-env（或直接用 pm handoff）")
@click.option("--lease-token-env", default=None, metavar="ENV_NAME", help="从该环境变量读取口令（读后即清除）")
@click.option("--idempotency-key", required=True)
@click.pass_context
def create_handoff(
    ctx: click.Context,
    handoff_id: str,
    checkpoint_id: str,
    from_owner: str,
    to_owner: str,
    lease_token: str | None,
    lease_token_env: str | None,
    idempotency_key: str,
) -> None:
    """Create an immutable handoff.v2 from an active lease and checkpoint."""
    lease_token = _lease_token(ctx, argv_value=lease_token, env_name=lease_token_env)
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
@click.option(
    "--new-lease-token", default=None, help="已弃用：口令会留在进程列表里；请用 --new-lease-token-env（或直接用 pm takeover）"
)
@click.option("--new-lease-token-env", default=None, metavar="ENV_NAME", help="从该环境变量读取新口令（读后即清除）")
@click.option("--lease-seconds", type=click.IntRange(60, 3_600), default=900, show_default=True)
@click.option("--idempotency-key", required=True)
@click.pass_context
def accept_handoff(
    ctx: click.Context,
    handoff_id: str,
    receiver_id: str,
    new_lease_token: str | None,
    new_lease_token_env: str | None,
    lease_seconds: int,
    idempotency_key: str,
) -> None:
    """Atomically transfer the Run lease to the named receiver."""
    new_lease_token = _lease_token(
        ctx,
        argv_value=new_lease_token,
        env_name=new_lease_token_env,
        option="--new-lease-token",
        env_option="--new-lease-token-env",
    )
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
