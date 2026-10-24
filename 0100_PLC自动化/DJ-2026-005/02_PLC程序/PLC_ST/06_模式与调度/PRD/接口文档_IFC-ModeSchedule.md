# 接口文档 06_模式与调度（FB_1001 / FB_1005 / FB_1006 / FB_2002）

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | 06 模式与调度接口定义 |
| **文档版本** | V15.0.0 |
| **关联源码** | 06_模式与调度/FB_1001_MachineMode_BufferFraming.scl |
| **同文档涵盖** | 06_模式与调度/FB_1005_HomePrepare_BufferFraming.scl；06_模式与调度/FB_1006_ManualTeach_BufferFraming.scl；06_模式与调度/FB_2002_StationBridge.scl |
| **编制日期** | 2026-10-24 |
| **编制人** | Claude（用户待审） |
| **遵循规范** | LSP-905_SCL编程规范 |
| **依据** | 全局 `00_程序方案/接口文档_INT.md` 与 `详细设计说明书_DSN.md` |

## 1. 功能概述与接口

## 机器模式（FB_1001_MachineMode_BufferFraming）

机器模式（手动 / 回原点 / 准备 / 自动）、暂停、停止收尾、设备状态字 D116，机器级报警触发 F0~F25（急停、8 扇门、伺服、变频器、HMI 停止、三轴极限）。

### FB_1001_MachineMode_BufferFraming：VAR_IN_OUT

| 名称 | 类型 | 说明 |
|---|---|---|
| io_stMachine | ST_Machine | 模式与状态字 (本 FB 写) |
| io_stHmi | ST_Hmi | HMI 命令 (读); 回写报警号 / 设备状态 |
| io_stIo | ST_Io | 物理输入 (读) |
| io_stAlarm | ST_Alarm | 报警 (读锁存, 写机器级触发) |
| io_stHome | ST_HomePrepare | 回原点 / 准备状态 (读) |

## 回原点与准备（FB_1005_HomePrepare_BufferFraming）

回原点序列（预处理 → Z → X1/X2）与准备序列（夹爪 / 升降缸 → Z 待机点 → X1 取料点 → X2 取料点 → 等输送），F80 / F81，三个轴的使能与错误复位。

### FB_1005_HomePrepare_BufferFraming：VAR_IN_OUT

| 名称 | 类型 | 说明 |
|---|---|---|
| io_stHome | ST_HomePrepare | 回原点 / 准备状态 (本 FB 写) |
| io_stMachine | ST_Machine | 模式 (读) |
| io_stIo | ST_Io | 物理输入 (读) |
| io_stAlarm | ST_Alarm | 报警 (写 F80 / F81 触发, 读复位) |
| io_arrAxis | ARRAY[1..3] OF ST_ServoAxis | 轴: 1 = Z, 2 = X1, 3 = X2 |
| io_stBridge | ST_Bridge | 站间中继 (读 Hold) |
| io_stPP | ST_PickPlace | 取放料 (读点位 / 速度) |
| io_stFeed | ST_Feeder | 小车 (读点位) |
| io_stConv | ST_ConveyorSystem | 输送 (读 4 层准备完成) |

## 手动与示教（FB_1006_ManualTeach_BufferFraming）

手动：速度加减、三轴点动、X1 / X2 手动定位、示教写点位、夹爪松开与升降缸手动、输送强制位放行。

### FB_1006_ManualTeach_BufferFraming：VAR_IN_OUT

| 名称 | 类型 | 说明 |
|---|---|---|
| io_stManual | ST_Manual | 手动 / 示教状态 (本 FB 写) |
| io_stMachine | ST_Machine | 模式 (读) |
| io_stHmi | ST_Hmi | HMI 命令 (读); 速度设定 (写回) |
| io_stIo | ST_Io | 物理输入 (读) |
| io_stPP | ST_PickPlace | 取放料 (示教写点位, 读待机点) |
| io_stFeed | ST_Feeder | 小车 (示教写点位) |
| io_stExt | ST_ExternalLink | 组框机链路 (读安全异常) |
| io_stBridge | ST_Bridge | 站间中继 (读安全区) |
| io_arrAxis | ARRAY[1..3] OF ST_ServoAxis | 轴: 1 = Z, 2 = X1, 3 = X2 |

## 站间中继（FB_2002_StationBridge）

站间信号中继：只做赋值（安全区、层请求、层取料完成、A / B 请求、X1 送料完成、Hold、回原点要求），外加三处最简组合（Hold = 报警 Hold 或暂停；送框许可；收到清除脉冲后清送料完成位），并把取放料 / 小车的报警触发搬入 `stAlarm`。

### FB_2002_StationBridge：VAR_IN_OUT

| 名称 | 类型 | 说明 |
|---|---|---|
| io_stBridge | ST_Bridge | 站间中继 |
| io_stConv | ST_ConveyorSystem | 4 层输送 |
| io_stPP | ST_PickPlace | 取放料 |
| io_stFeed | ST_Feeder | X2 小车 |
| io_stHome | ST_HomePrepare | 回原点 / 准备 |
| io_stManual | ST_Manual | 手动 |
| io_stExt | ST_ExternalLink | 组框机链路 |
| io_stMachine | ST_Machine | 模式 |
| io_stAlarm | ST_Alarm | 报警 |

## 附：约定

所有 FB 参数仅用 `VAR_IN_OUT`（结构体）和必要的 `VAR_INPUT` 标量，不使用 `VAR_OUTPUT`；结构体字段定义见 `程序文档/PLC变量定义文档_VAR.md`，接口总表见 `00_程序方案/接口文档_INT.md` 第 5 节。
