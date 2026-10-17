# M3-PRDLAYOUT2｜驾驶舱接口文档对照与修复器实施卡（M3-PRDLAYOUT 第 2 张）

> 卡片编号：`CARD-SW008-M3-PRDLAYOUT2`
> 版本：`V1.0`（2026-10-15；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-15 说“按照计划开始今天的任务，预授权给你。11:00汇报进度”；此前 2026-10-14 裁决“根 PRD/ 不再生成；02_PLC程序/PLC_ST/00_程序方案/，保留这个”、要求高内聚低耦合，并让我裁决云端建议（17:25 已裁决）；本卡 SHA 先在聊天报出再启动；条件见 §7；**不含推送，不含规范库修订**）
> 档次：**产品档**（分档器：`auto_pm/…` 命中产品源码，`templates/…`、`tests/…` 同；取最高档；不得降级）
> 依赖：卡 141（M3-WBS23）的 Run/Work 已达技术终态且 CHG-DOCU-2026-047（SYS-2026-001）已收口（由启动脚本核验）
> 隔离基线：`f4dea34ca659365ee065d758fac62955c0871fb7`（卡 141 的提交，本地分支 `codex/m3-wbs23-v3039`，同时是已推送线 `origin/codex/m2-gov-wbs9-attest` 的尖端，CI 第 15 次 success）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-15）

1. **为什么**：用户 2026-10-14 的裁决（设计稿 `.auto-pm/reports/M3_PRDLAYOUT_DESIGN_20261014.md`，WBS §4.7.23、§4.7.24，台账 TD-SW008-131、138）：根 `PRD/` 不再生成，方案级 INT = FB 实例表 + FC 调用表 + 跨系统交换区契约；硬要求高内聚、低耦合；先只改 PLC。第 1 张（模板卡，卡 139，提交 `89892058`）已落地并推送（CI 第 15 次 success）。本卡是驾驶舱一侧。2026-10-14 17:25 对云端建议的裁决：交换区表头的“协议”做成开放列表（含 PROFINET、OPC UA，不限于 Modbus TCP、CC-Link），并新增“单位”列（word16 或 byte）。
2. **做什么**（4 个已有文件改、3 个文件新增；见 §4）：
   - **`repairer.py`**：驾驶舱“缺 PRD 目录”的修复，PLC 项目（有 `02_PLC程序/PLC_ST`）补到 `02_PLC程序/PLC_ST/00_程序方案/`，不再新建根 `PRD/`；已有根 `PRD/` 的老项目仍留在原处，没有 `PLC_ST` 的项目仍用 `PRD/`；
   - **`scheme_doc.py`（新）**：方案级 `接口文档_INT.md` 与代码的**存在性对照**，三项：FB 实例表对数据块里声明的 FB 实例（类型名 + `数据块.变量名`，两个方向的差异都点名）；FC 调用表对项目里定义与调用的 FC（表里有项目里没有、代码调用表里未登记都点名；定义了但没被调用的不算差异；注释里的不算调用）；交换区契约里的“负责的块”与“本机侧承载的变量”（数据块与第一级变量）在代码里存在（按项目填写的占位格不查）。**只警告，不失败，不写任何文件**；
   - **`checker.py`**：`PlcChecker` 在文档一致性检查之后调用 `scheme_items`，把结果加进检查项（出现异常也只给一条警告）；阶段门禁不变、不新增阻断；
   - **模板 `接口文档_INT.md.jinja`**：交换区一览表头改为“协议（开放列表）”、“总量”、新增“单位”列（word16 或 byte），说明里写明协议不限于 Modbus TCP、CC-Link，可填 PROFINET、OPC UA 等；3.1 字定义的偏移单位同单位列；
   - **测试**：`tests/plc/test_scheme_doc.py` 14 个、`tests/plc/test_repairer_prd_location.py` 5 个；端到端 `test_pmf_template_plc.py` 扩 v15 并新增 v16（生成的工程三项对照全为 pass）、v17（数据块里多出一个实例，对照项只警告、不失败）。
3. **开发期实测**（开发工作树，非治理）：新增 19 + 2 个用例全过；`tests/plc` 与端到端模板测试合计 234 个全过；涉及 `PlcChecker`、`PlcRepairer` 的其余测试文件 204 个通过、1 个跳过；`ruff check` 与 `mypy`（新模块）干净。
4. **本卡带来的、用户应当知道的后果**：
   - 已有项目（DJ-2026-005、008、009、011）上会多出 1～3 个“接口文档 INT ↔ 代码”检查项；对旧格式（参数明细写在方案级）的 INT，会得到“没有 FB 实例表”的警告，这是预期的提示，不是失败；
   - 新建的 PLC 项目的修复不再产生根 `PRD/`；
   - 协议开放列表只是文档表头与说明，驾驶舱不校验协议取值。
