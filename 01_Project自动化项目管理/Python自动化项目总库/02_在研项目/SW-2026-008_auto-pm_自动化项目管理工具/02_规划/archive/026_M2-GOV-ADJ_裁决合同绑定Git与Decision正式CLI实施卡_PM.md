# M2-GOV-ADJ｜裁决合同绑定 Git 与 Decision 正式 CLI 实施卡（整改 R1：B + C）

> 卡片编号：`CARD-SW008-M2-GOV-ADJ`
> 阶段：整改阶段 3（见 024 号总览）；**前置：阶段 2（卡 023 BL02）已达完成判据**
> 版本：`V0.3`（2026-09-30，回填 BL02 最终基线并定稿；委托执行；Checkpoint 先于提交）
> 状态：`PLANNED / NOT_AUTHORIZED`（V0.3 定稿，待授权；授权方式见 §7.1）
> 覆盖 GPT 项：B、C
> 隔离基线：`7cfe227e7bf4a7df57d95644a80ea2652ef5a9cc`（BL02 最终不可变候选，CHG-SCPT-2026-356 completed，判卷 `c387bb9b…d18e`）
> 治理任务真源：WBS 候选提交 `a385452cde480090d27175f1b4d2ccfe358a4cec`；WBS SHA-256 `AEBB2AE678D483A19E499C3A3706FD5C880643EF3EB689B2B4093D0665045EC6`
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或能力不低于它的模型；实际执行者 `Claude Opus 5.5`
> 禁用能力：`pm-workflow`

> V0.3 定稿说明：BL02 已于 2026-09-30 验收（最终候选 `7cfe227e`），本版回填该基线并定稿。授权方式：用户 2026-09-30 在对话中授权 Claude 全权推进 M2 里程碑（“M2里程碑的任务都给你授权推进”），审批与验收由 Claude 以委托方式执行并如实记录，不以用户亲手签署冒充。执行顺序吸取 BL02 教训：Run 的 `git_head` 固定为本卡基线，门禁在未提交的候选字节上执行，Checkpoint 先于提交创建并在 evidence 中逐文件记录 SHA-256；提交后核验提交内 blob 与 Checkpoint 记录一致，再推进 Run/Work 终态。V0.2 原字节归档于 `.auto-pm/reports/m2-gov-adj/card026_V0.2_original.md`。

## 1. 背景与已核实事实

1. H11A/H11B/H11C 的裁决与围栏命令（`continuity work adjudicate`、`continuity run fence-legacy-terminal`）由 2026-09-29 的 CHG-349/353 交付。其中 `adjudicate_blocked_work` 只用 `DecisionService.get_decision_with_sha256` 读取 Decision 字节，**没有**做 Git 绑定，强度低于 `settle_expired_run`。H11A 的 11 条是在未跟踪 Decision 下执行的，已登记为“较弱合同下执行”，本卡不回溯重验。
2. 参照实现已存在：`ContinuityStore._decision_git_snapshots(...)`（`settle_expired_run` 使用）。它接受“目标（原）Decision”与“恢复 Decision”，并逐项校验：恢复 Run 的 `git_head` 是完整 commit OID；首次执行时当前 Git HEAD 精确等于该 `git_head`；两个 Decision 文件在 Git index 中被精确跟踪；相对 HEAD 无脏改；工作树 clean blob 与 `git_head` 处的 blob 一致；SHA-256 与调用方绑定值一致；读取前后无漂移。
3. `decision create` CLI 目前只有 `--target-run-id`，没有 `--target-work-id`；`adjudicate_blocked_work` 的 Decision 是用 `DecisionService` 的 Python 接口临时生成的（H11A、H11B），H11C 的两个 Decision 是用户运行的脚本以同一方式生成。
3.1 DTO 层已具备：`RuntimeDecisionCapability` 有 `target_work_ids`；`adjudicate_blocked_work` 与 `fence_legacy_terminal_lease` 均为独占 action；Run 级 action 只接受 `target_run_ids`。
4. 事件重放兼容风险：H11 期间已写入的 `WORK_ADJUDICATED` 事件，其 `request` 里没有 Git 绑定字段；若把新字段加进 `request`，旧事件的重放比较会失败。

