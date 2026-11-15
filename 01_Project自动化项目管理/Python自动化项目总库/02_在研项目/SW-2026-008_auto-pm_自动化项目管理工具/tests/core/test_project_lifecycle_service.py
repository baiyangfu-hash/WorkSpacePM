"""CHG-SCPT-2026-652：归档前的五项检查、预演不写、只改登记表一栏、重新激活，以及从登记表补出已删除的项目。

账本、收件箱、Git、登记表都用真的：临时 Git 工作区里建真的 Continuity Store，卡用 Store 自己的入口写进去。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core import project_lifecycle_service as lifecycle
from auto_pm.application.core.project_delete_guard import mark_registry_deleted, recycle_project
from auto_pm.application.core.workspace_registry_service import (
    WorkspaceRegistryError,
    WorkspaceRegistryService,
)
from auto_pm.contracts import workspace_context as wc
from auto_pm.contracts.intake import (
    Disposition,
    IntakeClassification,
    IntakeItem,
    IntakeKind,
    IntakeNote,
    IntakeStatus,
    TriageTicket,
)
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope, Mission, MissionState
from auto_pm.domain.models.change import ChangeSummary
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.infrastructure.intake_store import IntakeStore
from tests.core.test_workspace_registry_service import _anchor, _workspace
from tests.git_support import run_git

PID = "DJ-2026-005"
OTHER = "DJ-2026-006"
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
STAMP = NOW.isoformat()
DECISION = "DEC-20261101-AAAA0001"
ALL_CHECKS = (
    lifecycle.CHECK_OPEN_WORK,
    lifecycle.CHECK_CLOSURE,
    lifecycle.CHECK_ACCEPTED,
    lifecycle.CHECK_UNCOMMITTED,
    lifecycle.CHECK_INBOX,
)


def commit_all(root: Path) -> None:
    run_git(root, "add", "-A")
    run_git(root, "commit", "-q", "--allow-empty", "-m", "snapshot", config=["user.email=t@example.invalid", "user.name=t"])


class Site:
    """一个真的 Git 工作区：登记表里有控制项目和 DJ-2026-005（已提交）；``.auto-pm`` 不进 Git，和真工作区一样。"""

    def __init__(self, root: Path, *, status: str = "") -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.registry = _workspace(root)
        if status:
            self.set_registry_status(PID, status)
        self.project = root / "0100_PLC自动化" / PID
        (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8")
        run_git(root, "init", "-q", "-b", "main")
        commit_all(root)
        self._store: ContinuityStore | None = None

    def set_registry_status(self, project_id: str, status: str) -> None:
        """照真登记表的排版改一条的状态（末尾加一栏），别的字节不动。"""
        text = self.registry.read_text(encoding="utf-8")
        head, found, tail = text.partition(f'"project_id": "{project_id}"')
        assert found
        body, brace, rest = tail.partition("\n    }")
        self.registry.write_text(
            head + found + body + f',\n      "status": "{status}"' + brace + rest, encoding="utf-8", newline="\n"
        )

    @property
    def store(self) -> ContinuityStore:
        if self._store is None:
            self._store = ContinuityStore(self.root)
            self._store.initialize(STAMP, "test")
        return self._store

    @property
    def db(self) -> Path:
        return self.root / ".auto-pm" / "continuity.db"

    def work(self, work_id: str, state: str, *, project: str = PID) -> None:
        self.store.create_work(
            {
                "work_id": work_id,
                "subject_project_id": project,
                "kind": "WBS",
                "title": work_id,
                "state": state,
                "owner": "t",
                "read_only": 0,
                "authorization_ref": DECISION,
                "scope_json": json.dumps(["a.py"]),
                "scope_hash": "a" * 64,
                "source_fingerprint": f"sha256:{'b' * 64}",
                "version": 1,
                "created_at": STAMP,
                "updated_at": STAMP,
            },
            f"key-{work_id}",
            STAMP,
        )

    def mission(self, mission_id: str, work_id: str, state: MissionState, *, project: str = PID) -> None:
        authority = AuthorityEnvelope(
            envelope_id=f"AUTH-{mission_id}",
            subject_project_id=project,
            change_id="CHG-PLC-2026-001",
            decision_id=DECISION,
            scope_paths=("a.py",),
            valid_from=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(days=1),
            audit=AuthorityAudit(
                created_by="pm",
                created_at=NOW,
                approved_by="user",
                approved_at=NOW,
                source_fingerprint=f"sha256:{'c' * 64}",
            ),
        )
        mission = Mission(
            mission_id=mission_id,
            subject_project_id=project,
            title=mission_id,
            objective="objective",
            state=state,
            root_work_id=work_id,
            acceptance_criteria=("done",),
            authority=authority,
            version=1,
            created_by="pm",
            created_at=NOW,
            updated_at=NOW,
        )
        values: dict[str, Any] = mission.model_dump(mode="json")
        values.pop("schema_version")
        values["acceptance_criteria_json"] = json.dumps(values.pop("acceptance_criteria"))
        values["authority_json"] = json.dumps(values.pop("authority"), sort_keys=True)
        self.store.create_mission(values, f"key-{mission_id}", STAMP)

    def closure(self, mission_id: str, work_id: str, state: str) -> None:
        """收口记录这一行：正常由收口流程写；这里只要它的状态，所以直接写这一行。"""
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute(
                "INSERT INTO closure_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"CLOSURE-{mission_id}", mission_id, work_id, "RUN-X", "CP-X", "CHG-PLC-2026-001", DECISION, state, "h", 1, STAMP, STAMP),
            )

    def closed_card(self, number: int = 1, *, closure: str | None = "COMPLETED", project: str = PID) -> str:
        """一张关好的卡：Work 和 Mission 都是 CLOSED；``closure`` 是收口记录的状态，None 表示没有收口记录。"""
        mission_id, work_id = f"MISSION-{number}", f"WORK-{number}"
        self.work(work_id, "CLOSED", project=project)
        self.mission(mission_id, work_id, MissionState.CLOSED, project=project)
        if closure is not None:
            self.closure(mission_id, work_id, closure)
        return mission_id

    def inbox_item(self, title: str, *, project: str = PID) -> IntakeItem:
        assert self.store.db_path == self.db  # the inbox lives in the same ledger file; this also creates it
        item, _ = IntakeStore(self.root).add_item(
            request_id=f"REQ-{hashlib.sha256(title.encode()).hexdigest()[:8]}",
            project_id=project,
            title=title,
            classification=IntakeClassification(kind=IntakeKind.BUG, domain="PLC"),
            ticket=TriageTicket(
                original_words=title,
                affects=project,
                duplicate_check="查过，没有同类条目",
                evidence=("file:README.md",),
                disposition=Disposition.AFTER_CURRENT,
                rationale="不急",
                alternatives=("下个迭代",),
                cost_risk="半天；低",
            ),
            proposed_by="pm-test",
        )
        return item

    def note(self, title: str, *, project: str = PID) -> IntakeNote:
        """一条待整理记录（D-357）：只有一句话和原话。"""
        assert self.store.db_path == self.db
        note, _ = IntakeStore(self.root).add_note(
            request_id=f"REQ-NOTE-{hashlib.sha256(title.encode()).hexdigest()[:8]}",
            project_id=project,
            title=title,
            original_words=title,
            kind_hint=IntakeKind.ITERATION,
            recorded_by="no-agent-marker",
        )
        return note

    def turn(self, note: IntakeNote) -> IntakeItem:
        """把待整理记录转成正式条目（PROPOSED）。"""
        item, _ = IntakeStore(self.root).add_item(
            request_id=f"REQ-TURN-{note.note_id}",
            project_id=note.project_id,
            title=note.title,
            classification=IntakeClassification(kind=IntakeKind.BUG, domain="PLC"),
            ticket=TriageTicket(
                original_words=note.original_words,
                affects=note.project_id,
                duplicate_check="查过，没有同类条目",
                evidence=("file:README.md",),
                disposition=Disposition.REJECT,
                rationale="记错了，建议不做",
                alternatives=("留着",),
                cost_risk="无",
            ),
            proposed_by="pm-test",
            from_note=note.note_id,
            triaged_by="claude",
        )
        return item

    def decide(self, item: IntakeItem, status: IntakeStatus) -> None:
        IntakeStore(self.root).decide_item(
            item.item_id,
            status=status,
            ticket_hash=item.ticket_hash,
            decided_by="user",
            decision_ref="user-confirmation:cmsg_inbox_decision",
        )

    def plan(self) -> lifecycle.LifecyclePlan:
        return lifecycle.plan_archive(self.root, PID, self.project, control_root=self.root)

    def failed(self) -> tuple[str, ...]:
        return tuple(check.name for check in self.plan().checks if not check.passed)

    def snapshot(self) -> dict[str, str]:
        """登记表、账本主文件和项目目录的指纹，用来证明“什么都没写”。"""
        files = [self.registry, *sorted(p for p in self.project.rglob("*") if p.is_file())]
        if self.db.is_file():
            files.append(self.db)
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

    def entries(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = json.loads(self.registry.read_text(encoding="utf-8"))["projects"]
        return projects


@pytest.fixture
def site(tmp_path: Path) -> Site:
    return Site(tmp_path / "ws")


# ── 五项检查 ──────────────────────────────────────────────


def test_a_project_with_no_ledger_and_a_clean_tree_passes_all_five(site: Site) -> None:
    plan = site.plan()
    assert tuple(check.name for check in plan.checks) == ALL_CHECKS
    assert plan.blockers == () and (plan.status_before, plan.status_after) == ("", "archived")
    assert "状态码" not in plan.checks[0].advice  # 没有开着的卡就没有状态码要注
    assert not site.db.exists()  # 预演不替人建账本


def test_cards_that_were_closed_properly_pass_and_another_projects_cards_do_not_count(site: Site) -> None:
    site.closed_card(1)
    site.work("WORK-9", "IN_PROGRESS", project=OTHER)  # 别的项目开着的卡
    site.closed_card(8, closure=None, project=OTHER)  # 别的项目没收口的卡
    item = site.inbox_item("别的项目的条目", project=OTHER)
    assert item.status is IntakeStatus.PROPOSED
    assert site.plan().blockers == ()


def test_check_1_open_work_refuses(site: Site) -> None:
    site.work("WORK-1", "IN_PROGRESS")
    assert site.failed() == (lifecycle.CHECK_OPEN_WORK,)
    assert any("开着的 Work WORK-1" in blocker for blocker in site.plan().blockers)
    advice = site.plan().checks[0].advice  # 归档这一层补的“怎么办”和中文状态名；project delete 共用的原因文字不改
    assert advice.startswith("怎么办：") and "pm missions --pid" in advice
    assert advice.endswith("状态码：IN_PROGRESS 在干")


@pytest.mark.parametrize("closure", ["PREPARED", None])
def test_check_2_a_closed_card_without_a_completed_closure_refuses(site: Site, closure: str | None) -> None:
    site.closed_card(1)  # 这张收好了，不该被点名
    mission_id = site.closed_card(2, closure=closure)
    plan = site.plan()
    assert site.failed() == (lifecycle.CHECK_CLOSURE,)
    (blocker,) = plan.blockers
    assert mission_id in blocker and "MISSION-1" not in blocker
    # CHG-SCPT-2026-656（D-359）：原来写“先用 D 单的办法收掉”，那个办法并不存在；整句逐字锁住。
    assert blocker == (
        f"{lifecycle.CHECK_CLOSURE}：Mission {mission_id} 已关（CLOSED），但收口记录不是 COMPLETED"
        "（停在 PREPARED，或者查不到收口记录）；"
        "这类卡现在还没有命令能把收口补走完（缺陷 D-340，待修），请把卡号交给主执行，这个项目先不归档"
    )


def test_check_3_one_accepted_mission_that_was_never_closed_refuses(site: Site) -> None:
    """验收第 3 条点名的特例：只有一张 ACCEPTED 没收口的 Mission，开着的卡那一项查不到它。"""
    site.work("WORK-1", "CLOSED")
    site.mission("MISSION-1", "WORK-1", MissionState.ACCEPTED)
    assert site.failed() == (lifecycle.CHECK_ACCEPTED,)
    (blocker,) = site.plan().blockers
    assert "Mission MISSION-1 已验收（ACCEPTED）还没收口" in blocker
    assert "先在驾驶舱点确认验收收口，或用 pm close" in blocker


def test_check_3_an_accepted_work_refuses_too(site: Site) -> None:
    site.closed_card(1)
    site.work("WORK-2", "ACCEPTED")
    assert site.failed() == (lifecycle.CHECK_ACCEPTED,)
    (blocker,) = site.plan().blockers
    assert "Work WORK-2 已验收（ACCEPTED）还没收口" in blocker


@pytest.mark.parametrize("tracked", [False, True])
def test_check_4_an_uncommitted_change_refuses(site: Site, tracked: bool) -> None:
    target = site.project / (".copier-answers.yml" if tracked else "new.txt")
    target.write_text("changed\n", encoding="utf-8")
    assert site.failed() == (lifecycle.CHECK_UNCOMMITTED,)
    assert any("没提交的改动" in blocker for blocker in site.plan().blockers)


def test_check_4_shows_a_chinese_file_name_as_written_not_as_escape_codes(site: Site) -> None:
    """CHG-SCPT-2026-656（D-360）：Git 默认把中文路径写成八进制转义码，归档第 4 项要显示原字。"""
    (site.project / "工位一_说明.txt").write_text("没提交\n", encoding="utf-8")
    (site.project / "plain.txt").write_text("untracked\n", encoding="utf-8")
    assert site.failed() == (lifecycle.CHECK_UNCOMMITTED,)
    (blocker,) = site.plan().blockers
    folder = site.project.relative_to(site.root).as_posix()  # 项目本身就在中文目录下
    assert not folder.isascii()
    assert blocker == (
        f"{lifecycle.CHECK_UNCOMMITTED}：项目目录里有没提交的改动："
        f"?? {folder}/plain.txt；?? {folder}/工位一_说明.txt"
    )
    assert "\\" not in blocker


def test_check_5_one_proposed_inbox_item_refuses_and_is_listed_by_id_and_title(site: Site) -> None:
    """验收第 3 条点名的特例：只有一条 PROPOSED 的收件箱条目。"""
    item = site.inbox_item("登录页偶发白屏")
    assert item.status is IntakeStatus.PROPOSED
    assert site.failed() == (lifecycle.CHECK_INBOX,)
    (blocker,) = site.plan().blockers
    assert item.item_id in blocker and "登录页偶发白屏" in blocker and "PROPOSED 待确认" in blocker
    advice = site.plan().checks[-1].advice
    assert advice.startswith("怎么办：") and "pm inbox confirm" in advice and "pm inbox reject" in advice


def test_check_5_a_confirmed_item_still_blocks_and_a_rejected_one_does_not(site: Site) -> None:
    confirmed = site.inbox_item("已确认还没排的条目")
    rejected = site.inbox_item("已拒绝的条目")
    site.decide(confirmed, IntakeStatus.CONFIRMED)
    site.decide(rejected, IntakeStatus.REJECTED)
    (blocker,) = site.plan().blockers
    assert confirmed.item_id in blocker and "CONFIRMED 已确认，还没排进计划" in blocker
    assert rejected.item_id not in blocker


def test_check_5_a_raw_note_refuses_and_is_listed_by_id_and_title(site: Site) -> None:
    """D-357：待整理记录也算收件箱有待处理；别的项目的记录不算。"""
    site.note("别的项目的一句话", project=OTHER)
    assert site.failed() == ()
    note = site.note("看板字太小")
    assert site.failed() == (lifecycle.CHECK_INBOX,)
    (blocker,) = site.plan().blockers
    assert blocker == f"{lifecycle.CHECK_INBOX}：待整理记录 {note.note_id}（还没整理成正式条目）：看板字太小"
    advice = site.plan().checks[-1].advice
    assert "待整理记录请 AI 先整理成正式条目（pm inbox add --from-note <NOTE-ID>），再由用户确认或拒绝" in advice
    assert "pm inbox confirm" in advice and "pm inbox reject" in advice and advice.startswith("怎么办：")


def test_check_5_a_note_stops_blocking_only_after_it_was_turned_and_the_item_was_decided(site: Site) -> None:
    """记错的一句话要走完一圈：转成正式条目（这时挡的是条目），用户拒绝后才放行；已转正的记录本身不挡。"""
    note = site.note("记错的一句话")
    item = site.turn(note)
    (blocker,) = site.plan().blockers
    assert item.item_id in blocker and "PROPOSED 待确认" in blocker and note.note_id not in blocker
    site.decide(item, IntakeStatus.REJECTED)
    assert site.failed() == ()


def test_check_5_lists_open_items_first_then_raw_notes(site: Site) -> None:
    item = site.inbox_item("一条正式条目")
    note = site.note("一句还没整理的话")
    first, second = site.plan().blockers
    assert item.item_id in first and first.startswith(f"{lifecycle.CHECK_INBOX}：收件箱条目 ")
    assert note.note_id in second and second.startswith(f"{lifecycle.CHECK_INBOX}：待整理记录 ")


def test_notes_that_cannot_be_read_refuse_and_the_readable_items_are_still_listed(site: Site, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.pm_intake_service import PmIntakeError, PmIntakeService

    item = site.inbox_item("一条正式条目")

    def broken(self: PmIntakeService, project_id: str, *args: object) -> tuple[IntakeNote, ...]:
        raise PmIntakeError("待整理记录无法读取")

    monkeypatch.setattr(PmIntakeService, "list_notes", broken)
    assert site.failed() == (lifecycle.CHECK_INBOX,)
    first, second = site.plan().blockers
    assert item.item_id in first
    assert second == f"{lifecycle.CHECK_INBOX}：读不出待整理记录，无法确认有没有还没整理的：待整理记录无法读取"


def test_a_ledger_without_the_notes_table_passes_check_5_and_is_not_changed(site: Site) -> None:
    """老账本没有 intake_notes 表：归档检查照常过，不建表，账本字节不变。"""
    site.closed_card(1)
    with closing(sqlite3.connect(site.db)) as conn:
        conn.execute("DROP TABLE intake_notes")
        conn.commit()
    before = site.snapshot()
    assert site.failed() == ()
    assert site.snapshot() == before
    with closing(sqlite3.connect(site.db)) as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='intake_notes'").fetchone() is None


def test_an_unreadable_ledger_refuses_every_check_that_reads_it(site: Site) -> None:
    site.db.parent.mkdir(parents=True, exist_ok=True)
    site.db.write_bytes(b"this is not a sqlite file")
    assert site.failed() == (
        lifecycle.CHECK_OPEN_WORK,
        lifecycle.CHECK_CLOSURE,
        lifecycle.CHECK_ACCEPTED,
        lifecycle.CHECK_INBOX,
    )
    blockers = site.plan().blockers
    assert sum("读不出本机账本" in blocker for blocker in blockers) == 3
    assert sum("读不出收件箱" in blocker for blocker in blockers) == 1


def test_git_that_cannot_answer_refuses(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    _workspace(root)  # 不是 Git 仓库
    plan = lifecycle.plan_archive(root, PID, root / "0100_PLC自动化" / PID, control_root=root)
    assert tuple(check.name for check in plan.checks if not check.passed) == (lifecycle.CHECK_UNCOMMITTED,)
    assert "读不出 Git 状态" in plan.blockers[0]


def test_an_inbox_that_cannot_be_read_refuses(site: Site, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.pm_intake_service import PmIntakeError, PmIntakeService

    def broken(self: PmIntakeService, project_id: str, *args: object) -> tuple[IntakeItem, ...]:
        raise PmIntakeError("收件箱表坏了")

    monkeypatch.setattr(PmIntakeService, "list_items", broken)
    assert site.failed() == (lifecycle.CHECK_INBOX,)
    assert "读不出收件箱" in site.plan().blockers[0] and "收件箱表坏了" in site.plan().blockers[0]


# ── 没完成的变更单：只提示，不挡 ──────────────────────────


def test_an_unfinished_change_order_is_only_a_hint(site: Site) -> None:
    from auto_pm.domain.change.change_service import ChangeService

    created = ChangeService(str(site.root)).create_change_request(
        project_id=PID, domain="PLC", business_nature="DEF", impact_scope=["LOCAL"], applicant="user",
        background="背景", necessity="必要性",
    )
    commit_all(site.root)
    plan = site.plan()
    assert plan.change_hints == (f"{created.change_number}（draft）",)
    assert plan.blockers == ()


def test_completed_change_orders_are_not_hinted_and_unreadable_records_say_so(
    site: Site, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auto_pm.domain.change.change_service import ChangeService

    summaries = [
        ChangeSummary(change_number="CHG-PLC-2026-002", status="completed"),
        ChangeSummary(change_number="CHG-PLC-2026-003", status="approved"),
        ChangeSummary(change_number="CHG-PLC-2026-001", status="implementing"),
    ]
    monkeypatch.setattr(ChangeService, "list_change_requests", lambda self, project_id: summaries)
    assert lifecycle.open_change_hints(site.root, PID) == [
        "CHG-PLC-2026-001（implementing）",
        "CHG-PLC-2026-003（approved）",
    ]

    def broken(self: ChangeService, project_id: str) -> list[ChangeSummary]:
        raise OSError("变更目录读不了")

    monkeypatch.setattr(ChangeService, "list_change_requests", broken)
    (hint,) = lifecycle.open_change_hints(site.root, PID)
    assert "读不出变更记录" in hint and site.plan().blockers == ()


# ── 预演不写；写只改一栏 ──────────────────────────────────


def test_planning_writes_nothing(site: Site) -> None:
    site.closed_card(1)
    site.closed_card(2, closure="PREPARED")
    site.inbox_item("一条待确认")
    site.note("一句还没整理的话")
    before = site.snapshot()
    with closing(sqlite3.connect(site.db)) as conn:
        events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert site.plan().blockers
    lifecycle.plan_reactivate(site.root, PID)
    with closing(sqlite3.connect(site.db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == events
    assert site.snapshot() == before


def _other_entries_text(registry: Path) -> str:
    """登记表里 DJ-2026-005 这一条以外的全部文字（逐字节比对用）。"""
    text = registry.read_text(encoding="utf-8")
    start = text.index('    {\n      "project_id": "DJ-2026-005"')
    return text[:start] + text[text.index("\n    }", start):]


@pytest.mark.parametrize("status", ["", "active", "paused"])
def test_archive_changes_only_this_projects_status_and_keeps_schema_v1(tmp_path: Path, status: str) -> None:
    site = Site(tmp_path / "ws", status=status)
    site.closed_card(1)
    entry_before = dict(site.entries()[1])
    others_before = _other_entries_text(site.registry)
    tree_before = sorted(p.relative_to(site.root).as_posix() for p in site.project.rglob("*"))

    change = lifecycle.apply_plan(site.root, site.plan())

    assert (change.before, change.after, change.written) == (status, "archived", True)
    entry_after = site.entries()[1]
    assert entry_after == {**entry_before, "status": "archived"}
    assert _other_entries_text(site.registry) == others_before
    payload = json.loads(site.registry.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "workspace-registry.v1"
    wc.WorkspaceRegistry.model_validate(payload)
    assert sorted(p.relative_to(site.root).as_posix() for p in site.project.rglob("*")) == tree_before  # 目录不搬


def test_apply_refuses_a_plan_with_a_blocker_and_writes_nothing(site: Site) -> None:
    site.work("WORK-1", "IN_PROGRESS")
    before = site.registry.read_bytes()
    with pytest.raises(lifecycle.ProjectLifecycleError, match="开着的 Work WORK-1"):
        lifecycle.apply_plan(site.root, site.plan())
    assert site.registry.read_bytes() == before


def test_apply_checks_the_status_again_when_it_writes(site: Site) -> None:
    """预演之后登记表被别人改了：写的那一刻再核一次现在的状态，不照旧计划硬写。"""
    plan = site.plan()
    site.set_registry_status(PID, "archived")
    before = site.registry.read_bytes()
    with pytest.raises(lifecycle.ProjectLifecycleError, match="已归档"):
        lifecycle.apply_plan(site.root, plan)
    assert site.registry.read_bytes() == before


@pytest.mark.parametrize(("status", "words"), [("archived", "只有在研或暂停的项目能归档"), ("deleted", "已删除")])
def test_archive_refuses_a_project_that_is_already_archived_or_deleted(tmp_path: Path, status: str, words: str) -> None:
    site = Site(tmp_path / "ws", status=status)
    plan = site.plan()
    assert plan.refusal and words in plan.refusal and plan.blockers[0] == plan.refusal


def test_archive_refuses_a_project_that_is_not_registered(site: Site) -> None:
    _anchor(site.root / "0100_PLC自动化" / OTHER, OTHER)
    commit_all(site.root)
    plan = lifecycle.plan_archive(site.root, OTHER, site.root / "0100_PLC自动化" / OTHER, control_root=site.root)
    assert "不在工作区登记表里" in plan.refusal and "project register" in plan.refusal
    with pytest.raises(lifecycle.ProjectLifecycleError):
        lifecycle.apply_plan(site.root, plan)


def test_an_unreadable_registry_refuses(site: Site) -> None:
    site.registry.write_text("{not json", encoding="utf-8")
    assert "读不出工作区登记表" in site.plan().refusal
    assert "读不出工作区登记表" in lifecycle.plan_reactivate(site.root, PID).refusal


# ── 重新激活 ──────────────────────────────────────────────


def test_reactivate_puts_an_archived_project_back_to_active_and_touches_nothing_else(tmp_path: Path) -> None:
    site = Site(tmp_path / "ws", status="archived")
    site.work("WORK-1", "IN_PROGRESS")  # 重新激活不查五项
    entry_before = dict(site.entries()[1])
    others_before = _other_entries_text(site.registry)
    plan = lifecycle.plan_reactivate(site.root, PID)
    assert plan.blockers == () and plan.checks == ()
    change = lifecycle.apply_plan(site.root, plan)
    assert (change.before, change.after) == ("archived", "active")
    assert site.entries()[1] == {**entry_before, "status": "active"}
    assert _other_entries_text(site.registry) == others_before


@pytest.mark.parametrize(("status", "label"), [("", "在研"), ("active", "在研"), ("paused", "暂停"), ("deleted", "已删除")])
def test_reactivate_refuses_anything_that_is_not_archived_and_names_the_status(
    tmp_path: Path, status: str, label: str
) -> None:
    site = Site(tmp_path / "ws", status=status)
    before = site.registry.read_bytes()
    plan = lifecycle.plan_reactivate(site.root, PID)
    assert f"现在的状态是“{label}”" in plan.refusal and "不是“已归档”" in plan.refusal
    with pytest.raises(lifecycle.ProjectLifecycleError):
        lifecycle.apply_plan(site.root, plan)
    assert site.registry.read_bytes() == before


def test_set_status_never_writes_deleted_and_never_starts_from_it(tmp_path: Path) -> None:
    site = Site(tmp_path / "ws", status="deleted")
    service = WorkspaceRegistryService(site.root)
    before = site.registry.read_bytes()
    with pytest.raises(WorkspaceRegistryError, match="不能改成"):
        service.set_status(PID, "deleted", only_from=("active",))
    with pytest.raises(WorkspaceRegistryError, match="已删除"):
        service.set_status(PID, "active", only_from=("deleted", "archived"))
    assert service.set_status("DJ-2026-404", "archived", only_from=("active",)) is None
    assert site.registry.read_bytes() == before


# ── 从登记表补出已删除的项目 ──────────────────────────────


def test_deleted_projects_come_from_the_registry_and_say_whether_they_can_be_restored(site: Site) -> None:
    assert lifecycle.deleted_projects(site.root) == []
    recycled = recycle_project(site.root, site.project, PID, now=NOW)
    mark_registry_deleted(site.root, PID)

    (found,) = lifecycle.deleted_projects(site.root)
    assert (found.project_id, found.project_root, found.restorable) == (PID, f"0100_PLC自动化/{PID}", True)
    assert found.hint == f"可以用 project restore {PID} 搬回"

    recycled.rename(site.root / "moved-away")
    (gone,) = lifecycle.deleted_projects(site.root)
    assert not gone.restorable and gone.hint == "回收区里找不到（可能已手工清掉）"


def test_deleted_projects_of_a_workspace_without_a_readable_registry_is_empty(tmp_path: Path) -> None:
    assert lifecycle.deleted_projects(tmp_path) == []
    site = Site(tmp_path / "ws")
    site.registry.write_text("{not json", encoding="utf-8")
    assert lifecycle.deleted_projects(site.root) == []
