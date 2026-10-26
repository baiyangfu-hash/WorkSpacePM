"""Card service reads remain inert and dispatch fails without canonical authority."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from auto_pm.application.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.application.core.implementation_card_service import (
    ImplementationCardError,
    ImplementationCardService,
)
from auto_pm.application.core.work_registry_service import WorkRegistryService
from auto_pm.contracts.continuity import CheckpointItem, RunState, WorkKind, WorkState
from auto_pm.contracts.execution_adapter import ExecutionStartEvidence
from auto_pm.contracts.implementation_card import (
    Boundaries,
    CardState,
    EvidenceMap,
    GateDefinition,
    ImplementationCard,
    Outcomes,
    StopLines,
)
from tests.git_support import git_out


def git(root: Path, *args: str) -> str:
    return git_out(root, *args)


@pytest.fixture
def governed_candidate(tmp_path: Path) -> tuple[Path, Path, str]:
    root = tmp_path / "control"
    root.mkdir()
    git(root, "init", "-q")
    (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8", errors="replace")
    (root / "plans").mkdir()
    (root / "plans" / "WBS.md").write_text(
        "# WBS\n| M2 | IN_PROGRESS |\n| M2-GOV-IC01 | implementation card |\n",
        encoding="utf-8", errors="replace",
    )
    (root / "project").mkdir()
    (root / "project" / "file.py").write_text("value = 1\n", encoding="utf-8", errors="replace")
    (root / "governance").mkdir()
    (root / "governance" / "evidence.md").write_text(
        "baseline evidence\n", encoding="utf-8", errors="replace"
    )
    (root / "other.txt").write_text("baseline other\n", encoding="utf-8", errors="replace")
    git(root, "add", ".gitignore", "plans/WBS.md", "project/file.py",
        "governance/evidence.md", "other.txt")
    git(root, "-c", "user.name=Card Test", "-c", "user.email=card@example.invalid",
        "commit", "-q", "-m", "base")
    base = git(root, "rev-parse", "HEAD")
    candidate = root / ".auto-pm" / "worktrees" / "candidate"
    candidate.parent.mkdir(parents=True)
    git(root, "worktree", "add", "-q", "-b", "codex/card-test", str(candidate), base)
    return root, candidate, base


def complete_draft(candidate: Path, base: str) -> ImplementationCard:
    return draft().model_copy(update={
        "base_commit": base, "worktree_path": str(candidate),
        "commit_evidence_paths": ("governance/evidence.md",),
        "problem_statement": "A production control gap needs a bounded card",
        "acceptance_criteria": ("Current evidence is checked",),
        "non_goals": ("No release changes",),
        "gates": (GateDefinition(name="pytest", cwd="project", argv=("python", "-m", "pytest"),
                                 coverage_targets=("project/file.py",)),),
        "outcomes": Outcomes(normal="Pass", small_problem="One repair",
                             non_blocking="Report", blocking="Stop"),
    })


def replace_card(service: ImplementationCardService, card: ImplementationCard) -> bytes:
    target = service.directory / f"{card.card_id}.json"
    payload = (card.model_dump_json(indent=2) + "\n").encode("utf-8")
    target.write_bytes(payload)
    return payload


def write_decision(root: Path, approved_files: tuple[str, ...] | None = None) -> None:
    decision_dir = root / ".auto-pm" / "decisions"
    decision_dir.mkdir(parents=True, exist_ok=True)
    (decision_dir / "DEC-20260928-8D72B667.json").write_text(json.dumps({
        "schema_version": "decision_package.v1", "decision_id": "DEC-20260928-8D72B667",
        "project_id": "SW-2026-008", "change_id": "CHG-SCPT-2026-338",
        "approved_scope": "MODULE", "approved_files": list(
            approved_files or ("project/file.py", "governance/evidence.md")
        ),
        "approver": "fubai", "approved_at": "2026-09-28T17:42:37+00:00",
        "decision_conclusion": "approved", "conditions": [], "metadata": {},
    }), encoding="utf-8", errors="replace")


def establish_authority(
    root: Path,
    candidate: Path,
    base: str,
    *,
    decision_paths: tuple[str, ...] = ("project/file.py", "governance/evidence.md"),
    work_paths: tuple[str, ...] = ("project/file.py", "governance/evidence.md"),
    run_paths: tuple[str, ...] = ("project/file.py", "governance/evidence.md"),
    running: bool = False,
) -> tuple[WorkRegistryService, ContinuityExecutionService]:
    write_decision(root, decision_paths)
    works = WorkRegistryService(root)
    works.initialize("test")
    works.create_work(
        work_id="WORK-1", subject_project_id="SW-2026-008", kind=WorkKind.GOVERNANCE,
        title="Card work", owner="card-agent", scope_paths=list(work_paths),
        source_fingerprint=f"git:{base}", idempotency_key="card-work-create",
    )
    works.authorize("WORK-1", "DEC-20260928-8D72B667", "card-work-authorize")
    works.transition("WORK-1", WorkState.IN_PROGRESS, "card-work-start")
    execution = ContinuityExecutionService(root)
    execution.start_run(
        run_id="RUN-1", work_id="WORK-1", executor_id="card-agent", adapter="codex",
        owned_paths=list(run_paths), declared_dirty_paths=[], observed_dirty_paths=[],
        git_head=base, worktree_path=str(candidate), lease_token="card-secret",
        lease_seconds=3600, idempotency_key="card-run-start",
    )
    if running:
        execution.record_start_evidence(
            run_id="RUN-1", owner_id="card-agent", lease_token="card-secret",
            evidence=ExecutionStartEvidence(
                process_id=1234, session_id="card-test-session", started_at=datetime.now(UTC)
            ),
            idempotency_key="card-run-started",
        )
    return works, execution


def outside_card_bytes(root: Path) -> dict[str, str]:
    card_dir = root / ".auto-pm" / "implementation-cards"
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file() and not path.is_relative_to(card_dir)
    }


def test_validate_checks_wbs_base_worktree_and_keeps_bytes(
    governed_candidate: tuple[Path, Path, str],
) -> None:
    root, candidate, base = governed_candidate
    service = ImplementationCardService(root)
    card = complete_draft(candidate, base)
    establish_authority(root, candidate, base)
    target, _ = service.create(card)
    original = target.read_bytes()
    outside_before = outside_card_bytes(root)
    assert service.validate(card.card_id).card_id == card.card_id
    assert target.read_bytes() == original
    assert outside_card_bytes(root) == outside_before
    for changed in (
        card.model_copy(update={"wbs_item_id": "UNKNOWN-ITEM"}),
        card.model_copy(update={"milestone_id": "UNKNOWN-MILESTONE"}),
        card.model_copy(update={"source_refs": ("WBS:plans/missing.md",)}),
        card.model_copy(update={"source_refs": ("WBS:plans/WBS.md", "FILE:plans/missing.md")}),
        card.model_copy(update={"base_commit": "b" * 40}),
        card.model_copy(update={"worktree_path": str(root)}),
        card.model_copy(update={"worktree_path": str(root / "rogue")}),
        card.model_copy(update={"gates": (GateDefinition(
            name="bad", cwd="project", argv=("python", "-m", "pytest"),
            coverage_targets=("other/file.py",)),)}),
    ):
        before = replace_card(service, changed)
        with pytest.raises((ImplementationCardError, ValueError)):
            service.validate(card.card_id)
        assert target.read_bytes() == before
    replace_card(service, card)
    assert service.validate(card.card_id).card_id == card.card_id


@pytest.mark.parametrize("missing_from", ["decision", "work", "run"])
def test_validate_rejects_authority_missing_commit_evidence_path(
    governed_candidate: tuple[Path, Path, str], missing_from: str,
) -> None:
    root, candidate, base = governed_candidate
    full = ("project/file.py", "governance/evidence.md")
    product_only = ("project/file.py",)
    decision_paths = product_only if missing_from == "decision" else full
    work_paths = product_only if missing_from in {"decision", "work"} else full
    run_paths = product_only if missing_from in {"decision", "work", "run"} else full
    establish_authority(
        root, candidate, base, decision_paths=decision_paths,
        work_paths=work_paths, run_paths=run_paths,
    )
    service = ImplementationCardService(root)
    card = complete_draft(candidate, base)
    target, _ = service.create(card)
    original = target.read_bytes()
    with pytest.raises(ImplementationCardError, match="scope|owned_paths|approved_files"):
        service.validate(card.card_id)
    assert target.read_bytes() == original


def draft() -> ImplementationCard:
    return ImplementationCard(
        card_id="CARD-TEST-002", project_id="SW-2026-008", intent_type="GOVERNANCE",
        wbs_item_id="M2-GOV-IC01", milestone_id="M2",
        source_refs=("WBS:plans/WBS.md",),
        problem_statement="TODO: define problem", base_commit="a" * 40,
        worktree_path="C:/candidate", owned_paths=("project/file.py",),
        commit_evidence_paths=("governance/evidence.md",),
        non_goals=("TODO: define exclusions",), gates=(),
        stop_lines=StopLines(max_runs=2, max_healing_attempts=1,
                             # The deadline is relative to now: a fixed date turned this fixture into a time bomb
                             # (baseline exception E-G1-1, failing from 2026-09-29).
                             deadline_utc=(datetime.now(UTC) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                             quota_stop_remaining_percent=30),
        outcomes=Outcomes(normal="TODO", small_problem="TODO", non_blocking="TODO", blocking="TODO"),
        evidence=EvidenceMap(decision_id="DEC-20260928-8D72B667", work_id="WORK-1",
                             run_id="RUN-1", checkpoint_id="TODO", final_commit="TODO"),
        boundaries=Boundaries(merge="SEPARATE_APPROVAL", push="SEPARATE_APPROVAL",
                              deploy="SEPARATE_APPROVAL", release="SEPARATE_APPROVAL"),
    )


def test_create_template_and_read_only_validation(tmp_path: Path) -> None:
    service = ImplementationCardService(tmp_path)
    json_path, markdown_path = service.create(draft())
    assert json_path.is_file() and markdown_path.is_file()
    assert "TODO" in markdown_path.read_text(encoding="utf-8", errors="replace")
    before = json_path.read_bytes()
    with pytest.raises(ValueError, match="incomplete"):
        service.validate("CARD-TEST-002")
    assert json_path.read_bytes() == before
    assert service.load("CARD-TEST-002").state is CardState.DRAFT


def test_dispatch_and_approval_fail_closed(tmp_path: Path) -> None:
    service = ImplementationCardService(tmp_path)
    service.create(draft())
    with pytest.raises(ValueError, match="incomplete"):
        service.approve("CARD-TEST-002", approver="fubai", approval_evidence="approved")
    with pytest.raises(ImplementationCardError, match="external approval"):
        service.dispatch("CARD-TEST-002")
    assert service.load("CARD-TEST-002").state is CardState.DRAFT


def test_external_approval_advances_two_legal_edges_without_decision_creation(
    governed_candidate: tuple[Path, Path, str],
) -> None:
    root, candidate, base = governed_candidate
    service = ImplementationCardService(root)
    service.create(complete_draft(candidate, base))
    with pytest.raises(ImplementationCardError, match="self-approve"):
        service.approve("CARD-TEST-002", approver="Codex agent",
                        approval_evidence="DEC-20260928-8D72B667")
    with pytest.raises(ImplementationCardError, match="unavailable"):
        service.approve("CARD-TEST-002", approver="fubai",
                        approval_evidence="DEC-20260928-8D72B667")
    write_decision(root)
    approved = service.approve("CARD-TEST-002", approver="fubai",
                               approval_evidence="DEC-20260928-8D72B667")
    assert approved.state is CardState.APPROVED
    assert approved.state_history == (CardState.DRAFT, CardState.REVIEWED, CardState.APPROVED)
    with pytest.raises(ImplementationCardError, match="canonical authority unavailable"):
        service.dispatch("CARD-TEST-002")
    assert service.load("CARD-TEST-002").state is CardState.APPROVED


def test_dispatch_rejects_an_expired_deadline_without_changing_the_card(
    governed_candidate: tuple[Path, Path, str],
) -> None:
    """TD-SW008-090 余项：截止时间已过就拒绝派发，卡仍停在 APPROVED，字节不变。

    与夹具改成相对时间配套：期限随真实时间漂移时测试不能静默变红，而过期这个分支要有自己的负向用例。
    """
    root, candidate, base = governed_candidate
    establish_authority(root, candidate, base, running=True)
    service = ImplementationCardService(root)
    card = complete_draft(candidate, base)
    expired = (datetime.now(UTC) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    card = card.model_copy(update={"stop_lines": card.stop_lines.model_copy(update={"deadline_utc": expired})})
    service.create(card)
    service.approve(card.card_id, approver="fubai", approval_evidence=card.evidence.decision_id)
    target = service.directory / f"{card.card_id}.json"
    original = target.read_bytes()
    outside_before = outside_card_bytes(root)
    with pytest.raises(ImplementationCardError, match="execution deadline has passed"):
        service.dispatch(card.card_id)
    assert service.load(card.card_id).state is CardState.APPROVED
    assert target.read_bytes() == original
    assert outside_card_bytes(root) == outside_before


def test_checkpoint_requires_gate_receipt_and_current_bytes(tmp_path: Path) -> None:
    source = tmp_path / "project" / "file.py"
    source.parent.mkdir()
    source.write_text("value = 1\n", encoding="utf-8", errors="replace")
    evidence_source = tmp_path / "governance" / "evidence.md"
    evidence_source.parent.mkdir()
    evidence_source.write_text("evidence\n", encoding="utf-8", errors="replace")
    gate = GateDefinition(name="pytest", cwd="project", argv=("python", "-m", "pytest"),
                          coverage_targets=("project/file.py",))
    card = draft().model_copy(update={"gates": (gate,)})
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    evidence_digest = hashlib.sha256(evidence_source.read_bytes()).hexdigest()
    receipt = ImplementationCardService._gate_evidence_key(gate.model_dump_json()) + "0"
    checkpoint = CheckpointItem(
        checkpoint_id="CP-1", run_id="RUN-1", sequence=1, summary="verified",
        git_head="a" * 40, dirty_paths=("project/file.py", "governance/evidence.md"),
        evidence=(f"sha256:project/file.py:{digest}",
                  f"sha256:governance/evidence.md:{evidence_digest}",
                  "healing_attempts:0", receipt),
        created_at="2026-09-28T18:00:00+00:00",
    )
    ImplementationCardService.validate_checkpoint_evidence(card, checkpoint, tmp_path)
    source.write_text("value = 2\n", encoding="utf-8", errors="replace")
    with pytest.raises(ImplementationCardError, match="stale"):
        ImplementationCardService.validate_checkpoint_evidence(card, checkpoint, tmp_path)
    source.write_text("value = 1\n", encoding="utf-8", errors="replace")
    missing_governance = checkpoint.model_copy(update={
        "evidence": tuple(item for item in checkpoint.evidence
                          if "governance/evidence.md" not in item)
    })
    with pytest.raises(ImplementationCardError, match="current-byte coverage"):
        ImplementationCardService.validate_checkpoint_evidence(card, missing_governance, tmp_path)
    missing_gate = checkpoint.model_copy(update={"evidence": checkpoint.evidence[:-1]})
    with pytest.raises(ImplementationCardError, match="gate receipts"):
        ImplementationCardService.validate_checkpoint_evidence(card, missing_gate, tmp_path)


def test_verify_binds_terminal_evidence_and_closes_atomically(
    governed_candidate: tuple[Path, Path, str],
) -> None:
    root, candidate, base = governed_candidate
    works, execution = establish_authority(root, candidate, base, running=True)
    service = ImplementationCardService(root)
    before_create = outside_card_bytes(root)
    card = complete_draft(candidate, base)
    service.create(card)
    assert outside_card_bytes(root) == before_create
    before_approve = outside_card_bytes(root)
    service.approve(card.card_id, approver="fubai", approval_evidence=card.evidence.decision_id)
    assert outside_card_bytes(root) == before_approve
    before_dispatch = outside_card_bytes(root)
    service.dispatch(card.card_id)
    assert outside_card_bytes(root) == before_dispatch
    source = candidate / "project" / "file.py"
    evidence_source = candidate / "governance" / "evidence.md"
    source.write_text("value = 2\n", encoding="utf-8", errors="replace")
    evidence_source.write_text("final evidence\n", encoding="utf-8", errors="replace")
    gate = card.gates[0]
    checkpoint = execution.checkpoint(
        checkpoint_id="CP-CARD-001", run_id="RUN-1", owner_id="card-agent",
        lease_token="card-secret", summary="current bytes and gate result", git_head=base,
        dirty_paths=["project/file.py", "governance/evidence.md"], evidence=[
            f"sha256:project/file.py:{hashlib.sha256(source.read_bytes()).hexdigest()}",
            f"sha256:governance/evidence.md:"
            f"{hashlib.sha256(evidence_source.read_bytes()).hexdigest()}",
            "healing_attempts:0",
            ImplementationCardService._gate_evidence_key(gate.model_dump_json()) + "0",
        ], idempotency_key="card-checkpoint",
    )
    git(candidate, "add", "project/file.py", "governance/evidence.md")
    git(candidate, "-c", "user.name=Card Test", "-c", "user.email=card@example.invalid",
        "commit", "-q", "-m", "candidate")
    final_commit = git(candidate, "rev-parse", "HEAD")
    execution.transition_run("RUN-1", RunState.VERIFYING, "card-agent", "card-secret", "card-run-verifying")
    execution.transition_run("RUN-1", RunState.SUCCEEDED, "card-agent", "card-secret", "card-run-succeeded")
    works.transition("WORK-1", WorkState.VERIFYING, "card-work-verifying")
    card_path = service.directory / f"{card.card_id}.json"
    before_failure = card_path.read_bytes()
    before_other = outside_card_bytes(root)
    with pytest.raises(ImplementationCardError):
        service.verify(card.card_id, checkpoint_id="CP-MISSING", final_commit=final_commit)
    assert card_path.read_bytes() == before_failure
    assert outside_card_bytes(root) == before_other
    with pytest.raises(ImplementationCardError):
        service.verify(card.card_id, checkpoint_id=checkpoint.checkpoint_id,
                       final_commit="f" * 40)
    assert card_path.read_bytes() == before_failure
    assert outside_card_bytes(root) == before_other
    closed = service.verify(card.card_id, checkpoint_id=checkpoint.checkpoint_id,
                            final_commit=final_commit)
    assert closed.state is CardState.CLOSED
    assert closed.evidence.checkpoint_id == checkpoint.checkpoint_id
    assert closed.evidence.final_commit == final_commit
    assert closed.state_history == (
        CardState.DRAFT, CardState.REVIEWED, CardState.APPROVED, CardState.DISPATCHED,
        CardState.VERIFYING, CardState.ACCEPTED, CardState.CLOSED,
    )
    assert service.load(card.card_id) == closed
    assert outside_card_bytes(root) == before_other


@pytest.mark.parametrize("variant", ["missing", "extra"])
def test_verify_rejects_non_exact_final_commit_without_mutating_card(
    governed_candidate: tuple[Path, Path, str], variant: str,
) -> None:
    root, candidate, base = governed_candidate
    works, execution = establish_authority(root, candidate, base, running=True)
    service = ImplementationCardService(root)
    card = complete_draft(candidate, base)
    service.create(card)
    service.approve(card.card_id, approver="fubai", approval_evidence=card.evidence.decision_id)
    service.dispatch(card.card_id)

    source = candidate / "project" / "file.py"
    evidence_source = candidate / "governance" / "evidence.md"
    source.write_text("value = 2\n", encoding="utf-8", errors="replace")
    dirty_paths = ["project/file.py"]
    staged_paths = ["project/file.py"]
    if variant == "extra":
        evidence_source.write_text("final evidence\n", encoding="utf-8", errors="replace")
        (candidate / "other.txt").write_text("unexpected\n", encoding="utf-8", errors="replace")
        dirty_paths.append("governance/evidence.md")
        staged_paths.extend(("governance/evidence.md", "other.txt"))
    gate = card.gates[0]
    checkpoint = execution.checkpoint(
        checkpoint_id="CP-CARD-EXACT", run_id="RUN-1", owner_id="card-agent",
        lease_token="card-secret", summary="exact path defense", git_head=base,
        dirty_paths=dirty_paths, evidence=[
            f"sha256:project/file.py:{hashlib.sha256(source.read_bytes()).hexdigest()}",
            f"sha256:governance/evidence.md:"
            f"{hashlib.sha256(evidence_source.read_bytes()).hexdigest()}",
            "healing_attempts:0",
            ImplementationCardService._gate_evidence_key(gate.model_dump_json()) + "0",
        ], idempotency_key="card-checkpoint-exact",
    )
    git(candidate, "add", *staged_paths)
    git(candidate, "-c", "user.name=Card Test", "-c", "user.email=card@example.invalid",
        "commit", "-q", "-m", variant)
    final_commit = git(candidate, "rev-parse", "HEAD")
    execution.transition_run(
        "RUN-1", RunState.VERIFYING, "card-agent", "card-secret", "card-run-verifying"
    )
    execution.transition_run(
        "RUN-1", RunState.SUCCEEDED, "card-agent", "card-secret", "card-run-succeeded"
    )
    works.transition("WORK-1", WorkState.VERIFYING, "card-work-verifying")
    card_path = service.directory / f"{card.card_id}.json"
    before = card_path.read_bytes()
    outside_before = outside_card_bytes(root)
    with pytest.raises(ImplementationCardError, match="exactly match authorized paths"):
        service.verify(card.card_id, checkpoint_id=checkpoint.checkpoint_id,
                       final_commit=final_commit)
    assert card_path.read_bytes() == before
    assert outside_card_bytes(root) == outside_before


def test_validate_and_dispatch_are_intercepted_by_the_same_precheck(
    governed_candidate: tuple[Path, Path, str],
) -> None:
    """M2-GOV-IC02 (card 027 §5.3, §6 G3): structured cards reuse the Markdown precheck rules."""

    from auto_pm.cli.__main__ import cli

    from auto_pm.ui.cli.implementation_card import command_tree_of

    tree = command_tree_of(cli)
    root, candidate, base = governed_candidate
    paths = ("project/file.py", "project/new.py", "governance/evidence.md")
    establish_authority(
        root, candidate, base, decision_paths=paths, work_paths=paths, run_paths=paths, running=True
    )
    service = ImplementationCardService(root)
    owned = ("project/file.py", "project/new.py")
    card = complete_draft(candidate, base).model_copy(update={
        "owned_paths": owned,
        "gates": (GateDefinition(name="pytest", cwd="project", argv=("python", "-m", "pytest"),
                                 coverage_targets=owned),),
    })
    target, _ = service.create(card)

    with pytest.raises(ImplementationCardError, match="precheck failed.*project/new.py"):
        service.validate(card.card_id, command_tree=tree)

    declared = card.model_copy(update={"planned_new_paths": ("project/new.py",)})
    replace_card(service, declared)
    assert service.validate(card.card_id, command_tree=tree).planned_new_paths == ("project/new.py",)

    unknown_option = declared.model_copy(update={"gates": (GateDefinition(
        name="doc", cwd="project", argv=("python", "main.py", "doc", "check", "--strict"),
        coverage_targets=owned),)})
    replace_card(service, unknown_option)
    service.approve(card.card_id, approver="fubai", approval_evidence=card.evidence.decision_id)
    approved = target.read_bytes()
    with pytest.raises(ImplementationCardError, match="--strict"):
        service.dispatch(card.card_id, command_tree=tree)
    assert target.read_bytes() == approved
