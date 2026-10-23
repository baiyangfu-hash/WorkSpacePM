# 接口文档 FB_1013_NinetyDegreeTransfer

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | FB_1013 九十度转向机构接口定义 |
| **文档版本** | V9.0.0 |
| **2026-10-22 对齐** | 接口表“说明”列按代码行尾注释逐字对齐（`plc docs check`），对齐前写法移到文末附录；只改文档，版本号和文件名不变 |
| **关联源码** | actuator/FB_1013_NinetyDegreeTransfer.scl |
| **编制日期** | 2026-05-29 |
| **编制人** | Trae |
| **审核人** | 人工 |
| **遵循规范** | 905_SCL编程规范_LSP（原801已归档，职能由905承接）, PLCopen MC Part 1 | 
| **V9.0.0 变更** | VAR_OUTPUT从70个精简至27个：删除冗余M0~M10/位置BOOL/派生状态共32个；报警合并为WORD类型(q_wAlarm+q_wErrorClass)；NV合并为BYTE(q_byNVState)；新增台面位置枚举(q_iTablePosition) |

## 1. 功能概述

**九十度转角移载机构控制块**，封装入料检测 -> 气缸升降 -> 取物动作 -> 电机正转(90度) -> 放物动作 -> 电机反转(90度) -> 气回升 -> 完成通知 的完整多步状态机。

适用于需要将物料从A工位（入料方向）经90度旋转转移至D工位（出料方向）的自动化输送场景，包含5组气缸执行器、1组旋转电机、多路位置传感器和完整的超时/报警诊断体系。

### 1.1 职责边界

| 做什么 | 不做什么 |
|--------|----------|
| 管理13步主状态机(S30~S42)的步进顺序 | 不决定何时启动周期（由编排器/OB1决定） |
| 通过VAR_IN_OUT直连ST_Cylinder控制5组气缸 | 不直接操作物理IO（由OB1映射） |
| 通过VAR_IN_OUT直连ST_ConveyorMotor控制旋转电机 | 不处理变频器参数配置 |
| 监控入料传感器(5路)+到位信号(多路) | 不负责上游来料的节拍协调 |
| 各动作超时计时与报警输出 | 不处理非本机构的报警汇总 |
| 断电保持(NV)状态恢复 | 不管理全局断电保持策略 |

### 1.2 实例化场景

| 场景 | 实例名 | 说明 |
|------|--------|------|
| 主线九十度转向机构 | fbNinetyDeg : FB_1013 | A口入料->90度正转->D口出料->90度反转回原位 |
| 备用转向单元 | fbNinetyDegBackup : FB_1013 | 同构冗余实例，独立步进器 |

### 1.3 机械结构示意

```
          A侧(入料)                          D侧(出料)
    ┌──────────────┐                   ┌──────────────┐
    │  入料检测     │ ──入物机构──→      │              │
    │  (5个传感器)  │                  │  出盘机构      │
    └──────┬───────┘                   └──────┬───────┘
           │                                  │
    ┌──────┴───────┐    旋转台面(90度)   ┌──────┴───────┐
    │   取物机构    │ ←―――――――――――→     │   放物机构    │
    │ (升降+夹取)   │    电机正/反转     │ (升降+释放)   │
    └──────────────┘                   └──────────────┘
           │
    ┌──────┴───────┐
    │  升降气缸     │  (整体升降: 上位=待机/下位=工作)
    │  +摆臂/推板   │
    └──────────────┘
```

## 2. 状态机步序常量

