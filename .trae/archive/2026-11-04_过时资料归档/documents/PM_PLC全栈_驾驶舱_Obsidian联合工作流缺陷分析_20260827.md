# PM / PLC / 全栈技能 × 驾驶舱 × Obsidian 联合工作流缺陷分析

## 1. 摘要 (Summary)

复盘近几次任务（子代理物理隔离 RFC 落地、CHG-SCPT-2026-166 落账门禁下沉、DJ-2026-009 验证与补齐），发现联合工作流的根本缺陷不是「缺规范」，而是 **「文档真源」与「工具实现」之间的口径漂移（drift）**，以及 **「门禁声明」与「实测结果」之间的失真（falsification）**。这两类缺陷直接侵蚀「零负担交付铁律」赖以成立的可信度——AI 声称"全绿"，实测却非绿。

本计划产出一份 **P0/P1/P2 分级缺陷清单**，并对 **P0/P1 缺陷执行修复**（P2 仅记录不修改）。修复原则：**以代码实现为真源、文档向实现对齐**，仅做文档口径修正，不做代码重构。

## 2. 现状分析 (Current State Analysis)

### 2.1 联合工作流架构（已确认）

* **三技能**：`pm-workflow`（唯一落账 owner）→ 派发 `plc-electrical-engineer` / `fullstack-engineer`（纯执行者）

* **驾驶舱**：`auto-pm` CLI + QML GUI，通过 `.auto-pm/ai_context.json` / `ai_feedback.json` / `handoffs/<request_id>.json` 传递上下文

* **Obsidian**：`00_Obsidian_Base全局规范文件仓库/` 规范真源 + `spec_registry.json` 索引

* **交接契约**：`skill_context`（输入）→ `handoff_result`（输出）→ `pm_closure`（收尾落账）

### 2.2 缺陷清单（8 项，含证据）

