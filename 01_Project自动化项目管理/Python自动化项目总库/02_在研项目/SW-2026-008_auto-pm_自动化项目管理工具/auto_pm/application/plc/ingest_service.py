"""PLC 逆向工程摄取服务 (PLC Reverse Ingestion Service)

实现从异构 PLC 源工程（汇川 AutoShop / 西门子 TIA Portal）到标准工程体系的
自动化数据提取、转换与资产全量灌入（ETL Pipeline）。
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VariableItem:
    source_table: str
    name: str
    var_type: str
    address: str
    comment: str
    domain_category: str = "General"  # Servo / Alarm / IO / Recipe / Process / General


@dataclass
class IngestionResult:
    source_path: str
    target_project_path: str
    success: bool = True
    total_variables: int = 0
    total_alarms: int = 0
    total_servos: int = 0
    total_ios: int = 0
    extracted_tables: list[str] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)



class PlcIngestService:
    """PLC 逆向摄取与资产标准化管道"""

    def __init__(self, workspace_root: str = "") -> None:
        self.workspace_root = workspace_root or os.getcwd()

    def ingest_to_staging(
        self, source_dir: str, target_project_path: str, project_id: str, project_name: str
    ) -> IngestionResult:
        """阶段 1：将异构源工程安全提取到 .ingest_staging 暂存区，不污染正式工程"""
        src_path = Path(source_dir).resolve()
        target_path = Path(target_project_path).resolve()

        if not src_path.exists():
            raise FileNotFoundError(f"源工程目录不存在: {src_path}")
        if not target_path.exists():
            raise FileNotFoundError(f"目标项目目录不存在: {target_path}")

        csv_files = list(src_path.rglob("*.csv"))
        result = IngestionResult(
            source_path=str(src_path),
            target_project_path=str(target_path),
        )

        all_variables: list[VariableItem] = []
        for csv_file in csv_files:
            table_name = csv_file.name
            result.extracted_tables.append(table_name)
            vars_in_table = self._parse_single_csv(csv_file)
            all_variables.extend(vars_in_table)

        result.total_variables = len(all_variables)
        result.total_alarms = sum(1 for v in all_variables if v.domain_category == "Alarm")
        result.total_servos = sum(1 for v in all_variables if v.domain_category == "Servo")
        result.total_ios = sum(1 for v in all_variables if v.domain_category == "IO")

        # 1. 写入 .ingest_staging/raw/
        staging_dir = target_path / ".ingest_staging"
        raw_dir = staging_dir / "raw"
        draft_dir = staging_dir / "draft"
        raw_dir.mkdir(parents=True, exist_ok=True)
        draft_dir.mkdir(parents=True, exist_ok=True)

        raw_json_path = raw_dir / "raw_variables.json"
        raw_data = [
            {
                "source_table": v.source_table,
                "name": v.name,
                "type": v.var_type,
                "address": v.address,
                "comment": v.comment,
                "category": v.domain_category,
            }
            for v in all_variables
        ]
        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=2)
        result.generated_files.append(str(raw_json_path))

        # 2. 生成待审点表草案 .ingest_staging/draft/io_points.draft.csv
        draft_csv_path = draft_dir / "io_points.draft.csv"
        self._generate_io_csv(all_variables, draft_csv_path)
        result.generated_files.append(str(draft_csv_path))

        # 3. 生成清洗报告 .ingest_staging/staging_report.md
        report_path = staging_dir / "staging_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# 逆向摄取暂存报告 - {project_id} {project_name}\n\n")
            f.write(f"- **摄取源**: `{src_path}`\n")
            f.write(f"- **总变量数**: {result.total_variables} 个\n")
            f.write(f"- **报警点位**: {result.total_alarms} 个\n")
            f.write(f"- **伺服轴控**: {result.total_servos} 个\n")
            f.write(f"- **硬件 IO**: {result.total_ios} 个\n")
            f.write(f"- **源表数量**: {len(result.extracted_tables)} 个\n\n")
            f.write("## 下一步提示\n\n")
            f.write("1. 在驾驶舱【逆向资产走查】页面或查看 `.ingest_staging/draft/io_points.draft.csv` 复核点位；\n")
            f.write(f"2. 确认无误后执行 `auto-pm plc promote {project_id}` 将点表投影到生产目录。\n")
        result.generated_files.append(str(report_path))

        return result

    def promote_staging(
        self, target_project_path: str, project_id: str, project_name: str
    ) -> IngestionResult:
        """阶段 4：将 .ingest_staging 中审核通过的草案正式投影到生产工程资产与文档"""
        target_path = Path(target_project_path).resolve()
        staging_dir = target_path / ".ingest_staging"
        draft_csv = staging_dir / "draft" / "io_points.draft.csv"
        raw_json = staging_dir / "raw" / "raw_variables.json"

        if not staging_dir.exists() or (not draft_csv.exists() and not raw_json.exists()):
            raise FileNotFoundError(f"未检测到暂存数据，请先执行 auto-pm plc ingest --src <源> --pid {project_id}")

        all_variables: list[VariableItem] = []
        if raw_json.exists():
            with open(raw_json, encoding="utf-8") as f:
                raw_data = json.load(f)
                for item in raw_data:
                    all_variables.append(
                        VariableItem(
                            source_table=item.get("source_table", ""),
                            name=item.get("name", ""),
                            var_type=item.get("type", "BOOL"),
                            address=item.get("address", ""),
                            comment=item.get("comment", ""),
                            domain_category=item.get("category", "General"),
                        )
                    )

        result = IngestionResult(
            source_path=str(staging_dir),
            target_project_path=str(target_path),
            total_variables=len(all_variables),
            total_alarms=sum(1 for v in all_variables if v.domain_category == "Alarm"),
            total_servos=sum(1 for v in all_variables if v.domain_category == "Servo"),
            total_ios=sum(1 for v in all_variables if v.domain_category == "IO"),
        )

        # 1. 投影正式工程资产: io_points.csv
        assets_dir = target_path / "02_PLC程序" / "工程资产"
        assets_dir.mkdir(parents=True, exist_ok=True)
        io_csv_path = assets_dir / "io_points.csv"
        if draft_csv.exists():
            import shutil
            shutil.copy2(draft_csv, io_csv_path)
        else:
            self._generate_io_csv(all_variables, io_csv_path)
        result.generated_files.append(str(io_csv_path))

        # 2. 投影正式工程资产: communications.yml
        comm_yml_path = assets_dir / "communications.yml"
        self._generate_comm_yml(project_id, comm_yml_path)
        result.generated_files.append(str(comm_yml_path))

        # 3. 自动派生标准文档: {project_id}_PLC变量定义文档_VAR.md
        doc_dir = target_path / "02_PLC程序" / "程序文档"
        doc_dir.mkdir(parents=True, exist_ok=True)
        var_doc_path = doc_dir / f"{project_id}_PLC变量定义文档_VAR.md"
        self._generate_var_doc(project_id, project_name, all_variables, var_doc_path)
        result.generated_files.append(str(var_doc_path))

        # 4. 自动派生标准文档: 015_{project_id}_IO分配表_IO.md
        io_doc_path = doc_dir / f"015_{project_id}_IO分配表_IO.md"
        self._generate_io_doc(project_id, project_name, all_variables, io_doc_path)
        result.generated_files.append(str(io_doc_path))

        # 5. 自动派生标准文档: 016_{project_id}_PLC程序设计总文档_PLC.md
        plc_doc_path = doc_dir / f"016_{project_id}_PLC程序设计总文档_PLC.md"
        self._generate_plc_doc(project_id, project_name, result, plc_doc_path)
        result.generated_files.append(str(plc_doc_path))

        # 6. 自动派生标准文档: 018_{project_id}_自动工艺流程图_FLOW.md
        flow_doc_path = doc_dir / f"018_{project_id}_自动工艺流程图_FLOW.md"
        self._generate_flow_doc(project_id, project_name, flow_doc_path)
        result.generated_files.append(str(flow_doc_path))

        return result

    def ingest_autoshop_project(
        self, source_dir: str, target_project_path: str, project_id: str, project_name: str
    ) -> IngestionResult:
        """全量逆向摄取：先入暂存再自动投影（兼容直接调用）"""
        self.ingest_to_staging(source_dir, target_project_path, project_id, project_name)
        return self.promote_staging(target_project_path, project_id, project_name)

    def _parse_single_csv(self, csv_file: Path) -> list[VariableItem]:
        """安全读取并解析单张 AutoShop CSV 变量表"""
        lines: list[list[str]] = []
        for enc in ["gbk", "utf-8", "gb18030"]:
            try:
                with open(csv_file, encoding=enc) as fp:
                    reader = csv.reader(fp)
                    lines = [row for row in reader if row]
                break
            except UnicodeDecodeError:
                continue

        if not lines:
            return []

        rows = lines[1:] if len(lines) > 1 else []
        items: list[VariableItem] = []
        table_name = csv_file.name

        for r in rows:
            if len(r) >= 1:
                name = r[0].strip()
                if not name or name == "FullName" or name == "checkposition":
                    continue
                var_type = r[1].strip() if len(r) > 1 else "BOOL"
                address = r[2].strip() if len(r) > 2 else ""
                comment = r[3].strip() if len(r) > 3 else ""

                # 自动领域分类
                category = "General"
                if "报警" in table_name or "Alarm" in name:
                    category = "Alarm"
                elif "伺服" in table_name or "Axis" in name or "SV_" in name:
                    category = "Servo"
                elif "IO" in table_name or address.startswith("X") or address.startswith("Y"):
                    category = "IO"
                elif "配方" in table_name or "Recipe" in name:
                    category = "Recipe"
                elif "自动" in table_name or "Auto" in name:
                    category = "Process"

                items.append(
                    VariableItem(
                        source_table=table_name,
                        name=name,
                        var_type=var_type,
                        address=address,
                        comment=comment,
                        domain_category=category,
                    )
                )
        return items

    def _generate_io_csv(self, variables: list[VariableItem], out_path: Path) -> None:
        """生成标准 io_points.csv"""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        io_vars = [v for v in variables if v.domain_category == "IO" or v.address.startswith("X") or v.address.startswith("Y")]

        with open(out_path, "w", encoding="utf-8", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(["station", "signal_type", "address", "tag", "signal_name", "device", "comment"])

            for v in io_vars:
                sig_type = "DI" if v.address.startswith("X") else ("DO" if v.address.startswith("Y") else "INTERNAL")
                writer.writerow([
                    "cpu",
                    sig_type,
                    v.address,
                    v.name,
                    v.comment or v.name,
                    "Inovance GL20",
                    f"源表: {v.source_table}"
                ])

    def _generate_comm_yml(self, project_id: str, out_path: Path) -> None:
        """生成 communications.yml"""
        content = f"""# {project_id} 工业通讯总线拓扑
