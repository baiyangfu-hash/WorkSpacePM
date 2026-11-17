# M2-GOV-TD7｜技术债台账同步实施卡

> 卡片编号：`CARD-SW008-M2-TD7`
> 版本：`V1.0`（2026-10-09；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-08 预授权台账同步卡，2026-10-09 白天预授权再次覆盖；原话均见 `.auto-pm/reports/PREAUTH_M2_20261008.txt`；条件见 §7）
> 档次：文档档；只登记与同步，不处理债务
> 隔离基线：`6e17f086e540082cbb8495d95850998d8b9318be`（分支 `codex/m2-v05c-gui-e2e-r2`，CHG-SCPT-2026-396 completed）
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 治理任务基线：WBS V3.0.23，提交 `a538f942f1995f1ec3e50ad45c624bdc123c6bc3`
> 对应 WBS：`M2-GOV-TD7`（本卡不修改 WBS）
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033，以及基线提交中的《M2 门禁分档与单卡规模规则》（文档档：不需要 pytest 全量）。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-09）

1. 台账规则 3：新发现的问题先登记债务编号再决定修复；规则 2：关联 CHG 状态改变时同步台账。F01-1、F02 与 V05-C 的验收事实、失败记录处置方案 A 的结果，以及真实模型联验中发现的新问题（沙箱与权限、脚本预检、快照读取与并发写入冲突、变更单没有作废状态），目前不在台账里或已过时。
2. 基线台账原字节 SHA-256 为 `791aa8ef260e9b366cce0880e2426954e1a40eb13a48bca7cf0a0dda637cadea`（编号最高 102）。
3. **改七条既有债务行**，每行只许改三列：关联 CHG、状态、事实证据（末尾追加；旧内容是新内容的前缀）；编号、问题、负责人、优先级、验收条件、后续 WBS 六列一字不改：

| 编号 | 动作 |
|---|---|
| TD-SW008-086 | 追加进展：用户 2026-10-09 选定处置方案 A，只处置两个租约过期 Run（已执行并收口）；本条对象原样保留；核实变更单状态机没有作废状态，指向新增行 TD-SW008-106；状态保持待执行 |
| TD-SW008-089 | 追加进展：同 086，方案 A 不处置本条对象（CHG-SCPT-2026-386、V05B2 的 Work/Run 原样保留）；指向新增行 TD-SW008-106；状态保持待执行 |
| TD-SW008-091 | 追加更新：TD-SW008-102 已补证，TD6 更正说明所指的强度缺口补上，处置说明与证明一致；状态保持已偿还 |
| TD-SW008-094 | 追加 F02 进展：版本字段必填与消费者重验已补；其余三项（窗口入口超时证明、能力提示文字、F01-a 分支变异）仍待补，状态保持待复核；关联 CHG 由待立改为 F02 的变更单 |
| TD-SW008-095 | 追加第三次出现：F02 第一次受治理执行 core 组 `database is locked`；触发条件含机器负载但测试自身缺有界重试；状态保持待复核 |
| TD-SW008-098 | 追加 F01-1 进展；验收条件里“暂停后拒绝”部分按卡 072 的取舍未采纳，所以状态由待执行改活动，不写已偿还；关联 CHG 改为 F01-1 的变更单 |
| TD-SW008-102 | 追加处置：整库内容比较与真实窗口实演已补，验收条件三项满足；状态由待复核改已偿还；关联 CHG 改为 F01-1 的变更单 |

4. **追加新行**（TD-SW008-103～107）：

| 编号 | 内容 |
|---|---|
| TD-SW008-103 | Windows 沙箱无法按配置的 elevated 模式为 `codex exec` 初始化（node_repl 自锁），V05-C 经用户授权只对模型子进程降为 unelevated；隔离强度降低而非修复 |
| TD-SW008-104 | 治理脚本缺只读预检模式，曾造成未经批准的完整启动（WBS 修订 7 的误启动）；F02 与 V05-C 的脚本已加 `--check-only`，其余仍无 |
| TD-SW008-105 | 界面状态快照读取与并发写入冲突（P1 产品缺陷）：快照的禁止写入共享锁会让另一线程的写入报只读，批准点击偶发失败；V05-C 的测试暂时挡住快照读取来避开，产品未修；修复要另立核心档卡 |
| TD-SW008-106 | 变更单状态机没有作废状态：停在 implementing 的 CHG-381、386、DOCU-018、DOCU-028 无合法办法收口；需新增“废弃”状态（核心档，建议 M3） |
| TD-SW008-107 | V05-C 的已知限制：窗口离屏、PLC 只做静态检查、执行器超时 300 秒、联验只覆盖两个小目标 |

