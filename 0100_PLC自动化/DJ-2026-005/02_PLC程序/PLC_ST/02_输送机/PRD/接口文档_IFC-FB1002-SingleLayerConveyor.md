# 接口文档 FB_1002_SingleLayerConveyor_BufferFraming

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | FB_1002 单层输送机接口定义 |
| **文档版本** | V15.0.0 |
| **关联源码** | 02_输送机/FB_1002_SingleLayerConveyor_BufferFraming.scl |
| **编制日期** | 2026-10-24 |
| **编制人** | Claude（用户待审） |
| **遵循规范** | LSP-905_SCL编程规范 |
| **依据** | 全局 `00_程序方案/接口文档_INT.md` 4.5 / 5 / 8，`详细设计说明书_DSN.md` 5.1 |

## 1. 功能概述

单层边框输送机 10 步状态机，4 层各调用一次（实例在 FB_1007 内）。输出全部写在 `io_stLayer` 里，不使用 `VAR_OUTPUT`。

## 2. 步序常量

| 常量名 | 值 | 说明 |
|---|---|---|
| STEP_IDLE | 0 | 分支 / 待机 |
| STEP_INIT_WAIT | 1 | 状态判断（阻挡下降、分料升起） |
| STEP_INIT_RUN | 2 | 初始化反转排空 |
| STEP_SEND_ON | 10 | 放行，位置到后快速正转 |
| STEP_ARRIVE | 20 | 运行到阻挡前，延时后停 |
| STEP_SEPARATE | 30 | 分料下降 |
| STEP_BLOCK_DOWN | 50 | 阻挡下降 |
| STEP_SLOW_FEED | 60 | 送到取料位 |
| STEP_REQUEST | 70 | 请求取料 |
| STEP_RELEASE | 80 | 等取走 |

## 3. 接口参数 (VAR_INPUT)

| 名称 | 类型 | 说明 |
|---|---|---|
| i_dInitRevMs | DINT | 初始化反转时长 ms (10000) |
| i_dPreBlockMs | DINT | 阻挡前到位延时 ms (3000) |
| i_dSlowFeedMs | DINT | 慢速到位延时 ms (2000) |
| i_dReleaseOkMs | DINT | 取走后延时, 有"取料完成" ms (1000) |
| i_dReleaseNgMs | DINT | 取走后延时, 无"取料完成" ms (8000) |
| i_dStarveMs | DINT | 缺料判定时间 ms (10000) |
| i_dCylTimeoutMs | DINT | 气缸位置报警时间 ms (5000) |

## 4. 接口参数 (VAR_IN_OUT)

| 名称 | 类型 | 说明 |
|---|---|---|
| io_stLayer | ST_SingleLayer | 本层全部数据 |

结构体 `ST_SingleLayer` 的字段（传感器、命令、状态、报警触发）见 `02_输送机/ST_SingleLayer.scl` 与全局 `接口文档_INT.md` 4.5；接口字段只在这两处维护。

## 5. 报警触发（`arrTrig`，由 FB_1007 映射到 F 号）

| 下标 | 含义 | F 号（1 层 / 2 / 3 / 4） |
|---|---|---|
| 1 / 2 | 阻挡上位 1 / 2 未到 | F34、F35 / F42、F43 / F50、F51 / F58、F59 |
| 3 / 4 | 阻挡下位 1 / 2 未到 | F36、F37 / F44、F45 / F52、F53 / F60、F61 |
| 5 / 6 | 分料上位 1 / 2 未到 | F38、F39 / F46、F47 / F54、F55 / F62、F63 |
| 7 / 8 | 分料下位 1 / 2 未到 | F40、F41 / F48、F49 / F56、F57 / F64、F65 |
| 9 | 缺料 | F103 / F102 / F101 / F100 |

## 6. 相对旧版的接口变化

旧版 `ST_SingleLayerConveyor`（含 FB_1011 / FB_1012 子块与 q_ 输出字段）整体废弃；新增 `bStopPending`（输入）与 `bAtRest`（输出）用于“停止后本循环结束”。
