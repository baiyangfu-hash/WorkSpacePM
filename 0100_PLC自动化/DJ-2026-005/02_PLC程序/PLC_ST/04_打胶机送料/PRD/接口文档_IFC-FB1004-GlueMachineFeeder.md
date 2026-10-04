# 接口文档 FB_1004_GlueMachineFeeder_BufferFraming

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | FB_1004 打胶机送料接口定义 |
| **文档版本** | V8.1.0 |
| **关联源码** | 04_打胶机送料/FB_1004_GlueMachineFeeder_BufferFraming.scl |
| **编制日期** | 2026-05-17 |
| **编制人** | Trae |
| **遵循规范** | LSP-905 |
| **数据来源** | 源程序功能基线_SRC-DJ-2026-005-V1.0.0 |

## 1. 功能概述

X2轴横移+打胶机交互控制。4步D760状态机，收到取放料放料完成后直接去取料位取边框，再送料到打胶机位置交互。

## 2. 状态机步序常量(D760)

| 常量名 | 值 | 步骤名 | 说明 |
|--------|---|--------|------|
| D760_IDLE | 0 | 空闲待机 | 等待FB_1003放料完成 |
| D760_MOVE_TO_PICKUP | 1 | X2→取料位 | 移动到取料点D620 |
| D760_MOVE_TO_GLUE | 2 | X2→打胶机送料 | 到D630,关Y47,等X76发Y44,等X102 |
| D760_RETURN_STANDBY | 3 | X2→待机位 | 返回D610,开Y47 |

## 3. 接口参数 (VAR_IN_OUT)

| 名称 | 类型 | 说明 |
|---|---|---|
| io_stFeeder | ST_GlueFeeder | 打胶送料小车工站数据结构体 |
| io_stX2Axis | ST_ServoAxis | X2轴(送料横移) 对象化标准接口 |

结构体 `ST_GlueFeeder`、`ST_ServoAxis` 的字段不在本文档展开，统一在 `程序文档/PLC变量定义文档_VAR.md` 对应结构体的小节维护（接口字段只在一处维护，`plc docs check` 会核对）。

## 4. 状态机伪代码

```
CASE q_iCurrentState OF
  D760_IDLE: (* 0 *)
    q_bX2AxisMoveAbsReq := FALSE;
    q_bAllowPickup := FALSE;
    q_bSafetyZoneSignal := FALSE;  (* 安全区开放 *)
    IF i_bPlaceDone THEN
      q_iCurrentState := D760_MOVE_TO_PICKUP;
    END_IF;

  D760_MOVE_TO_PICKUP: (* 1: X2→取料点D620 *)
    q_rX2AxisTargetPos := rPickupPos;       (* D620 *)
    q_bX2AxisMoveAbsReq := TRUE;
    IF i_bX2AxisInPos THEN
      q_iCurrentState := D760_MOVE_TO_GLUE;
    END_IF;

  D760_MOVE_TO_GLUE: (* 2: X2→放料点D630，交互 *)
    q_rX2AxisTargetPos := rGluePlacePos;    (* D630 *)
    q_bX2AxisMoveAbsReq := TRUE;
    IF i_bX2AxisInPos THEN
      q_bSafetyZoneSignal := TRUE;           (* 关安全区Y47 *)
      IF i_bGlueMachineAllowFeed THEN
        q_bAllowPickup := TRUE;              (* 发Y44 *)
      END_IF;
      IF i_bGlueMachinePickupComplete THEN
        q_bAllowPickup := FALSE;
        q_iCurrentState := D760_RETURN_STANDBY;
      END_IF;
    END_IF;

  D760_RETURN_STANDBY: (* 3: X2→待机位D610 *)
    q_rX2AxisTargetPos := rStandbyPos;      (* D610 *)
    q_bX2AxisMoveAbsReq := TRUE;
    IF i_bX2AxisInPos THEN
      q_bSafetyZoneSignal := FALSE;          (* 开安全区 *)
      q_iCurrentState := D760_IDLE;
    END_IF;
END_CASE;
```

## 5. 报警码

| 码 | 含义 |
|:--:|------|
| 201 | X2轴伺服故障 |
| 202 | X2轴限位触发 |
| 203 | X2轴移动超时 |
| 204 | 安全区传感器异常 |
| 205 | 送料平台有边框(回原点阻塞) |

## 6. 关联文档

| 文档 | 路径 |
|------|------|
| DSN | 详细设计说明书_DSN-FB1004-GlueMachineFeeder-V6.0.0.md |
| CHG | 变更记录_CHG-FB1004-GlueMachineFeeder-V6.0.0.md |
| UM | 使用说明_UM-FB1004-GlueMachineFeeder-V6.0.0.md |
