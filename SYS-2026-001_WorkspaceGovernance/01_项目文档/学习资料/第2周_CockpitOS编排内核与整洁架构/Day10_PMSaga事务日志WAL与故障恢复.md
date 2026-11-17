---
version: "V2.0.0"
status: "正式发布"
created: "2026-09-07"
updated: "2026-09-07"
spec_id: "GUIDE_W2_D10"
project_id: "SW-2026-008"
title: "Day 10：PM Saga 事务日志 WAL 与故障恢复"
---

# Day 10：PM Saga 事务日志 WAL 与故障恢复

> 🎯 **今日目标**：理解 Cockpit OS 的分布式收口事务日志（PM Saga WAL）与断电检查点（Checkpoint）恢复机制。  
> ⏱️ **预计耗时**：50 分钟  
> 🛠️ **前置准备**：查看 `auto_pm/domain/workflow/saga.py`。

---

## 💡 一、工控视角看 Saga WAL：PLC 断电保持与重载日志

在大型自动化产线中央控制柜中，最怕的是“工件运行到一半突然全厂停电”：
- 如果没有断电保护，重新上电后 PLC 根本不知道设备处于什么状态，盲目动作必然撞机；
- 工业级系统必须有 **保持型寄存器（Retentive Memory）** 与 **顺序事件记录日志（SOE / WAL, Write-Ahead Logging）**：
  - 每一个动作执行前，先在掉电保持区打一个“检查点标记（Checkpoint）”；
  - 重新上电后，PLC 自动读取日志：“上一次执行到了第 4 步，第 5 步未完成，启动第 5 步的反向补偿回滚程序”。

`PmClosureSagaCoordinator` 就是项目管理中的**“断电保持状态机”**！
当一个任务闭环收尾涉及多个文件（改变更单状态、改台账、改 PM_SESSION、消费交接包）时，如果电脑突然死机或断网，Saga 日志能精准诊断故障步并安全补偿！

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 📝 8 步 PM Saga 顺序事务日志 (WAL)                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ Step 1: PREFLIGHT_VALIDATE (预检回执与证据存在性)                          │
│ Step 2: CONSUME_HANDOFF    (原子消费并锁定交接包)                          │
│ Step 3: TRANSITION_CHANGE  (变更单流转至 completed)                         │
│ Step 4: UPDATE_PM_SESSION  (回写会话记录与状态摘要)                        │
│ Step 5: RECONCILE_LEDGER   (台账写入与一致性对账)                          │
│ Step 6: CLOSE_CHANGE       (变更单正式闭环归档)                            │
│ Step 7: PERSIST_REPORT     (持久化执行与验收报告)                          │
│ Step 8: SAGAS_COMPLETE     (事务整体标记完成)                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚙️ 二、正向补偿与故障注入测试

- **顺序写入（Write-Ahead Log）**：在动文件前先写日志 `.auto-pm/saga/<request_id>.saga.json`；
- **反向补偿（Compensating Action）**：如果在第 5 步台账写入失败，Saga 引擎会自动倒序执行：还原 PM_SESSION -> 还原变更单状态 -> 释放交接包锁定；
- 绝不给用户和系统留下“变更单关了但台账没记”、“交接包吃了但会话没写”的半死状态！

---

## 🧪 三、5 分钟动手实操实验

### 步骤 1：运行 PM Saga 事务日志自动化测试
```powershell
$env:PYTHONPATH = "00_Infrastructure/auto_pm"
python -m pytest tests/workflow/test_saga.py -v
```
*预期输出*：17 项 Saga 单测 100% passed，包括故障注入中断、检查点重放与完整补偿。

---

## 🛡️ 四、改崩恢复法与今日自测打卡

### 🚑 Saga 事务中断救援
若某次任务在收尾阶段被外部意外 Kill：
再次运行任务时，Saga 协调器会自动嗅探到未完成的 `.saga.json` 并提示恢复或自动执行补偿回滚。

### 📝 今日自测思考题
1. 什么是预写式日志（WAL, Write-Ahead Logging）？
2. 如果在更新台账步骤发生异常，Saga 补偿机制会做哪些动作？
3. 为什么多资产跨文件变更必须引入 Saga 分布式事务模型？
