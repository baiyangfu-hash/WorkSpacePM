"""The triage desk's read-only view of one project (TD-SW008-066, full version).

``pm triage`` answers three questions at once: which cards are open (the single focus, the ones waiting for the
user, the parked ones), which inbox items need the user's decision, and in what order the confirmed items should
be taken.  It is a *suggestion*: nothing in this module changes the focus, confirms an item or opens a card.
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from auto_pm.contracts.intake import Disposition, IntakeKind, IntakeStatus

# An item waiting for the user's yes/no for longer than this is flagged; the user decides, the desk never expires it.
PROPOSED_STALE_DAYS: Final = 3
# A confirmed item that nobody has turned into a plan for longer than this is flagged (same as a parked card).
CONFIRMED_STALE_DAYS: Final = 7

# The default order of the kinds when the recommended dispositions are equal (urgent first, scheduled changes last).
KIND_RANK: Final = {
    IntakeKind.URGENT: 0,
    IntakeKind.BUG: 1,
    IntakeKind.ITERATION: 2,
    IntakeKind.DEBT: 3,
    IntakeKind.CHANGE: 4,
}
KIND_LABEL: Final = {
    IntakeKind.URGENT: "紧急",
    IntakeKind.BUG: "bug 修复",
    IntakeKind.ITERATION: "正常迭代",
    IntakeKind.DEBT: "技术债",
    IntakeKind.CHANGE: "功能变更",
}
DISPOSITION_LABEL: Final = {
    Disposition.INTERRUPT_NOW: "立即打断",
    Disposition.AFTER_CURRENT: "排在当前卡之后",
    Disposition.INBOX_WAIT: "留在收件箱待排",
    Disposition.REJECT: "驳回",
}

TRIAGE_RULE: Final = (
    "排序规则：先看分诊单的建议处置（立即打断 > 排在当前卡之后 > 留在收件箱待排 > 驳回），"
    "同档再看类别（紧急 > bug > 正常迭代 > 技术债 > 功能变更），再同档先到先得。"
    "这只是建议：焦点只有用户说了才切（pm switch），确认和驳回只有用户本人说了才算。"
)


class FocusCard(BaseModel):
    """One open card of the project, as the triage desk shows it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: str
    title: str
    state: str
    column: Literal["ACTIVE", "WAITING", "PARKED"]
    # Whole days a parked card has been put aside (0 for the other columns).
    parked_days: int = Field(default=0, ge=0)
    stale: bool = False


class TriageEntry(BaseModel):
    """One inbox item in the suggested order, with the next legal step spelled out."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rank: int = Field(ge=1)
    item_id: str
    kind: IntakeKind
    title: str
    status: IntakeStatus
    disposition: Disposition
    ticket_hash: str
    # Whole days the item has waited since it was proposed (PROPOSED) or confirmed (CONFIRMED).
    waiting_days: int = Field(ge=0)
    stale: bool
    # Why the item sits here and what happens next, in plain words.
    reason: str
    next_step: str
    # True when the next step is the user's call; the desk never takes it.
    needs_user: bool
    # A command skeleton for the next step (empty when the step is just waiting); placeholders are in <angle brackets>.
    command: str = ""


class TriageReport(BaseModel):
    """The whole read-only triage view of a project."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["pm-triage.v1"] = "pm-triage.v1"
    project_id: str
    focus: tuple[FocusCard, ...] = ()
    # Items the user has not decided yet, in suggested order.
    decide_now: tuple[TriageEntry, ...] = ()
    # Confirmed items nobody has planned yet, in suggested order.
    ready_queue: tuple[TriageEntry, ...] = ()
    hints: tuple[str, ...] = ()
    rule: str = TRIAGE_RULE
