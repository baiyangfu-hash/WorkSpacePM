"""TD-071 card 1: Mission park/unpark in the Continuity Store (storage layer only).

One project may have several open Missions, but at most one ACTIVE ("在干") and at most one held lease.
Parking puts the ACTIVE one down with a checkpoint and fences its lease; unparking picks a parked one
back up only when nothing else is active, the worktree is exactly as it was left, and the user's own
words are cited.  Everything else that would touch a parked Run's lease is refused.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core.mission_service import MissionService, MissionServiceError
from auto_pm.contracts.continuity import RunState, WorkKind
from auto_pm.contracts.lease_reclaim import (
    GRACE_SECONDS,
    PARKED_TOKEN_PREFIX,
    ProcessVerdict,
    lease_is_held,
    lease_token_is_fenced,
)
from auto_pm.contracts.mission import (
    BOARD_COLUMN_BY_STATE,
    AuthorityAudit,
    AuthorityEnvelope,
    Mission,
    MissionPark,
    MissionState,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from tests.core.test_continuity_execution_service import (
    Clock,
    _checkpoint,
    _direct_settlement_values,
    _services,
    _settlement_ready,
    _start,
)

PROJECT = "SW-2026-008"
APPROVAL = "user-confirmation:cmsg_user_says_switch_to_A"


class Scene:
    """Mission A (root WORK-001, RUN-001 held by agent-a) ACTIVE; Mission B (WORK-002) waiting."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True)
        self.root = root
        self.clock = Clock()
        self.works, self.execution = _services(root, self.clock)
        self.store: ContinuityStore = self.execution._store
        self.missions = MissionService(root, now=self.clock, store=self.store)
        _start(self.execution)
        self.execution.transition_run("RUN-001", RunState.RUNNING, "agent-a", "lease-secret", "a-running")
        self.head = self.store.get_run("RUN-001").git_head
        self.a = self.create_mission("MISSION-A", "WORK-001", title="第1道收尾")
        self.a = self.activate(self.a, "WORK-001")

    def authority(self, *, hours: int = 24) -> AuthorityEnvelope:
        now = self.clock()
        return AuthorityEnvelope(
            envelope_id="AUTH-SW008-PARK",
            subject_project_id=PROJECT,
            change_id="CHG-SCPT-2026-500",
            decision_id="DEC-20260909-PARK0001",
            scope_paths=("auto_pm/core/a.py",),
            valid_from=now - timedelta(hours=1),
            expires_at=now + timedelta(hours=hours),
            audit=AuthorityAudit(
                created_by="Claude PM",
                created_at=now,
                approved_by="fubai",
                approved_at=now,
                source_fingerprint=f"sha256:{'c' * 64}",
            ),
        )

    def create_mission(self, mission_id: str, work_id: str, *, title: str, hours: int = 24) -> Mission:
        now = self.clock()
        mission = Mission(
            mission_id=mission_id,
            subject_project_id=PROJECT,
            title=title,
            objective=title,
            acceptance_criteria=("done",),
            authority=self.authority(hours=hours),
            created_by="Claude PM",
            created_at=now,
            updated_at=now,
        )
        values = mission.model_dump(mode="json")
        values.pop("schema_version")
        values["acceptance_criteria_json"] = json.dumps(values.pop("acceptance_criteria"))
        values["authority_json"] = json.dumps(values.pop("authority"), sort_keys=True)
        return self.store.create_mission(
            values, f"create-{mission_id}", now.isoformat(), max_open_per_project=8
        )

    def activate(self, mission: Mission, work_id: str) -> Mission:
        now = self.clock().isoformat()
        waiting = self.store.transition_mission(
            mission.mission_id, mission.version, MissionState.AWAITING_APPROVAL, work_id,
            f"submit-{mission.mission_id}", now,
        )
        return self.store.transition_mission(
            waiting.mission_id, waiting.version, MissionState.ACTIVE, work_id,
            f"start-{mission.mission_id}", now,
        )

    def second_card(self) -> Mission:
        self.works.create_work(
            work_id="WORK-002",
            subject_project_id=PROJECT,
            kind=WorkKind.GOVERNANCE,
            title="急活",
            owner="architect",
            scope_paths=["auto_pm/core/a.py", "tests/test_a.py"],
            source_fingerprint="sha256:def",
            idempotency_key="create-work-2",
            read_only=True,
        )
        mission = self.create_mission("MISSION-B", "WORK-002", title="客户急改 IO 表")
        return self.store.transition_mission(
            mission.mission_id, mission.version, MissionState.AWAITING_APPROVAL, "WORK-002",
            "submit-MISSION-B", self.clock().isoformat(),
        )

    def start_second_run(self) -> None:
        _start(
            self.execution, run_id="RUN-002", work_id="WORK-002", executor_id="agent-b",
            lease_token="token-b", idempotency_key="create-run-b",
        )
        self.execution.transition_run("RUN-002", RunState.RUNNING, "agent-b", "token-b", "b-running")

    def park(self, mission_id: str = "MISSION-A", **changes: Any) -> MissionPark:
        mission = self.store.get_mission(mission_id)
        values: dict[str, Any] = {
            "mission_id": mission_id,
            "expected_mission_version": mission.version,
            "park_id": f"PARK-{mission_id[-1]}-1",
            "checkpoint_id": f"CKPT-PK-{mission_id[-1]}-1",
            "owner_id": "agent-a",
            "lease_token": "lease-secret",
            "reason": "客户急改 IO 表",
            "summary": "OB1 已改完，差测试；下一步补 test_a",
            "git_head": self.head,
            "dirty_paths": ["auto_pm/core/a.py"],
            "idempotency_key": f"park-{mission_id}",
            "approval_evidence_ref": APPROVAL,
        }
        values.update(changes)
        return self.store.park_mission(**values)

    def unpark(self, mission_id: str = "MISSION-A", **changes: Any) -> tuple[MissionPark, Any]:
        mission = self.store.get_mission(mission_id)
        values: dict[str, Any] = {
            "mission_id": mission_id,
            "expected_mission_version": mission.version,
            "new_owner_id": "agent-c",
            "new_token": "token-c",
            "lease_seconds": 900,
            "observed_git_head": self.head,
            "observed_dirty_paths": ["auto_pm/core/a.py"],
            "approval_evidence_ref": APPROVAL,
            "idempotency_key": f"unpark-{mission_id}",
        }
        values.update(changes)
        return self.store.unpark_mission(**values)

    def db(self) -> sqlite3.Connection:
        return closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db"))  # type: ignore[return-value]

    def snapshot(self) -> tuple[Any, ...]:
        with self.db() as conn:
            return tuple(
                tuple(conn.execute(query).fetchall())
                for query in (
                    "SELECT * FROM events ORDER BY rowid",
                    "SELECT * FROM mission_items ORDER BY mission_id",
                    "SELECT * FROM run_items ORDER BY run_id",
                    "SELECT * FROM execution_leases ORDER BY run_id",
                    "SELECT * FROM checkpoints ORDER BY checkpoint_id",
                    "SELECT * FROM run_parks ORDER BY park_id",
                )
            )


