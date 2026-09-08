"""handoff.v1 CLI 的请求、回执和 PM 消费测试。"""

from __future__ import annotations

import json
from pathlib import Path

from auto_pm.cli.__main__ import cli
from auto_pm.core.ai_handoff_service import AiHandoffService
from click.testing import CliRunner


def test_handoff_cli_create_list_show(tmp_path: Path) -> None:
    runner = CliRunner()
    create = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "create",
            "--pid",
            "SW-2026-008",
            "--to",
            "fullstack-engineer",
            "--summary",
            "执行 cockpit CLI 适配",
            "--mode",
            "grooming",
            "--request-id",
            "AI-20260901-CLI",
            "--json-output",
        ],
    )
    assert create.exit_code == 0, create.output
    payload = json.loads(create.output)
    assert payload["schema_version"] == "handoff.v1"

    listed = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "list",
            "--pid",
            "SW-2026-008",
            "--json-output",
        ],
    )
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)[0]["request_id"] == "AI-20260901-CLI"

    shown = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "show",
            "AI-20260901-CLI",
            "--json-output",
        ],
    )
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.output)["status"] == "pending"


def test_handoff_cli_close_result_file_and_legacy_pid_resolution(tmp_path: Path) -> None:
    runner = CliRunner()
    created = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "create",
            "--pid",
            "SW-2026-008",
            "--to",
            "plc-electrical-engineer",
            "--summary",
            "执行 PLC 静态检查",
            "--request-id",
            "AI-20260901-CLI-CLOSE",
        ],
    )
    assert created.exit_code == 0, created.output

    result_file = tmp_path / "handoff_result.json"
    (tmp_path / "CHG-PLC-2026-001.md").write_text("# CHG-PLC-2026-001\n", encoding="utf-8")
    result_file.write_text(
        json.dumps(
            {
                "summary": "PLC 静态检查通过",
                "verification": {
                    "lint_result": "auto-pm plc check PASS",
                    "test_result": "pytest PASS",
                },
                "changed_files": ["DJ-2026-005/TEC.md"],
                "chg_updates": ["CHG-PLC-2026-001: verified"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    closed = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "close",
            "--pid",
            "SW-2026-008",
            "--result-file",
            str(result_file),
            "--json-output",
        ],
    )
    assert closed.exit_code == 0, closed.output
    assert json.loads(closed.output)["status"] == "consumed"

    retry = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "close",
            "AI-20260901-CLI-CLOSE",
            "--result-file",
            str(result_file),
            "--json-output",
        ],
    )
    assert retry.exit_code == 0, retry.output


def test_handoff_cli_close_rejects_missing_evidence(tmp_path: Path) -> None:
    runner = CliRunner()
    created = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "create",
            "--pid",
            "SW-2026-008",
            "--to",
            "fullstack-engineer",
            "--summary",
            "必须有验证证据",
            "--request-id",
            "AI-20260901-CLI-FAIL",
        ],
    )
    assert created.exit_code == 0, created.output

    closed = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "close",
            "AI-20260901-CLI-FAIL",
        ],
    )
    assert closed.exit_code == 1
    assert "验证证据" in closed.output


def test_handoff_cli_preflight_does_not_consume(tmp_path: Path) -> None:
    runner = CliRunner()
    created = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "create",
            "--pid",
            "SW-2026-008",
            "--to",
            "fullstack-engineer",
            "--summary",
            "预检不应改变状态",
            "--request-id",
            "AI-20260901-CLI-PREFLIGHT",
        ],
    )
    assert created.exit_code == 0, created.output

    result_file = tmp_path / "preflight.json"
    result_file.write_text(
        json.dumps({"verification": {"other_checks": ["preflight PASS"]}}),
        encoding="utf-8",
    )
    preflight = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "preflight",
            "AI-20260901-CLI-PREFLIGHT",
            "--result-file",
            str(result_file),
            "--pid",
            "SW-2026-008",
            "--json-output",
        ],
    )
    assert preflight.exit_code == 0, preflight.output
    assert json.loads(preflight.output)["already_consumed"] is False

    shown = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "show",
            "AI-20260901-CLI-PREFLIGHT",
            "--json-output",
        ],
    )
    assert json.loads(shown.output)["status"] == "pending"


