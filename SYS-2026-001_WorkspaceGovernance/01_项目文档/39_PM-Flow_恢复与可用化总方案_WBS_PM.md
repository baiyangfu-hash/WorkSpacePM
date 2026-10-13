# PM-Flow 恢复与可用化总方案

> 文档版本：V3.0.34；修订日期：2026-10-13；状态：M0、M1、M2 已验收（M2 里程碑由用户于 2026-10-11 宣布验收，见 §4.7.13）；M3 已启动，第一日批次（卡 099～103）已完成（V3.0.28），第二批（卡 105～110：台账翻转、CI 基线刷新与推送、D01 指引修正、TD-SW008-042、Q03、文档草案采纳、台账与 WBS 回写）已完成（V3.0.29，见 §4.7.14）；其后 CI 基线再刷新（卡 111）与第三批新增任务行（`M3-RACE`、`M3-CF`、`M3-FIG` 及排队的仓库治理项）登记于 §4.7.15（V3.0.30）；2026-10-11 傍晚的仓库卫生清理（工作树 228 → 63、分支 206 → 54）与 `M3-ROOT`、`M3-HYG` 两个任务行登记于 §4.7.16（V3.0.31）；同日的核心档卡 115（`M3-RACE`）与卡 116（`M2-B1`）、控制根对齐（`M3-ROOT`）的执行与卫生清理的收尾登记于 §4.7.17（V3.0.32）；当晚的卡 119（变更单补入库）、卡 120（V07）、卡 121（台账回写）与卡 122（本记录）以及 V08 的勘测发现登记于 §4.7.18（V3.0.33）；2026-10-13 的卡 123～126、PLC 门禁实际依赖 Siemens 语言服务插件的发现与用户的裁决登记于 §4.7.19（V3.0.34）；以下按时间顺序保留 M2 进行期间的状态记录；M2 进行中，U01、U02、U03A、U03B、U04A、U04B、统一集成基线 `M2-BL01`、实施卡工作流 `M2-GOV-IC01` 与规范沉淀 `M2-GOV-U04S01` 均已验收闭环；H11 已 `COMPLETED / ACCEPTED`，治理整改阶段 1～5 已完成（阶段 2～5 的批准与验收为用户授权下的委托执行，记为 `DELEGATED_ACCEPTED`），阶段 6 `M2-GOV-WBS2` 的复查候选 `e07f7662` 已由用户于 2026-09-30 亲自验收并绑定回执（V3.0.18），记为 `COMPLETED / ACCEPTED`；详见 §4.7.3。U05、U06、U07A～U07D、U08 已于 2026-09-30～2026-10-01 逐项验收闭环，新增 V05 前置任务 U09A～U09C（`PLANNED / NOT_AUTHORIZED`）；详见 §4.7.4（V3.0.19）。U09A～U09C 与 QML 生命周期根修 `M2-GOV-QML1` 已于 2026-10-01～2026-10-03 验收闭环，U01～U09 全部完成；详见 §4.7.5（V3.0.20）。V01 已于 2026-10-03 验收闭环（实际 5 路径）；用户同日确认新增 PLC 文档与代码一致性核对任务 V01B～V01D，并定顺序 V01B → V01C → V01D → V02；详见 §4.7.6（V3.0.21）。V01B～V04、第 1 期、TD1、第 1 期审计缺陷修复与 TD2 已于 2026-10-03～2026-10-06 逐项验收闭环；审计结论、F01 与 V05 的拆分、F05 分期与新的执行顺序登记于 §4.7.7（V3.0.22）。F01-a、V05-A/B/B2/B3、V04-T、V06 钩子半与判卷半及其两次补强（V06B～V06D）和台账四张卡（TD3R～TD6）已于 2026-10-07～2026-10-08 逐项验收闭环；三次独立审计的处置、授权记录、新增任务与新顺序、部署意图与 M3 候选登记于 §4.7.8（V3.0.23）。F02、V05-C、TD7、规则修订与分档器已于 2026-10-09 验收闭环，N1a 与 N2-0 已完成并等待用户验收；用户同日决定 M2 基线冻结，V04-R1（整张）、V07、V08、M2-F01B、M2-B1 与文档采纳后移到 M3（承诺保留），M2 的剩余集合为最小 WBS 文档卡、`M2-DEP-INT`、审计包、GPT 审计、技术部署与推送；本修订同时采纳 V3.0.23，登记于 §4.7.9（V3.0.24）。N1a、N2-0 与最小 WBS 卡已由用户验收，`M2-DEP-INT` 已提交并按预授权收口；GPT 最终审计提出的“最终提交没有被治理库 Checkpoint 绑定”（B-01）以 §4.7.10 的最终提交证明处置，状态写回登记于 §4.7.10（V3.0.25）。卡 083 已由用户验收并 completed；开发运行时已技术性部署到 `1.3.3-4b5c630`（卡 084 V1.1，CHG-SCPT-2026-400 completed），M2 隔离候选分支已推送（未合并 main）；该状态写回登记于 §4.7.11（V3.0.26）。发布治理整顿批次（卡 085～094）的状态写回与历史队列 H02～H10 的只读核对登记于 §4.7.12（V3.0.27）。用户宣布 M2 里程碑验收、M3 启动与第一日批次（卡 099～103）登记于 §4.7.13（V3.0.28）。当前裁决以下方机器可检的“当前投影”为准；后续长篇版本记录仅是历史证据，不再参与当前状态判定。
> 项目：SW-2026-008；治理：SYS-2026-001；规划标识：PMF-20260912。
> 修订依据：用户要求“重新修订方案，原子级拆解，最终需求必须达成”。本轮直接修订既有计划；不再设置一个等待批准的“先盘点再规划”项目。
> 本文件给出 4 个产品里程碑、201 个任务 ID 行（V3.0.20 起按逐行机器计数；V3.0.18 以前写作“100 个原子任务”，见 §4.7.5）及 1 条主线；其中 Q01～Q03 是已冻结基线失败的独立收敛队列。任务属于批次内部步骤，不等于逐条重复用户审批。C09 的补强门槛不构成重新派发原业务的许可。

<!-- AUTO_PM:BEGIN wbs-current-projection -->
| Milestone | Status | Evidence | Next |
|---|---|---|---|
| M0 | ACCEPTED | 历史验收链；G10 集成锚点 `d87fd3d`；本轮未重跑但不撤销既有验收 | 保持冻结基线，仅在依赖漂移时复验 |
| M1 | ACCEPTED | 不可变候选 `8b02de55`；`CP-SW008-PMF-G10R1-001`；Run SUCCEEDED/lease RELEASED/Work CLOSED；稳定运行时 `1.3.3-8b02de5` | 从 U01 启动 M2 |
| M2 | ACCEPTED / USER_MILESTONE_ACCEPTED_20261011 / BASELINE_FROZEN_V3.0.24 / V06_ACCEPTED / F011_ACCEPTED / F02_ACCEPTED / V05C_ACCEPTED / TD7_ACCEPTED / RULE_ACCEPTED / TIER_ACCEPTED / N1A_ACCEPTED / N2_0_ACCEPTED / WBS8_ACCEPTED / DEP_INT_COMMITTED_AND_CLOSED / FINAL_AUDIT_B01_ATTESTED / WBS9_ACCEPTED / DEP_TECH_DEPLOYED / ISOLATED_BRANCH_PUSHED / RELEASE_GOVERNANCE_BATCH_COMPLETED / M3_FIRST_DAY_BATCH_099_103_COMPLETED | U04A `d59120c7`；U04B `d200eb9b`、R1 `e05fafa1`；H11A `e648e0b4`、H11C `0b724997`；14 条目标 Work 均 `CANCELLED`，5 条旧终态 lease 已围栏，历史 Run/Checkpoint/旧事件保留；2026-09-29 采样时事件链 2566 条、0 断裂，SW008 无 BLOCKED Work，Resume 无冲突，台账 0/0/0；**2026-09-30 整改后（2026-09-30T15:35:07-07:00）**：BL02 `7cfe227e`、ADJ `d876cf98`、IC02 `e6529115`、整合 `a808fa8a`，开发运行时 active `1.3.3-a808fa8`/previous `1.3.3-0b72499`；事件链 2651 条、0 断裂，`pm resume` 无冲突，两项目台账 0/0/0；**2026-10-01（2026-10-01T13:44:48-07:00）**：U05 `ace7a959`、U06 `8b7f199a`、U07A `795fe448`、U07B `35379585`、U07C `9a92e9b7`、U07D `460e24f6`、U08 `d40318d0` 均已验收闭环（CHG-SCPT-2026-362～369 completed）；事件链 2778 条、0 断裂，SW008 无未终结 Mission，两项目台账 0/0/0；开发运行时仍为 `1.3.3-a808fa8`，不含 U05～U08 代码；**2026-10-03（2026-10-03T05:59:44-07:00）**：U09A `eebdeecb`、U09B `cec3afa7`、QML 根修 `6eead5e4`/`d95f45d2`、U09C `3c32e8ad` 均已验收闭环（CHG-SCPT-2026-370～373 completed），事件链 2929 条、0 断裂，两项目台账 0/0/0；开发运行时仍为 `1.3.3-a808fa8`，不含 U05～U09C 代码；**2026-10-03（2026-10-03T14:54:46-07:00）**：V01 `37a4faff`（父 `3c32e8ad`）已验收闭环（CHG-SCPT-2026-374 completed），用户确认新增 V01B～V01D（需求说明 043），事件链 2973 条、0 断裂，两项目台账 0/0/0；开发运行时仍为 `1.3.3-a808fa8`，不含 U05～V01 代码；**2026-10-06（2026-10-06T15:20:40-07:00）**：V01B `d890be25`、V01C `1e1ef760`、V01D `fb94afa9`、V02 `cf6f6f33`、TD1 `b6668dcf`、V03 `edeeead9`、第 1 期 `4e165cf4`、V04 `a6447be6`、第 1 期审计缺陷修复 `948884db`、TD2 `1956dd9a` 均已验收闭环（对应 CHG 全部 completed），代码线唯一尖端 `1956dd9a`，事件链 3164 条、0 断裂，两项目台账 0/0/0；开发运行时仍为 `1.3.3-a808fa8`，不含 U05～1956dd9a 代码；**2026-10-08（2026-10-08T16:28:17-07:00）**：F01-a `01ad3923`、V05-A `5a2f9c48`、V05-B `5686bd9f`、V05-B2 `aeedf92f`、TD3R `769f145d`、V04-T `715713bb`、V06 钩子半 `c3c20e07`、V05-B3 `4d0b33ac`、TD4 `23e6ed64`、TD5 `6a84a186`、V06B `592211ee`、TD6 `06f4ae4d`、V06C `83369f67`、V06D `3bc740a4`、F01-1 `763395e4` 均已验收闭环（对应 CHG 全部 completed），代码线唯一尖端 `763395e4`，事件链 3421 条、0 断裂，两项目台账 0/0/0；开发运行时仍为 `1.3.3-a808fa8`，不含 U05～`763395e4` 代码；**2026-10-09（2026-10-09T11:10:39-07:00）**：F02 `98c2110d`、V05-C `6e17f086`、TD7 `c8d49c29`、规则修订 `a0ac852b`、分档器 `370e0297` 均已验收闭环（对应 CHG 全部 completed），N1a `388b22c4`（CHG-DOCU-2026-031）已提交、N2-0（CHG-DOCU-2026-025，只读勘测，无提交）已出报告，二者均等待用户验收；代码线唯一尖端 `388b22c43a334faf1e29d9bb0038150a403b17e3`，两项目台账 0/0/0；开发运行时仍为 `1.3.3-a808fa8`，**不含** M2 代码，且与 M2 代码线从 `7cfe227e` 分叉（缺 ADJ 与 IC02 两个功能，见 §4.7.9）；**2026-10-09（2026-10-09T18:32:15-07:00）**：N1a（`388b22c4`，CHG-DOCU-2026-031）、N2-0（CHG-DOCU-2026-025）、最小 WBS 卡（`f06c5aac`，CHG-DOCU-2026-032）已由用户验收并 completed；`M2-DEP-INT` 合并提交 `1d0be4af`（父 `f06c5aac` 与发布源 `a808fa8a`，树 `644c5732`，CHG-SCPT-2026-399 completed，九项门禁全过）；GPT 最终审计（`.auto-pm/reports/m2-relay/m2-final-audit-20261009/gpt-output/AUDIT_REPORT_FINAL.md`，SHA-256 前 8 位 `66cc5dcd`）的阻断项 B-01 由 §4.7.10 的最终提交证明处置，代码线唯一尖端 `1d0be4af`，开发运行时仍为 `1.3.3-a808fa8`，尚未部署；**2026-10-09（2026-10-09T20:57:03-07:00）**：卡 083（`4b5c6307`，CHG-DOCU-2026-033）已由用户验收并 completed；技术性部署（卡 084 V1.1，CHG-SCPT-2026-400 completed）：开发运行时 active `1.3.3-4b5c630`（`source_commit` 为 `4b5c6307`），previous `1.3.3-a808fa8`；第一轮（Run `RUN-SW008-M2-DEPTECH-001` FAILED、Work `WORK-SW008-M2-DEPTECH-001` CANCELLED）因切换后核验判据过严自动回退，第二轮（Run `RUN-SW008-M2-DEPTECH-002` SUCCEEDED、Work CLOSED）成功，核验结果见 §4.7.11；M2 隔离候选分支 `codex/m2-gov-wbs9-attest`（`4b5c6307`）已于 2026-10-09T20:22:07-07:00 一次性推送到 origin（新分支，不含 main，未强推），未合并 main；**2026-10-10（2026-10-10T09:23:59-07:00）**：发布治理整顿批次（卡 085～094，详见 §4.7.12）：卡 085、卡 086、卡 087、卡 088 的变更单已由用户验收并 completed；卡 089、卡 090、卡 091、卡 092、卡 094、卡 093 技术完成（Run SUCCEEDED、Work CLOSED），变更单停在 implementing 等用户阅读后验收；15 个本地带注解 tag `release-src/<release-id>` 已建立且**未推送**；代码线唯一尖端 `7506af72`（分支 `codex/m2-trk-check`，未推送、未合并 main）；开发运行时仍为 `1.3.3-4b5c630`，批次不含运行时部署；历史队列 H04～H06、H08、H09 仍未处置（需用户另行批准）；**2026-10-11**：用户在对话中宣布 M2 里程碑验收；M3 第一日批次（卡 099～103，详见 §4.7.13）：卡 099～103 的变更单均 completed，技术线性历史 `0d22fdd0` → `fea74b33` → `bf19b6bd` → `853fc651` → `9f952044` → `dbf7d031`（本地分支 `codex/m2-td11-sync`，未推送、未合并 main）；此前 M2 的验收待办（卡 089～094 的变更单）已全部 completed | M2 已授权的全部工作项已完成：技术性部署与推送均已执行，不再有待执行的 M2 承诺；M2 里程碑已由用户于 2026-10-11 宣布验收；此后进入 M3（延期承诺表见 §4.7.9）；合并 main 等到 M3 的 D03；历史遗留的 5 个未终结 Work（`MULTIPLE_ACTIVE_WORKS`）按用户要求原样保留，M3 再议；D07 正式稳定交付仍是独立边界 |
| M3 | IN_PROGRESS（2026-10-11 起） | WBS §4.9；自 M2 后移：V04-R1、V07（部分完成，“从基准提取”保留待办）、V08（测试部分完成，收紧并入 `M3-PLUGIN`）、M2-F01B（延期承诺表见 §4.7.9）；`M2-B1` 已完成（卡 116）；2026-10-11：卡 099～111（§4.7.13～§4.7.15）；2026-10-12：卡 113～122、控制根对齐、卫生清理与夜间五张卡（§4.7.16～§4.7.18）；2026-10-13：卡 123～126（§4.7.19）；已推送线尖端 `dcfca387`（CI 第 9 次 success），其上本地未推送：卡 124 `b5d3e552` → 卡 125 `d6d382ff` → 卡 126（本记录） | `M3-PLUGIN`（把插件命令行接入驾驶舱门禁，产品档，卡 127，今天）→ 推送并读 CI → 小修卡（TD-SW008-130、131 与 AGENTS 措辞）→ V04-R1 → D02；`M3-CF`（需用户给报错样本）、`M3-FIG`；`M3-HYG` 的剩余部分；TD-SW008-132（DJ-2026-005，有意保留作驾驶舱实测对象）在 WBS 完工后使用；D03 合并 main 与 D07 切换仍是用户另行授权的独立边界；M2-F01B 的范围、TD-SW008-123 的入库口径待用户裁决 |

| Blocker | Target | Blocking | Record | Disposition |
|---|---|---|---|---|
| P2 五文件真实执行证据未闭环 | P2 | YES | TD-SW008-008；INC-SW008-C09P2-318-20260927；CHG-SCPT-2026-323 | 仅阻断 P2 自身，独立偿还 |
| P2 历史异常与旧 Checkpoint 局限 | M1,U01 | NO | TD-SW008-008；WBS V2.6.1～V2.6.3 | 历史原样保留，不反向撤销当前 M1 验收，不阻断 U01 |
| main 尚未集成 M1 候选 | M2 | NO | 分支 `codex/g10-r1-lifecycle`；提交 `8b02de55` | 合并、推送、部署继续作为独立边界 |
| U01 与 runtime-fix 尚无统一基线 | M2 后续执行 | NO / RESOLVED | `M2-BL01`；候选 `4851fce4`；`CP-SW008-M2-BL01-001`；Run SUCCEEDED/lease RELEASED；Work CLOSED；CHG-HMI-2026-002 completed | 统一基线固定；后续任务只能从该不可变提交或经独立验收的后继开始 |
| M2-GOV-IC01 首次执行提交合同冲突 | M2-GOV-IC01 | NO / RESOLVED | 首次失败历史保留；纠正链 `RUN-SW008-M2-GOV-IC01-002` SUCCEEDED；`CP-SW008-M2-GOV-IC01-003`；commit `b7bb9357`；CHG-SCPT-2026-338 completed | 八个产品路径与两个提交证据路径已分层建模并由正常 Git hook 验收；后续任务复用该合同 |
| 历史 `BLOCKED` Work 仍进入活动视图 | 默认 Resume / 历史治理 | NO / RESOLVED_BY_H11 | H11A/B/C 已使 14 条目标 Work 全部前向 `CANCELLED`；NOSKIP Run 已合法结算；5 条旧终态 lease 已围栏；QG 两个 SUCCEEDED Checkpoint 与全部失败史原样保留 | 不重开或二次验收 H11；后续仅修复裁决 Decision 的 Git 绑定与正式 CLI 合同，历史对象不再作为 U05 活动阻断 |
<!-- AUTO_PM:END wbs-current-projection -->

> V3.0.16 将 H11 的已执行终态写回当前投影：14 条目标 Work 均 `CANCELLED`，5 条旧终态 lease 已围栏，事件链与历史 Checkpoint 保持可审计；明确 `fubai` 与 `baiyang` 是同一用户的等权署名，并区分 Claude 编制记录与用户亲手执行的收口动作。新增 BL02、ADJ、IC02、DEP1、WBS2 五个治理原子任务，冻结 U/R/发布三线血统及 U05 的统一基线前置；本修订只改 WBS 单文件，不执行后续整改、部署、合并或推送。
> V3.0.15 记录 U04 完整验收：U04B 十路径产品候选正常 Hook 提交 `d200eb9b`，U04B-R1 七路径合同提交 `e05fafa1`；两个当前字节 Checkpoint、终态租约恢复事件、Run/Work/Mission/CHG 与台账证据均成立。H11 只读复核把 14 条历史 BLOCKED Work 划分为 11 条常规处置、1 条 NOSKIP 非终态 Run 结算、2 个 Work 下 5 条旧终态未释放 lease 的兼容裁决；本修订仅更新 WBS 与建立实施卡，不创建 H11 CHG/Decision/Work/Run，不修改 canonical 数据库。
> V3.0.13 依据 U03B 当前字节与 canonical 事件链只读预检修订 U04：现有三路径范围无法同时满足后台持续刷新、Boss 视图接线与结构化失败定位；现有哈希事件可证明启动/投影/状态迁移，但 FAILED 迁移缺少可安全展示的结构化失败步骤。U04 因而拆分为 U04A“不可变执行阶段与失败归因事件合同”和 U04B“QML 真实活动时间线与持续刷新”，以 `b8010027` 为唯一新增基线。另登记 H11 处置 14 条历史 BLOCKED Work，并登记 `M2-GOV-U04S01` 在 U04 验收后、U05 前沉淀跨项目规范。本修订只规划，不创建 CHG/Decision/Work/Run，不修改源码、数据库或 release。
> V3.0.12 记录 U03B 独立验收：五路径候选正常 Hook 提交 `b8010027`；`CP-SW008-M2-U03B-001` 绑定当前洁净字节，11 项定向测试、Ruff、strict Mypy 与 diff-check 全部 Exit 0，Run 002 `SUCCEEDED`、Work/Mission `CLOSED`、CHG-341 completed。首次 Run 因行政命令缺失幂等参数停在 READY、无 Checkpoint/子进程，已通过独立恢复链前向撤销；历史保留且不参与通过判定。下一产品任务为 U04。
> V3.0.11 记录 U03A 独立验收：六路径候选正常 Hook 提交 `316ab46b`；`CP-SW008-M2-U03A-002` 绑定当前洁净字节，35 项定向测试、Ruff、Mypy 全部 Exit 0，Run `SUCCEEDED`、Work `CLOSED`、CHG-340 completed。首次过早建立的 Run 已通过独立恢复 Decision/Work/Run 前向撤销，历史原样保留，不参与通过判定；下一产品任务为 U03B。
> V3.0.10 依据 U03 当前调用链只读复核拆分 U03A/U03B：旧 `confirm_start` 只推进 Work 状态，不能证明真实 Run/session；Cockpit 旧投影会把状态变化误显示为“执行中”，并可能被无关历史 BLOCKED Run 污染。U03A 先恢复持久化批准链并接通 E08 真实启动证据，U03B 再完成 QML 异步一次确认；U04 保留持续进度/失败时间线职责。固定模型名不再作为未启动任务的执行合同，改由风险等级与独立复核级别路由，实际模型写入 Run。本修订不创建 U03A CHG/Decision/Work/Run，不修改源码。
> V3.0.5 记录 `M2-GOV-IC01` 首次执行的真实结果：八个产品文件已通过 26 项定向测试、Ruff、strict Mypy 与 diff-check，并形成当前字节 Checkpoint；本地提交因稳定 commit-msg 合同要求 CHG 与项目台账同一暂存快照而被正确拒绝。旧 Run/Work/Mission 如实保持 FAILED/BLOCKED，未使用 `--no-verify`。后续唯一纠正链将产品路径与两个提交治理证据路径分层建模；不得增加第十一路径或重写历史。
> V3.0.6 完成 `M2-GOV-IC01` 有界纠正：实施卡合同显式区分八个产品路径与两个提交证据路径；33 项定向测试、Ruff、strict Mypy、diff-check 全部 Exit 0；`CP-SW008-M2-GOV-IC01-003` 绑定当前十路径，正常 Git hook 生成不可变提交 `b7bb9357`；Run/Work/Mission 与 CHG-338 全部合法闭环。首次失败链及 `CP-...-001/002` 原样保留为历史，不参与当前通过判定。
> V3.0.3 新增并启动原子任务 `M2-BL01`：从 `main@0d7071b7` 的运行身份修复基线机械引入 U01 提交 `d88eedd5` 的精确两文件，形成 M2 后续任务唯一集成基线。用户批准仅覆盖本卡；不授权合并、推送、部署或 release 切换。
> V3.0.2 记录 Batch C 的准入裁决并新增 M2 原子任务 `M2-GOV-IC01`。该任务仅建立实施卡一等合同与自动化工作流，当前为 `PLANNED / NOT_AUTHORIZED / BLOCKED_BY_BASELINE`；本修订不执行源码、不创建治理运行链，也不授权合并、推送、部署或 release 切换。
> V3.0.1 仅记录 U01 的独立验收：五状态演示原型在隔离候选 `d88eedd5` 固化，当前字节的 Checkpoint、Run、Work 与 CHG 闭环证据已齐备；M2 因而进入 `IN_PROGRESS`。本修订不启动 U02，不改变 P2 历史或其独立技术债处置，也不触及合并、推送、部署或 release 切换。
> V3.0.0 建立“当前投影 / 历史证据”分层：WBS 顶部只表达当前里程碑、阻断关系和下一步；CHG/台账保存变更史，Continuity 保存 Work/Run/Checkpoint/lease，事故与技术债使用各自登记。机器门禁候选 `aa72432f`（CHG-DOCU-2026-013、CP-SW008-WBSPROJ-002）拒绝用历史事故阻断已验收里程碑，并要求每个阻断项具有正式记录与处置。
> V2.5.0 的授权仅涵盖 WBS 修订；既有 216 的历史实施、验收、隔离提交记录保留。当前获准核验 V04-R0/FIX/FENCE、失败 Recovery 和旧 `app.db` 处置证据，并同步 WBS 事实；C09 恢复写入、Hook 安装、合并、发布等均须各自有效范围和阶段门禁，不能从文档修订或旧 216 授权外推。
> 沿用原文件已经生成的 PM-027 九节结构，直接修订正文。V1.0.0 留存在 archive/PMF-20260912，退出当前派工入口。
> V2.1.0 依据实际 G06 启动演练修订：不把一次环境诊断包装成候选工作树补丁；先固定真实执行就绪门、G06 输入合同和候选集成点，再进入源码执行。
> V2.1.1 依据 G10 的真实 Checkpoint 合同修订：不可变提交的非活动候选装配必须发生在 G10 Run 之前；Run 只在最终、洁净的集成 HEAD 上启动，避免把受控组合误报为基线漂移。
> V2.2.0 依据 P01 后的代码合同复核修订：前授权计划草稿与强授权 Mission 分层；禁止用空授权或伪造 CHG/Decision 提前创建 Mission，并把 P 链及下游依赖重排为可执行顺序。
> V2.3.0 依据 P08-R 的实际闭合修订：强授权 Mission 还必须显式、最小化地声明允许派生的子 Work 类型；P08-R 的不可变提交与 Checkpoint 是 P09 的唯一新增前置，P09 不得自行补写或扩大 Mission 授权。
> V2.4.0 依据 P11 首次 CLI 冷启动重放实演修订：P10 的内存 card 重试不能代替进程重启后的 request_id 恢复；P11 同票根治 Facade 在 CHG 离开 DRAFT 后的幂等范围卡重建，禁止在 CLI 中绕过服务真源。
> V2.4.1 依据 B01～P11 只读审计修订：仅同步已验收 P 链与 B 链的事实投影，固定 P11 隔离提交锚点；不重写原子任务合同、不把历史失败尝试改写为通过，也不越过本轮审计范围宣称 E/C/Q 已闭合。
> V2.4.3 依据 C09 真实隔离工作树实演修订：R1 的双根身份验收不覆盖 Run 创建、意图重放与新增文件投影；增加 C09-R2 集成门禁，保留旧意图与模型授权事实，不用数据库手改绕过。
> V2.4.4 依据 C09/Q03 真实执行准备失败修订：C09-R2 的双根合同未使微任务计划持久化与 Run/租约创建成为原子操作，且规划入口把 24 小时租约写死；新增 C09-R3A 作为 C09 的恢复前置，完整的受控撤销与 fencing 进入 V04-R1，不用改系统时间、直改数据库或抢占有效租约绕过。
> V2.4.5 依据 C09 真实长租约阻断修订：将可复用的租约生命周期、受控撤销与 epoch fencing 前置为 V04-R0；C09-R3A 可以在“旧租约到期”之外，经 V04-R0 的受控 Recovery 链证明无 Popen 后撤销。V04-R1 保留真实进程中断/回收的端到端演练，不以等待自然到期替代治理。

> V2.5.0 依据主工作区、隔离候选与 canonical Continuity 数据库的只读核验同步 C09 真实进度：原业务 Run 仍待验收，R3B/R3C 和项目身份收口均未闭合，两条本轮辅助 Run 已 FAILED。隔离候选 V2.4.8 只作待核对输入；本次只修订本 WBS，不恢复执行或改动业务、治理对象与 release。
> V2.5.1 补核 V04-R0 的取消、FIX/FENCE 的技术 Checkpoint 与待验收状态、两次 FAILED Recovery，以及旧 `app.db` 原字节备份和缺失的处置回执。§4.8 的 V01～V08 整体未开工；V04-R0 是为 C09 阻断前置的有限抢先，不等于 V 批次或 M2 启动。
> V2.5.2 仅同步用户对 `CHG-SAFE-2026-012` 单目标 FENCE 的独立验收：对应 Work 为 `ACCEPTED`，CHG 为 `completed`（未流转 `closed`），不外推到 V04-R0 整体、FIX、R3B、R3C、C09 或 M1/M2。
> V2.5.3 仅同步 V04-R0 FIX 子 Work 的独立验收：当前候选字节与 Checkpoint 匹配，补做租约生命周期/恢复定向验证后 `WORK-SW008-PMF-V04R0FIX-001` 为 `ACCEPTED`；上层 `CHG-SCPT-2026-309` 仅为 `implementing`，V04-R0 整体及 C09 仍未验收。
> V2.5.4 仅记录 `c09-final-e2e` 的 `app.db` 单目标补充证据裁决：原始 JSON 处置回执仍缺失，事后审计记录与原会话输出、备份、Decision 范围和当前字节可并列支持限定的恢复到 HEAD 事实；不据此追认 R3B/R3C/C09 验收或恢复原业务 Run。
> V2.5.5 记录按用户批准顺序开展的 R3B SW008＋SW009 独立质量门复核：既有 R3B Checkpoint/Work/Decision 仅覆盖 SW008；SW009 当前业务候选定向 pytest/Ruff 为 PASS、strict Mypy 为 exit 1（201 项）。跨项目门禁未通过，R3B Work 仍 VERIFYING；依 WBS 停在 R3B，不进入 R3C 或原业务 Run。
> V2.5.6 记录独立 SW009 12 文件类型修复：新隔离候选同 HEAD 的自动 Checkpoint 当前字节与 pytest/Ruff/Mypy 三门均 PASS，修复 Work 已 ACCEPTED、Run SUCCEEDED 且租约已释放，CHG-SCPT-2026-016 completed、台账无差异；原业务候选仍为原字节、原 strict Mypy 失败没有被该修复覆盖。SW008 与 SW009 两份证据位于不同工作树，尚无同一联合候选及原业务 Run 当前字节验收，R3B 总 Work 继续 VERIFYING，R3C/C09/M1 不推进。
> V2.5.7 记录新隔离候选将已验收的 SW008 15＋SW009 12 文件差异作同头、同字节组合；两项目 pytest/Ruff/Mypy 六门 exit 0，自动联合 Checkpoint 当前性 true。联合质量 Work 已独立验收、Run SUCCEEDED 且租约 RELEASED，CHG-SCPT-2026-317 completed、SW008 台账零差异。此为 R3B 联合质量子门，不替代尚未闭合的 V04-R0 原 Work 或旧 R3B 总 Work；原业务候选字节、Run、R3C、C09/M1 均未推进。
> V2.5.8 在原 V04-R0 Decision/Work 下完成未扩路径的独立验证：候选完整核心测试 129 passed、Ruff/Mypy exit 0；新同 Work 验证 Run 有当前字节自动 Checkpoint、SUCCEEDED/lease RELEASED，原 Work ACCEPTED、CHG-309 completed。原 CANCELLED Run 与两次 FAILED Recovery 不改写。旧 SW008 R3B Checkpoint 当前性复核 true，结合新双项目联合质量证据及 V04-R0 原 Work 终态，旧 R3B Work 已独立 ACCEPTED。R3C、原业务 Run/C09、M1、提交/合并/release 均未推进。
> V2.5.9 记录 2026-09-25 独立只读审计与物理验证事实：确认稳定部署回退加载 1.3.2 且 1.3.2 上下文存在 release_id 谎报（归独立基础设施线 Track A，不阻断业务线）；完成 c09-final-e2e 与 c09-r3b-joint-20260924 字节比对与 diff 矩阵，证实 FE 为弱类型旧字节、JT 为六门全绿新字节、FE 独有 test_pmf_python.py 在 JT 环境实测 exit 0；证实 app.db 两边均为 Git clean 且 blob 完全一致；定性 09-25 凌晨 c09-r3c-root-clean 上的 NOSKIP/QG 运行为旁路测试候选，不作为 R3C 主线失败证明；确立用户批准的受控单向同步推进路线。不篡改任何既定退出条件与任务依赖。
> V2.6.0 依据 2026-09-25 独立执行与端到端闭环事实：签发专用 Decision DEC-20260925-C09R3C01 恢复原业务 Run 验收租约与状态；清洗 c09-final-e2e 候选至严格 3 owned paths，五项质量门全绿；自动生成并追加内容绑定 Checkpoint CP-SW009-PMF-C09-FINAL-001，获得用户显式报批；通过 PmFacadeService.accept 与 PmClosureService 闭环流程，完成 CHG-SCPT-2026-012 实质与证据注入；RUN-PLAN-F767C11087531180 终态 SUCCEEDED（租约 RELEASED），WORK-MSN-F0564CAF05D18E0B 与 MISSION-0648162FF0602FDD 终态 CLOSED；SW-2026-009 与 SW-2026-008 双项目台账对账 0 差异。里程碑 M1 正式达成并验收。
> V2.6.1 是后续审计校准，不改写 V2.6.0 当时的状态机与用户验收事实。原 Checkpoint 的 SW009 Mypy 实际仅检查生产文件且使用 `--follow-imports=skip`；原候选对生产与测试两文件重跑 strict Mypy 为 172 errors / 12 files、Exit 1。因此“原候选五门完整全绿、M1 当前无保留通过”不成立。九条历史 `BLOCKED` Work 仍占用 P2 五文件路径，其中 NOSKIP Run 仍 `BLOCKED` 且旧租约未标记 RELEASED；本轮停在安全预检。证据见 `.auto-pm/reports/c09-p2/20260927-m0-m1-p2-independent-review.md`。
> V2.6.2 记录从已验收 G10 隔离集成提交继续构造的唯一 M1 不可变候选：`codex/m1-final-candidate` 当前洁净 HEAD 为 `a1c5d94d5da1cec7fe2ec14ada6f440608443003`，父提交 `6327cbe18029b44a838c9f19892284fcb628785d`，相对基线 `41bd6204e708b2054fc514a5f3cf377bc02ec64f` 仅含 7 条明确差异。SW008 扩展核心套件 203 passed，6 个门禁/依赖文件 Ruff 与 normal-import strict Mypy 均 Exit 0；SW009 8 passed（9 subtests）、Ruff/Mypy Exit 0；C09 E2E pytest/Ruff/Mypy Exit 0。该结果修复 V2.6.1 的质量缺口，但尚未形成新的 Decision/Work/Run/Checkpoint、未被稳定运行时消费，也未合并、部署或切换 release。新增 G10-R1 固定“验收后 Work 生命周期与显式 Resume”合同；正式 M1 治理验收须待该门与稳定运行时入口可执行后另行完成。
> V2.6.3 记录 G10-R1 与 M1 的正式收口：唯一候选沿 `a1c5d94d` 经门禁合同根治提交 `0fb0c6f3` 与生命周期提交 `8b02de55f011df31591601464e0eebf4db5e4f23` 形成洁净不可变 HEAD；`CP-SW008-PMF-G10R1-001` 绑定该提交前同一六路径当前字节，Run `RUN-SW008-PMF-G10R1-002` 为 `SUCCEEDED`、lease `RELEASED`、Work `WORK-SW008-PMF-G10R1-002` 为 `CLOSED`，CHG-328/329 均 `completed`。分支 `codex/g10-r1-lifecycle` 已推送，未合并 main。新 release `1.3.3-8b02de5` 由该精确提交可重复构建，active exact-tree 497 文件验证通过，previous `1.3.2-9d3c920` exact-tree 468 文件验证通过，隔离前切换/回退演练通过；根入口 configured/effective/load path 已一致指向新 release、无 fallback，SW008 台账 0 缺失/0 孤儿/0 不一致。原 C09 Checkpoint 局限、M0 当前未重验及 P2 阻断均保留，不因 M1 收口被改写。


## 1. 项目信息

### 1.1 交付目标和责任

交付一个用户可以日常使用的 PM 工作流：输入目标，确认方案，系统完成内部建单、授权、实际执行、测试、证据和落账，用户验收。Python 与 PLC 静态交付共用控制面；命令行、驾驶舱和 SDK 共用应用服务。中断后能够恢复，跨 Agent 不依赖手工传 JSON。

用户负责目标、范围和风险决策；当前主控负责依赖、派工、机器验证及交付；执行 Agent 负责受限范围内的实现。用户不承担探路、填对象、复制 token、查门禁或替 Agent 收尾。

最终完成条件在 §8 固定。文档完成、单元测试通过、Mission 标记 ACCEPTED、CLI 存在，均不能单独证明产品交付。

### 1.2 本次修订解决什么

| 旧方案中导致执行受阻的安排 | V2 的处理 |
|---|---|
| R01～R05 全部历史恢复后才允许产品迭代 | 仅实际 owner、路径、租约冲突阻断对应任务；用现有显式 Work/Run 选择，历史清理进入 H 队列 |
| 已恢复的缓存、已归档的文档仍写“待执行” | 使用下表的当前事实；复用已有证据，内容没有漂移就不重复操作 |
| 单项“接执行器”“自动闭环”跨多个失败面 | 拆成单行为、单退出条件的原子行；代码和该行为的测试同票交付 |
| 提交之后才能构建修复、修复之后才能提交 | B03～B06 定义固定哈希的非活动管理候选及限定投影修复；它不依赖预先提交或部署 |
| 直到最后才遇到真实 Hook | B01 记录基线，B08 实际双 Hook 预检，G01～G06 固化来源和前置检查 |
| 建立 Work 后才发现实际 Run 环境与普通命令不一致 | 每次 Run 前执行真实控制面只读快照；环境异常先做受控对照，未复现前不得写 Git 配置或新增修复范围 |
| 多条已验收候选长期并列，直到稳定发布才组合 | G10 在 P/E/C 前建立非活动集成候选；只消费不可变已验收提交，冲突返回原子来源票 |
| 每次发现都另起恢复项目 | 一个有边界的失败记录；主控负责归属和替换方案；不得暗中扩大当前 Work |
| 每原子都让用户再批准一次 | 一个批次列出内部原子、路径、验证及风险，一次范围批准后自动推进；高风险外部动作明确列入或另批 |
| 全量类型历史债既说不阻断，又在发布时要求突然清零 | §8.2 预先定义必需门禁和全库审计的不同用途；任何 FAIL 保留原结果，不到发布日临时改口径 |

### 1.3 V2.0 开工基线与当前执行叠加状态

下表保留 V2.0 制定时的开工基线，不把历史事实倒写为当前状态。每张新票只复验与其相关的指纹；2026-09-13 的实际推进状态另列于表后。

| 对象 | 当前事实 | 后续处理 |
|---|---|---|
| Git | HEAD 为 93ea7d24c95f636968db7496b7b4563c2fa0babe；216 两文件在暂存区；另有归档、治理文件和台账修改 | 保留暂存；按提交集合区分，不要求全仓空白 |
| 216 | 实现验收已有 26 项目标测试、Ruff、Mypy 证据；Work ACCEPTED、Run SUCCEEDED；尚未提交 | B02 复用证据；B09 完成现有隔离提交，不重写已通过的实现 |
| 216 文档 | 元数据、台账与正文的实施记录存在不一致；部分字段仍为占位 | B05 依据既有批准/验收事实补齐，不能以文档标记代替产品完成 |
| 根入口 | main.py 解析到 active 1.3.3-d8f7c8b；previous 为 1.3.2-9d3c920 | 已做过的缓存恢复不重做；变更后按实际来源复验 |
| 实际 Git Hook | .git/hooks/pre-commit 与 commit-msg 用 PYTHONPATH 指向 C 平铺 auto_pm，绕过 main.py | 当前 Hook 来源不是 active 指针的证明；G01/G02 处理入口和安装 |
| 提交阻断 | pre-commit 遍历注册项目，只调用 reconcile 读取既存差异；SAFE-007 的状态投影差异导致非零 | 提交检查没有再次误写 SAFE-008；B04/B06 只处理已确认的投影差异 |
| 编号误匹配 | 母体已暂存的 216 改为精确编号；平铺/活动版本未因此自动更新 | 用固定候选验证，不能认为暂存即运行生效 |
| 默认 Resume | 未指定对象时返回 MULTIPLE_ACTIVE_WORKS，work/run 为空 | 当前 CLI 已支持 --work-id、--run-id；选择歧义不是数据库损坏，也不是全项目禁写 |
| 恢复能力 | 母体存在 settle_expired_run；活动版没有 settle-expired 子命令 | H01 使用经过验证的管理候选；不能对活动版运行不存在的命令 |
| 产品入口 | plan 需要既有 Mission；approve 需要内部 Work；execute 只推进 Work；prepare 只返回 PREPARED；accept 只推进 Mission | P/E/C 各自补齐真实缺口，不以方法名推断能力 |
| 旧 Saga | pm_saga_service.py 仍关联旧 handoff 服务/状态和 pm-workflow 默认 actor | 只复用领域动作与失败样例；新闭环使用 Continuity v2，禁止重新启用退役技能 |
| 文档路线 | 39 V1.0.0 的“编制前无差异”和 R02 未恢复等已经过时 | 本版替换当前排期；26 的治理边界继续适用，历史正文不倒写成当前完成 |

#### 2026-09-13 执行叠加状态（历史快照）

| 对象 | 经核验状态 | 对后续的含义 |
|---|---|---|
| G03～G05 | Work 均为 ACCEPTED；G05 的不可变隔离提交为 `157f150457c7988b6a5142c1c0ddd52e0cb02339` | G06 只能以该提交建立候选，不能回退到 root main 或拿未提交候选代替基线 |
| G07 | 全量基线已冻结：14 项 pytest 失败、Mypy 重复模块发现失败；Ruff 通过 | 失败进入 Q01～Q03；它们不冒充 G06 失败，也不能拖到 D05 当天才分派 |
| G08、G09 | 两票均已 ACCEPTED；各自候选成果尚未作为统一源码基线 | G10 只在各自形成不可变提交后组合验证，P/E/C 不直接消费分散候选 |
| G06 | `WORK-SW008-PMF-G06-001` 为 READY，尚无 Run/lease/checkpoint；原授权仅含 CLI 与测试两条路径 | V2.1 的同一快照合同要求扩展至 INFRA/git_hook_enforcer.py，现有 Work/Decision 不可据此启动源码 Run |
| G06 候选 | `codex/g06-preflight` 位于受管目录，HEAD=`157f1504`，工作树和 diff --check 均为空 | 实际控制面 `governed_worktree_snapshot` 已在正常执行环境返回相同 HEAD、空脏路径；不存在已证实的 Git 配置阻断 |
| 运行时 | active release 仍为 `1.3.3-d8f7c8b` | 本轮所有候选均未部署；Hook 安装、合并和 release 切换仍是独立动作 |

#### 2026-09-14 G10 执行更正

| 对象 | 经核验状态 | 对后续的含义 |
|---|---|---|
| G06、G08、G09 | 三张隔离提交分别为 `02af257`、`16d3580`、`1c45ebb`，均未合并到 main | G10 只能消费这些不可变输入，不能从根工作树或来源候选复制未提交差异 |
| 首次 G10 Run | `RUN-SW008-PMF-G10-001` 在组合前的 `02af257` 启动；组合与 58 项测试均通过，但 Checkpoint 因当前 HEAD=`d87fd3d` 被 v2 同头硬门禁拒绝 | 该 Run/Work 保持 BLOCKED 审计；不得伪造 Checkpoint、改源码或把候选合并到 main |
| G10 V2.1.1 顺序 | 先以授权 Work 装配最终、洁净的非活动集成候选，再以该最终 HEAD 启动新的 Run | 新 Run 的 `git_head` 与 Checkpoint HEAD 可相同；重跑组合门禁后才允许进入 VERIFYING |

#### 2026-09-24 C09/V04-R0 当前核验投影（以 canonical 数据库和各工作树当前状态为准）

| 对象 | 已核验事实 | 收敛含义 |
|---|---|---|
| 主工作区与 release | 根 `codex/c09-recovery-governance` 位于 `482f64d5ca56a549ed6eb0cfd11ec0bab3c89c8b`；`pm resume SW-2026-008 --json` 曾返回 `MULTIPLE_ACTIVE_WORKS`，Work/Run/Checkpoint/lease 均未默认选定；active/previous 指针仍分别为 `1.3.3-d8f7c8b` / `1.3.2-9d3c920`。2026-09-24 仅将 active release 树内 17 个 `__pycache__` 目录、42 个 `.pyc` 可恢复地移入 `.auto-pm/reports/c09-control-entry/quarantined-active-cache-20260924`，manifest 的 469 文件原字节匹配；其后 launcher 实际验证并加载已指向的 active release，未改指针 | 不从根默认启动 C09；区分 V2.5.5 的 previous 加载快照与当前 active 验证事实；缓存可恢复，不把运行入口修复当作业务验收或 release 切换授权 |
| R2/R3A | R2 Work `WORK-SW008-PMF-C09R2-001` 和 R3A Work `WORK-MSN-E887C44ECCD3B240` 均为 ACCEPTED，各有 SUCCEEDED Run 与 Checkpoint；隔离提交链含 `620a4af4`、`3743ae67`、`d89b1269` | 只证明这些既定合同与已提交候选；不证明 C09、R3B/R3C 或 V04-R0 已验收 |
| B 历史汇总 | `WORK-SW008-PMF-B218-001` 当前为 CLOSED，`RUN-SW008-PMF-B218-001` 为 SUCCEEDED，具有 `CP-SW008-PMF-B218-001` | V2.4.1 的 VERIFYING 是历史快照，不再作为当前阻断；汇总关闭仍不替代逐原子证据 |
| 原 Python 业务 | `RUN-PLAN-F767C11087531180` 为 VERIFYING，`WORK-MSN-F0564CAF05D18E0B` 与 `MISSION-0648162FF0602FDD` 为 BLOCKED；原 Run 无 Checkpoint/closure，旧验收租约版本 3 未标记 `RELEASED:`；`CHG-SCPT-2026-012`（SW-2026-009）仍为 approved，文件未提交且验证结论写明待原 Run Checkpoint 与用户验收 | 保留已投影原业务、租约和 CHG；不得因词典改动或辅助 Run 而宣称验收、重新派发业务、直接改租约或清理文件 |
| C09 收敛候选 | 旧 `codex/c09-convergence` 位于 `d89b1269`，仍有未提交源码、测试及业务差异；候选 V2.4.8 尚未替换本 WBS。原 SW008 `c09-r3b-governed` 的 `RUN-SW008-PMF-C09R3B-003` 已 SUCCEEDED，同头 `CP-SW008-PMF-C09R3B-003` 在正确候选根复核 current=true；`WORK-SW008-PMF-C09R3B-002` 已独立 ACCEPTED。新双项目联合质量候选见下行；R3C 与 closure Work 仍 IN_PROGRESS | R3B 技术前置已验收，但原业务候选仍为旧字节且原业务 Run 无 Checkpoint；不得凭 R3B 直接宣告 R3C/C09/M1 验收或合并 |
| 本轮辅助 Run | `RUN-SW008-PMF-C09-CLOSURE-003` 与 `RUN-SW008-PMF-C09R3C-007` 均已停止并在 canonical 库中为 FAILED，均无 Checkpoint；对应 Work 未验收 | 本轮停止在 WBS 修订；失败保留审计，不重启、改写或以新 Run 遮盖 |
| V04-R0 原目标 | 原 `RUN-SW008-PMF-V04R0-001` 仍 CANCELLED、无 Checkpoint，租约已 fenced；两次恢复尝试 `RUN-SW008-PMF-V04R0REC-001/002` 仍 FAILED、无 Checkpoint，恢复 Work 仍 IN_PROGRESS。原 `WORK-SW008-PMF-V04R0-001` 沿既有 Decision 在 HEAD `85beeb12` 的同一候选补 `RUN-SW008-PMF-V04R0-VERIFY-001` / `CP-SW008-PMF-V04R0-VERIFY-001`：6 个实际存在的授权 owned 文件、5 个当前脏文件；完整核心 pytest 129 passed、Ruff/Mypy exit 0，自动 Checkpoint 三门 exit 0/current=true；新 Run SUCCEEDED、lease RELEASED，原 Work ACCEPTED，`CHG-SCPT-2026-309` completed | V04-R0 基础合同已独立验收，但原 CANCELLED 与 FAILED 历史不改写；V04-R1 真实进程回收演练、R3C 和原业务另有门槛 |
| V04-R0 FIX/FENCE | `RUN-SW008-PMF-V04R0FIX-001` 与 `RUN-SW008-PMF-V04R0FENCE-001` 均 SUCCEEDED，分别有同头 `CP-SW008-PMF-V04R0FIX-001`（候选 HEAD `85beeb12`）和 `CP-SW008-PMF-V04R0FENCE-001`（控制根 HEAD `482f64d5`）。FIX 自动收据仍仅固定 13 个 `append_verified_checkpoint` 用例；本轮另以同一候选完整核心 129 个用例通过，FIX/current=true，Ruff/Mypy exit 0。FENCE 目标 lease epoch 4、`RELEASED:`，结算及 fencing 事件存在；FIX/FENCE 子 Work 均 ACCEPTED，`CHG-SAFE-2026-012` completed（非 closed），候选源码/测试仍未提交 | 子票与原 Work 现在分别有独立证据，不以 FENCE 子票改写原 CANCELLED Run；完成 V04-R0 不代表 V04-R1 或 C09 验收 |
| 旧 `data/app.db` | 候选 V2.4.8/`CHG-SCPT-2026-014` 记录原业务证据采集曾被受跟踪、越界脏路径阻断。原字节备份 SHA-256 为 `6B6932B2124F853976A3E85DF9DEFCDBCD5D981B38513FCE44B9468B92AAC17E`；要求的原始 JSON 处置回执仍缺失，相关 C09FE 三个 Run 与 FINISH Run 均 FAILED、无 Checkpoint。2026-09-24 的[单目标事后审计与补充证据裁决](../../.auto-pm/reports/c09-fe/RUN-PLAN-F767C11087531180-app.db-retrospective-audit-20260924.md)将原会话 `preserve-reset` 输出、`DEC-20260923-C09DONE2` 范围、备份及 `c09-final-e2e` 当前/HEAD blob 交叉核对；当前该文件 SHA-256 为 `6F9DF94BD217C0D915559AFC234CB4678720CD0C46B638D92D578A7D15277838`，blob 为 `afc44bd8246ab3d34d3b668188f6f31f229bde69`，路径 Git 状态为空 | 仅接受限定的“该候选曾恢复到当时 HEAD 且当前同 blob”补充证据，不伪造原 JSON；继续完整候选差异、owned-path 和当前内容核验，不据此创建 Checkpoint、改变 FAILED 历史或降低其他门槛 |
| R3B 原业务候选历史复核 | [2026-09-24 独立门禁记录](../../.auto-pm/reports/c09-r3b/20260924-sw008-sw009-independent-gate-attempt.md)：既有 `CP-SW008-PMF-C09R3B-003`、Work/Decision 的有效范围仅 SW008；SW009 `c09-final-e2e` 当时改动文件定向 pytest 为 7 passed、9 subtests，Ruff exit 0、strict Mypy exit 1（201 项）。原业务候选至今未获联合修复写入 | 保留原候选的失败字节与历史裁决，不将新联合候选 PASS 倒写旧业务候选；原业务 Checkpoint/C09/M1 仍未验收 |
| SW009 类型修复本票 | `codex/c09-sw009-type-repair` 同 HEAD `d89b1269`，仅 12 个批准文件有差异；`CP-SW009-C09R3B-TYPE-001` 自动收据的 pytest/Ruff/Mypy 全 exit 0，当前字节复核 true；另独立原样 strict Mypy 含 `tests/test_services.py` exit 0，服务测试 8 passed、9 subtests。`WORK-SW009-C09R3B-TYPE-001` ACCEPTED，Run SUCCEEDED/lease RELEASED，`CHG-SCPT-2026-016` completed 且 SW009 台账 0 差异。原 `c09-final-e2e` 两份业务文件哈希未变 | 该修复单独只解除 SW009 类型子门；与 SW008 来源分属不同工作树的缺口，现由下行的新联合候选另行证明，不倒写原业务候选。GUI 全量未运行；R3B 总 Work 继续 VERIFYING |
| R3B 同候选联合质量本票 | 新 `codex/c09-r3b-joint-20260924` 位于 `d89b1269`，只机械组合已验收的 SW008 15 与 SW009 12 个差异；两个项目的 diff 分别与来源一致，无 staged/untracked。`CP-SW008-PMF-C09R3B-JOINT-001` 为同一候选、两项目根、27 个 owned/dirty 路径的 v2 自动证据，六门 pytest/Ruff/Mypy 均 exit 0、当前性 true；SW009 测试文件额外 strict Mypy exit 0。`RUN-SW008-PMF-C09R3B-JOINT-001` SUCCEEDED、lease RELEASED，`WORK-SW008-PMF-C09R3B-JOINT-001` ACCEPTED，`CHG-SCPT-2026-317` completed，SW008 台账 0 差异；`app.db` 哈希未变 | 联合质量子门与旧 R3B 总 Work 现均已独立验收；原业务候选仍为旧字节，R3C 原 Run 权限恢复及 C09/M1 不因 R3B 通过而自动成立 |
| V 批次/M2 | canonical 未见 V01～V08 对应已验收 Work；§4.8 仅 V04-R0 因 C09 租约阻断提前开展技术子步骤，V04/FIX/FENCE 状态如上 | 不将 V04-R0 抢先工作表述为 V01～V08 或 M2 整体开工；V01 可按 C01/C03 依赖另行授权，V02/V03/V05 等仍受 C09 等前置约束 |

#### 2026-09-25 C09 端到端闭环与 M1 历史验收记录（当前质量裁决以 2026-09-27 表为准）

| 对象 | 已核验事实 | 收敛含义 |
|---|---|---|
| 原 Python 业务 Run | `RUN-PLAN-F767C11087531180` 经专用 Decision `DEC-20260925-C09R3C01` 受控恢复租约，成功记录 Checkpoint `CP-SW009-PMF-C09-FINAL-001` 并获用户明确验收。通过 `PmClosureService` 推进至终态 `SUCCEEDED`（version 4/5），租约已原子释放并标记 `RELEASED` | 原业务 Run 完整闭环，无需新建替代 Run，0 次手工治理 JSON |
| 业务 Work / Mission | `WORK-MSN-F0564CAF05D18E0B` 终态 `CLOSED`（version 7）；`MISSION-0648162FF0602FDD` 经 `accept()` 流转 `ACCEPTED` 并由 closure 推进至终态 `CLOSED`（version 7） | C09 业务任务与主授权 Mission 均达成正式闭环 |
| 候选工作树与质量门 | `c09-final-e2e` 剔除全部 24 个越界脏路径，严格锚定 3 owned paths；替换缺失类型依赖，pytest（7 passed, 9 subtests）、Ruff（0 issues）、Mypy（success）、E2E 门禁全部 Exit 0 全绿 | 质量门契约 100% 达成，无越界污染，无测试作弊 |
| 变更单实质注入 | `CHG-SCPT-2026-012`（SW-2026-009）经 `SubstanceInjector` 自动注入实施记录、验证证据链（Closure `CLOSURE-81A79E222611B45666151B32`）与加密签名，通过 SubstanceChecker 零占位检查 | 变更管理闭环，无手工填表 |
| 项目台账对账 | 工作区根执行 `main.py ledger reconcile SW-2026-009` 与 `main.py ledger reconcile SW-2026-008`：两项目台账缺失 0、多余 0、状态不一致 0，均显示 `✅ 对账无差异` | 双项目台账与 canonical 状态完全一致 |
| 里程碑 M1 状态 | M1（第一条可用 PM-Flow 候选）退出标准已全部达成并由用户核准 | M1 状态正式标记为 `COMPLETED / ACCEPTED`；后续推进 M2/V01～V08 |

#### 2026-09-27 独立复验与 P2 当前投影（覆盖上述历史验收叙述的当前裁决）

| 对象 | 当前证据与裁决 | 下一门槛 |
|---|---|---|
| M0 | B10 Work `ACCEPTED`、B218 汇总 Work `CLOSED`、G10 后续 Work `ACCEPTED`；已验收 G10 集成提交 `d87fd3d68222a27850530a14ec1ac452b467be87` 保留为 M1 重建起点。本轮未逐项重演 B/G 全部 Hook 与发布入口证据 | 历史完成记录保留；当前完整复验仍为 `UNVERIFIED`，不得由 M1 候选质量结果反推为重新验收 |
| C09 业务状态 | 原 Run `SUCCEEDED`、租约 `RELEASED`，原 Work/Mission `CLOSED`，Closure `COMPLETED`，CHG-012 `completed`，SW008/SW009 对账均 0 差异；业务终态 `PASS` | 历史数据与批准事件保持不变 |
| C09 原候选质量 | CP-SW009-PMF-C09-FINAL-001 的 SW009 Mypy 命令使用 `--follow-imports=skip`，仅含 `dictionary_service.py`，漏检 `tests/test_services.py`。同原候选以 `mypy --strict --no-incremental` 重跑两文件为 172 errors / 12 files、Exit 1 | 历史缺口与原 Checkpoint 永久保留，不以后续候选倒写 |
| M1 统一不可变候选 | `codex/g10-r1-lifecycle` 洁净 HEAD `8b02de55f011df31591601464e0eebf4db5e4f23`，提交链为 `a1c5d94d → 0fb0c6f3 → 8b02de55`，已推送 origin、未合并 main。V2.6.2 的跨项目完整质量门保持 PASS；G10-R1 追加 138＋117＋58 项回归及六文件 Ruff/Mypy PASS | `CP-SW008-PMF-G10R1-001` 绑定提交前同一六路径字节；`RUN-SW008-PMF-G10R1-002` SUCCEEDED/lease RELEASED，`WORK-SW008-PMF-G10R1-002` CLOSED，CHG-328/329 completed。当前 M1 治理证据链 `PASS` |
| 生命周期/稳定入口 | release `1.3.3-8b02de5` 由精确提交 `8b02de55` 可重复构建，aggregate manifest SHA-256 `940176be95603ba18fa1939361415aaffd7246cda2b193bc74153ca5b0d96050`；active exact-tree 497 文件、previous `1.3.2-9d3c920` exact-tree 468 文件均通过，隔离前切换/回退演练通过。根入口 configured/effective/load path 一致指向新 release、fallback 为空 | 稳定入口已消费验收实现。83 条 `ACCEPTED` Work 不再计入执行活动集合；12 条真实 `BLOCKED` Work 继续保留并占用自身路径，须显式选择或按各自证据前向处置，不批量取消 |
| P2 / CHG-323 | 五文件代码存档存在；相关历史 `BLOCKED` Work 与本票路径重叠；NOSKIP Run `BLOCKED`、旧租约保留已过期 token，缺真实进程回收证明。CHG-323 仍 `implementing`，P2 `BLOCKED` | G10-R1 只根治活动状态判定与显式 Resume，不替代 NOSKIP 进程/租约证据；P2 在自身前置满足前不启动新 Run |
| M2 | U01 的显式依赖为 P06/E03/C07，P2 不是其 WBS 明列前置；U/V 整体尚未启动或验收 | 先形成 U01 独立实施卡并复核路径冲突；M2 的代码执行、CHG/Decision/Work/Run 另行报批，D 阶段发布仍另行验收 |

### 1.4 一个确定的主线

B 解除当前提交阻塞 → G 固定开发与门禁通道 → P/E/C 完成第一条真实 Python 闭环 → U/V 完成驾驶舱、SDK、PLC 与恢复验证 → D 稳定部署和连续使用。

H 是有限的历史处置队列。只有它的具体对象确实占有当前批准路径或有效写入资格时，才成为该对象所对应任务的前置；不能用“历史未全清”阻断主线。

## 2. 迭代目标

### 2.1 用户需求及最终证据

| 需求 | 用户可观察结果 | 实现任务 | 最终验收 |
|---|---|---|---|
| REQ01：不用手写表单 | 输入 PID/目标即可得到草案；批准后自动形成 CHG/Decision/Mission/Work | P01～P11 | AC01、AC02 |
| REQ02：真正派工 | 有真实执行进程、实际模型和退出码；失败不会假报接管 | E01～E08 | AC03、AC04 |
| REQ03：自动测试与证据 | 自动收集本任务差异、领域门禁、Checkpoint | C01～C03 | AC05 |
| REQ04：自动落账 | 验收绑定证据，CHG 和台账由服务同步，失败可重试 | C04～C09 | AC06、AC07 |
| REQ05：恢复与跨 Agent | 重开界面或换 Agent 后续同一 Work，过期 owner 不能续写 | G08、E06～E08、V03～V04 | AC08 |
| REQ06：三种入口 | CLI、GUI、SDK 同一权限、同一事实、同一收口 | P11、U01～U08 | AC09 |
| REQ07：IT/OT 都可用 | Python 真实任务和 PLC 静态工程均完成新需求到验收 | C09、V01～V02、V05 | AC10 |
| REQ08：有强门禁 | 未批准、伪单号、越界、台账不一致、坏证据都被拒绝 | B08、G03～G06、V06 | AC11 |
| REQ09：技能与模板减负 | 技能只调服务；从已通过的真实工程提取模板 | V07～V08、D01 | AC12 |
| REQ10：能稳定运行 | 可复现构建、实际加载一致、兼容回退、连续使用 | D03～D09 | AC13、AC14 |

### 2.2 “两步”的准确含义

正常业务有两次用户决策：批准目标/范围，验收成果。系统内部仍保留完整治理对象，自动创建和校验。任务执行、模型续跑、同范围重试、测试及证据生成不逐条询问用户。

提交、合并、部署、实际数据库恢复或全局规范修改是可独立批准的动作。可在一个清晰的批次批准中同时列明多项动作；不得把“不再机械问询”解释成自动取得所有权限。

自然语言理解由当前主控或获准模型完成；Facade 接收经过校验的结构化意图，不凭空假设 Python 领域服务自身具备大模型推理能力。

### 2.3 对历史蓝图的保留与替换

保留 plan/execute/resume、领域组件复用、零手工 JSON、双领域实战、薄 SDK/技能与真实 Git 硬锁。旧蓝图中的稳定目录直接编码、PM_SESSION 执行真源、handoff.v1、pm-workflow、跨 DB/Git/文件“全局 ACID”、全仓回滚，均不作为本版实现办法。

历史 Pass=51、旧 45/1803 项测试等仅为历史证据，不是新版本固定验收数字。禁止通过 import 或 --help 成功宣布端到端完成。

## 3. 迭代范围

### 3.1 路径缩写与唯一真源

本表只用于展开下文路径，不创建新目录或第二份状态真源。工作区根为 C:/Users/fubai/Documents/My_Workspace。

| 缩写 | 相对工作区根的完整路径 | 职责 |
|---|---|---|
| S | SYS-2026-001_WorkspaceGovernance | 治理计划、批准与验收 |
| D | 01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具 | 唯一研发母体 |
| C | 00_Infrastructure/auto_pm | 稳定部署、launcher、release manifest、双槽 |
| R | .auto-pm | 根运行库、只读报告、构建候选与恢复介质 |
| O | 00_Obsidian_Base全局规范文件仓库 | 生效规范，只读消费 |
| CHGDIR | D/04_监控/01_变更管理/01_变更单 | 变更单实际目录 |
| LEDGER | D/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md | SW-2026-008 台账投影 |
| CORE | D/auto_pm/application/core | 应用服务 |
| INFRA | D/auto_pm/infrastructure | 运行库、进程和 Git 适配 |
| CONTRACT | D/auto_pm/contracts | DTO 与协议 |
| CLI | D/auto_pm/ui/cli | CLI 接入 |
| QML | D/auto_pm/ui/qml | 现有驾驶舱视图、Bridge |
| T | D/tests | 自动化测试 |

矩阵里的“拟新增”路径是待建设资产，不能当作现在可执行的命令。每个批次授权自动展开这些路径，并把本批 CHG/Decision/验收文档的确切生成路径列入附件；不得拿“相关测试”“整个目录”充当写入白名单。

### 3.2 复用状态和运行架构

| 已有资产 | 本轮结论 | 本版安排 |
|---|---|---|
| 216精确编号匹配 | 已实现且验收，尚未提交/部署 | B复用，不重写 |
| 显式Work/Run选择 | 活动版现有能力 | 从第一批直接使用 |
| settle-expired / Runtime Decision参数 | 母体HEAD已有，活动版未提供 | H验证和桥接，不再开发一套 |
| 根main.py Hook模板 | 母体HEAD已有，实际安装仍旧模板 | G01复用、G02受控安装 |
| Mission/Facade/执行prepare | 类和测试已有，真实链路未接通 | P/E/C补行为缺口 |
| 旧pm_saga_service | 混有退役handoff语义 | 领域动作可复用，v2收口入口拟建 |
| 实际监督器/新意图入口/Cockpit SDK | 尚无本轮端到端可用证据 | 明列实现与实演任务，不记已有PASS |



~~~mermaid
flowchart LR
    USER["目标 / 范围批准 / 验收"] --> ENTRY["CLI / QML / 薄 SDK"]
    ENTRY --> FACADE["现有 PmFacade + 新增接线"]
    FACADE --> DRAFT["PlanningDraft / request_id"]
    DRAFT --> CHG["CHG / 规范 / 范围卡"]
    CHG --> DEC["用户批准的 Decision"]
    DEC --> MIS["Mission + AuthorityEnvelope"]
    MIS --> WORK["选定 Work"]
    WORK --> SUP["执行监督器"]
    SUP --> EXEC["真实本地执行 Agent"]
    EXEC --> EV["Diff / 门禁 / Checkpoint"]
    EV --> CLOSE["Continuity v2 收口 + 幂等投影"]
    FACADE --> DB["根 continuity.db"]
    SUP --> DB
    CLOSE --> DB
    CLOSE --> DOC["CHG / 台账 / 只读摘要"]
    CODE["固定母体 commit"] --> REL["不可变 release"]
    REL --> LAUNCH["main.py 统一解析"]
    LAUNCH --> ENTRY
    LAUNCH --> HOOK["pre-commit / commit-msg"]
~~~

控制面是唯一状态写入者。执行 Agent 只改 owned paths；监督器维护租约与进程身份，模型提示中不出现 token。QML 只呈现服务结果，不另建任务状态机。root main 用于控制和集成，一个候选 worktree 执行一个批准批次；所有权证明代替“工作区必须完全干净”。

### 3.3 已决定的关键取舍

1. 显式选择 Work/Run：优先使用当前已存在的参数；多任务列表是产品增强，不先发明一套恢复机制。
2. 一次性管理候选：B03 可使用固定 HEAD 加 216 精确补丁，尚未提交也能做限定恢复。身份记为管理候选，不称 release，不改 active，不把 PYTHONPATH 偷换为日常入口。
3. 双 Hook 保留：B08/B09 仍通过实际 Hook；G 才按预定工作修改安装模板、作用域和异常行为。禁止 --no-verify 或临时关闭 Hook。
4. 候选与正式发布分开：管理候选允许 base+patch 哈希；正式发布必须来自已提交母体 commit。
5. 先做本机单执行器：Codex 是首个后端；其它 Agent 通过平台中立交接。没有真实登录/启动证据就记“执行器不可用”，不声称全自动。
6. 跨资源提交：SQLite 事务加持久步骤/outbox；文件按内容哈希幂等更新。失败补偿只影响本事务写入，不恢复整棵工作树。
7. 门禁前置：每批开始时运行当前必需预检。恢复包允许以已知 FAIL 为输入，验收必须消除它；不能规定“修复门禁的工作必须在原门禁已绿时才能开始”。
8. 前授权对象分层：`PlanningDraft` 只承载目标、验收、范围演进和请求幂等，不是 `Mission`，没有 `AuthorityEnvelope`，不能派生 Work/Run 或进入执行；真实 CHG 与用户批准的 Decision 齐备后才允许物化强授权 Mission。不得把 `Mission.authority` 改为可空，也不得伪造占位 CHG/Decision。
9. 批次授权：本版将 94 个原子作为 4 个里程碑内的步骤；对旧文档“逐包审批”的粒度解释在批次 Decision 中明写，不静默改 O 或 .trae 法典。

## 4. 迭代计划

### 4.1 原子任务的定义与推进规则

每个原子交付一个独立可判断的行为，包含该行为的测试，不把“全部实现”与“以后补测试”拆成两票。源码增量以 1～3 个主文件加对应测试为常态；跨文件的单一事务必须整体验证。

每行含依赖、产出位置、机器判定和执行/复核模型。依赖完成、当前批次授权有效、目标 lease/基线无冲突即自动进入下一行。单项预计一个 15～60 分钟专注窗口；这是拆分预算，不是完成时间保证。两次同因失败后由主控在本票内复盘并改方案；超出路径/风险范围才提交一个合并后的决策点。

每张源码 Run 在创建前或重新进入前必须通过一次真实执行就绪门：以将实际使用的控制面、解释器、候选 worktree 和 Git 子进程采集 `HEAD`、工作树脏路径、工作树身份及目标 Work/Decision。检查必须无写入，记录执行环境、完整命令、候选 HEAD 和退出码。任何诊断先在同一调用链复现，并与隔离环境对照；未证明为稳定产品问题时，不得写 Git 配置、停止守护进程、替换 PATH 或修改源码。已有 READY Work 不豁免此门，只有通过后才能创建新的 Run。

“同一快照”专指 Git index 的不可变 `StagedSnapshot`；提交信息文件与工作树内容是显式的实时输入，预检必须记录其路径和读取阶段。预检的成功只描述该次输入，不能保证未来 Git commit 前的文件仍未变化。实现不得复制 `.git/index`、篡改 `GIT_INDEX_FILE` 或以 monkeypatch 冒充真实 Hook；应让同一 `StagedSnapshot` 直接进入实际 `pre-commit` 与 `commit-msg` 的公共检查函数。

“完成”先记行为证据；实现、验收、提交、部署各自有状态。下表是任务合同，当前进度以 §1.3 的最新核验投影及 canonical 对象为准；没有有效证据的行保持 PLANNED，不以候选差异或历史批准宣称完成。

模型路由从 V3.0.10 起以风险等级为准：`R0`=纯文档/机械只读，`R1`=单模块且无状态机/租约/并发，`R2`=跨 UI/Service/Store、异步、幂等或持久状态，`R3`=事件链、租约、进程回收、历史恢复或发布切换。未启动任务各行既有 `A/T/G/L` 只保留为历史建议，不再构成模型授权；实际模型、reasoning effort、adapter 与独立复核者必须记录在 Decision/Run。默认路由为 R0=Luna/Terra、R1=Terra high、R2=Sol high/xhigh、R3=Sol ultra 或 Astra 规划并由 Sol 执行；任一等级都不能替代路径、门禁、Checkpoint 与用户批准。

### 4.2 B：当前提交阻塞的有限解除（B01～B10）

批次产物：216 代码隔离提交、恢复记录可追溯、原有无关改动仍在。B 的实际投影修复属于本次新提出的明确范围，不声称已被此前“隔离提交”覆盖。

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| B01 | 冻结本批输入清单 | 本版 | R/reports/PMF-20260912/B01.json（拟生成） | HEAD、index 两路径/哈希、LEDGER/目标 CHG/Hook 哈希；其它 dirty 分类。漂移只更新相关项，不全仓重查 | T/G |
| B02 | 确认 216 验收仍对应当前代码 | B01 | 只读 D/auto_pm/domain/change/ledger_updater.py、T/change/test_ledger_updater.py、现有 Checkpoint | 内容一致复用 26 项证据；不一致才跑该两路径测试；失败退回原 216 范围 | T/G |
| B03 | 固化非活动管理候选 | B02 | R/artifacts/PMF-20260912/bootstrap/（拟生成，只含清单对象） | 固定 HEAD + 216 补丁；源码/测试/依赖与来源哈希齐全；import 来源唯一；无 active 切换 | T/A |
| B04 | 证明唯一投影修复的安全性 | B03 | 克隆 CHG/LEDGER 夹具和 R/reports/PMF-20260912/B04.json；调用候选已有 CLI | 先只读 reconcile，再在副本用现有 --fix；允许差异仅 SAFE-007 状态单元格；008与其它字节不变；第二次零差异；无需新写恢复算法或脚本 | T/G |
| B05 | 补齐 216 治理正文的真实记录 | B02、批次授权对象就绪 | CHGDIR/CHG-SCPT/CHG-SCPT-2026-216.md；对应新的补充 Decision，不覆盖 B5DE7168 | 依据已有实施/验收记录填实；明确未提交/未部署；正文无未填项；不撤销已批准验收 | T/G |
| B06 | 执行一次 SAFE-007 精确投影修正 | B04、B05；恢复范围已批准 | LEDGER 中 SAFE-007 的状态单元格；R 下本次备份/操作证据 | 确认单写窗口并复核文件hash；源状态仍待验收；调用B04验证的既有CLI。写前差异集合扩大则零写退出；旧CLI没有跨文件CAS保证，不声称具备 | A/G |
| B07 | 核验修复前后范围一致 | B06 | R/reports/PMF-20260912/B07.json（拟生成） | 备份可读、目标正确、008 未改、无关 dirty 内容哈希相同；216 两项暂存不变 | G/T |
| B08 | 验证实际两个 Git Hook | B07 | 只读 .git/hooks/pre-commit、commit-msg；预期提交信息在专用报告目录 | 设置 PYTHONDONTWRITEBYTECODE=1；实际脚本预检，退出码都为 0；异常不能当 PASS。失败归属到 B/G 已列原子 | T/G |
| B09 | 完成 216 源码隔离提交 | B08；沿用有效提交批准 | 当前已暂存的 ledger_updater.py 与 test_ledger_updater.py 两项 | 真实 git commit 成功、两 Hook 执行；git show 仅这两源码路径。失败保留 index，不能自动再加文件 | T/G |
| B10 | 单独闭合本次治理文件集合 | B09；该集合提交范围明确 | 216文档/Decision、CHGDIR/CHG-SAFE/CHG-SAFE-2026-007.md及原批准证据、本次恢复CHG/Decision、LEDGER精确批准行；39/旧版快照若纳入须明列 | 与B09不混提；从拟提交快照检出验证CHG/Decision/台账闭包，SAFE007行不得缺原CHG；选定hunk不带DOCU012/SAFE008/217等无关行；记录提交关联 | T/G |

B04/B06 直接复用候选已有 ledger reconcile 与 --fix，不新增恢复产品或修改算法。真实运行资格仍为独立 CHG/Decision/Work/Run。复核显示当前差异集合恰好为 SAFE-007；整个项目命令之所以可被限定使用，是因为写前差异白名单、单写窗口和副本结果都已验证。不能把这种受控一次性操作宣称为命令原生支持单行过滤或原子CAS。恢复只改投影，不把 SAFE-007/008 擅自验收关闭；无法保证单写窗口就保留现场，不手工平账。

B03/B04 的候选固化、克隆验证和 B06 真实写入是同一恢复批次内不同原子。无需先完成 H，也无需先把该候选提交或部署。批次声明包含这项管理入口例外和完整目标，避免执行时再次临时索取零碎授权。

### 4.3 G：固定开发、门禁和候选集成通道（G01～G10）

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| G01 | 确认 Hook 模板统一根入口 | B09 | CLI/git_hook.py、T/cli/test_git_hook.py | 优先复用母体已有 main.py 模板；pre-commit/commit-msg 均同 launcher，禁止平铺 import；模板已满足则只补证据 | T/G |
| G02 | 安装已验证的 Hook 模板 | G01；安装范围已批准 | .git/hooks/pre-commit、.git/hooks/commit-msg；R 下旧脚本备份 | 明确模板 commit/hash；通过受控管理候选安装；实际脚本 hash 对应模板且 -B/禁缓存生效。失败只恢复本次脚本 | A/G |
| G03 | 门禁异常可靠拒绝 | G01 | INFRA/git_hook_enforcer.py、T/cli/test_git_hook.py | 解析、DB/文件读取异常必须非零，不能 warning 后放行；合法正常提交仍通过 | T/G |
| G04 | 明确暂存集合和被检快照 | G03 | INFRA/git_hook_enforcer.py、T/cli/test_git_hook.py | 检测提交所属 CHG/PID、index 中的代码/治理证据；未暂存的“修好文件”不能掩盖提交快照不完整 | T/G |
| G05 | 区分相关提交门和全局发布门 | G04 | CLI/git_hook.py、INFRA/git_hook_enforcer.py、T/cli/test_git_hook.py | 本次 CHG/关联台账缺项必拒；无关项目既存差异只报告；未知归属拒绝；发布仍跑全部注册项目对账。此合同须随 G 批次明确批准 | A/G |
| G06 | 提交前可调用同一只读预检 | G05；执行就绪门通过；范围修订已批准 | CLI/git_hook.py、INFRA/git_hook_enforcer.py、T/cli/test_git_hook.py | 预检一次读取 `StagedSnapshot`，将同一对象交给真实 pre-commit 与 commit-msg 公共检查；提交信息为实际只读输入，工作区证据仍按实际 Hook 语义读取并标记实时阶段。不得复制 index、设置替代 index 或修复被检文件。真实 Git fixture 覆盖通过、index/工作区证据不一致、未知项目和输入读取错误；失败输出项目、路径、阶段 | T/G |
| G07 | 建立固定候选及回归输入基线 | B09 | 一个批准的候选worktree；R/reports/PMF-20260912/G07.json；只读已有 worktree_policy_service 与测试 | 固定commit检出；复用已有worktree策略；运行全量基线并冻结失败指纹；源码差异清单确定，不先重写构建系统 | T/G |
| G08 | 选定Work的状态读模型一致 | G07 | CORE/continuity_resume_service.py、CONTRACT/continuity_resume.py、T/core/test_continuity_resume_service.py | 复用现有 --work-id/--run-id；已结束Run的旧lease不伪装活跃写入故障；合法多任务可列选择；不扩大写权限 | T/G |
| G09 | 呈现实际加载版本身份 | G07 | CORE/workspace_context_service.py、CONTRACT/workspace_context.py、T/core/test_workspace_context_service.py；根main.py如需传递身份须明列 | configured/effective/load path/fallback reason来自实际launcher；不把active指针当已加载证明 | T/G |
| G10 | 集成已验收的门禁和运行身份候选 | G06、G08、G09；各自隔离提交已形成 | 一个受管的非活动集成 worktree；R/reports/PMF-20260912/G10.json | 在已授权 Work 内先从 G06 不可变提交建立候选，仅以 `cherry-pick -x` 组合 G08、G09，并列出三票提交、父项和路径；候选最终 HEAD 洁净后才启动 G10 Run。随后运行 G06/G08/G09 定向组合测试并创建同 HEAD Checkpoint。冲突或输入基线不一致时仅复原新 G10 候选、保留证据并回到来源票；不安装 Hook、不合并、不部署、不切换 release | A/G |
| G10-R1 | 验收后 Work 生命周期与显式 Resume 合同收敛 | G10；统一 M1 不可变候选 `a1c5d94`；独立 CHG/Decision/Work/Run 与精确路径授权 | CONTRACT/continuity.py、INFRA/continuity_store.py、CORE/continuity_resume_service.py、CORE/work_registry_service.py；T/core/test_continuity_resume_service.py、T/core/test_work_registry_service.py | **PASS / ACCEPTED**：execution-active 仅含 `PLANNED/READY/IN_PROGRESS/BLOCKED/VERIFYING`；`ACCEPTED` 为不可执行的验收后状态，不占路径、不参加默认 Resume，且只能到 `CLOSED`；`CLOSED/CANCELLED` 为终态。多活动对象时默认恢复 Fail-Closed，显式 `--work-id/--run-id` 可精确选择；`BLOCKED` 继续占路径。六路径当前字节 Checkpoint、Run/lease、Work 与 CHG-328/329 均闭环，洁净提交 `8b02de55` 已由稳定 release `1.3.3-8b02de5` 消费；现有 12 条 BLOCKED 未批量关闭、历史 Checkpoint 未改写 | A/G |

G01、G03～G10-R1 已在受控候选实现，G02 是明确批准的 Hook 安装动作。G10-R1 最终不可变提交为 `8b02de55`，稳定入口已由 release `1.3.3-8b02de5` 消费；模板安装、候选验收、稳定部署和 main 合并仍是不同边界。M2 后续以该 release 对应提交作为运行时起点，不从分散 Work、旧 C09 候选或主工作区脏文件重新拼装；若需要 main 集成，仍须单独授权。

#### G10 的固定控制顺序（V2.1.1）

1. 已批准的 CHG、Decision 和 Work 固定 G06/G08/G09 的输入提交、父项、九条源码/测试路径及 G10.json；此时不得创建 Run。
2. 在新建的非活动 G10 worktree 中，以 G06 的不可变提交检出候选，仅使用 `git cherry-pick -x` 组合 G08、G09。该装配不编辑来源候选、不引入新源码差异、不安装 Hook，也不合并 main。
3. 核验最终集成 HEAD、来源保留信息、九条组合路径和候选洁净状态。冲突或输入提交/父项不一致时，只复原该新 G10 候选至 G06 基线并将 Work 标记 BLOCKED；来源票保持不变。
4. 仅在步骤 3 的最终洁净 HEAD 上启动 G10 Run，`declared_dirty_paths` 为空。重跑 58 项定向组合 pytest、九路径 Ruff、六生产源码 Mypy 与基线到最终 HEAD 的 diff --check。
5. 使用同一最终 HEAD 创建 Checkpoint，Run/Work 转 VERIFYING，CHG 转 pending_acceptance。任何绕过、伪造初始 HEAD、预先启动 Run 后再组合提交，均为失败而不是恢复路径。

过渡期必须关闭已知误写入口：216未部署前，后续批次的CHG/台账写入统一交给已固化216修复的管理候选，并在该批Decision列明命令、目标与内容hash；不能在旧active写账后再次临时修补。它与现行控制面共用唯一根Store和串行写入资格，不建立第二本真实账。普通生产只读仍从main.py进入。P/E/C的新产品代码先在隔离的演练数据/工程上验证，真实模型进程确实执行；M1/M2称“可用候选”，D07之后才称稳定上线。管理候选在正式更新后退出写入入口。

### 4.3.1 Q：已冻结基线失败的独立收敛（Q01～Q03）

Q 队列来源唯一为 G07 的失败指纹。它不回写历史 PASS，也不把已知的历史 CHG 格式告警、旧 ACL 或远端差异混入范围。Q 可以与不依赖其结果的 G/P/E/C 候选研发并行；D03、D05 前必须完成。

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| Q01 | 使 Vartable 真实样例在干净候选可复现 | G07 | T/vartable/samples/Work-FB变量表导出.csv、T/vartable/samples/Autoshop-FB变量表导出.csv、T/vartable/test_format_detector.py、T/vartable/test_work3_parser.py、T/vartable/test_autoshop_parser.py | 从固定候选检出并运行三份测试；两个样例的内容哈希、编码和解析断言一致。若样例不能合法入库，测试必须明确跳过的产品边界并由替代真实样例重新验证，不能伪造 parser 结果 | T/G |
| Q02 | 使 PDF 导出测试在声明运行环境可重复 | G07 | QML/bridges/delivery_bridge.py、T/qml/test_delivery_bridge.py | 用真实 Qt 离线 PDF 路径运行 exportDocToPdf；Windows COM/Office 不作为隐含依赖。若当前 Qt 平台不支持，报告版本与能力矩阵并回到本票处理，不能把环境错误记为通过 | A/G |
| Q03 | 消除 Mypy 的重复模块发现歧义 | G07 | D/pyproject.toml、T/__init__.py、D/templates/python-tool/template/tests/__init__.py | 以固定工作目录运行全量 Mypy，目录发现唯一且不通过忽略目录掩盖真实新代码；后续全量静态检查不再因 duplicate module 提前中止 | T/G |

### 4.4 P：从需求到可执行授权（P01～P11）

P 链有两个不同安全域：P02～P07 的 `PlanningDraft` 是不可执行的前授权计划记录；P08 才在真实 CHG、已批准 Decision 和同一方案 hash 完整对账后创建 `Mission`。`request_id` 与输入指纹共同保证重放：同 ID 同载荷返回同一草稿，同 ID 不同载荷必须拒绝。P08 之前任何对象不得创建 Work/Run、派发执行器或宣称已有 Mission 授权。

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| P01 | 意图输入 DTO | G10 | CONTRACT/pm_facade.py、拟新增 T/contracts/test_pm_intent.py | PID、目标、验收项、request_id 可序列化；缺必填拒绝；不写业务对象 | T/G |
| P02 | 定义不可执行 PlanningDraft 合同 | P01 | CONTRACT/pm_facade.py、T/contracts/test_pm_intent.py | 草稿含 request_id、输入指纹、目标、验收与明确的 PRE_AUTH 状态；不含 AuthorityEnvelope；类型和状态均不能被 MissionService、Work 或 Run 接受 | T/G |
| P03 | 幂等持久化唯一 PlanningDraft | P02 | CORE/pm_facade_service.py、INFRA/continuity_store.py、T/core/test_pm_facade_service.py | 同 request_id+同载荷返回同一草稿；同 request_id+不同载荷拒绝；新目标不要求用户提供内部 ID；此步不能创建 Mission/Work/Run | A/G |
| P04 | 创建唯一 CHG 草稿并绑定 PlanningDraft | P03 | CORE/pm_facade_service.py、D/auto_pm/domain/change/change_service.py、INFRA/continuity_store.py、T/change/test_change_service.py、T/core/test_pm_facade_service.py | 调用现有 create_change_request/生成器；形成唯一真实 CHG 与草稿关联；重放无重复；未批准不进入执行 | T/G |
| P05 | PlanningDraft 绑定真实规范版本 | P04 | CORE/pm_facade_service.py、INFRA/continuity_store.py、T/core/test_pm_facade_service.py | 从 O/spec_registry.json 解析 Python/PLC 有效规范路径/版本并固化来源；缺失给出具体原因，不猜规范 | T/G |
| P06 | PlanningDraft 产生可批准范围卡 | P05 | CONTRACT/pm_facade.py、CORE/pm_facade_service.py、T/core/test_pm_facade_service.py | 文件路径、验收、风险、非目标、不可变方案 hash 齐全；不使用全仓通配授权；范围卡仍不可执行 | T/G |
| P07 | 用户批准并绑定真实 Decision | P06 | D/auto_pm/domain/change/decision_service.py、CORE/pm_facade_service.py、INFRA/continuity_store.py、T/cli/test_decision.py、T/core/test_pm_facade_service.py | Decision 绑定真实 CHG 与精确方案 hash；旧 hash 批准拒绝；重复同一批准只产生一个有效 Decision；证据非模型自签 | A/G |
| P08 | 物化强授权 Mission | P07 | CORE/pm_facade_service.py、CORE/mission_service.py、INFRA/continuity_store.py、T/core/test_pm_facade_service.py | 仅以真实 change_id、decision_id、CHG_DECISION 构造 AuthorityEnvelope 并创建唯一 Mission；无占位 ID、无空授权；重放返回同一 Mission；子 Work 类型的最小授权由 P08-R 独立闭合 | A/G |
| P08-R | 强授权 Mission 的最小子 Work 类型 | P08 | Mission 授权合同与定向测试；历史隔离提交 `e2cb0787e246b0d462f26e2c6bbd5be64ff266d6` | 仅显式允许 `WorkKind.WBS`，BUG/TEST/DEBT/GOVERNANCE 等拒绝；canonical `WORK-SW008-PMF-P08R-002` 为 ACCEPTED、`RUN-SW008-PMF-P08R-001` 为 SUCCEEDED，具有 `CP-SW008-PMF-P08R-001`；旧 P08-R Work 的 CANCELLED 记录保留 | A/G |
| P09 | 从强授权 Mission 派生可选定 Work | P08 + P08-R 闭合 | CORE/work_registry_service.py、CORE/pm_facade_service.py、T/core/test_work_registry_service.py | 仅接受已允许 `WorkKind.WBS` 的有效 Mission；Work 路径不超 Decision；与其它 owner 冲突精确拒绝；用户不填 ID；无 Mission 或无 WBS 子 Work 授权不得建 Work | T/G |
| P10 | 全授权链中断可重试 | P09 | CORE/pm_facade_service.py、INFRA/continuity_store.py、T/core/test_pm_facade_service.py | PlanningDraft/CHG/Decision/Mission/Work 每一持久化边界故障注入后重试均只有一条链；不留下虚假 READY 或无授权 Mission | A/G |
| P11 | CLI 接通新需求 plan | P06、P10 | CLI/pm.py、CORE/pm_facade_service.py、T/cli/test_pm_facade.py、T/core/test_pm_facade_service.py | 新需求参数真实创建/恢复 PlanningDraft 与范围卡；批准后沿同链到唯一 Work；CHG 离开 DRAFT 后，CLI 冷启动仍可按相同 request_id+输入恢复同一 PlanningScopeCard 及授权链；保留原 Mission 调用兼容；未来参数以实现后的 --help 为准 | A/G |

### 4.5 E：真正执行、监督和接棒（E01～E08）

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| E01 | 真实本地执行器最小实演 | G10；执行器使用已批准 | 拟新增 INFRA/local_executor.py、T/core/test_local_executor.py；独立微任务夹具 | 真实模型进程完成一项允许的文件改动；记录 actual model/session/exit；mock 只能作单测；认证失败明确阻断本后端 | T/G |
| E02 | 持久调度意图 | P09、E01 | CONTRACT/execution_adapter.py、CORE/execution_adapter_service.py、T/core/test_execution_adapter_service.py | 先持久 intent 再启动；相同 operation_id 无重复调度；PREPARED 仍表示未启动 | A/G |
| E03 | 启动确认映射真实 Run | E02 | 拟新增 CORE/execution_supervisor_service.py、T/core/test_execution_supervisor_service.py | 收到真实 session/进程开始时间才显示执行；无法启动可重试且没有伪 RUNNING | T/G |
| E04 | 监督器续租且隔离秘密 | E03 | CORE/continuity_execution_service.py、INFRA/continuity_store.py、T/core/test_continuity_execution_service.py | owner/token/expiry/CAS 同一写事务核验；新日志/argv/模型上下文无明文 token；不改历史事件求清零 | A/G |
| E05 | 真实结束状态进入验证 | E03 | CORE/execution_supervisor_service.py、T/core/test_execution_supervisor_service.py | 0、非0、被终止分别处理；模型输出“成功”不能覆盖失败退出码 | T/G |
| E06 | 主控重启可识别原 session | E04、E05 | CORE/execution_supervisor_service.py、T/core/test_execution_supervisor_service.py | 持久 intent/session 对账；进程 PID 复用不误认；失联记待恢复，不盲目重复启动 | A/G |
| E07 | 自动生成 checkpoint-bound handoff.v2 | E06、C03 | CORE/continuity_execution_service.py、T/core/test_continuity_execution_service.py | 交接绑定 scope/基线/Checkpoint；接收方新租约；不使用旧 handoff 或传出 token | T/G |
| E08 | CLI execute 接真实监督器 | E05、P11 | CORE/pm_facade_service.py、CLI/pm.py、T/cli/test_pm_facade.py | execute 返回真实 dispatch 状态；先前“只改 Work 就称已接管”的路径消失 | T/G |

E07 依赖 C03，C01～C03 只依赖 E05，因此没有 E→C→E 的循环。首条 Python 闭环可在 E07 尚待跨 Agent 场景时完成；恢复是正式完成必验项，不是首条演示的虚假前置。

### 4.6 C：自动证据、验收和落账（C01～C09）

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| C01 | 采集本任务实际差异 | E05 | 拟新增 CORE/evidence_collection_service.py、T/core/test_evidence_collection_service.py | owned paths 外差异拒绝纳入；基线与暂存/未暂存分别记录；不偷收他人修改 | T/G |
| C02 | 自动执行 Python 质量门 | C01 | CORE/evidence_collection_service.py、T/core/test_evidence_collection_service.py | 真实 pytest/Ruff/Mypy 命令和退出码绑定内容 hash；非零不能伪装 PASS | T/G |
| C03 | 自动构造并追加 Checkpoint | C02 | CORE/evidence_collection_service.py、CORE/continuity_execution_service.py、T/core/test_continuity_execution_service.py | 系统生成完整证据；用户不填 result.json；代码/证据被改动后旧验证失效 | T/G |
| C04 | 用户验收绑定最新通过证据 | C03 | CORE/pm_facade_service.py、T/core/test_pm_facade_service.py | 旧 Checkpoint、失败证据、重复验收有明确结果；仅推进 Mission 不算完成 | T/G |
| C05 | 建立 v2 可恢复收口步骤 | C04 | 拟新增 CORE/pm_closure_service.py、T/core/test_pm_closure_service.py；INFRA/continuity_store.py | DB 状态和步骤/outbox 原子落库；不消费 AiHandoffService 或 HANDOFF_CONSUMED | A/G |
| C06 | 证据回填目标 CHG 实质 | C05 | D/auto_pm/domain/change/substance_injector.py、CORE/pm_closure_service.py、T/change/test_substance_control.py | 从验证证据填真实实施/验证字段；SubstanceChecker 无空壳；只改本 CHG | T/G |
| C07 | 精确台账投影和失败重试 | C06 | CORE/pm_closure_service.py、D/auto_pm/domain/change/ledger_reconciler.py、T/core/test_pm_closure_service.py | 复用216匹配；投影失败显示待同步；重复操作无重复事件；必要投影未完成不得最终关闭 | A/G |
| C08 | 按证据闭合Run/Work/Mission | C07 | CORE/pm_closure_service.py、INFRA/continuity_store.py、T/core/test_pm_closure_service.py | 合法顺序推进Run、Work、Mission的对应终态；必要投影完成后才整体完成；重放不重复事件/验收 | A/G |
| C09-R1 | 候选执行根与控制根双根绑定 | C08、E08、G10 | CLI/Facade/运行身份合同及定向测试 | 候选源码从隔离 worktree 实际加载；CHG、Decision、Mission、Work、Run 仅使用 canonical 根 Store；拒绝创建第二本 continuity.db；回执同时记录 execution_root、control_root、候选 commit 与实际加载路径 | A/G |
| C09-R2 | 双根执行链和新文件投影集成补强 | C09-R1 | 候选 CORE/INFRA/执行合同及定向测试；仅 canonical 控制根承载治理 Store | 同仓库外部隔离 worktree 可建 Run，异仓库拒绝；已持久意图仅在原洁净 HEAD 上补建唯一 Run；新增文件有明确缺失基线、成功回执及失败回滚；旧 v1 计划可读；候选身份不冒充 active release；旧提交意图不得跨提交复用 | A/G |
| C09-R3A | 执行准备原子性与有界租约 | C09-R2；目标旧 C09/Q03 Run 已到期并经 Recovery 链结算，或已由 V04-R0 的 Recovery 链证明未启动并撤销 | 候选 CORE/pm_facade_service.py、CORE/execution_adapter_service.py、CORE/execution_microtask_service.py、INFRA/continuity_store.py；T/core/test_pm_facade_service.py、test_execution_adapter_service.py、test_execution_microtask_service.py、test_local_execution_orchestrator.py | 先验证并持久化 execution_root 下的微任务计划，再创建唯一 Run/lease；准备失败不得留下 READY/RUNNING Run 或有效 lease；lease_seconds 为受边界约束的显式合同，不得硬编码 86_400；同仓库外部 worktree 的计划路径可验证，异仓库拒绝；token 不进入 argv、环境、日志、事件或公开回执 | A/G |
| C09-R3B | 跨项目质量证据与现有修复联合收敛 | C09-R3A、C08、V04-R0 的可核验证据 | 历史 `codex/c09-r3b-cross-project-gates` / `codex/c09-convergence` 与现行 `codex/c09-r3b-joint-20260924` 均为隔离候选；仅按有效 Decision 组合 SW008 15＋SW009 12 个精确路径，不扩大为整仓修改 | 每个 owned path 取得所属项目、当前字节与候选身份绑定的真实质量证据；跨项目 pytest/Ruff/Mypy 任一失败即拒绝；创建及续租使用同一有界策略；终态原子释放 lease 并 fencing 旧持有者；保留失败 Run。V04-R0 原 Work、旧 SW008 R3B Work 与新双项目联合质量 Work 均已独立 ACCEPTED，R3B 技术前置已闭合；原业务候选仍为旧字节，本门不替代 R3C/原业务验收 | A/G |
| C09-R3C | 原 VERIFYING Run 的验收权限恢复门 | C09-R3B、V04-R0 的可核验证据；原 Run 的投影、start claim、进程回收/缺失、当前租约与专门批准均经重核 | `CONTRACT/decision_package.py`、`CORE/continuity_execution_service.py`、`INFRA/continuity_store.py`、`CLI/continuity.py` 及定向测试；原 Run 与事件只读保留 | 已验收通过 (ACCEPTED)：专用 Decision `DEC-20260925-C09R3C01` 签发（SHA-256: `d05f6d0d7c922c3e873b6be0def7e2827860ad38352205293c70247975d49ab6`），恢复租约至 `antigravity:c09-verifier`（version 4），epoch/secret CAS 轮换，追加 `VERIFICATION_LEASE_RECOVERED` 事件，Work 恢复 `IN_PROGRESS`、Mission 恢复 `ACCEPTANCE_PENDING`。 | A/G |
| C09 | 第一条 Python 新需求闭环实演 | C09-R3B、C09-R3C 联合验收、C08、E08、G10；原业务 Run 沿合法续接路径完成 | 拟新增 T/e2e/test_pmf_python.py；批准的真实 Python 演练工程；保留 `CHG-SCPT-2026-012` 与原 Run | **PASS / ACCEPTED**：2026-09-25 业务验收终态成立，原 Run `SUCCEEDED`、Work/Mission `CLOSED`、CHG 实质注入、双台账零差异。原 Checkpoint 的覆盖不足永久保留；后续统一不可变候选补足完整技术质量，G10-R1 当前字节治理链闭环并由稳定入口消费，因此 C09/M1 当前验收成立，但不得倒写原 Checkpoint。 | T/A |

2026-09-25 的业务状态机验收事实保留：原业务 `RUN-PLAN-F767C11087531180` 为 `SUCCEEDED`（lease `RELEASED`），原 Work `WORK-MSN-F0564CAF05D18E0B` 与 Mission `MISSION-0648162FF0602FDD` 均为 `CLOSED`；用户验收、实质注入与台账对账记录仍有效。隔离 worktree 承载候选源码与产品改动，canonical 控制根承载唯一 Continuity Store、CHG、Decision 与台账。**2026-09-27 的统一不可变候选由 `a1c5d94` 合法派生至 `8b02de55`，补足技术质量、G10-R1 当前字节治理链及稳定入口消费；原 Checkpoint 覆盖不足仍按原样保留。M1 当前为 `COMPLETED / ACCEPTED`。M2 只能按各原子任务的显式依赖、独立实施卡与当前控制面预检推进，不从 M1 验收外推执行授权。**

2026-09-25 最终验收核对结果：

1. 原业务 Run、ExecutionIntent、投影回执、候选 HEAD（`d89b1269`）与三个 owned paths 当前字节完全匹配；候选工作树严格剔除 24 个越界脏路径。
2. R3B 联合质量证据（两项目 27 文件、六门全绿）与 V04-R0 基础合同此前均已独立 ACCEPTED；R3C 经专用 Decision `DEC-20260925-C09R3C01` 完成 CAS 租约受控恢复，Work 恢复 `IN_PROGRESS`，Mission 恢复 `ACCEPTANCE_PENDING`。
3. 当时记录 `c09-final-e2e` 候选质量门通过；2026-09-27 核对原 Checkpoint 后纠正其覆盖口径：SW009 Mypy 实际仅含生产文件，使用 `--follow-imports=skip`，未覆盖 `tests/test_services.py`，不得再称“五门完整通过、无跳过”。原候选生产与测试两文件 strict Mypy 独立复验为 172 errors / 12 files、Exit 1。
4. 成功追加内容绑定 Checkpoint `CP-SW009-PMF-C09-FINAL-001`（schema `checkpoint-evidence.v2`，quality `PASS`），并获得用户明确验收批准。
5. 通过 `PmFacadeService.accept` 将 Mission 流转至 `ACCEPTED`；通过 `PmClosureService.prepare_closure`、`inject_prepared_change_substance` 将验证与实施实质自动注入 `CHG-SCPT-2026-012`；通过 `complete_closure` 推进 Run 至 `SUCCEEDED`（lease `RELEASED`）、Work 与 Mission 推进至 `CLOSED`。
6. 工作区根入口执行 `ledger reconcile SW-2026-009` 与 `ledger reconcile SW-2026-008` 对账无差异（0 缺失、0 多余、0 不一致）。实际提交预检通过，全过程 0 次人工手写治理 JSON。

历史辅助 Run `RUN-SW008-PMF-C09-CLOSURE-003` 和 `RUN-SW008-PMF-C09R3C-007` 的 FAILED 记录只读保留作审计证据，不改写历史。稳定部署运行时回退加载 1.3.2 归属独立基础设施线 Track A，后续与 M2 推进并行或单独处置。合并、推送、部署和 release 切换仍为独立后续边界。

### 4.7 U：用户界面与 SDK（U01～U09）

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| U01 | 五状态可点击界面原型 | P06、E03、C07 | 拟新增 S/01_项目文档/prototypes/pm-flow-v2.html | 新目标、确认、执行、失败/恢复、验收五场景可达；标明演示数据；按钮/函数/导航无死链 | T/G |
| U02 | QML 输入目标生成真实草稿 | U01、P11 | QML/bridges/pm_cockpit_bridge.py、QML/views/BossCockpitView.qml、QML/boss_main.qml、T/qml/test_pm_cockpit_bridge.py、T/qml/test_boss_cockpit_view.py | Bridge→Facade 实际持久化 `PRE_AUTH` PlanningDraft；显示项目、目标、验收与“范围待规划”，不让用户填内部 ID；未形成真实范围卡前不得虚构范围，批准前不得展示为 Mission；按实施卡 016 五产品路径及独立治理证据门禁验收 | ACCEPTED / `74493c37` / `CP-SW008-M2-U02-002` |
| U03A | 批准链恢复与真实启动合同 | U02、E08 | INFRA/continuity_store.py、CORE/pm_facade_service.py、CORE/pm_cockpit_service.py；T/infrastructure/test_continuity_store.py、T/core/test_pm_facade_service.py、T/core/test_pm_cockpit_service.py | 从持久化批准链恢复精确 PlanningScopeCard；一次确认只形成一个 operation/Run；只有真实 RUN_STARTED、session/PID 后显示执行中；历史 BLOCKED Run 不污染当前 Mission；按实施卡 017 验收 | ACCEPTED / `316ab46b` / `CP-SW008-M2-U03A-002` |
| U03B | QML 一次确认与异步启动接线 | U03A | QML/bridges/pm_cockpit_bridge.py、QML/views/BossCockpitView.qml、QML/boss_main.qml；T/qml/test_pm_cockpit_bridge.py、T/qml/test_boss_cockpit_view.py | 后台调用不阻塞主线程；连点/信号重放只调用一次；busy 防重；失败解除 busy 且不显示伪接管；重载后以 canonical 快照为准；按实施卡 017 验收 | ACCEPTED / `b8010027` / `CP-SW008-M2-U03B-001` |
| U04A | 不可变执行阶段与失败归因事件合同 | U03B | CONTRACT/execution_adapter.py、CORE/continuity_execution_service.py、CORE/execution_supervisor_service.py、CORE/local_execution_orchestrator.py、INFRA/continuity_store.py；T/contracts/test_execution_adapter.py、T/core/test_continuity_execution_service.py、test_execution_supervisor_service.py、test_local_execution_orchestrator.py、T/infrastructure/test_continuity_store.py | 进度与失败步骤进入同一 canonical 哈希事件链；FAILED/PENDING/BLOCKED 只能显示结构化安全 reason code，旧事件缺失原因时明确 `LEGACY_UNKNOWN`；不得从未哈希 idempotency key、stdout/stderr 或 QML 内存猜测；不重写历史事件或数据库 schema | ACCEPTED / `d59120c7` / `CP-SW008-M2-U04A-001` |
| U04B | QML 真实活动时间线与持续刷新 | U04A | CONTRACT/pm_cockpit.py、CORE/pm_cockpit_service.py、QML/bridges/pm_cockpit_bridge.py、QML/views/BossCockpitView.qml、QML/components/ActivityTimeline.qml、QML/boss_main.qml；T/contracts/test_pm_cockpit.py、T/core/test_pm_cockpit_service.py、T/qml/test_pm_cockpit_bridge.py、T/qml/test_boss_cockpit_view.py | QRunnable＋Signal 有界持续刷新；仅显示当前 Mission/root Work/Run 的 canonical 活动；无伪百分比；失败能定位到 U04A 安全步骤；历史 BLOCKED Work 不污染当前卡片；不得修改 U05 EvidenceDrawer 或重新实现 U03A 首次启动判定 | ACCEPTED / `d200eb9b` / `CP-SW008-M2-U04B-001`；R1 `e05fafa1` |
| U05 | 恢复同一任务与证据抽屉 | U04B、E06、C03、`M2-GOV-BL02`；整改按 024 闭环并经用户验收 | QML/bridges/pm_cockpit_bridge.py、QML/components/EvidenceDrawer.qml、T/qml/test_pm_cockpit_bridge.py | 关闭重开后同 Work/Run；证据匹配当前内容；恢复动作受服务资格限制；隔离候选必须从 BL02 统一基线启动。`M2-GOV-DEP1` 是软依赖：未部署时可开发，但必须声明运行时不含 M2 产品代码，不得声称稳定运行时验收 | ACCEPTED / `ace7a959` / `CKPT-SW008-M2-U05-001` / CHG-SCPT-2026-362 completed（实际 11 路径，见 §4.7.4） |
| U06 | GUI 验收与待同步状态 | U05、C07 | QML/bridges/pm_cockpit_bridge.py、QML/views/BossCockpitView.qml、T/qml/test_boss_cockpit_view.py | 验收→投影失败→重试→完成可观测；缺必要证据不能点成“已完成” | ACCEPTED / `8b7f199a` / `CKPT-SW008-M2-U06-001` / CHG-SCPT-2026-363 completed（实际 9 路径，见 §4.7.4） |
| U07 | 薄 Cockpit SDK | C09 | 拟新增 D/auto_pm/api.py、T/core/test_cockpit_api.py；D/auto_pm/__init__.py | SDK经统一运行身份/Facade从新目标到批准、真实execute、验收落账完整实演；生产初始化不落到editable/母体；不只验import/查询 | SPLIT（V3.0.19）：按下方 U07A～U07D 四行执行并验收；本行保留为原合同 |
| U07A | 验证与验收门接线 | U06、C09 | CORE/execution_adapter_service.py、CORE/pm_facade_service.py、CONTRACT/pm_facade.py；T/core/test_execution_adapter_service.py、T/core/test_pm_facade_service.py、T/core/test_pm_run_e2e.py | 批准的范围卡一次调用完成真实执行与质量验证并到达验收门；执行或验证失败保留现场、不进入验收；技术栈解析不依赖进程当前目录；按实施卡 032 V1.1 验收 | ACCEPTED / `795fe448` / `CKPT-SW008-M2-U07A-001` / CHG-SCPT-2026-364、365 completed |
| U07B | 收尾实质接线 | U07A | CORE/pm_closure_service.py、D/auto_pm/domain/change/substance_injector.py；T/change/test_substance_control.py、T/core/test_pm_closure_service.py、T/core/test_pm_run_e2e.py | 真实链路验收后收尾由 `PENDING_SYNC` 变为 `COMPLETED`：生成的 CHG 被写入实质内容与验证结论，台账无差异；缺章节时待同步、修复后可重试；不推进 CHG 状态；按实施卡 033 验收 | ACCEPTED / `35379585` / `CKPT-SW008-M2-U07B-001` / CHG-SCPT-2026-366 completed |
| U07C | 薄 Cockpit SDK 与运行身份守卫 | U07B | D/auto_pm/api.py、D/auto_pm/__init__.py；T/core/test_cockpit_api.py | 即原 U07 的交付：SDK 经统一运行身份/Facade 从新目标到批准、真实执行、验收、收尾完整实演；每次写入前重解析运行身份，冲突或非控制根即拒绝且零写入；按实施卡 034 验收 | ACCEPTED / `9a92e9b7` / `CKPT-SW008-M2-U07C-001` / CHG-SCPT-2026-367 completed |
| U07D | GUI 开工接线 | U07C、U06 | CORE/pm_cockpit_service.py、QML/bridges/pm_cockpit_bridge.py；T/core/test_pm_cockpit_service.py、T/qml/test_pm_cockpit_bridge.py、T/qml/test_pm_cockpit_start_e2e.py | 驾驶舱对规划批准的草稿任务给出“确认开始”；开始即恢复范围卡、执行并验证，到达验收门；非预期异常不泄漏原文；无 QML 改动；按实施卡 035 验收 | ACCEPTED / `460e24f6` / `CKPT-SW008-M2-U07D-001` / CHG-SCPT-2026-368 completed |
| U08 | 旧 workflow 接口兼容 | U07 | CLI/workflow.py、拟新增 T/cli/test_workflow_compat.py | 现有命令保留；新 workflow 别名只委托 pm；不能恢复旧写入状态机；未知旧动作明确拒绝 | ACCEPTED / `d40318d0` / `CKPT-SW008-M2-U08-001` / CHG-SCPT-2026-369 completed |
| U09A | 范围卡持久化与按哈希批准 | U07A、U08（隔离基线 `d40318d0`） | INFRA/continuity_store.py、CONTRACT/pm_facade.py、CORE/pm_facade_service.py；拟新增 T/core/test_pm_pending_scope_card.py | 规范库追加范围卡表且不升 schema 版本；可提交与修订、列出待批准、列出草稿；读出即校验，记录被改动即拒绝；凭 request_id 与 plan_hash 一次完成 CHG 批准、Decision、Mission、Work，重放幂等；不启动执行；按实施卡 037 验收 | ACCEPTED / `eebdeecb` / `CKPT-SW008-M2-U09A-001` / CHG-SCPT-2026-370 completed（实际 4 路径，见 §4.7.5） |
| U09B | CLI 列出草稿与范围卡持久化 | U09A | CLI/pm.py；测试与其余确切路径以开工前勘测后的实施卡为准 | `pm` 能列出草稿与待批准范围卡；`pm plan` 经 U09A 的提交方法持久化范围卡；`pm approve` 可只凭 request_id 与 plan_hash 批准；既有参数形式保持兼容 | ACCEPTED / `cec3afa7` / `CKPT-SW008-M2-U09B-001` / CHG-SCPT-2026-371 completed（实际 4 路径，见 §4.7.5） |
| U09C | 驾驶舱展示待批准范围卡与“批准范围并开始” | U09B、U07D、U06 | CONTRACT/pm_cockpit.py、CORE/pm_cockpit_service.py、QML/bridges/pm_cockpit_bridge.py、QML/views/BossCockpitView.qml 与批准人配置项；确切路径以开工前勘测后的实施卡为准 | 驾驶舱展示 PM 起草的待批准范围卡；一个按钮完成批准并接 U07D 的开始；整条链只有“批准范围”“最终验收”两次业务决策；批准人来自配置项，未配置则拒绝，且模型身份不得充当批准人 | ACCEPTED / `3c32e8ad` / `CKPT-SW008-M2-U09C-004` / CHG-SCPT-2026-372 completed（实际 13 路径；基线为根修 `d95f45d2`；Run004，见 §4.7.5） |

U01 已于 2026-09-27 独立验收：隔离候选提交 `d88eedd5` 仅含 `S/01_项目文档/prototypes/pm-flow-v2.html` 与其静态测试；`CP-SW008-U01-001` 绑定验收前候选字节，Run `SUCCEEDED`、lease `RELEASED`、Work `CLOSED`，`CHG-HMI-2026-001` 为 `completed`。U02 已以提交 `74493c37`、`CP-SW008-M2-U02-002` 和完整治理终态独立验收。U03A 已以提交 `316ab46b`、`CP-SW008-M2-U03A-002` 验收；U03B 已以提交 `b8010027`、`CP-SW008-M2-U03B-001` 验收；U04A 已以提交 `d59120c7`、`CP-SW008-M2-U04A-001` 验收；U04B 已以产品提交 `d200eb9b`、恢复合同提交 `e05fafa1`、`CP-SW008-M2-U04B-001`、`CP-SW008-M2-U04BR1-001` 及完整治理终态验收。H11 已完成并验收；U05～U08 仍须逐项按实施卡和独立授权推进，其中 U05 必须从 BL02 统一基线启动。

**V3.0.19 补记。** U05、U06、U07A～U07D、U08 已逐项按实施卡 030～036 与独立授权完成并验收，证据见 §4.7.4；上一段“U05～U08 仍须逐项……推进”是 V3.0.16 时点的表述，予以保留。原 U07 在开工前勘测中拆为 U07A～U07D；为满足 V05“从 GUI 输入目标到验收、两次业务决策”，按用户 2026-10-01 的裁决新增 U09A～U09C，三项均为 `PLANNED / NOT_AUTHORIZED`。

**V3.0.20 补记。** U09A～U09C 已逐项按实施卡 037、039、040 与独立授权完成并验收，U01～U09 至此全部闭环；U09C 的首个 Run 在 `tests/qml` 门禁遇到间歇性原生崩溃而硬停止，其根修作为横向治理任务 `M2-GOV-QML1` 完成并验收，U09C 的隔离基线因此由 U09B 改为根修提交 `d95f45d2`。上一段“三项均为 `PLANNED / NOT_AUTHORIZED`”是 V3.0.19 时点的表述，予以保留；证据见 §4.7.5。

U01 是在现有 PySide6/QML 方案上的交互原型，不换 Web 技术栈。界面核心信息固定为：目标、当前阶段、实际执行器、下一可行动作、证据、验收；复杂内部对象默认折叠。

### 4.7.1 M2 横向治理原子任务

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 状态 |
|---|---|---|---|---|---|
| M2-BL01 | runtime-fix 与 U01 两文件形成唯一不可变集成基线 | active runtime 源 `f4626947`；`main@0d7071b7`；U01 `d88eedd5` | `02_规划/016_M2统一集成基线实施卡_PM.md` 规定的两个 U01 owned paths；独立规划卡/WBS 不进入产品提交 | 候选 `4851fce4` 精确两文件、blob 等同 U01、pytest/Ruff/Mypy Exit 0、候选入口 fail-closed、canonical runtime 无 fallback、Checkpoint 当前；Run SUCCEEDED/lease RELEASED、Work CLOSED、CHG completed | ACCEPTED / CLOSED |
| M2-GOV-IC01 | 实施卡一等合同、模板、校验与 dispatch/verify 工作流 | PM-033 V2.1；`M2-BL01` ACCEPTED | 实施卡 015 的八个产品路径；CHG-338 与 SW008 台账仅作为提交证据路径 | 33 passed；Ruff/Mypy/diff-check Exit 0；`CP-SW008-M2-GOV-IC01-003`；commit `b7bb9357` 恰含十路径；Run SUCCEEDED、Work/Mission CLOSED、CHG completed | ACCEPTED / CLOSED |
| M2-GOV-U04S01 | U03/U04 异步一次启动与 canonical 活动投影规范沉淀 | U04B ACCEPTED；Obsidian CCB 独立批准 | `00_Obsidian_Base全局规范文件仓库/02_Python开发域/216_PySide6_GUI开发规范_DEV.md`、`00_Obsidian_Base全局规范文件仓库/04_驾驶舱与全栈域/300_高级语言与工业上位机系统_Google_SRE工程可靠性规范_DEV.md`、`00_Obsidian_Base全局规范文件仓库/spec_registry.json` | 仅沉淀经 U03/U04 实测成立的一次启动、canonical 重载、后台 Signal、真实事件进度和失败降级合同；注册表校验通过；不得把项目 ID、历史事故或具体 CHG 写成全局规范 | ACCEPTED / `14650723` / `CP-SW008-M2-GOV-U04S01-001` / CHG-SPEC-2026-017 completed |
| M2-GOV-BL02 | U04B、R1/Hook 修复与 H11 发布线形成唯一统一基线 | U04B、U04B-R1、Hook 修复与 H11 合同均已验收；卡 023 | 卡 023 的 20 个修改路径与 4 个只读对照路径；不得引入 CHG/台账证据文件 | U、R、发布线差异按合同整合；冲突逐文件记录；事件兼容、pytest/Ruff/Mypy、exact-tree 与临时切换/回退演练全部通过；形成不可变提交 | COMPLETED / DELEGATED_ACCEPTED / `7cfe227e` / `CKPT-SW008-M2-GOV-BL02-002` / CHG-SCPT-2026-356、357 completed |
| M2-GOV-ADJ | 裁决合同绑定 Git Decision 字节并提供正式 CLI | `M2-GOV-BL02` ACCEPTED；卡 026 | 卡 026 的 9 个 owned paths；`adjudicate_blocked_work` 复用 `_decision_git_snapshots`；`decision create` 增加精确 `--target-work-id` 合同 | 原/裁决 Decision 均绑定恢复 Run HEAD；未跟踪、脏改、SHA/HEAD 漂移 fail-closed；CLI/API 等价与正反例全绿 | COMPLETED / DELEGATED_ACCEPTED / `d876cf98` / `CKPT-SW008-M2-GOV-ADJ-001` / CHG-SCPT-2026-358 completed |
| M2-GOV-IC02 | 实施卡在创建 Work/Run 前完成命令、测试路径、基线与范围预检 | `M2-GOV-BL02` ACCEPTED；与 ADJ 独立；卡 027 | 卡 027 的 11 个 owned paths；强制接入 `continuity work create` 前置判卷 | 未知命令、未知既有路径、baseline/scope 漂移在 Work/Run 创建前 fail-closed；历史两类问题有防复发测试 | COMPLETED / DELEGATED_ACCEPTED / `e6529115` / `CKPT-SW008-M2-GOV-IC02-001` / CHG-SCPT-2026-359 completed |
| M2-GOV-DEP1 | 把 BL02、ADJ、IC02 的整合提交构建为开发运行时 | BL02、ADJ、IC02 均 ACCEPTED；用户另行批准；卡 028 | 无产品源码 owned paths；仅受治理的 release/manifest/pointer 与报告对象 | exact-tree、身份一致性、切换与回退演练通过；失败自动回退；不等同 D07 正式稳定交付 | COMPLETED / DELEGATED_ACCEPTED / 整合 `a808fa8a`、release `1.3.3-a808fa8` / `CKPT-SW008-M2-GOV-DEP1-001`、`CKPT-SW008-M2-GOV-DEP1-002` / CHG-SCPT-2026-360、361 completed |
| M2-GOV-WBS2 | WBS 修订 2 与整改交付包 | 阶段 1～5 按 024 达成；未部署时如实记录；卡 029 | WBS 单文件与整改交付证据清单 | 回写各阶段 SHA/ID、当前时点证据、技术债与 U05 准入；Claude 阶段复查或用户明确裁决后关闭整改 | COMPLETED / ACCEPTED（复查候选 `e07f7662` 由 CHG-DOCU-2026-023 / `DEC-20260930-WBS2CAND` 形成，用户 2026-09-30 亲自验收，回执 `.auto-pm/reports/m2-gov-wbs2/first_commit_acceptance_receipt.txt`（SHA-256 `628e475452cf7d9b1c7e7734e08d609dac1559d9b28a27d6723a9f89c30b9c9d`）） |
| M2-GOV-WBS1 | WBS 修订 1：H11 终态、三线血统、治理整改任务与来源说明 | H11 COMPLETED / ACCEPTED；卡 025 | WBS 单文件 | 提交 `a385452c`（父 `58ac6a03`）仅含 WBS；CHG-DOCU-2026-022 closed；`CP-SYS001-M2-GOV-WBS1-001`；Claude 只读复查见 024 §7 | COMPLETED / CLAUDE_REVIEWED（用户批准开工；终验收的发起进程无法由 schema 证明，未记为 ACCEPTED） |
| M2-GOV-WBS3 | WBS 修订 3：U05～U08 验收回写、U07 拆分补记与 U09 新增 | U08 ACCEPTED；用户 2026-10-01 选定“先修订 WBS 再开工 U09A”；卡 038 | WBS 单文件 | 回写 U05～U08 的提交、CHG、Checkpoint；登记 U07A～U07D 与 U09A～U09C；调整 V05 依赖与 M2 范围；登记两项技术债；除卡 038 §5 列明的行外只加不删 | COMPLETED / ACCEPTED（提交 `79ab9516`；CHG-DOCU-2026-024 completed，用户 2026-10-01 在对话弹窗确认验收，Claude 代跑收口） |
| M2-GOV-QML1 | QML 测试生命周期根修（间歇性原生崩溃） | U09C 首个 Run 的 qml 门禁硬停止（失败史保留）；用户 2026-10-02 授权接手并查明根因 | QML/bridges/file_watcher_bridge.py、QML/bridges/pm_cockpit_bridge.py；T/qml/conftest.py、T/qml/test_boss_cockpit_view.py、T/qml/test_file_watcher_bridge.py、T/qml/test_pm_cockpit_bridge.py（相对 U09B 累计 6 路径） | 查明并消除后台 worker 与 GUI 对象的强引用环所致的原生崩溃：真实原生栈、真实对象环与线程轨迹、旧生产代码负向对照；窗口、Bridge、engine 有序收尾；叠加 U09C 十三文件后崩溃配置重复通过 | COMPLETED / ACCEPTED（F `6eead5e4`、F2 `d95f45d2`；`CKPT-SW008-M2-QMLLIFE-003`、`CKPT-SW008-M2-QMLLIFE-004`；CHG-SCPT-2026-373 completed，用户 2026-10-03 在对话中确认验收，Claude 代跑收口） |
| M2-GOV-WBS4 | WBS 修订 4：U09A～U09C 验收回写、QML 根修补记与技术基线校准 | U09C ACCEPTED；CHG-SCPT-2026-372、373 completed；用户 2026-10-03 批准；卡 041 | WBS 单文件 | 回写 U09A～U09C 的提交、CHG、Checkpoint；登记 `M2-GOV-QML1`；写明 M2 代码线的堆叠提交链与唯一尖端；对齐任务计数口径；沉淀教训与技术债；除卡 041 §5 列明的行外只加不删 | COMPLETED / ACCEPTED（提交 `7e2768a1`；CHG-DOCU-2026-025 completed，用户 2026-10-03 在对话中确认验收，Claude 代跑收口） |
| M2-GOV-WBS5 | WBS 修订 5：V01 验收回写与 PLC 文档与代码一致性核对任务登记 | V01 ACCEPTED；CHG-SCPT-2026-374 completed；需求说明 043 已由用户确认；用户 2026-10-03 同意写卡；卡 044 | WBS 单文件 | 回写 V01 的提交、CHG、Checkpoint、实际路径与已知限制；登记 V01B～V01D 并改 V02 依赖；更新 M2 代码线唯一尖端；沉淀教训与技术债；除卡 044 §5 列明的行外只加不删 | COMPLETED / ACCEPTED（提交 `57e14c19`；CHG-DOCU-2026-026 completed） |
| M2-GOV-TD1 | 技术债台账回写：复核 TD-SW008-001～008 并导入 WBS 圈号清单 | WBS5 ACCEPTED；V02 ACCEPTED；卡 049 | 台账单文件 | 复核 TD-SW008-001～008 的状态，导入 009 起的 WBS 圈号清单与暂存清单；旧行只改状态、不删 | COMPLETED / ACCEPTED（提交 `b6668dcf`，父 `cf6f6f33`；CHG-DOCU-2026-016 completed） |
| M2-P1 | 第 1 期：入口分类与分诊收件箱 | V03 ACCEPTED；需求说明 043；卡 051 | 14 个路径（见 §4.7.7） | 分类、收件箱、分诊记录校验、plan 分类、只读建议；用户批准时附的是有条件预授权，验收与收口由用户做出 | COMPLETED / ACCEPTED（提交 `4e165cf4`，父 `edeeead9`；CHG-SCPT-2026-379 completed） |
| M2-P1FIX | 第 1 期审计缺陷修复（A-P1-01～03、C11、C12） | M2-P1 ACCEPTED；V04 ACCEPTED；独立审计 P1/V04 报告；卡 054 | 9 个路径（5 个产品、4 个既有测试） | 分类规划成为单一的持久成功边界；已绑定重放逐项核对显式分类；文件取证必须是控制根内的普通文件；CLI 批准在写入前核对批准身份与 plan_hash；GPT 起草的卡 053 与其 CHG-SCPT-2026-381、Work `WORK-SW008-M2-P1-AUDITFIX-001`（BLOCKED）作为失败尝试保留、未处置 | COMPLETED / ACCEPTED（提交 `948884db`，父 `a6447be6`；CHG-SCPT-2026-382 completed） |
| M2-GOV-TD2 | TD2：台账登记、审计归档、需求说明与分档规则落库 | M2-P1FIX ACCEPTED；卡 055 | 17 个文档路径（含 CHG-374 §9.1 追认的两个落点） | 台账追加 TD-SW008-078～086；12 个原始文件归档并建索引；需求说明与门禁分档规则成文；F06 追认写入 CHG-374 | COMPLETED / ACCEPTED（提交 `1956dd9a`，父 `948884db`；CHG-DOCU-2026-017 completed） |
| M2-GOV-WBS6 | WBS 修订 6：V01B～V04、P1、TD1、P1 修复与 TD2 验收回写，F01 与 V05 拆分，F05 分期与新顺序 | TD2 ACCEPTED；用户 2026-10-06 同意拆卡与顺序；卡 056 | WBS 单文件 | 回写上列任务的提交、CHG、Checkpoint 与路径数；登记 F01-a、F01-b、V05-A/B/C、V04-T；更正 V03、V04 的验收口径；除卡 056 §5 列明的行外只加不删 | COMPLETED / ACCEPTED（提交 `0b56b2f4`；CHG-DOCU-2026-027 completed） |
| M2-GOV-TD3R | 技术债台账登记重启（TD-SW008-087～094） | V05-B2 ACCEPTED；卡 062（重启自 GPT 起草的卡 061，两次启动失败，其遗留对象不处置） | 台账单文件 | 追加八行：Git 子进程固定时限、卡工具身份与幂等键硬编码、V05-B2 首次尝试的失败对象、实施卡测试日期写死，以及独立审计 R2 的四项发现 | COMPLETED / ACCEPTED（提交 `769f145d`，父 `aeedf92f`；CHG-DOCU-2026-019 completed） |
| M2-GOV-TD4 | 台账状态更新（TD-SW008-081、091、092） | V05-B3 ACCEPTED；V04-T ACCEPTED；卡 066 | 台账单文件 | 逐条核对各行自己的验收条件：081、091 写已偿还，092 只写部分处置并改活动；旧列一字不改 | COMPLETED / ACCEPTED（提交 `23e6ed64`，父 `4d0b33ac`；CHG-DOCU-2026-020 completed） |
| M2-GOV-TD5 | 技术债台账追加三条（TD-SW008-095～097） | TD4 ACCEPTED；用户 2026-10-08 批准登记；卡 067 | 台账单文件 | 负载敏感测试、判卷器不在 Git、本机残留进程；只登记不处置 | COMPLETED / ACCEPTED（提交 `6a84a186`，父 `23e6ed64`；CHG-DOCU-2026-021 completed） |
| M2-GOV-TD6 | 台账同步（TD-SW008-098～102 与四行更新） | V06B ACCEPTED；卡 069 | 台账单文件 | 登记 Astra 审计 F-01 与 GPT R4 的发现；078 补 F01-a 进展，091 收窄处置说明，094 关联 F-02，096 补 V06B 进展 | COMPLETED / ACCEPTED（提交 `06f4ae4d`，父 `592211ee`；CHG-DOCU-2026-022 completed） |
| M2-GOV-WBS7 | WBS 修订 7：F01-a、V05-A/B/B2/B3、V04-T、V06 系列与台账四卡验收回写，三次审计处置，授权与新顺序，部署意图与 M3 候选 | V06D ACCEPTED；用户 2026-10-08 接受修订；卡 073 | WBS 单文件 | 回写上列任务的提交、CHG、Checkpoint 与路径数；登记新任务；除卡 073 §5 列明的行外只加不删 | COMPLETED / ACCEPTED（提交 `a538f942`，在分支 `codex/m2-gov-wbs7b`；CHG-DOCU-2026-029 completed；由 M2-GOV-WBS8 一并采纳进 M2 主链） |
| M2-GOV-RULE | 门禁规则修订：把分档与并行验证的测量结论写成规则 | 提速测量三次结果（见 §4.7.8）；用户 2026-10-08 同意提出；M2-F02 ACCEPTED | 规则文档 `02_规划/M2_门禁分档与单卡规模规则_PM.md` 单文件 | 并行 4 进程快 1.6～2.4 倍但不稳定，不无条件写入规则；按改动范围选测试，发布前再全跑；规则修订不放宽任何门禁 | COMPLETED / ACCEPTED（提交 `a0ac852b`，父 `c8d49c29`；CHG-DOCU-2026-024 completed） |
| M2-TOOL-TIER | 分档器：按精确改动路径与版本化核心清单自动定档 | M2-GOV-RULE ACCEPTED；用户 2026-10-08 同意提出 | 拟：工具文件与对应测试（范围在勘测后确定） | 未知路径或无法归类就拒绝定档并按核心档处理；产品与核心档的字节核验不降档；在空闲机器上重测最慢测试以取得可信耗时 | COMPLETED / ACCEPTED（提交 `370e0297`，父 `a0ac852b`；CHG-SCPT-2026-398 completed） |
| M2-GOV-DOCS | 文档采纳：项目关键文档按 Astra 对账草案修订并刷新到当时尖端 | M2-F02 ACCEPTED；Astra 里程碑审计的九份草案（`.auto-pm/reports/astra-milestone-audit-20261008/proposals/document_drafts/`） | 草案列明的项目文档（含 README、PM_SESSION、章程、发布门禁规范、立项表、当前基线评估与三份历史报告标注） | 保留历史验收原文与 PM_SESSION 行数约束；采纳前重核源文件指纹；文档档，跑 `tests/test_pm_session_size.py` 与文档检查 | 后移到 M3，承诺保留（用户 2026-10-09 决定：GPT 的设计不算 M2，不属 M2 收口集合；见 §4.7.9 延期承诺表）；原状态 PLANNED；**2026-10-11 已完成（卡 108）**：采纳 8 份（PM_SESSION 的那份因文件已退役不采纳），提交 `a6d5d8f3`，CHG-DOCU-2026-040 completed；相对草稿的四处有意偏离见 §4.7.14 |
| M2-B1 | 耦合治理第一步：连续性存储的三个纯哈希函数提取 | M2-F02 ACCEPTED；Astra 耦合方案 `COUPLING_REFACTOR_PLAN.md` | 拟：`continuity_store.py` 与一个新增内部模块及定向测试 | 保留既有接口、输入输出与事件 JSON 一致；不得据此宣布存储已解耦；触及核心清单，按核心档全量九组 | 后移到 M3，承诺保留（用户 2026-10-09 决定：GPT 的设计不算 M2，不属 M2 收口集合；见 §4.7.9 延期承诺表）；原状态 PLANNED；**2026-10-12 已完成（卡 116，`M3-B1`）**：提交 `c54accd4`，CHG-SCPT-2026-409 completed；三个纯函数搬进 `auto_pm/infrastructure/continuity_internal/codec.py`，Store 保留一行委托，新增 16 个测试，核心档九组严格全绿；不宣称存储已解耦，TD-SW008-055 不因此关闭 |
| M2-DEP-TECH | 开发运行时技术性部署：构建 M2 发布包并切换开发运行时（含回退演练） | V05-C、M2-DEP-INT ACCEPTED；审计包备好且 GPT 对 M2 的最终审计完成（审计发现的缺陷按冻结条款修复）；用户在审计之后另行明确批准（V3.0.24：V04-R1、V07、V08 后移到 M3，不再是前置） | 拟：发布构建与安装映射（仿 `M2-GOV-DEP1`），无产品源码改动 | 构建可复现；切换前后 active/previous 与实际加载身份一致；回退演练保留新事件；切换须用户明确批准；不等同 D07 正式交付 | COMPLETED / DELEGATED_ACCEPTED（卡 084 V1.1；CHG-SCPT-2026-400 completed；release `1.3.3-4b5c630`，`source_commit` 为 `4b5c6307`；Run `RUN-SW008-M2-DEPTECH-002` SUCCEEDED、Work CLOSED；用户 2026-10-09 授权，第一轮自动回退、第二轮成功；证据 `.auto-pm/reports/m2-dep-tech/gate_b/acceptance_receipt.txt`） |
| M2-PUSH | 以 M2 作隔离候选，一次推送 | M2-DEP-TECH ACCEPTED | 无文件改动；一次推送动作 | 推送目标、分支与范围由用户在对话中明确授权后才执行；目前没有任何推送授权；不合并 main；V3.0.26：用户已于 2026-10-09 夜在对话中明确授权，已推送，见状态列 | COMPLETED（用户 2026-10-09 授权；分支 `codex/m2-gov-wbs9-attest`，提交 `4b5c6307`，2026-10-09T20:22:07-07:00 一次性推送到 origin，新分支；未推 main、未强推、未合并 main） |
| M2-GOV-TD7 | 技术债台账同步（登记 TD-SW008-103～107，更新七条既有行） | V05-C ACCEPTED；卡 076 | 台账单文件 | 登记真实模型联验与失败记录处置中发现的问题（沙箱初始化、只读预检缺失、状态快照读写冲突、变更单没有作废状态、V05-C 已知限制）；只登记与同步，不处理债务 | COMPLETED / ACCEPTED（提交 `c8d49c29`，父 `6e17f086`；CHG-DOCU-2026-023 completed） |
| M2-N1A | 驾驶舱角色与边界说明文档入库 | 用户 2026-10-09 批准 N1a + N2-0 批次；卡 079 | 新增 `SYS-2026-001_WorkspaceGovernance/01_项目文档/40_驾驶舱角色与边界_PM.md`（1 个路径） | 只写用户已确认的内容；开头声明不改变任何现行规则、不替代 AGENTS.md；不碰 `.trae` | COMPLETED / ACCEPTED（用户 2026-10-09 验收；提交 `388b22c4`，父 `370e0297`；CHG-DOCU-2026-031 completed） |
| M2-N2-0 | 恢复与查询合同只读勘测 | 用户 2026-10-09 批准 N1a + N2-0 批次；卡 080 | 报告 `.auto-pm/reports/m2-n20/N2-0_SURVEY_REPORT.md`（SHA-256 前 8 位 `1352e908`），不改任何仓库文件 | 比较控制根检出、发布 `1.3.3-a808fa8` 与 M2 尖端三个版本；机器引用逐条核对、只读前后指纹相同 | COMPLETED / ACCEPTED（用户 2026-10-09 验收；无提交，报告 SHA-256 前 8 位 `1352e908`；CHG-DOCU-2026-025 completed） |
| M2-DEP-INT | 把发布线的 ADJ 与 IC02 整合进 M2 代码线（部署前提任务，不是债务偿还） | N2-0 报告；用户 2026-10-09 预授权 | 拟：`decision.py`、`ui/cli/continuity.py`、`continuity_store.py`、`implementation_card_*` 等发布线改过的文件及对应测试，落点以实施卡为准 | 整合后 `adjudicate_blocked_work` 与实施卡预检均可用且合同不变；M2 已有功能不回退；触及核心清单，按核心档全量九组；不以丢弃任一方改动解决冲突；门禁全过且提交等于 Checkpoint 时可代为收口 | COMPLETED（合并提交 `1d0be4af`，父 `f06c5aac` 与 `a808fa8a`；CHG-SCPT-2026-399 completed，九项门禁全过，按预授权委托收口；最终提交证明见 §4.7.10） |
| M2-GOV-WBS8 | WBS 修订 8（最小版）：采纳 V3.0.23，回写 F02 至分档器及 N1a、N2-0 的事实，写入 M2 冻结条款、剩余清单与延期承诺表，新增 M2-DEP-INT | 用户 2026-10-09 决定与预授权；卡 081 | WBS 单文件 | 除卡 081 §5 列明的行外只加不删；E 链、V04-R1 拆分、D08、N 系列等处置不写入，留给 M3 规划 | COMPLETED / ACCEPTED（用户 2026-10-09 验收；提交 `f06c5aac`，父 `388b22c4`；CHG-DOCU-2026-032 completed） |
| M2-GOV-WBS9 | WBS 修订 9（最小版）：写入 `M2-DEP-INT` 的最终提交证明（回应 GPT 最终审计 B-01），并把已验收的状态写回当前投影 | GPT 最终审计 B-01；用户 2026-10-09“选 A，今晚做”；卡 083 | WBS 单文件 | 只加 §4.7.10、一个任务行、版本记录与状态单元格；不改产品、规则、台账；D08 与冻结条款不变 | COMPLETED / ACCEPTED（用户 2026-10-09 验收；提交 `4b5c6307`，父 `1d0be4af`；CHG-DOCU-2026-033 completed；Work `WORK-SYS001-M2-GOV-WBS9-001` CLOSED） |
| M2-GOV-WBS10 | WBS 修订 10（最小版）：把卡 083 的验收、技术性部署与推送的结果写回当前投影 | 用户 2026-10-09“wbs写回”；卡 085 | WBS 单文件 | 只加 §4.7.11、一个任务行、版本记录与状态单元格；不改产品、规则、台账；D08 与冻结条款不变 | COMPLETED / ACCEPTED（用户验收；提交 `aa02be02`，父 `4b5c6307`；CHG-DOCU-2026-034 completed；Work `WORK-SYS001-M2-GOV-WBS10-001` CLOSED） |
| M2-GOV-TD8 | 技术债台账登记（TD-SW008-108～114）与既有 009/019/026 行更新 | 用户 2026-10-09 夜裁决；卡 086 | 台账单文件 | 只登记与更新台账行，不处理任何债务；登记治理记录未入库、release 标注缺失、对账不查 Git 等发现 | COMPLETED / ACCEPTED（用户验收；提交 `425f8b09`，父 `aa02be02`；CHG-DOCU-2026-026 completed；Work `WORK-SW008-M2-TD8-001` CLOSED） |
| M2-RGOV-0 | 发布治理只读盘点：CHG 冻结清单、release 清单、暴露面扫描 | 用户 2026-10-10 批准；卡 087 | 报告目录 `.auto-pm/reports/m2-rgov0/out/`（无提交） | 只读；不改任何仓库文件、不入库、不推送；输出带 SHA-256 的清单与报告 | COMPLETED / ACCEPTED（用户验收；CHG-DOCU-2026-027 completed；Work `WORK-SW008-M2-RGOV0-001` CLOSED） |
| M2-GOV-CHGIMP | 把 SW-2026-008 与 SYS-2026-001 的变更单正文与变更台账入库 | 用户 2026-10-10 批准；卡 088；TD-SW008-108 | 变更单正文与两个变更台账（共 227 个文件，其中 216 个新增、11 个修改） | 只入库既有文件，不改正文；字节清单冻结；本地分支，不推送 | COMPLETED / ACCEPTED（用户验收；提交 `5b7056d2`，父 `425f8b09`；CHG-DOCU-2026-028 completed；Work `WORK-SW008-M2-CHGIMP-001` CLOSED） |
| M2-GOV-TD9 | 技术债台账更新（108、109、111～113）并登记 TD-SW008-115～117 | 用户 2026-10-10 预授权当日排期；卡 089 | 台账单文件 | 只登记与更新台账行，不处理任何债务 | COMPLETED / ACCEPTED（提交 `6e250842`，父 `5b7056d2`；CHG-DOCU-2026-029 completed（读自变更单文件，2026-10-11）；Work `WORK-SW008-M2-TD9-001` CLOSED） |
| M2-RGOV-1 | 为 15 个已部署 release 的源码提交建立本地带注解 tag | 用户 2026-10-10 预授权当日排期；卡 090 | git 引用 `release-src/<release-id>`，无文件改动 | 只建本地 tag；不推送（含 tag）、不移动、不删除；1.2.4 的源码提交按核对结果更正 | COMPLETED / ACCEPTED（CHG-DOCU-2026-030 completed（读自变更单文件，2026-10-11）；Work `WORK-SW008-M2-RTAG-001` CLOSED） |
| M2-GOV-RANN | release 更正与标注记录（状态、可回退资格、更正） | 用户 2026-10-10 预授权当日排期；卡 091 | 新增 `00_Infrastructure/auto_pm/release_annotations.json`（1 个文件） | 只新增记录，不改任何 release 指针与 manifest；只有 previous 与已核实的历史 release 具回退资格 | COMPLETED / ACCEPTED（提交 `5c157f73`，父 `6e250842`；CHG-DOCU-2026-031 completed（读自变更单文件，2026-10-11）；Work `WORK-SW008-M2-RANN-001` CLOSED） |
| M2-GOV-RTOOL | 工具链冻结：锁定依赖清单与环境记录 | 用户 2026-10-10 预授权当日排期；卡 092 | 新增 `00_Infrastructure/auto_pm/environment/` 下 2 个文件 | 只新增记录；声明范围与实际安装版本的差异如实记录；在全新虚拟环境里核验 | COMPLETED / ACCEPTED（提交 `11a829c1`，父 `5c157f73`；CHG-DOCU-2026-032 completed（读自变更单文件，2026-10-11）；Work `WORK-SW008-M2-RTOOL-001` CLOSED） |
| M2-GOV-GIGN | .gitignore 补洞（压缩包与备份包规则） | 用户 2026-10-10 预授权当日排期；卡 094；TD-SW008-115 | `.gitignore` 末尾追加一段（1 个文件） | 只追加；不移出任何已跟踪文件；规则只拦以后的新文件 | COMPLETED / ACCEPTED（提交 `8cb8dceb`，父 `11a829c1`；CHG-DOCU-2026-033 completed（读自变更单文件，2026-10-11）；Work `WORK-SW008-M2-GIGN-001` CLOSED） |
| M2-GOV-TRK | 变更单入库检查工具（对账看不见的“文件在盘上但不在提交里”） | 用户 2026-10-10 预授权当日排期；卡 093；TD-SW008-113 | 新增 `tests/tools/chg_tracking_check.py` 与 `tests/e2e/test_pmf_chg_tracking_check.py`（测试档，2 个文件） | 只读检查，不写仓库；不接入任何门禁；不入库任何变更单 | COMPLETED / ACCEPTED（提交 `7506af72`，父 `8cb8dceb`；CHG-SCPT-2026-401 completed（读自变更单文件，2026-10-11）；Work `WORK-SW008-M2-TRK-001` CLOSED） |
| M2-GOV-WBS11 | WBS 修订 11（最小版）：把发布治理整顿批次的结果与历史队列核对写回当前投影 | 用户 2026-10-10 预授权当日排期；卡 095 | WBS 单文件 | 只加 §4.7.12、十个任务行、版本记录与状态单元格；不改产品、规则、台账；D08 与冻结条款不变；不替用户验收任何变更单 | COMPLETED / ACCEPTED（提交 `657f3dc5`，父 `7506af72`；SYS-2026-001 的 CHG-DOCU-2026-035 completed（读自变更单文件，2026-10-11）；Work `WORK-SYS001-M2-GOV-WBS11-001` CLOSED；该提交在兄弟分支上，经卡 100 并入本地线） |
| M2-GOV-CHGSYNC | 把卡 088 之后新产生的变更单正文与两个变更台账补入库（SW-2026-008 的 10 个与 SYS-2026-001 的 1 个 CHG，13 个文件） | 用户 2026-10-10 选方案 A、2026-10-11 批准；卡 099；TD-SW008-108 | 变更单正文 11 个与两个变更台账 | 只入库本地分支；SW-2026-009 与 PLC 项目的变更单不在其中；不推送 | COMPLETED / ACCEPTED（提交 `fea74b33`，父 `0d22fdd0`；CHG-DOCU-2026-036 completed；Work `WORK-SW008-M2-CHGSYNC-001` CLOSED；用户验收） |
| M2-GOV-MRG1 | 把兄弟分支（卡 093 的检查工具、卡 095 的 WBS V3.0.27）本地合并进主线 | 用户 2026-10-11 批准 V1.1；卡 100 | 3 个文件（2 个新增测试、WBS 一处修改） | `git merge --no-ff`，不手改；V1.0 因 rest 组一个瞬时竞态测试在 G2 失败而作废（TD-SW008-120），V1.1 加一条具名、有证据的容忍规则；不推送 | COMPLETED / ACCEPTED（合并提交 `bf19b6bd`，父 `fea74b33` 与 `657f3dc5`，树 `7addde99`；CHG-SCPT-2026-403 completed；Work `WORK-SW008-M2-MRG1-002` CLOSED；用户验收） |
| M2-GOV-Q01 | 实现 WBS 任务 Q01：两个真实 vartable 样例入库（嵌套 .gitignore 与 .gitattributes） | 用户 2026-10-10 裁决补样本、2026-10-11 批准并委托验收；卡 101；TD-SW008-054 | `tests/vartable/samples/` 下 4 个新增文件 | 样例与已入库的 00_Infrastructure 副本逐字节相同；不改项目 .gitignore 与仓库根 .gitattributes；不改任何测试或产品代码 | COMPLETED / ACCEPTED（提交 `853fc651`，父 `bf19b6bd`；CHG-SCPT-2026-404 completed；Work `WORK-SW008-M2-Q01-001` CLOSED；用户委托验收；rest 组 1 failed / 854 passed / 13 skipped） |
| M2-GOV-ERRA | 为 CHG-SCPT-2026-195 §10.1 第 2 项追加勘误（QPrinter 并未替换为 QPdfWriter） | 用户 2026-10-10 接受分诊结论、2026-10-11 批准并委托验收；卡 102；TD-SW008-001/061 | 新增 `04_监控/01_变更管理/03_勘误/ERR-SCPT-2026-195-01.md`（1 个文件） | 只追加文件，不改变更单原文、不改代码与测试 | COMPLETED / ACCEPTED（提交 `9f952044`，父 `853fc651`；CHG-DOCU-2026-037 completed；Work `WORK-SW008-M2-ERRA-001` CLOSED；用户委托验收） |
| M2-GOV-TD11 | 技术债台账同步：卡 099～102 的事实写回，新登记 TD-SW008-120 与 121 | 用户 2026-10-11 批准并委托验收；卡 103；TD-SW008-118 | 台账单文件 | 只追加进展与新登记，不改任何已有债务的状态、不删行 | COMPLETED / ACCEPTED（提交 `dbf7d031`，父 `9f952044`；CHG-DOCU-2026-038 completed；Work `WORK-SW008-M2-TD11-001` CLOSED；用户委托验收） |
| M2-GOV-WBS12 | WBS 修订 12（V3.0.28）：写入 M2 里程碑验收、M3 启动、卡 099～103 批次记录、Q 队列证据与波次 4 瘦身的落字 | 用户 2026-10-11 宣布 M2 验收并预授权当日排期；卡 104 | WBS 单文件 | 只加 §4.7.13、七个任务行、版本记录与当前产品状态段，并更新卡 089～095 与投影的状态单元格；D 阶段各行原文、D08、冻结条款与延期承诺表不变；不替用户宣布任何未宣布的验收 | COMPLETED / ACCEPTED（提交 `9655382d`；CHG-DOCU-2026-036 completed（读自变更单文件，2026-10-11）；Work `WORK-SYS001-M2-GOV-WBS12-001` CLOSED） |
| M2-GOV-TD12 | 技术债台账状态翻转：TD-SW008-001 与 061 标已偿还，并为 TD-SW008-002 追加 2026-10-11 的 Mypy 实测 | 用户 2026-10-11 预授权当日排期；卡 105 | 台账单文件 | 只翻转两条已满足验收条件的债务的状态并追加事实；不处置其他债务 | COMPLETED / ACCEPTED（提交 `741ed045`，父 `9655382d`；CHG-DOCU-2026-039 completed（读自变更单文件，2026-10-11）；Work `WORK-SW008-M2-TD12-001` CLOSED） |
| M2-GOV-CIBASE | 刷新 Linux CI 基线：去掉 Q01 类别与 14 个 id（卡 101 入库样例后它们在干净检出里通过，比较脚本把过期基线判为 FAIL） | 用户 2026-10-11 “先做CI基线小卡，做完再推送”；卡 106 | `tests/tools/sw008_ci/baseline.linux.json`（1 个文件） | 只改这一个数据文件；不改测试、产品、工作流；不重测 Linux | COMPLETED / ACCEPTED（提交 `620e7597`，父 `741ed045`；CHG-SCPT-2026-405 completed；Work `WORK-SW008-M2-CIBASE-001` CLOSED；已推送，CI 第 4 次运行 success） |
| M3-A1 | 合并三项小修复：D01 指引文件修正、TD-SW008-042 的条件断言、Q03 的 mypy 重名中止 | 用户 2026-10-11 预授权当日排期（D01、TD-SW008-042、Q03）；卡 107 | AGENTS.md、两个薄适配入口、操作手册 36、`tests/qml/test_file_watcher_bridge.py`、`pyproject.toml`（6 个文件） | 核心档（入口文件按未知路径判核心）；九组回归 + 真实变异；不改产品代码 | COMPLETED / ACCEPTED（提交 `eca0fab8`，父 `620e7597`；CHG-SCPT-2026-406 completed；Work `WORK-SW008-M3-A1-001` CLOSED） |
| M3-DOCS | 采纳 2026-10-08 审计的文档修订草案（8 份；PM_SESSION 的那份不采纳） | 用户 2026-10-11 预授权（M2-GOV-DOCS）；卡 108 | README、章程、发布门禁规范、立项表、当前基线评估、项目总结报告、验收核验报告、测试策略与验收规程（8 个文件） | 只加时点边界横幅并把 PM_SESSION 单一真源的旧提法改为已退役的历史摘要；历史事实与数字保留 | COMPLETED / ACCEPTED（提交 `a6d5d8f3`，父 `eca0fab8`；CHG-DOCU-2026-040 completed；Work `WORK-SW008-M3-DOCS-001` CLOSED） |
| M3-TD13 | 技术债台账回写：042、054 已偿还，002 追加 Q03 结果，新登记 TD-SW008-122、123、124 | 用户 2026-10-11 预授权；卡 109 | 台账单文件 | 只翻转已满足验收条件的债务并追加事实；不删行；不处置其他债务 | COMPLETED / ACCEPTED（提交 `31bed234`，父 `a6d5d8f3`；CHG-DOCU-2026-041 completed；Work `WORK-SW008-M3-TD13-001` CLOSED） |
| M3-WBS13 | WBS 修订 13（V3.0.29）：登记第二批（卡 105～110）、推送与 CI 结果、Q02 关闭与 Q03 结论、D01 与 M2-GOV-DOCS 完成 | 用户 2026-10-11 预授权当日排期；卡 110 | WBS 单文件 | 只加 §4.7.14、五个任务行、版本记录与当前产品状态段，并更新投影与五个已有任务行的状态单元格；D 阶段各行原文、D08、冻结条款不变 | COMPLETED / ACCEPTED（提交 `e61c4fa9`；CHG-DOCU-2026-037 completed（SYS-2026-001，读自变更单文件，2026-10-11）；Work `WORK-SYS001-M3-WBS13-001` CLOSED；已推送） |
| M3-CIBASE2 | 再刷新 Linux CI 基线：去掉已修好的夹具健康测试的 id 与其类别（21 → 20 个 id） | 卡 107 修好 TD-SW008-042 后，CI 第 5 次运行（`e61c4fa9`）在基线比较一步失败（基线过期）；用户 2026-10-11 “推送卡111”；卡 111 | `tests/tools/sw008_ci/baseline.linux.json`（1 个文件） | 只改这一个数据文件；不改测试、产品、工作流；教训：修复基线里登记的测试时必须在同一张卡里同步刷新基线 | COMPLETED / ACCEPTED（提交 `07709559`，父 `e61c4fa9`；CHG-SCPT-2026-407 completed；Work `WORK-SW008-M3-CIBASE2-001` CLOSED；已推送，CI 第 6 次运行 success） |
| M3-RACE | 连续性存储边车路径检查在并发写入下不再瞬时失败（TD-SW008-120、077） | 用户 2026-10-11 批准补行；TD-SW008-120、077；卡 100 V1.1 的具名容忍规则 | 拟：`D/auto_pm/infrastructure/` 下连续性存储的边车路径检查及 `T/e2e/test_pmf_recovery.py`（精确路径由实施卡前的只读勘测确定，不在此处预设） | 并发读写下读者不再出现“路径必须是唯一链接的普通文件”的瞬时报错，或把该测试改成对竞态确定的断言，并有负向测试；rest 组连续多次运行无偶发失败；卡 100 V1.1 的具名容忍规则不再被需要；核心档：九组回归、真实变异，建议引入独立审计；不得以放宽断言或重跑洗绿 | COMPLETED / ACCEPTED（提交 `ef3c13af`，父 `ba0ef3e9`；CHG-SCPT-2026-408 completed；Work `WORK-SW008-M3-RACE-001` CLOSED；核心档九组严格全绿未用容忍规则；TD-SW008-120 改为待复核——观察期条件未满足不标已偿还） |
| M3-CF | 博图/InoProShop 编译报错的结构化反馈通道 | 用户 2026-10-10 排序的业务缺口 ②；用户 2026-10-11 批准补行 | 拟新增一个解析模块与定向测试（精确路径由实施卡前的勘测确定）；不改 O 正式规范 | 给定用户贴入的真实报错文本，解析为（文件、行、错误码、消息）的结构化记录并绑定当前 Work/Checkpoint；坏输入与无法解析的行明确拒绝而不是静默忽略；不宣称 TIA/InoProShop 编译，编译与导入仍由用户执行；**需要用户提供 1～2 份真实报错文本样本** | PLANNED（实施卡未出；等待样本） |
| M3-FIG | 图与文档一致性检查（Mermaid 可解析、与接口表/变量表对照） | 用户 2026-10-10 排序的业务缺口 ③；用户 2026-10-11 批准补行 | 拟新增一个检查脚本与定向测试，接入 `doc check` 之外的独立入口（精确路径由实施卡前的勘测确定）；不改 O 正式规范 | 对故意制造的不一致样例（图中信号不在接口表、变量表缺项）报告具体位置，对一致的样例通过；纯文档与脚本，不改正式规范与既有文档内容；不据此宣称仿真或联调 | PLANNED（实施卡未出） |
| M3-INV | 仓库只读盘点：文档与资产的权威性、归属与引用清单（零移动、零删除、零覆盖） | 2026-10-11 外部审计简报（见 §4.7.15）；与 M2-GOV-DOCS、D01 去重 | `R/` 下的盘点报告与人工裁决表；不改仓库文件 | 以固定提交为基线生成机器可复核的文件清单与分类（现行/规范/实施记录/候选稿/历史归档/重复待裁决），标出归属、引用方、建议动作与不确定项；输出只读；不确定项列给用户，不自行裁决 | PLANNED / QUEUED / NOT_AUTHORIZED（排队，不是授权；位置：M3 功能任务之后、D03 冻结之前，用户可提前） |
| M3-REPOGOV | 仓库治理批次：权威标注、链接与路径修复、有限合并/归档、必要的目录移动与防回归规则 | `M3-INV` 的裁决表；用户裁决 | 由 `M3-INV` 的裁决表逐批列出精确路径白名单 | 按类别小批次，每批有路径白名单、引用扫描、内容校验、测试与回退点；不删除历史治理证据与用户保留对象；以证据关闭（无未裁决冲突、链接/路径检查结果明确、归属例外清单），不以清理提交数量为成功指标 | PLANNED / QUEUED / NOT_AUTHORIZED（范围与时机需用户裁决） |
| M3-MAIN | main 集成策略决策（文档与方案卡，不实施） | D03 的前置决策；2026-10-11 外部审计简报 | 方案文档；不改分支、不合并、不推送 | 比较“把活跃分支快进为 main”与“治理及 D03 冻结后择取/重建最终提交集合再集成”，说明 Git 历史、已部署运行时、CI 触发条件（现 workflow 对 main 的 push 不触发）、治理账本与回退影响；当前事实：`origin/main`=`e83c117d`，活跃分支领先 107 个提交、涉及 472 个路径；决策权在用户 | PLANNED / QUEUED / NOT_AUTHORIZED |
| M3-WBS14 | WBS 修订 14（V3.0.30）：登记卡 111 与 CI 结果、用户批准的三个任务行与排队的仓库治理项 | 用户 2026-10-11 “批准补三个任务行，出卡”；卡 112 | WBS 单文件 | 只加 §4.7.15、八个任务行、版本记录与当前产品状态段，并更新投影与 `M3-WBS13` 的状态单元格；D 阶段各行原文、D08、冻结条款不变 | COMPLETED / ACCEPTED（提交 `5cd57f8b`；CHG-DOCU-2026-038 completed（SYS-2026-001，读自变更单文件，2026-10-12）；Work `WORK-SYS001-M3-WBS14-001` CLOSED；卡 112 的提交随卡 113 与卡 114 一并推送） |
| M3-TD14 | 技术债台账回写：登记 TD-SW008-125（修复基线内测试须同卡刷新 CI 基线）、126（残留目录壳与 Temp 下的工作树）、127（卡的工作树与分支收口后没有回收） | 2026-10-11 CI 第 5 次失败的教训与仓库清理；用户 2026-10-12 批准当日排期；卡 113 | 台账单文件 | 只加三行与四个 §3 证据行，不改已有债务状态、不删行 | COMPLETED / ACCEPTED（提交 `3ac045f1`，父 `5cd57f8b`；CHG-DOCU-2026-042 completed；Work `WORK-SW008-M3-TD14-001` CLOSED） |
| M3-ROOT | 控制根对齐集成线：让控制根检出的 `AGENTS.md`、WBS 与规则文件是现行版本，运行时（release 指针、`continuity.db`、Decision JSON）一字不动 | 用户 2026-10-11 同意补行并同意在 `M3-RACE` 之前做；方案 `.auto-pm/reports/M3_ROOT_ALIGN_PLAN_20261012.md`（只读冲突清单：215 个未跟踪副本字节相同、8 个冲突文件、70 个只在旧分支跟踪的文件） | 控制根工作区；新建分支 `codex/control-root-20261012`；备份目录 `My_Workspace_backups\root-align-20261012` | 先存后切：切换前备份 4 + 70 + 8 个文件与状态、补丁；验证门：`AGENTS.md` 与目标逐字节相同、3 个 release 指针与 `continuity.db` 的 sha256 切换前后相同、`main.py --version` 仍为 1.3.3-4b5c630、两项目台账对账 0/0/0、`pm resume` 的冲突与候选逐项相同；任一不过即回退（旧分支原样保留）；不改 release 载荷与 Hook；不合并 main | COMPLETED / ACCEPTED（2026-10-12 用户确认后执行：控制根现为 `codex/control-root-20261012`（`ba0ef3e9`），12 项验证门全部通过，旧分支原样保留；执行日志 `.auto-pm/reports/m3-root/exec_log.jsonl`，备份 `My_Workspace_backups\root-align-20261012`；无提交，不属任何卡的提交集合） |
| M3-HYG | 分支与工作树收敛：存量清理（已做）、归档分支与工作树的处置、残留目录壳、收口后自动回收（增量） | 用户 2026-10-11 同意补行并批准步骤 1～4；核对清单 `.auto-pm/reports/M3_HYG_CHECKLIST_20261011.md`；TD-SW008-126、127 | 本地分支引用、`git worktree` 登记与 `.auto-pm/worktrees` 下的目录；备份 `C:\Users\fubai\Documents\My_Workspace_backups\hyg-20261011`；不动提交、不动治理库 | 存量（2026-10-11 与 2026-10-12 已完成）：2026-10-11 步骤 1～4（干净工作树 116 个与有改动的 31 个移除、分支 152 个删除）；2026-10-12 A5：50 个有独有提交的工作树存补丁后移除、41 个归档分支名删除；登记的工作树 228 → 19、分支 206 → 19、归档引用 59 个，对账 0/0/0、`pm resume` 逐项相同。剩余：仍被检出的 11 个旧分支（其中 4 个绑着存活 Run，不动）、约 17 个带外来权限的残留目录壳（需管理员权限，我不改权限）、卡工厂收口后自动回收（TD-SW008-127 的增量部分） | IN_PROGRESS（存量部分 COMPLETED，剩余部分 PLANNED） |
| M3-WBS15 | WBS 修订 15（V3.0.31）：登记卡 113、仓库卫生清理的结果与 `M3-ROOT`、`M3-HYG` 任务行 | 用户 2026-10-12 “批准，截止17:00，推送一并授权”；卡 114 | WBS 单文件 | 只加 §4.7.16、四个任务行、版本记录与当前产品状态段，并更新投影与 `M3-WBS14` 的状态单元格；D 阶段各行原文、D08、冻结条款不变 | COMPLETED / ACCEPTED（提交 `ba0ef3e9`；CHG-DOCU-2026-039 completed（SYS-2026-001，读自变更单文件，2026-10-12）；Work `WORK-SYS001-M3-WBS15-001` CLOSED；已推送，CI 第 7 次 success） |
| M3-TD15 | 技术债台账回写：TD-SW008-120 改为待复核、为 077、055、108、123、127 追加进展、登记 TD-SW008-128 | 用户 2026-10-12 预授权当日排期；卡 117 | 台账单文件 | 只加进展与新行并翻转一条状态到待复核，不改验收条件、不删行 | COMPLETED / ACCEPTED（提交 `37a4a6a5`，父 `c54accd4`；CHG-DOCU-2026-043 completed；Work `WORK-SW008-M3-TD15-001` CLOSED） |
| M3-WBS16 | WBS 修订 16（V3.0.32）：登记卡 115～117、控制根对齐与卫生清理的收尾，更正过时的清理数字 | 用户 2026-10-12 预授权当日排期；卡 118 | WBS 单文件 | 只加 §4.7.17、两个任务行、版本记录与当前产品状态段，并更新投影与五个已有任务行的状态单元格；D 阶段各行原文、D08、冻结条款不变 | COMPLETED / ACCEPTED（提交 `098e2bf6`；CHG-DOCU-2026-040 completed（SYS-2026-001，读自变更单文件，2026-10-12）；Work `WORK-SYS001-M3-WBS16-001` CLOSED；已推送，CI 第 8 次 success） |
| M3-CS2 | 变更单补入库：SW-2026-008 的 16 个与 SYS-2026-001 的 5 个新变更单（LF 规范化）与两个活台账入库 | 用户 2026-10-12 预授权当日排期与夜间窗口；卡 119（产品档，因分档器把变更单目录判为运行时数据） | 23 个路径（新变更单与两个台账） | 不改任何产品字节（四棵树逐字节核对）、不丢基线台账行 ID、九组回归与基线逐项相同；不含 SW-2026-009 与 PLC 项目的变更单 | COMPLETED / ACCEPTED（提交 `4f855e04`，父 `7e926f4f`；CHG-DOCU-2026-044 completed；Work `WORK-SW008-M3-CS2-001` CLOSED；rest 组 869 passed, 13 skipped、core 组 1142 passed, 1 skipped，未使用容忍规则） |
| M3-V07 | Python 模板验证（WBS 任务 V07 的测试部分） | 用户 2026-10-12 预授权当日排期；卡 120（测试档） | 新增 1 个测试文件 | 只新增 `tests/e2e/test_pmf_template_python.py`；不改产品与模板字节；“从基准提取模板”未做（见 V07 行） | COMPLETED / ACCEPTED（提交 `7e926f4f`，父 `098e2bf6`；CHG-SCPT-2026-410 completed；Work `WORK-SW008-M3-V07-001` CLOSED；rest 组 869 passed, 13 skipped，未使用容忍规则） |
| M3-TD16 | 技术债台账回写：为 108、120 追加进展，登记 TD-SW008-129、130、131 | 用户 2026-10-12 睡前允许夜里接着做台账与 WBS 文档卡；卡 121 | 台账单文件 | 只加进展与新行、不改验收条件、不删行；129 需用户裁决 | COMPLETED / ACCEPTED（提交 `c1b08fc1`，父 `4f855e04`；CHG-DOCU-2026-045 completed） |
| M3-WBS17 | WBS 修订 17（V3.0.33）：登记卡 119～121、V07 行状态与 V08 勘测 | 用户 2026-10-12 睡前允许夜里接着做文档卡；卡 122 | WBS 单文件 | 只加 §4.7.18、四个任务行、版本记录与当前产品状态段，并更新投影与 V07、V08、M3-WBS16 行；D 阶段各行原文、D08、冻结条款不变 | COMPLETED / ACCEPTED（提交 `c8a4f689`；CHG-DOCU-2026-041 completed（SYS-2026-001，读自变更单文件，2026-10-13）；Work `WORK-SYS001-M3-WBS17-001` CLOSED；已推送，CI 第 9 次 success） |
| M3-TPL1 | PLC 模板修复：让 `plc-standard-project` 生成的项目通过插件命令行 `check` 与 `test` | 用户 2026-10-13 “同意按这个方案做，先出修模板那张卡”并批准；卡 124（产品档，`templates/` 命中 PRODUCT-TEMPLATES） | 4 个模板文件 | 只改 FB_1001（`VAR CONSTANT`）、FB_2001（复位输出回写）与两个 `.scltest`；不改产品与规范库；修前 17 个错误、退出码 1，修后 0、退出码 0 | COMPLETED / ACCEPTED（提交 `b5d3e552`，父 `dcfca387`；CHG-SCPT-2026-412 completed；Work `WORK-SW008-M3-TPL1-001` CLOSED；rest 组 888 passed, 13 skipped、core 组 1142 passed, 1 skipped；插件 2.17.2，二进制 SHA-256 前 16 位 690f0c6923509564） |
| M3-TD17 | 技术债台账回写：129 重新定性、131 并入接口文档副本，登记 TD-SW008-132（DJ-2026-005，有意保留）、133（SysLib 31 处未解析引用） | 用户 2026-10-13 “登记为债务，等WBS全部完工后，用于测试驾驶舱功能”；卡 125 | 台账单文件 | 只加进展与新行、不改验收条件、不删行、不改 DJ-2026-005 | COMPLETED / ACCEPTED（提交 `d6d382ff`，父 `b5d3e552`；CHG-DOCU-2026-046 completed） |
| M3-PLUGIN | 把 Siemens 语言服务插件的命令行 `check`、`test` 接入驾驶舱 `plc check` 与阶段门禁，并收紧 V08 测试 | 用户 2026-10-13 “同意按这个方案做”；TD-SW008-129；卡 127（产品档） | `auto_pm` 的 PLC 检查器与阶段门禁、测试 | 找不到插件为“未验证”、交付阶段为失败；记录插件版本与二进制 SHA-256；二进制只在本机调用、不入库不入 CI；驾驶舱只保留一小段插件漏掉的结构检查（空文件、乱码单文件）；“变量文档缺失”在 `plc check` 为警告、到交付阶段升失败（用户已同意） | PLANNED（卡 127 今天出，正式门禁后推送） |
| M3-WBS18 | WBS 修订 18（V3.0.34）：登记卡 123～125、插件发现、用户裁决与今日计划 | 用户 2026-10-13 “规划今天的任务，wbs还剩哪些任务”；卡 126 | WBS 单文件 | 只加 §4.7.19、四个任务行、版本记录与当前产品状态段，并更新投影与 V07、V08、M3-WBS17 行；D 阶段各行原文、D08、冻结条款不变 | 本卡自身（状态以其 Work 与变更单为准） |

产品代码范围与提交治理证据必须分层表达。实施卡建立本身不等于验收；最终仍须新的 Decision、有效 Work/Run、当前字节 Checkpoint、正常 Git Hook 本地提交及合法治理终态。

#### 4.7.2 治理时点、三线血统与来源说明（2026-09-29）

**当前时点证据。** 于主工作区 HEAD `58ac6a03a886832588e8adc6d81c16453ac8b25a`、本地时间 `2026-09-29T19:44:46-07:00` 只读采集：canonical 事件 2566 条、前后哈希断裂 0；`WORK_ADJUDICATED` 14 条且对应 14 个 Work 全部 `CANCELLED`；`RUN_LEGACY_LEASE_FENCED` 5 条；SW008 Work 状态仅有 `ACCEPTED/CANCELLED/CLOSED`，无 `BLOCKED`；`pm resume SW-2026-008 --json` 无候选和冲突；SW008 台账 0 缺失、0 孤儿、0 状态不一致。CHG-SCPT 状态精确统计为 approved 33、implementing 15、pending_acceptance 10、draft 4、completed 97、closed 28；按非终态口径未关闭 62 条。active release 为 `1.3.3-0b72499`，previous 为 `1.3.3-e648e0b`，configured/effective/load path 一致且无 fallback。

**署名与来源。** `fubai` 与 `baiyang` 是同一用户的等权署名。CHG-347～354 的文件编制字段为 Claude，审批字段为用户等权署名 `baiyang`；CHG-355 的编制与审批字段均为 `baiyang`。根据用户 2026-09-29 的明确确认，CHG-354/355 最终收口、H11C 执行 CHG-355，以及 `DEC-20260929-H11CFENC`、`DEC-20260929-H11CADJD` 的创建与批准由用户亲手执行；其余 Claude 写入均源自对话授权。现有 CHG/Decision schema 不单独记录命令发起进程，故本段同时引用文件字段与用户确认，不以署名等价掩盖 Agent 写入来源。

| 血统 | 冻结点 | 当前事实 |
|---|---|---|
| U 线 | `d200eb9b` | U04B 驾驶舱活动时间线，10 个产品路径 |
| R 线 | `70d7e093`（父提交 `e05fafa1`） | 终态 lease reconcile + Hook 双根修复，共 11 个路径 |
| 发布线 | `0b724997`（经 `e648e0b4`） | H11A/H11C 行政裁决与旧终态 lease 围栏，去重后 10 个路径 |

验证方法为 `git rev-parse`、`git merge-base`、`git merge-tree` 与逐提交 `git diff --name-only`（2026-09-29）：U 线与 R 线代码合并无冲突，仅治理台账冲突；继续并入发布线时，产品代码冲突集中在 `continuity_execution_service.py`、`decision_package.py`、`continuity.py`、`test_continuity_store.py` 四个文件，`continuity_store.py` 可文本自动合并但仍需语义验收。实施卡工具只在 M2 线；发布线独有 `work adjudicate`、`adjudication-evidence`、`run fence-legacy-terminal`、`legacy-terminal-evidence` 四个命令，M2 线独有 `run reconcile-terminal-lease` 与五个 `implementation-card` 命令。

**开发运行时切换政策。** M2 期间任何开发运行时切换必须使用独立 CHG、Decision、exact-tree 校验、身份一致性核验及切换/回退演练；D07 仍是唯一正式稳定交付边界。2026-09-29 已受控切换 `1.3.3-8f08c1a`、`1.3.3-e648e0b`、`1.3.3-0b72499`；这些开发运行时不自动授权下一次部署，也不把候选验收外推为 main 合并或正式发布。

#### 4.7.3 整改阶段最终证据与技术债登记（V3.0.17，2026-09-30）

本节由 `M2-GOV-WBS2`（卡 029 V0.4）追加，只加不删；V3.0.16 及更早的文字保留，§4.7.1 表仅修改各行状态单元格。所有数字均在 2026-09-30T15:35:07-07:00 重新采集（命令见下表“采集方法”），与 2026-09-29 的“当时值”并列，不沿用旧数字。完整交付包（精确 diff、原始命令与 Exit Code、提交关系图、控制面终态、技术债、GPT 原始要求、偏差与风险）位于 `.auto-pm/reports/m2-gov-wbs2/M2_GOV_DELIVERY_PACKAGE.md`。

**整改阶段最终证据。**

| 阶段 | 卡 | 不可变提交 / 产物 | CHG / Decision | Run / Work / Checkpoint | 门禁结果摘要 |
|---|---|---|---|---|---|
| 1 WBS 修订 1 | 025 | `a385452c`（父 `58ac6a03`） | CHG-DOCU-2026-022 closed；`DEC-20260929-WBS10001` | RUN/WORK-SYS001-M2-GOV-WBS1-001 SUCCEEDED/CLOSED；`CP-SYS001-M2-GOV-WBS1-001` | 仅 WBS 单文件；G1～G5（见 024 §7） |
| 2 BL02 统一基线 | 023 V0.4 | `7cfe227e`（经 `e8d9b3e5`、`4e08b0dd`） | CHG-SCPT-2026-356、357 completed；`DEC-20260929-BL02CODE`、`DEC-20260930-BL02RSET` | Run 002 SUCCEEDED（001 CANCELLED 保留）、Work CLOSED；`CKPT-SW008-M2-GOV-BL02-002` | G1 `PASS_WITH_BASELINE_EXCEPTION`（E-G1-1/2/3、E-G3-1），G2/G4/G5/G6 PASS，G3 `PASS_WITH_BASELINE_EXCEPTION` |
| 3 ADJ（R1） | 026 V0.3 | `d876cf98`（父 `7cfe227e`，9 路径） | CHG-SCPT-2026-358 completed；`DEC-20260930-ADJCODE0` | RUN/WORK-SW008-M2-GOV-ADJ-001 SUCCEEDED/CLOSED；`CKPT-SW008-M2-GOV-ADJ-001` | G1 `PASS_WITH_BASELINE_EXCEPTION`（1204 passed），G2～G6 PASS |
| 4 IC02（R2） | 027 V0.4 | `e6529115`（父 `7cfe227e`，11 路径） | CHG-SCPT-2026-359 completed；`DEC-20260930-IC02CODE` | RUN/WORK-SW008-M2-GOV-IC02-001 SUCCEEDED/CLOSED；`CKPT-SW008-M2-GOV-IC02-001` | G1～G7 全 PASS（1197 passed） |
| 5A DEP1 Gate A | 028 V0.2/V0.3 | 整合 `a808fa8a`（父 `7cfe227e`、`d876cf98`、`e6529115`） | CHG-SCPT-2026-360 completed；`DEC-20260930-DEP1INTG` | RUN/WORK-SW008-M2-GOV-DEP1-001 SUCCEEDED/CLOSED；`CKPT-SW008-M2-GOV-DEP1-001` | 并集回归 1458/1458 有结果、0 失败；两次构建逐文件一致；临时切换/回退演练通过 |
| 5B DEP1 Gate B | 028 V0.3 | release `1.3.3-a808fa8`（无源码提交） | CHG-SCPT-2026-361 completed；`DEC-20260930-DEP1DPLY` | RUN/WORK-SW008-M2-GOV-DEP1-002 SUCCEEDED/CLOSED；`CKPT-SW008-M2-GOV-DEP1-002` | 切换后核验全部通过（identity 无 fallback、新命令可用、V0.3 预检 exit 0、台账 0/0/0、证据命令 19/19、事件链 0 断裂、三个 release exact-tree） |

**验收状态口径。** `DELEGATED_ACCEPTED` 表示批准与验收由 Claude 依用户 2026-09-30 的对话授权以委托方式执行（CHG 批准/验证结论文件带“委托执行”标记），证据齐备，但**用户本人尚未逐阶段亲自验收**，故不记为 `ACCEPTED`。阶段 1 的批准文件无委托标记，终验收发起进程无法由现有 schema 证明，记 `CLAUDE_REVIEWED`。`M2-GOV-WBS2` 由本复查候选形成，处于 `VERIFYING / PENDING_ACCEPTANCE`；用户亲自验收候选后，方可由仅含状态与验收回执的第二提交更新。

**H11 现状。** 保持 `COMPLETED / ACCEPTED`：14 条目标 Work 均 `CANCELLED`、5 条旧终态 lease 已围栏（`WORK_ADJUDICATED` 14 条、`RUN_LEGACY_LEASE_FENCED` 5 条，当前采集）；本轮未重新执行、未重新裁决、未改写历史事件或 Checkpoint。

**时点证据（当前值对当时值）。**

| 指标 | 当前值（2026-09-30T15:35） | 2026-09-29 当时值 | 采集方法 |
|---|---|---|---|
| 主工作区 HEAD / 分支 | `6f759fce` / `codex/c09-recovery-governance` | `58ac6a03` | `git rev-parse HEAD`、`git branch --show-current` |
| active / previous release | `1.3.3-a808fa8` / `1.3.3-0b72499` | `1.3.3-0b72499` / `1.3.3-e648e0b` | 读 `active_release.json`、`previous_release.json` |
| canonical 事件数 / 链断裂 | 2651 / 0（304/304 Run 活动校验通过） | 2566 / 0 | 只读数据库副本上运行 `m2-gov-dep1/tools/drill.py` |
| `WORK_ADJUDICATED` / `RUN_LEGACY_LEASE_FENCED` | 14 / 5 | 14 / 5 | `select count(*) from events where event_type=…`（只读） |
| Work 状态分布（全库） | ACCEPTED 97、BLOCKED 2、CANCELLED 87、CLOSED 64；2 条 BLOCKED 均属 SW009，SW008 无 BLOCKED | SW008 无 BLOCKED | `select state,count(*) from work_items group by state`（只读） |
| SW008 未关闭 CHG | **73**（approved 38、implementing 16、pending_acceptance 14、draft 5）；另有 4 个归档目录下格式异常文件 CHG-SCPT-2026-161～164 状态字段无法解析 | 62（仅 CHG-SCPT 口径） | 读 CHG 文件「变更状态」字段（`collect_facts.py`），不用文本近似 |
| 工作树数量 / 含未提交改动 | 124 / 22 | 119 / 22 | `git worktree list --porcelain` 与逐个 `git status --porcelain` |
| 台账 SW-2026-008 / SYS-2026-001 | 均 0/0/0 | 0/0/0 | `main.py ledger reconcile <PID>` |

**来源说明（按 CHG 文件 approver/comment 字段现场核对，不凭聊天角色推断）。** GPT 实施了阶段 1 的候选（卡 025）；CHG-DOCU-2026-022 的批准文件无委托标记，以用户批准为据。阶段 2 的 CHG-356 批准行（V0.3，2026-09-29）无委托标记，其验证结论与 CHG-357、358、359、360、361 的批准及验收均带“委托执行”标记，实际执行者为 Claude Opus 5.5 代 `fubai` 署名；CHG-DOCU-2026-023（本卡）由 Claude Sonnet 5.5 代为批准，复查候选验收与最终验收不在委托内。DEP1 Gate B 的切换脚本由用户亲自运行（第 3 次运行通过）。`fubai` 与 `baiyang` 为同一用户等权署名；现有 CHG/Decision schema 不单独记录命令发起进程。

**实际偏差声明（相对 GPT 原始整改要求）。** ① 增加 BL02 统一基线（三线互不包含）；② 增加并**已执行**开发运行时集成部署（原文“不部署、不切换 release”；用户批准，开发运行时，非 D07）；③ H11 直接记为 `COMPLETED / ACCEPTED`；④ WBS 分两次修订；⑤ D 项扩大为“预检命令 + 强制接入 `continuity work create`”；⑥ 增加来源说明；⑦ 阶段 2～5 由 Claude 委托执行批准与验收；⑧ DEP1 Gate B 经三次运行（首次因预检相对路径自动回退、二次因备份目录已存在在切换前停止、三次首轮被中断后幂等重入通过）；⑨ BL02 首个整合 Run 001 CANCELLED 并以恢复链完成；⑩ 卡 029 由 Claude Sonnet 5.5 执行，且起卡时错建的 Work（`WORK-SW008-M2-GOV-WBS2-001`）已 CANCELLED 保留。

**技术债登记（当前值；完整 17 项见交付包 §6）。** ① 主工作区大量 CHG/台账/Decision/实施卡及三个 release 指针文件未提交；② SW008 未关闭 CHG 73 个，另有 4 个格式异常归档 CHG；③ Markdown 与结构化实施卡两套并存（方案 C 为后续）；④ Service/Facade 层 `create_work` 与 Mission 派生 Work 未接入预检；⑤ 缺少正式 release 构建命令；⑥ H11 在较弱合同下执行；⑦ 旧 Hook 在 GBK 终端 emoji 报错；⑧ 主工作区 WBS 与本隔离候选分叉；⑨ 历史非终态 Run；⑩ 124 个工作树中 22 个含未提交改动；⑪ release 目录未被 Git 跟踪；⑫ CHG-346 失败历史；⑬ pytest-qt 间歇性 access violation（E-G1-3）；⑭ `list_missions` 历史 Mission 校验失败（E-G3-1）；⑮ SW009 有 2 条 BLOCKED Work；⑯ 部署脚本缺少中断保护；⑰ `work create` 不校验 Work 与 Decision 的项目一致性。

**U05 状态。** 整改闭环并经用户验收后可启动；U05 的隔离基线为 BL02 统一基线 `7cfe227e`；集成部署（`1.3.3-a808fa8`）为软依赖，现已就绪。未经用户验收本候选，不得启动 U05；本修订不授权合并 main、推送、正式发布或 D07。

**V3.0.18 补记（验收回执）。** 用户于 2026-09-30 在会话中亲自作出“第一提交验收通过”（未委托执行 Agent），回执 `.auto-pm/reports/m2-gov-wbs2/first_commit_acceptance_receipt.txt`（SHA-256 `628e475452cf7d9b1c7e7734e08d609dac1559d9b28a27d6723a9f89c30b9c9d`） 绑定复查候选 `e07f7662`（父 `a385452c`）、卡 029 V0.4 与首个 Checkpoint `CKPT-SYS001-M2-GOV-WBS2-001`。据此 `M2-GOV-WBS2` 更新为 `COMPLETED / ACCEPTED`，整改闭环，U05 可由 BL02 统一基线 `7cfe227e` 启动。该验收只覆盖 WBS V3.0.17 候选本身：阶段 2～5 仍为 `DELEGATED_ACCEPTED`，阶段 1 仍为 `CLAUDE_REVIEWED`（用户尚未逐阶段亲自验收）；不授权合并 main、推送、正式发布、D07 或新的 release 切换。上文 V3.0.17 段落中关于“待用户验收”的表述是当时的历史状态，予以保留。

#### 4.7.4 U05～U08 验收回写、U07 拆分与 U09 新增（V3.0.19，2026-10-01）

本节由 `M2-GOV-WBS3`（卡 038 V1.0）追加，只加不删；V3.0.18 及更早的文字保留，仅修改卡 038 §5 列明的行。所有 SHA、ID 与数字均在 2026-10-01T13:44:48-07:00 只读采集（`.auto-pm/reports/m2-gov-wbs3/collect_facts.py`，输出 `facts_raw.json`）。

**U05～U08 验收证据。**

| 卡（SHA-256 前 8 位） | 任务 | 不可变提交 | CHG / Decision | Run / Work / Checkpoint | 门禁 | 最终验收方式 |
|---|---|---|---|---|---|---|
| 030 V1.0（`269c0093`） | U05 | `ace7a959`（父 `7cfe227e`；11 路径） | CHG-SCPT-2026-362 completed；`DEC-20260930-U05CODE0` | Run U05-001 SUCCEEDED；Work U05-001 CLOSED；`CKPT-SW008-M2-U05-001` | G1、G3～G7 PASS；G2 `PASS_WITH_BASELINE_EXCEPTION`（仅 E-G1-1） | 用户本人验收并运行收口脚本 |
| 031 V1.0（`30781b0a`） | U06 | `8b7f199a`（父 `ace7a959`；9 路径） | CHG-SCPT-2026-363 completed；`DEC-20260930-U06CODE0` | Run U06-001 SUCCEEDED；Work U06-001 CLOSED；`CKPT-SW008-M2-U06-001` | G1、G3～G7 PASS；G2 `PASS_WITH_BASELINE_EXCEPTION`（仅 E-G1-1） | 用户本人验收并运行收口脚本 |
| 032 V1.1（`81b08a50`） | U07A | `795fe448`（父 `8b7f199a`；6 路径） | CHG-SCPT-2026-364 completed；CHG-SCPT-2026-365 completed；`DEC-20260930-U07ACODE`、`DEC-20261001-U07ARSET` | Run U07A-001 CANCELLED、Run U07A-002 SUCCEEDED、Run U07A-RSET-001 SUCCEEDED；Work U07A-001 CLOSED、Work U07A-RSET-001 CLOSED；`CKPT-SW008-M2-U07A-001` | G1、G3～G7 PASS；G2 `PASS_WITH_BASELINE_EXCEPTION`（仅 E-G1-1） | 用户本人验收并运行收口脚本（364、365） |
| 033 V1.0（`03d05c11`） | U07B | `35379585`（父 `795fe448`；5 路径） | CHG-SCPT-2026-366 completed；`DEC-20261001-U07BCODE` | Run U07B-001 SUCCEEDED；Work U07B-001 CLOSED；`CKPT-SW008-M2-U07B-001` | G1、G3～G7 PASS；G2 `PASS_WITH_BASELINE_EXCEPTION`（仅 E-G1-1） | 用户本人验收并运行收口脚本 |
| 034 V1.0（`039853bb`） | U07C | `9a92e9b7`（父 `35379585`；3 路径） | CHG-SCPT-2026-367 completed；`DEC-20261001-U07CCODE` | Run U07C-001 SUCCEEDED；Work U07C-001 CLOSED；`CKPT-SW008-M2-U07C-001` | G1、G3～G7 PASS；G2 `PASS_WITH_BASELINE_EXCEPTION`（仅 E-G1-1） | 用户在对话弹窗确认，Claude 代跑收口 |
| 035 V1.0（`4d284a50`） | U07D | `460e24f6`（父 `9a92e9b7`；5 路径） | CHG-SCPT-2026-368 completed；`DEC-20261001-U07DCODE` | Run U07D-001 SUCCEEDED；Work U07D-001 CLOSED；`CKPT-SW008-M2-U07D-001` | G1、G3～G7 PASS；G2 `PASS_WITH_BASELINE_EXCEPTION`（仅 E-G1-1） | 用户在对话弹窗确认，Claude 代跑收口 |
| 036 V1.0（`d2788e3c`） | U08 | `d40318d0`（父 `460e24f6`；2 路径） | CHG-SCPT-2026-369 completed；`DEC-20261001-U08CODE0` | Run U08-001 SUCCEEDED；Work U08-001 CLOSED；`CKPT-SW008-M2-U08-001` | G1、G3～G7 PASS；G2 `PASS_WITH_BASELINE_EXCEPTION`（仅 E-G1-1） | 用户在对话弹窗确认，Claude 代跑收口 |

**来源说明（按 CHG 文件批准行与验证结论现场核对）。** 七张卡的实施批准均为用户在对话或确认弹窗中明确批准后，由 Claude Sonnet 5.5 以委托方式执行（CHG 批准行带“委托执行”标记）。最终验收：CHG-SCPT-2026-362～366 的验证结论为“用户本人验收通过”；CHG-SCPT-2026-367～369 为“用户在对话弹窗确认验收通过（由 Claude 代为运行）”。卡 035（U07D）的字节写成于用户批准设计摘要之后，用户未逐字阅读，CHG-SCPT-2026-368 的批准行已如实记录。U07A、U07B 回执中的执行者与委托日期沿用通用脚本的旧文案，实际执行者为 Claude Sonnet 5.5、批准日期以 CHG 批准行为准，属显示问题。`fubai` 与 `baiyang` 为同一用户等权署名。

**实际偏差声明（相对 V3.0.18 任务表）。** ① U05 实际 11 个路径、U06 实际 9 个路径（表内原各列 3 个），原因见实施卡 030、031 的 §1；② 原 U07 一行在开工前勘测后拆为四项：U07A（执行成功后没有任何产品代码生成验证 Checkpoint，驾驶舱到不了验收门）、U07B（规划生成的 CHG 没有实质内容，收尾永远待同步）、U07C（原 U07 的 SDK）、U07D（驾驶舱“开始”对规划类任务失败）；该拆分在执行前没有先回写 WBS，由本修订补记；③ U07A 的 Run 001 因长门禁期间漏续租而租约过期，经恢复链 CHG-SCPT-2026-365 / `DEC-20261001-U07ARSET` 结算为 `CANCELLED`，Run 002 `SUCCEEDED`；卡 032 因隐私口径与既有存储设计矛盾，经用户批准由 V1.0 升为 V1.1；④ U08 只提供代码层兼容，CLI 参考文档的修订留给 D01。

**U09 新增（V05 前置）。** 2026-10-01 U08 收口后的只读勘测确认：驾驶舱只能保存 `PRE_AUTH` 草稿，且其 `request_id` 对用户不可见；范围、风险、非目标与执行授权由调用方传入，产品内没有自动规划器；批准前的范围卡没有持久化，规范库也没有“列出草稿”的读取接口。因此 V05 要求的“从 GUI 输入目标到验收”缺少“目标 → 范围卡 → 批准”一段。用户 2026-10-01 裁决：① 范围卡由 PM 经 CLI/SDK 起草，驾驶舱只展示给用户审；② 驾驶舱用一个按钮“批准范围并开始”，整条链两次业务决策（批准范围、最终验收）；③ 待批准范围卡存规范库追加的一张表，在事件链内可审计；④ 驾驶舱批准人身份来自配置项，未配置则拒绝批准。据此新增 U09A（Store 与 Facade，实施卡 037）、U09B（CLI）、U09C（驾驶舱），V05 增加对 U09C 的依赖，M2 范围改为 U01～U09、V01～V08。U09B、U09C 须各自先勘测写卡。

**任务表计数。** §4.2～§4.10 各表按 ID 行机器计数：V3.0.18 为 107 行，本修订后为 115 行（U07A～U07D 4 行、U09A～U09C 3 行、`M2-GOV-WBS3` 1 行）。文首“100 个原子任务”为历史口径，与逐行计数不一致；本修订不改该句，口径留待 M2 总审计统一。

**时点证据（2026-10-01T13:44:48-07:00）。**

| 指标 | 当前值 | 采集方法 |
|---|---|---|
| 主工作区 HEAD / 分支 | `a84fd7ee` / `codex/c09-recovery-governance` | `git rev-parse HEAD`、`git branch --show-current` |
| active / previous release | `1.3.3-a808fa8` / `1.3.3-0b72499` | 读 `active_release.json`、`previous_release.json` |
| canonical 事件数 / 链断裂 | 2778 / 0 | 只读连接逐条复算前后哈希 |
| SW008 未终结 Mission | 0 | `select count(*) from mission_items …`（只读） |
| SW008 未关闭 CHG | 73（另有 4 个格式异常归档文件无法解析） | 逐文件读“变更状态”字段 |
| 工作树数量 | 132 | `git worktree list --porcelain` |
| 台账 SW-2026-008 / SYS-2026-001 | 均 0/0/0 | `main.py ledger reconcile <PID>` |

**技术债登记（增补，接 §4.7.3 的 ①～⑰）。** ⑱ 真实控制库 `schema_meta` 存在 `continuity-store.v2` 与 `continuity-store.v3` 两行，迁移链从未走到 v7，各表由每次重跑的建表语句补齐；当前不影响读写，但任何新逻辑不得依赖 schema 版本号判断，只能判断表是否存在；⑲ `DecisionService` 的模型自签拦截规则只拦 `ai/agent/codex/gpt/model`，不拦 `claude`，由 U09C 与批准人配置项一并处置。已知限制（各验收回执已记录，不另编号）：U07D 的租约口令只在进程内存，进程在“执行完成、验证未做”之间崩溃后无法补验证；`SubstanceChecker` 仍会对 CHG 模板 §6.3 的占位关联单行报占位；开发运行时 `1.3.3-a808fa8` 不含 U05～U08 代码。

**后续顺序。** U09A → U09B → U09C → V01～V08 → M2 总审计与 WBS 回写。M2 完成后做一次开发运行时部署（独立 CHG/Decision、exact-tree、切换/回退演练，切换脚本由用户运行，不等于正式发布）；合并 main 等到 M3 的 D03；正式部署只在 D07。本修订不授权 U09A 开工、合并 main、推送、部署或 release 切换。

#### 4.7.5 U09A～U09C 验收回写、QML 生命周期根修与技术基线校准（V3.0.20，2026-10-03）

本节由 `M2-GOV-WBS4`（卡 041 V1.0）追加，只加不删；V3.0.19 及更早的文字保留，仅修改卡 041 §5 列明的行。所有 SHA、ID 与数字均在 2026-10-03T05:59:44-07:00 只读采集（`.auto-pm/reports/m2-gov-wbs4/collect_facts4.py`，输出 `facts_raw.json`）。用户在对话中批准本修订的范围，批准发生在卡字节写成之前，回执已如实记录。

**U09A～U09C 验收证据。**

| 卡（SHA-256 前 8 位） | 任务 | 不可变提交 | CHG / Decision | Run / Work / Checkpoint | 门禁 | 最终验收方式 |
|---|---|---|---|---|---|---|
| 037 V1.0（`a8b5475a`） | U09A | `eebdeecb`（父 `d40318d0`；4 路径） | CHG-SCPT-2026-370 completed；`DEC-20261001-U09ACODE` | Run U09A-001 SUCCEEDED；Work U09A-001 CLOSED；`CKPT-SW008-M2-U09A-001` | G1、G3～G7 PASS；G2 `PASS_WITH_BASELINE_EXCEPTION`（仅 E-G1-1）；变异 4/4 | 用户在对话弹窗确认，Claude 代跑收口 |
| 039 V1.0（`df6de8d0`） | U09B | `cec3afa7`（父 `eebdeecb`；4 路径） | CHG-SCPT-2026-371 completed；`DEC-20261001-U09BCODE` | Run U09B-001 SUCCEEDED；Work U09B-001 CLOSED；`CKPT-SW008-M2-U09B-001` | G1、G3～G8 PASS；G2 `PASS_WITH_BASELINE_EXCEPTION`（仅 E-G1-1）；变异 6/6；qml 首跑 1 个时序抖动已按卡处置并记入判卷 | 用户在对话弹窗确认，Claude 代跑收口 |
| 040 V1.0（`5c4cd040`）→ V1.2（`6d09d57e`）→ V1.3（`b5e39548`） | U09C | `3c32e8ad`（父 `d95f45d2`；13 路径） | CHG-SCPT-2026-372 completed；`DEC-20261001-U09CCODE`、`DEC-20261002-U09CROOT`、`DEC-20261002-U09CFIN3`、`DEC-20261002-U09CRUN4` | Run U09C-001 FAILED、Run U09C-002 FAILED、Run U09C-003 FAILED、Run U09C-004 SUCCEEDED；Work U09C-001 CANCELLED、Work U09C-002 CANCELLED、Work U09C-003 CANCELLED、Work U09C-004 CLOSED；`CKPT-SW008-M2-U09C-004` | Run004 判卷 `PASS_WITH_BASELINE_EXCEPTION`（仅 E-G1-1）：崩溃配置复验 5×40、混合 G1 307、QML 283+1、core 916/3/1、contracts 191/1、infrastructure 32、cli 252/1、change 230；G8 6/6 | 用户在对话中确认验收通过，Claude 代跑收口（2026-10-03） |

**M2-GOV-QML1（QML 测试生命周期根修）。** U09C 首个 Run 在 `tests/qml` 门禁出现间歇性原生崩溃（`Fatal Python error: Aborted`，第 36 项，位于已有测试 `test_pm_cockpit_start_e2e.py` 的事件处理处），按实施卡 040 §9 硬停止。限时诊断确认已有的 U06 测试 `test_boss_main_retries_the_sync_and_turns_the_card_into_completed` 是崩溃的必要条件、新增测试并非原因，随后由 CHG-SCPT-2026-373 查明并修复。根因（外部调试器抓到的原生调用栈，导出符号近邻为 `QAbstractEventDispatcher::filterNativeEvent → purecall → abort`，不是精确的函数与源码行，也不是完整内存转储；真实对象环与线程轨迹佐证）：后台 worker 与 GUI Bridge 之间存在强引用环，GUI 线程创建的对象被后台垃圾回收线程销毁，随后 GUI 原生事件泵处理已销毁对象而中止。修复分两次提交：F `6eead5e4`（4 路径：文件监视 worker 去掉无用的 GUI 回指并补真实线程池与后台回收回归；测试侧确定性的窗口、Bridge、engine 收尾，以及 U06 测试在后台快照未完成时就读库的时序竞态）与 F2 `d95f45d2`（2 路径：PM 启动 worker 持有应用服务而不是 GUI Bridge，旧生产代码的负向对照在真实所有权断言处失败）；相对 U09B 累计 6 路径。验证：F2 基线混合 G1 220 passed、QML 260 passed/1 deselected；叠加 U09C 十三文件后崩溃配置复验 5×40 通过。已知限制：有限次无崩溃不等于永不崩溃；没有取得完整内存转储；F2 的旧代码负向对照证明所有权缺陷，不单独证明所有崩溃都只有这一个原因。Run 记录：Run QMLLIFE-001 FAILED、Run QMLLIFE-002 FAILED、Run QMLLIFE-003 SUCCEEDED、Run QMLLIFE-004 SUCCEEDED；Work：Work QMLLIFE-001 CANCELLED、Work QMLLIFE-002 CANCELLED、Work QMLLIFE-003 CLOSED、Work QMLLIFE-004 CLOSED；Checkpoint `CKPT-SW008-M2-QMLLIFE-003`、`CKPT-SW008-M2-QMLLIFE-004`；CHG-SCPT-2026-373 completed。

**U09C 实际偏差声明（相对 V3.0.19 任务表）。** ① U09C 实际 13 个路径（表内只列四类路径加“批准人配置项”），多出 `boss_main.qml`、新增组件 `PendingScopeCard.qml`、`app_config.py`、`boss_qml_window.py`、`decision_service.py` 与 4 个新增测试文件；② 隔离基线由 U09B `cec3afa7` 改为根修 F2 `d95f45d2`；③ Run 历史：Run001（qml 门禁硬停止）、Run002、Run003（core 门禁在 4500 秒上限处超时）均 FAILED、Checkpoint 为 0，Work001～003 均 `CANCELLED`，历史原样保留；Run004 `SUCCEEDED`、Work004 `CLOSED`。Work003 因旧 Decision 条件明文“不允许 Run004”且授权只接受 `PLANNED` 的 Work，不能转回继续使用，故取消并新建后继 Work004 与 Decision `DEC-20261002-U09CRUN4`；④ Run004 内发现并修正了判卷与变异工具三处从未在真实输出上验证过的缺陷（JUnit 失败类型读取、含中文参数的节点编号转义归一、变异 M2 的预期失败形式），工具字节被门禁证据绑定，所以整个窗口重开，前两轮窗口作为被取代证据保留；详见 `.auto-pm/reports/m2-u09c-run004/DEVIATIONS_RUN004.md`（SHA-256 `6fda603e8c144259b4dc385962a676b4d5c3552a91945cad4937b52aadf976ce`）；⑤ 非 QML 批次末尾的自动源码检查两次报 `git failed:` 原因未查明（逐进程指纹与判卷的源码核验均无漂移）；⑥ 已知限制：批准人是配置声明而不是认证；提示语随下一次快照清除；一个项目同一时刻只能有一个未终结任务；`AUTO_PM_COCKPIT_APPROVER` 的使用说明留给 D01。

**技术基线（M2 代码线，V3.0.20 校准）。** M2 代码线是一条尚未合并的堆叠提交链，从 BL02 统一基线起到 U09C 止，逐个核对父子相连（核对结果：相连）；链上最后一个提交 `3c32e8ad`（分支 `codex/m2-u09c-lifecycle-final`）就是 M2 代码线当前唯一的尖端，后继任务只能从该提交或经独立验收的后继开始；WBS 修订提交（V3.0.18 `572932a7`、V3.0.19 `79ab9516` 与本修订）在 SYS-2026-001 的文档分支链上，不在代码链内。

| 序 | 标签 | 提交 | 父提交 |
|---|---|---|---|
| 1 | BL02 | `7cfe227e` | `4e08b0dd` |
| 2 | U05 | `ace7a959` | `7cfe227e` |
| 3 | U06 | `8b7f199a` | `ace7a959` |
| 4 | U07A | `795fe448` | `8b7f199a` |
| 5 | U07B | `35379585` | `795fe448` |
| 6 | U07C | `9a92e9b7` | `35379585` |
| 7 | U07D | `460e24f6` | `9a92e9b7` |
| 8 | U08 | `d40318d0` | `460e24f6` |
| 9 | U09A | `eebdeecb` | `d40318d0` |
| 10 | U09B | `cec3afa7` | `eebdeecb` |
| 11 | QML-F | `6eead5e4` | `cec3afa7` |
| 12 | QML-F2 | `d95f45d2` | `6eead5e4` |
| 13 | U09C | `3c32e8ad` | `d95f45d2` |

分支当前指向：`codex/m2-u09a-scope-card-store` `eebdeecb`、`codex/m2-u09b-cli-scope-card` `cec3afa7`、`codex/m2-qml-lifecycle` `d95f45d2`、`codex/m2-u09c-lifecycle-final` `3c32e8ad`、`codex/m2-gov-wbs3` `79ab9516`。开发运行时 active `1.3.3-a808fa8`、previous `1.3.3-0b72499`，不含 U05～U09C 代码；M2 全部完成后做一次开发运行时部署（独立 CHG/Decision、exact-tree、切换/回退演练，切换脚本由用户运行，不等于正式发布）；合并 main 等到 M3 的 D03；正式部署只在 D07。

**任务表计数。** §4.2～§4.10 各表按 ID 行机器计数：V3.0.19 为 115 行，本修订后为 117 行（`M2-GOV-QML1`、`M2-GOV-WBS4` 各 1 行）。文首原写“100 个原子任务”，是 V3.0.18 以前的历史口径；V3.0.20 起文首改写为逐行机器计数口径，并在此保留原数字作说明。

**时点证据（2026-10-03T05:59:44-07:00）。**

| 指标 | 当前值 | 采集方法 |
|---|---|---|
| 主工作区 HEAD / 分支 | `a84fd7ee` / `codex/c09-recovery-governance` | `git rev-parse HEAD`、`git branch --show-current` |
| active / previous release | `1.3.3-a808fa8` / `1.3.3-0b72499` | 读 `active_release.json`、`previous_release.json` |
| canonical 事件数 / 链断裂 | 2929 / 0 | 只读连接逐条复算前后哈希 |
| SW008 未终结 Mission | 0 | `select count(*) from mission_items …`（只读） |
| SW008 未关闭 CHG | 73（另有 4 个格式异常归档文件无法解析） | 逐文件读“变更状态”字段 |
| 工作树数量 | 139 | `git worktree list --porcelain` |
| 台账 SW-2026-008 / SYS-2026-001 | 均 0/0/0 | `main.py ledger reconcile <PID>` |

**教训沉淀（V3.0.20）。** ① 演练用的项目副本必须包含点文件（`.ruff.toml`），否则 Ruff 通过没有意义：U09C 的演练漏了它，真实配置下有 4 处告警；② 门禁工具的判卷代码要先在真实输出上验证再启动长批次：U09C 的判卷工具缺陷到 Run004 才暴露，工具字节绑定证据，修正会使整个窗口重开；③ 长门禁的时间上限要用实测值估算并留余量：Run003 的 core 在 4500 秒上限处约 72% 超时，Run004 把上限放到 8000 秒，实测 3728 秒；④ 后台任务有约 30 分钟的系统时限，会杀掉启动长批次的外壳而真正的测试进程不受影响，串联与续租因此不能依赖外壳，需要每个检查周期手动续租；⑤ 间歇性原生崩溃对输出捕获方式、导入顺序等无关扰动极敏感，诊断要用固定顺序重放加对照，并把“必要条件”与“相关因素”分开。

**技术债登记（增补，接 ⑱⑲）。** ⑲ 已由 U09C 处置：`DecisionService` 的自签拦截规则现在也拦 `claude`、`anthropic`、`opus`、`sonnet`、`haiku`、`fable`、`gemini`、`copilot`、`llm`、`bot`、`assistant`；⑳ 驾驶舱批准人是配置声明而不是认证，拒绝模型名只是防误用、不是防伪造；㉑ 根修只有原生调用栈与对象环证据、没有完整内存转储，间歇性崩溃不能证明“永不再发”；㉒ 非 QML 批次末尾自动源码检查两次报 `git failed:`，原因未查明。

**后续顺序。** V01～V08（V05 对 U09C 的依赖已满足）→ M2 总审计与 WBS 回写 → 一次开发运行时部署 → M3。本修订不授权 V01 开工、合并 main、推送、部署或 release 切换。

#### 4.7.6 V01 验收回写、PLC 文档与代码一致性核对任务登记（V3.0.21，2026-10-03）

本节由 `M2-GOV-WBS5`（卡 044 V1.0）追加，只加不删；V3.0.20 及更早的文字保留，仅修改卡 044 §5 列明的行。所有 SHA、ID 与数字均在 2026-10-03T14:54:46-07:00 只读采集（`.auto-pm/reports/m2-gov-wbs5/collect_facts5.py`，输出 `facts_raw.json`）。

**V01 验收证据。**

| 卡（SHA-256 前 8 位） | 任务 | 不可变提交 | CHG / Decision | Run / Work / Checkpoint | 门禁 | 最终验收方式 |
|---|---|---|---|---|---|---|
| 042 V1.0（`dbb04f53`） | V01 | `37a4faff`（父 `3c32e8ad`；5 路径；+1552/−14） | CHG-SCPT-2026-374 completed；`DEC-20261003-V01PLCQG` | Run V01-001 SUCCEEDED；Work V01-001 CLOSED；`CKPT-SW008-M2-V01-001` | G1～G9 全部通过（G2 仅含基线例外 E-G1-1）；G1 268 passed（基线 236，新增 32）；core 948 passed/3 failed/1 skipped；qml 283、cli 252/1、contracts 191/1、infrastructure 32、change 230 与基线相同；变异 12/12；钉死基准冒烟通过 | 用户在对话弹窗确认，Claude 代跑收口 |

**V01 的效果。** PLC 任务（Run 的 owned 路径位于带 `.plc.json` 的 PLC 工程内）现在在验证时自动走 PLC 质量门：在候选工作树上以库方式调用现行 `PlcChecker` 与 `SclLinter`，失败项即不通过，警告只记录；证据存为 `checkpoint-evidence.v3`，绑定 Git 证据、PLC 工程根下全部文件字节（含被 Git 忽略的文件）与检查器包指纹；Facade 按 Run 选择 profile，验收校验识别 v3；一个 Run 只验证一个领域；Python 路径与 v1/v2 证据不变。

**V01 实际偏差声明（相对 V3.0.20 任务表）。** ① 路径：WBS 的 V01 行只列 2 个路径，实际 5 个：执行服务与 Facade 两个产品文件必须同改（否则 PLC 任务走不到验收门：通用门只认 `.py`、Facade 写死 profile、验收只认 v1/v2），另新增两个测试文件，既有 `test_evidence_collection_service.py` 未改；② 用户批准早于卡的最终字节（其后只补写演练事实），回执已如实记录；③ 判卷没有偏差记录，唯一例外为基线既有 E-G1-1；④ 钉死基准：DJ-2026-005 在提交 `3c32e8ad` 的 Git 目录树 SHA 为 `b457f2b95acd58db7cf65207236ef0999ebda9dd`（现行检查器实测 50 通过、1 警告、0 失败）。

**V01 已知限制。** INT/VAR 与 SCL 的一致性未核对（只做同基线绑定）；进程内质量门没有超时；检查器指纹只覆盖 `plc` 包本身；工程根之外被 Git 忽略的输入不在绑定内；整项目检查意味着已有失败项的工程（如 DJ-2026-000）内任何 Run 都会被拒绝。

**PLC 文档与代码一致性核对：用户确认的需求。** 需求说明 `02_规划/043_PLC文档与代码一致性核对与自动补全需求说明_PM.md`（SHA-256 前 8 位 `3fee21e6`，用户 2026-10-03 确认）：核对信号名、数据类型、方向、注释，不核对通信协议；FB/FC 的接口文档只写自己声明的参数，DB、OB、结构体的变量表在变量定义文档、结构体字段只在一处维护；整份文档缺失警告并给草稿，不一致拦住并精确指出；直接拦提交、不设宽限期；自动补全只补缺行、不覆盖人写文字、补入行带【待确认】、一条命令确认；AI 任务写的文档不带标记。基准现状：DJ-2026-005 的文档与代码已大面积对不上（例如 FB_2001 的文档仍是旧的逐个信号，代码已重构为结构体整块传递），规则生效后须先治愈基准。

**新增任务与顺序（用户 2026-10-03 确定）：V01B → V01C → V01D → V02。** V01B 把核对并入检查器并做自动补全（`plc check`、驾驶舱红灯、AI 验收门同时生效）；V01C 用其工具给 DJ-2026-005 生成草稿、用户审核后写入并重新钉基准；V01D 做提交拦截钩子与阶段门接入，碰提交钩子，单独验收；V02 依赖改为 V01、V01B、V01C、V01D、C09。V08 的模板提取使用治愈并重新钉死后的基准。各任务均须先勘测、写卡、用户批准后开工；本修订不授权其中任何一项。

**技术基线更新（M2 代码线）。** 代码线唯一尖端由 U09C 变为 V01 `37a4faff`（分支 `codex/m2-v01-plc-quality-gate`，父 `3c32e8ad`），逐个核对父子相连（核对结果：相连）；后继任务从该提交或经独立验收的后继开始。

| 序 | 标签 | 提交 | 父提交 |
|---|---|---|---|
| 1 | BL02 | `7cfe227e` | `4e08b0dd` |
| 2 | U05 | `ace7a959` | `7cfe227e` |
| 3 | U06 | `8b7f199a` | `ace7a959` |
| 4 | U07A | `795fe448` | `8b7f199a` |
| 5 | U07B | `35379585` | `795fe448` |
| 6 | U07C | `9a92e9b7` | `35379585` |
| 7 | U07D | `460e24f6` | `9a92e9b7` |
| 8 | U08 | `d40318d0` | `460e24f6` |
| 9 | U09A | `eebdeecb` | `d40318d0` |
| 10 | U09B | `cec3afa7` | `eebdeecb` |
| 11 | QML-F | `6eead5e4` | `cec3afa7` |
| 12 | QML-F2 | `d95f45d2` | `6eead5e4` |
| 13 | U09C | `3c32e8ad` | `d95f45d2` |
| 14 | V01 | `37a4faff` | `3c32e8ad` |

分支当前指向：`codex/m2-u09c-lifecycle-final` `3c32e8ad`、`codex/m2-v01-plc-quality-gate` `37a4faff`、`codex/m2-gov-wbs4` `7e2768a1`。开发运行时 active `1.3.3-a808fa8`、previous `1.3.3-0b72499`，不含 U05～V01 代码；M2 全部完成后做一次开发运行时部署（独立 CHG/Decision、exact-tree、切换/回退演练，切换脚本由用户运行）；合并 main 等到 M3 的 D03。

**任务表计数。** §4.2～§4.10 各表按 ID 行机器计数：V3.0.20 为 117 行，本修订后为 121 行（`M2-GOV-WBS5`、`V01B`、`V01C`、`V01D` 各 1 行）。

**时点证据（2026-10-03T14:54:46-07:00）。**

| 指标 | 当前值 | 采集方法 |
|---|---|---|
| 主工作区 HEAD / 分支 | `a84fd7ee` / `codex/c09-recovery-governance` | `git rev-parse HEAD`、`git branch --show-current` |
| active / previous release | `1.3.3-a808fa8` / `1.3.3-0b72499` | 读 `active_release.json`、`previous_release.json` |
| canonical 事件数 / 链断裂 | 2973 / 0 | 只读连接逐条复算前后哈希 |
| SW008 未终结 Mission | 0 | `select count(*) from mission_items …`（只读） |
| SW008 未关闭 CHG | 73（另有 4 个格式异常归档文件无法解析） | 逐文件读“变更状态”字段 |
| 工作树数量 | 141 | `git worktree list --porcelain` |
| 台账 SW-2026-008 / SYS-2026-001 | 均 0/0/0 | `main.py ledger reconcile <PID>` |

**教训沉淀（V3.0.21）。** ① 后台长任务的外壳有 2 小时上限，续租循环到期会停，需要在到期前重开，不能假设它一直在；② 涉及“文档对代码”这类规则时，先用真实基准粗测再定拦截策略：V01 勘测发现基准文档与代码已大面积不一致，直接改变了任务顺序；③ 基准按“某个提交上目录的 Git 目录树 SHA”钉死，不指向活目录；④ 在这台机器上 Bash 的 `$'\r'` 与 heredoc 里的反斜杠不可靠，字节级检查一律用 Python；⑤ 系统可能拒绝停止已启动的后台测试进程，长跑应避免重叠。

**技术债登记（增补，接 ⑳～㉒）。** ㉓ `plc check --json` 的输出末尾追加一行 `launcher:` 且受控制台编码影响，无法被直接解析（V01 勘测发现，未处理）；㉔ V01 的质量门在进程内执行、没有超时；㉕ V01 的检查器指纹只覆盖 `plc` 包本身（不含 `find_prd_dir` 所在模块），工程根之外被 Git 忽略的输入不在绑定内。

**后续顺序。** V01B → V01C → V01D → V02 → V03～V08 → M2 总审计与 WBS 回写 → 一次开发运行时部署 → M3。本修订不授权 V01B 开工、合并 main、推送、部署或 release 切换。

#### 4.7.7 V01B～V04、第 1 期、TD1、第 1 期审计缺陷修复与 TD2 验收回写；拆分、分期与新顺序（V3.0.22，2026-10-06）

本节由 `M2-GOV-WBS6`（卡 056 V1.0）追加，只加不删；V3.0.21 及更早的文字保留，仅修改卡 056 §5 列明的行。所有 SHA、ID 与数字均在 2026-10-06T15:20:40-07:00 只读采集（`.auto-pm/reports/m2-gov-wbs6/collect_facts6.py`，输出 `facts_raw.json`）；文中时间均为用户所在地的本地时间（UTC-7）。

**验收证据（均由用户在对话中确认验收，CHG 收口由 Claude 代跑）。**

| 卡 | 不可变提交 | CHG | Run / Work / Checkpoint | 门禁 |
|---|---|---|---|---|
| 卡 045（V01B；SHA-256 前 8 位 `ed93c8fb`） | `d890be25`（父 `37a4faff`；15 路径；15 个文件，+1766/−161） | CHG-SCPT-2026-375 completed | RUN-SW008-M2-V01B-001 SUCCEEDED；WORK-SW008-M2-V01B-001 CLOSED；`CKPT-SW008-M2-V01B-001` | 9 项门禁全部通过（含基线例外） |
| 卡 046（V01C；SHA-256 前 8 位 `5a53a7f0`） | `1e1ef760`（父 `d890be25`；8 路径；8 个文件，+410/−411） | CHG-PLC-2026-014 completed | RUN-DJ005-M2-V01C-001 SUCCEEDED；WORK-DJ005-M2-V01C-001 CLOSED；`CKPT-DJ005-M2-V01C-001` | 6 项门禁全部通过 |
| 卡 047（V01D；SHA-256 前 8 位 `241d98a3`） | `fb94afa9`（父 `1e1ef760`；6 路径；6 个文件，+604/−0） | CHG-SCPT-2026-376 completed | RUN-SW008-M2-V01D-001 SUCCEEDED；WORK-SW008-M2-V01D-001 CLOSED；`CKPT-SW008-M2-V01D-001` | 9 项门禁全部通过（含基线例外） |
| 卡 048（V02；SHA-256 前 8 位 `67ab5cfa`） | `cf6f6f33`（父 `fb94afa9`；2 路径；2 个文件，+341/−1） | CHG-SCPT-2026-377 completed | RUN-SW008-M2-V02-001 SUCCEEDED；WORK-SW008-M2-V02-001 CLOSED；`CKPT-SW008-M2-V02-001` | 9 项门禁全部通过（含基线例外） |
| 卡 049（TD1；SHA-256 前 8 位 `4659e65d`） | `b6668dcf`（父 `cf6f6f33`；1 路径；1 个文件，+84/−7） | CHG-DOCU-2026-016 completed | RUN-SW008-M2-GOV-TD1-001 SUCCEEDED；WORK-SW008-M2-GOV-TD1-001 CLOSED；`CKPT-SW008-M2-GOV-TD1-001` | 6 项门禁全部通过 |
| 卡 050（V03；SHA-256 前 8 位 `fbd566e4`） | `edeeead9`（父 `b6668dcf`；2 路径；2 个文件，+237/−0） | CHG-SCPT-2026-378 completed | RUN-SW008-M2-V03-001 SUCCEEDED；WORK-SW008-M2-V03-001 CLOSED；`CKPT-SW008-M2-V03-001` | 9 项门禁全部通过 |
| 卡 051（P1；SHA-256 前 8 位 `1e6fe979`） | `4e165cf4`（父 `edeeead9`；14 路径；14 个文件，+2967/−12） | CHG-SCPT-2026-379 completed | RUN-SW008-M2-P1-001 SUCCEEDED；WORK-SW008-M2-P1-001 CLOSED；`CKPT-SW008-M2-P1-001` | 9 项门禁全部通过 |
| 卡 052（V04；SHA-256 前 8 位 `131edf48`） | `a6447be6`（父 `4e165cf4`；6 路径；6 个文件，+794/−21） | CHG-SCPT-2026-380 completed | RUN-SW008-M2-V04-001 SUCCEEDED；WORK-SW008-M2-V04-001 CLOSED；`CKPT-SW008-M2-V04-001` | 9 项门禁全部通过 |
| 卡 054（P1FIX；SHA-256 前 8 位 `2f6e5de2`） | `948884db`（父 `a6447be6`；9 路径；9 个文件，+1650/−174） | CHG-SCPT-2026-382 completed | RUN-SW008-M2-P1FIX-001 SUCCEEDED；WORK-SW008-M2-P1FIX-001 CLOSED；`CKPT-SW008-M2-P1FIX-001` | 9 项门禁全部通过 |
| 卡 055（TD2；SHA-256 前 8 位 `24751227`） | `1956dd9a`（父 `948884db`；17 路径；17 个文件，+1563/−1） | CHG-DOCU-2026-017 completed | RUN-SW008-M2-TD2-001 SUCCEEDED；WORK-SW008-M2-TD2-001 CLOSED；`CKPT-SW008-M2-TD2-001` | 9 项门禁全部通过 |

V01C 的变更对象在 DJ-2026-005 项目内（`CHG-PLC-2026-014`，Work 与 Run 的项目标识为 `DJ005`），与其余各卡同属一条代码链；卡 053 是 GPT 起草的、未获批准的第 1 期修复草稿卡，其演练留下的 CHG-SCPT-2026-381（implementing）、Work `WORK-SW008-M2-P1-AUDITFIX-001`（BLOCKED）与候选分支 `codex/m2-p1-audit-fix` 作为失败尝试**保留、未处置**（登记为 TD-SW008-086），不计入上表。

**验收口径的更正与区分。** ① V03：底层 handoff.v2 机制、同一 Work 续跑与旧 owner 拒写已验收；“无需用户搬 JSON 或口令”的产品流程**尚未交付**（N2，关联 TD-SW008-063～065）。② V04：实际范围为 6 个路径——两处产品修复（E06 对账改用回执的 `owner_id`；存储对 WAL 边车瞬时状态的有限重试，写路径与严格只读路径各一处）、三个测试文件（含真实进程恢复演练 r01～r09 与边车确定性测试 sc01～sc08）与台账追加 TD-SW008-074～077；不扩写为“主控重启后自动续做”或“任意并发读取”，残余边界保留在 TD-SW008-074～077。③ 第 1 期：卡 051 的验收是历史事实，**不等于**审计发现已修复；A-P1-01～03、C11、C12 由卡 054 的提交 `948884db` 修复并验收，TD-SW008-066、070、072、073 的其余部分不关闭。④ 第 1 期审计缺陷修复的验证缺口（变异检查只覆盖 10 个守护点、测试文件新增行未逐行审读）登记为 TD-SW008-085。

**计划修订与拆分（用户 2026-10-05、2026-10-06 同意）。** 新顺序：WBS 修订 6（本卡）→ M2-F01A → V05-A → V05-B → V05-C → V04-R1 → V06 → V07/V08 → V04-T（可并入 V04-R1 的明确测试范围）→ M2-F01B（M2 末或 M3）→ M2 交叉总审计与 WBS 终稿 → 经单独批准的一次开发运行时部署；合并 main 保留至 M3 D03。其中：
- **F01 拆分**：F01-a 只做失败关闭（HEAD 有 `.plc.json` 而暂存区或工作区没有即拒绝，全部改名与移动一并拒绝，不新增存储，不改 `checker.py`），是 V05、V08 与部署的前置；F01-b 是合法移动与退役入口，独立新能力卡。F01-a 的 Git HEAD 身份不是持久登记，不据此关闭历史身份债务。
- **V05 拆分**：V05-A 带版本和能力标志的共用查询合同（触及 contracts，按核心档）；V05-B GUI 双根与生产线程池接线；V05-C 真实双领域 GUI 联验（调用真实模型前须先获用户授权）。V05 顶层行是汇总，A、B 通过不能写成 V05 完成。
- **F05 分期**：M2 只交 `parking_supported=false`、`preemption_supported=false` 的版本化查询合同，挂起与抢占相关动作返回 UNSUPPORTED；完整挂起放 M3（调度状态与业务状态分离，每项目一个当前槽、最多三个挂起槽，恢复重新核验授权）；运行中插队依赖 V04-R1。N1.4 的完整目标**保持未交付**。V04-R1 不是 V05 的前置。
- **单卡规模**：产品文件一般不超过约 6 个、围绕一组关键反例，超出继续拆；文档卡按业务项目与基线拆分，SW-2026-008 侧（TD2）与 SYS-2026-001 侧（本卡）分开。门禁分档规则见 `02_规划/M2_门禁分档与单卡规模规则_PM.md`（SHA-256 前 8 位 `8fec2229`），需求说明见 `02_规划/M2_入口分类与定位交接_需求说明_REQ.md`（SHA-256 前 8 位 `6ea58e0f`）；两者随 TD2 提交 `1956dd9a` 入库，没有机器分档器，各卡仍须显式写完整门禁矩阵。
- **本期不采纳演练证据的跨 Run 复用**，受治理执行里完整重跑；以后的演练前后用 `m2-tools/seal_inputs.py` 封存输入，但封存不是复用授权。

**新增与修改的任务行。** §4.7.1 新增 `M2-GOV-TD1`、`M2-P1`、`M2-P1FIX`、`M2-GOV-TD2`、`M2-GOV-WBS6`；§4.8 新增 `M2-F01A`、`M2-F01B`、`V04-T`、`V05-A`、`V05-B`、`V05-C`；V05 的依赖与验收文字、V06 的坏证据反例、V08 的依赖与边界相应补充（见表）。新增 ID 先去重再计数。

**技术基线更新（M2 代码线）。** 代码线唯一尖端由 V01 `37a4faff` 变为 TD2 `1956dd9a`（分支 `codex/m2-td2-docs`），逐个核对父子相连（核对结果：相连）；后继任务从该提交或经独立验收的后继开始。未合并 main、未推送；开发运行时 active `1.3.3-a808fa8`、previous `1.3.3-0b72499`，不含 U05～1956dd9a 的代码。

| 序 | 标签 | 提交 | 父提交 |
|---|---|---|---|
| 1 | V01 | `37a4faff` | `3c32e8ad` |
| 2 | V01B | `d890be25` | `37a4faff` |
| 3 | V01C | `1e1ef760` | `d890be25` |
| 4 | V01D | `fb94afa9` | `1e1ef760` |
| 5 | V02 | `cf6f6f33` | `fb94afa9` |
| 6 | TD1 | `b6668dcf` | `cf6f6f33` |
| 7 | V03 | `edeeead9` | `b6668dcf` |
| 8 | P1 | `4e165cf4` | `edeeead9` |
| 9 | V04 | `a6447be6` | `4e165cf4` |
| 10 | P1FIX | `948884db` | `a6447be6` |
| 11 | TD2 | `1956dd9a` | `948884db` |

**任务表计数。** §4.2～§4.10 各表按 ID 行机器计数：V3.0.21 为 121 行，本修订后为 132 行（新增 11 个 ID，见上）。

**时点证据（2026-10-06T15:20:40-07:00）。**

| 指标 | 当前值 | 采集方法 |
|---|---|---|
| 主工作区 HEAD / 分支 | `a84fd7ee` / `codex/c09-recovery-governance` | `git rev-parse HEAD`、`git branch --show-current` |
| active / previous release | `1.3.3-a808fa8` / `1.3.3-0b72499` | 读 `active_release.json`、`previous_release.json` |
| canonical 事件数 / 链断裂 | 3164 / 0 | 只读连接逐条复算前后哈希 |
| SW008 未终结 Mission | 0 | `select count(*) from mission_items …`（只读） |
| SW008 未关闭 CHG | 74（另有 4 个格式异常的归档文件无法解析） | 逐文件读“变更状态”字段 |
| 工作树数量 | 154 | `git worktree list --porcelain` |
| 台账 SW-2026-008 / SYS-2026-001 | 均 0/0/0 | `main.py ledger reconcile <PID>` |
| 活动技术债台账行数 / 最后编号 | 94 / TD-SW008-086 | 读 TD2 提交里的台账 |

**教训沉淀（V3.0.22）。** ① 变异检查的判据要在真实环境里校准：pytest 在窄终端下会把失败消息从摘要里丢掉，严格判据曾因此把全部变异误判为“未抓住”，运行脚本须固定宽终端；② 草稿与演练的交付要先“演练、再报批”，重门禁由总协调方独占机器顺序执行，演练长时间没有可验收交付时应及时换人接手；③ 凡写进卡或 WBS 的数字都由工具读取，不凭记忆。

**技术债登记（增补）。** 本修订不新增债务编号；审计发现与台账、需求、WBS 的映射见 `02_规划/archive/F05_与审计讨论_20261005/INDEX.md`，新增债务见台账 TD-SW008-078～086。

**后续顺序。** WBS 修订 6 → F01-a → V05-A → V05-B → V05-C → V04-R1 → V06 → V07/V08 → V04-T → F01-b → M2 交叉总审计与 WBS 终稿 → 一次开发运行时部署（须单独批准）→ M3。本修订不授权任何后续任务开工、合并 main、推送、部署或 release 切换。

#### 4.7.8 F01-a 至 F01-1 验收回写；三次独立审计的处置；授权记录；新任务与新顺序；部署意图与 M3 候选（V3.0.23，2026-10-08）

本节由 `M2-GOV-WBS7`（卡 073）追加，只加不删；V3.0.22 及更早的文字保留，仅修改卡 073 §5 列明的行。所有 SHA、ID 与数字均在 2026-10-08T16:28:17-07:00 只读采集（`.auto-pm/reports/m2-gov-wbs7/collect_facts7.py`，输出 `facts_raw.json`）；文中时间均为用户所在地的本地时间（UTC-7）。

**验收证据（所有卡均经受治理执行：Work/Run/Checkpoint、提交字节等于 Checkpoint、G1～G9 全部通过；验收由用户本人或按用户的有条件预授权委托 Claude 代为收口，条件是 G1～G9 全部通过且提交与 Checkpoint 一致，逐卡原话与回执见 `.auto-pm/reports` 下的 PREAUTH 记录与各卡 `acceptance_receipt.txt`）。**

| 卡 | 不可变提交 | CHG | Run / Work / Checkpoint | 门禁 |
|---|---|---|---|---|
| 卡 057（F01-a；SHA-256 前 8 位 `a4f4445c`） | `01ad3923`（父 `1956dd9a`；6 路径；6 个文件，+664/−4） | CHG-SCPT-2026-383 completed | RUN-SW008-M2-F01A-001 SUCCEEDED；WORK-SW008-M2-F01A-001 CLOSED；`CKPT-SW008-M2-F01A-001` | 9 项门禁全部通过 |
| 卡 058（V05-A；SHA-256 前 8 位 `a2f53542`） | `5a2f9c48`（父 `01ad3923`；8 路径；8 个文件，+635/−5） | CHG-SCPT-2026-384 completed | RUN-SW008-M2-V05A-001 SUCCEEDED；WORK-SW008-M2-V05A-001 CLOSED；`CKPT-SW008-M2-V05A-001` | 9 项门禁全部通过 |
| 卡 059（V05-B；SHA-256 前 8 位 `40f64238`） | `5686bd9f`（父 `5a2f9c48`；6 路径；6 个文件，+292/−21） | CHG-SCPT-2026-385 completed | RUN-SW008-M2-V05B-001 SUCCEEDED；WORK-SW008-M2-V05B-001 CLOSED；`CKPT-SW008-M2-V05B-001` | 9 项门禁全部通过 |
| 卡 060（V05-B2；SHA-256 前 8 位 `bbe50730`） | `aeedf92f`（父 `5686bd9f`；6 路径；6 个文件，+321/−5） | CHG-SCPT-2026-387 completed | RUN-SW008-M2-V05B2-002 SUCCEEDED；WORK-SW008-M2-V05B2-002 CLOSED；`CKPT-SW008-M2-V05B2-002` | 9 项门禁全部通过 |
| 卡 062（M2-GOV-TD3R；SHA-256 前 8 位 `4637d6a4`） | `769f145d`（父 `aeedf92f`；1 路径；1 个文件，+8/−0） | CHG-DOCU-2026-019 completed | RUN-SW008-M2-TD3R-001 SUCCEEDED；WORK-SW008-M2-TD3R-001 CLOSED；`CKPT-SW008-M2-TD3R-001` | 9 项门禁全部通过 |
| 卡 063（V04-T；SHA-256 前 8 位 `e68ccf2b`） | `715713bb`（父 `769f145d`；2 路径；2 个文件，+109/−38） | CHG-SCPT-2026-388 completed | RUN-SW008-M2-V04T-001 SUCCEEDED；WORK-SW008-M2-V04T-001 CLOSED；`CKPT-SW008-M2-V04T-001` | 9 项门禁全部通过 |
| 卡 065（V06（钩子一半）；SHA-256 前 8 位 `a4d675aa`） | `c3c20e07`（父 `715713bb`；1 路径；1 个文件，+199/−0） | CHG-SCPT-2026-390 completed | RUN-SW008-M2-V06-001 SUCCEEDED；WORK-SW008-M2-V06-001 CLOSED；`CKPT-SW008-M2-V06-001` | 9 项门禁全部通过 |
| 卡 064（V05-B3；SHA-256 前 8 位 `85573204`） | `4d0b33ac`（父 `c3c20e07`；2 路径；2 个文件，+98/−0） | CHG-SCPT-2026-389 completed | RUN-SW008-M2-V05B3-002 SUCCEEDED；WORK-SW008-M2-V05B3-002 CLOSED；`CKPT-SW008-M2-V05B3-002` | 9 项门禁全部通过 |
| 卡 066（M2-GOV-TD4；SHA-256 前 8 位 `5f21aa5e`） | `23e6ed64`（父 `4d0b33ac`；1 路径；1 个文件，+3/−3） | CHG-DOCU-2026-020 completed | RUN-SW008-M2-TD4-001 SUCCEEDED；WORK-SW008-M2-TD4-001 CLOSED；`CKPT-SW008-M2-TD4-001` | 9 项门禁全部通过 |
| 卡 067（M2-GOV-TD5；SHA-256 前 8 位 `b0aa03e8`） | `6a84a186`（父 `23e6ed64`；1 路径；1 个文件，+3/−0） | CHG-DOCU-2026-021 completed | RUN-SW008-M2-TD5-001 SUCCEEDED；WORK-SW008-M2-TD5-001 CLOSED；`CKPT-SW008-M2-TD5-001` | 9 项门禁全部通过 |
| 卡 068（V06B；SHA-256 前 8 位 `7b2132bd`） | `592211ee`（父 `6a84a186`；3 路径；3 个文件，+230/−0） | CHG-SCPT-2026-391 completed | RUN-SW008-M2-V06B-001 SUCCEEDED；WORK-SW008-M2-V06B-001 CLOSED；`CKPT-SW008-M2-V06B-001` | 9 项门禁全部通过 |
| 卡 069（M2-GOV-TD6；SHA-256 前 8 位 `1b57f967`） | `06f4ae4d`（父 `592211ee`；1 路径；1 个文件，+9/−4） | CHG-DOCU-2026-022 completed | RUN-SW008-M2-TD6-001 SUCCEEDED；WORK-SW008-M2-TD6-001 CLOSED；`CKPT-SW008-M2-TD6-001` | 9 项门禁全部通过 |
| 卡 070（V06C；SHA-256 前 8 位 `6f6f7a1d`） | `83369f67`（父 `06f4ae4d`；2 路径；2 个文件，+205/−11） | CHG-SCPT-2026-392 completed | RUN-SW008-M2-V06C-001 SUCCEEDED；WORK-SW008-M2-V06C-001 CLOSED；`CKPT-SW008-M2-V06C-001` | 9 项门禁全部通过 |
| 卡 071（V06D；SHA-256 前 8 位 `26d712fd`） | `3bc740a4`（父 `83369f67`；1 路径；1 个文件，+87/−3） | CHG-SCPT-2026-393 completed | RUN-SW008-M2-V06D-001 SUCCEEDED；WORK-SW008-M2-V06D-001 CLOSED；`CKPT-SW008-M2-V06D-001` | 9 项门禁全部通过 |
| 卡 072（F01-1；SHA-256 前 8 位 `35529109`） | `763395e4`（父 `3bc740a4`；4 路径；4 个文件，+179/−6） | CHG-SCPT-2026-394 completed | RUN-SW008-M2-F011-001 SUCCEEDED；WORK-SW008-M2-F011-001 CLOSED；`CKPT-SW008-M2-F011-001` | 9 项门禁全部通过 |

**口径更正与区分。** ① V06：卡 065 只做了钩子一半；判卷反例一半由 V06B 入库、V06C 收紧，钩子侧的证明缺口由 V06D 补强；WBS 层面的 V06 以三次独立审计后的残余为准——双根（linked-worktree 与控制根）路由和预检内部故障分支未覆盖（TD-SW008-100）、判卷器只证明报告字节一致而不证明报告内容实质（TD-SW008-099 的更深一层）、变异分类器与封存工具仍在不进 Git 的外部目录（TD-SW008-096）。② V05-B3 修复的 TD-SW008-091 已写已偿还，但 GPT R4-05 指出其证明强度低于措辞（写入比较只比行数、没有真实销毁窗口），措辞已在台账收窄并登记补证（TD-SW008-102）；F01-1 已补完整数据库内容比较与真实窗口关闭实演。③ F01-a 的台账 TD-SW008-078 写活动而非已偿还：已进入 HEAD 的删除认不出、部分分支缺直接变异证据、合法移动与退役入口属 F01-b。④ V05-C 尚未进行：前面各卡用的是无界面窗口与受控替身，可见窗口与真实模型联验由 V05-C 交付。⑤ 首次受治理执行失败的记录（V05-B2 首次 CHG-SCPT-2026-386、V05-B3 首次 Run、GPT 起草的 TD3 卡留下的 CHG-DOCU-2026-018 等）全部原样保留，处置须先提方案并经用户批准。

**三次独立审计与处置。** ① GPT R2（`.auto-pm/reports/m2-gpt-r2-20261007/AUDIT_REPORT_GPT_R2.md`）对 P1 修复、F01-a、V05-A、V05-B 与 V05-B2 冻结字节的审计：发现关闭后最终验收仍先写入、启动任务迟到信号无关闭抑制等，登记 TD-SW008-091～094，V05-B3 修复前两项。② Astra 里程碑只读审计（`.auto-pm/reports/astra-milestone-audit-20261008/`）：确认两项固定源码缺口——关闭后遗漏的写入口（`confirmStart` 无关闭检查，登记 TD-SW008-098，由 F01-1 修复）与缺失版本字段被默认补值（并入 TD-SW008-094，由 F02 修复）；另给出文档对账九份草案（由 M2-GOV-DOCS 采纳）、耦合治理方案（M2-B1 只做首个小切片）与技术债状态核验。③ GPT R4（`.auto-pm/reports/m2-gpt-r4-20261008/AUDIT_REPORT_GPT_R4_V06.md`）对 V06 两半的审计：1 项阻断（基线例外不要求真实、正确绑定的复现证据，登记 TD-SW008-099，V06C 收紧）、4 项重要（暂存区只比文件名与跨项目反例缺失登记 TD-SW008-100，由 V06D 补；TD-SW008-091 证明偏弱登记 TD-SW008-102；报告只证字节一致登记于 099）、3 项次要与 1 项观察（101 与 096）；三份报告的处理决定见 `.auto-pm/reports/m2-relay/DECISIONS_20261008.md` 与 `ASTRA_AUDIT_RECEIPT_20261008.md`。GPT 只做审计，不实现，不替用户验收。

**授权记录（用户 2026-10-08 对话原话，逐字记录在 `.auto-pm/reports/PREAUTH_M2_20261008.txt`）。** ① V06C、V06D、F01-1、F02 四张卡的有条件预授权（卡 SHA 先在聊天报出、字节一致、机器预检通过、范围不超出卡路径；门禁失败即停；验收与变更单收口委托，条件为 G1～G9 全过且提交与 Checkpoint 一致；止损照旧）。② V05-C 的真实模型调用：合计不超过 20 次、累计不超过 90 分钟、模型用 Sol 不用 Astra；确认电脑不休眠，PLC 演练接受 V02 的工程。③ 接受本 WBS 修订 7。预授权不含：规则修订卡、分档器卡、V04-R1、V05-C 的卡本身、技术性部署、推送、合并与文档采纳，这些仍须逐张报 SHA 并经用户批准。

**新任务行与新顺序。** §4.7.1 新增 `M2-GOV-TD3R`、`M2-GOV-TD4`、`M2-GOV-TD5`、`M2-GOV-TD6`、`M2-GOV-WBS7`、`M2-GOV-RULE`、`M2-TOOL-TIER`、`M2-GOV-DOCS`、`M2-B1`、`M2-DEP-TECH`、`M2-PUSH`；§4.8 新增 `V05-B2`、`V05-B3`、`V06B`、`V06C`、`V06D`、`M2-F011`、`M2-F02`，并补充 V05-C 与 V06 的文字。顺序：F02 → 规则修订与分档器 → V04-R1 → V05-C → 文档采纳与 WBS 终稿 → B1 小切片 → V07、V08、F01-b → GPT 对 M2（并回溯 M1、M0）的最终审计 → 开发运行时技术性部署 → 以 M2 作隔离候选 → 一次推送。

**部署意图（用户 2026-10-08）。** 把 M2 成果构建成发布包、装进开发运行时做一次技术性切换（仿 `M2-GOV-DEP1`，含回退演练），然后以 M2 作为隔离候选，再一次推送。三步各自须用户批准：技术性部署须报卡 SHA 并经批准；推送须用户在对话中另行明确授权，目前没有任何推送授权；合并 main 仍等到 M3 的 D03；技术性部署不等同 D07 正式交付。

**M3 候选（未排期、未批准，不计入任务行；M2 收口后出可批准的规划）。** ① 业务缺口：界面设计闭环（原型预览、批准、截图对比）、博图或 InoProShop 编译报错的结构化反馈通道、图与文档一致性检查（图能渲染、与接口表和变量表一致）、PLC 仿真门（PLCSIM 或软 PLC）、上位机与 PLC 的通信回环联调、客户文档结构化入口。② 治理成本：不降门槛，降单卡搭建成本——卡工厂（从一份配置生成整套门禁工具，对应 TD-SW008-088）、分档器（M2-TOOL-TIER）、按执行器的信任档（新接入的模型或 Agent 先用受限档：小范围、仅文档档或测试档、沙箱、无批准权、变异与独立审计必过；对应 TD-SW008-084）。③ 其余：完整挂起与抢占（V3.0.22 已分期）、线程亲和检查、暂停状态的统一拒写、多项目与多人协作。

**提速测量结论（2026-10-08，`.auto-pm/reports/m2-speedup/`）。** core 组并行 4 进程两次分别耗时 57 分钟与 85 分钟（第一次多出一个对并行敏感的失败），串行逐项计时一次 2 小时 16 分（失败集合与基线相同）；最慢 60 项约占 45%，集中在真实多进程链路类测试；串行测量期间我同时跑了其他任务，耗时有并发污染，真热点须在空闲机器上重测（M2-TOOL-TIER 的任务）。结论：并行不能无条件写进规则，更稳的方向是按改动范围选测试、发布前再全跑。

**技术基线更新（M2 代码线）。** 代码线唯一尖端由 TD2 `1956dd9a` 变为 `763395e4`（分支 `codex/m2-f011-closing-seal`），逐个核对父子相连（核对结果：相连）；后继任务从该提交或经独立验收的后继开始。未合并 main、未推送；开发运行时 `1.3.3-a808fa8`。

| 序 | 标签 | 提交 | 父提交 |
|---|---|---|---|
| 1 | TD2 | `1956dd9a` | `948884db` |
| 2 | F01A | `01ad3923` | `1956dd9a` |
| 3 | V05A | `5a2f9c48` | `01ad3923` |
| 4 | V05B | `5686bd9f` | `5a2f9c48` |
| 5 | V05B2 | `aeedf92f` | `5686bd9f` |
| 6 | TD3R | `769f145d` | `aeedf92f` |
| 7 | V04T | `715713bb` | `769f145d` |
| 8 | V06 | `c3c20e07` | `715713bb` |
| 9 | V05B3 | `4d0b33ac` | `c3c20e07` |
| 10 | TD4 | `23e6ed64` | `4d0b33ac` |
| 11 | TD5 | `6a84a186` | `23e6ed64` |
| 12 | V06B | `592211ee` | `6a84a186` |
| 13 | TD6 | `06f4ae4d` | `592211ee` |
| 14 | V06C | `83369f67` | `06f4ae4d` |
| 15 | V06D | `3bc740a4` | `83369f67` |
| 16 | F011 | `763395e4` | `3bc740a4` |

**任务表计数。** §4.2～§4.10 各表按 ID 行机器计数：V3.0.22 为 132 行，本修订后为 150 行（新增 18 个 ID，见上）。

**时点证据（2026-10-08T16:28:17-07:00）。**

| 指标 | 当前值 | 采集方法 |
|---|---|---|
| 主工作区 HEAD / 分支 | `a84fd7ee` / `codex/c09-recovery-governance` | `git rev-parse HEAD`、`git branch --show-current` |
| active / previous release | `1.3.3-a808fa8` / `1.3.3-0b72499` | 读 `active_release.json`、`previous_release.json` |
| canonical 事件数 / 链断裂 | 3421 / 0 | 只读连接逐条复算前后哈希 |
| SW008 未终结 Mission | 0 | `select count(*) from mission_items …`（只读） |
| SW008 未关闭 CHG | 76（另有 4 个格式异常的归档文件无法解析） | 逐文件读“变更状态”字段 |
| 工作树数量 | 179 | `git worktree list --porcelain` |
| 台账 SW-2026-008 / SYS-2026-001 | 均 0/0/0 | `main.py ledger reconcile <PID>` |
| 活动技术债台账行数 / 最后编号 | 110 / TD-SW008-102 | 读尖端提交里的台账 |

**教训沉淀（V3.0.23）。** ① 卡工具的身份（卡号、分支、Run、幂等键、计数）分散在多处手改，派生新卡时反复出现残留与改错（分支名被前一个替换改坏、卡文件名未换、判卷计数忽略多组变异）；解法是单一配置加生成器，并让工具自检残留，不是降低标准。② 夹具陷阱要在写测试前探测：两个项目的变更单编号各自从 001 起，用“001”当“他项目变更单”实际两边都有；探测发现后改用只存在于另一个项目的编号。③ 门禁的计数要按“命名组的运行次数”而不是“变异个数”。④ 全量测试对机器负载敏感，重门禁期间不并发其他重任务，演练也不与测量并跑。⑤ 独立审计找到了我自己漏掉的相邻入口与证明偏弱之处，交叉审计（谁也不审自己写的）是必要的，不是形式。

**技术债登记（增补）。** 本修订不新增债务编号；TD-SW008-098、102 在代码侧已由 F01-1 处置，台账状态留待下一张台账同步卡更新（不在本卡）；本期台账变化：TD3R 追加 087～094，TD4 更新 081、091、092 的状态，TD5 追加 095～097，TD6 追加 098～102 并更新 078、091、094、096，见各卡。

**后续顺序。** F02 → 规则修订与分档器 → V04-R1 → V05-C → 文档采纳与 WBS 终稿 → B1 → V07/V08/F01-b → GPT 最终审计 → 技术性部署 → 隔离候选 → 一次推送。本修订不授权任何后续任务开工、合并 main、推送、部署或 release 切换。

#### 4.7.9 F02 至分档器的验收回写；N1a 与 N2-0 的结果；M2 冻结条款、剩余清单与延期承诺表（V3.0.24，2026-10-09）

本节由 `M2-GOV-WBS8`（卡 081）追加，只加不删；V3.0.23 及更早的文字保留，仅修改卡 081 §5 列明的行。所有 SHA、ID 与状态均在 2026-10-09T11:10:39-07:00 只读采集（`.auto-pm/reports/m2-wbs8/collect_facts8.py`，输出 `facts8.json`）；文中时间均为用户所在地的本地时间（UTC-7）。V3.0.23 本身（提交 `a538f942`，CHG-DOCU-2026-029 completed）此前不在 M2 主链上，本卡一并采纳，所以相对主链上 V3.0.11 的差异很大；第 8 次修订独有的部分是本节、§4.11 的冻结条款与上面列明的行。第 8 次修订是**最小版**：用户 2026-10-09 决定 GPT 的设计不算 M2，E 链拆分、V04-R1 拆分、D08 新增项、N 系列等处置都不写进 M2 的 WBS，留给 M3 规划（见 `.auto-pm/reports/WBS_REVISION_PROPOSAL_20261009_V0.2.md` 与 `.auto-pm/reports/REQUIREMENT_POOL.md`）。

**验收证据（经受治理执行：Work/Run/Checkpoint、提交字节等于 Checkpoint、G1～G9 全部通过；验收与变更单收口由用户按 2026-10-08、2026-10-09 的有条件预授权委托 Claude 代为运行脚本，逐卡原话与回执见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 与各卡 `acceptance_receipt.txt`）。**

| 卡 | 不可变提交 | CHG | Run / Work / Checkpoint | 门禁 |
|---|---|---|---|---|
| 卡 074（F02；SHA-256 前 8 位 `0045da34`） | `98c2110d`（父 `763395e4`；10 路径；10 个文件，+319/−39） | CHG-SCPT-2026-395 completed | RUN-SW008-M2-F02-002 SUCCEEDED；WORK-SW008-M2-F02-002 CLOSED；`CKPT-SW008-M2-F02-002` | 9 项门禁全部通过 |
| 卡 075（V05-C；SHA-256 前 8 位 `604f3f9f`） | `6e17f086`（父 `98c2110d`；1 路径；1 个文件，+525/−0） | CHG-SCPT-2026-396 completed | RUN-SW008-M2-V05C-002 SUCCEEDED；WORK-SW008-M2-V05C-002 CLOSED；`CKPT-SW008-M2-V05C-002` | 9 项门禁全部通过 |
| 卡 076（M2-GOV-TD7；SHA-256 前 8 位 `863daef6`） | `c8d49c29`（父 `6e17f086`；1 路径；1 个文件，+12/−7） | CHG-DOCU-2026-023 completed | RUN-SW008-M2-TD7-001 SUCCEEDED；WORK-SW008-M2-TD7-001 CLOSED；`CKPT-SW008-M2-TD7-001` | 9 项门禁全部通过 |
| 卡 077（M2-GOV-RULE；SHA-256 前 8 位 `1ac7d8a4`） | `a0ac852b`（父 `c8d49c29`；1 路径；1 个文件，+15/−0） | CHG-DOCU-2026-024 completed | RUN-SW008-M2-RULE-001 SUCCEEDED；WORK-SW008-M2-RULE-001 CLOSED；`CKPT-SW008-M2-RULE-001` | 9 项门禁全部通过 |
| 卡 078（M2-TOOL-TIER；SHA-256 前 8 位 `f7f89abc`） | `370e0297`（父 `a0ac852b`；3 路径；3 个文件，+683/−0） | CHG-SCPT-2026-398 completed | RUN-SW008-M2-TIER-001 SUCCEEDED；WORK-SW008-M2-TIER-001 CLOSED；`CKPT-SW008-M2-TIER-001` | 9 项门禁全部通过 |

**等待用户验收的两项（不委托）。** N1a（卡 079）：提交 `388b22c4`（父 `370e0297`，1 个新增文件），`CKPT-SYS001-M2-N1A-001`，RUN-SYS001-M2-N1A-001 SUCCEEDED、WORK-SYS001-M2-N1A-001 CLOSED，CHG-DOCU-2026-031 停在 implementing，等用户通读后说“内容是我的意思”再收口。N2-0（卡 080）：只读勘测，成果是 `.auto-pm/reports/m2-n20/N2-0_SURVEY_REPORT.md`（SHA-256 前 8 位 `1352e908`），RUN-SW008-M2-N20-001 SUCCEEDED、WORK-SW008-M2-N20-001 CLOSED，CHG-DOCU-2026-025 停在 implementing，等用户读报告后验收。

**租约过期的结算（方案 A，用户 2026-10-08 确认）。** V05-C 第一轮（RUN-SW008-M2-V05C-001）与 WBS 修订 7 的第一次运行（RUN-SYS001-M2-GOV-WBS7-001）都因租约过期而作废；两条旧 Run 与旧 Work 均已以 CANCELLED 结算，恢复链为 RUN-SW008-M2-SETTLE-V05C-001（CHG-SCPT-2026-397）与 RUN-SYS001-M2-SETTLE-WBS7-001（CHG-DOCU-2026-030），Decision 已绑定提交 `3f4fff29`、`5feb8e93`；历史原样保留，不改写。V05-C 第二轮（RUN-SW008-M2-V05C-002）通过。

**授权与决定记录（用户对话原话逐字记录在 `.auto-pm/reports/PREAUTH_M2_20261008.txt`）。** ① 2026-10-09 白天预授权：V05-C 收口、结算方案 A、TD7、规则修订、分档器。② 路线定向：驾驶舱是“守门人/管理者”，配合用户选的 IDE、Agent 与模型使用；用户个人介入每张低风险卡不超过 3 次；不再就路线与 GPT 往返；批准 N1a + N2-0 批次。③ M2 按原承诺收口，批准按 V0.2 起草 WBS 修订。④ 尽快完成 M2 后做技术部署，基线必须冻结。⑤ 开工信号：GPT 的设计不算 M2，V04-R1（整张）、V07、V08、M2-F01B、M2-B1、文档采纳后移到 M3；WBS 第 8 次修订缩成最小版，并与采纳 V3.0.23 合为一张卡；M2 剩余为最小 WBS 文档卡、ADJ/IC02 整合、审计包、GPT 审计（发现缺陷按冻结条款修）、技术部署（审计之后用户再明确批准）、推送（用户另行授权）；最小 WBS 文档卡与 ADJ/IC02 整合两张卡预授权（先聊天报 SHA 等条件照旧），WBS 卡由用户验收一次，整合卡门禁全过且提交等于 Checkpoint 时可委托收口。本节不授权合并 main、推送、部署或 release 切换。

**N2-0 的发现与新增 `M2-DEP-INT`。** 发布 `1.3.3-a808fa8` 的源提交 `a808fa8a` 与 M2 代码线从 `7cfe227e` 分叉：发布线比分叉点多 3 个提交，M2 线多 44 个提交，发布源提交不是 M2 尖端的祖先。发布线里的 ADJ（`d876cf98`，`adjudicate_blocked_work`）与 IC02（`e6529115`，实施卡预检，强制接入 `continuity work create`）不在 M2 线上：M2 线里没有 `implementation_card_precheck.py`，`decision.py` 里没有 `adjudicate_blocked_work`。所以技术性部署之前必须先整合，新增任务 `M2-DEP-INT`（核心档；两线改过同一批文件，会有合并冲突）。它是部署前提任务，把已验收的两个功能带进 M2 线，不是债务偿还。依据 `.auto-pm/reports/m2-n20/N2-0_SURVEY_REPORT.md`（SHA-256 前 8 位 `1352e908`）。

**M2 冻结后的剩余清单与顺序（用户 2026-10-09 决定；逐张出卡，一次只激活一张，重门禁独占）。**

| 顺序 | 事项 | 说明 |
|---|---|---|
| 1 | `M2-GOV-WBS8`（本卡：最小 WBS 文档卡，采纳 V3.0.23 并写入 V3.0.24） | 已预授权；用户验收一次，收口不委托 |
| 2 | `M2-DEP-INT`（ADJ/IC02 整合，核心档） | 已预授权；门禁全过且提交等于 Checkpoint 时可委托收口 |
| 3 | 审计包 | 备好后交 GPT |
| 4 | GPT 对 M2 的最终审计 | 审计，不是路线讨论；发现缺陷按冻结条款修（修缺陷，不加功能） |
| 5 | `M2-DEP-TECH` 技术性部署（含回退演练） | 审计之后，用户再明确批准切换 |
| 6 | `M2-PUSH` 一次推送 | 用户另行明确授权目标与范围；目前没有任何推送授权 |

**延期承诺表（后移到 M3 不等于取消；D09 要求未达成的承诺不得移出验收表）。**

| 项 | 原目的 | 现处置 | 触发条件 |
|---|---|---|---|
| V04-R1（整张，不拆） | 受控租约撤销与 fencing 的真实进程演练 | 后移到 M3 | M3 规划时排序 |
| V07、V08 | 从基准提取 Python 与 PLC 模板 | 后移到 M3 | M3 规划时排序 |
| F01-b（任务 M2-F01B） | PLC 工程合法移动与退役入口 | 后移到 M3 | 用户批准范围后 |
| B1 小切片（任务 M2-B1） | 连续性存储三个纯哈希函数提取 | 后移到 M3 | M3 规划时排序 |
| 文档采纳（任务 M2-GOV-DOCS，9 份草案） | 项目关键文档按对账草案修订 | 后移到 M3 | M3 规划时排序 |

**技术基线更新（M2 代码线）。** 代码线唯一尖端由 F01-1 `763395e4` 变为 `388b22c43a334faf1e29d9bb0038150a403b17e3`（分支 `codex/m2-n1a-roles-doc`），逐个核对父子相连（核对结果：相连）；后继任务从该提交或经独立验收的后继开始。未合并 main、未推送；开发运行时 `1.3.3-a808fa8`，不含 M2 代码。

| 序 | 标签 | 提交 | 父提交 |
|---|---|---|---|
| 1 | F02 | `98c2110d` | `763395e4` |
| 2 | V05-C | `6e17f086` | `98c2110d` |
| 3 | M2-GOV-TD7 | `c8d49c29` | `6e17f086` |
| 4 | M2-GOV-RULE | `a0ac852b` | `c8d49c29` |
| 5 | M2-TOOL-TIER | `370e0297` | `a0ac852b` |
| 6 | M2-N1A | `388b22c4` | `370e0297` |

**任务表计数。** §4.2～§4.10 各表按 ID 行机器计数：V3.0.23 为 150 行，本修订后为 155 行（新增 5 个 ID：`M2-GOV-TD7`、`M2-N1A`、`M2-N2-0`、`M2-DEP-INT`、`M2-GOV-WBS8`）。

**时点证据（2026-10-09T11:10:39-07:00）。**

| 指标 | 当前值 | 采集方法 |
|---|---|---|
| 主工作区 HEAD / 分支 | `5feb8e93` / `codex/c09-recovery-governance` | `git rev-parse HEAD`、`git branch --show-current` |
| active / previous release | `1.3.3-a808fa8` / `1.3.3-0b72499` | 读 `active_release.json`、`previous_release.json` |
| 台账 SW-2026-008 / SYS-2026-001 | 均 0/0/0 | `main.py ledger reconcile <PID>` |
| 活动技术债台账最后编号 | `TD-SW008-107` | 读尖端提交里的台账 |

**教训沉淀（V3.0.24）。** ① 外部 Agent 的租约续期必须有明确的责任人，并在每次查看进度时先核对续租日志；V05-C 第一轮因续租循环的相对路径静默失败而作废，修复后的脚本先续租一次再睡眠、失败时大声报错。② 部署前先比较发布线与开发线的差异，不要假设后者包含前者（N2-0 的发现）。

**后续顺序。** 见上表。本修订不授权合并 main、推送、部署或 release 切换；这些仍须用户在对话中明确授权。

#### 4.7.10 M2-DEP-INT 的最终提交证明与状态写回（V3.0.25，2026-10-09）

本节由 `M2-GOV-WBS9`（卡 083）追加，只加不删。所有 SHA、ID 与状态均在 2026-10-09T18:32:15-07:00 只读采集（`.auto-pm/reports/m2-wbs9/collect_facts9.py`，输出 `facts9.json`）。

**为什么需要这一节。** GPT 最终审计（`.auto-pm/reports/m2-relay/m2-final-audit-20261009/gpt-output/AUDIT_REPORT_FINAL.md`，SHA-256 前 8 位 `66cc5dcd`）的阻断项 B-01 指出：连续性库里 `M2-DEP-INT` 的 Checkpoint 只绑定 Run 的启动基线 `f06c5aac` 与候选文件哈希，没有最终合并提交与树的 SHA，所以“提交等于 Checkpoint”无法从治理记录独立复核。这是该库的既有设计：`checkpoint.git_head` 必须等于 Run 的启动 `git_head`，Checkpoint 先于提交创建，故任何卡的 Checkpoint 都只能绑定启动基线（本线 46 张卡同此）。给治理库增加“最终提交”对象类型属于新增产品功能，不在 M2 冻结范围内，所以本节用 git 提交历史保证只追加的方式补上这条证明：**本节写入后不得改动其中任何 SHA；若需更正，只能追加新的证明节。**

**最终提交证明（RUN-SW008-M2-DEPINT-001）**

| 项 | 值 |
|---|---|
| Run / Work / 变更单 | RUN-SW008-M2-DEPINT-001 SUCCEEDED / WORK-SW008-M2-DEPINT-001 CLOSED / CHG-SCPT-2026-399 completed |
| Checkpoint | `CKPT-SW008-M2-DEPINT-001`，其 `git_head` 为启动基线 `f06c5aac08a90a3e089142f9d16cafdfead75452`（设计如此，见上） |
| 最终提交 | `1d0be4af46423b46b8521884aaca98c42943f8a8` |
| 第一父提交（基线，最小 WBS 卡） | `f06c5aac08a90a3e089142f9d16cafdfead75452` |
| 第二父提交（发布源） | `a808fa8a43335ceb5705d7384d2afbb0a12e412c` |
| 树 | `644c5732219f48b7863444b6e5cfddd166e7d3d7` |
| 判卷文件 | `.auto-pm/reports/m2-depint/gates/gate_verdict.json`，SHA-256 `9d2ac109dc11146a42b9fa30e52863f32802e5871d7a7f9249c0e69c24c51718`；门禁：G1 PASS、G2 PASS、G3 PASS、G4 PASS、G5 PASS、G6 PASS、G7 PASS、G8 PASS、G9 PASS |
| 合并可重现（G8） | 在一次性工作树里用同一条合并命令得到同一棵树 `644c5732219f48b7863444b6e5cfddd166e7d3d7`；MERGE_HEAD 等于发布源；无未合并路径、无冲突标记 |
| 工具与卡指纹 | 卡 082 SHA-256 `a183be0e65eea8042b1de4d312ff26ebc54dc3ba3fd94a09f841db4db2d47c0c`；工具清单 manifest SHA-256 `995560830741b7631324098fa3d7d08eb6205618e6d11b8b89d45e03851d4845` |

**20 个受控文件在最终提交里的 SHA-256**（与 Checkpoint 绑定的候选字节、卡 082 §5.1 表逐个相同）

| 路径（相对 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`） | SHA-256 |
|---|---|
| `auto_pm/application/core/continuity_execution_service.py` | `e96463fd1767e5132dce4c0662dd3a3f71d3546c6dca73d978bb8aea2c4bb09b` |
| `auto_pm/application/core/implementation_card_precheck.py` | `2b92e7f1a06ee4b9ed18117ca51bf6671a9051dc88d6cf9d9387f87d0402f297` |
| `auto_pm/application/core/implementation_card_service.py` | `32e110e6acebfd549ce6afa41dccb353e837739ff70c5b3a5e5f672d2f6102ff` |
| `auto_pm/application/core/work_registry_service.py` | `74c066bbd8cb4d35f9c5e38e29e61d85abdf25bd0cc67f02de19dd7109d5c753` |
| `auto_pm/contracts/implementation_card.py` | `b3b04730dfe4283a0f90b1c5215448f6614c128da64511bd93eb525cdfa72269` |
| `auto_pm/infrastructure/continuity_store.py` | `3e3ae1bddaa87588ad2069ce226a0a5d040d9d84a021e2ea638a011cf869f983` |
| `auto_pm/templates/governance/implementation_card.md.jinja` | `561b218fa48c3c69baf19707540c0f7aad3cfd432298ab016ec77410f937013f` |
| `auto_pm/ui/cli/continuity.py` | `8c5b02980670d94bd2836287f7753dfc976065b5a109686b759365e92ab1b087` |
| `auto_pm/ui/cli/decision.py` | `e2c0255a9db923cbadf5a36272ebd0faaa080059e38cba7173d844f45894cfd4` |
| `auto_pm/ui/cli/implementation_card.py` | `61aa2faff4c36214dd6cd2d9dac9357d33f54708b67cd9cd21ef3eaccaff2d09` |
| `tests/cli/test_continuity.py` | `1e4795db8b23b3d5877f0da422dd902b8b808da8a21656d63c3c6cc18d63b106` |
| `tests/cli/test_decision.py` | `98281a31fbd900c87af0e671e1d71573fad66e5de5e8a20757e52dc0874cf44d` |
| `tests/cli/test_implementation_card.py` | `4fef11cc8fbb54865dbf7707fca3343afb09027e12103ae3f3805124d006ed8b` |
| `tests/contracts/test_decision_package.py` | `6c4f201dc6a0c2b907d9cb4a002b24d986b56e29605a14410b4d1fad56f825e0` |
| `tests/contracts/test_implementation_card.py` | `0ee63e6d2fdba62a16eaa6f8a7308218b712f790daf3079850192ca27112757c` |
| `tests/core/test_implementation_card_precheck.py` | `b980eecbc55d61eefde9ea7e62cdf93c9b2a236763bb5017e9b26b32784d0b4e` |
| `tests/core/test_implementation_card_service.py` | `65a5598a7103d448991cfbc1e4b69513adf7ca306684f7ab86938ec4bb5c0fbb` |
| `tests/core/test_legacy_terminal_lease_fence.py` | `bd7959dc285bbd6f2ceb52c59628944a6c41f9dc784d7f56dc73d2fce6188394` |
| `tests/core/test_work_registry_service.py` | `4c4379b5328ca71a1e4c7e4b0fa8ebcb80a7e61821b0e9f01b6189eaddfc245c` |
| `tests/infrastructure/test_continuity_store.py` | `82674491ba625de454c2523b3c3d39eb750f2247ec77142a6bc99982c4ac2e1a` |

**怎样复核。** ① `git rev-list --parents -n 1 1d0be4af4642` 得到上表两个父提交；② `git rev-parse 1d0be4af4642^{tree}` 得到上表的树；③ 对每个路径执行 `git show 1d0be4af4642:<项目根>/<路径> | sha256sum` 得到上表 SHA-256；④ 判卷文件的 SHA-256 与上表相同。本卡的检查器在门禁里逐项做了这四步，并有三个反例各被拒绝：错误的提交、错误的树、任一文件字节漂移。

**对技术部署的要求。** 部署卡必须从提交 `1d0be4af`（或其后只含文档的后继提交）构建发布包，核对 `release_meta.json` 的 `source_commit` 与树，并把核对结果写进部署证据；切换前后的 active/previous 指针与实际加载身份一致。

**状态写回（用户 2026-10-09 验收）。** N1a（`388b22c4`，CHG-DOCU-2026-031）、N2-0（CHG-DOCU-2026-025）、最小 WBS 卡（`f06c5aac`，CHG-DOCU-2026-032）均已 completed；§4.7.9 里“等待用户验收的两项”是该修订写成时的状态，此后已验收。`M2-DEP-INT` 的变更单 CHG-SCPT-2026-399 已按用户的预授权（门禁全过且提交等于 Checkpoint 的文件字节）委托收口，用户可复核并推翻。

**本节不授权**：合并 main、推送、部署或 release 切换；这些仍须用户在对话中明确批准或授权。

#### 4.7.11 卡 083 验收、技术性部署与推送的状态写回（V3.0.26，2026-10-09）

本节由 `M2-GOV-WBS10`（卡 085）追加，只加不删。所有 SHA、ID 与状态均在 2026-10-09T20:57:03-07:00 只读采集（`.auto-pm/reports/m2-wbs10/collect_facts10.py`，输出 `facts10.json`）。**本节只写回已经发生并可核对的事实，不新增范围，不宣布 M2 里程碑验收。**

**写回的事实**

| 项 | 值 |
|---|---|
| 卡 083（最终提交证明） | 提交 `4b5c6307e814cd6bf17337f31ccd8c7e533553e1`（父 `1d0be4af46423b46b8521884aaca98c42943f8a8`）；CHG-DOCU-2026-033 completed（用户 2026-10-09 验收）；Run `RUN-SYS001-M2-GOV-WBS9-001` SUCCEEDED、Work `WORK-SYS001-M2-GOV-WBS9-001` CLOSED |
| 技术部署卡 | 卡 084 V1.1，SHA-256 `c4201956a4dd68db04be61a02f23888478d4fa20a961645d825d2d8f51e19024`；CHG-SCPT-2026-400 completed（按用户授权委托收口）；Decision `DEC-20261009-DTECHDPL` |
| 第一轮 | Run `RUN-SW008-M2-DEPTECH-001` FAILED / Work `WORK-SW008-M2-DEPTECH-001` CANCELLED：切换后核验判据“根入口身份核对 conflicts == []”遇到新旧运行时都存在的 `MULTIPLE_ACTIVE_WORKS`，按设计自动回退，指针恢复为切换前字节；证据 `.auto-pm/reports/m2-dep-tech/gate_b_round1/` |
| 第二轮 | Run `RUN-SW008-M2-DEPTECH-002` SUCCEEDED / Work `WORK-SW008-M2-DEPTECH-002` CLOSED，Checkpoint `CKPT-SW008-M2-DEPTECH-002`；用户同意把判据改为“冲突集合与切换前相同、无新增” |
| 部署结果 | active `1.3.3-4b5c630`、previous `1.3.3-a808fa8`（切换前：active `1.3.3-a808fa8`、previous `1.3.3-0b72499`）；release 的 `source_commit` 为 `4b5c6307e814cd6bf17337f31ccd8c7e533553e1`；manifest 条目 SHA-256 `f8cecee8d79ffd40c58d2fa577bf7f9f277b4152c50dbc1ef435f0544a79613e` |
| 切换后核验 | 身份核对：已配置版本等于实际加载版本、无降级；冲突集合与切换前相同（`MULTIPLE_ACTIVE_WORKS`，不是新版本引入）；resume 带 query 块；两项目台账 0/0/0；真实库证据命令 19/19 退出码 0；事件链 3634 条、0 处断裂；三个 release 的 exact-tree 全部通过；核验记录 SHA-256 `e682eb7fdadddd0964829ad76bc128ab178202dbd947eaf860f2b5925a2f5e84`，证据 `.auto-pm/reports/m2-dep-tech/gate_b/post_checks.txt` |
| 回退 | 命令 `bash .auto-pm/reports/dep1_release_ops.sh rollback /c/Users/fubai/Documents/My_Workspace /c/Users/fubai/Documents/My_Workspace/.auto-pm/reports/m2-dep-tech/gate_b/pointer_backup_20261010T030915Z`；数据库未回退，切换前备份见 `.auto-pm/reports/m2-dep-tech/gate_b/` |
| 推送 | 分支 `codex/m2-gov-wbs9-attest` → origin，提交 `4b5c6307e814cd6bf17337f31ccd8c7e533553e1`；2026-10-09T20:22:07-07:00（本地 reflog 记录）；新分支，未推 main，未强推；`origin/main`（`e83c117d`）是该提交的祖先 |
| 合并 main | 未合并（§4.11 与 §4.7.9：合并 main 等到 M3 的 D03；技术部署不需要合并） |

**未随本修订改变的事项**

1. 历史遗留的 5 个未终结 Work（`WORK-SW008-M2-F02-001`（BLOCKED）、`WORK-SW008-M2-P1-AUDITFIX-001`（BLOCKED）、`WORK-SW008-M2-TD3-001`（READY）、`WORK-SW008-M2-V05B2-001`（BLOCKED）、`WORK-SW008-M2-V05B3-001`（BLOCKED））使 `pm resume` 在新旧运行时下都报 `MULTIPLE_ACTIVE_WORKS`；用户要求原样保留，M3 再议，本修订不处置。
2. D07（受控稳定交付）、D08（连续三次真实日常交付）与 V04-R1、V07、V08、M2-F01B、M2-B1、文档采纳仍按 §4.7.9 的延期承诺表在 M3；冻结条款（§4.11）与 D08 不变。
3. M2 里程碑验收由用户在对话中决定；本节与当前投影只记录“M2 已授权的工作项均已完成”，不写 `ACCEPTED`。

**本节不授权**：合并 main、再次推送、再次部署、release 切换、任何债务或历史失败记录的处置。

#### 4.7.12 发布治理整顿批次（卡 085～094）的状态写回与历史队列核对（V3.0.27，2026-10-10）

本节由 `M2-GOV-WBS11`（卡 095）追加，只加不删。所有 SHA、ID 与状态均在 2026-10-10T09:23:59-07:00 只读采集（`.auto-pm/reports/m2-wbs11/collect_facts11.py`，输出 `facts11.json`），Run、Work 与变更单状态读自治理库与变更单文件。**本节只写回已经发生并可核对的事实，不新增范围，不宣布 M2 里程碑验收，不替用户验收任何变更单。**

**批次任务与状态**（卡 094 先于卡 093 提交，编号不代表顺序）

| 卡 | 项目 | 提交 | 父提交 | 变更单 | 变更单状态 | Run | Work | 结果 |
|---|---|---|---|---|---|---|---|---|
| 卡 085（`M2-GOV-WBS10`） | SYS-2026-001 | `aa02be02` | `4b5c6307` | CHG-DOCU-2026-034 | completed | `RUN-SYS001-M2-GOV-WBS10-001` SUCCEEDED | `WORK-SYS001-M2-GOV-WBS10-001` CLOSED | WBS V3.0.26：写回卡 083 验收、技术性部署与推送 |
| 卡 086（`M2-GOV-TD8`） | SW-2026-008 | `425f8b09` | `aa02be02` | CHG-DOCU-2026-026 | completed | `RUN-SW008-M2-TD8-001` SUCCEEDED | `WORK-SW008-M2-TD8-001` CLOSED | 台账登记 TD-SW008-108～114，更新 009/019/026 |
| 卡 087（`M2-RGOV-0`） | SW-2026-008 | — | — | CHG-DOCU-2026-027 | completed | `RUN-SW008-M2-RGOV0-001` SUCCEEDED | `WORK-SW008-M2-RGOV0-001` CLOSED | 只读盘点：CHG 冻结清单、release 清单、暴露面扫描（无提交） |
| 卡 088（`M2-GOV-CHGIMP`） | SW-2026-008 | `5b7056d2` | `425f8b09` | CHG-DOCU-2026-028 | completed | `RUN-SW008-M2-CHGIMP-001` SUCCEEDED | `WORK-SW008-M2-CHGIMP-001` CLOSED | 227 个变更单与台账文件入库（本地分支，未推送） |
| 卡 089（`M2-GOV-TD9`） | SW-2026-008 | `6e250842` | `5b7056d2` | CHG-DOCU-2026-029 | implementing | `RUN-SW008-M2-TD9-001` SUCCEEDED | `WORK-SW008-M2-TD9-001` CLOSED | 台账更新 108/109/111～113，登记 115～117 |
| 卡 090（`M2-RGOV-1`） | SW-2026-008 | — | — | CHG-DOCU-2026-030 | implementing | `RUN-SW008-M2-RTAG-001` SUCCEEDED | `WORK-SW008-M2-RTAG-001` CLOSED | 15 个本地带注解 release 源码 tag（无提交，未推送） |
| 卡 091（`M2-GOV-RANN`） | SW-2026-008 | `5c157f73` | `6e250842` | CHG-DOCU-2026-031 | implementing | `RUN-SW008-M2-RANN-001` SUCCEEDED | `WORK-SW008-M2-RANN-001` CLOSED | release 更正与标注记录 |
| 卡 092（`M2-GOV-RTOOL`） | SW-2026-008 | `11a829c1` | `5c157f73` | CHG-DOCU-2026-032 | implementing | `RUN-SW008-M2-RTOOL-001` SUCCEEDED | `WORK-SW008-M2-RTOOL-001` CLOSED | 锁定依赖 108 项与环境记录 |
| 卡 094（`M2-GOV-GIGN`） | SW-2026-008 | `8cb8dceb` | `11a829c1` | CHG-DOCU-2026-033 | implementing | `RUN-SW008-M2-GIGN-001` SUCCEEDED | `WORK-SW008-M2-GIGN-001` CLOSED | .gitignore 追加压缩包与备份包规则 |
| 卡 093（`M2-GOV-TRK`） | SW-2026-008 | `7506af72` | `8cb8dceb` | CHG-SCPT-2026-401 | implementing | `RUN-SW008-M2-TRK-001` SUCCEEDED | `WORK-SW008-M2-TRK-001` CLOSED | 变更单入库检查工具与 9 个测试节点 |

**结果清单**

| 项 | 值 |
|---|---|
| 本地 release 源码 tag | 15 个带注解的本地 tag `release-src/<release-id>`（卡 090），清单 `.auto-pm/reports/m2-rtag/out/tags.json`（SHA-256 `8d769b2a46334809ff72c89c6741bca0ac122a826801bc974b3f13a4ec414541`）；**未推送** |
| release 标注记录 | `00_Infrastructure/auto_pm/release_annotations.json`（卡 091），SHA-256 `19eab043aac904edb44cbfa1d982e8661c091134d12a2dddca8a398867307168` |
| 锁定依赖与环境记录 | `00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt`（SHA-256 `53b75f3feee2fe455c29231a0c3678850022bbe4259438793bc33dec60f7671b`）与 `00_Infrastructure/auto_pm/environment/environment_record.json`（SHA-256 `938316fc76483bae3805781fa1d4df578c345d3a9f4d418d32c37a1ae1c079c5`）（卡 092） |
| 忽略规则 | `.gitignore`（卡 094），SHA-256 `c91f63361ac77fc6a3c8b8ebd5a07b0c05a38cac2fdeafc63abdc13ba646e459` |
| 变更单入库检查工具 | `tests/tools/chg_tracking_check.py`（卡 093），SHA-256 `f8c2a8867080b175656ae32c1b8c7239fdd428ed195af34a8a8352752d537a9f` |
| 检查工具的真实试跑 | 对控制根与分支 `codex/m2-trk-check`：检查 496 个变更单文件，24 个不在该分支的提交里、0 个被改动；输出 `.auto-pm/reports/m2-wbs11/tracking_run.json`（SHA-256 `754fb3e34f46427f0186f7c27a52b9d79d60728f9e0d0aec80bf2974e08d0c15`） |

**历史队列 H02～H10 的只读核对**（2026-10-10 07:40 核对，证据 `.auto-pm/reports/H_QUEUE_CHECK_20261010.md`，SHA-256 `900747e40cef1c378d37bee1877d01bb0baaffa5902df099b5e18928a862965d`；Run 与 Work 状态为采集时现读）

| 队列 | 对象 | 当前状态 | 判断 |
|---|---|---|---|
| 队列 H02 | `RUN-SW008-R4-215-IMPL-01` / `WORK-SW008-R4-215-IMPL` | Run CANCELLED，Work CANCELLED | 已达终态，无需再处置 |
| 队列 H03 | `RUN-SW008-SAFE-004-ACL-01` / `WORK-SW008-SAFE-004-ACL` | Run CANCELLED，Work CANCELLED | 已达终态，无需再处置 |
| 队列 H04 | `RUN-SW008-A2-201-04` / `WORK-SW008-A2-201-R2` | Run VERIFYING，Work ACCEPTED | 未处置：过期非终态 Run，待按 H01 机制结算（需用户批准） |
| 队列 H05 | `RUN-SW008-A2-201-03` / `WORK-SW008-A2-201-R2` | Run RUNNING，Work ACCEPTED | 未处置：同 H04 |
| 队列 H06 | `RUN-SW008-A2-201-01` / `WORK-SW008-A2-201` | Run BLOCKED，Work CANCELLED | 未处置：过期非终态 Run，待结算（需用户批准） |
| 队列 H07 | `RUN-SW008-REC-001-06` / `WORK-SW008-REC-001` | Run SUCCEEDED，Work CANCELLED | Work 已达终态（以取消收口）；WBS 要求的“具名剩余项”是否保留未核对 |
| 队列 H08 | 工作树 `.auto-pm/worktrees/codex-a2-pm-facade`（HEAD `06782f4d`） | 仍存在且洁净；提交已被 origin 分支包含 | 未处置：依赖 H04～H06 先结算，退役须用户批准目录处置 |
| 队列 H09 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/archive/PMF-20260912` | 目录存在，8 个源文档已从原位置删除；对该目录没有任何提交 | 已移动、未提交：归档闭环缺最后一步（独立提交清单，需用户批准） |
| 队列 H10 | `.auto-pm/worktrees/wbs8-candidate` | 是普通目录，不是 Git 工作树 | 用途已判明（普通目录）；保留或隔离标签的书面记录未见 |

**未随本修订改变的事项**（均需用户另行裁决，不在 M2 已授权范围内）

1. 上表中 卡 089、卡 090、卡 091、卡 092、卡 094、卡 093 的变更单停在 implementing，等用户阅读后验收；本修订不替用户验收。
2. 本批次的提交都在本地分支，没有任何推送；15 个 release 源码 tag 与变更单入库提交是否推送、仓库是否转私有，由用户在待办完成后决定。
3. 检查工具发现的 24 个不在提交里的变更单（今天新建的变更单、SW-2026-009 与 PLC 项目的变更单）如何入库，另行立卡；PLC 项目的变更单入库仍等用户裁决。
4. 已入库却命中忽略规则的 996 个文件是否移出跟踪，等用户分类裁决；历史清理或重写不在任何已批准范围内。
5. 历史队列 H04～H06、H08、H09 的处置需用户另行批准；5 个历史未终结 Work（`MULTIPLE_ACTIVE_WORKS`）按用户要求原样保留，M3 再议。
6. D07、D08、V04-R1、V07、V08、M2-F01B、M2-B1 与文档采纳仍按 §4.7.9 的延期承诺表在 M3；冻结条款（§4.11）与 D08 不变。M2 里程碑验收由用户在对话中决定。

**本节不授权**：合并 main、任何推送、部署、release 切换、任何债务或历史失败记录的处置。

#### 4.7.13 M2 里程碑验收、M3 启动与第一日批次（卡 099～103）（V3.0.28，2026-10-11）

本节由 `M2-GOV-WBS12`（卡 104）追加，只加不删。所有 SHA 与状态在 2026-10-11 只读采集（提交读自 git，变更单状态读自变更单文件，Run/Work 读自治理库的收口回执）。

**1. M2 里程碑验收**：用户 2026-10-11 在对话中宣布 M2 里程碑验收（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾）。M2 的全部工作项已完成：开发运行时 `1.3.3-4b5c630` 已技术性部署，M2 隔离候选分支已推送（未合并 main），发布治理整顿批次（卡 085～094）与卡 095、096～098 的变更单均 completed。**验收不授权**：合并 main、任何推送（含 tag）、转私有、D07 切换与 release 切换仍是独立边界，各自需要用户另行授权。验收时仍然开放并**带入 M3** 的事项：历史队列 H04～H06、H08、H09 的处置（§4.7.12）、历史遗留的 5 个未终结 Work（`MULTIPLE_ACTIVE_WORKS`，按用户要求原样保留）、台账中仍为活动或待执行的债务（见 `活动技术债台账.md`）、V04-R1、V07、V08、M2-F01B、M2-B1、M2-GOV-DOCS（延期承诺表 §4.7.9）。

**2. M3 启动**：当前投影 M3 行由 `NOT_STARTED` 改为 `IN_PROGRESS`。M3 的任务清单仍以 §4.9（D01～D09）与 §4.3.1（Q01～Q03）及延期承诺表为准；本修订不新增产品需求。

**3. 第一日批次（卡 099～103）**：全部在本地线性分支上，G1～G9 全部 PASS；变更单均 completed（卡 099、100 由用户亲自验收，卡 101～103 由用户委托验收，委托条件为 G1～G9 全 PASS 且提交字节等于冻结清单，均已满足）。卡 100 V1.0 因 rest 组一个瞬时竞态测试在 G2 失败而作废（Run FAILED、Work CANCELLED，登记为 TD-SW008-120），V1.1 通过。

| 卡 | 提交 | 父提交 | 变更单 | 状态 | Run | Work |
|---|---|---|---|---|---|---|
| 卡 099（`M2-GOV-CHGSYNC`） | `fea74b33` | `0d22fdd0` | CHG-DOCU-2026-036 | completed | `RUN-SW008-M2-CHGSYNC-001` SUCCEEDED | `WORK-SW008-M2-CHGSYNC-001` CLOSED |
| 卡 100（`M2-GOV-MRG1`） | `bf19b6bd` | `fea74b33` + `657f3dc5` | CHG-SCPT-2026-403 | completed | `RUN-SW008-M2-MRG1-002` SUCCEEDED | `WORK-SW008-M2-MRG1-002` CLOSED |
| 卡 101（`M2-GOV-Q01`） | `853fc651` | `bf19b6bd` | CHG-SCPT-2026-404 | completed | `RUN-SW008-M2-Q01-001` SUCCEEDED | `WORK-SW008-M2-Q01-001` CLOSED |
| 卡 102（`M2-GOV-ERRA`） | `9f952044` | `853fc651` | CHG-DOCU-2026-037 | completed | `RUN-SW008-M2-ERRA-001` SUCCEEDED | `WORK-SW008-M2-ERRA-001` CLOSED |
| 卡 103（`M2-GOV-TD11`） | `dbf7d031` | `9f952044` | CHG-DOCU-2026-038 | completed | `RUN-SW008-M2-TD11-001` SUCCEEDED | `WORK-SW008-M2-TD11-001` CLOSED |

线性历史：已推送线尖端 `0d22fdd0` → 卡 099 → 卡 100（合并 `657f3dc5`，即卡 093 与卡 095）→ 卡 101 → 卡 102 → 卡 103。**本地线未推送、未合并 main。**

**4. Q 队列进展（§4.3.1）**

| 任务 | 状态 | 证据 |
|---|---|---|
| 任务 Q01 | 已解（卡 101，`853fc651`） | 两个真实样例 CSV 此前被项目 `.gitignore` 的 `*.csv*` 挡在 Git 之外；嵌套 `.gitignore`（`!*.csv`）与 `.gitattributes`（`*.csv -text -diff`）加两个与 `00_Infrastructure/auto_pm/tests/vartable/samples/` 已入库副本逐字节相同的样例入库。干净检出该提交后 `tests/vartable` 为 120 passed / 12 skipped；rest 组由 15 failed / 840 passed 变为 1 failed / 854 passed / 13 skipped（余下 1 个是 TD-SW008-042） |
| 任务 Q02 | 取证完成，等待用户确认关闭 | 真实 Qt 离线路径：Python 3.12.14、PySide6 6.11.1、Qt 6.11.1，平台插件 `offscreen`，`QPrinter` 输出格式 `PdfFormat` 且无需系统打印机；`tests/qml/test_delivery_bridge_pdf.py`（子进程里真实导出 PDF，断言无 `0x80040155`）连续 3 次 1 passed。CHG-SCPT-2026-195 §10.1 第 2 项的错误记载已由勘误 `ERR-SCPT-2026-195-01` 更正（卡 102） |
| 任务 Q03 | **仍开放** | 2026-10-11 实测：`python -m mypy .`（项目根）仍因 `Duplicate module named "tests"`（`tests/__init__.py` 与 `templates/python-tool/template/tests/__init__.py`）以“Found 1 error in 1 file (errors prevented further checking)”中止；`python -m mypy auto_pm` 为 244 个源文件 no issues；`python -m mypy auto_pm tests` 为 89 errors in 27 files（均为测试文件缺类型注解，无重复模块中止）。要关闭 Q03，需要改 `pyproject.toml` 或 `templates/.../tests/__init__.py`（产品档），另立卡 |

**5. 波次 4 瘦身落字（用户 2026-10-10 同意方向；本修订落字，经用户批准卡 104 的 SHA 后生效）**：§4.9 的 D01～D09 各行原文不变，实施时按下述方式合并卡片，**门槛不降**：
1. **D04 与 D05 合并为一张实施卡**：同一条受治理运行里先构建不可变候选（D04 的验收列），再对同一候选跑全量门禁（D05 的验收列）；两列的通过标准、失败出口与“尚未 active”的限制全部保留，缺任何一项不得发布；
2. **D06 瘦身为一次演练并与 D07 合并为一张实施卡**：演练内容为“切到候选、退回 previous、核对数据完好、不兼容写入被拒绝、新事件保留”这一次完整往返；D07 的真实加载同一制品与失败恢复条款全部保留；**切换 active 指针的时机由用户另行授权（D07 的部署范围批准条件不变）**；
3. 其余 D 行（D01～D03、D08、D09）不变。云端相关内容不属于本计划。

**6. 本批不做什么 / 未决事项**：不推送、不合并 main、不转私有、不部署、不切换 release；SW-2026-009 的 15 个与 PLC 项目的 2 个变更单未入库（用户 2026-10-10 选方案 A，另议）；台账中“要用户决定”的事项（008、011、043、044、062、063、066、067、068、069、071、084 等）待用户逐项表态；Q02、Q03 的关闭、TD-SW008-001/061 状态翻转（卡 105）。

**本节不授权**：合并 main、任何推送、转私有、部署、release 切换、任何债务或历史失败记录的处置。

#### 4.7.14 M3 第二批（卡 105～110）、推送与 CI 结果（V3.0.29，2026-10-11）

本节由 `M3-WBS13`（卡 110）追加，只加不删。所有 SHA 与状态在 2026-10-11 只读采集（提交读自 git，变更单状态读自变更单文件）。授权依据：用户 2026-10-11 先说“先做CI基线小卡，做完再推送”，再说“可以，按这个排期，预授权给你，授权有效时间截止到下午5:00pm.”（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt`）；所有变更单收口均为委托执行，委托条件是 G1～G9 全 PASS 且提交字节等于冻结清单，均已满足。

**1. 推送与 CI**：用户授权的单分支快进推送已执行：`origin/codex/m2-gov-wbs9-attest` 由 `0d22fdd0` 快进到 `620e7597`（10 个提交，不带 tag，不进 main）；推送前只读核对为快进、0 个密钥形态命中、无超过 5 MB 的文件。该提交触发的 CI（`sw008-ci`，第 4 次运行，run id 38162827537）结论 `success`，即刷新后的基线被接受。远端线之后没有新的推送。

**2. 卡与提交**

| 卡 | 提交 | 父提交 | 变更单 | 状态 | Run | Work |
|---|---|---|---|---|---|---|
| 卡 105（`M2-GOV-TD12`） | `741ed045` | `9655382d` | CHG-DOCU-2026-039 | completed | `RUN-SW008-M2-TD12-001` SUCCEEDED | `WORK-SW008-M2-TD12-001` CLOSED |
| 卡 106（`M2-GOV-CIBASE`） | `620e7597` | `741ed045` | CHG-SCPT-2026-405 | completed | `RUN-SW008-M2-CIBASE-001` SUCCEEDED | `WORK-SW008-M2-CIBASE-001` CLOSED |
| 卡 107（`M3-A1`） | `eca0fab8` | `620e7597` | CHG-SCPT-2026-406 | completed | `RUN-SW008-M3-A1-001` SUCCEEDED | `WORK-SW008-M3-A1-001` CLOSED |
| 卡 108（`M3-DOCS`） | `a6d5d8f3` | `eca0fab8` | CHG-DOCU-2026-040 | completed | `RUN-SW008-M3-DOCS-001` SUCCEEDED | `WORK-SW008-M3-DOCS-001` CLOSED |
| 卡 109（`M3-TD13`） | `31bed234` | `a6d5d8f3` | CHG-DOCU-2026-041 | completed | `RUN-SW008-M3-TD13-001` SUCCEEDED | `WORK-SW008-M3-TD13-001` CLOSED |

线性历史（本地）：`620e7597`（已推送）→ 卡 107 `eca0fab8` → 卡 108 `a6d5d8f3` → 卡 109 `31bed234`；卡 110（本记录）在其上。卡 107 之后的各卡**未推送、未合并 main**。

**3. Q 队列（§4.3.1）**

| 任务 | 状态 | 证据 |
|---|---|---|
| 任务 Q01 | 已解（卡 101，`853fc651`；CI 基线随卡 106 刷新） | 见 §4.7.13 |
| 任务 Q02 | **已关闭**（依据用户当日预授权中的“Q02 关闭”） | 真实 Qt 离线路径取证见 §4.7.13（PySide6 6.11.1，平台 `offscreen`，`QPrinter` 的 `PdfFormat`；`test_delivery_bridge_pdf.py` 连续 3 次 1 passed）；CHG-195 的错误记载已由勘误 `ERR-SCPT-2026-195-01` 更正 |
| 任务 Q03 | **中止缺陷已修复，`mypy .` 全绿不在本任务验收内** | 卡 107：`pyproject.toml` 的 `[tool.mypy] exclude` 改为排除模板 tests 包，`python -m mypy .` 不再因 `Duplicate module named "tests"` 中止，跑完全部源文件并以“Found 273 errors in 89 files (checked 511 source files)”结束。验收条件“目录发现唯一、后续全量静态检查不再因 duplicate module 提前中止”满足；“不通过忽略目录掩盖真实新代码”：被排除的目录只含一个只有注释的 `__init__.py` 与两个 `.jinja` 模板，没有可检查的 Python 代码。残留的既存错误（`scripts/` 101、`tests/` 109、`auto_pm/` 63，其中多数是 `logging` 目录遮蔽标准库造成的假错误）登记为 TD-SW008-122；`mypy auto_pm` 仍为 244 个源文件零问题 |

**4. D01 与 M2-GOV-DOCS**
- **D01 已完成（卡 107）**：`AGENTS.md` 去掉被转义吃坏的字符（DEV-ENC-001 行的回车符与丢失的反引号；自闭环约束行里的反斜杠与响铃符，命令名改为 `send_message`、`main.py doc check`、`main.py plc check <PID>`），“阶段 3”一行改为 PM_SESSION 已退役；`AGENTS.md` 与两个薄适配入口各加“当前计划与状态投影”指向 WBS 的一行；操作手册 36 去掉固化的旧版本号并新增 §9“受治理实施卡的标准动作”。`.trae` 两执行技能未纳入（需用户明确授权）。
- **M2-GOV-DOCS 已完成（卡 108）**：采纳 8 份草稿，**相对草稿的四处有意偏离**：不写入已过时的 2026-10-08 候选身份（改指向本 WBS 的当前投影）；PM_SESSION 一律写“已退役”而非“可刷新摘要”；不采纳 PM_SESSION 自己的那份（文件已退役）；发布门禁规范保留示例记录块。

**5. 本批发现的新债务与局限（已登记于台账，卡 109）**
- TD-SW008-122：`mypy .` 的残留噪声与 `logging` 目录遮蔽（上表 Q03）。
- TD-SW008-123：控制根检出分支的 release 指针文件（`active_release.json`、`previous_release.json`、`deployment_manifest.json`）已修改未提交，HEAD 与磁盘记录的版本不同；D03“固定提交可检出”的前置，**需用户裁决入库口径**。
- TD-SW008-124：卡的档次没有门禁强制运行分档器——卡 099 与卡 102 的路径按分档器属产品档，当时按文档档做门禁；卡 107 的九组回归（rest 组 855 passed, 13 skipped，core 组 1142 passed, 1 skipped）在含这两张卡的树上完整重跑，等于补做，没有发现回归。
- 卡 107 的 G2 没有使用任何容忍规则（strict）。

**6. 未决事项（不变）**：台账里“要用户决定”的事项（008、011、043、044、062、063、066、067、068、069、071、084 等）；M2-F01B 的范围；H04～H06、H08、H09；SW-2026-009 的 15 个与 PLC 项目的 2 个变更单；D03 合并 main 与 D07 切换（独立授权）；`mypy .` 是否要变绿及范围（TD-SW008-122）。核心档下一批：TD-SW008-120/077（边车竞态）→ M2-B1，建议引入独立审计。

**本节不授权**：合并 main、除上述单分支快进外的任何推送、转私有、部署、release 切换、任何债务或历史失败记录的处置。

#### 4.7.15 CI 基线再刷新、第三批新增任务行与仓库治理排队项（V3.0.30，2026-10-11）

本节由 `M3-WBS14`（卡 112）追加，只加不删。所有 SHA 与状态在 2026-10-11 只读采集。授权依据：用户 2026-10-11 说“推送卡111”与“批准补三个任务行，出卡”（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt`）；变更单收口为委托执行（G1～G9 全 PASS 且提交字节等于冻结清单）。

**1. 推送与 CI 的实际过程（更正 §4.7.14 之后的事实）**

| CI 运行 | run id | 提交 | 结论 | 说明 |
|---|---|---|---|---|
| 第 4 次 | 38162827537 | `620e7597` | success | 卡 106 刷新基线后 |
| 第 5 次 | 38176986566 | `e61c4fa9` | **failure** | 只在“Compare the failures with the known Linux baseline”一步失败，Pytest 步骤本身通过；原因按代码与卡 107 结果推断为：卡 107 修好 TD-SW008-042，该测试在 Linux 上也通过，基线仍登记它，比较脚本把“基线条目意外通过”判为 FAIL（基线过期）。GitHub 作业日志需登录才能下载，原始输出未读到，**该原因是推断，由第 6 次变绿证实** |
| 第 6 次 | 38180864747 | `07709559` | success | 卡 111（CHG-SCPT-2026-407）把该 id 与类别从基线去掉（21 → 20）后 |

**教训**：修复基线里登记的测试时，必须在同一张卡里同步刷新 `tests/tools/sw008_ci/baseline.linux.json`；本次是卡 107 漏掉了这一步，由卡 111 补救。已推送线尖端现为 `07709559`，本地没有未推送的提交。

**2. 用户批准新增的三个任务行（2026-10-11）**：`M3-RACE`（TD-SW008-120、077 的边车竞态，核心档，先于其他核心卡，建议独立审计）、`M3-CF`（编译报错结构化反馈，业务缺口 ②，需要用户提供真实报错文本样本）、`M3-FIG`（图与文档一致性检查，业务缺口 ③）。三者的范围与路径都由各自实施卡前的只读勘测确定，本节不预设；批准的只是任务行，不是实施。

**3. 排队的仓库治理项（来源：2026-10-11 外部审计简报；状态 PLANNED / QUEUED / NOT_AUTHORIZED，排队不是授权）**：`M3-INV`（只读盘点）、`M3-REPOGOV`（治理批次）、`M3-MAIN`（main 集成策略决策）。依据与位置：
- 现有安排只覆盖局部：`M2-GOV-DOCS`（指定的 8 份关键文档，已完成）、`D01`（指定的指引与规则，已完成）、`D03`（“所有必需文件都可从固定提交检出”）；**没有**覆盖全仓文档的权威性清单、目录与文件归属、链接与工具路径依赖的系统性验证与防回归规则，因此新增这三项。
- 位置建议（待用户裁决）：`M3-INV` 是只读的，可在 M3 功能任务（`M3-RACE` 等）期间任何时间做；`M3-REPOGOV` 放在 M3 功能任务之后、`D03` 冻结之前；`M3-MAIN` 在 `D03` 之前做出决策。**本修订不改 D 阶段各行原文与已批准的里程碑顺序**，对 `D03` 追加的前置条件只在本节陈述，需用户确认后才写入 `D03` 行。
- 现状事实（只读，2026-10-11）：`origin/main` = `e83c117d`，是已推送线的祖先；已推送线领先 107 个提交、涉及 472 个路径（其中约 414 个在 SW-2026-008 项目目录、35 个在 SYS-2026-001），这是路径变更总量，不代表同等数量的产品源码文件；现 CI 工作流对 main 的 push 不触发（`branches-ignore: [main]`），仍可手动触发。

**4. 外部审计简报的事实核对（更正过时项）**
- 活跃分支尖端：简报写 `0d22fdd0`（92 个提交、441 个路径），现为 `07709559`（107 个提交、472 个路径）；WBS 现为 V3.0.30，M2 已由用户 2026-10-11 宣布验收，M3 进行中。
- Linux CI：简报写“基线 35 个失败、测量源 3.13 与 CI 3.12 不同”；现基线为 20 个 id，CI 首次运行（Python 3.12）结论为 PASS_KNOWN_BASELINE，第 6 次运行 success，该项已解决；但“PASS_KNOWN_BASELINE 不是全绿”的限制不变。
- TD-SW008-104～107 仍为“待执行”（只读核对台账，2026-10-11），简报的描述属实。
- 5 条历史未终结 Work：`WORK-SW008-M2-F02-001`、`P1-AUDITFIX-001`、`V05B2-001`、`V05B3-001` 为 BLOCKED，`WORK-SW008-M2-TD3-001` 为 READY（只读读自治理库）；按用户要求保留，默认恢复可能报 `MULTIPLE_ACTIVE_WORKS`，不得由合并或文件整理顺手改终态。
- 新增的相关债务：TD-SW008-122（`mypy .` 残留）、123（release 指针文件入库口径，D03 前置）、124（卡档次没有门禁强制）。

**5. 暂不处理 / 保留**：历史治理证据与审计记录、5 条历史 Work 的终态、`.trae/` 下的技能、Obsidian 正式规范、用户保留的备份与归档；均不在本节任何任务的默认范围内。

**本节不授权**：实施 `M3-RACE`、`M3-CF`、`M3-FIG`、`M3-INV`、`M3-REPOGOV`、`M3-MAIN` 中的任何一项；移动、删除、覆盖任何文件；合并 main、推送、转私有、部署、release 切换。

#### 4.7.16 仓库卫生清理（存量）与 `M3-ROOT`、`M3-HYG`（V3.0.31，2026-10-12）

本节由 `M3-WBS15`（卡 114）追加，只加不删。所有数字取自 2026-10-11/12 的只读核对与清理执行日志（`.auto-pm/reports/m3-hyg/exec_log.jsonl`）。授权依据：用户 2026-10-11 “接受你的建议”（两次）与 2026-10-12 “批准，截止17:00，推送一并授权，A4先出方案”；变更单收口为委托执行（G1～G9 全 PASS 且提交字节等于冻结清单）。

**1. 为什么要做**：2026-10-11 的核对显示控制根工作区有 4166 条状态（其中 3486 个未跟踪的 release 载荷、273 个 Decision JSON、219 个与已推送线字节相同的“分支不一致”文件），本地有 206 个分支与 228 个工作树（约 66 GB）。WBS 里原本没有任何任务负责分支与工作树，只有 H08 一条（单个 A2 工作树）；每张受治理卡都会新增 1 个分支与 1 个工作树，不处理只会更多。

**2. 已执行的存量清理（步骤 1～4）**

| 步骤 | 做法 | 结果 |
|---|---|---|
| 1 归档（只新增） | 对有线上没有的独有提交的 42 个分支与 12 个游离提交写 `refs/archive/*`，打 bundle `unique-work-20261011.bundle`（以已推送线为前置，0.5 MB，校验通过）；补丁等价的 5 个分支另写归档引用并打 bundle | 59 个归档引用；备份目录 `C:\Users\fubai\Documents\My_Workspace_backups\hyg-20261011` 含 bundle、分支名→SHA 清单与核对数据 |
| 2 移除干净的工作树 | 逐个复核（状态干净、HEAD 在线上、无存活 Run、无非缓存类被忽略文件）后 `git worktree remove`，不加 `--force`；`.plc-out/`、`coverage/` 这类可再生输出列入白名单 | 移除 116 个 |
| 3 有改动的工作树 | 先保存补丁、未跟踪文件与状态到备份目录并校验，再 `--force` 移除；保存失败或未跟踪过大即跳过 | 移除 31 个；跳过 1 个（Temp 下的 `codex-pmf-g08-…`，HEAD 不在线上，8134 个跟踪文件全部不存在的空壳）；2 个因残留目录壳留下 |
| 4 删分支名 | 对祖先或（补丁等价且已归档）的分支，复核后 `git branch -D`；仍被工作树检出的不删 | 删除 152 个；10 个因仍被检出而保留 |

结果：登记的工作树 228 → 64，本地分支 206 → 55，磁盘空闲约 +42 GB；`ledger reconcile` 两项目 0/0/0；`pm resume SW-2026-008` 的冲突与候选集合前后逐项相同；已推送线 `07709559` 未动。

**3. 清理中的发现**：（a）17 个残留目录壳的 `.pytest_cache` 带外来安全上下文的访问权限，本用户读不到也删不掉，git 已取消其登记，需要管理员权限清除（我不修改文件权限）；（b）有 17 个工作树曾登记在系统 Temp 目录下，Windows 清理可能把它们变成空壳；（c）4 个工作树绑着存活的 Run（`RUN-SW008-A2-201-01/03`、`RUN-SW008-PMF-E01-001`、`RUN-SW008-PMF-G10-001`、`RUN-SYS001-PMF-WBS25-001`），不动，等用户对这些 Run 的处置裁决。已登记为 TD-SW008-126、127（卡 113，`3ac045f1`）。

**4. 新增任务行**：`M3-ROOT`（控制根对齐集成线；方案 `.auto-pm/reports/M3_ROOT_ALIGN_PLAN_20261012.md`，只读冲突清单：215 个未跟踪副本字节相同可无损移除、4 个内容不同的 Decision 与 70 个只在旧分支跟踪的文件先存后放回、8 个冲突文件按“release 指针与 SW-2026-009 变更单保留本地、WBS 与台账取目标”处理；切换后 `pm resume` 前后逐项相同才算通过，否则回退；**待用户确认才执行**）与 `M3-HYG`（存量已完成，剩余的归档分支与工作树的处置、残留目录壳、卡工厂收口后自动回收仍待做）。位置：`M3-ROOT` 在 `M3-RACE` 之前、重门禁运行之外执行；`M3-HYG` 的剩余部分与 `M3-REPOGOV` 的文件级治理分开，不阻塞 D 阶段。

**5. 用户 2026-10-11/12 的裁决（记录）**：（a）控制根对齐放在 `M3-RACE` 之前；（b）SW-2026-009 归它自己治理，D08 之前由它自己整理干净（D08 会把它当 Python 靶子，DJ-2026-005 当 PLC 靶子）；（c）仓库治理项 `M3-INV`、`M3-REPOGOV`、`M3-MAIN` 仍是排队（PLANNED / QUEUED / NOT_AUTHORIZED），不是授权。

**本节不授权**：执行 `M3-ROOT`；处置 42 个归档分支与 50 个工作树；删除任何提交、治理证据或用户保留对象；修改文件权限；合并 main、转私有、部署、release 切换。

#### 4.7.17 核心档卡 115、116、控制根对齐与卫生清理收尾（V3.0.32，2026-10-12）

本节由 `M3-WBS16`（卡 118）追加，只加不删。所有 SHA 与状态在 2026-10-12 只读采集。授权依据：用户 2026-10-12 “批准，截止17:00，推送一并授权，A4先出方案”“A4确认，先切控制根”“放开夜间窗口，已批准的卡可以跑到收口。但是17:30我下班，那个时间点必须有序停止，我只能放开19:00之后”“继续”；变更单收口为委托执行（G1～G9 全 PASS 且提交字节等于冻结清单）。

**1. 提交与变更单**

| 卡 | 提交 | 父提交 | 变更单 | 状态 | 说明 |
|---|---|---|---|---|---|
| 114（`M3-WBS15`） | `ba0ef3e9` | `5cd57f8b` | CHG-DOCU-2026-039（SYS-2026-001） | completed | 已推送，CI 第 7 次运行（run id 38255861741）success |
| 115（`M3-RACE`） | `ef3c13af` | `ba0ef3e9` | CHG-SCPT-2026-408 | completed | 本地，未推送 |
| 116（`M3-B1` = `M2-B1`） | `c54accd4` | `ef3c13af` | CHG-SCPT-2026-409 | completed | 本地，未推送 |
| 117（`M3-TD15`） | `37a4a6a5` | `c54accd4` | CHG-DOCU-2026-043 | completed | 本地，未推送 |

**2. `M3-RACE`（TD-SW008-120、077）**：根因读自代码——严格只读读取前的 `_file_inventory` 在边车文件（`-wal`、`-shm`、`-journal`）于某个瞬间不是单链接普通文件时直接硬报错；同一检查在 `_validated_db_path` 早有有界重试，清点这一处是漏掉的第二处。修法：边车异常改为可重试的漂移信号，持续异常仍以原消息拒绝，数据库文件本身仍不重试；新增 5 个确定性测试（其中 3 个在旧代码上失败，1 个只记录既有的重试行为）。核心档九组回归严格全绿、**未使用具名容忍规则**（rest 组 855 passed, 13 skipped、infrastructure 组 79 passed、core 组 1142 passed, 1 skipped），r09 在候选里隔离重复 20 次全部通过。**局限**：竞态是概率性的，确定性测试证明了修复点，真实进程重复运行只能说明“没再见到”，所以 TD-SW008-120 状态改为待复核而不是已偿还，TD-SW008-077 的其余边车异常种类与压力测量仍未做。

**3. `M2-B1`（卡 116）**：把 `ContinuityStore` 的三个纯函数（Run 创建请求哈希、结算请求哈希、租约令牌指纹）原样搬进新增的 `continuity_internal/codec.py`，Store 保留一行委托；新增 16 个测试，期望摘要取自基线原代码一次性算出的字面量；九组严格全绿（infrastructure 组 95 passed）。**不宣称存储已解耦，TD-SW008-055 不关闭**，后续批次（只读组件、单类事务命令、门面拆分）仍待排。

**4. `M3-ROOT`（控制根对齐，已执行）**：控制根现为 `codex/control-root-20261012`（`ba0ef3e9`），12 项验证门全部通过（`AGENTS.md` 与目标逐字节相同、WBS 为 V3.0.31、3 个 release 指针与 `continuity.db` 的 sha256 切换前后相同、版本不变、两项目对账 0/0/0、`pm resume` 逐项相同）。**执行中的三个问题**（各出现一次、各解决一次，验证门与自动回退起了作用）：（a）一把 2026-10-09 的 0 字节陈旧 `.git/index.lock` 已移除并记录；（b）方案里“台账取目标版本”的判断是错的——控制根里的 `01_版本变更台账.md` 是 `change create` 写入的活台账，含卡 099 之后新建的 12 个变更单的记录，最终保留本地版本；（c）回退留下的同名分支，脚本已处理。**由此留下**：控制根里有约 105 个变更单文件不在 git 里（含 SW-2026-009 与 PLC 项目的，二者按用户裁决自治理），SW-2026-008 与 SYS-2026-001 的部分排入同步入库卡（产品档，九组回归）。

**5. `M3-HYG`（收尾）**：2026-10-12 的 A5 把 50 个有独有提交的工作树存补丁后移除、41 个归档分支名删除（归档引用与 bundle 兜底）；登记的工作树 228 → 19、分支 206 → 19。**更正**：V3.0.31（§4.7.16 与 `M3-HYG` 行）所写的“工作树 63、分支 54、42 个分支与 50 个工作树待用户处置”是 A5 之前的数字，已处置。剩余项见 `M3-HYG` 行。

**6. 运行规则（用户 2026-10-12 授权，记录）**：白天有序停止于 17:30；17:30～19:00 不动；19:00 之后的夜间窗口只跑已批准的卡（17:30 前已在聊天报出最终 SHA 的卡），跑到收口、不推送、任一门禁失败即停下保留现场；同一问题两次未解即通知用户由其切换 Opus 诊断。

**本节不授权**：合并 main、除上述一次快进推送外的任何推送、转私有、部署、release 切换、任何债务或历史失败记录的处置、修改文件权限。

#### 4.7.18 2026-10-12 夜：卡 119～122 与 V08 勘测（V3.0.33）

本节由 `M3-WBS17`（卡 122）追加，只加不删。所有 SHA 与状态在 2026-10-12 夜只读采集。授权依据：用户 2026-10-12 说“放开夜间窗口，已批准的卡可以跑到收口”“现在就跑”（卡 119 在 18:39 提前于 19:00 启动），并在睡前说“允许第1项，第2项，第3项。电脑不睡眠，明早上5点汇报你的成果”——第 1 项是夜里接着做台账与 WBS 文档卡，第 2 项是 V08 卡夜里也跑，第 3 项是夜里推送并读 CI；变更单收口为委托执行（G1～G9 全 PASS 且提交字节等于冻结清单）。

**1. 提交与变更单**

| 卡 | 提交 | 父提交 | 变更单 | 状态 | 说明 |
|---|---|---|---|---|---|
| 120（`M3-V07`） | `7e926f4f` | `098e2bf6` | CHG-SCPT-2026-410 | completed | 测试档；rest 组 869 passed, 13 skipped |
| 119（`M3-CS2`） | `4f855e04` | `7e926f4f` | CHG-DOCU-2026-044 | completed | 产品档；九组与基线逐项相同（rest 组 869 passed, 13 skipped、core 组 1142 passed, 1 skipped） |
| 121（`M3-TD16`） | `c1b08fc1` | `4f855e04` | CHG-DOCU-2026-045 | completed | 文档档；登记 TD-SW008-129、130、131 |

**2. `M3-CS2`**：21 个新变更单（SW-2026-008 16 个、SYS-2026-001 5 个）与两个活台账入库。磁盘上的这些文件是 CRLF，仓库的 `.gitattributes`（`* text=auto eol=lf`）规定入库为 LF，冻结字节取 LF 规范化后的字节，使“提交的 blob 等于 Checkpoint 哈希”的核对不因换行而偏。分档器把变更单目录判为产品档（变更单是治理工具运行时读写的数据），所以卡 119 跑了完整九组回归，并先用一个不含 core 与 qml 组的预检跑（非治理）确认新字节不改变任何已测组的结果。SW-2026-009 与 PLC 项目的变更单不在范围（用户裁决：SW-2026-009 自治理）。

**3. `V07`（部分完成）**：`tests/e2e/test_pmf_template_python.py` 14 个测试，用真模板生成工程并复测，见 V07 行；该文件的一个设计教训：文件集断言写在共享工程上会被子进程留下的工具缓存目录污染（项目的测试插件会打乱顺序），已改为每个断言各自新生成。**本节不宣称 WBS 的 V07 行整行完成**：“从基准提取模板”未做，行内写的 `python_cockpit` 路径不存在。

**4. V08 勘测（卡待出）**：对真模板 `templates/plc-standard-project` 生成的项目做了变异勘测（脚本 `.auto-pm/reports/m3-v08/explore3.py`）。会失败的场景：两处 `.plc.json` 非法、缺 name、缺 version、缺失，缺 `PM_SESSION_<项目号>.md`，缺台账，缺 `PRD/接口文档_INT.md`，缺标准目录。**不报告的破损**：PLC_ST 下的 `接口文档_INT.md` 被删、`OB1.scl` 被改成无法解析的内容；`PLC变量定义文档_VAR.md` 被删只增加文档一致性警告。已登记 TD-SW008-129（需用户裁决要不要让这些失败）、TD-SW008-130（检查项仍用旧字形“版本变更台帐”）、TD-SW008-131（模板里有成对的静态文件与 `.jinja` 影子重复）。V08 卡只钉“实际会拒绝”的场景，不改产品。

**5. 运行规则（用户 2026-10-12 授权，记录）**：夜间窗口只跑已批准的卡（先在聊天报 SHA）；任一失败停下保留现场、不重跑；同一问题两次未解通知用户；连续 2 张卡失败整体停下；本节之外的夜间授权为：台账与 WBS 文档卡、V08 卡与一次快进推送。

**本节不授权**：合并 main、转私有、部署、release 切换、任何债务或历史失败记录的处置（TD-SW008-129 需用户裁决）、修改文件权限。

#### 4.7.19 2026-10-13：PLC 门禁实际依赖插件、卡 123～126 与用户的裁决（V3.0.34）

本节由 `M3-WBS18`（卡 126）追加，只加不删。所有 SHA 与状态在 2026-10-13 只读采集。授权依据：用户 2026-10-13 说“同意按这个方案做，先出修模板那张卡”“批准，开跑”“登记为债务，等WBS全部完工后，用于测试驾驶舱功能”“1同意，V07保留待办，卡127收口后允许推送”；变更单收口为委托执行（G1～G9 全 PASS 且提交字节等于冻结清单）。

**1. 提交与变更单**

| 卡 | 提交 | 父提交 | 变更单 | 状态 | 说明 |
|---|---|---|---|---|---|
| 123（`M3-V08`） | `dcfca387` | `c8a4f689` | CHG-SCPT-2026-411 | completed | 测试档；rest 组 888 passed, 13 skipped；夜间运行，已推送，CI 第 9 次 success |
| 124（`M3-TPL1`） | `b5d3e552` | `dcfca387` | CHG-SCPT-2026-412 | completed | 产品档九组严格全绿；本地，未推送 |
| 125（`M3-TD17`） | `d6d382ff` | `b5d3e552` | CHG-DOCU-2026-046 | completed | 文档档；登记 TD-SW008-132、133；本地，未推送 |

**2. 发现：用户的真实 PLC 门禁是 VS Code 插件 Dynamic Siemens Language Support**。插件安装目录自带命令行 `siemens-lsp`（`check` 诊断、`test` 跑 `.scltest`，有错退出码为 1）。用它检查驾驶舱模板生成的标准项目（配上真实的 `01_SharedLibraries`），修前 `check` 报 17 个错误、退出码 1，`test` 退出码 1，而驾驶舱 `plc check` 全绿。**含义**：驾驶舱 PLC 门禁比用户实际依赖的门禁弱，AGENTS.md 里“Linter 语法白名单”的说法没有被实现。插件对空文件与乱码单文件同样报 0 诊断，所以驾驶舱的结构检查与插件互补。使用边界（用户裁决）：非商业使用、尊重著作权——插件二进制只在本机调用，不放进仓库、CI 或发布包；证据里只记录版本与哈希。

**3. `M3-TPL1`（卡 124）**：模板里三类缺陷——`FB_1001_Station1` 在功能块体内用无效的 `CONST…END_CONST` 块（7 个语法错误）；两个集成测试引用 `ST_CommonAlarm` 里不存在的成员（10 个错误）；以及修测试时暴露的真实功能缺陷：`FB_2001` 的复位分支在输出写回结构体之前就 `RETURN`，复位周期输出保持旧值。修后 `check`、`test` 退出码均为 0，3 个插件负向对照各被拒绝。

**4. DJ-2026-005 的裁决**：对活体基准项目原位置只读运行插件，`check` 8 个错误（`FB_2001` 把结构体里声明为 `INT` 的 `o_iMESAlarmQueue`、`o_iStationAlarmStatus` 当数组用共 6 处；`basic_test.scltest` 引用不存在的 `i_bGlueMachine_Fault` 共 2 处）、`test` 退出码 1。用户裁决：**登记为债务（TD-SW008-132），有意保留不修，等 WBS 全部完工后用于测试驾驶舱功能**（可作为 D08 的 PLC 项）。本节不授权修改 DJ-2026-005 的任何文件。

**5. 用户 2026-10-13 的其他裁决**：“变量文档缺失”在 `plc check` 保持警告、到交付阶段升为失败（同意）；V07 的“从基准提取模板”保留待办；卡 127 收口后允许推送。

**6. 今日计划（2026-10-13）**：卡 126（本记录）→ 卡 127（`M3-PLUGIN`，产品档，九组回归约 2 小时 40 分）→ 推送卡 124～127 并读 CI → 小修卡（TD-SW008-130、131 与 AGENTS 措辞，产品档；今晚或明天）。

**7. WBS 仍未完成的任务**：`M3-PLUGIN`（今天）；V04-R1；M2-F01B（范围待用户批准）；`M3-CF`（等用户给真实报错样本）；`M3-FIG`；V07 的“从基准提取”（保留待办）；D02～D09；排队未授权的 `M3-INV`、`M3-REPOGOV`、`M3-MAIN` 与 `M3-HYG` 的剩余部分；用户名下的历史队列 H04、H05、H06、H08、H09、H10。

**本节不授权**：修改 DJ-2026-005、合并 main、转私有、部署、release 切换、任何债务或历史失败记录的处置、修改文件权限、把插件二进制放进仓库或 CI。

### 4.8 V：双领域、恢复和模板（V01～V08）

当前进度：V01～V08 尚未作为整体开工，M2 未启动或验收。仅 V04-R0 因 C09 的旧租约阻断提前开展：原 Run 保留 CANCELLED，新同 Work 验证 Run SUCCEEDED、有当前字节 Checkpoint、lease RELEASED，原 Work ACCEPTED、CHG-309 completed；FIX/FENCE 子 Work 各自 ACCEPTED，FENCE CHG completed（非 closed），两次早期 Recovery 仍 FAILED。V04-R0 基础合同已闭合，不等于 V04/V04-R1 的真实进程回收演练完成，也不表示 V 批次整体启动。V01 仅可在 C01/C03 的独立授权及真实 PLC 门禁证据下启动。

**V3.0.21 补记。** V01 已于 2026-10-03 验收闭环（提交 `37a4faff`、卡 042、CHG-SCPT-2026-374），上一段“V01～V08 尚未作为整体开工”与“V01 仅可在……启动”是 V3.0.20 及更早时点的表述，予以保留。用户同日确认新增 V01B～V01D（PLC 文档与代码一致性核对、基准治愈、提交拦截），V02 依赖随之改为 V01、V01B、V01C、V01D、C09；证据与需求见 §4.7.6。

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| V01 | PLC 静态质量门插件 | C01、C03 | CORE/evidence_collection_service.py、T/core/test_evidence_collection_service.py | 复用现行 PLC checker；违规 SCL 确实失败；.plc.json/SCL/INT/VAR 证据同基线 | T/G |
| V01B | PLC 文档与代码一致性核对与自动补全 | V01；需求说明 043 已确认 | 拟：PLC 域新增核对与补全模块并并入 `PlcChecker`；`plc` 命令组的核对、补全与确认命令；PLC 变量定义文档与 FB 接口文档模板的修订；对应测试（确切路径以勘测后的实施卡为准） | 核对信号名、数据类型、方向、注释（不核对通信协议）；整份文档缺失警告并给出草稿；不一致拦住并精确指出对象、变量、差异与位置；代码到文档的补全只补缺行、不覆盖人写文字、补入行带【待确认】、一条命令确认；新检查项使 `plc check`、驾驶舱 PLC 检查统计与 V01 的 AI 验收门同时生效；钉死基准隔离副本冒烟 | T/G |
| V01C | 基准治愈与升基准 | V01B | DJ-2026-005 的接口文档与变量定义文档（项目内容，非产品源码）；基准钉值（提交与目录树 SHA） | 用 V01B 的工具生成草稿，用户审核确认后写入；现行检查器对该项目全绿；重新钉基准并更新冒烟钉值；独立 CHG，活目录只在用户确认后改动 | A/G |
| V01D | 提交拦截钩子与阶段门接入 | V01B、V01C | 提交钩子（碰 Hook 基础设施）；`StageGateEngine` 的“监控→收尾”门；对应测试（确切路径以勘测后的实施卡为准） | PLC 文档与代码对不上或仍带【待确认】即拦提交并自动补全；阶段门与交付拦未确认；`--no-verify` 无法阻止，由其他关口兜底；单独验收 | T/G |
| M2-F01A | F01-a：删除 PLC 工程标记后提交钩子与阶段门失败关闭 | TD-SW008-078；V01D ACCEPTED | 拟：`plc_git_marker_guard.py`（新增）、`plc_doc_hook.py`、`stage_gate_engine.py` 三个产品文件（必要时第 4 个 `git_hook_enforcer.py`）及对应测试；不新增存储、不改 `checker.py` | 以 Git HEAD 为身份来源：HEAD 有 `.plc.json` 而暂存区或工作区没有即拒绝，不放行任何改名或移动（错误信息指向 F01-b）；纯删除、坏 IFC 后删标记、首次创建、无 PLC 身份的工程、HEAD 读取故障均有真实 Git 反例；已进入 HEAD 的删除认不出（`--no-verify`、其他克隆），如实保留；产品档，全量九组回归；V05、V08 与部署之前必须验收 | T/G |
| M2-F01B | F01-b：合法的 PLC 工程移动与退役入口 | M2-F01A ACCEPTED；TD-SW008-079 | 独立新能力卡，范围在勘测后确定 | 经用户明确批准的移动与退役入口，含授权记录、真实 Git 反例与失败关闭；不阻塞 F01-a；M2 末或 M3；持久登记另行设计；V3.0.24：后移到 M3，承诺保留，范围待用户批准 | T/G |
| M2-F011 | F01-1：驾驶舱关闭封口 | V06D ACCEPTED；TD-SW008-098、102；Astra 审计 F-01；卡 072（已验收闭环） | 驾驶舱桥与 `boss_main.qml` 两个产品文件、两个 QML 测试文件（4 个既有路径） | 不可逆的 `beginShutdown`；`confirmStart` 补关闭检查；独立窗口在关闭请求与销毁时封口，嵌入宿主只暂停；完整数据库内容比较与真实窗口实演；产品档，全量九组；GPT 设计里暂停状态统一拒写、线程亲和与代际丢弃未采纳，留作后续 | T/G |
| M2-F02 | F02：查询合同版本字段必填与消费者重验 | M2-F011 ACCEPTED；Astra 审计 F-02；TD-SW008-094 | 拟：`continuity_query.py`、`continuity_resume.py`、`continuity_query_service.py`、`pm_facade_service.py`、`pm_cockpit_service.py`、`ui/cli/pm.py`、`api.py` 与对应测试，落点以实施卡为准 | 两个版本字段去默认并由生产显式填写；完整 query 与能力输入统一严格重验并接入 Facade、CLI、SDK、GUI 的实际消费点；旧 Resume 缺 query 的读取兼容保留，现代入口不得补版本或降级；触及 contracts，按核心档全量九组与变异；已验收闭环（提交 `98c2110d`，父 `763395e4`；CHG-SCPT-2026-395 completed） | T/G |
| V02 | PLC 新需求静态闭环 | V01、V01B、V01C、V01D、C09 | 拟新增 T/e2e/test_pmf_plc.py；批准的 PLC 演练工程 | 新目标到真实 SCL 变化、静态门禁、验收落账；上机编译/下发单列未执行，不虚报工业运行成功 | T/A |
| V03 | 真实更换 Agent 续跑 | E07、C09 | 拟新增 T/e2e/test_pmf_handoff.py；R 下本场景证据 | 第二 Agent 接同一 Work，旧 owner 后续写入拒绝；无需用户搬 JSON/token | T/A |
| V04-R0 | 租约生命周期、受控撤销与 epoch fencing 基础 | C08、E08 | 候选 lease/执行合同、CORE/continuity_execution_service.py、INFRA/continuity_store.py、CLI/continuity.py；T/core/test_continuity_execution_service.py | 正常 SUCCEEDED/FAILED/CANCELLED 在同一事务释放 lease；提前撤销必须由新的 Recovery CHG/Decision/Work/Run 明确授权，且仅在无 Popen 证据时取消；无法证明 child 回收即 PENDING；撤销/接管提升 epoch，旧 epoch 写入被拒绝；不得直改 expires_at 或泄露 token | A/G |
| V04 | 进程中断/lease 到期恢复实演 | E06、V03 | 拟新增 T/e2e/test_pmf_recovery.py | 杀执行进程、主控重启各实演；到期不冒记成功；取消/续跑有合法证据与幂等事件 | A/G |
| V04-R1 | 受控租约撤销与 fencing 真实进程演练 | V04、V04-R0、C09-R3A | T/e2e/test_pmf_lease_recovery.py；R 下真实本机场景证据 | 短租约心跳续租；已启动进程先以 PID/job 指纹证明回收，否则 PENDING；每次接管提升 lease epoch，旧 epoch 的回写被拒绝；不得直改 expires_at、泄露 token 或抢占未知进程；V3.0.24：整张（不拆分）后移到 M3，承诺保留，不属 M2 收口集合（用户 2026-10-09 决定；见 §4.7.9 延期承诺表） | A/G |
| V04-T | V04 与 V03 的测试补强 | V04 ACCEPTED；V03 ACCEPTED；TD-SW008-081 | 范围只在 V04 的恢复测试与 V03 的交接测试文件，不改产品代码 | r03 证明真实的到期拒绝而非错误 owner；Win32 进程探测分存活、已退出、未知三态，查询失败不当作已退出；V03 的 q05 重放测试比较完整的租约值；每项有真实失败变异；测试档 | T/G |
| V05 | GUI 双领域联合验收 | U06、U07、U09C、V02、V04、M2-P1FIX、M2-GOV-TD2、M2-GOV-WBS6、M2-F01A | 拟新增 T/e2e/test_pmf_gui.py；R 下截图/事件证据；顶层汇总行，交付拆为 V05-A、V05-B、V05-C | Python/PLC 各从GUI输入目标到验收；两次业务决策；真实进程/静态检查；无人工改库；仅 V05-A、V05-B、V05-C 各自通过并完成最终真实联验才可更新本行的验收，A 或 B 通过不能写成 V05 完成；Python 与 PLC 均经生产构造路径、真实线程池、真实权限链与确定性收尾；替身、手调 worker.run 与静态合同测试不能替代真实联验；V04-R1 不是 V05 的前置 | T/A |
| V05-A | 带版本和能力标志的 resume/orient 共用只读查询合同 | M2-P1FIX、M2-GOV-WBS6、M2-F01A；TD-SW008-071 | 拟：约 6 个产品文件以内（含 `contracts/continuity_query.py`、`contracts/continuity_resume.py`）与三个测试文件；落点以勘测后的实施卡为准 | 真实生产者与 GUI、CLI、SDK 消费者；`parking_supported=false`、`preemption_supported=false`，挂起与抢占相关动作返回 UNSUPPORTED；缺失或不兼容的版本失败关闭；快照不含租约口令、不建表、不改焦点；触及 contracts，按核心档全量九组与变异；不关闭完整挂起债务 | T/G |
| V05-B | GUI 双根、对共用查询的消费、生产线程池与构造接线 | V05-A ACCEPTED；TD-SW008-083 | 拟：GUI 与驾驶舱接线相关文件（约 6 个产品文件以内），落点以勘测后的实施卡为准 | 生产构造路径、真实线程池、权限链接线；不等于双领域全链已验收 | T/G |
| V05-B2 | GUI 能力提示与有序关闭 | V05-B ACCEPTED；卡 060 | `pm_cockpit_service.py`、`continuity_query_service.py`、驾驶舱桥与窗口入口及对应测试（6 个路径） | 能力提示只在版本合法时才断言“不支持”，查不到、不完整或抛错保持操作停用；关闭有界等待在途任务、超时保留对象、窗口入口按序拆除；17 项变异；首次尝试因一次无关 Git 超时失败，原样保留，第二次受治理执行成功 | T/G |
| V05-B3 | 关闭防护修复（最终验收入口与启动轮询） | V05-B2 ACCEPTED；TD-SW008-091、092；卡 064 | 驾驶舱桥与一个新增测试文件（2 个路径） | `confirmAcceptance` 在关闭后拒绝且不写；启动轮询在交付关闭后丢弃迟到结果、关闭时停计时器；4 项变异；首次受治理执行因 core 组一个对负载敏感的无关测试失败，Run 记 FAILED、Work 记 BLOCKED，原样保留，第二次成功 | T/G |
| V05-C | 真实双领域 GUI 联验 | V05-A、V05-B、M2-F01A ACCEPTED；U06、U07、U09C、V02、V04；M2-F011、M2-F02 ACCEPTED | 拟新增 `T/e2e/test_pmf_gui.py` 与 R 下截图、事件证据 | Python 与 PLC 各从 GUI 输入目标到验收；两次业务决策；真实模型进程与权限；调用真实模型前须先获用户授权；确定性收尾；无人工改库；用户 2026-10-08 已授权调用真实模型：合计不超过 20 次、累计不超过 90 分钟、模型用 Sol（不用 Astra），卡本身仍须批准；联验期间电脑不休眠；PLC 演练工程用 V02 的那个，只做静态语法自检，不碰 TIA 与硬件；已验收闭环（提交 `6e17f086`，父 `98c2110d`；CHG-SCPT-2026-396 completed；第一轮因租约过期作废，第二轮通过，见 §4.7.9） | T/A |
| V06 | 双 Hook 与坏证据负向实演 | G06、C09 | 拟新增 T/e2e/test_pmf_gate_failures.py；隔离 Git 测试仓 | 错 CHG、坏台账、空壳证据、越权文件、预检异常分别拒绝；不得破坏真实用户项目来造测试；坏证据反例须含空集合、错卡或基线或 Run、报告映射缺项、陈旧或漂移字节，明确 FAIL 或 UNVERIFIED，测试报错不得充当成功反例；已拆为钩子半（卡 065，提交 `c3c20e07`）、判卷半入库（V06B）、判卷合同收紧（V06C）与钩子测试补强（V06D），均已验收，残余见 TD-SW008-100、101、096 | T/G |
| V06B | 判卷器入库与坏证据反例 | V06 ACCEPTED；TD-SW008-096；卡 068 | `tests/tools/verdict_check.py`、`tests/tools/__init__.py`、`tests/e2e/test_pmf_gate_judge.py`（3 个新增文件） | 判卷器迁入版本库且判卷语义与外部原件逐分支等价；16 个反例各因自己的原因被拒绝；14 项变异；变异分类器与封存工具未入库，096 保持待执行 | T/G |
| V06C | 判卷器例外合同收紧 | V06B ACCEPTED；TD-SW008-099、101；卡 070 | `tests/tools/verdict_check.py`、`tests/e2e/test_pmf_gate_judge.py`（2 个既有文件） | 基线例外必须有匹配的例外条目与存在的证据文件；共用空报告与畸形判卷文件稳定拒绝；110 份历史判卷新旧判卷器接受或拒绝逐份相同；32 个测试、28 项变异，变异运行器保存完整输出 | T/G |
| V06D | 钩子测试补强 | V06C ACCEPTED；TD-SW008-100；卡 071 | `tests/e2e/test_pmf_gate_failures.py`（1 个既有文件） | 暂存状态逐项比较（mode、blob、stage、路径）与敏感性测试；空台账与垃圾台账、两个项目文件同提交、他项目有效变更单的真实拒绝；15 个测试节点、4 项变异；双根路由与预检内部故障分支留待后续 | T/G |
| V07 | 从通过的 Python 基准提取模板 | C09 | D/auto_pm/templates/python_cockpit 中基准确定的最小文件清单；拟新增 T/e2e/test_pmf_template_python.py | 先固定活体基准 commit/测试，再提模板；生成第二个新工程复测；不能用预制空壳替代；V3.0.24：后移到 M3，承诺保留（不属 M2 收口集合；见 §4.7.9 延期承诺表）；**V3.0.33：部分完成（卡 120，`M3-V07`，提交 `7e926f4f`，CHG-SCPT-2026-410 completed）**：新增 `tests/e2e/test_pmf_template_python.py`（14 个测试），经产品的 `TemplateService` 用真模板 `templates/python-tool` 生成两个工程并复测——文件集精确钉死为 25 个、无残留占位符、生成工程自带 pytest、ruff、严格 mypy 与命令行都通过、第二个工程独立、非法项目号与非法包名被拒绝且不留残留；6 个真实模板变异各被预期测试杀死并按字节还原；**未做**：本行写的“从基准提取模板”（行内的 `python_cockpit` 路径在仓库里不存在，真实模板是 `templates/python-tool`）与新测试在远端 Linux CI 上的结果；**V3.0.34：用户 2026-10-13 裁决“从基准提取模板”保留待办**（不关闭、不改写）；部分完成的事实不变 | T/G |
| V08 | 从通过的 PLC 基准提取模板 | V02、M2-F01A | 母体实际 PLC Copier 模板中基准确定的最小文件清单；拟新增 T/e2e/test_pmf_template_plc.py | .plc.json/INT/VAR/门禁生成后完整；字段错误真实被拒绝；不擅改 O 正式规范；保留 PLC 静态验证边界，不宣称 TIA 编译、下发或设备运行；V3.0.24：后移到 M3，承诺保留（不属 M2 收口集合；见 §4.7.9 延期承诺表）；V3.0.33：勘测与草稿测试已做（`.auto-pm/reports/m3-v08/`，19 个用例本地全过），发现 PLC 静态检查对若干明显破损不报告（TD-SW008-129，需用户裁决）、检查项仍用旧字形标签（TD-SW008-130）、模板里有静态与 `.jinja` 影子重复文件（TD-SW008-131）；实施卡排在本记录之后，只钉“实际会拒绝”的场景，不宣称字段错误全部被拒；**V3.0.34：测试部分完成（卡 123，`M3-V08`，提交 `dcfca387`，CHG-SCPT-2026-411 completed）**：新增 `tests/e2e/test_pmf_template_plc.py`（19 个测试，6 个真实模板变异全部被杀），经产品的 `TemplateService` 用真模板 `plc-standard-project` 生成两个工程，钉死 83 个文件，`PlcChecker` 零失败，八种实际会被拒绝的错误各恰好一个失败项；用户的真实 PLC 门禁是插件命令行，用它检查模板生成的项目修前报 17 个错误，卡 124（`M3-TPL1`，提交 `b5d3e552`）已把模板修到 `check`、`test` 退出码 0；**未做**：驾驶舱 `plc check` 接入插件、本测试收紧为“生成工程 `check`、`test` 退出码 0”（并入 `M3-PLUGIN`）；“PLC 静态检查对若干破损不报告”见 TD-SW008-129 | T/G |

演练目标优先复用已存在的 SW-2026-010、DJ-2026-011，确认其所属和用途后固化精确路径。它们不是运行前假定有效的资产；若不可用，则以 SW-2026-009/DJ-2026-005 的固定只读基准创建隔离演练副本并纳入 V 批次，不默认修改真实业务项目。

V07/V08 的模板文件清单由已经验收的基准差异机械提取；这是依赖于前序产物的确定输入，不是执行代理随意选整棵 templates。基准不通过时停在本原子，不传播模板。

### 4.9 D：稳定交付（D01～D09）

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| D01 | 日常指引和薄适配引用 | V05、U08 | S/01_项目文档/36_驾驶舱与双技术栈日常迭代操作手册_PM.md、AGENTS.md、.agent/rules/project-rule.md、.cursor/rules/workspace-ai-coexistence.mdc；.trae 两执行技能仅在明确授权时纳入 | 所有操作指向已验证高阶入口；技能不手工填表；无死链/双真源；pm-workflow 继续隔离 | L/T |
| D02 | 实现可复现构建入口 | G10 | 拟新增 D/scripts/pmf_build.py、T/core/test_pmf_build.py | 固定Git输入构建载荷，拒绝dirty或缺失依赖；同输入两次清单相同；此源码在D03冻结前完成并验收 | T/G |
| D03 | 固定最终母体提交集合 | D01、D02、Q01～Q03、V06～V08、G03～G10 | 批准路径的 Git 提交；R 下最终源码清单 | 所有必需源码/测试/模板都可从固定 commit 检出；没有只在本机未跟踪文件中的依赖 | T/G |
| D04 | 构建不可变候选 | D03 | 只调用D03提交中已有D/scripts/pmf_build.py；R/artifacts/PMF-20260912/release/ | 相同 commit 两次构建载荷清单一致；manifest/依赖/读写 schema 兼容齐全；尚未 active | T/G |
| D05 | 候选全量门禁 | D04、Q01～Q03 | R/reports/PMF-20260912/D05/ | 按§8.2实际跑必需集合；缺任何项不得发布；全库审计原始失败单列且不得称全绿 | T/G |
| D06 | 新旧版本与数据回退演练 | D05 | 隔离数据副本与候选/previous；R 下证据 | 回退程序保留新事件；不兼容写入拒绝；不拿旧 DB 备份覆盖发布后新事务 | A/G |
| D07 | 受控安装并切换有效版本 | D06；部署范围已批准 | C 的 manifest/新 release/active/previous；实际 Hook 安装映射 | 根 CLI/GUI/Hook/SDK 真实加载同一已验证制品；失败恢复本次指针/脚本，不改母体和业务库 | A/G |
| D08 | 连续三次真实日常交付 | D07 | R 下三次任务与验收证据 | 至少一次 Python、一次 PLC 静态、一次跨会话恢复；每次从新目标开始且无人工改库/治理 JSON | T/A |
| D09 | 项目级最终交付判定 | D08、全部 AC | 本文验收区和 S 中项目交付记录 | 列出实际发布、所有必需 AC/提交、明确历史队列；未达成的承诺不得移出验收表求关闭 | A/G |

D08 用三次可重复任务验收替代“等三天看一看”。无需新增定时器或让用户等一个未定义的观察期；真实日常使用反馈仍可在后续独立迭代接收。

### 4.10 H：有限历史队列（H01～H10，不作全局前置）

| ID | 单一交付 | 依赖/触发 | 精确对象 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| H01 | 固化过期 Run 结算候选 | G07；需要结算时 | CORE/continuity_execution_service.py、CLI/continuity.py、CLI/decision.py、T/core/test_continuity_execution_service.py | 复用现有 settle_expired_run；独立恢复 CHG/Work/Run、目标 Decision、CAS/到期/scope 在克隆库通过；只用合法 CANCELLED，不伪成功 | A/G |
| H02 | 处置 R4-215 的单一过期 Run | H01；目标处置已批准 | RUN-SW008-R4-215-IMPL-01 | 沿用已有中断事实，恢复链自身可终态；CHG215未完成安全目标转 E04，不重开另一产品计划 | A/G |
| H03 | 处置 SAFE004 的单一过期 Run | H01；目标处置已批准 | RUN-SW008-SAFE-004-ACL-01 | 只结算该 Run，不触碰旧 release ACL；未做的 ACL 工作仍保留真实待办 | A/G |
| H04 | 结算A2目标04 | H01；目标处置已批准 | RUN-SW008-A2-201-04 | 只处理该过期非终态Run；CAS/事件可核验；不覆盖母Work已有验收 | A/G |
| H05 | 结算A2目标03 | H01；目标处置已批准 | RUN-SW008-A2-201-03 | 同H04机制、独立目标/幂等键；不夹带其它Run | A/G |
| H06 | 结算A2目标01 | H01；目标处置已批准 | RUN-SW008-A2-201-01 | 同H04机制；已终态则只返回幂等证据，不重复写 | A/G |
| H07 | 判断REC-001的真实剩余范围 | 本轮记录可用 | WORK-SW008-REC-001、RUN-SW008-REC-001-06 | 比对原授权/证据：已完成才收口；否则保留具名剩余项；Run成功不代替Work验收 | A/G |
| H08 | A2工作树处置 | H04～H06；目录处置已批准 | git worktree list 中对应 codex/a2-pm-facade 的精确物理路径 | 无有效占用、独有提交/忽略资产保全后才退役；达不到条件则登记保留理由；禁止git clean | T/G |
| H09 | 已批准文档归档闭环 | 既有归档授权仍有效 | 既有PMF-20260912归档清单的9组源/目标与引用 | 已移动不重复移动；源/目标hash/引用核验后独立提交该清单；不把后续发现混入归档 | T/G |
| H10 | wbs8-candidate用途定性 | 本轮事实可用 | 实际wbs8-candidate目录及其现有索引记录 | 判明普通目录/候选资产而非Git工作树；明确保留/隔离标签；不在其中错误向父Git写入 | T/G |
| H11 | 历史 BLOCKED Work 裁决与活动索引退出 | H01；实施卡 019；H11A/B/C 分批独立批准 | H11A 11 条 Work；H11B NOSKIP Run/Work；H11C 5 条旧终态 lease 与 2 条 Work | 14 条目标 Work 全部 `CANCELLED`；NOSKIP Run 合法结算；5 条 lease 围栏；历史 Run/Checkpoint/旧事件不改写；QG 成功 Checkpoint 仅作辅助证据；事件链 0 断裂、Resume 无冲突、台账 0/0/0 | COMPLETED / ACCEPTED；CHG-349～355 completed |

H01先核对上述五个Run是否仍为原状态/版本；任何已变化目标单独退出，其它获批目标继续。恢复Run自身也必须有合法终态回执。H11 必须先输出 14 条对象的“当前版本—Run/lease—验收事实—建议终态—工作树引用”矩阵，再分离常规终态化与 NOSKIP 单目标恢复；不得把一张批处理卡解释为统一取消授权。历史CHG161～164格式、旧release ACL、远端同步不扩成此队列的额外原子。

### 4.11 里程碑、依赖与第一张执行卡

| 里程碑 | 范围 | 用户拿到的结果 | 退出标准 |
|---|---|---|---|
| M0 交付通道恢复 | B01～B10、G01～G10 | 216 可提交；后续任务知道用什么代码、检什么范围、在哪执行 | 历史完成记录保留；2026-09-27 只核到 B10 `ACCEPTED`、B218 `CLOSED`、G10 后续 Work `ACCEPTED`，未逐项重演双 Hook 与集成候选，当前完整复验 `UNVERIFIED`。 |
| M1 第一条可用 PM-Flow 候选 | P01～P11、E01～E08、C01～C09、G10-R1 | CLI在候选环境完成真实Python新任务；内部对象和证据由系统生成 | **COMPLETED / ACCEPTED**：历史业务终态与台账成立；统一不可变候选最终为 `8b02de55`，完整技术门 PASS；G10-R1 当前字节 Checkpoint、SUCCEEDED/RELEASED Run、CLOSED Work 与 CHG-328/329 终态成立；release `1.3.3-8b02de5` 可重复构建、前切换/回退演练和 exact-tree 验证通过，根入口 configured/effective/load path 一致且无 fallback。原 C09 Checkpoint 局限保留，不回写历史；main 尚未合并。 |
| M2 驾驶舱与双领域候选 | U01～U09、V01～V06（含 V01B～V01D、V05-A～V05-C、V05-B2、V05-B3、V04-T、V06B～V06D；V04-R1、V07、V08 后移到 M3）、M2-P1、M2-P1FIX、M2-F01A、M2-F011、M2-F02、M2-GOV-WBS8、M2-DEP-INT | GUI、SDK、PLC、跨Agent、故障恢复在候选中走同一条链 | V05/V06真实正反验收；V04-R1、V07、V08、M2-F01B、M2-B1 与文档采纳后移到 M3，承诺保留（延期承诺表见 §4.7.9）；M2 基线按 V3.0.24 冻结 |
| M3 稳定使用 | Q01～Q03、D01～D09；自 M2 后移：V04-R1、V07、V08、M2-F01B、M2-B1、M2-GOV-DOCS | 根入口稳定运行，三次真实任务可重复交付 | 全部 AC、制品一致性、兼容回退、全量门禁与 D08 均有证据 |

主依赖：
~~~text
B01 -> B02 -> B03 -> B04 -----> B06 -> B07 -> B08 -> B09 -> B10
               \-> B05 ------/
B09 -> G01 -> G02
        \-> G03 -> G04 -> G05 -> G06
B09 -> G07 -> G08/G09
G06 + G08 + G09 -> G10 -> G10-R1
G10 -> P01 -> P02 -> P03 -> P04 -> P05 -> P06 -> P07 -> P08 -> P08-R -> P09 -> P10 -> P11
G10 -> E01; P09 + E01 -> E02 -> E03 -> E04/E05 -> E06
E05 -> C01 -> C02 -> C03 -> C04 -> C05 -> C06 -> C07 -> C08
C03 + E06 -> E07; E05 + P11 -> E08
C08 + E08 + G10 -> C09-R1 -> C09-R2 -> C09-R3A -> C09-R3B -> C09-R3C -> C09
C09 -> U01 -> U02 -> U03A -> U03B -> U04A -> U04B -> M2-GOV-BL02 -> U05 -> U06 -> U07 -> U08
U04B -> M2-GOV-U04S01; H01 -> H11（COMPLETED / ACCEPTED）
M2-GOV-BL02 -> M2-GOV-ADJ; M2-GOV-BL02 -> M2-GOV-IC02; M2-GOV-ADJ + M2-GOV-IC02 -> M2-GOV-DEP1（软依赖 U05）; M2-GOV-DEP1 -> M2-GOV-WBS2
C09 -> V -> D
U06 -> U07A -> U07B -> U07C -> U07D -> U08（V3.0.19：原 U07 的实际拆分）
U08 -> U09A -> U09B -> U09C -> V05（V3.0.19：V05 前置）
U09B -> M2-GOV-QML1 -> U09C（V3.0.20：U09C 的实际隔离基线是根修提交 d95f45d2）
V01 -> V01B -> V01C -> V01D -> V02（V3.0.21：用户 2026-10-03 确定顺序；V02 另依赖 C09）
V02 -> M2-GOV-TD1 -> V03 -> M2-P1 -> V04 -> M2-P1FIX -> M2-GOV-TD2 -> M2-GOV-WBS6 -> M2-F01A -> V05-A -> V05-B -> V05-C（V3.0.22；V04-R1 不是 V05 的前置；M2-F01B 与 V04-T 不阻塞 V05）
V05-B -> V05-B2 -> V05-B3 -> V06B -> V06C -> V06D -> M2-F011 -> M2-F02 -> M2-GOV-RULE -> M2-TOOL-TIER -> V04-R1 -> V05-C -> M2-GOV-DOCS -> M2-B1 -> V07/V08/M2-F01B -> M2-DEP-TECH -> M2-PUSH（V3.0.23 的执行顺序，不是新增依赖：V04-R1 仍不是 V05 的前置；V04-T 与 TD3R～TD6、V06 钩子半在其间验收；V05-C 的卡仍须批准）
M2-F02 -> M2-GOV-RULE -> M2-TOOL-TIER -> V05-C -> M2-GOV-TD7 -> M2-N1A / M2-N2-0 -> M2-GOV-WBS8 -> M2-DEP-INT -> 审计包 -> GPT 最终审计 -> M2-DEP-TECH -> M2-PUSH（V3.0.24 的冻结顺序；V04-R1、V07、V08、M2-F01B、M2-B1、M2-GOV-DOCS 后移到 M3，不在 M2 收口集合内）
G07 -> Q01/Q02/Q03 -> D03 -> D04 -> D05
~~~

**M2 冻结条款（V3.0.24，用户 2026-10-09 决定）。** ① M2 的收口集合就是下面的剩余清单，本条款随 V3.0.24 落库的那一刻起它就是 M2 的基线：最小 WBS 文档卡（本修订）→ ADJ/IC02 整合（`M2-DEP-INT`）→ 审计包 → GPT 对 M2 的最终审计（发现缺陷按②修）→ 开发运行时技术性部署（审计之后，用户再明确批准）→ 一次推送（用户另行明确授权）。② 此后只允许两类改动进入 M2：原清单里的承诺；最终审计或部署门禁发现的缺陷（修缺陷，不加功能）。③ 其他新想法、新需求、新界面一律进 M3（`.auto-pm/reports/REQUIREMENT_POOL.md` 与 M3 规划），收到时当场说明它在线的哪一侧与对工期的影响；要把它插进 M2，是一次需用户批准的正式基线变更，先报推迟多久再动。④ V3.0.24 之后，本文件对 M2 只做“状态写回”（某卡已验收、提交号），不改范围，直到 M2 收口。⑤ 冻结不禁止修错：发现缺陷按②处理。


V2.0 的第一张执行卡为 B 批次；其历史输入、输出和批准边界保留如下，不能作为 2026-09-13 的当前启动指令：

- 输入：当前 HEAD、216 暂存两文件及已验收证据、SAFE-007 单个差异、当前双 Hook。
- 输出：限定投影修复证据、真实双 Hook 通过、216 两源码隔离提交、独立治理记录集合。
- 批次需要新增声明：允许固定哈希非活动管理候选；允许本次 SAFE-007 投影单元格写入；允许补齐216治理正文；这些不属于之前两代码文件的实施 scope。
- 机器对象：由主控使用现有服务生成恢复 CHG/Decision/Work/Run，明确选定 Work/Run，内部持有有效 lease；不需要先完成 H。
- 原子顺序：B01～B10，内部常规检查/克隆/重试不再逐项问用户。
- 2026-09-19 历史审计投影：P01～P11 均已有最终 ACCEPTED Work、SUCCEEDED Run 与 Checkpoint；P08-R 已以 `e2cb0787e246b0d462f26e2c6bbd5be64ff266d6` 闭合 Mission 的最小 WBS 子 Work 授权，P11 已形成隔离提交 `50a929ccb60de32365fafe0f1819c9c195401656`。P 链从 G10 集成提交 `d87fd3d68222a27850530a14ec1ac452b467be87` 连续可达至该 P11 提交，尚未合并到根 `main`。当时 B218 Work 为 VERIFYING；最新 canonical 核验已是 CLOSED、Run SUCCEEDED、Checkpoint 存在，见 §1.3。该历史审计不授予 C09 恢复执行权。

## 5. 资源分配

### 5.1 每个模型承担什么

模型定位参考本会话已经打开的 OpenAI 官方模型说明；下表是本项目工程分配，不是模型性能保证或账单预测。

| 简称 | 推荐用途 | 约束 |
|---|---|---|
| A | GPT-6 Astra 高推理；架构、候选集成、恢复范围、CAS/事务、最终验收 | 负责边界与反证，不替代机器门禁，也不在明确代码票内擅自扩大整改范围 |
| T | Terra Ultra；一般代码、测试、CLI、QML、构建和明确的恢复算法实现 | 216 继续复用；模型名字和推理档在 Run 记录，不从 UI 名称猜启动模型 |
| G | GPT-5.5 xhigh；独立读差异和失败证据、反证关键事务 | 不代替机器门禁；不让复核者自行扩大整改范围 |
| L | Luna high；已确定映射的日常指引与证据索引 | 不独立处理 DB、lease、Hook、发布或授权 |
| Spark | 可选：已定位的1～2文件文案/命名微修 | 不负责整个WBS包，也不为“每个模型用一下”制造交接 |

A/T 的推荐依据分别是复杂推理与端到端工作、能力成本平衡。G06 和 Q01/Q03 由 Terra Ultra 执行、GPT-5.5 xhigh 独立复核；G10 与 Q02 由 Astra 负责候选边界和运行环境判定。Ultra 是否可用以当前客户端/执行器能力为准；执行器不支持该档时明确报错或使用批次预先允许的替代，不能静默升级费用或换模型。

### 5.2 派工与执行上下文

每个票据只带：WBS ID、用户批准引用、CHG/Decision、选定 Work/Run、完整 owned paths、输入 hash、单行为目标、验收命令、失败边界。批准对象和运行凭据由系统维护，不要求用户复制粘贴。

先单写者、一个执行 Agent、一个只读复核者。只读审计或互不重叠的独立模块可以并行；CORE/pm_facade_service.py、INFRA/continuity_store.py、QML/bridges/pm_cockpit_bridge.py 的写入串行。

同一问题两次失败后，复核者收到的是最小复现、diff 和原始失败，不是整个历史文件夹。模型切换延续同一 Work，按协议建立新 Run/接棒，不再复制一个同名工作项目。

## 6. 风险管理

### 6.1 失败归属和停止范围

| 失败类别 | 处理者及动作 | 能否阻断主线 |
|---|---|---|
| 本原子实现/测试不合格 | 执行者在批准路径内修复；两次同因失败由主控复盘 | 阻断本原子及依赖它的任务 |
| 精确目标已被其它 owner 修改 | 保留现场，主控裁定当前对象和基线；未依赖任务可继续 | 只阻断竞争对象 |
| 已知历史文档格式/旧ACL/远端差异 | 记录到既有 CHG 或 H 的明确条目；不写历史求全绿 | 未证明影响本交付即不阻断 |
| 新的发布必需失败 | 在本批范围内修复；确需范围变化时给出一份最小替换方案及影响 | 阻断对应里程碑，不能删验收条件 |
| 无法启动实际执行器 | E01报告真实错误；其它已授权开发可继续；具名人工接力仅作开发手段 | 真实自动执行验收仍阻断，不能假报完成 |
| 执行环境与普通命令结果不同 | 先用真实控制面函数和同一候选对照；记录环境、argv、HEAD、脏路径与诊断。只有稳定复现并影响产品合同才另列原子范围 | 只阻断当前 Run；不作为候选配置补丁或全局历史清理理由 |
| 真实投影恢复集合扩大 | B06零写退出；固定输入和候选，主控检查为何漂移 | 阻断B06，不自动改全部台账 |

“发现截止”限制当前批次的 scope，不意味着停止报告新事实。每个新事实必须回答它破坏哪一项已定验收；没有这个关联就进入下一轮候选，不形成另一个无限前置计划。

### 6.2 回退约束

B 的文件写入前保留内容备份、hash 和操作事件；补偿仅在目标仍为本次写出的 hash 时执行。G02 安装只备份/恢复两 Hook，不改变 Git 历史。源码失败保留候选 worktree 与证据，禁止 reset/clean/stash 他人改动。D06/D07 回退程序和指针，不自动覆盖已产生新事件的数据库。

读取 SQLite 要考虑 WAL；在线一致副本使用只读连接和 SQLite backup 机制，不把正在变化的 db 主文件单独复制当完整快照。报告不打印租约秘密。正式 verify-only 对被检业务文件保持无写入；需要输出报告时写专用证据目录并明确这项诊断副作用。

## 7. 沟通计划

本轮已经完成方案修订授权内的工作。后续对一个写入批次给用户的是完整范围卡，不是“是否允许我再检查一下”。技术负责人负责准备机器对象及脚本参数，不让用户从多个恢复方案中承担技术选型。

| 时点 | 用户看到的内容 |
|---|---|
| 批次首次开工 | 单一推荐、全部内部原子、精确范围、验证和必要风险动作 |
| 普通执行期间 | 当前可用能力及关键结果；同范围测试/重试自动推进 |
| 真正越界或外部风险变化 | 一个汇总决策：发生什么、影响哪个验收、最小调整是什么 |
| 里程碑验收 | 可重复操作、机器证据、实际未通过项；不把代码验收称运行生效 |
| 提交/发布 | 使用已有明确批准；新增范围一次列清，不重复索取已授予的权限 |

计划、执行、验收和发布状态分别显示。旧39、归档37和其它历史WBS只作引用，本版是当前产品排期入口；26继续提供治理边界。新聊天只需本文件、当前WBS ID及系统Checkpoint，不能靠聊天记录重建第二账本。

## 8. 验收标准

### 8.1 固定验收场景

| AC | 必须通过的行为 | 主责 | 最终所需证据 |
|---|---|---|---|
| AC01 | 新PID+目标生成方案，无需预先手造内部对象 | P11 | 入口调用、PlanningDraft/范围卡hash、0次用户手写JSON |
| AC02 | 同一确认重放/中断重试不重复授权 | P10 | 每持久化边界失败注入、对象数量与事件 |
| AC03 | 实际执行进程启动 | E03/E08 | actual model、session、进程身份、真实启动回执 |
| AC04 | 失败退出不因文字“成功”变成成功 | E05 | 0/非0/终止三类实演 |
| AC05 | 差异和门禁证据绑定当前内容 | C03 | 命令/cwd/版本/hash/Exit Code；坏证据拒绝 |
| AC06 | 验收后正确CHG与精确台账落账 | C07/C09 | 无占位字段、目标零差异、相邻编号未改 |
| AC07 | 投影写失败可重试且不重复结算 | C05/C07 | 崩溃点/权限错误演练、待同步状态、幂等事件 |
| AC08 | 重启、到期、真实换Agent可恢复 | V03/V04 | 同Work续跑、旧owner拒绝、恢复自身终态 |
| AC09 | CLI/GUI/SDK行为与权限一致 | U07/V05 | 三入口共享Facade/运行身份的联测；U07提供SDK完整闭环，V05提供GUI实演 |
| AC10 | Python与PLC静态新任务完成 | C09/V02/V05 | 两领域真实差异、领域门禁、验收/落账；硬件未测明确 |
| AC11 | 双Hook与scope防御真实有效 | V06 | 正常放行；伪号/坏账/异常/越权均拒绝 |
| AC12 | 已验证模板与薄技能可复用 | V07/V08/D01 | 活体基准→模板→第二工程；规则与指引无死链 |
| AC13 | 可复现制品、入口一致、回退保留数据 | D04/D06/D07 | commit、manifest、实际加载路径、schema兼容 |
| AC14 | 连续三次无需人工修治理对象 | D08/D09 | 三条完整任务记录，至少含Python/PLC/跨会话 |

所有 AC 均为必需。研发阶段已实现不代表稳定环境已通过，D09只在部署和日常使用证据齐全后判定产品完成。

### 8.2 开始时就确定的门禁合同

执行与发布使用下表，不再用一句“全量全绿”遮蔽实际范围。这是修订方案中的显式合同，须进入批次批准；不是把现有失败擅自改为 PASS。

| 门禁 | 每原子/批次 | 最终候选 | 判定 |
|---|---|---|---|
| 本行为与受影响组件测试 | 每原子必跑 | 全部纳入回归 | 必需 Exit 0，无新增 skip 或硬编码成功 |
| 母体全量 pytest | G07跑基线；Q01/Q02 和公共状态机改动后复跑 | D05必跑全量 | 必需 Exit 0；既存skip逐项列明，覆盖必需AC的skip不能豁免 |
| Ruff/Mypy | 本次变更文件及其必要依赖 | D05对产品批准范围、依赖和新增代码再跑 | 必需 Exit 0；不能排除本次实际影响路径求通过 |
| 全库 Ruff/Mypy 审计 | G07固定全库原始结果/诊断指纹 | D05以相同配置重跑 | 所有FAIL如实展示；既存且不在交付依赖的债独立记录；新增或恶化项必须解决 |
| CHG/文档实质与引用 | 目标CHG、改动文档、模板生成产物 | 全部交付工件 | 必需无占位/死链；历史未改文档结构告警不冒充本次PASS |
| Git双Hook | B08实际预检；G后每批预检 | 所有实际提交及安装后复测 | 必需真实通过，无绕过；作用域变化仅按G05批准合同 |
| Run 执行就绪 | 每个源码 Run 创建前执行真实控制面快照 | G10、D05复核记录 | 控制面以实际候选返回一致 HEAD、空闲路径事实和无诊断退出；环境差异未定位前不得用本地配置补丁掩盖 |
| 台账 | 当前任务及所属项目 | 发布时全部注册项目 | 缺项/悬空/状态差异都为0；任何异常非零 |
| Release/schema/加载身份 | 相应候选 | D05～D07必跑 | 实际commit/manifest/代码路径/读写兼容一致 |
| 真实E2E与GUI | 对应C/U/V原子 | D05/D08复核 | 无进程PoC、无GUI实演、无PLC静态链任一缺失都不能称交付 |

全库审计不是最终产品“全工作区零债”的承诺。发布必需集合包括全部母体回归、实际交付依赖的静态检查、全部发布台账和所有AC；如果历史诊断落在实际交付依赖内，就必须纳入本范围修复，不能以“历史债”排除。若用户要求全仓所有项目类型错误清零，那是单独的明确扩大目标，不与 pm-flow 可用性混写。

G07 已知失败的闭合归属固定为：Q01 处理候选中 Vartable 真实样例可复现性，Q02 处理 Qt PDF 导出运行环境，Q03 处理 Mypy 模块发现。历史 CHG 格式告警不属于三项，也不作为 G06、Q 或 D05 的通过条件。每项必须保留原始失败指纹和新的命令证据；不得通过扩大忽略规则、删断言或把失败改标记为历史而获得绿灯。

### 8.3 可直接使用的现有命令

以下命令本轮已由现有源码/帮助确认；不在真实环境执行带修复参数的命令来验证产品。

~~~powershell
# 工作区根，只读恢复；默认多任务时由主控明确选择。
& .\.venv\Scripts\python.exe -B -I .\main.py pm resume SW-2026-008 --json
& .\.venv\Scripts\python.exe -B -I .\main.py pm resume SW-2026-008 --work-id <已选Work> --run-id <已选Run> --json

# 工作区根，只读台账；此命令不会纠正差异。
& .\.venv\Scripts\python.exe -B -I .\main.py ledger reconcile SW-2026-008

# 在研发候选 D 工作目录，用工作区 .venv 解释器运行216目标回归。
& <工作区Python绝对路径> -B -m pytest tests/change/test_ledger_updater.py -q -p no:cacheprovider -o addopts=
& <工作区Python绝对路径> -B -m ruff check --no-cache auto_pm/domain/change/ledger_updater.py tests/change/test_ledger_updater.py
& <工作区Python绝对路径> -B -m mypy --no-incremental auto_pm/domain/change/ledger_updater.py
~~~

占位符由系统从所选 Work 和 workspace context 代入，不交给用户手填。实际执行命令必须记录完整 argv/cwd/被测hash；秘密不进入 argv。pytest 日志/缓存/覆盖率写专用目录或禁用，禁止污染 release exact-tree。

D02 的 pmf_build.py、G06 增强预检、P11 的新目标参数、U07 的 Cockpit SDK 是拟建接口。它们须先完成对应原子和帮助/行为测试，才能作为后续派工的实际命令。活动1.3.3不提供 settle-expired；H 的恢复不能复制该命令到现行 root 后期待成功。

## 9. 附件

### 9.1 依据

- [用户指定的历史需求蓝图](archive/G1-20260909/Cockpit_OS_大一统集成与超级特种兵架构方案_WBS.md)：读取产品需求，不执行其中旧入口/技能指令。
- [26 治理基线](26_SW-2026-008_治理恢复与连续性重基线总计划_PM.md)：真源及权限边界。
- [36 日常操作手册](36_驾驶舱与双技术栈日常迭代操作手册_PM.md)：领域交付、Work/Run及分范围验证。
- [38 既有恢复证据](38_Cockpit_OS_工作区恢复与单主线收口报告_REP.md)：历史工作树和恢复依据。
- [归档37](archive/PMF-20260912/37_Cockpit_OS_超级特种兵大一统目标架构与迁移总方案_PM.md)：已有资产复用，不重开旧排期。
- [39 V1.0.0 历史快照](archive/PMF-20260912/39_PM-Flow_恢复与可用化总方案_WBS_PM_V1.0.0.md)：仅用于比较本次修订。
- O/01_项目管理域/02_规划阶段/027_迭代项目计划模板_PM.md：沿用九节结构。
- O/01_项目管理域/02_规划阶段/033_功能模块迭代流程标准_PM.md：真实验证、源码基线、授权、发布。
- O/01_项目管理域/04_变更管理/042_通用变更管理流程规范_PM.md §3.7：CHG/Decision与Work/Run边界。
- [OpenAI模型定位](https://developers.openai.com/api/docs/models)、[模型指导](https://developers.openai.com/api/docs/guides/latest-model)：本会话已实际打开；具体WBS分配由本计划承担。

### 9.2 本轮修改范围和可验证状态

本轮 V2.5.0 仅修订主工作区本39文件中的真实进度、C09 收敛门槛、依赖和版本记录。V1.0.0 历史快照及隔离候选 V2.4.8 保留原样；未改产品源码、Continuity 数据库、Hook、release 指针、CHG/Decision/Work/Run 状态或隔离候选。`SW-2026-009` 的未提交 `CHG-SCPT-2026-012` 原样保留，其 approved 状态和未完成验证结论分别陈列，不能以文档修订代替业务验收。

V2.5.1 只同步本轮新核实的 V04-R0、R3B 和旧 `app.db` 事实及 §4.8/V 批次启动门槛；保留原备份、未提交候选、FAILED Run 与 `CHG-SCPT-2026-012`，不据此改动 canonical 状态或宣告任何业务验收。缺失的 JSON 处置回执与未建立的独立验收均明列为未通过，不通过文档补记为已完成。

V2.5.2 只将本轮单目标 FENCE 验收结果写回 WBS 当前投影；保留 FIX、R3B、R3C、原业务及旧 `app.db` 证据门的独立状态，不从台账的共用“已关闭”标签推断 CHG 已 `closed`。本 WBS 修订不授权其它状态流转。

V2.5.3 只将 FIX 子 Work 的独立验收写回 WBS 当前投影；原 V04-R0 Work、CHG-309 整体、R3B/R3C、原业务与旧 `app.db` 证据门不随之关闭。候选源码和测试仍未提交，不把 Work 验收解释为提交、合并或发布授权。

V2.6.2 仅同步唯一 M1 不可变候选的真实质量证据，并新增 G10-R1 生命周期/Resume 收敛任务。它不新建或流转 canonical 治理对象，不改历史 Checkpoint、P2/CHG-323、release 指针或稳定部署，不授权批量处置历史 BLOCKED Work，也不把候选 PASS 写成 M1 正式完成。V2.6.3 随后以独立 CHG/Decision、当前字节治理证据链、可重复 release、回退演练和根入口身份验证完成 M1 收口；该收口仍不授权 main 合并、P2 历史清理或 M2 执行。

复核项：95 个原子编号唯一；补齐既有 P08-R 的任务行，C09-R3B/R3C 位于 C09 前且不逆转原业务 Run 的历史；G10-R1 位于 G10 后并成为 M1 正式治理验收前置；所有依赖均指向存在的编号且无环；所有 REQ/AC 有责任任务；PlanningDraft 与 Mission 的安全边界、G06 的输入合同、G10 集成边界和 Q01～Q03 的最终门禁归属明确。文档校验只证明计划结构完整，不代替产品验收。

### 9.3 版本修订记录

| 版本 | 日期 | 改动 |
|---|---|---|
| V1.0.0 | 2026-09-12 | 初始25工作包，恢复前置过长、粒度不均、真实提交入口验证过晚 |
| V2.0.0 | 2026-09-12 | 纠正当前事实与Hook因果；80原子、4产品里程碑、限定bootstrap、显式对象选择、门禁合同、历史旁路和完整需求验收映射 |
| V2.1.0 | 2026-09-13 | 按实际 G06 启动演练补充真实执行就绪门；把 G06 的同一 index 快照合同扩至 enforcer；新增 G10 候选集成与 Q01～Q03 已冻结基线失败收敛；更新当前执行入口 |
| V2.1.1 | 2026-09-14 | 修正 G10 的 Run/Checkpoint 顺序：不可变提交先装配为最终、洁净的非活动候选，Run 再以该 HEAD 启动；保留首次 G10 基线漂移阻断作为审计证据，不改产品源码、来源候选或 release。 |
| V2.2.0 | 2026-09-14 | 修正 P02 先建 DRAFT Mission 与既有强授权 Mission 合同的矛盾；新增独立、不可执行、可幂等持久化的 PlanningDraft，将真实 CHG、规范、范围卡、Decision、Mission、Work 重排为 P02～P11，并同步全部下游依赖与验收映射。 |
| V2.3.0 | 2026-09-14 | 根据 P08-R 的闭合证据补全强授权 Mission 的子 Work 类型契约：仅允许 WBS，明确拒绝其它类型；将 P08-R 设为 P09 的唯一新增门禁，并更新主线与当前推进投影。 |
| V2.4.0 | 2026-09-14 | 根据 P11 冷启动重放失败的根因证据，将 Facade 及其回归测试纳入 P11 四路径范围；要求 CHG 离开 DRAFT 后仍能以相同 request_id 与输入恢复同一范围卡和唯一授权链，不在 CLI 建立旁路。 |
| V2.4.1 | 2026-09-19 | B01～P11 只读审计后同步执行投影：P01～P11 已验收并以 `50a929c` 固定 P 链隔离提交锚点；保留 B02～B09 汇总 Work 仍为 VERIFYING 的事实，不修改原子合同、产品源码或运行态。 |
| V2.4.2 | 2026-09-21 | 根据 C09 候选实演的运行身份与单一 Store 复核，新增 C09-R1 双根绑定前置；不改变 M1 范围、里程碑顺序或发布边界。 |
| V2.4.3 | 2026-09-21 | 根据实际外部隔离工作树 Run 创建失败、旧意图无 Run 与新文件投影合同，新增 C09-R2 并明确 C09 依赖；保留 R1/R1a 历史验收与旧意图，修正原子任务计数。 |
| V2.4.4 | 2026-09-21 | 根据 C09/Q03 的执行准备与长租约失败，新增 C09-R3A：计划持久化先于 Run/lease、有界可配置租约及启动前失败无残留；新增 V04-R1：受控撤销、进程证明与 fencing 的独立系统级验收。不改旧 Run、数据库、产品源码、release 或部署。 |
| V2.4.5 | 2026-09-23 | 根据真实 24 小时 C09 租约阻断，将租约生命周期、Recovery 撤销和 epoch fencing 前置为 V04-R0；C09-R3A 可经 V04-R0 的无 Popen 证明恢复。V04-R1 保留真实进程回收演练。不改历史事件，不以系统时间或直改数据库绕过。 |
| V2.5.0 | 2026-09-23 | 只读对照主工作区、C09 隔离候选和 canonical 数据库后，将原业务 VERIFYING/未验收、两条辅助 Run FAILED、R3B/R3C 未闭合及 V04-R0 未闭合写入当前投影；将跨项目证据、租约、越界脏路径差异、原 Run 验收权限和 CHG/台账设为 C09 联合收敛门槛。本轮只修订 WBS。 |
| V2.5.1 | 2026-09-24 | 重核 V04-R0 原 Run CANCELLED、FIX/FENCE 的 SUCCEEDED Run 与同头 Checkpoint、两个 VERIFYING Work 和待独立验收，以及两次 FAILED Recovery；核实旧 `app.db` 原字节备份哈希和当前 HEAD blob 一致，但处置 JSON 回执缺失、C09FE/FINISH Runs FAILED；明确 V01～V08/M2 未整体启动，保留 C09 联合收敛阻断。仅更新 WBS 事实。 |
| V2.5.2 | 2026-09-24 | 用户仅验收 `CHG-SAFE-2026-012` 的单目标 FENCE；受控流转使对应 Work 为 ACCEPTED、CHG 为 completed（非 closed），台账对账 0 差异。FIX、R3B、V04-R0 整体、原 C09 与 M1/M2 未因该验收通过。 |
| V2.5.3 | 2026-09-24 | 对 V04-R0 FIX 独立核验：当前候选字节与同头 Checkpoint 一致，补做 10 个相关定向用例及 FAILED/CANCELLED 临时隔离验证；仅 `WORK-SW008-PMF-V04R0FIX-001` 流转 ACCEPTED，`CHG-SCPT-2026-309` 为 implementing，原 V04-R0 Work 与 C09/M1/M2 均未验收。 |
| V2.5.4 | 2026-09-24 | 对原业务候选旧 `app.db` 的备份、原会话输出、Decision 范围与当前/HEAD 字节作限定补充证据裁决；原始 JSON 回执仍缺失，不追认失败 Run 或 C09 验收。 |
| V2.5.5 | 2026-09-24 | 独立复核 R3B：既有 SW008 Checkpoint/Decision 不覆盖 SW009；原业务候选 SW009 strict Mypy exit 1（201 项），故联合门继续阻断。 |
| V2.5.6 | 2026-09-24 | 在新隔离候选完成 SW009 12 文件 strict Mypy 修复并独立核验自动 Checkpoint、Run/lease、Work、CHG 与台账；保留原业务候选的旧字节、R3B 跨工作树联合门和 R3C/C09/M1 阻断，更新根 launcher 的真实 active 加载事实。 |
| V2.5.7 | 2026-09-24 | 将 SW008 15 与 SW009 12 个已验收差异机械组合到同头隔离候选；同一候选两项目六项真实门禁、自动当前字节 Checkpoint 与额外 SW009 测试文件 strict Mypy 均通过；联合质量 Work ACCEPTED、Run SUCCEEDED/lease RELEASED、CHG-317 completed、SW008 台账零差异。旧 R3B 总 Work 与 V04-R0 原 Work 未闭合，原业务候选/Run、R3C、C09/M1 均不外推。 |
| V2.5.8 | 2026-09-24 | 在原 V04-R0 Work/Decision 范围内补同候选验证 Run/自动当前字节 Checkpoint，完整核心 129 passed、Ruff/Mypy exit 0，原 Work ACCEPTED、CHG-309 completed；原取消 Run 与失败 Recovery 均保留。结合已通过的 SW008＋SW009 联合质量证据，旧 R3B Work 的 Checkpoint 重核 current=true 后独立 ACCEPTED。CHG-310 仍 implementing，原业务候选字节、R3C/C09/M1、合并/发布边界均未改变。 |
| V2.5.9 | 2026-09-25 | 独立只读审计与物理验证：确认稳定部署回退加载 1.3.2 且 1.3.2 上下文存在 release_id 谎报（归独立基础设施线 Track A）；完成 c09-final-e2e 与 c09-r3b-joint-20260924 字节比对与 diff 矩阵，证实 FE 独有 test_pmf_python.py 在 JT 环境实测 exit 0；定性 09-25 凌晨旁路测试候选；确立受控推进方案。 |
| V2.6.0 | 2026-09-25 | C09 业务端到端闭环与 M1 正式达成：专用 Decision DEC-20260925-C09R3C01 恢复原业务 Run 验收租约，清洗 c09-final-e2e 候选至 3 owned paths，五门全绿；记录 Checkpoint CP-SW009-PMF-C09-FINAL-001，经用户明确批准；通过 PmFacadeService.accept 与 PmClosureService 闭环流程，CHG-SCPT-2026-012 完成实质注入；RUN-PLAN-F767C11087531180 终态 SUCCEEDED（租约 RELEASED），WORK-MSN-F0564CAF05D18E0B 与 MISSION-0648162FF0602FDD 终态 CLOSED；SW-2026-009/008 台账 0 差异；M1 标记 COMPLETED / ACCEPTED。 |
| V2.6.1 | 2026-09-27 | 独立复验校准：保留 V2.6.0 业务状态机及用户批准历史，但纠正“五门全绿”的覆盖口径；原 CP 的 SW009 Mypy 使用 `--follow-imports=skip` 且漏检测试，原候选 strict 双文件复测 Exit 1；M1 当前质量 `FAIL`，M0 当前完整复验 `UNVERIFIED`。P2 五文件本轮因九条历史活动 Work 路径冲突、NOSKIP 旧 Run/租约未安全处置而停在创建新 Work 前；没有新 Run、Checkpoint 或 177 项全套测试。 |
| V2.6.2 | 2026-09-27 | 从已验收 G10 隔离集成链重建唯一 M1 不可变候选 `a1c5d94`：SW008 扩展核心 203 passed，6 文件 Ruff/normal-import strict Mypy Exit 0；SW009 8 passed（9 subtests）及 Ruff/Mypy Exit 0；C09 E2E pytest/Ruff/Mypy Exit 0；候选洁净、临时产物已清除。新增 G10-R1 固定 ACCEPTED 非活动、BLOCKED 仍活动、显式 Resume 与多活动 Fail-Closed 合同。保留原 Checkpoint 局限，不创建治理终态，不合并、部署或切换 release。 |
| V2.6.3 | 2026-09-27 | G10-R1 六路径当前字节治理链完成，最终洁净提交 `8b02de55` 已推送至 `origin/codex/g10-r1-lifecycle`，未合并 main；CHG-328/329 completed，Run SUCCEEDED/lease RELEASED、Work CLOSED。由该提交可重复构建并注册 release `1.3.3-8b02de5`，active/previous exact-tree、隔离前切换/回退与根入口身份均通过，SW008 台账 0/0/0。M1 标记 COMPLETED / ACCEPTED；M0 当前重验、原 C09 Checkpoint 局限、P2/CHG-323 阻断和 M2 未启动事实不变。 |
| V3.0.1 | 2026-09-27 | U01 五状态演示原型在独立隔离候选提交 `d88eedd5` 固化；静态原型测试 2 passed、Ruff/Mypy/diff-check 均为 Exit 0。`CP-SW008-U01-001`、Run SUCCEEDED/lease RELEASED、Work CLOSED 与 `CHG-HMI-2026-001` completed 形成当前验收链，SW008 台账 0/0/0。M2 标记 IN_PROGRESS；U02～U08、P2、合并、部署和 release 切换均未由此启动。 |
| V3.0.2 | 2026-09-28 | Batch C 全量资产与 M2 准入审计闭合；新增原子任务 `M2-GOV-IC01` 及实施卡 015，只规划实施卡合同与自动化工作流。 |
| V3.0.3 | 2026-09-28 | 启动 `M2-BL01`，从运行身份修复基线机械引入 U01 两文件，形成 M2 唯一不可变集成基线。 |
| V3.0.4 | 2026-09-28 | `M2-BL01` 验收闭环：候选 `4851fce4`、Checkpoint、Run/Work、CHG 与台账证据齐备。 |
| V3.0.5 | 2026-09-28 | `M2-GOV-IC01` 八文件技术门禁通过并形成 Checkpoint，但首次提交因 CHG/台账未进入同一暂存快照而被正常门禁拒绝；历史如实保留，唯一纠正链改为八个产品路径加两个提交证据路径，禁止第十一路径。 |
| V3.0.6 | 2026-09-28 | `M2-GOV-IC01` 有界纠正闭合：八产品路径与两提交证据路径分层建模，33 项测试及 Ruff/Mypy/diff-check 全绿，当前十路径 Checkpoint `CP-SW008-M2-GOV-IC01-003` 与正常 hook 提交 `b7bb9357` 成立，Run/Work/Mission/CHG 均达合法终态；下一项为 U02 只读预检。 |
| V3.0.7 | 2026-09-28 | U02 开工前校准：确认现有 QML 接线与测试需要五条产品路径；`PlanningDraft` 无确定范围字段，界面只能如实标示“范围待规划”，不得提前创建 Mission。实施卡 016 已建，本次不宣称 U02 产品或治理验收。 |
| V3.0.8 | 2026-09-28 | U02 五产品路径已在 `m2-u02-planning-draft` 隔离候选实现，定向 QML/Cockpit 11 项、Facade 27 项、Ruff/Mypy/diff-check 均 Exit 0；`CP-SW008-M2-U02-001` 绑定 `b7bb9357` 与七条授权路径。正常 Git Hook 因候选旧基线 CHG 集合与现行台账不一致（120 孤儿、3 状态差异）拒绝提交；Run/Work 如实置 `BLOCKED`，CHG-339 保持 `implementing`。未提交、未验收，不改变 M0/M1 或 release。 |
| V3.0.9 | 2026-09-28 | U02 有界纠正闭环：确认首次阻断源于把 canonical 294 条完整台账复制到历史候选；恢复 `b7bb9357` 的 173 条分支本地快照并仅增量加入 CHG-339 后，候选达到 174/174、0/0/0。完整复跑 38 项测试及 Ruff/Mypy/diff-check，`CP-SW008-M2-U02-002` 与正常 Hook 提交 `74493c37` 成立；Run SUCCEEDED、lease RELEASED、Work/Mission CLOSED、CHG-339 completed，canonical 台账 0/0/0。旧 `CP-SW008-M2-U02-001` 仅保留为失败尝试历史证据。 |
| V3.0.10 | 2026-09-28 | U03 开工前代码评审确认一次性启动与后台快照刷新属于不同风险域，将原 U03 拆分为 U03A/U03B 并分别设置独立验收边界；本次仅修订规划，不启动执行。 |
| V3.0.11 | 2026-09-28 | U03A 一次性受控启动闭环：不可变提交 `316ab46b`、当前字节 Checkpoint `CP-SW008-M2-U03A-002` 与 35 项定向门禁成立；首次过早 Run 如实取消并保留，最终 Run/Work/Mission/CHG 合法闭环。 |
| V3.0.12 | 2026-09-28 | U03B 后台快照刷新闭环：隔离候选洁净提交 `b8010027`、当前字节 Checkpoint 与 11 项门禁成立；首次 READY Run 安全取消并保留，最终治理链合法闭环。下一产品任务校准为 U04。 |
| V3.0.13 | 2026-09-28 | U04 开工前只读根因核验：现有事件可证明执行阶段，但终态事件缺少可供 UI 可信投影的结构化失败原因；旧 `ActivityTimeline` 仍消费 PM_SESSION 摘要且驾驶舱无连续后台刷新。将 U04 拆为 U04A（不可变进度/失败合同）与 U04B（当前 Mission 时间线/连续刷新），新增实施卡 018；另登记非阻断的历史活动 Work 清障 H11 与规范沉淀 `M2-GOV-U04S01`。本次仅修订 WBS 与实施卡，不创建治理对象或执行源码变更。 |
| V3.0.14 | 2026-09-28 | U04A 已在 `d59120c7` 不可变隔离提交完成：结构化失败合同、哈希事件写入、legacy 兼容与 fail-closed 读取均落地；188 项 Pytest、Ruff、strict Mypy、diff-check 全绿；`CP-SW008-M2-U04A-001` 当前，Run/Work/Mission/CHG 合法终态，台账零差异。U04B 消费第二次用户授权并从该提交启动；H11、U05、合并、推送、部署与 release 仍在边界外。 |
| V3.0.15 | 2026-09-28 | U04 完整验收：U04B 产品提交 `d200eb9b`、R1 合同提交 `e05fafa1`、两个 Checkpoint、唯一终态租约恢复事件及治理终态成立。H11 只读准备将 14 条历史 BLOCKED Work 分为 11 条常规处置、NOSKIP 单目标结算、5 条旧终态未释放 lease 兼容裁决；仅更新 WBS 与实施卡，不执行 H11。 |
| V3.0.16 | 2026-09-29 | H11 已完成并验收：14 条目标 Work 均 `CANCELLED`、NOSKIP 已结算、5 条旧终态 lease 已围栏，历史证据保留；明确 `fubai`/`baiyang` 等权署名及 Claude/用户写入来源。新增 BL02、ADJ、IC02、DEP1、WBS2 五个治理原子任务，冻结 U/R/发布三线血统、开发运行时切换政策与 U05 的 BL02 硬依赖。本次仅修订 WBS。 |
| V3.0.17 | 2026-09-30 | 整改阶段 1～5 最终证据写入：BL02 `7cfe227e`、ADJ `d876cf98`、IC02 `e6529115`、整合 `a808fa8a` 与开发运行时 `1.3.3-a808fa8`（CHG-SCPT-2026-356～361 completed）；H11 保持 `COMPLETED / ACCEPTED`；新增 §4.7.3（当前值对当时值的时点证据、来源说明、偏差声明、技术债登记、U05 准入）；§4.7.1 仅更新状态单元格并补 `M2-GOV-WBS1` 行；`M2-GOV-WBS2` 为 `VERIFYING / PENDING_ACCEPTANCE`，待用户亲自验收。本次仅修订 WBS，不创建产品提交、不合并、不推送、不部署。 |
| V3.0.18 | 2026-09-30 | 用户亲自验收 V3.0.17 复查候选 `e07f7662`：`M2-GOV-WBS2` 更新为 `COMPLETED / ACCEPTED` 并绑定验收回执；新增 §4.7.3 “V3.0.18 补记”与当前状态段落。仅状态、回执引用与版本记录，不改其它阶段状态，不合并、不推送、不部署。 |
| V3.0.19 | 2026-10-01 | U05、U06、U07A～U07D、U08 验收回写（`ace7a959`、`8b7f199a`、`795fe448`、`35379585`、`9a92e9b7`、`460e24f6`、`d40318d0`；CHG-SCPT-2026-362～369 completed）；补记原 U07 拆分为 U07A～U07D；新增 V05 前置任务 U09A～U09C（`PLANNED / NOT_AUTHORIZED`），V05 增加对 U09C 的依赖，M2 范围改为 U01～U09；新增 §4.7.4 与两项技术债；§4.7.1 补 `M2-GOV-WBS3` 行，其实施与验收以 CHG-DOCU-2026-024 为准。本次仅修订 WBS，不创建产品提交、不合并、不推送、不部署。 |
| V3.0.20 | 2026-10-03 | U09A～U09C 验收回写（`eebdeecb`、`cec3afa7`、`3c32e8ad`；CHG-SCPT-2026-370～372 completed）；§4.7.1 新增 `M2-GOV-QML1`（根修 `6eead5e4`、`d95f45d2`；CHG-SCPT-2026-373 completed）与 `M2-GOV-WBS4` 两行并回写 `M2-GOV-WBS3` 状态；新增 §4.7.5（验收证据、U09C 偏差、M2 代码线技术基线、任务计数口径、教训与技术债）；文首任务计数改为逐行机器计数口径；其实施与验收以 CHG-DOCU-2026-025 为准。本次仅修订 WBS，不创建产品提交、不合并、不推送、不部署。 |
| V3.0.21 | 2026-10-03 | V01 验收回写（`37a4faff`；CHG-SCPT-2026-374 completed；实际 5 路径）；§4.7.1 新增 `M2-GOV-WBS5` 并回写 `M2-GOV-WBS4` 状态；§4.8 新增 V01B、V01C、V01D 三行并改 V02 依赖；新增 §4.7.6（V01 证据、已知限制、一致性核对需求、任务顺序、技术基线更新、教训与技术债）；任务计数 117 → 121；其实施与验收以 CHG-DOCU-2026-026 为准。本次仅修订 WBS，不创建产品提交、不合并、不推送、不部署。 |
| V3.0.22 | 2026-10-06 | V01B～V04、第 1 期、TD1、第 1 期审计缺陷修复与 TD2 验收回写（提交 `d890be25`、`1e1ef760`、`fb94afa9`、`cf6f6f33`、`b6668dcf`、`edeeead9`、`4e165cf4`、`a6447be6`、`948884db`、`1956dd9a`）；§4.7.1 新增 5 个治理与产品任务行并回写 `M2-GOV-WBS5` 状态；§4.8 新增 F01-a、F01-b、V04-T、V05-A、V05-B、V05-C 并补充 V05、V06、V08；新增 §4.7.7（验收证据、口径更正、F01 与 V05 拆分、F05 分期、新顺序、技术基线更新、教训）；任务计数 121 → 132；其实施与验收以 CHG-DOCU-2026-027 为准。本次仅修订 WBS，不创建产品提交、不合并、不推送、不部署。 |
| V3.0.23 | 2026-10-08 | F01-a、V05-A/B/B2/B3、V04-T、V06 系列（钩子半、判卷半入库、合同收紧、钩子补强）与台账四卡验收回写（提交 `01ad3923`、`5a2f9c48`、`5686bd9f`、`aeedf92f`、`769f145d`、`715713bb`、`c3c20e07`、`4d0b33ac`、`23e6ed64`、`6a84a186`、`592211ee`、`06f4ae4d`、`83369f67`、`3bc740a4`、`763395e4`）；§4.7.1 新增 11 个治理任务行并回写 `M2-GOV-WBS6` 状态；§4.8 新增 V05-B2、V05-B3、V06B～V06D、M2-F011、M2-F02 并补充 V05-C 与 V06；新增 §4.7.8（验收证据、口径更正、三次独立审计的处置、授权记录、新顺序、部署意图、M3 候选、提速测量结论、技术基线更新、教训）；任务计数 132 → 150；其实施与验收以 CHG-DOCU-2026-029 为准。本次仅修订 WBS，不创建产品提交、不合并、不推送、不部署。 |
| V3.0.24 | 2026-10-09 | M2 冻结修订（最小版）：采纳 V3.0.23；回写 F02 `98c2110d`、V05-C `6e17f086`、TD7 `c8d49c29`、规则修订 `a0ac852b`、分档器 `370e0297` 的验收，N1a `388b22c4` 与 N2-0 的结果（均待用户验收）；记录租约过期结算（方案 A）与用户 2026-10-09 的决定和预授权；§4.11 增加 M2 冻结条款与剩余清单；延期承诺表（V04-R1 整张、V07、V08、M2-F01B、M2-B1、文档采纳后移到 M3，承诺保留）；新增 M2-DEP-INT（N2-0 发现 M2 线缺发布线的 ADJ 与 IC02）；E 链拆分、V04-R1 拆分、D08 新增项、N 系列等 GPT 的处置不写入 M2，留 M3 规划；D08 不变；§4.7.1 新增 5 个任务行并回写 5 行状态；新增 §4.7.9；任务计数 150 → 155；其实施与验收以 Work `WORK-SYS001-M2-GOV-WBS8-001` 与其变更单为准。本次仅修订 WBS，不创建产品提交、不合并、不推送、不部署。 |
| V3.0.25 | 2026-10-09 | 最小版修订：写入 `M2-DEP-INT` 的最终提交证明（提交 `1d0be4af`，树 `644c5732`，20 个文件 SHA-256，判卷 SHA-256），回应 GPT 最终审计阻断项 B-01；状态写回：N1a、N2-0、最小 WBS 卡已由用户验收，`M2-DEP-INT` 已收口；新增 §4.7.10 与任务行 `M2-GOV-WBS9`；任务计数 155 → 156；冻结条款与延期承诺表不变；其实施与验收以 Work `WORK-SYS001-M2-GOV-WBS9-001` 与其变更单为准。本次仅修订 WBS，不创建产品提交、不合并、不推送、不部署。 |
| V3.0.26 | 2026-10-09 | 最小版修订：把卡 083 的用户验收（提交 `4b5c6307`）、技术性部署（卡 084 V1.1，release `1.3.3-4b5c630`，CHG-SCPT-2026-400）与推送（分支 `codex/m2-gov-wbs9-attest`）的结果写回当前投影；新增 §4.7.11 与任务行 `M2-GOV-WBS10`；任务计数 156 → 157；冻结条款与延期承诺表不变；不宣布 M2 里程碑验收；其实施与验收以 Work `WORK-SYS001-M2-GOV-WBS10-001` 与其变更单为准。本次仅修订 WBS，不创建产品提交、不合并、不推送、不部署。 |
| V3.0.27 | 2026-10-10 | 最小版修订：把发布治理整顿批次（卡 085～094）的状态写回当前投影，新增 §4.7.12（批次任务与状态、结果清单、历史队列 H02～H10 的只读核对、未决事项）与十个任务行（`M2-GOV-TD8`、`M2-RGOV-0`、`M2-GOV-CHGIMP`、`M2-GOV-TD9`、`M2-RGOV-1`、`M2-GOV-RANN`、`M2-GOV-RTOOL`、`M2-GOV-TRK`、`M2-GOV-GIGN`、`M2-GOV-WBS11`）；任务计数 157 → 167；`M2-GOV-WBS10` 行写回验收；冻结条款与延期承诺表不变；不宣布 M2 里程碑验收，不替用户验收任何变更单；其实施与验收以 Work `WORK-SYS001-M2-GOV-WBS11-001` 与其变更单为准。本次仅修订 WBS，不创建产品提交、不合并、不推送、不部署。 |
| V3.0.28 | 2026-10-11 | 最小版修订：写入用户 2026-10-11 宣布的 M2 里程碑验收与 M3 启动；新增 §4.7.13（第一日批次卡 099～103 的提交与变更单、Q01～Q03 的取证与状态、波次 4 瘦身的落字、带入 M3 的未决事项）与七个任务行（`M2-GOV-CHGSYNC`、`M2-GOV-MRG1`、`M2-GOV-Q01`、`M2-GOV-ERRA`、`M2-GOV-TD11`、`M2-GOV-WBS12`、`M2-GOV-TD12`，任务计数 167 → 174）；把卡 089～095 的状态单元格更新为变更单实际状态（均 completed）；D 阶段各行原文、D08、冻结条款与延期承诺表不变；不合并、不推送、不部署。 |
| V3.0.29 | 2026-10-11 | 最小版修订：登记第二批（卡 105～110）、推送 `620e7597` 与 CI 第 4 次运行 success、Q02 关闭与 Q03 结论（中止缺陷已修，残留登记 TD-SW008-122）、D01 与 M2-GOV-DOCS 完成；新增 §4.7.14 与五个任务行（`M2-GOV-CIBASE`、`M3-A1`、`M3-DOCS`、`M3-TD13`、`M3-WBS13`，任务计数 174 → 179）；更新投影 M3 行与 `M2-GOV-DOCS`、`M2-GOV-TD12`、`M2-GOV-WBS12` 的状态单元格；D 阶段各行原文、D08、冻结条款与延期承诺表不变；不合并、不再推送、不部署。 |
| V3.0.30 | 2026-10-11 | 最小版修订：登记卡 111（CI 基线再刷新）与 CI 第 5、6 次运行的实际结论及教训；新增用户批准的 `M3-RACE`、`M3-CF`、`M3-FIG` 与排队的 `M3-INV`、`M3-REPOGOV`、`M3-MAIN`（PLANNED / QUEUED / NOT_AUTHORIZED）；新增 §4.7.15（含外部审计简报的事实核对）与八个任务行（`M3-CIBASE2`、`M3-RACE`、`M3-CF`、`M3-FIG`、`M3-INV`、`M3-REPOGOV`、`M3-MAIN`、`M3-WBS14`，任务计数 179 → 187）；更新投影 M3 行与 `M3-WBS13` 的状态单元格；D 阶段各行原文、D08、冻结条款与延期承诺表不变；不合并、不再推送、不部署。 |
| V3.0.31 | 2026-10-12 | 最小版修订：登记卡 113（台账回写，TD-SW008-125、126、127）、2026-10-11 傍晚的仓库卫生清理存量结果（工作树 228 → 64、分支 206 → 55、归档引用 59 个）与 `M3-ROOT`、`M3-HYG` 两个任务行；新增 §4.7.16 与四个任务行（`M3-TD14`、`M3-ROOT`、`M3-HYG`、`M3-WBS15`，任务计数 187 → 191）；更新投影 M3 行与 `M3-WBS14` 的状态单元格；D 阶段各行原文、D08、冻结条款与延期承诺表不变；不合并、不再推送（推送另授权）、不部署。 |
| V3.0.32 | 2026-10-12 | 最小版修订：登记卡 115（`M3-RACE`，TD-SW008-120 待复核）、卡 116（`M2-B1` 已完成）、卡 117（台账回写）、控制根对齐（`M3-ROOT` 已执行，含执行中的三个问题与保留本地台账的教训）与卫生清理收尾（工作树 228 → 19、分支 206 → 19），更正 V3.0.31 里过时的清理数字；新增 §4.7.17 与两个任务行（`M3-TD15`、`M3-WBS16`，任务计数 191 → 193）；更新投影 M3 行与 `M2-B1`、`M3-RACE`、`M3-ROOT`、`M3-HYG`、`M3-WBS15` 的状态单元格；D 阶段各行原文、D08、冻结条款与延期承诺表不变；不合并、不推送（推送另授权）、不部署。 |
| V3.0.33 | 2026-10-12 | 最小版修订：登记当晚的卡 119（变更单补入库，产品档）、卡 120（V07 Python 模板验证）、卡 121（台账回写）与 V08 的勘测发现（TD-SW008-129、130、131）；V07 行改为部分完成并写明未做的部分（从基准提取、Linux CI 结果），V08 行追加勘测事实；新增 §4.7.18 与四个任务行（`M3-CS2`、`M3-V07`、`M3-TD16`、`M3-WBS17`，任务计数 193 → 197）；更新投影 M3 行与 `M3-WBS16` 的状态单元格；D 阶段各行原文、D08、冻结条款与延期承诺表不变；不合并、不部署。 |
| V3.0.34 | 2026-10-13 | 最小版修订：登记卡 123（V08 测试部分完成）、卡 124（PLC 模板修复）、卡 125（台账：TD-SW008-129 重新定性、登记 132 与 133）与 PLC 门禁实际依赖插件命令行的发现；记录用户的裁决（DJ-2026-005 有意保留作驾驶舱实测对象、变量文档缺失到交付阶段升失败、V07 “从基准提取”保留待办、卡 127 收口后允许推送）与今日计划；V07、V08 行追加事实；新增 §4.7.19 与四个任务行（`M3-TPL1`、`M3-TD17`、`M3-PLUGIN`、`M3-WBS18`，任务计数 197 → 201）；更新投影 M3 行与 `M3-WBS17` 的状态单元格；D 阶段各行原文、D08、冻结条款与延期承诺表不变；不合并、不部署。 |

当前产品状态（2026-09-29）：原 C09 业务 Run `SUCCEEDED`、租约 `RELEASED`，原 Work/Mission `CLOSED`，CHG-012 `completed`，双项目台账历史证据保留。原 Checkpoint 的 SW009 类型检查范围不足、原候选 strict 复验 Exit 1 的历史结论不改写；不可变候选 `8b02de55` 已完成完整技术复验和 G10-R1 治理闭环，故 M1 维持 `COMPLETED / ACCEPTED`。M0 历史完成保留、当前完整复验 `UNVERIFIED`。U01、U02、U03A、U03B、U04A、U04B 与 `M2-GOV-U04S01` 已独立验收，M2 为 `IN_PROGRESS`。H11 的 14 条历史目标 Work 已全部退出活动索引，5 条旧终态 lease 已围栏；当前开发运行时为 `1.3.3-0b72499`、无 fallback。下一治理任务为 `M2-GOV-BL02`，U05 以 BL02 为硬基线前置，开发运行时部署为软依赖。main 尚未合并，后续整改、集成、推送与 D 阶段正式发布仍是独立边界。

当前产品状态（2026-09-30，V3.0.17）：治理整改阶段 1～5 已完成并在隔离分支上形成不可变提交（未合并 main、未推送）；开发运行时已切换为 `1.3.3-a808fa8`，previous `1.3.3-0b72499`，无 fallback；阶段 2～5 的批准与验收为委托执行（`DELEGATED_ACCEPTED`）。`M2-GOV-WBS2` 处于 `VERIFYING / PENDING_ACCEPTANCE`，U05 待用户亲自验收本修订后启动。M1 维持 `COMPLETED / ACCEPTED`，M0 当前完整复验仍 `UNVERIFIED`，D 阶段正式稳定交付仍是独立边界。

当前产品状态（2026-09-30，V3.0.18）：整改阶段 6 `M2-GOV-WBS2` 已由用户亲自验收第一提交并 `COMPLETED / ACCEPTED`；整改闭环，U05 可从 BL02 统一基线 `7cfe227e` 启动。阶段 2～5 仍为 `DELEGATED_ACCEPTED`；未合并 main、未推送；开发运行时 `1.3.3-a808fa8` 不等同 D07 正式稳定交付。

当前产品状态（2026-10-01，V3.0.19）：U05、U06、U07A～U07D、U08 已验收闭环，各自在隔离分支上形成不可变提交（未合并 main、未推送）；开发运行时仍为 `1.3.3-a808fa8`，不含 U05～U08 代码。M2 为 `IN_PROGRESS`；下一项为 U09A（实施卡 037，待用户批准），随后 U09B、U09C 与 V01～V08。D 阶段正式稳定交付仍是独立边界。

当前产品状态（2026-10-03，V3.0.20）：U01～U09 已全部验收闭环；M2 代码线唯一尖端为 `3c32e8ad`（分支 `codex/m2-u09c-lifecycle-final`，未合并 main、未推送）；开发运行时仍为 `1.3.3-a808fa8`，不含 U05～U09C 代码。M2 为 `IN_PROGRESS`；下一项为 V01～V08，随后 M2 总审计与一次开发运行时部署。D 阶段正式稳定交付仍是独立边界。

当前产品状态（2026-10-03，V3.0.21）：U01～U09 与 V01 已验收闭环；M2 代码线唯一尖端为 `37a4faff`（分支 `codex/m2-v01-plc-quality-gate`，未合并 main、未推送）；开发运行时仍为 `1.3.3-a808fa8`，不含 U05～V01 代码。M2 为 `IN_PROGRESS`；下一项为 V01B（PLC 文档与代码一致性核对与自动补全），顺序 V01B → V01C → V01D → V02，随后 V03～V08、M2 总审计与一次开发运行时部署。D 阶段正式稳定交付仍是独立边界。

当前产品状态（2026-10-06，V3.0.22）：U01～U09、V01～V04、第 1 期及其审计缺陷修复、TD1、TD2 均已验收闭环；M2 代码线唯一尖端为 `1956dd9a`（分支 `codex/m2-td2-docs`，未合并 main、未推送）；开发运行时仍为 `1.3.3-a808fa8`，不含 U05～1956dd9a 的代码。M2 为 `IN_PROGRESS`；下一项为 M2-F01A（删除 PLC 工程标记后失败关闭），随后 V05-A、V05-B、V05-C，再 V04-R1、V06、V07/V08、V04-T、M2-F01B，最后做 M2 交叉总审计、WBS 终稿与一次开发运行时部署（须单独批准）。N1.4 的完整挂起目标属于 M3，M2 只交 UNSUPPORTED 的查询合同；D 阶段正式稳定交付仍是独立边界。

当前产品状态（2026-10-08，V3.0.23）：U01～U09、V01～V06、V05-A/B/B2/B3、V04-T、第 1 期及其审计缺陷修复、F01-a、TD1～TD6 均已验收闭环（含 F01-1）；M2 代码线唯一尖端为 `763395e4`（分支 `codex/m2-f011-closing-seal`，未合并 main、未推送）；开发运行时仍为 `1.3.3-a808fa8`，不含 U05～`763395e4` 的代码。M2 为 `IN_PROGRESS`；下一项为 F02，随后规则修订与分档器、V04-R1、V05-C（真实模型调用已获用户授权，卡仍须批准）、文档采纳与 WBS 终稿、B1、V07/V08/F01-b，最后做 GPT 对 M2 的最终审计、开发运行时技术性部署与一次推送（均须用户批准）。N1.4 的完整挂起目标属于 M3；D 阶段正式稳定交付仍是独立边界。

当前产品状态（2026-10-09，V3.0.24）：U01～U09、V01～V06、V05-A/B/B2/B3、V05-C、V04-T、第 1 期及其审计缺陷修复、F01-a、F01-1、F02、TD1～TD7、规则修订、分档器均已验收闭环；N1a 与 N2-0 已完成并等待用户验收；M2 代码线唯一尖端为 `388b22c43a334faf1e29d9bb0038150a403b17e3`（分支 `codex/m2-n1a-roles-doc`，未合并 main、未推送）；开发运行时仍为 `1.3.3-a808fa8`，不含 M2 代码，且与 M2 代码线分叉（缺 ADJ 与 IC02，见 §4.7.9）。M2 为 `IN_PROGRESS`，基线自本修订起冻结：剩余为最小 WBS 文档卡、`M2-DEP-INT`、审计包、GPT 最终审计、技术性部署与一次推送（部署在审计之后须用户再明确批准，推送须用户另行授权）；V04-R1、V07、V08、M2-F01B、M2-B1 与文档采纳在 M3。D 阶段正式稳定交付仍是独立边界。

当前产品状态（2026-10-09，V3.0.25）：M2 代码线唯一尖端为 `1d0be4af`（`M2-DEP-INT` 的合并提交，分支 `codex/m2-dep-int-adj-ic02`，未合并 main、未推送），发布源 `a808fa8a` 已是其祖先；开发运行时仍为 `1.3.3-a808fa8`，不含 M2 代码。N1a、N2-0、最小 WBS 卡已验收，整合卡已收口，最终提交证明见 §4.7.10。M2 为 `IN_PROGRESS`，基线冻结：剩余为 GPT 对 B-01 的只读复审、技术性部署（审计之后须用户再明确批准）与一次推送（须用户另行授权）；V04-R1、V07、V08、M2-F01B、M2-B1 与文档采纳在 M3。

当前产品状态（2026-10-09，V3.0.26）：M2 代码线唯一尖端为 `4b5c6307`（分支 `codex/m2-gov-wbs9-attest`，已推送到 origin，未合并 main）；开发运行时 active `1.3.3-4b5c630`、previous `1.3.3-a808fa8`，含 M2 代码。卡 083 已验收，技术性部署与推送均已完成（见 §4.7.11）。M2 已授权的工作项全部完成，里程碑验收由用户决定；基线冻结不变，V04-R1、V07、V08、M2-F01B、M2-B1 与文档采纳在 M3；5 个历史未终结 Work 原样保留；D 阶段正式稳定交付仍是独立边界。

当前产品状态（2026-10-10，V3.0.27）：M2 代码线唯一尖端为 `7506af72`（分支 `codex/m2-trk-check`，本地分支，未推送、未合并 main）；开发运行时 active `1.3.3-4b5c630`、previous `1.3.3-a808fa8`，不含本批次的新增测试工具。发布治理整顿批次（卡 085～094）已技术完成，卡 089、卡 090、卡 091、卡 092、卡 094、卡 093 的变更单等用户阅读后验收（见 §4.7.12）。M2 已授权的工作项全部完成，里程碑验收由用户决定；基线冻结不变，V04-R1、V07、V08、M2-F01B、M2-B1 与文档采纳在 M3；5 个历史未终结 Work 原样保留；D 阶段正式稳定交付仍是独立边界。

当前产品状态（2026-10-11，V3.0.28）：M2 里程碑已由用户宣布验收；M3 已启动。本地线性分支 `codex/m2-td11-sync` 的尖端为 `dbf7d031`（`0d22fdd0` 之上的卡 099～103，未推送、未合并 main）；已推送线尖端仍为 `0d22fdd0`（`origin/codex/m2-gov-wbs9-attest`）；开发运行时 active `1.3.3-4b5c630`、previous `1.3.3-a808fa8` 不变，不含本日批次的新增文件。Q01 已解、Q02 取证完成、Q03 仍开放；合并 main、推送、转私有、D07 切换与 release 切换仍是用户另行授权的独立边界。

当前产品状态（2026-10-11，V3.0.29）：M2 里程碑已验收；M3 进行中。已推送线尖端为 `620e7597`（`origin/codex/m2-gov-wbs9-attest`，CI 第 4 次运行 success）；其上本地线 卡 107 `eca0fab8` → 卡 108 `a6d5d8f3` → 卡 109 `31bed234` → 卡 110（本记录）未推送、未合并 main。开发运行时 active `1.3.3-4b5c630`、previous `1.3.3-a808fa8` 不变。Q01、Q02 已关闭，Q03 的中止缺陷已修（`mypy .` 残留见 TD-SW008-122）；D01、M2-GOV-DOCS 完成；合并 main、再次推送、转私有、D07 切换与 release 切换仍是用户另行授权的独立边界。

当前产品状态（2026-10-11，V3.0.30）：M2 里程碑已验收；M3 进行中。已推送线尖端为 `07709559`（`origin/codex/m2-gov-wbs9-attest`，CI 第 6 次运行 success；第 5 次因基线过期失败，已由卡 111 修复），本地没有未推送的提交，卡 112（本记录）在其上。开发运行时 active `1.3.3-4b5c630`、previous `1.3.3-a808fa8` 不变。下一批：`M3-RACE`（核心档）→ `M2-B1`；仓库治理项已排队未授权；合并 main、再次推送、转私有、D07 切换与 release 切换仍是用户另行授权的独立边界。

当前产品状态（2026-10-12，V3.0.31）：M2 里程碑已验收；M3 进行中。已推送线尖端 `07709559`（CI 第 6 次 success）；其上本地提交 卡 112 `5cd57f8b` → 卡 113 `3ac045f1` → 卡 114（本记录），待用户已授权的一次快进推送。仓库卫生清理的存量部分已做（工作树 64、分支 55）；控制根仍停在旧分支，对齐方案已出待确认。开发运行时 active `1.3.3-4b5c630`、previous `1.3.3-a808fa8` 不变。合并 main、转私有、D07 切换与 release 切换仍是用户另行授权的独立边界。

当前产品状态（2026-10-12，V3.0.32）：M2 里程碑已验收；M3 进行中。已推送线尖端 `ba0ef3e9`（CI 第 7 次 success）；其上本地未推送：卡 115 `ef3c13af`（M3-RACE）→ 卡 116 `c54accd4`（M2-B1）→ 卡 117 `37a4a6a5`（台账回写）→ 卡 118（本记录）。控制根已对齐集成线（`codex/control-root-20261012`）；工作树 19、分支 19。开发运行时 active `1.3.3-4b5c630`、previous `1.3.3-a808fa8` 不变。合并 main、转私有、D07 切换与 release 切换仍是用户另行授权的独立边界。

当前产品状态（2026-10-12 夜，V3.0.33）：M2 里程碑已验收；M3 进行中。已推送线尖端 `098e2bf6`（CI 第 8 次 success）；其上本地：卡 120 `7e926f4f`（V07）→ 卡 119 `4f855e04`（变更单补入库）→ 卡 121 `c1b08fc1`（台账回写）→ 卡 122（本记录）；推送与 CI 结果以其后的记录为准。V07 部分完成，V08 卡待出（勘测发现登记为 TD-SW008-129～131，129 需用户裁决）。开发运行时 active `1.3.3-4b5c630`、previous `1.3.3-a808fa8` 不变。合并 main、转私有、D07 切换与 release 切换仍是用户另行授权的独立边界。

当前产品状态（2026-10-13，V3.0.34）：M2 里程碑已验收；M3 进行中。已推送线尖端 `dcfca387`（CI 第 9 次 success）；其上本地：卡 124 `b5d3e552`（PLC 模板修复）→ 卡 125 `d6d382ff`（台账）→ 卡 126（本记录）；下一张是卡 127（`M3-PLUGIN`，把插件命令行接入驾驶舱门禁），收口后用户已允许推送。DJ-2026-005 有意保留（TD-SW008-132）。开发运行时 active `1.3.3-4b5c630`、previous `1.3.3-a808fa8` 不变。合并 main、转私有、D07 切换与 release 切换仍是用户另行授权的独立边界。
