# SW-2026-008 PM 驾驶舱强制闭环 - Gemini 交接与后续 WBS

## 0. 交接目的与边界

本文件将当前 WBS-C1 实现和未收口的基线门禁工作交接给 Gemini。当前会话在写入本文件后停止编码；Gemini 应以工作区实况、`AGENTS.md`、PM_SESSION、变更单和 `auto_pm` 命令输出为准，不应把本文中的快照当作长期真源。

- 工作区：`C:\Users\fubai\Documents\My_Workspace`
- Git HEAD：`72c8a577799f40e30185805722668bb4474ecb73`
- 系统级 Full Track 母单：`CHG-SCPT-2026-156`，当前仍为 `draft`
- 当前实施范围：已批准 WBS-C1；另已批准“修复 C1 验收所阻断的全局 pytest/Ruff/Mypy 基线”补充范围。
- 未获批准范围：WBS-C2 至 C7、`.trae/`、Obsidian 规范真源、PLC/HMI 业务程序、真实硬件。

### 必须保留的约束

1. 先读代码、配置和真源文档，再提出业务问题或修改代码。
2. 未经用户新的阶段 1 批准，不实施 C2 至 C7。
3. 不要重置、清理或覆盖现有工作树；尤其不要恢复 `.auto-pm/ai_context.json` 的 Git 跟踪。
4. `.trae/` 由 Trae 生态维护，只读。
5. PM_SESSION、CHG、`.auto-pm/ai_feedback.json` 和台账仅由 `pm-workflow` 在验收全绿后收口；禁止先写收尾记录再补门禁。

## 1. 当前事实快照

最后一次只读预检证据为 `FACT-847FC5F0F1852AEB`，采集于 2026-09-02；事实包有效期很短，Gemini 开工前必须重新执行：

```powershell
& '.\.venv\Scripts\python.exe' -m auto_pm -w . project preflight SW-2026-008 --json
```

该次预检确认：

- 项目路径为 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`。
- PM_SESSION SHA-256 为 `9edfc133a1d5bbc249cd99004d7a00e5beff6bc7b59fe513b65847d51b375973`。
- 开放 CHG 为 `CHG-SCPT-2026-144`、`145`、`153`、`156`，均为 `draft`。
- `spec_registry.json` SHA-256 为 `172db09e0fabb766f191877755c40f9be467de6f5d351ef4932a9ab2e02c7b7f`，预检未发现项目 Spec Snapshot 漂移。
- 运行根为 `00_Infrastructure/auto_pm`，代码层为 `contracts/domain/infrastructure/application/ui`，共 185 个 Python 文件。

### 当前工作树

本批 C1 相关改动：

| 状态 | 路径 | 说明 |
|---|---|---|
| staged deletion | `.auto-pm/ai_context.json` | 从 Git 追踪中移除；本地运行态文件应保留但被 `.gitignore` 忽略。 |
| modified | `.gitignore` | 忽略 `.auto-pm/ai_context.json`。 |
| modified | `00_Infrastructure/auto_pm/auto_pm/ui/cli/project.py` | 新增只读 `project preflight` 和 `project fact validate` CLI。 |
| untracked | `00_Infrastructure/auto_pm/auto_pm/contracts/project_fact_snapshot.py` | 事实包 Pydantic Schema 与完整性指纹。 |
| untracked | `00_Infrastructure/auto_pm/auto_pm/application/core/project_fact_service.py` | 只读事实采集、篡改/过期/身份/工作树漂移拒绝。 |
| untracked | `00_Infrastructure/auto_pm/tests/application/test_project_fact_service.py` | 事实包和工作树漂移回归测试。 |
| untracked | `00_Infrastructure/auto_pm/tests/cli/test_project_preflight.py` | CLI 只读预检与事实验证回归测试。 |

以下是用户本地 Obsidian 状态，必须原样保留且不纳入本批提交：

- `00_Obsidian_Base全局规范文件仓库/.obsidian/community-plugins.json`
- `00_Obsidian_Base全局规范文件仓库/.obsidian/workspace.json`
- `00_Obsidian_Base全局规范文件仓库/.obsidian/plugins/hearth/`

## 2. 已完成的 WBS-C1 实现

### 新能力

1. `ProjectFactSnapshot` 使用 `project-fact.v1`，包含项目身份、Git SHA/状态、PM_SESSION 指纹、开放 CHG、规范注册表及版本漂移、代码结构和可用门禁。
2. `auto_pm project preflight <PID>` 完全只读；Git 查询使用 `GIT_OPTIONAL_LOCKS=0`，不会写入 Git 跟踪资产。
3. `auto_pm project fact validate <FACT_FILE> --pid <PID>` 硬拒绝缺字段、项目不匹配、过期、完整性篡改和当前工作树漂移。
4. `.auto-pm/ai_context.json` 已从版本控制索引移除，并加入 `.gitignore`，从而不会再因运行态上下文更新污染 Git 工作树。

### 已通过的范围内验证

```text
pytest tests/application/test_project_fact_service.py tests/cli/test_project_preflight.py
4 passed

