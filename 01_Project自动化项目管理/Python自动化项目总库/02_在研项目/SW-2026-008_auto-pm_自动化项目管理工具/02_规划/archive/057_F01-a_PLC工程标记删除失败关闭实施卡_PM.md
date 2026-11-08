# F01-a｜删除 PLC 工程标记后提交钩子与阶段门失败关闭实施卡

> 卡片编号：`CARD-SW008-M2-F01A`
> 对应 WBS：`M2-F01A`（WBS V3.0.22 §4.8；台账 `TD-SW008-078`；需求依据 DECISIONS 的 D-001）
> 版本：`V1.0`（2026-10-06，一次定稿；执行期间不得修订，见 §9）
> 状态：`PLANNED / NOT_AUTHORIZED`（定稿，待授权；授权方式见 §7；**没有任何预授权**）
> 档次：产品档（规则文档 §4：全量九组回归、相关静态与场景门禁、严格变异检查）
> 依赖：TD2（卡 055）已提交 `1956dd9a`，其 CHG-DOCU-2026-017 已由用户验收收口；WBS 修订 6 已提交 `0b56b2f4`（CHG-DOCU-2026-027 completed）
> 隔离基线：`1956dd9a003bca2dab379d7e368aaf78c60d7170`（分支 `codex/m2-td2-docs`）
> 治理任务真源：WBS 提交 `0b56b2f4de2b35effea7e100ab2c56bc1cec0bc7`（V3.0.22）
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或能力不低于它的模型；实际执行者 `Claude Sonnet 5.5`
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

> V1.0 定稿说明：本卡的 6 个参考文件来自 GPT 在临时副本里冻结的 overlay（`.auto-pm/reports/m2-f01-survey-gpt-20261006/overlay-freeze-001/`）。**GPT 交付时 pytest、ruff、mypy 都没有运行过**；我在全新的基线副本上运行后发现并修了四处（详见 `.auto-pm/reports/m2-f01a/PROVENANCE.md`）：（一）一个新测试在“工程目录含中文”时断言写错（Git 输出被转义，产品代码没问题）；（二）两个文件有 ruff 的导入排版问题；（三）**一个真实的产品回归**：新钩子在“没有 Git 的目录”里也拒绝，破坏了既有测试 `tests/cli/test_git_hook.py::test_enforce_pre_commit_reports_unrelated_ledger_error_without_blocking`——这是跑 cli 组才暴露的，已改成按设计（D-001）保持旧合同，并补了一个测试；（四）因此新增测试由 27 个变成 28 个。三个产品文件我读完了全部差异（新增模块 232 行，钩子 +6 行，阶段门 +13 行）；三个测试文件新增的行我没有逐行审读，其有效性由全量回归与严格变异检查证明。参考文件、变异计划与脚本、判卷脚本、安装脚本与演练输出归档于 `.auto-pm/reports/m2-f01a/`，仅供参考；执行者不得现场修订本卡、扩大路径或放宽门禁；遇到本卡未覆盖的情况按 §9 停止并报告。

## 1. 背景与已核实事实（2026-10-06，基线 `1956dd9a`，均为命令、源码或日志核验）

