"""M2-3 T55: ChangeService DB 集成测试

验证 ChangeService 在注入 DatabaseManager 后，CRUD 和状态流转操作会同步持久化到 DB：
- T53: create_change_request 同步写入 change_requests + impact_analysis
- T52: transition_status 同步写入 approval_history
- T54: update_change_request 同步更新 impact_analysis
"""

from __future__ import annotations

import gc
import os
from collections.abc import Generator

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.repository import ChangeRequestRepository


@pytest.fixture
def svc_with_db(workspace_root: str) -> Generator[tuple[ChangeService, DatabaseManager], None, None]:
    """创建带 DB 的 ChangeService

    依赖 conftest.py 的 workspace_root fixture（创建 TEST-2026-001 项目结构）。
    teardown 时显式清理 DB 文件，避免 SQLite WAL 模式文件锁定导致临时目录无法删除。
    """
    db = DatabaseManager(workspace_root)
    db.init_schema()
    svc = ChangeService(workspace_root, db=db)
    yield svc, db
    # teardown: 释放 DB 资源，清理 WAL/SHM 文件（Windows 文件锁定规避）
    try:
        db.drop_all()
    except Exception:
        pass
    db.close()  # CHG-100 T2: 显式关闭连接，避免复用连接持有文件锁
    gc.collect()
    for ext in ("", "-wal", "-shm"):
        f = db.db_path + ext
        if os.path.isfile(f):
            try:
                os.remove(f)
            except (PermissionError, OSError):
                pass


@pytest.fixture
def created_change(
    svc_with_db: tuple[ChangeService, DatabaseManager], project_id: str
) -> Generator[tuple[str, ChangeService, DatabaseManager], None, None]:
    """创建一个测试变更单并返回 (change_number, svc, db)

    测试结束后自动清理变更单文件。
    """
    svc, db = svc_with_db
    cr = svc.create_change_request(
        project_id=project_id,
        domain="PLC",
        business_nature="DEF",
        impact_scope=["LOCAL"],
        applicant="集成测试",
        background="M2-3 集成测试变更背景",
        necessity="M2-3 集成测试变更必要性",
    )
    yield cr.change_number, svc, db
    # 清理变更单文件
    file_path = svc._locator.find_change_file(cr.change_number)
    if file_path and os.path.isfile(file_path):
        os.remove(file_path)


