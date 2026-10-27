# M3-DECL｜改动声明口径统一与计划七栏必填门禁卡（三十个路径）

> 卡片编号：`CARD-SW008-M3-DECL`
> 版本：`V1.0`（2026-10-22；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户预授权自行收口推送；合并 PR #35、#36 与切换时用户确认；本卡 SHA 先在线程里报出；条件见 §7）
> 档次：核心（改产品代码），跑九组回归
> 依赖：上一张卡 RUN-SW008-M3-CHGUNIQ2-001 已达技术终态且 CHG-SCPT-2026-447 已收口（由启动脚本核验）
> 隔离基线：`a53d9f2e79f9733f96ce442e31a035828a5dd94d`（`main` 上 PR #34 的合并提交，含卡 180、181；本地分支 `m3-decl-base`）
> 路径根：`.`
> 执行模型：Claude（产品与测试代码由云端会话写成 PR #35、#36）；独立审计 68、69 由项目另开的云端会话做
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。时间均为亚利桑那时间（MST）。

## 1. 背景与已核实事实（2026-10-22）

1. **为什么**：真 Trae 一句话需求试跑（DJ-2026-011 报警汇总，报告 `真Trae试跑打分_20261022.md`）判不过：计划与 Run 的改动声明为空，`pm plan`、`continuity run start`、质量验证都放行，只有验收（`pm_facade_service`）拒收，Mission `MISSION-D053E7A789FF5928` 停在 ACCEPTANCE_PENDING；计划缺“是否涉及安全回路”，并把已退役的 `PM_SESSION_DJ-2026-011.md` 列入范围。
2. **做什么**：云端写成 PR #35（改动声明口径统一：空声明在计划、批准、开 Run 时拒收；验证与验收共用 `contracts/declared_dirty.py` 一处比对；PM_SESSION 不许入范围或声明）与 PR #36（叠在 #35 上：计划七栏必填，缺一栏不许出卡、不许批准）。两条 PR 线性接在 `main` `a53d9f2e` 后面，先合 #35 再合 #36 的产品树就是 PR #36 头 `fd1590f0` 的树。本卡冻结这 28 个文件的字节（10 个产品文件含 2 个新增，18 个测试文件含 3 个新增），加台账与 WBS 回写，在本机跑九组门禁。
3. **已验证**：开发工作树里 `ruff check auto_pm tests` 与 `mypy auto_pm` 干净；新测试文件 73 条可收集（72 条通过、1 条参数组合按设计跳过）；cli 组可收集数 415→420、core 组 1215→1288，其余组不变。
4. **不做什么**：不改 PR 的字节（审计 68、69 若要求修改，按新字节重出本卡）；不碰 DJ-2026-011 的 Mission（切换后用带正确声明的新 Run 合规收口）；不部署、不切换（合并与切换时用户确认）。
5. **合并方式**：本卡提交只作门禁证据；合并按 PR 顺序：先合 #35，再合 #36，切换脚本核对合并后的三棵产品子树等于本卡提交。台账与 WBS 的回写随后以纯文档 PR 进 `main`。
6. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差。
7. **演练事实（非治理，临时工作树，不是正式证据）**：2026-10-22 上午（MST）在基线 `a53d9f2e` 的临时工作树里，安装 PR #36 头 `fd1590f0` 的 28 个文件字节与台账、WBS 回写后跑了基线测量、快速门禁（含 5 个真实变异、2 个文档反例与真实提交钩子干跑）与判卷：九组回归用合成输出判卷，G1～G9 全 PASS；4 个反例变体的判卷结果符合预期。新测试文件里恰有 1 条参数组合按设计跳过（空授权的 submit 入口，submit 本来就要求显式授权），已在 G2/G3 事先声明。演练不是正式证据，正式 Run 完整重跑。

## 2. 单一目标与完成定义

冻结的 30 个文件的字节被提交，九组回归只多出本卡的新测试；技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行；之后开 PR，独立审计通过且 CI 全绿后由 Claude 按用户授权合并；再另行构建新版本并切换（切换时用户一句话确认）。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、25 个修改文件的基线 blob 等于冻结哈希、5 个新文件在基线不存在。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **机器负载**：启动前核对前台无游戏/启动器，近 10 秒 CPU 低；重载门禁不在 17:00～21:00（MST）跑，预计结束时间也不得落入该时段；开防休眠。
4. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有续租成功。
5. **正式门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 2 小时。

