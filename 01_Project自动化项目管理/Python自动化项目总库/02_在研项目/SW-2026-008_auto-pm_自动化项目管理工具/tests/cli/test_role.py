"""``auto-pm role``: list the packs, and check them with an exit code a gate can trust."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.ui.cli.__main__ import cli

pytestmark = pytest.mark.usefixtures("identity_guard_off")


def _real_workspace() -> Path:
    """The workspace that holds the tracked role library ``roles/``."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "roles" / "shared").is_dir():
            return parent
    raise AssertionError("找不到含 roles/ 的工作区根目录")


def test_role_list_names_the_library_packs(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(cli, ["-w", str(_real_workspace()), "role", "list"])
    assert result.exit_code == 0, result.output
    names = result.output.split()
    assert {"fullstack-engineer", "plc-electrical-engineer", "product-pm"} <= set(names)


def test_role_check_json_on_the_real_library_is_clean(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(cli, ["-w", str(_real_workspace()), "role", "check", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True and payload["findings"] == []


def test_role_check_exits_1_when_the_library_is_missing(tmp_path: Path, cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(cli, ["-w", str(tmp_path), "role", "check"])
    assert result.exit_code == 1
    assert "RP-001" in result.output and "不通过" in result.output


def test_role_check_exits_1_when_a_pack_is_broken(tmp_path: Path, cli_runner: CliRunner) -> None:
    (tmp_path / "roles" / "Bad_Pack").mkdir(parents=True)
    result = cli_runner.invoke(cli, ["-w", str(tmp_path), "role", "check"])
    assert result.exit_code == 1
    assert "RP-001" in result.output and "不通过" in result.output
