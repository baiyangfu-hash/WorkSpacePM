"""PLC-HMI 概念映射：SFB 库函数（规范配置（规范检查规则/参数配置））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_SPEC_DIRS = [
    "00_Obsidian_Base全局规范文件仓库/01_项目管理域",
    "00_Obsidian_Base全局规范文件仓库/02_Python开发域",
    "00_Obsidian_Base全局规范文件仓库/03_PLC自动化域",
    "00_Obsidian_Base全局规范文件仓库/04_驾驶舱与全栈域",
    "0100_PLC自动化/00_通用规范",
    "01_Project自动化项目管理/00_通用规范",
]

DEFAULT_ARCHIVE_DIR = "00_Obsidian_Base全局规范文件仓库/_archive"

DEFAULT_REGISTRY_PATH = "00_Obsidian_Base全局规范文件仓库/spec_registry.json"

CHECK_SCOPES = ("workspace", "project")

DEFAULT_OUTPUT_PATHS = {
    "pm_index": "00_Obsidian_Base全局规范文件仓库/00_INDEX_全局规范索引.md",
    "plc_readme": "0100_PLC自动化/00_通用规范/README.md",
    "python_readme": "01_Project自动化项目管理/00_通用规范/README.md",
    "report": "00_Obsidian_Base全局规范文件仓库/health_report.md",
}

DOMAIN_CONFIG: dict[str, dict[str, Any]] = {
    "pm": {
        "title": "全局规范索引",
        "output_path": "00_Obsidian_Base全局规范文件仓库/00_INDEX_全局规范索引.md",
        "sub_domains": {
            "00_元规则与治理": "元规则与治理",
            "01_启动阶段": "启动阶段",
            "02_规划阶段": "规划阶段",
            "03_执行管控": "执行管控",
            "04_变更管理": "变更管理",
            "05_收尾验收": "收尾验收",
        },
    },
    "plc": {
        "title": "PLC自动化项目通用规范库",
        "output_path": "0100_PLC自动化/00_通用规范/README.md",
        "sub_domains": {
            "03_PLC自动化域": "PLC自动化规范",
            "PLC编程": "PLC编程规范",
            "项目管理": "项目管理规范",
        },
    },
    "python": {
        "title": "Python自动化项目通用规范库",
        "output_path": "01_Project自动化项目管理/00_通用规范/README.md",
        "sub_domains": {
            "02_Python开发域": "Python开发规范",
            "Python开发": "Python开发规范",
        },
    },
    "cockpit": {
        "title": "驾驶舱与全栈开发规范库",
        "output_path": "00_Obsidian_Base全局规范文件仓库/04_驾驶舱与全栈域/README.md",
        "sub_domains": {
            "04_驾驶舱与全栈域": "驾驶舱与全栈规范",
        },
    },
}

CORE_IDS: dict[str, list[str]] = {
    "plc": ["LSP-905", "LSP-907"],
    "python": ["CODE-210"],
}

AUTO_GENERATED_HEADER = "⚠️ 本文件由spec_registry.json自动生成，请勿手动编辑"

DOMAIN_ORDER = ["pm", "plc", "python", "cross-domain"]

DOMAIN_LABELS = {
    "pm": "项目管理域 (PM)",
    "plc": "PLC自动化域 (PLC)",
    "python": "Python开发域 (Python)",
    "cross-domain": "跨域通用 (Cross-Domain)",
}

SUB_DOMAIN_ORDER = {
    "00_元规则与治理": 0,
    "01_启动阶段": 1,
    "02_规划阶段": 2,
    "03_执行管控": 3,
    "04_变更管理": 4,
    "05_收尾验收": 5,
    "PLC编程": 10,
    "项目管理": 11,
    "Python开发": 20,
    "_archive/deprecated": 90,
    "_archive/history": 91,
}

LIFECYCLE_ICONS = {
    "stable": "🟢",
    "deprecated": "🟡",
    "archived": "⚪",
    "draft": "🔵",
}


@dataclass
class WorkspaceConfig:
    workspace: Path
    spec_dirs: list[str] = field(default_factory=lambda: list(DEFAULT_SPEC_DIRS))
    archive_dir: str = DEFAULT_ARCHIVE_DIR
    registry_path: str = DEFAULT_REGISTRY_PATH
    output_paths: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_OUTPUT_PATHS))

    @property
    def full_registry_path(self) -> Path:
        return self.workspace / self.registry_path

    @property
    def full_archive_dir(self) -> Path:
        return self.workspace / self.archive_dir

    @property
    def full_spec_dirs(self) -> list[Path]:
        return [self.workspace / d for d in self.spec_dirs]

    @property
    def full_output_paths(self) -> dict[str, Path]:
        return {k: self.workspace / v for k, v in self.output_paths.items()}


def load_config(config_path: str | Path | None = None) -> WorkspaceConfig:
    if config_path is not None:
        config_path = Path(config_path)
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            workspace = Path(data.get("workspace", ".")).resolve()
            spec_dirs = data.get("spec_dirs", list(DEFAULT_SPEC_DIRS))
            archive_dir = data.get("archive_dir", DEFAULT_ARCHIVE_DIR)
            registry_path = data.get("registry_path", DEFAULT_REGISTRY_PATH)
            output_paths = data.get("output_paths", dict(DEFAULT_OUTPUT_PATHS))
            return WorkspaceConfig(
                workspace=workspace,
                spec_dirs=spec_dirs,
                archive_dir=archive_dir,
                registry_path=registry_path,
                output_paths=output_paths,
            )

    workspace = Path(".").resolve()
    return WorkspaceConfig(workspace=workspace)
