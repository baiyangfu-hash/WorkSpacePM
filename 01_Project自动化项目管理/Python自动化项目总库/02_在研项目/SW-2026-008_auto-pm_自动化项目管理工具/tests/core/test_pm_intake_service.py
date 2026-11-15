"""PM front desk: inbox store and service rules (card CARD-SW008-M2-P1, scenarios sv01-sv14).

Every test runs the real store and the real service on a temporary Git workspace with a real Continuity Store database.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from auto_pm.contracts.intake import (
    ChangeAction,
    Disposition,
    IntakeClassification,
    IntakeItem,
    IntakeKind,
    IntakeNote,
    IntakeNoteSummary,
    IntakeStatus,
    NoteStatus,
    TriageTicket,
    UrgentCriterion,
    note_actor_label,
)
from auto_pm.contracts.pm_facade import PlanningDraft, PmIntent
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.intake_store import IntakeStore
from tests.core.test_continuity_execution_service import Clock, _checkpoint, _services, _start

if TYPE_CHECKING:
    from auto_pm.application.core.pm_intake_service import PmIntakeError, PmIntakeService
else:
    from auto_pm.application.core.pm_intake_service import PmIntakeError, PmIntakeService

PYTHON_PROJECT = "SW-2026-901"
PLC_PROJECT = "DJ-2026-902"
BARE_PROJECT = "SW-2026-903"
APPROVER = "fubai"
CONFIRMATION = "user-confirmation:chat-20261005-a1"
INTAKE_TABLES = {"intake_items", "planning_draft_intake_bindings"}


@dataclass
class Desk:
    root: Path
    service: PmIntakeService
    counter: int = 0

    def ticket(self, **changes: Any) -> TriageTicket:
        values: dict[str, Any] = {
            "original_words": "登录页偶发白屏",
            "affects": "SW-2026-901 登录页",
            "duplicate_check": "查过台账与收件箱，没有同类条目",
            "evidence": ("file:README.md",),
            "disposition": Disposition.AFTER_CURRENT,
            "rationale": "不阻塞当前卡，当前卡收口后处理",
            "alternatives": ("并入下个迭代",),
            "cost_risk": "半天；低风险",
        }
        values.update(changes)
        return TriageTicket(**values)

    def propose(
        self,
        title: str = "登录页偶发白屏",
        *,
        kind: IntakeKind = IntakeKind.BUG,
        project: str = PYTHON_PROJECT,
        request_id: str = "",
        ticket: TriageTicket | None = None,
        impact_scope: tuple[str, ...] = (),
    ) -> IntakeItem:
        self.counter += 1
        classification = self.service.classify(
            project,
            kind=kind,
            change_action=ChangeAction.ADD if kind is IntakeKind.CHANGE else None,
            domain="",
            impact_scope=impact_scope,
        )
        item, _ = self.service.propose(
            request_id=request_id or f"REQ-INTAKE-{self.counter:03d}",
            project_id=project,
            title=title,
            classification=classification,
            ticket=ticket or self.ticket(),
            proposed_by="pm-test",
        )
        return item

    def confirm(self, item: IntakeItem, *, reference: str = CONFIRMATION) -> IntakeItem:
        return self.service.confirm(
            item.item_id, ticket_hash=item.ticket_hash, approver=APPROVER, approval_evidence_ref=reference
        )

    def draft(self, request_id: str = "REQ-PLAN-001", project: str = PYTHON_PROJECT) -> str:
        ContinuityStore(self.root).create_planning_draft(
            PlanningDraft.from_intent(
                PmIntent(
                    subject_project_id=project,
                    request_id=request_id,
                    objective="Plan the confirmed item",
                    acceptance_criteria=("A plan exists.",),
                )
            )
        )
        return request_id

    def sql(self, statement: str, *parameters: Any) -> list[tuple[Any, ...]]:
        with closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db")) as conn:
            return [tuple(row) for row in conn.execute(statement, parameters).fetchall()]

    def tables(self) -> set[str]:
        return {str(row[0]) for row in self.sql("SELECT name FROM sqlite_master WHERE type='table'")}

    def events(self, event_type: str = "") -> int:
        if event_type:
            return int(self.sql("SELECT COUNT(*) FROM events WHERE event_type=?", event_type)[0][0])
        return int(self.sql("SELECT COUNT(*) FROM events")[0][0])



@pytest.mark.parametrize("source", ["direct", "inbox"])
@pytest.mark.parametrize("field", ["kind", "action", "domain", "scope", "project"])
def test_audit_f05_bound_replay_checks_every_explicit_field(
    desk: Desk,
    source: str,
    field: str,
) -> None:
    item = desk.confirm(desk.propose(kind=IntakeKind.CHANGE))
    request = desk.draft()
    filing = item.classification
    item_id = item.item_id if source == "inbox" else ""
    IntakeStore(desk.root).bind_planning_classification(request, filing, item_id)
    before = desk.sql("SELECT * FROM events ORDER BY rowid")
    bound_before = desk.sql("SELECT * FROM planning_draft_intake_bindings")
    options: dict[str, Any] = {
        "request_id": request,
        "kind": None,
        "change_action": None,
        "domain": "",
        "impact_scope": (),
        "inbox_id": "",
    }
    project = PYTHON_PROJECT
    if field == "project":
        project = PLC_PROJECT
    else:
        key, value = {
            "kind": ("kind", IntakeKind.BUG),
            "action": ("change_action", ChangeAction.REMOVE),
            "domain": ("domain", "PLC"),
            "scope": ("impact_scope", ("SYSTEM",)),
        }[field]
        options[key] = value
    with pytest.raises(PmIntakeError, match="不一致|同一项目"):
        desk.service.plan_classification(project, **options)
    assert desk.sql("SELECT * FROM events ORDER BY rowid") == before
    assert desk.sql("SELECT * FROM planning_draft_intake_bindings") == bound_before
    options.update(kind=None, change_action=None, domain="", impact_scope=())
    assert desk.service.plan_classification(PYTHON_PROJECT, **options) == (filing, item_id)
    options.update(
        kind=filing.kind,
        change_action=filing.change_action,
        domain=filing.domain,
        impact_scope=filing.impact_scope,
    )
    assert desk.service.plan_classification(PYTHON_PROJECT, **options) == (filing, item_id)


@pytest.mark.parametrize("case", ["directory", "mixed", "missing", "external", "broken", "query"])
def test_audit_f06_file_evidence_requires_a_provable_regular_file(
    desk: Desk,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    import os

    evidence: tuple[str, ...] = ("file:README.md",)
    link: Path | None = None
    if case in ("directory", "mixed"):
        (desk.root / "directory").mkdir()
        evidence = (
            ("file:directory",) if case == "directory" else ("file:README.md", "file:directory")
        )
    elif case == "missing":
        evidence = ("file:missing.txt",)
    elif case in ("external", "broken"):
        outside = desk.root.parent / f"outside-{case}"
        outside.mkdir()
        (outside / "proof.txt").write_text("outside", encoding="utf-8", errors="replace")
        link = desk.root / "link"
        if os.name == "nt":
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            assert result.returncode == 0, result.stdout + result.stderr
        else:
            link.symlink_to(outside, target_is_directory=True)
        if case == "broken":
            outside.rename(outside.with_name(outside.name + "-moved"))
        evidence = ("file:link/proof.txt",)
    before = desk.sql("SELECT * FROM events ORDER BY rowid")
    try:
        with monkeypatch.context() as patch:
            if case == "query":
                real_is_file = Path.is_file

                def fail_query(path: Path) -> bool:
                    if path == desk.root / "README.md":
                        raise PermissionError("audit status query")
                    return real_is_file(path)

                patch.setattr(Path, "is_file", fail_query)
            with pytest.raises(PmIntakeError, match="取证"):
                desk.propose(ticket=desk.ticket(evidence=evidence))
        assert desk.sql("SELECT * FROM events ORDER BY rowid") == before
        assert desk.service.list_items(PYTHON_PROJECT) == ()
        assert desk.sql("SELECT COUNT(*) FROM intake_items") == [(0,)]  # the tables exist from initialize (073); a refusal stores no row
        ordinary = desk.propose(ticket=desk.ticket(evidence=("file:README.md",)))
        assert ordinary.ticket.evidence == ("file:README.md",)
        after = desk.sql("SELECT * FROM events ORDER BY rowid")
        replay, created = desk.service.propose(
            request_id=ordinary.request_id, project_id=ordinary.project_id,
            title=ordinary.title, classification=ordinary.classification,
            ticket=ordinary.ticket, proposed_by="replay",
        )
        assert (replay, created) == (ordinary, False)
        assert desk.sql("SELECT * FROM events ORDER BY rowid") == after
    finally:
        if link is not None:
            if os.name == "nt":
                link.rmdir()
            else:
                link.unlink()



def _repository(root: Path) -> None:
    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    (root / "README.md").write_text("baseline\n", encoding="utf-8", errors="replace")
    (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8", errors="replace")
    subprocess.run(["git", "-C", str(root), "add", "README.md", ".gitignore"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=Intake Test", "-c", "user.email=intake@example.invalid",
         "commit", "-m", "baseline"],
        check=True, capture_output=True,
    )


def _build_desk(root: Path) -> Desk:
    _repository(root)
    projects = []
    for project, stack in ((PYTHON_PROJECT, "python"), (PLC_PROJECT, "plc"), (BARE_PROJECT, "")):
        directory = root / project
        directory.mkdir()
        if stack:
            (directory / ".copier-answers.yml").write_text(
                f"project_id: {project}\nproject_name: Intake Test\nstack: {stack}\n", encoding="utf-8"
            )
        projects.append({"project_id": project, "project_root": project, "development_root": project})
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps({"schema_version": "workspace-registry.v1", "projects": projects}), encoding="utf-8"
    )
    ContinuityStore(root).initialize("2026-10-05T00:00:00+00:00", "test")
    return Desk(root, PmIntakeService(root))


@pytest.fixture
def desk(tmp_path: Path) -> Desk:
    return _build_desk(tmp_path)


def test_sv01_items_are_numbered_per_project_and_leave_an_event(desk: Desk) -> None:
    first = desk.propose("第一条")
    second = desk.propose("第二条")
    assert (first.item_id, second.item_id) == ("INBOX-SW-2026-901-0001", "INBOX-SW-2026-901-0002")
    assert first.status is IntakeStatus.PROPOSED and first.decided_by == ""
    assert [item.item_id for item in desk.service.list_items(PYTHON_PROJECT)] == [first.item_id, second.item_id]
    assert desk.service.get(second.item_id) == second
    assert desk.events("INTAKE_ITEM_RECORDED") == 2
    row = desk.sql("SELECT aggregate_type, aggregate_id FROM events WHERE event_type='INTAKE_ITEM_RECORDED' ORDER BY rowid")
    assert row == [("intake_item", first.item_id), ("intake_item", second.item_id)]
    assert desk.sql("SELECT seq, status FROM intake_items ORDER BY seq") == [(1, "PROPOSED"), (2, "PROPOSED")]


def test_sv02_a_replay_returns_the_same_item_and_changed_content_is_refused(desk: Desk) -> None:
    first = desk.propose(request_id="REQ-REPLAY")
    events = desk.events()
    classification = desk.service.classify(
        PYTHON_PROJECT, kind=IntakeKind.BUG, change_action=None, domain="", impact_scope=()
    )
    again, created = desk.service.propose(
        request_id="REQ-REPLAY",
        project_id=PYTHON_PROJECT,
        title="登录页偶发白屏",
        classification=classification,
        ticket=desk.ticket(),
        proposed_by="someone-else",
    )
    assert (again, created) == (first, False)
    assert desk.events() == events and len(desk.service.list_items(PYTHON_PROJECT)) == 1
    for changes in ({"rationale": "换了一个理由"}, {"disposition": Disposition.INBOX_WAIT}):
        with pytest.raises(PmIntakeError, match="request_id"):
            desk.service.propose(
                request_id="REQ-REPLAY", project_id=PYTHON_PROJECT, title="登录页偶发白屏",
                classification=classification, ticket=desk.ticket(**changes), proposed_by="pm-test",
            )
    assert desk.events() == events and len(desk.service.list_items(PYTHON_PROJECT)) == 1


def test_sv03_an_open_duplicate_title_is_refused_until_the_first_is_rejected(desk: Desk) -> None:
    first = desk.propose("登录页  偶发白屏")
    for variant in ("登录页 偶发白屏", " 登录页   偶发白屏 ", "登录页\t偶发白屏"):
        with pytest.raises(PmIntakeError, match=first.item_id):
            desk.propose(variant)
    assert desk.propose("登录页偶发白屏").item_id == "INBOX-SW-2026-901-0002"
    desk.service.reject(first.item_id, ticket_hash=first.ticket_hash, approver=APPROVER, approval_evidence_ref=CONFIRMATION)
    assert desk.propose("登录页 偶发白屏").item_id == "INBOX-SW-2026-901-0003"
    assert desk.propose("AbC").item_id == "INBOX-SW-2026-901-0004"
    with pytest.raises(PmIntakeError, match="同名"):
        desk.propose("abc")


def test_sv04_a_missing_evidence_file_or_unknown_project_is_refused_without_a_trace(desk: Desk) -> None:
    before = (desk.events(), desk.tables())
    with pytest.raises(PmIntakeError, match="取证文件不存在"):
        desk.propose(ticket=desk.ticket(evidence=("file:docs/not-there.md",)))
    with pytest.raises(PmIntakeError, match="项目不存在"):
        desk.service.propose(
            request_id="REQ-GHOST",
            project_id="SW-GHOST-001",
            title="幽灵项目",
            classification=IntakeClassification(kind=IntakeKind.BUG, domain="SCPT"),
            ticket=desk.ticket(),
            proposed_by="pm-test",
        )
    assert (desk.events(), desk.tables()) == before
    assert desk.propose(ticket=desk.ticket(evidence=("file:README.md", "cmd:git status --short")))


def test_sv05_a_safety_emergency_must_declare_the_safe_impact_scope(desk: Desk) -> None:
    ticket = desk.ticket(urgent_criterion=UrgentCriterion.SAFETY, disposition=Disposition.INTERRUPT_NOW)
    with pytest.raises(PmIntakeError, match="SAFE"):
        desk.propose("急停回路失效", kind=IntakeKind.URGENT, project=PLC_PROJECT, ticket=ticket, impact_scope=("MODULE",))
    item = desk.propose("急停回路失效", kind=IntakeKind.URGENT, project=PLC_PROJECT, ticket=ticket, impact_scope=("MODULE", "SAFE"))
    assert item.classification.domain == "PLC" and item.classification.business_nature == "EMRG"
    other = desk.ticket(urgent_criterion=UrgentCriterion.DATA_LOSS, disposition=Disposition.INTERRUPT_NOW)
    assert desk.propose("数据库被截断", kind=IntakeKind.URGENT, ticket=other).classification.urgency == "urgent"


def test_sv06_a_confirmation_binds_the_exact_content_and_a_human_approver(desk: Desk) -> None:
    item = desk.propose()
    events = desk.events()
    for approver, reference, ticket_hash in (
        (APPROVER, CONFIRMATION, "0" * 64),
        (APPROVER, CONFIRMATION, item.ticket_hash[:-1] + ("0" if item.ticket_hash[-1] != "0" else "1")),
        ("claude", CONFIRMATION, item.ticket_hash),
        ("GPT-5", CONFIRMATION, item.ticket_hash),
        (APPROVER, "chat said yes", item.ticket_hash),
        (APPROVER, "user-confirmation:short", item.ticket_hash),
        (APPROVER, CONFIRMATION, "not-a-hash"),
    ):
        with pytest.raises(PmIntakeError):
            desk.service.confirm(item.item_id, ticket_hash=ticket_hash, approver=approver, approval_evidence_ref=reference)
    assert desk.service.get(item.item_id).status is IntakeStatus.PROPOSED and desk.events() == events
    confirmed = desk.confirm(item)
    assert confirmed.status is IntakeStatus.CONFIRMED
    assert (confirmed.decided_by, confirmed.decision_ref) == (APPROVER, CONFIRMATION) and confirmed.decided_at
    assert desk.events("INTAKE_ITEM_CONFIRMED") == 1
    assert desk.confirm(item) == confirmed and desk.events("INTAKE_ITEM_CONFIRMED") == 1
    with pytest.raises(PmIntakeError, match="PROPOSED"):
        desk.confirm(item, reference="user-confirmation:chat-20261005-b2")
    with pytest.raises(PmIntakeError, match="PROPOSED"):
        desk.service.reject(item.item_id, ticket_hash=item.ticket_hash, approver=APPROVER, approval_evidence_ref=CONFIRMATION)
    assert desk.service.get(item.item_id) == confirmed


def test_sv07_a_rejected_item_stays_rejected(desk: Desk) -> None:
    item = desk.propose()
    rejected = desk.service.reject(
        item.item_id, ticket_hash=item.ticket_hash, approver=APPROVER, approval_evidence_ref=CONFIRMATION, note="不做了"
    )
    assert rejected.status is IntakeStatus.REJECTED and rejected.note == "不做了"
    with pytest.raises(PmIntakeError, match="PROPOSED"):
        desk.confirm(item)
    assert desk.service.list_items(PYTHON_PROJECT) == ()
    assert desk.service.list_items(PYTHON_PROJECT, (IntakeStatus.REJECTED,)) == (rejected,)
    assert desk.events("INTAKE_ITEM_REJECTED") == 1
    with pytest.raises(PmIntakeError, match="不存在"):
        desk.service.get("INBOX-SW-2026-901-0099")


def test_sv16_an_item_recommended_for_rejection_can_only_be_rejected(desk: Desk) -> None:
    item = desk.propose("建议驳回的条目", ticket=desk.ticket(disposition=Disposition.REJECT))
    with pytest.raises(PmIntakeError, match="reject"):
        desk.confirm(item)
    assert desk.service.get(item.item_id).status is IntakeStatus.PROPOSED and desk.events("INTAKE_ITEM_CONFIRMED") == 0
    rejected = desk.service.reject(item.item_id, ticket_hash=item.ticket_hash, approver=APPROVER, approval_evidence_ref=CONFIRMATION)
    assert rejected.status is IntakeStatus.REJECTED


def test_sv08_an_uninitialised_store_is_refused_and_never_gains_inbox_tables(tmp_path: Path) -> None:
    _repository(tmp_path)
    (tmp_path / "SW-2026-901").mkdir()
    store = IntakeStore(tmp_path)
    classification = IntakeClassification(kind=IntakeKind.BUG, domain="SCPT")
    ticket = TriageTicket(
        original_words="x", affects="x", duplicate_check="x", evidence=("file:README.md",),
        disposition=Disposition.INBOX_WAIT, rationale="x", alternatives=("x",), cost_risk="x",
    )
    with pytest.raises(ContinuityStoreError, match="尚未初始化"):
        store.add_item(request_id="R1", project_id=PYTHON_PROJECT, title="t", classification=classification, ticket=ticket, proposed_by="p")
    assert not (tmp_path / ".auto-pm" / "continuity.db").exists()
    assert store.list_items(PYTHON_PROJECT) == () and store.summary(PYTHON_PROJECT).is_empty
    (tmp_path / ".auto-pm").mkdir()
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn, conn:
        conn.execute("CREATE TABLE unrelated (x TEXT)")
    with pytest.raises(ContinuityStoreError):
        store.add_item(request_id="R1", project_id=PYTHON_PROJECT, title="t", classification=classification, ticket=ticket, proposed_by="p")
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
        assert {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {"unrelated"}


def test_sv09_the_inbox_tables_exist_after_initialize_and_an_old_ledger_without_them_is_only_filled_by_a_write(desk: Desk) -> None:
    assert INTAKE_TABLES <= desk.tables()  # 073: the base DDL creates them
    with closing(sqlite3.connect(desk.root / ".auto-pm" / "continuity.db")) as conn, conn:
        conn.execute("DROP TABLE planning_draft_intake_bindings")
        conn.execute("DROP TABLE intake_items")
    assert desk.tables().isdisjoint(INTAKE_TABLES)  # what a ledger from before 073 looks like
    store = IntakeStore(desk.root)
    assert store.list_items(PYTHON_PROJECT) == () and store.summary(PYTHON_PROJECT).is_empty
    assert store.get_planning_classification("REQ-NONE") is None
    with pytest.raises(ContinuityStoreError, match="不存在"):
        store.get_item("INBOX-SW-2026-901-0001")
    assert desk.tables().isdisjoint(INTAKE_TABLES)  # reads never create them
    desk.propose()
    assert INTAKE_TABLES <= desk.tables()  # the first write still works on such a ledger
    ContinuityStore(desk.root).initialize("2026-10-05T01:00:00+00:00", "test")
    assert len(desk.service.list_items(PYTHON_PROJECT)) == 1


def test_sv10_binding_a_confirmed_item_marks_it_planned_exactly_once(desk: Desk) -> None:
    item = desk.confirm(desk.propose("要转计划的条目"))
    request = desk.draft()
    store = IntakeStore(desk.root)
    assert store.bind_planning_classification(request, item.classification, item.item_id) == item.classification
    planned = desk.service.get(item.item_id)
    assert planned.status is IntakeStatus.PLANNED and planned.plan_request_id == request
    assert store.get_planning_classification(request) == (item.classification, item.item_id)
    assert desk.events("INTAKE_ITEM_PLANNED") == 1 and desk.events("PLANNING_DRAFT_INTAKE_BOUND") == 1
    store.bind_planning_classification(request, item.classification, item.item_id)
    store.bind_planning_classification(request, item.classification)
    assert desk.events("INTAKE_ITEM_PLANNED") == 1 and desk.events("PLANNING_DRAFT_INTAKE_BOUND") == 1
    other = IntakeClassification(kind=IntakeKind.CHANGE, change_action=ChangeAction.FREEZE, domain="SCPT")
    with pytest.raises(ContinuityStoreError, match="已绑定"):
        store.bind_planning_classification(request, other)
    with pytest.raises(ContinuityStoreError, match="已绑定"):
        store.bind_planning_classification(request, item.classification, "INBOX-SW-2026-901-0099")
    second = desk.draft("REQ-PLAN-002")
    with pytest.raises(ContinuityStoreError, match="已确认"):
        store.bind_planning_classification(second, item.classification, item.item_id)
    assert desk.service.get(item.item_id) == planned


def test_sv11_only_a_confirmed_item_of_the_same_project_and_classification_can_be_bound(desk: Desk) -> None:
    store = IntakeStore(desk.root)
    proposed = desk.propose("还没确认")
    request = desk.draft()
    with pytest.raises(ContinuityStoreError, match="已确认"):
        store.bind_planning_classification(request, proposed.classification, proposed.item_id)
    confirmed = desk.confirm(desk.propose("已确认"))
    foreign = desk.draft("REQ-PLAN-003", PLC_PROJECT)
    with pytest.raises(ContinuityStoreError, match="同一项目"):
        store.bind_planning_classification(foreign, confirmed.classification, confirmed.item_id)
    other = IntakeClassification(kind=IntakeKind.DEBT, domain="SCPT")
    with pytest.raises(ContinuityStoreError, match="不一致"):
        store.bind_planning_classification(request, other, confirmed.item_id)
    with pytest.raises(ContinuityStoreError, match="PlanningDraft 不存在"):
        store.bind_planning_classification("REQ-NO-DRAFT", confirmed.classification, confirmed.item_id)
    assert desk.service.get(confirmed.item_id).status is IntakeStatus.CONFIRMED
    assert desk.service.get(proposed.item_id).status is IntakeStatus.PROPOSED
    assert desk.events("INTAKE_ITEM_PLANNED") == 0


def test_sv12_the_domain_is_explicit_or_follows_the_project_stack(desk: Desk) -> None:
    assert desk.service.resolve_domain(PYTHON_PROJECT) == "SCPT"
    assert desk.service.resolve_domain(PLC_PROJECT) == "PLC"
    assert desk.service.resolve_domain(BARE_PROJECT, "DOCU") == "DOCU"
    assert desk.service.resolve_domain(PYTHON_PROJECT, "PLC") == "PLC"
    with pytest.raises(PmIntakeError, match="--domain"):
        desk.service.resolve_domain(BARE_PROJECT)
    with pytest.raises(PmIntakeError, match="--domain"):
        desk.service.resolve_domain("SW-GHOST-001")
    with pytest.raises(PmIntakeError, match="不合法"):
        desk.service.resolve_domain(PYTHON_PROJECT, "XXXX")
    with pytest.raises(PmIntakeError):
        desk.service.classify(PYTHON_PROJECT, kind=IntakeKind.BUG, change_action=None, domain="", impact_scope=("GLOBAL",))
    with pytest.raises(PmIntakeError):
        desk.service.classify(PYTHON_PROJECT, kind=IntakeKind.CHANGE, change_action=None, domain="", impact_scope=())
    default = desk.service.classify(PYTHON_PROJECT, kind=IntakeKind.DEBT, change_action=None, domain="", impact_scope=())
    assert default.impact_scope == ("MODULE",)


def test_sv13_plan_classification_follows_the_inbox_the_options_or_the_binding(desk: Desk) -> None:
    item = desk.confirm(desk.propose("按条目建计划", kind=IntakeKind.CHANGE))
    plan = desk.service.plan_classification
    none: dict[str, Any] = {"change_action": None, "domain": "", "impact_scope": ()}
    assert plan(PYTHON_PROJECT, request_id="R", kind=None, inbox_id=item.item_id, **none) == (item.classification, item.item_id)
    assert plan(PYTHON_PROJECT, request_id="R", kind=IntakeKind.CHANGE, inbox_id=item.item_id, **none)[1] == item.item_id
    for mismatch in (
        {"kind": IntakeKind.BUG, **none},
        {"kind": None, "change_action": ChangeAction.FREEZE, "domain": "", "impact_scope": ()},
        {"kind": None, "change_action": None, "domain": "PLC", "impact_scope": ()},
        {"kind": None, "change_action": None, "domain": "", "impact_scope": ("SYSTEM",)},
    ):
        with pytest.raises(PmIntakeError, match="不一致"):
            plan(PYTHON_PROJECT, request_id="R", inbox_id=item.item_id, **mismatch)
    with pytest.raises(PmIntakeError, match="同一项目"):
        plan(PLC_PROJECT, request_id="R", kind=None, inbox_id=item.item_id, **none)
    proposed = desk.propose("尚未确认")
    with pytest.raises(PmIntakeError, match="已确认"):
        plan(PYTHON_PROJECT, request_id="R", kind=None, inbox_id=proposed.item_id, **none)
    assert plan(PYTHON_PROJECT, request_id="R2", kind=None, inbox_id="", **none) == (None, "")
    direct, item_id = plan(
        PYTHON_PROJECT, request_id="R2", kind=IntakeKind.CHANGE, change_action=ChangeAction.REMOVE, domain="", impact_scope=("SYSTEM",), inbox_id=""
    )
    assert direct is not None
    assert (direct.change_action, direct.impact_scope, item_id) == (ChangeAction.REMOVE, ("SYSTEM",), "")
    request = desk.draft("R3")
    IntakeStore(desk.root).bind_planning_classification(request, direct)
    assert plan(PYTHON_PROJECT, request_id=request, kind=None, inbox_id="", **none) == (direct, "")
    IntakeStore(desk.root).bind_planning_classification(desk.draft("R4"), item.classification, item.item_id)
    assert plan(PYTHON_PROJECT, request_id="R4", kind=None, inbox_id=item.item_id, **none)[1] == item.item_id
    with pytest.raises(PmIntakeError, match="已确认"):
        plan(PYTHON_PROJECT, request_id="R5", kind=None, inbox_id=item.item_id, **none)


def test_sv14_the_summary_lists_confirmed_items_first_then_the_most_urgent(desk: Desk) -> None:
    urgent = desk.ticket(urgent_criterion=UrgentCriterion.WRONG_OUTPUT, disposition=Disposition.INTERRUPT_NOW)
    waiting = desk.ticket(disposition=Disposition.INBOX_WAIT)
    items = {
        "wait-1": desk.propose("等待一", ticket=waiting),
        "after-1": desk.propose("当前卡后一"),
        "urgent-1": desk.propose("紧急一", kind=IntakeKind.URGENT, ticket=urgent),
        "wait-2": desk.propose("等待二", ticket=waiting),
        "after-2": desk.propose("当前卡后二"),
        "urgent-2": desk.propose("紧急二", kind=IntakeKind.URGENT, ticket=urgent),
        "rejected": desk.propose("将被驳回"),
    }
    desk.service.reject(
        items["rejected"].item_id, ticket_hash=items["rejected"].ticket_hash, approver=APPROVER, approval_evidence_ref=CONFIRMATION
    )
    desk.confirm(items["wait-2"])
    summary = IntakeStore(desk.root).summary(PYTHON_PROJECT)
    assert (summary.awaiting_confirmation, summary.confirmed_waiting) == (5, 1)
    assert [brief.item_id for brief in summary.queue] == [
        items["wait-2"].item_id,
        items["urgent-1"].item_id,
        items["urgent-2"].item_id,
        items["after-1"].item_id,
        items["after-2"].item_id,
    ]
    assert [brief.status for brief in summary.queue][:2] == [IntakeStatus.CONFIRMED, IntakeStatus.PROPOSED]
    assert IntakeStore(desk.root).summary(PLC_PROJECT).is_empty


def test_sv15_recording_confirming_and_planning_never_touch_execution_state(tmp_path: Path) -> None:
    clock = Clock()
    clock.value = datetime.now(UTC)
    _, execution = _services(tmp_path, clock)
    _start(execution, lease_token="live-token")
    _checkpoint(execution, lease_token="live-token")
    (tmp_path / "SW-2026-008_auto-pm").mkdir()
    service = PmIntakeService(tmp_path)
    guarded = ("work_items", "run_items", "execution_leases", "checkpoints", "mission_items", "handoffs_v2")

    def snapshot() -> dict[str, list[tuple[Any, ...]]]:
        with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
            return {table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")] for table in guarded}

    def run_events() -> list[tuple[Any, ...]]:
        with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
            return [tuple(row) for row in conn.execute("SELECT * FROM events WHERE aggregate_id IN ('RUN-001', 'WORK-001') ORDER BY rowid")]

    before, before_events = snapshot(), run_events()
    assert before["run_items"] and before["execution_leases"] and before["checkpoints"]
    classification = service.classify("SW-2026-008", kind=IntakeKind.BUG, change_action=None, domain="SCPT", impact_scope=())
    ticket = TriageTicket(
        original_words="发现一个 bug", affects="当前卡之外", duplicate_check="查过", evidence=("file:README.md",),
        disposition=Disposition.AFTER_CURRENT, rationale="不阻塞", alternatives=("忽略",), cost_risk="低",
    )
    item, _ = service.propose(
        request_id="REQ-ASIDE", project_id="SW-2026-008", title="旁路发现的 bug", classification=classification, ticket=ticket, proposed_by="pm-test"
    )
    service.confirm(item.item_id, ticket_hash=item.ticket_hash, approver=APPROVER, approval_evidence_ref=CONFIRMATION)
    service.list_items("SW-2026-008")
    assert snapshot() == before and run_events() == before_events


# ---- TD-SW008-072：取证里的 chg / commit / ledger 入箱时只读核验确实存在 ----


class _KnownChanges:
    """Stands in for the change service: only the listed numbers exist, and the first lookup may be project-scoped."""

    def __init__(self, known: set[str], *, only_unscoped: bool = False) -> None:
        self.known = known
        self.only_unscoped = only_unscoped
        self.calls: list[tuple[str, str | None]] = []

    def next_change_number(self, project_id: str, domain: str) -> str:
        return "CHG-SCPT-2026-900"

    def get_change_request(self, change_number: str, project_id: str | None = None) -> object | None:
        self.calls.append((change_number, project_id))
        if self.only_unscoped and project_id is not None:
            return None
        return object() if change_number in self.known else None


def _head(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    ).stdout.strip()


def test_td072_a_cited_change_request_must_exist(desk: Desk) -> None:
    before = (desk.events(), desk.tables())
    with pytest.raises(PmIntakeError, match="取证变更单不存在"):
        desk.propose(ticket=desk.ticket(evidence=("file:README.md", "chg:CHG-SCPT-2026-378")))
    assert (desk.events(), desk.tables()) == before


def test_td072_a_known_change_request_is_accepted_and_looked_up_project_first_then_anywhere(tmp_path: Path) -> None:
    desk = _build_desk(tmp_path)
    changes = _KnownChanges({"CHG-SCPT-2026-378"})
    desk.service = PmIntakeService(tmp_path, change_service=changes)  # type: ignore[arg-type]
    assert desk.propose(ticket=desk.ticket(evidence=("chg:CHG-SCPT-2026-378",)))
    assert changes.calls == [("CHG-SCPT-2026-378", PYTHON_PROJECT)]
    elsewhere = _KnownChanges({"CHG-SCPT-2026-379"}, only_unscoped=True)
    desk.service = PmIntakeService(tmp_path, change_service=elsewhere)  # type: ignore[arg-type]
    assert desk.propose(ticket=desk.ticket(evidence=("chg:CHG-SCPT-2026-379",)), title="别的项目的变更单")
    assert elsewhere.calls == [("CHG-SCPT-2026-379", PYTHON_PROJECT), ("CHG-SCPT-2026-379", None)]


def test_td072_a_cited_commit_must_be_a_commit_of_this_repository(desk: Desk) -> None:
    head = _head(desk.root)
    assert desk.propose(ticket=desk.ticket(evidence=(f"commit:{head}",)))
    assert desk.propose(ticket=desk.ticket(evidence=(f"commit:{head[:7]}",)), title="短号也行")
    with pytest.raises(PmIntakeError, match="取证提交不存在"):
        desk.propose(ticket=desk.ticket(evidence=("commit:deadbeef",)), title="不存在的提交")
    blob = subprocess.run(
        ["git", "-C", str(desk.root), "rev-parse", "HEAD:README.md"], check=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    ).stdout.strip()
    with pytest.raises(PmIntakeError, match="取证提交不存在"):
        desk.propose(ticket=desk.ticket(evidence=(f"commit:{blob}",)), title="不是提交的对象")


def test_td072_a_cited_ledger_row_must_exist_in_the_project_ledger_folder(desk: Desk) -> None:
    folder = desk.root / PYTHON_PROJECT / "04_监控" / "02_整改项"
    (folder / "archive").mkdir(parents=True)
    (folder / "活动技术债台账.md").write_text(
        "| ID | 说明 |\n|---|---|\n| TD-SW901-001 | 活动条目 |\n正文里提到 TD-SW901-099 但不是表格行\n", encoding="utf-8"
    )
    (folder / "archive" / "已偿还.md").write_text("| TD-SW901-002 | 已偿还条目 |\n", encoding="utf-8")
    for ledger_id in ("TD-SW901-001", "TD-SW901-002"):
        assert desk.propose(ticket=desk.ticket(evidence=(f"ledger:{ledger_id}",)), title=f"引用 {ledger_id}")
    for missing in ("TD-SW901-003", "TD-SW901-099"):
        with pytest.raises(PmIntakeError, match="取证台账行不存在"):
            desk.propose(ticket=desk.ticket(evidence=(f"ledger:{missing}",)), title=f"引用 {missing}")


def test_td072_a_ledger_row_is_found_when_the_project_keeps_its_ledger_under_11_monitoring(desk: Desk) -> None:
    folder = desk.root / PYTHON_PROJECT / "11_监控" / "02_整改项"
    folder.mkdir(parents=True)
    (folder / "活动技术债台账.md").write_text("| TD-SW901-011 | 旧布局项目的债 |\n", encoding="utf-8")

    assert desk.propose(ticket=desk.ticket(evidence=("ledger:TD-SW901-011",)))


def test_td072_a_project_without_a_ledger_folder_refuses_ledger_evidence(desk: Desk) -> None:
    with pytest.raises(PmIntakeError, match="取证台账行不存在"):
        desk.propose(ticket=desk.ticket(evidence=("ledger:TD-SW901-001",)))


def test_td072_cmd_evidence_is_still_only_a_claim(desk: Desk) -> None:
    assert desk.propose(ticket=desk.ticket(evidence=("cmd:python -m this_does_not_exist",)))


def test_td072_a_ledger_row_is_found_in_the_project_its_id_names_even_when_another_project_cites_it(desk: Desk) -> None:
    folder = desk.root / PYTHON_PROJECT / "04_监控" / "02_整改项"
    folder.mkdir(parents=True)
    (folder / "活动技术债台账.md").write_text("| TD-SW901-007 | 驾驶舱债 |\n", encoding="utf-8")
    # SW901 = SW-2026-901；PLC 项目引用它的债
    assert desk.propose(project=PLC_PROJECT, kind=IntakeKind.BUG, ticket=desk.ticket(evidence=("ledger:TD-SW901-007",)))
    with pytest.raises(PmIntakeError, match="取证台账行不存在"):
        desk.propose(project=PLC_PROJECT, ticket=desk.ticket(evidence=("ledger:TD-SW901-008",)), title="没有这行")


# ---------------------------------------------------------------- D-357: raw notes


def _note(desk: Desk, title: str = "看板字太小", *, words: str = "字太小了，看不清", request_id: str = "", by: str = "trae") -> IntakeNote:
    desk.counter += 1
    note, _ = desk.service.note(
        request_id=request_id or f"REQ-NOTE-{desk.counter:03d}", project_id=PYTHON_PROJECT, title=title,
        original_words=words, kind_hint=IntakeKind.ITERATION, recorded_by=by,
    )
    return note


def _turn(desk: Desk, note: IntakeNote, *, request_id: str = "REQ-TURN-1", title: str = "", words: str = "", by: str = "claude") -> tuple[IntakeItem, bool]:
    classification = desk.service.classify(PYTHON_PROJECT, kind=IntakeKind.BUG, change_action=None, domain="", impact_scope=())
    return desk.service.propose(
        request_id=request_id, project_id=PYTHON_PROJECT, title=title or note.title, classification=classification,
        ticket=desk.ticket(original_words=words or note.original_words), proposed_by="pm-test",
        from_note=note.note_id, triaged_by=by,
    )


def test_d357_notes_are_numbered_per_project_listed_in_order_and_leave_an_event(desk: Desk) -> None:
    first = _note(desk, "第一句")
    second = _note(desk, "第二句", by="no-agent-marker")
    assert (first.note_id, second.note_id) == ("NOTE-SW-2026-901-0001", "NOTE-SW-2026-901-0002")
    assert first.status is NoteStatus.RAW and (first.item_id, first.triaged_by, first.triaged_at) == ("", "", "")
    assert desk.service.list_notes(PYTHON_PROJECT) == (first, second)
    assert desk.service.list_notes(PLC_PROJECT) == ()
    row = desk.sql("SELECT aggregate_type, aggregate_id FROM events WHERE event_type='INTAKE_NOTE_RECORDED' ORDER BY rowid")
    assert row == [("intake_note", first.note_id), ("intake_note", second.note_id)]
    assert desk.sql("SELECT seq, status, item_id, title_key FROM intake_notes ORDER BY seq") == [(1, "RAW", None, "第一句"), (2, "RAW", None, "第二句")]
    summary = IntakeStore(desk.root).note_summary(PYTHON_PROJECT)
    assert summary == IntakeNoteSummary(
        waiting=2, oldest_note_id=first.note_id, oldest_recorded_by="trae", oldest_created_at=first.created_at
    )
    assert IntakeStore(desk.root).note_summary(PLC_PROJECT).is_empty
    assert desk.service.list_items(PYTHON_PROJECT) == ()  # a note is not an inbox item
    assert IntakeStore(desk.root).summary(PYTHON_PROJECT).is_empty


def test_d357_the_note_contract_keeps_raw_and_triaged_apart() -> None:
    base: dict[str, Any] = {
        "note_id": "NOTE-SW-2026-901-0001", "request_id": "R", "project_id": PYTHON_PROJECT, "title": "t",
        "original_words": "  第一行\n第二行  ", "recorded_by": "claude", "created_at": "2026-11-13T00:00:00+00:00",
    }
    note = IntakeNote(**base)
    assert note.original_words == "第一行\n第二行" and note.kind_hint is IntakeKind.ITERATION
    triage = {"item_id": "INBOX-SW-2026-901-0001", "triaged_by": "claude", "triaged_at": "2026-11-13T01:00:00+00:00"}
    assert IntakeNote(**base, status=NoteStatus.TRIAGED, **triage).item_id == triage["item_id"]
    for field in triage:  # a raw note carries none of the three; a triaged one needs all three
        with pytest.raises(ValueError, match="raw note"):
            IntakeNote(**base, **{field: triage[field]})
        with pytest.raises(ValueError, match="triaged note"):
            IntakeNote(**base, status=NoteStatus.TRIAGED, **{key: value for key, value in triage.items() if key != field})
    with pytest.raises(ValueError, match="same project"):
        IntakeNote(**base, status=NoteStatus.TRIAGED, **{**triage, "item_id": "INBOX-DJ-2026-902-0001"})
    with pytest.raises(ValueError, match="note_id"):
        IntakeNote(**{**base, "note_id": "NOTE-DJ-2026-902-0001"})
    with pytest.raises(ValueError):
        IntakeNote.model_validate({**base, "extra_field": 1})
    for blank in ("title", "original_words", "recorded_by"):
        with pytest.raises(ValueError):
            IntakeNote(**{**base, blank: " "})
    assert IntakeNoteSummary.model_validate({"waiting": 1, "a_field_from_a_newer_release": 1}).waiting == 1
    assert note_actor_label("no-agent-marker") == "本机终端（没带 AI 标记）"
    assert note_actor_label("unknown-agent") == "带了标记但不在名册里的 AI"
    assert note_actor_label("trae") == "trae"


def test_d357_a_replay_returns_the_same_note_and_changed_content_is_refused(desk: Desk) -> None:
    first = _note(desk, request_id="REQ-SAME")
    events = desk.events()
    again, created = desk.service.note(
        request_id="REQ-SAME", project_id=PYTHON_PROJECT, title=first.title, original_words=first.original_words,
        kind_hint=IntakeKind.ITERATION, recorded_by="cursor",
    )
    assert (again, created) == (first, False) and desk.events() == events  # the first recorder stays on record
    for change in ({"title": "另一个标题"}, {"original_words": "另一句"}, {"kind_hint": IntakeKind.BUG}, {"project_id": PLC_PROJECT}):
        values: dict[str, Any] = {
            "request_id": "REQ-SAME", "project_id": PYTHON_PROJECT, "title": first.title,
            "original_words": first.original_words, "kind_hint": IntakeKind.ITERATION, "recorded_by": "trae", **change,
        }
        with pytest.raises(PmIntakeError, match="request_id 已绑定不同内容"):
            desk.service.note(**values)
    assert desk.events() == events and len(desk.sql("SELECT 1 FROM intake_notes")) == 1


def test_d357_duplicate_titles_are_checked_against_raw_notes_and_open_items_only(desk: Desk) -> None:
    note = _note(desk, "看板 字太小")
    with pytest.raises(PmIntakeError, match=f"已有同名待整理记录: {note.note_id}"):
        _note(desk, "看板   字太小")
    item = desk.propose("导出没反应")
    with pytest.raises(PmIntakeError, match=f"已有同名未处理条目: {item.item_id}"):
        _note(desk, "导出没反应")
    with pytest.raises(PmIntakeError, match=f"--from-note {note.note_id}"):
        desk.propose("看板 字太小")
    desk.service.reject(item.item_id, ticket_hash=item.ticket_hash, approver=APPROVER, approval_evidence_ref=CONFIRMATION)
    assert _note(desk, "导出没反应").note_id.endswith("-0002")  # a decided item no longer holds the title
    turned, _ = _turn(desk, note)
    assert desk.service.list_notes(PYTHON_PROJECT, (NoteStatus.TRIAGED,))[0].item_id == turned.item_id
    with pytest.raises(PmIntakeError, match=f"已有同名未处理条目: {turned.item_id}"):
        _note(desk, "看板 字太小")  # now the open item holds the title, not the triaged note


def test_d357_turning_a_note_is_one_transaction_and_happens_once(desk: Desk, monkeypatch: pytest.MonkeyPatch) -> None:
    note = _note(desk)
    events = desk.events()

    def broken(*_args: Any, **_kwargs: Any) -> None:
        raise ContinuityStoreError("写记录失败（测试打桩）")

    with monkeypatch.context() as patch:
        patch.setattr(IntakeStore, "_store_note", staticmethod(broken))
        with pytest.raises(PmIntakeError, match="测试打桩"):
            _turn(desk, note)
    assert desk.events() == events and desk.service.list_items(PYTHON_PROJECT) == ()
    assert desk.service.list_notes(PYTHON_PROJECT) == (note,)

    for refused, pattern in (
        ({"words": note.original_words + "！"}, "不逐字相同"),
        ({"words": note.original_words[:-1]}, "不逐字相同"),
    ):
        with pytest.raises(PmIntakeError, match=pattern):
            _turn(desk, note, **refused)
    with pytest.raises(PmIntakeError, match="待整理记录不存在: NOTE-SW-2026-901-0009"):
        _turn(desk, note.model_copy(update={"note_id": "NOTE-SW-2026-901-0009"}))
    assert desk.events() == events and desk.service.list_items(PYTHON_PROJECT) == ()

    item, created = _turn(desk, note, title="看板首页字号偏小")
    assert created and item.status is IntakeStatus.PROPOSED and item.proposed_by == "pm-test"
    triaged = desk.service.list_notes(PYTHON_PROJECT, (NoteStatus.TRIAGED,))[0]
    assert (triaged.status, triaged.item_id, triaged.triaged_by, triaged.triaged_at) == (NoteStatus.TRIAGED, item.item_id, "claude", item.created_at)
    assert (triaged.title, triaged.original_words, triaged.recorded_by, triaged.created_at) == (note.title, note.original_words, "trae", note.created_at)
    assert desk.service.list_notes(PYTHON_PROJECT) == ()
    assert [row[0] for row in desk.sql("SELECT event_type FROM events ORDER BY rowid")][-2:] == ["INTAKE_ITEM_RECORDED", "INTAKE_NOTE_TRIAGED"]
    assert desk.sql("SELECT status, item_id FROM intake_notes") == [("TRIAGED", item.item_id)]

    events = desk.events()
    assert _turn(desk, note, title="看板首页字号偏小") == (item, False) and desk.events() == events
    with pytest.raises(PmIntakeError, match=f"已经转成 {item.item_id}"):
        _turn(desk, note, request_id="REQ-TURN-2", title="再转一次")
    other = _note(desk, "另一件事", words="另一句")
    with pytest.raises(PmIntakeError, match="不是由待整理记录"):
        _turn(desk, other, title="看板首页字号偏小", words=note.original_words)  # REQ-TURN-1 belongs to the first note
    with pytest.raises(PmIntakeError, match="待整理记录不存在"):
        _turn(desk, other.model_copy(update={"note_id": "NOTE-SW-2026-901-0009"}), title="看板首页字号偏小", words=note.original_words)
    assert desk.events() == events + 1 and len(desk.service.list_items(PYTHON_PROJECT)) == 1


def test_d357_a_note_of_another_project_cannot_be_turned(desk: Desk) -> None:
    note = _note(desk)
    classification = desk.service.classify(PLC_PROJECT, kind=IntakeKind.BUG, change_action=None, domain="", impact_scope=())
    with pytest.raises(PmIntakeError, match=f"属于项目 {PYTHON_PROJECT}"):
        desk.service.propose(
            request_id="REQ-X", project_id=PLC_PROJECT, title="t", classification=classification,
            ticket=desk.ticket(original_words=note.original_words), proposed_by="pm-test", from_note=note.note_id, triaged_by="claude",
        )
    assert desk.service.list_items(PLC_PROJECT) == () and desk.service.list_notes(PYTHON_PROJECT) == (note,)


def test_d357_reading_notes_creates_neither_the_table_nor_the_ledger(desk: Desk, tmp_path_factory: pytest.TempPathFactory) -> None:
    import hashlib

    _note(desk)
    db = desk.root / ".auto-pm" / "continuity.db"
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("DROP TABLE intake_notes")  # what a ledger from before D-357 looks like
    digest = hashlib.sha256(db.read_bytes()).hexdigest()
    store = IntakeStore(desk.root)
    assert store.list_notes(PYTHON_PROJECT) == () and store.note_summary(PYTHON_PROJECT).is_empty
    assert desk.service.list_notes(PYTHON_PROJECT, (NoteStatus.RAW, NoteStatus.TRIAGED)) == ()
    assert "intake_notes" not in desk.tables() and hashlib.sha256(db.read_bytes()).hexdigest() == digest
    assert _note(desk, "老账本上第一次写").note_id.endswith("-0001") and "intake_notes" in desk.tables()

    bare = tmp_path_factory.mktemp("no-ledger")
    _repository(bare)
    assert IntakeStore(bare).list_notes(PYTHON_PROJECT) == () and IntakeStore(bare).note_summary(PYTHON_PROJECT).is_empty
    assert not (bare / ".auto-pm").exists()
    with pytest.raises(ContinuityStoreError, match="尚未初始化"):
        IntakeStore(bare).add_note(
            request_id="R", project_id=PYTHON_PROJECT, title="t", original_words="w", kind_hint=IntakeKind.ITERATION, recorded_by="trae"
        )
    assert not (bare / ".auto-pm" / "continuity.db").exists()


def test_d357_a_note_row_that_cannot_be_read_is_an_error_not_an_empty_list(desk: Desk) -> None:
    _note(desk)
    with closing(sqlite3.connect(desk.root / ".auto-pm" / "continuity.db")) as conn, conn:
        conn.execute("UPDATE intake_notes SET note_json='{}'")
    with pytest.raises(PmIntakeError, match="待整理记录无法读取"):
        desk.service.list_notes(PYTHON_PROJECT)