## 2. 单一目标

- **B**：`adjudicate_blocked_work` 首次执行必须与 `settle_expired_run` 同强度地绑定 Git；
- **C**：`decision create` 增加 `--target-work-id`，并建立按 action 的严格互斥/必填合同，使 Work 裁决 Decision 不再需要临时脚本。

## 3. 实施前预检（只读，先于任何写入）

1. 核验本卡已由计划模板定稿：隔离基线不再含占位符，卡片最终 SHA-256 已被外部 Approval Receipt 绑定；否则立即停止。
2. 核验隔离基线 SHA 存在、是 BL02 的最终不可变提交，且 BL02 结论为 `PASS`。
3. 核验命令存在：`main.py decision create`（含 `--target-run-id`、`--allow-runtime-action`、`--allow-outcome`）、`main.py continuity work adjudicate`、`main.py continuity work adjudication-evidence`；**并核验 `--target-work-id` 目前不存在**（否则说明基线已变，停止）。
4. 核验 §4 每个路径在基线上的存在性与标注一致。
5. 核验 `_decision_git_snapshots` 存在且签名与 §1.2 一致。
6. 记录基线的相关测试结果作为对照（§6 G1 用）。

## 4. 精确 Owned Paths（9）

均相对 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/`。

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `auto_pm/infrastructure/continuity_store.py` | 存在 | B：`adjudicate_blocked_work` 绑定 Git；证据对象 |
| 2 | `auto_pm/application/core/work_registry_service.py` | 存在 | B：把恢复 Run 的 `git_head` 与 Decision SHA 传给 Store；`adjudication_evidence` 补充只读诊断 |
| 3 | `auto_pm/ui/cli/decision.py` | 存在 | C：`--target-work-id` 与互斥矩阵 |
| 4 | `tests/core/test_work_registry_service.py` | 存在 | B 测试 |
| 5 | `tests/infrastructure/test_continuity_store.py` | 存在 | B 存储层测试 |
| 6 | `tests/cli/test_decision.py` | 存在 | C 测试 |
| 7 | `tests/contracts/test_decision_package.py` | 存在 | C 的 DTO 测试（只加不删） |
| 8 | `auto_pm/application/core/continuity_execution_service.py` | 存在 | B2：`fence_legacy_terminal_lease` 同样绑定 Git |
| 9 | `tests/core/test_legacy_terminal_lease_fence.py` | 存在 | B2 测试（该文件由 BL02 引入，在 BL02 之前的 R 线提交上不存在） |

**B2（用户已于 2026-09-29 决定纳入）**：把同样的 Git 绑定应用到 `fence_legacy_terminal_lease`（同为本次新增、同样较弱）。已选：额外授权 #8、#9，共 9 个路径。同一弱点、同一模式，合并修复更不易出现两处偏差。§5.1 的合同同样适用于 `fence_legacy_terminal_lease`：首次执行绑定恢复 Run 的 Git HEAD，Decision 已跟踪、无脏改、SHA 与 HEAD blob 一致；重放先于 Git 检查；新增证据放入 `authority` 子对象，不改 `request`；G2 的 10 个场景对它同样各做一遍。

治理证据对象在控制根落账，不计入上述路径。

## 5. 合同

### 5.1 B：裁决绑定 Git（`adjudicate_blocked_work`）

**首次执行**（在幂等重放分支之后）必须：
1. 调用 `_decision_git_snapshots`，参数：`recovery_git_head` = 恢复 Run 的 `git_head`；`target_decision_id` = 目标 Work 当前的 `authorization_ref`（原 Decision）与其 SHA-256；`recovery_decision_id` = 裁决 Decision 与其 SHA-256；`require_current_head=True`。
2. 恢复 Run 的 `worktree_path` 必须规范化后等于控制根主工作树（与 `fence_terminal_lease` 一致）。
3. 任一校验失败：整个事务回滚，不写 Work、不写事件。

**审计**：成功事件的 payload 新增 `authority` 子对象，记录 `git_head`、原 Decision 的 HEAD blob OID、裁决 Decision 的 HEAD blob OID。**不得修改 `request` 字段集合**，以保持旧事件重放等价。

**重放**：幂等重放（同 key）先于所有 Git 检查，HEAD 已前移或 Decision 已变化时仍返回原结果；对 H11 期间写入、无 `authority` 的旧事件，重放必须继续成功。

**运维流程（须写入 `adjudication-evidence` 的帮助或输出说明）**：裁决前必须先把原 Decision 与裁决 Decision 提交进控制根 HEAD，并**在提交之后**再创建恢复 Run；之后 HEAD 不得前移，直到首次裁决完成。

### 5.2 C：Decision 正式 CLI

`decision create` 新增 `--target-work-id`（可重复）。按 action 的合同：

| action 组合 | `--target-run-id` | `--target-work-id` | 说明 |
|---|---|---|---|
| Run 级：`settle_expired_run`、`revoke_unstarted_run`、`fence_terminal_lease` | 必填（≥1） | 禁止 | 沿用既有可组合语义 |
| `fence_legacy_terminal_lease` | 必填（≥1） | 禁止 | 独占，不与其他 action 混用 |
| `adjudicate_blocked_work` | 禁止 | 必填（≥1） | 独占，不与其他 action 混用；只接受精确 Work ID |
| 未提供任何 runtime 选项 | — | — | 普通 Decision，行为不变 |

- 不满足矩阵一律非零退出，错误信息指出违反的规则；不得静默丢弃多余参数。
- `--allow-outcome` 仍只接受 `CANCELLED`。
- CLI 生成的 runtime Decision 与 `DecisionService.create_decision` 以同一 capability 生成的结果**字节等价**（`approved_at` 除外），并以测试证明；此后不再使用临时 Python 脚本生成此类 Decision。

## 6. 门禁矩阵

**G1 回归（对照基线）**：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/contracts tests/core tests/infrastructure tests/cli
```

