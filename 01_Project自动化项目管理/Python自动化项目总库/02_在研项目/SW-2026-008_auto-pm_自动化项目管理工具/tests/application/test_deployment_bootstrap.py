"""Dual-slot bootstrap resolver tests (NG-WP-13).

The bootstrap module is stdlib-only container infrastructure; it is loaded by
path from the workspace container copy so the mother suite can gate it without
importing ``auto_pm``.  Skipped when the container layout is absent (pure
release-artifact checkouts).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_CONTAINER = Path(__file__).resolve().parents[6] / "00_Infrastructure" / "auto_pm"
_BOOTSTRAP = _CONTAINER / "launcher" / "bootstrap.py"

pytestmark = pytest.mark.skipif(
    not _BOOTSTRAP.is_file(), reason="container launcher/bootstrap.py not present in checkout"
)


def _load_bootstrap() -> ModuleType:
    spec = importlib.util.spec_from_file_location("deployment_bootstrap_under_test", _BOOTSTRAP)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bs() -> ModuleType:
    return _load_bootstrap()


def _make_container(tmp_path: Path) -> Path:
    root = tmp_path / "container"
    (root / "releases").mkdir(parents=True)
    (root / "deployment_manifest.json").write_text(
        json.dumps({"schema_version": "deployment_manifest.v1", "releases": {}}), encoding="utf-8"
    )
    return root


def _pointer(container: Path, name: str, release_id: str | None) -> None:
    (container / name).write_text(
        json.dumps(
            {
                "schema_version": "release_pointer.v1",
                "slot": name,
                "release_id": release_id,
                "updated_at": None,
            }
        ),
        encoding="utf-8",
    )


def _release(container: Path, release_id: str, *, registered: bool = True) -> Path:
    release_dir = container / "releases" / release_id
    release_dir.mkdir(parents=True)
    (release_dir / "auto_pm_marker.txt").write_text("payload", encoding="utf-8")
    if registered:
        manifest_path = container / "deployment_manifest.json"
        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["releases"][release_id] = {"files": {}}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return release_dir


def test_active_ok_resolves_active_slot(bs: ModuleType, tmp_path: Path) -> None:
    container = _make_container(tmp_path)
    release_dir = _release(container, "1.2.3-87183fb")
    _pointer(container, "active_release.json", "1.2.3-87183fb")
    resolved, slot = bs.resolve_with_fallback(container)
    assert slot == "active_release.json"
    assert resolved == release_dir.resolve()
    assert resolved.is_relative_to((container / "releases").resolve())


def test_active_corrupted_falls_back_to_previous(bs: ModuleType, tmp_path: Path) -> None:
    container = _make_container(tmp_path)
    _release(container, "r-prev")
    (container / "active_release.json").write_text("{corrupted", encoding="utf-8")
    _pointer(container, "previous_release.json", "r-prev")
    resolved, slot = bs.resolve_with_fallback(container)
    assert slot == "previous_release.json"
    assert resolved.name == "r-prev"


def test_active_dir_missing_falls_back_to_previous(bs: ModuleType, tmp_path: Path) -> None:
    container = _make_container(tmp_path)
    _release(container, "r-prev")
    _pointer(container, "active_release.json", "r-ghost")
    _pointer(container, "previous_release.json", "r-prev")
    resolved, slot = bs.resolve_with_fallback(container)
    assert slot == "previous_release.json"


def test_both_slots_null_fails_closed(bs: ModuleType, tmp_path: Path) -> None:
    container = _make_container(tmp_path)
    _pointer(container, "active_release.json", None)
    _pointer(container, "previous_release.json", None)
    with pytest.raises(bs.BootstrapError) as excinfo:
        bs.resolve_with_fallback(container)
    assert excinfo.value.exit_code == bs.EXIT_POINTER_INVALID


def test_both_slots_unreadable_fails_closed(bs: ModuleType, tmp_path: Path) -> None:
    container = _make_container(tmp_path)
    (container / "active_release.json").write_text("{", encoding="utf-8")
    (container / "previous_release.json").write_text("nonsense", encoding="utf-8")
    with pytest.raises(bs.BootstrapError) as excinfo:
        bs.resolve_with_fallback(container)
    assert excinfo.value.exit_code == bs.EXIT_POINTER_INVALID


def test_release_id_escape_fails_closed(bs: ModuleType, tmp_path: Path) -> None:
    container = _make_container(tmp_path)
    _pointer(container, "active_release.json", "../escape")
    with pytest.raises(bs.BootstrapError) as excinfo:
        bs.resolve_with_fallback(container)
    assert excinfo.value.exit_code == bs.EXIT_RELEASE_INVALID


def test_release_not_in_manifest_fails_closed(bs: ModuleType, tmp_path: Path) -> None:
    container = _make_container(tmp_path)
    _release(container, "r1", registered=False)
    _pointer(container, "active_release.json", "r1")
    with pytest.raises(bs.BootstrapError) as excinfo:
        bs.resolve_with_fallback(container)
    assert excinfo.value.exit_code == bs.EXIT_RELEASE_INVALID


def test_symlinked_release_dir_fails_closed(bs: ModuleType, tmp_path: Path) -> None:
    container = _make_container(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    _release(container, "r1")
    try:
        (container / "releases" / "evil").symlink_to(outside, target_is_directory=True)
    except OSError as exc:  # Windows symlink privilege
        pytest.skip(f"无法创建 symlink: {exc}")
    _pointer(container, "active_release.json", "evil")
    with pytest.raises(bs.BootstrapError) as excinfo:
        bs.resolve_with_fallback(container)
    assert excinfo.value.exit_code == bs.EXIT_RELEASE_INVALID


def test_invalid_container_layout_fails_closed(bs: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(bs.BootstrapError) as excinfo:
        bs.resolve_with_fallback(tmp_path / "missing")
    assert excinfo.value.exit_code == bs.EXIT_CONTAINER_INVALID


def test_bootstrap_module_never_imports_auto_pm(bs: ModuleType) -> None:
    source = _BOOTSTRAP.read_text(encoding="utf-8")
    assert "import auto_pm" not in source
    assert "from auto_pm" not in source


def test_real_container_pointers_stay_uninitialized(bs: ModuleType) -> None:
    """The real container must stay un-deployed until NG-WP-15 flips pointers."""
    assert bs._read_pointer_release_id(_CONTAINER, "active_release.json") is None
    assert bs._read_pointer_release_id(_CONTAINER, "previous_release.json") is None
