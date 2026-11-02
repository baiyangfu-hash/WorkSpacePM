"""WorkflowEngine 单元测试 - Phase 2"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.domain.constraint.workflow import WorkflowEngine


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

    @pytest.mark.parametrize(
        ("name", "expected"),
        [("plain.md", '"plain.md"'), ("a&b;c.md", '"a&b;c.md"'), ("中文 名字.md", '"中文 名字.md"'), ("x^y.md", '"x^y.md"')],
    )
    def test_the_windows_spelling_always_quotes_a_shell_word(
        self, monkeypatch: pytest.MonkeyPatch, name: str, expected: str
    ) -> None:
        """cmd.exe reads ``&`` and ``^`` in a bare word as syntax; ``list2cmdline`` alone quotes only spaces (the windows-extra failure)."""
        from auto_pm.domain.constraint import workflow

        monkeypatch.setattr(workflow.os, "name", "nt")
        assert workflow._quoted_for_shell(name) == expected

    @pytest.mark.parametrize("name", ["plain.md", "has space.md", "中文 名字.md", "a&b;c.md", "it's.md"])
    def test_run_cmd_passes_the_file_as_one_argument(self, temp_workspace: Path, name: str) -> None:
        """CHG-SCPT-2026-472: ``{file}`` was pasted into a shell string unquoted; a space, ``&`` or ``;`` split or injected."""
        import shlex
        import subprocess
        import sys

        from auto_pm.domain.constraint.models import WorkflowStep

        target = temp_workspace / name
        target.write_text("# t", encoding="utf-8")
        seen = temp_workspace / "seen.txt"
        script = temp_workspace / "show.py"
        script.write_text(
            "import sys, pathlib\n"
            f"pathlib.Path({str(seen)!r}).write_text(repr(sys.argv[1:]), encoding='utf-8')\n",
            encoding="utf-8",
        )
        runner = subprocess.list2cmdline([sys.executable, str(script)]) if sys.platform == "win32" else shlex.join([sys.executable, str(script)])
        engine = WorkflowEngine(temp_workspace)

        engine._execute_step(WorkflowStep(action="run_cmd", command=f"{runner} {{file}}"), target, None)

        assert seen.read_text(encoding="utf-8") == repr([str(target)])
