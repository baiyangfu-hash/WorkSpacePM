# 接口文档 - GlobalVars.db (全局变量数据块 V7.1.0)

## 文档信息
| 项目 | 内容 |
|------|------|
| **数据块名称** | GlobalVars |
| **功能描述** | 边框缓存机PLC控制系统全局变量数据交换中心 |
| **当前版本** | V7.1.1 |
| **编译日期** | 2026-05-20 |
| **总变量数** | ~220+个 (5个STRUCT结构 + astServoAxis[3] + 7个FB实例) |
| **符合规范** | LSP-905_SCL编程规范 |

### V7.1.1 变更 (2026-05-20) - TC11 Bug修复
- 🆕 stPickPlace新增 `i_iPickLayer_Input`: INT (外部指定取料层号1~4, 独立输入)
- 🔧 OB1接线修复: `i_iPickLayer` 从 `o_iCurrentPickLayer`(输出) 改为 `i_iPickLayer_Input`(独立输入)
- 📝 断开输出→输入反馈回路, 解决FB_1003内部iPickLayer(=0)覆盖问题

### V7.1.0 变更 (2026-05-20)
- 🆕 新增 `astServoAxis[1..3]`: ST_ServoAxis V3.0 伺服轴数组 (每轴74字段×3=222字段)
- 🔄 FB_1003接口变更: VAR_IN_OUT `io_stZAxis`/`io_stX1Axis` 直连轴结构体(删除6个悬空输出)

---

## 数据结构概览

