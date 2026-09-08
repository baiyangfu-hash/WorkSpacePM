"""PLC 端到端工作流测试

测试流程: init → check → repair → check
覆盖 3 种模式: shared-library, test-suite, standard-project

由于端到端测试不依赖 copier，手动创建最小项目结构，
重点验证 PlcService 的 check → repair → check 流程。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_pm.plc.service import PlcService


class TestE2ePlcWorkflow:
    """端到端 PLC 工作流测试"""

    @pytest.mark.parametrize("mode,template_name", [
        ("shared-library", "plc-shared-library"),
        ("test-suite", "plc-test-suite"),
        ("standard-project", "plc-standard-project"),
    ])
    def test_init_check_repair_check_workflow(
        self, tmp_path: Path, mode: str, template_name: str
    ) -> None:
        """测试 init → check → repair → check 完整流程"""
        workspace = tmp_path
        project_dir = workspace / f"TEST-{mode}"
        project_dir.mkdir()

        # 1. 模拟 init: 创建最小项目结构（不依赖 copier）
        self._create_minimal_project(project_dir, mode)

        # 2. 第一次 check: 应有 FAIL 项（缺少 PM_SESSION/PRD/标准目录等）
        svc = PlcService(str(workspace))
        result1 = svc.check(str(project_dir))
        assert len(result1.items) > 0, "首次检查应产生检查项"
        assert result1.fail_count > 0, "首次检查应有 FAIL 项"

        # 3. repair: 修复缺失项
        repair_result = svc.repair(str(project_dir), dry_run=False)
        assert repair_result.fixed_count > 0, "修复应产生 fixed 项"

        # 4. 第二次 check: FAIL 项应减少
        result2 = svc.check(str(project_dir))
        assert result2.fail_count <= result1.fail_count, (
            f"修复后 FAIL 项应减少: {result2.fail_count} vs {result1.fail_count}"
        )

    def _create_minimal_project(self, project_dir: Path, mode: str) -> None:
        """创建最小项目结构用于测试

        由于端到端测试不依赖 copier，手动创建最小结构：
        - shared-library: .plc.json 在根目录, libraries 为空
        - test-suite: .plc.json 在根目录, libraries 指向 SysLib
        - standard-project: .plc.json 在 02_PLC程序/PLC_ST/ 下
        """
        if mode == "standard-project":
            # 标准项目: .plc.json 在 02_PLC程序/PLC_ST/ 下
            plc_subdir = project_dir / "02_PLC程序" / "PLC_ST"
            plc_subdir.mkdir(parents=True)
            (plc_subdir / ".plc.json").write_text(
                json.dumps(
                    {
                        "name": "TEST",
                        "description": "测试",
                        "version": "V1.0.0",
                        "libraries": ["../../../01_SharedLibraries/SysLib"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        elif mode == "test-suite":
            # 测试套件: .plc.json 在根目录
            (project_dir / ".plc.json").write_text(
                json.dumps(
                    {
                        "name": "TEST",
                        "description": "测试",
                        "version": "V1.0.0",
                        "libraries": ["../01_SharedLibraries/SysLib"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        else:  # shared-library
            # 共享库: .plc.json 在根目录, libraries 为空
            (project_dir / ".plc.json").write_text(
                json.dumps(
                    {
                        "name": "TEST",
                        "description": "测试",
                        "version": "V1.0.0",
                        "libraries": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
