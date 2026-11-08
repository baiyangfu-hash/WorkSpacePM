# M2-GOV-MRG1｜兄弟分支合并实施卡（V1.1）

> 卡片编号：`CARD-SW008-M2-MRG1`
> 版本：`V1.1`（2026-10-11；最终字节报 SHA 后冻结，执行期间不得修改；V1.0 已作废，见 §1 第 8 条）
> 状态：`PLANNED / PENDING_USER_APPROVAL`（用户 2026-10-11 选择方案 1：出卡 100 V1.1；本卡 SHA 报给用户之后，须用户在聊天中回复批准才启动；条件见 §7）
> 档次：**测试档**（分档器对“基线 → 合并结果”的真实差异分档：2 个测试文件 + 1 个治理文档，不改任何产品文件；相关完整组 `rest`，含 tests/e2e）
> 依赖：卡 099（M2-GOV-CHGSYNC）的 Run/Work 已达技术终态且 CHG-DOCU-2026-036 已收口（由启动脚本核验）
> 隔离基线：`fea74b3359fae9f1a182298c346dc386ad61bf93`（卡 099 的提交，本地分支 `codex/m2-chgsync-records`，父为推送线尖端 `0d22fdd0`）
> 被合并提交：`657f3dc5fef37607233cd4145d254b65e6644fe0`（本地分支 `codex/m2-gov-wbs11-writeback`：卡 095 的 WBS V3.0.27，其父含卡 093 的 `7506af72`）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-11）

1. **为什么要这张卡**：卡 093（变更单入库检查工具及其端到端测试，提交 `7506af72`）与卡 095（WBS V3.0.27，把发布治理批次与 H02～H10 队列检查的状态写回，提交 `657f3dc5`）都建在 `8cb8dceb` 之上、位于兄弟分支里；后来的卡 096～099 在另一条线上，**推送线上的 WBS 仍是 V3.0.26**，而 TD 台账、CI 与变更单入库在这条线上。两条线必须接回一条线，才能把 M2 之后的治理成果一起推送。
2. **做什么**：在基线 `fea74b33` 之上建一条**本地**分支 `codex/m2-merge-093-095`，对 `657f3dc5` 做一次 `git merge --no-commit --no-ff`（不手改任何一行），再以合并提交收口：第二个父提交就是 `657f3dc5`。合并结果的树为 `7addde99015c9b2cdf2d0fadc6183acb06a62517`（我用 `git merge-tree --write-tree` 干跑得到，无冲突）。
3. **合并结果恰为 3 个文件**（相对基线）：
   - 新增 `tests/e2e/test_pmf_chg_tracking_check.py` 与 `tests/tools/chg_tracking_check.py`（卡 093；9 个新测试节点、12 个严格变异）；
   - 修改 `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md`（卡 095；V3.0.26 → V3.0.27）。
   两个兄弟分支相对它们的共同祖先 `8cb8dceb` 只含这些改动；卡 096～099 没有触碰这 3 个路径，所以没有冲突、没有需要人工取舍的地方。