5. 我在隔离演练树上用本卡的专用检查器完整跑了一遍（非受治理执行，不能复用为正式门禁）：基线、安装、候选三步原始退出码均 0；G1–G9 全部 PASS；22 项内存负向对照都改变了目标输入并被指定断言拒绝；共用判卷器退出 0；`gate_verdict` SHA-256 `95549b32b12cb33dabab6a8f26f9cb9a93a5de14051fccf03ea9327500d7a0d5`，`DONE` SHA-256 `bf0b31b362a625fad4389dc56c9bdd21a24eaa0ee3a08a0172805732887b9b6e`；证据目录 `.auto-pm/reports/m2-td7/gates_rehearsal/`。
6. 不在本卡范围：处置任何债务、失败记录（CHG-381、386、018、CHG-DOCU-2026-028 及其 Work、Run、Decision 等；方案 A 对两个租约过期 Run 的处置由另一张卡执行并已收口，不在本卡）；任何产品、测试、模板、WBS 改动。

## 2. 单一目标与完成定义

让台账与已验收的卡一致：改七行（至多三列）、追加五行新行；只修改一个文件，产品、测试、模板均零改动。

## 3. 实施前预检

1. 核对卡字节与已向用户报告的 SHA 一致、基线、唯一 owned path 及最终字节。没有这些，不创建 CHG/Decision/Work/Run。启动脚本有只读的 `--check-only`，预检只用它。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空；预检仅读，不代表获批。
3. 核对前置 CHG-SCPT-2026-396 completed；核对历史失败记录仍在原状态且本卡不触碰。
4. 新候选 HEAD 等于基线且 clean、index 为空、基线台账 SHA 一致；工具、配置、负向计划及原始证据引用均匹配冻结指纹。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `04_监控/02_整改项/活动技术债台账.md` | 存在 | 改 086、089、091、094、095、098、102 七行（至多三列）；在 §2.2 末尾、§3 之前插入新行；其余原字节不变 |

