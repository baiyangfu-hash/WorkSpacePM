"""PLC-HMI 概念映射：SFB 库函数（应用上下文（全局状态管理/工作空间信息））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

应用上下文 - 持有 CLI 命令所需的全局对象"""

from __future__ import annotations

import os

from auto_pm import __app_name__
from auto_pm.config.app_config import AutoPmConfig
from auto_pm.logging.logging import setup_logger


class AppContext:
    """Holds all the objects needed by commands"""

    def __init__(self, workspace_root: str = "") -> None:
        self.app_config = AutoPmConfig(app_name=__app_name__)
        self.logger = setup_logger(log_level=self.app_config.log_level, app_name=__app_name__)
        # 工作空间根目录（项目库所在目录）
        if not workspace_root:
            workspace_root = os.environ.get("AUTO_PM_WORKSPACE", "")
        if not workspace_root:
            from auto_pm.core.paths import get_config_file_path

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
            curr = os.path.abspath(os.getcwd())
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

    @property
    def templates_dir(self) -> str:
        """模板目录：项目根目录下的 templates/"""
        # auto_pm/app_context.py -> auto_pm/ -> 项目根/templates/
        package_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(package_dir)
        return os.path.join(project_root, "templates")
