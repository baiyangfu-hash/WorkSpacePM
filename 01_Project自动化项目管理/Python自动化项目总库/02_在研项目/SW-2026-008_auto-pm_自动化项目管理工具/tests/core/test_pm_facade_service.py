"""Behaviour tests for the state-free PM Facade."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.core.mission_service import MissionService
from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.core.work_registry_service import WorkRegistryService

from auto_pm.contracts.continuity import WorkKind, WorkState
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope, MissionState
from auto_pm.contracts.pm_facade import PmConfirmationKind, PmIntent
from auto_pm.infrastructure.continuity_store import ContinuityStore


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

    card = facade.accept("MISSION-PM-001")
    assert card.kind is PmConfirmationKind.ACCEPTANCE
    assert card.mission_state is MissionState.ACCEPTED


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

    assert schema_version == "continuity-store.v6"
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
