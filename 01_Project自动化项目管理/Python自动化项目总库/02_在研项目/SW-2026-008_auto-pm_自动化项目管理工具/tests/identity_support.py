"""Switch the runtime-identity guard off for the command modules a test file exercises (TD-SW008-214).

For tests about something other than the runtime identity, whose scratch workspaces have no registered project anchor.
The guard itself is covered by the ``test_*_runtime_identity.py`` files, which do not use this.
"""

from __future__ import annotations

import sys

import pytest


def guard_off(monkeypatch: pytest.MonkeyPatch, *modules: str) -> None:
    """Replace ``require_runtime_identity`` in the named ``auto_pm.ui.cli`` modules (whichever package alias is loaded)."""

    for package in ("auto_pm.ui.cli", "auto_pm.cli"):
        for module in modules:
            target = sys.modules.get(f"{package}.{module}")
            if target is not None and hasattr(target, "require_runtime_identity"):
                monkeypatch.setattr(target, "require_runtime_identity", lambda *_a, **_k: None)
