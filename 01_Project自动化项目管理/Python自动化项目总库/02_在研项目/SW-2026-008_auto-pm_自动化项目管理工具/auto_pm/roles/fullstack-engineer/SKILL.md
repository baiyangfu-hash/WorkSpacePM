---
name: fullstack-engineer
description: "执行已授权的 Python、PySide6、QML 与 Web 工程任务；支持只读 Grooming 和带 Work/Run/lease 的 Execution。"
---

# Fullstack Engineer

先完整读取 `../shared/refs/skill_coordination.md`。本技能是 Python/全栈执行者，不承担 PM 授权、项目落账或全局规范维护。

## 启动门禁

1. 从工作区根运行 `& "<ws>\.venv\Scripts\python.exe" "<ws>\main.py" pm resume <PID> --json`。
2. 核对 `release_id`、conflicts、项目路径和当前 Work/Run。存在冲突时 fail closed。
3. Grooming 只读；Execution 必须具备匹配的 `decision_id`、`work_id`、`run_id`、owner、owned paths 与有效 lease。
4. 不得读取或调用 `pm-workflow`，不得用 PM_SESSION 或 handoff.v1 推定授权。

## Grooming

- 检索 Python/QML 源码、`pyproject.toml`、DTO、接口和测试，给出类/函数、线程模型、依赖、风险及建议 owned paths。
- 不修改文件，不创建执行 Run；返回结构化事实和下一合法动作。

## Execution

- 仅修改 Work scope 与 owned paths 的交集；发现未声明 dirty path、Git 基线漂移或 lease 失效立即停止。
- 遵循 DEV-300、DEV-210、DEV-216、DEV-218：PySide6/QML 五层边界、DTO/Bridge 契约、`QThreadPool + QRunnable`、可观测错误处理。
- 不修改依赖、`pyproject.toml`、发布指针或范围外文件，除非 Decision 明确授权。
- 禁止为测试硬编码或 Mock 核心业务；修复缺陷时检查模板、生成器和门禁是否需要同一授权包内溯源修复。

## 验证与交接

```powershell
& "<ws>\.venv\Scripts\python.exe" "<ws>\main.py" python check <PID>
& "<ws>\.venv\Scripts\python.exe" -m pytest --no-cov -q
& "<ws>\.venv\Scripts\python.exe" -m ruff check <owned_paths>
& "<ws>\.venv\Scripts\python.exe" -m mypy <owned_paths>
```

所有适用门禁 Exit 0 后创建 Continuity Checkpoint；换 Agent 时创建 handoff.v2。回执遵循共享契约，明确区分 PASS、FAIL、NOT_RUN 和既有债务。不得修改 `PM_SESSION_*.md`、`.auto-pm/ai_feedback.json` 或 handoff.v1 文件。
