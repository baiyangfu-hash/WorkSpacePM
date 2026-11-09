# Tasks

- [x] Task 1: 实测验证 Claude-result V3 诊断报告 12 项残留问题并产出综合诊断报告
  - [x] SubTask 1.1: Grep/Read 验证 #1 except Exception（实测 70 处/22 文件，frontmatter_svc.py 2 处有 log.warning 非静默，失真）
  - [x] SubTask 1.2: Grep/Read 验证 #2 _get_project_info() 两处克隆（system_facade.py + delivery_facade.py，存在）
  - [x] SubTask 1.3: Read 验证 #3 FacadeRegistry.initialize() dict[str, Any]（ui/registry.py，存在）
  - [x] SubTask 1.4: Grep 验证 #4 TODO 未闭环（实测 16 处非 7 处，含 substance_checker 字符串字面量误计，失真）
  - [x] SubTask 1.5: Read 验证 #5 change/models.py 与 models/change.py 命名歧义（存在）
  - [x] SubTask 1.6: Grep 验证 #6 ProjectInfo 原地修改属性（实测 25 处非 ~15 处，失真）
  - [x] SubTask 1.7: Read 验证 #7 Ruff 规则集偏保守（.ruff.toml select 子集，存在）
  - [x] SubTask 1.8: Read 验证 #8 AutoPmConfig 配置类功能单薄（config/app_config.py，存在）
  - [x] SubTask 1.9: Grep 验证 #9 os.path vs pathlib 混用（存在）
  - [x] SubTask 1.10: Read 验证 #10 7 个向后兼容委托方法（project_service.py，存在）
  - [x] SubTask 1.11: Read 验证 #11 search_projects() 未走缓存（project_service.py，存在）
  - [x] SubTask 1.12: 运行 mypy auto_pm/ 验证 #12 errors 遗留（实测 5 errors/2 files 非 24/8，全为 unreachable，严重失真）
  - [x] SubTask 1.13: 汇总实测结果，产出 `09_整改项/diagnostic_report.md`（8 存在 + 4 失真）

- [x] Task 2: 更新 02_设计/ 下 5 个设计文档至 V3.1.0
  - [x] SubTask 2.1: 更新 001_PRD.md（V3.1.0 + 已实现 + 实现状态基线 + 6 工作域实现度）
  - [x] SubTask 2.2: 更新 002_INT.md（DTO/Command/Event 对齐实际 contracts/，发现 19 个新 DTO + ChangeRequestDTO 主键 change_id→change_number + 实测 13 Protocol 非 10）
  - [x] SubTask 2.3: 更新 003_DSN.md（架构图对齐实际目录 + Bridge 拆分标注已完成 + 实现进度基线 + 测试设计 1115 passed）
  - [x] SubTask 2.4: 更新 004_TEC.md（技术决策落地状态 + 复用资产表对齐 + 实施策略 4 阶段完成度）
  - [x] SubTask 2.5: 更新 005_里程碑与实施计划.md（M0-M4 标注实际完成度 + M0-M5 实际核查小节）

- [x] Task 3: 制定 CLI 测试计划
  - [x] SubTask 3.1: 创建 `09_整改项/CLI测试计划.md`（实测 10 子命令组矩阵 + 153 用例 + 执行命令 + 现有资产映射）

- [x] Task 4: 制定 GUI 测试计划
  - [x] SubTask 4.1: 创建 `09_整改项/GUI测试计划.md`（8 QML 页面矩阵 + 6 状态覆盖 + 可见模式约束 + 6 交互链路 + 89 用例）

- [x] Task 5: 整理归档 09_整改项/
  - [x] SubTask 5.1: 归档 `remediation_plan.md` → `archive/`
  - [x] SubTask 5.2: 归档 `Claude-result` → `archive/Claude-result_V0.9.1_原始报告.md`（重命名区分）
  - [x] SubTask 5.3: 创建 `archive/landing_plans/` 并归档 4 个 Landing Plan（M2/M3/M4_delivery/M4_spec）
  - [x] SubTask 5.4: 重写 `README.md` 索引（活跃 4 文件 + 归档清单 + 整理规则 + 关键发现摘要）

# Task Dependencies
- Task 1 须先于 Task 2（诊断实测结果 feeds 设计文档"实现状态基线"章节）
- Task 3/4 可与 Task 1/2 并行（测试计划基于 V0.9.1 现状，不依赖诊断结论）
- Task 5 须在 Task 1/3/4 完成后执行（归档依赖诊断报告产出 + 测试计划就位）
