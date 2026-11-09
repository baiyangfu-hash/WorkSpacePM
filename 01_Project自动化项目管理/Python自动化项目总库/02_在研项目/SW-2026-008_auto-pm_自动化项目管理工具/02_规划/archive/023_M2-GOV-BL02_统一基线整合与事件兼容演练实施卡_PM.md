# M2-GOV-BL02｜统一基线整合与事件兼容演练实施卡

> 卡片编号：`CARD-SW008-M2-GOV-BL02`
> 对应 WBS：`M2-GOV-BL02`（拟新增，见 024 号方案的 WBS 修订 1）
> 版本：`V0.4`（2026-09-30，依据第一轮执行事实与 GPT 裁决修订：验证 Run 顺序、G1 语义、基线例外、过期 Run 收口、测试执行方式）
> 状态：`PLANNED / NOT_AUTHORIZED`（V0.4 待用户批准；V0.3 的批准回执只对 V0.3 字节有效，见 §7.2）
> 变更单：继续沿用 `CHG-SCPT-2026-356`（不新建 BL02 CHG）；V0.4 的审批记录、卡片完整 SHA-256 与最终候选 `7cfe227e7bf4a7df57d95644a80ea2652ef5a9cc` 追加到该 CHG，保留 V0.3 历史；路径 Decision `DEC-20260929-BL02CODE` 不因卡片升版重建，由 V0.4 Approval Receipt 显式关联
> 控制根：`C:\Users\fubai\Documents\My_Workspace`
> 隔离基线：`70d7e093c92bc982e686322b1b59c62155ca628d`
> 治理任务真源：已验收 WBS 候选提交 `a385452cde480090d27175f1b4d2ccfe358a4cec`；WBS SHA-256 `AEBB2AE678D483A19E499C3A3706FD5C880643EF3EB689B2B4093D0665045EC6`；大小 `135128` 字节
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或能力不低于它的模型；首轮实际执行者为 `Claude Sonnet 5.5`（用户于对话中确认）；执行模型不构成授权，仍须满足 §7 签字门，且必须写入 Approval Receipt
> 禁用能力：`pm-workflow`
> 治理属性：只产出**候选**与证据；不合并到 main、不推送、不部署、不切换 release

> V0.2 更正说明：V0.1 把 `70d7e093` 当作“M2 尖端”，这是错误的。摸底证明 M2 产品线在 U04A 处分叉为两条从未合并的分支，`70d7e093` 不含 U04B 产品提交。本版基线改为三条线的统一整合。

> V0.4 更正说明（2026-09-30，第一轮执行后）：① V0.3 §8 要求“先提交、再建立绑定最终 HEAD 的 Checkpoint”，但没有安排新的验证 Run；现有服务对 `Run.git_head != 当前 HEAD` 一律拒绝（`Git baseline drift`），这是正常保护，不是执行错误。V0.4 把顺序改为“整合 Run → 最终不可变候选 → 验证 Run”（§8）；② 整合 Run 001 的 lease 已于 2026-09-30 05:33 UTC 过期且无法续期，现有服务不允许 `RUNNING → CANCELLED`，唯一合法收口路径需要独立恢复授权，见 §8 与 §12；③ G1 增加取值 `UNVERIFIED`，单进程命令崩溃而无等价来源对照时不得写 PASS，并把已知基线例外登记为例外清册；④ 明确分进程执行 G1 时的 node ID 完整性证明，该执行方式变更须经本次批准；⑤ G3 增加元数据最小集与历史 Mission 校验异常例外，G5 固定 `bsdtar --options hdrcharset=UTF-8`。V0.3 原字节已归档为 `.auto-pm/reports/m2-gov-bl02/card023_V0.3_original.md`（SHA-256 `d2e03f3d…5ff49`）。

> V0.4 签字前修正（2026-09-30，依据 GPT 第二次裁决）：⑥ §8 明确“从现有最终候选继续验收”，不再重建整合工作树与整合 Run；⑦ 消除 §6 与 §8 的矛盾：用户接受无来源对照的风险**不能**把它变成基线例外，只能单独记录“有条件验收”，G1 原始结论保持 `UNVERIFIED`；⑧ 恢复链补充 Decision 必须被 Git 跟踪并绑定恢复 Run 的控制根 HEAD 的前置条件，恢复链自身的终态与租约释放须先在隔离副本演练；⑨ E-G1-3 增加一轮有界稳定性探测（§6）。上一版 V0.4 草稿字节 SHA-256 `02f595ad…dca3` 已归档。

> V0.3 更正说明：① `M2-GOV-WBS1` 已形成并验收不可变 WBS 候选 `a385452c`，控制根工作副本仍为 V3.0.15；本卡以该已验收提交作为任务治理依据，不修改或冒充已同步控制根 WBS，分叉继续按卡 025 §10 记录为非阻断技术债；② Ruff/Mypy 仅接收 §4 中 17 个 Python 文件，不再把 3 个 QML 文件错误传给 Python 静态检查器；③ G5 固定为 `git archive + bsdtar + 临时控制根` 的可复现演练，严禁来源不明的一次性 release 脚本；④ 增加与卡 025 同级的实施审批、哈希漂移失效与 GUI 合同。

## 1. 背景与已核实事实（均由 `git merge-base` / `git merge-tree` 与提交内容核验）

