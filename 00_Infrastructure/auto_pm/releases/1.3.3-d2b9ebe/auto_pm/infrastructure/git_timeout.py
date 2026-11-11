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


def no_window_flag(*, windows: bool | None = None) -> int:
    """Windows ``CREATE_NO_WINDOW``; 0 elsewhere. ``windows`` lets tests pick the system without touching ``os.name``."""
    on_windows = os.name == "nt" if windows is None else windows
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if on_windows else 0


def _hidden_window(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Return ``kwargs`` with the no-console-window flag added when Git's output is captured.

    A background ``git`` started from a GUI would otherwise flash a console window each time. The flag is added
    only when stdout is redirected: ``CREATE_NO_WINDOW`` gives the child its own hidden console, so an
    un-redirected ``git`` would lose its output instead of printing to the user's terminal.
    """
    flag = no_window_flag()
    redirected = bool(kwargs.get("capture_output")) or kwargs.get("stdout") is not None
    if not flag or not redirected:
        return kwargs
    return {**kwargs, "creationflags": int(kwargs.get("creationflags", 0)) | flag}


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
        return subprocess.run(list(command), timeout=limit, **_hidden_window(kwargs))
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
    """Bounded Git run returning UTF-8 text output (``errors="replace"``, DEV-ENC-001).

    Lenient: a byte that is not UTF-8 becomes U+FFFD.  Use it only where the answer is an exit code, an object id or a message shown
    to a person.  When the output carries PATHS that a scope, protected-path or identity comparison reads, use
    :func:`run_git_bounded_strict_text` — ``tests/infrastructure/test_git_text_callers.py`` lists every caller of this function with its reason.
    """
    kwargs.update(text=True, encoding="utf-8", errors="replace")  # lenient-decode: D-162 — callers are judged on exit codes and ASCII ids; a strict text-mode decode would lose the whole output on Windows (reader thread swallows the error), so any caller that compares text needs its own bytes path
    return cast(
        "subprocess.CompletedProcess[str]",
        _run_bounded(command, default_timeout=default_timeout, error_cls=error_cls, where=where, **kwargs),
    )


def run_git_bounded_strict_text(
    command: Sequence[str],
    *,
    default_timeout: float,
    error_cls: type[Exception],
    where: Path | str,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Bounded Git run whose text output must be valid UTF-8; otherwise ``error_cls`` is raised (fail closed).

    The output is captured as bytes and decoded HERE.  ``text=True`` would decode in a reader thread, and on Windows a decode error
    there is swallowed and the caller silently gets ``stdout=None``.  ``check=True`` keeps its meaning (``CalledProcessError`` carrying
    the decoded output) and a ``str`` ``input`` is encoded as UTF-8; ``text`` / ``encoding`` / ``errors`` are not accepted.
    """
    for forbidden in ("text", "encoding", "errors", "universal_newlines"):
        if forbidden in kwargs:
            raise TypeError(f"run_git_bounded_strict_text decodes by itself; do not pass {forbidden}=")
    check = bool(kwargs.pop("check", False))
    if isinstance(kwargs.get("input"), str):
        kwargs["input"] = kwargs["input"].encode("utf-8")
    raw = cast(
        "subprocess.CompletedProcess[bytes]",
        _run_bounded(command, default_timeout=default_timeout, error_cls=error_cls, where=where, check=False, **kwargs),
    )
    try:
        stdout = None if raw.stdout is None else raw.stdout.decode("utf-8")
        stderr = None if raw.stderr is None else raw.stderr.decode("utf-8")
    except UnicodeDecodeError as error:
        verb = next((part for part in command[1:] if not part.startswith("-") and part != str(where)), "")
        raise error_cls(f"git {verb} 的输出不是合法 UTF-8，无法可信地比对路径或名称: {error}") from error
    done: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(raw.args, raw.returncode, stdout, stderr)
    if check and raw.returncode != 0:
        raise subprocess.CalledProcessError(raw.returncode, raw.args, output=stdout, stderr=stderr)
    return done
