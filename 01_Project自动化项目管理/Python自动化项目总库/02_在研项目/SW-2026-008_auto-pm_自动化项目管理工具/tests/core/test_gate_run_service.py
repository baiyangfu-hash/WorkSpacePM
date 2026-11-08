"""D-107a / D-108 / D-105: the official multi-group gate.

Three failures of the 11-07 deployment gate, each pinned here: groups run where no ``tests/`` exists and "pass" with exit 4/5
(D-105); cockpit variables leak into the test children (D-108); the verdict of a many-group run depends on every group being there
and judged on its own summary line (D-107).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from auto_pm.application.core import gate_run_service as gate
from auto_pm.application.core.gate_run_service import (
    GROUPS,
    GateGroup,
    GateRunError,
    GateRunService,
)

_PASS_LINE = "123 passed, 2 skipped in 4.20s\n"


def _group(name: str = "g", **changes: object) -> GateGroup:
    return GateGroup(name, ("tests/x",), **changes)  # type: ignore[arg-type]


def _log(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "g.txt"
    path.write_text(text, encoding="utf-8")
    return path


# ── environment (D-108) ─────────────────────────────────


def test_child_environment_never_carries_cockpit_variables() -> None:
    base = {
        "PATH": "/usr/bin",
        "HOME": "/home/x",
        "AUTO_PM_WORKSPACE": "/real/ws",
        "AUTO_PM_CONTROL_ROOT": "/real/root",
        "AUTO_PM_RUN_WORKTREE": "/real/wt",
        "AUTO_PM_CALLER_CWD": "/release",
        "AUTO_PM_AGENT": "claude",
        "CLAUDECODE": "1",
        "LONG_GATE_LEASE_TOKEN": "secret",
        "PYTEST_ADDOPTS": "-k nothing",
    }
    env = gate.child_environment(base)
    assert env["PATH"] == "/usr/bin" and env["HOME"] == "/home/x"
    assert not [key for key in env if key.upper().startswith("AUTO_PM_")]
    assert (
        "CLAUDECODE" not in env
        and "LONG_GATE_LEASE_TOKEN" not in env
        and "PYTEST_ADDOPTS" not in env
    )
    assert env["PYTHONDONTWRITEBYTECODE"] == "1" and env["PYTHONUTF8"] == "1"


def test_child_environment_filter_is_case_insensitive_for_windows_names() -> None:
    env = gate.child_environment({"Path": "C:\\bin", "auto_pm_workspace": "x"})
    assert env["Path"] == "C:\\bin" and "auto_pm_workspace" not in env


# ── judging (D-105) ─────────────────────────────────────


@pytest.mark.parametrize("code", [1, 2, 4, 5, 124])
def test_nonzero_exit_fails_even_with_a_pass_line(tmp_path: Path, code: int) -> None:
    verdict, why = gate.judge_group(_group(), code, _log(tmp_path, _PASS_LINE))
    assert verdict == "FAIL" and str(code) in why


def test_exit_zero_with_no_tests_ran_is_a_failure(tmp_path: Path) -> None:
    verdict, why = gate.judge_group(_group(), 0, _log(tmp_path, "no tests ran in 0.01s\n"))
    assert verdict == "FAIL" and "no tests ran" in why


def test_exit_zero_without_a_summary_line_is_a_failure(tmp_path: Path) -> None:
    verdict, _ = gate.judge_group(_group(), 0, _log(tmp_path, "just some output\n"))
    assert verdict == "FAIL"


def test_missing_log_and_missing_exit_code_fail(tmp_path: Path) -> None:
    assert gate.judge_group(_group(), 0, tmp_path / "absent.txt")[0] == "FAIL"
    assert gate.judge_group(_group(), None, _log(tmp_path, _PASS_LINE))[0] == "FAIL"


def test_failed_in_the_summary_line_fails_even_with_exit_zero(tmp_path: Path) -> None:
    assert (
        gate.judge_group(_group(), 0, _log(tmp_path, "1 failed, 5 passed in 1.00s\n"))[0] == "FAIL"
    )


def test_deselect_count_must_equal_the_manifest_exactly(tmp_path: Path) -> None:
    undeclared = _group()
    declared = _group(deselect=("a::b",), deselected=1)
    one = _log(tmp_path, "10 passed, 1 deselected in 1.00s\n")
    assert gate.judge_group(undeclared, 0, one)[0] == "FAIL"
    assert gate.judge_group(declared, 0, one)[0] == "PASS"
    many = _log(tmp_path, "1 passed, 5000 deselected in 1.00s\n")
    assert gate.judge_group(declared, 0, many)[0] == "FAIL"  # audit 1.3
    none = _log(tmp_path, "10 passed in 1.00s\n")
    assert gate.judge_group(declared, 0, none)[0] == "FAIL"  # the node matched nothing


def test_a_group_with_a_deselect_must_say_how_many() -> None:
    with pytest.raises(ValueError, match="deselect"):
        GateGroup("g", ("tests/x",), deselect=("a::b",))


@pytest.mark.parametrize("group", [g for g in GROUPS if g.min_cases > 1], ids=lambda g: g.name)
def test_every_group_needs_its_case_floor(tmp_path: Path, group: GateGroup) -> None:
    log = _log(tmp_path, f"1 passed{', 1 deselected' if group.deselected else ''} in 0.01s\n")
    verdict, why = gate.judge_group(group, 0, log)
    assert (
        verdict == "FAIL" and "下限" in why
    )  # audit 1.4: one passing test must not pass the 3000-case core group
    enough = _log(
        tmp_path,
        f"{group.min_cases} passed{', 1 deselected' if group.deselected else ''} in 1.00s\n",
    )
    assert gate.judge_group(group, 0, enough)[0] == "PASS"


def test_xfail_xpass_and_skipped_do_not_count_as_having_run(tmp_path: Path) -> None:
    assert gate.judge_group(_group(), 0, _log(tmp_path, "7 xfailed in 0.10s\n"))[0] == "FAIL"
    assert gate.judge_group(_group(), 0, _log(tmp_path, "3 xpassed in 0.10s\n"))[0] == "FAIL"


def test_too_many_skipped_fails(tmp_path: Path) -> None:
    log = _log(tmp_path, f"100 passed, {gate.MAX_SKIPPED + 1} skipped in 1.00s\n")
    assert gate.judge_group(_group(), 0, log)[0] == "FAIL"


def test_plain_pass(tmp_path: Path) -> None:
    assert gate.judge_group(_group(), 0, _log(tmp_path, _PASS_LINE)) == ("PASS", "")


# ── group table ─────────────────────────────────────────


def test_group_table_is_the_eleven_invocations_and_rest_ignores_the_others() -> None:
    names = [g.name for g in GROUPS]
    assert len(names) == len(set(names)) == 11
    rest = next(g for g in GROUPS if g.name == "rest")
    for name in (
        "application",
        "change",
        "cli",
        "contracts",
        "core",
        "infrastructure",
        "plc",
        "qml",
    ):
        assert f"tests/{name}" in rest.ignore
    core = next(g for g in GROUPS if g.name == "core")
    assert "tests/core/test_implementation_card_basis.py" in core.ignore


def test_argv_has_no_cwd_dependence_and_serial_groups_have_no_xdist() -> None:
    parallel = gate.group_argv(next(g for g in GROUPS if g.name == "cli"), python="py", jobs=8)
    serial = gate.group_argv(next(g for g in GROUPS if g.name == "qml"), python="py", jobs=8)
    assert "-n" in parallel and "-n" not in serial
    assert "--no-cov" in parallel and "-p" in parallel
    assert (
        "--deselect=tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events" in serial
    )


def test_manifest_sha256_changes_when_a_group_is_removed() -> None:
    assert gate.manifest_sha256(GROUPS) != gate.manifest_sha256(GROUPS[:-1])


# ── running ─────────────────────────────────────────────


def _line(group: GateGroup) -> str:
    return f"{group.min_cases + 5} passed, 2 skipped{f', {group.deselected} deselected' if group.deselected else ''} in 4.20s\n"


class _Recorder:
    """Stands in for pytest: writes a log per group and remembers the environment it was given."""

    def __init__(
        self,
        outcomes: Mapping[str, tuple[int, str]] | None = None,
        on_group: Callable[[str], None] | None = None,
    ) -> None:
        self.outcomes = dict(outcomes or {})
        self.on_group = on_group
        self.envs: list[Mapping[str, str]] = []
        self.cwds: list[Path] = []

    def __call__(
        self, argv: Sequence[str], cwd: Path, env: Mapping[str, str], log: Path, timeout: int
    ) -> int:
        name = log.stem
        group = next(g for g in GROUPS if g.name == name)
        code, text = self.outcomes.get(name, (0, _line(group)))
        log.write_text(text, encoding="utf-8")
        self.envs.append(env)
        self.cwds.append(cwd)
        if self.on_group is not None:
            self.on_group(name)
        return code


class _Tree:
    """A scriptable stand-in for the git calls of ``tree_state``."""

    def __init__(self, dirty: bool = False, untracked: bool = False) -> None:
        self.head = "a" * 40
        self.status: str | None = " M x.py" if dirty else ("?? zz_probe.py" if untracked else "")
        self.ignored: str | None = ""

    def install(self, monkeypatch: pytest.MonkeyPatch) -> Path:
        real = gate._git

        def fake(worktree: Path, *args: str) -> str | None:
            if args[:1] == ("status",):
                assert "--untracked-files=all" in args  # audit 1.1: untracked files must count
                return self.status
            if args[:1] == ("ls-files",):
                assert "-z" in args  # D-126: NUL-separated, raw names
                return None if self.ignored is None else self.ignored.replace("\n", "\0")
            if args[:1] == ("rev-parse",) and "HEAD" in args:
                return self.head
            return real(worktree, *args)

        monkeypatch.setattr(gate, "_git", fake)
        top = Path(gate.__file__).resolve()
        return next(p for p in top.parents if (p / ".git").exists())


def _clean_repo(monkeypatch: pytest.MonkeyPatch, dirty: bool = False) -> Path:
    return _Tree(dirty=dirty).install(monkeypatch)


def test_full_run_passes_and_every_child_gets_the_clean_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUTO_PM_WORKSPACE", "/real/ws")
    monkeypatch.setenv("AUTO_PM_CONTROL_ROOT", "/real/root")
    repo = _clean_repo(monkeypatch)
    recorder = _Recorder()
    summary = GateRunService(runner=recorder).run(repo, tmp_path)
    assert summary.verdict == "PASS" and summary.complete
    assert len(recorder.envs) == 11
    assert all(not [k for k in env if k.upper().startswith("AUTO_PM_")] for env in recorder.envs)
    assert all((cwd / "tests").is_dir() for cwd in recorder.cwds)  # D-105: never the release folder
    saved = json.loads((tmp_path / "gate_summary.json").read_text(encoding="utf-8"))
    assert saved["verdict"] == "PASS" and set(saved["results"]) == {g.name for g in GROUPS}
    assert all(item["log_sha256"] for item in saved["results"].values())


def test_one_group_with_no_tests_ran_fails_the_whole_gate_although_every_exit_is_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _clean_repo(monkeypatch)
    summary = GateRunService(runner=_Recorder({"rest": (0, "no tests ran in 0.01s\n")})).run(
        repo, tmp_path
    )
    assert summary.verdict == "FAIL"
    assert summary.results["rest"].verdict == "FAIL"


def test_exit_five_group_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _clean_repo(monkeypatch)
    summary = GateRunService(runner=_Recorder({"core": (5, "no tests ran in 0.01s\n")})).run(
        repo, tmp_path
    )
    assert summary.verdict == "FAIL" and "4/5" in summary.results["core"].why


def test_partial_run_is_never_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _clean_repo(monkeypatch)
    summary = GateRunService(runner=_Recorder()).run(repo, tmp_path, only=["plc"])
    assert summary.verdict == "PARTIAL" and not summary.complete


def test_dirty_worktree_is_never_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _clean_repo(monkeypatch, dirty=True)
    summary = GateRunService(runner=_Recorder()).run(repo, tmp_path)
    assert summary.verdict != "PASS"


def test_unknown_group_and_missing_tests_dir_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _clean_repo(monkeypatch)
    with pytest.raises(GateRunError, match="未知的组"):
        GateRunService(runner=_Recorder()).run(repo, tmp_path, only=["nope"])
    with pytest.raises(GateRunError, match="不是 Git 工作树"):
        GateRunService(runner=_Recorder()).run(tmp_path, tmp_path / "out")


def test_judge_dir_recomputes_from_the_logs_and_catches_a_tampered_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _clean_repo(monkeypatch)
    GateRunService(runner=_Recorder()).run(repo, tmp_path)
    assert GateRunService().judge_dir(tmp_path).verdict == "PASS"
    (tmp_path / "plc.txt").write_text("3 failed, 1 passed in 1.00s\n", encoding="utf-8")
    again = GateRunService().judge_dir(tmp_path)
    assert again.verdict == "FAIL" and again.results["plc"].verdict == "FAIL"


def test_judge_dir_does_not_write_anything(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _clean_repo(monkeypatch)
    GateRunService(runner=_Recorder()).run(repo, tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    GateRunService().judge_dir(tmp_path)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_a_summary_with_only_skipped_tests_is_a_failure(tmp_path: Path) -> None:
    verdict, why = gate.judge_group(_group(), 0, _log(tmp_path, "5 skipped in 0.10s\n"))
    assert verdict == "FAIL" and "没跑" in why


# ── audit 1 of #612: five ways to be passed by mistake, each with its counter-example ──


def test_an_untracked_file_makes_the_tree_dirty_and_the_gate_not_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _Tree(untracked=True).install(monkeypatch)
    summary = GateRunService(runner=_Recorder()).run(repo, tmp_path)
    assert summary.git_dirty is True and summary.verdict == "PARTIAL"
    assert any("不干净" in reason for reason in summary.reasons)


def test_ignored_code_files_make_the_gate_not_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = _Tree()
    tree.ignored = "tests/conftest_hidden.py\n"
    summary = GateRunService(runner=_Recorder()).run(tree.install(monkeypatch), tmp_path)
    assert summary.verdict == "PARTIAL" and summary.ignored_code == ["tests/conftest_hidden.py"]


def test_tree_state_in_a_real_repository(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    for key, value in (
        ("user.email", "t@example.com"),
        ("user.name", "t"),
        ("commit.gpgsign", "false"),
    ):
        git("config", key, value)
    (tmp_path / "tests").mkdir()
    (tmp_path / "auto_pm").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("hidden_*.py\n__pycache__/\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "c0")
    assert gate.tree_state(tmp_path, tmp_path).dirty is False
    (tmp_path / "tests" / "conftest.py").write_text(
        "x = 1\n", encoding="utf-8"
    )  # untracked, not ignored
    assert gate.tree_state(tmp_path, tmp_path).dirty is True
    (tmp_path / "tests" / "conftest.py").unlink()
    (tmp_path / "tests" / "hidden_plugin.py").write_text(
        "x = 1\n", encoding="utf-8"
    )  # ignored code under tests/
    (tmp_path / "tests" / "__pycache__").mkdir()
    (tmp_path / "tests" / "__pycache__" / "x.py").write_text("x = 1\n", encoding="utf-8")
    state = gate.tree_state(tmp_path, tmp_path)
    assert state.dirty is False and state.ignored_code == ("tests/hidden_plugin.py",)


def test_tree_state_lists_an_ignored_code_file_with_a_non_ascii_name(tmp_path: Path) -> None:
    """D-126: git quotes such a name ("\\350\\...") unless asked for -z, and the quoted text no longer ends in ``.py``."""

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    for key, value in (("user.email", "t@example.com"), ("user.name", "t"), ("commit.gpgsign", "false")):
        git("config", key, value)
    (tmp_path / "tests").mkdir()
    (tmp_path / "auto_pm").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("*隐藏*.py\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "c0")
    (tmp_path / "tests" / "隐藏插件.py").write_text("x = 1\n", encoding="utf-8")
    state = gate.tree_state(tmp_path, tmp_path)
    assert state.ignored_code == ("tests/隐藏插件.py",)


def test_a_tree_that_changes_during_the_round_is_not_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = _Tree()
    repo = tree.install(monkeypatch)

    def someone_commits(name: str) -> None:
        if name == "application":
            tree.head = "b" * 40  # another process commits in the worktree while the round runs

    summary = GateRunService(runner=_Recorder(on_group=someone_commits)).run(repo, tmp_path)
    assert summary.commit == "a" * 40 and summary.commit_end == "b" * 40
    assert summary.verdict == "PARTIAL" and any("变了" in reason for reason in summary.reasons)


def test_a_file_touched_during_the_round_is_not_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = _Tree()
    repo = tree.install(monkeypatch)

    def someone_edits(name: str) -> None:
        if name == "plc":
            tree.status = " M auto_pm/x.py"

    summary = GateRunService(runner=_Recorder(on_group=someone_edits)).run(repo, tmp_path)
    assert (
        summary.git_dirty is False
        and summary.git_dirty_end is True
        and summary.verdict == "PARTIAL"
    )


def _passed_round(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    repo = _clean_repo(monkeypatch)
    GateRunService(runner=_Recorder()).run(repo, tmp_path)
    assert GateRunService().judge_dir(tmp_path).verdict == "PASS"
    return repo, gate.sha256_file(tmp_path / "gate_summary.json") or ""


def test_judge_rejects_a_log_forged_into_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _passed_round(tmp_path, monkeypatch)
    (tmp_path / "plc.txt").write_text(
        "999 passed in 1.00s\n", encoding="utf-8"
    )  # audit 1.2: a *pass* line, not a failure line
    judged = GateRunService().judge_dir(tmp_path)
    assert judged.verdict == "FAIL" and "SHA-256" in judged.results["plc"].why


def test_judge_rejects_an_exit_file_that_disagrees_with_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _passed_round(tmp_path, monkeypatch)
    (tmp_path / "plc.exit").write_text("1\n", encoding="utf-8")
    judged = GateRunService().judge_dir(tmp_path)
    assert judged.verdict == "FAIL" and ".exit" in judged.results["plc"].why


def test_judge_rejects_an_edited_exit_code_in_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _passed_round(tmp_path, monkeypatch)
    (tmp_path / "plc.exit").write_text("5\n", encoding="utf-8")
    (tmp_path / "plc.txt").write_text("no tests ran in 0.01s\n", encoding="utf-8")
    record = json.loads((tmp_path / "gate_summary.json").read_text(encoding="utf-8"))
    record["results"]["plc"]["exit"] = 0  # the forger fixes the record's exit but not the disk
    (tmp_path / "gate_summary.json").write_text(json.dumps(record), encoding="utf-8")
    assert GateRunService().judge_dir(tmp_path).verdict == "FAIL"


def test_judge_rejects_a_missing_log_or_exit_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _passed_round(tmp_path, monkeypatch)
    (tmp_path / "core.txt").unlink()
    (tmp_path / "cli.exit").unlink()
    judged = GateRunService().judge_dir(tmp_path)
    assert (
        judged.results["core"].verdict == "FAIL"
        and judged.results["cli"].verdict == "FAIL"
        and judged.verdict == "FAIL"
    )


def test_judge_with_the_pinned_summary_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, digest = _passed_round(tmp_path, monkeypatch)
    assert GateRunService().judge_dir(tmp_path, expect_sha256=digest).verdict == "PASS"
    wrong = GateRunService().judge_dir(tmp_path, expect_sha256="0" * 64)
    assert wrong.verdict == "PARTIAL" and any("SHA-256" in reason for reason in wrong.reasons)


def test_judge_with_a_worktree_notices_a_moved_or_dirty_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = _Tree()
    repo = tree.install(monkeypatch)
    GateRunService(runner=_Recorder()).run(repo, tmp_path)
    assert GateRunService().judge_dir(tmp_path, worktree=repo).verdict == "PASS"
    tree.head = "c" * 40
    assert GateRunService().judge_dir(tmp_path, worktree=repo).verdict == "PARTIAL"
    tree.head = "a" * 40
    tree.status = "?? new.py"
    assert GateRunService().judge_dir(tmp_path, worktree=repo).verdict == "PARTIAL"


def test_a_record_without_the_end_of_round_facts_is_not_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _passed_round(tmp_path, monkeypatch)
    record = json.loads((tmp_path / "gate_summary.json").read_text(encoding="utf-8"))
    del record["commit_end"], record["git_dirty_end"]  # an older or hand-made record
    (tmp_path / "gate_summary.json").write_text(json.dumps(record), encoding="utf-8")
    assert GateRunService().judge_dir(tmp_path).verdict == "PARTIAL"


@pytest.mark.parametrize("field", ["git_dirty", "git_dirty_end"])
@pytest.mark.parametrize("value", [True, None])
def test_either_dirty_flag_alone_being_bad_is_not_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    """Counterexample: edit one of the two dirty flags in the record; each must be checked on its own."""

    _passed_round(tmp_path, monkeypatch)
    record = json.loads((tmp_path / "gate_summary.json").read_text(encoding="utf-8"))
    record[field] = value
    (tmp_path / "gate_summary.json").write_text(json.dumps(record), encoding="utf-8")
    assert GateRunService().judge_dir(tmp_path).verdict == "PARTIAL"


def test_judge_with_a_worktree_notices_a_hidden_ignored_code_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counterexample: the tree is clean and on the same commit, but an ignored conftest appeared after the round."""

    tree = _Tree()
    repo = tree.install(monkeypatch)
    GateRunService(runner=_Recorder()).run(repo, tmp_path)
    tree.ignored = "tests/conftest.py\n"
    result = GateRunService().judge_dir(tmp_path, worktree=repo)
    assert result.verdict == "PARTIAL" and any("不一致" in reason for reason in result.reasons)


