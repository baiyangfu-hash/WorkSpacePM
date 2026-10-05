"""Intake contracts: classification, triage ticket and inbox item rules (card CARD-SW008-M2-P1, scenarios ct01-ct10)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from auto_pm.contracts.intake import (
    ChangeAction,
    Disposition,
    IntakeBrief,
    IntakeClassification,
    IntakeItem,
    IntakeKind,
    IntakeStatus,
    IntakeSummary,
    TriageTicket,
    UrgentCriterion,
    parse_evidence,
)

PROJECT = "SW-TEST-001"
ITEM_ID = "INBOX-SW-TEST-001-0001"


def _ticket(**changes: Any) -> TriageTicket:
    values: dict[str, Any] = {
        "original_words": "登录页偶发白屏",
        "affects": "SW-TEST-001 登录页",
        "duplicate_check": "查过台账与收件箱，没有同类条目",
        "evidence": ("file:README.md",),
        "disposition": Disposition.AFTER_CURRENT,
        "rationale": "不阻塞当前卡，当前卡收口后处理",
        "alternatives": ("并入下个迭代",),
        "cost_risk": "半天；低风险",
    }
    values.update(changes)
    return TriageTicket(**values)


def _classification(kind: IntakeKind = IntakeKind.BUG, **changes: Any) -> IntakeClassification:
    values: dict[str, Any] = {"kind": kind, "domain": "SCPT"}
    if kind is IntakeKind.CHANGE:
        values["change_action"] = ChangeAction.ADD
    values.update(changes)
    return IntakeClassification(**values)


def _item(
    classification: IntakeClassification | None = None,
    ticket: TriageTicket | None = None,
    **changes: Any,
) -> IntakeItem:
    values: dict[str, Any] = {
        "item_id": ITEM_ID,
        "request_id": "REQ-INTAKE-001",
        "project_id": PROJECT,
        "title": "登录页偶发白屏",
        "classification": classification or _classification(),
        "ticket": ticket or _ticket(),
        "proposed_by": "pm-test",
        "created_at": "2026-10-05T00:00:00+00:00",
    }
    values.update(changes)
    return IntakeItem.create(**values)


def _urgent_ticket(**changes: Any) -> TriageTicket:
    values: dict[str, Any] = {
        "urgent_criterion": UrgentCriterion.WRONG_OUTPUT,
        "disposition": Disposition.INTERRUPT_NOW,
    }
    values.update(changes)
    return _ticket(**values)


@pytest.mark.parametrize(
    ("kind", "nature", "urgency"),
    [
        (IntakeKind.ITERATION, "OPT", "normal"),
        (IntakeKind.BUG, "DEF", "normal"),
        (IntakeKind.CHANGE, "REQ", "normal"),
        (IntakeKind.URGENT, "EMRG", "urgent"),
        (IntakeKind.DEBT, "OPT", "normal"),
    ],
)
def test_ct01_each_kind_files_under_its_change_nature(kind: IntakeKind, nature: str, urgency: str) -> None:
    classification = _classification(kind)
    assert classification.business_nature == nature
    assert classification.urgency == urgency


def test_ct02_a_feature_change_names_its_action_and_only_a_change_may_have_one() -> None:
    assert {action.value for action in ChangeAction} == {"ADD", "MODIFY", "REDUCE", "FREEZE", "REMOVE"}
    for action in ChangeAction:
        assert _classification(IntakeKind.CHANGE, change_action=action).change_action is action
    with pytest.raises(ValidationError):
        IntakeClassification(kind=IntakeKind.CHANGE, domain="SCPT")
    for kind in (IntakeKind.ITERATION, IntakeKind.BUG, IntakeKind.URGENT, IntakeKind.DEBT):
        with pytest.raises(ValidationError):
            IntakeClassification(kind=kind, domain="SCPT", change_action=ChangeAction.FREEZE)


@pytest.mark.parametrize(
    "changes",
    [
        {"domain": "scpt"},
        {"domain": "SC"},
        {"domain": "SCPTX"},
        {"impact_scope": ()},
        {"impact_scope": ("MODULE", "MODULE")},
        {"impact_scope": ("module",)},
    ],
)
def test_ct03_classification_refuses_malformed_domain_and_scope(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _classification(**changes)


def test_ct04_evidence_must_have_a_known_kind_and_a_well_formed_value() -> None:
    accepted = {
        "file:README.md": "file",
        "file:docs/a/b.md": "file",
        "cmd:main.py ledger reconcile SW-2026-008": "cmd",
        "ledger:TD-SW008-066": "ledger",
        "chg:CHG-SCPT-2026-378": "chg",
        "commit:edeeead9": "commit",
    }
    for entry, kind in accepted.items():
        assert parse_evidence(entry)[0] == kind
    for entry in (
        "",
        "README.md",
        "note:it looked wrong",
        "file:",
        "file:/etc/passwd",
        "file:../outside.txt",
        "file:a/../b.txt",
        "file:a\\b.txt",
        "file:C:/x.txt",
        "file:a//b.txt",
        "cmd:ab",
        "ledger:TD-1",
        "ledger:066",
        "chg:CHG-1",
        "commit:XYZ",
        "commit:abc",
    ):
        with pytest.raises(ValueError):
            parse_evidence(entry)


def test_ct05_a_ticket_without_evidence_or_alternative_or_with_blank_text_is_refused() -> None:
    for changes in (
        {"evidence": ()},
        {"evidence": ("file:README.md", "file:README.md")},
        {"evidence": ("opinion:strongly felt",)},
        {"alternatives": ()},
        {"alternatives": ("a", "a")},
        {"rationale": "   "},
        {"original_words": ""},
        {"affects": "\t"},
        {"cost_risk": "x" * 2001},
        {"duplicate_of": ("whatever",)},
        {"duplicate_of": ("TD-SW008-066", "TD-SW008-066")},
        {"unknown_field": "x"},
    ):
        with pytest.raises(ValidationError):
            _ticket(**changes)
    ticket = _ticket(duplicate_of=("TD-SW008-066", "INBOX-SW-TEST-001-0002", "CHG-SCPT-2026-378"))
    assert len(ticket.duplicate_of) == 3


def test_ct06_urgency_rules_are_enforced_on_the_item() -> None:
    assert _item(_classification(IntakeKind.URGENT), _urgent_ticket()).ticket.urgent_criterion is not None
    with pytest.raises(ValidationError):
        _item(_classification(IntakeKind.URGENT), _ticket(disposition=Disposition.INTERRUPT_NOW))
    with pytest.raises(ValidationError):
        _item(_classification(IntakeKind.BUG), _urgent_ticket())
    with pytest.raises(ValidationError):
        _item(_classification(IntakeKind.BUG), _ticket(disposition=Disposition.INTERRUPT_NOW))
    with pytest.raises(ValidationError):
        _item(_classification(IntakeKind.URGENT), _urgent_ticket(disposition=Disposition.INBOX_WAIT))
    assert _item(_classification(IntakeKind.URGENT), _urgent_ticket(disposition=Disposition.AFTER_CURRENT))
    for disposition in (Disposition.AFTER_CURRENT, Disposition.INBOX_WAIT, Disposition.REJECT):
        assert _item(ticket=_ticket(disposition=disposition)).ticket.disposition is disposition


def test_ct07_the_ticket_hash_binds_every_recorded_recommendation() -> None:
    first = _item()
    assert first.ticket_hash == _item().ticket_hash
    assert first.ticket_hash == IntakeItem.hash_for(PROJECT, "  登录页偶发白屏  ", first.classification, first.ticket)
    assert len(first.ticket_hash) == 64
    payload = first.model_dump(mode="json")
    tampered: list[dict[str, Any]] = [
        {**payload, "title": "另一个标题"},
        {**payload, "project_id": "SW-TEST-002", "item_id": "INBOX-SW-TEST-002-0001"},
        {**payload, "classification": {**payload["classification"], "domain": "PLC"}},
        {**payload, "classification": {**payload["classification"], "impact_scope": ["SYSTEM"]}},
        {**payload, "ticket": {**payload["ticket"], "rationale": "改过的理由"}},
        {**payload, "ticket": {**payload["ticket"], "evidence": ["file:README.md", "cmd:echo changed"]}},
        {**payload, "ticket_hash": "0" * 64},
        {**payload, "ticket_hash": "A" * 64},
    ]
    for candidate in tampered:
        with pytest.raises(ValidationError):
            IntakeItem.model_validate(candidate)
    assert IntakeItem.model_validate(payload) == first


def test_ct08_status_and_decision_fields_must_agree() -> None:
    payload = _item().model_dump(mode="json")
    decided = {"decided_by": "fubai", "decision_ref": "user-confirmation:chat-20261005", "decided_at": "2026-10-05T01:00:00+00:00"}
    assert IntakeItem.model_validate({**payload, **decided, "status": "CONFIRMED"}).status is IntakeStatus.CONFIRMED
    assert IntakeItem.model_validate({**payload, **decided, "status": "REJECTED"}).status is IntakeStatus.REJECTED
    planned = IntakeItem.model_validate({**payload, **decided, "status": "PLANNED", "plan_request_id": "REQ-1"})
    assert planned.plan_request_id == "REQ-1"
    recommended_rejection = _item(ticket=_ticket(disposition=Disposition.REJECT)).model_dump(mode="json")
    assert IntakeItem.model_validate({**recommended_rejection, **decided, "status": "REJECTED"}).status is IntakeStatus.REJECTED
    for candidate in (
        {**recommended_rejection, **decided, "status": "CONFIRMED"},
        {**recommended_rejection, **decided, "status": "PLANNED", "plan_request_id": "REQ-1"},
        {**payload, **decided},
        {**payload, "status": "CONFIRMED"},
        {**payload, **decided, "status": "CONFIRMED", "decided_by": ""},
        {**payload, **decided, "status": "CONFIRMED", "plan_request_id": "REQ-1"},
        {**payload, **decided, "status": "PLANNED"},
        {**payload, "plan_request_id": "REQ-1"},
        {**payload, "item_id": "INBOX-SW-OTHER-001-0001"},
        {**payload, "item_id": "ITEM-1"},
        {**payload, "project_id": "sw-test-001"},
        {**payload, "proposed_by": " padded "},
        {**payload, "note": "line one\nline two"},
    ):
        with pytest.raises(ValidationError):
            IntakeItem.model_validate(candidate)


def test_ct09_the_summary_is_empty_until_something_waits() -> None:
    assert IntakeSummary().is_empty
    brief = IntakeBrief(
        item_id=ITEM_ID,
        kind=IntakeKind.BUG,
        title="登录页偶发白屏",
        status=IntakeStatus.PROPOSED,
        disposition=Disposition.AFTER_CURRENT,
    )
    assert not IntakeSummary(awaiting_confirmation=1, queue=(brief,)).is_empty
    assert not IntakeSummary(confirmed_waiting=1).is_empty


def test_ct10_records_are_closed_and_immutable() -> None:
    item = _item()
    with pytest.raises(ValidationError):
        IntakeItem.model_validate({**item.model_dump(mode="json"), "extra": 1})
    with pytest.raises(ValidationError):
        IntakeClassification.model_validate({"kind": "BUG", "domain": "SCPT", "extra": 1})
    with pytest.raises(ValidationError):
        item.__setattr__("title", "changed")
    with pytest.raises(ValidationError):
        item.classification.__setattr__("domain", "PLC")
