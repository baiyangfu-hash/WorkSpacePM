# M2-GOV-WBS10｜部署与推送状态写回实施卡

> 卡片编号：`CARD-SW008-M2-GOV-WBS10`
> 版本：`V1.0`（2026-10-09；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PENDING_USER_APPROVAL`（用户 2026-10-09 夜以“wbs写回”要求做这件事；本卡 SHA 报给用户之后，须用户在聊天中回复批准才启动；条件见 §7）
> 档次：文档档。分档器（卡 078）对本卡路径的计算结果：文档档，命中规则 `DOCS-WORKSPACE-GOVERNANCE`，规则表版本 1.0（SHA-256 `26e3480c6420566619e9d13c98f0b761ffdd01ff0924417ba7e9b65568355e4a`），声明“文档档”无冲突
> 隔离基线：`4b5c6307e814cd6bf17337f31ccd8c7e533553e1`（卡 083 提交，分支 `codex/m2-gov-wbs9-attest`；技术部署变更单 CHG-SCPT-2026-400 completed）
> 路径根：`SYS-2026-001_WorkspaceGovernance`
> 治理任务基线：WBS V3.0.25；冻结条款 §4.11（“状态写回”是冻结后允许的唯一 WBS 动作）
> 执行模型：`claude-sonnet-5-5`
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-09）

1. **为什么**：M2 的技术性部署（卡 084 V1.1）与推送已经完成，卡 083 也已由用户验收；但 WBS 当前投影仍停在这些动作之前：`M2-PUSH` 行写着“PLANNED、目前没有任何推送授权”，`M2-DEP-TECH` 写着“PLANNED”，`M2-GOV-WBS9` 写着“PLANNED”，M2 行的“下一步”仍是“推送、部署待做”。任何后续 Agent 读到的都是过期状态。
2. **做什么**（只改 WBS 一个文件，V3.0.25 → V3.0.26）：①新增 §4.7.11，写回 CHG-DOCU-2026-033（卡 083，提交 `4b5c6307`）已验收，卡 084 V1.1 的部署结果（release `1.3.3-4b5c630`、source_commit `4b5c6307`、CHG-SCPT-2026-400 completed、第一轮自动回退与第二轮成功、切换后核验、回退命令）与推送结果（分支 `codex/m2-gov-wbs9-attest`、提交 `4b5c6307`、origin 新分支、未合并 main）；②把当前投影的 M2 行与 `M2-GOV-WBS9`、`M2-DEP-TECH`、`M2-PUSH` 三个任务行的状态更新为已发生的事实；③新增任务行 `M2-GOV-WBS10`（任务计数 156 → 157）、版本记录一行与文末状态段。
3. **不做什么**：不宣布 M2 里程碑验收（这是用户的决定，投影里写成 `AWAITING_USER_MILESTONE_ACCEPTANCE`）；不处置 5 个历史未终结 Work；不登记新债务；不改任何产品、规则、台账、`.trae`；不合并、不再推送、不部署。
4. **检查**：检查器把 §4.7.11 里的部署结果与部署验收回执和部署 manifest、推送提交与 origin 上该分支的当前提交、两个变更单的状态与变更单文件逐项核对；四个新反例（错误的 active release、错误的推送提交、错误的变更单状态、越权宣布 M2 验收）与沿用的十九个反例都必须各被对应断言拒绝；其余沿用卡 083 的判据（相对 V3.0.25 只改列明的行与单元格、其余只加不删、D08 与冻结条款不变、引用的 SHA/变更单/债务编号/Run/Work/Checkpoint/Decision/release/文件真实存在、字节等于冻结值）。**它不证明内容就是用户的意思**，这由用户验收。
5. 我在隔离演练树上完整跑了一遍（非受治理执行，不能复用为正式门禁）：基线、安装、候选三步原始退出码均 0；G1–G9 全部 PASS（含候选上的 `doc check` exit 0）；23 项内存负向对照都改变了目标输入并被指定断言拒绝；`gate_verdict` SHA-256 `6e525a3bf805cabc2c195525cf02010069fd08437996218129c73f6f24746d27`，`DONE` SHA-256 `9900b7c71c51b13e0886b4563ceb979c867b25e7f91e8996878b17f5e9c89578`；证据目录 `.auto-pm/reports/m2-wbs10/gates_rehearsal/`。
6. 不在本卡范围：任何产品、测试、模板、台账、规则文本、`.trae`；改写已有 Checkpoint 或治理库；合并 main、推送、再次部署；M3 的任何事项；把近期只读核对中发现的新问题登记为债务（那是另一张台账文档卡，需要用户另行决定）。

## 2. 单一目标与完成定义

把卡 083 验收、技术性部署与推送的结果写进 WBS V3.0.26，只改这一个文件。技术完成 = 提交通过全部门禁、提交字节等于 Checkpoint；**验收 = 用户阅读 §4.7.11 与投影状态后确认**，变更单收口不委托。

## 3. 实施前预检

1. 核对卡字节与已向用户报告的 SHA 一致、基线、唯一 owned path 及冻结的最终字节、基线 WBS 字节等于冻结的 `base_wbs.md`。启动脚本有只读的 `--check-only`，预检只用它。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. 核对前置技术部署卡（CHG-SCPT-2026-400）为 completed 且其 Run SUCCEEDED、Work CLOSED；卡 083 变更单 CHG-DOCU-2026-033 completed；origin 上 `codex/m2-gov-wbs9-attest` 等于基线。
4. 新候选 HEAD 等于基线且 clean、index 为空；工具、配置、负向计划均匹配冻结指纹。
5. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`；门禁用后台等待，不反复轮询。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | 修改：基线为 V3.0.25，写成 V3.0.26（相对路径根 `SYS-2026-001_WorkspaceGovernance`） |

