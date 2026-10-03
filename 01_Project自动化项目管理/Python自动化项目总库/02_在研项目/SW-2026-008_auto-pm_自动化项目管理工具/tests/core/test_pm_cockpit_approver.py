"""U09C: the approver comes only from configuration, and a model name can never be that approver.

Scenario ids a01..a05 are the configuration and the cockpit bridge builder; s01..s03 are the self-signing rule
(card 040 section 5.4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from auto_pm.domain.change.decision_service import DecisionService, DecisionValidationError
from auto_pm.infrastructure.config.app_config import AutoPmConfig
from auto_pm.ui.boss_qml_window import build_cockpit_bridge

_HASH = "a" * 64
_EVIDENCE = "user-confirmation:cockpit-0123456789abcdef-01234567"


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTO_PM_COCKPIT_APPROVER", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.chdir(Path(__file__).resolve().parents[2])


def _approver_of(bridge: object) -> str:
    # The bridge holds the service loaded through the alias module path, so read the attribute instead of
    # comparing classes (auto_pm.core.* and auto_pm.application.core.* are distinct module objects).
    service = cast(Any, bridge)._service
    return str(service._approver)


# --------------------------------------------------------------------------- a: configuration


def test_a01_the_approver_defaults_to_empty_which_means_approval_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)

    assert AutoPmConfig().cockpit_approver == ""


def test_a02_the_approver_is_read_from_the_namespaced_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("AUTO_PM_COCKPIT_APPROVER", "fubai")

    assert AutoPmConfig().cockpit_approver == "fubai"
    assert AutoPmConfig(cockpit_approver="baiyang").cockpit_approver == "baiyang"


def test_a03_an_empty_environment_variable_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("AUTO_PM_COCKPIT_APPROVER", "")

    assert AutoPmConfig().cockpit_approver == ""


def test_a04_the_bridge_builder_hands_the_configured_approver_to_the_service(
    qapp: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)

    configured = build_cockpit_bridge(str(tmp_path), AutoPmConfig(cockpit_approver="fubai"))
    unconfigured = build_cockpit_bridge(str(tmp_path), AutoPmConfig())

    assert _approver_of(configured) == "fubai"
    assert _approver_of(unconfigured) == ""


def test_a05_an_unreadable_configuration_leaves_the_approver_empty_instead_of_guessing(
    qapp: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "NOT-A-LEVEL")
    monkeypatch.setenv("AUTO_PM_COCKPIT_APPROVER", "fubai")
    with pytest.raises(ValidationError):
        AutoPmConfig()

    bridge = build_cockpit_bridge(str(tmp_path))

    assert _approver_of(bridge) == ""


# --------------------------------------------------------------------------- s: the self-signing rule


@pytest.mark.parametrize(
    "name",
    [
        "Claude",
        "claude-opus-5-5",
        "Claude Code",
        "PM (Claude)",
        "claude_sonnet",
        "sonnet",
        "Opus 5.5",
        "haiku",
        "Anthropic",
        "fable-5-1",
        "gemini",
        "Copilot",
        "gpt-5",
        "codex-gpt-5",
        "Codex Agent",
        "AI",
        "my.ai.assistant",
        "model",
        "llm-bot",
    ],
)
def test_s01_every_model_or_agent_style_name_is_refused_as_approver(name: str) -> None:
    with pytest.raises(DecisionValidationError, match="自签"):
        DecisionService.validate_planning_approval(name, _HASH, _EVIDENCE)


@pytest.mark.parametrize("name", ["fubai", "baiyang", "Maia", "Zhang San", "li.wei", "王工"])
def test_s02_human_names_are_still_accepted(name: str) -> None:
    approval = DecisionService.validate_planning_approval(name, _HASH, _EVIDENCE)

    planning = approval["planning_approval"]
    assert isinstance(planning, dict)
    assert planning["approval_evidence_ref"] == _EVIDENCE


def test_s03_the_other_approval_rules_are_unchanged() -> None:
    with pytest.raises(DecisionValidationError, match="user-confirmation"):
        DecisionService.validate_planning_approval("fubai", _HASH, "chat-said-ok-123")
    with pytest.raises(DecisionValidationError, match="plan_hash"):
        DecisionService.validate_planning_approval("fubai", "short", _EVIDENCE)
