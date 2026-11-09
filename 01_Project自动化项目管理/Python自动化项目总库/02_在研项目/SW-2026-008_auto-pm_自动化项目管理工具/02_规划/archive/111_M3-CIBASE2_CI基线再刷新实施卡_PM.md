# M3-CIBASE2｜CI 基线再刷新实施卡

> 卡片编号：`CARD-SW008-M3-CIBASE2`
> 版本：`V1.0`（2026-10-11；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-11 预授权当日排期含 TD-SW008-042，并要求“替我收口验收”；本卡是卡 107 修复 TD-SW008-042 的必然后果；本卡 SHA 先在聊天报出再启动；条件见 §7；**不含推送**）
> 档次：**测试档**（规则文档 §3：只改测试目录下的一个数据文件；相关完整组 `rest`；不改任何产品或测试代码）
> 依赖：卡 110（M3-WBS13）的 Run/Work 已达技术终态且 CHG-DOCU-2026-041（卡 109）已收口（由启动脚本核验）
> 隔离基线：`e61c4fa9e914c810e2013615fbaca86d45f41c8d`（卡 110 的提交，已推送的远端尖端）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-11）

1. **为什么**：2026-10-11 把 `e61c4fa9` 推送后，CI 第 5 次运行（`sw008-ci`）只在“Compare the failures with the known Linux baseline”一步失败（Pytest 步骤本身通过）。原因按下面推断：卡 107 修好了 TD-SW008-042，夹具健康测试 `tests/test_fixture_health.py::TestFixtureHealth::test_no_conditional_assertion_skips` 在 Linux 上也通过了，但基线 `baseline.linux.json` 仍登记它为已知失败（类别 `KNOWN_BASELINE_ALSO_ON_WINDOWS`）。比较脚本的规则是“基线里的条目意外通过 = 判 FAIL（基线过期）”。**局限**：GitHub 的日志下载需要登录，我读不到该步骤的原始输出，只读到了步骤级的失败标记与退出码 1；上面是依据代码与卡 107 结果的推断，合并后再推送、读 CI 才能证明。
2. **做什么**（只改这一个数据文件）：去掉 `ids` 里的 1 个 id、`id_category` 里对应的 1 项、`categories` 里的 `KNOWN_BASELINE_ALSO_ON_WINDOWS`；其余 20 个 id 与 `schema`、`platform`、`recorded_on`、`measured_on` 原样；`refreshed_on` 保持，`refresh_note` 末尾追加一句说明。被去掉的 id：
   - `tests/test_fixture_health.py::TestFixtureHealth::test_no_conditional_assertion_skips`
3. **没有任何测试读这个文件**：它只被 CI 工作流的比较步骤读取；rest 组结果应与卡 107 的受治理输出完全相同（0 failed / 855 passed / 13 skipped）。
4. **检查**：独立检查脚本核对：文件字节等于冻结值、标准 JSON 格式；`ids` 恰为旧 `ids` 去掉 1 个；`id_category` 键与 `ids` 一致、类别都存在、被去掉的类别不再出现；其余顶层字段不变；刷新说明已变化；无密钥形态的值。并**真实运行随仓库交付的 `compare_baseline.py`**：新的 20 个失败集合 → `PASS_KNOWN_BASELINE`（exit 0）；旧的 21 个集合（含已修好的测试）→ `FAIL`；少一个 id → `FAIL`（过期）。8 个反例与 1 个正例各被对应断言处理。**它不证明 Linux 行为**，见第 1 条的局限。
5. **演练事实（非治理，草稿工作树，不是正式证据）**：2026-10-11 在基线 `e61c4fa9` 的临时工作树里做了轻量演练（原始输出在 `.auto-pm/reports/m3-cibase2/gates_rehearsal/`）：基线上夹具健康、冒烟、导入测试 27 个全部通过；装入冻结文件后同样 27 个通过；快速门禁与判卷脚本在“rest 组输出取卡 107 的真实输出”的合成条件下 G1–G9 全 PASS。真实的 rest 组回归只有正式 Run 才有，演练没有跑它。
6. **不做什么**：不改任何测试、产品、工作流或比较脚本；不重测 Linux；不推送（推送需用户另行授权）。

## 2. 单一目标与完成定义

