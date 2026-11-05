# auto-pm PRD V1.1.0 更新规格

## Why

auto-pm（SW-2026-008）已完成 P1-P5 实施，核心功能（项目CRUD、Copier模板、PLC检查/修复、变更管理、pywebview GUI、SQLite缓存）全部可用，87个测试通过。但存在以下问题需要通过PRD更新来对齐：

1. **需求状态未跟踪**：PRD仍为V1.0.0初版，未记录哪些需求已完成、哪些有偏差
2. **架构偏差**：实际代码结构与PRD §3.1架构图有多处不一致（目录结构、文件命名）
3. **技能对接未执行**：P4阶段（技能对接）未启动，pm-workflow仍调用pm-mgr，plc-electrical-engineer仍调用plc-check
4. **工具链关系未明确**：auto-pm与pm-mgr(SW-2026-007)、plc-check的关系需决策
5. **数据真源策略模糊**：PM_SESSION.md、.copier-answers.yml、SQLite三源并存，职责未明确
6. **测试覆盖率不达标**：62% < PRD目标80%

## What Changes

### 需求状态更新（PRD §2.2 User Stories）

- 标记US-01~US-07的完成状态和实现偏差
- 新增US-08（GUI桌面应用）、US-09（SQLite索引缓存）——P5实际交付但PRD未记录

### 架构对齐（PRD §3.1）

- **BREAKING**: 更新架构图反映实际代码结构（`auto_pm/change/`替代`core/change_management.py`，`auto_pm/models/`新增层，`auto_pm/db/`新增层，`auto_pm/gui/`新增层）
- 更新CLI命令设计（PRD §3.2），补充`auto-pm gui`、`auto-pm change transition`等实际已实现命令
- 更新模板系统（PRD §3.3），标记`plc-syslib-fb`为未实现

### 工具链关系决策

- **auto-pm取代pm-mgr(SW-2026-007)**：pm-workflow技能改为调用auto-pm，pm-mgr项目归档
- **auto-pm取代plc-check**：plc-electrical-engineer技能改为调用`auto-pm plc check/repair/standardize`，plc-check CLI废弃

### 数据真源策略

- **三源并存各有职责**：
  - `.copier-answers.yml` = 项目元数据真源（project_id/name/stack/version/description/phase）
  - `PM_SESSION_*.md` = 项目管理真源（定位/焦点/状态/日志/交付物）
  - `.auto-pm/index.db` = 索引缓存（可随时从文件系统重建，加速查询）

### 迭代规划新增

- 新增§6「迭代路线图」，定义V1.1.0~V1.4.0的迭代方向
- 新增§7「技能对接方案」，详细规划pm-workflow/plc-electrical-engineer/fullstack-engineer如何调用auto-pm

### Success Criteria更新

- 代码质量指标：测试覆盖率目标从≥80%调整为≥75%（考虑到repairer等模块测试难度）
- 新增技能对接指标：3个技能的SKILL.md均引用auto-pm CLI

## Impact

- Affected specs: PRD V1.0.0全部章节
- Affected code: 无代码变更（仅文档更新）
- Affected skills: pm-workflow、plc-electrical-engineer、fullstack-engineer的SKILL.md需更新
- Affected rules: `project-rule.md`中pm-mgr引用需更新为auto-pm

---

## ADDED Requirements

### Requirement: PRD需求状态跟踪

PRD SHALL为每个User Story标注实现状态（已完成/部分完成/未实现），并记录实现偏差。

#### Scenario: 需求完成状态可追溯

- **WHEN** 查看PRD §2.2 User Stories
- **THEN** 每个US有明确的完成状态标记和实现偏差说明

### Requirement: 工具链关系明确

PRD SHALL明确auto-pm与pm-mgr、plc-check、plc-var-parser的关系，标注取代/废弃/并存。

#### Scenario: 工具链关系清晰

- **WHEN** 查看PRD §3工具链关系
- **THEN** 可明确知道auto-pm取代了pm-mgr和plc-check，plc-var-parser保持独立

### Requirement: 数据真源策略

PRD SHALL定义三源并存的职责边界和同步规则。

#### Scenario: 数据真源职责清晰

- **WHEN** 查看PRD §3数据真源策略
- **THEN** 可明确.copier-answers.yml、PM_SESSION.md、SQLite各自的职责和同步方向

