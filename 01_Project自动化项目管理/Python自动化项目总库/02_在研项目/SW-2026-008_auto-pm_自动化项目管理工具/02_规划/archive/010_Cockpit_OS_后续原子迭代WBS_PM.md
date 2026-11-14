# Cockpit OS 后续原子迭代 WBS（PM）

> 文档状态：UNFROZEN_AFTER_ACCEPTANCE / READY_FOR_NG-WP-24
> 编制日期：2026-09-08
> 项目：SW-2026-008
> 新鲜恢复证据：`RESUME-8507F3C9721F3B2A`
> 事实包：`FACT-5B36E84E4EEE7DB8`
> 收尾提交前 Git HEAD：`a5d3166a`；最终 HEAD 以本次收尾提交后的 Git 记录为准。
> `next_legal_action`：NG-WP-24～48 恢复为逐包阶段0勘测、报批、执行和验收；不因解冻自动获得源码、发布、切流或清理授权。

## 1. 结论与边界

原《Cockpit OS 大一统集成与超级特种兵架构方案》尚未完全实现。当前可确认的是：W0/C2-C3 已在研发母体完成 27 路径实现、自动化验证和用户验收，`CHG-SCPT-2026-188` 已关闭；其余能力必须按本 WBS 逐包复核、回收、补齐、Dogfood 和发布。

本文件只授予规划可见性，不授予任何源码修改、CHG 关闭、提交、发布、切流、归档、删除或清理权限。每个实施包必须独立完成：fresh resume → 精确 CHG → 精确 DecisionPackage → execution handoff → 门禁 → PM 收尾 → 用户验收。

## 2. 当前事实基线

| 事实项 | 当前证据 | 裁决 |
|---|---|---|
| 稳定部署指针 | `active_release.json=1.2.4-6699a5b`；`previous_release.json=1.2.3-f950525` | 指针实物优先；`pm resume`/旧叙述中的“尚未切换”属于待纠偏漂移 |
| W0 决策链 | `DEC-20260908-34F0A422`；`AI-20260908-144338-D09FC0BF`；45 passed；Ruff/Mypy Exit 0；CHG-188 closed | 实现与用户验收完成；不等于稳定发布 |
| 事务与编排组件 | 候选容器存在；研发母体缺失 | 必须先做逐文件来源、哈希、依赖与语义裁决，再回收 |
| Facade / SDK | 研发母体和候选容器均未发现 `workflow_facade.py`、`api.py` | 属于净新增能力，不能声称完成 |
| workflow CLI | 研发母体仅有 `list/run/history/status` | `plan/execute/resume` 尚未形成 CLI 闭环 |
| 待验收队列 | `CHG-DOCU-2026-005`、`CHG-SCPT-2026-184/185` | 仍须逐项验收；CHG-188 已在本次用户授权下关闭 |

## 3. 路径与审批约定

- `DEV_ROOT`：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
- `CANDIDATE_ROOT`：`00_Infrastructure/auto_pm`，只作为候选来源与部署容器；禁止直接作为研发母体修改。
- `PYTHON`：`C:/Users/fubai/Documents/My_Workspace/.venv/Scripts/python.exe`
- 原子包编号采用 `NG-WP-19`～`NG-WP-48`，避免与已经使用的 `NG-WP-00`～`NG-WP-18` 混淆。
- 每包一个主要意图、目标执行时间 `<30 min`、一个独立停止点。相邻包不得用同一批准结论跨包执行。
- 所有源码包在开工前必须把目标文件写入新 DecisionPackage 的 `approved_paths`；表中路径是范围上限，不是自动授权。

## 4. 原子 WBS

### Wave A：状态裁决、验收与可恢复基线

