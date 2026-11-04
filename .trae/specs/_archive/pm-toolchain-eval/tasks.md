# Tasks

## Phase 1: 项目骨架
- [x] Task 1: 创建 `pm_mgr` 项目骨架（参考 specmgr 结构）
  - [x] 创建项目目录 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-007_pm工作流工具链/`
  - [x] 创建 `pyproject.toml`，依赖仅标准库 + `click`
  - [x] 创建 `pm_mgr/cli.py` 主入口，注册 5 个子命令（init/retrofit/check/detect/snapshot）
  - [x] 创建 `pm_mgr/bootstrap.py` 模板渲染+目录生成逻辑（从 .trae/project-bootstrap/ 读取）
  - [x] 创建 `pm_mgr/detect.py` 项目类型多信号检测逻辑（已修复递归搜索）
  - [x] 创建 `pm_mgr/retrofit.py` 旧项目补完逻辑（hooks + handoffs + spec snapshot 注入）
  - [x] 创建 `pm_mgr/snapshot.py` Spec Snapshot 读取 spec_registry.json + 写入 PM_SESSION（已修复缺失段追加）
  - [x] 创建 `pm_mgr/check.py` 健康检查逻辑

## Phase 2: init 命令
- [x] Task 2: 实现 `pm-mgr init` 命令
  - [x] 从 `.trae/project-bootstrap/<type>/` 读取 PM_SESSION 模板并替换占位符
  - [x] 复制 hooks 脚本到 `.github/hooks/`
  - [x] 创建 `.trae/handoffs/` 目录
  - [x] 创建目录结构（software 9 个 / plc 24 个）
  - [x] 生成骨架文件（pyproject.toml / .plc.json / README / 变更台帐 等）
  - [x] 复制文档模板（software 3 个 / plc 6 个）并替换占位符
  - [x] 自动填充 Spec Snapshot 从 spec_registry.json
  - [x] 幂等性：已存在的文件不覆盖（或 `--force` 选项）
  - [x] 验证：用临时 software 和 plc 目录跑通（software: 21个, plc: 38个）

## Phase 3: retrofit 命令
- [x] Task 3: 实现 `pm-mgr retrofit` 命令
  - [x] 自动检测项目类型（调用 detect 模块）
  - [x] 读取 PM_SESSION，检查 lifecycle 字段（archived 则跳过，除非 `--force`）
  - [x] 注入 hooks：复制对应类型的 hooks 脚本到 `.github/hooks/`
  - [x] 创建 `.trae/handoffs/` 目录
  - [x] 补全 Spec Snapshot 区块（仅当 PM_SESSION 中缺失或不完整时）
  - [x] 幂等性：已存在则跳过
  - [x] 验证：对 DJ-2026-000 执行 retrofit --force，确认添加 .github/hooks/ + .trae/handoffs/ + Spec Snapshot 区块

## Phase 4: check + detect + snapshot 命令
- [x] Task 4: 实现所有辅助命令
  - [x] `pm-mgr detect`：输出项目类型（按多信号优先级，已修复递归搜索 pyproject.toml）
  - [x] `pm-mgr check`：检查 PM_SESSION、hooks/、handoffs/、Spec Snapshot 是否完整
  - [x] `pm-mgr check --fix`：自动修复缺失项（调用 retrofit 逻辑）
  - [x] `pm-mgr snapshot`：独立刷新 Spec Snapshot
  - [x] 验证：SysLib→plc, DJ-2026-000→plc, SW-2026-005→software；init后check全部通过；retrofit后check全部通过

## Phase 5: 集成到 pm-workflow 技能
- [x] Task 5: 更新 pm-workflow SKILL.md
  - [x] Step 0 项目类型检测改为 `pm-mgr detect`（替代硬编码的目录名匹配）
  - [x] Step 3G 初始化改为 `pm-mgr init`（替代直接调用 PS 脚本）
  - [x] 新增 Step 3H 旧项目补完流程（调用 `pm-mgr retrofit`）
  - [x] 更新推荐口令（新增 `pm: 补完` 命令）
  - [x] 新增 pm-mgr 工具依赖说明

# Task Dependencies

- Task 2 depends on Task 1
- Task 3 depends on Task 1
- Task 4 depends on Task 1
- Task 5 depends on Task 2, Task 3, Task 4
- Tasks 2, 3, 4 can be done in parallel after Task 1
