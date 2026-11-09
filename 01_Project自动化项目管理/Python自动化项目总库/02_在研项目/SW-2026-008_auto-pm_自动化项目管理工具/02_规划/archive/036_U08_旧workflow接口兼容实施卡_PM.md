# U08｜旧 workflow 接口兼容实施卡

> 卡片编号：`CARD-SW008-M2-U08`
> 对应 WBS：`U08`（WBS V3.0.18 §4.7）：“旧 workflow 接口兼容”，依赖 U07
> 版本：`V1.0`（2026-10-01，一次定稿；执行期间不得修订，见 §9）
> 状态：`PLANNED / NOT_AUTHORIZED`（定稿，待授权；授权方式见 §7）
> 依赖：U07A/U07B/U07C 与 U07D 已验收收口（CHG-SCPT-2026-364～368 completed）
> 隔离基线：`460e24f692f42578e8e76e8004b3fae2d0221f93`
> 治理任务真源：WBS 提交 `572932a7d7fe23cf799c6f8800d77263aec3c3ee`；WBS SHA-256 `33EE746A6D9495B7B39D09921605D3745A405AE26D1EBC51450C60213ACD5FCD`
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或能力不低于它的模型；实际执行者 `Claude Sonnet 5.5`
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

> V1.0 定稿说明：本卡写于一次**可行性演练**之后（§1.4）。演练在真实的 `auto-pm` 命令入口上，把“`workflow` 命令组保留原有 4 个命令、并把 7 个旧动作名直接绑定到 `pm` 的同名命令对象、其余一律明确拒绝”真实跑通（identity 为真、`--help` 同源、未知动作退出码 2）。演练脚本归档于 `.auto-pm/reports/m2-u08/diag_u08.py`，仅供参考，不是产品代码。执行者只做填空与验证，不得现场修订本卡、扩大路径或放宽门禁；遇到本卡未覆盖的情况按 §9 停止并报告。

## 1. 背景与已核实事实（2026-10-01，基线 `460e24f6`，均为命令或源码核验）

1. WBS U08 原文：拟改 `CLI/workflow.py`，拟新增 `tests/cli/test_workflow_compat.py`；验收“现有命令保留；新 workflow 别名只委托 pm；不能恢复旧写入状态机；未知旧动作明确拒绝”。
2. 现状：顶层 `auto-pm workflow` 是约束工作流引擎的命令组（`list / run / history / status RUN_ID`，由 `WorkflowEngine` 驱动），在 `auto_pm/ui/cli/__main__.py` 以 `cli.add_command(workflow_group)` 注册；另有 `auto-pm pm workflow`，只打印兼容提示“pm-workflow 已退役隔离；请使用 pm plan / approve / execute / resume / accept”（`PmFacadeService.compatibility_notice`，已有测试，保持不变）。
3. 历史 CLI 参考 `02_规划/009_CLI命令参考.md` §10 仍写着 `workflow plan / execute / status --workflow-id`，而当前代码里 `workflow` 没有 `plan`/`execute`，`status` 的参数是位置参数 `RUN_ID`。也就是说，旧使用习惯（敲 `workflow plan/execute…`）今天得到的是 Click 的通用“No such command”，没有任何指引；而旧写入状态机（`ai_handoff_service`、`pm_saga_service`、以 `pm-workflow` 为默认 actor 的 handoff 命令）已被治理明确“只复用领域动作与失败样例，禁止重新启用”。
4. **可行性演练结果**：把 `workflow` 组换成一个 `click.Group` 子类，保留 4 个原命令对象，并把 `pm_group.commands` 里 `plan / approve / confirm-start / execute / accept / resume / context` 这 7 个**同一个 Command 对象**以同名注册进来；重写 `resolve_command`，对第一个非选项参数既不是已注册命令时抛 `click.UsageError`（退出码 2）。结果：`compat.commands[n] is pm_group.commands[n]` 对 7 个名字全为真；`workflow --help` 同时列出 4 个原命令与 7 个委托命令；`workflow resume --help` 与 `pm resume --help` 正文一致；`workflow handoff / close / workflow / start` 均得到退出码 2 与固定的退役说明；`workflow list` 仍退出码 0。因为委托命令就是 `pm` 的命令对象本身，它们天然继承 `pm` 的全部守卫（控制根校验、哈希校验、批准证据校验、令牌只走环境变量），**不存在第二条写入路径**。
5. `pm_group` 里共有 8 个命令：`plan / approve / confirm-start / execute / accept / workflow / resume / context`；`workflow` 被排除（避免 `workflow workflow` 递归与二义），其余 7 个全部委托。
6. 现有测试：`tests/cli/test_workflow.py`（4 个用例，覆盖 `list/run/history/status`，用 `workflow_group` 直接调用）、`tests/cli/test_pm_facade.py`（含 `pm workflow` 展示型别名与 linked worktree 拒绝用例）。本卡不改它们。G1 基线（本卡 §6 G1 同一集合去掉计划新增的 `test_workflow_compat.py`、`460e24f6` 干净检出、改动前实测）：12 passed、0 failed、0 skipped；原始输出 `.auto-pm/reports/m2-u08/gates/G1_baseline.txt`（退出码 0）。
7. 基线质量（`460e24f6`，U07D 验收时的同一提交、同一命令）：contracts 191 passed 1 skipped；infrastructure 32 passed；cli 216 passed 1 skipped；qml 241 passed（排除一个测试）+ 该测试单独 1 passed；core 810 passed 1 skipped 3 failed（失败即 E-G1-1，位于 `tests/core/test_implementation_card_service.py`，非本卡路径）；`tests/change` 230 passed。原始输出：`.auto-pm/reports/m2-u07d/gates/`。本卡 §4 已存在的 Python 路径在基线上 `ruff` 与 `mypy --strict` 均通过（预检再核）。
8. 已登记的基线例外沿用：E-G1-1、E-G1-2、E-G1-3、E-G3-1。
9. **明确不在本卡**：`02_规划/009_CLI命令参考.md` 等文档的修订（属于 D01 的“日常指引与薄适配引用”，且本卡 owned paths 不含文档）；`pm workflow` 展示型别名；`handoff` 命令组及其 `pm-workflow` 默认 actor（旧状态机的存量代码不在本卡处置，另有治理处理）；任何 QML、SDK、Facade、收尾、Hook、release。

