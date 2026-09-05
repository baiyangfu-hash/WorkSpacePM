"""工作空间治理服务：提供根目录纯净度校验与游离日志/临时文件自动清扫 (CHG-SCPT-2026-155)"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# 根目录允许保留的标准白名单节点（不区分大小写比较）
ROOT_WHITELIST: set[str] = {
    "00_obsidian_base全局规范文件仓库",
    "01_project自动化项目管理",
    "0100_plc自动化",
    "sys-2026-001_workspacegovernance",
    "docs",
    ".git",
    ".gitignore",
    ".gitattributes",
    ".dockerignore",
    ".github",
    ".devcontainer",
    ".cursor",
    ".agents",
    ".idea",
    ".venv",
    ".trae",
    ".auto-pm",
    ".vs",
    ".vscode",
    "agents.md",
    "readme.md",
    "license",
    "main.py",
    "requirements.txt",
    "setup_env.bat",
    "双击启动驾驶舱.bat",
}


@dataclass
class SanitationIssue:
    file_path: Path
    relative_path: str
    issue_type: str  # 'unauthorized_root_file' | 'temp_log' | 'temp_script'
    description: str


@dataclass
class SanitationReport:
    is_pure: bool
    unauthorized_files: list[SanitationIssue] = field(default_factory=list)
    temp_files: list[SanitationIssue] = field(default_factory=list)

    @property
    def total_issues(self) -> int:
        return len(self.unauthorized_files) + len(self.temp_files)


class GovernanceService:
    """工作空间治理的核心服务引擎"""

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        if workspace_root is None:
            workspace_root = Path.cwd()

        curr = Path(workspace_root).resolve()
        top_root = curr
        # 向上寻找包含 SYS-2026-001 或 00_Obsidian_Base 或 0100_PLC自动化 的超级工作区根目录
        while curr.parent != curr:
            if (
                (curr / "SYS-2026-001_WorkspaceGovernance").exists()
                or (curr / "00_Obsidian_Base全局规范文件仓库").exists()
                or (curr / "0100_PLC自动化").exists()
            ):
                top_root = curr
                break
            curr = curr.parent

        self.workspace_root = top_root

    def get_log_dir(self) -> Path:
        """获取全工作区统一日志与日志重定向收容池目录"""
        log_dir = self.workspace_root / ".auto-pm" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    def inspect_sanitation(self) -> SanitationReport:
        """检查工作区根目录及关联目录的纯净度"""
        report = SanitationReport(is_pure=True)

        if not self.workspace_root.exists():
            return report

        for item in self.workspace_root.iterdir():
            name_lower = item.name.lower()
            if name_lower in ROOT_WHITELIST:
                continue

            rel_path = str(item.relative_to(self.workspace_root))

            # 检查是否为临时日志或散落脚本
            if item.is_file():
                if name_lower.startswith("mypy") and name_lower.endswith(".txt"):
                    report.temp_files.append(
                        SanitationIssue(
                            file_path=item,
                            relative_path=rel_path,
                            issue_type="temp_log",
                            description="游离的 mypy 校验输出日志",
                        )
                    )
                elif name_lower.endswith(".log"):
                    report.temp_files.append(
                        SanitationIssue(
                            file_path=item,
                            relative_path=rel_path,
                            issue_type="temp_log",
                            description="游离的测试/运行日志文件",
                        )
                    )
                elif name_lower.startswith(".tmp_") and name_lower.endswith(".py"):
                    report.temp_files.append(
                        SanitationIssue(
                            file_path=item,
                            relative_path=rel_path,
                            issue_type="temp_script",
                            description="游离的临时 Python 脚本",
                        )
                    )
                else:
                    report.unauthorized_files.append(
                        SanitationIssue(
                            file_path=item,
                            relative_path=rel_path,
                            issue_type="unauthorized_root_file",
                            description="未经白名单备案的根目录散落文件",
                        )
                    )

        report.is_pure = report.total_issues == 0
        return report

    def clean_workspace(self, clean_cache: bool = False) -> list[str]:
        """清理工作区游离文件及（可选）编译缓存"""
        cleaned_paths: list[str] = []
        report = self.inspect_sanitation()

        # 清理游离临时日志与脚本
        for issue in report.temp_files:
            try:
                if issue.file_path.is_file():
                    issue.file_path.unlink()
                    cleaned_paths.append(issue.relative_path)
            except OSError:
                pass

        if clean_cache:
            # 清理常见 Python 缓存目录
            cache_patterns = [".pytest_cache", ".ruff_cache", "__pycache__"]
            for root, dirs, _files in os.walk(self.workspace_root):
                for d in dirs:
                    if d in cache_patterns:
                        p = Path(root) / d
                        try:
                            import shutil

                            shutil.rmtree(p, ignore_errors=True)
                            cleaned_paths.append(str(p.relative_to(self.workspace_root)))
                        except Exception:
                            pass

        return cleaned_paths
