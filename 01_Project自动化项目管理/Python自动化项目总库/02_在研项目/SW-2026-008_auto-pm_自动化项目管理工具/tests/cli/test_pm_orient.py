"""V05-A: ``pm orient`` and ``pm resume`` expose the same versioned, capability-flagged query and write nothing."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from click.testing import CliRunner, Result

from auto_pm.application.core.pm_facade_service import PmFacadeService
from auto_pm.contracts.continuity_query import ContinuityQuery
from auto_pm.contracts.continuity_resume import ContinuityResume
from auto_pm.ui.cli.__main__ import cli

PROJECT = "SW-2026-008"
UNSUPPORTED_ACTIONS = ("PARK", "RESUME_PARKED", "PREEMPT")
# runtime-capabilities.v2 (TD-071 card 3): parking is supported, pre-emption is not
DECLARED = {"PARK": "SUPPORTED", "RESUME_PARKED": "SUPPORTED", "PREEMPT": "UNSUPPORTED"}


def _workspace(root: Path) -> Path:
    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "README.md", ".gitignore"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=Orient Test", "-c", "user.email=orient@example.invalid", "commit", "-m", "baseline"],
        check=True,
        capture_output=True,
    )
    project = root / PROJECT
    project.mkdir()
    (project / ".copier-answers.yml").write_text(f"project_id: {PROJECT}\nproject_name: Orient Test\nstack: python\n", encoding="utf-8")
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [{"project_id": PROJECT, "project_root": PROJECT, "development_root": PROJECT}],
            }
        ),
        encoding="utf-8",
    )
    return project


def _snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def _run(root: Path, *args: str) -> Result:
    return CliRunner().invoke(cli, ["-w", str(root), "pm", *args])


def _json(result: Result) -> Any:
    assert result.exit_code == 0, result.output
    start = result.output.index("{")
    return json.JSONDecoder().raw_decode(result.output[start:])[0]


def test_orient_is_listed_with_its_options_and_the_three_asked_actions(tmp_path: Path) -> None:
    _workspace(tmp_path)
    assert "orient" in _run(tmp_path, "--help").output
    helped = _run(tmp_path, "orient", "--help")
    assert helped.exit_code == 0
    for needle in ("--requested-action", "--work-id", "--run-id", "--json", *UNSUPPORTED_ACTIONS):
        assert needle in helped.output


def test_orient_and_resume_json_carry_the_same_query_block(tmp_path: Path) -> None:
    _workspace(tmp_path)
    oriented = _json(_run(tmp_path, "orient", PROJECT, "--json"))
    resumed = _json(_run(tmp_path, "resume", PROJECT, "--json"))
    assert oriented == resumed
    query = oriented["query"]
    assert (query["schema_version"], query["capabilities"]["contract_version"]) == ("continuity-query.v1", "runtime-capabilities.v2")
    assert query["capabilities"]["parking_supported"] is True and query["capabilities"]["preemption_supported"] is False
    assert [(a["action"], a["status"]) for a in query["capabilities"]["actions"]] == list(DECLARED.items())
    assert query["requested_action"] is None
    assert oriented["schema_version"] == "continuity-resume.v2" and "lease_token" not in json.dumps(oriented)


@pytest.mark.parametrize("action", UNSUPPORTED_ACTIONS)
def test_an_asked_action_is_answered_as_declared_with_exit_zero(tmp_path: Path, action: str) -> None:
    _workspace(tmp_path)
    plain = _json(_run(tmp_path, "orient", PROJECT, "--json"))
    asked = _json(_run(tmp_path, "orient", PROJECT, "--requested-action", action, "--json"))
    answer = asked["query"]["requested_action"]
    assert answer is not None
    assert (answer["action"], answer["status"]) == (action, DECLARED[action]) and answer["reason"]
    assert {k: v for k, v in asked.items() if k != "query"} == {k: v for k, v in plain.items() if k != "query"}
    text = _run(tmp_path, "orient", PROJECT, "--requested-action", action)
    assert text.exit_code == 0 and action in text.output and f": {DECLARED[action]}（" in text.output


@pytest.mark.parametrize("asked", ["park", "PAUSE", "NONE", "READY", "PARKED"])
def test_an_unknown_asked_action_is_refused_by_the_command_and_writes_nothing(tmp_path: Path, asked: str) -> None:
    _workspace(tmp_path)
    before = _snapshot(tmp_path)
    refused = _run(tmp_path, "orient", PROJECT, "--requested-action", asked)
    assert refused.exit_code != 0 and "Invalid value" in refused.output
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / ".auto-pm").exists()


def test_the_text_output_states_the_declared_capabilities_for_both_commands(tmp_path: Path) -> None:
    _workspace(tmp_path)
    for command in ("resume", "orient"):
        shown = _run(tmp_path, command, PROJECT)
        assert shown.exit_code == 0, shown.output
        assert "continuity-query.v1" in shown.output
        assert "挂起: 支持" in shown.output and "插队: 不支持" in shown.output and "pm park" in shown.output


def test_neither_command_creates_or_changes_anything_in_a_workspace_without_a_store(tmp_path: Path) -> None:
    _workspace(tmp_path)
    before = _snapshot(tmp_path)
    for args in (("resume", PROJECT, "--json"), ("orient", PROJECT, "--json"), ("orient", PROJECT, "--requested-action", "PARK"), ("orient", PROJECT)):
        assert _run(tmp_path, *args).exit_code == 0
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / ".auto-pm").exists()


def _replaced_answer(root: Path, kind: str) -> ContinuityResume:
    """What a replaced or regressed facade could hand to the command: a Resume that was never validated."""

    good = cast(ContinuityResume, PmFacadeService(root).resume(project_id=PROJECT))
    assert good.query is not None
    if kind == "legal":
        return good
    if kind == "no-query-block":
        return good.model_copy(update={"query": None})
    fields = {name: getattr(good.query, name) for name in ContinuityQuery.model_fields if name != "schema_version"}
    return good.model_copy(update={"query": ContinuityQuery.model_construct(**fields)})


@pytest.mark.parametrize("kind", ["legal", "no-schema-version", "no-query-block"])
@pytest.mark.parametrize("as_json", [True, False])
@pytest.mark.parametrize("command", ["resume", "orient"])
def test_both_commands_check_the_answer_again_and_print_nothing_when_it_is_broken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, as_json: bool, kind: str
) -> None:
    _workspace(tmp_path)
    answer = _replaced_answer(tmp_path, kind)
    before = _snapshot(tmp_path)
    monkeypatch.setattr(PmFacadeService, command, lambda self, **_kwargs: answer)
    shown = _run(tmp_path, command, PROJECT, *(["--json"] if as_json else []))
    if kind == "legal":  # the control: the replaced facade itself is not what makes the command fail
        assert shown.exit_code == 0, shown.output
        assert answer.evidence_id in shown.output and "continuity-query.v1" in shown.output
    else:
        assert shown.exit_code != 0 and ("未通过校验" in shown.output or "缺少 query" in shown.output)
        assert answer.evidence_id not in shown.output and "continuity-resume.v2" not in shown.output  # no half of a success payload
    assert _snapshot(tmp_path) == before
