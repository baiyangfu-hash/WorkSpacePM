# V06｜双 Hook 真实拒绝实施卡（钩子一半）

> 卡片编号：`CARD-SW008-M2-V06`
> 对应 WBS：`V06`（WBS V3.0.22 第 786 行“双 Hook 与坏证据负向实演”）的**钩子一半**；判卷反例一半见 §1.4 与 §11
> 版本：`V1.0`（2026-10-07，一次定稿；执行期间不得修订，见 §9）
> 状态：`PLANNED / NOT_AUTHORIZED`（定稿，待授权；授权方式见 §7）
> 档次：测试档（规则文档 §3：仅测试，产品字节必须不变；相关完整测试组、测试健康检查、类型与静态检查、对新增断言做变异检查）
> 依赖：V04-T（卡 063）已提交并收口（CHG-SCPT-2026-388 completed，由启动脚本核验）
> 隔离基线：`715713bb24d7439a953a2938b8751a1352495cd3`（V04-T 的提交，分支 `codex/m2-v04t-e2e-proofs`）
> 治理任务真源：WBS 提交 `0b56b2f4de2b35effea7e100ab2c56bc1cec0bc7`（V3.0.22）
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

> 说明：GPT 交付了范围勘测与草稿 V0.1（`.auto-pm/reports/m2-gpt-r2-20261007/V06_DRAFT_V0.1.md`，只读设计）。我对照源码核实后自己写成本卡的 1 个新增测试文件，并在全新基线副本上跑过（§1.5）。参考文件、变异计划与脚本、判卷脚本、安装脚本与演练输出归档于 `.auto-pm/reports/m2-v06/`，仅供参考；执行者不得现场修订本卡、扩大路径或放宽门禁；遇到本卡未覆盖的情况按 §9 停止并报告。

## 1. 背景与已核实事实（2026-10-07，基线 `715713bb`，均为源码、命令或日志核验）

1. **WBS 要求**：V06 要证明两个钩子在隔离 Git 测试仓里分别拒绝：错 CHG、坏台账、空壳证据、越权文件、预检异常；不得破坏真实用户项目来造测试；另有“坏证据反例”（空集合、错卡或基线或 Run、报告映射缺项、陈旧或漂移字节须明确 FAIL 或 UNVERIFIED，测试报错不得充当成功反例）。
2. **现有覆盖的缺口**：`tests/cli/test_git_hook.py` 与 `tests/infrastructure/test_git_hook_enforcer.py` 是单元级与探针级——真实 `git commit` 只配了一个桩 `main.py` 记录路径，拒绝场景用 monkeypatch 与注入的暂存快照；**没有**在真实隔离仓库里用 `git-hook install` 写出的真实钩子、真实检查器、真实 `git commit` 去证明拒绝，也没有“同一个夹具的正例能提交”的对照（没有对照，夹具坏了也会让所有负例看起来“被拒”）。
3. **我核实的行为**（在隔离仓库里实测）：产品自己的 `change create`/`transition`/`ledger reconcile` 命令能造出台账一致的夹具（对账 0/0/0，约 9 秒）；真实钩子对正例放行并打印“相关项目台账门禁校验通过”“强校验绑定通过”；钩子脚本以 `exit $?` 传递检查器的退出码，所以检查器崩溃也阻断提交；pre-commit 负责台账一致性与生产文件归属，commit-msg 负责变更单绑定与合法执行态。
4. **本卡只做钩子一半**：WBS 的“坏证据反例”要调用 `verdict_check.py`，该工具在控制根 `.auto-pm/reports/m2-tools/`，**不在 Git 里**，新检出没有它；用不可复现的外部依赖做测试会让测试在别处失败或被迫跳过，所以如实留作后续事项（工具先进入 Git 或另立工具卡，再补那一半），不在本卡冒充完成。“空壳证据”在钩子层的对应物是空台账：本卡的 g07 用台账与变更单不一致证明，另在探索中验证过清空或写入垃圾字节的台账同样被“台账未闭环”拒绝，未列为独立测试。
5. **我在全新基线副本上的演练**（2026-10-07，非受治理执行，受治理执行里完整重跑，不采纳这些输出；输出在 `.auto-pm/reports/m2-v06/gates_rehearsal/`）：
   ① `ruff check` 与 `mypy --strict` 对该文件零问题、`git diff --check` 通过；
   ② G1：26 passed、1 failed（既存，与基线相同：26 passed、1 failed）；
   ③ 新测试文件整体 **9 passed**（0:01:39）；
   ④ **严格变异检查**：7 个变异（改钩子检查器与钩子脚本模板这两个产品文件）全部被点名的测试以**真实断言失败**抓住，点名的测试先在未变异字节上为绿，每个文件逐字节还原：
   - M01-the-missing-change-request-check-is-off：a commit message without a change request is refused for that reason
   - M02-two-change-requests-are-accepted：a commit must bind exactly one change request
   - M03-the-legal-state-check-is-off：a change request that is not approved yet blocks the commit
   - M04-the-ledger-gate-is-off：a ledger that does not match its change requests blocks the commit
   - M05-an-unowned-production-file-gets-an-owner：a production file that no project owns blocks the commit
   - M06-the-pre-commit-script-ignores-the-checker：the pre-commit hook script blocks the commit when its checker fails
   - M07-the-commit-msg-script-ignores-the-checker：the commit-msg hook script blocks the commit when its checker fails
   ⑤ **相关完整组 `rest`**（含 `tests/e2e`）：717 passed（基线 708，另加新测试 9）、15 failed、13 skipped（0:20:58），失败集合与卡 063 的真实门禁输出逐个相同。
