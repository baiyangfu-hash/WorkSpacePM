# 接口文档 FB_2001_CommonAlarm_AllStation

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | FB_2001_CommonAlarm_AllStation 接口定义 |
| **文档版本** | V15.0.0 |
| **关联源码** | 05_公共报警/FB_2001_CommonAlarm_AllStation.scl |
| **编制日期** | 2026-10-24 |
| **编制人** | Claude（用户待审） |
| **遵循规范** | LSP-905_SCL编程规范 |
| **依据** | 全局 `00_程序方案/接口文档_INT.md` 与 `详细设计说明书_DSN.md` |

## 1. 功能概述与接口

F0~F127 报警自保持、分级（A 类进 M8，B 类按机构 Hold，提示类只显示）、最小报警号、复位键边沿清除和声光输出（杆灯绿 / 黄 / 红、蜂鸣、复位灯）。

## 接口参数 (VAR_IN_OUT)

| 名称 | 类型 | 说明 |
|---|---|---|
| io_stAlarm | ST_Alarm | 报警触发 / 锁存 / 分级输出 / 声光 |
| io_stMachine | ST_Machine | 模式 (声光条件) |
| io_stIo | ST_Io | 复位键 X100 输入, 声光输出 Y24~Y27 / Y50 |
| io_stHmi | ST_Hmi | 静音 M9, 强置选项 M515 |

## 附：约定

所有 FB 参数仅用 `VAR_IN_OUT`（结构体）和必要的 `VAR_INPUT` 标量，不使用 `VAR_OUTPUT`；结构体字段定义见 `程序文档/PLC变量定义文档_VAR.md`，接口总表见 `00_程序方案/接口文档_INT.md` 第 5 节。
