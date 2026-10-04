# 接口文档 FB_1003_PickPlace_BufferFraming

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | FB_1003 取放料机构接口定义 |
| **文档版本** | V8.0.0 |
| **关联源码** | 03_取放料/FB_1003_PickPlace_BufferFraming.scl |
| **编制日期** | 2026-05-20 |
| **编制人** | Trae |
| **遵循规范** | LSP-905, ST_ServoAxis V3.0(PLCopen MC Part 1) |
| **数据来源** | FB_1003 V7.0.0 源码 + GlobalVars.db V7.1.1 |

## 1. 功能概述

取放料机构控制块。Z轴升降 + X1轴横移 + 4组夹爪(前/后/前2/后2)控制。6步状态机(S20~S25)，一次取两根边框。产品检测在S22步内完成。

**V7.0.0重大变更**：删除6个间接轴请求输出(q_bZAxis*/q_bX1Axis*)，改用 `VAR_IN_OUT` 直连 `ST_ServoAxis V3.0` 嵌套结构体，FB内部直接操作 PLCopen MC 标准接口(stPower/stAbs/stStop/stSensor)。

## 2. 状态机步序常量

| 常量名 | 值 | 步骤名 | 说明 |
|--------|---|--------|------|
| S20_IDLE | 0 | 待机等待 | Z待机位，等取料请求。V7.0: 含轴使能检查+伺服报警检查 |
| S21_UP_TO_PICK | 1 | 上升到取料高度 | Z→D514取片教点。V7.0: 直接写io_stZAxis.stAbs (PLCopen MC_MoveAbsolute) |
| S22_CLAMP_AND_DETECT | 2 | 夹紧与检测 | 4夹紧+4光电+确认时间 |
| S23_MOVE_TO_PLACE | 3 | 移动到放料位置 | L1/L3→D520, L2/L4→D540。V7.0: 直接写io_stX1Axis.stAbs |
| S24_DOWN_TO_PLACE | 4 | 下降到放料高度 | Z→D524放片教点。V7.0: 直接写io_stZAxis.stAbs + q_bLiftDown |
| S25_UNCLAMP_AND_NOTIFY | 5 | 松开与通知 | 4松开+发信号给FB_1004 |

## 3. 接口参数 (VAR_IN_OUT)

| 名称 | 类型 | 说明 | OB1接线 |
|------|------|------|---------|
| io_stZAxis | ST_ServoAxis | Z轴升降伺服 (对象化标准接口) | => astServoAxis[1] |
| io_stX1Axis | ST_ServoAxis | X1轴横移伺服 (对象化标准接口) | => astServoAxis[2] |
| io_stPickPlace | ST_PickPlace | 取放料机构数据结构体 | — |
| io_stRecipe | ST_RecipeManager | 10组配方管理器与当前生效配方 | — |

结构体 `ST_PickPlace`、`ST_RecipeManager`、`ST_ServoAxis` 的字段不在本文档展开，统一在 `程序文档/PLC变量定义文档_VAR.md` 对应结构体的小节维护（接口字段只在一处维护，`plc docs check` 会核对）。

**ST_ServoAxis V3.0 子结构体访问路径**:

| 子结构体 | FB内用途 | 关键字段 |
|----------|---------|---------|
| `.stPower.Status` | 使能状态读取 | Status:BOOL |
| `.stPower.Enable` | 使能命令写入 | Enable:=TRUE |
| `.stAbs.Position` | 绝对定位目标位置 | Position:REAL |
| `.stAbs.Velocity` | 绝对定位速度 | Velocity:REAL |
| `.stAbs.Execute` | 绝对定位启动 | Execute:=TRUE/FALSE |
| `.stAbs.Done` | 定位完成反馈 | Done:BOOL(只读) |
| `.stAbs.Error` | 定位错误反馈 | Error:BOOL(只读) |
| `.stStop.Execute` | 急停命令 | Execute:=TRUE |
| `.stSensor.ServoAlarm` | 伺服驱动器报警 | ServoAlarm:BOOL(只读) |
| `.stSensor.FwdLimit` | 正限位开关 | FwdLimit:BOOL(只读) |
| `.stSensor.RevLimit` | 负限位开关 | RevLimit:BOOL(只读) |

## 4. 报警码 (FB_1003内部产生)

| 码 | 含义 | 触发条件 |
|:--:|------|----------|
| 71 | 升降超时 | tLiftTimer.Q (S21/S24) |
| 72 | 产品检测失败(S22) | 4光电未全ON |
| 73 | 伺服报警 | stSensor.ServoAlarm=TRUE (S20) |
| 74 | 轴限位触发 | FwdLimit OR RevLimit (S21/S23/S24) |
| 75 | 轴定位错误 | stAbs.Error=TRUE (S21/S24) |
| 80 | 取料平台有边框 | FrameDetect1 OR FrameDetect2 (S20) |
| 101 | 夹紧传感器不一致 | 夹紧位信号矛盾 (S22) |

## 5. 历史接口变更 (V6.0 → V7.0)

### 5.1 手动操作信号的删除项

> **V7.0删除项**（V6.0有但V7.0代码中已不存在）:
> - ~~i_bLx_ZAxis_JogUp~~ / ~~i_bLx_ZAxis_JogDown~~ （伺服点动 → 改由ST_ServoAxis.stJog处理）
> - ~~i_bLx_X1Axis_JogFwd~~ / ~~i_bLx_X1Axis_JogRev~~ （同上）

### 5.2 已删除的轴请求输出 (V6.0→V7.0移除)

以下6个输出在V6.0中存在，V7.0中**已删除**（功能迁移至VAR_IN_OUT直连）：

| V6.0名称 | V7.0替代方案 |
|----------|-------------|
| ~~q_bZAxisHomeRequest~~ | io_stZAxis.stHome.Execute (FB内直接调用) |
| ~~q_bZAxisMoveAbsReq~~ | io_stZAxis.stAbs.Execute (FB内直接调用) |
| ~~q_rZAxisTargetPos~~ | io_stZAxis.stAbs.Position (FB内直接写入) |
| ~~q_bX1AxisHomeRequest~~ | io_stX1Axis.stHome.Execute (FB内直接调用) |
| ~~q_bX1AxisMoveAbsReq~~ | io_stX1Axis.stAbs.Execute (FB内直接调用) |
| ~~q_rX1AxisTargetPos~~ | io_stX1Axis.stAbs.Position (FB内直接写入) |

## 6. 接口统计对比

| 项目 | V6.0.0 | V7.0.0 | 变化 |
|------|:-----:|:-----:|:----:|
| VAR_INPUT | 42 | 38 | -4 (删除伺服点动4个+复位1个，净-5; 实际代码41个) |
| VAR_OUTPUT | 22 | 16 | -6 (删除轴请求输出6个) |
| VAR_IN_OUT | 0 | 2 | +2 (新增io_stZAxis/io_stX1Axis) |
| **总计** | **64** | **56** | **-8 (接口简化)** |

## 7. 关联文档

| 文档 | 路径 | 版本 |
|------|------|:----:|
| DSN | 详细设计说明书_DSN-FB1003-PickPlace-V7.0.0.md | V7.0.0 |
| CHG | 变更记录_CHG-FB1003-PickPlace-V7.0.0.md | V7.0.0 |
| UM | 使用说明_UM-FB1003-PickPlace-V6.0.0.md | V6.0.0 |
| DB1 | GlobalVars.db (stPickPlace结构体) | V7.1.1 |
