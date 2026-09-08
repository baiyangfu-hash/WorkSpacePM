"""SystemFacade 集成测试（M4 后续待办 B4 + C7 补齐）

验证 SystemFacade → TemplateService → 文件系统 + ProjectService 端到端链路。
验证 SystemFacade → PmSessionViewAggregator → PM_SESSION 文件 端到端链路。

覆盖 3 个 template 相关方法（无 Service bug 的方法）：
- list_templates: TemplateService.list_templates() 扫描 templates_dir
- get_template_path: TemplateService.get_template_path(name) 返回路径
- get_template_detail: TemplateService.get_template_path + 读 copier.yml + 推断 stack + 统计 usage_count

阶段 C bug 修复/误判验证后补齐 3 个方法：
- apply_template: bug #6 修复后调 copy_template（用 mock template_service 验证 Facade → ProjectInfo → Service 链路）
- get_pm_session_view: bug #4 误判验证（_PmSessionViewAggregator 正确封装 generate_view）
- run_pm_session_check: bug #5 误判验证（_PmSessionViewAggregator 正确封装 check）

参考 M3 的 test_change_facade_int.py 模式。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from auto_pm.core.project_service import ProjectService
from auto_pm.core.template_service import TemplateService

from auto_pm.application.system_facade import SystemFacade
from auto_pm.ui.contracts.dto.system_dto import (
    ApplyTemplateResultDTO,
    PmSessionCheckResultDTO,
    PmSessionViewDTO,
    TemplateDetailDTO,
)


@pytest.fixture
def system_facade_real(
    temp_workspace: str,
    templates_dir: Path,
) -> SystemFacade:
    """构造含真实 Service 的 SystemFacade

    - TemplateService(templates_dir=str(templates_dir))
    - ProjectService(workspace_root=temp_workspace) — list_projects 扫描文件系统
    - pm_session_service=None（bug #4/#5 待修复，跳过）

    temp_workspace 预置 2 个项目目录：
    - DJ-2026-001_测试PLC/.plc.json → stack=plc
    - SW-2026-001_测试Python/.copier-answers.yml → stack=python
    """
    template_service = TemplateService(templates_dir=str(templates_dir))
    project_service = ProjectService(workspace_root=temp_workspace, db=None)
    return SystemFacade(
        pm_session_service=None,  # bug #4/#5 待修复
        template_service=template_service,
        project_service=project_service,
    )


def test_system_facade_int_list_templates(system_facade_real: SystemFacade) -> None:
    """集成测试：list_templates 从 templates_dir 扫描模板列表

    templates_dir fixture 预置 2 个模板（plc-standard + python-standard）+ 1 个无 copier.yml 目录。
    TemplateService.list_templates 只返回含 copier.yml 的目录。
    """
    result = system_facade_real.list_templates()
    assert result.success is True
    templates = result.payload
    assert isinstance(templates, list)
    assert len(templates) == 2
    assert "plc-standard" in templates
    assert "python-standard" in templates
    # not-a-template 目录无 copier.yml，应被过滤
    assert "not-a-template" not in templates


def test_system_facade_int_get_template_path(system_facade_real: SystemFacade) -> None:
    """集成测试：get_template_path 返回模板绝对路径"""
    result = system_facade_real.get_template_path("plc-standard")
    assert result.success is True
    path = result.payload
    assert isinstance(path, str)
    assert path.endswith("plc-standard")
    # copier.yml 应存在于返回路径
    assert (Path(path) / "copier.yml").exists()


def test_system_facade_int_get_template_path_not_exist(system_facade_real: SystemFacade) -> None:
    """集成测试：get_template_path 模板不存在时返回 success=False"""
    result = system_facade_real.get_template_path("not-exist-template")
    assert result.success is False
    assert "模板不存在" in result.message or "not" in result.message.lower()


def test_system_facade_int_get_template_detail_plc(system_facade_real: SystemFacade) -> None:
    """集成测试：get_template_detail 读取 plc-standard 模板详情

    - version 从 copier.yml 的 _commit 读取（fixture 设为 v1.2.0）
    - description 从 copier.yml 的 _description 读取
    - stack 推断为 'plc'（template_name 含 'plc'）
    - usage_count 统计 stack=plc 的项目数（temp_workspace 有 1 个 DJ-2026-001）
    """
    result = system_facade_real.get_template_detail("plc-standard")
    assert result.success is True
    assert result.payload is not None

    dto: TemplateDetailDTO = result.payload
    assert dto.name == "plc-standard"
    assert dto.version == "v1.2.0"
    assert dto.description == "PLC 标准模板"
    assert dto.stack == "plc"
    assert dto.usage_count == 1  # DJ-2026-001 是 plc
    assert dto.path.endswith("plc-standard")


def test_system_facade_int_get_template_detail_python(system_facade_real: SystemFacade) -> None:
    """集成测试：get_template_detail 读取 python-standard 模板详情

    - stack 推断为 'python'（template_name 含 'python'）
    - usage_count 统计 stack=python 的项目数（temp_workspace 有 1 个 SW-2026-001）
    """
    result = system_facade_real.get_template_detail("python-standard")
    assert result.success is True
    assert result.payload is not None

    dto: TemplateDetailDTO = result.payload
    assert dto.name == "python-standard"
    assert dto.version == "v0.3.0"
    assert dto.description == "Python 标准模板"
    assert dto.stack == "python"
    assert dto.usage_count == 1  # SW-2026-001 是 python
    assert dto.path.endswith("python-standard")


def test_system_facade_int_get_template_detail_not_exist(system_facade_real: SystemFacade) -> None:
    """集成测试：get_template_detail 模板不存在时返回 success=False"""
    result = system_facade_real.get_template_detail("not-exist")
    assert result.success is False


def test_system_facade_int_full_flow(system_facade_real: SystemFacade) -> None:
    """集成测试：端到端流程 list → get_path → get_detail"""
    # 1. list
    list_result = system_facade_real.list_templates()
    assert list_result.success
    assert len(list_result.payload) == 2  # type: ignore[arg-type]

    # 2. get_path
    template_name = list_result.payload[0]  # type: ignore[index]
    path_result = system_facade_real.get_template_path(template_name)
    assert path_result.success
    assert path_result.payload.endswith(template_name)  # type: ignore[union-attr]

    # 3. get_detail
    detail_result = system_facade_real.get_template_detail(template_name)
    assert detail_result.success
    assert detail_result.payload.name == template_name  # type: ignore[union-attr]
    assert detail_result.payload.stack in ("plc", "python", "pm")  # type: ignore[union-attr]


def test_system_facade_int_no_template_service() -> None:
    """集成测试：未注入 TemplateService 时 template 方法返回 success=False"""
    facade = SystemFacade(
        pm_session_service=None,
        template_service=None,
        project_service=None,
    )

    assert facade.list_templates().success is False
    assert facade.get_template_path("any").success is False
    assert facade.get_template_detail("any").success is False


def test_system_facade_int_get_template_detail_no_project_service(templates_dir: Path) -> None:
    """集成测试：未注入 ProjectService 时 get_template_detail 仍能成功（usage_count=0）

    SystemFacade.get_template_detail 中 project_service 为 None 时跳过 usage_count 统计。
    """
    template_service = TemplateService(templates_dir=str(templates_dir))
    facade = SystemFacade(
        pm_session_service=None,
        template_service=template_service,
        project_service=None,
    )

    result = facade.get_template_detail("plc-standard")
    assert result.success is True
    assert result.payload is not None
    assert result.payload.usage_count == 0  # 无 project_service，不统计
    assert result.payload.stack == "plc"


# ── 阶段 C bug #6 修复后的集成测试（apply_template）──


@pytest.fixture
def system_facade_with_apply_template(  # type: ignore[no-untyped-def]
    temp_workspace: str,
    db_manager,
    project_repo_with_data,
) -> SystemFacade:
    """构造含真实 ProjectService + mock template_service 的 SystemFacade

    bug #6 修复后：apply_template 通过 project_service 查 ProjectInfo 后调 copy_template。
    用 mock template_service 避免实际调用 copier.run_copy（依赖模板完整性）。
    """
    project_service = ProjectService(workspace_root=temp_workspace, db=db_manager)

    # mock template_service：记录 copy_template 调用参数
    captured: dict[str, Any] = {}

    def _copy_template(template_name, dest_path, data, overwrite=False) -> Any:  # type: ignore[no-untyped-def]
        captured["template_name"] = template_name
        captured["dest_path"] = dest_path
        captured["data"] = data
        captured["overwrite"] = overwrite
        return {"applied": True, "dest_path": dest_path, "template": template_name}

    template_service = SimpleNamespace(
        list_templates=lambda: ["plc-standard"],
        get_template_path=lambda name: f"/templates/{name}",
        copy_template=_copy_template,
    )
    facade = SystemFacade(
        pm_session_service=None,
        template_service=template_service,
        project_service=project_service,
    )
    facade._captured = captured  # type: ignore[attr-defined]
    return facade


def test_system_facade_int_apply_template_success(
    system_facade_with_apply_template: SystemFacade,
) -> None:
    """集成测试：apply_template 正确查询 ProjectInfo 并传给 copy_template

    bug #6 修复后链路：Facade → project_service.get_project_cached → copy_template(dest_path, data, overwrite=True)
    验证 copy_template 收到正确的 dest_path（项目绝对路径）和 data（含 project_id/name/stack）。
    """
    result = system_facade_with_apply_template.apply_template("DJ-2026-001", "plc-standard")
    assert result.success is True
    assert isinstance(result.payload, ApplyTemplateResultDTO)
    assert result.payload.project_id == "DJ-2026-001"
    assert result.payload.template_name == "plc-standard"

    # 验证 copy_template 收到的参数
    captured = system_facade_with_apply_template._captured  # type: ignore[attr-defined]
    assert captured["template_name"] == "plc-standard"
    assert captured["overwrite"] is True  # apply_template 用 overwrite=True
    # dest_path 应该是项目绝对路径
    assert "DJ-2026-001_测试PLC" in captured["dest_path"]
    # data 应含 project_id/name/stack
    assert captured["data"]["project_id"] == "DJ-2026-001"
    assert captured["data"]["stack"] == "plc"
    assert captured["data"]["project_name"] == "测试PLC"


def test_system_facade_int_apply_template_project_not_found(
    system_facade_with_apply_template: SystemFacade,
) -> None:
    """集成测试：apply_template 项目不存在时返回 success=False"""
    result = system_facade_with_apply_template.apply_template("NOT-EXIST-999", "plc-standard")
    assert result.success is False
    assert result.payload is None
    assert "项目不存在" in result.message


def test_system_facade_int_apply_template_no_project_service(templates_dir: Path) -> None:
    """集成测试：project_service=None 时 apply_template 返回 '未注入 project_service'"""
    template_service = TemplateService(templates_dir=str(templates_dir))
    facade = SystemFacade(
        pm_session_service=None,
        template_service=template_service,
        project_service=None,
    )

    result = facade.apply_template("DJ-2026-001", "plc-standard")
    assert result.success is False
    assert "未注入 project_service" in result.message


# ── 阶段 C bug #4/#5 误判验证（get_pm_session_view / run_pm_session_check）──


@pytest.fixture
def pm_session_workspace(tmp_path: Path) -> Path:
    """含 PM_SESSION_*.md 文件的工作空间

    构造一个含所有必备章节（0-9，除 7）的 PM_SESSION 文件，
    供 _PmSessionViewAggregator.generate_view / check 使用。
    """
    ws = tmp_path / "pm_session_ws"
    ws.mkdir()

    # 构造含所有必备章节的 PM_SESSION 文件
    pm_session_content = """# PM_SESSION_SW-2026-008