## 2. 单一目标（用户故事与完成定义）

作为还在用旧习惯敲 `auto-pm workflow …` 的人或脚本：

1. 原有的 `workflow list / run / history / status` 一字不变地继续工作；
2. 旧动作 `plan / approve / confirm-start / execute / accept / resume / context` 现在可以写在 `workflow` 下，**效果与 `pm` 同名命令完全一致**（同一个命令对象，同样的守卫）；
3. 任何其它旧动作（含 `workflow` 自身、`handoff`、`close`、`start` 等）被**明确拒绝**，给出固定的中文说明与可用清单，退出码为 2，不触发任何引擎或状态机、不写任何文件；
4. 不引入、不恢复、不间接依赖任何旧写入状态机（handoff.v1 / saga / `pm-workflow` actor）。

## 3. 实施前预检（只读，先于任何写入）

1. 核验本卡字节 SHA-256 已被外部 Approval Receipt 绑定；核验 `隔离基线` 是 U07D 提交且可解析、WBS 提交与 SHA-256 一致。
2. 运行 `main.py implementation-card precheck --card-file` 对本卡，退出码必须为 0。
3. 核验 §4 中 1 个“存在”路径在基线上存在、1 个“计划新增”路径在基线上不存在。
4. 在隔离候选中，对 §6 G1 的目标测试文件（不含计划新增文件）复现基线结果并记录数字（修改前），ruff 与 mypy 对 §4 已存在的 Python 路径通过；不一致则停止。
5. 核验隔离候选 HEAD 等于基线，configured/effective runtime 与加载路径一致且无 fallback。
6. 阅读 `.auto-pm/reports/m2-u08/diag_u08.py`，确认其做法与本卡 §5 一致。
7. **续租（硬性）**：开始任何超过 30 分钟的门禁（G2 的 core 约 60 分钟）之前，先后台启动 `bash .auto-pm/reports/m2_renew_loop.sh <close.env>`；门禁结束后创建 `STOP_RENEW` 文件停止它。续租失效（租约过期）时停止并报告，不得自行走恢复链。

## 4. 精确 Owned Paths（2）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `auto_pm/ui/cli/workflow.py` | 存在 | `workflow` 命令组改为带委托与明确拒绝的 Group 子类；4 个原命令的函数体不动 |
| 2 | `tests/cli/test_workflow_compat.py` | 计划新增 | 兼容层测试 |

出现第 3 条产品脏路径即停止，不得现场扩大 Decision。治理证据对象在控制根落账，不计入上述路径。

## 5. 合同（全部定稿，执行者不得改写含义）

### 5.1 `workflow.py`

