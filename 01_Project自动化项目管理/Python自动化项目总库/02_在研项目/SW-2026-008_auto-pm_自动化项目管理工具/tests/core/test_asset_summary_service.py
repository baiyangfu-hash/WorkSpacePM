"""工程资产摘要服务测试"""

from __future__ import annotations

from pathlib import Path

from auto_pm.application.core.asset_summary_service import AssetSummaryService


def _write_asset_files(asset_dir: Path) -> None:
    asset_dir.mkdir(parents=True)
    (asset_dir / "io_points.csv").write_text(
        "\n".join(
            [
                "station,signal_type,address,tag,signal_name,device,comment",
                "common,DI,I0.0,ESTOP_OK,急停回路正常,操作台,TRUE=安全链路闭合",
                "conveyor,DO,Q0.0,CONVEYOR_RUN,输送带运行,变频器,TRUE=正转运行",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (asset_dir / "program_blocks.yml").write_text(
        "\n".join(
            [
                "blocks:",
                '  - name: "OB1"',
                '    type: "OB"',
                '    path: "02_PLC程序/PLC_ST/OB1/OB1.scl"',
                '    responsibility: "主循环与调用编排"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (asset_dir / "communications.yml").write_text(
        "\n".join(
            [
                "channels:",
                '  - name: "HMI"',
                '    protocol: "ethernet"',
                '    role: "人机界面"',
                '    endpoint: "Siemens S7-1200"',
                '    notes: "补齐 IP、端口和变量映射"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_build_summary_for_valid_plc_assets(tmp_path: Path) -> None:
    """有效的三类工程资产应返回健康摘要"""
    project_dir = tmp_path / "DJ-2026-030_资产项目"
    asset_dir = project_dir / "02_PLC程序" / "工程资产"
    _write_asset_files(asset_dir)

    service = AssetSummaryService()
    summary = service.build_summary(str(project_dir), stack="plc", project_type="single_machine")

    assert summary["status"] == "healthy"
    assert summary["asset_dir_exists"] is True
    assert summary["io_points"]["count"] == 2
    assert summary["program_blocks"]["count"] == 1
    assert summary["communications"]["count"] == 1
    assert summary["total_issues"] == 0


def test_build_summary_reports_missing_columns_and_files(tmp_path: Path) -> None:
    """缺列和缺文件应返回 warning/missing 问题摘要"""
    project_dir = tmp_path / "DJ-2026-031_异常资产项目"
    asset_dir = project_dir / "02_PLC程序" / "工程资产"
    asset_dir.mkdir(parents=True)
    (asset_dir / "io_points.csv").write_text(
        "\n".join(
            [
                "station,signal_type,address,tag",
                "common,DI,I0.0,ESTOP_OK",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (asset_dir / "program_blocks.yml").write_text("blocks:\n  - name: OB1\n", encoding="utf-8")

    service = AssetSummaryService()
    summary = service.build_summary(str(project_dir), stack="plc", project_type="single_machine")

    assert summary["status"] == "missing"
    assert summary["io_points"]["valid"] is False
    assert "io_points.csv 缺少列" in summary["io_points"]["issues"][0]
    assert summary["program_blocks"]["valid"] is False
    assert "program_blocks.yml 第 1 项缺少字段" in summary["program_blocks"]["issues"][0]
    assert summary["communications"]["exists"] is False
    assert summary["total_issues"] == 3


def test_build_summary_returns_not_applicable_for_python_project(tmp_path: Path) -> None:
    """非 PLC 项目返回不适用摘要"""
    service = AssetSummaryService()
    summary = service.build_summary(str(tmp_path), stack="python", project_type="")

    assert summary["status"] == "not_applicable"
    assert summary["total_issues"] == 0
