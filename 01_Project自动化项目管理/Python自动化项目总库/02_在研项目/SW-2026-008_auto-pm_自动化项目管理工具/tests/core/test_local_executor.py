"""Subprocess-backed safety tests for the standalone local Codex executor."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from auto_pm.infrastructure.local_executor import (
    ISOLATION_MARKER,
    ISOLATION_SCHEMA_VERSION,
    LocalCodexExecutor,
    LocalExecutionError,
    LocalExecutionHandle,
    LocalExecutionRequest,
    LocalExecutionStatus,
    LocalHandshakeStatus,
)

SECRET = "unit-secret-value"


def _git(repository: Path, *arguments: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _microtask_repository(tmp_path: Path, *, marked: bool = True) -> Path:
    repository = tmp_path / ("marked-microtask" if marked else "ordinary-repository")
    repository.mkdir()
    (repository / "allowed.txt").write_text("baseline\n", encoding="utf-8")
    if marked:
        (repository / ISOLATION_MARKER).write_text(
            json.dumps({"schema_version": ISOLATION_SCHEMA_VERSION}),
            encoding="utf-8",
        )
    _git(repository, "init")
    _git(repository, "add", ".")
    _git(
        repository,
        "-c",
        "user.name=Local Executor Test",
        "-c",
        "user.email=local-executor@example.invalid",
        "commit",
        "-m",
        "baseline",
    )
    return repository


def _helper(tmp_path: Path) -> Path:
    path = tmp_path / "innocuous_codex_helper.py"
    path.write_text(
        """from __future__ import annotations

import os
import sys
import time
from pathlib import Path

arguments = sys.argv[1:]
if arguments[:2] != ["exec", "--ephemeral"]:
    raise SystemExit(11)
if arguments[arguments.index("-m") + 1] != "gpt-5.6-terra":
    raise SystemExit(12)
if arguments[arguments.index("--sandbox") + 1] != "workspace-write":
    raise SystemExit(13)
if "--json" not in arguments:
    raise SystemExit(14)

repository = Path(arguments[arguments.index("-C") + 1])
prompt = arguments[-1]
if "environment" in prompt and os.environ.get("AUTO_PM_TEST_LEASE"):
    raise SystemExit(19)
if "timeout" in prompt:
    time.sleep(5)
(repository / "allowed.txt").write_text("changed\\n", encoding="utf-8")
if "scope" in prompt:
    (repository / "outside.txt").write_text("outside\\n", encoding="utf-8")
if "invalid" in prompt:
    print('{"type":"thread.started","session_id":"forged-session"}')
    time.sleep(5)
    raise SystemExit(0)
if "controlless" in prompt:
    print('{"thread_id":"model-like-json"}')
    raise SystemExit(0)
if "secret" in prompt:
    print("token=unit-secret-value")
    print('"secret": "unit-secret-value"', file=sys.stderr)
    print("Authorization: Bearer unit-secret-value", file=sys.stderr)
print('{"type":"thread.started","thread_id":"helper-session-1"}')
if "after-start" in prompt:
    time.sleep(0.5)
if "nonzero" in prompt:
    raise SystemExit(7)
