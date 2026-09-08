"""DashboardService 单元测试

验证 Week 1 首页驾驶舱摘要数据：
- 项目总数
- 阶段分布
- 未关闭变更数
- PLC 检查失败项目数
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.core.dashboard_service import DashboardService
from auto_pm.core.project_service import ProjectService
from auto_pm.db.connection import DatabaseManager
from auto_pm.db.repository import ChangeRequestRepository
from auto_pm.models import ChangeSummary, ProjectRecord


class _FakeCheckResult:
    def __init__(
        self,
        fail_count: int = 0,
        not_applicable: bool = False,
        not_applicable_reason: str = "",
    ) -> None:
        self.fail_count = fail_count
        self.not_applicable = not_applicable
        self.not_applicable_reason = not_applicable_reason


class _FakePlcService:
    def __init__(
        self,
        fail_counts: dict[str, int] | None = None,
        not_applicable_paths: set[str] | None = None,
    ) -> None:
        self._fail_counts = fail_counts or {}
        self._not_applicable_paths = not_applicable_paths or set()

    def check(self, project_path: str) -> _FakeCheckResult:
        if project_path in self._not_applicable_paths:
            return _FakeCheckResult(
                not_applicable=True,
                not_applicable_reason="Python 项目（无 .plc.json + 有 pyproject.toml），PLC 检查不适用",
            )
        return _FakeCheckResult(self._fail_counts.get(project_path, 0))


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    d = DatabaseManager(str(tmp_path))
    d.init_schema()
    return d


@pytest.fixture
def project_service(tmp_path: Path, db: DatabaseManager) -> ProjectService:
    return ProjectService(str(tmp_path), db=db)


@pytest.fixture
def change_service(tmp_path: Path, db: DatabaseManager) -> ChangeService:
    return ChangeService(str(tmp_path), db=db)


def _make_project_record(
    project_id: str,
    name: str = "",
    stack: str = "plc",
    phase: str = "developing",
    business_line: str = "",
    file_mtime: float = 1000.0,
) -> ProjectRecord:
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
        file_mtime=file_mtime,
        last_scanned="2026-01-01",
    )


def _make_change_summary(
    change_number: str,
    project_id: str = "SW-2026-001",
    status: str = "draft",
    apply_date: str = "2026-01-01",
) -> ChangeSummary:
    return ChangeSummary(
        change_number=change_number,
        project_id=project_id,
        project_name=project_id,
        domain="PLC",
        business_nature="REQ",
        impact_scope=["LOCAL"],
        status=status,
        applicant="张三",
        apply_date=apply_date,
        title="测试变更",
    )


class TestDashboardService:
    @pytest.mark.parametrize(
        ("timezone_value", "expected_timestamp"),
        [
            (
                "2026-06-27T00:00:00+00:00",
                datetime(2026, 6, 27, tzinfo=timezone.utc).timestamp(),
            ),
            (
                "2026-06-26T17:00:00-07:00",
                datetime(2026, 6, 27, tzinfo=timezone.utc).timestamp(),
            ),
        ],
        ids=["UTC", "America-Phoenix"],
    )
    def test_parse_date_to_timestamp_is_timezone_deterministic(
        self, timezone_value: str, expected_timestamp: float
    ) -> None:
        """带时区日期在 UTC 与 America/Phoenix 表示下保持同一排序瞬间。"""
        assert DashboardService._parse_date_to_timestamp(timezone_value) == expected_timestamp

    def test_get_summary_empty_data(
        self, project_service: ProjectService, change_service: ChangeService
    ) -> None:
        service = DashboardService(project_service, change_service)

        result = service.get_summary()

        assert result.total_projects == 0
        assert result.phase_counts == {
            "developing": 0,
            "commissioning": 0,
            "production": 0,
            "archived": 0,
        }
        assert result.open_change_count == 0
        assert result.failed_check_project_count == 0
        assert result.recent_activities == []
        assert result.risk_hints == ["当前未发现高优先级风险"]

    def test_get_summary_with_projects_changes_and_failed_checks(
        self,
        project_service: ProjectService,
        change_service: ChangeService,
        db: DatabaseManager,
    ) -> None:
        projects = [
            _make_project_record("DJ-2026-001", "PLC单机A", "plc", "developing", "DJ", file_mtime=1751000000.0),
            _make_project_record("DJ-2026-002", "PLC单机B", "plc", "commissioning", "DJ", file_mtime=1750900000.0),
            _make_project_record("SW-2026-003", "软件A", "python", "developing", "SW", file_mtime=1782535000.0),
            _make_project_record("SW-2026-004", "软件B", "python", "archived", "SW", file_mtime=1750800000.0),
        ]
        assert project_service._repo is not None
        for record in projects:
            project_service._repo.upsert(record)

        change_repo = ChangeRequestRepository(db)
        change_repo.upsert(
            _make_change_summary(
                "CHG-PLC-2026-001",
                project_id="DJ-2026-001",
                status="draft",
                apply_date="2026-06-25",
            )
        )
        change_repo.upsert(
            _make_change_summary(
                "CHG-PLC-2026-002",
                project_id="DJ-2026-001",
                status="implementing",
                apply_date="2026-06-27",
            )
        )
        change_repo.upsert(
            _make_change_summary(
                "CHG-PLC-2026-003",
                project_id="DJ-2026-002",
                status="closed",
                apply_date="2026-06-20",
            )
        )

        fake_plc_service = _FakePlcService(
            {
                "/tmp/DJ-2026-001": 2,
                "/tmp/DJ-2026-002": 0,
            }
        )
        service = DashboardService(project_service, change_service, plc_service=fake_plc_service)

        result = service.get_summary()

        assert result.total_projects == 4
        assert result.phase_counts["developing"] == 2
        assert result.phase_counts["commissioning"] == 1
        assert result.phase_counts["archived"] == 1
        assert result.open_change_count == 2
        assert result.failed_check_project_count == 1
        assert result.failed_check_project_ids == ["DJ-2026-001"]
        assert len(result.recent_activities) == 4
        # CHG-106: recent_activities 格式从 list[str] 改为 list[dict[str, Any]]
        # 每项结构: {"type": "default"|"success", "title": "...", "desc": "...", "time": "..."}
        assert result.recent_activities[0]["title"].startswith("项目更新 SW-2026-003")
        assert any(
            "CHG-PLC-2026-002" in item["title"]
            for item in result.recent_activities
        )
        assert result.risk_hints[0] == "存在 2 条未关闭变更，建议优先清理实施中和待验收项"
        assert result.risk_hints[1] == "PLC 检查失败项目: DJ-2026-001"

    # ── V0.4.1 Step 3: not_applicable 口径测试 ──────────────

    def test_not_applicable_project_not_counted_as_failed(
        self,
        project_service: ProjectService,
        change_service: ChangeService,
    ) -> None:
        """V0.4.1 Step 3: not_applicable 项目不计入 failed_check_project_count

        场景：stack='plc' 但实际是 Python 项目（PlcService.check 返回 not_applicable=True）
        应该：not_applicable_project_count=1, failed_check_project_count=0
        """
        # SW-2026-003 stack='plc' 但实际是 Python 项目（误标或扫描器误判）
        records = [
            _make_project_record(
                "SW-2026-003", "Python工具", "plc", "developing", "SW"
            ),
        ]
        assert project_service._repo is not None
        for r in records:
            project_service._repo.upsert(r)

        fake_plc_service = _FakePlcService(
            not_applicable_paths={"/tmp/SW-2026-003"}
        )
        service = DashboardService(
            project_service, change_service, plc_service=fake_plc_service
        )

        result = service.get_summary()

        # not_applicable 应被正确计数
        assert result.not_applicable_project_count == 1
        assert result.not_applicable_project_ids == ["SW-2026-003"]
        # failed_check_project_count 应为 0（不适用 ≠ 失败）
        assert result.failed_check_project_count == 0
        assert result.failed_check_project_ids == []

    def test_not_applicable_mixed_with_failed(
        self,
        project_service: ProjectService,
        change_service: ChangeService,
    ) -> None:
        """V0.4.1 Step 3: not_applicable 与 failed 混合场景

        场景：1 个 PLC 检查失败 + 1 个 Python 项目（not_applicable）
        应该：failed_check_project_count=1, not_applicable_project_count=1
        """
        records = [
            _make_project_record(
                "DJ-2026-001", "PLC单机A", "plc", "developing", "DJ"
            ),
            _make_project_record(
                "SW-2026-003", "Python工具", "plc", "developing", "SW"
            ),
        ]
        assert project_service._repo is not None
        for r in records:
            project_service._repo.upsert(r)

        fake_plc_service = _FakePlcService(
            fail_counts={"/tmp/DJ-2026-001": 2},
            not_applicable_paths={"/tmp/SW-2026-003"},
        )
        service = DashboardService(
            project_service, change_service, plc_service=fake_plc_service
        )

        result = service.get_summary()

        # failed + not_applicable 分离
        assert result.failed_check_project_count == 1
        assert result.failed_check_project_ids == ["DJ-2026-001"]
        assert result.not_applicable_project_count == 1
        assert result.not_applicable_project_ids == ["SW-2026-003"]

    def test_risk_hints_not_applicable_only(
        self,
        project_service: ProjectService,
        change_service: ChangeService,
    ) -> None:
        """V0.4.1 Step 3: 仅有 not_applicable 没 failed 时给出信息提示"""
        records = [
            _make_project_record(
                "SW-2026-003", "Python工具", "plc", "developing", "SW"
            ),
        ]
        assert project_service._repo is not None
        for r in records:
            project_service._repo.upsert(r)

        fake_plc_service = _FakePlcService(
            not_applicable_paths={"/tmp/SW-2026-003"}
        )
        service = DashboardService(
            project_service, change_service, plc_service=fake_plc_service
        )

        result = service.get_summary()

        # risk_hints 应包含 not_applicable 信息提示
        not_applicable_hint = next(
            (h for h in result.risk_hints if "PLC 检查不适用项目" in h), None
        )
        assert not_applicable_hint is not None
        assert "1" in not_applicable_hint
        assert "Python" in not_applicable_hint

    def test_risk_hints_failed_and_not_applicable_both_shown(
        self,
        project_service: ProjectService,
        change_service: ChangeService,
    ) -> None:
        """V0.4.1 收口批次阶段 4: failed 与 not_applicable 同时存在时两者都展示

        m2 修复: not_applicable 是口径说明（Python 项目正常情况），与 failed（真失败）
        相互独立。始终展示 not_applicable 提示，让用户清楚看到 Python 项目口径。
        """
        records = [
            _make_project_record(
                "DJ-2026-001", "PLC单机A", "plc", "developing", "DJ"
            ),
            _make_project_record(
                "SW-2026-003", "Python工具", "plc", "developing", "SW"
            ),
        ]
        assert project_service._repo is not None
        for r in records:
            project_service._repo.upsert(r)

        fake_plc_service = _FakePlcService(
            fail_counts={"/tmp/DJ-2026-001": 2},
            not_applicable_paths={"/tmp/SW-2026-003"},
        )
        service = DashboardService(
            project_service, change_service, plc_service=fake_plc_service
        )

        result = service.get_summary()

        # failed 与 not_applicable 应同时展示（口径独立）
        not_applicable_hints = [
            h for h in result.risk_hints if "PLC 检查不适用项目" in h
        ]
        assert len(not_applicable_hints) == 1
        assert "1" in not_applicable_hints[0]
        failed_hints = [
            h for h in result.risk_hints if "PLC 检查失败项目" in h
        ]
        assert len(failed_hints) == 1

    # ── P3 根源修复：stack="python" 正常项目 not_applicable 统计 ──────────────

    def test_not_applicable_python_stack_project(
        self,
        project_service: ProjectService,
        change_service: ChangeService,
    ) -> None:
        """P3 根源修复：stack='python' 的正常项目应被 PlcChecker 判定为 not_applicable

        移除 DashboardService 第104行 stack 过滤后，所有项目都经过
        PlcChecker.check() 统一判定。stack='python' 的项目由 PlcChecker
        基于文件特征（无 .plc.json + 有 pyproject.toml）返回 not_applicable=True。
        """
        records = [
            _make_project_record(
                "SW-2026-003", "Python工具", "python", "developing", "SW"
            ),
        ]
        assert project_service._repo is not None
        for r in records:
            project_service._repo.upsert(r)

        fake_plc_service = _FakePlcService(
            not_applicable_paths={"/tmp/SW-2026-003"}
        )
        service = DashboardService(
            project_service, change_service, plc_service=fake_plc_service
        )

        result = service.get_summary()

        assert result.not_applicable_project_count == 1
        assert result.not_applicable_project_ids == ["SW-2026-003"]
        assert result.failed_check_project_count == 0

    def test_not_applicable_mixed_stacks(
        self,
        project_service: ProjectService,
        change_service: ChangeService,
    ) -> None:
        """P3 根源修复：混合 stack 场景验证

        PLC 项目(failed) + Python 项目(not_applicable) + PLC 项目(normal) + Python 项目(normal)
        """
        records = [
            _make_project_record("DJ-2026-001", "PLC单机A", "plc", "developing", "DJ"),
            _make_project_record("SW-2026-003", "Python工具A", "python", "developing", "SW"),
            _make_project_record("DJ-2026-002", "PLC单机B", "plc", "production", "DJ"),
            _make_project_record("SW-2026-004", "Python工具B", "python", "archived", "SW"),
        ]
        assert project_service._repo is not None
        for r in records:
            project_service._repo.upsert(r)

        fake_plc_service = _FakePlcService(
            fail_counts={"/tmp/DJ-2026-001": 2},
            not_applicable_paths={"/tmp/SW-2026-003"},
        )
        service = DashboardService(
            project_service, change_service, plc_service=fake_plc_service
        )

        result = service.get_summary()

        assert result.total_projects == 4
        assert result.failed_check_project_count == 1
        assert result.failed_check_project_ids == ["DJ-2026-001"]
        assert result.not_applicable_project_count == 1
        assert result.not_applicable_project_ids == ["SW-2026-003"]
