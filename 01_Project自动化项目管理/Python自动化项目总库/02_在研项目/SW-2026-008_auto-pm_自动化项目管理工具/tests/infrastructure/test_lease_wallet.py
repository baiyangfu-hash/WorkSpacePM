"""The local lease wallet keeps one holder's token per Run; it never hands a token to another owner and never hides a broken file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_pm.infrastructure import lease_wallet


def test_save_then_load_returns_the_token_of_the_same_owner_only(tmp_path: Path) -> None:
    path = lease_wallet.save(tmp_path, run_id="RUN-1", owner_id="agent-a", lease_token="secret-a", epoch=1)

    assert path == tmp_path.resolve() / lease_wallet.WALLET_DIR / "RUN-1.json"
    assert lease_wallet.load(tmp_path, run_id="RUN-1", owner_id="agent-a") == "secret-a"
    with pytest.raises(lease_wallet.LeaseWalletError, match="不属于 agent-b"):
        lease_wallet.load(tmp_path, run_id="RUN-1", owner_id="agent-b")


def test_a_new_holder_replaces_the_previous_entry_atomically(tmp_path: Path) -> None:
    lease_wallet.save(tmp_path, run_id="RUN-1", owner_id="agent-a", lease_token="secret-a", epoch=1)
    lease_wallet.save(tmp_path, run_id="RUN-1", owner_id="agent-b", lease_token="secret-b", epoch=2)

    assert lease_wallet.load(tmp_path, run_id="RUN-1", owner_id="agent-b") == "secret-b"
    assert [p.name for p in (tmp_path / lease_wallet.WALLET_DIR).iterdir()] == ["RUN-1.json"]  # no temporary file left behind


def test_a_missing_entry_and_a_broken_file_are_errors(tmp_path: Path) -> None:
    assert lease_wallet.find(tmp_path, "RUN-9") is None
    with pytest.raises(lease_wallet.LeaseWalletError, match="没有"):
        lease_wallet.load(tmp_path, run_id="RUN-9", owner_id="agent-a")
    broken = lease_wallet.wallet_path(tmp_path, "RUN-8")
    broken.parent.mkdir(parents=True)
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(lease_wallet.LeaseWalletError, match="无法读取"):
        lease_wallet.find(tmp_path, "RUN-8")
    broken.write_text(json.dumps({"schema_version": "lease-wallet.v1", "run_id": "RUN-OTHER", "owner_id": "a", "lease_token": "t"}), encoding="utf-8")
    with pytest.raises(lease_wallet.LeaseWalletError, match="格式无效"):
        lease_wallet.find(tmp_path, "RUN-8")


@pytest.mark.parametrize("run_id", ["../escape", "a/b", "", "RUN 1"])
def test_a_run_id_that_is_not_a_plain_file_name_is_refused(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(lease_wallet.LeaseWalletError):
        lease_wallet.wallet_path(tmp_path, run_id)
