# PLC变量定义文档

> 结构体与数据块的变量表，字段名、类型、说明与源码逐项一致（`plc docs check` 核对）。FB 的接口变量见各模块 `PRD/接口文档_IFC-*.md`。
> 2026-10-24 按新设计整体重写：旧版的配方、MES 队列、STD-820 对接结构体已随旧设计废弃。

## 变量表

### GlobalVars（数据块）

| 名称 | 类型 | 说明 |
|---|---|---|
| stMachine | ST_Machine | 模式、暂停、停止、状态字 (FB_1001 写) |
| stHmi | ST_Hmi | HMI 命令与设定值 |
| stIo | ST_Io | 全部物理输入 / 输出映射 |
| stAlarm | ST_Alarm | 报警触发、锁存、分级输出、声光 |
| stBridge | ST_Bridge | 站间中继信号 (FB_2002 写) |
| stHome | ST_HomePrepare | 回原点 / 准备序列 |
| stManual | ST_Manual | 手动 / 示教 |
| stConv | ST_ConveyorSystem | 4 层输送 (含 astLayer[1..4]) |
| stPP | ST_PickPlace | 取放料 |
| stFeed | ST_Feeder | X2 送料小车 |
| stExt | ST_ExternalLink | 组框机链路 / 打胶机握手 |
| astAxis | ARRAY[1..3] OF ST_ServoAxis | 伺服轴: [1] Z, [2] X1, [3] X2 |
| fbMode | FB_1001_MachineMode_BufferFraming | 模式 |
| fbHome | FB_1005_HomePrepare_BufferFraming | 回原点 / 准备 |
| fbManual | FB_1006_ManualTeach_BufferFraming | 手动 / 示教 |
| fbExternal | FB_ExternalDeviceInteraction | 组框机链路 (FB_3001) |
| fbBridge | FB_2002_StationBridge | 站间中继 |
| fbConv | FB_1007_ConveyorSystem_BufferFraming | 4 层输送 (内含 4 个 FB_1002) |
| fbPickPlace | FB_1003_PickPlace_BufferFraming | 取放料 |
| fbFeeder | FB_1004_GlueMachineFeeder_BufferFraming | 小车 |
| fbAlarm | FB_2001_CommonAlarm_AllStation | 报警 (最后调用) |

### ST_Bridge（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| bSafeZone | BOOL | 取料机构在安全区 (取放料 -> 4 层) |
| abLayerReq | ARRAY[1..4] OF BOOL | 各层请求取料 (4 层 -> 取放料) |
| abPickDone | ARRAY[1..4] OF BOOL | 各层取料完成 (取放料 -> 本层, 本层对本层) |
| bReqA | BOOL | 组 1 请求 A (小车 -> 取放料) |
| bReqB | BOOL | 组 2 请求 B (小车 -> 取放料, 4 根模式不用) |
| iGroupCount | INT | 取料组数: 2 根模式 2, 4 根模式 1 (取放料 -> 小车) |
| abFeedDone | ARRAY[1..2] OF BOOL | X1 组 1 / 组 2 送料完成 (取放料 -> 小车) |
| bFeedDoneClr | BOOL | 清两个"X1 送料完成" (小车 -> 取放料, 步 2 入口一拍) |
| abHoldConv | ARRAY[1..4] OF BOOL | 各层保持 (报警 -> 4 层) |
| bHoldPP | BOOL | 取放料保持 |
| bHoldFeeder | BOOL | 小车保持 |
| bHoldHome | BOOL | 回原点保持 |
| bInitReqConv | BOOL | 回原点预处理期间输送初始化 (回原点 -> 4 层) |
| bReleaseGripperLock | BOOL | F80 期间禁止 Z 定位 (回原点 -> 取放料) |
| bFeedPermit | BOOL | 送框许可 (组框机链路 -> 小车) |
| bPPAtS20 | BOOL | 取放料处于 S20 (取放料 -> 小车) |
| rZStandby | REAL | Z 待机点 D500 (取放料 -> 小车) |

