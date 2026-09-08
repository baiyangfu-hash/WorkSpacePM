"""Unit tests for PlcIngestService in auto_pm (SW-2026-008)."""

import csv
import tempfile
from pathlib import Path

from auto_pm.application.plc.ingest_service import PlcIngestService


def test_plc_ingest_service_basic():
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
