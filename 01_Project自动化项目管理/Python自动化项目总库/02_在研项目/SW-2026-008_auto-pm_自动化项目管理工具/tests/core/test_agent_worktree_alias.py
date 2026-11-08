"""动态 agent 名：每个对话一个别名工位；对话结束时回收，回收前保住未提交的内容。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from auto_pm.application.core.agent_worktree_service import (
    AgentWorktreeError,
    AgentWorktreeService,
    StationRefusedError,
    acts_for,
    base_agent,
    session_alias,
)

SESSION = "b89bc814-eb30-4921-bfcc-9e54a1e1ec05"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def _control_root(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    root = tmp_path / "root"
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True, capture_output=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "t"), ("commit.gpgsign", "false")):
        _git(root, "config", key, value)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "c0")
    _git(root, "remote", "add", "origin", str(origin))
    _git(root, "push", "-q", "origin", "main")
    _git(root, "fetch", "-q", "origin")
    return root


def _service(root: Path) -> AgentWorktreeService:
    return AgentWorktreeService(root, run_state=lambda run_id: None)


@pytest.fixture
def as_user(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("AUTO_PM_AGENT", "AUTO_PM_SESSION_ID", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID"):
        monkeypatch.delenv(key, raising=False)
    for key in [name for name in __import__("os").environ if name.upper().startswith("CODEX_")]:
        monkeypatch.delenv(key, raising=False)


def test_alias_names_are_recognised_and_strangers_are_not() -> None:
    assert base_agent("claude") == "claude"
    assert base_agent("claude-b89bc8") == "claude"
    assert base_agent("trae-0a1b2c") == "trae"
    for bad in ("claude-b89bc", "claude-B89BC8", "claude-zzzzzz", "other-b89bc8", "claude-b89bc8x", ""):
        assert base_agent(bad) == ""


def test_the_alias_comes_from_the_session_id_and_is_empty_without_one() -> None:
    assert session_alias({"CLAUDE_CODE_SESSION_ID": SESSION}) == "claude-b89bc8"
    assert session_alias({}) == ""
    assert session_alias({"CLAUDE_CODE_SESSION_ID": "xyz"}).startswith("claude-")  # 不是十六进制就取哈希


def test_a_claude_conversation_acts_for_its_own_alias_but_not_for_anothers(
    monkeypatch: pytest.MonkeyPatch, as_user: None
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION)

    assert acts_for("claude", "claude-b89bc8")
    assert acts_for("claude", "claude")
    assert not acts_for("claude", "claude-aaaaaa")
    assert not acts_for("claude", "codex-b89bc8")
    assert not acts_for("?", "claude-b89bc8")
    assert acts_for("", "claude-aaaaaa")  # 用户自己的终端


def test_two_conversations_get_their_own_stations_and_cannot_close_each_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_user: None
) -> None:
    root = _control_root(tmp_path)
    service = _service(root)
    first = service.open("claude-aaaaaa", "card1", fetch=False)
    second = service.open("claude-bbbbbb", "card2", fetch=False)
    assert first.path.name == "claude-aaaaaa" and second.path.name == "claude-bbbbbb"
    assert first.branch == "claude/card1" and second.branch == "claude/card2"

    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "aaaaaa00-0000-0000-0000-000000000000")
    with pytest.raises(StationRefusedError, match="不能收"):
        service.close("claude-bbbbbb", fetch=False)
    with pytest.raises(StationRefusedError, match="不能回收"):
        service.release("claude-bbbbbb")


def test_release_saves_uncommitted_and_untracked_work_then_removes_the_directory_but_keeps_the_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_user: None
) -> None:
    root = _control_root(tmp_path)
    service = _service(root)
    station = service.open("claude-aaaaaa", "card1", fetch=False)
    (station.path / "a.txt").write_text("edited\n", encoding="utf-8")
    (station.path / "new.txt").write_text("brand new\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "aaaaaa00-0000-0000-0000-000000000000")

    result = service.release("claude-aaaaaa")

    assert not station.path.exists()
    assert "refs/heads/claude/card1" in _git(root, "for-each-ref", "--format=%(refname)")
    assert result.rescue_ref.startswith("refs/rescue/claude-aaaaaa/")
    assert _git(root, "show", f"{result.rescue_ref}:a.txt") == "edited\n"
    assert _git(root, "show", f"{result.rescue_ref}:new.txt") == "brand new\n"
    assert _git(root, "rev-parse", "claude/card1").strip() == _git(root, "rev-parse", f"{result.rescue_ref}^").strip()


def test_release_of_a_clean_station_makes_no_rescue_ref(tmp_path: Path, as_user: None) -> None:
    root = _control_root(tmp_path)
    service = _service(root)
    service.open("claude-aaaaaa", "card1", fetch=False)

    result = service.release("claude-aaaaaa")

    assert result.rescue_ref == ""
    assert "refs/rescue" not in _git(root, "for-each-ref", "--format=%(refname)")


def test_release_refuses_a_plain_roster_name(tmp_path: Path, as_user: None) -> None:
    root = _control_root(tmp_path)
    service = _service(root)
    service.open("claude", "card1", fetch=False)

    with pytest.raises(AgentWorktreeError, match="不是会话别名"):
        service.release("claude")


def _set_note(root: Path, name: str, **changes: object) -> None:
    path = root / ".auto-pm" / "station-holders" / f"{name}.json"
    note = json.loads(path.read_text(encoding="utf-8"))
    note.update(changes)
    path.write_text(json.dumps(note), encoding="utf-8")


def _hours_ago(hours: float) -> str:
    from datetime import UTC, datetime, timedelta

    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


DEAD_PID = 2_000_000_000  # 不会存在的进程号


def test_stale_needs_a_dead_holder_process_and_a_silent_heartbeat_at_the_same_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_user: None
) -> None:
    import os

    root = _control_root(tmp_path)
    service = _service(root)
    for name, card in (("claude-aaaaaa", "c1"), ("claude-bbbbbb", "c2"), ("claude-cccccc", "c3"), ("claude-dddddd", "c4")):
        service.open(name, card, fetch=False)
    _set_note(root, "claude-aaaaaa", pid=DEAD_PID, heartbeat_at=_hours_ago(5))  # 进程没了且久无心跳：陈旧
    _set_note(root, "claude-bbbbbb", pid=os.getpid(), heartbeat_at=_hours_ago(5))  # 长任务：心跳旧但进程活着，不回收
    _set_note(root, "claude-cccccc", pid=DEAD_PID, heartbeat_at=_hours_ago(0.1))  # 进程没了但心跳很新，再等等
    _set_note(root, "claude-dddddd", pid=DEAD_PID, heartbeat_at="not a time")  # 读不出心跳：证明不了，不回收

    listed = service.reclaim_stale(apply=False)
    assert [name for name, _ in listed] == ["claude-aaaaaa"]
    assert (root / ".auto-pm" / "worktrees" / "claude-aaaaaa").exists()

    monkeypatch.setenv("CLAUDECODE", "1")
    with pytest.raises(StationRefusedError, match="只由用户"):
        service.reclaim_stale(apply=True)
    monkeypatch.delenv("CLAUDECODE")

    service.reclaim_stale(apply=True)
    assert not (root / ".auto-pm" / "worktrees" / "claude-aaaaaa").exists()
    for kept in ("claude-bbbbbb", "claude-cccccc", "claude-dddddd"):
        assert (root / ".auto-pm" / "worktrees" / kept).exists()


def test_the_silence_threshold_is_configurable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_user: None) -> None:
    root = _control_root(tmp_path)
    service = _service(root)
    service.open("claude-aaaaaa", "c1", fetch=False)
    _set_note(root, "claude-aaaaaa", pid=DEAD_PID, heartbeat_at=_hours_ago(5))

    monkeypatch.setenv("AUTO_PM_STATION_STALE_HOURS", "8")
    assert service.reclaim_stale(apply=False) == []
    monkeypatch.setenv("AUTO_PM_STATION_STALE_HOURS", "1")
    assert [name for name, _ in service.reclaim_stale(apply=False)] == ["claude-aaaaaa"]


def test_touching_the_heartbeat_makes_a_silent_station_fresh_again(tmp_path: Path, as_user: None) -> None:
    root = _control_root(tmp_path)
    service = _service(root)
    service.open("claude-aaaaaa", "c1", fetch=False)
    _set_note(root, "claude-aaaaaa", pid=DEAD_PID, heartbeat_at=_hours_ago(5))
    assert service.stale_aliases()

    assert service.touch_heartbeat("claude-aaaaaa")

    assert service.stale_aliases() == []
    assert not service.touch_heartbeat("claude-eeeeee")  # 没有记录的工位什么都不做


def test_a_station_without_a_holder_note_is_never_called_stale(tmp_path: Path, as_user: None) -> None:
    root = _control_root(tmp_path)
    service = _service(root)
    service.open("claude-aaaaaa", "card1", fetch=False)
    (root / ".auto-pm" / "station-holders" / "claude-aaaaaa.json").unlink()

    assert service.reclaim_stale(apply=False) == []


# ── 不绑死 Claude：任何 agent 都能派生名字和回收 ─────────────────────────


@pytest.fixture
def as_codex(monkeypatch: pytest.MonkeyPatch, as_user: None) -> None:
    monkeypatch.setenv("AUTO_PM_AGENT", "codex")


def test_a_wrapper_can_set_its_own_session_id_and_base(monkeypatch: pytest.MonkeyPatch, as_codex: None) -> None:
    from auto_pm.application.core.agent_worktree_service import caller_alias

    monkeypatch.setenv("AUTO_PM_SESSION_ID", "my-wrapper-run-17")
    first = caller_alias()
    assert first.startswith("codex-") and base_agent(first) == "codex"
    assert caller_alias() == first  # 同一个会话 ID 永远同一个别名

    monkeypatch.setenv("AUTO_PM_SESSION_ID", "another-run")
    assert caller_alias() != first


def test_the_generic_session_id_wins_over_the_claude_one_and_the_base_comes_from_auto_pm_agent() -> None:
    env = {"AUTO_PM_SESSION_ID": "aaaaaa11-0000", "CLAUDE_CODE_SESSION_ID": "bbbbbb22-0000"}
    assert session_alias(env) == "claude-aaaaaa"
    assert session_alias({**env, "AUTO_PM_AGENT": "codex:cli"}) == "codex-aaaaaa"
    assert session_alias({**env, "AUTO_PM_AGENT": "nobody"}) == ""


def test_without_any_session_id_the_first_call_makes_one_and_remembers_it_per_parent_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_codex: None
) -> None:
    import os

    from auto_pm.application.core.agent_worktree_service import caller_alias, ensure_session_id

    root = _control_root(tmp_path)
    monkeypatch.setenv("AUTO_PM_SESSION_ID", "placeholder")
    monkeypatch.delenv("AUTO_PM_SESSION_ID")  # ensure_session_id 直接写 os.environ；这样收尾时 monkeypatch 会还原
    assert caller_alias() == ""
    ensure_session_id(root)
    first = caller_alias()
    assert first.startswith("codex-")

    monkeypatch.delenv("AUTO_PM_SESSION_ID")
    ensure_session_id(root)  # 同一个父进程的下一条命令
    assert caller_alias() == first
    assert (root / ".auto-pm" / "session-ids" / f"{os.getppid()}.txt").is_file()


def test_the_user_terminal_never_gets_a_generated_session_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_user: None) -> None:
    from auto_pm.application.core.agent_worktree_service import caller_alias, ensure_session_id

    ensure_session_id(_control_root(tmp_path))

    assert caller_alias() == ""


def test_a_codex_conversation_opens_and_releases_its_own_station_without_any_claude_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_codex: None
) -> None:
    from auto_pm.application.core.agent_worktree_service import caller_alias

    root = _control_root(tmp_path)
    service = _service(root)
    monkeypatch.setenv("AUTO_PM_SESSION_ID", "codex-run-1")
    mine = caller_alias()
    station = service.open(mine, "card1", fetch=False)
    assert station.branch == "codex/card1"
    (station.path / "note.txt").write_text("unsaved\n", encoding="utf-8")

    result = service.release(mine)

    assert not station.path.exists() and result.rescue_ref
    assert _git(root, "show", f"{result.rescue_ref}:note.txt") == "unsaved\n"


# --- D-76: without a declared CLAUDE_PID the holder pid is unknown (0) and the station is never "stale" ---------------


def test_without_claude_pid_the_holder_pid_is_unknown_and_the_station_is_never_reclaimed(tmp_path: Path, as_user: None) -> None:
    root = _control_root(tmp_path)
    service = _service(root)
    service.open("claude-aaaaaa", "c1", fetch=False)
    note = json.loads((root / ".auto-pm" / "station-holders" / "claude-aaaaaa.json").read_text(encoding="utf-8"))
    assert note["pid"] == 0  # not os.getppid(): that is usually a short-lived shell
    _set_note(root, "claude-aaaaaa", heartbeat_at=_hours_ago(50))

    assert service.stale_aliases() == []


def test_a_declared_claude_pid_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_user: None) -> None:
    root = _control_root(tmp_path)
    monkeypatch.setenv("CLAUDE_PID", "4242")
    _service(root).open("claude-aaaaaa", "c1", fetch=False)
    note = json.loads((root / ".auto-pm" / "station-holders" / "claude-aaaaaa.json").read_text(encoding="utf-8"))
    assert note["pid"] == 4242


# --- D-77: a reused parent pid is a new conversation; records of dead parents are removed --------------------------------


def _fresh_session(root: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    from auto_pm.application.core.agent_worktree_service import caller_alias, ensure_session_id

    monkeypatch.delenv("AUTO_PM_SESSION_ID", raising=False)
    ensure_session_id(root)
    return caller_alias()


def test_a_reused_parent_pid_gets_a_new_session_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_codex: None) -> None:
    from auto_pm.application.core import agent_worktree_service as module

    root = _control_root(tmp_path)
    monkeypatch.setattr(module, "_process_start_marker", lambda pid: "start-1")
    first = _fresh_session(root, monkeypatch)
    assert first.startswith("codex-")
    assert _fresh_session(root, monkeypatch) == first  # same process, same start time

    monkeypatch.setattr(module, "_process_start_marker", lambda pid: "start-2")  # the pid number was reused
    assert _fresh_session(root, monkeypatch) != first


def test_session_records_of_dead_parent_processes_are_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_codex: None) -> None:
    import os

    root = _control_root(tmp_path)
    folder = root / ".auto-pm" / "session-ids"
    folder.mkdir(parents=True)
    (folder / f"{DEAD_PID}.txt").write_text("deadbeef", encoding="utf-8")

    _fresh_session(root, monkeypatch)

    assert not (folder / f"{DEAD_PID}.txt").exists()
    assert (folder / f"{os.getppid()}.txt").is_file()


def test_the_start_marker_of_a_live_process_is_stable_and_a_missing_pid_has_none() -> None:
    import os

    from auto_pm.application.core.agent_worktree_service import _process_start_marker

    mine = _process_start_marker(os.getpid())
    assert mine == _process_start_marker(os.getpid())
    assert _process_start_marker(DEAD_PID) == ""


# --- D-87: a borrow record that names nobody on the roster is not a borrower -------------------------------------------


@pytest.mark.parametrize("name", ["evil", "claude-ZZZZZZ", "claude-12345", "", "../claude"])
def test_a_borrow_record_with_a_name_outside_the_roster_is_ignored(tmp_path: Path, as_user: None, name: str) -> None:
    root = _control_root(tmp_path)
    service = _service(root)
    service.open("claude", "c1", fetch=False)
    service._borrow_file("claude").write_text(json.dumps({"by": name, "branch": "claude/c1"}), encoding="utf-8")

    assert service.borrower("claude") == ""


def test_a_borrow_record_with_a_roster_name_is_honoured(tmp_path: Path, as_user: None) -> None:
    root = _control_root(tmp_path)
    service = _service(root)
    service.open("claude", "c1", fetch=False)
    service._borrow_file("claude").write_text(json.dumps({"by": "claude-b89bc8", "branch": "claude/c1"}), encoding="utf-8")

    assert service.borrower("claude") == "claude-b89bc8"
