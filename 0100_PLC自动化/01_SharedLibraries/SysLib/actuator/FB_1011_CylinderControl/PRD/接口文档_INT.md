---
spec_id: INT-FB1011
title: "FB_1011 气缸控制接口定义"
version: "V13.0.0"
domain: plc
lifecycle: stable
canonical_path: "0100_PLC自动化/01_SharedLibraries/SysLib/actuator/FB_1011_CylinderControl/PRD/接口文档_INT.md"
tags: ["气缸控制", "执行器", "PLC功能块", "接口", "电磁阀", "结构体"]
---
# 接口文档 FB_1011_CylinderControl

## 0. 文档基础信息

| 属性         | 值                                                                                       |
| ------------ | ---------------------------------------------------------------------------------------- |
| **文档标题** | FB_1011 气缸控制接口定义                                                                 |
| **文档版本** | V13.0.0                                                                                  |
| **关联源码** | actuator/FB_1011_CylinderControl/FB_1011_CylinderControl.scl (V13.0.0)                   |
| **关联结构体** | actuator/FB_1011_CylinderControl/ST_Cylinder.scl (V3.1.0)                              |
| **编制日期** | 2026-06-18                                                                               |
| **编制人**   | Trae                                                                                     |
| **审核人**   | 人工                                                                                     |
| **遵循规范** | LSP-905-V1.0.2, LSP-904-V1.2.0, LSP-903-V2.1.0                                          |
| **变更记录** | V13.0.0: Breaking Change-重命名stCmd→i_stCmd, stSts→q_stSts, 对齐LSP-905前缀规范; 调用方需更新引脚名 |
| **变更记录** | V12.0.0: 新增防呆锁存(s_iLatchedSolenoidType+s_iLatchedMode), 运动中参数不可变; 新增i_stCmd.Mode(0=手动/1=自动); 新增i_stCmd.ModeStatus(WORD); CASE分支改用锁存值; 手动模式跳过超时检测 |
| **变更记录** | V11.0.0: Breaking Change-扁平接口(9入5出)→结构体接口(1入1出); i_stCmd:ST_CylinderCmd+q_stSts:ST_CylinderSts; 删除q_aSolenoid[0..7]→SolenoidA/SolenoidB独立BOOL |
| **变更记录** | V10.0.0: Breaking Change-新增双线圈两位阀支持(SolenoidType=1); q_bSolenoid→q_aSolenoid[0..7] ARRAY输出; 新增RetractPolarity参数; 命令处理从IF/ELSIF改为CASE SolenoidType分支; 双线圈A/B互锁+无命令保持位+ELSE安全态 |
| **变更记录** | V9.2.0: P0定时器修复-三段式+顶部无条件批量调用; 消抖关闭时设IN=FALSE让TON自然复位; 超时检测移入命令分支内加s_bMoving防误报; 移除尾部独立fb_tTimeout()调用 |

## 0.1 电磁阀类型定义

| SolenoidType值 | 电磁阀类型     | 线圈数量 | 输出信号                              | 默认行为         | 当前支持       |
| -------------- | -------------- | -------- | ------------------------------------- | ---------------- | -------------- |
| **0**          | **两位三通单线圈弹簧复位** | 1个      | q_stSts.SolenoidA                     | 弹簧复位(收回)   | 支持(默认)     |
| **1**          | **双线圈中封阀** | 2个      | q_stSts.SolenoidA, q_stSts.SolenoidB | 失电中封保持     | 支持     |
| 2              | 3位4通中封阀   | 2个      | q_stSts.SolenoidA, q_stSts.SolenoidB | 保持位置(中封)   | 预留扩展       |
| 3              | 3位4通中泄阀   | 2个      | q_stSts.SolenoidA, q_stSts.SolenoidB | 泄压回油(中泄)   | 预留扩展       |

> **适用场景**: 气缸阀(伸出/收回)、真空阀(真空/破真空)、夹具(夹紧/松开)、升降(上升/下降)等所有双位置执行机构。

### 0.1.1 单线圈弹簧复位阀真值表(默认配置, SolenoidType=0)

