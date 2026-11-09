# M3-TPL1｜PLC 模板修复实施卡（让模板通过插件的 check 与 test）

> 卡片编号：`CARD-SW008-M3-TPL1`
> 版本：`V1.0`（2026-10-13；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / AWAITING-APPROVAL`（用户 2026-10-13 说“同意按这个方案做，先出修模板那张卡”；本卡 SHA 在聊天报出，**待用户批准后才启动**；条件见 §7；**不含推送**）
> 档次：**产品档**（分档器：`templates/…` 命中规则 PRODUCT-TEMPLATES；不得降级）
> 依赖：卡 123（M3-V08）的 Run/Work 已达技术终态且 CHG-SCPT-2026-411 已收口（由启动脚本核验）
> 隔离基线：`dcfca387f8112b55e14156d0eaf3d4e5ffc04f78`（卡 123 的提交，本地分支 `codex/m3-v08-template-plc`，已推送为 `origin/codex/m2-gov-wbs9-attest` 的尖端）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-13，只读勘测）

1. **为什么**：用户的 PLC 门禁实际依赖 VS Code 插件 Dynamic Siemens Language Support。插件安装目录自带命令行 `siemens-lsp`（`check` 做诊断，`test` 跑 `.scltest`，有错退出码为 1）。用它检查驾驶舱模板 `plc-standard-project` 生成的标准项目（配上真实的 `01_SharedLibraries`），**`check` 报 17 个错误、退出码 1，`test` 退出码 1**；而驾驶舱自己的 `plc check` 对同一工程全绿。模板自身通不过用户的真实门禁，按 AGENTS 第 4 条从源头产线修。
2. **缺陷与修法**（勘测时在草稿目录里逐项验证，非治理）：
   - `FB_1001_Station1.scl.jinja` 在功能块体内写了裸的 `CONST … END_CONST` 块（插件报 7 个语法错误）；同项目的 `FB_2001` 已在用合法写法 `VAR CONSTANT … END_VAR`。→ 把这一块改为 `VAR CONSTANT … END_VAR`，其余不动。
   - `basic_test.scltest.jinja`、`interlock_test.scltest.jinja` 引用 `GlobalVars.stGlobal.bPowerOn`、`bEmergencyStop`、`bAutoRunning`、`bSafetyLight`，而 `ST_CommonAlarm` 没有这些成员（插件报 10 个错误）。→ 改为经真实成员练公共报警功能块：basic 用例“拉高输送机报警码 → 任意报警激活为真；清零并复位 → 为假”，interlock 用例“输送机报警 5、取放料报警 2 → 当前最高优先级报警码为 2”。
   - **修测试时暴露了一个真实功能缺陷**：`FB_2001_CommonAlarm_AllStation.scl` 的复位分支在把输出写回结构体之前就 `RETURN`，所以复位周期里结构体输出保持复位前的旧值（basic 用例的“复位后为假”断言在原逻辑上失败，得到 `true`）。→ 在 `RETURN` 之前补写与块末尾完全相同的 8 条输出回写。
3. **验证口径**：修后在同一勘测里 `check` 退出码 0（0 个错误）、`test` 退出码 0（2 个用例都通过）。正式门禁用同一条命令行、固定插件版本 2.17.2、记录二进制的 SHA-256，并先在基线模板上证明“修前确为 17 个错误、退出码 1”。
4. **不做什么**：
   - 不改产品代码与测试代码，不改模板文件集（静态影子文件 `FB_1001_Station1.scl` 等的删除是 TD-SW008-131，另卡）；
   - 不把插件接入驾驶舱门禁（下一张卡）；不改 V08 测试（第三张卡再收紧）；不动 Obsidian 规范库；不推送；
   - 不处理 `SysLib` 共享库在插件测试转译时的“31 处未解析变量引用”（来自库自身的 `i_stCmd.*`，不影响本卡的 `check`/`test` 结果，另行登记）。
5. **公开的局限**：插件的 `check` 对“空文件、乱码单文件”同样报 0 诊断（勘测实测），这一类由驾驶舱自己的结构检查补（TD-SW008-129 的后续卡）；本卡的门禁需要本机装有该版本插件，缺失即失败（不是“通过”）。
6. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差；此前所有受治理卡均严格全绿（未使用）。
7. **演练事实（非治理，草稿工作树，不是正式证据）**：2026-10-13 在基线 `dcfca387` 的临时工作树里跑了本卡的快速门禁脚本（原始输出在 `.auto-pm/reports/m3-tpl1/gates_rehearsal/`）：基线模板生成的工程 `check` 退出码 1、17 个错误，`test` 退出码 1；候选模板生成的工程 `check` 退出码 0、0 个错误，`test` 退出码 0、2/2 个用例；插件 2.17.2 二进制 SHA-256 前后相同；三个插件负向对照各被拒绝（M1 `check` 18 个错误、M2 `test` 非零、M3 `check` 11 个错误）；四棵树核对只差这 4 个文件；真实 pre-commit 钩子对暂存的 4 个文件退出 0；九组用合成输出（基线输出的副本）走判卷，G1–G9 全 PASS，3 个反例变体判卷结果各符合预期。演练不是正式证据，正式 Run 完整重跑。

## 2. 单一目标与完成定义

模板生成的标准项目通过插件命令行 `check` 与 `test`（退出码 0），且驾驶舱自己的九组回归与基线逐项相同。技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、四个文件的基线 blob 等于冻结哈希、卡 123 的 Run/Work 为 SUCCEEDED/CLOSED、CHG-SCPT-2026-411 completed、插件 2.17.2 已安装。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`。
4. **正式门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 2 小时 40 分钟（九组回归约 2 小时 35 分钟）。

