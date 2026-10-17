# U07C｜薄 Cockpit SDK 与运行身份守卫实施卡

> 卡片编号：`CARD-SW008-M2-U07C`
> 对应 WBS：`U07`（WBS V3.0.18 §4.7）的第三部分，即 WBS 原文的“薄 Cockpit SDK”；U07A/U07B 已完成其前置接线
> 版本：`V1.0`（2026-10-01，一次定稿；执行期间不得修订，见 §9）
> 状态：`PLANNED / NOT_AUTHORIZED`（定稿，待授权；授权方式见 §7）
> 依赖：U07A（`795fe448`）与 U07B（`35379585`）均已验收收口（CHG-SCPT-2026-364/365/366 completed）
> 隔离基线：`35379585634253e45f68d8986c003eabf18a996b`
> 治理任务真源：WBS 提交 `572932a7d7fe23cf799c6f8800d77263aec3c3ee`；WBS SHA-256 `33EE746A6D9495B7B39D09921605D3745A405AE26D1EBC51450C60213ACD5FCD`
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或能力不低于它的模型；实际执行者 `Claude Sonnet 5.5`
> 禁用能力：`pm-workflow`

> V1.0 定稿说明：本卡写于一次**可行性演练**之后（§1.4）。演练在 U07A/U07B 的真实夹具上，用一个约 60 行的原型 SDK 把“新目标 → 范围卡 → 人工批准 → 真实执行 → 自动验证 → 验收 → 收尾”整条链真实跑通：Decision 生成、验证通过、重放相等、验收 `ACCEPTED`、收尾 `COMPLETED`、台账干净。原型与演练脚本归档于 `.auto-pm/reports/m2-u07c/`（`proto_api.py`、`diag_sdk.py`，仅供参考，不是产品代码）。执行者只做填空与验证，不得现场修订本卡、扩大路径或放宽门禁；遇到本卡未覆盖的情况按 §9 停止并报告。

## 1. 背景与已核实事实（2026-10-01，基线 `35379585`，均为命令或源码核验）