@pytest.fixture
def scene(tmp_path: Path) -> Scene:
    return Scene(tmp_path / "ws")


# ------------------------------------------------------------------ contracts


def test_every_mission_state_has_exactly_one_board_column() -> None:
    assert set(BOARD_COLUMN_BY_STATE) == set(MissionState)
    assert BOARD_COLUMN_BY_STATE[MissionState.PARKED].value == "PARKED"
    assert BOARD_COLUMN_BY_STATE[MissionState.BLOCKED].value == "WAITING"
    assert BOARD_COLUMN_BY_STATE[MissionState.DRAFT].value == "WAITING"


def test_lease_is_held_is_false_for_fenced_tokens_whatever_the_expiry(scene: Scene) -> None:
    now = scene.clock()
    future = now + timedelta(hours=1)
    assert lease_is_held(lease_token="lease-secret", expires_at=future, now=now)
    assert not lease_is_held(lease_token=PARKED_TOKEN_PREFIX + "x", expires_at=future, now=now)
    assert not lease_is_held(lease_token="RELEASED:x", expires_at=future, now=now)
    within_grace = now - timedelta(seconds=GRACE_SECONDS - 5)
    assert lease_is_held(lease_token="lease-secret", expires_at=within_grace, now=now)
    assert not lease_is_held(
        lease_token="lease-secret", expires_at=now - timedelta(seconds=GRACE_SECONDS + 1), now=now
    )
    assert lease_token_is_fenced("PARKED:abc") and not lease_token_is_fenced("parked:abc")


def test_parked_mission_requires_root_work_and_may_outlive_its_authority(scene: Scene) -> None:
    data = scene.a.model_dump()
    with pytest.raises(ValueError, match="root_work_id"):
        Mission.model_validate({**data, "state": MissionState.PARKED, "root_work_id": None})
    late = scene.a.authority.expires_at + timedelta(days=3)
    assert Mission.model_validate({**data, "state": MissionState.PARKED, "updated_at": late})
    with pytest.raises(ValueError, match="authority validity window"):
        Mission.model_validate({**data, "state": MissionState.ACTIVE, "updated_at": late})


# ------------------------------------------------------------------ schema v8


def test_fresh_store_is_v8_with_the_active_only_index_and_the_park_table(scene: Scene) -> None:
    with scene.db() as conn:
        version = conn.execute("SELECT schema_version FROM schema_meta").fetchone()[0]
        indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert version == "continuity-store.v8"
    assert "idx_one_active_mission_per_project" in indexes
    assert "idx_one_open_mission_per_project" not in indexes
    assert {"idx_one_open_park_per_run", "idx_run_parks_mission"} <= indexes
    assert "run_parks" in tables


