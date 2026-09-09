from __future__ import annotations

from pathlib import Path

from auto_pm.spec.core.checker_base import (
    HealthChecker,
    Severity,
    SkillContractDriftChecker,
)
from auto_pm.spec.core.registry import SpecRegistry
from auto_pm.spec.core.scanner import SpecScanner
from auto_pm.spec.core.skill_contracts import SKILL_CONTRACTS


def _write_correct_skill_docs(workspace: Path) -> None:
    """在 workspace 下创建满足活动契约的假技能文档。"""
    skills = workspace / ".trae" / "skills"
    fs_dir = skills / "fullstack-engineer"
    fs_dir.mkdir(parents=True, exist_ok=True)
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

    def test_active_contracts_do_not_reference_pm_workflow(self) -> None:
        """已弃用的 pm-workflow 不得再次进入活动门禁契约。"""
        assert all(
            "pm-workflow" not in relpath
            for contract in SKILL_CONTRACTS
            for relpath in contract.doc_relpaths
        )

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
