# Checklist

## 阶段 0：测试环境准备

- [x] 工作空间虚拟环境已激活（`.venv\Scripts\Activate.ps1`）
- [x] pytest 已安装且可调用（9.1.0）
- [x] pytest-qt 已安装且可调用（4.5.0）
- [x] pytest-cov 已安装且可调用（7.1.0）
- [x] pytest-benchmark 已安装且可调用（5.2.3）
- [x] PySide6 已安装且可调用（6.11.1）
- [x] auto-pm 命令可调用（`auto-pm --version` 输出 0.1.0）

## 阶段 1：现有测试基线

- [x] `tests/` 下所有现有测试已执行
- [x] 通过/失败/错误用例数已记录（275 passed, 0 failed）
- [x] 失败用例清单已记录（无失败用例）
- [x] 覆盖率报告已生成（71%）

## 阶段 2：L1 单元测试

### CLI project 子命令组（CLI-PROJ-001 至 039）

- [x] CLI-PROJ-001 `project list` 空工作空间
- [x] CLI-PROJ-002 `project list` 含1个项目
- [x] CLI-PROJ-003 至 007 `project list --business-line` 各业务线筛选
- [x] CLI-PROJ-008 至 010 `project list --stack` 各技术栈筛选
- [ ] CLI-PROJ-011 `project list` 无效业务线（未单独测试）
- [x] CLI-PROJ-012 至 014 `project create` 各技术栈 + dry-run
- [ ] CLI-PROJ-015 `project create` 目标路径已存在（未单独测试）
- [ ] CLI-PROJ-016 `project create` 缺少必填参数（未单独测试）
- [x] CLI-PROJ-017 `project create` 中文项目名
- [x] CLI-PROJ-018 至 020 `project show` 正常/--json/不存在
- [x] CLI-PROJ-021 至 025 `project edit` 各字段更新/无参数/不存在（注：--phase 中文值触发 Bug-6）
- [x] CLI-PROJ-026 至 028 `project delete` --confirm/无 confirm/不存在
- [x] CLI-PROJ-029 至 033 `project retrofit` 各场景
- [x] CLI-PROJ-034 至 039 `project import` 复制/移动/业务线/已存在/不存在/不一致

### CLI plc 子命令组（CLI-PLC-001 至 023）

- [ ] CLI-PLC-001 至 003 `plc init` 正常/已存在/缺参数（未单独测试 init）
- [x] CLI-PLC-004 至 006 `plc check` 正常/--json/--all
- [ ] CLI-PLC-007 `plc check --all` 空工作空间（未单独测试）
- [x] CLI-PLC-008 至 009 `plc check` 不存在/无参数无 --all
- [x] CLI-PLC-010 至 013 `plc check` 缺失各类标志文件
- [x] CLI-PLC-014 至 019 `plc repair` 各场景
- [x] CLI-PLC-020 至 023 `plc standardize` 各场景

### CLI python 子命令组（CLI-PY-001 至 003）

- [x] CLI-PY-001 `python init` 占位提示
- [x] CLI-PY-002 `python check` 占位提示
- [ ] CLI-PY-003 `python init` 缺 --name（未单独测试）

### CLI change 子命令组（CLI-CHG-001 至 030）

- [x] CLI-CHG-001 `change create` 全参数
- [ ] CLI-CHG-002 至 008 `change create` 缺各必填参数（Service 层已测，CLI 层未单独测试）
- [ ] CLI-CHG-009 至 011 `change create` 无效 domain/nature/scope（Service 层已测）
- [ ] CLI-CHG-012 `change create` 多个 --scope（未单独测试）
- [ ] CLI-CHG-013 至 015 `change create` --urgency/--planned-date/--references（未单独测试）
- [x] CLI-CHG-016 `change create` 项目不存在
- [x] CLI-CHG-017 至 018 `change list` 有/无变更单
- [ ] CLI-CHG-019 至 020 `change list` --status/--domain 筛选（未单独测试）
- [x] CLI-CHG-021 至 022 `change show` 正常/不存在
- [x] CLI-CHG-023 至 026 `change transition` 各状态流转
- [x] CLI-CHG-027 `change transition` 非法流转
- [x] CLI-CHG-028 至 030 `change transition` 不存在/无效状态/--comment

### CLI template 子命令组（CLI-TPL-001 至 006）

- [x] CLI-TPL-001 `template list` 正常
- [ ] CLI-TPL-002 `template list` 空模板目录（未单独测试）
- [x] CLI-TPL-003 至 004 `template update` 正常/--overwrite
- [x] CLI-TPL-005 `template update` 无 .copier-answers.yml
- [x] CLI-TPL-006 `template update` 不存在

### CLI gui 命令（CLI-GUI-001 至 004）

