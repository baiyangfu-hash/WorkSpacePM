"""Inbox persistence: intake items and plan classifications in the Continuity Store database.

The tables are created lazily by the first write, never by ``initialize``, so an existing store keeps
its exact table set until the inbox is used. A write refuses to run on a store that was never
initialised, because creating tables there would make a later ``initialize`` refuse the database.
Nothing here touches Mission, Work, Run, lease or checkpoint rows.
"""

from __future__ import annotations

import hmac
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from auto_pm.contracts.intake import (
    DISPOSITION_RANK,
    OPEN_INTAKE_STATUSES,
    Disposition,
    IntakeBrief,
    IntakeClassification,
    IntakeItem,
    IntakeKind,
    IntakeNote,
    IntakeNoteSummary,
    IntakeStatus,
    IntakeSummary,
    NoteStatus,
    TriageTicket,
)
from auto_pm.contracts.pm_facade import PlanningScopeCard
from auto_pm.infrastructure.continuity_store import (
    INTAKE_BINDINGS_DDL,
    INTAKE_ITEMS_DDL,
    INTAKE_NOTES_DDL,
    ContinuityStore,
    ContinuityStoreError,
)

_QUEUE_LIMIT = 5


def _title_key(title: str) -> str:
    return " ".join(title.split()).casefold()


