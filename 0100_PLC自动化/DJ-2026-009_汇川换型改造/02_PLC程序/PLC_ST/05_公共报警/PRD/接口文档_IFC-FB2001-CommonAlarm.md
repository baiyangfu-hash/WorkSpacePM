# 接口文档 FB_2001_CommonAlarm_AllStation

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | FB_2001 公共报警接口定义 |
| **文档版本** | V9.3.0 |
| **关联源码** | 05_公共报警/FB_2001_CommonAlarm_AllStation.scl |
| **编制日期** | 2026-05-17（V9.2.0 按代码对齐 2026-10-22；V9.3.0 报警汇总卡预做 2026-10-22） |
| **编制人** | Trae |
| **遵循规范** | LSP-905 |
| **数据来源** | 源程序功能基线_SRC-DJ-2026-005-V1.0.0 |

## 1. 功能概述

按 009 代码（`FB_2001_CommonAlarm_AllStation.scl` V4.0.0，报警汇总卡预做，结构体整块传递）：只有一个接口变量 `io_stGlobal`，类型 `ST_CommonAlarm`。块内只读三路报警源（安全管理 FB_1030 `q_dwAlarm`、上下游握手 FB_3001 `q_wErrorCode`、工位 1 `iAlarmCode`），给 HMI 输出当前最高优先级报警码、报警类别字、同时报警条数、最近 10 条报警历史、新报警标志和累计次数。**本块不改任何动作**：急停、门锁、安全继电器的状态只拿来报警显示，停机、复位、运行许可都不在本块。结构体各字段见 `02_PLC程序/程序文档/PLC变量定义文档_VAR.md` 的 `ST_CommonAlarm` 表。

V9.1.0 写的是 DJ-2026-005 源程序基线的设计（急停、8 扇安全门、变频器、伺服、传感器冗余、指示灯、蜂鸣器等独立输入输出），009 代码里没有实现，已移到文末附录留底，不删。

## 2. 接口变量

| 名称 | 类型 | 方向 | 说明 |
|------|------|------|------|
| `io_stGlobal` | ST_CommonAlarm | VAR_IN_OUT | 公共报警工站全量数据结构体 |

OB1 第 3 部分先写三路报警源，再调用：

```
GlobalVars.stGlobal.i_dwSafetyAlarm := GlobalVars.fbSafety.q_dwAlarm;   // @安全区 圈出, 只读
GlobalVars.stGlobal.i_wExtErrorCode := GlobalVars.wExtErrorCode;
GlobalVars.stGlobal.i_iStationAlarm := GlobalVars.stStation1.stStatus.iAlarmCode;
GlobalVars.fbCommonAlarm(io_stGlobal := GlobalVars.stGlobal);
```

## 3. 行为说明

- **新报警**：某个报警码从无到有算一次（工位报警码从一个非 0 码变成另一个非 0 码也算）。每次新报警：码插到 `o_arrAlarmHistory[0]`，旧的往后挤，第 11 条丢掉；`o_iAlarmEventCount` 加 1（到 32767 后从 1 重新计）；`o_bNewAlarmFlag` 置 1。同一扫描出现多条新报警时，码最小的排在 [0]。
- **复位**（`i_bReset`，HMI 写）：只认上升沿，按住不重复清。只清历史、累计次数、新报警标志；还在的报警照常显示，不会因复位再记一次。复位那个扫描输出照常封包（原 V3.0.0 复位时 RETURN，输出保持旧值）。
- **当前报警码**：所有正在报警的码里最小的（码越小越优先）；`o_iActiveAlarmCount` 是同时在报的条数。
- **类别字** `o_wGlobalAlarmWord`：bit0 安全、bit1 上下游通讯/握手、bit2 工位 1。按类别置位，不再把报警码按位“或”（原来 1 OR 2 = 3 会混码）。
- 原 V3.0.0 的 8 条代码问题（文档代码对齐记录 C-1～C-8）按报警汇总卡逐条改掉，见卡说明。

## 4. 报警码表（009，V4.0.0）

