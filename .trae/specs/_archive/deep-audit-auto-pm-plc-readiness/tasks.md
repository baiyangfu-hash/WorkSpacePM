# Tasks — auto-pm PLC 落地就绪度修复

> 基于深度审查 spec.md，按 P0→P1→P2 顺序修复，确保 auto-pm 能正常管理三个参考 PLC 项目。
> 原则：每个任务可独立验证，P0 必须先做，P1 可并行，P2 最后同步。

---

## P0 阻断性问题修复（必须先做）

- [ ] Task P0-1: 支持 LSP-907§3.1 嵌套 .plc.json 布局
  - [ ] SubTask P0-1.1: 修改 `auto_pm/core/project_service.py` `_read_plc_json`，优先读 `02_PLC程序/通用ST程序及变量表/.plc.json`，回退根目录
  - [ ] SubTask P0-1.2: 修改 `auto_pm/plc/checker.py` `_check_plc_json`，同步嵌套布局优先级
  - [ ] SubTask P0-1.3: 编写测试覆盖 DJ-2026-005 双 .plc.json 场景（验证读取 V6.0.0 而非 V1.0.0）

- [ ] Task P0-2: 新增 library 项目类型，修复 SysLib 误判
  - [ ] SubTask P0-2.1: 修改 `auto_pm/plc/checker.py` `_detect_project_type`，新增 `library` 类型判定（基于 .plc.json name 字段或目录特征）
  - [ ] SubTask P0-2.2: 修改 `auto_pm/plc/models.py`，新增 `LIBRARY_SKIP_DIRS` 常量，库项目跳过 STD_DIRS 检查
  - [ ] SubTask P0-2.3: 修改 `auto_pm/plc/repairer.py`，库项目跳过 STD_DIRS 创建
  - [ ] SubTask P0-2.4: 编写测试覆盖 SysLib 库项目检查场景（验证 0 项 FAIL）

- [ ] Task P0-3: SysLib FB 子目录递归扫描
  - [ ] SubTask P0-3.1: 修改 `auto_pm/plc/checker.py` `_scan_and_check`，对 `library` 类型项目递归扫描 FB_* 子目录
  - [ ] SubTask P0-3.2: 编写测试覆盖 SysLib 12 个 FB 子目录扫描场景

- [ ] Task P0-4: 统一变更管理路径常量，修复 Bug-2 不完整
  - [ ] SubTask P0-4.1: 在 `auto_pm/change/path_resolver.py` 定义单一真源 `_CHANGE_SEARCH_PATHS`（含 PLC + Python 双路径）
  - [ ] SubTask P0-4.2: 修改 `auto_pm/change/change_service.py` `_CHANGE_FILE_SEARCH_PATHS` 改为 import 引用
  - [ ] SubTask P0-4.3: 修改 `auto_pm/db/sync.py` `_sync_changes` 改为 import 引用，覆盖 PLC + Python 双路径
  - [ ] SubTask P0-4.4: 编写测试覆盖 PLC + Python 项目变更单同步场景

- [ ] Task P0-5: 统一 ChangeService 与 ProjectService 工作空间路径处理
  - [ ] SubTask P0-5.1: 修改 `auto_pm/change/change_service.py` `_get_project_path`，改为复用 `ProjectService.find_project_path`（递归扫描）
  - [ ] SubTask P0-5.2: 修改 `auto_pm/change/change_service.py` `_find_change_file`，同步递归扫描逻辑
  - [ ] SubTask P0-5.3: 编写测试覆盖跨层级变更单管理场景（workspace_root=My_Workspace，操作 DJ-2026-005）

---

## P1 重要问题修复（可并行）

- [ ] Task P1-1: STD_DIRS 支持 00_项目管理/04_变更管理 布局
  - [ ] SubTask P1-1.1: 修改 `auto_pm/plc/models.py` `STD_DIRS`，将 `04_变更管理` 改为支持 `00_项目管理/04_变更管理` 或根级 `04_变更管理` 两种布局
  - [ ] SubTask P1-1.2: 修改 `auto_pm/plc/checker.py` `_check_std_dirs`，按任一布局存在即 pass
  - [ ] SubTask P1-1.3: 编写测试覆盖 DJ-2026-005 变更管理布局场景

