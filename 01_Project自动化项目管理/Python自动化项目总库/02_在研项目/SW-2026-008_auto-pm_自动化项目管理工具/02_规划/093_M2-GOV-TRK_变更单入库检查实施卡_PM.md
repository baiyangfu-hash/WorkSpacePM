# M2-GOV-TRK｜变更单入库检查工具实施卡

> 卡片编号：`CARD-SW008-M2-TRK`
> 版本：`V1.0`（2026-10-10；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-10 预授权当日排期，原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾；条件见 §7）
> 档次：**测试档**（规则文档 §3：只新增测试与测试辅助工具；相关完整组 `rest`，含 tests/e2e；不改任何产品文件）
> 依赖：卡 094（M2-GOV-GIGN）的 Run/Work 已达技术终态（由启动脚本核验）
> 隔离基线：`8cb8dceb86e957ce6096c4ace39a0e988144d38d`（卡 094 的提交，本地分支 `codex/m2-gign-rules`）
> 治理任务真源：WBS 提交 `aa02be02674e062f0ececcfe69b565860ffbe55c`（V3.0.26）；台账 TD-SW008-113
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

## 1. 背景与已核实事实（2026-10-10，基线 `8cb8dceb`）

1. **为什么要这张卡**：`ledger reconcile` 只比较“变更单文件在磁盘上”与“台账有一行”，**从不问“这个文件是否在某个提交里”**。164 张变更单因此只存在于一块磁盘上、没有进过任何提交，对账一直是 0/0/0（台账 TD-SW008-108 与 TD-SW008-113；卡 088 已把它们入库到本地分支 `codex/m2-chgimp-records`）。这是根因：没有任何检查会再发现同类问题。
2. **做什么**（两个新增文件，其余零改动）：
   - `tests/tools/chg_tracking_check.py`：只读检查工具。找出 `01_变更单` 目录（或 `--dir` 指定的目录）里所有名为 `CHG-<域>-<年>-<序号>.md` 的文件，与 `--ref`（默认 HEAD）的树比对：**不在树里**的报 `untracked`，**在树里但内容不同**的报 `modified`（比较前把 CRLF 归一为 LF，与 Git 入库一致）。退出码：0 全部已入库且未改动，2 有发现，3 输入不可用（不是仓库、引用不存在、目录越界）。跳过 `.git`、`.auto-pm`、`.venv`、`node_modules`、`__pycache__`。**永不写仓库，永不执行 `git add`。**
   - `tests/e2e/test_pmf_chg_tracking_check.py`：9 个测试节点，每个都建一个真实的一次性 Git 仓库、做真实提交、把工具当命令运行，核对退出码与报告：全部已入库为干净；只在盘上为 untracked 且不改动仓库状态；内容变化为 modified；只有换行差异不算改动；非变更单文件不被检查；`--ref` 决定“已入库”的含义；`--dir` 只查指定目录；非仓库、不存在的引用、越界目录被拒绝；默认搜索只看 `01_变更单` 目录并跳过运行态目录。
3. **在真实控制根上的只读试跑**（2026-10-10，对基线分支，输出 `.auto-pm/reports/m2-trk/real_run_control_root.json`）：检查 495 个变更单文件，**23 个不在基线提交里**、0 个被改动。分布：DJ-2026-005 1 张；DJ-2026-008_长边框堆垛机 1 张；SW-2026-008_auto-pm_自动化项目管理工具 6 张；SW-2026-009_英语学习助手 15 张。这些是今天新建且尚未入库的变更单与两个项目里尚未入库的变更单；本卡**只报告、不入库**（入库另卡）。工具的第一次真实运行就找到了对账一直看不见的东西。
4. **本卡的限度**：检查工具**不接进任何门禁、启动脚本或提交钩子**（接线要改核心或产品文件，需另卡与批准）；本卡只让“发现”这件事存在、可测试、可被以后的门禁调用。
5. **我在全新基线副本上的演练**（2026-10-10，非受治理执行，受治理执行里完整重跑，不采纳这些输出；输出在 `.auto-pm/reports/m2-trk/gates_rehearsal/`）：
   ① `ruff check` 与 `mypy --strict` 对两个 Python 文件零问题、`git diff --check` 通过；
   ② G1：基线 `1 failed, 26 passed in 14.12s`；候选 `1 failed, 26 passed in 4.76s`（既存失败相同）；
   ③ G9：新测试文件 `9 passed in 12.61s`；
   ④ G8：12 个变异在未变异字节上先为绿，变异后各被点名测试的真实断言失败杀死，字节逐一还原，完整输出已保存；
   ⑤ G6：除这两个新增文件外 `templates`、`auto_pm`、`tests` 树与基线逐字节相同；
   ⑥ G2 的 rest 组回归：演练里在基线副本上完整跑过一遍，正式门禁重跑，基线取 M2-DEP-INT 卡受治理执行的真实输出（其项目代码字节与本基线相同）。