```
DATA_BLOCK GlobalVars
├── stExternal  : STRUCT (22变量)    ← FB_ExternalDeviceInteraction V6.0.0
│   ├── 安全信号输入(4): EStop/SafetyDoor[8]/HmiStop/BusHealthy
│   ├── 组框机(4输入): AutoRunning/AllowFeed/Fault/EStop
│   ├── 打胶机(3输入): AutoRunning/Fault/EStop
│   ├── 机器人(3输入): AutoRunning/Fault/EStop
│   └── 输出(11): EStopActive/SafetyDoorFault[8]/HmiStopActive/...
│
├── stConveyor  : STRUCT (33变量)    ← 4×FB_1002 V7.0.0 (展开调用)
│   ├── 共享信号(6): AutoMode/ManualMode/Start/Stop/SeparateTimeoutMs/SafetyDoorOk/VfdFault
│   ├── 逐层输入(14×ARRAY[1..4]): 传感器7组 + 手动操作6组 + PickupConfirmed
│   ├── 逐层输出(10×ARRAY[1..4]): 执行器5组 + HMI状态5组
│   └── 汇总(3): q_bRunning(OR)/q_bFault(OR)/q_iAlarmCode(MIN)
│
├── stPickPlace : STRUCT (53变量)    ← FB_1003_PickPlace V7.0.0 (6步S20~S25)
│   ├── 系统控制(5): AutoMode/ManualMode/Start/Stop/Reset
│   ├── 手动操作(10): ZJogUp/ZJogDown/X1JogFwd/X1JogRev/FrontClamp/RearClamp/...×2
│   ├── 工艺参数(7): PickLayer_Input(🆕V7.1.1)/ZSpeed/X1Speed/ClampConfirmTime/LiftActionTime
│   ├── 上游信号(1×ARRAY[1..4]): LayerFeedDone
│   ├── 产品检测(4): LongEdge1/2/ShortEdge1/2
│   ├── 夹爪传感器(8): FrontClampClosed/Opened/RearClampClosed/Opened/...2
│   ├── 升降传感器(2): LiftHomePos/LiftWorkPoint
│   ├── 边框/满料检测(4): FrameDetect1/2/FullMaterialDetect1/2
│   └── 输出(14): FrontClamp/RearClamp/.../CurrentState/AlarmCode/Running (V7.0删除6个轴请求)
│
├── astServoAxis: ARRAY[1..3] OF ST_ServoAxis  ← 🆕 V7.1.0 伺服轴数组 (PLCopen MC Part 1)
│   ├── [1]=Z轴(升降)  → FB_1003.io_stZAxis  (VAR_IN_OUT直连)
│   ├── [2]=X1轴(横移) → FB_1003.io_stX1Axis (VAR_IN_OUT直连)
│   ├── [3]=X2轴(送料) → FB_1004后续迭代预留
│   └── 每轴子结构体(10个):
│       ├── stPower:  ST_SvPower  (6字段)  Enable/StopMode + Status/Busy/Error/ErrorID
│       ├── stHome:   ST_SvHome   (8字段)  Execute/HomeMode/Position + Done/Busy/...
│       ├── stAbs:    ST_SvAbs    (12字段) Execute/Pos/Vel/Acc/Dec/Jerk + Done/...
│       ├── stJog:    ST_SvJog    (11字段) Forward/Backward/Vel/Acc/Dec/Jerk + Done/...
│       ├── stStop:   ST_SvStop   (7字段)  Execute/Deceleration/Jerk + Done/...
│       ├── stHalt:   ST_SvHalt   (7字段)  Execute/Deceleration/Jerk + Done/...
│       ├── stRel:    ST_SvRel    (12字段) Execute/Dist/Vel/Acc/Dec/Jerk + Done/...
│       ├── stReset:  ST_SvReset  (5字段)  Execute + Done/Busy/Error/ErrorID
│       ├── stSensor: ST_Sensor   (5字段)  HomeSensor/FwdLimit/RevLimit/InPosition/ServoAlarm
│       └── rCurrentPos: REAL (1字段) 当前位置反馈 mm
│
│
├── stFeeder    : STRUCT (21变量)    ← FB_1004_GlueMachineFeeder V6.0.0 (4步D760)
│   ├── 系统控制(4): AutoMode/ManualMode/Start/Stop
│   ├── 手动操作(2): X2JogPos/X2JogNeg
│   ├── 上游信号(2): PlaceDone/X2Speed
│   ├── 打胶机交互(2): GlueMachineAllowFeed/PickupComplete
│   ├── X2区域传感器(4): X2ZoneSensor1/2/3/4
│   └── 输出(9): X2AxisHomeRequest/MoveAbsReq/TargetPos/AllowPickup/SafetyZoneSignal/...
│
├── stGlobal    : STRUCT (33变量)    ← FB_2001_CommonAlarm V6.0.0
│   ├── 系统/安全报警输入(8): EStopActive/SafetyDoorFault[8]/HmiStop/VfdFault[4]/X1X2ZServoFault/BusUnhealthy
│   ├── 输送机报警(5×ARRAY[1..4]): SeparateTimeout/SensorFaultBlockUp/Down/SepUp/Down
│   ├── 取放料报警(7): ClampTimeout/LiftTimeout/ProductMissing/SensorFault/FrameOnPlatform/X1Limit/ZLimit
│   ├── 送料报警(3): X2Limit/MoveTimeout/FrameOnPlatform
│   ├── 外部报警(3): FrameMachineFault/EStop/RobotFault
│   ├── 控制(1): Reset
│   └── 输出(10): CurrentAlarmCode/GlobalAlarmWord/AlarmCount/MesQueue[10]/NewAlarmPulse/Lights/Buzzer
│
└── FB实例(7)
    ├── fbExternalDevice  : FB_ExternalDeviceInteraction
    ├── fbConveyor_L1     : FB_1002_SingleLayerConveyor_BufferFraming  🆕 V7.0.0
    ├── fbConveyor_L2     : FB_1002_SingleLayerConveyor_BufferFraming  🆕 V7.0.0
    ├── fbConveyor_L3     : FB_1002_SingleLayerConveyor_BufferFraming  🆕 V7.0.0
    ├── fbConveyor_L4     : FB_1002_SingleLayerConveyor_BufferFraming  🆕 V7.0.0
    ├── fbPickPlace       : FB_1003_PickPlace_BufferFraming
    ├── fbGlueFeeder      : FB_1004_GlueMachineFeeder_BufferFraming
    └── fbCommonAlarm     : FB_2001_CommonAlarm_AllStation
END_DATA_BLOCK
```

---

## 详细接口定义

