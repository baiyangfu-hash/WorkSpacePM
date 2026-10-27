"""``auto-pm role``: list the packs, and check them with an exit code a gate can trust."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.ui.cli.__main__ import cli

pytestmark = pytest.mark.usefixtures("identity_guard_off")


def test_role_list_names_the_shipped_packs(tmp_path: Path, cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(cli, ["-w", str(tmp_path), "role", "list"])
    assert result.exit_code == 0, result.output
    assert result.output.split() == ["engineer-plc", "engineer-python", "product-pm"]


def test_role_check_json_without_a_workspace_is_ok_but_unverified(tmp_path: Path, cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(cli, ["-w", str(tmp_path), "role", "check", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert {item["level"] for item in payload["findings"]} == {"UNVERIFIED"}


def test_role_check_exits_1_when_a_pack_is_broken(
    tmp_path: Path, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    roles = tmp_path / "roles"
    (roles / "Bad_Pack").mkdir(parents=True)
    monkeypatch.setattr("auto_pm.application.core.role_pack_service.default_roles_dir", lambda: roles)
    result = cli_runner.invoke(cli, ["-w", str(tmp_path), "role", "check"])
    assert result.exit_code == 1
    assert "RP-001" in result.output and "不通过" in result.output