1. **缺陷（独立审计 F01，台账 `TD-SW008-078`）**：删除一个 PLC 工程的标记文件 `.plc.json` 之后，提交钩子与阶段门**同时**失效——钩子靠“暂存快照里有没有标记”识别 PLC 工程，阶段门靠“工作区里有没有标记”，标记一删，两处都把这个工程当成“不是 PLC 工程”而放行，“PLC 文档与代码一致”这条防线可以被一个删除动作绕过。
2. **修法（决定 D-001，我与你在 2026-10-05/06 的讨论定下的 Git 最小方案）**：以 **Git HEAD 为历史身份来源**，不新增存储、不登记、不读缓存与数据库：钩子在最前面比较“HEAD 里的标记路径”与“暂存区里的标记路径”，HEAD 有而暂存区没有就拒绝；阶段门比较“HEAD”与“工作区”，同条件保留原有的 PLC 拦截项。**不放行任何改名或移动**（仅标记移动、整个工程移动、移入 archive 全部拒绝，提示“移动或退役请走 F01-b 的授权”）；合法移动与退役归 F01-b 另卡。已核实的非 Git 工作区与未出生仓库保持旧合同；任何 Git 读取故障（HEAD 损坏、提交对象缺失、权限失败、工程在所选仓库之外）一律失败关闭。
3. **残余（如实保留，写进台账 `TD-SW008-078`）**：已经进入 HEAD 的标记删除认不出（`--no-verify`、其他克隆、历史上的同类缺陷）；HEAD 身份不是持久登记，不据此关闭历史身份债务；并发修改 HEAD 与暂存区的全部时序窗口没有消除（读取前后核对可见漂移，仍有窗口）；阶段门在多个 Git 命令上的累计延时只测过一次（见下）。
4. **性能实测**（本仓库约 8000 个文件，基线工作树）：`removed_index_markers` 一次 0.3～1.7 秒，`marker_in_head` 一次约 0.2 秒；每次提交多出约一两秒，我认为可接受。
5. **新增测试**：共 **28** 个（钩子测试文件 13、阶段门测试文件 8、真实 pre-commit 测试文件 7）；三个文件的收集数由 15/6/3 增加到 28/14/10（旧测试字节全部保留为文件前缀，确切的节点清单归档在 `new_nodes.json`，G3 逐个比对）。
6. **我在全新基线副本上的演练**（2026-10-06，非受治理执行，受治理执行里完整重跑，不采纳这些输出；输出在 `.auto-pm/reports/m2-f01a/gates_rehearsal2/`）：
   ① `ruff check` 与 `mypy --strict` 对 6 个文件零问题、`git diff --check` 通过；
   ② G1：26 passed、1 failed（既存，与基线相同：26 passed、1 failed）；
   ③ 三个测试文件整体 **52 passed**（0:01:15），含真实 Git 仓库与真实 pre-commit 进程；
   ④ **严格变异检查**：12 个变异全部被点名的测试以**真实断言失败**抓住，点名的测试先在未变异字节上为绿，每个文件逐字节还原（第一次运行有两个没抓住：一个变异与另一处检查等价、一个变异让测试以异常而非断言失败，已改写变异后重跑，旧输出保留在 `gates_rehearsal_attempt1/`）：
   - M01-guard-call-neutralised：the pre-commit hook must refuse when a HEAD marker is gone from the index
   - M02-stage-ignores-head-marker：the stage gate must keep its BLOCKER when the HEAD marker is missing from the work tree
   - M03-archive-move-allowed：a marker moved into an archive folder gets no exception
   - M04-any-head-failure-is-unborn：a corrupt HEAD is a read failure, never an unborn repository
   - M05-project-outside-repo-borrows-head：a project outside the selected repository cannot borrow its HEAD
   - M06-guard-skipped-on-empty-snapshot：the marker check runs even when the staged snapshot is empty
   - M07-hook-swallows-guard-errors：a Git read failure in the hook fails closed
   - M08-stage-verification-error-passes：a failed marker verification keeps a failing stage item
   - M09-hint-removed：the refusal names the F01-b authorization path
   - M10-unborn-hook-refuses-everything：an unborn repository still checks its new PLC project instead of refusing it
   - M11-unborn-stage-gate-errors：an unborn project uses its current PLC document contract in the stage gate
   - M12-non-git-workspace-refused：a verified non-Git workspace keeps the old contract (no removed markers, no refusal)
   ⑤ **回归的一个子集**（与 V04/卡 054 的真实门禁输出逐组对照，失败集合相同）：
   - application：174 passed（基线 174）、0 failed、0 skipped（3.37s）
   - plc：144 passed（基线 144）、0 failed、0 skipped（16.38s）
   - change：230 passed（基线 230）、0 failed、0 skipped（3.74s）
   - contracts：210 passed（基线 210）、0 failed、1 skipped（25.79s）
   - infrastructure：68 passed（基线 55，另加新测试 13）、0 failed、0 skipped（0:02:12）
   - qml_debounce_alone：1 passed（基线 1）、0 failed、0 skipped（1.56s）
   - cli：335 passed（基线 328，另加新测试 7）、0 failed、1 skipped（0:09:08）
   - core 里的阶段门两个文件：24 passed。
   **九组回归的 `core`、`qml`、`rest` 三组没有在演练里跑**（它们不含本卡文件，且各需 8～100 分钟），受治理执行里全部重跑；演练里的子集已经暴露并修掉了上面的回归。