4. **不做什么**：不改任何产品文件、其他测试、台账、既有变更单；不推送、不合并进 `main`、不打 tag；不处置任何债务或历史失败记录。卡 093 的检查工具**仍不接入任何门禁**（接线另卡批准）。
5. **本卡自己的变更单**会在启动之后产生，不在合并结果里；收口后控制根里会多出这一个文件与一行台账（TD-SW008-113 的已知局限，沿用卡 088、099 的处理）。
6. **门禁怎么保证“合并结果没有被基线变化破坏”**：测试档的 5 类门禁在合并候选上完整重跑——rest 组回归（基线取卡 093 受治理执行的真实输出：它们是同一批 rest 组测试，两者的差别只在非测试文件；**V1.1 新增一条有证据的规则，见第 8 条**）、夹具健康/冒烟/导入、`ruff` 与 `mypy --strict`、12 个严格变异、字节与范围指纹；另加合并专有检查：候选 HEAD 仍是基线、`MERGE_HEAD` 等于 `657f3dc5`、暂存索引的树等于冻结树、WBS 字节等于冻结值。
7. （V1.0 的演练，结果仍然有效，因为合并结果与其余门禁未变）我在隔离演练树上完整跑了一遍（非受治理执行，不能复用为正式门禁；输出在 `.auto-pm/reports/m2-mrg1/gates_rehearsal/`）：基线 G1 为 `1 failed, 26 passed`（既存失败）；合并安装通过（`MERGE_HEAD` 为 `657f3dc5`、树为 `7addde99`、变更集恰为 3 个文件、字节等于 §5.1）；快速门禁与 rest 组回归通过：rest 组 `15 failed, 840 passed, 13 skipped`，与卡 093 受治理执行的真实输出逐项相同（失败集合相同）；12 个严格变异全部被点名测试的真实断言杀死、字节逐一还原；G1–G9 判卷全部 PASS，`gate_verdict` SHA-256 `d2f64b45538e6a14111cd88e7f1bf059d2ce960e171e635a1aa646b145e13d8c`。**另外，按卡 098 V1.0 的教训，我在演练树里把暂存的合并结果直接交给真实 `.git/hooks/pre-commit`，退出 0。**诚实记录：演练第一轮在变异运行器处崩溃——它把 WBS 路径当成项目内文件读取，找不到；这是工具对“WBS 在项目目录之外”的适配遗漏，不是合并或测试的问题；已修正并重新生成工具包（`mutation_run.py` 的指纹已更新进 §5.2），然后重跑快速门禁与判卷（rest 组输出与它无关，沿用第一轮）。正式 Run 会完整重跑全部门禁。
8. **V1.0 的结局与 V1.1 的变化（2026-10-11 如实记录）**：用户批准 V1.0 后正式运行，G1、G3～G9 通过，**G2 失败**：rest 组 16 failed / 839 passed，比卡 093 多一个失败 `tests/e2e/test_pmf_recovery.py::test_r09_a_reader_never_fails_because_another_process_has_a_transaction_open`——这是一个多进程读写压力测试，读者子进程在 `continuity.db-wal` 的路径检查处瞬时报 `Continuity Store 路径必须是唯一链接的普通文件`，属台账 TD-SW008-077 同一类边车竞态；该组耗时 31 分钟，比卡 093 与演练（21～29 分钟）更长，说明当时机器负载更高。合并结果的 3 个文件与全部产品代码字节未变。按 V1.0 的 §9 与批准条件，我没有重跑也没有提交，停下并保留了现场；随后在同一候选字节上把该测试单独跑了 3 次，3 次都通过（20.7 s、20.7 s、49.7 s）。用户据此选择方案 1：出 V1.1。V1.0 的 Run（`RUN-SW008-M2-MRG1-001`）已记 FAILED、Work 记 CANCELLED、变更单 CHG-SCPT-2026-403 退回 approved 并沿用，原始证据在 `.auto-pm/reports/m2-mrg1/v1.0/`。
   **V1.1 只改一处判据（G2），其余全部不变**：rest 组回归的失败集合必须等于卡 093 的失败集合；**唯一的容忍**是上面这一个具名节点——它在组内失败一次是允许的，当且仅当同一候选字节上、门禁自动对它做的 3 次单独运行**全部通过**，且其余每个节点与基线逐项相同（通过数恰比基线少 1、跳过数与退出码相同、无 ERROR 节点）。3 次单独运行的原始输出绑定进判卷文件，判卷记录一条 deviation。我用 V1.0 的真实失败输出与真实的 3 次单独运行做了判卷干跑：正例通过；“单独运行有 1 次失败”与“组内出现另一个不同的失败”两个反例都被拒绝；共用判卷脚本 `verdict_check.py` 接受正例的判卷文件。另在一次性工作树里对新的 G2 外壳脚本做了冒烟（桩替换 rest 组）：3 次单独运行与字节记录都正常生成。

## 2. 单一目标与完成定义

把冻结的合并结果提交到本地分支：合并提交的父为 `fea74b33` 与 `657f3dc5`，树为 `7addde99`，3 个文件字节等于 §5.1。技术完成 = 全部门禁通过（G2 按 §1 第 8 条与 §6）、提交树等于冻结树、Checkpoint 绑定当前字节；**验收 = 你阅读后确认**，变更单收口不委托。

## 3. 实施前预检

