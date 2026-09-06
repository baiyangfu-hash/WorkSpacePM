"""Fail-closed dual-slot deployment container tests (NG-WP-12)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core.deployment_service import (
    ACTIVE_POINTER,
    MANIFEST_FILE,
    MANIFEST_SCHEMA,
    POINTER_SCHEMA,
    PREVIOUS_POINTER,
    RELEASES_DIR,
    DeploymentContainer,
    DeploymentFileError,
    DeploymentStateError,
)

ENTRY_PAYLOAD = b"release payload\n"


def _make_container(tmp_path: Path, *, with_manifest: bool = True) -> Path:
    root = tmp_path / "container"
    (root / RELEASES_DIR).mkdir(parents=True)
    if with_manifest:
        (root / MANIFEST_FILE).write_text(
            json.dumps({"schema_version": MANIFEST_SCHEMA, "releases": {}}), encoding="utf-8"
        )
    return root


def _make_release(root: Path, release_id: str, payload: bytes = ENTRY_PAYLOAD) -> Path:
    release_dir = root / RELEASES_DIR / release_id
    release_dir.mkdir(parents=True)
    (release_dir / "artifact.bin").write_bytes(payload)
    return release_dir


def _register_release(root: Path, release_id: str, payload: bytes = ENTRY_PAYLOAD) -> None:
    manifest_path = root / MANIFEST_FILE
    manifest: dict[str, Any] = {"schema_version": MANIFEST_SCHEMA, "releases": {}}
    if manifest_path.exists():
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        manifest = loaded
    manifest["releases"][release_id] = {
        "files": {"artifact.bin": hashlib.sha256(payload).hexdigest()},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _write_pointer(root: Path, name: str, release_id: str | None) -> None:
    (root / name).write_text(
        json.dumps(
            {
                "schema_version": POINTER_SCHEMA,
                "slot": name,
                "release_id": release_id,
                "updated_at": None,
            }
        ),
        encoding="utf-8",
    )


class TestReleaseIdValidation:
    @pytest.mark.parametrize(
        "release_id", ["1.2.3-87183fb", "20260905T140000Z-87183fb", "R1", "a.b_c-d"]
    )
    def test_accepts_legal_ids(self, tmp_path: Path, release_id: str) -> None:
        container = DeploymentContainer(_make_container(tmp_path))
        assert container.validate_release_id(release_id) == release_id

    @pytest.mark.parametrize(
        "release_id",
        ["", ".hidden", "..", "a/b", "a\\b", "a b", "-lead", "$env", "中文", "a" * 65],
    )
    def test_rejects_illegal_ids(self, tmp_path: Path, release_id: str) -> None:
        container = DeploymentContainer(_make_container(tmp_path))
        with pytest.raises(DeploymentFileError):
            container.validate_release_id(release_id)

    def test_container_root_must_exist(self, tmp_path: Path) -> None:
        with pytest.raises(DeploymentFileError):
            DeploymentContainer(tmp_path / "missing")

    def test_releases_root_must_be_plain_dir(self, tmp_path: Path) -> None:
        root = tmp_path / "container"
        root.mkdir()
        (root / RELEASES_DIR).write_text("not a dir", encoding="utf-8")
        with pytest.raises(DeploymentFileError):
            DeploymentContainer(root)


class TestReleaseDirContainment:
    def test_must_exist_requires_plain_directory(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        container = DeploymentContainer(root)
        with pytest.raises(DeploymentFileError):
            container.release_dir("r1", must_exist=True)
        release_dir = _make_release(root, "r1")
        assert container.release_dir("r1", must_exist=True) == release_dir.resolve()

    def test_symlinked_release_dir_is_rejected(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        outside = tmp_path / "outside"
        outside.mkdir()
        _make_release(root, "r1")
        try:
            (root / RELEASES_DIR / "evil").symlink_to(outside, target_is_directory=True)
        except OSError as exc:  # Windows symlink privilege, matches suite convention
            pytest.skip(f"无法创建 symlink: {exc}")
        container = DeploymentContainer(root)
        with pytest.raises(DeploymentFileError):
            container.release_dir("evil", must_exist=True)


class TestPointers:
    def test_missing_pointer_is_uninitialized(self, tmp_path: Path) -> None:
        container = DeploymentContainer(_make_container(tmp_path))
        pointer = container.read_pointer(ACTIVE_POINTER)
        assert pointer.release_id is None

    def test_unknown_pointer_name_is_state_error(self, tmp_path: Path) -> None:
        container = DeploymentContainer(_make_container(tmp_path))
        with pytest.raises(DeploymentStateError):
            container.read_pointer("other_release.json")

    def test_pointer_roundtrip(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        _make_release(root, "r1")
        container = DeploymentContainer(root)
        container.write_pointer(ACTIVE_POINTER, "r1")
        pointer = container.read_pointer(ACTIVE_POINTER)
        assert pointer.release_id == "r1"
        assert pointer.updated_at is not None
        assert not [p for p in root.iterdir() if p.name.startswith(".active_release")]

    def test_write_pointer_requires_existing_release(self, tmp_path: Path) -> None:
        container = DeploymentContainer(_make_container(tmp_path))
        with pytest.raises(DeploymentFileError):
            container.write_pointer(ACTIVE_POINTER, "ghost")

    def test_corrupted_pointer_fails_closed(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        (root / ACTIVE_POINTER).write_text("{not json", encoding="utf-8")
        container = DeploymentContainer(root)
        with pytest.raises(DeploymentFileError):
            container.read_pointer(ACTIVE_POINTER)

    @pytest.mark.parametrize(
        "payload",
        [
            {"schema_version": "other.v1", "slot": ACTIVE_POINTER, "release_id": None},
            {"schema_version": POINTER_SCHEMA, "slot": "mismatch", "release_id": None},
            {"schema_version": POINTER_SCHEMA, "slot": ACTIVE_POINTER, "release_id": "../escape"},
            {"schema_version": POINTER_SCHEMA, "slot": ACTIVE_POINTER, "release_id": 42},
        ],
    )
    def test_invalid_pointer_content_fails_closed(
        self, tmp_path: Path, payload: dict[str, Any]
    ) -> None:
        root = _make_container(tmp_path)
        (root / ACTIVE_POINTER).write_text(json.dumps(payload), encoding="utf-8")
        container = DeploymentContainer(root)
        with pytest.raises(DeploymentFileError):
            container.read_pointer(ACTIVE_POINTER)

    def test_atomic_write_cleans_temp_on_replace_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _make_container(tmp_path)
        _make_release(root, "r1")
        container = DeploymentContainer(root)
        real_replace = os.replace

        def exploding_replace(src: Any, dst: Any) -> None:
            raise OSError("replace failed")

        monkeypatch.setattr(os, "replace", exploding_replace)
        with pytest.raises(OSError, match="replace failed"):
            container.write_pointer(ACTIVE_POINTER, "r1")
        monkeypatch.setattr(os, "replace", real_replace)
        leftovers = [p.name for p in root.iterdir() if ".active_release" in p.name]
        assert leftovers == []
        assert not (root / ACTIVE_POINTER).exists()

    def test_previous_pointer_is_independent(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        _make_release(root, "r1")
        _make_release(root, "r2")
        container = DeploymentContainer(root)
        container.write_pointer(ACTIVE_POINTER, "r1")
        container.write_pointer(PREVIOUS_POINTER, "r2")
        assert container.read_pointer(ACTIVE_POINTER).release_id == "r1"
        assert container.read_pointer(PREVIOUS_POINTER).release_id == "r2"


class TestManifestVerification:
    def test_verify_release_counts_files(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        _make_release(root, "r1")
        _register_release(root, "r1")
        container = DeploymentContainer(root)
        assert container.verify_release("r1") == 1

    def test_tampered_file_fails_closed(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        _make_release(root, "r1")
        _register_release(root, "r1")
        (root / RELEASES_DIR / "r1" / "artifact.bin").write_bytes(b"tampered")
        container = DeploymentContainer(root)
        with pytest.raises(DeploymentFileError, match="SHA-256 不匹配"):
            container.verify_release("r1")

    def test_unregistered_regular_file_fails_closed(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        release_dir = _make_release(root, "r1")
        _register_release(root, "r1")
        (release_dir / "unexpected.txt").write_text("extra", encoding="utf-8")
        with pytest.raises(DeploymentFileError, match="未注册文件"):
            DeploymentContainer(root).verify_release("r1")

    def test_unregistered_directory_fails_closed(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        release_dir = _make_release(root, "r1")
        _register_release(root, "r1")
        (release_dir / "unexpected").mkdir()
        with pytest.raises(DeploymentFileError, match="未注册目录"):
            DeploymentContainer(root).verify_release("r1")

    def test_symlinked_payload_file_fails_closed(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        release_dir = _make_release(root, "r1")
        _register_release(root, "r1")
        target = release_dir / "artifact.bin"
        target.unlink()
        try:
            target.symlink_to(release_dir / "linked.bin")
        except OSError as exc:
            pytest.skip(f"无法创建 symlink: {exc}")
        with pytest.raises(DeploymentFileError, match="不允许链接或重解析点"):
            DeploymentContainer(root).verify_release("r1")

    def test_missing_file_fails_closed(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        (root / RELEASES_DIR / "r1").mkdir()
        _register_release(root, "r1")
        container = DeploymentContainer(root)
        with pytest.raises(DeploymentFileError, match="文件缺失"):
            container.verify_release("r1")

    def test_release_dir_missing_fails_closed(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        _register_release(root, "r1")
        container = DeploymentContainer(root)
        with pytest.raises(DeploymentFileError, match="不存在或不是目录"):
            container.verify_release("r1")

    def test_release_not_in_manifest_fails_closed(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        _make_release(root, "r1")
        container = DeploymentContainer(root)
        with pytest.raises(DeploymentStateError):
            container.verify_release("r1")

    def test_forbidden_manifest_path_fails_closed(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        _make_release(root, "r1")
        outside = tmp_path / "outside.bin"
        outside.write_bytes(ENTRY_PAYLOAD)
        manifest = {
            "schema_version": MANIFEST_SCHEMA,
            "releases": {"r1": {"files": {"../outside.bin": "0" * 64}}},
        }
        (root / MANIFEST_FILE).write_text(json.dumps(manifest), encoding="utf-8")
        container = DeploymentContainer(root)
        with pytest.raises(DeploymentFileError, match="路径越界"):
            container.verify_release("r1")

    def test_malformed_manifest_fails_closed(self, tmp_path: Path) -> None:
        root = _make_container(tmp_path)
        _make_release(root, "r1")
        (root / MANIFEST_FILE).write_text("{broken", encoding="utf-8")
        container = DeploymentContainer(root)
        with pytest.raises(DeploymentFileError):
            container.verify_release("r1")


class TestContainerLock:
    def test_lock_is_exclusive_and_released(self, tmp_path: Path) -> None:
        container = DeploymentContainer(_make_container(tmp_path))
        with container.acquire_lock():
            with pytest.raises(DeploymentStateError):
                with container.acquire_lock():
                    pass
        with container.acquire_lock():
            pass
        assert not container.lock_path().exists()
