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
- 本机心跳：4.0s ON / 4.0s OFF 方波输出 (`bMachine_HeartbeatToUp` / `ToDown`)
- 超时保护：连续 12.0s 检测不到外部心跳电平翻转，置位 `ComFault` 并安全封锁。

## 3. 握手中途通讯故障处理（CARD-DJ-2026-009-002，对应需求说明验收项 A3）

- 进料握手在第 10～40 步时，上下游**任一侧**通讯故障（`bAnyComFault` 为 1）：当拍撤销 `bMachine_RcvModuleIdAck`、`bMachine_AllowInfeed`、`bMachine_InfeedArrived` 和 `q_bAllowInfeedAct`，步序回第 0 步。
- 出料握手在第 10～40 步时，上下游**任一侧**通讯故障：当拍撤销 `bMachine_SendModuleId`、`bMachine_OutfeedReq`、`bMachine_OutfeedArrivedAck` 和 `q_bAllowOutfeedAct`，步序回第 0 步。
- 下游断线也中止进料、上游断线也中止出料（用户 2026-10-20 答复）。第 0 步有通讯故障时不发 `bMachine_ReadyIn` / `bMachine_ReadyOut`，不开始新的握手。
- 通讯恢复后分两种情况（用户 2026-10-20 答复）：
  - 不在作业中（故障时握手在第 0 步），或者在非自动模式下中止的：对方心跳恢复翻转后，第 0 步按原逻辑重新开始握手，不需要复位。
  - 自动模式（`i_bAutoMode` 为 1）且正在作业中（第 10～40 步）被中止的：置内部锁 `s_bInfeedLock` / `s_bOutfeedLock`，通讯恢复后仍不发就绪信号，要人工复位 `i_bResetCmd` 才能重新握手。
  - 复位只在通讯已恢复时清锁：网线还断着时按复位不清锁，通讯恢复后要再按一次（用户 2026-10-20 17:40 MST 按建议批准）。清锁只认复位的上升沿：复位一直按住不松时网线接回来，锁不清，要松开再按。
  - “作业中”暂按握手进行中（第 10～40 步）算；CARD-DJ-2026-009-003 接上本机产品检测传感器后，改成“握手进行中或机器里有产品”（同上批准）。
- 断线到 12 s 心跳超时之前，读进来的对方信号保持旧值（用户 2026-10-20 确认可以接受）。
- `q_wErrorCode` 位定义（常量见 VAR CONSTANT）：

| 位 | 常量 | 含义 | 清除方式 |
|:---:|:---|:---|:---|
| 16#0001 | `ERR_INFEED_ABORT` | 进料握手第 10～40 步因通讯故障中止 | 复位 `i_bResetCmd` |
| 16#0002 | `ERR_OUTFEED_ABORT` | 出料握手第 10～40 步因通讯故障中止 | 复位 `i_bResetCmd` |
| 16#0004 | `ERR_WAIT_RESET` | 自动作业中被中止，等待人工复位 | 复位 `i_bResetCmd` |
| 16#0010 | `ERR_UP_COM` | 上游通讯故障（实时） | 故障消失即清 |
| 16#0020 | `ERR_DOWN_COM` | 下游通讯故障（实时） | 故障消失即清 |
