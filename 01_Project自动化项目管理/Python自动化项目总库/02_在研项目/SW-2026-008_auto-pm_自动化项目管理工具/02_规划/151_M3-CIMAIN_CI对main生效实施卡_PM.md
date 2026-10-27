# M3-CIMAIN｜CI 对 main 与 PR 生效实施卡（一个文件）

> 卡片编号：`CARD-SW008-M3-CIMAIN`
> 版本：`V1.0`（2026-10-16；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-16 说“你的其他建议全部批准”“允许夜里推”“允许夜里执行”“今天晚上继续作业”；项目 Claude 的评审已采纳；本卡 SHA 先在聊天报出再启动；条件见 §7）
> 档次：**核心档**（分档器：`.github/` 不在已知规则内，按“未知路径按核心档复核”；不得降级）
> 依赖：上一张卡（M3-HYGIN1）的 Run/Work 已达技术终态且其变更单已收口（由启动脚本核验）
> 隔离基线：`e0d452d4c4378022247c40c9ab4960b7727769be`（上一张卡的提交，本地分支 `codex/m3-hygin1-records`）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-16 夜）

1. **为什么**：`origin/main` 在 `e83c117d`（活跃分支的祖先，差 140 多个提交，可快进）。现状：工作流 `.github/workflows/sw008-ci.yml` 的 push 触发写着 `branches-ignore: [main]`，没有 `pull_request` 触发——合并到 main 之后没有 CI，将来云端与项目 Claude 的 PR 也不会跑 CI。用户 2026-10-16 批准 M3-CIMAIN 与 M3-MAIN；项目 Claude 的云端只读评审（`reviews/01_cimain_workflow.md`）指出照原计划实施会出 4 个问题，我核对后全部采纳：（A）普通分支的推送若也改用 `before`，被并发取消的那次推送里的提交永远不会被扫描；（B）`before` 不存在时 `git log` 直接抛 Python 栈，红灯却不知原因；（C）main 上 `cancel-in-progress: true`，连续两次推送 main，前一个提交永远没有结论，而 M3-MAIN 的条件恰是“CI 通过的提交”；（D）`${{ }}` 直接拼进脚本有注入面，事件字段应走 `env:`。
2. **做什么**（一个文件；全部事实在构建时读自 git 并断言）：
   - `push` 去掉 `branches-ignore: [main]`，保留 `paths` 过滤；新增对 main 的 `pull_request` 触发（同一组 `paths`）；
   - 并发组 `sw008-ci-${{ github.ref }}` 保留，`cancel-in-progress` 改为 `${{ github.ref != 'refs/heads/main' }}`（main 不取消）；
   - 秘密扫描一步：基线按事件取——推送到 main 用 `before`，pull request 用 `pull_request.base.sha`，其余推送与手动运行保持 `origin/main` 全段；基线为空、全零或不在检出里则**拒绝扫描并明确失败**（`::error::` 一行，退出 1）；事件字段走 `env:`；
   - 其余步骤、`permissions`、`env` 一字不改。
3. **不做什么**：不改检查步骤、测试基线、密钥与 `permissions`；不改分支保护与任何 GitHub 账户设置（M3-COLLAB 的子项，你决定后再做）；不改 `secret_scan.py` 与其他测试工具；不碰 main；不推送由本卡完成（夜间推送由我收口后按用户允许另行完成并读 CI）。
4. **为什么是核心档**：分档器不认识这个路径，按“未知路径按核心档复核”的规则声明为核心档，跑九组回归并要求与上一张卡的受治理输出逐项相同。
5. **本卡带来的、用户应当知道的事**：改动只在一个工作流文件；普通分支的行为不变（仍扫 `origin/main..HEAD` 全段）；`pull_request` 触发要真实开一个到 main 的 PR 才能验证，计划在 M3-MAIN 一步先开“目标提交到 main”的草稿 PR 验证（评审建议），main 上的 push 路径在快进推送之后验证；`paths` 过滤在将来把 CI 设为必需检查后，不碰这些路径的 PR 会一直等不到检查，留给 M3-COLLAB。
6. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差；此前所有受治理卡均严格全绿（未使用）。
7. **演练事实（非治理，草稿工作树，不是正式证据）**：2026-10-17 在基线（卡 150 的提交）的临时工作树里跑了一遍本卡的快速门禁与判卷（原始输出在 `.auto-pm/reports/m3-cimain/gates_rehearsal/`）：候选字节等于冻结文本、YAML 可解析、触发与并发组符合设计、秘密扫描脚本块在 8 个沙盒仓库里的行为全部符合预期、CI 自检通过、冒烟与导入测试通过、静态检查、7 个反例全部被内容合同拒绝、真实 pre-commit 钩子退出 0；九组回归用合成输出（卡 150 的受治理输出，产品字节未变所以期望增量为零）判卷，G1–G9 全 PASS，4 个反例变体判卷结果符合预期。演练中发现并修掉的两处是判卷脚本自己的：自检输出里本来就含 FAIL 字样（改为核对“全部符合预期”一句）、变异条数写成 6（实为 7 个反例加 1 个正例）。演练不是正式证据，正式 Run 完整重跑。

