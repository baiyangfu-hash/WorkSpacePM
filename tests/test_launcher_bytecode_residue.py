"""Launcher must never fall back quietly: bytecode residue stops it, other damage warns loudly."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

LAUNCHER_DIR = Path(__file__).resolve().parents[1] / "00_Infrastructure" / "auto_pm" / "launcher"
sys.path.insert(0, str(LAUNCHER_DIR))
from bootstrap import (  # type: ignore[import-not-found]
    ACTIVE_POINTER,
    EXIT_RELEASE_INVALID,
    MANIFEST_FILE,
    MANIFEST_SCHEMA,
    POINTER_SCHEMA,
    PREVIOUS_POINTER,
    PURGE_COMMAND,
    RELEASES_DIR,
    BootstrapError,
    BytecodeResidueError,
    purge_bytecode,
    resolve_release,
    resolve_with_fallback,
)
from launch import main as launcher_main  # type: ignore[import-not-found]


def _add_release(root: Path, release_id: str) -> dict[str, str]:
    package = root / RELEASES_DIR / release_id / "auto_pm"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("__version__ = 'test'\n", encoding="utf-8")
    (package / "__main__.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    return {
        f"auto_pm/{name}": hashlib.sha256((package / name).read_bytes()).hexdigest()
        for name in ("__init__.py", "__main__.py")
    }


def _container(tmp_path: Path, previous: str | None = "previous") -> Path:
    root = tmp_path / "container"
    (root / RELEASES_DIR).mkdir(parents=True)
    releases = {key: _add_release(root, key) for key in ("active", "previous")}
    (root / MANIFEST_FILE).write_text(
        json.dumps({"schema_version": MANIFEST_SCHEMA, "releases": {k: {"files": v} for k, v in releases.items()}}),
        encoding="utf-8",
    )
    for name, release_id in ((ACTIVE_POINTER, "active"), (PREVIOUS_POINTER, previous)):
        (root / name).write_text(
            json.dumps({"schema_version": POINTER_SCHEMA, "slot": name, "release_id": release_id}),
            encoding="utf-8",
        )
    return root


def _pycache(root: Path, release_id: str, *names: str) -> Path:
    cache = root / RELEASES_DIR / release_id / "auto_pm" / "__pycache__"
    cache.mkdir()
    for name in names:
        (cache / name).write_bytes(b"\x00bytecode")
    return cache


def test_bytecode_residue_in_active_stops_instead_of_falling_back(tmp_path: Path) -> None:
    root = _container(tmp_path)
    _pycache(root, "active", "__init__.cpython-312.pyc", "__main__.cpython-312.pyc")

    with pytest.raises(BytecodeResidueError) as error:
        resolve_release(root)

    assert error.value.exit_code == EXIT_RELEASE_INVALID
    assert error.value.residue == ("auto_pm/__pycache__",)
    assert PURGE_COMMAND in str(error.value)
    with pytest.raises(BytecodeResidueError):
        resolve_with_fallback(root)


def test_launcher_reports_residue_and_does_not_start_previous(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _container(tmp_path)
    _pycache(root, "active", "__init__.cpython-312.pyc")

    assert launcher_main(["--resolve-only"], container=root) == EXIT_RELEASE_INVALID

    captured = capsys.readouterr()
    assert "Python 缓存" in captured.err
    assert "--purge-bytecode" in captured.err
    assert "previous" not in captured.out


def test_cache_dir_with_non_bytecode_file_is_damage_not_residue(tmp_path: Path) -> None:
    """Counter-example: only plain *.pyc counts as residue; anything else stays generic damage."""
    root = _container(tmp_path, previous=None)
    _pycache(root, "active", "__init__.cpython-312.pyc", "notes.txt")

    with pytest.raises(BootstrapError, match="未登记目录") as error:
        resolve_release(root)

    assert not isinstance(error.value, BytecodeResidueError)


def test_other_damage_still_falls_back_but_says_why(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _container(tmp_path)
    (root / RELEASES_DIR / "active" / "extra.txt").write_text("extra", encoding="utf-8")

    resolution = resolve_release(root)
    assert resolution.slot == PREVIOUS_POINTER
    assert "未登记文件: extra.txt" in resolution.fallback_reason

    assert launcher_main(["--resolve-only"], container=root) == 0
    captured = capsys.readouterr()
    assert "警告" in captured.err and "已改用上一版本" in captured.err
    assert "未登记文件: extra.txt" in captured.err


def test_clean_active_has_no_fallback_reason(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _container(tmp_path)

    assert resolve_release(root).fallback_reason == ""
    assert launcher_main(["--resolve-only"], container=root) == 0
    assert capsys.readouterr().err == ""


def test_residue_in_previous_is_named_when_both_slots_fail(tmp_path: Path) -> None:
    root = _container(tmp_path)
    (root / RELEASES_DIR / "active" / "auto_pm" / "__init__.py").write_text("tampered\n", encoding="utf-8")
    _pycache(root, "previous", "__init__.cpython-312.pyc")

    with pytest.raises(BootstrapError, match="双槽均无效") as error:
        resolve_release(root)

    assert "SHA-256 不匹配" in str(error.value)
    assert PURGE_COMMAND in str(error.value)


def test_purge_removes_only_residue_then_active_verifies(tmp_path: Path) -> None:
    root = _container(tmp_path)
    _pycache(root, "active", "__init__.cpython-312.pyc")
    _pycache(root, "previous", "__main__.cpython-312.pyc")
    payload_before = {
        path: path.read_bytes() for path in (root / RELEASES_DIR).rglob("*.py")
    }

    removed = purge_bytecode(root)

    assert removed == ["active/auto_pm/__pycache__", "previous/auto_pm/__pycache__"]
    assert not list((root / RELEASES_DIR).rglob("__pycache__"))
    assert {path: path.read_bytes() for path in (root / RELEASES_DIR).rglob("*.py")} == payload_before
    resolution = resolve_release(root)
    assert (resolution.slot, resolution.fallback_reason) == (ACTIVE_POINTER, "")


def test_purge_refuses_to_touch_a_damaged_active(tmp_path: Path) -> None:
    root = _container(tmp_path)
    (root / RELEASES_DIR / "active" / "auto_pm" / "__init__.py").write_text("tampered\n", encoding="utf-8")
    cache = _pycache(root, "active", "__init__.cpython-312.pyc")

    with pytest.raises(BootstrapError, match="SHA-256 不匹配"):
        purge_bytecode(root)

    assert cache.is_dir()


def test_purge_leaves_non_bytecode_cache_dir_alone(tmp_path: Path) -> None:
    root = _container(tmp_path, previous=None)
    cache = _pycache(root, "active", "__init__.cpython-312.pyc", "notes.txt")

    with pytest.raises(BootstrapError, match="未登记目录"):
        purge_bytecode(root)

    assert sorted(child.name for child in cache.iterdir()) == ["__init__.cpython-312.pyc", "notes.txt"]


def test_launcher_purge_argument_cleans_and_verifies_without_starting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _container(tmp_path)
    _pycache(root, "active", "__init__.cpython-312.pyc")

    def forbidden_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("purge must not start the release")

    import launch  # type: ignore[import-not-found]

    monkeypatch.setattr(launch.subprocess, "run", forbidden_run)

    assert launcher_main(["--purge-bytecode"], container=root) == 0

    captured = capsys.readouterr()
    assert "已清除 1 处" in captured.out
    assert "release verified via active_release.json" in captured.out
    assert captured.err == ""


def _run_launcher_capturing_child(
    root: Path, monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    import launch  # type: ignore[import-not-found]

    class _Done:
        returncode = 0

    monkeypatch.setattr(launch.subprocess, "run", lambda *_a, **_k: _Done())
    assert launcher_main(args, container=root) == 0


def test_json_runs_keep_the_launcher_status_line_off_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # TD-SW008-031: `plc check --json` and every other --json command must leave stdout parseable.
    root = _container(tmp_path)

    _run_launcher_capturing_child(root, monkeypatch, ["plc", "check", "DJ-2026-005", "--json"])

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "release verified via active_release.json" in captured.err


def test_plain_runs_still_print_the_launcher_status_line_on_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _container(tmp_path)

    _run_launcher_capturing_child(root, monkeypatch, ["plc", "check", "DJ-2026-005"])

    captured = capsys.readouterr()
    assert "release verified via active_release.json" in captured.out
    assert captured.err == ""
