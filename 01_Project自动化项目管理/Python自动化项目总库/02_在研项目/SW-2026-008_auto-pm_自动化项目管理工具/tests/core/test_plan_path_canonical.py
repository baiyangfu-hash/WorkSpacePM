"""D-103: ``pm plan`` and ``pm approve`` must agree on how a plan path is spelled.

A scope path with a trailing slash used to be kept as typed by ``plan`` and then refused by the Mission authority
after the CHG and the Decision were already written. Plan now normalises both lists with one function, and approve
refuses a non-canonical card before it writes anything. Real store, real ChangeService, real Git temp repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.application.core.pm_facade_service import PmFacadeError
from auto_pm.contracts.pm_facade import (
    PlanningScopeCard,
    PmIntent,
    canonical_plan_path,
    canonical_plan_paths,
)
from tests.core.test_pm_pending_scope_card import SUBMITTER, _env, _grant
from tests.core.test_pm_run_e2e import CALC, CALC_TEST, PROJECT_ID
from tests.plan_filing_support import LEGACY_EQUIVALENT_FILING


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a/b/", "a/b"),
        ("a//b", "a/b"),
        ("./a/b", "a/b"),
        ("  a/b/  ", "a/b"),
        ("a/b", "a/b"),
    ],
)
def test_canonical_plan_path_gives_one_spelling(raw: str, expected: str) -> None:
    assert canonical_plan_path(raw) == expected


@pytest.mark.parametrize("raw", ["", ".", "/abs", "a/../b", "a\\b", "a/*.py"])
def test_unsafe_paths_are_left_for_the_existing_validators(raw: str) -> None:
    assert canonical_plan_path(raw) == raw.strip()


def test_scope_and_declared_use_the_same_function() -> None:
    grant = _grant(("a/b/",))
    scope, canon = canonical_plan_paths(("a/b/",), grant)
    assert scope == ("a/b",)
    assert canon is not None and canon.declared_dirty_paths == ("a/b",)
    assert grant.declared_dirty_paths == ("a/b/",)  # the caller's grant is not changed in place


def test_plan_with_trailing_slashes_approves_end_to_end(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-D103-001")
    scope = (f"{CALC}/", f"./{CALC_TEST}")

    submitted = env.submit("REQ-D103-001", scope=scope)

    assert submitted.card.scope_paths == (CALC, CALC_TEST)
    assert submitted.card.execution_grant.declared_dirty_paths == (CALC, CALC_TEST)
    result = env.approve("REQ-D103-001", submitted.card.plan_hash)
    assert result.mission_id and result.work_id and result.decision_id


def test_create_and_preview_normalise_the_same_way(tmp_path: Path) -> None:
    env = _env(tmp_path)
    draft = env.draft("REQ-D103-002")
    intent = PmIntent(
        request_id=draft.request_id,
        subject_project_id=draft.subject_project_id,
        objective=draft.objective,
        acceptance_criteria=draft.acceptance_criteria,
    )
    slashed = (f"{CALC}/", f"{CALC_TEST}/")

    created = env.facade.create_planning_scope_card(
        intent,
        scope_paths=slashed,
        risks=("r1",),
        non_goals=("no refactor",),
        execution_grant=_grant(slashed),
        classification=LEGACY_EQUIVALENT_FILING,
    )
    previewed = env.facade.preview_planning_scope_card(
        intent,
        scope_paths=slashed,
        risks=("r1",),
        non_goals=("no refactor",),
        execution_grant=_grant(slashed),
        classification=LEGACY_EQUIVALENT_FILING,
    )

    assert created.scope_paths == (CALC, CALC_TEST)
    assert previewed == created


def test_approve_refuses_a_non_canonical_stored_card_before_writing_anything(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    env.draft("REQ-D103-003")
    draft = env.store.get_planning_draft("REQ-D103-003")
    intent = PmIntent(
        request_id=draft.request_id,
        subject_project_id=draft.subject_project_id,
        objective=draft.objective,
        acceptance_criteria=draft.acceptance_criteria,
    )
    change_id = env.facade.create_planning_draft_change(
        intent, classification=LEGACY_EQUIVALENT_FILING
    )
    # A card as an older plan could have stored it: declared paths kept with a trailing slash.
    legacy = PlanningScopeCard.from_draft(
        draft,
        change_id=change_id,
        scope_paths=(f"{CALC}/", CALC_TEST),
        risks=("r1",),
        non_goals=("no refactor",),
        spec_sources=env.facade.bind_planning_draft_specs(intent),
        execution_grant=_grant((f"{CALC}/", CALC_TEST)),
    )
    env.store.submit_planning_scope_card(legacy, SUBMITTER)
    decisions = env.root / ".auto-pm" / "decisions"
    before = len(list(decisions.glob("*.json"))) if decisions.exists() else 0
    change_before = env.chg_status(change_id)

    with pytest.raises(PmFacadeError, match="declared_dirty_paths"):
        env.approve("REQ-D103-003", legacy.plan_hash)

    assert (len(list(decisions.glob("*.json"))) if decisions.exists() else 0) == before
    assert env.chg_status(change_id) == change_before
    assert env.store.list_missions(PROJECT_ID) == ()