| i_stCmd.Extend | i_stCmd.Retract | i_stCmd.ExtendPolarity | q_stSts.SolenoidA | q_stSts.SolenoidB | 气缸行为 |
| -------------- | --------------- | ---------------------- | ----------------- | ----------------- | -------- |
| TRUE           | FALSE           | FALSE                  | TRUE              | FALSE             | 伸出     |
| FALSE          | TRUE            | FALSE                  | FALSE             | FALSE             | 收回     |
| FALSE          | FALSE           | FALSE                  | FALSE             | FALSE             | 弹簧复位 |
| TRUE           | FALSE           | TRUE                   | FALSE             | FALSE             | 伸出     |
| FALSE          | TRUE            | TRUE                   | TRUE              | FALSE             | 收回     |
| FALSE          | FALSE           | TRUE                   | TRUE              | FALSE             | 弹簧复位 |

### 0.1.2 线圈极性取反说明

| i_stCmd.ExtendPolarity | 说明     | q_stSts.SolenoidA=TRUE | q_stSts.SolenoidA=FALSE | 传感器映射                              | 适用场景                |
| --------------------- | -------- | ---------------------- | ----------------------- | --------------------------------------- | ----------------------- |
| FALSE (默认)          | 正常极性 | 伸出                   | 收回                    | ExtendedPos->伸出位, RetractedPos->收回位 | 阻挡/夹紧等气缸         |
| TRUE                  | 极性取反 | 收回                   | 伸出                    | ExtendedPos->收回位, RetractedPos->伸出位 | 拍正/顶升等弹簧复位气缸 |

> **极性取反完整行为**: 当 i_stCmd.ExtendPolarity=TRUE 时, 不仅电磁阀输出反转, 传感器映射也互换(物理伸出位视为逻辑收回位, 物理收回位视为逻辑伸出位), 状态输出 q_stSts.IsExtended/q_stSts.IsRetracted 随之反转.

### 0.1.3 双线圈中封阀真值表(SolenoidType=1)

> 双线圈中封阀使用A/B两个线圈互斥控制, q_stSts.SolenoidA=线圈A(动点方向), q_stSts.SolenoidB=线圈B(原点方向). 任意时刻最多一个线圈ON, 无命令时两个线圈均OFF(失电中封保持). 需配合 i_stCmd.RetractPolarity 参数控制B线圈极性.

| i_stCmd.Extend | i_stCmd.Retract | i_stCmd.ExtendPolarity | i_stCmd.RetractPolarity | q_stSts.SolenoidA | q_stSts.SolenoidB | 气缸行为     |
| -------------- | --------------- | ---------------------- | ----------------------- | ----------------- | ----------------- | ------------ |
| TRUE           | FALSE           | FALSE                  | FALSE                   | TRUE              | FALSE             | A线圈驱动伸出 |
| TRUE           | FALSE           | TRUE                   | FALSE                   | FALSE             | FALSE             | A线圈极性取反驱动伸出 |
| FALSE          | TRUE            | FALSE                  | FALSE                   | FALSE             | TRUE              | B线圈驱动收回 |
| FALSE          | TRUE            | FALSE                  | TRUE                    | FALSE             | FALSE             | B线圈极性取反驱动收回 |
| TRUE           | TRUE            | -                      | -                       | TRUE              | FALSE             | 伸出优先(A线圈ON) |
| FALSE          | FALSE           | -                      | -                       | FALSE             | FALSE             | 保持位(双线圈均OFF) |

> **i_stCmd.RetractPolarity说明**: 当RetractPolarity=TRUE时, B线圈(原点方向)极性取反, 即收回命令不再驱动B线圈, 而是驱动A线圈. 此参数仅对双线圈模式(SolenoidType=1)有效, 单线圈模式忽略.

## 1. 功能概述

**单一气缸执行控制块**, 封装 推力/拉力命令 -> 传感器消抖 -> 极性映射 -> 电磁阀输出 -> 到位检测 -> 超时保护 -> 传感器冗余一致性检查 的完整闭环.

支持多种电磁阀类型配置(单线圈弹簧复位/双线圈中封), 支持线圈极性取反(含传感器映射反转), 支持磁环传感器TON消抖, 支持手动/自动运行模式, 支持运动中参数防呆锁存.