当前存在**三条**互不包含的产品线：

| 线 | 尖端 | 内容 | 相对 U04A `d59120c7` 的产品差异 |
|---|---|---|---|
| U 线（U04B） | `d200eb9b` | 驾驶舱活动时间线 | 10 个路径（cockpit 服务、契约、QML、Bridge、4 个测试） |
| R 线（R1 + Hook 修复） | `70d7e093`（其父为 `e05fafa1`） | 终态 lease 兼容 reconcile（`e05fafa1`，7 个路径）+ Hook 双根修复（`70d7e093`，4 个路径） | 11 个路径 |
| 发布线（H11） | `0b724997`（经 `e648e0b4`） | `adjudicate_blocked_work`、`fence_legacy_terminal_lease`；建立在 `f4626947` 之上，含 Hook 修复的并行副本 `8f08c1a5` | H11A 8 个路径 + H11C 8 个路径（去重后 10 个） |

已核实：

1. U 线与 R 线共同祖先是 `d59120c7`（U04A）；两者各自验收，从未合并。控制/文档分支 `4166b9af` 也不含其中任何一条。
2. U 线与 R 线合并：产品代码**无冲突**，仅台账文档冲突（治理证据，不进候选）。
3. 再把发布线并入：冲突文件为 `auto_pm/application/core/continuity_execution_service.py`、`auto_pm/contracts/decision_package.py`、`auto_pm/ui/cli/continuity.py`、`tests/infrastructure/test_continuity_store.py`，另加台账文档；`continuity_store.py` 文本可自动合并，语义未验证。
4. M2 线对事件读取加了按类型的 schema 白名单（`continuity_store.py` 中 `allowed_schemas`，基线约第 5276～5290 行）并引入 `run-transition.v4`、`terminal-lease-reconciliation.v1`；canonical 库现含 5 个 `RUN_LEGACY_LEASE_FENCED` 与 14 个 `WORK_ADJUDICATED` 事件，M2 读取代码从未见过它们。
5. M2 线相对 `f4626947` 未新增或修改表结构（无 CREATE/ALTER TABLE）。
6. `main`（`0d7071b7`）= `f4626947` + 仅一个测试文件，是 M2 线的祖先，与本卡无冲突。
7. 实施卡工具（`implementation_card*`、`implementation-card` 命令）只在 M2 线，不在发布线；发布线独有 4 个命令（`continuity work adjudicate`、`adjudication-evidence`、`continuity run fence-legacy-terminal`、`legacy-terminal-evidence`），M2 线独有 `continuity run reconcile-terminal-lease` 与 5 个 `implementation-card` 命令。

## 2. 单一目标

产出一个**干净、不可变、可回退**的统一基线候选，同时包含：U04B 驾驶舱时间线、R1 终态 lease reconcile、Hook 双根修复、H11A 与 H11C 合同；并**用 canonical 数据库副本证明** M2 读取路径面对新事件不会误拒。

本卡不解决整改 B/C/D，也不改变任何业务语义。

## 3. 实施前基线门禁（只读，先于任何写入）

执行 Agent 必须先输出事实表，任一项不符即停止：

1. 治理任务真源核验：`git rev-parse a385452c^{commit}` 必须得到完整提交 `a385452cde480090d27175f1b4d2ccfe358a4cec`；该提交中的 WBS 必须匹配本卡头部 SHA-256 与大小，并包含 `M2-GOV-BL02 = PLANNED / NOT_AUTHORIZED`。控制根 WBS 尚未同步不阻断本卡，但必须在证据中明确标记 `WBS_CONTROL_ROOT_SPLIT`，不得把旧工作副本称为 V3.0.16。
2. 冻结起点并写入 Checkpoint 证据：`git rev-parse` 以下四个 SHA 并确认可解析：`70d7e093`、`d200eb9b`、`e648e0b4`、`0b724997`；核验 `70d7e093` 是 `e05fafa1` 的后代，`d200eb9b` 的父提交是 `d59120c7`，且 `d200eb9b` 与 `e05fafa1` 互不为祖先。
3. 冻结数据分两步：审批前只读记录 `.auto-pm/continuity.db` 的 SHA-256、大小与事件计数；审批成立后、创建候选或修改源码前，才允许把数据库复制到 `.auto-pm/reports/m2-gov-bl02/`。副本只用于演练与取证，任何时候不得覆盖、附加或替换真实库。
4. 只读核验命令均存在：`git merge-tree --write-tree`（Git ≥ 2.38，当前 2.45.1）、`git archive`、`tar`（Windows bsdtar）、`main.py pm resume`、`main.py continuity work adjudication-evidence`、`main.py continuity run legacy-terminal-evidence`；任一不存在则停止，不得临时发明替代命令。
5. 逐个核验 §4 路径在其**来源提交**上是否存在，并与 §4 标注一致；不一致即基线漂移，停止。
6. 确认拟建候选目录与分支未被占用，并确认 Continuity 无活动 Mission/Work/Run。进程命令行若因系统权限无法枚举，不得伪报“无进程”；必须以目标目录/分支未创建、Continuity 无活动执行和执行器句柄登记为空三项共同判定，任一无法证明即停止。
7. 只使用主工作区 `.venv\Scripts\python.exe -B` 与稳定根入口，不从候选加载 release 指针。
8. Run 生命周期预检：记录任一 Run 的 lease 到期时间；整合 Run 必须在 lease 有效期内完成全部提交并转入终态，或在到期前续期（续期须使用同一 owner 与 token，过期后不可续期）。lease 一旦过期而 Run 仍为 `RUNNING`，立即停止并报告，只允许走 §8 第 6 步的独立恢复授权，禁止直接 SQL、禁止补偿脚本。