6. 本卡不调用真实模型，不碰 PLC 项目的变更单，不入库任何变更单。

## 2. 单一目标与完成定义

新增两个文件，让“变更单在盘上但不在提交里”这件事能被一个只读命令发现，并被测试证明。其余产品、模板、台账、WBS 均零改动。

9 个新增测试节点（均在 `tests/e2e/test_pmf_chg_tracking_check.py`）；12 个变异（对象是检查工具代码，每个由点名测试的真实断言失败杀死）：
   - M01-an-untracked-file-is-clean：a change request that is not in the commit is reported, not silently accepted
   - M02-a-modified-file-is-clean：a committed change request whose content changed is reported
   - M03-line-endings-count-as-a-change：a difference in line endings alone is not a modification (Git normalises on add)
   - M04-any-markdown-is-a-change-request：only files named CHG-<DOMAIN>-<YEAR>-<NNN>.md are change requests
   - M05-findings-exit-zero：findings are a non-zero exit code, so a gate can stop on them
   - M06-bad-input-exits-zero：a folder that is not a repository is refused with exit 3, never reported as clean
   - M07-the-reference-commit-is-ignored：the tree of --ref decides what counts as tracked, not the current HEAD
   - M08-dir-searches-the-whole-repository：with --dir only the named folders are checked
   - M09-a-folder-outside-the-repository-is-accepted：--dir may not leave the repository
   - M10-runtime-folders-are-searched：worktrees and runtime state under .auto-pm are not change requests of this repository
   - M11-the-search-leaves-the-change-request-folders：by default only folders named 01_变更单 are searched
   - M12-the-count-is-not-reported：the report says how many change requests were checked

技术完成 = 全部门禁通过且提交字节等于冻结清单；**验收 = 用户阅读后确认**，变更单收口不委托。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线、2 个 owned path 及参考字节。没有这些，不创建 CHG/Decision/Work/Run。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空；预检仅读，不代表获批。启动脚本另有 `--check-only` 模式，只做上述检查、不写任何东西。
3. 核对卡 094 的 Run/Work 为 SUCCEEDED/CLOSED；核对历史失败记录仍在原状态且本卡不触碰。
4. 新候选 HEAD 等于基线且 clean；两个新增路径在基线不存在；工具与参考字节均匹配冻结指纹。
5. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`，门禁期间每次检查先看续租日志（规则文档 §15）。

## 4. 精确 Owned Paths（2）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `tests/e2e/test_pmf_chg_tracking_check.py` | 计划新增 | 证明检查工具的测试：在真实的一次性 Git 仓库里运行工具，核对退出码与报告 |
| 2 | `tests/tools/chg_tracking_check.py` | 计划新增 | 检查工具：只读，把变更单文件与指定提交的树比对，报 untracked 与 modified，永不写仓库 |

出现第 3 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-trk/`、本卡文件、演练工作树）不是额外产品 owned paths，不进本卡产品提交。

## 5. 字节合同

### 5.1 参考字节指纹

两个新增文件的最终 SHA-256（UTF-8、LF、无 BOM）；冻结文件保存在 `.auto-pm/reports/m2-trk/proto/`。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `tests/e2e/test_pmf_chg_tracking_check.py` | 计划新增 | `cf1c5c3bfd72a9e5aebc606a49a7e679d0dafcb437b46462879ecd4e849aaeff` |
| 2 | `tests/tools/chg_tracking_check.py` | 计划新增 | `f8c2a8867080b175656ae32c1b8c7239fdd428ed195af34a8a8352752d537a9f` |

### 5.2 冻结工具

工具与脚本由卡 078（M2-TOOL-TIER，测试档、rest 组）的已验收工具派生（`.auto-pm/reports/m2-trk/`）；共用判卷脚本仍是控制根下的外部副本。变异运行器保存每次运行的完整输出并绑定进判卷文件。G2 的基线取 M2-DEP-INT 卡受治理执行的 rest 组真实输出。

