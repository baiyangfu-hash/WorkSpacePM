"""Shared fixture helper: register a project in a scratch workspace so the runtime-identity guard can resolve it.

Tests about leases, handoffs or recovery drive the real ``continuity`` command in a bare workspace; since TD-SW008-214 those
write commands resolve the project's runtime identity first, which needs a registry entry and an anchor file.
"""

from __future__ import annotations

import json
from pathlib import Path


def register_project(root: Path, project_id: str) -> None:
    """Write a minimal Workspace Registry and project anchor for ``project_id`` (a folder of the same name) under ``root``."""

    project = root / project_id
    project.mkdir(parents=True, exist_ok=True)
    (project / ".copier-answers.yml").write_text(
        f"project_id: {project_id}\nproject_name: Fixture\nstack: python\n", encoding="utf-8"
    )
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [{"project_id": project_id, "project_root": project_id, "development_root": project_id}],
            }
        ),
        encoding="utf-8",
    )
