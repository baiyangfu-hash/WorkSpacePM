---
spec_id: INT-DJ-2026-005-PLC_ST
title: "DJ-2026-005 边框缓存机 PLC 程序接口文档"
version: "V10.0.0"
domain: plc
lifecycle: active
tags: ["接口文档", "PLC程序"]
---

# 接口文档 DJ-2026-005 边框缓存机 PLC 程序

## 1. 文档基础信息

**文档标题**：DJ-2026-005 边框缓存机 PLC 程序接口文档
**文档版本**：V10.0.0
**编制日期**：2026-10-24
**编制人**：Claude
**审核人**：用户（待审）
**遵循规范**：INT-815, LSP-905, LSP-903
**依据**：[REQ](需求分析文档_REQ.md)、[DSN](详细设计说明书_DSN.md)、[IO 表](015_IO分配表_IO.md)、[PRC](020_原程序工艺说明_PRC.md)

## 2. 版本变更记录

| 版本号 | 变更内容 | 变更人 | 变更日期 |
|--------|----------|--------|----------|
| V10.0.0 | 全部重写：按 DSN V8.0.0 的 11 个模块重新定义结构体、FB 接口、站间中继、HMI 软元件、步序常量、报警表。旧版（V9.x）中的 MES 报警字、配方管理器、心跳等条目原程序没有，已删除 | Claude | 2026-10-24 |
| V9.2.0 及更早 | Trae 版本，已废 | Trae / plc-electrical-engineer | 2026-06 ~ 09 |

## 3. 使用说明

- 本文是**编码时的唯一接口来源**：结构体字段名、FB 参数名、步序常量名以本文为准；DSN 的描述若与本文有出入，以本文为准并回头改 DSN。
- 原程序是三菱 FX5U 软元件地址，HMI（GP-Pro EX）直接访问这些地址。新程序保持**与 HMI 的语义对应**（第 7 节），实际变量到 HMI 的映射表是**另一件待办**（HMI 工程需用户导出，见 REQ Q-F）。
- 命名：`i_` 输入、`q_`/`o_` 输出、`io_` 进出、`s_` FB 内部静态、`st`/`ast`/`arr` 为结构体/结构体数组/数组、`b` BOOL、`i` INT、`d` DINT、`r` REAL。
- 步序用 `INT` + 具名常量（目标平台 TIA V19 无枚举，TEC 4.1；将来 V20+ 可原样换枚举，数值不变）。

## 4. 全局数据（GlobalVars）

### 4.1 总体结构

| 变量 | 类型 | 说明 |
|---|---|---|
| `stMachine` | `ST_Machine` | 模式、暂停、停止、状态字（FB_1001 写） |
| `stHmi` | `ST_Hmi` | HMI 命令与设定值（对应第 7 节） |
| `stIo` | `ST_Io` | 全部物理输入 / 输出映射（IO 表）。输入在 OB1 之前由硬件映射写入，输出在最后读出 |
| `stHome` | `ST_HomePrepare` | 回原点 / 准备序列状态 |
| `stManual` | `ST_Manual` | 手动 / 示教状态 |
| `stConv` | `ST_ConveyorSystem` | 4 层输送（含 `astLayer[1..4]`） |
| `stPP` | `ST_PickPlace` | 取放料（点位、对号、状态） |
| `stFeed` | `ST_Feeder` | X2 送料小车 |
| `stExt` | `ST_ExternalLink` | 组框机链路 / 打胶机握手 |
| `stBridge` | `ST_Bridge` | 站间中继信号（第 6 节） |
| `stAlarm` | `ST_Alarm` | 报警触发、锁存、分级输出、声光 |
| `astAxis` | `ARRAY[1..3] OF ST_ServoAxis` | 轴（沿用 SysLib；编号沿用现有 GlobalVars：1 = Z、2 = X1、3 = X2） |
| `fbMode … fbAlarm` | 各 FB 实例 | 见 OB1 |