### ST_Hmi（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| bManual | BOOL | 手动 (M0) |
| bAutoRun | BOOL | 自动运行键 (M6) |
| bStop | BOOL | 停止 (M7) |
| bPause | BOOL | 暂停 (M95) |
| bMute | BOOL | 静音 (M9) |
| bPrepareKey | BOOL | 准备键 (保留) |
| bBlinkOpt | BOOL | 强置选项 / 一键退料 (M515) |
| bTeach | ARRAY[1..6] OF BOOL | 示教 M61~M66 |
| bJog | ARRAY[1..6] OF BOOL | 点动 M156~M161 (X1 正反, X2 正反, Z 正反) |
| bSpeedUp | ARRAY[1..3] OF BOOL | 手动速度加 M150/M152/M154 (X1 / X2 / Z) |
| bSpeedDown | ARRAY[1..3] OF BOOL | 手动速度减 M151/M153/M155 |
| bPosX1 | ARRAY[1..4] OF BOOL | X1 定位 M162~M165 (D510 / D520 / D540 / D550) |
| bPosX2 | ARRAY[1..2] OF BOOL | X2 定位 M166 / M167 (D512 / D522) |
| bGripRelease | BOOL | 夹爪松开 (M67, 新增) |
| bLiftUp | BOOL | 升降缸上升 (新增, 待 HMI 核对) |
| bLiftDown | BOOL | 升降缸下降 (新增, 待 HMI 核对) |
| bConvForce | ARRAY[0..20] OF BOOL | 输送强制位 M70~M90 (M80 除外) |
| bFeedBtn | ARRAY[1..4] OF BOOL | 上料按钮 M250~M253 |
| bAutoSpeedUp | BOOL | 自动速度加 (M700) |
| bAutoSpeedDown | BOOL | 自动速度减 (M701) |
| bLinkMode | BOOL | 组框机联机 (M501) |
| bContinuousSend | BOOL | 连续送框 (M502) |
| bSingleSend | BOOL | 单套送框回读 (M510, PLC 回写) |
| rManualSpeed | ARRAY[1..3] OF REAL | 手动速度 D2000 / D2002 / D2004, 范围 500~5000 |
| rAutoSpeed | REAL | 自动速度 D600, 范围 10000~100000 |
| iAlarmNo | INT | 最小报警号 (D117), 无报警为 0 |
| iDeviceState | INT | 设备状态 (D116) |

