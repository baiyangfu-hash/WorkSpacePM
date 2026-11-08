"""``gate precheck``: the pre-push self check (ruff + mypy win32 + the tests that belong to the change).

What is pinned: which tests count as "related" to a change (and that a change nothing tests is UNVERIFIED, never a pass); that the three
steps run with CI's own flags in the project folder with a clean child environment; that a failing, missing or silent step can never
make the report PASS; that the command is read-only.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.application.core import gate_precheck_service as pre
from auto_pm.application.core.gate_precheck_service import (
    PrecheckService,
    changed_files,
    related_tests,
)
from auto_pm.application.core.gate_run_service import GateRunError, project_dir_in
from auto_pm.ui.cli.gate import gate_group

# ── related tests ───────────────────────────────────────


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    files = {
        "auto_pm/a/b.py": "",
        "auto_pm/a/c.py": "",
        "auto_pm/a/__init__.py": "",
        "tests/core/test_imports_dotted.py": "import auto_pm.a.b\n",
        "tests/core/test_imports_from_module.py": "from auto_pm.a.b import thing\n",
        "tests/core/test_imports_from_package.py": "from auto_pm.a import b\n",
        "tests/core/test_imports_from_package_many.py": "from auto_pm.a import c, b  # both\n",
        "tests/core/test_other.py": "from auto_pm.a import c\n",
        "tests/core/test_b_named.py": "x = 1\n",
        "tests/core/test_b2.py": "# mentions auto_pm.a.b only in a comment\n",
        "tests/conftest.py": "",
    }
    for relative, text in files.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return project


def test_a_changed_module_is_related_to_the_tests_that_import_it_or_are_named_after_it(tmp_path: Path) -> None:
    tests, note = related_tests(_project(tmp_path), ["auto_pm/a/b.py"])
    assert note == ""
    assert tests == [
        "tests/core/test_b2.py",  # named test_b*: the name rule is deliberately generous
        "tests/core/test_b_named.py",
        "tests/core/test_imports_dotted.py",
        "tests/core/test_imports_from_module.py",
        "tests/core/test_imports_from_package.py",
        "tests/core/test_imports_from_package_many.py",
    ]


def test_a_test_that_only_imports_a_sibling_module_is_not_related(tmp_path: Path) -> None:
    tests, _ = related_tests(_project(tmp_path), ["auto_pm/a/b.py"])
    assert "tests/core/test_other.py" not in tests


def test_a_changed_test_file_is_itself_related_and_a_deleted_one_is_not(tmp_path: Path) -> None:
    project = _project(tmp_path)
    assert related_tests(project, ["tests/core/test_other.py"])[0] == ["tests/core/test_other.py"]
    assert related_tests(project, ["tests/core/test_gone.py"])[0] == []


@pytest.mark.parametrize("path", ["tests/conftest.py", "pyproject.toml", "requirements.txt"])
def test_a_change_that_can_break_any_test_makes_everything_related_and_says_so(tmp_path: Path, path: str) -> None:
    tests, note = related_tests(_project(tmp_path), [path])
    assert tests == ["tests"] and "全部" in note


def test_a_docs_only_change_has_no_related_tests(tmp_path: Path) -> None:
    assert related_tests(_project(tmp_path), ["README.md", "docs/x.md"]) == ([], "")


# ── changed files (real git) ────────────────────────────


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def test_changed_files_counts_committed_staged_unstaged_and_untracked_changes(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "keep.py").write_text("1\n", encoding="utf-8")
    (repo / "edit.py").write_text("1\n", encoding="utf-8")
    (repo / "stage.py").write_text("1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "checkout", "-q", "-b", "work")
    (repo / "committed.py").write_text("1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "work")
    (repo / "edit.py").write_text("2\n", encoding="utf-8")  # unstaged
    (repo / "stage.py").write_text("2\n", encoding="utf-8")
    _git(repo, "add", "stage.py")  # staged
    (repo / "new.py").write_text("1\n", encoding="utf-8")  # untracked
    (repo / "中文目录").mkdir()
    (repo / "中文目录" / "新.py").write_text("1\n", encoding="utf-8")  # a non-ASCII name must come back as itself, not quoted
    assert changed_files(repo, "main") == ["committed.py", "edit.py", "new.py", "stage.py", "中文目录/新.py"]


def test_changed_files_refuses_when_the_base_is_unknown(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.py").write_text("1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    with pytest.raises(GateRunError, match="共同祖先"):
        changed_files(repo, "origin/nope")


# ── the steps ───────────────────────────────────────────

OK_PYTEST = "12 passed in 1.00s\n"


class _Recorder:
    def __init__(self, outcomes: Mapping[str, tuple[int, str]] | None = None) -> None:
        self.outcomes = dict(outcomes or {})
        self.calls: list[tuple[str, list[str], Path, dict[str, str]]] = []

    def __call__(self, argv: Sequence[str], cwd: Path, env: Mapping[str, str], log: Path, timeout: int) -> int:
        name = log.stem
        code, text = self.outcomes.get(name, (0, OK_PYTEST if name == "pytest" else "All checks passed!\n"))
        log.write_text(text, encoding="utf-8")
        self.calls.append((name, list(argv), cwd, dict(env)))
        return code


def _repo_root() -> Path:
    here = Path(pre.__file__).resolve()
    return next(p for p in here.parents if (p / ".git").exists())


def _service_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    recorder: _Recorder,
    changed: list[str],
    tests: tuple[list[str], str],
) -> pre.PrecheckReport:
    monkeypatch.setattr(pre, "changed_files", lambda worktree, base: changed)
    monkeypatch.setattr(pre, "related_tests", lambda project, inside: tests)
    return PrecheckService(runner=recorder).run(_repo_root(), out_dir=tmp_path / "out")


def _py_changed() -> list[str]:
    # repo-relative path under the project folder, so the prefix strip in ``run`` keeps it
    project = project_dir_in(_repo_root())
    prefix = project.relative_to(_repo_root()).as_posix()
    return [f"{prefix}/auto_pm/x.py"]


def test_a_clean_change_runs_ruff_mypy_and_the_related_tests_with_ci_flags_in_the_project_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AUTO_PM_WORKSPACE", "/real/ws")
    monkeypatch.setenv("AUTO_PM_CONTROL_ROOT", "/real/root")
    recorder = _Recorder()
    report = _service_run(monkeypatch, tmp_path, recorder, _py_changed(), (["tests/core/test_x.py"], ""))
    assert report.verdict == "PASS"
    assert [name for name, *_ in recorder.calls] == ["ruff", "mypy", "pytest"]
    by_name = {name: argv for name, argv, _, _ in recorder.calls}
    assert by_name["ruff"][-5:] == ["ruff", "check", "--no-cache", "auto_pm", "tests"]
    assert "--platform" in by_name["mypy"] and "win32" in by_name["mypy"]
    assert {"--no-incremental", "--cache-dir=/dev/null"} <= set(by_name["mypy"])
    assert by_name["pytest"][3:5] == ["pytest", "tests/core/test_x.py"] and "no:cacheprovider" in by_name["pytest"]
    assert all((cwd / "tests").is_dir() for _, _, cwd, _ in recorder.calls)
    assert all(not [k for k in env if k.upper().startswith("AUTO_PM_")] for *_, env in recorder.calls)
    assert all(env["PYTHONDONTWRITEBYTECODE"] == "1" for *_, env in recorder.calls)


def test_many_related_tests_run_in_parallel_few_do_not(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorder = _Recorder()
    _service_run(monkeypatch, tmp_path, recorder, _py_changed(), ([f"tests/t{i}.py" for i in range(5)], ""))
    assert "-n" in recorder.calls[-1][1]
    recorder = _Recorder()
    _service_run(monkeypatch, tmp_path, recorder, _py_changed(), (["tests/t.py"], ""))
    assert "-n" not in recorder.calls[-1][1]


@pytest.mark.parametrize("step", ["ruff", "mypy", "pytest"])
def test_a_failing_step_fails_the_report_although_the_others_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: str
) -> None:
    recorder = _Recorder({step: (1, "boom\n")})
    report = _service_run(monkeypatch, tmp_path, recorder, _py_changed(), (["tests/t.py"], ""))
    assert report.verdict == "FAIL"
    assert {s.name: s.verdict for s in report.steps}[step] == "FAIL"


def test_a_missing_tool_is_unverified_not_a_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorder = _Recorder({"mypy": (1, "/usr/bin/python: No module named mypy\n")})
    report = _service_run(monkeypatch, tmp_path, recorder, _py_changed(), (["tests/t.py"], ""))
    assert {s.name: s.verdict for s in report.steps}["mypy"] == "UNVERIFIED"
    assert report.verdict == "UNVERIFIED"


def test_a_failure_beats_a_missing_tool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorder = _Recorder({"mypy": (1, "No module named mypy\n"), "ruff": (1, "E501\n")})
    report = _service_run(monkeypatch, tmp_path, recorder, _py_changed(), (["tests/t.py"], ""))
    assert report.verdict == "FAIL"


def test_pytest_exit_zero_without_a_passed_line_is_a_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for text in ("", "no tests ran in 0.01s\n", "3 skipped in 0.10s\n"):
        recorder = _Recorder({"pytest": (0, text)})
        report = _service_run(monkeypatch, tmp_path, recorder, _py_changed(), (["tests/t.py"], ""))
        assert report.verdict == "FAIL", text


def test_a_timeout_is_a_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report = _service_run(monkeypatch, tmp_path, _Recorder({"ruff": (124, "")}), _py_changed(), (["tests/t.py"], ""))
    assert report.verdict == "FAIL" and "超时" in next(s.why for s in report.steps if s.name == "ruff")


def test_python_changed_but_no_test_found_is_unverified_never_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report = _service_run(monkeypatch, tmp_path, _Recorder(), _py_changed(), ([], ""))
    assert report.verdict == "UNVERIFIED"
    assert next(s for s in report.steps if s.name == "pytest").verdict == "UNVERIFIED"


def test_no_python_change_skips_pytest_and_can_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorder = _Recorder()
    report = _service_run(monkeypatch, tmp_path, recorder, ["README.md"], ([], ""))
    assert report.verdict == "PASS" and [name for name, *_ in recorder.calls] == ["ruff", "mypy"]
    assert next(s for s in report.steps if s.name == "pytest").verdict == "SKIPPED"


def test_a_runner_that_cannot_start_is_a_failure_not_a_crash(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def broken(argv: Sequence[str], cwd: Path, env: Mapping[str, str], log: Path, timeout: int) -> int:
        raise OSError("no such interpreter")

    monkeypatch.setattr(pre, "changed_files", lambda worktree, base: ["README.md"])
    report = PrecheckService(runner=broken).run(_repo_root(), out_dir=tmp_path / "out")
    assert report.verdict == "FAIL"


def test_a_folder_without_tests_is_refused(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    with pytest.raises(GateRunError):
        PrecheckService(runner=_Recorder()).run(repo, out_dir=tmp_path / "out")


# ── the command ─────────────────────────────────────────


def test_the_command_exit_codes_and_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pre, "changed_files", lambda worktree, base: ["README.md"])
    monkeypatch.setattr("auto_pm.ui.cli.gate.PrecheckService", lambda: PrecheckService(runner=_Recorder()))
    result = CliRunner().invoke(gate_group, ["precheck", "--worktree", str(_repo_root()), "--out", str(tmp_path / "o")])
    assert result.exit_code == 0 and "自检结论 PASS" in result.output and "gate run" in result.output
    as_json = CliRunner().invoke(gate_group, ["precheck", "--worktree", str(_repo_root()), "--out", str(tmp_path / "o2"), "--json"])
    assert as_json.exit_code == 0 and '"verdict": "PASS"' in as_json.output


def test_the_command_exits_one_on_a_failed_step_and_two_when_it_cannot_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pre, "changed_files", lambda worktree, base: ["README.md"])
    failing = _Recorder({"ruff": (1, "E501\n")})
    monkeypatch.setattr("auto_pm.ui.cli.gate.PrecheckService", lambda: PrecheckService(runner=failing))
    failed = CliRunner().invoke(gate_group, ["precheck", "--worktree", str(_repo_root()), "--out", str(tmp_path / "o")])
    assert failed.exit_code == 1 and "FAIL" in failed.output and "完整输出" in failed.output
    not_git = CliRunner().invoke(gate_group, ["precheck", "--worktree", str(tmp_path)])
    assert not_git.exit_code == 2