def test_v7_store_with_an_open_mission_migrates_without_touching_rows(tmp_path: Path) -> None:
    scene = Scene(tmp_path / "ws")
    with scene.db() as conn, conn:
        conn.execute("DROP INDEX idx_one_active_mission_per_project")
        conn.execute("DROP TABLE run_parks")
        conn.execute(
            """CREATE UNIQUE INDEX idx_one_open_mission_per_project ON mission_items(subject_project_id)
            WHERE state NOT IN ('ACCEPTED', 'CLOSED', 'CANCELLED')"""
        )
        conn.execute("UPDATE schema_meta SET schema_version='continuity-store.v7'")
        missions_before = conn.execute("SELECT * FROM mission_items").fetchall()
    with scene.db() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    ContinuityStore(scene.root).initialize(scene.clock().isoformat(), "test-v8")

    with scene.db() as conn:
        version = conn.execute("SELECT schema_version FROM schema_meta").fetchone()[0]
        migration = conn.execute(
            "SELECT from_version, to_version, tool_version FROM schema_migrations"
        ).fetchall()
        indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        missions_after = conn.execute("SELECT * FROM mission_items").fetchall()
    assert version == "continuity-store.v8"
    assert migration == [("continuity-store.v7", "continuity-store.v8", "test-v8")]
    assert "idx_one_open_mission_per_project" not in indexes
    assert "idx_one_active_mission_per_project" in indexes
    assert missions_after == missions_before
    # Re-initializing a v8 store is a no-op.
    ContinuityStore(scene.root).initialize(scene.clock().isoformat(), "again")
    with scene.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1


def test_an_older_tool_refuses_to_open_a_v8_store(scene: Scene, monkeypatch: pytest.MonkeyPatch) -> None:
    import auto_pm.infrastructure.continuity_store as module

    monkeypatch.setattr(
        module, "_KNOWN_SCHEMA_VERSIONS", module._KNOWN_SCHEMA_VERSIONS - {"continuity-store.v8"}
    )
    with pytest.raises(ContinuityStoreError, match="未知或未来"):
        ContinuityStore(scene.root).initialize(scene.clock().isoformat(), "1.3.3")


def test_the_database_refuses_a_second_active_mission(scene: Scene) -> None:
    b = scene.second_card()
    with pytest.raises(ContinuityStoreError, match="只能有一张在干"):
        scene.store.transition_mission(
            b.mission_id, b.version, MissionState.ACTIVE, "WORK-002", "start-b", scene.clock().isoformat()
        )
    with scene.db() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE mission_items SET state='ACTIVE' WHERE mission_id='MISSION-B'")
    assert scene.store.get_mission("MISSION-B").state is MissionState.AWAITING_APPROVAL


def test_open_mission_limit_is_a_store_parameter_defaulting_to_the_old_rule(scene: Scene) -> None:
    now = scene.clock()
    mission = Mission(
        mission_id="MISSION-X",
        subject_project_id=PROJECT,
        title="x",
        objective="x",
        acceptance_criteria=("x",),
        authority=scene.authority(),
        created_by="Claude PM",
        created_at=now,
        updated_at=now,
    )
    values = mission.model_dump(mode="json")
    values.pop("schema_version")
    values["acceptance_criteria_json"] = json.dumps(values.pop("acceptance_criteria"))
    values["authority_json"] = json.dumps(values.pop("authority"), sort_keys=True)
    with pytest.raises(ContinuityStoreError, match="未终结 Mission"):
        scene.store.create_mission(values, "create-x", now.isoformat())
    with pytest.raises(ContinuityStoreError, match="上限 1 张|未终结"):
        scene.store.create_mission(values, "create-x", now.isoformat(), max_open_per_project=1)
    with pytest.raises(ContinuityStoreError, match="上限 2 张"):
        scene.second_card()
        scene.store.create_mission(values, "create-x", now.isoformat(), max_open_per_project=2)
    with pytest.raises(ContinuityStoreError, match="正整数"):
        scene.store.create_mission(values, "create-x", now.isoformat(), max_open_per_project=0)


# ------------------------------------------------------------------ park


