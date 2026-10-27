# M3-PATHORDER｜收口准备比较改动路径不看顺序实施卡（四个路径）

> 卡片编号：`CARD-SW008-M3-PATHORDER`
> 版本：`V1.0`（2026-10-21；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户预授权自行收口推送与合并；本卡 SHA 先在线程里报出；条件见 §7）
> 档次：核心（改产品代码），跑九组回归
> 依赖：上一张卡 RUN-SW008-M3-ADOPT-001 已达技术终态且 CHG-SCPT-2026-443 已收口（由启动脚本核验）
> 隔离基线：`fc19c10354bdfa969e22b7c6c7edc8cff30c42fa`（`main` 当前提交，含卡 178，本地分支 `origin/main`）
> 路径根：`.`
> 执行模型：Claude；独立审计由项目另开的云端会话做
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。时间均为亚利桑那时间（MST）。

## 1. 背景与已核实事实（2026-10-21）

1. **为什么**：D08 第 2 道（DJ-2026-011 双手启动）`plc check` 退出码 0、插件测试 6/6、用户验收，Mission 到 ACCEPTED；Trae CN 随后 `close_accepted`，收口准备（C05，`ContinuityStore.prepare_closure`）拒绝：“最新 Checkpoint 未绑定 Run 当前验证证据”。本机账本核实：`RUN-DJ011-TWOHAND-001` 登记的 4 个改动路径顺序是 OB1、FB、DB1、Test；最新 Checkpoint `CP-RUN-DJ011-TWOHAND-001-VERIFY` 由证据服务按字典序存成 DB1、FB、OB1、Test，内容相同。C05 逐位比较，只要登记顺序不是字典序，任何 Mission 都关不掉；验收前的质量验证（`pm_facade_service`）本来就是排序后比较，两处口径不一。
2. **做什么**：C05 改成 `sorted(checkpoint.dirty_paths) != sorted(run.declared_dirty_paths)`，路径不同或重复仍拒。新增 3 个测试。台账登记并偿还 TD-SW008-168，§3 追加卡 178 的 CHG-SCPT-2026-443；WBS 写回。
3. **已验证**：开发工作树里新测试 3 条与收口服务、提前终态测试共 25 条通过，ruff、mypy 干净。第 2 道现在 Mission ACCEPTED、Work IN_PROGRESS、Run VERIFYING，没有走上终态，修复部署后直接重试 `close_accepted` 即可。
4. **不做什么**：不改证据服务的排序；不改 Run 登记；不碰 DJ-2026-011 的 Mission；不部署、不切换发布版本（与卡 178 一起另行切换，切换时用户确认）。同类有序比较的全面排查由项目另开的线程做，本卡只修已挡住 D08 的这一处。
5. **你应当知道的事**：卡 178 已合并但还没切换；本卡合并后两项修复一起构建一次、切换一次。
6. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差。
7. **演练事实（非治理，临时工作树，不是正式证据）**：2026-10-21 中午（MST）在基线 `fc19c103` 的临时工作树里跑了基线测量、安装、快速门禁（含 2 个真实变异与真实提交钩子干跑）与判卷：九组回归用合成输出判卷，G1～G9 全 PASS；4 个反例变体的判卷结果符合预期（core 计数变化、rest 一个失败、r09 重跑失败均被拒，r09 重跑 3/3 通过放行）。演练不是正式证据，正式 Run 完整重跑。

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
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/continuity_store.py` | 存在 | 收口准备（C05）比较 Checkpoint 与 Run 的改动路径时先排序再比（与验收前的质量验证同一口径）；路径不同或重复仍拒 |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_closure_path_order.py` | 计划新增 | 新测试 3 条：同一组路径顺序不同能准备收口、路径不同被拒、重复路径被拒 |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/活动技术债台账.md` | 存在 | 台账回写：登记并偿还 TD-SW008-168；§3 追加 CHG-SCPT-2026-443 |
| 4 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | WBS 短投影回写 V4.0.12：`M3-ADOPT` 合并、新增 `M3-PATHORDER` 行、D08 在两项修复一起部署后继续 |

出现第 5 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-pathorder/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；3 个修改文件的基线（`fc19c103` 上的）blob SHA-256 在 `pathorder_config.json` 与启动脚本里冻结。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/continuity_store.py` | 存在 | `2d304d7e046832ab9f19c9a2a58eb0b767a3c24d9a8d90dd16ac0150a1b0064b` |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_closure_path_order.py` | 计划新增 | `461c6bd45ab699ee4e9a3602d60c90e588e623aa0b66e1337440cadf9f82975f` |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/活动技术债台账.md` | 存在 | `ee4894ca15c4d5d3a2db01216b16879e524117ebfd8cc228b85e55331aadc23f` |
| 4 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | `7148b54b4ea8a6bf9ec2d22e76f83b4da88125b2193cc5e245ffd383946d902d` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-pathorder/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `ee0a47f5273ed8a9dfd39f958a096a29c1fb510dc17617206de5e66292a5a0c7`。

