# OB1 主程序组织块接口文档

## 1. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | OB1主程序组织块接口文档 |
| **适用组件** | OB1 (主程序组织块) |
| **文档类型** | 接口文档 / Interface Document (IFC) |
| **文档版本** | V9.1.0 |
| **编制日期** | 2026-05-20 |
| **编制人** | Trae |
| **审核人** | [待审核] |
| **遵循规范** | `LSP-905_SCL编程规范` |

---

## 2. 功能概述

OB1是边框缓存机的**主程序组织块**，负责：
- 各工站功能块实例化与调用调度（纯调度，不含业务逻辑）
- GlobalVars数据块作为统一I/O映射中心
- 工站间信号转发（PickPlace→Feeder）
- 汇总逻辑计算（Conveyor 4层OR/MIN）
- 后处理逻辑（PickPlace双电磁阀Release=NOT Action）

---

## 3. 程序架构

```
┌─────────────────────────────────────────────────────────────┐
│                      OB1 主程序组织块 (V7.1.1)                │
├─────────────────────────────────────────────────────────────┤
│  Step 1: fbExternalDevice (FB_ExternalDeviceInteraction)    │
│          ← stExternal.i_* (27输入) → stExternal.o_* (20输出) │
│                                                                 │
│  Step 2: fbConveyor_L1~L4 (4×FB_1002 展开)                   │
│          ← stConveyor.i_* → stConveyor.o_*                  │
│          + 汇总: q_bRunning(OR) / q_bFault(OR) / q_iAlarmCode(MIN)│
│                                                                 │
│  Step 3: fbPickPlace (FB_1003 V7.0.0)                        │
│          ← stPickPlace.i_* → stPickPlace.o_*                │
│          + VAR_IN_OUT: io_stZAxis => astServoAxis[1]         │
│          + VAR_IN_OUT: io_stX1Axis => astServoAxis[2]        │
│          + 后处理: o_*_Release := NOT o_*_Action            │
│                                                                 │
│  Step 4: 工站间信号: Feeder.i_PickPlace_FeedComplete          │
│          := PickPlace.o_PlaceComplete_ToFeeder               │
│                                                                 │
│  Step 5: fbGlueFeeder (FB_1004 V6.0.0)                       │
│          ← stFeeder.i_* → stFeeder.o_*                      │
│                                                                 │
│  Step 6: fbCommonAlarm (FB_2001 V6.0.0)                      │
│          ← 各站报警码 → stGlobal.o_*                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 功能块调用关系

| 调用顺序 | FB名称 | 版本 | 功能描述 | 输入来源 | 输出去向 |
|:-------:|--------|:----:|----------|----------|----------|
| 1 | FB_ExternalDeviceInteraction | V4.1.0 | 外部设备交互(组框机/打胶机/机器人/安全) | GlobalVars.stExternal (27in) | GlobalVars.stExternal (20out) |
| 2 | FB_1002 ×4 (L1~L4展开) | V7.0.0 | 四层输送机控制(每层独立Step_S状态机) | GlobalVars.stConveyor (逐层ARRAY索引, 22in/11out per layer) | GlobalVars.stConveyor (逐层ARRAY + 3个汇总标量) |
| 3 | FB_1003_PickPlace | V7.0.0 | 取放料机构(6步S20~S25状态机+PLCopen MC) | GlobalVars.stPickPlace (38in) + VAR_IN_OUT轴引用(2) | GlobalVars.stPickPlace (16out) |
| 4 | FB_1004_GlueMachineFeeder | V6.0.0 | 打胶机送料(4步D760状态机) | GlobalVars.stFeeder (14in含工站间信号) | GlobalVars.stFeeder (14out) |
| 5 | FB_2001_CommonAlarm | V6.0.0 | 公共报警管理(49类报警+指示灯+MES队列) | Conveyor/PickPlace/Feeder报警 + Reset | GlobalVars.stGlobal (16out) |

---

## 5. 关键接线说明

### 5.1 FB_1003 VAR_IN_OUT 轴引用 (V7.0.0新增)

```
fbPickPlace(
    ...
    (* V7.0.0: VAR_IN_OUT 必须在VAR_OUTPUT之前声明 *)
    io_stZAxis   => GlobalVars.astServoAxis[1],    // Z轴(升降)
    io_stX1Axis  => GlobalVars.astServoAxis[2],     // X1轴(取放料横移)

    q_bFrontClamp   => GlobalVars.stPickPlace.o_bFrontClamp_Action,
    ...
);
```

### 5.2 i_iPickLayer 接线变更 (V7.1.1修复)

```
(* V7.1.1前 - 反馈回路(有Bug): *)
i_iPickLayer := GlobalVars.stPickPlace.o_iCurrentPickLayer;  // ❌ 输出→输入

