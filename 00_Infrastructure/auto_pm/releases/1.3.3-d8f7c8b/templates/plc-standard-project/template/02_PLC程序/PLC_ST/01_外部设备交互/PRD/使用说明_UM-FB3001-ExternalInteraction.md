---
spec_id: UM-000
title: "FB_3001 使用说明 (UM)"
version: "V1.0.0"
status: "正式"
created: "2026-08-22"
domain: plc
---

# 使用说明 (UM) - FB_3001_ExternalInteraction

## 1. 快速接入指引
1. 在全局数据块中声明 `stExternal: ST_ExternalDevice`；
2. 在 OB1 主循环中按周期调用 `fbExternal(..., io_stExternal := GlobalVars.stExternal)`；
3. 将 `stExternal` 中的输入输出位与现场硬线 I/O 或通讯 DB 块完成变量映射。