1. WBS U07 原文：单一交付“薄 Cockpit SDK”，拟新增 `auto_pm/api.py`、`tests/core/test_cockpit_api.py`，改 `auto_pm/__init__.py`；验收“SDK 经统一运行身份/Facade 从新目标到批准、真实 execute、验收落账完整实演；生产初始化不落到 editable/母体；不只验 import/查询”。AC09（CLI/GUI/SDK 行为与权限一致）依赖本卡提供 SDK 完整闭环。
2. 现状：CLI（`auto_pm/ui/cli/pm.py`）与驾驶舱各自拼装 `PmFacadeService` 调用；没有可被脚本/其它 Agent 直接 `import` 的稳定入口，也没有任何写入口检查“当前加载的包是否就是配置的运行时 release”。`WorkspaceContextService.resolve` 已能给出 `configured_release_id`、`effective_release_id`、`runtime_fallback_reason` 与 `conflicts`（`RUNTIME_IDENTITY_UNVERIFIED`：加载的包不在 `runtime_root/releases/<id>/auto_pm/__init__.py`、在工作区外或无法确定；`RUNTIME_IDENTITY_DIVERGENCE`：与指针不一致），并提供 `package_file_provider` 注入点——这就是“生产初始化不落到 editable/母体”的现成判据：开发树/母体源码加载时 `conflicts` 非空。
3. 完整链路所需的每一步在 U07A/U07B 之后都已存在：`create_planning_scope_card`、CHG 批准链（CLI `_approve_planning_change` 的逻辑）、`approve_planning_scope_card`（拒绝模型/Agent 自签与非 `user-confirmation:` 证据）、`run_approved_planning`（U07A）、`accept`、`PmCockpitService.close_accepted`（U06/U07B，收尾到 `COMPLETED`）。
4. **可行性演练结果**：原型（构造时解析一次运行身份、每次写入前检查 `conflicts` 与控制根、令牌只在内存、`run` 同一进程重放用同一令牌）驱动真实链路：`conflicts ()`、Decision 生成、`run` → `verified True`/`ACCEPTANCE_PENDING`、第二次 `run` 返回相等结果、`accept` → `ACCEPTED`、`close` → `COMPLETED`、`LedgerReconciler.reconcile` 为 0/0/0。即本卡不需要任何新的底层能力，只是把既有步骤收进一个带身份守卫的薄壳。
5. 一个必须在设计里处理的真实约束：`run_approved_planning` 的验证需要执行时的租约令牌，令牌设计上只在调用栈内、不落盘（卡 032 §5.2-3）。因此同一进程内重复 `run` 必须复用同一令牌；若进程重启后需求已处于 `ACCEPTANCE_PENDING`，令牌已不可得，SDK 必须明确拒绝重复执行并指引直接验收，而不是用新令牌去验证（会得到误导性的“质量验证未通过”）。
6. 明确**不在本卡**：CHG 状态推进（`pending_acceptance/accepting/completed`）及其审批人身份——它需要“谁是最终验收人”的身份模型，且更严格的 `SubstanceChecker` 仍会对 §6.3 的 `CHG-______` 关联单行报占位，二者都是治理决策，不是 SDK 能静默替用户做的事；本卡的 SDK 把需求收尾到 Mission `CLOSED` 与台账干净，CHG 状态仍沿用既有收口脚本推进（与 U07B 一致）。**用户已于 2026-10-01 在对话中裁决：继续由收口脚本承担，不为此新增卡或 SDK 能力**。GUI 开工接线、旧 workflow 兼容（U08）也不在本卡。
7. 基线质量（`35379585`，U07B 验收时的同一提交、同一命令）：分目录回归 contracts 191 passed 1 skipped；infrastructure 32 passed；cli 216 passed 1 skipped；qml 232 passed（排除一个测试）+ 该测试单独 1 passed；core 788 passed 1 skipped 3 failed（失败即 E-G1-1，位于 `tests/core/test_implementation_card_service.py`，非本卡路径）；`tests/change` 230 passed。原始输出：`.auto-pm/reports/m2-u07b/gates/`。G1 基线（本卡 §6 G1 同一集合去掉计划新增的 `test_cockpit_api.py`、`35379585` 干净检出、改动前实测）：113 passed、0 failed、0 skipped；原始输出 `.auto-pm/reports/m2-u07c/gates/G1_baseline.txt`（退出码 0）。
8. 已登记的基线例外沿用：E-G1-1、E-G1-2、E-G1-3、E-G3-1。
9. 不修改：`PmFacadeService`、`PmCockpitService`、`PmClosureService`、`WorkspaceContextService`、`ChangeService`、`DecisionService`、`ContinuityStore`、驾驶舱 QML/Bridge、CLI、Hook、release、任何 SQLite schema 或事件类型。

## 2. 单一目标（用户故事与完成定义）

作为用脚本或另一个 Agent 驱动 PM 的人，我 `import` 一个稳定入口，并且：

1. 用统一入口完成“新目标 → 范围卡 → 人工批准 → 真实执行 → 自动验证 → 验收 → 收尾”，每一步都经同一个运行身份检查与同一个 Facade；
2. 当前加载的包不是配置的运行时 release（开发树/editable/母体、工作区外、与指针不一致）时，**所有写入口都被明确拒绝且零写入**，只读的身份查询仍可用；
3. 批准永远来自调用方提供的真实审批人与 `user-confirmation:` 证据，SDK 不得自签、不得伪造；
4. 同一进程内重复执行是安全重放；跨进程重复执行被明确拒绝；
5. 不依赖调用方进程的当前目录，令牌不出现在任何返回值、日志或异常文本里。

## 3. 实施前预检（只读，先于任何写入）

1. 核验本卡字节 SHA-256 已被外部 Approval Receipt 绑定；核验 `隔离基线` 是 U07B 提交且可解析、WBS 提交与 SHA-256 一致。
2. 运行 `main.py implementation-card precheck --card-file` 对本卡，退出码必须为 0。
3. 核验 §4 中 1 个“存在”路径在基线上存在、2 个“计划新增”路径在基线上不存在。
4. 在隔离候选中，对 §6 G1 的目标测试文件（不含计划新增文件）复现基线结果并记录数字（修改前），ruff 与 mypy 对 §4 已存在的 Python 路径通过；不一致则停止。
5. 核验隔离候选 HEAD 等于基线，configured/effective runtime 与加载路径一致且无 fallback。
6. 阅读 `.auto-pm/reports/m2-u07c/proto_api.py` 与 `diag_sdk.py`，确认其调用顺序与本卡 §5 一致。
7. **续租（硬性）**：开始任何超过 30 分钟的门禁（G2 的 core 约 50 分钟）之前，先后台启动 `bash .auto-pm/reports/m2_renew_loop.sh <close.env>`；门禁结束后创建 `STOP_RENEW` 文件停止它。续租失效（租约过期）时停止并报告，不得自行走恢复链。