(* V7.1.1后 - 独立输入(已修复): *)
i_iPickLayer := GlobalVars.stPickPlace.i_iPickLayer_Input;      // ✅ HMI独立指定
```

### 5.3 PickPlace 后处理 — 双电磁阀松开输出

```
(* OB1后处理: Release = NOT Action (双电磁阀互锁) *)
GlobalVars.stPickPlace.o_bFrontClamp_Release  := NOT GlobalVars.stPickPlace.o_bFrontClamp_Action;
GlobalVars.stPickPlace.o_bRearClamp_Release   := NOT GlobalVars.stPickPlace.o_bRearClamp_Action;
GlobalVars.stPickPlace.o_bFrontClamp2_Release := NOT GlobalVars.stPickPlace.o_bFrontClamp2_Action;
GlobalVars.stPickPlace.o_bRearClamp2_Release   := NOT GlobalVars.stPickPlace.o_bRearClamp2_Action;
```

### 5.4 Conveyor 汇总逻辑

```
(* 4层运行中 OR *)
stConveyor.q_bRunning := q_aLayerRunning[1] OR q_aLayerRunning[2]
                     OR q_aLayerRunning[3] OR q_aLayerRunning[4];

(* 4层故障 OR *)
stConveyor.q_bFault := q_aLayerFault[1] OR q_aLayerFault[2]
                 OR q_aLayerFault[3] OR q_aLayerFault[4];

(* 4层报警码 MIN优先级 *)
IF q_aLayerAlarmCode[1] > 0 THEN q_iAlarmCode := q_aLayerAlarmCode[1]; END_IF;
(* L2/L3/L4: 仅当更小时更新... *)
```

### 5.5 工站间信号流

```
PickPlace ──o_bPlaceComplete_ToFeeder──→ Feeder.i_bPickPlace_FeedComplete
                                          ↓
                                    Feeder (D760状态机)
                                          ↓
                              o_bAllowPickup / o_bSafetyZoneSignal
```

---

## 6. 数据区映射

### 6.1 GlobalVars.db 结构体总览

| 结构体 | 用途 | 变量数 | 对应FB |
|--------|------|:-----:|-------|
| stGlobal | 全局控制+报警 | 16 | FB_2001 |
| stExternal | 外部设备交互 | 47 (27in+20out) | FB_External |
| stConveyor | 四层输送机(含汇总) | 33+3=36 | 4×FB_1002 |
| stPickPlace | 取放料机构 | 56 (53in+3out? 实际53+3out后处理) | FB_1003 |
| stFeeder | 打胶机送料 | 35 (21in+14out) | FB_1004 |
| astServoAxis[1..3] | 伺服轴数组 | 3×ST_ServoAxis | FB_1003/FB_1004(预留) |
| fb* (7个实例) | 功能块实例 | 7 | 各FB实例化 |

### 6.2 HMI关键地址

| 地址 | 变量 | 说明 |
|------|------|------|
| D400 | stGlobal.o_wGlobalAlarmWord | 全局报警字 |
| D402 | stGlobal.o_iCurrentAlarmCode | 最高优先级报警码 |
| D404 | stGlobal.o_iMESAlarmCount | MES报警计数 |
| D406-D425 | stGlobal.o_iMESAlarmQueue[0..9] | MES报警队列 |
| M200 | stGlobal.o_bAnyAlarmActive | 全局互锁 |
| D102 | stPickPlace.i_rZAxisSpeed | Z轴速度 |
| D103 | stPickPlace.i_rX1AxisSpeed | X1轴速度 |
| D104 | stPickPlace.i_iClampConfirmTime | 夹紧确认时间 |
| D105 | stPickPlace.i_iLiftActionTime | 升降超时 |
| D121 | stPickPlace.o_iCurrentPickLayer | 当前取料层 |
| D126 | stPickPlace.o_iCurrentState | 取放料步序 |

---

## 7. 版本历史

| 版本号 | 日期 | 变更内容 |
|--------|------|----------|
| **V7.1.1** | **2026-05-20** | **Bug修复**: TC11 i_iPickLayer输入源从o_iCurrentPickLayer(输出反馈回路)改为i_iPickLayer_Input(独立输入), 断开FB内部覆盖问题 |
| **V7.1.0** | **2026-05-20** | **FB_1003 V7.0.0集成**: 新增VAR_IN_OUT io_stZAxis/io_stX1Axis=>astServoAxis[1..2]; GlobalVars.db新增astServoAxis[1..3]数组 |
| **V7.0.0** | **2026-05-18** | **Conveyor重构**: FB_1001容器取消, 展开调用4×FB_1002(L1~L4); 新增汇总逻辑(q_bRunning/q_bFault/q_iAlarmCode); 下游引用更新(PickPlace取q_aLayerFeedDone) |
| V6.0.1 | 2026-05-18 | 修复: 所有GlobalVars成员引用对齐DB实际定义(stExternal 27in/20out, stConveyor 34in/30out, stPickPlace 51in/20out等) |
| V6.0.0 | 2026-05-18 | Phase 3全部重写: 同步所有FB到V6.0.0新接口, 变量名100%英文 |
| V5.0.0 | 2026-05-04 | 接口变量名100%英文化, 与GlobalVars.db V3.0.0同步 |
