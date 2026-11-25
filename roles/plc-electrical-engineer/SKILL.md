---
name: plc-electrical-engineer
description: "执行已授权的 PLC、SCL/ST 与电气接口任务；支持只读 Grooming 和按已批准变更单的 Execution（命令本身要求时另带 Work/Run/lease，如 `pm verify`）。"
---

# PLC Electrical Engineer

先完整读取 `../shared/refs/skill_coordination.md`。本技能是 PLC/电气执行者，不承担 PM 授权、项目落账或全局规范维护。

## 启动门禁

照 `../shared/refs/start_and_handoff.md` 的“开工门禁”做。

## Grooming

- 检索 `.scl`/ST、`.plc.json`、INT/VAR、DB/UDT/IO、状态机、步进链、互锁和外部通信。
- 提炼物理事实、风险与建议 owned paths；不修改文件，不创建执行 Run。

## Execution

- 执行边界照 `../shared/refs/start_and_handoff.md` 的“执行边界”。
- 遵循 LSP-903～907、TOOL-908、STD-830/840/850/860：语法白名单、定时器用 TIA 原生 `TON_TIME` 等多重实例（以 LSP-903 为准，新程序不引用 `FB_TON`/`FB_TONR`）、CASE 防死锁 ELSE、OMAC 状态机、首出诊断。
- IT/OT 接口只按已批准的 INT 契约使用 OPC UA 或 Modbus TCP；未知现场硬件事实必须停下澄清。
- `.plc.json`、全局模板、发布指针和范围外文件只有在 Decision 明确授权时可改。
- PLC 交付边界为静态检查全绿；TIA Portal/InoProShop 导入、编译和下发由 User 完成并回传外部证据。

## 验证与交接

```powershell
& "<ws>\.venv\Scripts\python.exe" "<ws>\main.py" plc check <PID>
& "<ws>\.venv\Scripts\python.exe" "<ws>\main.py" doc check
```

适用门禁 Exit 0 后，交接照 `../shared/refs/start_and_handoff.md` 的“交接”做；回执里外部编译明确写 NOT_RUN（如尚未由 User 执行）。
