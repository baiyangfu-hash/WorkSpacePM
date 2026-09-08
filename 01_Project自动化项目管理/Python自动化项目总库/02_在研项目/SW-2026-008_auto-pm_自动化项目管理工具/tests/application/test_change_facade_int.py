"""ChangeFacade 集成测试（M3 新增）

验证 ChangeFacade → ChangeService → Repository → DB 端到端链路。
不验证 CHG-*.md 文件生成（涉及 ChgGenerator + 路径解析，复杂度高），
仅预置 DB 记录验证 list/get/timeline/validation_summary 的聚合逻辑。

参考 M2 的 test_workbench_facade_int.py 模式。
"""

from __future__ import annotations

import shutil

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.repository import ChangeRequestRepository, ProjectRepository
from auto_pm.models import ApprovalRecord
from auto_pm.models.change import ChangeSummary, ImpactAnalysis
from auto_pm.models.project import ProjectRecord

from auto_pm.application.change_facade import ChangeFacade


@pytest.fixture
def temp_workspace(tmp_path: Path) -> None:  # type: ignore[misc, name-defined]
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    proj_dir = ws_dir / "02_在研项目" / "SW-2026-001_Test"
    proj_dir.mkdir(parents=True)
    (proj_dir / ".copier-answers.yml").write_text(
        "project_id: SW-2026-001\nproject_name: Test Project",
        encoding="utf-8",
    )
    yield str(ws_dir)
    shutil.rmtree(ws_dir, ignore_errors=True)


@pytest.fixture
def change_facade_with_db(temp_workspace) -> None:  # type: ignore[misc, no-untyped-def]
    """构造含 DB 缓存的 ChangeFacade，预置 1 个项目 + 1 个变更单 + 1 条影响分析 + 2 条审批历史"""
    db = DatabaseManager(temp_workspace)
    db.init_schema()

    # 预置项目记录（change_requests 表的 project_id 外键约束）
    project_repo = ProjectRepository(db)
    project_repo.upsert(
        ProjectRecord(
            project_id="SW-2026-001",
            name="Test Project",
            path="02_在研项目/SW-2026-001_Test",
            stack="plc",
            version="1.0.0",
            phase="production",
            business_line="DJ",
        )
    )

    # 预置变更单
    change_repo = ChangeRequestRepository(db)
    change_repo.upsert(
        ChangeSummary(
            change_number="CHG-2026-001",
            project_id="SW-2026-001",
            project_name="Test Project",
            domain="ELEC",
            business_nature="DEF",
            impact_scope=["LOCAL"],  # ImpactScope 枚举值
            status="approved",
            applicant="user1",
            apply_date="2026-07-07",
            title="测试变更单",
            urgency="normal",
        )
    )

    # 预置影响分析
    # 注意：impact_analysis 表有外键约束 FOREIGN KEY (project_id, change_number)
    # REFERENCES change_requests(project_id, change_number)，必须传 project_id
    # 否则默认值 '' 不满足外键约束，触发 IntegrityError: FOREIGN KEY constraint failed
    change_repo.save_impact_analysis(
        ImpactAnalysis(
            project_id="SW-2026-001",
            change_number="CHG-2026-001",
            risk_level="high",
            mitigation="缓解措施 A",
            constraint_impacts={"成本": "中"},
            domain_impacts={"ELEC": {"affected": "yes", "content": "电气图纸修改"}},
            propagation_chain="A→B→C",
            related_changes=["CHG-2026-000"],
            updated_at="2026-07-07",
        )
    )

    # 预置审批历史（2 条流转：draft→submitted→approved）
    # 注意：save_approval_record 签名为 (change_number, to_status, approver, comment, from_status)
    # 不接收 transition_date（由 DB 自动填充 datetime.now()），但为了测试断言可控，
    # 我们直接用 ApprovalHistoryRepository.insert 写入完整记录
    from auto_pm.db.repository import ApprovalHistoryRepository

    approval_repo = ApprovalHistoryRepository(db)
    # 注意：approval_history 表外键约束 FOREIGN KEY (project_id, change_number)
    # REFERENCES change_requests(project_id, change_number)，必须传 project_id
    approval_repo.insert(
        ApprovalRecord(
            project_id="SW-2026-001",
            change_number="CHG-2026-001",
            from_status="draft",
            to_status="submitted",
            approver="user1",
            comment="提交审批",
            transition_date="2026-07-07T10:00:00",
        )
    )
    approval_repo.insert(
        ApprovalRecord(
            project_id="SW-2026-001",
            change_number="CHG-2026-001",
            from_status="submitted",
            to_status="approved",
            approver="user2",
            comment="同意",
            transition_date="2026-07-08T11:00:00",
        )
    )

    # 构造 ChangeService + ChangeFacade
    change_service = ChangeService(workspace_root=temp_workspace, db=db)

    # get_change_request 走文件系统扫描（self._locator.find_change_file），
    # 不从 DB 缓存读取。集成测试不构造 CHG-*.md 文件（涉及 ChgGenerator 复杂度高），
    # 故 mock 该方法返回基于 DB 记录构造的 ChangeRequest，其他方法（list_approval_history /
    # get_impact_analysis）保持真实走 DB Repository。
    from auto_pm.change.constants import ChangeRequest

    mock_cr = ChangeRequest(
        change_number="CHG-2026-001",
        project_id="SW-2026-001",
        project_name="Test Project",
        domain="ELEC",
        business_nature="DEF",
        impact_scope=["LOCAL"],
        status="approved",
        applicant="user1",
        apply_date="2026-07-07",
        title="测试变更单",
        urgency="normal",
    )
    change_service.get_change_request = lambda cn, project_id=None: mock_cr if cn == "CHG-2026-001" else None  # type: ignore[assignment, method-assign]

    facade = ChangeFacade(change_service=change_service)
    yield facade
    # 清理（tmp_path 自动清理，但显式关闭 DB 连接避免 Windows 文件锁）
    import gc
    gc.collect()


