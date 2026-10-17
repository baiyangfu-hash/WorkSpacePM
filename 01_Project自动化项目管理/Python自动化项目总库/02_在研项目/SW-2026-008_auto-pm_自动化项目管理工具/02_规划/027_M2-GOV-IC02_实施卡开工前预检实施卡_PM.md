# M2-GOV-IC02｜实施卡开工前预检实施卡（整改 R2：D）

> 卡片编号：`CARD-SW008-M2-GOV-IC02`
> 阶段：整改阶段 4（见 024 号总览）；前置：阶段 2（卡 023 BL02）已达完成判据；与阶段 3 互相独立，但两者都基于 BL02 基线，须各自独立候选
> 版本：`V0.4`（2026-09-30，回填 BL02 最终基线并定稿；委托执行；Checkpoint 先于提交）
> 状态：`PLANNED / NOT_AUTHORIZED`（V0.4 定稿，待授权；授权方式见 §7.1）
> 覆盖 GPT 项：D
> 隔离基线：`7cfe227e7bf4a7df57d95644a80ea2652ef5a9cc`
> 治理任务真源：WBS 候选提交 `a385452cde480090d27175f1b4d2ccfe358a4cec`；WBS SHA-256 `AEBB2AE678D483A19E499C3A3706FD5C880643EF3EB689B2B4093D0665045EC6`
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或能力不低于它的模型；实际执行者 `Claude Opus 5.5`
> 禁用能力：`pm-workflow`

> V0.4 定稿说明：BL02 已于 2026-09-30 验收（最终候选 `7cfe227e7bf4a7df57d95644a80ea2652ef5a9cc`），本版回填该基线并定稿；与卡 026 一样从 BL02 独立起步，由卡 028 合并。自举人工预检（§3）已在该基线上完成并归档于 `.auto-pm/reports/m2-gov-ic02/preflight_facts.md`。授权方式：用户 2026-09-30 在对话中授权 Claude 全权推进 M2 里程碑，审批与验收由 Claude 以委托方式执行并如实记录。执行顺序：Run 的 `git_head` 固定为本卡基线，门禁在未提交候选字节上执行，Checkpoint 先于提交创建并逐文件记录 SHA-256，提交后核验 blob 一致再推进终态。V0.3 原字节归档于 `.auto-pm/reports/m2-gov-ic02/card027_V0.3_original.md`。

## 1. 背景与已核实事实

1. 实施卡机制是 M1 结束后为应对 C09 的混乱而增设的（IC01，提交 `b7bb9357`，仅在 M2 血统，不在稳定 release 血统）。它交付的是**结构化卡**：`ImplementationCard`（Pydantic）、`ImplementationCardService`、`implementation-card` CLI（`create`/`validate`/`approve`/`dispatch`/`verify`）和一个 Jinja 渲染模板。
2. 结构化卡已有的校验：`base_commit` 必须是完整不可变 SHA；派发前候选 HEAD 必须等于它；门禁 `argv` 必须是规范 token 列表且禁止 shell；门禁必须精确覆盖 `owned_paths`；`owned_paths` 与提交证据路径不得重叠；WBS 源文件必须已跟踪且无未提交改动；候选必须是受管的隔离工作树。
3. 结构化卡**没有**的校验（本卡要补）：`argv` 里的 `main.py <组> <命令>` 是否真实存在；既有路径是否真实存在于 `base_commit`，或被明确声明为“计划新增”；卡声明的基线是否包含卡里列出的既有路径。
4. **结构化卡不能充当“创建 Work/Run 之前”的门禁**：`create` 要求 `--decision-id`、`--work-id`、`--run-id` 已存在，`require_complete` 也检查执行身份是否完整，即它是在 Work/Run 之后才形成的。
5. **实际使用的卡是手写 Markdown 卡**（019～029 等），完全没有走结构化卡流程；`continuity work create` 现有选项为 `--work-id --pid --kind --title --owner --scope（可重复） --source-fingerprint --idempotency-key --read-only`，创建时不核对任何卡。
6. 两类已发生的历史事故（须做成防复发测试）：
   - 020 号卡把门禁写成 `main.py doc check --strict`，而 `doc check` 没有 `--strict` 选项；
   - 019 号卡列了 `tests/infrastructure/test_continuity_store.py`，在实际使用的基线上该文件不存在（卡是按另一条血统的基线写的）。

## 2. 单一目标