## 4. 精确 Owned Paths（20 个会被修改，4 个只读对照）

均相对 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/`。

**A. 来自 U 线 `d200eb9b`（相对 `d59120c7` 的产品差异，与 R 线无冲突；这些路径在基线 `70d7e093` 上均已存在，U04B 只是修改它们）**

| # | 路径 | 基线状态 |
|---|---|---|
| 1 | `auto_pm/application/core/pm_cockpit_service.py` | 存在 |
| 2 | `auto_pm/contracts/pm_cockpit.py` | 存在 |
| 3 | `auto_pm/ui/qml/boss_main.qml` | 存在 |
| 4 | `auto_pm/ui/qml/bridges/pm_cockpit_bridge.py` | 存在 |
| 5 | `auto_pm/ui/qml/components/ActivityTimeline.qml` | 存在 |
| 6 | `auto_pm/ui/qml/views/BossCockpitView.qml` | 存在 |
| 7 | `tests/contracts/test_pm_cockpit.py` | 存在 |
| 8 | `tests/core/test_pm_cockpit_service.py` | 存在 |
| 9 | `tests/qml/test_boss_cockpit_view.py` | 存在 |
| 10 | `tests/qml/test_pm_cockpit_bridge.py` | 存在 |

**B. 来自发布线 H11A/H11C（在 R 线基线上引入）**

| # | 路径 | 基线状态 | 说明 |
|---|---|---|---|
| 11 | `auto_pm/contracts/decision_package.py` | 存在 | 冲突 |
| 12 | `auto_pm/application/core/work_registry_service.py` | 存在 | H11A |
| 13 | `auto_pm/application/core/continuity_execution_service.py` | 存在 | 冲突 |
| 14 | `auto_pm/infrastructure/continuity_store.py` | 存在 | 自动合并，需语义核验 |
| 15 | `auto_pm/ui/cli/continuity.py` | 存在 | 冲突 |
| 16 | `tests/contracts/test_decision_package.py` | 存在 | H11A、H11C |
| 17 | `tests/core/test_work_registry_service.py` | 存在 | H11A |
| 18 | `tests/core/test_legacy_terminal_lease_fence.py` | 计划新增 | H11C |
| 19 | `tests/infrastructure/test_continuity_store.py` | 存在 | 两侧都改；H11A 侧亦新建同名文件，属 add/add 冲突 |
| 20 | `tests/cli/test_continuity.py` | 存在 | H11A、H11C |

**C. 只读对照（必须与 R 线基线字节一致，不得修改）**

| # | 路径 | 基线状态 |
|---|---|---|
| 21 | `auto_pm/ui/cli/git_hook.py` | 存在 |
| 22 | `auto_pm/infrastructure/git_hook_enforcer.py` | 存在 |
| 23 | `tests/cli/test_git_hook.py` | 存在 |
| 24 | `tests/infrastructure/test_git_hook_enforcer.py` | 存在 |

治理证据对象（CHG、Decision、台账）在控制根按正常流程落账，不计入上述路径，也不复制进候选；台账文档冲突不进入候选。

## 5. 整合合同

### 5.1 引入方式
- 在**全新隔离工作树**中以 `70d7e093`（R 线，已含 Hook 修复）为起点建立新分支；不得 rebase、reset 或改写 `d200eb9b`、`e05fafa1`、`70d7e093`、`e648e0b4`、`0b724997` 及其所在分支。
- 第一步引入 U 线：只取 `d200eb9b` 相对 `d59120c7` 的 §4-A 十个产品路径差异（预期无冲突）。
- 第二步引入发布线：只取 `e648e0b4` 与 `0b724997` 的 §4-B 产品路径差异，不引入它们的 CHG/台账证据文件。
- 三条线须保持可区分：建议三次独立整合提交（U、H11A、H11C），或一次合并提交并在证据中列出各线贡献。

### 5.2 冲突解析规则
1. **只做并集**：任一侧新增的函数、分支、测试不得丢失；同一函数两侧都改时，两侧语义都必须保留并以测试证明。
2. `tests/infrastructure/test_continuity_store.py`：保留 R 线侧既有测试全文，再追加 H11A、H11C 侧的测试，不得覆盖。
3. 每个冲突文件形成一条**解析记录**（冲突块、取舍、依据），随 Checkpoint 交付。
4. 禁止为通过测试而删除、跳过或放宽任一侧的既有断言。

### 5.3 事件兼容规则
- M2 读取路径必须**接受** `WORK_ADJUDICATED` 与 `RUN_LEGACY_LEASE_FENCED`（含 schema `work-adjudication.v1`、`legacy-terminal-lease-fence.v1`），且不得因它们对当前 Mission、Resume 或活动投影产生拒绝或错误。
- 若演练证明需要修改读取代码，修改必须：向前兼容、对未知事件保持 fail-closed 的原有语义（只是显式登记这两类）、并有针对性测试；且只能落在 §4 已授权的路径内。**需要 §4 之外的路径时立即停止并修订本卡。**

## 6. 门禁矩阵

在候选的 SW008 项目根、使用主工作区 `.venv\Scripts\python.exe -B` 执行。

**G1 并集回归**（先在三个来源尖端各自取得同一集合的结果作为对照；差异为 0 新失败才算通过）：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/contracts tests/core tests/infrastructure tests/cli tests/qml
```

