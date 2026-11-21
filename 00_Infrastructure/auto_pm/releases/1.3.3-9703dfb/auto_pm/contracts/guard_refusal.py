"""Typed refusal that names the guard behind it (CHG-SCPT-2026-476, interlock matrix P0).

Every refusal a cockpit guard raises carries a ``guard_id`` that is registered in ``interlock_matrix.GUARDS``.  Text alone
cannot be audited: two guards may print the same sentence and one guard may be edited to refuse for a second reason without
the sentence changing.  The id lets the exit-drill test compare *which guard actually fired* with the set the matrix
declares for that step.

``GuardRefusal`` is a mixin: the concrete classes below (and in ``ui.cli.guard_refusal`` / ``infrastructure.guard_refusal``)
also derive from the exception the call site used to raise, so every ``except`` clause and every exit code stays as it was.
"""

from __future__ import annotations


class GuardRefusal(Exception):  # noqa: N818 - named for what it is (a refusal), not an error
    """Marker base: a refusal produced by the guard registered as ``guard_id``.

    It has no constructor of its own on purpose: the concrete classes combine it with ``ClickException`` or
    ``ContinuityStoreError``, whose constructors call ``super().__init__(message)``; a second constructor here would break that chain.
    """

    guard_id: str = ""