- [x] CLI-GUI-001 `gui --help`
- [ ] CLI-GUI-002 `gui --debug` 启动（未测试，避免阻塞）
- [ ] CLI-GUI-003 `gui` PySide6 缺失（未测试）
- [ ] CLI-GUI-004 `python main.py` 启动（未测试）

### CLI 全局选项（CLI-GLOBAL-001 至 006）

- [x] CLI-GLOBAL-001 `-w <workspace>`
- [x] CLI-GLOBAL-002 `--version`
- [x] CLI-GLOBAL-003 `--help`
- [x] CLI-GLOBAL-004 `AUTO_PM_WORKSPACE` 环境变量
- [ ] CLI-GLOBAL-005 `-w` 放在子命令后（未单独测试）
- [ ] CLI-GLOBAL-006 无 `-w` 使用当前目录（未单独测试）

### Core Service（SVC-PROJ/TPL/CHG/PLC）

- [x] SVC-PROJ-001 至 042 ProjectService 全部用例
- [x] SVC-TPL-001 至 008 TemplateService 全部用例
- [x] SVC-CHG-001 至 023 ChangeService 全部用例
- [x] SVC-PLC-001 至 016 PlcChecker/PlcRepairer 全部用例

### DB 层（DB-CONN/REPO/CHG/SCAN/SYNC）

- [x] DB-CONN-001 至 005 DatabaseManager 全部用例
- [x] DB-REPO-001 至 011 ProjectRepository 全部用例
- [x] DB-CHG-001 至 003 ChangeRequestRepository 全部用例
- [x] DB-SCAN-001 至 002 ScanLogRepository 全部用例
- [x] DB-SYNC-001 至 008 SyncService 全部用例

### Models（MDL-001 至 017）

- [x] MDL-001 至 017 Project/ChangeRequest/ChangeSummary/business_line 全部用例

### Config/Logging/Utils

- [x] CFG-001 至 002 AutoPmConfig 全部用例
- [x] LOG-001 至 002 setup_logger 全部用例
- [x] UTL-001 至 002 file_utils 全部用例

## 阶段 3：L2 GUI 测试

### MainWindow（GUI-MW-001 至 035）

- [x] GUI-MW-001 至 007 实例化/尺寸/侧边栏/工具栏/状态栏/菜单栏/默认角色（冒烟通过）
- [ ] GUI-MW-008 至 010 切换角色至 PLC/Python/规范编辑（交互测试缺失）
- [ ] GUI-MW-011 至 015 导航至项目列表/规范中心/模板管理/报告中心/系统设置（交互测试缺失）
- [ ] GUI-MW-016 至 017 搜索框/业务线下拉（交互测试缺失）
- [ ] GUI-MW-018 至 022 新建/导入/同步缓存/刷新按钮（交互测试缺失）
- [ ] GUI-MW-023 至 026 卡片点击/返回/编辑/删除信号（交互测试缺失）
- [ ] GUI-MW-027 showEvent 自动加载（交互测试缺失）
- [ ] GUI-MW-028 DB 初始化失败回退（交互测试缺失）
- [ ] GUI-MW-029 至 030 _load_projects 缓存优先/空回退（交互测试缺失）
- [ ] GUI-MW-031 _update_statusbar（交互测试缺失）
- [ ] GUI-MW-032 工作空间默认值（UI-002 回归）- ⚠️ 部分修复
- [x] GUI-MW-033 状态栏 DB 文案（UI-004 回归）- ✅ 已修复
- [ ] GUI-MW-034 至 035 状态栏工作空间路径/扫描时间（UI-004 回归）- ⚠️ 部分修复

### ProjectListView（GUI-PLV-001 至 027）

- [x] GUI-PLV-001 至 004 实例化/set_projects/get_project（冒烟通过）
- [x] GUI-PLV-005 至 008 set_search_text 各场景（冒烟通过）
- [ ] GUI-PLV-009 至 013 set_business_line/筛选/组合筛选（交互测试缺失）
- [ ] GUI-PLV-014 至 016 set_loading/set_error/空状态（交互测试缺失）
- [ ] GUI-PLV-017 至 019 卡片点击/右键编辑/右键删除信号（交互测试缺失）
- [ ] GUI-PLV-020 至 023 统计栏更新（交互测试缺失）
- [ ] GUI-PLV-024 至 026 响应式列数/resizeEvent（交互测试缺失）
- [x] GUI-PLV-027 搜索框布局（UI-001 回归）- ✅ 已修复

### ProjectWorkspaceView（GUI-WS-001 至 015）

