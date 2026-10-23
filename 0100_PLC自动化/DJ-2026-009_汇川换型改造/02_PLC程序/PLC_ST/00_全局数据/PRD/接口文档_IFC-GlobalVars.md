---
spec_id: INT-800
title: "DJ-2026-009 GlobalVars 全局数据块接口文档 (IFC)"
version: "V1.0.0"
status: "正式"
created: "2026-08-23"
domain: plc
---

# 接口文档 (IFC) - DJ-2026-009 汇川换型改造 GlobalVars

## 1. 模块定位
遵循 `STD-901` 与 `LSP-905` 规范，作为全机 OB1 与各工位功能块之间的数据交换总线，实施结构体整块传递。

## 2. 结构体定义
- `stGlobal`: 全局系统控制与报警 (ST_CommonAlarm)
- `stExternal`: 外部交互总线 (ST_ExternalDevice)
- `astServoAxis`: 伺服驱动轴数组 (ST_AxisPos)

## 3. 待在 GlobalVars 里补声明的变量

GlobalVars 的声明不在仓库里，导入 InoProShop 工程时按下表补（类型和说明见 `02_PLC程序/程序文档/PLC变量定义文档_VAR.md` 第 3.6 节）。

| 变量 | 来源卡 | 备注 |
|:---|:---|:---|
| `fbModbusClient`、`awModbusUpRead` / `awModbusUpWrite` / `awModbusDownRead` / `awModbusDownWrite`、`bModbusEnable`、`bModbusUpLinkOK` / `bModbusDownLinkOK` | CARD-DJ-2026-009-001 | 见 FB_3002 接口文档第 5 节 |
| `sMachineModuleID` | CARD-DJ-2026-009-003 | **VAR_GLOBAL RETAIN（断电保持）** |
| `stModuleIdHmi` | CARD-DJ-2026-009-003 | 建议 RETAIN（时间参数要保持） |
| `bExtAllowInfeedAct`、`bExtAllowOutfeedAct`、`bExtUpstreamDone`、`bExtDownstreamDone`、`bExtComAlarm`、`wExtErrorCode` | CARD-DJ-2026-009-003 | FB_3001 输出 |
| `fbSafety`（类型 `FB_1030_SafetyManager`，共享库） | CARD-DJ-2026-009-004 | 安全区；安全 IO 和入参数组不放 GlobalVars，见 `00_全局数据/GVL_SafetyIO.st`（导入时新建 GVL `GVL_SafetyIO` 粘入） |
