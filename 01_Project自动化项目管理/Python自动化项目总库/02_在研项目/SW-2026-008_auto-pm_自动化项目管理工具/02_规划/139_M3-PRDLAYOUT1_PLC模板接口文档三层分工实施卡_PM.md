# M3-PRDLAYOUT1｜PLC 模板接口文档三层分工实施卡（M3-PRDLAYOUT 第 1 张）

> 卡片编号：`CARD-SW008-M3-PRDLAYOUT1`
> 版本：`V1.0`（2026-10-14；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-14 说“我裁决，根 PRD/ 不再生成；02_PLC程序/PLC_ST/00_程序方案/，保留这个”，并回答三个问题、要求高内聚低耦合，另说“按照规划继续任务”；本卡 SHA 先在聊天报出再启动；条件见 §7；**不含推送，不含规范库修订**）
> 档次：**产品档**（分档器：`templates/…` 命中 PRODUCT-TEMPLATES，`tests/…` 命中 TESTS-TREE，取最高档；不得降级）
> 依赖：卡 138（M3-WBS22）的 Run/Work 已达技术终态且 CHG-DOCU-2026-046（SYS-2026-001）已收口（由启动脚本核验）
> 隔离基线：`19eb76c36288a6b216d61ed6ad1165885597ea4a`（卡 138 的提交，本地分支 `codex/m3-wbs22-v3038`，同时是已推送线 `origin/codex/m2-gov-wbs9-attest` 的尖端）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-14）

1. **为什么**：用户 2026-10-14 对 PLC 接口文档的裁决（设计稿 `.auto-pm/reports/M3_PRDLAYOUT_DESIGN_20261014.md`，WBS §4.7.23，台账 TD-SW008-131、138）：FB、FC 各有独立接口文档；方案级接口文档只写 FB 实例表（FB 类型名 + 实例名 + 一句话用途）、FC 调用表与跨系统交换区契约；根 `PRD/` 不再生成，`PLC_ST/00_程序方案/` 是标准位置；硬要求高内聚、低耦合；先只改 PLC。
2. **做什么**（3 个已有文件改、5 个文件新增；见 §4）：
   - **`copier.yml`**：`_exclude` 加入 `/PRD`——新工程不再生成根 `PRD/`（需求、接口、详细设计、技术方案四份占位文档）。四个源文件**留在模板里作为不用的死文件**：卡工具包目前只会改与增，不会删路径（TD-SW008-131）；工具包获得删除能力时一并删除；
   - **方案级 `接口文档_INT.md.jinja`** 重写为三部分：**FB 实例表**（三个实例：`FB_3001_ExternalInteraction` → `GlobalVars.fbExternalDevice`，`FB_1001_Station1` → `GlobalVars.fbStation1`，`FB_2001_CommonAlarm_AllStation` → `GlobalVars.fbCommonAlarm`，各带一句话用途与块级接口文档路径）、**FC 调用表**、**跨系统交换区契约**（一览表头：对象、协议、地址区间、总字数、本机写区、对方写区、本机侧承载变量、负责的块；字定义只在 3.1 一处，附写法示例；地址写成 `Dxxx–Dyyy` 的占位，不照搬任何厂牌的具体地址；指向机器可读的 `communications.yml`）；
   - **最小 FC 示例** `06_公共函数/FC_4001_ScaleAnalog.scl`：模拟量原始值（0..27648）线性换算为工程量，纯函数、不读写任何全局变量、默认不被任何块调用；连同使用说明、变更记录、接口文档、详细设计四份块级文档（`.md.jinja`，与 FB 的块级文档同形）；
   - **`tests/e2e/test_pmf_template_plc.py`**：文件清单钉死 83 → 84（去掉根 `PRD/` 四个文件，加 FC 的五个文件）；“缺接口文档”反例改为删 `00_程序方案/接口文档_INT.md`、期望失败项 `00_程序方案/接口文档_INT.md`；新增三个用例：v13 根 `PRD/` 不再生成且 `find_prd_dir` 返回 `00_程序方案`、v14 方案级 INT 的 FB 实例表与 `GlobalVars.db` 声明的实例**恰好相同**、v15 INT 含 FC 表与交换区契约且不重复块级参数明细。
3. **开发期实测**（开发工作树，非治理）：生成的工程 84 个文件，没有根 `PRD/`；静态检查零失败（含 FC 的块级文档一致性、结构规则）；真实插件 `check`、`test` 退出码 0（FC 示例是合法 SCL）；`tests/e2e/test_pmf_template_plc.py` 26 个全过；`tests/plc`（含影子文件守护）等相关用例 337 个全过。
4. **本卡带来的、用户应当知道的后果**：
   - 新建的 PLC 项目不再有根 `PRD/`；驾驶舱继续接受它作为历史位置（`find_prd_dir` 先根后 `00_程序方案`），所以已有项目（DJ-2026-009、011）不受影响；
   - 修复器仍会把缺的文档补到根 `PRD/`——这由第 2 张卡（驾驶舱卡）改；
   - “方案级 INT 与代码里的实例一一对应”的驾驶舱检查是第 2 张卡；本卡只用测试 v14 在模板内钉住这一点。
