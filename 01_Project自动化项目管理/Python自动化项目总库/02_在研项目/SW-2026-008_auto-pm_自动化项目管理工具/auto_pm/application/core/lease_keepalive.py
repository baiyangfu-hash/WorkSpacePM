"""Keep one Run's lease alive while a long foreground command runs (a full pytest, ``pm verify``)."""

from __future__ import annotations

import threading
from types import TracebackType

from auto_pm.application.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)

DEFAULT_LEASE_SECONDS = 900


class LeaseKeepAliveError(RuntimeError):
    """The first renewal failed, so the command was never started."""


class LeaseKeepAlive:
    """Renew the lease every ``lease_seconds // 3`` until the block ends.

    Only renews: the total-hold cap (``extend-hold``) is untouched, so a renewal refused at the cap stops the loop and is
    reported through :attr:`error` — it never raises into the caller's command. ``strict`` makes the *first* renewal
    mandatory (a command that cannot keep its lease should not start); ``pm verify`` uses ``strict=False`` because it
    carries its own lease checks.
    """

    def __init__(
        self,
        execution: ContinuityExecutionService,
        *,
        run_id: str,
        owner_id: str,
        token: str,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        interval_seconds: float | None = None,
        strict: bool = True,
    ) -> None:
        self._execution = execution
        self._run_id = run_id
        self._owner_id = owner_id
        self._token = token
        self._lease_seconds = lease_seconds
        self._interval = interval_seconds if interval_seconds is not None else lease_seconds / 3
        self._strict = strict
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.error: str = ""
        self.renewals = 0

    def _renew_once(self) -> None:
        lease = self._execution.current_lease(self._run_id)
        self._execution.renew_lease(
            self._run_id,
            self._owner_id,
            self._token,
            self._lease_seconds,
            f"{self._run_id.lower()}-keepalive-v{lease.version}",
            expected_version=lease.version,
        )
        self.renewals += 1

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._renew_once()
            except ContinuityExecutionError as error:
                self.error = str(error)
                return

    def __enter__(self) -> LeaseKeepAlive:
        try:
            self._renew_once()
        except ContinuityExecutionError as error:
            if self._strict:
                raise LeaseKeepAliveError(f"首次续租失败，命令没有启动：{error}") from error
            self.error = str(error)
            return self
        self._thread = threading.Thread(target=self._loop, name="lease-keepalive", daemon=True)
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=30)