出现第二条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-wbs10/`、本卡文件、演练工作树）不是额外产品 owned paths，不进本卡提交。

## 5. 字节合同

唯一最终文件 SHA-256：`b667b5451a0b22ca2a2cb7922ff0c4d312d27f3fb04afab95f909509f2189a30`（基线 V3.0.25 字节 SHA-256 `5d09d21b3c9c67024941b5f1d4afb5a06069fce43d08a0e5b7887db595b1c326`）。UTF-8、LF、无 BOM。冻结的最终文件保存在 `.auto-pm/reports/m2-wbs10/proto/`，由 `patch_wbs10.py` 从 V3.0.25 与 `facts10.json` 确定性生成；安装器只在明确安装阶段确认基线字节后写入，判卷器不得调用安装或生成。

1. 变更集恰为这一个修改文件；其余基线字节不变。
2. **相对 V3.0.25，只允许下表 6 行被替换，且只改列明的单元格**（“追加”＝新文本必须以旧文本开头；“替换”＝该单元格改变）；其余 V3.0.25 的行全部保留且顺序不变，所有版本记录行保留；新增行须满足第 3 至 5 条。

| # | 被替换的行（前缀） | 改变的单元格 |
|---|---|---|
| 1 | `> 文档版本：V3.0.25` | 版本，并在“状态写回登记于 §4.7.10（V3.0.25）。”之后插入一句 |
| 2 | `> 本文件给出 4 个产品里程碑、156 个任务` | 156 → 157 |
| 3 | `\| M2 \|`（当前投影） | 状态（替换，追加三个事实标记与 `AWAITING_USER_MILESTONE_ACCEPTANCE`）、证据（追加）、下一步（替换） |
| 4 | `\| M2-DEP-TECH \|` | 状态（替换） |
| 5 | `\| M2-PUSH \|` | 验收条件（追加一句）、状态（替换） |
| 6 | `\| M2-GOV-WBS9 \|` | 状态（替换） |

3. `D08` 行与 V3.0.25 完全相同；冻结条款（§4.11 的 ①～⑤）与延期承诺表不变；§4.7.10 的最终提交证明字节不变。新增任务行恰为 `M2-GOV-WBS10`，任务 ID 行由 156 变为 157 且无重复。
4. 新增文字中的每个提交 SHA、树、变更单、债务编号、Run/Work/Checkpoint（本卡自己的 Work/Run/Checkpoint 编号除外）、Decision、release、`.auto-pm/` 文件都真实存在；§4.7.11 的 active/previous release 与部署验收回执一致、release 的 source_commit 与 manifest 一致、推送提交等于 origin 上该分支的当前提交、变更单状态与变更单文件一致；无占位符残留；表格列数不比 V3.0.25 更差。
5. 当前投影的 M2 状态不得含 `ACCEPTED` 或 `MILESTONE_ACCEPTED` 标记（子项的 `*_ACCEPTED` 除外）并必须含 `AWAITING_USER_MILESTONE_ACCEPTANCE`。
6. 验证只读，负向对照仅修改内存中的输入；每个样本必须改变目标输入并被对应目标断言拒绝。
7. 工具与配置的 manifest 已冻结，SHA-256 为 `d556fe632c2c5d361a887105fbc7dbcc58aba943dcd5a9f2b1c82c2b4ca67318`；实际运行必须由外部传入该期望值。共享判卷器 SHA-256 为 `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188`。
8. 门禁前后逐一记录最终文件 SHA，全部相同且等于本卡。

冻结工具（`.auto-pm/reports/m2-wbs10/`，由卡 083 的已治理工具派生，判断部分改为部署、推送与变更单状态的核对）：

| 工具 | SHA-256 |
|---|---|
| `wbs10_runner.py` | `edff0d9772f49349f724bb011996302d536634898728e452e6f8a931baa17d9b` |
| `wbs10_check.py` | `b09f3b6a16ee6edb38b4886b3ee9d5f8db105793549987eba89a1d16ecd3094a` |
| `install_candidate.py` | `2724a58bd9a139d223768946787c528d6bc111edf27b3c3b7c13ae340f4f8bac` |
| `prepare_wbs10.py` | `f25decf499b61627c84f2d7490469efc974673bccda5818a24e6a23f92371581` |
| `patch_wbs10.py` | `1227c8a6b9674b4f7789243a0c8c8cf5750bd8207a640462d436a63dc5ff9bc3` |
| `collect_facts10.py` | `66d4699af8389ba8a85417cddec218c756a97aee44e33d63c5194363935643e0` |
| `wbs10_config.json` | `49b0fd6578262bd562fa183d79e27f14efe6b1fe65b6dac85dc01f6ec227ad33` |
| `facts10.json` | `adf3b5004aec9844a7595777835b315c2c489535aa7e7e6a2960bc715e6768bf` |
| `base_wbs.md` | `5d09d21b3c9c67024941b5f1d4afb5a06069fce43d08a0e5b7887db595b1c326` |

## 6. 门禁矩阵

顺序：基线测量 → 显式安装 → 最终候选测量和判卷。任一非零或环境异常立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份、工作树与初始 hook | HEAD 为基线、clean、index 空，WBS 基线字节等于冻结值；真实 hook 指纹非空 |
| G2 | 基线文档检查 | 根入口 `main.py doc check` 显式传控制根与候选根，原始 exit 0 |
| G3 | 安装前治理台账 | 根入口 `main.py ledger reconcile SYS-2026-001`，无 fix，exit 0 且 0/0/0 |
| G4 | 最终候选文档检查 | 同根入口，原始 exit 0；受检前后字节均等于冻结值 |
| G5 | 安装后治理台账 | 同只读对账，原始 exit 0 且 0/0/0 |
| G6 | 文档语义 | §5 全部成立，含部署、推送与变更单状态与实际记录逐项相符 |
| G7 | 真实 hook 保全 | 运行前后全部真实 hook 字节相同 |
| G8 | 轻量负向对照（23 项） | history_row_deleted、unlisted_cell_changed、version_row_lost、d08_changed、duplicate_id_row、bad_commit_sha、missing_change_request、missing_debt_id、freeze_clause_removed、v07_not_deferred、dep_tech_keeps_v07、attest_wrong_commit、attest_wrong_tree、attest_file_drift、deploy_wrong_active、push_wrong_tip、chg_state_mismatch、milestone_overclaim、placeholder_left、crlf、out_of_scope、tampered_bytes、wrong_column_count，各由对应断言拒绝 |
| G9 | 最终范围与字节 | 实测变更仅唯一 owned 文件（修改）、HEAD 仍基线、index 空；完整改动清单及前后 SHA 绑定 |

判卷另由冻结的 `m2-tools/verdict_check.py` 核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-09 夜以“wbs写回”要求做此事；本卡 SHA 报给用户后，**由用户在聊天中回复批准**才启动。批准条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧；不做真实模型调用 |
| **内容验收** | **用户阅读 §4.7.11 与投影状态后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与改动摘要，等用户批准。
2. 创建 SYS-2026-001 DOCU/OPT 变更单、匹配 Decision（`DEC-<当天>-WBS10WRT`）、Work `WORK-SYS001-M2-GOV-WBS10-001`、Run `RUN-SYS001-M2-GOV-WBS10-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）；实际创建前验证未被占用。
3. 从代码基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-wbs10`，分支 `codex/m2-gov-wbs10-writeback`。
4. 安装最终字节并完整重跑门禁（`wbs10_gates_all.sh`）；先创建当前字节 Checkpoint，再正常 Hook 提交唯一 owned 文件，绝不 no-verify；核对提交父、范围及 blob 与 Checkpoint 完全一致。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；**变更单停在“实施中”，等用户验收后再收口**。

## 9. 硬停止

基线、工具/卡/Decision 指纹、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败；负向目标未命中；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要改这一个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮；不处置任何历史失败对象。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结工具、事实文件与最终文件；演练原始门禁（非治理）；正式独立门禁、CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；用户阅读验收的记录。

## 11. 限制与后续

本卡只改 WBS，不修改任何已有 Checkpoint、治理库对象或产品。本卡提交在分支 `codex/m2-gov-wbs10-writeback`，是 `codex/m2-gov-wbs9-attest` 之上的一个仅含文档的后继提交，**不推送、不合并**；是否推送与合并仍由用户另行授权。不含对近期核对发现的新问题（CHG 文件未提交、旧 release 校验不通过、manifest 笔误、工具版本约束失真等）的任何处置，那些需要另一张台账文档卡并由用户决定。