| 常量名 | 值 | 步骤名 | 说明 |
|--------|---|--------|------|
| S30_IDLE | 0 | 待机等待 | 全部复位，等待启动。检查入料、NV恢复 |
| S31_FEED_CHECK | 1 | 入料检测 | 检测5路入料传感器，确认有料 |
| S32_LIFT_DOWN | 2 | 气缸下行 | 升降气缸下降到工作位 |
| S33_PICK_DOWN | 3 | 取物下降 | 取物机构下降到取料高度 |
| S34_PICK_CLAMP | 4 | 取物夹取 | 夹取物料+确认 |
| S35_PICK_UP | 5 | 取物上升 | 取物机构上升收回 |
| S36_MOTOR_FWD | 6 | 电机正转90度 | 旋转台面正向旋转90度(A->D) |
| S37_PLACE_DOWN | 7 | 放物下降 | 放物机构下降到放料高度 |
| S38_PLACE_RELEASE | 8 | 放物释放 | 释放物料+确认 |
| S39_PLACE_UP | 9 | 放物上升 | 放物机构上升收回 |
| S40_MOTOR_REV | 10 | 电机反转90度 | 旋转台面反向旋转90度(D->A回原位) |
| S41_LIFT_UP | 11 | 气缸上行 | 升降气缸上升到待机位 |
| S42_CYCLE_DONE | 12 | 周期完成 | 输出完成信号，等待下一周期 |

## 3. 接口定义

### 3.1 VAR_INPUT (系统控制信号)

| 名称 | 类型 | 默认值 | 有效值域 | 说明 | 来源 |
|------|------|--------|----------|------|------|
| i_bReset | BOOL | FALSE | TRUE/FALSE | 系统复位   | OB1←HMI |
| i_bAutoMode | BOOL | FALSE | TRUE/FALSE | 自动模式   | OB1←HMI |
| i_bManualMode | BOOL | FALSE | TRUE/FALSE | 手动模式   | OB1←HMI |
| i_bStart | BOOL | FALSE | TRUE/FALSE | 启动信号        | OB1←HMI |
| i_bStop | BOOL | FALSE | TRUE/FALSE | 停止信号       | OB1←HMI |
| i_bEnable | BOOL | FALSE | TRUE/FALSE | 使能信号 | 编排器/OB1 |

### 3.2 VAR_INPUT (入料检测传感器)

| 名称 | 类型 | 默认值 | 有效值域 | 说明 | 来源 |
|------|------|--------|----------|------|------|
| i_bFeedDetect0 | BOOL | FALSE | TRUE/FALSE | 入料检测通道0  | OB1←IO |
| i_bFeedDetect1 | BOOL | FALSE | TRUE/FALSE | 入料检测通道1  | OB1←IO |
| i_bFeedDetect2 | BOOL | FALSE | TRUE/FALSE | 入料检测通道2  | OB1←IO |
| i_bFeedDetect3 | BOOL | FALSE | TRUE/FALSE | 入料检测通道3  | OB1←IO |
| i_bFeedDetect4 | BOOL | FALSE | TRUE/FALSE | 入料检测通道4  | OB1←IO |

### 3.3 VAR_INPUT (到位/位置传感器)

| 名称 | 类型 | 默认值 | 有效值域 | 说明 | 来源 |
|------|------|--------|----------|------|------|
| i_bPickPlaceDone | BOOL | FALSE | TRUE/FALSE | 取放完成确认       | OB1←FB_xxx |
| i_bLiftUpPos | BOOL | FALSE | TRUE/FALSE | 升降上位传感器    | OB1←IO |
| i_bLiftDownPos | BOOL | FALSE | TRUE/FALSE | 升降下位传感器    | OB1←IO |
| i_bFwdArrived | BOOL | FALSE | TRUE/FALSE | 正转到位传感器 | OB1←IO |
| i_bRevArrived | BOOL | FALSE | TRUE/FALSE | 反转到位传感器 | OB1←IO |

### 3.4 VAR_INPUT (工艺参数)

