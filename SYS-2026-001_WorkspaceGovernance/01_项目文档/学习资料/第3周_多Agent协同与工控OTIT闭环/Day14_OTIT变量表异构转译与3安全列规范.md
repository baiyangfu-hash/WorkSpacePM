---
version: "V2.0.0"
status: "正式发布"
created: "2026-09-07"
updated: "2026-09-07"
spec_id: "GUIDE_W3_D14"
project_id: "SW-2026-008"
title: "Day 14：OT-IT 变量表异构转译与 3 安全列规范"
---

# Day 14：OT-IT 变量表异构转译与 3 安全列规范

> 🎯 **今日目标**：掌握 14 种异构 PLC 变量表的自动嗅探与转译机制，理解 STD-816/817 汽车级安全三列规范（wiring_level, fail_safe, break_action）。  
> ⏱️ **预计耗时**：50 分钟  
> 🛠️ **前置准备**：查看 `02_PLC程序/工程资产/io_points.csv`。

---

## 💡 一、工控视角看变量表转译：打破各品牌 PLC 的“巴别塔”

做工控最让人头疼的是每个厂家的变量表格式完全不同：
- **汇川 AutoShop**：带 `_var_begin` 前缀，制表符分隔；
- **三菱 GX Works3**：点位导出带固定的制表符与软元件注释；
- **倍福 / CodeSys**：XML 树状导出或平铺 CSV；
- **西门子 TIA Portal**：带引号的逗号分隔符导出。

每次项目上位机要读取 PLC 点位，工程师都得手动在 Excel 里复制粘贴、调整列序，**耗时 2 天且极易对错行导致气缸乱撞！**

`auto-pm vartable` 管道彻底终结了人工对表：
- **自动文件魔数与首行特征嗅探（FormatDetector）**；
- **转译至统一纯净 `IOPoint` 领域模型**；
- **一键输出到标准 `io_points.csv`**！

```text
异构原始变量表 (AutoShop / CodeSys / Works3)
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🔄 FormatDetector & BaseParser (统一映射管道)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ 映射标准: IOPoint(tag_name, data_type, address, comment, station)          │
│ 汽车级安全扩展: wiring_level, fail_safe, break_action                       │
└─────────────────────────────────────────────────────────────────────────────┘
                   │
                   ▼
标准交付物: 02_PLC程序/工程资产/io_points.csv
```

---

## ⚙️ 二、汽车制造级安全三列规范（STD-816 / 817）

在新版规范中，每个关键点位必须包含三项安全属性，以支撑严苛的工业安全评估：
1. **`wiring_level`（接线安全等级）**：如 `SIL2`, `SIL3`, `Cat.4`, `Standard`；
2. **`fail_safe`（故障安全态）**：断电/断线时信号逻辑是常开（NO）还是常闭（NC），如急停按钮必须为常闭 NC（Fail-Safe Low）；
3. **`break_action`（熔断保护动作）**：传感器掉线时系统执行的保护策略（如 `EMERGENCY_STOP` 急停、`CYCLE_PAUSE` 循环暂停、`ALARM_ONLY` 仅报警）。

---

## 🧪 三、5 分钟动手实操实验

### 步骤 1：查看变量表转译与解析帮助
```powershell
$env:PYTHONPATH = "00_Infrastructure/auto_pm"
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" vartable --help
```
*预期输出*：展示 vartable 命令组，支持 batch-parse 与 export。

### 步骤 2：校验某项目 IO 点表规范完整性
```powershell
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" plc check --pid DJ-2026-005
```
*预期输出*：门禁自动检查 `io_points.csv` 是否符合安全三列及格式标准。

---

## 🛡️ 四、改崩恢复法与今日自测打卡

### 🚑 点表解析格式未知
若遇到新型 PLC 导出格式未被探测到：
查看 `auto_pm/domain/vartable/parsers/`，只需新建一个继承自 `BaseParser` 的独立解析器，实现 `sniff()` 与 `parse()` 即可无缝扩展！

### 📝 今日自测思考题
1. 为什么急停回路（E-Stop）在 `fail_safe` 中必须设计为常闭（NC）？
2. `wiring_level` 为 `SIL3` 的安全门联锁点位对应什么硬件要求？
3. `FormatDetector` 是如何实现自动识别各品牌变量表格式的？
