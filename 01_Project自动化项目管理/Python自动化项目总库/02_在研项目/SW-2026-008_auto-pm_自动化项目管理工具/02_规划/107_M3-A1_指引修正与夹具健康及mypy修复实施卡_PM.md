# M3-A1｜指引修正、夹具健康与 mypy 重名修复实施卡

> 卡片编号：`CARD-SW008-M3-A1`
> 版本：`V1.0`（2026-10-11；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-11 说“可以，按这个排期，预授权给你，授权有效时间截止到下午5:00pm.”，授权含 D01、TD-SW008-042、Q03，并要求“替我收口验收”；本卡 SHA 先在聊天报出再启动；条件见 §7）
> 档次：**核心档**（分档器：`AGENTS.md`、`.agent/rules/project-rule.md`、`.cursor/rules/workspace-ai-coexistence.mdc` 无匹配规则，按“未知路径=核心”处理；`pyproject.toml` 属产品档；操作手册属文档档；测试文件属测试档。取最高档=核心，不得降）
> 依赖：卡 106（M2-GOV-CIBASE）的 Run/Work 已达技术终态且 CHG-SCPT-2026-405 已收口（由启动脚本核验）
> 隔离基线：`620e75972fdcc605b5d7e74c8cdae072c4358c6d`（卡 106 的提交，本地分支 `codex/m2-cibase-refresh`，也是已推送的远端尖端）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-11）

本卡合并三个已排期、已核实的小缺陷（均在用户当日预授权范围内），共 6 个文件、全部为既有文件的修改：

1. **D01 日常指引与薄适配（4 个文件）**
   - `AGENTS.md` 有被转义吃坏的文字：DEV-ENC-001 一行里 `errors=` 后夹带一个回车符并丢了反引号；“子代理零负担自闭环约束”一行里 `send_message` 与检查命令被反斜杠和一个响铃符（0x07）包住，读不出命令名；“阶段 3【验收】”一行仍写“PM_SESSION 仅按需刷新项目摘要”，与用户 2026-10-10 的 PM_SESSION 退役裁决相冲突。修法：三行改为可读、正确的文字（见 §5.3），并在真源索引表加一行指向当前计划（WBS）。
   - `.agent/rules/project-rule.md`、`.cursor/rules/workspace-ai-coexistence.mdc` 是只引用不维护的薄适配入口：各加同一行“当前计划与状态投影”指向 WBS（V3.0.28 之后以其“当前投影”为准），不改其他内容。
   - 操作手册 `36_…日常迭代操作手册_PM.md`：头部固化的运行版本 `1.3.3-d8f7c8b` 早已不是当前版本（active 为 `1.3.3-4b5c630`），改为指向运行时的版本查询命令与 `active_release.json`；“PM_SESSION 只是人工可读项目摘要”改为已退役表述；末尾新增 §9“受治理实施卡的标准动作”（命令名均取自受治理流程里实际使用的命令）。
2. **TD-SW008-042**：`tests/qml/test_file_watcher_bridge.py` 的 `test_completed_real_pool_worker_does_not_retain_its_gui_bridge` 在 `finally` 里把 `assert pool.waitForDone(10_000)` 放在 `if retained is not None:` 内，被 `tests/test_fixture_health.py::test_no_conditional_assertion_skips`（AST 判据：`if … is not None` 的分支体含 assert）判为条件断言跳过。这是 rest 组在 Windows 上唯一剩下的既存失败（卡 101 的受治理输出：1 failed / 854 passed / 13 skipped）。修法：`pool_done = True` 先赋值，分支内改为 `pool_done = pool.waitForDone(10_000)`，`assert pool_done` 放在分支之外；清理动作与顺序不变，原有断言语义不变（保留对象时仍必须等到线程池结束）。
3. **Q03**：`pyproject.toml` 的 `[tool.mypy]` 里 `exclude = []`。在项目根运行 `mypy .` 时，模板里的 `templates/python-tool/template/tests/__init__.py` 与项目的 `tests/__init__.py` 重名（Duplicate module named "tests"），mypy 在发现阶段就中止，**一个文件都没检查**。修法：`exclude` 改为排除模板的 tests 目录（正则 `^templates/python-tool/template/tests/`），其余设置不动。