| WP | 原子目标 | 精确范围/产物 | 依赖 | 硬验收与停止点 | 状态 |
|---|---|---|---|---|---|
| NG-WP-19 | 生成单一状态事实表 | 只读：`active_release.json`、`previous_release.json`、SW/SYS `PM_SESSION`、fresh `pm resume` | 无 | 指针、Git HEAD、active_changes、next_legal_action 四项一致性报告；发现冲突即停，不改状态 | COMPLETED |
| NG-WP-20 | 裁决遗留 handoff 生命周期 | 只处理 `AI-20260908-142440-1010ED65`、`AI-20260908-144106-F378E3F8`；输出前向 disposition | NG-WP-19 | 两项已标记 `expired` 并保留历史；另有同项目旧 SPEC stale 被项目级 timeout 同步标记 expired，已记录副作用 | COMPLETED_WITH_SIDE_EFFECT_NOTE |
| NG-WP-21 | 建立待验收矩阵 | `CHG-DOCU-2026-005`、`CHG-SCPT-2026-184/185/188` 的声明、实物、门禁、缺口逐项矩阵 | NG-WP-19 | W0 门禁全通过；其他 CHG 保持各自待验收/阻断，不批量关闭 | COMPLETED |
| NG-WP-22 | 完成 W0 用户验收闭环 | 仅 `CHG-SCPT-2026-188`、SW `PM_SESSION`、项目台账 | NG-WP-21 + 用户明确验收 | 45 passed；Ruff/Mypy Exit 0；`ledger reconcile SW-2026-008` Exit 0；用户已验收，CHG 已 closed | COMPLETED |
| NG-WP-23 | 建立 W0 可恢复 Git 检查点 | 仅 `DEC-20260908-34F0A422.approved_paths`、对应 CHG/PM 记录 | NG-WP-22 + 独立提交批准 | 提交 `0119fda2` 含 27 批准路径及对应 DecisionPackage/CHG；无 release 删除混入 | COMPLETED |

### Wave B：Phase 0～2 母体恢复与证明

| WP | 原子目标 | 精确范围/产物 | 依赖 | 硬验收与停止点 | 状态 |
|---|---|---|---|---|---|
| NG-WP-24 | 固化候选→母体来源清单 | 候选/母体的 `workflow_dtos.py`、`change_transaction.py`、`workflow_orchestrator.py` 及两份测试；SHA-256、imports、Git provenance | NG-WP-23 | 形成逐文件 ADOPT/REWORK/REJECT 裁决；只读，不复制 | NOT_APPROVED |
| NG-WP-25 | 回收 Workflow DTO | `DEV_ROOT/auto_pm/contracts/workflow_dtos.py`；对应 DTO 测试 | NG-WP-24 | import 冒烟和 DTO 测试 Exit 0；不得引入 application/domain 反向依赖 | NOT_APPROVED |
| NG-WP-26 | 回收事务管理器主体 | `DEV_ROOT/auto_pm/application/core/change_transaction.py` | NG-WP-25 | begin/record/rollback 基础冒烟 Exit 0；工作区外写入必须 fail-closed | NOT_APPROVED |
| NG-WP-27 | 固化事务失败与回滚测试 | `DEV_ROOT/tests/application/test_change_transaction.py` | NG-WP-26 | 正常、异常、重复恢复、越界路径用例全绿；测试不得修改真实项目 | NOT_APPROVED |
| NG-WP-28 | 回收编排器 plan 路径 | `DEV_ROOT/auto_pm/application/core/workflow_orchestrator.py` | NG-WP-25,NG-WP-27 | plan 只生成计划/审批材料，不进入 execution；定向测试 Exit 0 | NOT_APPROVED |
| NG-WP-29 | 固化 plan 防空壳测试 | `DEV_ROOT/tests/application/test_workflow_orchestrator.py` | NG-WP-28 | 缺 PID、缺事实包、空 approved_paths、陈旧事实均拒绝 | NOT_APPROVED |
| NG-WP-30 | 回收 execute verify-only 路径 | 同 `workflow_orchestrator.py` | NG-WP-29 | 默认 verify-only；缺 DecisionPackage、scope 越界、lease 过期均 fail-closed | NOT_APPROVED |
| NG-WP-31 | 固化 execute 补偿与隔离测试 | 同 `test_workflow_orchestrator.py` | NG-WP-30 | 失败注入后无半写、无自动 commit、可重复恢复；Exit 0 | NOT_APPROVED |
| NG-WP-32 | 回收 resume/checkpoint 路径 | 同 `workflow_orchestrator.py` | NG-WP-31 | 输出 evidence_id、fact_evidence_id、read_set、next_legal_action | NOT_APPROVED |
| NG-WP-33 | 固化 resume 漂移测试 | 同 `test_workflow_orchestrator.py` | NG-WP-32 | Git/指针/CHG 改变后旧事实包被识别为 stale；Exit 0 | NOT_APPROVED |

