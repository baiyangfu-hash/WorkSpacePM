"""U09C: the cockpit lists pending scope cards and applies the user's single approval.

Real ContinuityStore, ChangeService and Git temp repository (the U09A fixtures); the cockpit service is the unit under test.
Scenario ids p01..p14 are the service; k01..k05 are the presentation contract (card 040 section 5.4).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from auto_pm.application.core.pm_cockpit_service import PmCockpitError, PmCockpitService
from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.pm_cockpit import (
    CockpitUserAction,
    PmCockpitPendingScopeCard,
    PmCockpitSnapshot,
)
from tests.core.test_pm_pending_scope_card import COCKPIT_REQUEST, _Env, _env
from tests.core.test_pm_run_e2e import CALC, PROJECT_ID

_EVIDENCE = re.compile(r"user-confirmation:cockpit-[0-9a-f]{16}-[0-9a-f]{8}")
_INTERNAL_KEYS = {"mission_id", "decision_id", "work_id", "run_id", "lease_token", "token"}


def _service(env: _Env, *, approver: str = "fubai") -> PmCockpitService:
    return PmCockpitService(env.root, store=env.store, facade=env.facade, approver=approver)


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _all_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _all_keys(item)}
    return set()


def _pending(env: _Env, request_id: str = "REQ-U09C-A", *, risks: tuple[str, ...] = ("r1",)) -> str:
    """A draft with a persisted scope card; returns the plan hash."""

    env.draft(request_id)
    return env.submit(request_id, risks=risks).card.plan_hash


def _writes(env: _Env) -> tuple[object, ...]:
    return (
        env.state(),
        env.count("planning_draft_decision_bindings"),
        env.count("mission_items"),
        env.count("work_items"),
    )


def _cancel(env: _Env, mission_id: str, key: str) -> None:
    mission = env.store.get_mission(mission_id)
    env.facade._missions.transition(
        mission_id=mission_id,
        expected_version=mission.version,
        new_state=MissionState.CANCELLED,
        root_work_id=None,
        idempotency_key=key,
    )


# --------------------------------------------------------------------------- p: the service


def test_p01_the_snapshot_lists_the_pending_scope_card_with_everything_the_user_must_judge(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    plan_hash = _pending(env, COCKPIT_REQUEST)

    snapshot = _service(env).snapshot()

    assert len(snapshot.pending_cards) == 1
    card = snapshot.pending_cards[0]
    assert (card.project_id, card.request_id, card.plan_hash, card.revision) == (PROJECT_ID, COCKPIT_REQUEST, plan_hash, 1)
    assert card.objective == "Fix add()"
    assert card.acceptance_criteria == ("add(2, 3) == 5",)
    assert card.scope_paths == (CALC, f"{PROJECT_ID}/tests/test_calc.py")
    assert (card.risks, card.non_goals) == (("r1",), ("no refactor",))
    assert card.executor == "codex · agent-a"
    assert (card.submitted_by, card.approver) == ("PM (Claude)", "fubai")
    assert card.submitted_at
    assert (card.can_approve, card.approve_blocked_reason) == (True, "")
    assert snapshot.projects[0].user_action is CockpitUserAction.NONE
    dumped = snapshot.model_dump(mode="json")
    assert not _INTERNAL_KEYS & _all_keys(dumped["pending_cards"])


def test_p02_only_the_newest_unapproved_revision_is_listed(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-U09C-A")
    env.submit("REQ-U09C-A", risks=("old",))
    newest = env.submit("REQ-U09C-A", risks=("new",)).card.plan_hash

    cards = _service(env).snapshot().pending_cards
    assert [(c.revision, c.plan_hash, c.risks) for c in cards] == [(2, newest, ("new",))]

    env.approve("REQ-U09C-A", newest)
    assert _service(env).snapshot().pending_cards == ()


@pytest.mark.parametrize("approver", ["", "   "])
def test_p03_an_unconfigured_approver_blocks_the_card_with_a_fixed_reason(
    tmp_path: Path, approver: str
) -> None:
    env = _env(tmp_path)
    _pending(env)

    card = _service(env, approver=approver).snapshot().pending_cards[0]

    assert card.can_approve is False
    assert card.approver == ""
    assert "未配置批准人" in card.approve_blocked_reason
    assert "AUTO_PM_COCKPIT_APPROVER" in card.approve_blocked_reason


def test_p04_an_unfinished_task_blocks_approval_until_it_ends(tmp_path: Path) -> None:
    env = _env(tmp_path)
    first_hash = _pending(env, "REQ-U09C-A")
    _pending(env, "REQ-U09C-B", risks=("rb",))
    first = env.approve("REQ-U09C-A", first_hash)

    blocked = _service(env).snapshot().pending_cards
    assert [(c.request_id, c.can_approve) for c in blocked] == [("REQ-U09C-B", False)]
    # TD-071 card 3: the second card collides with the open one; the cockpit names it and points at the user's release
    reason = blocked[0].approve_blocked_reason
    assert "要改同一批文件" in reason and first.mission_id in reason and "pm approve --admission-release-ref" in reason

    _cancel(env, first.mission_id, "u09c-p04-cancel")
    freed = _service(env).snapshot().pending_cards
    assert [(c.request_id, c.can_approve, c.approve_blocked_reason) for c in freed] == [("REQ-U09C-B", True, "")]


def test_p05_an_unreadable_pending_record_is_a_notice_and_never_hides_the_project_card(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    _pending(env)
    stored = env.scalars("SELECT card_json FROM planning_scope_cards")[0]
    env.sql("UPDATE planning_scope_cards SET card_json=?", stored.replace(CALC, f"{PROJECT_ID}/src/evil.py"))

    snapshot = _service(env).snapshot()

    assert snapshot.pending_cards == ()
    assert [card.project_id for card in snapshot.projects] == [PROJECT_ID]
    assert "无法安全读取" in snapshot.projects[0].risk or snapshot.projects[0].mission
    assert any("待批准范围卡无法安全读取" in note for note in snapshot.notices)


def test_p06_without_a_store_there_are_no_pending_cards_and_nothing_is_created(tmp_path: Path) -> None:
    env = _env(tmp_path, name="seeded")
    fresh = (tmp_path / "fresh").resolve()
    from tests.core.test_pm_run_e2e import _build_workspace

    _build_workspace(fresh)
    snapshot = PmCockpitService(fresh, approver="fubai").snapshot()

    assert snapshot.pending_cards == ()
    assert not (fresh / ".auto-pm" / "continuity.db").exists()
    assert env.db.exists()


def test_p07_approve_scope_builds_the_chain_with_the_configured_approver_and_a_stable_reference(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    plan_hash = _pending(env, COCKPIT_REQUEST)

    result = _service(env).approve_scope(COCKPIT_REQUEST, plan_hash)

    assert (result.request_id, result.plan_hash, result.subject_project_id) == (COCKPIT_REQUEST, plan_hash, PROJECT_ID)
    assert env.store.get_mission(result.mission_id).state is MissionState.DRAFT
    decision = env.facade._decisions.get_decision(result.decision_id)
    assert decision.approver == "fubai"
    reference = decision.metadata["planning_approval"]["approval_evidence_ref"]
    assert _EVIDENCE.fullmatch(reference)
    assert reference == _service(env)._approval_evidence(plan_hash)
    assert reference != _service(env, approver="baiyang")._approval_evidence(plan_hash)
    assert "fubai" not in reference
    assert env.chg_status(result.change_id) == "approved"


def test_p08_approving_again_is_idempotent(tmp_path: Path) -> None:
    env = _env(tmp_path)
    plan_hash = _pending(env)
    first = _service(env).approve_scope("REQ-U09C-A", plan_hash)
    before = _writes(env)

    second = _service(env).approve_scope("REQ-U09C-A", plan_hash)

    assert second == first
    assert _writes(env) == before


def test_p09_without_a_configured_approver_the_approval_is_refused_and_writes_nothing(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    plan_hash = _pending(env)
    before = _writes(env)

    with pytest.raises(PmCockpitError, match="未配置批准人"):
        _service(env, approver="").approve_scope("REQ-U09C-A", plan_hash)

    assert _writes(env) == before


@pytest.mark.parametrize("approver", ["Claude", "claude-opus-5-5", "Claude Code", "gpt-5", "Codex Agent", "sonnet", "PM (Claude)"])
def test_p10_a_model_name_can_never_be_the_configured_approver(tmp_path: Path, approver: str) -> None:
    env = _env(tmp_path)
    plan_hash = _pending(env)
    before = _writes(env)
    change_id = env.store.get_submitted_planning_scope_card("REQ-U09C-A", plan_hash).card.change_id
    status = env.chg_status(change_id)

    with pytest.raises(PmCockpitError, match="自签"):
        _service(env, approver=approver).approve_scope("REQ-U09C-A", plan_hash)

    assert (_writes(env), env.chg_status(change_id)) == (before, status)


def test_p11_a_stale_unknown_or_blank_request_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env.draft("REQ-U09C-A")
    old = env.submit("REQ-U09C-A", risks=("old",)).card.plan_hash
    new = env.submit("REQ-U09C-A", risks=("new",)).card.plan_hash
    before = _writes(env)
    service = _service(env)

    with pytest.raises(PmCockpitError, match="取代"):
        service.approve_scope("REQ-U09C-A", old)
    with pytest.raises(PmCockpitError):
        service.approve_scope("REQ-U09C-A", "a" * 64)
    with pytest.raises(PmCockpitError, match="未找到要批准的范围卡"):
        service.approve_scope("  ", new)
    with pytest.raises(PmCockpitError, match="未找到要批准的范围卡"):
        service.approve_scope("REQ-U09C-A", "")

    assert _writes(env) == before


def test_p12_an_unfinished_task_refuses_the_approval_before_any_write(tmp_path: Path) -> None:
    env = _env(tmp_path)
    first_hash = _pending(env, "REQ-U09C-A")
    second_hash = _pending(env, "REQ-U09C-B", risks=("rb",))
    _service(env).approve_scope("REQ-U09C-A", first_hash)
    before = _writes(env)

    with pytest.raises(PmCockpitError, match="要改同一批文件"):
        _service(env).approve_scope("REQ-U09C-B", second_hash)

    assert _writes(env) == before


def test_p13_after_the_approval_the_project_card_offers_the_start_and_no_pending_card_remains(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    plan_hash = _pending(env)
    _service(env).approve_scope("REQ-U09C-A", plan_hash)

    snapshot = _service(env).snapshot()

    assert snapshot.pending_cards == ()
    assert snapshot.projects[0].user_action is CockpitUserAction.CONFIRM_START


def test_p14_the_snapshot_never_exposes_the_approver_evidence_or_internal_identifiers(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    plan_hash = _pending(env)
    service = _service(env)
    before = json.dumps(service.snapshot().model_dump(mode="json"), ensure_ascii=False)
    service.approve_scope("REQ-U09C-A", plan_hash)
    after = json.dumps(service.snapshot().model_dump(mode="json"), ensure_ascii=False)

    for text in (before, after):
        assert "user-confirmation" not in text
        assert "lease" not in text.lower()


# --------------------------------------------------------------------------- k: the presentation contract


def _card_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "project_id": "SW-2026-008",
        "project_name": "auto pm",
        "request_id": "REQ-1",
        "plan_hash": "a" * 64,
        "revision": 1,
        "objective": "Do it",
        "acceptance_criteria": ["works"],
        "scope_paths": ["a.py"],
        "risks": ["r"],
        "non_goals": ["n"],
        "executor": "codex · gpt-approved",
        "submitted_by": "PM",
        "submitted_at": "2026-10-02T00:00:00+00:00",
        "approver": "fubai",
        "can_approve": True,
        "approve_blocked_reason": "",
    }
    payload.update(changes)
    return payload


def test_k01_a_valid_pending_card_round_trips_and_is_frozen() -> None:
    card = PmCockpitPendingScopeCard.model_validate(_card_payload())

    assert card.schema_version == "pm-cockpit-pending-scope-card.v1"
    assert PmCockpitPendingScopeCard.model_validate(card.model_dump(mode="json")) == card
    with pytest.raises(ValidationError):
        cast(Any, card).objective = "changed"


@pytest.mark.parametrize(
    "changes",
    [
        {"plan_hash": "short"},
        {"plan_hash": "A" * 64},
        {"revision": 0},
        {"objective": ""},
        {"request_id": ""},
        {"executor": ""},
        {"approve_blocked_reason": "x" * 201, "can_approve": False},
        {"unexpected": "field"},
    ],
)
def test_k02_malformed_pending_cards_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PmCockpitPendingScopeCard.model_validate(_card_payload(**changes))


def test_k03_a_card_is_either_approvable_without_a_reason_or_blocked_with_one() -> None:
    with pytest.raises(ValidationError):
        PmCockpitPendingScopeCard.model_validate(_card_payload(can_approve=True, approve_blocked_reason="why"))
    with pytest.raises(ValidationError):
        PmCockpitPendingScopeCard.model_validate(_card_payload(can_approve=False, approve_blocked_reason=""))
    blocked = PmCockpitPendingScopeCard.model_validate(
        _card_payload(can_approve=False, approve_blocked_reason="未配置批准人")
    )
    assert blocked.can_approve is False


def test_k04_a_pre_u09c_snapshot_payload_still_validates_with_no_pending_cards() -> None:
    legacy = {"schema_version": "pm-cockpit-snapshot.v1", "projects": [], "activities": [], "notices": []}

    snapshot = PmCockpitSnapshot.model_validate(legacy)

    assert snapshot.pending_cards == ()


def test_k05_the_pending_card_has_no_lease_or_internal_work_fields() -> None:
    names = set(PmCockpitPendingScopeCard.model_fields)

    assert not {"mission_id", "work_id", "run_id", "decision_id", "lease_token", "approval_evidence_ref"} & names


def test_p15_a_second_card_on_other_files_is_approvable_without_a_release(tmp_path: Path) -> None:
    """TD-071 card 3, positive control of p04: an open task alone no longer blocks the next card."""

    env = _env(tmp_path)
    first_hash = _pending(env, "REQ-U09C-A")
    env.draft("REQ-U09C-B")
    second_hash = env.submit("REQ-U09C-B", risks=("rb",), scope=(f"{PROJECT_ID}/docs/notes.md",)).card.plan_hash
    env.approve("REQ-U09C-A", first_hash)

    pending = _service(env).snapshot().pending_cards
    assert [(c.request_id, c.can_approve, c.approve_blocked_reason) for c in pending] == [("REQ-U09C-B", True, "")]
    _service(env).approve_scope("REQ-U09C-B", second_hash)
    assert len(env.store.list_missions(PROJECT_ID)) == 2
