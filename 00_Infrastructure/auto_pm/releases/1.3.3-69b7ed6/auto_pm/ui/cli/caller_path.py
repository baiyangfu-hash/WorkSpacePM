"""Command-line path arguments that mean "relative to where the caller typed the command" (TD-SW008-232).

The launcher starts the release with its own directory as the working directory, so a plain ``click.Path`` resolves ``backups/x.db`` against the release
folder.  The launcher therefore exports the caller's directory in ``AUTO_PM_CALLER_CWD``; ``CallerPath`` anchors a relative value there *before* click
checks that it exists.  Without the variable (a direct ``python main.py`` run) nothing changes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import click

CALLER_CWD_ENV = "AUTO_PM_CALLER_CWD"


def anchor_to_caller(value: str | os.PathLike[str]) -> str | os.PathLike[str]:
    """Return ``value`` joined to the caller's directory when it is relative and the launcher told us where that is."""

    caller = os.environ.get(CALLER_CWD_ENV)
    if not caller or os.path.isabs(value):
        return value
    joined = os.path.join(caller, os.fspath(value))
    return Path(joined) if isinstance(value, os.PathLike) else joined


def caller_cwd_default() -> str | None:
    """The caller's own directory when the launcher exported it, else ``None`` (the callee then falls back to the process directory as before).

    For options whose documented default is "the current directory" and whose value is handed to code that would otherwise read ``Path.cwd()``,
    i.e. the release folder when started through the launcher.  Use as ``default=caller_cwd_default`` (click calls it at parse time).
    """

    return os.environ.get(CALLER_CWD_ENV) or None


class CallerPath(click.Path):
    """``click.Path`` that resolves a relative argument against the caller's directory."""

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> Any:
        if isinstance(value, (str, os.PathLike)):
            value = anchor_to_caller(value)
        return super().convert(value, param, ctx)
