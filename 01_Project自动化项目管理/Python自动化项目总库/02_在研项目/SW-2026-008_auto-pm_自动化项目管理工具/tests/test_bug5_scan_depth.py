"""Bug-5 回归测试: 扫描深度不一致（005 遗留问题）

任务描述: 008 中迁移自 005 的 ProjectOverviewService 扫描 depth=1，
          与 PlcProjectService 的 depth=4 不一致，需统一为 depth=4。

实际代码核查发现（与描述不符，已报告）:
  - 008 中不存在 ProjectOverviewService 类（005 的该类已迁移为 ProjectService）
  - ProjectService.list_projects 默认 scan_depth=4（已与 PlcChecker 一致）
  - PlcChecker.check_workspace 默认 scan_depth=4
  - 008 中无任何 depth=1 的扫描逻辑

本测试锁定 depth=4 的正确行为，防止未来回归。
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from auto_pm.application.core.project_service import ProjectService
from auto_pm.domain.plc.checker import PlcChecker


def _make_plc_project(parent: Path, name: str) -> Path:
    """在 parent 下创建一个由 .plc.json 识别的 PLC 项目目录"""
    project_dir = parent / name
    project_dir.mkdir(parents=True)
    (project_dir / ".plc.json").write_text(
        json.dumps({"name": name}, ensure_ascii=False),
        encoding="utf-8",
    )
    return project_dir


class TestScanDepthDefault:
    """扫描深度默认值应为 4"""

    def test_project_service_default_depth_is_4(self) -> None:
        """ProjectService.list_projects 默认 scan_depth=4"""
        sig = inspect.signature(ProjectService.list_projects)
        param = sig.parameters["scan_depth"]
        assert param.default == 4

    def test_plc_checker_default_depth_is_4(self) -> None:
        """PlcChecker.check_workspace 默认 scan_depth=4"""
        sig = inspect.signature(PlcChecker.check_workspace)
        param = sig.parameters["scan_depth"]
        assert param.default == 4


class TestScanDepthConsistency:
    """ProjectService 与 PlcChecker 扫描深度一致"""

    def test_both_use_same_default_depth(self) -> None:
        """两个 Service 的默认扫描深度应一致（均为 4）"""
        ps_depth = inspect.signature(ProjectService.list_projects).parameters[
            "scan_depth"
        ].default
        plc_depth = inspect.signature(PlcChecker.check_workspace).parameters[
            "scan_depth"
        ].default
        assert ps_depth == plc_depth == 4


class TestScanDepth4FindsNestedProject:
    """depth=4 扫描应能发现 4 层嵌套的项目"""

    def test_finds_project_at_depth_4(self, tmp_path: Path) -> None:
        """4 层嵌套的项目应被扫描到"""
        # 创建 4 层嵌套: a/b/c/d/project
        # depth=0 扫描 workspace → 发现 a
        # depth=1 → 发现 b
        # depth=2 → 发现 c
        # depth=3 → 发现 d
        # depth=4 → 发现 project（4 > 4 为 False，继续扫描）
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        _make_plc_project(deep, "DJ-DEEP-001")

        svc = ProjectService(str(tmp_path))
        projects = svc.list_projects()

        assert any(p.project_id == "DJ-DEEP-001" for p in projects)

    def test_does_not_find_project_at_depth_5(self, tmp_path: Path) -> None:
        """5 层嵌套的项目不应被扫描到（depth=4 边界）"""
        # 创建 5 层嵌套: a/b/c/d/e/project
        # depth=5 时 5 > 4 为 True，直接返回
        deep = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        _make_plc_project(deep, "DJ-DEEP-002")

        svc = ProjectService(str(tmp_path))
        projects = svc.list_projects()

        assert not any(p.project_id == "DJ-DEEP-002" for p in projects)

    def test_finds_shallow_project(self, tmp_path: Path) -> None:
        """直接子目录的项目应被扫描到"""
        _make_plc_project(tmp_path, "DJ-SHALLOW-001")

        svc = ProjectService(str(tmp_path))
        projects = svc.list_projects()

        assert any(p.project_id == "DJ-SHALLOW-001" for p in projects)
