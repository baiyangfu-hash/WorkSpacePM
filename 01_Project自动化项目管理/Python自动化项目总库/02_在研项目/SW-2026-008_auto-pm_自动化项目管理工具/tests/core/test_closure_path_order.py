"""收口准备（C05）比较 Checkpoint 与 Run 的改动路径时不看顺序（M3-PATHORDER）

D08 第 2 道（DJ-2026-011）Run 登记的路径是 OB1→FB→DB1→Test，证据服务写 Checkpoint 时按字典序
存成 DB1→FB→OB1→Test；C05 逐个位置比较，内容相同也拒收，Mission 停在 ACCEPTED。验收前的
质量验证（``pm_facade_service``）本来就按排序后比较，C05 改成同样的口径；路径真的不同仍拒绝。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from auto_pm.application.core.pm_closure_service import PmClosureError, PmClosureService
from tests.core.test_pm_closure_service import (
    _CHECKPOINT_ID,
    _MISSION_ID,
    _RUN_ID,
    _accepted_lineage,
    _table_counts,
)


def _paths(database: Path, declared: list[str], checkpoint: list[str]) -> None:
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute(
            "UPDATE run_items SET declared_dirty_paths_json=? WHERE run_id=?",
            (json.dumps(declared), _RUN_ID),
        )
        conn.execute(
            "UPDATE checkpoints SET dirty_paths_json=? WHERE checkpoint_id=?",
            (json.dumps(checkpoint), _CHECKPOINT_ID),
        )


def _service(tmp_path: Path) -> tuple[PmClosureService, Path]:
    store, database = _accepted_lineage(tmp_path)
    service = PmClosureService(
        tmp_path, now=lambda: datetime(2026, 9, 20, 12, 10, tzinfo=UTC), store=store
    )
    return service, database


def test_the_same_paths_in_another_order_prepare_the_closure(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    _paths(
        database,
        ["OB1/OB1.scl", "FB_0001/FB.scl", "DB1/DB.scl", "Test/t.scltest"],
        ["DB1/DB.scl", "FB_0001/FB.scl", "OB1/OB1.scl", "Test/t.scltest"],
    )
    preparation = service.prepare_closure(_MISSION_ID, idempotency_key="order-prepare")
    assert preparation.closure.run_id == _RUN_ID
    assert _table_counts(database)["closure_items"] == 1


def test_different_paths_are_still_refused(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    _paths(database, ["OB1/OB1.scl", "FB_0001/FB.scl"], ["FB_0001/FB.scl", "DB1/DB.scl"])
    with pytest.raises(PmClosureError, match="最新 Checkpoint 未绑定 Run 当前验证证据"):
        service.prepare_closure(_MISSION_ID, idempotency_key="order-prepare")
    assert _table_counts(database)["closure_items"] == 0


def test_a_duplicated_path_is_still_refused(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    _paths(database, ["OB1/OB1.scl", "OB1/OB1.scl"], ["OB1/OB1.scl"])
    with pytest.raises(PmClosureError, match="最新 Checkpoint 未绑定 Run 当前验证证据"):
        service.prepare_closure(_MISSION_ID, idempotency_key="order-prepare")
    assert _table_counts(database)["closure_items"] == 0