结果取值只有四种，不得自造：`PASS`（命令完整执行，无失败）、`PASS_WITH_BASELINE_EXCEPTION`（完整执行，全部失败都在例外清册且每项都有来源对照原始输出）、`UNVERIFIED`（命令未能完整执行，或存在无来源对照的失败/崩溃）、`FAIL`（存在新增失败）。原始命令、Exit Code 与输出必须原样归档，失败输出不得删除或改写。

**例外清册**（首轮执行已核实，验证 Run 须重新核实并以原始输出为准）：

| 编号 | 内容 | 来源对照 |
|---|---|---|
| E-G1-1 | `tests/core/test_implementation_card_service.py` 三项失败：`test_verify_binds_terminal_evidence_and_closes_atomically`、`test_verify_rejects_non_exact_final_commit_without_mutating_card[extra]`、`[missing]`（失败点为 `ImplementationCardService.dispatch` 的前置检查，不在任何 owned path） | 在 `70d7e093` 与 `d200eb9b` 上以同一命令得到同名同数量失败；`0b724997` 无该测试文件 |
| E-G1-2 | `tests/qml` 整组在 Windows 上因 Qt access violation 崩溃（pytest-qt `_process_events`），收集 206 个、通过 181 个后进程中止 | `d200eb9b` 上同一命令在同一位置崩溃；`70d7e093`（203 个）全部通过；deselect 崩溃点测试后候选与 `d200eb9b` 均为 205 passed，该测试单独运行均通过 |
| E-G1-3 | 五目录单进程命令在候选上于第 123 个测试处崩溃（`tests/contracts/test_decision_package.py::test_runtime_decision_accepts_matching_legacy_version_anchor[100]`，其前有 `tests/qml/test_pm_cockpit_bridge.py` 等 Qt 测试） | 2026-09-30 已按下列“单进程崩溃诊断”执行一次，结论 (c)：同一棵候选树、同一顺序一次崩溃一次通过，属间歇性时序崩溃；在不含 H11 的 `e8d9b3e5` 上同样崩溃，`d200eb9b` 单次未崩溃，无法归因；见 `.auto-pm/reports/m2-gov-bl02/G1_single_process_diagnosis.md`。随后按下列“有界稳定性探测”再执行一轮（2026-09-30，764 秒）：23 个固定 node ID、固定顺序，候选 3/3 崩溃，**R 来源 `70d7e093`（不含 U04B 与 H11）3/3 崩溃，崩溃栈与崩溃点与候选相同**，U 来源 `d200eb9b` 0/3 崩溃；证据 `.auto-pm/reports/m2-gov-bl02/g1_probe/`。据此 E-G1-3 登记为**来源复现的既存崩溃**（不宣称已修复），验证 Run 须重新取得同类来源对照。**E-G1-3 在未取得来源复现证据前不是基线例外**；用户若接受其风险，只能按 §8 第 8 步记录“有条件验收”，G1 原始结论仍为 `UNVERIFIED` |

**有界稳定性探测（E-G1-3，最后一轮）**：使用单进程崩溃诊断得到的 22 项复现集合加崩溃点共 23 个 node ID（由 ddmin 日志与脚本确定性重建，须先证明 23 个 ID 在候选、`d200eb9b`、`70d7e093` 上都能被收集）；固定顺序、解释器与环境；候选、U 来源 `d200eb9b`、R 来源 `70d7e093` 各最多 3 次，串行轮转执行，总上限 45 分钟；不再做 ddmin、不再跑全套、不修改源码。判读：来源也复现——记录来源证据，E-G1-3 可登记为“来源复现的既存崩溃”（仍不宣称已修复）；仅候选复现或全部未复现——G1 保持 `UNVERIFIED`，有限次数未崩溃不能证明问题不存在。

**单进程崩溃诊断（有界，一次性）**：固定实际测试顺序（`--collect-only -q` 在固定 seed 洗牌后的顺序）、同一解释器与同一环境；用临时排序插件在候选与来源上回放崩溃前缀，用 ddmin 求最小复现集，再把最小复现集在 `d200eb9b`（含 U04B）与 `70d7e093` 上回放。不得反复盲跑整套。诊断结论只有：(a) 最小复现集完全落在 U04B 线既有测试内并在 `d200eb9b` 复现——则 E-G1-3 可并入 E-G1-2；(b) 只在候选复现——则为整合新增因素，G1 判 `FAIL`；(c) 无法判定——G1 保持 `UNVERIFIED`。

