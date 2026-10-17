# V02｜PLC 新需求静态闭环实施卡

> 卡片编号：`CARD-SW008-M2-V02`
> 对应 WBS：`V02`（WBS V3.0.21 §4.8 任务表；V02 依赖由 `M2-GOV-WBS5` 提交 `57e14c19` 改为 V01、V01B、V01C、V01D、C09）
> 需求依据：REQ07（IT/OT 都可用）、AC10（Python 与 PLC 静态新任务完成）
> 版本：`V1.0`（2026-10-04，一次定稿；执行期间不得修订，见 §9）
> 状态：`PLANNED / NOT_AUTHORIZED`（定稿，待授权；授权方式见 §7）
> 依赖：V01、V01B、V01C、V01D 已验收闭环（M2 代码线尖端 `fb94afa9`，CHG-SCPT-2026-376 completed）；C09 已 `PASS / ACCEPTED`（WBS §4.8）
> 隔离基线：`fb94afa9fd2b37e396e34b8ba1209c2436eda428`
> 治理任务真源：WBS 提交 `57e14c194fdcc9c69fa601223240d68589472747`（V3.0.21，CHG-DOCU-2026-026 completed）；WBS SHA-256 `e5be410f35b2b883c036474173e66c09d5b3beb6bf19a3c4dae4582474202bf5`
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或能力不低于它的模型；实际执行者 `Claude Sonnet 5.5`
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

> V1.0 定稿说明：本卡写于一次**可行性演练**之后（§1.7）。演练在项目副本与真实仓库的临时工作树里实现了全部改动，用真实 Git、真实审批链、真实 V01/V01B 门、真实验收与收口，并在钉死的已治愈基准上真跑了 8 个场景。参考实现、变异脚本、G1/G2/G9 脚本、安装脚本、判卷脚本与演练输出归档于 `.auto-pm/reports/m2-v02/`（`proto/<相对路径>` 共 2 个文件、`mutation_check.py`、`run_g1_set.sh`、`run_g2.sh`、`run_g9_e2e.sh`、`run_gates_fast.sh`、`run_gates_g2.sh`、`run_gates_v02.py`、`g6_check.py`、`install_candidate.py`、`reference_manifest.json`、`rehearsal/`），仅供参考，不是产品代码；执行者可按参考实现填空，但必须满足 §5 的合同与 §6 的门禁。执行者不得现场修订本卡、扩大路径或放宽门禁；遇到本卡未覆盖的情况按 §9 停止并报告。
> 路径偏差说明：WBS 的 V02 行只写了“拟新增 e2e 测试文件”。演练在真实基准上发现验收门的一处真实缺陷（§1.4），修复只需改一行产品代码，所以本卡的确切路径为 §4 的 2 个：1 个既有产品文件的一行替换、1 个新测试文件。WBS 对本卡实际路径的回写留到 M2 总审计。

## 1. 背景与已核实事实（2026-10-04，基线 `fb94afa9`，均为命令或源码核验）