- [ ] Task P1-2: 新增 minimal 项目类型，修复 DJ-2026-000 误判
  - [ ] SubTask P1-2.1: 修改 `auto_pm/plc/checker.py` `_detect_project_type`，新增 `minimal` 类型判定（基于目录规模或 .plc.json 标志）
  - [ ] SubTask P1-2.2: 修改 `auto_pm/plc/models.py`，新增 `MINIMAL_SKIP_DIRS` 常量
  - [ ] SubTask P1-2.3: 编写测试覆盖 DJ-2026-000 小型项目检查场景

- [ ] Task P1-3: 修复 parser._all_verification_passed 逻辑缺陷
  - [ ] SubTask P1-3.1: 修改 `auto_pm/change/parser.py:313-329`，修正 `total_count` 计数规则（仅计入含状态列的表格行）
  - [ ] SubTask P1-3.2: 编写测试覆盖 §10 验证项解析场景

- [ ] Task P1-4: 修复 change_service 临时文件泄漏
  - [ ] SubTask P1-4.1: 修改 `auto_pm/change/change_service.py:254-272`，改用 `try/finally` 确保 tmp 文件清理
  - [ ] SubTask P1-4.2: 编写测试覆盖异常路径下 tmp 文件清理场景

- [ ] Task P1-5: 修复 checker.py SysLib 路径子串误判
  - [ ] SubTask P1-5.1: 修改 `auto_pm/plc/checker.py:93`，改为 `os.path.basename(project_path)` 精确匹配
  - [ ] SubTask P1-5.2: 编写测试覆盖路径含 SysLib 子串但不属于库项目的场景

- [ ] Task P1-6: 连接 workspace_view.change_updated 信号
  - [ ] SubTask P1-6.1: 修改 `auto_pm/ui/main_window.py` `_build_central`，补充 `self._workspace_view.change_updated.connect(self._on_refresh)`
  - [ ] SubTask P1-6.2: 编写 GUI 测试覆盖工作区变更创建后状态栏刷新场景

- [ ] Task P1-7: 修复 _status_change 硬编码为 0
  - [ ] SubTask P1-7.1: 修改 `auto_pm/ui/main_window.py:469`，调用 `ChangeService.list_all_changes()` 获取实际计数
  - [ ] SubTask P1-7.2: 编写 GUI 测试覆盖状态栏变更数显示场景

---

## P2 文档与测试同步（最后做）

- [ ] Task P2-1: 修正 PM_SESSION 测试数和状态字段
  - [ ] SubTask P2-1.1: 修改 `PM_SESSION_SW-2026-008.md` 测试数 778→688
  - [ ] SubTask P2-1.2: 修正 V2.0.1-A/C 同时出现在 completed 和 next_up 的状态矛盾

- [ ] Task P2-2: 重新生成完整覆盖率报告
  - [ ] SubTask P2-2.1: 运行 `task coverage` 重新生成 `09_整改项/覆盖率报告.txt`，确保包含 change/cli/core/db 全部模块
  - [ ] SubTask P2-2.2: 更新 `09_整改项/V2.0-测试执行检查清单.md` 测试数和覆盖率数据

- [ ] Task P2-3: 文档四件套版本对齐
  - [ ] SubTask P2-3.1: 同步 `002_接口文档_INT.md` 至 V2.0.2
  - [ ] SubTask P2-3.2: 同步 `003_详细设计说明书_DSN.md` 至 V2.0.2
  - [ ] SubTask P2-3.3: 同步 `004_技术方案文档_TEC.md` 至 V2.0.2

- [ ] Task P2-4: 验收测试——三参考项目端到端
  - [ ] SubTask P2-4.1: 对 SysLib 执行 `auto-pm plc check/repair/standardize`，验证 0 误报、0 结构破坏
  - [ ] SubTask P2-4.2: 对 DJ-2026-000 执行 `auto-pm plc check/repair/standardize`，验证 0 误报、0 结构破坏
  - [ ] SubTask P2-4.3: 对 DJ-2026-005 执行 `auto-pm plc check/repair/standardize/change list`，验证读取 V6.0.0 .plc.json、变更单正确列出

---

# Task Dependencies

- **P0 任务**必须先于 P1 完成，P0 内部 P0-1~P0-5 可并行
- **P1 任务**依赖 P0 完成，P1 内部各任务可并行
- **P2 任务**依赖 P0+P1 完成，P2-4 端到端验收依赖所有代码修复完成
- **建议执行顺序**：P0-2/P0-3（SysLib 修复）→ P0-1（DJ-2026-005 修复）→ P0-4/P0-5（变更管理修复）→ P1 并行 → P2 同步
