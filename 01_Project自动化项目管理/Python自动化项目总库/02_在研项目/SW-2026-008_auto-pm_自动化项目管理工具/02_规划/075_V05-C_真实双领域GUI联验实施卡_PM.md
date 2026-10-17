# V05-C｜真实双领域 GUI 联验实施卡

> 卡片编号：`CARD-SW008-M2-V05C`
> 对应 WBS：`V05-C`（V3.0.23 §4.8）
> 版本：`V1.1`（2026-10-09，第二次执行；字节合同、变异计划与门禁标准与 V1.0 完全相同，只换身份与启动条件；执行期间不得修订）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-08 预授权，原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt`；条件见 §7）
> 档次：**测试档**（规则文档 §3：只新增测试；相关完整组 `rest`，含 tests/e2e；不改任何产品文件）
> 依赖：F02（卡 074，CHG-SCPT-2026-395 completed，由启动脚本核验）
> 隔离基线：`98c2110d8893d330a5d8f2bfe26981e8b90c2434`（F02，分支 `codex/m2-f02-query-versions-r2`）
> 治理任务真源：WBS 提交 `a538f942f1995f1ec3e50ad45c624bdc123c6bc3`（V3.0.23）
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 执行模型：`claude-sonnet-5-5`（驱动者）；**联验里的执行代理是真实的 `codex exec`，模型显式指定 `gpt-6.1-sol`**
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

## 1. 背景与已核实事实（2026-10-08，基线 `98c2110d`）

1. **V05-C 要证明什么**：前面各卡（V05-A、V05-B、B2、B3、F01-1、F02）用的是无界面窗口、手动驱动的后台任务和受控替身。V05-C 把整条路真实地串起来：离屏的真实 `boss_main.qml` 窗口（生产桥、服务、**真实线程池**、生产关闭流程）；Python 与 PLC 两个项目各自从窗口输入目标开始；PM 一侧提交范围卡；用户在窗口里点“批准范围并开始”（第一次业务决策）；**真实模型进程**在隔离副本里改文件；质量验证；点“确认验收”（第二次业务决策）；后台收尾；台账干净。
2. **真实模型与授权**：用户 2026-10-08 授权真实调用模型，合计不超过 20 次、累计不超过 90 分钟，**模型用 Sol 不用 Astra**（原话 `PREAUTH_M2_20261008.txt`）。本机默认配置是 `gpt-6-astra`，所以每次调用都显式写 `-m gpt-6.1-sol`，不依赖默认。`gpt-6.1-sol` 已用 `codex debug models` 核实在模型目录里（GPT-6.1-Sol）。codex 可执行文件在 `C:\Program Files\WindowsApps\OpenAI.Codex_26.1002.7124.0_x64__2p2nqsd0c76g0\app\resources\codex.exe`（v0.162.0-alpha.2，不在 PATH 上，路径带应用版本；启动脚本核对路径存在、版本行、模型目录三项，任一不符不开工）。
3. **预检与演练调用（已做，均计入总账）**：2026-10-08 起我做了 16 次真实调用，先是 4 次预检（label `preflight*`：第 1 次让 Sol 只回答“OK”，6.3 秒返回、事件流含 `thread.started`；随后 3 次在临时空仓库里让 Sol 改一个文件，用来确认沙箱，见第 8 条），再是联验演练（label `python`、`plc`，其中前 4 次因第 8 条的权限问题没有改动文件，修正后全部通过）。每次调用的时间、状态与完整命令（提示词已脱敏）都在总账里。
4. **调用预算的强制方式**：总账是一个全局文件（`.auto-pm/reports/m2-v05c/budget_ledger.json`），测试里的执行器在**每次启动进程之前**检查并登记；第 21 次调用或累计满 90 分钟都会在启动前被拒绝（`CallBudgetError`）。有专门的测试证明这一点。演练与正式门禁共用同一个总账。
5. **默认与真实两种运行方式（同一份代码，没有任何跳过）**：默认运行用脚本替身（真实子进程，说 codex 的握手、写真实文件），免费，因此这个文件会成为每次全量回归的一部分；设置 `V05C_MODE=real` 才调用真实 codex。正式门禁的 G9 用真实模式；G2 的 rest 组与 G8 变异用默认模式。
6. **我在全新基线副本上的演练**（2026-10-09，非受治理执行，受治理执行里完整重跑，不采纳这些输出；输出在 `.auto-pm/reports/m2-v05c/gates_rehearsal/`）：
   ① `ruff check` 与 `mypy --strict` 对该文件零问题、`git diff --check` 通过；
   ② G1：26 passed、1 failed（既存，与基线相同：26 passed、1 failed）；
   ③ G9（真实模式，演练一次）：三个测试 3 passed、0 failed、0 skipped；真实调用耗时 python 22.0 秒, plc 34.1 秒；截图与事件列表已保存；
   ④ G8：7 个变异在未变异字节上先为绿，变异后各被点名测试的真实断言失败杀死，字节逐一还原，完整输出已保存；
   ⑤ G6：除这个新增文件外 `templates`、`auto_pm`、`tests` 树与基线逐字节相同；
   ⑥ G2 的 rest 组回归不在这次演练里重跑；完整 rest 组由正式门禁重跑，基线取卡 074 受治理执行的真实输出。
7. **本卡的限度**：窗口是离屏的（用户 2026-10-08 选定；可见窗口的截图留待用户在场时补做，不在本卡）；PLC 只做静态检查，不上机编译、不下发、不碰博图和硬件；真实模型的行为有随机性——正式 G9 里模型没做对就是门禁失败，保留现场、停下报告，不靠重跑变绿；执行器的单次超时是 300 秒（编排器不暴露，本卡不改产品）。
8. **沙箱与权限（用户已授权的覆盖）**：本机的 Codex 配置会让 elevated 沙箱初始化失败（模型能答不能改文件；将在台账同步卡里登记为新增债务）。用户 2026-10-08 晚授权：**只对模型子进程**把沙箱模式降为 unelevated（命令里加 `-c 'windows.sandbox="unelevated"'`；仍是 `--sandbox workspace-write`；不改配置文件、不改系统设置，授权原话见 `PREAUTH_M2_20261008.txt`）。判卷核对总账里每次调用的命令确实带这一项。演练中还发现：Python 3.12.4 起，以 0o700 创建的目录（pytest 的 `tmp_path`）在 Windows 上带“仅属主”访问控制，沙箱账户读不到，模型会说 Access is denied、一个文件也不改，调用却返回成功；所以真实模式下测试把工作区放在继承临时目录权限的普通目录里，用完删除；替身模式不受影响。真实模式下每次调用的模型事件流与错误输出保存在证据目录的 `_model/`，不作判据，只供复核。
9. **演练中发现的产品缺陷（本卡不改产品；将在台账同步卡里登记）**：窗口每 5 秒读一次状态快照，快照读取在 Windows 下用“禁止写入”的共享锁复制数据库，此时另一线程的写入会报 `attempt to write a readonly database`，点“批准范围并开始”会失败。旧测试用同步假线程池从未遇到。本卡的窗口测试在批准阶段暂时挡住快照读取来避开它（测试里的 `snapshots_held_off`），修复属于另立的核心档卡，登记在台账同步卡里。另一个测试基础设施发现：真实线程池下主线程用 `QTest.qWait` 等待会持有 GIL，把批准到验收的链路拖慢约 8 倍，测试改用 `time.sleep` 轮询。
10. **第一次执行（V1.0，Run/Work `…V05C-001`）的结果与为什么有第二次**：2026-10-09 04:22 开始，05:35 门禁跑完，判卷九项（G1～G9）全部通过，整套用时 1 小时 13 分。但 Run 的租约在 05:22 已经过期——原因是我启动续租循环时给的配置文件路径是相对路径，续租脚本在第一次续租（04:42）就找不到配置而退出，我没有在启动后核对第一次续租，也没有在门禁期间看续租日志。过期的租约不能续，也就不能建 Checkpoint 和提交，所以这一轮拿不到提交。**这是操作失误，不是代码或门禁问题。** 第一次执行的 Run 与 Work 原样保留（Run 为带过期租约的 RUNNING，Work 为 IN_PROGRESS，其处置并入失败记录处置方案另行报批），证据归档在 `.auto-pm/reports/m2-v05c/attempt1/`，**不用于本次判卷**；变更单 CHG-SCPT-2026-396 沿用（同一变更的第二次执行）。第二次执行从头完整重跑。续租循环的脚本已修（先转绝对路径，并在第一次睡眠前立即续租一次，失败即退出报错），执行时必须确认日志里有 `first renewal ok`，门禁期间每次检查都先看续租日志。调用总账共用：第一次执行的 G9 用了 2 次，所以启动条件由“已用不超过 15 次”放宽为“不超过 17 次”，本次 G9 再用 2 次，合计 18 次，仍在 20 次上限内。按止损规则，这是同一问题的最后一次机会。

## 2. 单一目标与完成定义

新增一个测试文件，让“从窗口输入目标到最终验收”这条路在 Python 与 PLC 两个项目上都被真实地跑通并留下证据。一个新增文件，其余产品、模板、台账、WBS 均零改动。

3 个新增测试节点：

| 测试 | 证明 |
|---|---|
| `test_a_python_goal_typed_into_the_window_reaches_the_final_acceptance_and_a_clean_ledger` | Python 项目：在窗口输入框填目标与验收、点“保存规划草稿”；PM 提交范围卡；点“批准范围并开始”，执行代理改 `calc.py` 与测试文件，质量验证通过；点“确认验收”，后台收尾；任务、工作、运行与变更单都到终态，台账干净；控制根的缺陷代码未被改动（改动只在隔离副本）；调用的模型名恰为 `gpt-6.1-sol` 且带沙箱参数 |
| `test_a_plc_goal_typed_into_the_window_reaches_the_final_acceptance_with_a_consistent_document` | PLC 项目（固定基准 DJ-2026-005）：同样的窗口路径；执行代理改两个 SCL 文件和变量定义文档；V01 静态门禁与文档一致性检查通过；控制根字节未变 |
| `test_the_call_budget_refuses_the_twenty_first_call_and_a_used_up_clock` | 总账在第 21 次调用与时长用完时拒绝，不会启动进程 |

另外每个领域测试都保存五张窗口截图（目标已输入、草稿已保存、待批准、运行后、已收尾）和完整事件列表，供验收时查看。

7 个变异（对象是产品代码、窗口 QML 与本文件自身，每个由点名测试的真实断言失败杀死）：
   - M01-the-default-model-is-used：the request names the approved model, never a default
   - M02-approval-never-starts-the-worker：one click on the approve button really queues the approve-and-start worker
   - M03-acceptance-never-closes：the final acceptance click queues the closure
   - M04-the-window-is-not-wired-to-approval：the window's approve signal reaches the bridge
   - M05-the-draft-form-sends-no-project：the draft form passes the selected project to the bridge
   - M06-the-call-budget-is-off-by-one：the 21st call is refused
   - M07-the-budget-is-not-counted：every start is counted in the ledger before anything is launched

## 3. 实施前预检

1. 核对卡字节与已向用户报告的 SHA 一致、基线、WBS、1 个 owned path 及参考字节。没有这些，不创建 CHG/Decision/Work/Run。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空；预检仅读，不代表获批。启动脚本另有 `--check-only` 模式，只做上述检查、不写任何东西。
3. 核对前置 CHG-SCPT-2026-395 completed；核对历史失败记录仍在原状态且本卡不触碰。
4. 核对 codex 可执行文件存在、版本行为 `codex-cli 0.162.0-alpha.2`、模型 `gpt-6.1-sol` 在目录里、总账剩余额度足够（已用不超过 17 次、4000 秒）。
5. 新候选 HEAD 等于基线且 clean；新增路径在基线不存在；工具与参考字节均匹配冻结指纹。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `tests/e2e/test_pmf_gui.py` | 计划新增 | 新增：两个领域的窗口端到端测试与调用总账测试 |

出现第 2 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-v05c/`、本卡文件、演练工作树、截图与总账）不是额外产品 owned paths，不进本卡产品提交。

