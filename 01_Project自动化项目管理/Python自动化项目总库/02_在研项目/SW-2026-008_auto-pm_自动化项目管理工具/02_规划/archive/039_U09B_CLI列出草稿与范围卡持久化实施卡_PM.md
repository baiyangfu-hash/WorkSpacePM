# U09B｜CLI 列出草稿与范围卡持久化实施卡

> 卡片编号：`CARD-SW008-M2-U09B`
> 对应 WBS：`U09B`（WBS V3.0.19 §4.7，由 `M2-GOV-WBS3` 提交 `79ab9516` 新增）；`V05` 的前置缺口第二部分
> 版本：`V1.0`（2026-10-01，一次定稿；执行期间不得修订，见 §9）
> 状态：`PLANNED / NOT_AUTHORIZED`（定稿，待授权；授权方式见 §7）
> 依赖：U09A 已验收收口（提交 `eebdeecb`，CHG-SCPT-2026-370 completed）
> 隔离基线：`eebdeecb76b7f1a0f85545f92da891f89f7504e1`
> 治理任务真源：WBS 提交 `79ab9516bff42be100b88e2a7a67e5c3358cf9b7`（V3.0.19，CHG-DOCU-2026-024 completed）；WBS SHA-256 `CE9054C1CBD6D9F5DF8B24FAA579948CD03971E6F8AC7C724A6F1F3DD89B2623`
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或能力不低于它的模型；实际执行者 `Claude Sonnet 5.5`
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

> V1.0 定稿说明：本卡写于一次**可行性演练**之后（§1.6）。演练用原型 `pm.py` 在真实的 `auto-pm` 命令入口上，把“列出驾驶舱草稿 → 为草稿起草并持久化范围卡 → 列出待批准卡 → 凭 request_id 与 plan_hash 批准”以及全部拒绝路径真实跑通（20/20）。原型与演练脚本归档于 `.auto-pm/reports/m2-u09b/`（`make_proto_pm.py`、`proto_pm.py`、`diag_u09b.py`、`diag_u09b_output.txt`，仅供参考，不是产品代码；`proto_pm.py` 是 `pm.py` 的完整参考实现，执行者可按它填空，但须满足 §5 的合同与门禁）。执行者不得现场修订本卡、扩大路径或放宽门禁；遇到本卡未覆盖的情况按 §9 停止并报告。
> 路径偏差说明：WBS 的 U09B 行只写了 `CLI/pm.py`，并注明“测试与其余确切路径以开工前勘测后的实施卡为准”。勘测发现一个必须在源头堵住的缺陷（§1.5：按哈希批准会在项目已有未终结任务时写了一半才失败），守卫属于 Facade 的批准方法，故本卡增加 Facade 一个路径及其测试；WBS 对本卡实际路径的回写留到 M2 总审计。

## 1. 背景与已核实事实（2026-10-01，基线 `eebdeecb`，均为命令或源码核验）