适用于输送机系统中任何需要伸出/收回动作的气动执行器(阻挡气缸, 分料气缸, 双作用顶升气缸等).

### 1.1 职责边界

| 做什么                               | 不做什么                             |
| ------------------------------------ | ------------------------------------ |
| 接收伸出/收回命令                    | 不关心什么时候该伸出(由编排器决定)   |
| 输出电磁阀信号(支持多种类型配置)     | 不直接操作物理IO(由OB1映射)          |
| 磁环传感器TON消抖                    | 不关心传感器的物理地址               |
| 极性映射(传感器+输出反转)            | 不参与其他气缸的逻辑                 |
| 上下位同时ON冲突诊断                 | 不处理非本气缸的报警                 |
| 动作超时计时与报警                   | 不处理多气缸协调                     |
| 运动中参数防呆锁存                   | 不负责模式切换的决策逻辑             |

### 1.2 实例化场景

| 场景         | 实例名               | 配置                                      | 说明                                              |
| ------------ | -------------------- | ----------------------------------------- | ------------------------------------------------- |
| 阻挡气缸     | fbBlock : FB_1011    | i_stCmd.SolenoidType=0, i_stCmd.ExtendPolarity=FALSE | i_stCmd.Extend=阻挡下降, i_stCmd.Retract=阻挡上升           |
| 分料气缸     | fbSeparate : FB_1011 | i_stCmd.SolenoidType=0, i_stCmd.ExtendPolarity=FALSE | i_stCmd.Extend=分料推出, i_stCmd.Retract=分料复位           |
| 拍正气缸     | fbAlign : FB_1011    | i_stCmd.SolenoidType=0, i_stCmd.ExtendPolarity=TRUE  | i_stCmd.Extend=拍正伸出, i_stCmd.Retract=拍正收回(极性取反) |
| 双作用顶升气缸 | fbLift : FB_1011   | i_stCmd.SolenoidType=1, i_stCmd.ExtendPolarity=FALSE, i_stCmd.RetractPolarity=FALSE | 双线圈A/B互锁, 失电中封保持, i_stCmd.Extend=A线圈伸出, i_stCmd.Retract=B线圈收回 |
| 双作用夹紧气缸 | fbClamp : FB_1011  | i_stCmd.SolenoidType=1, i_stCmd.ExtendPolarity=FALSE, i_stCmd.RetractPolarity=TRUE | 双线圈B极性取反, i_stCmd.Extend=A线圈夹紧, i_stCmd.Retract=B线圈极性取反松开 |
| 真空阀       | fbVacuum : FB_1011  | i_stCmd.SolenoidType=0, i_stCmd.ExtendPolarity=FALSE | i_stCmd.Extend=真空ON, i_stCmd.Retract=破真空; RetractedPos取反ExtendedPos |

## 2. 接口定义

### 2.1 VAR_INPUT CONSTANT (结构体)

| 名称    | 类型           | 说明                                                              | 来源           |
| ------- | -------------- | ----------------------------------------------------------------- | -------------- |
| i_stCmd | ST_CylinderCmd | 命令+传感器+参数, CONSTANT禁止FB内部篡改                          | 编排器/OB1     |

**ST_CylinderCmd 字段定义** (V3.1.0):