def test_park_does_all_five_steps_in_one_go(scene: Scene) -> None:
    lease_before = scene.store.get_lease("RUN-001")
    run_before = scene.store.get_run("RUN-001")

    park = scene.park()

    mission = scene.store.get_mission("MISSION-A")
    run = scene.store.get_run("RUN-001")
    lease = scene.store.get_lease("RUN-001")
    checkpoint = scene.store.get_checkpoint("CKPT-PK-A-1")
    assert mission.state is MissionState.PARKED and mission.version == scene.a.version + 1
    assert run.state is RunState.BLOCKED and run.version == run_before.version + 1
    assert lease.lease_token.startswith(PARKED_TOKEN_PREFIX)
    assert lease.version == lease_before.version + 1
    assert lease.expires_at == lease_before.expires_at and lease.owner_id == "agent-a"
    assert checkpoint.summary == "OB1 已改完，差测试；下一步补 test_a"
    assert checkpoint.git_head == scene.head and checkpoint.dirty_paths == ("auto_pm/core/a.py",)
    assert checkpoint.evidence == ("park:PARK-A-1", "reason:客户急改 IO 表")
    assert park.run_id == "RUN-001" and park.unparked_at is None and park.parked_by == "agent-a"
    assert scene.store.get_open_park("MISSION-A") == park
    with scene.db() as conn:
        events = conn.execute(
            "SELECT event_type, payload_json FROM events ORDER BY rowid DESC LIMIT 3"
        ).fetchall()
    assert [row[0] for row in events] == ["MISSION_PARKED", "RUN_PARKED", "CHECKPOINT_CREATED"]
    assert all("lease-secret" not in row[1] for row in events)
    # The Run activity timeline still validates its hash chain and shows the checkpoint.
    stages = [activity.event_type for activity in scene.store.list_run_activities("RUN-001")]
    assert stages[-1] == "CHECKPOINT_CREATED"


def test_park_replays_with_the_same_key_and_refuses_a_changed_request(scene: Scene) -> None:
    first = scene.park()
    before = scene.snapshot()
    again = scene.store.park_mission(
        mission_id="MISSION-A",
        expected_mission_version=scene.a.version,
        park_id="PARK-A-1",
        checkpoint_id="CKPT-PK-A-1",
        owner_id="agent-a",
        lease_token="lease-secret",
        reason="客户急改 IO 表",
        summary="OB1 已改完，差测试；下一步补 test_a",
        git_head=scene.head,
        dirty_paths=["auto_pm/core/a.py"],
        idempotency_key="park-MISSION-A",
        approval_evidence_ref=APPROVAL,
    )
    assert again == first and scene.snapshot() == before
    with pytest.raises(ContinuityStoreError, match="语义不一致"):
        scene.store.park_mission(
            mission_id="MISSION-A",
            expected_mission_version=scene.a.version,
            park_id="PARK-A-1",
            checkpoint_id="CKPT-PK-A-1",
            owner_id="agent-a",
            lease_token="lease-secret",
            reason="另一个原因",
            summary="OB1 已改完，差测试；下一步补 test_a",
            git_head=scene.head,
            dirty_paths=["auto_pm/core/a.py"],
            idempotency_key="park-MISSION-A",
            approval_evidence_ref=APPROVAL,
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"lease_token": "not-the-token"}, "lease ownership 不匹配"),
        ({"owner_id": "agent-b"}, "lease ownership 不匹配"),
        ({"dirty_paths": ["tests/elsewhere.py"]}, "超出本卡范围"),
        ({"dirty_paths": ["auto_pm/core/a.py", "auto_pm/core/a.py"]}, "重复"),
        ({"dirty_paths": ["../escape.py"]}, "非法 authority path"),
        ({"git_head": "0" * 40}, "baseline drift"),
        ({"git_head": "abc"}, "40 位"),
        ({"expected_mission_version": 1}, "版本冲突"),
        ({"summary": "  "}, "断点摘要"),
        ({"summary": "token lease-secret leaked"}, "不得包含 lease token"),
        ({"park_id": "park-lower"}, "park_id 格式"),
    ],
)
def test_park_refusals_write_nothing(scene: Scene, changes: dict[str, Any], message: str) -> None:
    before = scene.snapshot()
    with pytest.raises(ContinuityStoreError, match=message):
        scene.park(**changes)
    assert scene.snapshot() == before


def test_park_refuses_an_expired_lease_and_a_waiting_mission(scene: Scene) -> None:
    b = scene.second_card()
    with pytest.raises(ContinuityStoreError, match="只有在干（ACTIVE）或卡住（BLOCKED）"):
        scene.park("MISSION-B", expected_mission_version=b.version)
    scene.clock.value = scene.clock.value + timedelta(hours=2)
    before = scene.snapshot()
    with pytest.raises(ContinuityStoreError, match="lease 已过期"):
        scene.park()
    assert scene.snapshot() == before


