# M2-GOV-PLCCHG｜PLC 变更单入库实施卡

> 卡片编号：`CARD-SW008-M2-PLCCHG`
> 版本：`V1.0`（2026-10-10；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PENDING_USER_APPROVAL`（用户 2026-10-10 在对话中选择方案 B“先单独立卡把 CHG-PLC-2026-014 入库，再推”；本卡 SHA 报给用户之后，须用户在聊天中回复批准才启动；条件见 §7）
> 档次：文档档（新增 1 个变更单文件，不改任何产品、测试、规则文档、台账、PLC 工程文件）
> 隔离基线：`8cb8dceb86e957ce6096c4ace39a0e988144d38d`（卡 094 的提交，本地分支 `codex/m2-gign-rules`）
> 路径根：`.`
> 治理任务基线：WBS V3.0.25（引用了本变更单）；云端推送任务的检查 5
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-10）

1. **为什么**：把 M2 收口与 CHG 入库提交推到远端之前，有一项检查要求 WBS 引用的 75 个变更单编号在推送树里都有文件。实测 74 个有，**只缺 `CHG-PLC-2026-014`**。它是 PLC 项目 DJ-2026-005 的变更单（卡 046、V01C：基准项目的接口与变量文档治愈），状态 completed，WBS 引用了它，但它从未进入任何提交（卡 088 的入库范围按用户当时的裁决不含 PLC 项目）。用户选择方案 B：单独立卡把它入库，再推送。
2. **做什么**：新增 1 个文件 `0100_PLC自动化/DJ-2026-005/11_监控/01_变更管理/01_变更单/CHG-PLC/CHG-PLC-2026-014.md`，字节与工作区现有文件完全相同（11429 字节，SHA-256 见 §5），不做任何修改。
3. **内容核对**：我读过全文：它是标准的变更单模板，记录编号、项目号 DJ-2026-005、技术领域 PLC、业务性质 OPT、模块级、变更状态 completed、变更背景引用卡 046 V1.0 与其 SHA-256；没有客户名称、网络地址、账号口令或密钥；§5～§8 仍是模板占位（与同批已入库的同类变更单一致）。检查器另有密钥模式扫描。
4. **不做什么**：不入库项目 DJ-2026-005 的变更台账与同项目其他变更单，不入库 DJ-2026-008 的变更单，不改任何 PLC 工程文件；不推送（推送是用户已批准的另一步，在本卡验收之后按云端任务的检查逐项重跑再执行）。
5. **检查**：独立检查器核对：变更集恰为这 1 个新增文件、字节等于冻结值、UTF-8、无密钥与带口令的 URL、路径匹配 PLC 变更单的目录与命名、文件里含自己的编号、该路径在基线提交里不存在、基线提交的 WBS 引用了该编号；9 个反例（extra_file、missing_file、byte_drift、secret_injected、wrong_kind、already_tracked、id_not_in_file、not_referenced、crlf_flip）各被对应断言拒绝。
6. 我在隔离演练树上完整跑了一遍（非受治理执行，不能复用为正式门禁）：基线、安装、候选三步原始退出码均 0；G1–G9 全部 PASS；9 项反例全部被拒绝；`gate_verdict` SHA-256 `4adce2f25cddf2d845b5d68ff19107b33f9d324656a5dcc450d740daf1946b3e`，`DONE` SHA-256 `83974daeae3e45c6a56cb1b0925d8daa6522f9642038681fe5074c63ae0cc5f4`；证据目录 `.auto-pm/reports/m2-plcchg/gates_rehearsal/`。
7. **提交分支的取舍**：本卡以 `8cb8dceb` 为基线、建独立本地分支 `codex/m2-plcchg-import`。已完成的卡 093（`7506af72`）与卡 095（`657f3dc5`）也以 `8cb8dceb` 为父，它们的变更单未验收，不进入本次推送；之后需要时再用一个合并提交把两条线合在一起（本地操作）。

## 2. 单一目标与完成定义

把 `CHG-PLC-2026-014` 按字节入库到本地分支。技术完成 = 提交通过全部门禁、提交字节等于冻结清单；**验收 = 用户阅读后确认**，变更单收口不委托。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线、冻结文件字节、工具字节等于冻结清单、卡 094 的 Run/Work 已达技术终态。启动脚本有只读的 `--check-only`，预检只用它。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **续租**：先用绝对路径启动续租循环并确认日志里有 `first renewal ok`。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `0100_PLC自动化/DJ-2026-005/11_监控/01_变更管理/01_变更单/CHG-PLC/CHG-PLC-2026-014.md` | 计划新增 | 新增：PLC 项目 DJ-2026-005 的已完成变更单，按字节入库 |

出现第二条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-plcchg/`、本卡文件、演练工作树）不是额外 owned paths。

## 5. 字节合同

