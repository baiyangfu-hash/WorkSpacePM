"""Bridge coverage for the no-write default cockpit path."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

from auto_pm.infrastructure.continuity_store import ContinuityStore
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


def _git_root(root: Path) -> None:
    subprocess.run(
        ["git", "-C", str(root), "init"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
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


def test_bridge_persists_pre_auth_draft_and_replays_same_input(tmp_path: Path) -> None:
    _registry(tmp_path)
    _git_root(tmp_path)
    store = ContinuityStore(tmp_path)
    store.initialize("2026-09-28T00:00:00+00:00", "test")
    bridge = PmCockpitBridge(str(tmp_path))
    first = bridge.createPlanningDraft(
        "DJ-2026-005", " Improve line throughput ", "Measure cycle time\nNo safety bypass"
    )
    replay = bridge.createPlanningDraft(
        "DJ-2026-005", "Improve line throughput", "Measure cycle time\nNo safety bypass"
    )
    changed = bridge.createPlanningDraft(
        "DJ-2026-005", "Improve quality", "Measure cycle time\nNo safety bypass"
    )
    new_session = PmCockpitBridge(str(tmp_path)).createPlanningDraft(
        "DJ-2026-005", "Improve line throughput", "Measure cycle time\nNo safety bypass"
    )

    assert all(result["success"] for result in (first, replay, changed, new_session))
    assert first["draft"] == replay["draft"]
    assert first["draft"]["state"] == "PRE_AUTH"
    assert first["draft"]["scope_status"] == "范围待规划"
    assert first["draft"]["acceptance_criteria"] == ["Measure cycle time", "No safety bypass"]
    assert "request_id" not in first["draft"]
    with sqlite3.connect(store.db_path) as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("planning_drafts", "mission_items", "work_items", "run_items")
        }
        request_ids = conn.execute("SELECT request_id FROM planning_drafts").fetchall()
    assert counts == {"planning_drafts": 3, "mission_items": 0, "work_items": 0, "run_items": 0}
    assert len(set(request_ids)) == 3
    assert not list(tmp_path.rglob("CHG-*.md"))


def test_bridge_rejects_incomplete_or_unknown_planning_input(tmp_path: Path) -> None:
    _registry(tmp_path)
    _git_root(tmp_path)
    store = ContinuityStore(tmp_path)
    store.initialize("2026-09-28T00:00:00+00:00", "test")
    bridge = PmCockpitBridge(str(tmp_path))

    for project, objective, acceptance in (
        ("DJ-2026-005", "", "Accepted"),
        ("DJ-2026-005", "Objective", "  "),
        ("", "Objective", "Accepted"),
        ("UNKNOWN", "Objective", "Accepted"),
        ("DJ-2026-005", "Objective", "Same\nSame"),
    ):
        result = bridge.createPlanningDraft(project, objective, acceptance)
        assert result["success"] is False
        assert "draft" not in result

    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM planning_drafts").fetchone()[0] == 0