1. 核对卡字节与已向用户报告的 SHA 一致、基线分支仍在基线、兄弟分支仍在 `657f3dc5`、`git merge-tree --write-tree` 的结果仍是冻结树、3 个路径与参考字节、卡 099 的 Run/Work 为 SUCCEEDED/CLOSED 且 CHG-DOCU-2026-036 completed、V1.0 的 Run/Work 为 FAILED/CANCELLED（旧候选工作树与分支已清理，不存在）。没有这些，不创建 Decision/Work/Run。启动脚本另有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. 新候选 HEAD 等于基线且 clean；两个测试路径在基线不存在、WBS 路径的基线 blob 等于冻结的基线哈希。
4. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`，门禁期间每次检查先看续租日志。

## 4. 精确 Owned Paths（3）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_chg_tracking_check.py` | 计划新增 | 卡 093 的端到端测试：在真实的一次性 Git 仓库里运行检查工具 |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/chg_tracking_check.py` | 计划新增 | 卡 093 的检查工具：只读，报 untracked 与 modified |
| 3 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | 卡 095 的 WBS V3.0.27（修改） |

出现第 4 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-mrg1/`、本卡文件、演练工作树）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

合并结果中 3 个文件的 SHA-256；冻结副本保存在 `.auto-pm/reports/m2-mrg1/proto/`（路径同 §4 的仓库相对路径或项目相对路径）。WBS 的基线 blob SHA-256 为 `b667b5451a0b22ca2a2cb7922ff0c4d312d27f3fb04afab95f909509f2189a30`。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_chg_tracking_check.py` | 计划新增 | `cf1c5c3bfd72a9e5aebc606a49a7e679d0dafcb437b46462879ecd4e849aaeff` |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/chg_tracking_check.py` | 计划新增 | `f8c2a8867080b175656ae32c1b8c7239fdd428ed195af34a8a8352752d537a9f` |
| 3 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | `27411f80694e864dbcb556db31cb8aef09ce19b4d4cc1ec0aba617d6bc730c56` |

### 5.2 冻结工具

工具与脚本由卡 093（M2-GOV-TRK，测试档、rest 组）的已验收工具派生（`.auto-pm/reports/m2-mrg1/`），安装器换成合并安装器，判卷与脚本为合并做了适配（WBS 在项目目录之外、暂存区的差异、MERGE_HEAD 与树检查）；V1.1 在 G2 外壳脚本里加入具名节点的 3 次单独运行、判卷里加入上述唯一容忍规则（`run_gates_g2.sh`、`run_gates_mrg.py` 的指纹因此更新，其余工具与 V1.0 相同）；共用判卷脚本仍是控制根下的外部副本。清单（含全部工具的指纹）文件 `reference_manifest.json` 的 SHA-256 为 `044690e6524848a60d502ae0316112ebba8ecaf81b5952fe6efa2793f3e51386`。

| 工具 | SHA-256 |
|---|---|
| `commit_msg.template.txt` | `0a2fda8388e4850517cd6ff2d74cf4ba14c090471812ba1df346f0bad1f78d9e` |
| `g6_check.py` | `0383da115a7aef2e0d2473d5c84cd75322720c8e27d48460d6e353a1ddaa8fcf` |
| `install_candidate.py` | `325a0e3689b14cdd3c853408a242357e6fd9bd23ffa72ac53f8e59ab2167b080` |
| `m2-tools/mutation_classify.py` | `0fff21f888cb1a50094f050ef8bc3b42ea25653ba508581e3c85fa1b28d79019` |
| `m2-tools/verdict_check.py` | `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188` |
| `mutation_plan.json` | `e13bed31f40441efa389d09e8d9e42aef58f4ff275001c7c6dfaacfd3b9d0bb6` |
| `mutation_run.py` | `b2169912789250ca92843e7183e87d439384671a2ce2bb0721212443d3a2f2b7` |
| `new_nodes.json` | `37f3a2954b71389460f53e2d66a3b6d2dbf9879e89bedbedf69b7242b17a5d7b` |
| `run_g2.sh` | `10b906ffd3424a7f94faf4100f85ba1d32319e650a3e7d61aa9c08656872508a` |
| `run_gates_fast.sh` | `5242fafe080658cc439b4ea5492adfd6f8e3a2f206ca0d9e27313e4ca9ddb558` |
| `run_gates_g2.sh` | `e39d6a95285d2b9061d2ce40290a0cefbc731bae78bc3db0710b11befc5033f9` |
| `run_gates_mrg.py` | `224fc89c48a651e201c7f3e9b21120253434292b1dd03421dce09c3d82c6c055` |
| `wbs_base_sha256.txt` | `0b06a932496c58b49b0ab583d628b6d355659658005cbb79ae0baeee006b1060` |