1. 新增一个**只读的开工前预检**，同时服务 Markdown 卡与结构化卡两种入口，对命令、既有路径与基线做 fail-closed 校验；
2. **强制接入**：`continuity work create` 创建**写入型** Work 时必须引用一张通过预检的卡，并把 Work 的 scope 约束在卡的 owned paths 之内；
3. 为上述两类历史事故各建立防复发测试。

方案 C（把结构化卡作为唯一真源、Markdown 卡由它渲染生成、预检与创建流程合并）**不在本卡**，登记为后续迭代。

## 3. 实施前预检（只读，先于任何写入）

1. 核验本卡已由计划模板定稿：隔离基线不再含占位符，最终卡片 SHA-256 已被外部 Approval Receipt 绑定；否则停止。
2. 核验隔离基线 SHA 存在、是 BL02 最终提交，且 BL02 结论为 `PASS`。
3. 核验命令存在：`main.py implementation-card validate`、`create`、`dispatch`、`main.py continuity work create`（在 BL02 基线上；若 `implementation-card` 不存在则基线不含 IC01，停止）。
4. 核验 §4 每个路径在基线上的存在性与标注一致。
5. 核验 `ImplementationCard`、`GateDefinition` 字段与 §1.2 一致；核验 `continuity work create` 的选项与 §1.5 一致。
6. 记录基线相关测试结果作为对照（含现有的 CLI `work create` 相关测试，§6 G6 用）。

## 4. 精确 Owned Paths（11）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `auto_pm/contracts/implementation_card.py` | 存在 | 结构化卡新增“计划新增路径”字段（如 `planned_new_paths`） |
| 2 | `auto_pm/application/core/implementation_card_service.py` | 存在 | `validate`/`dispatch` 复用预检 |
| 3 | `auto_pm/ui/cli/implementation_card.py` | 存在 | 新增 `precheck` 命令 |
| 4 | `auto_pm/application/core/implementation_card_precheck.py` | 计划新增 | 预检核心：卡解析、命令树解析、路径存在性、基线漂移 |
| 5 | `auto_pm/templates/governance/implementation_card.md.jinja` | 存在 | 模板加入“基线状态”列与头部字段 |
| 6 | `auto_pm/ui/cli/continuity.py` | 存在 | `work create` 强制接入预检 |
| 7 | `tests/contracts/test_implementation_card.py` | 存在 | 契约测试（只加不删） |
| 8 | `tests/core/test_implementation_card_service.py` | 存在 | 服务测试 |
| 9 | `tests/cli/test_implementation_card.py` | 存在 | CLI 测试 |
| 10 | `tests/core/test_implementation_card_precheck.py` | 计划新增 | 预检与防复发测试 |
| 11 | `tests/cli/test_continuity.py` | 存在 | `work create` 强制接入的测试，并调整既有 `work create` 用例 |

治理证据对象在控制根落账，不计入上述路径。**与阶段 3（卡 026）的 owned paths 无交集**（026 不含 `ui/cli/continuity.py` 与 `tests/cli/test_continuity.py`），使两个候选在卡 028 中可无冲突整合。

## 5. 合同

### 5.1 卡的机器可读格式（本合同同时适用于 Markdown 卡与结构化卡渲染结果）

1. **头部字段**（Markdown 引用块中的行）：`隔离基线：`取值为 40 位小写十六进制 commit SHA，或字面量 `WORKTREE`（表示以控制根工作树为基线，用于文档类卡）；`路径根：`为相对控制根的目录。**占位符（如 `<…回写…>`）视为“基线未回写”，预检失败**——这使后续阶段的卡在前一阶段未回写前无法开工。
2. **路径表**：任何同时含 `路径` 与 `基线状态` 两列的表格都被视为路径表；`路径` 列单元格取反引号内的相对路径（相对“路径根”）；`基线状态` 只允许三个值：
   - `存在`：必须在 `隔离基线` 提交上存在（`WORKTREE` 时在控制根工作树上存在）；
   - `计划新增`：必须在基线上**不存在**（防止把已存在文件误标为新增）；
   - `运行态`：不受 Git 跟踪的运行态对象（如 `.auto-pm/continuity.db`），要求在控制根文件系统上存在。
3. 表格里没有 `基线状态` 列、或取值不在上述三者之中 → 预检失败。旧卡（019～022 等）不迁移，预检对旧卡以“提示”报告，不改写它们。

### 5.2 预检的三项校验（全部 fail-closed，任一失败返回非零，且**不创建任何控制面对象**）

