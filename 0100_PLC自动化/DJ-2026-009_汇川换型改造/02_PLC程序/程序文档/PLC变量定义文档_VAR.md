# PLC变量定义文档 - DJ-2026-009 汇川换型改造

> **项目编号**: DJ-2026-009
> **项目名称**: 汇川换型改造
> **文档版本**: V1.2.0（2026-10-22 报警汇总卡预做）
> **编制日期**: 2026-08-24
> **遵循规范**: LSP-905 SCL编程规范, LSP-907 项目结构规范

## 1. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | 汇川换型改造 PLC变量定义文档 |
| **文档版本** | V1.2.0 |
| **编制日期** | 2026-08-24 |
| **适用范围** | 汇川换型改造 项目 (DJ-2026-009) |
| **遵循规范** | IEC 61131-3, LSP-905 SCL编程规范 |

## 2. 变量命名规范

### 2.1 命名规则

遵循 LSP-905 SCL 编程规范的命名规则：

| 前缀 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `i_` | INPUT | 输入参数 | `i_bStart` |
| `q_` | OUTPUT | 输出参数 | `q_bRunning` |
| `io_` | IN_OUT | 输入输出参数 | `io_stServoAxis` |
| `st` | STRUCT | 结构体 | `stConveyor` |
| `a` | ARRAY | 数组 | `aLayerRunning[1..4]` |
| `b` | BOOL | 布尔量 | `bEnable` |
| `i` | INT | 整数 | `iAlarmCode` |
| `r` | REAL | 浮点数 | `rSpeed` |
| `t` | TIME | 时间 | `tDebounce` |
| `fb` | FB实例 | 功能块实例 | `fbConveyor` |

### 2.2 信号方向前缀

- `i_b` : BOOL 输入
- `i_i` : INT 输入
- `i_r` : REAL 输入
- `q_b` : BOOL 输出
- `q_i` : INT 输出
- `q_r` : REAL 输出

## 3. 全局变量 (GlobalVars)

### 3.1 GlobalVars 里的结构体与功能块实例（按 OB1 实际引用，2026-10-22 核对）

GlobalVars 的声明不在仓库里（见 `PLC_ST/00_全局数据/PRD/接口文档_IFC-GlobalVars.md` 第 3 节），下表按 OB1 实际用到的名字列出。

| 全局名 | 类型 | 说明 |
|--------|------|------|
| `stGlobal` | ST_CommonAlarm | 公共复位与报警汇总（字段见下文 ST_CommonAlarm 表）；复位 `stGlobal.i_bReset` 由 HMI 写 |
| `stExternal` | ST_ExternalDevice | 上下游对接总线（ST_UpstreamDocking / ST_DownstreamDocking + 急停 / 安全门 / 通讯综合故障） |
| `stStation1` | ST_Station1 | 工位 1 全量数据（Control / Status / Config / Sensors / Actuators） |
| `bModbusEnable` | BOOL | FB_3002 Modbus 客户端使能 |
| `bModbusUpLinkOK` / `bModbusDownLinkOK` | BOOL | 上 / 下游 Modbus 链路正常 |
| `awModbusUpRead` / `awModbusUpWrite` / `awModbusDownRead` / `awModbusDownWrite` | WORD 数组 | Modbus 寄存器映像，长度见 FB_3002 接口文档第 5 节 |

ST_ExternalDevice 与 ST_Station1 两个“外壳”结构体的字段表见 3.7 节（报警汇总卡已给 7 个子结构体成员补上行尾注释，原 C-6）。

原 3.1～3.5 节（stConveyor / stPickPlace / stFeeder 等，DJ-2026-005 三工站的变量）009 代码里没有，已移到文末附录。

