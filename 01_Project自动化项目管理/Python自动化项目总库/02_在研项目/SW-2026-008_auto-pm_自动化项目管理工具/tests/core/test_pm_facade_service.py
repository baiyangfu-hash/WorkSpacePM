"""Behaviour tests for the state-free PM Facade."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.core.mission_service import MissionService, MissionServiceError
from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.core.work_registry_service import WorkRegistryError, WorkRegistryService
from auto_pm.core.workspace_context_service import WorkspaceContextService

from auto_pm.application.core.evidence_collection_service import (
    EvidenceCollectionService,
    PythonQualityGate,
    PythonQualityReceipt,
    _quality_receipt_hash,
)
from auto_pm.application.core.pm_facade_service import PmFacadeService as PlanningFacade
from auto_pm.application.core.pm_intake_service import PmIntakeService
from auto_pm.contracts.continuity import RunState, WorkKind, WorkState
from auto_pm.contracts.execution_adapter import (
    ExecutionAdapterKind,
    ForegroundExecutionReceipt,
    WorktreeMode,
)
from auto_pm.contracts.intake import Disposition, IntakeItem, IntakeKind, IntakeStatus, TriageTicket
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope, MissionState
from auto_pm.contracts.pm_facade import (
    PlanningExecutionGrant,
    PlanningScopeCard,
    PmConfirmationKind,
    PmIntent,
    PmRunOutcome,
)
from auto_pm.domain.change.decision_service import DecisionError
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.intake_store import IntakeStore
from tests.plan_checklist_support import full_checklist

# Plans must declare the exact files they will change (改动声明不得为空).
_EXAMPLE_GRANT = PlanningExecutionGrant(
    adapter=ExecutionAdapterKind.MANUAL,
    approved_model="manual",
    declared_dirty_paths=("auto_pm/example.py",),
    plan_checklist=full_checklist(),
)


def _audit_scene(root: Path) -> tuple[PmFacadeService, Path, IntakeItem]:
    facade, database, _changes = _p10_facade(root)
    project_id = _planning_intent().subject_project_id
    project = root / project_id
    (project / ".copier-answers.yml").write_text(
        f"project_id: {project_id}\nproject_name: Audit planning fixture\nstack: python\n",
        encoding="utf-8", errors="replace",
    )
    context = WorkspaceContextService(str(root)).resolve(project_id=project_id, start_path=project)
    assert context.subject.project_id == project_id
    assert context.subject.stack == "python"
    desk = PmIntakeService(root, store=IntakeStore(root, database))
    filing = desk.classify(
        project_id, kind=IntakeKind.BUG, change_action=None, domain="", impact_scope=()
    )
    item, _created = desk.propose(
        request_id="REQ-AUDIT-INBOX",
        project_id="SW-TEST-001",
        title="Audit failure",
        classification=filing,
        proposed_by="audit",
        ticket=TriageTicket(
            original_words="Audit failure",
            affects="Planning",
            duplicate_check="Checked",
            evidence=("file:specs/python.md",),
            disposition=Disposition.AFTER_CURRENT,
            rationale="After current",
            alternatives=("Wait",),
            cost_risk="Low",
        ),
    )
    item = desk.confirm(
        item.item_id,
        ticket_hash=item.ticket_hash,
        approver="fubai",
        approval_evidence_ref="user-confirmation:chat-20261005-audit",
    )
    assert item.project_id == context.subject.project_id
    assert item.classification.domain == "SCPT"
    return facade, database, item


def _audit_card(facade: PlanningFacade, item: IntakeItem, **options: Any) -> PlanningScopeCard:
    values: dict[str, Any] = {
        "scope_paths": ("auto_pm/example.py",),
        "risks": ("Drift",),
        "non_goals": ("No deployment",),
        "execution_grant": PlanningExecutionGrant(
            adapter=ExecutionAdapterKind.CODEX, approved_model="gpt-approved",
            declared_dirty_paths=("auto_pm/example.py",),
            plan_checklist=full_checklist(original="Audit failure"),
        ),
        "classification": item.classification,
        "intake_item_id": item.item_id,
    }
    values.update(options)
    return facade.create_planning_scope_card(_planning_intent(), **values)


def _audit_count(database: Path, table: str, where: str = "", args: tuple[str, ...] = ()) -> int:
    with closing(sqlite3.connect(database)) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
            return 0
        return int(conn.execute(f"SELECT COUNT(*) FROM {table} {where}", args).fetchone()[0])


def _audit_unconsumed(root: Path, database: Path, item: IntakeItem) -> dict[str, Any]:
    cold = IntakeStore(root, database)
    persisted = cold.get_item(item.item_id)
    assert persisted.status is IntakeStatus.CONFIRMED
    assert persisted.plan_request_id == ""
    assert cold.get_planning_classification(_planning_intent().request_id) is None
    cards = _audit_count(database, "planning_scope_cards")
    assert cards == 0
    events = {
        event: _audit_count(database, "events", "WHERE event_type=?", (event,))
        for event in (
        "INTAKE_ITEM_PLANNED",
        "PLANNING_DRAFT_INTAKE_BOUND",
        "PLANNING_SCOPE_CARD_SUBMITTED",
        )
    }
    assert list(events.values()) == [0, 0, 0]
    return {"status": persisted.status.value, "plan_request_id": persisted.plan_request_id,
            "cards": cards, "events": events}


@pytest.mark.parametrize("entry", ["create", "submit"])
@pytest.mark.parametrize("invalid", ["scope", "risk", "non_goal", "grant"])
def test_audit_f01_invalid_contract_never_consumes(
    tmp_path: Path,
    invalid: str,
    entry: str,
) -> None:
    facade, database, item = _audit_scene(tmp_path)
    values: dict[str, Any] = {
        "scope_paths": ("auto_pm/example.py",),
        "risks": ("Drift",),
        "non_goals": ("No deployment",),
        "execution_grant": PlanningExecutionGrant(
            adapter=ExecutionAdapterKind.CODEX, approved_model="gpt-approved",
            declared_dirty_paths=("auto_pm/example.py",),
            plan_checklist=full_checklist(original="Audit failure"),
        ),
        "classification": item.classification,
        "intake_item_id": item.item_id,
    }
    replacements: dict[str, tuple[str, Any]] = {
        "scope": ("scope_paths", ("auto_pm/*",)),
        "risk": ("risks", (" ",)),
        "non_goal": ("non_goals", (" ",)),
        "grant": (
            "execution_grant",
            PlanningExecutionGrant(
                adapter=ExecutionAdapterKind.CODEX,
                approved_model="gpt-approved",
                declared_dirty_paths=("outside.py",),
            ),
        ),
    }
    key, value = replacements[invalid]
    values[key] = value
    with pytest.raises(PmFacadeError):
        if entry == "create":
            facade.create_planning_scope_card(_planning_intent(), **values)
        else:
            facade.create_planning_draft(_planning_intent())
            facade.submit_planning_scope_card(
                _planning_intent().request_id, submitted_by="audit", **values
            )
    _audit_unconsumed(tmp_path, database, item)
    cold = PmFacadeService(tmp_path, store=ContinuityStore(tmp_path, database))
    card = _audit_card(cold, item)
    assert (
        cold._store.get_submitted_planning_scope_card(card.request_id, card.plan_hash).card == card
    )


@pytest.mark.parametrize("boundary", ["chg_before", "chg_after", "specs", "card"])
def test_audit_f02_preparation_io_failure_cold_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    facade, database, item = _audit_scene(tmp_path)
    with monkeypatch.context() as patch:
        if boundary.startswith("chg_"):
            change_module = sys.modules[type(facade._changes).__module__]
            original_write = vars(change_module)["write_file"]

            def failing_write(*args: Any, **kwargs: Any) -> Any:
                if boundary == "chg_after":
                    original_write(*args, **kwargs)
                raise OSError("audit CHG I/O boundary")

            patch.setattr(change_module, "write_file", failing_write)
        elif boundary == "specs":
            original_event = ContinuityStore._append_event

            def failing_event(*args: Any, **kwargs: Any) -> None:
                original_event(*args, **kwargs)
                if args[2] == "PLANNING_DRAFT_SPECS_BOUND":
                    raise sqlite3.OperationalError("audit spec persistence boundary")

            patch.setattr(ContinuityStore, "_append_event", staticmethod(failing_event))
        else:
            original_card = PlanningScopeCard.from_draft

            def failing_card(*args: Any, **kwargs: Any) -> PlanningScopeCard:
                card = original_card(*args, **kwargs)
                if kwargs["change_id"]:
                    raise ValueError("audit card construction boundary")
                return card

            patch.setattr(PlanningScopeCard, "from_draft", failing_card)
        with pytest.raises((OSError, sqlite3.OperationalError, PmFacadeError)):
            _audit_card(facade, item)
    _audit_unconsumed(tmp_path, database, item)
    with closing(sqlite3.connect(database)) as conn:
        reserved = conn.execute("SELECT change_id FROM planning_draft_chg_bindings").fetchone()[0]
    cold = PmFacadeService(tmp_path, store=ContinuityStore(tmp_path, database))
    card = _audit_card(cold, item)
    assert card.change_id == reserved
    assert _audit_card(cold, item) == card
    assert len(list((tmp_path / "SW-TEST-001").rglob("CHG-*.md"))) == 1
    assert (
        cold._store.get_submitted_planning_scope_card(card.request_id, card.plan_hash).card == card
    )


@pytest.mark.parametrize(
    "boundary", ["card", "item", "binding", "card_event", "item_event", "binding_event", "commit"]
)
def test_audit_f03_sqlite_boundaries_roll_back_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    from auto_pm.infrastructure.continuity_store import _PLANNING_SCOPE_CARDS_DDL

    facade, database, item = _audit_scene(tmp_path)
    facade.create_planning_draft_change(
        _planning_intent(), classification=item.classification, intake_item_id=item.item_id
    )
    facade.bind_planning_draft_specs(_planning_intent())
    commit_observed: list[dict[str, int]] = []
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute(_PLANNING_SCOPE_CARDS_DDL)
        if boundary != "commit":
            operations = {
                "card": ("INSERT", "planning_scope_cards", ""),
                "item": ("UPDATE", "intake_items", ""),
                "binding": ("INSERT", "planning_draft_intake_bindings", ""),
                "card_event": (
                    "INSERT",
                    "events",
                    "WHEN NEW.event_type='PLANNING_SCOPE_CARD_SUBMITTED'",
                ),
                "item_event": ("INSERT", "events", "WHEN NEW.event_type='INTAKE_ITEM_PLANNED'"),
                "binding_event": (
                    "INSERT",
                    "events",
                    "WHEN NEW.event_type='PLANNING_DRAFT_INTAKE_BOUND'",
                ),
            }
            verb, table, condition = operations[boundary]
            conn.execute(
                f"CREATE TRIGGER audit_failure AFTER {verb} ON {table} {condition} BEGIN SELECT RAISE(ABORT, 'audit boundary'); END"
            )
    with monkeypatch.context() as patch:
        if boundary == "commit":
            real_connect = sqlite3.connect

            class FailingCommit(sqlite3.Connection):
                def commit(self) -> None:
                    if self.execute("SELECT 1 FROM planning_scope_cards").fetchone() is not None:
                        commit_observed.append({
                            "cards": self.execute("SELECT COUNT(*) FROM planning_scope_cards").fetchone()[0],
                            "bindings": self.execute("SELECT COUNT(*) FROM planning_draft_intake_bindings").fetchone()[0],
                            "planned": self.execute("SELECT COUNT(*) FROM intake_items WHERE status='PLANNED'").fetchone()[0],
                            "success_events": self.execute("SELECT COUNT(*) FROM events WHERE event_type IN ('INTAKE_ITEM_PLANNED', 'PLANNING_DRAFT_INTAKE_BOUND', 'PLANNING_SCOPE_CARD_SUBMITTED')").fetchone()[0],
                        })
                        raise sqlite3.OperationalError("audit commit boundary")
                    super().commit()

            def connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
                kwargs["factory"] = FailingCommit
                connection = real_connect(*args, **kwargs)
                assert isinstance(connection, sqlite3.Connection)
                return connection

            patch.setattr(sqlite3, "connect", connect)
        with pytest.raises(sqlite3.DatabaseError, match="audit") as injected:
            _audit_card(facade, item)
    expected_commit = [{"cards": 1, "bindings": 1, "planned": 1, "success_events": 3}] if boundary == "commit" else []
    assert commit_observed == expected_commit
    rollback = _audit_unconsumed(tmp_path, database, item)
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("DROP TRIGGER IF EXISTS audit_failure")
    cold = PmFacadeService(tmp_path, store=ContinuityStore(tmp_path, database))
    card = _audit_card(cold, item)
    assert (
        cold._store.get_submitted_planning_scope_card(card.request_id, card.plan_hash).card == card
    )
    for event in (
        "INTAKE_ITEM_PLANNED",
        "PLANNING_DRAFT_INTAKE_BOUND",
        "PLANNING_SCOPE_CARD_SUBMITTED",
    ):
        assert _audit_count(database, "events", "WHERE event_type=?", (event,)) == 1
    with closing(sqlite3.connect(database)) as conn:
        chain = conn.execute(
            "SELECT previous_hash, event_hash FROM events ORDER BY rowid"
        ).fetchall()
    assert chain[0][0] == ""
    assert all(chain[index][0] == chain[index - 1][1] for index in range(1, len(chain)))
    print(json.dumps({"F03": boundary, "exception": type(injected.value).__name__,
                      "message": str(injected.value), "before_commit": commit_observed,
                      "cold_rollback": rollback, "retry_plan_hash": card.plan_hash,
                      "event_chain_rows": len(chain)}, ensure_ascii=False))


def test_audit_f04_success_is_durable_and_replay_keeps_execution_rows(tmp_path: Path) -> None:
    facade, database, item = _audit_scene(tmp_path)
    tables = (
        "mission_items",
        "work_items",
        "run_items",
        "execution_leases",
        "checkpoints",
        "handoffs_v2",
    )
    with closing(sqlite3.connect(database)) as conn:
        before = {
            table: conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() for table in tables
        }
    card = _audit_card(facade, item)
    cold = PmFacadeService(tmp_path, store=ContinuityStore(tmp_path, database))
    assert _audit_count(database, "planning_scope_cards") == 1
    saved = cold._store.get_submitted_planning_scope_card(card.request_id, card.plan_hash)
    assert saved.card == card and saved.revision == 1
    assert _audit_card(cold, item, classification=None, intake_item_id="") == card
    assert (
        cold.submit_planning_scope_card(
            card.request_id,
            scope_paths=card.scope_paths,
            risks=card.risks,
            non_goals=card.non_goals,
            execution_grant=card.execution_grant,
            submitted_by="audit",
        ).card
        == card
    )
    assert _audit_count(database, "planning_scope_cards") == 1
    for event in (
        "INTAKE_ITEM_PLANNED",
        "PLANNING_DRAFT_INTAKE_BOUND",
        "PLANNING_SCOPE_CARD_SUBMITTED",
    ):
        assert _audit_count(database, "events", "WHERE event_type=?", (event,)) == 1
    with closing(sqlite3.connect(database)) as conn:
        assert {
            table: conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() for table in tables
        } == before
    assert IntakeStore(tmp_path, database).get_item(item.item_id).plan_request_id == card.request_id
    revised = _audit_card(cold, item, risks=("Revised risk",))
    assert revised.plan_hash != card.plan_hash
    assert (
        cold._store.get_submitted_planning_scope_card(
            revised.request_id, revised.plan_hash
        ).revision
        == 2
    )
    assert _audit_count(database, "events", "WHERE event_type=?", ("INTAKE_ITEM_PLANNED",)) == 1


@pytest.mark.parametrize("field", ["domain", "kind", "scope", "action", "project"])
def test_audit_f02_cold_retry_rejects_mismatched_reserved_change(
    tmp_path: Path,
    field: str,
) -> None:
    from auto_pm.contracts.intake import ChangeAction, IntakeClassification

    facade, database, item = _audit_scene(tmp_path)
    filing = IntakeClassification(
        kind=IntakeKind.CHANGE, change_action=ChangeAction.ADD, domain="SCPT"
    )
    facade.create_planning_draft_change(_planning_intent(), classification=filing)
    changed: dict[str, Any] = {
        "domain": {"domain": "PLC"},
        "kind": {"kind": IntakeKind.BUG, "change_action": None},
        "scope": {"impact_scope": ("SYSTEM",)},
        "action": {"change_action": ChangeAction.REMOVE},
        "project": {},
    }
    if field == "project":
        intent = _planning_intent().model_copy(update={"subject_project_id": "SW-OTHER-002"})
        with pytest.raises(PmFacadeError, match="同一项目|不同输入"):
            facade.create_planning_draft_change(intent, classification=filing)
    else:
        mismatch = IntakeClassification.model_validate({**filing.model_dump(), **changed[field]})
        with pytest.raises(PmFacadeError, match="CHG|候选"):
            facade.create_planning_draft_change(_planning_intent(), classification=mismatch)
    _audit_unconsumed(tmp_path, database, item)


def test_audit_f08_saved_classified_card_approves_and_legacy_create_without_declaration_is_refused(
    tmp_path: Path,
) -> None:
    facade, database, item = _audit_scene(tmp_path)
    card = _audit_card(facade, item)
    cold = PmFacadeService(tmp_path, store=ContinuityStore(tmp_path, database))
    approved = cold.approve_pending_planning_scope_card(
        card.request_id,
        expected_plan_hash=card.plan_hash,
        approver="fubai",
        approval_evidence_ref="user-confirmation:chat-20261005-audit-saved",
    )
    assert approved.plan_hash == card.plan_hash
    assert _audit_card(cold, item) == card
    assert (
        cold.approve_pending_planning_scope_card(
            card.request_id,
            expected_plan_hash=card.plan_hash,
            approver="fubai",
            approval_evidence_ref="user-confirmation:chat-20261005-audit-saved",
        )
        == approved
    )
    assert _audit_count(database, "run_items") == 0
    legacy_intent = _planning_intent().model_copy(update={"request_id": "REQ-LEGACY"})
    # A legacy create without any declared dirty path is now refused before any write.
    with pytest.raises(PmFacadeError, match="--declared-dirty"):
        cold.create_planning_scope_card(
            legacy_intent, scope_paths=("legacy.py",), risks=("Risk",), non_goals=("No deployment",)
        )
    assert (
        _audit_count(database, "planning_scope_cards", "WHERE request_id=?", ("REQ-LEGACY",)) == 0
    )

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
    card = facade.create_planning_scope_card(_planning_intent(), scope_paths=("auto_pm/example.py",), risks=("retry",), non_goals=("no execution",), execution_grant=_EXAMPLE_GRANT)
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
        plan_checklist=full_checklist(),
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
    assert captured["lease_seconds"] == 900

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


@pytest.mark.needs_quality_tools
def test_acceptance_rechecks_generic_owned_paths_after_rehash(tmp_path: Path) -> None:
    _, facade, _ = _verified_acceptance_ready(tmp_path)
    run = facade._store.get_run("RUN-C04-001")
    collector = EvidenceCollectionService(tmp_path)
    receipt = collector.run_generic_checkpoint_quality_gates(run, tmp_path)
    assert receipt.status == "PASS"
    collection = collector.collect(run)
    serialized = collector.build_checkpoint_evidence(collection, receipt)
    assert facade._acceptance_evidence_is_current(serialized, collection, run, tmp_path)

    envelope = json.loads(serialized)
    envelope["quality_receipt"]["owned_python_paths"] = [
        "project/auto_pm/core/target.py"
    ]
    payload = {
        key: value for key, value in envelope["quality_receipt"].items() if key != "status"
    }
    envelope["receipt_hash"] = facade._evidence_hash(payload)
    envelope["envelope_hash"] = facade._evidence_hash(
        {key: value for key, value in envelope.items() if key != "envelope_hash"}
    )
    forged = facade._canonical_json(envelope)
    assert not facade._acceptance_evidence_is_current(forged, collection, run, tmp_path)


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

    assert schema_version == "continuity-store.v8"
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
    (project / "PM_SESSION_SW-TEST-001.md").write_text("# Test project\n", encoding="utf-8")
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
        _planning_intent(), scope_paths=("auto_pm/example.py",), risks=("scope drift",), non_goals=("no execution",),
        execution_grant=_EXAMPLE_GRANT,
    )
    assert facade.create_planning_scope_card(
        _planning_intent(), scope_paths=("auto_pm/example.py",), risks=("scope drift",), non_goals=("no execution",),
        execution_grant=_EXAMPLE_GRANT,
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
        execution_grant=_EXAMPLE_GRANT,
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
        execution_grant=_EXAMPLE_GRANT,
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
        execution_grant=_EXAMPLE_GRANT,
    )

    assert replayed == card


@pytest.mark.parametrize("seconds", [True, 59, 3601, 86_400])
def test_planning_lease_configuration_rejects_unbounded_values(
    tmp_path: Path, seconds: int
) -> None:
    with pytest.raises(PmFacadeError, match="planning_lease_seconds"):
        PmFacadeService(tmp_path, planning_lease_seconds=seconds)


def test_planning_lease_configuration_accepts_short_bounded_value(tmp_path: Path) -> None:
    facade = PmFacadeService(tmp_path, planning_lease_seconds=300)
    assert facade._planning_lease_seconds == 300


def test_approved_planning_card_can_be_recovered_from_persisted_truth(tmp_path: Path) -> None:
    facade, _database, changes = _p10_facade(tmp_path)
    card = facade.create_planning_scope_card(
        _planning_intent(),
        scope_paths=("auto_pm/example.py",),
        risks=("scope drift",),
        non_goals=("no unrelated edits",),
        execution_grant=PlanningExecutionGrant(
            adapter=ExecutionAdapterKind.CODEX,
            approved_model="gpt-5.6-sol",
            declared_dirty_paths=("auto_pm/example.py",),
            plan_checklist=full_checklist(),
        ),
    )
    for state in ("submitted", "under_review", "approved"):
        changes.transition_status(
            card.change_id,
            state,
            approver="fubai",
            comment="human review",
            project_id="SW-TEST-001",
        )
    facade.approve_planning_scope_card(
        card,
        expected_plan_hash=card.plan_hash,
        approver="fubai",
        approval_evidence_ref="user-confirmation:U03A-001",
    )
    mission = facade.materialize_planning_mission(card)

    assert facade.recover_planning_scope_card(mission.mission_id) == card


def test_start_approved_mission_keeps_generated_lease_inside_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    facade = PmFacadeService(tmp_path)
    card = SimpleNamespace(plan_hash="a" * 64)
    receipt = object()
    monkeypatch.setattr(facade, "approve", lambda mission_id: None)
    monkeypatch.setattr(facade, "recover_planning_scope_card", lambda mission_id: card)
    captured: dict[str, object] = {}

    def execute(recovered: object, **kwargs: object) -> object:
        captured.update(kwargs)
        assert recovered is card
        return receipt

    monkeypatch.setattr(facade, "execute_planning_foreground", execute)

    assert facade.start_approved_mission_foreground("MISSION-U03A") is receipt
    assert captured["expected_plan_hash"] is card.plan_hash
    assert isinstance(captured["lease_token"], str)
    assert len(captured["lease_token"]) >= 32
    assert captured["lease_token_environment"] == "AUTO_PM_EXECUTION_LEASE_TOKEN"


def _gate_event_count(root: Path) -> int:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])


def _move_to_acceptance_pending(missions: MissionService, key: str) -> None:
    pending = missions.get("MISSION-C04-001")
    missions.transition(
        mission_id=pending.mission_id,
        expected_version=pending.version,
        new_state=MissionState.ACCEPTANCE_PENDING,
        root_work_id=pending.root_work_id,
        idempotency_key=key,
    )


def test_acceptance_gate_reason_reports_a_mission_that_is_not_at_the_gate(
    tmp_path: Path,
) -> None:
    _, facade, _ = _verified_acceptance_ready(tmp_path)
    before = _gate_event_count(tmp_path)

    reason = facade.acceptance_gate_reason("MISSION-C04-001")

    assert reason == "当前 Mission 尚未到达用户验收门"
    assert _gate_event_count(tmp_path) == before


def test_acceptance_gate_reason_is_empty_only_when_accept_would_pass(tmp_path: Path) -> None:
    missions, facade, _ = _verified_acceptance_ready(tmp_path)
    _move_to_acceptance_pending(missions, "c04-gate-reason-current")
    before = _gate_event_count(tmp_path)

    assert facade.acceptance_gate_reason("MISSION-C04-001") == ""
    assert _gate_event_count(tmp_path) == before
    assert facade._store.get_run("RUN-C04-001").state is RunState.VERIFYING
    assert missions.get("MISSION-C04-001").state is MissionState.ACCEPTANCE_PENDING
    assert facade.accept("MISSION-C04-001").mission_state is MissionState.ACCEPTED


def test_acceptance_gate_reason_matches_the_accept_refusal_after_content_changes(
    tmp_path: Path,
) -> None:
    missions, facade, _ = _verified_acceptance_ready(tmp_path)
    (tmp_path / "project" / "auto_pm" / "core" / "target.py").write_text(
        "def value() -> int:\n    return 2\n", encoding="utf-8"
    )
    _move_to_acceptance_pending(missions, "c04-gate-reason-stale")
    before = _gate_event_count(tmp_path)

    reason = facade.acceptance_gate_reason("MISSION-C04-001")

    with pytest.raises(PmFacadeError) as refusal:
        facade.accept("MISSION-C04-001")
    assert reason
    assert reason == str(refusal.value)
    assert "证据" in reason
    assert _gate_event_count(tmp_path) == before


def test_acceptance_gate_reason_matches_the_accept_refusal_when_the_run_failed(
    tmp_path: Path,
) -> None:
    missions, facade, execution = _verified_acceptance_ready(tmp_path)
    execution.transition_run(
        "RUN-C04-001",
        RunState.FAILED,
        "c04-test",
        "c04-test-lease",
        "c04-gate-reason-failed",
    )
    _move_to_acceptance_pending(missions, "c04-gate-reason-failed-pending")

    reason = facade.acceptance_gate_reason("MISSION-C04-001")

    with pytest.raises(PmFacadeError) as refusal:
        facade.accept("MISSION-C04-001")
    assert reason == str(refusal.value)
    assert "Run" in reason


def test_acceptance_gate_reason_requires_a_checkpoint_on_the_latest_run(
    tmp_path: Path,
) -> None:
    missions, facade = _setup(tmp_path)
    facade.plan("MISSION-PM-001")
    facade.approve("MISSION-PM-001", "WORK-PM-001")
    active = missions.get("MISSION-PM-001")
    missions.transition(
        mission_id=active.mission_id,
        expected_version=active.version,
        new_state=MissionState.ACCEPTANCE_PENDING,
        root_work_id=active.root_work_id,
        idempotency_key="gate-reason-no-run",
    )

    reason = facade.acceptance_gate_reason("MISSION-PM-001")

    assert "Run" in reason
    with pytest.raises(PmFacadeError) as refusal:
        facade.accept("MISSION-PM-001")
    assert reason == str(refusal.value)


def _unverified_run_ready(root: Path) -> tuple[MissionService, PmFacadeService, ContinuityExecutionService]:
    """Mission at the acceptance gate whose only Run is RUNNING, without any Checkpoint."""
    missions, facade = _setup(root)
    (root / ".gitignore").write_text(".auto-pm/\n__pycache__/\n", encoding="utf-8")
    (root / "pm.py").write_text("VALUE = 1\n", encoding="utf-8")
    facade.plan("MISSION-PM-001")
    facade.approve("MISSION-PM-001", "WORK-PM-001")
    head = _commit_baseline(root)
    execution = ContinuityExecutionService(root, store=facade._store)
    execution.start_run(
        run_id="RUN-GATE-001",
        work_id="WORK-PM-001",
        executor_id="gate-test",
        adapter="test",
        owned_paths=["pm.py"],
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head=head,
        worktree_path=str(root),
        lease_token="gate-lease",
        lease_seconds=900,
        idempotency_key="gate-run-create",
    )
    execution.transition_run(
        "RUN-GATE-001", RunState.RUNNING, "gate-test", "gate-lease", "gate-run-running"
    )
    active = missions.get("MISSION-PM-001")
    missions.transition(
        mission_id=active.mission_id,
        expected_version=active.version,
        new_state=MissionState.ACCEPTANCE_PENDING,
        root_work_id=active.root_work_id,
        idempotency_key="gate-pending",
    )
    return missions, facade, execution


def test_acceptance_gate_reason_requires_the_latest_run_to_be_verifying(tmp_path: Path) -> None:
    _, facade, _ = _unverified_run_ready(tmp_path)
    before = _gate_event_count(tmp_path)

    reason = facade.acceptance_gate_reason("MISSION-PM-001")

    with pytest.raises(PmFacadeError) as refusal:
        facade.accept("MISSION-PM-001")
    assert reason == str(refusal.value)
    assert "VERIFYING" in reason
    assert _gate_event_count(tmp_path) == before


def test_acceptance_gate_reason_requires_a_checkpoint_on_a_verifying_run(tmp_path: Path) -> None:
    _, facade, execution = _unverified_run_ready(tmp_path)
    execution.transition_run(
        "RUN-GATE-001", RunState.VERIFYING, "gate-test", "gate-lease", "gate-run-verifying"
    )

    reason = facade.acceptance_gate_reason("MISSION-PM-001")

    with pytest.raises(PmFacadeError) as refusal:
        facade.accept("MISSION-PM-001")
    assert reason == str(refusal.value)
    assert "Checkpoint" in reason


def _approved_run_card(root: Path) -> tuple[PmFacadeService, PlanningScopeCard]:
    facade, _database, changes = _p10_facade(root)
    grant = PlanningExecutionGrant(
        adapter=ExecutionAdapterKind.CODEX,
        approved_model="agent-a",
        declared_dirty_paths=("auto_pm/example.py",),
        plan_checklist=full_checklist(),
    )
    card = facade.create_planning_scope_card(
        _planning_intent(),
        scope_paths=("auto_pm/example.py",),
        risks=("unit",),
        non_goals=("no refactor",),
        execution_grant=grant,
    )
    for state in ("submitted", "under_review", "approved"):
        changes.transition_status(
            card.change_id, state, approver="fubai", comment="human", project_id="SW-TEST-001"
        )
    facade.approve_planning_scope_card(
        card,
        expected_plan_hash=card.plan_hash,
        approver="fubai",
        approval_evidence_ref="user-confirmation:U07A-UNIT",
    )
    return facade, card


def _event_total(database: Path) -> int:
    with closing(sqlite3.connect(database)) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])


def _outcome(mission_id: str, *, verified: bool) -> PmRunOutcome:
    return PmRunOutcome(
        mission_id=mission_id,
        run_id="RUN-UNIT-001",
        receipt_status="VERIFYING",
        verified=verified,
        checkpoint_id="CP-RUN-UNIT-001-VERIFY" if verified else "",
        mission_state=MissionState.ACCEPTANCE_PENDING,
        message="unit",
    )


def test_run_outcome_binds_the_checkpoint_to_the_verified_flag() -> None:
    assert _outcome("MISSION-X", verified=True).checkpoint_id
    with pytest.raises(ValueError, match="checkpoint_id"):
        PmRunOutcome(
            mission_id="MISSION-X",
            run_id="RUN-X",
            receipt_status="VERIFYING",
            verified=True,
            mission_state=MissionState.ACTIVE,
            message="unit",
        )
    with pytest.raises(ValueError, match="checkpoint_id"):
        PmRunOutcome(
            mission_id="MISSION-X",
            run_id="RUN-X",
            receipt_status="FAILED",
            verified=False,
            checkpoint_id="CP-X",
            mission_state=MissionState.ACTIVE,
            message="unit",
        )
    with pytest.raises(ValueError, match="at most 200"):
        PmRunOutcome(
            mission_id="MISSION-X",
            run_id="RUN-X",
            receipt_status="FAILED",
            verified=False,
            mission_state=MissionState.ACTIVE,
            message="x" * 201,
        )


def test_verify_for_acceptance_refuses_a_mission_that_cannot_be_verified(tmp_path: Path) -> None:
    _, facade = _setup(tmp_path)
    before = _gate_event_count(tmp_path)

    with pytest.raises(PmFacadeError, match="不在可验证状态"):
        facade.verify_for_acceptance("MISSION-PM-001", lease_token="unit-lease")

    assert _gate_event_count(tmp_path) == before


def test_verify_for_acceptance_requires_the_latest_run_to_be_verifying(tmp_path: Path) -> None:
    _, facade, _ = _unverified_run_ready(tmp_path)
    before = _gate_event_count(tmp_path)

    with pytest.raises(PmFacadeError, match="未处于 VERIFYING"):
        facade.verify_for_acceptance("MISSION-PM-001", lease_token="gate-lease")

    assert _gate_event_count(tmp_path) == before


def test_verify_for_acceptance_reports_a_refused_checkpoint_without_changing_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missions, facade, execution = _unverified_run_ready(tmp_path)
    execution.transition_run(
        "RUN-GATE-001", RunState.VERIFYING, "gate-test", "gate-lease", "gate-run-verifying"
    )
    captured: dict[str, Any] = {}

    def refuse(_self: ContinuityExecutionService, **kwargs: Any) -> None:
        captured.update(kwargs)
        raise ContinuityExecutionError("simulated quality failure")

    monkeypatch.setattr(ContinuityExecutionService, "append_verified_checkpoint", refuse)
    before = _gate_event_count(tmp_path)

    outcome = facade.verify_for_acceptance("MISSION-PM-001", lease_token="gate-lease")

    assert outcome.verified is False
    assert outcome.checkpoint_id == ""
    assert outcome.message == "质量验证未通过，已保留现场；未进入验收。"
    assert outcome.mission_state is MissionState.ACCEPTANCE_PENDING
    assert "gate-lease" not in outcome.model_dump_json()
    assert captured == {
        "checkpoint_id": "CP-RUN-GATE-001-VERIFY",
        "run_id": "RUN-GATE-001",
        "owner_id": "gate-test",
        "lease_token": "gate-lease",
        "project_root": tmp_path,
        "profile": "generic",
    }
    assert _gate_event_count(tmp_path) == before
    assert missions.get("MISSION-PM-001").state is MissionState.ACCEPTANCE_PENDING


def test_run_approved_planning_rejects_a_drifted_plan_hash_before_any_effect(
    tmp_path: Path,
) -> None:
    facade, card = _approved_run_card(tmp_path)

    with pytest.raises(PmFacadeError, match="plan_hash"):
        facade.run_approved_planning(
            card,
            expected_plan_hash="0" * 64,
            lease_token="unit-lease",
            lease_token_environment="AUTO_PM_EXECUTION_LEASE_TOKEN",
        )

    assert facade._store.list_missions("SW-TEST-001", include_terminal=True) == ()


def test_run_approved_planning_skips_verification_when_execution_did_not_finish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    facade, card = _approved_run_card(tmp_path)
    receipt = ForegroundExecutionReceipt(
        operation_id="OP-UNIT",
        run_id="RUN-UNIT-001",
        status="PENDING",
        claim_sha256="a" * 64,
    )
    calls: list[str] = []

    def execute(_card: PlanningScopeCard, **_kwargs: object) -> ForegroundExecutionReceipt:
        calls.append("execute")
        return receipt

    def forbidden(*_args: object, **_kwargs: object) -> PmRunOutcome:
        raise AssertionError("verification must not run for an unfinished execution")

    monkeypatch.setattr(facade, "execute_planning_foreground", execute)
    monkeypatch.setattr(facade, "verify_for_acceptance", forbidden)

    first = facade.run_approved_planning(
        card,
        expected_plan_hash=card.plan_hash,
        lease_token="unit-lease",
        lease_token_environment="AUTO_PM_EXECUTION_LEASE_TOKEN",
    )
    database = tmp_path / ".auto-pm" / "p10-test.db"
    events = _event_total(database)
    second = facade.run_approved_planning(
        card,
        expected_plan_hash=card.plan_hash,
        lease_token="unit-lease",
        lease_token_environment="AUTO_PM_EXECUTION_LEASE_TOKEN",
    )

    assert first == second
    assert first.verified is False
    assert first.receipt_status == "PENDING"
    assert first.run_id == "RUN-UNIT-001"
    assert first.mission_state is MissionState.ACTIVE
    assert first.message == "执行未完成，未进行质量验证；已保留现场。"
    assert calls == ["execute", "execute"]
    assert _event_total(database) == events
    mission = facade.materialize_planning_mission(card)
    assert mission.root_work_id
    assert facade._store.get_work(mission.root_work_id).state is WorkState.IN_PROGRESS


def test_run_approved_planning_verifies_a_finished_execution_with_the_same_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    facade, card = _approved_run_card(tmp_path)
    receipt = ForegroundExecutionReceipt(
        operation_id="OP-UNIT",
        run_id="RUN-UNIT-001",
        status="VERIFYING",
        claim_sha256="a" * 64,
        process_id=1,
        session_id="session-unit",
        exit_code=0,
        projection_sha256="b" * 64,
    )
    seen: dict[str, str] = {}

    def verify(mission_id: str, *, lease_token: str) -> PmRunOutcome:
        seen["mission_id"] = mission_id
        seen["lease_token"] = lease_token
        return _outcome(mission_id, verified=True).model_copy(update={"receipt_status": "x"})

    monkeypatch.setattr(facade, "execute_planning_foreground", lambda *_a, **_k: receipt)
    monkeypatch.setattr(facade, "verify_for_acceptance", verify)

    outcome = facade.run_approved_planning(
        card,
        expected_plan_hash=card.plan_hash,
        lease_token="unit-lease",
        lease_token_environment="AUTO_PM_EXECUTION_LEASE_TOKEN",
    )

    assert seen == {
        "mission_id": facade.materialize_planning_mission(card).mission_id,
        "lease_token": "unit-lease",
    }
    assert outcome.verified is True
    assert outcome.receipt_status == "VERIFYING"


def _rehearsal_database_inventory(database: Path) -> dict[str, dict[str, object]]:
    inventory: dict[str, dict[str, object]] = {}
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = Path(str(database) + suffix)
        if path.exists():
            raw = path.read_bytes()
            inventory[suffix] = {
                "exists": True, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                "mtime_ns": path.stat().st_mtime_ns,
            }
        else:
            inventory[suffix] = {"exists": False}
    return inventory


def test_rehearsal_c11_f08_preview_is_physically_read_only_under_delete_journal(tmp_path: Path) -> None:
    """C11-RO: preview preserves source database and all sidecar bytes/existence/mtime."""
    facade, database, item = _audit_scene(tmp_path)
    card = _audit_card(facade, item)
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA journal_mode=DELETE").fetchone() == ("delete",)
    before = _rehearsal_database_inventory(database)
    assert before[""]["exists"] is True
    preview = facade.preview_planning_scope_card(
        _planning_intent(), scope_paths=("auto_pm/example.py",), risks=("Drift",),
        non_goals=("No deployment",),
        execution_grant=PlanningExecutionGrant(
            adapter=ExecutionAdapterKind.CODEX, approved_model="gpt-approved",
            declared_dirty_paths=("auto_pm/example.py",),
            plan_checklist=full_checklist(original="Audit failure"),
        ),
        classification=item.classification, intake_item_id=item.item_id,
    )
    assert preview == card
    assert _rehearsal_database_inventory(database) == before
    replay = facade.preview_planning_scope_card(
        _planning_intent(), scope_paths=("auto_pm/example.py",), risks=("Drift",),
        non_goals=("No deployment",),
        execution_grant=PlanningExecutionGrant(
            adapter=ExecutionAdapterKind.CODEX, approved_model="gpt-approved",
            declared_dirty_paths=("auto_pm/example.py",),
            plan_checklist=full_checklist(original="Audit failure"),
        ),
        classification=item.classification, intake_item_id=item.item_id,
    )
    assert replay == card
    assert _rehearsal_database_inventory(database) == before