6. **基线数字**（本卡基线的代码字节与卡 063 提交的相同，沿用其真实门禁输出 `.auto-pm/reports/m2-v04t/gates/g2_candidate/rest.txt`）：`rest` 组既存 15 个失败；G1 集合在基线上 **26 passed、1 failed（既存）、0 skipped**。
7. **新增测试**：共 **9** 个，在 1 个新增文件里；没有旧测试被改动；确切的节点清单归档在 `new_nodes.json`，G3 逐个比对。
8. **限度（如实）**：夹具用产品命令造，若这些命令以后改变，夹具需要同步；钩子在 Windows 上由 Git for Windows 的 sh 执行；预检异常用“检查器崩溃”实演（真实的 Python 异常、真实的非零退出），不是逐个注入内部函数的异常；判卷反例一半未覆盖；这些测试尚未被独立审计。

## 2. 单一目标（用户故事与完成定义）

作为维护者，我希望两个真实钩子的拒绝能力有端到端的、可重复的证明：

1. 在一个隔离的真实仓库里，正例通过两个钩子提交成功；
2. 无变更单、变更单不存在、两个变更单、变更单未获批准，分别被 **commit-msg** 以对的理由拒绝；
3. 归属未知的生产文件、台账与变更单不一致，分别被 **pre-commit** 以对的理由拒绝；
4. 检查器崩溃（pre-commit 脚本，或只在 commit-msg 脚本）也阻断提交；
5. 每次拒绝后 HEAD 不动、暂存区原样；
6. 既有测试全部保留，相关完整组 `rest` 与基线逐个一致（失败集合相同、通过数恰为基线加 9、跳过数不变）。

依据 PM-042、PM-033、DEV-300 与 DEV-210；规范只读。无 UI 改动，HTML 原型不适用。

## 3. 实施前预检（只读，先于任何写入）