## 4. 精确 Owned Paths（4）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/02_工位1_动作机构/FB_1001_Station1.scl.jinja` | 存在 | 功能块 FB_1001 的步序常量：无效的 CONST…END_CONST 块改为 VAR CONSTANT…END_VAR（4 行改动内的 2 行） |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/05_公共报警/FB_2001_CommonAlarm_AllStation.scl` | 存在 | 公共报警块：复位分支在 RETURN 前补写 8 个输出的回写（含一行说明注释） |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/Test/basic_test.scltest.jinja` | 存在 | 集成测试 basic：改用 ST_CommonAlarm 的真实成员（报警触发与复位） |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/Test/interlock_test.scltest.jinja` | 存在 | 集成测试 interlock：改为报警优先级联锁（最小报警码优先） |

出现第 5 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-tpl1/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；四个文件的基线（`dcfca387` 上的）blob SHA-256 在 `tpl1_config.json` 与启动脚本里冻结。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/02_工位1_动作机构/FB_1001_Station1.scl.jinja` | 存在 | `5b23da8a4a178c5e48e9d6777699550abd3fb8cf80ca23766e58f0fe0dff4523` |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/05_公共报警/FB_2001_CommonAlarm_AllStation.scl` | 存在 | `2a88009d8081c8812e957ede736cfa44964dabf0cc514de070c50d4c038ef510` |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/Test/basic_test.scltest.jinja` | 存在 | `ca495fa7894a4d28f24e13c66e9ec0f621ea4d4a9bfc04cec3352dde78302850` |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/templates/plc-standard-project/template/02_PLC程序/PLC_ST/Test/interlock_test.scltest.jinja` | 存在 | `cc28ae1685bfd1fd4b45babd4176130ae40f546544e3807cce9a37d59f5f25a5` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-tpl1/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `5ea3ff53f0c6093d3ca2899127452ed1690a16a8931e217da2eadab1e5cb7031`。G2 的基线是卡 116 受治理执行的九组真实输出，其中 rest 组换成卡 123 受治理执行的 rest 输出（888 passed），汇总在 `.auto-pm/reports/m3-tpl1/baseline_g2/`。