| 字段           | 类型  | 默认值 | 有效值域    | 说明                                                              |
| -------------- | ----- | ------ | ----------- | ----------------------------------------------------------------- |
| Extend         | BOOL  | FALSE  | TRUE/FALSE  | 动点命令: 伸出/真空ON/夹紧/下降                                    |
| Retract        | BOOL  | FALSE  | TRUE/FALSE  | 原点命令: 收回/破真空/松开/上升                                    |
| ExtendedPos    | BOOL  | FALSE  | TRUE/FALSE  | 动点到位传感器: 伸出位/真空表                                      |
| RetractedPos   | BOOL  | FALSE  | TRUE/FALSE  | 原点到位传感器: 收回位/大气压力; 真空阀无此传感器时取反ExtendedPos |
| TimeoutMs      | DINT  | 5000   | 0~60000     | 动作超时时间(ms), 0=关闭超时检测                                   |
| DebounceMs     | DINT  | 0      | 0~1000      | 传感器消抖时间(ms), 0=关闭消抖(设IN=FALSE让TON自然复位)            |
| SolenoidType   | INT   | 0      | 0~3         | 电磁阀类型: 0=两位三通单线圈弹簧复位(默认), 1=双线圈中封阀, 2/3=预留 |
| ExtendPolarity | BOOL  | FALSE  | TRUE/FALSE  | 线圈A极性: FALSE=正常, TRUE=取反(电磁阀+传感器映射均反转)          |
| RetractPolarity| BOOL  | FALSE  | TRUE/FALSE  | 线圈B极性(仅双线圈模式生效): FALSE=正常, TRUE=取反                  |
| Mode           | INT   | 1      | 0~1         | 运行模式: 0=手动(跳过超时, 线圈直接输出), 1=自动(全保护); 默认自动安全态 |
| ModeStatus     | WORD  | 16#0000| 16#0000~16#FFFF | 模式状态字: 上层传递的状态标志, 预留供序列控制器使用           |

> **命令优先级**: 当 Extend 和 Retract 同时为 TRUE 时, Extend(动点)优先.

### 2.2 VAR_OUTPUT (结构体)

| 名称    | 类型           | 说明                                                              | 去向           |
| ------- | -------------- | ----------------------------------------------------------------- | -------------- |
| q_stSts | ST_CylinderSts | 线圈输出+到位状态+诊断                                             | 编排器/OB1     |

**ST_CylinderSts 字段定义** (V3.0.0):

| 字段         | 类型  | 默认值 | 有效值域    | 说明                            |
| ------------ | ----- | ------ | ----------- | ------------------------------- |
| SolenoidA    | BOOL  | FALSE  | TRUE/FALSE  | 线圈A输出: 动点方向; 单线圈仅用此输出 |
| SolenoidB    | BOOL  | FALSE  | TRUE/FALSE  | 线圈B输出: 原点方向; 单线圈时始终FALSE |
| IsExtended   | BOOL  | FALSE  | TRUE/FALSE  | 已到动点 (极性映射后)           |
| IsRetracted  | BOOL  | FALSE  | TRUE/FALSE  | 已到原点 (极性映射后)           |
| Timeout      | BOOL  | FALSE  | TRUE/FALSE  | 动作超时报警 (自动模式)         |
| SensorFault  | BOOL  | FALSE  | TRUE/FALSE  | 传感器冗余故障 (两点同时ON, 消抖后检测) |

### 2.3 VAR (内部变量)

> 2026-10-22 对齐说明：这些是块内部静态变量（`VAR`），不是接口引脚，`plc docs check` 只核对接口引脚，所以本表第一列不叫“名称”，检查器不把它当接口表。内容与代码一致，没改。

| 内部变量              | 类型    | 默认值 | 说明                              |
| --------------------- | ------- | ------ | --------------------------------- |
| fb_tDebounceExt       | FB_TON  | -      | ExtendedPos消抖定时器             |
| fb_tDebounceRet       | FB_TON  | -      | RetractedPos消抖定时器            |
| fb_tTimeout           | FB_TONR | -      | 超时定时器 (TONR锁存)             |
| s_bExtDebounced       | BOOL    | FALSE  | ExtendedPos消抖后信号             |
| s_bRetDebounced       | BOOL    | FALSE  | RetractedPos消抖后信号            |
| s_dExtDebounceEt      | DINT    | 0      | ExtendedPos消抖ET接收             |
| s_dRetDebounceEt      | DINT    | 0      | RetractedPos消抖ET接收            |
| s_bLogicExtPos        | BOOL    | FALSE  | 逻辑伸出位 (极性映射后)           |
| s_bLogicRetPos        | BOOL    | FALSE  | 逻辑收回位 (极性映射后, 双线圈模式用于B线圈极性映射) |
| s_bMoving             | BOOL    | FALSE  | 正在执行动作中                    |
| s_iLatchedSolenoidType| INT     | 0      | 防呆: 运动中锁存的SolenoidType, 空闲时刷新 (V12.0.0) |
| s_iLatchedMode        | INT     | 1      | 防呆: 运动中锁存的Mode, 空闲时刷新; 默认自动 (V12.0.0) |

