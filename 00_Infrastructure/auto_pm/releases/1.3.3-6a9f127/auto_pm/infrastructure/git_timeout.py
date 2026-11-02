"""One bounded, diagnosable time limit for every Git subprocess the cockpit starts."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

GIT_TIMEOUT_ENV = "AUTO_PM_GIT_TIMEOUT_SECONDS"
GIT_TIMEOUT_MIN = 5.0
GIT_TIMEOUT_MAX = 600.0


def resolve_git_timeout(
    default: float, *, environ: Mapping[str, str] | None = None
) -> float:
    """Return ``default`` unless the override is set; an unusable override raises ValueError."""
    raw = (os.environ if environ is None else environ).get(GIT_TIMEOUT_ENV)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        value = float("nan")
    if not GIT_TIMEOUT_MIN <= value <= GIT_TIMEOUT_MAX:
        raise ValueError(
            f"{GIT_TIMEOUT_ENV}={raw!r} 不可用：必须是 "
            f"{GIT_TIMEOUT_MIN:g}~{GIT_TIMEOUT_MAX:g} 秒之间的数字"
        )
    return value


def _run_bounded(
    command: Sequence[str],
    *,
    default_timeout: float,
    error_cls: type[Exception],
    where: Path | str,
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    """Run Git with a bounded limit; a hang or bad override fails closed as ``error_cls``.

    The timeout receipt names the command, directory, limit and the time actually waited,
    so a long tail is visible instead of being re-run until it turns green.
    KeyboardInterrupt and OSError propagate untouched.
    """
    try:
        limit = resolve_git_timeout(default_timeout)
    except ValueError as error:
        raise error_cls(str(error)) from error
    started = time.monotonic()
    try:
        return subprocess.run(list(command), timeout=limit, **kwargs)
    except subprocess.TimeoutExpired as error:
        verb = next((part for part in command[1:] if not part.startswith("-") and part != str(where)), "")
        raise error_cls(
            f"Git 命令超时回执：git {verb} 在 {where} 超过 {limit:g} 秒时限"
            f"（实际等待 {time.monotonic() - started:.1f} 秒）被终止，无法证明状态；"
            f"可用 {GIT_TIMEOUT_ENV} 在 {GIT_TIMEOUT_MIN:g}~{GIT_TIMEOUT_MAX:g} 秒内调整后整体重做"
        ) from error


def run_git_bounded(
    command: Sequence[str],
    *,
    default_timeout: float,
    error_cls: type[Exception],
    where: Path | str,
    **kwargs: Any,
) -> subprocess.CompletedProcess[bytes]:
    """Bounded Git run returning bytes output (see ``_run_bounded``)."""
    return cast(
        "subprocess.CompletedProcess[bytes]",
        _run_bounded(command, default_timeout=default_timeout, error_cls=error_cls, where=where, **kwargs),
    )


def run_git_bounded_text(
    command: Sequence[str],
    *,
    default_timeout: float,
    error_cls: type[Exception],
    where: Path | str,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Bounded Git run returning UTF-8 text output (``errors="replace"``, DEV-ENC-001)."""
    kwargs.update(text=True, encoding="utf-8", errors="replace")
    return cast(
        "subprocess.CompletedProcess[str]",
        _run_bounded(command, default_timeout=default_timeout, error_cls=error_cls, where=where, **kwargs),
    )
