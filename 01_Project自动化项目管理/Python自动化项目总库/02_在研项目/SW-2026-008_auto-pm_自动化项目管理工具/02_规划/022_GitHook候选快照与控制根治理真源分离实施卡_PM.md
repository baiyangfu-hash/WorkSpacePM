# Git Hook 候选快照与控制根治理真源分离实施卡

> 卡片编号：`SW008-M2-GOV-HOOKCTX-001`  
> 状态：`IN_PROGRESS / CHG-SCPT-2026-347 纠正执行（CHG-346 失败历史保留）`  
> 项目归属：`SW-2026-008_auto-pm_自动化项目管理工具`  
> 变更类型：`BUG_FIX / GOVERNANCE_CONTRACT`  
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或同等级推理模型  
> 编制日期：2026-09-29  
> 禁用能力：`pm-workflow`

## 1. 背景与已确认事实

`CHG-SCPT-2026-345` 的三文件隔离候选已完成代码门禁和控制面验收，但执行正常本地隔离提交时，Git Hook 使用候选工作树内的历史台账去对账 control-root 当前 canonical 数据库，得到 `107 orphan` 并阻断提交；同一时点从主工作区根执行 `ledger reconcile SW-2026-008` 为 `0 missing / 0 orphan / 0 mismatch`。

已确认当前 Hook 已能把两个物理根传入启动器：

- `-w <WORKTREE_ROOT>`：触发提交的候选工作树；
- `--control-root <PROJECT_ROOT>`：主工作区控制根和稳定 runtime。

但 `git-hook pre-commit / commit-msg / preflight` 的判卷实现仍以单一 `workspace_root` 处理 Git 暂存证据和治理真源，造成两个时间维度混用：

1. 候选工作树中的 Git index、源码与测试字节属于候选快照；
2. CHG、版本台账和 `.auto-pm/continuity.db` 属于 control-root 当前治理状态。

因此本卡修复的是 **Git Hook 双根判卷合同**，不是重新实现 `CHG-SCPT-2026-345`，也不是整理主工作区历史脏文件。

## 2. 单一目标

令 Git Hook 在 linked worktree 中提交时满足以下可证明合同：

```text
候选 Git index / staged source / candidate HEAD
                    │
                    ├── 只从 WORKTREE_ROOT 读取
                    │
                    └── 通过同一 Git common-dir 证明与 CONTROL_ROOT 同仓

当前 CHG / 项目台账 / canonical continuity state
                    │
                    └── 只从 CONTROL_ROOT 读取和判卷
```

没有合法 control-root、无法证明同仓、候选 index 漂移、CHG 不唯一或治理状态不一致时必须 `fail-closed`；严禁静默退回候选历史台账，严禁静默跳过门禁。

## 3. 实施前基线门禁

执行 Agent 必须先只读完成以下预检并记录原始输出：

1. 确认主工作区为 `C:\Users\fubai\Documents\My_Workspace`，记录 `git rev-parse HEAD`、分支和状态；
2. 选择一个**干净、不可变、已包含 `f4626947`（CHG-336 Hook 双根启动器修复）及当前已验收 M2 基线**的提交作为新隔离候选起点；不得从主工作区脏状态、`runtime-context-contract-governed` 的 staged 现场或任一历史 C09/P2 脏工作树复制整树；
3. 核验基线的 `AppContext` 和根 CLI 已原生支持 `control_root`；若不支持，立即停止并报告基线错误，不得把第五个生产文件偷偷并入本卡；
4. 核验 `CHG-SCPT-2026-345` 候选保持原 HEAD、原三条 staged 路径和原哈希，实施本卡期间不得改动；
5. 核验当前没有正在使用拟建候选目录或分支的进程；
6. 只使用主工作区 `.venv\Scripts\python.exe -B` 和稳定根入口，不从候选目录的 release 指针加载 runtime。

任一事实与本卡不符，停在只读状态，不自行扩展范围。

## 4. 精确 Owned Paths

本卡源码改动严格限制为四个文件：

1. `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/git_hook.py`
2. `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/git_hook_enforcer.py`
3. `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_git_hook.py`
4. `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_git_hook_enforcer.py`

治理对象（CHG、Decision、Work、Run、Checkpoint、台账）按正常 PM 流程单独落账，不得计入上述四个产品代码路径，也不得把它们复制进候选以骗过 Hook。

### 4.1 提交证据层修订（2026-09-29，用户批准方案 A）

首次执行（CHG-346，Gemini）未走治理链且证据不足，其 `completed` 状态被状态机锁定，作为失败历史保留；纠正执行由 `CHG-SCPT-2026-347`、`DEC-20260929-HOOKCTX2`、`WORK/RUN-SW008-M2-HOOKCTX-002` 承载。