1. WBS V02 原文：新目标到真实 SCL 变化、静态门禁、验收落账；上机编译与下发单列为“未执行”，不虚报工业运行成功；产出为拟新增的 `tests/e2e/test_pmf_plc.py` 与“批准的 PLC 演练工程”。V02 之后 V08（从通过的 PLC 基准提取模板）直接依赖它，V05（GUI 双领域联合验收）也依赖它。
2. **现状**：V01 的 `tests/core/test_plc_checkpoint_chain.py` 已用合成工程（`DJ-TEST-001`）证明 PLC Run 的验收链，`tests/core/test_pm_run_e2e.py` 证明 Python 链直到收口与台账；两者都不是真实 PLC 工程。**缺口**：没有任何测试在真实的 PLC 基准上把“新需求 → 真实 SCL 与文档变化 → V01 静态门（含 V01B 文档与代码一致性）→ 验收 → 收口 → 台账”整条链走一遍。
3. **演练工程的选择**：WBS 要求先确认候选的所属与用途。`DJ-2026-011`（驾驶舱 A6 PLC 续作验证套件）是一个空骨架（OB1 全是 TODO、没有变量、文档只有桩），触发不了 V01B 的文档核对；V01C 钉死并已治愈的基准 `DJ-2026-005`（提交 `1e1ef760c6f9c8814dbe47d681da760c887d28ee`，其上该目录的 Git 目录树 SHA `ae8ff3a787936702a6d5df5ce3aadaecc3cb4eed`）有真实的功能块、结构体与变量定义文档，也是 V08 提取模板所用的基准。**选 DJ-2026-005 的钉死副本**：测试用 `git archive` 从钉死提交只读导出到临时仓库，导出后核对目录树 SHA，真实工作区与真实 PLC 工程目录一概不动。
4. **演练发现 ①（真实缺陷）**：`PmFacadeService._require_current_acceptance_checkpoint`（基线第 966 行）用元组直接比较“Checkpoint 记录的改动路径”（Git 按字母序给出）与“Run 声明的路径”（保持写批准卡时的顺序）。声明范围不是字母序时，哪怕 Run 已通过全部质量门，`accept` 也永远报“Checkpoint 与最新 Run 声明差异不一致”，该任务无法验收。演练里把范围写成（结构体、功能块、文档）三个文件的非字母序即复现；既有测试的范围恰好都是字母序，所以一直没暴露。**修复**：两侧各自排序后再比较，只忽略顺序，仍要求文件集合完全相等。
5. **演练发现 ②（环境前提，非缺陷）**：V01 的受管工作树快照把 Git 的诊断输出当作拒绝理由；临时仓库若没有与真实仓库相同的换行设置（真实仓库的 `.git/config` 里 `core.autocrlf=false`、`core.safecrlf=false`，并有根目录 `.gitattributes`：`* text=auto eol=lf`），脚本写出 LF 文件时 Git 会打印 CRLF 警告，验证就会被拒绝。测试夹具复刻这三项设置；“警告不应拒绝”登记为技术债候选（§11）。
6. **演练发现 ③（行为确认）**：声明了三个文件而代理只改了其中两个，质量验证不通过（p06）；SCL 缺文档或文档类型写错，V01B 一致性核对使验证不通过（p02、p03）；加入 `GOTO` 违反白名单，V01 的 SCL 规范检查使验证不通过（p04）。这些都保留现场、不开验收门。
7. **执行代理如实说明**：`pm execute` 真实启动的是 `codex exec`，本机命令行里没有 `codex`；既有测试通过 `LocalCodexExecutor` 的 `command_prefix` 注入脚本替身。本卡沿用这一做法：替身是一个真实子进程，真实完成握手、真实写出 SCL 与文档；批准链、隔离工作树、质量门、验收、收口与台账全是产品代码。**这不是真 AI 在写代码**；真实代理的演练在部署后另做（§11）。
8. **可行性演练结果**（归档于 `.auto-pm/reports/m2-v02/rehearsal/`）：① 参考实现过 `ruff` 与 `mypy --strict`（2 个 Python 路径，零 `type: ignore`/`noqa`）；② 新测试文件 8 个测试全部通过（在最终字节的临时工作树里独占机器约 4 分钟，并发占用时 8 分 44 秒）；③ 不带修复时 p05 失败（`accept` 报“声明差异不一致”），带修复通过；④ 2 处变异（§6 G8）全部被 p05 抓住、源文件字节全部还原；⑤ 既有的 10 个相关测试文件在基线上 **213 passed、0 skipped**，在带修复的最终字节上同样 **213 passed**（各约 38 分钟）；⑥ 整条快门禁（静态检查、收集、G1、G9、G8、G6 与判卷）在全新的临时工作树上按脚本完整演练通过，判卷干跑九项全 PASS。
9. **基线数字**：① G1 集合（§6）在基线 `fb94afa9` 的隔离工作树里、改动前实测 **213 passed、0 skipped**；② G2 各组沿用 V01D 终态（真实隔离工作树，原始输出 `.auto-pm/reports/m2-v01d/gates/g2_candidate/`）：contracts 191 passed 1 skipped；infrastructure 47 passed；cli 263 passed 1 skipped；change 230 passed；core 954 passed、3 failed（即 E-G1-1）、1 skipped；qml 283 passed（排除一个测试）+ 该测试单独 1 passed；application 174 passed；plc 144 passed。新测试在 `tests/e2e`，不在这九组内，所以各组增量为 0，由 G9 单独门禁。
10. 已登记的基线例外沿用：E-G1-1（`tests/core/test_implementation_card_service.py` 的 3 个既存失败）、E-G1-2、E-G1-3、E-G3-1。
11. **明确不在本卡**：真实代理（`codex exec`）的执行演练；换 Agent 续跑（V03）；GUI 联合验收（V05）；PLC 上机编译与下发；DJ-2026-011、DJ-2026-009 的任何使用；模板提取（V08）；Hook、release、部署；任何 PLC 工程目录与基准钉值；`tests/e2e/test_pmf_python.py`；其他产品文件的任何改动。