def test_handoff_queue_snapshot_is_read_only_and_aggregates_statuses(tmp_path: Path) -> None:
    runner = CliRunner()
    for request_id, summary in (
        ("AI-20260902-QUEUE-PENDING", "保留待处理请求"),
        ("AI-20260902-QUEUE-CONSUMED", "完成可统计请求"),
    ):
        created = runner.invoke(
            cli,
            [
                "-w",
                str(tmp_path),
                "handoff",
                "create",
                "--pid",
                "SW-2026-008",
                "--to",
                "fullstack-engineer",
                "--summary",
                summary,
                "--request-id",
                request_id,
            ],
        )
        assert created.exit_code == 0, created.output

    closed = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "close",
            "AI-20260902-QUEUE-CONSUMED",
            "--summary",
            "完成只读队列统计",
            "--other-check",
            "queue snapshot PASS",
        ],
    )
    assert closed.exit_code == 0, closed.output

    queue = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "queue",
            "--pid",
            "SW-2026-008",
            "--limit",
            "1",
            "--json-output",
        ],
    )
    assert queue.exit_code == 0, queue.output
    payload = json.loads(queue.output)
    assert payload["schema_version"] == "handoff.queue.v1"
    assert payload["read_only"] is True
    assert payload["total"] == 2
    assert payload["status_counts"] == {
        "pending": 1,
        "claimed": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
        "expired": 0,
        "consumed": 1,
    }
    assert payload["lifecycle_state_counts"] == {"awaiting_pickup": 1, "consumed": 1}
    assert len(payload["latest"]) == 1

    shown = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "show",
            "AI-20260902-QUEUE-PENDING",
            "--json-output",
        ],
    )
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.output)["status"] == "pending"

    service = AiHandoffService(tmp_path)
    snapshot = service.queue_snapshot("SW-2026-008")
    assert snapshot["status_counts"]["pending"] == 1


def test_handoff_cli_execution_lifecycle_requires_lease_owner(tmp_path: Path) -> None:
    runner = CliRunner()
    request_id = "AI-20260903-LIFECYCLE"
    created = runner.invoke(
        cli,
        [
            "-w", str(tmp_path), "handoff", "create", "--pid", "SW-2026-008",
            "--to", "fullstack-engineer", "--summary", "执行生命周期", "--request-id", request_id,
        ],
    )
    assert created.exit_code == 0, created.output

    claimed = runner.invoke(
        cli,
        ["-w", str(tmp_path), "handoff", "claim", request_id, "--executor-id", "codex-worker"],
    )
    assert claimed.exit_code == 0, claimed.output

    rejected = runner.invoke(
        cli,
        ["-w", str(tmp_path), "handoff", "start", request_id, "--executor-id", "other-worker"],
    )
    assert rejected.exit_code == 1
    assert "租约持有者" in rejected.output

    started = runner.invoke(
        cli,
        ["-w", str(tmp_path), "handoff", "start", request_id, "--executor-id", "codex-worker"],
    )
    assert started.exit_code == 0, started.output

    result_file = tmp_path / "handoff-result.json"
    result_file.write_text(
        json.dumps({"summary": "完成", "verification": {"test_result": "1 passed"}}),
        encoding="utf-8",
    )
    submitted = runner.invoke(
        cli,
        [
            "-w", str(tmp_path), "handoff", "result-submit", request_id,
            "--executor-id", "codex-worker", "--result-file", str(result_file), "--json-output",
        ],
    )
    assert submitted.exit_code == 0, submitted.output
    assert json.loads(submitted.output)["status"] == "completed"
    queue = runner.invoke(
        cli,
        ["-w", str(tmp_path), "handoff", "queue", "--pid", "SW-2026-008", "--json-output"],
    )
    assert queue.exit_code == 0, queue.output
    assert json.loads(queue.output)["total"] == 1


def test_handoff_cli_requeue_requires_pm_reason_and_preserves_history(tmp_path: Path) -> None:
    runner = CliRunner()
    request_id = "AI-20260903-REQUEUE"
    created = runner.invoke(
        cli,
        [
            "-w", str(tmp_path), "handoff", "create", "--pid", "SW-2026-008",
            "--to", "fullstack-engineer", "--summary", "重新派发测试", "--request-id", request_id,
        ],
    )
    assert created.exit_code == 0, created.output
    claimed = runner.invoke(
        cli,
        [
            "-w", str(tmp_path), "handoff", "claim", request_id, "--executor-id", "offline-worker",
            "--lease-seconds", "60",
        ],
    )
    assert claimed.exit_code == 0, claimed.output

    service = AiHandoffService(tmp_path)
    request = service.get_request(request_id)
    assert request is not None
    request["status"] = "expired"
    service._write_atomic(service._find_request_path(request_id), request)

    requeued = runner.invoke(
        cli,
        [
            "-w", str(tmp_path), "handoff", "requeue", request_id, "--pm-id", "pm-workflow",
            "--reason", "executor lease expired", "--json-output",
        ],
    )
    assert requeued.exit_code == 0, requeued.output
    payload = json.loads(requeued.output)
    assert payload["status"] == "pending"
    assert payload["dispatch"]["state"] == "awaiting_pickup"
    assert payload["execution"]["requeue_history"][-1]["pm_id"] == "pm-workflow"


    rejected = runner.invoke(
        cli,
        [
            "-w", str(tmp_path), "handoff", "requeue", request_id, "--pm-id", "pm-workflow",
            "--reason", "should reject active pending request",
        ],
    )
    assert rejected.exit_code == 1
    assert "仅允许重新派发" in rejected.output


def test_handoff_cli_execution_requires_decision_id(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "handoff",
            "create",
            "--pid",
            "SW-2026-008",
            "--to",
            "fullstack-engineer",
            "--summary",
            "execution without approval",
            "--mode",
            "execution",
        ],
    )
    assert result.exit_code == 1
    assert "必须绑定 decision_id" in result.output
