"""“工作树与分支”页的按钮（看板工位管理单，2026-11-16）：每行能不能收、点了跑哪条命令、带 AI 标记时一律灰着不运行。

用的是项目经理按用户本机样子写的验收图（13:49Z）：claude-1b7302 能收；名册外的 gate-formal 能清、但写明可能正被门禁用着；
codex 有没推送的、trae 有未提交的，灰着照抄命令原话；远程已删的分支只有已并进 main 的进整批清理；手工开的 detached 目录灰着。
命令用假的运行器，不碰真账本；真命令、真仓库的那一条在 test_cockpit_board_worktrees_flow.py。
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import actions, decisions, policy, readers, stations  # noqa: E402
from cockpit_board.widgets import common as c  # noqa: E402
from cockpit_board.widgets.decisions import ConfirmDialog, DecisionsPage  # noqa: E402
from cockpit_board.widgets.worktrees import (  # noqa: E402
    ActionDialog,
    RegistryDialog,
    WorktreesPage,
)
from cockpit_board.worktree_controller import (  # noqa: E402
    NOT_ALLOWED,
    NOTHING_TO_RECLAIM,
    RUNNING,
    WorktreeController,
)

NOW = datetime(2026, 11, 16, 14, 0, tzinfo=UTC)
CODEX_SAID = "有 1 个提交还没推到 GitHub；先 `git push -u origin codex/701-io`"
TRAE_SAID = "有未提交的改动：a.txt、b.txt、c.txt；先提交或交给用户决定"
MANUAL_SAID = "工位不在分支上（detached HEAD），不动"


def _station(name: str, kind: str, branch: str, *, dirty: int = 0, unpushed: int = 0, merged: bool | None = True,
             checked: bool = True, **extra: Any) -> dict[str, Any]:
    return {"name": name, "path": f"/w/.auto-pm/worktrees/{name}", "kind": kind, "registered": True, "broken": "",
            "branch": branch, "checked": checked, "dirty": dirty if checked else None, "unpushed": unpushed if checked else None,
            "merged": merged if checked else None, "locked": False, "idle_days": 0, "stale": False, **extra}


STATIONS = [
    _station("claude-1b7302", "agent", "claude/690-intake-368c1af"),
    _station("gate-formal", "other", "gate/formal"),
    _station("codex", "agent", "codex/701-io", unpushed=1, merged=False),
    _station("trae", "agent", "trae/702-ui", dirty=3),
    _station("gate-manual", "other", ""),
]
SWEEP = [
    {"target": "/w/.auto-pm/worktrees/claude-1b7302", "category": "agent", "remove": True, "reason": "已并进 main、干净"},
    {"target": "/w/.auto-pm/worktrees/gate-formal", "category": "other", "remove": True, "reason": "已并进 main、干净"},
    {"target": "/w/.auto-pm/worktrees/codex", "category": "agent", "remove": False, "reason": CODEX_SAID},
    {"target": "/w/.auto-pm/worktrees/trae", "category": "agent", "remove": False, "reason": TRAE_SAID},
    {"target": "/w/.auto-pm/worktrees/gate-manual", "category": "other", "remove": False, "reason": MANUAL_SAID},
    {"target": "claude/628a-gui-shell", "category": "gone-branch", "remove": True, "reason": "远程已删且已并进 main，删本地分支"},
    {"target": "claude/650-wip", "category": "gone-branch", "remove": False, "reason": "远程已删但没并进 main，保留"},
]
CLAIMS = [{"card": "690-intake-368c1af", "owner": "claude-1b7302", "status": "active",
           "paths": ["00_Infrastructure/auto_pm/active_release.json", "0100_PLC自动化/DJ-2026-005/x.scl"]}]
HOLDERS = {"claude-1b7302": {"title": "部署 1.3.4", "heartbeat_at": (NOW - timedelta(hours=2)).isoformat()}}


def _view(**changes: Any) -> stations.StationsView:
    arguments: dict[str, Any] = {"human_block": "", "now": NOW, "long_runs": []}
    arguments.update(changes)
    return stations.build_view(arguments.pop("stations", STATIONS), arguments.pop("sweep", SWEEP), arguments.pop("claims", CLAIMS),
                               arguments.pop("holders", HOLDERS), **arguments)


def _row(view: stations.StationsView, name: str) -> stations.StationRow:
    return next(row for row in view.rows if row.name == name)


# ---------------------------------------------------------------- 判断（纯 Python）


def test_roster_and_alias_are_the_same_as_the_cockpit_command() -> None:
    from auto_pm.application.core import agent_worktree_service as service

    assert stations.ROSTER_PREFIX == service.AGENT_ROSTER
    assert stations.ALIAS.pattern == service._ALIAS.pattern


def test_the_acceptance_picture_from_the_users_machine() -> None:
    view = _view()
    claude = _row(view, "claude-1b7302")
    assert claude.action is not None and claude.action.args == ("worktree", "close", "claude-1b7302") and claude.blocked == ""
    assert claude.card == "690-intake-368c1af" and claude.project == "DJ-2026-005"
    assert "对话“部署 1.3.4”" in claude.who and "占位人 claude-1b7302" in claude.who and "心跳 2.0 小时前" in claude.last_seen
    gate = _row(view, "gate-formal")  # 名册外：close 不认这个名字，只能按清理清单清这一个目录
    assert gate.action is not None and gate.action.args == ("worktree", "sweep", "--apply", "--only", "gate-formal", "--no-fetch")
    assert gate.blocked == "" and "未知" in gate.warning  # 命令不说哪个目录正被门禁用着：照实写未知，不假装
    assert _row(view, "codex").blocked == CODEX_SAID  # 原话照抄
    assert _row(view, "trae").blocked == TRAE_SAID
    assert _row(view, "gate-manual").blocked == "清理清单判了保留：" + MANUAL_SAID
    # 远程已删的分支：没有单项参数，只有一个整批按钮，确认框里列全会清的；没并进 main 的只列不清
    assert view.sweep_all is not None and view.sweep_all.args == ("worktree", "sweep", "--apply", "--no-fetch")
    cleared = [value for key, value in view.sweep_all.facts if key == "会清"]
    assert cleared == [item["target"] for item in SWEEP if item["remove"]]
    assert [(row.target, row.removable) for row in view.sweep] == [("claude/628a-gui-shell", True), ("claude/650-wip", False)]


def test_a_running_long_task_keeps_every_off_roster_dir_and_an_unread_one_says_unknown() -> None:
    running = _view(long_runs=[{"name": "gate-full", "state": "RUNNING"}, {"name": "old", "state": "DONE"}])
    gate = _row(running, "gate-formal")
    assert "有长任务在跑（gate-full）" in gate.warning and gate.blocked == gate.warning  # 分不出门禁用的是哪个目录：都不放
    assert _row(running, "claude-1b7302").blocked == ""  # 名册里的工位照旧按自己的检查结果
    assert running.sweep_all_blocked == gate.warning and _view().sweep_all_blocked == ""  # 整批会连名册外目录一起清：一样不放
    unread = _view(long_runs=None)
    assert "未知" in _row(unread, "gate-formal").warning and "没读到" in _row(unread, "gate-formal").warning


def test_close_block_follows_the_command_in_order() -> None:
    base = _station("claude", "agent", "claude/1")
    assert stations.close_block(base) == ""
    assert "还没查过" in stations.close_block({**base, "checked": False})
    assert "lock" in stations.close_block({**base, "locked": True})
    assert "detached" in stations.close_block({**base, "branch": ""})
    assert "不是 claude/ 开头" in stations.close_block({**base, "branch": "trae/1"})
    assert stations.close_block({**base, "dirty": 2}) == "有未提交的改动 2 个文件"  # 清理清单没读到时按数字写
    assert stations.close_block({**base, "unpushed": 1, "merged": False}) == "有 1 个提交还没推到 GitHub"
    assert stations.close_block({**base, "unpushed": 2, "merged": True}) == ""  # 已并进本机 main（待推备份）允许收工位
    assert stations.close_block({**base, "dirty": 2}, TRAE_SAID) == TRAE_SAID
    assert "目录坏了" in stations.close_block({**base, "broken": "目录不在了"})


def test_nothing_is_clickable_when_the_board_has_an_ai_marker_or_cannot_tell() -> None:
    for markers in (("CLAUDECODE",), None):
        reason = decisions.human_only_block(markers)
        view = _view(human_block=reason)
        assert reason and all(row.blocked == reason for row in view.rows)


def test_unread_commands_grey_the_buttons_instead_of_meaning_none() -> None:
    view = _view(sweep=None, claims=None)
    assert _row(view, "gate-formal").blocked == "清理清单没读到，判不了能不能清"
    assert _row(view, "claude-1b7302").blocked == ""  # 收工位只看工位列表本身的检查结果
    assert _row(view, "claude-1b7302").project == stations.UNKNOWN
    assert any("占位表没读到" in note for note in view.notes) and view.sweep_all is None


def test_every_command_the_page_can_run_is_on_the_policy_list() -> None:
    view = _view()
    produced = [row.action.args for row in view.rows if row.action is not None]
    produced += [view.sweep_all.args] if view.sweep_all else []
    produced += [stations.reclaim_preview_args(), stations.reclaim_action(["x"]).args]
    assert produced and all(stations.allowed_command(args) for args in produced)
    for bad in (("worktree", "close", "--force"), ("worktree", "close", "a b"), ("worktree", "close", "x", "--force"),
                ("worktree", "sweep", "--apply"), ("worktree", "open", "claude", "1"), ("pm", "accept", "--mission-id", "M")):
        assert not stations.allowed_command(bad), bad


def test_policy_names_why_this_page_may_remove_things() -> None:
    """policy.NEVER 里有“删除”：这一页是唯一例外，来由和护栏写在 policy.py，按钮字也不出现禁用词。"""
    source = (SCRIPTS / "cockpit_board" / "policy.py").read_text(encoding="utf-8")
    assert "删除" in policy.NEVER and "WORKTREE_BUTTONS" in source and "唯一例外" in source
    for guard in ("AI 标记", "检查结果", "WORKTREE_COMMANDS", "回执"):
        assert guard in source, guard
    for text in policy.WORKTREE_BUTTONS:
        assert not any(word in text for word in policy.NEVER), text


def test_card_and_project_come_from_branch_and_claim_paths() -> None:
    assert stations.card_of("claude/695-launcher-worktree") == "695-launcher-worktree"
    assert stations.card_of("main") == "" and stations.card_of("") == ""
    assert stations.project_of(["01_Project/Python/02_在研项目/SW-2026-008_auto-pm/x.py", "0100_PLC自动化/DJ-2026-005/a"]) == (
        "SW-2026-008、DJ-2026-005")
    assert stations.project_of(["00_Obsidian_Base/x.md"]) == ""


def test_reclaim_preview_is_read_back_with_wrapped_lines() -> None:
    text = ("可回收 claude-aaaaaa：孤儿持有者记录：工位目录已不存在，没有记录持有进程号，\n"
            "50.0 小时没有心跳（阈值 24 小时）\n可回收 claude-bbbbbb：记录的持有进程 9 已不在\n加 --apply 才会真的回收（先存救援引用，分支保留）\n")
    assert stations.parse_reclaim_preview(text) == [
        "claude-aaaaaa：孤儿持有者记录：工位目录已不存在，没有记录持有进程号，50.0 小时没有心跳（阈值 24 小时）",
        "claude-bbbbbb：记录的持有进程 9 已不在",
    ]
    assert stations.parse_reclaim_preview("没有持有对话已不在的会话别名工位，也没有孤儿持有者记录\n") == []


def test_claim_list_reader() -> None:
    assert readers.parse("claim_list", "[]").data == {"claims": []}
    assert not readers.parse("claim_list", '[{"owner": "x"}]').ok


# ---------------------------------------------------------------- 页面和控制器


class FakeCli:
    def __init__(self, preview: str = "", registry: str = "", registry_rc: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.preview = preview
        self.registry = registry
        self.registry_rc = registry_rc

    def __call__(self, command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        args = command[3:]
        self.calls.append(args)
        if args == ["worktree", "reclaim", "--stale"]:
            return subprocess.CompletedProcess(command, 0, self.preview, "")
        if args == ["agent", "list", "--json"]:
            return subprocess.CompletedProcess(command, self.registry_rc, self.registry, "账本读不了" if self.registry_rc else "")
        return subprocess.CompletedProcess(command, 0, "已收工位\n", "")


def _wait(controller: WorktreeController, qapp: QApplication) -> None:
    for _ in range(200):
        for job in list(controller._jobs):
            job.wait(2000)
        qapp.processEvents()
        if not controller._jobs:
            break
    qapp.processEvents()


def _results() -> list[c.ReadResult]:
    data = {"worktree_list": {"stations": STATIONS}, "worktree_sweep": {"items": SWEEP, "applied": False, "fetch_warning": ""},
            "claim_list": {"claims": CLAIMS}, "long_run": {"tasks": []}}
    out = []
    for reader, value in data.items():
        outcome = actions.ReadOutcome("ok", "x", 0, stdout="{}")
        out.append(c.ReadResult(reader, "main.py " + reader, outcome, readers.Parsed(readers.OK, value)))
    return out


def _page(markers: tuple[str, ...] | None = ()) -> WorktreesPage:
    page = WorktreesPage(None, lambda: markers, lambda _text: None, lambda: NOW)
    page.show_results("范围：本机控制根", _results())
    return page


def _buttons(page: WorktreesPage) -> dict[str, QPushButton]:
    return {f"{b.property('worktree_action')}:{b.property('target') or ''}": b
            for b in page.findChildren(QPushButton) if b.property("worktree_action")}


def test_page_draws_one_card_per_station_with_the_reason_beside_a_grey_button(qapp: QApplication) -> None:
    page = _page()
    buttons = _buttons(page)
    assert buttons["close:claude-1b7302"].isEnabled() and buttons["sweep_one:gate-formal"].isEnabled()
    assert not buttons["close:codex"].isEnabled() and not buttons["close:trae"].isEnabled()
    assert not buttons["sweep_one:gate-manual"].isEnabled()
    reasons = {label.property("blocked_reason"): label.text() for label in page.findChildren(QLabel) if label.property("blocked_reason")}
    assert reasons["codex"] == CODEX_SAID and reasons["trae"] == TRAE_SAID
    assert buttons["reclaim:"].isEnabled() and buttons["sweep_all:3 项"].isEnabled()  # 整批按钮的目标写“N 项”
    assert {b.text() for b in page.findChildren(QPushButton)} <= policy.WORKTREE_BUTTONS


def test_with_an_ai_marker_every_button_is_grey_and_the_dialog_cannot_run(qapp: QApplication) -> None:
    page = _page(("CLAUDECODE",))
    assert not any(b.isEnabled() for b in _buttons(page).values())
    action = _view().rows[0].action
    assert action is not None
    dialog = page.open_dialog(action, "", "", run=False)  # 就算从别处直接打开确认框：确认键也灰着
    assert not dialog.run_button.isEnabled() and dialog.blocked


def test_dialog_shows_target_checks_and_the_command(qapp: QApplication) -> None:
    page = _page()
    row = _row(page.view, "claude-1b7302")
    assert row.action is not None
    dialog = page.open_dialog(row.action, row.blocked, row.warning, run=False)
    assert isinstance(dialog, ActionDialog) and dialog.run_button.isEnabled()
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "claude/690-intake-368c1af" in texts and "未提交 0" in texts and "未推送 0" in texts and "已并进 main" in texts
    assert dialog.command_text == "main.py worktree close claude-1b7302"


def test_controller_runs_the_exact_command_and_rereads_on_success(qapp: QApplication) -> None:
    page, fake, changed = _page(), FakeCli(), []
    controller = WorktreeController(page, Path("/nowhere"), lambda: changed.append(1), runner=fake, markers=lambda: ())
    row = _row(page.view, "claude-1b7302")
    assert row.action is not None
    page.run_requested.emit(row.action)
    _wait(controller, qapp)
    assert fake.calls == [["worktree", "close", "claude-1b7302"]] and changed == [1]
    assert page.receipts[-1].rc == 0
    receipts = [f for f in page.findChildren(QLabel) if f.text() == "已收工位"]
    assert receipts, "回执没画在页上"


def test_controller_refuses_with_an_ai_marker_or_an_unlisted_command(qapp: QApplication) -> None:
    page, fake = _page(), FakeCli()
    agent = WorktreeController(page, Path("/nowhere"), lambda: None, runner=fake, markers=lambda: ("CLAUDECODE",))
    action = _view().rows[0].action
    assert action is not None
    agent.run(action)
    agent.preview_reclaim()
    _wait(agent, qapp)
    assert fake.calls == [] and all("未运行" in r.command for r in page.receipts[-2:])
    assert page.receipts[-1].output == decisions.human_only_block(("CLAUDECODE",))
    human = WorktreeController(page, Path("/nowhere"), lambda: None, runner=fake, markers=lambda: ())
    human.run(stations.Action("close", "收工位", "", ("worktree", "close", "x", "--force"), "x"))
    _wait(human, qapp)
    assert fake.calls == [] and page.receipts[-1].output == NOT_ALLOWED


def test_reclaim_lists_first_then_confirms_with_apply(qapp: QApplication) -> None:
    page = _page()
    fake = FakeCli("可回收 claude-aaaaaa：孤儿持有者记录：工位目录已不存在\n加 --apply 才会真的回收（先存救援引用，分支保留）\n")
    controller = WorktreeController(page, Path("/nowhere"), lambda: None, runner=fake, markers=lambda: ())
    controller.dialog_on_preview = False
    _buttons(page)["reclaim:"].click()
    _wait(controller, qapp)
    assert fake.calls == [["worktree", "reclaim", "--stale"]]  # 只列，什么都不动
    assert page.pending_reclaim is not None and page.pending_reclaim.args == ("worktree", "reclaim", "--stale", "--apply")
    assert page.pending_reclaim.facts == (("会清", "claude-aaaaaa：孤儿持有者记录：工位目录已不存在"),)
    empty = FakeCli("没有持有对话已不在的会话别名工位，也没有孤儿持有者记录\n")
    page.pending_reclaim = None
    other = WorktreeController(page, Path("/nowhere"), lambda: None, runner=empty, markers=lambda: ())
    other.preview_reclaim()
    _wait(other, qapp)
    assert page.pending_reclaim is None and page.receipts[-1].output == NOTHING_TO_RECLAIM


# ---------------------------------------------------------------- U-1：批准人放进确认框；撞车放行默认收起


def _target() -> decisions.Target:
    return decisions.Target(project_id="DJ-1", change_id="CHG-1", request_id="REQ-1", item_id="IN-1", mission_id="M-1",
                            plan_hash="h" * 64, ticket_hash="t" * 64, title="t")


def test_needs_approver_matches_where_build_args_passes_approver() -> None:
    now = datetime(2026, 11, 16, 14, 0)
    fill = {"reason": "r", "summary": "s", "as_owner": "claude:cloud", "note": "n", "verification_conclusion": "全部通过"}
    for decision in decisions.DECISIONS:
        for pin in (False, True):
            values = {f.key: fill.get(f.key, "x") for f in decision.fields if f.required}
            args = decisions.build_args(decision, _target(), values, approver="baiyang", pin_enforced=pin, now=now)
            assert ("--approver" in args) == decisions.needs_approver(decision, pin), (decision.key, pin)


def test_approver_box_is_in_the_dialog_prefilled_from_the_page(qapp: QApplication) -> None:
    def preview(decision: Any, target: Any, values: Any, approver: str, pin: bool) -> str:
        return str(decisions.shown_command(decisions.build_args(decision, target, values, approver=approver, pin_enforced=pin,
                                                            now=datetime(2026, 11, 16))))

    page = DecisionsPage(lambda _t: None, preview)
    page.approver_input.setText("baiyang")
    for key in ("approve_card", "inbox_confirm", "change_approve"):
        dialog = page.open_dialog(decisions.BY_KEY[key], _target(), run=False)
        assert isinstance(dialog, ConfirmDialog)
        assert dialog.inputs["approver"].text() == "baiyang", key
        assert "--approver baiyang" in dialog.command_label.text(), key
        dialog.inputs["approver"].setText("")
        assert not dialog.run_button.isEnabled() and "批准人" in dialog.problem.text(), key
        dialog.inputs["approver"].setText("白杨")
        assert '--approver "白杨"' in dialog.command_label.text() or "--approver 白杨" in dialog.command_label.text(), key
    closing = page.open_dialog(decisions.BY_KEY["close"], _target(), run=False)
    assert "approver" not in closing.inputs  # 不要批准人的按钮不放这一栏


def test_admission_release_is_folded_with_a_one_line_note(qapp: QApplication) -> None:
    page = DecisionsPage(lambda _t: None, lambda *a: "main.py pm approve")
    dialog = page.open_dialog(decisions.BY_KEY["approve_card"], _target(), run=False)
    box, toggle = dialog.inputs["admission_release_ref"], dialog.toggles["admission_release_ref"]
    assert box.isHidden() and toggle.text() == "展开"
    note = decisions.BY_KEY["approve_card"].fields[0].note
    assert note and note in [label.text() for label in dialog.findChildren(QLabel)]
    toggle.click()
    assert not box.isHidden() and toggle.text() == "收起"
    assert {"展开", "收起"} <= decisions.DECISION_BUTTONS


def test_the_clean_dialog_shows_the_sweep_verdict_with_the_kind_and_the_head() -> None:
    """G 工位止血（卡 280）：sweep 判可清的 detached 目录，确认框写明是门禁目录还是手工 detached 目录、HEAD 是哪个提交。"""
    said = "门禁目录，不在分支上（detached HEAD 84d472996970），这个提交已在 origin/main 上，目录干净，没有长任务在用"
    sweep = [dict(item, remove=True, reason=said) if str(item["target"]).endswith("/gate-manual") else item for item in SWEEP]
    gate = _row(_view(sweep=sweep), "gate-manual")
    assert gate.blocked == "" and gate.action is not None
    assert ("清理清单判词", said) in gate.action.facts
    formal = _row(_view(), "gate-formal").action
    assert formal is not None and ("清理清单判词", "已并进 main、干净") in formal.facts


# ---------------------------------------------------------------- AI 登记表（CHG-SCPT-2026-712）：“登记新 AI”和“注销”

REGISTRY = {
    "builtin": [{"name": name, "branch_prefix": prefix} for name, prefix in stations.ROSTER_PREFIX.items()],
    "registered": [{"name": "antigravity", "branch_prefix": "antigravity/", "status": "active", "registered_by": "baiyang",
                    "registered_at": "2026-11-17T13:00:00Z", "source_ref": "board"}],
}
REGISTRY_JSON = json.dumps(REGISTRY, ensure_ascii=False)


def test_registry_name_rule_is_the_same_as_the_cockpit_command() -> None:
    from auto_pm.application.core import agent_registry

    assert stations.AGENT_NAME.pattern == agent_registry.NAME.pattern


def test_registry_commands_are_on_the_policy_list_and_nothing_else_is() -> None:
    registered = REGISTRY["registered"][0]
    produced = [stations.registry_preview_args(), stations.register_action("kiro").args, stations.unregister_action(registered).args]
    assert produced == [("agent", "list", "--json"), ("agent", "register", "kiro", "--via", "board"), ("agent", "unregister", "antigravity")]
    assert all(stations.allowed_command(args) for args in produced)
    for bad in (("agent", "register", "kiro"), ("agent", "register", "kiro", "--via", "terminal"), ("agent", "register", "a b", "--via", "board"),
                ("agent", "register", "--via", "--via", "board"), ("agent", "unregister", "kiro", "--force"), ("agent", "list")):
        assert not stations.allowed_command(bad), bad
    assert {"登记新 AI", "注销"} <= policy.WORKTREE_BUTTONS


def test_registry_listing_is_read_back_or_said_unreadable() -> None:
    parsed = stations.parse_registry(REGISTRY_JSON)
    assert parsed is not None
    builtin, registered = parsed
    assert [b["name"] for b in builtin] == list(stations.ROSTER_PREFIX) and [r["name"] for r in registered] == ["antigravity"]
    for bad in ("", "不是 JSON", "[]", '{"builtin": [], "registered": {}}', '{"registered": []}'):
        assert stations.parse_registry(bad) is None, bad


def test_register_problem_says_what_is_wrong_before_the_command_runs() -> None:
    taken = ["claude", "antigravity"]
    assert stations.register_problem("kiro", taken) == ""
    assert stations.register_problem("", taken) == "先填名字"
    for bad in ("Kiro", "k", "kiro-1", "1kiro", "kiro ai", "a" * 21):
        assert "小写字母开头" in stations.register_problem(bad, taken), bad
    assert stations.register_problem("antigravity", taken) == "antigravity 已经在名册里了"
    assert stations.register_problem("claude", taken) == "claude 已经在名册里了"


def _registry_buttons(dialog: QDialog) -> dict[str, QPushButton]:
    return {str(b.property("registry_unregister")): b for b in dialog.findChildren(QPushButton) if b.property("registry_unregister")}


def test_the_register_button_is_on_the_page_and_grey_with_an_ai_marker(qapp: QApplication) -> None:
    assert _buttons(_page())["registry:"].isEnabled()
    assert not _buttons(_page(("CLAUDECODE",)))["registry:"].isEnabled()
    assert not _buttons(_page(None))["registry:"].isEnabled()  # 认不出带没带标记，也灰着


def test_the_register_dialog_lists_the_roster_and_only_runs_a_legal_new_name(qapp: QApplication) -> None:
    page = _page()
    dialog = page.open_registry(stations.parse_registry(REGISTRY_JSON), run=False)
    assert isinstance(dialog, RegistryDialog) and page.last_registry is dialog
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "claude" in texts and "antigravity · antigravity/ · 登记 baiyang" in texts
    assert set(_registry_buttons(dialog)) == {"antigravity"} and _registry_buttons(dialog)["antigravity"].isEnabled()
    assert not dialog.run_button.isEnabled() and dialog.problem.text() == "先填名字"
    assert dialog.command_label.text() == "main.py agent register <名字> --via board"
    for name, problem in (("claude", "claude 已经在名册里了"), ("antigravity", "antigravity 已经在名册里了"), ("Kiro", "小写字母开头")):
        dialog.name_input.setText(name)
        assert not dialog.run_button.isEnabled() and problem in dialog.problem.text(), name
    dialog.name_input.setText(" kiro ")
    assert dialog.run_button.isEnabled() and dialog.problem.text() == ""
    assert dialog.command_label.text() == "main.py agent register kiro --via board"
    dialog.run_button.click()
    assert dialog.chosen == stations.register_action("kiro")
    assert {b.text() for b in dialog.findChildren(QPushButton)} <= policy.WORKTREE_BUTTONS


def test_unregister_from_the_dialog_goes_through_a_second_confirm(qapp: QApplication) -> None:
    page = _page()
    dialog = page.open_registry(stations.parse_registry(REGISTRY_JSON), run=False)
    _registry_buttons(dialog)["antigravity"].click()
    chosen = dialog.chosen
    assert chosen is not None and chosen.key == "unregister" and chosen.args == ("agent", "unregister", "antigravity")
    confirm = page.open_dialog(chosen, run=False)
    assert isinstance(confirm, ActionDialog) and confirm.run_button.isEnabled()
    assert confirm.command_text == "main.py agent unregister antigravity"
    texts = " ".join(label.text() for label in confirm.findChildren(QLabel))
    assert "antigravity/" in texts and "baiyang，2026-11-17T13:00:00Z" in texts


def test_an_unreadable_roster_still_lets_the_user_register_and_says_so(qapp: QApplication) -> None:
    dialog = _page().open_registry(None, run=False)
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "读不懂" in texts and not _registry_buttons(dialog)
    dialog.name_input.setText("kiro")
    assert dialog.run_button.isEnabled()  # 判重交给命令自己


def test_with_an_ai_marker_the_register_dialog_cannot_register_or_unregister(qapp: QApplication) -> None:
    page = _page(("CLAUDECODE",))
    dialog = page.open_registry(stations.parse_registry(REGISTRY_JSON), run=False)
    assert dialog.blocked and not _registry_buttons(dialog)["antigravity"].isEnabled()
    dialog.name_input.setText("kiro")
    assert not dialog.run_button.isEnabled()
    dialog._register()
    dialog._choose(stations.unregister_action(REGISTRY["registered"][0]))
    assert dialog.chosen is None


def test_controller_lists_the_roster_first_then_runs_the_register_command(qapp: QApplication) -> None:
    page, changed = _page(), []
    fake = FakeCli(registry=REGISTRY_JSON)
    controller = WorktreeController(page, Path("/nowhere"), lambda: changed.append(1), runner=fake, markers=lambda: ())
    controller.dialog_on_preview = False
    _buttons(page)["registry:"].click()
    _wait(controller, qapp)
    assert fake.calls == [["agent", "list", "--json"]]  # 只读，什么都不动
    assert page.pending_registry == stations.parse_registry(REGISTRY_JSON)
    page.run_requested.emit(stations.register_action("kiro"))
    _wait(controller, qapp)
    assert fake.calls[-1] == ["agent", "register", "kiro", "--via", "board"] and changed == [1]
    assert page.receipts[-1].rc == 0


def test_controller_leaves_a_receipt_when_the_roster_cannot_be_listed(qapp: QApplication) -> None:
    page = _page()
    fake = FakeCli(registry_rc=2)
    controller = WorktreeController(page, Path("/nowhere"), lambda: None, runner=fake, markers=lambda: ())
    controller.dialog_on_preview = False
    controller.preview_registry()
    _wait(controller, qapp)
    assert fake.calls == [["agent", "list", "--json"]] and page.pending_registry is None
    assert page.receipts[-1].rc == 2


def test_controller_refuses_the_registry_with_an_ai_marker(qapp: QApplication) -> None:
    page, fake = _page(), FakeCli(registry=REGISTRY_JSON)
    agent = WorktreeController(page, Path("/nowhere"), lambda: None, runner=fake, markers=lambda: ("CLAUDECODE",))
    agent.preview_registry()
    agent.run(stations.register_action("kiro"))
    _wait(agent, qapp)
    assert fake.calls == [] and all("未运行" in r.command for r in page.receipts[-2:])
    assert page.receipts[-1].output == decisions.human_only_block(("CLAUDECODE",))


def test_running_receipt_is_replaced_when_command_finishes(qapp: QApplication) -> None:
    page = _page()
    action = stations.register_action("antigravity")
    page.add_receipt(actions.Receipt("20:49", action.label, stations.shown_command(action.args), None, False, RUNNING))
    assert RUNNING in [label.text() for label in page.findChildren(QLabel)]
    page.add_receipt(actions.Receipt("20:49", action.label, stations.shown_command(action.args), 0, False, "已登记 antigravity"))
    assert len(page.receipts) == 1 and page.receipts[0].rc == 0
    texts = [label.text() for label in page.findChildren(QLabel)]
    assert RUNNING not in texts and "已登记 antigravity" in texts


def test_page_shows_registered_ai_roster_from_ledger_and_refreshes_on_register(qapp: QApplication, tmp_path: Path) -> None:
    from auto_pm.infrastructure.continuity_store import AGENT_REGISTRY_DDL

    empty_page = WorktreesPage(tmp_path, lambda: (), lambda _text: None, lambda: NOW)
    empty_page.show_results("范围：本机控制根", _results())
    empty_texts = [label.text() for label in empty_page.findChildren(QLabel)]
    assert "已登记：还没有" in empty_texts
    assert any(text.startswith("内置：claude（claude/）") for text in empty_texts)

    db_path = tmp_path / ".auto-pm" / "continuity.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(AGENT_REGISTRY_DDL)
        conn.execute(
            "INSERT INTO agent_registry (name, branch_prefix, status, registered_by, registered_at, source_ref)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ("antigravity", "antigravity/", "active", "no-agent-marker", "2026-11-18T03:49:12Z", "board"),
        )
        conn.execute(
            "INSERT INTO agent_registry (name, branch_prefix, status, registered_by, registered_at, source_ref)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ("oldai", "oldai/", "retired", "no-agent-marker", "2026-11-17T00:00:00Z", "board"),
        )
        conn.commit()

    rows = stations.read_registered(tmp_path)
    assert [row["name"] for row in rows] == ["antigravity"]

    page = WorktreesPage(tmp_path, lambda: (), lambda _text: None, lambda: NOW)
    page.pending_registry = ([], [])
    fake = FakeCli(registry=REGISTRY_JSON)
    controller = WorktreeController(
        page, tmp_path, lambda: page.show_results("范围：本机控制根", _results()), runner=fake, markers=lambda: ()
    )
    page.show_results("范围：本机控制根", _results())
    assert "已登记：还没有" in [label.text() for label in page.findChildren(QLabel)]

    page.run_requested.emit(stations.register_action("antigravity"))
    _wait(controller, qapp)
    assert page.pending_registry is None
    assert "已登记：antigravity · antigravity/ · 登记 no-agent-marker，2026-11-18T03:49:12Z" in [
        label.text() for label in page.findChildren(QLabel)
    ]
    assert [r.rc for r in page.receipts] == [0]