## 2. 单一目标（用户故事与完成定义）

作为要靠 autopm 做 PLC 改动的人，我希望一个新需求从批准到验收落账的整条链在真实的 PLC 工程上被证明可用，并且不会被产品自身的缺陷卡死：

1. 新增 `tests/e2e/test_pmf_plc.py`：在钉死且已治愈的基准 DJ-2026-005 的临时副本上，通过真实的审批链与隔离工作树，让脚本替身代理完成一个真实需求（公共报警块新增蜂鸣器输出：结构体加字段、功能块加一行赋值、变量定义文档加一行），经 V01 静态门（含 V01B 一致性核对）验证，开验收门，验收，收口，台账零差异；
2. 同一测试文件证明不该通过的情形都不通过且保留现场：只改 SCL 不改文档、文档类型写错、出现 `GOTO`、声明的文件没改完；验证后再改动会关闭验收门；重放不产生第二个进程或证据；
3. 修复验收门的排序缺陷：声明范围不按字母序也能验收，同时仍要求改动文件集合与声明完全相等；
4. 上机编译与下发明确“未执行”，不虚报工业运行成功（§10）。

## 3. 实施前预检（只读，先于任何写入）

1. 核验本卡字节 SHA-256 已被外部 Approval Receipt 绑定；核验 `隔离基线` 是 V01D 提交且可解析（分支 `codex/m2-v01d-plc-commit-gate` 仍在 `fb94afa9`）、WBS 提交与 SHA-256 一致。
2. 运行 `main.py implementation-card precheck --card-file` 对本卡，退出码必须为 0。
3. 核验 §4 中 1 个“存在”路径在基线上存在、1 个“计划新增”路径在基线上不存在。
4. 在隔离候选中，对 §6 G1 集合复现基线结果 **213 passed、0 skipped**（修改前），`ruff` 与 `mypy --strict` 对 §4 已存在的 1 个 Python 路径通过；不一致则停止。
5. 核验隔离候选 HEAD 等于基线，configured/effective runtime 与加载路径一致且无 fallback；核验钉死提交 `1e1ef760` 可解析且其上 `0100_PLC自动化/DJ-2026-005` 的目录树 SHA 为 `ae8ff3a787936702a6d5df5ce3aadaecc3cb4eed`。
6. 阅读 `.auto-pm/reports/m2-v02/proto/` 下的参考实现与 `mutation_check.py`，确认其做法与本卡 §5 一致；核对 `reference_manifest.json` 中各文件与工具的 SHA-256。
7. **续租（硬性）**：G1 与 G2 的 core 各约 30～80 分钟，开始任何超过 30 分钟的门禁前先续租；每个检查周期（不超过 25 分钟）续一次租（`m2_renew_loop.sh`），单次续租不超过 3600 秒，finalize 前租约须剩余 300 秒以上。租约过期时停止并报告，不得自行走恢复链。
8. **判卷与门禁工具先验证再起长批次**：判卷脚本与变异脚本必须先在真实输出上跑通一次，再启动长批次；工具字节一旦被证据绑定，任何修正都会使整个窗口重开。
9. **长批次不得重叠**：G1、G9、G8、G2 的各目录按顺序单独运行，不与 `tests/qml` 组重叠。后台起长批次用 `nohup`（本机没有 `setsid`），并确认输出文件真的开始增长。

## 4. 精确 Owned Paths（2）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `auto_pm/application/core/pm_facade_service.py` | 存在 | 验收检查点比较处的一行替换：两侧各自排序后再比较（删除 1 行、新增 1 行，其余字节不变） |
| 2 | `tests/e2e/test_pmf_plc.py` | 计划新增 | 真实基准上的 PLC 新需求端到端测试（8 个场景） |

出现第 3 条产品脏路径即停止，不得现场扩大 Decision。治理证据对象在控制根落账，不计入上述路径。

