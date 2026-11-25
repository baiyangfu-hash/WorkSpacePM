import json
import subprocess
from pathlib import Path

import pytest

from auto_pm.application.core import gate_task_service
from auto_pm.application.core.gate_task_service import GateCandidate
from auto_pm.infrastructure.gate_task_store import GateTaskStore


def test_github_only_falls_back_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = gate_task_service.GitHubGateExecutor(tmp_path)
    monkeypatch.setattr(executor, "_repo", lambda: "example/project")
    attempt, _ = GateTaskStore(tmp_path).reserve("candidate", "github")
    candidate = GateCandidate("a" * 40, "b" * 40, "c" * 40, "d" * 64, "gate-full-v1")

    def unavailable(root: Path, argv: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr(gate_task_service, "run_command", unavailable)
    assert executor.launch(attempt, candidate).state == "unavailable"


def test_local_checks_for_real_plugin_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = gate_task_service.LocalGateExecutor(tmp_path)
    attempt, _ = GateTaskStore(tmp_path).reserve("candidate", "local")
    candidate = GateCandidate("a" * 40, "b" * 40, "c" * 40, "d" * 64, "gate-full-v1")
    monkeypatch.setattr(gate_task_service, "sha256_file", lambda path: None)
    result = executor.launch(attempt, candidate)
    assert result.state == "unavailable"
    assert "Siemens" in result.detail or "Windows" in result.detail
    assert not (tmp_path / ".auto-pm/reports/gate-tasks" / attempt.id).exists()


def test_github_service_outage_allows_offline_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = gate_task_service.GitHubGateExecutor(tmp_path)
    monkeypatch.setattr(executor, "_repo", lambda: "example/project")
    attempt, _ = GateTaskStore(tmp_path).reserve("candidate", "github")
    candidate = GateCandidate("a" * 40, "b" * 40, "c" * 40, "d" * 64, "gate-full-v1")
    calls: list[list[str]] = []

    def outage(root: Path, argv: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, "", "HTTP 503: Service Unavailable")

    monkeypatch.setattr(gate_task_service, "run_command", outage)
    assert executor.launch(attempt, candidate).state == "unavailable"
    assert len(calls) == 1 and calls[0][1] == "api"


def test_known_github_run_is_reconciled_by_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executor = gate_task_service.GitHubGateExecutor(tmp_path)
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
    executor = gate_task_service.LocalGateExecutor(tmp_path)
    attempt, _ = GateTaskStore(tmp_path).reserve("candidate", "local")
    candidate = GateCandidate("a" * 40, "b" * 40, "c" * 40, "d" * 64, "gate-full-v1")
    config = tmp_path / ".auto-pm/reports/gate-tasks" / attempt.id / "task.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}", encoding="utf-8")
    payload = {"runner_alive": False, "scheduler_state": "Ready", "scheduler_exit": 4, "scheduler_started": True}
    monkeypatch.setattr(executor, "_runner", lambda *args: subprocess.CompletedProcess(args, 0, json.dumps(payload), ""))
    assert executor.inspect(attempt, candidate).state == "failed"


