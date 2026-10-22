---
spec_id: IFC-FB1012
title: "FB_1012 输送电机控制接口定义"
version: "V9.0.0"
domain: plc
lifecycle: stable
canonical_path: "0100_PLC自动化/01_SharedLibraries/SysLib/actuator/FB_1012_ConveyorMotor/PRD/接口文档_IFC-FB1012-ConveyorMotor-V9.0.0.md"
tags: ["输送电机", "执行器", "PLC功能块", "接口", "变频器"]
---
# 接口文档 FB_1012_ConveyorMotor

## 0. 文档基础信息

| 属性         | 值                                                                                       |
| ------------ | ---------------------------------------------------------------------------------------- |
| **文档标题** | FB_1012 输送电机控制接口定义                                                             |
| **文档版本** | V9.0.0                                                                                   |
| **2026-10-22 对齐** | 接口表“说明”列按代码行尾注释逐字对齐（`plc docs check`），对齐前写法移到文末附录；只改文档，版本号和文件名不变 |
| **关联源码** | actuator/FB_1012_ConveyorMotor/FB_1012_ConveyorMotor.scl                                 |
| **编制日期** | 2026-05-30                                                                               |
| **编制人**   | Trae                                                                                     |
| **审核人**   | 人工                                                                                     |
| **遵循规范** | LSP-905-V1.0.2, LSP-904-V1.2.0, LSP-903-V1.0.0                                          |
| **变更记录** | V9.0.0: 移除ST_ConveyorMotor回归扁平接口; 取消安全门信号; 慢速改为方向修饰符; 新增控制模式预留 |

## 0.1 核心设计决策

| 决策                     | 理由                                                       |
| ------------------------ | ---------------------------------------------------------- |
| 取消安全门信号           | 执行器只负责执行和反馈执行结果, 安全互锁由编排器/上层处理   |
| 慢速是方向修饰符         | 慢速不能独立运行, 必须与方向命令(Fwd/Rev)组合才生效        |
| 端子控制为默认模式       | 当前VFD通过端子控制方向和速度段, 通讯控制预留               |
| 预留通讯控制模式         | i_iCtrlMode=1时启用i_rSpeed, 现阶段仅实现端子模式(i_iCtrlMode=0) |
| 注释使用中文             | LSP-904允许中文注释, 仅禁止中文标点                        |

## 1. 功能概述

**输送电机控制块**, 封装方向命令 -> VFD故障检测 -> 方向互斥 -> 慢速修饰 -> 实际输出的完整链路.

适用于通过变频器驱动的输送带电机, 支持正转/反转两种方向, 每种方向可选高速或慢速运行.

### 1.1 职责边界

| 做什么                               | 不做什么                                   |
| ------------------------------------ | ------------------------------------------ |
| 方向命令互斥 (Fwd优先于Rev)          | 不决定何时启动/停止 (编排器决定)           |
| 慢速修饰方向输出                     | 不处理安全互锁 (由编排器/上层处理)         |
| VFD故障检测与报警                    | 不处理VFD复位 (编排器决定)                 |
| 预留通讯控制模式接口                 | 不执行PID或速度闭环                        |

### 1.2 控制模式

| i_iCtrlMode | 模式     | 速度控制方式                     | 当前支持   |
| ----------- | -------- | -------------------------------- | ---------- |
| **0**       | **端子控制** | VFD端子接收Fwd/Rev/Slow数字信号 | 支持(默认) |
| 1           | 通讯控制 | i_rSpeed通过总线写入VFD          | 预留       |

## 2. 接口定义

### 2.1 VAR_INPUT

| 名称          | 类型 | 默认值  | 有效值域    | 说明                                                    | 来源           |
| ------------- | ---- | ------- | ----------- | ------------------------------------------------------- | -------------- |
| i_bFwdCmd     | BOOL | FALSE   | TRUE/FALSE  | 正转命令                                                | 编排器         |
| i_bRevCmd     | BOOL | FALSE   | TRUE/FALSE  | 反转命令                                                | 编排器         |
| i_bSlowCmd    | BOOL | FALSE   | TRUE/FALSE  | 慢速命令(方向修饰符, 必须与Fwd/Rev组合)              | 编排器         |
| i_bVfdFault   | BOOL | FALSE   | TRUE/FALSE  | 变频器故障输入                                          | OB1->IO映射    |
| i_iCtrlMode   | INT  | 0       | 0~1         | 控制模式: 0=端子控制, 1=通讯控制(预留)                | 编排器         |
| i_rSpeed      | REAL | 100.0   | 0.0~100.0   | 速度设定值(%, 通讯模式用, 端子模式无效)              | 编排器/HMI     |

