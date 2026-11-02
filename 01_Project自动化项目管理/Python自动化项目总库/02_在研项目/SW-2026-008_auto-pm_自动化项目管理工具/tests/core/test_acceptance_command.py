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
    shell_fragility_problem,
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


def test_git_with_a_chinese_path_mentions_quotepath() -> None:
    hints = command_hints("git ls-files 项目甲/文件.txt", windows=False)
    assert len(hints) == 1 and "core.quotePath=false" in hints[0]


def test_a_chinese_path_for_pytest_needs_no_encoding_hint() -> None:
    assert command_hints("python -m pytest {worktree}/目录/测试.py", windows=False) == ()


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


# ── a command run from the control root must be pointed at the Run's worktree ───────────────────────────


@pytest.mark.parametrize(
    "command",
    [
        "python -m pytest tests/test_alarm.py -q",
        "pytest tests -q",
        "python scripts/check_io.py",
        r".venv\Scripts\python.exe -m pytest tests",
    ],
)
def test_pytest_and_scripts_that_do_not_name_the_worktree_get_the_hint(command: str) -> None:
    hints = command_hints(command, windows=True)
    assert len(hints) == 1 and "控制根" in hints[0] and "{worktree}" in hints[0] and "AUTO_PM_RUN_WORKTREE" in hints[0]


@pytest.mark.parametrize(
    "command",
    [
        "python -m pytest {worktree}/tests/test_alarm.py -q",
        "python {worktree}/scripts/check_io.py",
        "python -m pytest .auto-pm/worktrees/trae/tests -q",
        "python -B main.py plc check DJ-2026-011",  # cockpit commands are pointed at the worktree by environment
        r".venv\Scripts\python.exe -B main.py doc check",
        r".venv\Scripts\python.exe -B C:\work\main.py doc check",
        "python -c pass",
        "git -C {worktree} status --short",
    ],
)
def test_commands_that_name_the_worktree_or_are_cockpit_commands_get_no_worktree_hint(command: str) -> None:
    assert command_hints(command, windows=True) == ()


# ── commands that PowerShell would silently change when pasted (refused at plan time) ──


@pytest.mark.parametrize(
    ("command", "fragment"),
    [
        # Chinese text outside a cockpit command and outside a path
        ("python -c \"print('中文')\"", "中文只允许出现在 main.py 驾驶舱命令参数中"),
        ("python -B scripts/check.py 中文", "中文只允许出现在 main.py 驾驶舱命令参数中"),
        ("pytest -k 报警汇总", "中文只允许出现在 main.py 驾驶舱命令参数中"),
        ("git log --grep=修复", "中文只允许出现在 main.py 驾驶舱命令参数中"),
        # variables and backticks expand to something else (an unset variable becomes the empty string)
        ("python -c \"import sys; sys.exit(int('$missing' != ''))\"", "PowerShell 会把它展开"),
        ("pytest -k $name", "PowerShell 会把它展开"),
        ("python -B main.py doc check --pid $env:PID", "PowerShell 会把它展开"),
        ("python -B main.py doc check \"a`b\"", "PowerShell 会把它展开"),
        # bare wildcards
        ("pytest tests/test_*.py", "含通配符"),
        ("python -B main.py doc check *.md", "含通配符"),
        ("git ls-files src/?.py", "含通配符"),
    ],
)
@pytest.mark.parametrize("windows", [False, True])
def test_a_command_that_powershell_would_change_is_refused_with_the_rewrite_advice(
    command: str, fragment: str, windows: bool
) -> None:
    reason = shell_fragility_problem(command, windows=windows)
    assert fragment in reason, reason
    assert "python -B 脚本路径" in reason and "AUTO_PM_RUN_WORKTREE" in reason


@pytest.mark.parametrize(
    "command",
    [
        "python -B main.py doc check --说明 中文",  # user-facing text of a cockpit command
        "python -B main.py plc check DJ-2026-011",
        "python -m pytest {worktree}/目录/测试.py",  # a path: a mangled one fails loudly, it cannot pass
        "git ls-files 项目甲/文件.txt",
        "python -B -c \"print(2 * 3)\"",  # the code after -c is Python source, not a file pattern
        "python -B -c \"import sys; sys.exit(0)\"",
        "python -B {worktree}/scripts/check_io.py",
        "pytest tests -q -k alarm",
    ],
)
@pytest.mark.parametrize("windows", [False, True])
def test_plain_ascii_commands_and_cockpit_commands_with_chinese_arguments_are_not_refused(command: str, windows: bool) -> None:
    assert shell_fragility_problem(command, windows=windows) == ""