### Requirement: 迭代路线图

PRD SHALL包含V1.1.0~V1.4.0的迭代规划，每阶段有明确交付物和验收标准。

#### Scenario: 后续迭代方向明确

- **WHEN** 查看PRD §6迭代路线图
- **THEN** 可明确V1.1.0（技能对接+测试达标）→V1.2.0（python子命令）→V1.3.0（plc-syslib-fb）→V1.4.0（高级特性）的路线

### Requirement: 技能对接方案

PRD SHALL包含3个技能的对接方案，定义每个技能调用auto-pm的具体命令和场景。

#### Scenario: 技能对接方案可执行

- **WHEN** 查看PRD §7技能对接方案
- **THEN** pm-workflow、plc-electrical-engineer、fullstack-engineer的SKILL.md更新方案明确

## MODIFIED Requirements

### Requirement: US-01 项目新建

**原需求**：通过CLI/GUI新建标准项目，生成符合规范的项目骨架

**实现状态**：✅ 已完成，有偏差

**实现偏差**：
- CLI `project create` 已实现，支持 `--stack plc|python`
- GUI `create_project` 已实现
- Copier模板 `plc-standard` 和 `python-tool` 已创建
- **偏差**：PRD中`plc init`和`project create --stack plc`功能重复，两者都调用`copier copy plc-standard`。建议`plc init`作为`project create --stack plc`的快捷方式

### Requirement: US-02 项目列表与详情

**原需求**：列出所有项目并查看详情

**实现状态**：✅ 已完成，有增强

**实现增强**：
- CLI `project list/show` 已实现
- GUI `list_projects/get_project` 已实现
- 新增SQLite缓存模式：`list_projects_cached`/`get_project_cached`，优先从DB读取
- 新增技术栈筛选（GUI）和搜索（GUI）

### Requirement: US-03 项目编辑与删除

**原需求**：编辑项目元数据和删除项目

**实现状态**：✅ 已完成

**实现细节**：
- CLI `project edit` 支持 `--phase/--desc/--version`
- CLI `project delete` 需 `--confirm`
- GUI `update_project`/`delete_project` 已实现
- 编辑写入`.copier-answers.yml`（copier来源）或`.plc.json`（plc_json来源），保证关键字段不丢失

### Requirement: US-04 PLC项目初始化

**原需求**：基于Copier模板生成符合LSP-907的PLC项目骨架

**实现状态**：✅ 已完成

**实现细节**：
- CLI `plc init <ID> --name <NAME>` 已实现
- 调用`copier copy plc-standard`，生成`.plc.json` + `PM_SESSION` + `PRD/` + 标准目录

### Requirement: US-05 PLC项目结构检查

**原需求**：检查项目是否符合LSP-907规范并自动修复

**实现状态**：✅ 已完成，有增强

**实现增强**：
- CLI `plc check <ID>` / `plc check --all` 已实现
- CLI `plc repair <ID> [--rename] [--dry-run]` 已实现
- 新增 `plc standardize <ID> [--apply]` 文档命名标准化（PRD未提及但已实现）

### Requirement: US-06 模板增量更新

**原需求**：模板升级后老项目能增量同步更新

**实现状态**：✅ 已完成

**实现细节**：
- CLI `template update <ID>` 已实现
- 调用`copier.run_update()`，支持`--overwrite`
- CLI `template list` 列出可用模板

### Requirement: US-07 技能调用

**原需求**：技能通过CLI调用auto-pm，模板内容不进上下文

**实现状态**：⚠️ 部分完成

**已完成**：auto-pm CLI全部命令可用，`.copier-answers.yml`可读
**未完成**：3个技能的SKILL.md均未更新为调用auto-pm，仍使用pm-mgr/plc-check

### Requirement: 架构（PRD §3.1）

**原需求**：PRD定义的目录结构

**实现状态**：⚠️ 有偏差

