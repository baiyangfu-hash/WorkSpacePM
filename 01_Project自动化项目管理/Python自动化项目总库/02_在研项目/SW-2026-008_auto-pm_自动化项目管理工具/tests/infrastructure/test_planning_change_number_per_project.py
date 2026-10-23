"""规划草稿预留变更单号时，别的项目已占的同号不再挡路（M3-CHGUNIQ）

变更单按项目编号，可规划草稿的号码绑定表在全工作区唯一。D08 之后给 SW-2026-010 做
io-check 命令时，项目里下一个号 CHG-SCPT-2026-004 已被 SW-2026-009 的草稿占着，``pm plan``
报“候选 CHG 已绑定其他 PlanningDraft”。现在候选号被占时顺延到同一序列里第一个空号。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from auto_pm.contracts.pm_facade import PlanningDraft, PmIntent
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


def _store(tmp_path: Path) -> ContinuityStore:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    store = ContinuityStore(tmp_path, tmp_path / ".auto-pm" / "continuity.db")
    store.initialize("2026-10-21T00:00:00+00:00", "test")
    return store


def _draft(store: ContinuityStore, request_id: str, project_id: str) -> str:
    draft = PlanningDraft.from_intent(
        PmIntent(
            request_id=request_id,
            subject_project_id=project_id,
            objective=f"objective of {request_id}",
            acceptance_criteria=("done",),
        )
    )
    store.create_planning_draft(draft)
    return draft.request_id


def test_a_number_held_by_another_project_moves_to_the_next_free_one(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for n, request in ((4, "REQ-009-A"), (5, "REQ-009-B"), (7, "REQ-009-C")):
        store.reserve_planning_draft_change(
            _draft(store, request, "SW-2026-009"), f"CHG-SCPT-2026-{n:03d}"
        )
    own = _draft(store, "REQ-010-IO", "SW-2026-010")
    assert store.reserve_planning_draft_change(own, "CHG-SCPT-2026-004") == "CHG-SCPT-2026-006"


def test_a_free_candidate_is_kept(tmp_path: Path) -> None:
    store = _store(tmp_path)
    own = _draft(store, "REQ-010-IO", "SW-2026-010")
    assert store.reserve_planning_draft_change(own, "CHG-SCPT-2026-003") == "CHG-SCPT-2026-003"


def test_a_replay_returns_the_original_number(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.reserve_planning_draft_change(
        _draft(store, "REQ-009-A", "SW-2026-009"), "CHG-SCPT-2026-004"
    )
    own = _draft(store, "REQ-010-IO", "SW-2026-010")
    first = store.reserve_planning_draft_change(own, "CHG-SCPT-2026-004")
    assert first == "CHG-SCPT-2026-005"
    assert store.reserve_planning_draft_change(own, "CHG-SCPT-2026-004") == first


def test_the_number_width_is_kept_past_the_padding(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.reserve_planning_draft_change(_draft(store, "REQ-A", "SW-2026-009"), "CHG-PLC-2026-099")
    own = _draft(store, "REQ-B", "DJ-2026-011")
    assert store.reserve_planning_draft_change(own, "CHG-PLC-2026-099") == "CHG-PLC-2026-100"


def test_a_malformed_candidate_is_refused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    own = _draft(store, "REQ-B", "SW-2026-010")
    with pytest.raises(ContinuityStoreError, match="格式非法"):
        store.reserve_planning_draft_change(own, "CHG-SCPT-2026-ABC")
