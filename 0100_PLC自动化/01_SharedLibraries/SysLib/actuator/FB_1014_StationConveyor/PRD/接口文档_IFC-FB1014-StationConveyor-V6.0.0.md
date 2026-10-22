---
spec_id: IFC-FB1014
title: "FB_1014 工站输送机接口定义"
version: "V6.0.0"
domain: plc
lifecycle: stable
canonical_path: "0100_PLC自动化/01_SharedLibraries/SysLib/actuator/FB_1014_StationConveyor/PRD/接口文档_IFC-FB1014-StationConveyor-V6.0.0.md"
tags: ["工站输送机", "编排器", "PLC功能块", "接口", "气缸", "电机", "运行模式"]
---
# 接口文档 FB_1014_StationConveyor

## 0. 文档基础信息

| 属性         | 值                                                                                                    |
| ------------ | ----------------------------------------------------------------------------------------------------- |
| **文档标题** | FB_1014 工站输送机接口定义                                                                            |
| **文档版本** | V6.0.0                                                                                                |
| **2026-10-22 对齐** | 接口表“说明”列按代码行尾注释逐字对齐（`plc docs check`），对齐前写法移到文末附录；只改文档，版本号和文件名不变 |
| **关联源码** | actuator/FB_1014_StationConveyor/FB_1014_StationConveyor.scl                                          |
| **编制日期** | 2026-05-31                                                                                            |
| **编制人**   | Trae                                                                                                  |
| **审核人**   | 人工                                                                                                  |
| **遵循规范** | LSP-905-V1.0.2, LSP-904-V1.2.0, LSP-903-V1.0.0, LSP-906-V1.0.0                                      |
| **变更记录** | V5.0.0: 纯编排器重构; 移除ST_Cylinder VAR_IN_OUT; 移除电磁阀输出; 扁平化气缸命令/状态接口; 删除内部FB_1011/FB_1012实例 |
|             | V6.0.0: 新增运行模式i_iMode; 新增对齐/出料子步骤计数器; 新增MODE常量; 功能切换表适配模式; OB1接线增加i_iMode; 交互协议补充Mode=1时序 |

## 0.1 核心设计决策

| 决策                                       | 理由                                                                                      |
| ------------------------------------------ | ----------------------------------------------------------------------------------------- |
| FB_1014是纯编排器, 内部无FB_1011/FB_1012实例 | 编排器只做决策, 执行器实例化在OB1; 解耦编排与执行, 各FB可独立测试                          |
| 气缸接口扁平化(命令/状态BOOL), 删除ST_Cylinder | 消除VAR_IN_OUT双向耦合; FB_1014只输出命令, 读入状态, 数据流单向清晰                       |
| 无电磁阀输出, 电磁阀由FB_1011在OB1输出      | 编排器不触碰物理IO; 电磁阀输出是FB_1011的职责, FB_1014只告诉FB_1011"伸出"或"收回"         |
| 拍正气缸极性由FB_1011的i_bExtendPolarity=TRUE处理 | OB1实例化拍正FB_1011时配置极性参数; FB_1014无需手动NOT, 逻辑语义统一(Extend=伸出)         |
| 电机命令直接映射FB_1012输入接口             | q_bFwdCmd/q_bRevCmd/q_bSlowCmd与FB_1012的i_bFwdCmd/i_bRevCmd/i_bSlowCmd一一对应, OB1直连  |
| 运行模式通过i_iMode输入, 编排器根据模式切换气缸/电机行为 | Mode决定气缸功能复用策略; 编排器内部逻辑分支处理, 执行器FB无需感知模式                      |

### 0.1.1 V5.0.0 -> V6.0.0 变更摘要

| 变更项              | V5.0.0                      | V6.0.0                              | 理由                         |
| ------------------- | --------------------------- | ----------------------------------- | ---------------------------- |
| 运行模式            | 无                          | VAR_INPUT i_iMode : INT := 1        | 支持双向/单向运行模式切换     |
| 对齐子步骤计数器    | 无                          | VAR m_iAlignStep : INT := 0         | ALIGN状态内部子步骤跟踪       |
| 出料准备子步骤计数器| 无                          | VAR m_iDischPrepStep : INT := 0     | DISCHARGE状态子步骤跟踪       |
| 模式常量            | 无                          | VAR_CONSTANT MODE_NORMAL=0, MODE_B_DUAL=1, MODE_A_DUAL=2 | 规范模式值语义, 禁止魔数     |
| 功能切换表          | 单模式(正常)                | 按Mode=0/1/2分别定义气缸功能        | Mode影响气缸功能复用策略     |
| OB1接线             | 无i_iMode                   | 新增i_iMode连线                     | 模式由上层/HMI传入            |
| 交互协议            | 单一流程                    | 新增Mode=1时序(S2b/S3/S4)           | B侧双向模式物料流向不同       |
| 接口统计            | VAR_INPUT 17, VAR 17, VAR_CONSTANT 9 | VAR_INPUT 18, VAR 19, VAR_CONSTANT 12 | 新增1个输入+2个变量+3个常量   |

### 0.1.2 V4.3.0 -> V5.0.0 变更摘要 (Breaking Change)

| 变更项              | V4.3.0                      | V5.0.0                              | 理由                         |
| ------------------- | --------------------------- | ----------------------------------- | ---------------------------- |
| 气缸接口            | VAR_IN_OUT ST_Cylinder x3   | 扁平VAR_INPUT(状态) + VAR_OUTPUT(命令) | 消除双向耦合, 数据流单向化   |
| 电磁阀输出          | q_yInfeedSolenoid等3个      | 删除                                | 电磁阀由FB_1011在OB1输出     |
| 马达输出命名        | q_yFwdCmd/q_yRevCmd/q_ySlowCmd | q_bFwdCmd/q_bRevCmd/q_bSlowCmd   | 前缀y改为b, 是命令而非物理IO |
| 内部FB实例          | FB_1011 x3 + FB_1012 x1     | 无内部FB实例                        | 纯编排器, 执行器在OB1实例化  |
| 气缸状态输入        | 封装在ST_Cylinder内         | 独立BOOL输入i_bXxxIsExtended等      | 扁平化, 来源明确(从FB_1011)  |
| VFD报警             | 无                          | i_bVfdAlarm(从FB_1012)              | 编排器需感知电机故障         |
| 拍正极性处理        | FB_1014内部NOT              | FB_1011 i_bExtendPolarity=TRUE      | 极性逻辑归FB_1011, 编排器无感 |

## 1. 功能概述

**工站输送机编排功能块**, 纯编排器角色: 根据上下游请求、传感器信号和运行模式, 输出气缸命令(给FB_1011)和电机命令(给FB_1012), 输入气缸状态(从FB_1011)和电机状态(从FB_1012).

FB_1014内部不实例化任何执行器FB, 所有执行器(FB_1011 x3, FB_1012 x1)在OB1中实例化, FB_1014仅通过扁平BOOL接口与之交互.

### 1.1 运行模式说明

| 模式常量      | 值 | 名称       | 说明                                                         |
| ------------- | -- | ---------- | ------------------------------------------------------------ |
| MODE_NORMAL   | 0  | 正常模式   | A侧进料, B侧出料; 标准单向输送                                |
| MODE_B_DUAL   | 1  | B侧双向    | B侧出料气缸可兼作进料; 支持B→B回流或B侧双向物料交换           |
| MODE_A_DUAL   | 2  | A侧双向    | A侧进料气缸可兼作出料; 支持A→A回流或A侧双向物料交换           |