### ST_Io（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| bX1Home | BOOL | X0 X1轴原点 |
| bX2Home | BOOL | X1 X2轴原点 |
| bZHome | BOOL | X2 Z轴原点 |
| bX1LimitFwd | BOOL | X3 X1轴前极限 |
| bX1LimitRev | BOOL | X4 X1轴后极限 |
| bX2LimitFwd | BOOL | X5 X2轴前极限 |
| bX2LimitRev | BOOL | X6 X2轴后极限 |
| bZLimitUp | BOOL | X7 Z轴上极限 |
| bZLimitDown | BOOL | X10 Z轴下极限 |
| bX1ServoAlarm | BOOL | X11 X1轴伺服报警 |
| bX2ServoAlarm | BOOL | X12 X2轴伺服报警 |
| bZServoAlarm | BOOL | X13 Z轴伺服报警 |
| bVfd1Alarm | BOOL | X14 变频器1异常 |
| bVfd2Alarm | BOOL | X15 变频器2异常 |
| bVfd3Alarm | BOOL | X16 变频器3异常 |
| bVfd4Alarm | BOOL | X17 变频器4异常 |
| bConv1DropEye | BOOL | X20 一层放料检测光电 |
| bConv1PreBlock | BOOL | X21 一层阻挡前接近开关 |
| bConv1Pos1 | BOOL | X22 一层到位接近开关1 |
| bConv1Pos2 | BOOL | X23 一层到位接近开关2 |
| bConv1BlockUp1 | BOOL | X24 一层阻挡气缸上位1 |
| bConv1BlockDown1 | BOOL | X25 一层阻挡气缸下位1 |
| bConv1SepUp1 | BOOL | X26 一层分料气缸上位1 |
| bConv1SepDown1 | BOOL | X27 一层分料气缸下位1 |
| bConv2DropEye | BOOL | X30 二层放料检测光电 |
| bConv2PreBlock | BOOL | X31 二层阻挡前接近开关 |
| bConv2Pos1 | BOOL | X32 二层到位接近开关1 |
| bConv2Pos2 | BOOL | X33 二层到位接近开关2 |
| bConv2BlockUp1 | BOOL | X34 二层阻挡气缸上位1 |
| bConv2BlockDown1 | BOOL | X35 二层阻挡气缸下位1 |
| bConv2SepUp1 | BOOL | X36 二层分料气缸上位1 |
| bConv2SepDown1 | BOOL | X37 二层分料气缸下位1 |
| bConv3DropEye | BOOL | X40 三层放料检测光电 |
| bConv3PreBlock | BOOL | X41 三层阻挡前接近开关 |
| bConv3Pos1 | BOOL | X42 三层到位接近开关1 |
| bConv3Pos2 | BOOL | X43 三层到位接近开关2 |
| bConv3BlockUp1 | BOOL | X44 三层阻挡气缸上位1 |
| bConv3BlockDown1 | BOOL | X45 三层阻挡气缸下位1 |
| bConv3SepUp1 | BOOL | X46 三层分料气缸上位1 |
| bConv3SepDown1 | BOOL | X47 三层分料气缸下位1 |
| bConv4DropEye | BOOL | X50 四层放料检测光电 |
| bConv4PreBlock | BOOL | X51 四层阻挡前接近开关 |
| bConv4Pos1 | BOOL | X52 四层到位接近开关1 |
| bConv4Pos2 | BOOL | X53 四层到位接近开关2 |
| bConv4BlockUp1 | BOOL | X54 四层阻挡气缸上位1 |
| bConv4BlockDown1 | BOOL | X55 四层阻挡气缸下位1 |
| bConv4SepUp1 | BOOL | X56 四层分料气缸上位1 |
| bConv4SepDown1 | BOOL | X57 四层分料气缸下位1 |
| bPPFrontProd1 | BOOL | X60 前夹料产品检测1 |
| bPPFrontProd2 | BOOL | X61 前夹料产品检测2 |
| bPPRearProd1 | BOOL | X62 后夹料产品检测1 |
| bPPRearProd2 | BOOL | X63 后夹料产品检测2 |
| bPPRearClamp1 | BOOL | X64 夹紧气缸后夹紧位1 |
| bPPRearOpen1 | BOOL | X65 夹紧气缸后松开位1 |
| bPPFrontClamp1 | BOOL | X66 夹紧气缸前夹紧位1 |
| bPPFrontOpen1 | BOOL | X67 夹紧气缸前松开位1 |
| bPPLiftUp | BOOL | X70 上升气缸上位 |
| bPPLiftDown | BOOL | X71 上升气缸下位 |
| bFeederFrontEye1 | BOOL | X72 送料机构前检测1 |
| bFeederFrontEye2 | BOOL | X73 送料机构前检测2 |
| bFeederRearEye1 | BOOL | X74 送料机构后检测1 |
| bFeederRearEye2 | BOOL | X75 送料机构后检测1 |
| bGlueAllowFeed | BOOL | X76 打胶机允许送料 |
| bHmiStopButton | BOOL | X77 触摸屏STOP按钮 |
| bResetButton | BOOL | X100 复位按钮 |
| bEStop | BOOL | X101 急停按钮 |
| bGluePickDone | BOOL | X102 打胶机取料完成信号 |
| bDoorCheck2 | BOOL | X103 电控门检测2 |
| bConv1BlockUp2 | BOOL | X104 一层阻挡气缸上位2 |
| bConv1BlockDown2 | BOOL | X105 一层阻挡气缸下位2 |
| bConv1SepUp2 | BOOL | X106 一层分料气缸上位2 |
| bConv1SepDown2 | BOOL | X107 一层分料气缸下位2 |
| bConv2BlockUp2 | BOOL | X110 二层阻挡气缸上位2 |
| bConv2BlockDown2 | BOOL | X111 二层阻挡气缸下位2 |
| bConv2SepUp2 | BOOL | X112 二层分料气缸上位2 |
| bConv2SepDown2 | BOOL | X113 二层分料气缸下位2 |
| bConv3BlockUp2 | BOOL | X114 三层阻挡气缸上位2 |
| bConv3BlockDown2 | BOOL | X115 三层阻挡气缸下位2 |
| bConv3SepUp2 | BOOL | X116 三层分料气缸上位2 |
| bConv3SepDown2 | BOOL | X117 三层分料气缸下位2 |
| bConv4BlockUp2 | BOOL | X120 四层阻挡气缸上位2 |
| bConv4BlockDown2 | BOOL | X121 四层阻挡气缸下位2 |
| bConv4SepUp2 | BOOL | X122 四层分料气缸上位2 |
| bConv4SepDown2 | BOOL | X123 四层分料气缸下位2 |
| bPPRearClamp2 | BOOL | X124 夹紧气缸后夹紧位2 |
| bPPRearOpen2 | BOOL | X125 夹紧气缸后松开位2 |
| bPPFrontClamp2 | BOOL | X126 夹紧气缸前夹紧位2 |
| bPPFrontOpen2 | BOOL | X127 夹紧气缸前松开位2 |
| bFrameDropEye1 | BOOL | X130 边框掉料检测1 (图纸已装, 原程序未使用) |
| bFrameDropEye2 | BOOL | X131 边框掉料检测2 (图纸已装, 原程序未使用) |
| bPPG3Prod1 | BOOL | 预留 夹爪3产品检测1 (4 根模式, 未接线) |
| bPPG3Prod2 | BOOL | 预留 夹爪3产品检测2 (4 根模式, 未接线) |
| bPPG3Clamp1 | BOOL | 预留 夹爪3夹紧位1 (4 根模式, 未接线) |
| bPPG3Clamp2 | BOOL | 预留 夹爪3夹紧位2 (4 根模式, 未接线) |
| bPPG3Open1 | BOOL | 预留 夹爪3松开位1 (4 根模式, 未接线) |
| bPPG3Open2 | BOOL | 预留 夹爪3松开位2 (4 根模式, 未接线) |
| bPPG4Prod1 | BOOL | 预留 夹爪4产品检测1 (4 根模式, 未接线) |
| bPPG4Prod2 | BOOL | 预留 夹爪4产品检测2 (4 根模式, 未接线) |
| bPPG4Clamp1 | BOOL | 预留 夹爪4夹紧位1 (4 根模式, 未接线) |
| bPPG4Clamp2 | BOOL | 预留 夹爪4夹紧位2 (4 根模式, 未接线) |
| bPPG4Open1 | BOOL | 预留 夹爪4松开位1 (4 根模式, 未接线) |
| bPPG4Open2 | BOOL | 预留 夹爪4松开位2 (4 根模式, 未接线) |
| bDoorL1 | BOOL | X140 左1安全门 |
| bDoorL2 | BOOL | X141 左2安全门 |
| bDoorL3 | BOOL | X142 左3安全门 |
| bDoorL4 | BOOL | X143 左4安全门 |
| bDoorR1 | BOOL | X144 右1安全门 |
| bDoorR2 | BOOL | X145 右2安全门 |
| bDoorR3 | BOOL | X146 右3安全门 |
| bDoorR4 | BOOL | X147 右4安全门 |
| bConv1Full1 | BOOL | X150 1层边框检测开关1 |
| bConv1Full2 | BOOL | X151 1层边框检测开关2 |
| bConv2Full1 | BOOL | X152 2层边框检测开关1 |
| bConv2Full2 | BOOL | X153 2层边框检测开关2 |
| bConv3Full1 | BOOL | X154 3层边框检测开关1 |
| bConv3Full2 | BOOL | X155 3层边框检测开关2 |
| bConv4Full1 | BOOL | X156 4层边框检测开关1 |
| bConv4Full2 | BOOL | X157 4层边框检测开关2 |
| bFramePauseIn | BOOL | X160 组框机开门暂停信号 |
| bFrameEStopIn | BOOL | X161 组框机急停信号 |
| bQConv1Fwd | BOOL | Y10 输送线1正转 |
| bQConv1Rev | BOOL | Y11 输送线1反转 |
| bQConv1Slow | BOOL | Y12 输送线1慢速 |
| bQConv2Fwd | BOOL | Y13 输送线2正转 |
| bQConv2Rev | BOOL | Y14 输送线2反转 |
| bQConv2Slow | BOOL | Y15 输送线2慢速 |
| bQConv3Fwd | BOOL | Y16 输送线3正转 |
| bQConv3Rev | BOOL | Y17 输送线3反转 |
| bQConv3Slow | BOOL | Y20 输送线3慢速 |
| bQConv4Fwd | BOOL | Y21 四层输送线正转 |
| bQConv4Rev | BOOL | Y22 输送线4反转 |
| bQConv4Slow | BOOL | Y23 输送线4慢速 |
| bQLampGreen | BOOL | Y24 杆灯绿 |
| bQLampRed | BOOL | Y25 杆灯红 |
| bQLampYellow | BOOL | Y26 杆灯黄 |
| bQBuzzer | BOOL | Y27 蜂鸣器 |
| bQConv1Block | BOOL | Y30 一层阻挡气缸 |
| bQConv1Sep | BOOL | Y31 一层分料气缸 |
| bQConv2Block | BOOL | Y32 二层阻挡气缸 |
| bQConv2Sep | BOOL | Y33 二层分料气缸 |
| bQConv3Block | BOOL | Y34 三层阻挡气缸 |
| bQConv3Sep | BOOL | Y35 三层分料气缸 |
| bQConv4Block | BOOL | Y36 四层阻挡气缸 |
| bQConv4Sep | BOOL | Y37 四层分料气缸 |
| bQPPRearClamp | BOOL | Y40 取料后侧气缸夹紧 |
| bQPPFrontClamp | BOOL | Y41 取料前侧气缸夹紧 |
| bQPPG3Clamp | BOOL | 预留 夹爪3夹紧 (4 根模式, 未接线) |
| bQPPG4Clamp | BOOL | 预留 夹爪4夹紧 (4 根模式, 未接线) |
| bQPPLiftUp | BOOL | Y42 气缸上升 |
| bQPPLiftDown | BOOL | Y43 气缸下降 |
| bQGluePickAllowed | BOOL | Y44 抓料可 |
| bQFramePause | BOOL | Y45 组框机暂停 |
| bQFrameEStop | BOOL | Y46 组框机急停 |
| bQGlueSafeZone | BOOL | Y47 给打胶机安全区信号 |
| bQLampResetBtn | BOOL | Y50 复位按钮指示灯 |