### 第一部分: stExternal结构 (22变量) - FB_ExternalDeviceInteraction V6.0.0

#### 安全信号输入 (4个)
| 变量名 | 类型 | 初始值 | 说明 | 物理地址 |
|--------|------|--------|------|----------|
| `i_bEStop` | BOOL | FALSE | 急停按钮 | X101 |
| `i_bSafetyDoor` | ARRAY[1..8] OF BOOL | - | 8路安全门异常 | X140~X147 |
| `i_bHmiStop` | BOOL | FALSE | HMI停止按钮 | X77 |
| `i_bBusHealthy` | BOOL | FALSE | 总线/外设健康 | - |

#### 组框机输入 (4个)
| 变量名 | 类型 | 初始值 | 说明 |
|--------|------|--------|------|
| `i_bFrameMachineAutoRunning` | BOOL | FALSE | 组框机自动运行中 |
| `i_bFrameMachineAllowFeed` | BOOL | FALSE | 组框机允许送料 |
| `i_bFrameMachineFault` | BOOL | FALSE | 组框机故障 |
| `i_bFrameMachineEStop` | BOOL | FALSE | 组框机急停 |

#### 打胶机输入 (3个)
| 变量名 | 类型 | 初始值 | 说明 |
|--------|------|--------|------|
| `i_bGlueMachineAutoRunning` | BOOL | FALSE | 打胶机自动运行中 |
| `i_bGlueMachineFault` | BOOL | FALSE | 打胶机故障 |
| `i_bGlueMachineEStop` | BOOL | FALSE | 打胶机急停 |

#### 机器人输入 (3个)
| 变量名 | 类型 | 初始值 | 说明 |
|--------|------|--------|------|
| `i_bRobotAutoRunning` | BOOL | FALSE | 机器人自动运行中 |
| `i_bRobotFault` | BOOL | FALSE | 机器人故障 |
| `i_bRobotEStop` | BOOL | FALSE | 机器人急停 |

#### 输出 (11个)
| 变量名 | 类型 | 初始值 | 说明 |
|--------|------|--------|------|
| `q_bEStopActive` | BOOL | FALSE | 急停激活汇总 |
| `q_bSafetyDoorFault` | ARRAY[1..8] OF BOOL | - | 安全门异常(给FB_2001) |
| `q_bHmiStopActive` | BOOL | FALSE | HMI停止激活 |
| `q_bFrameMachineRequestFeed` | BOOL | FALSE | 请求组框机送料 |
| `q_bFrameMachinePause` | BOOL | FALSE | 组框机暂停 |
| `q_bFrameMachineReady` | BOOL | FALSE | 本机就绪,可接收 |
| `q_bGlueMachineRequestRun` | BOOL | FALSE | 请求打胶机运行 |
| `q_bGlueMachineResetReq` | BOOL | FALSE | 打胶机复位请求 |
| `q_bRobotAllowStacking` | BOOL | FALSE | 允许机器人堆叠 |
| `q_bRobotStopStacking` | BOOL | FALSE | 停止机器人堆叠 |
| `q_bRobotResetReq` | BOOL | FALSE | 机器人复位请求 |

---

### 第二部分: stConveyor结构 (33变量) - 4×FB_1002 V7.0.0

**架构变化 V6→V7**: FB_1001 容器取消，OB1 展开调用 4 个 FB_1002 实例。每层共用信号为标量，逐层信号为 ARRAY[1..4]。

#### 共享信号 (6个标量, 4层共用)

| 变量名 | 类型 | 初始值 | 说明 |
|--------|------|--------|------|
| `i_bAutoMode` | BOOL | FALSE | 自动运行模式 |
| `i_bManualMode` | BOOL | FALSE | 手动调试模式 |
| `i_bStart` | BOOL | FALSE | 自动循环启动 (上升沿) |
| `i_bStop` | BOOL | FALSE | 停止 (电平有效) |
| `i_iSeparateTimeoutMs` | INT | 5000 | 分料超时时间 (ms, 0~60000) |
| `i_bSafetyDoorOk` | BOOL | TRUE | 安全门状态 (TRUE=关闭OK) |
| `i_bVfdFault` | BOOL | FALSE | 变频器故障 |

