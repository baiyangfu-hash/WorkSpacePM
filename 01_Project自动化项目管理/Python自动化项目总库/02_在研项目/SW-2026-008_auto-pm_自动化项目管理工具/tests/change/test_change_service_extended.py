"""ChangeService 扩展方法单元测试

覆盖 list_all_changes / update_change_request / delete_change_request

说明：
    - 领域筛选使用 CHG-040 规范定义的领域代码（ELEC/MECH/PLC/HMI/SCPT/DOCU/SAFE），
      而非中文标签。测试中使用 DOCU（工程文档）和 PLC（PLC程序）。
    - 状态筛选使用 STATUS_FLOW 中定义的英文状态码。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.repository import ChangeRequestRepository, ProjectRepository
from auto_pm.models import ChangeSummary, ProjectRecord

# ── 共享测试数据 ──────────────────────────────────────

_SAMPLE_CHG_CONTENT = """# 变更单

## 3. 变更基本信息

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | CHG-DOCU-2026-001 |
| 项目名称 | TEST-2026-001 测试项目 |
| 项目编号 | TEST-2026-001 |

### 3.1 技术领域（必选）
| 领域 | 选择 | 说明 |
|------|------|------|
| ☑ **DOCU** 工程文档 | **选中** | 设计说明书 |

### 3.2 业务性质（必选）
| 性质 | 选择 | 典型场景 |
|------|------|----------|
| ☑ **DEF** 缺陷修复 | **选中** | Bug修复 |

### 3.3 影响范围（可多选）
| 范围 | 选择 | 审批要求 |
|------|------|----------|
| ☑ **MODULE** 模块级变更 | **选中** | 项目负责人审批 |

### 3.4 申请信息
| 字段 | 内容 |
|------|------|
| 变更申请人 | 张三 |
| 申请日期 | 2026-01-15 |
| 预计实施日期 | 2026-01-20 |
| 紧急程度 | ☑一般 □紧急 □非常紧急 |
| 变更状态 | draft |

## 4. 变更原因

**变更背景**：
测试变更背景描述

**变更必要性**：
测试变更必要性描述

**参考依据**：
测试参考依据

## 8. 变更审批

### 8.1 审批流程（按影响范围分级）

| 审批环节 | 审批人 | 审批意见 | 审批日期 | 签字/电子签章 |
|----------|--------|----------|----------|---------------|
| **初审** | 李四 | 同意 | 2026-01-16 | 李四 |

