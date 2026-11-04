# auto-pm V0.9.1 诊断残留问题修复（阶段 1 Quick Wins）Spec

## Why

`09_整改项/diagnostic_report.md`（V0.9.1 实测版）对 12 项残留问题逐项实证后，识别出 6 项低风险、高收益的 Quick Wins（阶段 1），涉及代码克隆、类型安全、缓存缺失、命名歧义、死分支清理。这些问题虽非阻断性缺陷，但影响可维护性与类型安全性，且修复工作量小（合计约 2.5 小时）、风险低（均有明确的文件位置与修复方向）。

本 spec 仅覆盖阶段 1 的 6 项 Quick Wins。阶段 2（TODO 评估/Ruff 扩展/Config 扩展/ProjectInfo model_copy 25 处）与阶段 3/4（委托方法清理/pathlib 迁移）属较大重构，需单独评估，不在本 spec 范围。

## What Changes

### 修复 1：frontmatter_svc.py 补 `as e` 绑定（#1）
- `auto_pm/spec/services/frontmatter_svc.py` L89/L140 两处 `except Exception:` 改为 `except Exception as e:`，日志已有 `log.warning(..., exc_info=True)` 无需新增

### 修复 2：消除 `_get_project_info()` 两处克隆（#2）
- `auto_pm/application/system_facade.py` L56-80：`_get_project_info()` 改为直接调 `self._project_service.get_project(project_id)`
- `auto_pm/application/delivery_facade.py` L64-88：同上
- **BREAKING**：无（方法签名与返回值不变，仅内部实现简化）

### 修复 3：`FacadeRegistry.initialize()` 改用 `TypedDict`（#3）
- `auto_pm/ui/registry.py`：`initialize(services: dict[str, Any])` 改为 `initialize(services: ServiceContainer)`，新增 `ServiceContainer(TypedDict)` 定义所有 service key
- 调用方（`app_context.py` 或 equivalent）同步更新：构造 `ServiceContainer` 字典传入
- 移除 `cast()` 调用（TypedDict 直接类型安全）

### 修复 4：重命名 `change/models.py` → `change/constants.py`（#5）
- `auto_pm/change/models.py` → `auto_pm/change/constants.py`
- 更新所有 `from auto_pm.change.models import` 为 `from auto_pm.change.constants import`
- **BREAKING**：导入路径变更（内部模块，无外部 API 影响）

### 修复 5：`search_projects()` 优先走缓存（#11）
- `auto_pm/core/project_service.py` L319-335：`search_projects()` 改为先尝试 `list_projects_cached()`，`RuntimeError` 时降级 `list_projects()`

### 修复 6：mypy 5 处 unreachable 死分支清理（#12）
- `auto_pm/application/delivery_facade.py` L124/L141/L157/L175：清理 `data = {"raw": data}` 死分支
- `auto_pm/ui/qml/models/change_list_model.py` L71：清理同类死分支
- 修复后 `mypy auto_pm/` 应为 0 errors

## Impact
- Affected code:
  - `auto_pm/spec/services/frontmatter_svc.py`（2 处 except）
  - `auto_pm/application/system_facade.py`（_get_project_info 简化）
  - `auto_pm/application/delivery_facade.py`（_get_project_info 简化 + 4 处死分支清理）
  - `auto_pm/ui/registry.py`（TypedDict + 移除 cast）
  - `auto_pm/app_context.py` 或调用方（ServiceContainer 构造）
  - `auto_pm/change/models.py` → `auto_pm/change/constants.py`（重命名 + 导入更新）
  - `auto_pm/core/project_service.py`（search_projects 缓存优先）
  - `auto_pm/ui/qml/models/change_list_model.py`（1 处死分支清理）
  - 所有 `from auto_pm.change.models import` 的导入方（需 Grep 定位）
- Affected tests：现有 1115 passed 须保持不退化；若导入路径变更影响测试，同步更新测试导入
- 不涉及：阶段 2/3/4 的较大重构（TODO 评估/Ruff 扩展/Config/ProjectInfo model_copy/委托方法/pathlib）

## ADDED Requirements

### Requirement: except Exception 绑定异常变量
`frontmatter_svc.py` 的 2 处 `except Exception:` SHALL 绑定异常变量为 `as e`，保留现有 `log.warning(..., exc_info=True)` 日志。

#### Scenario: 异常变量绑定
- **WHEN** Read `auto_pm/spec/services/frontmatter_svc.py` L89/L140
- **THEN** 两处均为 `except Exception as e:`，日志行不变

### Requirement: 消除 _get_project_info 克隆
`system_facade.py` 与 `delivery_facade.py` 的 `_get_project_info()` SHALL 委托 `self._project_service.get_project(project_id)`，不再复制"DB 缓存优先 + 文件系统降级"逻辑。

#### Scenario: 委托 get_project
- **WHEN** Read 两个 Facade 的 `_get_project_info()`
- **THEN** 方法体简化为 `if not self._project_service: return None` + `return self._project_service.get_project(project_id)`，原 ~18 行克隆逻辑删除

### Requirement: FacadeRegistry 类型安全
`FacadeRegistry.initialize()` 参数 SHALL 为 `ServiceContainer`（TypedDict），不再使用 `dict[str, Any]` + `cast()`。

#### Scenario: TypedDict 装配
- **WHEN** Read `auto_pm/ui/registry.py`
- **THEN** 定义 `class ServiceContainer(TypedDict)` 含所有 service key（dashboard_service/project_service/asset_summary_service/change_service/spec_check_service 等），`initialize()` 参数类型为 `ServiceContainer`，无 `cast()` 调用

### Requirement: change/constants.py 命名消除歧义
`auto_pm/change/models.py` SHALL 重命名为 `auto_pm/change/constants.py`，所有导入方同步更新。

#### Scenario: 重命名后导入一致
- **WHEN** Grep `from auto_pm.change.models import` in `auto_pm/` + `tests/`
- **THEN** 0 处命中（全部更新为 `from auto_pm.change.constants import`）

### Requirement: search_projects 缓存优先
`search_projects()` SHALL 优先走 `list_projects_cached()`，`RuntimeError` 时降级 `list_projects()`。

#### Scenario: 缓存优先路径
- **WHEN** Read `auto_pm/core/project_service.py` `search_projects()`
- **THEN** 方法体先 `try: all_projects = self.list_projects_cached()` + `except RuntimeError: all_projects = self.list_projects()`

### Requirement: mypy 0 errors
清理 `delivery_facade.py` 4 处 + `change_list_model.py` 1 处 unreachable 死分支后，`mypy auto_pm/` SHALL 返回 0 errors。

#### Scenario: mypy 通过
- **WHEN** 激活 venv 后运行 `mypy auto_pm/`
- **THEN** exit code 0，无 error 输出

### Requirement: 测试不退化
所有修复完成后，`pytest --no-cov -q` SHALL 保持 1115 passed / 2 skipped（允许新增测试但禁止减少通过数）。

#### Scenario: 全量回归通过
- **WHEN** 激活 venv 后运行 `pytest --no-cov -q`
- **THEN** 1115 passed / 2 skipped，0 failed