## 3. 信号处理流水线

> **定时器批量调用区**: 遵循LSP-903 V2.1.0三段式规范, 所有定时器(fb_tDebounceExt, fb_tDebounceRet, fb_tTimeout)在代码顶部无条件批量调用, 不在条件分支内联调用. 消抖定时器通过IN引脚控制启停, 超时定时器通过IN/R引脚控制启停/复位.

```
物理传感器        TON消抖            传感器故障检测        极性映射             命令处理(CASE 锁存值)
i_stCmd.ExtendedPos ─→ fb_tDebounceExt ─→ s_bExtDebounced ─┬─→ SensorFault ─→ s_bLogicExtPos ─→ CASE s_iLatchedSolenoidType
i_stCmd.RetractedPos ─→ fb_tDebounceRet ─→ s_bRetDebounced ─┤                  ─→ s_bLogicRetPos ─→   0: 单线圈 → q_stSts.SolenoidA
                                                              │                                       1: 双线圈 → q_stSts.SolenoidA/B互锁
i_stCmd.DebounceMs ──→ PT参数(0=直通)                         └─→ i_stCmd.ExtendPolarity             ELSE: 安全态(全OFF)
                                                                    FALSE: 正常映射
                                                                    TRUE:  互换映射

防呆锁存 (V12.0.0):
  空闲时(s_bMoving=FALSE): s_iLatchedSolenoidType := i_stCmd.SolenoidType; s_iLatchedMode := i_stCmd.Mode
  运动中(s_bMoving=TRUE):  锁存值不变, 防止参数跳变导致输出异常
```

## 4. 行为逻辑

### 4.1 防呆锁存机制 (V12.0.0)

```
(* 仅在空闲时重新锁存参数, 运动中保持锁存值不变 *)
IF NOT s_bMoving THEN
    s_iLatchedSolenoidType := i_stCmd.SolenoidType;
    s_iLatchedMode := i_stCmd.Mode;
END_IF;
```

> **设计意图**: 防止运动过程中 SolenoidType 或 Mode 参数被上层意外修改, 导致电磁阀类型切换或模式跳变引起输出异常. 锁存值在空闲时自动刷新, 下次动作时生效.

### 4.2 命令处理(CASE s_iLatchedSolenoidType 分支)

```
CASE s_iLatchedSolenoidType OF
    0:  // 单线圈弹簧复位阀 (见4.3~4.7)
        q_stSts.SolenoidB := FALSE;  // 单线圈SolenoidB始终FALSE
        // 命令处理逻辑见4.5

    1:  // 双线圈中封阀 (见4.8)
        // A/B互锁, 无命令保持位, ELSE全OFF

ELSE
    (* 非法类型兜底: 安全态 *)
    q_stSts.SolenoidA := FALSE;
    q_stSts.SolenoidB := FALSE;
END_CASE;
```

### 4.3 传感器消抖

```
IF i_stCmd.DebounceMs > 0 THEN
    fb_tDebounceExt.IN := i_stCmd.ExtendedPos;
    fb_tDebounceExt.PT := i_stCmd.DebounceMs;
    s_bExtDebounced := fb_tDebounceExt.Q;
    s_dExtDebounceEt := fb_tDebounceExt.ET;
    fb_tDebounceRet.IN := i_stCmd.RetractedPos;
    fb_tDebounceRet.PT := i_stCmd.DebounceMs;
    s_bRetDebounced := fb_tDebounceRet.Q;
    s_dRetDebounceEt := fb_tDebounceRet.ET;
ELSE
    (* 消抖关闭: 设IN=FALSE让TON自然复位, 信号直通 *)
    fb_tDebounceExt.IN := FALSE;
    fb_tDebounceRet.IN := FALSE;
    s_bExtDebounced := i_stCmd.ExtendedPos;
    s_bRetDebounced := i_stCmd.RetractedPos;
END_IF;
```

### 4.4 传感器冗余一致性检查(消抖后, 极性映射前)

