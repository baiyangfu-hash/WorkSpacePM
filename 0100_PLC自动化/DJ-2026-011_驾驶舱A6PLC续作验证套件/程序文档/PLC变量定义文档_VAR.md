# PLC变量定义文档（VAR）- DJ-2026-011 驾驶舱A6PLC续作验证套件

> 项目编号: DJ-2026-011
> 项目名称: 驾驶舱A6PLC续作验证套件
> 版本: V1.1.1
> 创建日期: 2026-10-22
> 覆盖范围: DB_TwoHandStartTest、DB_AlarmSummaryTest

## 1. 变量命名约定

- 功能块实例使用 `fb_` 前缀，测试激励使用 `s_` 前缀，输出结果使用 `s_` 前缀。
- 布尔量使用 `b` 类型标识，整型使用 `i` 类型标识，数组使用 `arr` 类型标识。
- 变量名使用英文小驼峰，注释使用中文与英文半角标点。

## DB_TwoHandStartTest

| 变量名 | 类型 | 说明 |
|--------|------|------|
| fb_TwoHandStart | FB_1091_TwoHandStart_DJ2026011 | 被测功能块实例 |
| s_bStartLeft | BOOL | 测试激励: 左启动按钮 |
| s_bStartRight | BOOL | 测试激励: 右启动按钮 |
| s_dSyncWindowMs | DINT | 同步窗口毫秒值, 500 = 0.5s |
| s_bStartOutput | BOOL | 结果: 双手启动输出 |
| s_bSyncFault | BOOL | 结果: 同步故障 |

## DB_AlarmSummaryTest

| 变量名 | 类型 | 说明 |
|--------|------|------|
| fb_AlarmSummary | FB_2001_AlarmSummary_DJ2026011 | 被测报警汇总功能块实例 |
| s_arrAlarms | ARRAY[1..16] OF BOOL | 测试激励: 16 路报警输入, 第 1 路由 OB1 接同步故障 |
| s_bReset | BOOL | 测试激励: 复位按钮 |
| s_bAlarmLamp | BOOL | 结果: 报警灯 |
| s_bAnyAlarm | BOOL | 结果: 报警汇总 |

## 2. 变更记录

| 日期 | 版本 | 变更内容 | 变更人 |
|------|------|---------|--------|
| 2026-10-22 | V1.1.0 | 新增 DB_AlarmSummaryTest 变量定义，补充 DB_TwoHandStartTest 现有变量 | trae |
| 2026-10-22 | V1.1.1 | 对象标题改为纯对象名，供文档一致性检查按标题定位变量表 | trae |