1. 核验本卡字节 SHA-256 与向用户报告的一致；核验 V04-T 的 CHG-SCPT-2026-388 已 completed、分支 `codex/m2-v04t-e2e-proofs` 仍在 `715713bb`。
2. 运行 `main.py implementation-card precheck --card-file` 对本卡，退出码必须为 0。
3. 核验 §4 中 1 个“计划新增”路径在基线上不存在。
4. 在隔离候选里、安装之前，对 §6 G1 集合复现基线结果（**26 passed、1 failed（既存）、0 skipped**），输出写入 `.auto-pm/reports/m2-v06/gates/G1_baseline_candidate.txt`；不一致则停止。
5. 核验隔离候选 HEAD 等于基线且工作树干净。
6. 阅读 `.auto-pm/reports/m2-v06/proto/` 下的参考文件，核对 `reference_manifest.json` 中各文件与工具的 SHA-256。
7. 判卷、检查与变异脚本已在参考字节上跑通（§1.5）；工具字节一旦被证据绑定，任何修正都会使整个窗口重开。后台起长批次用 `nohup`，并确认输出文件真的开始增长。`rest` 组约 20 分钟、变异检查约 10 分钟，所以 Run 需要续租循环（`p1_renew_loop.sh`，**必须从仓库根、用 `.auto-pm/reports/...` 开头的路径启动**，每 1200 秒续一次）；**回归与变异检查必须顺序执行，不得与其他重负载同时跑**（开工时创建重负载标记 `.auto-pm/reports/HEAVY_GATES_RUNNING`）。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `tests/e2e/test_pmf_gate_failures.py` | 计划新增 | 新增：真实隔离仓库里两个真实钩子的拒绝实演，9 个测试 |

出现第 2 条脏路径即停止，不得现场扩大 Decision。治理证据对象在控制根落账，不计入上述路径；产品文件（钩子检查器与钩子模板只在变异检查里被临时改动并逐字节还原）、既有测试、共享夹具、`conftest`、测试配置、台账、WBS 本卡都不改。

## 5. 合同（全部定稿，执行者不得改写含义）

### 5.1 最终字节

1 个文件的字节固定为参考字节（UTF-8、LF、无字节序标记），归档为 `.auto-pm/reports/m2-v06/proto/` 下的同相对路径文件；`install_candidate.py` 逐字节核验后装入候选（先确认该文件在候选里不存在），不得手工改写。

| # | 路径 | 基线状态 | 最终 SHA-256 |
|---|---|---|---|
| 1 | `tests/e2e/test_pmf_gate_failures.py` | 计划新增 | `4d9f31b64b25855b7496acdd1b03913a2319f03a8e86339389435df9dc6d5d0f` |

检查与构建工具（`reference_manifest.json` 里的 `tools/` 条目，字节固定）：

| 工具 | SHA-256 |
|---|---|
| `commit_msg.template.txt` | `e3ae87456513512286ef338d82b301e84c072639615ad42ae31e0f22d748e89f` |
| `g6_check.py` | `80ee6daa3a59ef424211881ad9b93af34348690de943d6a2a83d3387dad8e591` |
| `install_candidate.py` | `43e068993e9cbbfa0cc44ac19d18e71765b1e9cd2163cf89cbe0b2287bbe029d` |
| `m2-tools/mutation_classify.py` | `0fff21f888cb1a50094f050ef8bc3b42ea25653ba508581e3c85fa1b28d79019` |
| `m2-tools/verdict_check.py` | `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188` |
| `mutation_plan.json` | `8401cdf19233c91e2ee1b49298aa35d6cdd4b2ec8397d9627fb5250ab0123f0b` |
| `mutation_run.py` | `346e19e20e047f1e3686be167d6abfb033e8513c0f0e75f7a79971bffab99698` |
| `new_nodes.json` | `5ddea88303650e05dd7f0bbf2758f1bfdd427046e6d48bb73ae8ed84527c8af1` |
| `run_g2.sh` | `10b906ffd3424a7f94faf4100f85ba1d32319e650a3e7d61aa9c08656872508a` |
| `run_gates_fast.sh` | `c4f0b257b4a977b38739502fabdc4fb3178b60075c30047b1065cd9433ccb53c` |
| `run_gates_g2.sh` | `72992e5ff87f14d6fcb9baef04fd43a083ec15b54a0257b14c9cfa77810528be` |
| `run_gates_v06.py` | `f3ec34067adb7535c33ab2ee11e413b7a00ecee2d324b3919126cb2d4b018ccf` |

### 5.2 行为合同

**5.2.1 夹具**：在临时目录建 Git 仓库，含一个已登记项目（`.copier-answers.yml`）与一个生产代码文件；经产品命令 `change create`、`change transition`（到 `implementing`，或为 g05 停在 `submitted`）与 `ledger reconcile` 创建变更单并把台账对账到 0/0/0；用 `git-hook install` 装钩子；修改生产文件并暂存全部变更。夹具里 `main.py` 只是 `from auto_pm.cli.__main__ import cli` 的启动器（被 `.gitignore` 忽略，不进暂存区）。