### 3.6 组件 ID 与外部交互新增全局变量（CARD-DJ-2026-009-003 草稿）

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `sMachineModuleID` | STRING[32] | 本机 ID（组件 ID 第 2 格），**须声明在断电保持区（VAR_GLOBAL RETAIN）** |
| `stModuleIdHmi` | ST_ModuleIdHmi | 组件 ID 人工操作与时间参数（HMI），建议也放断电保持区（参数要保持；命令位 PLC 处理后自动清 0） |
| `bExtAllowInfeedAct` | BOOL | FB_3001 进料动作允许（供工位联锁，见待办） |
| `bExtAllowOutfeedAct` | BOOL | FB_3001 出料动作允许（供工位联锁，见待办） |
| `bExtUpstreamDone` | BOOL | 进料握手完成脉冲 |
| `bExtDownstreamDone` | BOOL | 出料握手完成脉冲 |
| `bExtComAlarm` | BOOL | 外部通讯综合报警 |
| `wExtErrorCode` | WORD | FB_3001 故障诊断字（位定义见 FB_3001 接口文档第 3 节） |

### ST_ModuleIdHmi（组件 ID 人工操作与时间参数）

| 名称 | 类型 | 说明 |
|------|------|------|
| `bCmdCopyFromUp` | BOOL | 拷入: 上游 ID -> 本机 ID (R4) |
| `bCmdManualEntry` | BOOL | 补录: sManualId -> 本机 ID (R5) |
| `bCmdRelease` | BOOL | 放行: 上游 ID 不合格时人工允许本次进料 (R5) |
| `bCmdClear` | BOOL | 清空本机 ID (R6) |
| `sManualId` | STRING[32] | 人工补录的组件 ID |
| `dLeaveTimeMs` | DINT | 出料中检测不到产品判产品离开的时间 ms (0 = 按 2000) |
| `dIdleClearMs` | DINT | 自动作业中无产品自动清本机 ID 的时间 ms (0 = 按 20000, 暂定) |

### 3.7 结构体（UDT）字段表（按代码生成，2026-10-22）

说明列与代码注释逐字一致，`plc docs check` 按这些表核对。

### ST_UpstreamDocking（上游对接 8 步握手，代码 `PLC_ST/01_外部设备交互/ST_ExternalDevice.scl`）

| 名称 | 类型 | 说明 |
|------|------|------|
| `bMachine_ReadyIn` | BOOL | (1) 机器准备好进料信号 |
| `bMachine_RcvModuleIdAck` | BOOL | (4) 机器收到组件ID信号 |
| `bMachine_AllowInfeed` | BOOL | (5) 机器允许上游进料信号 |
| `bMachine_InfeedArrived` | BOOL | (7) 机器给上游组件进料到位信号 |
| `bMachine_HeartbeatToUp` | BOOL | [心跳] 本机向上游心跳 (4s ON / 4s OFF) |
| `bUpstream_LineReady` | BOOL | (2) 上游流水线准备好信号 |
| `bUpstream_SendModuleId` | BOOL | (3) 上游流水线传组件ID信号 |
| `bUpstream_InfeedReq` | BOOL | (6) 上游流水线入料请求信号 |
| `bUpstream_InfeedArrivedAck` | BOOL | (8) 上游回收收到进料到位信号 |
| `bUpstream_HeartbeatFromUp` | BOOL | [心跳] 上游输入心跳 |
| `sRcvModuleID` | STRING[32] | 接收的组件 ID |
| `bUpstreamComFault` | BOOL | 上游通讯心跳超时故障 (12s) |
| `iInfeedStep` | INT | 进料握手当前步序 0~8 |

### ST_DownstreamDocking（下游对接 8 步握手，代码 `PLC_ST/01_外部设备交互/ST_ExternalDevice.scl`）

| 名称 | 类型 | 说明 |
|------|------|------|
| `bMachine_ReadyOut` | BOOL | (2) 机器准备好出料信号 |
| `bMachine_SendModuleId` | BOOL | (3) 机器传组件ID信号 |
| `bMachine_OutfeedReq` | BOOL | (6) 机器给下游出料请求信号 |
| `bMachine_OutfeedArrivedAck` | BOOL | (8) 机器回收收到进料到位信号 |
| `bMachine_HeartbeatToDown` | BOOL | [心跳] 本机向下游心跳 (4s ON / 4s OFF) |
| `bDownstream_LineReady` | BOOL | (1) 下游流水线准备好信号 |
| `bDownstream_RcvModuleIdAck` | BOOL | (4) 下游流水线收到组件ID信号 |
| `bDownstream_AllowOutfeed` | BOOL | (5) 下游流水线允许机器出料信号 |
| `bDownstream_OutfeedArrived` | BOOL | (7) 下游流水线给机器进料到位信号 |
| `bDownstream_HeartbeatFromDown` | BOOL | [心跳] 下游输入心跳 |
| `sSendModuleID` | STRING[32] | 发送给下游的组件 ID |
| `bDownstreamComFault` | BOOL | 下游通讯心跳超时故障 (12s) |
| `iOutfeedStep` | INT | 出料握手当前步序 0~8 |