def test_a_failure_in_the_last_step_rolls_the_whole_park_back(
    scene: Scene, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = ContinuityStore._insert_mapping

    def failing(conn: sqlite3.Connection, table: str, values: dict[str, Any]) -> None:
        if table == "run_parks":
            raise sqlite3.IntegrityError("simulated crash before the park row")
        original(conn, table, values)

    monkeypatch.setattr(ContinuityStore, "_insert_mapping", staticmethod(failing))
    before = scene.snapshot()
    with pytest.raises(sqlite3.IntegrityError):
        scene.park()
    assert scene.snapshot() == before
    assert scene.store.get_lease("RUN-001").lease_token == "lease-secret"


def test_a_blocked_mission_can_be_parked_too(scene: Scene) -> None:
    blocked = scene.missions.transition(
        mission_id="MISSION-A",
        expected_version=scene.a.version,
        new_state=MissionState.BLOCKED,
        root_work_id=None,
        idempotency_key="block-a",
    )
    park = scene.park(expected_mission_version=blocked.version)
    assert scene.store.get_mission("MISSION-A").state is MissionState.PARKED
    assert park.mission_id == "MISSION-A"


# ------------------------------------------------------------------ while parked


def test_while_parked_every_other_lease_action_is_refused(scene: Scene) -> None:
    _checkpoint(scene.execution)
    handoff = scene.store.create_handoff(
        handoff_id="HO-001",
        checkpoint_id="CP-001",
        from_owner="agent-a",
        to_owner="agent-b",
        lease_token="lease-secret",
        idempotency_key="handoff-before-park",
    )
    scene.park(dirty_paths=["auto_pm/core/a.py"])
    lease = scene.store.get_lease("RUN-001")
    run = scene.store.get_run("RUN-001")
    before = scene.snapshot()

    with pytest.raises(ContinuityStoreError, match="搁着.*不能续租"):
        scene.store.renew_lease("RUN-001", "agent-a", "lease-secret", 900, "renew-parked")
    with pytest.raises(ContinuityStoreError, match="搁着.*不能接手"):
        scene.store.transfer_lease(handoff.handoff_id, "agent-b", "token-b2", 900, "takeover-parked")
    with pytest.raises(ContinuityStoreError, match="搁着.*不需要再交接"):
        scene.store.create_handoff(
            handoff_id="HO-002",
            checkpoint_id="CP-001",
            from_owner="agent-a",
            to_owner="agent-b",
            lease_token="lease-secret",
            idempotency_key="handoff-parked",
        )
    with pytest.raises(ContinuityStoreError, match="搁着不是掉线"):
        scene.store.reclaim_lease(
            run_id="RUN-001",
            expected_owner_id="agent-a",
            expected_lease_version=lease.version,
            claimant_id="agent-b",
            new_token="token-reclaim",
            lease_seconds=900,
            process_verdict=ProcessVerdict.PROVEN_DEAD,
            risk_acceptance_id="",
            reason="looks dead",
            idempotency_key="reclaim-parked",
        )
    # The fenced marker itself is never accepted as a holder's token, nor is the old token.
    for token in (lease.lease_token, "lease-secret"):
        with pytest.raises(ContinuityStoreError, match="搁着"):
            scene.store.transition_run(
                "RUN-001", run.version, RunState.RUNNING.value, f"run-{token[:8]}", "",
                owner_id="agent-a", lease_token=token,
            )
        with pytest.raises(ContinuityStoreError, match="搁着"):
            scene.store.create_checkpoint(
                {
                    "checkpoint_id": f"CP-{token[:6]}",
                    "run_id": "RUN-001",
                    "summary": "x",
                    "git_head": scene.head,
                    "dirty_paths_json": "[]",
                    "evidence_json": '["x"]',
                    "created_at": scene.clock().isoformat(),
                },
                f"cp-{token[:8]}",
                scene.clock().isoformat(),
                owner_id="agent-a",
                lease_token=token,
            )
    # Even long after the old expiry a parked Run is not reclaimable.
    scene.clock.value = scene.clock.value + timedelta(days=3)
    with pytest.raises(ContinuityStoreError, match="搁着不是掉线"):
        scene.store.reclaim_lease(
            run_id="RUN-001",
            expected_owner_id="agent-a",
            expected_lease_version=lease.version,
            claimant_id="agent-b",
            new_token="token-reclaim",
            lease_seconds=900,
            process_verdict=ProcessVerdict.PROVEN_DEAD,
            risk_acceptance_id="",
            reason="looks dead",
            idempotency_key="reclaim-parked-late",
        )
    assert scene.snapshot() == before


def test_mission_service_cannot_park_or_unpark_by_a_plain_transition(scene: Scene) -> None:
    with pytest.raises(MissionServiceError, match="只能走 park/unpark"):
        scene.missions.transition(
            mission_id="MISSION-A",
            expected_version=scene.a.version,
            new_state=MissionState.PARKED,
            root_work_id=None,
            idempotency_key="plain-park",
        )
    with pytest.raises(ContinuityStoreError, match="park_mission"):
        scene.store.transition_mission(
            "MISSION-A", scene.a.version, MissionState.PARKED, "WORK-001", "raw-park", scene.clock().isoformat()
        )
    scene.park()
    parked = scene.store.get_mission("MISSION-A")
    with pytest.raises(MissionServiceError, match="只能走 park/unpark"):
        scene.missions.transition(
            mission_id="MISSION-A",
            expected_version=parked.version,
            new_state=MissionState.ACTIVE,
            root_work_id=None,
            idempotency_key="plain-unpark",
        )
    with pytest.raises(ContinuityStoreError, match="unpark_mission"):
        scene.store.transition_mission(
            "MISSION-A", parked.version, MissionState.ACTIVE, "WORK-001", "raw-unpark", scene.clock().isoformat()
        )
    with pytest.raises(MissionServiceError, match="不允许从 PARKED 流转到 BLOCKED"):
        scene.missions.transition(
            mission_id="MISSION-A",
            expected_version=parked.version,
            new_state=MissionState.BLOCKED,
            root_work_id=None,
            idempotency_key="parked-to-blocked",
        )
    cancelled = scene.missions.transition(
        mission_id="MISSION-A",
        expected_version=parked.version,
        new_state=MissionState.CANCELLED,
        root_work_id=None,
        idempotency_key="cancel-parked",
    )
    assert cancelled.state is MissionState.CANCELLED


# ------------------------------------------------------------------ unpark


def test_unpark_grants_a_new_epoch_to_whoever_picks_it_up(scene: Scene) -> None:
    epoch_before = scene.store.get_grant_epoch("RUN-001")
    scene.park()
    scene.clock.value = scene.clock.value + timedelta(hours=5)  # the old lease is long expired

    park, lease = scene.unpark()

    assert park.unparked_by == "agent-c" and park.unparked_at is not None
    assert scene.store.get_open_park("MISSION-A") is None
    assert scene.store.get_mission("MISSION-A").state is MissionState.ACTIVE
    assert scene.store.get_run("RUN-001").state is RunState.RUNNING
    assert lease.owner_id == "agent-c" and lease.lease_token == "token-c"
    assert scene.store.get_grant_epoch("RUN-001") == lease.version > epoch_before
    with scene.db() as conn:
        payload = conn.execute(
            "SELECT payload_json FROM events WHERE event_type='MISSION_UNPARKED'"
        ).fetchone()[0]
    assert APPROVAL in payload and "token-c" not in payload
    # The new holder can work again with its own token and the epoch it was granted.
    checkpoint = _checkpoint(
        scene.execution,
        checkpoint_id="CP-AFTER",
        owner_id="agent-c",
        lease_token="token-c",
        idempotency_key="checkpoint-after-unpark",
        expected_epoch=lease.version,
    )
    assert checkpoint.run_id == "RUN-001"
    # Replaying the same unpark returns the same result and writes nothing.
    before = scene.snapshot()
    mission = scene.store.get_mission("MISSION-A")
    replay_park, _ = scene.store.unpark_mission(
        mission_id="MISSION-A",
        expected_mission_version=mission.version - 1,
        new_owner_id="agent-c",
        new_token="token-c",
        lease_seconds=900,
        observed_git_head=scene.head,
        observed_dirty_paths=["auto_pm/core/a.py"],
        approval_evidence_ref=APPROVAL,
        idempotency_key="unpark-MISSION-A",
    )
    assert replay_park == park and scene.snapshot() == before


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"observed_git_head": "1" * 40}, "HEAD 变了"),
        ({"observed_dirty_paths": ["auto_pm/core/a.py", "tests/test_a.py"]}, "多出改动: tests/test_a.py"),
        ({"observed_dirty_paths": []}, "少了改动: auto_pm/core/a.py"),
        ({"approval_evidence_ref": "  "}, "用户授权凭据"),
        ({"approval_evidence_ref": "said token-c"}, "不得包含 lease token"),
        ({"new_token": "PARKED:forged"}, "保留前缀"),
        ({"lease_seconds": 30}, "60 到 3600"),
        ({"expected_mission_version": 1}, "版本冲突"),
    ],
)
def test_unpark_refusals_write_nothing(scene: Scene, changes: dict[str, Any], message: str) -> None:
    scene.park()
    before = scene.snapshot()
    with pytest.raises(ContinuityStoreError, match=message):
        scene.unpark(**changes)
    assert scene.snapshot() == before