## 0. Meta
- project_id: SW-2026-008
- version: V0.8.0

## 1. Positioning（项目定位）
自动化项目管理工具

## 2. Current Focus
当前焦点：M4 落地

## 3. Status Summary
状态：进行中

## 4. Decisions
无

## 5. Open Questions
无

## 6. Risks
无

## 8. Handoff Notes
无

## 9. Next Actions
下一步：继续开发
"""
    (ws / "PM_SESSION_SW-2026-008.md").write_text(pm_session_content, encoding="utf-8")
    return ws


@pytest.fixture
def system_facade_with_pm_session(pm_session_workspace: Path) -> SystemFacade:
    """构造含真实 _PmSessionViewAggregator 的 SystemFacade

    bug #4/#5 误判验证：make_pm_session_service 已正确封装 generate_view/check 返回 dict，
    SystemFacade 现有调用方式正确。
    """
    from auto_pm.ui.factories import make_pm_session_service

    pm_session_service = make_pm_session_service(str(pm_session_workspace))
    assert pm_session_service is not None, "make_pm_session_service 应返回聚合器实例"

    return SystemFacade(
        pm_session_service=pm_session_service,
        template_service=None,
        project_service=None,
    )


def test_system_facade_int_get_pm_session_view(
    system_facade_with_pm_session: SystemFacade,
    pm_session_workspace: Path,
) -> None:
    """集成测试：get_pm_session_view 通过 _PmSessionViewAggregator 生成视图

    bug #4 误判验证：make_pm_session_service 创建的 _PmSessionViewAggregator 已正确封装
    generate_view() 返回 dict（含 file_path + view），SystemFacade 现有调用方式正确。
    """
    result = system_facade_with_pm_session.get_pm_session_view()
    assert result.success is True
    assert isinstance(result.payload, PmSessionViewDTO)
    assert isinstance(result.payload.data, dict)
    # data 应含 file_path 和 view 两个 key
    assert "file_path" in result.payload.data
    assert "view" in result.payload.data
    # file_path 应指向 PM_SESSION 文件
    assert "PM_SESSION_SW-2026-008.md" in result.payload.data["file_path"]
    # view 应是 markdown 字符串
    assert isinstance(result.payload.data["view"], str)
    assert "PM_SESSION 只读视图" in result.payload.data["view"]


def test_system_facade_int_run_pm_session_check(
    system_facade_with_pm_session: SystemFacade,
) -> None:
    """集成测试：run_pm_session_check 通过 _PmSessionViewAggregator 运行健康检查

    bug #5 误判验证：make_pm_session_service 创建的 _PmSessionViewAggregator 已正确封装
    check() 返回 dict（含 file_path/file_size_kb/total_lines/is_healthy 等），
    SystemFacade 现有调用方式正确。
    """
    result = system_facade_with_pm_session.run_pm_session_check()
    assert result.success is True
    assert isinstance(result.payload, PmSessionCheckResultDTO)
    assert isinstance(result.payload.data, dict)
    # data 应含健康检查关键字段
    expected_keys = {"file_path", "file_size_kb", "total_lines", "is_healthy", "missing_required"}
    assert expected_keys.issubset(result.payload.data.keys())
    # 构造的 PM_SESSION 含所有必备章节，is_healthy 应为 True
    assert result.payload.data["is_healthy"] is True
    assert result.payload.data["missing_required"] == []


def test_system_facade_int_get_pm_session_view_no_service() -> None:
    """集成测试：pm_session_service=None 时 get_pm_session_view 返回 success=False"""
    facade = SystemFacade(pm_session_service=None)
    result = facade.get_pm_session_view()
    assert result.success is False
    assert "No pm_session_service" in result.message


def test_system_facade_int_run_pm_session_check_no_service() -> None:
    """集成测试：pm_session_service=None 时 run_pm_session_check 返回 success=False"""
    facade = SystemFacade(pm_session_service=None)
    result = facade.run_pm_session_check()
    assert result.success is False
    assert "No pm_session_service" in result.message