出现第二条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-td7/`、本卡文件、演练工作树）不是额外产品 owned paths，不进本卡产品提交。

## 5. 字节合同

唯一最终文件 SHA-256：`985636f4d33c4c48caa7f34b0a6a2f8db4d9a37d9aa807b56e2cc7d742ea25f6`。UTF-8、LF、无 BOM。冻结的最终台账、行更新与新增行保存在 `.auto-pm/reports/m2-td7/`（`proto/`、`updated_rows.md`、`new_rows.md`）；安装器只在明确安装阶段核对基线后写入，判卷器不得调用安装或生成。

1. 除所列更新行与新增行外，全部基线原字节不变；更新行中编号、问题、负责人、优先级、验收条件、后续 WBS 不变，事实证据只追加，关联 CHG 与状态等于 §1.3。
2. 新号从基线最大编号后连续增长，无重复，九列齐全，优先级与状态合法，证据非空且引用文件存在，不记已偿还。
3. 写已偿还的行，其关联 CHG 的变更状态必须为 completed 或 closed（判卷器从受控根读取该变更单）；每个有依据提交的更新，该提交必须出现在追加文字中，且是候选 HEAD 的祖先（git 自己判定）。
4. 追加文字里反引号包围的文件引用必须真实存在：仓库内文件在候选树中存在，`.auto-pm/` 下的证据文件匹配冻结 SHA。
5. 验证只读，负向对照仅修改内存中的输入；每个样本必须改变目标输入并被对应目标断言拒绝。
6. 工具与配置的 manifest 已冻结，SHA-256 为 `dced639e46ec9879488cb20189db1ff69f44e9b4f3324e5287600c0480c89e34`；实际运行必须由外部传入该期望值。共享判卷器 SHA-256 为 `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188`。
7. 门禁前后逐一记录最终文件 SHA，全部相同且等于本卡。无门禁跨 Run 复用。

冻结工具（`.auto-pm/reports/m2-td7/`；运行器与安装器沿用 TD6 已验收代码，仅改名；检查器的辅助函数沿用 TD6，判断部分改为由配置驱动）：

| 工具 | SHA-256 |
|---|---|
| `td7_runner.py` | `26155992285ef85cd74d3721285718d9aa8b2687569ff1928e02472ddb724139` |
| `td7_check.py` | `f5f2387134bef8b49b7e3d2972412377c1d945ecf46cd91069020a95acac6ba1` |
| `install_candidate.py` | `030a468655f1a2a390eff611c285850f64e17c7c55884e20aa59b51e506395a8` |
| `prepare_td7.py` | `7e9e9e0ed2aa4dae204ed2d99efb4af0c7f4cc6f6e9c68ef8d9a6d1eed9885cf` |
| `td7_config.json` | `2cd2b2e98c6198b6ecaae5458bd8dc68a2bcbad331fda4e7769d3aff65af1ec9` |
| `updated_rows.md` | `feedeb4e2138c66ef925e902e1c09422fdd5f349eaf2deb58af001b8edbdda7c` |
| `new_rows.md` | `45c0327bf898856f828e7ce51679e7c3cac00bda183745146d2553f3a81a6c09` |
| `base_ledger.md` | `791aa8ef260e9b366cce0880e2426954e1a40eb13a48bca7cf0a0dda637cadea` |

## 6. 门禁矩阵

顺序：基线测量 → 显式安装 → 最终候选测量和判卷。任一非零或环境异常立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份、工作树与初始 hook | HEAD 为基线、clean、index 空，台账为原字节；真实 hook 指纹非空 |
| G2 | 基线文档检查 | 根入口 `main.py doc check` 显式传控制根与候选根，原始 exit 0 |
| G3 | 安装前治理台账 | 根入口 `main.py ledger reconcile SW-2026-008`，无 fix，exit 0 且 0/0/0 |
| G4 | 最终候选文档检查 | 同根入口，原始 exit 0；受检前后字节均等于冻结值 |
| G5 | 安装后治理台账 | 同只读对账，原始 exit 0 且 0/0/0 |
| G6 | 台账语义、旧字节、关联 CHG、依据提交、引用 | §5 全部成立 |
| G7 | 真实 hook 保全 | 运行前后全部真实 hook 字节相同 |
| G8 | 轻量负向对照（22 项） | modify_other_row、delete_row、revert_one_update、change_priority、change_acceptance、replace_evidence、illegal_status、overclaim_repaid、repaid_with_open_chg、chg_unbound、basis_missing、not_ancestor、dead_reference、out_of_scope、tampered_bytes、crlf、new_row_missing、new_row_duplicate_id、new_row_invalid_priority、new_row_repaid、new_row_empty_evidence、new_row_dead_reference，各由对应断言拒绝 |
| G9 | 最终范围、HEAD、index、diff | 实测变更仅唯一 owned 文件、HEAD 仍基线、index 空、无未跟踪残留；完整 diff 及前后 SHA 绑定 |

判卷另由冻结的 `m2-tools/verdict_check.py` 核对完整 G1–G9、card/base/run、报告映射及文件 SHA；空集合、缺报告、错误身份均拒绝。测量与安装分离，任何 STOP 禁止再次运行该证据目录。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-08 与 2026-10-09 的有条件预授权（原话 `.auto-pm/reports/PREAUTH_M2_20261008.txt`）：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径；任一不满足则不开工 |
| 最终验收 | 已委托：G1–G9 全部通过且提交与 Checkpoint 一致时由 claude-sonnet-5-5 代为验收并收口 CHG；用户可复核并推翻 |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与登记摘要。
2. 创建独立 SW-2026-008 DOCU/OPT 变更单、匹配 Decision（`DEC-<当天>-TD7DOCS0`）、Work `WORK-SW008-M2-TD7-001`、Run `RUN-SW008-M2-TD7-001`（租约不超过 3600 秒）；实际创建前验证未被占用，不复用幂等键或旧 token。
3. 从代码基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-td7`，分支 `codex/m2-td7-docs`。
4. 安装最终字节并完整重跑门禁（`td7_gates_all.sh`）；先创建当前字节 Checkpoint，再正常 Hook 提交唯一 owned 文件，绝不 no-verify；核对提交父、范围及 blob 与 Checkpoint 完全一致。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；条件满足后代为验收并收口 CHG。

## 9. 硬停止

基线、工具/卡/Decision 指纹、owner/scope、lease 或 hook 漂移；新增范围；任何门禁失败；负向目标未命中；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要变更所列行以外的既有台账内容、CHG、WBS、产品、模板、Obsidian 或安全设置：均停止，保留现场，不靠重跑、改字节或放宽判据变绿；不处置任何历史失败对象。按止损规则：同一问题最多修 2 轮，每卡总时长上限 6 小时，连续 2 张卡失败整体停下。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结工具、台账与行更新、新增行；演练原始门禁（非治理）；正式独立门禁、CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；代验收记录；GPT 对提交的独立审计。

## 11. 限制与后续

本卡只登记与同步，不修任何缺陷、不处置失败记录。检查保证结构、引用和冻结字节，事实判断由来源审阅承担。无合并、推送、部署或 release 切换授权。
