"""D-146 card 1: the read-only half of the one-command release (preflight and status).  Nothing may be written."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from auto_pm.application.core import release_deploy_check as rdc
from auto_pm.application.core.gate_run_service import GROUPS

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

    def verdict(
        self,
        tmp: Path,
        commit: str,
        text: str = "PASS",
        name: str = "verdict.json",
        *,
        extra: dict[str, object] | None = None,
    ) -> Path:
        path = tmp / name
        payload: dict[str, object] = {
            "schema": "gate-run.v1",
            "commit": commit,
            "commit_end": commit,
            "verdict": text,
            "complete": True,
            "tier": "L3",
            "plugin_result": "success",
            "git_dirty": False,
            "git_dirty_end": False,
            "manifest_sha256": "a" * 64,
            "reasons": [],
            "groups_run": [g.name for g in GROUPS],
            "results": {g.name: {"verdict": "PASS"} for g in GROUPS},
        }
        if extra:
            payload.update(extra)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def audit(self, tmp: Path, commit: str, token: str = "PASS", verdict_name: str = "verdict.json", sha: str | None = None, prose: str = "") -> Path:
        """The signed-off file: free prose plus the machine-readable audit line, bound to the verdict file ``verdict_name``."""

        gate = tmp / verdict_name
        digest = sha if sha is not None else (hashlib.sha256(gate.read_bytes()).hexdigest()[:16] if gate.exists() else "0" * 16)
        path = tmp / "audit.md"
        path.write_text(
            f"# 独立审计结论，候选 {commit}\n{prose}\naudit:AUD-001 independent-audit {token} RUN-TEST {commit} verdict-sha256={digest} 2026-11-08T16:00Z {path}\n",
            encoding="utf-8",
        )
        return path


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
    made = Repo(tmp_path)
    monkeypatch.setattr(rdc, "check_release_consistency", lambda _root: {"status": "ok", "failures": [], "warnings": []})
    monkeypatch.setattr(rdc, "_list_processes", lambda: ([(1, 0, "init")], ""))  # other test workers are not a real deployment in flight
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


@pytest.mark.parametrize("problem", ["", "decision", "commit", "receipt", "baseline"])
def test_only_the_original_rolled_back_release_can_reuse_its_slot(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, problem: str,
) -> None:
    rid = f"1.3.3-{repo.merge[:7]}"
    folder = repo.container / "releases" / rid
    folder.mkdir()
    change_id = "CHG-SCPT-2026-736"
    decision_id = f"DEC-20261122-D{repo.merge[:7].upper()}"
    evidence = repo.root / ".auto-pm" / "reports" / f"release-deploy-{rid}"
    evidence.mkdir(parents=True)
    (evidence / "state.json").write_text(json.dumps({
        "backup": "", "decision_id": decision_id, "change_id": change_id,
        "rolled_back_with": "user-confirmation:cmsg_roll_back",
    }), encoding="utf-8")
    if problem == "receipt":
        (evidence / "receipt.json").write_text("{}", encoding="utf-8")
    decisions = repo.root / ".auto-pm" / "decisions"
    decisions.mkdir()
    (decisions / f"{decision_id}.json").write_text(json.dumps({
        "decision_id": decision_id, "change_id": change_id, "project_id": "SW-2026-008",
        "decision_conclusion": "rejected" if problem == "decision" else "approved",
        "approved_files": [
            (rdc.CONTAINER / name).as_posix()
            for name in (f"releases/{rid}", "active_release.json", "previous_release.json", "deployment_manifest.json")
        ],
    }), encoding="utf-8")
    (repo.container / "deployment_manifest.json").write_text(json.dumps({
        "releases": {rid: {"source_commit": repo.side if problem == "commit" else repo.merge}},
    }), encoding="utf-8")
    before_release = "1.3.1-bbbbbbb" if problem == "baseline" else "1.3.2-aaaaaaa"
    change = SimpleNamespace(status="implementing", references=f"RELEASE={rid}; COMMIT={repo.merge}; PREVIOUS={before_release}")
    monkeypatch.setattr("auto_pm.domain.change.change_service.ChangeService.get_change_request", lambda *_args, **_kwargs: change)

    report = _happy(repo, tmp_path)
    if problem:
        assert not report.ok and not report.resume_from
    else:
        assert report.ok and report.resume_from == before_release
        assert _by_name(report)["已装候选逐文件校验"].status == rdc.PASS


@pytest.mark.parametrize("case", ["missing", "other_commit", "short_commit", "prefix_12", "not_pass", "unreadable"])
def test_the_gate_verdict_must_name_this_commit_and_pass(repo: Repo, tmp_path: Path, case: str) -> None:
    gate = {
        "missing": None,
        "other_commit": repo.verdict(tmp_path, "0" * 40, name="other.json"),
        "short_commit": repo.verdict(tmp_path, repo.merge[:8], name="short.json"),
        "prefix_12": repo.verdict(tmp_path, repo.merge[:12], name="prefix12.json"),
        "not_pass": repo.verdict(tmp_path, repo.merge, "FAIL (core)", name="fail.json"),
        "unreadable": tmp_path / "nowhere.json",
    }[case]

    report = rdc.preflight(repo.root, repo.merge, gate_verdict=gate, audit_signoff=repo.audit(tmp_path, repo.merge, verdict_name=gate.name if gate else "verdict.json"))

    gate_check = _by_name(report)["门禁判决"]
    assert not report.ok and gate_check.status == rdc.FAIL
    if case in ("other_commit", "short_commit", "prefix_12"):
        assert "不是待发布提交" in gate_check.detail, "must fail on the commit, not on the result text"
    if case == "not_pass":
        assert "不是 PASS" in gate_check.detail


@pytest.mark.parametrize(
    "case",
    [
        "wrong_commit_end",
        "pass_prefix_spoof",
        "missing_tier",
        "l2_tier",
        "incomplete",
        "dirty_start",
        "dirty_end",
        "empty_manifest",
        "short_manifest",
        "missing_group",
        "failed_group",
        "plugin_empty",
        "plugin_skipped",
        "plugin_failure",
        "nonempty_reasons",
    ],
)
def test_gate_verdict_requires_complete_clean_l3_full_receipt(repo: Repo, tmp_path: Path, case: str) -> None:
    missing_groups_results = {g.name: {"verdict": "PASS"} for g in GROUPS[:-1]}
    failed_group_results = {g.name: {"verdict": "PASS"} for g in GROUPS}
    failed_group_results["core"] = {"verdict": "FAIL"}
    cases: dict[str, dict[str, object]] = {
        "wrong_commit_end": {"commit_end": "0" * 40},
        "pass_prefix_spoof": {"verdict": "PASS (L2)"},
        "missing_tier": {"tier": None},
        "l2_tier": {"tier": "L2"},
        "incomplete": {"complete": False},
        "dirty_start": {"git_dirty": True},
        "dirty_end": {"git_dirty_end": True},
        "empty_manifest": {"manifest_sha256": ""},
        "short_manifest": {"manifest_sha256": "abc123"},
        "missing_group": {"results": missing_groups_results},
        "failed_group": {"results": failed_group_results},
        "plugin_empty": {"plugin_result": ""},
        "plugin_skipped": {"plugin_result": "skipped"},
        "plugin_failure": {"plugin_result": "failure"},
        "nonempty_reasons": {"reasons": ["有残余失败"]},
    }
    gate = repo.verdict(tmp_path, repo.merge, name=f"{case}.json", extra=cases[case])
    report = rdc.preflight(
        repo.root,
        repo.merge,
        gate_verdict=gate,
        audit_signoff=repo.audit(tmp_path, repo.merge, verdict_name=gate.name),
    )
    gate_check = _by_name(report)["门禁判决"]
    assert not report.ok and gate_check.status == rdc.FAIL, (case, gate_check)


def _audit_check(repo: Repo, tmp_path: Path, *, token: str = "PASS", sha: str | None = None, prose: str = "") -> rdc.Check:
    gate = repo.verdict(tmp_path, repo.merge)
    report = rdc.preflight(repo.root, repo.merge, gate_verdict=gate, audit_signoff=repo.audit(tmp_path, repo.merge, token=token, sha=sha, prose=prose))
    return _by_name(report)["独立审计签字"]


@pytest.mark.parametrize(
    "prose",
    ["结论：**放行**。", "不放行，打回", "打回，不能放行", "审计 FAIL，未通过（PASS 了 3 项）", "放行，没有保留项", ""],
)
def test_only_the_machine_readable_audit_line_counts_whatever_the_prose_says(repo: Repo, tmp_path: Path, prose: str) -> None:
    assert _audit_check(repo, tmp_path, prose=prose).status == rdc.PASS


@pytest.mark.parametrize("token", ["FAIL", "REJECT", "NOT-PASS", "pass", "PASS,"])
def test_an_audit_line_whose_token_is_not_exactly_pass_is_refused(repo: Repo, tmp_path: Path, token: str) -> None:
    assert _audit_check(repo, tmp_path, token=token).status == rdc.FAIL


def test_an_audit_that_passed_with_notes_does_not_allow_one_click(repo: Repo, tmp_path: Path) -> None:
    check = _audit_check(repo, tmp_path, token="PASS-with-notes")

    assert check.status == rdc.FAIL and "用户确认引用" in check.detail


def test_an_audit_of_another_verdict_file_is_refused(repo: Repo, tmp_path: Path) -> None:
    check = _audit_check(repo, tmp_path, sha="1" * 16)

    assert check.status == rdc.FAIL and "verdict-sha256" in check.detail


def test_prose_alone_without_the_audit_line_is_refused(repo: Repo, tmp_path: Path) -> None:
    gate = repo.verdict(tmp_path, repo.merge)
    signoff = tmp_path / "prose.md"
    signoff.write_text(f"# 独立审计结论，候选 {repo.merge}\n结论：**放行**。PASS\n", encoding="utf-8")

    check = _by_name(rdc.preflight(repo.root, repo.merge, gate_verdict=gate, audit_signoff=signoff))["独立审计签字"]

    assert check.status == rdc.FAIL and "机器可读" in check.detail


def test_an_audit_for_another_commit_or_none_at_all_is_refused(repo: Repo, tmp_path: Path) -> None:
    gate = repo.verdict(tmp_path, repo.merge)
    other = repo.audit(tmp_path, "f" * 40)
    none = rdc.preflight(repo.root, repo.merge, gate_verdict=gate)

    assert _by_name(rdc.preflight(repo.root, repo.merge, gate_verdict=gate, audit_signoff=other))["独立审计签字"].status == rdc.FAIL
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
    receipt = repo.root / ".auto-pm" / "reports" / f"{rdc.EVIDENCE_PREFIX}1.3.2-aaaaaaa" / "receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{}", encoding="utf-8")

    info = rdc.status(repo.root)

    assert info["pointers"]["active"]["release_id"] == "1.3.2-aaaaaaa"
    assert info["pointers"]["previous"]["release_id"] == "1.3.1-bbbbbbb"
    assert info["installed_releases"] == ["1.3.1-bbbbbbb", "1.3.2-aaaaaaa"]
    assert info["last_receipt"] == str(receipt)


def test_a_running_test_or_cockpit_process_blocks_the_deploy(repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [(1, 0, "init"), (4242, 1, "python -m pytest tests/core"), (4243, 1, "/usr/bin/python3 main.py gui")]
    monkeypatch.setattr(rdc, "_list_processes", lambda: (rows, ""))

    report = _happy(repo, tmp_path)

    busy = _by_name(report)["没有测试或驾驶舱进程在跑"]
    assert not report.ok and busy.status == rdc.FAIL and "4242" in busy.detail and "4243" in busy.detail


def test_this_command_and_its_ancestors_are_not_busy_processes() -> None:
    me = os.getpid()
    rows = [(1, 0, "init"), (50, 1, "python -m pytest"), (me, 50, "python main.py release deploy"), (900, 1, "python other.py")]

    assert rdc._busy_processes(rows) == []


def test_a_process_list_that_cannot_be_read_is_unverified_not_ok(repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rdc, "_list_processes", lambda: (None, "ps 超过 30 秒没返回"))

    report = _happy(repo, tmp_path)

    busy = _by_name(report)["没有测试或驾驶舱进程在跑"]
    assert not report.ok and busy.status == rdc.UNVERIFIED
    assert "ps 超过 30 秒没返回" in busy.detail  # D-234: the reason travels with the verdict


def test_the_real_process_list_is_readable_here() -> None:
    rows, why = rdc._list_processes()

    assert rows is not None, why
    mine = [line for pid, _parent, line in rows if pid == os.getpid()]
    assert len(mine) == 1 and mine[0].strip(), f"this process is not in the list with its command line: {mine!r}"
    assert rdc._runs_python(mine[0]), mine[0]  # the line is good enough for the check that reads it


def test_the_process_list_does_not_start_powershell_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-234: inside the gate's white-listed environment the PowerShell query took 20 to 27 of its 30 seconds; the list is read in-process now."""

    def no_child(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("the process list started a child process")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(rdc, "windows_command_lines", lambda: ([(7, 1, "python.exe -m pytest")], ""))
    monkeypatch.setattr(subprocess, "run", no_child)

    assert rdc._list_processes() == ([(7, 1, "python.exe -m pytest")], "")


def test_a_ps_that_fails_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")  # ps is the non-Windows way; the answers below are scripted, no ps is started

    def timed_out(*_a: object, **_k: object) -> object:
        raise subprocess.TimeoutExpired("ps", 30)

    monkeypatch.setattr(subprocess, "run", timed_out)
    assert rdc._list_processes() == (None, "ps 超过 30 秒没返回")

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: subprocess.CompletedProcess(["ps"], 3, "", "ps: boom\n"))
    rows, why = rdc._list_processes()
    assert rows is None and "退出码 3" in why and "ps: boom" in why

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: subprocess.CompletedProcess(["ps"], 0, "junk\n", ""))
    rows, why = rdc._list_processes()
    assert rows is None and "没有一行进程" in why