> **默认值说明**: i_iMode默认值为1(MODE_B_DUAL), 适配最常见的双向往复输送场景. 若仅需单向上线, 在OB1中将i_iMode绑定为常量0(MODE_NORMAL).

### 1.2 职责边界

| 做什么                                         | 不做什么                                       |
| ---------------------------------------------- | ---------------------------------------------- |
| 状态机驱动(空闲->就绪->进料->对齐->加工->出料) | 不实例化FB_1011/FB_1012(在OB1中实例化)         |
| 输出气缸伸出/收回命令(给FB_1011)               | 不输出电磁阀信号(由FB_1011输出)                |
| 输出电机方向/慢速命令(给FB_1012)               | 不处理VFD复位(由OB1/上层处理)                  |
| 读取气缸到位状态(从FB_1011)                    | 不处理气缸超时/传感器故障(FB_1011内部处理)     |
| 读取VFD报警状态(从FB_1012)                     | 不处理安全互锁(由上层处理)                     |
| 上下游握手协议                                 | 不决定工站是否被选中(由上层决定)               |
| 根据i_iMode切换气缸功能复用策略                | 不直接驱动电磁阀(FB_1011负责)                   |

### 1.3 物料流向

```
        进料(反转)        拍正对齐         加工           出料(正转)
    <-------------- [====物料====] ============ --------------->
    上游方向         A侧对齐          工位             下游方向
         |           |                |                 |
      上游请求    拍正气缸伸出      X420检测         下游请求
         |        阻挡气缸下降         |                 |
         |<--- q_bReplyUpstream        q_bReplyDownstream ---|
         |           |                |                 |
      到位检测    FB_1011到位确认   X421/X422         到位检测
      (功能切换)                   (功能切换)        (功能切换)
```

### 1.4 功能切换说明 (Mode=0 NORMAL)

| 部件                    | 入料时功能       | 对齐时功能         | 出料时功能       |
| ----------------------- | ---------------- | ------------------ | ---------------- |
| i_xPos1 (X421)          | 入料检测光电1    | -                  | 出料检测光电1    |
| i_xPos2 (X422)          | 入料检测光电2    | -                  | 出料检测光电2    |
| DischargeCyl(FB_1011)   | **入料气缸**     | 保持放下           | 出料气缸         |
| InfeedCyl(FB_1011)      | 入料气缸         | **下降到位**       | **出料气缸**     |
| AlignCyl(FB_1011)       | -                | **伸出确认->收回** | -                |

### 1.5 功能切换说明 (Mode=1 B_DUAL, B侧双向)

| 部件                    | 入料时功能       | 对齐时功能         | 出料时功能       |
| ----------------------- | ---------------- | ------------------ | ---------------- |
| i_xPos1 (X421)          | 入料检测光电1    | -                  | 出料检测光电1    |
| i_xPos2 (X422)          | 入料检测光电2    | -                  | 出料检测光电2    |
| DischargeCyl(FB_1011)   | **入料气缸(主)+出料气缸(副)** | 保持放下       | 出料气缸         |
| InfeedCyl(FB_1011)      | **阻挡气缸**     | **下降到位**       | **出料气缸(主)** |
| AlignCyl(FB_1011)       | -                | **伸出确认->收回** | -                |

> **Mode=1关键差异**: B侧DischargeCyl在入料时兼用, 即物料可以从B侧进入(B侧双向); 入料阶段InfeedCyl仅作阻挡, DischargeCyl承担进料主导.

### 1.6 功能切换说明 (Mode=2 A_DUAL, A侧双向)

| 部件                    | 入料时功能       | 对齐时功能         | 出料时功能       |
| ----------------------- | ---------------- | ------------------ | ---------------- |
| i_xPos1 (X421)          | 入料检测光电1    | -                  | 出料检测光电1    |
| i_xPos2 (X422)          | 入料检测光电2    | -                  | 出料检测光电2    |
| DischargeCyl(FB_1011)   | **入料气缸**     | 保持放下           | **阻挡气缸**     |
| InfeedCyl(FB_1011)      | 入料气缸         | **下降到位**       | **出料气缸(主)+入料气缸(副)** |
| AlignCyl(FB_1011)       | -                | **伸出确认->收回** | -                |

> **Mode=2关键差异**: A侧InfeedCyl在出料时兼用, 即物料可以从A侧回流(A侧双向); 出料阶段DischargeCyl仅作阻挡, InfeedCyl承担出料主导.

## 2. 接口定义

### 2.1 VAR_INPUT - 控制信号 (9)

| 名称            | 类型 | 默认值 | 有效值域   | 说明           | 来源   |
| --------------- | ---- | ------ | ---------- | -------------- | ------ |
| i_bAutoMode     | BOOL | FALSE  | TRUE/FALSE | 自动模式使能   | OB1    |
| i_iMode         | INT  | 1      | 0~2        | 运行模式: 0=正常/1=B侧双向/2=A侧双向 | OB1/HMI |
| i_bUpstreamReq  | BOOL | FALSE  | TRUE/FALSE | 上游请求       | 上游FB |
| i_bDownstreamReq| BOOL | FALSE  | TRUE/FALSE | 下游请求       | 下游FB |
| i_bSelected     | BOOL | FALSE  | TRUE/FALSE | 工站选中       | 上层   |
| i_bProcessDone  | BOOL | FALSE  | TRUE/FALSE | 外部加工完成   | 上层   |
| i_bStop         | BOOL | FALSE  | TRUE/FALSE | 停止信号       | 上层   |
| i_bPause        | BOOL | FALSE  | TRUE/FALSE | 暂停信号       | 上层   |
| i_bSlowMode     | BOOL | FALSE  | TRUE/FALSE | 慢速模式使能   | 上层   |

### 2.2 VAR_INPUT - 延时参数 (4)

| 名称                | 类型 | 默认值 | 有效值域   | 说明                 | 来源       |
| ------------------- | ---- | ------ | ---------- | -------------------- | ---------- |
| i_dInfeedDelayMs    | DINT | 1000   | 0~60000    | 入料延时(ms)         | OB1/HMI    |
| i_dDischargeDelayMs | DINT | 1000   | 0~60000    | 出料延时(ms)         | OB1/HMI    |
| i_dAlignDelayMs     | DINT | 500    | 0~60000    | 拍正对齐延时(ms)     | OB1/HMI    |
| i_dDebounceMs       | DINT | 200    | 0~1000     | 输送光电去抖延时(ms) | OB1/HMI    |

### 2.3 VAR_INPUT - 输送传感器 (3)

| 名称          | 类型 | 默认值 | 有效值域   | 说明                          | 来源          |
| ------------- | ---- | ------ | ---------- | ----------------------------- | ------------- |
| i_xInfeedStart| BOOL | FALSE  | TRUE/FALSE | 入料开始光电(X420)        | OB1->IO映射   |
| i_xPos1       | BOOL | FALSE  | TRUE/FALSE | 位置1光电(X421)         | OB1->IO映射  |
| i_xPos2       | BOOL | FALSE  | TRUE/FALSE | 位置2光电(X422)         | OB1->IO映射  |

