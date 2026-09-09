"""CLI coverage for platform-neutral continuity v2."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from auto_pm.cli.__main__ import cli
from click.testing import CliRunner, Result


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repository(root: Path) -> None:
    _git(root, "init")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(
        root,
        "-c",
        "user.name=Continuity Test",
        "-c",
        "user.email=continuity@example.invalid",
        "commit",
        "-m",
        "baseline",
    )


def _invoke(runner: CliRunner, root: Path, args: list[str]) -> Result:
    return runner.invoke(cli, ["-w", str(root), "continuity", *args], catch_exceptions=False)


def test_continuity_cli_runs_checkpoint_and_handoff_v2(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _repository(tmp_path)
    created = _invoke(
        cli_runner,
        tmp_path,
        [
            "work", "create", "--work-id", "WORK-CLI-001", "--pid", "SW-TEST-001",
            "--kind", "TEST", "--title", "CLI continuity", "--owner", "agent-a",
            "--scope", "README.md", "--idempotency-key", "work-create", "--read-only",
        ],
    )
    assert created.exit_code == 0
    assert json.loads(created.output)["state"] == "READY"

    started = _invoke(
        cli_runner,
        tmp_path,
        [
            "run", "start", "--run-id", "RUN-CLI-001", "--work-id", "WORK-CLI-001",
            "--executor", "agent-a", "--adapter", "codex", "--owned", "README.md",
            "--declared-dirty", "README.md", "--lease-token", "lease-a",
            "--lease-seconds", "900", "--idempotency-key", "run-start",
        ],
    )
    assert started.exit_code == 0
    assert json.loads(started.output)["state"] == "RUNNING"

    (tmp_path / "README.md").write_text("changed\n", encoding="utf-8")
    checkpoint = _invoke(
        cli_runner,
        tmp_path,
        [
            "checkpoint", "create", "--checkpoint-id", "CP-CLI-001", "--run-id", "RUN-CLI-001",
            "--owner", "agent-a", "--lease-token", "lease-a", "--summary", "changed readme",
            "--evidence", "pytest:0", "--idempotency-key", "checkpoint-create",
        ],
    )
    assert checkpoint.exit_code == 0
    assert json.loads(checkpoint.output)["dirty_paths"] == ["README.md"]

    handoff = _invoke(
        cli_runner,
        tmp_path,
        [
            "handoff", "create", "--handoff-id", "HO-CLI-001", "--checkpoint-id", "CP-CLI-001",
            "--from-owner", "agent-a", "--to-owner", "agent-b", "--lease-token", "lease-a",
            "--idempotency-key", "handoff-create",
        ],
    )
    assert handoff.exit_code == 0
    assert json.loads(handoff.output)["schema_version"] == "handoff.v2"

    accepted = _invoke(
        cli_runner,
        tmp_path,
        [
            "handoff", "accept", "--handoff-id", "HO-CLI-001", "--receiver", "agent-b",
            "--new-lease-token", "lease-b", "--lease-seconds", "900",
            "--idempotency-key", "handoff-accept",
        ],
    )
    assert accepted.exit_code == 0
    assert json.loads(accepted.output)["owner_id"] == "agent-b"


def test_run_start_rejects_physically_dirty_undeclared_owned_path(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _repository(tmp_path)
    created = _invoke(
        cli_runner,
        tmp_path,
        [
            "work", "create", "--work-id", "WORK-CLI-002", "--pid", "SW-TEST-001",
            "--kind", "TEST", "--title", "Dirty gate", "--owner", "agent-a",
            "--scope", "README.md", "--idempotency-key", "work-create", "--read-only",
        ],
    )
    assert created.exit_code == 0
    (tmp_path / "README.md").write_text("dirty\n", encoding="utf-8")

    started = _invoke(
        cli_runner,
        tmp_path,
        [
            "run", "start", "--run-id", "RUN-CLI-002", "--work-id", "WORK-CLI-002",
            "--executor", "agent-a", "--adapter", "codex", "--owned", "README.md",
            "--lease-token", "lease-a", "--lease-seconds", "900",
            "--idempotency-key", "run-start",
        ],
    )
    assert started.exit_code == 1
    assert "未声明" in started.output