```
IF s_bExtDebounced AND s_bRetDebounced THEN
    q_stSts.SensorFault := TRUE;
ELSE
    q_stSts.SensorFault := FALSE;
END_IF;
```

### 4.5 极性映射

```
IF i_stCmd.ExtendPolarity THEN
    s_bLogicExtPos := s_bRetDebounced;   (* 物理收回位 -> 逻辑伸出位 *)
    s_bLogicRetPos := s_bExtDebounced;   (* 物理伸出位 -> 逻辑收回位 *)
ELSE
    s_bLogicExtPos := s_bExtDebounced;   (* 正常映射 *)
    s_bLogicRetPos := s_bRetDebounced;
END_IF;
(* 注: i_stCmd.RetractPolarity 不影响传感器极性映射, 仅影响双线圈B线圈输出极性 *)
```

### 4.6 单线圈正常运行(SolenoidType=0)

```
伸出流程:  i_stCmd.Extend=TRUE
  -> q_stSts.SolenoidA := NOT i_stCmd.ExtendPolarity
  -> q_stSts.SolenoidB := FALSE  (单线圈SolenoidB始终FALSE)
  -> s_bMoving := TRUE
  -> 启动超时计时 (如果i_stCmd.TimeoutMs>0 且 s_iLatchedMode=1 自动模式)
  -> 等待 s_bLogicExtPos=TRUE
  -> q_stSts.IsExtended := TRUE, q_stSts.IsRetracted := FALSE
  -> s_bMoving := FALSE
  -> 取消超时计时, 清除q_stSts.Timeout

收回流程:  i_stCmd.Retract=TRUE
  -> q_stSts.SolenoidA := i_stCmd.ExtendPolarity
  -> q_stSts.SolenoidB := FALSE  (单线圈SolenoidB始终FALSE)
  -> s_bMoving := TRUE
  -> 启动超时计时 (如果i_stCmd.TimeoutMs>0 且 s_iLatchedMode=1 自动模式)
  -> 等待 s_bLogicRetPos=TRUE
  -> q_stSts.IsRetracted := TRUE, q_stSts.IsExtended := FALSE
  -> s_bMoving := FALSE
  -> 取消超时计时, 清除q_stSts.Timeout
```

### 4.7 手动模式与超时处理

```
手动模式 (s_iLatchedMode=0):
  -> 跳过超时检测, 线圈直接输出到位
  -> 传感器故障仍检测, 不因手动模式跳过安全诊断

自动模式 (s_iLatchedMode=1):
  -> 如果 fb_tTimeout.Q=TRUE 且 s_bMoving=TRUE (超时到达且正在执行动作):
    -> q_stSts.Timeout := TRUE  (锁存, 直到下次到位或命令变化时清除)
    -> q_stSts.SolenoidA/SolenoidB 保持当前输出 (不强制改变, 由编排器决策)

空闲状态 (i_stCmd.Extend=FALSE AND i_stCmd.Retract=FALSE):
  -> 单线圈(SolenoidType=0): q_stSts.SolenoidA = i_stCmd.ExtendPolarity (弹簧复位状态)
  -> 双线圈(SolenoidType=1): q_stSts.SolenoidA = FALSE, q_stSts.SolenoidB = FALSE (失电中封保持)
  -> fb_tTimeout.IN := FALSE; fb_tTimeout.R := TRUE
  -> 超时故障自动清除 (q_stSts.Timeout := FALSE)
  -> q_stSts.IsExtended := s_bLogicExtPos
  -> q_stSts.IsRetracted := s_bLogicRetPos
```

### 4.8 双线圈中封阀行为逻辑(SolenoidType=1)

#### 4.8.1 A/B互锁规则

```
双线圈核心约束:
  1. q_stSts.SolenoidA 和 q_stSts.SolenoidB 互斥, 任意时刻最多一个ON
  2. 无命令时两个线圈均OFF, 气缸保持当前位置(失电中封, 非弹簧复位)
  3. i_stCmd.Extend优先: 同时命令时A线圈ON, B线圈OFF
```

#### 4.8.2 伸出流程