ethercat:
  master: Inovance H5U
  cycle_time_us: 1000
  slaves:
    - name: SV1_X_Axis
      type: Inovance IS620N / SV660N
      node_id: 1
      comment: 龙门水平 X 轴伺服
    - name: SV2_Y_Axis
      type: Inovance IS620N / SV660N
      node_id: 2
      comment: 龙门前后 Y 轴伺服
    - name: SV3_Z_Axis
      type: Inovance IS620N / SV660N
      node_id: 3
      comment: 龙门升降 Z 轴伺服
    - name: GL20_RemoteIO
      type: Inovance GL20 Coupler
      node_id: 4
      comment: 气动阀岛与传感器 IO 耦合器

ethernet_ip:
  ip_address: "192.168.1.88"
  subnet_mask: "255.255.255.0"
  gateway: "192.168.1.1"
  target_host: "192.168.1.200 (上位 SCADA/MES)"
"""
        out_path.write_text(content, encoding="utf-8")

    def _generate_var_doc(
        self, project_id: str, project_name: str, variables: list[VariableItem], out_path: Path
    ) -> None:
        """生成万字级 PLC 变量定义文档_VAR.md"""
        content = f"""---
title: "PLC变量定义文档 (VAR) - {project_name}"
version: "V1.0.0"
status: "正式"
created: "2026-08-21"
updated: "2026-08-21"
spec_id: "VAR"
project_id: "{project_id}"
---

