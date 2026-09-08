"""M2-1 新增 Repository 单元测试

覆盖：
- ImpactAnalysisRepository: UPSERT/查询/删除（T45）
- ApprovalHistoryRepository: 插入/查询/删除（T46）
"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.repository import (
    ApprovalHistoryRepository,
    ChangeRequestRepository,
    ImpactAnalysisRepository,
    ProjectRepository,
)
from auto_pm.models import (
    ApprovalRecord,
    ChangeSummary,
    ImpactAnalysis,
    ProjectRecord,
)


def _seed_change_request(db: DatabaseManager, change_number: str = "CHG-PLC-2026-001") -> None:
    """插入前置 change_requests 记录以满足外键约束"""
    # 先插入引用的项目记录
    ProjectRepository(db).upsert(
        ProjectRecord(
            project_id="SW-2026-001",
            name="测试项目",
            path="/tmp/SW-2026-001",
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
    # 插入变更单记录
    ChangeRequestRepository(db).upsert(
        ChangeSummary(
            change_number=change_number,
            project_id="SW-2026-001",
            project_name="测试项目",
            domain="PLC",
            business_nature="REQ",
            impact_scope=["LOCAL"],
            status="draft",
            applicant="张三",
            apply_date="2026-01-01",
            title="测试变更",
        ),
        file_path="/tmp/chg.md",
        file_mtime=2000.0,
    )


# ── ImpactAnalysisRepository 测试 ─────────────────────


class TestImpactAnalysisRepository:
    """变更影响分析持久化 CRUD 测试（T45）"""

    @pytest.fixture
    def repo(self, tmp_path: Path) -> ImpactAnalysisRepository:
        db = DatabaseManager(str(tmp_path))
        db.init_schema()
        _seed_change_request(db)
        return ImpactAnalysisRepository(db)

    @staticmethod
    def _make_analysis(change_number: str = "CHG-PLC-2026-001", project_id: str = "SW-2026-001") -> ImpactAnalysis:
        return ImpactAnalysis(
            project_id=project_id,
            change_number=change_number,
            risk_level="medium",
            mitigation="增加单元测试覆盖率",
            constraint_impacts={"范围": "中", "进度": "低", "成本": "无"},
            domain_impacts={
                "PLC": {"affected": True, "content": "修改FB_TON", "related_chg": ""},
                "HMI": {"affected": False, "content": "", "related_chg": ""},
            },
            propagation_chain="SCPT -> PLC -> HMI",
            related_changes=["CHG-PLC-2026-002", "CHG-HMI-2026-001"],
            updated_at="2026-06-25T10:00:00",
        )

    def test_upsert_and_get(self, repo: ImpactAnalysisRepository) -> None:
        """UPSERT 后应能查询到记录"""
        analysis = self._make_analysis()
        repo.upsert(analysis)

        result = repo.get_by_change_number("CHG-PLC-2026-001")
        assert result is not None
        assert result.change_number == "CHG-PLC-2026-001"
        assert result.risk_level == "medium"
        assert result.mitigation == "增加单元测试覆盖率"
        assert result.constraint_impacts == {"范围": "中", "进度": "低", "成本": "无"}
        assert result.domain_impacts["PLC"]["affected"] is True
        assert result.domain_impacts["HMI"]["affected"] is False
        assert result.propagation_chain == "SCPT -> PLC -> HMI"
        assert result.related_changes == ["CHG-PLC-2026-002", "CHG-HMI-2026-001"]
        assert result.updated_at == "2026-06-25T10:00:00"

    def test_upsert_overwrite(self, repo: ImpactAnalysisRepository) -> None:
        """重复 UPSERT 应覆盖旧记录"""
        repo.upsert(self._make_analysis())
        # 第二次 upsert 修改 risk_level
        updated = self._make_analysis()
        updated.risk_level = "high"
        updated.mitigation = "需代码评审 + 增加集成测试"
        repo.upsert(updated)

        result = repo.get_by_change_number("CHG-PLC-2026-001")
        assert result is not None
        assert result.risk_level == "high"
        assert result.mitigation == "需代码评审 + 增加集成测试"

    def test_get_not_found(self, repo: ImpactAnalysisRepository) -> None:
        """查询不存在的记录返回 None"""
        assert repo.get_by_change_number("NOT-EXIST") is None

    def test_delete(self, repo: ImpactAnalysisRepository) -> None:
        """删除记录"""
        repo.upsert(self._make_analysis())
        assert repo.delete("CHG-PLC-2026-001") is True
        assert repo.get_by_change_number("CHG-PLC-2026-001") is None
        assert repo.delete("CHG-PLC-2026-001") is False  # 已删除

    def test_empty_fields_persist(self, repo: ImpactAnalysisRepository) -> None:
        """空字段应能正确持久化和读取"""
        analysis = ImpactAnalysis(project_id="SW-2026-001", change_number="CHG-PLC-2026-001")
        repo.upsert(analysis)

        result = repo.get_by_change_number("CHG-PLC-2026-001")
        assert result is not None
        assert result.risk_level == ""
        assert result.mitigation == ""
        assert result.constraint_impacts == {}
        assert result.domain_impacts == {}
        assert result.propagation_chain == ""
        assert result.related_changes == []

    def test_updated_at_auto_filled(self, repo: ImpactAnalysisRepository) -> None:
        """updated_at 为空时应自动填充当前时间"""
        analysis = ImpactAnalysis(project_id="SW-2026-001", change_number="CHG-PLC-2026-001")
        repo.upsert(analysis)

        result = repo.get_by_change_number("CHG-PLC-2026-001")
        assert result is not None
        assert result.updated_at != ""  # 应自动填充


# ── ApprovalHistoryRepository 测试 ────────────────────


class TestApprovalHistoryRepository:
    """审批流转历史持久化 CRUD 测试（T46）"""

    @pytest.fixture
    def repo(self, tmp_path: Path) -> ApprovalHistoryRepository:
        db = DatabaseManager(str(tmp_path))
        db.init_schema()
        _seed_change_request(db)
        return ApprovalHistoryRepository(db)

    @staticmethod
    def _make_record(
        change_number: str = "CHG-PLC-2026-001",
        from_status: str = "draft",
        to_status: str = "submitted",
        project_id: str = "SW-2026-001",
    ) -> ApprovalRecord:
        return ApprovalRecord(
            project_id=project_id,
            change_number=change_number,
            from_status=from_status,
            to_status=to_status,
            approver="张三",
            comment="提交审批",
            transition_date="2026-06-25T10:00:00",
        )

    def test_insert_and_list(self, repo: ApprovalHistoryRepository) -> None:
        """插入后应能按变更单号查询"""
        record = self._make_record()
        rec_id = repo.insert(record)
        assert rec_id > 0

        history = repo.list_by_change("CHG-PLC-2026-001")
        assert len(history) == 1
        assert history[0].id == rec_id
        assert history[0].change_number == "CHG-PLC-2026-001"
        assert history[0].from_status == "draft"
        assert history[0].to_status == "submitted"
        assert history[0].approver == "张三"
        assert history[0].comment == "提交审批"
        assert history[0].transition_date == "2026-06-25T10:00:00"

    def test_list_empty(self, repo: ApprovalHistoryRepository) -> None:
        """查询无记录的变更单返回空列表"""
        assert repo.list_by_change("NOT-EXIST") == []

    def test_list_ordered_by_id(self, repo: ApprovalHistoryRepository) -> None:
        """多条记录应按 id 升序返回（时间顺序）"""
        repo.insert(self._make_record(to_status="submitted"))
        repo.insert(self._make_record(from_status="submitted", to_status="under_review"))
        repo.insert(self._make_record(from_status="under_review", to_status="approved"))

        history = repo.list_by_change("CHG-PLC-2026-001")
        assert len(history) == 3
        # 验证按 id 升序
        assert history[0].to_status == "submitted"
        assert history[1].to_status == "under_review"
        assert history[2].to_status == "approved"
        # 验证 id 递增
        assert history[0].id < history[1].id < history[2].id

    def test_delete_by_change(self, repo: ApprovalHistoryRepository) -> None:
        """按变更单号删除所有审批历史"""
        repo.insert(self._make_record(to_status="submitted"))
        repo.insert(self._make_record(from_status="submitted", to_status="approved"))

        deleted = repo.delete_by_change("CHG-PLC-2026-001")
        assert deleted == 2
        assert repo.list_by_change("CHG-PLC-2026-001") == []

    def test_delete_by_change_empty(self, repo: ApprovalHistoryRepository) -> None:
        """删除无记录的变更单返回 0"""
        assert repo.delete_by_change("NOT-EXIST") == 0

    def test_transition_date_auto_filled(self, repo: ApprovalHistoryRepository) -> None:
        """transition_date 为空时应自动填充"""
        record = ApprovalRecord(
            project_id="SW-2026-001",
            change_number="CHG-PLC-2026-001",
            from_status="draft",
            to_status="submitted",
            approver="李四",
            comment="",
        )
        rec_id = repo.insert(record)
        assert rec_id > 0

        history = repo.list_by_change("CHG-PLC-2026-001")
        assert len(history) == 1
        assert history[0].transition_date != ""  # 应自动填充


# ── ChangeRequestRepository 扩展方法测试（M2-2 T51） ──


class TestChangeRequestRepositoryExtension:
    """ChangeRequestRepository 扩展方法测试（M2-2 T51）

    覆盖 4 个委托方法：save_impact_analysis / get_impact_analysis /
    save_approval_record / list_approval_history
    """

    @pytest.fixture
    def repo(self, tmp_path: Path) -> ChangeRequestRepository:
        db = DatabaseManager(str(tmp_path))
        db.init_schema()
        _seed_change_request(db)
        return ChangeRequestRepository(db)

    def test_save_and_get_impact_analysis(self, repo: ChangeRequestRepository) -> None:
        """save_impact_analysis + get_impact_analysis 往返测试"""
        analysis = ImpactAnalysis(
            project_id="SW-2026-001",
            change_number="CHG-PLC-2026-001",
            risk_level="high",
            mitigation="需代码评审",
            constraint_impacts={"范围": "高"},
            domain_impacts={"PLC": {"affected": True, "content": "修改FB", "related_chg": ""}},
            propagation_chain="SCPT -> PLC",
            related_changes=["CHG-PLC-2026-002"],
        )
        repo.save_impact_analysis(analysis)

        result = repo.get_impact_analysis("CHG-PLC-2026-001")
        assert result is not None
        assert result.risk_level == "high"
        assert result.mitigation == "需代码评审"
        assert result.constraint_impacts == {"范围": "高"}
        assert result.domain_impacts["PLC"]["affected"] is True
        assert result.related_changes == ["CHG-PLC-2026-002"]

    def test_get_impact_analysis_not_found(self, repo: ChangeRequestRepository) -> None:
        """查询不存在的影响分析返回 None"""
        assert repo.get_impact_analysis("NOT-EXIST") is None

    def test_save_impact_analysis_overwrite(self, repo: ChangeRequestRepository) -> None:
        """重复保存影响分析应覆盖"""
        repo.save_impact_analysis(
            ImpactAnalysis(project_id="SW-2026-001", change_number="CHG-PLC-2026-001", risk_level="low")
        )
        repo.save_impact_analysis(
            ImpactAnalysis(project_id="SW-2026-001", change_number="CHG-PLC-2026-001", risk_level="high")
        )

        result = repo.get_impact_analysis("CHG-PLC-2026-001")
        assert result is not None
        assert result.risk_level == "high"

    def test_save_and_list_approval_record(self, repo: ChangeRequestRepository) -> None:
        """save_approval_record + list_approval_history 测试"""
        rec_id = repo.save_approval_record(
            change_number="CHG-PLC-2026-001",
            to_status="submitted",
            approver="张三",
            comment="提交审批",
            from_status="draft",
            project_id="SW-2026-001",
        )
        assert rec_id > 0

        history = repo.list_approval_history("CHG-PLC-2026-001")
        assert len(history) == 1
        assert history[0].from_status == "draft"
        assert history[0].to_status == "submitted"
        assert history[0].approver == "张三"
        assert history[0].comment == "提交审批"

    def test_list_approval_history_empty(self, repo: ChangeRequestRepository) -> None:
        """查询无记录的审批历史返回空列表"""
        assert repo.list_approval_history("NOT-EXIST") == []

    def test_save_multiple_approval_records_ordered(self, repo: ChangeRequestRepository) -> None:
        """多条审批记录应按 id 升序返回"""
        repo.save_approval_record(
            "CHG-PLC-2026-001", "submitted", "张三", "提交", from_status="draft", project_id="SW-2026-001"
        )
        repo.save_approval_record(
            "CHG-PLC-2026-001", "approved", "李四", "同意", from_status="submitted", project_id="SW-2026-001"
        )
        repo.save_approval_record(
            "CHG-PLC-2026-001", "implementing", "王五", "开始实施", from_status="approved", project_id="SW-2026-001"
        )

        history = repo.list_approval_history("CHG-PLC-2026-001")
        assert len(history) == 3
        assert history[0].to_status == "submitted"
        assert history[1].to_status == "approved"
        assert history[2].to_status == "implementing"
        assert history[0].id < history[1].id < history[2].id

    def test_save_approval_record_without_from_status(self, repo: ChangeRequestRepository) -> None:
        """from_status 可选，不传时为空字符串"""
        rec_id = repo.save_approval_record(
            "CHG-PLC-2026-001", "submitted", "张三", "提交", project_id="SW-2026-001"
        )
        assert rec_id > 0

        history = repo.list_approval_history("CHG-PLC-2026-001")
        assert len(history) == 1
        assert history[0].from_status == ""  # 默认空字符串