> 轴编号沿用现有 GlobalVars（见 TEC），与原程序“轴 1 = X1、轴 2 = X2、轴 3 = Z”不同；IO 表里以信号名（`X1_*`、`X2_*`、`Z_*`）为准，**写代码时以名为准，不以编号为准**。

### 4.2 `ST_Machine`

| 字段 | 类型 | 方向 | 说明 | 原软元件 |
|---|---|---|---|---|
| `bManual` | BOOL | 读 | 手动模式 | M0 |
| `bHoming` | BOOL | 读 | 回原点模式 | M1 |
| `bPrepare` | BOOL | 读 | 准备模式 | M2 |
| `bAuto` | BOOL | 读 | 自动模式 | M4 |
| `bHomeDone` | BOOL | 读 | 已回原点 | M94 |
| `bFault` | BOOL | 读 | 异常（急停类） | M8 |
| `bPause` | BOOL | 读 | 暂停 | M95 |
| `bStopPending` | BOOL | 读 | 停止请求（本循环结束后退出自动） | F12 语义 |
| `bPrepareDone` | BOOL | 读 | 准备完成（一拍） | SM8044 语义 |
| `iDeviceState` | INT | 读 | D116：手动 1、回原点 2、准备 3、自动 5、待机 6、异常 8、暂停 10 | D116 |
| `bSimulate` | BOOL | 读 | 本机模拟（跳过传感器条件，沿用） | — |

### 4.3 `ST_Hmi`（HMI → PLC 命令；PLC → HMI 状态）

字段与原软元件对应关系见第 7 节，此处只列字段名：

`bManual, bAutoRun, bStop, bPause, bMute, bPrepareKey, bTeach[1..6], bJog[1..6], bSpeedUp[1..3], bSpeedDown[1..3], bPosX1[1..4], bPosX2[1..2], bGripRelease, bLiftUp, bLiftDown, bConvForce[0..20], bFeedBtn[1..4], bAutoSpeedUp, bAutoSpeedDown, bSingleSend(M510 回读), bLinkMode(M501), bContinuousSend(M502), rManualSpeed[1..3], rAutoSpeed, iAlarmNo, iDeviceState`。

### 4.4 `ST_Io`

输入、输出字段名按 [IO 表](015_IO分配表_IO.md) 的“符号名”列逐点对应（146 点），例如 `X_ZAxisHome`、`Y_ClampFront`。不在此重复；`工程资产/io_points.csv` 是机读版，生成 `ST_Io` 时以它为输入。

### 4.5 `ST_ConveyorSystem` 与 `ST_SingleLayer`

`ST_ConveyorSystem`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `astLayer` | `ARRAY[1..4] OF ST_SingleLayer` | 4 层 |
| `bAllReady` | BOOL | 4 层准备完成 |
| `bAnyRequest` | BOOL | 任一层有取料请求 |

`ST_SingleLayer`（**一层**；`1` 层 = 最下层，参见 PRC 1；层号与 F 号映射见第 9 节）：

