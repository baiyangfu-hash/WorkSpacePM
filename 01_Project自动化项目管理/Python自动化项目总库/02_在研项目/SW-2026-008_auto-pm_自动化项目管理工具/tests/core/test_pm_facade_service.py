"""Behaviour tests for the state-free PM Facade."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.core.mission_service import MissionService, MissionServiceError
from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.core.work_registry_service import WorkRegistryError, WorkRegistryService

from auto_pm.application.core.evidence_collection_service import (
    EvidenceCollectionService,
    PythonQualityGate,
    PythonQualityReceipt,
    _quality_receipt_hash,
)
from auto_pm.contracts.continuity import RunState, WorkKind, WorkState
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind, WorktreeMode
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope, MissionState
from auto_pm.contracts.pm_facade import (
    PlanningExecutionGrant,
    PlanningScopeCard,
    PmConfirmationKind,
    PmIntent,
)
from auto_pm.domain.change.decision_service import DecisionError
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


def _git_root(root: Path) -> None:
    subprocess.run(
        ["git", "-C", str(root), "init"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _authority(now: datetime) -> AuthorityEnvelope:
    return AuthorityEnvelope(
        envelope_id="AUTH-PM-FACADE-001",
        subject_project_id="SW-TEST-001",
        change_id="CHG-SCPT-2026-201",
        decision_id="DEC-20260910-C518CA55",
        scope_paths=("pm.py",),
        valid_from=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=1),
        audit=AuthorityAudit(
            created_by="Codex PM",
            created_at=now,
            approved_by="fubai",
            approved_at=now,
            source_fingerprint=f"sha256:{'b' * 64}",
        ),
    )


def _setup(root: Path) -> tuple[MissionService, PmFacadeService]:
    _git_root(root)
    now = datetime.now(UTC)
    works = WorkRegistryService(root)
    works.initialize("test")
    works.create_work(
        work_id="WORK-PM-001",
        subject_project_id="SW-TEST-001",
        kind=WorkKind.WBS,
        title="Facade root work",
        owner="Codex",
        scope_paths=["pm.py"],
        source_fingerprint="sha256:test",
        idempotency_key="work-create",
        read_only=True,
    )
    missions = MissionService(root)
    missions.initialize("test")
    missions.create(
        mission_id="MISSION-PM-001",
        subject_project_id="SW-TEST-001",
        title="Friendly PM",
        objective="Hide internal task routing from the user.",
        acceptance_criteria=["User sees only confirmation cards."],
        authority=_authority(now),
        created_by="Codex PM",
        idempotency_key="mission-create",
        root_work_id="WORK-PM-001",
    )
    return missions, PmFacadeService(root)


def _commit_baseline(root: Path) -> str:
    subprocess.run(
        ["git", "-C", str(root), "add", "."],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=C04 Test",
            "-c",
            "user.email=c04@example.invalid",
            "commit",
            "-m",
            "C04 baseline",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()


def _verified_acceptance_ready(
    root: Path,
) -> tuple[MissionService, PmFacadeService, ContinuityExecutionService]:
    """Build one latest, content-bound C03 checkpoint using real quality gates."""

    missions, facade = _setup(root)
    (root / ".gitignore").write_text(
        ".auto-pm/\n__pycache__/\n.pytest_cache/\n.mypy_cache/\n.ruff_cache/\n",
        encoding="utf-8",
    )
    project = root / "project"
    source = project / "auto_pm" / "core" / "target.py"
    source.parent.mkdir(parents=True)
    (project / "auto_pm" / "__init__.py").write_text("", encoding="utf-8")
    (project / "auto_pm" / "core" / "__init__.py").write_text("", encoding="utf-8")
    source.write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
    test_path = project / "tests" / "core" / "test_continuity_execution_service.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text(
        "from auto_pm.core.target import value\n\n\n"
        "def test_append_verified_checkpoint_profile_target() -> None:\n"
        "    assert value() == 1\n",
        encoding="utf-8",
    )
    (project / "pyproject.toml").write_text(
        "[tool.ruff]\nline-length = 88\n\n[tool.mypy]\nfiles = [\"auto_pm\"]\n",
        encoding="utf-8",
    )
    git_head = _commit_baseline(root)
    scope_paths = [
        "project/auto_pm/core/target.py",
        "project/tests/core/test_continuity_execution_service.py",
    ]
    works = WorkRegistryService(root)
    works.create_work(
        work_id="WORK-C04-001",
        subject_project_id="SW-C04-001",
        kind=WorkKind.TEST,
        title="C04 verified acceptance root work",
        owner="Codex",
        scope_paths=scope_paths,
        source_fingerprint="sha256:c04",
        idempotency_key="c04-work-create",
        read_only=True,
    )
    now = datetime.now(UTC)
    missions.create(
        mission_id="MISSION-C04-001",
        subject_project_id="SW-C04-001",
        title="C04 verified acceptance",
        objective="Bind acceptance to a current verified checkpoint.",
        acceptance_criteria=["Only the latest passing checkpoint can be accepted."],
        authority=_authority(now).model_copy(
            update={
                "subject_project_id": "SW-C04-001",
                "scope_paths": tuple(scope_paths),
            }
        ),
        created_by="Codex PM",
        idempotency_key="c04-mission-create",
        root_work_id="WORK-C04-001",
    )
    facade.plan("MISSION-C04-001")
    facade.approve("MISSION-C04-001", "WORK-C04-001")
    execution = ContinuityExecutionService(root, store=facade._store)
    execution.start_run(
        run_id="RUN-C04-001",
        work_id="WORK-C04-001",
        executor_id="c04-test",
        adapter="test",
        owned_paths=scope_paths,
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head=git_head,
        worktree_path=str(root),
        lease_token="c04-test-lease",
        lease_seconds=900,
        idempotency_key="c04-run-create",
    )
    execution.transition_run(
        "RUN-C04-001",
        RunState.RUNNING,
        "c04-test",
        "c04-test-lease",
        "c04-run-start",
    )
    run = facade._store.get_run("RUN-C04-001")
    collector = EvidenceCollectionService(root)
    collection = collector.collect(run)
    gates = (
        PythonQualityGate(
            "pytest",
            (
                sys.executable,
                "-m",
                "pytest",
                "-o",
                "addopts=",
                "-p",
                "no:cacheprovider",
                "-k",
                "append_verified_checkpoint",
                "tests/core/test_continuity_execution_service.py",
            ),
            str(project.resolve()),
            0,
            "c04-test-pytest",
            "verified by the C03 checkpoint contract suite",
        ),
        PythonQualityGate(
            "ruff", (sys.executable, "-m", "ruff", "check"), str(project.resolve()), 0,
            "c04-test-ruff", "verified by the C03 checkpoint contract suite",
        ),
        PythonQualityGate(
            "mypy", (sys.executable, "-m", "mypy"), str(project.resolve()), 0,
            "c04-test-mypy", "verified by the C03 checkpoint contract suite",
        ),
    )
    receipt = PythonQualityReceipt(
        run_id=run.run_id,
        baseline_git_head=run.git_head,
        candidate_path=collection.worktree_path,
        project_root=str(project.resolve()),
        evidence_hash=collection.content_hash,
        gates=gates,
        evidence_current=True,
        evidence_error=None,
        content_hash=_quality_receipt_hash(
            run_id=run.run_id,
            baseline_git_head=run.git_head,
            candidate_path=collection.worktree_path,
            project_root=str(project.resolve()),
            evidence_hash=collection.content_hash,
            gates=gates,
            evidence_current=True,
            evidence_error=None,
        ),
    )
    execution.checkpoint(
        checkpoint_id="CP-C04-001",
        run_id="RUN-C04-001",
        owner_id="c04-test",
        lease_token="c04-test-lease",
        summary="verified C03 checkpoint evidence",
        git_head=collection.git_head,
        dirty_paths=[],
        evidence=[collector.build_checkpoint_evidence(collection, receipt)],
        idempotency_key="c04-checkpoint",
    )
    execution.transition_run(
        "RUN-C04-001",
        RunState.VERIFYING,
        "c04-test",
        "c04-test-lease",
        "c04-run-verifying",
    )
    return missions, facade, execution


def _planning_facade(root: Path) -> tuple[PmFacadeService, Path]:
    _git_root(root)
    database = root / ".auto-pm" / "p03-planning-draft-test.db"
    store = ContinuityStore(root, database)
    store.initialize("2026-09-14T00:00:00+00:00", "test")
    return PmFacadeService(root, store=store), database


def _planning_intent(*, objective: str = "Persist a pre-authorization plan.") -> PmIntent:
    return PmIntent(
        request_id="REQ-P03-001",
        subject_project_id="SW-TEST-001",
        objective=objective,
        acceptance_criteria=("Replay must be idempotent.",),
    )


def _p10_facade(root: Path) -> tuple[PmFacadeService, Path, ChangeService]:
    """Build one isolated planning facade without creating authority objects."""
    _git_root(root)
    project = root / "SW-TEST-001"
    (project / "04_监控" / "01_变更管理" / "01_变更单").mkdir(parents=True)
    (project / "04_监控" / "01_变更管理" / "01_版本变更台帐.md").write_text(
        "# 台帐\n\n| 序号 | 变更编号 | 描述 |\n|---|---|---|\n", encoding="utf-8"
    )
    (root / "specs").mkdir()
    (root / "specs" / "python.md").write_text("python", encoding="utf-8")
    (root / "specs" / "plc.md").write_text("plc", encoding="utf-8")
    registry = root / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"specs": {
        "DEV-TEST": {"domain": "python", "lifecycle": "stable", "canonical_path": "specs/python.md", "version": "V1"},
        "LSP-TEST": {"domain": "plc", "lifecycle": "active", "canonical_path": "specs/plc.md", "version": "V1"},
    }}), encoding="utf-8")
    workspace = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    workspace.parent.mkdir(parents=True)
    workspace.write_text(json.dumps({"schema_version": "workspace-registry.v1", "projects": [{"project_id": "SW-TEST-001", "project_root": "SW-TEST-001", "development_root": "SW-TEST-001"}]}), encoding="utf-8")
    database = root / ".auto-pm" / "p10-test.db"
    store = ContinuityStore(root, database)
    store.initialize("2026-09-14T00:00:00+00:00", "test")
    changes = ChangeService(str(root))
    facade = PmFacadeService(root, store=store, change_service=changes)
    return facade, database, changes


def _p10_card(root: Path) -> tuple[PmFacadeService, PlanningScopeCard, Path]:
    """Build one approved, isolated PlanningScopeCard for fault-retry checks."""
    facade, database, changes = _p10_facade(root)
    card = facade.create_planning_scope_card(_planning_intent(), scope_paths=("auto_pm/example.py",), risks=("retry",), non_goals=("no execution",))
    for state in ("submitted", "under_review", "approved"):
        changes.transition_status(card.change_id, state, approver="fubai", comment="human", project_id="SW-TEST-001")
    return facade, card, database


def test_approved_card_cold_start_recovers_one_exact_mission_and_root_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facade, _database, changes = _p10_facade(tmp_path)
    grant = PlanningExecutionGrant(
        adapter=ExecutionAdapterKind.CODEX,
        approved_model="gpt-approved",
        required_worktree_mode=WorktreeMode.ISOLATED,
        declared_dirty_paths=("auto_pm/example.py",),
    )
    card = facade.create_planning_scope_card(
        _planning_intent(),
        scope_paths=("auto_pm/example.py",),
        risks=("dispatch drift",),
        non_goals=("no model startup",),
        execution_grant=grant,
    )
    for state in ("submitted", "under_review", "approved"):
        changes.transition_status(
            card.change_id,
            state,
            approver="fubai",
            comment="human",
            project_id="SW-TEST-001",
        )
    decision = facade.approve_planning_scope_card(
        card,
        expected_plan_hash=card.plan_hash,
        approver="fubai",
        approval_evidence_ref="user-confirmation:E08A-001",
    )
    first_mission = facade.materialize_planning_mission(card)
    first_work = facade.create_planning_work(card)
    second_mission = facade.materialize_planning_mission(card)
    second_work = facade.create_planning_work(card)

    assert first_mission == second_mission
    assert first_work == second_work
    assert decision.metadata == {
        "planning_approval": {
            "schema_version": "planning-approval.v2",
            "plan_hash": card.plan_hash,
            "approval_evidence_ref": "user-confirmation:E08A-001",
            "request_id": card.request_id,
            "execution_grant": grant.model_dump(mode="json"),
        }
    }
    assert first_mission.authority.routing.allowed_execution_adapters == frozenset(
        {ExecutionAdapterKind.CODEX}
    )
    assert first_mission.authority.routing.approved_model == "gpt-approved"
    assert first_mission.authority.routing.required_worktree_mode is WorktreeMode.ISOLATED
    assert first_mission.authority.routing.declared_dirty_paths == ("auto_pm/example.py",)

    drifted = card.model_copy(
        update={
            "execution_grant": grant.model_copy(update={"approved_model": "gpt-drifted"})
        }
    )
    with pytest.raises(PmFacadeError, match="plan_hash"):
        facade.materialize_planning_mission(drifted)
    assert facade._store.list_missions("SW-TEST-001", include_terminal=True) == (first_mission,)
    assert facade._store.list_works("SW-TEST-001", include_terminal=True) == (first_work,)

    captured: dict[str, Any] = {}
    marker = SimpleNamespace(intent=SimpleNamespace(operation_id="planning-operation"))

    def fake_prepare(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return marker

    monkeypatch.setattr(facade._execution, "prepare", fake_prepare)
    assert (
        facade.prepare_planning_execution(
            card,
            expected_plan_hash=card.plan_hash,
            lease_token="one-time-secret",
        )
        is marker
    )
    active = facade._store.get_mission(first_mission.mission_id)
    assert active.state is MissionState.ACTIVE
    assert active.root_work_id == first_work.work_id
    assert facade._store.get_work(first_work.work_id).state is WorkState.READY
    assert captured["adapter"] is ExecutionAdapterKind.CODEX
    assert captured["executor_id"] == "gpt-approved"
    assert captured["force_isolation"] is True
    assert captured["lease_token"] == "one-time-secret"

    microtask = object()
    saga_receipt = object()
    monkeypatch.setattr(facade._execution, "prepare_microtask", lambda operation_id: microtask)
    monkeypatch.setattr(
        facade._local_orchestrator,
        "execute",
        lambda **kwargs: saga_receipt,
    )
    assert (
        facade.execute_planning_foreground(
            card,
            expected_plan_hash=card.plan_hash,
            lease_token="one-time-secret",
            lease_token_environment="E08CD_TOKEN",
        )
        is saga_receipt
    )


def test_p10_retries_draft_and_chg_after_post_write_interruptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    facade, database, _changes = _p10_facade(tmp_path)
    original_draft = facade._store.create_planning_draft
    draft_fired = False

    def fail_after_draft(*args: Any, **kwargs: Any) -> Any:
        nonlocal draft_fired
        result = original_draft(*args, **kwargs)
        if not draft_fired:
            draft_fired = True
            raise ContinuityStoreError("injected after Draft persistence")
        return result

    monkeypatch.setattr(facade._store, "create_planning_draft", fail_after_draft)
    with pytest.raises(PmFacadeError, match="injected"):
        facade.create_planning_draft(_planning_intent())
    draft = facade.create_planning_draft(_planning_intent())

    original_change = facade._changes.create_change_request
    change_fired = False

    def fail_after_change(*args: Any, **kwargs: Any) -> Any:
        nonlocal change_fired
        result = original_change(*args, **kwargs)
        if not change_fired:
            change_fired = True
            raise ValueError("injected after CHG persistence")
        return result

    monkeypatch.setattr(facade._changes, "create_change_request", fail_after_change)
    with pytest.raises(PmFacadeError, match="injected"):
        facade.create_planning_draft_change(_planning_intent())
    change_id = facade.create_planning_draft_change(_planning_intent())

    assert draft.request_id == "REQ-P03-001" and change_id.startswith("CHG-")
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM planning_drafts").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM planning_draft_chg_bindings").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM mission_items").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM work_items").fetchone()[0] == 0


def test_p10_retries_decision_after_post_write_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    facade, card, database = _p10_card(tmp_path)
    original = facade._decisions.create_decision
    fired = False

    def fail_after_decision(*args: Any, **kwargs: Any) -> Any:
        nonlocal fired
        result = original(*args, **kwargs)
        if not fired:
            fired = True
            raise DecisionError("injected after Decision persistence")
        return result

    monkeypatch.setattr(facade._decisions, "create_decision", fail_after_decision)
    approval = {
        "expected_plan_hash": card.plan_hash,
        "approver": "fubai",
        "approval_evidence_ref": "user-confirmation:P10-TEST-002",
    }
    with pytest.raises(PmFacadeError, match="injected"):
        facade.approve_planning_scope_card(card, **approval)
    decision = facade.approve_planning_scope_card(card, **approval)

    assert decision.change_id == card.change_id
    assert len(list((tmp_path / ".auto-pm" / "decisions").glob("DEC-*.json"))) == 1
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM planning_draft_decision_bindings").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM mission_items").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM work_items").fetchone()[0] == 0


def test_p10_retries_each_persisted_authority_boundary_without_duplicate_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A post-write interruption must replay one chain, never a phantom authority."""
    facade, card, database = _p10_card(tmp_path)
    approved = facade.approve_planning_scope_card(card, expected_plan_hash=card.plan_hash, approver="fubai", approval_evidence_ref="user-confirmation:P10-TEST-001")

    original_mission = facade._missions.create_from_planning_approval
    fired = False
    def fail_after_mission(*args: Any, **kwargs: Any) -> Any:
        nonlocal fired
        result = original_mission(*args, **kwargs)
        if not fired:
            fired = True
            raise MissionServiceError("injected after Mission persistence")
        return result
    monkeypatch.setattr(facade._missions, "create_from_planning_approval", fail_after_mission)
    with pytest.raises(PmFacadeError, match="injected"):
        facade.materialize_planning_mission(card)
    mission = facade.materialize_planning_mission(card)

    original_authorize = facade._works.authorize
    fired = False
    observed_pre_authorize: list[tuple[WorkState, str]] = []

    def fail_before_work_authorization(*args: Any, **kwargs: Any) -> Any:
        nonlocal fired
        if not fired:
            fired = True
            pending = facade._works.get_work(str(args[0]))
            observed_pre_authorize.append((pending.state, pending.authorization_ref))
            raise WorkRegistryError("injected before Work authorization")
        return original_authorize(*args, **kwargs)

    monkeypatch.setattr(facade._works, "authorize", fail_before_work_authorization)
    with pytest.raises(PmFacadeError, match="injected"):
        facade.create_planning_work(card)
    assert observed_pre_authorize == [(WorkState.PLANNED, "")]
    work = facade.create_planning_work(card)

    assert mission.authority.decision_id == approved.decision_id
    assert work.authorization_ref == approved.decision_id and work.state is WorkState.READY
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM planning_drafts").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM planning_draft_chg_bindings").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM planning_draft_decision_bindings").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM mission_items").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM work_items").fetchone()[0] == 1


