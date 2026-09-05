from __future__ import annotations

from pathlib import Path

from auto_pm.spec.core.checker_base import (
    HealthChecker,
    Severity,
    SkillContractDriftChecker,
)
from auto_pm.spec.core.registry import SpecRegistry
from auto_pm.spec.core.scanner import SpecScanner


def _write_correct_skill_docs(workspace: Path) -> None:
    """在 workspace 下创建含「正确」真源值的假技能文档。

    真源值直接从代码模块读取，避免硬编码导致与契约清单脱节。
    """
    from auto_pm.application.core.paths import PG_CLOSING_DIR
    from auto_pm.application.core.pm_session_service import (
        ARCHIVE_DIR_NAME,
        MAX_FILE_LINES,
        MAX_FILE_SIZE_KB,
    )
    from auto_pm.domain.change.constants import STATUS_FLOW

    skills = workspace / ".trae" / "skills"
    pm_refs = skills / "pm-workflow" / "refs"
    pm_refs.mkdir(parents=True, exist_ok=True)
    fs_dir = skills / "fullstack-engineer"
    fs_dir.mkdir(parents=True, exist_ok=True)

    gates_content = (
        "# 状态机\n\n"
        f"{' '.join(sorted(STATUS_FLOW.keys()))}\n\n"
        "门禁: ruff check mypy pytest --no-cov -q 改动文件\n"
    )

    (pm_refs / "pm_session_guide.md").write_text(
        "# PM_SESSION 指南\n\n"
        f"阈值: {MAX_FILE_SIZE_KB}KB / {MAX_FILE_LINES}行\n"
        f"归档目录: {ARCHIVE_DIR_NAME} (位于 {PG_CLOSING_DIR})\n",
        encoding="utf-8",
    )
    (pm_refs / "process_gates.md").write_text(gates_content, encoding="utf-8")
    (pm_refs / "handoff_schema.md").write_text(
        "# Handoff Schema\n\n变更编号格式: CHG-{DOMAIN}-{YYYY}-{XXX}\n",
        encoding="utf-8",
    )
    (fs_dir / "SKILL.md").write_text(
        "# SKILL\n\n门禁: ruff check mypy pytest --no-cov -q 改动文件\n",
        encoding="utf-8",
    )


class TestSkillContractDriftChecker:
    def test_no_docs_returns_empty(self, populated_workspace: Path) -> None:
        """populated_workspace 默认无 .trae/skills，文档缺失应 SKIP（无结果）。"""
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = SkillContractDriftChecker()
        results = checker.check(reg, scanner)
        shc017 = [r for r in results if r.check_id == "SHC-017"]
        assert len(shc017) == 0

    def test_no_drift_when_docs_correct(self, populated_workspace: Path) -> None:
        """技能文档含全部正确真源值时，不产生 SHC-017 漂移。"""
        _write_correct_skill_docs(populated_workspace)
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = SkillContractDriftChecker()
        results = checker.check(reg, scanner)
        shc017 = [r for r in results if r.check_id == "SHC-017"]
        assert len(shc017) == 0

    def test_detects_value_drift(self, populated_workspace: Path) -> None:
        """篡改阈值真源值（150 → 999），应报 C1 漂移且 severity=ERROR。"""
        _write_correct_skill_docs(populated_workspace)
        guide = populated_workspace / ".trae/skills/pm-workflow/refs/pm_session_guide.md"
        guide.write_text(
            "# PM_SESSION 指南\n\n阈值: 999KB / 300行\n归档目录: PM_SESSION归档 (位于 05_收尾)\n",
            encoding="utf-8",
        )
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = SkillContractDriftChecker()
        results = checker.check(reg, scanner)
        shc017 = [r for r in results if r.check_id == "SHC-017"]
        assert len(shc017) >= 1
        assert all(r.severity == Severity.ERROR for r in shc017)
        assert any("C1" in r.message for r in shc017)
        assert any("150" in r.message for r in shc017)

    def test_detects_keys_drift(self, populated_workspace: Path) -> None:
        """删除一个状态名，应报 C2 漂移且 severity=ERROR。"""
        _write_correct_skill_docs(populated_workspace)
        from auto_pm.domain.change.constants import STATUS_FLOW

        states = sorted(STATUS_FLOW.keys())
        removed = states[-1]
        gates = populated_workspace / ".trae/skills/pm-workflow/refs/process_gates.md"
        gates.write_text(
            "# 状态机\n\n"
            f"{' '.join(states[:-1])}\n\n"
            "门禁: ruff check mypy pytest --no-cov -q 改动文件\n",
            encoding="utf-8",
        )
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = SkillContractDriftChecker()
        results = checker.check(reg, scanner)
        shc017 = [r for r in results if r.check_id == "SHC-017"]
        assert len(shc017) >= 1
        assert all(r.severity == Severity.ERROR for r in shc017)
        assert any(removed in r.message for r in shc017)

    def test_literal_drift_warning(self, populated_workspace: Path) -> None:
        """删除门禁字面量 ruff check，应报 C4 漂移且 severity=WARNING。"""
        _write_correct_skill_docs(populated_workspace)
        skill = populated_workspace / ".trae/skills/fullstack-engineer/SKILL.md"
        skill.write_text(
            "# SKILL\n\n门禁: mypy pytest --no-cov -q 改动文件\n",
            encoding="utf-8",
        )
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        checker = SkillContractDriftChecker()
        results = checker.check(reg, scanner)
        shc017 = [r for r in results if r.check_id == "SHC-017"]
        assert len(shc017) >= 1
        assert any(r.severity == Severity.WARNING for r in shc017)
        assert any("ruff check" in r.message for r in shc017)

    def test_registered_in_health_checker(self, populated_workspace: Path) -> None:
        """SHC-017 应被 HealthChecker.run_by_id 正确调度（已注册）。"""
        reg = SpecRegistry(populated_workspace)
        reg.load()
        scanner = SpecScanner(populated_workspace)
        hc = HealthChecker()
        results = hc.run_by_id("SHC-017", reg, scanner)
        assert isinstance(results, list)
