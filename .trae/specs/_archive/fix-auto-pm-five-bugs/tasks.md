# Tasks

## Bug-1: 修复 `_get_project_path` 路径假设错误

- [x] Task 1: 修复 `auto_pm/change/change_service.py` 的 `_get_project_path` 方法
  - [x] SubTask 1.1: 读取 `change_service.py:300-305` 理解原实现（假设目录名=project_id）
  - [x] SubTask 1.2: 修改为优先按 `{project_id}_` 前缀匹配，保留精确匹配向后兼容
  - [x] SubTask 1.3: 编写回归测试 `tests/test_bug1_get_project_path.py`（11 个测试用例）
  - [x] SubTask 1.4: 验证测试通过

## Bug-2: 修复 `_sync_changes` 路径错误

- [x] Task 2: 修复 `auto_pm/db/sync.py` 的 `_sync_changes` 和 `_find_change_file` 方法
  - [x] SubTask 2.1: 读取 `sync.py:192` 理解原实现（在 `04_变更管理` 查找）
  - [x] SubTask 2.2: 修正 `change_dir` 路径为 `00_项目管理/04_变更管理/01_变更单`
  - [x] SubTask 2.3: 修改 `_find_change_file` 搜索 `CHG-{domain}/` 子目录
  - [x] SubTask 2.4: 更新 `tests/db/test_sync.py` 的 TestFindChangeFile 以匹配新目录结构
  - [x] SubTask 2.5: 编写回归测试 `tests/test_bug2_sync_changes.py`（6 个测试用例）
  - [x] SubTask 2.6: 验证测试通过

## Bug-3: 修复 GUI 变更单弹窗枚举不匹配

- [x] Task 3: 修复 `auto_pm/gui/static/index.html` 的变更单弹窗枚举值
  - [x] SubTask 3.1: 读取 `index.html:152-178` 理解原实现（domain 含 INTF、nature 含 FIX、scope 不匹配）
  - [x] SubTask 3.2: 读取 `auto_pm/change/models.py` 确认 DOMAINS/BUSINESS_NATURES/IMPACT_SCOPES 常量值
  - [x] SubTask 3.3: 更新 `chgDomain` 的 option 值为 ELEC/MECH/PLC/HMI/SCPT/DOCU/SAFE
  - [x] SubTask 3.4: 更新 `chgNature` 的 option 值为 REQ/DEF/OPT/CFG/EMRG
  - [x] SubTask 3.5: 更新 `chgScope` 的 option 值为 LOCAL/MODULE/SYSTEM/CROSS/SAFE
  - [x] SubTask 3.6: 编写回归测试 `tests/test_bug3_gui_enum.py`（9 个测试用例）
  - [x] SubTask 3.7: 验证测试通过

## Bug-4: 修复 `retrofit` 命令 `_src_path` 推断错误

- [x] Task 4: 修复 `auto_pm/cli/project.py` 的 `cmd_retrofit` 命令
  - [x] SubTask 4.1: 读取 `project.py:242` 理解原实现（python 写入 `templates/python-standard`）
  - [x] SubTask 4.2: 读取 `auto_pm/gui/api.py` 确认 STACK_TEMPLATE_MAP = {"plc": "plc-standard", "python": "python-tool"}
  - [x] SubTask 4.3: 修改 `cmd_retrofit` 使用 `template_map = {"plc": "plc-standard", "python": "python-tool"}`
  - [x] SubTask 4.4: 编写回归测试 `tests/test_bug4_retrofit_src_path.py`（4 个测试用例）
  - [x] SubTask 4.5: 验证测试通过

## Bug-5: 扫描深度不一致（描述与代码不符）

- [x] Task 5: 处理扫描深度不一致问题
  - [x] SubTask 5.1: 读取 `auto_pm/core/project_service.py` 确认 `list_projects` 默认 scan_depth
  - [x] SubTask 5.2: 读取 `auto_pm/plc/checker.py` 确认 `check_workspace` 默认 scan_depth
  - [x] SubTask 5.3: 确认 008 中不存在 ProjectOverviewService 类（005 的该类已迁移为 ProjectService）
  - [x] SubTask 5.4: 报告 Bug 描述与实际代码不符（任务描述称 depth=1，实际已是 depth=4）
  - [x] SubTask 5.5: 编写回归测试 `tests/test_bug5_scan_depth.py`（6 个测试用例）锁定 depth=4 行为
  - [x] SubTask 5.6: 验证测试通过

## 验证

- [x] Task 6: 运行全部回归测试验证
  - [x] SubTask 6.1: 运行 5 个新测试文件（36 个测试通过）
  - [x] SubTask 6.2: 运行受影响的现有测试（80 个测试通过）
  - [x] SubTask 6.3: 运行 ruff 检查（5 个新测试文件全部通过，无新增错误）
  - [x] SubTask 6.4: 运行 mypy 检查（26 个错误均为预先存在，非本次修改引入）

# Task Dependencies

- [Task 2] depends on [Task 1] — `_sync_changes` 调用 `change_service.list_change_requests`，后者使用 `_get_project_path` ✅
- [Task 1, 3, 4, 5] 相互独立，可并行 ✅
- [Task 6] depends on [Task 1, 2, 3, 4, 5] — 验证需所有修复完成 ✅
