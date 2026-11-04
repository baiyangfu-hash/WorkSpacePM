# Tasks

本评估报告为分析性质，不涉及代码实施。以下为基于评估发现的后续行动建议（用户反馈后修订）。

- [x] Task 1: 评估结果审阅与确认
  - 用户审阅评估报告，确认各维度评分和发现是否认可
  - 确认优先级排序（P0/P1/P2）是否与实际业务需求一致
  - ✅ 用户反馈：电路设计改为"辅助分析"、HMI 用 HTML 原型、P1/P2 采纳

## P0: 电路辅助分析 + HMI HTML 原型

- [ ] Task 2: 电路辅助分析能力补充（plc-electrical-engineer 技能扩展）
  - IO 清单提取：从设备模型/工艺描述中自动提取 IO 点表
  - 接线表生成：参考 WireViz 等开源项目，根据连接关系生成接线表
  - 元器件选型建议：基于负载/环境参数给出选型建议
  - 输出格式：结构化数据（JSON/Excel），非图纸
  - 明确边界：不生成电气原理图，原理图由工程师在 EPLAN 中完成

- [ ] Task 3: HMI HTML 原型生成能力补充（plc-electrical-engineer 技能扩展）
  - 在 HMI 设计阶段，根据 PRD/REQ 生成 HTML 交互原型
  - 覆盖：画面布局、按钮交互、状态切换、报警弹窗、趋势图占位
  - 交付物：可浏览器打开的 HTML 文件，作为需求确认/甲方评审材料
  - 与现有 `03_HMI设计/` 目录结构对齐

## P1: 技能→驾驶舱反馈通道

- [ ] Task 4: 技能执行结果回写驾驶舱
  - 设计反馈协议：技能执行结果（门禁/测试/LSP）→ JSON 文件 → 驾驶舱读取
  - 驾驶舱 UI：AI 工作状态指示器（运行中/完成/失败）+ 门禁结果面板
  - 评估是否需要新增 Bridge 或复用现有 AiContextBridge（双向扩展）
  - 注意：配合 P2 架构，pm-workflow 作为唯一入口统一收集结果

## P2: 技能架构重构（pm-workflow 唯一入口）

- [ ] Task 5: 技能架构重构方案设计
  - 目标：驾驶舱只对接 pm-workflow，pm-workflow 统筹分发到 fullstack/plc
  - 待讨论方案细节：
    - pm-workflow 如何将 cockpit 上下文传递给子技能？
    - fullstack/plc 删除 cockpit 检查后，如何接收上下文？
    - 跨技能切换流程（pm→fullstack / pm→plc）是否需要调整？
    - 驾驶舱 "AI 辅助" 按钮触发后，用户对 AI 说话时如何确保只触发 pm-workflow？
  - 改动范围：
    - pm-workflow SKILL.md：强化 Step 0.5（唯一 cockpit 消费者），补充上下文传递机制
    - fullstack-engineer SKILL.md：删除 item 1.5（cockpit 上下文检查），改为接收 pm 传递的上下文
    - plc-electrical-engineer SKILL.md：删除 Step 0.5（cockpit 上下文检查），改为接收 pm 传递的上下文

# Task Dependencies
- Task 2 和 Task 3 可并行（均属于 plc-electrical-engineer 技能扩展）
- Task 4 依赖 Task 5 的架构决策（pm-workflow 作为唯一入口后，反馈通道设计会简化）
- Task 5 需用户确认方案细节后再实施