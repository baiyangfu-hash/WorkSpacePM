# M2-GOV-CICD1｜CI 最小版落地实施卡

> 卡片编号：`CARD-SW008-M2-CICD1`
> 版本：`V1.1`（2026-10-10；V1.0 的 SHA 为 `ba86cf2c867702b5779624db3c749effdcb1b8fdd2d486d10831f3d2843b0f83`，其九组门禁全过但收口提交被 Git Hook 拒绝，原因与改动见 §1 第 7 条；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PENDING_USER_APPROVAL`（用户 2026-10-10 要求落地云端的 CI，并对 V1.0 被 Hook 拒绝后的建议回复“按建议修”；本卡 V1.1 的 SHA 报给用户之后，须用户在聊天中回复批准才启动，不沿用对 V1.0 SHA 的批准；条件见 §7）
> 档次：**产品档**（分档器 `tier_classifier`、规则表 v1.0 对 `.github/` 的计算结果：PRODUCT-GITHUB「repository automation」；规则文档 §11：分档器只推荐，不降档；4 个工具文件在 `tests/tools/` 下按 TESTS-TREE 为测试档，取最高档即产品档）。九组回归在受治理 Run 里完整重跑（规则文档 §8：不跨 Run 复用）
> 依赖：台账卡 097（CHG-DOCU-2026-035 completed，由启动脚本核验）
> 隔离基线：`ec3d46f6f909086a97dd85ca4c0fec85107f717d`（卡 097 的提交，本地分支 `codex/m2-td10-docs`）
> 路径根：`.`（仓库根；工作流在 `.github/workflows/`，4 个工具文件在项目的 `tests/tools/sw008_ci/` 下，路径含 `tests/`）
> 候选来源：云端执行者的分支 `claude/cloud-ci-lite-candidate`，提交 `82291847c1c64943c9c2777ac7592d7c2892ef3e`（只读取其 git 对象的字节，不执行、不合并该分支）
> 执行模型：`claude-sonnet-5-5`；云端执行者起草候选，GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033，以及基线提交中的《M2 门禁分档与单卡规模规则》。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-10）

1. **为什么**：项目没有任何 CI。每次提交的静态检查与回归只在本机串行跑（九组约 2 小时 40 分），换机器或换一个云端执行者就没有早期预警，也看不出 Linux 与 Windows 的行为差异。
2. **云端执行者的实测**（用户转述其回报并经我只读核对）：在 `d3c50a8b` 上，Ubuntu 24.04、Python 3.13，按锁文件安装 108 个包（`pip check` 无冲突）；全量测试 **3485 过 / 35 败 / 21 跳，328.9 秒**（`-n 4`）；35 个失败归为 6 类：POSIX 钩子无可执行位 15、vartable 样本文件缺失 14、Windows 路径 3、`sh --login` 1、信号语义未核实 1、两边都失败的夹具健康测试 1。随后在 GitHub 的 ubuntu-24.04 + Python 3.12.15 真实运行器上跑出同一组 35 项，耗时 5 分 8 秒。rest 组（859 个）Linux 为 812/29/18，与 Windows 基线 831/15/13 的差异完全对得上（13 个钩子用例与 1 个信号用例仅 Linux 失败，5 个 Win32 分支仅 Linux 跳过）。
3. **本卡做什么**：把候选的 5 个新增文件落地到受治理线（见 §4）；3 个 Python 文件与基线 JSON 的字节与云端候选完全相同，工作流只改 4 处路径引用（见第 7 条）：
   - 工作流 `sw008-ci`：`push`（不含 `main`）与手动触发；`permissions: contents: read`；不引用任何 secret；检出不保留凭据；依次做：装锁定依赖、CI 工具自测、扫描相对 `main` 新增行里的密钥、ruff、mypy（`--platform win32`）、`pytest -n 4 tests`、与 Linux 基线比较、确认工作树仍然干净；日志保留 14 天；25 分钟超时。
   - 比较工具的三种结论：`PASS`、`PASS_KNOWN_BASELINE`（失败恰等于基线，**不是全绿**）、`FAIL`（出现新失败、基线项不再失败即基线过期、或 pytest 非正常结束）。
4. **本卡不做什么**：①**不删除** `.github/workflows/plc-tool-ci.yml`——云端候选提交里有这条删除，但那是现存项目 SW-2026-005（树里有 93 个文件）的 CI，不在本卡范围，故不纳入；②不做 Windows 检查与 CD；③不改任何产品、测试、模板、台账；④不推送、不合并 `main`、不打 tag。
5. **它的性质**：早期预警，**不是验收证据**，不替代本地受治理门禁（工作流文件头与比较工具输出都写明）。
6. 我在隔离演练树上用本卡的专用检查器跑了一遍（非受治理执行，不能复用为正式门禁）：基线 G1、安装、快速门禁全部通过；9 个变异全部被自测的指定检查击杀并逐字节还原；判卷逻辑用 M2-DEP-INT 的受治理九组输出做演练，G1–G9 PASS，4 个反例各被拒绝；`gate_verdict`（演练，judge 逻辑）SHA-256 `4b006b27d1ae4025b59c84fdcaca8d5669f666790d74f5a774d0cab695011a8f`。**演练里没有重跑九组回归**，正式 Run 完整重跑。证据目录 `.auto-pm/reports/m2-cicd2/gates_rehearsal/`。**V1.1 的演练多做了一步 V1.0 缺的：把 5 个文件暂存后直接运行真实的 `.git/hooks/pre-commit`（只读干跑，不提交），记录在 `hook_pre_commit_dry.txt`（退出码 0）；同一方法对 V1.0 的旧布局（`.github/sw008-ci` 下的 `.py`）干跑，得到与实际完全相同的拒绝（`hook_pre_commit_negative.txt`，退出码 1），说明这一步能真正拦出问题**。
7. **V1.0 为什么停下，V1.1 改了什么**：V1.0 的九组门禁 G1–G9 全部 PASS，但收口提交被正常 Git Hook 拒绝：`暂存生产文件归属未知或不唯一: .github/sw008-ci/compare_baseline.py`——Hook 要求仓库根下的 `.py` 必须落在某个已登记项目目录内（或为 `main.py`），`.github/sw008-ci` 下三个 `.py` 都不满足。我在 V1.0 演练时没有走真实 Hook，所以事先没发现。V1.0 的卡、证据与门禁输出保存在 `.auto-pm/reports/m2-cicd/`，其 Run 已 FAILED、Work 已 CANCELLED；变更单 CHG-SCPT-2026-402 已按合法流转退回已批准并沿用。**V1.1 唯一的实质变化是位置**：4 个工具文件改放项目 `tests/tools/sw008_ci/`（与卡 093 的 `tests/tools/chg_tracking_check.py` 同一惯例；路径含 `tests/`，Hook 的排除词放行；不改 Hook，不用 `--no-verify`）；工作流因此改 4 处：删 `paths` 里的 `.github/sw008-ci/**`（已被项目目录 `**` 覆盖）、3 处 `python -I` 调用改为 `$PROJ/tests/tools/sw008_ci/…`。3 个 Python 与 JSON 的字节一个不改。新位置在项目 `tests/` 下，会被工作流自己的 Ruff 步骤（`ruff check auto_pm tests`）检查：我用项目自己的 ruff 配置核对过 3 个文件均无问题，并把它加进 G4。

## 2. 单一目标与完成定义

把 5 个文件落地到本地受治理分支，其余零改动。技术完成 = 提交通过全部门禁（含九组回归）、提交字节等于冻结清单；**验收 = 用户阅读后确认**，变更单收口不委托。让工作流在远端真正运行需要把提交推送（另行授权，不在本卡）。

变异检查（9 个，对象是 CI 工具，每个由自测的指定检查击杀）：
   - M01-a-new-failure-is-accepted：a failure that is not in the baseline is a FAIL（由自测检查“failure missing from baseline -> FAIL”击杀）
   - M02-a-stale-baseline-is-accepted：a baseline item that no longer fails is a FAIL, never a silent pass（由自测检查“baseline item unexpectedly passes -> FAIL (stale)”击杀）
   - M03-a-crashed-run-is-accepted：a pytest exit code other than 0 or 1 means the run did not complete: FAIL（由自测检查“pytest crashed (exit 2) -> FAIL”击杀）
   - M04-a-clean-run-hides-a-stale-baseline：a clean run against a non-empty baseline is a stale baseline: FAIL（由自测检查“clean run but non-empty baseline -> FAIL (stale)”击杀）
   - M05-the-failures-are-never-reported-as-known：failures that equal the baseline are reported as PASS_KNOWN_BASELINE with exit 0（由自测检查“failures equal baseline -> PASS_KNOWN_BASELINE”击杀）
   - M06-the-scan-reads-only-the-final-diff：a secret added and removed inside the range is still found（由自测检查“added then removed inside the range -> scan still fails”击杀）
   - M07-the-token-pattern-is-gone：a GitHub-token-shaped string in an added line is found（由自测检查“token-shaped addition -> scan fails”击杀）
   - M08-the-scan-always-passes：the scan exits 1 when anything is flagged（由自测检查“token-shaped addition -> scan fails”击杀）
   - M09-the-scan-flags-clean-additions：an addition that is not provider-shaped passes（由自测检查“clean addition -> scan passes”击杀）

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线、基线里 5 个路径不存在、冻结文件字节等于清单、工具字节等于冻结指纹、前置变更单 completed。启动脚本有只读的 `--check-only`，预检只用它。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **续租**：先用绝对路径启动续租循环并确认日志里有 `first renewal ok`；九组回归约 2 小时 40 分，期间每次检查先看续租日志。
4. 重门禁期间不在同一台机器上并发任何测试或静态检查（规则文档 §9）。

## 4. 精确 Owned Paths（5）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `.github/workflows/sw008-ci.yml` | 计划新增 | 工作流：ubuntu-24.04、Python 3.12、只读令牌、无 secret、非 main 推送与手动触发 |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/sw008_ci/baseline.linux.json` | 计划新增 | Linux 已知失败基线（35 项，6 类原因），由工作流比较 |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/sw008_ci/compare_baseline.py` | 计划新增 | 把一次 pytest 的失败与基线比较：新失败、基线过期、崩溃都判 FAIL；与基线相等记 PASS_KNOWN_BASELINE（不是全绿） |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/sw008_ci/secret_scan.py` | 计划新增 | 逐提交扫描相对 main 新增的行里厂商格式的密钥（只打印位置，不打印值） |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/sw008_ci/selftest.py` | 计划新增 | CI 工具的自测：证明检查能失败（9 项） |

出现第六条候选变更即停止（含对任何既有工作流的删除或修改）。准备和证据落点（`.auto-pm/reports/m2-cicd2/`、本卡文件、演练工作树）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

5 个新增文件的最终 SHA-256（UTF-8、LF、无 BOM）；冻结文件保存在 `.auto-pm/reports/m2-cicd2/proto/`：3 个 Python 与基线 JSON 取自候选提交 `82291847` 的 git 对象且字节未改，工作流是同一对象加 4 处路径引用改动（逐项记录在 `freeze_notes.json`）。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `.github/workflows/sw008-ci.yml` | 计划新增 | `2ea1a7551b11a9b037ce65f300845a6824035505a19f10b7574e0cf6d0fb7e62` |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/sw008_ci/baseline.linux.json` | 计划新增 | `d97655404b71db5c47a0c42004be37614f5e8a19d13f0beeb5a6109533be9357` |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/sw008_ci/compare_baseline.py` | 计划新增 | `92a7d726448085334e8fc85b4ff214b32fb94f8b6eeb3ab81d98fc42e6eafd90` |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/sw008_ci/secret_scan.py` | 计划新增 | `e89ee5d81d831a59be93cffe770582bf833986f98577064202497c679c4aa0a3` |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/sw008_ci/selftest.py` | 计划新增 | `922930fa4f76d1b79db88abb75f904981c5166b213991e0ff897f5460e4e02b2` |

### 5.2 冻结工具

专用工具在 `.auto-pm/reports/m2-cicd2/`：运行器与脚手架派生自卡 093 的已验收工具，判卷器（`run_gates_cicd.py`）、语义检查器（`cicd_check.py`）、树比对（`g6_check.py`）、变异运行器与安装器为本卡新写。G2 的基线取 M2-DEP-INT 卡受治理执行的九组真实输出（其 `auto_pm`、`templates` 字节与本基线相同，`tests` 与本基线只差本卡的 4 个非测试文件，G3 对基线提交实测证明）。

| 工具 | SHA-256 |
|---|---|
| `cicd_check.py` | `ca4aaf99fb45ad49d204211ac05f97a109d814aef289ff547360c1417e484946` |
| `commit_msg.template.txt` | `bd193dc496b0524f093e35427199c44810b622c5c162d12ba61106052f0b56a8` |
| `g6_check.py` | `baa3684819debc63cfa95dc216b5618e3d7cc2611f9a8e4d2f4c00e588fcf217` |
| `install_candidate.py` | `a971d71344a9d7ab69336005ce1d90defac89804e278b83931aee2997585c790` |
| `m2-tools/verdict_check.py` | `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188` |
| `mutation_plan.json` | `a37ca28996aeabbace8790153b6a4a7776e4a28772a08b01968df25a541fe175` |
| `mutation_run.py` | `22565b893572d5195ac0f45a3bd4ea4fb6b8ad9ead51a0a345beb21f8e560d24` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |
| `run_gates_cicd.py` | `1e8ad396149fdbec03e20294bbc351aa1194dd150397f76f1cb2a990a0f3918b` |
| `run_gates_fast.sh` | `92c9a7d3c3f7d63288957c27516997f64fc82b3793f500742896bf41293513fa` |
| `run_gates_g2.sh` | `60c5abceb90c090e92fe3cd97d03df6b0c3f722975805d3bc2d5e68289498ce1` |

提交：只含这 5 个文件；父提交为基线；经正常钩子，绝不绕过；提交 blob 与 git 对冻结字节算出的 blob id 相同。Checkpoint 在提交之前创建，证据里写明各文件的 SHA-256。

## 6. 门禁矩阵

产品档。顺序：基线测量 → 安装参考字节 → 快速门禁（G4、G1、G9、G6、G8）→ 九组回归（G2）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 夹具健康、冒烟、导入测试 | 与基线完全相同（26 passed，1 个既存失败） |
| G2 | 九组回归（十个输出） | 逐组：失败集合、通过数、跳过数与 M2-DEP-INT 的治理输出相同，无 ERROR 节点 |
| G3 | 项目代码树 | `auto_pm`、`templates` 与基线提交逐字节相同；`tests` 与基线相比恰好只多 4 个工具文件（都不是测试模块，pytest 不收集），其余逐字节相同（G2 的比较因此有效） |
| G4 | 静态检查 | 3 个 Python 文件 `ruff`（E、F）、项目自己的 ruff 配置（即工作流的 Ruff 步骤）、`mypy --strict` 与解析零问题；字节扫描；无抑制注释 |
| G5 | 范围 | 变更集恰为 5 个 owned path，字节等于 §5.1，无残留 |
| G6 | 工作流与树的语义 | 只读令牌、无 secret 引用、无 fork 或特权触发、`main` 不触发、检出不留凭据、动作固定主版本、有时限、托管 Linux 运行器、含自测/扫描/ruff/mypy/pytest/比较、引用文件存在、工具不引入网络库、无密钥形字面量、基线文件自洽；工作流不再引用旧的 `.github/sw008-ci`、引用的工具文件都存在且在 `push` 路径过滤之内；`.github` 与基线相比只多工作流 1 个文件 |
| G7 | 隔离 | 新增行不引用真实控制根；真实 `.git/hooks` 前后字节相同；门禁不遗留 python 进程 |
| G8 | 严格变异（9 个） | 自测先在未变异字节上全绿，每个变异使其以指定检查 FAIL 退出 1，字节还原；原始输出保存并绑定 |
| G9 | CI 自测 | 按工作流的运行方式（`python -I`）全部检查符合预期 |

判卷另由冻结的 `m2-tools/verdict_check.py` 核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-10 要求落地云端 CI，并对 V1.0 被 Hook 拒绝后的建议回复“按建议修”；**本卡 V1.1 的 SHA 报给用户后，由用户在聊天中回复批准**才启动，不沿用对 V1.0 SHA 的批准。条件：卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧；不做真实模型调用 |
| **内容验收** | **用户 2026-10-10 在聊天中明确委托（原话：“卡98结束后，你替我验收”，记入 PREAUTH 日志）：仅当 G1–G9 全部 PASS 且提交与冻结清单一致，才由 Claude 代为运行收口脚本；否则停下报告。这是对卡 098 的委托，不外推；用户若自己先验收，以用户为准** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与摘要，等用户批准。
2. 沿用变更单 CHG-SCPT-2026-402（V1.0 被 Hook 拒绝后已退回已批准）并按用户批准的 V1.1 重新进入实施；新建匹配 Decision（`DEC-<当天>-CICDLAN2`）、Work `WORK-SW008-M2-CICD1-002`、Run `RUN-SW008-M2-CICD1-002`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-cicd2`，分支 `codex/m2-cicd-ci2`。
4. 安装冻结字节并完整重跑门禁（`cicd_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob id。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；**变更单停在“实施中”，等用户阅读后验收再收口。**

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease 或 hook 漂移；新增范围；任何门禁失败；负向目标未命中；Checkpoint 不能绑定清单哈希；提交 Hook 拒绝；需要改清单之外的任何文件或删除任何既有文件：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结工具、文件清单与冻结副本；演练原始门禁（非治理）；正式门禁（含九组）、CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；用户阅读验收的记录。

## 11. 限制与后续

本卡只新增 5 个文件；提交在本地分支 `codex/m2-cicd-ci2`，**不推送、不合并**。工作流只在被推送到远端后才会运行：首次推送会触发它（对除 `main` 外的任何分支），推送另行授权。云端候选分支 `claude/cloud-ci-lite-candidate` 上的三个已知局限同样适用：Linux 基线是在 Python 3.13 上先测、再在 GitHub 的 3.12 上复核一致；Windows 检查（真实钩子的 E2E、路径语义）与 CD（候选构建、回退演练、受控安装）不在本卡，之后各出卡；`plc-tool-ci.yml` 保持不动，是否停用由用户另行裁决。