| 码 | 含义 | 来源 |
|:--:|------|------|
| 0 | 无报警 | — |
| 1～8 | 第 1～8 个急停被按下 | FB_1030 q_dwAlarm bit0～7 |
| 9～16 | 第 1～8 扇门没关好/没锁 | bit8～15 |
| 17～24 | 第 1～8 道光栅被遮挡（009 无光栅，预留） | bit16～23 |
| 25～28 | 第 1～4 个安全继电器反馈故障 | bit24～27 |
| 29 | 总线断线（远程 IO / SV660N） | bit28 |
| 30 | 复位被拒：安全回路未恢复/门没锁/总线断 | bit29 |
| 31 | 复位过早：距第一次复位不足 10 s | bit30 |
| 32 | 门锁回失败 | bit31 |
| 41 | 进料握手因通讯故障中止 | FB_3001 q_wErrorCode bit0 |
| 42 | 出料握手因通讯故障中止 | bit1 |
| 43 | 自动作业中被中止，等人工复位 | bit2 |
| 44 | 预留（bit3 未定义） | bit3 |
| 45 | 上游通讯故障 | bit4 |
| 46 | 下游通讯故障 | bit5 |
| 47 | 进料第 20 步上游 ID 不合格 | bit6 |
| 48 | 握手中途中止，ID 待人工核对 | bit7 |
| 49～56 | 预留（bit8～15 未定义） | bit8～15 |
| 101 | 工位 1 进料超时 | FB_1001 iAlarmCode |
| 102 | 工位 1 夹紧/顶升超时 | 同上 |
| 103 | 工位 1 松开/出料超时 | 同上 |
| 104 | 工位 1 缩回超时 | 同上 |

HMI 报警文本按上表做；HMI 地址待 HMI 选型后定（旧文档的 D400～D425 是 005 的规划，009 不存在）。

### 4.1 DJ-2026-005 基线码表（留底，009 未用）

| 优先级 | 码 | 含义 | 源 |
|:-----:|:--:|------|-----|
| 0 | 0 | 无报警 | — |
| 1 | 1 | 急停 | F0 |
| 2 | 2~9 | 安全门1~8开 | F1~F8 |
| 3 | 11~13 | X1/X2/Z伺服故障 | F9~F11 |
| 4 | 14 | HMI STOP | F12 |
| 5 | 15~18 | 变频器1~4异常 | F13~F16 |
| 6 | 31~34 | L1传感器冗余不一致(阻挡/分料×4) | F30~F37 |
| 7 | 41~44 | L2传感器冗余不一致 | F40~F47 |
| 8 | 51~54 | L3传感器冗余不一致 | F50~F57 |
| 9 | 61~64 | L4传感器冗余不一致 | F60~F65 |
| 10 | 71 | 取放料夹紧传感器冗余不一致 | F66~F71 |
| 11 | 81 | 取料平台有边框 | F80 |
| 12 | 82 | 送料平台有边框 | F81 |
| 13 | 91 | 送料传感器异常 | F90~F91 |
| 14 | 100~103 | L1~L4分料超时 | F100~F103 |
| 15 | 110 | 组框机安全/通信异常 | F104~F105 |
| 16 | 120 | 总线/外设不健康 | 占位 |

## 5. 关联文档

| 文档 | 路径 |
|------|------|
| ALM | 报警码定义_ALM-DJ-2026-005-V6.0.0.md |
| CHG | 变更记录_CHG-FB2001-CommonAlarm-V6.0.0.md |
| UM | 使用说明_UM-FB2001-CommonAlarm-V6.0.0.md |

## 附：代码中已不存在的旧条目（DJ-2026-005 源程序基线设计，009 未实现，留底不删）

下列表格原为 V9.1.0 第 2、3 节。009 代码只有 `io_stGlobal` 一个接口变量，这些输入输出都不存在，留底不删。

### A.2 VAR_INPUT（旧） - 各工站报警信号

#### 2.1 系统/安全报警

