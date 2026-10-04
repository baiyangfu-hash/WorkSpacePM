# PLC变量定义文档

> 本文件的变量表由 `plc docs sync` 按代码补全；标注“【待确认】”的行需人工审核后运行 `plc docs confirm`。

## 变量表

### GlobalVars（数据块）

| 名称 | 类型 | 说明 |
|---|---|---|
| stGlobal | ST_CommonAlarm | 全局控制与报警数据 (FB_2001_CommonAlarm) |
| stExternal | ST_ExternalDevice | 外部设备交互信号 (ST_ExternalDevice) |
| stConveyor.astLayer | ARRAY[1..4] OF ST_SingleLayerConveyor | 各层输送机数据 (4 层) |
| stConveyor.i_bAutoMode | BOOL | 自动运行模式 |
| stConveyor.i_bManualMode | BOOL | 手动调试模式 |
| stConveyor.i_bStart | BOOL | 自动循环启动 |
| stConveyor.i_bStop | BOOL | 停止 |
| stConveyor.i_dSeparateTimeoutMs | DINT | 分料超时时间(ms) |
| stConveyor.i_dDebounceMs | DINT | 传感器消抖(ms) |
| stConveyor.i_bSafetyDoorOk | BOOL | 安全门OK |
| stConveyor.i_bVfdFault | BOOL | 变频器故障 |
| stConveyor.q_bRunning | BOOL | 4层 OR |
| stConveyor.q_bFault | BOOL | 4层 OR |
| stConveyor.q_iAlarmCode | INT | 4层报警码 MIN |
| stPickPlace | ST_PickPlace | 取放料机构信号 (ST_PickPlace) |
| stRecipeManager | ST_RecipeManager | 配方管理器 (10 组配方) |
| stFeeder | ST_GlueFeeder | 打胶机送料机构信号 (ST_GlueFeeder) |
| astServoAxis | ARRAY[1..3] OF ST_ServoAxis | 伺服轴数组: [1]=Z轴 [2]=X1轴 [3]=X2轴 |
| fbExternalDevice | FB_ExternalDeviceInteraction | 外部设备交互功能块实例 |
| fbConveyor_L1 | FB_1002_SingleLayerConveyor_BufferFraming | 第 1 层输送机功能块实例 |
| fbConveyor_L2 | FB_1002_SingleLayerConveyor_BufferFraming | 第 2 层输送机功能块实例 |
| fbConveyor_L3 | FB_1002_SingleLayerConveyor_BufferFraming | 第 3 层输送机功能块实例 |
| fbConveyor_L4 | FB_1002_SingleLayerConveyor_BufferFraming | 第 4 层输送机功能块实例 |
| fbPickPlace | FB_1003_PickPlace_BufferFraming | 取放料机构功能块实例 |
| fbGlueFeeder | FB_1004_GlueMachineFeeder_BufferFraming | 打胶机送料功能块实例 |
| fbCommonAlarm | FB_2001_CommonAlarm_AllStation | 公共报警管理功能块实例 |

### ST_UpstreamDocking（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| bMachine_ReadyIn | BOOL | (1) 机器准备好进料信号 |
| bMachine_RcvModuleIdAck | BOOL | (4) 机器收到组件ID信号 |
| bMachine_AllowInfeed | BOOL | (5) 机器允许上游进料信号 |
| bMachine_InfeedArrived | BOOL | (7) 机器给上游组件进料到位信号 |
| bMachine_HeartbeatToUp | BOOL | [心跳] 本机向上游心跳 (4s ON / 4s OFF) |
| bUpstream_LineReady | BOOL | (2) 上游流水线/机器人准备好信号 |
| bUpstream_SendModuleId | BOOL | (3) 上游流水线传组件ID信号 |
| bUpstream_InfeedReq | BOOL | (6) 上游流水线入料请求信号 |
| bUpstream_InfeedArrivedAck | BOOL | (8) 上游回收收到进料到位信号 |
| bUpstream_HeartbeatFromUp | BOOL | [心跳] 上游输入心跳 |
| sRcvModuleID | STRING[32] | 接收的组件 ID |
| bUpstreamComFault | BOOL | 上游通讯中断报警 (12s 超时) |
| iInfeedStep | INT | 当前步序 0~8 |
| bRobot_Fault | BOOL | 机器人故障 |
| bRobot_EStop | BOOL | 机器人急停 |

