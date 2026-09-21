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


class WorkspaceProjectMapping(BaseModel):
    """One explicit project topology entry."""

    model_config = ConfigDict(frozen=True)

    project_id: str
    project_root: str
    development_root: str
    control_project_id: str = ""
    control_pm_session: str = ""
    runtime_root: str = ""


class WorkspaceRegistry(BaseModel):
    """Versioned topology registry consumed without workspace-wide scanning."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["workspace-registry.v1"] = "workspace-registry.v1"
    projects: tuple[WorkspaceProjectMapping, ...]


class WorkspaceContext(BaseModel):
    """A bounded identity card for one invocation, never global state."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["workspace-context.v2"] = "workspace-context.v2"
    workspace_root: str
    resolution_source: Literal["explicit", "directory"]
    subject_project_id: str
    subject: ContextProject
    control_project_id: str = ""
    control_pm_session: str = ""
    development_root: str
    runtime_root: str = ""
    # Backward-compatible alias for the configured active-release pointer.
    release_id: str = ""
    configured_release_id: str = ""
    effective_release_id: str = ""
    runtime_load_path: str = ""
    runtime_fallback_reason: str = ""
    read_set: tuple[ContextEvidence, ...]
    evidence_id: str
    conflicts: tuple[str, ...] = ()
