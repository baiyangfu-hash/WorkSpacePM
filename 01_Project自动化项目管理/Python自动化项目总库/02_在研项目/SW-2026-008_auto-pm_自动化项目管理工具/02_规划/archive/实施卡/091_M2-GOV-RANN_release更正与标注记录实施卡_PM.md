# M2-GOV-RANN｜release 更正与标注记录实施卡

> 卡片编号：`CARD-SW008-M2-RANN`
> 版本：`V1.0`（2026-10-10；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-10 预授权当日排期，原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾；条件见 §7）
> 档次：文档档（一个新增记录文件；不改 manifest、指针与载荷）
> 隔离基线：`6e2508425a1efcd13f643a9eed7d85a9faf40748`（卡 089 的提交，本地分支 `codex/m2-td9-docs`；卡 090 的 15 个本地 tag 已存在）
> 路径根：`.`
> 治理任务基线：WBS V3.0.26；台账 TD-SW008-109、110（本卡的验收条件来自这两条）
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-10）

1. **为什么**：盘点卡 087 查实：15 个 release 里 5 个 exact-tree 校验不通过，但名单上没有任何标注；`1.2.4-6699a5b` 的源码提交在 manifest 与该载荷自己的 `release_meta.json` 里都写错（对象不存在），另有两处只写了短 SHA。启动器的自动回退只看 active 与 previous 两个指针，所以目前没有实际风险，但依赖的是隐含约定，而不是明文规则。
2. **怎么改**：不改旧字节（错误值同时在载荷里，改了会破坏它的校验记录）。**新增一个记录文件** `00_Infrastructure/auto_pm/release_annotations.json`：登记每个 release 的状态、是否可作回退目标、源码提交（全 SHA）、对应的本地 tag（卡 090）、从源码重建的对比结果，并以 `corrections` 记录更正；另写四条明文规则。
3. **状态表**（冻结在记录文件里）：

| release | 状态 | 可作回退目标 | exact-tree | 从源码重建 | 更正 |
|---|---|---|---|---|---|
| `1.2.3-813105c` | archive_unverified | 否 | 不通过 | different | — |
| `1.2.3-d41eb38` | archive_unverified | 否 | 不通过 | identical | — |
| `1.2.3-f950525` | archive_unverified | 否 | 不通过 | identical | — |
| `1.2.4-6699a5b` | archive_unverified | 否 | 不通过 | n/a | source_commit 更正 |
| `1.3.0-5345f40` | verified_historical | 否 | 通过 | identical | — |
| `1.3.1-a7dae04` | verified_historical | 否 | 通过 | identical | — |
| `1.3.2-9d3c920` | verified_historical | 否 | 通过 | identical | source_commit 更正 |
| `1.3.3-0b72499` | verified_historical | 否 | 通过 | identical | — |
| `1.3.3-4b5c630` | active | 否 | 通过 | identical | — |
| `1.3.3-8b02de5` | verified_historical | 否 | 通过 | identical | — |
| `1.3.3-8f08c1a` | verified_historical | 否 | 通过 | identical | — |
| `1.3.3-a808fa8` | previous | 是 | 通过 | identical | — |
| `1.3.3-d8f7c8b` | archive_unverified | 否 | 不通过 | different | source_commit 更正 |
| `1.3.3-e648e0b` | verified_historical | 否 | 通过 | identical | — |
| `1.3.3-f462694` | verified_historical | 否 | 通过 | identical | — |

4. **不做什么**：不改 `deployment_manifest.json`、`active_release.json`、`previous_release.json` 与 `releases/` 下任何字节；不让回退/切换脚本读取本文件（那是后续的工具改动，不在今天）；不推送、不打 tag、不删除任何旧 release。
5. **检查**：独立检查器重新取事实：release 集合等于当前 manifest；每个源码提交存在、与登记值一致（更正项与短 SHA 项另验）、对应的本地 tag 指向它；每个 release 的 exact-tree 结果重新用发布脚本核验；active 与 previous 状态等于当前两个指针；只有 previous 且校验通过者可标为回退目标；字节等于冻结值；8 个反例（rollback_on_failed_release、release_missing、unlisted_release、wrong_commit、tag_mismatch、active_mismatch、status_exact_tree_disagrees、byte_drift）各被对应断言拒绝。**它不证明状态划分符合你的意图**，这由你验收。
6. 我在隔离演练树上完整跑了一遍（非受治理执行，不能复用为正式门禁）：基线、安装、候选三步原始退出码均 0；G1–G9 全部 PASS；8 项反例全部被拒绝；`gate_verdict` SHA-256 `87119ae063bfc2f58d774ed8fcad20e34d840a673e869775d940ac99a172a9d2`，`DONE` SHA-256 `51889fc09d82a783f6741ce03c6a8086247270dbe4207ddc20720e0f42f2762a`；证据目录 `.auto-pm/reports/m2-rann/gates_rehearsal/`。

## 2. 单一目标与完成定义