### ST_DownstreamDocking（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| bMachine_ReadyOut | BOOL | (2) 机器准备好出料信号 |
| bMachine_SendModuleId | BOOL | (3) 机器传组件ID信号 |
| bMachine_OutfeedReq | BOOL | (6) 机器给下游出料请求信号 (允许打胶机抓料 Y44) |
| bMachine_OutfeedArrivedAck | BOOL | (8) 机器回收收到进料到位信号 |
| bMachine_HeartbeatToDown | BOOL | [心跳] 本机向下游心跳 (4s ON / 4s OFF) |
| bSafetyZoneSignal | BOOL | 安全区隔离/开放信号 (Y47) |
| bDownstream_LineReady | BOOL | (1) 下游流水线准备好 (允许送料 X76) |
| bDownstream_RcvModuleIdAck | BOOL | (4) 下游流水线收到组件ID信号 |
| bDownstream_AllowOutfeed | BOOL | (5) 下游流水线允许机器出料信号 |
| bDownstream_OutfeedArrived | BOOL | (7) 下游取料完成信号 (X102) |
| bDownstream_HeartbeatFromDown | BOOL | [心跳] 下游输入心跳 |
| bDownstream_Fault | BOOL | 打胶机故障 |
| bDownstream_EStop | BOOL | 打胶机急停 |
| sSendModuleID | STRING[32] | 发送给下游的组件 ID |
| bDownstreamComFault | BOOL | 下游通讯中断报警 (12s 超时) |
| iOutfeedStep | INT | 当前步序 0~8 |

### ST_ExternalDevice（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| i_bEnable | BOOL | 系统总使能 |
| i_bAutoMode | BOOL | 自动模式选择 |
| i_bManualMode | BOOL | 手动模式选择 |
| i_bStart | BOOL | 启动按钮 |
| i_bStop | BOOL | 停止按钮 |
| i_bReset | BOOL | 复位按钮 |
| i_bLocalReady | BOOL | 本机就绪状态 |
| i_bAnyAlarmActive | BOOL | 本机有任何报警激活 |
| i_bSystemFault | BOOL | 本机系统故障 |
| stUpstream | ST_UpstreamDocking | 上游机器人供料对接 |
| stDownstream | ST_DownstreamDocking | 下游打胶机送料对接 |
| i_bFrameMachine_AutoRunning | BOOL | 组框机自动运行中 |
| i_bFrameMachine_AllowFeed | BOOL | 组框机允许向缓存机输送边框 |
| i_bFrameMaterialRequest | BOOL | 组框机有边框需要送入缓存机 |
| i_bDoorOpenRequest | BOOL | 组框机操作门打开(需本机暂停) |
| i_bFrameMachine_EStop | BOOL | 组框机急停信号(需联锁) |
| i_bFrameMachine_SafetyErr | BOOL | 组框机安全系统异常 |
| i_bFrameMachine_CommErr | BOOL | 与组框机通讯异常 |
| o_bFrameMachine_RequestFeed | BOOL | 向组框机请求输送边框 |
| o_bFrameMachine_Pause | BOOL | 向组框机发送暂停指令 |
| o_bFrameMachine_EStop | BOOL | 向组框机发送急停联锁信号 |
| o_bDoorOpenRequest | BOOL | 向组框机申请开门操作 |
| o_bFrameMachine_Ready | BOOL | 本机就绪, 可接收边框 |
| o_bFrameMachine_EmergencyStop | BOOL | 组框机急停/安全异常时强制本机停止 |
| o_bExternalDeviceFault | BOOL | 外部设备故障标志 |
| o_iExternalDeviceAlarmSummary | INT | 外部设备故障报警码(300~399段) |
| o_bSystemSafetyConditionMet | BOOL | 系统安全条件是否满足 |

