"""D-204: initialising a project's PM files files a change order whose applicant is a "who did this" record, never a placeholder."""

from __future__ import annotations

import getpass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from auto_pm.application.workbench_use_cases import WorkbenchUseCases
from auto_pm.infrastructure.user_name import UserNameUnavailableError


def _use_cases() -> tuple[WorkbenchUseCases, MagicMock, MagicMock]:
    project_service = MagicMock()
    project_service.get_project.return_value = SimpleNamespace(path="/p", name="demo", stack="plc")
    change_service = MagicMock()
    return WorkbenchUseCases(project_service, change_service=change_service), project_service, change_service


def _nobody() -> str:
    raise UserNameUnavailableError("取不到当前登录用户名")


def test_a01_without_a_login_name_nothing_is_initialised_and_no_order_is_filed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTO_PM_AUTHOR", raising=False)
    monkeypatch.setattr("auto_pm.application.workbench_use_cases.require_user_name", _nobody)
    cases, project_service, change_service = _use_cases()
    outcome = cases.initialize_project_pm("SW-1")
    assert outcome.success is False and "未初始化" in outcome.message and "AUTO_PM_AUTHOR" in outcome.message
    project_service.init_project_pm_framework.assert_not_called()  # refused before anything was written
    change_service.create_change_request.assert_not_called()


def test_a02_an_explicit_author_wins_and_the_order_carries_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_PM_AUTHOR", "alice")
    monkeypatch.setattr("auto_pm.application.workbench_use_cases.require_user_name", _nobody)
    cases, _project, change_service = _use_cases()
    assert cases.initialize_project_pm("SW-1").success is True
    assert change_service.create_change_request.call_args.kwargs["applicant"] == "alice"


def test_a03_the_login_name_is_used_when_no_author_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTO_PM_AUTHOR", raising=False)
    monkeypatch.setattr(getpass, "getuser", lambda: "bob")
    cases, _project, change_service = _use_cases()
    assert cases.initialize_project_pm("SW-1").success is True
    assert change_service.create_change_request.call_args.kwargs["applicant"] == "bob"
