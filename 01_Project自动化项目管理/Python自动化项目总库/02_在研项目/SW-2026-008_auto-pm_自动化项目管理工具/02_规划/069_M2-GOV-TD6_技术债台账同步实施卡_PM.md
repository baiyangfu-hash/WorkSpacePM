# M2-GOV-TD6｜技术债台账同步实施卡

> 卡片编号：`CARD-SW008-M2-TD6`
> 版本：`V1.0`（2026-10-08；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / NOT_AUTHORIZED`（批准依据见 §7）
> 档次：文档档；只登记与同步，不处理债务
> 隔离基线：`592211eed674ec8e811c02370d8423744585aaf9`（V06B，CHG-SCPT-2026-391 completed）
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 治理任务基线：WBS V3.0.22，提交 `0b56b2f4de2b35effea7e100ab2c56bc1cec0bc7`；WBS SHA-256 `41469091baa836807b5d8913e5a0678a3e38f043253b008f72cd00e1bab522d6`
> 对应 WBS：TD6 无独立任务行；让台账跟上两次独立审计与已验收的卡，不在本卡修改 WBS
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033，以及基线提交中的《M2 门禁分档与单卡规模规则》（文档档：不需要 pytest 全量）。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-08）

1. 台账规则 3：新发现的问题先登记债务编号再决定修复；规则 2：关联 CHG 状态改变时同步台账。两次独立审计（Astra 里程碑审计 F-01、F-02；GPT R4 对 V06 与 V06B 的审计 R4-01～R4-09）的发现，以及 F01-a、V06B 的验收事实，目前不在台账里或已过时。用户已批准后续顺序（TD6 → V06C → V06D → F01-1 → F02 → …），这些卡都以本卡的登记为前置。
2. 基线台账原字节 SHA-256 为 `661e0a1350ffaa2e8a35ea96115c21dde1decd75033d88b7fdf6969b8eec19a8`（TD5 提交后的字节，编号最高 097）。
3. **追加五行**（TD-SW008-098～102）：098 关闭后遗漏的写入口 F-01（`confirmStart` 无关闭检查，我已对照源码核实，P2）；099 判卷器例外合同过松（R4-01、R4-02、R4-08，P1，缺口在外部原件里就有）；100 V06 钩子测试证明缺口（R4-03、R4-04，P2）；101 V06 证据保全不足（R4-06、R4-07，P2）；102 TD-SW008-091 证明强度低于措辞（R4-05，P2）。F-02 不另立根因，并入 TD-SW008-094（审计也如此建议）。
4. **改四条既有债务行**，每行只许改三列：关联 CHG、状态、事实证据（末尾追加；旧内容是新内容的前缀）；编号、问题、负责人、优先级、验收条件、后续 WBS 六列一字不改：
   - TD-SW008-078：F01-a 已由卡 057 处置并验收（提交 `01ad3923`，CHG-SCPT-2026-383 completed）。**状态由“待执行”改“活动”，不写已偿还**——已进入 HEAD 的删除认不出、部分分支缺直接变异证据、合法移动与退役入口属 TD-SW008-079。关联 CHG 由“待立”改为 CHG-SCPT-2026-383。
   - TD-SW008-091：追加更正说明：原处置说明“Mission、Work、Run 与事件不变”强于证明（测试的写入比较只比较行数，窗口销毁分支没有真正销毁 QML 窗口）；修复本身仍有证据，**状态保持已偿还**，补证另见 102。
   - TD-SW008-094：追加 F-02 关联；状态、关联 CHG 不变。
   - TD-SW008-096：追加 V06B 进展（判卷器已入库，判卷语义与原件逐分支等价；分类器、封存工具、正式入口仍在外部）；关联 CHG 由“待立”改为 CHG-SCPT-2026-391；状态保持待执行。
5. 我在隔离演练树上用本卡的专用检查器完整跑了一遍（2026-10-08，非受治理执行，不能复用为正式门禁）：基线、安装、候选三步原始退出码均 0；G1–G9 全部 PASS；22 项内存负向对照都改变了目标输入并被指定断言拒绝；共用判卷器退出 0；`gate_verdict` SHA-256 `0b60afc918ed64652f021b47daac7162f4ece5f714af77a428a883e4bab8addb`，`DONE` SHA-256 `385b0b29e6abea1c345bdcb15cb481e37878f205a522d3c4fcbed0eddfbbc113`；证据目录 `.auto-pm/reports/m2-td6/gates_rehearsal/`。
6. 对账原始输出保留 CHG-SCPT-2026-161–164 的既有结构告警；命令退出 0 且对账 0/0/0。该结果只证明台账对账门通过，不宣称全项目历史变更单无规范债。
7. 不在本卡范围：处置任何债务、失败记录（CHG-381、386、018 等）；改 TD-SW008-086、089；任何产品、测试、模板、WBS 改动。

## 2. 单一目标与完成定义

让台账与两次审计和已验收的卡一致：追加五行、改四行的三列；只修改一个文件，产品、测试、模板均零改动。

| 编号 | 动作 | 新状态 | 关联 CHG | 依据 |
|---|---|---|---|---|
| TD-SW008-078 | 追加进展；状态与关联 CHG 更新 | 活动 | CHG-SCPT-2026-383 | `01ad3923` |
| TD-SW008-091 | 追加更正说明 | 已偿还（不变） | 不变 | `4d0b33ac`、GPT R4-05 |
| TD-SW008-094 | 追加 F-02 关联 | 待复核（不变） | 不变 | Astra F-02 |
| TD-SW008-096 | 追加 V06B 进展；关联 CHG 更新 | 待执行（不变） | CHG-SCPT-2026-391 | `592211ee` |
| TD-SW008-098 | 新增：关闭后遗漏的写入口 | 待执行 | 待立 | Astra F-01 |
| TD-SW008-099 | 新增：判卷器例外合同过松 | 待执行（P1） | 待立 | GPT R4-01/02/08 |
| TD-SW008-100 | 新增：V06 钩子测试证明缺口 | 待执行 | 待立 | GPT R4-03/04 |
| TD-SW008-101 | 新增：V06 证据保全不足 | 待执行 | 待立 | GPT R4-06/07 |
| TD-SW008-102 | 新增：TD-SW008-091 证明强度不足 | 待复核 | 待立 | GPT R4-05 |

## 3. 实施前预检

1. 核对卡字节与已向用户报告的 SHA 一致、基线、WBS、唯一 owned path 及最终字节。没有这些，不创建 CHG/Decision/Work/Run。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空；预检仅读，不代表获批。
3. 核对前置 CHG-SCPT-2026-391 completed；核对历史失败记录仍在原状态且本卡不触碰。
4. 正式执行显式选择本卡新 Work/Run，不借用任何旧授权；新候选 HEAD 等于基线且 clean、index 为空、基线台账 SHA 一致；工具、配置、负向计划及原始证据引用均匹配冻结指纹。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `04_监控/02_整改项/活动技术债台账.md` | 存在 | 改 078、091、094、096 四行（三列）；在 §2.2 末尾、§3 之前插入 098–102；其余原字节不变 |

出现第二条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-td6/`、本卡文件、演练工作树）不是额外产品 owned paths，不进本卡产品提交。