1. WBS U09B 原文：“`pm` 能列出草稿与待批准范围卡；`pm plan` 经 U09A 的提交方法持久化范围卡；`pm approve` 可只凭 request_id 与 plan_hash 批准；既有参数形式保持兼容”。用户 2026-10-01 的裁决：范围卡由 PM（Claude）经 CLI/SDK 起草，驾驶舱只展示给用户审；驾驶舱的 `request_id` 对用户不可见，所以 PM 必须能从规范库列出草稿。
2. 现状：`pm plan` 的新需求形式只在内存里算出范围卡并打印，**不持久化**；`pm approve` 的新需求形式要求调用方把范围、风险、非目标、执行授权**原样再传一遍**；没有任何命令能列出草稿或待批准的卡，驾驶舱保存的草稿（`REQ-COCKPIT-…`）PM 看不到。
3. U09A 已提供 Facade 能力（`eebdeecb`）：`list_planning_drafts(project_id)`、`list_pending_planning_scope_cards(project_id)`、`submit_planning_scope_card(request_id, scope_paths, risks, non_goals, execution_grant, submitted_by)`（要求草稿已存在，execution_grant 必填）、`approve_pending_planning_scope_card(request_id, expected_plan_hash, approver, approval_evidence_ref) -> PlanningApprovalResult`（一次完成 CHG 批准、Decision、Mission、Work）。本卡只把它们接到命令行。
4. 与既有测试的耦合（已核实）：`tests/cli/test_pm_facade.py` 与 `tests/cli/test_workflow_compat.py` 通过 `monkeypatch.setattr("auto_pm.cli.pm._facade", …)` 打桩，所以新代码必须继续经 `_facade(ctx)` 取得 Facade；U08 的 `workflow` 兼容层用固定元组 `("plan","approve","confirm-start","execute","accept","resume","context")` 把这 7 个名字绑定到 `pm` 的**同一命令对象**，因此 `workflow plan`/`workflow approve` 会自动获得新形式，而新增的 `drafts`/`pending` 不在元组里，`workflow drafts` 仍按既有机制被拒绝（退出码 2）；既有测试对 `pm_group` 的命令集合没有精确断言。
5. **勘测发现的缺陷（本卡要堵）**：数据库有唯一索引“同一项目只能有一个未终结 Mission”。演练中，第一个请求已批准（Mission 为 DRAFT）时再批准第二个请求，`approve_pending_planning_scope_card` 的 CHG 批准与 Decision 都已写入、Decision 已绑定，才在创建 Mission 那一步报“同一项目已有未终结 Mission”——留下“已批准但没有任务”的半成品：该请求从待批准列表消失（已有 Decision 绑定），草稿总览却显示已批准。可恢复（待第一个任务终结后重放批准即可）但不可见，也违背“被拒绝的批准不写任何东西”。修复：**首次批准前**检查项目是否已有未终结 Mission，有就在写入前拒绝；已批准请求的重放不受影响（§5.2）。数据库唯一索引仍是并发情况下的最后防线。
6. **可行性演练结果**（`.auto-pm/reports/m2-u09b/diag_u09b_output.txt`，20/20）：`drafts` 列出驾驶舱草稿且含阶段字段；草稿形式 `plan` 持久化范围卡，输出就是该卡 JSON；重放完全相同且不新增修订；范围变化得到修订 2 并取代旧修订；未知草稿报“不存在”；两种形式的缺参提示各自列出缺项；完整形式 `plan` 持久化且输出与此前同形、重放相同；短形式 `approve` 对已被取代的哈希拒绝、对最新哈希批准并输出 `AUTHORIZED` 与 `work_state`（不含内部编号）、重放相同；项目已有未终结任务时首次批准被拒绝且什么都没写、该任务自己的请求重放仍相同；模型自签、未知哈希、`--owner` 被拒绝；旧的完整形式 `approve` 不变；批准后 `plan` 被拒绝（“已批准”）；linked worktree 对四个命令均拒绝且不创建 `.auto-pm`。
7. 基线（`eebdeecb` 干净检出、改动前实测）：G1 目标集合（5 个既有文件）**106 passed**、0 failed、0 skipped，用时约 4 分钟，输出 `.auto-pm/reports/m2-u09b/gates/G1_baseline.txt`（退出码 0）；§4 中 2 个已存在的 Python 路径在基线上 `ruff` 与 `mypy --strict` 均通过（`G4_baseline_ruff.txt`、`G4_baseline_mypy.txt`，退出码 0）。
8. G2 基线（U09A 验收时的同一提交 `eebdeecb`、同一命令）：contracts 191 passed 1 skipped；infrastructure 32 passed；cli 230 passed 1 skipped；qml 241 passed（排除一个测试）+ 该测试单独 1 passed；core 847 passed 1 skipped 3 failed（失败即 E-G1-1，位于 `tests/core/test_implementation_card_service.py`，非本卡路径）；`tests/change` 230 passed。原始输出：`.auto-pm/reports/m2-u09a/gates/`。
9. 已登记的基线例外沿用：E-G1-1、E-G1-2、E-G1-3、E-G3-1。
10. **明确不在本卡**：驾驶舱界面、Bridge、批准人配置项与 `DecisionService` 的模型自签规则补全（U09C）；SDK `api.py`；文档（含 `009_CLI命令参考.md`，留给 D01）；`workflow` 命令组与 `__main__.py`；Store 与合同模型；任何 schema、事件类型、迁移。

## 2. 单一目标（用户故事与完成定义）

作为起草范围卡的 PM：

