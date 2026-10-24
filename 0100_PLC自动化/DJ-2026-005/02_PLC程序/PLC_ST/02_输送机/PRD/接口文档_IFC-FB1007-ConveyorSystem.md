# 接口文档 FB_1007_ConveyorSystem_BufferFraming

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | FB_1007_ConveyorSystem_BufferFraming 接口定义 |
| **文档版本** | V15.0.0 |
| **关联源码** | 02_输送机/FB_1007_ConveyorSystem_BufferFraming.scl |
| **编制日期** | 2026-10-24 |
| **编制人** | Claude（用户待审） |
| **遵循规范** | LSP-905_SCL编程规范 |
| **依据** | 全局 `00_程序方案/接口文档_INT.md` 与 `详细设计说明书_DSN.md` |

## 1. 功能概述与接口

4 层输送系统：持有 4 个 FB_1002 实例，把 ST_Io 的传感器和 Bridge / Machine 的命令搬到每层，把每层命令加上手动强制、上料点动后写到物理输出，汇总准备完成 / 请求 / 静止点，一键退料，气缸与缺料报警触发搬入 `stAlarm`。

## 接口参数 (VAR_IN_OUT)

| 名称 | 类型 | 说明 |
|---|---|---|
| io_stConv | ST_ConveyorSystem | 4 层输送 |
| io_stBridge | ST_Bridge | 站间中继 (读) |
| io_stMachine | ST_Machine | 模式 |
| io_stIo | ST_Io | 物理输入输出 |
| io_stAlarm | ST_Alarm | 报警 (写 arrTrig) |
| io_stHmi | ST_Hmi | 一键退料 M515 / 上料按钮 |
| io_stManual | ST_Manual | 手动强制位 |

## 附：约定

所有 FB 参数仅用 `VAR_IN_OUT`（结构体）和必要的 `VAR_INPUT` 标量，不使用 `VAR_OUTPUT`；结构体字段定义见 `程序文档/PLC变量定义文档_VAR.md`，接口总表见 `00_程序方案/接口文档_INT.md` 第 5 节。
