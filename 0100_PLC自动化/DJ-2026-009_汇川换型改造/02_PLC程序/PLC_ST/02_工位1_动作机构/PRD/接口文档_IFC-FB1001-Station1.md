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

## 2. 输入输出引脚表

| 变量名 | 类型 | 方向 | 说明 |
|:---|:---:|:---:|:---|
| `io_stStation` | ST_Station1 | VAR_IN_OUT | 工位1 全局交互结构体 (整块传递) |
| `io_stExternal` | ST_ExternalDevice | VAR_IN_OUT | 外部设备 8步握手交握结构体 |

## 3. 结构体字段（ST_Station1，定义见 ST_Station1.scl）

控制指令 stControl：

| 字段 | 类型 | 说明 |
| :--- | :---: | :--- |
| bAutoEnable | BOOL | 自动运行使能 (1=使能) |
| bManualStart | BOOL | 手动单步启动 |
| bReset | BOOL | 故障复位指令 |
| bPause | BOOL | 暂停运行 |
| bSingleStepMode | BOOL | 单步运行模式 |
| bSafeToRun | BOOL | 运行许可，OB1 每扫描从 FB_1030 q_bSafeToRun 写入（CARD-DJ-2026-009-004） |

状态反馈 stStatus：

| 字段 | 类型 | 说明 |
| :--- | :---: | :--- |
| iStep | DINT | 当前工步号 (0=待机, 1=等料, 2=进料, 10=夹紧, 20=加工, 30=出料, 99=故障) |
| bRunning | BOOL | 运行中标志 |
| bDone | BOOL | 周期完成标志 |
| bAlarm | BOOL | 站级报警标志 |
| iAlarmCode | DINT | 报警代码 (101=进料超时, 102=夹紧超时, 103=出料超时, 104=缩回超时) |
| bFrozen | BOOL | 安全停机，步序冻结在断点等续跑（CARD-DJ-2026-009-004） |
| bMotionStopped | BOOL | 动作完全停止：电机无请求且不转、两个气缸都在端点；接 FB_1030 i_bMotionStopped（开门条件） |

## 4. 常量（CONST，单独列出）

| 常量名 | 值 | 含义 |
|:---|:---:|:---|
| `CYL1_RETRACT_ON_STOP` | FALSE | 夹紧气缸停机（急停/开门/断线/报警/离开自动）时：FALSE=保持当前命令，TRUE=发缩回。按 IO 表逐阀定，阀型未定前按保持 |
| `CYL2_RETRACT_ON_STOP` | FALSE | 顶升气缸，同上 |

## 5. 安全停机与断点续跑（CARD-DJ-2026-009-004 预做，安全区待签字）

- `stControl.bSafeToRun` = 0（急停、开门、继电器故障、总线断，或上电后还没两次复位 + 按启动）：同一扫描电机请求清零，气缸按第 4 节常量处理，**步序冻结不回零**（3Sun 断点续跑，规范 2.5，用户 10-21 定）。
- 运行许可回来（两次复位隔 10 s + 按启动）后从冻结的步接着走；冻结期间工步/加工计时停止，续跑时该步超时从头计。
- 离开自动或站级报警仍按原逻辑处理（回待机/故障步），但气缸不再一刀切强制缩回（原第 93～96 行），改按第 4 节常量（规范 2.3 重审）。

> CARD-DJ-2026-009-003（预做分支 `claude/dj009-card003`）：`stStatus` 新增 `bReadyOut`（BOOL，加工完成可出料：出料步且气缸已松开），OB1 接 FB_3001 `i_bMachineReadyOut`；`stStatus` 新增 `bProductPresent`（入料到位、加工到位或 `stSensors.arrProductSens[0..7]` 任一路为 1），接 FB_3001 `i_bProductPresent`；`stSensors` 新增 `arrProductSens`（ARRAY[0..7] OF BOOL，产品检测传感器预留 8 路，未接的保持 0）。本块不再直接写 `io_stExternal` 里的 `bMachine_ReadyIn` / `bMachine_ReadyOut`，改由 FB_3001 根据 `stStatus.bWaitMaterial` / `stStatus.bReadyOut` 发出，`io_stExternal` 对本块只读（读 `iInfeedStep`）。