## 4. 精确 Owned Paths（3）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `auto_pm/api.py` | 计划新增 | `CockpitClient`、`CockpitIdentity`、`CockpitApiError` |
| 2 | `auto_pm/__init__.py` | 存在 | 只追加惰性导出（PEP 562 `__getattr__`）与 `__all__` 条目 |
| 3 | `tests/core/test_cockpit_api.py` | 计划新增 | 真实链路与身份守卫测试 |

出现第 4 条产品脏路径即停止，不得现场扩大 Decision。治理证据对象在控制根落账，不计入上述路径。

## 5. 合同（全部定稿，执行者不得改写含义）

### 5.1 模块与异常（`auto_pm/api.py`）

1. 使用真实包路径导入（`auto_pm.application.core.*`、`auto_pm.contracts.*`、`auto_pm.change.*`、`auto_pm.domain.*`、`auto_pm.infrastructure.*`），不使用 `auto_pm.core` 别名，使 `mypy --strict` 可见真实类型。
2. `CockpitApiError(RuntimeError)`：SDK 唯一对外异常。底层 `PmFacadeError`、`PmClosureError`、`PmCockpitError`、`WorkspaceContextError`、`WorktreePolicyError`、`TransitionGuardError`、`DecisionError`、`ContinuityStoreError`、`ValueError`（含 pydantic 校验错误）一律以 `CockpitApiError(str(原异常)) from 原异常` 重新抛出；不吞异常、不返回错误码代替异常。
3. `CockpitIdentity`（pydantic，冻结，`extra="forbid"`）：`project_id: str`、`workspace_root: str`、`configured_release_id: str`、`effective_release_id: str`、`runtime_load_path: str`、`runtime_fallback_reason: str`、`conflicts: tuple[str, ...]`、`writable: bool`；`writable` 恒等于 `not conflicts`（校验器强制）。由 `WorkspaceContext` 的同名字段映射，不含令牌或任何秘密。

### 5.2 客户端（`CockpitClient`）

构造：`CockpitClient(workspace_root: str | Path, project_id: str, *, facade: PmFacadeService | None = None, package_file_provider: Callable[[], str | Path | None] | None = None)`。

