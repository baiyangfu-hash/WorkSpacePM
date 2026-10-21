# FB_1001_Station1 接口设计说明书

> **项目编号**: DJ-2026-009  
> **功能块**: `FB_1001_Station1`  
> **模块名称**: 工位1 动作机构控制  
> **版本号**: V1.0.0  
> **编制人**:   
> **更新日期**: 2026-08-23  
> **规范依据**: DEV-001 / LSP-905 / LSP-907  

---

## 1. 功能块概述

`FB_1001_Station1` 负责 汇川换型改造 工位1 进料、定位、夹紧顶升、加工延时与出料输送控制。

---

## 2. 接口参数定义 (VAR_IN_OUT)

| 参数名 | 数据类型 | 描述 |
| :--- | :--- | :--- |
| `io_stStation` | `ST_Station1` | 工位1 全局交互结构体 (包含 Control, Status, Config, Sensors, Actuators) |

### 2.1 控制指令子结构 (`stControl`)

| 字段名 | 类型 | 说明 |
| :--- | :---: | :--- |
| `bAutoEnable` | BOOL | 自动运行使能 (1=使能) |
| `bManualStart` | BOOL | 手动单步启动 |
| `bReset` | BOOL | 故障复位指令 |
| `bPause` | BOOL | 暂停运行 |
| `bSingleStepMode` | BOOL | 单步运行模式 |

### 2.2 状态反馈子结构 (`stStatus`)

| 字段名 | 类型 | 说明 |
| :--- | :---: | :--- |
| `iStep` | DINT | 当前工步号 (0=待机, 1=等料, 2=进料, 10=夹紧, 20=加工, 30=出料) |
| `bRunning` | BOOL | 运行中标志 |
| `bDone` | BOOL | 周期完成标志 |
| `bAlarm` | BOOL | 站级报警标志 |
| `iAlarmCode` | DINT | 报警代码 (101=进料超时, 102=夹紧超时, 103=松开超时) |

> CARD-DJ-2026-009-003（预做分支 `claude/dj009-card003`）：`stStatus` 新增 `bReadyOut`（BOOL，加工完成可出料：出料步且气缸已松开），OB1 接 FB_3001 `i_bMachineReadyOut`；`stStatus` 新增 `bProductPresent`（入料到位、加工到位或 `stSensors.arrProductSens[0..7]` 任一路为 1），接 FB_3001 `i_bProductPresent`；`stSensors` 新增 `arrProductSens`（ARRAY[0..7] OF BOOL，产品检测传感器预留 8 路，未接的保持 0）。本块不再直接写 `io_stExternal` 里的 `bMachine_ReadyIn` / `bMachine_ReadyOut`，改由 FB_3001 根据 `stStatus.bWaitMaterial` / `stStatus.bReadyOut` 发出，`io_stExternal` 对本块只读（读 `iInfeedStep`）。