基线文件与卡 107 之后的事实一致。技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、基线文件的基线 blob 等于冻结哈希（`c117fc973c3462dc372fc3a46d0cc8e0e0b5571987805af981d383455b622443`）、卡 110 的 Run/Work 为 SUCCEEDED/CLOSED、CHG-DOCU-2026-041 completed。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/sw008_ci/baseline.linux.json` | 存在 | Linux CI 的已知基线：去掉夹具健康测试的 id 与 `KNOWN_BASELINE_ALSO_ON_WINDOWS` 类别（余 20 个 id），其余字段原样，刷新说明追加一句 |

出现第 2 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-cibase2/`、本卡文件、演练工作树）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；基线（`e61c4fa9` 上的）blob SHA-256 为 `c117fc973c3462dc372fc3a46d0cc8e0e0b5571987805af981d383455b622443`。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/sw008_ci/baseline.linux.json` | 存在 | `375a0c388a7521f29f24fbd32120ce75c1ded4d137ba23721383994fa2bbb7b4` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-cibase2/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `248c5b272bbd361f3da35fe0f68da49eb4d9fb4b4454cd809ca381c8effd16f8`。G2 的基线取卡 107 受治理执行的 rest 组真实输出（`.auto-pm/reports/m3-a1/gates/g2_candidate/rest.txt`，其 SHA-256 冻结在 `cibase2_config.json`）。

| 工具 | SHA-256 |
|---|---|
| `cibase2_config.json` | `e96d43fbd3a7d20e072fb8e681b8f84787c64c2ce6130caa40e21f52056b010b` |
| `cibase2_gates.py` | `dcd4e2f0adba15adb8c140e85def799fb15e1a4367ad32600ec9e2dbc2033766` |
| `cibase2_gates_all.sh` | `ef1f225702e46db3592e36b1a21b1d8db7acacf7b5e1ac1b04edde34b0180b19` |
| `commit_msg.template.txt` | `a466067c3514567303daa118a0c77d1825a4e8230b54245052a2e98eb5ab9f6f` |
| `install_files.py` | `94677ec9d8ce4d93d8447add7b88e1f90e4f31d30d0d33ef103b93921b35bf61` |
| `run_g2.sh` | `10b906ffd3424a7f94faf4100f85ba1d32319e650a3e7d61aa9c08656872508a` |

## 6. 门禁矩阵

测试档。顺序：基线测量 → 安装冻结文件 → 快速门禁 → rest 组回归（G2）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 夹具健康、冒烟、导入测试 | 基线与候选都全部通过且数目相同（卡 107 已修好既存失败） |
| G2 | rest 组回归（含 tests/e2e、tests/vartable） | 与卡 107 的真实输出逐项相同：失败集合（空）、通过数 855、skip 数 13，无 ERROR |
| G3 | 基线文件合同与比较脚本的真实行为 | 文件合同无问题（20 个 id、被去掉的类别不再出现、键一致、其余字段不变、刷新说明已变化、标准格式）；`compare_baseline.py`：新集合 exit 0 且 PASS_KNOWN_BASELINE，旧 21 个集合 exit 1，少一个 id exit 1 |
| G4 | Git 语义 | 文件未被忽略；Git 存储的 blob 等于原始字节 |
| G5 | 范围与字节 | 变更集恰为 1 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净 |
| G6 | 既有内容不变 | auto_pm 与 templates 树与基线逐字节相同；tests 树只差这一个文件 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的该文件退出 0（临时索引） |
| G8 | 负向对照（8 项反例与 1 个正例） | byte_drift、secret_injected、crlf_flip、removed_id_left_in、other_id_dropped、category_map_out_of_sync、removed_category_kept、measured_on_changed 各被对应断言拒绝；冻结文件被接受 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-11 说“可以，按这个排期，预授权给你，授权有效时间截止到下午5:00pm.”（含 TD-SW008-042 的修复），并已要求“替我收口验收”（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾）；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与摘要，随即启动（预授权范围内，且在 17:00 之前）。
2. 创建 SW-2026-008 SCPT/DEF 变更单、匹配 Decision（`DEC-<当天>-CIBASE02`）、Work `WORK-SW008-M3-CIBASE2-001`、Run `RUN-SW008-M3-CIBASE2-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-cibase2`，分支 `codex/m3-cibase2-refresh`。
4. 安装冻结字节并完整重跑门禁（`cibase2_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要改这个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。正式门禁期间不并发其他重任务。若 G2 因 TD-SW008-120 的竞态测试失败，本卡**没有**容忍规则，按上条停下，由用户裁决。**17:00 之后不启动任何新卡**。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始输出（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录。

## 11. 限制与后续

提交在本地分支 `codex/m3-cibase2-refresh`（卡 110 的提交之上）。本卡之后：推送需要用户另行授权（上一次“推送”只覆盖了 `e61c4fa9` 及之前的提交）；推送后读 CI 结果并确认是否通过。
