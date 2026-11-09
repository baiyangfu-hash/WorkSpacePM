# Checklist: FB_1014_StationConveyor V2.0.0 验收清单

## 接口验证

- [x] VAR_INPUT接口数量=8 (i_bAutoMode, i_bUpstreamReq, i_bDownstreamReq, i_bSelected, i_bSlowOutMode, i_bProcessDone, i_dReplyDelayMs, i_dDischargeDelayMs)
- [x] VAR_IN_OUT接口数量=3 (io_stSafety, io_stSensors, io_stMotor)
- [x] VAR_OUTPUT接口数量=8 (q_yReplyUpstream, q_yReplyDownstream, q_yBarrierLift, q_yAlignClamp, q_iState, q_dwProductionCount, q_bInfeedActive, q_bIntAlarmMem)
- [x] 内部变量定义完整(9个)

## 状态机验证

- [x] 状态常量定义完整(8个)
- [x] IDLE状态：所有输出清零，归正夹紧保持ON
- [x] READY状态：等待请求信号
- [x] INFEED状态：马达正转，松夹紧，三光电确认
- [x] PROCESSING状态：马达停止，等待加工完成
- [x] WAIT_DISCHARGE状态：保持静止，等待下游请求
- [x] DISCHARGE状态：马达正转，抬阻挡，ReplyDownstream=TRUE
- [x] COMPLETE状态：清除输出，产量+1，产量计数正确
- [x] FAULT状态：冻结输出，SafeToRun恢复时返回IDLE

## 安全逻辑验证

- [x] SafeToRun计算正确：EStop AND SfcStop AND LightCurtain1 AND LightCurtain2 AND (NOT Fault) AND (NOT CombinedAlarm)
- [x] AlarmOut计算正确：Fault OR CombinedAlarm
- [x] 急停优先级：立即停止马达，进入FAULT态
- [x] 光幕优先级：立即停止马达，进入FAULT态
- [x] 报警优先级：停止马达，记录AlarmOut，不立即FAULT

## 位置检测验证

- [x] tPosStart定时器：InfeedStart → StartConfirmed
- [x] tPos1定时器：InfeedPos1 → Pos1Confirmed
- [x] tPos2定时器：InfeedPos2 → Pos2Confirmed
- [x] AllConfirmed计算：StartConfirmed AND Pos1Confirmed AND Pos2Confirmed
- [x] 去抖延时使用io_stSensors.DebounceMs

## 辅助逻辑验证

- [x] 回应上游逻辑正确
- [x] 下游中断报警逻辑正确
- [x] 回复延迟定时器正确
- [x] 出料延时定时器正确

## 代码质量验证

- [x] 注释符合LSP-904规范
- [x] 变量命名符合LSP-905规范
- [x] 无硬编码常量(使用参数)
- [x] 代码结构清晰易读

## 输出文件验证

- [x] 文件保存至正确路径：actuator/FB_1014_StationConveyor.scl
- [x] 文件版本标注：V2.0.0
- [x] 关联文档引用完整