1. 构造时解析一次运行身份：`WorkspaceContextService(str(root), package_file_provider=…).resolve(project_id=project_id, start_path=root)`，其中 `root` 为 `Path(workspace_root).resolve()`；必须传 `start_path=root`，不得依赖进程当前目录，不得 `os.chdir`。解析失败抛 `CockpitApiError`。`facade` 为空时构造 `PmFacadeService(root)`；`facade`、`package_file_provider` 是测试/嵌入注入点，生产调用方不传。
2. `identity -> CockpitIdentity`：只读，返回**最近一次解析**的身份，不写任何数据。
3. **写入守卫** `_require_writable()`（所有写方法的第一步，早于任何写入、早于参数之外的任何副作用）：重新解析一次运行身份并更新 `identity`；`conflicts` 非空则抛 `CockpitApiError("运行身份未通过校验，SDK 已拒绝写入：" + "；".join(conflicts))`；随后 `WorktreePolicyService(root).require_control_root()`，失败抛 `CockpitApiError`。守卫失败时不得创建 `.auto-pm`、数据库、Mission、CHG、Decision 或任何文件（测试用“目录前后快照相同”证明）。
4. 写方法（全部关键字参数，返回既有 DTO，不新增 DTO）：
   - `plan(*, request_id, objective, acceptance: Sequence[str], scope_paths: Sequence[str], risks: Sequence[str], non_goals: Sequence[str], adapter: ExecutionAdapterKind, approved_model: str, declared_dirty_paths: Sequence[str] = ()) -> PlanningScopeCard`：构造 `PmIntent(subject_project_id=self 的 project_id, …)` 与 `PlanningExecutionGrant(adapter=…, approved_model=…, declared_dirty_paths=…)`，调用 `facade.create_planning_scope_card(...)`。
   - `approve_plan(card: PlanningScopeCard, *, approver: str, approval_evidence_ref: str) -> DecisionPackageDTO`：先按 CLI `_approve_planning_change` 的**同一规则**把卡绑定的 CHG 以调用方提供的 `approver` 推进到 `approved`（`draft→submitted→under_review→approved`、`submitted→…`、`under_review→approved`，评论 `user approved planning scope {plan_hash}`，已在 `approved/implementing/pending_acceptance/accepting/completed` 则不再流转，其它状态拒绝），再调用 `facade.approve_planning_scope_card(card, expected_plan_hash=card.plan_hash, approver=approver, approval_evidence_ref=approval_evidence_ref)`。**SDK 不得提供默认审批人或默认证据，不得自行构造 `user-confirmation:`**；模型/Agent 自签、非法证据由既有 `DecisionService` 拒绝并以 `CockpitApiError` 抛出。
   - `run(card: PlanningScopeCard) -> PmRunOutcome`：令牌 `secrets.token_urlsafe(32)` 仅保存在实例内存字典（键为 `card.plan_hash`），同一实例对同一卡重复调用复用同一令牌；调用 `facade.run_approved_planning(card, expected_plan_hash=card.plan_hash, lease_token=令牌, lease_token_environment="AUTO_PM_EXECUTION_LEASE_TOKEN")`。若实例内无该卡的令牌且该卡对应的 Mission 已处于 `ACCEPTANCE_PENDING`，抛 `CockpitApiError("该需求已执行并验证，等待验收；请直接确认验收，不要重复执行。")` 且不调用 `run_approved_planning`。Mission 状态通过 `facade.materialize_planning_mission(card)` 取得 `mission_id` 后以 `ContinuityStore(root).get_mission(mission_id).state` 读取。
   - `accept(mission_id: str) -> PmConfirmationCard`：`facade.accept(mission_id)`。
   - `close(mission_id: str) -> PmCockpitCompletion`：`PmCockpitService(root).close_accepted(mission_id)`（与驾驶舱同一幂等键与同一收尾）。
5. 只读方法：`mission_state(mission_id: str) -> MissionState`（`ContinuityStore(root).get_mission(...).state`，不经写入守卫、不写数据；Store 不可读抛 `CockpitApiError`）。
6. 令牌只在实例内存与调用栈内：不得写入日志、返回值、异常文本、任何持久化对象，也不得新增任何口令落点（`ContinuityStore` 既有的 `execution_leases.lease_token` 为唯一落点，本卡不触碰）。
7. 不得提供任何绕过 Facade 的捷径（直接 SQL、直接改 Mission/Work/Run 状态、直接写变更单）。

### 5.3 包导出（`auto_pm/__init__.py`）

只追加，不删改任何既有行：`__all__` 末尾追加 `"CockpitApiError"`、`"CockpitClient"`、`"CockpitIdentity"`；新增模块级 `__getattr__(name)`（PEP 562），当 `name` 是这三个名字之一时 `from auto_pm import api` 后返回 `getattr(api, name)`，否则 `raise AttributeError(f"module 'auto_pm' has no attribute {name!r}")`；`if TYPE_CHECKING:` 下导入三者供类型检查。**导入 `auto_pm` 本身不得加载 `auto_pm.api`**（惰性）。

### 5.4 测试夹具约定（`test_cockpit_api.py`）

1. 复用 `tests/core/test_pm_run_e2e.py` 已有的 `_build_workspace`、`_helper_source`、常量（`PROJECT_ID`、`CALC`、`CALC_TEST`、`FIXED_CALC`、`GOOD_TESTS`），不复制其代码；真实 Git 工作区、真实子进程辅助脚本、真实 pytest/ruff/mypy 质量门，不 Mock `EvidenceCollectionService`、`ContinuityExecutionService`、`PmClosureService`、质量收据或任何业务结果；
2. 运行身份守卫测试用一个带 `runtime_root`（`00_Infrastructure/auto_pm`，含 `active_release.json` 与 `releases/<id>/auto_pm/__init__.py` 文件）的工作区注册表，经 `package_file_provider` 注入“加载的包位置”，不修改真实运行时；
3. 每个场景结束不得在仓库内残留 `.coverage`、缓存、`tmp_*`。

### 5.5 必测场景（G3）

