"""An agent session cannot rewrite the Obsidian spec library without the user's own words as evidence.

``spec index``, ``spec sync``, ``spec frontmatter --fix`` and ``spec check --fix`` (not ``--dry-run``) write files in the
global spec library.  AGENTS.md ("知识库迭代铁律") says the library is never overwritten by an AI on its own: it needs a change
order and the user's approval.  Like the approval commands, an agent session (one of the AGENT_MARKERS in the environment) is
refused before any file is touched unless it passes ``--approval-evidence-ref user-confirmation:<the user's message>``.
Previews and read-only checks are not affected.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.application.core.lease_handover_service import AGENT_MARKERS
from auto_pm.ui.cli import spec as spec_cli
from auto_pm.ui.cli.spec import spec_group

GOOD_EVIDENCE = "user-confirmation:cmsg_01AfNxhPWkgwWYuL1EVfYC7t1rGHHJbj"
BAD_EVIDENCE = ("yes", "user-confirmation:short", "user-confirmation:claude-says-ok-now", "  ")

# Commands that write the library, and the ones that must keep working in an agent session.
WRITING = {
    "index": ["index"],
    "sync": ["sync"],
    "frontmatter --fix": ["frontmatter", "--fix"],
    "check --fix": ["check", "--fix"],
}
NOT_WRITING = {
    "check": ["check"],
    "check --fix --dry-run": ["check", "--fix", "--dry-run"],
    "frontmatter (preview)": ["frontmatter"],
    "report": ["report"],
}


class _Untouchable:
    touched: list[str] = []  # noqa: RUF012

    def __init__(self, *_a: object, **_k: object) -> None:
        type(self).touched.append("constructed")

    def __getattr__(self, name: str) -> object:
        type(self).touched.append(name)
        raise RuntimeError(f"拒绝之后仍在使用: {name}")


@pytest.fixture
def untouched(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    _Untouchable.touched = []
    for name in ("IndexService", "CheckService", "FrontmatterService", "ReportService"):
        monkeypatch.setattr(spec_cli, name, _Untouchable)
    monkeypatch.setattr(spec_cli, "_resolve_workspace", lambda *_a, **_k: tmp_path)
    monkeypatch.setattr(spec_cli, "_load_ws_config", lambda *_a, **_k: None)
    return _Untouchable.touched


def _run(args: list[str], *extra: str) -> object:
    return CliRunner().invoke(spec_group, [*args, *extra])


@pytest.mark.parametrize("name", sorted(WRITING))
@pytest.mark.parametrize("marker", AGENT_MARKERS)
def test_an_agent_session_cannot_rewrite_the_library(
    name: str, marker: str, monkeypatch: pytest.MonkeyPatch, untouched: list[str]
) -> None:
    monkeypatch.setenv(marker, "1")
    result = _run(WRITING[name])
    assert result.exit_code != 0  # type: ignore[attr-defined]
    assert "agent 会话" in result.output and "规范库" in result.output  # type: ignore[attr-defined]
    assert "--approval-evidence-ref user-confirmation:" in result.output  # type: ignore[attr-defined]
    assert untouched == []


@pytest.mark.parametrize("evidence", BAD_EVIDENCE)
@pytest.mark.parametrize("name", sorted(WRITING))
def test_bad_evidence_is_still_refused(
    name: str, evidence: str, monkeypatch: pytest.MonkeyPatch, untouched: list[str]
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    result = _run(WRITING[name], "--approval-evidence-ref", evidence)
    assert result.exit_code != 0 and "agent 会话" in result.output  # type: ignore[attr-defined]
    assert untouched == []


@pytest.mark.parametrize("name", sorted(WRITING))
def test_the_users_evidence_lets_an_agent_session_through(
    name: str, monkeypatch: pytest.MonkeyPatch, untouched: list[str]
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    result = _run(WRITING[name], "--approval-evidence-ref", GOOD_EVIDENCE)
    assert "agent 会话" not in result.output  # type: ignore[attr-defined]
    assert untouched  # the command went on to the service


@pytest.mark.parametrize("name", sorted(WRITING))
def test_a_user_terminal_without_markers_is_not_asked(name: str, untouched: list[str]) -> None:
    result = _run(WRITING[name])
    assert "agent 会话" not in result.output  # type: ignore[attr-defined]
    assert untouched


@pytest.mark.parametrize("name", sorted(NOT_WRITING))
def test_previews_and_read_only_commands_are_not_refused_in_an_agent_session(
    name: str, monkeypatch: pytest.MonkeyPatch, untouched: list[str]
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    result = _run(NOT_WRITING[name])
    assert "agent 会话" not in result.output  # type: ignore[attr-defined]
    assert untouched
