"""PLC-HMI 概念映射：SFB 库函数（数据库仓库（通用 CRUD 操作/ORM 封装））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

数据访问层（Repository）

提供 projects / change_requests / impact_analysis / approval_history / scan_log 五张表的 CRUD 操作。
所有方法使用参数化查询防止 SQL 注入。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from auto_pm.db.connection import DatabaseManager
from auto_pm.models import (
    ApprovalRecord,
    ChangeSummary,
    ImpactAnalysis,
    ProjectRecord,
)


class ProjectRepository:
    """项目索引缓存 CRUD"""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def upsert(self, project: ProjectRecord) -> None:
        """插入或更新项目记录（UPSERT）"""
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO projects
                    (project_id, name, path, stack, version, description,
                     source, phase, business_line, extra, file_mtime, last_scanned,
                     scanner_version)
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    name=excluded.name,
                    path=excluded.path,
                    stack=excluded.stack,
                    version=excluded.version,
                    description=excluded.description,
                    source=excluded.source,
                    phase=excluded.phase,
                    business_line=excluded.business_line,
                    extra=excluded.extra,
                    file_mtime=excluded.file_mtime,
                    last_scanned=excluded.last_scanned,
                    scanner_version=excluded.scanner_version
                """,
                (
                    project.project_id,
                    project.name,
                    project.path,
                    project.stack,
                    project.version,
                    project.description,
                    project.source,
                    project.phase,
                    project.business_line,
                    json.dumps(project.extra, ensure_ascii=False),
                    project.file_mtime,
                    project.last_scanned,
                    project.scanner_version,
                ),
            )
            conn.commit()

    def get_by_id(self, project_id: str) -> ProjectRecord | None:
        """按 project_id 查询项目"""
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            return self._row_to_record(row) if row else None

    def list_all(self) -> list[ProjectRecord]:
        """列出所有项目（按 project_id 排序）"""
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY project_id").fetchall()
            return [self._row_to_record(row) for row in rows]

    def list_by_stack(self, stack: str) -> list[ProjectRecord]:
        """按技术栈筛选项目"""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE stack = ? ORDER BY project_id",
                (stack,),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def list_by_business_line(self, business_line: str) -> list[ProjectRecord]:
        """按业务线筛选项目

        Args:
            business_line: 业务线编码（SW/DJ/ZD/XT/WX）

        Returns:
            匹配业务线的项目列表，按 project_id 排序
        """
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE business_line = ? ORDER BY project_id",
                (business_line,),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def list_by_phase(self, phase: str) -> list[ProjectRecord]:
        """按阶段筛选项目

        Args:
            phase: 项目阶段（developing/commissioning/production/archived）

        Returns:
            匹配阶段的项目列表，按 project_id 排序
        """
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE phase = ? ORDER BY project_id",
                (phase,),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def delete(self, project_id: str) -> bool:
        """删除项目记录

        Returns:
            True 如果删除了记录，False 如果记录不存在
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            conn.commit()
            return int(cursor.rowcount) > 0

    def count(self) -> int:
        """项目总数"""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM projects").fetchone()
            return int(row["cnt"]) if row else 0

    def get_mtime(self, project_id: str) -> float:
        """获取项目的 file_mtime（增量扫描判据）

        Returns:
            file_mtime，如果项目不存在返回 0
        """
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT file_mtime FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            return float(row["file_mtime"]) if row else 0

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ProjectRecord:
        """将数据库行转换为 ProjectRecord"""
        extra: dict[str, Any] = json.loads(row["extra"]) if row["extra"] else {}
        columns = row.keys()
        business_line = row["business_line"] if "business_line" in columns else ""
        scanner_version = row["scanner_version"] if "scanner_version" in columns else ""
        return ProjectRecord(
            project_id=row["project_id"],
            name=row["name"],
            path=row["path"],
            stack=row["stack"],
            version=row["version"],
            description=row["description"],
            source=row["source"],
            phase=row["phase"],
            business_line=business_line,
            extra=extra,
            file_mtime=row["file_mtime"],
            last_scanned=row["last_scanned"],
            scanner_version=scanner_version,
        )


class ChangeRequestRepository:
    """变更单索引缓存 CRUD"""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        # M2-2: 组合影响分析和审批历史 Repository，提供统一入口
        self._impact_repo = ImpactAnalysisRepository(db)
        self._approval_repo = ApprovalHistoryRepository(db)

    def upsert(self, change: ChangeSummary, file_path: str = "", file_mtime: float = 0) -> None:
        """插入或更新变更单记录"""
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO change_requests
                    (project_id, change_number, project_name, domain,
                     business_nature, impact_scope, status, applicant,
                     apply_date, title, file_path, file_mtime)
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, change_number) DO UPDATE SET
                    project_name=excluded.project_name,
                    domain=excluded.domain,
                    business_nature=excluded.business_nature,
                    impact_scope=excluded.impact_scope,
                    status=excluded.status,
                    applicant=excluded.applicant,
                    apply_date=excluded.apply_date,
                    title=excluded.title,
                    file_path=excluded.file_path,
                    file_mtime=excluded.file_mtime
                """,
                (
                    change.project_id,
                    change.change_number,
                    change.project_name,
                    change.domain,
                    change.business_nature,
                    json.dumps(change.impact_scope, ensure_ascii=False),
                    change.status,
                    change.applicant,
                    change.apply_date,
                    change.title,
                    file_path,
                    file_mtime,
                ),
            )
            conn.commit()

    def list_by_project(self, project_id: str) -> list[ChangeSummary]:
        """按项目 ID 查询变更单列表"""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM change_requests WHERE project_id = ? ORDER BY change_number",
                (project_id,),
            ).fetchall()
            return [self._row_to_summary(row) for row in rows]

    def list_all(self) -> list[ChangeSummary]:
        """列出所有变更单"""
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM change_requests ORDER BY change_number").fetchall()
            return [self._row_to_summary(row) for row in rows]

    def count_by_project(self, project_id: str) -> int:
        """统计项目的变更单数"""
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM change_requests WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            return int(row["cnt"]) if row else 0

    def delete(self, change_number: str, project_id: str | None = None) -> bool:
        """删除变更单记录"""
        with self.db.get_connection() as conn:
            if project_id:
                cursor = conn.execute(
                    "DELETE FROM change_requests WHERE project_id = ? AND change_number = ?",
                    (project_id, change_number),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM change_requests WHERE change_number = ?", (change_number,)
                )
            conn.commit()
            return int(cursor.rowcount) > 0

    def delete_by_project(self, project_id: str) -> int:
        """删除项目的所有变更单记录

        Returns:
            删除的记录数
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute("DELETE FROM change_requests WHERE project_id = ?", (project_id,))
            conn.commit()
            return int(cursor.rowcount)

    @staticmethod
    def _row_to_summary(row: sqlite3.Row) -> ChangeSummary:
        """将数据库行转换为 ChangeSummary"""
        impact_scope: list[str] = json.loads(row["impact_scope"]) if row["impact_scope"] else []
        return ChangeSummary(
            change_number=row["change_number"],
            project_id=row["project_id"],
            project_name=row["project_name"],
            domain=row["domain"],
            business_nature=row["business_nature"],
            impact_scope=impact_scope,
            status=row["status"],
            applicant=row["applicant"],
            apply_date=row["apply_date"],
            title=row["title"],
        )

    # ── M2-2: 影响分析与审批历史委托方法（统一入口） ──

    def save_impact_analysis(self, analysis: ImpactAnalysis) -> None:
        """保存变更影响分析（M2-2 T47）

        委托给 ImpactAnalysisRepository.upsert，提供 ChangeRequestRepository 统一入口。

        Args:
            analysis: 影响分析模型，change_number 为主键
        """
        self._impact_repo.upsert(analysis)

    def get_impact_analysis(
        self, change_number: str, project_id: str | None = None
    ) -> ImpactAnalysis | None:
        """查询变更影响分析（M2-2 T48）

        委托给 ImpactAnalysisRepository.get_by_change_number。

        Returns:
            ImpactAnalysis 或 None（不存在时）
        """
        return self._impact_repo.get_by_change_number(change_number, project_id=project_id)

    def save_approval_record(
        self,
        change_number: str,
        to_status: str,
        approver: str,
        comment: str = "",
        from_status: str = "",
        project_id: str = "",
    ) -> int:
        """保存审批流转记录（M2-2 T49）

        委托给 ApprovalHistoryRepository.insert，提供 ChangeRequestRepository 统一入口。
        每次 transition_status 流转都应调用此方法追加一条记录。

        Args:
            change_number: 变更编号
            to_status: 流转后的目标状态
            approver: 审批人/操作人
            comment: 审批意见
            from_status: 流转前状态（可选，由 ChangeService 传入 current_cr.status）
            project_id: 项目编号（B4 新增）

        Returns:
            记录 ID
        """
        record = ApprovalRecord(
            project_id=project_id,
            change_number=change_number,
            from_status=from_status,
            to_status=to_status,
            approver=approver,
            comment=comment,
        )
        return self._approval_repo.insert(record)

    def list_approval_history(
        self, change_number: str, project_id: str | None = None
    ) -> list[ApprovalRecord]:
        """查询审批流转历史（M2-2 T50）

        委托给 ApprovalHistoryRepository.list_by_change，按 id 升序（时间顺序）返回。

        Returns:
            审批记录列表，空列表表示无记录
        """
        return self._approval_repo.list_by_change(change_number, project_id=project_id)


class ImpactAnalysisRepository:
    """变更影响分析持久化 CRUD（M2-1 新增）

    对齐 impact_analysis 表，存储 §6 影响分析的结构化数据。
    供 GUI 传播链视图和影响分析编辑使用。
    """

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def upsert(self, analysis: ImpactAnalysis) -> None:
        """插入或更新影响分析记录（UPSERT）

        Args:
            analysis: 影响分析模型，change_number 为主键
        """
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO impact_analysis
                    (project_id, change_number, risk_level, mitigation, constraint_impacts,
                     domain_impacts, propagation_chain, related_changes, updated_at)
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, change_number) DO UPDATE SET
                    risk_level=excluded.risk_level,
                    mitigation=excluded.mitigation,
                    constraint_impacts=excluded.constraint_impacts,
                    domain_impacts=excluded.domain_impacts,
                    propagation_chain=excluded.propagation_chain,
                    related_changes=excluded.related_changes,
                    updated_at=excluded.updated_at
                """,
                (
                    analysis.project_id,
                    analysis.change_number,
                    analysis.risk_level,
                    analysis.mitigation,
                    json.dumps(analysis.constraint_impacts, ensure_ascii=False),
                    json.dumps(analysis.domain_impacts, ensure_ascii=False),
                    analysis.propagation_chain,
                    json.dumps(analysis.related_changes, ensure_ascii=False),
                    analysis.updated_at or datetime.now().isoformat(),
                ),
            )
            conn.commit()

    def get_by_change_number(
        self, change_number: str, project_id: str | None = None
    ) -> ImpactAnalysis | None:
        """按变更编号查询影响分析

        Returns:
            ImpactAnalysis 或 None（不存在时）
        """
        with self.db.get_connection() as conn:
            if project_id:
                row = conn.execute(
                    "SELECT * FROM impact_analysis WHERE project_id = ? AND change_number = ?",
                    (project_id, change_number),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM impact_analysis WHERE change_number = ?",
                    (change_number,),
                ).fetchone()
            return self._row_to_analysis(row) if row else None

    def delete(self, change_number: str, project_id: str | None = None) -> bool:
        """删除影响分析记录

        Returns:
            True 如果删除了记录，False 如果记录不存在
        """
        with self.db.get_connection() as conn:
            if project_id:
                cursor = conn.execute(
                    "DELETE FROM impact_analysis WHERE project_id = ? AND change_number = ?",
                    (project_id, change_number),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM impact_analysis WHERE change_number = ?",
                    (change_number,),
                )
            conn.commit()
            return int(cursor.rowcount) > 0

    @staticmethod
    def _row_to_analysis(row: sqlite3.Row) -> ImpactAnalysis:
        """将数据库行转换为 ImpactAnalysis"""
        constraint_impacts: dict[str, str] = (
            json.loads(row["constraint_impacts"]) if row["constraint_impacts"] else {}
        )
        domain_impacts: dict[str, dict[str, Any]] = (
            json.loads(row["domain_impacts"]) if row["domain_impacts"] else {}
        )
        related_changes: list[str] = (
            json.loads(row["related_changes"]) if row["related_changes"] else []
        )
        columns = row.keys()
        project_id = row["project_id"] if "project_id" in columns else ""
        return ImpactAnalysis(
            project_id=project_id,
            change_number=row["change_number"],
            risk_level=row["risk_level"],
            mitigation=row["mitigation"],
            constraint_impacts=constraint_impacts,
            domain_impacts=domain_impacts,
            propagation_chain=row["propagation_chain"],
            related_changes=related_changes,
            updated_at=row["updated_at"],
        )


