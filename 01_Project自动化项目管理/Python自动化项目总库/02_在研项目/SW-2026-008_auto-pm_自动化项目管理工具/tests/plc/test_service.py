"""PlcService 单元测试（M3-Iter4）

验证 PlcService 封装 PlcChecker/PlcRepairer/SubstanceChecker 的统一入口。
"""

from __future__ import annotations

import json
from pathlib import Path

from auto_pm.application.core.protocols import PlcServiceProtocol
from auto_pm.domain.plc.service import PlcService


class TestPlcServiceProtocolConformance:
    """验证 PlcService 实现 PlcServiceProtocol"""

    def test_plc_service_implements_protocol(self, tmp_path: Path) -> None:
        """PlcService 实现 PlcServiceProtocol"""
        svc = PlcService(str(tmp_path))
        assert isinstance(svc, PlcServiceProtocol)

    def test_plc_service_has_required_methods(self, tmp_path: Path) -> None:
        """PlcService 包含 Protocol 定义的所有方法"""
        svc = PlcService(str(tmp_path))
        required_methods = ["check", "repair", "standardize"]
        for method_name in required_methods:
            assert callable(getattr(svc, method_name, None)), (
                f"PlcService 缺少方法: {method_name}"
            )


class TestPlcServiceCheck:
    """PlcService.check 测试"""

    def test_check_returns_check_result(self, tmp_path: Path) -> None:
        """check 返回 CheckResult"""
        # 创建一个简单的 PLC 项目
        project_dir = tmp_path / "DJ-2026-001_PLC项目"
        project_dir.mkdir()
        (project_dir / ".plc.json").write_text(
            json.dumps(
                {
                    "name": "DJ-2026-001",
                    "description": "测试 PLC 项目",
                    "version": "V1.0.0",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        svc = PlcService(str(tmp_path))
        result = svc.check(str(project_dir))

        assert result.project_path == str(project_dir)
        # 应该有检查项
        assert len(result.items) > 0

    def test_check_with_fix_flag(self, tmp_path: Path) -> None:
        """check(fix=True) 在有 fail 时自动修复"""
        project_dir = tmp_path / "DJ-2026-002_问题项目"
        project_dir.mkdir()
        # 只创建 .plc.json，不创建标准目录（会有 fail 项）
        (project_dir / ".plc.json").write_text(
            json.dumps(
                {
                    "name": "DJ-2026-002",
                    "description": "测试",
                    "version": "V1.0.0",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        svc = PlcService(str(tmp_path))
        svc.check(str(project_dir), fix=True)

        # 修复后应创建标准目录（CHG-SCPT-2026-146: 01_启动 替代 00_项目管理）
        assert (project_dir / "01_启动").is_dir()


class TestPlcServiceRepair:
    """PlcService.repair 测试"""

    def test_repair_dry_run(self, tmp_path: Path) -> None:
        """repair(dry_run=True) 不实际修改文件"""
        project_dir = tmp_path / "DJ-2026-003_测试项目"
        project_dir.mkdir()
        (project_dir / ".plc.json").write_text(
            json.dumps(
                {"name": "DJ-2026-003", "description": "测试", "version": "V1.0.0"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        svc = PlcService(str(tmp_path))
        result = svc.repair(str(project_dir), dry_run=True)

        assert result.project_path == str(project_dir)
        # dry_run 模式下不应创建目录
        assert not (project_dir / "00_项目管理").exists()


class TestPlcServiceStandardize:
    """PlcService.standardize 测试"""

    def test_standardize_dry_run(self, tmp_path: Path) -> None:
        """standardize(dry_run=True) 不实际重命名"""
        project_dir = tmp_path / "DJ-2026-004_测试项目"
        project_dir.mkdir()
        (project_dir / "PRD").mkdir()
        # 创建一个非标准命名的文档
        (project_dir / "PRD" / "需求文档_PRD-001.md").write_text(
            "# 需求文档\n\n内容", encoding="utf-8"
        )

        svc = PlcService(str(tmp_path))
        result = svc.standardize(str(project_dir), dry_run=True)

        assert result.project_path == str(project_dir)
        # dry_run 模式下原文件应仍存在
        assert (project_dir / "PRD" / "需求文档_PRD-001.md").exists()


class TestPlcServiceCheckSubstance:
    """PlcService.check_substance 测试"""

    def test_check_substance_returns_check_result(self, tmp_path: Path) -> None:
        """check_substance 返回 CheckResult"""
        project_dir = tmp_path / "DJ-2026-005_测试项目"
        project_dir.mkdir()
        (project_dir / "PRD").mkdir()
        # 创建一个空壳文档
        (project_dir / "PRD" / "需求分析文档_REQ.md").write_text(
            "# 需求分析\n\n待补充", encoding="utf-8"
        )

        svc = PlcService(str(tmp_path))
        result = svc.check_substance(str(project_dir))

        assert result.project_path == str(project_dir)