1. **命令存在**：从卡内容中提取所有 `main.py <组> [<子组>] <命令> [选项]` 调用，逐个在真实 click 命令树中解析：命令路径必须存在；出现的 `--选项` 必须是该命令声明过的选项。提取范围限定于 `main.py` 调用，不解析任意 shell 文本；含变量的前缀（如 `& $python -B main.py ...`）只取 `main.py` 之后的部分。未知命令或选项 → 拒绝，并给出最接近的合法候选。
2. **路径存在性与标注一致**：按 §5.1.2 逐行核验；标注与事实不一致（标“存在”而不存在、标“计划新增”而已存在）→ 拒绝。
3. **基线漂移**：`隔离基线` 必须可解析为完整 commit（或 `WORKTREE`）；所有 `存在` 路径都在该基线上存在。
4. **占位符拒绝**：隔离基线、路径、命令或审批字段中出现 `<...>`、`待回写`、`TBD` 等占位符 → 拒绝。动态产物（例如部署 release ID）必须在最终执行卡定稿时替换为精确值，不能靠运行时猜测。

### 5.3 入口

- `main.py implementation-card precheck --card-file <路径>`：读取卡并逐项输出结果，退出码 0 表示全部通过。**只读**，不写 Git、数据库、Work/Run/Decision。
- 结构化卡的 `validate` 与 `dispatch` 内部复用同一预检。

### 5.4 强制接入 `continuity work create`（方案 B）

1. 新增选项 `--card-file <路径>`。**写入型 Work（未加 `--read-only`）必须提供**；缺失 → 非零退出，且不写任何对象。`--read-only` 的 Work 豁免。
2. `work create` 在写入前于**同一进程内重新运行预检**（不信任任何回执文件，避免伪造）；预检失败 → 非零退出。
3. **scope 绑定**：每个 `--scope` 必须落在卡的路径表所列路径之内（路径根加相对路径后，精确相等或位于其下）；有 scope 不在卡内 → 拒绝。
4. **可追溯**：未显式提供 `--source-fingerprint` 时，默认写入 `card:<卡文件字节的 SHA-256>`；显式提供则保持原值。
5. **不受影响的路径**：由 Mission 强授权派生的 Work（`create_from_mission`）、服务层与 Facade 内部调用 `WorkRegistryService.create_work` 的路径不经此 CLI，本卡不改；登记为技术债（服务层与 Facade 未强制）。
6. **运行态操作的 Work**（例如 H11 那类 scope 为 `.auto-pm/continuity.db` 的恢复 Work）同样必须有卡，其路径表用 `运行态` 状态；这与 019/022 一类卡的现有写法兼容，只需补齐格式。
7. **不提供旁路**：不设置“跳过预检”的开关。

## 6. 门禁矩阵

**G1 回归（对照基线）**：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/contracts tests/core tests/infrastructure tests/cli
```

先在基线取得同一集合结果；新增失败为 0（既存债只能标 `BASELINE_EXCEPTION`）。整集约 30～45 分钟，须后台运行并监视。

**G2 防复发测试（GPT 明确要求的两类，必须各有独立测试，且用与真实事故等价的输入）**：
1. `doc check --strict` 型：卡里出现 `main.py doc check --strict` → 预检拒绝，并指出 `--strict` 不是 `doc check` 的选项；
2. 不存在测试路径型：卡里列出的既有测试路径在声明基线上不存在且未标“计划新增” → 预检拒绝；标“计划新增”则通过；标“存在”但实际不存在 → 拒绝；标“计划新增”但已存在 → 拒绝。

**G3 预检其他必测场景**：未知命令；未知子组；合法命令通过；`隔离基线` 占位符（基线未回写）；路径/命令/审批字段占位符；`隔离基线` 不可解析；基线漂移；缺 `基线状态` 列；`运行态` 路径的存在与缺失；`WORKTREE` 基线；结构化卡 `validate`/`dispatch` 被同一预检拦截；预检只读；对 019、020 的历史片段回放，均被拒绝或提示。

**G4 强制接入必测场景**：写入型 Work 不带 `--card-file` → 拒绝且无写入；带失败预检的卡 → 拒绝且无写入；scope 超出卡的路径 → 拒绝；通过预检且 scope 在卡内 → 成功，`source_fingerprint` 为 `card:<sha256>`；显式 `--source-fingerprint` 不被覆盖；`--read-only` 豁免；不存在“跳过预检”的选项（`--help` 核验）。

**G5 静态质量**：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m ruff check --no-cache <§4 中 Python 路径>
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m mypy --strict --no-incremental <§4 中 Python 路径>
git diff --check
```

不得用 `--follow-imports=skip` 或文件级抑制换绿。

