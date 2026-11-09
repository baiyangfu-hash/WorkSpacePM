"""D-155: ``identity_guard_off`` switches the identity checks off for every command module, however late it is first loaded, and puts them all back."""

from __future__ import annotations

import importlib
import sys

import pytest

from auto_pm.ui.cli import runtime_identity_guard as source
from tests.conftest import IDENTITY_GUARD_NAMES, _command_modules, _no_identity_check

# Command modules that the old fixed name list never named, but that bind the checks by name.
_MODULES_OUTSIDE_THE_OLD_LIST = ("doc", "gate", "pm_retire")


def test_a_command_module_first_loaded_while_the_guard_is_off_gets_the_no_op(
    identity_guard_off: None,
) -> None:
    sys.modules.pop("auto_pm.ui.cli.dogfood", None)
    fresh = importlib.import_module("auto_pm.ui.cli.dogfood")

    assert fresh.require_runtime_identity_for_workspace is _no_identity_check


@pytest.fixture
def _loaded_before_the_guard_goes_off() -> None:
    """Declared first in the tests below, so these modules are already loaded (with the real checks bound) when the fixture starts."""

    for name in _MODULES_OUTSIDE_THE_OLD_LIST:
        importlib.import_module(f"auto_pm.ui.cli.{name}")


@pytest.mark.parametrize("name", _MODULES_OUTSIDE_THE_OLD_LIST)
def test_modules_the_old_name_list_missed_are_switched_off_too(
    name: str, _loaded_before_the_guard_goes_off: None, identity_guard_off: None
) -> None:
    module = importlib.import_module(f"auto_pm.ui.cli.{name}")
    bound = [n for n in IDENTITY_GUARD_NAMES if hasattr(module, n)]
    assert bound, f"{name} no longer binds an identity check; pick another module for this test"
    assert all(getattr(module, n) is _no_identity_check for n in bound)


def test_every_command_module_and_the_source_have_the_real_checks_back_after_the_fixture() -> None:
    real = {n: getattr(source, n) for n in IDENTITY_GUARD_NAMES}
    importlib.import_module("auto_pm.ui.cli.__main__")

    _drive_fixture()
    leaked = [
        (m.__name__, n)
        for m in _command_modules()
        for n in IDENTITY_GUARD_NAMES
        if getattr(m, n, None) is _no_identity_check
    ]
    assert leaked == [], f"checks still switched off after the fixture: {leaked}"
    assert {n: getattr(source, n) for n in IDENTITY_GUARD_NAMES} == real


def _drive_fixture() -> None:
    from tests import conftest

    fixture = conftest.identity_guard_off.__wrapped__  # type: ignore[attr-defined]
    gen = fixture()
    next(gen)
    sys.modules.pop("auto_pm.ui.cli.dogfood", None)
    importlib.import_module("auto_pm.ui.cli.dogfood")  # first loaded while the guard is off
    with pytest.raises(StopIteration):
        next(gen)
