"""D-05: ``release trial`` copies the active release out of the workspace and touches nothing in it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from auto_pm.application.core.release_trial_service import ReleaseTrialError, ReleaseTrialService


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _workspace(tmp_path: Path, *, release_path: str = "1.0.0-abc") -> Path:
    root = tmp_path / "ws"
    release = root / "00_Infrastructure" / "auto_pm" / "releases" / "1.0.0-abc"
    (release / "auto_pm" / "__pycache__").mkdir(parents=True)
    (release / "auto_pm" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (release / "auto_pm" / "mod.py").write_text("y = 2\n", encoding="utf-8")
    (release / "auto_pm" / "__pycache__" / "mod.cpython-312.pyc").write_bytes(b"cache")
    (release / "release_meta.json").write_text("{}", encoding="utf-8")
    pointer = root / "00_Infrastructure" / "auto_pm" / "active_release.json"
    pointer.write_text(
        json.dumps({"release_id": "1.0.0-abc", "release_path": release_path}), encoding="utf-8"
    )
    return root


def test_the_copy_has_the_code_but_no_bytecode_and_leaves_the_workspace_untouched(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    before = _tree_hash(root)

    copy = ReleaseTrialService(root).make_copy(scratch)

    assert copy.release_id == "1.0.0-abc"
    assert (copy.destination / "auto_pm" / "mod.py").read_text(encoding="utf-8") == "y = 2\n"
    assert not list(copy.destination.rglob("__pycache__")) and not list(copy.destination.rglob("*.pyc"))
    assert copy.files == 3
    assert _tree_hash(root) == before
    assert scratch in copy.destination.parents
    assert "python -B" in copy.run_hint and str(copy.destination) in copy.run_hint


def test_each_call_makes_its_own_folder(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    service = ReleaseTrialService(root)

    assert service.make_copy(scratch).destination != service.make_copy(scratch).destination


def test_a_destination_inside_the_workspace_is_refused(tmp_path: Path) -> None:
    root = _workspace(tmp_path)

    with pytest.raises(ReleaseTrialError, match="工作区里面"):
        ReleaseTrialService(root).make_copy(root / "00_Infrastructure")
    with pytest.raises(ReleaseTrialError, match="工作区里面"):
        ReleaseTrialService(root).make_copy(root)


@pytest.mark.parametrize("bad", ["../escape", "a/b", "..", "."])
def test_a_pointer_that_leaves_releases_is_refused(tmp_path: Path, bad: str) -> None:
    root = _workspace(tmp_path, release_path=bad)

    with pytest.raises(ReleaseTrialError, match="单层目录名"):
        ReleaseTrialService(root).active_release_dir()


def test_a_missing_pointer_or_release_says_so(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ReleaseTrialError, match="读不出"):
        ReleaseTrialService(empty).active_release_dir()
    root = _workspace(tmp_path, release_path="9.9.9-none")
    with pytest.raises(ReleaseTrialError, match="不存在"):
        ReleaseTrialService(root).active_release_dir()
