"""Shared fixture helper: register a project in a scratch workspace so the runtime-identity guard can resolve it.

Tests about leases, handoffs, recovery or change orders drive the real command line in a bare workspace; since TD-SW008-214 those
write commands resolve the project's runtime identity first, which needs a registry entry and an anchor file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def register_project(root: Path, project_id: str, folder: str | None = None) -> None:
    """Add ``project_id`` (living in ``folder``, default a folder of the same name) to the Workspace Registry under ``root``.

    Calling it again for another project keeps the earlier entries.
    """

    folder = folder or project_id
    project = root / folder
    project.mkdir(parents=True, exist_ok=True)
    anchor = project / ".copier-answers.yml"
    if not anchor.exists():
        anchor.write_text(f"project_id: {project_id}\nproject_name: Fixture\nstack: python\n", encoding="utf-8")
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = (
        json.loads(registry.read_text(encoding="utf-8"))
        if registry.exists()
        else {"schema_version": "workspace-registry.v1", "projects": []}
    )
    payload["projects"].append({"project_id": project_id, "project_root": folder, "development_root": folder})
    registry.write_text(json.dumps(payload), encoding="utf-8")
