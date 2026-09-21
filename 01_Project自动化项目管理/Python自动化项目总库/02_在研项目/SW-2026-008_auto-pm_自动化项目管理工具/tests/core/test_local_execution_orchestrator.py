"""Real-process proofs for the foreground execution claim and projection Saga."""

from __future__ import annotations

import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from auto_pm.core.execution_adapter_service import (
    ExecutionDispatchResult,
)
from auto_pm.core.execution_adapter_service import (
    LeaseCapability as DispatchLeaseCapability,
)
from auto_pm.core.local_execution_orchestrator import LocalExecutionOrchestrator

from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.infrastructure.local_executor import LocalCodexExecutor
from tests.core.test_execution_adapter_service import PROJECT_PATH
from tests.core.test_execution_microtask_service import _prepared

_LEASE_TOKEN = "must-never-persist"
_LEASE_ENV = "AUTO_PM_E08CD_LEASE"


class _CountingExecutor(LocalCodexExecutor):
    def __init__(self, code: str) -> None:
        super().__init__(command_prefix=(sys.executable, "-c", code))
        self.starts = 0
        self._lock = threading.Lock()

    def start(self, request):
        with self._lock:
            self.starts += 1
        return super().start(request)


def _inputs(root: Path, operation_id: str):
    dispatch_service = _prepared(root, operation_id=operation_id)
    store = ContinuityStore(root)
    intent = store.get_execution_intent(operation_id)
    assert intent is not None
    dispatch = ExecutionDispatchResult(
        receipt=intent.receipt,
        intent=intent,
        lease=DispatchLeaseCapability(intent.receipt.owner_id, _LEASE_TOKEN),
    )
    return dispatch, dispatch_service.prepare_microtask(operation_id)


def _helper_code(content: str) -> str:
    return (
        "import json,os,pathlib,sys,time;"
        "repo=pathlib.Path(sys.argv[sys.argv.index('-C')+1]);"
        f"secret=os.environ.get({_LEASE_ENV!r});"
        "print(json.dumps({'type':'thread.started','thread_id':'thread-e08cd'}),flush=True);"
        f"(repo/{PROJECT_PATH!r}).write_text({content!r},encoding='utf-8');"
        "print('password=hunter2 sk-proj-secretvalue',file=sys.stderr,flush=True);"
        "time.sleep(0.15);"
        "sys.exit(23 if secret is not None else 0)"
    )


def test_foreground_saga_uses_real_helper_strips_secret_and_replays_without_popen(
    tmp_path: Path,
    monkeypatch,
) -> None:
    operation_id = "OP-E08CD-REAL-HELPER"
    dispatch, microtask = _inputs(tmp_path, operation_id)
    executor = _CountingExecutor(_helper_code("projected by helper\n"))
    orchestrator = LocalExecutionOrchestrator(tmp_path, executor=executor)
    monkeypatch.setenv(_LEASE_ENV, _LEASE_TOKEN)

    first = orchestrator.execute(
        dispatch=dispatch,
        microtask=microtask,
        lease_token_environment=_LEASE_ENV,
        renewal_interval_seconds=0.05,
    )
    assert first.status == "VERIFYING"
    assert first.exit_code == 0
    assert executor.starts == 1
    assert "must-never-persist" not in first.model_dump_json()
    assert "hunter2" not in first.model_dump_json()
    assert (
        Path(microtask.plan.source_worktree_path) / PROJECT_PATH
    ).read_text(encoding="utf-8") == "projected by helper\n"

    replay = orchestrator.execute(
        dispatch=dispatch,
        microtask=microtask,
        lease_token_environment=_LEASE_ENV,
        renewal_interval_seconds=0.05,
    )
    assert replay == first
    assert executor.starts == 1


def test_concurrent_claim_has_one_real_popen_winner(tmp_path: Path, monkeypatch) -> None:
    operation_id = "OP-E08CD-CONCURRENT"
    dispatch, microtask = _inputs(tmp_path, operation_id)
    executor = _CountingExecutor(_helper_code("concurrent winner\n"))
    orchestrator = LocalExecutionOrchestrator(tmp_path, executor=executor)
    monkeypatch.setenv(_LEASE_ENV, _LEASE_TOKEN)
    barrier = threading.Barrier(2)

    def invoke():
        barrier.wait()
        return orchestrator.execute(
            dispatch=dispatch,
            microtask=microtask,
            lease_token_environment=_LEASE_ENV,
            renewal_interval_seconds=0.05,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _index: invoke(), range(2)))
    assert executor.starts == 1
    assert {item.status for item in results}.issubset({"PENDING", "VERIFYING"})
    assert ContinuityStore(tmp_path).get_execution_start_claim(operation_id) is not None
    with ContinuityStore(tmp_path)._read_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='EXECUTION_START_CLAIMED'"
        ).fetchone()[0]
    assert count == 1
