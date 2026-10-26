"""Shared Git time limit: bounded override, explicit receipt, fail closed, interrupt not swallowed."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from auto_pm.infrastructure.control_root_guard import clean_git_environment
from auto_pm.infrastructure.git_timeout import GIT_TIMEOUT_ENV, resolve_git_timeout, run_git_bounded


class _BoomError(RuntimeError):
    pass


def _slow_env() -> dict[str, str]:
    env = clean_git_environment()
    env.update(
        GIT_CONFIG_COUNT="1",
        GIT_CONFIG_KEY_0="alias.slow",
        GIT_CONFIG_VALUE_0=f'!"{Path(sys.executable).as_posix()}" -c "import time; time.sleep(60)"',
    )
    return env


def test_default_used_when_override_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(GIT_TIMEOUT_ENV, raising=False)
    assert resolve_git_timeout(42.0) == 42.0


def test_override_in_range_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GIT_TIMEOUT_ENV, "77")
    assert resolve_git_timeout(10.0) == 77.0


@pytest.mark.parametrize("bad", ["abc", "0", "4", "601", "nan", "-1"])
def test_bad_override_rejected(monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    monkeypatch.setenv(GIT_TIMEOUT_ENV, bad)
    with pytest.raises(ValueError, match="不可用"):
        resolve_git_timeout(10.0)


def test_bad_override_fails_closed_as_caller_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(GIT_TIMEOUT_ENV, "abc")
    with pytest.raises(_BoomError, match="不可用"):
        run_git_bounded(
            ["git", "--version"], default_timeout=10.0, error_cls=_BoomError, where=tmp_path,
            capture_output=True,
        )


def test_normal_git_returns_result(tmp_path: Path) -> None:
    done = run_git_bounded(
        ["git", "--version"], default_timeout=30.0, error_cls=_BoomError, where=tmp_path,
        capture_output=True, check=False,
    )
    assert done.returncode == 0 and b"git version" in done.stdout


def test_real_hang_becomes_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.setenv(GIT_TIMEOUT_ENV, "5")
    with pytest.raises(_BoomError) as info:
        run_git_bounded(
            ["git", "-C", str(tmp_path), "slow"], default_timeout=30.0, error_cls=_BoomError,
            where=tmp_path, capture_output=True, check=False, env=_slow_env(),
        )
    message = str(info.value)
    assert "超时回执" in message and "git slow" in message and "5 秒" in message and "实际等待" in message


def test_interrupt_not_swallowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("auto_pm.infrastructure.git_timeout.subprocess.run", boom)
    with pytest.raises(KeyboardInterrupt):
        run_git_bounded(["git", "--version"], default_timeout=10.0, error_cls=_BoomError, where=tmp_path)


def test_every_call_site_keeps_its_documented_default_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pin each site's default so a silent 30 -> 300 edit turns this red (approval chain included)."""
    from types import SimpleNamespace

    from auto_pm.application.core import (
        approval_proof_service,
        chg_tracking_service,
        evidence_collection_service,
    )
    from auto_pm.application.core import execution_microtask_service as microtask
    from auto_pm.infrastructure import continuity_store, local_executor, plc_git_marker_guard

    monkeypatch.delenv(GIT_TIMEOUT_ENV, raising=False)
    seen: list[tuple[str, float]] = []

    class _Stop(Exception):  # noqa: N818
        pass

    def recorder(label: str):  # type: ignore[no-untyped-def]
        def record(*_args: object, default_timeout: float, **_kwargs: object) -> None:
            seen.append((label, default_timeout))
            raise _Stop

        return record

    def probe(module: object, label: str, call) -> None:  # type: ignore[no-untyped-def]
        for name in ("run_git_bounded", "run_git_bounded_text"):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, recorder(label))
        with pytest.raises(_Stop):
            call()

    store = SimpleNamespace(workspace_root=tmp_path)
    probe(local_executor, "local_executor", lambda: local_executor.LocalCodexExecutor._git_output(None, tmp_path, "status"))  # type: ignore[arg-type]
    probe(continuity_store, "continuity_store.bytes", lambda: continuity_store.ContinuityStore._git_bytes(store, "status"))  # type: ignore[arg-type]
    probe(continuity_store, "continuity_store.clean", lambda: continuity_store.ContinuityStore._require_paths_clean_at_head(store, "x"))  # type: ignore[arg-type]
    probe(plc_git_marker_guard, "plc_marker", lambda: plc_git_marker_guard._git(tmp_path, "status"))
    probe(microtask, "microtask", lambda: microtask.ExecutionMicrotaskService._git_bytes(tmp_path, "status"))
    probe(approval_proof_service, "approval", lambda: approval_proof_service.ApprovalProofService(tmp_path)._git("status"))
    probe(evidence_collection_service, "evidence", lambda: evidence_collection_service.EvidenceCollectionService._git_output(tmp_path, "status"))
    probe(chg_tracking_service, "chg", lambda: chg_tracking_service._git(tmp_path, "status"))

    assert dict(seen) == {
        "local_executor": 15.0,
        "continuity_store.bytes": 10.0,
        "continuity_store.clean": 10.0,
        "plc_marker": 10.0,
        "microtask": 120.0,
        "approval": 30.0,
        "evidence": 600.0,
        "chg": 60.0,
    }