## 5. 合同（全部定稿，执行者不得改写含义）

### 5.1 `auto_pm/application/core/pm_facade_service.py`（一行替换）

在 `_require_current_acceptance_checkpoint` 里，把

`        if checkpoint.dirty_paths != run.declared_dirty_paths:`

替换为

`        if tuple(sorted(checkpoint.dirty_paths)) != tuple(sorted(run.declared_dirty_paths)):`

文件其余字节、错误文案（“Checkpoint 与最新 Run 声明差异不一致”）、既有的 `git_head` 比较与“唯一自动质量证据”检查一字不变。

### 5.2 `tests/e2e/test_pmf_plc.py`（新增）

1. **夹具**：模块级夹具 `benchmark_tar` 在测试仓库内用 `git rev-parse --show-toplevel` 找到仓库，核对钉死提交上 `0100_PLC自动化/DJ-2026-005` 的目录树 SHA 等于钉值（钉死提交不可用或不等就**失败并指出原因，不得跳过**），再用 `git archive --format=tar` 取出该目录；`build_workspace` 在临时目录建仓库，设置 `core.autocrlf=false`、`core.safecrlf=false` 与 `.gitattributes`（`* text=auto eol=lf`），解包基准，补最小的规范与工作区注册文件、`.gitignore`，提交基线；
2. **需求**：公共报警块新增蜂鸣器输出——`ST_CommonAlarm.scl` 在 `o_bNewAlarmFlag` 行后新增 `o_bBuzzer : BOOL := FALSE;` 及行尾注释；`FB_2001_CommonAlarm_AllStation.scl` 在功能块末尾前新增 `io_stGlobal.o_bBuzzer := io_stGlobal.o_bAnyAlarmActive;`；`PLC变量定义文档_VAR.md` 的 `ST_CommonAlarm` 小节在 `o_bAnyAlarmActive` 行后新增对应行；
3. **执行代理替身**：一个真实子进程（`LocalCodexExecutor(command_prefix=(解释器, 脚本))`），打印握手事件、把给定内容写入隔离工作树里的给定文件、退出 0；`批准链`用 `PlanningExecutionGrant`（适配器 `codex`、`declared_dirty_paths` 等于范围）、`create_planning_scope_card`、变更单 `submitted → under_review → approved` 与 `approve_planning_scope_card`，与 V01 的 `test_plc_checkpoint_chain.py` 同口径；
4. 测试不得通过 Mock 业务结果、硬编码预期字段或跳过来变绿；只替换“执行代理”这一外部进程。

### 5.3 必测场景（G3）

测试文件中的每个测试函数都须对应下表一个场景；场景编号写在测试名里（`test_p01_…`）。

| 场景 | 要证明的行为 |
|---|---|
| p01 | 新需求（范围为字母序）经执行、验证（检查点证据 `checkpoint-evidence.v3`）、验收，收口得 `COMPLETED`（Run `SUCCEEDED`、Work `CLOSED`、Mission `CLOSED`），变更单记录含检查点与三个范围路径，台账零差异；隔离工作树里三个文件含新内容，`plc docs` 核对零拦住零标记，控制根里这三个文件字节不变 |
| p02 | 只改 SCL 不改文档 → 验证不通过，保留现场（Run 仍 `VERIFYING`、Mission 仍 `ACTIVE`、无 Checkpoint），`accept` 被拒 |
| p03 | 文档里新增行的类型写错 → 验证不通过，无 Checkpoint |
| p04 | 功能块里加入 `GOTO` → 验证不通过，`accept` 被拒 |
| p05 | 范围不按字母序声明 → 验证通过且验收成功（修复前此场景失败） |
| p06 | 声明了三个文件而代理只改两个 → 验证不通过，无 Checkpoint |
| p07 | 重放同一已验证的 Run 不产生第二个进程、事件或 Checkpoint，结果相同 |
| p08 | 验证之后在工作树里再改动 SCL → 验收门关闭，`accept` 被拒 |

### 5.4 明确不做

不改任何其他产品文件、既有测试、驾驶舱/Bridge/QML、Store、合同模型、Hook、release；不新增 schema、事件类型或迁移；不改任何文档与 Obsidian 规范；不改真实 PLC 工程目录与基准钉值；不做 PLC 上机编译或下发；不合并、不推送、不部署、不切换 release。