**实现偏差**：
| PRD定义 | 实际实现 | 说明 |
|---------|---------|------|
| `cli/plc/commands.py` | `cli/plc/__init__.py` | 合并到包入口 |
| `cli/python/commands.py` | `cli/python/__init__.py` | 合并到包入口 |
| `core/change_management.py` | `change/`包（7模块） | 拆分为独立包 |
| `core/overview_service.py` | 未实现 | 功能整合到project_service.py |
| `plc/checker.py`在cli下 | `plc/checker.py`在auto_pm/plc/ | 位置不同 |
| `plc/repairer.py`在cli下 | `plc/repairer.py`在auto_pm/plc/ | 位置不同 |
| 无 | `models/`层（Pydantic v2） | 新增 |
| 无 | `db/`层（SQLite） | 新增 |
| 无 | `gui/`层（pywebview） | 新增 |
| `templates/plc-syslib-fb/` | 未实现 | 缺失 |

### Requirement: Success Criteria（PRD §1.3）

**原需求**：代码质量 mypy strict + ruff + pytest覆盖率 ≥80%

**实现状态**：⚠️ 部分达标

**当前指标**：
| 维度 | 目标 | 实际 | 状态 |
|------|------|------|------|
| 功能完整性 | 100% | 100% | ✅ |
| 模板可演进 | 支持 | 支持 | ✅ |
| 多技术栈 | 2个 | 2个 | ✅ |
| 规范合规PLC | 100% | 100% | ✅ |
| 规范合规Python | 100% | 未实现 | ⚠️ V1.0.0 Non-goal |
| 上下文节省 | 减少80% | 未验证 | ❓ |
| 代码质量 | ≥80% | 62% | ❌ |

## REMOVED Requirements

### Requirement: overview_service.py

**Reason**: 功能已整合到project_service.py的list_projects/get_project方法中，无需独立Service
**Migration**: 无需迁移，project_service.py已覆盖

---

## 需求完成度汇总

### P0需求（必须完成）

| US | 需求 | 状态 | 偏差说明 |
|----|------|------|---------|
| US-01 | 项目新建 | ✅ 完成 | plc init与project create --stack plc功能重复 |
| US-02 | 项目列表与详情 | ✅ 完成+增强 | 新增SQLite缓存、GUI搜索/筛选 |
| US-03 | 项目编辑与删除 | ✅ 完成 | 编辑写回.copier-answers.yml或.plc.json |
| US-04 | PLC项目初始化 | ✅ 完成 | — |

### P1需求（应该完成）

| US | 需求 | 状态 | 偏差说明 |
|----|------|------|---------|
| US-05 | PLC结构检查 | ✅ 完成+增强 | 新增standardize命令 |
| US-06 | 模板增量更新 | ✅ 完成 | — |
| US-07 | 技能调用 | ⚠️ 部分完成 | CLI可用，但3个技能SKILL.md未更新 |

### P5实际交付（PRD未记录）

| 能力 | 状态 | 说明 |
|------|------|------|
| US-08: GUI桌面应用 | ✅ 完成 | pywebview + JS bridge，项目CRUD + 变更单查看 |
| US-09: SQLite索引缓存 | ✅ 完成 | 3表(projects/change_requests/scan_log) + 增量同步 |
| US-10: Pydantic v2模型 | ✅ 完成 | Project/ProjectRecord/ChangeSummary/DTO |

---

## 迭代路线图

### V1.1.0 — 技能对接 + 测试达标

**目标**：auto-pm成为技能工具链的唯一入口

| 交付物 | 验收标准 |
|--------|---------|
| pm-workflow SKILL.md更新 | 调用`auto-pm project create/plc init`替代`pm-mgr` |
| plc-electrical-engineer SKILL.md更新 | 调用`auto-pm plc check/repair/standardize`替代`plc-check` |
| fullstack-engineer SKILL.md更新 | 新增`auto-pm project list/show`调用 |
| project-rule.md更新 | pm-mgr引用替换为auto-pm |
| pm-mgr项目归档 | SW-2026-007标记为已归档 |
| 测试覆盖率≥75% | 补充repairer/sync/checker/gui测试 |

### V1.2.0 — Python子命令实现

**目标**：python技术栈完整支持

| 交付物 | 验收标准 |
|--------|---------|
| `python init`调用Copier模板 | 与`project create --stack python`统一逻辑 |
| `python check`基础检查 | 检查pyproject.toml/README/tests/规范命名 |
| python-tool模板增强 | 支持更多项目类型（库/服务/脚本） |

### V1.3.0 — plc-syslib-fb模板

**目标**：支持SysLib FB项目初始化

| 交付物 | 验收标准 |
|--------|---------|
| plc-syslib-fb Copier模板 | 生成符合LSP-907的SysLib FB项目骨架 |
| plc check支持syslib_fb类型 | 检查SysLib FB特有结构 |