class TestChangeServiceDBIntegration:
    """M2-3 T55: ChangeService DB 持久化集成测试"""

    def test_create_writes_to_db(
        self,
        created_change: tuple[str, ChangeService, DatabaseManager],
    ) -> None:
        """T53: create_change_request 同步写入 change_requests + impact_analysis"""
        change_number, svc, db = created_change

        # 验证 change_requests 表有记录
        repo = ChangeRequestRepository(db)
        changes = repo.list_all()
        assert any(c.change_number == change_number for c in changes), \
            f"change_requests 表中应有 {change_number} 记录"

        # 验证 impact_analysis 表有记录
        analysis = repo.get_impact_analysis(change_number)
        assert analysis is not None, f"impact_analysis 表中应有 {change_number} 记录"
        assert analysis.change_number == change_number
        # 新创建的变更单 §6 影响分析为空（模板初始状态）
        assert analysis.risk_level == ""
        assert analysis.mitigation == ""
        assert analysis.updated_at != ""  # 自动填充时间

    def test_transition_writes_approval_history(
        self,
        created_change: tuple[str, ChangeService, DatabaseManager],
    ) -> None:
        """T52: transition_status 同步写入 approval_history"""
        change_number, svc, db = created_change

        # 流转: draft → submitted
        svc.transition_status(
            change_number=change_number,
            new_status="submitted",
            approver="测试审批人",
            comment="提交审批",
        )

        # 验证 approval_history 表有记录
        repo = ChangeRequestRepository(db)
        history = repo.list_approval_history(change_number)
        assert len(history) == 1, "应有 1 条审批历史记录"
        assert history[0].change_number == change_number
        assert history[0].from_status == "draft"
        assert history[0].to_status == "submitted"
        assert history[0].approver == "测试审批人"
        assert history[0].comment == "提交审批"

    def test_multiple_transitions_append_history(
        self,
        created_change: tuple[str, ChangeService, DatabaseManager],
    ) -> None:
        """T52: 多次流转追加多条审批历史记录"""
        change_number, svc, db = created_change

        # draft → submitted
        svc.transition_status(change_number, "submitted", "张三", "提交")
        # submitted → under_review
        svc.transition_status(change_number, "under_review", "李四", "开始审查")
        # under_review → approved
        svc.transition_status(change_number, "approved", "王五", "审批通过")

        repo = ChangeRequestRepository(db)
        history = repo.list_approval_history(change_number)
        assert len(history) == 3, "应有 3 条审批历史记录"
        # 验证按时间顺序
        assert history[0].to_status == "submitted"
        assert history[1].to_status == "under_review"
        assert history[2].to_status == "approved"
        # 验证 from_status 链
        assert history[0].from_status == "draft"
        assert history[1].from_status == "submitted"
        assert history[2].from_status == "under_review"

    def test_update_updates_impact_analysis(
        self,
        created_change: tuple[str, ChangeService, DatabaseManager],
    ) -> None:
        """T54: update_change_request 同步更新 impact_analysis"""
        change_number, svc, db = created_change

        # 修改变更单字段（background 是可修改字段）
        updated = svc.update_change_request(
            change_number, background="修改后的变更背景描述"
        )
        assert updated is not None

        # 验证 impact_analysis 记录仍存在（update 不应删除）
        repo = ChangeRequestRepository(db)
        analysis = repo.get_impact_analysis(change_number)
        assert analysis is not None, "impact_analysis 记录应仍存在"
        assert analysis.change_number == change_number

    def test_no_db_no_persistence(
        self,
        workspace_root: str,
        project_id: str,
    ) -> None:
        """T55: 未注入 DB 时不持久化（向后兼容，不报错）"""
        svc = ChangeService(workspace_root)  # 不注入 DB
        cr = svc.create_change_request(
            project_id=project_id,
            domain="PLC",
            business_nature="DEF",
            impact_scope=["LOCAL"],
            applicant="无DB测试",
            background="无DB测试背景",
            necessity="无DB测试必要性",
        )

        # 应正常创建文件，不报错
        assert os.path.isfile(cr.file_path)

        # 流转也应正常工作
        result = svc.transition_status(cr.change_number, "submitted", "测试", "提交")
        assert result is not None

        # 清理
        file_path = svc._locator.find_change_file(cr.change_number)
        if file_path and os.path.isfile(file_path):
            os.remove(file_path)

    def test_cross_project_collision_isolation(
        self,
        svc_with_db: tuple[ChangeService, DatabaseManager],
    ) -> None:
        """验证跨项目同单号冲突时的隔离性（B4 核心验证）"""
        svc, db = svc_with_db

        repo = ChangeRequestRepository(db)
        from auto_pm.db.repository import ProjectRepository
        from auto_pm.models import ChangeSummary, ProjectRecord
        # 插入项目记录以满足外键约束
        ProjectRepository(db).upsert(
            ProjectRecord(
                project_id="TEST-2026-001",
                name="测试项目1",
                path="/tmp/TEST-2026-001",
                stack="plc",
                version="V1.0.0",
                description="测试",
                source="copier",
                phase="developing",
                extra={},
                file_mtime=1000.0,
                last_scanned="2026-01-01T00:00:00",
            )
        )
        ProjectRepository(db).upsert(
            ProjectRecord(
                project_id="TEST-2026-002",
                name="另一个测试项目",
                path="/tmp/TEST-2026-002",
                stack="plc",
                version="V1.0.0",
                description="测试",
                source="copier",
                phase="developing",
                extra={},
                file_mtime=1000.0,
                last_scanned="2026-01-01T00:00:00",
            )
        )

        c1 = ChangeSummary(
            change_number="CHG-PLC-2026-999",
            project_id="TEST-2026-001",
            project_name="测试项目1",
            domain="PLC",
            business_nature="REQ",
            impact_scope=["LOCAL"],
            status="draft",
            applicant="张三",
            apply_date="2026-01-01",
            title="测试变更1",
        )
        c2 = ChangeSummary(
            change_number="CHG-PLC-2026-999",
            project_id="TEST-2026-002",
            project_name="测试项目2",
            domain="PLC",
            business_nature="REQ",
            impact_scope=["LOCAL"],
            status="closed",
            applicant="李四",
            apply_date="2026-01-01",
            title="测试变更2",
        )
        repo.upsert(c1)
        repo.upsert(c2)

        # 验证仓库层面的隔离性
        changes_p1 = repo.list_by_project("TEST-2026-001")
        changes_p2 = repo.list_by_project("TEST-2026-002")
        assert len(changes_p1) == 1
        assert len(changes_p2) == 1
        assert changes_p1[0].status == "draft"
        assert changes_p2[0].status == "closed"

        # 验证 get_impact_analysis 隔离性
        from auto_pm.models import ImpactAnalysis
        ia1 = ImpactAnalysis(project_id="TEST-2026-001", change_number="CHG-PLC-2026-999", risk_level="low")
        ia2 = ImpactAnalysis(project_id="TEST-2026-002", change_number="CHG-PLC-2026-999", risk_level="high")
        repo.save_impact_analysis(ia1)
        repo.save_impact_analysis(ia2)

        res_ia1 = repo.get_impact_analysis("CHG-PLC-2026-999", project_id="TEST-2026-001")
        res_ia2 = repo.get_impact_analysis("CHG-PLC-2026-999", project_id="TEST-2026-002")
        assert res_ia1 is not None
        assert res_ia2 is not None
        assert res_ia1.risk_level == "low"
        assert res_ia2.risk_level == "high"

        # 验证 list_approval_history 隔离性
        repo.save_approval_record(
            change_number="CHG-PLC-2026-999",
            to_status="submitted",
            approver="张三",
            project_id="TEST-2026-001"
        )
        repo.save_approval_record(
            change_number="CHG-PLC-2026-999",
            to_status="closed",
            approver="李四",
            project_id="TEST-2026-002"
        )
        h1 = repo.list_approval_history("CHG-PLC-2026-999", project_id="TEST-2026-001")
        h2 = repo.list_approval_history("CHG-PLC-2026-999", project_id="TEST-2026-002")
        assert len(h1) == 1
        assert h1[0].to_status == "submitted"
        assert len(h2) == 1
        assert h2[0].to_status == "closed"