| 工具 | SHA-256 |
|---|---|
| `adjust_counts.py` | `b0662948d52b927db2ba88232b20550616efeb572bdbd129472bb79cbee3ca1d` |
| `commit_msg.template.txt` | `65e7c1e24f087a794d9c7d4fa311a0e31430ffef290b683a273e2261a2c1a29a` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `install_files.py` | `4bb58fc62227495246fc92f37c1c7918465f9da70e238ab5050fdcdaa2f419c9` |
| `pathorder_config.json` | `1865c5a3c83008e9694bb00edd6899239c9923475abb70da5e6139c1e845349c` |
| `pathorder_gates.py` | `89aa1ed467774a3081a574d2a413e382ba864e9457c97e21e81fa455c896dd62` |
| `pathorder_gates_all.sh` | `ef28f272268a7e4fd921998402b336378f06546a28f182d1d3290d2da0f79d0d` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

## 6. 门禁矩阵

核心档。顺序：基线测量 → 安装冻结文件 → 快速门禁 → 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、3 个修改文件为基线字节、新测试文件不存在；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与卡 178 的受治理输出相比（产品子树与本卡基线相同）：失败集合为空、无 ERROR，core 组通过 +3（本卡新测试），其余各组不变。唯一容忍规则见 §1 第 6 条 |
| G3 | 内容合同 | 新测试与收口服务测试 19 条通过、0 条跳过；改动模块 mypy 干净；`doc check` 退出码与基线相同；台账与 WBS 满足冻结的逐行合同；插件二进制前后相同 |
| G4 | 静态 | `ruff check auto_pm tests` 干净；`mypy --platform win32 auto_pm` 干净；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 4 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 产品树只差冻结文件 | `auto_pm`、`templates`、`tests`、`scripts` 四棵树相对基线恰好只差本卡的 1 个产品文件与 1 个测试文件 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 4 个文件退出 0（临时索引） |
| G8 | 真实变异与文档反例 | 2 个变异（C05 又逐位比较；C05 按集合比较、忽略重复）让新测试失败，并按字节还原；2 个文档反例被逐行合同拒绝 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-18 在项目聊天里预授权“自行收口推送，其他按照你的经验来…你现在负责全局”，并授权 Claude 合并 main；2026-10-21 第 2 道收口被 C05 路径顺序比较挡住后由 Claude 定根治；**本卡 SHA 在线程里报出后**启动（重载门禁不在 17:00～21:00 跑）。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | 按用户 2026-10-18 的预授权委托：G1～G9 全 PASS 且提交字节等于冻结清单后由 Claude 收口；独立审计通过且 CI 全绿后由 Claude 合并 |
| 审批人 | fubai |
| 执行模型 | Claude |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

0. 启动前核对本机负载；不在 17:00～21:00 启动；开防休眠。
1. 在线程里报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 的 SCPT/DEF 变更单、匹配 Decision（`DEC-<当天>-M3PATHO1`）、Work `WORK-SW008-M3-PATHORDER-001`、Run `RUN-SW008-M3-PATHORDER-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-pathorder`，分支 `codex/m3-pathorder`。
4. 安装冻结字节并完整重跑门禁（`pathorder_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单（收口结论写明委托签署，TD-SW008-158）；推送 PR 分支并开 PR；独立审计通过且 CI 全绿后按用户授权合并。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 6 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；插件缺失或版本不符；需要改这 4 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮；同一问题两次未解就通知用户；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始输出（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录；PR。

## 11. 限制与后续

提交在本地分支 `codex/m3-pathorder`，之后推送为 PR 分支。之后：用 D06/D07 同一份操作脚本从合并后的提交构建并切换新版本（含卡 178、179，切换时用户确认），然后重试第 1、2 道的 Mission 收口，接着做 D08 第 3 道。