## 6. 门禁矩阵

测试档。顺序：基线测量 → 合并安装 → 快速门禁（G4、G3、G1、G9、G8、G6）→ rest 组回归（G2）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 夹具健康、冒烟、导入测试 | 候选与基线完全相同（26 passed，1 个既存失败） |
| G2 | rest 组回归（含 tests/e2e） | 与卡 093 的真实 rest 组输出比：失败集合相同、通过数相同、无新增 skip 与 ERROR；**唯一容忍**：具名节点 `test_r09_a_reader_never_fails_because_another_process_has_a_transaction_open` 在组内失败一次，且同一候选字节上 3 次单独运行全部通过（此时通过数恰少 1、其余逐项相同） |
| G3 | 新测试节点 | 收集到的恰为冻结的 9 个节点 |
| G4 | 静态检查 | 两个 Python 文件 `ruff`、`mypy --strict` 零问题，`git diff --cached --check`，字节扫描，新增行无抑制注释 |
| G5 | 范围与合并 | 变更集恰为 3 个 owned path，字节等于 §5.1；HEAD 仍是基线；`MERGE_HEAD` 为 `657f3dc5`；暂存索引的树等于冻结树 `7addde99`；无残留 |
| G6 | 既有内容不变 | `templates`、`auto_pm`、`tests` 树除这两个新增文件外与基线逐字节相同 |
| G7 | 隔离 | 新增行不引用真实控制根；真实 `.git/hooks` 前后字节相同；门禁不遗留 python 进程 |
| G8 | 严格变异 | 12 个变异各被点名测试的真实断言失败杀死，字节还原；每次运行的完整输出保存并绑定 |
| G9 | 新测试文件整体 | 9 passed、0 failed、0 skipped |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA；收口脚本另核对提交的第二个父提交与树。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-11 选择方案 1（出 V1.1）；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、被合并提交、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与合并摘要，等用户批准。
2. 沿用已退回 approved 的 SW-2026-008 变更单 CHG-SCPT-2026-403，新建匹配 Decision（`DEC-<当天>-MRGSIBL2`；Decision 编号后缀必须恰为 8 个字符）、Work `WORK-SW008-M2-MRG1-002`、Run `RUN-SW008-M2-MRG1-002`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）；实际创建前验证未被占用。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-mrg1`，分支 `codex/m2-merge-093-095`。
4. 合并安装并完整重跑门禁（`mrg_gates_all.sh`）；先创建当前字节 Checkpoint，再经正常 Hook 完成合并提交，绝不 no-verify；核对提交父（基线与 `657f3dc5`）、范围、树与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；**变更单停在“实施中”，等用户阅读后验收再收口。**

## 9. 硬停止

基线、被合并提交、冻结合并树、工具/卡/Decision 指纹、owner/scope、lease（含续租失败）或 hook 漂移；合并有冲突或需要手改；G2 里出现具名节点以外的任何差异，或具名节点的 3 次单独运行不是 3/3 通过（具名容忍规则只有这一条，不得扩展）；新增范围；任何门禁失败；变异未被杀死；Checkpoint 不能绑定当前字节；提交 Hook 拒绝：均停止，保留现场，不靠重跑、改字节或放宽判据变绿。按止损规则：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。全量测试对机器负载敏感（台账 TD-SW008-095）：正式门禁期间不并发其他重任务。

## 10. 交付物

基线与被合并提交的 SHA 与预检事实表；卡与预检；冻结参考字节与工具；演练原始门禁（非治理）与真实钩子干跑；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、树与 blob 核对和对账；用户阅读验收的记录。

## 11. 限制与后续

合并只在本地分支 `codex/m2-merge-093-095` 上，**不推送、不合并进 main**；推送（含远端仓库是公开的这一点）要你另行授权。合并完成后，推送线的候选尖端会成为本分支，其上的卡 096～099 与本卡构成一条线性历史。TD 台账同步卡与 CHG-195 勘误卡以本卡提交为基线另立。不处置 TD-SW008 台账里的任何债务。
