"""WorkflowEngine 单元测试 - Phase 2"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.constraint.workflow import WorkflowEngine


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    return tmp_path


class TestWorkflowEngine:
    def test_load_all(self, temp_workspace: Path) -> None:
        """从包定义目录正确加载包含 file-modify 与 pre-commit 在内的工作流"""
        engine = WorkflowEngine(temp_workspace)
        workflows = engine.load_all()

        assert len(workflows) >= 2
        names = [w.name for w in workflows]
        assert "file-modify" in names
        assert "pre-commit" in names

    def test_run_file_modify_workflow(self, temp_workspace: Path) -> None:
        """运行 file-modify 工作流"""
        target_file = temp_workspace / "test.md"
        target_file.write_text("# Test", encoding="utf-8")

        engine = WorkflowEngine(temp_workspace)
        run_res = engine.run("file-modify", file_path=target_file)

        assert run_res.status == "success"
        assert run_res.steps_completed == 2

    def test_workflow_not_found(self, temp_workspace: Path) -> None:
        """运行不存在的工作流抛出 ValueError"""
        engine = WorkflowEngine(temp_workspace)
        with pytest.raises(ValueError):
            engine.run("non-existent-wf")
