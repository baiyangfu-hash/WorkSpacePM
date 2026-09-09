"""Stateless provider adapter and Resume v2 CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

from auto_pm.core.continuity_adapter import ContinuityAdapter
from click.testing import CliRunner

from auto_pm.ui.cli.__main__ import cli


def _workspace(root: Path) -> Path:
    project = root / "SW-2026-008"
    project.mkdir()
    (project / ".copier-answers.yml").write_text(
        "project_id: SW-2026-008\nproject_name: Adapter Test\nstack: python\n",
        encoding="utf-8",
    )
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": "SW-2026-008",
                        "project_root": "SW-2026-008",
                        "development_root": "SW-2026-008",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return project


def test_two_provider_adapters_receive_identical_canonical_payload(tmp_path: Path) -> None:
    project = _workspace(tmp_path)

    codex = ContinuityAdapter(tmp_path, "codex").resume(invocation_path=project)
    cursor = ContinuityAdapter(tmp_path, "cursor").resume(invocation_path=project)

    assert codex == cursor
    assert codex["schema_version"] == "continuity-resume.v2"
    assert "provider" not in codex


def test_pm_resume_cli_defaults_to_v2(tmp_path: Path) -> None:
    _workspace(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "--workspace",
            str(tmp_path),
            "pm",
            "resume",
            "SW-2026-008",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "continuity-resume.v2"
    assert payload["work"] is None
    assert payload["next_legal_action"] == ""


def test_v2_rejects_manual_control_override(tmp_path: Path) -> None:
    _workspace(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "--workspace",
            str(tmp_path),
            "pm",
            "resume",
            "SW-2026-008",
            "--control-pid",
            "SYS-2026-001",
        ],
    )

    assert result.exit_code != 0
    assert "Registry" in result.output