先在基线取得同一集合结果；新增失败为 0（既存债只能标 `BASELINE_EXCEPTION`）。含 `test_continuity_execution_service.py` 的整集约 30～45 分钟，须后台运行并监视。

**G2 B 必测场景**（每项都要有独立测试）：
1. 原 Decision 未跟踪 → 拒绝；
2. 裁决 Decision 未跟踪 → 拒绝；
3. Decision 相对 HEAD 有脏改 → 拒绝；
4. 恢复 Run 的 `git_head` 与当前 HEAD 不一致（首次执行）→ 拒绝；
5. 调用方绑定的 SHA 与 HEAD blob 不一致 → 拒绝；
6. Decision 在复核期间漂移 → 拒绝；
7. 上述任一失败后不写 Work、不写事件（回滚）；
8. 正常首次执行：写入 `authority` 子对象且 `request` 字段集合不变；
9. 正常重放：HEAD 前移后同 key 仍成功，且不重复写事件；
10. 重放 H11 期间写入、无 `authority` 的旧格式事件仍成功。

**G3 C 必测场景**：矩阵每一行至少各一个正例与反例；`--target-work-id` 与 `--target-run-id` 混用、缺目标、action 混用独占动作、非法 outcome 各一个；CLI 与 API 的字节等价测试；`--help` 含新参数。

**G4 既有行为不退化**：`settle_expired_run`、`fence_terminal_lease`、`revoke_unstarted_run` 的既有测试与对应 CLI 行为不变；`adjudication-evidence` 与旧调用兼容。

