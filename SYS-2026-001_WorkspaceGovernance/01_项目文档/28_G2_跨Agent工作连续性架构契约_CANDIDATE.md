# G2 跨 Agent 工作连续性架构契约（项目候选）

> 状态：`ACCEPTED_CANDIDATE / NOT_OBSIDIAN_EFFECTIVE`
> 决策日期：2026-09-09
> 适用范围：SW-2026-008 研发母体与 My_Workspace 本地治理运行态
> 上位计划：`26_SW-2026-008_治理恢复与连续性重基线总计划_PM.md`
> 吸收来源：文档 20～24；来源文档保留历史字节，但不再分别充当实现契约
> 明确排除：`.trae/skills/pm-workflow`、PLC/LSP、DEV-300、Obsidian 正式法典和其他业务项目整改

## 1. 架构不变项

1. Project、Governance、Work、Run、Checkpoint、Handoff 和 Release 是不同对象，不得共用一个状态字段。
2. subject project 与 control project 必须显式映射；控制面不得覆盖主体项目状态。
3. PM 是治理职责，不是某个 Agent 技能。所有授权写入通过平台中立服务执行，并保留 User 批准证据。
4. Markdown 只承载规范、授权和人工摘要，不承载高频运行状态。
5. Adapter 只转换入口和显示，不持有核心状态。
6. 所有恢复均从显式身份、持久化状态和指纹开始；禁止依赖“最近一次会话”或自由文本猜测。

## 2. 真源决策

| 事实 | 唯一真源 | 说明 |
|---|---|---|
| 项目拓扑 | Workspace Registry 的显式映射 | 记录 subject/control/development/runtime；不得全文搜索 PM_SESSION |
| CHG/Decision 授权 | 既有 CHG、Decision 和审批历史 | 只回答允许做什么，不表示已完成 |
| Work/Run/Checkpoint/Lease/Event | 根 `.auto-pm/continuity.db` | SQLite WAL 事务库；工作空间本地唯一可变运行真源 |
| 交接快照 | `.auto-pm/handoffs/*.json` 的 handoff.v2 | 从事务状态生成并带指纹；不反向成为状态真源 |
| 审计导出 | `.auto-pm/events/*.jsonl` | 从事务事件表导出、逐条哈希链接；不可用于覆盖当前状态 |
| 项目人工摘要 | PM_SESSION | 只投影项目级目标、风险、活跃 Work ID 和下一合法动作摘要 |
| 查询索引 | 根 `.auto-pm/index.db` | 可重建投影；项目内 `index.db` 停止新增写入并经迁移后退出 |
| Git/Release | 实时 Git 快照、release manifest、active/previous 指针 | 叙述不得覆盖实物 |

`continuity.db` 不保存规范正文、CHG 正文或源码副本，只保存其规范化 ID、路径和内容指纹。

## 3. Continuity Store 最小 Schema

| 表 | 主键 | 必备字段 |
|---|---|---|
| `schema_meta` | `schema_version` | created_at、migrated_at、tool_version |
| `work_items` | `work_id` | subject_project_id、kind、title、state、owner、authorization_ref、scope_hash、source_fingerprint、version、timestamps |
| `work_relations` | `(from_work_id,to_work_id,relation)` | relation=`blocks/blocked_by/parent/child/discovered_from/duplicates`、created_event_id |
| `runs` | `run_id` | work_id、actor、adapter、state、development_root、runtime_root、release_id、git_head、dirty_hash、worktree_ref、version、timestamps |
| `checkpoints` | `checkpoint_id` | work_id、run_id、sequence、state_snapshot、evidence_hash、read_set_hash、next_action、created_at；记录不可变 |
| `leases` | `lease_id` | work_id、run_id、owner、owned_paths_hash、acquired_at、expires_at、released_at、version |
| `events` | `event_id` | aggregate_type、aggregate_id、event_type、payload_json、previous_hash、event_hash、created_at、idempotency_key |
| `outbox` | `outbox_id` | event_id、artifact_kind、target_path、payload_hash、published_at |

所有命令使用 `BEGIN IMMEDIATE`、busy timeout、乐观版本号和 `idempotency_key`。聚合状态变更与事件追加必须在同一事务提交；JSON/JSONL 输出通过 outbox 后置生成，失败可重试，不能形成第二真源。

## 4. 对象状态机

### 4.1 Work

`PLANNED → READY → IN_PROGRESS → VERIFYING → ACCEPTED → CLOSED`

允许分支：`READY/IN_PROGRESS → BLOCKED → READY`；任一未关闭状态可经批准进入 `CANCELLED`。写入型 Work 从 `PLANNED` 进入 `READY` 前必须验证批准的 CHG/Decision、scope hash 和路径上限；只读 grooming 必须显式标记 `read_only=true`，不能借此写入。

### 4.2 Run

`CREATED → CLAIMED → RUNNING → RESULT_SUBMITTED → VERIFIED → COMPLETED`

