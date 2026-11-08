# M2-GOV-WBS9｜整合卡最终提交证明与状态写回实施卡

> 卡片编号：`CARD-SW008-M2-GOV-WBS9`
> 版本：`V1.0`（2026-10-09；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / APPROVED`（用户 2026-10-09 傍晚“选 A，今晚做”，原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾；这是对 22:00“不再起新卡”约束的明确延长；条件见 §7）
> 档次：文档档。分档器（卡 078）对本卡路径的计算结果：文档档，命中规则 `DOCS-WORKSPACE-GOVERNANCE`，规则表版本 1.0（SHA-256 `26e3480c6420566619e9d13c98f0b761ffdd01ff0924417ba7e9b65568355e4a`），声明“文档档”无冲突
> 隔离基线：`1d0be4af46423b46b8521884aaca98c42943f8a8`（`M2-DEP-INT` 合并提交，分支 `codex/m2-dep-int-adj-ic02`；CHG-SCPT-2026-399 completed）
> 路径根：`SYS-2026-001_WorkspaceGovernance`
> 治理任务基线：WBS V3.0.24；GPT 最终审计 `.auto-pm/reports/m2-relay/m2-final-audit-20261009/gpt-output/AUDIT_REPORT_FINAL.md`（SHA-256 `66cc5dcd8b5dcbda08b517053b3df17eedf0454642f0c1adda6cdf201b63852d`）的阻断项 B-01
> 执行模型：`claude-sonnet-5-5`
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-09）

1. **为什么**：GPT 最终审计阻断项 B-01：整合卡的 Checkpoint 在治理库里只绑定启动基线 `f06c5aac` 与候选文件哈希，没有最终合并提交 `1d0be4af`。我核实：这是该库的既有设计（`checkpoint.git_head` 必须等于 Run 的启动 `git_head`，Checkpoint 先于提交创建），46 张卡同此；但“部署的就是经门禁的提交”确实应能从治理记录独立复核。
2. **为什么不改治理库**：给库增加“最终提交”对象类型是新增产品功能，不在 M2 冻结范围。所以本卡把证明写进 WBS 一个新节（§4.7.10），靠 git 提交历史保证只追加。
3. **做什么**（只改 WBS 一个文件，V3.0.24 → V3.0.25）：①新增 §4.7.10：最终提交 `1d0be4af46423b46b8521884aaca98c42943f8a8`、两个父提交、树 `644c5732219f48b7863444b6e5cfddd166e7d3d7`、20 个受控文件的 SHA-256、判卷文件 SHA-256 与 G1–G9 结论、合并可重现（G8）、复核方法、对技术部署的要求；②把已由用户验收的 N1a、N2-0、最小 WBS 卡与已收口的整合卡写回当前投影与任务行；③新增任务行 `M2-GOV-WBS9`（任务计数 155 → 156）与版本记录一行与文末状态段。
4. **检查**：检查器把节里的提交、父提交、树和 20 个文件 SHA-256 逐项与 git 对象核对；三个反例（错误的提交、错误的树、任一文件字节漂移）必须各被对应断言拒绝；其余沿用卡 081 的判据（相对 V3.0.24 只改列明的行与单元格、其余只加不删、D08 与冻结条款不变、引用的 SHA/变更单/债务编号/文件真实存在、字节等于冻结值）。**它不证明内容就是用户的意思**，这由用户验收。
5. 我在隔离演练树上完整跑了一遍（非受治理执行，不能复用为正式门禁）：基线、安装、候选三步原始退出码均 0；G1–G9 全部 PASS（含候选上的 `doc check` exit 0）；19 项内存负向对照都改变了目标输入并被指定断言拒绝（含上述三个反例）；`gate_verdict` SHA-256 `c1cb03e656eb9e19f8eeab2bcf22a10f3cd14528a716ef456a597a4032c39891`，`DONE` SHA-256 `15745ca6bfdf6f5b78a883f6621e42995eccee2df54c44c3a8912cb7bbab84b9`；证据目录 `.auto-pm/reports/m2-wbs9/gates_rehearsal/`。
6. 不在本卡范围：任何产品、测试、模板、台账、规则文本、`.trae`；改写已有 Checkpoint 或治理库；技术部署、推送、合并 main；M3 的任何事项。

## 2. 单一目标与完成定义

把整合卡的最终提交证明与已验收状态写进 WBS V3.0.25，只改这一个文件。技术完成 = 提交通过全部门禁、提交字节等于 Checkpoint；**验收 = 用户阅读 §4.7.10 与投影状态后确认**，变更单收口不委托。

## 3. 实施前预检

1. 核对卡字节与已向用户报告的 SHA 一致、基线、唯一 owned path 及冻结的最终字节、基线 WBS 字节等于冻结的 `base_wbs.md`。启动脚本有只读的 `--check-only`，预检只用它。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. 核对前置整合卡（CHG-SCPT-2026-399）为 completed 且其 Run SUCCEEDED、Work CLOSED。
4. 新候选 HEAD 等于基线且 clean、index 为空；工具、配置、负向计划均匹配冻结指纹。
5. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`；门禁用后台等待，不反复轮询。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | 修改：基线为 V3.0.24，写成 V3.0.25（相对路径根 `SYS-2026-001_WorkspaceGovernance`） |

