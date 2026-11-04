# Checklist

## Bug-1: `_get_project_path` 路径假设错误

- [x] `auto_pm/change/change_service.py` 的 `_get_project_path` 方法支持 `{project_id}_` 前缀匹配
- [x] `_get_project_path` 保留精确匹配以向后兼容
- [x] `_get_project_path` 不误匹配前缀相似但不同的项目（如 `SW-2026-0080_` 不匹配 `SW-2026-008`）
- [x] `tests/test_bug1_get_project_path.py` 存在且测试通过（11 个测试用例）

## Bug-2: `_sync_changes` 路径错误

- [x] `auto_pm/db/sync.py` 的 `_sync_changes` 中 `change_dir` 路径为 `00_项目管理/04_变更管理/01_变更单`
- [x] `auto_pm/db/sync.py` 的 `_find_change_file` 搜索 `CHG-{domain}/` 子目录
- [x] `tests/db/test_sync.py` 的 TestFindChangeFile 已更新为 CHG-{domain}/ 子目录结构
- [x] `tests/test_bug2_sync_changes.py` 存在且测试通过（6 个测试用例）
- [x] DB 中 `change_requests` 表的 `file_path` 列指向真实的 .md 文件路径

## Bug-3: GUI 变更单弹窗枚举不匹配

- [x] `auto_pm/gui/static/index.html` 的 `chgDomain` option 值为 ELEC/MECH/PLC/HMI/SCPT/DOCU/SAFE（不含 INTF）
- [x] `auto_pm/gui/static/index.html` 的 `chgNature` option 值为 REQ/DEF/OPT/CFG/EMRG（不含 FIX）
- [x] `auto_pm/gui/static/index.html` 的 `chgScope` option 值为 LOCAL/MODULE/SYSTEM/CROSS/SAFE
- [x] `tests/test_bug3_gui_enum.py` 存在且测试通过（9 个测试用例）

## Bug-4: `retrofit` 命令 `_src_path` 推断错误

- [x] `auto_pm/cli/project.py` 的 `cmd_retrofit` 使用 `template_map = {"plc": "plc-standard", "python": "python-tool"}`
- [x] python 项目 retrofit 后 `.copier-answers.yml` 的 `_src_path` 为 `templates/python-tool`
- [x] plc 项目 retrofit 后 `.copier-answers.yml` 的 `_src_path` 为 `templates/plc-standard`
- [x] 已存在 `.copier-answers.yml` 时 retrofit 跳过写入
- [x] `tests/test_bug4_retrofit_src_path.py` 存在且测试通过（4 个测试用例）

## Bug-5: 扫描深度不一致（描述与代码不符）

- [x] 已报告 Bug 描述与实际代码不符（任务描述称 depth=1，实际已是 depth=4）
- [x] `auto_pm/core/project_service.py` 的 `list_projects` 默认 `scan_depth=4`
- [x] `auto_pm/plc/checker.py` 的 `check_workspace` 默认 `scan_depth=4`
- [x] 008 中不存在 ProjectOverviewService 类（已确认 005 的该类迁移为 ProjectService）
- [x] `tests/test_bug5_scan_depth.py` 存在且测试通过（6 个测试用例）

## 整体验证

- [x] 5 个新测试文件全部通过（36 个测试用例）
- [x] 受影响的现有测试全部通过（80 个测试用例）
- [x] ruff 检查无新增错误（5 个新测试文件全部 `All checks passed!`）
- [x] mypy 检查无新增错误（26 个错误均为预先存在）
- [x] 未修改与 Bug 无关的代码
- [x] 代码遵循 210 Python 编程规范