def test_a_shell_wrapper_that_merely_mentions_python_and_pytest_is_not_a_busy_process() -> None:
    """The wrapper's command line holds both words, but the process is bash; only an interpreter running the work counts."""

    rows = [
        (1, 0, "init"),
        (10, 1, 'bash -c "cd repo && python -m pytest tests/core"'),
        (11, 1, "/bin/sh -c 'exec python3 main.py gui'"),
        (12, 1, r'C:\\Program Files\\Git\\bin\\bash.exe -c "python -m pytest"'),
        (13, 1, "tail -f /tmp/python-pytest.log"),
    ]

    assert rdc._busy_processes(rows) == []


@pytest.mark.parametrize(
    "command_line",
    [
        "python -m pytest tests/core",
        "/usr/bin/python3.12 -m pytest",
        r'"C:\\Program Files\\Python312\\python.exe" -m pytest tests',
        r"C:\\Python312\\python.exe main.py gui",
        r"C:\\x\\pythonw.exe boss_main.py",
    ],
    ids=["bare", "posix-versioned", "quoted-windows-path", "windows-path", "pythonw"],
)
def test_a_python_interpreter_running_tests_or_the_cockpit_is_still_busy(command_line: str) -> None:
    assert rdc._busy_processes([(1, 0, "init"), (77, 1, command_line)]) == ["77"]