## 6. 门禁矩阵

所有命令均在隔离候选的项目根执行，使用工作区 `.venv` 解释器与 `-B`，先 `-o addopts= --no-cov -p no:cacheprovider`。

**G1 既有相关测试不变**（脚本 `.auto-pm/reports/m2-v02/run_g1_set.sh`；修改前先对基线跑同一集合并记录数字；修改后全部通过，0 失败，不新增跳过）：集合为 `tests/core/test_pm_facade_service.py`、`tests/core/test_pm_run_e2e.py`、`tests/core/test_plc_checkpoint_chain.py`、`tests/core/test_pm_pending_scope_card.py`、`tests/core/test_pm_approval_guard.py`、`tests/core/test_pm_cockpit_service.py`、`tests/core/test_cockpit_api.py`、`tests/cli/test_pm_pending_cards.py`、`tests/qml/test_pm_cockpit_approval_bridge.py`、`tests/qml/test_pm_cockpit_start_e2e.py`。基线数字：**213 passed、0 skipped**；候选须恰为 213 passed、0 failed、0 skipped。

**G2 分目录回归**（固定方法；基线数字见 §1.9；候选相对基线：失败集合相同——core 仅 E-G1-1 的既存失败、无新增失败、无新增跳过；各目录通过数不少于基线）。共九组：`tests/qml`（排除去抖测试）、去抖测试单独一组、`tests/contracts`、`tests/infrastructure`、`tests/cli`、`tests/change`、`tests/core`、`tests/application`、`tests/plc`，命令与顺序见 `.auto-pm/reports/m2-v02/run_g2.sh` 的前九组（脚本最后的“其余目录”组仅作参考，不设门）。各组都必须在**最终字节**上全量重跑；core 约 75 分钟，**必须先按 §3-7 续租**。`tests/qml` 组出现 Qt access violation 不得按 E-G1-2 豁免：先在全新进程单独重跑出问题的文件一次并保存两次原始输出；仍崩溃则按 §9 停止。

**G3 必测场景**：§5.3 的 p01～p08 各一个独立测试，并在判卷报告中列出“场景 → 测试名”对照；测试文件中的每个测试函数都须对应一个场景，收集到的测试数恰为 8。

**G4 静态质量**：对 §4 的 2 个 Python 路径运行 `ruff check --no-cache`、`mypy --strict --no-incremental`，以及 `git diff --check`；不得使用 `--follow-imports=skip`，不得新增文件级抑制或为通过门禁新增 `type: ignore`/`noqa`（新增文件全文零出现；既有文件的 diff 新增行零出现）；在最终字节上运行；新增（未跟踪）文件另行用 Python 按字节扫描回车、行尾空白与制表符（仓库约定为 LF）。

**G5 范围与洁净**：`git diff --name-only` 加未跟踪文件的路径集合精确等于 §4 的 2 个路径；无 `.coverage`、缓存、`tmp_*` 残留（DEV-TMP-001）；任何 `.qml` 文件无改动。

**G6 既有内容不变**（参考脚本 `.auto-pm/reports/m2-v02/g6_check.py CANDIDATE_ROOT BASELINE_ROOT`）：① `pm_facade_service.py` 相对基线**恰好删除上面的旧行、新增上面的新行**，别无差异，且新增行零抑制；② `auto_pm/domain`、`auto_pm/contracts`、`auto_pm/ui`、`auto_pm/infrastructure` 四个目录树字节不变；③ 候选与基线之间除 §4 的 2 个路径外，`auto_pm`、`templates`、`tests` 三个目录里没有任何文件差异；④ 既有测试不改一个断言。

**G7 不触碰生产**：新增测试只使用临时目录，对真实仓库只读（`rev-parse`、`archive`）；新增行不含对真实控制根（`My_Workspace`）与 `continuity.db` 的引用；**真实 `.git/hooks` 下的文件在全部门禁运行前后字节完全相同**（判卷脚本逐文件比对）；不改 Hook、release、`.auto-pm` 下任何运行态对象（Run 自己的治理对象除外）；不改任何真实 PLC 工程目录。