| 分组 | 字段 | 类型 | 方向 | 说明 |
|---|---|---|---|---|
| 传感器输入 | `bPreBlock` | BOOL | 入 | 阻挡前到位传感器 |
| | `bPick1, bPick2` | BOOL | 入 | 边框取料位接近开关 1、2 |
| | `bFull1, bFull2` | BOOL | 入 | 边框满料检测 1、2 |
| | `bBlkUp1, bBlkUp2, bBlkDn1, bBlkDn2` | BOOL | 入 | 阻挡气缸上 / 下位 1、2 |
| | `bSepUp1, bSepUp2, bSepDn1, bSepDn2` | BOOL | 入 | 分料气缸上 / 下位 1、2 |
| 命令输入 | `bInitReq` | BOOL | 入 | 初始化请求（回原点预处理期间） |
| | `bAutoRun` | BOOL | 入 | 自动运行 |
| | `bHold` | BOOL | 入 | 本层保持（暂停 / 本层报警 / 全局 Hold） |
| | `bReset` | BOOL | 入 | 异常停机（M8 或进手动） |
| | `bSafeZone` | BOOL | 入 | 取料机构在安全区 |
| | `bPickDone` | BOOL | 入 | 本层取料完成（来自取放料，本层对本层） |
| | `bStopPending` | BOOL | 入 | 停止请求：本循环结束后不再开新循环（2026-10-24 编码时补，DSN 4.1） |
| 命令输出 | `bBlockDown` | BOOL | 出 | 阻挡下降命令（Y 阻挡） |
| | `bSepDown` | BOOL | 出 | 分料下降命令 |
| | `bFwd, bRev, bSlow` | BOOL | 出 | 输送正转、反转、慢速 |
| 状态输出 | `bReady` | BOOL | 出 | 准备完成 |
| | `bRequest` | BOOL | 出 | 请求取料 |
| | `iStep` | INT | 出 | 当前步（供 HMI / 测试） |
| | `bAtRest` | BOOL | 出 | 静止点（步 0），停止收尾判断用（2026-10-24 编码时补） |
| 双向 | `bUnload` | BOOL | 进出 | 退料（原 `VAR_IN_OUT 退料`） |
| 报警触发 | `arrTrig[0..8]` | ARRAY OF BOOL | 出 | 8 个气缸位置报警触发 + 1 个缺料触发，由 FB_1007 映射到 F 号（第 9 节） |

### 4.6 `ST_PickPlace`

| 字段 | 类型 | 说明 |
|---|---|---|
| `iStep` | INT | 0 未激活，20~25 = S20~S25 |
| `iPhase` | INT | 子相 0 窗口 / 1 轴运动 / 2 等待转移 |
| `iPair` | INT | 1 = 前位对（3+4 层），2 = 后位对（1+2 层） |
| `astPair[1..2]` | `ST_PairPoint` | `rXPick, rZPick, rXPlace` |
| `rZStandby` | REAL | D500 |
| `rZPlace` | REAL | D524 |
| `rAutoSpeed` | REAL | D600（范围 10000~100000） |
| `abPickDone[1..4]` | BOOL | 各层取料完成（输出给输送） |
| `abFeedDone[1..2]` | BOOL | X1 前 / 后送料完成（输出给小车） |
| `bClampFront, bClampRear` | BOOL | 夹紧命令（Y40/Y41 语义） |
| `bLiftUp, bLiftDown` | BOOL | 升降缸命令 |
| `bSafeZone` | BOOL | 输出：取料机构在安全区（给 Bridge） |
| 传感器输入 | `bClampedF1..2, bClampedR1..2, bReleasedF1..2, bReleasedR1..2, bLiftUpPos, bLiftDnPos, bProdF1..2, bProdR1..2` | BOOL | 输入映射，名称见 IO 表 |
| 报警触发 | `arrTrig[0..15]` | BOOL | F30~F33、F66~F75 的 14 个触发 + 夹紧超时 |

### 4.7 `ST_Feeder`

| 字段 | 类型 | 说明 |
|---|---|---|
| `iStep` | INT | 0~3（D760） |
| `rPosPick` | REAL | D512 |
| `rPosFeed` | REAL | D522 |
| `bReqA` | BOOL | 前位请求 A |
| `bReqB` | BOOL | 后位请求 B |
| `abEyes[1..4]` | BOOL | X72~X75 四个光电（亮 = 有料） |
| `bY44` | BOOL | 送料完成通知 / 送框信号 Y44 |
| `bY47` | BOOL | X2 在取料点 |
| `bFeedPermit` | BOOL | 出发许可（来自 FB_3001） |
| `arrTrig[0..4]` | BOOL | F90、F91、小车提示、F22、F23 |

### 4.8 `ST_ExternalLink`