## 5. 字节合同

### 5.1 参考字节指纹

新增文件的最终 SHA-256（UTF-8、LF、无 BOM）；冻结文件保存在 `.auto-pm/reports/m2-v05c/proto/`。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `tests/e2e/test_pmf_gui.py` | 计划新增 | `cf424a43fe698d7467039c8cc1d74863977ed9d71c6ba9a9774982ba1c3c2cb6` |

### 5.2 冻结工具

工具与脚本由卡 071（测试档、rest 组）与卡 074（启动与收口）的已演练工具派生（`.auto-pm/reports/m2-v05c/`）；共用判卷脚本仍是控制根下的外部副本。变异运行器保存每次运行的完整输出并绑定进判卷文件。G2 的基线取卡 074 受治理执行的 rest 组真实输出。

| 工具 | SHA-256 |
|---|---|
| `commit_msg.template.txt` | `feacf3db24458b52a405d62556d3dc821b48416e76d6e8630e54b26889231a59` |
| `g6_check.py` | `29db41cc115eda6695109b81633e4cd2f42d1bfb3ecbbee0e4a3a74ba589b133` |
| `install_candidate.py` | `a8c822dd7ce6fa53b511be85acbcdb1e48825159072b9da0de855d706892bd99` |
| `m2-tools/mutation_classify.py` | `0fff21f888cb1a50094f050ef8bc3b42ea25653ba508581e3c85fa1b28d79019` |
| `m2-tools/verdict_check.py` | `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188` |
| `mutation_plan.json` | `f7d383d929798f109739d6a2af2a1bf601a1751a4278720d23aadd483947a6e2` |
| `mutation_run.py` | `e9e1cadcaed6af51c802eafb18680b58e03675ed618cdb7bf9a10eebe880d8bb` |
| `new_nodes.json` | `438881a22808c4274bdffc2d54b1c393943f52848e7c034a9d913478f19a5514` |
| `run_g2.sh` | `10b906ffd3424a7f94faf4100f85ba1d32319e650a3e7d61aa9c08656872508a` |
| `run_gates_fast.sh` | `c9efce0b0cc97e60513628dcb5fafce67271c0be2685c3ab4414ca578b58a0fa` |
| `run_gates_g2.sh` | `8e322804c314c9f2b80a023bf3e431c7db1ded8670339bb1d8f760c82ce6c052` |
| `run_gates_v05c.py` | `0924b7c9616962def1cb45f841f8764310f6e992477be32700f2c856414bacdf` |

