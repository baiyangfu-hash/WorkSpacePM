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
    assert {option.name for option in retire_pm.params} >= {"project_id", "work_ids", "mission_ids", "stale", "apply_"}


def test_it_needs_exactly_one_of_a_named_work_a_named_card_or_stale(root: Path) -> None:
    for args in ((), ("--stale", "--work-id", "WORK-OLD"), ("--stale", "--mission-id", "M-1"),
                 ("--work-id", "WORK-OLD", "--mission-id", "M-1")):
        result = _run(root, *args)
        assert result.exit_code != 0 and "三选一" in result.output, args
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


def test_apply_outside_the_control_root_is_refused_before_anything_is_written(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D-134: removing the control-root check used to leave every test green."""

    from auto_pm.application.core.worktree_policy_service import (
        WorktreePolicyError,
        WorktreePolicyService,
    )

    def refuse(self: WorktreePolicyService) -> None:
        raise WorktreePolicyError("NOT-CONTROL-ROOT")

    monkeypatch.setattr(WorktreePolicyService, "require_control_root", refuse)
    result = _run(root, "--stale", "--apply")
    assert result.exit_code != 0 and "NOT-CONTROL-ROOT" in result.output
    assert _state(root) is WorkState.BLOCKED
    assert not (root / ".auto-pm" / "reports" / "retire").exists()


# ---------------------------------------------------------------- CHG-SCPT-2026-647：--mission-id


@pytest.fixture
def draft(root: Path) -> str:
    from tests.core.test_retire_service import _bare

    return _bare(root, "MISSION-DRAFT")


def _card_state(root: Path, mission_id: str) -> str:
    return ContinuityStore(root).get_mission(mission_id).state.value


def _payload(result: Result) -> dict[str, object]:
    loaded: dict[str, object] = json.loads(result.output[result.output.index("{") : result.output.rindex("}") + 1])
    return loaded


def test_mission_id_preview_lists_the_card_and_writes_nothing(root: Path, draft: str) -> None:
    result = _run(root, "--mission-id", draft, "--mission-id", "MISSION-NOPE")
    assert result.exit_code == 0, result.output
    payload = _payload(result)
    assert payload["mode"] == "dry-run" and payload["leftovers"] == [] and payload["not_card"] == ["MISSION-NOPE"]
    assert payload["cards"] == [{
        "mission_id": draft, "title": "draft card", "mission_state": "DRAFT", "root_work_id": "",
        "kind": "draft_without_work", "can_retire": True, "blocked_reason": "",
    }]
    assert _card_state(root, draft) == "DRAFT" and not (root / ".auto-pm" / "reports" / "retire").exists()


@pytest.mark.parametrize("words", [(), ("--approval-evidence-ref", "agent-decided-it")])
def test_mission_id_apply_from_an_agent_is_refused(root: Path, draft: str, words: tuple[str, ...]) -> None:
    result = _run(root, "--mission-id", draft, "--apply", *words, env={"CLAUDECODE": "1"})
    assert result.exit_code != 0
    assert _card_state(root, draft) == "DRAFT" and not (root / ".auto-pm" / "reports" / "retire").exists()


def test_the_user_in_person_retires_a_named_draft(root: Path, draft: str) -> None:
    result = _run(root, "--mission-id", draft, "--apply")
    assert result.exit_code == 0, result.output
    payload = _payload(result)
    assert payload["results"] == [{
        "kind": "draft_without_work", "work_id": "", "mission_ids": [draft], "mission_states_before": ["DRAFT"],
        "cancelled_mission_ids": [draft], "outcome": "retired", "detail": "已取消",
    }]
    assert Path(str(payload["trace"])).is_file()
    assert _card_state(root, draft) == "CANCELLED" and _state(root) is WorkState.BLOCKED  # 残留 Work 没被顺手收
