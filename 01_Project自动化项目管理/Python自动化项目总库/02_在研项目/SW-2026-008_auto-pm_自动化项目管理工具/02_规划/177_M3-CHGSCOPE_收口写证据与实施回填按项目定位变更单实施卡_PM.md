# M3-CHGSCOPE｜收口写证据与实施回填按项目定位变更单实施卡（六个路径）

> 卡片编号：`CARD-SW008-M3-CHGSCOPE`
> 版本：`V1.1`（2026-10-20；取代 V1.0；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户预授权自行收口推送与合并；本卡 SHA 先在线程里报出；条件见 §7）
> 档次：核心（改产品代码），跑九组回归
> 依赖：上一张卡 RUN-SW008-M3-DOCSYNC-001 已达技术终态且 CHG-SCPT-2026-439 已收口（由启动脚本核验）
> 隔离基线：`f759716f2ed16b665d637d29ae6aa8751cb0d24d`（`main` 当前提交，含卡 176，本地分支 `codex/m3-main-chgscope-base`）
> 路径根：`.`
> 执行模型：Claude；独立审计由项目另开的云端会话做
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。时间均为亚利桑那时间（MST）。

## 1. 背景与已核实事实（2026-10-20）

1. **为什么**：卡 176 部署后，D08 第 1 道重做（SW-2026-010，功率因数与效率不大于 1）的代码、测试、变更单完成、Work 关闭与提交都已做到，但 Mission 收口写证据时 `SubstanceInjector._find_unique_change_file` 要求同号变更单在整个工作空间只有一份。变更单按项目编号，不同项目必然重名（实测全工作区 254 份 `CHG-SCPT-2026-002`），Mission 停在 ACCEPTED。实施回填 `SubstanceInjector.inject` 也取全工作区第一个同号文件，可能写进别的项目的变更单。
2. **做什么**：给了项目编号时，只在该项目根（按 `ChangeFileLocator.get_project_path` 定位，不进隐藏目录）下 `04_监控` 或 `11_监控` 的 `01_变更管理/01_变更单` 里找，排除 `archive`；收口仍要求恰好一份。收口服务把 Work 的 `subject_project_id` 传入；没给编号或定位不到项目时沿用原来的全工作区查找。新增 8 个测试，测试替身的 Work 补上项目字段。台账登记并偿还 TD-SW008-166，偿还 TD-SW008-164、165；WBS 写回。
3. **已验证**：在开发工作树里对真实工作区只读调用：按 SW-2026-010 定位到它自己的 `CHG-SCPT-2026-002`；不带项目编号时原检查照旧拒绝。同类的全工作区查找还有两处（决策服务的跨项目重号检查已按项目过滤并排除运行态工作树；关联变更单存在性检查只判断有无），本卡不改。
4. **不做什么**：不改变更单编号规则；不清理 `.auto-pm` 下的副本；不碰 SW-2026-010 的 Mission（修复部署后由 D08 重试收口）；不部署、不切换发布版本（另行，切换时用户确认）。
5. **你应当知道的事**：重试收口不需要人手改任何治理对象；第 1 道的 Mission 在新版本下重试 `close_accepted` 即可闭环。
6. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差。
7. **为什么有 V1.1**：V1.0 的正式 Run（`RUN-SW008-M3-CHGSCOPE-001`）G1～G9 全部通过（core 1205 通过 1 跳过，change +8），但提交时 commit-msg 钩子拒绝：提交说明正文里出现了第二个变更单号（举例写到的 `254 个同号文件`的那个编号），钩子要求生产代码提交只绑定一个变更单。按 §9 硬停止；V1.0 的 Run 已用有效租约转 FAILED、Work 转 CANCELLED，证据在 `.auto-pm/reports/m3-chgscope/v10/`。V1.1 只改提交说明（去掉第二个编号）与 Work/Run/Checkpoint/Decision 编号，6 个文件的字节与 V1.0 相同；变更单仍是 CHG-SCPT-2026-441；正式门禁完整重跑。
8. **演练事实（非治理，临时工作树，不是正式证据）**：2026-10-20 下午（MST）在基线 `f759716f` 的临时工作树里跑了基线测量、安装、快速门禁（含 4 个真实变异与真实提交钩子干跑）与判卷：九组回归用合成输出判卷，G1～G9 全 PASS；4 个反例变体的判卷结果符合预期。开发工作树里对真实工作区只读调用：按 SW-2026-010 定位到它自己的 CHG-SCPT-2026-002，不带项目编号时原检查照旧拒绝。演练不是正式证据，正式 Run 完整重跑。

