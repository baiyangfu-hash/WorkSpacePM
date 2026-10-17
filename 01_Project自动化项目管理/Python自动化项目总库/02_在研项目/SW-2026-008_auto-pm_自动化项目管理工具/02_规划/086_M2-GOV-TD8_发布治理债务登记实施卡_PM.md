# M2-GOV-TD8｜发布治理债务登记实施卡

> 卡片编号：`CARD-SW008-M2-TD8`
> 版本：`V1.0`（2026-10-09；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PENDING_USER_APPROVAL`（用户 2026-10-09 夜批准起草；本卡 SHA 报给用户之后，须用户在聊天中回复批准才启动；条件见 §7）
> 档次：文档档；只登记，不处理债务
> 隔离基线：`aa02be02674e062f0ececcfe69b565860ffbe55c`（WBS 写回卡 085 的提交，分支 `codex/m2-gov-wbs10-writeback`；CHG-DOCU-2026-034 completed）
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 治理任务基线：WBS V3.0.26（本卡不修改 WBS）
> 对应 WBS：发布治理整顿批次（M2 之后、M3 之前；本卡之后由用户决定是否写入 WBS）
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033，以及基线提交中的《M2 门禁分档与单卡规模规则》（文档档：不需要 pytest 全量）。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-09 夜）

1. 台账规则 3：新发现的问题先登记债务编号再决定修复，不得只留在聊天记录中。用户要求的“发布治理整顿”（盘点卡、推送、入库、标注、锁定工具版本）必须有债务编号作依据。
2. 事实来源是静态证据文件 `.auto-pm/reports/RELEASE_GOVERNANCE_FINDINGS_20261009.md`（SHA-256 `8d9b87374f537b2a687b0dbfaeed749f481d6b58ab9547b4d981f211dc73f305`），所有数字都来自 2026-10-09 夜的只读命令输出。
3. 基线台账原字节 SHA-256 为 `985636f4d33c4c48caa7f34b0a6a2f8db4d9a37d9aa807b56e2cc7d742ea25f6`（编号最高 107）。
4. **改三条既有债务行**，每行只许改一列：事实证据（末尾追加；旧内容是新内容的前缀）；其余八列一字不改，状态保持“活动”：

| 编号 | 动作 |
|---|---|
| TD-SW008-009 | 追加进展：未入库的不只是指针文件，164 个 CHG 正文不在任何提交里；根因与处置见新增 108、113，公开仓库见 112 |
| TD-SW008-019 | 追加进展：最近 7 个 release 载荷目录未被 Git 跟踪；5 个校验不通过、6 个源码提交不在远端；见新增 109、110、111 |
| TD-SW008-026 | 追加进展：M2 新增表而版本常量仍为 v7，真实库 schema_meta 仍只有 v2、v3，裁决仍未做 |

5. **追加新行**（TD-SW008-108～114）：

| 编号 | 内容 | 优先级 |
|---|---|---|
| TD-SW008-108 | 治理记录没有进入任何提交：164 个 CHG 正文与已修改的台账只在本机磁盘 | P0 |
| TD-SW008-109 | 5 个 release 载荷 exact-tree 校验不通过且 manifest 没有标注 | P1 |
| TD-SW008-110 | `1.2.4-6699a5b` 的 source_commit 在 manifest 与 release_meta 里写错，另有两个短 SHA | P1 |
| TD-SW008-111 | 6 个 release 的源码提交不在任何 origin 分支上 | P0 |
| TD-SW008-112 | 远端仓库公开，内容未经审查（含 PLC 项目目录），已推送的视为已公开 | P0 |
| TD-SW008-113 | 对账与文档检查不检查 CHG 文件是否被 Git 跟踪，缺口在全绿下长期存在 | P1 |
| TD-SW008-114 | pyproject 工具版本约束与实际环境四项不一致且无锁文件 | P1 |

6. 我在隔离演练树上用本卡的专用检查器完整跑了一遍（非受治理执行，不能复用为正式门禁）：基线、安装、候选三步原始退出码均 0；G1–G9 全部 PASS；18 项内存负向对照都改变了目标输入并被指定断言拒绝；共用判卷器退出 0；`gate_verdict` SHA-256 `567bbd82f435b82cf1799e77447d465d325c89c90b7d5dcac35520b4a69b7251`，`DONE` SHA-256 `86cd59e1e66002f37f0f1f230140b541190c1c244da7accd4b0b8e20c38115f2`；证据目录 `.auto-pm/reports/m2-td8/gates_rehearsal/`。
7. 不在本卡范围：处置任何债务或失败记录；推送、打 tag、合并、入库 CHG；改 WBS；任何产品、测试、模板改动。

## 2. 单一目标与完成定义

让台账登记本批发现：改三行（只追加证据）、追加七行新行；只修改一个文件。技术完成 = 提交通过全部门禁、提交字节等于 Checkpoint；**验收 = 用户阅读新增与更新的行后确认**，变更单收口不委托。

## 3. 实施前预检

1. 核对卡字节与已向用户报告的 SHA 一致、基线、唯一 owned path 及最终字节。启动脚本有只读的 `--check-only`，预检只用它。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. 核对前置 CHG-DOCU-2026-034 completed；origin 上的分支不受本卡影响。
4. 新候选 HEAD 等于基线且 clean、index 为空、基线台账 SHA 一致；工具、配置、负向计划及原始证据引用均匹配冻结指纹。
5. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`；门禁后台等待，不反复轮询。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `04_监控/02_整改项/活动技术债台账.md` | 存在 | 改 009、019、026 三行（只追加证据列）；在 §2.2 末尾、§3 之前插入新行 108～114；其余原字节不变 |

