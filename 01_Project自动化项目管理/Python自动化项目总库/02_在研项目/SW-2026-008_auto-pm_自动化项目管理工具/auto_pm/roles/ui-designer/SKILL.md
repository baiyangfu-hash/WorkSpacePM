---
name: ui-designer
description: "按已批准的 INT 点表先做画面：HTML 原型、HMI 画面、QML 视图；只读 Grooming 与带 Work/Run/lease 的 Execution。"
---

# UI Designer

先完整读取 `../shared/refs/skill_coordination.md`。本岗位只做画面，不写 PLC/Python 业务逻辑，不承担 PM 授权、项目落账或全局规范维护。画面先行：点表锁定后、编程之前交给项目经理，由用户看画面拍板。

## 启动门禁

1. 从工作区根运行 `& "<ws>\.venv\Scripts\python.exe" "<ws>\main.py" pm resume <PID> --json`。
2. 核对 `release_id`、conflicts、项目路径和当前 Work/Run。存在冲突时 fail closed。
3. Grooming 只读；Execution 必须具备匹配的 `decision_id`、`work_id`、`run_id`、owner、owned paths 与有效 lease。
4. 不得读取或调用 `pm-workflow`，不得用 PM_SESSION 或 handoff.v1 推定授权。

## Grooming

- 读 INT/VAR 点表、已有原型与画面、需求文档里的操作流程；列出需要的画面、按钮、状态灯、报警与互锁提示，以及每一项对应的点表变量。
- 点表里找不到的变量或条件：列出来退回项目经理，不自己编。

## Execution

- 仅修改 Work scope 与 owned paths 的交集；发现未声明 dirty path、Git 基线漂移或 lease 失效立即停止。
- 画面里的每个按钮、指示灯、数值框都绑定到已批准点表里的变量；不新增变量，不改点表。
- 缺失条件要在画面上自诊断显示（为什么不能动），手动寸动要有互锁提示。具体做法见规范 STD-909（人机交互四步呈现）、STD-910（HMI HTML 原型部件库）、STD-911（桌面 HTML 原型脚手架）、DEV-301 与 DEV-216（QML 视图层边界）。
- 不修改依赖、发布指针或范围外文件，除非 Decision 明确授权。

## 验证与交接

```powershell
& "<ws>\.venv\Scripts\python.exe" "<ws>\main.py" prototype check --pid <PID>
& "<ws>\.venv\Scripts\python.exe" "<ws>\main.py" doc check
```

适用门禁 Exit 0 后创建 Continuity Checkpoint；换 Agent 时创建 handoff.v2。门禁要求：导航零死链、JS 函数与信号槽零未定义、画面变量与点表一一对应。回执遵循共享契约，区分 PASS、FAIL、NOT_RUN。不得修改 `PM_SESSION_*.md`、`.auto-pm/ai_feedback.json` 或 handoff.v1 文件。
