# 接口文档 FB_ExternalDeviceInteraction

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | FB_ExternalDeviceInteraction 接口定义 |
| **文档版本** | V15.0.0 |
| **关联源码** | 01_外部设备交互/FB_ExternalDeviceInteraction.scl |
| **编制日期** | 2026-10-24 |
| **编制人** | Claude（用户待审） |
| **遵循规范** | LSP-905_SCL编程规范 |
| **依据** | 全局 `00_程序方案/接口文档_INT.md` 与 `详细设计说明书_DSN.md` |

## 1. 功能概述与接口

组框机链路（FB_3001）：联机 M501 / 连续送框 M502 / 单套送框许可 M510，本机安全异常输出 R5000.0 与 Y45 / Y46，组框机安全异常 F104（A 类）、通讯异常 F105（提示类）。

## 接口参数 (VAR_IN_OUT)

| 名称 | 类型 | 说明 |
|---|---|---|
| io_stExt | ST_ExternalLink | 组框机链路 (本 FB 写) |
| io_stMachine | ST_Machine | 模式 (保留, 本 FB 暂不读) |
| io_stHmi | ST_Hmi | 联机 M501 / 连续 M502 (读), 单套回读 M510 (写) |
| io_stIo | ST_Io | Y45 / Y46 输出 |
| io_stFeed | ST_Feeder | 小车 Y44 (读, 消耗单套许可) |
| io_stAlarm | ST_Alarm | 报警 (读 F0~F8 锁存, 写 F104 / F105 触发) |

## 附：约定

所有 FB 参数仅用 `VAR_IN_OUT`（结构体）和必要的 `VAR_INPUT` 标量，不使用 `VAR_OUTPUT`；结构体字段定义见 `程序文档/PLC变量定义文档_VAR.md`，接口总表见 `00_程序方案/接口文档_INT.md` 第 5 节。
