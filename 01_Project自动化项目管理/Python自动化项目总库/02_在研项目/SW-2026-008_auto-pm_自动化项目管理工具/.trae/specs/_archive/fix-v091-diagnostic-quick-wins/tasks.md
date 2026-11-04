# Tasks

- [x] Task 1: frontmatter_svc.py 补 `as e` 绑定（#1）
  - [x] SubTask 1.1: Read 确认 L91/L146 两处 `except Exception:` 位置
  - [x] SubTask 1.2: Edit L91 `except Exception:` → `except Exception as e:`（log.warning 保留）
  - [x] SubTask 1.3: Edit L146 `except Exception:` → `except Exception as e:`（log.warning 保留）

- [x] Task 2: 消除 `_get_project_info()` 两处克隆（#2）
  - [x] SubTask 2.1: Read `auto_pm/application/system_facade.py` L50-85 确认 `_get_project_info()` 完整实现
  - [x] SubTask 2.2: Read `auto_pm/application/delivery_facade.py` L58-92 确认 `_get_project_info()` 完整实现
  - [x] SubTask 2.3: Read `auto_pm/core/project_service.py` `get_project()` 方法确认逻辑等价（DB 缓存优先 + 文件系统降级）
  - [x] SubTask 2.4: Edit system_facade.py `_get_project_info()` 简化为委托 `self._project_service.get_project(project_id)`
  - [x] SubTask 2.5: Edit delivery_facade.py `_get_project_info()` 同样简化

- [x] Task 3: `FacadeRegistry.initialize()` 改用 `TypedDict`（#3）
  - [x] SubTask 3.1: Read registry.py 确认 initialize() 参数与 cast() 用法
  - [x] SubTask 3.2: Grep 定位调用方（qml_main_window.py + test_facade_registry.py）
  - [x] SubTask 3.3: Read 调用方确认 services dict 构造
  - [x] SubTask 3.4: Edit registry.py 新增 ServiceContainer(TypedDict) + 移除 cast() + import 10 Protocol
  - [x] SubTask 3.5: Edit test_facade_registry.py 补 template_service key（原 .get() 掩盖的缺陷）

- [x] Task 4: 重命名 `change/models.py` → `change/constants.py`（#5）
  - [x] SubTask 4.1: Grep 定位 14 个导入方（6 auto_pm + 8 tests，共 26 处 import）
  - [x] SubTask 4.2: Read models.py 确认内容（常量+异常+校验+re-export）
  - [x] SubTask 4.3: Move-Item 重命名 models.py → constants.py
  - [x] SubTask 4.4: Edit 14 文件 26 处 import 更新为 constants
  - [x] SubTask 4.5: 无 `from auto_pm.change import models` 形式（0 处）
  - [x] SubTask 4.6: constants.py re-export（ChangeRequest/ChangeSummary）保留

- [x] Task 5: `search_projects()` 优先走缓存（#11）
  - [x] SubTask 5.1: Read project_service.py 确认 search_projects() + list_projects_cached() 签名
  - [x] SubTask 5.2: Edit search_projects() 改为 try list_projects_cached() + except RuntimeError 降级

- [x] Task 6: mypy 5 处 unreachable 死分支清理（#12）
  - [x] SubTask 6.1: Read `auto_pm/application/delivery_facade.py` L115-180 确认 4 处 `data = {"raw": data}` 死分支上下文
  - [x] SubTask 6.2: Read `auto_pm/ui/qml/models/change_list_model.py` L65-75 确认 1 处死分支上下文
  - [x] SubTask 6.3: 分析死分支成因（mypy 类型窄化判定不可达），决定删除或修正类型注解
  - [x] SubTask 6.4: Edit delivery_facade.py 清理 4 处死分支
  - [x] SubTask 6.5: Edit change_list_model.py 清理 1 处死分支
  - [x] SubTask 6.6: 激活 venv 运行 `mypy auto_pm/` 确认 0 errors

- [x] Task 7: 全量回归验证
  - [x] SubTask 7.1: 激活 venv 运行 `pytest --no-cov -q` 确认 1260 passed / 2 skipped / 0 failed
  - [x] SubTask 7.2: 运行 `ruff check auto_pm/` 确认 0 errors
  - [x] SubTask 7.3: 运行 `mypy auto_pm/` 确认 0 errors

# Task Dependencies
- Task 1/2/5 互相独立，可并行
- Task 3 独立（TypedDict 改造）
- Task 4 独立（重命名 + 导入更新），但须在全量回归前完成
- Task 6 独立（死分支清理），但 Task 2 修改 delivery_facade.py 须与 Task 6 协调（同文件）
- Task 7 须在所有修复完成后执行（全量验证）
- 建议：Task 2 + Task 6 合并到同一子代理（同修改 delivery_facade.py，避免冲突）
