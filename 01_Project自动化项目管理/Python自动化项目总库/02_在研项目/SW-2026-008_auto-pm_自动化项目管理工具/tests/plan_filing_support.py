"""An explicit classification (TD-SW008-070) for tests that are not about how a plan is classified.

A new plan must be classified; nothing is filed under a default any more. Tests that only need a plan to exist pass
this one: kind BUG files as nature DEF, scope MODULE, urgency normal, domain SCPT - the filing the old default produced.
"""

from __future__ import annotations

from auto_pm.contracts.intake import IntakeClassification, IntakeKind

LEGACY_EQUIVALENT_FILING = IntakeClassification(kind=IntakeKind.BUG, domain="SCPT")