### ST_SingleLayerConveyor（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| bAutoMode | BOOL | 自动运行模式 |
| bManualMode | BOOL | 手动调试模式 |
| bStart | BOOL | 自动循环启动 |
| bStop | BOOL | 停机 (电平有效, 步序清零复位) |
| bPause | BOOL | 异常暂停 (仅切断电机, 保持步序与气缸) |
| bInitStart | BOOL | 初始化/退料启动脉冲 |
| iLayerIndex | INT | 层索引 1~4 |
| dInitRevDurationMs | DINT | 初始化反转排空时长 (源程序 10.0s) |
| dPreBlockDelayMs | DINT | 阻挡前到位延时时长 (源程序 3.0s) |
| dSlowFeedDelayMs | DINT | 慢速定位到位延时时长 (源程序 2.0s) |
| dFullMaterialDelayMs | DINT | 满料防侧翻自动减速延时 (源程序 5.0s) |
| dPickupReleaseDelayMs | DINT | 取料完成脱离延时 (有交互 1.0s, 无交互 8.0s) |
| dSeparateTimeoutMs | DINT | 气缸动作超时报警阈值 (默认 5000ms) |
| dDebounceMs | DINT | 传感器消抖滤波时间(ms) |
| bPreSeparateSensor | BOOL | 阻挡前到位接近开关 (X31/X41/X51/X61) |
| bPositionSensor1 | BOOL | 边框取料位接近开关 1 (X32/X42/X52/X62) |
| bPositionSensor2 | BOOL | 边框取料位接近开关 2 (X33/X43/X53/X63 冗余) |
| bFullMaterial1 | BOOL | 边框满料检测 1 (X150/X152/X154/X156) |
| bFullMaterial2 | BOOL | 边框满料检测 2 (X151/X153/X155/X157) |
| bBlockCylinderUp1 | BOOL | 阻挡气缸 1 上位 (缩回无干涉) |
| bBlockCylinderUp2 | BOOL | 阻挡气缸 2 上位 (缩回无干涉) |
| bBlockCylinderDown1 | BOOL | 阻挡气缸 1 下位 (阻挡通道) |
| bBlockCylinderDown2 | BOOL | 阻挡气缸 2 下位 (阻挡通道) |
| bSeparateCylinderUp1 | BOOL | 分料气缸 1 上位 (缩回无干涉) |
| bSeparateCylinderUp2 | BOOL | 分料气缸 2 上位 (缩回无干涉) |
| bSeparateCylinderDown1 | BOOL | 分料气缸 1 下位 (推出分料) |
| bSeparateCylinderDown2 | BOOL | 分料气缸 2 下位 (推出分料) |
| bBlockCylinderUp | BOOL | 阻挡气缸上位 (旧引脚别名，兼容保留) |
| bBlockCylinderDown | BOOL | 阻挡气缸下位 (旧引脚别名，兼容保留) |
| bSeparateCylinderUp | BOOL | 分料气缸上位 (旧引脚别名，兼容保留) |
| bSeparateCylinderDown | BOOL | 分料气缸下位 (旧引脚别名，兼容保留) |
| bRobotInSafetyPos | BOOL | 取料机构在安全区区域 (干涉区互锁) |
| bSafetyDoorOk | BOOL | 安全门状态 TRUE=关闭OK |
| bVfdFault | BOOL | 变频器故障 |
| bPickupConfirmed | BOOL | 取料机构已取走物料握手信号 (取料完成) |
| bManBlockExtend | BOOL | 手动:阻挡下降 |
| bManBlockRetract | BOOL | 手动:阻挡上升 |
| bManSeparatePush | BOOL | 手动:分料推出 |
| bManConveyorFwd | BOOL | 手动:输送正转 |
| bManConveyorRev | BOOL | 手动:输送反转 |
| bManConveyorSlow | BOOL | 手动:输送慢速 |
| q_bBlockSolenoid | BOOL | 阻挡单阀输出 TRUE=双气缸同时下降放行 |
| q_bSeparateSolenoid | BOOL | 分料单阀输出 TRUE=双气缸同时推出分料 |
| q_bConveyorFwd | BOOL | 输送带快速正转 (受暂停联锁) |
| q_bConveyorRev | BOOL | 输送带反转退料 (受暂停联锁) |
| q_bConveyorSlow | BOOL | 输送带慢速 (定位慢速 OR 满料防侧翻慢速) |
| q_bInitDone | BOOL | 初始化就绪完成 (准备完成) |
| q_bRequestPickup | BOOL | 请求取料 (等待 XZ 机械手) |
| q_bLayerFeedDone | BOOL | 兼容别名 (同 q_bRequestPickup) |
| q_iCurrentState | INT | 当前步序 (Step_S) |
| q_iAlarmCode | INT | 本层报警码 |
| q_bRunning | BOOL | 自动运行中 |
| q_bFault | BOOL | 本层有故障 |
| q_bAnySensorFault | BOOL | 气缸传感器故障 |

