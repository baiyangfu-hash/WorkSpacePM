"""U09A: pre-approval scope cards are persisted, listed and approved by plan hash.

Every test runs on a real ContinuityStore, a real ChangeService and a real Git temp repository.
Scenario numbers (s01..s16) follow card 037 section 5.4.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.core.local_execution_orchestrator import LocalExecutionOrchestrator

from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.pm_facade import (
    PlanningApprovalResult,
    PlanningDraft,
    PlanningDraftOverview,
    PlanningExecutionGrant,
    PlanningScopeCard,
    PmIntent,
    SubmittedPlanningScopeCard,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.local_executor import LocalCodexExecutor
from tests.core.test_pm_run_e2e import (
    CALC,
    CALC_TEST,
    FIXED_CALC,
    GOOD_TESTS,
    LEASE_ENV,
    PROJECT_ID,
    _build_workspace,
    _helper_source,
)

if TYPE_CHECKING:
    from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService
else:
    from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService

OTHER_PROJECT = "SW-OTHER-001"
SCOPE = (CALC, CALC_TEST)
APPROVER = "fubai"
EVIDENCE = "user-confirmation:U09A-TEST-001"
SUBMITTER = "PM (Claude)"
COCKPIT_REQUEST = "REQ-COCKPIT-0123456789ABCDEF0123456789ABCDEF"
EVENT_KEYS = {"request_id", "revision", "plan_hash", "change_id", "submitted_by", "card_sha256"}


def _grant() -> PlanningExecutionGrant:
    return PlanningExecutionGrant(
        adapter=ExecutionAdapterKind.CODEX,
        approved_model="agent-a",
        declared_dirty_paths=SCOPE,
    )


def _add_project(root: Path, project_id: str) -> None:
    changes = root / project_id / "04_监控" / "01_变更管理"
    (changes / "01_变更单").mkdir(parents=True)
    (changes / "01_版本变更台帐.md").write_text(
        "# 台帐\n\n| 序号 | 变更编号 | 描述 |\n|---|---|---|\n", encoding="utf-8"
    )
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["projects"].append(
        {"project_id": project_id, "project_root": project_id, "development_root": project_id}
    )
    registry.write_text(json.dumps(payload), encoding="utf-8")


@dataclass
class _Env:
    root: Path
    store: ContinuityStore
    facade: PmFacadeService
    changes: ChangeService

    @property
    def db(self) -> Path:
        return self.root / ".auto-pm" / "continuity.db"

    def draft(
        self,
        request_id: str,
        *,
        project: str = PROJECT_ID,
        objective: str = "Fix add()",
    ) -> PlanningDraft:
        return self.facade.create_planning_draft(
            PmIntent(
                request_id=request_id,
                subject_project_id=project,
                objective=objective,
                acceptance_criteria=("add(2, 3) == 5",),
            )
        )

    def card(self, request_id: str, *, risks: tuple[str, ...] = ("r1",)) -> PlanningScopeCard:
        """Build the card of a persisted draft without persisting it (bindings are created)."""

        draft = self.store.get_planning_draft(request_id)
        return self.facade.create_planning_scope_card(
            PmIntent(
                request_id=draft.request_id,
                subject_project_id=draft.subject_project_id,
                objective=draft.objective,
                acceptance_criteria=draft.acceptance_criteria,
            ),
            scope_paths=SCOPE,
            risks=risks,
            non_goals=("no refactor",),
            execution_grant=_grant(),
        )

    def submit(
        self,
        request_id: str,
        *,
        risks: tuple[str, ...] = ("r1",),
        submitter: str = SUBMITTER,
    ) -> SubmittedPlanningScopeCard:
        return self.facade.submit_planning_scope_card(
            request_id,
            scope_paths=SCOPE,
            risks=risks,
            non_goals=("no refactor",),
            execution_grant=_grant(),
            submitted_by=submitter,
        )

    def approve(
        self,
        request_id: str,
        plan_hash: str,
        *,
        approver: str = APPROVER,
        evidence: str = EVIDENCE,
        release: str = "",
    ) -> PlanningApprovalResult:
        return self.facade.approve_pending_planning_scope_card(
            request_id,
            expected_plan_hash=plan_hash,
            approver=approver,
            approval_evidence_ref=evidence,
            admission_release_ref=release,
        )

    def chg_status(self, change_id: str, project: str = PROJECT_ID) -> str:
        change = self.changes.get_change_request(change_id, project_id=project)
        assert change is not None
        return str(change.status)

    def count(self, table: str) -> int:
        with closing(sqlite3.connect(self.db)) as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def events(self, event_type: str = "") -> list[tuple[str, str, str]]:
        query = "SELECT event_type, aggregate_id, payload_json FROM events"
        args: tuple[str, ...] = ()
        if event_type:
            query += " WHERE event_type=?"
            args = (event_type,)
        with closing(sqlite3.connect(self.db)) as conn:
            return [(str(r[0]), str(r[1]), str(r[2])) for r in conn.execute(query + " ORDER BY rowid", args)]

    def state(self) -> tuple[int, int]:
        """(scope card rows, event rows) - the pair every refusal must leave unchanged."""

        with closing(sqlite3.connect(self.db)) as conn:
            has_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='planning_scope_cards'"
            ).fetchone()
            cards = conn.execute("SELECT COUNT(*) FROM planning_scope_cards").fetchone()[0] if has_table else 0
            events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return int(cards), int(events)

    def sql(self, statement: str, *args: str) -> None:
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute(statement, args)

    def scalars(self, statement: str) -> list[str]:
        with closing(sqlite3.connect(self.db)) as conn:
            return [str(row[0]) for row in conn.execute(statement)]

    def chain_is_intact(self) -> bool:
        with closing(sqlite3.connect(self.db)) as conn:
            conn.row_factory = sqlite3.Row
            previous = ""
            for row in conn.execute("SELECT * FROM events ORDER BY rowid"):
                expected = hashlib.sha256(
                    f"{previous}|{row['aggregate_id']}|{row['event_type']}|"
                    f"{row['payload_json']}|{row['created_at']}".encode()
                ).hexdigest()
                if row["previous_hash"] != previous or row["event_hash"] != expected:
                    return False
                previous = str(row["event_hash"])
        return True

    def settled_sha(self) -> str:
        """Hash the database file after merging the WAL so a read can be proven write-free."""

        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        wal = Path(f"{self.db}-wal")
        assert not wal.exists() or wal.stat().st_size == 0
        return hashlib.sha256(self.db.read_bytes()).hexdigest()

    def approve_change(self, change_id: str, project: str = PROJECT_ID) -> None:
        for state in ("submitted", "under_review", "approved"):
            self.changes.transition_status(
                change_id, state, approver=APPROVER, comment="human", project_id=project
            )


def _env(tmp_path: Path, *, with_executor: bool = False, name: str = "ws") -> _Env:
    root = (tmp_path / name).resolve()
    _build_workspace(root)
    store = ContinuityStore(root)
    store.initialize(datetime.now(UTC).isoformat(), "u09a-test")
    changes = ChangeService(str(root))
    if with_executor:
        helper = tmp_path / f"{name}-fake_codex.py"
        helper.write_text(
            _helper_source(
                calc=FIXED_CALC, tests=GOOD_TESTS, exit_code=0, counter=tmp_path / f"{name}-starts.txt"
            ),
            encoding="utf-8",
        )
        facade = PmFacadeService(
            root,
            store=store,
            change_service=changes,
            local_orchestrator=LocalExecutionOrchestrator(
                root,
                store=store,
                executor=LocalCodexExecutor(command_prefix=(sys.executable, str(helper))),
            ),
        )
    else:
        facade = PmFacadeService(root, store=store, change_service=changes)
    return _Env(root, store, facade, changes)


# --------------------------------------------------------------------------- s01 / s02: additive table, no schema bump


def test_s01_new_table_is_appended_without_a_schema_bump(tmp_path: Path) -> None:
    env = _env(tmp_path)
    tables = set(env.scalars("SELECT name FROM sqlite_master WHERE type='table'"))
    assert "planning_scope_cards" in tables
    assert env.scalars("SELECT schema_version FROM schema_meta") == ["continuity-store.v8"]
    assert env.count("schema_migrations") == 0


def test_s01_a_v7_store_without_the_table_lists_nothing_and_creates_it_on_first_submit(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    env.sql("DROP TABLE planning_scope_cards")
    meta = env.scalars("SELECT schema_version || '|' || created_at FROM schema_meta")
    assert env.store.list_pending_planning_scope_cards(PROJECT_ID) == ()
    assert env.scalars("SELECT name FROM sqlite_master WHERE name='planning_scope_cards'") == []

    env.draft("REQ-S01-001")
    env.submit("REQ-S01-001")

    assert env.scalars("SELECT name FROM sqlite_master WHERE name='planning_scope_cards'") == [
        "planning_scope_cards"
    ]
    assert env.scalars("SELECT schema_version || '|' || created_at FROM schema_meta") == meta
    assert env.count("schema_migrations") == 0
    assert len(env.store.list_pending_planning_scope_cards(PROJECT_ID)) == 1


def test_s02_the_live_two_row_schema_meta_shape_behaves_the_same(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.sql("DELETE FROM schema_meta")
    env.sql("INSERT INTO schema_meta VALUES ('continuity-store.v3', 'x', '1.3.0')")
    env.sql("INSERT INTO schema_meta VALUES ('continuity-store.v2', 'x', '1.3.3')")
    env.sql("DROP TABLE planning_scope_cards")
    expected = ["continuity-store.v2", "continuity-store.v3"]

    assert env.store.list_pending_planning_scope_cards(PROJECT_ID) == ()
    env.draft("REQ-S02-001")
    submitted = env.submit("REQ-S02-001")
    assert env.store.list_pending_planning_scope_cards(PROJECT_ID) == (submitted,)
    assert env.store.get_submitted_planning_scope_card("REQ-S02-001", submitted.card.plan_hash) == submitted
    env.store.initialize("2026-10-01T00:00:00+00:00", "u09a-test")

    assert env.scalars("SELECT schema_version FROM schema_meta ORDER BY 1") == expected
    assert env.count("schema_migrations") == 0
    assert env.chain_is_intact()


# --------------------------------------------------------------------------- s03: reads never write


def test_s03_reads_leave_the_database_bytes_untouched(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S03-001")
    submitted = env.submit("REQ-S03-001")
    before = env.settled_sha()

    assert env.store.list_pending_planning_scope_cards(PROJECT_ID) == (submitted,)
    assert env.store.get_submitted_planning_scope_card("REQ-S03-001", submitted.card.plan_hash) == submitted
    assert len(env.store.list_planning_drafts(PROJECT_ID)) == 1

    assert env.settled_sha() == before


def test_s03_reads_without_the_table_do_not_create_it(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S03-002")
    env.sql("DROP TABLE planning_scope_cards")
    before = env.settled_sha()

    assert env.store.list_pending_planning_scope_cards(PROJECT_ID) == ()
    overview = env.store.list_planning_drafts(PROJECT_ID)
    assert [item.card_revision for item in overview] == [0]
    with pytest.raises(ContinuityStoreError):
        env.store.get_submitted_planning_scope_card("REQ-S03-002", "a" * 64)

    assert env.settled_sha() == before
    assert env.scalars("SELECT name FROM sqlite_master WHERE name='planning_scope_cards'") == []


# --------------------------------------------------------------------------- s04 / s05 / s06: submit, round trip, revisions


def test_s04_submit_appends_one_row_and_one_chained_event_and_replays_idempotently(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S04-001")
    card = env.card("REQ-S04-001")
    cards_before, events_before = env.state()

    assert env.store.submit_planning_scope_card(card, SUBMITTER) == 1
    submitted = env.store.get_submitted_planning_scope_card("REQ-S04-001", card.plan_hash)

    assert submitted.revision == 1
    assert env.state() == (cards_before + 1, events_before + 1)
    events = env.events("PLANNING_SCOPE_CARD_SUBMITTED")
    assert len(events) == 1
    assert events[0][1] == "REQ-S04-001"
    payload = json.loads(events[0][2])
    assert set(payload) == EVENT_KEYS
    assert payload["revision"] == 1
    assert payload["plan_hash"] == submitted.card.plan_hash
    assert payload["change_id"] == submitted.card.change_id
    assert payload["submitted_by"] == SUBMITTER
    stored = env.scalars("SELECT card_json FROM planning_scope_cards")[0]
    assert payload["card_sha256"] == hashlib.sha256(stored.encode("utf-8")).hexdigest()
    assert env.chain_is_intact()

    replay = env.submit("REQ-S04-001")
    assert replay.revision == 1
    assert env.state() == (cards_before + 1, events_before + 1)


def test_s05_listed_card_equals_the_submitted_card_field_by_field(tmp_path: Path) -> None:
    env = _env(tmp_path)
    draft = env.draft("REQ-S05-001", objective="Fix add() for real")
    submitted = env.submit("REQ-S05-001")

    pending = env.store.list_pending_planning_scope_cards(PROJECT_ID)

    assert pending == (submitted,)
    assert pending[0].card == submitted.card
    assert pending[0].objective == draft.objective == "Fix add() for real"
    assert pending[0].revision == 1
    assert pending[0].superseded is False
    assert pending[0].submitted_by == SUBMITTER
    assert pending[0].submitted_at
    assert pending[0].card.scope_paths == SCOPE
    assert pending[0].card.execution_grant == _grant()
    assert env.facade._planning_scope_card_hash(pending[0].card) == pending[0].card.plan_hash


def test_s06_a_new_revision_supersedes_the_old_one(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S06-001")
    first = env.submit("REQ-S06-001", risks=("r1",))
    second = env.submit("REQ-S06-001", risks=("r2",))

    assert (first.revision, second.revision) == (1, 2)
    assert first.card.plan_hash != second.card.plan_hash
    assert env.store.list_pending_planning_scope_cards(PROJECT_ID) == (second,)
    old = env.store.get_submitted_planning_scope_card("REQ-S06-001", first.card.plan_hash)
    assert old.revision == 1
    assert old.superseded is True
    assert old.card == first.card
    assert env.store.get_submitted_planning_scope_card("REQ-S06-001", second.card.plan_hash).superseded is False
    assert env.count("planning_scope_cards") == 2
    # Replaying the older revision must not resurrect it or create a third one.
    assert env.submit("REQ-S06-001", risks=("r1",)).revision == 1
    assert env.count("planning_scope_cards") == 2
    assert env.store.list_pending_planning_scope_cards(PROJECT_ID) == (second,)


# --------------------------------------------------------------------------- s07: tampering is refused as a whole


@pytest.mark.parametrize("column", ["card_json", "plan_hash", "change_id"])
def test_s07_a_tampered_record_fails_every_read_and_returns_nothing(
    tmp_path: Path, column: str
) -> None:
    env = _env(tmp_path)
    for request_id in ("REQ-S07-CLEAN", "REQ-S07-TAMPERED"):
        env.draft(request_id)
    clean = env.submit("REQ-S07-CLEAN")
    tampered = env.submit("REQ-S07-TAMPERED")
    assert len(env.store.list_pending_planning_scope_cards(PROJECT_ID)) == 2

    if column == "card_json":
        stored = env.scalars("SELECT card_json FROM planning_scope_cards WHERE request_id='REQ-S07-TAMPERED'")[0]
        assert CALC in stored
        env.sql(
            "UPDATE planning_scope_cards SET card_json=? WHERE request_id='REQ-S07-TAMPERED'",
            stored.replace(CALC, f"{PROJECT_ID}/src/evil.py"),
        )
    elif column == "plan_hash":
        env.sql("UPDATE planning_scope_cards SET plan_hash=? WHERE request_id='REQ-S07-TAMPERED'", "f" * 64)
    else:
        env.sql(
            "UPDATE planning_scope_cards SET change_id=? WHERE request_id='REQ-S07-TAMPERED'",
            "CHG-SCPT-2026-998",
        )

    with pytest.raises(ContinuityStoreError):
        env.store.list_pending_planning_scope_cards(PROJECT_ID)
    with pytest.raises(ContinuityStoreError):
        env.store.get_submitted_planning_scope_card("REQ-S07-TAMPERED", tampered.card.plan_hash)
    if column == "plan_hash":
        with pytest.raises(ContinuityStoreError):
            env.store.get_submitted_planning_scope_card("REQ-S07-TAMPERED", "f" * 64)
    # The untouched record is still readable on its own, but never returned by the failed listing.
    assert env.store.get_submitted_planning_scope_card("REQ-S07-CLEAN", clean.card.plan_hash) == clean


# --------------------------------------------------------------------------- s08: submit refusals write nothing


def test_s08_unknown_request_is_refused_without_writes(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S08-001")
    card = env.submit("REQ-S08-001").card
    before = env.state()

    with pytest.raises(ContinuityStoreError, match="不存在"):
        env.store.submit_planning_scope_card(card.model_copy(update={"request_id": "REQ-UNKNOWN-001"}), SUBMITTER)

    assert env.state() == before


def test_s08_a_card_for_a_different_change_is_refused_without_writes(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S08-002")
    card = env.submit("REQ-S08-002").card
    before = env.state()

    with pytest.raises(ContinuityStoreError, match="CHG"):
        env.store.submit_planning_scope_card(card.model_copy(update={"change_id": "CHG-SCPT-2026-998"}), SUBMITTER)

    assert env.state() == before


def test_s08_a_card_with_different_spec_sources_is_refused_without_writes(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S08-003")
    card = env.submit("REQ-S08-003").card
    before = env.state()
    drifted = tuple((spec_id, path, "V9") for spec_id, path, _version in card.spec_sources)

    with pytest.raises(ContinuityStoreError, match="规范"):
        env.store.submit_planning_scope_card(card.model_copy(update={"spec_sources": drifted}), SUBMITTER)

    assert env.state() == before


def test_s08_a_card_whose_hash_does_not_match_its_content_is_refused_without_writes(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S08-004")
    card = env.submit("REQ-S08-004").card
    before = env.state()

    with pytest.raises(ContinuityStoreError, match="plan_hash"):
        env.store.submit_planning_scope_card(card.model_copy(update={"plan_hash": "0" * 64}), SUBMITTER)
    with pytest.raises(ContinuityStoreError, match="plan_hash"):
        env.store.submit_planning_scope_card(card.model_copy(update={"risks": ("changed",)}), SUBMITTER)

    assert env.state() == before


@pytest.mark.parametrize("submitter", ["", "   ", " lead", "trail ", "x" * 81, "bad\nname"])
def test_s08_a_non_canonical_submitter_is_refused_without_writes(
    tmp_path: Path, submitter: str
) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S08-005")
    card = env.submit("REQ-S08-005").card
    before = env.state()

    with pytest.raises(ContinuityStoreError, match="submitted_by"):
        env.store.submit_planning_scope_card(card, submitter)
    with pytest.raises(PmFacadeError):
        env.submit("REQ-S08-005", risks=("another",), submitter=submitter)

    assert env.state() == before


def test_s08_an_approved_request_accepts_no_further_revision(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S08-006")
    submitted = env.submit("REQ-S08-006")
    env.approve("REQ-S08-006", submitted.card.plan_hash)
    before = env.state()

    with pytest.raises(PmFacadeError, match="已批准"):
        env.submit("REQ-S08-006", risks=("late",))
    replacement = env.card("REQ-S08-006", risks=("late",))
    with pytest.raises(ContinuityStoreError, match="已批准"):
        env.store.submit_planning_scope_card(replacement, SUBMITTER)

    assert env.state() == before


def test_s08_the_facade_requires_an_existing_draft_and_an_explicit_grant(tmp_path: Path) -> None:
    env = _env(tmp_path)
    with pytest.raises(PmFacadeError, match="不存在"):
        env.submit("REQ-S08-MISSING")
    env.draft("REQ-S08-007")
    before = env.state()
    arguments: dict[str, Any] = {
        "scope_paths": SCOPE,
        "risks": ("r1",),
        "non_goals": ("n1",),
        "execution_grant": None,
        "submitted_by": SUBMITTER,
    }
    with pytest.raises(PmFacadeError, match="execution_grant"):
        env.facade.submit_planning_scope_card("REQ-S08-007", **arguments)
    assert env.state() == before


# --------------------------------------------------------------------------- s09 / s10 / s11: approval by hash


def test_s09_approval_by_hash_builds_the_whole_authorization_chain(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft(COCKPIT_REQUEST)
    submitted = env.submit(COCKPIT_REQUEST)
    card = submitted.card
    assert env.chg_status(card.change_id) == "draft"

    result = env.approve(COCKPIT_REQUEST, card.plan_hash)

    assert env.chg_status(card.change_id) == "approved"
    decision = env.facade._decisions.get_decision(result.decision_id)
    assert decision.metadata["planning_approval"] == {
        "schema_version": "planning-approval.v2",
        "plan_hash": card.plan_hash,
        "approval_evidence_ref": EVIDENCE,
        "request_id": COCKPIT_REQUEST,
        "execution_grant": card.execution_grant.model_dump(mode="json"),
    }
    assert decision.approver == APPROVER
    assert decision.approved_files == list(card.scope_paths)
    mission = env.store.get_mission(result.mission_id)
    assert mission.state is MissionState.DRAFT
    assert mission.authority.decision_id == result.decision_id
    assert mission.authority.change_id == card.change_id
    work = env.store.get_work(result.work_id)
    assert work.subject_project_id == PROJECT_ID
    assert work.work_id == result.work_id
    assert result == PlanningApprovalResult(
        request_id=COCKPIT_REQUEST,
        subject_project_id=PROJECT_ID,
        change_id=card.change_id,
        plan_hash=card.plan_hash,
        decision_id=result.decision_id,
        mission_id=result.mission_id,
        work_id=result.work_id,
    )
    assert env.store.list_pending_planning_scope_cards(PROJECT_ID) == ()
    assert env.facade.recover_planning_scope_card(result.mission_id) == card


def test_s09_a_change_already_under_review_is_completed_to_approved(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S09-002")
    card = env.submit("REQ-S09-002").card
    env.changes.transition_status(card.change_id, "submitted", approver=APPROVER, comment="human", project_id=PROJECT_ID)
    env.changes.transition_status(card.change_id, "under_review", approver=APPROVER, comment="human", project_id=PROJECT_ID)

    env.approve("REQ-S09-002", card.plan_hash)

    assert env.chg_status(card.change_id) == "approved"


def test_s10_approval_replay_is_idempotent(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S10-001")
    card = env.submit("REQ-S10-001").card
    first = env.approve("REQ-S10-001", card.plan_hash)
    counts = {
        table: env.count(table)
        for table in ("planning_draft_decision_bindings", "mission_items", "work_items", "events")
    }
    decisions_before = len(list((env.root / ".auto-pm" / "decisions").glob("*.json")))

    second = env.approve("REQ-S10-001", card.plan_hash)

    assert second == first
    assert {table: env.count(table) for table in counts} == counts
    assert len(list((env.root / ".auto-pm" / "decisions").glob("*.json"))) == decisions_before
    assert env.chain_is_intact()


def test_s11_a_model_signed_approval_is_refused_before_any_write(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S11-001")
    card = env.submit("REQ-S11-001").card
    before, status = env.state(), env.chg_status(card.change_id)

    with pytest.raises(PmFacadeError, match="自签"):
        env.approve("REQ-S11-001", card.plan_hash, approver="gpt-5")

    assert (env.state(), env.chg_status(card.change_id)) == (before, status)
    assert env.count("planning_draft_decision_bindings") == 0


def test_s11_evidence_that_is_not_a_user_confirmation_is_refused_before_any_write(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S11-002")
    card = env.submit("REQ-S11-002").card
    before, status = env.state(), env.chg_status(card.change_id)

    with pytest.raises(PmFacadeError, match="user-confirmation"):
        env.approve("REQ-S11-002", card.plan_hash, evidence="chat-said-ok-123")

    assert (env.state(), env.chg_status(card.change_id)) == (before, status)


def test_s11_an_unknown_hash_is_refused_before_any_write(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S11-003")
    card = env.submit("REQ-S11-003").card
    before, status = env.state(), env.chg_status(card.change_id)

    with pytest.raises(PmFacadeError):
        env.approve("REQ-S11-003", "a" * 64)
    with pytest.raises(PmFacadeError):
        env.approve("REQ-S11-NOPE", card.plan_hash)

    assert (env.state(), env.chg_status(card.change_id)) == (before, status)


def test_s11_a_superseded_revision_cannot_be_approved(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S11-004")
    first = env.submit("REQ-S11-004", risks=("r1",)).card
    second = env.submit("REQ-S11-004", risks=("r2",)).card
    before, status = env.state(), env.chg_status(first.change_id)

    with pytest.raises(PmFacadeError, match="取代"):
        env.approve("REQ-S11-004", first.plan_hash)

    assert (env.state(), env.chg_status(first.change_id)) == (before, status)
    assert env.approve("REQ-S11-004", second.plan_hash).plan_hash == second.plan_hash


def test_s11_replaying_with_another_approver_is_refused_and_creates_nothing(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S11-005")
    card = env.submit("REQ-S11-005").card
    env.approve("REQ-S11-005", card.plan_hash)
    before, status = env.state(), env.chg_status(card.change_id)
    bindings = env.count("planning_draft_decision_bindings")

    with pytest.raises(PmFacadeError, match="不同批准"):
        env.approve("REQ-S11-005", card.plan_hash, approver="baiyang")

    assert (env.state(), env.chg_status(card.change_id)) == (before, status)
    assert env.count("planning_draft_decision_bindings") == bindings == 1


def test_s11_a_rejected_change_cannot_be_approved_and_nothing_is_written(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S11-006")
    card = env.submit("REQ-S11-006").card
    env.changes.transition_status(card.change_id, "submitted", approver=APPROVER, comment="human", project_id=PROJECT_ID)
    env.changes.transition_status(card.change_id, "under_review", approver=APPROVER, comment="human", project_id=PROJECT_ID)
    env.changes.transition_status(card.change_id, "rejected", approver=APPROVER, comment="human", project_id=PROJECT_ID)
    before = env.state()

    with pytest.raises(PmFacadeError):
        env.approve("REQ-S11-006", card.plan_hash)

    assert env.state() == before
    assert env.count("planning_draft_decision_bindings") == 0


# --------------------------------------------------------------------------- s12 / s13: overview and project isolation


def test_s12_the_overview_reports_each_draft_stage_and_cockpit_drafts(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S12-NOCARD")
    env.draft("REQ-S12-PENDING")
    env.draft(COCKPIT_REQUEST, objective="Created from the cockpit")
    env.draft("REQ-S12-APPROVED")
    pending = env.submit("REQ-S12-PENDING", risks=("r1",))
    env.submit("REQ-S12-PENDING", risks=("r2",))
    approved = env.submit("REQ-S12-APPROVED")
    env.approve("REQ-S12-APPROVED", approved.card.plan_hash)

    overview = {item.draft.request_id: item for item in env.facade.list_planning_drafts(PROJECT_ID)}

    assert set(overview) == {"REQ-S12-NOCARD", "REQ-S12-PENDING", COCKPIT_REQUEST, "REQ-S12-APPROVED"}
    assert (overview["REQ-S12-NOCARD"].card_revision, overview["REQ-S12-NOCARD"].approved) == (0, False)
    assert overview["REQ-S12-NOCARD"].change_id == ""
    assert (overview["REQ-S12-PENDING"].card_revision, overview["REQ-S12-PENDING"].approved) == (2, False)
    assert overview["REQ-S12-PENDING"].change_id == pending.card.change_id
    assert (overview["REQ-S12-APPROVED"].card_revision, overview["REQ-S12-APPROVED"].approved) == (1, True)
    cockpit = overview[COCKPIT_REQUEST]
    assert isinstance(cockpit, PlanningDraftOverview)
    assert cockpit.draft.objective == "Created from the cockpit"
    assert cockpit.draft.acceptance_criteria == ("add(2, 3) == 5",)
    assert cockpit.created_at
    assert (cockpit.card_revision, cockpit.approved) == (0, False)
    assert env.facade.list_planning_drafts(PROJECT_ID) == env.store.list_planning_drafts(PROJECT_ID)


def test_s13_another_project_never_appears_in_either_list(tmp_path: Path) -> None:
    env = _env(tmp_path)
    _add_project(env.root, OTHER_PROJECT)
    env.draft("REQ-S13-MINE")
    env.draft("REQ-S13-THEIRS", project=OTHER_PROJECT)
    # CHG numbers are allocated per project; advance the other project's sequence so the two cards
    # do not compete for the same globally unique candidate identifier.
    env.changes.create_change_request(
        project_id=OTHER_PROJECT,
        domain="SCPT",
        business_nature="DEF",
        impact_scope=["MODULE"],
        applicant="PM Facade",
        background="filler change that advances the sequence",
        necessity="isolate the two projects' candidate identifiers",
    )
    mine = env.submit("REQ-S13-MINE")
    theirs = env.facade.submit_planning_scope_card(
        "REQ-S13-THEIRS",
        scope_paths=SCOPE,
        risks=("r1",),
        non_goals=("n1",),
        execution_grant=_grant(),
        submitted_by=SUBMITTER,
    )

    assert env.facade.list_pending_planning_scope_cards(PROJECT_ID) == (mine,)
    assert env.facade.list_pending_planning_scope_cards(OTHER_PROJECT) == (theirs,)
    assert [item.draft.request_id for item in env.facade.list_planning_drafts(PROJECT_ID)] == ["REQ-S13-MINE"]
    assert [item.draft.request_id for item in env.facade.list_planning_drafts(OTHER_PROJECT)] == ["REQ-S13-THEIRS"]
    assert env.facade.list_pending_planning_scope_cards("SW-NOBODY-001") == ()


# --------------------------------------------------------------------------- s14: nothing starts executing


def test_s14_submit_list_and_approve_never_create_a_run_or_a_lease(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S14-001")
    card = env.submit("REQ-S14-001").card
    env.facade.list_pending_planning_scope_cards(PROJECT_ID)
    env.facade.list_planning_drafts(PROJECT_ID)
    env.approve("REQ-S14-001", card.plan_hash)

    assert env.count("run_items") == 0
    assert env.count("execution_leases") == 0
    assert env.count("checkpoints") == 0
    assert env.count("mission_items") == 1
    assert env.count("work_items") == 1


# --------------------------------------------------------------------------- s15: the real chain


def test_s15_cockpit_draft_to_accepted_runs_through_the_persisted_card(tmp_path: Path) -> None:
    env = _env(tmp_path, with_executor=True)
    env.draft(COCKPIT_REQUEST)
    submitted = env.submit(COCKPIT_REQUEST)
    listed = env.facade.list_pending_planning_scope_cards(PROJECT_ID)
    assert listed == (submitted,)

    result = env.approve(COCKPIT_REQUEST, listed[0].card.plan_hash)
    card = env.facade.recover_planning_scope_card(result.mission_id)
    outcome = env.facade.run_approved_planning(
        card,
        expected_plan_hash=card.plan_hash,
        lease_token=secrets.token_urlsafe(32),
        lease_token_environment=LEASE_ENV,
    )

    assert outcome.verified is True
    assert outcome.mission_state is MissionState.ACCEPTANCE_PENDING
    assert outcome.mission_id == result.mission_id
    accepted = env.facade.accept(outcome.mission_id)
    assert accepted.mission_state is MissionState.ACCEPTED
    assert env.chain_is_intact()


# --------------------------------------------------------------------------- s16: the old route is unchanged


def test_s16_the_existing_authorization_route_works_without_any_persisted_card(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-S16-001")
    card = env.card("REQ-S16-001")
    env.approve_change(card.change_id)
    decision = env.facade.approve_planning_scope_card(
        card, expected_plan_hash=card.plan_hash, approver=APPROVER, approval_evidence_ref=EVIDENCE
    )
    mission = env.facade.materialize_planning_mission(card)
    work = env.facade.create_planning_work(card)

    assert env.count("planning_scope_cards") == 0
    assert env.facade.recover_planning_scope_card(mission.mission_id) == card
    assert decision.decision_id == mission.authority.decision_id
    assert work.work_id
    overview = env.facade.list_planning_drafts(PROJECT_ID)
    assert [(item.card_revision, item.approved) for item in overview] == [(0, True)]
    assert env.facade.list_pending_planning_scope_cards(PROJECT_ID) == ()
