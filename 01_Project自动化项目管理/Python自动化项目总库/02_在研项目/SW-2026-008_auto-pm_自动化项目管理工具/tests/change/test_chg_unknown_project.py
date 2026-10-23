"""给了找不到的项目编号时，收口写证据与实施回填都拒绝，不退回全工作区（M3-CHGUNIQ 续）

卡 177 让收口写证据与实施回填按项目定位变更单，但给了项目编号却定位不到项目目录时仍退回
全工作区查找，会把别的项目的同号变更单当成目标写进去（审计 64）。现在这种情况一律拒绝。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.domain.change.substance_injector import SubstanceInjectionError, SubstanceInjector
from tests.change.test_chg_project_scope import CHG, _inject, workspace  # noqa: F401


def test_an_unknown_project_never_falls_back_to_another_projects_change(
    workspace: dict[str, Path],  # noqa: F811
) -> None:
    """收口写证据与实施回填都拒绝，别的项目的同号单一字不改"""
    before = {k: workspace[k].read_bytes() for k in ("a", "b", "c", "stale")}
    with pytest.raises(
        SubstanceInjectionError, match="GHOST-2026-999 的变更单目录内唯一存在，实际匹配数: 0"
    ):
        _inject(workspace["root"], "GHOST-2026-999")
    with pytest.raises(FileNotFoundError, match="未找到变更单文件"):
        SubstanceInjector.inject(
            workspace_root=workspace["root"],
            change_number=CHG,
            substance={"implementation_tasks": [], "verification_records": []},
            changed_files=["src/x.py"],
            executor_id="tester",
            project_id="GHOST-2026-999",
        )
    assert {k: workspace[k].read_bytes() for k in before} == before
