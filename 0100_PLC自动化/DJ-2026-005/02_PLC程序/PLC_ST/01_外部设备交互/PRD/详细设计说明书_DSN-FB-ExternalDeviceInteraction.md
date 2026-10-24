# 详细设计说明书 FB_ExternalDeviceInteraction

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | FB_ExternalDeviceInteraction详细设计说明书 |
| **文档版本** | V15.0.0 |
| **关联源码** | 01_外部设备交互/FB_ExternalDeviceInteraction.scl |
| **关联IFC** | 接口文档_IFC-FB3001-ExternalDeviceInteraction.md |
| **编制日期** | 2026-10-24 |
| **编制人** | Claude（用户待审） |
| **遵循规范** | LSP-905_SCL编程规范 |
| **依据** | 全局 `00_程序方案/接口文档_INT.md` 与 `详细设计说明书_DSN.md` |

## 1. 设计依据

工艺步序、转移条件、定时和报警表以全局 `00_程序方案/详细设计说明书_DSN.md` 为准，本文只记录**编码层面的实现选择**，以及与全局文档的差异（待评审确认）。

## 2. 实现结构：组框机链路（FB_ExternalDeviceInteraction）

1. `FB_R_TRIG / FB_F_TRIG` 取允许送料的上升 / 下降沿。
2. 本机安全异常 = F0~F8 任一锁存；Y45 与 Y46 目前同一条件（本机安全异常 或 组框机安全异常）。
3. F104 / F105 触发同时写 `stExt.arrTrig` 与 `stAlarm.arrTrig[104 / 105]`。

### 源码头部说明