| 字段 | 类型 | 说明 | 原 |
|---|---|---|---|
| `bLinkMode` | BOOL | M501：组框机联机 | M501 |
| `bContinuous` | BOOL | M502：连续送框 | M502 |
| `bSingle` | BOOL | 单套送框许可 | M510 |
| `bLinkSafetyOut` | BOOL | 本机 → 组框机：F0 或 F1~F8 | R5000.0 |
| `bPeerSafetyFault` | BOOL | 组框机 → 本机：安全异常 | R5010.0 |
| `bPeerPermit` | BOOL | 组框机 → 本机：允许送料 | R5011.0 |
| `bLinkFail` | BOOL | 通讯异常 | SB49 ∨ SB6A ∨ SB0A1 |
| `bY45, bY46` | BOOL | 组框机暂停 / 急停输出 | Y45/Y46 |
| `arrTrig[0..1]` | BOOL | F104、F105 |

### 4.9 `ST_Alarm`

| 字段 | 类型 | 说明 |
|---|---|---|
| `arrTrig` | `ARRAY[0..127] OF BOOL` | 各机构每扫描写入触发（一位一写） |
| `arrLatch` | `ARRAY[0..127] OF BOOL` | 自保持输出 |
| `bReset` | BOOL | 复位键（X100）上升沿 |
| `bFault` | BOOL | 任一 A 类 → M8 |
| `bAny` | BOOL | 任一非提示类 |
| `abHoldConv[1..4]` | BOOL | 各层保持 |
| `bHoldPP, bHoldFeeder, bHoldHome` | BOOL | 取放料 / 小车 / 回原点保持 |
| `iAlarmNo` | INT | 最小 F 号 → HMI D117（无报警为 0） |
| `bLampGreen/Yellow/Red/Buzzer/Reset` | BOOL | 声光 Y24~Y27、Y50 |

### 4.10 `ST_HomePrepare` / `ST_Manual` / `ST_Bridge`

- `ST_HomePrepare`：`iHomeStep, iPrepStep, bPreprocessDone, bAxisInitDone, bHomeDoneZ, bHomeDoneX1, bHomeDoneX2, bPrepareDone, bInitReqConv`。
- `ST_Manual`：`bJogLockZ/X1/X2`（轴禁止）、`abForce[0..20]`（输送强制位）、`bTeachWrite[1..6]`、`arrTrig[0..1]`（保留）。
- `ST_Bridge`：第 6 节全部中继信号。

## 5. FB 接口（`VAR_IN_OUT` 整体传递）

所有 FB 参数仅用 `VAR_IN_OUT`（结构体）+ 必要的 `VAR_INPUT` 标量；不使用 `VAR_OUTPUT`，结构体内的输出字段由 FB 写。统一约定：每个 FB 内部 `s_` 前缀的静态变量。

| FB | VAR_IN_OUT | 说明 |
|---|---|---|
| FB_1001_MachineMode_BufferFraming | `io_stMachine : ST_Machine`, `io_stHmi : ST_Hmi`, `io_stIo : ST_Io`, `io_stAlarm : ST_Alarm` | 模式 / D116 / 机器级报警触发 |
| FB_1005_HomePrepare_BufferFraming | `io_stHome : ST_HomePrepare`, `io_stMachine`, `io_stIo`, `io_stAlarm`, `io_astAxis : ARRAY[1..3] OF ST_ServoAxis`, `io_stBridge` | 回原点 + 准备 |
| FB_1006_ManualTeach_BufferFraming | `io_stManual : ST_Manual`, `io_stMachine`, `io_stHmi`, `io_stIo`, `io_stPP : ST_PickPlace`, `io_stFeed : ST_Feeder`, `io_astAxis` | 手动与示教 |
| FB_3001（`FB_ExternalDeviceInteraction`） | `io_stExt : ST_ExternalLink`, `io_stMachine`, `io_stHmi`, `io_stIo`, `io_stFeed`, `io_stAlarm` | 组框机链路 |
| FB_2002_StationBridge | `io_stBridge : ST_Bridge`, `io_stConv`, `io_stPP`, `io_stFeed`, `io_stMachine`, `io_stAlarm` | 中继（纯赋值） |
| FB_1007_ConveyorSystem_BufferFraming | `io_stConv : ST_ConveyorSystem`, `io_stBridge`, `io_stMachine`, `io_stIo`, `io_stAlarm` | 内含 fbL1~fbL4 |
| FB_1002_SingleLayerConveyor_BufferFraming | `io_stLayer : ST_SingleLayer` | 单层状态机；参数 `VAR_INPUT`：`i_dInitRevMs, i_dPreBlockMs, i_dSlowFeedMs, i_dReleaseOkMs, i_dReleaseNgMs, i_dStarveMs, i_dCylTimeoutMs : DINT` |
| FB_1003_PickPlace_BufferFraming | `io_stPP : ST_PickPlace`, `io_stBridge`, `io_stMachine`, `io_stIo`, `io_stAlarm`, `io_astAxis` | S20~S25 |
| FB_1004_GlueMachineFeeder_BufferFraming | `io_stFeed : ST_Feeder`, `io_stBridge`, `io_stExt`, `io_stMachine`, `io_stIo`, `io_stAlarm`, `io_astAxis` | 小车 |
| FB_2001_CommonAlarm_AllStation | `io_stAlarm : ST_Alarm`, `io_stMachine`, `io_stIo` | 锁存 / 分级 / 声光 |