| 工具 | SHA-256 |
|---|---|
| `commit_msg.template.txt` | `8e4bf346b4caa5b89db3e3d38c8cc3c11f326870b0151cc9081df2279ce66da2` |
| `g6_check.py` | `add08a22fbf5e11410ed79f6301319228be241d3b59775ea3916297db0eba15d` |
| `install_candidate.py` | `9e598023a3adbeaa5943933808b8ab1183925dcf7295c8231e3b7f943ced122c` |
| `m2-tools/mutation_classify.py` | `0fff21f888cb1a50094f050ef8bc3b42ea25653ba508581e3c85fa1b28d79019` |
| `m2-tools/verdict_check.py` | `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188` |
| `mutation_plan.json` | `e13bed31f40441efa389d09e8d9e42aef58f4ff275001c7c6dfaacfd3b9d0bb6` |
| `mutation_run.py` | `cec1a0d18c1273df4c12a7bc35fccde22a180e5545f3380197f13b53e6ea48d3` |
| `new_nodes.json` | `37f3a2954b71389460f53e2d66a3b6d2dbf9879e89bedbedf69b7242b17a5d7b` |
| `run_g2.sh` | `10b906ffd3424a7f94faf4100f85ba1d32319e650a3e7d61aa9c08656872508a` |
| `run_gates_fast.sh` | `b31c7ae32d1a4831ce885ca13cd90e6ffdee8c407e68d00c9fe045946a31fcf7` |
| `run_gates_g2.sh` | `03941855ca6bdda7f47f789da1117ba804f7d937d8a6d28b985f8ad0cf39e9c6` |
| `run_gates_trk.py` | `f8e6be56158758f8ca2e88ca5de4f5aae6308574ad82c39992c727cb3ae6803a` |

## 6. 门禁矩阵

测试档。顺序：基线测量 → 安装参考字节 → 快速门禁（G4、G3、G1、G9、G8、G6）→ rest 组回归（G2）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 夹具健康、冒烟、导入测试 | 与基线完全相同（26 passed，1 个既存失败） |
| G2 | rest 组回归（含 tests/e2e） | 失败集合与基线相同、通过数恰增 9、无新增 skip 与 ERROR |
| G3 | 新测试节点 | 收集到的恰为冻结的 9 个节点 |
| G4 | 静态检查 | 两个 Python 文件 `ruff`、`mypy --strict` 零问题，`git diff --check`，字节扫描，新增行无抑制注释 |
| G5 | 范围 | 变更集恰为 2 个 owned path，字节等于 §5.1，无残留 |
| G6 | 既有内容不变 | `templates`、`auto_pm`、`tests` 树除这两个新增文件外与基线逐字节相同 |
| G7 | 隔离 | 新增行不引用真实控制根；真实 `.git/hooks` 前后字节相同；门禁不遗留 python 进程 |
| G8 | 严格变异 | 12 个变异各被点名测试的真实断言失败杀死，字节还原；每次运行的完整输出保存并绑定 |
| G9 | 新测试文件整体 | 9 passed、0 failed、0 skipped |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-10 预授权当日排期（原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾）：卡 SHA 先在汇报里报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在汇报里报告最终卡 SHA 与改动摘要。
2. 创建 SW-2026-008 SCPT/DEF 变更单、匹配 Decision（`DEC-<当天>-TRKCHECK`）、Work `WORK-SW008-M2-TRK-001`、Run `RUN-SW008-M2-TRK-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）；实际创建前验证未被占用，不复用幂等键或旧 token。
3. 从代码基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-trk`，分支 `codex/m2-trk-check`。
4. 安装参考字节并完整重跑门禁（`trk_gates_all.sh`）；先创建当前字节 Checkpoint，再正常 Hook 提交 2 个 owned 文件，绝不 no-verify；核对提交父、范围及 blob 与 Checkpoint 完全一致。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；**变更单停在“实施中”，等用户阅读后验收再收口。**

## 9. 硬停止

基线、工具/卡/Decision 指纹、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败；变异未被点名断言杀死；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要改这两个文件以外的任何内容、或为让测试变绿而放宽断言：均停止，保留现场，不靠重跑、改字节或放宽判据变绿。按止损规则：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。全量测试对机器负载敏感（台账 TD-SW008-095）：正式门禁期间不并发其他重任务。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结参考字节与工具；演练原始门禁（非治理）；真实控制根只读试跑结果；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；用户阅读验收的记录。

## 11. 限制与后续

检查工具只报告、不入库、不接入任何门禁；23 个尚未入库的变更单怎么处理（入库另卡、PLC 的两张在“PLC 变更单入库”事项里）、是否把检查接进提交前或推送前门禁，均是后续单独卡与批准的事。提交在本地分支 `codex/m2-trk-check`，**不推送、不合并**。不处置 TD-SW008 台账里的任何债务。