允许分支：`CLAIMED/RUNNING → CHECKPOINTED → RUNNING`；异常进入 `FAILED`、租约过期进入 `EXPIRED`、经恢复处置进入新的 Run。旧 Run 不回写成新 Run，不复用 run_id。

### 4.3 Lease 与 Checkpoint

同一 Work 同一 owned path 同时只能有一个有效写 lease。lease 到期后旧 owner 的 heartbeat、结果提交和关闭全部拒绝。Checkpoint 永不原位更新；每次按 sequence 追加，必须绑定 work_id、run_id、Git 基线、dirty 分类、read_set 和 evidence。

## 5. Identity / Context v2

解析顺序固定为：显式 `project_id` → 当前目录向上的唯一项目锚点 → Workspace Registry 的已验证映射。禁止全工作区递归扫描、文本包含推断、`ai_context.json` 默认选择和隐式 latest project。

成功结果必须包含：schema_version、subject_project_id、control_project_id、development_root、runtime_root、release_id、resolution_source、read_set、evidence、conflicts。路径必须规范化为工作区内相对路径，read_set 每项包含 SHA-256。

无锚点、多候选、映射冲突、路径越界、指纹不符、release 指针不完整或不可读均返回结构化非零结果。Context v2 不查询 Work/Run，也不生成 next action。

## 6. Work / Run / Resume v2

Resume 必须先消费成功的 Context v2，再按显式 work_id/run_id 查询。未显式指定时，只允许在“当前 actor、当前 subject、唯一有效 lease”条件下选择；零个返回空状态，多个返回 `AMBIGUOUS_ACTIVE_RUN`，禁止按更新时间取 latest。

Resume v2 分别返回 subject、control、runtime、work、run、checkpoint、authorization、git、read_set、evidence、conflicts 和 allowed_actions。allowed_actions 只能由状态机和授权计算；任一 stale 指纹、Git 漂移、未知 dirty、过期 lease、scope 冲突或 schema 不兼容必须优先于 next action。

PM_SESSION 的 current focus 只能显示 Work ID 和摘要，不得反向驱动 Resume。

## 7. Handoff v2

必填字段：schema_version、handoff_id、subject_project_id、control_project_id、work_id、run_id、checkpoint_id、authorization_ref、development_root、runtime_root、release_id、source/target Git revision、dirty declaration、owned_paths、from/to actor、lease、read_first、constraints、acceptance、evidence、result_ref 和 capability set。

handoff.v1 继续只读。需要 Work、Run、lease、写权限或基线保护的场景不得降级到 v1；v1 迁移必须产生显式 migration event，缺失字段不得猜测。自由文本、源码 suppression、自称 PASS 和 PM_SESSION 段落均不能替代授权或豁免。

## 8. Git、Worktree 与证据

每个写入 Run 记录 repo root、HEAD、dirty path 集及其 hash、approved paths 和 owned paths。dirty 文件分为 `expected_owned`、`pre_existing_foreign`、`unknown`；出现 unknown 或 ownership 重叠立即失败关闭。

worktree 默认关闭；并发写入、发布、高风险、跨项目、共享 dirty tree 或 owned path 重叠时强制使用。关闭 Work 不自动删除 worktree，必须先验证提交、未跟踪文件、未消费 checkpoint 和恢复指针。

验证证据必须区分 `verified` 与 `not_verified`，记录命令、cwd、解释器/入口、版本、exit code、时间和产物 hash。窄测不能宣称全量通过，active release 测试不能代替研发母体测试。

## 9. 兼容与迁移

- 新版本：`workspace-context.v2`、`continuity-store.v1`、`work.v1`、`run.v1`、`checkpoint.v1`、`handoff.v2`、`pm-resume.v2`。
- 旧 Context/Resume/Handoff 只读兼容；任何写操作要求新 capability。
- migration 只前向新增表和字段，不删除旧表；每步记录前后 schema、行数、hash 和回退备份。
- 项目内 `index.db` 在完成所有权和数据盘点前保持只读；禁止自动合并两个数据库的冲突记录。
- 未知 schema、缺 capability 或迁移中断一律停止写入。

## 10. 验收矩阵

G3～G7 至少覆盖：显式/目录 Context、subject/control 反转、无锚点、多候选、路径越界、指纹漂移、双库冲突、Work block/unblock、重复 idempotency、并发 lease、lease 过期、owned path 重叠、dirty 三分类、checkpoint 重放、跨 Agent 接续、v1 只读、未知 schema、outbox 重试、故障注入无半写、inactive release 验证、切流回退。

最终 Dogfood 使用两个真实独立 Agent：Agent A 在受控 Work 上生成 checkpoint，Agent B 仅凭 handoff.v2 和持久化状态恢复，得到相同 subject、授权、Git 基线、允许动作和 evidence，并安全完成或明确失败关闭。

## 11. 生效边界

本文件是 SW-2026-008 的已接受实现契约，但不是 Obsidian 正式规范。它授权后续 G3～G7 按总计划实施，不授权修改 Obsidian、扩大到其他项目或解除 `pm-workflow` 隔离。G7 Dogfood 全绿后，G8 才可提交正式规范差异和注册表生效包。