## 6. 门禁矩阵

测试档。顺序：基线测量 → 安装参考字节 → 快速门禁（G4、G3、G1、**G9 真实联验**、G8、G6）→ rest 组回归（G2）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 夹具健康、冒烟、导入测试 | 与基线完全相同（26 passed，1 个既存失败） |
| G2 | rest 组回归（含 tests/e2e，替身模式） | 失败集合与基线相同、通过数恰增 3、无新增 skip 与 ERROR |
| G3 | 新测试节点 | 收集到的恰为冻结的 3 个节点 |
| G4 | 静态检查 | 该文件 `ruff`、`mypy --strict` 零问题，`git diff --check`，字节扫描，新增行无抑制注释 |
| G5 | 范围 | 变更集恰为 1 个 owned path，字节等于 §5.1，无残留 |
| G6 | 既有内容不变 | `templates`、`auto_pm`、`tests` 树除这个新增文件外与基线逐字节相同 |
| G7 | 隔离 | 新增行不引用真实控制根；真实 `.git/hooks` 前后字节相同；门禁不遗留 python 进程 |
| G8 | 严格变异 | 7 个变异各被点名测试的真实断言失败杀死，字节还原；每次运行的完整输出保存并绑定 |
| G9 | **真实模型联验** | 三个测试 3 passed、0 failed、0 skipped；总账新增恰 2 条（python、plc），状态均 SUCCEEDED、模型均为 `gpt-6.1-sol`、命令含 `-m gpt-6.1-sol`、`workspace-write` 与用户授权的 `windows.sandbox="unelevated"`；总账累计不超过 20 次与 5400 秒；codex 版本行与模型目录核对通过；两个项目各有五张截图与事件列表且非空 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA（含总账前后快照、版本与模型目录文件）。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-08 的预授权（原话 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末段）：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径；任一不满足则不开工 |
| 真实模型调用 | 用户 2026-10-08 授权：合计不超过 20 次、累计不超过 90 分钟，只用 Sol（显式 `gpt-6.1-sol`）；已用 16 次（预检、演练与第一次执行）；第二次执行的 G9 再用 2 次，合计不超过 20 次；任一上限先到即停，不得放宽 |
| 窗口 | 用户选定离屏窗口；可见窗口截图另行告知后再做 |
| 最终验收 | 已委托：G1–G9 全部通过且提交与 Checkpoint 一致时由 claude-sonnet-5-5 代为验收并收口 CHG；用户可复核并推翻 |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