**分进程执行 G1 的批准条件**（这是相对 V0.3 的执行方式变更，须经用户批准本卡后方可使用）：按目录分进程执行，且必须同时提交 node ID 完整性证明：`--collect-only -q` 得到的全部 node ID（数量须与五目录单进程收集数一致）与各子进程 `-v` 输出中带结果的 node ID 逐一比对，未执行数必须为 0；崩溃点及其后未执行的测试必须以 `--deselect` 加单独回放补足并逐个记入结果；证明脚本放在临时目录，运行后删除，脚本字节 SHA-256 与输出归档。满足以上条件时该结果最多取 `PASS_WITH_BASELINE_EXCEPTION`，且必须同时报告单进程命令的原始结果；分进程覆盖完整只证明每个测试都有结果，不证明混合运行稳定，单进程崩溃仍按 E-G1-3 处理。

**G2 加法检查**：证明候选相对三个来源尖端（`d200eb9b`、`70d7e093`、`0b724997`）的差异都是纯新增或保留，各来源新增的函数与测试名在候选中都存在。检查脚本放在临时目录，运行后删除；结果记录进证据。

**G3 数据库副本兼容演练**：把 §3.2 的副本放入一个**全新的临时控制根**（`git init`，含 `.auto-pm/continuity.db` 副本与所需 Decision 文件），从**候选源码**（不是稳定 release）对该临时根执行：`pm resume`、驾驶舱活动投影读取（U04B 的时间线）、`adjudication-evidence`、`legacy-terminal-evidence`，以及对全部事件的 schema/哈希链校验读取。要求：全部成功、无 fail-closed 误拒、事件链 0 断裂。演练全程不得触碰真实库，结束后删除临时根。临时根的最小只读元数据集：`SYS-2026-001_WorkspaceGovernance/workspace_registry.json` 与 `PM_SESSION_SYS-2026-001.md`、项目目录内的 `.copier-answers.yml`（项目锚点）、`00_Infrastructure/auto_pm/` 下的 `active_release.json`、`previous_release.json`、`deployment_manifest.json` 与被指向的稳定 release 目录，以及 `.auto-pm/decisions/`。候选源码以 `AUTO_PM_WORKSPACE=<临时根>` 加 `-I` 子进程并把候选项目根置于 `sys.path` 的方式加载，此时 `pm resume` 的 `RUNTIME_IDENTITY_UNVERIFIED`（`loaded_package_outside_workspace`）是演练方式带来的，不算误拒。**例外 E-G3-1**：`ContinuityStore.list_missions(include_terminal=True)` 对一个历史 Mission 抛出“Mission timestamps must be inside the authority validity window”，稳定 release `1.3.3-0b72499`、`70d7e093`、`d200eb9b` 读同一份副本抛出同一错误，属既存数据/读取行为，须在验证 Run 中重新对照，不得因它放宽对 H11 事件的读取要求。

**G4 静态质量**：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m ruff check --no-cache <§4 中 A、B 的 17 个 Python 文件>
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m mypy --strict --no-incremental <同一组 17 个 Python 文件>
git diff --check
```

3 个 QML 文件（`boss_main.qml`、`ActivityTimeline.qml`、`BossCockpitView.qml`）不得传给 Ruff/Mypy；其结构、接线和导航由 G1 中 `tests/qml/test_boss_cockpit_view.py`、`tests/qml/test_pm_cockpit_bridge.py` 及相关 QML 回归覆盖。不得用 `--follow-imports=skip`、文件级抑制、删除 QML 断言或缩小测试集合换绿；若既存依赖穿透失败，报告精确基线差异并停止。

**G5 可复现的临时构建与回退演练（不进入真实容器）**：

前置条件：G1～G4 已通过；三条整合提交已形成；候选 `HEAD` 固定且工作树洁净。G5 只允许使用系统已核验存在的 `git archive`、Windows `bsdtar`、PowerShell 与主工作区 Python；不得调用或新建来源不明的一次性 release 构建脚本。

1. 使用 `git archive --format=tar --output <TEMP>\candidate.tar HEAD:<SW008项目根> auto_pm templates` 导出候选载荷，并用 Windows `bsdtar`（`C:\Windows\System32\tar.exe --options hdrcharset=UTF-8 -xf`，缺少该选项时含中文文件名的 `templates/` 会解包失败）解包到 `<TEMP>\00_Infrastructure\auto_pm\releases\1.3.3-<候选短SHA>`；导出输入必须是候选 `HEAD`，不得从脏工作树复制。
2. 在临时目录内生成 `release_meta.json` 与 `deployment_manifest.json`：manifest 必须枚举载荷的全部普通文件及 SHA-256；随后反向扫描目录，证明“manifest 缺失 = 0、孤儿文件 = 0、哈希不一致 = 0、`__pycache__/.pyc` = 0”。生成与校验逻辑只能写在 `<TEMP>`，原始命令、脚本字节 SHA-256 和输出必须归档到证据目录，演练后删除临时脚本。
3. 复用 G3 的临时控制根与数据库副本，复制根入口所需的最小只读元数据；把当前稳定 release `1.3.3-0b72499` 只读复制为临时 previous 槽。严禁写真实 `00_Infrastructure/auto_pm`。
4. 在临时控制根写入**合成** active/previous 指针：先 active=候选、previous=`1.3.3-0b72499`，执行临时根 `main.py pm resume SW-2026-008 --json`，要求 `configured_release_id == effective_release_id == 候选`、`runtime_load_path` 指向候选载荷、`fallback_reason == ""`；再把 active 切回 `1.3.3-0b72499` 并重复根入口身份校验，证明回退有效且无 fallback。
5. 两次身份输出、指针字节、manifest、release_meta、候选提交 SHA 与 exact-tree 结果一并写入 Checkpoint 证据。任一步依赖真实 release 指针、真实容器写入或无法达到 0/0/0 时，G5 失败并停止。

**G6 未改动核验**：§4-C 的四个文件与 `70d7e093` 字节一致；候选工作树洁净，仅 §4-A、§4-B 的路径出现于提交。

## 7. 实施授权签字门与 GUI 合同

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-GOV-BL02 V0.4` |
| 实施批准 | `PENDING` |
| 最终验收 | `PENDING` |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| Git 起点 | `70d7e093c92bc982e686322b1b59c62155ca628d` |
| 治理任务真源 | WBS 提交 `a385452cde480090d27175f1b4d2ccfe358a4cec`，SHA-256 `AEBB2AE678D483A19E499C3A3706FD5C880643EF3EB689B2B4093D0665045EC6` |
| Owned Paths | §4-A、§4-B 的 20 个修改路径；§4-C 的 4 个路径只读 |
| 执行模型 | `Claude Sonnet 5.5`（首轮由用户在对话中确认；V0.4 回执须写明） |
| 明确禁止 | 范围外路径、修改 §4-C、直接 SQL、canonical 写入、历史改写、合并、推送、部署、真实 release 切换 |