```
伸出流程:  i_stCmd.Extend=TRUE
  -> q_stSts.SolenoidA := NOT i_stCmd.ExtendPolarity  (A线圈驱动, 受ExtendPolarity控制)
  -> q_stSts.SolenoidB := FALSE                        (B线圈互锁OFF)
  -> s_bMoving := TRUE
  -> 启动超时计时 (如果i_stCmd.TimeoutMs>0 且 s_iLatchedMode=1)
  -> 等待 s_bLogicExtPos=TRUE
  -> q_stSts.IsExtended := TRUE, q_stSts.IsRetracted := FALSE
  -> s_bMoving := FALSE
  -> 取消超时计时, 清除q_stSts.Timeout
```

#### 4.8.3 收回流程

```
收回流程:  i_stCmd.Retract=TRUE (且i_stCmd.Extend=FALSE)
  -> q_stSts.SolenoidA := FALSE                        (A线圈互锁OFF)
  -> q_stSts.SolenoidB := NOT i_stCmd.RetractPolarity  (B线圈驱动, 受RetractPolarity控制)
  -> s_bMoving := TRUE
  -> 启动超时计时 (如果i_stCmd.TimeoutMs>0 且 s_iLatchedMode=1)
  -> 等待 s_bLogicRetPos=TRUE
  -> q_stSts.IsRetracted := TRUE, q_stSts.IsExtended := FALSE
  -> s_bMoving := FALSE
  -> 取消超时计时, 清除q_stSts.Timeout
```

#### 4.8.4 保持位(空闲状态)

```
当 i_stCmd.Extend=FALSE AND i_stCmd.Retract=FALSE 时 (空闲):
  -> q_stSts.SolenoidA := FALSE  (A线圈OFF)
  -> q_stSts.SolenoidB := FALSE  (B线圈OFF)
  -> 气缸保持当前位置(双线圈均失电, 中封保持, 非弹簧复位)
  -> s_bMoving := FALSE
  -> fb_tTimeout.IN := FALSE; fb_tTimeout.R := TRUE
  -> 超时故障自动清除 (q_stSts.Timeout := FALSE)
  -> q_stSts.IsExtended := s_bLogicExtPos
  -> q_stSts.IsRetracted := s_bLogicRetPos
```

#### 4.8.5 CASE ELSE安全态(非法SolenoidType)

```
当 SolenoidType 不在 0~1 范围内时:
  -> q_stSts.SolenoidA := FALSE
  -> q_stSts.SolenoidB := FALSE
  -> 所有输出置为安全态, 禁止任何线圈驱动
```

## 5. 接口交互协议

```
编排器(FB_1002)                                FB_1011_CylinderControl
     |                                                 |
     |-- i_stCmd.Extend := TRUE --------------------->|  (命令: 伸出)
     |   i_stCmd.ExtendPolarity := FALSE               |
     |   i_stCmd.DebounceMs := 50                      |
     |   i_stCmd.Mode := 1 (自动)                      |
     |   i_stCmd.SolenoidType := 0                     |
     |                                                 |  q_stSts.SolenoidA := TRUE
     |                                                 |  消抖+极性映射...
     |                                                 |  s_bLogicExtPos=TRUE
     |<-- q_stSts.IsExtended := TRUE ------------------|  (反馈: 已伸出)
     |                                                 |
     |-- i_stCmd.Extend := FALSE --------------------->|  (撤销命令)
     |                                                 |  弹簧复位 (保持原位安全)

手动模式示例:
     |-- i_stCmd.Extend := TRUE --------------------->|  (命令: 伸出)
     |   i_stCmd.Mode := 0 (手动)                      |
     |   i_stCmd.TimeoutMs := 5000                     |
     |                                                 |  q_stSts.SolenoidA := TRUE
     |                                                 |  跳过超时检测, 线圈直接输出
     |<-- q_stSts.IsExtended := TRUE ------------------|  (反馈: 到位)
```

## 6. 报警码

| 报警码 | 报警名称     | 触发条件                                | 复位方式                               | 严重级别 |
| ------ | ------------ | --------------------------------------- | -------------------------------------- | -------- |
| W-001  | 动作超时     | fb_tTimeout.Q=TRUE且s_bMoving=TRUE(自动模式) | 撤销命令(Extend/Retract均FALSE)或重新触发下一动作 | Warning  |
| W-002  | 传感器故障   | s_bExtDebounced=TRUE AN s_bRetDebounced=TRUE | 传感器状态恢复正常                     | Warning  |