def test_a_command_that_cannot_be_parsed_is_left_to_command_problem() -> None:
    assert shell_fragility_problem("pytest && 中文", windows=False) == ""
    assert "shell 符号" in command_problem("pytest && 中文", windows=False)


@pytest.mark.parametrize("variant", ["中文", "$x", "*", "`"])
def test_the_plan_checklist_carries_the_fragility_reason_with_the_command_number(variant: str) -> None:
    checks = (
        AcceptanceCheck(command="python -B scripts/ok.py", expected_exit_code=0),
        AcceptanceCheck(command=f"python -B scripts/check.py {variant}", expected_exit_code=0),
    )
    checklist = PlanChecklist(
        original_request="x", safety_circuit="否", acceptance_checks=checks, rollback="git revert"
    )
    problems = plan_checklist_problems(
        checklist, declared=(), scope=("a/",), risks=("r",), acceptance_criteria=("一", "二")
    )
    assert any(item.startswith("⑤第 2 条验收命令不能照原文执行") for item in problems), problems
    assert not any(item.startswith("⑤第 1 条") for item in problems)


def test_a_windows_style_cockpit_command_may_carry_chinese_arguments() -> None:
    assert shell_fragility_problem(r".venv\Scripts\python.exe -B main.py doc check --说明 中文", windows=True) == ""


# Trae card A (SW-2026-008 / CHG-DOCU-2026-091): PowerShell one-liners pasted as --check commands.  In PowerShell the first
# one reported success although ``$p`` was empty (the unquoted Chinese path was mangled), i.e. a green that checked nothing.
_TRAE_CARD_A_FALSE_GREEN = (
    "$p=01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/README.md; "
    "$l=Get-Content -Path $p -Encoding UTF8; "
    "$n=($l | Select-String -Pattern ^##.*本文适用范围与读者 | Select-Object -Last 1).LineNumber; "
    "if(($l[$n] -match 适用范围) -and ($l[$n] -match 读者)){exit 0}else{exit 1}"
)
_TRAE_CARD_A_QUOTEPATH = (
    "$d=@(git diff --name-only); if(($d.Count -eq 1) -and ($d[0] -like *SW-2026-008*/README.md)){exit 0}else{exit 1}"
)


@pytest.mark.parametrize("command", [_TRAE_CARD_A_FALSE_GREEN, _TRAE_CARD_A_QUOTEPATH])
@pytest.mark.parametrize("windows", [False, True])
def test_the_trae_false_green_one_liners_cannot_become_acceptance_commands(command: str, windows: bool) -> None:
    """Either the parser (``;`` is a shell operator) or the fragility rule ($, Chinese, wildcards) refuses each of them."""
    reason = command_problem(command, windows=windows) or shell_fragility_problem(command, windows=windows)
    assert reason, "a PowerShell one-liner was accepted as an acceptance command"
    checklist = PlanChecklist(
        original_request="x",
        safety_circuit="否",
        acceptance_checks=(AcceptanceCheck(command=command, expected_exit_code=0),),
        rollback="git revert",
    )
    problems = plan_checklist_problems(checklist, declared=(), scope=("a/",), risks=("r",), acceptance_criteria=("一",))
    assert any(item.startswith("⑤第 1 条验收命令不能照原文执行") for item in problems), problems


@pytest.mark.parametrize(
    "command",
    [
        "$p=a/b.md",  # leading variable assignment
        "Get-Content -Path $p",  # a PowerShell variable as an argument
        "python -B -c \"exit(0 if '$p' else 1)\"",  # a variable inside the quotes is still expanded by PowerShell
    ],
)
def test_each_ingredient_of_the_false_green_is_refused_on_its_own(command: str) -> None:
    reason = command_problem(command, windows=True) or shell_fragility_problem(command, windows=True)
    assert reason


@pytest.mark.parametrize("extra", ["$x", "`", "*.py", "?"])
@pytest.mark.parametrize("windows", [False, True])
def test_a_chinese_path_does_not_excuse_a_variable_a_backtick_or_a_wildcard_in_the_same_command(extra: str, windows: bool) -> None:
    """The path exemption is only for the path argument itself (coordinator ruling for PR 490)."""

    def refused(command: str) -> str:
        # An unquoted backtick is already a parse error (command substitution); the rest is the fragility rule.
        return command_problem(command, windows=windows) or shell_fragility_problem(command, windows=windows)

    assert refused("python -B 项目甲/检查.py") == ""
    assert refused(f"python -B 项目甲/检查.py {extra}") != ""
    assert refused(f"python -B 项目甲/检查{extra}.py") != ""
