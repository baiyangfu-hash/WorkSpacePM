"""CHG-SCPT-2026-652：``project archive`` / ``project reactivate`` 两条命令，和 ``project list`` 的四种列法。

走真命令行（``cli``）、真登记表、真 Git 工作区；审计日志只换成记到列表里，好核对“预演不写审计”。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from auto_pm.application.core.lease_handover_service import AGENT_MARKERS
from auto_pm.application.core.project_delete_guard import mark_registry_deleted, recycle_project
from auto_pm.application.core.workspace_registry_service import WorkspaceRegistryService
from auto_pm.contracts.mission import MissionState
from auto_pm.ui.cli.__main__ import cli
from tests.core.test_project_lifecycle_service import (
    NOW,
    PID,
    Site,
    _other_entries_text,
    commit_all,
)
from tests.core.test_workspace_registry_service import _anchor

USER_WORDS = "user-confirmation:cmsg_user_says_archive_ok"
ARCHIVED = "DJ-2026-006"
DELETED = "DJ-2026-007"


class Desk:
    """命令行这一头：一个 ``Site`` 加上被记下来的审计日志。"""

    def __init__(self, site: Site, monkeypatch: pytest.MonkeyPatch) -> None:
        self.site = site
        self.audit: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "auto_pm.infrastructure.logging.audit.audit_log",
            lambda action, **details: self.audit.append({"action": action, **details}),
        )

    def run(self, *args: str) -> Result:
        return CliRunner().invoke(cli, ["-w", str(self.site.root), "project", *args], catch_exceptions=False)

    def status(self) -> str:
        return str(self.site.entries()[1].get("status", ""))


@pytest.fixture
def no_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in AGENT_MARKERS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def desk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_agent: None) -> Desk:
    return Desk(Site(tmp_path / "ws"), monkeypatch)


@pytest.fixture
def archived_desk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_agent: None) -> Desk:
    return Desk(Site(tmp_path / "ws", status="archived"), monkeypatch)


# ── project archive ───────────────────────────────────────


def test_archive_without_confirm_lists_the_five_checks_and_writes_nothing(desk: Desk) -> None:
    desk.site.closed_card(1)
    before = desk.site.snapshot()
    result = desk.run("archive", PID)
    assert result.exit_code == 0, result.output
    for name in ("卡全关", "收口走完", "没有已验收没收口的卡", "没有没提交的改动", "收件箱没有待处理条目"):
        assert f"[通过] {name}" in result.output
    assert "怎么办" not in result.output
    assert "在研 → 已归档" in result.output and "预演" in result.output
    assert desk.site.snapshot() == before and desk.audit == [] and desk.status() == ""


def test_archive_dry_run_hints_at_unfinished_change_orders_without_refusing(desk: Desk) -> None:
    from auto_pm.domain.change.change_service import ChangeService

    created = ChangeService(str(desk.site.root)).create_change_request(
        project_id=PID, domain="PLC", business_nature="DEF", impact_scope=["LOCAL"], applicant="user",
        background="背景", necessity="必要性",
    )
    commit_all(desk.site.root)
    result = desk.run("archive", PID)
    assert result.exit_code == 0, result.output
    assert f"{created.change_number}（draft）" in result.output and "只是提示，不挡" in result.output


@pytest.mark.parametrize("marker", ["AUTO_PM_AGENT", "CLAUDECODE", "CODEX_THREAD_ID"])
def test_archive_confirm_is_refused_for_an_agent(desk: Desk, monkeypatch: pytest.MonkeyPatch, marker: str) -> None:
    before = desk.site.snapshot()
    monkeypatch.setenv(marker, "1")
    result = desk.run("archive", PID, "--confirm", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 1 and "归档项目只听用户本人" in result.output
    assert desk.site.snapshot() == before and desk.audit == []


@pytest.mark.parametrize("words", [None, "yes please", "user-confirmation:claude_said_ok"])
def test_archive_confirm_needs_the_users_own_words(desk: Desk, words: str | None) -> None:
    before = desk.site.snapshot()
    extra = [] if words is None else ["--approval-evidence-ref", words]
    result = desk.run("archive", PID, "--confirm", *extra)
    assert result.exit_code == 1 and "只听用户本人" in result.output
    assert desk.site.snapshot() == before and desk.audit == []


def test_archive_confirm_flips_one_field_keeps_the_folder_and_show_and_list_still_find_it(desk: Desk) -> None:
    desk.site.closed_card(1)
    others = _other_entries_text(desk.site.registry)
    tree = sorted(p.relative_to(desk.site.root).as_posix() for p in desk.site.project.rglob("*"))

    result = desk.run("archive", PID, "--confirm", "--approval-evidence-ref", USER_WORDS)

    assert result.exit_code == 0, result.output
    assert "项目已归档" in result.output and desk.status() == "archived"
    assert _other_entries_text(desk.site.registry) == others
    assert json.loads(desk.site.registry.read_text(encoding="utf-8"))["schema_version"] == "workspace-registry.v1"
    assert sorted(p.relative_to(desk.site.root).as_posix() for p in desk.site.project.rglob("*")) == tree
    assert desk.audit == [
        {
            "action": "project_archive",
            "project_id": PID,
            "status_before": "active",
            "status_after": "archived",
            "approval_evidence_ref": USER_WORDS,
        }
    ]
    shown = desk.run("show", PID)
    assert shown.exit_code == 0 and "状态:" in shown.output and "已归档" in shown.output
    listed = json.loads(desk.run("list", "--status", "archived", "--json").output)
    assert [row["project_id"] for row in listed] == [PID]


def test_archive_confirm_with_a_failed_check_is_refused_with_the_reason(desk: Desk) -> None:
    desk.site.work("WORK-1", "CLOSED")
    desk.site.mission("MISSION-1", "WORK-1", MissionState.ACCEPTED)
    desk.site.inbox_item("登录页偶发白屏")
    (desk.site.project / "new.txt").write_text("x", encoding="utf-8")
    before = desk.site.registry.read_bytes()
    result = desk.run("archive", PID, "--confirm", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 1 and "现在不能归档" in result.output
    assert "[通过] 卡全关" in result.output and "[通过] 收口走完" in result.output
    for name in ("没有已验收没收口的卡", "没有没提交的改动", "收件箱没有待处理条目"):
        assert f"[不过] {name}" in result.output
    assert "MISSION-1" in result.output and "登录页偶发白屏" in result.output
    flat = result.output.replace("\n", "")
    assert "PROPOSED 待确认" in flat and "pm inbox confirm" in flat  # 不过的那一项下面写怎么办
    assert "pm missions --pid" not in flat  # 通过的那一项不写
    assert desk.site.registry.read_bytes() == before and desk.audit == []


def test_archive_of_an_unknown_or_already_archived_project_is_refused(archived_desk: Desk) -> None:
    missing = archived_desk.run("archive", "DJ-2026-404")
    assert missing.exit_code == 1 and "项目不存在" in missing.output
    again = archived_desk.run("archive", PID, "--confirm", "--approval-evidence-ref", USER_WORDS)
    assert again.exit_code == 1 and "只有在研或暂停的项目能归档" in again.output
    assert archived_desk.status() == "archived" and archived_desk.audit == []


# ── project reactivate ────────────────────────────────────


def test_reactivate_without_confirm_only_previews(archived_desk: Desk) -> None:
    before = archived_desk.site.snapshot()
    result = archived_desk.run("reactivate", PID)
    assert result.exit_code == 0, result.output
    assert "已归档 → 在研" in result.output and "预演" in result.output
    assert archived_desk.site.snapshot() == before and archived_desk.audit == []


def test_reactivate_confirm_is_refused_for_an_agent_and_without_the_users_words(
    archived_desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = archived_desk.site.snapshot()
    no_words = archived_desk.run("reactivate", PID, "--confirm")
    assert no_words.exit_code == 1 and "只听用户本人" in no_words.output
    styled = archived_desk.run("reactivate", PID, "--confirm", "--approval-evidence-ref", "user-confirmation:agent_ok")
    assert styled.exit_code == 1 and "只听用户本人" in styled.output
    monkeypatch.setenv("AUTO_PM_AGENT", "trae")
    as_agent = archived_desk.run("reactivate", PID, "--confirm", "--approval-evidence-ref", USER_WORDS)
    assert as_agent.exit_code == 1 and "重新激活项目只听用户本人" in as_agent.output
    assert archived_desk.site.snapshot() == before and archived_desk.audit == []


def test_reactivate_confirm_puts_the_project_back_to_active(archived_desk: Desk) -> None:
    others = _other_entries_text(archived_desk.site.registry)
    result = archived_desk.run("reactivate", PID, "--confirm", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 0, result.output
    assert archived_desk.status() == "active" and _other_entries_text(archived_desk.site.registry) == others
    assert archived_desk.audit == [
        {
            "action": "project_reactivate",
            "project_id": PID,
            "status_before": "archived",
            "status_after": "active",
            "approval_evidence_ref": USER_WORDS,
        }
    ]


def test_reactivate_refuses_a_project_that_is_not_archived_and_says_what_it_is(desk: Desk) -> None:
    before = desk.site.registry.read_bytes()
    result = desk.run("reactivate", PID, "--confirm", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 1 and "现在的状态是“在研”" in result.output and "不是“已归档”" in result.output
    unknown = desk.run("reactivate", "DJ-2026-404")
    assert unknown.exit_code == 1 and "不在工作区登记表里" in unknown.output
    assert desk.site.registry.read_bytes() == before and desk.audit == []


def test_archive_then_reactivate_round_trip(desk: Desk) -> None:
    assert desk.run("archive", PID, "--confirm", "--approval-evidence-ref", USER_WORDS).exit_code == 0
    assert desk.run("reactivate", PID, "--confirm", "--approval-evidence-ref", USER_WORDS).exit_code == 0
    assert desk.status() == "active"
    assert [entry["action"] for entry in desk.audit] == ["project_archive", "project_reactivate"]


# ── project list：默认、--status archived、--status deleted、--all ──


@pytest.fixture
def three(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_agent: None) -> tuple[Desk, Path]:
    """一个在研（DJ-2026-005）、一个已归档（DJ-2026-006）、一个已删除且目录在回收区（DJ-2026-007）。"""
    site = Site(tmp_path / "ws")
    registry = WorkspaceRegistryService(site.root)
    for project_id, status in ((ARCHIVED, "archived"), (DELETED, "")):
        _anchor(site.root / "0100_PLC自动化" / project_id, project_id)
        registry.register(project_id, kind="equipment", status=status)
    recycled = recycle_project(site.root, site.root / "0100_PLC自动化" / DELETED, DELETED, now=NOW)
    mark_registry_deleted(site.root, DELETED)
    return Desk(site, monkeypatch), recycled


def _ids(result: Result) -> list[str]:
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    assert all("project_id" in row for row in rows)
    return sorted(row["project_id"] for row in rows)


def test_list_hides_archived_by_default_and_says_how_many(three: tuple[Desk, Path]) -> None:
    desk, _ = three
    table = desk.run("list")
    assert table.exit_code == 0, table.output
    assert PID in table.output and ARCHIVED not in table.output and DELETED not in table.output
    assert "另有 1 个已归档，用 `--status archived` 或 `--all` 看" in table.output
    as_json = desk.run("list", "--json")
    assert PID in _ids(as_json) and ARCHIVED not in _ids(as_json) and DELETED not in _ids(as_json)
    assert "另有" not in as_json.output  # --json 只输出列表


def test_list_without_archived_projects_has_no_tail_line(desk: Desk) -> None:
    table = desk.run("list")
    assert table.exit_code == 0 and PID in table.output and "另有" not in table.output


def test_list_status_archived_shows_only_the_archived_ones(three: tuple[Desk, Path]) -> None:
    desk, _ = three
    assert _ids(desk.run("list", "--status", "archived", "--json")) == [ARCHIVED]
    table = desk.run("list", "--status", "archived")
    assert ARCHIVED in table.output and PID not in table.output and "另有" not in table.output


def test_list_status_deleted_comes_from_the_registry_and_says_whether_it_can_be_restored(
    three: tuple[Desk, Path],
) -> None:
    desk, recycled = three
    rows = json.loads(desk.run("list", "--status", "deleted", "--json").output)
    assert [(row["project_id"], row["status"], row["kind"], row["restorable"]) for row in rows] == [
        (DELETED, "deleted", "equipment", True)
    ]
    assert rows[0]["path"] == f"0100_PLC自动化/{DELETED}"
    table = desk.run("list", "--status", "deleted")
    assert DELETED in table.output and f"project restore {DELETED}" in table.output.replace("\n", "")
    assert PID not in table.output

    moved = desk.site.root.parent / "moved-away"  # 手工清出工作区
    recycled.rename(moved)
    rows = json.loads(desk.run("list", "--status", "deleted", "--json").output)
    assert [(row["project_id"], row["restorable"]) for row in rows] == [(DELETED, False)]
    assert "回收区里找不到" in desk.run("list", "--status", "deleted").output.replace("\n", "")

    # 目录被手工搬回工作区（没走 project restore）：扫得到了，就按扫到的那一行列一次，不再从登记表补一行
    moved.rename(desk.site.root / "0100_PLC自动化" / DELETED)
    rows = json.loads(desk.run("list", "--status", "deleted", "--json").output)
    assert [row["project_id"] for row in rows] == [DELETED] and "restorable" not in rows[0]


def test_list_all_shows_active_archived_and_deleted_and_still_takes_other_filters(three: tuple[Desk, Path]) -> None:
    desk, _ = three
    everything = _ids(desk.run("list", "--all", "--json"))
    assert {PID, ARCHIVED, DELETED} <= set(everything)
    table = desk.run("list", "--all")
    assert all(project_id in table.output for project_id in (PID, ARCHIVED, DELETED)) and "另有" not in table.output
    assert _ids(desk.run("list", "--all", "--kind", "equipment", "--json")) == [ARCHIVED, DELETED]
    assert _ids(desk.run("list", "--all", "--search", "007", "--json")) == [DELETED]
    assert _ids(desk.run("list", "--all", "--status", "archived", "--json")) == [ARCHIVED]
    assert DELETED not in _ids(desk.run("list", "--all", "--stack", "plc", "--json"))  # 登记表里没有技术栈


# ── 搬回后登记表不留空键（第 9 条，走真命令） ──────────────


def test_delete_then_restore_leaves_no_empty_status_before_delete_key(three: tuple[Desk, Path]) -> None:
    desk, _ = three
    registry = desk.site.registry
    entry_before_delete = {**next(e for e in desk.site.entries() if e["project_id"] == DELETED)}
    assert (entry_before_delete["status"], entry_before_delete["status_before_delete"]) == ("deleted", "")
    start = registry.read_text(encoding="utf-8").index(f'    {{\n      "project_id": "{DELETED}"')
    others = registry.read_text(encoding="utf-8")[:start]

    result = desk.run("restore", DELETED, "--apply", "--approval-evidence-ref", USER_WORDS)

    assert result.exit_code == 0, result.output
    entry = next(e for e in desk.site.entries() if e["project_id"] == DELETED)
    assert "status_before_delete" not in entry and entry["status"] == ""
    assert {k: v for k, v in entry.items() if k != "status"} == {
        k: v for k, v in entry_before_delete.items() if k not in ("status", "status_before_delete")
    }
    assert registry.read_text(encoding="utf-8")[:start] == others


# ── 已启用批准口令：改为用户在终端输入口令 ────────────────


def test_with_a_committed_pin_archive_needs_the_pin_typed_in_a_terminal(desk: Desk, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.approval_proof_service import ApprovalProofService, make_key
    from auto_pm.ui.cli import approval_pin

    pin = "relay-K1-on"
    key = make_key("baiyang", pin, n=2**10)
    monkeypatch.setattr(ApprovalProofService, "committed_state", lambda self: ([key], ""))

    no_terminal = desk.run("archive", PID, "--confirm", "--approval-evidence-ref", USER_WORDS)
    assert no_terminal.exit_code == 1 and "用户本人在自己的终端" in no_terminal.output and desk.status() == ""

    monkeypatch.setattr(approval_pin, "_stdin_is_tty", lambda: True)
    answers = iter(["wrong-pin-123", pin])
    monkeypatch.setattr(approval_pin, "_prompt_hidden", lambda text: next(answers))
    wrong = desk.run("archive", PID, "--confirm")
    assert wrong.exit_code == 1 and desk.status() == "" and desk.audit == []
    right = desk.run("archive", PID, "--confirm")
    assert right.exit_code == 0, right.output
    assert desk.status() == "archived"
    assert desk.audit[-1]["approval_evidence_ref"].startswith("user-confirmation:pin-")
    assert "project-archive" in desk.audit[-1]["approval_evidence_ref"]


def test_open_cards_get_a_what_to_do_line_and_chinese_state_names(desk: Desk) -> None:
    desk.site.work("WORK-1", "IN_PROGRESS")
    result = desk.run("archive", PID)
    flat = result.output.replace("\n", "")
    assert result.exit_code == 1 and "[不过] 卡全关" in flat
    assert "开着的 Work WORK-1（IN_PROGRESS）" in flat  # 和 project delete 共用的原因文字原样
    assert "怎么办：" in flat and "pm missions --pid" in flat and "状态码：IN_PROGRESS 在干" in flat


def test_archive_dry_run_lists_a_raw_note_with_its_way_out_and_changes_nothing(desk: Desk) -> None:
    """D-357：归档预演第 5 项列出待整理记录和新的“怎么办”；预演不改登记表、不改账本。"""
    note = desk.site.note("看板字太小")
    commit_all(desk.site.root)
    before = desk.site.snapshot()
    result = desk.run("archive", PID)
    flat = result.output.replace("\n", "")
    assert "[不过] 收件箱没有待处理条目" in result.output
    assert f"待整理记录 {note.note_id}（还没整理成正式条目）：看板字太小" in flat
    assert "待整理记录请 AI 先整理成正式条目（pm inbox add --from-note <NOTE-ID>）" in flat
    for name in ("卡全关", "收口走完", "没有已验收没收口的卡", "没有没提交的改动"):
        assert f"[通过] {name}" in result.output
    assert desk.site.snapshot() == before and desk.audit == []

    refused = desk.run("archive", PID, "--confirm", "--approval-evidence-ref", USER_WORDS)
    assert refused.exit_code == 1 and "现在不能归档" in refused.output and note.note_id in refused.output
    assert desk.site.snapshot() == before and desk.status() != "archived"


def test_archive_passes_once_the_note_was_turned_into_an_item_and_the_user_rejected_it(desk: Desk) -> None:
    from auto_pm.contracts.intake import IntakeStatus

    note = desk.site.note("记错的一句话")
    item = desk.site.turn(note)
    commit_all(desk.site.root)
    waiting = desk.run("archive", PID)
    assert "[不过] 收件箱没有待处理条目" in waiting.output and item.item_id in waiting.output
    assert note.note_id not in waiting.output  # the triaged note itself no longer blocks
    desk.site.decide(item, IntakeStatus.REJECTED)
    done = desk.run("archive", PID)
    assert "[通过] 收件箱没有待处理条目" in done.output and "[不过]" not in done.output


def test_archive_dry_run_on_a_ledger_without_the_notes_table_does_not_create_it(desk: Desk) -> None:
    import sqlite3
    from contextlib import closing

    desk.site.closed_card(1)
    with closing(sqlite3.connect(desk.site.db)) as conn:
        conn.execute("DROP TABLE intake_notes")
        conn.commit()
    commit_all(desk.site.root)
    before = desk.site.snapshot()
    result = desk.run("archive", PID)
    assert "[通过] 收件箱没有待处理条目" in result.output
    assert desk.site.snapshot() == before
    with closing(sqlite3.connect(desk.site.db)) as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='intake_notes'").fetchone() is None
