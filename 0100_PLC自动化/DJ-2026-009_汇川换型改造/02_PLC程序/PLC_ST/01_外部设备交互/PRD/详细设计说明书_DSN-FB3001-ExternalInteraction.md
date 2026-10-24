---
spec_id: DES-021
title: "FB_3001_ExternalInteraction 详细设计说明书 (DSN)"
version: "V1.0.0"
status: "正式"
created: "2026-08-22"
domain: plc
---

# 详细设计说明书 (DSN) - FB_3001_ExternalInteraction

## 1. 上游进料 8 步状态机
- Step 0: 广播 `bMachine_ReadyIn (1)`，等待 `bUpstream_LineReady (2)`
- Step 10: 收到 `bUpstream_SendModuleId (3)`，锁存 ID 并回传 `bMachine_RcvModuleIdAck (4)`
- Step 20: 给出 `bMachine_AllowInfeed (5)`，等待 `bUpstream_InfeedReq (6)` 并启动电机
- Step 30: 到位光电接通，输出 `bMachine_InfeedArrived (7)`
- Step 40: 收到 `bUpstream_InfeedArrivedAck (8)`，复位握手信号，事务完成

## 2. 心跳与超时机制
- 本机心跳：4.0s ON / 4.0s OFF 方波输出 (`bMachine_HeartbeatToUp` / `ToDown`)。做法：`s_tHbToggle` 自复位，每 4 s 出一个单周期脉冲，用这个脉冲翻转 `s_bHbState`，再把 `s_bHbState` 输出（CARD-DJ-2026-009-003 修正：原来直接输出定时器 Q，心跳只亮一个扫描周期）。失去使能时心跳输出 0。
- 超时保护：连续 12.0s 检测不到外部心跳电平翻转，置位 `ComFault` 并安全封锁。

## 3. 握手中途通讯故障处理（CARD-DJ-2026-009-002，对应需求说明验收项 A3）

- 进料握手在第 10～40 步时，上下游**任一侧**通讯故障（`bAnyComFault` 为 1）：当拍撤销 `bMachine_RcvModuleIdAck`、`bMachine_AllowInfeed`、`bMachine_InfeedArrived` 和 `q_bAllowInfeedAct`，步序回第 0 步。
- 出料握手在第 10～40 步时，上下游**任一侧**通讯故障：当拍撤销 `bMachine_SendModuleId`、`bMachine_OutfeedReq`、`bMachine_OutfeedArrivedAck` 和 `q_bAllowOutfeedAct`，步序回第 0 步。
- 下游断线也中止进料、上游断线也中止出料（用户 2026-10-20 答复）。第 0 步有通讯故障时不发 `bMachine_ReadyIn` / `bMachine_ReadyOut`，不开始新的握手。
- 通讯恢复后分两种情况（用户 2026-10-20 答复）：
  - 不在作业中（故障时握手在第 0 步），或者在非自动模式下中止的：对方心跳恢复翻转后，第 0 步按原逻辑重新开始握手，不需要复位。
  - 自动模式（`i_bAutoMode` 为 1）且正在作业中（第 10～40 步）被中止的：置内部锁 `s_bInfeedLock` / `s_bOutfeedLock`，通讯恢复后仍不发就绪信号，要人工复位 `i_bResetCmd` 才能重新握手。
  - 复位只在通讯已恢复时清锁：网线还断着时按复位不清锁，通讯恢复后要再按一次（用户 2026-10-20 17:40 MST 按建议批准）。清锁只认复位的上升沿：复位一直按住不松时网线接回来，锁不清，要松开再按。
  - “作业中”= 握手进行中（第 10～40 步）**或机器里有产品**（`i_bProductPresent` 为 1，CARD-DJ-2026-009-003 起生效，同上批准）。握手在第 0 步但机器里有产品时出现通讯故障，自动模式下置出料锁 `s_bOutfeedLock`：产品要出料前须人工复位。
- 断线到 12 s 心跳超时之前，读进来的对方信号保持旧值（用户 2026-10-20 确认可以接受）。
- `q_wErrorCode` 位定义（常量见 VAR CONSTANT）：