def test_plan_approve_and_execute_are_bounded_and_idempotent(tmp_path: Path) -> None:
    _, facade = _setup(tmp_path)

    plan = facade.plan("MISSION-PM-001")
    assert plan.kind is PmConfirmationKind.APPROVAL
    assert plan.mission_state is MissionState.AWAITING_APPROVAL
    assert facade.plan("MISSION-PM-001").mission_state is MissionState.AWAITING_APPROVAL

    approved = facade.approve("MISSION-PM-001", "WORK-PM-001")
    assert approved.kind is PmConfirmationKind.EXECUTION
    assert approved.mission_state is MissionState.ACTIVE

    executing = facade.execute("MISSION-PM-001")
    assert executing.kind is PmConfirmationKind.EXECUTION
    assert facade._work("WORK-PM-001").state is WorkState.IN_PROGRESS


def test_accept_requires_the_verification_gate(tmp_path: Path) -> None:
    missions, facade = _setup(tmp_path)

    facade.plan("MISSION-PM-001")
    facade.approve("MISSION-PM-001", "WORK-PM-001")
    active = missions.get("MISSION-PM-001")
    missions.transition(
        mission_id=active.mission_id,
        expected_version=active.version,
        new_state=MissionState.ACCEPTANCE_PENDING,
        root_work_id=active.root_work_id,
        idempotency_key="verification-complete",
    )

    with pytest.raises(PmFacadeError, match="Run"):
        facade.accept("MISSION-PM-001")


