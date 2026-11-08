"""D-146 card 1: the read-only half of the one-command release (preflight and status).  Nothing may be written."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from auto_pm.application.core import release_deploy_check as rdc

PYPROJECT = 'name = "auto-pm"\nversion = "1.3.3"\n'


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return done.stdout.strip()


class Repo:
    """A control root with a merge commit on main (the release point), a side commit, and the release container."""

    def __init__(self, base: Path) -> None:
        self.root = base / "root"
        self.root.mkdir()
        _git(self.root, "init", "-q", "-b", "main")
        project = self.root / rdc.PROJECT_DIR
        project.mkdir(parents=True)
        (project / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "base")
        _git(self.root, "checkout", "-q", "-b", "feature")
        (project / "feature.txt").write_text("x\n", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "feature")
        self.side = _git(self.root, "rev-parse", "HEAD")
        _git(self.root, "checkout", "-q", "main")
        (project / "main.txt").write_text("y\n", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "main moves")
        _git(self.root, "merge", "-q", "--no-ff", "feature", "-m", "Merge feature")
        self.merge = _git(self.root, "rev-parse", "HEAD")
        _git(self.root, "checkout", "-q", "-b", "unmerged", self.base_commit())
        (project / "lonely.txt").write_text("z\n", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "never merged")
        self.lonely = _git(self.root, "rev-parse", "HEAD")
        _git(self.root, "checkout", "-q", "main")
        self.container = self.root / rdc.CONTAINER
        (self.container / "launcher").mkdir(parents=True)
        (self.container / "releases").mkdir()
        (self.container / "launcher" / "bootstrap.py").write_text("def _resolve_slot(container, slot, release_id):\n    return container\n", encoding="utf-8")
        for slot, rid in (("active_release.json", "1.3.2-aaaaaaa"), ("previous_release.json", "1.3.1-bbbbbbb")):
            (self.container / slot).write_text(json.dumps({"release_id": rid, "updated_at": "2026-11-01T00:00:00+00:00"}), encoding="utf-8")
        (self.container / "deployment_manifest.json").write_text(json.dumps({"releases": {"1.3.2-aaaaaaa": {}, "1.3.1-bbbbbbb": {}}}), encoding="utf-8")

    def base_commit(self) -> str:
        return _git(self.root, "rev-list", "--max-parents=0", "HEAD")

    def tree_digest(self) -> dict[str, str]:
        return {
            str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(self.root.rglob("*")) if p.is_file() and ".git" not in p.parts
        }

    def verdict(self, tmp: Path, commit: str, text: str = "PASS (9 groups)") -> Path:
        path = tmp / "verdict.json"
        path.write_text(json.dumps({"commit": commit, "verdict": text}), encoding="utf-8")
        return path

    def audit(self, tmp: Path, commit: str, body: str = "结论：**放行**。") -> Path:
        path = tmp / "audit.md"
        path.write_text(f"# 独立审计结论，候选 {commit}\n{body}\n", encoding="utf-8")
        return path


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
    made = Repo(tmp_path)
    monkeypatch.setattr(rdc, "check_release_consistency", lambda _root: {"status": "ok", "failures": [], "warnings": []})
    monkeypatch.setattr(rdc, "_busy_processes", lambda _psutil: [])  # other test workers are not a real deployment in flight
    return made


def _by_name(report: rdc.Preflight) -> dict[str, rdc.Check]:
    return {check.name: check for check in report.checks}


def _happy(repo: Repo, tmp_path: Path) -> rdc.Preflight:
    return rdc.preflight(repo.root, repo.merge, gate_verdict=repo.verdict(tmp_path, repo.merge), audit_signoff=repo.audit(tmp_path, repo.merge))


def test_a_merge_commit_on_main_with_gate_and_audit_may_be_deployed(repo: Repo, tmp_path: Path) -> None:
    report = _happy(repo, tmp_path)

    assert report.ok, report.render()
    assert report.release_id == f"1.3.3-{repo.merge[:7]}"


def test_the_preflight_writes_nothing(repo: Repo, tmp_path: Path) -> None:
    before = repo.tree_digest()

    _happy(repo, tmp_path)
    rdc.status(repo.root)

    assert repo.tree_digest() == before  # the verdict and audit files live outside the control root, so the whole tree must be byte-identical


def test_a_commit_that_is_not_a_merge_commit_is_refused(repo: Repo, tmp_path: Path) -> None:
    report = rdc.preflight(repo.root, repo.side, gate_verdict=repo.verdict(tmp_path, repo.side), audit_signoff=repo.audit(tmp_path, repo.side))

    assert not report.ok
    assert _by_name(report)["是合并提交"].status == rdc.FAIL


def test_a_commit_that_is_not_on_main_is_refused(repo: Repo, tmp_path: Path) -> None:
    report = rdc.preflight(repo.root, repo.lonely, gate_verdict=repo.verdict(tmp_path, repo.lonely), audit_signoff=repo.audit(tmp_path, repo.lonely))

    assert _by_name(report)["已在主线上"].status == rdc.FAIL


def test_an_unknown_commit_is_refused_without_a_traceback(repo: Repo) -> None:
    report = rdc.preflight(repo.root, "deadbeef" * 5)

    assert not report.ok and _by_name(report)["提交存在"].status == rdc.FAIL


def test_an_already_installed_release_slot_is_refused(repo: Repo, tmp_path: Path) -> None:
    rid = f"1.3.3-{repo.merge[:7]}"
    (repo.container / "releases" / rid).mkdir()

    assert _by_name(_happy(repo, tmp_path))["发布槽位空闲"].status == rdc.FAIL


def test_a_manifest_entry_alone_also_takes_the_slot(repo: Repo, tmp_path: Path) -> None:
    rid = f"1.3.3-{repo.merge[:7]}"
    (repo.container / "deployment_manifest.json").write_text(json.dumps({"releases": {rid: {}}}), encoding="utf-8")

    assert _by_name(_happy(repo, tmp_path))["发布槽位空闲"].status == rdc.FAIL


@pytest.mark.parametrize("case", ["missing", "other_commit", "not_pass"])
def test_the_gate_verdict_must_name_this_commit_and_pass(repo: Repo, tmp_path: Path, case: str) -> None:
    gate = {
        "missing": None,
        "other_commit": repo.verdict(tmp_path, "0" * 40),
        "not_pass": repo.verdict(tmp_path, repo.merge, "FAIL (core)"),
    }[case]

    report = rdc.preflight(repo.root, repo.merge, gate_verdict=gate, audit_signoff=repo.audit(tmp_path, repo.merge))

    assert not report.ok and _by_name(report)["门禁判决"].status == rdc.FAIL


def test_an_audit_that_passed_with_reservations_does_not_allow_one_click(repo: Repo, tmp_path: Path) -> None:
    signoff = repo.audit(tmp_path, repo.merge, "结论：**放行（有保留项）**。")

    report = rdc.preflight(repo.root, repo.merge, gate_verdict=repo.verdict(tmp_path, repo.merge), audit_signoff=signoff)

    audit = _by_name(report)["独立审计签字"]
    assert not report.ok and audit.status == rdc.FAIL and "用户确认引用" in audit.detail


def test_an_audit_for_another_commit_or_none_at_all_is_refused(repo: Repo, tmp_path: Path) -> None:
    other = repo.audit(tmp_path, "f" * 40)
    none = rdc.preflight(repo.root, repo.merge, gate_verdict=repo.verdict(tmp_path, repo.merge))

    assert _by_name(rdc.preflight(repo.root, repo.merge, audit_signoff=other))["独立审计签字"].status == rdc.FAIL
    assert _by_name(none)["独立审计签字"].status == rdc.FAIL


def test_a_check_that_cannot_run_is_unverified_and_never_reads_as_ok(repo: Repo, tmp_path: Path) -> None:
    (repo.container / "launcher" / "bootstrap.py").unlink()

    report = _happy(repo, tmp_path)

    assert not report.ok
    assert _by_name(report)["已装发布逐文件校验"].status == rdc.UNVERIFIED


def test_a_failing_exact_tree_of_an_installed_release_is_refused(repo: Repo, tmp_path: Path) -> None:
    (repo.container / "launcher" / "bootstrap.py").write_text(
        "def _resolve_slot(container, slot, release_id):\n    raise SystemExit('exact-tree mismatch ' + release_id)\n", encoding="utf-8"
    )

    report = _happy(repo, tmp_path)

    assert not report.ok
    assert any(c.status == rdc.FAIL and "逐文件校验" in c.name for c in report.checks)


def test_a_heavy_gate_marker_blocks_the_deploy(repo: Repo, tmp_path: Path) -> None:
    marker = repo.root / rdc.HEAVY_GATES_MARKER
    marker.parent.mkdir(parents=True)
    marker.write_text("", encoding="utf-8")

    assert _by_name(_happy(repo, tmp_path))["没有重型门禁在跑"].status == rdc.FAIL


def test_the_report_always_lists_what_it_does_not_cover(repo: Repo, tmp_path: Path) -> None:
    report = _happy(repo, tmp_path)

    assert report.to_dict()["not_covered"] == list(rdc.NOT_COVERED)
    assert any("没覆盖" in line for line in report.render())


def test_status_reports_pointers_installed_releases_and_the_last_receipt(repo: Repo) -> None:
    receipt = repo.root / ".auto-pm" / "reports" / "deploy-1.3.2-aaaaaaa" / "receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{}", encoding="utf-8")

    info = rdc.status(repo.root)

    assert info["pointers"]["active"]["release_id"] == "1.3.2-aaaaaaa"
    assert info["pointers"]["previous"]["release_id"] == "1.3.1-bbbbbbb"
    assert info["installed_releases"] == ["1.3.1-bbbbbbb", "1.3.2-aaaaaaa"]
    assert info["last_receipt"] == str(receipt)


def test_a_running_test_or_cockpit_process_blocks_the_deploy(repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rdc, "_busy_processes", lambda _psutil: ["4242"])

    report = _happy(repo, tmp_path)

    assert not report.ok and _by_name(report)["没有测试或驾驶舱进程在跑"].status == rdc.FAIL
