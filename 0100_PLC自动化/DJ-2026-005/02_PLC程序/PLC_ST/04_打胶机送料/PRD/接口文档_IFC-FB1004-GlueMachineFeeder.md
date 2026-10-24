# 接口文档 FB_1004_GlueMachineFeeder_BufferFraming

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | FB_1004_GlueMachineFeeder_BufferFraming 接口定义 |
| **文档版本** | V15.0.0 |
| **关联源码** | 04_打胶机送料/FB_1004_GlueMachineFeeder_BufferFraming.scl |
| **编制日期** | 2026-10-24 |
| **编制人** | Claude（用户待审） |
| **遵循规范** | LSP-905_SCL编程规范 |
| **依据** | 全局 `00_程序方案/接口文档_INT.md` 与 `详细设计说明书_DSN.md` |

## 1. 功能概述与接口

X2 送料小车 4 步（D760：0 回取料点、1 等满、2 去送料点、3 等打胶机取走），产生前位 / 后位请求 A / B、Y44 抓料可、Y47 安全区信号和小车报警触发（F90、F91、F107）。

## 接口参数 (VAR_IN_OUT)

| 名称 | 类型 | 说明 |
|---|---|---|
| io_stFeed | ST_Feeder | 小车数据 |
| io_stBridge | ST_Bridge | 站间中继 (读: X1 送料完成 / 取放料在 S20 / Z 待机点 / Hold) |
| io_stExt | ST_ExternalLink | 组框机链路 (读) |
| io_stMachine | ST_Machine | 模式 |
| io_stIo | ST_Io | 物理输入输出 |
| io_stAlarm | ST_Alarm | 报警 (本 FB 不直接写, 经 arrTrig 汇总) |
| io_arrAxis | ARRAY[1..3] OF ST_ServoAxis | 轴: 1 = Z, 2 = X1, 3 = X2 |

## 附：约定

所有 FB 参数仅用 `VAR_IN_OUT`（结构体）和必要的 `VAR_INPUT` 标量，不使用 `VAR_OUTPUT`；结构体字段定义见 `程序文档/PLC变量定义文档_VAR.md`，接口总表见 `00_程序方案/接口文档_INT.md` 第 5 节。
