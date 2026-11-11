"""骨架 D 的 7 个新页（CHG-SCPT-2026-628）：任务、要你出手、工作树与分支、发版、PR 与审计、脊柱图、命令与契约。

- 读命令的四页，每条命令四态都要画对：读到、读不懂、命令不存在（本机发布版太旧）、断网；
  没读到时不画要点，页面上不出现“0”或“读到了”，只出现三态标签之一。
- 没读到但有“上次读取”快照：要点用快照的，状态行写明是几分钟前的。
- 两页只读数据文件（spine.json、commands_map.json），坏文件写“读不懂”，不画空图。
- PR 与审计页用窗口的 GitHub 采集，读不到不画成“没有 PR”，也不拿缓存冒充现在。
- 新页上没有按钮（侧栏按钮除外）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QAbstractButton, QApplication, QLabel, QWidget  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cockpit_board"
sys.path.insert(0, str(SCRIPTS))

import github_collector as gh  # noqa: E402
from cockpit_board import actions, app, readers, shell, snapshot  # noqa: E402
from cockpit_board.widgets import (  # noqa: E402
    attention,
    commands,
    prs,
    release,
    spine,
    tasks,
    worktrees,
)
from cockpit_board.widgets import common as c  # noqa: E402

from tests.core import test_pm_dashboard as base  # noqa: E402 - 复用假工作空间
from tests.core import test_pm_dashboard_gui as gui_tests  # noqa: E402 - 复用窗口工厂

NOW = datetime(2026, 11, 11, 18, 0, tzinfo=UTC)
READ_PAGE_KEYS = ("attention", "tasks", "worktrees", "release")
NEW_PAGE_KEYS = (*READ_PAGE_KEYS, "prs", "spine", "commands")
# 读法 → 正常样本
SAMPLES = {
    "orient": "orient.json", "missions": "pm_missions.json", "pending": "pm_pending.json", "inbox": "pm_inbox.json",
    "worktree_list": "worktree_list.json", "worktree_sweep": "worktree_sweep.json", "long_run": "long_run_status.json",
}
MISSING = (FIXTURES / "stderr_missing_command.txt").read_text(encoding="utf-8")
OFFLINE = "fatal: unable to access 'https://github.com/x/y/': Could not resolve host: github.com\n"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _texts(widget: QWidget) -> list[str]:
    return [label.text() for label in widget.findChildren(QLabel)]


def _runner(mode: str, seen: list[list[str]] | None = None) -> Callable[..., subprocess.CompletedProcess[str]]:
    """假的 subprocess.run：ok 回真样本，garbage 回认不得的文字，missing 回“没有这条命令”，offline 回断网报错。"""

    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if seen is not None:
            seen.append(command)
        args = command[3:]  # [python, -B, main.py, ...]
        reader = next(r.reader for reads in shell.page_reads().values() for r in reads
                      if args[: len(r.command.split())] == r.command.split())
        if mode == "ok":
            return subprocess.CompletedProcess(command, 0, _fixture(SAMPLES[reader]), "")
        if mode == "garbage":
            return subprocess.CompletedProcess(command, 0, "这不是 JSON\n", "")
        if mode == "missing":
            return subprocess.CompletedProcess(command, 2, "", MISSING)
        return subprocess.CompletedProcess(command, 1, "", OFFLINE)

    return run


# ---- 页面登记 ------------------------------------------------------------------------------------


def test_new_pages_are_registered_and_reads_come_from_pages_json() -> None:
    keys = {p.key for p in shell.PAGES}
    assert set(NEW_PAGE_KEYS) <= keys
    declared = shell.page_reads()
    assert set(declared) == {"tasks", "prs", "worktrees", "release", "spine", "commands", "attention"}
    for key in READ_PAGE_KEYS:
        assert declared[key], key  # 读命令的页都声明了命令
        assert all(r.reader in readers.READERS for r in declared[key])
    for key in ("prs", "spine", "commands"):
        assert declared[key] == ()  # 这三页不起命令


def test_page_read_fills_in_the_project_and_splits_the_command() -> None:
    read = shell.PageRead("pm inbox list", ("--project-id", shell.PID), "inbox")
    assert read.needs_project
    assert read.argv("SW-2026-008") == ["pm", "inbox", "list", "--project-id", "SW-2026-008"]
    assert not shell.PageRead("worktree list", ("--json",), "worktree_list").needs_project


# ---- 读取状态（四态 + 没读 + 快照）----------------------------------------------------------------


def _outcome(mode: str, reader: str = "missions") -> actions.ReadOutcome:
    run = _runner(mode)
    read = next(r for reads in shell.page_reads().values() for r in reads if r.reader == reader)
    return actions.run_read(Path("/nowhere"), read.argv("SW-2026-008"), run)


@pytest.mark.parametrize(("mode", "state", "words"), [
    ("ok", "", "读到了"),
    ("garbage", "unreadable", "不是认得的格式"),
    ("missing", "unchecked", "本机发布版太旧"),
    ("offline", "offline", "断网"),
])
def test_read_state_four_ways(mode: str, state: str, words: str) -> None:
    outcome = _outcome(mode)
    parsed = readers.parse("missions", outcome.stdout) if outcome.kind == "ok" else None
    got_state, status = c.read_state(c.ReadResult("missions", "main.py pm missions", outcome, parsed))
    assert got_state == state
    assert words in status


def test_read_state_not_read_yet_and_skipped_are_unchecked() -> None:
    assert c.read_state(c.ReadResult("missions", "x"))[0] == "unchecked"
    state, status = c.read_state(c.ReadResult("missions", "x", skipped="没有受管项目"))
    assert state == "unchecked" and "没有受管项目" in status


@pytest.mark.parametrize("mode", ["garbage", "missing", "offline"])
def test_page_draws_no_values_and_no_zero_when_not_read(qapp: QApplication, mode: str) -> None:
    page = tasks.TasksPage()
    results = [c.ReadResult(r.reader, "main.py " + " ".join(r.argv("SW-2026-008")), _outcome(mode, r.reader),
                            readers.parse(r.reader, _outcome(mode, r.reader).stdout) if mode == "garbage" else None)
               for r in shell.page_reads()["tasks"]]
    page.show_results("项目：SW-2026-008", results)
    texts = _texts(page.reads.parentWidget())
    shown = [t for t in texts if t in c.STATES.values()]
    assert len(shown) == len(results)  # 每条命令一个三态标签
    assert "读到了" not in texts
    names = {name for name, _ in tasks.COLUMNS}
    assert not names & set(texts)  # 四栏的名字都不画（不画成“在干 没有”）
    assert not any(t.strip() == "0" or t.startswith("0 ") for t in texts)


def test_page_draws_values_when_read(qapp: QApplication) -> None:
    page = tasks.TasksPage()
    results = []
    for read in shell.page_reads()["tasks"]:
        outcome = _outcome("ok", read.reader)
        results.append(c.ReadResult(read.reader, "x", outcome, readers.parse(read.reader, outcome.stdout)))
    page.show_results("项目：SW-2026-008", results)
    texts = _texts(page)
    assert "读到了" in texts
    assert any(t.startswith("1 张：合成样本：GUI 骨架") for t in texts)  # 在干那一栏
    assert "SW-2026-008" in texts  # orient 的项目号
    assert not [t for t in texts if t in c.STATES.values()]


# ---- 后台读一页：快照 ----------------------------------------------------------------------------


def test_read_page_saves_a_snapshot_and_falls_back_to_it_when_offline(tmp_path: Path) -> None:
    reads = shell.page_reads()["tasks"]
    first = app.read_page(tmp_path, reads, "SW-2026-008", _runner("ok"), NOW)
    assert [r.outcome.kind for r in first] == ["ok", "ok"]
    saved = sorted(p.name for p in (tmp_path / snapshot.CACHE_RELATIVE).iterdir())
    assert saved == ["missions-sw-2026-008.json", "orient-sw-2026-008.json"]
    later = app.read_page(tmp_path, reads, "SW-2026-008", _runner("offline"), NOW + timedelta(minutes=5))
    for result in later:
        state, status = c.read_state(result)
        assert state == "offline"
        assert "上次读取：5 分钟前" in status
        assert c.shows_values(result)  # 要点用快照的


def test_read_page_does_not_snapshot_unreadable_output(tmp_path: Path) -> None:
    results = app.read_page(tmp_path, shell.page_reads()["release"], "", _runner("garbage"), NOW)
    assert c.read_state(results[0])[0] == "unreadable"
    assert not (tmp_path / snapshot.CACHE_RELATIVE).exists()


def test_read_page_without_a_project_skips_project_commands(tmp_path: Path) -> None:
    seen: list[list[str]] = []
    results = app.read_page(tmp_path, shell.page_reads()["attention"], "", _runner("ok", seen), NOW)
    assert seen == []
    assert all(c.read_state(r)[0] == "unchecked" and r.skipped for r in results)
    # 不要项目号的命令照读
    results = app.read_page(tmp_path, shell.page_reads()["worktrees"], "", _runner("ok", seen), NOW)
    assert [r.outcome.kind for r in results] == ["ok", "ok"]
    assert all("--apply" not in command for command in seen)  # 清理只列，不带写开关


def test_read_page_turns_a_crash_into_a_line(tmp_path: Path) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("坏了")

    results = app.read_page(tmp_path, shell.page_reads()["release"], "", boom, NOW)
    assert c.read_state(results[0]) == ("unchecked", "没读：读的时候出错：RuntimeError: 坏了")


# ---- 各页的要点 ----------------------------------------------------------------------------------


def _data(reader: str) -> dict[str, Any]:
    parsed = readers.parse(reader, _fixture(SAMPLES[reader]))
    assert parsed.ok
    data: dict[str, Any] = parsed.data
    return data


def test_attention_lists_what_waits_for_you() -> None:
    assert attention.summarize("pending", _data("pending")) == [("等你批准的范围卡", "没有")]
    rows = attention.summarize("inbox", {"items": [{"item_id": "IN-1", "title": "加急：换传感器", "status": "proposed"},
                                                   {"item_id": "IN-2", "title": "已确认", "status": "CONFIRMED"}]})
    assert rows == [("等你确认的收件箱条目", "1 条"), ("收件箱一共", "2 条"), ("IN-1", "加急：换传感器")]
    rows = attention.summarize("pending", {"cards": [{"objective": "改报警", "card": {"request_id": "REQ-9"}},
                                                     {"objective": "旧的", "superseded": True, "card": {}}]})
    assert rows == [("等你批准的范围卡", "1 张"), ("REQ-9", "改报警")]


def test_worktrees_say_unchecked_for_null_fields_and_list_sweep_items() -> None:
    rows = worktrees.summarize("worktree_list", _data("worktree_list"))
    assert rows[0] == ("工位", "1 个")
    assert rows[1][0] == "claude-fc1e6b" and "改动和推送没检查" in rows[1][1]
    checked = worktrees.summarize("worktree_list", {"stations": [
        {"name": "trae", "branch": "trae/1", "checked": True, "dirty": 2, "unpushed": False, "merged": None}]})
    assert checked[1] == ("trae", "trae/1 · 有未提交 2 · 都已推送 · 没检查")
    sweep = worktrees.summarize("worktree_sweep", _data("worktree_sweep"))
    assert sweep[0] == ("可清理", "3 项（只列出，没清）")
    assert sweep[1] == ("claude/628a-gui-shell", "gone-branch · 远程已删且已并进 main，删本地分支")
    assert worktrees.summarize("worktree_list", {"stations": []}) == [("工位", "没有")]


def test_release_lists_long_running_tasks() -> None:
    rows = release.summarize("long_run", _data("long_run"))
    assert rows[0] == ("长任务", "2 个")
    assert rows[1] == ("gate-full", "在跑 · 开始于 2026-11-11T12:00:00+00:00")
    assert rows[2] == ("old", "读不懂 · status.json 读不出")


def test_tasks_orient_rows() -> None:
    rows = dict(tasks.summarize("orient", _data("orient")))
    assert rows["项目"] == "SW-2026-008"
    assert rows["焦点卡"] == "没有焦点卡"


# ---- 只读数据文件的两页 --------------------------------------------------------------------------


def test_spine_page_draws_ten_steps_and_the_off_spine_case(qapp: QApplication) -> None:
    data = spine.load()
    assert data is not None
    blocks = spine.step_rows(data)
    assert [title for title, _ in blocks[:10]] == [f"第 {s['n']} 步 · {s['name']}" for s in data["steps"]]
    assert len(blocks) == 10 + len(data["off_spine"])
    step3 = dict(blocks[2][1])
    assert step3["要你出手"] == "确认计划"
    assert "任务" in dict(blocks[0][1])["在哪页看"]  # 页键换成了侧栏上的字
    page = spine.SpinePage()
    assert "第 1 步 · 进门定位" in _texts(page)


def test_commands_page_counts_match_the_map(qapp: QApplication) -> None:
    data = commands.load()
    assert data is not None
    groups = commands.grouped(data)
    assert {key: len(rows) for key, rows in groups.items() if rows} == data["counts"]
    assert all(note for name, note in groups["never"])
    assert any("--fix" in note for name, note in groups["read"])  # 只读命令的写开关写明了
    page = commands.CommandsPage()
    assert f"只读（{data['counts']['read']} 条）" in _texts(page)


@pytest.mark.parametrize("make", [spine.SpinePage, commands.CommandsPage])
def test_data_pages_say_unreadable_for_a_bad_file(qapp: QApplication, tmp_path: Path, make: Callable[[Path], QWidget]) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{不是 JSON", encoding="utf-8")
    page = make(bad)
    texts = _texts(page)
    assert "读不懂" in texts
    assert not any(t.startswith("第 1 步") or t.startswith("只读（") for t in texts)


# ---- PR 与审计 -----------------------------------------------------------------------------------


def _snapshot(state: str, from_cache: bool = False, pulls: int = 1) -> gh.Snapshot:
    pull = gh.PullInfo(number=758, title="GUI C", url="https://example.invalid/758", author="me", head_sha="80c0b932",
                       head_ref="claude/628c-gui-contracts", draft=True, updated_at="2026-11-11T18:00:00Z")
    return gh.Snapshot("o/r", state, NOW, NOW - timedelta(hours=1) if from_cache else None, from_cache=from_cache,
                       pulls=[pull] * pulls)


def test_prs_page_states(qapp: QApplication) -> None:
    page = prs.PrsPage()
    assert page.state == "unchecked"
    page.show_github(None, disabled=True)
    assert "按 --no-github 启动，没读 GitHub" in _texts(page)
    page.show_github(_snapshot("offline"), disabled=False)
    assert page.state == "offline"
    assert "开着的 PR" not in _texts(page)  # 从没读到过：不画成“没有 PR”
    page.show_github(_snapshot("offline", from_cache=True), disabled=False)
    assert page.state == "offline" and "#758" not in _texts(page)  # 缓存不拿来冒充现在
    assert any("缓存截至" in t for t in _texts(page))
    page.show_github(_snapshot("ok"), disabled=False)
    assert page.state == "" and "读到了" in _texts(page)
    assert "草稿 · GUI C · claude/628c-gui-contracts" in _texts(page)
    page.show_github(_snapshot("ok", pulls=0), disabled=False)
    assert ("开着的 PR", "没有") == prs.pull_rows(_snapshot("ok", pulls=0))[0]


# ---- 接进窗口 ------------------------------------------------------------------------------------


def _wait(qapp: QApplication, window: Any) -> None:
    deadline = datetime.now(UTC) + timedelta(seconds=20)
    while window._reading_pages and datetime.now(UTC) < deadline:
        qapp.processEvents()
    for thread in list(window._threads):
        thread.wait(5000)
    qapp.processEvents()
    assert not window._reading_pages


def test_opening_a_read_page_reads_its_commands_in_the_background(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    seen: list[list[str]] = []
    window = gui_tests._window(qapp, root, db, read_runner=_runner("ok", seen))
    window._refresh_decisions = lambda: None
    for key in READ_PAGE_KEYS:
        window.sidebar.buttons[key].click()
        _wait(qapp, window)
        page = window.read_pages[key]
        assert page.results and all(c.read_state(r)[0] == "" for r in page.results), key
        assert "正在读" not in page.project_line.text()
    asked = [command[3:] for command in seen]
    assert ["pm", "missions", "--pid", "DJ-2026-101"] in asked  # 工程工位默认项目
    assert ["worktree", "sweep", "--json", "--no-fetch"] in asked
    # 打开没有命令的页不起命令
    before = len(seen)
    for key in ("prs", "spine", "commands"):
        window.sidebar.buttons[key].click()
    assert len(seen) == before
    window.close()


def test_read_page_offline_in_the_window_shows_the_state_tag(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = gui_tests._window(qapp, root, db, read_runner=_runner("missing"))
    window.goto("release")
    _wait(qapp, window)
    texts = _texts(window.release)
    assert "没检查" in texts
    assert any("本机发布版太旧" in t for t in texts)
    window.close()


def test_new_pages_have_no_buttons(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = gui_tests._window(qapp, root, db, read_runner=_runner("ok"))
    for key in NEW_PAGE_KEYS:
        window.goto(key)
        _wait(qapp, window)
        assert not window.router.pages[key].findChildren(QAbstractButton), key
    window.close()


# ---- 顶上一行总状态：空态、错态文案（CHG-SCPT-2026-637）------------------------------------------

TEXTS = shell.page_texts()  # 文案从 pages.json 读，不在测试里写死
PAGE_CLASSES: dict[str, Callable[[], c.ReadPage]] = {
    "tasks": tasks.TasksPage, "attention": attention.AttentionPage,
    "worktrees": worktrees.WorktreesPage, "release": release.ReleasePage,
}
# 每页“读到且空”的数据（读法 → 数据）；没列的读法用正常样本
EMPTY_DATA: dict[str, dict[str, Any]] = {
    "missions": {"active": [], "waiting": [], "parked": [], "closed": [{"mission_id": "M-1", "title": "旧卡"}]},
    "pending": {"cards": [{"objective": "旧的", "superseded": True, "card": {}}]},
    "inbox": {"items": [{"item_id": "IN-2", "title": "已确认", "status": "CONFIRMED"}]},
    "worktree_list": {"stations": []},
    "long_run": {"tasks": [{"name": "old", "state": "DONE", "exit_code": 0}]},
}
FULL_DATA: dict[str, dict[str, Any]] = {
    "missions": {"active": [{"mission_id": "M-2", "title": "在干的卡"}], "waiting": [], "parked": [], "closed": []},
    "pending": {"cards": [{"objective": "改报警", "card": {"request_id": "REQ-9"}}]},
    "inbox": {"items": [{"item_id": "IN-1", "title": "换传感器", "status": "PROPOSED"}]},
    "worktree_list": {"stations": [{"name": "trae", "branch": "trae/1", "checked": False}]},
    "long_run": {"tasks": [{"name": "gate-full", "state": "RUNNING"}]},
}


class _Parsed:
    def __init__(self, data: dict[str, Any]) -> None:
        self.ok, self.data, self.note = True, data, ""


def _ok(reader: str, data: dict[str, Any] | None) -> c.ReadResult:
    outcome = _outcome("ok", reader)
    parsed: Any = _Parsed(data) if data is not None else readers.parse(reader, outcome.stdout)
    return c.ReadResult(reader, "x", outcome, parsed)


def _results(key: str, fill: dict[str, dict[str, Any]], broken: str = "", mode: str = "offline") -> list[c.ReadResult]:
    out = []
    for read in shell.page_reads()[key]:
        if read.reader == broken:
            outcome = _outcome(mode, read.reader)
            parsed = readers.parse(read.reader, outcome.stdout) if mode == "garbage" else None
            out.append(c.ReadResult(read.reader, "x", outcome, parsed))
        else:
            out.append(_ok(read.reader, fill.get(read.reader)))
    return out


def _top(page: QWidget) -> list[str]:
    """顶上那一行总状态的字（没有就是空列表）。"""
    for frame in page.findChildren(QWidget):
        if frame.property("pagestatus") == "true":
            return _texts(frame)
    return []


@pytest.mark.parametrize("key", READ_PAGE_KEYS)
def test_read_page_top_line_empty_full_and_errors(qapp: QApplication, key: str) -> None:
    empty_text, error_text = TEXTS[key]
    page = PAGE_CLASSES[key]()
    page.show_results("x", _results(key, EMPTY_DATA))
    assert page.status == ("empty", "") and _top(page) == [empty_text]  # 空态不配三态标签
    page.show_results("x", _results(key, FULL_DATA))
    assert page.status == ("", "") and _top(page) == []
    first = shell.page_reads()[key][0].reader
    for mode, state in (("offline", "offline"), ("missing", "unchecked"), ("garbage", "unreadable")):
        page.show_results("x", _results(key, EMPTY_DATA, broken=first, mode=mode))
        assert page.status == ("error", state), mode
        assert _top(page) == [c.STATES[state], error_text], mode


@pytest.mark.parametrize(("key", "reader"), [("tasks", "orient"), ("worktrees", "worktree_sweep")])
def test_commands_that_do_not_judge_empty_still_raise_the_error_line(qapp: QApplication, key: str, reader: str) -> None:
    """进门定位、清理清单不参与判空（读法 A），但它们读不到时照样算没读到，顶上画错态。"""
    page = PAGE_CLASSES[key]()
    page.show_results("x", _results(key, EMPTY_DATA))
    assert page.status == ("empty", "")  # 它们读到了也不挡空态
    page.show_results("x", _results(key, EMPTY_DATA, broken=reader, mode="offline"))
    assert page.status == ("error", "offline")
    assert _top(page) == [c.STATES["offline"], TEXTS[key][1]]


def test_snapshot_fallback_draws_the_error_line_not_the_empty_line(qapp: QApplication, tmp_path: Path) -> None:
    reads = shell.page_reads()["release"]
    app.read_page(tmp_path, reads, "", _runner("ok"), NOW)
    later = app.read_page(tmp_path, reads, "", _runner("offline"), NOW + timedelta(minutes=5))
    assert c.shows_values(later[0])  # 有快照
    page = release.ReleasePage()
    page.show_results("x", later)
    assert page.status == ("error", "offline")
    assert TEXTS["release"][0] not in _texts(page)
    assert _top(page) == [c.STATES["offline"], TEXTS["release"][1]]


def test_page_status_order_offline_then_unreadable_then_unchecked() -> None:
    def res(mode: str) -> c.ReadResult:
        outcome = _outcome(mode)
        return c.ReadResult("missions", "x", outcome, readers.parse("missions", outcome.stdout) if mode == "garbage" else None)

    def never(_reader: str, _data: dict[str, Any]) -> bool | None:
        return None

    assert c.page_status([res("missing"), res("garbage"), res("offline")], never) == ("error", "offline")
    assert c.page_status([res("missing"), res("garbage")], never) == ("error", "unreadable")
    assert c.page_status([res("missing"), c.ReadResult("missions", "x", skipped="没项目")], never) == ("error", "unchecked")
    assert c.page_status([_ok("missions", None)], never) == ("", "")  # 没有一条参与判空：不画空态
    assert c.page_status([], never) == ("", "")


def test_prs_page_top_line(qapp: QApplication) -> None:
    empty_text, error_text = TEXTS["prs"]
    page = prs.PrsPage()
    page.show_github(_snapshot("ok", pulls=0), disabled=False)
    assert page.status == ("empty", "") and _top(page) == [empty_text]
    page.show_github(_snapshot("offline"), disabled=False)
    assert page.status == ("error", "offline") and _top(page) == [c.STATES["offline"], error_text]
    page.show_github(_snapshot("offline", from_cache=True), disabled=False)
    assert _top(page) == [c.STATES["offline"], error_text]
    assert "#758" not in _texts(page)  # 有缓存照样不列 PR
    page.show_github(_snapshot("ok"), disabled=False)
    assert page.status == ("", "") and _top(page) == []
    page.show_github(None, disabled=True)
    assert page.status == ("", "") and _top(page) == []  # 其他读不到的保持原来的说明


@pytest.mark.parametrize(("make", "key"), [(spine.SpinePage, "spine"), (commands.CommandsPage, "commands")])
def test_data_pages_use_the_pages_json_error_text(qapp: QApplication, tmp_path: Path, make: Callable[[Path], QWidget], key: str) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{不是 JSON", encoding="utf-8")
    assert TEXTS[key][1] in _texts(make(bad))


# ---- CHG-SCPT-2026-639：“要你出手”“决定”两页读哪些项目 ------------------------------------------------------


ASK_TABLES = """
CREATE TABLE planning_drafts (request_id TEXT PRIMARY KEY, subject_project_id TEXT, objective TEXT);
CREATE TABLE planning_scope_cards (request_id TEXT, revision INTEGER, created_at TEXT);
CREATE TABLE planning_draft_decision_bindings (request_id TEXT PRIMARY KEY);
"""


def _with_pending_card(db: Path, project: str, request_id: str = "REQ-ASK-PAGES") -> None:
    """在假账本里放一张等批准的范围卡（只建看板读的几列），它所在的项目没有任何 Mission。"""
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(db)) as conn, conn:
        conn.executescript(ASK_TABLES)
        conn.execute("INSERT INTO planning_drafts VALUES (?, ?, ?)", (request_id, project, "只有范围卡的项目"))
        conn.execute("INSERT INTO planning_scope_cards VALUES (?, 1, ?)", (request_id, NOW.isoformat()))


def test_read_pages_reads_every_project_in_turn(tmp_path: Path) -> None:
    seen: list[list[str]] = []
    reads = shell.page_reads()["attention"]
    results = app.read_pages(tmp_path, reads, ["DJ-2026-101", "SW-2026-008"], _runner("ok", seen), NOW)
    assert len(results) == 2 * len(reads) and all(c.read_state(r)[0] == "" for r in results)
    asked = [command[3:] for command in seen]
    for pid in ("DJ-2026-101", "SW-2026-008"):
        assert ["pm", "pending", "--project-id", pid] in asked and ["pm", "inbox", "list", "--project-id", pid] in asked
    # 没有项目时照旧读一次，写明没读
    seen.clear()
    assert all(r.skipped for r in app.read_pages(tmp_path, reads, [], _runner("ok", seen), NOW)) and seen == []


def test_ask_project_ids_station_then_asks_then_open_cards(tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    _with_pending_card(db, "SW-2026-008")
    board = base.pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    assert app.ask_project_ids(board, "DJ-2026-101") == ["DJ-2026-101", "SW-2026-008"]
    assert app.ask_project_ids(board, "") == ["SW-2026-008", "DJ-2026-101"]  # 默认项目是空的也找得到
    assert app.ask_project_ids(board, "SW-2026-008") == ["SW-2026-008", "DJ-2026-101"]  # 去重
    assert app.ask_project_ids(board, "DJ-2026-101", limit=1) == ["DJ-2026-101"]
    assert app.ask_project_ids(None, "") == []


@pytest.mark.parametrize("station", ["DJ-2026-101", ""])
def test_attention_page_reads_the_project_that_has_the_card(qapp: QApplication, tmp_path: Path, station: str) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    _with_pending_card(db, "SW-2026-008")
    seen: list[list[str]] = []
    window = gui_tests._window(qapp, root, db, read_runner=_runner("ok", seen))
    window._refresh_decisions = lambda: None
    window.options.station_project = station
    window.sidebar.buttons["attention"].click()
    _wait(qapp, window)
    asked = [command[3:] for command in seen]
    assert ["pm", "pending", "--project-id", "SW-2026-008"] in asked
    assert ["pm", "inbox", "list", "--project-id", "DJ-2026-101"] in asked  # 有开着的卡的项目也读
    line = window.read_pages["attention"].project_line.text()
    assert "SW-2026-008" in line and "DJ-2026-101" in line
    window.close()


def test_decisions_page_reads_a_project_that_only_has_a_pending_card(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    _with_pending_card(db, "SW-2026-008")
    window = gui_tests._window(qapp, root, db, read_runner=_runner("ok"))
    asked: list[list[str]] = []
    window.decisions.refresh = lambda project_ids, _missions: asked.append(list(project_ids))
    window._refresh_decisions()
    assert asked and "SW-2026-008" in asked[-1] and "DJ-2026-101" in asked[-1]
    window.close()
