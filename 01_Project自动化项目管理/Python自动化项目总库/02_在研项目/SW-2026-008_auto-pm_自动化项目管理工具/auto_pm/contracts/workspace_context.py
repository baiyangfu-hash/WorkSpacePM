"""Read-only, fail-closed workspace context contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ContextProject(BaseModel):
    """The project established by a verifiable workspace anchor."""

    model_config = ConfigDict(frozen=True)

    project_id: str
    name: str
    path: str
    stack: str
    phase: str
    source: str


class ContextEvidence(BaseModel):
    """One bounded input that was read while resolving an invocation."""

    model_config = ConfigDict(frozen=True)

    path: str
    sha256: str


class WorkspaceContext(BaseModel):
    """A bounded identity card for one invocation, never global state."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["workspace-context.v1"] = "workspace-context.v1"
    workspace_root: str
    resolution_source: Literal["explicit", "directory"]
    subject: ContextProject
    control_project_id: str = ""
    control_pm_session: str = ""
    development_root: str
    runtime_root: str = ""
    release_id: str = ""
    read_set: tuple[ContextEvidence, ...]
    evidence_id: str
    conflicts: tuple[str, ...] = ()
