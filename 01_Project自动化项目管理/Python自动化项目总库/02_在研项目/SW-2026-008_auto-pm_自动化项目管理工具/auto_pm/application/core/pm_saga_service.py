"""PM 收口跨资产 Saga 事务编排服务（PmClosureSagaCoordinator）。

管理 handoff close 时的跨资产事务流转，提供：
- 8 个确定性步骤的顺序流转 WAL 日志
- 关键状态与数据模型 (SagaStep, SagaStatus)
- 检查点持久化与失败注入（simulate_fail_at）
- 从 Checkpoint 断点恢复（resume_saga，防双写）
- 自动备份与补偿回滚（compensate_saga）
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from auto_pm.application.core.ai_handoff_service import (
    AiHandoffService,
    HandoffError,
    HandoffNotFoundError,
)

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


class SagaError(HandoffError):
    """PmClosureSaga 基础异常。"""


class SagaExecutionError(SagaError):
    """Saga 步骤执行失败或故障注入阻断异常。"""


class SagaNotFoundError(SagaError):
    """未找到指定的 Saga 事务日志。"""


class SagaStep(str, Enum):
    """Saga 状态流转步骤。"""

    PREFLIGHT = "preflight"
    HANDOFF_CONSUMED = "handoff_consumed"
    SUBSTANCE_INJECTED = "substance_injected"
    CHG_TRANSITIONED = "chg_transitioned"
    LEDGER_RECONCILED = "ledger_reconciled"
    FEEDBACK_RECORDED = "feedback_recorded"
    PM_SESSION_RECORDED = "pm_session_recorded"
    COMPLETED = "completed"


class SagaStatus(str, Enum):
    """Saga 全局事务生命周期状态。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"


SAGA_STEPS_ORDER: tuple[str, ...] = (
    SagaStep.PREFLIGHT.value,
    SagaStep.HANDOFF_CONSUMED.value,
    SagaStep.SUBSTANCE_INJECTED.value,
    SagaStep.CHG_TRANSITIONED.value,
    SagaStep.LEDGER_RECONCILED.value,
    SagaStep.FEEDBACK_RECORDED.value,
    SagaStep.PM_SESSION_RECORDED.value,
    SagaStep.COMPLETED.value,
)