7. **基线数字**（本卡基线与卡 054 提交的代码字节相同——TD2 只改文档——所以直接沿用卡 054 真实门禁的输出 `.auto-pm/reports/m2-p1fix/gates/g2_candidate/`）：既存失败为 core 3 个、rest 15 个、G1 集合 1 个（`test_no_conditional_assertion_skips`）；G1 集合在基线上 **26 passed、1 failed（既存）、0 skipped**。
8. **明确不在本卡**：F01-b（合法移动与退役入口）；持久登记；`checker.py`、`wrapper`、Workbench、contracts、数据库、模板；已进入 HEAD 的删除的追溯；其他 Checker 与验收路线、硬件与 PLC 编译；V05 系列；任何产品文件之外的修改；Hook 脚本本身、release、部署。

## 2. 单一目标（用户故事与完成定义）

作为用户，我希望删除 PLC 工程标记不能让“PLC 文档与代码一致”这条防线失效：

1. 纯删除标记（含暂存快照为空的情形）：提交被拒绝（H16、E04），阶段门保留原拦截项（S07）；
2. 删除标记不能掩盖一个错误的接口文档（H17）；未暂存的恢复不能盖过暂存区里的删除（H18）；工作区删除而暂存区仍保留时阶段门也拦截（S08）；
3. 不放行任何改名与移动：仅标记移动、整个工程移动、移入 archive 都被拒绝并提示走 F01-b（H19、E05）；已在 HEAD 里的 archive 标记也不能删（H20）；
4. 未出生仓库照旧检查其新 PLC 工程（H21、S09）；已核实的非 Git 工作区保持旧合同（H24，以及既有的 `test_enforce_pre_commit_reports_unrelated_ledger_error_without_blocking`）；
5. Git 读取故障失败关闭：HEAD 损坏、提交对象缺失、权限失败、工程在所选仓库之外，都不被当作“无标记”或“不适用”（H22、H23、S10、S11、E06）；
6. 既有的旧测试全部保留、全部通过，九组回归与基线逐组一致（失败集合相同、通过数恰为基线加新测试数）。

依据 PM-042、PM-033、DEV-300（零崩溃、白盒日志）与 LSP 规范；规范只读。本卡无 UI 改动，HTML 原型不适用。

## 3. 实施前预检（只读，先于任何写入）

1. 核验本卡字节 SHA-256 已被外部 Approval Receipt 绑定；核验卡 055 的 CHG-DOCU-2026-017 已由用户验收收口、分支 `codex/m2-td2-docs` 仍在 `1956dd9a`。
2. 运行 `main.py implementation-card precheck --card-file` 对本卡，退出码必须为 0。
3. 核验 §4 中 5 个“存在”路径在基线上存在、1 个“计划新增”路径在基线上不存在。
4. 在隔离候选里、安装之前，对 §6 G1 集合复现基线结果（**26 passed、1 failed（既存）、0 skipped**），输出写入 `.auto-pm/reports/m2-f01a/gates/G1_baseline_candidate.txt`；不一致则停止。
5. 核验隔离候选 HEAD 等于基线且工作树干净。
6. 阅读 `.auto-pm/reports/m2-f01a/proto/` 下的参考文件与 `PROVENANCE.md`，核对 `reference_manifest.json` 中各文件与工具的 SHA-256。
7. 判卷、检查与变异脚本已在参考字节上跑通（§1.6）；工具字节一旦被证据绑定，任何修正都会使整个窗口重开。后台起长批次用 `nohup`，并确认输出文件真的开始增长。**九组回归的 `core` 组约需 1.5～1.7 小时**，所以 Run 需要续租循环（`p1_renew_loop.sh`，每 1200 秒续一次，带 6 小时上限），提交前租约须剩余 300 秒以上。**回归、真实进程测试与变异检查必须顺序执行，不得与其他重负载同时跑**（脚本已按此编排；开工时创建重负载标记 `.auto-pm/reports/HEAVY_GATES_RUNNING`，通知 GPT 不要同时跑 pytest）。