已部署的稳定 Hook 仍是旧合同：commit-msg 要求关联 CHG 与项目台账位于同一暂存快照。修复本身尚未生效，因此本次本地隔离提交按 IC01 的分层做法允许两条**提交证据路径**（不属于产品 owned paths，不进入 Run owned_paths）：

1. `04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-347.md`（自控制根原字节引入）；
2. `04_监控/01_变更管理/02_变更记录/01_版本变更台账.md`（仅在候选分支本地快照上增量加入 CHG-347 一行，不复制 canonical 全量台账）。

提交内容严格为四个产品路径加这两个证据路径，共六路径；出现第七路径即停止。

## 5. 必须实现的合同

### 5.1 CLI 双根传递

- `git_hook.py` 必须从 `AppContext` 分别取得：
  - `workspace_root` 作为 `candidate_root`；
  - `control_root` 作为 `governance_root`。
- `pre-commit`、`commit-msg` 和 `preflight` 必须把两个根显式传给判卷器；`preflight` 捕获一次候选 index 快照，并将同一对象交给两个子门禁。
- `release-gate` 仍只对 control-root 全局治理状态判卷，不得错误读取 linked worktree 历史台账。

### 5.2 同仓身份校验

判卷前必须证明：

- 两个根都可解析为真实绝对路径；
- `candidate_root` 是 Git worktree；
- `control_root` 是该仓库的 primary control root；
- 二者解析出的 `git common-dir` 完全一致；
- 不接受环境变量、junction、独立 `.git` 目录或任意外部路径伪造 control-root。

校验失败返回非零，不得 fallback。

### 5.3 候选证据边界

以下事实只允许从 `candidate_root` 读取：

- staged index 条目、object id 和不可变 staged snapshot；
- staged 生产代码归属路径；
- 候选 HEAD 与 index 漂移；
- 工作树字节与 staged blob 的一致性（如该检查适用）。

不得从 control-root 的 index 代替候选 index，也不得把主工作区未暂存源码混入判卷。

### 5.4 治理真源边界

以下事实只允许从 `control_root` 读取：

- 项目注册与 staged 路径到项目 ID 的映射；
- commit message 引用的当前 CHG 文件、唯一性、项目归属及合法状态；
- 当前版本变更台账；
- canonical `.auto-pm/continuity.db` 及 ledger reconcile 结果。

候选工作树中历史 CHG/台账缺失或陈旧不得造成假失败，也不得被当作当前治理真源。control-root 当前治理状态不一致必须真实阻断。

### 5.5 原有安全语义不得退化

- 生产代码仍必须绑定合法 CHG；
- 未知或多项目归属继续阻断；
- staged snapshot 读取失败继续阻断；
- CHG 缺失、重复、PID 不匹配或状态非法继续阻断；
- `pre-commit` 与 `commit-msg` 仍基于同一个候选 staged snapshot；
- 不允许 `--no-verify`、自动修台账、自动改 CHG、自动写数据库或自动安装 Hook。

## 6. 必测场景

至少增加以下自动化测试：

1. linked worktree 的候选 index 含生产代码，候选台账为旧快照，但 control-root 当前台账/canonical 为 `0/0/0`：门禁通过；
2. 候选 index 为空而 control-root 有 staged 文件：不得误判为候选提交；
3. control-root 当前台账不一致：门禁阻断；
4. 候选与 control-root 不属于同一 common-dir：门禁阻断；
5. control-root 缺失或不是 primary root：门禁阻断；
6. commit message 引用的 CHG 仅存在于候选旧快照、不存在于 control-root：门禁阻断；
7. CHG 在 control-root 存在但 PID 与候选生产路径不一致：门禁阻断；
8. `preflight` 只捕获一次候选 staged snapshot，并把同一对象传给 pre-commit 与 commit-msg；
9. `release-gate` 只使用 control-root，且保持全局严格门禁；
10. 安装脚本继续生成 `-w "$WORKTREE_ROOT" --control-root "$PROJECT_ROOT"`，不得退回单根调用。

测试 fixture 必须位于临时目录，不得读取或写入真实 canonical 数据库；测试结束不得残留 `.coverage`、缓存或临时仓库。

## 7. 验证命令

在新隔离候选的 SW008 项目根执行：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/cli/test_git_hook.py tests/infrastructure/test_git_hook_enforcer.py

& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m ruff check --no-cache auto_pm/ui/cli/git_hook.py auto_pm/infrastructure/git_hook_enforcer.py tests/cli/test_git_hook.py tests/infrastructure/test_git_hook_enforcer.py

& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m mypy --strict --no-incremental auto_pm/ui/cli/git_hook.py auto_pm/infrastructure/git_hook_enforcer.py tests/cli/test_git_hook.py tests/infrastructure/test_git_hook_enforcer.py
```

随后建立完全临时的 primary repo + linked worktree fixture，运行真实 Hook 集成测试，证明：

- Git evidence 来自 linked worktree index；
- 治理判卷来自 primary control-root；
- unrelated/external control-root 非零退出；
- 不产生真实工作区写入。

所有命令必须 Exit 0，且 `git status --porcelain` 只能出现四个 owned paths。若 Mypy 因既存依赖穿透失败，不得使用 `--follow-imports=skip` 或文件级抑制换绿，应报告精确基线差异并停止。

## 8. 治理执行顺序

1. 只读预检并输出事实表；
2. 新建独立 CHG（建议下一可用 `CHG-SCPT` 编号，名称为“Git Hook 候选快照与控制根治理真源分离”）；
3. 经用户批准后由 `DecisionService` 生成精确四路径 Decision；
4. 通过高层服务创建 Work/Run 和有界租约；禁止直接 SQL；
5. 在新隔离候选内实施四文件修复；
6. 完成测试、自检、Checkpoint、Run/Work/CHG 验收和 SW008 台账 reconcile；
7. 仅在 Hook 自身能够正常通过、提交内容严格等于授权范围时创建本地隔离提交；
8. 停止并提交证据报告。合并、推送、部署、release 切换、Hook 安装均需另行授权。

## 9. 与 CHG-345 的关系

本卡完成只代表 Hook 判卷合同具备修复候选，不自动改变以下事实：

- 不修改 `runtime-context-contract-governed`；
- 不重写 `CP-SW008-M2-RICTX-001`；
- 不把 CHG-345 标为 completed；
- 不自动重试 CHG-345 的隔离提交。

本卡形成有效本地提交并经独立复核后，才可单独申请一次“使用已修复 Hook 重试 CHG-345 原三文件隔离提交”的窄授权。重试时三文件 SHA-256、HEAD、Checkpoint 或 staged 路径任一漂移即停止。

## 10. 硬停止条件

出现以下任一情况立即保留现场并停止，不得补丁式扩大：

- 需要第五个产品/测试文件；
- 需要修改 `.git/hooks`、active/previous release、WBS 或 Obsidian 规范；
- 需要复制 CHG/台账/release 到候选；
- 需要直接修改 canonical 数据库或历史 Checkpoint；
- 需要清理主工作区或历史工作树；
- 无法证明 candidate/control-root 同仓身份；
- 测试只能通过 skip、ignore、mock canonical 或降低门禁；
- 发现现有 active runtime 与选择的源码基线合同不一致；
- 出现第六条脏路径、未知进程或未回收执行句柄。

## 11. 执行 Agent 交付物

执行 Agent 必须一次性交付：

1. 基线与双根身份事实表；
2. CHG / Decision / Work / Run / Checkpoint ID；
3. 四文件 diff 与最终 SHA-256；
4. 10 个必测场景的 PASS/FAIL 矩阵；
5. Pytest、Ruff、Mypy 原始命令、Exit Code 和输出位置；
6. 最终 `git status --porcelain`；
7. 本地隔离提交 SHA（如合法完成）；
8. canonical 对账结果；
9. 对 CHG-345 是否已具备“可重试原提交”的裁决：`PASS / FAIL / UNVERIFIED`。

不得仅以聊天陈述、“测试过了”或手工拼接日志代替物理证据。

## 12. 可直接交给执行 Agent 的提示词

```text
在 C:\Users\fubai\Documents\My_Workspace 接手 SW-2026-008 的 Git Hook 双根判卷合同修复。

先完整阅读根目录 AGENTS.md 和：
01_Project自动化项目管理/Python自动化项目总库/02_在研项目/
SW-2026-008_auto-pm_自动化项目管理工具/02_规划/
022_GitHook候选快照与控制根治理真源分离实施卡_PM.md

先只读执行实施卡 §3 预检并给出事实表。不要相信前序聊天结论，不要使用 pm-workflow。
本任务单一目标是：候选 Git index/源码证据只从 candidate root 读取；当前 CHG、台账、
canonical 状态只从 control-root 读取；二者必须证明属于同一 Git common-dir，否则 fail-closed。

严格 owned paths 仅为实施卡 §4 的四个文件。必须新建独立 CHG、Decision、Work、Run，
并在新的干净隔离候选中实施。禁止直接 SQL、--no-verify、复制台账/CHG/release、修改历史
Checkpoint、清理工作区、合并、推送、部署、切换 release 或安装 Hook。

不要改动 CHG-SCPT-2026-345 的三文件候选；它只是复现证据。本任务完成后也不要自动重试
CHG-345 提交。若需要第五个文件或任何边界外操作，立即停止并报告，不得自行扩大。

实施后完成 §6 全部场景、§7 三类门禁、真实临时 primary+linked-worktree Hook 集成测试，
再按高层服务完成 Checkpoint 和验收。交卷前按 §11 自检并一次性提交完整证据。
```

