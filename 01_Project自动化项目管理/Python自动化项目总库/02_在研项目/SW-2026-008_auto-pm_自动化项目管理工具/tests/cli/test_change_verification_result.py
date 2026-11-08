"""D-48: ``change transition --to completed`` takes a structured ``--verification-result``."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.ui.cli.__main__ import cli
from tests.change.test_acceptance_flow import (
    acceptance_workspace,  # noqa: F401 - the shared fixture
)

pytestmark = [pytest.mark.cli, pytest.mark.usefixtures("identity_guard_off")]

CHG = "CHG-DOCU-2026-001"


def _run(cli_runner: CliRunner, workspace: str, *args: str) -> tuple[int, str]:
    result = cli_runner.invoke(cli, ["-w", workspace, "change", "transition", CHG, *args], catch_exceptions=False)
    return result.exit_code, result.output


def _to_accepting(cli_runner: CliRunner, workspace: str) -> None:
    assert _run(cli_runner, workspace, "--to", "pending_acceptance", "--approver", "张三")[0] == 0
    assert _run(cli_runner, workspace, "--to", "accepting", "--approver", "李四")[0] == 0


def test_result_pass_completes_and_the_old_keyword_notice_is_not_shown(cli_runner: CliRunner, acceptance_workspace: str) -> None:  # noqa: F811
    _to_accepting(cli_runner, acceptance_workspace)

    code, output = _run(cli_runner, acceptance_workspace, "--to", "completed", "--approver", "李四", "--verification-result", "pass")

    assert code == 0 and "状态流转成功" in output and "将弃用" not in output


def test_result_fail_is_refused_and_the_change_stays_accepting(cli_runner: CliRunner, acceptance_workspace: str) -> None:  # noqa: F811
    _to_accepting(cli_runner, acceptance_workspace)

    code, output = _run(cli_runner, acceptance_workspace, "--to", "completed", "--approver", "李四", "--verification-result", "fail")

    assert code == 1 and "退回返工" in output


def test_without_the_option_the_old_way_works_and_says_it_is_going_away(cli_runner: CliRunner, acceptance_workspace: str) -> None:  # noqa: F811
    _to_accepting(cli_runner, acceptance_workspace)

    code, output = _run(cli_runner, acceptance_workspace, "--to", "completed", "--approver", "李四")

    assert code == 0 and "将弃用" in output


def test_an_unknown_result_is_rejected_by_the_option_itself(cli_runner: CliRunner, tmp_path: Path) -> None:
    code, output = _run(cli_runner, str(tmp_path), "--to", "completed", "--verification-result", "maybe")

    assert code != 0 and "Invalid value for '--verification-result'" in output