## 5. 字节合同

唯一最终文件 SHA-256：`791aa8ef260e9b366cce0880e2426954e1a40eb13a48bca7cf0a0dda637cadea`。UTF-8、LF、无 BOM。冻结的最终台账、四行更新与五行新增保存在 `.auto-pm/reports/m2-td6/`（`proto/`、`updated_rows.md`、`new_rows.md`）；安装器只在明确安装阶段核对基线后写入，判卷器不得调用安装或生成。

1. 除四行与新增五行外，全部基线原字节不变；四行中编号、问题、负责人、优先级、验收条件、后续 WBS 不变，事实证据只追加，关联 CHG 与状态等于 §2。
2. 新号从基线最大编号后连续增长，无重复，九列齐全，优先级与状态合法，证据非空且引用文件存在，不记已偿还。
3. 写已偿还的行，其关联 CHG 的变更状态必须为 completed 或 closed（判卷器从受控根读取该变更单）；每个有依据提交的更新，该提交必须出现在追加文字中，且是候选 HEAD 的祖先（git 自己判定）。
4. 追加文字里反引号包围的文件引用必须真实存在：仓库内文件在候选树中存在，`.auto-pm/` 下的证据文件匹配冻结 SHA。
5. 验证只读，负向对照仅修改内存中的输入；每个样本必须改变目标输入并被对应目标断言拒绝。
6. 工具与配置的 manifest 已冻结，SHA-256 为 `7ccb0aad4587994d37ab99b8062aa9af14e6ae7d77e764ee19111fb2a2cc6ec3`；实际运行必须由外部传入该期望值。共享判卷器 SHA-256 为 `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188`。
7. 门禁前后逐一记录最终文件 SHA，全部相同且等于本卡。无门禁跨 Run 复用。

