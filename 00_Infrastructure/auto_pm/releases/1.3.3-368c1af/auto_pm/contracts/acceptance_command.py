"""Acceptance command text -> an argument list, without ever handing the text to a shell.

An acceptance command is typed once in ``pm plan --check "命令 => 退出码"`` and is later *executed* by ``pm verify``.
Between the two, no shell may re-interpret it: a Chinese PowerShell literal is mangled by the console code page,
``&&`` or ``|`` silently becomes an extra argument, and a quoted path changes meaning on the way.  So the text is split
here into an argv list (the same rules the platform's own command line uses) and the plan stage refuses what cannot
be run that way.  Pure functions, no IO, so the plan checklist (contracts layer) and the runner (application layer)
share one parser.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import PurePath

__all__ = [
    "GIT_QUOTEPATH_OPTION",
    "AcceptanceCommandError",
    "WORKTREE_PLACEHOLDER",
    "ParsedCommand",
    "command_hints",
    "command_problem",
    "parse_command",
    "shell_fragility_problem",
    "with_git_quotepath",
]

#: Git prints non-ASCII path names as octal escapes ("\344\270\255") unless this is off.
GIT_QUOTEPATH_OPTION = ("-c", "core.quotePath=false")

_SHELL_CHARACTERS = frozenset("|&;<>")
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


class AcceptanceCommandError(ValueError):
    """The command text cannot be turned into one plain command (message is for the user)."""


@dataclass(frozen=True)
class _Token:
    text: str
    quoted: bool


@dataclass(frozen=True)
class ParsedCommand:
    """The argument list, and whether any argument was written with quotes (for the shell-syntax checks)."""

    argv: tuple[str, ...]
    quoted: tuple[bool, ...]


def _split_windows(text: str) -> list[_Token]:
    """Microsoft C runtime rules: backslashes are literal unless they precede a double quote."""

    tokens: list[_Token] = []
    current: list[str] = []
    in_token = False
    quoted = False
    in_quotes = False
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\\":
            run = 0
            while index < length and text[index] == "\\":
                run += 1
                index += 1
            if index < length and text[index] == '"':
                current.append("\\" * (run // 2))
                if run % 2:
                    current.append('"')
                    index += 1
                # An even run leaves the quote to be handled as a delimiter on the next turn.
            else:
                current.append("\\" * run)
            in_token = True
            continue
        if char == '"':
            in_quotes = not in_quotes
            quoted = True
            in_token = True
        elif char in " \t" and not in_quotes:
            if in_token:
                tokens.append(_Token("".join(current), quoted))
                current, in_token, quoted = [], False, False
        else:
            current.append(char)
            in_token = True
        index += 1
    if in_quotes:
        raise AcceptanceCommandError("引号没有配对")
    if in_token:
        tokens.append(_Token("".join(current), quoted))
    return tokens


def _split_posix(text: str) -> list[_Token]:
    """POSIX shell word rules (quotes and backslash escapes), without any expansion."""

    tokens: list[_Token] = []
    current: list[str] = []
    in_token = False
    quoted = False
    quote = ""
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if quote == "'":
            if char == "'":
                quote = ""
            else:
                current.append(char)
        elif quote == '"':
            if char == '"':
                quote = ""
            elif char == "\\" and index + 1 < length and text[index + 1] in '"\\$`':
                index += 1
                current.append(text[index])
            else:
                current.append(char)
        elif char == "\\":
            if index + 1 >= length:
                raise AcceptanceCommandError("命令以反斜杠结尾")
            index += 1
            current.append(text[index])
            in_token = True
        elif char in "'\"":
            quote = char
            quoted = True
            in_token = True
        elif char in " \t":
            if in_token:
                tokens.append(_Token("".join(current), quoted))
                current, in_token, quoted = [], False, False
        else:
            current.append(char)
            in_token = True
        index += 1
    if quote:
        raise AcceptanceCommandError("引号没有配对")
    if in_token:
        tokens.append(_Token("".join(current), quoted))
    return tokens


def parse_command(text: str, *, windows: bool | None = None) -> ParsedCommand:
    """Split ``text`` into the argument list the verifier will execute; raise if it needs a shell.

    ``windows`` selects the quoting rules; the default follows the running platform.  Refused (each with a reason the
    user can act on): an empty command, a line break, shell operators (``&& || | ; > <``, ``&``, redirections), command
    substitution, a ``#`` comment, and a leading ``NAME=value`` environment assignment.  These do *not* work without a
    shell, and running them as plain arguments would pass a "green" that never checked anything.
    """

    if "\n" in text or "\r" in text:
        raise AcceptanceCommandError("验收命令不能含换行：一条命令写成一行")
    use_windows = (os.name == "nt") if windows is None else windows
    tokens = _split_windows(text) if use_windows else _split_posix(text)
    if not tokens:
        raise AcceptanceCommandError("验收命令是空的")
    for token in tokens:
        if token.quoted:
            continue
        if token.text.startswith("#"):
            raise AcceptanceCommandError("命令里不能带 # 注释：注释写到验收标准的文字里")
        if _SHELL_CHARACTERS & set(token.text):
            raise AcceptanceCommandError(
                f"命令里有 shell 符号（{token.text}）：这里不经过 shell，& | ; > < 不会生效；"
                "要组合多个动作，请写成一个脚本或 python -c，再各用一条 --check"
            )
        if "$(" in token.text or "`" in token.text:
            raise AcceptanceCommandError(f"命令里有命令替换（{token.text}）：这里不经过 shell，不会展开")
    first = tokens[0]
    if not first.quoted and _ENV_ASSIGNMENT.match(first.text):
        raise AcceptanceCommandError(
            f"命令不能以环境变量赋值开头（{first.text}）：这里不经过 shell；把赋值写进脚本或 python -c"
        )
    return ParsedCommand(
        argv=tuple(token.text for token in tokens),
        quoted=tuple(token.quoted for token in tokens),
    )


def command_problem(text: str, *, windows: bool | None = None) -> str:
    """The reason ``text`` cannot be executed as one plain command, or an empty string when it can."""

    try:
        parse_command(text, windows=windows)
    except AcceptanceCommandError as error:
        return str(error)
    return ""


def _is_git(executable: str) -> bool:
    return PurePath(executable.replace("\\", "/")).name.lower() in {"git", "git.exe"}


def _is_python(executable: str) -> bool:
    return PurePath(executable.replace("\\", "/")).name.lower().startswith(("python", "py."))


def with_git_quotepath(argv: tuple[str, ...]) -> tuple[tuple[str, ...], bool]:
    """Insert ``-c core.quotePath=false`` right after ``git`` unless the caller already set core.quotePath.

    Returns the argument list to execute and whether it differs from the approved text (that is recorded in the execution log).
    """

    if not argv or not _is_git(argv[0]):
        return argv, False
    if any(item.startswith("core.quotePath=") or item.lower().startswith("core.quotepath=") for item in argv[1:]):
        return argv, False
    return (argv[0], *GIT_QUOTEPATH_OPTION, *argv[1:]), True


#: Spelled in an approved command; ``pm verify`` replaces it with the Run's worktree path before executing.
WORKTREE_PLACEHOLDER = "{worktree}"


def _targets_worktree(argv: tuple[str, ...]) -> bool:
    """Does a pytest or script command point at the Run's worktree (placeholder or an explicit ``git -C`` style path)?"""

    return any(WORKTREE_PLACEHOLDER in item or "worktrees" in item.replace("\\", "/") for item in argv[1:])


