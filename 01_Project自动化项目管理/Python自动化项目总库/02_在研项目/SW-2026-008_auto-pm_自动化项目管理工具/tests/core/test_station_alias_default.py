"""D-112: a bare roster name from an agent with its own conversation alias means that conversation's own station.

Before: every Claude conversation passed ``claude`` and shared one station; whoever opened it first held it for days and a second
conversation could not open a PR from a different card (#607, #608).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.application.core.agent_worktree_service import AgentWorktreeService, caller_alias
from auto_pm.application.core.pr_open_service import PrOpenRefusedError, PrOpenService
from auto_pm.ui.cli.claim import _owner
from auto_pm.ui.cli.worktree import resolve_station_name, shared_station_refusal
from tests.core.test_agent_worktree_alias import (  # noqa: F401 - fixture import
    SESSION,
    _control_root,
    as_user,
)

pytestmark = pytest.mark.usefixtures("as_user")

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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
) -> None:
    root = _control_root(tmp_path)
    _service(root).open("claude", "DEFECT-REG-241", fetch=False)
    alias = _as_claude(monkeypatch)
    with pytest.raises(PrOpenRefusedError) as raised:
        PrOpenService(root).plan("claude", "d109", "card.md", fetch=False)
    assert alias in str(raised.value) and "worktree open" in str(raised.value)


def test_pr_open_hint_is_absent_for_a_user_terminal(tmp_path: Path) -> None:
    root = _control_root(tmp_path)
    _service(root).open("claude", "DEFECT-REG-241", fetch=False)
    with pytest.raises(PrOpenRefusedError) as raised:
        PrOpenService(root).plan("claude", "d109", "card.md", fetch=False)
    assert "worktree open" not in str(raised.value)


# ── claim identity follows the alias (D-112, found on the 11-07 deployment: claimed as `claude`, PR refused for `claude-a119dc`) ──


def test_pr_open_refuses_a_bare_name_claim_for_an_alias_station(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counterexample: another conversation of the same agent holds the bare-name claim; the alias station must not ride on it."""

    from auto_pm.application.core import pr_open_service

    root = _control_root(tmp_path)
    alias = _as_claude(monkeypatch)
    _service(root).open(alias, "c1", fetch=False)
    seen: list[str] = []

    def fake(_root: object, _card: str, owner: str) -> str:
        seen.append(owner)
        return "" if owner == "claude" else f"占位不是 {owner}"

    monkeypatch.setattr(pr_open_service, "claim_refusal", fake)
    with pytest.raises(PrOpenRefusedError, match="占位不是"):
        PrOpenService(root).plan(alias, "c1", "card.md", fetch=False)
    assert seen == [alias]


def test_pr_open_refuses_when_the_claim_is_another_conversations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auto_pm.application.core import pr_open_service

    root = _control_root(tmp_path)
    alias = _as_claude(monkeypatch)
    _service(root).open(alias, "c1", fetch=False)
    monkeypatch.setattr(pr_open_service, "claim_refusal", lambda *_a: "占位是别人的")
    with pytest.raises(PrOpenRefusedError, match="占位是别人的"):
        PrOpenService(root).plan(alias, "c1", "card.md", fetch=False)


def test_close_of_the_shared_bare_station_is_refused_without_shared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Counterexample: `worktree close claude` from a conversation that has no alias station would close the other conversations' station."""

    alias = _as_claude(monkeypatch)
    assert "--shared" in shared_station_refusal("claude")
    assert shared_station_refusal(alias) == ""  # its own station
    assert shared_station_refusal("trae") == ""  # not this caller's base name


def test_close_guard_does_not_apply_to_the_users_own_terminal() -> None:
    assert shared_station_refusal("claude") == ""


def test_claim_owner_defaults_to_the_conversation_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    alias = _as_claude(monkeypatch)
    assert _owner("") == alias and alias != "claude"
    assert _owner("claude") == "claude"  # releasing a pre-D-112 claim must be said out loud
    assert _owner(" claude-0a1b2c ") == "claude-0a1b2c"


def test_two_conversations_get_different_claim_owners(monkeypatch: pytest.MonkeyPatch) -> None:
    first = _as_claude(monkeypatch)
    second = _as_claude(monkeypatch, OTHER_SESSION)
    assert _owner("") == second and first != second
