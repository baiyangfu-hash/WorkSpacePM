# Checklist

## 流程图完整性
- [x] 驾驶舱→pm-workflow→子技能→反馈的完整链路已覆盖
- [x] 每个步骤有编号（①-⑫）和说明
- [x] 步骤说明表有执行者、动作、关键输出
- [x] 两个子技能分支（PLC 和 Fullstack）均已展示

## 方案对比完整性
- [x] 方案 A（pm 中介）已详述，含优缺点 6 条
- [x] 方案 B（共享文件）已详述，含优缺点 6 条
- [x] 方案 C（pm 内联）已详述，含优缺点 6 条
- [x] 方案对比总览表（9 个维度 × 3 个方案）
- [x] 推荐方案 A，有明确理由

## 实施细节
- [x] skill_context JSON 结构已定义
- [x] 子技能返回结果结构已定义
- [x] pm-workflow 改动方案已明确（Step 0.5 强化 + Step 3 原型扩展）
- [x] fullstack-engineer 改动方案已明确（删除 item 1.5 + 新增接收上下文 + 接收原型）
- [x] plc-electrical-engineer 改动方案已明确（删除 Step 0.5 + 新增接收上下文 + 接收原型）
- [x] 驾驶舱 AiContextBridge 双向扩展方案已明确
- [x] HTML 原型由 pm-workflow 统一代理（全栈 Web UI + PLC HMI）

## 边界情况
- [x] 用户直接触发子技能（绕过 cockpit）
- [x] cockpit 上下文 + 无变更单
- [x] 子技能执行失败
- [x] 跨域变更单
- [x] ai_context.json 过期

## 交付物
- [x] spec.md 包含完整流程图 + 三种方案对比 + 推荐方案实施细节
- [x] tasks.md 包含 6 个任务（含依赖关系）
- [x] checklist.md 包含验证清单（本文件）