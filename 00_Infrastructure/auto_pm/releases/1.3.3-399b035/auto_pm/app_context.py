"""PLC-HMI 概念映射：SFB 库函数（应用上下文（全局状态管理/工作空间信息））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

应用上下文 - 持有 CLI 命令所需的全局对象"""

from __future__ import annotations

import os

from auto_pm import __app_name__
from auto_pm.infrastructure.config.app_config import AutoPmConfig
from auto_pm.infrastructure.logging.logging import PACKAGE_LOGGER_NAME, setup_logger


class AppContext:
    """Holds all the objects needed by commands"""

    def __init__(self, workspace_root: str = "") -> None:
        self.app_config = AutoPmConfig(app_name=__app_name__)
        # 挂在包日志器 auto_pm 上：各模块 getLogger(__name__) 都是它的子节点，日志才进得了 auto-pm.log。
        # 控制台只打 WARNING 以上、且只在根日志器没有 handler 时打，和修复前 Python 兜底输出的条件完全一致，
        # 命令行输出不多一行也不少一行；文件按配置级别全记。
        self.logger = setup_logger(
            log_level=self.app_config.log_level,
            app_name=PACKAGE_LOGGER_NAME,
            console_level="WARNING",
            console_as_last_resort=True,
        )
        # 工作空间根目录（项目库所在目录）
        if not workspace_root:
            workspace_root = os.environ.get("AUTO_PM_WORKSPACE", "")
        if not workspace_root:
            from auto_pm.application.core.paths import get_config_file_path
            cfg_file = get_config_file_path()
            if os.path.isfile(cfg_file):
                try:
                    with open(cfg_file, encoding="utf-8") as f:
                        val = f.read().strip()
                        if val:
                            if os.path.isabs(val):
                                workspace_root = val
                            else:
                                # 相对路径转换为相对于配置文件所在目录的绝对路径
                                workspace_root = os.path.abspath(
                                    os.path.join(os.path.dirname(cfg_file), val)
                                )
                except Exception:
                    pass
        if not workspace_root:
            # 向上攀爬搜寻包含关键特征标识的顶级工作空间根目录
            # Started through the launcher the process sits in the release folder; the user's own folder is AUTO_PM_CALLER_CWD.
            curr = os.path.abspath(os.environ.get("AUTO_PM_CALLER_CWD") or os.getcwd())
            while True:
                anchors = [
                    ".auto-pm",
                    ".git",
                    "00_Obsidian_Base全局规范文件仓库",
                    "0100_PLC自动化",
                    "01_Project自动化项目管理",
                    "Workspace_Handoff_Document.md",
                    "AGENTS.md",
                ]
                if any(os.path.exists(os.path.join(curr, a)) for a in anchors):
                    workspace_root = curr
                    break
                parent = os.path.dirname(curr)
                if parent == curr:
                    break
                curr = parent
        self.workspace_root: str = workspace_root or os.getcwd()
        # PM cold-start commands may execute from a linked candidate while every
        # governed record remains in the primary control root.  The default keeps
        # the historical single-root contract intact for all other commands.
        self.control_root: str = self.workspace_root

    @property
    def templates_dir(self) -> str:
        """模板目录：项目根目录下的 templates/"""
        # auto_pm/app_context.py -> auto_pm/ -> 项目根/templates/
        package_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(package_dir)
        return os.path.join(project_root, "templates")