卡、基线、范围或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 向用户在聊天报告最终卡 SHA 与改动摘要。
2. 创建 SW-2026-008 SCPT/DEF 变更单、匹配 Decision（`DEC-<当天>-V05CGUI2`）、Work `WORK-SW008-M2-V05C-002`、Run `RUN-SW008-M2-V05C-002`（租约不超过 3600 秒，续租循环；真实联验可能超过一小时，续租循环覆盖。**续租循环必须用绝对路径启动，并在启动后核对第一次续租成功**）；实际创建前验证未被占用，不复用幂等键或旧 token。
3. 从代码基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-v05c-r2`，分支 `codex/m2-v05c-gui-e2e-r2`。
4. 安装参考字节并完整重跑门禁（`v05c_gates_all.sh`）；先创建当前字节 Checkpoint，再正常 Hook 提交 1 个 owned 文件，绝不 no-verify；核对提交父、范围及 blob 与 Checkpoint 完全一致。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；条件满足后代为验收并收口 CHG。

## 9. 硬停止

基线、工具/卡/Decision 指纹、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败；变异未被点名断言杀死；真实调用的任何一次未完成、模型名不对、超出预算、命令里缺沙箱参数；模型改了允许范围之外的文件（执行器的包含性检查会拒绝）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要改这个文件以外的任何内容、或为让测试变绿而放宽断言：均停止，保留现场，不靠重跑、改字节或放宽判据变绿。按止损规则：同一问题最多修 2 轮，每卡总时长上限 6 小时，连续 2 张卡失败整体停下。全量测试对机器负载敏感（台账 TD-SW008-095）：正式门禁期间我不并发其他重任务。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结参考字节与工具；演练原始门禁（非治理）；正式独立门禁与证据（截图、事件列表、总账前后快照、版本与模型目录）；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；代验收记录；GPT 对提交的独立审计。

## 11. 限制与后续

窗口为离屏；可见窗口截图待用户在场补做。PLC 不上机、不下发。联验只覆盖这两个范围内的小目标，不代表任意需求都能由模型做对。真实模型的运行时间与结果有随机性；执行器单次超时 300 秒。不处理 TD-SW008 台账里的其余债务；台账是否因本卡更新由后续台账卡依据证据另行处理。无合并、推送、部署或 release 切换授权。