class PmClosureSagaCoordinator:
    """PM 收口跨资产事务编排器。"""

    def __init__(
        self,
        workspace_root: str | Path,
        handoff_service: AiHandoffService | None = None,
    ) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._handoff_service = handoff_service or AiHandoffService(self._workspace_root)

    @property
    def saga_log_dir(self) -> Path:
        """事务日志存储目录: .auto-pm/reports/dogfood/handoff-saga"""
        return self._workspace_root / ".auto-pm" / "reports" / "dogfood" / "handoff-saga"

    def saga_log_path(self, request_id: str) -> Path:
        """获取指定 request_id 的 Saga 日志文件路径。"""
        return self.saga_log_dir / f"{request_id}.saga.json"

    def get_saga_status(self, request_id: str) -> dict[str, Any] | None:
        """读取指定 request_id 的 Saga 事务状态日志。"""
        return self._load_saga_log(request_id)

    def execute_saga(
        self,
        request_id: str,
        *,
        result: Mapping[str, Any] | None = None,
        idempotency_key: str = "",
        actor: str = "pm-workflow",
        simulate_fail_at: str = "",
    ) -> dict[str, Any]:
        """执行 PM 收口跨资产全流程 Saga 事务。"""
        self._handoff_service._validate_request_id(request_id)
        if not actor.strip():
            raise SagaError("actor 不能为空")

        current = self._handoff_service.get_request(request_id)
        if current is None:
            raise HandoffNotFoundError(f"找不到有效 handoff: {request_id}")

        merged, effective_key, fingerprint = self._handoff_service._prepare_close_payload(
            current,
            result or {},
            idempotency_key,
        )

        # 幂等检查：若 Saga 已完成且是相同请求，直接返回
        existing = self._load_saga_log(request_id)
        if existing and existing.get("status") == SagaStatus.COMPLETED.value:
            return existing

        project_id = str(merged.get("project_id", ""))
        saga_id = existing.get("saga_id") if existing else f"SAGA-{request_id}-{uuid.uuid4().hex[:8].upper()}"

        saga_data: dict[str, Any] = {
            "saga_id": saga_id,
            "request_id": request_id,
            "project_id": project_id,
            "status": SagaStatus.IN_PROGRESS.value,
            "current_step": SagaStep.PREFLIGHT.value,
            "completed_steps": [],
            "checkpoints": [],
            "backup_files": {},
            "error": None,
            "actor": actor,
            "idempotency_key": effective_key,
            "fingerprint": fingerprint,
            "result": dict(result or {}),
            "created_at": existing.get("created_at", datetime.now(UTC).isoformat()) if existing else datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        return self._run_saga_steps(
            saga_data=saga_data,
            merged=merged,
            effective_key=effective_key,
            fingerprint=fingerprint,
            actor=actor,
            result=result or {},
            simulate_fail_at=simulate_fail_at,
        )

    def resume_saga(
        self,
        request_id: str,
        *,
        actor: str = "pm-workflow",
        simulate_fail_at: str = "",
    ) -> dict[str, Any]:
        """从断点继续执行未完成步骤直至 completed。"""
        self._handoff_service._validate_request_id(request_id)
        saga_data = self._load_saga_log(request_id)
        if saga_data is None:
            raise SagaNotFoundError(f"未找到 Saga 事务日志: {request_id}")

        if saga_data.get("status") == SagaStatus.COMPLETED.value:
            return saga_data

        if saga_data.get("status") == SagaStatus.COMPENSATED.value:
            raise SagaError(f"Saga 已处于 compensated 补偿状态，不可直接 resume: {request_id}")

        current = self._handoff_service.get_request(request_id)
        if current is None:
            raise HandoffNotFoundError(f"找不到有效 handoff: {request_id}")

        result = saga_data.get("result") or {}
        effective_key = str(saga_data.get("idempotency_key") or current.get("idempotency_key") or request_id)
        merged, _, fingerprint = self._handoff_service._prepare_close_payload(
            current,
            result,
            effective_key,
        )

        saga_data["status"] = SagaStatus.IN_PROGRESS.value
        saga_data["error"] = None
        saga_data["updated_at"] = datetime.now(UTC).isoformat()
        self._save_saga_log(saga_data)

        return self._run_saga_steps(
            saga_data=saga_data,
            merged=merged,
            effective_key=effective_key,
            fingerprint=fingerprint,
            actor=actor or str(saga_data.get("actor", "pm-workflow")),
            result=result,
            simulate_fail_at=simulate_fail_at,
        )

    def compensate_saga(
        self,
        request_id: str,
        *,
        actor: str = "pm-workflow",
    ) -> dict[str, Any]:
        """从 backup_files 恢复所有被修改文件原始内容，将状态置为 compensated。"""
        self._handoff_service._validate_request_id(request_id)
        saga_data = self._load_saga_log(request_id)
        if saga_data is None:
            raise SagaNotFoundError(f"未找到 Saga 事务日志: {request_id}")

        if saga_data.get("status") == SagaStatus.COMPENSATED.value:
            return saga_data

        backup_files = dict(saga_data.get("backup_files") or {})
        restored: list[str] = []
        for path_str, original_content in backup_files.items():
            target_path = Path(path_str)
            if original_content is None:
                if target_path.exists():
                    try:
                        target_path.unlink()
                        restored.append(f"removed:{path_str}")
                    except OSError:
                        pass
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(str(original_content), encoding="utf-8", errors="replace")
                restored.append(f"restored:{path_str}")

        saga_data["status"] = SagaStatus.COMPENSATED.value
        saga_data["current_step"] = "compensated"
        saga_data["updated_at"] = datetime.now(UTC).isoformat()
        checkpoints = list(saga_data.get("checkpoints") or [])
        checkpoints.append(
            {
                "step": "compensated",
                "status": "completed",
                "occurred_at": datetime.now(UTC).isoformat(),
                "actor": actor,
                "restored_files": restored,
            }
        )
        saga_data["checkpoints"] = checkpoints
        self._save_saga_log(saga_data)
        return saga_data

    # ── 内部编排逻辑 ──────────────────────────────────────────

    def _run_saga_steps(
        self,
        *,
        saga_data: dict[str, Any],
        merged: dict[str, Any],
        effective_key: str,
        fingerprint: str,
        actor: str,
        result: Mapping[str, Any],
        simulate_fail_at: str,
    ) -> dict[str, Any]:
        """驱动 8 个步骤的顺序执行，跳过已完成步骤。"""
        for step in SAGA_STEPS_ORDER:
            completed_steps = list(saga_data.get("completed_steps") or [])
            if step in completed_steps:
                continue

            saga_data["current_step"] = step
            saga_data["updated_at"] = datetime.now(UTC).isoformat()
            self._save_saga_log(saga_data)

            # 故障注入检查
            if simulate_fail_at and simulate_fail_at == step:
                self._record_failure(saga_data, step, f"Simulated failure at step: {step}")

            try:
                if step == SagaStep.PREFLIGHT.value:
                    self._step_preflight(saga_data, merged, effective_key, fingerprint)
                elif step == SagaStep.HANDOFF_CONSUMED.value:
                    self._step_handoff_consumed(
                        saga_data, merged, effective_key, fingerprint, actor, result
                    )
                elif step == SagaStep.SUBSTANCE_INJECTED.value:
                    self._step_substance_injected(saga_data, merged, actor)
                elif step == SagaStep.CHG_TRANSITIONED.value:
                    self._step_chg_transitioned(saga_data, merged)
                elif step == SagaStep.LEDGER_RECONCILED.value:
                    self._step_ledger_reconciled(saga_data, merged)
                elif step == SagaStep.FEEDBACK_RECORDED.value:
                    self._step_feedback_recorded(saga_data, merged)
                elif step == SagaStep.PM_SESSION_RECORDED.value:
                    self._step_pm_session_recorded(saga_data, merged, actor)
                elif step == SagaStep.COMPLETED.value:
                    self._step_completed(saga_data, merged)
            except SagaExecutionError:
                raise
            except Exception as exc:
                self._record_failure(saga_data, step, str(exc))

        return saga_data

    def _record_failure(self, saga_data: dict[str, Any], step: str, error_message: str) -> None:
        """记录失败检查点并持久化失败态日志。"""
        saga_data["status"] = SagaStatus.FAILED.value
        saga_data["current_step"] = step
        saga_data["error"] = error_message
        saga_data["updated_at"] = datetime.now(UTC).isoformat()
        checkpoints = list(saga_data.get("checkpoints") or [])
        checkpoints.append(
            {
                "step": step,
                "status": "failed",
                "occurred_at": datetime.now(UTC).isoformat(),
                "error": error_message,
            }
        )
        saga_data["checkpoints"] = checkpoints
        self._save_saga_log(saga_data)
        raise SagaExecutionError(error_message)

    def _mark_step_done(
        self,
        saga_data: dict[str, Any],
        step: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """标记步骤完成并持久化检查点。"""
        completed_steps = list(saga_data.get("completed_steps") or [])
        if step not in completed_steps:
            completed_steps.append(step)
        saga_data["completed_steps"] = completed_steps

        checkpoints = list(saga_data.get("checkpoints") or [])
        checkpoints.append(
            {
                "step": step,
                "status": "completed",
                "occurred_at": datetime.now(UTC).isoformat(),
                "details": dict(details or {}),
            }
        )
        saga_data["checkpoints"] = checkpoints
        saga_data["updated_at"] = datetime.now(UTC).isoformat()
        self._save_saga_log(saga_data)

    def _backup_file(self, saga_data: dict[str, Any], path: Path) -> None:
        """在修改前备份文件的原始内容（若已备份则保留首次快照）。"""
        key = str(path.resolve())
        backup_files = dict(saga_data.get("backup_files") or {})
        if key in backup_files:
            return
        if path.is_file():
            backup_files[key] = path.read_text(encoding="utf-8", errors="replace")
        else:
            backup_files[key] = None
        saga_data["backup_files"] = backup_files

    # ── 8 大 Saga 步骤实现 ─────────────────────────────────────

    def _step_preflight(
        self,
        saga_data: dict[str, Any],
        merged: dict[str, Any],
        effective_key: str,
        fingerprint: str,
    ) -> None:
        """步骤 1 (preflight): 运行预检逻辑，验证入参、白名单、证据、真实性。"""
        self._handoff_service._validate_closure(merged)
        self._mark_step_done(
            saga_data,
            SagaStep.PREFLIGHT.value,
            {
                "project_id": merged.get("project_id"),
                "idempotency_key": effective_key,
                "fingerprint": fingerprint,
            },
        )

    def _step_handoff_consumed(
        self,
        saga_data: dict[str, Any],
        merged: dict[str, Any],
        effective_key: str,
        fingerprint: str,
        actor: str,
        result: Mapping[str, Any],
    ) -> None:
        """步骤 2 (handoff_consumed): 消费 handoff，写入 consumed 状态与指纹。"""
        request_id = str(merged["request_id"])
        path = self._handoff_service._find_request_path(request_id)
        self._backup_file(saga_data, path)

        now = datetime.now(UTC).isoformat()
        merged.update(
            {
                "schema_version": self._handoff_service.SCHEMA_VERSION,
                "status": "consumed",
                "closed_at": now,
                "consumed_at": now,
                "closed_by": actor,
                "idempotency_key": effective_key,
                "closure": {
                    "idempotency_key": effective_key,
                    "fingerprint": fingerprint,
                    "closed_by": actor,
                },
            }
        )
        self._handoff_service._write_atomic(path, merged)
        if result:
            self._handoff_service._write_result_atomic(request_id, result)

        self._mark_step_done(
            saga_data,
            SagaStep.HANDOFF_CONSUMED.value,
            {
                "file": str(path),
                "consumed_at": now,
            },
        )

    def _step_substance_injected(
        self,
        saga_data: dict[str, Any],
        merged: dict[str, Any],
        actor: str,
    ) -> None:
        """步骤 3 (substance_injected): 备份 CHG 文件并调用 SubstanceInjector.inject。"""
        target_chg_id = self._resolve_target_chg_id(merged)
        if target_chg_id:
            chg_file = self._find_chg_file(target_chg_id)
            if chg_file is not None and chg_file.is_file():
                self._backup_file(saga_data, chg_file)
                from auto_pm.domain.change.substance_injector import SubstanceInjector

                substance_raw = merged.get("change_substance")
                if isinstance(substance_raw, Mapping):
                    substance = dict(substance_raw)
                elif isinstance(substance_raw, str) and substance_raw.startswith("{"):
                    try:
                        substance = json.loads(substance_raw)
                    except Exception:
                        substance = {}
                else:
                    substance = {}

                execution_dict = merged.get("execution")
                if isinstance(execution_dict, Mapping):
                    executor_id = str(execution_dict.get("executor_id") or actor)
                else:
                    executor_id = actor

                SubstanceInjector.inject(
                    workspace_root=self._workspace_root,
                    change_number=target_chg_id,
                    substance=substance,
                    changed_files=merged.get("changed_files") or [],
                    executor_id=executor_id,
                    project_id=str(merged.get("project_id", "")),
                )
        self._mark_step_done(
            saga_data,
            SagaStep.SUBSTANCE_INJECTED.value,
            {"target_chg_id": target_chg_id},
        )

    def _step_chg_transitioned(
        self,
        saga_data: dict[str, Any],
        merged: dict[str, Any],
    ) -> None:
        """步骤 4 (chg_transitioned): 自动流转关联变更单状态（支持 completed 或 closed）。"""
        transitions: dict[str, str] = {}
        target_chgs = self._resolve_all_chg_targets(merged)
        from auto_pm.domain.change.markdown_editor import ChangeMarkdownEditor

        editor = ChangeMarkdownEditor()

        for chg_id, target_status in target_chgs.items():
            chg_file = self._find_chg_file(chg_id)
            if chg_file is not None and chg_file.is_file():
                self._backup_file(saga_data, chg_file)
                content = chg_file.read_text(encoding="utf-8", errors="replace")
                content = editor.update_status_field(content, target_status)
                if target_status in ("completed", "closed"):
                    content = editor.update_verification_conclusion(
                        content, "全部通过,可关闭"
                    )
                chg_file.write_text(content, encoding="utf-8", errors="replace")
                transitions[chg_id] = target_status

        self._mark_step_done(
            saga_data,
            SagaStep.CHG_TRANSITIONED.value,
            {"transitions": transitions},
        )

    def _step_ledger_reconciled(
        self,
        saga_data: dict[str, Any],
        merged: dict[str, Any],
    ) -> None:
        """步骤 5 (ledger_reconciled): 备份台账并调用 LedgerReconciler.auto_fix，断言台账 0 差异。"""
        project_id = str(merged.get("project_id", ""))
        target_chg_id = self._resolve_target_chg_id(merged)
        project_path = self._resolve_project_path(project_id, target_chg_id)

        from auto_pm.domain.change.ledger_reconciler import LedgerReconciler
        from auto_pm.domain.change.path_resolver import find_ledger_file

        existing_ledger = find_ledger_file(str(project_path))
        if existing_ledger:
            self._backup_file(saga_data, Path(existing_ledger))
        else:
            default_ledger = (
                project_path / "04_监控" / "01_变更管理" / "02_变更记录" / "01_版本变更台帐.md"
            )
            self._backup_file(saga_data, default_ledger)

        reconciler = LedgerReconciler()
        diff = reconciler.reconcile(str(project_path))
        if not diff.is_clean:
            reconciler.auto_fix(str(project_path), diff)

        final_diff = reconciler.reconcile(str(project_path))
        if not final_diff.is_clean:
            raise SagaExecutionError(f"台账对账仍有差异: {final_diff.summary()}")

        self._mark_step_done(
            saga_data,
            SagaStep.LEDGER_RECONCILED.value,
            {"summary": final_diff.summary(), "project_path": str(project_path)},
        )

    def _step_feedback_recorded(
        self,
        saga_data: dict[str, Any],
        merged: dict[str, Any],
    ) -> None:
        """步骤 6 (feedback_recorded): 若有反馈更新，安全回写 .auto-pm/ai_feedback.json。"""
        fb_path = self._workspace_root / ".auto-pm" / "ai_feedback.json"
        self._backup_file(saga_data, fb_path)

        target_chg_id = self._resolve_target_chg_id(merged)
        feedback_data = {
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "completed",
            "skill": str(merged.get("executor_skill", "fullstack-engineer")),
            "change_number": target_chg_id or "",
            "changed_files": list(merged.get("changed_files") or []),
            "lint_result": merged.get("verification", {}).get("lint_result", "PASS"),
            "test_result": merged.get("verification", {}).get("test_result", "PASS"),
            "risks": list(merged.get("risks") or []),
            "verification": "[已验证]",
            "summary": str(merged.get("summary", "")),
            "request_id": str(merged.get("request_id", "")),
        }

        fb_path.parent.mkdir(parents=True, exist_ok=True)
        temp_fb = fb_path.parent / f".{fb_path.name}.{uuid.uuid4().hex}.tmp"
        with temp_fb.open("w", encoding="utf-8", errors="replace", newline="\n") as stream:
            json.dump(feedback_data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temp_fb.replace(fb_path)

        self._mark_step_done(
            saga_data,
            SagaStep.FEEDBACK_RECORDED.value,
            {"file": str(fb_path)},
        )

    def _step_pm_session_recorded(
        self,
        saga_data: dict[str, Any],
        merged: dict[str, Any],
        actor: str,
    ) -> None:
        """步骤 7 (pm_session_recorded): 若 PM_SESSION 存在，备份并登记收口记录。"""
        project_id = str(merged.get("project_id", ""))
        target_chg_id = self._resolve_target_chg_id(merged)
        project_path = self._resolve_project_path(project_id, target_chg_id)
        pm_session_file = self._find_pm_session_file(project_id, project_path)

        if pm_session_file is not None and pm_session_file.is_file():
            self._backup_file(saga_data, pm_session_file)
            content = pm_session_file.read_text(encoding="utf-8", errors="replace")
            request_id = str(merged.get("request_id", ""))
            now_iso = datetime.now(UTC).isoformat()
            closure_line = (
                f"- skill_handoff_{request_id}: 收口变更 {target_chg_id or ''}，"
                f"状态 consumed，执行人 {actor}，完成时间 {now_iso}\n"
            )
            if re.search(r"^##\s*8\.", content, re.MULTILINE):
                content = re.sub(
                    r"(^##\s*8\.[^\n]*\n)",
                    rf"\g<1>{closure_line}",
                    content,
                    count=1,
                    flags=re.MULTILINE,
                )
            else:
                content = content.rstrip() + f"\n\n## 8. Handoff Notes\n{closure_line}"
            pm_session_file.write_text(content, encoding="utf-8", errors="replace")

        self._mark_step_done(
            saga_data,
            SagaStep.PM_SESSION_RECORDED.value,
            {"pm_session": str(pm_session_file) if pm_session_file else None},
        )

    def _step_completed(
        self,
        saga_data: dict[str, Any],
        merged: dict[str, Any],
    ) -> None:
        """步骤 8 (completed): 标记状态为 completed，原子写入完成态日志。"""
        saga_data["status"] = SagaStatus.COMPLETED.value
        saga_data["current_step"] = SagaStep.COMPLETED.value
        completed_steps = list(saga_data.get("completed_steps") or [])
        if SagaStep.COMPLETED.value not in completed_steps:
            completed_steps.append(SagaStep.COMPLETED.value)
        saga_data["completed_steps"] = completed_steps

        checkpoints = list(saga_data.get("checkpoints") or [])
        checkpoints.append(
            {
                "step": SagaStep.COMPLETED.value,
                "status": "completed",
                "occurred_at": datetime.now(UTC).isoformat(),
                "details": {"request_id": merged.get("request_id")},
            }
        )
        saga_data["checkpoints"] = checkpoints
        saga_data["updated_at"] = datetime.now(UTC).isoformat()
        self._save_saga_log(saga_data)

    # ── 路径与辅助方法 ──────────────────────────────────────────

    def _save_saga_log(self, saga_data: dict[str, Any]) -> None:
        """原子写入 Saga 事务日志文件。"""
        request_id = str(saga_data["request_id"])
        self.saga_log_dir.mkdir(parents=True, exist_ok=True)
        target = self.saga_log_path(request_id)
        temp_path = self.saga_log_dir / f".{target.name}.{uuid.uuid4().hex}.tmp"
        with temp_path.open("w", encoding="utf-8", errors="replace", newline="\n") as stream:
            json.dump(saga_data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temp_path.replace(target)

    def _load_saga_log(self, request_id: str) -> dict[str, Any] | None:
        """读取已有的 Saga 事务日志文件。"""
        path = self.saga_log_path(request_id)
        if not path.is_file():
            return None
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _resolve_target_chg_id(self, merged: Mapping[str, Any]) -> str:
        """解析主要目标变更单编号。"""
        direct = (
            merged.get("change_id")
            or (merged.get("skill_context") or {}).get("change_id")
            or (merged.get("change_substance") or {}).get("change_number")
        )
        if direct:
            return str(direct).strip()
        for update in merged.get("chg_updates") or []:
            m = re.search(r"(CHG-[A-Za-z0-9_-]+)", str(update))
            if m:
                return m.group(1)
        return ""

    def _resolve_all_chg_targets(self, merged: Mapping[str, Any]) -> dict[str, str]:
        """解析所有需要流转的变更单及目标状态。"""
        targets: dict[str, str] = {}
        target_chg_id = self._resolve_target_chg_id(merged)
        if target_chg_id:
            targets[target_chg_id] = "completed"

        for update in merged.get("chg_updates") or []:
            update_str = str(update).strip()
            if not update_str:
                continue
            m = re.search(r"(CHG-[A-Za-z0-9_-]+)", update_str)
            if not m:
                continue
            chg_id = m.group(1)
            status = "closed" if "closed" in update_str.lower() else "completed"
            targets[chg_id] = status
        return targets

    def _find_chg_file(self, chg_id: str) -> Path | None:
        """跨资产定位变更单 Markdown 文件。"""
        clean_id = chg_id[:-3] if chg_id.endswith(".md") else chg_id
        pattern = f"**/{clean_id}.md"
        direct = self._workspace_root / (clean_id if clean_id.endswith(".md") else f"{clean_id}.md")
        if direct.is_file():
            return direct
        matches = list(self._workspace_root.glob(pattern))
        if matches:
            return matches[0]
        # 兼容在子目录运行时的上层目录查找
        for candidate_root in (Path.cwd(), Path.cwd().parent, Path.cwd().parent.parent):
            sub_matches = list(candidate_root.glob(pattern))
            if sub_matches:
                return sub_matches[0]
        return None

    def _resolve_project_path(self, project_id: str, chg_id: str) -> Path:
        """解析项目根路径。"""
        if chg_id:
            chg_file = self._find_chg_file(chg_id)
            if chg_file is not None:
                curr = chg_file.parent
                while curr != curr.parent and curr != self._workspace_root.parent:
                    if (
                        any(curr.glob(f"PM_SESSION_{project_id}*.md"))
                        or (curr / ".copier-answers.yml").exists()
                        or (curr / ".plc.json").exists()
                        or (curr / "pyproject.toml").exists()
                        or curr.name == project_id
                        or curr.name.startswith(f"{project_id}_")
                    ):
                        return curr
                    curr = curr.parent

        try:
            from auto_pm.change.file_locator import ChangeFileLocator
            from auto_pm.change.parser import ChgParser

            locator = ChangeFileLocator(str(self._workspace_root), ChgParser())
            path_str = locator.get_project_path(project_id)
            if path_str and Path(path_str).is_dir():
                return Path(path_str)
        except Exception:
            pass

        candidate = self._workspace_root / project_id
        if candidate.is_dir():
            return candidate

        return self._workspace_root

    def _find_pm_session_file(self, project_id: str, project_path: Path) -> Path | None:
        """定位 PM_SESSION 主文档。"""
        candidates: list[Path] = []
        if project_path.exists():
            candidates.extend(project_path.glob(f"PM_SESSION_{project_id}*.md"))
            candidates.extend(project_path.glob("PM_SESSION.md"))
        candidates.extend(self._workspace_root.glob(f"PM_SESSION_{project_id}*.md"))
        candidates.extend(self._workspace_root.glob("PM_SESSION.md"))
        for c in candidates:
            if c.is_file():
                return c
        return None