| 名称 | 类型 | 默认值 | 说明 | 来源 |
|------|------|--------|------|------|
| i_bEStopActive | BOOL | FALSE | 急停(X101) | OB1←External |
| i_bSafetyDoorFault[1..8] | BOOL[1..8] | FALSE | 8安全门异常(X140~X147) | OB1←External |
| i_bHmiStop | BOOL | FALSE | HMI STOP(X77) | OB1←External |
| i_bVfdFault[1..4] | BOOL[1..4] | FALSE | 4变频器异常 | OB1←FB_1001 |
| i_bX1ServoFault | BOOL | FALSE | X1伺服故障(X11) | OB1←FB_1003 |
| i_bX2ServoFault | BOOL | FALSE | X2伺服故障(X12) | OB1←FB_1004 |
| i_bZServoFault | BOOL | FALSE | Z伺服故障(X13) | OB1←FB_1003 |
| i_bBusUnhealthy | BOOL | FALSE | 总线/外设健康位 | OB1←External |

#### 2.2 输送机报警

| 名称 | 类型 | 默认值 | 说明 | 来源 |
|------|------|--------|------|------|
| i_bConvSeparateTimeout[1..4] | BOOL[1..4] | FALSE | L1~L4分料超时 | FB_1002×4 |
| i_bConvSensorFaultBlockUp[1..4] | BOOL[1..4] | FALSE | 阻挡上位冗余不一致 | FB_1002×4 |
| i_bConvSensorFaultBlockDown[1..4] | BOOL[1..4] | FALSE | 阻挡下位冗余不一致 | FB_1002×4 |
| i_bConvSensorFaultSepUp[1..4] | BOOL[1..4] | FALSE | 分料上位冗余不一致 | FB_1002×4 |
| i_bConvSensorFaultSepDown[1..4] | BOOL[1..4] | FALSE | 分料下位冗余不一致 | FB_1002×4 |

#### 2.3 取放料报警

| 名称 | 类型 | 说明 | 来源 |
|------|------|------|------|
| i_bPickClampTimeout | BOOL | 夹紧确认超时 | FB_1003 |
| i_bPickLiftTimeout | BOOL | 升降动作超时 | FB_1003 |
| i_bPickProductMissing | BOOL | 4光电未全检到 | FB_1003 |
| i_bPickSensorFault | BOOL | 夹紧/升降传感器冗余不一致 | FB_1003 |
| i_bPickFrameOnPlatform | BOOL | 取料平台有边框(F80) | FB_1003 |
| i_bPickX1Limit | BOOL | X1轴限位 | FB_1003 |
| i_bPickZLimit | BOOL | Z轴限位 | FB_1003 |

#### 2.4 送料报警

| 名称 | 类型 | 说明 | 来源 |
|------|------|------|------|
| i_bFeedX2Limit | BOOL | X2轴限位 | FB_1004 |
| i_bFeedMoveTimeout | BOOL | X2移动超时 | FB_1004 |
| i_bFeedFrameOnPlatform | BOOL | 送料平台有边框(F81) | FB_1004 |

### A.3 VAR_OUTPUT（旧）

#### 3.1 汇总输出

| 名称 | 类型 | 默认值 | 说明 | 去向 |
|------|------|--------|------|------|
| q_wCurrentAlarmCode | WORD | 16#0000 | 当前最高优先级报警码 | OB1→HMI(D120) |
| q_wGlobalAlarmWord | WORD | 16#0000 | 全局报警字(报警码值) | OB1→HMI(D400) |
| q_iAlarmCount | INT | 0 | MES累计报警次数 | OB1→HMI(D404) |
| q_aMesQueue[0..9] | INT[0..9] | 0 | MES去重报警队列(10条) | OB1→HMI(D406~D425) |
| q_bNewAlarmPulse | BOOL | FALSE | 新报警脉冲(蜂鸣器触发) | OB1 |

#### 3.2 指示灯

| 名称 | 类型 | 默认值 | 说明 | 去向 |
|------|------|--------|------|------|
| q_bLightGreen | BOOL | FALSE | 绿灯(Y24):自动运行+无故障 | OB1→IO |
| q_bLightRed | BOOL | FALSE | 红灯(Y25):任何故障 | OB1→IO |
| q_bLightYellow | BOOL | FALSE | 黄灯(Y26):暂停/等待/回原点中 | OB1→IO |
| q_bBuzzer | BOOL | FALSE | 蜂鸣器(Y27):新报警脉冲 | OB1→IO |
| q_bResetLight | BOOL | FALSE | 复位按钮灯(Y50) | OB1→IO |