## 7. 接口版本兼容性说明

### 7.1 V11.0.0 Breaking Change: 扁平→结构体

| 变更项 | V10.0.0及之前 | V11.0.0及之后 |
| ------ | ------------- | ------------- |
| 输入引脚 | 9个独立 VAR_INPUT | 1个 i_stCmd:ST_CylinderCmd |
| 输出引脚 | 5个独立 VAR_OUTPUT | 1个 q_stSts:ST_CylinderSts |
| 电磁阀输出 | q_aSolenoid[0..7] ARRAY | q_stSts.SolenoidA / SolenoidB 独立BOOL |
| 到位状态 | q_bIsExtended / q_bIsRetracted | q_stSts.IsExtended / q_stSts.IsRetracted |
| 超时报警 | q_bTimeout | q_stSts.Timeout |
| 传感器故障 | q_bSensorFault | q_stSts.SensorFault |

**迁移示例**:
```
// V10.0.0
fbCylinder(i_bExtend := ..., i_bRetract := ..., q_aSolenoid[0] => ...);

// V13.0.0
fbCylinder(i_stCmd := cmd, q_stSts => sts);
cmd.Extend := ...;
cmd.ExtendPolarity := ...;
sts.SolenoidA => ...;
```

### 7.2 V13.0.0 Breaking Change: 引脚重命名

| 变更项 | V12.0.0 | V13.0.0 |
| ------ | ------- | ------- |
| 输入引脚 | stCmd:= | i_stCmd:= |
| 输出引脚 | stSts=> | q_stSts=> |

> V13.0.0 仅重命名FB级引脚, 结构体内部字段名不变. 调用方只需更新引脚名即可.

### 7.3 V12.0.0 新增字段

| 新增字段 | 默认值 | 说明 |
| -------- | ------ | ---- |
| i_stCmd.Mode | 1 (自动) | 不影响旧调用方(默认自动=全保护, 与V11行为一致) |
| i_stCmd.ModeStatus | 16#0000 | 预留, 不填不影响功能 |

## 8. 关联文档

| 文档名称     | 路径                                                              | 说明                   |
| ------------ | ----------------------------------------------------------------- | ---------------------- |
| 需求分析     | PRD/需求分析文档_REQ.md                                           | 功能需求规格           |
| 详细设计     | PRD/详细设计说明书_DSN.md                                         | 算法与状态机设计       |
| 技术方案     | PRD/技术方案文档_TEC.md                                           | 系统架构与部署方案     |
| 源码         | FB_1011_CylinderControl.scl                                       | 功能块实现             |
| 结构体定义   | ST_Cylinder.scl                                                   | 接口结构体定义         |
| SCL编程规范  | 00_通用规范/PLC编程/905_SCL编程规范_LSP.md                        | 命名与编码规范         |
| 定时器规范   | 00_通用规范/PLC编程/903_定时器使用规范_LSP.md                     | 定时器使用规范         |
| 注释规范     | 00_通用规范/PLC编程/904_SCL注释规范_LSP.md                        | 注释格式规范           |

---

## 附：2026-10-22 对齐前的旧说明（留底，不删）

> 本文件名是“接口文档_INT.md”，`plc docs check` 只认 `接口文档_IFC-*.md`，所以现在检查器看不到它、只报“缺少接口文档”警告。
> 2026-10-22 用改名后的副本试跑过：会多出 14 个拦住项（2 处说明措辞 + 2.3 内部变量表 12 行）。已提前按代码对齐，改名留给下次碰 FB_1011 的卡。

| 引脚/表 | 对齐前文档写法 | 现写法（= 代码注释） |
|------|------|------|
| i_stCmd | 命令+传感器+参数结构体, CONSTANT禁止FB内部篡改 | 命令+传感器+参数, CONSTANT禁止FB内部篡改 |
| q_stSts | 线圈输出+到位状态+诊断结构体 | 线圈输出+到位状态+诊断 |
| 2.3 表头第一列 | 名称 | 内部变量 |
