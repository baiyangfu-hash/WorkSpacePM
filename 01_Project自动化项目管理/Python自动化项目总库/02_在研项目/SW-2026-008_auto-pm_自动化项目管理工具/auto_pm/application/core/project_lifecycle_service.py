"""Project archive and reactivate (CHG-SCPT-2026-652): the checks, the dry-run plan and the one registry field they flip.

Archiving only sets the project's status in the Workspace Registry to ``archived``; the folder, the ID and the path
stay where they are.  Before that, five things are checked and any one of them refuses (fail closed: a ledger, Git or
inbox that cannot be read also refuses):

1. no open Mission, Work or Run            (``project_delete_guard.open_work_blockers``, reused)
2. every CLOSED Mission has a COMPLETED closure record
3. no ACCEPTED Mission or Work that was never closed
4. no uncommitted change in the folder     (``project_delete_guard.uncommitted_blockers``, reused)
5. no open inbox item (PROPOSED or CONFIRMED, i.e. ``OPEN_INTAKE_STATUSES``)

Change orders that are not ``completed`` are listed as a hint only; they never refuse.

This module also builds the ``deleted`` rows ``project list --status deleted`` shows: a deleted project's folder is in
the recycle area, so a directory scan cannot find it and the rows come from the registry instead.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from auto_pm.application.core.pm_intake_service import PmIntakeService
from auto_pm.application.core.project_delete_guard import (
    list_recycled,
    open_work_blockers,
    uncommitted_blockers,
)
from auto_pm.application.core.workspace_registry_service import (
    StatusChange,
    WorkspaceRegistryError,
    WorkspaceRegistryService,
)
from auto_pm.contracts.continuity import WorkState
from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.workspace_context import status_label
from auto_pm.domain.change.change_service import ChangeService
from auto_pm.infrastructure.continuity_store import ContinuityStore

log = logging.getLogger(__name__)

#: Statuses ``project archive`` accepts as a starting point (an entry with no status counts as ``active``).
ARCHIVABLE_STATUSES: tuple[str, ...] = ("active", "paused")

CHECK_OPEN_WORK = "卡全关"
CHECK_CLOSURE = "收口走完"
CHECK_ACCEPTED = "没有已验收没收口的卡"
CHECK_UNCOMMITTED = "没有没提交的改动"
CHECK_INBOX = "收件箱没有待处理条目"


class ProjectLifecycleError(RuntimeError):
    """The project cannot be archived or reactivated; nothing was written."""


@dataclass(frozen=True)
class LifecycleCheck:
    """One of the five archive checks: its name and what it found (nothing found means it passed)."""

    name: str
    problems: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.problems


@dataclass(frozen=True)
class LifecyclePlan:
    """What ``archive`` / ``reactivate`` would do; ``refusal`` or a failed check means it must not be written."""

    project_id: str
    status_before: str
    status_after: str
    refusal: str = ""
    checks: tuple[LifecycleCheck, ...] = ()
    change_hints: tuple[str, ...] = ()

    @property
    def blockers(self) -> tuple[str, ...]:
        """Every reason not to write, each led by the check it comes from."""

        found = [self.refusal] if self.refusal else []
        found += [f"{check.name}：{problem}" for check in self.checks for problem in check.problems]
        return tuple(found)

    @property
    def change_line(self) -> str:
        return (
            f"登记表里 {self.project_id} 的项目状态："
            f"{status_label(self.status_before)} → {status_label(self.status_after)}（别的栏、别的项目不动，目录不搬）"
        )


@dataclass(frozen=True)
class DeletedProject:
    """One registry entry whose status is ``deleted`` and whether its folder is still in the recycle area."""

    project_id: str
    project_root: str
    kind: str
    restorable: bool

    @property
    def hint(self) -> str:
        if self.restorable:
            return f"可以用 project restore {self.project_id} 搬回"
        return "回收区里找不到（可能已手工清掉）"


def _has_ledger(control_root: str | Path) -> bool:
    return (Path(control_root) / ".auto-pm" / "continuity.db").is_file()


def closure_blockers(control_root: str | Path, project_id: str) -> list[str]:
    """CLOSED Missions of the project whose closure record is not COMPLETED (stuck at PREPARED, or missing)."""

    if not _has_ledger(control_root):
        return []
    try:
        store = ContinuityStore(Path(control_root))
        return [
            f"Mission {mission.mission_id} 已关（CLOSED），但收口记录不是 COMPLETED"
            "（停在 PREPARED，或者查不到收口记录）；先用 D 单的办法收掉"
            for mission in store.list_missions(project_id, include_terminal=True)
            if mission.state is MissionState.CLOSED and not store.has_completed_closure(mission.mission_id)
        ]
    except Exception as error:  # 读不出来一律不放行
        return [f"读不出本机账本，无法确认收口有没有走完：{error}"]


def accepted_blockers(control_root: str | Path, project_id: str) -> list[str]:
    """ACCEPTED Missions and Work of the project: accepted but never closed, which the open-work check lets through."""

    if not _has_ledger(control_root):
        return []
    advice = "先在驾驶舱点确认验收收口，或用 pm close"
    try:
        store = ContinuityStore(Path(control_root))
        found = [
            f"Mission {mission.mission_id} 已验收（ACCEPTED）还没收口；{advice}"
            for mission in store.list_missions(project_id, include_terminal=True)
            if mission.state is MissionState.ACCEPTED
        ]
        found += [
            f"Work {work.work_id} 已验收（ACCEPTED）还没收口；{advice}"
            for work in store.list_works(project_id, include_terminal=True)
            if work.state is WorkState.ACCEPTED
        ]
        return found
    except Exception as error:  # 读不出来一律不放行
        return [f"读不出本机账本，无法确认有没有已验收没收口的卡：{error}"]


def inbox_blockers(control_root: str | Path, project_id: str) -> list[str]:
    """Open inbox items of the project (PROPOSED 待确认 and CONFIRMED 待处理); an unreadable inbox also blocks."""

    try:
        items = PmIntakeService(control_root).list_items(project_id)
    except Exception as error:  # 读不出来一律不放行
        return [f"读不出收件箱，无法确认有没有待处理条目：{error}"]
    return [f"收件箱条目 {item.item_id}（{item.status.value}）：{item.title}" for item in items]


def open_change_hints(workspace_root: str | Path, project_id: str) -> list[str]:
    """Hint only, never a refusal: the project's change orders that are not ``completed`` (number and status)."""

    try:
        summaries = ChangeService(str(workspace_root)).list_change_requests(project_id)
    except Exception as error:
        return [f"读不出变更记录（{error}），请自己核对有没有没收口的变更单"]
    return sorted(
        f"{summary.change_number}（{summary.status}）" for summary in summaries if summary.status != "completed"
    )


