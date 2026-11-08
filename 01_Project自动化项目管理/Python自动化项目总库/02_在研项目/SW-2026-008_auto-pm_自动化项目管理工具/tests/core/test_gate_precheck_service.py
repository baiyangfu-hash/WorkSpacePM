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
        "auto_pm/a/__init__.py": "",
        "auto_pm/a/b.py": "",
        "auto_pm/a/c.py": "",
        "auto_pm/z/__init__.py": "",
        "auto_pm/z/deep.py": "",
        "tests/__init__.py": "",
        "tests/conftest.py": "",
        "tests/core/__init__.py": "",
        "tests/core/test_imports_dotted.py": "import auto_pm.a.b\n",
        "tests/core/test_imports_as.py": "import auto_pm.a.b as bee\n",
        "tests/core/test_imports_from_module.py": "from auto_pm.a.b import thing\n",
        "tests/core/test_imports_from_package.py": "from auto_pm.a import b\n",
        "tests/core/test_imports_paren_multiline.py": "from auto_pm.a import (\n    c,\n    b,\n)\n",
        "tests/core/test_imports_in_function.py": "def test_x():\n    from auto_pm.a.b import thing\n",
        "tests/core/test_only_c.py": "from auto_pm.a import c\n",
        "tests/core/test_mentions_in_comment.py": "# auto_pm.a.b is only named in a comment here\nx = 1\n",
        "tests/core/test_via_helper.py": "from tests.core_helper import make\n",
        "tests/core_helper.py": "from auto_pm.a.b import thing\n",
        "tests/core/test_via_helper_chain.py": "from tests.chain_two import make\n",
        "tests/chain_two.py": "from tests.core_helper import make\n",
        "tests/core/test_relative.py": "from .sibling_helper import make\n",
        "tests/core/sibling_helper.py": "from auto_pm.a.b import thing\n",
        "tests/cli/__init__.py": "",
        "tests/cli/conftest.py": "",
        "tests/cli/test_one.py": "x = 1\n",
        "tests/cli/sub/test_two.py": "x = 1\n",
        "tests/cli/conftest_user/test_three.py": "x = 1\n",
        "tests/qml/test_reads_qml.py": "x = 'a.qml'\n",
        "tests/core/test_deep.py": "import auto_pm.z.deep\n",
        "tests/core/test_string_dotted.py": "def test_x(monkeypatch):\n    monkeypatch.setattr('auto_pm.a.c.thing', 1)\n",
        "tests/core/test_string_path.py": "def test_x():\n    open('auto_pm/a/c.py')\n    open('main.py')\n",
        "tests/infrastructure/test_guard_rglob.py": "from pathlib import Path\ndef test_x():\n    list(Path('auto_pm').rglob('*.py'))\n",
        "tests/infrastructure/test_guard_walk.py": "import os\ndef test_x():\n    list(os.walk('scripts'))\n",
        "tests/infrastructure/test_walks_elsewhere.py": "from pathlib import Path\ndef test_x():\n    list(Path('other').rglob('*'))\n",
        "tests/infrastructure/test_names_tree_no_walk.py": "x = 'auto_pm'\n",
    }
    for relative, text in files.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return project


def test_a_changed_module_is_related_to_every_test_that_imports_it_in_any_written_form(tmp_path: Path) -> None:
    tests, note = _graph(_project(tmp_path), ["auto_pm/a/b.py"])
    assert "守卫" in note
    assert [t for t in tests if "infrastructure" not in t] == [
        "tests/core/test_imports_as.py",
        "tests/core/test_imports_dotted.py",
        "tests/core/test_imports_from_module.py",
        "tests/core/test_imports_from_package.py",
        "tests/core/test_imports_in_function.py",
        "tests/core/test_imports_paren_multiline.py",  # audit 1 of #634: b on the second line of a parenthesised import
        "tests/core/test_relative.py",  # through a helper reached by a relative import
        "tests/core/test_via_helper.py",  # through a helper module under tests/
        "tests/core/test_via_helper_chain.py",  # through two helpers
    ]


def test_any_python_change_pulls_in_every_guard_test_that_walks_the_source_tree(tmp_path: Path) -> None:
    # audit 2 of #634: tests that rglob/os.walk the whole tree never import the changed module, so the import graph cannot pick them
    for change in ("auto_pm/z/deep.py", "tests/core/test_only_c.py"):
        tests, note = related_tests(_project(tmp_path / change.replace("/", "_")), [change])
        assert {"tests/infrastructure/test_guard_rglob.py", "tests/infrastructure/test_guard_walk.py"} <= set(tests)
        assert "2 个" in note
        assert "tests/infrastructure/test_walks_elsewhere.py" not in tests  # walks, but names none of the three words


