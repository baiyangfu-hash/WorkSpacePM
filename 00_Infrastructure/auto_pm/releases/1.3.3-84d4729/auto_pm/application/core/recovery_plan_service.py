"""Read-only exit-chain printer for ``continuity recovery plan`` (CHG-SCPT-2026-476, interlock matrix P0).

The settlement of one abandoned Run is at least ten commands with many identifiers; done by hand it goes wrong.  This service
reads the abnormal-state table of the interlock matrix, fills what the ledger already knows (project, Run, Work) and prints the
rest as ``<PLACEHOLDER>``.  It never writes the ledger and never runs a command.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.contracts.continuity import RunState, WorkState
from auto_pm.contracts.interlock_matrix import STATES, AbnormalState, conflict_state
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError

_FINISHED_WORK = frozenset({WorkState.ACCEPTED, WorkState.CLOSED, WorkState.CANCELLED})
_TERMINAL_RUN = frozenset({RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED})
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


class RecoveryPlanError(RuntimeError):
    """The plan cannot be built (unknown state, unknown Run, nothing abnormal to plan for)."""


def fill(template: str, values: dict[str, str]) -> str:
    """Replace ``{name}`` with the known value, or ``<NAME>`` when the ledger does not know it."""

    return _PLACEHOLDER.sub(lambda match: values.get(match.group(1)) or f"<{match.group(1).upper()}>", template)


class RecoveryPlanService:
    def __init__(self, workspace_root: str | Path, now: datetime | None = None) -> None:
        self._store = ContinuityStore(Path(workspace_root).resolve())
        self._now = now

    def detect_run_state(self, run_id: str) -> str:
        """Which registered state a named Run is in (read-only); raises when it is in none."""

        try:
            run = self._store.get_run(run_id)
            work = self._store.get_work(run.work_id)
            lease = self._store.get_lease(run_id)
        except ContinuityStoreError as error:
            raise RecoveryPlanError(f"读不到 Run {run_id}: {error}") from error
        if run.state in _TERMINAL_RUN:
            raise RecoveryPlanError(f"Run {run_id} 已是终态 {run.state.value}，没有要处理的异常")
        if work.state in _FINISHED_WORK:
            return "LIVE_RUN_UNDER_FINISHED_WORK"
        now = self._now or datetime.now(UTC)
        if datetime.fromisoformat(lease.expires_at) <= now.astimezone(UTC):
            return "LEASE_EXPIRED"
        raise RecoveryPlanError(f"Run {run_id} 的租约有效、Work 未结束，账本里没有登记的异常状态")

    def values_for(self, project_id: str, run_id: str, work_id: str) -> dict[str, str]:
        values = {"pid": project_id}
        if run_id:
            values["run_id"] = run_id
            if not work_id:
                try:
                    work_id = self._store.get_run(run_id).work_id
                except ContinuityStoreError:
                    work_id = ""
        if work_id:
            values["work_id"] = work_id
        return values

    def render(self, state: AbnormalState, values: dict[str, str]) -> list[str]:
        lines = [
            f"状态 {state.state_id}: {state.title}",
            f"探测: {state.detector}",
            f"谁能做: {state.who.value} | 切换发版时可放行: "
            f"{'-' if state.switch_safe is None else ('是' if state.switch_safe else '否')} | 最低代码版本: {state.needs_code_version}",
        ]
        if not state.exit_steps:
            lines.append("出口: 矩阵登记为缺口，没有现成命令。不要自己改账本，交给协调者。")
            return lines
        lines.append("出口（按顺序；<大写> 是要你填的值；本命令只打印，不执行）:")
        for index, step in enumerate(state.exit_steps, start=1):
            tag = "[人工] " if step.manual else ""
            lines.append(f"  {index}. {tag}{step.title}  (谁: {step.who.value})")
            if step.command:
                lines.append(f"     $ {fill(step.command, values)}")
            if step.needs:
                lines.append(f"     前提: {', '.join(step.needs)}")
            if step.note:
                lines.append(f"     注: {step.note}")
        return lines

    def plan(self, *, project_id: str, state_id: str = "", run_id: str = "", work_id: str = "") -> list[str]:
        """The printed plan for one explicit state, or the state the named Run is in."""

        if not state_id:
            if not run_id:
                raise RecoveryPlanError("请给 --state 或 --run-id")
            state_id = self.detect_run_state(run_id)
        state = STATES.get(state_id)
        if state is None:
            raise RecoveryPlanError(f"矩阵里没有状态 {state_id}；已登记: {', '.join(sorted(STATES))}")
        return self.render(state, self.values_for(project_id, run_id, work_id))

    def plan_for_conflicts(self, *, project_id: str, conflicts: tuple[str, ...]) -> list[str]:
        """One plan per distinct state behind the conflict codes ``pm orient`` reports (several conflicts are all planned)."""

        lines: list[str] = []
        seen: set[str] = set()
        for code in conflicts:
            state = conflict_state(code)
            if state is None:
                raise RecoveryPlanError(f"冲突码 {code} 不在矩阵里，请先登记（interlock_matrix.STATES）")
            if state.state_id in seen:
                continue
            seen.add(state.state_id)
            if lines:
                lines.append("")
            lines.extend(self.render(state, {"pid": project_id}))
        return lines