def test_accept_binds_to_the_latest_passing_checkpoint(tmp_path: Path) -> None:
    missions, facade, _ = _verified_acceptance_ready(tmp_path)
    pending = missions.get("MISSION-C04-001")
    missions.transition(
        mission_id=pending.mission_id,
        expected_version=pending.version,
        new_state=MissionState.ACCEPTANCE_PENDING,
        root_work_id=pending.root_work_id,
        idempotency_key="c04-verification-complete",
    )

    card = facade.accept("MISSION-C04-001")
    assert card.kind is PmConfirmationKind.ACCEPTANCE
    assert card.mission_state is MissionState.ACCEPTED
    assert facade.accept("MISSION-C04-001") == card


def test_accept_rejects_a_checkpoint_after_owned_content_changes(tmp_path: Path) -> None:
    missions, facade, _ = _verified_acceptance_ready(tmp_path)
    (tmp_path / "project" / "auto_pm" / "core" / "target.py").write_text(
        "def value() -> int:\n    return 2\n", encoding="utf-8"
    )
    pending = missions.get("MISSION-C04-001")
    missions.transition(
        mission_id=pending.mission_id,
        expected_version=pending.version,
        new_state=MissionState.ACCEPTANCE_PENDING,
        root_work_id=pending.root_work_id,
        idempotency_key="c04-stale-evidence",
    )

    with pytest.raises(PmFacadeError, match="证据"):
        facade.accept("MISSION-C04-001")