**G8 变异检验**（执行者在代码完成后、最终门禁之前运行，结果绑定进判卷）：运行 `.auto-pm/reports/m2-v02/mutation_check.py`（2 处变异：验收重新按原始顺序比较；只排序检查点一侧）；每处变异后 p05 必须变红，源文件随后原样还原并校验字节；任一变异存活或还原后字节不一致即停止。输出归档于 `.auto-pm/reports/m2-v02/gates/mutation_check_output.json`。

**G9 真实基准端到端**：运行 `.auto-pm/reports/m2-v02/run_g9_e2e.sh`（即对 `tests/e2e/test_pmf_plc.py` 全量运行），通过标准：**8 passed、0 failed、0 skipped**，退出码 0。该文件会真实导出钉死基准、真实起子进程、真实走完审批链与收口（约 4～9 分钟）。

## 7. 实施授权签字门

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-V02 V1.0` |
| 实施批准 | `PENDING`（须用户在对话中明确批准；批准后以委托方式由 Claude 执行，回执另行生成） |
| 最终验收 | `PENDING`（验收由用户做出；CHG 收口须经用户在对话弹窗确认后才可由 Claude 代跑） |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| 隔离基线 | `fb94afa9fd2b37e396e34b8ba1209c2436eda428` |
| Owned Paths | §4 的 2 个路径 |
| 执行模型 | `Claude Sonnet 5.5` |
| 明确禁止 | 第 3 条路径、对 `pm_facade_service.py` 做上述一行替换以外的任何改动、改既有测试断言、改 V01～V01D 已验收的其他文件、改真实 PLC 工程目录与基准钉值、改 Hook 与 release、改 Obsidian 规范与任何文档、新增 schema 或迁移、直接改真实库、历史改写、合并、推送、部署 |

### 7.2 授权成立与失效

1. 卡片字节、隔离基线、WBS 真源、owned paths、执行模型或禁止事项任一漂移，审批立即失效。
2. 外部 Approval Receipt 绑定本卡完整字节 SHA-256、基线、WBS 提交、2 个路径、允许/禁止动作、执行模型、审批人与时间；卡片自身不含自身 SHA-256。
3. 实施批准与最终验收分离；执行 Agent 不得自签验收。

## 8. 治理执行顺序

1. 只读预检并输出事实表（§3），含 G1 修改前的基线数字。
2. 用户批准本卡后，创建并批准 SW-2026-008 的独立 CHG（领域 SCPT）与精确 Decision（§4 两路径，计划新增路径不检查基线存在；Decision 建议 `DEC-20261004-V02PLCFX`，日期以起卡当天为准，后缀须恰 8 位）。
3. 创建 Work（`--card-file` 指向本卡，Work 与 Decision 的项目一致，均为 SW-2026-008；建议 `WORK-SW008-M2-V02-001`）、在全新隔离候选（自 V01D 提交 `fb94afa9` 起，分支 `codex/m2-v02-plc-e2e`，工作树 `.auto-pm/worktrees/m2-v02`）启动 Run（`--lease-seconds` 不超过 3600；建议 `RUN-SW008-M2-V02-001`），并按 §3-7 管理续租。
4. 在候选中按 §5 实现、运行 G8 变异检验并完成 §6 门禁；判卷结果写入 `.auto-pm/reports/m2-v02/gates/` 下机器可读判卷文件。
5. 创建当前字节 Checkpoint（`git_head` 为基线，逐文件记录 SHA-256 与判卷文件 SHA-256），**先于提交**；随后走正常 Hook 提交（不得 `--no-verify`）；提交后核验提交内 blob 与 Checkpoint 逐一相同，否则停止。
6. Run/Work 终态、台账 `main.py ledger reconcile SW-2026-008` 为 0/0/0；CHG 收口须经用户弹窗确认后由 Claude 代跑，或由用户自己运行。
7. 向用户报告后停止；SHA 与 ID 写入交接文档。WBS 对本任务结果的回写为独立的后续修订，不在本卡范围。

## 9. 有界纠正与硬停止条件

本卡单提交，一个主 Run；仅当失败稳定复现、完全落在 §4 路径内、无需合同或路径扩展时，允许一个纠正 Run（必须新建 Run 并重建 Checkpoint）。**执行期间不得修订本卡**；需要修订本卡即属于硬停止。

以下任一情况立即保留现场、停止并报告：

- 基线 HEAD、runtime 身份、Decision 字节、owned paths 或基准目录树 SHA 不一致，或需要第 3 条路径；
- 钉死提交 `1e1ef760` 在仓库里不可解析；
- 需要改 `pm_facade_service.py` 里上述一行以外的任何内容、其他产品文件或任何既有测试断言才能实现；
- 只能通过 Mock 业务结果、硬编码预期输出、跳过测试、放宽断言、文件级抑制或 `noqa`/`type: ignore` 才能通过；
- 既有测试出现需要改断言的失败；
- `tests/core`、`tests/cli`、`tests/change`、`tests/plc` 内出现无法归因于已登记基线例外的失败，或 `tests/qml` 出现可复现的 Qt 崩溃（按 G2 流程仍无法通过）；
- 任一变异检验存活，或还原后字节不一致；G7 的真实钩子文件前后字节不同；G9 任一通过标准不成立；
- Run 租约已过期（说明续租失效）：停止并报告，不得自行走恢复链；
- Checkpoint 不是当前字节，或质量门未完整返回；
- 发现本卡与代码事实矛盾（先停止，由用户裁决是否出新版本，不得自行改卡）。

## 10. 交付物

1. 基线 SHA 与预检事实表（含 G1 修改前的基线数字与基准目录树 SHA）；
2. CHG / Decision / Work / Run / Checkpoint ID 与 Approval Receipt；
3. 精确 diff 与 2 个路径的最终 SHA-256；
4. G1～G9 矩阵、原始命令、Exit Code、输出位置，以及 G2 对基线的逐目录对照；
5. G3 场景（p01～p08）与测试名称的对照表；
6. 不可变提交 SHA 与 Checkpoint 绑定核对；
7. 明确声明：PLC 新需求在钉死的已治愈基准上经真实审批链、V01 静态门（含 V01B 一致性核对）、验收、收口与台账走通；声明范围不按字母序的任务现在可以验收（修复了一处真实缺陷）。**已知限制必须如实报告**：执行代理是脚本替身，不是真实的 AI（`codex exec` 在本机命令行不可用）；**PLC 上机编译、下发与任何工业运行均未执行，不虚报运行成功**；测试依赖钉死提交 `1e1ef760` 一直留在仓库历史里（不可用时测试失败而不是跳过）；测试要求临时仓库使用与真实仓库一致的换行设置（Git 的 CRLF 警告会使验证被拒，登记为技术债）；该文件约 4～9 分钟，较重；`DJ-2026-011`、`DJ-2026-009` 与 SysLib 未使用。

## 11. 与其他任务的关系与需要用户知悉的决策点

- **V03**（真实更换 Agent 续跑）、**V05**（GUI 双领域联合验收）、**V08**（从通过的 PLC 基准提取模板）依赖本卡；V08 使用同一个钉死基准。
- **需要用户在批准本卡时知悉的点**（均为我的默认裁决，如要改请在批准前说，我改卡后重新报批）：
  ① **把验收门的一行缺陷修复并入本卡**，而不是另开修复卡：修复只有一行、由本卡的 p05 与变异检验证明；另开卡要多走一整轮批准与 G2（约 2 小时）；
  ② **演练工程用钉死基准 DJ-2026-005 的临时副本**，不用空骨架 DJ-2026-011（它触发不了文档核对）；
  ③ **执行代理用脚本替身**，所以证明的是“产品这条链”，不是“某个 AI 写得好不好”；真实 `codex exec` 或我以人工适配器执行的演练建议在部署后做（可与 V03 合并）；
  ④ **测试依赖钉死提交留在历史里**，不可用就失败（不跳过）；M3 合并时必须保留这条历史；
  ⑤ **新测试较重（约 4～9 分钟）**，不在 G2 九组里，由 G9 单独门禁。
- **技术债候选**：Git 的 CRLF 警告被受管快照当作拒绝理由（应区分建议性警告与真实诊断）；验收门之外是否还有按元组比较路径顺序的位置（本次只发现一处）；`plc check` 退出码恒为 0；`DJ-2026-009`、SysLib 的文档治愈；拒绝时钩子自动补全对大差异项目偏多。
- **D01**：写入“声明范围顺序不再影响验收”与 PLC 新需求流程的操作说明；本卡不改文档。
- WBS 对本卡实际 2 个路径的回写与 M2 总审计不在本卡范围。
