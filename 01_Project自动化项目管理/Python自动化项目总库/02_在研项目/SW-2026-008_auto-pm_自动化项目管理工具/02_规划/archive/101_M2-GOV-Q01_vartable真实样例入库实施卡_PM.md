# M2-GOV-Q01｜vartable 真实样例入库实施卡

> 卡片编号：`CARD-SW008-M2-Q01`
> 版本：`V1.0`（2026-10-11；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PENDING_USER_APPROVAL`（用户 2026-10-11 要求连续派生三张卡；本卡 SHA 报给用户之后，须用户在聊天中回复批准才启动；条件见 §7）
> 档次：**测试档**（规则文档 §3：只新增测试夹具与其 Git 元文件；相关完整组 `rest`，含 tests/vartable；不改任何产品或测试代码）
> 依赖：卡 100（M2-GOV-MRG1）的 Run/Work 已达技术终态且 CHG-SCPT-2026-403 已收口（由启动脚本核验）
> 隔离基线：`bf19b6bd684fe703321882bec111a3e6b51ccf36`（卡 100 V1.1 的合并提交，本地分支 `codex/m2-merge-093-095`；CHG-SCPT-2026-403 completed）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-11，基线 `bf19b6bd`）

1. **为什么要这张卡**：WBS 任务 **Q01** 要求“14 个 vartable 真实样例测试在干净候选可复现，或明确跳过并用替代样例重验”，它是 D05 全量门禁的前置，不能拖到 D05 当天。你 2026-10-10 裁决“补样本”（不跳过）。台账 TD-SW008-054 记录了这 15 个既存失败。
2. **根因（已查明）**：两个真实样例 CSV 在控制根磁盘上存在，但被项目 `.gitignore` 第 9 行的 `*.csv*` 规则挡在 Git 之外，所以任何干净检出（隔离工作树、云端 CI）都缺它们，14 个测试因“真实样例 fixture 缺失”失败。控制根上的 rest 组原有 15 个失败 = 这 14 个 + 1 个 TD-SW008-042（夹具健康测试）。
3. **做什么**（4 个新增文件，全在 `tests/vartable/samples/` 下）：两个样例 CSV；一个嵌套 `.gitignore`（`!*.csv`，嵌套规则优先于父目录规则）；一个嵌套 `.gitattributes`（`*.csv -text -diff`）。样例是 UTF-16LE 带 BOM（Work-FB）和 GB18030 带 CRLF（Autoshop-FB）。仓库根的默认属性是 `* text=auto eol=lf`，Git for Windows 还默认 `core.autocrlf=true`；今天 Git 的自动判断把这两个文件识别为二进制（`git ls-files --eol` 显示 `-text`），本来不会被改字节，但这是启发式判断；显式的 `-text` 把它固定下来，之后内容或 Git 版本变化也不会让样例字节漂移。
4. **为什么用嵌套文件而不改项目 `.gitignore` 与仓库根 `.gitattributes`**：分档器把项目 `.gitignore` 判为产品档、把仓库根 `.gitattributes` 判为核心档；嵌套文件只作用于这个目录，保持在测试档，不扩大影响面。
5. **这不是新的公开内容**：两个 CSV 与已经入库、已在远端的 `00_Infrastructure/auto_pm/tests/vartable/samples/` 下的同名副本逐字节相同（我在基线与 `origin/codex/m2-gov-wbs9-attest` 上核对过，SHA-256 相同）。仍然不推送：推送由你另行授权。样例里的 Work-FB 的功能块名“边框缓存机”是项目内信号名，不含客户名。
6. **预期效果**：rest 组从 15 failed / 840 passed 变为 1 failed / 854 passed（剩下的 1 个是 TD-SW008-042，不在本卡）；14 个节点（清单冻结在 `q01_config.json` 的 `fixed_nodes`）与整个 `tests/vartable` 文件夹全绿。
7. 我在隔离演练树上完整跑了一遍（非受治理执行，不能复用为正式门禁；输出在 `.auto-pm/reports/m2-q01/gates_rehearsal/`）：基线 `tests/vartable` 为 14 failed / 106 passed / 12 skipped，失败恰是冻结的 14 个节点；安装后这 14 个节点与整个 `tests/vartable` 通过（120 passed / 12 skipped）；rest 组 `1 failed, 854 passed, 13 skipped`（23 分 39 秒；基线为 15 failed / 840 passed / 13 skipped），唯一的失败是 TD-SW008-042；G1–G9 判卷全部 PASS，共用判卷脚本接受判卷文件；真实 `pre-commit` 钩子对暂存的 4 个文件退出 0；7 个反例各被对应断言拒绝、完整集合被接受。**诚实记录**：演练第一轮在 G6 的导出步骤崩溃（Windows 自带的 tar 不能解含中文路径的归档，已改用 Python 的 tarfile）；第二轮暴露了我写的四处判据错误——tests/vartable 在基线上本来就有 12 个 skip（我写成了 0）、“安装前干净”的记录点放在了安装之后、钩子被解析到 WSL 的 bash 而不是 Git 的 bash、以及“缺 .gitattributes 会让 CRLF 样例被规范化”这个假设不成立（`git ls-files --eol` 显示 Git 目前就把这两个文件自动判为二进制，不会规范化；显式的 `-text` 是把这个判断固定下来的防御，所以 §1 第 3 条与负向对照据此改写）——均已修正；修正后重跑了快速门禁与判卷，rest 组输出沿用第一次完整运行（它与这些修正无关）。正式 Run 会完整重跑全部门禁。
8. **不做什么**：不改任何测试代码、不改产品代码、不改 TD-SW008-042 的夹具健康测试、不改项目 `.gitignore` 与仓库根 `.gitattributes`、不改 `00_Infrastructure` 下的副本；不推送、不打 tag、不处置任何债务。

## 2. 单一目标与完成定义

让两个真实样例在干净检出里存在且字节不变，从而 14 个 vartable 真实样例测试可复现。技术完成 = 全部门禁通过且提交字节等于冻结清单；**验收 = 用户阅读后确认**，变更单收口不委托。

## 3. 实施前预检

1. 核对卡字节与已向用户报告的 SHA 一致、基线分支仍在基线、4 个路径在基线不存在、工具与冻结字节指纹。没有这些，不创建 CHG/Decision/Work/Run。启动脚本另有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. 核对卡 100 的 Run/Work 为 SUCCEEDED/CLOSED、CHG-SCPT-2026-403 completed。
4. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`，门禁期间每次检查先看续租日志。

