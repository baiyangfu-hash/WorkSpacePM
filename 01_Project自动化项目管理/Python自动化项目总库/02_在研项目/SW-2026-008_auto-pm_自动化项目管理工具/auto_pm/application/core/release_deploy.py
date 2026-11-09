"""The one-command deploy as a sequence: preflight -> books -> build -> switch -> self-checks -> (roll back | close books + receipt) (D-146 card 4).

Only the **order and the safety rules** live here; every side effect goes through an injected port (release operations, the ledger, the
self-checks), so the whole sequence is tested on fakes.  Wiring it to the real ledger and switching it on in the CLI is a separate, later step:
nothing in this card deploys anything.

Safety rules, each pinned by a test:

* a preflight that is not fully green stops everything before a single byte is written;
* the self-check set must contain every name in ``REQUIRED_SELF_CHECKS``; a caller cannot quietly drop one;
* all self-checks run (a failure does not hide the next one), and **any** failure rolls the pointers back, then re-reads the identity;
* the books are closed only after the checks passed; after a rollback they stay open and the error lists every failed check;
* after a rollback the same confirmation reference cannot be used again (ruling of 2026-11-08): a new deploy needs a new one;
* the database is never rolled back and ``main`` is never merged.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from auto_pm.application.core.release_deploy_check import Preflight
from auto_pm.application.core.release_ledger import (
    Books,
    DeployPlan,
    LedgerError,
    LedgerPort,
    close_books,
    open_books,
    write_receipt,
)

# What the 69b7ed6 deploy checked, plus the two the 7th release had and 69b7ed6 dropped (kept on purpose, ruling of 2026-11-08).
REQUIRED_SELF_CHECKS = (
    "identity",
    *(f"help {name}" for name in (
        "pm handoff", "pm takeover", "pm orient", "continuity run reclaim", "continuity lease record-holder", "gui",
        "long-run", "pm state-backup", "pm triage", "claim", "pr", "release",
    )),
    "smoke pm orient SW-2026-008", "smoke pm orient SYS-2026-001", "card precheck",
    "ledger SW-2026-008", "ledger SYS-2026-001", "ledger SW-2026-009", "ledger DJ-2026-005",
    "exact-tree new", "exact-tree old", "exact-tree older",
    "pre-commit hook dry run", "event chain drill",
)

SelfCheck = Callable[[], tuple[bool, str]]


class DeployError(RuntimeError):
    """The deploy stopped; ``rolled_back`` says whether the pointers were put back."""

    def __init__(self, message: str, *, rolled_back: bool = False, failed: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.rolled_back = rolled_back
        self.failed = failed


class ReleaseOpsPort(Protocol):
    def active_release(self) -> str: ...
    def is_built(self, release_id: str) -> bool: ...
    def build(self) -> dict[str, Any]: ...
    def switch(self, backup: Path) -> dict[str, Any]: ...
    def rollback(self, backup: Path) -> dict[str, Any]: ...
    def manifest_entry_sha256(self, release_id: str) -> str: ...


@dataclass
class DeployResult:
    release_id: str
    change_id: str
    backup: str
    receipt: str
    checks: dict[str, str] = field(default_factory=dict)
    steps: list[str] = field(default_factory=list)


def _ensure_complete(checks: Mapping[str, SelfCheck]) -> None:
    missing = [name for name in REQUIRED_SELF_CHECKS if name not in checks]
    if missing:
        raise DeployError(f"自检清单缺 {len(missing)} 项，不能部署：{'；'.join(missing[:5])}{'…' if len(missing) > 5 else ''}")


def _refuse_reused_confirmation(plan: DeployPlan) -> None:
    try:
        failed = json.loads(plan.state_file.read_text(encoding="utf-8")).get("rolled_back_with", "")
    except (OSError, ValueError):
        failed = ""
    if failed and failed == plan.confirm_ref:
        raise DeployError("上一次部署已经回退过；重试需要用户给一个新的确认引用（不能沿用回退那次的）")


def _read_state(plan: DeployPlan) -> dict[str, Any]:
    try:
        data = json.loads(plan.state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _update_state(plan: DeployPlan, **values: str) -> None:
    state = _read_state(plan)
    state.update(values)
    plan.evidence_dir.mkdir(parents=True, exist_ok=True)
    plan.state_file.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def _mark_rolled_back(plan: DeployPlan) -> None:
    _update_state(plan, rolled_back_with=plan.confirm_ref)


def _first_backup(plan: DeployPlan, offered: Path) -> Path:
    """The backup of the **first** switch attempt: recorded before the pointers move, reused by every resume (a rollback must restore the
    pointers as they were before the deploy, not as they were before a later retry)."""

    recorded = str(_read_state(plan).get("backup", ""))
    if recorded:
        return Path(recorded)
    _update_state(plan, backup=str(offered))
    return offered


def run_self_checks(checks: Mapping[str, SelfCheck]) -> dict[str, tuple[bool, str]]:
    """Every required check, in order, none skipped after a failure; a check that raises counts as failed."""

    results: dict[str, tuple[bool, str]] = {}
    for name in REQUIRED_SELF_CHECKS:
        try:
            results[name] = checks[name]()
        except Exception as error:  # noqa: BLE001 - a crashing check is a failed check, never an abort that skips the rollback
            results[name] = (False, f"检查本身出错：{error}")
    return results


def deploy(
    plan: DeployPlan,
    *,
    preflight: Preflight,
    ops: ReleaseOpsPort,
    ledger: LedgerPort,
    checks: Mapping[str, SelfCheck],
    backup: Path,
    rollback_command: str,
    background: str,
    necessity: str,
) -> DeployResult:
    """Run the whole deploy; returns on success, raises ``DeployError`` otherwise (and says whether it rolled back)."""

    if not preflight.ok:
        raise DeployError("预检没通过，什么都没写：" + "；".join(f"{c.name}={c.status}" for c in preflight.checks if c.status != "PASS"))
    _ensure_complete(checks)
    _refuse_reused_confirmation(plan)
    backup = _first_backup(plan, backup)
    steps: list[str] = []
    try:
        books: Books = open_books(plan, ledger, background=background, necessity=necessity)
    except LedgerError as error:
        raise DeployError(f"建账没完成（可用 --resume 续）：{error}") from error
    steps.extend(books.steps)

    already_switched = ops.active_release() == plan.release_id
    entry: dict[str, Any] = {}
    if not already_switched:
        if not ops.is_built(plan.release_id):
            entry = ops.build()
            steps.append("build")
        try:
            ops.switch(backup)
            steps.append("switch")
        except Exception as error:  # noqa: BLE001 - whatever failed after the pointers may have moved is undone below
            return _undo(plan, ops, backup, steps, f"切换没成功：{error}", ())
    results = run_self_checks(checks)
    failed = tuple(name for name, (good, _detail) in results.items() if not good)
    if failed:
        return _undo(plan, ops, backup, steps, f"切换后自检 {len(failed)} 项没过：" + "；".join(f"{n}（{results[n][1]}）" for n in failed[:5]), failed)
    summary = json.dumps({name: detail for name, (_good, detail) in results.items()}, ensure_ascii=False, sort_keys=True)
    checks_sha = hashlib.sha256(summary.encode("utf-8")).hexdigest()
    entry_sha = str(entry.get("entry_sha256", "")) or ops.manifest_entry_sha256(plan.release_id)  # a resumed or already-built deploy has no build result
    if not entry_sha:
        raise DeployError("读不出清单条目的哈希，回执不能留空；已切换且自检通过，修好清单后可 --resume")
    try:
        closed = close_books(
            plan, ledger, change_id=books.change_id,
            evidence=[f"release={plan.release_id} commit={plan.commit} manifest_entry_sha256={entry_sha}", f"post_checks sha256={checks_sha}", f"confirmation {plan.confirm_ref}"],
            conclusion=f"验收通过：有效版本 active={plan.release_id}，previous={plan.old_release}；自检 {len(results)} 项全过；确认引用 {plan.confirm_ref}",
        )
    except LedgerError as error:
        raise DeployError(f"已切换且自检通过，但收口没完成（可用 --resume 续，不会再切换）：{error}") from error
    steps.extend(closed.steps)
    receipt = write_receipt(plan, change_id=books.change_id, backup=str(backup), entry_sha256=entry_sha, checks_sha256=checks_sha, rollback_command=rollback_command)
    return DeployResult(plan.release_id, books.change_id, str(backup), str(receipt), {n: d for n, (_g, d) in results.items()}, steps)


def _undo(plan: DeployPlan, ops: ReleaseOpsPort, backup: Path, steps: list[str], reason: str, failed: tuple[str, ...]) -> DeployResult:
    """Put the pointers back and verify the identity; the books stay open.  Always raises."""

    try:
        ops.rollback(backup)
    except Exception as error:  # noqa: BLE001
        raise DeployError(f"{reason}；回退也没成功：{error}。手工回退命令见回执或备份目录 {backup}", rolled_back=False, failed=failed) from error
    _mark_rolled_back(plan)
    raise DeployError(f"{reason}；已回退到 {plan.old_release}，账目保持打开。重试需要新的用户确认引用", rolled_back=True, failed=failed)
