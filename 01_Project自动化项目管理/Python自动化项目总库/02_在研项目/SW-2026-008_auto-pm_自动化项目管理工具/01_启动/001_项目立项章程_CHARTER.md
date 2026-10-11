---
version: "V1.2.0"
status: "APPROVED"
created: "2026-08-16"
updated: "2026-08-16"
project_id: "SW-2026-008"
title: "auto-pm 自动化项目管理工具 - 项目立项章程 (CHARTER)"
author: "Product PM"
---

# auto-pm 自动化项目管理工具 - 项目立项章程 (CHARTER)

> **所属过程组**：`01_启动 (Initiating)`  
> **项目编号**：`SW-2026-008`  
> **治理来源索引**：项目控制状态按工作区治理规则核对 canonical Continuity v2 记录、有效 WBS、已验收 Git/Checkpoint 与有效运行身份。`PM_SESSION_SW-2026-008.md` 已退役（用户 2026-10-10 裁决），仅作历史摘要，不是控制真源。

---

## 1. 项目愿景与业务定位 (One-Liner & Positioning)

- **一句话定义**：面向电气自动化工程师与全栈开发人员的**本地工业级项目作业驾驶舱与 5 大过程组治理系统**。
- **解决的核心痛点**：
  1. 工业现场软硬件协作割裂，PLC 代码与 HMI 设计缺乏前置需求（PRD）和接口变量契约（INT）约束。
  2. 项目状态与变更记录随意，现场临时改动无追溯，缺少端到端的 Dogfooding 质量闭环。
  3. 存量老项目缺乏规范诊断，代码腐化严重（全局脏变量直接读写、缺少安全联锁防呆）。

---

## 2. 目标用户画像 (Target Users)

1. **电气自动化工程师 (PLC/HMI 工程师)**：
   - 负责西门子 S7-1200/1500、汇川等 PLC 编程、HMI 画面流转、Modbus 现场调试与设备安全联锁。
2. **上位机/全栈开发工程师 (Python/QML 工程师)**：
   - 负责工业上位机、数据采集工具链开发与自动化测试门禁维护。
3. **复合型产品项目经理 (Product-oriented Technical PM)**：
   - 负责按 PMBOK 5 大过程组推进项目交付，卡死 Stage-Gate 出厂与现场门禁。

---

## 3. 边界划分：In-Scope 与 Non-Goals (坚决不做的非目标红线)

### 3.1 本期核心范围 (In-Scope)
- ✅ **5 大过程组 Stage-Gate 阶段门禁引擎**（G1 立项 -> G2 出厂 -> G3 现场 -> G4 验收）。
- ✅ **PLC 工艺代码生成器与 LSP-905 规范排查器**（强制 `VAR_IN_OUT` 结构体解耦传递）。
- ✅ **12 章节标准变更管理 (CHG)** 与 台账自动化对账（Ledger Reconcile）。
- ✅ **多厂商变量表转换器 (VarTable Converter)** 与 Modbus TCP 实时波形监测工坊。
- ✅ **本地沙箱项目池与维护知识库治理**（`0100_项目/` 沙箱 与 `学习资料/` 知识库）。

### 3.2 坚决不做的非目标红线 (Non-Goals)
- ❌ **不做在线多租户云端 SaaS 协作平台**：完全基于本地文件与 SQLite 本地单机作业，保障工业现场离线安全。
- ❌ **不做替代 TIA Portal / STEP 7 的通用在线 IDE**：专注于架构治理、代码生成与规范排查，底层编译交给官方工业软件。
- ❌ **不做复杂的重型审批流 ERP**：门禁采用“只读静态扫描 + 自动化 Checklist”，不增加现场繁琐审批负担。

---

## 4. 技术栈与环境约束 (Constraints & Environment)

- **开发语言与框架**：Python 3.11+ / PySide6 (Qt Quick / QML 6.x)。
- **受支持运行环境**：工作空间根受支持的 `.venv` 虚拟环境。
- **代码质量门禁**：
  - 静态检查：`ruff check` 0 errors, `mypy` 0 errors。
  - 自动化测试：`pytest` 单元测试通过率 100%。
  - 摘要投影：`PM_SESSION` 保持 ≤150 行双层快照（历史约束；该文件已退役）；行数与结构约束不改变 canonical 控制证据的优先级。