> **命令优先级**: `i_bFwdCmd` > `i_bRevCmd`. 正转和反转同时为TRUE时, 正转优先.
>
> **慢速修饰规则**: `i_bSlowCmd`是方向命令的修饰符, 不能独立运行. 仅当方向命令(Fwd/Rev)有效时, SlowCmd才生效: 方向+慢速=慢速运行, 方向+无慢速=高速运行. SlowCmd单独为TRUE时无输出.

### 2.2 VAR_OUTPUT

| 名称         | 类型 | 默认值 | 有效值域    | 说明                          | 去向           |
| ------------ | ---- | ------ | ----------- | ----------------------------- | -------------- |
| q_bFwdOut    | BOOL | FALSE  | TRUE/FALSE  | 正转输出(经互锁后)            | OB1->IO映射    |
| q_bRevOut    | BOOL | FALSE  | TRUE/FALSE  | 反转输出(经互锁后)            | OB1->IO映射    |
| q_bSlowOut   | BOOL | FALSE  | TRUE/FALSE  | 慢速输出(经互锁后)            | OB1->IO映射    |
| q_bRunning   | BOOL | FALSE  | TRUE/FALSE  | 运行中                  | 编排器         |
| q_bVfdAlarm  | BOOL | FALSE  | TRUE/FALSE  | VFD报警                | 编排器->报警   |

## 3. 行为逻辑

### 3.1 互锁优先级

```
优先级从高到低:
1. VFD故障   -> 所有输出 := FALSE, q_bVfdAlarm := TRUE
2. 方向命令   -> Fwd > Rev (慢速修饰方向输出)
```

### 3.2 正常运转

```
i_bFwdCmd=TRUE, i_bSlowCmd=TRUE:
  -> q_bFwdOut := TRUE, q_bSlowOut := TRUE  (慢速正转)
  -> q_bRevOut := FALSE, q_bRunning := TRUE

i_bFwdCmd=TRUE, i_bSlowCmd=FALSE:
  -> q_bFwdOut := TRUE, q_bSlowOut := FALSE (高速正转)
  -> q_bRevOut := FALSE, q_bRunning := TRUE

i_bRevCmd=TRUE (FwdCmd=FALSE), i_bSlowCmd=TRUE:
  -> q_bRevOut := TRUE, q_bSlowOut := TRUE  (慢速反转)
  -> q_bFwdOut := FALSE, q_bRunning := TRUE

i_bRevCmd=TRUE (FwdCmd=FALSE), i_bSlowCmd=FALSE:
  -> q_bRevOut := TRUE, q_bSlowOut := FALSE (高速反转)
  -> q_bFwdOut := FALSE, q_bRunning := TRUE

i_bSlowCmd=TRUE (无方向命令):
  -> q_bFwdOut := FALSE, q_bRevOut := FALSE, q_bSlowOut := FALSE
  -> q_bRunning := FALSE  (慢速不能独立运行)

所有命令=FALSE:
  -> q_bFwdOut := FALSE, q_bRevOut := FALSE, q_bSlowOut := FALSE
  -> q_bRunning := FALSE
```

### 3.3 VFD故障检测

```
IF i_bVfdFault THEN
  q_bVfdAlarm := TRUE;
  q_bFwdOut := FALSE;
  q_bRevOut := FALSE;
  q_bSlowOut := FALSE;
  q_bRunning := FALSE;
ELSE
  q_bVfdAlarm := FALSE;
END_IF;
```

### 3.4 命令真值表

