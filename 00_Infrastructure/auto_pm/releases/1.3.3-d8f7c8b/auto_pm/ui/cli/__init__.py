"""PLC-HMI 概念映射：程序入口（CLI 包初始化（命令行子包入口））

像 PLC 的启动流程，程序的上电入口点。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)


def write_ai_context(
    workspace_root: str,
    project_id: str,
    project_name: str = "",
    stack: str = "",
    phase: str = "",
    *,
    entry_mode: str = "direct",
    active_page: str = "workspace",
) -> bool:
    """写入 AI 上下文文件（.auto-pm/ai_context.json）

    在 CLI 命令（project show / plc check）执行后自动调用，
    将当前操作的项目上下文写入，供 cockpit 或 AI 技能恢复上下文。

    Args:
        workspace_root: 工作空间根目录
        project_id: 项目编号
        project_name: 项目名称
        stack: 技术栈（plc/python）
        phase: 项目阶段

    Returns:
        True 表示写入成功
    """
    stack_lower = stack.lower()
    if stack_lower == "plc":
        intent = "plc_review"
        target_skill = "plc-electrical-engineer"
    elif stack_lower == "python":
        intent = "project_followup"
        target_skill = "fullstack-engineer"
    else:
        intent = "project_followup"
        target_skill = "pm-workflow"

    session_ref = f"PM_SESSION_{project_id}.md" if project_id else ""
    context = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "auto-pm CLI",
        "workspace_root": str(Path(workspace_root).resolve()),
        "request_id": f"CLI-{uuid.uuid4().hex[:12].upper()}",
        "entry_mode": entry_mode,
        "intent": intent,
        "target_skill": target_skill,
        "active_project": {
            "id": project_id,
            "name": project_name,
            "stack": stack,
            "phase": phase,
        },
        "active_change": None,
        "active_page": active_page,
        "product_context": {
            "goal_ref": f"{session_ref}#product-goal" if session_ref else "",
            "hypothesis_ref": f"{session_ref}#hypothesis-ledger" if session_ref else "",
            "success_metric_ref": "",
            "active_hypothesis": {},
        },
    }

    try:
        ai_dir = Path(workspace_root) / ".auto-pm"
        ai_dir.mkdir(parents=True, exist_ok=True)
        ctx_file = ai_dir / "ai_context.json"
        ctx_file.write_text(
            json.dumps(context, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log.debug("AI 上下文已写入: %s (%d bytes)", ctx_file, len(json.dumps(context)))
        return True
    except Exception as e:
        log.warning("写入 AI 上下文失败: %s", e)
        return False
