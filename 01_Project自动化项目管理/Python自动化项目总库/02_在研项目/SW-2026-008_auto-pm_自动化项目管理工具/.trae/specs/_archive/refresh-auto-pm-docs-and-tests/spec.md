# auto-pm 项目诊断与文档刷新 Spec

## Why

auto-pm 项目当前代码基线已达 V0.9.1（1115 passed / ruff 0 errors / mypy 24 P1P2 errors），五层架构（CLI→Facade→Service→Repository→Models）、5 个 Facade、5 个 Domain Bridge、10 个 Protocol 契约均已落地，QML 已是唯一 UI 入口。但存在三处文档与代码脱节：

1. **设计文档滞后**：`02_设计/` 下 PRD/INT/DSN/TEC 仍为 `V3.0.0-draft 待评审`，描述的是"目标架构"，但代码已实现该架构（M0-M4 里程碑大部分完成）。文档未反映实际实现状态，导致"文档说要做，代码已做完"的失真。
2. **诊断报告分散且未验证**：`09_整改项/Claude-result`（V3 诊断报告，基于 V0.9.1）指出 12 项 P2-P4 残留问题，但未与代码实测交叉验证；`09_整改项/README.md` 索引失真（声称"2 个活跃文件"，实际 7 个；引用不存在的 `diagnostic_report.md`）。
3. **测试计划缺失**：当前无成文的 CLI/GUI 测试计划，测试虽有 1115 passed 但缺少面向 V0.9.1 的系统性测试矩阵（CLI 命令覆盖、GUI 可见模式交互覆盖）。

## What Changes

### 诊断（实测验证）
- 实测验证 Claude-result V3 诊断报告中 12 项 P2-P4 残留问题（Grep/Read 交叉核查）
- 产出 V0.9.1 实测版综合诊断报告 `09_整改项/diagnostic_report.md`，原 `Claude-result` 归档

### 设计文档更新（02_设计/）
- **001_PRD.md**：版本 V3.0.0-draft → V3.1.0，状态 待评审 → 已实现（标注实现度），新增"当前实现状态基线"章节
- **002_INT.md**：版本 V3.0.0-draft → V3.1.0，DTO/Command/Event 契约对齐实际代码（`ui/contracts/`），Facade/Bridge 映射表对齐实际类名
- **003_DSN.md**：版本 V3.0.0-draft → V3.1.0，5 层架构图对齐实际目录，Bridge 拆分状态标注"已完成"，新增"实现进度基线"章节
- **004_TEC.md**：版本 V3.0.0-draft → V3.1.0，技术决策标注落地状态，复用资产表对齐实际
- **005_里程碑与实施计划.md**：M0-M4 标注实际完成度（基于代码核查），M5-M9 保留规划

### 测试计划（09_整改项/）
- 新增 `CLI测试计划.md`：CLI 命令矩阵（project/change/spec/template/plc/doc/session/vartable/gui 子命令）、覆盖范围、执行方式
- 新增 `GUI测试计划.md`：QML 页面矩阵（驾驶舱/项目工作台/变更中心/规范中心/报告/模板/设置）、可见模式交互测试、状态覆盖（idle/loading/success/empty/warning/error）

### 整改项归档整理（09_整改项/）
- 归档 `remediation_plan.md`（状态=已完成）→ `archive/`
- 归档 4 个 Landing Plan（M2/M3/M4_delivery/M4_spec，对应里程碑已完成）→ `archive/landing_plans/`
- 归档 `Claude-result`（被实测版诊断报告替代）→ `archive/`
- 重写 `README.md` 索引：活跃文件（实测诊断报告 + CLI/GUI 测试计划 + README）、归档文件清单

**文件命名约束**：遵循项目规范，新增文档文件名不带版本号后缀（版本在 frontmatter/正文标识），仅归档时为区分同名文件可加日期前缀。

## Impact
- Affected specs: 无（本 spec 为文档治理任务，不涉及代码 spec 变更）
- Affected docs:
  - `02_设计/001_产品需求文档_PRD.md` ~ `005_里程碑与实施计划.md`（5 个文档更新）
  - `09_整改项/README.md`（索引重写）
  - `09_整改项/Claude-result`（归档至 archive/）
  - `09_整改项/remediation_plan.md`（归档至 archive/）
  - `09_整改项/M2~M4_*.md`（4 个归档至 archive/landing_plans/）
  - 新增 `09_整改项/diagnostic_report.md`（实测诊断报告）
  - 新增 `09_整改项/CLI测试计划.md`
  - 新增 `09_整改项/GUI测试计划.md`
- Affected code: 无（纯文档任务，不修改 .py 代码）

## ADDED Requirements

### Requirement: V0.9.1 实测综合诊断报告
系统 SHALL 产出基于 V0.9.1 代码实测的综合诊断报告，交叉验证 Claude-result V3 报告中 12 项残留问题，标注每项的"实测状态"（存在/已修复/部分修复/失真）。

