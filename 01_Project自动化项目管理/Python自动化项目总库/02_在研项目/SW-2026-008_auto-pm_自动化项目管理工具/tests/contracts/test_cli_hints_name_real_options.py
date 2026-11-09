"""D-189: a message that tells the user to run ``main.py <command> --option`` must name an option that command really has.

``release_deploy`` once said "可用 --resume 续" while ``release deploy`` has no such option; the user would copy a command that fails.
The check reads every string literal in ``auto_pm`` and, for each ``main.py <command path> ... --option`` hint, resolves the command through the
real click tree and asks it.  Hints are skipped when the command path cannot be resolved (prose such as ``main.py 的``).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import click

from auto_pm.ui.cli.__main__ import cli

PACKAGE = Path(__file__).resolve().parents[2] / "auto_pm"
HINT = re.compile(r"main\.py\s+((?:[a-z][a-z0-9-]*\s+|<[^>]*>\s+|[A-Z_]+\s+)*?)(--[a-z][a-z0-9-]*)")
OPTION = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)")


def _resolve(words: list[str]) -> click.Command | None:
    command: click.Command = cli
    context = click.Context(cli)
    for index, word in enumerate(words):
        if not isinstance(command, click.Group):
            break
        child = command.get_command(context, word)
        if child is None:
            return None if index == 0 else command
        command = child
    return command


def _options(command: click.Command) -> set[str]:
    return {opt for param in command.params for opt in (*param.opts, *param.secondary_opts)} | {
        "--help"
    }


def _strings(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _hint_errors(text: str, line: int, where: str) -> list[str]:
    errors: list[str] = []
    for match in HINT.finditer(text):
        words = [
            word
            for word in match.group(1).split()
            if not word.startswith("<") and not word.isupper()
        ]
        command = _resolve(words)
        if command is None:
            continue
        tail = re.split(r"main\.py|&&|;|`", text[match.start(2) :].split("\n")[0])[0]
        known = _options(command)
        errors += [
            f"{where}:{line} `main.py {' '.join(words)}` has no option {option}"
            for option in OPTION.findall(tail)
            if option not in known
        ]
    return errors


def test_every_main_py_hint_in_the_package_names_options_the_command_has() -> None:
    errors: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for line, text in _strings(path):
            errors += _hint_errors(text, line, str(path.relative_to(PACKAGE.parent)))
    assert errors == []


def test_the_checker_catches_an_option_the_command_does_not_have() -> None:
    assert _hint_errors("run `main.py pm park --pid X --as me`", 1, "x") == [
        "x:1 `main.py pm park` has no option --pid",
        "x:1 `main.py pm park` has no option --as",
    ]
    assert _hint_errors("run `main.py pm park --mission-id M --reason r`", 1, "x") == []


def test_the_deploy_messages_only_name_options_that_release_deploy_has() -> None:
    """The ``--resume`` text had no ``main.py`` in front, so it is checked against the command's options directly."""

    deploy = _resolve(["release", "deploy"])
    assert deploy is not None
    unknown = [
        f"{line}: {option}"
        for line, text in _strings(PACKAGE / "application" / "core" / "release_deploy.py")
        for option in OPTION.findall(text)
        if option not in _options(deploy)
    ]
    assert unknown == []