1. `pm drafts --project-id PID` 能看到该项目的全部规划草稿（含驾驶舱保存的、用户不可见编号的草稿），每项带目标、验收条件、范围卡阶段与是否已批准；
2. `pm plan` 起草的范围卡被**持久化**；为已保存的草稿起草时只需 `--request-id` 加范围、风险、非目标、执行授权，不必重述目标与验收；原有的完整形式继续可用且输出同形；
3. `pm pending --project-id PID` 能看到待批准的最新范围卡；
4. `pm approve --request-id R --plan-hash H --approver A --approval-evidence-ref E` 凭已保存的卡一次完成批准，不必重传范围；既有的完整形式不变；
5. 项目已有未终结任务时，首次批准在写入任何东西之前被明确拒绝；
6. 所有新输出不含 mission/decision/work 内部编号；既有 `--mission-id` 兼容形式与 `execute/confirm-start/accept/resume/context/workflow` 一字不变。

## 3. 实施前预检（只读，先于任何写入）

1. 核验本卡字节 SHA-256 已被外部 Approval Receipt 绑定；核验 `隔离基线` 是 U09A 提交且可解析、WBS 提交与 SHA-256 一致。
2. 运行 `main.py implementation-card precheck --card-file` 对本卡，退出码必须为 0。
3. 核验 §4 中 2 个“存在”路径在基线上存在、2 个“计划新增”路径在基线上不存在。
4. 在隔离候选中，对 §6 G1 的目标测试文件（不含计划新增文件）复现基线结果并记录数字（修改前），ruff 与 mypy 对 §4 已存在的 Python 路径通过；不一致则停止。
5. 核验隔离候选 HEAD 等于基线，configured/effective runtime 与加载路径一致且无 fallback。
6. 阅读 `.auto-pm/reports/m2-u09b/proto_pm.py`（参考实现）与 `diag_u09b.py`，确认其做法与本卡 §5 一致。
7. **续租（硬性）**：开始任何超过 30 分钟的门禁（G2 的 core 约 55 分钟）之前，先后台启动 `bash .auto-pm/reports/m2_renew_loop.sh <close.env>`；门禁结束后创建 `STOP_RENEW` 文件停止它。续租失效（租约过期）时停止并报告，不得自行走恢复链。

## 4. 精确 Owned Paths（4）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `auto_pm/ui/cli/pm.py` | 存在 | 新增 `drafts`/`pending`，`plan` 持久化并支持草稿形式，`approve` 支持短形式 |
| 2 | `auto_pm/application/core/pm_facade_service.py` | 存在 | 在 `approve_pending_planning_scope_card` 内追加“已有未终结任务”守卫（只追加，§5.2） |
| 3 | `tests/cli/test_pm_pending_cards.py` | 计划新增 | 命令行测试 |
| 4 | `tests/core/test_pm_approval_guard.py` | 计划新增 | 守卫测试 |

出现第 5 条产品脏路径即停止，不得现场扩大 Decision。治理证据对象在控制根落账，不计入上述路径。

## 5. 合同（全部定稿，执行者不得改写含义）

### 5.1 `auto_pm/ui/cli/pm.py`

通用规则：所有新增与改动的命令先在 `try` 内调用 `_require_control_root(ctx)`，再经 `_facade(ctx)` 取 Facade（既有测试对 `_facade` 打桩）；`PmFacadeError`、`WorktreePolicyError`、`ValueError` 一律转 `click.ClickException`（退出码 1，不泄漏堆栈）；JSON 一律 `ensure_ascii=False, indent=2`；任何命令输出的 JSON 里**不得出现** `mission_id`、`decision_id`、`work_id` 键；不新增环境变量、文件或持久化对象；`from click.core import ParameterSource` 这一行 import 可新增。

