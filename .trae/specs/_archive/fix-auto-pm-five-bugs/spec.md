# auto-pm 五项 Bug 修复 Spec

## Why

auto-pm（SW-2026-008）在 P1-P5 实施完成后，经代码审计与回归测试发现 5 个影响功能正确性的 Bug：
1. `ChangeService._get_project_path` 假设目录名等于 project_id，与实际命名约定 `{project_id}_{project_name}` 不符，导致变更单创建/列表功能对正常命名的项目失效
2. `DatabaseSync._sync_changes` 在错误的目录 `04_变更管理` 查找变更单，实际路径为 `00_项目管理/04_变更管理/01_变更单/CHG-{domain}/`，导致 SQLite 缓存中变更记录始终为空
3. GUI 变更单弹窗的 domain/nature/scope 三个 select 枚举值与后端 `change/models.py` 常量不匹配（domain 含非法值 INTF、nature 含非法值 FIX、scope 选项与 IMPACT_SCOPES 完全不匹配），导致创建变更单时校验失败
4. `project retrofit` 命令对 python 项目写入 `_src_path: templates/python-standard`，实际模板名为 `python-tool`，导致后续 `copier run_update` 失败
5. 扫描深度不一致（005 遗留问题）：任务描述称 ProjectOverviewService 扫描 depth=1，需统一为 depth=4

这些 Bug 涉及变更管理、DB 缓存、GUI、模板更新、项目扫描五个核心链路，需逐一修复并补充回归测试以防止回归。

## What Changes

### Bug-1: `_get_project_path` 路径假设错误
- 修改 `auto_pm/change/change_service.py` 的 `_get_project_path` 方法
- 优先按 `{project_id}_` 前缀匹配项目目录（符合 `cmd_create` 的命名约定）
- 保留精确匹配（目录名 == project_id）以向后兼容

### Bug-2: `_sync_changes` 路径错误
- 修改 `auto_pm/db/sync.py` 的 `_sync_changes` 方法
- 修正 `change_dir` 路径为 `00_项目管理/04_变更管理/01_变更单`
- 修改 `_find_change_file` 方法，搜索 `CHG-{domain}/` 子目录下的变更单文件

### Bug-3: GUI 变更单弹窗枚举不匹配
- 修改 `auto_pm/gui/static/index.html` 的变更单弹窗
- `chgDomain` 的 option 值对齐 DOMAINS 常量（ELEC/MECH/PLC/HMI/SCPT/DOCU/SAFE，移除非法的 INTF）
- `chgNature` 的 option 值对齐 BUSINESS_NATURES 常量（REQ/DEF/OPT/CFG/EMRG，移除非法的 FIX）
- `chgScope` 的 option 值对齐 IMPACT_SCOPES 常量（LOCAL/MODULE/SYSTEM/CROSS/SAFE）

### Bug-4: `retrofit` 命令 `_src_path` 推断错误
- 修改 `auto_pm/cli/project.py` 的 `cmd_retrofit` 命令
- 使用与 `cmd_create`/`GuiApi.STACK_TEMPLATE_MAP` 一致的模板映射：`plc → plc-standard, python → python-tool`

### Bug-5: 扫描深度不一致（描述与代码不符）
- **重要发现**：任务描述称 008 中存在 ProjectOverviewService 扫描 depth=1，但实际代码审计确认 008 中不存在该类（005 的该类已迁移为 ProjectService），且 `ProjectService.list_projects` 与 `PlcChecker.check_workspace` 默认均为 `scan_depth=4`
- **处理方式**：按任务要求"如果发现 Bug 描述与实际代码不符，先报告再修复"，未修改源代码，编写回归测试锁定 depth=4 行为

## Impact

- Affected specs: 无前置 spec 依赖（独立 Bug 修复）
- Affected code:
  - `auto_pm/change/change_service.py` — Bug-1 修复
  - `auto_pm/db/sync.py` — Bug-2 修复
  - `auto_pm/gui/static/index.html` — Bug-3 修复
  - `auto_pm/cli/project.py` — Bug-4 修复
  - `tests/test_bug1_get_project_path.py` — Bug-1 回归测试（新增）
  - `tests/test_bug2_sync_changes.py` — Bug-2 回归测试（新增）
  - `tests/test_bug3_gui_enum.py` — Bug-3 回归测试（新增）
  - `tests/test_bug4_retrofit_src_path.py` — Bug-4 回归测试（新增）
  - `tests/test_bug5_scan_depth.py` — Bug-5 回归测试（新增）
  - `tests/db/test_sync.py` — 更新 TestFindChangeFile 以匹配新目录结构

---

## ADDED Requirements

### Requirement: 项目路径前缀匹配

`ChangeService._get_project_path` SHALL 支持项目目录命名约定 `{project_id}_{project_name}`，同时保留精确匹配以向后兼容。

#### Scenario: 前缀匹配正常命名的项目目录
- **WHEN** 调用 `_get_project_path("SW-2026-008")` 且工作空间存在目录 `SW-2026-008_auto-pm_自动化项目管理工具`
- **THEN** 返回该目录的绝对路径

#### Scenario: 精确匹配向后兼容
- **WHEN** 调用 `_get_project_path("SW-2026-008")` 且工作空间存在目录 `SW-2026-008`（无后缀）
- **THEN** 返回该目录的绝对路径

#### Scenario: 不误匹配前缀相似但不同的项目
- **WHEN** 调用 `_get_project_path("SW-2026-008")` 且工作空间存在 `SW-2026-0080_xxx` 但不存在 `SW-2026-008_*`
- **THEN** 返回 None（不误匹配 `SW-2026-0080_`）