所有时间参数 `DINT` 毫秒；所有位置 / 速度 `REAL`。

## 6. 站间中继（FB_2002，`ST_Bridge`）

只做赋值，**不含逻辑**。读取上一扫描输出，写给下一扫描使用（信号一拍延迟）。

| 中继信号 | 源 | 去向 | 说明 |
|---|---|---|---|
| `bSafeZone` | `stPP.bSafeZone` | 4 层 `bSafeZone` | 取料机构在安全区 |
| `abLayerReq[1..4]` | 4 层 `bRequest` | `stPP`（层请求） | 层请求 |
| `abPickDone[1..4]` | `stPP.abPickDone` | 对应层 `bPickDone` | **本层对本层**（R-CONV-06） |
| `bReqA, bReqB` | `stFeed` | `stPP` | 前位 / 后位请求 |
| `abFeedDone[1..2]` | `stPP` | `stFeed` | X1 前 / 后送料完成 |
| `abHoldConv[1..4]` | `stAlarm` | 4 层 `bHold` | 保持 |
| `bHoldPP, bHoldFeeder, bHoldHome` | `stAlarm` | 各 FB | 保持 |
| `bManual, bHoming, bPrepare, bAuto, bFault, bPause` | `stMachine` | 各 FB | 模式标志 |
| `bInitReqConv` | `stHome` | 4 层 `bInitReq` | 回原点预处理期间初始化输送 |
| `bReleaseGripperLock` | `stHome` | `stPP` | F80 期间禁止 Z 定位 |
| `bFeedPermit` | `stExt` | `stFeed` | 送框许可 |

## 7. HMI 软元件接口

### 7.1 HMI → PLC（命令与设定）

| 功能 | 原软元件 | 新字段 | 说明 |
|---|---|---|---|
| 手动 | M0 | `stHmi.bManual` | |
| 自动运行键 | M6 | `bAutoRun` | |
| 停止 | M7 | `bStop` | |
| 静音 | M9 | `bMute` | |
| 暂停 | M95 | `bPause` | |
| 速度加减 | M150~M155 | `bSpeedUp[1..3]` / `bSpeedDown[1..3]` | X1 / X2 / Z |
| 点动 | M156~M161 | `bJog[1..6]` | 正 / 反 × 3 轴 |
| X1 定位 | M162~M165 | `bPosX1[1..4]` | D510 / D520 / D540 / D550 |
| X2 定位 | M166 / M167 | `bPosX2[1..2]` | D512 / D522 |
| 示教 | M61~M66 | `bTeach[1..6]` | |
| 夹爪松开（新增） | M67 | `bGripRelease` | |
| 输送强制 | M70~M90（M80 除外） | `bConvForce[0..20]` | 阻挡 / 分料 / 正反转 / 慢速 |
| 上料按钮 | M250~M253 | `bFeedBtn[1..4]` | |
| 自动速度加减 | M700 / M701 | `bAutoSpeedUp/Down` | |
| 送框模式 | M501 / M502 | `bLinkMode / bContinuousSend` | |
| 强置选项 | M515 | `bBlinkOpt` | 沿用灯闪选项 |
| 速度设定 | D2000 / D2002 / D2004 | `rManualSpeed[1..3]` | 范围 500~5000 |
| 自动速度 | D600 | `rAutoSpeed` | 范围 10000~100000 |
| 待机点 | D500 | `rZStandby` | |
| 点位寄存器 | D510~D554 | `stPP.astPair[...]`、`rPosPick/rPosFeed` | 见 7.4 |