1. 冻结文件清单（路径与 SHA-256）在 `.auto-pm/reports/m2-plcchg/files_manifest.json`，SHA-256 为 `c3da3113928af0cb0ed6fa6d9423888f22a2d175d7387bfd8362bce8c10cb9cf`；该文件最终 SHA-256 为 `c3d98b0ba64d0aa2c4ddfb6e815591b338056f12d494f4be750a6f2798fbca17`；冻结副本在 `.auto-pm/reports/m2-plcchg/proto/`。变更集恰为这一个新增文件。
2. 工具与配置的 manifest 已冻结，SHA-256 为 `0ff4e10be3b934d4f3c44d2910bc071aa0e597aea5745b160d82009820bd3a67`；实际运行由启动脚本逐文件核对。共享判卷器 SHA-256 为 `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188`。
3. 提交：只含冻结文件；父提交为基线；经正常钩子，绝不绕过；提交 blob 与 git 对冻结字节算出的 blob id 相同（git 在入库时归一换行，按 blob id 比较）。
4. Checkpoint 在提交之前创建，证据里写明冻结清单的路径与 SHA-256。

冻结工具（`.auto-pm/reports/m2-plcchg/`；运行器、安装器沿用卡 091 的已验收代码，仅改名；检查器的判断部分为本卡新写）：

| 工具 | SHA-256 |
|---|---|
| `plcchg_runner.py` | `e31b784bd089b1243971893ef23dd23dada216557c6eb7dd1c691b13e2925e6e` |
| `plcchg_check.py` | `c30d89b04f503c9fdf3c7b5347cdafeb8bd7de93006f48fb647db24d0742d414` |
| `install_candidate.py` | `8f8c38ce181e0876655a3a5cb446c23f107dc6e042e4fdab2661d119d7c37947` |
| `prepare_plcchg.py` | `ecbe85dee9c46aeacdac3139f203158cea97bc05441effb9a570d30b2d40df72` |
| `plcchg_config.json` | `f8256470a70294dddcdee9b6973775f11941b299b1c330400bc4754ee681d91d` |
| `files_manifest.json` | `c3da3113928af0cb0ed6fa6d9423888f22a2d175d7387bfd8362bce8c10cb9cf` |
| `commit_msg.template.txt` | `c397db2b170d7a87e61776854a75510f18246d557e73167c980490fb96636826` |

## 6. 门禁矩阵

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份、工作树与初始 hook | HEAD 为基线、clean；冻结文件在基线不存在；真实 hook 指纹非空 |
| G2 | 基线文档检查 | 根入口 `main.py doc check` 显式传控制根与候选根，原始 exit 0 |
| G3 | 安装前治理台账 | `ledger reconcile` 对 SW-2026-008 与 SYS-2026-001 无 fix，exit 0 且 0/0/0 |
| G4 | 最终候选文档检查 | 同根入口，原始 exit 0；受检前后字节均等于冻结值 |
| G5 | 安装后治理台账 | 同只读对账，两个项目均 exit 0 且 0/0/0 |
| G6 | 文件语义 | §1.5 全部成立 |
| G7 | 真实 hook 保全 | 运行前后全部真实 hook 字节相同 |
| G8 | 轻量负向对照（9 项） | extra_file、missing_file、byte_drift、secret_injected、wrong_kind、already_tracked、id_not_in_file、not_referenced、crlf_flip，各由对应断言拒绝 |
| G9 | 最终范围与字节 | 实测变更恰为冻结文件、HEAD 仍基线、index 空；完整改动清单及前后 SHA 绑定 |

判卷另由冻结的 `m2-tools/verdict_check.py` 核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-10 选择方案 B；**本卡 SHA 报给用户后，由用户在聊天中回复批准才启动**。批准条件：卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与摘要，等用户批准。
2. 创建独立 SW-2026-008 DOCU/OPT 变更单、匹配 Decision（`DEC-<当天>-PLCCHGIM`）、Work `WORK-SW008-M2-PLCCHG-001`、Run `RUN-SW008-M2-PLCCHG-001`（租约不超过 3600 秒）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-plcchg`，分支 `codex/m2-plcchg-import`。
4. 安装冻结字节并完整重跑门禁（`plcchg_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob id。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；**变更单停在“实施中”，等用户阅读后验收再收口。**

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease 或 hook 漂移；新增范围；任何门禁失败；负向目标未命中；Checkpoint 不能绑定清单哈希；提交 Hook 拒绝；需要改清单之外的任何文件：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结工具、文件清单与冻结副本；演练原始门禁（非治理）；正式门禁、CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；用户阅读验收的记录。

## 11. 限制与后续

提交在本地分支 `codex/m2-plcchg-import`，**不推送、不合并**；推送按云端任务的范围与检查另行执行（快进、不 force、不推 main 与 tag）。DJ-2026-005 的变更台账与其余 PLC 变更单是否入库，等用户裁决。
