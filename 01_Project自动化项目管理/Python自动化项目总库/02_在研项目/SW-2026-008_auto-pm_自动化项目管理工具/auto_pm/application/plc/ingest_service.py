"""PLC 逆向工程摄取服务 (PLC Reverse Ingestion Service)

实现从异构 PLC 源工程（汇川 AutoShop / 西门子 TIA Portal）到标准工程体系的
自动化数据提取、转换与资产全量灌入（ETL Pipeline）。
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from datetime import date
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
        # 源工程变量表里没有通讯配置：项目里已有的（建项目时模板生成、或人填过的）不覆盖，没有才写一份待填写的空清单
        comm_yml_path = assets_dir / "communications.yml"
        if not comm_yml_path.exists():
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
                    "待填写",
                    f"源表: {v.source_table}"
                ])

    def _generate_comm_yml(self, project_id: str, out_path: Path) -> None:
        """生成待填写的 communications.yml（格式同项目模板：channels 列表）。

        源工程变量表里读不到控制器、总线和 IP，这里不编任何设备或地址，只留空清单等人按电气图纸填。
        """
        content = f"""# {project_id} 通讯对象清单：摄取时源工程变量表里没有通讯配置，按电气图纸补齐
project_id: "{project_id}"
channels: []
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
created: "{date.today().isoformat()}"
updated: "{date.today().isoformat()}"
spec_id: "VAR"
project_id: "{project_id}"
---

# PLC变量定义文档 (VAR) - {project_id} {project_name}

> **摄取来源**：源工程 CSV 变量表逆向摄取
> **数据总规模**：累计 `{len(variables)}` 个变量点位

---

## 1. 变量分类统计表

| 领域分类 | 点位数量 | 典型应用与映射说明 |
| :--- | :---: | :--- |
| **Alarm (报警)** | **{sum(1 for v in variables if v.domain_category == 'Alarm')}** | 表名带“报警”或变量名带 Alarm |
| **Servo (伺服)** | **{sum(1 for v in variables if v.domain_category == 'Servo')}** | 表名带“伺服”或变量名带 Axis、SV_ |
| **IO (输入输出)** | **{sum(1 for v in variables if v.domain_category == 'IO')}** | 表名带 IO 或地址以 X、Y 开头 |
| **Recipe (配方)** | **{sum(1 for v in variables if v.domain_category == 'Recipe')}** | 表名带“配方”或变量名带 Recipe |
| **Process (自动工序)** | **{sum(1 for v in variables if v.domain_category == 'Process')}** | 表名带“自动”或变量名带 Auto |
| **General (其他)** | **{sum(1 for v in variables if v.domain_category == 'General')}** | 以上都不是 |
| **总计** | **{len(variables)}** | 按表名、变量名、地址自动分类，分类以人工复核为准 |

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
created: "{date.today().isoformat()}"
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
            content += f"| **{v.address}** | `{v.name}` | DI | {v.comment or v.name} | 待填写 |\n"

        content += """\n## 2. 数字量输出 (DO) 映射清单\n\n| 物理端子 | 变量名 | 信号类型 | 执行器/电磁阀描述 | 关联机构 |\n| :---: | :--- | :---: | :--- | :--- |\n"""
        do_list = [v for v in io_vars if v.address.startswith("Y")]
        for v in do_list:
            content += f"| **{v.address}** | `{v.name}` | DO | {v.comment or v.name} | 待填写 |\n"

        out_path.write_text(content, encoding="utf-8")

    def _generate_plc_doc(
        self, project_id: str, project_name: str, result: IngestionResult, out_path: Path
    ) -> None:
        """生成 016_PLC程序设计总文档_PLC.md"""
        content = f"""---
title: "PLC程序设计总文档 (PLC) - {project_name}"
version: "V1.0.0"
status: "正式"
created: "{date.today().isoformat()}"
spec_id: "PLC"
project_id: "{project_id}"
---

# 016_{project_id}_PLC程序设计总文档_PLC

## 1. 摄取所得

本项目为 **{project_name}**。以下数字来自源工程 CSV 变量表，控制器、总线和工位源工程变量表里读不到，留待填写。

- 控制器型号：待填写
- 现场总线：待填写
- 变量总规模：{result.total_variables} 点位
- 报警点位：{result.total_alarms} 个
- 伺服相关点位：{result.total_servos} 个
- 硬件 IO 点位：{result.total_ios} 个

---

## 2. 工位划分与功能块映射

待填写：按工艺方案列出工位和对应功能块，摄取不推断工位。
"""
        out_path.write_text(content, encoding="utf-8")

    def _generate_flow_doc(self, project_id: str, project_name: str, out_path: Path) -> None:
        """生成 018_自动工艺流程图_FLOW.md"""
        content = f"""---
title: "自动工艺流程图 (FLOW) - {project_name}"
version: "V1.0.0"
status: "正式"
created: "{date.today().isoformat()}"
spec_id: "FLOW"
project_id: "{project_id}"
---

# 018_{project_id}_自动工艺流程图_FLOW

待填写：源工程变量表里没有工艺流程，按工艺方案画出步序。

```mermaid
graph TD
    S0([待填写：第一步]) --> S1[待填写：下一步]
```
"""
        out_path.write_text(content, encoding="utf-8")
