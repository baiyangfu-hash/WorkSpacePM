"""NG-WP-15 isolated release-entry acceptance tests."""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

LAUNCHER_DIR = Path(__file__).resolve().parents[1] / "00_Infrastructure" / "auto_pm" / "launcher"
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
CONTAINER_ROOT = WORKSPACE_ROOT / "00_Infrastructure" / "auto_pm"
sys.path.insert(0, str(LAUNCHER_DIR))
from bootstrap import (  # type: ignore[import-not-found]
    ACTIVE_POINTER,
    EXIT_POINTER_INVALID,
    EXIT_RELEASE_INVALID,
    MANIFEST_FILE,
    MANIFEST_SCHEMA,
    POINTER_SCHEMA,
    PREVIOUS_POINTER,
    RELEASES_DIR,
    BootstrapError,
    resolve_with_fallback,
)
from launch import main as launcher_main  # type: ignore[import-not-found]


def _git_bytes(*arguments: str, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(WORKSPACE_ROOT), *arguments],
        input=input_bytes,
        capture_output=True,
        check=True,
    )
    return result.stdout


def _index_entries(release_root: str) -> dict[str, str]:
    output = _git_bytes("ls-files", "--stage", "-z", "--", release_root)
    entries: dict[str, str] = {}
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        _mode, raw_oid, raw_stage = metadata.split()
        assert raw_stage == b"0"
        path = raw_path.decode(encoding="utf-8", errors="replace")
        entries[path] = raw_oid.decode(encoding="ascii")
    return entries


def _read_git_blobs(object_ids: set[str]) -> dict[str, bytes]:
    ordered = sorted(object_ids)
    output = _git_bytes(
        "cat-file",
        "--batch",
        input_bytes=("\n".join(ordered) + "\n").encode(encoding="ascii"),
    )
    blobs: dict[str, bytes] = {}
    cursor = 0
    for requested_oid in ordered:
        header_end = output.index(b"\n", cursor)
        header = output[cursor:header_end].decode(encoding="ascii").split()
        actual_oid, object_type, raw_size = header
        assert actual_oid == requested_oid
        assert object_type == "blob"
        size = int(raw_size)
        start = header_end + 1
        end = start + size
        blobs[requested_oid] = output[start:end]
        assert output[end : end + 1] == b"\n"
        cursor = end + 1
    assert cursor == len(output)
    return blobs


def _operational_release_files() -> list[tuple[str, dict[str, str]]]:
    manifest = json.loads(
        (CONTAINER_ROOT / MANIFEST_FILE).read_text(
            encoding="utf-8", errors="replace"
        )
    )
    releases: list[tuple[str, dict[str, str]]] = []
    for pointer_name in (ACTIVE_POINTER, PREVIOUS_POINTER):
        pointer = json.loads(
            (CONTAINER_ROOT / pointer_name).read_text(
                encoding="utf-8", errors="replace"
            )
        )
        release_id = pointer.get("release_id")
        assert isinstance(release_id, str) and release_id
        files = manifest["releases"][release_id]["files"]
        assert isinstance(files, dict) and files
        releases.append((release_id, files))
    return releases


def _pointer(release_id: str | None) -> dict[str, object]:
    return {"schema_version": POINTER_SCHEMA, "slot": "", "release_id": release_id}


def _write_pointer(root: Path, name: str, release_id: str | None) -> None:
    payload = _pointer(release_id)
    payload["slot"] = name
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def _add_release(root: Path, release_id: str, *, marker_program: bool = False) -> dict[str, str]:
    release = root / RELEASES_DIR / release_id
    package = release / "auto_pm"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("__version__ = 'test'\n", encoding="utf-8")
    if marker_program:
        program = (
            "import os\nfrom pathlib import Path\n"
            "Path(os.environ['AUTO_PM_TEST_MARKER']).write_text(str(Path(__file__).resolve()), encoding='utf-8')\n"
        )
    else:
        program = "raise SystemExit(0)\n"
    (package / "__main__.py").write_text(program, encoding="utf-8")
    files: dict[str, str] = {}
    for path in release.rglob("*"):
        if path.is_file():
            files[path.relative_to(release).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def _container(tmp_path: Path, active: str | None = "active", previous: str | None = None) -> tuple[Path, dict[str, dict[str, str]]]:
    root = tmp_path / "container"
    (root / RELEASES_DIR).mkdir(parents=True)
    releases = {"active": _add_release(root, "active"), "previous": _add_release(root, "previous")}
    (root / MANIFEST_FILE).write_text(
        json.dumps({"schema_version": MANIFEST_SCHEMA, "releases": {key: {"files": value} for key, value in releases.items()}}),
        encoding="utf-8",
    )
    _write_pointer(root, ACTIVE_POINTER, active)
    _write_pointer(root, PREVIOUS_POINTER, previous)
    return root, releases


def test_valid_release_executes_only_from_verified_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, releases = _container(tmp_path)
    releases["active"] = _add_release(root, "active", marker_program=True)
    (root / MANIFEST_FILE).write_text(
        json.dumps({"schema_version": MANIFEST_SCHEMA, "releases": {key: {"files": value} for key, value in releases.items()}}),
        encoding="utf-8",
    )
    marker = tmp_path / "provenance.txt"
    monkeypatch.setenv("AUTO_PM_TEST_MARKER", str(marker))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "untrusted"))
    assert launcher_main([], container=root) == 0
    assert marker.read_text(encoding="utf-8") == str((root / RELEASES_DIR / "active" / "auto_pm" / "__main__.py").resolve())
    assert not list((root / RELEASES_DIR / "active").rglob("__pycache__"))