本表仅是待签对象声明，不是授权真源。卡片 SHA-256 不得写入卡片自身；审批时必须在外部 Approval Receipt 中绑定：卡片完整字节 SHA-256、Git 起点、WBS 提交与 WBS SHA-256、20+4 路径、允许动作、禁止动作、执行模型、审批人和审批时间。

### 7.2 授权成立与失效

1. 只有用户明确批准本卡 V0.4 的完整物理字节后，才能创建 CHG、Decision、Work/Run（含 §8 的恢复授权与验证 Run）。V0.3 的批准回执 `APPROVAL-20260929-M2-GOV-BL02` 只对 V0.3 字节有效；V0.4 须有新的 Approval Receipt，且回执必须包含执行模型、20+4 路径、允许与禁止动作（首轮回执缺这些字段）。Agent 不得把本轮“允许修订卡片”解释为“批准实施”。
2. Approval Receipt、CHG 与 Decision 必须通过高层服务建立；聊天记录仅作为审批证据来源，不得直接写数据库或伪造用户签字。
3. 卡片、Git 起点、WBS 真源、Owned Paths 或禁止事项任一漂移，旧审批立即失效，必须停止并重新报批。
4. 实施批准与最终验收是两个独立签字门。执行 Agent 只能提交候选与证据，不能代替用户完成最终验收或 CHG 收口。

### 7.3 GUI 最小合同

后续驾驶舱审批页至少必须展示并机器校验：卡片版本与 SHA-256、Git 起点、WBS 真源、20 个修改路径与 4 个只读路径、执行模型、允许/禁止动作、预计 CHG/Decision/Work/Run，以及 `批准实施 / 拒绝 / 要求修订` 三个互斥动作。卡片或基线漂移必须醒目标红并 fail-closed；实施审批与最终验收使用独立按钮和独立回执；GUI 只能调用高层领域服务，禁止直接改 Markdown、Decision JSON 或 canonical 数据库。

## 8. 治理执行顺序（V0.4：整合 Run → 最终不可变候选 → 收口整合 Run → 验证 Run）

**已完成部分（V0.3 授权下，2026-09-29～30，不得重做）**：§3 预检、CHG `CHG-SCPT-2026-356`、Decision `DEC-20260929-BL02CODE`、Work `WORK-SW008-M2-GOV-BL02-001`、整合 Run `RUN-SW008-M2-GOV-BL02-001`、三条整合提交与最终不可变候选 `7cfe227e7bf4a7df57d95644a80ea2652ef5a9cc`（见 §12）。V0.4 **从现有最终候选继续验收**：不得重建整合工作树、不得新建整合 Run、不得改写/reset/重做任何整合提交、不得在 `7cfe227e` 之后新增代码提交。后续卡片若从零执行，第 1～5 步的通用顺序为：预检 → 用户签字与 CHG/Decision → 创建 Work 与整合 Run → 三条整合提交（整合 Run 不承担 Checkpoint）→ 冻结最终候选。

**V0.4 待执行步骤**：