### ST_PickPlace（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| i_bEnable | BOOL | 总使能 |
| i_bAutoMode | BOOL | 自动模式 |
| i_bManualMode | BOOL | 手动模式 |
| i_bStart | BOOL | 启动按钮 |
| i_bStop | BOOL | 停止按钮 |
| i_bReset | BOOL | 复位按钮 |
| i_bLx_ZAxis_JogUp | BOOL | 手动: Z轴点动上升 |
| i_bLx_ZAxis_JogDown | BOOL | 手动: Z轴点动下降 |
| i_bLx_X1Axis_JogFwd | BOOL | 手动: X1轴点动前进 |
| i_bLx_X1Axis_JogRev | BOOL | 手动: X1轴点动后退 |
| i_bLx_FrontClamp | BOOL | 手动: 前夹紧 |
| i_bLx_RearClamp | BOOL | 手动: 后夹紧 |
| i_bLx_FrontClamp2 | BOOL | 手动: 前夹紧2 |
| i_bLx_RearClamp2 | BOOL | 手动: 后夹紧2 |
| i_bLx_LiftUp | BOOL | 手动: 升降上升 |
| i_bLx_LiftDown | BOOL | 手动: 升降下降 |
| i_bLx_Lift_Up | BOOL | 手动: 升降上升 (别名) |
| i_bLx_Lift_Down | BOOL | 手动: 升降下降 (别名) |
| i_iPickLayer | INT | 强制指定的取料层号 (0=自动根据小车槽位调度) |
| i_iPickLayer_Input | INT | 取料层号别名 |
| i_rZSpeed | REAL | Z轴速度(mm/s) |
| i_rX1Speed | REAL | X1轴速度(mm/s) |
| i_rZAxisSpeed | REAL | Z轴速度别名 |
| i_rX1AxisSpeed | REAL | X1轴速度别名 |
| i_iClampConfirmTime | INT | 夹紧确认时间(ms) |
| i_iLiftActionTime | INT | 升降动作超时(ms) |
| i_bLayerRequestPickup | ARRAY[1..4] OF BOOL | 1~4层请求取料 (来自 FB_1002) |
| i_bLayerFeedDone | ARRAY[1..4] OF BOOL | 兼容旧别名 |
| o_bLayerPickupDone | ARRAY[1..4] OF BOOL | 发送给 1~4 层的取料完成信号 |
| i_bCartAtPickPos | BOOL | 小车在接料位 (X2轴到位 D512) |
| i_bCartPermitPlace | BOOL | 小车允许放料 (处于接料安全状态) |
| i_bCartSlotLong1_HasMat | BOOL | 小车槽位1(长边1) 有料光电检测 |
| i_bCartSlotLong2_HasMat | BOOL | 小车槽位2(长边2) 有料光电检测 |
| i_bCartSlotShort1_HasMat | BOOL | 小车槽位3(短边1) 有料光电检测 |
| i_bCartSlotShort2_HasMat | BOOL | 小车槽位4(短边2) 有料光电检测 |
| i_bLongEdge1Detect | BOOL | 长边1工件检测光电 |
| i_bLongEdge2Detect | BOOL | 长边2工件检测光电 |
| i_bShortEdge1Detect | BOOL | 短边1工件检测光电 |
| i_bShortEdge2Detect | BOOL | 短边2工件检测光电 |
| i_bFrontClamp_Closed | BOOL | 前夹爪1夹紧到位 |
| i_bFrontClamp_Opened | BOOL | 前夹爪1松开到位 |
| i_bRearClamp_Closed | BOOL | 后夹爪1夹紧到位 |
| i_bRearClamp_Opened | BOOL | 后夹爪1松开到位 |
| i_bFrontClamp2_Closed | BOOL | 前夹爪2夹紧到位 |
| i_bFrontClamp2_Opened | BOOL | 前夹爪2松开到位 |
| i_bRearClamp2_Closed | BOOL | 后夹爪2夹紧到位 |
| i_bRearClamp2_Opened | BOOL | 后夹爪2松开到位 |
| i_bLift_HomePos | BOOL | 升降气缸原位 |
| i_bLift_WorkPoint | BOOL | 升降气缸动位 |
| i_bFrameDetect1 | BOOL | 边框到位检测1 |
| i_bFrameDetect2 | BOOL | 边框到位检测2 |
| i_bFullMaterialDetect1 | BOOL | 满料检测1 |
| i_bFullMaterialDetect2 | BOOL | 满料检测2 |
| o_bFrontClamp_Action | BOOL | 前夹爪夹紧动作 |
| o_bFrontClamp_Release | BOOL | 前夹爪松开动作 |
| o_bRearClamp_Action | BOOL | 后夹爪夹紧动作 |
| o_bRearClamp_Release | BOOL | 后夹爪松开动作 |
| o_bFrontClamp2_Action | BOOL | 前夹爪2夹紧动作 |
| o_bFrontClamp2_Release | BOOL | 前夹爪2松开动作 |
| o_bRearClamp2_Action | BOOL | 后夹爪2夹紧动作 |
| o_bRearClamp2_Release | BOOL | 后夹爪2松开动作 |
| o_bLift_Up | BOOL | 升降上升 |
| o_bLift_Down | BOOL | 升降下降 |
| o_bLiftUp | BOOL | 别名 |
| o_bLiftDown | BOOL | 别名 |
| o_bPickPlaceInSafetyZone | BOOL | 取放料机构在安全区 (互锁给输送机/打胶小车) |
| o_bPlaceComplete_ToFeeder | BOOL | 单次放料完成脉冲 |
| o_bAllSlotsFull_ToCart | BOOL | 小车 4 根边框全部集齐 (M30, 允许发车) |
| o_bRunning | BOOL | 自动运行中 |
| o_bFault | BOOL | 机构故障 |
| o_bX1Fault | BOOL | X1轴故障 |
| o_bZFault | BOOL | Z轴故障 |
| o_iCurrentState | INT | 当前状态机步序 |
| o_iCurrentPickLayer | INT | 当前正在处理的层号 (1..4) |
| o_iStationAlarmCode | INT | 报警码 |

