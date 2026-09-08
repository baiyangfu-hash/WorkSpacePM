"""Application 层集成测试共享 fixture

为 SpecFacade / DeliveryFacade / SystemFacade 集成测试提供：
- temp_workspace: 临时工作空间（含 .plc.json 项目标志）
- db_manager: 已 init_schema 的 DatabaseManager
- project_repo_with_data: 预置 2 个项目记录
- change_repo_with_data: 预置 1 个变更记录
- templates_dir: 含 2 个模板的目录（plc-standard + python-standard）
- spec_registry_workspace: 含最小 spec_registry.json 的工作空间

参考 tests/change/conftest.py 模式，避免在多个 _int.py 中重复构造。
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.repository import ChangeRequestRepository, ProjectRepository
from auto_pm.models.change import ChangeSummary
from auto_pm.models.project import ProjectRecord


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Generator[str, None, None]:
    """临时工作空间（含一个 PLC 项目 + 一个 Python 项目标志）"""
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()

    # 两个项目目录
    plc_dir = ws_dir / "02_在研项目" / "DJ-2026-001_测试PLC"
    plc_dir.mkdir(parents=True)
    (plc_dir / ".plc.json").write_text(
        json.dumps(
            {"name": "DJ-2026-001", "version": "V1.0.0", "type": "standard"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    py_dir = ws_dir / "02_在研项目" / "SW-2026-001_测试Python"
    py_dir.mkdir(parents=True)
    # .copier-answers.yml 含 stack 字段，让 ProjectScanner 正确识别为 python 项目
    (py_dir / ".copier-answers.yml").write_text(
        "project_id: SW-2026-001\nproject_name: 测试Python\nstack: python\n",
        encoding="utf-8",
    )

    yield str(ws_dir)
    shutil.rmtree(ws_dir, ignore_errors=True)


@pytest.fixture
def db_manager(temp_workspace: str) -> Generator[DatabaseManager, None, None]:
    """已 init_schema 的 DatabaseManager（temp_workspace 下）"""
    db = DatabaseManager(temp_workspace)
    db.init_schema()
    yield db
    # 显式释放引用 + GC，避免 Windows SQLite WAL 文件锁
    db.close()  # CHG-100 T2: 显式关闭复用连接
    import gc

    gc.collect()


@pytest.fixture
def project_repo_with_data(
    db_manager: DatabaseManager,
    temp_workspace: str,
) -> ProjectRepository:
    """预置 2 个项目记录的 ProjectRepository

    - DJ-2026-001: plc / developing / SW
    - SW-2026-001: python / production / DJ

    注：path 使用绝对路径（对齐 ProjectScanner 行为），确保 DocRefreshService /
    AssetSummaryService 等依赖绝对路径的 Service 能正常工作。
    """
    repo = ProjectRepository(db_manager)
    repo.upsert(
        ProjectRecord(
            project_id="DJ-2026-001",
            name="测试PLC",
            path=str(Path(temp_workspace) / "02_在研项目" / "DJ-2026-001_测试PLC"),
            stack="plc",
            version="1.0.0",
            phase="developing",
            business_line="SW",
        )
    )
    repo.upsert(
        ProjectRecord(
            project_id="SW-2026-001",
            name="测试Python",
            path=str(Path(temp_workspace) / "02_在研项目" / "SW-2026-001_测试Python"),
            stack="python",
            version="0.5.0",
            phase="production",
            business_line="DJ",
        )
    )
    return repo


@pytest.fixture
def change_repo_with_data(
    db_manager: DatabaseManager,
) -> ChangeRequestRepository:
    """预置 1 个变更记录的 ChangeRequestRepository

    - CHG-2026-001: DOCU / approved / SW-2026-001
    """
    repo = ChangeRequestRepository(db_manager)
    repo.upsert(
        ChangeSummary(
            change_number="CHG-2026-001",
            project_id="SW-2026-001",
            project_name="测试Python",
            domain="DOCU",
            business_nature="DEF",
            impact_scope=["LOCAL"],
            status="approved",
            applicant="user1",
            apply_date="2026-07-07",
            title="测试变更单",
            urgency="normal",
        )
    )
    return repo


@pytest.fixture
def templates_dir(tmp_path: Path) -> Path:
    """含 2 个模板的目录（plc-standard + python-standard）

    每个模板含 copier.yml，供 TemplateService.list_templates / get_template_path 使用。
    """
    tpl_root = tmp_path / "templates"
    tpl_root.mkdir()

    # plc-standard 模板
    plc_tpl = tpl_root / "plc-standard"
    plc_tpl.mkdir()
    (plc_tpl / "copier.yml").write_text(
        "_description: PLC 标准模板\n_commit: v1.2.0\n",
        encoding="utf-8",
    )

    # python-standard 模板
    py_tpl = tpl_root / "python-standard"
    py_tpl.mkdir()
    (py_tpl / "copier.yml").write_text(
        "_description: Python 标准模板\n_commit: v0.3.0\n",
        encoding="utf-8",
    )

    # 无 copier.yml 的目录（应被 TemplateService 忽略）
    (tpl_root / "not-a-template").mkdir()

    return tpl_root


@pytest.fixture
def spec_registry_workspace(tmp_path: Path) -> Path:
    """含最小 spec_registry.json 的工作空间

    构造 2 条规范记录（plc + python），并在工作空间下创建对应的规范文件，
    供 CheckService / SpecCenterAdapter / ReportService.get_spec_report 使用。

    spec_registry.json 路径对齐 WorkspaceConfig 默认值：
    `<workspace>/00_Obsidian_Base全局规范文件仓库/spec_registry.json`
    """
    ws = tmp_path / "spec_ws"
    ws.mkdir()

    # 规范文件目录
    plc_spec_dir = ws / "0100_PLC自动化" / "00_通用规范" / "PLC编程"
    plc_spec_dir.mkdir(parents=True)
    plc_spec_file = plc_spec_dir / "905_SCL编程规范.md"
    plc_spec_file.write_text("# SCL 编程规范\n", encoding="utf-8")

    py_spec_dir = ws / "01_Project自动化项目管理" / "00_通用规范" / "Python开发"
    py_spec_dir.mkdir(parents=True)
    # python 规范文件故意不创建，制造 missing 项用于测试

    # spec_registry.json（对齐 WorkspaceConfig 默认 registry_path）
    registry_dir = ws / "00_Obsidian_Base全局规范文件仓库"
    registry_dir.mkdir(parents=True)
    registry_data = {
        "version": "1.0",
        "specs": {
            "LSP-905": {
                "spec_id": "LSP-905",
                "title": "SCL 编程规范",
                "number": "905",
                "domain": "plc",
                "lifecycle": "active",
                "canonical_path": "0100_PLC自动化/00_通用规范/PLC编程/905_SCL编程规范.md",
                "version": "V2.0",
            },
            "CODE-210": {
                "spec_id": "CODE-210",
                "title": "Python 编码规范",
                "number": "210",
                "domain": "python",
                "lifecycle": "active",
                "canonical_path": "01_Project自动化项目管理/00_通用规范/Python开发/210_Python编码规范.md",
                "version": "V1.0",
            },
        },
    }
    (registry_dir / "spec_registry.json").write_text(
        json.dumps(registry_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return ws
