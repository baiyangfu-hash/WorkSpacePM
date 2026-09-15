"""Run a bounded local Codex process only inside a marked microtask repository.

This module deliberately has no Continuity or provider-dispatch side effects.  A
caller must first create and commit an explicitly marked, standalone Git
repository; the executor only starts ``codex exec`` after proving that boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import subprocess
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import IO, Any

from auto_pm.contracts.execution_adapter import ExecutionStartEvidence

ISOLATION_MARKER = ".codex-microtask.json"
ISOLATION_SCHEMA_VERSION = "local-codex-microtask.v1"
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_OUTPUT_LIMIT_BYTES = 64 * 1024
MAX_TIMEOUT_SECONDS = 600.0
MAX_OUTPUT_LIMIT_BYTES = 1024 * 1024
MAX_SNAPSHOT_FILES = 1_024
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024

_GIT_TIMEOUT_SECONDS = 15.0
_TERMINATE_GRACE_SECONDS = 5.0
_OUTPUT_CHUNK_BYTES = 8 * 1024
_ASSIGNMENT_SECRET = re.compile(
    r"(?i)(\b(?:api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*)([^\s,;]+)"
)
_JSON_SECRET = re.compile(
    r'(?i)("(?:api[_-]?key|token|secret|password|authorization)"\s*:\s*")([^"]+)(")'
)
_BEARER_SECRET = re.compile(r"(?i)(\bbearer\s+)([A-Za-z0-9._~+/=-]+)")
_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


class LocalExecutionError(RuntimeError):
    """Raised before process creation when the microtask boundary is invalid."""


class LocalExecutionStatus(StrEnum):
    """Truthful outcomes for one local subprocess invocation."""

    NOT_STARTED = "NOT_STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    SCOPE_VIOLATION = "SCOPE_VIOLATION"


class LocalHandshakeStatus(StrEnum):
    """Truthful outcome of the executor-control startup handshake."""

    STARTED = "STARTED"
    INVALID = "INVALID"
    TIMED_OUT = "TIMED_OUT"
    PROCESS_EXITED = "PROCESS_EXITED"


@dataclass(frozen=True)
class LocalExecutionRequest:
    """The bounded, file-level authority for a single local Codex invocation."""

    repository: str | Path
    allowed_paths: tuple[str, ...]
    model: str
    prompt: str = field(repr=False)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES
    sensitive_values: tuple[str, ...] = field(default_factory=tuple, repr=False)


@dataclass(frozen=True)
class LocalExecutionResult:
    """Secret-safe evidence from one attempt; ``started`` reflects Popen success only."""

    status: LocalExecutionStatus
    requested_model: str
    repository: str
    command: tuple[str, ...]
    started: bool
    process_id: int | None
    session_id: str | None
    started_at: datetime | None
    exit_code: int | None
    timed_out: bool
    stdout: str = field(repr=False)
    stderr: str = field(repr=False)
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    changed_paths: tuple[str, ...] = ()
    scope_violations: tuple[str, ...] = ()
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        """Return true only for a completed, in-scope, zero-exit process."""

        return self.status is LocalExecutionStatus.SUCCEEDED


@dataclass(frozen=True)
class LocalExecutionHandshake:
    """A trusted start receipt, or a fail-closed reason with no receipt."""

    status: LocalHandshakeStatus
    process_id: int
    evidence: ExecutionStartEvidence | None = None
    error: str | None = None


@dataclass
class _ActiveExecution:
    request: LocalExecutionRequest
    validated: _ValidatedRequest
    before: dict[str, str]
    process: subprocess.Popen[bytes]
    stdout_capture: _BoundedCapture
    stderr_capture: _BoundedCapture
    control_events: queue.Queue[dict[str, object] | None]
    stdout_thread: threading.Thread
    stderr_thread: threading.Thread


@dataclass(frozen=True)
class LocalExecutionHandle:
    """Opaque ownership of one current Popen process between start and wait."""

    _active: _ActiveExecution = field(repr=False)

    @property
    def process_id(self) -> int:
        return self._active.process.pid


@dataclass(frozen=True)
class _ValidatedRequest:
    repository: Path
    allowed_paths: frozenset[str]
    command: tuple[str, ...]
    safe_command: tuple[str, ...]


class _BoundedCapture:
    """Collect pipe output without allowing an untrusted child to exhaust memory."""

    def __init__(self, limit_bytes: int) -> None:
        self._limit_bytes = limit_bytes
        self._data = bytearray()
        self._truncated = False
        self._lock = threading.Lock()

    def append(self, chunk: bytes) -> None:
        """Keep only the configured prefix while continuing to drain the pipe."""

        with self._lock:
            remaining = self._limit_bytes - len(self._data)
            if remaining > 0:
                self._data.extend(chunk[:remaining])
            if len(chunk) > remaining:
                self._truncated = True

    def text(self) -> str:
        """Decode captured bytes without letting malformed child output abort evidence collection."""

        with self._lock:
            value = bytes(self._data).decode("utf-8", errors="replace")
            return f"{value}\n[output truncated]" if self._truncated else value

    @property
    def truncated(self) -> bool:
        """Return whether data was discarded after the bounded prefix."""

        with self._lock:
            return self._truncated


class LocalCodexExecutor:
    """Execute one non-interactive Codex task under strict local containment checks."""

    def __init__(self, *, command_prefix: Sequence[str] = ("codex",)) -> None:
        prefix = tuple(command_prefix)
        if not prefix or any(not item or "\0" in item for item in prefix):
            raise LocalExecutionError("command_prefix must contain non-empty command tokens")
        self._command_prefix = prefix

    def execute(self, request: LocalExecutionRequest) -> LocalExecutionResult:
        """Compatibility wrapper for the explicit ``start/handshake/wait`` lifecycle."""

        started = self.start(request)
        if isinstance(started, LocalExecutionResult):
            return started
        handshake = self.handshake(started, timeout_seconds=request.timeout_seconds)
        if handshake.status is LocalHandshakeStatus.STARTED:
            return self.wait(started, evidence=handshake.evidence)
        return self.wait(
            started,
            force_status=(
                LocalExecutionStatus.TIMED_OUT
                if handshake.status is LocalHandshakeStatus.TIMED_OUT
                else LocalExecutionStatus.FAILED
            ),
            error=handshake.error,
        )

    def start(self, request: LocalExecutionRequest) -> LocalExecutionHandle | LocalExecutionResult:
        """Launch a process without claiming a session or execution state.

        The returned handle represents only a successful ``Popen``.  Consumers must
        call :meth:`handshake` and receive canonical evidence before they may treat
        the process as started work.
        """

        validated = self._validate_request(request)
        before = self._snapshot_tree(validated.repository)
        stdout_capture = _BoundedCapture(request.output_limit_bytes)
        stderr_capture = _BoundedCapture(request.output_limit_bytes)
        try:
            process = subprocess.Popen(
                validated.command,
                cwd=validated.repository,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (OSError, ValueError) as error:
            return self._not_started_result(request, validated, error)

        control_events: queue.Queue[dict[str, object] | None] = queue.Queue()
        stdout_thread = self._drain_control_pipe(process.stdout, stdout_capture, control_events)
        stderr_thread = self._drain_pipe(process.stderr, stderr_capture)
        return LocalExecutionHandle(
            _ActiveExecution(
                request=request,
                validated=validated,
                before=before,
                process=process,
                stdout_capture=stdout_capture,
                stderr_capture=stderr_capture,
                control_events=control_events,
                stdout_thread=stdout_thread,
                stderr_thread=stderr_thread,
            )
        )

    def handshake(
        self,
        handle: LocalExecutionHandle,
        *,
        timeout_seconds: float,
    ) -> LocalExecutionHandshake:
        """Accept only the current process's canonical ``thread.started`` event.

        A malformed canonical event or timeout is fail-closed: this method stops and
        reaps the exact child represented by ``handle`` before returning no evidence.
        """

        if not 0 < timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise LocalExecutionError("handshake timeout must be within executor bounds")
        active = handle._active
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._stop_and_join(active)
                return LocalExecutionHandshake(
                    status=LocalHandshakeStatus.TIMED_OUT,
                    process_id=active.process.pid,
                    error="startup handshake timed out; child process was reaped",
                )
            try:
                event = active.control_events.get(timeout=remaining)
            except queue.Empty:
                continue
            if event is None:
                self._stop_and_join(active)
                return LocalExecutionHandshake(
                    status=LocalHandshakeStatus.PROCESS_EXITED,
                    process_id=active.process.pid,
                    error="process exited before canonical startup evidence",
                )
            if event.get("type") != "thread.started":
                continue
            session_id = event.get("thread_id")
            if set(event) != {"type", "thread_id"} or not isinstance(session_id, str):
                self._stop_and_join(active)
                return LocalExecutionHandshake(
                    status=LocalHandshakeStatus.INVALID,
                    process_id=active.process.pid,
                    error="invalid canonical startup event; child process was reaped",
                )
            try:
                evidence = ExecutionStartEvidence(
                    process_id=active.process.pid,
                    session_id=session_id,
                    started_at=datetime.now(UTC),
                )
            except ValueError:
                self._stop_and_join(active)
                return LocalExecutionHandshake(
                    status=LocalHandshakeStatus.INVALID,
                    process_id=active.process.pid,
                    error="invalid startup session identity; child process was reaped",
                )
            return LocalExecutionHandshake(
                status=LocalHandshakeStatus.STARTED,
                process_id=active.process.pid,
                evidence=evidence,
            )

    def wait(
        self,
        handle: LocalExecutionHandle,
        *,
        evidence: ExecutionStartEvidence | None = None,
        timeout_seconds: float | None = None,
        force_status: LocalExecutionStatus | None = None,
        error: str | None = None,
    ) -> LocalExecutionResult:
        """Collect final process and scope evidence after handshake or fail-closed stop."""

        active = handle._active
        timeout = active.request.timeout_seconds if timeout_seconds is None else timeout_seconds
        if not 0 < timeout <= MAX_TIMEOUT_SECONDS:
            raise LocalExecutionError("wait timeout must be within executor bounds")
        timed_out = False
        if active.process.poll() is None:
            try:
                active.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                self._stop_process(active.process)
        active.stdout_thread.join()
        active.stderr_thread.join()
        return self._finalize(
            active,
            evidence=evidence,
            timed_out=timed_out,
            force_status=force_status,
            error=error,
        )

    def _finalize(
        self,
        active: _ActiveExecution,
        *,
        evidence: ExecutionStartEvidence | None,
        timed_out: bool,
        force_status: LocalExecutionStatus | None,
        error: str | None,
    ) -> LocalExecutionResult:
        request = active.request
        stdout = self._redact(active.stdout_capture.text(), request.sensitive_values)
        stderr = self._redact(active.stderr_capture.text(), request.sensitive_values)
        try:
            after = self._snapshot_tree(active.validated.repository)
        except LocalExecutionError as snapshot_error:
            return LocalExecutionResult(
                status=LocalExecutionStatus.SCOPE_VIOLATION,
                requested_model=request.model,
                repository=str(active.validated.repository),
                command=active.validated.safe_command,
                started=True,
                process_id=active.process.pid,
                session_id=evidence.session_id if evidence else None,
                started_at=evidence.started_at if evidence else None,
                exit_code=active.process.returncode,
                timed_out=timed_out,
                stdout=stdout,
                stderr=stderr,
                stdout_truncated=active.stdout_capture.truncated,
                stderr_truncated=active.stderr_capture.truncated,
                scope_violations=("<scope-verification-failed>",),
                error=self._redact(str(snapshot_error), request.sensitive_values),
            )
        changed_paths = tuple(
            sorted(
                path
                for path in active.before.keys() | after.keys()
                if active.before.get(path) != after.get(path)
            )
        )
        scope_violations = tuple(
            path for path in changed_paths if path not in active.validated.allowed_paths
        )
        status = force_status or self._status_for(
            active.process.returncode,
            timed_out,
            scope_violations,
        )
        return LocalExecutionResult(
            status=status,
            requested_model=request.model,
            repository=str(active.validated.repository),
            command=active.validated.safe_command,
            started=True,
            process_id=active.process.pid,
            session_id=evidence.session_id if evidence else None,
            started_at=evidence.started_at if evidence else None,
            exit_code=active.process.returncode,
            timed_out=timed_out or status is LocalExecutionStatus.TIMED_OUT,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=active.stdout_capture.truncated,
            stderr_truncated=active.stderr_capture.truncated,
            changed_paths=changed_paths,
            scope_violations=scope_violations,
            error=self._redact(error, request.sensitive_values) if error else None,
        )

    def _validate_request(self, request: LocalExecutionRequest) -> _ValidatedRequest:
        repository = Path(request.repository).resolve()
        if not repository.is_dir():
            raise LocalExecutionError(f"microtask repository is not a directory: {repository}")
        if not isinstance(request.model, str) or not request.model.strip() or "\0" in request.model:
            raise LocalExecutionError("model must be a non-empty string")
        if not isinstance(request.prompt, str) or not request.prompt.strip() or "\0" in request.prompt:
            raise LocalExecutionError("prompt must be a non-empty string")
        self._validate_limits(request)
        allowed_paths = self._normalize_allowed_paths(request.allowed_paths)
        if ISOLATION_MARKER in allowed_paths:
            raise LocalExecutionError("the isolation marker can never be an allowed changed path")
        self._assert_isolated_microtask_repository(repository)
        for path in allowed_paths:
            self._assert_allowed_path_is_contained(repository, path)

        command = (
            *self._command_prefix,
            "exec",
            "--ephemeral",
            "-m",
            request.model,
            "-C",
            str(repository),
            "--sandbox",
            "workspace-write",
            "--json",
            request.prompt,
        )
        safe_command = (*command[:-1], "<redacted prompt>")
        return _ValidatedRequest(repository, allowed_paths, command, safe_command)

    @staticmethod
    def _validate_limits(request: LocalExecutionRequest) -> None:
        if (
            isinstance(request.timeout_seconds, bool)
            or not isinstance(request.timeout_seconds, (int, float))
            or not 0 < request.timeout_seconds <= MAX_TIMEOUT_SECONDS
        ):
            raise LocalExecutionError(
                f"timeout_seconds must be greater than zero and at most {MAX_TIMEOUT_SECONDS:g}"
            )
        if (
            isinstance(request.output_limit_bytes, bool)
            or not isinstance(request.output_limit_bytes, int)
            or not 1 <= request.output_limit_bytes <= MAX_OUTPUT_LIMIT_BYTES
        ):
            raise LocalExecutionError(
                f"output_limit_bytes must be between 1 and {MAX_OUTPUT_LIMIT_BYTES}"
            )

    @staticmethod
    def _normalize_allowed_paths(values: tuple[str, ...]) -> frozenset[str]:
        if not values:
            raise LocalExecutionError("allowed_paths must contain at least one explicit file")
        normalized: set[str] = set()
        for raw in values:
            if not isinstance(raw, str) or not raw or "\0" in raw or "\\" in raw:
                raise LocalExecutionError(f"invalid allowed path: {raw!r}")
            posix = PurePosixPath(raw)
            windows = PureWindowsPath(raw)
            if (
                posix.is_absolute()
                or windows.is_absolute()
                or ":" in raw
                or ".." in posix.parts
                or str(posix) in {"", "."}
                or raw.endswith("/")
            ):
                raise LocalExecutionError(f"allowed path escapes the repository: {raw!r}")
            path = posix.as_posix()
            if path in normalized:
                raise LocalExecutionError(f"duplicate allowed path: {path}")
            normalized.add(path)
        return frozenset(normalized)

    def _assert_isolated_microtask_repository(self, repository: Path) -> None:
        git_directory = repository / ".git"
        if not git_directory.is_dir() or git_directory.is_symlink():
            raise LocalExecutionError("microtask repository must own a standalone .git directory")
        top_level = Path(self._git_output(repository, "rev-parse", "--show-toplevel").strip()).resolve()
        if top_level != repository:
            raise LocalExecutionError("microtask repository must be its own Git top-level")
        self._git_output(repository, "rev-parse", "--verify", "HEAD")
        status = self._git_output(
            repository,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        if status:
            raise LocalExecutionError("microtask repository must be clean before execution")
        marker = repository / ISOLATION_MARKER
        if not marker.is_file() or marker.is_symlink():
            raise LocalExecutionError(f"missing committed isolation marker: {ISOLATION_MARKER}")
        try:
            marker_data = json.loads(marker.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError as error:
            raise LocalExecutionError("isolation marker is not valid JSON") from error
        if (
            not isinstance(marker_data, dict)
            or marker_data.get("schema_version") != ISOLATION_SCHEMA_VERSION
        ):
            raise LocalExecutionError("isolation marker schema is not recognized")
        self._git_output(repository, "cat-file", "-e", f"HEAD:{ISOLATION_MARKER}")

    @staticmethod
    def _assert_allowed_path_is_contained(repository: Path, relative_path: str) -> None:
        target = repository.joinpath(*PurePosixPath(relative_path).parts)
        try:
            target.resolve(strict=False).relative_to(repository)
        except ValueError as error:
            raise LocalExecutionError(
                f"allowed path resolves outside microtask repository: {relative_path}"
            ) from error

    def _git_output(self, repository: Path, *arguments: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(repository), *arguments],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=_GIT_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise LocalExecutionError("Git validation could not be completed") from error
        if result.returncode != 0:
            raise LocalExecutionError(f"Git validation failed: {' '.join(arguments[:2])}")
        return result.stdout

    def _snapshot_tree(self, repository: Path) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        total_bytes = 0

        def visit(directory: Path) -> None:
            nonlocal total_bytes
            with os.scandir(directory) as entries:
                for entry in sorted(entries, key=lambda item: item.name):
                    path = Path(entry.path)
                    relative = path.relative_to(repository).as_posix()
                    if relative == ".git":
                        continue
                    if len(snapshot) >= MAX_SNAPSHOT_FILES:
                        raise LocalExecutionError("microtask repository exceeds the file snapshot bound")
                    if entry.is_symlink():
                        self._assert_symlink_is_contained(repository, path, relative)
                        snapshot[relative] = f"symlink:{os.readlink(path)}"
                    elif entry.is_dir(follow_symlinks=False):
                        visit(path)
                    elif entry.is_file(follow_symlinks=False):
                        size = entry.stat(follow_symlinks=False).st_size
                        total_bytes += size
                        if total_bytes > MAX_SNAPSHOT_BYTES:
                            raise LocalExecutionError("microtask repository exceeds the snapshot byte bound")
                        snapshot[relative] = self._file_fingerprint(path)
                    else:
                        raise LocalExecutionError(f"unsupported filesystem entry in microtask: {relative}")

        visit(repository)
        return snapshot

    @staticmethod
    def _assert_symlink_is_contained(repository: Path, path: Path, relative: str) -> None:
        try:
            path.resolve(strict=False).relative_to(repository)
        except ValueError as error:
            raise LocalExecutionError(
                f"microtask symlink resolves outside repository: {relative}"
            ) from error

    @staticmethod
    def _file_fingerprint(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(_OUTPUT_CHUNK_BYTES):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _drain_pipe(
        stream: IO[Any] | None,
        capture: _BoundedCapture,
    ) -> threading.Thread:
        if stream is None:
            raise LocalExecutionError("subprocess did not provide the requested output pipe")

        def drain() -> None:
            try:
                while chunk := stream.read(_OUTPUT_CHUNK_BYTES):
                    capture.append(chunk)
            finally:
                stream.close()

        thread = threading.Thread(target=drain, daemon=True)
        thread.start()
        return thread

    @staticmethod
    def _drain_control_pipe(
        stream: IO[Any] | None,
        capture: _BoundedCapture,
        events: queue.Queue[dict[str, object] | None],
    ) -> threading.Thread:
        """Drain the ``--json`` control stream while exposing parsed event envelopes."""

        if stream is None:
            raise LocalExecutionError("subprocess did not provide the requested output pipe")

        def drain() -> None:
            try:
                while line := stream.readline():
                    capture.append(line)
                    try:
                        parsed = json.loads(line.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        events.put(parsed)
            finally:
                stream.close()
                events.put(None)

        thread = threading.Thread(target=drain, daemon=True)
        thread.start()
        return thread

    @staticmethod
    def _stop_process(process: subprocess.Popen[bytes]) -> None:
        try:
            process.terminate()
        except OSError:
            pass
        try:
            process.wait(timeout=_TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=_TERMINATE_GRACE_SECONDS)

    def _stop_and_join(self, active: _ActiveExecution) -> None:
        """Reap only the Popen process held by this handle and drain both pipes."""

        if active.process.poll() is None:
            self._stop_process(active.process)
        active.stdout_thread.join()
        active.stderr_thread.join()

    def _not_started_result(
        self,
        request: LocalExecutionRequest,
        validated: _ValidatedRequest,
        error: OSError | ValueError,
    ) -> LocalExecutionResult:
        return LocalExecutionResult(
            status=LocalExecutionStatus.NOT_STARTED,
            requested_model=request.model,
            repository=str(validated.repository),
            command=validated.safe_command,
            started=False,
            process_id=None,
            session_id=None,
            started_at=None,
            exit_code=None,
            timed_out=False,
            stdout="",
            stderr="",
            error=self._redact(str(error), request.sensitive_values),
        )

    @staticmethod
    def _status_for(
        exit_code: int | None,
        timed_out: bool,
        scope_violations: tuple[str, ...],
    ) -> LocalExecutionStatus:
        if scope_violations:
            return LocalExecutionStatus.SCOPE_VIOLATION
        if timed_out:
            return LocalExecutionStatus.TIMED_OUT
        if exit_code == 0:
            return LocalExecutionStatus.SUCCEEDED
        return LocalExecutionStatus.FAILED

    @staticmethod
    def _redact(value: str, sensitive_values: tuple[str, ...]) -> str:
        redacted = value
        for secret in sorted({item for item in sensitive_values if item}, key=len, reverse=True):
            redacted = redacted.replace(secret, "<redacted>")
        redacted = _JSON_SECRET.sub(r"\1<redacted>\3", redacted)
        redacted = _BEARER_SECRET.sub(r"\1<redacted>", redacted)
        redacted = _ASSIGNMENT_SECRET.sub(r"\1<redacted>", redacted)
        return _OPENAI_KEY.sub("<redacted>", redacted)


__all__ = [
    "DEFAULT_OUTPUT_LIMIT_BYTES",
    "DEFAULT_TIMEOUT_SECONDS",
    "ISOLATION_MARKER",
    "ISOLATION_SCHEMA_VERSION",
    "LocalCodexExecutor",
    "LocalExecutionError",
    "LocalExecutionRequest",
    "LocalExecutionResult",
    "LocalExecutionStatus",
]