### 7.2 PLC → HMI（状态）

| 原 | 新字段 | 说明 |
|---|---|---|
| D116 | `iDeviceState` | 第 4.2 节 |
| D117 | `iAlarmNo` | 最小报警号（原程序未使用，新增） |
| D760 | `stFeed.iStep` | 小车步 |
| M94 | `bHomeDone` | |
| 模式灯 | `bManual…bAuto` | |
| 送框状态 | `bSingle(M510)`、`bPeerSafetyFault`、`bPeerPermit`、`bLinkFail` | 7.3 |

### 7.3 组框机链路规则

| 规则 | 内容 |
|---|---|
| M501 = 0 | 不联机：送框不受链路约束，只受 X76（打胶机允许）约束 |
| M501 = 1 且 M502 = 1 | 连续送框 |
| M501 = 1 且 M502 = 0 | 单套送框：`bPeerPermit` 上升沿置 `bSingle`，下降沿或 Y44 成立时复位 |
| 组框机安全异常（M501 ∧ ¬通讯异常 ∧ R5010.0） | 禁止 X2 定位、转移禁止（手动除外）、F104（A 类） |
| 通讯异常（M501 ∧ SB49/SB6A/SB0A1） | 联锁解除，只 F105（提示） |
| Y45 / Y46 | 原程序被屏蔽；新程序按 DSN 8 恢复，待现场确认（REQ R-EXT-04） |

### 7.4 点位寄存器

| 寄存器 | 含义 | 新位置 |
|---|---|---|
| D500 | Z 待机点 | `rZStandby` |
| D510 / D520 | X1 前位取 / 放 | `astPair[1].rXPick / rXPlace` |
| D514 / D524 | Z 取 / 放 | `astPair[1].rZPick` / `rZPlace`（放共用） |
| D540 / D550 | X1 后位取 / 放 | `astPair[2].rXPick / rXPlace` |
| D544 | Z 后位取 | `astPair[2].rZPick` |
| D512 / D522 | X2 取 / 送 | `rPosPick / rPosFeed` |

> 现场点位值是 PDF 快照；示教会覆盖。点位断电保持：放在 `GlobalVars` 的 `VAR RETAIN`（TEC 7）。

## 8. 步序常量

具名常量放各 FB 内 `VAR CONSTANT`；`ST_*` 结构体里的 `iStep` 为 `INT`。若将来换枚举，下表“常量”列即枚举成员。

| 模块 | 常量 | 值 |
|---|---|---|
| 输送 | `STEP_IDLE / INIT_WAIT / INIT_RUN / SEND_ON / ARRIVE / SEPARATE / BLOCK_DOWN / SLOW_FEED / REQUEST / RELEASE` | 0 / 1 / 2 / 10 / 20 / 30 / 50 / 60 / 70 / 80 |
| 取放料 | `STEP_NONE / S20 … S25` | 0 / 20 … 25 |
| 取放料子相 | `PH_WINDOW / PH_MOVE / PH_WAIT` | 0 / 1 / 2 |
| 小车 | `STEP_HOME / WAIT_FULL / TO_FEED / SEND` | 0 / 1 / 2 / 3 |
| 回原点 | `HM_IDLE / PRE / Z / XX / DONE` | 0 / 10 / 20 / 30 / 40 |
| 准备 | `PR_IDLE / GRIP / Z / X1 / X2 / WAIT_CONV / DONE` | 0 / 10 / 20 / 30 / 40 / 50 / 60 |
| 设备状态 | `ST_MANUAL / HOMING / PREPARE / AUTO / STANDBY / FAULT / PAUSE` | 1 / 2 / 3 / 5 / 6 / 8 / 10 |