### 2.4 VAR_INPUT - 气缸状态(从FB_1011) (6)

| 名称                   | 类型 | 默认值 | 有效值域   | 说明                          | 来源                |
| ---------------------- | ---- | ------ | ---------- | ----------------------------- | ------------------- |
| i_bInfeedIsExtended    | BOOL | FALSE  | TRUE/FALSE | A侧阻挡气缸伸出到位(来自FB_1011) | FB_1011.q_bIsExtended |
| i_bInfeedIsRetracted   | BOOL | FALSE  | TRUE/FALSE | A侧阻挡气缸收回到位(来自FB_1011) | FB_1011.q_bIsRetracted|
| i_bAlignIsExtended     | BOOL | FALSE  | TRUE/FALSE | 拍正气缸伸出到位(来自FB_1011)   | FB_1011.q_bIsExtended |
| i_bAlignIsRetracted    | BOOL | FALSE  | TRUE/FALSE | 拍正气缸收回到位(来自FB_1011)   | FB_1011.q_bIsRetracted|
| i_bDischargeIsExtended | BOOL | FALSE  | TRUE/FALSE | B侧阻挡气缸伸出到位(来自FB_1011) | FB_1011.q_bIsExtended |
| i_bDischargeIsRetracted| BOOL | FALSE  | TRUE/FALSE | B侧阻挡气缸收回到位(来自FB_1011) | FB_1011.q_bIsRetracted|

> **极性透明**: 拍正气缸的FB_1011实例在OB1中配置i_bExtendPolarity=TRUE, 因此FB_1011的q_bIsExtended/q_bIsRetracted已经是极性映射后的逻辑值. FB_1014无需关心极性, 直接使用即可.

### 2.5 VAR_INPUT - 电机状态(从FB_1012) (1)

| 名称        | 类型 | 默认值 | 有效值域   | 说明                    | 来源              |
| ----------- | ---- | ------ | ---------- | ----------------------- | ----------------- |
| i_bVfdAlarm | BOOL | FALSE  | TRUE/FALSE | VFD报警(来自FB_1012)     | FB_1012.q_bVfdAlarm |

### 2.6 VAR_OUTPUT - 气缸命令(给FB_1011) (6)

| 名称              | 类型 | 默认值 | 有效值域   | 说明                        | 去向               |
| ----------------- | ---- | ------ | ---------- | --------------------------- | ------------------ |
| q_bInfeedExtend   | BOOL | FALSE  | TRUE/FALSE | A侧阻挡气缸伸出命令          | FB_1011.i_bExtend  |
| q_bInfeedRetract  | BOOL | FALSE  | TRUE/FALSE | A侧阻挡气缸收回命令          | FB_1011.i_bRetract |
| q_bAlignExtend    | BOOL | FALSE  | TRUE/FALSE | 拍正气缸伸出命令            | FB_1011.i_bExtend  |
| q_bAlignRetract   | BOOL | FALSE  | TRUE/FALSE | 拍正气缸收回命令            | FB_1011.i_bRetract |
| q_bDischargeExtend| BOOL | FALSE  | TRUE/FALSE | B侧阻挡气缸伸出命令          | FB_1011.i_bExtend  |
| q_bDischargeRetract| BOOL | FALSE | TRUE/FALSE | B侧阻挡气缸收回命令          | FB_1011.i_bRetract |

> **命令语义**: Extend/Retract是逻辑语义, 实际电磁阀输出由FB_1011根据i_bExtendPolarity决定. 拍正气缸在OB1中配置i_bExtendPolarity=TRUE, 因此q_bAlignExtend=TRUE时FB_1011会自动处理极性反转.

### 2.7 VAR_OUTPUT - 电机命令(给FB_1012) (3)

| 名称       | 类型 | 默认值 | 有效值域   | 说明                          | 去向              |
| ---------- | ---- | ------ | ---------- | ----------------------------- | ----------------- |
| q_bFwdCmd  | BOOL | FALSE  | TRUE/FALSE | 电机正转命令(到FB_1012)        | FB_1012.i_bFwdCmd |
| q_bRevCmd  | BOOL | FALSE  | TRUE/FALSE | 电机反转命令(到FB_1012)        | FB_1012.i_bRevCmd |
| q_bSlowCmd | BOOL | FALSE  | TRUE/FALSE | 电机慢速命令(到FB_1012)     | FB_1012.i_bSlowCmd|

> **慢速修饰规则**: q_bSlowCmd是方向命令的修饰符, 不能独立运行. 仅当q_bFwdCmd或q_bRevCmd为TRUE时, q_bSlowCmd才生效. 参见FB_1012 IFC.

### 2.8 VAR_OUTPUT - 握手 (2)

| 名称              | 类型 | 默认值 | 有效值域   | 说明           | 去向   |
| ----------------- | ---- | ------ | ---------- | -------------- | ------ |
| q_bReplyUpstream  | BOOL | FALSE  | TRUE/FALSE | 回应上游可进料 | 上游FB |
| q_bReplyDownstream| BOOL | FALSE  | TRUE/FALSE | 回应下游可出料 | 下游FB |

### 2.9 VAR_OUTPUT - 诊断 (4)

| 名称                 | 类型  | 默认值 | 有效值域    | 说明                | 去向       |
| -------------------- | ----- | ------ | ----------- | ------------------- | ---------- |
| q_iState             | INT   | 0      | 0~8         | 当前状态(0-8)       | HMI/上层   |
| q_dwProductionCount  | DWORD | 0      | 0~16#FFFFFFFF| 产量计数器        | HMI/上层   |
| q_bInfeedActive      | BOOL  | FALSE  | TRUE/FALSE  | 输送进行中          | HMI/上层   |
| q_bIntAlarmMem       | BOOL  | FALSE  | TRUE/FALSE  | 中断报警暂存        | HMI/上层   |

### 2.10 VAR - 内部状态变量 (2)

> 2026-10-22 对齐说明：这两个是块内部的静态变量（`VAR`），不是接口引脚，`plc docs check` 只核对接口引脚，所以本表第一列不再叫“名称”，检查器不把它当接口表。
> 值域按代码实际改了：`m_iAlignStep` 代码里最大赋到 4（FB_1014_StationConveyor.scl:402），`m_iDischPrepStep` 最大赋到 2（同文件:509）。原写的“0~3”见文末附录。

| 内部变量         | 类型 | 默认值 | 有效值域 | 说明（= 代码注释）           |
| ---------------- | ---- | ------ | -------- | ---------------------------- |
| m_iAlignStep     | INT  | 0      | 0~4      | 拍正对齐子步骤计数(ALIGN状态) |
| m_iDischPrepStep | INT  | 0      | 0~2      | 出料准备子步骤计数(DISCHARGE状态) |

> **子步骤计数器用途**: m_iAlignStep跟踪ALIGN状态内"伸出检测→下降到位→拍正收回"子流程; m_iDischPrepStep跟踪DISCHARGE状态内"出料气缸准备→电机启动→到位检测"子流程. Mode=1/2时子步骤分支不同, 详见第4章交互协议.

### 2.11 接口统计