1. **`pm drafts --project-id PID`**（`--project-id` 必填）：只读。输出 `{"schema_version": "pm-planning-drafts.v1", "project_id": PID, "drafts": [PlanningDraftOverview.model_dump(mode="json"), …]}`，没有草稿时 `drafts` 为 `[]`，退出码 0。调用 `facade.list_planning_drafts(PID)`。
2. **`pm pending --project-id PID`**（`--project-id` 必填）：只读。输出 `{"schema_version": "pm-pending-scope-cards.v1", "project_id": PID, "cards": [SubmittedPlanningScopeCard.model_dump(mode="json"), …]}`。调用 `facade.list_pending_planning_scope_cards(PID)`。
3. **`pm plan`**：
   - 新增选项 `--submitted-by`（默认 `pm-cli`，`show_default=True`），记录范围卡提交者（写入事件链）；`--mission-id` 兼容形式一字不变，且不使用该选项（给了新需求参数与 `--mission-id` 混用仍报原有错误）。
   - **形式判定**：`--mission-id` 为空、`--request-id` 非空，且 `--project-id`、`--objective`、`--acceptance` 三者**都没给** → **草稿形式**；其余新需求调用 → **完整形式**。
   - **完整形式**（原有参数不变）：先 `facade.create_planning_draft(PmIntent(subject_project_id, request_id, objective, acceptance_criteria))`，再 `facade.submit_planning_scope_card(request_id, scope_paths=…, risks=…, non_goals=…, execution_grant=PlanningExecutionGrant(adapter=ExecutionAdapterKind(…), approved_model=…, declared_dirty_paths=…), submitted_by=…)`。必填项检查与文案沿用：缺项时报 `新需求 plan 缺少必填参数: ` 加缺项列表（`--project-id --request-id --objective --acceptance --scope --risk --non-goal --adapter --approved-model` 中缺的）。
   - **草稿形式**：不创建草稿，直接对已保存的草稿调用上述 `submit_planning_scope_card`。必填项为 `--scope --risk --non-goal --adapter --approved-model`，缺项时报 `按已保存草稿提交范围卡缺少必填参数: ` 加缺项列表。草稿不存在时 Facade 的错误原样转为退出码 1（文案含“不存在”）。
   - 两种形式都输出**该范围卡本身**：`card.model_dump_json(indent=2)`（即 `PlanningScopeCard`，`schema_version` 为 `planning-scope-card.v1`，与此前同形，且与 `pending` 中对应项的 `card` 相等）。
   - 语义：重放（相同参数）输出完全相同、不新增修订与事件；范围、风险等变化得到新修订并取代旧修订；请求已批准后再 `plan` 退出码 1 且输出含“已批准”（Facade 文案原样）。
   - 更新 `plan_pm` 的 docstring 说明持久化与草稿形式。
4. **`pm approve` 短形式**：判定为 `--mission-id` 为空、`--root-work-id` 为空、`--request-id` 非空，且 `--project-id --objective --acceptance --scope --risk --non-goal --adapter --approved-model --declared-dirty` 九项**全都没给**。短形式仍要求 `--plan-hash --approver --approval-evidence-ref`（缺项沿用既有 `新需求批准缺少必填参数: ` 文案）。流程：`facade.approve_pending_planning_scope_card(request_id, expected_plan_hash=plan_hash, approver=approver, approval_evidence_ref=approval_evidence_ref)`；随后 `card = facade.recover_planning_scope_card(result.mission_id)`、`work = facade.create_planning_work(card)`（均为幂等读取/重放，用于得到 `work_state`，不得另造路径）；输出与完整形式同形的 JSON：`schema_version` 为 `pm-plan-approval.v1`，键恰为 `request_id`、`subject_project_id`、`change_id`、`plan_hash`、`authorization_status`（`AUTHORIZED`）、`work_state`（`work.state.value`）。短形式下显式给了 `--owner`（`ctx.get_parameter_source("owner") is ParameterSource.COMMANDLINE`）→ 退出码 1，文案 `按哈希批准已保存范围卡时不支持 --owner`。
   - 完整形式（九项中任一给了）与 `--mission-id` 兼容形式的行为与输出**一字不变**；完整形式的末尾 JSON 输出与短形式共用同一个私有输出函数（输出内容不变）。
5. **其余命令**（`confirm-start`、`execute`、`accept`、`workflow`、`resume`、`context`）与 `_planning_scope_card`、`_approve_planning_change`、`_emit_card` 的行为一字不变。参考实现见 `proto_pm.py`。

### 5.2 `auto_pm/application/core/pm_facade_service.py`（只追加）

