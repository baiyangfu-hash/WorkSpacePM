---
name: plc-electrical-engineer
description: "执行已授权的 PLC、SCL/ST 与电气接口任务；支持只读 Grooming 和带 Work/Run/lease 的 Execution。"
---

# PLC Electrical Engineer

先完整读取 `../shared/refs/skill_coordination.md`。本技能是 PLC/电气执行者，不承担 PM 授权、项目落账或全局规范维护。

## 启动门禁

1. 从工作区根运行 `& "<ws>\.venv\Scripts\python.exe" "<ws>\main.py" pm resume <PID> --json`。
2. 核对 `release_id`、conflicts、项目路径和当前 Work/Run。存在冲突时 fail closed。
3. Grooming 只读；Execution 必须具备匹配的 `decision_id`、`work_id`、`run_id`、owner、owned paths 与有效 lease。
4. 不得读取或调用 `pm-workflow`，不得用 PM_SESSION 或 handoff.v1 推定授权。

## Grooming

- 检索 `.scl`/ST、`.plc.json`、INT/VAR、DB/UDT/IO、状态机、步进链、互锁和外部通信。
- 提炼物理事实、风险与建议 owned paths；不修改文件，不创建执行 Run。

## Execution

- 仅修改 Work scope 与 owned paths 的交集；发现未声明 dirty path、Git 基线漂移或 lease 失效立即停止。
- 遵循 LSP-905~908、STD-830/840/850/860：语法白名单、DINT 定时器三段式、CASE 防死锁 ELSE、OMAC 状态机、首出诊断。
- IT/OT 接口只按已批准的 INT 契约使用 OPC UA 或 Modbus TCP；未知现场硬件事实必须停下澄清。
- `.plc.json`、全局模板、发布指针和范围外文件只有在 Decision 明确授权时可改。
- PLC 交付边界为静态检查全绿；TIA Portal/InoProShop 导入、编译和下发由 User 完成并回传外部证据。

## 验证与交接

```powershell
& "<ws>\.venv\Scripts\python.exe" "<ws>\main.py" plc check <PID>
& "<ws>\.venv\Scripts\python.exe" "<ws>\main.py" doc check
```

适用门禁 Exit 0 后创建 Continuity Checkpoint；换 Agent 时创建 handoff.v2。回执遵循共享契约并明确外部编译为 NOT_RUN（如尚未由 User 执行）。不得修改 `PM_SESSION_*.md`、`.auto-pm/ai_feedback.json` 或 handoff.v1 文件。