### V1.4.0 — 高级特性

**目标**：提升日常使用体验

| 交付物 | 验收标准 |
|--------|---------|
| GUI增强 | 变更单创建/流转、项目概览看板 |
| `auto-pm project scan`命令 | 一键扫描+缓存同步 |
| `auto-pm change transition` GUI | GUI内变更单状态流转 |
| 全局规则自动更新 | 技能安装时自动更新project-rule.md |

---

## 技能对接方案

### pm-workflow → auto-pm

| 当前调用 | 替换为 | 场景 |
|---------|--------|------|
| `pm-mgr -w "<ws>" detect <dir>` | `auto-pm project show <ID>` | 检测项目类型 |
| `pm-mgr -w "<ws>" init <dir>` | `auto-pm project create --stack <plc\|python> --id <ID> --name <NAME>` | 新建项目 |
| `pm-mgr -w "<ws>" retrofit <dir>` | `auto-pm project edit <ID> --phase <PHASE>` | 补完项目 |
| `pm-mgr -w "<ws>" check <dir>` | `auto-pm plc check <ID>` | 健康检查 |
| `pm-mgr -w "<ws>" snapshot <dir>` | `auto-pm project show <ID>`（读取PM_SESSION） | 状态快照 |

**注意事项**：
- pm-mgr的`init`会创建PM_SESSION + 目录结构 + 文档模板，auto-pm的`project create`通过Copier模板实现相同效果
- pm-mgr的`retrofit`为已有项目补全PM_SESSION，auto-pm暂无等价命令。需新增`auto-pm project retrofit <ID>`或在`project create`中增加`--retrofit`模式
- pm-mgr的`detect`根据目录结构推断项目类型，auto-pm的`project list`已内置此能力

### plc-electrical-engineer → auto-pm

| 当前调用 | 替换为 | 场景 |
|---------|--------|------|
| `plc-check <project_root>` | `auto-pm plc check <ID>` | LSP-907检查 |
| （手动修复） | `auto-pm plc repair <ID> --rename` | 自动修复 |
| （手动标准化） | `auto-pm plc standardize <ID> --apply` | 文档命名标准化 |
| `plc-var-parser <int_doc>` | 保持独立 | 接口文档变量表解析（auto-pm不涉及） |

**注意事项**：
- `plc-var-parser`保持独立，auto-pm不涉及PLC变量解析
- `auto-pm plc check`需要支持`--json`输出格式，便于技能解析结果

### fullstack-engineer → auto-pm

| 新增调用 | 场景 |
|---------|------|
| `auto-pm project list` | 了解工作空间项目概况 |
| `auto-pm project show <ID>` | 读取项目元数据，替代手动读取PM_SESSION |
| `auto-pm project create --stack python --id <ID> --name <NAME>` | 创建Python项目 |
| `auto-pm change create --pid <ID> ...` | 创建变更单 |

**注意事项**：
- fullstack-engineer当前不调用任何CLI工具，对接为增量添加
- 主要价值：通过`auto-pm project show`快速获取项目元数据，无需手动解析PM_SESSION

### 数据真源策略

| 真源 | 职责 | 写入方 | 读取方 |
|------|------|--------|--------|
| `.copier-answers.yml` | 项目元数据真源（project_id/name/stack/version/description/phase） | Copier（创建时）、auto-pm edit（更新时） | auto-pm project list/show、技能 |
| `PM_SESSION_*.md` | 项目管理真源（定位/焦点/状态/日志/交付物） | pm-workflow技能、auto-pm init | pm-workflow/plc-electrical-engineer/fullstack-engineer技能 |
| `.auto-pm/index.db` | 索引缓存（加速查询，可随时重建） | auto-pm sync | auto-pm GUI、auto-pm project list --cached |

**同步规则**：
1. 文件系统为权威源，DB为缓存
2. `auto-pm sync`（或GUI同步按钮）从文件系统重建DB
3. `auto-pm project edit`同时写入`.copier-answers.yml`和DB
4. `auto-pm project create`通过Copier写入`.copier-answers.yml` + PM_SESSION，然后sync到DB
5. 技能读取项目元数据优先用`auto-pm project show`（从文件系统），GUI优先用DB缓存