- [x] GUI-WS-001 实例化（冒烟通过）
- [x] GUI-WS-002 至 007 load_project 更新标题/ID/技术栈徽标/阶段徽标/返回按钮/编辑按钮（冒烟通过）
- [ ] GUI-WS-008 至 009 删除按钮/apply_role（交互测试缺失）
- [ ] GUI-WS-010 至 013 apply_role 各角色（交互测试缺失）
- [ ] GUI-WS-014 占位页面文案（交互测试缺失）
- [x] GUI-WS-015 占位页面风格一致性（UI-003 回归）- ✅ 已修复

### GlobalView（GUI-GV-001 至 010）

- [x] GUI-GV-001 实例化（冒烟通过）
- [ ] GUI-GV-002 至 005 show_tab 各 Tab（交互测试缺失）
- [ ] GUI-GV-006 show_tab 强制可见（交互测试缺失）
- [ ] GUI-GV-007 至 009 apply_role 各角色（交互测试缺失）
- [ ] GUI-GV-010 占位页面版本提示（交互测试缺失）

### OverviewTab（GUI-OV-001 至 004）

- [x] GUI-OV-001 实例化（冒烟通过）
- [x] GUI-OV-002 至 003 load_project 正常/真实项目（冒烟通过）
- [ ] GUI-OV-004 load_project 异常处理（交互测试缺失）

### Widgets

- [x] GUI-PC-001 至 011 ProjectCard 全部用例（冒烟通过）
- [x] GUI-SB-001 至 006 StatsBar 全部用例（含 UI-002 回归，冒烟通过）
- [x] GUI-FB-001 至 008 FilterBar 全部用例（冒烟通过）

### Dialogs

- [x] GUI-DLG-NEW-001 至 011 NewProjectDialog（冒烟通过）
- [x] GUI-DLG-EDIT-001 至 008 EditProjectDialog（冒烟通过）
- [x] GUI-DLG-DEL-001 至 007 DeleteProjectDialog（冒烟通过）
- [x] GUI-DLG-IMP-001 至 011 ImportProjectDialog（冒烟通过）

### 角色适配集成（GUI-ROLE-001 至 009）

- [x] GUI-ROLE-001 至 004 各角色工作区 Tab（源码审查通过）
- [x] GUI-ROLE-005 至 007 各角色全局 Tab（源码审查通过）
- [ ] GUI-ROLE-008 角色切换日志（交互测试缺失）
- [ ] GUI-ROLE-009 角色互斥（交互测试缺失）

## 阶段 4：L3 端到端测试

- [x] E2E-001 PLC 项目完整生命周期（通过 SIDE-CLI-004 至 020 验证）
- [x] E2E-002 Python 项目完整生命周期（占位命令验证）
- [x] E2E-003 项目导入工作流（基线测试通过）
- [x] E2E-004 变更管理完整流程（SIDE-CLI + 基线测试）
- [x] E2E-005 DB 缓存同步工作流（基线测试通过）
- [x] E2E-006 GUI 完整工作流（冒烟测试通过，交互测试缺失）
- [x] E2E-SRC-001 至 005 三源数据一致性（基线测试通过）
- [x] E2E-ROLE-001 至 004 多角色工作流（源码审查通过）

## 阶段 5：L4 侧自动测试

### CLI 侧自动测试（SIDE-CLI-001 至 023）

- [x] SIDE-CLI-001 `auto-pm --version`
- [x] SIDE-CLI-002 `auto-pm --help`
- [x] SIDE-CLI-003 `project list` 空列表
- [x] SIDE-CLI-004 `project create --stack plc`
- [x] SIDE-CLI-005 `project list` 含新项目
- [x] SIDE-CLI-006 `project show`
- [x] SIDE-CLI-007 `project show --json`
- [x] SIDE-CLI-008 `project edit --phase developing`（注：中文值触发 Bug-6）
- [x] SIDE-CLI-009 `project list --business-line`
- [x] SIDE-CLI-010 `project list --stack`
- [x] SIDE-CLI-011 `plc check`
- [x] SIDE-CLI-012 `plc check --all`
- [x] SIDE-CLI-013 `plc repair --dry-run`
- [x] SIDE-CLI-014 `plc standardize`
- [x] SIDE-CLI-015 `change create`
- [x] SIDE-CLI-016 `change list`
- [x] SIDE-CLI-017 `change show`
- [x] SIDE-CLI-018 `change transition`
- [x] SIDE-CLI-019 `template list`
- [x] SIDE-CLI-020 `project delete --confirm`
- [x] SIDE-CLI-021 `project list` 空列表
- [x] SIDE-CLI-022 `python init` 占位
- [x] SIDE-CLI-023 `python check` 占位

### CLI 异常场景（SIDE-CLI-ERR-001 至 007）

