# M2-GOV-WBS11｜发布治理批次状态写回实施卡

> 卡片编号：`CARD-SW008-M2-GOV-WBS11`
> 版本：`V1.0`（2026-10-10；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-10 预授权当日排期，原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾；条件见 §7）
> 档次：文档档（只改 WBS 一个文件，不改任何产品、测试、规则文档、台账）
> 隔离基线：`7506af72230e669dc8b460d596c028cc9d9eba0c`（卡 093 的提交，本地分支 `codex/m2-trk-check`；卡 093 的 Run/Work 已达技术终态）
> 路径根：`SYS-2026-001_WorkspaceGovernance`
> 治理任务基线：WBS V3.0.26；冻结条款 §4.11（“状态写回”是冻结后允许的唯一 WBS 动作）
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-10）

1. **为什么**：WBS 当前投影（V3.0.26）停在发布治理整顿批次之前：卡 085 的行还写着 PLANNED，卡 086～094 没有任何任务行，历史队列 H02～H10 的核对结果没有写入。任何后续 Agent 读到的是过期状态。
2. **做什么**（只改 WBS 一个文件，V3.0.26 → V3.0.27）：①新增 §4.7.12：批次任务与状态表（提交、父提交、变更单及其状态、Run、Work）、结果清单（本地 tag 数量、标注记录、锁定依赖与环境记录、忽略规则、检查工具的指纹与真实试跑结果）、历史队列 H02～H10 的只读核对表、未决事项；②新增十个任务行 `M2-GOV-TD8`、`M2-RGOV-0`、`M2-GOV-CHGIMP`、`M2-GOV-TD9`、`M2-RGOV-1`、`M2-GOV-RANN`、`M2-GOV-RTOOL`、`M2-GOV-GIGN`、`M2-GOV-TRK`、`M2-GOV-WBS11`（任务计数 157 → 167）；③把 `M2-GOV-WBS10` 行更新为已验收的事实；当前投影的 M2 行状态追加批次标记、证据追加一句；④版本记录一行与文末状态段。
3. **批次事实（卡生成时现读，写入 WBS 的值以门禁时的现读为准）**：
   - 卡 085（`M2-GOV-WBS10`）：变更单 CHG-DOCU-2026-034 completed，提交 `aa02be02`
   - 卡 086（`M2-GOV-TD8`）：变更单 CHG-DOCU-2026-026 completed，提交 `425f8b09`
   - 卡 087（`M2-RGOV-0`）：变更单 CHG-DOCU-2026-027 completed，无提交
   - 卡 088（`M2-GOV-CHGIMP`）：变更单 CHG-DOCU-2026-028 completed，提交 `5b7056d2`
   - 卡 089（`M2-GOV-TD9`）：变更单 CHG-DOCU-2026-029 implementing，提交 `6e250842`
   - 卡 090（`M2-RGOV-1`）：变更单 CHG-DOCU-2026-030 implementing，无提交
   - 卡 091（`M2-GOV-RANN`）：变更单 CHG-DOCU-2026-031 implementing，提交 `5c157f73`
   - 卡 092（`M2-GOV-RTOOL`）：变更单 CHG-DOCU-2026-032 implementing，提交 `11a829c1`
   - 卡 094（`M2-GOV-GIGN`）：变更单 CHG-DOCU-2026-033 implementing，提交 `8cb8dceb`
   - 卡 093（`M2-GOV-TRK`）：变更单 CHG-SCPT-2026-401 implementing，提交 `7506af72`
   已由用户验收（变更单 completed）的卡 085、086、087、088；技术完成、变更单在 implementing 等用户阅读后验收的卡 089、090、091、092、094、093。**本修订不替用户验收任何变更单。**