### ST_Station1_Control（工位1 控制命令，代码 `PLC_ST/02_工位1_动作机构/ST_Station1.scl`）

| 名称 | 类型 | 说明 |
|------|------|------|
| `bAutoEnable` | BOOL | 自动运行使能 |
| `bManualStart` | BOOL | 手动单步启动 |
| `bReset` | BOOL | 故障复位 |
| `bPause` | BOOL | 暂停 |
| `bSingleStepMode` | BOOL | 单步模式 |
| `bSafeToRun` | BOOL | 运行许可, OB1 每扫描从 FB_1030 q_bSafeToRun 写入 (CARD-DJ-2026-009-004) |

### ST_Station1_Status（工位1 状态，代码 `PLC_ST/02_工位1_动作机构/ST_Station1.scl`）

| 名称 | 类型 | 说明 |
|------|------|------|
| `iStep` | DINT | 当前工步号 |
| `bRunning` | BOOL | 运行中 |
| `bDone` | BOOL | 本周期动作完成 |
| `bAlarm` | BOOL | 站级报警 |
| `iAlarmCode` | DINT | 报警代码 (101~199) |
| `bWaitMaterial` | BOOL | 等待来料 |
| `bProcessing` | BOOL | 加工中 |
| `bReadyOut` | BOOL | 【待确认】加工完成可出料 (出料步且气缸已松开) |
| `bProductPresent` | BOOL | 【待确认】本工位有产品 (入料到位/加工到位/预留产品传感器任一路为 1) |
| `bFrozen` | BOOL | 安全停机, 步序冻结在断点等续跑 (CARD-DJ-2026-009-004) |
| `bMotionStopped` | BOOL | 【待确认】动作完全停止: 电机无请求且不转, 气缸都在端点 (接 FB_1030 i_bMotionStopped) |

### ST_Station1_Config（工位1 参数，代码 `PLC_ST/02_工位1_动作机构/ST_Station1.scl`）

| 名称 | 类型 | 说明 |
|------|------|------|
| `dDebounceMs` | DINT | 光电消抖时间 (ms, 默认 100) |
| `dCylTimeoutMs` | DINT | 气缸动作超时时间 (ms, 默认 5000) |
| `dProcessTimeMs` | DINT | 工艺加工延时时间 (ms, 默认 2000) |

### ST_Station1_Sensors（工位1 传感器，代码 `PLC_ST/02_工位1_动作机构/ST_Station1.scl`）

| 名称 | 类型 | 说明 |
|------|------|------|
| `bInPosSensor` | BOOL | 入料到位光电 |
| `bWorkPosSensor` | BOOL | 加工到位光电 |
| `arrProductSens` | ARRAY[0..7] OF BOOL | 【待确认】产品检测传感器预留 8 路 (未接的保持 0), 任一路为 1 即有产品 |

### ST_Station1_Actuators（工位1 执行器，代码 `PLC_ST/02_工位1_动作机构/ST_Station1.scl`）

| 名称 | 类型 | 说明 |
|------|------|------|
| `stMotorFwd` | ST_ConveyorMotor | 进料输送电机 |
| `stCyl1` | ST_Cylinder | 夹紧气缸 |
| `stCyl2` | ST_Cylinder | 顶升气缸 |

### ST_CommonAlarm（公共报警全量数据，代码 `PLC_ST/05_公共报警/ST_CommonAlarm.scl`）

