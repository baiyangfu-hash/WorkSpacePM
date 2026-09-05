"""SystemFacade 单元测试

覆盖 SystemFacade 的 7 个方法：
- get_pm_session_view / run_pm_session_check
- list_templates / get_template_path
- get_template_detail（含 copier.yml 解析 + stack 推断 + usage_count 统计）
- apply_template
- archive_pm_session（M5 CHG-117 新增）

M4 第 2 批重构后：方法返回带类型 DTO（list_templates/get_template_path 除外，保持基础类型）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from auto_pm.application.system_facade import SystemFacade
from auto_pm.ui.contracts.dto.system_dto import (
    ApplyTemplateResultDTO,
    PmSessionArchiveResultDTO,
    PmSessionCheckResultDTO,
    PmSessionViewDTO,
    TemplateDetailDTO,
)

# ── mock helpers ──────────────────────────────────────


def _raise(exc: Exception) -> Any:
    """返回一个调用即抛出指定异常的函数（兼容任意参数签名）"""

    def _fn(*args: Any, **kwargs: Any) -> Any:
        raise exc

    return _fn


def _make_pm_service(**overrides: Any) -> SimpleNamespace:
    """构造 pm_session_service mock"""
    return SimpleNamespace(
        generate_view=overrides.get("generate_view", lambda: {"status": "ok"}),
        check=overrides.get("check", lambda: {"errors": 0, "warnings": 2}),
        archive=overrides.get(
            "archive",
            lambda section, keep_recent, dry_run: {
                "archive_file": "/tmp/archive.md",
                "archived_sections": [section],
                "archived_line_count": 10,
                "main_file_lines_before": 300,
                "main_file_lines_after": 290,
                "is_dry_run": dry_run,
                "section_title": "Implementation Log",
                "section_total_lines": 50,
                "keep_recent": keep_recent,
            },
        ),
    )


def _make_template_service(**overrides: Any) -> SimpleNamespace:
    """构造 template_service mock

    阶段 C bug #6 修复后：apply_template 改为 copy_template(template_name, dest_path, data, overwrite)
    """
    return SimpleNamespace(
        list_templates=overrides.get("list_templates", lambda: ["tpl1", "tpl2"]),
        get_template_path=overrides.get("get_template_path", lambda name: f"/templates/{name}"),
        copy_template=overrides.get(
            "copy_template",
            lambda template_name, dest_path, data, overwrite=False: {
                "applied": True,
                "dest_path": dest_path,
                "template": template_name,
                "data": data,
            },
        ),
    )


def _make_project(stack: str = "python") -> SimpleNamespace:
    """构造单个 project mock（含 stack 属性，用于 get_template_detail usage_count 统计）"""
    return SimpleNamespace(stack=stack)


def _make_project_info(
    project_id: str = "PROJ-001",
    name: str = "测试项目",
    stack: str = "python",
    path: str = "/tmp/proj",
) -> SimpleNamespace:
    """构造 ProjectInfo mock（含完整字段，用于 apply_template 查项目路径）"""
    return SimpleNamespace(
        project_id=project_id,
        name=name,
        path=path,
        stack=stack,
        project_type="single_machine",
    )


def _make_project_service(*projects: Any) -> SimpleNamespace:
    """构造 project_service mock

    - get_project_cached(pid) → 返回匹配的 project 或 None
    - list_projects() → 返回所有 projects
    """
    if not projects:
        projects = (_make_project_info(),)

    def _get_cached(pid: str) -> Any:
        for p in projects:
            if p.project_id == pid:
                return p
        return None

    def _list() -> Any:
        return list(projects)

    return SimpleNamespace(
        get_project_cached=_get_cached,
        get_project=_get_cached,
        list_projects=_list,
    )


# ── get_pm_session_view 测试 ──────────────────────────────


def test_get_pm_session_view_success() -> None:
    """正常调用返回 PmSessionViewDTO 且 data 字段正确"""
    svc = _make_pm_service(generate_view=lambda: {"status": "ok", "version": "1.0"})
    facade = SystemFacade(pm_session_service=svc)

    res = facade.get_pm_session_view()

    assert res.success is True
    assert isinstance(res.payload, PmSessionViewDTO)
    assert res.payload.data == {"status": "ok", "version": "1.0"}


def test_get_pm_session_view_no_service() -> None:
    """pm_session_service=None 时返回 success=False + payload=None"""
    facade = SystemFacade(pm_session_service=None)

    res = facade.get_pm_session_view()

    assert res.success is False
    assert res.payload is None
    assert "No pm_session_service" in res.message


def test_get_pm_session_view_exception() -> None:
    """service.generate_view() 抛异常时返回 success=False + payload=None"""
    svc = SimpleNamespace(generate_view=_raise(Exception("view boom")), check=lambda: {})
    facade = SystemFacade(pm_session_service=svc)

    res = facade.get_pm_session_view()

    assert res.success is False
    assert res.payload is None
    assert "view boom" in res.message


# ── run_pm_session_check 测试 ──────────────────────────────


def test_run_pm_session_check_success() -> None:
    """正常调用返回 PmSessionCheckResultDTO 且 data 字段正确"""
    svc = _make_pm_service(check=lambda: {"errors": 0, "warnings": 2, "passed": 10})
    facade = SystemFacade(pm_session_service=svc)

    res = facade.run_pm_session_check()

    assert res.success is True
    assert isinstance(res.payload, PmSessionCheckResultDTO)
    assert res.payload.data == {"errors": 0, "warnings": 2, "passed": 10}


def test_run_pm_session_check_no_service() -> None:
    """pm_session_service=None 时返回 success=False + payload=None"""
    facade = SystemFacade(pm_session_service=None)

    res = facade.run_pm_session_check()

    assert res.success is False
    assert res.payload is None
    assert "No pm_session_service" in res.message


def test_run_pm_session_check_exception() -> None:
    """service.check() 抛异常时返回 success=False + payload=None"""
    svc = SimpleNamespace(generate_view=lambda: {}, check=_raise(Exception("check boom")))
    facade = SystemFacade(pm_session_service=svc)

    res = facade.run_pm_session_check()

    assert res.success is False
    assert res.payload is None
    assert "check boom" in res.message


# ── list_templates 测试 ──────────────────────────────


def test_list_templates_success() -> None:
    """正常调用返回 list[str]"""
    svc = _make_template_service(list_templates=lambda: ["python-tpl", "plc-tpl"])
    facade = SystemFacade(pm_session_service=None, template_service=svc)

    res = facade.list_templates()

    assert res.success is True
    assert res.payload == ["python-tpl", "plc-tpl"]


def test_list_templates_no_service() -> None:
    """template_service=None 时返回 success=False + payload=[]"""
    facade = SystemFacade(pm_session_service=None, template_service=None)

    res = facade.list_templates()

    assert res.success is False
    assert res.payload == []
    assert "No template_service" in res.message


# ── get_template_path 测试 ──────────────────────────────


def test_get_template_path_success() -> None:
    """正常调用返回 str 路径"""
    svc = _make_template_service(get_template_path=lambda name: f"/templates/{name}")
    facade = SystemFacade(pm_session_service=None, template_service=svc)

    res = facade.get_template_path("python-tpl")

    assert res.success is True
    assert res.payload == "/templates/python-tpl"


def test_get_template_path_no_service() -> None:
    """template_service=None 时返回 success=False + payload=''"""
    facade = SystemFacade(pm_session_service=None, template_service=None)

    res = facade.get_template_path("python-tpl")

    assert res.success is False
    assert res.payload == ""
    assert "No template_service" in res.message


# ── get_template_detail 测试 ──────────────────────────────


def test_get_template_detail_success(tmp_path: Path) -> None:  # type: ignore[name-defined]
    """正常调用返回 TemplateDetailDTO 且 6 个字段正确（含 copier.yml 解析 + stack 推断 + usage_count 统计）"""
    # 创建 copier.yml
    copier_yml = tmp_path / "copier.yml"
    copier_yml.write_text(
        "_commit: v1.2.3\n_description: Python project template\n", encoding="utf-8"
    )

    template_svc = _make_template_service(get_template_path=lambda name: str(tmp_path))
    project_svc = SimpleNamespace(
        list_projects=lambda: [
            _make_project("python"),
            _make_project("python"),
            _make_project("plc"),
        ],
    )
    facade = SystemFacade(
        pm_session_service=None, template_service=template_svc, project_service=project_svc
    )

    res = facade.get_template_detail("python-tpl")

    assert res.success is True
    assert isinstance(res.payload, TemplateDetailDTO)
    assert res.payload.name == "python-tpl"
    assert res.payload.version == "v1.2.3"
    assert res.payload.description == "Python project template"
    assert res.payload.stack == "python"
    assert res.payload.usage_count == 2  # 2 个 python 项目
    assert res.payload.path == str(tmp_path)


def test_get_template_detail_no_copier_yml(tmp_path: Path) -> None:  # type: ignore[name-defined]
    """copier.yml 不存在时使用默认值 version=unknown + description=暂无描述"""
    template_svc = _make_template_service(get_template_path=lambda name: str(tmp_path))
    facade = SystemFacade(
        pm_session_service=None, template_service=template_svc, project_service=None
    )

    res = facade.get_template_detail("plc-tpl")

    assert res.success is True
    assert isinstance(res.payload, TemplateDetailDTO)
    assert res.payload.version == "unknown"
    assert res.payload.description == "暂无描述"
    assert res.payload.stack == "plc"  # "plc" in template_name
    assert res.payload.usage_count == 0  # project_service=None


def test_get_template_detail_no_service() -> None:
    """template_service=None 时返回 success=False + payload=None"""
    facade = SystemFacade(pm_session_service=None, template_service=None)

    res = facade.get_template_detail("python-tpl")

    assert res.success is False
    assert res.payload is None
    assert "No template_service" in res.message


def test_get_template_detail_path_not_exist() -> None:
    """template_service.get_template_path 返回空字符串时返回 success=False"""
    template_svc = _make_template_service(get_template_path=lambda name: "")
    facade = SystemFacade(pm_session_service=None, template_service=template_svc)

    res = facade.get_template_detail("missing-tpl")

    assert res.success is False
    assert res.payload is None
    assert "模板路径不存在" in res.message


# ── apply_template 测试 ──────────────────────────────


def test_apply_template_success() -> None:
    """正常调用返回 ApplyTemplateResultDTO 且字段正确

    阶段 C bug #6 修复后：调 copy_template(template_name, dest_path, data, overwrite=True)
    """
    svc = _make_template_service(
        copy_template=lambda template_name, dest_path, data, overwrite=False: {
            "applied": True,
            "dest_path": dest_path,
            "template": template_name,
            "data": data,
        }
    )
    project_svc = _make_project_service()
    facade = SystemFacade(
        pm_session_service=None, template_service=svc, project_service=project_svc
    )

    res = facade.apply_template("PROJ-001", "python-tpl")

    assert res.success is True
    assert isinstance(res.payload, ApplyTemplateResultDTO)
    assert res.payload.project_id == "PROJ-001"
    assert res.payload.template_name == "python-tpl"
    assert res.payload.result["applied"] is True
    assert res.payload.result["dest_path"] == "/tmp/proj"  # 来自 _make_project_info 默认 path
    assert res.payload.result["data"]["project_id"] == "PROJ-001"
    assert res.payload.result["data"]["stack"] == "python"


def test_apply_template_no_service() -> None:
    """template_service=None 时返回 success=False + payload=None"""
    facade = SystemFacade(pm_session_service=None, template_service=None)

    res = facade.apply_template("PROJ-001", "python-tpl")

    assert res.success is False
    assert res.payload is None
    assert "No template_service" in res.message


def test_apply_template_no_project_service() -> None:
    """project_service=None 时返回 '未注入 project_service'"""
    svc = _make_template_service()
    facade = SystemFacade(pm_session_service=None, template_service=svc, project_service=None)

    res = facade.apply_template("PROJ-001", "python-tpl")

    assert res.success is False
    assert res.payload is None
    assert "未注入 project_service" in res.message


def test_apply_template_project_not_found() -> None:
    """project_service 未找到项目时返回 success=False"""
    svc = _make_template_service()
    project_svc = _make_project_service()  # 默认含 PROJ-001
    facade = SystemFacade(
        pm_session_service=None, template_service=svc, project_service=project_svc
    )

    res = facade.apply_template("NOT-EXIST", "python-tpl")

    assert res.success is False
    assert res.payload is None
    assert "项目不存在" in res.message


def test_apply_template_exception() -> None:
    """service.copy_template() 抛异常时返回 success=False + payload=None"""
    svc = SimpleNamespace(
        list_templates=lambda: [],
        get_template_path=lambda name: "",
        copy_template=_raise(Exception("apply boom")),
    )
    project_svc = _make_project_service()
    facade = SystemFacade(
        pm_session_service=None, template_service=svc, project_service=project_svc
    )

    res = facade.apply_template("PROJ-001", "python-tpl")

    assert res.success is False
    assert res.payload is None
    assert "apply boom" in res.message


# ── archive_pm_session 测试（M5 CHG-117 新增）──────────────


def test_archive_pm_session_success() -> None:
    """正常调用返回 PmSessionArchiveResultDTO 且字段正确"""
    svc = _make_pm_service()
    facade = SystemFacade(pm_session_service=svc)

    res = facade.archive_pm_session("6", 20, True)

    assert res.success is True
    assert isinstance(res.payload, PmSessionArchiveResultDTO)
    assert res.payload.archive_file == "/tmp/archive.md"
    assert res.payload.archived_sections == ["6"]
    assert res.payload.archived_line_count == 10
    assert res.payload.main_file_lines_before == 300
    assert res.payload.main_file_lines_after == 290
    assert res.payload.is_dry_run is True
    assert res.payload.section_title == "Implementation Log"
    assert res.payload.section_total_lines == 50
    assert res.payload.keep_recent == 20


def test_archive_pm_session_no_service() -> None:
    """pm_session_service=None 时返回 success=False + payload=None"""
    facade = SystemFacade(pm_session_service=None)

    res = facade.archive_pm_session("6", 20, False)

    assert res.success is False
    assert res.payload is None
    assert "No pm_session_service" in res.message


def test_archive_pm_session_error_response() -> None:
    """service.archive() 返回 error 字段时返回 success=False"""
    svc = _make_pm_service(
        archive=lambda section, keep_recent, dry_run: {"error": f"章节 §{section} 不存在"}
    )
    facade = SystemFacade(pm_session_service=svc)

    res = facade.archive_pm_session("99", 0, True)

    assert res.success is False
    assert res.payload is None
    assert "章节 §99 不存在" in res.message


def test_archive_pm_session_exception() -> None:
    """service.archive() 抛异常时返回 success=False + payload=None"""
    svc = SimpleNamespace(
        generate_view=lambda: {},
        check=lambda: {},
        archive=_raise(Exception("archive boom")),
    )
    facade = SystemFacade(pm_session_service=svc)

    res = facade.archive_pm_session("6", 20, False)

    assert res.success is False
    assert res.payload is None
    assert "archive boom" in res.message
