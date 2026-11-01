"""keep_system_awake: ask for it, always release it, never raise into the command (TD-SW008-160)."""

from __future__ import annotations

import os

import pytest

from auto_pm.infrastructure import keep_awake
from auto_pm.infrastructure.keep_awake import (
    ES_CONTINUOUS,
    ES_SYSTEM_REQUIRED,
    keep_system_awake,
)


class _Setter:
    def __init__(self, results: list[int] | None = None, raises: bool = False) -> None:
        self.calls: list[int] = []
        self._results = results or [1]
        self._raises = raises

    def __call__(self, flags: int) -> int:
        self.calls.append(flags)
        if self._raises:
            raise OSError("power API unavailable")
        return self._results[0]


def test_it_asks_for_the_system_to_stay_on_and_releases_it_afterwards() -> None:
    setter = _Setter()
    with keep_system_awake(setter) as accepted:
        assert accepted is True
        assert setter.calls == [ES_CONTINUOUS | ES_SYSTEM_REQUIRED]
    assert setter.calls == [ES_CONTINUOUS | ES_SYSTEM_REQUIRED, ES_CONTINUOUS]


def test_a_refused_request_is_reported_but_the_command_still_runs() -> None:
    setter = _Setter(results=[0])
    with keep_system_awake(setter) as accepted:
        assert accepted is False
    assert setter.calls[-1] == ES_CONTINUOUS


def test_a_power_api_that_raises_never_reaches_the_caller() -> None:
    setter = _Setter(raises=True)
    with keep_system_awake(setter) as accepted:
        assert accepted is False
    assert len(setter.calls) == 2  # the request and the release were both attempted


def test_the_release_runs_when_the_command_raises() -> None:
    setter = _Setter()
    with pytest.raises(RuntimeError, match="boom"):
        with keep_system_awake(setter):
            raise RuntimeError("boom")
    assert setter.calls[-1] == ES_CONTINUOUS


def test_without_a_power_api_it_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keep_awake, "_windows_setter", lambda: None)
    with keep_system_awake() as accepted:
        assert accepted is False


def test_the_real_setter_exists_only_on_windows() -> None:
    setter = keep_awake._windows_setter()
    if os.name == "nt":
        assert callable(setter)
    else:
        assert setter is None
