"""Store flavour of ``GuardRefusal``: a ``ContinuityStoreError`` that also says which registered guard refused."""

from __future__ import annotations

from auto_pm.contracts.guard_refusal import GuardRefusal
from auto_pm.infrastructure.continuity_store import ContinuityStoreError


class GuardStoreRefusal(ContinuityStoreError, GuardRefusal):  # noqa: N818
    """Raise this instead of a bare ``ContinuityStoreError`` when a registered guard refuses."""

    def __init__(self, guard_id: str, message: str) -> None:
        ContinuityStoreError.__init__(self, message)
        if not guard_id:
            raise ValueError("GuardRefusal 必须带 guard_id")
        self.guard_id = guard_id
