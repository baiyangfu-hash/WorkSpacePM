---
spec_id: CHG-800
title: "DJ-2026-009 GlobalVars 全局数据块变更记录 (CHG)"
version: "V1.0.0"
status: "正式"
created: "2026-08-23"
domain: plc
---

# 变更记录 (CHG) - DJ-2026-009 汇川换型改造 GlobalVars

- V1.0.0 (2026-08-23): 初始创建，建立全工站结构体整块传递数据总线。
- V1.1.0 (2026-10-21，预做分支 `claude/dj009-card003`): CARD-DJ-2026-009-003 草稿新增本机 ID `sMachineModuleID`（断电保持）、HMI 结构体 `stModuleIdHmi` 和 FB_3001 输出接线变量，见接口文档第 3 节。
- V1.2.0 (2026-10-22，预做分支 `claude/safety-manager-card004`): CARD-DJ-2026-009-004 草稿新增 `fbSafety : FB_1030_SafetyManager`（GlobalVars）；安全 IO 单独放全局变量表 `00_全局数据/GVL_SafetyIO.st`（`ESTOP_OK AT %IX0.0` 等，安全区整文件）。