def test_github_l2_dispatch_and_receipt_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import base64
    import hashlib

    executor = gate_task_service.GitHubGateExecutor(tmp_path)
    monkeypatch.setattr(executor, "_repo", lambda: "example/project")
    l2 = GateCandidate("a" * 40, "b" * 40, "c" * 40, "d" * 64, "gate-l2-v1", tier="L2", groups=("application",))
    attempt, _ = GateTaskStore(tmp_path).reserve(l2.key, "github")

    # 1) launch fails clearly when main workflow lacks requested_tier input
    old_wf = base64.b64encode(b"      task_id:\n      candidate_sha:\n      base_sha:\n").decode("ascii")

    def fake_api_old(_root: Path, argv: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
        target = argv[2] if len(argv) > 2 else ""
        if target.endswith("/branches/main"):
            return subprocess.CompletedProcess(argv, 0, l2.base, "")
        if "/git/commits/" in target:
            return subprocess.CompletedProcess(argv, 0, l2.tree, "")
        return subprocess.CompletedProcess(argv, 0, old_wf, "")

    monkeypatch.setattr(gate_task_service, "run_command", fake_api_old)
    old_res = executor.launch(attempt, l2)
    assert old_res.state == "failed" and "L2" in old_res.detail

    # 2) launch passes requested_tier=L2 when supported, and omits requested_tier for L3
    new_wf = base64.b64encode(
        b"      task_id:\n      candidate_sha:\n      base_sha:\n      requested_tier:\n"
    ).decode("ascii")
    monkeypatch.setattr(
        gate_task_service,
        "run_command",
        lambda _root, argv, timeout=30: (
            subprocess.CompletedProcess(argv, 0, l2.base, "")
            if len(argv) > 2 and argv[2].endswith("/branches/main")
            else subprocess.CompletedProcess(argv, 0, l2.tree, "")
            if len(argv) > 2 and "/git/commits/" in argv[2]
            else subprocess.CompletedProcess(argv, 0, new_wf, "")
        ),
    )
    dispatches: list[tuple[str, ...]] = []

    def fake_gh(*args: str) -> subprocess.CompletedProcess[str]:
        dispatches.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(executor, "_gh", fake_gh)
    assert executor.launch(attempt, l2).state == "queued"
    assert "requested_tier=L2" in dispatches[-1]

    l3 = l2.as_full()
    assert executor.launch(attempt, l3).state == "queued"
    assert not any(arg.startswith("requested_tier=") for arg in dispatches[-1])

    # 3) _receipt verifies gate-verdict-l2-<sha12> + gate-l2 commit status and rejects incomplete L2
    verdict_payload = {
        "schema": "gate-run.v1",
        "tier": "L2",
        "verdict": "PASS",
        "commit": l2.commit,
        "commit_end": l2.commit,
        "complete": False,
        "manifest_sha256": l2.manifest,
        "expected_groups": ["application"],
        "reasons": [],
        "results": {"application": {"exit": 0, "verdict": "PASS"}},
    }
    verdict_bytes = json.dumps(verdict_payload).encode("utf-8")
    digest = hashlib.sha256(verdict_bytes).hexdigest()
    run_url = "https://github.com/example/project/actions/runs/987"

    def dl_gh(*args: str) -> subprocess.CompletedProcess[str]:
        assert args[0] == "run" and args[1] == "download"
        assert f"gate-verdict-l2-{l2.commit[:12]}" in args
        dest = Path(args[args.index("--dir") + 1]) / "gate_summary.json"
        dest.write_bytes(verdict_bytes)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(executor, "_gh", dl_gh)
    statuses = [[{
        "context": "gate-l2",
        "state": "success",
        "target_url": run_url,
        "description": f"PASS: verdict PASS tier L2 sha256 {digest}, plugin skipped",
        "creator": {"login": "github-actions[bot]"},
    }]]
    monkeypatch.setattr(
        gate_task_service,
        "run_command",
        lambda _root, argv, timeout=30: subprocess.CompletedProcess(argv, 0, json.dumps(statuses), ""),
    )
    ok_obs = executor._receipt("987", l2, run_url)
    assert ok_obs.state == "passed" and '"tier": "L2"' in ok_obs.detail

    # Wrong expected_groups in candidate fails receipt check
    wrong_group = GateCandidate("a" * 40, "b" * 40, "c" * 40, "d" * 64, "gate-l2-v1", tier="L2", groups=("application", "cli"))
    assert executor._receipt("987", wrong_group, run_url).state == "failed"


def test_local_executor_rejects_l2_candidate(tmp_path: Path) -> None:
    executor = gate_task_service.LocalGateExecutor(tmp_path)
    l2 = GateCandidate("a" * 40, "b" * 40, "c" * 40, "d" * 64, "gate-l2-v1", tier="L2", groups=("application",))
    attempt, _ = GateTaskStore(tmp_path).reserve(l2.key, "local")
    res = executor.launch(attempt, l2)
    assert res.state == "failed" and "L3" in res.detail