def test_release_child_preserves_user_arguments_without_release_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, releases = _container(tmp_path)
    release = root / RELEASES_DIR / "active" / "auto_pm" / "__main__.py"
    release.write_text(
        "import os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['AUTO_PM_TEST_ARGS']).write_text(repr(sys.argv[1:]), encoding='utf-8')\n",
        encoding="utf-8",
    )
    releases["active"] = {
        path.relative_to(root / RELEASES_DIR / "active").as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (root / RELEASES_DIR / "active").rglob("*")
        if path.is_file()
    }
    (root / MANIFEST_FILE).write_text(
        json.dumps({"schema_version": MANIFEST_SCHEMA, "releases": {key: {"files": value} for key, value in releases.items()}}),
        encoding="utf-8",
    )
    args_file = tmp_path / "args.txt"
    monkeypatch.setenv("AUTO_PM_TEST_ARGS", str(args_file))
    assert launcher_main(["--help"], container=root) == 0
    assert args_file.read_text(encoding="utf-8") == "['--help']"


def test_tampered_active_release_fails_closed(tmp_path: Path) -> None:
    root, _ = _container(tmp_path, previous=None)
    (root / RELEASES_DIR / "active" / "auto_pm" / "__init__.py").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(BootstrapError, match="SHA-256 不匹配") as error:
        resolve_with_fallback(root)
    assert error.value.exit_code == EXIT_RELEASE_INVALID


def test_extra_payload_node_fails_closed(tmp_path: Path) -> None:
    root, _ = _container(tmp_path, previous=None)
    (root / RELEASES_DIR / "active" / "unexpected.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(BootstrapError, match="未登记文件") as error:
        resolve_with_fallback(root)
    assert error.value.exit_code == EXIT_RELEASE_INVALID


def test_null_pointers_fail_closed(tmp_path: Path) -> None:
    root, _ = _container(tmp_path, active=None, previous=None)
    with pytest.raises(BootstrapError, match="未初始化") as error:
        resolve_with_fallback(root)
    assert error.value.exit_code == EXIT_POINTER_INVALID


def test_invalid_active_falls_back_to_exact_verified_previous(tmp_path: Path) -> None:
    root, _ = _container(tmp_path, active="active", previous="previous")
    (root / RELEASES_DIR / "active" / "extra.txt").write_text("extra", encoding="utf-8")
    release, slot = resolve_with_fallback(root)
    assert slot == PREVIOUS_POINTER
    assert release == (root / RELEASES_DIR / "previous").resolve()


def test_payload_symlink_or_reparse_fails_closed(tmp_path: Path) -> None:
    root, _ = _container(tmp_path, previous=None)
    link = root / RELEASES_DIR / "active" / "payload-link"
    try:
        link.symlink_to(root / RELEASES_DIR / "active" / "auto_pm", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"host disallows symlink creation: {exc}")
    with pytest.raises(BootstrapError, match="链接或重解析点"):
        resolve_with_fallback(root)


def test_operational_release_payloads_are_git_byte_opaque() -> None:
    paths = [
        f"00_Infrastructure/auto_pm/releases/{release_id}/{relative}"
        for release_id, files in _operational_release_files()
        for relative in files
    ]
    output = _git_bytes(
        "-c",
        "core.quotePath=false",
        "check-attr",
        "--stdin",
        "text",
        input_bytes=("\n".join(paths) + "\n").encode(encoding="utf-8"),
    ).decode(encoding="utf-8", errors="replace")
    records = output.splitlines()

    assert len(records) == len(paths)
    for expected_path, record in zip(paths, records, strict=True):
        actual_path, attribute, value = record.rsplit(": ", 2)
        assert actual_path == expected_path
        assert attribute == "text"
        assert value == "unset", f"{actual_path}: release payload must be -text"


def test_operational_release_worktree_and_index_blobs_match_manifest() -> None:
    for release_id, files in _operational_release_files():
        release_prefix = f"00_Infrastructure/auto_pm/releases/{release_id}"
        expected_paths = {
            f"{release_prefix}/{relative}": expected
            for relative, expected in files.items()
        }
        index_entries = _index_entries(release_prefix)
        assert set(index_entries) == set(expected_paths)
        blobs = _read_git_blobs(set(index_entries.values()))

        for relative_path, expected_sha256 in expected_paths.items():
            worktree_bytes = (WORKSPACE_ROOT / relative_path).read_bytes()
            index_bytes = blobs[index_entries[relative_path]]
            assert hashlib.sha256(worktree_bytes).hexdigest() == expected_sha256
            assert hashlib.sha256(index_bytes).hexdigest() == expected_sha256


def test_root_entry_has_no_parent_auto_pm_import() -> None:
    root_entry = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(root_entry.read_text(encoding="utf-8"))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    )
    assert not any(name == "auto_pm" or name.startswith("auto_pm.") for name in imported_modules)
