"""F16: an agent session cannot approve a change order or issue a decision package on its own, with or without a PIN.

The user's ruling (A, 2026-10-31): like ``pm approve``, an agent session goes ahead only with a well-formed
``--approval-evidence-ref user-confirmation:<the user's message>``; with none, or one an agent wrote, it is refused.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from auto_pm.application.core.lease_handover_service import AGENT_MARKERS
from auto_pm.ui.cli import change as change_cli
from auto_pm.ui.cli import decision as decision_cli
from auto_pm.ui.cli.change import change_group
from auto_pm.ui.cli.decision import decision_group


class _Untouchable:
    """Stands in for the services; any use after the refusal is recorded and fails the test."""

    touched: list[str] = []  # noqa: RUF012

    def __init__(self, *_a: object, **_k: object) -> None:
        type(self).touched.append("constructed")

    def __getattr__(self, name: str) -> object:
        type(self).touched.append(name)
        raise RuntimeError(f"批准被拒绝之后仍在使用: {name}")


@pytest.fixture
def untouched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    _Untouchable.touched = []
    monkeypatch.setattr(change_cli, "ChangeService", _Untouchable)
    monkeypatch.setattr(decision_cli, "DecisionService", _Untouchable)
    monkeypatch.setattr(change_cli, "require_runtime_identity_for_change", lambda *a, **k: None)
    monkeypatch.setattr(decision_cli, "require_runtime_identity_for_change", lambda *a, **k: None)
    return _Untouchable.touched


def _obj(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        control_root=tmp_path, workspace_root=str(tmp_path), templates_dir=str(tmp_path)
    )


def _approve(tmp_path: Path, *extra: str) -> object:
    return CliRunner().invoke(
        change_group,
        ["transition", "CHG-1", "--to", "approved", "--approver", "probe-bot", *extra],
        obj=_obj(tmp_path),
    )


def _decide(tmp_path: Path, *extra: str) -> object:
    return CliRunner().invoke(
        decision_group,
        ["create", "--change-id", "CHG-1", "--approver", "probe-bot", *extra],
        obj=_obj(tmp_path),
    )


GOOD_EVIDENCE = "user-confirmation:cmsg_01AfNxhPWkgwWYuL1EVfYC7t1rGHHJbj"
BAD_EVIDENCE = (
    "yes",  # not the user-confirmation form
    "user-confirmation:short",  # under 8 characters
    "user-confirmation:claude-says-it-is-ok",  # names an agent
    "user-confirmation:codex/auto-approved",
    "   ",  # blank is the same as none
)


@pytest.mark.parametrize("marker", AGENT_MARKERS)
def test_an_agent_marker_stops_change_approval_before_any_service(
    marker: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untouched: list[str]
) -> None:
    monkeypatch.setenv(marker, "trae:cn")
    result = _approve(tmp_path)
    assert result.exit_code != 0  # type: ignore[attr-defined]
    assert "agent 会话" in result.output and marker in result.output  # type: ignore[attr-defined]
    assert untouched == []


@pytest.mark.parametrize("marker", AGENT_MARKERS)
def test_an_agent_marker_stops_decision_create_before_any_service(
    marker: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untouched: list[str]
) -> None:
    monkeypatch.setenv(marker, "1")
    result = _decide(tmp_path)
    assert result.exit_code != 0  # type: ignore[attr-defined]
    assert "agent 会话" in result.output  # type: ignore[attr-defined]
    assert untouched == []


def test_other_transitions_are_not_refused_by_this_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untouched: list[str]
) -> None:
    monkeypatch.setenv("AUTO_PM_AGENT", "trae:cn")
    result = CliRunner().invoke(
        change_group, ["transition", "CHG-1", "--to", "under_review"], obj=_obj(tmp_path)
    )
    assert "agent 会话" not in result.output
    assert untouched  # the command went on to the service


def test_a_user_terminal_without_markers_still_reaches_the_service(
    tmp_path: Path, untouched: list[str]
) -> None:
    result = _approve(tmp_path)
    assert "agent 会话" not in result.output  # type: ignore[attr-defined]
    assert untouched  # not refused: the command went on to the service


def test_an_empty_marker_is_not_an_agent_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untouched: list[str]
) -> None:
    monkeypatch.setenv("AUTO_PM_AGENT", "  ")
    assert "agent 会话" not in _approve(tmp_path).output  # type: ignore[attr-defined]


@pytest.mark.parametrize("marker", AGENT_MARKERS)
def test_an_agent_with_the_users_evidence_reaches_the_service(
    marker: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untouched: list[str]
) -> None:
    monkeypatch.setenv(marker, "1")
    result = _approve(tmp_path, "--approval-evidence-ref", GOOD_EVIDENCE)
    assert "agent 会话" not in result.output  # type: ignore[attr-defined]
    assert untouched  # not refused: the command went on to the service


def test_an_agent_with_the_users_evidence_reaches_decision_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untouched: list[str]
) -> None:
    reached: list[str] = []
    monkeypatch.setattr(decision_cli, "require_approval_pin", lambda *a, **k: reached.append("pin"))
    monkeypatch.setenv("CLAUDECODE", "1")
    result = _decide(tmp_path, "--approval-evidence-ref", GOOD_EVIDENCE)
    assert "agent 会话" not in result.output  # type: ignore[attr-defined]
    assert reached == ["pin"]  # past the agent refusal, on to the PIN step


@pytest.mark.parametrize("evidence", BAD_EVIDENCE)
def test_an_agent_with_bad_evidence_is_still_refused(
    evidence: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untouched: list[str]
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    for result in (
        _approve(tmp_path, "--approval-evidence-ref", evidence),
        _decide(tmp_path, "--approval-evidence-ref", evidence),
    ):
        assert result.exit_code != 0  # type: ignore[attr-defined]
        assert "agent 会话" in result.output  # type: ignore[attr-defined]
    assert untouched == []


def test_the_refusal_tells_the_agent_how_to_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untouched: list[str]
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    output = _approve(tmp_path).output  # type: ignore[attr-defined]
    assert "--approval-evidence-ref user-confirmation:" in output
    assert "没有带用户原话凭据" in output


def test_an_agent_with_evidence_still_meets_the_pin_when_one_is_committed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, untouched: list[str]
) -> None:
    """The evidence only lifts this agent-marker refusal; a committed PIN is still asked for afterwards."""

    seen: list[str] = []

    def _pin(*_a: object, **kwargs: object) -> None:
        seen.append(str(kwargs.get("purpose")))
        raise click.ClickException("需要口令")

    monkeypatch.setattr(change_cli, "require_approval_pin", _pin)
    monkeypatch.setenv("CLAUDECODE", "1")
    result = _approve(tmp_path, "--approval-evidence-ref", GOOD_EVIDENCE)
    assert seen == ["change-approve"]
    assert "需要口令" in result.output  # type: ignore[attr-defined]
    assert untouched == []