1. `workflow_group` 仍是模块级名字、仍叫 `workflow`、帮助文本仍为“工作流编排与执行管理”，但其类型改为本模块内的 `click.Group` 子类 `_WorkflowGroup`。`__main__.py` 的注册语句不改。
2. 4 个原命令 `list / run / history / status` 的函数、选项、帮助、行为与既有测试一字不变；仍用 `@workflow_group.command(name=…)` 注册。
3. **委托**：模块加载时，对固定元组 `_DELEGATED_TO_PM = ("plan", "approve", "confirm-start", "execute", "accept", "resume", "context")` 中的每个名字，执行 `workflow_group.add_command(pm_group.commands[name], name)`，其中 `pm_group` 来自 `auto_pm.cli.pm`（与 `__main__.py` 同一导入路径，保证是同一模块对象）。名字不存在则让 `KeyError` 在导入期直接失败（失败即停，不静默跳过）。**不得**为这些名字另写任何包装函数、重新声明选项、复制其逻辑，也**不得**包含 `workflow` 自身。
4. **明确拒绝**：重写 `resolve_command(ctx, args)`：当 `args` 的第一个元素存在、不以 `-` 开头、且 `self.get_command(ctx, 该名字)` 为 `None` 时，抛 `click.UsageError(_UNKNOWN_ACTION.format(name=repr(该名字)[:40]), ctx=ctx)`（退出码 2），不得调用 `super()`、不得走引擎。其余情况调用 `super().resolve_command(ctx, args)`。固定文案（逐字）：`旧 workflow 动作 {name} 已退役，不会恢复旧写入状态机；可用：list/run/history/status（工作流引擎）与 plan/approve/confirm-start/execute/accept/resume/context（等同 pm 同名命令）。`
5. 本模块不得新增对 `ai_handoff_service`、`pm_saga_service`、`auto_pm.cli.handoff`、`continuity` 写服务的导入，不得出现字符串 `pm-workflow`（既有注释/文案若含该字样以“不得新增”为准，基线 `workflow.py` 不含它）。
6. 不改 `pm.py`、`__main__.py`、`PmFacadeService`、任何 Facade/服务层代码；不新增选项、环境变量、持久化或日志对象。

### 5.2 必测场景（G3）

1. **委托同一性**：对 7 个名字，`workflow_group.commands[n] is pm_group.commands[n]`；`workflow_group.commands` 的键集合恰为 4 个原命令名 ∪ 这 7 个名字（共 11 个，不多不少，**不含 `workflow`**）；
2. **原命令保留**：`tests/cli/test_workflow.py` 的既有用例全部原样通过；另在新文件里断言 4 个原命令仍为原函数对象且 `--help` 仍含“工作流编排与执行管理”；
3. **委托效果一致（真实 CLI 入口）**：用 `tests/cli/test_pm_facade.py` 已有的 `_setup`，在两个相同的临时工作区里分别用 `pm` 与 `workflow` 走同一序列——`plan --mission-id MISSION-PM-CLI-001`（退出码 0、输出 JSON 相等）、`confirm-start --mission-id MISSION-PM-CLI-001`（退出码 0、输出 JSON 相等）、`accept --mission-id MISSION-PM-CLI-001`（尚未到验收门：退出码相等且为 1、输出相等）；
4. **守卫同样适用**：在 linked worktree 里用 `workflow plan --mission-id …` 得到与 `pm plan` 相同的拒绝（退出码 1、输出含 `linked worktree`），且**未创建** `.auto-pm`；`workflow execute` 在令牌环境变量缺失/请求不一致时同样拒绝，输出不含令牌值（沿用 `pm execute` 的既有守卫，用 `--request-id`/`--card-json` 不一致的最小夹具即可）；
5. **未知旧动作明确拒绝**：`handoff`、`close`、`start`、`workflow`、`rollback`、以及一个任意乱码动作，各一例：退出码 2、输出含固定文案的开头“旧 workflow 动作”与可用清单、**不含** Python 堆栈；调用前后工作区文件树快照完全相同（无 `.auto-pm`、无任何新文件）；引擎未被构造（对 `WorkflowEngine` 的构造次数为 0，用既有真实类的计数包装即可，不 Mock 业务结果）；
6. **名字过长/含特殊字符**：超过 40 字符的未知动作名，输出中的名字被截断到约定长度，不影响退出码；
7. **`--help` 同源**：`workflow --help` 列出全部 11 个命令；`workflow resume --help` 与 `pm resume --help` 的正文（去掉首行用法行）逐字一致；
8. **不恢复旧状态机**：对 `auto_pm/ui/cli/workflow.py` 做 AST 导入扫描：不含 `ai_handoff_service`、`pm_saga_service`、`handoff` 相关导入；源码不含 `pm-workflow`；
9. **`pm workflow` 与注册不变**：`pm workflow` 仍是展示型别名（输出含“pm-workflow 已退役隔离”）；通过 `auto-pm` 入口调用 `workflow list` 仍成功；`cli.commands["workflow"] is workflow_group`；
10. **既有行为不变**：`tests/cli/test_workflow.py`、`tests/cli/test_pm_facade.py` 全部原样通过。

