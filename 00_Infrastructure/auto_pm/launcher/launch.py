#!/usr/bin/env python3
"""Dual-slot deployment launcher (NG-WP-12/13, fail-closed).

Resolution stage shared with the workspace-root entry: validates the container
layout, resolves the active pointer (approved previous as sole fallback) via
``bootstrap.py``, and enforces ``releases/`` containment plus manifest
registration.  Real release execution is wired by a later work package; until
then the launcher exits non-zero before running any release code, so this
script can never silently start unverified content.

Exit codes (from bootstrap.py):
    0  active release resolved and manifest-listed (resolution only)
    2  container layout invalid
    3  pointer uninitialized or unreadable (both slots exhausted)
    4  active release invalid, escaping releases/ or not manifest-listed
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bootstrap import BootstrapError, resolve_with_fallback


def main() -> int:
    container = Path(__file__).resolve().parent.parent
    try:
        release_dir, slot = resolve_with_fallback(container)
    except BootstrapError as exc:
        print(f"launcher: {exc}", file=sys.stderr)
        return exc.exit_code
    print(f"launcher: active release resolved via {slot}: {release_dir}")
    print("launcher: skeleton mode - release execution is not wired yet (NG-WP-13/15)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
