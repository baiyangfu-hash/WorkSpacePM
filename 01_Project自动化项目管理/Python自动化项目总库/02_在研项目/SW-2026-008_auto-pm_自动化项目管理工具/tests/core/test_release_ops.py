"""D-146 card 2: the Python port of ``pmf_release_ops.sh`` (build / verify / switch / rollback) on a throw-away control root."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core import release_ops as ops
from auto_pm.application.core.release_deploy_check import CONTAINER, PROJECT_DIR

FAKE_BUILDER = '''
import json, os
from pathlib import Path

class Result:
    built_at = "2026-11-08T00:00:00+00:00"
    def __init__(self, files): self.files = files
    def manifest_entry(self): return {"files": self.files, "source_commit": "x"}

def project_version(repo, commit, project_root): return "1.3.3"

def build(repo, commit, project_root, output, release_id):
    output.mkdir(parents=True)
    (output / "payload.txt").write_text("payload", encoding="utf-8")
    if os.environ.get("FAKE_BUILD") == "crash":
        raise RuntimeError("builder crashed after creating the folder")
    return Result({"payload.txt": "sha"})

def verify(output, files, meta):
    bad = ["payload.txt"] if os.environ.get("FAKE_BUILD") == "mismatch" else []
    return {"missing": [], "orphans": [], "mismatch": bad, "meta": []}
'''
LAUNCHER = '''
from pathlib import Path
def _resolve_slot(container, slot, release_id):
    folder = Path(container) / "releases" / release_id
    if (folder / "BROKEN").exists():
        raise SystemExit("exact-tree mismatch " + release_id)
    return folder
'''


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                          capture_output=True, text=True, encoding="utf-8", check=True)
    return done.stdout.strip()


class World:
    def __init__(self, base: Path) -> None:
        self.root = base / "root"
        self.root.mkdir()
        _git(self.root, "init", "-q", "-b", "main")
        project = self.root / PROJECT_DIR
        (project / "scripts").mkdir(parents=True)
        (project / "pyproject.toml").write_text('version = "1.3.3"\n', encoding="utf-8")
        (project / "scripts" / "pmf_build.py").write_text(FAKE_BUILDER, encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "release point")
        self.commit = _git(self.root, "rev-parse", "HEAD")
        self.container = self.root / CONTAINER
        (self.container / "launcher").mkdir(parents=True)
        (self.container / "launcher" / "bootstrap.py").write_text(LAUNCHER, encoding="utf-8")
        for release in ("1.3.2-aaaaaaa", "1.3.1-bbbbbbb"):
            (self.container / "releases" / release).mkdir(parents=True)
        self.set_pointers(active="1.3.2-aaaaaaa", previous="1.3.1-bbbbbbb")
        (self.container / "deployment_manifest.json").write_text(
            json.dumps({"schema_version": "deployment_manifest.v1", "releases": {"1.3.2-aaaaaaa": {}, "1.3.1-bbbbbbb": {}}}), encoding="utf-8")
        self.new_id = f"1.3.3-{self.commit[:7]}"

    def set_pointers(self, *, active: str, previous: str) -> None:
        for slot, release in (("active_release.json", active), ("previous_release.json", previous)):
            (self.container / slot).write_text(json.dumps({"release_id": release}), encoding="utf-8")

    def pointers(self) -> tuple[str, str]:
        return ops.pointer_release(self.container, "active_release.json"), ops.pointer_release(self.container, "previous_release.json")

    def manifest_bytes(self) -> bytes:
        return (self.container / "deployment_manifest.json").read_bytes()

    def identity(self, root: Path) -> dict[str, Any]:
        active = ops.pointer_release(self.container, "active_release.json")
        return {"configured_release_id": active, "effective_release_id": active, "runtime_fallback_reason": ""}


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def test_build_installs_the_release_and_writes_the_manifest_entry_but_moves_no_pointer(world: World) -> None:
    result = ops.build(world.root, world.root, world.commit)

    assert result["release_id"] == world.new_id and result["files"] == 1
    assert (world.container / "releases" / world.new_id / "payload.txt").is_file()
    manifest = json.loads(world.manifest_bytes())
    assert world.new_id in manifest["releases"], "the entry is written at build time, before any switch"
    assert world.pointers() == ("1.3.2-aaaaaaa", "1.3.1-bbbbbbb")
    assert len(result["entry_sha256"]) == 64


def test_build_refuses_an_existing_slot_and_an_existing_manifest_entry_without_changing_anything(world: World) -> None:
    (world.container / "releases" / world.new_id).mkdir()
    before = world.manifest_bytes()
    with pytest.raises(ops.ReleaseOpsError, match="已存在"):
        ops.build(world.root, world.root, world.commit)
    assert world.manifest_bytes() == before and (world.container / "releases" / world.new_id).is_dir() and not any((world.container / "releases" / world.new_id).iterdir())

    (world.container / "releases" / world.new_id).rmdir()
    manifest = json.loads(before)
    manifest["releases"][world.new_id] = {}
    (world.container / "deployment_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ops.ReleaseOpsError, match="已存在"):
        ops.build(world.root, world.root, world.commit)


def test_a_build_that_crashes_after_creating_the_folder_leaves_no_folder_and_the_old_manifest(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """The script left the half-built folder behind; the port removes it."""

    monkeypatch.setenv("FAKE_BUILD", "crash")
    before = world.manifest_bytes()

    with pytest.raises(RuntimeError, match="crashed"):
        ops.build(world.root, world.root, world.commit)

    assert not (world.container / "releases" / world.new_id).exists()
    assert world.manifest_bytes() == before


def test_a_build_that_fails_its_own_verification_after_the_manifest_was_written_is_undone(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_BUILD", "mismatch")
    before = world.manifest_bytes()

    with pytest.raises(ops.ReleaseOpsError, match="逐文件校验没过"):
        ops.build(world.root, world.root, world.commit)

    assert not (world.container / "releases" / world.new_id).exists()
    assert world.manifest_bytes() == before, "the entry that was already written is taken out again"


def test_build_refuses_a_manifest_of_another_schema(world: World) -> None:
    (world.container / "deployment_manifest.json").write_text(json.dumps({"schema_version": "v0", "releases": {}}), encoding="utf-8")

    with pytest.raises(ops.ReleaseOpsError, match="schema_version"):
        ops.build(world.root, world.root, world.commit)


def _built(world: World) -> str:
    return str(ops.build(world.root, world.root, world.commit)["release_id"])


def test_switch_backs_up_then_writes_previous_before_active(world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    new = _built(world)
    order: list[str] = []
    real = ops._write_pointer

    def recording(container: Path, slot: str, release: str) -> None:
        order.append(slot)
        real(container, slot, release)

    monkeypatch.setattr(ops, "_write_pointer", recording)
    backup = tmp_path / "backup"

    result = ops.switch(world.root, new, "1.3.2-aaaaaaa", backup, world.identity)

    assert order == ["previous_release.json", "active_release.json"]
    assert world.pointers() == (new, "1.3.2-aaaaaaa") and result["active"] == new
    names = sorted(p.name for p in backup.iterdir())
    assert names == ["SHA256SUMS", "active_release.json", "deployment_manifest.json", "previous_release.json"]
    assert ops.pointer_release(backup, "active_release.json") == "1.3.2-aaaaaaa", "the backup holds the pointers as they were"


@pytest.mark.parametrize("problem", ["wrong_old", "new_broken", "old_broken", "backup_exists"])
def test_switch_refuses_before_writing_anything(world: World, tmp_path: Path, problem: str) -> None:
    new = _built(world)
    backup = tmp_path / "backup"
    old = "1.3.2-aaaaaaa"
    if problem == "wrong_old":
        old = "1.3.1-bbbbbbb"
    elif problem == "new_broken":
        (world.container / "releases" / new / "BROKEN").write_text("", encoding="utf-8")
    elif problem == "old_broken":
        (world.container / "releases" / "1.3.2-aaaaaaa" / "BROKEN").write_text("", encoding="utf-8")
    else:
        backup.mkdir()
    pointers, manifest = world.pointers(), world.manifest_bytes()

    with pytest.raises(ops.ReleaseOpsError):
        ops.switch(world.root, new, old, backup, world.identity)

    assert world.pointers() == pointers and world.manifest_bytes() == manifest
    assert not (backup / "SHA256SUMS").exists()


def test_a_wrong_runtime_identity_after_the_switch_is_an_error_and_the_backup_can_undo_it(world: World, tmp_path: Path) -> None:
    new = _built(world)
    backup = tmp_path / "backup"
    wrong = lambda _root: {"configured_release_id": new, "effective_release_id": "1.3.2-aaaaaaa", "runtime_fallback_reason": "fell back"}  # noqa: E731

    with pytest.raises(ops.ReleaseOpsError, match="运行身份"):
        ops.switch(world.root, new, "1.3.2-aaaaaaa", backup, wrong)
    assert world.pointers() == (new, "1.3.2-aaaaaaa"), "the pointers are switched; the caller rolls back"

    ops.rollback(world.root, backup, world.identity)
    assert world.pointers() == ("1.3.2-aaaaaaa", "1.3.1-bbbbbbb")


def test_rollback_restores_only_the_pointers_and_keeps_the_installed_release(world: World, tmp_path: Path) -> None:
    new = _built(world)
    backup = tmp_path / "backup"
    ops.switch(world.root, new, "1.3.2-aaaaaaa", backup, world.identity)
    manifest_after_build = world.manifest_bytes()

    result = ops.rollback(world.root, backup, world.identity)

    assert result["active"] == "1.3.2-aaaaaaa" and world.pointers() == ("1.3.2-aaaaaaa", "1.3.1-bbbbbbb")
    assert world.manifest_bytes() == manifest_after_build, "the manifest is not rolled back"
    assert (world.container / "releases" / new).is_dir(), "the installed release stays installed"


def test_rollback_refuses_a_tampered_or_missing_backup_without_touching_the_pointers(world: World, tmp_path: Path) -> None:
    new = _built(world)
    backup = tmp_path / "backup"
    ops.switch(world.root, new, "1.3.2-aaaaaaa", backup, world.identity)
    switched = world.pointers()

    (backup / "active_release.json").write_text(json.dumps({"release_id": "9.9.9-evil"}), encoding="utf-8")
    with pytest.raises(ops.ReleaseOpsError, match="被改过"):
        ops.rollback(world.root, backup, world.identity)
    assert world.pointers() == switched

    with pytest.raises(ops.ReleaseOpsError, match="SHA256SUMS"):
        ops.rollback(world.root, tmp_path / "nowhere", world.identity)
    assert world.pointers() == switched


def test_a_rollback_whose_identity_is_not_the_old_release_is_an_error(world: World, tmp_path: Path) -> None:
    new = _built(world)
    backup = tmp_path / "backup"
    ops.switch(world.root, new, "1.3.2-aaaaaaa", backup, world.identity)

    with pytest.raises(ops.ReleaseOpsError, match="回退后运行身份"):
        ops.rollback(world.root, backup, lambda _root: {"configured_release_id": new, "effective_release_id": new, "runtime_fallback_reason": ""})