### Requirement: 变更单 DB 同步路径正确

`DatabaseSync._sync_changes` SHALL 在正确路径 `00_项目管理/04_变更管理/01_变更单` 查找变更单文件，`_find_change_file` SHALL 搜索 `CHG-{domain}/` 子目录。

#### Scenario: 同步变更单到 DB 缓存
- **WHEN** 项目目录下存在 `00_项目管理/04_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-001.md`
- **THEN** `_sync_changes` 能找到该文件并将变更记录写入 `change_requests` 表
- **AND** DB 中 `change_requests` 表的 `file_path` 列指向真实的 .md 文件路径

#### Scenario: 变更单文件位于 CHG-{domain} 子目录
- **WHEN** 调用 `_find_change_file(change_dir, "CHG-DOCU-2026-001")`
- **THEN** 在 `change_dir/CHG-DOCU/` 子目录下查找以 `CHG-DOCU-2026-001` 开头的 .md 文件

### Requirement: GUI 变更单弹窗枚举值与后端一致

GUI 变更单弹窗的 `chgDomain`/`chgNature`/`chgScope` 三个 select 的 option 值 SHALL 与 `auto_pm/change/models.py` 中的 DOMAINS/BUSINESS_NATURES/IMPACT_SCOPES 常量完全一致。

#### Scenario: domain 选项对齐 DOMAINS 常量
- **WHEN** 解析 `index.html` 中 `<select id="chgDomain">` 的所有 option value
- **THEN** value 集合等于 {ELEC, MECH, PLC, HMI, SCPT, DOCU, SAFE}
- **AND** 不包含非法值 INTF

#### Scenario: nature 选项对齐 BUSINESS_NATURES 常量
- **WHEN** 解析 `index.html` 中 `<select id="chgNature">` 的所有 option value
- **THEN** value 集合等于 {REQ, DEF, OPT, CFG, EMRG}
- **AND** 不包含非法值 FIX

#### Scenario: scope 选项对齐 IMPACT_SCOPES 常量
- **WHEN** 解析 `index.html` 中 `<select id="chgScope">` 的所有 option value
- **THEN** value 集合等于 {LOCAL, MODULE, SYSTEM, CROSS, SAFE}

### Requirement: retrofit 命令模板路径映射正确

`project retrofit` 命令生成的 `.copier-answers.yml` 中 `_src_path` SHALL 使用与 `cmd_create`/`GuiApi.STACK_TEMPLATE_MAP` 一致的模板映射。

#### Scenario: python 项目 retrofit 写入正确模板路径
- **WHEN** 对 stack="python" 的项目执行 `project retrofit`
- **THEN** 生成的 `.copier-answers.yml` 中 `_src_path` 为 `templates/python-tool`
- **AND** 不为 `templates/python-standard`

#### Scenario: plc 项目 retrofit 写入正确模板路径
- **WHEN** 对 stack="plc" 的项目执行 `project retrofit`
- **THEN** 生成的 `.copier-answers.yml` 中 `_src_path` 为 `templates/plc-standard`

#### Scenario: 已存在 .copier-answers.yml 时跳过
- **WHEN** 项目已存在 `.copier-answers.yml` 文件
- **THEN** retrofit 命令跳过写入，不覆盖已有文件

### Requirement: 扫描深度统一为 depth=4

`ProjectService.list_projects` 和 `PlcChecker.check_workspace` 的默认 `scan_depth` SHALL 为 4，确保能发现嵌套较深的项目目录。

#### Scenario: ProjectService.list_projects 默认 scan_depth=4
- **WHEN** 检查 `ProjectService.list_projects` 方法签名
- **THEN** `scan_depth` 参数默认值为 4

#### Scenario: PlcChecker.check_workspace 默认 scan_depth=4
- **WHEN** 检查 `PlcChecker.check_workspace` 方法签名
- **THEN** `scan_depth` 参数默认值为 4

#### Scenario: depth=4 能发现 4 层嵌套项目
- **WHEN** 工作空间存在 4 层嵌套的项目目录（如 `a/b/c/d/SW-2026-008_xxx`）
- **THEN** `list_projects(scan_depth=4)` 能发现该项目

## MODIFIED Requirements

### Requirement: ChangeService 项目路径解析策略

原 `_get_project_path` 仅支持精确匹配（目录名 == project_id）。**修改为**: 优先按 `{project_id}_` 前缀匹配，保留精确匹配作为向后兼容回退。

### Requirement: DatabaseSync 变更单目录发现策略

原 `_sync_changes` 在 `04_变更管理` 查找变更单。**修改为**: 在 `00_项目管理/04_变更管理/01_变更单` 查找，`_find_change_file` 搜索 `CHG-{domain}/` 子目录。

### Requirement: GUI 变更单弹窗枚举值

原 `chgDomain`/`chgNature`/`chgScope` 的 option 值与后端常量不匹配。**修改为**: 三个 select 的 option 值严格对齐 `change/models.py` 的 DOMAINS/BUSINESS_NATURES/IMPACT_SCOPES 常量。

### Requirement: retrofit 命令模板路径推断

原 `cmd_retrofit` 对 python 项目写入 `templates/python-standard`。**修改为**: 使用 `template_map = {"plc": "plc-standard", "python": "python-tool"}` 映射，与 `cmd_create`/`GuiApi.STACK_TEMPLATE_MAP` 一致。

## REMOVED Requirements

无。