def test_a_test_that_names_a_module_or_file_in_a_string_is_related(tmp_path: Path) -> None:
    # audit 2 self-check: monkeypatch.setattr("pkg.mod.func", ...) and open("main.py") load/read the file without importing it
    project = _project(tmp_path)
    assert "tests/core/test_string_dotted.py" in _graph(project, ["auto_pm/a/c.py"])[0]
    assert "tests/core/test_string_dotted.py" not in _graph(project, ["auto_pm/a/b.py"])[0]
    assert "tests/core/test_string_path.py" in _graph(project, ["auto_pm/a/c.py"])[0]
    (project / "main.py").write_text("", encoding="utf-8")
    assert "tests/core/test_string_path.py" in _graph(project, ["main.py"])[0]


def test_a_test_that_walks_a_folder_without_naming_the_source_tree_or_names_it_without_walking_is_not_a_guard(tmp_path: Path) -> None:
    tests, _ = _graph(_project(tmp_path), ["auto_pm/a/c.py"])
    assert "tests/infrastructure/test_names_tree_no_walk.py" not in tests


def test_a_deleted_or_renamed_module_still_selects_the_tests_that_import_its_old_name(tmp_path: Path) -> None:
    # D-128 (audit 3 of #634): the old path no longer exists, yet the tests importing it must run (they fail with ImportError)
    project = _project(tmp_path)
    (project / "auto_pm/a/b.py").unlink()
    tests, _ = _graph(project, ["auto_pm/a/b.py", "auto_pm/a/b_renamed.py"])
    assert "tests/core/test_imports_dotted.py" in tests and "tests/core/test_via_helper.py" in tests


def test_a_documentation_only_change_pulls_in_no_guard(tmp_path: Path) -> None:
    assert _graph(_project(tmp_path), ["docs/x.md"]) == ([], "")


def test_a_test_that_only_imports_a_sibling_or_only_names_the_module_in_text_is_not_related(tmp_path: Path) -> None:
    tests, _ = _graph(_project(tmp_path), ["auto_pm/a/b.py"])
    assert "tests/core/test_only_c.py" not in tests and "tests/core/test_mentions_in_comment.py" not in tests


def test_a_changed_package_init_reaches_every_importer_of_anything_below_it(tmp_path: Path) -> None:
    tests, _ = _graph(_project(tmp_path), ["auto_pm/z/__init__.py"])
    assert tests == ["tests/core/test_deep.py"]


def test_a_changed_test_file_is_itself_related_and_a_deleted_one_is_not(tmp_path: Path) -> None:
    project = _project(tmp_path)
    assert _graph(project, ["tests/core/test_only_c.py"])[0] == ["tests/core/test_only_c.py"]
    assert _graph(project, ["tests/core/test_gone.py"])[0] == []


def test_a_changed_helper_module_is_related_to_the_tests_that_import_it_directly_or_through_another_helper(tmp_path: Path) -> None:
    tests, _ = _graph(_project(tmp_path), ["tests/core_helper.py"])
    assert tests == ["tests/core/test_via_helper.py", "tests/core/test_via_helper_chain.py"]


def test_a_changed_sub_conftest_is_related_to_every_test_below_its_folder_only(tmp_path: Path) -> None:
    tests, _ = _graph(_project(tmp_path), ["tests/cli/conftest.py"])
    assert tests == ["tests/cli/conftest_user/test_three.py", "tests/cli/sub/test_two.py", "tests/cli/test_one.py"]


def test_a_sub_conftest_change_next_to_a_module_change_does_not_hide_either(tmp_path: Path) -> None:
    """Audit 1.3: the conftest change used to be ignored as soon as another change had tests."""
    tests, _ = _graph(_project(tmp_path), ["tests/cli/conftest.py", "auto_pm/a/c.py"])
    assert "tests/cli/test_one.py" in tests and "tests/core/test_only_c.py" in tests


@pytest.mark.parametrize("path", ["tests/conftest.py", "pyproject.toml", "requirements.txt"])
def test_a_change_that_can_break_any_test_makes_everything_related_and_says_so(tmp_path: Path, path: str) -> None:
    tests, note = _graph(_project(tmp_path), [path])
    assert tests == ["tests"] and "全部" in note


@pytest.mark.parametrize("path", ["qml/Main.qml", "templates/x.jinja", "config/rules.yaml", "data/blob.json", "assets/logo.png"])
def test_a_changed_non_python_file_makes_everything_related_never_nothing(tmp_path: Path, path: str) -> None:
    """Audit 1.1: a .qml or .jinja change used to run no test at all and still say PASS."""
    tests, note = _graph(_project(tmp_path), [path, "README.md"])
    assert tests == ["tests"] and "非 Python" in note