| 名称 | 类型 | 默认值 | 有效值域 | 说明 | 来源 |
|------|------|--------|----------|------|------|
| i_iFeedTimeoutMs | INT | 3000 | 0~60000 | 入料检测超时          | OB1←HMI |
| i_iLiftTimeoutMs | INT | 5000 | 0~60000 | 升降动作超时            | OB1←HMI |
| i_iPickTimeoutMs | INT | 3000 | 0~60000 | 取物动作超时       | OB1←HMI |
| i_iPlaceTimeoutMs | INT | 3000 | 0~60000 | 放物动作超时       | OB1←HMI |
| i_iMotorTimeoutMs | INT | 5000 | 0~60000 | 电机转动超时     | OB1←HMI |
| i_iClampConfirmMs | INT | 500 | 0~5000 | 夹取/释放确认时间     | OB1←HMI |
| i_iCycleDonePulseMs | INT | 500 | 0~2000 | Done脉冲宽度   | OB1←HMI |

### 3.5 VAR_OUTPUT (气缸/电机直接输出)

| 名称 | 类型 | 默认值 | 有效值域 | 说明 | 去向 |
|------|------|--------|----------|------|------|
| q_bOutputReset | BOOL | FALSE | TRUE/FALSE | 输出总复位      | OB1→IO |
| q_bCylinderUp | BOOL | FALSE | TRUE/FALSE | 主升降上升   | OB1→IO |
| q_bCylinderDown | BOOL | FALSE | TRUE/FALSE | 主升降下降   | OB1→IO |
| q_bPickUp | BOOL | FALSE | TRUE/FALSE | 取物升降上升  | OB1→IO |
| q_bPickDown | BOOL | FALSE | TRUE/FALSE | 取物升降下降  | OB1→IO |
| q_bPlaceUp | BOOL | FALSE | TRUE/FALSE | 放物升降上升     | OB1→IO |
| q_bPlaceDown | BOOL | FALSE | TRUE/FALSE | 放物升降下降     | OB1→IO |
| q_bSwingArmDown | BOOL | FALSE | TRUE/FALSE | 摆臂下降 | OB1→IO |
| q_bPushPlateUp | BOOL | FALSE | TRUE/FALSE | 推板上升 | OB1→IO |
| q_bPushPlateDown | BOOL | FALSE | TRUE/FALSE | 推板下降 | OB1→IO |
| q_bMotorFwd | BOOL | FALSE | TRUE/FALSE | 电机正转    | OB1→IO |
| q_bMotorRev | BOOL | FALSE | TRUE/FALSE | 电机反转    | OB1→IO |

### 3.6 VAR_OUTPUT (状态指示输出) — V9.0精简

| 名称 | 类型 | 默认值 | 有效值域 | 说明 | 去向 |
|------|------|--------|----------|------|------|
| q_bPickDone | BOOL | FALSE | TRUE/FALSE | 取物完成   | 编排器/HMI |
| q_bPlaceDone | BOOL | FALSE | TRUE/FALSE | 放物完成   | 编排器/HMI |
| q_iTablePosition | INT | 0 | 0~5 | 台面位置: 0=未知 1=A 2=AO 3=O 4=OD 5=D   | HMI |

> **V9.0变更说明**：删除了以下V7.0的状态输出 —— q_bWaitState1, q_bTrayIn, q_bCylinderAtTop/Bottom, q_bPickAtTop/Bottom, q_bPickUpDone, q_bSwingArmUpDone, q_bPosA_Picker/Feeder, q_bPosA/AO/O/OD/D, q_bFwdArrived/RevArrived, q_bA_InputHasMaterial/InputA_HasMaterial/CPortIn_HasMaterial, q_bM0~M10。这些信息均可通过 q_iCurrentStep、q_iTablePosition 或直接读取传感器输入获得。

### 3.7 VAR_OUTPUT (报警/错误输出) — V9.0 WORD类型

| 名称 | 类型 | 默认值 | 有效值域 | 说明 | 去向 |
|------|------|--------|----------|------|------|
| q_wAlarm | WORD | 0 | 0~16#3FFF | 报警位: bitN→报警码(130+N), N=0~13 | OB1→FB_2001/HMI |
| q_wErrorClass | WORD | 0 | 0~16#001F | 错误分类: bit0=主升降 bit1=取物 bit2=电机 bit3=放物 bit4=安全/入料 | OB1→FB_2001 |
| q_wErrorID | WORD | 0 | 130~143 | 当前错误编号 130~143 | OB1→FB_2001 |
| q_bError | BOOL | FALSE | TRUE/FALSE | 错误汇总标志 | 编排器→FB_2001 |

