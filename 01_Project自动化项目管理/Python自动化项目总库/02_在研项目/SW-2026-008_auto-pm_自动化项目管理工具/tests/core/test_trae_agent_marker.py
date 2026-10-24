"""Trae must announce itself: the cockpit recognises AUTO_PM_AGENT=trae:cn and the .trae rules tell Trae to set it."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from auto_pm.application.core.agent_worktree_service import caller_agent
from auto_pm.application.core.lease_handover_service import agent_markers

REPO = Path(__file__).resolve().parents[6]
WRAPPER = REPO / ".trae" / "bin" / "pm-as-trae.ps1"
RULE = REPO / ".trae" / "rules" / "cockpit-entry.md"
SKILL = REPO / ".trae" / "skills" / "cockpit-entry" / "SKILL.md"

needs_trae_files = pytest.mark.skipif(
    not WRAPPER.is_file(), reason="the .trae folder is not part of this checkout"
)


@pytest.mark.parametrize("value", ["trae:cn", "trae:intl", "trae", "Trae:CN"])
def test_both_trae_editions_are_recognised_as_trae(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    for key in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AUTO_PM_AGENT", value)

    assert caller_agent() == "trae"
    assert agent_markers({"AUTO_PM_AGENT": value}) == ["AUTO_PM_AGENT"]


@needs_trae_files
def test_the_wrapper_sets_the_marker_for_one_command_and_restores_it() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    assert '$env:AUTO_PM_AGENT = "trae:cn"' in text
    assert re.search(r"finally\s*\{[^}]*Remove-Item Env:AUTO_PM_AGENT", text, re.S), (
        "必须在 finally 里还原"
    )
    assert "$env:AUTO_PM_AGENT = $previous" in text
    assert "@args" in text and "$LASTEXITCODE" in text, "参数要原样传给 main.py，退出码要原样返回"


@needs_trae_files
def test_the_rules_point_trae_at_the_wrapper() -> None:
    for path in (RULE, SKILL):
        text = path.read_text(encoding="utf-8")
        assert ".trae\\bin\\pm-as-trae.ps1" in text, path.name
        assert "AUTO_PM_AGENT=trae:cn" in text, path.name
        assert "冒号前面那段" in text or "冒号后面的 `cn` 只是备注" in text, path.name
