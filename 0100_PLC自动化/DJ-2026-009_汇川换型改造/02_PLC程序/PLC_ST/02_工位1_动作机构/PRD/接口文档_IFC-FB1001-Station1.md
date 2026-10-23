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
| `io_stStation` | ST_Station1 | 工位1 全局交互结构体 (整块传递) |

### 2.1 控制指令子结构 (`stControl`)

| 字段名 | 类型 | 说明 |
| :--- | :---: | :--- |

### 2.2 状态反馈子结构 (`stStatus`)

| 字段名 | 类型 | 说明 |
| :--- | :---: | :--- |
| io_stExternal | ST_ExternalDevice | 外部设备 8步握手交握结构体 |

## 附：代码中已不存在的旧条目（待确认后删除）

| 名称 | 类型 | 说明 | 原对象 |
|---|---|---|---|
| bAutoEnable | BOOL | 【待确认】自动运行使能 (1=使能) | FB_1001_Station1 |
| bManualStart | BOOL | 【待确认】手动单步启动 | FB_1001_Station1 |
| bReset | BOOL | 【待确认】故障复位指令 | FB_1001_Station1 |
| bPause | BOOL | 【待确认】暂停运行 | FB_1001_Station1 |
| bSingleStepMode | BOOL | 【待确认】单步运行模式 | FB_1001_Station1 |
| iStep | DINT | 【待确认】当前工步号 (0=待机, 1=等料, 2=进料, 10=夹紧, 20=加工, 30=出料) | FB_1001_Station1 |
| bRunning | BOOL | 【待确认】运行中标志 | FB_1001_Station1 |
| bDone | BOOL | 【待确认】周期完成标志 | FB_1001_Station1 |
| bAlarm | BOOL | 【待确认】站级报警标志 | FB_1001_Station1 |
| iAlarmCode | DINT | 【待确认】报警代码 (101=进料超时, 102=夹紧超时, 103=松开超时) | FB_1001_Station1 |
