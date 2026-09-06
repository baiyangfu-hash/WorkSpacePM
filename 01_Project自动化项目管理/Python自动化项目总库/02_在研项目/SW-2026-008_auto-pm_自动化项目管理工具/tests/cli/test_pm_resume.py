"""Regression coverage for the bounded cross-AI PM cold-start command."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from auto_pm.cli.__main__ import cli
from click.testing import CliRunner


def _git(workspace: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        check=True,
        encoding="utf-8",
        errors="replace",
        text=True,
    )


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    subject = workspace / "SW-2026-008_auto-pm"
    subject.mkdir(parents=True)
    (subject / ".copier-answers.yml").write_text(
        "project_id: SW-2026-008\nproject_name: auto-pm\nstack: python\n",
        encoding="utf-8",
    )
    (subject / "PM_SESSION_SW-2026-008.md").write_text(
        "- runtime_root: 00_Infrastructure/auto_pm\n",
        encoding="utf-8",
    )
    control = workspace / "SYS-2026-001_WorkspaceGovernance"
    control.mkdir()
    (control / "PM_SESSION_SYS-2026-001.md").write_text(
        "- current_focus: SW-2026-008 驾驶舱闭环\n"
        "- [待批准] SW-2026-008 WBS-C2 | scope=执行生命周期\n",
        encoding="utf-8",
    )
    registry = workspace / "00_Obsidian_Base全局规范文件仓库"
    registry.mkdir()
    (registry / "spec_registry.json").write_text(
        json.dumps({"specs": {"PM-042": {"version": "V2.4.0"}}}),
        encoding="utf-8",
    )
    runtime = workspace / "00_Infrastructure" / "auto_pm"
    (runtime / "auto_pm" / "application").mkdir(parents=True)
    (runtime / "pyproject.toml").write_text("[project]\nname = 'fixture'\n", encoding="utf-8")
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "fixture")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "fixture")
    return workspace


def test_pm_resume_uses_governance_control_plane_and_is_bounded(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["-w", str(workspace), "pm", "resume", "SW-2026-008", "--json"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert len(result.output.encode("utf-8")) <= 12_288
    payload = json.loads(result.output)
    assert payload["schema_version"] == "pm-resume.v1"
    assert payload["control_project_id"] == "SYS-2026-001"
    assert payload["git_clean"] is True
    assert payload["next_legal_action"].startswith("阶段 0")
    assert len(payload["read_set"]) <= 3
    assert "PM_SESSION_SYS-2026-001.md" in payload["read_set"][0]
