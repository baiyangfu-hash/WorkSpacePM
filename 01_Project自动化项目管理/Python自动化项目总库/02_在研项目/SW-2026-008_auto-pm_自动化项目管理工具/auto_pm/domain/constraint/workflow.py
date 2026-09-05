"""工作流引擎 - Phase 2 (CST-WORKFLOW)

实现 WorkflowEngine 类，支持编排并执行多步骤工作流（如 file_modify 与 pre_commit）。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from auto_pm.constraint.guard import FileGuard
from auto_pm.constraint.models import Workflow, WorkflowRun, WorkflowStep
from auto_pm.logging.audit import audit_log


class WorkflowEngine:
    """工作流引擎"""

    def __init__(self, workspace_root: Path, guard: FileGuard | None = None) -> None:
        self._workspace_root = Path(workspace_root)
        self._guard = guard or FileGuard(workspace_root)
        # 数据目录跟随工作空间（与 FileGuard 一致），测试传 tmp_path 自动隔离
        self._data_dir = self._workspace_root / ".auto-pm" / "constraint"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._runs_file = self._data_dir / "workflow_runs.json"

    def find_workflows_dir(self) -> Path:
        pkg_dir = Path(__file__).resolve().parent / "definitions" / "workflows"
        if pkg_dir.is_dir():
            return pkg_dir

        for root_str, dirs, _files in os.walk(str(self._workspace_root)):
            root = Path(root_str)
            if "workflows" in dirs and root.name == "definitions":
                return root / "workflows"

        return pkg_dir

    def load_all(self) -> list[Workflow]:
        wf_dir = self.find_workflows_dir()
        if not wf_dir.is_dir():
            return []

        workflows = []
        for yaml_file in sorted(wf_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if not data:
                    continue

                steps = [
                    WorkflowStep(
                        name=s["name"],
                        action=s["action"],
                        command=s.get("command"),
                        params=s.get("params", {}),
                        allow_failure=s.get("allow_failure", False),
                    )
                    for s in data.get("steps", [])
                ]

                wf = Workflow(
                    name=data["name"],
                    description=data.get("description", ""),
                    steps=steps,
                )
                workflows.append(wf)
            except Exception:
                continue

        return workflows

    def get_workflow(self, name: str) -> Workflow | None:
        for wf in self.load_all():
            if wf.name == name:
                return wf
        return None

    def run(
        self, name: str, file_path: Path | None = None, params: dict[str, Any] | None = None
    ) -> WorkflowRun:
        wf = self.get_workflow(name)
        if wf is None:
            raise ValueError(f"工作流未找到: {name}")

        run_id = hashlib.sha256(f"{name}:{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        started_at = datetime.now()

        run_record = WorkflowRun(
            run_id=run_id,
            workflow_name=name,
            status="running",
            started_at=started_at,
            steps_completed=0,
            step_logs=[],
        )

        success = True

        for idx, step in enumerate(wf.steps):
            step_log = f"Step {idx + 1}/{len(wf.steps)}: {step.name} [{step.action}]"
            try:
                self._execute_step(step, file_path, params)
                step_log += " -> PASS"
                run_record.steps_completed += 1
            except Exception as e:
                step_log += f" -> FAIL ({e})"
                if not step.allow_failure:
                    success = False
                    run_record.step_logs.append(step_log)
                    break

            run_record.step_logs.append(step_log)

        run_record.status = "success" if success else "failed"
        run_record.completed_at = datetime.now()

        self._save_run(run_record)
        audit_log("workflow_run", run_id=run_id, workflow=name, status=run_record.status)

        return run_record

    def _execute_step(
        self, step: WorkflowStep, file_path: Path | None, params: dict[str, Any] | None
    ) -> None:
        action = step.action

        if action == "guard":
            target = file_path or (Path(params["file"]) if params and "file" in params else None)
            if target:
                self._guard.take_snapshot(target)

        elif action == "verify":
            target = file_path or (Path(params["file"]) if params and "file" in params else None)
            if target:
                res = self._guard.verify_snapshot(target)
                if not res.get("verified", False):
                    raise RuntimeError(f"文件快照验证失败: {target}")

        elif action == "check_encoding":
            target = file_path or (Path(params["file"]) if params and "file" in params else None)
            if target:
                res = self._guard.check_encoding(target)
                if not res["is_healthy"]:
                    raise RuntimeError(f"编码检查失败: {target}")

        elif action == "run_cmd":
            cmd = step.command
            if cmd:
                if file_path:
                    cmd = cmd.replace("{file}", str(file_path))
                completed = subprocess.run(
                    cmd, shell=True, cwd=str(self._workspace_root), capture_output=True
                )
                if completed.returncode != 0:
                    stderr_msg = completed.stderr.decode("utf-8", errors="replace")
                    raise RuntimeError(f"命令执行失败 exit={completed.returncode}: {stderr_msg}")

    def _save_run(self, run_record: WorkflowRun) -> None:
        runs = self.list_runs()
        runs.append(
            {
                "run_id": run_record.run_id,
                "workflow_name": run_record.workflow_name,
                "status": run_record.status,
                "started_at": run_record.started_at.isoformat(),
                "completed_at": (
                    run_record.completed_at.isoformat() if run_record.completed_at else None
                ),
                "steps_completed": run_record.steps_completed,
                "step_logs": run_record.step_logs,
            }
        )
        self._runs_file.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_runs(self) -> list[dict[str, Any]]:
        if not self._runs_file.is_file():
            return []
        try:
            data: list[dict[str, Any]] = json.loads(self._runs_file.read_text(encoding="utf-8"))
            return data
        except Exception:
            return []