1. **用户签字**：用户批准本卡 V0.4 完整物理字节，生成新的 Approval Receipt（含卡片 SHA-256、最终候选 SHA、执行模型、20+4 路径、允许/禁止动作），并把 V0.4 审批记录、卡片哈希与最终候选追加到 `CHG-SCPT-2026-356`；Receipt 显式关联既有 `DEC-20260929-BL02CODE`。Agent 只准备脚本，不代签。
2. **恢复链一次授权**（由用户批准并运行脚本；Agent 不得自行补偿、不得写 SQL）。服务代码核实的前置条件：
   - 独立恢复 CHG（与 `CHG-SCPT-2026-356` 不同）；恢复 Decision 为无条件 approved，`runtime_capability` 精确为 `settle_expired_run` / 目标 `RUN-SW008-M2-GOV-BL02-001` / 结果 `CANCELLED`，`approved_files` 覆盖 `.auto-pm/continuity.db`；
   - 恢复 Work 为写入型、`IN_PROGRESS`，授权引用恢复 Decision，scope 覆盖 `.auto-pm/continuity.db`；恢复 Run 位于**控制根主工作树**、`RUNNING`、有效 lease，owned 覆盖 `.auto-pm/continuity.db`；
   - **Git 绑定**：原 Decision `DEC-20260929-BL02CODE.json` 与恢复 Decision 文件必须被 Git 跟踪、相对 HEAD 无脏改，且与恢复 Run 的 `git_head` 中的 blob 一致；首次结算时控制根当前 HEAD 必须精确等于恢复 Run 的 `git_head`。因此须先以一次仅含这两个 Decision 文件（及必要的恢复治理文件）的提交固化，再在该 HEAD 上启动恢复 Run（先例：`58ac6a03` 固化 H11B 结算 Decision）。该提交走正常 Hook，只 add 精确路径；
   - 结算：`continuity run settle-expired` 把目标 Run 前向结算为 `CANCELLED`，核验旧 lease token 失效（结算后以旧 token 续期/迁移必须被拒绝）；**保留原 BL02 Work**，供第 3 步唯一验证 Run 使用（结算后目标 Work 的实际状态及能否再起 Run 必须先经演练证明）；
   - 恢复链自身收尾：恢复 Run `RUNNING → VERIFYING → SUCCEEDED`（释放 lease），恢复 Work `IN_PROGRESS → VERIFYING → ACCEPTED → CLOSED`（先例：`WORK-SW008-H11B-SETLB-001`）；不得留下活动恢复 Run 或未释放 lease；
   - **演练先行**：上述全部步骤先在隔离副本（`git init` 临时控制根 + canonical 数据库副本 + Decision/CHG 副本 + 稳定 release）完整演练通过，并归档命令、输出与前后数据库事件差异，再交用户批准真实执行；
   - 进程检查：`RUN_STARTED`/`EXECUTION_START_CLAIMED` 事件缺失只证明没有服务启动记录；结算前须另行列出系统进程并确认无以该 Run 工作树为 cwd 或命令行的 python/pytest/git 进程，结果归档。
3. **唯一一个验证 Run**：同一 Work、同一 CHG、同一 20 个 owned paths，工作树 `.auto-pm/worktrees/m2-gov-bl02`，`git_head` 等于 `7cfe227e…` 且工作树洁净；lease 最长 3600 秒并按需续期。验证 Run 内执行 §6 全部门禁，创建绑定最终 `HEAD` 与当前字节的 Checkpoint，evidence 必须指向真实报告文件及其 SHA-256，不得以一句“测试通过”代替。创建该 Run 的命令由用户运行或明确放行。
4. **结论与终态**：
   - G1 为 `PASS` 或 `PASS_WITH_BASELINE_EXCEPTION`（每项例外均有来源对照原始输出）：可推进验证 Run 与 Work 终态、SW008 台账 reconcile；
   - G1 为 `UNVERIFIED`：**不得**推进 `SUCCEEDED / ACCEPTED / completed`，只提交现状报告。用户若决定接受未对照风险，须**单独签署“有条件验收”回执**（独立于实施批准与最终验收），写明 G1 原始结论 `UNVERIFIED`、所接受的具体例外编号与用途限制（仅作为 R1/R2/U05 的开发基线；不放行合并、推送、部署或 release 切换）；有条件验收**不改写** G1 结论、不把风险登记为基线例外；控制面终态是否可在有条件验收下推进由该回执明确规定；
   - G1 为 `FAIL`：停止。
   服务层 `continuity work transition --to ACCEPTED/CLOSED` 不校验执行人身份，因此 BL02 Work 的 `ACCEPTED`/`CLOSED` 与验证 Run 的 `SUCCEEDED` 均由**用户运行的收口脚本**执行，Agent 只提交证据与脚本。**CHG 最终收口由用户执行**。
5. 停止并提交证据报告；合并、推送、部署、release 切换均需另行授权。

## 9. 硬停止条件

出现任一情况立即保留现场并停止，不得补丁式扩大：

- 来源 SHA、路径存在性、命令存在性或三线互不包含关系与本卡不符；
- 需要 §4 之外的路径，或需要修改 §4-C 的文件；
- 需要修改 canonical 数据库、历史事件、Checkpoint、release 指针或 Hook 安装；
- G1 出现新增失败、G3 出现误拒或事件链断裂而无法在 §5.3 授权范围内修复；
- 只能通过 skip、ignore、mock canonical 或降低门禁才能变绿；
- 出现未知进程、未回收执行句柄或第二条脏路径。
- 卡片 V0.4、Approval Receipt、WBS 真源、Git 起点或执行模型身份无法相互证明。
- G5 需要真实 release 指针写入、来源不明的一次性构建脚本，或临时载荷 exact-tree 不是 0/0/0。
- 任一 Run 的 lease 在其终态之前过期，或需要在最终 HEAD 之后新增提交；
- 需要绕过 `Git baseline drift` 检查、修改既有 Run 的 `git_head`、补偿脚本或直接 SQL 才能推进；
- 恢复链演练未通过，或演练显示结算后原 BL02 Work 无法再起验证 Run；
- 单进程崩溃诊断结论为 (b)（整合新增因素）。