测试不得通过 Mock 业务结果、硬编码预期字段或跳过来变绿；可对“外部副作用点”做计数包装，但不得替换 `pm` 命令对象或其服务。

### 5.3 明确不做

不改任何文档（含 `009_CLI命令参考.md`）；不改 `pm.py`、`__main__.py`；不新增 `workflow` 下的任何写入动作；不改 handoff 命令组；不新增 schema、事件类型或迁移；不合并、不推送、不部署、不切换 release。

## 6. 门禁矩阵

所有命令均在隔离候选的项目根执行，使用工作区 `.venv` 解释器与 `-B`，先 `-o addopts= --no-cov -p no:cacheprovider`。

**G1 定向测试**（修改前先对基线跑同一集合（不含计划新增文件）并记录数字；修改后全部通过，0 失败，不新增跳过）：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider `
  tests/cli/test_workflow.py tests/cli/test_pm_facade.py tests/cli/test_workflow_compat.py
```

基线数字：12 passed（§1.6）；执行者须在隔离候选复现同一数字；候选须不少于 12 + 本卡新增测试数，且 0 failed、0 skipped。

**G2 分目录回归**（固定方法，同 U05～U07D；基线数字见 §1.7，候选相对基线：失败集合相同——core 仅 E-G1-1 的 3 个既存失败、通过数不少于基线、无新增失败、无新增跳过；`tests/change` 同样对比）：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/contracts
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/infrastructure
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/cli
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/change
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/core
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/qml --deselect tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events
```

各组都必须在**最终字节**上全量重跑；core 约 60 分钟，**必须先按 §3-7 启动续租循环**。`tests/qml` 组出现 Qt access violation 不得按 E-G1-2 豁免：先在全新进程单独重跑出问题的文件一次并保存两次原始输出；仍崩溃则按 §9 停止。

**G3 必测场景**：§5.2 的 10 项各至少一个独立测试，并在判卷报告中列出“场景 → 测试名”对照。

**G4 静态质量**：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m ruff check --no-cache auto_pm/ui/cli/workflow.py tests/cli/test_workflow_compat.py
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m mypy --strict --no-incremental auto_pm/ui/cli/workflow.py tests/cli/test_workflow_compat.py
git diff --check
```

不得使用 `--follow-imports=skip`，不得新增文件级抑制或为通过门禁新增 `type: ignore`/`noqa`；在最终字节上运行。

**G5 范围与洁净**：`git diff --name-only` 加未跟踪文件的路径集合精确等于 §4 的 2 个路径；无 `.coverage`、缓存、`tmp_*` 残留（DEV-TMP-001）。

**G6 既有内容不变**：`auto_pm/ui/cli/workflow.py` 中 4 个原命令的函数体、装饰器参数与帮助文本的 diff 无任何被删除/修改的行（允许删除/调整的只有 import 行与 `workflow_group` 的定义行本身及紧邻其下的 `pass`）；`tests/cli/test_workflow.py`、`tests/cli/test_pm_facade.py` 字节不变（不在 owned paths 内）。

**G7 不触碰生产**：测试只使用临时目录与临时库，不读写真实控制面与真实 `00_Infrastructure`；不改 Hook、release、`.auto-pm` 下任何运行态对象。