| 工具 | SHA-256 |
|---|---|
| `commit_msg.template.txt` | `5f3f7d19ea7c93bf263c22395d9d707fd3984a25698a40595376f1f978bc11dd` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `install_files.py` | `b002b23777c72c3c28a228bb7264b2962c4fa38d9e749df525908a46691bb439` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |
| `tpl1_config.json` | `2fc8beb2fd69366660d1360d564f2838f9a010a2ebba7058513253b088475dd0` |
| `tpl1_gates.py` | `01c42e72fac2e041b2ec6bcc96b1bc8c90b4c759616b6f8be0bfd15ba182bcbc` |
| `tpl1_gates_all.sh` | `96a68fb13c54d51b31ea8cc920a4460acc6c0ff2bd52065dd45f21e9340a513b` |

## 6. 门禁矩阵

产品档。顺序：基线测量（身份、健康测试、**插件在基线模板生成的工程上的 check 与 test**）→ 安装冻结文件 → 快速门禁（健康测试、插件在候选模板生成的工程上的 check 与 test、三个插件负向对照、四棵树、真实 pre-commit 钩子干跑）→ 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、四个文件为基线字节；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与基线九组输出（卡 116，rest 组取卡 123）逐项相同（失败集合、通过数、skip 数、无 ERROR）；本卡不改任何测试字节，所以任何差异都是失败。唯一容忍规则见 §1 第 6 条 |
| G3 | 插件命令行：修前与修后 | 基线模板生成的工程：`check` 退出码非零且恰为 17 个错误、`test` 退出码非零；候选模板生成的工程：`check` 退出码 0 且 0 个错误、`test` 退出码 0 且跑了 2/2 个用例、无 FAIL；插件二进制 SHA-256 前后相同 |
| G4 | 修复内容与静态 | 生成工程里：FB_1001 无裸 CONST 块且有 VAR CONSTANT；FB_2001 复位分支回写输出（该赋值出现两次）；测试不再含 bPowerOn 等不存在的成员；无残留占位符；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 4 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 其他字节不变 | `auto_pm`、`tests`、`scripts` 与基线逐字节相同；`templates` 只差这 4 个文件 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 4 个文件退出 0（临时索引） |
| G8 | 插件负向对照（3 个，在生成工程的临时副本上） | M1 把裸 CONST 块放回 FB_1001：`check` 必须非零退出；M2 删掉复位分支的输出回写：`test` 必须非零退出；M3 让测试引用不存在的成员：`check` 必须非零退出 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-13 说“同意按这个方案做，先出修模板那张卡”（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt`）；**须用户在看到本卡 SHA 后明确批准才启动**；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与摘要，**等用户批准**。
2. 批准后创建 SW-2026-008 SCPT/OPT 变更单、匹配 Decision（`DEC-<当天>-M3TPL101`）、Work `WORK-SW008-M3-TPL1-001`、Run `RUN-SW008-M3-TPL1-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-tpl1`，分支 `codex/m3-tpl1-plc-template`。
4. 安装冻结字节并完整重跑门禁（`tpl1_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 6 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；插件缺失或版本不符；需要改这 4 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；同一问题两次未解就通知用户（用户切 Opus 诊断）；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；勘测与演练原始输出（非治理）；正式独立门禁与证据（含插件版本与二进制哈希、修前修后的插件原始输出）；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录。

## 11. 限制与后续

提交在本地分支 `codex/m3-tpl1-plc-template`（卡 123 的提交之上）；推送需要用户另行授权。之后：卡 125——把插件的 `check`、`test` 接入驾驶舱 `plc check` 与阶段门禁（找不到插件为“未验证”，交付阶段为失败）；卡 126——收紧 V08 测试（模板生成的工程 `check`、`test` 退出码 0）并更正 AGENTS 中“语法白名单”的措辞；TD-SW008-130、131 各一张小卡。