| #  | 缺陷                       | 证据（文档 vs 实现）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |        分级        |
| -- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :--------------: |
| D1 | PM\_SESSION 阈值/归档路径口径漂移  | [pm\_session\_guide.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/pm-workflow/refs/pm_session_guide.md#L7-L8) 写「严格 ≤150 行」「历史目录 `00_项目管理/06_PM_SESSION历史/`」；代码 [pm\_session\_service.py](file:///c:/Users/fubai/Documents/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/pm_session_service.py#L32-L41) 实际 `MAX_FILE_LINES=300`、`MAX_FILE_SIZE_KB=150`、归档目录 `PM_SESSION归档`；[checker.py](file:///c:/Users/fubai/Documents/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/checker.py#L498-L519) 阈值「>150 warn / >300 fail」 |      **P0**      |
| D2 | 状态机文档 9 步 vs 实现 12 态     | [process\_gates.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/pm-workflow/refs/process_gates.md#L19-L22) 写「严格 9 步」「accepting→closed 非法」；[constants.py](file:///c:/Users/fubai/Documents/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/change/constants.py#L119-L132) 实际 12 态，含 `conditionally_approved`/`rejected`/`archived`，且 `completed→{closed,archived}`                                                                                                                                                                                                                           |      **P0**      |
| D3 | 门禁声明「全绿」vs 实测「非绿」        | [fullstack-engineer/SKILL.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/fullstack-engineer/SKILL.md#L27-L40) / [process\_gates.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/pm-workflow/refs/process_gates.md#L24-L30) 要求 `ruff/mypy/pytest` 全绿；实测全量 `mypy auto_pm` 50 errors、ruff 主环境缺失、pytest exit code 1（sandbox audit.log 误报）                                                                                                                                                                                                                                                                                         |      **P0**      |
| D4 | 沙箱 audit.log 使命令成败信号失真   | 本轮所有 `change transition` 写入 `C:\Users\fubai\.auto-pm\audit\audit.log` 被沙箱拦截返回非零码，但状态流转实际成功                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |      **P1**      |
| D5 | 新旧变更路径并存，「破坏性切换」名不副实     | [path\_resolver.py](file:///c:/Users/fubai/Documents/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/change/path_resolver.py#L140-L147) 注释称「破坏性切换后单路径」但仍保留 `11_监控`/`00_项目管理` 兼容路径；DJ-2026-009 台账仍在旧路径                                                                                                                                                                                                                                                                                                                                                                                                      |      **P1**      |
| D6 | handoff\_schema 示例编号口径漂移 | [handoff\_schema.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/pm-workflow/refs/handoff_schema.md#L31) 示例 `CHG-PLC-2026-001`；现网实际 `CHG-SCPT-2026-166`（域 `SCPT`），域命名习惯不一                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |      **P1**      |
| D7 | 机械三要素起手口径 vs 实际执行        | [skill\_coordination.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/shared/refs/skill_coordination.md#L23) 强制「机械CAD/3D、轴系、动作时序」起手门禁；但 DJ-009 实操未装三要素，靠驾驶舱 `plc check` 兜底                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |      **P2**      |
| D8 | spec\_registry 跨前缀编号冲突   | [spec\_registry.json](file:///c:/Users/fubai/Documents/My_Workspace/00_Obsidian_Base全局规范文件仓库/spec_registry.json#L20) `DEV-001` 与 [L115](file:///c:/Users/fubai/Documents/My_Workspace/00_Obsidian_Base全局规范文件仓库/spec_registry.json#L115) `PRD-001` 并存                                                                                                                                                                                                                                                                                                                                                                                                         | **P2**（用户已明确仅记录） |

### 2.3 根因归纳

1. **文档真源无自动化对账**：技能文档（`.trae/skills/**/refs/*.md`）与代码实现（`auto_pm/**`）之间没有「契约校验器」，阈值、状态机、路径等关键常量一旦在代码侧演进，文档即漂移。
2. **门禁声明语义含糊**：「全绿」未区分「改动文件全绿」vs「全量仓库全绿」，「ruff/mypy」未标注环境前置依赖。
3. **环境集成噪声**：沙箱对 `audit.log` 的写限制污染了 CLI 退出码，破坏了「命令成败即真值」的前提。

## 3. 拟变更 (Proposed Changes)

> 范围纪律：**只改文档，不改代码**；仅修正 6 处 P0/P1 文档口径，D7/D8 仅记录。

### 3.1 D1 — 修正 PM\_SESSION 阈值/归档路径（P0）

**文件**：[pm\_session\_guide.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/pm-workflow/refs/pm_session_guide.md)

**改动**（第 5-8 行 §1）：

* 「主文件：活跃快照，**严格 ≤150 行**，超过立即触发归档」→ 改为「主文件：活跃快照，阈值 **>150 行 warn、>300 行 fail、>150KB fail**，超过 300 行或 150KB 立即触发归档」。

* 「历史目录：`00_项目管理/06_PM_SESSION历史/YYYY-MM-DD_Vx.x.x.md`」→ 改为实际归档目录 `05_收尾/PM_SESSION归档/`（对齐 `ARCHIVE_DIR_NAME`）。

**为何**：使文档阈值与 [pm\_session\_service.py](file:///c:/Users/fubai/Documents/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/pm_session_service.py#L32-L41) 与 [checker.py](file:///c:/Users/fubai/Documents/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/checker.py#L498-L519) 完全一致，消除「≤150 行」与「300 行」的自相矛盾。

### 3.2 D2 — 修正状态机 9 步 → 12 态（P0）

**文件**：[process\_gates.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/pm-workflow/refs/process_gates.md)

**改动**（第 19-22 行 §2）：

* 「严格 9 步顺序」→ 改为「严格 12 态流转」。

* 补齐完整状态机：

```
draft → submitted → under_review → approved → implementing → pending_acceptance → accepting → completed → closed
                                          ↘ conditionally_approved ↗
under_review → rejected → draft（驳回退回）
completed → archived（归档，终态）
```

* 删除「`accepting → closed` 非法」这条（实现中 `accepting` 只能到 `completed`/`implementing`，`closed` 是终态），改为「`accepting → closed` 非法（须经 `completed`）；`completed` 可直通 `archived`」。

**为何**：使文档与 [constants.py STATUS\_FLOW](file:///c:/Users/fubai/Documents/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/change/constants.py#L119-L132) 完全一致，消除「9 步 vs 12 态」与「conditionally\_approved/rejected/archived 三态缺失」的误导。

### 3.3 D3 — 门禁声明明确口径（P0）

**文件**：[fullstack-engineer/SKILL.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/fullstack-engineer/SKILL.md) + [process\_gates.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/pm-workflow/refs/process_gates.md)

**改动**：

* [fullstack-engineer/SKILL.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/fullstack-engineer/SKILL.md#L27-L40) 第 27 行「必须自行运行 `ruff check` + `mypy` + `pytest --no-cov -q` 直至全绿」→ 补充口径：「全绿 = **改动文件** `ruff` 0 error + `mypy` 0 error + `pytest --no-cov -q` 0 failed；全量仓库的历史 mypy 错误不阻断本次交付，但需在 `handoff_result.verification` 中如实标注『全量 vs 改动文件』差异」。

* 第 40 行 `ruff check auto_pm/ && mypy auto_pm/` → 补充环境前置：「若主环境无 ruff，先 `pip install "ruff>=0.5,<0.6" --target .tmp_ruff` 临时装载，用完即删（DEV-TMP-001）」。

* [process\_gates.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/pm-workflow/refs/process_gates.md#L24-L30) 第 24-30 行「门禁实测强制检查」→ 同步补充同样的「改动文件 vs 全量」口径说明。

**为何**：消除「声称全绿」与「实测 50 errors」的失信风险，让门禁声明语义无歧义，可被外部审查如实验证（对齐 §4 审查报告验证规则）。

### 3.4 D4 — 记录沙箱退出码失真判定准则（P1）

**文件**：[process\_gates.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/pm-workflow/refs/process_gates.md)

**改动**（§2 门禁实测强制检查之后新增一条说明）：

* 新增「**退出码失真判定**：当命令因 `TRAE Sandbox Error: hit restricted ...audit.log` 返回非零码时，**不得据此判定业务失败**；须以命令正文输出的真实结果（如 `passed`/`Pass=44`）为准，并在 PM\_SESSION §6 记录『退出码受沙箱 audit.log 写限制污染』」。

**为何**：本轮所有 `change transition` 均因此误报，若后续 AI 将非零码当失败会误判阻塞。固化判定准则，避免重复踩坑。

### 3.5 D5 — 修正「破坏性切换」注释，承认双路径兼容期（P1）

**文件**：[path\_resolver.py](file:///c:/Users/fubai/Documents/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/change/path_resolver.py)

**改动**（第 10-15 行 docstring 与第 140-147 行注释）：

* 删除/修正「破坏性切换：不再区分 PLC / Python 两套路径，统一使用 5大过程组路径」与「破坏性切换后单路径」这一**不实声明**。

* 改为：「CHG-SCPT-2026-146 后**默认**使用 5 大过程组路径；为兼容历史项目（如 DJ-2026-009），`_CHANGE_SEARCH_PATHS` 仍保留 `11_监控`/`00_项目管理` 旧路径兜底，属**过渡兼容期**，待历史项目台账迁移完成后逐步下线」。

**为何**：注释与实现自相矛盾（声称「单路径」实则保留 3 条兼容路径），会让后续维护者误以为旧路径已废弃。修正为「默认新路径 + 兼容旧路径」的真实状态。**不改逻辑，只改注释**。

### 3.6 D6 — 统一示例编号口径（P1）

**文件**：[handoff\_schema.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/pm-workflow/refs/handoff_schema.md)

**改动**（第 31 行）：

* `"chg_updates": "CHG-PLC-2026-001 已更新至 implementing 状态"` → 改为 `"chg_updates": "CHG-SCPT-2026-166 已更新至 implementing 状态"`，并加注「编号格式 `CHG-{DOMAIN}-{YYYY}-{XXX}`，DOMAIN 为实际域缩写（如 SCPT/DOCU/PLC），勿用虚构域」。

**为何**：示例编号与实际现网命名（SCPT 域）不一致，易误导执行端套用错误前缀。对齐 [path\_resolver.py](file:///c:/Users/fubai/Documents/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/change/path_resolver.py#L34-L35) 的 `CHG-{DOMAIN}-{YYYY}-{XXX}` 正则。

### 3.7 D7 / D8 — 仅记录，不修改（P2）

* **D7 机械三要素起手门禁**：属流程策略问题，需用户另行决策是否放宽（DJ-009 实操未装三要素）。本轮不修改。

* **D8 spec\_registry 编号冲突**：用户已明确「仅记录不修改」，维持现状。

## 4. 假设与决策 (Assumptions & Decisions)

1. **真源优先原则**：D1/D2/D5/D6 均以代码实现（`auto_pm/**`）为真源，文档向实现对齐，**不改任何** **`.py`** **逻辑**（D5 仅改注释字符串）。
2. **修复范围**：仅 D1-D6（P0/P1），D7/D8 仅记录。不新增代码、不重构、不做「契约校验器」这类新功能（可列为后续独立 CHG，不在本计划内）。
3. **D4 不改沙箱配置**：沙箱 audit.log 写限制属环境层面，超出本计划范围，仅固化「判定准则」文档。
4. **门禁口径**：明确「改动文件全绿」为交付标准，「全量仓库全绿」为理想目标，二者差异须在 handoff\_result 如实标注。

## 5. 验证步骤 (Verification)

> 本计划仅改文档，无需运行 pytest/mypy/ruff；验证以「文档口径与代码真源一致」为门禁。

1. **D1 阈值一致性**：肉眼核对 [pm\_session\_guide.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/pm-workflow/refs/pm_session_guide.md) 写出的 `150/300 行` 与 [pm\_session\_service.py](file:///c:/Users/fubai/Documents/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/pm_session_service.py#L32-L33) `MAX_FILE_LINES=300`、[checker.py](file:///c:/Users/fubai/Documents/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/checker.py#L498-L519) 一致。
2. **D2 状态机一致性**：[process\_gates.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/pm-workflow/refs/process_gates.md) 写出的 12 态与 [constants.py STATUS\_FLOW](file:///c:/Users/fubai/Documents/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/change/constants.py#L119-L132) 完全一致。
3. **D6 编号格式**：[handoff\_schema.md](file:///c:/Users/fubai/Documents/My_Workspace/.trae/skills/pm-workflow/refs/handoff_schema.md) 示例编号匹配 `^CHG-[A-Z]+-\d{4}-\d{3}$` 正则。
4. **D5 无逻辑变更**：`git diff path_resolver.py` 确认仅注释/docstring 变更，无 `_CHANGE_SEARCH_PATHS` 逻辑改动。