def archive_checks(
    workspace_root: str | Path, project_id: str, project_path: str | Path, *, control_root: str | Path
) -> tuple[LifecycleCheck, ...]:
    """Run the five checks; read-only."""

    return (
        LifecycleCheck(CHECK_OPEN_WORK, tuple(open_work_blockers(control_root, project_id))),
        LifecycleCheck(CHECK_CLOSURE, tuple(closure_blockers(control_root, project_id))),
        LifecycleCheck(CHECK_ACCEPTED, tuple(accepted_blockers(control_root, project_id))),
        LifecycleCheck(CHECK_UNCOMMITTED, tuple(uncommitted_blockers(workspace_root, project_path))),
        LifecycleCheck(CHECK_INBOX, tuple(inbox_blockers(control_root, project_id))),
    )


def _registered_status(workspace_root: str | Path, project_id: str) -> tuple[str, str]:
    """(status, refusal): the entry's status as written, or why the registry cannot answer."""

    try:
        entry = WorkspaceRegistryService(workspace_root).find(project_id)
    except (WorkspaceRegistryError, OSError) as error:
        return "", f"读不出工作区登记表：{error}"
    if entry is None:
        return "", f"项目 {project_id} 不在工作区登记表里；先用 project register {project_id} 登记"
    return entry.status, ""


def plan_archive(
    workspace_root: str | Path, project_id: str, project_path: str | Path, *, control_root: str | Path | None = None
) -> LifecyclePlan:
    """Dry run of ``project archive``: status now, the five checks and the open change orders; writes nothing."""

    status, refusal = _registered_status(workspace_root, project_id)
    if not refusal and (status or "active") not in ARCHIVABLE_STATUSES:
        refusal = f"项目 {project_id} 现在的状态是“{status_label(status)}”，只有在研或暂停的项目能归档"
    return LifecyclePlan(
        project_id=project_id,
        status_before=status,
        status_after="archived",
        refusal=refusal,
        checks=archive_checks(workspace_root, project_id, project_path, control_root=control_root or workspace_root),
        change_hints=tuple(open_change_hints(workspace_root, project_id)),
    )


def plan_reactivate(workspace_root: str | Path, project_id: str) -> LifecyclePlan:
    """Dry run of ``project reactivate``: only an archived project can go back to active; writes nothing."""

    status, refusal = _registered_status(workspace_root, project_id)
    if not refusal and status != "archived":
        refusal = f"项目 {project_id} 现在的状态是“{status_label(status)}”，不是“已归档”，不能重新激活"
    return LifecyclePlan(project_id=project_id, status_before=status, status_after="active", refusal=refusal)


def apply_plan(workspace_root: str | Path, plan: LifecyclePlan) -> StatusChange:
    """Write the one status field a clean plan names; a plan with any blocker is refused here as well."""

    if plan.blockers:
        raise ProjectLifecycleError("；".join(plan.blockers))
    only_from = ARCHIVABLE_STATUSES if plan.status_after == "archived" else ("archived",)
    try:
        change = WorkspaceRegistryService(workspace_root).set_status(
            plan.project_id, plan.status_after, only_from=only_from
        )
    except (WorkspaceRegistryError, OSError) as error:
        raise ProjectLifecycleError(f"登记表没有改：{error}") from error
    if change is None or not change.written:
        raise ProjectLifecycleError(f"登记表里找不到项目 {plan.project_id}，没有改")
    return change


def deleted_projects(workspace_root: str | Path) -> list[DeletedProject]:
    """Registry entries whose status is ``deleted``, by project ID; read-only.

    A registry that is missing or cannot be read gives no rows and a logged warning, the same way ``project list``
    then shows every scanned project as unregistered.
    """

    try:
        entries = WorkspaceRegistryService(workspace_root).registry().projects
    except (WorkspaceRegistryError, OSError) as error:
        log.warning("读不出工作区登记表，列不出已删除的项目: %s", error)
        return []
    recycled = {item.project_id for item in list_recycled(workspace_root)}
    return sorted(
        (
            DeletedProject(item.project_id, item.project_root, item.kind, item.project_id in recycled)
            for item in entries
            if item.status == "deleted"
        ),
        key=lambda item: item.project_id,
    )