class ApprovalHistoryRepository:
    """审批流转历史持久化 CRUD（M2-1 新增）

    对齐 approval_history 表，每次 transition_status 流转追加一条记录。
    供 GUI 审批时间线使用。
    """

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def insert(self, record: ApprovalRecord) -> int:
        """插入一条审批流转记录

        Args:
            record: 审批记录模型（id 字段忽略，由 DB 自增）

        Returns:
            记录 ID
        """
        transition_date = record.transition_date or datetime.now().isoformat()
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO approval_history
                    (project_id, change_number, from_status, to_status, approver,
                     comment, transition_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.project_id,
                    record.change_number,
                    record.from_status,
                    record.to_status,
                    record.approver,
                    record.comment,
                    transition_date,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def list_by_change(
        self, change_number: str, project_id: str | None = None
    ) -> list[ApprovalRecord]:
        """按变更编号查询审批历史（按 id 升序，即时间顺序）

        Returns:
            审批记录列表，空列表表示无记录
        """
        with self.db.get_connection() as conn:
            if project_id:
                rows = conn.execute(
                    "SELECT * FROM approval_history WHERE project_id = ? AND change_number = ? ORDER BY id ASC",
                    (project_id, change_number),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM approval_history WHERE change_number = ? ORDER BY id ASC",
                    (change_number,),
                ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def delete_by_change(self, change_number: str, project_id: str | None = None) -> int:
        """删除变更单的所有审批历史记录

        Returns:
            删除的记录数
        """
        with self.db.get_connection() as conn:
            if project_id:
                cursor = conn.execute(
                    "DELETE FROM approval_history WHERE project_id = ? AND change_number = ?",
                    (project_id, change_number),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM approval_history WHERE change_number = ?",
                    (change_number,),
                )
            conn.commit()
            return int(cursor.rowcount)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ApprovalRecord:
        """将数据库行转换为 ApprovalRecord"""
        columns = row.keys()
        project_id = row["project_id"] if "project_id" in columns else ""
        return ApprovalRecord(
            id=row["id"],
            project_id=project_id,
            change_number=row["change_number"],
            from_status=row["from_status"],
            to_status=row["to_status"],
            approver=row["approver"],
            comment=row["comment"],
            transition_date=row["transition_date"],
        )


class ScanLogRepository:
    """扫描日志 CRUD"""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def insert(
        self,
        scan_type: str,
        projects_found: int,
        changes_found: int,
        duration_ms: int,
        status: str = "success",
        message: str = "",
    ) -> int:
        """插入扫描日志

        Returns:
            日志 ID
        """
        timestamp = datetime.now().isoformat()
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO scan_log
                    (scan_type, projects_found, changes_found, duration_ms,
                     status, message, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (scan_type, projects_found, changes_found, duration_ms, status, message, timestamp),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_latest(self) -> dict[str, Any] | None:
        """获取最近一次扫描日志"""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM scan_log ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else None