def test_accept_rejects_when_the_latest_run_failed(tmp_path: Path) -> None:
    missions, facade, execution = _verified_acceptance_ready(tmp_path)
    execution.transition_run(
        "RUN-C04-001",
        RunState.FAILED,
        "c04-test",
        "c04-test-lease",
        "c04-run-failed",
    )
    pending = missions.get("MISSION-C04-001")
    missions.transition(
        mission_id=pending.mission_id,
        expected_version=pending.version,
        new_state=MissionState.ACCEPTANCE_PENDING,
        root_work_id=pending.root_work_id,
        idempotency_key="c04-failed-evidence",
    )

    with pytest.raises(PmFacadeError, match="Run"):
        facade.accept("MISSION-C04-001")


def test_confirm_start_uses_the_mission_bound_work_without_an_internal_id(tmp_path: Path) -> None:
    _, facade = _setup(tmp_path)

    facade.plan("MISSION-PM-001")
    card = facade.confirm_start("MISSION-PM-001")

    assert card.kind is PmConfirmationKind.EXECUTION
    assert facade._work("WORK-PM-001").state is WorkState.IN_PROGRESS


def test_facade_rejects_out_of_order_actions_and_keeps_legacy_isolated(tmp_path: Path) -> None:
    _, facade = _setup(tmp_path)

    with pytest.raises(PmFacadeError, match="可执行状态"):
        facade.execute("MISSION-PM-001")
    assert "pm-workflow 已退役隔离" in facade.compatibility_notice()