**q_wAlarm 位映射表**：

| 位 | 报警码 | 含义 |
|:--:|:------:|------|
| %X0 | 130 | 升降气缸下行超时 |
| %X1 | 131 | 升降气缸上行超时 |
| %X2 | 132 | 取物机构下降超时 |
| %X3 | 133 | 取物机构上升超时 |
| %X4 | 134 | 取物夹取失败/超时 |
| %X5 | 135 | 电机正转90度超时 |
| %X6 | 136 | 电机反转90度超时 |
| %X7 | 137 | 放物机构下降超时 |
| %X8 | 138 | 放物机构上升超时 |
| %X9 | 139 | 放物释放失败/超时 |
| %X10 | 140 | 入料检测无料/超时 |
| %X11 | 141 | 传感器冲突(上下位同时ON) |
| %X12 | 142 | 安全门未关闭 |
| %X13 | 143 | 电机/VFD故障 |

**q_wErrorClass 位映射表**：

| 位 | 分类 | 覆盖报警码 |
|:--:|------|-----------|
| %X0 | 主升降机构 | 130, 131 |
| %X1 | 取物机构 | 132, 133, 134 |
| %X2 | 旋转电机 | 135, 136, 143 |
| %X3 | 放物机构 | 137, 138, 139 |
| %X4 | 安全/入料 | 140, 141, 142 |

> **V9.0变更说明**：删除了V7.0的独立BOOL报警位(q_bAlarm0~10)和分类错误位(q_bError1~5)。HMI/编排器使用 `q_wAlarm.%Xn` 访问单个报警，或直接将 WORD 映射到报警字寄存器。

### 3.8 VAR_OUTPUT (PLCopen标准状态)

| 名称 | 类型 | 默认值 | 有效值域 | 说明 | 去向 |
|------|------|--------|----------|------|------|
| q_iCurrentStep | INT | 0 | 0~12 | 当前步序(调试用)            | OB1→HMI |
| q_bBusy | BOOL | FALSE | TRUE/FALSE | 运行中       | 编排器 |
| q_bDone | BOOL | FALSE | TRUE/FALSE | 完成脉冲      | 编排器 |
| q_bErrorStatus | BOOL | FALSE | TRUE/FALSE | 错误标志(PLCopen) | 编排器→FB_2001 |
| q_wErrorIDPLCopen | WORD | 0 | 130~143 | 错误号(PLCopen)      | OB1→FB_2001 |

### 3.9 VAR_OUTPUT (断电保持)

| 名称 | 类型 | 默认值 | 有效值域 | 说明 | 去向 |
|------|------|--------|----------|------|------|
| q_byNVState | BYTE | 0 | 0~16#07 | 断电保持: bit0=Running bit1=步序>0 bit2=Error | 内部/NV区 |

### 3.10 VAR_IN_OUT (结构体参数)

| 名称 | 类型 | 说明 | OB1接线 |
|------|------|------|---------|
| io_stMainCylinder | ST_Cylinder | 主升降气缸           | => astCylinder[1] |
| io_stPickCylinder | ST_Cylinder | 取物升降气缸           | => astCylinder[2] |
| io_stPlaceCylinder | ST_Cylinder | 放物升降气缸           | => astCylinder[3] |
| io_stSwingArmCyl | ST_Cylinder | 摆臂气缸           | => astCylinder[4] |
| io_stPushPlateCyl | ST_Cylinder | 推板气缸           | => astCylinder[5] |
| io_stRotateMotor | ST_ConveyorMotor | 旋转电机           | => astMotor[1] |