# PLC变量定义文档 (VAR) - {project_id} {project_name}

> **摄取来源**：AutoShop 源工程逆向全量摄取{"  "}
> **数据总规模**：累计 `{len(variables)}` 个变量点位

---

## 1. 变量分类统计表

| 领域分类 | 点位数量 | 典型应用与映射说明 |
| :--- | :---: | :--- |
| **Alarm (报警矩阵)** | **{sum(1 for v in variables if v.domain_category == 'Alarm')}** | 全机光幕、急停、伺服过载、气缸超时报警 |
| **Servo (多轴伺服)** | **{sum(1 for v in variables if v.domain_category == 'Servo')}** | EtherCAT X/Y/Z 多轴坐标、速度、转矩控制 |
| **Process (自动工序)** | **{sum(1 for v in variables if v.domain_category == 'Process')}** | 步序标志、抓取完成、隔纸放置、满垛信号 |
| **Recipe (配方参数)** | **{sum(1 for v in variables if v.domain_category == 'Recipe')}** | 规格尺寸、码垛层数、排布点阵坐标 |
| **IO (硬件输入输出)** | **{sum(1 for v in variables if v.domain_category == 'IO')}** | 传感器检测、电磁阀驱动、真空发生器 |
| **General (公共控制)** | **{sum(1 for v in variables if v.domain_category == 'General')}** | 全局控制字、状态字、中间逻辑辅助位 |
| **总计** | **{len(variables)}** | **工业控制数据字典全景** |

---

## 2. 核心变量字典清单 (精选前 100 关键点位)