**5.2.2 拒绝的统一断言**：`git commit` 返回非零；`HEAD` 不变；暂存区文件列表不变；输出里有拒绝它的那个钩子的标签（`[auto-pm pre-commit]` 或 `[auto-pm commit-msg]`）与该场景的拒绝理由原文。正例断言：返回零、`HEAD` 前进、输出同时含两个钩子的通过语句。

**5.2.3 崩溃实演**：把夹具里的 `main.py` 换成会抛 `RuntimeError` 的脚本（g08，只在参数含 `pre-commit` 时崩，其余照常启动产品）或只在参数含 `commit-msg` 时崩的脚本（g09，pre-commit 先通过再由 commit-msg 的检查器崩溃）；提交必须被阻断，输出含崩溃标记，HEAD 与暂存区不变。

### 5.3 必测场景（G3）

新增的 9 个测试：

| 测试 | 拒绝它的钩子 | 要证明的行为 | 个数 |
|---|---|---|---|
| `test_g01_the_positive_control_commits_through_both_real_hooks` | — | 同一夹具的正例：两个钩子都跑、都同意，提交成功（排除“夹具坏了所以什么都被拒”） | 1 |
| `test_g02_a_commit_message_without_a_change_request_is_refused_by_commit_msg` | commit-msg | 未绑定变更单 | 1 |
| `test_g03_a_change_request_that_does_not_exist_is_refused_by_commit_msg` | commit-msg | CHG/PID/台账证据不完整或不一致 | 1 |
| `test_g04_two_change_requests_in_one_commit_are_refused_by_commit_msg` | commit-msg | 必须且只能绑定一个变更单 | 1 |
| `test_g05_a_change_request_that_is_not_approved_yet_is_refused_by_commit_msg` | commit-msg | 尚未获得审批批准（变更单停在 submitted） | 1 |
| `test_g06_a_production_file_that_no_project_owns_is_refused_by_pre_commit` | pre-commit | 暂存生产文件归属未知或不唯一 | 1 |
| `test_g07_a_ledger_that_does_not_match_its_change_requests_is_refused_by_pre_commit` | pre-commit | 关联项目台账未闭环（台账里多一行没有变更单的记录） | 1 |
| `test_g08_a_checker_that_crashes_in_pre_commit_still_blocks_the_commit` | pre-commit 脚本 | 仅 pre-commit 的检查器崩溃也阻断提交（commit-msg 根本没有机会运行） | 1 |
| `test_g09_a_checker_that_crashes_only_in_commit_msg_still_blocks_the_commit` | commit-msg 脚本 | pre-commit 通过、仅 commit-msg 的检查器崩溃也阻断提交 | 1 |

### 5.4 明确不做

产品代码、既有测试、共享夹具、`conftest` 与测试配置、台账与 WBS；判卷反例一半（见 §1.4）；用真实用户项目造测试；既有测试的删减、`skip`、抑制（`type: ignore`、`noqa`）；不用 `--no-verify`；不改 `.git/hooks` 下的真实钩子；不合并、不推送、不部署、不切换 release。

## 6. 门禁矩阵

