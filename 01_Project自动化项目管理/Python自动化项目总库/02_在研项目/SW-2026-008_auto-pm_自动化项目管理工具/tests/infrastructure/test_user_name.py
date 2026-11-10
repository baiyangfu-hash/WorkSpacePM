"""D-197: a stripped environment must not crash name lookups (Windows has no ``pwd`` module)."""

from __future__ import annotations

import getpass
import os

import pytest

from auto_pm.application.core.gate_run_service import child_environment
from auto_pm.infrastructure import user_name
from auto_pm.infrastructure.user_name import (
    UserNameUnavailableError,
    current_user_name,
    require_user_name,
)


def _no_pwd(*_a: object) -> str:
    raise ModuleNotFoundError("No module named 'pwd'")


def test_u01_windows_without_pwd_falls_back_instead_of_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(getpass, "getuser", _no_pwd)
    monkeypatch.setattr(os, "getlogin", lambda: "")
    assert current_user_name() == user_name.UNKNOWN_USER
    assert current_user_name("x") == "x"


def test_u02_falls_back_to_getlogin_before_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(getpass, "getuser", _no_pwd)
    monkeypatch.setattr(os, "getlogin", lambda: "alice")
    assert current_user_name() == "alice"


def test_u03_no_console_is_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(getpass, "getuser", lambda: (_ for _ in ()).throw(KeyError("uid")))

    def no_console() -> str:
        raise OSError("no tty")

    monkeypatch.setattr(os, "getlogin", no_console)
    assert current_user_name() == user_name.UNKNOWN_USER


def test_u04_gate_child_env_keeps_every_name_getuser_reads() -> None:
    names = {"LOGNAME": "a", "USER": "b", "LNAME": "c", "USERNAME": "d", "AUTO_PM_X": "no"}
    env = child_environment(names)
    assert {key: env[key] for key in ("LOGNAME", "USER", "LNAME", "USERNAME")} == {
        "LOGNAME": "a",
        "USER": "b",
        "LNAME": "c",
        "USERNAME": "d",
    }
    assert "AUTO_PM_X" not in env


# Names the official ``gate run`` child must inherit so it behaves like the CI runner / a plain Windows shell
# (home and login-name lookups: getpass, Path.home(), os.path.expanduser).
CI_IDENTITY_VARIABLES = {
    "USERNAME",
    "USER",
    "LOGNAME",
    "LNAME",
    "HOMEDRIVE",
    "HOMEPATH",
    "USERPROFILE",
    "HOME",
}


def test_u05_gate_child_env_matches_the_ci_identity_variable_set() -> None:
    source = dict.fromkeys(CI_IDENTITY_VARIABLES, "v")
    assert CI_IDENTITY_VARIABLES <= set(child_environment(source))


def test_u06_a_record_that_says_who_did_it_never_gets_the_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-204: a signature by "unknown" proves nothing; ``require_user_name`` raises instead of falling back."""

    monkeypatch.setattr(getpass, "getuser", _no_pwd)
    monkeypatch.setattr(os, "getlogin", lambda: "")
    with pytest.raises(UserNameUnavailableError):
        require_user_name()
    assert current_user_name() == user_name.UNKNOWN_USER  # display and metadata keep the harmless placeholder
    monkeypatch.setattr(getpass, "getuser", lambda: " alice ")
    assert require_user_name() == "alice"
