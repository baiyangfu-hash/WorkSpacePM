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
    IntakeStatus,
    TriageTicket,
    UrgentCriterion,
)
from auto_pm.contracts.pm_facade import PlanningDraft, PmIntent
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.intake_store import IntakeStore
from tests.core.test_continuity_execution_service import Clock, _checkpoint, _services, _start

if TYPE_CHECKING:
    from auto_pm.application.core.pm_intake_service import PmIntakeError, PmIntakeService
else:
    from auto_pm.core.pm_intake_service import PmIntakeError, PmIntakeService

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
        assert desk.tables().isdisjoint(INTAKE_TABLES)
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
    assert desk.propose(ticket=desk.ticket(evidence=("file:README.md", "cmd:git status --short", "chg:CHG-SCPT-2026-378")))


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


def test_sv09_the_inbox_tables_appear_with_the_first_write_and_reads_never_create_them(desk: Desk) -> None:
    assert desk.tables().isdisjoint(INTAKE_TABLES)
    store = IntakeStore(desk.root)
    assert store.list_items(PYTHON_PROJECT) == () and store.summary(PYTHON_PROJECT).is_empty
    assert store.get_planning_classification("REQ-NONE") is None
    with pytest.raises(ContinuityStoreError, match="不存在"):
        store.get_item("INBOX-SW-2026-901-0001")
    assert desk.tables().isdisjoint(INTAKE_TABLES)
    desk.propose()
    assert INTAKE_TABLES <= desk.tables()
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