冻结工具（`.auto-pm/reports/m2-td6/`；运行器与安装器沿用 TD3R、TD4 已演练代码，仅改名；检查器的辅助函数沿用 TD3R，判断部分为本卡新写，因为本卡同时需要“只改指定行的指定列”与“追加新行”两种检查）：

| 工具 | SHA-256 |
|---|---|
| `td6_runner.py` | `ee64c973192c1d35cd5652c579bbcffe0f848d6eccde1784d00e6609c65cfe01` |
| `td6_check.py` | `02a213b3dedf375fc98040cdc117aa40cf3177c2da6aaf33f9885c1d06a6a3e1` |
| `install_candidate.py` | `9ed9f7774d4268cd1b08f2a32c155da0c2ce19909f1e2ea69d664a196645d8b5` |
| `prepare_td6.py` | `892a824a493c8d3878c848c29ec232e6032610d8ec4f8902b66bb4092140eb62` |
| `td6_config.json` | `1723c50bd1df0495e1bffab7fea1c3a74e0bf3d5e19e78c04ace8aea399eef59` |
| `updated_rows.md` | `d8f7b87ac374faacbea05c0d5274babc7931f5aad84081c5ed7cbbfd2dbce76f` |
| `new_rows.md` | `5bff13b3a8715eb11e7e8d14575ae77de548eb23a40f28970e04c4f5c038d8fb` |
| `base_ledger.md` | `661e0a1350ffaa2e8a35ea96115c21dde1decd75033d88b7fdf6969b8eec19a8` |

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

判卷另由冻结的 `m2-tools/verdict_check.py` 核对完整 G1–G9、card/base/run、报告映射及文件 SHA；空集合、缺报告、错误身份均拒绝。越界负向是变更路径清单输入的内存测试；测量器输出 `is_governed_evidence=false`，正式外层须由 Checkpoint 绑定测量。测量与安装分离，任何 STOP 禁止再次运行该证据目录。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | PENDING；须卡的最终 SHA 在聊天报出之后，用户明确回复批准 |
| 最终验收 | PENDING；不在委托范围内，须已提交、门禁与 Checkpoint 核验后，由用户明确验收；CHG 保持 implementing 直到用户确认 |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与登记摘要，等待明确批准。
2. 批准后创建独立 SW-2026-008 DOCU/OPT 变更单、匹配 Decision（`DEC-<当天>-TD6DOCS0`）、Work `WORK-SW008-M2-TD6-001`、Run `RUN-SW008-M2-TD6-001`（租约不超过 3600 秒）；实际创建前验证未被占用，不复用幂等键或旧 token。
3. 从代码基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-td6`，分支 `codex/m2-td6-docs`。
4. 安装最终字节并完整重跑门禁（`td6_gates_all.sh`）；先创建当前字节 Checkpoint，再正常 Hook 提交唯一 owned 文件，绝不 no-verify；核对提交父、范围及 blob 与 Checkpoint 完全一致。
5. 依法推进 Run/Work 技术终态，对账 0/0/0。报告已提交、等待用户验收；用户验收前不收口 CHG。

## 9. 硬停止

基线、工具/卡/Decision 指纹、owner/scope、lease 或 hook 漂移；新增范围；任何门禁失败；负向目标未命中；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要变更四行以外的既有台账内容、CHG、WBS、产品、模板、Obsidian 或安全设置：均停止，保留现场，不靠重跑、改字节或放宽判据变绿；不处置任何历史失败对象。按止损规则：同一问题最多修 2 轮，每卡总时长上限 6 小时，连续 2 张卡失败整体停下。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结工具、台账与四行更新、五行新增；演练原始门禁（非治理）；批准后独立正式门禁、CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；用户验收另行记录；GPT 对提交的独立审计。

## 11. 限制与后续

本卡只登记与同步，不修任何缺陷、不迁移判卷器、不处置失败记录。检查保证结构、引用和冻结字节，事实判断由来源审阅承担；098 的触及面限于保留桥对象或嵌入调用，是静态审计结论，未动态复现。后续按路线图：V06C（099、101）、V06D（100、101）、F01-1（098、102）、F02（094 的 F-02 部分）。无合并、推送、部署或 release 切换授权。