## 2. 单一目标与完成定义

冻结的 6 个文件的字节被提交，九组回归只多出本卡的新测试；技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行；之后开 PR，独立审计通过且 CI 全绿后由 Claude 按用户授权合并；再另行构建新版本并切换（切换时用户一句话确认）。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、5 个修改文件的基线 blob 等于冻结哈希、新测试文件在基线不存在。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **机器负载**：启动前核对前台无游戏/启动器，近 10 秒 CPU 低；重载门禁不在 17:00～21:00（MST）跑，预计结束时间也不得落入该时段；开防休眠。
4. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有续租成功。
5. **正式门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 2 小时。

## 4. 精确 Owned Paths（6）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/change/substance_injector.py` | 存在 | 收口写证据与实施回填：给了项目编号就只在该项目 04_监控/11_监控 的变更单目录里找（不含 archive），收口仍必须恰好一份；定位不到项目时沿用原来的全工作区查找 |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/pm_closure_service.py` | 存在 | 收口写证据时把 Work 的项目（subject_project_id）传进去；读 Work 失败转成收口错误 |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/change/test_substance_control.py` | 存在 | 测试替身的 Work 补上 subject_project_id（真实 Work 都有这个字段） |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/change/test_chg_project_scope.py` | 计划新增 | 新测试 8 条：别的项目同号不挡收口、11_监控 布局、无项目编号时原唯一性照旧、同项目 archive 副本被忽略、同项目两份仍拒绝、本项目缺失时拒绝、实施回填写进本项目、收口服务按 Work 的项目定位 |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/活动技术债台账.md` | 存在 | 台账回写：登记并偿还 TD-SW008-166，TD-SW008-164、165 偿还；§3 追加 CHG-SCPT-2026-439、440 |
| 6 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | WBS 短投影回写 V4.0.10：`M3-DOCSYNC` 完成与 D07b、新增 `M3-CHGSCOPE` 行、D08 在本修复部署后继续 |

