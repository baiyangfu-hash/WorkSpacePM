# 各岗位共用：开工门禁、执行边界与交接

本页是 fullstack-engineer、plc-electrical-engineer、ui-designer、test-engineer 共用的几条，只写在这里；各岗位的 SKILL.md 只写本岗位自己的，指到这里来，不再各抄一份（`main.py role check` 的 RP-010 会拦住两个岗位抄同一句）。

## 开工门禁

1. 进门照 `.trae/skills/cockpit-entry/SKILL.md` 的“进门”做（确认控制根和项目编号、跑只读定位），这里不另写一遍命令。
2. 核对 `release_id`、conflicts、项目路径，以及本卡的变更单是否已经用户批准、领卡占位是否覆盖要改的文件（走 Run 的卡另核当前 Work/Run）。存在冲突时 fail closed。
3. 不得读取或调用 `pm-workflow`，不得用 PM_SESSION 或 handoff.v1 推定授权。
4. 执行岗位（fullstack-engineer、plc-electrical-engineer、ui-designer）：Grooming 只读；Execution 必须具备用户批准过的变更单和覆盖可改范围的领卡占位（`AGENTS.md` 红线 2、D-101）；走 Run 的卡（看板“确认开工”一键流、命令本身要求 Run 或租约的）另需匹配的 `decision_id`、`work_id`、`run_id`、owner、owned paths 与有效 lease。

## 执行边界

- 仅修改领卡占位登记的路径（走 Run 的卡：Work scope 与 owned paths 的交集）；发现未声明 dirty path、Git 基线漂移或 lease 失效立即停止。

## 交接

适用门禁 Exit 0 后：走 Run 的卡创建 Continuity Checkpoint，PR 线的卡在占位上用 `main.py claim note` 记一笔（`AGENTS.md` FLOW-002“交接记录”）；换 agent 照 `.trae/skills/cockpit-entry/SKILL.md` 的“换 agent”做。回执遵循 `skill_coordination.md` 的共享契约，明确区分 PASS、FAIL、NOT_RUN 和既有债务。不得修改 `PM_SESSION_*.md`、`.auto-pm/ai_feedback.json` 或 handoff.v1 文件。
