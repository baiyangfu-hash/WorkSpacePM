"""D-195: who is on this computer's control root.  Records are information only: nothing is refused, deleted or blocked here."""

from __future__ import annotations

import json
import os
import platform
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from auto_pm.application.core.station_presence import (
    SCHEMA,
    list_presence,
    orient_lines,
    record_presence,
)

DEAD_PID = 2_000_000_000
MARKERS = ("AUTO_PM_AGENT", "AUTO_PM_SESSION_ID", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "AUTO_PM_SESSION_TITLE")


@pytest.fixture(autouse=True)
def _as_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite may itself run inside an agent; every test starts as the user's own terminal."""

    for key in list(os.environ):
        if key in MARKERS or key.upper().startswith("CODEX_"):
            monkeypatch.delenv(key, raising=False)


def _agent(monkeypatch: pytest.MonkeyPatch, session: str = "abcdef0123456789", *, pid: int | None = None, base: str = "claude") -> None:
    monkeypatch.setenv("AUTO_PM_AGENT", base)
    monkeypatch.setenv("AUTO_PM_SESSION_ID", session)
    monkeypatch.setenv("CLAUDE_PID", str(os.getpid() if pid is None else pid))


def _write(root: Path, key: str, *, hours: float = 0.0, pid: int = DEAD_PID, machine: str | None = None, where: str = "control-root", alias: str = "") -> Path:
    stamp = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    path = root / ".auto-pm" / "presence" / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "key": key,
                "alias": alias or f"claude-{key[:6]}",
                "source": "claude",
                "machine": platform.node() if machine is None else machine,
                "pid": pid,
                "where": where,
                "title": "",
                "opened_at": stamp,
                "seen_at": stamp,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_an_agent_conversation_leaves_one_record_with_its_machine_source_and_place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _agent(monkeypatch)
    assert record_presence(tmp_path, cwd=tmp_path) is True
    (entry,) = list_presence(tmp_path)
    assert entry.alias == "claude-abcdef" and entry.source == "claude"
    assert entry.machine == platform.node() and entry.pid == os.getpid()
    assert entry.where == "control-root" and entry.verdict == "alive"


def test_the_users_own_terminal_and_unidentified_callers_leave_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert record_presence(tmp_path) is False
    monkeypatch.setenv("AUTO_PM_AGENT", "nobody-we-know")  # an agent marker the roster does not know
    assert record_presence(tmp_path) is False
    assert not (tmp_path / ".auto-pm").exists()


def test_a_user_terminal_that_happens_to_carry_a_session_id_is_still_not_a_conversation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_PM_SESSION_ID", "abcdef0123456789")  # no agent marker: the user's own terminal
    monkeypatch.setenv("CLAUDE_PID", str(os.getpid()))
    assert record_presence(tmp_path) is False
    assert not (tmp_path / ".auto-pm").exists()


@pytest.mark.parametrize(
    ("relative", "where"),
    [("", "control-root"), ("src/deep", "control-root"), (".auto-pm/worktrees/claude-abcdef", "station"), ("../elsewhere", "other")],
)
def test_the_place_is_the_station_the_control_root_or_somewhere_else(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str, where: str) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _agent(monkeypatch)
    cwd = (root / relative).resolve() if relative else root
    cwd.mkdir(parents=True, exist_ok=True)
    record_presence(root, cwd=cwd)
    assert list_presence(root)[0].where == where


def test_a_second_call_inside_the_interval_does_not_rewrite_but_keeps_the_first_opened_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _agent(monkeypatch)
    record_presence(tmp_path, min_interval_seconds=0)
    path = next((tmp_path / ".auto-pm" / "presence").glob("*.json"))
    first = path.read_text(encoding="utf-8")

    assert record_presence(tmp_path) is True  # default interval: nothing to do
    assert path.read_text(encoding="utf-8") == first

    assert record_presence(tmp_path, min_interval_seconds=0) is True  # forced refresh
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["opened_at"] == json.loads(first)["opened_at"] and after["seen_at"] >= json.loads(first)["seen_at"]


def test_two_conversations_are_two_records_and_each_sees_the_other(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _agent(monkeypatch, "aaaaaa111111")
    record_presence(tmp_path)
    _agent(monkeypatch, "bbbbbb222222", base="trae")
    record_presence(tmp_path)
    entries = list_presence(tmp_path)
    assert sorted(e.alias for e in entries) == ["claude-aaaaaa", "trae-bbbbbb"]
    assert orient_lines(tmp_path) and "claude-aaaaaa" in orient_lines(tmp_path)[0] and "trae-bbbbbb" not in orient_lines(tmp_path)[0]


@pytest.mark.parametrize(
    ("kwargs", "verdict"),
    [
        ({"hours": 0.0, "pid": DEAD_PID}, "alive"),
        ({"hours": 1.0, "pid": DEAD_PID}, "quiet"),
        ({"hours": 5.0, "pid": DEAD_PID}, "orphan"),
        ({"hours": 5.0, "pid": 0}, "orphan"),
        ({"hours": 5.0, "pid": os.getpid()}, "alive"),
        ({"hours": 5.0, "pid": DEAD_PID, "machine": "SOME-OTHER-PC"}, "elsewhere"),
    ],
)
def test_the_verdict_follows_the_process_and_the_silence_and_never_judges_another_computer(tmp_path: Path, kwargs: dict[str, object], verdict: str) -> None:
    _write(tmp_path, "k1", **kwargs)  # type: ignore[arg-type]
    (entry,) = list_presence(tmp_path)
    assert entry.verdict == verdict and entry.reason


def test_listing_never_deletes_even_a_suspected_orphan(tmp_path: Path) -> None:
    path = _write(tmp_path, "k1", hours=50.0)
    assert list_presence(tmp_path)[0].verdict == "orphan"
    assert path.exists()


def test_unreadable_and_foreign_files_are_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "good", hours=0.0)
    folder = tmp_path / ".auto-pm" / "presence"
    (folder / "broken.json").write_text("{not json", encoding="utf-8")
    (folder / "other.json").write_text(json.dumps({"schema": "something-else"}), encoding="utf-8")
    assert [e.key for e in list_presence(tmp_path)] == ["good"]


def test_orient_says_nothing_when_nobody_else_is_known_or_only_orphans_remain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert orient_lines(tmp_path) == ()
    _write(tmp_path, "gone", hours=50.0)
    assert orient_lines(tmp_path) == ()
    _agent(monkeypatch)
    record_presence(tmp_path)
    assert orient_lines(tmp_path) == ()  # only myself (and a suspected orphan)


def test_orient_counts_those_standing_on_the_control_root(tmp_path: Path) -> None:
    _write(tmp_path, "a1", hours=0.0, where="control-root", pid=os.getpid())
    _write(tmp_path, "b2", hours=0.0, where="station", pid=os.getpid())
    (line,) = orient_lines(tmp_path)
    assert "2 个会话在场" in line and "1 个站在控制根上" in line and "worktree who" in line


def test_a_record_that_cannot_be_written_is_not_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _agent(monkeypatch)
    (tmp_path / ".auto-pm").write_text("a file where the folder should be", encoding="utf-8")
    assert record_presence(tmp_path) is False
    assert list_presence(tmp_path) == []
    assert orient_lines(tmp_path) == ()
