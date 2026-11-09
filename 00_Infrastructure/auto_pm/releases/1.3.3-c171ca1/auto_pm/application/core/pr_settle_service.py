"""Read-only scan for Runs whose work is already merged into main but whose Run, Mission and change record are still open (D-32).

A merge on GitHub triggers nothing in the ledger: the Run, the Mission and the change record stay "in progress" until somebody
remembers them.  This scan finds them and prints, for each, the commands that are legal next.  It writes nothing and settles
nothing: acceptance stays the user's act, and a Run, Work or Mission is never moved here (``continuity run/work/mission
transition`` must not be used on its own, AGENTS.md).

A Run counts as merged when its newest known commit is not the commit it started from and is an ancestor of ``origin/main``.  The
newest known commit is the HEAD of the Run's worktree while that still exists, otherwise the HEAD of its latest checkpoint.  The
answer is only as fresh as the last ``git fetch``; this scan does not go online.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.contracts.continuity import RunItem
from auto_pm.contracts.mission import MissionState
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.control_root_guard import clean_git_environment
from auto_pm.infrastructure.git_timeout import run_git_bounded_text

DEFAULT_BASE = "origin/main"


class PrSettleError(RuntimeError):
    """The scan could not be done (no ledger, no base ref)."""


@dataclass(frozen=True)
class SettleItem:
    run_id: str
    work_id: str
    run_state: str
    mission_id: str | None
    mission_state: str | None
    lease_expired: bool
    head: str
    merged: bool
    why: str
    next_steps: tuple[str, ...]


class PrSettleService:
    def __init__(
        self,
        root: str | Path,
        store: ContinuityStore | None = None,
        *,
        base_ref: str = DEFAULT_BASE,
    ) -> None:
        self._root = Path(root)
        self._store = store or ContinuityStore(self._root)
        self._base = base_ref

    def scan(self, project_id: str) -> tuple[SettleItem, ...]:
        """Every live Run of the project with whether its work is already in the base branch, newest facts first."""
        self._require_base()
        try:
            missions = {
                m.root_work_id: m for m in self._store.list_missions(project_id) if m.root_work_id
            }
            works = self._store.list_works(project_id)
        except ContinuityStoreError as error:
            raise PrSettleError(str(error)) from error
        items: list[SettleItem] = []
        for work in works:
            for run in self._store.list_runs(work.work_id):
                items.append(self._judge(run, missions.get(work.work_id)))
        return tuple(sorted(items, key=lambda item: item.run_id))

    # ── judging one Run ──────────────────────────────────────────

    def _judge(self, run: RunItem, mission: object | None) -> SettleItem:
        head = self._newest_head(run)
        merged, why = self._merged(run, head)
        expired = self._lease_expired(run.run_id)
        mission_id = getattr(mission, "mission_id", None)
        mission_state = getattr(getattr(mission, "state", None), "value", None)
        steps = (
            self._next_steps(run.run_id, run.work_id, mission_id, mission_state, expired)
            if merged
            else ()
        )
        return SettleItem(
            run.run_id,
            run.work_id,
            run.state.value,
            mission_id,
            mission_state,
            expired,
            head,
            merged,
            why,
            steps,
        )

    def _newest_head(self, run: RunItem) -> str:
        worktree = Path(run.worktree_path)
        if worktree.is_dir():
            head = self._git(worktree, "rev-parse", "--verify", "HEAD")
            if head.returncode == 0 and head.stdout.strip():
                return head.stdout.strip()
        checkpoint = self._store.latest_checkpoint(run.run_id)
        return checkpoint.git_head if checkpoint is not None else run.git_head

    def _merged(self, run: RunItem, head: str) -> tuple[bool, str]:
        if head == run.git_head:
            return False, "no commit since the Run started"
        result = self._git(self._root, "merge-base", "--is-ancestor", head, self._base)
        if result.returncode == 0:
            return True, f"{head[:12]} is in {self._base}"
        if result.returncode == 1:
            return False, f"{head[:12]} is not in {self._base} yet"
        return False, f"unknown: git could not judge {head[:12]} ({result.stderr.strip()[:120]})"

    def _lease_expired(self, run_id: str) -> bool:
        try:
            lease = self._store.get_lease(run_id)
        except ContinuityStoreError:
            return False
        expires = datetime.fromisoformat(lease.expires_at.replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return expires <= datetime.now(UTC)

    @staticmethod
    def _next_steps(
        run_id: str, work_id: str, mission_id: str | None, mission_state: str | None, expired: bool
    ) -> tuple[str, ...]:
        steps: list[str] = []
        if mission_id is None:
            steps.append(
                f"这个 Run（{work_id}）没有绑定 Mission：交主执行按它的变更单收口，不要单独转 Run、Work 的状态"
            )
        elif mission_state == MissionState.ACCEPTED.value:
            steps.append(
                f"main.py pm close --mission-id {mission_id}   # 已验收，一步收口（并回文件、推进 Run/Work/Mission、写变更单证据）"
            )
        elif mission_state in {MissionState.CLOSED.value, MissionState.CANCELLED.value}:
            steps.append(
                f"Mission {mission_id} 已是 {mission_state} 而 Run 还开着：main.py continuity recovery plan --pid <项目> --run-id {run_id}"
            )
        else:
            steps.append(
                f"PR 已并入，Mission {mission_id} 还是 {mission_state}：等用户验收（驾驶舱“确认验收”，或用户本人在终端 main.py pm accept --mission-id {mission_id}），之后 main.py pm close --mission-id {mission_id}"
            )
        if expired:
            steps.append(
                f"租约已过期：main.py continuity recovery plan --pid <项目> --run-id {run_id}   # 只打印恢复链，不执行"
            )
        steps.append(
            "变更单：收口后 main.py change transition <CHG> completed --pid <项目>；再 main.py ledger reconcile <项目>"
        )
        return tuple(steps)

    # ── git ──────────────────────────────────────────────────────

    def _require_base(self) -> None:
        if (
            self._git(
                self._root, "rev-parse", "--verify", "--quiet", f"{self._base}^{{commit}}"
            ).returncode
            != 0
        ):
            raise PrSettleError(f"找不到 {self._base}：先 git fetch origin main（本命令不联网）")

    @staticmethod
    def _git(where: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return run_git_bounded_text(
            ["git", "-C", str(where), *args],
            default_timeout=30.0,
            error_cls=PrSettleError,
            where=where,
            capture_output=True,
            check=False,
            env=clean_git_environment(),
        )


def render(items: tuple[SettleItem, ...]) -> list[str]:
    """Plain lines for the terminal; only the merged-but-still-open Runs get the next-step list."""
    waiting = [item for item in items if item.merged]
    lines = [f"开着的 Run {len(items)} 个，其中 {len(waiting)} 个的工作已并入主线、等着收口。"]
    for item in waiting:
        lines.append(
            f"- {item.run_id}（{item.run_state}，Work {item.work_id}，Mission {item.mission_id or '无'}"
            f"{'，租约已过期' if item.lease_expired else ''}）：{item.why}"
        )
        lines.extend(f"    {step}" for step in item.next_steps)
    for item in items:
        if not item.merged:
            lines.append(f"- {item.run_id}（{item.run_state}）：{item.why}")
    return lines
