"""删除项目前的护栏（TD-193）：先查开着的任务和未提交改动，再把目录搬进回收区，而不是直接 ``rmtree``。

``project delete --confirm`` 以前只有一个开关：不看项目有没有开着的 Mission / Work / Run，不看有没有没提交的改动，
删了就没了。这里只提供两件事，谁能下令删（用户本人的口令或原话、agent 一律不行）由命令层负责：

- ``delete_blockers``：列出挡住删除的原因（开着的 Mission、Work、Run；项目目录里没提交的改动；读不出来也算挡住）；
- ``recycle_project``：把项目目录整体搬到 ``<工作区>/.auto-pm/recycle/<项目编号>/<时间戳>/``，可原样搬回；
- ``list_recycled``：只读列出回收区里有什么、搬进来多久了（TD-208）。回收区没有任何自动清理，列表只为让人决定要不要手工清，这里不删任何东西。

CHG-SCPT-2026-650：

- ``recycle_project`` 搬完另记一张小记录（``.auto-pm/recycle-origins/<项目编号>/<时间戳>.json``，不放进回收区目录本身，
  回收区里照旧只有搬进来的目录），写明原来在工作区哪个目录，搬回时照它放回原处；
- ``mark_registry_deleted``：删除项目的公用一步，命令行 ``project delete`` 和窗口删除搬进回收区之后都调它，把登记表里这一条标“已删除”
  （不抹行）。不放进 ``recycle_project``：``project import --force`` 覆盖旧目录也调 ``recycle_project``，那不是删项目；
- ``plan_restore`` / ``restore_project``：把回收区的一份目录搬回原处，目标已有同名目录就拒绝，搬回后把登记表状态改回删除前的值。
  谁能下令搬回（只听用户本人）由命令层负责，和删除同一口径。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.application.core.approval_proof_service import ApprovalProofError, ApprovalProofService
from auto_pm.application.core.lease_handover_service import agent_markers
from auto_pm.contracts.continuity import RunState
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.git_timeout import run_git_bounded_strict_text

RECYCLE_RELATIVE_DIR = Path(".auto-pm") / "recycle"
ORIGINS_RELATIVE_DIR = Path(".auto-pm") / "recycle-origins"  # 回收区每份目录“原来在哪”的记录
_TERMINAL_RUN_STATES = frozenset({RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED})
_PROJECT_ID_PREFIX = re.compile(r"^([A-Z]{2,4}-\d{4}-\d{3})")


class ProjectDeleteError(RuntimeError):
    """项目目录不能安全地搬进回收区；什么都没动。"""


def open_work_blockers(control_root: str | Path, project_id: str) -> list[str]:
    """项目在本机账本里还开着的 Mission、Work 和 Run；账本读不出来时也返回一条挡住的原因（不放行）。"""

    root = Path(control_root)
    if not (root / ".auto-pm" / "continuity.db").is_file():
        return []
    blockers: list[str] = []
    try:
        store = ContinuityStore(root)
        for mission in store.list_missions(project_id):
            blockers.append(f"开着的 Mission {mission.mission_id}（{mission.state.value}）")
        for work in store.list_works(project_id):
            blockers.append(f"开着的 Work {work.work_id}（{work.state.value}）")
            for run in store.list_runs(work.work_id):
                if run.state not in _TERMINAL_RUN_STATES:
                    blockers.append(
                        f"开着的 Run {run.run_id}（{run.state.value}，Work {work.work_id}）"
                    )
    except ContinuityStoreError as error:
        blockers.append(f"读不出本机账本，无法确认有没有开着的任务：{error}")
    except Exception as error:  # 读不出来一律不放行
        blockers.append(f"读不出本机账本，无法确认有没有开着的任务：{error}")
    return blockers


def uncommitted_blockers(workspace_root: str | Path, project_path: str | Path) -> list[str]:
    """项目目录里没提交的改动（含未跟踪文件）；Git 读不出来也算挡住。"""

    try:
        done = run_git_bounded_strict_text(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", str(project_path)],
            default_timeout=60.0,
            error_cls=ProjectDeleteError,
            where=workspace_root,
            cwd=str(workspace_root),
            capture_output=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, ProjectDeleteError) as error:
        return [f"读不出 Git 状态，无法确认有没有没提交的改动：{error}"]
    if done.returncode != 0:
        return [f"读不出 Git 状态，无法确认有没有没提交的改动：{done.stderr.strip()}"]
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    if not lines:
        return []
    shown = "；".join(line.strip() for line in lines[:5])
    more = f" 等共 {len(lines)} 处" if len(lines) > 5 else ""
    return [f"项目目录里有没提交的改动：{shown}{more}"]


def delete_blockers(
    workspace_root: str | Path,
    project_id: str,
    project_path: str | Path,
    *,
    control_root: str | Path | None = None,
) -> list[str]:
    """挡住删除的全部原因；空表示可以删。"""

    return open_work_blockers(control_root or workspace_root, project_id) + uncommitted_blockers(
        workspace_root, project_path
    )


def overwrite_blockers(control_root: str | Path, directory_name: str) -> list[str]:
    """``project import --force`` 要覆盖的目录对应的项目还开着任务时的原因；目录名不带项目编号则账本里不会有它的任务。"""

    match = _PROJECT_ID_PREFIX.match(directory_name)
    return open_work_blockers(control_root, match.group(1)) if match else []


def surface_identity_problem(control_root: str | Path, environ: Mapping[str, str]) -> str:
    """界面（没有口令输入口）发起删除时的拒绝原因；空表示可以继续。

    带 agent 标记的环境一律拒绝；已启用批准口令时，界面无法验证用户本人，也拒绝并请用户到自己的终端用 ``project delete``。
    读不出批准口令配置时同样拒绝（不放行）。
    """

    markers = agent_markers(environ)
    if markers:
        return f"删除项目只听用户本人，当前环境带 agent 标记（{', '.join(markers)}）；请用户在自己的界面或终端操作"
    try:
        if ApprovalProofService(control_root).enforced():
            return "已启用批准口令，界面不能代替口令；请用户在自己的终端运行 project delete <项目编号> --confirm"
    except ApprovalProofError as error:
        return f"读不出批准口令配置，不放行：{error}"
    return ""


def recycle_project(
    workspace_root: str | Path,
    project_path: str | Path,
    project_id: str,
    *,
    now: datetime | None = None,
) -> Path:
    """把项目目录整体搬进回收区并返回新位置；目录不在工作区里面或就是工作区本身时拒绝。"""

    workspace = Path(workspace_root).resolve()
    source = Path(project_path).resolve()
    if source == workspace or workspace not in source.parents:
        raise ProjectDeleteError(f"项目目录必须在工作区里面（且不是工作区本身）：{source}")
    recycle_root = workspace / RECYCLE_RELATIVE_DIR
    if source == recycle_root or recycle_root in source.parents or source in recycle_root.parents:
        raise ProjectDeleteError(f"项目目录与回收区重叠，拒绝搬动：{source}")
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S%fZ")
    destination = recycle_root / project_id / stamp
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
    except OSError as error:
        raise ProjectDeleteError(
            f"搬进回收区失败（项目目录保持原样或请手工核对）：{error}"
        ) from error
    origin = {"project_id": project_id, "project_path": source.relative_to(workspace).as_posix()}
    try:
        record = _origin_file(workspace, project_id, stamp)
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(origin, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass  # 记录写不上不影响已经搬好的目录；搬回时退回去查登记表
    return destination


def _origin_file(workspace: Path, project_id: str, stamp: str) -> Path:
    return workspace / ORIGINS_RELATIVE_DIR / project_id / f"{stamp}.json"


def mark_registry_deleted(workspace_root: str | Path, project_id: str) -> str:
    """删除项目的公用一步：目录已经搬进回收区之后，把登记表里这一条标“已删除”，返回给人看的一句话。

    登记表里没有这个项目时什么都不写；登记表读不出或写不上时抛 ``ProjectDeleteError``（目录已在回收区，要告诉人）。
    """

    from auto_pm.application.core.workspace_registry_service import (
        WorkspaceRegistryError,
        WorkspaceRegistryService,
    )

    try:
        changed = WorkspaceRegistryService(workspace_root).mark_deleted(project_id)
    except (WorkspaceRegistryError, OSError) as error:
        raise ProjectDeleteError(f"目录已搬进回收区，但登记表没标上“已删除”：{error}") from error
    if changed is None:
        return f"登记表里没有 {project_id}，没改登记表"
    if not changed.written:
        return f"登记表里 {project_id} 本来就是“已删除”"
    return f"登记表里 {project_id} 已标“已删除”（这一条保留，编号以后仍可查）"


@dataclass(frozen=True)
class RecycledProject:
    """回收区里的一份项目目录：搬进来的时间从目录名里的时间戳读，读不出来时 ``recycled_at`` 为 None。"""

    project_id: str
    stamp: str
    path: Path
    recycled_at: datetime | None

    def age_days(self, now: datetime) -> int | None:
        return None if self.recycled_at is None else max(0, (now - self.recycled_at).days)


def _stamp_time(stamp: str) -> datetime | None:
    try:
        return datetime.strptime(stamp, "%Y%m%dT%H%M%S%fZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def list_recycled(workspace_root: str | Path) -> list[RecycledProject]:
    """只读：列出 ``<工作区>/.auto-pm/recycle/<项目编号>/<时间戳>/``，最近搬进来的在前；回收区不存在时返回空表。

    只看目录名，不递归、不统计大小、不改任何文件；认不出时间戳的目录照样列出（``recycled_at`` 为 None），不丢项。
    """

    recycle_root = Path(workspace_root) / RECYCLE_RELATIVE_DIR
    if not recycle_root.is_dir():
        return []
    found: list[RecycledProject] = []
    for project_dir in sorted(recycle_root.iterdir()):
        if not project_dir.is_dir():
            continue
        for entry in sorted(project_dir.iterdir()):
            if entry.is_dir():
                found.append(RecycledProject(project_dir.name, entry.name, entry, _stamp_time(entry.name)))
    found.sort(key=lambda item: (item.recycled_at or datetime.min.replace(tzinfo=UTC), item.stamp), reverse=True)
    return found


@dataclass(frozen=True)
class RestorePlan:
    """一份回收区目录搬回哪里；``problems`` 不空就不能搬。"""

    item: RecycledProject
    target: Path
    target_relative: str
    target_from: str  # 目标位置从哪来：回收区记录 / 登记表
    problems: tuple[str, ...]


def plan_restore(workspace_root: str | Path, project_id: str, stamp: str = "") -> RestorePlan:
    """只读：找出回收区里要搬回的那一份和它原来的位置；找不到这一份、或不知道原来在哪时抛 ``ProjectDeleteError``。"""

    workspace = Path(workspace_root).resolve()
    items = [item for item in list_recycled(workspace) if item.project_id == project_id]
    if not items:
        raise ProjectDeleteError(f"回收区里没有项目 {project_id}（project recycle-list 可看回收区里有什么）")
    if stamp:
        chosen = next((item for item in items if item.stamp == stamp), None)
        if chosen is None:
            listed = "、".join(item.stamp for item in items)
            raise ProjectDeleteError(f"回收区里 {project_id} 没有 {stamp} 这一份；有的是：{listed}")
    elif len(items) > 1:
        listed = "、".join(item.stamp for item in items)
        raise ProjectDeleteError(f"回收区里 {project_id} 有 {len(items)} 份，请用 --stamp 指定搬回哪一份：{listed}")
    else:
        chosen = items[0]
    relative, target_from = _origin_of(workspace, chosen)
    if not relative:
        raise ProjectDeleteError(
            f"不知道 {project_id} 原来在哪（回收区没有原位置记录，登记表里也没有这一条）；"
            f"请用户本人手工把 {chosen.path} 搬回原处，再用 project register 登记"
        )
    target = (workspace / relative).resolve()
    recycle_root = workspace / RECYCLE_RELATIVE_DIR
    problems: list[str] = []
    if target == workspace or workspace not in target.parents:
        problems.append(f"原位置不在工作区里面：{relative}")
    elif target == recycle_root or recycle_root in target.parents:
        problems.append(f"原位置在回收区里面：{relative}")
    elif os.path.lexists(target):
        problems.append(f"原位置已经有同名目录或文件：{relative}（先处理掉它再搬回）")
    return RestorePlan(chosen, target, relative, target_from, tuple(problems))


def _origin_of(workspace: Path, item: RecycledProject) -> tuple[str, str]:
    record = _origin_file(workspace, item.project_id, item.stamp)
    if record.is_file():
        try:
            data = json.loads(record.read_text(encoding="utf-8"))
            relative = str(data.get("project_path") or "") if isinstance(data, dict) else ""
        except (OSError, ValueError):
            relative = ""
        if relative:
            return relative, "回收区记录"
    from auto_pm.application.core.workspace_registry_service import (
        WorkspaceRegistryError,
        WorkspaceRegistryService,
    )

    try:
        entry = WorkspaceRegistryService(workspace).find(item.project_id)
    except (WorkspaceRegistryError, OSError):
        entry = None
    if entry is not None and entry.project_root:
        return entry.project_root, "登记表"
    return "", ""


def restore_project(workspace_root: str | Path, plan: RestorePlan) -> str:
    """把 ``plan`` 那一份目录搬回原处，再把登记表状态改回删除前的值；返回登记表那一步给人看的一句话。"""

    if plan.problems:
        raise ProjectDeleteError("不能搬回：" + "；".join(plan.problems))
    if os.path.lexists(plan.target):  # 预演之后、真搬之前又出现了同名目录
        raise ProjectDeleteError(f"原位置已经有同名目录或文件：{plan.target_relative}（先处理掉它再搬回）")
    try:
        plan.target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(plan.item.path), str(plan.target))
    except OSError as error:
        raise ProjectDeleteError(f"搬回失败（回收区里的目录保持原样或请手工核对）：{error}") from error
    workspace = Path(workspace_root).resolve()
    record = _origin_file(workspace, plan.item.project_id, plan.item.stamp)
    record.unlink(missing_ok=True)
    for emptied in (plan.item.path.parent, record.parent):
        try:
            emptied.rmdir()  # 这个项目在回收区里已经空了才删得掉，不空就留着
        except OSError:
            pass

    from auto_pm.application.core.workspace_registry_service import (
        WorkspaceRegistryError,
        WorkspaceRegistryService,
    )

    project_id = plan.item.project_id
    try:
        changed = WorkspaceRegistryService(workspace_root).mark_restored(project_id)
    except (WorkspaceRegistryError, OSError) as error:
        raise ProjectDeleteError(f"目录已搬回 {plan.target_relative}，但登记表没改回来：{error}") from error
    if changed is None:
        return f"登记表里没有 {project_id}：要让驾驶舱认识它，请运行 project register {project_id} --path {plan.target_relative}"
    if not changed.written:
        return f"登记表里 {project_id} 不是“已删除”，没改登记表"
    from auto_pm.contracts.workspace_context import status_label

    return f"登记表里 {project_id} 的状态已改回“{status_label(changed.after)}”"