def _runs_pytest_or_script(argv: tuple[str, ...]) -> bool:
    """pytest, or a Python script other than ``main.py`` (cockpit commands are pointed at the worktree by environment)."""

    name = PurePath(argv[0].replace("\\", "/")).name.lower()
    if name.startswith(("pytest", "py.test")):
        return True
    if not _is_python(argv[0]):
        return False
    rest = argv[1:]
    if "-m" in rest and rest.index("-m") + 1 < len(rest) and rest[rest.index("-m") + 1] == "pytest":
        return True
    scripts = [item for item in rest if item.lower().endswith(".py")]
    return bool(scripts) and PurePath(scripts[0].replace("\\", "/")).name.lower() != "main.py"


def _non_ascii(value: str) -> bool:
    return any(ord(char) > 127 for char in value)


def command_hints(text: str, *, windows: bool | None = None) -> tuple[str, ...]:
    """Advice (not refusals) for a command that is legal but easy to get wrong; the refusals are in :func:`shell_fragility_problem`."""

    try:
        argv = parse_command(text, windows=windows).argv
    except AcceptanceCommandError:
        return ()
    hints: list[str] = []
    if _runs_pytest_or_script(argv) and not _targets_worktree(argv):
        hints.append(
            "pytest 或脚本命令在控制根里运行，默认检查的是控制根的文件，不是本任务工位里改的文件：路径写成 "
            f"{WORKTREE_PLACEHOLDER}/…（验证时换成工位路径），或让脚本自己读环境变量 AUTO_PM_RUN_WORKTREE；"
            "main.py 驾驶舱命令不用管，验证时已指向工位"
        )
    return tuple(hints)


_REWRITE_ADVICE = (
    "改写办法：把检查写进一个 Python 脚本文件，check 只写 `python -B 脚本路径`（脚本里用环境变量 AUTO_PM_RUN_WORKTREE 找工位、"
    "自己处理中文和通配）；不要把中文、通配、变量写在命令文本里"
)
_WILDCARD_CHARACTERS = "*?"
_EXPANSION_CHARACTERS = "$`"


#: pytest options whose next argument is a value (a name, an expression), not a test path.
_PYTEST_VALUE_OPTIONS = frozenset({"-k", "-m", "-p", "-o", "-c", "-W", "-n", "--deselect", "--ignore", "--ignore-glob", "--rootdir"})


