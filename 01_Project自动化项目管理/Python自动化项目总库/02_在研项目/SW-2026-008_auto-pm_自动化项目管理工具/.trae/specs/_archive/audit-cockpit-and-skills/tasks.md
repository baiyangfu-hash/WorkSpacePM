# Tasks

- [x] Task 1: 固定联合审查基线与对象范围
  - [x] SubTask 1.1: 核对 `PM_SESSION_SW-2026-008.md`、`006_技术债评估报告.md` 与既有 `.trae/specs/`，确认本次审查与历史技术债/文档类 spec 的边界
  - [x] SubTask 1.2: 明确本次包含的驾驶舱对象、技能对象、共享规则文件与排除范围
  - [x] SubTask 1.3: 形成“当前开发进度基线 + 本次审查范围”摘要

- [x] Task 2: 审查驾驶舱主链路与工作域边界
  - [x] SubTask 2.1: 审查 `PM_SESSION`、AI 上下文桥接、`qml_main_window.py`、QML 页面与 Bridge/Facade/Service 的主链路
  - [x] SubTask 2.2: 标注驾驶舱页面工作域中的重复职责、跨层耦合、状态同步断点和观测盲区
  - [x] SubTask 2.3: 汇总项目侧发现并按严重度分级

- [x] Task 3: 审查三个技能的定位、边界与共享规则
  - [x] SubTask 3.1: 审查 `pm-workflow` 的入口、统筹、交接与回写职责是否闭环
  - [x] SubTask 3.2: 审查 `fullstack-engineer` 与 `plc-electrical-engineer` 的执行边界、降级路径与领域专有规则
  - [x] SubTask 3.3: 审查 `refs/skill_coordination.md` 与各技能私有规则是否存在重复维护、冲突或漏管
  - [x] SubTask 3.4: 汇总技能侧发现并按严重度分级

- [x] Task 4: 形成联合审查结论与整改入口
  - [x] SubTask 4.1: 将项目侧和技能侧发现整理为统一问题清单
  - [x] SubTask 4.2: 为每条问题补齐证据状态（已验证/待验证）、影响范围、建议动作
  - [x] SubTask 4.3: 将问题映射到 CHG、spec、技术债、PM_SESSION watchout 等后续入口

- [x] Task 5: 复核审查结果可执行性
  - [x] SubTask 5.1: 检查是否覆盖驾驶舱主链路、技能边界、共享规则、整改入口四大维度
  - [x] SubTask 5.2: 检查是否遗漏高优先级问题的 owner、依赖关系或验证状态
  - [x] SubTask 5.3: 形成可直接进入下一轮实施/整改的执行清单

# Task Dependencies

- Task 2 依赖 Task 1（必须先固定审查基线与范围）
- Task 3 依赖 Task 1（必须先固定技能对象与共享规则范围）
- Task 4 依赖 Task 2 和 Task 3（需先产出项目侧与技能侧发现）
- Task 5 依赖 Task 4（最终复核建立在问题清单与整改入口之上）