#### 逐层输入 ARRAY[1..4] (14组)

| 变量名 | 类型 | 说明 | 来源 |
|--------|------|------|------|
| `i_aPreSeparateSensor` | ARRAY[1..4] OF BOOL | 分料前接近开关 | IO |
| `i_aPositionSensor1` | ARRAY[1..4] OF BOOL | 到位传感器1 | IO |
| `i_aPositionSensor2` | ARRAY[1..4] OF BOOL | 到位传感器2 (冗余) | IO |
| `i_aBlockCylinderUp` | ARRAY[1..4] OF BOOL | 阻挡气缸上位 | IO |
| `i_aBlockCylinderDown` | ARRAY[1..4] OF BOOL | 阻挡气缸下位 | IO |
| `i_aSeparateCylinderUp` | ARRAY[1..4] OF BOOL | 分料气缸上位 | IO |
| `i_aSeparateCylinderDown` | ARRAY[1..4] OF BOOL | 分料气缸下位 | IO |
| `i_aPickupConfirmed` | ARRAY[1..4] OF BOOL | 取料机构已取走物料 | ←FB_1003 |
| `i_aManBlockExtend` | ARRAY[1..4] OF BOOL | 手动: 阻挡下降 | HMI |
| `i_aManBlockRetract` | ARRAY[1..4] OF BOOL | 手动: 阻挡上升 | HMI |
| `i_aManSeparatePush` | ARRAY[1..4] OF BOOL | 手动: 分料推出 | HMI |
| `i_aManConveyorFwd` | ARRAY[1..4] OF BOOL | 手动: 输送正转 | HMI |
| `i_aManConveyorRev` | ARRAY[1..4] OF BOOL | 手动: 输送反转 | HMI |
| `i_aManConveyorSlow` | ARRAY[1..4] OF BOOL | 手动: 输送慢速 | HMI |

#### 逐层输出 ARRAY[1..4] (10组)

| 变量名 | 类型 | 说明 | 去向 |
|--------|------|------|------|
| `q_aBlockSolenoid` | ARRAY[1..4] OF BOOL | 阻挡电磁阀 (TRUE=下降) | IO (Y30~Y37) |
| `q_aSeparateSolenoid` | ARRAY[1..4] OF BOOL | 分料电磁阀 (TRUE=推出) | IO (Y30~Y37) |
| `q_aConveyorFwd` | ARRAY[1..4] OF BOOL | 输送带正转 | IO (Y10~Y23) |
| `q_aConveyorRev` | ARRAY[1..4] OF BOOL | 输送带反转 | IO (Y10~Y23) |
| `q_aConveyorSlow` | ARRAY[1..4] OF BOOL | 输送带慢速 | IO (Y10~Y23) |
| `q_aLayerStep` | ARRAY[1..4] OF INT | 各层当前步序 0~70 | HMI |
| `q_aLayerAlarmCode` | ARRAY[1..4] OF INT | 各层报警码 (0=正常) | HMI + FB_2001 |
| `q_aLayerRunning` | ARRAY[1..4] OF BOOL | 各层运行中 | HMI |
| `q_aLayerFault` | ARRAY[1..4] OF BOOL | 各层故障 | HMI |
| `q_aLayerFeedDone` | ARRAY[1..4] OF BOOL | 各层放料完成 (脉冲) | →FB_1003 |
| `q_aLayerSensorFault` | ARRAY[1..4] OF BOOL | 各层传感器故障 | →FB_2001 |

#### 汇总变量 (OB1计算后回写, 3个)

| 变量名 | 类型 | 初始值 | 说明 | 逻辑 |
|--------|------|--------|------|------|
| `q_bRunning` | BOOL | FALSE | 输送机总运行中 (HMI) | 4层 OR |
| `q_bFault` | BOOL | FALSE | 输送机总故障 (HMI+互锁) | 4层 OR |
| `q_iAlarmCode` | INT | 0 | 最高优先级报警码 (HMI+FB_2001) | 4层 MIN(>0) |

