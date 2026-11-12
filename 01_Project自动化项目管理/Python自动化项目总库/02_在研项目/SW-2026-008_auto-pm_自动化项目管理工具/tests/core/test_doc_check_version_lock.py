"""DOC-004 version lock (D-294): it used to be always green; now it compares the project's own version with the active release."""

from __future__ import annotations

import json
from pathlib import Path

from auto_pm.application.core.doc_services import DocCheckService
from auto_pm.domain.doc.models import DocCheckResult

APP = Path("01_Project自动化项目管理") / "Python自动化项目总库" / "02_在研项目" / "SW-2026-008_auto-pm_自动化项目管理工具"
PYPROJECT = """[project]
name = "auto-pm"
version = "{version}"

[tool.ruff]
required-version = ">=0.8.4"
"""


def _workspace(tmp_path: Path, *, source: str | None = "1.3.3", released: str | None = "1.3.3", release_id: str = "1.3.3-abc1234") -> Path:
    app = tmp_path / APP
    app.mkdir(parents=True)
    if source is not None:
        (app / "pyproject.toml").write_text(PYPROJECT.format(version=source), encoding="utf-8")
    container = tmp_path / "00_Infrastructure" / "auto_pm"
    container.mkdir(parents=True)
    (container / "active_release.json").write_text(
        json.dumps({"schema_version": "release_pointer.v1", "release_id": release_id, "release_path": release_id}), encoding="utf-8"
    )
    if released is not None:
        meta_dir = container / "releases" / release_id
        meta_dir.mkdir(parents=True)
        (meta_dir / "release_meta.json").write_text(json.dumps({"release_id": release_id, "version": released}), encoding="utf-8")
    return tmp_path


def _doc004(root: Path) -> DocCheckResult:
    return next(result for result in DocCheckService(root).check_all() if result.check_id == "DOC-004")


def test_the_same_version_on_both_sides_passes_and_ruffs_required_version_is_not_read(tmp_path: Path) -> None:
    result = _doc004(_workspace(tmp_path))

    assert result.passed is True
    assert "pyproject=1.3.3" in result.message and "0.8.4" not in result.message


def test_a_different_version_fails(tmp_path: Path) -> None:
    """The check that used to be written green (``passed_ver or True``) must be able to go red."""

    result = _doc004(_workspace(tmp_path, source="1.3.4", released="1.3.3"))

    assert result.passed is False
    assert "版本不一致" in result.message and "1.3.4" in result.message and "1.3.3" in result.message


def test_an_unreadable_project_version_fails_as_not_comparable(tmp_path: Path) -> None:
    result = _doc004(_workspace(tmp_path, source=None))

    assert result.passed is False
    assert "无法比对" in result.message and "pyproject.toml" in result.message


def test_a_missing_release_meta_fails_as_not_comparable(tmp_path: Path) -> None:
    result = _doc004(_workspace(tmp_path, released=None))

    assert result.passed is False
    assert "无法比对" in result.message and "release_meta.json" in result.message


def test_no_active_release_pointer_fails_as_not_comparable(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    (root / "00_Infrastructure" / "auto_pm" / "active_release.json").unlink()

    result = _doc004(root)

    assert result.passed is False
    assert "无法比对" in result.message and "active_release.json" in result.message


def test_a_retired_pm_session_is_not_read(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    (root / APP / "PM_SESSION_SW-2026-008.md").write_text("- version: V1.2.4\n", encoding="utf-8")

    result = _doc004(root)

    assert result.passed is True
    assert "PM_SESSION" not in result.message and "1.2.4" not in result.message
