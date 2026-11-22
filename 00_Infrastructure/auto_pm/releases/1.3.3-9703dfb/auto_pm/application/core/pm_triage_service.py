"""PM front desk, triage step: suggest an order for the open inbox items (TD-SW008-066, full version).

The service only reads.  It never confirms an item, opens a card, takes the key from the card that is running or
switches the focus: those are the user's calls (``pm inbox confirm``, ``pm plan``, ``pm switch``).  What it adds
is the one view that was missing, namely the open cards and the open inbox items side by side, with the next
legal step of every item written out.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.application.core.mission_switch_service import MissionSwitchError, MissionSwitchService
from auto_pm.application.core.pm_intake_service import PmIntakeError, PmIntakeService
from auto_pm.contracts.intake import DISPOSITION_RANK, Disposition, IntakeItem, IntakeStatus
from auto_pm.contracts.mission import PARKED_STALE_DAYS, MissionBoard
from auto_pm.contracts.triage import (
    CONFIRMED_STALE_DAYS,
    DISPOSITION_LABEL,
    KIND_LABEL,
    KIND_RANK,
    PROPOSED_STALE_DAYS,
    FocusCard,
    TriageEntry,
    TriageReport,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore

_COMMAND = "python main.py pm"


class PmTriageError(RuntimeError):
    """Raised when the triage view cannot be read."""


def _days_since(timestamp: str, now: datetime) -> int:
    """Whole days from an ISO timestamp to ``now``; an unreadable stamp counts as zero, never as an error."""

    try:
        moment = datetime.fromisoformat(timestamp)
    except ValueError:
        return 0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return max(0, int((now - moment).total_seconds() // 86_400))


def suggested_order_key(item: IntakeItem) -> tuple[int, int, str]:
    """The sort key of the default order: recommended disposition, then kind, then first come first served."""

    return (DISPOSITION_RANK[item.ticket.disposition], KIND_RANK[item.classification.kind], item.item_id)


class PmTriageService:
    """Build the read-only :class:`TriageReport` of one project."""

    def __init__(
        self,
        control_root: str | Path,
        *,
        intake: PmIntakeService | None = None,
        switch: MissionSwitchService | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._root = Path(control_root).resolve()
        self._intake = intake or PmIntakeService(self._root)
        self._switch = switch or MissionSwitchService(self._root)
        self._now = now or (lambda: datetime.now(UTC))

    def report(self, project_id: str) -> TriageReport:
        """Return the focus, the items waiting for the user and the confirmed items in suggested order."""

        now = self._now()
        board = self._board(project_id)
        try:
            items = self._intake.list_items(project_id)
        except PmIntakeError as error:
            raise PmTriageError(str(error)) from error
        focus = self._focus(board, now)
        has_active = bool(board.active)
        proposed = sorted(
            (item for item in items if item.status is IntakeStatus.PROPOSED), key=suggested_order_key
        )
        confirmed = sorted(
            (item for item in items if item.status is IntakeStatus.CONFIRMED), key=suggested_order_key
        )
        decide_now = tuple(
            self._proposed_entry(rank, item, now) for rank, item in enumerate(proposed, start=1)
        )
        ready_queue = tuple(
            self._confirmed_entry(rank, item, now, board=board, has_active=has_active)
            for rank, item in enumerate(confirmed, start=1)
        )
        return TriageReport(
            project_id=project_id,
            focus=focus,
            decide_now=decide_now,
            ready_queue=ready_queue,
            hints=self._hints(project_id, board, focus, decide_now, ready_queue),
        )

    # ------------------------------------------------------------------ focus
    def _board(self, project_id: str) -> MissionBoard:
        """The project's cards; a workspace whose ledger was never created simply has none."""

        if not ContinuityStore(self._root).db_path.is_file():
            return MissionBoard(subject_project_id=project_id)
        try:
            return self._switch.board(project_id)
        except MissionSwitchError as error:
            raise PmTriageError(str(error)) from error

    @staticmethod
    def _focus(board: MissionBoard, now: datetime) -> tuple[FocusCard, ...]:
        cards: list[FocusCard] = [
            FocusCard(mission_id=m.mission_id, title=m.title, state=m.state.value, column="ACTIVE")
            for m in board.active
        ]
        cards.extend(
            FocusCard(mission_id=m.mission_id, title=m.title, state=m.state.value, column="WAITING")
            for m in board.waiting
        )
        for parked in board.parked:
            days = max(0, int((now - parked.park.parked_at).total_seconds() // 86_400))
            cards.append(
                FocusCard(
                    mission_id=parked.mission.mission_id,
                    title=parked.mission.title,
                    state=parked.mission.state.value,
                    column="PARKED",
                    parked_days=days,
                    stale=days > PARKED_STALE_DAYS,
                )
            )
        return tuple(cards)

    # ------------------------------------------------------------------ entries
    def _proposed_entry(self, rank: int, item: IntakeItem, now: datetime) -> TriageEntry:
        waiting = _days_since(item.created_at, now)
        disposition = item.ticket.disposition
        if disposition is Disposition.REJECT:
            step = "分诊单建议驳回：同意就驳回；不同意请让 PM 重新分诊（建议驳回的条目不能被确认）。"
            verb = "reject"
        else:
            step = "等你决定：同意这条建议就确认，不同意就驳回，或让 PM 改分诊单后重新入箱。"
            verb = "confirm"
        return TriageEntry(
            rank=rank,
            item_id=item.item_id,
            kind=item.classification.kind,
            title=item.title,
            status=item.status,
            disposition=disposition,
            ticket_hash=item.ticket_hash,
            waiting_days=waiting,
            stale=waiting > PROPOSED_STALE_DAYS,
            reason=self._reason(item),
            next_step=step,
            needs_user=True,
            command=(
                f"{_COMMAND} inbox {verb} {item.item_id} --ticket-hash {item.ticket_hash} "
                "--approver <用户名字> --approval-evidence-ref user-confirmation:<用户那条消息的时间或编号>"
            ),
        )

    def _confirmed_entry(
        self,
        rank: int,
        item: IntakeItem,
        now: datetime,
        *,
        board: MissionBoard,
        has_active: bool,
    ) -> TriageEntry:
        waiting = _days_since(item.decided_at, now)
        plan = (
            f"{_COMMAND} plan --project-id {item.project_id} --request-id <新请求号> "
            f"--inbox-id {item.item_id} <其余七栏参数，照 cockpit-entry 第 5 步>"
        )
        if not has_active:
            step = "现在没有在干的卡：可以转成计划（报给用户批准后才开工）。"
            command = plan
            needs_user = False
        elif item.ticket.disposition is Disposition.INTERRUPT_NOW:
            current = ", ".join(m.mission_id for m in board.active)
            step = (
                f"分诊单建议立即打断在干的卡 {current}，但只有用户说“先做它”才切："
                "先把它转成计划并批准成新卡，再由用户用 pm switch 切过去（先把手上的卡搁着）。"
            )
            command = plan
            needs_user = True
        else:
            current = ", ".join(m.mission_id for m in board.active)
            step = f"排在在干的卡 {current} 收口之后，收口后再转成计划。"
            command = ""
            needs_user = False
        return TriageEntry(
            rank=rank,
            item_id=item.item_id,
            kind=item.classification.kind,
            title=item.title,
            status=item.status,
            disposition=item.ticket.disposition,
            ticket_hash=item.ticket_hash,
            waiting_days=waiting,
            stale=waiting > CONFIRMED_STALE_DAYS,
            reason=self._reason(item),
            next_step=step,
            needs_user=needs_user,
            command=command,
        )

    @staticmethod
    def _reason(item: IntakeItem) -> str:
        kind = KIND_LABEL[item.classification.kind]
        parts = [f"{kind}", f"建议{DISPOSITION_LABEL[item.ticket.disposition]}"]
        if item.ticket.urgent_criterion is not None:
            parts.append(f"判据 {item.ticket.urgent_criterion.value}")
        return "，".join(parts) + f"；{item.ticket.rationale}"

    # ------------------------------------------------------------------ hints
    @staticmethod
    def _hints(
        project_id: str,
        board: MissionBoard,
        focus: tuple[FocusCard, ...],
        decide_now: tuple[TriageEntry, ...],
        ready_queue: tuple[TriageEntry, ...],
    ) -> tuple[str, ...]:
        hints: list[str] = []
        if len(board.active) > 1:
            ids = ", ".join(m.mission_id for m in board.active)
            hints.append(f"同时有多张卡在干（{ids}），按设计只该有一张：先问用户留哪张，不要自己判断。")
        for card in focus:
            if card.column == "PARKED" and card.stale:
                hints.append(
                    f"{card.mission_id} 已搁着 {card.parked_days} 天（超过 {PARKED_STALE_DAYS} 天）："
                    "由用户决定拿回还是作废，不要自己作废。"
                )
        waiting = [card for card in focus if card.column == "WAITING"]
        if waiting:
            ids = ", ".join(card.mission_id for card in waiting)
            hints.append(f"有 {len(waiting)} 张卡在等你（{ids}）：先看 python main.py pm missions --pid {project_id}。")
        old = [entry.item_id for entry in decide_now if entry.stale]
        if old:
            hints.append(
                f"以下条目等你决定已超过 {PROPOSED_STALE_DAYS} 天：{', '.join(old)}。确认、驳回或让 PM 改分诊单，别让它们一直挂着。"
            )
        forgotten = [entry.item_id for entry in ready_queue if entry.stale]
        if forgotten:
            hints.append(
                f"以下已确认的条目超过 {CONFIRMED_STALE_DAYS} 天还没转成计划：{', '.join(forgotten)}。"
            )
        return tuple(hints)