---

### 第三部分: stPickPlace结构 (52变量) - FB_1003_PickPlace V6.0.0

#### 系统控制 (4个)
| 变量名 | 类型 | 初始值 | 说明 |
|--------|------|--------|------|
| `i_bAutoMode` | BOOL | FALSE | 自动模式 |
| `i_bManualMode` | BOOL | FALSE | 手动模式 |
| `i_bStart` | BOOL | FALSE | 启动 |
| `i_bStop` | BOOL | FALSE | 停止 |

#### 手动操作 (6个)
| 变量名 | 类型 | 初始值 | 说明 |
|--------|------|--------|------|
| `i_bLx_FrontClamp` | BOOL | FALSE | 手动-前夹紧 |
| `i_bLx_RearClamp` | BOOL | FALSE | 手动-后夹紧 |
| `i_bLx_FrontClamp2` | BOOL | FALSE | 手动-前夹紧2 |
| `i_bLx_RearClamp2` | BOOL | FALSE | 手动-后夹紧2 |
| `i_bLx_LiftUp` | BOOL | FALSE | 手动-升降上升 |
| `i_bLx_LiftDown` | BOOL | FALSE | 手动-升降下降 |

#### 工艺参数 (7个)
| 变量名 | 类型 | 初始值 | 说明 | 范围 |
|--------|------|--------|------|------|
| `i_iPickLayer_Input` | INT | 0 | **🆕V7.1.1** 外部指定取料层号(1~4), 0=无效 (HMI/上位机设置) | 0~4 |
| `i_rZAxisSpeed` | REAL | 100.0 | Z轴速度(mm/s) | 10~200 |
| `i_rX1AxisSpeed` | REAL | 150.0 | X1轴速度(mm/s) | 10~300 |
| `i_iClampConfirmTime` | INT | 500 | 夹紧确认时间(ms) | 100~2000 |
| `i_iLiftActionTime` | INT | 3000 | 升降动作超时(ms) | 1000~10000 |

#### 上游信号 (1个)
| 变量名 | 类型 | 说明 |
|--------|------|------|
| `i_bLayerFeedDone` | ARRAY[1..4] OF BOOL | L1~L4各层放料完成 |

#### 产品检测 (4个)
| 变量名 | 类型 | 说明 |
|--------|------|------|
| `i_bLongEdge1Detect` | BOOL | 长边1光电 |
| `i_bLongEdge2Detect` | BOOL | 长边2光电 |
| `i_bShortEdge1Detect` | BOOL | 短边1光电 |
| `i_bShortEdge2Detect` | BOOL | 短边2光电 |

#### 夹爪传感器 (8个)
| 变量名 | 类型 | 说明 |
|--------|------|------|
| `i_bFrontClampClosed` | BOOL | 前夹紧位1 |
| `i_bFrontClampOpened` | BOOL | 前松开位1 |
| `i_bRearClampClosed` | BOOL | 后夹紧位1 |
| `i_bRearClampOpened` | BOOL | 后松开位1 |
| `i_bFrontClamp2Closed` | BOOL | 前夹紧位2 |
| `i_bFrontClamp2Opened` | BOOL | 前松开位2 |
| `i_bRearClamp2Closed` | BOOL | 后夹紧位2 |
| `i_bRearClamp2Opened` | BOOL | 后松开位2 |

#### 升降传感器 (2个)
| 变量名 | 类型 | 说明 |
|--------|------|------|
| `i_bLiftHomePos` | BOOL | 升降上位 |
| `i_bLiftWorkPoint` | BOOL | 升降下位 |

#### 边框/满料检测 (4个)
| 变量名 | 类型 | 说明 |
|--------|------|------|
| `i_bFrameDetect1` | BOOL | 边框检测1 |
| `i_bFrameDetect2` | BOOL | 边框检测2 |
| `i_bFullMaterialDetect1` | BOOL | 满料检测1 |
| `i_bFullMaterialDetect2` | BOOL | 满料检测2 |

