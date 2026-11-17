# M2-GOV-GIGN｜.gitignore 补洞实施卡

> 卡片编号：`CARD-SW008-M2-GIGN`
> 版本：`V1.0`（2026-10-10；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-10 预授权当日排期，原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾；条件见 §7）
> 档次：文档档（修改 1 个配置文件，只在末尾追加；不改任何产品与测试）
> 隔离基线：`11a829c14cc69d9ed419355e753e6523e21799b7`（卡 092 的提交，本地分支 `codex/m2-rtool-lock`）
> 路径根：`.`
> 治理任务基线：WBS V3.0.26；台账 TD-SW008-115（本卡的验收条件之一）
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-10）

1. **为什么**：用户问“过滤条件为什么没有生效”。查实原因之一：当前 `.gitignore` 没有 `*.zip`、`*.bak`、`*.7z` 规则，所以 60 MB 的 zip、35 MB 的 HMI 备份包没有任何拦截（另两个原因：规则晚于文件；忽略规则不处理已入库的文件与历史，见台账 TD-SW008-115）。
2. **做什么**：在 `.gitignore` 末尾追加一段：一行带日期与台账编号的注释，加 8 条规则：`*.zip`、`*.7z`、`*.rar`、`*.tar`、`*.tgz`、`*.tar.gz`、`*.bak`、`*.hmiproj.bak`。不改任何已有行，不移出任何已跟踪文件。
3. **效果与边界**：规则只拦**以后的新文件**；已入库的 zip/bak 仍在版本库里，历史不变（要不要把它们移出跟踪，是你另行裁决的事，不在本卡）。检查器用 git 自己的 `check-ignore` 验证：6 个样例路径（压缩包与备份包）会被忽略，7 个样例路径（源码、测试、文档、QML、SCL、配置、模板）不会被忽略。
4. **检查**：独立检查器核对：候选文件以基线文件为前缀（旧内容一字不改），追加的恰为冻结的注释与规则、顺序一致；用 git 在一次性仓库里实测样例路径；字节等于冻结值；6 个反例（old_line_changed、extra_rule、source_ignored、rule_missing、byte_drift、crlf）各被对应断言拒绝。
5. 我在隔离演练树上完整跑了一遍（非受治理执行，不能复用为正式门禁）：基线、安装、候选三步原始退出码均 0；G1–G9 全部 PASS；6 项反例全部被拒绝；`gate_verdict` SHA-256 `4ed5bb55e3a0f93fd335f3f23b087911c09d302335f2c91f098118b857fbae20`，`DONE` SHA-256 `9a4db70b41bcff64a48db60cefac48b2cb27375d56d32abdf06c4b6ee197f32c`；证据目录 `.auto-pm/reports/m2-gign/gates_rehearsal/`。
6. 不在本卡范围：把已入库的 zip/bak/exe/db 等 996 个命中规则的文件移出跟踪；推送、打 tag、改历史；任何产品、测试、规则文档、台账改动。

## 2. 单一目标与完成定义

把追加规则提交到本地分支。技术完成 = 提交通过全部门禁、提交字节等于冻结清单；**验收 = 用户阅读追加的规则后确认**，变更单收口不委托。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线、基线 blob 等于冻结的基线哈希、冻结副本字节等于配置、工具字节等于冻结清单、卡 092 的 Run/Work 已达技术终态。启动脚本有只读的 `--check-only`，预检只用它。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **续租**：先用绝对路径启动续租循环并确认日志里有 `first renewal ok`。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `.gitignore` | 存在 | 修改：只在末尾追加一段规则（一行注释与 8 条规则） |