**G5 静态质量**：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m ruff check --no-cache <§4 中 Python 路径>
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m mypy --strict --no-incremental <§4 中 Python 路径>
git diff --check
```

不得用 `--follow-imports=skip` 或文件级抑制换绿。

**G6 不触碰生产**：测试全部使用临时仓库与临时库，不读写真实 `.auto-pm/continuity.db`；结束不得残留 `.coverage`、缓存或临时仓库。

## 7. 实施授权签字门与 GUI 合同

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-GOV-ADJ V0.3` |
| 实施批准 | `PENDING`（委托执行，回执另行生成） |
| 最终验收 | `PENDING` |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| 隔离基线 | `7cfe227e7bf4a7df57d95644a80ea2652ef5a9cc` |
| Owned Paths | §4 的 9 个路径 |
| 执行模型 | `Claude Opus 5.5` |
| 明确禁止 | 范围外路径、直接 SQL、历史事件/Checkpoint 改写、Hook/release 修改、合并、推送、部署 |

本表不是授权真源。BL02 完成后，本卡必须回填精确基线并形成新版本；外部 Approval Receipt 必须绑定最终卡片 SHA-256、BL02 提交、WBS 真源、9 个 owned paths、允许/禁止动作、执行模型、审批人和审批时间。卡片自身不得写入自身 SHA-256。

### 7.2 授权成立与失效

1. 计划模板、含占位符的卡片或未绑定 Approval Receipt 的卡片均不得创建写入型 Work/Run。
2. 卡片、BL02 基线、WBS 真源、owned paths、执行模型或禁止事项任一漂移，旧审批立即失效。
3. 实施批准与最终验收是两个独立签字门；执行 Agent 只能提交候选与证据，不能代替用户验收或关闭 CHG。
4. GUI 必须展示卡片版本/哈希、BL02 基线、9 路径、允许/禁止动作与审批身份，并通过高层领域服务生成回执；禁止直接改 Markdown、Decision JSON 或 canonical 数据库。

## 8. 治理执行顺序

1. 只读预检并输出事实表（§3）。
2. **由用户**通过 §7 签字门批准已回填 BL02 基线的最终卡片，再创建并批准独立 CHG 与精确 Decision（§4 的 9 个路径，B2 已选）；Agent 不代为批准。
3. 高层服务创建 Work、Run 与有界租约；禁止直接 SQL。
4. 在全新隔离候选（自 BL02 基线起步）中实施并完成 §6 门禁。
5. 创建当前字节 Checkpoint（`git_head` 为基线，dirty paths 为实际改动的 owned paths，evidence 逐文件记录 SHA-256 与判卷文件 SHA-256），随后走正常 Hook 提交；提交后核验提交内 blob 与 Checkpoint 记录逐一相同，否则停止。
6. Run/Work 终态、台账 reconcile；**CHG 最终收口由用户执行**。
7. 停止并向用户报告；SHA 与 ID 回写 024 §2；部署另见卡 028，不在本卡。

## 9. 硬停止条件

- 基线 SHA、路径存在性、命令存在性或 `_decision_git_snapshots` 与本卡不符；
- 需要 §4（及已选 B2）之外的路径；
- 需要修改 `settle_expired_run` 的既有行为或既有事件格式；
- 只能通过降低校验、mock Git 或 skip 才能变绿；
- 需要改数据库、历史事件、Checkpoint、Hook 安装、release 指针。
- 本卡仍含基线占位符，或卡片 SHA-256、Approval Receipt、BL02 提交、执行模型身份无法相互证明。

## 10. 交付物

1. 基线 SHA 与预检事实表；
2. CHG / Decision / Work / Run / Checkpoint ID；
3. 精确 diff 与最终 SHA-256；
4. G1～G6 矩阵、原始命令、Exit Code、输出位置；
5. G2 的 10 个场景与 G3 矩阵的测试名对照表；
6. 不可变提交 SHA；
7. 对“H11 期间弱合同下的执行”的说明（已登记，不重验）。
8. Approval Receipt、最终卡片 SHA-256、BL02 基线与实施/验收双签字门状态。

## 11. 与其他阶段的关系

本卡完成后，B/C 只是候选提交；稳定运行时仍是旧合同，直到卡 028 的集成部署获用户批准。
