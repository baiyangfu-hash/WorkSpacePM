# Agent 协同与连续性通用契约

> 来源：CHG-SCPT-2026-032。适用于 `fullstack-engineer` 与 `plc-electrical-engineer`；`pm-workflow` 已退役隔离，不属于本契约消费者。

## 1. 角色与真源

- **PM 是治理角色，不是独占技能**：当前主 Agent 负责需求澄清、CHG、Decision、Work 授权、验收和关闭。
- **执行技能不持有治理权**：只能在收到匹配的 `project_id`、`work_id`、`run_id`、`decision_id`、`owned_paths` 与 lease 后修改已授权范围。
- **机器真源**：CHG/Decision 管授权；Continuity Store 中的 Work/Run/Checkpoint/lease 管执行状态；Git 管代码基线；发布 manifest 与 active/previous 指针管运行版本。
- **人工投影**：`PM_SESSION_*.md` 仅用于项目摘要，不是 Work/Run/审批真源；执行技能不得修改。
- **适配层无状态**：Agent、IDE、技能和聊天上下文不得创建平行账本，不得写 `.auto-pm/ai_feedback.json` 或 handoff.v1 文件。

## 2. 统一入口

所有驾驶舱命令从工作区根目录执行：

```powershell
& "<workspace>\.venv\Scripts\python.exe" "<workspace>\main.py" pm resume <PID> --json
```

禁止以 `python -m auto_pm`、研发母体目录或某个 IDE 私有脚本作为生产入口。Resume 的 `context.release_id` 必须对应 active release；存在 conflict 时 fail closed。

## 3. 四阶段流程

1. **Grooming**：先运行 `pm resume <PID> --json`，再只读勘测源码、配置、接口和测试。无已授权 Work/Run 时只能返回事实，不得修改。
2. **Approval**：PM 角色建立 CHG 和 Decision，并创建/授权 Work；User 明示批准前不得进入 Execution。
3. **Execution**：执行技能核对 Work/Run/Decision、owned paths、Git baseline 与 lease，只修改 owned paths；dirty tree 未声明、lease 过期或 schema 未知时停止。
4. **Acceptance**：执行端运行领域门禁，创建 Checkpoint；需要换 Agent 时创建 checkpoint-bound handoff.v2。PM 角色核验代码、证据、状态和台账后关闭 Work/CHG。

## 4. 交接契约

- 对话回执必须包含：`project_id`、`work_id`、`run_id`、`checkpoint_id`、`decision_id`、`owner`、`owned_paths`、`git_head`、`dirty_paths`、`changed_files`、`verification`、`risks`、`next_legal_action`。
- 物理交接只能使用 `main.py continuity checkpoint create`、`continuity handoff create` 和 `continuity handoff accept`；handoff.v1 仅可读历史，不得新增。
- 执行技能不得自行宣布验收、关闭 CHG、切换 release 或修改 Obsidian；这些动作由 PM 角色在授权范围内完成。

## 5. 独立触发

用户直接调用执行技能时，技能仍先执行 `pm resume <PID> --json`。若没有可执行的已授权 Work/Run，则降级为只读 Grooming，返回需要 PM 角色建立的授权对象；不得借用 PM_SESSION、旧 handoff 或聊天文字推定执行权。
