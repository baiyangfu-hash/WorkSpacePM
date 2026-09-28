"""Implementation card CLI; validation and verification never run gates or deploy."""

from __future__ import annotations

import json
from pathlib import Path

import click
from pydantic import ValidationError

from auto_pm.app_context import AppContext
from auto_pm.application.core.implementation_card_service import (
    ImplementationCardError,
    ImplementationCardService,
)
from auto_pm.contracts.implementation_card import (
    Boundaries,
    EvidenceMap,
    ImplementationCard,
    IntentType,
    Outcomes,
    StopLines,
)


def _service(ctx: click.Context) -> ImplementationCardService:
    app_ctx: AppContext = ctx.find_root().obj
    return ImplementationCardService(Path(app_ctx.control_root))


def _emit(value: object) -> None:
    click.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


@click.group(name="implementation-card")
def implementation_card_group() -> None:
    """Bounded implementation-card.v1 workflow."""


@implementation_card_group.command(name="create")
@click.option("--card-id", required=True)
@click.option("--pid", "project_id", required=True)
@click.option("--wbs-item-id", required=True)
@click.option("--milestone-id", required=True)
@click.option("--source-ref", "source_refs", multiple=True, required=True,
              help="Repeat WBS:<workspace-relative-path> once and FILE:<path> as needed")
@click.option("--intent", type=click.Choice([item.value for item in IntentType]), required=True)
@click.option("--base-commit", required=True)
@click.option("--worktree", required=True)
@click.option("--owned-path", "owned_paths", multiple=True, required=True)
@click.option("--commit-evidence-path", "commit_evidence_paths", multiple=True, required=True)
@click.option("--decision-id", required=True)
@click.option("--work-id", required=True)
@click.option("--run-id", required=True)
@click.option("--max-runs", type=click.IntRange(1, 20), required=True)
@click.option("--max-healing-attempts", type=click.IntRange(0, 20), required=True)
@click.option("--deadline-utc", required=True)
@click.option("--quota-stop-remaining-percent", type=click.IntRange(0, 100), required=True)
@click.pass_context
def create_card(
    ctx: click.Context, card_id: str, project_id: str, wbs_item_id: str,
    milestone_id: str, source_refs: tuple[str, ...], intent: str, base_commit: str,
    worktree: str, owned_paths: tuple[str, ...], commit_evidence_paths: tuple[str, ...],
    decision_id: str, work_id: str, run_id: str, max_runs: int,
    max_healing_attempts: int, deadline_utc: str, quota_stop_remaining_percent: int,
) -> None:
    """Create JSON and Markdown review artifacts with explicit TODO fields."""
    try:
        card = ImplementationCard(
            card_id=card_id, project_id=project_id, wbs_item_id=wbs_item_id,
            milestone_id=milestone_id, source_refs=source_refs,
            intent_type=IntentType(intent),
            problem_statement="" if intent == "FEATURE" else "TODO: problem statement",
            base_commit=base_commit, worktree_path=worktree, owned_paths=owned_paths,
            commit_evidence_paths=commit_evidence_paths,
            non_goals=("TODO: non-goals",), gates=(),
            stop_lines=StopLines(
                max_runs=max_runs, max_healing_attempts=max_healing_attempts,
                deadline_utc=deadline_utc,
                quota_stop_remaining_percent=quota_stop_remaining_percent,
            ),
            outcomes=Outcomes(normal="TODO", small_problem="TODO", non_blocking="TODO", blocking="TODO"),
            evidence=EvidenceMap(decision_id=decision_id, work_id=work_id, run_id=run_id,
                                 checkpoint_id="TODO", final_commit="TODO"),
            boundaries=Boundaries(merge="SEPARATE_APPROVAL", push="SEPARATE_APPROVAL",
                                  deploy="SEPARATE_APPROVAL", release="SEPARATE_APPROVAL"),
        )
        json_path, markdown_path = _service(ctx).create(card)
        _emit({"card": str(json_path), "review": str(markdown_path)})
    except (ImplementationCardError, ValidationError, OSError, ValueError) as error:
        raise click.ClickException(str(error)) from error


@implementation_card_group.command(name="validate")
@click.argument("card_id")
@click.pass_context
def validate_card(ctx: click.Context, card_id: str) -> None:
    """Validate without changing the card, governance store, or repository."""
    try:
        card = _service(ctx).validate(card_id)
        _emit({"card_id": card.card_id, "state": card.state.value, "valid": True})
    except (ImplementationCardError, ValueError) as error:
        raise click.ClickException(str(error)) from error


@implementation_card_group.command(name="approve")
@click.argument("card_id")
@click.option("--approver", required=True)
@click.option("--approval-evidence", required=True)
@click.pass_context
def approve_card(ctx: click.Context, card_id: str, approver: str, approval_evidence: str) -> None:
    """Attach external user approval to an already reviewed card."""
    try:
        card = _service(ctx).approve(card_id, approver=approver, approval_evidence=approval_evidence)
        _emit({"card_id": card.card_id, "state": card.state.value})
    except (ImplementationCardError, ValueError) as error:
        raise click.ClickException(str(error)) from error


@implementation_card_group.command(name="dispatch")
@click.argument("card_id")
@click.pass_context
def dispatch_card(ctx: click.Context, card_id: str) -> None:
    """Emit the checked execution package; do not launch an executor."""
    try:
        _emit(_service(ctx).dispatch(card_id))
    except (ImplementationCardError, ValueError, OSError) as error:
        raise click.ClickException(str(error)) from error


@implementation_card_group.command(name="verify")
@click.argument("card_id")
@click.option("--checkpoint-id", required=True)
@click.option("--final-commit", required=True)
@click.pass_context
def verify_card(ctx: click.Context, card_id: str, checkpoint_id: str, final_commit: str) -> None:
    """Validate current-byte terminal evidence; no merge or deployment."""
    try:
        card = _service(ctx).verify(card_id, checkpoint_id=checkpoint_id, final_commit=final_commit)
        _emit({"card_id": card.card_id, "state": card.state.value})
    except (ImplementationCardError, ValueError, OSError) as error:
        raise click.ClickException(str(error)) from error
