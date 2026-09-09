# FB_2001_CommonAlarm_AllStation 详细设计说明书

## 1. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | 公共报警管理功能块详细设计说明书 |
| **适用FB** | FB_2001_CommonAlarm_AllStation |
| **文档版本** | V9.1.0 |
| **编制日期** | 2026-05-18 |
| **编制人** | Trae |
| **审核人** | [待审核] |
| **遵循规范** | LSP-905_SCL编程规范 |

## 2. 变更记录摘要

> 完整变更历史请参阅: [变更记录_CHG-FB2001-CommonAlarm-V6.0.0.md](./变更记录_CHG-FB2001-CommonAlarm-V6.0.0.md)

| 版本号 | 日期 | 变更内容摘要 | 详细说明链接 |
|--------|------|-------------|-------------|
| **V6.0.0** | **2026-05-18** | **重构: 基于SRC基线重写。3-INT输入→~25 BOOL分类输入, 内置49类报警码优先级扫描, 新增指示灯/蜂鸣器5路输出, 新增MES去重环形队列, 全英文化变量** | [→ V6.0.0变更详情](./变更记录_CHG-FB2001-CommonAlarm-V6.0.0.md#v600) |
| V2.1.0 | 2026-05-04 | 旧版3-INT输入(~20报警码) | 已废弃 |

---

## 3. 功能描述

### 3.1 核心功能

FB_2001_CommonAlarm_AllStation 是一个**纯逻辑功能块**，作为边框缓存机的**全局报警管理中心**：

- **全工站报警汇聚**: 接收~25个BOOL分类报警输入，覆盖安全/输送/取放料/送料/外部五类报警源
- **内置优先级扫描**: 按49类报警码优先级从高到低扫描BOOL输入，直接计算最高优先级报警码(INT)
- **全局报警字计算**: 将报警码转换为WORD类型输出，供HMI报警灯使用
- **MES报警环形队列**: 采用环形缓冲区维护最近10条去重报警记录，供MES系统读取上传
- **新报警脉冲标志**: 检测到新报警时输出单周期脉冲，触发主控进行MES数据上传和蜂鸣器
- **指示灯/蜂鸣器控制**: 输出5路物理信号——绿灯(Y24)/红灯(Y25)/黄灯(Y26)/蜂鸣器(Y27)/复位灯(Y50)
- **完全解耦设计**: 无任何X/Y/M/D物理地址引用，所有数据通过逻辑变量交互

### 3.2 数据流向图

```
┌─────────────────────────────────────────────────────────────────────────┐
│               FB_2001_CommonAlarm_AllStation (纯逻辑块)                   │
│                                                                          │
│    输入 (VAR_INPUT) — 5类~25个BOOL:                                       │
│    ├─ 系统/安全 (9+8+4=21个):                                            │
│    │   ├─ i_bEStopActive              急停(X101)                         │
│    │   ├─ i_bSafetyDoorFault[1..8]    8路安全门                          │
│    │   ├─ i_bHmiStop                  HMI STOP                           │
│    │   ├─ i_bVfdFault[1..4]           4路变频器                          │
│    │   ├─ i_bX1ServoFault             X1伺服故障                         │
│    │   ├─ i_bX2ServoFault             X2伺服故障                         │
│    │   ├─ i_bZServoFault              Z伺服故障                          │
│    │   └─ i_bBusUnhealthy             总线/外设健康位                     │
│    ├─ 输送机 (5×4=20个):                                                 │
│    │   ├─ i_bConvSeparateTimeout[1..4]        L1~L4分料超时              │
│    │   ├─ i_bConvSensorFaultBlockUp[1..4]     阻挡上位冗余不一致         │
│    │   ├─ i_bConvSensorFaultBlockDown[1..4]   阻挡下位冗余不一致         │
│    │   ├─ i_bConvSensorFaultSepUp[1..4]       分料上位冗余不一致         │
│    │   └─ i_bConvSensorFaultSepDown[1..4]     分料下位冗余不一致         │
│    ├─ 取放料 (7个):                                                       │
│    │   ├─ i_bPickClampTimeout / i_bPickLiftTimeout  夹紧/升降超时        │
│    │   ├─ i_bPickProductMissing / i_bPickSensorFault 产品/传感器异常     │
│    │   └─ i_bPickFrameOnPlatform / i_bPickX1Limit / i_bPickZLimit       │
│    ├─ 送料 (3个):                                                         │
│    │   ├─ i_bFeedX2Limit / i_bFeedMoveTimeout / i_bFeedFrameOnPlatform  │
│    ├─ 外部 (3个):                                                         │
│    │   └─ i_bFrameMachineFault / i_bFrameMachineEStop / i_bRobotFault   │
│    └─ i_bReset                         复位                               │
│                                                                          │
│    内部处理:                                                              │
│    ├─ 优先级扫描 (49类码, 按序匹配首个激活BOOL)                           │
│    ├─ 全局报警字计算 (INT→WORD)                                          │
│    ├─ 新报警脉冲检测 (上升沿)                                             │
│    ├─ MES环形队列 (10条去重)                                              │
│    └─ 蜂鸣器定时 (TONR, 2s)                                               │
│                                                                          │
│    输出 (VAR_OUTPUT) — 10个:                                              │
│    ├─ q_wCurrentAlarmCode  WORD     → 主控 → D120 (HMI文本显示)         │
│    ├─ q_wGlobalAlarmWord   WORD     → 主控 → D400 (HMI报警灯指示)       │
│    ├─ q_iAlarmCount        INT      → 主控 → D404 (MES累计统计)         │
│    ├─ q_aMesQueue[0..9]    WORD[10] → 主控 → D406~D425 (MES队列)        │
│    ├─ q_bNewAlarmPulse     BOOL     → 主控 (单周期脉冲, 触发MES上传)     │
│    ├─ q_bLightGreen        BOOL      → IO → Y24 (绿灯-正常运行)           │
│    ├─ q_bLightRed          BOOL      → IO → Y25 (红灯-故障)               │
│    ├─ q_bLightYellow       BOOL      → IO → Y26 (黄灯-待机/等待)          │
│    ├─ q_bBuzzer            BOOL      → IO → Y27 (蜂鸣器-新报警)           │
│    └─ q_bResetLight        BOOL      → IO → Y50 (复位按钮灯)              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 架构定位

### 4.1 在主控系统中的位置

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     主控程序 (PRG_MainControl_DJ2026005)                  │
│                                                                          │
│  Step1: FB_ExternalDeviceInteraction  ──外部设备交互                      │
│  Step2: FB_1001_Conveyor4Layer        ──四层输送机控制                   │
│  Step3: FB_1003_PickPlace             ──取放料机构                       │
│  Step4: FB_1004_GlueMachineFeeder     ──打胶机送料                       │
│                          ↓                                               │
│  Step5: fbCommonAlarm(FB_2001_CommonAlarm_AllStation)                    │
│         各工站/外部/系统BOOL ──→ 扫描 ──→ 报警码 + 指示灯/蜂鸣器          │
│                          ↓                                               │
│  Step6: IO输出映射 (报警灯/蜂鸣器 → Y24~Y27/Y50)                         │
│  Step7: HMI数据回写 (D120/D400/D404/D406~D425)                           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 核心算法设计

### 5.1 报警码优先级扫描算法

```
报警码计算 (每个扫描周期执行):

wAlarmCode := ALM_NONE (WORD#16#0000);

┌─────┬──────────────────────────────────────────────────────────┐
│优先级│ 扫描项                  │ 报警码(WORD)│ 说明             │
├─────┼──────────────────────────┼─────────┼───────────────────────┤
│  0  │ i_bEStopActive          │    1    │ 急停                   │
│  1  │ i_bSafetyDoorFault[1..8]│  2~9    │ 安全门1~8              │
│  2  │ i_bX1ServoFault         │   11    │ X1伺服故障             │
│     │ i_bX2ServoFault         │   12    │ X2伺服故障             │
│     │ i_bZServoFault          │   13    │ Z伺服故障              │
│  3  │ i_bHmiStop              │   14    │ HMI STOP按鈕           │
│  4  │ i_bVfdFault[1..4]       │ 15~18   │ 变频器1~4故障          │
│  5  │ i_bFrameMachineFault    │  110    │ 组框机故障/急停        │
│     │ i_bFrameMachineEStop    │  110    │ (同码)                 │
│  6  │ i_bBusUnhealthy         │  120    │ 总线/外设不健康        │
│  7  │ ConvSensorFaultBlockUp  │ 31~34   │ L1~L4阻挡上位冗余不一致│
│     │ ConvSensorFaultSepDown  │ 51~54   │ L1~L4分料下位冗余不一致│
│  8  │ i_bPickSensorFault      │   71    │ 取放料传感器冗余不一致 │
│     │ i_bPickProductMissing   │   72    │ 取放料产品检测失败     │
│     │ i_bPickFrameOnPlatform  │   80    │ 取料平台有边框         │
│     │ i_bPickX1Limit          │   81    │ X1轴限位               │
│     │ i_bPickZLimit           │   82    │ Z轴限位                │
│  9  │ i_bFeedFrameOnPlatform  │   82    │ 送料平台有边框         │
│     │ i_bFeedX2Limit          │   91    │ X2轴限位               │
│ 10  │ ConvSeparateTimeout[1..4]│100~103 │ L1~L4分料超时          │
│  -  │ i_bRobotFault           │  115    │ 机器人故障             │
└─────┴──────────────────────────┴─────────┴───────────────────────┘

算法特性:
  - 低码优先: 一旦匹配到首个激活报警(对应当前最高优先级), 立即停止后续扫描
  - ALM_NONE守卫: 每层扫描都以 iAlarmCode=ALM_NONE 作为判断条件, 不覆盖已匹配的高优先级码
  - 同码复用: 组框机故障和急停共用110, PickZLimit和FeedFrameOnPlatform共用82
```

### 5.2 全局报警字计算算法

```
全局报警字计算 (每个扫描周期执行):

IF iAlarmCode <> ALM_NONE THEN
    wGlobalAlarmWord := INT_TO_WORD(iAlarmCode);
ELSE
    wGlobalAlarmWord := 0;
END_IF;

含义:
  - V6.0.0中报警字等于报警码的直接WORD转换(非OR组合)
  - 因为V6.0.0已内置优先级选取, 每次只输出一个报警码
  - 非零值表示至少有一个报警激活
  - 写入D400供HMI判断是否有报警(用于驱动报警灯)
```

### 5.3 新报警脉冲检测算法

```
脉冲检测 (每个扫描周期执行):

bAnyAlarm := (iAlarmCode <> ALM_NONE);

IF bAnyAlarm AND NOT bPrevAnyAlarm THEN
    bNewAlarmPulse := TRUE;          (* 上升沿: 从无报警→有报警 *)
    iAlarmCount := iAlarmCount + 1;  (* MES累计+1 *)
ELSIF NOT bAnyAlarm THEN
    bNewAlarmPulse := FALSE;         (* 无报警时清除脉冲 *)
END_IF;
bPrevAnyAlarm := bAnyAlarm;

含义:
  - bNewAlarmPulse仅在一个扫描周期内为TRUE
  - 触发条件: 上一周期无任何报警, 本周期出现报警(包括优先级切换不触发)
  - iAlarmCount持续累加, 不复位则不清零
```

### 5.4 MES报警环形队列算法

```
环形队列操作流程:

检测到新报警(bAnyAlarm AND bNewAlarmPulse)时:
  1. 去重检查: 遍历队列[0..9], 检查iAlarmCode是否已存在
  2. 若已存在 → 跳过, 不入队
  3. 若不存在 → 写入aMesQueue[iQueueIndex], iQueueIndex++
  4. iQueueIndex溢出处理: IF iQueueIndex > 9 THEN iQueueIndex := 0;

与V5.0.0移位法的区别:
  - V5.0.0: 移位法 - 所有元素后移, 新码写入[0], [9]丢弃
  - V6.0.0: 环形缓冲区 - 按序写入, 写满后循环覆盖最早记录

复位操作(i_bReset=TRUE):
  - iAlarmCode := 0; wGlobalAlarmWord := 0
  - iAlarmCount := 0; iQueueIndex := 0
  - bNewAlarmPulse := FALSE; bPrevAnyAlarm := FALSE
  - aMesQueue[0..9]全部清零
  - 蜂鸣器: tR:=TRUE 停止
  - RETURN (跳过本周期后续所有逻辑)
```

### 5.5 指示灯/蜂鸣器控制算法

```
指示灯逻辑 (每个扫描周期):

bLightRed   := bAnyAlarm;          (* 任何故障→红灯 *)
bLightYellow := NOT bAnyAlarm;      (* 无故障→黄灯(待机/等待) *)
bLightGreen := NOT bAnyAlarm;       (* 无故障→绿灯(正常运行) *)
q_bResetLight := i_bReset;          (* 复位按钮灯直通输入 *)

蜂鸣器逻辑 (TONR, PT=2000ms):

IF bNewAlarmPulse THEN
    bBuzzer := TRUE;               (* 新报警→启动蜂鸣 *)
    tPt := T_BUZZER_DEFAULT(2000); (* 定时2s *)
    tIn := TRUE; tR := FALSE;
END_IF;

IF tQ THEN                         (* 定时到 *)
    bBuzzer := FALSE;              (* 关闭蜂鸣 *)
    tIn := FALSE; tR := TRUE;      (* 复位定时器 *)
END_IF;

含义:
  - 红灯/绿灯/黄灯互斥: 有报警→红灯, 无报警→绿+黄同时亮
  - 蜂鸣器: 新报警触发后响2s自动关闭; TONR为保持型定时器
  - 蜂鸣器不随故障持续而持续响, 仅在"新报警出现"的2s内响起
```

---

## 6. D区地址分配表

| D地址 | 位宽 | 来源变量 | 说明 |
|-------|------|----------|------|
| **D120** | WORD (16bit) | q_wCurrentAlarmCode | 当前最高优先级报警码数值(HMI文本显示) |
| **D400** | WORD (16bit) | q_wGlobalAlarmWord | 报警码WORD形式(非零即有报警) |
| **D404** | INT (16bit) | q_iAlarmCount | 自上次复位以来的累计报警次数 |
| **D406~D425** | 10×INT (160bit) | q_aMesQueue[0..9] | MES报警环形队列(按写入顺序, 最新覆盖最旧) |

---

## 7. 相关文档链接

### 7.1 本FB文档体系

| 文档类型 | 文档名称 | 说明 |
|---------|:--------|:-----|
| **详细设计说明书 (DSN)** | 本文档 | BOOL输入分类、49类报警码优先级扫描、环形队列、指示灯/蜂鸣器算法 |
| **接口文档 (IFC)** | [接口文档_IFC-FB2001-CommonAlarm-V6.0.0.md](./接口文档_IFC-FB2001-CommonAlarm-V6.0.0.md) | ~25输入/10输出的完整接口定义 |
| **使用说明 (UM)** | [使用说明_UM-FB2001-CommonAlarm-V6.0.0.md](./使用说明_UM-FB2001-CommonAlarm-V6.0.0.md) | ST调用示例、调试指南、常见问题排查 |
| **变更记录 (CHG)** | [变更记录_CHG-FB2001-CommonAlarm-V6.0.0.md](./变更记录_CHG-FB2001-CommonAlarm-V6.0.0.md) | 版本历史、变更台账 |

### 7.2 关联FB文档

| FB名称 | 文档路径 | 关系说明 |
|--------|:---------|:--------|
| FB_1001_Conveyor4Layer (四层输送机) | `../四层输送机/` | 提供输送机BOOL报警输入 |
| FB_1003_PickPlace (取放料机构) | `../取放料机构/` | 提供取放料BOOL报警输入 |
| FB_1004_GlueMachineFeeder (打胶机送料) | `../送料机构/` | 提供送料BOOL报警输入 |
| FB_3001_ExternalDeviceInteraction | `../external/` | 提供急停/安全门/总线/组框机/机器人BOOL输入 |

### 7.3 项目级文档

| 文档名称 | 路径 | 说明 |
|---------|:-----|:-----|
| PLC程序设计总文档 | `../../程序文档/016_DJ-2026-005_PLC程序设计总文档_PLC.md` | 整体架构说明 |
| PLC变量定义文档 | `../../程序文档/PLC变量定义文档_VAR-DJ-2026-005.md` | 全局D/M区变量定义(含D120/D400/D404/M200等) |

---

## 附录: 特殊设计决策记录

| 决策ID | 决策内容 | 原因 | 替代方案(未采用) |
|:------:|:---------|:-----|:---------------|
| D001 | 采用独立FB而非分散在各工站中 | 职责单一, 易于维护和扩展 | 分散在各工站(增加耦合度, 逻辑复杂) |
| D002 | V6.0.0采用BOOL输入+内置优先级扫描 | 各工站FB无需感知报警码体系, 降低耦合; 报警码集中管理 | 延续V5.0.0的INT输入(各工站需自己算码) |
| D003 | 低码优先(数值越小越紧急) | 急停=1, 安全门=2~9, 符合安全优先级直觉 | 高码优先(不符合安全行业惯例) |
| D004 | MES队列采用环形缓冲区(非移位法) | 代码简洁, 保留最近10条且明确覆盖顺序 | 移位法(每次入队需移动9个元素, ST语言开销大) |
| D005 | 使用去重策略 | 避免同一报警反复入队占满队列 | 不去重(可能导致10条全为同一报警码) |
| D006 | 新报警脉冲标志 | 上升沿触发, 让主控只需检测TRUE即可触发MES上传 | 持续标志(需要主控自己处理边沿) |
| D007 | 蜂鸣器使用TONR保持型定时器 | 新报警响2s后自动停; TONR保持累计, 适合脉冲触发的延时场景 | TP脉冲定时器(每次需重触, 不适合单次脉冲) |
| D008 | 红灯/绿灯/黄灯基于bAnyAlarm | 简单明确, 3灯覆盖设备运行/待机/故障三态 | 基于全局报警字各位(过于复杂, V5.0.0方案) |

---

**文档版本**: V6.0.0
**最后更新**: 2026-05-18
**下次审查日期**: [待定]
