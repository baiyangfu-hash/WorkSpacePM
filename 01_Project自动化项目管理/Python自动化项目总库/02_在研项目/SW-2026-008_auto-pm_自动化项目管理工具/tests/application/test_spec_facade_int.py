"""SpecFacade 集成测试（M4 后续待办 B2）

验证 SpecFacade → CheckService/SpecCenterAdapter → SpecRegistry → spec_registry.json 端到端链路。
不验证完整 HealthChecker（涉及文件解析/正则匹配，复杂度高），仅预置 spec_registry.json
+ 1 个真实规范文件 + 1 个 missing 规范文件，验证 overview/list_entries/run_check 的聚合逻辑。

参考 M3 的 test_change_facade_int.py 模式。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.application.spec_facade import SpecFacade
from auto_pm.ui.contracts.dto.spec_dto import (
    SpecCenterEntryDTO,
    SpecCenterOverviewDTO,
    SpecCheckResultDTO,
)
from auto_pm.ui.global_pages.spec_center_dto import SpecCenterAdapter


@pytest.fixture
def spec_facade_real(spec_registry_workspace: Path) -> SpecFacade:
    """构造含真实 Service 的 SpecFacade

    - CheckService(workspace=spec_registry_workspace)
    - SpecCenterAdapter(workspace=spec_registry_workspace)
    - spec_registry.json 含 2 条规范（plc 文件存在 / python 文件 missing）
    """
    from auto_pm.domain.spec.services.check_svc import CheckService

    check_service = CheckService(workspace=spec_registry_workspace)
    center_service = SpecCenterAdapter(workspace=spec_registry_workspace)
    return SpecFacade(
        spec_check_service=check_service,  # type: ignore[arg-type]
        spec_center_service=center_service,
    )


def test_spec_facade_int_get_overview(spec_facade_real: SpecFacade) -> None:
    """集成测试：get_spec_center_overview 从 SpecRegistry 读取规范列表

    spec_registry.json 预置 2 条规范（plc + python），均 lifecycle=active。
    health_summary 应为全 0（get_overview 不触发完整检查）。
    """
    result = spec_facade_real.get_spec_center_overview()
    assert result.success is True
    assert result.payload is not None

    dto: SpecCenterOverviewDTO = result.payload
    assert dto.spec_count == 2
    assert dto.domain_counts == {"plc": 1, "python": 1}
    assert dto.lifecycle_counts == {"active": 2}
    # health_summary 是 dict（Facade 转 HealthSummaryDTO → dict）
    assert dto.health_summary["error_count"] == 0
    assert dto.health_summary["warning_count"] == 0
    assert dto.health_summary["info_count"] == 0
    assert dto.health_summary["exit_code"] == 0


def test_spec_facade_int_list_entries_all(spec_facade_real: SpecFacade) -> None:
    """集成测试：list_spec_center_entries 返回全部规范条目"""
    result = spec_facade_real.list_spec_center_entries(filter_domain=None)
    assert result.success is True
    assert len(result.payload) == 2  # type: ignore[arg-type]

    spec_ids = {e.spec_id for e in result.payload}  # type: ignore[union-attr]
    assert spec_ids == {"LSP-905", "CODE-210"}

    # 每个条目都是 SpecCenterEntryDTO
    for entry in result.payload:  # type: ignore[union-attr]
        assert isinstance(entry, SpecCenterEntryDTO)
        assert entry.lifecycle == "active"


def test_spec_facade_int_list_entries_filter_plc(spec_facade_real: SpecFacade) -> None:
    """集成测试：list_spec_center_entries(filter_domain='plc') 仅返回 plc 域规范"""
    result = spec_facade_real.list_spec_center_entries(filter_domain="plc")
    assert result.success is True
    assert len(result.payload) == 1  # type: ignore[arg-type]

    entry = result.payload[0]  # type: ignore[index]
    assert entry.spec_id == "LSP-905"
    assert entry.domain == "plc"
    assert entry.title == "SCL 编程规范"
    assert entry.number == "905"


def test_spec_facade_int_list_entries_file_exists(spec_facade_real: SpecFacade) -> None:
    """集成测试：list_spec_center_entries 反映规范文件是否真实存在

    LSP-905 文件存在（fixture 创建），CODE-210 文件 missing（fixture 故意不创建）。
    """
    result = spec_facade_real.list_spec_center_entries(filter_domain=None)
    assert result.success is True

    by_id = {e.spec_id: e for e in result.payload}  # type: ignore[union-attr]
    assert by_id["LSP-905"].file_exists is True
    assert by_id["CODE-210"].file_exists is False


def test_spec_facade_int_list_entries_filter_python(spec_facade_real: SpecFacade) -> None:
    """集成测试：list_spec_center_entries(filter_domain='python') 返回 python 域规范"""
    result = spec_facade_real.list_spec_center_entries(filter_domain="python")
    assert result.success is True
    assert len(result.payload) == 1  # type: ignore[arg-type]

    entry = result.payload[0]  # type: ignore[index]
    assert entry.spec_id == "CODE-210"
    assert entry.domain == "python"


def test_spec_facade_int_run_check(spec_facade_real: SpecFacade) -> None:
    """集成测试：run_spec_check 执行真实健康检查并返回 CheckOutput

    CheckService.run() 返回 CheckOutput，Facade 转 SpecCheckResultDTO。
    由于 spec_registry.json 中 CODE-210 文件缺失，可能产生 warning/error（具体取决于 checker 实现），
    本测试仅验证返回结构正确，不固定断言 error_count 数值。
    """
    result = spec_facade_real.run_spec_check()
    assert result.success is True
    assert result.payload is not None

    dto: SpecCheckResultDTO = result.payload
    assert isinstance(dto.error_count, int)
    assert isinstance(dto.warning_count, int)
    assert isinstance(dto.info_count, int)
    assert isinstance(dto.exit_code, int)
    assert isinstance(dto.results, list)
    # exit_code 应为 0（无 error）或 1（有 error）
    assert dto.exit_code in (0, 1)


def test_spec_facade_int_full_flow(spec_facade_real: SpecFacade) -> None:
    """集成测试：端到端流程 overview → list_entries → run_check"""
    # 1. overview
    overview_result = spec_facade_real.get_spec_center_overview()
    assert overview_result.success
    assert overview_result.payload.spec_count == 2  # type: ignore[union-attr]

    # 2. list_entries
    list_result = spec_facade_real.list_spec_center_entries()
    assert list_result.success
    assert len(list_result.payload) == 2  # type: ignore[arg-type]

    # 3. run_check
    check_result = spec_facade_real.run_spec_check()
    assert check_result.success
    assert isinstance(check_result.payload.error_count, int)  # type: ignore[union-attr]


def test_spec_facade_int_no_service() -> None:
    """集成测试：未注入 Service 时返回 success=False"""
    facade = SpecFacade(spec_check_service=None, spec_center_service=None)

    overview = facade.get_spec_center_overview()
    assert overview.success is False
    assert "No spec_center_service" in overview.message

    entries = facade.list_spec_center_entries()
    assert entries.success is False
    assert "No spec_center_service" in entries.message

    check = facade.run_spec_check()
    assert check.success is False
    assert "No spec_check_service" in check.message