### Wave C：Facade 与 CLI 表现层

| WP | 原子目标 | 精确范围/产物 | 依赖 | 硬验收与停止点 | 状态 |
|---|---|---|---|---|---|
| NG-WP-34 | 新增 WorkflowFacade | `DEV_ROOT/auto_pm/application/workflow_facade.py`；对应单测 | NG-WP-33 | 仅包装应用层，返回标准结果；不得直接写 Git/台账 | NOT_APPROVED |
| NG-WP-35 | 新增 CLI plan | `DEV_ROOT/auto_pm/ui/cli/workflow.py` | NG-WP-34 | 保留 `list/run/history/status`；`plan --json` 契约测试 Exit 0 | NOT_APPROVED |
| NG-WP-36 | 新增 CLI resume | 同 `workflow.py` | NG-WP-35 | `resume [PID] --json` 与 PM resume 的关键事实一致；漂移 fail-closed | NOT_APPROVED |
| NG-WP-37 | 新增 CLI execute | 同 `workflow.py` | NG-WP-36 | 缺 `--decision-id` 必须失败；默认 verify-only；`--commit` 需要独立批准 | NOT_APPROVED |
| NG-WP-38 | 建立 CLI E2E 套件 | `DEV_ROOT/tests/cli/test_workflow_commands.py` | NG-WP-37 | help、plan、resume、execute 正/负路径全绿；无真实 commit | NOT_APPROVED |

### Wave D：Python SDK

| WP | 原子目标 | 精确范围/产物 | 依赖 | 硬验收与停止点 | 状态 |
|---|---|---|---|---|---|
| NG-WP-39 | 新增 `Cockpit` SDK 门面 | `DEV_ROOT/auto_pm/api.py`、`DEV_ROOT/auto_pm/__init__.py` | NG-WP-34 | `from auto_pm import Cockpit` 冒烟 Exit 0；API 不旁路 Facade 门禁 | NOT_APPROVED |
| NG-WP-40 | 固化 SDK 生命周期测试 | `DEV_ROOT/tests/application/test_cockpit_api.py` | NG-WP-39 | 上下文管理器正常/异常退出、重复关闭、只读默认值全绿 | NOT_APPROVED |

### Wave E：真实 Dogfood 与硬锁

| WP | 原子目标 | 精确范围/产物 | 依赖 | 硬验收与停止点 | 状态 |
|---|---|---|---|---|---|
| NG-WP-41 | Python 项目只读预演 | `SW-2026-009_英语学习助手`；仅 plan/resume/verify-only 与临时证据 | NG-WP-38,NG-WP-40 | 不改业务源码、不 commit；事实包和下一动作一致；异常即停 | NOT_APPROVED |
| NG-WP-42 | Python 项目受控执行演练 | SW-2026-009 中由独立 CHG/DEC 精确批准的一个测试断言 | NG-WP-41 + 独立业务批准 | 定向 pytest、项目门禁、ledger reconcile 全绿；commit 单独批准 | NOT_APPROVED |
| NG-WP-43 | PLC 项目静态预演 | `0100_PLC自动化/DJ-2026-005`；plan/resume/verify-only | NG-WP-38 | `plc check DJ-2026-005` Exit 0；不导入 TIA、不下发、不改 PLC 源码 | NOT_APPROVED |
| NG-WP-44 | Git 双硬锁负向复测 | 临时隔离 worktree/fixture；pre-commit、commit-msg | NG-WP-42,NG-WP-43 | 台账不一致与伪 CHG 均被拒绝；不得污染真实分支和根目录 | NOT_APPROVED |

### Wave F：回归、发布、回退与治理收口