def test_unpark_refuses_a_mission_that_is_not_parked_or_whose_authority_expired(tmp_path: Path) -> None:
    scene = Scene(tmp_path / "ws")
    with pytest.raises(ContinuityStoreError, match="只有搁着（PARKED）"):
        scene.unpark()
    scene.park()
    scene.clock.value = scene.a.authority.expires_at + timedelta(minutes=1)
    with pytest.raises(ContinuityStoreError, match="授权已过期"):
        scene.unpark()


def test_insert_an_urgent_card_then_pick_the_first_one_back_up(scene: Scene) -> None:
    b = scene.second_card()
    # A is still ACTIVE, so B cannot start.
    with pytest.raises(MissionServiceError, match="正在干"):
        scene.missions.transition(
            mission_id="MISSION-B", expected_version=b.version, new_state=MissionState.ACTIVE,
            root_work_id=None, idempotency_key="start-b-too-early",
        )
    scene.park()
    b = scene.missions.transition(
        mission_id="MISSION-B", expected_version=b.version, new_state=MissionState.ACTIVE,
        root_work_id=None, idempotency_key="start-b",
    )
    scene.start_second_run()
    # B is now in hand: A cannot be picked back up.
    with pytest.raises(ContinuityStoreError, match="客户急改 IO 表.*正在干"):
        scene.unpark()
    # Even with B's Mission row out of the way, B's held lease still blocks picking A up.
    with scene.db() as conn, conn:
        conn.execute("UPDATE mission_items SET state='BLOCKED' WHERE mission_id='MISSION-B'")
    with pytest.raises(ContinuityStoreError, match="别的 Run 持有租约.*RUN-002"):
        scene.unpark()
    with scene.db() as conn, conn:
        conn.execute("UPDATE mission_items SET state='ACTIVE' WHERE mission_id='MISSION-B'")

    board = scene.store.list_missions_by_board(PROJECT)
    assert [m.mission_id for m in board.active] == ["MISSION-B"]
    assert [p.mission.mission_id for p in board.parked] == ["MISSION-A"]
    assert board.parked[0].checkpoint_summary.startswith("OB1 已改完")
    assert board.waiting == () and board.closed == () and board.open_count == 2

    scene.clock.value = scene.clock.value + timedelta(minutes=10)
    scene.park(
        "MISSION-B", owner_id="agent-b", lease_token="token-b", idempotency_key="park-b",
        summary="IO 表改了一半", reason="等客户回图纸",
    )
    # A later edit of A's row (e.g. a new scope revision) must not reorder the parked column.
    with scene.db() as conn, conn:
        conn.execute("UPDATE mission_items SET updated_at='2026-09-09T23:00:00+00:00' WHERE mission_id='MISSION-A'")
    board = scene.store.list_missions_by_board(PROJECT)
    assert board.active == ()
    # Last put down is listed first (suggested back first).
    assert [p.mission.mission_id for p in board.parked] == ["MISSION-B", "MISSION-A"]

    park, _lease = scene.unpark()
    assert park.mission_id == "MISSION-A"
    board = scene.store.list_missions_by_board(PROJECT)
    assert [m.mission_id for m in board.active] == ["MISSION-A"]
    assert [p.mission.mission_id for p in board.parked] == ["MISSION-B"]


