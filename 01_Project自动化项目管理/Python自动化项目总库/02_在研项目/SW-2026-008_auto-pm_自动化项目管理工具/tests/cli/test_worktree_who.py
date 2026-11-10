"""D-195: ``worktree who`` lists who is on this computer's control root; any worktree command of an agent registers it."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from auto_pm.application.core.station_presence import SCHEMA
from auto_pm.ui.cli.__main__ import cli

MARKERS = ("AUTO_PM_AGENT", "AUTO_PM_SESSION_ID", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for key in list(os.environ):
        if key in MARKERS or key.upper().startswith("CODEX_"):
            monkeypatch.delenv(key, raising=False)
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    control = tmp_path / "root"
    subprocess.run(["git", "init", "-q", "-b", "main", str(control)], check=True, capture_output=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "t"), ("commit.gpgsign", "false")):
        _git(control, "config", key, value)
    (control / "a.txt").write_text("a\n", encoding="utf-8")
    _git(control, "add", ".")
    _git(control, "commit", "-qm", "c0")
    _git(control, "remote", "add", "origin", str(origin))
    _git(control, "push", "-q", "origin", "main")
    _git(control, "fetch", "-q", "origin")
    return control


def _who(root: Path, *args: str, env: dict[str, str] | None = None) -> Result:
    return CliRunner(env=env).invoke(cli, ["--workspace", str(root), "worktree", "who", *args])


def _records(root: Path) -> list[dict[str, Any]]:
    folder = root / ".auto-pm" / "presence"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))] if folder.is_dir() else []


def test_the_users_terminal_sees_an_empty_list_and_registers_nothing(root: Path) -> None:
    result = _who(root)
    assert result.exit_code == 0, result.output
    assert "没有在场登记" in result.output
    assert _records(root) == []
    assert json.loads(_who(root, "--json").output) == []


def test_an_agent_running_who_registers_itself_and_sees_itself_marked(root: Path) -> None:
    env = {"AUTO_PM_AGENT": "claude", "AUTO_PM_SESSION_ID": "abcdef0123456789", "CLAUDE_PID": str(os.getpid())}
    result = _who(root, env=env)
    assert result.exit_code == 0, result.output
    assert "claude-abcdef" in result.output and "（你）" in result.output
    (record,) = _records(root)
    assert record["schema"] == SCHEMA and record["source"] == "claude" and record["where"] in {"control-root", "other"}


def test_another_conversation_shows_up_with_its_source_and_a_suspected_orphan_is_only_marked(root: Path) -> None:
    folder = root / ".auto-pm" / "presence"
    folder.mkdir(parents=True)
    old = "2020-01-01T00:00:00+00:00"
    import platform

    (folder / "zzz.json").write_text(
        json.dumps({"schema": SCHEMA, "key": "zzz", "alias": "trae-123456", "source": "trae", "machine": platform.node(), "pid": 0,
                    "where": "control-root", "title": "", "opened_at": old, "seen_at": old}),
        encoding="utf-8",
    )
    result = _who(root, "--json")
    (entry,) = json.loads(result.output)
    assert entry["alias"] == "trae-123456" and entry["verdict"] == "orphan" and entry["source"] == "trae"
    text = _who(root).output
    assert "trae-123456" in text and "疑似孤儿" in text and "不会自动删除" in text
    assert (folder / "zzz.json").exists()


def test_any_worktree_command_of_an_agent_registers_it_so_who_from_a_second_window_sees_both(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("auto_pm.ui.cli.worktree.require_runtime_identity_for_workspace", lambda _ctx: None)
    first = {"AUTO_PM_AGENT": "claude", "AUTO_PM_SESSION_ID": "aaaaaa111111", "CLAUDE_PID": str(os.getpid())}
    second = {"AUTO_PM_AGENT": "trae", "AUTO_PM_SESSION_ID": "bbbbbb222222", "CLAUDE_PID": str(os.getpid())}
    listed = CliRunner(env=first).invoke(cli, ["--workspace", str(root), "worktree", "list"])
    assert listed.exit_code == 0, listed.output
    seen = json.loads(_who(root, "--json", env=second).output)
    assert sorted(e["alias"] for e in seen) == ["claude-aaaaaa", "trae-bbbbbb"]
    assert {e["verdict"] for e in seen} == {"alive"}


def test_who_is_listed_in_the_group_help(root: Path) -> None:
    result = CliRunner().invoke(cli, ["--workspace", str(root), "worktree", "--help"])
    assert "who" in result.output
