"""SHC-011~014 文档同步检查器测试（CHG-SCPT-2026-145）

测试 4 个新增 Checker 的正向（一致）和负向（不一致）行为。
这些 Checker 不依赖 SpecRegistry，只依赖 SpecScanner + PM_SESSION 文件。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.spec.core.checker_base import (
    DocIndexValidityChecker,
    Severity,
    TestCountConsistencyChecker,
    VerificationStatusChecker,
    VersionConsistencyChecker,
)
from auto_pm.spec.core.config import WorkspaceConfig
from auto_pm.spec.core.registry import SpecRegistry
from auto_pm.spec.core.scanner import SpecScanner

# ── Fixture ──────────────────────────────────────────────


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """创建项目目录（PM_SESSION 所在目录）"""
    project = tmp_path / "TestProject"
    project.mkdir()
    return project


def _make_scanner(workspace: Path, project_root: Path) -> SpecScanner:
    """创建指向 project_root 的 SpecScanner"""
    config = WorkspaceConfig(workspace=workspace)
    return SpecScanner(workspace=workspace, config=config, project_root=project_root)


def _make_registry(workspace: Path) -> SpecRegistry:
    """创建 SpecRegistry（SHC-011~014 不使用它，但 check() 签名需要）"""
    return SpecRegistry(workspace)


def _write_pm_session(
    project: Path,
    sections: dict[str, str],
    filename: str = "PM_SESSION_TEST-2026-001.md",
) -> Path:
    """写入 PM_SESSION 文件

    Args:
        project: 项目目录
        sections: {章节号: 章节内容} 字典
        filename: PM_SESSION 文件名
    """
    pm_path = project / filename
    content = f"# {pm_path.stem}\n\n"
    for section_num in sorted(sections.keys()):
        content += f"## {section_num}\n\n{sections[section_num]}\n\n"
    pm_path.write_text(content, encoding="utf-8")
    return pm_path


def _write_pyproject(project: Path, version: str) -> Path:
    """写入 pyproject.toml"""
    path = project / "pyproject.toml"
    path.write_text(
        f'[project]\nname = "test"\nversion = "{version}"\n', encoding="utf-8"
    )
    return path


def _write_changelog(project: Path, version: str, unreleased: bool = False) -> Path:
    """写入 CHANGELOG.md"""
    path = project / "CHANGELOG.md"
    content = "# Changelog\n\n"
    if unreleased:
        content += "## [Unreleased]\n\n- unreleased changes\n\n"
    content += f"## [{version}] - 2026-07-25\n\n- test entry\n"
    path.write_text(content, encoding="utf-8")
    return path


def _write_junit_xml(project: Path, tests: int, failures: int = 0) -> Path:
    """写入 junit xml 测试结果文件"""
    junit_dir = project / "coverage" / "junit"
    junit_dir.mkdir(parents=True, exist_ok=True)
    junit_path = junit_dir / "test-results.xml"
    # 使用字符串拼接避免 XML 转义问题
    xml_content = (
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<testsuites tests="{tests}" failures="{failures}">\n'
        f'  <testsuite name="suite" tests="{tests}" failures="{failures}">\n'
        f"  </testsuite>\n"
        f"</testsuites>\n"
    )
    junit_path.write_text(xml_content, encoding="utf-8")
    return junit_path


# ── SHC-011 VersionConsistencyChecker ────────────────────


class TestVersionConsistencyChecker:
    """SHC-011: 版本号四件套一致性"""

    def test_all_versions_consistent(self, tmp_path: Path, project_dir: Path) -> None:
        """正向：pyproject=CHANGELOG=§2=§8 一致"""
        _write_pyproject(project_dir, "1.2.0")
        _write_changelog(project_dir, "1.2.0")
        _write_pm_session(project_dir, {
            "2": "- current_focus: 代码基线 V1.2.0",
            "8": "- current_state: 代码基线 V1.2.0 不变",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = VersionConsistencyChecker().check(reg, scanner)
        shc011 = [r for r in results if r.check_id == "SHC-011"]
        assert len(shc011) == 0

    def test_pyproject_changelog_mismatch(
        self, tmp_path: Path, project_dir: Path
    ) -> None:
        """负向：pyproject 1.2.0 vs CHANGELOG 1.1.0"""
        _write_pyproject(project_dir, "1.2.0")
        _write_changelog(project_dir, "1.1.0")
        _write_pm_session(project_dir, {
            "2": "- current_focus: 代码基线 V1.2.0",
            "8": "- current_state: 代码基线 V1.2.0 不变",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = VersionConsistencyChecker().check(reg, scanner)
        shc011 = [r for r in results if r.check_id == "SHC-011"]
        assert len(shc011) >= 1
        assert any("CHANGELOG.md" in r.message for r in shc011)
        assert all(r.severity == Severity.ERROR for r in shc011)

    def test_pm_session_section2_mismatch(
        self, tmp_path: Path, project_dir: Path
    ) -> None:
        """负向：§2 版本号与 pyproject 不一致"""
        _write_pyproject(project_dir, "1.2.0")
        _write_changelog(project_dir, "1.2.0")
        _write_pm_session(project_dir, {
            "2": "- current_focus: 代码基线 V0.9.0",
            "8": "- current_state: 代码基线 V1.2.0 不变",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = VersionConsistencyChecker().check(reg, scanner)
        shc011 = [r for r in results if r.check_id == "SHC-011"]
        assert any("PM_SESSION §2" in r.message for r in shc011)

    def test_pm_session_section8_missing_version(
        self, tmp_path: Path, project_dir: Path
    ) -> None:
        """负向：§8 缺少版本号声明"""
        _write_pyproject(project_dir, "1.2.0")
        _write_changelog(project_dir, "1.2.0")
        _write_pm_session(project_dir, {
            "2": "- current_focus: 代码基线 V1.2.0",
            "8": "- current_state: 无版本号声明",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = VersionConsistencyChecker().check(reg, scanner)
        shc011 = [r for r in results if r.check_id == "SHC-011"]
        assert any("PM_SESSION §8" in r.message and "未找到" in r.message for r in shc011)

    def test_changelog_unreleased_skipped(
        self, tmp_path: Path, project_dir: Path
    ) -> None:
        """正向：CHANGELOG 含 [Unreleased] 时应跳过取第一个真实版本"""
        _write_pyproject(project_dir, "1.2.0")
        _write_changelog(project_dir, "1.2.0", unreleased=True)
        _write_pm_session(project_dir, {
            "2": "- current_focus: 代码基线 V1.2.0",
            "8": "- current_state: 代码基线 V1.2.0 不变",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = VersionConsistencyChecker().check(reg, scanner)
        shc011 = [r for r in results if r.check_id == "SHC-011"]
        assert len(shc011) == 0

    def test_no_pyproject_skips_pyproject_check(
        self, tmp_path: Path, project_dir: Path
    ) -> None:
        """正向：非 Python 项目无 pyproject.toml 时不报 pyproject 错误"""
        _write_changelog(project_dir, "1.2.0")
        _write_pm_session(project_dir, {
            "2": "- current_focus: 代码基线 V1.2.0",
            "8": "- current_state: 代码基线 V1.2.0 不变",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = VersionConsistencyChecker().check(reg, scanner)
        shc011 = [r for r in results if r.check_id == "SHC-011"]
        assert len(shc011) == 0


# ── SHC-012 TestCountConsistencyChecker ───────────────────


class TestTestCountConsistencyChecker:
    """SHC-012: 测试数一致性"""

    def test_counts_match(self, tmp_path: Path, project_dir: Path) -> None:
        """正向：§3 声明 100 passed，junit xml tests=100"""
        _write_junit_xml(project_dir, tests=100)
        _write_pm_session(project_dir, {
            "3": "- completed: pytest 100 passed in 10s",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = TestCountConsistencyChecker().check(reg, scanner)
        shc012 = [r for r in results if r.check_id == "SHC-012"]
        assert len(shc012) == 0

    def test_counts_mismatch(self, tmp_path: Path, project_dir: Path) -> None:
        """负向：§3 声明 100 passed，junit xml tests=95"""
        _write_junit_xml(project_dir, tests=95)
        _write_pm_session(project_dir, {
            "3": "- completed: pytest 100 passed in 10s",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = TestCountConsistencyChecker().check(reg, scanner)
        shc012 = [r for r in results if r.check_id == "SHC-012"]
        assert len(shc012) == 1
        assert "100" in shc012[0].message and "95" in shc012[0].message
        assert shc012[0].severity == Severity.WARNING

    def test_no_junit_xml(self, tmp_path: Path, project_dir: Path) -> None:
        """负向：无 junit xml 文件"""
        _write_pm_session(project_dir, {
            "3": "- completed: pytest 100 passed in 10s",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = TestCountConsistencyChecker().check(reg, scanner)
        shc012 = [r for r in results if r.check_id == "SHC-012"]
        assert len(shc012) == 1
        assert "未找到" in shc012[0].message

    def test_no_test_declaration_skipped(
        self, tmp_path: Path, project_dir: Path
    ) -> None:
        """正向：§3 无测试数声明时跳过"""
        _write_junit_xml(project_dir, tests=100)
        _write_pm_session(project_dir, {
            "3": "- completed: 无测试相关内容",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = TestCountConsistencyChecker().check(reg, scanner)
        shc012 = [r for r in results if r.check_id == "SHC-012"]
        assert len(shc012) == 0

    def test_multiple_declarations_uses_last(
        self, tmp_path: Path, project_dir: Path
    ) -> None:
        """正向：§3 有多个 pytest N passed 声明时取最后一个（最新）"""
        _write_junit_xml(project_dir, tests=150)
        _write_pm_session(project_dir, {
            "3": (
                "- completed: pytest 100 passed\n"
                "- completed: pytest 120 passed\n"
                "- completed: pytest 150 passed"
            ),
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = TestCountConsistencyChecker().check(reg, scanner)
        shc012 = [r for r in results if r.check_id == "SHC-012"]
        assert len(shc012) == 0


# ── SHC-013 VerificationStatusChecker ─────────────────────


class TestVerificationStatusChecker:
    """SHC-013: 验证状态标注"""

    def test_has_verified_marker(self, tmp_path: Path, project_dir: Path) -> None:
        """正向：§8 包含 [已验证] 标注"""
        _write_pm_session(project_dir, {
            "8": "- current_state: 代码基线 V1.2.0 不变 [已验证]",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = VerificationStatusChecker().check(reg, scanner)
        shc013 = [r for r in results if r.check_id == "SHC-013"]
        assert len(shc013) == 0

    def test_has_pending_marker(self, tmp_path: Path, project_dir: Path) -> None:
        """正向：§8 包含 [待验证] 标注"""
        _write_pm_session(project_dir, {
            "8": "- current_state: 某结论 [待验证]",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = VerificationStatusChecker().check(reg, scanner)
        shc013 = [r for r in results if r.check_id == "SHC-013"]
        assert len(shc013) == 0

    def test_no_marker(self, tmp_path: Path, project_dir: Path) -> None:
        """负向：§8 无任何验证状态标注"""
        _write_pm_session(project_dir, {
            "8": "- current_state: 代码基线 V1.2.0 不变",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = VerificationStatusChecker().check(reg, scanner)
        shc013 = [r for r in results if r.check_id == "SHC-013"]
        assert len(shc013) == 1
        assert "缺少验证状态标注" in shc013[0].message
        assert shc013[0].severity == Severity.WARNING

    def test_no_section8_skipped(self, tmp_path: Path, project_dir: Path) -> None:
        """正向：无 §8 章节时跳过"""
        _write_pm_session(project_dir, {
            "2": "- current_focus: test",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = VerificationStatusChecker().check(reg, scanner)
        shc013 = [r for r in results if r.check_id == "SHC-013"]
        assert len(shc013) == 0


# ── SHC-014 DocIndexValidityChecker ───────────────────────


class TestDocIndexValidityChecker:
    """SHC-014: 文档索引有效性"""

    def test_all_docs_present_and_valid(
        self, tmp_path: Path, project_dir: Path
    ) -> None:
        """正向：req/int/dsn/tec 四类文档齐全且路径有效"""
        design_dir = project_dir / "02_设计"
        design_dir.mkdir()
        (design_dir / "001_产品需求文档_PRD.md").write_text("# PRD", encoding="utf-8")
        (design_dir / "002_接口文档_INT.md").write_text("# INT", encoding="utf-8")
        (design_dir / "003_详细设计说明书_DSN.md").write_text("# DSN", encoding="utf-8")
        (design_dir / "004_技术方案文档_TEC.md").write_text("# TEC", encoding="utf-8")
        _write_pm_session(project_dir, {
            "4": (
                "- req: 02_设计/001_产品需求文档_PRD.md\n"
                "- int: 02_设计/002_接口文档_INT.md\n"
                "- dsn: 02_设计/003_详细设计说明书_DSN.md\n"
                "- tec: 02_设计/004_技术方案文档_TEC.md\n"
            ),
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = DocIndexValidityChecker().check(reg, scanner)
        shc014 = [r for r in results if r.check_id == "SHC-014"]
        assert len(shc014) == 0

    def test_missing_doc_type(self, tmp_path: Path, project_dir: Path) -> None:
        """负向：缺少 tec 文档索引"""
        design_dir = project_dir / "02_设计"
        design_dir.mkdir()
        (design_dir / "001_产品需求文档_PRD.md").write_text("# PRD", encoding="utf-8")
        (design_dir / "002_接口文档_INT.md").write_text("# INT", encoding="utf-8")
        (design_dir / "003_详细设计说明书_DSN.md").write_text("# DSN", encoding="utf-8")
        _write_pm_session(project_dir, {
            "4": (
                "- req: 02_设计/001_产品需求文档_PRD.md\n"
                "- int: 02_设计/002_接口文档_INT.md\n"
                "- dsn: 02_设计/003_详细设计说明书_DSN.md\n"
            ),
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = DocIndexValidityChecker().check(reg, scanner)
        shc014 = [r for r in results if r.check_id == "SHC-014"]
        assert any("缺少必需文档索引" in r.message and "tec" in r.message for r in shc014)
        assert all(r.severity == Severity.ERROR for r in shc014)

    def test_invalid_path(self, tmp_path: Path, project_dir: Path) -> None:
        """负向：文档路径不存在"""
        _write_pm_session(project_dir, {
            "4": (
                "- req: 02_设计/不存在.md\n"
                "- int: 02_设计/002_接口文档_INT.md\n"
                "- dsn: 02_设计/003_详细设计说明书_DSN.md\n"
                "- tec: 02_设计/004_技术方案文档_TEC.md\n"
            ),
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = DocIndexValidityChecker().check(reg, scanner)
        shc014 = [r for r in results if r.check_id == "SHC-014"]
        assert any("req" in r.message and "路径无效" in r.message for r in shc014)

    def test_no_section4_skipped(self, tmp_path: Path, project_dir: Path) -> None:
        """正向：无 §4 Artifacts Index 章节时跳过"""
        _write_pm_session(project_dir, {
            "2": "- current_focus: test",
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = DocIndexValidityChecker().check(reg, scanner)
        shc014 = [r for r in results if r.check_id == "SHC-014"]
        assert len(shc014) == 0

    def test_http_path_skipped(self, tmp_path: Path, project_dir: Path) -> None:
        """正向：http 开头的路径跳过有效性检查"""
        _write_pm_session(project_dir, {
            "4": (
                "- req: https://example.com/prd.md\n"
                "- int: 02_设计/002_接口文档_INT.md\n"
                "- dsn: 02_设计/003_详细设计说明书_DSN.md\n"
                "- tec: 02_设计/004_技术方案文档_TEC.md\n"
            ),
        })
        design_dir = project_dir / "02_设计"
        design_dir.mkdir()
        (design_dir / "002_接口文档_INT.md").write_text("# INT", encoding="utf-8")
        (design_dir / "003_详细设计说明书_DSN.md").write_text("# DSN", encoding="utf-8")
        (design_dir / "004_技术方案文档_TEC.md").write_text("# TEC", encoding="utf-8")
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = DocIndexValidityChecker().check(reg, scanner)
        shc014 = [r for r in results if r.check_id == "SHC-014"]
        # req 是 http 路径不检查，其他三个路径有效，应无报错
        assert len(shc014) == 0

    def test_legacy_file_index_can_discover_root_prd_docs(
        self, tmp_path: Path, project_dir: Path
    ) -> None:
        """正向：旧版 File Index + 根目录 PRD 四件套也应被兼容"""
        prd_dir = project_dir / "PRD"
        prd_dir.mkdir()
        (prd_dir / "需求分析文档_REQ.md").write_text("# REQ", encoding="utf-8")
        (prd_dir / "接口文档_INT.md").write_text("# INT", encoding="utf-8")
        (prd_dir / "详细设计说明书_DSN.md").write_text("# DSN", encoding="utf-8")
        (prd_dir / "技术方案文档_TEC.md").write_text("# TEC", encoding="utf-8")
        _write_pm_session(project_dir, {
            "4": (
                "- 02_PLC程序/PLC_ST/: PLC 程序源码\n"
                "- PRD/: 项目需求文档\n"
            ),
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = DocIndexValidityChecker().check(reg, scanner)
        shc014 = [r for r in results if r.check_id == "SHC-014"]
        assert len(shc014) == 0

    def test_placeholder_doc_paths_are_skipped_without_invalid_path_errors(
        self, tmp_path: Path, project_dir: Path
    ) -> None:
        """负向：占位路径应跳过路径校验，但仍报告缺失的文档类型"""
        design_dir = project_dir / "02_设计"
        design_dir.mkdir()
        (design_dir / "001_产品需求文档_PRD.md").write_text("# PRD", encoding="utf-8")
        _write_pm_session(project_dir, {
            "4": (
                "- req: 02_设计/001_产品需求文档_PRD.md\n"
                "- int: (待创建)\n"
                "- dsn: 待补充\n"
                "- tec: {PRD_DIR}/004_技术方案文档_TEC.md\n"
            ),
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = DocIndexValidityChecker().check(reg, scanner)
        shc014 = [r for r in results if r.check_id == "SHC-014"]
        assert len(shc014) == 1
        assert "缺少必需文档索引" in shc014[0].message
        assert "int" in shc014[0].message
        assert "dsn" in shc014[0].message
        assert "tec" in shc014[0].message
        assert all("路径无效" not in r.message for r in shc014)

    def test_template_pm_session_is_skipped(
        self, tmp_path: Path, project_dir: Path
    ) -> None:
        """正向：模板 PM_SESSION 文件应跳过 SHC-014 检查"""
        _write_pm_session(
            project_dir,
            {
                "4": (
                    "- req: 待补充\n"
                    "- int: 待补充\n"
                    "- dsn: 待补充\n"
                    "- tec: 待补充\n"
                ),
            },
            filename="PM_SESSION_TEMPLATE.md",
        )
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = DocIndexValidityChecker().check(reg, scanner)
        shc014 = [r for r in results if r.check_id == "SHC-014"]
        assert len(shc014) == 0

    def test_prd_alias_is_accepted_as_req(
        self, tmp_path: Path, project_dir: Path
    ) -> None:
        """正向：prd 条目应作为 req 的兼容别名处理"""
        design_dir = project_dir / "02_设计"
        design_dir.mkdir()
        (design_dir / "001_产品需求文档_PRD.md").write_text("# PRD", encoding="utf-8")
        (design_dir / "002_接口文档_INT.md").write_text("# INT", encoding="utf-8")
        (design_dir / "003_详细设计说明书_DSN.md").write_text("# DSN", encoding="utf-8")
        (design_dir / "004_技术方案文档_TEC.md").write_text("# TEC", encoding="utf-8")
        _write_pm_session(project_dir, {
            "4": (
                "- prd: 02_设计/001_产品需求文档_PRD.md\n"
                "- int: 02_设计/002_接口文档_INT.md\n"
                "- dsn: 02_设计/003_详细设计说明书_DSN.md\n"
                "- tec: 02_设计/004_技术方案文档_TEC.md\n"
            ),
        })
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = DocIndexValidityChecker().check(reg, scanner)
        shc014 = [r for r in results if r.check_id == "SHC-014"]
        assert len(shc014) == 0

    def test_component_pm_session_is_skipped(
        self, tmp_path: Path, project_dir: Path
    ) -> None:
        """正向：FB 组件级 PM_SESSION 不应按项目四件套校验"""
        _write_pm_session(project_dir, {
            "4": (
                "- req: PRD/需求分析文档_REQ.md\n"
                "- tec: PRD/技术方案文档_TEC.md\n"
            ),
        }, filename="PM_SESSION_FB1012.md")
        scanner = _make_scanner(tmp_path, project_dir)
        reg = _make_registry(tmp_path)
        results = DocIndexValidityChecker().check(reg, scanner)
        shc014 = [r for r in results if r.check_id == "SHC-014"]
        assert len(shc014) == 0
