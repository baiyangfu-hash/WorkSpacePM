"""TD-SW008-214: no command-line command can appear without a decision about the runtime-identity guard.

Twelve command groups (``pm``, ``change``, ``continuity``, ``decision``, ``implementation-card``, ``ledger``, ``plc``,
``python``, ``project``, ``doc``, ``prototype``, ``template``) have their own test that lists every command as guarded or not.
The other groups had nothing: a new write command there reached the ledger or a project folder with no identity check and no
test noticing.  This test walks the whole command tree and applies one rule to every command outside those twelve groups:

* its callback calls ``require_runtime_identity*`` or ``warn_runtime_identity`` - guarded, nothing to record; or
* it is listed in ``UNDECIDED`` below, the frozen list of today's commands that the open debt TD-SW008-214 has not decided yet.

A new command that is neither fails here; a listed command that has since been guarded must be removed from the list, so
the list can only shrink.  Entering a command in ``UNDECIDED`` is a decision for the person who approves the card, not a
way past the test: this file is a protected test path and shows up in the PR scope check.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Iterator

import click
import pytest

from auto_pm.ui.cli.__main__ import cli
from auto_pm.ui.cli.runtime_identity_guard import require_runtime_identity

# Groups whose commands are all classified by their own test (tests/cli/test_*_runtime_identity.py).
CLASSIFIED_GROUPS = frozenset(
    {
        "change",
        "continuity",
        "decision",
        "doc",
        "implementation-card",
        "ledger",
        "plc",
        "pm",
        "project",
        "prototype",
        "python",
        "template",
    }
)

# Today's commands in the other groups with no identity guard and no decision yet (TD-SW008-214: allow list still open).
UNDECIDED: dict[str, tuple[str, ...]] = {
    "clean": ("",),
    "constraint": (
        "check",
        "guard",
        "heal",
        "list",
        "verify",
    ),
    "context": ("resolve",),
    "delivery": (
        "archive clean",
        "archive list",
        "build",
        "package",
        "status",
    ),
    "doctor": ("",),
    "dogfood": (
        "inspect",
        "prepare",
        "review",
    ),
    "git-hook": (
        "commit-msg",
        "install",
        "pre-commit",
        "preflight",
        "release-gate",
    ),
    "gui": ("",),
    "handoff": (
        "claim",
        "close",
        "create",
        "fail",
        "failures",
        "heartbeat",
        "list",
        "preflight",
        "queue",
        "requeue",
        "result-submit",
        "saga compensate",
        "saga resume",
        "saga status",
        "show",
        "start",
        "timeout",
    ),
    "pm-session": (
        "archive",
        "check",
        "view",
    ),
    "pr": (
        "open",
        "ready",
    ),
    "role": (
        "check",
        "list",
    ),
    "spec": (
        "check",
        "frontmatter",
        "index",
        "lint",
        "report",
        "sync",
    ),
    "vartable": (
        "batch-parse",
        "convert",
        "detect-encoding",
        "detect-format",
        "list-encodings",
        "list-formats",
        "parse",
    ),
    "workflow": (
        "confirm-start",
        "context",
        "history",
        "list",
        "plan",
        "resume",
        "run",
        "status",
    ),
    "worktree": (
        "close",
        "list",
        "open",
        "sweep",
    ),
}

GUARD_CALL = re.compile(r"\b(?:require_runtime_identity\w*|warn_runtime_identity)\b")


def _walk(group: click.Group, prefix: str = "") -> Iterator[tuple[str, click.Command]]:
    for name, command in sorted(group.commands.items()):
        if isinstance(command, click.Group):
            yield from _walk(command, f"{prefix}{name} ")
        else:
            yield f"{prefix}{name}", command


def _guarded(command: click.Command) -> bool:
    return command.callback is not None and bool(
        GUARD_CALL.search(inspect.getsource(command.callback))
    )


def _outside_classified_groups() -> dict[str, click.Command]:
    return {
        name: command for name, command in _walk(cli) if name.split()[0] not in CLASSIFIED_GROUPS
    }


def _undecided() -> set[str]:
    return {f"{group} {sub}".strip() for group, subs in UNDECIDED.items() for sub in subs}


def _unknown() -> list[str]:
    return sorted(
        name
        for name, command in _outside_classified_groups().items()
        if not _guarded(command) and name not in _undecided()
    )


def test_every_command_outside_the_classified_groups_is_guarded_or_listed() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    unknown = _unknown()
    assert not unknown, (
        "这些命令既没有运行身份校验，也不在 UNDECIDED 里："
        + "、".join(unknown)
        + "。写账、写项目文件的命令加 require_runtime_identity*；只读的在 UNDECIDED 登记，并在 PR 里写明理由（TD-SW008-214）。"
    )


def test_a_new_unguarded_command_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    @click.group("zz-new")
    def new_group() -> None: ...

    @new_group.command("writes")
    def writes() -> None: ...

    @new_group.command("guarded")
    def guarded() -> None:
        require_runtime_identity(click.get_current_context(), "P-1")

    monkeypatch.setitem(cli.commands, "zz-new", new_group)
    assert _unknown() == ["zz-new writes"]


def test_the_undecided_list_only_names_commands_that_exist_and_are_still_unguarded() -> None:
    """The list is a ratchet: a command that got its guard (or was removed) must leave it."""

    present = _outside_classified_groups()
    gone = sorted(name for name in _undecided() if name not in present)
    assert not gone, "UNDECIDED 里有已不存在的命令（请删掉）：" + "、".join(gone)
    now_guarded = sorted(name for name in _undecided() if _guarded(present[name]))
    assert not now_guarded, "这些命令已经有运行身份校验，请从 UNDECIDED 里删掉：" + "、".join(
        now_guarded
    )


def test_a_classified_group_is_not_also_in_the_undecided_list() -> None:
    assert not CLASSIFIED_GROUPS & set(UNDECIDED)


def test_every_top_level_group_is_either_classified_or_covered_here() -> None:
    top = {name.split()[0] for name, _ in _walk(cli)}
    assert top >= CLASSIFIED_GROUPS, "CLASSIFIED_GROUPS 里有已不存在的命令组：" + "、".join(
        sorted(CLASSIFIED_GROUPS - top)
    )
