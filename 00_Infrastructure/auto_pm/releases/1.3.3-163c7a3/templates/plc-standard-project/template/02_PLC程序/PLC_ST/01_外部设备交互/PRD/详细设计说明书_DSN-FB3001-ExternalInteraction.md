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