def test_planning_draft_replays_the_same_request_and_payload(tmp_path: Path) -> None:
    facade, database = _planning_facade(tmp_path)

    created = facade.create_planning_draft(_planning_intent())
    replayed = PmFacadeService(
        tmp_path, store=ContinuityStore(tmp_path, database)
    ).create_planning_draft(_planning_intent())

    assert replayed == created
    assert database.is_file()
    assert not (tmp_path / ".auto-pm" / "continuity.db").exists()
    assert {"mission_id", "work_id", "run_id"}.isdisjoint(created.model_dump())


def test_planning_draft_migrates_a_v3_store_in_the_isolated_database(tmp_path: Path) -> None:
    _, database = _planning_facade(tmp_path)
    with sqlite3.connect(database) as conn:
        conn.execute("DROP INDEX idx_planning_drafts_project_state")
        conn.execute("DROP TABLE planning_drafts")
        conn.execute("UPDATE schema_meta SET schema_version='continuity-store.v3'")

    store = ContinuityStore(tmp_path, database)
    store.initialize("2026-09-14T00:01:00+00:00", "test")

    with sqlite3.connect(database) as conn:
        schema_version = conn.execute("SELECT schema_version FROM schema_meta").fetchone()[0]
        planning_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='planning_drafts'"
        ).fetchone()

    assert schema_version == "continuity-store.v7"
    assert planning_table == ("planning_drafts",)


