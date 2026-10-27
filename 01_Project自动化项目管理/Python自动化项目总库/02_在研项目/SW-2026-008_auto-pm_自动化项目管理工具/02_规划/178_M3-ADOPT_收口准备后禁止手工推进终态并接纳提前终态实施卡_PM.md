# M3-ADOPT｜收口准备后禁止手工推进终态并接纳提前终态实施卡（四个路径）

> 卡片编号：`CARD-SW008-M3-ADOPT`
> 版本：`V1.0`（2026-10-21；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户预授权自行收口推送与合并；本卡 SHA 先在线程里报出；条件见 §7）
> 档次：核心（改产品代码），跑九组回归
> 依赖：上一张卡 RUN-SW008-M3-CHGSCOPE-002 已达技术终态且 CHG-SCPT-2026-441 已收口（由启动脚本核验）
> 隔离基线：`10165f900028d6776b9930fbac761f5485e9c4a2`（`main` 当前提交，含卡 177，本地分支 `origin/main`）
> 路径根：`.`
> 执行模型：Claude；独立审计由项目另开的云端会话做
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。时间均为亚利桑那时间（MST）。

## 1. 背景与已核实事实（2026-10-21）

1. **为什么**：切换到 `1.3.3-10165f9` 后，Trae CN 重试 D08 第 1 道（SW-2026-010）的 Mission 收口，卡 177 修的变更单查重这次已通过，但 C08（`ContinuityStore.finalize_closure`）拒绝：它要求 Run 仍在 VERIFYING、Work 仍在 IN_PROGRESS。本机账本核实：收口在 10-20 21:30:33 准备好（`CLOSURE-33DE726E225B5209B90EE8E1`），21:39 执行方用底层命令把 `RUN-SW010-RANGE-004` 转 SUCCEEDED、把 Work 依次转 VERIFYING/ACCEPTED/CLOSED。这两个终态在状态机里都没有出边，C08 这条检查也不是新加的（以前被查重挡在前面没碰到），所以 Mission 没有任何合规路径关闭。
2. **做什么**：收口准备好以后（存在该 Run/Work 的 PREPARED 收口），底层的 Work 迁移拒绝转 VERIFYING/ACCEPTED/CLOSED，Run 迁移拒绝转 SUCCEEDED，提示终态只能由 `close_accepted` 一步推进；FAILED/CANCELLED 不拦。C08 遇到 Run 已 SUCCEEDED 且 Work 已 CLOSED 时，核对两者最后一次迁移事件分别是 SUCCEEDED 与 CLOSED、时间不早于收口准备，满足就不再改 Run/Work，记一条 `CLOSURE_LINEAGE_ADOPTED`（带两条终态事件编号），再照常关闭 Mission、Closure、步骤与 outbox；准备之前到达、或只有一方终态，仍按原来的报错拒绝。新增 6 个测试。台账登记并偿还 TD-SW008-167，§3 追加 441、442；WBS 写回。
3. **已验证**：开发工作树里新测试 6 条与原收口服务测试 16 条全部通过，ruff、mypy 干净；九组回归由正式门禁 G2 完整跑。
4. **不做什么**：不改 Run/Work 的状态机出边；不手改账本；不碰 SW-2026-010 的 Mission（修复部署后由 D08 重试收口）；不部署、不切换发布版本（另行，切换时用户确认）。
5. **你应当知道的事**：D08 后续题目的提示词已加“绝不单独用 run/work 命令改 Run 或 Work 的状态”；本卡让账本本身也拦住这一步。
6. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差。
7. **演练事实（非治理，临时工作树，不是正式证据）**：2026-10-21 上午（MST）在基线 `10165f90` 的临时工作树里跑了基线测量、安装、快速门禁（含 4 个真实变异与真实提交钩子干跑）与判卷：九组回归用合成输出判卷，G1～G9 全 PASS；4 个反例变体的判卷结果符合预期（core 计数变化、rest 一个失败、r09 重跑失败均被拒，r09 重跑 3/3 通过放行）。开发工作树里新测试 6 条与收口服务原测试 16 条通过，ruff、mypy 干净。演练不是正式证据，正式 Run 完整重跑。

## 2. 单一目标与完成定义

冻结的 4 个文件的字节被提交，九组回归只多出本卡的新测试；技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行；之后开 PR，独立审计通过且 CI 全绿后由 Claude 按用户授权合并；再另行构建新版本并切换（切换时用户一句话确认）。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、3 个修改文件的基线 blob 等于冻结哈希、新测试文件在基线不存在。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **机器负载**：启动前核对前台无游戏/启动器，近 10 秒 CPU 低；重载门禁不在 17:00～21:00（MST）跑，预计结束时间也不得落入该时段；开防休眠。
4. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有续租成功。
5. **正式门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 2 小时。