**G6 既有 CLI 用例**：`tests/cli/test_continuity.py` 中原本创建写入型 Work 的用例，须通过一个测试辅助函数生成最小合法卡（路径标“计划新增”、基线取测试仓库 HEAD）后继续通过；**不得删除或放宽这些用例的断言**。

**G7 不触碰生产**：测试用临时仓库与临时库，不读写真实控制面；结束不残留 `.coverage`、缓存或临时仓库。

## 7. 实施授权签字门与 GUI 合同

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-GOV-IC02 V0.4` |
| 实施批准 | `PENDING`（委托执行，回执另行生成） |
| 最终验收 | `PENDING` |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| 隔离基线 | `7cfe227e7bf4a7df57d95644a80ea2652ef5a9cc` |
| Owned Paths | §4 的 11 个路径 |
| 执行模型 | `Claude Opus 5.5` |
| 明确禁止 | 旁路开关、范围外路径、直接 SQL、历史改写、Hook/release 修改、合并、推送、部署 |

本表不是授权真源。BL02 完成后必须回填精确基线并形成新版本；外部 Approval Receipt 绑定最终卡片 SHA-256、BL02 提交、WBS 真源、11 个 owned paths、允许/禁止动作、执行模型、审批人和审批时间。卡片自身不得包含自身 SHA-256。

### 7.2 授权成立与失效

1. 含占位符或未绑定 Approval Receipt 的计划模板不得创建写入型 Work/Run。
2. 本卡执行前必须先以人工等价流程证明自身满足 §5.1～§5.2；该证据随 Approval Receipt 保存。
3. 卡片、BL02 基线、WBS 真源、owned paths、执行模型或禁止事项任一漂移，旧审批立即失效。
4. 实施批准与最终验收分离；GUI 必须展示卡片版本/哈希、基线、11 路径和审批身份，并调用高层领域服务生成回执，禁止直接修改 Markdown、Decision JSON 或 canonical 数据库。

## 8. 治理执行顺序

1. 只读预检并输出事实表（§3）。
2. **由用户**通过 §7 签字门批准已回填 BL02 基线的最终卡片，再创建并批准独立 CHG 与精确 Decision（§4 路径）；Agent 不代为批准。
3. 高层服务创建 Work、Run 与有界租约；**本阶段的 Work 创建仍在强制接入落地之前进行，因此本卡自身按现有流程执行**，并在事实表里注明。
4. 在全新隔离候选（自 BL02 基线起步）中实施并完成 §6 门禁。
5. 创建当前字节 Checkpoint（`git_head` 为基线，dirty paths 为实际改动的 owned paths，evidence 逐文件记录 SHA-256 与判卷文件 SHA-256），随后走正常 Hook 提交；提交后核验提交内 blob 与 Checkpoint 记录逐一相同，否则停止。
6. Run/Work 终态、台账 reconcile；**CHG 最终收口由用户执行**。
7. 停止并向用户报告；SHA 与 ID 回写 024 §2。

**自举要求**：本卡在开工前，须先用手工方式完成 §3 的命令与路径核验并把结果写进事实表；本卡及 023～029 各卡自身也须满足 §5.1 的格式，否则强制接入落地后它们无法作为 Work 创建的依据。

## 9. 硬停止条件

- 基线不含 `implementation-card` 命令，或基线 SHA 与本卡不符；
- 需要 §4 之外的路径；
- 只能通过设置旁路开关、放宽校验、mock 命令树或 skip 才能变绿；
- 需要改数据库、历史事件、Checkpoint、Hook 安装、release 指针。
- 本卡仍含任意占位符，或卡片 SHA-256、Approval Receipt、BL02 提交、执行模型身份无法相互证明。

## 10. 交付物

1. 基线 SHA 与预检事实表；
2. CHG / Decision / Work / Run / Checkpoint ID；
3. 精确 diff 与最终 SHA-256；
4. G1～G7 矩阵、原始命令、Exit Code、输出位置；
5. G2 两类防复发测试的名称与对应真实事故的输入对照；
6. 不可变提交 SHA；
7. 明确声明：预检已被 `continuity work create` 强制调用（CLI 路径）；服务层与 Facade 路径未强制，已登记技术债；方案 C 为后续迭代。
8. Approval Receipt、最终卡片 SHA-256、BL02 基线、自举人工预检证据与双签字门状态。

## 11. 与其他阶段的关系

预检落地后，后续每张实施卡（含 026、028、029）应符合 §5.1 的格式并在开工前通过预检；但在卡 028 部署前，它只存在于候选，稳定运行时里没有。
