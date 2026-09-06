"""CLI coverage for the C1 read-only project preflight gate."""

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


def _create_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    project_dir = workspace / "SW-2026-008_预检测试"
    project_dir.mkdir(parents=True)
    (project_dir / ".copier-answers.yml").write_text(
        "project_id: SW-2026-008\nproject_name: auto-pm\nstack: python\n",
        encoding="utf-8",
    )
    (project_dir / "PM_SESSION_SW-2026-008.md").write_text(
        "- runtime_root: 00_Infrastructure/auto_pm\n",
        encoding="utf-8",
    )
    registry_dir = workspace / "00_Obsidian_Base全局规范文件仓库"
    registry_dir.mkdir()
    (registry_dir / "spec_registry.json").write_text(
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


def test_preflight_is_read_only_and_fact_validate_accepts_current_snapshot(tmp_path: Path) -> None:
    workspace = _create_workspace(tmp_path)
    runner = CliRunner()

    preflight = runner.invoke(
        cli,
        ["-w", str(workspace), "project", "preflight", "SW-2026-008", "--json"],
        catch_exceptions=False,
    )

    assert preflight.exit_code == 0, preflight.output
    snapshot = json.loads(preflight.output)
    assert snapshot["schema_version"] == "project-fact.v1"
    assert snapshot["project_id"] == "SW-2026-008"
    assert not (workspace / ".auto-pm" / "ai_context.json").exists()

    fact_file = tmp_path / "project-fact.json"
    fact_file.write_text(preflight.output, encoding="utf-8")
    validated = runner.invoke(
        cli,
        [
            "-w",
            str(workspace),
            "project",
            "fact",
            "validate",
            str(fact_file),
            "--pid",
            "SW-2026-008",
            "--json",
        ],
        catch_exceptions=False,
    )

    assert validated.exit_code == 0, validated.output
    assert json.loads(validated.output)["valid"] is True
