"""D02: the reproducible build entry ``scripts/pmf_build.py`` builds the release payload from a committed Git object only, refuses what it must refuse and gives the same manifest twice.

Most tests use a throw-away repository with a tiny project (hermetic). One golden test builds the real commit of the active release and compares it with the manifest recorded for it
(skipped, and reported as skipped, in a clone that does not have that commit).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pmf_build.py"
COMMIT_DATE = "2026-01-02T03:04:05+00:00"
EXPECTED_BUILT_AT = "2026-01-02T03:04:05+00:00"
ACTIVE_RELEASE = "1.3.3-4b5c630"
ACTIVE_COMMIT = "4b5c6307e814cd6bf17337f31ccd8c7e533553e1"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pmf_build_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pb = _load()
ENV = {**os.environ, "GIT_AUTHOR_DATE": COMMIT_DATE, "GIT_COMMITTER_DATE": COMMIT_DATE, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), "-c", "core.quotePath=false", *args], capture_output=True, env=ENV)
    assert done.returncode == 0, done.stderr.decode("utf-8", errors="replace")
    return done.stdout.decode("utf-8", errors="replace").strip()


BASE_FILES = {
    "pyproject.toml": '[project]\nname = "demo"\nversion = "9.9.9"\n',
    "auto_pm/__init__.py": "__version__ = '9.9.9'\n",
    "auto_pm/__main__.py": "from auto_pm.core.worker import run\n\nrun()\n",
    "auto_pm/application/core/__init__.py": "",
    "auto_pm/application/core/worker.py": "from auto_pm.domain.models.item import Item\n\n\ndef run() -> Item:\n    return Item()\n",
    "auto_pm/domain/models/__init__.py": "",
    "auto_pm/domain/models/item.py": "class Item:\n    pass\n",
    "templates/t/template/readme.txt": "template file\n",
}


def _make_repo(tmp_path: Path, root: str = "proj", files: dict[str, str] | None = None) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    for name, text in (files if files is not None else BASE_FILES).items():
        target = repo / root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "demo")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_pb01_two_builds_of_one_commit_have_the_same_manifest_and_meta_bytes(tmp_path: Path) -> None:
    repo, commit = _make_repo(tmp_path)
    first = pb.build(repo, commit, "proj", tmp_path / "out1")
    second = pb.build(repo, commit, "proj", tmp_path / "out2")
    assert first.files == second.files and list(first.files) == sorted(first.files)
    assert first.release_id == f"9.9.9-{commit[:7]}" and first.version == "9.9.9" and first.source_commit == commit
    assert first.built_at == EXPECTED_BUILT_AT
    assert (tmp_path / "out1" / "release_meta.json").read_bytes() == (tmp_path / "out2" / "release_meta.json").read_bytes()
    assert "release_meta.json" in first.files and "auto_pm/__main__.py" in first.files and "templates/t/template/readme.txt" in first.files
    assert first.manifest_entry() == second.manifest_entry()


def test_pb02_a_dirty_or_untracked_working_tree_does_not_change_the_result(tmp_path: Path) -> None:
    repo, commit = _make_repo(tmp_path)
    clean = pb.build(repo, commit, "proj", tmp_path / "clean")
    (repo / "proj" / "auto_pm" / "domain" / "models" / "item.py").write_text("class Item:\n    changed = True\n", encoding="utf-8")
    (repo / "proj" / "auto_pm" / "untracked_local_only.py").write_text("x = 1\n", encoding="utf-8")
    dirty = pb.build(repo, commit, "proj", tmp_path / "dirty")
    assert dirty.files == clean.files
    assert not (tmp_path / "dirty" / "auto_pm" / "untracked_local_only.py").exists()


def test_pb03_a_revision_that_is_not_a_commit_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    repo, _commit = _make_repo(tmp_path)
    with pytest.raises(pb.BuildError) as caught:
        pb.build(repo, "no-such-revision", "proj", tmp_path / "out")
    assert caught.value.code == "not-a-commit"
    assert not (tmp_path / "out").exists()


def test_pb04_a_payload_without_templates_is_refused(tmp_path: Path) -> None:
    files = {k: v for k, v in BASE_FILES.items() if not k.startswith("templates/")}
    repo, commit = _make_repo(tmp_path, files=files)
    with pytest.raises(pb.BuildError) as caught:
        pb.build(repo, commit, "proj", tmp_path / "out")
    assert caught.value.code == "missing-payload-dir" and "templates" in caught.value.details
    assert not (tmp_path / "out").exists()


def test_pb05_a_payload_without_the_main_entry_is_refused(tmp_path: Path) -> None:
    files = {k: v for k, v in BASE_FILES.items() if k != "auto_pm/__main__.py"}
    repo, commit = _make_repo(tmp_path, files=files)
    with pytest.raises(pb.BuildError) as caught:
        pb.build(repo, commit, "proj", tmp_path / "out")
    assert caught.value.code == "missing-required-file" and "auto_pm/__main__.py" in caught.value.details
    assert not (tmp_path / "out").exists()


def test_pb06_an_import_that_resolves_outside_the_payload_is_refused_with_the_module_named(tmp_path: Path) -> None:
    files = dict(BASE_FILES)
    files["auto_pm/application/core/worker.py"] = "from auto_pm.domain.models.item import Item\nfrom auto_pm.infrastructure.only_on_my_machine import helper\n\n\ndef run() -> Item:\n    return Item()\n"
    repo, commit = _make_repo(tmp_path, files=files)
    with pytest.raises(pb.BuildError) as caught:
        pb.build(repo, commit, "proj", tmp_path / "out")
    assert caught.value.code == "unresolved-import" and "auto_pm.infrastructure.only_on_my_machine" in caught.value.details
    assert not (tmp_path / "out").exists()


def test_pb07_an_existing_output_directory_is_refused_and_left_untouched(tmp_path: Path) -> None:
    repo, commit = _make_repo(tmp_path)
    existing = tmp_path / "out"
    existing.mkdir()
    (existing / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(pb.BuildError) as caught:
        pb.build(repo, commit, "proj", existing)
    assert caught.value.code == "output-exists"
    assert [p.name for p in existing.iterdir()] == ["keep.txt"]


def test_pb08_committed_bytecode_and_pycache_never_reach_the_payload(tmp_path: Path) -> None:
    repo, _commit = _make_repo(tmp_path)
    cache = repo / "proj" / "auto_pm" / "__pycache__"
    cache.mkdir()
    (cache / "x.cpython-312.pyc").write_bytes(b"\x00\x01")
    (repo / "proj" / "auto_pm" / "stray.pyc").write_bytes(b"\x02")
    _git(repo, "add", "-f", "-A")
    _git(repo, "commit", "-q", "-m", "add bytecode")
    result = pb.build(repo, "HEAD", "proj", tmp_path / "out")
    assert not [name for name in result.files if "__pycache__" in name or name.endswith(".pyc")]


def test_pb09_verify_accepts_a_fresh_build_and_reports_a_changed_a_missing_and_an_extra_file(tmp_path: Path) -> None:
    repo, commit = _make_repo(tmp_path)
    result = pb.build(repo, commit, "proj", tmp_path / "out")
    assert pb.verify(tmp_path / "out", result.files) == {"missing": [], "orphans": [], "mismatch": [], "files": [str(len(result.files))]}
    (tmp_path / "out" / "auto_pm" / "domain" / "models" / "item.py").write_text("class Item:\n    tampered = 1\n", encoding="utf-8")
    (tmp_path / "out" / "templates" / "t" / "template" / "readme.txt").unlink()
    (tmp_path / "out" / "auto_pm" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    report = pb.verify(tmp_path / "out", result.files)
    assert report["mismatch"] == ["auto_pm/domain/models/item.py"]
    assert report["missing"] == ["templates/t/template/readme.txt"]
    assert report["orphans"] == ["auto_pm/extra.py"]


def test_pb10_a_project_root_with_non_ascii_characters_builds(tmp_path: Path) -> None:
    repo, commit = _make_repo(tmp_path, root="项目/自动化工具")
    result = pb.build(repo, commit, "项目/自动化工具", tmp_path / "out")
    assert result.version == "9.9.9" and "auto_pm/__init__.py" in result.files


def test_pb11_the_command_line_returns_0_on_success_and_2_on_a_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo, commit = _make_repo(tmp_path)
    assert pb.main(["build", "--repo", str(repo), "--commit", commit, "--project-root", "proj", "--output", str(tmp_path / "out")]) == 0
    ok = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert ok["ok"] is True and ok["files"] == 6 + 1 + 1  # 7 payload files of the demo project + release_meta.json
    assert pb.main(["build", "--repo", str(repo), "--commit", commit, "--project-root", "proj", "--output", str(tmp_path / "out")]) == 2
    refused = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert refused["ok"] is False and refused["code"] == "output-exists"
    assert pb.main(["verify", "--output", str(tmp_path / "out")]) == 0


def test_pb12_the_release_meta_carries_the_commit_the_version_and_the_commit_time(tmp_path: Path) -> None:
    repo, commit = _make_repo(tmp_path)
    pb.build(repo, commit, "proj", tmp_path / "out", release_id="custom-1")
    meta = json.loads((tmp_path / "out" / "release_meta.json").read_text(encoding="utf-8"))
    assert meta["schema_version"] == "release_metadata.v1" and meta["release_id"] == "custom-1"
    assert meta["source_commit"] == commit and meta["version"] == "9.9.9" and meta["built_at"] == EXPECTED_BUILT_AT


def test_pb13_golden_the_active_release_commit_rebuilds_to_the_recorded_manifest(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[2]
    top = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"], capture_output=True, text=True, encoding="utf-8")
    if top.returncode != 0:
        pytest.skip("UNVERIFIED: not inside a git work tree")
    repo = Path(top.stdout.strip())
    prefix = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-prefix"], capture_output=True, text=True, encoding="utf-8").stdout.strip().rstrip("/")
    has_commit = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{ACTIVE_COMMIT}^{{commit}}"], capture_output=True).returncode == 0
    manifest_path = repo / "00_Infrastructure" / "auto_pm" / "deployment_manifest.json"
    if not has_commit or not manifest_path.is_file():
        pytest.skip("UNVERIFIED: the commit of the active release or its recorded manifest is not in this clone")
    releases = json.loads(manifest_path.read_text(encoding="utf-8"))["releases"]
    if ACTIVE_RELEASE not in releases:
        pytest.skip("UNVERIFIED: the recorded manifest of the active release is a deployment record of the control root, not part of this commit")
    recorded = releases[ACTIVE_RELEASE]
    result = pb.build(repo, ACTIVE_COMMIT, prefix, tmp_path / "golden", release_id=ACTIVE_RELEASE)
    payload = {k: v for k, v in result.files.items() if k != "release_meta.json"}
    recorded_payload = {k: v for k, v in recorded["files"].items() if k != "release_meta.json"}
    assert payload == recorded_payload
    assert result.built_at == recorded["built_at"] and result.version == recorded["version"] and result.source_commit == recorded["source_commit"]