## 2. 单一目标与完成定义

冻结的一个文件的字节被提交，且九组回归与上一张卡的输出逐项相同；技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、冻结文件的基线 blob 等于冻结哈希。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **机器负载**：启动前核对前台无游戏/启动器，近 10 秒 CPU 低；Windows 更新已由用户暂停至 2026-11-18。
4. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有续租成功。
5. **正式门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 1 小时 30 分钟。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `.github/workflows/sw008-ci.yml` | 存在 | `.github/workflows/sw008-ci.yml`：push 去掉对 main 的排除、新增对 main 的 pull_request 触发、main 不取消、秘密扫描基线按事件取并失败即关闭（共 3 处替换） |

出现第 2 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-cimain/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；冻结文件的基线（`e0d452d4` 上的）blob SHA-256 在 `cimain_config.json` 与启动脚本里冻结。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `.github/workflows/sw008-ci.yml` | 存在 | `996d3bd3e9c6727683883959667516e216d991dce7dc03a7c09ca497cca82282` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-cimain/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `1cd24880317722cdfc0aa763447d21af93f1224f206d16f0bbad51b2e1ec7f44`。

| 工具 | SHA-256 |
|---|---|
| `adjust_counts.py` | `3be71108779dd23bcc742186b5048c82e6a0c29de6998e80318d5587dcda595f` |
| `cimain_config.json` | `ac6c6285271853975661d9641db1414693b0f244bae7d87a118d26dc67d0225e` |
| `cimain_gates.py` | `f3fab1fdf747bceb2e0ffb6a87902ddf9291bc76708b896066ec3a058560f114` |
| `cimain_gates_all.sh` | `27e1d1a60a21cb618f42c474b4e5f9ae171f4d6f51fcd6d12328de6397b95b72` |
| `cimain_lib.py` | `f870229ce9097a422e29f73a756a4113ad1b80ee9446d63f857266eaf1a8b1d5` |
| `commit_msg.template.txt` | `12cc5ef6bac1f36d615e38f34748b8aa1701c8e65733453afdd65600edc23b58` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `install_files.py` | `a13a522ab987a7eacf9767ab7378d996899d78ad58816cd59195d49c3bbbb48e` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

## 6. 门禁矩阵

核心档。顺序：基线测量 → 安装冻结文件 → 快速门禁 → 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、冻结文件为基线字节；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与上一张卡的受治理输出相比：失败集合为空、无 ERROR，各组通过数与 skip 数不变（本卡不加测试）。唯一容忍规则见 §1 第 6 条 |
| G3 | 内容合同 | 候选字节等于冻结文本（基线加三处冻结的替换，LF、无 BOM）；YAML 可解析、push 没有分支过滤、`pull_request` 只对 main 且 `paths` 与 push 相同、main 不取消、`workflow_dispatch` 还在、其余步骤与 `permissions`、`env` 与基线相同；**秘密扫描脚本块在 8 个沙盒场景里行为正确**（推送 main 且 before 有效 → 基线为 before；before 全零或不存在 → 退出 1 并给 `::error::`；普通分支推送 → `origin/main`；pull request → 其 base.sha，缺失则退出 1；手动运行 → `origin/main`；分支推送但没有 `origin/main` → 退出 1）；CI 自检脚本 `selftest.py` 退出 0；冒烟与导入测试通过；插件二进制 SHA-256 前后相同 |
| G4 | 静态 | `ruff check auto_pm tests` 干净；`mypy --platform win32 auto_pm` 干净；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 1 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 产品字节不变 | `auto_pm`、`templates`、`tests`、`scripts` 四棵树与基线逐字节相同 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 1 个文件退出 0（临时索引） |
| G8 | 负向对照与正例 | 7 个反例（恢复 `branches-ignore`、main 可被取消、每次推送都用 `before`、去掉失败即关闭的检查、pull request 用 `origin/main`、CRLF、改了别的步骤）各被同一内容合同拒绝；冻结候选被接受 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-16 说“你的其他建议全部批准”“允许夜里推”“允许夜里执行”“今天晚上继续作业”，项目 Claude 的评审 `reviews/01_cimain_workflow.md` 采纳（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt`）；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

0. 启动前核对本机负载：无游戏/启动器在前台，近 10 秒 CPU 占用低；有则等待，不启动。
1. 在聊天报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 的 SCPT/OPT 变更单、匹配 Decision（`DEC-<当天>-M3CIMN01`）、Work `WORK-SW008-M3-CIMAIN-001`、Run `RUN-SW008-M3-CIMAIN-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-cimain`，分支 `codex/m3-cimain-workflow`。
4. 安装冻结字节并完整重跑门禁（`cimain_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 6 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；插件缺失或版本不符；需要改这 1 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；同一问题两次未解就通知用户（用户切 Opus 诊断）；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始输出（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录。

## 11. 限制与后续

提交在本地分支 `codex/m3-cimain-workflow`。之后：推送并读 CI（改了工作流文件，所以会触发一次 CI，也验证语法）；台账与 WBS 回写；M3-MAIN（选定目标提交，草稿 PR，快进推送）。
