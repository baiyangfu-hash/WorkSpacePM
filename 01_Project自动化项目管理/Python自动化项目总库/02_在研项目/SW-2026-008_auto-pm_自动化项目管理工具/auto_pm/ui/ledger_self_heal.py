"""Ledger self-heal for the cockpit window, behind the same runtime-identity refusal as the command line (TD-SW008-214)."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from auto_pm.application.core.workspace_context_service import WorkspaceContextService


class _Project(Protocol):
    project_id: str
    path: str


class _Reconciler(Protocol):
    def auto_fix(self, project_path: str) -> object: ...


def heal_project_ledgers(workspace_root: str, projects: Iterable[_Project], reconciler: _Reconciler, phase: str) -> None:
    """Run ``auto_fix`` for every project whose runtime identity is clean; skip (and say so) for the rest.

    ``phase`` names the moment in the warning lines ("启动" / "切换").  A project whose identity cannot be verified is
    skipped like one with a conflict: the window starts anyway, the ledger of that project is left alone.
    """

    for project in projects:
        try:
            context = WorkspaceContextService(workspace_root).resolve(
                project_id=project.project_id, start_path=Path(workspace_root)
            )
            conflicts = tuple(context.conflicts)
        except Exception as error:  # an unverifiable identity must not stop the window from opening
            sys.stderr.write(f"[WARNING] 项目 {project.project_id} {phase}自动对账已跳过，运行身份无法核对: {error}\n")
            continue
        if conflicts:
            sys.stderr.write(
                f"[WARNING] 项目 {project.project_id} {phase}自动对账已跳过，运行身份有冲突: " + "；".join(conflicts) + "\n"
            )
            continue
        try:
            reconciler.auto_fix(project.path)
        except Exception as error:
            sys.stderr.write(f"[WARNING] 项目 {project.project_id} {phase}自动对账失败: {error}\n")