1. **完整真实实演**：从工作区外的当前目录构造 `CockpitClient`，经 `plan → approve_plan → run → run(重放) → accept → close`：Decision 生成；`run` 为 `verified True`；重放返回相等且未再启动辅助进程（计数文件）；`accept` 得 `ACCEPTED`；`close` 得 `COMPLETED`；`mission_state` 为 `CLOSED`；变更单已被回填、无占位且含 `**验证结论**` 行；`LedgerReconciler().reconcile(root).is_clean`；源工作区的范围文件字节不变；
2. **跨进程重复执行被拒绝**：场景 1 在 `run` 之后、`accept` 之前，用**新** `CockpitClient` 实例对同一卡调用 `run` → 抛固定异常、`run_approved_planning` 未被调用（事件总数不变）；随后原实例/新实例 `accept` 仍成功；
3. **身份守卫—拒绝**：注册表带 `runtime_root`，`package_file_provider` 分别返回 (a) 工作区内但不在 `releases/<id>/auto_pm/__init__.py`（模拟 editable/母体）、(b) 工作区外路径、(c) 另一个 release 目录下的 `__init__.py`（与指针不一致）：每种情况下 `identity.writable` 为 `False`、`conflicts` 含对应固定代码；`plan`、`approve_plan`、`run`、`accept`、`close` 全部抛 `CockpitApiError`；调用前后工作区文件树快照完全相同（无 `.auto-pm`、无数据库、无变更单变化）；`identity` 与 `mission_state` 的只读调用不报错；
4. **身份守卫—放行与实时重查**：`package_file_provider` 返回当前配置 release 的 `releases/<id>/auto_pm/__init__.py` → `writable True` 且 `plan` 成功；之后把 provider 切换为场景 3(a) 的位置 → 下一次写入立即被拒绝（证明每次写入都重新解析，不是只在构造时检查）；
5. **无运行时映射的项目**：注册表无 `runtime_root` 的项目 → `conflicts ()`、`writable True`（场景 1 即此情形）；
6. **批准不可伪造**：`approve_plan` 用模型/Agent 风格审批人（如 `codex-agent`）、缺少或非法证据引用（如 `confirmed`）→ 各抛 `CockpitApiError`；无 Decision 产生、CHG 状态不被推进到 `approved` 之外的任何位置；SDK 签名中不存在默认审批人/证据；
7. **错误映射**：对不存在的 `mission_id` 调用 `accept`/`close`/`mission_state` 抛 `CockpitApiError`（不泄漏底层异常类型到调用方）；对构造参数 `project_id` 不在注册表中抛 `CockpitApiError`；
8. **隐私**：任一场景后，数据库除 `execution_leases.lease_token` 列外的全部文本、返回的 DTO、`CockpitApiError` 文本、日志捕获中都不含租约令牌；测试同时断言令牌确实只出现在该列；
9. **惰性导出**：在**全新子进程**里 `import auto_pm` 后 `"auto_pm.api" in sys.modules` 为 `False`；访问 `auto_pm.CockpitClient is auto_pm.api.CockpitClient`；访问未知名字抛 `AttributeError`；
10. **既有行为不变**：`tests/core/test_pm_facade_service.py`、`test_pm_run_e2e.py`、`test_pm_closure_service.py`、`test_pm_cockpit_service.py` 全部原样通过。

测试不得通过 Mock 业务结果、硬编码预期字段或跳过来变绿；单元层可对“外部副作用点”注入故障，但场景 1、2 必须使用真实子进程、真实质量门与真实收尾服务。

### 5.6 明确不做

不推进变更单状态、不设计最终验收人身份模型（见 §1.6）；不改 Facade/驾驶舱/收尾/上下文服务/CLI；不改 GUI 开工流程；不实现旧 workflow 兼容（U08）；不新增 schema、事件类型或迁移；不提供任何无批准链即启动执行的入口；不合并、不推送、不部署、不切换 release。

## 6. 门禁矩阵

所有命令均在隔离候选的项目根执行，使用工作区 `.venv` 解释器与 `-B`，先 `-o addopts= --no-cov -p no:cacheprovider`。

**G1 定向测试**（修改前先对基线跑同一集合（不含计划新增文件）并记录数字；修改后全部通过，0 失败，不新增跳过）：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider `
  tests/core/test_pm_facade_service.py tests/core/test_pm_run_e2e.py tests/core/test_pm_closure_service.py `
  tests/core/test_pm_cockpit_service.py tests/core/test_cockpit_api.py
