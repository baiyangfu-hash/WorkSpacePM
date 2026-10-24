# 接口文档 FB_1003_PickPlace_BufferFraming

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | FB_1003_PickPlace_BufferFraming 接口定义 |
| **文档版本** | V15.0.0 |
| **关联源码** | 03_取放料/FB_1003_PickPlace_BufferFraming.scl |
| **编制日期** | 2026-10-24 |
| **编制人** | Claude（用户待审） |
| **遵循规范** | LSP-905_SCL编程规范 |
| **依据** | 全局 `00_程序方案/接口文档_INT.md` 与 `详细设计说明书_DSN.md` |

## 1. 功能概述与接口

取放料机构 S20~S25 状态机：成对取料（前位对 = 3+4 层，后位对 = 1+2 层），Z 与 X1 两轴定位，夹爪与升降缸 Y40~Y43 统一由本 FB 写出，产生取料完成、X1 送料完成、安全区信号和取放料报警触发（F30~F33、F66~F75、F106）。

## 接口参数 (VAR_IN_OUT)

| 名称 | 类型 | 说明 |
|---|---|---|
| io_stPP | ST_PickPlace | 取放料数据 |
| io_stBridge | ST_Bridge | 站间中继 (读: 层请求 / A、B 请求 / Hold) |
| io_stMachine | ST_Machine | 模式 |
| io_stIo | ST_Io | 物理输入输出 |
| io_stAlarm | ST_Alarm | 报警 (本 FB 不直接写, 经 arrTrig 汇总) |
| io_arrAxis | ARRAY[1..3] OF ST_ServoAxis | 轴: 1 = Z, 2 = X1, 3 = X2 |

## 附：约定

所有 FB 参数仅用 `VAR_IN_OUT`（结构体）和必要的 `VAR_INPUT` 标量，不使用 `VAR_OUTPUT`；结构体字段定义见 `程序文档/PLC变量定义文档_VAR.md`，接口总表见 `00_程序方案/接口文档_INT.md` 第 5 节。