| 项目                     | V5.0.0 | V6.0.0 | 变化  |
| ------------------------ | :----: | :----: | :---: |
| VAR_INPUT (控制)         | 8      | 9      | +1    |
| VAR_INPUT (参数)         | 4      | 4      | 0     |
| VAR_INPUT (传感器)       | 3      | 3      | 0     |
| VAR_INPUT (气缸状态)     | 6      | 6      | 0     |
| VAR_INPUT (电机状态)     | 1      | 1      | 0     |
| VAR (内部状态)           | 0      | 2      | +2    |
| VAR_CONSTANT             | 9      | 12     | +3    |
| VAR_OUTPUT (气缸命令)    | 6      | 6      | 0     |
| VAR_OUTPUT (电机命令)    | 3      | 3      | 0     |
| VAR_OUTPUT (握手)        | 2      | 2      | 0     |
| VAR_OUTPUT (诊断)        | 4      | 4      | 0     |
| **VAR_INPUT总计**        | **22** | **23** | **+1**|
| **VAR总计**              | **0**  | **2**  | **+2**|
| **VAR_CONSTANT总计**     | **9**  | **12** | **+3**|
| **VAR_OUTPUT总计**       | **15** | **15** | **0** |

## 3. 行为逻辑

### 3.1 状态机步序常量

| 常量名          | 值 | 名称   | 说明                           |
| --------------- | -- | ------ | ------------------------------ |
| ST_IDLE         | 0  | 空闲   | 等待模式使能                   |
| ST_READY        | 1  | 就绪   | 自动模式下等待请求             |
| ST_INFEED       | 2  | 进料   | X421/X422作入料检测, 气缸切换  |
| ST_ALIGN        | 3  | 对齐   | 拍正气缸确认+阻挡下降+拍正收回 |
| ST_PROCESSING   | 4  | 加工中 | 皮带停止, 等待加工完成         |
| ST_DISCHARGE    | 5  | 出料   | X421/X422作出料检测, 气缸切换  |
| ST_COMPLETE     | 6  | 完成   | 复位标志                       |
| ST_PAUSE        | 7  | 暂停   | 暂停信号触发                   |
| ST_FAULT        | 8  | 停止   | 停止信号触发                   |

### 3.2 运行模式常量

| 常量名        | 值 | 名称       | 说明                                 |
| ------------- | -- | ---------- | ------------------------------------ |
| MODE_NORMAL   | 0  | 正常模式   | A侧进料, B侧出料; 标准单向输送        |
| MODE_B_DUAL   | 1  | B侧双向    | B侧出料气缸可兼作进料(B侧双向)       |
| MODE_A_DUAL   | 2  | A侧双向    | A侧进料气缸可兼作出料(A侧双向)       |

> **模式选择原则**: 正常情况下使用Mode=0或1; Mode=1适用于需要从B侧回流/补料的场景; Mode=2适用于需要从A侧回流/排料的场景. 模式切换应在ST_IDLE状态下进行, 运行中切换将被忽略.

### 3.3 VFD故障封锁

```
IF i_bVfdAlarm THEN
    q_bFwdCmd := FALSE;
    q_bRevCmd := FALSE;
    q_bSlowCmd := FALSE;
    q_bInfeedExtend := FALSE;
    q_bInfeedRetract := TRUE;
    q_bAlignExtend := FALSE;
    q_bAlignRetract := TRUE;
    q_bDischargeExtend := FALSE;
    q_bDischargeRetract := TRUE;
    q_bReplyUpstream := FALSE;
    q_bReplyDownstream := FALSE;
    q_bInfeedActive := FALSE;
    m_iAlignStep := 0;
    m_iDischPrepStep := 0;
    -> 转入 ST_FAULT;
END_IF;
```

### 3.4 气缸/传感器功能切换表 (按Mode区分)

#### 3.4.1 Mode=0 (NORMAL) - 入料时(INFEED状态)

| 物理位置                | 功能         | 命令输出                    | 状态输入                   |
| ----------------------- | ------------ | --------------------------- | -------------------------- |
| DischargeCyl(FB_1011)   | **入料气缸** | q_bDischargeExtend=TRUE     | i_bDischargeIsExtended     |
| InfeedCyl(FB_1011)      | 阻挡气缸     | q_bInfeedRetract=TRUE       | i_bInfeedIsRetracted       |
| AlignCyl(FB_1011)       | 不参与       | 保持收回                    | -                          |

#### 3.4.2 Mode=0 (NORMAL) - 对齐时(ALIGN状态)

| 物理位置                | 功能           | 命令输出                  | 状态输入                 |
| ----------------------- | -------------- | ------------------------- | ------------------------ |
| AlignCyl(FB_1011)       | **拍正气缸**   | q_bAlignExtend->q_bAlignRetract | i_bAlignIsExtended->i_bAlignIsRetracted |
| InfeedCyl(FB_1011)      | **阻挡气缸下降** | q_bInfeedExtend=TRUE      | i_bInfeedIsExtended      |
| DischargeCyl(FB_1011)   | 保持放下       | q_bDischargeExtend=TRUE   | i_bDischargeIsExtended   |

#### 3.4.3 Mode=0 (NORMAL) - 出料时(DISCHARGE状态)

| 物理位置                | 功能         | 命令输出                  | 状态输入                   |
| ----------------------- | ------------ | ------------------------- | -------------------------- |
| InfeedCyl(FB_1011)      | **出料气缸** | q_bInfeedExtend=TRUE      | i_bInfeedIsExtended        |
| DischargeCyl(FB_1011)   | 出料气缸     | q_bDischargeRetract=TRUE  | i_bDischargeIsRetracted    |
| AlignCyl(FB_1011)       | 不参与       | 保持收回                  | -                          |

#### 3.4.4 Mode=1 (B_DUAL) - 入料时(INFEED状态)

| 物理位置                | 功能                   | 命令输出                    | 状态输入                   |
| ----------------------- | ---------------------- | --------------------------- | -------------------------- |
| DischargeCyl(FB_1011)   | **入料气缸(主)**       | q_bDischargeExtend=TRUE     | i_bDischargeIsExtended     |
| InfeedCyl(FB_1011)      | **阻挡气缸**           | q_bInfeedRetract=TRUE       | i_bInfeedIsRetracted       |
| AlignCyl(FB_1011)       | 不参与                 | 保持收回                    | -                          |

> **Mode=1入料差异**: 与Mode=0相同, B侧DischargeCyl承担入料主导. 差异体现在DISCHARGE阶段(见3.4.6).

#### 3.4.5 Mode=1 (B_DUAL) - 对齐时(ALIGN状态)

| 物理位置                | 功能           | 命令输出                  | 状态输入                 |
| ----------------------- | -------------- | ------------------------- | ------------------------ |
| AlignCyl(FB_1011)       | **拍正气缸**   | q_bAlignExtend->q_bAlignRetract | i_bAlignIsExtended->i_bAlignIsRetracted |
| InfeedCyl(FB_1011)      | **阻挡气缸下降** | q_bInfeedExtend=TRUE      | i_bInfeedIsExtended      |
| DischargeCyl(FB_1011)   | 保持放下       | q_bDischargeExtend=TRUE   | i_bDischargeIsExtended   |

> **Mode=1对齐**: 与Mode=0行为一致.

#### 3.4.6 Mode=1 (B_DUAL) - 出料时(DISCHARGE状态)

