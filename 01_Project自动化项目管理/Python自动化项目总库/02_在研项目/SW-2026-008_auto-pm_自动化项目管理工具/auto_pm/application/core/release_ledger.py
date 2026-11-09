"""Deploy bookkeeping for the one-command release: change order, Decision, Work, Run, Checkpoint, closure and the receipt (D-146 card 3).

This is the ledger half of the hand-written D07M script, as a resumable sequence.  Every step first asks the ledger where things stand and does
only what is missing, so a run killed half way can be started again (re-run the same ``release deploy`` command) without creating a second change order, Work or Run.
It runs the **same cockpit commands** the script ran, through an injected port (the real port shells out to ``main.py``; the tests use a fake
that behaves like the ledger).  The ``approved`` step needs the user's confirmation reference and is refused without one: this module never
invents an approval.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

PROJECT_ID = "SW-2026-008"
CHANGE_WALK = ("draft", "submitted", "under_review", "approved", "implementing")
CLOSE_WALK = ("implementing", "pending_acceptance", "accepting", "completed")
WORK_CLOSE = ("IN_PROGRESS", "VERIFYING", "ACCEPTED", "CLOSED")
CONFIRM_PREFIX = "user-confirmation:"
_CHG = re.compile(r"CHG-[A-Z]+-\d{4}-\d+")


class LedgerError(RuntimeError):
    """The bookkeeping could not continue; the message says which step and what to do."""


class LedgerPort(Protocol):
    def cli(self, *args: str) -> str: ...
    def find_change(self, release_id: str) -> str:
        """Id of the change order whose references carry ``RELEASE=<release_id>``, or ``""`` when there is none."""
        ...
    def change_status(self, change_id: str) -> str: ...
    def decision_exists(self, decision_id: str) -> bool: ...
    def work_state(self, work_id: str) -> str | None: ...
    def run_state(self, run_id: str) -> str | None: ...
    def checkpoint_exists(self, checkpoint_id: str) -> bool: ...
    def ensure_station(self, path: Path) -> None: ...


@dataclass(frozen=True)
class DeployPlan:
    release_id: str
    old_release: str
    commit: str
    confirm_ref: str
    approver: str
    paths: tuple[str, ...]
    station: Path
    evidence_dir: Path
    decision_id: str = ""

    def __post_init__(self) -> None:
        reference = self.confirm_ref
        if not reference.startswith(CONFIRM_PREFIX) or len(reference[len(CONFIRM_PREFIX):].strip()) < 6:
            raise LedgerError("缺少用户确认引用：--confirm-ref 写成 user-confirmation:<用户那条消息的时间或编号>；没有它不批准、不部署")
        if not self.decision_id:
            # The id carries a date; a resume after UTC midnight must reuse the first run's id, not mint a second Decision.
            saved = _load_state_file(self.state_file).get("decision_id", "")
            object.__setattr__(self, "decision_id", saved or f"DEC-{datetime.now(UTC):%Y%m%d}-DEPLOY{self.slug[-8:]}")

    @property
    def slug(self) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "-", self.release_id).strip("-").upper()

    @property
    def work_id(self) -> str:
        return f"WORK-DEPLOY-{self.slug}"

    @property
    def run_id(self) -> str:
        return f"RUN-DEPLOY-{self.slug}"

    @property
    def checkpoint_id(self) -> str:
        return f"CKPT-DEPLOY-{self.slug}"

    @property
    def owner(self) -> str:
        return f"claude:deploy-{self.slug.lower()}"

    @property
    def state_file(self) -> Path:
        return self.evidence_dir / "state.json"


@dataclass
class Books:
    change_id: str = ""
    steps: list[str] = field(default_factory=list)


def pick_change(release_id: str, candidates: Sequence[tuple[str, str]]) -> str:
    """The change order for ``release_id`` among ``(change_id, references)`` rows, or ``""`` when none.

    The match is exact on the ``RELEASE=<id>`` item of the ``;``-separated references (never a substring: ``1.3.3-abc`` must not claim
    ``1.3.3-abcdef0``), and more than one hit is an error rather than a pick.  The real ledger port feeds its rows through this.
    """

    wanted = f"RELEASE={release_id}"
    hits = [change_id for change_id, references in candidates if wanted in (item.strip() for item in references.split(";"))]
    if len(hits) > 1:
        raise LedgerError(f"发布号 {release_id} 在账本里有 {len(hits)} 张变更单（{', '.join(hits)}），不能任取一张；请人工确认后删除多余的")
    return hits[0] if hits else ""


def _load_state_file(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _load_state(plan: DeployPlan) -> dict[str, str]:
    return _load_state_file(plan.state_file)


def _save_state(plan: DeployPlan, state: dict[str, str]) -> None:
    plan.evidence_dir.mkdir(parents=True, exist_ok=True)
    temporary = plan.state_file.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(plan.state_file)


def _walk(port: LedgerPort, change_id: str, sequence: Sequence[str], plan: DeployPlan, books: Books, comments: dict[str, str]) -> None:
    """Move the change order along ``sequence`` from wherever it is; each transition is one cockpit command."""

    for _ in range(len(sequence) + 1):
        status = port.change_status(change_id)
        if status not in sequence:
            hint = "（这个发布号已有一张走完的变更单：已完成或已拒绝，不能再续）" if status in ("completed", "rejected", "cancelled") else ""
            raise LedgerError(f"变更单 {change_id} 处于 {status or '未知'}，不在可续的路径 {sequence} 上{hint}")
        if status == sequence[-1]:
            return
        target = sequence[sequence.index(status) + 1]
        args = ["change", "transition", change_id, "--pid", PROJECT_ID, "--to", target, "--approver", plan.approver]
        if target == "approved":
            args += ["--approval-evidence-ref", plan.confirm_ref]
        if target in comments:
            args += ["--verification-conclusion" if target == "completed" else "--comment", comments[target]]
        port.cli(*args)
        books.steps.append(f"change {status} -> {target}")
    raise LedgerError(f"变更单 {change_id} 没能走到 {sequence[-1]}")


def open_books(plan: DeployPlan, port: LedgerPort, *, background: str, necessity: str) -> Books:
    """Change order -> approved/implementing, Decision, Work (authorized), station, Run (RUNNING), Work IN_PROGRESS.  Resumable."""

    books = Books()
    state = _load_state(plan)
    if state.get("decision_id") != plan.decision_id:
        state["decision_id"] = plan.decision_id
        _save_state(plan, state)
    change_id = state.get("change_id", "")
    if not change_id:
        # Killed between "change create" and the state write: the order exists in the ledger but not in state.json.
        change_id = port.find_change(plan.release_id)
        if change_id:
            state["change_id"] = change_id
            _save_state(plan, state)
            books.steps.append(f"change adopt {change_id}")
    if not change_id:
        out = port.cli(
            "change", "create", "--pid", PROJECT_ID, "--domain", "SCPT", "--nature", "CFG", "--scope", "SYSTEM", "--applicant", plan.approver,
            "--background", background, "--necessity", necessity,
            "--references", f"RELEASE={plan.release_id}; COMMIT={plan.commit}; PREVIOUS={plan.old_release}; {plan.confirm_ref}", "--urgency", "normal",
        )
        found = _CHG.findall(out)
        if not found:
            raise LedgerError("解析不出新建变更单的编号")
        change_id = found[-1]
        state["change_id"] = change_id
        _save_state(plan, state)
        books.steps.append(f"change create {change_id}")
    books.change_id = change_id
    _walk(port, change_id, CHANGE_WALK, plan, books, {})

    if not port.decision_exists(plan.decision_id):
        args = ["decision", "create", "--change-id", change_id, "--pid", PROJECT_ID, "--approver", plan.approver,
                "--approval-evidence-ref", plan.confirm_ref, "--decision-id", plan.decision_id]
        for path in plan.paths:
            args += ["--file", path]
        port.cli(*args, "--condition", f"仅写入 releases/{plan.release_id}、清单与两个指针；切换后核验任一失败即回退指针；不回滚数据库、不合并 main")
        books.steps.append("decision create")

    if port.work_state(plan.work_id) is None:
        args = ["continuity", "work", "create", "--work-id", plan.work_id, "--pid", PROJECT_ID, "--kind", "WBS",
                "--title", f"发布 {plan.release_id}", "--owner", plan.owner, "--idempotency-key", f"{plan.slug}-work-create"]
        for path in plan.paths:
            args += ["--scope", path]
        port.cli(*args)
        books.steps.append("work create")
    if port.work_state(plan.work_id) == "PLANNED":
        port.cli("continuity", "work", "authorize", "--work-id", plan.work_id, "--decision-id", plan.decision_id, "--idempotency-key", f"{plan.slug}-work-auth")
        books.steps.append("work authorize")

    if port.run_state(plan.run_id) is None:
        port.ensure_station(plan.station)
        args = ["continuity", "run", "start", "--run-id", plan.run_id, "--work-id", plan.work_id, "--executor", plan.owner, "--adapter", "claude-code",
                "--worktree", str(plan.station), "--lease-wallet", "--lease-seconds", "3600", "--idempotency-key", f"{plan.slug}-run-start"]
        for path in plan.paths:
            args += ["--owned", path, "--declared-dirty", path]
        port.cli(*args)
        books.steps.append("run start")
    if port.run_state(plan.run_id) == "READY":
        port.cli("continuity", "run", "transition", "--run-id", plan.run_id, "--to", "RUNNING", "--owner", plan.owner, "--lease-wallet", "--idempotency-key", f"{plan.slug}-run-running")
        books.steps.append("run RUNNING")
    if port.work_state(plan.work_id) == "READY":
        port.cli("continuity", "work", "transition", "--work-id", plan.work_id, "--to", "IN_PROGRESS", "--idempotency-key", f"{plan.slug}-work-inprogress")
        books.steps.append("work IN_PROGRESS")
    return books


def close_books(plan: DeployPlan, port: LedgerPort, *, change_id: str, evidence: Sequence[str], conclusion: str) -> Books:
    """Checkpoint, Run SUCCEEDED, Work CLOSED, change order completed.  Only called after the switch and its checks passed.  Resumable."""

    books = Books(change_id=change_id)
    if not port.checkpoint_exists(plan.checkpoint_id):
        args = ["continuity", "checkpoint", "create", "--checkpoint-id", plan.checkpoint_id, "--run-id", plan.run_id, "--owner", plan.owner,
                "--lease-wallet", "--summary", f"有效版本已切换到 {plan.release_id}（上一版 {plan.old_release}），切换后核验通过",
                "--idempotency-key", f"{plan.slug}-checkpoint"]
        for item in evidence:
            args += ["--evidence", item]
        port.cli(*args)
        books.steps.append("checkpoint create")
    for current, target in (("RUNNING", "VERIFYING"), ("VERIFYING", "SUCCEEDED")):
        if port.run_state(plan.run_id) == current:
            port.cli("continuity", "run", "transition", "--run-id", plan.run_id, "--to", target, "--owner", plan.owner, "--lease-wallet", "--idempotency-key", f"{plan.slug}-run-{target.lower()}")
            books.steps.append(f"run {target}")
    if port.run_state(plan.run_id) != "SUCCEEDED":
        raise LedgerError(f"Run {plan.run_id} 没到 SUCCEEDED：{port.run_state(plan.run_id)}")
    for _ in range(len(WORK_CLOSE)):
        state = port.work_state(plan.work_id)
        if state == "CLOSED":
            break
        if state not in WORK_CLOSE:
            raise LedgerError(f"Work {plan.work_id} 处于 {state}，不在可续的路径上")
        target = WORK_CLOSE[WORK_CLOSE.index(state) + 1]
        port.cli("continuity", "work", "transition", "--work-id", plan.work_id, "--to", target, "--idempotency-key", f"{plan.slug}-work-{target.lower()}")
        books.steps.append(f"work {target}")
    else:
        if port.work_state(plan.work_id) != "CLOSED":
            raise LedgerError(f"Work {plan.work_id} 发出收口命令后仍没到 CLOSED：{port.work_state(plan.work_id)}")
    _walk(port, change_id, CLOSE_WALK, plan, books, {"completed": conclusion})
    return books


def write_receipt(plan: DeployPlan, *, change_id: str, backup: str, entry_sha256: str, checks_sha256: str, rollback_command: str) -> Path:
    """The receipt of a finished deploy: every identifier and checksum a later reader needs, and the one command that undoes the switch."""

    receipt = {
        "release": plan.release_id, "commit": plan.commit, "previous": plan.old_release, "manifest_entry_sha256": entry_sha256,
        "pointer_backup": backup, "checkpoint": plan.checkpoint_id, "run": f"{plan.run_id} SUCCEEDED", "work": f"{plan.work_id} CLOSED",
        "change": f"{change_id} completed", "decision": plan.decision_id, "post_checks_sha256": checks_sha256,
        "rollback_command": rollback_command, "confirmation": plan.confirm_ref, "closed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "not_authorized": ["merge to main", "database rollback"],
    }
    plan.evidence_dir.mkdir(parents=True, exist_ok=True)
    path = plan.evidence_dir / "receipt.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
