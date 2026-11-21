from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from auto_pm.infrastructure.gate_task_store import GateTaskStore


def test_simultaneous_agents_reserve_one_dispatch(tmp_path: Path) -> None:
    def reserve(_: int) -> tuple[str, bool]:
        attempt, new = GateTaskStore(tmp_path).reserve("same-candidate", "github")
        return attempt.id, new

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(reserve, range(16)))
    assert len({attempt_id for attempt_id, _ in outcomes}) == 1
    assert sum(new for _, new in outcomes) == 1


def test_single_local_round_per_control_root(tmp_path: Path) -> None:
    store = GateTaskStore(tmp_path)
    first, _ = store.reserve("first", "local")
    with pytest.raises(ValueError, match=first.id):
        store.reserve("second", "local")
    store.observe(first, "stopped")
    _, reserved = store.reserve("second", "local")
    assert reserved