门禁在隔离候选的最终字节上运行（快速部分 `run_gates_fast.sh`，相关完整组 `run_gates_g2.sh`，判卷 `run_gates_v06.py`，均只读，判卷在任一门禁不过时以非零退出；变异检查会临时改动并逐字节还原钩子的两个产品文件，所以排在其他快速门禁之后、完整组之前单独跑，脚本已按此顺序编排）。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 夹具健康与冒烟 | `tests/test_fixture_health.py`、`tests/test_smoke.py`、`tests/test_import.py` | 候选与安装前的基线完全相同：26 passed、唯一失败是既存的 `test_no_conditional_assertion_skips`、0 skipped |
| G2 相关完整组 | `rest`（含 `tests/e2e`）对照卡 063 的真实门禁输出 | 失败集合与基线逐个相同；通过数恰为基线加 9；跳过数与基线相同；退出码与基线相同；无报错节点 |
| G3 必测场景 | 新测试文件的收集结果 | 恰为 `new_nodes.json` 的 9 个新节点 |
| G4 静态质量 | 对该 Python 文件运行 `ruff check --no-cache` 与 `mypy --strict --no-incremental`；`git diff --check`；字节扫描 | 全部退出码 0；字节扫描零发现；新增行（含新增文件的全部行）中没有 `type: ignore`、`noqa`、`follow-imports=skip`、`pylint: disable` |
| G5 范围与最终字节 | 变更集与指纹 | 变更集恰为 §4 的 1 个路径；其 SHA-256 等于 §5.1；无缓存与临时文件残留；门禁前后字节记录相同 |
| G6 既有内容不变 | `g6_check.py` 对照由基线提交导出的目录树 | `templates` 与 `auto_pm` 字节不变；`tests` 与基线的差异恰为这 1 个新增测试文件 |
| G7 不触碰生产 | 新增测试行扫描、真实钩子记录与残留进程检查 | 新增的测试行不含对真实控制根（`My_Workspace`）的引用；真实 `.git/hooks` 下的文件在全部门禁前后字节相同；门禁前后 pytest 相关的 Python 进程数相同 |
| G8 负向对照 | `mutation_run.py`（计划 `mutation_plan.json` 的 7 个变异，判据 `m2-tools/mutation_classify.py`） | 计划的 SHA-256 等于指纹清单；点名的测试组先在未变异字节上全绿；每个变异让点名的测试出现真实断言失败；每个被改的文件逐字节还原；候选文件前后与冻结字节相同 |
| G9 新测试文件整体 | `tests/e2e/test_pmf_gate_failures.py` | **9 passed、0 failed、0 skipped**，退出码为 0 |

**提交与收尾**（由提交脚本执行）：创建当前字节 Checkpoint 后走正常 Hook 提交（不得 `--no-verify`）；提交内 blob 与 Checkpoint 逐一相同；`main.py ledger reconcile SW-2026-008` 为 0/0/0。

