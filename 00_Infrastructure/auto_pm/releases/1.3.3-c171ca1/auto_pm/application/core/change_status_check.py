"""auto_pm.application.core.change_status_check - the read-only check of change-order status edits for the UI layer.

``doctor`` (UI layer) may not import the infrastructure layer; this thin wrapper is the way in.
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.infrastructure.change_status_guard import pending_status_problems


def pending_change_status_problems(root: str) -> list[str] | None:
    """Working-tree change orders whose new approved-or-later status has no transition record; None = Git could not answer."""

    return pending_status_problems(Path(root))
