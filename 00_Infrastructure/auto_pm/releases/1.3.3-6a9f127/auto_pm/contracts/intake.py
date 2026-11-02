"""Intake contracts: classification, triage ticket and inbox item of the PM front desk.

Every new need, bug or idea is first recorded as an inbox item that carries a machine-checked triage
ticket. Recording an item never changes the current Mission, Work, Run or lease: it is a separate,
append-only record that a human confirms or rejects before anything becomes a plan.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class IntakeKind(StrEnum):
    """What a new item is, from the project manager's point of view."""

    ITERATION = "ITERATION"
    BUG = "BUG"
    CHANGE = "CHANGE"
    URGENT = "URGENT"
    DEBT = "DEBT"


class ChangeAction(StrEnum):
    """A feature change is not only an addition: it may also modify, reduce, freeze or remove."""

    ADD = "ADD"
    MODIFY = "MODIFY"
    REDUCE = "REDUCE"
    FREEZE = "FREEZE"
    REMOVE = "REMOVE"


class UrgentCriterion(StrEnum):
    """The objective reasons that justify interrupting the current work."""

    SAFETY = "SAFETY"
    DATA_LOSS = "DATA_LOSS"
    BLOCKS_ALL = "BLOCKS_ALL"
    WRONG_OUTPUT = "WRONG_OUTPUT"


class Disposition(StrEnum):
    """What the project manager recommends to do with the item."""

    INTERRUPT_NOW = "INTERRUPT_NOW"
    AFTER_CURRENT = "AFTER_CURRENT"
    INBOX_WAIT = "INBOX_WAIT"
    REJECT = "REJECT"


class IntakeStatus(StrEnum):
    """Life cycle of an inbox item; every transition is made by an explicit command."""

    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    PLANNED = "PLANNED"


OPEN_INTAKE_STATUSES = (IntakeStatus.PROPOSED, IntakeStatus.CONFIRMED)
DEFAULT_IMPACT_SCOPE = ("MODULE",)
EVIDENCE_KINDS = ("file", "cmd", "ledger", "chg", "commit")
KIND_BUSINESS_NATURE = {
    IntakeKind.ITERATION: "OPT",
    IntakeKind.BUG: "DEF",
    IntakeKind.CHANGE: "REQ",
    IntakeKind.URGENT: "EMRG",
    IntakeKind.DEBT: "OPT",
}
DISPOSITION_RANK = {
    Disposition.INTERRUPT_NOW: 0,
    Disposition.AFTER_CURRENT: 1,
    Disposition.INBOX_WAIT: 2,
    Disposition.REJECT: 3,
}

_ITEM_ID = re.compile(r"INBOX-[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+-\d{4}\Z")
_PROJECT_ID = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\Z")
_TICKET_HASH = re.compile(r"[0-9a-f]{64}\Z")
_DOMAIN = re.compile(r"[A-Z]{3,4}\Z")
_SCOPE = re.compile(r"[A-Z]{3,6}\Z")
_LEDGER_ID = re.compile(r"TD-[A-Z0-9]+-\d{3,}\Z")
_CHG_ID = re.compile(r"CHG-[A-Z]{3,4}-\d{4}-\d{3}\Z")
_COMMIT = re.compile(r"[0-9a-f]{7,40}\Z")
_DUPLICATE_REF = re.compile(
    r"(?:INBOX-[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+-\d{4}|TD-[A-Z0-9]+-\d{3,}|CHG-[A-Z]{3,4}-\d{4}-\d{3})\Z"
)
_MAX_SHORT = 200
_MAX_LONG = 2000


def _clean_text(value: str, *, limit: int, multiline: bool) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("text must not be blank")
    if len(cleaned) > limit:
        raise ValueError(f"text must not exceed {limit} characters")
    for char in cleaned:
        if char == "\n" and multiline:
            continue
        if not char.isprintable():
            raise ValueError("text must be printable" + ("" if multiline else " and single-line"))
    return cleaned


