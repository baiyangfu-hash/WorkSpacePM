"""D-112: a bare roster name from an agent with its own conversation alias means that conversation's own station.

Before: every Claude conversation passed ``claude`` and shared one station; whoever opened it first held it for days and a second
conversation could not open a PR from a different card (#607, #608).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from auto_pm.application.core.agent_worktree_service import AgentWorktreeService, caller_alias
from auto_pm.application.core.pr_open_service import PrOpenRefusedError, PrOpenService
from auto_pm.ui.cli.worktree import resolve_station_name
from tests.core.test_agent_worktree_alias import SESSION, _control_root, as_user  # noqa: F401 - fixture import

OTHER_SESSION = "0a1b2c3d-1111-2222-3333-444455556666"


def _as_claude(monkeypatch: pytest.MonkeyPatch, session: str = SESSION) -> str:
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", session)
    return caller_alias()


def _service(root: Path) -> AgentWorktreeService:
    return AgentWorktreeService(root, run_state=lambda run_id: None)


def test_opening_with_the_bare_name_goes_to_the_callers_own_alias_even_when_the_bare_station_is_taken(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    as_user: None,  # noqa: F811
) -> None:
    root = _control_root(tmp_path)
    service = _service(root)
    service.open(
        "claude", "DEFECT-REG-241", fetch=False
    )  # the other conversation, long-lived, under the shared name
    alias = _as_claude(monkeypatch)
    assert alias.startswith("claude-")
    name = resolve_station_name(service, "claude", opening=True)
    assert name == alias
    station = service.open(name, "d109", fetch=False)
    assert station.path.name == alias and station.branch == "claude/d109"
    assert (
        service.stations_dir / "claude"
    ).exists()  # the first conversation's station is untouched


def test_two_conversations_get_two_stations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_user: None
) -> None:  # noqa: F811
    service = _service(_control_root(tmp_path))
    first = (
        resolve_station_name(service, "claude", opening=True)
        if _as_claude(monkeypatch, SESSION)
        else ""
    )
    service.open(first, "c1", fetch=False)
    _as_claude(monkeypatch, OTHER_SESSION)
    second = resolve_station_name(service, "claude", opening=True)
    service.open(second, "c2", fetch=False)
    assert first != second and {p.name for p in service.stations_dir.iterdir()} == {first, second}


def test_non_opening_commands_use_the_alias_station_only_when_it_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    as_user: None,  # noqa: F811
) -> None:
    service = _service(_control_root(tmp_path))
    alias = _as_claude(monkeypatch)
    assert (
        resolve_station_name(service, "claude") == "claude"
    )  # no alias station yet: an older bare station keeps working
    service.open(alias, "c1", fetch=False)
    assert resolve_station_name(service, "claude") == alias


def test_nothing_changes_without_a_session_for_other_bases_or_for_an_explicit_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    as_user: None,  # noqa: F811
) -> None:
    service = _service(_control_root(tmp_path))
    assert (
        resolve_station_name(service, "claude", opening=True) == "claude"
    )  # the user's terminal: no alias
    alias = _as_claude(monkeypatch)
    assert resolve_station_name(service, "trae", opening=True) == "trae"
    assert resolve_station_name(service, alias, opening=True) == alias
    assert (
        resolve_station_name(service, "claude-ffffff", opening=True) == "claude-ffffff"
    )  # never someone else's alias


def test_pr_open_on_a_taken_bare_station_points_to_the_callers_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    as_user: None,  # noqa: F811
) -> None:
    root = _control_root(tmp_path)
    _service(root).open("claude", "DEFECT-REG-241", fetch=False)
    alias = _as_claude(monkeypatch)
    with pytest.raises(PrOpenRefusedError) as raised:
        PrOpenService(root).plan("claude", "d109", "card.md", fetch=False)
    assert alias in str(raised.value) and "worktree open" in str(raised.value)


def test_pr_open_hint_is_absent_for_a_user_terminal(tmp_path: Path, as_user: None) -> None:  # noqa: F811
    root = _control_root(tmp_path)
    _service(root).open("claude", "DEFECT-REG-241", fetch=False)
    with pytest.raises(PrOpenRefusedError) as raised:
        PrOpenService(root).plan("claude", "d109", "card.md", fetch=False)
    assert "worktree open" not in str(raised.value)