#### 输出 (19个)
| 变量名 | 类型 | 初始值 | 说明 |
|--------|------|--------|------|
| `q_bFrontClamp` | BOOL | FALSE | 前夹紧输出 |
| `q_bRearClamp` | BOOL | FALSE | 后夹紧输出 |
| `q_bFrontClamp2` | BOOL | FALSE | 前夹紧2输出 |
| `q_bRearClamp2` | BOOL | FALSE | 后夹紧2输出 |
| `q_bLiftUp` | BOOL | FALSE | 上升 |
| `q_bLiftDown` | BOOL | FALSE | 下降 |
| `q_bZAxisHomeRequest` | BOOL | FALSE | Z轴回原点请求 |
| `q_bZAxisMoveAbsReq` | BOOL | FALSE | Z轴绝对定位请求 |
| `q_rZAxisTargetPos` | REAL | 0.0 | Z轴目标位置 |
| `q_bX1AxisHomeRequest` | BOOL | FALSE | X1轴回原点请求 |
| `q_bX1AxisMoveAbsReq` | BOOL | FALSE | X1轴绝对定位请求 |
| `q_rX1AxisTargetPos` | REAL | 0.0 | X1轴目标位置 |
| `q_iCurrentState` | INT | 0 | 当前步序(0~5=S20~S25) |
| `q_iCurrentPickLayer` | INT | 0 | 当前取料层(1~4) |
| `q_iAlarmCode` | INT | 0 | 当前报警码 |
| `q_bPlaceDoneToFeeder` | BOOL | FALSE | 放料完成通知FB_1004 |
| `q_bSensorFault` | BOOL | FALSE | 夹紧/升降传感器冗余不一致 |
| `q_bProductMissing` | BOOL | FALSE | 4光电未全检到 |
| `q_bFrameOnPickupPlatform` | BOOL | FALSE | 取料平台有边框 |
| `q_bRunning` | BOOL | FALSE | 运行中 |

---

### 第四部分: stFeeder结构 (21变量) - FB_1004_GlueMachineFeeder V6.0.0

#### 系统控制 (4个)
| 变量名 | 类型 | 初始值 | 说明 |
|--------|------|--------|------|
| `i_bAutoMode` | BOOL | FALSE | 自动模式 |
| `i_bManualMode` | BOOL | FALSE | 手动模式 |
| `i_bStart` | BOOL | FALSE | 启动 |
| `i_bStop` | BOOL | FALSE | 停止 |

#### 手动操作 (2个)
| 变量名 | 类型 | 初始值 | 说明 |
|--------|------|--------|------|
| `i_bLx_X2JogPos` | BOOL | FALSE | 手动-X2正向点动 |
| `i_bLx_X2JogNeg` | BOOL | FALSE | 手动-X2反向点动 |

#### 上游信号 (2个)
| 变量名 | 类型 | 初始值 | 说明 |
|--------|------|--------|------|
| `i_bPlaceDone` | BOOL | FALSE | FB_1003放料完成脉冲 |
| `i_rX2Speed` | REAL | 120.0 | X2轴速度(mm/s) |

#### 打胶机交互 (2个)
| 变量名 | 类型 | 初始值 | 说明 | 物理地址 |
|--------|------|--------|------|----------|
| `i_bGlueMachineAllowFeed` | BOOL | FALSE | 打胶机允许送料 | X76 |
| `i_bGlueMachinePickupComplete` | BOOL | FALSE | 打胶机取料完成 | X102 |

#### X2区域传感器 (4个)
| 变量名 | 类型 | 初始值 | 说明 | 物理地址 |
|--------|------|--------|------|----------|
| `i_bX2ZoneSensor1` | BOOL | FALSE | X2区域前传感器1 | X72 |
| `i_bX2ZoneSensor2` | BOOL | FALSE | X2区域前传感器2 | X73 |
| `i_bX2ZoneSensor3` | BOOL | FALSE | X2区域后传感器1 | X74 |
| `i_bX2ZoneSensor4` | BOOL | FALSE | X2区域后传感器2 | X75 |