### ST_Machine（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| bManual | BOOL | 手动模式 (M0) |
| bHoming | BOOL | 回原点模式 (M1) |
| bPrepare | BOOL | 准备模式 (M2) |
| bAuto | BOOL | 自动模式 (M4) |
| bHomeDone | BOOL | 已回原点 (M94) |
| bFault | BOOL | 异常 / 急停类 (M8) |
| bPause | BOOL | 暂停 (M95) |
| bStopPending | BOOL | 停止请求: 本循环结束后退出自动 (F12 语义) |
| bPrepareDone | BOOL | 准备完成 (一拍) |
| bAllAtRest | BOOL | 输送 / 取放料 / 小车都在静止点 (FB_2002 写, FB_1001 读) |
| iDeviceState | INT | D116: 手动 1, 回原点 2, 准备 3, 自动 5, 待机 6, 异常 8, 暂停 10 |
| bSimulate | BOOL | 本机模拟 (M500): 跳过产品检测条件, 生产中必须为 FALSE |

### ST_ExternalLink（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| bLinkMode | BOOL | 组框机联机 (M501) |
| bContinuous | BOOL | 连续送框 (M502) |
| bSingle | BOOL | 单套送框许可 (M510) |
| bLinkSafetyOut | BOOL | 本机 -> 组框机: 安全异常 (R5000.0), F0 或 F1~F8 |
| bPeerSafetyFault | BOOL | 组框机 -> 本机: 安全异常 (R5010.0, 平台写入) |
| bPeerPermit | BOOL | 组框机 -> 本机: 允许送料 (R5011.0, 平台写入) |
| bLinkFail | BOOL | 通讯异常 (SB49 / SB6A / SB0A1 合并, 平台写入) |
| bY45 | BOOL | 组框机暂停输出 (Y45) |
| bY46 | BOOL | 组框机急停输出 (Y46) |
| arrTrig | ARRAY[0..1] OF BOOL | [0] F104 组框机安全异常, [1] F105 通讯异常 |