### ST_PickPlaceRecipe（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| sRecipeName | STRING[32] | 配方名称 (例: "182-72版型_双玻边框") |
| rZ_StandbyPos | REAL | Z轴安全待机高度 (D500) |
| rX1_PickPos | REAL | X1轴取料基准位 (D510) |
| rZ_PickHeightL1 | REAL | 1层取料高度 (长边1, D514) |
| rZ_PickHeightL2 | REAL | 2层取料高度 (长边2, D544) |
| rZ_PickHeightL3 | REAL | 3层取料高度 (短边1) |
| rZ_PickHeightL4 | REAL | 4层取料高度 (短边2) |
| rX1_PlaceLong1_Pos | REAL | 小车长边1槽 X1坐标 (D520 前放点) |
| rZ_PlaceLong1_Height | REAL | 小车长边1槽 Z放料高度 (D524) |
| rX1_PlaceLong2_Pos | REAL | 小车长边2槽 X1坐标 (D550 后放点) |
| rZ_PlaceLong2_Height | REAL | 小车长边2槽 Z放料高度 (D554) |
| rX1_PlaceShort1_Pos | REAL | 小车短边1槽 X1坐标 (D532) |
| rZ_PlaceShort1_Height | REAL | 小车短边1槽 Z放料高度 (D530) |
| rX1_PlaceShort2_Pos | REAL | 小车短边2槽 X1坐标 (D560) |
| rZ_PlaceShort2_Height | REAL | 小车短边2槽 Z放料高度 (D562) |
| rZ_Speed | REAL | Z轴运行速度 (mm/s) |
| rX1_Speed | REAL | X1轴运行速度 (mm/s) |
| iClampConfirmTimeMs | INT | 夹爪夹紧消抖确认时间 (ms) |
| iLiftActionTimeMs | INT | 升降动作超时看门狗 (ms) |

### ST_RecipeManager（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| iActiveRecipeId | INT | 当前激活配方号 (1..10) |
| bRecipeLoadReq | BOOL | 触发加载配方 |
| bRecipeSaveReq | BOOL | 触发保存配方 |
| stActiveRecipe | ST_PickPlaceRecipe | 当前正在运行的生效配方 |
| astRecipes | ARRAY[1..10] OF ST_PickPlaceRecipe | 10 组配方存储池 |

