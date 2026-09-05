"""Bug-2 回归测试: _sync_changes 路径错误

问题: SyncService._sync_changes 在 ``04_监控/01_变更管理`` 查找变更单，
      实际路径是 ``04_监控/01_变更管理/01_变更单/CHG-{domain}/CHG-*.md``。
修复: 修正扫描路径为 ``04_监控/01_变更管理/01_变更单``，
      并让 _find_change_file 搜索 ``CHG-{domain}/`` 子目录。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.core.project_service import ProjectService
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.sync import SyncService

# ── Fixtures ──────────────────────────────────────────


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    """创建测试用数据库"""
    db = DatabaseManager(str(tmp_path))
    db.init_schema()
    return db


def _make_change_file(project_dir: Path, change_number: str, domain: str) -> str:
    """在项目目录下创建变更单文件（正确路径结构）

    路径: 04_监控/01_变更管理/01_变更单/CHG-{domain}/CHG-*.md
    """
    chg_dir = project_dir / "04_监控" / "01_变更管理" / "01_变更单" / f"CHG-{domain}"
    chg_dir.mkdir(parents=True, exist_ok=True)
    chg_file = chg_dir / f"{change_number}.md"
    chg_file.write_text(
        f"# 变更单\n\n"
        "## 3. 变更基本信息\n\n"
        "### 3.0 编号与项目\n"
        "| 字段 | 内容 |\n|------|------|\n"
        f"| 变更编号 | {change_number} |\n"
        "| 项目编号 | DJ-2026-001 |\n\n"
        f"### 3.1 技术领域（必选）\n"
        "| 领域 | 选择 |\n|------|------|\n"
        f"| ☑ **{domain}** | **选中** |\n\n"
        "### 3.2 业务性质（必选）\n"
        "| 性质 | 选择 |\n|------|------|\n"
        "| ☑ **DEF** 缺陷修复 | **选中** |\n\n"
        "### 3.3 影响范围（可多选）\n"
        "| 范围 | 选择 |\n|------|------|\n"
        "| ☑ **LOCAL** 局部变更 | **选中** |\n\n"
        "### 3.4 申请信息\n"
        "| 字段 | 内容 |\n|------|------|\n"
        "| 变更申请人 | 测试 |\n"
        "| 申请日期 | 2026-01-01 |\n",
        encoding="utf-8",
    )
    return str(chg_file)


@pytest.fixture
def workspace_with_change(tmp_path: Path) -> Path:
    """创建包含变更单的工作空间

    项目目录命名为 {project_id}_{project_name}（实际约定），
    变更单位于 04_监控/01_变更管理/01_变更单/CHG-DOCU/ 下。
    """
    project_dir = tmp_path / "DJ-2026-001_测试项目"
    project_dir.mkdir()
    # .plc.json 让 ProjectService 能识别项目
    (project_dir / ".plc.json").write_text(
        json.dumps(
            {"name": "DJ-2026-001", "version": "V1.0.0", "description": "测试项目"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # 创建变更单（正确路径结构）
    _make_change_file(project_dir, "CHG-DOCU-2026-001", "DOCU")
    return tmp_path


# ── _find_change_file 测试 ────────────────────────────


class TestFindChangeFileSubdir:
    """_find_change_file 在 CHG-{domain}/ 子目录下查找"""

    def test_find_in_chg_subdir(self, tmp_path: Path) -> None:
        """变更单位于 CHG-{domain}/ 子目录下时应能找到"""
        change_dir = tmp_path / "01_变更单"
        chg_subdir = change_dir / "CHG-DOCU"
        chg_subdir.mkdir(parents=True)
        (chg_subdir / "CHG-DOCU-2026-001.md").write_text("# 变更单\n", encoding="utf-8")

        result = SyncService._find_change_file(str(change_dir), "CHG-DOCU-2026-001")
        assert result is not None
        assert result.endswith(os.path.join("CHG-DOCU", "CHG-DOCU-2026-001.md"))

    def test_find_in_multiple_subdirs(self, tmp_path: Path) -> None:
        """多个 CHG-{domain}/ 子目录时应找到对应文件"""
        change_dir = tmp_path / "01_变更单"
        for domain in ("DOCU", "PLC"):
            sub = change_dir / f"CHG-{domain}"
            sub.mkdir(parents=True)
            (sub / f"CHG-{domain}-2026-001.md").write_text("# 变更单\n", encoding="utf-8")

        result = SyncService._find_change_file(str(change_dir), "CHG-PLC-2026-001")
        assert result is not None
        assert "CHG-PLC-2026-001.md" in result

    def test_not_found_in_subdirs(self, tmp_path: Path) -> None:
        """子目录中无目标文件时返回 None"""
        change_dir = tmp_path / "01_变更单"
        sub = change_dir / "CHG-DOCU"
        sub.mkdir(parents=True)
        (sub / "CHG-DOCU-2026-001.md").write_text("# 变更单\n", encoding="utf-8")

        result = SyncService._find_change_file(str(change_dir), "CHG-DOCU-2026-999")
        assert result is None


# ── _sync_changes 测试 ────────────────────────────────


class TestSyncChangesPath:
    """_sync_changes 路径修复测试"""

    def test_sync_changes_finds_change_in_correct_path(
        self, db: DatabaseManager, workspace_with_change: Path
    ) -> None:
        """_sync_changes 应在 04_监控/01_变更管理/01_变更单/ 下找到变更单"""
        project_service = ProjectService(str(workspace_with_change))
        change_service = ChangeService(str(workspace_with_change))
        sync = SyncService(db, project_service, change_service)

        # 先同步项目（填充 DB）
        sync._sync_projects(force_full=True)

        # 同步变更单
        count = sync._sync_changes(force_full=True)

        # 修复前: change_dir 路径错误 → isdir 检查失败 → continue → count=0
        # 修复后: 路径正确 → 找到变更单 → count=1
        assert count == 1

    def test_sync_changes_upserts_change_with_path(
        self, db: DatabaseManager, workspace_with_change: Path
    ) -> None:
        """同步的变更单应包含正确的文件路径"""
        project_service = ProjectService(str(workspace_with_change))
        change_service = ChangeService(str(workspace_with_change))
        sync = SyncService(db, project_service, change_service)

        sync._sync_projects(force_full=True)
        sync._sync_changes(force_full=True)

        # 从 DB 读取变更单记录
        changes = sync.change_repo.list_all()
        assert len(changes) == 1
        record = changes[0]
        assert record.change_number == "CHG-DOCU-2026-001"

        # ChangeSummary 不含 file_path，直接查询 DB 验证 file_path 列
        # （_find_change_file 应在 CHG-{domain}/ 子目录中找到文件）
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT file_path FROM change_requests WHERE change_number = ?",
                ("CHG-DOCU-2026-001",),
            ).fetchone()
        assert row is not None
        file_path = row["file_path"]
        assert file_path != ""
        assert os.path.isfile(file_path)

    def test_sync_changes_no_change_dir_returns_zero(
        self, db: DatabaseManager, tmp_path: Path
    ) -> None:
        """项目无变更单目录时返回 0"""
        # 创建无变更单的项目
        project_dir = tmp_path / "DJ-2026-002_无变更项目"
        project_dir.mkdir()
        (project_dir / ".plc.json").write_text(
            json.dumps({"name": "DJ-2026-002"}, ensure_ascii=False),
            encoding="utf-8",
        )

        project_service = ProjectService(str(tmp_path))
        change_service = ChangeService(str(tmp_path))
        sync = SyncService(db, project_service, change_service)

        sync._sync_projects(force_full=True)
        count = sync._sync_changes(force_full=True)
        assert count == 0