在 `approve_pending_planning_scope_card` 里，取得 `card = submitted.card` 之后、调用 `self._approve_planning_change(card, approver)` 之前，追加守卫，并新增一个私有方法：

```python
            if not self._planning_request_is_approved(card) and self._store.list_missions(
                card.subject_project_id
            ):
                raise PmFacadeError("项目已有未终结的任务；请先验收或取消它，再批准新的范围卡")
```

```python
    def _planning_request_is_approved(self, card: PlanningScopeCard) -> bool:
        return any(
            item.approved
            for item in self._store.list_planning_drafts(card.subject_project_id)
            if item.draft.request_id == card.request_id
        )
```

语义与边界：① 只在**首次批准**（请求尚无 Decision 绑定）时检查；已批准请求的重放不受影响（它自己的任务可能仍未终结）；② `list_missions(project)` 取未终结（非 ACCEPTED/CLOSED/CANCELLED）的 Mission；③ 拒绝发生在任何写入之前：CHG 状态、Decision 绑定、事件、Mission、Work 均不变，该卡仍在待批准列表里；④ 其它项目的未终结任务不影响本项目；⑤ 不改任何既有语句，守卫文字与新方法是对该文件的纯新增（diff 中零删除行）；⑥ 数据库“同一项目一个未终结 Mission”的唯一索引保持不动，仍是并发下的最后防线，本守卫是预检而非锁。

### 5.3 必测场景（G3）

**命令行测试 `tests/cli/test_pm_pending_cards.py`**（用真实 `auto-pm` 入口、`CliRunner`、真实 Store 与 Git 临时仓；复用 `tests/cli/test_pm_facade.py` 的 `_setup_planning`、`_planning_args`、`_git` 与 `tests/cli/conftest.py` 的 `cli_runner`，只导入不修改；驾驶舱形态的草稿用 Facade 的 `create_planning_draft` 预置）：

- **c01**：`drafts` 列出驾驶舱草稿，含 `card_revision`、`approved`、目标与验收条件；没有草稿的项目返回空列表；别的项目的草稿不出现；输出键不含内部编号。
- **c02**：草稿形式 `plan` 持久化范围卡，输出与 `pending` 里该卡的 `card` 相等，`pending` 中 `revision` 为 1、`submitted_by` 为 `pm-cli`、`objective` 来自草稿；`executable` 为 false，无 mission/decision/work 键。
- **c03**：相同参数重放输出完全相同，修订号仍为 1，`PLANNING_SCOPE_CARD_SUBMITTED` 事件对该请求恰 1 条。
- **c04**：风险变化得到修订 2 且 `--submitted-by` 被记录；`pending` 只含最新修订；该请求的旧修订哈希按 §5.1 的批准被拒绝（见 c10）。
- **c05**：草稿不存在时退出码 1 且含“不存在”，库内范围卡行数与事件数不变。
- **c06**：两种形式的缺参文案各自正确且列出缺项；半给完整形式参数（如只给 `--request-id --objective`）按完整形式报缺项；失败时库内行数与事件数不变。
- **c07**：完整形式 `plan` 持久化，输出 `schema_version` 为 `planning-scope-card.v1` 且与此前同形，重放相同；`drafts` 显示其 `card_revision`。
- **c08**：短形式 `approve` 批准最新修订：输出恰为 §5.1-4 的键与值（`AUTHORIZED`、`READY`），CHG 变为 `approved`，`pending` 为空，库内 Decision 绑定、Mission、Work 各恰 1 个，输出无内部编号。
- **c09**：短形式重放输出相同，Decision 绑定、Mission、Work、事件总数不变。
- **c10**：拒绝且零写入（每例断言事件总数与 CHG 状态不变）：已被取代的哈希（含“取代”）、未知哈希、模型自签批准人（含“自签”）、非 user-confirmation 证据、缺 `--plan-hash/--approver/--approval-evidence-ref`、短形式给 `--owner`、`--mission-id` 与新需求批准参数混用。
- **c11**：旧完整形式 `approve` 不变：已有持久化卡时与没有持久化卡时都能批准并输出 `AUTHORIZED`/`READY`，批准后 `pending` 不含该请求。
- **c12**：请求已批准后 `plan`（两种形式）退出码 1 且含“已批准”，零写入。
- **c13**：linked worktree 下 `drafts`、`pending`、草稿形式 `plan`、短形式 `approve` 均退出码 1 且含 `linked worktree`，不创建 `.auto-pm`。
- **c14**：`workflow plan`（草稿形式）与 `workflow approve`（短形式）经委托得到与 `pm` 相同的结果；`workflow drafts` 退出码 2（未委托，按既有拒绝机制）。
- **c15**：项目已有未终结任务时，短形式首次批准退出码 1、含“未终结的任务”，零写入，该卡仍在 `pending`；取消第一个任务（Mission 经 `MissionService.transition` 到 `CANCELLED`）后，第二个请求的批准成功。