**ST_Cylinder 子字段访问路径 (V1.1.0)**:

| 子字段 | FB内用途 | 语义映射 |
|--------|---------|---------|
| `.Extend` | 伸出命令写入 | 升降→下降 / 取物→下降 / 放物→下降 / 摆臂→下 / 推板→降 |
| `.Retract` | 收回命令写入 | 升降→上升 / 取物→上升 / 放物→上升 / 摆臂→上 / 推板→升 |
| `.ExtendedPos` | 伸出位读取 | 下位 / 工作点 / 夹紧位 |
| `.RetractedPos` | 收回位读取 | 上位 / 原点 / 松开位 |
| `.TimeoutMs` | 超时参数读写 | 各气缸独立超时 |
| `.IsExtended` | 已伸出到位输出 | → 结构体内部状态 |
| `.IsRetracted` | 已收回到位输出 | → 结构体内部状态 |
| `.Timeout` | 超时报警输出 | → 汇总至q_bError |
| `.SensorFault` | 传感器冲突输出 | → 汇总至q_bError |

**ST_ConveyorMotor 子字段访问路径 (V1.1.0)**:

| 子字段 | FB内用途 | 语义映射 |
|--------|---------|---------|
| `.FwdCmd` | 正转命令写入 | 90度正转(A→D) |
| `.RevCmd` | 反转命令写入 | 90度反转(D→A) |
| `.SafetyDoorOk` | 安全门状态读取 | 旋转安全互锁 |
| `.VfdFault` | 变频器故障读取 | 电机故障检测 |
| `.Speed` | 速度设定读写 | 旋转速度 |
| `.FwdOut` | 正转实际输出 | → q_bMotorFwd |
| `.RevOut` | 反转实际输出 | → q_bMotorRev |
| `.Running` | 运行中状态 | → 状态指示 |
| `.VfdAlarm` | VFD报警输出 | → q_bError |

## 4. 行为逻辑

### 4.1 正常运行周期

```
完整周期流程 (S30 → S42):

S30_IDLE (待机)
  ├── 检查NV恢复断电前状态
  ├── 检查气缸在上位? 否则先回原点
  ├── 等待 i_bStart 上升沿
  └── [启动] → S31

S31_FEED_CHECK (入料检测)
  ├── 检测 i_bFeedDetect0~4 任一ON?
  ├── 有料 → S32, q_iTablePosition := 1(A)
  └── 无料 → 等待(可配超时) 或 报警140

S32_LIFT_DOWN (气缸下行)
  ├── io_stMainCylinder.Extend := TRUE
  ├── 等待 i_bLiftDownPos=TRUE
  ├── 超时 → Alarm130
  └── 到位 → S33

S33_PICK_DOWN (取物下降)
  ├── io_stPickCylinder.Extend := TRUE
  ├── 等待 ExtendedPos=TRUE
  ├── 超时 → Alarm132
  └── 到位 → S34

S34_PICK_CLAMP (取物夹取)
  ├── 摆臂下降 + 推板下降(夹取动作)
  ├── 等待 i_iClampConfirmMs 确认时间
  ├── 确认到位 → q_bPickDone, S35
  └── 失败 → Alarm134

S35_PICK_UP (取物上升)
  ├── io_stPickCylinder.Retract := TRUE
  ├── 等待 RetractedPos=TRUE
  ├── 超时 → Alarm133
  └── 到位 → S36

S36_MOTOR_FWD (电机正转90度)
  ├── VFD/安全门预检
  ├── io_stRotateMotor.FwdCmd := TRUE
  ├── q_iTablePosition := 2(AO)
  ├── 等待 i_bFwdArrived=TRUE → q_iTablePosition := 3(O)
  ├── 超时 → Alarm135
  └── 到位 → S37

S37_PLACE_DOWN (放物下降)
  ├── io_stPlaceCylinder.Extend := TRUE
  ├── q_iTablePosition := 4(OD) → 5(D)
  ├── 等待 ExtendedPos=TRUE
  ├── 超时 → Alarm137
  └── 到位 → S38

S38_PLACE_RELEASE (放物释放)
  ├── 摆臂上升 + 推板上升(释放动作)
  ├── 等待 i_iClampConfirmMs 确认时间
  ├── q_bPlaceDone := TRUE
  └── 确认到位 → S39

S39_PLACE_UP (放物上升)
  ├── io_stPlaceCylinder.Retract := TRUE
  ├── 等待 RetractedPos=TRUE
  ├── 超时 → Alarm138
  └── 到位 → S40

S40_MOTOR_REV (电机反转90度)
  ├── VFD/安全门预检
  ├── io_stRotateMotor.RevCmd := TRUE
  ├── 等待 i_bRevArrived=TRUE → q_iTablePosition := 1(A)
  ├── 超时 → Alarm136
  └── 到位 → S41

S41_LIFT_UP (气缸上行)
  ├── io_stMainCylinder.Retract := TRUE
  ├── 等待 i_bLiftUpPos=TRUE
  ├── 超时 → Alarm131
  └── 到位 → S42

S42_CYCLE_DONE (周期完成)
  ├── q_bDone := TRUE (脉冲输出)
  ├── q_bBusy := FALSE
  ├── q_byNVState := 0
  └── → S30_IDLE (等待下一周期)
```