def parse_evidence(entry: str) -> tuple[str, str]:
    """Split one evidence entry ``<kind>:<value>`` and check the form of its value."""

    kind, separator, value = entry.partition(":")
    if not separator or kind not in EVIDENCE_KINDS:
        raise ValueError("evidence must look like <file|cmd|ledger|chg|commit>:<value>")
    if value != value.strip() or not value:
        raise ValueError("evidence value must be canonical text")
    if kind == "file":
        parts = value.split("/")
        if (
            "\\" in value
            or ":" in value
            or value.startswith("/")
            or any(part in {"", ".", ".."} for part in parts)
            or not value.isprintable()
        ):
            raise ValueError("file evidence must be a safe workspace-relative path")
    elif kind == "cmd":
        if len(value) < 4 or len(value) > _MAX_SHORT or not value.isprintable():
            raise ValueError("cmd evidence must be a printable command of 4 to 200 characters")
    elif kind == "ledger":
        if _LEDGER_ID.fullmatch(value) is None:
            raise ValueError("ledger evidence must be a technical-debt id such as TD-SW008-066")
    elif kind == "chg":
        if _CHG_ID.fullmatch(value) is None:
            raise ValueError("chg evidence must be a change number such as CHG-SCPT-2026-378")
    elif _COMMIT.fullmatch(value) is None:
        raise ValueError("commit evidence must be a lowercase hex object name of 7 to 40 digits")
    return kind, value