**守卫测试 `tests/core/test_pm_approval_guard.py`**（真实 Store、真实 ChangeService；复用 `tests/core/test_pm_pending_scope_card.py` 的 `_env`、`_Env`、`_add_project`、常量，只导入不修改）：

- **g01**：第一个请求已批准（Mission 为 DRAFT）时批准第二个请求被拒绝，文案含“未终结的任务”且**不含** `MISSION-` 字样；CHG 状态、Decision 绑定数、事件总数、Mission 与 Work 数均不变；该卡仍在待批准列表。
- **g02**：第一个请求自己的重放在其任务未终结时仍返回相同结果、数量不变。
- **g03**：第一个任务取消后，第二个请求批准成功并形成完整授权链。
- **g04**：另一个项目的未终结任务不阻挡本项目的批准。
- **g05**：守卫发生在 CHG 迁移之前：拒绝后 CHG 仍是 `draft`；随后在任务终结后批准，CHG 经完整补走到 `approved`。

测试不得通过 Mock 业务结果、硬编码预期字段或跳过来变绿；对 `auto_pm.cli.pm._facade` 的打桩只允许用于既有测试那样的“外部副作用点计数”，不得替换 Facade 的业务结果。

### 5.4 明确不做

不改驾驶舱服务/Bridge/QML、批准人配置项、`DecisionService`；不改 SDK `api.py`、`workflow.py`、`__main__.py`、Store、合同模型；不新增 schema、事件类型或迁移；不改任何文档；不提供撤回/退回范围卡的命令；不把 `drafts`/`pending` 委托给 `workflow`；不合并、不推送、不部署、不切换 release。

## 6. 门禁矩阵

所有命令均在隔离候选的项目根执行，使用工作区 `.venv` 解释器与 `-B`，先 `-o addopts= --no-cov -p no:cacheprovider`。

**G1 定向测试**（修改前先对基线跑同一集合（不含计划新增文件）并记录数字；修改后全部通过，0 失败，不新增跳过）：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider `
  tests/cli/test_pm_facade.py tests/cli/test_workflow.py tests/cli/test_workflow_compat.py `
  tests/core/test_pm_facade_service.py tests/core/test_pm_pending_scope_card.py `
  tests/cli/test_pm_pending_cards.py tests/core/test_pm_approval_guard.py
```

基线数字：106 passed（§1.7）；执行者须在隔离候选复现同一数字；候选须不少于 106 + 本卡新增测试数，且 0 failed、0 skipped。

**G2 分目录回归**（固定方法，同 U05～U09A；基线数字见 §1.8，候选相对基线：失败集合相同——core 仅 E-G1-1 的 3 个既存失败、通过数不少于基线（core 须不少于基线加本卡 core 新增测试数）、无新增失败、无新增跳过；`tests/change` 同样对比）：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/contracts
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/infrastructure
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/cli
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/change
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/core
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/qml --deselect tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events
```

各组都必须在**最终字节**上全量重跑；core 约 55 分钟，**必须先按 §3-7 启动续租循环**。`tests/qml` 组出现 Qt access violation 不得按 E-G1-2 豁免：先在全新进程单独重跑出问题的文件一次并保存两次原始输出；仍崩溃则按 §9 停止。

**G3 必测场景**：§5.3 的 c01～c15 与 g01～g05 各至少一个独立测试，并在判卷报告中列出“场景 → 测试名”对照；测试文件中的每个测试函数都须对应一个场景。

**G4 静态质量**：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m ruff check --no-cache auto_pm/ui/cli/pm.py auto_pm/application/core/pm_facade_service.py tests/cli/test_pm_pending_cards.py tests/core/test_pm_approval_guard.py
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m mypy --strict --no-incremental auto_pm/ui/cli/pm.py auto_pm/application/core/pm_facade_service.py tests/cli/test_pm_pending_cards.py tests/core/test_pm_approval_guard.py
git diff --check
```