4. **不做什么**：不宣布 M2 里程碑验收（这是用户的决定，投影里仍是 `AWAITING_USER_MILESTONE_ACCEPTANCE`）；不处置历史队列里任何对象（H04～H06、H08、H09 的处置需用户另行批准）；不登记新债务；不改任何产品、规则、台账、`.trae`；不合并、不推送（含 tag）、不部署。
5. **检查**：检查器把 §4.7.12 的批次表与 git（提交、父提交）、变更单文件的状态、治理库的 Run/Work 状态逐项核对；本地 tag 数量与实际一致；文件指纹与基线提交里的字节一致；H02～H07 的状态与治理库一致；任务行的状态词与变更单实际状态一致。25 个反例（history_row_deleted、unlisted_cell_changed、version_row_lost、d08_changed、duplicate_id_row、bad_commit_sha、missing_change_request、missing_debt_id、freeze_clause_removed、v07_not_deferred、batch_wrong_commit、batch_wrong_parent、batch_chg_state_mismatch、batch_run_state_wrong、tag_count_wrong、artifact_sha_wrong、h_state_wrong、row_status_overclaim、milestone_overclaim、new_row_missing、placeholder_left、crlf、out_of_scope、tampered_bytes、wrong_column_count）都必须被对应断言拒绝。其余沿用卡 085 的判据（相对 V3.0.26 只改列明的行与单元格、其余只加不删、D08 与冻结条款不变、引用的 SHA/变更单/债务编号/Run/Work/Checkpoint/Decision/release/文件真实存在、字节等于冻结值）。**它不证明内容就是用户的意思**，这由用户验收。
6. 我在隔离演练树上完整跑了一遍（非受治理执行，不能复用为正式门禁）：基线、安装、候选三步原始退出码均 0；G1–G9 全部 PASS（含候选上的 `doc check` exit 0）；25 项内存负向对照都改变了目标输入并被指定断言拒绝；`gate_verdict` SHA-256 `6bec981557ad675915aa5d5907b114885d8401bd97e21022a9cbedbe09f782d0`，`DONE` SHA-256 `63fa44bcfa2cd76762641ac3dfd42e96d3859b313111264e83766a5d2e17343b`；证据目录 `.auto-pm/reports/m2-wbs11/gates_rehearsal/`。
7. 检查工具的真实试跑（卡 093 的工具，只读，对控制根与分支 `codex/m2-trk-check`）：检查 496 个变更单文件，24 个不在该分支提交里；输出 `.auto-pm/reports/m2-wbs11/tracking_run.json`。
8. 不在本卡范围：任何产品、测试、模板、台账、规则文本、`.trae`；改写已有 Checkpoint 或治理库；合并 main、推送、部署；M3 的任何事项；历史队列的任何处置。

## 2. 单一目标与完成定义

把发布治理整顿批次的状态与历史队列核对写进 WBS V3.0.27，只改这一个文件。技术完成 = 提交通过全部门禁、提交字节等于 Checkpoint；**验收 = 用户阅读 §4.7.12 与投影状态后确认**，变更单收口不委托。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线、唯一 owned path 及冻结的最终字节、基线 WBS 字节等于冻结的 `base_wbs.md`。启动脚本有只读的 `--check-only`，预检只用它。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. 核对卡 093 的 Run SUCCEEDED、Work CLOSED；基线分支 `codex/m2-trk-check` 等于基线。
4. 新候选 HEAD 等于基线且 clean、index 空；工具、配置、负向计划均匹配冻结指纹。
5. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`；门禁用后台等待，不反复轮询。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | 修改：基线为 V3.0.26，写成 V3.0.27（相对路径根 `SYS-2026-001_WorkspaceGovernance`） |

出现第二条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-wbs11/`、本卡文件、演练工作树）不是额外产品 owned paths，不进本卡提交。

## 5. 字节合同

唯一最终文件 SHA-256：`27411f80694e864dbcb556db31cb8aef09ce19b4d4cc1ec0aba617d6bc730c56`（基线 V3.0.26 字节 SHA-256 `b667b5451a0b22ca2a2cb7922ff0c4d312d27f3fb04afab95f909509f2189a30`）。UTF-8、LF、无 BOM。冻结的最终文件保存在 `.auto-pm/reports/m2-wbs11/proto/`，由 `patch_wbs11.py` 从 V3.0.26 与 `facts11.json` 确定性生成；安装器只在明确安装阶段确认基线字节后写入，判卷器不得调用安装或生成。