""",
        encoding="utf-8",
    )
    return path


def _request(repository: Path, prompt: str = "write allowed") -> LocalExecutionRequest:
    return LocalExecutionRequest(
        repository=repository,
        allowed_paths=("allowed.txt",),
        model="gpt-5.6-terra",
        prompt=prompt,
        timeout_seconds=2,
        output_limit_bytes=4_096,
        sensitive_values=(SECRET,),
    )


def test_executes_real_helper_with_safe_command_identity_and_redacted_output(tmp_path: Path) -> None:
    repository = _microtask_repository(tmp_path)
    helper = _helper(tmp_path)

    result = LocalCodexExecutor(command_prefix=(sys.executable, str(helper))).execute(
        _request(repository, "write allowed secret")
    )

    assert result.status is LocalExecutionStatus.SUCCEEDED
    assert result.succeeded is True
    assert result.started is True
    assert result.process_id is not None
    assert result.started_at is not None
    assert result.exit_code == 0
    assert result.requested_model == "gpt-5.6-terra"
    assert result.session_id == "helper-session-1"
    assert result.changed_paths == ("allowed.txt",)
    assert result.scope_violations == ()
    assert result.command[-10:] == (
        "exec",
        "--ephemeral",
        "-m",
        "gpt-5.6-terra",
        "-C",
        str(repository.resolve()),
        "--sandbox",
        "workspace-write",
        "--json",
        "<redacted prompt>",
    )
    assert "--dangerously-bypass-approvals-and-sandbox" not in result.command
    assert SECRET not in result.stdout
    assert SECRET not in result.stderr
    assert SECRET not in repr(result)


def test_child_environment_excludes_one_time_lease_capability(
    tmp_path: Path, monkeypatch
) -> None:
    repository = _microtask_repository(tmp_path)
    helper = _helper(tmp_path)
    monkeypatch.setenv("AUTO_PM_TEST_LEASE", SECRET)
    request = LocalExecutionRequest(
        **{
            **_request(repository, "write allowed environment").__dict__,
            "excluded_environment_keys": ("AUTO_PM_TEST_LEASE",),
        }
    )

    result = LocalCodexExecutor(command_prefix=(sys.executable, str(helper))).execute(request)

    assert result.status is LocalExecutionStatus.SUCCEEDED
    assert result.exit_code == 0


def test_start_handshake_wait_is_nonblocking_and_binds_current_process(tmp_path: Path) -> None:
    repository = _microtask_repository(tmp_path)
    helper = _helper(tmp_path)
    executor = LocalCodexExecutor(command_prefix=(sys.executable, str(helper)))

    handle = executor.start(_request(repository, "write allowed after-start"))

    assert isinstance(handle, LocalExecutionHandle)
    handshake = executor.handshake(handle, timeout_seconds=1)
    assert handshake.status is LocalHandshakeStatus.STARTED
    assert handshake.evidence is not None
    assert handshake.evidence.process_id == handle.process_id
    assert handshake.evidence.session_id == "helper-session-1"
    assert handshake.evidence.started_at.tzinfo is not None

    result = executor.wait(handle, evidence=handshake.evidence)
    assert result.status is LocalExecutionStatus.SUCCEEDED
    assert result.session_id == handshake.evidence.session_id
    assert result.started_at == handshake.evidence.started_at


@pytest.mark.parametrize("prompt", ["write allowed invalid", "write allowed controlless"])
def test_invalid_or_noncanonical_startup_events_reap_the_current_child(
    tmp_path: Path,
    prompt: str,
) -> None:
    repository = _microtask_repository(tmp_path)
    helper = _helper(tmp_path)
    executor = LocalCodexExecutor(command_prefix=(sys.executable, str(helper)))

    handle = executor.start(_request(repository, prompt))

    assert isinstance(handle, LocalExecutionHandle)
    handshake = executor.handshake(handle, timeout_seconds=0.2)
    assert handshake.status in {LocalHandshakeStatus.INVALID, LocalHandshakeStatus.PROCESS_EXITED, LocalHandshakeStatus.TIMED_OUT}
    assert handshake.evidence is None
    assert handle._active.process.poll() is not None

    result = executor.wait(handle, force_status=LocalExecutionStatus.FAILED, error=handshake.error)
    assert result.status is LocalExecutionStatus.FAILED
    assert result.session_id is None
    assert result.started_at is None


def test_reports_real_scope_violation_without_erasing_process_facts(tmp_path: Path) -> None:
    repository = _microtask_repository(tmp_path)
    helper = _helper(tmp_path)

    result = LocalCodexExecutor(command_prefix=(sys.executable, str(helper))).execute(
        _request(repository, "write allowed scope secret")
    )

    assert result.status is LocalExecutionStatus.SCOPE_VIOLATION
    assert result.succeeded is False
    assert result.started is True
    assert result.process_id is not None
    assert result.exit_code == 0
    assert result.changed_paths == ("allowed.txt", "outside.txt")
    assert result.scope_violations == ("outside.txt",)
    assert SECRET not in result.stdout
    assert SECRET not in result.stderr


def test_rejects_non_git_non_isolated_dirty_and_path_escape_before_process_start(
    tmp_path: Path,
) -> None:
    helper = _helper(tmp_path)
    executor = LocalCodexExecutor(command_prefix=(sys.executable, str(helper)))
    non_git = tmp_path / "not-a-repository"
    non_git.mkdir()

    with pytest.raises(LocalExecutionError, match="standalone .git"):
        executor.execute(_request(non_git))

    ordinary = _microtask_repository(tmp_path, marked=False)
    with pytest.raises(LocalExecutionError, match="isolation marker"):
        executor.execute(_request(ordinary))

    microtask = _microtask_repository(tmp_path)
    with pytest.raises(LocalExecutionError, match="escapes"):
        executor.execute(
            LocalExecutionRequest(
                repository=microtask,
                allowed_paths=("../outside.txt",),
                model="gpt-5.6-terra",
                prompt="write allowed",
            )
        )

    (microtask / "forbidden-before-start.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(LocalExecutionError, match="must be clean"):
        executor.execute(_request(microtask))
    assert (microtask / "allowed.txt").read_text(encoding="utf-8") == "baseline\n"


def test_never_claims_process_started_when_executable_cannot_launch(tmp_path: Path) -> None:
    repository = _microtask_repository(tmp_path)
    executor = LocalCodexExecutor(command_prefix=("missing-local-codex-command.exe",))

    result = executor.execute(_request(repository))

    assert result.status is LocalExecutionStatus.NOT_STARTED
    assert result.succeeded is False
    assert result.started is False
    assert result.process_id is None
    assert result.exit_code is None
    assert result.changed_paths == ()


def test_timeout_is_bounded_and_preserves_a_truthful_non_success_outcome(tmp_path: Path) -> None:
    repository = _microtask_repository(tmp_path)
    helper = _helper(tmp_path)
    request = _request(repository, "timeout")
    request = LocalExecutionRequest(
        repository=request.repository,
        allowed_paths=request.allowed_paths,
        model=request.model,
        prompt=request.prompt,
        timeout_seconds=1,
        output_limit_bytes=request.output_limit_bytes,
        sensitive_values=request.sensitive_values,
    )

    result = LocalCodexExecutor(command_prefix=(sys.executable, str(helper))).execute(request)

    assert result.status is LocalExecutionStatus.TIMED_OUT
    assert result.succeeded is False
    assert result.started is True
    assert result.timed_out is True
    assert result.exit_code is not None
    assert result.changed_paths == ()
