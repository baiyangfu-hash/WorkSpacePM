"""Tests for server-side stdlib-only gate_plan_ci and dual-track gate-full.yml wiring."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from auto_pm.application.core.gate_tier_policy import ALL_GATE_GROUPS

PROJECT = Path(__file__).resolve().parents[2]
WORKSPACE = PROJECT.parents[3]
PLAN_SCRIPT = PROJECT / "tests" / "tools" / "sw008_ci" / "gate_plan_ci.py"
WORKFLOW = WORKSPACE / ".github" / "workflows" / "gate-full.yml"
PROJ_PREFIX = "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/"


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}
    proc = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "core.quotepath=false", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=True,
    )
    return proc.stdout.strip()


def _init_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    target = repo / PROJ_PREFIX / "README.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def _commit_files(repo: Path, files: dict[str, str], msg: str) -> str:
    for rel, content in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _run_isolated(repo: Path, *args: str) -> dict[str, object]:
    env = {**os.environ, "PYTHONUTF8": "1"}
    proc = subprocess.run(
        [sys.executable, "-I", "-S", str(PLAN_SCRIPT), "--repo", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=True,
    )
    return dict(json.loads(proc.stdout))


def test_gate_plan_ci_imports_with_zero_site_packages_and_no_third_party_modules() -> None:
    snippet = (
        "import json, sys; "
        f"sys.path.insert(0, {str(PROJECT)!r}); "
        "import tests.tools.sw008_ci.gate_plan_ci as m; "
        "print(json.dumps({'groups': len(m.ALL_GATE_GROUPS), 'callable': callable(m.plan_ci_gate), "
        "'site': [p for p in sys.path if 'site-packages' in p.lower()], "
        "'third_party': [k for k in ('yaml', 'pydantic', 'pydantic_core') if k in sys.modules]}))"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-S", "-c", snippet],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONUTF8": "1"},
        check=True,
    )
    info = json.loads(proc.stdout)
    assert info["groups"] == len(ALL_GATE_GROUPS)
    assert info["callable"] is True
    assert info["site"] == []
    assert info["third_party"] == []


def test_gate_plan_ci_runs_in_isolated_stdlib_mode_for_l2_change(tmp_path: Path) -> None:
    repo, base = _init_repo(tmp_path)
    cand = _commit_files(
        repo,
        {f"{PROJ_PREFIX}auto_pm/application/sample_service.py": "VALUE = 1\n"},
        "ordinary application change",
    )
    github_output = tmp_path / "gh_output.txt"
    plan = _run_isolated(
        repo,
        "--base",
        base,
        "--candidate",
        cand,
        "--requested-tier",
        "L2",
        "--github-output",
        str(github_output),
    )
    assert plan["tier"] == "L2"
    assert plan["groups"] == ["application"]
    assert plan["run_plugin"] is False
    out_text = github_output.read_text(encoding="utf-8")
    assert "tier=L2\n" in out_text
    assert 'groups=["application"]\n' in out_text
    assert "groups_csv=application\n" in out_text
    assert "run_plugin=false\n" in out_text


def test_gate_plan_ci_overrides_l2_request_to_l3_for_core_and_outside_changes(tmp_path: Path) -> None:
    repo, base = _init_repo(tmp_path)
    cand_core = _commit_files(
        repo,
        {f"{PROJ_PREFIX}auto_pm/application/core/gate_extra.py": "X = 1\n"},
        "core gate change",
    )
    plan_core = _run_isolated(repo, "--base", base, "--candidate", cand_core, "--requested-tier", "L2")
    assert plan_core["tier"] == "L3"
    assert plan_core["groups"] == list(ALL_GATE_GROUPS)
    assert plan_core["run_plugin"] is True

    cand_outside = _commit_files(
        repo,
        {".github/workflows/gate-full.yml": "name: gate-full\n"},
        "workflow outside project",
    )
    plan_outside = _run_isolated(repo, "--base", base, "--candidate", cand_outside, "--requested-tier", "L2")
    assert plan_outside["tier"] == "L3"
    assert plan_outside["groups"] == list(ALL_GATE_GROUPS)
    assert plan_outside["run_plugin"] is True


def test_gate_plan_ci_fails_closed_to_l3_on_empty_or_invalid_inputs(tmp_path: Path) -> None:
    repo, base = _init_repo(tmp_path)
    same = _run_isolated(repo, "--base", base, "--candidate", base, "--requested-tier", "L2")
    assert same["tier"] == "L3" and same["run_plugin"] is True

    unknown_req = _run_isolated(repo, "--base", base, "--candidate", base, "--requested-tier", "L1")
    assert unknown_req["tier"] == "L3" and unknown_req["groups"] == list(ALL_GATE_GROUPS)


def test_gate_full_workflow_has_dual_track_l2_and_strict_l3_reuse() -> None:
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    loaded = yaml.safe_load(workflow_text)
    on_block = loaded.get("on") or loaded[True]
    inputs = on_block["workflow_dispatch"]["inputs"]
    assert "requested_tier" in inputs
    assert loaded["jobs"]["group"]["strategy"]["matrix"]["group"] == "${{ fromJson(needs.identity.outputs.groups) }}"
    assert "run_plugin == 'true'" in loaded["jobs"]["plugin"]["if"]
    assert '.tier == "L3" and .plugin_result == "success"' in workflow_text
    assert "gate-verdict-l2-" in workflow_text
    assert "context=gate-l2" in workflow_text
    assert "gate_plan_ci.py" in workflow_text