**必须如实说明的局限（Q03）**：这个修法只让 `mypy .` “能跑完”，不让它“变绿”。2026-10-11 的只读试验（卡 106 的提交上，证据 `.auto-pm/reports/m3-a1/q03_trial_exclude.txt`）显示：加了排除之后 `mypy .` 跑完 511 个源文件，报告 **273 个既存错误、分布在 89 个文件**（`scripts/` 101、`tests/` 109、`auto_pm/` 63）。其中 `auto_pm/` 的 63 个里有 57 个是 `getLogger` 之类的假错误：用 `mypy .` 发现模块时，名为 `logging` 的目录（`auto_pm/infrastructure/logging`、`tests/logging`）遮蔽了标准库 `logging`；加 `--explicit-package-bases` 试过一次，结果不变（`q03_trial_epb.txt`），按“同一问题最多两轮”的止损规则不再尝试。项目真正的类型门禁是 `mypy auto_pm`（244 个文件，零问题），本卡不动它。所以 Q03 的结论是“中止缺陷已修复；`mypy .` 的残留噪声另登记为新技术债（TD-SW008-122），不在本卡处置”。

4. **没有任何产品代码改动**：`auto_pm/` 与 `templates/` 与基线逐字节相同（G6 核对）。因此九组回归的结果应与卡 098 V1.1 的受治理输出一致，rest 组只多出已知的 24 个通过（9 个来自卡 093 的变更单跟踪测试，14 个来自卡 101 入库的真实样例，1 个是本卡修好的 TD-SW008-042），且**没有任何失败**。
5. **为什么是核心档、而不是文档档加测试档**：分档器把 `AGENTS.md` 等入口文件视为未知路径，按核心档处理，规则文档规定不得降档。这意味着 §6 的九组回归与真实变异是必须的，即使没有产品代码改动。分档器要求的“真实进程并发/状态边界覆盖”一项：本卡不触及任何进程、状态或并发代码，由未改动的真实进程测试（`tests/e2e`、`tests/infrastructure`，都在九组之内）承担；这一判断在卡里写明，供审计复核。
6. **一个已公开的流程缺口**：卡 099 与卡 102 的路径按分档器应为产品档（变更单与勘误所在目录属产品配置类路径），当时按文档档做了门禁，没有为它们单独跑九组回归。本卡的九组回归在含这两张卡的树上完整重跑，等于补做；结果写进 G2 报告。
7. **演练事实（非治理，草稿工作树，不是正式证据；九组没有真跑）**：2026-10-11 在基线上的临时工作树里做了演练（原始输出在 `.auto-pm/reports/m3-a1/gates_rehearsal/`）。基线上夹具健康、冒烟、导入测试 27 个里恰有 1 个失败（`test_no_conditional_assertion_skips`）；装入冻结文件后 27 个全部通过；夹具健康整文件 2 passed、watcher 桥接测试文件 18 passed；`mypy .` 跑完 511 个源文件（273 个既存错误，89 个文件，无重名中止）；`mypy --platform win32 auto_pm` 为 “Success: no issues found in 244 source files”；真实 pre-commit 钩子对暂存的 6 个文件退出 0；两个真实变异均被杀死并按字节还原；文档合同的 7 个对照全部按预期。判卷脚本用合成的九组输出（八组取卡 098 V1.1 的受治理输出，rest 组为期望形态）判得 G1–G9 全 PASS；再用 5 个反例各判一次：rest 多一个无关失败、rest 通过数不对、rest 只有指定竞态测试失败而三次重跑都过（按规则通过，记偏差）、竞态测试的重跑有一次失败、core 组通过数被改，除第三个外全部被判 FAIL。**演练不能证明九组真实结果**，那只有正式 Run 才有。
8. **不做什么**：不改产品代码、不改其他测试、不改规则文档（`.trae/`、Obsidian）、不改 release 指针文件、不推送、不合并 main、不处置任何技术债或历史失败记录。

## 2. 单一目标与完成定义

