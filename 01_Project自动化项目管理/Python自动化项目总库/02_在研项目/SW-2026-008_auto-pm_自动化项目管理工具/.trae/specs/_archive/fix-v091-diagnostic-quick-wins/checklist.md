# Checklist

## 修复 1：frontmatter_svc.py 补 as e
- [x] `auto_pm/spec/services/frontmatter_svc.py` L91 为 `except Exception as e:`（原 `except Exception:`）
- [x] `auto_pm/spec/services/frontmatter_svc.py` L146 为 `except Exception as e:`（原 `except Exception:`）
- [x] 两处 `log.warning(..., exc_info=True)` 日志保留并补充 `e` 参数（避免 F841 未使用变量）

## 修复 2：_get_project_info 克隆消除
- [x] `auto_pm/application/system_facade.py` `_get_project_info()` 方法体简化为委托 `self._project_service.get_project(project_id)`
- [x] `auto_pm/application/delivery_facade.py` `_get_project_info()` 方法体简化为委托 `self._project_service.get_project(project_id)`
- [x] 原 ~18 行"DB 缓存优先 + 文件系统降级"克隆逻辑已删除
- [x] 测试 mock（test_delivery_facade.py / test_system_facade.py）`_make_project_service()` 补 `get_project` 方法

## 修复 3：FacadeRegistry TypedDict
- [x] `auto_pm/ui/registry.py` 定义 `class ServiceContainer(TypedDict)` 含所有 service key
- [x] `auto_pm/ui/registry.py` `initialize()` 参数类型为 `ServiceContainer`（非 `dict[str, Any]`）
- [x] `auto_pm/ui/registry.py` 无 `cast()` 调用
- [x] 调用方传入的 dict 符合 ServiceContainer 结构
- [x] WorkbenchFacade/SystemFacade 构造函数签名同步调整为 `Protocol | None = None`（匹配工厂返回类型）
- [x] WorkbenchFacade.get_dashboard_snapshot() 补 None 守卫降级

## 修复 4：change/constants.py 重命名
- [x] `auto_pm/change/constants.py` 文件存在（原 `models.py` 已重命名）
- [x] Grep `from auto_pm.change.models import` in auto_pm/ + tests/ 返回 0 处
- [x] Grep `from auto_pm.change.constants import` 返回与原导入方数量一致
- [x] `constants.py` 保留原 `from auto_pm.models import ChangeRequest` re-export
- [x] `change_service.py` import 顺序修正（constants 在 file_locator 之前，ruff I001）

## 修复 5：search_projects 缓存优先
- [x] `auto_pm/core/project_service.py` `search_projects()` 先 `try: self.list_projects_cached()`
- [x] `except RuntimeError:` 降级 `self.list_projects()`

## 修复 6：mypy 死分支清理
- [x] `auto_pm/application/delivery_facade.py` 4 处 `data = {"raw": data}` 死分支已清理（L124/L141/L157/L175）
- [x] `auto_pm/application/delivery_facade.py` 移除未使用的 `import logging` + `log = logging.getLogger(__name__)`
- [x] `auto_pm/ui/qml/models/change_list_model.py` L71 死分支已清理
- [x] 激活 venv 后 `mypy auto_pm/` 返回 0 errors（exit code 0）

## 全量回归验证
- [x] `pytest --no-cov -q` 返回 1260 passed / 2 skipped / 0 failed（基线由 1115 增长至 1260，无退化）
- [x] `ruff check auto_pm/` 返回 0 errors
- [x] `mypy auto_pm/` 返回 0 errors

## 约束遵守
- [x] 未引入新的 `except Exception`（修复 1 仅补 `as e` 绑定 + 使用 `e` 于日志）
- [x] 未修改任何测试用例的断言值（仅允许更新导入路径 + 补 mock 方法）
- [x] 未扩大修复范围至阶段 2/3/4（TODO/Ruff/Config/ProjectInfo/委托方法/pathlib 不在本 spec 范围）
- [x] 所有改动遵循 210 编程规范（命名/风格/类型注解）