1. 变更集恰为这一个修改文件；其余基线字节不变。
2. **相对 V3.0.26，只允许下表 4 行被替换，且只改列明的单元格**（“追加”＝新文本必须以旧文本开头；“替换”＝该单元格改变）；其余 V3.0.26 的行全部保留且顺序不变，所有版本记录行保留；新增行须满足第 3 至 5 条。

| # | 被替换的行（前缀） | 改变的单元格 |
|---|---|---|
| 1 | `> 文档版本：V3.0.26` | 版本与日期，并在“状态写回登记于 §4.7.11（V3.0.26）。”之后插入一句 |
| 2 | `> 本文件给出 4 个产品里程碑、157 个任务` | 157 → 167 |
| 3 | `\| M2 \|`（当前投影） | 状态（替换，追加批次标记并保留 `AWAITING_USER_MILESTONE_ACCEPTANCE`）、证据（追加） |
| 4 | `\| M2-GOV-WBS10 \|` | 状态（替换为已验收的事实） |

3. `D08` 行与 V3.0.26 完全相同；冻结条款（§4.11 的 ①～⑤）与延期承诺表不变；§4.7.10、§4.7.11 的字节不变。新增任务行恰为上述十个，任务 ID 行由 157 变为 167 且无重复。
4. 新增文字中的每个提交 SHA、树、变更单、债务编号、Run/Work/Checkpoint（本卡自己的 Work/Run/Checkpoint 编号除外）、Decision、release、`.auto-pm/` 文件都真实存在；批次表里每个提交与父提交等于 git 的记录、每个变更单状态等于变更单文件、每个 Run/Work 状态等于治理库；本地 tag 数量等于实际；文件指纹等于基线提交里的字节；无占位符残留；表格列数不比 V3.0.26 更差。
5. 当前投影的 M2 状态不得含 `ACCEPTED` 或 `MILESTONE_ACCEPTED` 标记（子项的 `*_ACCEPTED` 除外）并必须含 `AWAITING_USER_MILESTONE_ACCEPTANCE`；任务行的 `COMPLETED / ACCEPTED` 只能对应 completed 的变更单。
6. 验证只读，负向对照仅修改内存中的输入；每个样本必须改变目标输入并被对应目标断言拒绝。
7. 工具与配置的 manifest 已冻结，SHA-256 为 `c47f221deafeb1048ba7a81a8913dc8b185df9b86ad908df252778ccb204eae4`；实际运行必须由外部传入该期望值。共享判卷器 SHA-256 为 `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188`。
8. 门禁前后逐一记录最终文件 SHA，全部相同且等于本卡。

冻结工具（`.auto-pm/reports/m2-wbs11/`，由卡 085 的已治理工具派生，判断部分改为批次表、变更单与 Run/Work 状态、tag、文件指纹与队列状态的核对）：

| 工具 | SHA-256 |
|---|---|
| `wbs11_runner.py` | `81534bdf81f366b753d3e5de61160240b697080b99e9a2d0d1b3810cc31af866` |
| `wbs11_check.py` | `ee312f9e539255d0ac7dfa0e3dd82edba371e417f5e59496fa79fb03e9f704a6` |
| `install_candidate.py` | `ff365e77401276d98492aeed38b36337f0556f07d24fc708b2feffc09bb50bc7` |
| `prepare_wbs11.py` | `a41c9946d62903bb40e7d16a8766d63f6beeadd4f37f26cc62f1fc164918b3a2` |
| `patch_wbs11.py` | `167c0d8d13ca7e0dc872127b1f7734be1bd9daf5758a06207210d6507dc9f8f8` |
| `collect_facts11.py` | `8f40847e8d853c28c37f9d2fa7c086afd2671f7acebce9fd6599f441a643e0a4` |
| `wbs11_config.json` | `b3821680678ae795fb2bc567d35c963812c7ccde5a9e11a2130be6dc5627868a` |
| `facts11.json` | `1426aa579ff7f247750f2c6e4873f8a493d3ac954c18d3d2697725fad710e475` |
| `base_wbs.md` | `b667b5451a0b22ca2a2cb7922ff0c4d312d27f3fb04afab95f909509f2189a30` |

