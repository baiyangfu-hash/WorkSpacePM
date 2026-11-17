# GlobalVars.scl 详细设计说明书

> **现行（2026-11-15，CHG-PLC-2026-022）**：各功能块经自己的背景数据块调用（如 `"DB_1001_MachineMode_DJ005"(...)`），GlobalVars 不再含 FB 实例，源文件改为 `GlobalVars.scl`；现行接口以 `00_程序方案/接口文档_INT.md` 4.1 与 `OB1.scl` 为准，下文旧版本内容只作历史。


## 1. 文档基础信息

| 属性 | 值 |
|------|-----|
| **文档标题** | 全局变量数据块详细设计说明书 |
| **适用DB** | GlobalVars.scl（2026-11-15 前为 GlobalVars.db） |
| **文档版本** | V9.1.0 |
| **编制日期** | 2026-08-02 |
| **编制人** | fubai |
| **审核人** | [待审核] |
| **遵循规范** | LSP-905_SCL编程规范 |

## 2. 功能描述

GlobalVars.db 是边框缓存机 PLC 程序的全局变量数据块，作为 OB1 与各 FB 之间的数据交换中心。所有功能块通过 VAR_IN_OUT 结构体整块传递，OB1 仅负责按工艺流顺序调度各 FB 并传递对应的结构体实例。

## 3. 结构体定义

### 3.1 stGlobal — 全局系统变量

| 变量名 | 类型 | 说明 |
|--------|------|------|
| bAutoMode | BOOL | 自动模式使能 |
| bManualMode | BOOL | 手动模式使能 |
| bStop | BOOL | 停止信号 |
| bEStop | BOOL | 急停信号 |
| bSystemReady | BOOL | 系统就绪 |
| wCurrentAlarmCode | WORD | 当前报警码 |
| aMesQueue | ARRAY[0..9] OF WORD | MES 报警去重队列 |

### 3.2 stConveyor — 输送机结构体 (FB_1002, V11.0.0)

包含 9 步 Step_S 状态机所需全部输入输出，结构体通过 VAR_IN_OUT io_stLayer 整块传递给 FB_1002。详见 [接口文档_IFC-FB1002-SingleLayerConveyor.md](../../02_输送机/PRD/接口文档_IFC-FB1002-SingleLayerConveyor.md)。

### 3.3 stPickPlace — 取放料结构体 (FB_1003, V8.0.0)

6 步 S20~S25 状态机，包含 Z 轴/X1 轴伺服轴结构体、4 夹爪控制、按层选放料点逻辑。详见 [接口文档_IFC-FB1003-PickPlace.md](../../03_取放料/PRD/接口文档_IFC-FB1003-PickPlace.md)。

### 3.4 stGlueFeeder — 打胶机送料结构体 (FB_1004, V7.0.0)

4 步 D760 状态机，X2 轴横移+打胶机交互。详见 [接口文档_IFC-FB1004-GlueMachineFeeder.md](../../04_打胶机送料/PRD/接口文档_IFC-FB1004-GlueMachineFeeder.md)。

### 3.5 stAlarm — 公共报警结构体 (FB_2001, V3.0.0)

49 类报警码，5 路指示灯/蜂鸣器。详见 [接口文档_IFC-FB2001-CommonAlarm.md](../../05_公共报警/PRD/接口文档_IFC-FB2001-CommonAlarm.md)。

### 3.6 stExternal — 外部设备交互结构体 (FB_External, V4.1.0)

8 路安全门+急停+总线健康。详见 [接口文档_IFC-FB3001-ExternalDeviceInteraction.md](../../01_外部设备交互/PRD/接口文档_IFC-FB3001-ExternalDeviceInteraction.md)。

## 4. 数据流

```
OB1
 ├─ stConveyor  ──→ FB_1002 (VAR_IN_OUT io_stLayer)
 ├─ stPickPlace ──→ FB_1003 (VAR_IN_OUT io_stZAxis, io_stX1Axis, ...)
 ├─ stGlueFeeder──→ FB_1004 (VAR_IN_OUT io_stX2Axis, ...)
 ├─ stAlarm    ──→ FB_2001 (VAR_INPUT)
 └─ stExternal ──→ FB_External (VAR_INPUT)
```

## 5. 版本演进

| 版本 | 日期 | 说明 |
|------|------|------|
| V7.0.0 | 2026-05-18 | Conveyor 子系统 V7.0.0 重构对齐 |
| V6.0.0 | 2026-05-17 | 基于 SRC 基线重写，全部 5 个 STRUCT 同步新 FB 接口 |
| V3.0.0 | 2026-04-27 | 初始版本 |

> 完整变更历史请参阅: [变更记录_CHG-GlobalVars.md](./变更记录_CHG-GlobalVars.md)