def _python_target(argv: tuple[str, ...]) -> tuple[str, int]:
    """What ``python …`` runs: ("script", index of the script), ("pytest", -1) for ``-m pytest``, or ("", -1).

    The script is the first argument that is not an interpreter flag (``-B``, ``-u`` …); ``-c`` and other ``-m`` modules
    are not scripts.
    """

    if not _is_python(argv[0]):
        return "", -1
    rest = argv[1:]
    for position, item in enumerate(rest):
        if item == "-c":
            return "", -1
        if item == "-m":
            return ("pytest", -1) if position + 1 < len(rest) and rest[position + 1] == "pytest" else ("", -1)
        if item.startswith("-"):
            continue
        return ("script", position + 1) if item.lower().endswith(".py") else ("", -1)
    return "", -1


def _is_cockpit_command(argv: tuple[str, ...]) -> bool:
    """``python [flags] main.py …``: the first script argument is ``main.py`` (not any later argument named like it)."""

    kind, index = _python_target(argv)
    return kind == "script" and PurePath(argv[index].replace("\\", "/")).name.lower() == "main.py"


def _plain_path(value: str) -> bool:
    """A single path argument: a path separator in it, and nothing a console would split or treat as syntax."""

    return ("/" in value or "\\" in value) and not any(char.isspace() or char in "\"'" for char in value)


def _chinese_path_allowed(argv: tuple[str, ...], index: int) -> bool:
    """May ``argv[index]`` carry non-ASCII characters because it is the path a program must open?

    Only where a mangled path *fails*: the script of ``python script.py`` (no such file, exit 2) and a pytest test path
    (file not found, exit 4).  ``git`` and similar commands match paths as pathspecs, so a wrong path still exits 0
    (``git diff --exit-code -- 坏路径`` compares nothing and succeeds): no exemption there.
    """

    item = argv[index]
    if item.startswith("-") or not _plain_path(item):
        return False
    kind, script_index = _python_target(argv)
    if kind == "script":
        return index == script_index
    if kind == "pytest":
        return argv[index - 1] not in _PYTEST_VALUE_OPTIONS
    if PurePath(argv[0].replace("\\", "/")).name.lower().startswith(("pytest", "py.test")):
        return argv[index - 1] not in _PYTEST_VALUE_OPTIONS
    return False


def shell_fragility_problem(text: str, *, windows: bool | None = None) -> str:
    """Why ``text`` is dangerous to paste into a console, or an empty string.

    ``pm verify`` runs the approved text as an argument list, so these commands *can* execute; but the agent or the user
    also runs the same text by hand in PowerShell, which changes it on the way: Chinese text is mangled by the console
    code page, ``$name`` and backticks are expanded (an unset variable becomes an empty string and the command can exit 0
    having checked nothing), and a bare ``*`` or ``?`` is expanded by one side and not the other.  Refused at plan time:

    - ``$`` or a backtick anywhere in the command;
    - ``*`` / ``?`` in an argument (the code after ``python -c`` is exempt: it is Python source, not a file pattern);
    - non-ASCII characters, except (a) in the arguments after the script of ``python main.py …`` (user-facing text such as
      ``--说明``) and (b) in the path a program must open and fails on when it is wrong: the script of ``python x.py`` and a
      pytest test path (:func:`_chinese_path_allowed`).  Nowhere else: not in ``python -c`` code, not in ``git`` arguments.

    A command that cannot be parsed is not judged here (:func:`command_problem` reports it).
    """

    try:
        argv = parse_command(text, windows=windows).argv
    except AcceptanceCommandError:
        return ""
    cockpit = _is_cockpit_command(argv)
    script_index = _python_target(argv)[1]
    code_index = argv.index("-c") + 1 if _is_python(argv[0]) and "-c" in argv[1:] else -1
    for index, item in enumerate(argv):
        if any(char in item for char in _EXPANSION_CHARACTERS):
            return (
                f"命令里有 $ 或反引号（{item}）：PowerShell 会把它展开（没定义的变量变成空串，命令可能照样退出码 0 却什么都没检查）。"
                + _REWRITE_ADVICE
            )
        if index > 0 and index != code_index and any(char in item for char in _WILDCARD_CHARACTERS) and not item.startswith("-"):
            return (
                f"参数 {item} 含通配符 * 或 ?：这里不经过 shell，不会展开，PowerShell 里又可能被展开成别的东西，检查对象不确定。"
                "写具体路径，或" + _REWRITE_ADVICE
            )
        if _non_ascii(item):
            if cockpit and index > script_index:
                continue
            if _chinese_path_allowed(argv, index):
                continue
            return (
                f"命令里有中文等非 ASCII 字符（{item}）：经 PowerShell 和控制台代码页可能变形，而且这类命令路径写坏了也不会报错。"
                "中文只允许出现在 main.py 驾驶舱命令参数中，以及 python 脚本 / pytest 的路径参数里。" + _REWRITE_ADVICE
            )
    return ""