## 10. 交付物

1. 四个冻结起点 SHA、数据库副本的 SHA-256 与事实表；
2. CHG / Decision / Work / 整合 Run / 恢复授权（如有）/ 验证 Run / Checkpoint ID；
3. 每个冲突文件的解析记录与最终 diff、最终 SHA-256；
4. G1～G6 矩阵（G1 使用 §6 的四种取值）、例外清册与每项例外的来源对照原始输出、原始命令、Exit Code 与输出位置；分进程执行时的 node ID 完整性证明；
5. G3 演练的对象清单与结果（含被演练的事件类型与数量）；
6. 不可变提交 SHA（或三个整合提交的 SHA）；
7. 对“该候选是否可作为后续整改 R1/R2 及 U05 的唯一基线”的结论：`PASS / FAIL / UNVERIFIED`。
8. Approval Receipt、卡片 SHA-256、WBS 真源校验、执行模型身份与两次独立签字门状态。

不得仅以聊天陈述代替物理证据。

## 11. 与其他任务的关系

- 本卡是整改 R1（B+C）、R2（D）与 U05 的前置：U05 依赖 U04B，而 U04B 目前并不在任何含 Hook 修复或 R1 的分支上。
- 本卡不改变 H11 的任何结果，也不重写任何历史事件或 Checkpoint。
- 是否部署由整改 R2 之后的“一次集成部署”另行请求用户批准；本卡的 G5 只做临时演练。
- 控制根 WBS V3.0.15 与已验收 V3.0.16 候选的同步/合并仍是卡 025 登记的独立边界；本卡不得顺带修改控制根 WBS，也不得因此把已验收候选降级为未验证。

## 12. 第一轮执行记录（2026-09-29～30，事实，供批准 V0.4 时核对）

- 授权：`APPROVAL-20260929-M2-GOV-BL02`（对应 V0.3 字节 SHA-256 `d2e03f3d…5ff49`）、`CHG-SCPT-2026-356`、`DEC-20260929-BL02CODE`（20 个路径，无运行态能力）；执行模型 Claude Sonnet 5.5，用户在对话中确认。
- 候选：分支 `codex/m2-gov-bl02-unified-baseline`，`e8d9b3e5`（U04B）→ `4e08b0dd`（H11A）→ `7cfe227e7bf4a7df57d95644a80ea2652ef5a9cc`（H11C），均通过正常 Hook；变更集恰为 20 个 owned paths，四个只读 Hook 路径与 `70d7e093` 字节一致。
- 整合 Run：`RUN-SW008-M2-GOV-BL02-001`，`RUNNING`，绑定 `70d7e093`，lease 于 2026-09-30 05:33 UTC 过期（version 3），无 Checkpoint；Work `WORK-SW008-M2-GOV-BL02-001` 为 `READY`。
- 门禁：G2、G4、G5、G6 通过；G3 通过（含 E-G3-1）；G1 为 `UNVERIFIED`（见 §6 例外清册）。证据目录 `.auto-pm/reports/m2-gov-bl02/`。
- 过程说明：首轮中，Work 授权与 Run 启动在用户尚未选择方案时由 Agent 发起的一批命令中执行，用户随后表示认可；该事实记录在案，V0.4 要求此类创建 Work/Run 的命令由用户运行或明确放行（§8 第 3 步）。
- 2026-09-30 E-G1-3 有界稳定性探测（764 秒/上限 2700 秒）：23 个固定 node ID（由 ddmin 日志确定性重建，77 次试验逐一吻合；三个来源均可收集），候选 3/3 崩溃、R 来源 `70d7e093` 3/3 崩溃（崩溃栈与崩溃点相同）、U 来源 `d200eb9b` 0/3；证据 `.auto-pm/reports/m2-gov-bl02/g1_probe/`、`G1_single_process_diagnosis.md`。
- 2026-09-30 恢复链与验证 Run 隔离演练（临时 `git init` 控制根 + canonical 库副本 + 稳定 release `1.3.3-0b72499`，脚本 `bl02_v04_1_approve.sh`、`bl02_v04_2_recovery.sh`、`bl02_v04_3_verify_run.sh` 以 `BL02_ROOT` 指向演练根原样运行）：V0.4 审批记录追加到 CHG-356（状态仍为 implementing）；恢复 CHG、Decision `DEC-20260930-BL02RSET`、两个 Decision 文件的 Git 绑定提交、恢复 Work/Run、`settle-expired` 使 Run 001 → `CANCELLED`（旧 lease 版本 3 → 4，旧 token 续租被拒）、恢复 Run `SUCCEEDED`（事件含 `lease_release`，恢复 token 续租被拒）、恢复 Work `CLOSED`；原 BL02 Work 结算后仍为 `READY`，验证 Run 002 在其上启动，`git_head = 7cfe227e`，Checkpoint 无 `Git baseline drift`、无脏路径；Run 002 与 Work 终态路径可达；台账 0/0/0，resume 无冲突；演练库事件 2578 → 2598、哈希链 0 断裂、既有事件未变；恢复脚本重跑 0 新事件、0 新提交。证据 `.auto-pm/reports/m2-gov-bl02/rehearsal/`。演练中发现并修复了两处脚本缺陷（进程检查匹配到自身、失败原因取错行）。