| i_bFwdCmd | i_bRevCmd | i_bSlowCmd | VFD  | q_bFwdOut | q_bRevOut | q_bSlowOut | q_bRunning | 说明     |
|:---------:|:---------:|:----------:|:----:|:---------:|:---------:|:----------:|:----------:|----------|
| 0         | 0         | 0          | OK   | 0         | 0         | 0          | 0          | 停止     |
| 0         | 0         | 1          | OK   | 0         | 0         | 0          | 0          | 慢速无效 |
| 1         | 0         | 0          | OK   | 1         | 0         | 0          | 1          | 高速正转 |
| 1         | 0         | 1          | OK   | 1         | 0         | 1          | 1          | 慢速正转 |
| 0         | 1         | 0          | OK   | 0         | 1         | 0          | 1          | 高速反转 |
| 0         | 1         | 1          | OK   | 0         | 1         | 1          | 1          | 慢速反转 |
| 1         | 1         | 0          | OK   | 1         | 0         | 0          | 1          | Fwd优先  |
| 1         | 1         | 1          | OK   | 1         | 0         | 1          | 1          | Fwd优先+慢速 |
| x         | x         | x          | 故障 | 0         | 0         | 0          | 0          | VFD封锁  |

## 4. 接口交互协议

```
编排器(FB_1002)                   FB_1012_ConveyorMotor
     |                                      |
     |-- i_bFwdCmd := TRUE ---------------->|  (高速正转)
     |<-- q_bFwdOut := TRUE ---------------|
     |<-- q_bRunning := TRUE --------------|
     |                                      |
     |-- i_bFwdCmd := TRUE ---------------->|
     |-- i_bSlowCmd := TRUE --------------->|  (切换慢速正转)
     |<-- q_bFwdOut := TRUE ---------------|
     |<-- q_bSlowOut := TRUE --------------|
     |                                      |
     |-- i_bFwdCmd := FALSE --------------->|  (停止)
     |-- i_bSlowCmd := FALSE -------------->|
     |<-- q_bFwdOut := FALSE --------------|
     |<-- q_bSlowOut := FALSE -------------|
     |<-- q_bRunning := FALSE -------------|
```

## 5. 报警码

本FB不直接输出报警码. VFD故障通过 `q_bVfdAlarm` 输出给编排器, 由编排器编码为带层号的报警码.

## 6. 关联文档

| 文档 | 路径                                                                                     |
|------|------------------------------------------------------------------------------------------|
| DSN  | 详细设计说明书_DSN-FB1012-ConveyorMotor-V9.0.0.md                                        |
| FB_1011 IFC | ../FB_1011_CylinderControl/PRD/接口文档_IFC-FB1011-CylinderControl-V9.0.0.md      |

---

## 附：2026-10-22 对齐前的旧说明（留底，不删）

> 2026-10-22 按 `plc docs check` 把上面接口表的“说明”列逐字改成代码行尾注释（代码为准，只改文档，没改 .scl）。
> 下表是改之前文档里的写法，有些比代码注释多写了单位、触发方式或用途，留在这里备查；
> 其中与代码实际行为不一致的地方，见共享库对齐记录 `PRD/文档代码对齐记录_20261022.md` 第 3 节。

| 引脚 | 对齐前文档说明 | 现说明（= 代码注释） |
|------|------|------|
| i_bSlowCmd | 慢速命令 (方向修饰符, 必须与Fwd/Rev组合才生效) | 慢速命令(方向修饰符, 必须与Fwd/Rev组合) |
| i_iCtrlMode | 控制模式: 0=端子控制(默认), 1=通讯控制(预留) | 控制模式: 0=端子控制, 1=通讯控制(预留) |
| i_rSpeed | 速度设定值(%, 通讯控制模式用, 端子模式下无效) | 速度设定值(%, 通讯模式用, 端子模式无效) |
| q_bFwdOut | 正转输出 (经互锁后) | 正转输出(经互锁后) |
| q_bRevOut | 反转输出 (经互锁后) | 反转输出(经互锁后) |
| q_bSlowOut | 慢速输出 (经互锁后) | 慢速输出(经互锁后) |
| q_bRunning | 运行中 (Fwd或Rev输出有效时) | 运行中 |
| q_bVfdAlarm | VFD报警 (锁存至故障消失) | VFD报警 |
