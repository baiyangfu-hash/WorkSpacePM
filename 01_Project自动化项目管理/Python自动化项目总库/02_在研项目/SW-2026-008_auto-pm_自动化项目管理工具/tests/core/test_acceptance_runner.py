"""The verifier runs the approved acceptance commands itself (CHG-SCPT-2026-472).

Real subprocesses, no mocks of the process layer: exit codes, UTF-8 output, Chinese paths and arguments, ``git`` with
``core.quotePath=false``, timeouts, and the evidence file.  The Chinese-Windows quoting rules run on every platform by
parsing with ``windows=True`` and executing the resulting argument list.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from auto_pm.application.core.acceptance_runner import (
    execution_environment,
    mismatch_lines,
    refusal_reason,
    run_acceptance_checks,
    worktree_environment,
    write_report,
)
from auto_pm.contracts.acceptance_command import parse_command
from auto_pm.contracts.plan_checklist import AcceptanceCheck
from tests.git_support import git_do
from tests.plan_checklist_support import native_command

PYTHON = sys.executable


def _quote(*argv: str) -> str:
    return shlex.join(argv)


def _check(command: str, expected: int = 0) -> AcceptanceCheck:
    return AcceptanceCheck(command=command, expected_exit_code=expected)


def _run(tmp_path: Path, command: str, expected: int = 0, **kwargs: object):  # type: ignore[no-untyped-def]
    return run_acceptance_checks([_check(command, expected)], cwd=tmp_path, windows=False, **kwargs)[0]  # type: ignore[arg-type]


# ── exit codes ──────────────────────────────────────────────────────────────


def test_a_command_with_the_approved_exit_code_passes(tmp_path: Path) -> None:
    result = _run(tmp_path, _quote(PYTHON, "-c", "print('ok')"))
    assert result.passed and result.exit_code == 0 and "ok" in result.output_tail and result.error == ""


def test_the_approved_code_need_not_be_zero(tmp_path: Path) -> None:
    """``=> 3`` means the check passes when the command exits 3, and fails when it exits 0."""
    assert _run(tmp_path, _quote(PYTHON, "-c", "raise SystemExit(3)"), expected=3).passed
    assert not _run(tmp_path, _quote(PYTHON, "-c", "pass"), expected=3).passed


def test_a_different_exit_code_is_a_mismatch_that_names_both_codes_and_the_output(tmp_path: Path) -> None:
    result = _run(tmp_path, _quote(PYTHON, "-c", "import sys; print('boom detail'); sys.exit(2)"))
    assert not result.passed and result.exit_code == 2
    (line,) = mismatch_lines([result])
    assert "第 1 条" in line and "期望退出码 0，实际 2" in line and "boom detail" in line


def test_stderr_is_part_of_the_recorded_output(tmp_path: Path) -> None:
    result = _run(tmp_path, _quote(PYTHON, "-c", "import sys; sys.stderr.write('to stderr')"))
    assert "to stderr" in result.output_tail


def test_all_commands_run_even_after_a_failure_so_one_report_shows_every_mismatch(tmp_path: Path) -> None:
    results = run_acceptance_checks(
        [_check(_quote(PYTHON, "-c", "raise SystemExit(1)")), _check(_quote(PYTHON, "-c", "pass"))],
        cwd=tmp_path,
        windows=False,
    )
    assert [item.passed for item in results] == [False, True]


# ── what cannot be run ──────────────────────────────────────────────────────


def test_a_missing_executable_is_a_failure_with_the_name_not_a_crash(tmp_path: Path) -> None:
    result = _run(tmp_path, "no-such-tool-xyz --version")
    assert not result.passed and result.exit_code is None and "no-such-tool-xyz" in result.error
    assert "没有跑成" in mismatch_lines([result])[0]


def test_a_command_that_needs_a_shell_is_not_run_at_all(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    result = _run(tmp_path, f"{_quote(PYTHON, '-c', 'pass')} && {_quote(PYTHON, '-c', f'open({str(marker)!r}, chr(119)).close()')}")
    assert not result.passed and result.exit_code is None and "不能按原文执行" in result.error
    assert not marker.exists()


def test_a_missing_working_directory_fails_every_command(tmp_path: Path) -> None:
    results = run_acceptance_checks([_check("python -c pass")], cwd=tmp_path / "gone", windows=False)
    assert not results[0].passed and "执行目录不存在" in results[0].error


def test_a_command_that_never_ends_is_killed_at_the_timeout(tmp_path: Path) -> None:
    result = _run(tmp_path, _quote(PYTHON, "-c", "import time; time.sleep(60)"), timeout=1)
    assert not result.passed and result.exit_code is None and "超过 1 秒" in result.error


# ── working directory, environment, output ──────────────────────────────────


def test_commands_run_in_the_given_worktree(tmp_path: Path) -> None:
    (tmp_path / "here.txt").write_text("x", encoding="utf-8")
    code = "import pathlib, sys; sys.exit(0 if pathlib.Path('here.txt').exists() else 9)"
    assert _run(tmp_path, _quote(PYTHON, "-c", code)).passed


def test_python_runs_in_utf8_mode_and_lease_credentials_are_not_handed_down(tmp_path: Path) -> None:
    env = execution_environment({"PATH": "/usr/bin", "AUTO_PM_LEASE_TOKEN": "secret", "KEEP": "1"})
    assert env["PYTHONUTF8"] == "1" and env["PYTHONIOENCODING"] == "utf-8"
    assert "AUTO_PM_LEASE_TOKEN" not in env and env["KEEP"] == "1"
    assert env["GIT_CONFIG_COUNT"] == "1" and env["GIT_CONFIG_KEY_0"] == "core.quotePath"


def test_an_existing_git_config_count_is_extended_not_replaced() -> None:
    env = execution_environment({"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "a", "GIT_CONFIG_VALUE_0": "1"})
    assert env["GIT_CONFIG_COUNT"] == "3" and env["GIT_CONFIG_KEY_2"] == "core.quotePath"
    assert env["GIT_CONFIG_KEY_0"] == "a"


def test_chinese_output_is_recorded_as_chinese(tmp_path: Path) -> None:
    result = _run(tmp_path, _quote(PYTHON, "-c", "print('\\u4e2d\\u6587\\u8f93\\u51fa')"))
    assert "中文输出" in result.output_tail


def test_chinese_output_in_the_chinese_windows_code_page_is_still_readable(tmp_path: Path) -> None:
    code = "import sys; sys.stdout.buffer.write('中文'.encode('gbk'))"
    result = _run(tmp_path, _quote(PYTHON, "-c", code))
    assert result.passed and "中文" in result.output_tail


def test_a_chinese_argument_and_a_chinese_working_directory_arrive_intact(tmp_path: Path) -> None:
    folder = tmp_path / "项目 甲"
    folder.mkdir()
    (folder / "文件.txt").write_text("内容", encoding="utf-8")
    code = "import sys, pathlib; print(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))"
    result = run_acceptance_checks(
        [_check(_quote(PYTHON, "-c", code, "文件.txt"))], cwd=folder, windows=False
    )[0]
    assert result.passed and "内容" in result.output_tail


def test_windows_quoting_rules_split_a_chinese_path_with_spaces_and_the_command_runs(tmp_path: Path) -> None:
    """The Chinese-Windows case: ``"…\\项目 目录\\a.py" 参数`` is split by the MSVCRT rules, then executed as a list."""
    script = tmp_path / "项目 目录" / "脚本.py"
    script.parent.mkdir()
    script.write_text("import sys; print(sys.argv[1:])", encoding="utf-8")
    command = f'"{PYTHON}" "{script}" 参数一 "参数 二"'
    result = run_acceptance_checks([_check(command)], cwd=tmp_path, windows=True)[0]
    assert result.passed
    assert result.argv[-2:] == ("参数一", "参数 二") and "['参数一', '参数 二']" in result.output_tail


def test_the_output_tail_keeps_the_last_lines_and_the_hash_covers_everything(tmp_path: Path) -> None:
    code = "print('\\n'.join(f'line {n}' for n in range(100)))"
    result = _run(tmp_path, _quote(PYTHON, "-c", code))
    assert result.output_tail.splitlines()[-1] == "line 99" and "line 0" not in result.output_tail
    assert len(result.output_tail.splitlines()) == 20
    assert len(result.output_sha256) == 64 and result.output_bytes > len(result.output_tail)


# ── git and Chinese file names ──────────────────────────────────────────────


def _repo_with_chinese_file(root: Path) -> None:
    git_do(root, "init", "-q")
    (root / "中文文件.txt").write_text("x", encoding="utf-8")
    git_do(root, "add", "-A")


@pytest.mark.skipif(sys.platform == "win32", reason="the quoting default differs only in how this test names the executable")
def test_a_git_command_lists_chinese_names_as_they_are_and_records_the_inserted_option(tmp_path: Path) -> None:
    _repo_with_chinese_file(tmp_path)
    plain = subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "core.quotePath=true", "ls-files"], capture_output=True, check=True
    ).stdout.decode()
    assert "\\" in plain  # without the option Git prints an octal-escaped, quoted name -- the failure being prevented

    result = _run(tmp_path, "git ls-files")

    assert result.passed and "中文文件.txt" in result.output_tail and "\\344" not in result.output_tail
    assert result.argv_differs and result.argv[1:3] == ("-c", "core.quotePath=false")
    assert result.command == "git ls-files"  # the approved text is recorded verbatim next to what really ran


def test_git_called_from_inside_a_script_also_prints_chinese_names(tmp_path: Path) -> None:
    _repo_with_chinese_file(tmp_path)
    code = "import subprocess; print(subprocess.run(['git', 'ls-files'], capture_output=True, text=True, encoding='utf-8').stdout)"
    result = _run(tmp_path, _quote(PYTHON, "-c", code))
    assert "中文文件.txt" in result.output_tail and "\\344" not in result.output_tail


# ── the evidence file ───────────────────────────────────────────────────────


def test_the_report_records_the_approved_text_the_executed_arguments_and_the_real_codes(tmp_path: Path) -> None:
    results = run_acceptance_checks(
        [_check(_quote(PYTHON, "-c", "print('good')")), _check(_quote(PYTHON, "-c", "raise SystemExit(4)"))],
        cwd=tmp_path,
        windows=False,
    )
    path = write_report(tmp_path / "control", "RUN-1", results)

    assert path.parent == tmp_path / "control" / ".auto-pm" / "reports" / "acceptance"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["run_id"] == "RUN-1" and data["all_passed"] is False
    first, second = data["checks"]
    assert first["exit_code"] == 0 and first["passed"] and "good" in first["output_tail"]
    assert second["exit_code"] == 4 and second["expected_exit_code"] == 0 and not second["passed"]
    assert second["command"] == results[1].command and second["argv"][0] == PYTHON


# ── the command forms the approved plans really use (written from the workspace root) ─────────────────────


def test_the_windows_forms_in_real_approved_plans_split_into_the_expected_arguments() -> None:
    """Exact strings from approved plans; backslashes stay literal under the Windows rules."""
    assert parse_command(r".venv\Scripts\python.exe -B main.py plc check DJ-2026-011", windows=True).argv == (
        r".venv\Scripts\python.exe", "-B", "main.py", "plc", "check", "DJ-2026-011",
    )  # fmt: skip
    assert parse_command(r"git -C .auto-pm\worktrees\trae status --short", windows=True).argv == (
        "git", "-C", r".auto-pm\worktrees\trae", "status", "--short",
    )  # fmt: skip
    assert parse_command("git -C . status --short", windows=True).argv == ("git", "-C", ".", "status", "--short")


@pytest.fixture
def control_root(tmp_path: Path) -> Path:
    """What a control root looks like to a command: ``.venv`` with an interpreter, ``main.py``, a worktree for an agent."""
    root = tmp_path / "控制根 目录"
    (root / ".venv" / "bin").mkdir(parents=True)
    if sys.platform != "win32":  # the POSIX-spelled tests below skip on Windows; the not-found test needs no interpreter
        os.symlink(PYTHON, root / ".venv" / "bin" / "python")
    (root / "main.py").write_text(
        "import os, sys\nprint(sys.argv[1:], os.environ.get('AUTO_PM_RUN_WORKTREE', ''))\n"
        "sys.exit(0 if sys.argv[1:] != ['boom'] else 6)\n",
        encoding="utf-8",
    )
    worktree = root / ".auto-pm" / "worktrees" / "trae"
    worktree.mkdir(parents=True)
    git_do(worktree, "init", "-q")
    git_do(root, "init", "-q")
    return root


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX spelling of the same forms; the Windows strings are split above")
def test_commands_written_from_the_workspace_root_run_from_the_control_root(control_root: Path) -> None:
    worktree = control_root / ".auto-pm" / "worktrees" / "trae"
    results = run_acceptance_checks(
        [
            _check(".venv/bin/python -B main.py plc check DJ-2026-011"),
            _check("git -C .auto-pm/worktrees/trae status --short"),
            _check("git -C . status --short"),
            _check(".venv/bin/python -B main.py doc check --说明 中文"),
        ],
        cwd=control_root,
        extra_env={"AUTO_PM_RUN_WORKTREE": str(worktree)},
        windows=False,
    )
    assert [item.passed for item in results] == [True, True, True, True], mismatch_lines(results)
    assert "['plc', 'check', 'DJ-2026-011']" in results[0].output_tail and str(worktree) in results[0].output_tail
    assert "['doc', 'check', '--说明', '中文']" in results[3].output_tail


def test_the_same_commands_run_from_a_worktree_would_not_be_found(control_root: Path) -> None:
    """Why the control root is the working directory: a worktree has no ``.venv``."""
    worktree = control_root / ".auto-pm" / "worktrees" / "trae"
    result = run_acceptance_checks([_check(".venv/bin/python -B main.py doc check")], cwd=worktree, windows=False)[0]
    assert not result.passed and "找不到命令" in result.error


def test_extra_environment_reaches_the_command_without_changing_the_base(tmp_path: Path) -> None:
    code = "import os; raise SystemExit(0 if os.environ['MY_EXTRA'] == '值' else 4)"
    assert _run(tmp_path, _quote(PYTHON, "-c", code), extra_env={"MY_EXTRA": "值"}).passed
    assert not _run(tmp_path, _quote(PYTHON, "-c", code)).passed


@pytest.mark.skipif(sys.platform == "win32", reason="swaps file descriptor 0 for a pipe that never delivers data")
def test_a_command_that_reads_standard_input_gets_end_of_input_instead_of_waiting(tmp_path: Path) -> None:
    """stdin is closed (``DEVNULL``): a command that reads it ends at once instead of hanging an IDE terminal."""
    reader, writer = os.pipe()  # nothing is ever written and the write end stays open: a read on it would block
    saved = os.dup(0)
    os.dup2(reader, 0)
    try:
        result = _run(tmp_path, _quote(PYTHON, "-c", "import sys; sys.exit(0 if sys.stdin.read() == '' else 3)"), timeout=20)
    finally:
        os.dup2(saved, 0)
        for descriptor in (saved, reader, writer):
            os.close(descriptor)
    assert result.passed, result.error or result.output_tail


# ── a read-only look at a command, without running it ──────────────────────────────────────────────────


def test_refusal_reason_is_empty_for_a_command_that_would_run_and_names_why_otherwise(tmp_path: Path) -> None:
    assert refusal_reason(native_command(PYTHON, "-c", "pass"), cwd=tmp_path) == ""
    assert "shell 符号" in refusal_reason("pytest && ruff check", cwd=tmp_path)
    assert "找不到命令 no-such-tool-xyz" in refusal_reason("no-such-tool-xyz --version", cwd=tmp_path)


# ── pointing a command that runs in the control root at the Run's worktree ──────────────────────────────


def test_the_worktree_environment_names_the_data_the_ledger_and_the_run_worktree() -> None:
    assert worktree_environment("/w/trae", "/root") == {
        "AUTO_PM_RUN_WORKTREE": "/w/trae",
        "AUTO_PM_WORKSPACE": "/w/trae",
        "AUTO_PM_CONTROL_ROOT": "/root",
    }


def test_the_worktree_placeholder_is_replaced_with_the_worktree_path_and_recorded_as_a_difference(tmp_path: Path) -> None:
    worktree = tmp_path / "工位 一"
    worktree.mkdir()
    (worktree / "ok.txt").write_text("x", encoding="utf-8")
    code = "import sys, pathlib; sys.exit(0 if pathlib.Path(sys.argv[1]).exists() else 8)"
    command = f"{_quote(PYTHON, '-c', code)} '{{worktree}}/ok.txt'"
    result = run_acceptance_checks(
        [_check(command)], cwd=tmp_path, extra_env=worktree_environment(worktree, tmp_path), windows=False
    )[0]
    assert result.passed and result.argv_differs and result.argv[-1] == f"{worktree}/ok.txt"
    assert result.command == command  # the approved text is kept verbatim


def test_a_placeholder_without_a_worktree_to_put_in_is_a_failure_not_a_literal_path(tmp_path: Path) -> None:
    result = _run(tmp_path, _quote(PYTHON, "-c", "pass", "{worktree}/x"))
    assert not result.passed and result.exit_code is None and "{worktree}" in result.error
