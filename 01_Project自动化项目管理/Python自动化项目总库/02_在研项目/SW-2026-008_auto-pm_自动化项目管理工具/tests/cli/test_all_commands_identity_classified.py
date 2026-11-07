"""TD-SW008-214: no command-line command can appear without a decision about the runtime-identity guard.

Every command group is either in ``CLASSIFIED_GROUPS`` (it has its own test, ``tests/cli/test_*_runtime_identity.py``, that
lists every command as guarded, warn-only or read-only) or its commands are walked here.  This test applies one rule to
every command outside ``CLASSIFIED_GROUPS``:

* its callback calls ``require_runtime_identity*`` or ``warn_runtime_identity`` - guarded, nothing to record; or
* it is listed in ``READ_ONLY`` below: a group with no write path at all, decided once and written down; or
* it is listed in ``UNDECIDED``, the frozen list of commands nobody has decided yet.  The debt is closed, so it is empty.

A new command that is none of these fails here; a listed command that has since been guarded must be removed from its list,
so the lists can only shrink.  Entering a command in ``READ_ONLY`` or ``UNDECIDED`` is a decision for the person who approves
the card, not a way past the test: any change to this file has to be listed in the PR's 可改范围 (the pr-gate scope check fails
without it), so the reviewer sees it.  It is not on the audit script's PROTECTED_PATTERNS list; the reviewer reads the diff of this file.
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
        "clean",
        "constraint",
        "continuity",
        "decision",
        "delivery",
        "doc",
        "dogfood",
        "git-hook",
        "handoff",
        "implementation-card",
        "ledger",
        "plc",
        "pm",
        "pm-session",
        "pr",
        "project",
        "prototype",
        "python",
        "spec",
        "template",
        "vartable",
        "workflow",
        "worktree",
    }
)

# TD-SW008-214 is closed: no command is left undecided.  The dict stays so that the ratchet below keeps its shape; a name may
# only be added here with the approval of the card that does it (a change to this file must be listed in the PR's 可改范围).
UNDECIDED: dict[str, tuple[str, ...]] = {}

# Commands in groups that have no write path at all, decided as read-only on 2026-11-01 (user: "按推荐").  They need no
# identity guard; a command that later gets one must leave this list, and one that starts to write must get a guard.
READ_ONLY: dict[str, tuple[str, ...]] = {
    "context": ("resolve",),  # prints the identity card; it is the check itself
    "doctor": ("",),  # environment diagnosis, prints only
    "gui": ("",),  # opens the cockpit window; every write inside goes through the guarded services
    "role": ("check", "list"),  # reads the role pack registry
}

# Commands that DO write, but only to GitHub (not the ledger, not any project file), and that must run in a cloud clone that has no
# runtime identity (D-39: ``claim`` pushes ``claims/<card>`` branches).  Not read-only: the write is real and stays listed here, by
# name, so a new subcommand of such a group does not slip in unclassified.  Their own test pins that nothing else is touched.
REMOTE_ONLY_NO_LEDGER: dict[str, tuple[str, ...]] = {
    "claim": ("list", "open", "release", "renew", "reclaim"),
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


def _read_only() -> set[str]:
    return {f"{group} {sub}".strip() for group, subs in READ_ONLY.items() for sub in subs}


def _remote_only() -> set[str]:
    return {f"{group} {sub}".strip() for group, subs in REMOTE_ONLY_NO_LEDGER.items() for sub in subs}


def _unknown() -> list[str]:
    return sorted(
        name
        for name, command in _outside_classified_groups().items()
        if not _guarded(command) and name not in _undecided() and name not in _read_only()
        and name not in _remote_only()
    )


def test_every_command_outside_the_classified_groups_is_guarded_or_listed() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    unknown = _unknown()
    assert not unknown, (
        "这些命令既没有运行身份校验，也不在 READ_ONLY 里："
        + "、".join(unknown)
        + "。写账、写项目文件的命令加 require_runtime_identity*；只读的在 READ_ONLY 登记，并在 PR 里写明理由（TD-SW008-214）。"
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
    for label, names in (
        ("UNDECIDED", _undecided()),
        ("READ_ONLY", _read_only()),
        ("REMOTE_ONLY_NO_LEDGER", _remote_only()),
    ):
        gone = sorted(name for name in names if name not in present)
        assert not gone, f"{label} 里有已不存在的命令（请删掉）：" + "、".join(gone)
        now_guarded = sorted(name for name in names if _guarded(present[name]))
        assert not now_guarded, f"这些命令已经有运行身份校验，请从 {label} 里删掉：" + "、".join(
            now_guarded
        )


def test_a_classified_group_is_not_also_in_the_undecided_list() -> None:
    assert not CLASSIFIED_GROUPS & (set(UNDECIDED) | set(READ_ONLY) | set(REMOTE_ONLY_NO_LEDGER))
    assert not set(READ_ONLY) & set(REMOTE_ONLY_NO_LEDGER), "claim 会写远程，不能归到 READ_ONLY"


def test_every_top_level_group_is_either_classified_or_covered_here() -> None:
    top = {name.split()[0] for name, _ in _walk(cli)}
    assert top >= CLASSIFIED_GROUPS, "CLASSIFIED_GROUPS 里有已不存在的命令组：" + "、".join(
        sorted(CLASSIFIED_GROUPS - top)
    )