def test_planning_draft_rejects_a_changed_payload_for_the_same_request_id(tmp_path: Path) -> None:
    facade, _ = _planning_facade(tmp_path)
    original = _planning_intent()
    facade.create_planning_draft(original)

    with pytest.raises(PmFacadeError, match="request_id 已绑定不同输入"):
        facade.create_planning_draft(_planning_intent(objective="A different plan."))

    assert facade.create_planning_draft(original).input_fingerprint


def test_planning_draft_does_not_create_mission_work_or_run(tmp_path: Path) -> None:
    facade, database = _planning_facade(tmp_path)
    facade.create_planning_draft(_planning_intent())

    with sqlite3.connect(database) as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("mission_items", "work_items", "run_items")
        }

    assert counts == {"mission_items": 0, "work_items": 0, "run_items": 0}


def test_planning_draft_binds_one_real_chg_and_replays_without_execution(tmp_path: Path) -> None:
    project = tmp_path / "SW-TEST-001"
    (project / "04_监控" / "01_变更管理" / "01_变更单").mkdir(parents=True)
    ledger = project / "04_监控" / "01_变更管理" / "01_版本变更台帐.md"
    ledger.write_text(
        "# 版本变更台帐\n\n| 序号 | 变更编号 | 描述 |\n|---|---|---|\n",
        encoding="utf-8",
    )
    _git_root(tmp_path)
    database = tmp_path / ".auto-pm" / "p04-planning-draft-test.db"
    store = ContinuityStore(tmp_path, database)
    store.initialize("2026-09-14T00:00:00+00:00", "test")
    facade = PmFacadeService(
        tmp_path,
        store=store,
        change_service=ChangeService(str(tmp_path)),
    )

    intent = PmIntent(
        request_id="REQ-P04-001",
        subject_project_id="SW-TEST-001",
        objective="Bind one reviewable change draft.",
        acceptance_criteria=("The CHG must replay exactly once.",),
    )
    change_id = facade.create_planning_draft_change(intent)
    replayed_change_id = facade.create_planning_draft_change(intent)

    assert replayed_change_id == change_id
    assert ChangeService(str(tmp_path)).get_change_request(change_id, "SW-TEST-001")
    with sqlite3.connect(database) as conn:
        bindings = conn.execute("SELECT request_id, change_id FROM planning_draft_chg_bindings").fetchall()
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("mission_items", "work_items", "run_items")
        }
    assert bindings == [("REQ-P04-001", change_id)]
    assert counts == {"mission_items": 0, "work_items": 0, "run_items": 0}