def test_default_runner_kills_a_group_that_overruns_and_reports_124(tmp_path: Path) -> None:
    """Counterexample: a hung group must not hang the gate; the exit is 124 and the log says it was killed."""

    import sys

    log = tmp_path / "g.txt"
    code = gate.default_runner(
        [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, {}, log, 1
    )
    assert code == 124 and "killed after 1 s" in log.read_text(encoding="utf-8")
    assert gate.default_runner([sys.executable, "-c", "print('ok')"], tmp_path, {}, log, 30) == 0


def test_a_git_that_fails_is_unknown_not_clean(tmp_path: Path) -> None:
    """Counterexample (audit 2): a broken index makes ``git status`` exit 128 with empty output; that must not read as a clean tree."""

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    for key, value in (
        ("user.email", "t@example.com"),
        ("user.name", "t"),
        ("commit.gpgsign", "false"),
    ):
        git("config", key, value)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "c0")
    (tmp_path / "tests" / "conftest.py").write_text("x = 1\n", encoding="utf-8")  # untracked
    (tmp_path / ".git" / "index").write_bytes(b"not an index")
    assert gate._git(tmp_path, "status", "--porcelain") is None
    state = gate.tree_state(tmp_path, tmp_path)
    assert state.dirty is None and gate.UNREADABLE_IGNORED in state.ignored_code


@pytest.mark.parametrize("broken", ["status", "ls-files"])
def test_a_round_is_not_pass_when_git_cannot_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    tree = _Tree()
    if broken == "status":
        tree.status = None
    else:
        tree.ignored = None
    summary = GateRunService(runner=_Recorder()).run(tree.install(monkeypatch), tmp_path)
    assert summary.verdict == "PARTIAL" and summary.reasons
    assert GateRunService().judge_dir(tmp_path).verdict == "PARTIAL"
