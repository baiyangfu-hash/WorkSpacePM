---
version: "V2.0.0"
status: "正式发布"
created: "2026-09-07"
updated: "2026-09-07"
spec_id: "GUIDE_W2_D06"
project_id: "SW-2026-008"
title: "Day 06：Clean Architecture 5 层架构与工控解耦"
---

# Day 06：Clean Architecture 5 层架构与工控解耦

> 🎯 **今日目标**：理解 Clean Architecture 5 层整洁架构在工业上位机中的设计哲学，搞清 Domain、Application、Infrastructure、Contracts 与 UI 的清晰职责。  
> ⏱️ **预计耗时**：50 分钟  
> 🛠️ **前置准备**：查看 `02_规划/003_详细设计说明书_DSN.md` 与 `ARCHITECTURE.md`。

---

## 💡 一、工控视角看架构分层：标准工站 POU 的物理隔离

在早期写 PLC 程序时，新手常把所有逻辑揉在一个 `Main [OB1]` 里：直接读物理输入点 `%I0.0`、直接计算浮点数、直接控制伺服驱动器，还在里面修改触摸屏文案。**一旦硬件换个品牌（如西门子换汇川），整个程序推倒重来！**

老手会把 PLC 严格分层：
- **标准工艺算法块（标准库 FB）**：纯算法，绝不绑定具体硬件通道；
- **设备驱动块（Device Driver）**：负责与硬件总线（Profinet / EtherCAT）打交道；
- **工站主控步进链（Sequence SFC）**：只按工艺时序调用下层设备；
- **HMI 接口数据块（UDT / DB）**：定义干净的数据结构传给触摸屏。

`auto-pm` 的 Clean Architecture 5 层物理整洁架构正是这种工业哲学的体现：

```text
【UI 表现层】              PySide6 + QML 工业前端 / CLI 终端
         │
         ▼
【Application 应用层】     Facade 操作面，流水线协调器 (WorkflowOrchestrator)
         │
         ▼
【Domain 核心领域层】       纯业务实体与算法 (PlcChecker, VarTableParser, ArchiveService)
         │                ▲
         ▼                │ 依赖倒置 (Inversion of Control)
【Infrastructure 基础层】   SQLite 仓储、文件系统读写、Copier 渲染引擎
         │
         ▼
【Contracts 契约层】       强类型纯净 DTO (Data Transfer Object)，前后端通信标准 UDT
```

---

## ⚙️ 二、架构铁律：单向依赖与禁止越权

1. **核心领域层（Domain）零依赖**：`auto_pm/domain/` 严禁 `import` 表现层（UI）或外部框架，保证算法在任何环境下都能 100% 独立离线单测；
2. **所有跨层传输必须走 DTO（Contracts）**：就像 PLC 与 HMI 通信绝不能直接传未对齐的散点，必须封装在固定结构体的通信 DB（DTO）中；
3. **表现层只是 HMI**：QML 页面只负责显示与按钮动效，业务处理全部抛给 Application Facade。

---

## 🧪 三、5 分钟动手实操实验

### 步骤 1：查看 Domain 纯净算法目录
```powershell
Get-ChildItem "00_Infrastructure/auto_pm/releases/1.2.4-6699a5b/auto_pm/domain" | Select-Object Name
```
*预期输出*：清晰展示 `change`、`doc`、`modbus`、`models`、`plc`、`project`、`spec`、`vartable` 等独立纯净子领域。

### 步骤 2：查看 Contracts 契约定义
```powershell
Get-ChildItem "00_Infrastructure/auto_pm/releases/1.2.4-6699a5b/auto_pm/ui/contracts" -Recurse | Where-Object { $_.Name -like "*dto.py" } | Select-Object Name
```
*预期输出*：列出 `change_dto.py`、`spec_dto.py`、`workbench_dto.py` 等传输实体。

---

## 🛡️ 四、改崩恢复法与今日自测打卡

### 🚑 架构防破坏自检
当你修改了代码后，运行静态检查器验证是否有跨层非法导入：
```powershell
python -m auto_pm doc check --strict
```

### 📝 今日自测思考题
1. 为什么 Domain 领域层严禁 import 任何 UI 组件？
2. DTO 在 PLC 与上位机通信中对应什么概念？
3. 如果把当前的 QML 前端换成 Web 浏览器界面，系统哪几层完全不需要修改？