| 物理位置                | 功能                   | 命令输出                  | 状态输入                   |
| ----------------------- | ---------------------- | ------------------------- | -------------------------- |
| InfeedCyl(FB_1011)      | **出料气缸(主)**       | q_bInfeedExtend=TRUE      | i_bInfeedIsExtended        |
| DischargeCyl(FB_1011)   | **出料气缸(副)+兼入料**| q_bDischargeRetract=TRUE  | i_bDischargeIsRetracted    |
| AlignCyl(FB_1011)       | 不参与                 | 保持收回                  | -                          |

> **Mode=1出料关键差异**: DischargeCyl在出料时保持"入料气缸"身份(收回), 即B侧气缸出料后同时准备好接收下一物料; InfeedCyl作为主出料气缸(伸出)引导物料向B侧移动. 见第4章S2b/S3时序.

#### 3.4.7 Mode=2 (A_DUAL) - 入料时(INFEED状态)

| 物理位置                | 功能         | 命令输出                    | 状态输入                   |
| ----------------------- | ------------ | --------------------------- | -------------------------- |
| DischargeCyl(FB_1011)   | **入料气缸** | q_bDischargeExtend=TRUE     | i_bDischargeIsExtended     |
| InfeedCyl(FB_1011)      | 入料气缸     | q_bInfeedRetract=TRUE       | i_bInfeedIsRetracted       |
| AlignCyl(FB_1011)       | 不参与       | 保持收回                    | -                          |

> **Mode=2入料**: 与Mode=0行为一致.

#### 3.4.8 Mode=2 (A_DUAL) - 对齐时(ALIGN状态)

| 物理位置                | 功能           | 命令输出                  | 状态输入                 |
| ----------------------- | -------------- | ------------------------- | ------------------------ |
| AlignCyl(FB_1011)       | **拍正气缸**   | q_bAlignExtend->q_bAlignRetract | i_bAlignIsExtended->i_bAlignIsRetracted |
| InfeedCyl(FB_1011)      | **阻挡气缸下降** | q_bInfeedExtend=TRUE      | i_bInfeedIsExtended      |
| DischargeCyl(FB_1011)   | 保持放下       | q_bDischargeExtend=TRUE   | i_bDischargeIsExtended   |

> **Mode=2对齐**: 与Mode=0行为一致.

#### 3.4.9 Mode=2 (A_DUAL) - 出料时(DISCHARGE状态)

| 物理位置                | 功能                   | 命令输出                  | 状态输入                   |
| ----------------------- | ---------------------- | ------------------------- | -------------------------- |
| InfeedCyl(FB_1011)      | **出料气缸(主)+入料气缸(副)** | q_bInfeedExtend=TRUE | i_bInfeedIsExtended        |
| DischargeCyl(FB_1011)   | **阻挡气缸**           | q_bDischargeExtend=TRUE   | i_bDischargeIsExtended     |
| AlignCyl(FB_1011)       | 不参与                 | 保持收回                  | -                          |

> **Mode=2出料关键差异**: InfeedCyl在出料时伸出引导物料向A侧移动(出料主气缸), 同时兼作入料气缸排队; DischargeCyl作为阻挡气缸(伸出)防止物料过冲. 见第4章S4时序.

## 4. 接口交互协议

### 4.1 完整进料->对齐->加工->出料流程 (Mode=0 NORMAL)

```
OB1                           FB_1014                FB_1011(Infeed)   FB_1011(Align)    FB_1011(Discharge)  FB_1012
 |                               |                       |                 |                  |                |
 |  i_iMode=0, i_bUpstreamReq=TRUE                      |                 |                  |                |
 |------------------------------>|                       |                 |                  |                |
 |                               |-- q_bDischargeExtend  |                 |                  |                |
 |                               |--------------------->| (via OB1 wiring)|                  |                |
 |                               |                       |                 |                  |                |
 |                               |-- q_bInfeedRetract    |                 |                  |                |
 |                               |--------------------->| (via OB1 wiring)|                  |                |
 |                               |                       |                 |                  |                |
 |                               |-- q_bRevCmd=TRUE      |                 |                  |                |
 |                               |------------------------------------------------------------>|                |
 |                               |                       |                 |                  |                |
 |  i_bDischargeIsExtended=TRUE  |                       |                 |                  |                |
 |<------------------------------|  (from FB_1011 status)|                 |                  |                |
 |                               |                       |                 |                  |                |
 |                               |-- q_bReplyUpstream=TRUE                |                  |                |
 |<------------------------------|                       |                 |                  |                |
 |                               |                       |                 |                  |                |
 |  (物料到位, 传感器触发)       |                       |                 |                  |                |
 |  i_xPos1=TRUE, i_xPos2=TRUE  |                       |                 |                  |                |
 |------------------------------>|                       |                 |                  |                |
 |                               |-- q_bRevCmd=FALSE     |                 |                  |                |
 |                               |------------------------------------------------------------>|                |
 |                               |                       |                 |                  |                |
 |                               |  [ALIGN state]        |                 |                  |                |
 |                               |-- q_bAlignExtend=TRUE |                 |                  |                |
 |                               |---------------------------------------->|                  |                |
 |                               |-- q_bInfeedExtend=TRUE|                 |                  |                |
 |                               |--------------------->| (via OB1 wiring)|                  |                |
 |                               |                       |                 |                  |                |
 |  i_bAlignIsExtended=TRUE      |                       |                 |                  |                |
 |<------------------------------|  (from FB_1011 status)|                 |                  |                |
 |                               |                       |                 |                  |                |
 |                               |-- q_bAlignRetract=TRUE|                 |                  |                |
 |                               |---------------------------------------->|                  |                |
 |                               |                       |                 |                  |                |
 |  i_bAlignIsRetracted=TRUE     |                       |                 |                  |                |
 |<------------------------------|  (from FB_1011 status)|                 |                  |                |
 |                               |                       |                 |                  |                |
 |                               |  [PROCESSING state]   |                 |                  |                |
 |  i_bProcessDone=TRUE          |                       |                 |                  |                |
 |------------------------------>|                       |                 |                  |                |
 |                               |                       |                 |                  |                |
 |                               |  [DISCHARGE state]    |                 |                  |                |
 |                               |  m_iDischPrepStep:=1  |                 |                  |                |
 |                               |-- q_bInfeedExtend=TRUE|                 |                  |                |
 |                               |--------------------->| (via OB1 wiring)|                  |                |
 |                               |-- q_bDischargeRetract |                 |                  |                |
 |                               |---------------------------------------------------------->|                |
 |                               |                       |                 |                  |                |
 |  i_bInfeedIsExtended=TRUE     |                       |                 |                  |                |
 |<------------------------------|  (from FB_1011 status)|                 |                  |                |
 |                               |  m_iDischPrepStep:=2  |                 |                  |                |
 |                               |-- q_bFwdCmd=TRUE      |                 |                  |                |
 |                               |------------------------------------------------------------>|                |
 |                               |                       |                 |                  |                |
 |                               |-- q_bReplyDownstream=TRUE              |                  |                |
 |<------------------------------|                       |                 |                  |                |
```

### 4.2 交互协议 - Mode=1 (B_DUAL) 出料阶段 (S3时序)

Mode=1下INFEED和ALIGN阶段与Mode=0一致, 差异集中在DISCHARGE阶段. 以下展示DISCHARGE状态完整时序(含子步骤):