#### 输出 (9个)
| 变量名 | 类型 | 初始值 | 说明 | 物理地址 |
|--------|------|--------|------|----------|
| `q_bX2AxisHomeRequest` | BOOL | FALSE | X2回原点请求 | - |
| `q_bX2AxisMoveAbsReq` | BOOL | FALSE | X2绝对定位请求 | - |
| `q_rX2AxisTargetPos` | REAL | 0.0 | X2目标位置 | - |
| `q_bAllowPickup` | BOOL | FALSE | 允许打胶机抓料 | Y44 |
| `q_bSafetyZoneSignal` | BOOL | FALSE | 打胶机安全区 | Y47 |
| `q_iCurrentState` | INT | 0 | 当前D760值(0~3) | - |
| `q_iAlarmCode` | INT | 0 | 当前报警码 | - |
| `q_bFrameOnFeedPlatform` | BOOL | FALSE | 送料平台有边框 | - |
| `q_bRunning` | BOOL | FALSE | 运行中 | - |

---

### 第五部分: stGlobal结构 (33变量) - FB_2001_CommonAlarm V6.0.0

#### 系统/安全报警输入 (8个)
| 变量名 | 类型 | 说明 |
|--------|------|------|
| `i_bEStopActive` | BOOL | 急停(X101) |
| `i_bSafetyDoorFault` | ARRAY[1..8] OF BOOL | 8安全门异常 |
| `i_bHmiStop` | BOOL | HMI STOP(X77) |
| `i_bVfdFault` | ARRAY[1..4] OF BOOL | 4变频器异常 |
| `i_bX1ServoFault` | BOOL | X1伺服故障(X11) |
| `i_bX2ServoFault` | BOOL | X2伺服故障(X12) |
| `i_bZServoFault` | BOOL | Z伺服故障(X13) |
| `i_bBusUnhealthy` | BOOL | 总线/外设健康 |

#### 输送机报警 (5个)
| 变量名 | 类型 | 说明 |
|--------|------|------|
| `i_bConvSeparateTimeout` | ARRAY[1..4] OF BOOL | L1~L4分料超时 |
| `i_bConvSensorFaultBlockUp` | ARRAY[1..4] OF BOOL | 阻挡上位冗余 |
| `i_bConvSensorFaultBlockDown` | ARRAY[1..4] OF BOOL | 阻挡下位冗余 |
| `i_bConvSensorFaultSepUp` | ARRAY[1..4] OF BOOL | 分料上位冗余 |
| `i_bConvSensorFaultSepDown` | ARRAY[1..4] OF BOOL | 分料下位冗余 |

#### 取放料报警 (7个)
| 变量名 | 类型 | 说明 |
|--------|------|------|
| `i_bPickClampTimeout` | BOOL | 夹紧超时 |
| `i_bPickLiftTimeout` | BOOL | 升降超时 |
| `i_bPickProductMissing` | BOOL | 产品检测失败 |
| `i_bPickSensorFault` | BOOL | 取放料传感器冗余不一致 |
| `i_bPickFrameOnPlatform` | BOOL | 取料平台有边框 |
| `i_bPickX1Limit` | BOOL | X1轴限位 |
| `i_bPickZLimit` | BOOL | Z轴限位 |

#### 送料报警 (3个)
| 变量名 | 类型 | 说明 |
|--------|------|------|
| `i_bFeedX2Limit` | BOOL | X2轴限位 |
| `i_bFeedMoveTimeout` | BOOL | X2移动超时 |
| `i_bFeedFrameOnPlatform` | BOOL | 送料平台有边框 |

#### 外部报警 (3个)
| 变量名 | 类型 | 说明 |
|--------|------|------|
| `i_bFrameMachineFault` | BOOL | 组框机故障 |
| `i_bFrameMachineEStop` | BOOL | 组框机急停 |
| `i_bRobotFault` | BOOL | 机器人故障 |

#### 控制 (1个)
| 变量名 | 类型 | 说明 |
|--------|------|------|
| `i_bReset` | BOOL | 复位 |