### 4.2 停止处理

```
当 i_bStop=TRUE 且 q_bBusy=TRUE 时:
  → 当前步骤立即停止所有输出
  → 气缸命令全部清除 (Extend:=FALSE, Retract:=FALSE)
  → 电机命令清除 (FwdCmd:=FALSE, RevCmd:=FALSE)
  → 记录当前步序到q_byNVState(断电保持)
  → q_bBusy := FALSE
  → q_bError := FALSE (停止≠错误, 可恢复)
  → 步序不归零 (支持从断点恢复)
```

### 4.3 复位处理

```
当 i_bReset=TRUE 时:
  → 所有输出强制清零 (q_bOutputReset := TRUE)
  → 6个ST_Cylinder/ST_ConveyorMotor内部状态清除
  → 步进器归零 (iCurrentStep := S30_IDLE)
  → 所有报警/错误清零 (q_wAlarm:=0, q_wErrorClass:=0, ...)
  → NV状态清除 (q_byNVState:=0)
  → q_bBusy := FALSE; q_bDone := FALSE; q_bError := FALSE
```

### 4.4 超时处理

```
每个动作步骤配有独立超时定时器:
  → 超时到达且尚未到位:
    - q_wAlarm对应位 := TRUE (锁存)
    - q_wErrorClass对应位 := TRUE
    - q_bError := TRUE
    - q_wErrorID := 对应报警码
    - 当前动作输出保持(不强制改变,由编排器决策)
    - 步序暂停(停在当前步,等待人工干预或复位)
```

### 4.5 手动模式

```
i_bManualMode=TRUE 时:
  → 状态机暂停 (iCurrentStep 保持不变, q_bBusy:=FALSE)
  → 各气缸/电机响应独立手动命令
  → 直接映射手动按钮→输出 (通过ST_Cylinder/ST_ConveyorMotor)
  → 安全互锁仍然生效
```

## 5. 接口交互协议

```
编排器/OB1                         FB_1013_NinetyDegreeTransfer
     │                                      │
     │── i_bStart := TRUE(沿) ──────────────→│  触发新周期
     │                                      │  S30→S31→...→S42
     │                                      │  (自动步进)
     │                                      │
     │←── q_bBusy := TRUE ─────────────────│  (运行中)
     │                                      │
     │←── q_bDone := TRUE(脉冲) ───────────│  (周期完成)
     │                                      │
     │── i_bStart := TRUE(沿) ──────────────→│  下一周期...
     │                                      │
     │── i_bStop := TRUE ──────────────────→│  停止
     │←── q_bBusy := FALSE ────────────────│
     │                                      │
     │── i_bReset := TRUE ─────────────────→│  复位
     │←── q_bOutputReset := TRUE ──────────│  全部清零
     │                                      │
     │  [io_stMainCylinder] ─── VAR_IN_OUT ──│  气缸直连
     │  [io_stRotateMotor]  ─── VAR_IN_OUT ──│  电机直连
```