## 7. 实施授权签字门

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-V06 V1.0` |
| 实施批准 | `PRE_AUTHORIZED_CONDITIONALLY`：用户 2026-10-07 的有条件预批准（原话见 `.auto-pm/reports/PREAUTH_M2_20261007.txt`）——前提是本卡最终 SHA 已在聊天中向用户报告、卡字节与该 SHA 一致、机器预检通过、范围不超出 §4 的路径；任一门禁不过即停下保留现场并等用户，不得重跑到绿；同一问题最多修 2 轮（V06 另允许最多重试 2 次，仍失败就写给 GPT 的交接）；V06 单卡总时长上限 10 小时（从 2026-10-07 19:20 算起）；连续 2 张卡失败即整体停下 |
| 最终验收 | `DELEGATED_CONDITIONALLY`：用户 2026-10-07 委托验收与 CHG 收口，条件是 G1～G9 全部通过且提交与 Checkpoint 一致；用户可复核并推翻 |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| 隔离基线 | `715713bb24d7439a953a2938b8751a1352495cd3` |
| Owned Paths | §4 的 1 个路径 |
| 执行模型 | `claude-sonnet-5-5` |
| 明确禁止 | 第 2 条路径、任何产品文件、既有测试、共享夹具、`conftest` 与测试配置、台账、WBS、既有 CHG、PM_SESSION、Obsidian 规范、Hook 脚本本身与 release、直接改真实库、历史改写、合并、推送、部署、V05-C 与真实模型调用 |

### 7.2 授权成立与失效

1. 卡片字节、隔离基线、owned paths、执行模型或禁止事项任一漂移，预批准立即失效。
2. 外部 Approval Receipt 绑定本卡完整字节 SHA-256、基线、1 个路径、最终文件 SHA-256、允许与禁止的动作、执行模型、审批人与时间；卡片自身不含自身 SHA-256。
3. 委托验收只在 §7.1 的条件全部成立时由收口脚本执行，并在 CHG 里写明“委托验收，非用户当场验收”。
4. V04-T 未收口前，本卡不得开工（由启动脚本核验）。

## 8. 治理执行顺序

1. 只读预检并输出事实表（§3），含安装前的 G1 基线。
2. 创建并批准 SW-2026-008 的独立 CHG（领域 SCPT，性质 OPT）与精确 Decision（§4 的 1 个路径；`DEC-<起卡当天日期>-V06HOOKS`）。
3. 创建 Work（`--card-file` 指向本卡；`WORK-SW008-M2-V06-001`）、在全新隔离候选（自 `715713bb` 起，分支 `codex/m2-v06-hook-refusals`，工作树 `.auto-pm/worktrees/m2-v06`）启动 Run（`RUN-SW008-M2-V06-001`，`--lease-seconds` 不超过 3600）；启动续租循环；运行全部门禁。
4. 装入参考字节、运行 §6 门禁；判卷结果写入 `.auto-pm/reports/m2-v06/gates/`。
5. 创建当前字节 Checkpoint（`git_head` 为基线，记录文件的 SHA-256 与判卷文件 SHA-256），**先于提交**；随后走正常 Hook 提交；提交后核验提交内 blob 与 Checkpoint 相同，否则停止。
6. Run/Work 终态、`main.py ledger reconcile SW-2026-008` 为 0/0/0；按 §7.1 的条件由收口脚本验收并收口 CHG。
7. 向用户报告后继续下一项（按预授权）；SHA 与 ID 写入状态页。

## 9. 有界纠正与硬停止条件

本卡单提交，一个主 Run；**执行期间不得修订本卡**；需要修订本卡即属于硬停止。任何门禁失败都不得靠重跑、改字节或放宽判据达成通过：保留现场与输出、停止并报告，由用户裁决。同一问题最多修 2 轮；V06 允许最多重试 2 次，仍失败就停下并准备给 GPT 的交接，不换花样硬试。

以下任一情况立即保留现场、停止并报告：

- 基线 HEAD、runtime 身份、Decision 字节或 owned paths 不一致，或需要第 2 条路径；
- 需要改 §4 之外的产品文件、既有测试、WBS、既有 CHG 才能让测试通过；
- 只能通过 Mock 业务结果、硬编码预期输出、跳过测试、放宽断言或抑制才能通过；
- 任一门禁不通过，或 G8 的任一变异存活、任一还原字节不一致；G7 发现测试结束后仍有遗留进程；
- 真实 `.git/hooks` 的文件前后字节不同；
- Checkpoint 不是当前字节，或质量门未完整返回；
- Run 租约已过期：停止并报告，不得自行走恢复链；
- 发现本卡与事实矛盾（先停止，由用户裁决是否出新版本，不得自行改卡）；
- 本卡总时长超过 10 小时（从 2026-10-07 19:20 算起，不含等用户）。

## 10. 交付物

1. 基线 SHA 与预检事实表（含安装前的 G1 基线）；
2. CHG / Decision / Work / Run / Checkpoint ID 与 Approval Receipt；
3. 精确 diff 与该路径的最终 SHA-256；
4. G1～G9 矩阵、原始命令、Exit Code、输出位置；
5. G3 场景与测试名称的对照表；
6. 不可变提交 SHA 与 Checkpoint 绑定核对；
7. 明确声明：两个真实钩子在真实隔离仓库里对 6 类坏证据各自以对的理由拒绝，检查器崩溃也阻断提交，正例对照能提交。**已知限制必须如实报告**：判卷反例一半（verdict_check.py 不在 Git）未覆盖；夹具依赖产品命令；预检异常用检查器崩溃实演；这些测试尚未被独立审计。

## 11. 与其他任务的关系

- **WBS V06 的判卷反例一半**：待 `verdict_check.py` 进入 Git 或另立工具卡之后补做；届时登记到台账并出卡。
- 之后拟：台账状态更新小卡（TD4）；提速测量（并行 `core` 验证与耗时画像）；V05-B3 的重跑（第一次执行因与本改动无关的测试在负载下失败，等用户决定）；V05-C 须用户先授权真实模型调用。
