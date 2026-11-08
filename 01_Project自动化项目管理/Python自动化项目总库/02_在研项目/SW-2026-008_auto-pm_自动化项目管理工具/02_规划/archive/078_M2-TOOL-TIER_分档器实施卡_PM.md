# M2-TOOL-TIER｜分档器实施卡

> 卡片编号：`CARD-SW008-M2-TIER`
> 对应 WBS：`M2-TOOL-TIER`（规则文档 V1.1 §11）
> 版本：`V1.0`（2026-10-09，一次定稿；执行期间不得修订）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-08 预授权分档器卡“赶得上就做”，2026-10-09 白天再次预授权；原话均见 `.auto-pm/reports/PREAUTH_M2_20261008.txt`；条件见 §7）
> 档次：**测试档**（规则文档 §3：只新增测试与测试辅助工具；相关完整组 `rest`，含 tests/e2e；不改任何产品文件）
> 依赖：RULE（卡 077，CHG-DOCU-2026-024 completed，由启动脚本核验）
> 隔离基线：`a0ac852badd1ae6bc4a533f8f4e66a641b79126d`（分支 `codex/m2-rule-docs`）
> 治理任务真源：WBS 提交 `a538f942f1995f1ec3e50ad45c624bdc123c6bc3`（V3.0.23）
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

## 1. 背景与已核实事实（2026-10-09，基线 `a0ac852b`）

1. **为什么要这张卡**：规则文档 V1.1 的 §1 写“分档取实际改动与验证工具变动的最高风险档，不由执行者自选；未知路径或无法归类就拒绝定档并按核心档评审”，§11 写“分档器只能推荐，不能降档”，§3 写 conftest、全局夹具等跨组影响不能当普通测试。但**分档器本身还不存在**——档次现在靠人工核对，正是规则要防止的“自选档次”。本卡把这些条文变成可审计的代码。
2. **做什么**（三个新增文件，其余零改动）：
   - `tests/tools/tier_classifier.py`：从改动路径算出档次。路径先归一化（斜杠、大小写、`./`、项目前缀），拒绝绝对路径、上跳和空改动集；按规则匹配，**同一路径命中多条规则时取最高档**；没有任何规则命中的路径按核心档并列入 `unknown`；文档目录里的脚本、配置、模板、查询类后缀升为产品档；改动集的档次取各路径的最高档；`check_declared` 只允许卡声明的档次**等于或高于**算出的档次；可从 `git diff`（重命名视为旧路径删除加新路径新增）和未跟踪文件读取改动路径；命令行退出码 0/2/3；每个结果带规则表版本与 SHA-256。
   - `tests/tools/tier_core_list.json`：版本化规则表（`m2-tier-rules.v1`，版本 1.0），共 57 条规则。核心档清单取保守口径：合同（contracts）、存储与迁移、连续性与执行授权与租约、任务与变更单状态机、发布与启动基础设施、运行态目录；产品档含其余产品包、模板、脚本、构建与测试配置、运行时读取的变更单与会话文件、跨组测试基础设施；测试档为 tests/ 其余；文档档为各类文档目录。**这是第一版，宁严勿松**；放宽只能由后续卡经批准修改。
   - `tests/e2e/test_pmf_tier_classifier.py`：73 个测试节点，含用已验收各卡的真实改动路径回放（F02 核心、F01-1 产品、V06B/V06C/V06D/V05-C 测试、TD7/RULE 文档、WBS 文档、过期 Run 恢复核心）、规则表的校验与被拒绝的坏规则表、git 改动读取（重命名、未跟踪）、命令行退出码、以及“项目里每个已跟踪文件都能被归类，未知项恰为已知集合”。
3. **本卡的限度**：分档器**只推荐**，本卡不把它接进启动脚本、判卷器或卡预检（那是后续接线，需要核心档改动与批准）；规则文档 §11 的机器落地缺口由此变小但未关闭。规则表的口径是第一版，可能把个别文件定得过严，不会过松。
4. **我在全新基线副本上的演练**（2026-10-09，非受治理执行，受治理执行里完整重跑，不采纳这些输出；输出在 `.auto-pm/reports/m2-tier/gates_rehearsal/`）：
   ① `ruff check` 与 `mypy --strict` 对两个 Python 文件零问题、`git diff --check` 通过；
   ② G1：26 passed、1 failed（既存，与基线相同：26 passed、1 failed）；
   ③ G9：73 个测试 73 passed、0 failed、0 skipped；
   ④ G8：17 个变异在未变异字节上先为绿，变异后各被点名测试的真实断言失败杀死，字节逐一还原，完整输出已保存；
   ⑤ G6：除这三个新增文件外 `templates`、`auto_pm`、`tests` 树与基线逐字节相同；
   ⑥ G2 的 rest 组回归不在这次演练里重跑；完整 rest 组由正式门禁重跑，基线取卡 075（V05-C）受治理执行的真实输出。