def test_planning_draft_binds_effective_python_and_plc_specs_without_execution(
    tmp_path: Path,
) -> None:
    _git_root(tmp_path)
    registry = tmp_path / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
    python_spec = tmp_path / "specs" / "python.md"
    plc_spec = tmp_path / "specs" / "plc.md"
    python_spec.parent.mkdir(parents=True)
    python_spec.write_text("python", encoding="utf-8")
    plc_spec.write_text("plc", encoding="utf-8")
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "specs": {
                    "DEV-TEST": {
                        "domain": "python",
                        "lifecycle": "stable",
                        "canonical_path": "specs/python.md",
                        "version": "V1.0.0",
                    },
                    "LSP-TEST": {
                        "domain": "plc",
                        "lifecycle": "active",
                        "canonical_path": "specs/plc.md",
                        "version": "V2.0.0",
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    database = tmp_path / ".auto-pm" / "p05-planning-draft-test.db"
    store = ContinuityStore(tmp_path, database)
    store.initialize("2026-09-14T00:00:00+00:00", "test")
    facade = PmFacadeService(tmp_path, store=store)

    sources = facade.bind_planning_draft_specs(_planning_intent())
    assert facade.bind_planning_draft_specs(_planning_intent()) == sources
    assert sources == (
        ("DEV-TEST", "specs/python.md", "V1.0.0"),
        ("LSP-TEST", "specs/plc.md", "V2.0.0"),
    )
    with sqlite3.connect(database) as conn:
        bindings = conn.execute(
            "SELECT spec_id, canonical_path, version FROM planning_draft_spec_bindings ORDER BY spec_id"
        ).fetchall()
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("mission_items", "work_items", "run_items")
        }
    assert bindings == list(sources)
    assert counts == {"mission_items": 0, "work_items": 0, "run_items": 0}


def test_planning_draft_spec_binding_reports_the_missing_source(tmp_path: Path) -> None:
    facade, _ = _planning_facade(tmp_path)

    with pytest.raises(PmFacadeError, match="规范注册表不存在"):
        facade.bind_planning_draft_specs(_planning_intent())


def test_planning_scope_card_is_deterministic_and_never_creates_execution(tmp_path: Path) -> None:
    _git_root(tmp_path)
    project = tmp_path / "SW-TEST-001"
    (project / "04_监控" / "01_变更管理" / "01_变更单").mkdir(parents=True)
    (project / "04_监控" / "01_变更管理" / "01_版本变更台帐.md").write_text(
        "# 台帐\n\n| 序号 | 变更编号 | 描述 |\n|---|---|---|\n", encoding="utf-8"
    )
    registry = tmp_path / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "python.md").write_text("python", encoding="utf-8")
    (tmp_path / "specs" / "plc.md").write_text("plc", encoding="utf-8")
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"specs": {
        "DEV-TEST": {"domain": "python", "lifecycle": "stable", "canonical_path": "specs/python.md", "version": "V1"},
        "LSP-TEST": {"domain": "plc", "lifecycle": "active", "canonical_path": "specs/plc.md", "version": "V1"},
    }}), encoding="utf-8")
    database = tmp_path / ".auto-pm" / "p06-test.db"
    store = ContinuityStore(tmp_path, database)
    store.initialize("2026-09-14T00:00:00+00:00", "test")
    facade = PmFacadeService(tmp_path, store=store, change_service=ChangeService(str(tmp_path)))

    card = facade.create_planning_scope_card(
        _planning_intent(), scope_paths=("auto_pm/example.py",), risks=("scope drift",), non_goals=("no execution",)
    )
    assert facade.create_planning_scope_card(
        _planning_intent(), scope_paths=("auto_pm/example.py",), risks=("scope drift",), non_goals=("no execution",)
    ) == card
    assert card.executable is False and len(card.plan_hash) == 64
    with sqlite3.connect(database) as conn:
        assert {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("mission_items", "work_items", "run_items")} == {"mission_items": 0, "work_items": 0, "run_items": 0}
    with pytest.raises(PmFacadeError, match="wildcards"):
        facade.create_planning_scope_card(_planning_intent(), scope_paths=("auto_pm/*",), risks=("scope drift",), non_goals=("no execution",))