## 4. 精确 Owned Paths（6）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `auto_pm/application/core/gates/stage_gate_engine.py` | 存在 | 阶段门：HEAD 有标记而工作区没有时保留原 PLC 拦截项；核验异常按未通过处理 |
| 2 | `auto_pm/infrastructure/plc_doc_hook.py` | 存在 | 提交钩子：在“暂存快照为空”与“无 PLC 相关文件”两个提前返回之前，先拒绝“HEAD 有标记而暂存区没有” |
| 3 | `auto_pm/infrastructure/plc_git_marker_guard.py` | 计划新增 | 新增：只读 Git 辅助模块——从 HEAD 读历史工程标记、从暂存区读现有标记；读取故障失败关闭；不登记、不缓存、不读库 |
| 4 | `tests/cli/test_git_hook_plc_docs.py` | 存在 | 既有测试文件末尾追加 7 个测试（E04～E06，真实 pre-commit 进程），旧测试字节不变 |
| 5 | `tests/core/test_stage_gate_plc_docs.py` | 存在 | 既有测试文件末尾追加 8 个测试（S07～S11），旧测试字节不变 |
| 6 | `tests/infrastructure/test_plc_doc_hook.py` | 存在 | 既有测试文件末尾追加 13 个测试（H16～H24），旧测试字节不变 |

出现第 7 条脏路径即停止，不得现场扩大 Decision。治理证据对象在控制根落账，不计入上述路径；台账、WBS、需求说明本卡不改。

## 5. 合同（全部定稿，执行者不得改写含义）

### 5.1 最终字节

6 个文件的字节固定为参考字节（UTF-8、LF、无字节序标记），归档为 `.auto-pm/reports/m2-f01a/proto/` 下的同相对路径文件；`install_candidate.py` 逐字节核验后装入候选（先确认既存文件等于基线字节、新增文件不存在），不得手工改写。

| # | 路径 | 基线状态 | 最终 SHA-256 |
|---|---|---|---|
| 1 | `auto_pm/application/core/gates/stage_gate_engine.py` | 存在 | `c959164a553f33262c163e80bdf93c19fa81f765c315f2f467cfda8b0f24bc3b` |
| 2 | `auto_pm/infrastructure/plc_doc_hook.py` | 存在 | `a245b8bb1a0bcf4a35fb5b376b5c11f47d2753fd2c57ebadd4c389b669189979` |
| 3 | `auto_pm/infrastructure/plc_git_marker_guard.py` | 计划新增 | `80dc210129b1dacc893059fd12e6dd84f97a09c79c336d234851daedaef6d516` |
| 4 | `tests/cli/test_git_hook_plc_docs.py` | 存在 | `7de62aa8a307127b03eb9b6cac983c228d95e682bea8c7e19a34562d66a197ce` |
| 5 | `tests/core/test_stage_gate_plc_docs.py` | 存在 | `cd98d20db8a4663bb3393a5f215b8e71b2d51e91dea3a315be58dfacfbaabd16` |
| 6 | `tests/infrastructure/test_plc_doc_hook.py` | 存在 | `0280f98a34f47000580409f038c6c7fb9ac8992bd5774eb99503f4564247bde4` |