| WP | 原子目标 | 精确范围/产物 | 依赖 | 硬验收与停止点 | 状态 |
|---|---|---|---|---|---|
| NG-WP-45 | 全量质量门禁 | `DEV_ROOT` 全量 pytest、Ruff、Mypy、doc check --strict、ledger reconcile | NG-WP-44 | 所有命令 Exit 0；任一失败即停止发布 | NOT_APPROVED |
| NG-WP-46 | 构建不可变候选槽位 | `00_Infrastructure/auto_pm/releases/<new-release-id>` 与 manifest；不改指针 | NG-WP-45 + 发布 CHG/DEC | exact-tree/manifest 100% 匹配；新槽位只写一次；失败不切流 | NOT_APPROVED |
| NG-WP-47 | 独立回退演练与受控切流 | 先演练新槽↔`1.2.4-6699a5b`；后续仅在独立明确批准时更新双指针 | NG-WP-46 + 切流批准 | resolve-only、startup guard、verify_release 全绿；切流前必须有可用 previous；失败原子回退 | NOT_APPROVED |
| NG-WP-48 | 文档/技能/PM 最终收口 | PRD/INT/DSN/TEC/CLI 文档、AGENTS/skills 的独立治理 CHG、SW/SYS PM_SESSION、ledger | NG-WP-47 + 独立规范变更批准 | 无死链、doc check --strict Exit 0、台账 0 差异、用户最终验收；`.trae` 未获专项批准不得改 | NOT_APPROVED |

## 5. 关键依赖链

`NG-WP-19 → NG-WP-20/NG-WP-21 → NG-WP-22 → NG-WP-23 → NG-WP-24 → NG-WP-25 → NG-WP-26 → NG-WP-27 → NG-WP-28 → NG-WP-29 → NG-WP-30 → NG-WP-31 → NG-WP-32 → NG-WP-33 → NG-WP-34 → NG-WP-35 → NG-WP-36 → NG-WP-37 → NG-WP-38 → NG-WP-39 → NG-WP-40 → NG-WP-41 → NG-WP-42 → NG-WP-43 → NG-WP-44 → NG-WP-45 → NG-WP-46 → NG-WP-47 → NG-WP-48`

仅 NG-WP-20 与 NG-WP-21 可在 NG-WP-19 后并行做只读取证；其余默认串行。任何包的失败、范围漂移、事实包过期或未获批准，都会阻断全部下游包。

## 6. 共用门禁命令模板

在工作区根目录执行，实际命令必须绑定当包 DecisionPackage 的精确路径：

```powershell
& .\.venv\Scripts\python.exe -m auto_pm -w . pm resume SW-2026-008 --json
& .\.venv\Scripts\python.exe -m pytest <approved-test-paths> --no-cov
& .\.venv\Scripts\python.exe -m ruff check <approved-source-and-test-paths>
& .\.venv\Scripts\python.exe -m mypy <approved-source-paths>
& .\.venv\Scripts\python.exe -m auto_pm -w . doc check SW-2026-008 --strict
& .\.venv\Scripts\python.exe -m auto_pm -w . ledger reconcile SW-2026-008
git diff --check -- <approved-paths>
git diff --name-only -- <approved-paths>
```

禁止使用 `git add .`、`--no-verify`、全仓格式化、reset/clean/stash/checkout 来制造绿灯。测试临时产物必须留在临时目录或 `.auto-pm/reports/`，结束后按 DEV-TMP-001 清理。

## 7. 模型路由

- 当前主控：负责 NG-WP-19～NG-WP-24 的事实裁决、架构边界、审批包和所有最终验收。
- `gpt-5.6-sol`：仅建议用于已批准的 NG-WP-25～NG-WP-40 精确编码包，以及 NG-WP-42/NG-WP-45 的机械执行与测试修复。
- Dogfood、发布、切流、规范/技能治理不整体移交给 SOL；必须由主控保持审批边界与 PM 收口。
- 不需要为了本规划切换模型，也不建议把整条任务迁移到 SOL。

## 8. 分批审批策略

不建议一次批准 NG-WP-19～NG-WP-48。首批只报批 **Wave A（NG-WP-19～NG-WP-23）**：先消除状态漂移、处理遗留 handoff、形成待验收矩阵、完成 W0 验收并建立可恢复检查点。Wave A 完成并重新 `pm resume` 后，再提交 Wave B 的精确路径 DecisionPackage。

## 9. 当前停止点

当前 Wave A 已执行完成；`CHG-SCPT-2026-188` 处于 `accepting`。根据 2026-09-08 用户冻结指令，最终验收关闭与 Wave B 及全部下游包均暂停；只允许先完成独立回归修正 WBS，经全量门禁和用户明确解冻后恢复。