| 位 | 常量 | 含义 | 清除方式 |
|:---:|:---|:---|:---|
| 16#0001 | `ERR_INFEED_ABORT` | 进料握手第 10～40 步因通讯故障中止 | 复位 `i_bResetCmd` |
| 16#0002 | `ERR_OUTFEED_ABORT` | 出料握手第 10～40 步因通讯故障中止 | 复位 `i_bResetCmd` |
| 16#0004 | `ERR_WAIT_RESET` | 自动作业中被中止，等待人工复位 | 复位 `i_bResetCmd` |
| 16#0010 | `ERR_UP_COM` | 上游通讯故障（实时） | 故障消失即清 |
| 16#0020 | `ERR_DOWN_COM` | 下游通讯故障（实时） | 故障消失即清 |
| 16#0040 | `ERR_ID_EMPTY` | 进料第 20 步上游 ID 不合格，等人工放行或补录（实时） | 放行、补录或 ID 合格即清 |
| 16#0080 | `ERR_ID_CHECK` | 握手第 20～40 步中止，ID 待人工核对 | HMI 拷入 / 补录 / 清空（复位不清） |

- 失去使能（`i_bEnable` 为 0，OB1 接急停回路正常信号）时，握手在第 10～40 步的按中途中止处理（记中止位、自动模式下置锁、第 20 步起要人工核对 ID），并撤销全部允许信号和动作输出 `q_bAllowInfeedAct` / `q_bAllowOutfeedAct`（原来不使能时不清动作输出，CARD-DJ-2026-009-003 一并处理）。
- `q_bUpstreamDone` / `q_bDownstreamDone` 只保持一个扫描周期（原来置 1 后从不清 0）。

## 4. 组件 ID 三格存储（CARD-DJ-2026-009-003 草稿，规则 R1～R6，用户 2026-10-20 答复）

产品流转：上游 ID → 本机 ID → 下游 ID。

| 格 | 变量 | 谁写 / 谁读 |
|:---|:---|:---|
| 上游 ID | `io_stExternal.stUpstream.sRcvModuleID` | 上游写（FB_3002 从寄存器读入），本机只读 |
| 本机 ID | `io_sMachineModuleID`（OB1 接 `GlobalVars.sMachineModuleID`，须断电保持 RETAIN） | 本机 |
| 下游 ID | `io_stExternal.stDownstream.sSendModuleID` | 本机写，下游读（FB_3002 写到寄存器） |

| 规则 | 程序做法 |
|:---|:---|
| R1 到位时上游 → 本机 | 进料第 10 步收到“上游传 ID”时锁存上游 ID（`s_sInfeedId`），第 30 步进料到位光电亮时拷入本机 ID。锁存是为了防止上游提前清寄存器，拷入的仍是第 10 步确认收到的那个上游 ID |
| R2 加工完成准备出料时本机 → 下游 | 出料第 0 步本机发“准备好出料”（`bMachine_ReadyOut` 为 1）期间把本机 ID 转存到下游 ID；第 10 步起不再改，下游读到的就是这个值 |
| R3 产品离开清下游 ID | ① 出料握手完成（第 40 步下游撤销到位）清下游 ID，本机 ID 一起清（用户答复）；② 出料第 30/40 步（已发出料请求）本机产品传感器持续检测不到产品超过 `dLeaveTimeMs`（0 按 2000 ms）清下游 ID，本机 ID 留给 R6 处理 |
| R4 异常交人工 | 握手第 20～40 步中止（通讯故障或失去使能）时不自动改 ID，置 `ERR_ID_CHECK` 报警；人工在 HMI 上“拷入”（上游 → 本机）、“补录”或“清空”后报警清除 |
| R5 空 ID 不许进料 | 第 20 步用 `FC_3003_CheckModuleId` 检查锁存的上游 ID，不合格时不发“允许进料”，置 `ERR_ID_EMPTY`；HMI“放行”只对这一次进料有效；HMI“补录”的 ID 本身检查合格才生效，同时作为本次进料的 ID |
| R6 本机 ID 断电保持、长时间无产品自动清 | 本机 ID 放在断电保持区；自动模式下进出料握手都在第 0 步、检测不到产品超过 `dIdleClearMs`（0 按 20000 ms，暂定）自动清；HMI“清空”随时可清 |

HMI 四个命令（`io_stIdHmi.bCmdCopyFromUp` / `bCmdManualEntry` / `bCmdRelease` / `bCmdClear`）由 HMI 置 1、PLC 处理后清 0；不使能时也处理。PLC 不做权限，权限由 HMI 权限动画处理（做 HMI 原型时一起做）。

**计时提醒**：`s_tLeaveTimer` / `s_tIdleTimer` 用共享库 `FB_TON`，参数按毫秒写；共享库目前按扫描次数计数，实际时长要等共享库定时器修复卡。