出现第二条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-gign/`、本卡文件、演练工作树）不是额外 owned paths。

## 5. 字节合同

1. 冻结文件清单（路径与 SHA-256）在 `.auto-pm/reports/m2-gign/files_manifest.json`，SHA-256 为 `96a31bbafdc53a2ce4fdcbc15026e6f35c282a9e3b75b0568805c3685163e308`；基线 `.gitignore` 的 SHA-256 为 `56ff2195834cce290c69882e1977d02f48fd9d749b73ffa5528e4fc71f3fd016`，最终 SHA-256 为 `c91f63361ac77fc6a3c8b8ebd5a07b0c05a38cac2fdeafc63abdc13ba646e459`；冻结副本在 `.auto-pm/reports/m2-gign/proto/.gitignore`。变更集恰为这一个修改文件。
2. 工具与配置的 manifest 已冻结，SHA-256 为 `d65935872b3ca19e7de53ae03e41f07861f271421065b180e6eb10ddef6f0135`；实际运行由启动脚本逐文件核对。共享判卷器 SHA-256 为 `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188`。
3. 提交：只含冻结文件；父提交为基线；经正常钩子，绝不绕过；提交 blob 与 git 对冻结字节算出的 blob id 相同。
4. Checkpoint 在提交之前创建，证据里写明冻结清单的路径与 SHA-256。

冻结工具（`.auto-pm/reports/m2-gign/`；运行器、安装器沿用卡 091 的已验收代码，仅改名；检查器的判断部分为本卡新写）：

| 工具 | SHA-256 |
|---|---|
| `gign_runner.py` | `ede31c6d366f868438a6095d124f34997bc91bcd1a75ca5f3f904742bdc4be28` |
| `gign_check.py` | `b7b5a332f4a823d34af89db5dfa48877c2270daf21b97e4c0ce8851c9c16641d` |
| `install_candidate.py` | `ffe5ccacdefc8633609bfacac2976ec1c720575d94bd4cbebc55c464e72e84b1` |
| `prepare_gign.py` | `39db87392d3364e64c3572137aecf306e0dd4589a43084c92821c3b828af211d` |
| `gign_config.json` | `c554de9c661b07db305b76c4983e761f1d9522f7997707c943276e56280b23ec` |
| `files_manifest.json` | `96a31bbafdc53a2ce4fdcbc15026e6f35c282a9e3b75b0568805c3685163e308` |
| `base_gitignore.txt` | `56ff2195834cce290c69882e1977d02f48fd9d749b73ffa5528e4fc71f3fd016` |

## 6. 门禁矩阵

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份、工作树与初始 hook | HEAD 为基线、clean；基线 `.gitignore` 字节等于冻结值；真实 hook 指纹非空 |
| G2 | 基线文档检查 | 根入口 `main.py doc check` 显式传控制根与候选根，原始 exit 0 |
| G3 | 安装前治理台账 | `ledger reconcile` 对 SW-2026-008 与 SYS-2026-001 无 fix，exit 0 且 0/0/0 |
| G4 | 最终候选文档检查 | 同根入口，原始 exit 0；受检前后字节均等于冻结值 |
| G5 | 安装后治理台账 | 同只读对账，两个项目均 exit 0 且 0/0/0 |
| G6 | 规则语义 | §1.4 全部成立（含 git 实测的样例路径） |
| G7 | 真实 hook 保全 | 运行前后全部真实 hook 字节相同 |
| G8 | 轻量负向对照（6 项） | old_line_changed、extra_rule、source_ignored、rule_missing、byte_drift、crlf，各由对应断言拒绝 |
| G9 | 最终范围与字节 | 实测变更恰为冻结文件、HEAD 仍基线、index 空；完整改动清单及前后 SHA 绑定 |

判卷另由冻结的 `m2-tools/verdict_check.py` 核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-10 预授权当日排期（原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾）：卡 SHA 先在汇报里报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读追加的规则后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 创建独立 SW-2026-008 DOCU/OPT 变更单、匹配 Decision（`DEC-<当天>-GIGNRULE`）、Work `WORK-SW008-M2-GIGN-001`、Run `RUN-SW008-M2-GIGN-001`（租约不超过 3600 秒）。
2. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-gign`，分支 `codex/m2-gign-rules`。
3. 安装冻结字节并完整重跑门禁（`gign_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob id。
4. 依法推进 Run/Work 技术终态，对账 0/0/0；**变更单停在“实施中”，等用户阅读后验收再收口。**

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease 或 hook 漂移；新增范围；任何门禁失败；负向目标未命中；Checkpoint 不能绑定清单哈希；提交 Hook 拒绝；需要改清单之外的任何文件或移出任何已跟踪文件：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结工具、文件清单与冻结副本；演练原始门禁（非治理）；正式门禁、CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；用户阅读验收的记录。

## 11. 限制与后续

规则只拦新文件；已入库的 996 个命中规则的文件仍在版本库与历史里（台账 TD-SW008-115 的验收条件另有两项：推送前的自动扫描门禁、你对已入库文件的分类裁决）。提交在本地分支 `codex/m2-gign-rules`，**不推送、不合并**。