把记录文件提交到本地分支。技术完成 = 提交通过全部门禁、提交字节等于冻结清单；**验收 = 用户阅读记录文件后确认**，变更单收口不委托。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线、新增文件在基线里不存在、冻结副本字节等于配置、工具字节等于冻结清单、卡 089 的 Run/Work 已达技术终态。启动脚本有只读的 `--check-only`，预检只用它。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **续租**：先用绝对路径启动续租循环并确认日志里有 `first renewal ok`。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `00_Infrastructure/auto_pm/release_annotations.json` | 计划新增 | 新增：release 状态、回退资格、源码提交与 tag、更正记录 |

出现第二条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-rann/`、本卡文件、演练工作树）不是额外 owned paths。

## 5. 字节合同

1. 冻结文件清单（路径与 SHA-256）在 `.auto-pm/reports/m2-rann/files_manifest.json`，SHA-256 为 `42022b7f95ea9c53ac491aa2170eab41bc3023bb9b9bb9b34abe93de4b4ae41f`；文件字节的冻结副本在 `.auto-pm/reports/m2-rann/proto/` 下同一相对路径，由 `prepare_rann.py` 从盘点输出、manifest、指针与本地 tag 确定性生成。变更集恰为这一个新增文件。
2. 工具与配置的 manifest 已冻结，SHA-256 为 `ea242b6ef5279126a9a5a21fadbc47f7fba3f08ea647576b3500416a47d0cb8f`；实际运行由启动脚本逐文件核对。共享判卷器 SHA-256 为 `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188`。
3. 提交：只含冻结文件；父提交为基线；经正常钩子，绝不绕过；提交 blob 与 git 对冻结字节算出的 blob id 相同。
4. Checkpoint 在提交之前创建，证据里写明冻结清单的路径与 SHA-256。

冻结工具（`.auto-pm/reports/m2-rann/`；运行器、安装器沿用卡 088 已验收代码，仅改名；检查器的判断部分为本卡新写）：

| 工具 | SHA-256 |
|---|---|
| `rann_runner.py` | `ee4e5c02e21292c5815388f0f2689670c4328b4371055f22432f9a6a45f9082d` |
| `rann_check.py` | `a6af743bd1e41ecd6d5df6400e46376e3d8b5248a8aee241af06fe29456f551e` |
| `install_candidate.py` | `d0f510bfff6af1240fb523ca514be79bf5c64a9a1dcf2ccda927602236479a9f` |
| `prepare_rann.py` | `ddc48d187914e69bc6462992c26757f8b8f732777b5cdf9ad7322e47c7886353` |
| `rann_config.json` | `d60e62c663c2ec1920f7625c23cd47978128161ece59f2dd7b29af0326bb60ff` |
| `files_manifest.json` | `42022b7f95ea9c53ac491aa2170eab41bc3023bb9b9bb9b34abe93de4b4ae41f` |

## 6. 门禁矩阵

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份、工作树与初始 hook | HEAD 为基线、clean；新增文件不存在；真实 hook 指纹非空 |
| G2 | 基线文档检查 | 根入口 `main.py doc check` 显式传控制根与候选根，原始 exit 0 |
| G3 | 安装前治理台账 | `ledger reconcile` 对 SW-2026-008 与 SYS-2026-001 无 fix，exit 0 且 0/0/0 |
| G4 | 最终候选文档检查 | 同根入口，原始 exit 0；受检前后字节均等于冻结值 |
| G5 | 安装后治理台账 | 同只读对账，两个项目均 exit 0 且 0/0/0 |
| G6 | 记录语义 | §1.5 全部成立（含 15 个 release 的校验重新核验） |
| G7 | 真实 hook 保全 | 运行前后全部真实 hook 字节相同 |
| G8 | 轻量负向对照（8 项） | rollback_on_failed_release、release_missing、unlisted_release、wrong_commit、tag_mismatch、active_mismatch、status_exact_tree_disagrees、byte_drift，各由对应断言拒绝 |
| G9 | 最终范围与字节 | 实测变更恰为冻结文件、HEAD 仍基线、index 空；完整改动清单及前后 SHA 绑定 |

判卷另由冻结的 `m2-tools/verdict_check.py` 核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-10 预授权当日排期（原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾）：卡 SHA 先在汇报里报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读记录文件后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 创建独立 SW-2026-008 DOCU/OPT 变更单、匹配 Decision（`DEC-<当天>-RANNRECD`）、Work `WORK-SW008-M2-RANN-001`、Run `RUN-SW008-M2-RANN-001`（租约不超过 3600 秒）。
2. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-rann`，分支 `codex/m2-rann-notes`。
3. 安装冻结字节并完整重跑门禁（`rann_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob id。
4. 依法推进 Run/Work 技术终态，对账 0/0/0；**变更单停在“实施中”，等用户阅读后验收再收口。**

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease 或 hook 漂移；新增范围；任何门禁失败；负向目标未命中；Checkpoint 不能绑定清单哈希；提交 Hook 拒绝；需要改清单之外的任何文件：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结工具、文件清单与冻结副本；演练原始门禁（非治理）；正式门禁、CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；用户阅读验收的记录。

## 11. 限制与后续

本卡只新增记录，不修改 manifest、指针与载荷，也不让任何脚本读取它：让回退/切换脚本强制遵守这些规则是后续的工具改动（TD-SW008-109 验收条件的第二半），不在本卡。提交在本地分支 `codex/m2-rann-notes`，**不推送、不合并**。
