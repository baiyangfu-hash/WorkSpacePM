# Agent 协同、分诊路由与门禁分档契约

> 跨角色通用路由正本。适用于 `product-pm`、`fullstack-engineer`、`plc-electrical-engineer`、`ui-designer`、`test-engineer`；已隔离的 `pm-workflow` 不属于消费者。

## 1. 角色与真源

- **PM 是治理角色**：主 Agent 负责需求澄清、范围拆解、变更单（CHG）报批、分诊派活、结果验收与收口汇总。
- **执行岗位不持有治理权**：只在已获授权范围与隔离工位内改文件并自检，不自批变更单、不代用户点验收、不改控制根 `main`。
- **机器真源**：`AGENTS.md`（`FLOW-001`、`FLOW-002`、`WS-001`）与受控变更单管授权；Git 提交与实施卡管改动事实；WBS 项目计划表状态由 `SW8/scripts/plan_status.py` 与 `card_status.py` 按 `main` 现场现算；Run 租约卡另由 Continuity Store 的 Work/Run/Decision/lease 管状态。
- **人工摘要非授权**：`PM_SESSION_*.md`、旧 handoff.v1 与交接交换区（`pm_handoff.py`）均不构成执行授权或审批凭据。

## 2. 统一进门入口

新会话或换班接手，按 `.trae/skills/cockpit-entry/SKILL.md` 先从控制根执行只读进门：

```powershell
.\.venv\Scripts\python.exe ".\01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-008_auto-pm_自动化项目管理工具\scripts\pm_flows.py" entry <PID>
```

无项目计划表或仅做单项目排查时，按需辅以 `.\main.py pm orient <PID> --json` 与 `pm_flows.py checkup <PID>`；严禁从隔离工位直接运行 `main.py` 主命令，也严禁绕过控制根 `.venv`。

## 3. PM 分诊与门禁分档决策表

| 决策维度 | 路由条件 | 执行路径与门禁要求 |
|---|---|---|
| 改动分级（`FLOW-001`） | 命中受保护路径（PLC/规则/合并脚本/删改外部文件/发版） | 走“要你点头”：先建 CHG 填齐 `§5`、经用户批准后开工位、必须 `AUD-001` 独立审计与用户推到完成 |
| 改动分级（`FLOW-001`） | 驾驶舱普通代码、测试、脚本、文档与工程自身清理 | 走“直接做，事后告诉你”：领卡号入分支与提交说明，本机门禁过即合并，当天汇报提交号与回退指令 |
| 任务组织（单卡 vs WBS） | 独立单点需求或缺陷 | 单张实施卡闭环 |
| 任务组织（单卡 vs WBS） | 多任务有前后依赖、需跟踪里程碑交付 | 在 `<项目>/00_项目管理/01_立项与需求/NNN_<PID>_项目计划表.md` 挂卡，`证据` 列挂含卡号的独立回执，用 `plan_status.py <PID>` 现算进度 |
| 流程轨（轻轨 vs 重轨 Run） | 日常开发、文档、修复与规则调整 | 走隔离工位 + 本地/云端门禁 + `pm_merge.py merge` 轻轨 |
| 流程轨（轻轨 vs 重轨 Run） | 看板“确认开工”一键流或命令硬要求 Run/租约 | 走 Work/Run/Checkpoint/lease、`pm verify` 与 `pm_flows.py closeout` |
| 门禁分档（`gate precheck`） | 按候选路径自动判 L1/L2/L3 | `gate plan --preview` 先看档次、理由和检查组；L1 本机 `gate precheck`，L2/L3 `gate start`；细则见命令总目录 |

## 4. 四阶段流水线与交接约定

1. **Grooming（只读）**：执行进门检查，只读源码、配置、点表与测试，识别 `FLOW-001` 分类、预计 `owned_paths` 与 `L1/L2/L3` 档次；缺授权时不写任何生产文件。
2. **Approval（报批）**：`要你点头` 类由 PM 产出实施计划并建 CHG（填齐 `§5` 后报批）；轻轨可直接定卡号开工位；Run 卡另备 Decision/Work。
3. **Execution（隔离执行）**：在 `R/.auto-pm/worktrees/<agent>` 分支实施，只动卡内路径，跑完本机单测/`ruff`/`mypy`/专用检查与 `gate precheck`（必要时推分支触发云端 `gate start`）。
4. **Audit & Acceptance（审计与收口）**：`要你点头` 类由独立会话的 `test-engineer` 审计放行；控制根跑 `pm_merge.py merge` 合入 `main` 并按 GitHub 档备份；按 `start_and_handoff.md` 更新单机交接或收口，Run 卡再创 Continuity Checkpoint。

- 对话回执须包含：卡号/变更单号、改动范围、门禁退出码或 Run ID、独立审计结论（若适用）、合并提交号与 `git revert` 回退指令、风险与下一步。
- 物理交接按模式选用 `pm_handoff.py`、`claim note` 或 Continuity `checkpoint/handoff.v2`（严禁新增 `handoff.v1`）。