三项缺陷在同一候选里同时修好：夹具健康测试整文件通过；`mypy .` 不再因重名中止；入口文件与操作手册可读、正确且指向当前计划。技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、6 个文件的基线 blob 等于冻结哈希、卡 106 的 Run/Work 为 SUCCEEDED/CLOSED、CHG-SCPT-2026-405 completed。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`。
4. **重门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 2 小时 40 分钟。

## 4. 精确 Owned Paths（6）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `AGENTS.md` | 存在 | 入口文档：去掉转义吃坏的字符与过时的 PM_SESSION 刷新提法，加当前计划指向行 |
| 2 | `.agent/rules/project-rule.md` | 存在 | 薄适配入口：加当前计划指向行 |
| 3 | `.cursor/rules/workspace-ai-coexistence.mdc` | 存在 | 薄适配入口：加当前计划指向行 |
| 4 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/36_驾驶舱与双技术栈日常迭代操作手册_PM.md` | 存在 | 操作手册：去掉固化的旧版本号、对齐 PM_SESSION 退役表述、新增 §9 实施卡标准动作 |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/qml/test_file_watcher_bridge.py` | 存在 | TD-SW008-042：把 assert 移出条件分支（只改一个 finally 块） |
| 6 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/pyproject.toml` | 存在 | Q03：`[tool.mypy]` 的 `exclude` 由空列表改为排除模板 tests 包（仅此一行） |

出现第 7 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-a1/`、本卡文件、演练工作树）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；基线（`620e7597` 上的）blob SHA-256 在 `ma_config.json` 与启动脚本里冻结。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `AGENTS.md` | 存在 | `a6f2d7f08b29adf6696427eed7be6633d3afc195e13c52cdfccdb6a87d14efb3` |
| 2 | `.agent/rules/project-rule.md` | 存在 | `6e6d1ac2c1a7b0462bbd20dc46998f9fdb72d0dc7a84a97eadc7a8c052daae0b` |
| 3 | `.cursor/rules/workspace-ai-coexistence.mdc` | 存在 | `40bad0bfc707d62145ae654b9b4e74b0e8fa113a8545ea931f9e15513d04c193` |
| 4 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/36_驾驶舱与双技术栈日常迭代操作手册_PM.md` | 存在 | `127b865660b787bf6ecf7ff21c57d707cbb165b812e94816bea61e425103eb22` |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/qml/test_file_watcher_bridge.py` | 存在 | `72e06eb50659109253370d86cec443fd621f3907b9444b26b0c4e01ef65bb7b2` |
| 6 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/pyproject.toml` | 存在 | `bdc9f0d761a8c5327dfea3600b7e23cb8bd7bc64214fe787487c19596fd99c1e` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-a1/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `16f3cd92fbb0b6902cb17671e75141adadfbd3cdb827ce05bf97e994b6ce16c1`。G2 的基线取卡 098 V1.1 受治理执行的九组真实输出（`.auto-pm/reports/m2-cicd2/gates/g2_candidate/`，各文件 SHA-256 冻结在 `ma_config.json`）。

| 工具 | SHA-256 |
|---|---|
| `commit_msg.template.txt` | `ad78c45a6a944ca0ba35535c7f7864f7c09bc5b3e7dc56da226ca85a0ec3a011` |
| `install_files.py` | `94a9973f5c6f7cc3dbf561dade7b2c540b44c3e0e49a93014df20242326bfcd1` |
| `ma_config.json` | `436ba0d62e0011e72af820a2e5b0bf1a32589bc52a85ebdd881abe08285fc1b6` |
| `ma_gates.py` | `201c2e77dabd6274c6e47ec05994738f3b5bd260b2b99a2bb88efe9d1e00901f` |
| `ma_gates_all.sh` | `b3a1d092af0312b023b763f83b94bb9e599b82b474de3a224326846139446646` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

### 5.3 文档的字节合同（G6 机器核对）

只允许下列旧行被替换，其余旧行必须逐行保留且顺序不变；新增内容里必须出现列出的片段；文件不得含回车、BOM、NUL 或任何控制字符（制表与换行除外）、末尾必须是换行、不得含密钥形态的值。