## 6. 门禁矩阵

顺序：基线测量 → 显式安装 → 最终候选测量和判卷。任一非零或环境异常立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份、工作树与初始 hook | HEAD 为基线、clean、index 空，WBS 基线字节等于冻结值；真实 hook 指纹非空 |
| G2 | 基线文档检查 | 根入口 `main.py doc check` 显式传控制根与候选根，原始 exit 0 |
| G3 | 安装前治理台账 | 根入口 `main.py ledger reconcile SYS-2026-001`，无 fix，exit 0 且 0/0/0 |
| G4 | 最终候选文档检查 | 同根入口，原始 exit 0；受检前后字节均等于冻结值 |
| G5 | 安装后治理台账 | 同只读对账，原始 exit 0 且 0/0/0 |
| G6 | 文档语义 | §5 全部成立，含批次事实与 git、变更单文件、治理库逐项相符 |
| G7 | 真实 hook 保全 | 运行前后全部真实 hook 字节相同 |
| G8 | 轻量负向对照（25 项） | history_row_deleted、unlisted_cell_changed、version_row_lost、d08_changed、duplicate_id_row、bad_commit_sha、missing_change_request、missing_debt_id、freeze_clause_removed、v07_not_deferred、batch_wrong_commit、batch_wrong_parent、batch_chg_state_mismatch、batch_run_state_wrong、tag_count_wrong、artifact_sha_wrong、h_state_wrong、row_status_overclaim、milestone_overclaim、new_row_missing、placeholder_left、crlf、out_of_scope、tampered_bytes、wrong_column_count，各由对应断言拒绝 |
| G9 | 最终范围与字节 | 实测变更仅唯一 owned 文件（修改）、HEAD 仍基线、index 空；完整改动清单及前后 SHA 绑定 |

判卷另由冻结的 `m2-tools/verdict_check.py` 核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-10 预授权当日排期（原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾）：卡 SHA 先在汇报里报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧；不做真实模型调用 |
| **内容验收** | **用户阅读 §4.7.12 与投影状态后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在汇报里报告最终卡 SHA 与改动摘要。
2. 创建 SYS-2026-001 DOCU/OPT 变更单、匹配 Decision（`DEC-<当天>-WBS11WRT`）、Work `WORK-SYS001-M2-GOV-WBS11-001`、Run `RUN-SYS001-M2-GOV-WBS11-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）；实际创建前验证未被占用。
3. 从代码基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-wbs11`，分支 `codex/m2-gov-wbs11-writeback`。
4. 安装最终字节并完整重跑门禁（`wbs11_gates_all.sh`）；先创建当前字节 Checkpoint，再正常 Hook 提交唯一 owned 文件，绝不 no-verify；核对提交父、范围及 blob 与 Checkpoint 完全一致。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；**变更单停在“实施中”，等用户验收后再收口**。

## 9. 硬停止

基线、工具/卡/Decision 指纹、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败；负向目标未命中；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要改这一个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮；不处置任何历史失败对象。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结工具、事实文件与最终文件；演练原始门禁（非治理）；正式独立门禁、CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；用户阅读验收的记录。

## 11. 限制与后续

本卡只改 WBS，不修改任何已有 Checkpoint、治理库对象或产品。本卡提交在分支 `codex/m2-gov-wbs11-writeback`，是 `codex/m2-trk-check` 之上的一个仅含文档的后继提交，**不推送、不合并**；是否推送与合并、本批次的变更单入库、历史队列的处置，均由用户另行裁决。