def test_change_facade_int_list_changes(change_facade_with_db) -> None:  # type: ignore[no-untyped-def]
    """集成测试：list_change_requests 从 DB 读取变更单列表"""
    result = change_facade_with_db.list_change_requests()
    assert result.success is True
    assert len(result.payload) == 1
    summary = result.payload[0]
    assert summary.change_number == "CHG-2026-001"
    assert summary.project_id == "SW-2026-001"
    assert summary.domain == "ELEC"
    assert summary.status == "approved"
    assert summary.impact_scope == ["LOCAL"]


def test_change_facade_int_get_detail(change_facade_with_db) -> None:  # type: ignore[no-untyped-def]
    """集成测试：get_change_detail 从 DB 读取变更单详情"""
    result = change_facade_with_db.get_change_detail("CHG-2026-001")
    assert result.success is True
    assert result.payload.change_number == "CHG-2026-001"
    assert result.payload.status == "approved"
    assert result.payload.applicant == "user1"


def test_change_facade_int_get_timeline(change_facade_with_db) -> None:  # type: ignore[no-untyped-def]
    """集成测试：get_change_timeline 从 DB 读取审批历史"""
    result = change_facade_with_db.get_change_timeline("CHG-2026-001")
    assert result.success is True
    assert len(result.payload) == 2
    assert result.payload[0].from_status == "draft"
    assert result.payload[0].to_status == "submitted"
    assert result.payload[1].from_status == "submitted"
    assert result.payload[1].to_status == "approved"
    assert result.payload[1].approver == "user2"
    assert result.payload[1].comment == "同意"
    assert result.payload[1].transition_date == "2026-07-08T11:00:00"


def test_change_facade_int_get_validation_summary(change_facade_with_db) -> None:  # type: ignore[no-untyped-def]
    """集成测试：get_change_validation_summary 聚合 ImpactAnalysis + ApprovalHistory"""
    result = change_facade_with_db.get_change_validation_summary("CHG-2026-001")
    assert result.success is True
    summary = result.payload
    assert summary.change_number == "CHG-2026-001"
    assert summary.current_status == "approved"
    assert summary.risk_level == "high"
    assert summary.mitigation == "缓解措施 A"
    assert summary.propagation_chain == "A→B→C"
    assert summary.approval_count == 2
    assert summary.last_approval_date == "2026-07-08T11:00:00"
    assert summary.domain_impacts == {"ELEC": {"affected": "yes", "content": "电气图纸修改"}}
    assert summary.related_changes == ["CHG-2026-000"]


def test_change_facade_int_full_flow(change_facade_with_db) -> None:  # type: ignore[no-untyped-def]
    """集成测试：端到端流程 list → get_detail → get_timeline → get_validation_summary"""
    # 1. list
    list_result = change_facade_with_db.list_change_requests()
    assert list_result.success and len(list_result.payload) == 1
    change_number = list_result.payload[0].change_number

    # 2. get_detail
    detail_result = change_facade_with_db.get_change_detail(change_number)
    assert detail_result.success
    assert detail_result.payload.status == "approved"

    # 3. get_timeline
    timeline_result = change_facade_with_db.get_change_timeline(change_number)
    assert timeline_result.success
    assert len(timeline_result.payload) == 2

    # 4. get_validation_summary
    summary_result = change_facade_with_db.get_change_validation_summary(change_number)
    assert summary_result.success
    assert summary_result.payload.approval_count == 2
    assert summary_result.payload.risk_level == "high"


def test_change_facade_int_not_found(change_facade_with_db) -> None:  # type: ignore[no-untyped-def]
    """集成测试：change_id 不存在时返回 success=False"""
    result = change_facade_with_db.get_change_detail("NOT-EXIST")
    assert result.success is False
    assert "not found" in result.message

    summary_result = change_facade_with_db.get_change_validation_summary("NOT-EXIST")
    assert summary_result.success is False
    assert "not found" in summary_result.message