检查与构建工具（`reference_manifest.json` 里的 `tools/` 条目，字节固定）：

| 工具 | SHA-256 |
|---|---|
| `commit_msg.template.txt` | `cd9fb3c6b4b48450b65603273a2fc91af700b1568178e345b6d0f3c28a5861b5` |
| `g6_check.py` | `15225ec0fc1c6470dfbc1c3b275c2023ef88b48096023ef2f9abc84736b3d49f` |
| `install_candidate.py` | `456637afe467ea94ee1b3ea2e5d09b8d0627ee2b59adc491debe760d9459f9e3` |
| `m2-tools/mutation_classify.py` | `0fff21f888cb1a50094f050ef8bc3b42ea25653ba508581e3c85fa1b28d79019` |
| `m2-tools/verdict_check.py` | `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188` |
| `mutation_plan.json` | `7def0f38323a6e6090f12ed69e1e034c0e8f30b4a5c8cb8108edd872a60f6315` |
| `mutation_run.py` | `b10c05d1b92affe9108f67d861f27f1419fa426573effd76667f695194c41f53` |
| `new_nodes.json` | `f85d2e16403beec2770207e0347a3a38df72291598125604047031875a7204ae` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |
| `run_gates_f01a.py` | `da588181e89dfaee1eb178314745ea08cca7ce51f370331cf365bd06a82c915d` |
| `run_gates_fast.sh` | `01220a1dac46516fc139c40ac7a1d6b455f2949219fd426946271dd1a8d65d72` |
| `run_gates_g2.sh` | `8d3de1a6671b60d736ba669380d5d4fd2fe954c8945f58f0799c5fd77e9ace74` |

### 5.2 行为合同

**5.2.1 辅助模块 `plc_git_marker_guard`**（只读，不写 Git、不建锁：每条 Git 命令带 `GIT_OPTIONAL_LOCKS=0`、`GIT_NO_LAZY_FETCH=1`、超时 10 秒）：`removed_index_markers(工作区根)` 返回“HEAD 里存在而暂存区里不存在”的标记路径（精确路径比较；archive 路径与移动没有任何例外，Git 的改名检测与相同的 blob 都不构成放行）；读取前后重复核对，HEAD 或暂存区在核验期间漂移就失败；已核实的非 Git 工作区返回空；HEAD 里的标记不是普通文件、路径含 `..` 或反斜杠、清单被截断或含无效编码，都按读取故障处理。`marker_in_head(工作区根, 工程路径)` 返回该工程根的标记是否在 HEAD 里；非 Git 与未出生仓库为否；工程在所选仓库之外、HEAD 损坏、提交对象缺失、权限失败都抛出 `GitMarkerGuardError`。**未出生仓库**只在 `HEAD` 是指向不存在分支的合法符号引用时才成立，已存在分支的提交对象损坏不算未出生。

**5.2.2 提交钩子**（`enforce_plc_docs`）：在“暂存快照为空”和“没有 PLC 相关文件”两个提前返回**之前**调用 `removed_index_markers`；非空就打印被删除的标记路径与固定提示“移动或退役请走 F01-b 的授权”并返回 1；辅助模块抛出的任何错误沿用既有的外层失败关闭处理（返回 1）。其余既有行为不变。

**5.2.3 阶段门**（`StageGateEngine._evaluate_plc_doc_code_consistency`，由静态方法改为实例方法以取得工作区根）：先用 `marker_in_head` 取得历史身份；核验抛出任何异常就返回一个 BLOCKER 级、未通过的拦截项（消息含异常）；工程目录里没有 `.plc.json` 时，HEAD 里有就返回未通过的拦截项（提示恢复标记并走 F01-b），HEAD 里没有就保持“不适用”；有标记时走原有的文档一致性检查。

**5.2.4 兼容**：不新增存储、登记、schema；不改 `checker.py`、wrapper、Workbench；`removed_index_markers` 对已核实的非 Git 工作区返回空元组，因此既有的在非 Git 目录里调用 `enforce_pre_commit` 的测试保持通过。