5. **不做什么**：不改规范库（`INT-815`、`INT-215`、`LSP-907` 的修订稿另交用户亲自批准）、不改阶段门禁与 `doc_consistency.py`、不删任何文件（根 PRD 的 4 个源文件仍留作未使用文件）、不动 DJ 项目、不推送、不合并 main。
6. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差；此前所有受治理卡均严格全绿（未使用）。
7. **演练事实（非治理，草稿工作树，不是正式证据）**：2026-10-15 在基线（卡 141 的提交）的临时工作树里跑了一遍本卡的快速门禁与判卷（原始输出在 `.auto-pm/reports/m3-prdl2/gates_rehearsal/`）：真实端到端模板测试 28 个全过、真实命令行在生成工程上的三种场景、静态检查、6 个真实变异全部被抓住并按字节还原、真实 pre-commit 钩子对暂存的 7 个文件退出 0；九组回归用合成输出（卡 139 的受治理输出按期望增量调整）判卷，G1–G9 全 PASS，4 个反例变体判卷结果符合预期。九组真实回归不在演练里跑；演练不是正式证据，正式 Run 完整重跑。

## 2. 单一目标与完成定义

驾驶舱按用户裁决的三层分工工作：缺 PRD 目录的 PLC 项目补到 `00_程序方案/`；方案级接口文档与代码的实例、FC、交换区契约有只警告的对照；模板的交换区表头协议开放、带单位列；九组回归只多出本卡的新用例（plc 组 +19、rest 组 +2）。技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、4 个已改文件的基线 blob 等于冻结哈希、3 个计划新增路径在基线上不存在、卡 141 的 Run/Work 为 SUCCEEDED/CLOSED、CHG-DOCU-2026-047 completed。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **机器负载**：启动前核对前台无游戏/启动器，近 10 秒 CPU 低；Windows 更新已由用户暂停至 2026-11-18。
4. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有续租成功。
5. **正式门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 1 小时 15 分钟（机器安静时）。

## 4. 精确 Owned Paths（7）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/checker.py` | 存在 | 在文档一致性检查之后调用方案级对照（只警告）；导入一行 |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/repairer.py` | 存在 | 缺 PRD 目录时 PLC 项目补到 00_程序方案/，不再新建根 PRD/ |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/scheme_doc.py` | 计划新增 | 新增：方案级接口文档与代码的存在性对照（FB 实例、FC 调用、交换区契约），只警告 |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/00_程序方案/接口文档_INT.md.jinja` | 存在 | 交换区一览表头：协议改为开放列表、新增“单位”列（word16 或 byte） |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_template_plc.py` | 存在 | v15 扩表头断言；新增 v16（三项对照在生成工程上通过）、v17（多出的实例只警告） |
| 6 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_repairer_prd_location.py` | 计划新增 | 新增：5 个修复器位置用例 |
| 7 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_scheme_doc.py` | 计划新增 | 新增：14 个对照用例 |

