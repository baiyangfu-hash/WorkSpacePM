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
    workspace_root = Path("C:/workspace")
    environment = launcher._child_environment(cache_root, workspace_root)

    assert "PYTHONPATH" not in environment
    assert environment["RUFF_CACHE_DIR"] == str(cache_root)
    assert environment["AUTO_PM_WORKSPACE"] == str(workspace_root)


def test_main_pins_child_to_workspace_owning_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher = _load_launcher()
    workspace_root = tmp_path / "workspace"
    container = _write_valid_container(
        workspace_root / "00_Infrastructure" / "auto_pm"
    )
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> object:
        captured["command"] = command
        captured.update(kwargs)
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    assert launcher.main(["pm", "resume", "SW-2026-008"], container=container) == 0
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["AUTO_PM_WORKSPACE"] == str(workspace_root)
    assert captured["cwd"] == container / "releases" / "1.2.4-test"
