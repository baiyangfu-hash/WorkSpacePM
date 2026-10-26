"""TD-SW008-070: a new plan must be classified; the facade no longer files one under a default."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService

from auto_pm.contracts.intake import IntakeClassification, IntakeKind
from auto_pm.contracts.pm_facade import PlanningScopeCard
from auto_pm.infrastructure.intake_store import IntakeStore
from tests.core.test_pm_facade_service import _EXAMPLE_GRANT, _p10_facade, _planning_intent

_REFUSAL = "新需求必须分类"
_TABLES = ("planning_drafts", "planning_scope_cards", "planning_draft_intake_bindings", "events")


def _counts(database: Path) -> dict[str, int]:
    with closing(sqlite3.connect(database)) as conn:
        found = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in _TABLES
            if table in found
        }


def _python_stack(root: Path) -> None:
    """Register the fixture project's stack, from which a kind alone gets its technical domain."""

    (root / "SW-TEST-001" / ".copier-answers.yml").write_text(
        "project_id: SW-TEST-001\nproject_name: Classification fixture\nstack: python\n",
        encoding="utf-8",
        errors="replace",
    )


def _chg_files(root: Path) -> list[str]:
    return sorted(path.name for path in root.rglob("CHG-*.md"))


def _plan(facade: PmFacadeService, **options: Any) -> PlanningScopeCard:
    card = facade.create_planning_scope_card(
        _planning_intent(),
        scope_paths=("auto_pm/example.py",),
        risks=("Drift",),
        non_goals=("No deployment",),
        execution_grant=_EXAMPLE_GRANT,
        **options,
    )
    assert isinstance(card, PlanningScopeCard)
    return card


def test_an_unclassified_scope_card_is_refused_before_any_write(tmp_path: Path) -> None:
    facade, database, _changes = _p10_facade(tmp_path)
    before, files = _counts(database), _chg_files(tmp_path)

    with pytest.raises(PmFacadeError, match=_REFUSAL):
        _plan(facade)

    assert _counts(database) == before
    assert _chg_files(tmp_path) == files


def test_an_unclassified_draft_change_is_refused_before_any_write(tmp_path: Path) -> None:
    facade, database, _changes = _p10_facade(tmp_path)
    before, files = _counts(database), _chg_files(tmp_path)

    with pytest.raises(PmFacadeError, match=_REFUSAL):
        facade.create_planning_draft_change(_planning_intent())

    assert _counts(database) == before
    assert _chg_files(tmp_path) == files


def test_a_saved_draft_nothing_classified_cannot_become_a_pending_card(tmp_path: Path) -> None:
    facade, database, _changes = _p10_facade(tmp_path)
    draft = facade.create_planning_draft(_planning_intent())
    before = _counts(database)

    with pytest.raises(PmFacadeError, match=_REFUSAL):
        facade.submit_planning_scope_card(
            draft.request_id,
            scope_paths=("auto_pm/example.py",),
            risks=("Drift",),
            non_goals=("No deployment",),
            execution_grant=_EXAMPLE_GRANT,
            submitted_by="audit",
        )

    assert _counts(database) == before
    assert before["planning_scope_cards"] == 0


def test_a_classified_plan_is_filed_by_its_kind_not_by_the_old_default(tmp_path: Path) -> None:
    facade, _database, changes = _p10_facade(tmp_path)
    urgent = IntakeClassification(kind=IntakeKind.URGENT, domain="SCPT")

    card = _plan(facade, classification=urgent)

    change = changes.get_change_request(card.change_id, project_id="SW-TEST-001")
    assert change is not None
    # The old default was always DEF + normal; an urgent request is now filed as an urgent emergency.
    assert (change.business_nature, change.urgency) == ("EMRG", "urgent")


def test_a_classified_draft_carries_its_kind_into_the_plan_built_from_it(tmp_path: Path) -> None:
    facade, database, changes = _p10_facade(tmp_path)
    _python_stack(tmp_path)

    draft = facade.create_classified_planning_draft(_planning_intent(), IntakeKind.DEBT)

    bound = IntakeStore(tmp_path, database).get_planning_classification(draft.request_id)
    assert bound is not None and bound[0].kind is IntakeKind.DEBT
    # The plan needs no classification of its own: the draft's kind files it.
    submitted = facade.submit_planning_scope_card(
        draft.request_id,
        scope_paths=("auto_pm/example.py",),
        risks=("Drift",),
        non_goals=("No deployment",),
        execution_grant=_EXAMPLE_GRANT,
        submitted_by="audit",
    )
    change = changes.get_change_request(submitted.card.change_id, project_id="SW-TEST-001")
    assert change is not None and change.business_nature == "OPT"


def test_a_classified_draft_is_idempotent_and_refuses_another_kind(tmp_path: Path) -> None:
    facade, database, _changes = _p10_facade(tmp_path)
    _python_stack(tmp_path)
    first = facade.create_classified_planning_draft(_planning_intent(), IntakeKind.BUG)
    assert facade.create_classified_planning_draft(_planning_intent(), IntakeKind.BUG) == first
    before = _counts(database)

    with pytest.raises(PmFacadeError, match="不同的分类"):
        facade.create_classified_planning_draft(_planning_intent(), IntakeKind.ITERATION)

    assert _counts(database) == before


def test_a_change_needs_an_action_so_a_kind_alone_cannot_classify_it(tmp_path: Path) -> None:
    facade, database, _changes = _p10_facade(tmp_path)
    _python_stack(tmp_path)
    before = _counts(database)

    with pytest.raises(PmFacadeError):
        facade.create_classified_planning_draft(_planning_intent(), IntakeKind.CHANGE)

    assert _counts(database) == before
