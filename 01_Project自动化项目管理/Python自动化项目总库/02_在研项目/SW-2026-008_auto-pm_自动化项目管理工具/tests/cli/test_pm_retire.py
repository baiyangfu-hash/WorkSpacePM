"""D-109 layer 2: ``pm retire`` previews by default; ``--apply`` needs the user's own approval."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from auto_pm.contracts.continuity import WorkState
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.ui.cli.__main__ import cli
from auto_pm.ui.cli.pm_retire import retire_pm
from tests.core.test_continuity_resume_service import _workspace
from tests.core.test_resume_residue import _leftover

PROJECT = "SW-2026-008"
AGENT_MARKERS = ("CLAUDECODE", "CODEX_HOME", "CODEX_SANDBOX", "AUTO_PM_AGENT")


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in (*AGENT_MARKERS, "CLAUDE_CODE_SESSION_ID", "AUTO_PM_SESSION_ID"):
        monkeypatch.delenv(name, raising=False)
    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    return tmp_path


def _run(root: Path, *args: str, env: dict[str, str] | None = None) -> Result:
    return CliRunner().invoke(cli, ["-w", str(root), "pm", "retire", "--pid", PROJECT, *args], env=env)


def _state(root: Path) -> WorkState:
    return ContinuityStore(root).get_work("WORK-OLD").state


def test_retire_is_registered_under_pm() -> None:
    assert retire_pm.name == "retire"
    assert {option.name for option in retire_pm.params} >= {"project_id", "work_ids", "stale", "apply_"}


def test_it_needs_either_a_named_work_or_stale(root: Path) -> None:
    for args in ((), ("--stale", "--work-id", "WORK-OLD")):
        result = _run(root, *args)
        assert result.exit_code != 0 and "二者选一" in result.output
    assert _state(root) is WorkState.BLOCKED


def test_the_default_is_a_preview_that_writes_nothing(root: Path) -> None:
    result = _run(root, "--stale")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output[result.output.index("{") : result.output.rindex("}") + 1])
    assert payload["mode"] == "dry-run"
    assert [(i["work_id"], i["can_retire"]) for i in payload["leftovers"]] == [("WORK-OLD", True)]
    assert _state(root) is WorkState.BLOCKED
    assert not (root / ".auto-pm" / "reports" / "retire").exists()


def test_an_agent_session_without_the_users_words_is_refused_and_nothing_changes(root: Path) -> None:
    result = _run(root, "--stale", "--apply", env={"CLAUDECODE": "1"})
    assert result.exit_code != 0 and "agent" in result.output
    assert _state(root) is WorkState.BLOCKED


def test_an_agent_cannot_pass_off_its_own_words_as_the_users(root: Path) -> None:
    result = _run(root, "--stale", "--apply", "--approval-evidence-ref", "agent-decided-it", env={"CLAUDECODE": "1"})
    assert result.exit_code != 0
    assert _state(root) is WorkState.BLOCKED


def test_the_user_in_person_retires_the_leftover_and_gets_a_trace(root: Path) -> None:
    result = _run(root, "--work-id", "WORK-OLD", "--apply")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output[result.output.index("{") : result.output.rindex("}") + 1])
    assert [(r["work_id"], r["outcome"]) for r in payload["results"]] == [("WORK-OLD", "retired")]
    assert Path(payload["trace"]).is_file()
    assert _state(root) is WorkState.CANCELLED