### ST_GlueFeeder（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| i_bEnable | BOOL | 总使能 |
| i_bAutoMode | BOOL | 自动模式 |
| i_bManualMode | BOOL | 手动模式 |
| i_bStart | BOOL | 启动按钮 |
| i_bStop | BOOL | 停止按钮 |
| i_bReset | BOOL | 复位按钮 |
| i_bLx_X2Axis_JogFwd | BOOL | 手动: X2正向点动 (前往打胶机) |
| i_bLx_X2Axis_JogRev | BOOL | 手动: X2反向点动 (返回接料位) |
| i_rFeedSpeed | REAL | X2轴送料速度(mm/s, D600) |
| rStandbyPosition | REAL | X2待机位置 (D610) |
| rPickupPosition | REAL | X2接料取片位置 (D512) |
| rFeedPosition | REAL | X2打胶机放料位置 (D522) |
| i_dDebounceMs | DINT | 传感器消抖时间(ms) |
| i_bCartSlotLong1_HasMat | BOOL | 小车槽位1(长边1) 有料检测 (X72) |
| i_bCartSlotLong2_HasMat | BOOL | 小车槽位2(长边2) 有料检测 (X73) |
| i_bCartSlotShort1_HasMat | BOOL | 小车槽位3(短边1) 有料检测 (X74) |
| i_bCartSlotShort2_HasMat | BOOL | 小车槽位4(短边2) 有料检测 (X75) |
| i_bAllSlotsFull_FromPickPlace | BOOL | 4根边框全部集齐全满 (M30) |
| i_bPickPlace_FeedComplete | BOOL | 单次放料完成脉冲 |
| i_bPickPlaceInSafetyZone | BOOL | 取放料机构在安全区 (Z轴在待机位) |
| i_bGlueMachine_AllowFeed | BOOL | 打胶机允许送料 (X76: 常态需保持有效) |
| i_bGlueMachine_SafetyOk | BOOL | 打胶机安全区/就绪状态 |
| i_bGlueMachine_EStop | BOOL | 打胶机急停状态 (TRUE=急停) |
| i_bGlueMachine_Fault | BOOL | 打胶机故障状态 (TRUE=故障) |
| i_bGlueMachine_ComFault | BOOL | 打胶机通讯中断 (12s 心跳超时) |
| i_bGlueMachine_PickupComplete | BOOL | 打胶机取料完成信号 (X102) |
| o_bCartAtPickPos | BOOL | 小车在接料位 (到达 D512) |
| o_bCartPermitPlace | BOOL | 小车允许放料 (处于接料安全状态) |
| o_bSafetyZoneSignal | BOOL | 给打胶机安全区信号 (Y47) |
| o_bAllowPickup | BOOL | 抓料可 / 放料请求信号 (Y44) |
| o_bFeederInSafetyZone | BOOL | 小车处于安全待机区 (未进入打胶机干涉区) |
| o_bRunning | BOOL | 自动运行中 |
| o_bFault | BOOL | 本站故障 |
| o_bX2Fault | BOOL | X2轴故障 |
| o_bInterlockStopActive | BOOL | 跨机联锁突发中断紧急制动生效 |
| o_iCurrentState | INT | 当前步序 (D760: 0~3) |
| o_rX2Axis_CurrentPosition | REAL | X2轴当前位置 |
| o_iStationAlarmCode | INT | 报警码 |

### ST_CommonAlarm（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| i_bReset | BOOL | 系统复位 |
| i_iConveyorAlarm | INT | 输送机报警码 |
| i_iPickPlaceAlarm | INT | 取放料机构报警码 |
| i_iFeederAlarm | INT | 打胶送料机构报警码 |
| o_wGlobalAlarmWord | WORD | 全局报警字 |
| o_iCurrentAlarmCode | INT | 当前最高优先级报警码 |
| o_bAnyAlarmActive | BOOL | 任意报警激活 |
| o_iMESAlarmCount | INT | MES报警计数 |
| o_iMESAlarmQueue | INT | MES报警队列 |
| o_bNewAlarmFlag | BOOL | 新报警标志 |
| o_iStationAlarmStatus | INT | 工站报警汇总状态 |
| o_bConveyorAlarmActive | BOOL | 输送机报警激活 |
| o_bPickPlaceAlarmActive | BOOL | 取放料报警激活 |
| o_bFeederAlarmActive | BOOL | 打胶送料报警激活 |
