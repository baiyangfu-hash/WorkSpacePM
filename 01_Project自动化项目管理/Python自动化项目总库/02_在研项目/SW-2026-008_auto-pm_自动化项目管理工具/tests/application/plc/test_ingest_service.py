"""Unit tests for PlcIngestService in auto_pm (SW-2026-008)."""

import csv
import tempfile
from pathlib import Path

from auto_pm.application.plc.ingest_service import PlcIngestService


def test_plc_ingest_service_basic() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        src_dir = ws / "src_autoshop"
        plc_dir = src_dir / "2_PLC"
        plc_dir.mkdir(parents=True, exist_ok=True)

        # 模拟 AutoShop GVT CSV 变量表
        csv_file = plc_dir / "AlarmTable.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Name", "Type", "Address", "Comment"])
            writer.writerow(["g_bEStopAlarm", "BOOL", "M100.0", "急停报警触发"])
            writer.writerow(["g_rXPosActual", "REAL", "D1000", "移载X轴实际坐标"])


        target_proj = ws / "0100_PLC自动化" / "DJ-TEST-001"
        target_proj.mkdir(parents=True, exist_ok=True)

        service = PlcIngestService(workspace_root=str(ws))
        res = service.ingest_autoshop_project(
            source_dir=str(src_dir),
            target_project_path=str(target_proj),
            project_id="DJ-TEST-001",
            project_name="测试码垛机",
        )

        assert res.success is True
        assert res.total_variables == 2
        assert res.total_alarms >= 1
        assert len(res.generated_files) >= 5

        # 验证生成的资产文件存在
        assert (target_proj / "02_PLC程序" / "工程资产" / "io_points.csv").exists()
        assert (target_proj / "02_PLC程序" / "工程资产" / "communications.yml").exists()
        assert (target_proj / "02_PLC程序" / "程序文档" / "015_DJ-TEST-001_IO分配表_IO.md").exists()


# 以下钉住：摄取只写源工程变量表里读得到的东西，不编控制器、总线、IP、设备和工艺（演示机的拓扑曾被写进每个摄取的项目）
INVENTED = ("H5U", "GL20", "IS620N", "SV660N", "192.168.", "EtherCAT", "龙门", "码垛", "隔纸", "托盘", "Inovance", "汇川")


def _ingest(ws: Path, *, keep_comm: str | None = None) -> Path:
    src = ws / "src" / "2_PLC"
    src.mkdir(parents=True)
    with open(src / "IO表.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Type", "Address", "Comment"])
        writer.writerow(["I_Start", "BOOL", "X0", "启动按钮"])
        writer.writerow(["Q_Lamp", "BOOL", "Y0", "运行灯"])
    project = ws / "0100_PLC自动化" / "DJ-TEST-002"
    project.mkdir(parents=True)
    if keep_comm is not None:
        assets = project / "02_PLC程序" / "工程资产"
        assets.mkdir(parents=True)
        (assets / "communications.yml").write_text(keep_comm, encoding="utf-8")
    PlcIngestService(workspace_root=str(ws)).ingest_autoshop_project(
        source_dir=str(ws / "src"), target_project_path=str(project), project_id="DJ-TEST-002", project_name="测试机"
    )
    return project


def test_ingest_writes_no_invented_hardware_or_process(tmp_path: Path) -> None:
    project = _ingest(tmp_path)
    found = []
    for path in (project / "02_PLC程序").rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            found += [(path.name, word) for word in INVENTED if word in text]
    assert found == []


def test_ingest_communications_file_uses_the_channels_list_the_readers_expect(tmp_path: Path) -> None:
    import yaml

    from auto_pm.application.core.asset_summary_service import AssetSummaryService

    project = _ingest(tmp_path)
    data = yaml.safe_load((project / "02_PLC程序" / "工程资产" / "communications.yml").read_text(encoding="utf-8"))
    assert data == {"project_id": "DJ-TEST-002", "channels": []}
    summary = AssetSummaryService().build_summary(str(project), "plc")["communications"]
    assert summary["exists"] and summary["valid"], summary


def test_ingest_keeps_an_existing_communications_file(tmp_path: Path) -> None:
    mine = 'project_id: "DJ-TEST-002"\nchannels:\n  - name: "HMI"\n    endpoint: "人填的"\n'
    project = _ingest(tmp_path, keep_comm=mine)
    assert (project / "02_PLC程序" / "工程资产" / "communications.yml").read_text(encoding="utf-8") == mine
