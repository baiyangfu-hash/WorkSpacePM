# 驾驶舱项目与技能体系联合审查 Spec

## Why
当前 `SW-2026-008 auto-pm` 已形成以 QML 驾驶舱为入口、以 `pm-workflow` 为统筹、以 `fullstack-engineer` / `plc-electrical-engineer` 为执行者的协同体系，但现有 spec 主要覆盖技术债、文档刷新和单次功能迭代，缺少一份面向“驾驶舱架构 + 技能边界 + 联动质量”的统一审查规格。为避免后续审查口径漂移，需要先把审查范围、证据标准、输出物和整改入口定义清楚。

## 当前开发进度基线
- 代码基线：`V1.1.0`，`PM_SESSION_SW-2026-008.md` 最近一次主更新为 2026-07-26。
- 驾驶舱现状：QML 单入口已落地，核心工作域覆盖驾驶舱、项目工作台、变更中心、规范中心、报告、模板、设置，并已接入 AI 上下文桥接与文件监听同步。
- 技能现状：`CHG-SCPT-2026-140` 已完成技能架构重构，`pm-workflow` 作为唯一入口和统筹者，`fullstack-engineer` / `plc-electrical-engineer` 作为纯执行者，二者共享 `refs/skill_coordination.md` 通用规则。
- 技术债现状：`006_技术债评估报告.md` 记录剩余 2 项 M5 UI 待接入债，说明后端/Bridge 能力与 QML 落地之间仍存在审查与治理价值。
- 现状缺口：尚无专门针对“驾驶舱主链路、技能边界、审查证据、整改优先级”四个维度的联合审查 spec。

## What Changes
- 新增一份针对 auto-pm 驾驶舱项目与 3 个核心技能的联合审查规格。
- 明确审查对象：驾驶舱入口链路、AI 上下文桥接、QML 页面工作域、Bridge/Facade/Service 分层、PM_SESSION 真源、技能协同规则。
- 明确审查对象：`pm-workflow`、`fullstack-engineer`、`plc-electrical-engineer` 的定位、边界、重复规则、依赖关系与断点风险。
- 定义审查结论输出：问题清单、证据链、严重度、影响范围、优先级、整改建议、是否需要新 CHG/spec。
- 定义审查过程中的“已验证 / 待验证”标注要求，避免引用未经证实的结论。
- 本次变更不引入破坏性接口调整。

## Impact
- Affected specs: `rebuild-auto-pm-v2-unified`、`v2.1-change-management-enhancement`、`refresh-auto-pm-docs-and-tests`
- Affected code: `PM_SESSION_SW-2026-008.md`、`auto_pm/ui/`、`auto_pm/application/`、`auto_pm/core/`、`auto_pm/change/`、`.trae/skills/fullstack-engineer/`、`.trae/skills/plc-electrical-engineer/`、`.trae/skills/pm-workflow/`

## ADDED Requirements

### Requirement: 审查范围基线固定
系统 SHALL 在启动联合审查前固定本次审查的范围、基线版本、包含项与排除项，避免把既有技术债审查、单次功能审查和本次联合审查混为一体。

#### Scenario: 固定本次联合审查范围
- **WHEN** 用户要求审查 auto-pm 驾驶舱项目以及 `pm-workflow`、`fullstack-engineer`、`plc-electrical-engineer`
- **THEN** 审查范围必须明确包含驾驶舱主链路、技能边界、共享规则、上下文桥接与整改入口
- **THEN** 审查范围必须明确区分与既有 `deep-tech-debt-audit-v1.1.0`、`refresh-auto-pm-docs-and-tests` 的边界

### Requirement: 驾驶舱主链路审查
系统 SHALL 审查驾驶舱从真源到界面的关键链路，包括 `PM_SESSION` / AI 上下文、窗口入口、QML 工作域、Bridge、Facade、Service 之间的职责与依赖关系。

#### Scenario: 审查驾驶舱链路完整性
- **WHEN** 审查执行到项目架构层
- **THEN** 必须核对 `PM_SESSION`、AI 上下文桥接、`qml_main_window.py`、QML 页面、Bridge、Facade、Service 的衔接关系
- **THEN** 必须标注链路中的重复职责、跨层耦合、状态失真点和不可观测点

### Requirement: 技能体系边界审查
系统 SHALL 审查 `pm-workflow`、`fullstack-engineer`、`plc-electrical-engineer` 三个技能的角色定位、共享规则引用、执行边界、降级路径与潜在冲突。

#### Scenario: 审查技能协同边界
- **WHEN** 审查执行到技能体系层
- **THEN** 必须核对 `pm-workflow` 是否保持唯一入口职责
- **THEN** 必须核对 `fullstack-engineer` 与 `plc-electrical-engineer` 是否存在重复规则、职责漂移或回写断点
- **THEN** 必须检查共享 `skill_coordination.md` 与各技能私有规则之间是否存在冲突或重复维护

### Requirement: 审查证据分级输出
系统 SHALL 输出结构化审查结果，并为每条结论附带证据状态、严重度和建议动作，避免出现“仅观点、无证据”的审查报告。

#### Scenario: 形成结构化审查结果
- **WHEN** 完成项目与技能的联合审查
- **THEN** 每条发现都必须标注所属对象、证据来源、严重度、影响范围和建议动作
- **THEN** 每条发现都必须标注为“已验证”或“待验证”
- **THEN** 输出必须可直接转化为后续 CHG、spec 或任务清单

### Requirement: 整改入口标准化
系统 SHALL 将审查发现映射到后续整改入口，明确哪些问题应进入 CHG、哪些应进入新 spec、哪些仅记录为技术债或 watchout。

#### Scenario: 将发现映射为后续动作
- **WHEN** 审查发现涉及架构、技能规则、QML 接入缺口或流程治理问题
- **THEN** 必须给出对应的整改入口类型（CHG / spec / 技术债 / PM_SESSION watchout）
- **THEN** 必须给出优先级和依赖关系，支持后续按批次落地

## MODIFIED Requirements
- 无。

## REMOVED Requirements
- 无。