```
OB1                           FB_1014                FB_1011(Infeed)   FB_1011(Align)    FB_1011(Discharge)  FB_1012
 |                               |                       |                 |                  |                |
 |                               |  [DISCHARGE state]    |                 |                  |                |
 |                               |  m_iDischPrepStep:=1  |                 |                  |                |
 |                               |                       |                 |                  |                |
 |                               |-- q_bInfeedExtend=TRUE|                 |                  |                |
 |                               |--------------------->| (via OB1 wiring)|                  |                |
 |                               |                       |    [Mode=1: InfeedCyl 出料主导]|                  |                |
 |                               |                       |                 |                  |                |
 |                               |-- q_bDischargeRetract=TRUE              |                  |                |
 |                               |---------------------------------------------------------->|                |
 |                               |                       |    [Mode=1: DischargeCyl 收回=出料兼入料]|             |                |
 |                               |                       |                 |                  |                |
 |  i_bInfeedIsExtended=TRUE     |                       |                 |                  |                |
 |<------------------------------|  (from FB_1011)       |                 |                  |                |
 |                               |                       |                 |                  |                |
 |  i_bDischargeIsRetracted=TRUE |                       |                 |                  |                |
 |<------------------------------|  (from FB_1011)       |                 |                  |                |
 |                               |                       |                 |                  |                |
 |                               |  m_iDischPrepStep:=2  |                 |                  |                |
 |                               |-- q_bFwdCmd=TRUE      |                 |                  |                |
 |                               |------------------------------------------------------------>|                |
 |                               |                       |                 |                  |                |
 |  (物料移动, X421/X422触发)    |                       |                 |                  |                |
 |  i_xPos1=TRUE, i_xPos2=TRUE  |                       |                 |                  |                |
 |------------------------------>|                       |                 |                  |                |
 |                               |                       |                 |                  |                |
 |                               |  m_iDischPrepStep:=3  |                 |                  |                |
 |                               |-- q_bFwdCmd=FALSE     |                 |                  |                |
 |                               |------------------------------------------------------------>|                |
 |                               |                       |                 |                  |                |
 |                               |-- q_bReplyDownstream=TRUE              |                  |                |
 |<------------------------------|                       |                 |                  |                |
 |                               |                       |                 |                  |                |
 |                               |  (DischargeCyl保持收回, |                 |                  |                |
 |                               |   可立即接收下一物料)   |                 |                  |                |
 |                               |  m_iDischPrepStep:=0  |                 |                  |                |
```

> **Mode=1出料时序要点**:
> - S3.1(m_iDischPrepStep=1): InfeedCyl伸出(出料主导) + DischargeCyl收回(出料副+入料预备)
> - S3.2(m_iDischPrepStep=2): 等待气缸到位→启动电机正转→物料送出
> - S3.3(m_iDischPrepStep=3): 传感器检测到位→停止电机→握手下游
> - 出料完成后DischargeCyl保持收回状态, 允许B侧立即启动下一轮进料(双向优势)

### 4.3 交互协议 - Mode=1 (B_DUAL) 连续出料/回流 (S2b时序)

Mode=1支持B侧回流入料(即DischargeCyl出料后立即作为入料气缸接收B侧回流):

```
OB1                           FB_1014                FB_1011(Infeed)   FB_1011(Align)    FB_1011(Discharge)  FB_1012
 |                               |                       |                 |                  |                |
 |  (上一轮出料完成,             |                       |                 |                  |                |
 |   DischargeCyl已收回)         |                       |                 |                  |                |
 |  i_bDownstreamReq=TRUE        |                       |                 |                  |                |
 |------------------------------>|                       |                 |                  |                |
 |                               |                       |                 |                  |                |
 |                               |  [Mode=1: B侧回流入料]|                 |                  |                |
 |                               |  DischargeCyl已收回,  |                 |                  |                |
 |                               |  直接作为入料气缸     |                 |                  |                |
 |                               |                       |                 |                  |                |
 |                               |-- q_bRevCmd=TRUE      |                 |                  |                |
 |                               |------------------------------------------------------------>|                |
 |                               |                       |                 |                  |                |
 |                               |-- q_bReplyUpstream=TRUE (回应B侧上游, 可接收回流)            |                |
 |<------------------------------|                       |                 |                  |                |
 |                               |                       |                 |                  |                |
 |  (B侧回流物料到位)            |                       |                 |                  |                |
 |  i_xPos1=TRUE, i_xPos2=TRUE  |                       |                 |                  |                |
 |------------------------------>|                       |                 |                  |                |
 |                               |-- q_bRevCmd=FALSE     |                 |                  |                |
 |                               |------------------------------------------------------------>|                |
 |                               |                       |                 |                  |                |
 |                               |  -> 进入ALIGN/正常流程|                 |                  |                |
```

> **Mode=1回流优势**: DischargeCyl出料后无需重新伸出即可接收B侧回流物料, 减少气缸动作次数, 提升双向输送节拍.

### 4.4 交互协议 - Mode=2 (A_DUAL) 出料阶段 (S4时序)

Mode=2下INFEED和ALIGN阶段与Mode=0一致, 差异集中在DISCHARGE阶段:

```
OB1                           FB_1014                FB_1011(Infeed)   FB_1011(Align)    FB_1011(Discharge)  FB_1012
 |                               |                       |                 |                  |                |
 |                               |  [DISCHARGE state]    |                 |                  |                |
 |                               |  m_iDischPrepStep:=1  |                 |                  |                |
 |                               |                       |                 |                  |                |
 |                               |-- q_bInfeedExtend=TRUE|                 |                  |                |
 |                               |--------------------->| (via OB1 wiring)|                  |                |
 |                               |    [Mode=2: InfeedCyl 出料主+入料副]  |                  |                |
 |                               |                       |                 |                  |                |
 |                               |-- q_bDischargeExtend=TRUE              |                  |                |
 |                               |---------------------------------------------------------->|                |
 |                               |    [Mode=2: DischargeCyl 伸出=阻挡]    |                  |                |
 |                               |                       |                 |                  |                |
 |  i_bInfeedIsExtended=TRUE     |                       |                 |                  |                |
 |<------------------------------|  (from FB_1011)       |                 |                  |                |
 |                               |                       |                 |                  |                |
 |  i_bDischargeIsExtended=TRUE  |                       |                 |                  |                |
 |<------------------------------|  (from FB_1011)       |                 |                  |                |
 |                               |                       |                 |                  |                |
 |                               |  m_iDischPrepStep:=2  |                 |                  |                |
 |                               |-- q_bFwdCmd=TRUE      |                 |                  |                |
 |                               |------------------------------------------------------------>|                |
 |                               |                       |                 |                  |                |
 |  (物料移动, X421/X422触发)    |                       |                 |                  |                |
 |  i_xPos1=TRUE, i_xPos2=TRUE  |                       |                 |                  |                |
 |------------------------------>|                       |                 |                  |                |
 |                               |                       |                 |                  |                |
 |                               |  m_iDischPrepStep:=3  |                 |                  |                |
 |                               |-- q_bFwdCmd=FALSE     |                 |                  |                |
 |                               |------------------------------------------------------------>|                |
 |                               |                       |                 |                  |                |
 |                               |-- q_bReplyDownstream=TRUE              |                  |                |
 |<------------------------------|                       |                 |                  |                |
 |                               |                       |                 |                  |                |
 |                               |  (InfeedCyl保持伸出,  |                 |                  |                |
 |                               |   可排队接收下一物料)  |                 |                  |                |
 |                               |  m_iDischPrepStep:=0  |                 |                  |                |
```

