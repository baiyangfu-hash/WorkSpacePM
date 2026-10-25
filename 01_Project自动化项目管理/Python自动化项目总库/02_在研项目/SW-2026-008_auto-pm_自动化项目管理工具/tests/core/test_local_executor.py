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
prompt = sys.stdin.buffer.read().decode("utf-8") if arguments[-1] == "-" else arguments[-1]
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
        "-",
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


def test_bare_command_name_is_resolved_through_path_so_windows_finds_the_cmd_shim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TD-SW008-185: Popen without a shell cannot find ``codex.cmd`` from the bare name ``codex``.
    from auto_pm.infrastructure import local_executor

    shim = str(Path("C:/tools/npm/codex.cmd"))
    monkeypatch.setattr(local_executor.shutil, "which", lambda name: shim if name == "codex" else None)

    assert LocalCodexExecutor()._command_prefix == (shim,)
    # A name PATH does not know, and any name that already carries a path, are left exactly as given.
    assert LocalCodexExecutor(command_prefix=("unknown-tool", "--x"))._command_prefix == ("unknown-tool", "--x")
    explicit = str(Path("/opt/codex"))
    assert LocalCodexExecutor(command_prefix=(explicit, "exec"))._command_prefix == (explicit, "exec")


# TD-SW008-185: the prompt is free text, so it travels over stdin (`codex exec -`), never on the command line where a
# .cmd/.bat launcher (the npm shim codex.cmd) would have cmd.exe parse it again.  The arguments that remain can come
# from the caller (model name, repository path); a .cmd/.bat launcher refuses cmd.exe metacharacters in them.
CMD_METACHARACTERS = ['"', "&", "%", "|", "<", ">", "^", "\n", "\r"]
HOSTILE_PROMPT = '修改 "allowed.txt" & echo 100% | type <nul > x ^ y\n第二行：中文、引号"和%PATH%'


def _prompt_echo_helper(tmp_path: Path) -> Path:
    path = tmp_path / "prompt_echo_helper.py"
    path.write_text(
        """from __future__ import annotations

import sys
from pathlib import Path

arguments = sys.argv[1:]
repository = Path(arguments[arguments.index("-C") + 1])
received = sys.stdin.buffer.read()
(repository / "allowed.txt").write_bytes(received)
print('{"type":"thread.started","thread_id":"echo-session"}')
""",
        encoding="utf-8",
    )
    return path


def test_prompt_reaches_the_child_over_stdin_intact_and_is_not_on_the_command_line(tmp_path: Path) -> None:
    repository = _microtask_repository(tmp_path)
    helper = _prompt_echo_helper(tmp_path)

    result = LocalCodexExecutor(command_prefix=(sys.executable, str(helper))).execute(
        _request(repository, HOSTILE_PROMPT)
    )

    assert result.status is LocalExecutionStatus.SUCCEEDED, result.error
    assert (repository / "allowed.txt").read_bytes() == HOSTILE_PROMPT.encode("utf-8")
    assert result.command[-1] == "-"
    assert not any("echo 100%" in argument or "allowed.txt\"" in argument for argument in result.command)


def test_a_child_that_never_reads_stdin_does_not_block_the_caller(tmp_path: Path) -> None:
    repository = _microtask_repository(tmp_path)
    helper = tmp_path / "deaf_helper.py"
    helper.write_text(
        'import sys\nprint(\'{"type":"thread.started","thread_id":"deaf"}\')\n', encoding="utf-8"
    )

    result = LocalCodexExecutor(command_prefix=(sys.executable, str(helper))).execute(
        _request(repository, "x" * 2_000_000)
    )

    assert result.started is True
    assert result.status is not LocalExecutionStatus.NOT_STARTED


@pytest.mark.parametrize("launcher", ["codex.cmd", "codex.bat", "CODEX.CMD"])
@pytest.mark.parametrize("character", CMD_METACHARACTERS)
def test_batch_launcher_accepts_any_prompt_because_it_is_not_on_the_command_line(
    tmp_path: Path, launcher: str, character: str
) -> None:
    repository = _microtask_repository(tmp_path)
    executor = LocalCodexExecutor(command_prefix=(launcher,))

    executor.validate(_request(repository, prompt=f"write allowed {character} calc.exe"))


@pytest.mark.parametrize("launcher", ["codex.cmd", "codex.bat", "CODEX.CMD"])
@pytest.mark.parametrize("character", CMD_METACHARACTERS)
def test_batch_launcher_refuses_cmd_metacharacters_in_the_model_name(
    tmp_path: Path, launcher: str, character: str
) -> None:
    repository = _microtask_repository(tmp_path)
    executor = LocalCodexExecutor(command_prefix=(launcher,))
    request = LocalExecutionRequest(
        repository=repository,
        allowed_paths=("allowed.txt",),
        model=f"gpt{character}calc",
        prompt="write allowed",
    )

    with pytest.raises(LocalExecutionError, match=r"argument \d+ contains cmd.exe metacharacters"):
        executor.validate(request)
    with pytest.raises(LocalExecutionError, match="cmd.exe metacharacters"):
        executor.start(request)


def test_batch_launcher_refuses_metacharacters_in_the_repository_path(tmp_path: Path) -> None:
    parent = tmp_path / "a&b"
    parent.mkdir()
    repository = _microtask_repository(parent)
    executor = LocalCodexExecutor(command_prefix=("codex.cmd",))

    with pytest.raises(LocalExecutionError, match="cmd.exe metacharacters"):
        executor.validate(_request(repository))


def test_batch_launcher_accepts_plain_arguments(tmp_path: Path) -> None:
    repository = _microtask_repository(tmp_path)

    LocalCodexExecutor(command_prefix=("codex.cmd",)).validate(_request(repository))


@pytest.mark.parametrize("character", CMD_METACHARACTERS)
def test_exe_launcher_is_not_affected_by_cmd_metacharacters(tmp_path: Path, character: str) -> None:
    repository = _microtask_repository(tmp_path)
    request = LocalExecutionRequest(
        repository=repository,
        allowed_paths=("allowed.txt",),
        model=f"gpt{character}calc",
        prompt="write allowed",
    )

    LocalCodexExecutor(command_prefix=("codex.exe",)).validate(request)