### ST_ConveyorSystem（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| astLayer | ARRAY[1..4] OF ST_SingleLayer | 4 层 (1 = 最下层) |
| bAllReady | BOOL | 4 层准备完成 |
| bAnyRequest | BOOL | 任一层有取料请求 |
| bAllAtRest | BOOL | 4 层都在静止点 (停止收尾判断) |

### ST_SingleLayer（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| bPreBlock | BOOL | 阻挡前到位传感器 |
| bPick1 | BOOL | 边框取料位接近开关 1 |
| bPick2 | BOOL | 边框取料位接近开关 2 |
| bFull1 | BOOL | 边框满料检测 1 |
| bFull2 | BOOL | 边框满料检测 2 |
| bBlkUp1 | BOOL | 阻挡气缸上位 1 |
| bBlkUp2 | BOOL | 阻挡气缸上位 2 |
| bBlkDn1 | BOOL | 阻挡气缸下位 1 |
| bBlkDn2 | BOOL | 阻挡气缸下位 2 |
| bSepUp1 | BOOL | 分料气缸上位 1 |
| bSepUp2 | BOOL | 分料气缸上位 2 |
| bSepDn1 | BOOL | 分料气缸下位 1 |
| bSepDn2 | BOOL | 分料气缸下位 2 |
| bInitReq | BOOL | 初始化请求 (回原点预处理期间) |
| bAutoRun | BOOL | 自动运行 |
| bHold | BOOL | 本层保持 (暂停 / 本层报警 / 全局 Hold) |
| bReset | BOOL | 异常停机 (M8 或进手动) |
| bSafeZone | BOOL | 取料机构在安全区 |
| bPickDone | BOOL | 本层取料完成 (来自取放料, 本层对本层) |
| bStopPending | BOOL | 停止请求 (本循环结束后不再开新循环) |
| bBlockDown | BOOL | 阻挡下降命令 (ON = 下降放行, OFF = 升起) |
| bSepDown | BOOL | 分料下降命令 (ON = 下降压料, OFF = 升起) |
| bFwd | BOOL | 输送正转 |
| bRev | BOOL | 输送反转 |
| bSlow | BOOL | 输送慢速 (只在正转或反转有效时才输出) |
| bReady | BOOL | 准备完成 |
| bRequest | BOOL | 请求取料 |
| bAtRest | BOOL | 静止点 (步 0), 供停止收尾判断 |
| iStep | INT | 当前步 (供 HMI / 测试) |
| bUnload | BOOL | 退料 (HMI 置位, 4 层准备完成后由 FB_1007 清除) |
| arrTrig | ARRAY[0..8] OF BOOL | 报警触发: [0..7] 气缸位置 (F34 起, 每层 +8), [8] 缺料 (F103 起, 每高一层 -1) |

