"""Arm the calling command for the memory gate (D-168): the thin application-layer door the CLI uses, so ``ui`` never imports ``infrastructure``."""

from __future__ import annotations

import os
from pathlib import Path

from auto_pm.infrastructure import memory_preflight


def arm_for_heavy_job(label: str) -> None:
    """Write this process's arm record (``memory_preflight.arm``); never raises and never changes what the command does."""

    memory_preflight.arm(label)


def disarm_this_process(start: Path | None = None) -> None:
    """Take this process out of the memory gate's reach again by removing its own arm record; never raises, and does nothing when it is not armed.

    An armed process tree is exactly what the gate may freeze.  A release deploy wants that while it builds and checks (heavy, restartable) but not
    from the moment it starts moving the release pointers until it exits: a freeze between "new release is live" and "new release has passed its
    self-checks" would leave an unverified release serving every conversation (D-174).  The record lives at ``<arm folder>/<pid>.json``, the
    same place ``memory_preflight.arm`` writes it.
    """

    folder = memory_preflight.arm_dir(start)
    if folder is not None:
        memory_preflight.disarm(folder / f"{os.getpid()}.json")
