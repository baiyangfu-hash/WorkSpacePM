"""PLC-HMI 概念映射：SFB 库函数（数据库同步（文件系统变更同步到数据库））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

增量扫描同步服务

策略：
1. 启动时调用 sync()，基于 file_mtime 增量扫描工作空间
2. 新项目或 mtime 变化的项目 → 重新扫描并 UPSERT
3. 文件系统中已删除的项目 → 从 DB 删除
4. 变更单同理同步

文件系统为单一真源，DB 仅作缓存。
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any

from auto_pm.change.change_service import ChangeService
from auto_pm.core.paths import get_change_requests_paths
from auto_pm.core.project_service import ProjectService
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.repository import (
    ChangeRequestRepository,
    ProjectRepository,
    ScanLogRepository,
)
from auto_pm.models import ProjectRecord
from auto_pm.models.project import extract_business_line

log = logging.getLogger(__name__)

# CHG-085: 扫描器版本号。scanner 逻辑变更（如 stack/phase 推断规则修改）时递增，
# 增量同步检测到 DB 缓存的 scanner_version 与当前不一致时强制重扫该项目。
# 历史：v1=初始版本（仅 mtime 增量判据，存在 scanner 逻辑变更不触发重扫的 P1 缺陷）
SCANNER_VERSION = "v2"


class SyncService:
    """增量扫描同步服务

    协调 ProjectService（文件系统扫描）和 Repository（DB 缓存），
    保持 DB 与文件系统一致。
    """

    def __init__(
        self,
        db: DatabaseManager,
        project_service: ProjectService,
        change_service: ChangeService | None = None,
        scanner_version: str = SCANNER_VERSION,
    ) -> None:
        self.db = db
        self.project_service = project_service
        self.change_service = change_service
        self.scanner_version = scanner_version
        self.project_repo = ProjectRepository(db)
        self.change_repo = ChangeRequestRepository(db)
        self.scan_log_repo = ScanLogRepository(db)

    def sync(self, force_full: bool = False) -> dict[str, Any]:
        """同步 DB 与文件系统

        Args:
            force_full: True 强制全量扫描（忽略 mtime）

        Returns:
            扫描结果 dict: {
                "scan_type": "full" | "incremental",
                "projects_found": int,
                "changes_found": int,
                "duration_ms": int,
                "status": "success" | "failed",
                "message": str,
            }
        """
        start_time = time.time()
        scan_type = "full" if force_full else "incremental"

        try:
            self.db.init_schema()
            projects_synced = self._sync_projects(force_full)
            changes_synced = self._sync_changes(force_full)

            duration_ms = int((time.time() - start_time) * 1000)
            result = {
                "scan_type": scan_type,
                "projects_found": projects_synced,
                "changes_found": changes_synced,
                "duration_ms": duration_ms,
                "status": "success",
                "message": "",
            }

            self.scan_log_repo.insert(
                scan_type=scan_type,
                projects_found=projects_synced,
                changes_found=changes_synced,
                duration_ms=duration_ms,
                status="success",
                message="",
            )
            log.info(
                "同步完成: %s, %d 项目, %d 变更单, %dms",
                scan_type,
                projects_synced,
                changes_synced,
                duration_ms,
            )
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            result = {
                "scan_type": scan_type,
                "projects_found": 0,
                "changes_found": 0,
                "duration_ms": duration_ms,
                "status": "failed",
                "message": error_msg,
            }
            self.scan_log_repo.insert(
                scan_type=scan_type,
                projects_found=0,
                changes_found=0,
                duration_ms=duration_ms,
                status="failed",
                message=error_msg,
            )
            log.error("同步失败: %s", error_msg)
            return result

    def _sync_projects(self, force_full: bool) -> int:
        """同步项目索引

        Returns:
            同步的项目数
        """
        # 从文件系统扫描项目
        fs_projects = self.project_service.list_projects()
        fs_ids = {p.project_id for p in fs_projects}

        # 从 DB 获取现有项目
        db_projects = self.project_repo.list_all()
        db_ids = {p.project_id for p in db_projects}
        # CHG-085: 构建 project_id → DB 记录映射，用于增量模式检查 scanner_version
        db_records = {p.project_id: p for p in db_projects}

        synced = 0
        now = datetime.now().isoformat()

        for proj in fs_projects:
            # 获取标志文件的 mtime
            mtime = self._get_project_mtime(proj.path)

            if not force_full:
                db_record = db_records.get(proj.project_id)
                db_mtime = db_record.file_mtime if db_record else 0.0
                db_scanner_version = db_record.scanner_version if db_record else ""
                # CHG-085: 增量跳过需同时满足：mtime 无变化 + scanner_version 一致
                # 原 P1 缺陷：仅看 mtime，scanner 逻辑变更不触发已缓存项目重扫
                if (
                    proj.project_id in db_ids
                    and mtime <= db_mtime
                    and db_scanner_version == self.scanner_version
                ):
                    continue  # 无变化且 scanner 版本一致，跳过

            # 有变化或新项目，UPSERT
            # P1-② 修复：优先使用项目元数据中的 business_line 字段（用户创建时显式指定），
            # 仅在该字段为空时从项目编号前缀推断。原缺陷：始终用 extract_business_line()
            # 覆盖，会丢失用户显式指定的业务线（如编号前缀与实际业务线不一致的场景）。
            record = ProjectRecord(
                project_id=proj.project_id,
                name=proj.name,
                path=proj.path,
                stack=proj.stack,
                version=proj.version,
                description=proj.description,
                source=proj.source,
                phase=proj.phase,
                business_line=proj.business_line or extract_business_line(proj.project_id),
                extra=proj.extra,
                file_mtime=mtime,
                last_scanned=now,
                scanner_version=self.scanner_version,
            )
            self.project_repo.upsert(record)
            synced += 1

        # 删除文件系统中已不存在的项目
        stale_ids = db_ids - fs_ids
        for stale_id in stale_ids:
            self.project_repo.delete(stale_id)
            self.change_repo.delete_by_project(stale_id)
            log.info("已删除过期项目: %s", stale_id)

        return synced

    def _sync_changes(self, force_full: bool) -> int:
        """同步变更单索引

        Returns:
            同步的变更单数
        """
        if self.change_service is None:
            return 0

        synced = 0
        db_projects = self.project_repo.list_all()

        for proj in db_projects:
            # 查找项目目录下的变更单文件
            # 实际路径: 00_项目管理/04_变更管理/01_变更单/CHG-{domain}/CHG-*.md
            # CHG-SCPT-2026-144: 改为遍历 get_change_requests_paths 支持多套目录约定
            change_dir = None
            for candidate in get_change_requests_paths(proj.path):
                if os.path.isdir(candidate):
                    change_dir = candidate
                    break
            if not change_dir:
                continue

            try:
                # 使用 ChangeService 扫描变更单
                summaries = self.change_service.list_change_requests(proj.project_id)
            except Exception as e:
                log.warning("扫描变更单失败: %s: %s", proj.project_id, e)
                continue

            for summary in summaries:
                # 获取变更单文件 mtime
                chg_path = self._find_change_file(change_dir, summary.change_number)
                chg_mtime = os.path.getmtime(chg_path) if chg_path else 0

                self.change_repo.upsert(summary, chg_path or "", chg_mtime)
                synced += 1

        return synced

    @staticmethod
    def _get_project_mtime(project_path: str) -> float:
        """获取项目标志文件的 mtime（委托给 ProjectScanner，消除克隆）

        优先级：.copier-answers.yml > .plc.json > PM_SESSION_*.md
        取最新修改时间作为增量判据。
        """
        from auto_pm.core.project_scanner import ProjectScanner

        return ProjectScanner.get_project_mtime(project_path)

    @staticmethod
    def _find_change_file(change_dir: str, change_number: str) -> str | None:
        """在变更管理目录中查找变更单文件

        变更单文件位于 ``CHG-{domain}/`` 子目录下，结构为:
        ``01_变更单/CHG-{domain}/CHG-{domain}-{YYYY}-{XXX}.md``
        """
        if not os.path.isdir(change_dir):
            return None
        try:
            for entry in os.listdir(change_dir):
                entry_path = os.path.join(change_dir, entry)
                if not os.path.isdir(entry_path):
                    continue
                # 进入 CHG-{domain}/ 子目录查找变更单文件
                for sub_entry in os.listdir(entry_path):
                    if sub_entry.startswith(change_number) and sub_entry.endswith(".md"):
                        return os.path.join(entry_path, sub_entry)
        except OSError:
            pass
        return None