#### 输出 (10个)
| 变量名 | 类型 | 初始值 | 说明 | 物理地址 |
|--------|------|--------|------|----------|
| `q_wCurrentAlarmCode` | WORD | 0 | 最高优先级报警码 | D402 |
| `q_wGlobalAlarmWord` | WORD | 0 | 全局报警字 | D400 |
| `q_iAlarmCount` | INT | 0 | MES累计报警次数 | D404 |
| `q_aMesQueue` | ARRAY[0..9] OF WORD | - | MES去重队列 | D406~D425 |
| `q_bNewAlarmPulse` | BOOL | FALSE | 新报警脉冲 | M201 |
| `q_bLightGreen` | BOOL | FALSE | 绿灯 | Y24 |
| `q_bLightRed` | BOOL | FALSE | 红灯 | Y25 |
| `q_bLightYellow` | BOOL | FALSE | 黄灯 | Y26 |
| `q_bBuzzer` | BOOL | FALSE | 蜂鸣器 | Y27 |
| `q_bResetLight` | BOOL | FALSE | 复位按钮灯 | Y50 |

---

## 报警码定义

### FB_2001_CommonAlarm 报警码优先级表

| 报警码 | 含义 | 优先级 | 来源 |
|--------|------|:------:|------|
| 1 | 急停激活 | P0 | stExternal.i_bEStop |
| 2~9 | 安全门1~8异常 | P0 | stExternal.i_bSafetyDoorFault |
| 11 | X1伺服故障 | P1 | stGlobal.i_bX1ServoFault |
| 12 | X2伺服故障 | P1 | stGlobal.i_bX2ServoFault |
| 13 | Z伺服故障 | P1 | stGlobal.i_bZServoFault |
| 14 | HMI STOP | P1 | stGlobal.i_bHmiStop |
| 15~18 | 变频器1~4故障 | P1 | stGlobal.i_bVfdFault |
| 30~33 | 阻挡上位传感器故障L1~L4 | P2 | stConveyor.q_bSensorFaultBlockUp |
| 50~53 | 分料下位传感器故障L1~L4 | P2 | stConveyor.q_bSensorFaultSeparateDown |
| 71 | 取放料传感器故障 | P2 | stPickPlace.q_bSensorFault |
| 72 | 产品检测失败 | P2 | stPickPlace.q_bProductMissing |
| 80 | 取料平台有边框 | P2 | stPickPlace.q_bFrameOnPickupPlatform |
| 81 | X1轴限位 | P2 | stGlobal.i_bPickX1Limit |
| 82 | Z轴限位 | P2 | stGlobal.i_bPickZLimit |
| 91 | X2轴限位 | P2 | stGlobal.i_bFeedX2Limit |
| 99~102 | 分料超时L1~L4 | P3 | stConveyor.q_bSeparateTimeout |
| 110 | 组框机故障/急停 | P3 | stGlobal.i_bFrameMachineFault/EStop |
| 115 | 机器人故障 | P3 | stGlobal.i_bRobotFault |
| 120 | 总线不健康 | P3 | stGlobal.i_bBusUnhealthy |

---

## 版本兼容性

| 版本 | 兼容性 | 说明 |
|------|--------|------|
| **V7.0.0** | ✅ 最新版 | Conveyor重构: FB_1001取消, 4×FB_1002展开, 33变量stConveyor |
| V6.0.0 | ❌ 已废弃 | FB_1001容器架构, 42变量stConveyor, 不兼容 |
| V3.0.0 | ❌ 已废弃 | o_前缀，INT类型报警码，接口不兼容 |

**升级路径**: V6.0.0 → V7.0.0 (stConveyor完全重写, OB1/DB1需同步更新)

---

## 关联文档
- **变更记录**: [变更记录_CHG-GlobalVars-V6.0.0.md](./变更记录_CHG-GlobalVars-V6.0.0.md)
- **架构文档**: [程序架构文档_ARC-DJ-2026-005-V2.0.0.md](../../../程序文档/程序架构文档_ARC-DJ-2026-005-V2.0.0.md)
- **命名规范**: LSP-905_SCL编程规范

---

*文档编译时间: 2026-05-18*
*生成工具: Trae IDE AI Assistant*
*审核状态: 待人工审核*
