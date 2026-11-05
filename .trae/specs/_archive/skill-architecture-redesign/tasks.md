# Tasks

## 分析阶段（已完成）

- [x] Task 0: 方案设计与对比
  - 完整任务执行流程图（驾驶舱→pm→子技能→反馈）
  - 三种跨技能切换方案对比（方案 A/B/C）
  - 推荐方案 A 实施细节（skill_context 结构、返回结果结构、边界情况）
  - HTML 原型设计：pm-workflow 统一代理方案（全栈 Web UI + PLC HMI）

## 方案确认阶段

- [x] Task 1: 用户确认方案 A
  - 确认 pm-workflow 作为唯一入口 + 中介模式
  - 确认 skill_context 结构和返回结果结构
  - 确认边界情况处理策略
  - 确认 HTML 原型由 pm-workflow 统一负责
  - 确认实施优先级（是否与 P0/P1 并行）

## 实施阶段（待方案确认后启动）

- [x] Task 2: pm-workflow SKILL.md 强化（核心改动）
  - Step 0.5 扩展：域判断 + 技能分发 + skill_context 构建
  - **Step 3 扩展**：方案/线框模式新增 HTML 原型产出能力
    - 全栈项目：Web UI 原型（页面布局、组件结构、交互模拟）
    - PLC 项目：HMI 原型（按钮、状态指示灯、报警列表、趋势图占位、变量绑定标注）
    - 原型文件存放规范：`PRD/原型/`
  - 新增子技能返回结果解析 → PM_SESSION 回写 → cockpit 反馈写入
  - 保留独立触发能力（ai_context.json 不存在时走原有流程）

- [x] Task 3: fullstack-engineer SKILL.md 重构
  - 删除 item 1.5（cockpit 上下文检查）
  - 新增"接收上下文"章节（从 pm-workflow prompt 中提取）
  - **新增"接收原型"步骤**（从 `PRD/原型/` 读取 Web UI 原型）
  - 保留独立触发能力（无 pm 上下文时读 PM_SESSION）

- [x] Task 4: plc-electrical-engineer SKILL.md 重构
  - 删除 Step 0.5（cockpit 上下文检查）
  - 新增"接收上下文"章节（从 pm-workflow prompt 中提取）
  - **新增"接收原型"步骤**（从 `PRD/原型/` 读取 HMI 原型）
  - 保留独立触发能力（无 pm 上下文时走 Step 1）

- [x] Task 5: 驾驶舱 AiContextBridge 双向扩展（配合 P1 反馈通道）
  - 新增 readAiFeedback() 方法（驾驶舱读取技能执行结果）
  - 驾驶舱 UI 新增"AI 工作状态"指示器

- [x] Task 6: 端到端验证
  - 场景 1：驾驶舱点击"AI 辅助"→ pm-workflow → plc-electrical-engineer → 回写
  - 场景 2：驾驶舱点击"AI 辅助"→ pm-workflow → fullstack-engineer → 回写
  - 场景 3：无 cockpit 上下文 → pm-workflow 独立触发 → 完整流程
  - 场景 4：直接触发 fullstack/plc（绕过 cockpit）→ 独立工作
  - 场景 5：pm-workflow 方案/线框模式 → 产出 HTML 原型 → 确认后分发到子技能

# Task Dependencies
- Task 1 依赖 Task 0（方案确认）
- Task 2（pm-workflow 强化）是核心改动，Task 3、4 依赖 Task 2 中确定的上下文/原型传递格式
- Task 5 依赖 Task 2（pm-workflow 反馈写入格式确定后，驾驶舱才能读）
- Task 6 依赖 Task 2-5 全部完成