```

基线数字：113 passed（§1.7）；执行者须在隔离候选中复现同一数字；候选须不少于 113 + 本卡新增测试数，且 0 failed、0 skipped。

**G2 分目录回归**（固定方法，同 U05～U07B；基线数字见 §1.7，候选相对基线：失败集合相同——core 仅 E-G1-1 的 3 个既存失败、通过数不少于基线、无新增失败、无新增跳过；`tests/change` 同样对比）：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/contracts
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/infrastructure
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/cli
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/change
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/core
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/qml --deselect tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events
```

`auto_pm/__init__.py` 的改动会被所有测试导入，因此上述各组都必须在**最终字节**上全量重跑；core 约 50 分钟，**必须先按 §3-7 启动续租循环**。`tests/qml` 组出现 Qt access violation 不得按 E-G1-2 豁免：先在全新进程单独重跑该文件一次并保存两次原始输出；仍崩溃则按 §9 停止。

**G3 必测场景**：§5.5 的 10 项各至少一个独立测试，并在判卷报告中列出“场景 → 测试名”对照。

**G4 静态质量**：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m ruff check --no-cache auto_pm/api.py auto_pm/__init__.py tests/core/test_cockpit_api.py
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m mypy --strict --no-incremental auto_pm/api.py auto_pm/__init__.py tests/core/test_cockpit_api.py
git diff --check
```

不得使用 `--follow-imports=skip`，不得新增文件级抑制或为通过门禁新增 `type: ignore`；`auto_pm/__init__.py` 里既有的 `# noqa: E402` 行不得改动，新增行不得带 `noqa`；在最终字节上运行。

**G5 范围与洁净**：`git diff --name-only` 加未跟踪文件的路径集合精确等于 §4 的 3 个路径；无 `.coverage`、缓存、`tmp_*` 残留（DEV-TMP-001）。

**G6 既有内容不变**：`auto_pm/__init__.py` 的 diff 中**没有任何被删除的行**（只追加）；`test_cockpit_api.py` 是新增文件；其余既有测试文件不在 owned paths 内、字节不变。

**G7 不触碰生产**：测试只使用临时仓库与临时库，不读写真实控制面与真实 `00_Infrastructure`；不改 Hook、release、`.auto-pm` 下任何运行态对象；e2e 的临时工作区在测试结束后被清理。