## 4. 精确 Owned Paths（4）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/vartable/samples/.gitattributes` | 计划新增 | 嵌套属性：`*.csv -text -diff`，Git 不规范化 UTF-16LE 与 CRLF 字节 |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/vartable/samples/.gitignore` | 计划新增 | 嵌套忽略规则：`!*.csv` 让本目录的两个样例不再被项目 `.gitignore` 的 `*.csv*` 吞掉 |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/vartable/samples/Autoshop-FB变量表导出.csv` | 计划新增 | 真实样例（GB18030，CRLF）；与已入库副本逐字节相同 |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/vartable/samples/Work-FB变量表导出.csv` | 计划新增 | 真实样例（TIA 导出，UTF-16LE 带 BOM）；与 `00_Infrastructure/auto_pm/tests/vartable/samples` 下已入库副本逐字节相同 |

出现第 5 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-q01/`、本卡文件、演练工作树）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

4 个新增文件的最终 SHA-256；冻结副本在 `.auto-pm/reports/m2-q01/proto/` 下同一路径。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/vartable/samples/.gitattributes` | 计划新增 | `5aebe3293e2d79176a761f8ef8000dfb0780783310bc63e3fd3d5954e26ad348` |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/vartable/samples/.gitignore` | 计划新增 | `5300307c6458336a7a2e01c44cc28bb8d8f0ed18e14992e65254acdf15a81e8e` |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/vartable/samples/Autoshop-FB变量表导出.csv` | 计划新增 | `04862439ebdb4432a1b9af65d866064d88c921f347eba7fe6cfc07f4382e8131` |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/vartable/samples/Work-FB变量表导出.csv` | 计划新增 | `f23a5d29993b2524717eb3e49db3d0dc7509b1c05cc20e435d01eadfea0fdc0e` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m2-q01/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `db20d3bf19462ade8aad38adc6f88534b2994513662d297af1c2103b470a875c`。G2 的基线取卡 100 V1.1 受治理执行的 rest 组真实输出（`.auto-pm/reports/m2-mrg1/gates/g2_candidate/rest.txt`，其 SHA-256 冻结在 `q01_config.json`）。

| 工具 | SHA-256 |
|---|---|
| `commit_msg.template.txt` | `f6ef9abbbf256c11cea1bdd308f398d31ad429c09099f86e2568d0cab6df838b` |
| `install_files.py` | `7df27c7d5bad884b25392bd130cbbfe847e6f35e6a7012fa3a26db61166f47f6` |
| `q01_config.json` | `bf54b58f7b19df8e83ee69f02d9f5795877f111773a0ec0b769a84f799675c29` |
| `q01_gates.py` | `c5bcbe8c9d47faf47ef1ab3683593492ac8538302638cdbfea85d36c32d0c091` |
| `q01_gates_all.sh` | `c425ce5b086d31977fb7d34fcafc8d743af2bce9918ca112788e7adc5c5374d3` |
| `run_g2.sh` | `10b906ffd3424a7f94faf4100f85ba1d32319e650a3e7d61aa9c08656872508a` |

## 6. 门禁矩阵

测试档。顺序：基线测量 → 安装冻结文件 → 快速门禁 → rest 组回归（G2）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 夹具健康、冒烟、导入测试；基线上 tests/vartable 的失败 | 候选与基线完全相同（既存失败仅 TD-SW008-042 一个）；基线上 tests/vartable 的失败恰为冻结的 14 个节点 |
| G2 | rest 组回归（含 tests/vartable） | 与卡 100 V1.1 的真实输出比：失败集合恰少这 14 个节点、通过数恰多 14、skip 数不变、无 ERROR |
| G3 | 样例相关测试 | 14 个冻结节点全部通过；整个 tests/vartable 文件夹 0 失败、0 跳过 |
| G4 | Git 语义 | 4 个文件均未被忽略；Git 存储的 blob 等于原始字节（无换行或编码规范化）；两个 CSV 的 SHA-256 等于基线上已入库的 00_Infrastructure 副本；无密钥格式的值 |
| G5 | 范围与字节 | 变更集恰为 4 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留 |
| G6 | 既有内容不变 | auto_pm 与 templates 树与基线逐字节相同；tests 树只多这 4 个文件 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的这 4 个文件退出 0（临时索引） |
| G8 | 负向对照（7 项反例与 1 个正例） | extra_file、missing_file、byte_drift、secret_injected、crlf_flip、嵌套 .gitignore 缺失（样例会被忽略）、嵌套 .gitattributes 缺失（`text` 属性不再是 unset）各被对应断言拒绝；完整集合被接受 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-10 裁决“补样本”、2026-10-11 要求连续派生三张卡；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与摘要，等用户批准。
2. 创建 SW-2026-008 SCPT/DEF 变更单、匹配 Decision（`DEC-<当天>-Q01SAMPL`）、Work `WORK-SW008-M2-Q01-001`、Run `RUN-SW008-M2-Q01-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）；实际创建前验证未被占用。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-q01`，分支 `codex/m2-q01-samples`。
4. 安装冻结字节并完整重跑门禁（`q01_gates_all.sh`）；先创建当前字节 Checkpoint，再正常 Hook 提交 4 个文件，绝不 no-verify；核对提交父、范围及 blob 与 Checkpoint 完全一致。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；**变更单停在“实施中”，等用户阅读后验收再收口。**

## 9. 硬停止

基线、工具/卡/Decision 指纹、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要改这 4 个文件以外的任何内容、或为让测试变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。全量测试对机器负载敏感（TD-SW008-095，另见 TD-SW008-120）：正式门禁期间不并发其他重任务。若 G2 因 TD-SW008-120 的竞态测试失败，本卡**没有**容忍规则，按上条停下，由你裁决。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始门禁（非治理）与真实钩子干跑；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；用户阅读验收的记录。

## 11. 限制与后续

提交在本地分支 `codex/m2-q01-samples`，**不推送、不合并进 main**。卡 102（CHG-195 勘误）与卡 103（台账同步）叠在本卡提交之上。TD-SW008-042 与 TD-SW008-120 是 rest 组里仍可能出现的失败来源，另案处理。