## 4. 精确 Owned Paths（4）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/continuity_store.py` | 存在 | 收口准备好以后，Work 的核验、验收、关闭迁移与 Run 的成功迁移被拒绝（只能由 C08 一步推进）；C08 接纳准备之后由同一 Run/Work 到达的提前终态，不改 Run/Work，记 CLOSURE_LINEAGE_ADOPTED，再关闭 Mission 与 Closure |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_closure_early_terminal.py` | 计划新增 | 新测试 6 条：准备后手工关 Work 被拒、手工让 Run 成功被拒、正常路径照旧经 C08 全部关闭、准备之后的提前终态被接纳且可重放、准备之前的终态被拒、只有 Run 终态仍被拒 |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/活动技术债台账.md` | 存在 | 台账回写：登记并偿还 TD-SW008-167；§3 追加 CHG-SCPT-2026-441、442 |
| 4 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | WBS 短投影回写 V4.0.11：`M3-CHGSCOPE` 完成与 D07c、新增 `M3-ADOPT` 行、D08 在本修复部署后继续 |

出现第 5 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-adopt/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；3 个修改文件的基线（`10165f90` 上的）blob SHA-256 在 `adopt_config.json` 与启动脚本里冻结。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/continuity_store.py` | 存在 | `2c32e1ae3d41d5628845d7d27e094eb24d01d1bd15ead5ca83af0a9625fe49d5` |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_closure_early_terminal.py` | 计划新增 | `e20027aec9f2c5a831f16cfc76f2c85dcffd56c93ca5f7b11a0157892fd56b05` |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/活动技术债台账.md` | 存在 | `1a1f1dae380c2fdaa3a2fb2a3fdda763d41071f1a537ff631d360d01e689c9f3` |
| 4 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | `ae142882cb048c934cfdc0206a2a9a1ebb5b1342cea62b37f49813896e54b49b` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-adopt/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `afc46946d12c4d6323e59ad347ec7ce700072066cf4d542f52120f64153f418c`。

| 工具 | SHA-256 |
|---|---|
| `adjust_counts.py` | `b0662948d52b927db2ba88232b20550616efeb572bdbd129472bb79cbee3ca1d` |
| `adopt_config.json` | `e78e1632a8c22f3b945124493583b435bd0df1cee98ac8460e1835b382e31b43` |
| `adopt_gates.py` | `ab7a1336141d3cc836742e3ca2dabf22db00906581ea1cda305ba142c9732b76` |
| `adopt_gates_all.sh` | `5ceb97472619a58a98cf689699eb0c88f0fa8b6bdee2610e7e7044eb0da608b7` |
| `commit_msg.template.txt` | `ed98083eb352e0f912751b8c29960296a2921f7485ad8a66a6bf1ef674b44029` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `install_files.py` | `b8a77be1cd7470796f6b4cc7c92a5650f9440b69054c7a1f72cd54c4cb0bda4b` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

## 6. 门禁矩阵

核心档。顺序：基线测量 → 安装冻结文件 → 快速门禁 → 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、3 个修改文件为基线字节、新测试文件不存在；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与卡 177 的受治理输出相比（产品子树与本卡基线相同）：失败集合为空、无 ERROR，core 组通过 +6（本卡新测试），其余各组不变。唯一容忍规则见 §1 第 6 条 |
| G3 | 内容合同 | 新测试与收口服务测试 22 条通过、0 条跳过；改动模块 mypy 干净；`doc check` 退出码与基线相同；台账与 WBS 满足冻结的逐行合同；插件二进制前后相同 |
| G4 | 静态 | `ruff check auto_pm tests` 干净；`mypy --platform win32 auto_pm` 干净；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 4 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 产品树只差冻结文件 | `auto_pm`、`templates`、`tests`、`scripts` 四棵树相对基线恰好只差本卡的 1 个产品文件与 1 个测试文件 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 4 个文件退出 0（临时索引） |
| G8 | 真实变异与文档反例 | 4 个变异（又能手工关 Work；又能手工让 Run 成功；C08 不再接纳；C08 接纳准备之前的终态）让测试失败，并按字节还原；2 个文档反例被逐行合同拒绝 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-18 在项目聊天里预授权“自行收口推送，其他按照你的经验来…你现在负责全局”，并授权 Claude 合并 main；2026-10-21 第 1 道收口重试被 C08 挡住后由 Claude 定根治；**本卡 SHA 在线程里报出后**启动（重载门禁不在 17:00～21:00 跑）。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | 按用户 2026-10-18 的预授权委托：G1～G9 全 PASS 且提交字节等于冻结清单后由 Claude 收口；独立审计通过且 CI 全绿后由 Claude 合并 |
| 审批人 | fubai |
| 执行模型 | Claude |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

0. 启动前核对本机负载；不在 17:00～21:00 启动；开防休眠。
1. 在线程里报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 的 SCPT/DEF 变更单、匹配 Decision（`DEC-<当天>-M3ADOPT1`）、Work `WORK-SW008-M3-ADOPT-001`、Run `RUN-SW008-M3-ADOPT-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-adopt`，分支 `codex/m3-adopt`。
4. 安装冻结字节并完整重跑门禁（`adopt_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单（收口结论写明委托签署，TD-SW008-158）；推送 PR 分支并开 PR；独立审计通过且 CI 全绿后按用户授权合并。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 6 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；插件缺失或版本不符；需要改这 4 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮；同一问题两次未解就通知用户；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始输出（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录；PR。

## 11. 限制与后续

提交在本地分支 `codex/m3-adopt`，之后推送为 PR 分支。之后：用 D06/D07 同一份操作脚本从合并后的提交构建并切换新版本（切换时用户确认），然后重试第 1 道的 Mission 收口，接着做 D08 第 3 道（第 2 道不受影响，可先做）。
