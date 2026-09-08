"""ReportService 单元测试

测试内容：
- get_project_overview() 返回正确统计
- get_change_overview() 返回正确统计
- 空数据情况
- 多项目多变更统计

使用真实 Service + 临时工作空间（DB 缓存模式）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.core.project_service import ProjectService
from auto_pm.core.report_service import ReportService
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.repository import ChangeRequestRepository
from auto_pm.models import ChangeSummary, ProjectRecord

# ── fixtures ─────────────────────────────────────────────


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    """临时 DB（已建表）"""
    d = DatabaseManager(str(tmp_path))
    d.init_schema()
    return d


@pytest.fixture
def project_service(tmp_path: Path, db: DatabaseManager) -> ProjectService:
    """带 DB 的 ProjectService"""
    return ProjectService(str(tmp_path), db=db)


@pytest.fixture
def change_service(tmp_path: Path, db: DatabaseManager) -> ChangeService:
    """带 DB 的 ChangeService"""
    return ChangeService(str(tmp_path), db=db)


@pytest.fixture
def report_service(project_service: ProjectService, change_service: ChangeService) -> ReportService:
    """ReportService（注入真实 Service）"""
    return ReportService(project_service, change_service)


def _make_project_record(
    project_id: str,
    name: str = "",
    stack: str = "plc",
    phase: str = "developing",
    business_line: str = "",
) -> ProjectRecord:
    """构造测试用 ProjectRecord"""
    return ProjectRecord(
        project_id=project_id,
        name=name or project_id,
        path=f"/tmp/{project_id}",
        stack=stack,
        version="V1.0.0",
        description="",
        source="copier",
        phase=phase,
        business_line=business_line,
        extra={},
        file_mtime=1000.0,
        last_scanned="2026-01-01",
    )


def _make_change_summary(
    change_number: str,
    project_id: str = "SW-2026-001",
    domain: str = "PLC",
    status: str = "draft",
) -> ChangeSummary:
    """构造测试用 ChangeSummary"""
    return ChangeSummary(
        change_number=change_number,
        project_id=project_id,
        project_name=project_id,
        domain=domain,
        business_nature="REQ",
        impact_scope=["LOCAL"],
        status=status,
        applicant="张三",
        apply_date="2026-01-01",
        title="测试变更",
    )


# ── get_project_overview 测试 ────────────────────────────


class TestGetProjectOverview:
    """get_project_overview() 测试"""

    def test_empty_data(self, report_service: ReportService) -> None:
        """空数据情况：所有计数为 0"""
        result = report_service.get_project_overview()
        assert result["total"] == 0
        assert result["by_stack"] == {"plc": 0, "python": 0, "unknown": 0}
        assert result["by_phase"] == {
            "developing": 0,
            "commissioning": 0,
            "production": 0,
            "archived": 0,
        }
        assert result["by_business_line"] == {
            "SW": 0, "DJ": 0, "ZD": 0, "XT": 0, "WX": 0,
        }

    def test_single_project(
        self, report_service: ReportService, project_service: ProjectService
    ) -> None:
        """单项目统计"""
        assert project_service._repo is not None
        project_service._repo.upsert(
            _make_project_record(
                "SW-2026-001", "项目A", stack="python", phase="developing", business_line="SW"
            )
        )
        result = report_service.get_project_overview()
        assert result["total"] == 1
        assert result["by_stack"]["python"] == 1
        assert result["by_stack"]["plc"] == 0
        assert result["by_phase"]["developing"] == 1
        assert result["by_business_line"]["SW"] == 1

    def test_multi_projects(
        self, report_service: ReportService, project_service: ProjectService
    ) -> None:
        """多项目多维度统计"""
        records = [
            _make_project_record("SW-2026-001", "项目1", "python", "developing", "SW"),
            _make_project_record("SW-2026-002", "项目2", "plc", "developing", "SW"),
            _make_project_record("DJ-2026-001", "项目3", "plc", "production", "DJ"),
            _make_project_record("ZD-2026-001", "项目4", "plc", "commissioning", "ZD"),
            _make_project_record("XT-2026-001", "项目5", "unknown", "archived", "XT"),
            _make_project_record("WX-2026-001", "项目6", "python", "production", "WX"),
        ]
        assert project_service._repo is not None
        for r in records:
            project_service._repo.upsert(r)

        result = report_service.get_project_overview()
        assert result["total"] == 6

        # 按技术栈
        assert result["by_stack"]["python"] == 2
        assert result["by_stack"]["plc"] == 3
        assert result["by_stack"]["unknown"] == 1

        # 按阶段
        assert result["by_phase"]["developing"] == 2
        assert result["by_phase"]["commissioning"] == 1
        assert result["by_phase"]["production"] == 2
        assert result["by_phase"]["archived"] == 1

        # 按业务线
        assert result["by_business_line"]["SW"] == 2
        assert result["by_business_line"]["DJ"] == 1
        assert result["by_business_line"]["ZD"] == 1
        assert result["by_business_line"]["XT"] == 1
        assert result["by_business_line"]["WX"] == 1

    def test_empty_phase_and_bl(
        self, report_service: ReportService, project_service: ProjectService
    ) -> None:
        """未设置 phase/business_line 时计入空 key"""
        assert project_service._repo is not None
        project_service._repo.upsert(
            _make_project_record("SW-2026-001", "项目A", stack="plc", phase="", business_line="")
        )
        result = report_service.get_project_overview()
        assert result["total"] == 1
        assert result["by_phase"][""] == 1
        assert result["by_business_line"][""] == 1
        # 已知 key 仍为 0
        assert result["by_phase"]["developing"] == 0
        assert result["by_business_line"]["SW"] == 0

    def test_return_structure_keys(
        self, report_service: ReportService
    ) -> None:
        """返回结构包含所有必需 key"""
        result = report_service.get_project_overview()
        assert set(result.keys()) == {
            "total", "by_stack", "by_phase", "by_business_line"
        }
        # by_stack 固定 key
        assert set(result["by_stack"].keys()) == {"plc", "python", "unknown"}
        # by_phase 固定 key
        assert set(result["by_phase"].keys()) == {
            "developing", "commissioning", "production", "archived"
        }
        # by_business_line 固定 key
        assert set(result["by_business_line"].keys()) == {"SW", "DJ", "ZD", "XT", "WX"}


# ── get_change_overview 测试 ─────────────────────────────


class TestGetChangeOverview:
    """get_change_overview() 测试"""

    def test_empty_data(self, report_service: ReportService) -> None:
        """空数据情况：total 为 0，分布为空 dict"""
        result = report_service.get_change_overview()
        assert result["total"] == 0
        assert result["by_status"] == {}
        assert result["by_domain"] == {}

    def test_single_change(
        self,
        report_service: ReportService,
        project_service: ProjectService,
        db: DatabaseManager,
    ) -> None:
        """单变更统计"""
        # 变更单外键约束：先插入项目记录
        assert project_service._repo is not None
        project_service._repo.upsert(_make_project_record("SW-2026-001"))
        repo = ChangeRequestRepository(db)
        repo.upsert(_make_change_summary("CHG-PLC-2026-001", status="draft", domain="PLC"))
        result = report_service.get_change_overview()
        assert result["total"] == 1
        assert result["by_status"]["draft"] == 1
        assert result["by_domain"]["PLC"] == 1

    def test_multi_changes(
        self,
        report_service: ReportService,
        project_service: ProjectService,
        db: DatabaseManager,
    ) -> None:
        """多变更多维度统计"""
        # 变更单外键约束：先插入项目记录
        assert project_service._repo is not None
        project_service._repo.upsert(_make_project_record("SW-2026-001"))
        repo = ChangeRequestRepository(db)
        changes = [
            _make_change_summary("CHG-PLC-2026-001", status="draft", domain="PLC"),
            _make_change_summary("CHG-PLC-2026-002", status="draft", domain="PLC"),
            _make_change_summary("CHG-PLC-2026-003", status="implementing", domain="PLC"),
            _make_change_summary("CHG-ELEC-2026-001", status="completed", domain="ELEC"),
            _make_change_summary("CHG-DOCU-2026-001", status="submitted", domain="DOCU"),
            _make_change_summary("CHG-MECH-2026-001", status="implementing", domain="MECH"),
        ]
        for c in changes:
            repo.upsert(c)

        result = report_service.get_change_overview()
        assert result["total"] == 6

        # 按状态
        assert result["by_status"]["draft"] == 2
        assert result["by_status"]["implementing"] == 2
        assert result["by_status"]["completed"] == 1
        assert result["by_status"]["submitted"] == 1

        # 按领域
        assert result["by_domain"]["PLC"] == 3
        assert result["by_domain"]["ELEC"] == 1
        assert result["by_domain"]["DOCU"] == 1
        assert result["by_domain"]["MECH"] == 1

    def test_return_structure_keys(self, report_service: ReportService) -> None:
        """返回结构包含所有必需 key"""
        result = report_service.get_change_overview()
        assert set(result.keys()) == {"total", "by_status", "by_domain"}


# ── 集成测试 ─────────────────────────────────────────────


class TestReportServiceIntegration:
    """ReportService 与真实 Service 集成测试"""

    def test_project_and_change_together(
        self,
        report_service: ReportService,
        project_service: ProjectService,
        db: DatabaseManager,
    ) -> None:
        """同时统计项目与变更"""
        # 预置项目
        assert project_service._repo is not None
        project_service._repo.upsert(
            _make_project_record("SW-2026-001", "项目A", "python", "developing", "SW")
        )
        project_service._repo.upsert(
            _make_project_record("DJ-2026-001", "项目B", "plc", "production", "DJ")
        )
        # 预置变更
        change_repo = ChangeRequestRepository(db)
        change_repo.upsert(_make_change_summary("CHG-PLC-2026-001", status="draft"))
        change_repo.upsert(_make_change_summary("CHG-PLC-2026-002", status="completed"))

        proj = report_service.get_project_overview()
        chg = report_service.get_change_overview()

        assert proj["total"] == 2
        assert chg["total"] == 2
        assert proj["by_stack"]["python"] == 1
        assert proj["by_stack"]["plc"] == 1
        assert chg["by_status"]["draft"] == 1
        assert chg["by_status"]["completed"] == 1

    def test_raises_without_db(self, tmp_path: Path) -> None:
        """ProjectService 未注入 DB 时 get_project_overview 抛 RuntimeError"""
        ps = ProjectService(str(tmp_path))
        cs = ChangeService(str(tmp_path))
        svc = ReportService(ps, cs)
        with pytest.raises(RuntimeError, match="未注入 DatabaseManager"):
            svc.get_project_overview()


# ── get_spec_report 测试（V2.2 Week3：基于 spec_registry.json） ───


_SAMPLE_SPECS: list[dict[str, Any]] = [
    {
        "spec_id": "LSP-905",
        "title": "SCL编程规范",
        "number": "905",
        "canonical_path": "0100_PLC自动化/00_通用规范/PLC编程/905_SCL编程规范_LSP.md",
        "version": "V1.0.3",
        "type_prefix": "LSP",
        "domain": "plc",
        "lifecycle": "stable",
        "sub_domain": "PLC编程",
        "tags": [],
        "replaces": [],
        "replaced_by": [],
    },
    {
        "spec_id": "LSP-904",
        "title": "SCL注释规范",
        "number": "904",
        "canonical_path": "0100_PLC自动化/00_通用规范/PLC编程/904_SCL注释规范_LSP.md",
        "version": "V1.2.0",
        "type_prefix": "LSP",
        "domain": "plc",
        "lifecycle": "stable",
        "sub_domain": "PLC编程",
        "tags": [],
        "replaces": [],
        "replaced_by": [],
    },
    {
        "spec_id": "CODE-210",
        "title": "Python编程规范",
        "number": "210",
        "canonical_path": "01_Project自动化项目管理/00_通用规范/Python开发/210_Python编程规范_DEV.md",
        "version": "V1.1.0",
        "type_prefix": "CODE",
        "domain": "python",
        "lifecycle": "stable",
        "sub_domain": "Python开发",
        "tags": [],
        "replaces": [],
        "replaced_by": [],
    },
    {
        "spec_id": "CODE-211",
        "title": "Python代码审查规范",
        "number": "211",
        "canonical_path": "01_Project自动化项目管理/00_通用规范/Python开发/211_Python代码审查规范_DEV.md",
        "version": "V1.0.0",
        "type_prefix": "CODE",
        "domain": "python",
        "lifecycle": "stable",
        "sub_domain": "Python开发",
        "tags": [],
        "replaces": [],
        "replaced_by": [],
    },
]


def _create_spec_registry(workspace: Path, specs: list[dict[str, Any]] | None = None) -> Path:
    """在工作空间下创建 spec_registry.json

    Args:
        workspace: 工作空间根目录
        specs: 规范列表（None 使用 _SAMPLE_SPECS）

    Returns:
        注册表文件路径
    """
    import json

    registry_dir = workspace / "00_Obsidian_Base全局规范文件仓库"
    registry_dir.mkdir(parents=True, exist_ok=True)
    registry_path = registry_dir / "spec_registry.json"

    specs_to_write = specs if specs is not None else _SAMPLE_SPECS
    data = {
        "version": "1.0.0",
        "last_updated": "2026-06-30",
        "workspace_root": str(workspace),
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
        "specs": {s["spec_id"]: {k: v for k, v in s.items() if k != "spec_id"} for s in specs_to_write},
    }
    registry_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return registry_path


def _create_spec_file_at(workspace: Path, canonical_path: str, content: str = "") -> Path:
    """在 workspace 下按 canonical_path 创建规范文件"""
    file_path = workspace / canonical_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content or "# 规范\n\n测试内容\n", encoding="utf-8")
    return file_path


class TestGetSpecReport:
    """get_spec_report() 测试（V2.2 Week3：基于 spec_registry.json）"""

    def test_raises_without_workspace_root(
        self, tmp_path: Path, db: DatabaseManager
    ) -> None:
        """未注入 workspace_root 时抛 RuntimeError"""
        ps = ProjectService(str(tmp_path), db=db)
        cs = ChangeService(str(tmp_path), db=db)
        svc = ReportService(ps, cs, db=db)
        with pytest.raises(RuntimeError, match="未注入 workspace_root"):
            svc.get_spec_report()

    def test_registry_not_found_returns_empty(self, tmp_path: Path, db: DatabaseManager) -> None:
        """注册表不存在时返回空报告"""
        ps = ProjectService(str(tmp_path), db=db)
        cs = ChangeService(str(tmp_path), db=db)
        svc = ReportService(ps, cs, workspace_root=str(tmp_path), db=db)

        result = svc.get_spec_report()
        assert result["total"] == 0
        assert result["found"] == 0
        assert result["missing"] == 0
        assert result["missing_codes"] == []
        assert result["by_stack"] == {}

    def test_all_missing(self, tmp_path: Path, db: DatabaseManager) -> None:
        """注册表存在但规范文件都不存在"""
        _create_spec_registry(tmp_path)  # 创建注册表，但不创建规范文件
        ps = ProjectService(str(tmp_path), db=db)
        cs = ChangeService(str(tmp_path), db=db)
        svc = ReportService(ps, cs, workspace_root=str(tmp_path), db=db)

        result = svc.get_spec_report()
        # _SAMPLE_SPECS 共 4 个：2 PLC + 2 Python
        assert result["total"] == 4
        assert result["found"] == 0
        assert result["missing"] == 4
        assert len(result["missing_codes"]) == 4
        # spec_id 格式为 LSP-XXX / CODE-XXX
        assert "LSP-905" in result["missing_codes"]
        assert "CODE-210" in result["missing_codes"]

        # by_stack 按 domain 分组
        assert set(result["by_stack"].keys()) == {"plc", "python"}
        assert result["by_stack"]["plc"]["total"] == 2
        assert result["by_stack"]["plc"]["found"] == 0
        assert len(result["by_stack"]["plc"]["missing"]) == 2
        assert result["by_stack"]["python"]["total"] == 2
        assert result["by_stack"]["python"]["found"] == 0
        assert len(result["by_stack"]["python"]["missing"]) == 2

    def test_all_found(self, tmp_path: Path, db: DatabaseManager) -> None:
        """所有规范文件都存在"""
        _create_spec_registry(tmp_path)
        # 按 canonical_path 创建所有规范文件
        for spec in _SAMPLE_SPECS:
            _create_spec_file_at(tmp_path, spec["canonical_path"])

        ps = ProjectService(str(tmp_path), db=db)
        cs = ChangeService(str(tmp_path), db=db)
        svc = ReportService(ps, cs, workspace_root=str(tmp_path), db=db)

        result = svc.get_spec_report()
        assert result["total"] == 4
        assert result["found"] == 4
        assert result["missing"] == 0
        assert result["missing_codes"] == []
        assert result["by_stack"]["plc"]["found"] == 2
        assert result["by_stack"]["plc"]["missing"] == []
        assert result["by_stack"]["python"]["found"] == 2
        assert result["by_stack"]["python"]["missing"] == []

    def test_partial_found(self, tmp_path: Path, db: DatabaseManager) -> None:
        """部分规范文件存在"""
        _create_spec_registry(tmp_path)
        # 仅创建 LSP-905 和 CODE-210
        _create_spec_file_at(tmp_path, "0100_PLC自动化/00_通用规范/PLC编程/905_SCL编程规范_LSP.md")
        _create_spec_file_at(tmp_path, "01_Project自动化项目管理/00_通用规范/Python开发/210_Python编程规范_DEV.md")

        ps = ProjectService(str(tmp_path), db=db)
        cs = ChangeService(str(tmp_path), db=db)
        svc = ReportService(ps, cs, workspace_root=str(tmp_path), db=db)

        result = svc.get_spec_report()
        assert result["total"] == 4
        assert result["found"] == 2
        assert result["missing"] == 2
        # 缺失的是 LSP-904 和 CODE-211
        assert "LSP-904" in result["missing_codes"]
        assert "CODE-211" in result["missing_codes"]
        assert "LSP-905" not in result["missing_codes"]
        assert "CODE-210" not in result["missing_codes"]

    def test_return_structure_keys(self, tmp_path: Path, db: DatabaseManager) -> None:
        """返回结构包含所有必需 key"""
        _create_spec_registry(tmp_path)
        ps = ProjectService(str(tmp_path), db=db)
        cs = ChangeService(str(tmp_path), db=db)
        svc = ReportService(ps, cs, workspace_root=str(tmp_path), db=db)

        result = svc.get_spec_report()
        assert set(result.keys()) == {
            "total", "found", "missing", "by_stack", "missing_codes"
        }
        for stack_data in result["by_stack"].values():
            assert set(stack_data.keys()) == {"total", "found", "missing"}


# ── get_scan_report 测试（M4-Iter2） ─────────────────────


class TestGetScanReport:
    """get_scan_report() 测试"""

    def test_raises_without_db(self, tmp_path: Path) -> None:
        """未注入 DB 时抛 RuntimeError"""
        ps = ProjectService(str(tmp_path))
        cs = ChangeService(str(tmp_path))
        svc = ReportService(ps, cs, workspace_root=str(tmp_path))
        with pytest.raises(RuntimeError, match="未注入 DatabaseManager"):
            svc.get_scan_report()

    def test_empty_scan_log(self, tmp_path: Path, db: DatabaseManager) -> None:
        """无扫描日志时返回默认值"""
        ps = ProjectService(str(tmp_path), db=db)
        cs = ChangeService(str(tmp_path), db=db)
        svc = ReportService(ps, cs, workspace_root=str(tmp_path), db=db)

        result = svc.get_scan_report()
        assert result["latest"] is None
        assert result["last_sync_time"] == "—"
        assert result["is_cache_available"] is True

    def test_with_scan_log(
        self, tmp_path: Path, db: DatabaseManager
    ) -> None:
        """有扫描日志时返回最近一条"""
        from auto_pm.db.repository import ScanLogRepository

        repo = ScanLogRepository(db)
        repo.insert(
            scan_type="full",
            projects_found=5,
            changes_found=3,
            duration_ms=1200,
            status="success",
            message="ok",
        )

        ps = ProjectService(str(tmp_path), db=db)
        cs = ChangeService(str(tmp_path), db=db)
        svc = ReportService(ps, cs, workspace_root=str(tmp_path), db=db)

        result = svc.get_scan_report()
        assert result["latest"] is not None
        assert result["latest"]["scan_type"] == "full"
        assert result["latest"]["projects_found"] == 5
        assert result["latest"]["changes_found"] == 3
        assert result["latest"]["status"] == "success"
        # last_sync_time 应为 "YYYY-MM-DD HH:MM" 格式
        assert result["last_sync_time"] != "—"
        assert len(result["last_sync_time"]) == 16
        assert result["is_cache_available"] is True

    def test_return_structure_keys(
        self, tmp_path: Path, db: DatabaseManager
    ) -> None:
        """返回结构包含所有必需 key"""
        ps = ProjectService(str(tmp_path), db=db)
        cs = ChangeService(str(tmp_path), db=db)
        svc = ReportService(ps, cs, workspace_root=str(tmp_path), db=db)

        result = svc.get_scan_report()
        assert set(result.keys()) == {"latest", "last_sync_time", "is_cache_available"}


# ── get_report 统一入口测试（M4-Iter2） ──────────────────


class TestGetReportDispatch:
    """get_report() 统一入口测试"""

    def test_dispatch_project(
        self, report_service: ReportService
    ) -> None:
        """project 类型分发到 get_project_overview"""
        result = report_service.get_report("project")
        assert "total" in result
        assert "by_stack" in result

    def test_dispatch_change(
        self, report_service: ReportService
    ) -> None:
        """change 类型分发到 get_change_overview"""
        result = report_service.get_report("change")
        assert "total" in result
        assert "by_status" in result

    def test_dispatch_spec(
        self, tmp_path: Path, db: DatabaseManager
    ) -> None:
        """spec 类型分发到 get_spec_report"""
        ps = ProjectService(str(tmp_path), db=db)
        cs = ChangeService(str(tmp_path), db=db)
        svc = ReportService(ps, cs, workspace_root=str(tmp_path), db=db)
        result = svc.get_report("spec")
        assert "total" in result
        assert "found" in result

    def test_dispatch_scan(
        self, tmp_path: Path, db: DatabaseManager
    ) -> None:
        """scan 类型分发到 get_scan_report"""
        ps = ProjectService(str(tmp_path), db=db)
        cs = ChangeService(str(tmp_path), db=db)
        svc = ReportService(ps, cs, workspace_root=str(tmp_path), db=db)
        result = svc.get_report("scan")
        assert "latest" in result

    def test_unknown_type_raises(
        self, report_service: ReportService
    ) -> None:
        """未知类型抛 ValueError"""
        with pytest.raises(ValueError, match="未知报告类型"):
            report_service.get_report("unknown_type")

    def test_list_report_types(self) -> None:
        """list_report_types 返回所有支持的类型"""
        assert hasattr(ReportService, "list_report_types")  # 方法存在性检查
        # 直接调用实例方法
        ps = ProjectService.__new__(ProjectService)  # 不调用 __init__
        cs = ChangeService.__new__(ChangeService)
        svc = ReportService(ps, cs)
        result = svc.list_report_types()
        assert "project" in result
        assert "change" in result
        assert "spec" in result
        assert "scan" in result
        assert len(result) == 4
