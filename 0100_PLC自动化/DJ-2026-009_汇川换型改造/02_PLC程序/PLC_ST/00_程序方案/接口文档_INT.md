# 汇川换型改造 接口设计文档

> **【作废】2026-10-19 按用户确认标作废，文件保留不删。** 本文是脚手架生成的骨架。内容以 `00_项目管理/01_立项与需求/020_DJ-2026-009_需求说明_REQ.md` 和 `02_PLC程序/程序文档/030_DJ-2026-009_通讯契约_INT.md` 为准（业务变更 BC-DJ-2026-009-004）。

> **项目编号**: DJ-2026-009  
> **项目名称**: 汇川换型改造  
> **版本号**: V1.0.0  
> **编制人**:   
> **更新日期**: 2026-08-23  
> **规范依据**: DEV-001 / LSP-907 / PROJ-016  

---

## 1. 全局数据交互总线 (GlobalVars.db)

| 变量名 | 数据类型 | 访问属性 | 功能描述 |
| :--- | :--- | :---: | :--- |
| `stGlobal` | `ST_CommonAlarm` | 读写 | 全局控制、系统工作模式与首出报警字 |
| `stExternal` | `ST_ExternalDevice` | 读写 | 外部机器人、上游/下游总线握手与安全门互锁 |
| `stStation1` | `ST_Station1` | 读写 | 工位1 动作机构控制、状态、气缸与定时器结构体 |
| `astServoAxis` | `ARRAY[1..4] OF ST_ServoAxis` | 读写 | PLCopen MC Part 1 伺服轴状态与控制总线 |

---

## 2. 功能块调度接口规范

所有工站 FB 严格遵循单一 `VAR_IN_OUT` 结构体参数调用规范：
```scl
// OB1.scl 调度调用范例
GlobalVars.fbStation1(io_stStation := GlobalVars.stStation1);
GlobalVars.stStation1 := GlobalVars.fbStation1.io_stStation;
```

---

## 3. FC 调用表（CARD-DJ-2026-009-003 追加，本节有效）

| FC 名 | 调用方 | 用途 |
| :--- | :--- | :--- |
| `FC_3003_CheckModuleId` | `FB_3001_ExternalInteraction` | 组件 ID 合格检查（现只判空） |