#### Scenario: 诊断报告交叉验证
- **WHEN** 阅读 `09_整改项/diagnostic_report.md`
- **THEN** 每项问题附 Grep/Read 实测证据（文件:行号 + 实际代码片段），与 Claude-result 声明对照

#### Scenario: 诊断报告归档原报告
- **WHEN** 诊断报告产出后
- **THEN** 原 `09_整改项/Claude-result` 移至 `archive/`，README 索引更新

### Requirement: 设计文档实现状态同步
系统 SHALL 将 `02_设计/` 下 5 个设计文档从"目标架构描述"更新为"已实现架构描述"，版本 V3.0.0-draft → V3.1.0，状态 待评审 → 已实现（标注实现度）。

#### Scenario: PRD 实现状态
- **WHEN** 阅读 `02_设计/001_产品需求文档_PRD.md`
- **THEN** 包含"当前实现状态基线"章节（V0.9.1 代码规模/版本号/架构完成度/里程碑核查），6 个工作域标注实际实现度

#### Scenario: INT 契约对齐
- **WHEN** 阅读 `02_设计/002_接口文档_INT.md`
- **THEN** DTO/Command/Event 契约与 `auto_pm/ui/contracts/` 实际代码一致，Facade/Bridge 映射表类名与实际一致

#### Scenario: DSN 架构对齐
- **WHEN** 阅读 `02_设计/003_详细设计说明书_DSN.md`
- **THEN** 5 层架构图目录名与实际代码一致（`application/` `ui/contracts/` `ui/qml/bridges/` `core/` `db/` `models/`），Bridge 拆分标注"已完成"

#### Scenario: 里程碑完成度核查
- **WHEN** 阅读 `02_设计/005_里程碑与实施计划.md`
- **THEN** M0-M4 标注实际完成度（基于代码核查：文件存在性/方法存在性/测试通过数），非仅凭声明标记

### Requirement: CLI 测试计划
系统 SHALL 在 `09_整改项/` 下提供 CLI 测试计划，覆盖所有 CLI 子命令的命令矩阵、参数组合、预期输出、执行方式。

#### Scenario: CLI 命令矩阵覆盖
- **WHEN** 执行 CLI 测试计划
- **THEN** 覆盖 project/change/spec/template/plc/doc/session/vartable/gui 9 个子命令组，每个子命令标注冒烟/功能/边界测试用例

#### Scenario: CLI 测试执行方式
- **WHEN** 阅读 CLI 测试计划
- **THEN** 标注冒烟测试（`-m smoke`）、单元测试（`-m cli`）、集成测试（`-m integration`）的执行命令与预期耗时

### Requirement: GUI 测试计划
系统 SHALL 在 `09_整改项/` 下提供 GUI 测试计划，覆盖 QML 页面矩阵、可见模式交互测试、状态覆盖，遵循"GUI 测试默认可见模式"约束。

#### Scenario: GUI 可见模式
- **WHEN** 执行 GUI 测试计划
- **THEN** 默认使用可见窗口模式（GUI_VISIBLE=1 或不设置 QT_QPA_PLATFORM=offscreen），仅在 CI/批量回归场景使用 offscreen

#### Scenario: QML 页面矩阵覆盖
- **WHEN** 阅读 GUI 测试计划
- **THEN** 覆盖驾驶舱/项目工作台/变更中心/规范中心/报告/模板/设置 7 个页面，每页面标注 idle/loading/success/empty/warning/error 6 状态覆盖

#### Scenario: GUI 交互测试
- **WHEN** 执行 GUI 测试计划
- **THEN** 覆盖关键交互链路（驾驶舱加载/打开项目工作台/创建变更单/规范检查/文档刷新），标注 pytest-qt 测试用例定位

### Requirement: 整改项文档归档整理
系统 SHALL 重组 `09_整改项/` 目录，已完成的历史文件归档到 `archive/`，活跃文件保留根目录，README 索引与实际文件一致。

#### Scenario: README 索引准确
- **WHEN** 阅读 `09_整改项/README.md`
- **THEN** "当前活跃文件"列表与根目录实际文件一一对应，"归档文件"列表与 `archive/` 实际文件一一对应

#### Scenario: 已完成文件归档
- **WHEN** 检查 `09_整改项/` 根目录
- **THEN** `remediation_plan.md`（已完成）+ `Claude-result`（被替代）+ 4 个 Landing Plan（里程碑已完成）已移至 `archive/` 或 `archive/landing_plans/`

#### Scenario: 活跃文件精简
- **WHEN** 检查 `09_整改项/` 根目录
- **THEN** 仅保留 `README.md` + `diagnostic_report.md` + `CLI测试计划.md` + `GUI测试计划.md` 4 个活跃文件