## 4. 精确 Owned Paths（30）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/api.py` | 存在 | PR #35/#36 的产品改动（接入统一的改动声明与计划七栏检查），字节等于 PR #36 头 fd1590f0 |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/continuity_execution_service.py` | 存在 | PR #35/#36 的产品改动（接入统一的改动声明与计划七栏检查），字节等于 PR #36 头 fd1590f0 |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/mission_service.py` | 存在 | PR #35/#36 的产品改动（接入统一的改动声明与计划七栏检查），字节等于 PR #36 头 fd1590f0 |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/pm_facade_service.py` | 存在 | PR #35/#36 的产品改动（接入统一的改动声明与计划七栏检查），字节等于 PR #36 头 fd1590f0 |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/contracts/declared_dirty.py` | 计划新增 | 新增：改动声明一处口径（空声明拒收、PM_SESSION 不许入范围、Checkpoint 与声明按集合比对，验证与验收共用） |
| 6 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/contracts/plan_checklist.py` | 计划新增 | 新增：计划七栏必填检查（原话、范围、声明、安全回路是/否、每条验收的命令与退出码、风险、回退） |
| 7 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/contracts/pm_facade.py` | 存在 | PR #35/#36 的产品改动（接入统一的改动声明与计划七栏检查），字节等于 PR #36 头 fd1590f0 |
| 8 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/change/decision_service.py` | 存在 | PR #35/#36 的产品改动（接入统一的改动声明与计划七栏检查），字节等于 PR #36 头 fd1590f0 |
| 9 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/continuity.py` | 存在 | PR #35/#36 的产品改动（接入统一的改动声明与计划七栏检查），字节等于 PR #36 头 fd1590f0 |
| 10 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/pm.py` | 存在 | PR #35/#36 的产品改动（接入统一的改动声明与计划七栏检查），字节等于 PR #36 头 fd1590f0 |
| 11 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_continuity.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 12 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_pm_facade.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 13 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_pm_handoff.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 14 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_pm_inbox.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 15 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_pm_pending_cards.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 16 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_cockpit_api.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 17 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_declared_dirty_consistency.py` | 计划新增 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 18 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_plan_checklist.py` | 计划新增 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 19 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_plc_checkpoint_chain.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 20 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_pm_facade_service.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 21 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_pm_pending_scope_card.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 22 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_pm_run_e2e.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 23 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_gui.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 24 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_intake.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 25 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_plc.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 26 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_reclaim.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 27 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plan_checklist_support.py` | 计划新增 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 28 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/qml/test_pm_cockpit_approval_bridge.py` | 存在 | PR #35/#36 的测试（新增或随新规则调整夹具），字节等于 PR #36 头 fd1590f0 |
| 29 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/活动技术债台账.md` | 存在 | 台账回写：登记并偿还 TD-SW008-171、172；§3 追加 CHG-SCPT-2026-447、448 |
| 30 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | WBS 短投影回写 V4.0.15：PR #34 合并与 D07e、新增 `M3-DECL` 行与试跑批次 |

