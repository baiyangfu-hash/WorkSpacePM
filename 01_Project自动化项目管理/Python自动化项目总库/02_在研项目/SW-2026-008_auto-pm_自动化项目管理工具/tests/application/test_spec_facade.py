"""SpecFacade 单元测试

覆盖 SpecFacade 的 4 个方法：
- run_spec_check
- get_spec_center_overview
- list_spec_center_entries
- generate_spec_index (M5 CHG-119 新增)
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from auto_pm.application.spec_facade import SpecFacade
from auto_pm.ui.contracts.dto.spec_dto import (
    SpecCenterEntryDTO,
    SpecCenterOverviewDTO,
    SpecCheckResultDTO,
    SpecFrontmatterResultDTO,
    SpecIndexResultDTO,
    SpecReportResultDTO,
)

# ── mock helpers ──────────────────────────────────────


def _make_check_output(**overrides: Any) -> SimpleNamespace:
    """构造 spec check 输出 mock（含 error_count/warning_count/info_count/exit_code/results）"""
    severity = overrides.get("severity", SimpleNamespace(name="ERROR"))
    result = SimpleNamespace(
        check_id=overrides.get("check_id", "CHK-001"),
        severity=severity,
        message=overrides.get("message", "sample message"),
        details=overrides.get("details", {"key": "value"}),
        fix_suggestion=overrides.get("fix_suggestion", "suggestion"),
    )
    return SimpleNamespace(
        error_count=overrides.get("error_count", 1),
        warning_count=overrides.get("warning_count", 2),
        info_count=overrides.get("info_count", 3),
        exit_code=overrides.get("exit_code", 1),
        results=overrides.get("results", [result]),
    )


def _make_overview(**overrides: Any) -> SimpleNamespace:
    """构造 spec center overview mock（含 spec_count/domain_counts/lifecycle_counts/health_summary）"""
    health = SimpleNamespace(
        error_count=overrides.get("health_error_count", 0),
        warning_count=overrides.get("health_warning_count", 1),
        info_count=overrides.get("health_info_count", 2),
        exit_code=overrides.get("health_exit_code", 0),
    )
    return SimpleNamespace(
        spec_count=overrides.get("spec_count", 10),
        domain_counts=overrides.get("domain_counts", {"PLC": 5, "Python": 5}),
        lifecycle_counts=overrides.get("lifecycle_counts", {"active": 8, "draft": 2}),
        health_summary=health,
    )


def _make_entry(**overrides: Any) -> SimpleNamespace:
    """构造 spec center entry mock（含 spec_id/title/number/domain/lifecycle/canonical_path/version/file_exists）"""
    return SimpleNamespace(
        spec_id=overrides.get("spec_id", "SW-2026-001"),
        title=overrides.get("title", "Sample Spec"),
        number=overrides.get("number", "001"),
        domain=overrides.get("domain", "PLC"),
        lifecycle=overrides.get("lifecycle", "active"),
        canonical_path=overrides.get("canonical_path", "/specs/sample.md"),
        version=overrides.get("version", "1.0.0"),
        file_exists=overrides.get("file_exists", True),
    )


def _raise(exc: Exception) -> Any:
    """返回一个调用即抛出指定异常的函数（兼容任意参数签名）"""

    def _fn(*args: Any, **kwargs: Any) -> Any:
        raise exc

    return _fn


# ── run_spec_check 测试 ──────────────────────────────────────


def test_run_spec_check_success() -> None:
    """正常调用返回 SpecCheckResultDTO 且字段正确"""
    output = _make_check_output()
    service = SimpleNamespace(run=lambda: output)
    facade = SpecFacade(spec_check_service=service)

    result = facade.run_spec_check()

    assert result.success is True
    assert isinstance(result.payload, SpecCheckResultDTO)
    assert result.payload.error_count == 1
    assert result.payload.warning_count == 2
    assert result.payload.info_count == 3
    assert result.payload.exit_code == 1
    assert len(result.payload.results) == 1
    item = result.payload.results[0]
    assert item["check_id"] == "CHK-001"
    assert item["severity"] == "ERROR"
    assert item["message"] == "sample message"
    assert item["details"] == {"key": "value"}
    assert item["fix_suggestion"] == "suggestion"


def test_run_spec_check_no_service() -> None:
    """spec_check_service=None 时返回 success=False + payload=None"""
    facade = SpecFacade(spec_check_service=None)

    result = facade.run_spec_check()

    assert result.success is False
    assert result.payload is None
    assert "No spec_check_service" in result.message


def test_run_spec_check_exception() -> None:
    """service.run() 抛异常时返回 success=False + payload=None"""
    service = SimpleNamespace(run=_raise(Exception("check boom")))
    facade = SpecFacade(spec_check_service=service)

    result = facade.run_spec_check()

    assert result.success is False
    assert result.payload is None
    assert "check boom" in result.message


# ── get_spec_center_overview 测试 ────────────────────────────


def test_get_spec_center_overview_success() -> None:
    """正常调用返回 SpecCenterOverviewDTO 且字段正确"""
    overview = _make_overview()
    service = SimpleNamespace(get_overview=lambda: overview)
    facade = SpecFacade(spec_center_service=service)

    result = facade.get_spec_center_overview()

    assert result.success is True
    assert isinstance(result.payload, SpecCenterOverviewDTO)
    assert result.payload.spec_count == 10
    assert result.payload.domain_counts == {"PLC": 5, "Python": 5}
    assert result.payload.lifecycle_counts == {"active": 8, "draft": 2}
    assert result.payload.health_summary == {
        "error_count": 0,
        "warning_count": 1,
        "info_count": 2,
        "exit_code": 0,
    }


def test_get_spec_center_overview_no_service() -> None:
    """spec_center_service=None 时返回 success=False + payload=None"""
    facade = SpecFacade(spec_center_service=None)

    result = facade.get_spec_center_overview()

    assert result.success is False
    assert result.payload is None
    assert "No spec_center_service" in result.message


def test_get_spec_center_overview_exception() -> None:
    """service.get_overview() 抛异常时返回 success=False + payload=None"""
    service = SimpleNamespace(get_overview=_raise(Exception("overview boom")))
    facade = SpecFacade(spec_center_service=service)

    result = facade.get_spec_center_overview()

    assert result.success is False
    assert result.payload is None
    assert "overview boom" in result.message


# ── list_spec_center_entries 测试 ────────────────────────────


def test_list_spec_center_entries_success() -> None:
    """正常调用返回 list[SpecCenterEntryDTO] 且字段正确"""
    entries = [
        _make_entry(spec_id="SW-001"),
        _make_entry(spec_id="SW-002", file_exists=False, domain="Python"),
    ]
    service = SimpleNamespace(list_entries=lambda filter_domain=None: entries)
    facade = SpecFacade(spec_center_service=service)

    result = facade.list_spec_center_entries()

    assert result.success is True
    assert isinstance(result.payload, list)
    assert len(result.payload) == 2
    assert all(isinstance(item, SpecCenterEntryDTO) for item in result.payload)
    assert result.payload[0].spec_id == "SW-001"
    assert result.payload[0].title == "Sample Spec"
    assert result.payload[0].number == "001"
    assert result.payload[0].domain == "PLC"
    assert result.payload[0].lifecycle == "active"
    assert result.payload[0].canonical_path == "/specs/sample.md"
    assert result.payload[0].version == "1.0.0"
    assert result.payload[0].file_exists is True
    assert result.payload[1].spec_id == "SW-002"
    assert result.payload[1].file_exists is False
    assert result.payload[1].domain == "Python"


def test_list_spec_center_entries_with_filter() -> None:
    """带 filter_domain 参数调用，验证 filter_domain 透传给 service.list_entries()"""
    captured: dict[str, Any] = {}

    def _list_entries(filter_domain: str | None = None) -> Any:
        captured["filter_domain"] = filter_domain
        return [_make_entry(domain="PLC")]

    service = SimpleNamespace(list_entries=_list_entries)
    facade = SpecFacade(spec_center_service=service)

    result = facade.list_spec_center_entries(filter_domain="PLC")

    assert result.success is True
    assert captured["filter_domain"] == "PLC"
    assert isinstance(result.payload, list)
    assert len(result.payload) == 1
    assert isinstance(result.payload[0], SpecCenterEntryDTO)
    assert result.payload[0].domain == "PLC"


def test_list_spec_center_entries_no_service() -> None:
    """spec_center_service=None 时返回 success=False + payload=[]"""
    facade = SpecFacade(spec_center_service=None)

    result = facade.list_spec_center_entries()

    assert result.success is False
    assert result.payload == []
    assert "No spec_center_service" in result.message


def test_list_spec_center_entries_exception() -> None:
    """service.list_entries() 抛异常时返回 success=False + payload=[]"""
    service = SimpleNamespace(list_entries=_raise(Exception("entries boom")))
    facade = SpecFacade(spec_center_service=service)

    result = facade.list_spec_center_entries()

    assert result.success is False
    assert result.payload == []
    assert "entries boom" in result.message


# ── generate_spec_index 测试（M5 CHG-119 新增）──────────────


def _make_index_output(**overrides: Any) -> SimpleNamespace:
    """构造 IndexService.run() 输出 mock（含 generated_files: list[Path], errors: list[str]）"""
    return SimpleNamespace(
        generated_files=overrides.get(
            "generated_files", [Path("/tmp/index_pm.md"), Path("/tmp/index_plc.md")]
        ),
        errors=overrides.get("errors", []),
    )


def test_generate_spec_index_success() -> None:
    """正常调用返回 SpecIndexResultDTO 且 Path→str 转换正确（domain='all'）"""
    output = _make_index_output()
    service = SimpleNamespace(run=lambda domains=None: output)
    facade = SpecFacade(index_service=service)

    result = facade.generate_spec_index(domain="all")

    assert result.success is True
    assert isinstance(result.payload, SpecIndexResultDTO)
    assert result.payload.domain == "all"
    # Path → str 转换验证（跨平台：str(Path(...)) 在 Windows 用反斜杠）
    assert all(isinstance(f, str) for f in result.payload.generated_files)
    assert result.payload.generated_files == [
        str(Path("/tmp/index_pm.md")),
        str(Path("/tmp/index_plc.md")),
    ]
    assert result.payload.errors == []


def test_generate_spec_index_domain_filter() -> None:
    """domain='plc' 时 service.run(domains=['plc']) 透传验证"""
    captured: dict[str, Any] = {}
    output = _make_index_output(generated_files=[Path("/tmp/index_plc.md")])

    def _run(domains=None) -> Any:  # type: ignore[no-untyped-def]
        captured["domains"] = domains
        return output

    service = SimpleNamespace(run=_run)
    facade = SpecFacade(index_service=service)

    result = facade.generate_spec_index(domain="plc")

    assert result.success is True
    assert result.payload.domain == "plc"  # type: ignore[union-attr]
    assert captured["domains"] == ["plc"]  # domain="plc" → domains=["plc"]


def test_generate_spec_index_all_domains_none() -> None:
    """domain='all' 时 service.run(domains=None) 透传验证"""
    captured: dict[str, Any] = {}
    output = _make_index_output()

    def _run(domains=None) -> Any:  # type: ignore[no-untyped-def]
        captured["domains"] = domains
        return output

    service = SimpleNamespace(run=_run)
    facade = SpecFacade(index_service=service)

    result = facade.generate_spec_index(domain="all")

    assert result.success is True
    assert captured["domains"] is None  # domain="all" → domains=None


def test_generate_spec_index_no_service() -> None:
    """index_service=None 时返回 success=False + payload=None"""
    facade = SpecFacade(index_service=None)

    result = facade.generate_spec_index()

    assert result.success is False
    assert result.payload is None
    assert "No index_service" in result.message


def test_generate_spec_index_exception() -> None:
    """service.run() 抛异常时返回 success=False + payload=None"""
    service = SimpleNamespace(run=_raise(Exception("index boom")))
    facade = SpecFacade(index_service=service)

    result = facade.generate_spec_index()

    assert result.success is False
    assert result.payload is None
    assert "index boom" in result.message


def test_generate_spec_index_with_errors() -> None:
    """output.errors 非空时仍返回 success=True（部分成功）"""
    output = _make_index_output(
        generated_files=[Path("/tmp/index_pm.md")],
        errors=["plc 域生成失败: 注册表为空"],
    )
    service = SimpleNamespace(run=lambda domains=None: output)
    facade = SpecFacade(index_service=service)

    result = facade.generate_spec_index()

    assert result.success is True
    assert result.payload.errors == ["plc 域生成失败: 注册表为空"]  # type: ignore[union-attr]
    assert result.payload.generated_files == [str(Path("/tmp/index_pm.md"))]  # type: ignore[union-attr]


# ── generate_spec_report 测试（M5 CHG-120 新增）──────────────


def _make_report_output(**overrides: Any) -> SimpleNamespace:
    """构造 ReportService.generate() 输出 mock（含 content: str, output_path: Path, fmt: str）"""
    return SimpleNamespace(
        content=overrides.get("content", "# 规范元数据汇总报告\n\n总览..."),
        output_path=overrides.get("output_path", Path("/tmp/规范元数据汇总报告.md")),
        fmt=overrides.get("fmt", "markdown"),
    )


# ── check_spec_frontmatter 测试（M5 CHG-121 新增）──────────────


def _make_frontmatter_item(**overrides: Any) -> SimpleNamespace:
    """构造 FrontmatterItem mock（8 字段：spec_id/file_path/has_frontmatter/is_deprecated/file_exists/new_frontmatter/status）"""
    return SimpleNamespace(
        spec_id=overrides.get("spec_id", "SW-2026-006"),
        file_path=overrides.get("file_path", Path("/tmp/spec.md")),
        has_frontmatter=overrides.get("has_frontmatter", False),
        is_deprecated=overrides.get("is_deprecated", False),
        file_exists=overrides.get("file_exists", True),
        new_frontmatter=overrides.get("new_frontmatter", "---\nspec_id: SW-2026-006\n---\n"),
        status=overrides.get("status", "pending"),
    )


def _make_frontmatter_output(**overrides: Any) -> SimpleNamespace:
    """构造 FrontmatterService.apply() 输出 mock（4 字段：items/modified_count/skipped_count/error_count）"""
    return SimpleNamespace(
        items=overrides.get("items", []),
        modified_count=overrides.get("modified_count", 1),
        skipped_count=overrides.get("skipped_count", 0),
        error_count=overrides.get("error_count", 0),
    )


def test_generate_spec_report_success() -> None:
    """正常调用返回 SpecReportResultDTO 且 Path→str 转换正确 + file_size=len(content)"""
    output = _make_report_output()
    service = SimpleNamespace(generate=lambda fmt="markdown", output_path=None: output)
    facade = SpecFacade(report_service=service)

    result = facade.generate_spec_report(fmt="markdown")

    assert result.success is True
    assert isinstance(result.payload, SpecReportResultDTO)
    assert result.payload.fmt == "markdown"
    # Path → str 转换验证（跨平台：str(Path(...)) 在 Windows 用反斜杠）
    assert result.payload.output_path == str(Path("/tmp/规范元数据汇总报告.md"))
    assert result.payload.content == "# 规范元数据汇总报告\n\n总览..."
    assert result.payload.file_size == len("# 规范元数据汇总报告\n\n总览...")


def test_generate_spec_report_fmt_json() -> None:
    """fmt='json' 时 service.generate(fmt='json') 透传验证"""
    captured: dict[str, Any] = {}
    output = _make_report_output(
        fmt="json", content='{"specs": {}}', output_path=Path("/tmp/report.json")
    )

    def _generate(fmt="markdown", output_path=None) -> Any:  # type: ignore[no-untyped-def]
        captured["fmt"] = fmt
        return output

    service = SimpleNamespace(generate=_generate)
    facade = SpecFacade(report_service=service)

    result = facade.generate_spec_report(fmt="json")

    assert result.success is True
    assert result.payload.fmt == "json"  # type: ignore[union-attr]
    assert captured["fmt"] == "json"  # fmt 透传验证
    assert result.payload.content == '{"specs": {}}'  # type: ignore[union-attr]
    assert result.payload.file_size == len('{"specs": {}}')  # type: ignore[union-attr]


def test_generate_spec_report_no_service() -> None:
    """report_service=None 时返回 success=False + payload=None"""
    facade = SpecFacade(report_service=None)

    result = facade.generate_spec_report()

    assert result.success is False
    assert result.payload is None
    assert "No report_service" in result.message


def test_generate_spec_report_exception() -> None:
    """service.generate() 抛异常时返回 success=False + payload=None"""
    service = SimpleNamespace(generate=_raise(Exception("report boom")))
    facade = SpecFacade(report_service=service)

    result = facade.generate_spec_report()

    assert result.success is False
    assert result.payload is None
    assert "report boom" in result.message


def test_generate_spec_report_file_size_accuracy() -> None:
    """file_size 准确反映 content 长度（含中文多字节字符）"""
    content = "# 报告\n\n中文内容测试\n" * 10
    output = _make_report_output(content=content)
    service = SimpleNamespace(generate=lambda fmt="markdown", output_path=None: output)
    facade = SpecFacade(report_service=service)

    result = facade.generate_spec_report()

    assert result.success is True
    assert result.payload.file_size == len(content)  # type: ignore[union-attr]
    assert result.payload.content == content  # type: ignore[union-attr]


# ── check_spec_frontmatter 测试（M5 CHG-121 新增）──────────────


def test_check_spec_frontmatter_success() -> None:
    """正常调用（auto_fix=False）返回 DTO + items Path→str 转换 + 状态统计"""
    items = [
        _make_frontmatter_item(spec_id="SW-006", status="pending"),
        _make_frontmatter_item(spec_id="SW-007", status="skipped", has_frontmatter=True),
        _make_frontmatter_item(spec_id="SW-008", status="error", file_exists=False),
    ]
    service = SimpleNamespace(preview=lambda: items)
    facade = SpecFacade(frontmatter_service=service)

    result = facade.check_spec_frontmatter(auto_fix=False)

    assert result.success is True
    assert isinstance(result.payload, SpecFrontmatterResultDTO)
    assert result.payload.total_count == 3
    assert result.payload.pending_count == 1
    assert result.payload.skipped_count == 1
    assert result.payload.error_count == 1
    assert result.payload.modified_count == 0  # auto_fix=False
    assert result.payload.auto_fixed is False
    # Path → str 转换验证
    assert result.payload.items[0]["file_path"] == str(Path("/tmp/spec.md"))
    assert result.payload.items[0]["status"] == "pending"


def test_check_spec_frontmatter_auto_fix() -> None:
    """auto_fix=True 时调用 apply(pending_items) + modified_count 从 apply 结果获取"""
    items = [
        _make_frontmatter_item(spec_id="SW-006", status="pending"),
        _make_frontmatter_item(spec_id="SW-007", status="skipped", has_frontmatter=True),
    ]
    apply_output = _make_frontmatter_output(modified_count=1)
    apply_calls: list = []  # type: ignore[type-arg]

    def _apply(pending_items) -> Any:  # type: ignore[no-untyped-def]
        apply_calls.append(pending_items)
        return apply_output

    service = SimpleNamespace(preview=lambda: items, apply=_apply)
    facade = SpecFacade(frontmatter_service=service)

    result = facade.check_spec_frontmatter(auto_fix=True)

    assert result.success is True
    assert result.payload.modified_count == 1  # type: ignore[union-attr]
    assert result.payload.auto_fixed is True  # type: ignore[union-attr]
    assert result.payload.pending_count == 1  # type: ignore[union-attr]  # 基于 preview 原始 items 统计
    # apply 只接收 pending items
    assert len(apply_calls) == 1
    assert len(apply_calls[0]) == 1
    assert apply_calls[0][0].spec_id == "SW-006"


def test_check_spec_frontmatter_auto_fix_no_pending() -> None:
    """auto_fix=True 但无 pending items 时不调用 apply"""
    items = [_make_frontmatter_item(spec_id="SW-007", status="skipped", has_frontmatter=True)]
    apply_calls: list = []  # type: ignore[type-arg]
    service = SimpleNamespace(
        preview=lambda: items,
        apply=lambda pending: (
            apply_calls.append(pending) or _make_frontmatter_output(modified_count=0)
        ),  # type: ignore[func-returns-value]
    )
    facade = SpecFacade(frontmatter_service=service)

    result = facade.check_spec_frontmatter(auto_fix=True)

    assert result.success is True
    assert result.payload.modified_count == 0  # type: ignore[union-attr]
    assert result.payload.pending_count == 0  # type: ignore[union-attr]
    assert len(apply_calls) == 0  # 无 pending，不调用 apply


def test_check_spec_frontmatter_no_service() -> None:
    """frontmatter_service=None 时返回 success=False + payload=None"""
    facade = SpecFacade(frontmatter_service=None)

    result = facade.check_spec_frontmatter()

    assert result.success is False
    assert result.payload is None
    assert "No frontmatter_service" in result.message


def test_check_spec_frontmatter_exception() -> None:
    """service.preview() 抛异常时返回 success=False + payload=None"""
    service = SimpleNamespace(preview=_raise(Exception("frontmatter boom")))
    facade = SpecFacade(frontmatter_service=service)

    result = facade.check_spec_frontmatter()

    assert result.success is False
    assert result.payload is None
    assert "frontmatter boom" in result.message


def test_run_spec_check_python_project(tmp_path: Path) -> None:
    """测试通过 SpecFacade 路由 Python 项目规范检查"""
    proj = SimpleNamespace(
        project_id="SW-2026-PYT", name="Python项目", stack="python", path=str(tmp_path)
    )
    proj_service = SimpleNamespace(
        get_project=lambda pid: proj if pid == "SW-2026-PYT" else None,
        workspace_root=str(tmp_path),
    )
    # mock PythonProjectService 行为
    facade = SpecFacade(project_service=proj_service)

    # 模拟 templates/python-tool/template 目录结构，用于 check
    (tmp_path / ".copier-answers.yml").write_text("stack: python\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )

    result = facade.run_spec_check(project_id="SW-2026-PYT")
    assert result.success is True
    assert isinstance(result.payload, SpecCheckResultDTO)
    # 因为很多必填文件没有，所以 error_count 应大于 0
    assert result.payload.error_count > 0


def test_run_spec_repair_python_project(tmp_path: Path) -> None:
    """测试通过 SpecFacade 路由 Python 项目一键修复"""
    proj = SimpleNamespace(
        project_id="SW-2026-PYT", name="Python项目", stack="python", path=str(tmp_path)
    )
    proj_service = SimpleNamespace(
        get_project=lambda pid: proj if pid == "SW-2026-PYT" else None,
        workspace_root=str(tmp_path),
    )
    facade = SpecFacade(project_service=proj_service)

    # 物理模板路径
    tpl_path = tmp_path / "templates" / "python-tool" / "template"
    tpl_path.mkdir(parents=True, exist_ok=True)
    (tpl_path / ".ruff.toml").write_text("ruff content", encoding="utf-8")

    # 手工把 templates_dir 补到 PythonProjectService
    # 我们需要在测试中 mock 或控制环境

    result = facade.run_spec_repair(project_id="SW-2026-PYT")
    # 即使修复项为 0（因缺少模板文件），也应该成功执行返回 success=True
    assert result.success is True
    assert "success" in result.message or "修复" in result.message