5. **不做什么**：不改驾驶舱产品代码、不改规范库（`INT-815`、`INT-215`、`LSP-907` 的修订稿另交用户批准）、不删模板里任何文件、不动 DJ-2026-005、009、011、不推送、不合并 main。
6. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差；此前所有受治理卡均严格全绿（未使用）。
7. **演练事实（非治理，草稿工作树，不是正式证据）**：2026-10-14 在基线（卡 138 的提交）的临时工作树里安装冻结文件后跑了本卡的快速门禁脚本（原始输出在 `.auto-pm/reports/m3-prdl1/gates_rehearsal/`）：基线与候选的健康测试相同；整份端到端模板测试 26 个全过且无跳过；生成的工程 84 个文件、没有根 PRD/、有 FC 示例的 5 个文件；真实 `plc check` 退出码 0（PRD 目录项指向 00_程序方案，没有以 PRD/ 开头的检查项，插件 check 与 test 项通过），删去方案级接口文档后退出码 1 且对应项失败；`ruff` 与 `mypy` 干净；5 个真实变异各被预期测试杀死并按字节还原；四棵树的差异恰为冻结的文件；真实 pre-commit 钩子对暂存的 8 个文件退出 0；九组用合成输出（卡 136 的输出副本，rest 组通过数 +3 调整）走判卷，G1–G9 全 PASS，4 个反例变体判卷结果各符合预期。演练不是正式证据，正式 Run 完整重跑。

## 2. 单一目标与完成定义

PLC 标准模板生成的新工程符合用户裁决的三层分工：没有根 `PRD/`、方案级 INT 是实例表 + FC 表 + 交换区契约、带一个最小 FC 示例，并且被测试钉住；驾驶舱九组回归只多出本卡的 3 个新用例（rest 组 +3）。技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、3 个已改文件的基线 blob 等于冻结哈希、5 个计划新增路径在基线上不存在、卡 138 的 Run/Work 为 SUCCEEDED/CLOSED、CHG-DOCU-2026-046 completed。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **机器负载**：启动前核对前台无游戏/启动器，近 10 秒 CPU 低；Windows 更新已由用户暂停至 2026-11-18。
4. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有续租成功。
5. **正式门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 1 小时 15 分钟（机器安静时）。