出现第 8 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-prdl2/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；4 个已改文件的基线（`f4dea34c` 上的）blob SHA-256 在 `prdl2_config.json` 与启动脚本里冻结，3 个新增路径无基线。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/checker.py` | 存在 | `30f2da774023e9af38b49298be4b3232c1d32f42a0fd473573bd2b9eb2782687` |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/repairer.py` | 存在 | `d3257dd02d729665bca6e090409c199691c80631e995b64a16221cd7b4d5d623` |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/scheme_doc.py` | 计划新增 | `e398c69bb463a284ceef45def22c55d4f0f026d8fda96220adcbb58e6c087bf2` |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/00_程序方案/接口文档_INT.md.jinja` | 存在 | `5bca8ab025ab5b8c105059f3e82070be13864cb33f8430f3adc68a51cbe8aca7` |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_template_plc.py` | 存在 | `19ebdf17b5893c2ad70c7c98c5f0896a0e4f6a40f8a777b1e97b73bb36c47f62` |
| 6 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_repairer_prd_location.py` | 计划新增 | `70fdc34755014d6a034ab4764300e4b0c23319a1eab07614e8e73d0edfa5a92f` |
| 7 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_scheme_doc.py` | 计划新增 | `8b4c74e147984207f350c21ca854332a216e20e0d85018cb73b55162f1e9c2c7` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-prdl2/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `36e7dc90499659b0c425d73f9277dbf0ee98bff5d67536ba71d627ec42e0deb6`。G2 的基线是卡 139（M3-PRDLAYOUT1）受治理执行的九组真实输出（`.auto-pm/reports/m3-prdl2/baseline_g2/`，同一产品字节；其后只有台账与 WBS 的文档提交）；期望的增量为：plc 组 +19，rest 组 +2，其余各组不变。

| 工具 | SHA-256 |
|---|---|
| `adjust_counts.py` | `3be71108779dd23bcc742186b5048c82e6a0c29de6998e80318d5587dcda595f` |
| `commit_msg.template.txt` | `e90e19d2cb40820ce3fe7eb16b6adc648cd5081cd9203be9d1e9b8a90205e226` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `install_files.py` | `3021fca08971b35454cd249866cd5517641565b21bb4b414bac4bab52cad6aef` |
| `prdl2_config.json` | `b8dd7ae9e5e1dc0fbdfebbed735a7ab85e80e48c7efa3f8eb8618ab0663bd188` |
| `prdl2_gates.py` | `71b8eac3dbe75cf8b61feeba484501afff2b368125ef7c30467bfea794ccb6b1` |
| `prdl2_gates_all.sh` | `555d78ace49ab0ee2c74ad5f42f5788cea904d6907da3319b6d3d4bd70d9d992` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

## 6. 门禁矩阵

产品档。顺序：基线测量（身份、健康测试、插件身份）→ 安装冻结文件 → 快速门禁（健康测试、整份端到端模板测试、真实 `plc check` 在生成工程上的端到端、静态、6 个真实变异、四棵树、真实 pre-commit 钩子干跑）→ 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、4 个已改文件为基线字节、3 个新增路径不存在；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与卡 139 的受治理输出相比：失败集合为空、skip 数不变、无 ERROR，通过数恰好增加 plc +19、rest +2，其余不变。唯一容忍规则见 §1 第 6 条 |
| G3 | 端到端模板与真实命令行 | 整份 `test_pmf_template_plc.py` 28 个用例通过且无跳过；生成的工程 84 个文件、没有根 `PRD/`、有 FC 示例的 5 个文件；真实的 `plc check` 退出码 0，PRD 目录项指向 `00_程序方案`，三项方案级对照项都是 pass，插件 check 与 test 项通过；数据块里多出一个实例时 FB 实例项为警告并点名 `GlobalVars.fbStation2`、三项对照都没有失败，唯一的失败项是已有的变量文档一致性检查（新实例不在变量文档里，退出码 1）；删去方案级接口文档后退出码 1 且 `00_程序方案/接口文档_INT.md` 项失败；插件二进制 SHA-256 前后相同 |
| G4 | 静态 | `ruff check auto_pm tests` 干净；`mypy --platform win32 auto_pm` 干净；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 7 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 其他字节不变 | `auto_pm`、`templates`、`tests`、`scripts` 四棵树各自与基线的差异恰为冻结的文件（含变异还原之后）；`scripts` 无差异 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 7 个文件退出 0（临时索引） |
| G8 | 真实变异（6 个） | M1 只在文档里的实例不再被发现：两个对应用例失败；M2 修复器又建根 PRD/：位置用例失败；M3 注释里的调用被算作调用：注释用例失败；M4 检查器不再运行对照：v16、v17 失败；M5 表头丢了单位列：v15 失败；M6 缺失的负责块不再被发现：契约用例失败；每个变异后文件按字节还原 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-15 说“按照计划开始今天的任务，预授权给你。11:00汇报进度”，此前 2026-10-14 裁决“根 PRD/ 不再生成；02_PLC程序/PLC_ST/00_程序方案/，保留这个”、要求高内聚低耦合，并让我裁决云端建议（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt`）；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

0. 启动前核对本机负载：无游戏/启动器在前台，近 10 秒 CPU 占用低；有则等待，不启动。
1. 在聊天报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 的 SCPT/OPT 变更单、匹配 Decision（`DEC-<当天>-M3PRDL02`）、Work `WORK-SW008-M3-PRDL2-001`、Run `RUN-SW008-M3-PRDL2-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-prdl2`，分支 `codex/m3-prdl2-cockpit`。
4. 安装冻结字节并完整重跑门禁（`prdl2_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单；不推送。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 6 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；插件缺失或版本不符；需要改这 7 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；同一问题两次未解就通知用户（用户切 Opus 诊断）；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；开发期与演练原始输出（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录。

## 11. 限制与后续

提交在本地分支 `codex/m3-prdl2-cockpit`（卡 141 的提交之上），**本卡不推送**。之后：台账与 WBS 回写；推送并读 CI；规范 `INT-815`、`INT-215`、`LSP-907` 的修订稿交用户亲自批准；`M3-D02B`。
