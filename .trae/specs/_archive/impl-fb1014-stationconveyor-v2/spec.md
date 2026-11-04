# FB_1014_StationConveyor V2.0.0 实现规范

## Why

工站级输送机功能块FB_1014需要从V1.0.0重构为V2.0.0，核心驱动力：
- V1.0.0接口37个扁平参数导致调用复杂、安全/传感器/电机信号散装
- 与FB_1012/FB_1013的VAR_IN_OUT模式不一致
- 加工步骤耦合导致无法通用

## What Changes

- **新增VAR_IN_OUT结构体**：ST_StationSafety、ST_InfeedSensors、ST_ConveyorMotor
- **接口从37个精简至19个**：减少49%的接口数量
- **合并冗余输入**：InfeedSelected+OutfeedSelected→Selected，ClampVacDone+EdgeConfirmExt→ProcessDone
- **消除无引用输入**：LiftUpper、TouchEdgeWait、EStopActive、LightCurtainFault
- **新增SafeToRun计算输出**：安全条件统一判断

## Impact

- Affected specs: FB_1014接口契约
- Affected code: actuator/FB_1014_StationConveyor.scl

## Requirements

### Requirement: 功能块结构定义

功能块FB_1014_StationConveyor应包含以下接口区域：

#### VAR_INPUT (8个)
| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| i_bAutoMode | BOOL | FALSE | 自动模式使能 |
| i_bUpstreamReq | BOOL | FALSE | 上游入料请求 |
| i_bDownstreamReq | BOOL | FALSE | 下游出料请求 |
| i_bSelected | BOOL | FALSE | 工站选中 |
| i_bSlowOutMode | BOOL | FALSE | 同速同出慢模式 |
| i_bProcessDone | BOOL | FALSE | 外部加工完成 |
| i_dReplyDelayMs | DINT | 500 | 回复上游后延迟(ms) |
| i_dDischargeDelayMs | DINT | 1000 | 出料输送延时(ms) |

#### VAR_IN_OUT (3个)
| 名称 | 类型 | 说明 |
|------|------|------|
| io_stSafety | ST_StationSafety | 安全互锁组 |
| io_stSensors | ST_InfeedSensors | 入料位置检测组 |
| io_stMotor | ST_ConveyorMotor | 输送电机 |

#### VAR_OUTPUT (8个)
| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| q_yReplyUpstream | BOOL | FALSE | 回应上游入料可 |
| q_yReplyDownstream | BOOL | FALSE | 回应下游出料可 |
| q_yBarrierLift | BOOL | FALSE | 出料阻挡抬升 |
| q_yAlignClamp | BOOL | TRUE | 入料归正夹紧 |
| q_iState | INT | 0 | 当前状态(0~7) |
| q_dwProductionCount | DWORD | 0 | 累计产量计数 |
| q_bInfeedActive | BOOL | FALSE | 入料输送进行中 |
| q_bIntAlarmMem | BOOL | FALSE | 中断报警暂存 |

#### VAR (内部变量)
| 名称 | 类型 | 说明 |
|------|------|------|
| iState | INT | 主状态机当前状态 |
| tPosStart | FB_TON | 入料开始光电确认定时器 |
| tPos1 | FB_TON | 到位光电1确认定时器 |
| tPos2 | FB_TON | 到位光电2确认定时器 |
| tReplyDelay | FB_TON | 回复延迟定时器 |
| tDischargeDelay | FB_TON | 出料延时定时器 |
| m_bReplyUpOk | BOOL | 回应上游OK |
| m_bTransferDone | BOOL | 搬送完成 |
| m_bSimDnOk | BOOL | 模拟下游OK(调试用) |

### Requirement: 状态机定义

主状态机(Station_SM)包含8个状态：

| 状态值 | 名称 | 说明 |
|--------|------|------|
| 0 | IDLE | 空闲 |
| 1 | READY | 就绪 |
| 2 | INFEED | 入料输送 |
| 3 | PROCESSING | 加工中 |
| 4 | WAIT_DISCHARGE | 等待出料 |
| 5 | DISCHARGE | 出料输送 |
| 6 | COMPLETE | 完成 |
| 7 | FAULT | 故障 |

### Requirement: 安全优先级链

按以下优先级处理：

1. **最高优先级 - 急停**：NOT EStop OR NOT SfcStop → 立即停止马达，进入FAULT态
2. **第二优先级 - 光幕**：NOT LightCurtain1 OR NOT LightCurtain2 → 立即停止马达，进入FAULT态
3. **第三优先级 - 报警**：Fault OR CombinedAlarm → 停止马达，记录AlarmOut

SafeToRun计算公式：
```
SafeToRun = EStop AND SfcStop AND LightCurtain1 AND LightCurtain2 
            AND (NOT Fault) AND (NOT CombinedAlarm)
```

### Requirement: 位置检测逻辑

三段光电独立TON去抖：
- tPosStart: InfeedStart → StartConfirmed
- tPos1: InfeedPos1 → Pos1Confirmed
- tPos2: InfeedPos2 → Pos2Confirmed

AllConfirmed = StartConfirmed AND Pos1Confirmed AND Pos2Confirmed

### Requirement: 状态流转逻辑

#### IDLE → READY
- 条件：AutoMode=TRUE AND Selected AND SafeToRun

#### READY → INFEED
- 条件：UpstreamReq AND ReplyUpOk AND Selected AND ReplyDelay.Q AND SafeToRun

#### INFEED → PROCESSING
- 动作：马达正转，松归正夹
- 条件：AllConfirmed AND ProcessDone

#### PROCESSING → WAIT_DISCHARGE
- 条件：ProcessDone脉冲

#### WAIT_DISCHARGE → DISCHARGE
- 条件：AllConfirmed AND DownstreamReq AND SafeToRun

#### DISCHARGE → COMPLETE
- 动作：马达正转，抬阻挡，ReplyDownstream=TRUE
- 条件：DischargeDelay.Q

#### COMPLETE → IDLE
- 动作：清除所有输出，产量+1

#### ANY → FAULT
- 条件：NOT SafeToRun
- 动作：冻结输出，夹紧保持ON

### Requirement: 注释规范

遵循LSP-904规范：
- 变量行内注释使用 `//`
- 功能块头部和逻辑分支说明使用 `(* *)`
- 禁止嵌套注释
- 禁止中文标点
- 禁止注释内容含 `(*`或 `*)`标记字符串

## 验收标准

1. 功能块编译通过，无语法错误
2. 接口数量：VAR_INPUT=8，VAR_IN_OUT=3，VAR_OUTPUT=8
3. 状态机8态完整实现
4. 安全优先级链正确
5. 位置检测去抖逻辑正确
6. 符合LSP-904注释规范