### ST_PickGroup（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| rXPick | REAL | X1 取料点 (A: D510, B: D540) |
| rZPick | REAL | Z 取料高度 (A: D514, B: D544) |
| rXPlace | REAL | X1 放料点 (A: D520, B: D550) |

### ST_PickPlace（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| iStep | INT | 0 未激活, 20~25 = S20~S25 |
| iPhase | INT | 子相: 0 窗口, 1 轴运动, 2 等待转移 |
| iGroup | INT | 当前取料组: 1 = 组 1 (2 根模式 3+4 层; 4 根模式 1~4 层), 2 = 组 2 (2 根模式 1+2 层) |
| bAtRest | BOOL | 静止点 (S20 或未激活) |
| bSafeZone | BOOL | 输出: 取料机构在安全区 (给 Bridge) |
| astGroup | ARRAY[1..2] OF ST_PickGroup | [1] 组 1 (原前位对 A), [2] 组 2 (原后位对 B, 4 根模式不用) |
| iPickModeReq | INT | HMI 请求的取料模式: 2 = 一次 2 根 (005 原机), 4 = 一次 4 根 |
| iGripCount | INT | 本机夹爪个数 (现场配置): 2 或 4; 005 为 2 |
| iPickMode | INT | 生效的取料模式, 只在手动或待机且无料时才接受 iPickModeReq |
| iGroupCount | INT | 取料组数: 2 根模式 2 组, 4 根模式 1 组 |
| bModeInvalid | BOOL | 请求 4 根模式但夹爪个数不足: 不切换, 只提示 (不占报警号) |
| rZStandby | REAL | D500 Z 待机点 |
| rZPlace | REAL | D524 Z 放料高度 (前后位共用) |
| rAutoSpeed | REAL | D600 自动速度, 范围 10000~100000 |
| rPosTol | REAL | 位置判定容差 (脉冲, 待现场整定) |
| dSettleMs | DINT | 步入口窗口 / A、B 出现确认 / S25 松开计时 |
| dClampTimeoutMs | DINT | 夹紧超时 (F106) |
| dCylTimeoutMs | DINT | 夹爪 / 升降缸位置报警 |
| abPickDone | ARRAY[1..4] OF BOOL | 各层取料完成 (本层对本层) |
| abFeedDone | ARRAY[1..2] OF BOOL | X1 组 1 / 组 2 送料完成 |
| bClampFront | BOOL | 前夹爪夹紧命令 (Y41, 自保持) |
| bClampRear | BOOL | 后夹爪夹紧命令 (Y40, 自保持) |
| bClampG3 | BOOL | 预留 夹爪 3 夹紧命令 (4 根模式, 未接线) |
| bClampG4 | BOOL | 预留 夹爪 4 夹紧命令 (4 根模式, 未接线) |
| bLiftUp | BOOL | 升降缸上升命令 (Y42) |
| bLiftDown | BOOL | 升降缸下降命令 (Y43) |
| bGripOpenReq | BOOL | 要求松开夹爪 (回原点 / 准备 / 手动) |
| bLiftUpReq | BOOL | 要求升降缸上升 (手动) |
| bLiftDownReq | BOOL | 要求升降缸下降 (回原点 / 准备 / 手动) |
| arrTrig | ARRAY[0..15] OF BOOL | 报警触发: [0..3] F30~F33, [4..11] F66~F73, [12..13] F74~F75, [14] F106, [15] 预留 |