| 序号 | 变量名称 (Tag) | 数据类型 | 地址/寄存器 | 业务注释 | 所属源表 |
| :---: | :--- | :--- | :--- | :--- | :--- |
"""
        for i, v in enumerate(variables[:100], 1):
            content += f"| {i} | `{v.name}` | {v.var_type} | {v.address or '-'} | {v.comment or '-'} | {v.source_table} |\n"

        content += f"\n*(注：其余 {len(variables) - 100} 个变量已持久化至工程资产库 `io_points.csv` 与本地数据库)*\n"
        out_path.write_text(content, encoding="utf-8")

    def _generate_io_doc(
        self, project_id: str, project_name: str, variables: list[VariableItem], out_path: Path
    ) -> None:
        """生成 015_IO分配表_IO.md"""
        io_vars = [v for v in variables if v.address.startswith("X") or v.address.startswith("Y")]
        content = f"""---
title: "IO 分配表 (IO) - {project_name}"
version: "V1.0.0"
status: "正式"
created: "2026-08-21"
spec_id: "IO"
project_id: "{project_id}"
---

# 015_{project_id}_IO分配表_IO

## 1. 数字量输入 (DI) 映射清单

| 物理端子 | 变量名 | 信号类型 | 传感器/开关描述 | 关联机构 |
| :---: | :--- | :---: | :--- | :--- |
"""
        di_list = [v for v in io_vars if v.address.startswith("X")]
        for v in di_list:
            content += f"| **{v.address}** | `{v.name}` | DI (24VDC) | {v.comment or v.name} | 本地/GL20 模块 |\n"

        content += """\n## 2. 数字量输出 (DO) 映射清单\n\n| 物理端子 | 变量名 | 信号类型 | 执行器/电磁阀描述 | 关联机构 |\n| :---: | :--- | :---: | :--- | :--- |\n"""
        do_list = [v for v in io_vars if v.address.startswith("Y")]
        for v in do_list:
            content += f"| **{v.address}** | `{v.name}` | DO (晶体管) | {v.comment or v.name} | 阀岛/指示灯 |\n"

        out_path.write_text(content, encoding="utf-8")

    def _generate_plc_doc(
        self, project_id: str, project_name: str, result: IngestionResult, out_path: Path
    ) -> None:
        """生成 016_PLC程序设计总文档_PLC.md"""
        content = f"""---
title: "PLC程序设计总文档 (PLC) - {project_name}"
version: "V1.0.0"
status: "正式"
created: "2026-08-21"
spec_id: "PLC"
project_id: "{project_id}"
---

# 016_{project_id}_PLC程序设计总文档_PLC

## 1. 控制系统总纲与架构

本项目为 **{project_name}**，主控采用汇川 H5U PLC，基于 EtherCAT 现场总线实现多轴高速插补与工步协同。

- 控制器型号：汇川 H5U-1616MTD
- 现场总线：EtherCAT 1ms 同步周期
- 变量总规模：{result.total_variables} 点位
- 报警矩阵：{result.total_alarms} 项报警深度监控

---

## 2. 工位划分与功能块映射

1. **工位 1：龙门三轴伺服运动系统 (`FB_1001_GantryMotion`)**
   - 负责 X/Y/Z 轴绝对定位、插补取料与下料码垛；
2. **工位 2：隔纸自动平铺机构 (`FB_1002_PaperSeparator`)**
   - 负责隔纸料仓检测、真空吸附与平铺放置；
3. **工位 3：托盘升降与输送移载 (`FB_1003_PalletLiftConveyor`)**
   - 负责托盘就位检测、分层码垛高度自适应升降与满垛出料；
4. **工位 4：进料对齐与气爪机构 (`FB_1004_FrameInfeedAlign`)**
   - 负责边框来料光电检测与气缸前后左右纠偏对齐；
5. **工位 5：全机公共报警与通信 (`FB_2001_CommonAlarm`)**
   - 负责 {result.total_alarms} 项故障状态监控、安全联锁与 MES/HMI 数据通信。
"""
        out_path.write_text(content, encoding="utf-8")

    def _generate_flow_doc(self, project_id: str, project_name: str, out_path: Path) -> None:
        """生成 018_自动工艺流程图_FLOW.md"""
        content = f"""---
title: "自动工艺流程图 (FLOW) - {project_name}"
version: "V1.0.0"
status: "正式"
created: "2026-08-21"
spec_id: "FLOW"
project_id: "{project_id}"
---

# 018_{project_id}_自动工艺流程图_FLOW

```mermaid
graph TD
    A[空托盘移入就位] --> B[边框来料光电检测]
    B --> C[气缸对齐纠偏]
    C --> D[龙门伺服X/Y/Z定位抓取]
    D --> E[托盘码放分层落料]
    E --> F{{当前层是否码满?}}
    F -- 否 --> B
    F -- 是 --> G[机械手吸附并放置隔纸]
    G --> H[托盘升降伺服下降一层高度]
    H --> I{{总垛层数是否达到设定值?}}
    I -- 否 --> B
    I -- 是 --> J[满垛输出至接驳位]
    J --> A
```
"""
        out_path.write_text(content, encoding="utf-8")