出现第 31 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-decl/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；25 个修改文件的基线（`a53d9f2e` 上的）blob SHA-256 在 `decl_config.json` 与启动脚本里冻结。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/api.py` | 存在 | `7f96bbd3a69e28eafaf1bf155560bdc88da3866ce5f2a936f80a3aa1c80f992c` |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/continuity_execution_service.py` | 存在 | `85babc5e60fff6910e824a476d438a03207b34eee61e151d25f7f0084f6443fe` |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/mission_service.py` | 存在 | `851c01f2664247528c368ec553d43158ad01205ff8db02d978cd2493852d07bd` |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/pm_facade_service.py` | 存在 | `d20286a4c6c03812903daac3042e46818ac1a7540fadb5057afff9d092031548` |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/contracts/declared_dirty.py` | 计划新增 | `4c9e7ddfe365d32dc4bc2c8e29f630167b22989f192efb0d41771afefba0b31e` |
| 6 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/contracts/plan_checklist.py` | 计划新增 | `914e9dc8f694035158b94a227b83d58914ada949ce39c52d9c4f55168e0808a5` |
| 7 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/contracts/pm_facade.py` | 存在 | `1e0b2ecbcace92630b29921a2f0accf37f97a4ba0f6874db42650335a0cc038d` |
| 8 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/change/decision_service.py` | 存在 | `e0f023a4a82ae992d2bc514d574ce955eea658534805e0f86bb907ccc301cdf7` |
| 9 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/continuity.py` | 存在 | `ac38344d8080d184fbe97b7f99309b5cc9cbecbafafa7b26b7ae24bda34c00e5` |
| 10 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/pm.py` | 存在 | `b510f3c0add740a7fe451bcae7d93c4a4c37be66c6576bce92c38d2d9f181614` |
| 11 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_continuity.py` | 存在 | `2a05930150a48760f5400557d346e1035ccd767feced8206f064616515b99080` |
| 12 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_pm_facade.py` | 存在 | `cbd847164278abb29ee200632743be815b9f0078069314ee6b5571d213e90563` |
| 13 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_pm_handoff.py` | 存在 | `dcdc7f2f1ee228c3f5517ecb014053d6332dfe1ab53def91557a50700493df9b` |
| 14 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_pm_inbox.py` | 存在 | `ddaaded8e7ca0b0fb75c40f5619d77d926e1fecd58adcc7645456919ac0d03ac` |
| 15 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_pm_pending_cards.py` | 存在 | `53f335cbd5071164ccf58f87d53b339a50bd4b3a505d04c3c674dd4dfede760d` |
| 16 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_cockpit_api.py` | 存在 | `951e67fe15a640c4c725da6dd77c57043b174e6c9c69fc3d5cca4e592b3a80f0` |
| 17 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_declared_dirty_consistency.py` | 计划新增 | `c75fc72634dcd932afc60e405879c36eaa87943c7e7e157c8b8864f73abe85b5` |
| 18 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_plan_checklist.py` | 计划新增 | `4a499adc5c56bee39fbde140948ca474100754fb10a568ef43839ee3f680175b` |
| 19 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_plc_checkpoint_chain.py` | 存在 | `a34ab8bd3f35c03f993e2b374b302b0d6cb611752800134b7230a14c12a9d563` |
| 20 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_pm_facade_service.py` | 存在 | `2f7bd192cecde6a9f26a17978bad0f9391f15223116b4d0ed865c328da835ac7` |
| 21 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_pm_pending_scope_card.py` | 存在 | `8efd8cbfebed35060c71055e458e5a5b265f698bd5f8d853fa0db35e745c5c69` |
| 22 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_pm_run_e2e.py` | 存在 | `d986e8c08c39854707c50c5886cc2fe4e7c27e40b63c74b78d94fa8906672640` |
| 23 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_gui.py` | 存在 | `dc9f350d12ed254ba9c170e4ae21e023bb283e1aaffe93b76d8b2106d03a866e` |
| 24 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_intake.py` | 存在 | `e100b7799f5d3ab1eeb49d44d12bcf18fbd99c703af6d625f4a8f0ffca32550f` |
| 25 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_plc.py` | 存在 | `137f21bbae340b60c6252ce3b4eadb454ee08c0785a9b5bc87199dfd3d790969` |
| 26 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_reclaim.py` | 存在 | `92dac3eb3161df85f957e2f13f7f73c245c5e19c45620b4c69d9b56a24e5b1a6` |
| 27 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plan_checklist_support.py` | 计划新增 | `2bf070412710a6b672a370288cd39101e25eaead9d604fb77aa8417e41c13528` |
| 28 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/qml/test_pm_cockpit_approval_bridge.py` | 存在 | `2d1099e5b15d3749f303e6f6368d2c6f3fe7fa2d88bfccb05259594b39f56fe5` |
| 29 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/活动技术债台账.md` | 存在 | `b19e8208689f6950b7dc0736035f04c529d7187bcc63306a7ed427bd425ca618` |
| 30 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | `434a01c28eed1970af354f3b5338e9c4071bc9bb7a6adedfee21d3922ed43af4` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-decl/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `cebf9b7b24dd1597f254eb51e12dbca21ff939f9aa1ba278644c23ee17cda03d`。

| 工具 | SHA-256 |
|---|---|
| `adjust_counts.py` | `b0662948d52b927db2ba88232b20550616efeb572bdbd129472bb79cbee3ca1d` |
| `commit_msg.template.txt` | `7f888adc725760b6d2fa5494867e4edc68918d34400ee015ff200c2499363292` |
| `decl_config.json` | `de83fcae44c09d8095d9d6b9ddc6129e5e75a97fb539989ef18e64c76b4849ea` |
| `decl_gates.py` | `9d65975ffb4f844b01713bd8633196c908f59a3036b5154b277a52b496f31be8` |
| `decl_gates_all.sh` | `f7c3fa0efa2258b0904aa1ab9164d86e7181fb952ea1799914e161ea685897a5` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `install_files.py` | `996797dd03a8a03568a61d3c9ee8806395972ce89ecafc8c74db55a8d0ac5422` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

## 6. 门禁矩阵

核心档。顺序：基线测量 → 安装冻结文件 → 快速门禁 → 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、25 个修改文件为基线字节、5 个新文件不存在；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与卡 181 的受治理输出相比（产品子树与本卡基线相同）：失败集合为空、无 ERROR，cli 组通过 +5、core 组通过 +72 并多 1 条事先声明的跳过（PR 新测试；跳过的是“空授权”参数组合里的 submit 入口，submit 本来就要求显式授权），其余各组不变。唯一容忍规则见 §1 第 6 条 |
| G3 | 内容合同 | 改动声明与计划七栏两个新测试文件 72 条通过、恰 1 条事先声明的跳过；改动模块 mypy 干净；改动模块 mypy 干净；`doc check` 退出码与基线相同；台账与 WBS 满足冻结的逐行合同；插件二进制前后相同 |
| G4 | 静态 | `ruff check auto_pm tests` 干净；`mypy --platform win32 auto_pm` 干净；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 30 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 产品树只差冻结文件 | `auto_pm`、`templates`、`tests`、`scripts` 四棵树相对基线恰好只差本卡的 10 个产品文件与 18 个测试文件 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 30 个文件退出 0（临时索引） |
| G8 | 真实变异与文档反例 | 5 个变异（空声明被接受；PM_SESSION 放行；任何改动都算与声明一致；安全回路不再必填；不再要求每条验收一条命令）让新测试失败，并按字节还原；2 个文档反例被逐行合同拒绝 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-18 在项目聊天里预授权“自行收口推送，其他按照你的经验来…你现在负责全局”，并授权 Claude 合并 main；2026-10-22 真 Trae 试跑打分后用户选 1（先打分再修驾驶舱）；修复由云端写成 PR #35、#36，本卡在本机门禁；**本卡 SHA 在线程里报出后**启动（重载门禁不在 17:00～21:00 跑）。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | 按用户 2026-10-18 的预授权委托：G1～G9 全 PASS 且提交字节等于冻结清单后由 Claude 收口；独立审计通过且 CI 全绿后由 Claude 合并 |
| 审批人 | fubai |
| 执行模型 | Claude |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

0. 启动前核对本机负载；不在 17:00～21:00 启动；开防休眠。
1. 在线程里报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 的 SCPT/DEF 变更单、匹配 Decision（`DEC-<当天>-M3DECL01`）、Work `WORK-SW008-M3-DECL-001`、Run `RUN-SW008-M3-DECL-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-decl`，分支 `codex/m3-decl`。
4. 安装冻结字节并完整重跑门禁（`decl_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单（收口结论写明委托签署，TD-SW008-158）；推送 PR 分支并开 PR；独立审计通过且 CI 全绿后按用户授权合并。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 6 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；插件缺失或版本不符；需要改这 30 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮；同一问题两次未解就通知用户；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始输出（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录；PR。

## 11. 限制与后续

提交在本地分支 `codex/m3-decl`，之后推送为 PR 分支。之后：审计 68、69 与 CI 通过、用户回“合并”后先合 #35 再合 #36，用 D06/D07 同一份操作脚本构建并切换新版本（用户确认），再用带正确声明的新 Run 收掉试跑那单，并重跑真 Trae 试跑。
