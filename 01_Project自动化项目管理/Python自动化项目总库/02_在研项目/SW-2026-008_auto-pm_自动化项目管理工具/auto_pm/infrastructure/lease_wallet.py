"""Local lease wallet: where an agent keeps the lease token of the Run it holds, so nobody copies a token by hand (TD-SW008-063/064).

One JSON file per Run under ``<control root>/.auto-pm/cache/lease-wallet/`` (git-ignored, like ``continuity.db``).  The file holds the token in
plain text: the same single-user, local trust model the user accepted for the ``execution_leases`` table on 2026-10-10 (TD-SW008-065) -
anyone who can read the control root can read both.  The token never appears in argv, in output or in Git.

The wallet is a convenience, never an authority: every write is still checked against the store (owner, token, expiry, epoch).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

WALLET_DIR = Path(".auto-pm") / "cache" / "lease-wallet"
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class LeaseWalletError(RuntimeError):
    """Raised when a wallet entry is missing, malformed or belongs to someone else."""


def wallet_path(control_root: str | Path, run_id: str) -> Path:
    if _RUN_ID.fullmatch(run_id) is None:
        raise LeaseWalletError("run_id 不能作为钱包文件名")
    return Path(control_root).resolve() / WALLET_DIR / f"{run_id}.json"


def save(control_root: str | Path, *, run_id: str, owner_id: str, lease_token: str, epoch: int) -> Path:
    """Atomically replace the Run's wallet entry with the current holder's token (the previous holder's token is dead anyway)."""

    if not owner_id or not lease_token or lease_token != lease_token.strip():
        raise LeaseWalletError("钱包需要非空的持有者与口令")
    target = wallet_path(control_root, run_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": "lease-wallet.v1",
        "run_id": run_id,
        "owner_id": owner_id,
        "lease_token": lease_token,
        "epoch": epoch,
        "written_at": datetime.now(UTC).isoformat(),
    }
    descriptor, temporary = tempfile.mkstemp(prefix=f".{run_id}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return target


def find(control_root: str | Path, run_id: str) -> dict[str, object] | None:
    """The wallet record of a Run, or ``None`` when there is none; a malformed file is an error, never silently ignored."""

    target = wallet_path(control_root, run_id)
    if not target.is_file():
        return None
    try:
        record = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise LeaseWalletError(f"钱包文件无法读取: {target.name}") from error
    if (
        not isinstance(record, dict)
        or record.get("schema_version") != "lease-wallet.v1"
        or record.get("run_id") != run_id
        or not isinstance(record.get("owner_id"), str)
        or not isinstance(record.get("lease_token"), str)
        or not record["lease_token"]
    ):
        raise LeaseWalletError(f"钱包文件格式无效: {target.name}")
    return record


_LISTED_ENTRIES = 8


def entries(control_root: str | Path) -> list[tuple[str, str]]:
    """(run_id, owner_id) of every readable wallet file under the control root, never the token; broken files are skipped (diagnostics only)."""

    directory = Path(control_root).resolve() / WALLET_DIR
    if not directory.is_dir():
        return []
    found: list[tuple[str, str]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            record = find(control_root, path.stem)
        except LeaseWalletError:
            continue
        if record is not None:
            found.append((path.stem, str(record["owner_id"])))
    return found


def missing_hint(control_root: str | Path, run_id: str) -> str:
    """Why a Run may have no entry here: the wallet is local to one control root and is written only by the command that started or took over the Run."""

    root = Path(control_root).resolve()
    present = entries(root)
    if present:
        listed = "、".join(f"{run}（属主 {owner}）" for run, owner in present[:_LISTED_ENTRIES])
        more = f" 等共 {len(present)} 个" if len(present) > _LISTED_ENTRIES else ""
        content = f"现有：{listed}{more}"
    else:
        content = "目前没有任何条目"
    return (
        f"（查的控制根：{root}；钱包{content}）"
        f"口令只存在建 Run 的那个控制根里，且只有 `run start --lease-wallet`、`pm takeover`、`run reclaim` 会写。"
        f"若 {run_id} 是别的执行者建的：让持有者先 `pm handoff`，你再 `pm takeover` 拿自己的口令；"
        f"或让建 Run 的人以 `run start --executor-id <你的身份> --lease-wallet` 建；若你们的控制根不是同一个目录，要先对齐。"
    )


def load(control_root: str | Path, *, run_id: str, owner_id: str) -> str:
    """The token kept for ``owner_id`` on ``run_id``; refused when the wallet belongs to another holder."""

    record = find(control_root, run_id)
    if record is None:
        raise LeaseWalletError(f"本机钱包里没有 {run_id} 的口令{missing_hint(control_root, run_id)}")
    if record["owner_id"] != owner_id:
        raise LeaseWalletError(f"{run_id} 的钱包属于 {record['owner_id']}，不属于 {owner_id}")
    return str(record["lease_token"])
