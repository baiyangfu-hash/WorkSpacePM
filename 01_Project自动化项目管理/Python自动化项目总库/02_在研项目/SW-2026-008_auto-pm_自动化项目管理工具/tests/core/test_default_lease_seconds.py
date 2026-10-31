"""默认租约秒数只有一个来源：各 CLI 选项与服务默认值必须与常量一致（防 900/1800 两套口径复发）。"""

from __future__ import annotations

import inspect
from typing import Any

import click

from auto_pm.application.core.local_execution_orchestrator import LocalExecutionOrchestrator
from auto_pm.application.core.mission_switch_service import MissionSwitchService
from auto_pm.application.core.pm_facade_service import PmFacadeService
from auto_pm.contracts.continuity import DEFAULT_LEASE_SECONDS
from auto_pm.ui.cli.continuity import continuity_group
from auto_pm.ui.cli.pm_handoff import takeover_pm
from auto_pm.ui.cli.pm_switch import switch_pm, unpark_pm

_NAMES = ("lease_seconds", "planning_lease_seconds")


def _service_defaults() -> dict[str, Any]:
    found: dict[str, Any] = {}
    for cls in (LocalExecutionOrchestrator, MissionSwitchService, PmFacadeService):
        for name, func in inspect.getmembers(cls, inspect.isfunction):
            params = inspect.signature(func).parameters
            found.update(
                {f"{cls.__name__}.{name}.{p}": params[p].default for p in _NAMES if p in params}
            )
    return found


def _cli_defaults(cmd: click.Command, prefix: str = "") -> dict[str, Any]:
    path = f"{prefix}/{cmd.name}"
    found = {f"{path}:{p.name}": p.default for p in cmd.params if p.name == "lease_seconds"}
    subs = cmd.commands.values() if isinstance(cmd, click.Group) else []
    for sub in subs:
        found.update(_cli_defaults(sub, path))
    return found


def test_constant_is_the_agreed_value() -> None:
    assert DEFAULT_LEASE_SECONDS == 1800


def test_service_signatures_use_the_constant() -> None:
    defaults = {k: v for k, v in _service_defaults().items() if v is not inspect.Parameter.empty}
    assert len(defaults) >= 4
    assert {k: v for k, v in defaults.items() if v != DEFAULT_LEASE_SECONDS} == {}


def test_cli_options_use_the_constant() -> None:
    defaults = _cli_defaults(continuity_group)
    for cmd in (takeover_pm, unpark_pm, switch_pm):
        defaults.update(_cli_defaults(cmd))
    assert {"/switch:lease_seconds", "/unpark:lease_seconds", "/takeover:lease_seconds"} <= {
        k.split(":")[0] + ":" + k.split(":")[1] for k in defaults
    }
    assert len(defaults) >= 7
    assert {k: v for k, v in defaults.items() if v != DEFAULT_LEASE_SECONDS} == {}
