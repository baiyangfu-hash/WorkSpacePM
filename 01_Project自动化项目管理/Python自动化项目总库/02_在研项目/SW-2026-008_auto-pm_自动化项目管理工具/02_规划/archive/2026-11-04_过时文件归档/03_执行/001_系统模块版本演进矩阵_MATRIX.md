---
version: "V1.2.3"
status: "ACTIVE"
created: "2026-08-16"
updated: "2026-09-01"
project_id: "SW-2026-008"
title: "auto-pm 核心模块版本演进与 Breaking Changes 矩阵 (MATRIX)"
author: "Lead Full-stack Engineer"
---

# auto-pm 核心模块版本演进与 Breaking Changes 矩阵 (MATRIX)

> **所属过程组**：`03_执行 (Executing)`  
> **项目编号**：`SW-2026-008`  
> **单一真源索引**：`PM_SESSION_SW-2026-008.md`

---

## 1. 核心架构组件版本演进矩阵

| 系统主版本 | 关键变更单 (CHG) | `WorkbenchFacade` 外观层 | `QML Bridges` 桥接层 | `StageGateEngine` 门禁引擎 | `PLC SCL Linter` 规范排查器 | 核心架构特征 / 破坏性变更 (Breaking Changes) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **V0.9.0** | CHG-SCPT-101 | V1.0.0 | V1.0.0 | - | - | 基础脚手架生成与 SQLite 扫描缓存落地 |
| **V1.0.0** | CHG-SCPT-140 | V2.0.0 | V2.0.0 | - | - | QML 玻璃拟态深色驾驶舱与三轨道 View 架构建立 |
| **V1.1.0** | CHG-SCPT-152 | V2.1.0 | V2.2.0 | - | - | 跨技能协同公共契约 (`skill_coordination.md`) 确立 |
| **V1.1.1** | CHG-SCPT-156 | V2.2.0 | V2.3.0 (`AiContextV2`) | - | - | `ai_context.json` V2 升级，PM 成为唯一回写 owner |
| **V1.1.2** | CHG-SCPT-157 | V2.3.0 | V2.4.0 (`SpecBridge`) | - | V1.0.0 (`LSP-905`) | 引入 SCL 工艺状态机离线生成器与 LSP-905 规范排查器 |
| **V1.2.0** | CHG-SCPT-158 | V3.0.0 | V3.0.0 | V1.0.0 (`G1~G4`) | V1.1.0 | 5 大过程组 Stage-Gate 阶段门禁规则引擎与 DTO 契约构建 |
| **V1.2.1** | CHG-SCPT-162 | V3.1.0 | V3.1.0 | V1.1.0 | V1.2.0 | 严苛审计缺陷修复与工业级安全加固 |
| **V1.2.2** | CHG-SCPT-163 | V3.2.0 | V3.2.0 | V1.1.0 | V1.2.1 | P1 级架构安全加固与工控全域测试安全网深化 |
| **V1.2.3 (当前代码基线)** | **CHG-SCPT-164/166/167** | **V3.3.0** | **V3.3.0** | **V1.2.0 (`G3落账门禁`)** | **V1.2.2** | **P2 质量收敛、友好排障、落账门禁与 SHC-017 契约对账器闭环** |
| **V1.2.3+Cockpit-P0** | CHG-SCPT-170 | V3.3.0 | V3.3.0 | V1.2.0 | V1.2.2 | 防空壳实质化体系（W0）、结构化决策包契约、W1-1 跨领域穿透门禁 |
| **V1.2.3+Cockpit-P1** | CHG-SCPT-171/172 | V3.3.0 | V3.3.0 | V1.3.0 (`证据门禁`) | V1.2.2 | 证据门禁 Scope Gating、PM Saga WAL 8 步事务日志与故障恢复 |
| **V1.2.3+Cockpit-OS** | CHG-SCPT-173~177 | V3.4.0 (`WorkflowFacade`) | V3.3.0 | V1.3.0 | V1.2.2 | **Cockpit OS 全链路**：DTO契约层、ChangeTransactionManager、WorkflowOrchestrator（plan+execute）、ProjectArchiveService（ARC台账+逆向恢复） |
| **V1.2.3+Release-f950525 (稳定部署)** | NG-WP-11~15 / CHG-SCPT-184 | V3.4.0 | V3.3.0 | V1.3.0 | V1.2.2 | **稳定双槽部署正式生效**：886文件manifest全验证、launcher双槽化、active=`1.2.3-f950525`；母体源码冻结于 2026-08-28 |

> **[A2-3 补录 2026-09-06]**：上表 Cockpit OS 批次（CHG-171~177）与 NG-WP 发布链路（NG-WP-11~15）均为 2026-09-04~06 执行，
> 此前矩阵停在 CHG-164。原 V1.2.3 代码基线行保留，后续行追加补录。

---

## 2. 各子领域模块成熟度一览

| 子领域包 | 当前版本 | 职责定义 | 单元测试覆盖 |
| :--- | :--- | :--- | :--- |
| `auto_pm.contracts` | V1.0.0 | 强类型 DTO 契约 (`gate_dtos`, `dto.py`) | 94% |
| `auto_pm.core.gates` | V1.0.0 | 5 大过程组 G1~G4 规则评估器与卡点阻断 | 97% |
| `auto_pm.plc` | V1.2.0 | 西门子 S7 SCL 生成、Linter 规范检查、UDT 结构体分析 | 92% |
| `auto_pm.change` | V2.0.0 | 9 步状态流转机、12 章节解析器、台账自动对账 | 95% |
| `auto_pm.vartable` | V1.5.0 | 多厂商变量表（Inovance, CoDeSys, Work3）解析与转换 | 90% |
| `auto_pm.modbus` | V1.1.0 | 异步 Modbus TCP 轮询、环形缓冲数据管道与 Sim 仿真 | 88% |
| `auto_pm.ui.qml` | V2.0.0 | 11 大 QML 视图组件与 5 大 Bridge 桥接通信 | 100% (138 QML tests) |
| `auto_pm.application.workflow` | **V1.0.0 (新)** | **WorkflowOrchestrator plan+execute、ChangeTransactionManager 事务沙箱** | **CHG-174~176: 55 passed** |
| `auto_pm.domain.plc.archive` | **V1.0.0 (新)** | **ProjectArchiveService：ARC 流水号归档、领域就近路由、逆向恢复** | **CHG-177: 45 passed** |
| `auto_pm.application.saga` | **V1.0.0 (新)** | **PM Saga WAL 事务日志：8 步顺序日志、Checkpoint 故障恢复、补偿回滚** | **CHG-172: 已验证** |
