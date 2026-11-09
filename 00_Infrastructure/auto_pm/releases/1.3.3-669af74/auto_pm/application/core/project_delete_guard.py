"""删除项目前的护栏（TD-193）：先查开着的任务和未提交改动，再把目录搬进回收区，而不是直接 ``rmtree``。

``project delete --confirm`` 以前只有一个开关：不看项目有没有开着的 Mission / Work / Run，不看有没有没提交的改动，
删了就没了。这里只提供两件事，谁能下令删（用户本人的口令或原话、agent 一律不行）由命令层负责：

- ``delete_blockers``：列出挡住删除的原因（开着的 Mission、Work、Run；项目目录里没提交的改动；读不出来也算挡住）；
- ``recycle_project``：把项目目录整体搬到 ``<工作区>/.auto-pm/recycle/<项目编号>/<时间戳>/``，可原样搬回。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.application.core.approval_proof_service import ApprovalProofError, ApprovalProofService
from auto_pm.application.core.lease_handover_service import agent_markers
from auto_pm.contracts.continuity import RunState
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.git_timeout import run_git_bounded_text

RECYCLE_RELATIVE_DIR = Path(".auto-pm") / "recycle"
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
        done = run_git_bounded_text(
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
    return destination