不得使用 `--follow-imports=skip`，不得新增文件级抑制或为通过门禁新增 `type: ignore`/`noqa`；在最终字节上运行；两个新增（未跟踪）文件另行扫描行尾空白与制表符。

**G5 范围与洁净**：`git diff --name-only` 加未跟踪文件的路径集合精确等于 §4 的 4 个路径；无 `.coverage`、缓存、`tmp_*` 残留（DEV-TMP-001）；任何 `.qml` 文件无改动。

**G6 既有内容不变**：① `pm_facade_service.py` 的 diff 中**零删除行**；② `pm.py` 的 diff 中被删除或改写的行只允许来自两块基线文本：(a) `plan_pm` 的 docstring 行与新需求 `card = _planning_scope_card(…)` 调用块；(b) `approve_pm` 末尾的内联 `pm-plan-approval.v1` JSON 输出块；以及 import 行；③ 5 个既有 G1 测试文件与 `tests/cli/test_pm_facade.py`、`tests/cli/test_workflow_compat.py` 字节不变（不在 owned paths 内）。

**G7 不触碰生产**：测试只使用临时目录与临时库，不读写真实控制面的 `.auto-pm/continuity.db` 与真实 `00_Infrastructure`；不改 Hook、release、`.auto-pm` 下任何运行态对象。

**G8 变异检验**（执行者在代码完成后、最终门禁之前运行，结果绑定进判卷）：临时破坏下列至少 3 处，对应测试必须变红，源文件随后原样还原并校验字节；任一变异存活即停止：① 删除 Facade 守卫的抛错；② 让 `pm plan` 不再持久化（只构造不提交）；③ 去掉 `drafts` 或 `pending` 的 `_require_control_root` 调用；执行者可再增补。脚本与输出归档于 `.auto-pm/reports/m2-u09b/mutation_check.py`、`mutation_check_output.json`（做法同 `.auto-pm/reports/m2-u09a/mutation_check.py`）。

