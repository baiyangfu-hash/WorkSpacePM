import subprocess
from pathlib import Path

import pytest

from auto_pm.contracts.pm_facade import PlanningDraft, PmIntent
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


def test_planning_spec_bindings_are_readable_and_fail_closed(tmp_path: Path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    store = ContinuityStore(tmp_path, tmp_path / ".auto-pm" / "continuity.db")
    store.initialize("2026-09-28T00:00:00+00:00", "test")
    draft = PlanningDraft.from_intent(
        PmIntent(
            request_id="REQ-U03A-001",
            subject_project_id="SW-2026-008",
            objective="Start only the approved execution.",
            acceptance_criteria=("Real RUN_STARTED evidence is required.",),
        )
    )
    store.create_planning_draft(draft)

    with pytest.raises(ContinuityStoreError, match="尚未绑定"):
        store.get_planning_draft_specs(draft.request_id)

    expected = (("DEV-300", "specs/dev-300.md", "V1"),)
    store.bind_planning_draft_specs(draft.request_id, expected)

    assert store.get_planning_draft_specs(draft.request_id) == expected