def test_a_test_file_that_cannot_be_parsed_makes_everything_related(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "tests/core/test_broken.py").write_text("def broken(:\n", encoding="utf-8")
    tests, note = related_tests(project, ["auto_pm/a/c.py"])
    assert tests == ["tests"] and "解析不了" in note


def test_a_test_file_with_a_utf8_bom_is_still_parsed(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "tests/core/test_bom.py").write_bytes(b"\xef\xbb\xbffrom auto_pm.a import c\n")
    tests, _ = related_tests(project, ["auto_pm/a/c.py"])
    assert "tests/core/test_bom.py" in tests and tests != ["tests"]


def test_a_docs_only_change_has_no_related_tests(tmp_path: Path) -> None:
    assert _graph(_project(tmp_path), ["README.md", "docs/x.md", "notes/y.rst"]) == ([], "")


# ── changed files (real git) ────────────────────────────


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
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


def _graph(project: Path, changes: Sequence[str]) -> tuple[list[str], str]:
    """``related_tests`` without the guard tests (``tests/infrastructure`` in the fixture), to look at the import graph alone."""

    tests, note = related_tests(project, changes)
    return [t for t in tests if "infrastructure" not in t], note


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


def _inside(name: str) -> str:
    project = project_dir_in(_repo_root())
    return f"{project.relative_to(_repo_root()).as_posix()}/{name}"


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


def test_the_full_tree_runs_in_parallel_and_junit_goes_to_the_logs_not_the_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = _Recorder()
    _service_run(monkeypatch, tmp_path, recorder, _py_changed(), (["tests"], "非 Python 文件"))
    argv = recorder.calls[-1][1]
    assert argv[argv.index("-n") + 1] != "1" and "loadfile" in argv
    assert f"--junitxml={tmp_path / 'out' / 'pytest-junit.xml'}" in argv


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
    report = _service_run(monkeypatch, tmp_path, recorder, [_inside("README.md")], ([], ""))
    assert report.verdict == "PASS" and [name for name, *_ in recorder.calls] == ["ruff", "mypy"]
    assert next(s for s in report.steps if s.name == "pytest").verdict == "SKIPPED"


def test_a_change_outside_the_project_folder_is_listed_and_the_verdict_is_never_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # audit 2 of #634: only AGENTS.md at the repository root changed; ruff/mypy "PASS" say nothing about it
    recorder = _Recorder()
    report = _service_run(monkeypatch, tmp_path, recorder, ["AGENTS.md", _inside("README.md")], ([], ""))
    assert report.outside_changes == ["AGENTS.md"] and report.verdict == "UNVERIFIED"
    failing = _service_run(monkeypatch, tmp_path, _Recorder({"ruff": (1, "E501\n")}), ["AGENTS.md"], ([], ""))
    assert failing.verdict == "FAIL"


def test_a_runner_that_cannot_start_is_a_failure_not_a_crash(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def broken(argv: Sequence[str], cwd: Path, env: Mapping[str, str], log: Path, timeout: int) -> int:
        raise OSError("no such interpreter")

    monkeypatch.setattr(pre, "changed_files", lambda worktree, base: [_inside("README.md")])
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
    monkeypatch.setattr(pre, "changed_files", lambda worktree, base: [_inside("README.md")])
    monkeypatch.setattr("auto_pm.ui.cli.gate.PrecheckService", lambda: PrecheckService(runner=_Recorder()))
    result = CliRunner().invoke(gate_group, ["precheck", "--worktree", str(_repo_root()), "--out", str(tmp_path / "o")])
    assert result.exit_code == 0 and "自检结论 PASS" in result.output and "gate run" in result.output
    as_json = CliRunner().invoke(gate_group, ["precheck", "--worktree", str(_repo_root()), "--out", str(tmp_path / "o2"), "--json"])
    assert as_json.exit_code == 0 and '"verdict": "PASS"' in as_json.output


def test_the_command_exits_one_on_a_failed_step_and_two_when_it_cannot_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(pre, "changed_files", lambda worktree, base: [_inside("README.md")])
    failing = _Recorder({"ruff": (1, "E501\n")})
    monkeypatch.setattr("auto_pm.ui.cli.gate.PrecheckService", lambda: PrecheckService(runner=failing))
    failed = CliRunner().invoke(gate_group, ["precheck", "--worktree", str(_repo_root()), "--out", str(tmp_path / "o")])
    assert failed.exit_code == 1 and "FAIL" in failed.output and "完整输出" in failed.output
    not_git = CliRunner().invoke(gate_group, ["precheck", "--worktree", str(tmp_path)])
    assert not_git.exit_code == 2
