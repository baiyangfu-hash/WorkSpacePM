"""Project fact package contracts used by PM preflight and decision gates."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FileFingerprint(BaseModel):
    """A stable fingerprint for a source-of-truth file."""

    model_config = ConfigDict(frozen=True)

    path: str
    sha256: str
    byte_count: int = Field(ge=0)


class GitFact(BaseModel):
    """Read-only Git evidence captured for a project preflight."""

    model_config = ConfigDict(frozen=True)

    repository_root: str
    head: str
    status: list[str] = Field(default_factory=list)


class OpenChangeFact(BaseModel):
    """A non-terminal change request belonging to the project."""

    model_config = ConfigDict(frozen=True)

    change_number: str
    status: str
    domain: str
    file_path: str


class SpecVersionDrift(BaseModel):
    """A PM_SESSION spec version that differs from the registered version."""

    model_config = ConfigDict(frozen=True)

    spec_id: str
    project_version: str
    registry_version: str


class SpecSnapshotFact(BaseModel):
    """The immutable registry evidence used by the fact package."""

    model_config = ConfigDict(frozen=True)

    registry: FileFingerprint
    registry_versions: dict[str, str] = Field(default_factory=dict)
    project_versions: dict[str, str] = Field(default_factory=dict)
    drifts: list[SpecVersionDrift] = Field(default_factory=list)


class CodeStructureFact(BaseModel):
    """A compact summary of the code root that will be changed."""

    model_config = ConfigDict(frozen=True)

    runtime_root: str
    source_root: str
    top_level_directories: list[str] = Field(default_factory=list)
    clean_architecture_layers: list[str] = Field(default_factory=list)
    python_file_count: int = Field(ge=0)


class AvailableCheckFact(BaseModel):
    """A check that can be run after an approved implementation."""

    model_config = ConfigDict(frozen=True)

    check_id: str
    command: str
    available: bool
    reason: str = ""


class ProjectFactSnapshot(BaseModel):
    """Versioned, integrity-protected evidence package for a PM decision."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["project-fact.v1"] = "project-fact.v1"
    evidence_id: str
    fingerprint: str
    project_id: str
    workspace_root: str
    project_path: str
    collected_at: datetime
    expires_at: datetime
    git: GitFact
    pm_session: FileFingerprint
    open_changes: list[OpenChangeFact] = Field(default_factory=list)
    spec_snapshot: SpecSnapshotFact
    code_structure: CodeStructureFact
    available_checks: list[AvailableCheckFact] = Field(default_factory=list)

    def integrity_fingerprint(self) -> str:
        """Return the SHA-256 digest over the immutable evidence fields."""
        payload = self.model_dump(mode="json", exclude={"evidence_id", "fingerprint"})
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class FactValidationResult(BaseModel):
    """The explicit acceptance or rejection result for a fact package."""

    model_config = ConfigDict(frozen=True)

    valid: bool
    evidence_id: str = ""
    failures: list[str] = Field(default_factory=list)