## 7. 实施授权签字门

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-U09B V1.0` |
| 实施批准 | `PENDING`（须用户在对话中明确批准；批准后以委托方式由 Claude 执行，回执另行生成） |
| 最终验收 | `PENDING`（验收由用户做出；CHG 收口须经用户在对话弹窗确认后才可由 Claude 代跑） |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| 隔离基线 | `eebdeecb76b7f1a0f85545f92da891f89f7504e1` |
| Owned Paths | §4 的 4 个路径 |
| 执行模型 | `Claude Sonnet 5.5` |
| 明确禁止 | 第 5 条路径、改驾驶舱/Bridge/QML/DecisionService/SDK/workflow.py/__main__.py/Store/合同模型、新增 schema 或迁移、对 Facade 既有语句做任何删除或改写、改文档、直接改真实库、历史改写、Hook/release 修改、合并、推送、部署 |

### 7.2 授权成立与失效

1. 卡片字节、隔离基线、WBS 真源、owned paths、执行模型或禁止事项任一漂移，审批立即失效。
2. 外部 Approval Receipt 绑定本卡完整字节 SHA-256、基线、WBS 提交、4 个路径、允许/禁止动作、执行模型、审批人与时间；卡片自身不含自身 SHA-256。
3. 实施批准与最终验收分离；执行 Agent 不得自签验收。

## 8. 治理执行顺序

1. 只读预检并输出事实表（§3），含 G1 修改前的基线数字。
2. 用户批准本卡后，创建并批准 SW-2026-008 的独立 CHG（领域 SCPT）与精确 Decision（§4 四路径，计划新增路径不检查基线存在）。
3. 创建 Work（`--card-file` 指向本卡，Work 与 Decision 的项目一致，均为 SW-2026-008）、在全新隔离候选（自 U09A 提交起，分支 `codex/m2-u09b-cli-scope-card`）启动 Run（`--lease-seconds` 不超过 3600）；**随即后台启动续租循环**（§3-7）。
4. 在候选中按 §5 实现、运行 G8 变异检验并完成 §6 门禁；判卷结果写入 `.auto-pm/reports/m2-u09b/` 下机器可读判卷文件。
5. 创建当前字节 Checkpoint（`git_head` 为基线，逐文件记录 SHA-256 与判卷文件 SHA-256），**先于提交**；随后走正常 Hook 提交（不得 `--no-verify`）；提交后核验提交内 blob 与 Checkpoint 逐一相同，否则停止。
6. Run/Work 终态、台账 `main.py ledger reconcile SW-2026-008` 为 0/0/0；CHG 收口须经用户弹窗确认后由 Claude 代跑，或由用户自己运行。
7. 向用户报告后停止；SHA 与 ID 写入交接文档。WBS 对本任务结果的回写为独立的后续修订，不在本卡范围。

## 9. 有界纠正与硬停止条件

本卡单提交，一个主 Run；仅当失败稳定复现、完全落在 §4 路径内、无需合同或路径扩展时，允许一个纠正 Run（必须新建 Run 并重建 Checkpoint）。**执行期间不得修订本卡**；需要修订本卡即属于硬停止。

以下任一情况立即保留现场、停止并报告：

- 基线 HEAD、runtime 身份、Decision 字节或 owned paths 不一致，或需要第 5 条路径；
- 需要改驾驶舱/Bridge/QML、`DecisionService`、SDK、`workflow.py`、`__main__.py`、Store、合同模型或任何文档才能实现；
- 需要对 Facade 既有语句做删除或改写才能加守卫；
- 既有 CLI 命令的输出、退出码或文案需要改变才能通过某个场景；
- 只能通过 Mock 业务结果、硬编码预期输出、跳过测试、放宽断言、文件级抑制或 `noqa`/`type: ignore` 才能通过；
- 既有测试出现需要改断言的失败；
- `tests/core`、`tests/cli`、`tests/change` 内出现无法归因于 E-G1-1 的失败，或 `tests/qml` 出现可复现的 Qt 崩溃（按 G2 流程仍无法通过）；
- 任一变异检验存活，或还原后字节不一致；
- Run 租约已过期（说明续租循环失效）：停止并报告，不得自行走恢复链；
- Checkpoint 不是当前字节，或质量门未完整返回；
- 发现本卡与代码事实矛盾（先停止，由用户裁决是否出新版本，不得自行改卡）。

## 10. 交付物

1. 基线 SHA 与预检事实表（含 G1 修改前的基线数字）；
2. CHG / Decision / Work / Run / Checkpoint ID 与 Approval Receipt；
3. 精确 diff 与 4 个路径的最终 SHA-256；
4. G1～G8 矩阵、原始命令、Exit Code、输出位置，以及 G2 对基线的逐目录对照；
5. G3 场景（c01～c15、g01～g05）与测试名称的对照表；
6. 不可变提交 SHA 与 Checkpoint 绑定核对；
7. 明确声明：`pm` 新增 `drafts`/`pending`，`plan` 持久化范围卡并支持草稿形式，`approve` 支持凭 request_id 与 plan_hash 批准；Facade 的按哈希批准在首次批准前拒绝“项目已有未终结任务”且不写任何东西；既有命令形式不变；驾驶舱、批准人配置与模型自签规则补全仍待 U09C；运行时 `1.3.3-a808fa8` 不含 U05～U09B 代码。

## 11. 与其他任务的关系

- **U09C**（依赖本卡与 U09A）：驾驶舱快照/Bridge/QML 展示待批准范围卡（读 U09A 的列表能力）、“批准范围并开始”单按钮（批准 + 接 U07D 的开始）、批准人配置项（未配置拒绝）与 `DecisionService` 模型自签规则补全（含 `claude`）。本卡的“项目已有未终结任务”守卫文案可被驾驶舱直接展示。
- **V05｜GUI 双领域联合验收**：依赖 U09A～U09C 全部完成。
- **D01**：修订 `009_CLI命令参考.md` 等文档，写入 `drafts`/`pending` 与新的 `plan`/`approve` 用法；本卡不改文档。
- WBS 对 U09 系列结果（含本卡实际 4 个路径）的回写与 M2 总审计不在本卡范围。