出现第 7 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-chgscope/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；5 个修改文件的基线（`f759716f` 上的）blob SHA-256 在 `chgscope_config.json` 与启动脚本里冻结。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/change/substance_injector.py` | 存在 | `cf03bc4ea206bdfd72c5ce4eab1a2049fcf6d627d484fb2c15968abf5dd68fce` |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/pm_closure_service.py` | 存在 | `e842df689845fecbc2a7c836630fecb955bfa1dbc8134dc31cca89c407c9506b` |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/change/test_substance_control.py` | 存在 | `44b494745464974ff853c602980d89212872ebf9f8391a3d23a946c1568a7a3a` |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/change/test_chg_project_scope.py` | 计划新增 | `d0ab275e25aeb153474a82862d90aee49275b2cc5e1392b74e6492db0c42646c` |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/活动技术债台账.md` | 存在 | `4ef952f51d2513c3dbafcbdbb6537b549d01ee119136bb7a97542282102eabde` |
| 6 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | `e575b19e21478c23c4ac3f004c8d7a67e8062bfad4b7519b86638e0bc2b9ad51` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-chgscope/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `3d4f99f8db530ddabbc8119a708b0f60166f782ab534656385b4c8c707f66ff8`。

| 工具 | SHA-256 |
|---|---|
| `adjust_counts.py` | `b0662948d52b927db2ba88232b20550616efeb572bdbd129472bb79cbee3ca1d` |
| `chgscope_config.json` | `6f6bd48bdd871bcabf8d92fa4dc3a77d6e520004e356df3087082dc555e8b9fe` |
| `chgscope_gates.py` | `a56e087fda80f37bd5c63d96d216e9c4fe36823496d91bb112985599ce1c19dc` |
| `chgscope_gates_all.sh` | `d105f571db1917b823ff925ba3fc33ceb7a46195f0e42652d0ab60bbb3957df2` |
| `commit_msg.template.txt` | `07a45942ad27bb31fbbfe8a2f48962ec00e6b09e7532ab89d204af31e586ba4d` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `install_files.py` | `6f3f89df2f7fbeaf3a3ff90a3f91e648285b2f2d27690a31a98e9bed1f78c2b4` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

## 6. 门禁矩阵

核心档。顺序：基线测量 → 安装冻结文件 → 快速门禁 → 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、5 个修改文件为基线字节、新测试文件不存在；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与卡 176 的受治理输出相比（产品子树与本卡基线相同）：失败集合为空、无 ERROR，change 组通过 +8（本卡新测试），其余各组不变。唯一容忍规则见 §1 第 6 条 |
| G3 | 内容合同 | 新测试、实施回填测试与收口服务测试 40 条通过、0 条跳过；两个改动模块 mypy 干净；`doc check` 退出码与基线相同；台账与 WBS 满足冻结的逐行合同；插件二进制前后相同 |
| G4 | 静态 | `ruff check auto_pm tests` 干净；`mypy --platform win32 auto_pm` 干净；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 6 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 产品树只差冻结文件 | `auto_pm`、`templates`、`tests`、`scripts` 四棵树相对基线恰好只差本卡的 2 个产品文件与 2 个测试文件 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 6 个文件退出 0（临时索引） |
| G8 | 真实变异与文档反例 | 4 个变异（收口忘传项目；查找忽略项目；archive 副本又算数；实施回填取全工作区第一个）让测试失败，并按字节还原；2 个文档反例被逐行合同拒绝 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-18 在项目聊天里预授权“自行收口推送，其他按照你的经验来…你现在负责全局”，并授权 Claude 合并 main；2026-10-20 对门禁修复方案回“A”，Trae 报告第二个缺陷后由 Claude 定根治；**本卡 SHA 在线程里报出后**启动（重载门禁不在 17:00～21:00 跑）。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | 按用户 2026-10-18 的预授权委托：G1～G9 全 PASS 且提交字节等于冻结清单后由 Claude 收口；独立审计通过且 CI 全绿后由 Claude 合并 |
| 审批人 | fubai |
| 执行模型 | Claude |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

0. 启动前核对本机负载；不在 17:00～21:00 启动；开防休眠。
1. 在线程里报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 的 SCPT/DEF 变更单、匹配 Decision（`DEC-<当天>-M3CHGSC2`）、Work `WORK-SW008-M3-CHGSCOPE-002`、Run `RUN-SW008-M3-CHGSCOPE-002`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-chgscope`，分支 `codex/m3-chgscope`。
4. 安装冻结字节并完整重跑门禁（`chgscope_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单（收口结论写明委托签署，TD-SW008-158）；推送 PR 分支并开 PR；独立审计通过且 CI 全绿后按用户授权合并。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 6 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；插件缺失或版本不符；需要改这 6 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮；同一问题两次未解就通知用户；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始输出（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录；PR。

## 11. 限制与后续

提交在本地分支 `codex/m3-chgscope`，之后推送为 PR 分支。之后：用 D06/D07 同一份操作脚本从合并后的提交构建并切换新版本（切换时用户确认），然后重试第 1 道的 Mission 收口，接着做 D08 第 2、3 道。
