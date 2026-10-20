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

- 进料握手在第 10～40 步时，只要 `bUpstreamComFault` 为 1：当拍撤销 `bMachine_RcvModuleIdAck`、`bMachine_AllowInfeed`、`bMachine_InfeedArrived` 和 `q_bAllowInfeedAct`，步序回第 0 步；第 0 步因通讯故障不再发 `bMachine_ReadyIn`，不会重新开始握手。
- 出料握手在第 10～40 步时，只要 `bDownstreamComFault` 为 1：当拍撤销 `bMachine_SendModuleId`、`bMachine_OutfeedReq`、`bMachine_OutfeedArrivedAck` 和 `q_bAllowOutfeedAct`，步序回第 0 步；第 0 步因通讯故障不再发 `bMachine_ReadyOut`。
- 进料只看上游故障、出料只看下游故障；第 0 步是否开始新的握手仍按原逻辑看 `bAnyComFault`（任一侧故障都不开始）。
- 通讯恢复（对方心跳重新翻转）后，第 0 步按原逻辑重新开始握手，不需要复位。
- `q_wErrorCode` 位定义（常量见 VAR CONSTANT）：

| 位 | 常量 | 含义 | 清除方式 |
|:---:|:---|:---|:---|
| 16#0001 | `ERR_INFEED_ABORT` | 进料握手第 10～40 步因上游通讯故障中止 | 复位 `i_bResetCmd` |
| 16#0002 | `ERR_OUTFEED_ABORT` | 出料握手第 10～40 步因下游通讯故障中止 | 复位 `i_bResetCmd` |
| 16#0010 | `ERR_UP_COM` | 上游通讯故障（实时） | 故障消失即清 |
| 16#0020 | `ERR_DOWN_COM` | 下游通讯故障（实时） | 故障消失即清 |