出现第二条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-wbs9/`、本卡文件、演练工作树）不是额外产品 owned paths，不进本卡提交。

## 5. 字节合同

唯一最终文件 SHA-256：`5d09d21b3c9c67024941b5f1d4afb5a06069fce43d08a0e5b7887db595b1c326`（基线 V3.0.24 字节 SHA-256 `dcebc57c78dfb5b32163fdab66650ac9980cac63dfeb978cf8c9b2f3da34cec0`）。UTF-8、LF、无 BOM。冻结的最终文件保存在 `.auto-pm/reports/m2-wbs9/proto/`，由 `patch_wbs9.py` 从 V3.0.24 与 `facts9.json` 确定性生成；安装器只在明确安装阶段确认基线字节后写入，判卷器不得调用安装或生成。

1. 变更集恰为这一个修改文件；其余基线字节不变。
2. **相对 V3.0.24，只允许下表 7 行被替换，且只改列明的单元格**（“追加”＝新文本必须以旧文本开头；“替换”＝该单元格改变）；其余 V3.0.24 的行全部保留且顺序不变，所有版本记录行保留；新增行须满足第 3 至 5 条。

| # | 被替换的行（前缀） | 改变的单元格 |
|---|---|---|
| 1 | `> 文档版本：V3.0.24` | 版本，并在“登记于 §4.7.9（V3.0.24）。”之后插入一句 |
| 2 | `> 本文件给出 4 个产品里程碑、155 个任务` | 155 → 156 |
| 3 | `\| M2 \|`（当前投影） | 状态（替换）、证据（追加）、下一步（替换） |
| 4 | `\| M2-N1A \|` | 状态（替换） |
| 5 | `\| M2-N2-0 \|` | 状态（替换） |
| 6 | `\| M2-DEP-INT \|` | 状态（替换） |
| 7 | `\| M2-GOV-WBS8 \|` | 状态（替换） |

3. `D08` 行与 V3.0.24 完全相同；冻结条款（§4.11 的 ①～⑤）与延期承诺表不变。新增任务行恰为 `M2-GOV-WBS9`，任务 ID 行由 155 变为 156 且无重复。
4. 新增文字中的每个提交 SHA、树、变更单、债务编号、Run/Work/Checkpoint（本卡自己的 Work/Run/Checkpoint 编号除外）、`.auto-pm/` 文件都真实存在；§4.7.10 的提交、父提交、树与 20 个文件 SHA-256 与 git 对象逐项相符；无占位符残留；表格列数不比 V3.0.24 更差。
5. 验证只读，负向对照仅修改内存中的输入；每个样本必须改变目标输入并被对应目标断言拒绝。
6. 工具与配置的 manifest 已冻结，SHA-256 为 `e62b93931eef4303cca3aac379c2955e5cb0bc4e2aab4bf695087732028592ea`；实际运行必须由外部传入该期望值。共享判卷器 SHA-256 为 `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188`。
7. 门禁前后逐一记录最终文件 SHA，全部相同且等于本卡。

冻结工具（`.auto-pm/reports/m2-wbs9/`，由卡 081 的已治理工具派生，判断部分增加最终提交证明的核对）：

| 工具 | SHA-256 |
|---|---|
| `wbs9_runner.py` | `9e4d15c1908e0b8ef499ebf202fd7663aba40e8fffcdb5449ea7b9c060ecf0de` |
| `wbs9_check.py` | `776a4510955e36ee220e6ee4e1ea8cfb2ee379f89cd1506b93ceae9c3048ad4d` |
| `install_candidate.py` | `fdf67e38d3889382b314b95f4ce1b19bafc192eaa34e1cb9d664adf7c78f7cf6` |
| `prepare_wbs9.py` | `171caa14b4af7f10ad5c0d8217ceff4bce4c70c3be83b38e56c3bf7c06c66f27` |
| `patch_wbs9.py` | `0c7c83cfc250abe4bddb53659e27409739ae3aef9cad5c6ba0790c157a4c8d40` |
| `collect_facts9.py` | `cde79d9301a96c600802a0a7d12bb0b5a9e0f5716e764956f163f9873fb9d257` |
| `wbs9_config.json` | `fc94e1787f9ae76aa84bcc35e8c0ebdab38903defd02497367f75fcb6d2b6b0a` |
| `facts9.json` | `f5d546518036dfb1ccd24153c6fa3c9bcc275c393320a0cf489eab84a63de545` |
| `wbs7_text.md` | `dcebc57c78dfb5b32163fdab66650ac9980cac63dfeb978cf8c9b2f3da34cec0` |
| `base_wbs.md` | `dcebc57c78dfb5b32163fdab66650ac9980cac63dfeb978cf8c9b2f3da34cec0` |

## 6. 门禁矩阵

顺序：基线测量 → 显式安装 → 最终候选测量和判卷。任一非零或环境异常立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份、工作树与初始 hook | HEAD 为基线、clean、index 空，WBS 基线字节等于冻结值；真实 hook 指纹非空 |
| G2 | 基线文档检查 | 根入口 `main.py doc check` 显式传控制根与候选根，原始 exit 0 |
| G3 | 安装前治理台账 | 根入口 `main.py ledger reconcile SYS-2026-001`，无 fix，exit 0 且 0/0/0 |
| G4 | 最终候选文档检查 | 同根入口，原始 exit 0；受检前后字节均等于冻结值 |
| G5 | 安装后治理台账 | 同只读对账，原始 exit 0 且 0/0/0 |
| G6 | 文档语义 | §5 全部成立，含最终提交证明与 git 对象逐项相符 |
| G7 | 真实 hook 保全 | 运行前后全部真实 hook 字节相同 |
| G8 | 轻量负向对照（19 项） | history_row_deleted、unlisted_cell_changed、version_row_lost、d08_changed、duplicate_id_row、bad_commit_sha、missing_change_request、missing_debt_id、freeze_clause_removed、v07_not_deferred、dep_tech_keeps_v07、attest_wrong_commit、attest_wrong_tree、attest_file_drift、placeholder_left、crlf、out_of_scope、tampered_bytes、wrong_column_count，各由对应断言拒绝 |
| G9 | 最终范围与字节 | 实测变更仅唯一 owned 文件（修改）、HEAD 仍基线、index 空；完整改动清单及前后 SHA 绑定 |

判卷另由冻结的 `m2-tools/verdict_check.py` 核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-09 傍晚“选 A，今晚做”（原话 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾）：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧；不做真实模型调用 |
| **内容验收** | **用户阅读 §4.7.10 与投影状态后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与改动摘要。
2. 创建 SYS-2026-001 DOCU/OPT 变更单、匹配 Decision（`DEC-<当天>-WBS9ATTE`）、Work `WORK-SYS001-M2-GOV-WBS9-001`、Run `RUN-SYS001-M2-GOV-WBS9-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）；实际创建前验证未被占用。
3. 从代码基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-wbs9`，分支 `codex/m2-gov-wbs9-attest`。
4. 安装最终字节并完整重跑门禁（`wbs9_gates_all.sh`）；先创建当前字节 Checkpoint，再正常 Hook 提交唯一 owned 文件，绝不 no-verify；核对提交父、范围及 blob 与 Checkpoint 完全一致。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；**变更单停在“实施中”，等用户验收后再收口**。

## 9. 硬停止

基线、工具/卡/Decision 指纹、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败；负向目标未命中；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要改这一个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，今天不开第二轮；不处置任何历史失败对象。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结工具、事实文件与最终文件；演练原始门禁（非治理）；正式独立门禁、CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；用户阅读验收的记录；GPT 对 B-01 的只读复审。

## 11. 限制与后续

本卡只改 WBS，不修改任何已有 Checkpoint、治理库对象或产品。最终提交证明的可信度来自 git 提交历史与可复核的 SHA，不来自治理库的新对象类型。技术部署由用户在 GPT 复审之后另行明确批准；推送另行授权。无合并 main、推送、部署或 release 切换授权。
