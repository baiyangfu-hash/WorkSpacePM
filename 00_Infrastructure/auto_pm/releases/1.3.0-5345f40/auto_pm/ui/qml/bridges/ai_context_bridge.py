# ruff: noqa: N802
"""AiContext Bridge - 驾驶舱 ↔ AI 技能上下文桥接（双向）

将当前驾驶舱状态（项目、变更单、页面）写入 JSON 文件，
供 AI 技能（pm-workflow）快速恢复上下文；
同时读取 AI 技能执行结果（门禁/测试/LSP）反馈给驾驶舱展示。

设计原则：
- 轻量 QObject，不依赖 Facade/Service 体系
- 只依赖 workspace_root（已在 qml_main_window.py 中可用）
- 写入 .auto-pm/ai_context.json，技能侧检查此文件决定是否跳过上下文恢复
- 读取 .auto-pm/ai_feedback.json，pm-workflow 统一收集子技能结果后写入
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Slot

from auto_pm.core.ai_handoff_service import AiHandoffService

logger = logging.getLogger(__name__)


class AiContextBridge(QObject):
    """驾驶舱 → AI 技能上下文桥接器

    将 cockpit 当前状态（项目、变更单、页面）写入 JSON 文件。
    AI 技能启动时检查此文件，若存在则跳过冗余的上下文恢复步骤。
    """

    def __init__(self, workspace_root: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._workspace_root = Path(workspace_root)

    def _handoff_service(self) -> AiHandoffService:
        return AiHandoffService(self._workspace_root)

    def _build_request_id(self) -> str:
        return "AI-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S%f")

    def _suggest_target_skill(self, stack: str, change_domain: str) -> str:
        domain = change_domain.upper()
        stack_lower = stack.lower()
        if domain == "PLC" or stack_lower == "plc":
            return "plc-electrical-engineer"
        if domain in {"SCPT", "PYTHON"} or stack_lower == "python":
            return "fullstack-engineer"
        return "pm-workflow"

    def _infer_intent(self, current_page: str, stack: str, change_number: str, phase: str = "") -> str:
        if phase == "initiating":
            return "initiate_project"
        if phase == "planning":
            return "plan_documents"
        if current_page == "specCenter":
            return "spec_check"
        if change_number:
            return "implement_change"
        if stack.lower() == "plc":
            return "plc_review"
        return "project_followup"

    def _extract_active_hypothesis(self, project_id: str, change_number: str = "") -> dict[str, str]:
        hyp_id = ""
        statement = ""
        expected_signal = ""
        success_metric = ""

        session_file = self._workspace_root / f"PM_SESSION_{project_id}.md"
        if not session_file.exists():
            for p in self._workspace_root.glob(f"**/PM_SESSION_{project_id}.md"):
                session_file = p
                break

        if session_file.exists():
            try:
                text = session_file.read_text(encoding="utf-8")
                for line in text.splitlines():
                    if "|" in line and "HYP-" in line:
                        parts = [p.strip() for p in line.split("|") if p.strip()]
                        if parts and "HYP-" in parts[0]:
                            hyp_id = parts[0]
                            if len(parts) > 1:
                                statement = parts[1]
                            if len(parts) > 3:
                                expected_signal = parts[3]
                            break
            except Exception:
                pass

        if not hyp_id and project_id:
            hyp_id = f"HYP-{project_id}-001"
            statement = f"验证 {project_id} 核心工艺与控制安全逻辑"
            expected_signal = "门禁全绿且硬件现场无死锁异常"

        return {
            "id": hyp_id,
            "statement": statement,
            "expected_signal": expected_signal,
            "success_metric": success_metric,
        }

    def _build_product_context(self, project_id: str, change_number: str = "") -> dict[str, Any]:
        if project_id:
            session_ref = f"PM_SESSION_{project_id}.md"
            active_hyp = self._extract_active_hypothesis(project_id, change_number)
            return {
                "goal_ref": f"{session_ref}#product-goal",
                "hypothesis_ref": f"{session_ref}#hypothesis-ledger" if active_hyp.get("id") else "",
                "success_metric_ref": active_hyp.get("success_metric", ""),
                "active_hypothesis": active_hyp,
            }
        return {"goal_ref": "", "hypothesis_ref": "", "success_metric_ref": "", "active_hypothesis": {}}

    def _fallback_feedback(self, status: str, summary: str) -> dict[str, Any]:
        return {
            "generated_at": "",
            "status": status,
            "skill": "",
            "change_number": "",
            "changed_files": [],
            "lint_result": {"violations": 0, "errors": 0},
            "test_result": {"passed": 0, "failed": 0, "skipped": 0},
            "plc_check_result": {"violations_count": 0},
            "risks": [],
            "verification": "[待反馈]",
            "summary": summary,
        }

    @Slot(str, result="QVariant")
    def setWorkspaceRoot(self, workspace_root: str) -> dict[str, Any]:
        """更新运行态工作空间根目录。"""
        self._workspace_root = Path(workspace_root)
        return {
            "success": True,
            "workspace_root": str(self._workspace_root),
            "message": f"AiContextBridge 已切换到: {self._workspace_root}",
        }

    @Slot(str, str, str, str, str, str, str, str, str, str, result="QVariant")
    def writeAiContext(
        self,
        project_id: str,
        project_name: str,
        stack: str,
        phase: str,
        change_number: str,
        change_title: str,
        change_domain: str,
        change_nature: str,
        change_status: str,
        current_page: str,
    ) -> dict[str, Any]:
        """写入 AI 上下文文件

        QML 端点击"AI 辅助"按钮时调用，将 cockpit 当前状态序列化到
        <workspace_root>/.auto-pm/ai_context.json。

        Args:
            project_id: 当前选中项目 ID（如 "DJ-2026-022"）
            project_name: 项目名称
            stack: 技术栈（"plc" / "python"）
            phase: 项目阶段（"developing" / "delivering" 等）
            change_number: 当前选中变更单号（如 "CHG-SCPT-2026-145"）
            change_title: 变更单标题
            change_domain: 变更域（"PLC" / "SCPT" / "DOCU" 等）
            change_nature: 变更性质（"DEF" / "OPT" / "FEAT" 等）
            change_status: 变更状态（"draft" / "implementing" 等）
            current_page: 当前 cockpit 页面（"changeCenter" / "workspace" 等）

        Returns:
            {"success": True/False, "file": str, "message": str}
        """
        request_id = self._build_request_id()
        context = {
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "auto-pm cockpit",
            "workspace_root": str(self._workspace_root),
            "request_id": request_id,
            "entry_mode": "cockpit",
            "intent": self._infer_intent(current_page, stack, change_number, phase),
            "target_skill": self._suggest_target_skill(stack, change_domain),
            "active_project": {
                "id": project_id,
                "name": project_name,
                "stack": stack,
                "phase": phase,
            },
            "active_change": {
                "number": change_number,
                "title": change_title,
                "domain": change_domain,
                "nature": change_nature,
                "status": change_status,
            },
            "active_page": current_page,
            "product_context": self._build_product_context(project_id, change_number),
        }

        try:
            ai_dir = self._workspace_root / ".auto-pm"
            ai_dir.mkdir(parents=True, exist_ok=True)
            ctx_file = ai_dir / "ai_context.json"
            ctx_file.write_text(
                json.dumps(context, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {
                "success": True,
                "file": str(ctx_file),
                "request_id": request_id,
                "message": f"上下文已写入 ({len(json.dumps(context, ensure_ascii=False))} bytes)",
            }
        except Exception as e:
            logger.warning("saveAiContext failed: %s", e, exc_info=True)
            return {"success": False, "message": str(e)}

    @Slot(result="QVariant")
    def clearAiContext(self) -> dict[str, Any]:
        """清除 AI 上下文文件

        Returns:
            {"success": True/False, "message": str}
        """
        ctx_file = self._workspace_root / ".auto-pm" / "ai_context.json"
        try:
            if ctx_file.exists():
                ctx_file.unlink()
                return {"success": True, "message": "上下文已清除"}
            return {"success": True, "message": "上下文文件不存在，无需清除"}
        except Exception as e:
            logger.warning("clearAiContext failed: %s", e, exc_info=True)
            return {"success": False, "message": str(e)}

    @Slot(str, result="QVariant")
    def listPendingHandoffs(self, project_id: str = "") -> list[dict[str, Any]]:
        """Expose pending executor handoffs for the cockpit work queue."""
        return self._handoff_service().list_pending(project_id)

    @Slot(str, str, str, str, str, str, str, str, result="QVariant")
    def writePmClosureContext(
        self,
        request_id: str,
        project_id: str,
        project_name: str,
        stack: str,
        phase: str,
        change_number: str,
        change_title: str,
        current_page: str,
    ) -> dict[str, Any]:
        """Write a PM-only closure context for one pending handoff.

        The method deliberately leaves the handoff unchanged.  It is consumed by
        pm-workflow, the sole writer of PM_SESSION and ai_feedback.json.
        """
        handoff = self._handoff_service().get_pending(request_id)
        if handoff is None:
            return {"success": False, "message": "未找到待收口交接包"}

        change_number_value = change_number or str(handoff.get("change_number", ""))
        change_title_value = change_title or str(handoff.get("change_title", ""))
        context = {
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "auto-pm cockpit",
            "workspace_root": str(self._workspace_root),
            "request_id": request_id,
            "entry_mode": "cockpit",
            "intent": "close_handoff",
            "target_skill": "pm-workflow",
            "handoff_request_id": request_id,
            "active_project": {
                "id": project_id or handoff["project_id"],
                "name": project_name,
                "stack": stack,
                "phase": phase,
            },
            "active_change": {
                "number": change_number_value,
                "title": change_title_value,
                "domain": str(handoff.get("change_domain", "")),
                "nature": str(handoff.get("change_nature", "")),
                "status": str(handoff.get("change_status", "")),
            },
            "active_page": current_page,
            "product_context": handoff.get("product_context")
            or self._build_product_context(project_id or str(handoff.get("project_id", "")), change_number_value),
        }
        try:
            ai_dir = self._workspace_root / ".auto-pm"
            ai_dir.mkdir(parents=True, exist_ok=True)
            ctx_file = ai_dir / "ai_context.json"
            ctx_file.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"success": True, "file": str(ctx_file), "message": "已准备 PM 收口上下文"}
        except OSError as exc:
            return {"success": False, "message": str(exc)}

    @Slot(result="QVariant")
    def readAiFeedback(self) -> dict[str, Any]:
        """读取 AI 技能执行结果反馈

        pm-workflow 在子技能执行完毕后，将结果写入
        .auto-pm/ai_feedback.json。驾驶舱读取此文件展示 AI 工作状态。

        Returns:
            {"success": True/False, "feedback": {...} 或 "message": str}
            反馈结构:
            {
                "generated_at": "ISO时间戳",
                "status": "completed" | "failed" | "running",
                "skill": "plc-electrical-engineer" | "fullstack-engineer",
                "change_number": "CHG-PLC-2026-001",
                "changed_files": ["文件路径列表"],
                "lint_result": {"violations": 0, "errors": 0},
                "test_result": {"passed": 0, "failed": 0, "skipped": 0},
                "plc_check_result": {"violations_count": 0},
                "risks": ["风险列表"],
                "verification": "[已验证] 或 [待验证]",
                "summary": "一句话摘要"
            }
        """
        fb_file = self._workspace_root / ".auto-pm" / "ai_feedback.json"
        try:
            if not fb_file.exists():
                return {
                    "success": False,
                    "message": "暂无 AI 反馈，将按空反馈状态渲染",
                    "feedback": self._fallback_feedback("missing", "暂无 AI 反馈"),
                    "feedback_state": "missing",
                }
            content = fb_file.read_text(encoding="utf-8")
            feedback = json.loads(content)
            return {
                "success": True,
                "feedback": feedback,
                "feedback_state": "available",
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "message": f"反馈文件格式错误，将按异常反馈状态渲染: {e}",
                "feedback": self._fallback_feedback("invalid", "AI 反馈文件格式错误"),
                "feedback_state": "invalid",
            }
        except Exception as e:
            logger.warning("readAiFeedback failed: %s", e, exc_info=True)
            return {
                "success": False,
                "message": f"读取 AI 反馈失败，将按异常反馈状态渲染: {e}",
                "feedback": self._fallback_feedback("error", "AI 反馈读取失败"),
                "feedback_state": "error",
            }