class IntakeStore(ContinuityStore):
    """Append-and-decide persistence for inbox items, with an event trail for every change."""

    @contextmanager
    def _intake_transaction(self) -> Iterator[sqlite3.Connection]:
        if not self.db_path.is_file():
            raise ContinuityStoreError("Continuity Store 尚未初始化，拒绝创建收件箱表")
        with self._transaction() as conn:
            if not self._schema_versions(conn):
                raise ContinuityStoreError("Continuity Store 尚未初始化，拒绝创建收件箱表")
            conn.execute(INTAKE_ITEMS_DDL)
            conn.execute(INTAKE_BINDINGS_DDL)
            conn.execute(INTAKE_NOTES_DDL)
            yield conn

    @staticmethod
    def _item_from_json(raw: object) -> IntakeItem:
        try:
            return IntakeItem.model_validate_json(str(raw))
        except ValueError as error:
            raise ContinuityStoreError("收件箱条目记录无法读取") from error

    @staticmethod
    def _store_item(conn: sqlite3.Connection, item: IntakeItem, now: str, *, seq: int = 0) -> None:
        payload = item.model_dump_json()
        if seq:
            conn.execute(
                "INSERT INTO intake_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.item_id,
                    item.request_id,
                    item.project_id,
                    seq,
                    _title_key(item.title),
                    item.status.value,
                    item.ticket_hash,
                    payload,
                    now,
                    now,
                ),
            )
            return
        conn.execute(
            "UPDATE intake_items SET status=?, item_json=?, updated_at=? WHERE item_id=?",
            (item.status.value, payload, now, item.item_id),
        )

    @staticmethod
    def _note_from_json(raw: object) -> IntakeNote:
        try:
            return IntakeNote.model_validate_json(str(raw))
        except ValueError as error:
            raise ContinuityStoreError("待整理记录无法读取") from error

    @staticmethod
    def _store_note(conn: sqlite3.Connection, note: IntakeNote, now: str, *, seq: int = 0) -> None:
        payload = note.model_dump_json()
        if seq:
            conn.execute(
                "INSERT INTO intake_notes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    note.note_id,
                    note.request_id,
                    note.project_id,
                    seq,
                    _title_key(note.title),
                    note.status.value,
                    payload,
                    note.item_id or None,
                    now,
                    now,
                ),
            )
            return
        conn.execute(
            "UPDATE intake_notes SET status=?, note_json=?, item_id=?, updated_at=? WHERE note_id=?",
            (note.status.value, payload, note.item_id or None, now, note.note_id),
        )

    def add_note(
        self,
        *,
        request_id: str,
        project_id: str,
        title: str,
        original_words: str,
        kind_hint: IntakeKind,
        recorded_by: str,
    ) -> tuple[IntakeNote, bool]:
        """Record one raw note; a replay of the same request with the same content returns it with ``False``."""

        now = self._utc_now().isoformat()
        with self._intake_transaction() as conn:
            seq = int(
                conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM intake_notes WHERE project_id=?",
                    (project_id,),
                ).fetchone()[0]
            )
            try:
                note = IntakeNote(
                    note_id=f"NOTE-{project_id}-{seq:04d}",
                    request_id=request_id,
                    project_id=project_id,
                    title=title,
                    original_words=original_words,
                    kind_hint=kind_hint,
                    recorded_by=recorded_by,
                    created_at=now,
                )
            except ValueError as error:
                raise ContinuityStoreError(str(error)) from error
            existing = conn.execute(
                "SELECT note_json FROM intake_notes WHERE request_id=?", (request_id,)
            ).fetchone()
            if existing is not None:
                stored = self._note_from_json(existing["note_json"])
                if (stored.project_id, stored.title, stored.original_words, stored.kind_hint) != (
                    note.project_id,
                    note.title,
                    note.original_words,
                    note.kind_hint,
                ):
                    raise ContinuityStoreError("request_id 已绑定不同内容，拒绝覆盖既有待整理记录")
                return stored, False
            key = _title_key(note.title)
            clash = conn.execute(
                "SELECT note_id FROM intake_notes WHERE project_id=? AND title_key=? AND status='RAW'",
                (project_id, key),
            ).fetchone()
            if clash is not None:
                raise ContinuityStoreError(f"已有同名待整理记录: {clash['note_id']}")
            clash = conn.execute(
                """SELECT item_id FROM intake_items
                WHERE project_id=? AND title_key=? AND status IN ('PROPOSED', 'CONFIRMED')""",
                (project_id, key),
            ).fetchone()
            if clash is not None:
                raise ContinuityStoreError(f"已有同名未处理条目: {clash['item_id']}")
            self._store_note(conn, note, now, seq=seq)
            self._append_event(
                conn,
                note.note_id,
                "INTAKE_NOTE_RECORDED",
                {
                    "note_id": note.note_id,
                    "request_id": request_id,
                    "project_id": project_id,
                    "kind_hint": note.kind_hint.value,
                    "recorded_by": recorded_by,
                },
                f"intake-note-record:{request_id}",
                now,
                aggregate_type="intake_note",
            )
            return note, True

    def list_notes(
        self, project_id: str, statuses: tuple[NoteStatus, ...] = (NoteStatus.RAW,)
    ) -> tuple[IntakeNote, ...]:
        """List the notes of one project in the order they were recorded.  Read-only: creates neither ledger nor table."""

        if not self.db_path.is_file():
            return ()
        with self._read_connection() as conn:
            if not self._table_exists(conn, "intake_notes"):
                return ()
            rows = conn.execute(
                "SELECT note_json, status FROM intake_notes WHERE project_id=? ORDER BY seq",
                (project_id,),
            ).fetchall()
        wanted = {status.value for status in statuses}
        return tuple(
            self._note_from_json(row["note_json"]) for row in rows if str(row["status"]) in wanted
        )

    def note_summary(self, project_id: str) -> IntakeNoteSummary:
        """Count the raw notes of one project and name the oldest.  Read-only like ``list_notes``."""

        notes = self.list_notes(project_id)
        if not notes:
            return IntakeNoteSummary()
        oldest = notes[0]
        return IntakeNoteSummary(
            waiting=len(notes),
            oldest_note_id=oldest.note_id,
            oldest_recorded_by=oldest.recorded_by,
            oldest_created_at=oldest.created_at,
        )

    def _note_to_triage(
        self, conn: sqlite3.Connection, note_id: str, project_id: str, ticket: TriageTicket
    ) -> IntakeNote:
        """The three hard rules of ``--from-note``, judged inside the writing transaction."""

        row = conn.execute("SELECT note_json FROM intake_notes WHERE note_id=?", (note_id,)).fetchone()
        if row is None:
            raise ContinuityStoreError(f"待整理记录不存在: {note_id}")
        note = self._note_from_json(row["note_json"])
        if note.project_id != project_id:
            raise ContinuityStoreError(
                f"待整理记录 {note_id} 属于项目 {note.project_id}，和 --project-id {project_id} 不一致"
            )
        if note.status is not NoteStatus.RAW:
            raise ContinuityStoreError(f"待整理记录 {note_id} 已经转成 {note.item_id}，不能再转一次")
        if ticket.original_words != note.original_words:
            raise ContinuityStoreError(
                f"--original-words 和待整理记录 {note_id} 里的原话不逐字相同，拒绝转正；整理的人不能改原话"
            )
        return note

    def add_item(
        self,
        *,
        request_id: str,
        project_id: str,
        title: str,
        classification: IntakeClassification,
        ticket: TriageTicket,
        proposed_by: str,
        from_note: str = "",
        triaged_by: str = "",
    ) -> tuple[IntakeItem, bool]:
        """Record one proposed item; a replay of the same request returns it with ``False``.

        With ``from_note`` the raw note is turned into this item in the same transaction: either both are written or neither.
        """

        try:
            wanted_hash = IntakeItem.hash_for(project_id, title, classification, ticket)
        except ValueError as error:
            raise ContinuityStoreError(str(error)) from error
        now = self._utc_now().isoformat()
        with self._intake_transaction() as conn:
            existing = conn.execute(
                "SELECT item_json FROM intake_items WHERE request_id=?", (request_id,)
            ).fetchone()
            if existing is not None:
                item = self._item_from_json(existing["item_json"])
                if item.project_id != project_id or not hmac.compare_digest(
                    item.ticket_hash, wanted_hash
                ):
                    raise ContinuityStoreError("request_id 已绑定不同内容，拒绝覆盖既有收件箱条目")
                if from_note:
                    row = conn.execute(
                        "SELECT item_id FROM intake_notes WHERE note_id=?", (from_note,)
                    ).fetchone()
                    if row is None:
                        raise ContinuityStoreError(f"待整理记录不存在: {from_note}")
                    if str(row["item_id"] or "") != item.item_id:
                        raise ContinuityStoreError(
                            f"request_id 已经记成 {item.item_id}，它不是由待整理记录 {from_note} 转来的，拒绝"
                        )
                return item, False
            note = self._note_to_triage(conn, from_note, project_id, ticket) if from_note else None
            clash = conn.execute(
                """SELECT item_id FROM intake_items
                WHERE project_id=? AND title_key=? AND status IN ('PROPOSED', 'CONFIRMED')""",
                (project_id, _title_key(title)),
            ).fetchone()
            if clash is not None:
                raise ContinuityStoreError(f"已有同名未处理条目: {clash['item_id']}")
            clash = conn.execute(
                """SELECT note_id FROM intake_notes
                WHERE project_id=? AND title_key=? AND status='RAW' AND note_id<>?""",
                (project_id, _title_key(title), from_note),
            ).fetchone()
            if clash is not None:
                raise ContinuityStoreError(
                    f"已有同名待整理记录: {clash['note_id']}；要转正它请加 --from-note {clash['note_id']}"
                )
            seq = int(
                conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM intake_items WHERE project_id=?",
                    (project_id,),
                ).fetchone()[0]
            )
            try:
                item = IntakeItem.create(
                    item_id=f"INBOX-{project_id}-{seq:04d}",
                    request_id=request_id,
                    project_id=project_id,
                    title=title,
                    classification=classification,
                    ticket=ticket,
                    proposed_by=proposed_by,
                    created_at=now,
                )
            except ValueError as error:
                raise ContinuityStoreError(str(error)) from error
            self._store_item(conn, item, now, seq=seq)
            self._append_event(
                conn,
                item.item_id,
                "INTAKE_ITEM_RECORDED",
                {
                    "item_id": item.item_id,
                    "request_id": request_id,
                    "project_id": project_id,
                    "kind": classification.kind.value,
                    "disposition": ticket.disposition.value,
                    "ticket_hash": item.ticket_hash,
                    "proposed_by": proposed_by,
                },
                f"intake-item-record:{request_id}:{item.ticket_hash}",
                now,
                aggregate_type="intake_item",
            )
            if note is not None:
                try:
                    triaged = IntakeNote.model_validate(
                        {
                            **note.model_dump(mode="json"),
                            "status": NoteStatus.TRIAGED.value,
                            "item_id": item.item_id,
                            "triaged_by": triaged_by,
                            "triaged_at": now,
                        }
                    )
                except ValueError as error:
                    raise ContinuityStoreError(str(error)) from error
                self._store_note(conn, triaged, now)
                self._append_event(
                    conn,
                    note.note_id,
                    "INTAKE_NOTE_TRIAGED",
                    {
                        "note_id": note.note_id,
                        "item_id": item.item_id,
                        "project_id": project_id,
                        "triaged_by": triaged_by,
                    },
                    f"intake-note-triage:{note.note_id}:{item.item_id}",
                    now,
                    aggregate_type="intake_note",
                )
            return item, True

    def get_item(self, item_id: str) -> IntakeItem:
        """Read one item by its identifier."""

        if not self.db_path.is_file():
            raise ContinuityStoreError(f"收件箱条目不存在: {item_id}")
        with self._read_connection() as conn:
            if not self._table_exists(conn, "intake_items"):
                raise ContinuityStoreError(f"收件箱条目不存在: {item_id}")
            row = conn.execute(
                "SELECT item_json FROM intake_items WHERE item_id=?", (item_id,)
            ).fetchone()
            if row is None:
                raise ContinuityStoreError(f"收件箱条目不存在: {item_id}")
            return self._item_from_json(row["item_json"])

    def list_items(
        self, project_id: str, statuses: tuple[IntakeStatus, ...] = OPEN_INTAKE_STATUSES
    ) -> tuple[IntakeItem, ...]:
        """List the items of one project in the order they were proposed."""

        if not self.db_path.is_file():
            return ()
        with self._read_connection() as conn:
            if not self._table_exists(conn, "intake_items"):
                return ()
            rows = conn.execute(
                "SELECT item_json, status FROM intake_items WHERE project_id=? ORDER BY seq",
                (project_id,),
            ).fetchall()
        wanted = {status.value for status in statuses}
        return tuple(
            self._item_from_json(row["item_json"]) for row in rows if str(row["status"]) in wanted
        )

    def decide_item(
        self,
        item_id: str,
        *,
        status: IntakeStatus,
        ticket_hash: str,
        decided_by: str,
        decision_ref: str,
        note: str = "",
    ) -> IntakeItem:
        """Confirm or reject a proposed item; the caller must name the exact content hash."""

        if status not in (IntakeStatus.CONFIRMED, IntakeStatus.REJECTED):
            raise ContinuityStoreError("只能把条目决定为 CONFIRMED 或 REJECTED")
        now = self._utc_now().isoformat()
        with self._intake_transaction() as conn:
            row = conn.execute(
                "SELECT item_json FROM intake_items WHERE item_id=?", (item_id,)
            ).fetchone()
            if row is None:
                raise ContinuityStoreError(f"收件箱条目不存在: {item_id}")
            item = self._item_from_json(row["item_json"])
            if not hmac.compare_digest(item.ticket_hash, ticket_hash):
                raise ContinuityStoreError("ticket_hash 与条目内容不一致，拒绝决定")
            if (
                item.status is status
                and item.decided_by == decided_by
                and item.decision_ref == decision_ref
            ):
                return item
            if item.status is not IntakeStatus.PROPOSED:
                raise ContinuityStoreError(f"只有 PROPOSED 条目可以决定，当前为 {item.status.value}")
            if status is IntakeStatus.CONFIRMED and item.ticket.disposition is Disposition.REJECT:
                raise ContinuityStoreError("PM 建议驳回此条目：同意请使用 reject，不同意请重新分诊")
            try:
                decided = IntakeItem.model_validate(
                    {
                        **item.model_dump(mode="json"),
                        "status": status.value,
                        "decided_by": decided_by,
                        "decision_ref": decision_ref,
                        "decided_at": now,
                        "note": note,
                    }
                )
            except ValueError as error:
                raise ContinuityStoreError(str(error)) from error
            self._store_item(conn, decided, now)
            self._append_event(
                conn,
                item_id,
                f"INTAKE_ITEM_{status.value}",
                {
                    "item_id": item_id,
                    "ticket_hash": item.ticket_hash,
                    "decided_by": decided_by,
                    "decision_ref": decision_ref,
                },
                f"intake-item-decide:{item_id}:{status.value}:{decision_ref}",
                now,
                aggregate_type="intake_item",
            )
            return decided

    def resolve_planning_classification(
        self,
        request_id: str,
        project_id: str,
        classification: IntakeClassification | None,
        item_id: str = "",
    ) -> tuple[IntakeClassification | None, str]:
        """Read and validate a filing without creating a binding or consuming an item."""
        if not self.db_path.is_file():
            if item_id:
                raise ContinuityStoreError(f"收件箱条目不存在: {item_id}")
            return classification, ""
        with self._read_connection() as conn:
            return self._resolve_planning_classification(
                conn, request_id, project_id, classification, item_id
            )

    def _resolve_planning_classification(
        self,
        conn: sqlite3.Connection,
        request_id: str,
        project_id: str,
        classification: IntakeClassification | None,
        item_id: str,
    ) -> tuple[IntakeClassification | None, str]:
        draft = (
            conn.execute(
                "SELECT subject_project_id FROM planning_drafts WHERE request_id=?", (request_id,)
            ).fetchone()
            if self._table_exists(conn, "planning_drafts")
            else None
        )
        if draft is not None and str(draft["subject_project_id"]) != project_id:
            raise ContinuityStoreError("request_id 与计划不属于同一项目")
        if self._table_exists(conn, "planning_draft_intake_bindings"):
            bound = conn.execute(
                "SELECT classification_json, item_id FROM planning_draft_intake_bindings "
                "WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if bound is not None:
                try:
                    stored = IntakeClassification.model_validate_json(
                        str(bound["classification_json"])
                    )
                except ValueError as error:
                    raise ContinuityStoreError("分类绑定记录无法读取") from error
                bound_item_id = str(bound["item_id"] or "")
                if (classification is not None and classification != stored) or (
                    item_id and item_id != bound_item_id
                ):
                    raise ContinuityStoreError("PlanningDraft 已绑定不同的分类或收件箱条目")
                classification, item_id = stored, bound_item_id
        if item_id:
            row = (
                conn.execute(
                    "SELECT item_json FROM intake_items WHERE item_id=?", (item_id,)
                ).fetchone()
                if self._table_exists(conn, "intake_items")
                else None
            )
            if row is None:
                raise ContinuityStoreError(f"收件箱条目不存在: {item_id}")
            item = self._item_from_json(row["item_json"])
            if item.project_id != project_id:
                raise ContinuityStoreError("收件箱条目与计划不属于同一项目")
            if classification is not None and item.classification != classification:
                raise ContinuityStoreError("计划的分类与收件箱条目不一致")
            replay = item.status is IntakeStatus.PLANNED and item.plan_request_id == request_id
            if item.status is not IntakeStatus.CONFIRMED and not replay:
                raise ContinuityStoreError(
                    f"只有已确认的条目可以转为计划，当前为 {item.status.value}"
                )
            classification = item.classification
        return classification, item_id

    def submit_classified_planning_scope_card(
        self,
        card: PlanningScopeCard,
        classification: IntakeClassification,
        item_id: str,
        submitted_by: str,
        *,
        allow_approved_replay: bool = False,
    ) -> int:
        """Commit the readable card, filing, item consumption and events on one connection."""
        now = self._utc_now().isoformat()
        with self._intake_transaction() as conn:
            self._resolve_planning_classification(
                conn, card.request_id, card.subject_project_id, classification, item_id
            )
            revision = self._submit_planning_scope_card(
                conn, card, submitted_by, allow_approved_replay=allow_approved_replay
            )
            self._bind_planning_classification(conn, card.request_id, classification, item_id, now)
            return revision

    def bind_planning_classification(
        self, request_id: str, classification: IntakeClassification, item_id: str = ""
    ) -> IntakeClassification:
        """Retain the legacy store API; facade planning uses the atomic card submission."""
        with self._intake_transaction() as conn:
            return self._bind_planning_classification(
                conn, request_id, classification, item_id, self._utc_now().isoformat()
            )

    def _bind_planning_classification(
        self,
        conn: sqlite3.Connection,
        request_id: str,
        classification: IntakeClassification,
        item_id: str,
        now: str,
    ) -> IntakeClassification:
        draft = conn.execute(
            "SELECT subject_project_id FROM planning_drafts WHERE request_id=?", (request_id,)
        ).fetchone()
        if draft is None:
            raise ContinuityStoreError(f"PlanningDraft 不存在: {request_id}")
        bound = conn.execute(
            "SELECT classification_json, item_id FROM planning_draft_intake_bindings "
            "WHERE request_id=?",
            (request_id,),
        ).fetchone()
        if bound is not None:
            try:
                stored = IntakeClassification.model_validate_json(str(bound["classification_json"]))
            except ValueError as error:
                raise ContinuityStoreError("分类绑定记录无法读取") from error
            if stored != classification or (item_id and str(bound["item_id"] or "") != item_id):
                raise ContinuityStoreError("PlanningDraft 已绑定不同的分类或收件箱条目")
            return stored
        if item_id:
            row = conn.execute(
                "SELECT item_json FROM intake_items WHERE item_id=?", (item_id,)
            ).fetchone()
            if row is None:
                raise ContinuityStoreError(f"收件箱条目不存在: {item_id}")
            item = self._item_from_json(row["item_json"])
            if item.status is not IntakeStatus.CONFIRMED:
                raise ContinuityStoreError(
                    f"只有已确认的条目可以转为计划，当前为 {item.status.value}"
                )
            if item.project_id != str(draft["subject_project_id"]):
                raise ContinuityStoreError("收件箱条目与计划不属于同一项目")
            if item.classification != classification:
                raise ContinuityStoreError("计划的分类与收件箱条目不一致")
            try:
                planned = IntakeItem.model_validate(
                    {
                        **item.model_dump(mode="json"),
                        "status": IntakeStatus.PLANNED.value,
                        "plan_request_id": request_id,
                    }
                )
            except ValueError as error:
                raise ContinuityStoreError(str(error)) from error
            self._store_item(conn, planned, now)
            self._append_event(
                conn,
                item_id,
                "INTAKE_ITEM_PLANNED",
                {"item_id": item_id, "plan_request_id": request_id},
                f"intake-item-plan:{item_id}:{request_id}",
                now,
                aggregate_type="intake_item",
            )
        conn.execute(
            "INSERT INTO planning_draft_intake_bindings VALUES (?, ?, ?, ?)",
            (request_id, classification.model_dump_json(), item_id or None, now),
        )
        self._append_event(
            conn,
            request_id,
            "PLANNING_DRAFT_INTAKE_BOUND",
            {
                "request_id": request_id,
                "kind": classification.kind.value,
                "item_id": item_id,
            },
            f"planning-draft-intake-bind:{request_id}",
            now,
            aggregate_type="planning_draft",
        )
        return classification

    def get_planning_classification(self, request_id: str) -> tuple[IntakeClassification, str] | None:
        """Return the bound classification and inbox item id of a plan request, if any.

        The lookup sits on the plan path, so it runs in a short write transaction like every other step
        of that path instead of the strict read snapshot, which refuses while another connection holds
        the database file open. It creates nothing.
        """

        if not self.db_path.is_file():
            return None
        with self._transaction() as conn:
            if not self._table_exists(conn, "planning_draft_intake_bindings"):
                return None
            row = conn.execute(
                "SELECT classification_json, item_id FROM planning_draft_intake_bindings "
                "WHERE request_id=?",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            classification = IntakeClassification.model_validate_json(str(row["classification_json"]))
        except ValueError as error:
            raise ContinuityStoreError("分类绑定记录无法读取") from error
        return classification, str(row["item_id"] or "")

    def summary(self, project_id: str) -> IntakeSummary:
        """Compile the read-only inbox view: confirmed items first, then by the recommended urgency."""

        items = self.list_items(project_id, OPEN_INTAKE_STATUSES)
        ordered = sorted(
            items,
            key=lambda item: (
                0 if item.status is IntakeStatus.CONFIRMED else 1,
                DISPOSITION_RANK[item.ticket.disposition],
                item.item_id,
            ),
        )
        return IntakeSummary(
            awaiting_confirmation=sum(1 for item in items if item.status is IntakeStatus.PROPOSED),
            confirmed_waiting=sum(1 for item in items if item.status is IntakeStatus.CONFIRMED),
            queue=tuple(
                IntakeBrief(
                    item_id=item.item_id,
                    kind=item.classification.kind,
                    title=item.title,
                    status=item.status,
                    disposition=item.ticket.disposition,
                )
                for item in ordered[:_QUEUE_LIMIT]
            ),
        )
