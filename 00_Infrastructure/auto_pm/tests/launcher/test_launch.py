"""Regression tests for the fail-closed stable launcher."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_launcher() -> ModuleType:
    launcher_path = Path(__file__).parents[2] / "launcher" / "launch.py"
    spec = importlib.util.spec_from_file_location("test_stable_launcher", launcher_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_valid_container(tmp_path: Path) -> Path:
    release_id = "1.2.4-test"
    release_dir = tmp_path / "releases" / release_id
    payload = release_dir / "auto_pm" / "__init__.py"
    payload.parent.mkdir(parents=True)
    payload.write_text("", encoding="utf-8")
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    (tmp_path / "active_release.json").write_text(
        json.dumps(
            {
                "schema_version": "release_pointer.v1",
                "slot": "active_release.json",
                "release_id": release_id,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "deployment_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "deployment_manifest.v1",
                "releases": {release_id: {"files": {"auto_pm/__init__.py": digest}}},
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_resolve_only_argument_verifies_without_starting_child(tmp_path: Path) -> None:
    launcher = _load_launcher()

    assert launcher.main(["--resolve-only"], container=_write_valid_container(tmp_path)) == 0


def test_unregistered_ruff_cache_remains_a_fail_closed_error(tmp_path: Path) -> None:
    launcher = _load_launcher()
    container = _write_valid_container(tmp_path)
    cache_dir = container / "releases" / "1.2.4-test" / "templates" / ".ruff_cache"
    cache_dir.mkdir(parents=True)

    assert launcher.main(["--resolve-only"], container=container) == 4


def test_child_environment_routes_ruff_cache_outside_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher = _load_launcher()
    monkeypatch.setenv("PYTHONPATH", "unsafe")
    monkeypatch.setenv("RUFF_CACHE_DIR", "unsafe")

    cache_root = Path("C:/container/.auto-pm/runtime-cache/ruff")
    environment = launcher._child_environment(cache_root)

    assert "PYTHONPATH" not in environment
    assert environment["RUFF_CACHE_DIR"] == str(cache_root)