### 8.2 审批结论
| 结论 | ☑ 通过 □ 有条件通过 □ 驳回 □ 拒绝 |
"""


def _make_summary(
    change_number: str = "CHG-DOCU-2026-001",
    project_id: str = "TEST-2026-001",
    domain: str = "DOCU",
    status: str = "draft",
) -> ChangeSummary:
    """构造测试用 ChangeSummary"""
    return ChangeSummary(
        change_number=change_number,
        project_id=project_id,
        project_name="测试项目",
        domain=domain,
        business_nature="DEF",
        impact_scope=["MODULE"],
        status=status,
        applicant="张三",
        apply_date="2026-01-15",
        title="测试变更",
    )


def _create_chg_file(workspace: str, change_number: str, domain: str, content: str) -> str:
    """在工作空间中创建变更单文件，返回文件路径"""
    project_path = os.path.join(workspace, "TEST-2026-001")
    # 创建项目标志文件，使 ChangeFileLocator._is_project_dir 识别为项目目录
    os.makedirs(project_path, exist_ok=True)
    with open(os.path.join(project_path, "PM_SESSION_TEST-2026-001.md"), "w", encoding="utf-8") as f:
        f.write("# PM_SESSION\n")
    chg_dir = os.path.join(
        project_path, "04_监控", "01_变更管理", "01_变更单", f"CHG-{domain}"
    )
    os.makedirs(chg_dir, exist_ok=True)
    file_path = os.path.join(chg_dir, f"{change_number}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return file_path


# ── DB fixtures ───────────────────────────────────────


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    """初始化 DB 并插入项目记录（满足外键约束）"""
    db = DatabaseManager(str(tmp_path))
    db.init_schema()
    ProjectRepository(db).upsert(
        ProjectRecord(
            project_id="TEST-2026-001",
            name="测试项目",
            path=str(tmp_path / "TEST-2026-001"),
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
    return db


@pytest.fixture
def db_with_changes(db: DatabaseManager) -> DatabaseManager:
    """DB 中插入多条变更单记录（不同状态/领域）"""
    repo = ChangeRequestRepository(db)
    records = [
        _make_summary("CHG-DOCU-2026-001", status="draft", domain="DOCU"),
        _make_summary("CHG-DOCU-2026-002", status="approved", domain="DOCU"),
        _make_summary("CHG-PLC-2026-001", status="draft", domain="PLC"),
        _make_summary("CHG-PLC-2026-002", status="implementing", domain="PLC"),
    ]
    for r in records:
        repo.upsert(r)
    return db


@pytest.fixture
def workspace_with_chg(tmp_path: Path) -> str:
    """创建包含变更单文件的工作空间（无 DB）"""
    _create_chg_file(str(tmp_path), "CHG-DOCU-2026-001", "DOCU", _SAMPLE_CHG_CONTENT)
    return str(tmp_path)


@pytest.fixture
def workspace_and_db(tmp_path: Path) -> tuple[str, DatabaseManager, str]:
    """工作空间 + DB，变更单文件和 DB 缓存均已就绪

    Returns:
        (workspace_root, db, chg_file_path)
    """
    chg_file = _create_chg_file(
        str(tmp_path), "CHG-DOCU-2026-001", "DOCU", _SAMPLE_CHG_CONTENT
    )

    db = DatabaseManager(str(tmp_path))
    db.init_schema()
    ProjectRepository(db).upsert(
        ProjectRecord(
            project_id="TEST-2026-001",
            name="测试项目",
            path=str(tmp_path / "TEST-2026-001"),
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
    ChangeRequestRepository(db).upsert(_make_summary(), chg_file, 1000.0)

    return str(tmp_path), db, chg_file


# ════════════════════════════════════════════════════════
#  list_all_changes 测试
# ════════════════════════════════════════════════════════


class TestListAllChanges:
    """list_all_changes 跨项目查询测试"""

    def test_no_filter_returns_all(self, db_with_changes: DatabaseManager) -> None:
        """无筛选 → 返回所有变更单"""
        svc = ChangeService(db_with_changes.workspace_root, db=db_with_changes)
        result = svc.list_all_changes()

        assert len(result) == 4
        # 验证按 change_number 排序
        numbers = [c.change_number for c in result]
        assert numbers == sorted(numbers)
        assert "CHG-DOCU-2026-001" in numbers
        assert "CHG-PLC-2026-002" in numbers

    def test_filter_by_status_draft(self, db_with_changes: DatabaseManager) -> None:
        """status='draft' → 只返回草稿状态"""
        svc = ChangeService(db_with_changes.workspace_root, db=db_with_changes)
        result = svc.list_all_changes(status="draft")

        assert len(result) == 2
        for c in result:
            assert c.status == "draft"
        numbers = {c.change_number for c in result}
        assert numbers == {"CHG-DOCU-2026-001", "CHG-PLC-2026-001"}

    def test_filter_by_domain_docu(self, db_with_changes: DatabaseManager) -> None:
        """domain='DOCU' → 只返回 DOCU 领域（工程文档）"""
        svc = ChangeService(db_with_changes.workspace_root, db=db_with_changes)
        result = svc.list_all_changes(domain="DOCU")

        assert len(result) == 2
        for c in result:
            assert c.domain == "DOCU"
        numbers = {c.change_number for c in result}
        assert numbers == {"CHG-DOCU-2026-001", "CHG-DOCU-2026-002"}

    def test_filter_by_domain_plc(self, db_with_changes: DatabaseManager) -> None:
        """domain='PLC' → 只返回 PLC 领域"""
        svc = ChangeService(db_with_changes.workspace_root, db=db_with_changes)
        result = svc.list_all_changes(domain="PLC")

        assert len(result) == 2
        for c in result:
            assert c.domain == "PLC"

    def test_combined_filter_status_and_domain(
        self, db_with_changes: DatabaseManager
    ) -> None:
        """status='draft' + domain='DOCU' 联合筛选 → 1 条"""
        svc = ChangeService(db_with_changes.workspace_root, db=db_with_changes)
        result = svc.list_all_changes(status="draft", domain="DOCU")

        assert len(result) == 1
        assert result[0].change_number == "CHG-DOCU-2026-001"
        assert result[0].status == "draft"
        assert result[0].domain == "DOCU"

    def test_filter_no_match(self, db_with_changes: DatabaseManager) -> None:
        """筛选无匹配 → 空列表"""
        svc = ChangeService(db_with_changes.workspace_root, db=db_with_changes)
        result = svc.list_all_changes(status="closed")
        assert result == []

    def test_fallback_file_scan_without_db(self, workspace_with_chg: str) -> None:
        """无 DB 时回退到文件系统扫描"""
        svc = ChangeService(workspace_with_chg)  # 不传 db
        result = svc.list_all_changes()

        assert len(result) == 1
        assert result[0].change_number == "CHG-DOCU-2026-001"

    def test_fallback_file_scan_with_status_filter(
        self, workspace_with_chg: str
    ) -> None:
        """无 DB 时文件扫描 + 状态筛选"""
        svc = ChangeService(workspace_with_chg)
        result = svc.list_all_changes(status="draft")
        assert len(result) == 1
        assert result[0].status == "draft"


# ════════════════════════════════════════════════════════
#  update_change_request 测试
# ════════════════════════════════════════════════════════


class TestUpdateChangeRequest:
    """update_change_request 修改变更单测试"""

    def test_update_background(self, workspace_with_chg: str) -> None:
        """修改背景字段"""
        svc = ChangeService(workspace_with_chg)
        updated = svc.update_change_request(
            "CHG-DOCU-2026-001", background="全新的变更背景内容"
        )

        assert updated is not None
        assert updated.background == "全新的变更背景内容"
        # 原必要性应保持不变
        assert updated.necessity == "测试变更必要性描述"

    def test_update_necessity(self, workspace_with_chg: str) -> None:
        """修改必要性字段"""
        svc = ChangeService(workspace_with_chg)
        updated = svc.update_change_request(
            "CHG-DOCU-2026-001", necessity="紧急的变更必要性"
        )

        assert updated is not None
        assert updated.necessity == "紧急的变更必要性"
        # 原背景应保持不变
        assert updated.background == "测试变更背景描述"

    def test_update_references(self, workspace_with_chg: str) -> None:
        """修改参考依据字段"""
        svc = ChangeService(workspace_with_chg)
        updated = svc.update_change_request(
            "CHG-DOCU-2026-001", references="新的参考依据文档"
        )

        assert updated is not None
        assert updated.references == "新的参考依据文档"

    def test_update_planned_date(self, workspace_with_chg: str) -> None:
        """修改预计实施日期"""
        svc = ChangeService(workspace_with_chg)
        updated = svc.update_change_request(
            "CHG-DOCU-2026-001", planned_date="2026-03-01"
        )

        assert updated is not None
        assert updated.planned_date == "2026-03-01"

    def test_update_urgency(self, workspace_with_chg: str) -> None:
        """修改紧急程度"""
        svc = ChangeService(workspace_with_chg)
        updated = svc.update_change_request(
            "CHG-DOCU-2026-001", urgency="urgent"
        )

        assert updated is not None
        assert updated.urgency == "urgent"

    def test_update_multiple_fields(self, workspace_with_chg: str) -> None:
        """同时修改多个字段"""
        svc = ChangeService(workspace_with_chg)
        updated = svc.update_change_request(
            "CHG-DOCU-2026-001",
            background="多字段背景",
            necessity="多字段必要性",
            planned_date="2026-04-01",
        )

        assert updated is not None
        assert updated.background == "多字段背景"
        assert updated.necessity == "多字段必要性"
        assert updated.planned_date == "2026-04-01"

    def test_update_protected_change_number_raises(
        self, workspace_with_chg: str
    ) -> None:
        """不允许修改 change_number → Python 参数绑定拒绝（TypeError）"""
        svc = ChangeService(workspace_with_chg)
        # change_number 是位置参数，通过 kwargs 传入会触发 TypeError
        with pytest.raises(TypeError, match="multiple values"):
            svc.update_change_request(
                "CHG-DOCU-2026-001", change_number="CHG-DOCU-2026-999"  # type: ignore[misc]
            )

    def test_update_protected_project_id_raises(
        self, workspace_with_chg: str
    ) -> None:
        """不允许修改 project_id → 抛 ValueError"""
        svc = ChangeService(workspace_with_chg)
        with pytest.raises(ValueError, match="不允许修改"):
            svc.update_change_request(
                "CHG-DOCU-2026-001", project_id="OTHER-2026-001"
            )

    def test_update_protected_status_raises(self, workspace_with_chg: str) -> None:
        """不允许修改 status → 抛 ValueError（提示用 transition_status）"""
        svc = ChangeService(workspace_with_chg)
        with pytest.raises(ValueError, match="transition_status"):
            svc.update_change_request(
                "CHG-DOCU-2026-001", status="approved"
            )

    def test_update_nonexistent_returns_none(self, workspace_with_chg: str) -> None:
        """修改不存在的变更单 → 返回 None"""
        svc = ChangeService(workspace_with_chg)
        result = svc.update_change_request(
            "CHG-DOCU-9999-999", background="不存在"
        )
        assert result is None

    def test_update_invalid_urgency_raises(self, workspace_with_chg: str) -> None:
        """urgency 值不合法 → 抛 SpecViolationError"""
        from auto_pm.change.constants import SpecViolationError

        svc = ChangeService(workspace_with_chg)
        with pytest.raises(SpecViolationError, match="紧急程度"):
            svc.update_change_request(
                "CHG-DOCU-2026-001", urgency="invalid_level"
            )

    def test_update_preserves_file_structure(self, workspace_with_chg: str) -> None:
        """修改后文件章节结构完整保留"""
        svc = ChangeService(workspace_with_chg)
        svc.update_change_request(
            "CHG-DOCU-2026-001", background="结构保留测试"
        )

        # 重新解析验证完整性
        cr = svc.get_change_request("CHG-DOCU-2026-001")
        assert cr is not None
        assert cr.change_number == "CHG-DOCU-2026-001"
        assert cr.project_id == "TEST-2026-001"
        assert cr.domain == "DOCU"
        assert cr.background == "结构保留测试"
        # 必要性未被破坏
        assert cr.necessity == "测试变更必要性描述"

    def test_update_syncs_db_cache(self, workspace_and_db: tuple[str, DatabaseManager, str]) -> None:
        """修改后 DB 缓存同步更新"""
        workspace, db, _ = workspace_and_db
        svc = ChangeService(workspace, db=db)

        updated = svc.update_change_request(
            "CHG-DOCU-2026-001", background="DB同步测试背景"
        )
        assert updated is not None

        # 从 DB 查询验证缓存已更新
        repo = ChangeRequestRepository(db)
        db_summaries = repo.list_all()
        assert len(db_summaries) == 1
        # title 来自 background 摘要
        assert "DB同步测试背景" in db_summaries[0].title


# ════════════════════════════════════════════════════════
#  delete_change_request 测试
# ════════════════════════════════════════════════════════


class TestDeleteChangeRequest:
    """delete_change_request 删除变更单测试"""

    def test_delete_existing(self, workspace_with_chg: str) -> None:
        """删除存在的变更单 → True，文件被删除"""
        svc = ChangeService(workspace_with_chg)
        # 确认文件存在
        cr = svc.get_change_request("CHG-DOCU-2026-001")
        assert cr is not None
        assert os.path.isfile(cr.file_path)

        result = svc.delete_change_request("CHG-DOCU-2026-001")
        assert result is True
        # 文件应已删除
        assert not os.path.isfile(cr.file_path)

    def test_delete_nonexistent_returns_false(self, workspace_with_chg: str) -> None:
        """删除不存在的变更单 → False"""
        svc = ChangeService(workspace_with_chg)
        result = svc.delete_change_request("CHG-DOCU-9999-999")
        assert result is False

    def test_delete_removes_db_cache(self, workspace_and_db: tuple[str, DatabaseManager, str]) -> None:
        """删除后 DB 缓存也清除"""
        workspace, db, chg_file = workspace_and_db
        svc = ChangeService(workspace, db=db)

        # 确认 DB 中有记录
        repo = ChangeRequestRepository(db)
        assert len(repo.list_all()) == 1

        # 执行删除
        result = svc.delete_change_request("CHG-DOCU-2026-001")
        assert result is True

        # DB 缓存应已清除
        assert repo.list_all() == []
        # 文件也应已删除
        assert not os.path.isfile(chg_file)

    def test_delete_only_db_record_when_file_missing(
        self, workspace_and_db: tuple[str, DatabaseManager, str]
    ) -> None:
        """文件已不存在但 DB 有记录 → 仍可删除 DB 缓存"""
        workspace, db, chg_file = workspace_and_db
        # 先手动删除文件
        os.remove(chg_file)

        svc = ChangeService(workspace, db=db)
        repo = ChangeRequestRepository(db)
        assert len(repo.list_all()) == 1

        result = svc.delete_change_request("CHG-DOCU-2026-001")
        assert result is True
        assert repo.list_all() == []

    def test_delete_then_get_returns_none(self, workspace_with_chg: str) -> None:
        """删除后再获取 → None"""
        svc = ChangeService(workspace_with_chg)
        svc.delete_change_request("CHG-DOCU-2026-001")

        cr = svc.get_change_request("CHG-DOCU-2026-001")
        assert cr is None


# ════════════════════════════════════════════════════════
#  跨项目单号过滤测试（TD-A04 修复，CHG-SCPT-2026-105）
# ════════════════════════════════════════════════════════


def _create_chg_file_for_project(
    workspace: str, project_id: str, change_number: str, domain: str, content: str
) -> str:
    """在指定项目目录中创建变更单文件（跨项目测试专用）"""
    project_path = os.path.join(workspace, project_id)
    os.makedirs(project_path, exist_ok=True)
    # 创建项目标志文件，使 ChangeFileLocator._is_project_dir 识别为项目目录
    with open(
        os.path.join(project_path, f"PM_SESSION_{project_id}.md"),
        "w",
        encoding="utf-8",
    ) as f:
        f.write("# PM_SESSION\n")
    chg_dir = os.path.join(
        project_path, "04_监控", "01_变更管理", "01_变更单", f"CHG-{domain}"
    )
    os.makedirs(chg_dir, exist_ok=True)
    file_path = os.path.join(chg_dir, f"{change_number}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return file_path


_SAMPLE_CHG_CONTENT_PROJECT_B = _SAMPLE_CHG_CONTENT.replace(
    "TEST-2026-001", "TEST-2026-002"
)


@pytest.fixture
def workspace_with_cross_project_chg(tmp_path: Path) -> tuple[str, str, str]:
    """创建两个项目各有相同变更单号的工作空间

    Returns:
        (workspace_root, file_path_a, file_path_b)
        两个项目 TEST-2026-001 和 TEST-2026-002 各有 CHG-DOCU-2026-001.md
    """
    file_a = _create_chg_file_for_project(
        str(tmp_path), "TEST-2026-001", "CHG-DOCU-2026-001", "DOCU", _SAMPLE_CHG_CONTENT
    )
    file_b = _create_chg_file_for_project(
        str(tmp_path),
        "TEST-2026-002",
        "CHG-DOCU-2026-001",
        "DOCU",
        _SAMPLE_CHG_CONTENT_PROJECT_B,
    )
    return str(tmp_path), file_a, file_b


class TestCrossProjectFilter:
    """跨项目单号过滤测试（TD-A04 修复验证）"""

    def test_find_with_project_id_a(
        self,
        workspace_with_cross_project_chg: tuple[str, str, str],
    ) -> None:
        """提供 project_id=TEST-2026-001 → 返回项目 A 的文件"""
        workspace, file_a, _ = workspace_with_cross_project_chg
        from auto_pm.change.file_locator import ChangeFileLocator
        from auto_pm.change.parser import ChgParser

        locator = ChangeFileLocator(workspace, ChgParser())
        result = locator.find_change_file(
            "CHG-DOCU-2026-001", project_id="TEST-2026-001"
        )
        assert result == file_a

    def test_find_with_project_id_b(
        self,
        workspace_with_cross_project_chg: tuple[str, str, str],
    ) -> None:
        """提供 project_id=TEST-2026-002 → 返回项目 B 的文件"""
        workspace, _, file_b = workspace_with_cross_project_chg
        from auto_pm.change.file_locator import ChangeFileLocator
        from auto_pm.change.parser import ChgParser

        locator = ChangeFileLocator(workspace, ChgParser())
        result = locator.find_change_file(
            "CHG-DOCU-2026-001", project_id="TEST-2026-002"
        )
        assert result == file_b

    def test_find_without_project_id_backward_compat(
        self,
        workspace_with_cross_project_chg: tuple[str, str, str],
    ) -> None:
        """不提供 project_id → 向后兼容，递归搜索返回第一个匹配"""
        workspace, file_a, _ = workspace_with_cross_project_chg
        from auto_pm.change.file_locator import ChangeFileLocator
        from auto_pm.change.parser import ChgParser

        locator = ChangeFileLocator(workspace, ChgParser())
        result = locator.find_change_file("CHG-DOCU-2026-001")
        # 不带 project_id 时返回第一个匹配（递归遍历顺序决定）
        assert result is not None
        assert result in (file_a, workspace_with_cross_project_chg[2])

    def test_get_change_request_with_project_id_a(
        self,
        workspace_with_cross_project_chg: tuple[str, str, str],
    ) -> None:
        """get_change_request 提供 project_id=TEST-2026-001 → 返回项目 A 的变更单"""
        workspace, _, _ = workspace_with_cross_project_chg
        svc = ChangeService(workspace)
        cr = svc.get_change_request("CHG-DOCU-2026-001", project_id="TEST-2026-001")
        assert cr is not None
        assert cr.project_id == "TEST-2026-001"

    def test_get_change_request_with_project_id_b(
        self,
        workspace_with_cross_project_chg: tuple[str, str, str],
    ) -> None:
        """get_change_request 提供 project_id=TEST-2026-002 → 返回项目 B 的变更单"""
        workspace, _, _ = workspace_with_cross_project_chg
        svc = ChangeService(workspace)
        cr = svc.get_change_request("CHG-DOCU-2026-001", project_id="TEST-2026-002")
        assert cr is not None
        assert cr.project_id == "TEST-2026-002"

    def test_get_change_request_without_project_id_returns_one(
        self,
        workspace_with_cross_project_chg: tuple[str, str, str],
    ) -> None:
        """get_change_request 不提供 project_id → 向后兼容，返回第一个匹配"""
        workspace, _, _ = workspace_with_cross_project_chg
        svc = ChangeService(workspace)
        cr = svc.get_change_request("CHG-DOCU-2026-001")
        assert cr is not None
        assert cr.project_id in ("TEST-2026-001", "TEST-2026-002")

    def test_delete_with_project_id_a(
        self,
        workspace_with_cross_project_chg: tuple[str, str, str],
    ) -> None:
        """delete_change_request 提供 project_id=TEST-2026-001 → 删除项目 A 的文件"""
        workspace, file_a, file_b = workspace_with_cross_project_chg
        svc = ChangeService(workspace)
        result = svc.delete_change_request(
            "CHG-DOCU-2026-001", project_id="TEST-2026-001"
        )
        assert result is True
        assert not os.path.isfile(file_a)
        # 项目 B 的文件应保留
        assert os.path.isfile(file_b)

    def test_find_with_nonexistent_project_id_fallback(
        self,
        workspace_with_cross_project_chg: tuple[str, str, str],
    ) -> None:
        """project_id 不存在 → 回退递归搜索（向后兼容）"""
        workspace, _, _ = workspace_with_cross_project_chg
        from auto_pm.change.file_locator import ChangeFileLocator
        from auto_pm.change.parser import ChgParser

        locator = ChangeFileLocator(workspace, ChgParser())
        result = locator.find_change_file(
            "CHG-DOCU-2026-001", project_id="NONEXISTENT-2026-999"
        )
        # project_id 定位失败时回退递归搜索
        assert result is not None