5. **演练中得到的两个设计修正**（已体现在冻结字节里）：大小写与前缀的测试曾用“未知路径也是核心”会误判通过的样例，已改成只有真实命中规则才可能得到期望档次的样例；跨组测试基础设施（conftest、shared fakes、tests 包标记）按规则升到产品档，而不是核心档，因为规则文档 §3 只要求扩大到九组。
6. 与本卡同日的其他事实：本卡在 V05-C（真实模型联验）、方案 A（两个过期 Run 的处置）、TD7（台账）、RULE（规则文档）之后；本卡不调用真实模型。

## 2. 单一目标与完成定义

新增三个文件，让“从改动路径算出档次、拒绝低档声明”这件事被代码与测试证明，并与已验收各卡的档次一致。其余产品、模板、台账、WBS 均零改动。

73 个新增测试节点（均在 `tests/e2e/test_pmf_tier_classifier.py`）；17 个变异（对象是分档器代码、规则表与测试本身，每个由点名测试的真实断言失败杀死）：
   - M01-an-unknown-path-is-not-core：a path no rule names is reviewed as core, never as documentation
   - M02-the-lowest-tier-of-the-change-wins：the tier of a change is the highest tier among its paths
   - M03-case-matters：matching ignores the case of the path (Windows file names)
   - M04-a-behaviour-suffix-in-docs-is-documentation：a script or configuration under a docs folder is not plain documentation
   - M05-a-declared-tier-may-undercut：a card may not declare a lower tier than the computed one
   - M06-an-empty-change-set-is-accepted：nothing to classify is refused, not called docs
   - M07-untracked-files-are-ignored：untracked files of the working tree can be included in the change
   - M08-a-conftest-is-an-ordinary-test：a conftest is cross-group test infrastructure, not an ordinary test
   - M09-contracts-are-not-core：contracts are core
   - M10-absolute-paths-are-accepted：an absolute path is not a repository-relative change
   - M11-parent-traversal-is-accepted：a path that climbs out of the repository is refused
   - M12-the-project-prefix-is-kept：the project prefix is removed before matching
   - M13-a-rename-is-one-path：a rename counts as the old path removed and the new path added
   - M14-the-same-path-is-counted-twice：one path written twice is counted once
   - M15-the-unknown-tier-can-be-lowered-by-the-rules-file：a rules file cannot lower the tier of an unknown path
   - M16-duplicate-rule-ids-are-accepted：a rule id is unique, so a rule cannot hide behind another
   - M17-core-runs-no-more-than-product：the core tier adds real-process, concurrency and state-boundary coverage

## 3. 实施前预检

1. 核对卡字节与已向用户报告的 SHA 一致、基线、WBS、3 个 owned path 及参考字节。没有这些，不创建 CHG/Decision/Work/Run。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空；预检仅读，不代表获批。启动脚本另有 `--check-only` 模式，只做上述检查、不写任何东西。
3. 核对前置 CHG-DOCU-2026-024 completed；核对历史失败记录仍在原状态且本卡不触碰。
4. 新候选 HEAD 等于基线且 clean；三个新增路径在基线不存在；工具与参考字节均匹配冻结指纹。
5. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`，门禁期间每次检查先看续租日志（规则文档 §15）。

## 4. 精确 Owned Paths（3）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `tests/e2e/test_pmf_tier_classifier.py` | 计划新增 | 证明分档器的测试：回放已验收各卡的真实改动路径、各条拒绝、规则表校验、命令行退出码 |
| 2 | `tests/tools/tier_classifier.py` | 计划新增 | 分档器代码：路径归一化、规则匹配（取最高档）、未知路径按核心档、只推荐不降档、读取 git 改动 |
| 3 | `tests/tools/tier_core_list.json` | 计划新增 | 版本化规则表：核心清单与各档路径规则，带版本号 |

出现第 4 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-tier/`、本卡文件、演练工作树）不是额外产品 owned paths，不进本卡产品提交。

## 5. 字节合同

### 5.1 参考字节指纹

三个新增文件的最终 SHA-256（UTF-8、LF、无 BOM）；冻结文件保存在 `.auto-pm/reports/m2-tier/proto/`。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `tests/e2e/test_pmf_tier_classifier.py` | 计划新增 | `c7fd1e77c0913cbc430751380442cbd259c125b4df2584593ad58c5cc1b9eeff` |
| 2 | `tests/tools/tier_classifier.py` | 计划新增 | `1a931258270b24209b50803dc6b1e7b0293529ebe1b28d8f78657f64c568f13a` |
| 3 | `tests/tools/tier_core_list.json` | 计划新增 | `26e3480c6420566619e9d13c98f0b761ffdd01ff0924417ba7e9b65568355e4a` |

### 5.2 冻结工具

工具与脚本由卡 071（V06D，测试档、rest 组）的已演练工具与卡 074（F02）的启动与收口脚本派生（`.auto-pm/reports/m2-tier/`）；共用判卷脚本仍是控制根下的外部副本。变异运行器保存每次运行的完整输出并绑定进判卷文件。G2 的基线取卡 075（V05-C）受治理执行的 rest 组真实输出。