## 9. 报警表（FB_2001，F0~F127）

| F 号 | 含义 | 类 | 产生者 | 延时 |
|---|---|---|---|---|
| F0 | 急停 X101 | A | FB_1001 | 0 |
| F1~F8 | 门 X140~X147 | A | FB_1001 | 0 |
| F9~F11 | X1 / X2 / Z 伺服报警 | A | FB_1001 | 0 |
| F12 | HMI 停止 | 提示 | FB_1001 | 0 |
| F13~F16 | 变频器 1~4 | A | FB_1001 | 0 |
| F20 / F21 | Z 轴前后极限（自动时） | B 取放料 | FB_1001 | 0 |
| F22 / F23 | X2 前后极限（自动时） | B 小车 | FB_1001 | 0 |
| F24 / F25 | X1 前后极限（自动时） | B 取放料 | FB_1001 | 0 |
| F30 / F31 | 后夹爪夹紧但前夹料产品检测 1 / 2 灭（原命名交叉） | B 取放料 | FB_1003 | 5 s |
| F32 / F33 | 前夹爪夹紧但后夹料产品检测 1 / 2 灭 | B 取放料 | FB_1003 | 5 s |
| F34~F41 | 1 层阻挡上 1、上 2、下 1、下 2；分料上 1、上 2、下 1、下 2 | B 输送 1 | FB_1002 | 5 s |
| F42~F49 | 2 层（+8） | B 输送 2 | FB_1002 | 5 s |
| F50~F57 | 3 层（+16） | B 输送 3 | FB_1002 | 5 s |
| F58~F65 | 4 层（+24） | B 输送 4 | FB_1002 | 5 s |
| F66~F73 | 夹爪：后夹紧 1、2，后松开 1、2，前夹紧 1、2，前松开 1、2 | B 取放料 | FB_1003 | 5 s |
| F74 / F75 | 升降缸上 / 下位未到 | B 取放料 | FB_1003 | 5 s |
| F80 | 回原点：夹爪有料 | B 回原点 | FB_1005 | 0 |
| F81 | 回原点：小车有料 | B 回原点 | FB_1005 | 0 |
| F90 / F91 | 小车前 / 后光电异常 | B 小车 | FB_1004 | 1 s |
| F100~F103 | 缺料：F100 = 4 层、F103 = 1 层 | B 输送（该层） | FB_1002 | 10 s |
| F104 | 组框机安全异常 | A | FB_3001 | 0 |
| F105 | 组框机通讯异常 | 提示 | FB_3001 | 0 |
| F106 | 夹紧超时（新增，R-PP-05） | B 取放料 | FB_1003 | 5 s |
| F107 | 小车等待 X102 超时（新增，R-FEED-05） | 提示 | FB_1004 | 10 s |
| F108~F127 | 预留 | — | — | — |

**分类含义**：A = 进 M8（急停类，清步序、清回原点完成）；B = 只让对应机构 Hold，其余继续；提示 = 只显示不停机。任一非提示类点亮红灯 / 蜂鸣。
**锁存规则**：触发 → 立即锁存；复位键上升沿且触发已消失 → 清除；F20~F25 仅自动时触发，退出自动后可复位。

## 10. 变更与待确认

- `ST_Io` 字段依赖 IO 表的最终版（待现场核对 X160 / X161、Y45 / Y46、X103 等，见 IO 表末尾）。
- HMI 软元件映射（GP-Pro EX 变量名）另外成表，不在本文件范围。
- F106 / F107 为新增号，评审时请确认可占用。