ruff check <上述 C1 改动文件>
PASS

mypy <上述 C1 生产代码文件>
PASS

auto_pm python check SW-2026-008
PASS
auto_pm doctor
PASS
auto_pm spec check
PASS
auto_pm doc check
PASS
git diff --check
PASS
```

## 3. 正式交接记录与当前收口状态

| 请求编号 | 模式 | 状态 | 用途 |
|---|---|---|---|
| `AI-20260902-140735-8DB7AB48` | grooming | `consumed` | 已完成只读差距勘测。 |
| `AI-20260902-WBSC1-EXEC` | execution | `pending` | 原始 C1 实施交接，须在所有门禁全绿后提交 `handoff_result` 并由 PM 消费。 |
| `AI-20260902-WBSC1-BASELINE-EXEC` | execution | `pending` | 用户后续批准的全局基线门禁修复交接。 |

交接状态必须用驾驶舱复核：

```powershell
& '.\.venv\Scripts\python.exe' -m auto_pm -w . handoff show AI-20260902-WBSC1-EXEC --json-output
& '.\.venv\Scripts\python.exe' -m auto_pm -w . handoff show AI-20260902-WBSC1-BASELINE-EXEC --json-output
```

当前不能关闭这两份 execution handoff，也不能更新 PM_SESSION、CHG-SCPT-2026-156 或 ledger。原因是全量质量门禁尚未全绿。

## 4. 全局基线门禁债务

### 4.1 全量 pytest

在提升权限的环境下，全量执行结果为：

```text
3 failed, 1763 passed, 23 skipped, 62 warnings
```

失败项和当前推断根因：

| 失败测试 | 当前事实 | 建议修复原则 |
|---|---|---|
| `tests/test_pm_session_size.py::TestPmSessionSizeGate::test_pm_session_file_exists` | 测试硬编码查找 `00_Infrastructure/auto_pm/PM_SESSION_SW-2026-008.md`，但项目真源在项目目录。 | 让测试或服务通过项目定位机制找真源；不要复制 PM_SESSION 形成双账本。 |
| `tests/core/test_dashboard_service.py::TestDashboardService::test_get_summary_with_projects_changes_and_failed_checks` | 测试假定最近活动第一项必须为项目更新，当前实际排序为变更记录优先。 | 明确产品排序契约后修服务或测试；不要只为绿灯硬编码排序。 |
| `tests/core/test_pm_session_service.py::TestConstants::test_thresholds_reasonable` | 测试要求 `MAX_FILE_LINES >= 200`，实际常量为 150；归档历史表明 150 是已有治理决策。 | 以当前 PM_SESSION 规模策略为真源，修正过时测试或在用户决策后恢复阈值，二者不可并存。 |

此前沙箱环境还报出 54 个 QML 路径权限错误；提升权限后的全量 pytest 已排除该环境噪声，故不要把它误判为 C1 回归。

### 4.2 全量 Ruff

命令 `ruff check auto_pm` 当前有 49 个错误，其中 21 个可安全自动修复，主要分组为：

- `E402`：`auto_pm/__init__.py`、`domain/spec/services/fix_svc.py` 的导入顺序。
- `I001`：多个 facade、gate 与 workbench 文件的导入排序。
- `W291/W293/UP015`：尾随空格、空白行和冗余 `open(..., "r")` 参数。
- `N802/N815`：Modbus/QML 桥接需要暴露的 camelCase API 与 `logging.Handler.handleError` 覆盖方法。

处理 N802/N815 时要保留公开的 QML/Qt API 兼容性：优先使用项目已接受的 Ruff `noqa`、覆盖注解或公开适配层，不可机械改名导致 QML 调用断裂。

### 4.3 全量 Mypy

命令 `mypy auto_pm` 当前为 `50 errors in 21 files`。问题主要是 `no-any-return` 和少量泛型/忽略注解错误，按层分组：

- UI：`spec_center_dto.py`、`ui/qml/bridges/*`、`ui/cli/spec.py`、`ui/cli/python/__init__.py`。
- Domain：Vartable parsers/converter、PLC service/repairer、`change_service.py`。
- Infrastructure：`db/repository.py`、`db/sync.py`。
- Application：`core/project_service.py`、`workbench_use_cases.py`、`workbench_facade.py`、`delivery/archive_manager.py`。

修复必须补足真实返回类型、Protocol 或边界转换；不得以无边界 `Any`、宽泛 `cast` 或关闭 mypy 规则来伪造绿灯。

## 5. Gemini 开工顺序

1. 复核 `AGENTS.md`、本文件、原始 PM 交接文档、PM_SESSION、CHG-SCPT-2026-156 和两份 pending handoff。
2. 运行 `git status --short`，确认 C1 改动和用户 Obsidian 改动仍分别存在；不得使用 `git reset --hard`、`git checkout --` 或递归清理。
3. 重新运行 `project preflight`，记录新 `evidence_id`；仅将其作为当前批次事实证据。
4. 先执行 WBS-B0 至 B4，使 C1 可正式验收；这已获用户批准。
5. B4 完成且用户看到阶段 3 验收结果后，再按阶段 0 -> 阶段 1 报批 -> 阶段 2 执行的 PM 流程申请 C2/C3。C4 至 C7 同理，不可合并跳过批准。

## 6. 后续 WBS

### 已批准的 C1 收口前置 WBS

| WBS | 目标 | 主要工作 | 完成标准 |
|---|---|---|---|
| B0 | 复现与基线固化 | 在提升权限环境运行全量 pytest、Ruff、Mypy；记录精确失败清单。 | 失败可稳定复现，且不混入 QML 沙箱权限噪声。 |
| B1 | pytest 真源对齐 | 修复 PM_SESSION 定位、Dashboard 排序契约、阈值测试与真源的不一致。 | 全量 pytest Exit Code 0；不复制 PM_SESSION、不硬编码活动顺序。 |
| B2 | Ruff 兼容治理 | 修复导入/空白/冗余参数；为 QML/Qt 公开 camelCase API 建立兼容的 lint 豁免或适配。 | `ruff check auto_pm` Exit Code 0；公开 API 无断裂。 |
| B3 | Mypy 边界收敛 | 消除 21 个文件的 `Any` 泄漏、泛型和无效 ignore。 | `mypy auto_pm` Exit Code 0；不关闭严格规则。 |
| B4 | C1 终验与 PM 收口 | 全量回归；提交两份 handoff_result；由 PM 做 close、CHG/PM_SESSION/feedback/ledger 收口。 | 所有门禁 Exit Code 0，两个 execution handoff 均被消费，台账对账通过。 |

### 未批准、需逐批走 PM 报批的强制闭环 WBS

| WBS | 工作包 | 主要交付 | 完成标准 |
|---|---|---|---|
| C2 | 派发与执行生命周期 | `claim/start/heartbeat/result-submit/fail/timeout`、状态机、`ExecutorAdapter` | 无 request_id 的执行被拒绝；状态和队列可审计。 |
| C3 | PM 一页决策包 | DecisionPackage Schema、CLI、事实证据引用、草稿 CHG 接口 | 每项结论引用 `evidence_id`；只接受已消费 Grooming。 |
| C4 | Quick/Full 强制连接 | CHG 持久字段、文件影响检查、自动升级/暂停 | Quick 越界自动冻结并升级 Full。 |
| C5 | 领域门禁证据 | Evidence Schema、Exit Code/命令/哈希/INT 契约 | 伪 PASS 不能被 handoff 消费。 |
| C6 | PM Saga 收口 | CHG、PM_SESSION、ledger、evidence、feedback 检查点与补偿 | 任一步失败不得显示完成；重试无重复账。 |
| C7 | 全链 Dogfood | 稳定/候选双钥匙、SW 自管理、DJ-2026-005 消费验收、回退演练 | 候选不可自批；完整链可重复、可复核、可回退。 |

## 7. B4 的 PM 收口顺序

在所有 B0-B3 门禁均为 Exit Code 0 后，Gemini 应让 `pm-workflow` 按以下顺序收口：

1. 为 `AI-20260902-WBSC1-EXEC` 和 `AI-20260902-WBSC1-BASELINE-EXEC` 分别生成结构化 `handoff_result`，包含 changed files、所有命令、Exit Code、测试计数和未运行项。
2. 对每份 result 运行 `auto_pm handoff preflight`；仅预检全绿后运行 `auto_pm handoff close`，使用唯一幂等键。
3. 复用并更新 `CHG-SCPT-2026-156` 的当前基线/实施/验证记录，不删除其历史版本。
4. 由 PM 回写 SW-2026-008 PM_SESSION 的 §3、§8 和必要的 `.auto-pm/ai_feedback.json`，然后运行 `ledger reconcile`。
5. 重新执行全量 pytest、Ruff、Mypy、`python check`、doctor、spec check、doc check，并呈报用户最终验收。

在第 1 至 5 步完成前，严禁声称 C1 已结项。

## 8. 建议交给 Gemini 的起始提示词

```text
在 C:\Users\fubai\Documents\My_Workspace 继续 SW-2026-008 驾驶舱强制闭环。先读取 AGENTS.md、SYS-2026-001_WorkspaceGovernance/01_项目文档/13_SW-2026-008_PM驾驶舱强制闭环_Gemini交接与后续WBS.md、原始 12_ 交接文档、PM_SESSION、CHG-SCPT-2026-156，并用 auto_pm 复核 AI-20260902-WBSC1-EXEC 与 AI-20260902-WBSC1-BASELINE-EXEC。当前仅批准 B0-B4：修复全量 pytest/Ruff/Mypy 基线后完成 C1 PM 收口。保留用户 Obsidian 改动，不修改 .trae，不实施 C2-C7，不在门禁全绿前关闭 handoff 或回写 PM_SESSION/CHG/ledger。
```