def test_status_finds_the_receipt_the_real_deploy_writes(repo: Repo) -> None:
    """D-188: ``release status`` once globbed ``deploy-*`` while the deploy wrote ``release-deploy-<id>/``; write the receipt through the deploy's own path code."""

    from types import SimpleNamespace  # noqa: PLC0415

    from auto_pm.application.core import release_ledger, release_wiring  # noqa: PLC0415

    report = SimpleNamespace(release_id="1.3.3-ccccccc", commit="c" * 40)
    plan, _backup = release_wiring.plan_for(repo.root, report, approver="fubai", confirm_ref="user-confirmation:2026-11-09T10:00Z")
    written = release_ledger.write_receipt(plan, change_id="CHG-SCPT-2026-1", backup="b", entry_sha256="e", checks_sha256="c", rollback_command="r")

    assert rdc.status(repo.root)["last_receipt"] == str(written)


def test_preflight_refuses_leftover_open_deploy_work_or_run_in_continuity_db(
    repo: Repo, tmp_path: Path
) -> None:
    """CHG-SCPT-2026-750: 账本存在未关闭的残留 WORK-DEPLOY-*/RUN-DEPLOY-* 时，切版前 preflight 必须直接 FAIL。"""
    import sqlite3

    db = repo.root / ".auto-pm" / "continuity.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE work_items (work_id TEXT PRIMARY KEY, state TEXT NOT NULL)")
        conn.execute("CREATE TABLE run_items (run_id TEXT PRIMARY KEY, state TEXT NOT NULL)")
        conn.execute("INSERT INTO work_items VALUES ('WORK-DEPLOY-1-3-3-OLD0001', 'IN_PROGRESS')")
        conn.execute("INSERT INTO run_items VALUES ('RUN-DEPLOY-1-3-3-OLD0001', 'RUNNING')")
        conn.commit()

    blocked = _happy(repo, tmp_path)
    conflict_check = _by_name(blocked)["无残留发布冲突"]
    assert not blocked.ok and conflict_check.status == rdc.FAIL
    assert "WORK-DEPLOY-1-3-3-OLD0001" in conflict_check.detail and "RUN-DEPLOY-1-3-3-OLD0001" in conflict_check.detail

    # Once closed/cancelled, preflight passes cleanly
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE work_items SET state='CLOSED'")
        conn.execute("UPDATE run_items SET state='CANCELLED'")
        conn.commit()

    clean = _happy(repo, tmp_path)
    assert clean.ok and _by_name(clean)["无残留发布冲突"].status == rdc.PASS
