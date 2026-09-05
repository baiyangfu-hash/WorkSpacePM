from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from auto_pm.spec.core.config import WorkspaceConfig


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "test_workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def spec_dirs(workspace: Path) -> list[Path]:
    dirs = [
        workspace / "00_Obsidian_Base全局规范文件仓库" / "01_项目管理域",
        workspace / "0100_PLC自动化" / "00_通用规范",
        workspace / "01_Project自动化项目管理" / "00_通用规范",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    return dirs


@pytest.fixture
def registry_dir(workspace: Path) -> Path:
    d = workspace / "00_Obsidian_Base全局规范文件仓库"
    d.mkdir(parents=True, exist_ok=True)
    return d


SAMPLE_REGISTRY: dict[str, Any] = {
    "version": "1.0.0",
    "last_updated": "2026-05-25",
    "workspace_root": "/test",
    "domains": {
        "pm": "项目管理域",
        "plc": "PLC自动化域",
        "python": "Python开发域",
        "cross-domain": "跨域通用",
    },
    "lifecycle_states": {
        "stable": "稳定",
        "draft": "草稿",
        "deprecated": "已废弃",
        "archived": "已归档",
    },
    "specs": {
        "PM-2026-001": {
            "title": "项目管理规范",
            "number": "PM-001",
            "canonical_path": "00_Obsidian_Base全局规范文件仓库/01_项目管理域/PM-2026-001_项目管理规范_DEV.md",
            "version": "V1.0.0",
            "type_prefix": "PM",
            "domain": "pm",
            "lifecycle": "stable",
            "sub_domain": "01_启动阶段",
            "tags": ["项目管理"],
            "replaces": [],
            "replaced_by": [],
        },
        "PLC-2026-001": {
            "title": "PLC编程规范",
            "number": "PLC-001",
            "canonical_path": "0100_PLC自动化/00_通用规范/PLC-2026-001_PLC编程规范_DEV.md",
            "version": "V1.0.0",
            "type_prefix": "PLC",
            "domain": "plc",
            "lifecycle": "stable",
            "sub_domain": "PLC编程",
            "tags": ["PLC"],
            "replaces": [],
            "replaced_by": [],
        },
        "CODE-210": {
            "title": "Python编程规范",
            "number": "CODE-210",
            "canonical_path": "01_Project自动化项目管理/00_通用规范/CODE-210_Python编程规范_DEV.md",
            "version": "V1.1.0",
            "type_prefix": "CODE",
            "domain": "python",
            "lifecycle": "stable",
            "sub_domain": "Python开发",
            "tags": ["Python"],
            "replaces": [],
            "replaced_by": [],
        },
        "PM-2026-002": {
            "title": "旧版管理规范",
            "number": "PM-002",
            "canonical_path": "00_Obsidian_Base全局规范文件仓库/_archive/PM-2026-002_旧版管理规范_DEV.md",
            "version": "V0.9.0",
            "type_prefix": "PM",
            "domain": "pm",
            "lifecycle": "deprecated",
            "sub_domain": "01_启动阶段",
            "tags": [],
            "replaces": [],
            "replaced_by": ["PM-2026-001"],
        },
    },
    "project_copies": [],
}


@pytest.fixture
def registry_json(registry_dir: Path) -> Path:
    path = registry_dir / "spec_registry.json"
    path.write_text(json.dumps(SAMPLE_REGISTRY, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def populated_workspace(workspace: Path, spec_dirs: list[Path], registry_json: Path) -> Path:
    for spec_id, info in SAMPLE_REGISTRY["specs"].items():
        file_path = workspace / info["canonical_path"]
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            f"---\nspec_id: {spec_id}\ntitle: {info['title']}\nversion: {info['version']}\nlifecycle: {info['lifecycle']}\n---\n\n# {info['title']}\n\n版本: {info['version']}\n",
            encoding="utf-8",
        )
    return workspace


@pytest.fixture
def config(workspace: Path) -> WorkspaceConfig:
    return WorkspaceConfig(workspace=workspace)