## 4. 精确 Owned Paths（8）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/copier.yml` | 存在 | `_exclude` 加入 `/PRD`：根 PRD/ 不再生成（源文件留作死文件） |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/00_程序方案/接口文档_INT.md.jinja` | 存在 | 方案级接口文档重写：FB 实例表、FC 调用表、跨系统交换区契约（含字定义的写法示例） |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/06_公共函数/FC_4001_ScaleAnalog.scl` | 计划新增 | 新增：最小的模拟量原始值换算 FC 示例（纯函数，默认不被调用） |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/06_公共函数/PRD/使用说明_UM-FC4001-ScaleAnalog.md.jinja` | 计划新增 | 新增：FC 示例的使用说明 |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/06_公共函数/PRD/变更记录_CHG-FC4001-ScaleAnalog.md.jinja` | 计划新增 | 新增：FC 示例的变更记录 |
| 6 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/06_公共函数/PRD/接口文档_IFC-FC4001-ScaleAnalog.md.jinja` | 计划新增 | 新增：FC 示例的块级接口文档（VAR_INPUT 三个参数与返回值） |
| 7 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/06_公共函数/PRD/详细设计说明书_DSN-FC4001-ScaleAnalog.md.jinja` | 计划新增 | 新增：FC 示例的详细设计说明书 |
| 8 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_template_plc.py` | 存在 | 文件清单钉死 83 → 84；根 PRD 相关断言改到 00_程序方案/；新增 v13～v15 三个用例钉住三层分工 |

出现第 9 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-prdl1/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；3 个已改文件的基线（`19eb76c3` 上的）blob SHA-256 在 `prdl1_config.json` 与启动脚本里冻结，5 个新增路径无基线。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/copier.yml` | 存在 | `307fb107847a62069d247b5f172140764090f1242b02185016918c36624b9eeb` |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/00_程序方案/接口文档_INT.md.jinja` | 存在 | `b8e6b0c3f32123486e4962bfd11496e14048c9261a9b8f2dcb17bbbe64fb99d5` |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/06_公共函数/FC_4001_ScaleAnalog.scl` | 计划新增 | `ae90e16b6dbe6dbe0fa0b00621680539d11cd22c51bf3597cb7c3905fb1808cc` |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/06_公共函数/PRD/使用说明_UM-FC4001-ScaleAnalog.md.jinja` | 计划新增 | `7956f232cdb9b1f6b2ee8d30d3a954dc341ecfa1fe52f5a00a31f68310ace7c7` |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/06_公共函数/PRD/变更记录_CHG-FC4001-ScaleAnalog.md.jinja` | 计划新增 | `6161cdaa0ca18e364a507e7e884e86f70afe48c45d36d3b0a701abc769595a18` |
| 6 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/06_公共函数/PRD/接口文档_IFC-FC4001-ScaleAnalog.md.jinja` | 计划新增 | `3cc8efca4405a4125ce7a9dd6175e7138504a1307f9e0044d121cc14d9aa3379` |
| 7 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/06_公共函数/PRD/详细设计说明书_DSN-FC4001-ScaleAnalog.md.jinja` | 计划新增 | `bd8b2eb42fdeb60115039400256e8093320c02c24feb589254b8e995694020f6` |
| 8 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_template_plc.py` | 存在 | `af5e9060589b249afcf1f0680a59a00884db0ce61631df1989309f6a7052d208` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-prdl1/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `617ddd37d4aa2ad55954c185bb3aa7ce3be2b582236d3d94e3c51217fac298d9`。G2 的基线是卡 136（D02）受治理执行的九组真实输出（`.auto-pm/reports/m3-prdl1/baseline_g2/`，同一产品字节；其后只有台账与 WBS 的文档提交）；期望的增量为：rest 组 +3，其余各组不变。

| 工具 | SHA-256 |
|---|---|
| `adjust_counts.py` | `3be71108779dd23bcc742186b5048c82e6a0c29de6998e80318d5587dcda595f` |
| `commit_msg.template.txt` | `d2d64506868dccddac2b855ec457a56bf316030b2292b9310c54e53490724d2b` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `install_files.py` | `9a8f4ab55e00cdd5d764f65aee63450247d5aefca9c5a84b49a3b6c30893e286` |
| `prdl1_config.json` | `e195af4e0756464a106b3d889e6e6ac23933dac547a0533e9f5454253bfe5de2` |
| `prdl1_gates.py` | `5503951c19f39c44499b3c45d99cb5234da90d9509a7da66a8e0d7471d2a2bef` |
| `prdl1_gates_all.sh` | `f0e256a609311118df7e10aeec68d9f0678070ec5aa2a2f4176bb0b04821fd67` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

## 6. 门禁矩阵

产品档。顺序：基线测量（身份、健康测试、插件身份）→ 安装冻结文件 → 快速门禁（健康测试、整份端到端模板测试、真实 `plc check` 在生成工程上的端到端、静态、5 个真实变异、四棵树、真实 pre-commit 钩子干跑）→ 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、3 个已改文件为基线字节、5 个新增路径不存在；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与卡 136 的受治理输出相比：失败集合为空、skip 数不变、无 ERROR，通过数恰好增加 rest +3，其余不变。唯一容忍规则见 §1 第 6 条 |
| G3 | 端到端模板与真实命令行 | 整份 `test_pmf_template_plc.py` 26 个用例通过且无跳过；生成的工程 84 个文件、没有根 `PRD/`、有 FC 示例的 5 个文件；真实的 `plc check` 退出码 0，PRD 目录项指向 `00_程序方案`，没有以 `PRD/` 开头的检查项，插件 check 与 test 项通过；删去方案级接口文档后退出码 1 且 `00_程序方案/接口文档_INT.md` 项失败；插件二进制 SHA-256 前后相同 |
| G4 | 静态 | `ruff check auto_pm tests` 干净；`mypy --platform win32 auto_pm` 干净；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 8 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 其他字节不变 | `auto_pm`、`templates`、`tests`、`scripts` 四棵树各自与基线的差异恰为冻结的文件（含变异还原之后）；`auto_pm`、`scripts` 无差异 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 8 个文件退出 0（临时索引） |
| G8 | 真实变异（5 个） | M1 根 PRD/ 又被生成：v13、v01 失败；M2 实例表里写错实例名：v14 失败；M3 缺交换区契约一节：v15 失败；M4 FC 示例不是合法 SCL：v09 失败；M5 FC 块级接口文档少一个参数：v03 失败；每个变异后文件按字节还原 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-14 说“我裁决，根 PRD/ 不再生成；02_PLC程序/PLC_ST/00_程序方案/，保留这个”，并回答三个问题、要求高内聚低耦合，另说“按照规划继续任务”（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt`）；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

0. 启动前核对本机负载：无游戏/启动器在前台，近 10 秒 CPU 占用低；有则等待，不启动。
1. 在聊天报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 的 SCPT/OPT 变更单、匹配 Decision（`DEC-<当天>-M3PRDL01`）、Work `WORK-SW008-M3-PRDL1-001`、Run `RUN-SW008-M3-PRDL1-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-prdl1`，分支 `codex/m3-prdl1-template`。
4. 安装冻结字节并完整重跑门禁（`prdl1_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单；不推送。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 6 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；插件缺失或版本不符；需要改这 8 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；同一问题两次未解就通知用户（用户切 Opus 诊断）；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；开发期与演练原始输出（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录。

## 11. 限制与后续

提交在本地分支 `codex/m3-prdl1-template`（卡 138 的提交之上），**本卡不推送**。之后：台账与 WBS 回写；推送并读 CI；第 2 张卡（驾驶舱：修复器补到 `00_程序方案/`、只警告的“方案级 INT 与代码实例一一对应”检查）；规范 `INT-815`、`INT-215`、`LSP-907` 的修订稿交用户批准。
