"""A Run started for another agent must land its token in that agent's wallet (wallet isolation, 11-03).

The defect: the main executor started ``--executor trae --lease-token <value>``; no wallet file was written, so Trae's own
``--lease-wallet`` command found nothing ("本机钱包里没有 … 的口令") and only the starter could ever renew the lease.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from auto_pm.infrastructure import lease_wallet
from tests.cli.test_continuity import _declaration_work, _invoke
from tests.git_support import run_worktree

# Same as test_continuity.py: these fixtures have no registered project anchor and build tier-less cards.
pytestmark = pytest.mark.usefixtures("identity_guard_off")

RUN = "RUN-CLI-OTHER"
WORK = "WORK-CLI-DECL"
_MARKERS = ("AUTO_PM_AGENT", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")


@pytest.fixture(autouse=True)
def _cards_here_predate_the_tier_cutover(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("auto_pm.application.core.implementation_card_tier.card_is_new", lambda _card: False)


@pytest.fixture(autouse=True)
def _no_agent_markers(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _MARKERS:
        monkeypatch.delenv(key, raising=False)
    for key in [k for k in os.environ if k.upper().startswith("CODEX_")]:
        monkeypatch.delenv(key, raising=False)


def _start(cli_runner: CliRunner, root: Path, executor: str, *credential: str) -> Result:
    return _invoke(
        cli_runner,
        root,
        [
            "run", "start", "--run-id", RUN, "--work-id", WORK, "--executor", executor, "--adapter", "trae",
            "--owned", "README.md", "--declared-dirty", "README.md", "--worktree", str(run_worktree(root)),
            *credential, "--lease-seconds", "3600", "--idempotency-key", "run-start-other",
        ],
    )


def test_a_run_for_another_agent_without_the_wallet_is_refused_and_writes_nothing(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _declaration_work(cli_runner, tmp_path, "README.md")
    monkeypatch.setenv("AUTO_PM_AGENT", "codex:m3")

    refused = _start(cli_runner, tmp_path, "trae", "--lease-token", "file-value")

    assert refused.exit_code == 1
    assert "--lease-wallet" in refused.output and "trae" in refused.output
    assert "file-value" not in refused.output
    assert lease_wallet.find(tmp_path, RUN) is None
    assert not (tmp_path / lease_wallet.WALLET_DIR / f"{RUN}.json").exists()


def test_the_wallet_start_writes_the_receivers_entry_so_the_receiver_can_read_it(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _declaration_work(cli_runner, tmp_path, "README.md")
    monkeypatch.setenv("AUTO_PM_AGENT", "codex:m3")

    started = _start(cli_runner, tmp_path, "trae:cn", "--lease-wallet")

    assert started.exit_code == 0, started.output
    token = lease_wallet.load(tmp_path, run_id=RUN, owner_id="trae:cn")  # what Trae's --lease-wallet reads
    assert token and token not in started.output
    with pytest.raises(lease_wallet.LeaseWalletError, match="不属于 codex"):
        lease_wallet.load(tmp_path, run_id=RUN, owner_id="codex")


def test_an_agent_starting_its_own_run_may_still_use_the_environment_token(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _declaration_work(cli_runner, tmp_path, "README.md")
    monkeypatch.setenv("AUTO_PM_AGENT", "trae:cn")
    monkeypatch.setenv("OWN_TOKEN", "own-secret")

    started = _start(cli_runner, tmp_path, "trae:cn", "--lease-token-env", "OWN_TOKEN")

    assert started.exit_code == 0, started.output


@pytest.mark.parametrize("caller", ["", "cursor:x"])
def test_the_user_terminal_and_a_different_agent_are_also_refused_for_a_roster_executor(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caller: str
) -> None:
    _declaration_work(cli_runner, tmp_path, "README.md")
    if caller:
        monkeypatch.setenv("AUTO_PM_AGENT", caller)

    refused = _start(cli_runner, tmp_path, "trae", "--lease-token", "file-value")

    assert refused.exit_code == 1 and "--lease-wallet" in refused.output
    assert ("用户终端" in refused.output) is (caller == "")


def test_an_executor_outside_the_roster_keeps_the_old_freedom(cli_runner: CliRunner, tmp_path: Path) -> None:
    _declaration_work(cli_runner, tmp_path, "README.md")

    started = _start(cli_runner, tmp_path, "agent-a", "--lease-token", "legacy-secret")

    assert started.exit_code == 0, started.output