| 名称 | 类型 | 说明 |
|------|------|------|
| `i_bReset` | BOOL | 系统复位 (HMI); 报警汇总只认上升沿: 清报警历史、计数和新报警标志 |
| `i_dwSafetyAlarm` | DWORD | 安全报警字, 接 FB_1030 q_dwAlarm (只读, 位定义见 FB_1030 文件头) |
| `i_wExtErrorCode` | WORD | 上下游握手故障字, 接 FB_3001 q_wErrorCode (位定义见 FB_3001 常量区) |
| `i_iStationAlarm` | DINT | 工位 1 报警码, 接 stStation1.stStatus.iAlarmCode (101~199, 0 = 无) |
| `o_wGlobalAlarmWord` | WORD | 报警类别字: bit0 安全, bit1 上下游通讯/握手, bit2 工位 1 |
| `o_iCurrentAlarmCode` | INT | 当前最高优先级报警码 (码越小越优先, 0 = 无报警, 码表见 FB_2001 文件头) |
| `o_bAnyAlarmActive` | BOOL | 任意报警激活 |
| `o_iActiveAlarmCount` | INT | 当前同时存在的报警条数 |
| `o_iAlarmEventCount` | INT | 新报警累计次数 (复位清零, 到 32767 后从 1 重新计) |
| `o_arrAlarmHistory` | ARRAY[0..9] OF INT | 最近 10 条新报警码, [0] 最新, 空位为 0 |
| `o_bNewAlarmFlag` | BOOL | 有未确认的新报警 (出现新报警置 1, 按复位清, 可接蜂鸣器) |
| `o_bSafetyAlarmActive` | BOOL | 安全类报警激活 (急停/门/继电器/总线/复位被拒等) |
| `o_bExtAlarmActive` | BOOL | 上下游通讯/握手类报警激活 |
| `o_bStationAlarmActive` | BOOL | 工位 1 报警激活 |

### ST_ExternalDevice（上下游对接外壳，代码 `PLC_ST/01_外部设备交互/ST_ExternalDevice.scl`）

| 名称 | 类型 | 说明 |
|------|------|------|
| `stUpstream` | ST_UpstreamDocking | 上游对接 8 步握手 |
| `stDownstream` | ST_DownstreamDocking | 下游对接 8 步握手 |
| `bEmergencyStop` | BOOL | 外部总线急停 (1=正常, 0=急停) |
| `bSafetyDoorOK` | BOOL | 外部安全门锁信号 |
| `bAnyComFault` | BOOL | 外部通讯综合故障 |

### ST_Station1（工位1 外壳，代码 `PLC_ST/02_工位1_动作机构/ST_Station1.scl`）

| 名称 | 类型 | 说明 |
|------|------|------|
| `stControl` | ST_Station1_Control | 控制命令与模式 |
| `stStatus` | ST_Station1_Status | 运行状态与报警 |
| `stConfig` | ST_Station1_Config | 参数设定 |
| `stSensors` | ST_Station1_Sensors | 传感器输入 |
| `stActuators` | ST_Station1_Actuators | 执行机构 (电机/气缸) |

## 4. 功能块实例

| 实例名 | FB类型 | 声明位置 | 说明 |
|--------|--------|----------|------|
| `fbSafety` | FB_1030_SafetyManager（共享库） | GlobalVars | 全机安全管理，OB1 最前调用（CARD-DJ-2026-009-004，安全区） |
| `fbModbusClient` | FB_3002_ModbusTcpClient | GlobalVars | 上下游 Modbus TCP 客户端数据映射 |
| `fbExternalDevice` | FB_3001_ExternalInteraction | GlobalVars | 上下游 8 步握手、心跳、组件 ID 三格 |
| `fbStation1` | FB_1001_Station1 | GlobalVars | 工位 1 动作机构 |
| `fbCommonAlarm` | FB_2001_CommonAlarm_AllStation | GlobalVars | 公共报警汇总：OB1 第 3 部分接入 FB_1030 q_dwAlarm、FB_3001 q_wErrorCode、工位 1 iAlarmCode（报警汇总卡） |

## 5. M/D 区规划

### 5.1 M 区 (内部继电器)

| 地址范围 | 用途 | 说明 |
|---------|------|------|
| M0~M4 | 模式选择/启停/复位 | HMI 写入 |
| M10~M49 | 手动操作信号 | HMI 写入 |
| M100~M199 | 状态回写 | PLC 写入，HMI 读取 |

### 5.2 D 区 (数据寄存器)

