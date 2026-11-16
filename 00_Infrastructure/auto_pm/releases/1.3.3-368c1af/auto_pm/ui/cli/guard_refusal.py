"""Click flavour of ``GuardRefusal``: prints exactly like the ``ClickException`` it replaces (same text, same exit code 1)."""

from __future__ import annotations

import click

from auto_pm.contracts.guard_refusal import GuardRefusal


class GuardClickRefusal(click.ClickException, GuardRefusal):
    """A ``ClickException`` that also says which registered guard refused."""

    def __init__(self, guard_id: str, message: str) -> None:
        click.ClickException.__init__(self, message)
        if not guard_id:
            raise ValueError("GuardRefusal 必须带 guard_id")
        self.guard_id = guard_id