### ST_Feeder（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| iStep | INT | 0~3 (D760) |
| bAtRest | BOOL | 静止点 (步 0 / 1) |
| bReqA | BOOL | 组 1 请求 A |
| bReqB | BOOL | 组 2 请求 B (4 根模式不用) |
| bY44 | BOOL | 抓料可 / 送框信号 (Y44) |
| bY47 | BOOL | 安全区信号: X2 在取料点 (Y47) |
| bFeedPermit | BOOL | 出发许可 (来自 FB_3001, 由 FB_2002 汇入) |
| rPosPick | REAL | D512 X2 取料点 |
| rPosFeed | REAL | D522 X2 送料点 |
| rAutoSpeed | REAL | 自动速度 D600 (FB_2002 由取放料同步) |
| rPosTol | REAL | 位置判定容差 (脉冲, 待现场整定) |
| dSettleMs | DINT | 步入口窗口 |
| dFeedFullMs | DINT | 4 光电全亮计时 (步 1) |
| dFeedEmptyMs | DINT | 光电全灭持续超时, 与 X102 二选一返回 |
| dEyeAlarmMs | DINT | 光电异常报警 (F90 / F91) |
| arrTrig | ARRAY[0..4] OF BOOL | 报警触发: [0] F90, [1] F91, [2] F107 已取消, [3..4] 预留 |

