import json
import subprocess
from pathlib import Path

import pytest

from auto_pm.application.core.gate_task_service import GateCandidate
from auto_pm.infrastructure import gate_executors
from auto_pm.infrastructure.gate_task_store import GateTaskStore


def test_github_only_falls_back_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = gate_executors.GitHubGateExecutor(tmp_path)
    monkeypatch.setattr(executor, "_repo", lambda: "example/project")
    attempt, _ = GateTaskStore(tmp_path).reserve("candidate", "github")
    candidate = GateCandidate("a" * 40, "b" * 40, "c" * 40, "d" * 64, "gate-full-v1")

    def unavailable(root: Path, argv: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr(gate_executors, "_command", unavailable)
    assert executor.launch(attempt, candidate).state == "unavailable"


def test_local_checks_for_real_plugin_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = gate_executors.LocalGateExecutor(tmp_path)
    attempt, _ = GateTaskStore(tmp_path).reserve("candidate", "local")
    candidate = GateCandidate("a" * 40, "b" * 40, "c" * 40, "d" * 64, "gate-full-v1")
    monkeypatch.setattr(gate_executors, "sha256_file", lambda path: None)
    result = executor.launch(attempt, candidate)
    assert result.state == "unavailable"
    assert "Siemens" in result.detail or "Windows" in result.detail
    assert not (tmp_path / ".auto-pm/reports/gate-tasks" / attempt.id).exists()


def test_github_service_outage_allows_offline_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = gate_executors.GitHubGateExecutor(tmp_path)
    monkeypatch.setattr(executor, "_repo", lambda: "example/project")
    attempt, _ = GateTaskStore(tmp_path).reserve("candidate", "github")
    candidate = GateCandidate("a" * 40, "b" * 40, "c" * 40, "d" * 64, "gate-full-v1")
    calls: list[list[str]] = []

    def outage(root: Path, argv: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, "", "HTTP 503: Service Unavailable")

    monkeypatch.setattr(gate_executors, "_command", outage)
    assert executor.launch(attempt, candidate).state == "unavailable"
    assert len(calls) == 1 and calls[0][1] == "api"


def test_known_github_run_is_reconciled_by_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executor = gate_executors.GitHubGateExecutor(tmp_path)
    store = GateTaskStore(tmp_path)
    attempt, _ = store.reserve("candidate", "github")
    attempt = store.observe(attempt, "running", "123")
    candidate = GateCandidate("a" * 40, "b" * 40, "c" * 40, "d" * 64, "gate-full-v1")

    def gh(*args: str) -> subprocess.CompletedProcess[str]:
        assert args[:3] == ("run", "view", "123")
        return subprocess.CompletedProcess(
            args, 0,
            json.dumps({
                "databaseId": 123, "headSha": candidate.base, "status": "completed",
                "conclusion": "cancelled", "url": "https://github.com/example/project/actions/runs/123",
                "displayTitle": f"gate-full {attempt.id} {candidate.commit}",
            }),
            "",
        )

    monkeypatch.setattr(executor, "_gh", gh)
    assert executor.inspect(attempt, candidate).state == "stopped"


def test_local_scheduled_process_exit_without_runner_receipt_is_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = gate_executors.LocalGateExecutor(tmp_path)
    attempt, _ = GateTaskStore(tmp_path).reserve("candidate", "local")
    candidate = GateCandidate("a" * 40, "b" * 40, "c" * 40, "d" * 64, "gate-full-v1")
    config = tmp_path / ".auto-pm/reports/gate-tasks" / attempt.id / "task.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}", encoding="utf-8")
    payload = {"runner_alive": False, "scheduler_state": "Ready", "scheduler_exit": 4, "scheduler_started": True}
    monkeypatch.setattr(executor, "_runner", lambda *args: subprocess.CompletedProcess(args, 0, json.dumps(payload), ""))
    assert executor.inspect(attempt, candidate).state == "failed"