| 地址范围 | 用途 | 说明 |
|---------|------|------|
| D100~D112 | 工艺参数设定 | HMI 写入 |
| D400~D425 | 报警 D 区 | PLC 写入 |
| D406~D425 | MES 报警队列（005 旧规划，009 不接 MES；报警历史为 `stGlobal.o_arrAlarmHistory`，HMI 地址待 HMI 选型后定） | 旧规划 |

## 6. 版本更新记录

| 版本 | 日期 | 更新内容 | 编制人 |
|------|------|----------|--------|
| V1.0.0 | 2026-08-24 | 初始版本 | auto-pm |
| V1.1.0 | 2026-10-22 | 按代码对齐：3.1 改为 OB1 实际全局名，新增 3.7 结构体字段表，第 4 节改为 009 实际实例；005 三工站旧条目移到附录 | Claude |
| V1.2.0 | 2026-10-22 | 报警汇总卡预做：ST_CommonAlarm 改为 009 实际报警源与输出；补 ST_ExternalDevice、ST_Station1 外壳字段表 | Claude |

## 附：代码中已不存在的旧条目（DJ-2026-005 三工站设计，009 未实现，留底不删）

#### 旧 3.1 系统全局变量

| 变量名 | 类型 | 地址 | 说明 |
|--------|------|------|------|
| `stGlobal.i_bReset` | BOOL | M4 | 系统复位 |
| `stGlobal.o_wGlobalAlarmWord` | WORD | D400 | 全局报警字 |
| `stGlobal.o_iCurrentAlarmCode` | INT | D402 | 当前报警码 |
| `stGlobal.o_bAnyAlarmActive` | BOOL | M100 | 任意报警激活 |
| `stGlobal.o_iMESAlarmCount` | INT | D404 | MES报警计数 |
| `stGlobal.o_iMESAlarmQueue` | ARRAY[1..10] OF INT | D406~D425 | MES报警队列 |

#### 旧 3.2 输送机变量 (stConveyor)

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `stConveyor.i_bAutoMode` | BOOL | 自动模式 |
| `stConveyor.i_bManualMode` | BOOL | 手动模式 |
| `stConveyor.i_bStart` | BOOL | 启动 |
| `stConveyor.i_bStop` | BOOL | 停止 |
| `stConveyor.q_bRunning` | BOOL | 运行中 |
| `stConveyor.q_bFault` | BOOL | 故障 |
| `stConveyor.q_iAlarmCode` | INT | 报警码 |

#### 旧 3.3 取放料变量 (stPickPlace)

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `stPickPlace.i_bAutoMode` | BOOL | 自动模式 |
| `stPickPlace.i_bManualMode` | BOOL | 手动模式 |
| `stPickPlace.q_iCurrentState` | INT | 当前状态 |
| `stPickPlace.q_iAlarmCode` | INT | 报警码 |
| `stPickPlace.q_bRunning` | BOOL | 运行中 |

#### 旧 3.4 送料变量 (stFeeder)

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `stFeeder.i_bAutoMode` | BOOL | 自动模式 |
| `stFeeder.q_iCurrentState` | INT | 当前状态 |
| `stFeeder.q_iAlarmCode` | INT | 报警码 |
| `stFeeder.q_bRunning` | BOOL | 运行中 |

#### 旧 3.5 外部设备变量 (stExternal)

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `stExternal.i_bEnable` | BOOL | 使能 |
| `stExternal.q_bSystemSafetyConditionMet` | BOOL | 系统安全条件满足 |
| `stExternal.q_bExternalDeviceFault` | BOOL | 外部设备故障 |


#### 旧 4. 功能块实例

| 实例名 | FB类型 | 声明位置 | 说明 |
|--------|--------|----------|------|
| `fbConveyor` | FB_1002_SingleLayerConveyor | GlobalVars | 输送机实例 |
| `fbPickPlace` | FB_1003_PickPlace | GlobalVars | 取放料实例 |
| `fbFeeder` | FB_1004_GlueMachineFeeder | GlobalVars | 送料实例 |
| `fbExternal` | FB_ExternalDeviceInteraction | GlobalVars | 外部设备交互实例 |
| `fbCommonAlarm` | FB_2001_CommonAlarm | GlobalVars | 公共报警实例 |