> **Mode=2出料时序要点**:
> - S4.1(m_iDischPrepStep=1): InfeedCyl伸出(出料主导) + DischargeCyl伸出(阻挡B侧)
> - S4.2(m_iDischPrepStep=2): 等待气缸到位→启动电机正转→物料向A侧送出
> - S4.3(m_iDischPrepStep=3): 传感器检测到位→停止电机→握手下游(A侧下游)
> - 出料完成后InfeedCyl保持伸出, 可排队接收A侧回流物料

### 4.5 VFD报警交互

```
FB_1012                         FB_1014                OB1
   |                              |                     |
   |-- q_bVfdAlarm := TRUE ------>|  (via OB1 wiring)   |
   |                              |                     |
   |                              | q_bFwdCmd := FALSE  |
   |                              | q_bRevCmd := FALSE  |
   |                              | q_bSlowCmd := FALSE |
   |                              | q_bIntAlarmMem := TRUE
   |                              | m_iAlignStep := 0   |
   |                              | m_iDischPrepStep := 0
   |                              | -> ST_FAULT         |
   |                              |                     |
   |                              | q_bReplyUpstream := FALSE
   |                              | q_bReplyDownstream := FALSE
```

## 5. 报警码

本FB不直接输出报警码. 报警信号通过以下BOOL输出给上层, 由上层编码为带层号的完整报警码:

| 信号             | 类型 | 说明                                   | 编码规则       |
| ---------------- | ---- | -------------------------------------- | -------------- |
| q_bIntAlarmMem   | BOOL | 中断报警暂存(VFD故障/停止信号触发)     | 由上层编码     |

> **气缸超时/传感器故障**: 由FB_1011内部检测并通过q_bTimeout/q_bSensorFault输出, FB_1014不转发. OB1可直接读取FB_1011实例的报警输出进行编码.

## 6. 组件复用审查

| 需求功能     | SysLib已有组件  | 复用方式       | 不复用原因                 |
| ------------ | --------------- | -------------- | -------------------------- |
| 气缸控制     | FB_1011         | OB1实例化, 命令/状态直连 | FB_1014是纯编排器, 不内部实例化 |
| 电机控制     | FB_1012         | OB1实例化, 命令/状态直连 | FB_1014是纯编排器, 不内部实例化 |
| 定时延时     | FB_TON          | VAR实例化      | -                          |
| 累积计时     | FB_TONR         | 未使用         | 当前无累积计时需求         |

## 7. OB1接线示例

### 7.1 实例声明

```scl
// ========== FB实例声明 ==========
// 编排器
fbStationConveyor : FB_1014;

// 气缸执行器 (3个FB_1011实例)
fbInfeedCyl   : FB_1011;    // A侧阻挡气缸
fbAlignCyl    : FB_1011;    // 拍正气缸 (极性取反)
fbDischargeCyl: FB_1011;    // B侧出料气缸

// 电机执行器 (1个FB_1012实例)
fbConveyorMotor: FB_1012;
```

### 7.2 FB_1014调用 (编排器)

```scl
// ========== FB_1014 编排器调用 ==========
fbStationConveyor(
    // 控制信号
    i_bAutoMode      := bAutoMode,
    i_iMode          := iMode,               // V6.0.0新增: 运行模式 0=正常/1=B侧双向/2=A侧双向
    i_bUpstreamReq   := bUpstreamReq,
    i_bDownstreamReq := bDownstreamReq,
    i_bSelected      := bSelected,
    i_bProcessDone   := bProcessDone,
    i_bStop          := bStop,
    i_bPause         := bPause,
    i_bSlowMode      := bSlowMode,

    // 延时参数
    i_dInfeedDelayMs    := dInfeedDelayMs,
    i_dDischargeDelayMs := dDischargeDelayMs,
    i_dAlignDelayMs     := dAlignDelayMs,
    i_dDebounceMs       := dDebounceMs,

    // 输送传感器
    i_xInfeedStart := xInfeedStart,    // X420
    i_xPos1        := xPos1,           // X421
    i_xPos2        := xPos2,           // X422

    // 气缸状态 (从FB_1011读取)
    i_bInfeedIsExtended    := fbInfeedCyl.q_bIsExtended,
    i_bInfeedIsRetracted   := fbInfeedCyl.q_bIsRetracted,
    i_bAlignIsExtended     := fbAlignCyl.q_bIsExtended,
    i_bAlignIsRetracted    := fbAlignCyl.q_bIsRetracted,
    i_bDischargeIsExtended := fbDischargeCyl.q_bIsExtended,
    i_bDischargeIsRetracted:= fbDischargeCyl.q_bIsRetracted,

    // 电机状态 (从FB_1012读取)
    i_bVfdAlarm := fbConveyorMotor.q_bVfdAlarm
);

// 读取FB_1014输出
bReplyUpstream   := fbStationConveyor.q_bReplyUpstream;
bReplyDownstream := fbStationConveyor.q_bReplyDownstream;
iStationState    := fbStationConveyor.q_iState;
dwProductionCount:= fbStationConveyor.q_dwProductionCount;
bInfeedActive    := fbStationConveyor.q_bInfeedActive;
bIntAlarmMem     := fbStationConveyor.q_bIntAlarmMem;
```

### 7.3 FB_1011调用 (气缸执行器 x3)

```scl
// ========== FB_1011 进料气缸 ==========
fbInfeedCyl(
    i_bExtend         := fbStationConveyor.q_bInfeedExtend,
    i_bRetract        := fbStationConveyor.q_bInfeedRetract,
    i_bExtendedPos    := xInfeedExtendedPos,     // 磁环传感器
    i_bRetractedPos   := xInfeedRetractedPos,    // 磁环传感器
    i_iTimeoutMs      := 5000,
    i_iDebounceMs     := 50,
    i_iSolenoidType   := 0,
    i_bExtendPolarity := FALSE                   // 正常极性
);
yInfeedSolenoid := fbInfeedCyl.q_bSolenoid;      // 电磁阀输出->物理IO

// ========== FB_1011 拍正气缸 ==========
fbAlignCyl(
    i_bExtend         := fbStationConveyor.q_bAlignExtend,
    i_bRetract        := fbStationConveyor.q_bAlignRetract,
    i_bExtendedPos    := xAlignExtendedPos,       // 磁环传感器
    i_bRetractedPos   := xAlignRetractedPos,      // 磁环传感器
    i_iTimeoutMs      := 3000,
    i_iDebounceMs     := 50,
    i_iSolenoidType   := 0,
    i_bExtendPolarity := TRUE                     // 极性取反! 弹簧复位气缸
);
yAlignSolenoid := fbAlignCyl.q_bSolenoid;         // 电磁阀输出->物理IO (无需NOT)

// ========== FB_1011 出料气缸 ==========
fbDischargeCyl(
    i_bExtend         := fbStationConveyor.q_bDischargeExtend,
    i_bRetract        := fbStationConveyor.q_bDischargeRetract,
    i_bExtendedPos    := xDischargeExtendedPos,   // 磁环传感器
    i_bRetractedPos   := xDischargeRetractedPos,  // 磁环传感器
    i_iTimeoutMs      := 5000,
    i_iDebounceMs     := 50,
    i_iSolenoidType   := 0,
    i_bExtendPolarity := FALSE                    // 正常极性
);
yDischargeSolenoid := fbDischargeCyl.q_bSolenoid; // 电磁阀输出->物理IO
```

