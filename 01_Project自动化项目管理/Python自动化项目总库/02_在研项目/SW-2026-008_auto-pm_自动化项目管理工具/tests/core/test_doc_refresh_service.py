"""文档自动区刷新服务测试"""

from __future__ import annotations

from pathlib import Path

import yaml
from auto_pm.core.doc_refresh_service import DocRefreshService
from auto_pm.models import ProjectInfo


def _setup_doc_project(tmp_path: Path) -> tuple[ProjectInfo, Path, Path]:
    project_dir = tmp_path / "DJ-2026-040_文档刷新项目"
    asset_dir = project_dir / "02_PLC程序" / "工程资产"
    doc_dir = project_dir / "02_PLC程序" / "程序文档"
    asset_dir.mkdir(parents=True)
    doc_dir.mkdir(parents=True)

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
        yaml.safe_dump(
            {
                "blocks": [
                    {
                        "name": "OB1",
                        "type": "OB",
                        "path": "02_PLC程序/PLC_ST/OB1/OB1.scl",
                        "responsibility": "主循环与调用编排",
                    },
                    {
                        "name": "fbConveyor",
                        "type": "FB",
                        "path": "02_PLC程序/PLC_ST/conveyor/",
                        "responsibility": "输送设备控制",
                    },
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (asset_dir / "communications.yml").write_text(
        yaml.safe_dump(
            {
                "channels": [
                    {
                        "name": "HMI",
                        "protocol": "ethernet",
                        "role": "人机界面",
                        "endpoint": "Siemens S7-1200",
                        "notes": "补齐 IP、端口和变量映射",
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    program_doc = doc_dir / "016_DJ-2026-040_PLC程序设计总文档_PLC.md"
    program_doc.write_text(
        "\n".join(
            [
                "# PLC程序设计总文档",
                "",
                "## 4. 软件架构",
                "",
                "### 4.1 组件清单与职责",
                "",
                "<!-- AUTO_PM:BEGIN plc-program-components -->",
                "旧内容",
                "<!-- AUTO_PM:END plc-program-components -->",
                "",
                "## 8. 关联文档索引",
                "",
                "<!-- AUTO_PM:BEGIN plc-asset-index -->",
                "旧索引",
                "<!-- AUTO_PM:END plc-asset-index -->",
                "",
            ]
        ),
        encoding="utf-8",
    )
    io_doc = doc_dir / "015_DJ-2026-040_IO分配表_IO.md"
    io_doc.write_text(
        "\n".join(
            [
                "# IO分配表",
                "",
                "## 2. IO 总览",
                "",
                "<!-- AUTO_PM:BEGIN plc-io-overview -->",
                "旧IO概览",
                "<!-- AUTO_PM:END plc-io-overview -->",
                "",
            ]
        ),
        encoding="utf-8",
    )

    project = ProjectInfo(
        project_id="DJ-2026-040",
        name="文档刷新项目",
        path=str(project_dir),
        stack="plc",
        phase="developing",
        version="0.4.0",
        description="Week 4 文档自动区刷新测试项目",
        extra={},
    )
    return project, program_doc, io_doc


def test_refresh_project_documents_dry_run_does_not_modify_files(tmp_path: Path) -> None:
    """dry-run 仅预览，不修改文档"""
    project, program_doc, io_doc = _setup_doc_project(tmp_path)
    service = DocRefreshService(str(tmp_path))

    result = service.refresh_project_documents(project, dry_run=True)

    assert result.updated is False
    assert len(result.refreshed_files) == 2
    assert "旧内容" in program_doc.read_text(encoding="utf-8")
    assert "旧IO概览" in io_doc.read_text(encoding="utf-8")


def test_refresh_project_documents_updates_auto_blocks(tmp_path: Path) -> None:
    """实际刷新时只替换自动区"""
    project, program_doc, io_doc = _setup_doc_project(tmp_path)
    service = DocRefreshService(str(tmp_path))

    result = service.refresh_project_documents(project, dry_run=False)

    assert result.updated is True
    program_content = program_doc.read_text(encoding="utf-8")
    io_content = io_doc.read_text(encoding="utf-8")
    assert "旧内容" not in program_content
    assert "OB1" in program_content
    assert "io_points.csv" in program_content
    assert "旧IO概览" not in io_content
    assert "### 2.1 自动区刷新摘要" in io_content
    assert "common" in io_content


def _setup_realistic_doc_project(tmp_path: Path) -> tuple[ProjectInfo, Path, Path]:
    """构建贴近真实 PLC 项目规模的资产与文档（参考 DJ-2026-005 边框缓存机）。

    与 _setup_doc_project 的最小样本（2 IO / 2 blocks / 1 channel）不同，
    本 helper 使用 19 IO / 7 blocks / 5 channels 的真实规模样本，
    用于验证 doc refresh 在真实资产场景下的契约。
    """
    project_dir = tmp_path / "DJ-2026-005_边框缓存机"
    asset_dir = project_dir / "02_PLC程序" / "工程资产"
    doc_dir = project_dir / "02_PLC程序" / "程序文档"
    asset_dir.mkdir(parents=True)
    doc_dir.mkdir(parents=True)

    # IO 点表：覆盖 7 个工站（cpu/di_ext_1/di_ext_3/di_ext_4/do_ext_1/do_ext_2/remote_io_1）
    # 共 19 行数据（DI 11 + DO 8），对齐 DJ-2026-005 真实工站分布
    io_rows = [
        "station,signal_type,address,tag,signal_name,device,comment",
        "cpu,DI,X0,Z_Home_Sensor,Z轴原点,Z轴伺服,TRUE=原点到位",
        "cpu,DI,X16,E_Stop_Button,急停按钮,操作台,TRUE=急停按下",
        "cpu,DO,Y0,Z_Axis_Pulse,Z轴脉冲,SV0,脉冲输出",
        "cpu,DO,Y10,Z_Servo_EN,Z轴伺服励磁,SV0,TRUE=使能",
        "di_ext_1,DI,X10,Left_Door1_Status,左侧门1状态,SQ1,安全门反馈",
        "di_ext_1,DI,X11,Right_Door2_Status,右侧门2状态,SQ4,安全门反馈",
        "di_ext_3,DI,X0,L4_PreFeed_Sensor,4层分料前感应,4层分料,材料到达",
        "di_ext_3,DI,X1,Front_Door_Lock_B5,前安全门锁定,安全系统,冗余",
        "di_ext_3,DI,X10,L3_Discharge_Done,3层放料完成,3层分料,TRUE=完成",
        "di_ext_4,DI,X0,L2_Discharge_Done,2层放料完成,2层分料,TRUE=完成",
        "di_ext_4,DI,X10,L1_Discharge_Done,1层放料完成,1层分料,TRUE=完成",
        "do_ext_1,DO,Y0,L4_Block_Solenoid,4层阻挡电磁阀,YV1,TRUE=下降",
        "do_ext_1,DO,Y2,L4_Conveyor_FWD,4层输送正转,VF1,TRUE=正转",
        "do_ext_2,DO,Y0,L2_Block_Solenoid,2层阻挡电磁阀,YV5,TRUE=下降",
        "do_ext_2,DO,Y10,L1_Block_Solenoid,1层阻挡电磁阀,YV7,TRUE=下降",
        "remote_io_1,DI,X0,Lift_Cyl_MovPt1,升降气缸动点1,磁性开关,动点到位",
        "remote_io_1,DI,XC,LongEdge1_Detect,长边1检测,SICK IME08,TRUE=检测到",
        "remote_io_1,DO,Y10,Lift_Cyl_Up,升降气缸上升,YV1,TRUE=上升",
        "remote_io_1,DO,Y12,FrontGrip_Clamp,前夹紧气缸夹紧,YV3,TRUE=夹紧",
    ]
    (asset_dir / "io_points.csv").write_text("\n".join(io_rows) + "\n", encoding="utf-8")

    # 程序块清单：7 个块（OB1 + DB + 5 FB），对齐 DJ-2026-005 真实 PLC_ST 目录
    (asset_dir / "program_blocks.yml").write_text(
        yaml.safe_dump(
            {
                "project_id": "DJ-2026-005",
                "blocks": [
                    {
                        "name": "OB1",
                        "type": "OB",
                        "path": "02_PLC程序/PLC_ST/OB1/OB1.scl",
                        "responsibility": "主循环与调用编排",
                    },
                    {
                        "name": "GlobalVars",
                        "type": "DB",
                        "path": "02_PLC程序/PLC_ST/DB1/GlobalVars.db",
                        "responsibility": "全局变量与 IO 映射",
                    },
                    {
                        "name": "FB_2001_CommonAlarm_AllStation",
                        "type": "FB",
                        "path": "02_PLC程序/PLC_ST/common/FB_2001_CommonAlarm_AllStation.scl",
                        "responsibility": "公共报警管理",
                    },
                    {
                        "name": "FB_1002_SingleLayerConveyor_BufferFraming",
                        "type": "FB",
                        "path": "02_PLC程序/PLC_ST/conveyor/FB_1002_SingleLayerConveyor_BufferFraming.scl",
                        "responsibility": "输送设备控制",
                    },
                    {
                        "name": "FB_ExternalDeviceInteraction",
                        "type": "FB",
                        "path": "02_PLC程序/PLC_ST/external/FB_ExternalDeviceInteraction.scl",
                        "responsibility": "外部设备交互",
                    },
                    {
                        "name": "FB_1004_GlueMachineFeeder_BufferFraming",
                        "type": "FB",
                        "path": "02_PLC程序/PLC_ST/feeder/FB_1004_GlueMachineFeeder_BufferFraming.scl",
                        "responsibility": "打胶机送料控制",
                    },
                    {
                        "name": "FB_1003_PickPlace_BufferFraming",
                        "type": "FB",
                        "path": "02_PLC程序/PLC_ST/pickplace/FB_1003_PickPlace_BufferFraming.scl",
                        "responsibility": "取放料控制",
                    },
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    # 通讯对象：5 个通道（HMI/Upstream/Downstream/RemoteIO/MES）
    (asset_dir / "communications.yml").write_text(
        yaml.safe_dump(
            {
                "channels": [
                    {
                        "name": "HMI",
                        "protocol": "ethernet",
                        "role": "人机界面",
                        "endpoint": "Proface GP4501ww",
                        "notes": "M0-M4 模式选择",
                    },
                    {
                        "name": "UpstreamDevice",
                        "protocol": "hardwired",
                        "role": "上游设备（组框机）",
                        "endpoint": "待现场确定",
                        "notes": "预留 7DI+5DO",
                    },
                    {
                        "name": "DownstreamDevice",
                        "protocol": "hardwired",
                        "role": "下游设备（打胶机）",
                        "endpoint": "X75-X79/X102",
                        "notes": "安全联锁",
                    },
                    {
                        "name": "RemoteIO",
                        "protocol": "fieldbus",
                        "role": "分布式IO",
                        "endpoint": "NZ2MFB1-32DT 站号1",
                        "notes": "取料机构 14DI+6DO",
                    },
                    {
                        "name": "MES",
                        "protocol": "ethernet",
                        "role": "上位机系统",
                        "endpoint": "待对接",
                        "notes": "D406-D425 报警队列",
                    },
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    program_doc = doc_dir / "016_DJ-2026-005_PLC程序设计总文档_PLC.md"
    program_doc.write_text(
        "\n".join(
            [
                "# 边框缓存机PLC程序设计总文档",
                "",
                "## 5. 软件架构",
                "",
                "### 5.1 组件清单与职责",
                "",
                "<!-- AUTO_PM:BEGIN plc-program-components -->",
                "旧内容（待补齐占位）",
                "<!-- AUTO_PM:END plc-program-components -->",
                "",
                "## 8. 关联文档索引",
                "",
                "<!-- AUTO_PM:BEGIN plc-asset-index -->",
                "旧索引",
                "<!-- AUTO_PM:END plc-asset-index -->",
                "",
            ]
        ),
        encoding="utf-8",
    )
    io_doc = doc_dir / "015_DJ-2026-005_IO分配表_IO.md"
    io_doc.write_text(
        "\n".join(
            [
                "# 边框缓存机IO分配表",
                "",
                "## 2. 系统硬件配置总览",
                "",
                "<!-- AUTO_PM:BEGIN plc-io-overview -->",
                "旧IO概览（待补齐占位）",
                "<!-- AUTO_PM:END plc-io-overview -->",
                "",
            ]
        ),
        encoding="utf-8",
    )

    project = ProjectInfo(
        project_id="DJ-2026-005",
        name="边框缓存机",
        path=str(project_dir),
        stack="plc",
        phase="developing",
        version="0.4.2",
        description="V0.4.2 Week1 真实资产回归测试",
        extra={},
    )
    return project, program_doc, io_doc


def test_refresh_with_realistic_assets_emits_real_content_and_idempotent(
    tmp_path: Path,
) -> None:
    """V0.4.2 Week1 回归测试：真实规模资产 → 真实内容输出 + 幂等性。

    覆盖 DJ-2026-005 资产补齐后的核心契约：
    - 首次 dry-run 检测到自动区有变更（占位 → 真实内容）
    - 实际刷新写入真实内容，文档中不出现 "待补齐" 占位符
    - 真实程序块名（OB1/FB_2001/FB_1003 等）与工站名（cpu/remote_io_1 等）出现在文档
    - 二次 dry-run 与实际刷新均无变更（幂等性）
    """
    project, program_doc, io_doc = _setup_realistic_doc_project(tmp_path)
    service = DocRefreshService(str(tmp_path))

    # 1) 首次 dry-run：检测到变更但不写盘
    dry_run_1 = service.refresh_project_documents(project, dry_run=True)
    assert dry_run_1.updated is False
    assert len(dry_run_1.refreshed_files) == 2
    assert all(file.changed for file in dry_run_1.refreshed_files)
    assert "旧内容（待补齐占位）" in program_doc.read_text(encoding="utf-8")

    # 2) 实际刷新：写入真实内容
    apply_1 = service.refresh_project_documents(project, dry_run=False)
    assert apply_1.updated is True
    program_content = program_doc.read_text(encoding="utf-8")
    io_content = io_doc.read_text(encoding="utf-8")

    # 2a) "待补齐" 占位符不应出现在刷新后的文档中
    assert "待补齐" not in program_content
    assert "待补齐" not in io_content

    # 2b) 真实程序块名出现（7 个块全部出现）
    for block_name in [
        "OB1",
        "GlobalVars",
        "FB_2001_CommonAlarm_AllStation",
        "FB_1002_SingleLayerConveyor_BufferFraming",
        "FB_ExternalDeviceInteraction",
        "FB_1004_GlueMachineFeeder_BufferFraming",
        "FB_1003_PickPlace_BufferFraming",
    ]:
        assert block_name in program_content, f"程序块 {block_name} 未出现在刷新后的文档中"

    # 2c) 真实工站名出现（7 个工站全部出现）
    for station in [
        "cpu",
        "di_ext_1",
        "di_ext_3",
        "di_ext_4",
        "do_ext_1",
        "do_ext_2",
        "remote_io_1",
    ]:
        assert station in io_content, f"工站 {station} 未出现在刷新后的 IO 概览中"

    # 2d) 资产索引包含真实计数（19 IO / 7 blocks / 5 channels）
    assert "共 19 条" in program_content
    assert "共 7 项" in program_content
    assert "共 5 项" in program_content

    # 2e) IO 概览计数正确（DI 11 / DO 8）
    assert "| DI (数字量输入) | 11 |" in io_content
    assert "| DO (数字量输出) | 8 |" in io_content

    # 3) 二次 dry-run：幂等性（无变更）
    dry_run_2 = service.refresh_project_documents(project, dry_run=True)
    assert dry_run_2.updated is False
    assert all(not file.changed for file in dry_run_2.refreshed_files)

    # 4) 二次实际刷新：幂等性（无变更）
    apply_2 = service.refresh_project_documents(project, dry_run=False)
    assert apply_2.updated is False
    assert all(not file.changed for file in apply_2.refreshed_files)