### 5.3 必测场景（G3）

新增的 28 个测试按下表分组（测试名 `test_f01a_<编号>_…`）。

| 场景 | 要证明的行为 | 所在文件与参数数 |
|---|---|---|
| H16 | 暂存快照为空（ACM 为空）时，删除 HEAD 里的标记仍被拒绝 | 钩子 1 |
| H17 | 删除标记不能掩盖一个错误的接口文档类型 | 钩子 1 |
| H18 | 工作区里未暂存的标记恢复不能盖过暂存区里的删除 | 钩子 1 |
| H19 | 仅标记移动、整个工程移动、移入 archive 三种情形都要求走 F01-b | 钩子 3 |
| H20 | 已在 HEAD 里的 archive 标记不能被删除 | 钩子 1 |
| H21 | 未出生仓库照旧检查它的新 PLC 工程（含一致与不一致两种） | 钩子 2 |
| H22 | 损坏的 HEAD（格式错误、提交对象缺失）是读取故障，不当作未出生仓库 | 钩子 2 |
| H23 | Git 权限故障不当作“标记集合为空” | 钩子 1 |
| H24 | 已核实的非 Git 工作区保持旧合同（不拒绝、无已删除标记） | 钩子 1 |
| S07 | HEAD 有标记而工作区没有时保留原 PLC 拦截项 | 阶段门 2 |
| S08 | 工作区删除标记即使暂存区仍保留也拦截 | 阶段门 1 |
| S09 | 未出生仓库里的工程用其当前 PLC 文档合同 | 阶段门 2 |
| S10 | 损坏的 Git HEAD 保持一个失败的 PLC 项 | 阶段门 2 |
| S11 | 选定仓库之外的工程不能借用其 HEAD | 阶段门 1 |
| E04 | 真实 pre-commit 进程拒绝纯标记删除，真实修复后接受 | CLI 2 |
| E05 | 真实 pre-commit 拒绝仅标记移动、整工程移动、移入 archive | CLI 3 |
| E06 | 真实 pre-commit 在 Git HEAD 损坏时失败关闭 | CLI 2 |

### 5.4 明确不做

见 §1.8。另：不改既有测试的任何字节（只在文件末尾追加）；不用 `--no-verify`；不改 `.git/hooks` 下的真实钩子；不合并、不推送、不部署、不切换 release。

## 6. 门禁矩阵

门禁在隔离候选的最终字节上运行（快速部分 `run_gates_fast.sh`，九组回归 `run_gates_g2.sh`，判卷 `run_gates_f01a.py`，均只读，判卷在任一门禁不过时以非零退出；变异检查会逐个改动并逐字节还原候选文件，所以排在其他快速门禁之后、九组回归之前单独跑，脚本已按此顺序编排）。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 夹具健康与冒烟 | `tests/test_fixture_health.py`、`tests/test_smoke.py`、`tests/test_import.py` | 候选与安装前的基线完全相同：26 passed、唯一失败是既存的 `test_no_conditional_assertion_skips`、0 skipped |
| G2 九组回归 | 十个输出逐组对照卡 054 的真实门禁输出 | 失败集合与基线逐个相同；通过数恰为基线加本卡新增（`infrastructure` +13、`core` +8、`cli` +7，其余 +0）；跳过数与基线相同；退出码与基线相同；无报错节点 |
| G3 必测场景 | 三个测试文件的收集结果 | 恰为基线测试加 `new_nodes.json` 的 28 个新节点，基线测试一个不少 |
| G4 静态质量 | 对 6 个 Python 文件运行 `ruff check --no-cache` 与 `mypy --strict --no-incremental`；`git diff --check`；字节扫描 | 全部退出码 0；字节扫描零发现；新增行中没有 `type: ignore`、`noqa`、`follow-imports=skip`、`pylint: disable` |
| G5 范围与最终字节 | 变更集与指纹 | 变更集恰为 §4 的 6 个路径；6 个文件的 SHA-256 等于 §5.1；无缓存与临时文件残留；门禁前后字节记录相同 |
| G6 既有内容不变 | `g6_check.py` 对照由基线提交导出的目录树 | `templates` 字节不变；`auto_pm` 与基线的差异恰为 3 个产品文件；`tests` 与基线的差异恰为 3 个测试文件 |
| G7 不触碰生产 | 新增测试行扫描、真实钩子记录与残留进程检查 | 新增的测试行不含对真实控制根（`My_Workspace`）的引用；真实 `.git/hooks` 下的文件在全部门禁前后字节相同；门禁前后 pytest 相关的 Python 进程数相同 |
| G8 负向对照 | `mutation_run.py`（计划 `mutation_plan.json` 的 12 个变异，判据 `m2-tools/mutation_classify.py`） | 计划的 SHA-256 等于指纹清单；点名的测试组先在未变异字节上全绿；每个变异让点名的测试出现真实断言失败（pytest 退出码 1、失败节点带被点名的测试标记、没有报错节点、消息类别为断言）；每个文件逐字节还原；6 个文件前后与冻结字节相同 |
| G9 三个测试文件整体 | `tests/infrastructure/test_plc_doc_hook.py`、`tests/core/test_stage_gate_plc_docs.py`、`tests/cli/test_git_hook_plc_docs.py` | **52 passed、0 failed、0 skipped**，退出码为 0 |

