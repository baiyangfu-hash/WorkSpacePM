---
spec_id: INT-815
title: "FB_3001_ExternalInteraction 接口文档 (IFC)"
version: "V1.0.0"
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
| `i_bEnable` | BOOL | VAR_INPUT | 功能块总使能 |
| `i_bAutoMode` | BOOL | VAR_INPUT | 【待确认】自动运行模式 |
| `i_bMachineReadyIn` | BOOL | VAR_INPUT | 本机进料就绪 (工位空闲) |
| `i_bMachineReadyOut`| BOOL | VAR_INPUT | 本机出料就绪 (加工完成) |
| `i_bInfeedArrivedSens`| BOOL | VAR_INPUT | 本机进料到位光电传感器 |
| `i_sSendModuleID` | STRING[32] | VAR_INPUT | 【待确认】本机待发出的组件 ID |
| `q_bAllowInfeedAct` | BOOL | VAR_OUTPUT | 【待确认】触发本机进料动作输出 |
| `q_bAllowOutfeedAct` | BOOL | VAR_OUTPUT | 【待确认】触发本机出料动作输出 |
| `q_bUpstreamDone` | BOOL | VAR_OUTPUT | 【待确认】本次进料交握事务完成脉冲 |
| `q_bDownstreamDone` | BOOL | VAR_OUTPUT | 【待确认】本次出料交握事务完成脉冲 |
| `q_bComAlarm` | BOOL | VAR_OUTPUT | 【待确认】外部通讯中断综合报警 |
| `io_stExternal` | ST_ExternalDevice | VAR_IN_OUT | STD-820 通用外部对接数据总线 |
| i_bResetCmd | BOOL | VAR_INPUT | 【待确认】故障复位指令 |
| q_wErrorCode | WORD | VAR_OUTPUT | 【待确认】故障诊断字 |
