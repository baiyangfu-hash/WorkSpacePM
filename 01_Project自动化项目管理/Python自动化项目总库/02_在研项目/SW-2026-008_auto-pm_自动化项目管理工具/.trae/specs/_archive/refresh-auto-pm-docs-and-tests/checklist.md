# Checklist

## 诊断报告验证
- [x] Claude-result V3 诊断报告 12 项残留问题均已 Grep/Read 实测验证，每项标注实测状态（8 存在 + 4 失真）
- [x] `09_整改项/diagnostic_report.md` 已产出，每项含 Grep/Read 实测证据（文件:行号 + 实际代码片段）
- [x] mypy auto_pm/ 实测运行，实际 5 errors in 2 files（全 unreachable，原报告声明 24 严重失真）

## 设计文档更新
- [x] `02_设计/001_产品需求文档_PRD.md` frontmatter version=V3.1.0，status=已实现，含"当前实现状态基线"章节
- [x] `02_设计/002_接口文档_INT.md` frontmatter version=V3.1.0，DTO/Command/Event 契约与 `auto_pm/ui/contracts/` 实际代码一致（发现 19 个新 DTO + ChangeRequestDTO 主键改名 + 13 Protocol）
- [x] `02_设计/003_详细设计说明书_DSN.md` frontmatter version=V3.1.0，5 层架构目录名与实际代码一致，Bridge 拆分标注已完成
- [x] `02_设计/004_技术方案文档_TEC.md` frontmatter version=V3.1.0，技术决策标注落地状态
- [x] `02_设计/005_里程碑与实施计划.md` frontmatter version=V3.1.0，M0-M4 标注实际完成度（基于代码核查）

## 测试计划
- [x] `09_整改项/CLI测试计划.md` 覆盖 10 个 CLI 子命令组（project/change/spec/template/plc/python/doc/pm-session/vartable/gui，实测较计划 9 个多 1 个 python 组）
- [x] `09_整改项/CLI测试计划.md` 标注冒烟/单元/集成测试执行命令与预期耗时（153 用例）
- [x] `09_整改项/GUI测试计划.md` 覆盖 8 个 QML 页面（驾驶舱/项目工作台/变更中心/规范中心/报告/模板/设置 + BarRow 组件）
- [x] `09_整改项/GUI测试计划.md` 每页面标注 idle/loading/success/empty/warning/error 6 状态覆盖
- [x] `09_整改项/GUI测试计划.md` 明确"默认可见模式"约束（GUI_VISIBLE=1，非 CI 不用 offscreen）

## 整改项归档整理
- [x] `09_整改项/` 根目录仅保留 4 个活跃文件（README.md + diagnostic_report.md + CLI测试计划.md + GUI测试计划.md）
- [x] `09_整改项/archive/` 含已归档的 remediation_plan.md + Claude-result_V0.9.1_原始报告.md + 4 个 Landing Plan（在 archive/landing_plans/）
- [x] `09_整改项/README.md` 索引"活跃文件"与根目录实际文件一一对应（4 个）
- [x] `09_整改项/README.md` 索引"归档文件"与 archive/ 实际文件一一对应

## 约束遵守
- [x] 未修改任何 .py 代码文件（纯文档任务，5 个子代理均确认）
- [x] 新增文档文件名无版本号后缀（版本在 frontmatter 标识，符合项目命名规范）
- [x] 设计文档"实现状态基线"章节基于代码核查，非仅凭声明标记完成（遵循里程碑核查规则）
- [x] GUI 测试计划遵循"默认可见模式"约束（符合 project_memory 强制规则）
