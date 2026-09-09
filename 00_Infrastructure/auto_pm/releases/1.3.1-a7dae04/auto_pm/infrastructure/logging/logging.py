"""PLC-HMI 概念映射：SFB 库函数（日志系统（统一日志配置/输出））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


class _SilentTimedRotatingFileHandler(TimedRotatingFileHandler):
    """静默的 TimedRotatingFileHandler

    emit 失败时不输出到 stderr，避免污染 Click 测试的 result.output
    （测试环境中 Trae Sandbox 可能限制 ~/.auto-pm/ 写入，实际使用环境不受影响）。
    """

    def handleError(self, record: logging.LogRecord) -> None:
        # 静默处理 emit 失败（如文件权限不足、沙箱限制）。
        # 默认 Handler.handleError 会输出到 sys.stderr，污染 Click 测试的 result.output。
        # 首次失败后从所有 logger 中移除自身，避免后续每次 emit 都触发失败处理。
        try:
            for logger_obj in logging.Logger.manager.loggerDict.values():
                if isinstance(logger_obj, logging.Logger) and self in logger_obj.handlers:
                    logger_obj.removeHandler(self)
        except Exception:
            # 退化情况：连移除自身都失败，则完全静默
            pass


def _get_log_dir() -> Path:
    """获取日志目录路径（~/.auto-pm/logs/）

    目录不存在时自动创建。电气部门试用期间日志持久化的基础。
    """
    log_dir = Path.home() / ".auto-pm" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logger(
    *, app_name: str, log_level: str, bind_to: logging.Logger | None = None
) -> logging.Logger:
    """
    Set up a logger with the specified application name and log level.

    配置两个 handler：
    - ``StreamHandler(sys.stderr)``：控制台输出（避免污染 --json 等 stdout 机器可读输出）
    - ``TimedRotatingFileHandler``：文件持久化到 ``~/.auto-pm/logs/auto-pm.log``，
      按天轮转，保留 30 天。电气部门试用期间问题追溯的关键能力。

    Parameters
    ----------
    app_name : str
        The name of the application.
    log_level : str
        The logging level as a string (e.g., 'DEBUG', 'INFO', 'WARNING',
        'ERROR', 'CRITICAL').
    bind_to : logging.Logger | None, optional
        An existing logger to bind the new logger's handlers to, by
        default None. Typically used for fastapi applications.
        ```python
        from fastapi.logger import logger as fastapi_logger

        setup_logger(app_name="my_app", log_level="info", bind_to=fastapi_logger)
        ```

    Returns
    -------
    logging.Logger
        The configured logger instance.
    """
    logger = logging.getLogger(app_name)
    normalised_log_level = getattr(logging, log_level.upper()) or logging.INFO
    logger.setLevel(normalised_log_level)

    # 幂等：已配置 handler 则不再重复添加，仅更新级别
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s [%(levelname)8.8s] %(message)s")

        # 1. 控制台 handler（stderr，避免污染 stdout 机器可读输出）
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 2. 文件 handler（按天轮转，保留 30 天）——电气部门试用期间问题追溯
        # 使用 _SilentTimedRotatingFileHandler：emit 失败时静默移除自身，
        # 避免 Trae Sandbox 等限制 ~/.auto-pm/ 写入时污染 stderr（影响 Click 测试）。
        try:
            log_dir = _get_log_dir()
            file_handler = _SilentTimedRotatingFileHandler(
                filename=str(log_dir / "auto-pm.log"),
                when="midnight",
                interval=1,
                backupCount=30,
                encoding="utf-8",
                delay=True,
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(normalised_log_level)
            logger.addHandler(file_handler)
        except (OSError, PermissionError) as e:
            # 日志目录创建/写入失败时仅用控制台日志，不阻断应用启动
            logger.warning("文件日志 handler 初始化失败，仅使用控制台日志: %s", e)

    if bind_to:
        bind_to.handlers = logger.handlers
        bind_to.setLevel(log_level)

    return logger
