"""Arm the calling command for the memory gate (D-168): the thin application-layer door the CLI uses, so ``ui`` never imports ``infrastructure``."""

from __future__ import annotations

from auto_pm.infrastructure import memory_preflight


def arm_for_heavy_job(label: str) -> None:
    """Write this process's arm record (``memory_preflight.arm``); never raises and never changes what the command does."""

    memory_preflight.arm(label)
