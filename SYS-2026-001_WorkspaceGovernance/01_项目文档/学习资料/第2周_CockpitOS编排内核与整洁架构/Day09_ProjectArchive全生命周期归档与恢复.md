---
version: "V2.0.0"
status: "正式发布"
created: "2026-09-07"
updated: "2026-09-07"
spec_id: "GUIDE_W2_D09"
project_id: "SW-2026-008"
title: "Day 09：ProjectArchive 全生命周期归档与恢复"
---

# Day 09：ProjectArchive 全生命周期归档与恢复

> 🎯 **今日目标**：掌握 Cockpit OS 的项目全生命周期归档与恢复引擎（ProjectArchiveService），理解三道安全硬门禁与 ARC 流水号机制。  
> ⏱️ **预计耗时**：50 分钟  
> 🛠️ **前置准备**：熟悉项目归档规范与目录结构。

---

## 💡 一、工控视角看项目归档：产线封存与可逆解封

当一台自动化设备出厂验收交付、进入 2 年质保期后，工程部通常需要对这套工程进行**“产线工程封存”**：
- 绝不能随手“把文件夹拖进回收站永久删除”（万一现场 3 年后需要升级，源码丢了就是重大事故）；
- 也不能继续让它混在“在研项目列表”里干扰日常开发视线；
- 正规做法是建立**归档库（Archive Vault）**，打上唯一的封存流水号（如 `ARC-20260907-001`），入库台账；
- **可逆还原**：一旦客户提出维保需求，输入归档单号，系统能瞬间原样还原到开发区！

`auto-pm` 研发的 `ProjectArchiveService` 彻底根治了旧版本物理硬删除的技术债！

```text
01_Project自动化项目管理/Python自动化项目总库/
├── 02_在研项目/                        # 日常活跃在研区
│   └── SW-2026-008_auto-pm/
└── 03_归档/                            # 安全归档冷区
    └── SW-2026-008_auto-pm_ARC-20260907-001/
```

---

## ⚙️ 二、归档引擎的三道安全硬门禁

归档引擎在移动项目前，必须连续通过三道物理门禁：
1. **门禁 1：存在性与路径校验**：确认项目真实存在且路径合法，防止误移系统核心目录；
2. **门禁 2：生产锁定与未闭环检查**：扫描项目内是否有未闭环的草稿变更单（CHG），有未完成单据禁止归档；
3. **门禁 3：台账自动入账与哈希锁定**：生成唯一的 `ARC-YYYYMMDD-XXX` 归档编号，登记归档台账，保留完整目录相对结构。

---

## 🧪 三、5 分钟动手实操实验

### 步骤 1：查看项目归档与恢复 CLI 帮助
```powershell
$env:PYTHONPATH = "00_Infrastructure/auto_pm"
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" project archive --help
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" project restore --help
```
*预期输出*：清晰展示 archive 与 restore 命令的参数，说明支持归档编号与逆向解封。

### 步骤 2：查看已归档项目列表
```powershell
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" project list --archived
```
*预期输出*：列出当前处于 03_归档 冷库中的所有工程。

---

## 🛡️ 四、改崩恢复法与今日自测打卡

### 🚑 误归档一键逆向恢复
若不小心归档了正在开发的项目，只需一行指令瞬间解封还原：
```powershell
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" project restore <PID>
```

### 📝 今日自测思考题
1. 为什么现代化工业管理系统必须彻底杜绝“物理硬删除”？
2. `ProjectArchiveService` 的三道硬门禁分别把关了什么风险？
3. 项目归档流水号采用什么命名规范？