class IntakeClassification(BaseModel):
    """The classification that decides how a plan is filed as a change request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: IntakeKind
    change_action: ChangeAction | None = None
    domain: str
    impact_scope: tuple[str, ...] = DEFAULT_IMPACT_SCOPE

    @field_validator("domain")
    @classmethod
    def _validate_domain(cls, value: str) -> str:
        if _DOMAIN.fullmatch(value) is None:
            raise ValueError("domain must be 3 or 4 uppercase letters")
        return value

    @field_validator("impact_scope")
    @classmethod
    def _validate_impact_scope(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values or len(set(values)) != len(values):
            raise ValueError("impact_scope must be non-empty and unique")
        if any(_SCOPE.fullmatch(value) is None for value in values):
            raise ValueError("impact_scope entries must be uppercase scope codes")
        return values

    @model_validator(mode="after")
    def _validate_change_action(self) -> IntakeClassification:
        if (self.kind is IntakeKind.CHANGE) != (self.change_action is not None):
            raise ValueError("change_action is required for CHANGE and forbidden for other kinds")
        return self

    @property
    def business_nature(self) -> str:
        """The change-request nature this kind is filed under."""

        return KIND_BUSINESS_NATURE[self.kind]

    @property
    def urgency(self) -> str:
        """The change-request urgency: only an URGENT item is filed as urgent."""

        return "urgent" if self.kind is IntakeKind.URGENT else "normal"


class TriageTicket(BaseModel):
    """The professional recommendation of the project manager; it cannot be recorded without evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    original_words: str
    affects: str
    duplicate_check: str
    duplicate_of: tuple[str, ...] = ()
    evidence: tuple[str, ...]
    urgent_criterion: UrgentCriterion | None = None
    disposition: Disposition
    rationale: str
    alternatives: tuple[str, ...]
    cost_risk: str
    decisions_for_user: tuple[str, ...] = ()

    @field_validator("original_words")
    @classmethod
    def _validate_original_words(cls, value: str) -> str:
        return _clean_text(value, limit=_MAX_LONG, multiline=True)

    @field_validator("affects", "duplicate_check", "rationale", "cost_risk")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _clean_text(value, limit=_MAX_LONG, multiline=True)

    @field_validator("alternatives", "decisions_for_user")
    @classmethod
    def _validate_text_list(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(_clean_text(item, limit=_MAX_SHORT, multiline=False) for item in values)
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("entries must be unique")
        return cleaned

    @field_validator("evidence")
    @classmethod
    def _validate_evidence(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values or len(set(values)) != len(values):
            raise ValueError("a triage ticket needs at least one unique evidence entry")
        for entry in values:
            parse_evidence(entry)
        return values

    @field_validator("duplicate_of")
    @classmethod
    def _validate_duplicate_of(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            _DUPLICATE_REF.fullmatch(value) is None for value in values
        ):
            raise ValueError("duplicate_of must list unique inbox, ledger or change ids")
        return values

    @model_validator(mode="after")
    def _validate_alternatives(self) -> TriageTicket:
        if not self.alternatives:
            raise ValueError("a triage ticket needs at least one alternative")
        return self


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _clean_title(value: str) -> str:
    return _clean_text(value, limit=120, multiline=False)


def _clean_actor(value: str) -> str:
    if not value or value != value.strip() or len(value) > 80 or not value.isprintable():
        raise ValueError("actor must be canonical printable text of at most 80 characters")
    return value


class IntakeItem(BaseModel):
    """One inbox record; its ``ticket_hash`` is what a human confirms."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["intake-item.v1"] = "intake-item.v1"
    item_id: str
    request_id: str
    project_id: str
    title: str
    classification: IntakeClassification
    ticket: TriageTicket
    ticket_hash: str
    status: IntakeStatus = IntakeStatus.PROPOSED
    proposed_by: str
    created_at: str
    decided_by: str = ""
    decision_ref: str = ""
    decided_at: str = ""
    note: str = ""
    plan_request_id: str = ""

    @staticmethod
    def hash_for(
        project_id: str,
        title: str,
        classification: IntakeClassification,
        ticket: TriageTicket,
    ) -> str:
        """Return the content hash a human confirms; it covers every recorded recommendation."""

        payload = {
            "project_id": project_id,
            "title": title.strip(),
            "classification": classification.model_dump(mode="json"),
            "ticket": ticket.model_dump(mode="json"),
        }
        return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()

    @classmethod
    def create(
        cls,
        *,
        item_id: str,
        request_id: str,
        project_id: str,
        title: str,
        classification: IntakeClassification,
        ticket: TriageTicket,
        proposed_by: str,
        created_at: str,
    ) -> IntakeItem:
        """Build a freshly proposed item whose hash is derived from its own content."""

        return cls(
            item_id=item_id,
            request_id=request_id,
            project_id=project_id,
            title=title,
            classification=classification,
            ticket=ticket,
            ticket_hash=cls.hash_for(project_id, title, classification, ticket),
            proposed_by=proposed_by,
            created_at=created_at,
        )

    @field_validator("project_id")
    @classmethod
    def _validate_project_id(cls, value: str) -> str:
        if _PROJECT_ID.fullmatch(value) is None:
            raise ValueError("project_id must be a canonical project id")
        return value

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        return _clean_title(value)

    @field_validator("request_id")
    @classmethod
    def _validate_request_id(cls, value: str) -> str:
        return _clean_text(value, limit=_MAX_SHORT, multiline=False)

    @field_validator("proposed_by")
    @classmethod
    def _validate_proposed_by(cls, value: str) -> str:
        return _clean_actor(value)

    @field_validator("decided_by")
    @classmethod
    def _validate_decided_by(cls, value: str) -> str:
        return _clean_actor(value) if value else value

    @field_validator("note")
    @classmethod
    def _validate_note(cls, value: str) -> str:
        return _clean_text(value, limit=_MAX_SHORT, multiline=False) if value else value

    @model_validator(mode="after")
    def _validate_consistency(self) -> IntakeItem:
        if _ITEM_ID.fullmatch(self.item_id) is None or not self.item_id.startswith(
            f"INBOX-{self.project_id}-"
        ):
            raise ValueError("item_id must be INBOX-<project id>-<4 digits>")
        if _TICKET_HASH.fullmatch(self.ticket_hash) is None or self.ticket_hash != self.hash_for(
            self.project_id, self.title, self.classification, self.ticket
        ):
            raise ValueError("ticket_hash must match the recorded content")
        urgent = self.classification.kind is IntakeKind.URGENT
        if urgent != (self.ticket.urgent_criterion is not None):
            raise ValueError("an urgent criterion is required for URGENT items and forbidden otherwise")
        if self.ticket.disposition is Disposition.INTERRUPT_NOW and not urgent:
            raise ValueError("only an URGENT item may interrupt the current work")
        if urgent and self.ticket.disposition is Disposition.INBOX_WAIT:
            raise ValueError("an URGENT item cannot be left waiting in the inbox")
        decided = bool(self.decided_by and self.decision_ref and self.decided_at)
        if self.status is IntakeStatus.PROPOSED:
            if self.decided_by or self.decision_ref or self.decided_at or self.plan_request_id:
                raise ValueError("a proposed item carries no decision")
        elif not decided:
            raise ValueError("a decided item needs decided_by, decision_ref and decided_at")
        if (self.status is IntakeStatus.PLANNED) != bool(self.plan_request_id):
            raise ValueError("plan_request_id is required exactly for PLANNED items")
        if self.ticket.disposition is Disposition.REJECT and self.status in (
            IntakeStatus.CONFIRMED,
            IntakeStatus.PLANNED,
        ):
            raise ValueError("an item recommended for rejection can only be rejected")
        return self


class IntakeBrief(BaseModel):
    """One open inbox item as shown by ``pm resume``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str
    kind: IntakeKind
    title: str
    status: IntakeStatus
    disposition: Disposition


class IntakeSummary(BaseModel):
    """The read-only inbox view that ``pm resume`` appends; it never changes the focus."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["intake-summary.v1"] = "intake-summary.v1"
    awaiting_confirmation: int = 0
    confirmed_waiting: int = 0
    queue: tuple[IntakeBrief, ...] = ()

    @property
    def is_empty(self) -> bool:
        """True when nothing is waiting in the inbox."""

        return not (self.awaiting_confirmation or self.confirmed_waiting or self.queue)