**提交与收尾**（由提交脚本执行）：创建当前字节 Checkpoint 后走正常 Hook 提交（不得 `--no-verify`）；提交内 blob 与 Checkpoint 逐一相同；`main.py ledger reconcile SW-2026-008` 为 0/0/0。

## 7. 实施授权签字门

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-F01A V1.0` |
| 实施批准 | `PENDING`（须用户在对话中明确批准；批准后以委托方式由 Claude 执行，回执另行生成；**当前没有任何预授权**） |
| 最终验收 | `PENDING`（验收由用户做出；CHG 收口须经用户确认后才可由 Claude 代跑） |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| 隔离基线 | `1956dd9a003bca2dab379d7e368aaf78c60d7170` |
| Owned Paths | §4 的 6 个路径 |
| 执行模型 | `Claude Sonnet 5.5` |
| 明确禁止 | 第 7 条路径、改 §4 之外的任何产品文件与既有测试、改 checker、新增存储或登记、改台账、WBS、既有 CHG、PM_SESSION、Obsidian 规范、Hook 脚本与 release、新增 schema 或迁移、直接改真实库、历史改写、合并、推送、部署 |

### 7.2 授权成立与失效

1. 卡片字节、隔离基线、owned paths、执行模型或禁止事项任一漂移，审批立即失效。
2. 外部 Approval Receipt 绑定本卡完整字节 SHA-256、基线、6 个路径、6 个最终文件 SHA-256、允许与禁止的动作、执行模型、审批人与时间；卡片自身不含自身 SHA-256。
3. 实施批准与最终验收分离；执行 Agent 不得自签验收。
4. 卡 055 未经用户验收收口前，本卡不得开工（已满足，由启动脚本核验）。

## 8. 治理执行顺序

1. 只读预检并输出事实表（§3），含安装前的 G1 基线。
2. 用户批准本卡后，创建并批准 SW-2026-008 的独立 CHG（领域 SCPT，性质 DEF）与精确 Decision（§4 六路径；`DEC-<起卡当天日期>-F01AGUAR`）。
3. 创建 Work（`--card-file` 指向本卡；`WORK-SW008-M2-F01A-001`）、在全新隔离候选（自 `1956dd9a` 起，分支 `codex/m2-f01a-marker-guard`，工作树 `.auto-pm/worktrees/m2-f01a`）启动 Run（`RUN-SW008-M2-F01A-001`，`--lease-seconds` 不超过 3600）；启动续租循环；全部门禁约 3 小时（其中 `core` 组约 1.5～1.7 小时）。
4. 装入参考字节、运行 §6 门禁；判卷结果写入 `.auto-pm/reports/m2-f01a/gates/`。
5. 创建当前字节 Checkpoint（`git_head` 为基线，记录 6 个文件的 SHA-256 与判卷文件 SHA-256），**先于提交**；随后走正常 Hook 提交；提交后核验提交内 blob 与 Checkpoint 相同，否则停止。
6. Run/Work 终态、`main.py ledger reconcile SW-2026-008` 为 0/0/0；CHG 收口须经用户确认后由 Claude 代跑，或由用户自己运行。
7. 向用户报告后停止；SHA 与 ID 写入交接文档。

## 9. 有界纠正与硬停止条件

本卡单提交，一个主 Run；**执行期间不得修订本卡**；需要修订本卡即属于硬停止。任何门禁失败都不得靠重跑、改字节或放宽判据达成通过：保留现场与输出、停止并报告，由用户裁决。**真实进程测试的间歇失败不得靠重跑掩盖**。

以下任一情况立即保留现场、停止并报告：

- 基线 HEAD、runtime 身份、Decision 字节或 owned paths 不一致，或需要第 7 条路径；
- 需要改 §4 之外的产品文件、既有测试、WBS、既有 CHG 才能让测试通过；
- 只能通过 Mock 业务结果、硬编码预期输出、跳过测试、放宽断言或抑制才能通过；
- 任一门禁不通过，或 G8 的任一变异存活、任一还原字节不一致；G7 发现测试结束后仍有遗留进程；
- 真实 `.git/hooks` 的文件前后字节不同；
- Checkpoint 不是当前字节，或质量门未完整返回；
- Run 租约已过期：停止并报告，不得自行走恢复链；
- 发现本卡与事实矛盾（先停止，由用户裁决是否出新版本，不得自行改卡）。

## 10. 交付物

1. 基线 SHA 与预检事实表（含安装前的 G1 基线）；
2. CHG / Decision / Work / Run / Checkpoint ID 与 Approval Receipt；
3. 精确 diff 与 6 个路径的最终 SHA-256；
4. G1～G9 矩阵、原始命令、Exit Code、输出位置；
5. G3 场景（H16～H24、S07～S11、E04～E06）与测试名称的对照表；
6. 不可变提交 SHA 与 Checkpoint 绑定核对；
7. 明确声明：删除 PLC 工程标记不再能让提交钩子与阶段门同时失效；不放行任何改名与移动；Git 读取故障失败关闭；非 Git 与未出生仓库保持旧合同。**已知限制必须如实报告**：已进入 HEAD 的删除认不出；HEAD 身份不是持久登记；Git 命令的并发时序窗口没有完全消除；三个测试文件新增的行没有被逐行审读；GPT 起草、我修了四处并读了全部产品差异；F01-b 未实施。

## 11. 与其他任务的关系与需要用户知悉的决策点

- F01-a 是 V05、V08 与部署的前置（WBS V3.0.22）；F01-b（合法移动与退役）独立成卡，不阻塞本卡。
- **需要你在批准本卡时知悉的点**（均为我的默认裁决，如要改请在批准前说，我改卡后重新报批）：
  ① **改名与移动一律拒绝**：合法移动以后要走 F01-b 的授权，现在做不到；
  ② **这是失败关闭**：一旦 Git 读取出错（含 HEAD 损坏）提交会被拒绝，宁可误拒也不放行；
  ③ **残余风险**：已进入 HEAD 的删除、`--no-verify`、其他克隆仍然认不出；
  ④ **GPT 的字节我改了四处**（含一个真实的产品回归），并已读完三个产品文件的全部差异，测试文件新增行未逐行审读；
  ⑤ **门禁全跑**（九组回归含约 1.5～1.7 小时的核心组），约 3 小时；演练里只跑了不含 core、qml、rest 的子集；
  ⑥ **每次提交多出约一两秒**（读取 Git HEAD 的文件清单）。
