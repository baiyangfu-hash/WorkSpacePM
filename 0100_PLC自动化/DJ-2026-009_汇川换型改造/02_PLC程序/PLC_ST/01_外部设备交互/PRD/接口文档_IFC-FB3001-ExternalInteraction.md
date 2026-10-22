---
spec_id: INT-815
title: "FB_3001_ExternalInteraction 接口文档 (IFC)"
version: "V1.2.0"
status: "正式"
created: "2026-08-22"
domain: plc
---

# 接口文档 (IFC) - FB_3001_ExternalInteraction 通用外部设备交互

## 1. 接口功能定义
本功能块遵循 `STD-820` 规范，实现与上游进料流水线及下游出料流水线的 8 步双向闭环交握，并内置 4s ON / 4s OFF 心跳监视与 12s 超时诊断。

## 2. 输入输出引脚表

| 变量名 | 类型 | 方向 | 说明 |
|:---|:---:|:---:|:---|
| `i_bEnable` | BOOL | VAR_INPUT | 功能块总使能 (OB1 接 FB_1030 运行许可 q_bSafeToRun, CARD-DJ-2026-009-004) |
| `i_bAutoMode` | BOOL | VAR_INPUT | 自动运行模式 |
| `i_bResetCmd` | BOOL | VAR_INPUT | 故障复位指令 (OB1: FB_1030 运行复位脉冲, 或运行许可中的普通复位, CARD-DJ-2026-009-004) |
| `i_bMachineReadyIn` | BOOL | VAR_INPUT | 本机进料就绪 (工位空闲) |
| `i_bMachineReadyOut` | BOOL | VAR_INPUT | 本机出料就绪 (加工完成) |
| `i_bInfeedArrivedSens` | BOOL | VAR_INPUT | 本机进料到位光电传感器 |
| `i_bProductPresent` | BOOL | VAR_INPUT | 本机有产品 (产品检测传感器, CARD-DJ-2026-009-003) |
| `q_bAllowInfeedAct` | BOOL | VAR_OUTPUT | 触发本机进料动作输出 |
| `q_bAllowOutfeedAct` | BOOL | VAR_OUTPUT | 触发本机出料动作输出 |
| `q_bUpstreamDone` | BOOL | VAR_OUTPUT | 本次进料交握事务完成脉冲 |
| `q_bDownstreamDone` | BOOL | VAR_OUTPUT | 本次出料交握事务完成脉冲 |
| `q_bComAlarm` | BOOL | VAR_OUTPUT | 外部通讯中断综合报警 |
| `q_wErrorCode` | WORD | VAR_OUTPUT | 故障诊断字 |
| `io_stExternal` | ST_ExternalDevice | VAR_IN_OUT | STD-820 通用外部对接数据总线 |
| `io_sMachineModuleID` | STRING[32] | VAR_IN_OUT | 本机 ID (组件 ID 第 2 格, 全局变量须断电保持 RETAIN) |
| `io_stIdHmi` | ST_ModuleIdHmi | VAR_IN_OUT | 组件 ID 人工操作与时间参数 (HMI) |

V1.2.0（CARD-DJ-2026-009-003）：删除 `i_sSendModuleID`（OB1 从来没接过；下游 ID 改由本机 ID 在“准备好出料”时转存，见 DSN 第 4 节），新增 `i_bProductPresent`、`io_sMachineModuleID`、`io_stIdHmi`。`q_bUpstreamDone` / `q_bDownstreamDone` 改为只保持一个扫描周期。

## 3. 常量（VAR CONSTANT，单独列出）

| 常量名 | 值 | 含义 |
|:---|:---:|:---|
| `ERR_INFEED_ABORT` | 16#0001 | 进料握手第 10～40 步中止（通讯故障或失去使能），保持到复位 |
| `ERR_OUTFEED_ABORT` | 16#0002 | 出料握手第 10～40 步中止（通讯故障或失去使能），保持到复位 |
| `ERR_WAIT_RESET` | 16#0004 | 自动作业中被中止，等待人工复位 |
| `ERR_UP_COM` | 16#0010 | 上游通讯故障（实时） |
| `ERR_DOWN_COM` | 16#0020 | 下游通讯故障（实时） |
| `ERR_ID_EMPTY` | 16#0040 | 进料第 20 步上游 ID 不合格（现只判空），等人工放行或补录（实时） |
| `ERR_ID_CHECK` | 16#0080 | 握手中途中止，ID 待人工核对（HMI 拷入/补录/清空后清，复位不清） |
| `ID_CHECK_OK` | 16#0000 | `FC_3003_CheckModuleId` 返回 0 = 合格 |
| `DEF_LEAVE_MS` | 2000 | 产品离开判定时间设定为 0 时按 2000 ms |
| `DEF_IDLE_MS` | 20000 | 无产品自动清本机 ID 时间设定为 0 时按 20000 ms（暂定） |
| `STEP_ID_INVOLVED` | 20 | 第 20 步起中止的握手要人工核对 ID |
| `HB_HALF_MS` | 4000 | 心跳半周期（4 s 亮 / 4 s 灭），安全区常量（CARD-DJ-2026-009-004，原为普通变量 `s_dHeartbeatPulse`） |
| `HB_TIMEOUT_MS` | 12000 | 对方心跳超时阈值，安全区常量（CARD-DJ-2026-009-004，原为普通变量 `s_dHbTimeoutMs`） |

时间参数用 DINT 毫秒写；共享库 `FB_TON` V3.0.0 起按真实毫秒计时（分支 `claude/syslib-timer-ms`）。

V1.3.0（CARD-DJ-2026-009-004 预做，安全区待签字）：OB1 把 `i_bEnable` 从急停按钮点改接 `FB_1030_SafetyManager.q_bSafeToRun`（开安全门时按钮点仍为 1，原来握手照走）；`i_bResetCmd` 改为 `q_bRunResetPulse OR (q_bSafeToRun AND 原复位来源)`，安全停机后不再一按就清；心跳两个时间改为 `VAR CONSTANT`（规范 0.4、9）。

## 4. 调用的函数

| FC 名 | 用途 |
|:---|:---|
| `FC_3003_CheckModuleId` | 组件 ID 合格检查（R5；现只判空） |