## 6. 接口统计

| 项目 | V7.0 | V9.0 | 变化 | 说明 |
|------|:----:|:----:|:----:|------|
| VAR_INPUT (系统控制) | 6 | 6 | — | Reset/Auto/Manual/Start/Stop/Enable |
| VAR_INPUT (传感器) | 10 | 10 | — | 5路入料+5路到位 |
| VAR_INPUT (工艺参数) | 6 | 7 | +1 | 新增 i_iFeedTimeoutMs |
| **VAR_INPUT 合计** | **22** | **23** | **+1** | |
| VAR_OUTPUT (驱动输出) | 12 | 12 | — | 气缸11+电机2(共享计数) |
| VAR_OUTPUT (状态指示) | 32 | 3 | **-29** | PickDone/PlaceDone/TablePosition |
| VAR_OUTPUT (报警错误) | 18 | 4 | **-14** | WORD类型: Alarm/ErrorClass/ErrorID/Error |
| VAR_OUTPUT (PLCopen) | 5 | 5 | — | Step/Busy/Done/ErrorStatus/ErrorIDPLCopen |
| VAR_OUTPUT (NV保持) | 3 | 1 | **-2** | NV_Retain→BYTE |
| **VAR_OUTPUT 合计** | **70** | **25** | **-45** | |
| VAR_IN_OUT (结构体) | 6 | 6 | — | 5xST_Cylinder + 1xST_ConveyorMotor |
| **总计** | **98** | **54** | **-44** | |

## 7. 关联文档

| 文档 | 路径 | 版本 |
|------|------|:----:|
| DSN | 详细设计说明书_DSN-FB1013-NinetyDegreeTransfer-V9.0.0.md | V9.0.0 |
| 气缸控制 IFC | 接口文档_IFC-FB1011-CylinderControl-V7.0.0.md | V7.0.0 |
| 电机控制 IFC | 接口文档_IFC-FB1012-ConveyorMotor-V7.0.0.md | V7.0.0 |
| ST_Cylinder类型 | ../../types/ST_Cylinder.scl | V1.1.0 |
| ST_ConveyorMotor类型 | ../../types/ST_ConveyorMotor.scl | V1.1.0 |
| 取放料机构 IFC | ../../../../DJ-2026-005/02_PLC程序/通用ST程序及变量表/pickplace/PRD/接口文档_IFC-FB1003-PickPlace-V7.0.0.md | V7.0.0 |
| 规范 | 905_SCL编程规范_LSP（法典 03_PLC自动化域；原801已归档，职能由905承接） | V1.2.1 | 
| 905规范 | ../../../../../01_需求与设计/10_编程及变量规范/905_SCL编程规范_DEV.md | V7.0.0 |

---

## 附：2026-10-22 对齐前的旧说明（留底，不删）

> 2026-10-22 按 `plc docs check` 把上面接口表的“说明”列逐字改成代码行尾注释（代码为准，只改文档，没改 .scl）。
> 下表是改之前文档里的写法，有些比代码注释多写了单位、触发方式或用途，留在这里备查；
> 其中与代码实际行为不一致的地方，见共享库对齐记录 `PRD/文档代码对齐记录_20261022.md` 第 3 节。

