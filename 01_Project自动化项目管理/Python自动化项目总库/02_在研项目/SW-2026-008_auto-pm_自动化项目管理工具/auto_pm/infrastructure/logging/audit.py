"""PLC-HMI 概念映射：SFB 库函数（审计日志（操作记录/变更追踪））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

关键操作审计日志

电气部门试用期间的操作行为审计能力。记录项目创建/删除/变更单流转/PLC 检查等
关键操作，写入 ``~/.auto-pm/audit/audit-YYYYMMDD.log``（按天轮转，保留 90 天）。

与 ``logging.py`` 的运行日志分离，审计日志独立存放便于审计追溯。

Usage:
    from auto_pm.logging.audit import audit_log

    audit_log("project_create", project_id="DJ-2026-100", stack="plc", user="electrical")
    audit_log("change_transition", change_number="CHG-SCPT-2026-083",
              from_status="draft", to_status="submitted")
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from auto_pm.logging.logging import _SilentTimedRotatingFileHandler

# AUTO_PM_AUDIT_DIR 设为以下值时禁用审计日志（不创建目录、不写文件）
_AUDIT_DISABLED_VALUES = {"off", "disabled", "none", "0", "false", ""}


def _get_audit_dir() -> Path | None:
    """获取审计日志目录路径。

    默认 ``~/.auto-pm/audit/``，可通过环境变量 ``AUTO_PM_AUDIT_DIR`` 覆盖。
    设为 off/disabled/none 等值，或目录创建失败时返回 ``None`` 表示禁用
    （静默降级，避免 Trae Sandbox 等限制用户目录写入时污染退出码）。
    """
    audit_dir_env = os.environ.get("AUTO_PM_AUDIT_DIR")
    if audit_dir_env is not None and audit_dir_env.strip().lower() in _AUDIT_DISABLED_VALUES:
        return None

    audit_dir = (
        Path(audit_dir_env).expanduser() if audit_dir_env else Path.home() / ".auto-pm" / "audit"
    )
    try:
        audit_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        return None
    return audit_dir


# 审计 logger 单例（独立于运行日志 logger，避免相互污染）
_audit_logger: logging.Logger | None = None


def _get_audit_logger() -> logging.Logger:
    """获取审计 logger 单例（幂等初始化）"""
    global _audit_logger
    if _audit_logger is not None:
        return _audit_logger

    logger = logging.getLogger("auto_pm.audit")
    logger.setLevel(logging.INFO)
    # 审计日志不向上传播到 root logger，避免重复输出
    logger.propagate = False

    if not logger.handlers:
        audit_dir = _get_audit_dir()
        if audit_dir is None:
            # 审计日志被禁用或目录不可写：不挂文件 handler，audit_log 静默 no-op
            _audit_logger = logger
            return logger

        formatter = logging.Formatter("%(asctime)s | %(message)s")
        try:
            # 使用 _SilentTimedRotatingFileHandler：emit 失败时静默移除自身，
            # 避免 Trae Sandbox 等限制 ~/.auto-pm/ 写入时污染 stderr（影响 Click 测试）。
            handler = _SilentTimedRotatingFileHandler(
                filename=str(audit_dir / "audit.log"),
                when="midnight",
                interval=1,
                backupCount=90,  # 审计日志保留 90 天（比运行日志 30 天更长）
                encoding="utf-8",
                delay=True,
            )
            handler.setFormatter(formatter)
            handler.setLevel(logging.INFO)
            logger.addHandler(handler)
        except (OSError, PermissionError):
            # 审计目录创建/写入失败时静默跳过，不阻断业务操作
            pass

    _audit_logger = logger
    return logger


def audit_log(action: str, **details: Any) -> None:
    """记录关键操作审计日志

    Args:
        action: 操作类型（如 project_create/project_delete/change_transition/
            plc_check/spec_check）
        **details: 操作详情键值对（如 project_id="DJ-2026-100", user="electrical"）

    Examples:
        >>> audit_log("project_create", project_id="DJ-2026-100", stack="plc")
        >>> audit_log("change_transition", change_number="CHG-SCPT-2026-083",
        ...           from_status="draft", to_status="submitted")
        >>> audit_log("plc_check", project_id="DJ-2026-100",
        ...           pass_count=20, warn_count=1, fail_count=0)
    """
    logger = _get_audit_logger()
    # 审计日志格式：时间戳 | ACTION=xxx | KEY1=VAL1 | KEY2=VAL2 ...
    # details 中的值用 JSON 序列化，确保复杂类型（list/dict）可读
    parts = [f"ACTION={action}"]
    for key, value in details.items():
        try:
            # 简单字符串/数字直接输出，复杂类型用 JSON
            if isinstance(value, str | int | float | bool):
                parts.append(f"{key}={value}")
            else:
                parts.append(f"{key}={json.dumps(value, ensure_ascii=False, default=str)}")
        except (TypeError, ValueError):
            parts.append(f"{key}=<unserializable>")

    # 附加时间戳（便于审计日志与运行日志交叉对照）
    parts.append(f"ts={datetime.now().isoformat()}")
    logger.info(" | ".join(parts))
