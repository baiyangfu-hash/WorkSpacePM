# 接口文档 FB_2001_CommonAlarm_AllStation

## 0. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | FB_2001 公共报警接口定义 |
| **文档版本** | V9.1.0 |
| **关联源码** | 05_公共报警/FB_2001_CommonAlarm_AllStation.scl |
| **编制日期** | 2026-05-17 |
| **编制人** | Trae |
| **遵循规范** | LSP-905 |
| **数据来源** | 源程序功能基线_SRC-DJ-2026-005-V1.0.0 |

## 1. 功能概述

汇总三工站所有报警源，计算全局报警字，管理MES去重队列(10条)，输出指示灯/蜂鸣器控制，产生新报警脉冲。

## 2. VAR_INPUT - 各工站报警信号

### 2.1 系统/安全报警

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

### 2.2 输送机报警

| 名称 | 类型 | 默认值 | 说明 | 来源 |
|------|------|--------|------|------|
| i_bConvSeparateTimeout[1..4] | BOOL[1..4] | FALSE | L1~L4分料超时 | FB_1002×4 |
| i_bConvSensorFaultBlockUp[1..4] | BOOL[1..4] | FALSE | 阻挡上位冗余不一致 | FB_1002×4 |
| i_bConvSensorFaultBlockDown[1..4] | BOOL[1..4] | FALSE | 阻挡下位冗余不一致 | FB_1002×4 |
| i_bConvSensorFaultSepUp[1..4] | BOOL[1..4] | FALSE | 分料上位冗余不一致 | FB_1002×4 |
| i_bConvSensorFaultSepDown[1..4] | BOOL[1..4] | FALSE | 分料下位冗余不一致 | FB_1002×4 |

### 2.3 取放料报警

| 名称 | 类型 | 说明 | 来源 |
|------|------|------|------|
| i_bPickClampTimeout | BOOL | 夹紧确认超时 | FB_1003 |
| i_bPickLiftTimeout | BOOL | 升降动作超时 | FB_1003 |
| i_bPickProductMissing | BOOL | 4光电未全检到 | FB_1003 |
| i_bPickSensorFault | BOOL | 夹紧/升降传感器冗余不一致 | FB_1003 |
| i_bPickFrameOnPlatform | BOOL | 取料平台有边框(F80) | FB_1003 |
| i_bPickX1Limit | BOOL | X1轴限位 | FB_1003 |
| i_bPickZLimit | BOOL | Z轴限位 | FB_1003 |

### 2.4 送料报警

| 名称 | 类型 | 说明 | 来源 |
|------|------|------|------|
| i_bFeedX2Limit | BOOL | X2轴限位 | FB_1004 |
| i_bFeedMoveTimeout | BOOL | X2移动超时 | FB_1004 |
| i_bFeedFrameOnPlatform | BOOL | 送料平台有边框(F81) | FB_1004 |

## 3. VAR_OUTPUT

### 3.1 汇总输出

| 名称 | 类型 | 默认值 | 说明 | 去向 |
|------|------|--------|------|------|
| q_wCurrentAlarmCode | WORD | 16#0000 | 当前最高优先级报警码 | OB1→HMI(D120) |
| q_wGlobalAlarmWord | WORD | 16#0000 | 全局报警字(报警码值) | OB1→HMI(D400) |
| q_iAlarmCount | INT | 0 | MES累计报警次数 | OB1→HMI(D404) |
| q_aMesQueue[0..9] | INT[0..9] | 0 | MES去重报警队列(10条) | OB1→HMI(D406~D425) |
| q_bNewAlarmPulse | BOOL | FALSE | 新报警脉冲(蜂鸣器触发) | OB1 |

### 3.2 指示灯

| 名称 | 类型 | 默认值 | 说明 | 去向 |
|------|------|--------|------|------|
| q_bLightGreen | BOOL | FALSE | 绿灯(Y24):自动运行+无故障 | OB1→IO |
| q_bLightRed | BOOL | FALSE | 红灯(Y25):任何故障 | OB1→IO |
| q_bLightYellow | BOOL | FALSE | 黄灯(Y26):暂停/等待/回原点中 | OB1→IO |
| q_bBuzzer | BOOL | FALSE | 蜂鸣器(Y27):新报警脉冲 | OB1→IO |
| q_bResetLight | BOOL | FALSE | 复位按钮灯(Y50) | OB1→IO |

## 4. 报警码完整表（按优先级）

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