def test_planning_approval_materializes_one_exact_authorized_mission(
    tmp_path: Path,
) -> None:
    _git_root(tmp_path)
    project = tmp_path / "SW-TEST-001"
    (project / "04_监控" / "01_变更管理" / "01_变更单").mkdir(parents=True)
    (project / "04_监控" / "01_变更管理" / "01_版本变更台帐.md").write_text(
        "# 台帐\n\n| 序号 | 变更编号 | 描述 |\n|---|---|---|\n",
        encoding="utf-8",
    )
    registry = tmp_path / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "python.md").write_text("python", encoding="utf-8")
    (tmp_path / "specs" / "plc.md").write_text("plc", encoding="utf-8")
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "specs": {
                    "DEV-TEST": {
                        "domain": "python",
                        "lifecycle": "stable",
                        "canonical_path": "specs/python.md",
                        "version": "V1",
                    },
                    "LSP-TEST": {
                        "domain": "plc",
                        "lifecycle": "active",
                        "canonical_path": "specs/plc.md",
                        "version": "V1",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    workspace_registry = tmp_path / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    workspace_registry.parent.mkdir(parents=True)
    workspace_registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": "SW-TEST-001",
                        "project_root": "SW-TEST-001",
                        "development_root": "SW-TEST-001",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    database = tmp_path / ".auto-pm" / "p07-test.db"
    store = ContinuityStore(tmp_path, database)
    store.initialize("2026-09-14T00:00:00+00:00", "test")
    changes = ChangeService(str(tmp_path))
    facade = PmFacadeService(tmp_path, store=store, change_service=changes)
    card = facade.create_planning_scope_card(
        _planning_intent(),
        scope_paths=("auto_pm/example.py",),
        risks=("scope drift",),
        non_goals=("no execution",),
    )
    for state in ("submitted", "under_review", "approved"):
        changes.transition_status(
            card.change_id,
            state,
            approver="fubai",
            comment="human review",
            project_id="SW-TEST-001",
        )

    with pytest.raises(PmFacadeError, match="尚未绑定用户批准的 Decision"):
        facade.materialize_planning_mission(card)
    with pytest.raises(PmFacadeError, match="过期或内容发生漂移"):
        facade.approve_planning_scope_card(
            card,
            expected_plan_hash="0" * 64,
            approver="fubai",
            approval_evidence_ref="user-confirmation:P07-TEST-001",
        )
    with pytest.raises(PmFacadeError, match="模型或 Agent 自签"):
        facade.approve_planning_scope_card(
            card,
            expected_plan_hash=card.plan_hash,
            approver="codex-gpt-5",
            approval_evidence_ref="user-confirmation:P07-TEST-001",
        )
    with pytest.raises(PmFacadeError, match="user-confirmation"):
        facade.approve_planning_scope_card(
            card,
            expected_plan_hash=card.plan_hash,
            approver="fubai",
            approval_evidence_ref="model-confirmation:P07-TEST-001",
        )

    approved = facade.approve_planning_scope_card(
        card,
        expected_plan_hash=card.plan_hash,
        approver="fubai",
        approval_evidence_ref="user-confirmation:P07-TEST-001",
    )
    replayed = facade.approve_planning_scope_card(
        card,
        expected_plan_hash=card.plan_hash,
        approver="fubai",
        approval_evidence_ref="user-confirmation:P07-TEST-001",
    )
    with pytest.raises(PmFacadeError, match="已绑定不同批准"):
        facade.approve_planning_scope_card(
            card,
            expected_plan_hash=card.plan_hash,
            approver="fubai",
            approval_evidence_ref="user-confirmation:P07-TEST-002",
        )

    assert replayed.to_dict() == approved.to_dict()
    assert approved.change_id == card.change_id
    assert approved.approved_files == list(card.scope_paths)
    assert approved.metadata["planning_approval"] == {
        "schema_version": "planning-approval.v2",
        "plan_hash": card.plan_hash,
        "approval_evidence_ref": "user-confirmation:P07-TEST-001",
        "request_id": card.request_id,
        "execution_grant": card.execution_grant.model_dump(mode="json"),
    }
    mission = facade.materialize_planning_mission(card, created_by="PM Facade")
    replayed_mission = facade.materialize_planning_mission(card, created_by="PM Facade")
    assert replayed_mission == mission
    assert mission.state is MissionState.DRAFT
    assert mission.subject_project_id == card.subject_project_id
    assert mission.acceptance_criteria == card.acceptance_criteria
    assert mission.mission_id.startswith("MISSION-") and "PLACEHOLDER" not in mission.mission_id
    assert mission.authority.envelope_id.startswith("AUTH-")
    assert mission.authority.authorization_source == "CHG_DECISION"
    assert mission.authority.change_id == card.change_id
    assert mission.authority.decision_id == approved.decision_id
    assert mission.authority.scope_paths == card.scope_paths
    assert mission.authority.allowed_child_work_kinds == frozenset({WorkKind.WBS})
    assert WorkKind.BUG not in mission.authority.allowed_child_work_kinds
    assert WorkKind.TEST not in mission.authority.allowed_child_work_kinds
    assert WorkKind.DEBT not in mission.authority.allowed_child_work_kinds
    assert WorkKind.GOVERNANCE not in mission.authority.allowed_child_work_kinds
    assert mission.authority.audit.approved_by == "fubai"
    assert mission.authority.audit.source_fingerprint.startswith("sha256:")
    with pytest.raises(PmFacadeError, match="plan_hash 已过期或内容发生漂移"):
        facade.materialize_planning_mission(card.model_copy(update={"plan_hash": "0" * 64}))
    assert len(list((tmp_path / ".auto-pm" / "decisions").glob("DEC-*.json"))) == 1
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM planning_draft_decision_bindings").fetchone()[0] == 1
        assert {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("mission_items", "work_items", "run_items")
        } == {"mission_items": 1, "work_items": 0, "run_items": 0}


def test_planning_scope_card_cold_replay_survives_approved_change(tmp_path: Path) -> None:
    facade, database, changes = _p10_facade(tmp_path)
    intent = _planning_intent()
    card = facade.create_planning_scope_card(
        intent,
        scope_paths=("auto_pm/example.py",),
        risks=("scope drift",),
        non_goals=("no execution",),
    )
    for state in ("submitted", "under_review", "approved"):
        changes.transition_status(
            card.change_id,
            state,
            approver="fubai",
            comment="human review",
            project_id="SW-TEST-001",
        )

    cold_facade = PmFacadeService(
        tmp_path,
        store=ContinuityStore(tmp_path, database),
        change_service=ChangeService(str(tmp_path)),
    )
    replayed = cold_facade.create_planning_scope_card(
        intent,
        scope_paths=("auto_pm/example.py",),
        risks=("scope drift",),
        non_goals=("no execution",),
    )

    assert replayed == card