### 7.4 FB_1012调用 (电机执行器)

```scl
// ========== FB_1012 输送电机 ==========
fbConveyorMotor(
    i_bFwdCmd    := fbStationConveyor.q_bFwdCmd,
    i_bRevCmd    := fbStationConveyor.q_bRevCmd,
    i_bSlowCmd   := fbStationConveyor.q_bSlowCmd,
    i_bVfdFault  := xVfdFault,                   // VFD故障输入->物理IO
    i_iCtrlMode  := 0,                           // 端子控制
    i_rSpeed     := 100.0
);
yMotorFwd  := fbConveyorMotor.q_bFwdOut;         // 正转输出->物理IO
yMotorRev  := fbConveyorMotor.q_bRevOut;         // 反转输出->物理IO
yMotorSlow := fbConveyorMotor.q_bSlowOut;        // 慢速输出->物理IO
```

### 7.5 接线拓扑图

```
                    OB1
                     |
    +----------------+----------------+----------------+
    |                |                |                |
 FB_1014          FB_1011          FB_1011          FB_1011          FB_1012
 (编排器)       (进料气缸)       (拍正气缸)       (出料气缸)       (输送电机)
    |                |                |                |                |
    | i_iMode <-- (HMI/上层)          |                |                |
    |                |                |                |                |
    | q_bInfeedExtend---->i_bExtend   |                |                |
    | q_bInfeedRetract--->i_bRetract  |                |                |
    |<---q_bIsExtended    |           |                |                |
    |<---q_bIsRetracted   |           |                |                |
    |                |                |                |                |
    | q_bAlignExtend----------------->i_bExtend        |                |
    | q_bAlignRetract---------------->i_bRetract       |                |
    |<---q_bIsExtended----------------|                |                |
    |<---q_bIsRetracted---------------|                |                |
    |                |                |                |                |
    | q_bDischargeExtend------------------------------>i_bExtend        |
    | q_bDischargeRetract----------------------------->i_bRetract       |
    |<---q_bIsExtended---------------------------------|                |
    |<---q_bIsRetracted--------------------------------|                |
    |                |                |                |                |
    | q_bFwdCmd-------------------------------------------------->i_bFwdCmd
    | q_bRevCmd-------------------------------------------------->i_bRevCmd
    | q_bSlowCmd------------------------------------------------>i_bSlowCmd
    |<---q_bVfdAlarm----------------------------------------------|
    |                |                |                |                |
    |                |->q_bSolenoid   |->q_bSolenoid   |->q_bSolenoid   |->q_bFwdOut
    |                |   (物理IO)      |   (物理IO)      |   (物理IO)      |->q_bRevOut
    |                |                |                |                |->q_bSlowOut
```

## 8. 关联文档

| 文档        | 路径                                                                                                   |
| ----------- | ------------------------------------------------------------------------------------------------------ |
| DSN         | 详细设计说明书_DSN-FB1014-StationConveyor-V6.0.0.md                                                    |
| PFL         | 工艺流程_PFL-FB1014-StationConveyor-V6.0.0.md                                                          |
| FB_1011 IFC | ../FB_1011_CylinderControl/PRD/接口文档_IFC-FB1011-CylinderControl-V9.0.0.md                            |
| FB_1012 IFC | ../FB_1012_ConveyorMotor/PRD/接口文档_IFC-FB1012-ConveyorMotor-V9.0.0.md                                |
| FB_TON      | ../../timer/FB_TON.scl                                                                                 |
| LSP-905     | ../../../../../0100_PLC自动化/00_通用规范/PLC编程/905_SCL编程规范_LSP.md                         |
| LSP-904     | ../../../../../0100_PLC自动化/00_通用规范/PLC编程/904_SCL注释规范_LSP.md                         |
| LSP-903     | ../../../../../0100_PLC自动化/00_通用规范/PLC编程/903_定时器使用规范_LSP.md                       |
| LSP-906     | ../../../../../0100_PLC自动化/00_通用规范/PLC编程/906_错误预防规则_LSP.md                         |

---

## 附：2026-10-22 对齐前的旧说明（留底，不删）

> 2026-10-22 按 `plc docs check` 把上面接口表的“说明”列逐字改成代码行尾注释（代码为准，只改文档，没改 .scl）。
> 下表是改之前文档里的写法，有些比代码注释多写了单位、触发方式或用途，留在这里备查；
> 其中与代码实际行为不一致的地方，见共享库对齐记录 `PRD/文档代码对齐记录_20261022.md` 第 3 节。

| 引脚 | 对齐前文档说明 | 现说明（= 代码注释） |
|------|------|------|
| i_iMode | 运行模式(0=正常/1=B侧双向/2=A侧双向) | 运行模式: 0=正常/1=B侧双向/2=A侧双向 |
| i_xInfeedStart | 入料开始光电(X420, 始终有效) | 入料开始光电(X420) |
| i_xPos1 | 位置1光电(X421, 功能随方向切换) | 位置1光电(X421) |
| i_xPos2 | 位置2光电(X422, 功能随方向切换) | 位置2光电(X422) |
| i_bInfeedIsExtended | 进料气缸已伸出(从FB_1011) | A侧阻挡气缸伸出到位(来自FB_1011) |
| i_bInfeedIsRetracted | 进料气缸已收回(从FB_1011) | A侧阻挡气缸收回到位(来自FB_1011) |
| i_bAlignIsExtended | 拍正气缸已伸出(从FB_1011) | 拍正气缸伸出到位(来自FB_1011) |
| i_bAlignIsRetracted | 拍正气缸已收回(从FB_1011) | 拍正气缸收回到位(来自FB_1011) |
| i_bDischargeIsExtended | 出料气缸已伸出(从FB_1011) | B侧阻挡气缸伸出到位(来自FB_1011) |
| i_bDischargeIsRetracted | 出料气缸已收回(从FB_1011) | B侧阻挡气缸收回到位(来自FB_1011) |
| i_bVfdAlarm | VFD报警(从FB_1012) | VFD报警(来自FB_1012) |
| q_bInfeedExtend | 进料气缸伸出命令 | A侧阻挡气缸伸出命令 |
| q_bInfeedRetract | 进料气缸收回命令 | A侧阻挡气缸收回命令 |
| q_bDischargeExtend | 出料气缸伸出命令 | B侧阻挡气缸伸出命令 |
| q_bDischargeRetract | 出料气缸收回命令 | B侧阻挡气缸收回命令 |
| q_bFwdCmd | 电机正转命令 | 电机正转命令(到FB_1012) |
| q_bRevCmd | 电机反转命令 | 电机反转命令(到FB_1012) |
| q_bSlowCmd | 慢速命令(方向修饰符) | 电机慢速命令(到FB_1012) |
| q_dwProductionCount | 累计产量计数 | 产量计数器 |

### 附：2.10 内部变量表对齐前的写法

| 内部变量 | 对齐前表头第一列 | 对齐前有效值域 | 现值域（按代码） |
|------|------|------|------|
| m_iAlignStep | 名称 | 0~3 | 0~4 |
| m_iDischPrepStep | 名称 | 0~3 | 0~2 |
