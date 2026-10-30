"""F01-a Git marker guard: direct evidence for each reject branch (TD-SW008-094 ③).

Each case feeds one hostile Git answer to the guard and requires a ``GitMarkerGuardError``; the happy path is pinned
alongside so a branch that always raises (or never raises) turns something red.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from auto_pm.infrastructure import plc_git_marker_guard as guard

OID = "a" * 40
OID2 = "b" * 40
ROOT = Path("/unused")


def _result(stdout: str, code: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=code, stdout=stdout, stderr=stderr)


def _answer(monkeypatch: pytest.MonkeyPatch, stdout: str, code: int = 0, stderr: str = "") -> None:
    monkeypatch.setattr(guard, "_git", lambda root, *args: _result(stdout, code, stderr))


@pytest.mark.parametrize("text", ["a\0b", "a\0b\0�\0", "bad�name\0"])
def test_nul_records_reject_truncated_or_lossy_listings(text: str) -> None:
    with pytest.raises(guard.GitMarkerGuardError, match="不完整或编码无效"):
        guard._nul_records(text)


def test_nul_records_accept_a_complete_listing_and_the_empty_one() -> None:
    assert guard._nul_records("") == []
    assert guard._nul_records("a\0b\0") == ["a", "b"]


@pytest.mark.parametrize("path", ["/abs/.plc.json", "../x/.plc.json", "a\\b\\.plc.json", ""])
def test_marker_path_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(guard.GitMarkerGuardError, match="不安全"):
        guard._marker_path(path)


def test_marker_path_keeps_a_normal_relative_path() -> None:
    assert guard._marker_path("0100/DJ-1/.plc.json") == "0100/DJ-1/.plc.json"


def test_head_markers_collect_regular_blobs_only_for_marker_files(monkeypatch: pytest.MonkeyPatch) -> None:
    listing = f"100644 blob {OID}\t0100/DJ-1/.plc.json\x00100644 blob {OID2}\t0100/DJ-1/readme.md\x00"
    _answer(monkeypatch, listing)
    assert guard._head_markers(ROOT, OID) == frozenset({"0100/DJ-1/.plc.json"})
    assert guard._head_markers(ROOT, None) == frozenset()


@pytest.mark.parametrize(
    "record",
    [
        f"120000 blob {OID}\tp/.plc.json",  # symlink mode
        f"160000 commit {OID}\tp/.plc.json",  # submodule
        f"100644 tree {OID}\tp/.plc.json",  # not a blob
        "100644 blob nothex\tp/.plc.json",  # bad object id
        f"100644 blob {OID} extra\tp/.plc.json",  # wrong field count
    ],
)
def test_head_markers_reject_a_marker_that_is_not_a_regular_file(monkeypatch: pytest.MonkeyPatch, record: str) -> None:
    _answer(monkeypatch, record + "\0")
    with pytest.raises(guard.GitMarkerGuardError, match="不是普通文件"):
        guard._head_markers(ROOT, OID)


def test_head_markers_reject_an_entry_without_a_tab_and_a_failed_read(monkeypatch: pytest.MonkeyPatch) -> None:
    _answer(monkeypatch, f"100644 blob {OID} p/.plc.json\0")
    with pytest.raises(guard.GitMarkerGuardError, match="格式无效"):
        guard._head_markers(ROOT, OID)
    _answer(monkeypatch, "", code=128, stderr="fatal")
    with pytest.raises(guard.GitMarkerGuardError, match="读取 HEAD marker 树"):
        guard._head_markers(ROOT, OID)


def test_head_markers_reject_a_truncated_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    _answer(monkeypatch, f"100644 blob {OID}\tp/.plc.json")  # no trailing NUL
    with pytest.raises(guard.GitMarkerGuardError, match="不完整或编码无效"):
        guard._head_markers(ROOT, OID)


def test_index_markers_collect_stage_zero_regular_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    _answer(monkeypatch, f"100755 {OID} 0\tp/.plc.json\0")
    assert guard._index_markers(ROOT) == frozenset({("p/.plc.json", OID)})


@pytest.mark.parametrize(
    "record",
    [
        f"100644 {OID} 1\tp/.plc.json",  # merge conflict stage
        f"100644 {OID} 2\tp/.plc.json",
        f"120000 {OID} 0\tp/.plc.json",  # symlink
        "100644 nothex 0\tp/.plc.json",
        f"100644 {OID} 0 x\tp/.plc.json",  # wrong field count
        f"100644 {OID} 0 p/.plc.json",  # no tab
    ],
)
def test_index_markers_reject_conflicts_and_non_files(monkeypatch: pytest.MonkeyPatch, record: str) -> None:
    _answer(monkeypatch, record + "\0")
    with pytest.raises(guard.GitMarkerGuardError, match="不是完整的普通文件条目"):
        guard._index_markers(ROOT)


def test_index_markers_reject_a_truncated_listing_and_a_failed_read(monkeypatch: pytest.MonkeyPatch) -> None:
    _answer(monkeypatch, f"100644 {OID} 0\tp/.plc.json")
    with pytest.raises(guard.GitMarkerGuardError, match="不完整或编码无效"):
        guard._index_markers(ROOT)
    _answer(monkeypatch, "", code=1, stderr="boom")
    with pytest.raises(guard.GitMarkerGuardError, match="读取 index marker 清单"):
        guard._index_markers(ROOT)


def _stub_repo(monkeypatch: pytest.MonkeyPatch, *, heads: list[str | None], indexes: list[frozenset[tuple[str, str]]]) -> None:
    head_calls = iter(heads)
    index_calls = iter(indexes)
    monkeypatch.setattr(guard, "_repository_root", lambda directory, allow_non_git: ROOT)
    monkeypatch.setattr(guard, "_head_commit", lambda root: next(head_calls))
    monkeypatch.setattr(guard, "_index_markers", lambda root: next(index_calls))
    monkeypatch.setattr(guard, "_head_markers", lambda root, oid: frozenset({"p/.plc.json", "q/.plc.json"}))


def test_removed_index_markers_name_every_head_marker_missing_from_the_index(monkeypatch: pytest.MonkeyPatch) -> None:
    index = frozenset({("q/.plc.json", OID)})
    _stub_repo(monkeypatch, heads=[OID, OID], indexes=[index, index])
    assert guard.removed_index_markers(ROOT) == ("p/.plc.json",)


def test_removed_index_markers_reject_index_drift_between_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    before = frozenset({("q/.plc.json", OID)})
    after = frozenset({("q/.plc.json", OID2)})
    _stub_repo(monkeypatch, heads=[OID, OID], indexes=[before, after])
    with pytest.raises(guard.GitMarkerGuardError, match="发生漂移"):
        guard.removed_index_markers(ROOT)


def test_removed_index_markers_reject_head_drift_between_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    index = frozenset({("q/.plc.json", OID)})
    _stub_repo(monkeypatch, heads=[OID, OID2], indexes=[index, index])
    with pytest.raises(guard.GitMarkerGuardError, match="发生漂移"):
        guard.removed_index_markers(ROOT)


def test_marker_in_head_rejects_head_drift_and_otherwise_answers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "p"
    project.mkdir()
    monkeypatch.setattr(guard, "_repository_root", lambda directory, allow_non_git: tmp_path.resolve())
    monkeypatch.setattr(guard, "_head_markers", lambda root, oid: frozenset({"p/.plc.json"}))
    heads = iter([OID, OID])
    monkeypatch.setattr(guard, "_head_commit", lambda root: next(heads))
    assert guard.marker_in_head(tmp_path, project) is True
    heads = iter([OID, OID2])
    monkeypatch.setattr(guard, "_head_commit", lambda root: next(heads))
    with pytest.raises(guard.GitMarkerGuardError, match="发生漂移"):
        guard.marker_in_head(tmp_path, project)


def test_marker_in_head_rejects_a_project_outside_the_selected_workspace(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    with pytest.raises(guard.GitMarkerGuardError, match="不属于选定工作区"):
        guard.marker_in_head(workspace, outside)