### ST_Alarm（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| arrTrig | ARRAY[0..127] OF BOOL | 各机构每扫描写入的触发 (一位一写) |
| arrLatch | ARRAY[0..127] OF BOOL | 自保持输出 |
| bReset | BOOL | 复位键 (X100) 上升沿, 一拍 |
| bFault | BOOL | 任一 A 类锁存 (-> M8) |
| bAny | BOOL | 任一非提示类锁存 |
| abHoldConv | ARRAY[1..4] OF BOOL | 各层保持 |
| bHoldPP | BOOL | 取放料保持 |
| bHoldFeeder | BOOL | 小车保持 |
| bHoldHome | BOOL | 回原点保持 |
| iAlarmNo | INT | 最小锁存 F 号 (给 HMI D117), 无报警为 0 |
| bLampGreen | BOOL | 杆灯绿 (Y24) |
| bLampYellow | BOOL | 杆灯黄 (Y26) |
| bLampRed | BOOL | 杆灯红 (Y25) |
| bBuzzer | BOOL | 蜂鸣器 (Y27) |
| bResetLamp | BOOL | 复位按钮灯 (Y50) |

### ST_HomePrepare（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| iHomeStep | INT | 回原点步: 0 待机, 10 预处理, 20 Z, 30 X1/X2, 40 完成 |
| iPrepStep | INT | 准备步: 0 待机, 10~60 |
| bPreprocessDone | BOOL | 预处理完成 (夹爪松开 + 升降缸下位) |
| bAxisInitDone | BOOL | 准备: 三轴到位完成 |
| bHomeDoneZ | BOOL | Z 已回原点 |
| bHomeDoneX1 | BOOL | X1 已回原点 |
| bHomeDoneX2 | BOOL | X2 已回原点 |
| bPrepareDone | BOOL | 准备完成 (一拍) |
| bInitReqConv | BOOL | 输送初始化请求 (回原点预处理期间) |
| bReleaseGripperLock | BOOL | F80 期间禁止 Z 定位 |
| bGripOpenCmd | BOOL | 夹爪松开命令 (RST Y40 / Y41) |
| bLiftDownCmd | BOOL | 升降缸下降命令 |
| dPrepZDelayMs | DINT | 准备: 夹爪松开 + 升降缸下位后, Z 动作前延时 |
| dPrepX1DelayMs | DINT | 准备: Z 到待机点后, X1 动作前延时 |
| dPrepX2DelayMs | DINT | 准备: X1、Z 都到位后, X2 动作前延时 |

### ST_Manual（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| bJogLockZ | BOOL | Z 轴点动禁止 |
| bJogLockX1 | BOOL | X1 轴点动禁止 |
| bJogLockX2 | BOOL | X2 轴点动禁止 |
| abForce | ARRAY[0..20] OF BOOL | 输送强制位 (已按条件放行) |
| bTeachWrite | ARRAY[1..6] OF BOOL | 示教写入脉冲 |
| bGripOpenCmd | BOOL | 手动夹爪松开命令 |
| bLiftUpCmd | BOOL | 手动升降缸上升命令 |
| bLiftDownCmd | BOOL | 手动升降缸下降命令 |
| arrTrig | ARRAY[0..1] OF BOOL | 报警触发 (保留) |
