"""Workspace context and project fact sources are read as strict UTF-8: a bad byte stops the read, it is never repaired."""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.application.core.project_fact_service import ProjectFactError, ProjectFactService
from auto_pm.application.core.workspace_context_service import (
    WorkspaceContextError,
    WorkspaceContextService,
)


def test_a_project_fact_source_with_a_bad_byte_is_refused(tmp_path: Path) -> None:
    source = tmp_path / "PM_SESSION.md"
    source.write_bytes(b"- status: ok \xff\n")

    with pytest.raises(ProjectFactError, match="无法读取文本事实源"):
        ProjectFactService._read_text(source)
    source.write_bytes(b"- status: ok\n")
    assert ProjectFactService._read_text(source) == "- status: ok\n"


def test_a_workspace_context_file_with_a_bad_byte_is_refused(tmp_path: Path) -> None:
    source = tmp_path / "workspace_registry.json"
    source.write_bytes(b'{"projects": "\xff"}')

    with pytest.raises(WorkspaceContextError, match="无法读取文件"):
        WorkspaceContextService._read_text(source)