| 文件 | 被替换的旧行（行首） | 新增内容必须含 |
|---|---|---|
| `AGENTS.md` | `4. **阶段 3【验收】**`、`在执行 Python 脚本读写…`、`执行代理在向 PM 或用户通过…` | `PM_SESSION 已退役（用户 2026-10-10 裁决）`、``encoding="utf-8", errors="replace"``、``send_message``、``main.py doc check``、`39_PM-Flow_恢复与可用化总方案_WBS_PM.md` |
| `.agent/rules/project-rule.md` | （无，仅在“治理基线”行之后插入一行） | `39_PM-Flow_恢复与可用化总方案_WBS_PM.md` |
| `.cursor/rules/workspace-ai-coexistence.mdc` | （无，仅在“治理基线”行之后插入一行） | `39_PM-Flow_恢复与可用化总方案_WBS_PM.md` |
| 操作手册 36 | `> 运行版本：`、`- PM_SESSION 只是人工可读项目摘要` | `active_release.json`、`PM_SESSION 已退役（用户 2026-10-10 裁决）`、`## 9. 受治理实施卡的标准动作`、``continuity checkpoint create``、``ledger reconcile <PID>`` |
| `pyproject.toml` | `exclude = []`（仅此一行；总行数不变） | `exclude = ["^templates/python-tool/template/tests/"]` |

## 6. 门禁矩阵

核心档。顺序：基线测量 → 安装冻结文件 → 快速门禁 → 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 夹具健康、冒烟、导入测试 | 基线：恰好一个既存失败（TD-SW008-042 的 `test_no_conditional_assertion_skips`）；候选：全部通过，通过数多 1、skip 数相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 八个稳定组与卡 098 V1.1 的受治理输出逐项相同（失败集合、通过数、skip 数、无 ERROR）；rest 组无任何失败且通过数 = 831 + 24 = 855、skip 数 13。**唯一容忍规则**（沿用已验收的卡 100 V1.1 的同一规则，写在卡内、事先声明）：如果 rest 组里恰有 `tests/e2e/test_pmf_recovery.py::test_r09_a_reader_never_fails_because_another_process_has_a_transaction_open` 一个失败，且它在同一候选字节里三次隔离重跑全部通过（TD-SW008-077/120 的瞬时竞态），则通过数需为 854、其余相同，并把这一偏差写入判卷记录；任何其他失败一律 FAIL |
| G3 | TD-SW008-042 与 Q03 的真实行为 | 夹具健康整文件通过；`tests/qml/test_file_watcher_bridge.py` 整文件通过；`mypy .` 不再出现 “Duplicate module named” 与 “prevented further checking”，且以 “Found N errors in M files (checked K source files)” 或 “Success” 结束（残留的既存错误不判失败，但如实记录条数）；`mypy --platform win32 auto_pm` 仍为零问题 |
| G4 | 静态检查 | 改动的测试文件 ruff 无问题；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 6 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 既有内容不变与文档合同 | `auto_pm` 与 `templates` 树与基线逐字节相同；`tests` 树只差改动的那一个文件；§5.3 的合同对 4 个文档与 `pyproject.toml` 全部满足 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 6 个文件退出 0（临时索引） |
| G8 | 真实变异与负向对照 | 把旧的条件断言写回，夹具健康的指定测试必须失败；把旧的空 `exclude` 写回，`mypy .` 必须再次中止；两个文件都按字节还原；文档合同的 7 个对照（控制字符重新注入、必需片段被删、未列出的旧行被改、密钥形态值注入、pyproject 第二行被改，以及两个正例）各被对应断言接受/拒绝 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-11 说“可以，按这个排期，预授权给你，授权有效时间截止到下午5:00pm.”（含 D01、TD-SW008-042、Q03），并已要求“替我收口验收”（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾）；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 SCPT/DEF 变更单、匹配 Decision（`DEC-<当天>-M3A10001`）、Work `WORK-SW008-M3-A1-001`、Run `RUN-SW008-M3-A1-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）；实际创建前验证未被占用。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-a1`，分支 `codex/m3-a1-guidance-fixes`。
4. 安装冻结字节并完整重跑门禁（`ma_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（上面 G2 写明的那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要改这六个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。**17:00 之后不启动任何新卡**（用户预授权的截止时间）。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始门禁（非治理）与真实钩子干跑；Q03 的两次只读试验原始输出；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录。

## 11. 限制与后续

提交在本地分支 `codex/m3-a1-guidance-fixes`（卡 106 的提交之上）；不推送（本卡之外的推送需用户另行授权）。后续：新技术债 TD-SW008-122（`mypy .` 的 273 个既存错误与 `logging` 目录遮蔽标准库）与 TD-SW008-123（控制根里已修改但未提交的 release 指针文件与它们记录的版本不一致）由随后的台账记录卡登记；`mypy .` 是否要变绿、变绿的范围，需用户另行裁决。