| 工具 | SHA-256 |
|---|---|
| `commit_msg.template.txt` | `5ffc8226fbdaec128b8bf7d720850f8fcc4e907fb410b85bbb8da24e4be99804` |
| `g6_check.py` | `1fdf1ed29ee2fa5696bee641f6d7d4228af4c5a8d71cd29ec4b37419f34323bd` |
| `install_candidate.py` | `07121b961fc32d7b077274af2718d91582e720556c8649a19f63ba01fdba7c98` |
| `m2-tools/mutation_classify.py` | `0fff21f888cb1a50094f050ef8bc3b42ea25653ba508581e3c85fa1b28d79019` |
| `m2-tools/verdict_check.py` | `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188` |
| `mutation_plan.json` | `47bb5d641f754b1b10ee7476048bc107f329ba48a7bcc88fbe982a32a2564b28` |
| `mutation_run.py` | `50a5227d87c23ff1bd0cc7a126440bcc062be1e1a1873d1f3b8f0d78e2072458` |
| `new_nodes.json` | `2e9397faf7b8b05ea3bff41068a330f0dd5f3e4fad838757f317067dc3517658` |
| `run_g2.sh` | `10b906ffd3424a7f94faf4100f85ba1d32319e650a3e7d61aa9c08656872508a` |
| `run_gates_fast.sh` | `97b2dce0d3fb0a6c3b96b314412b5d060262826ceb44ed901065afa71e345086` |
| `run_gates_g2.sh` | `274f51b7ca7d6a2fac2c5bb72d1da82051402057647f224a2102191f66801d84` |
| `run_gates_tier.py` | `55bc4d700c421021b80b564d3a996ac60b49b45ccbfacdba21e24a7c3ba34291` |

## 6. 门禁矩阵

测试档。顺序：基线测量 → 安装参考字节 → 快速门禁（G4、G3、G1、G9、G8、G6）→ rest 组回归（G2）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 夹具健康、冒烟、导入测试 | 与基线完全相同（26 passed，1 个既存失败） |
| G2 | rest 组回归（含 tests/e2e） | 失败集合与基线相同、通过数恰增 73、无新增 skip 与 ERROR |
| G3 | 新测试节点 | 收集到的恰为冻结的 73 个节点 |
| G4 | 静态检查 | 两个 Python 文件 `ruff`、`mypy --strict` 零问题，`git diff --check`，字节扫描，新增行无抑制注释 |
| G5 | 范围 | 变更集恰为 3 个 owned path，字节等于 §5.1，无残留 |
| G6 | 既有内容不变 | `templates`、`auto_pm`、`tests` 树除这三个新增文件外与基线逐字节相同 |
| G7 | 隔离 | 新增行不引用真实控制根；真实 `.git/hooks` 前后字节相同；门禁不遗留 python 进程 |
| G8 | 严格变异 | 17 个变异各被点名测试的真实断言失败杀死，字节还原；每次运行的完整输出保存并绑定 |
| G9 | 新测试文件整体 | 73 passed、0 failed、0 skipped |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-08 与 2026-10-09 的有条件预授权（原话 `.auto-pm/reports/PREAUTH_M2_20261008.txt`）：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径；任一不满足则不开工。13:00 有序停止，本卡只在估算其门禁能在 13:00 前结束时开始 |
| 最终验收 | 已委托：G1–G9 全部通过且提交与 Checkpoint 一致时由 claude-sonnet-5-5 代为验收并收口 CHG；用户可复核并推翻 |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

卡、基线、范围或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 向用户在聊天报告最终卡 SHA 与改动摘要。
2. 创建 SW-2026-008 SCPT/DEF 变更单、匹配 Decision（`DEC-<当天>-TIERCLAS`）、Work `WORK-SW008-M2-TIER-001`、Run `RUN-SW008-M2-TIER-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）；实际创建前验证未被占用，不复用幂等键或旧 token。
3. 从代码基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-tier`，分支 `codex/m2-tier-classifier`。
4. 安装参考字节并完整重跑门禁（`tier_gates_all.sh`）；先创建当前字节 Checkpoint，再正常 Hook 提交 3 个 owned 文件，绝不 no-verify；核对提交父、范围及 blob 与 Checkpoint 完全一致。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；条件满足后代为验收并收口 CHG。

## 9. 硬停止

基线、工具/卡/Decision 指纹、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败；变异未被点名断言杀死；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要改这三个文件以外的任何内容、或为让测试变绿而放宽断言：均停止，保留现场，不靠重跑、改字节或放宽判据变绿。按止损规则：同一问题最多修 2 轮，每卡总时长上限 6 小时，连续 2 张卡失败整体停下。全量测试对机器负载敏感（台账 TD-SW008-095）：正式门禁期间我不并发其他重任务。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结参考字节与工具；演练原始门禁（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；代验收记录；GPT 对提交的独立审计。

## 11. 限制与后续

分档器只推荐，不接入启动脚本、判卷器与卡预检；规则表第一版宁严勿松，后续放宽须另卡批准。不处理 TD-SW008 台账里的其余债务。无合并、推送、部署或 release 切换授权。
