"""D-75: ``AI_AGENT`` (the generic agent convention) is a caller marker for ``caller_agent()``, not only for the lease handover."""

from __future__ import annotations

import pytest

from auto_pm.application.core.agent_worktree_service import caller_agent

_OTHER_MARKERS = ("AUTO_PM_AGENT", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CODEX_SANDBOX", "CODEX_THREAD_ID", "AI_AGENT")


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _OTHER_MARKERS:
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("claude-code_2-1-317_agent", "claude"), ("Claude", "claude"), ("codex_cli", "codex"), ("cursor-agent", "cursor")],
)
def test_ai_agent_alone_names_the_agent(monkeypatch: pytest.MonkeyPatch, value: str, expected: str) -> None:
    monkeypatch.setenv("AI_AGENT", value)

    assert caller_agent() == expected


def test_ai_agent_that_names_nobody_on_the_roster_is_refused_not_treated_as_the_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_AGENT", "mystery-bot_1.0")

    assert caller_agent() == "?"


def test_a_roster_name_inside_a_longer_word_does_not_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_AGENT", "claudette")

    assert caller_agent() == "?"


def test_ai_agent_agreeing_with_the_other_markers_is_fine_and_disagreeing_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("AI_AGENT", "claude-code_2-1-317_agent")
    assert caller_agent() == "claude"

    monkeypatch.setenv("AI_AGENT", "codex_cli")
    assert caller_agent() == "?"


def test_without_any_marker_the_caller_is_the_user() -> None:
    assert caller_agent() == ""