出现第二条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-td8/`、本卡文件、演练工作树）不是额外产品 owned paths，不进本卡提交。

## 5. 字节合同

唯一最终文件 SHA-256：`dcb958409b6562994fd51a8a2902279e85a2748b5eefa1fe2c9f27473795892c`。UTF-8、LF、无 BOM。冻结的最终台账、行更新与新增行保存在 `.auto-pm/reports/m2-td8/`（`proto/`、`updated_rows.md`、`new_rows.md`）；安装器只在明确安装阶段核对基线后写入，判卷器不得调用安装或生成。

1. 除所列更新行与新增行外，全部基线原字节不变；更新行中除事实证据外的八列不变，事实证据只追加，状态保持“活动”。
2. 新号从基线最大编号后连续增长（108～114），无重复，九列齐全，优先级与状态合法，证据非空且引用文件存在，不记已偿还。
3. 追加文字里反引号包围的文件引用必须真实存在：`.auto-pm/` 下的证据文件匹配冻结 SHA。
4. 验证只读，负向对照仅修改内存中的输入；每个样本必须改变目标输入并被对应目标断言拒绝。
5. 工具与配置的 manifest 已冻结，SHA-256 为 `9ace156c1b44754af5fcfcd0697eed290c7bb5ea4c229f92ba122b6d50ed83f0`；实际运行必须由外部传入该期望值。共享判卷器 SHA-256 为 `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188`。
6. 门禁前后逐一记录最终文件 SHA，全部相同且等于本卡。

冻结工具（`.auto-pm/reports/m2-td8/`；运行器与安装器沿用 TD7 已验收代码，仅改名；检查器的辅助函数沿用，判断部分由配置驱动）：

| 工具 | SHA-256 |
|---|---|
| `td8_runner.py` | `00e6386d34e789100e9eeac2e725b0bb5d78cb4eee4ede838cbabf120227b379` |
| `td8_check.py` | `d4ba55f29de8968835d8c5a06883bee79830fe3e02f8ce094001948753bb60e8` |
| `install_candidate.py` | `490d16adfd91b67e987591bdda97704d6438f51c249104508109dff7cbfefe07` |
| `prepare_td8.py` | `0d26f65e609d056748fbb77b9e77e1c807dde56ffbab6b042ca5613da6f13c5f` |
| `td8_config.json` | `3e9b8f29b6f9900c9bd64514d3ff85ec1b9d07eec91ec04dba9990ab656b1c3e` |
| `updated_rows.md` | `fb9fdc89c5826b26d7fe104c1f3bb5fedf1d2cb95fb292060e9cc9ff5ba221ad` |
| `new_rows.md` | `5d94f10701b244de650c26409fbbf77ec7f3c829f06a6dd9f69525921876d7da` |
| `base_ledger.md` | `985636f4d33c4c48caa7f34b0a6a2f8db4d9a37d9aa807b56e2cc7d742ea25f6` |

## 6. 门禁矩阵

顺序：基线测量 → 显式安装 → 最终候选测量和判卷。任一非零或环境异常立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份、工作树与初始 hook | HEAD 为基线、clean、index 空，台账为原字节；真实 hook 指纹非空 |
| G2 | 基线文档检查 | 根入口 `main.py doc check` 显式传控制根与候选根，原始 exit 0 |
| G3 | 安装前治理台账 | 根入口 `main.py ledger reconcile SW-2026-008`，无 fix，exit 0 且 0/0/0 |
| G4 | 最终候选文档检查 | 同根入口，原始 exit 0；受检前后字节均等于冻结值 |
| G5 | 安装后治理台账 | 同只读对账，原始 exit 0 且 0/0/0 |
| G6 | 台账语义、旧字节、引用 | §5 全部成立 |
| G7 | 真实 hook 保全 | 运行前后全部真实 hook 字节相同 |
| G8 | 轻量负向对照（18 项） | modify_other_row、delete_row、revert_one_update、change_priority、change_acceptance、replace_evidence、illegal_status、overclaim_repaid、dead_reference、out_of_scope、tampered_bytes、crlf、new_row_missing、new_row_duplicate_id、new_row_invalid_priority、new_row_repaid、new_row_empty_evidence、new_row_dead_reference，各由对应断言拒绝 |
| G9 | 最终范围、HEAD、index、diff | 实测变更仅唯一 owned 文件、HEAD 仍基线、index 空、无未跟踪残留；完整 diff 及前后 SHA 绑定 |

判卷另由冻结的 `m2-tools/verdict_check.py` 核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-09 夜批准起草本卡；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读新增与更新的行后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与登记摘要，等用户批准。
2. 创建独立 SW-2026-008 DOCU/OPT 变更单、匹配 Decision（`DEC-<当天>-TD8DOCS0`）、Work `WORK-SW008-M2-TD8-001`、Run `RUN-SW008-M2-TD8-001`（租约不超过 3600 秒）；实际创建前验证未被占用。
3. 从代码基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-td8`，分支 `codex/m2-td8-docs`。
4. 安装最终字节并完整重跑门禁（`td8_gates_all.sh`）；先创建当前字节 Checkpoint，再正常 Hook 提交唯一 owned 文件，绝不 no-verify；核对提交父、范围及 blob 与 Checkpoint 完全一致。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；**变更单停在“实施中”，等用户验收后再收口**。

## 9. 硬停止

基线、工具/卡/Decision 指纹、owner/scope、lease 或 hook 漂移；新增范围；任何门禁失败；负向目标未命中；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要变更所列行以外的既有台账内容、CHG、WBS、产品、模板、Obsidian 或安全设置：均停止，保留现场，不靠重跑、改字节或放宽判据变绿；不处置任何历史失败对象。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结工具、台账与行更新、新增行；演练原始门禁（非治理）；正式独立门禁、CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；用户阅读验收的记录。

## 11. 限制与后续

本卡只登记，不修任何缺陷、不处置任何失败记录，也不推送：提交在分支 `codex/m2-td8-docs`，是 `codex/m2-gov-wbs10-writeback` 之上的仅含文档的后继提交，**不推送、不合并**。仓库是公开的（TD-SW008-112）：任何包含治理记录、release tag 的推送都要先经盘点卡的敏感信息扫描并由用户逐次授权。无合并、推送、部署或 release 切换授权。
