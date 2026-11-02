"""Acceptance command text -> argument list (CHG-SCPT-2026-472).

``pm verify`` executes the approved commands itself, so the text must mean the same thing on the way there: split by the
platform's own quoting rules, never through a shell.  The Windows rules are tested on every platform (``windows=True``).
"""

from __future__ import annotations

import pytest

from auto_pm.contracts.acceptance_command import (
    AcceptanceCommandError,
    command_hints,
    command_problem,
    parse_command,
    with_git_quotepath,
)
from auto_pm.contracts.plan_checklist import (
    AcceptanceCheck,
    PlanChecklist,
    plan_checklist_problems,
)

# ── splitting ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "windows", "expected"),
    [
        ("python -m pytest tests/a.py -q", False, ["python", "-m", "pytest", "tests/a.py", "-q"]),
        ("python -m pytest tests/a.py -q", True, ["python", "-m", "pytest", "tests/a.py", "-q"]),
        # POSIX quoting
        ("python -c 'print(1 > 0)'", False, ["python", "-c", "print(1 > 0)"]),
        ('python -c "a;b"', False, ["python", "-c", "a;b"]),
        (r"python a\ b.py", False, ["python", "a b.py"]),
        # Windows: backslashes are literal, spaces need quotes
        (r"python C:\Users\fubai\tool.py --x", True, ["python", r"C:\Users\fubai\tool.py", "--x"]),
        (r'python "C:\项目 目录\a.py" 参数', True, ["python", r"C:\项目 目录\a.py", "参数"]),
        # MSVCRT: 2n backslashes + quote -> n backslashes and the quote toggles; 2n+1 -> n backslashes + literal quote
        (r'"a b\\" c', True, ["a b\\", "c"]),
        (r"a\"b c", True, ['a"b', "c"]),
        # Chinese arguments pass through untouched
        ("python main.py plc check DJ-2026-011 --说明 中文", False, ["python", "main.py", "plc", "check", "DJ-2026-011", "--说明", "中文"]),
        ("   python   x.py   ", True, ["python", "x.py"]),
    ],
)
def test_text_is_split_the_way_the_platform_would(text: str, windows: bool, expected: list[str]) -> None:
    assert list(parse_command(text, windows=windows).argv) == expected


def test_an_empty_quoted_argument_survives() -> None:
    assert list(parse_command('python x.py ""', windows=True).argv) == ["python", "x.py", ""]
    assert list(parse_command("python x.py ''", windows=False).argv) == ["python", "x.py", ""]


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize(
    ("text", "word"),
    [
        ("pytest && ruff check", "shell 符号"),
        ("pytest || true", "shell 符号"),
        ("pytest | tee out.txt", "shell 符号"),
        ("pytest; echo done", "shell 符号"),
        ("pytest > out.txt", "shell 符号"),
        ("pytest >> out.txt", "shell 符号"),
        ("pytest < in.txt", "shell 符号"),
        ("pytest 2>&1", "shell 符号"),
        ("pytest a&b", "shell 符号"),
        ("echo $(date)", "命令替换"),
        ("echo `date`", "命令替换"),
        ("pytest # acceptance 1", "注释"),
        ("FOO=1 python x.py", "环境变量赋值"),
        ("", "空"),
        ("   ", "空"),
        ("a\nb", "换行"),
        ('python -c "print(1)', "引号"),
    ],
)
def test_what_needs_a_shell_is_refused_with_a_reason(text: str, word: str, windows: bool) -> None:
    with pytest.raises(AcceptanceCommandError) as caught:
        parse_command(text, windows=windows)
    assert word in str(caught.value)
    assert word in command_problem(text, windows=windows)


@pytest.mark.parametrize("windows", [False, True])
def test_shell_symbols_inside_quotes_are_just_text(windows: bool) -> None:
    parsed = parse_command('python -c "x = 1 if a > b else 2; print(x | 3)"', windows=windows)
    assert parsed.argv[-1] == "x = 1 if a > b else 2; print(x | 3)"
    assert command_problem('pytest -k "a or b"', windows=windows) == ""


def test_a_clean_command_has_no_problem() -> None:
    assert command_problem("python -m pytest -q tests/test_alarm.py", windows=False) == ""


# ── git ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("argv", "changed"),
    [
        (("git", "status"), True),
        (("git", "-C", "dir", "ls-files"), True),
        ("/usr/bin/git ls-files".split(), True),
        (("C:\\Program Files\\Git\\cmd\\git.exe", "ls-files"), True),
        (("git", "-c", "core.quotePath=false", "ls-files"), False),
        (("git", "-c", "core.quotepath=false", "ls-files"), False),
        (("python", "git"), False),
        (("gitk",), False),
        ((), False),
    ],
)
def test_git_always_gets_quotepath_off_unless_the_caller_set_it(argv: tuple[str, ...], changed: bool) -> None:
    result, differs = with_git_quotepath(tuple(argv))
    assert differs is changed
    if changed:
        assert result[1:3] == ("-c", "core.quotePath=false") and result[3:] == tuple(argv)[1:]
    else:
        assert result == tuple(argv)


# ── hints (legal but fragile on a Chinese Windows console) ──────────────────


def test_a_python_inline_script_with_chinese_text_gets_the_escape_hint() -> None:
    hints = command_hints('python -c "print(\'中文\')"', windows=False)
    assert len(hints) == 1 and "\\uXXXX" in hints[0] and "python -B -c" in hints[0]


def test_an_ascii_only_inline_script_has_no_hint() -> None:
    assert command_hints("python -B -c \"print('\\u4e2d\\u6587')\"", windows=False) == ()


def test_git_with_a_chinese_path_mentions_quotepath() -> None:
    hints = command_hints("git ls-files 项目甲/文件.txt", windows=False)
    assert len(hints) == 1 and "core.quotePath=false" in hints[0]


def test_a_chinese_path_for_pytest_needs_no_hint() -> None:
    assert command_hints("python -m pytest 目录/测试.py", windows=False) == ()


def test_a_wildcard_argument_is_called_out() -> None:
    hints = command_hints("python -m pytest tests/test_*.py", windows=False)
    assert len(hints) == 1 and "通配符" in hints[0]


def test_hints_stay_silent_for_a_command_that_cannot_be_parsed() -> None:
    assert command_hints("pytest && x", windows=False) == ()


# ── the plan checklist refuses at plan time what verify could not run ───────


def _problems(*commands: str) -> tuple[str, ...]:
    checklist = PlanChecklist(
        original_request="原话",
        safety_circuit="否",
        acceptance_checks=tuple(AcceptanceCheck(command=text, expected_exit_code=0) for text in commands),
        rollback="git revert",
    )
    return plan_checklist_problems(
        checklist,
        declared=("a.py",),
        scope=("a.py",),
        risks=("风险",),
        acceptance_criteria=tuple(f"标准 {n}" for n, _ in enumerate(commands)),
    )


def test_the_plan_checklist_names_the_command_that_cannot_run_without_a_shell() -> None:
    problems = _problems("python -m pytest -q", "pytest && ruff check")
    assert len(problems) == 1
    assert problems[0].startswith("⑤第 2 条验收命令不能照原文执行") and "shell 符号" in problems[0]


def test_a_plan_with_plain_commands_has_no_problem() -> None:
    assert _problems("python -m pytest -q", "python main.py plc check DJ-2026-011") == ()


def test_a_blank_command_is_reported_once_by_the_count_rule_only() -> None:
    problems = _problems("python -m pytest", "  ")
    assert len(problems) == 1 and "每条验收标准的命令和退出码" in problems[0]
