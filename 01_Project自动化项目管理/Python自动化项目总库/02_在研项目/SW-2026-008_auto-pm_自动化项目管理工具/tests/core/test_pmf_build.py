"""D02: the reproducible build entry ``scripts/pmf_build.py`` builds the release payload from a committed Git object only, refuses what it must refuse and gives the same manifest twice.

Most tests use a throw-away repository with a tiny project (hermetic). The golden test rebuilds the real commit of release 1.3.2-9d3c920, whose payload is committed under
``00_Infrastructure/auto_pm/releases/``, and compares it byte for byte (skipped, and reported as skipped, in a clone that does not have that commit or that payload).
"Reproducible" means: the payload files are byte-identical and ``release_meta.json`` is identical except ``builder.*``.
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
GOLDEN_RELEASE = "1.3.2-9d3c920"
GOLDEN_COMMIT = "9d3c92057a5dcdadbf1f1f693030ef9bc3c102a3"
GOLDEN_PROJECT_ROOT = "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具"
GOLDEN_COMMITTED = "00_Infrastructure/auto_pm/releases/" + GOLDEN_RELEASE


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
    assert pb.verify(tmp_path / "out", result.files) == {"missing": [], "orphans": [], "mismatch": [], "meta": [], "files": [str(len(result.files))]}
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


def test_pb13_the_builder_block_may_differ_between_machines_but_nothing_else(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, commit = _make_repo(tmp_path)
    first = pb.build(repo, commit, "proj", tmp_path / "one")
    monkeypatch.setattr(pb.platform, "python_version", lambda: "0.0.0-another-machine")
    second = pb.build(repo, commit, "proj", tmp_path / "two")
    meta_one = json.loads((tmp_path / "one" / "release_meta.json").read_text(encoding="utf-8"))
    meta_two = json.loads((tmp_path / "two" / "release_meta.json").read_text(encoding="utf-8"))
    assert meta_one["builder"] != meta_two["builder"]
    assert pb.meta_identity(meta_one) == pb.meta_identity(meta_two)
    assert pb.compare_meta(meta_one, meta_two) == []
    assert {k: v for k, v in first.files.items() if k != "release_meta.json"} == {k: v for k, v in second.files.items() if k != "release_meta.json"}
    assert first.files["release_meta.json"] != second.files["release_meta.json"]


def test_pb14_verify_against_the_manifest_of_another_machine_accepts_a_different_builder_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, commit = _make_repo(tmp_path)
    recorded = pb.build(repo, commit, "proj", tmp_path / "one")
    monkeypatch.setattr(pb.platform, "python_version", lambda: "0.0.0-another-machine")
    pb.build(repo, commit, "proj", tmp_path / "two")
    meta = {"release_id": recorded.release_id, "source_commit": recorded.source_commit, "version": recorded.version, "built_at": recorded.built_at}
    report = pb.verify(tmp_path / "two", recorded.files, meta)
    assert report["missing"] == [] and report["orphans"] == [] and report["mismatch"] == [] and report["meta"] == []


def test_pb15_a_changed_identity_field_of_the_meta_is_reported_and_a_changed_payload_file_is_still_a_mismatch(tmp_path: Path) -> None:
    repo, commit = _make_repo(tmp_path)
    built = pb.build(repo, commit, "proj", tmp_path / "out")
    meta_path = tmp_path / "out" / "release_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    recorded = {"release_id": built.release_id, "source_commit": built.source_commit, "version": built.version, "built_at": built.built_at}
    meta["source_commit"] = "0" * 40
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    report = pb.verify(tmp_path / "out", built.files, recorded)
    assert report["meta"] == ["source_commit"] and report["mismatch"] == []
    meta["source_commit"] = built.source_commit
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    (tmp_path / "out" / "auto_pm" / "__init__.py").write_text("changed\n", encoding="utf-8")
    again = pb.verify(tmp_path / "out", built.files, recorded)
    assert again["mismatch"] == ["auto_pm/__init__.py"] and again["meta"] == []


def test_pb16_an_unparsable_or_wrong_schema_meta_is_reported(tmp_path: Path) -> None:
    repo, commit = _make_repo(tmp_path)
    pb.build(repo, commit, "proj", tmp_path / "out")
    meta_path = tmp_path / "out" / "release_meta.json"
    meta_path.write_text("{not json", encoding="utf-8")
    assert pb.verify(tmp_path / "out")["meta"] == ["unparsable"]
    meta_path.write_text(json.dumps({"schema_version": "something-else"}), encoding="utf-8")
    assert pb.verify(tmp_path / "out")["meta"] == ["schema_version"]


def test_pb17_the_short_commit_form_of_an_older_record_is_a_prefix_match_not_a_difference() -> None:
    full = "9d3c92057a5dcdadbf1f1f693030ef9bc3c102a3"
    assert pb.compare_meta({"source_commit": "9d3c9205", "version": "1.3.2"}, {"source_commit": full, "version": "1.3.2", "builder": {"interpreter": "x"}}) == []
    assert pb.compare_meta({"source_commit": "deadbeef"}, {"source_commit": full}) == ["source_commit"]
    assert pb.compare_meta({"version": "1.3.2"}, {"version": "1.3.3"}) == ["version"]


def test_pb18_golden_the_commit_of_release_1_3_2_rebuilds_to_the_committed_payload_byte_for_byte(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[2]
    top = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"], capture_output=True, text=True, encoding="utf-8")
    if top.returncode != 0:
        pytest.skip("UNVERIFIED: not inside a git work tree")
    repo = Path(top.stdout.strip())
    if subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{GOLDEN_COMMIT}^{{commit}}"], capture_output=True).returncode != 0:
        pytest.skip("UNVERIFIED: the commit of the golden release is not in this clone")
    committed_dir = GOLDEN_COMMITTED
    head = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "-z", "HEAD", "--", committed_dir], capture_output=True)
    names = [n for n in head.stdout.decode("utf-8").split(chr(0)) if n]
    if head.returncode != 0 or len(names) < 100:
        pytest.skip("UNVERIFIED: the committed payload of the golden release is not in this clone")
    committed: dict[str, bytes] = {}
    for name in names:
        shown = subprocess.run(["git", "-C", str(repo), "show", f"HEAD:{name}"], capture_output=True)
        assert shown.returncode == 0
        committed[name[len(committed_dir) + 1:]] = shown.stdout
    result = pb.build(repo, GOLDEN_COMMIT, GOLDEN_PROJECT_ROOT, tmp_path / "golden", release_id=GOLDEN_RELEASE)
    rebuilt = {k: (tmp_path / "golden" / k).read_bytes() for k in result.files}
    payload_committed = {k: v for k, v in committed.items() if k != "release_meta.json" and "__pycache__" not in k and not k.endswith(".pyc")}
    payload_rebuilt = {k: v for k, v in rebuilt.items() if k != "release_meta.json"}
    assert sorted(payload_rebuilt) == sorted(payload_committed)
    assert [k for k in payload_rebuilt if payload_rebuilt[k] != payload_committed[k]] == []
    recorded_meta = json.loads(committed["release_meta.json"].decode("utf-8"))
    rebuilt_meta = json.loads(rebuilt["release_meta.json"].decode("utf-8"))
    differing = pb.compare_meta(recorded_meta, rebuilt_meta)
    # built_at of this pre-D02 release was typed by hand (2026-09-09T20:30:00Z); since D02 it is the commit time. Nothing else may differ.
    assert differing == ["built_at"], differing