- [x] SIDE-CLI-ERR-001 `project show NOT-EXIST`
- [x] SIDE-CLI-ERR-002 `project delete NOT-EXIST`
- [ ] SIDE-CLI-ERR-003 重复创建（未测试）
- [x] SIDE-CLI-ERR-004 `plc check NOT-EXIST`
- [x] SIDE-CLI-ERR-005 `change transition CHG-XXX`
- [ ] SIDE-CLI-ERR-006 无 -w（未单独测试）
- [ ] SIDE-CLI-ERR-007 `-w /not/exist`（未测试）

### GUI 侧自动测试（SIDE-GUI-001 至 064）

- [x] SIDE-GUI-001 至 006 启动验证（冒烟通过，截图跳过）
- [x] SIDE-GUI-007 至 013 侧边栏导航验证（源码审查通过）
- [x] SIDE-GUI-014 至 019 工具栏验证（源码审查通过）
- [x] SIDE-GUI-020 至 030 项目列表页验证（冒烟通过，截图跳过）
- [x] SIDE-GUI-031 至 037 项目工作区验证（冒烟通过，截图跳过）
- [x] SIDE-GUI-038 至 046 对话框验证（冒烟通过，截图跳过）
- [x] SIDE-GUI-047 至 052 角色切换验证（源码审查通过）
- [x] SIDE-GUI-053 至 057 状态栏验证（源码审查通过，UI-004 部分修复）
- [x] SIDE-GUI-058 UI-001 搜索框布局回归 - ✅ 已修复
- [x] SIDE-GUI-059 至 060 UI-002 统计栏/工作空间默认值回归 - ⚠️ 部分修复
- [x] SIDE-GUI-061 UI-003 占位页面风格回归 - ✅ 已修复
- [x] SIDE-GUI-062 至 064 UI-004 状态栏信息回归 - ⚠️ 部分修复

## 阶段 6：Bug 回归测试

- [x] Bug-1 路径前缀匹配回归测试通过（7 用例）
- [x] Bug-2 变更单同步路径回归测试通过（4 用例）
- [x] Bug-4 retrofit _src_path 推断回归测试通过（5 用例）
- [x] Bug-5 扫描深度统一为 4 回归测试通过（4 用例）
- [x] UI-001 搜索框布局回归验证通过 - ✅ 已修复
- [x] UI-002 统计栏数据 + 工作空间默认值回归验证 - ⚠️ 部分修复
- [x] UI-003 占位页面风格一致性回归验证通过 - ✅ 已修复
- [x] UI-004 状态栏信息完整性回归验证 - ⚠️ 部分修复

## 阶段 7：性能测试（可选）

- [ ] PERF-001 list_projects 10个项目 < 500ms - ⏭️ 跳过
- [ ] PERF-002 list_projects 100个项目 < 3s - ⏭️ 跳过
- [ ] PERF-003 list_projects_cached 100个项目 < 100ms - ⏭️ 跳过
- [ ] PERF-004 sync_to_cache 100个项目 < 5s - ⏭️ 跳过
- [ ] PERF-005 sync_to_cache 增量同步 < 1s - ⏭️ 跳过
- [ ] PERF-006 GUI 启动加载 < 5s - ⏭️ 跳过
- [ ] PERF-007 GUI 搜索响应 < 200ms - ⏭️ 跳过

## 阶段 8：最终检查清单生成

- [x] 所有测试结果已汇总
- [x] 缺陷清单已分类（按严重度）
- [x] `V2.0-测试执行检查清单.md` 已生成到 `09_整改项/` 目录
- [x] 检查清单含测试概览
- [x] 检查清单含分层测试结果
- [x] 检查清单含 Bug 回归测试结果
- [x] 检查清单含 UI 整改项回归测试结果
- [x] 检查清单含性能测试结果（可选，已标注跳过）
- [x] 检查清单含缺陷清单
- [x] 检查清单含需求完成度核对表
- [x] 检查清单含验收标准核对（11.1/11.2）
- [x] 每个检查项含状态（✅通过/❌失败/⚠️部分/⏭️跳过）和说明

## 验收标准核对（来自测试计划 11.1/11.2）

- [x] 所有 P0 测试用例通过（275 基线 + 30 CLI 侧自动）
- [ ] 所有 P1 测试用例通过（GUI 交互测试缺失）
- [ ] 覆盖率 ≥ 85%（当前 71%）
- [x] Bug 回归测试全部通过（Bug-1/2/4/5）
- [ ] UI 整改项回归验证通过（UI-002/004 部分修复）
- [x] 侧自动测试脚本可重复执行
- [ ] CI 流水线集成完成（未集成）
- [ ] 无阻断性 Bug（Bug-6 为阻断性）
- [ ] 无 P0 级别未解决问题（Bug-6 为 P0）
- [x] CLI 所有命令可用（除 edit --phase 中文值场景）
- [ ] GUI 所有功能可交互（仅冒烟测试）
- [x] 三源数据一致性验证通过
- [x] 多角色适配验证通过
