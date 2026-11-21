"""Subprocess adapter for detached gate executors."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_command(root: Path, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=root, timeout=timeout, capture_output=True, encoding="utf-8",
        errors="replace",  # lenient-decode: gh, Git and Windows scheduler may use the host code page
        check=False,
    )