def test_board_refuses_a_parked_mission_without_its_park_record(scene: Scene) -> None:
    scene.park()
    with scene.db() as conn, conn:
        conn.execute("UPDATE run_parks SET unparked_at='x', unparked_by='y'")
    with pytest.raises(ContinuityStoreError, match="数据不一致"):
        scene.store.list_missions_by_board(PROJECT)


def test_the_database_allows_only_one_open_park_per_run(scene: Scene) -> None:
    scene.park()
    with scene.db() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO run_parks VALUES ('PARK-A-2', 'RUN-001', 'MISSION-A', 'CKPT-PK-A-1',
            'agent-a', 'again', '2026-09-09T12:00:00+00:00', NULL, NULL)"""
        )
    with scene.db() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE run_parks SET unparked_at='2026-09-09T13:00:00+00:00'")


# ------------------------------------------------------------------ closure


def test_one_project_closes_one_mission_at_a_time(scene: Scene) -> None:
    _checkpoint(scene.execution)
    scene.second_card()
    with scene.db() as conn, conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """INSERT INTO closure_items VALUES ('CLOSURE-B', 'MISSION-B', 'WORK-001', 'RUN-001',
            'CP-001', 'CHG-SCPT-2026-500', 'DEC-20260909-PARK0001', 'PREPARED', 'h', 1,
            '2026-09-09T12:00:00+00:00', '2026-09-09T12:00:00+00:00')"""
        )
        conn.execute("UPDATE mission_items SET state='ACCEPTED' WHERE mission_id='MISSION-A'")
    with pytest.raises(ContinuityStoreError, match="MISSION-B 正在收口"):
        scene.store.prepare_closure("MISSION-A", "prepare-a", scene.clock().isoformat())

    with scene.db() as conn, conn:
        conn.execute("UPDATE closure_items SET state='COMPLETED'")
    with pytest.raises(ContinuityStoreError) as other:
        scene.store.prepare_closure("MISSION-A", "prepare-a-2", scene.clock().isoformat())
    assert "正在收口" not in str(other.value)


def test_a_closure_in_another_project_does_not_block(scene: Scene) -> None:
    _checkpoint(scene.execution)
    with scene.db() as conn, conn:
        conn.execute(
            """INSERT INTO mission_items SELECT 'MISSION-OTHER', 'DJ-2026-009', title, objective,
            'ACCEPTED', root_work_id, acceptance_criteria_json, authority_json, version, created_by,
            created_at, updated_at FROM mission_items WHERE mission_id='MISSION-A'"""
        )
        conn.execute(
            """INSERT INTO closure_items VALUES ('CLOSURE-O', 'MISSION-OTHER', 'WORK-001', 'RUN-001',
            'CP-001', 'CHG-SCPT-2026-500', 'DEC-20260909-PARK0001', 'PREPARED', 'h', 1,
            '2026-09-09T12:00:00+00:00', '2026-09-09T12:00:00+00:00')"""
        )
        conn.execute("UPDATE mission_items SET state='ACCEPTED' WHERE mission_id='MISSION-A'")
    with pytest.raises(ContinuityStoreError) as refused:
        scene.store.prepare_closure("MISSION-A", "prepare-a", scene.clock().isoformat())
    assert "正在收口" not in str(refused.value)


def test_administrative_settlement_refuses_a_parked_run_even_after_its_old_expiry(tmp_path: Path) -> None:
    clock = Clock()
    root = tmp_path / "settle"
    root.mkdir()
    service = _settlement_ready(root, clock)
    store = service._store
    target_run = store.get_run("RUN-TARGET")
    lease = store.get_lease("RUN-TARGET")
    # Put RUN-TARGET into the parked shape directly (a Mission that owns WORK-TARGET, a fenced lease, an open park).
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn, conn:
        conn.execute(
            """INSERT INTO mission_items VALUES ('MISSION-T', 'SW-2026-008', 't', 't', 'PARKED',
            'WORK-TARGET', '["t"]', '{}', 1, 'x', ?, ?)""",
            (clock().isoformat(), clock().isoformat()),
        )
        conn.execute(
            """INSERT INTO checkpoints VALUES ('CKPT-PK-T', 'RUN-TARGET', 99, 'parked', ?, '[]',
            '["park:PARK-T"]', ?)""",
            (target_run.git_head, clock().isoformat()),
        )
        conn.execute(
            "UPDATE execution_leases SET lease_token='PARKED:t', version=version+1 WHERE run_id='RUN-TARGET'"
        )
        conn.execute(
            """INSERT INTO run_parks VALUES ('PARK-T', 'RUN-TARGET', 'MISSION-T', 'CKPT-PK-T', 'x',
            'urgent', ?, NULL, NULL)""",
            (clock().isoformat(),),
        )
    clock.value = clock.value + timedelta(days=2)
    assert store.get_lease("RUN-TARGET").version == lease.version + 1
    with pytest.raises(ContinuityStoreError, match="搁着.*不能行政结算"):
        store.settle_expired_run(**_direct_settlement_values(service))
    assert store.get_run("RUN-TARGET").state is target_run.state


# ------------------------------------------------------------------ sweep: exhaustive state maps


def test_views_that_map_every_mission_state_know_parked(scene: Scene) -> None:
    from auto_pm.application.core.continuity_resume_service import ContinuityResumeService
    from auto_pm.application.core.pm_cockpit_service import PmCockpitService
    from auto_pm.contracts.continuity import WorkState

    scene.park()
    parked = scene.store.get_mission("MISSION-A")
    assert PmCockpitService._milestone(parked) == "搁着（断点已记）"
    for state in MissionState:
        PmCockpitService._milestone(parked.model_copy(update={"state": state}))
    action = ContinuityResumeService._next_action(
        MissionState.PARKED, WorkState.IN_PROGRESS, RunState.BLOCKED, True
    )
    assert action == "AWAIT_USER_UNPARK"


# ------------------------------------------------------------------ D5: a card stuck in verification


def test_d5_a_run_in_verifying_can_be_parked_and_comes_back_running(scene: Scene) -> None:
    scene.execution.transition_run(
        "RUN-001", RunState.VERIFYING, "agent-a", "lease-secret", "to-verifying"
    )

    park = scene.park(idempotency_key="park-verifying")

    assert scene.store.get_mission("MISSION-A").state is MissionState.PARKED
    assert scene.store.get_run("RUN-001").state is RunState.BLOCKED
    assert park.mission_id == "MISSION-A"
    scene.unpark()
    # Back as RUNNING: the work is verified afresh, the old VERIFYING state is not resurrected.
    assert scene.store.get_run("RUN-001").state is RunState.RUNNING
    assert scene.store.get_mission("MISSION-A").state is MissionState.ACTIVE


def test_d5_with_no_live_run_the_refusal_says_how_to_get_one(scene: Scene) -> None:
    scene.execution.transition_run(
        "RUN-001", RunState.VERIFYING, "agent-a", "lease-secret", "to-verifying"
    )
    scene.execution.transition_run(
        "RUN-001", RunState.FAILED, "agent-a", "lease-secret", "to-failed"
    )
    before = scene.snapshot()

    with pytest.raises(ContinuityStoreError, match=r"实际 0 个.*continuity run start"):
        scene.park()
    assert scene.snapshot() == before