| 引脚 | 对齐前文档说明 | 现说明（= 代码注释） |
|------|------|------|
| i_bReset | 系统复位命令 | 系统复位 |
| i_bAutoMode | 自动模式选择 | 自动模式 |
| i_bManualMode | 手动模式选择 | 手动模式 |
| i_bStart | 启动信号(上升沿触发) | 启动信号 |
| i_bStop | 停止信号(电平有效) | 停止信号 |
| i_bFeedDetect0 | 入料检测传感器0 | 入料检测通道0 |
| i_bFeedDetect1 | 入料检测传感器1 | 入料检测通道1 |
| i_bFeedDetect2 | 入料检测传感器2 | 入料检测通道2 |
| i_bFeedDetect3 | 入料检测传感器3 | 入料检测通道3 |
| i_bFeedDetect4 | 入料检测传感器4 | 入料检测通道4 |
| i_bPickPlaceDone | 取放完成信号(外部确认) | 取放完成确认 |
| i_bLiftUpPos | 升降气缸上位/上限位 | 升降上位传感器 |
| i_bLiftDownPos | 升降气缸下位/下限位 | 升降下位传感器 |
| i_bFwdArrived | 正转到位信号 | 正转到位传感器 |
| i_bRevArrived | 反转到位信号 | 反转到位传感器 |
| i_iFeedTimeoutMs | 入料检测超时(ms)，0=关闭 | 入料检测超时 |
| i_iLiftTimeoutMs | 升降气缸动作超时(ms)，0=关闭 | 升降动作超时 |
| i_iPickTimeoutMs | 取物机构动作超时(ms) | 取物动作超时 |
| i_iPlaceTimeoutMs | 放物机构动作超时(ms) | 放物动作超时 |
| i_iMotorTimeoutMs | 电机旋转超时(ms) | 电机转动超时 |
| i_iClampConfirmMs | 夹取/释放确认时间(ms) | 夹取/释放确认时间 |
| i_iCycleDonePulseMs | 完成脉冲宽度(ms) | Done脉冲宽度 |
| q_bOutputReset | 复位输出(全部清零) | 输出总复位 |
| q_bCylinderUp | 升降气缸-上升 | 主升降上升 |
| q_bCylinderDown | 升降气缸-下降 | 主升降下降 |
| q_bPickUp | 取物机构-上升 | 取物升降上升 |
| q_bPickDown | 取物机构-下降 | 取物升降下降 |
| q_bPlaceUp | 入物/放物机构-上升 | 放物升降上升 |
| q_bPlaceDown | 入物/放物机构-下降 | 放物升降下降 |
| q_bMotorFwd | 旋转电机-正向 | 电机正转 |
| q_bMotorRev | 旋转电机-反向 | 电机反转 |
| q_bPickDone | 取物完成信号 | 取物完成 |
| q_bPlaceDone | 放物完成信号 | 放物完成 |
| q_iTablePosition | 台面位置枚举: 0=未知 1=A 2=AO 3=O 4=OD 5=D | 台面位置: 0=未知 1=A 2=AO 3=O 4=OD 5=D |
| q_wErrorID | 当前错误编号 | 当前错误编号 130~143 |
| q_iCurrentStep | 当前步序号(S30~S42对应0~12) | 当前步序(调试用) |
| q_bBusy | 功能块忙(运行中) | 运行中 |
| q_bDone | 单周期完成(脉冲) | 完成脉冲 |
| q_bErrorStatus | 错误发生(PLCopen) | 错误标志(PLCopen) |
| q_wErrorIDPLCopen | 当前错误ID(PLCopen标准) | 错误号(PLCopen) |
| io_stMainCylinder | 主升降气缸结构体 - 直读直写 | 主升降气缸 |
| io_stPickCylinder | 取物升降气缸结构体 - 直读直写 | 取物升降气缸 |
| io_stPlaceCylinder | 放物升降气缸结构体 - 直读直写 | 放物升降气缸 |
| io_stSwingArmCyl | 摆臂气缸结构体 - 直读直写 | 摆臂气缸 |
| io_stPushPlateCyl | 推板气缸结构体 - 直读直写 | 推板气缸 |
| io_stRotateMotor | 旋转电机结构体 - 直读直写 | 旋转电机 |