## 7. 实施授权签字门

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-U08 V1.0` |
| 实施批准 | `PENDING`（须用户在对话中明确批准；批准后以委托方式由 Claude 执行，回执另行生成） |
| 最终验收 | `PENDING`（验收由用户做出；CHG 收口须经用户在对话弹窗确认后才可由 Claude 代跑） |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| 隔离基线 | `460e24f692f42578e8e76e8004b3fae2d0221f93` |
| Owned Paths | §4 的 2 个路径 |
| 执行模型 | `Claude Sonnet 5.5` |
| 明确禁止 | 第 3 条路径、任何文档改动、改动 `pm.py`/`__main__.py`/Facade/服务层、新增 `workflow` 下的写入动作、导入或恢复旧 handoff/saga 状态机、直接 SQL、历史改写、Hook/release 修改、合并、推送、部署 |

### 7.2 授权成立与失效

1. 卡片字节、隔离基线、WBS 真源、owned paths、执行模型或禁止事项任一漂移，审批立即失效。
2. 外部 Approval Receipt 绑定本卡完整字节 SHA-256、基线、WBS 提交、2 个路径、允许/禁止动作、执行模型、审批人与时间；卡片自身不含自身 SHA-256。
3. 实施批准与最终验收分离；执行 Agent 不得自签验收。

## 8. 治理执行顺序

1. 只读预检并输出事实表（§3），含 G1 修改前的基线数字。
2. 用户批准本卡后，创建并批准 SW-2026-008 的独立 CHG（领域 SCPT）与精确 Decision（§4 两路径，计划新增路径不检查基线存在）。
3. 创建 Work（`--card-file` 指向本卡，Work 与 Decision 的项目一致，均为 SW-2026-008）、在全新隔离候选（自 U07D 提交起，分支 `codex/m2-u08-workflow-compat`）启动 Run（`--lease-seconds` 不超过 3600）；**随即后台启动续租循环**（§3-7）。
4. 在候选中按 §5 实现并完成 §6 门禁；判卷结果写入 `.auto-pm/reports/m2-u08/` 下机器可读判卷文件。
5. 创建当前字节 Checkpoint（`git_head` 为基线，逐文件记录 SHA-256 与判卷文件 SHA-256），**先于提交**；随后走正常 Hook 提交（不得 `--no-verify`）；提交后核验提交内 blob 与 Checkpoint 逐一相同，否则停止。
6. Run/Work 终态、台账 `main.py ledger reconcile SW-2026-008` 为 0/0/0；CHG 收口须经用户弹窗确认后由 Claude 代跑，或由用户自己运行。
7. 向用户报告后停止；SHA 与 ID 写入交接文档。WBS 回写为独立的后续修订，不在本卡范围。

## 9. 有界纠正与硬停止条件

本卡单提交，一个主 Run；仅当失败稳定复现、完全落在 §4 路径内、无需合同或路径扩展时，允许一个纠正 Run（必须新建 Run 并重建 Checkpoint）。**执行期间不得修订本卡**；需要修订本卡即属于硬停止。

以下任一情况立即保留现场、停止并报告：

- 基线 HEAD、runtime 身份、Decision 字节或 owned paths 不一致，或需要第 3 条路径；
- 需要改 `pm.py`、`__main__.py`、任何 Facade/服务层代码或文档才能实现；
- 委托命令需要包装函数、重新声明选项或复制 `pm` 的逻辑才能工作（说明“同一命令对象”的前提不成立）；
- 只能通过 Mock `pm` 命令对象或其服务、硬编码预期输出、跳过测试、放宽断言、文件级抑制或 `noqa`/`type: ignore` 才能通过；
- 需要导入或恢复旧 handoff/saga/`pm-workflow` 状态机才能让某个旧动作“工作”——这类动作一律拒绝，不得兼容；
- 既有 `test_workflow.py`/`test_pm_facade.py` 出现需要改断言的失败；
- `tests/cli`、`tests/core`、`tests/change` 内出现无法归因于 E-G1-1 的失败，或 `tests/qml` 出现可复现的 Qt 崩溃（按 G2 流程仍无法通过）；
- Run 租约已过期（说明续租循环失效）：停止并报告，不得自行走恢复链；
- Checkpoint 不是当前字节，或质量门未完整返回；
- 发现本卡与代码事实矛盾（先停止，由用户裁决是否出新版本，不得自行改卡）。

## 10. 交付物

1. 基线 SHA 与预检事实表（含 G1 修改前的基线数字）；
2. CHG / Decision / Work / Run / Checkpoint ID 与 Approval Receipt；
3. 精确 diff 与 2 个路径的最终 SHA-256；
4. G1～G7 矩阵、原始命令、Exit Code、输出位置，以及 G2 对基线的逐目录对照；
5. G3 十类场景与测试名称的对照表；
6. 不可变提交 SHA 与 Checkpoint 绑定核对；
7. 明确声明：`auto-pm workflow` 保留原有 4 个命令，并把 7 个旧动作名直接委托给 `pm` 同名命令对象；其它旧动作被明确拒绝；未恢复任何旧写入状态机；CLI 参考文档仍待 D01 修订；运行时 `1.3.3-a808fa8` 不含 U05～U08 代码。

## 11. 与其他任务的关系

- **D01｜日常指引和薄适配引用**（依赖 V05、U08）：修订 `009_CLI命令参考.md` 等文档，使其指向已验证的高阶入口；本卡只提供代码层兼容。
- **V01～V08**：联合验收；本卡与其路径无交集。
- WBS 对 U05～U08 的回写与 M2 总审计不在本卡范围。
