"""Bridge coverage for the no-write default cockpit path."""

from __future__ import annotations

import json
from pathlib import Path

from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge


def _registry(root: Path) -> None:
    path = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": "DJ-2026-005",
                        "project_root": "projects/DJ-2026-005",
                        "development_root": "projects/DJ-2026-005",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_bridge_default_load_is_read_only_when_continuity_store_is_missing(tmp_path: Path) -> None:
    _registry(tmp_path)
    bridge = PmCockpitBridge(str(tmp_path))

    result = bridge.loadSnapshot()

    assert result["success"] is True
    card = result["snapshot"]["projects"][0]
    assert card["project_id"] == "DJ-2026-005"
    assert "向 PM 描述需求" in card["next_user_action"]
    assert "不会自动修复" in card["next_user_action"]
    assert not (tmp_path / ".auto-pm").exists()


def test_bridge_rejects_evidence_for_an_unregistered_project(tmp_path: Path) -> None:
    _registry(tmp_path)
    bridge = PmCockpitBridge(str(tmp_path))

    result = bridge.loadEvidence("UNKNOWN-001")

    assert result["success"] is False
    assert "不在工作空间项目清单" in result["message"]