## 7. 实施授权签字门

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-U07C V1.0` |
| 实施批准 | `PENDING`（须用户在对话中明确批准；批准后以委托方式由 Claude 执行，回执另行生成） |
| 最终验收 | `PENDING`（验收与 CHG 最终收口由用户亲自执行，不委托） |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| 隔离基线 | `35379585634253e45f68d8986c003eabf18a996b` |
| Owned Paths | §4 的 3 个路径 |
| 执行模型 | `Claude Sonnet 5.5` |
| 明确禁止 | 第 4 条路径、直接 SQL、历史改写、Hook/release 修改、改动 Facade/驾驶舱/收尾/上下文服务/CLI、SDK 自签或伪造审批、`os.chdir` 之类的全局状态、推进变更单状态、合并、推送、部署 |

### 7.2 授权成立与失效

1. 卡片字节、隔离基线、WBS 真源、owned paths、执行模型或禁止事项任一漂移，审批立即失效。
2. 外部 Approval Receipt 绑定本卡完整字节 SHA-256、基线、WBS 提交、3 个路径、允许/禁止动作、执行模型、审批人与时间；卡片自身不含自身 SHA-256。
3. 实施批准与最终验收分离；执行 Agent 不得自签验收。

## 8. 治理执行顺序

1. 只读预检并输出事实表（§3），含 G1 修改前的基线数字。
2. 用户批准本卡后，创建并批准 SW-2026-008 的独立 CHG（领域 SCPT）与精确 Decision（§4 三路径，计划新增路径不检查基线存在）。
3. 创建 Work（`--card-file` 指向本卡，Work 与 Decision 的项目一致，均为 SW-2026-008）、在全新隔离候选（自 U07B 提交起，分支 `codex/m2-u07c-cockpit-sdk`）启动 Run（`--lease-seconds` 不超过 3600）；**随即后台启动续租循环**（§3-7）。
4. 在候选中按 §5 实现并完成 §6 门禁；判卷结果写入 `.auto-pm/reports/m2-u07c/` 下机器可读判卷文件。
5. 创建当前字节 Checkpoint（`git_head` 为基线，逐文件记录 SHA-256 与判卷文件 SHA-256），**先于提交**；随后走正常 Hook 提交（不得 `--no-verify`）；提交后核验提交内 blob 与 Checkpoint 逐一相同，否则停止。
6. Run/Work 终态、台账 `main.py ledger reconcile SW-2026-008` 为 0/0/0；**CHG 最终收口由用户执行**。
7. 向用户报告后停止；SHA 与 ID 写入交接文档。WBS 回写为独立的后续修订，不在本卡范围。

## 9. 有界纠正与硬停止条件

本卡单提交，一个主 Run；仅当失败稳定复现、完全落在 §4 路径内、无需合同或路径扩展时，允许一个纠正 Run（必须新建 Run 并重建 Checkpoint）。**执行期间不得修订本卡**；需要修订本卡即属于硬停止。

以下任一情况立即保留现场、停止并报告：

- 基线 HEAD、runtime 身份、Decision 字节或 owned paths 不一致，或需要第 4 条路径；
- 需要改 `PmFacadeService`、`PmCockpitService`、`PmClosureService`、`WorkspaceContextService`、`ChangeService`、`DecisionService`、`ContinuityStore`、CLI、驾驶舱代码才能实现；
- 只能通过 Mock 业务结果/质量门/收尾、硬编码 `COMPLETED`/`verified=True`、跳过测试、放宽断言、文件级抑制或手改数据库才能通过；
- 需要 `os.chdir` 或其它进程级全局状态才能让测试通过；
- SDK 需要提供默认审批人/证据、自行构造 `user-confirmation:`、或在守卫失败时仍产生任何写入才能通过；
- 令牌出现在 `execution_leases.lease_token` 以外的任何持久化对象、日志、异常文本或返回值中；
- `import auto_pm` 会加载 `auto_pm.api`（破坏惰性），或 `auto_pm/__init__.py` 的改动使任何既有测试组出现新增失败；
- 本卡路径内的测试出现可复现的 Qt 崩溃（按 G2 流程仍无法通过）；`tests/core` 或 `tests/change` 内出现无法归因于 E-G1-1 的失败，同样停止；
- Run 租约已过期（说明续租循环失效）：停止并报告，不得自行走恢复链；
- Checkpoint 不是当前字节，或质量门未完整返回；
- 发现本卡与代码事实矛盾（先停止，由用户裁决是否出新版本，不得自行改卡）。

## 10. 交付物

1. 基线 SHA 与预检事实表（含 G1 修改前的基线数字）；
2. CHG / Decision / Work / Run / Checkpoint ID 与 Approval Receipt；
3. 精确 diff 与 3 个路径的最终 SHA-256；
4. G1～G7 矩阵、原始命令、Exit Code、输出位置，以及 G2 对基线的逐目录对照；
5. G3 十类场景与测试名称的对照表；
6. 不可变提交 SHA 与 Checkpoint 绑定核对；
7. 明确声明：SDK 现在能经统一运行身份检查与 Facade，从新目标走到批准、真实执行、验证、验收与收尾（Mission `CLOSED`、台账干净）；变更单状态推进与最终验收人身份模型尚未设计；GUI 开工流程尚未接线；运行时 `1.3.3-a808fa8` 不含 U05/U06/U07A/U07B/U07C 代码。

## 11. 与其他任务的关系

- **U08｜旧 workflow 接口兼容**（依赖本卡）：现有命令保留；新 workflow 别名只委托 pm；不能恢复旧写入状态机；未知旧动作明确拒绝。可复用本卡的 SDK 作为委托目标。
- **GUI 开工接线**（与本卡无路径交集，可并行）：驾驶舱“确认开始”改用 U07A 的 `run_approved_planning`，需单独的卡与用户批准。
- **变更单状态推进与最终验收人身份**：本卡不处理（§1.6）；用户已裁决（2026-10-01）继续由收口脚本承担，不再作为待办卡。
- WBS 对 U05/U06/U07 的回写与 M2 总审计不在本卡范围。
