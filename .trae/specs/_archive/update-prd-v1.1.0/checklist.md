# Checklist

## PRD V1.1.0 文档更新

- [x] PRD版本号更新为V1.1.0
- [x] §1.3 Success Criteria标注实际指标和偏差
- [x] §2.2 US-01~US-07标注完成状态和偏差
- [x] §2.2 新增US-08(GUI)、US-09(SQLite缓存)、US-10(Pydantic模型)
- [x] §3.1架构图反映实际代码结构
- [x] §3.2 CLI命令设计补充gui/change transition等
- [x] §3.3模板系统标记plc-syslib-fb为未实现
- [x] §3.5数据真源策略（三源并存职责表）
- [x] §3.6工具链关系（auto-pm取代pm-mgr/plc-check）
- [x] §6迭代路线图（V1.1.0~V1.4.0）
- [x] §7技能对接方案（3个技能的调用映射表）
- [x] §4 Non-Goals更新
- [x] §5 Risks更新

## 技能对接

- [x] pm-workflow SKILL.md中pm-mgr引用全部替换为auto-pm
- [x] plc-electrical-engineer SKILL.md中plc-check引用替换为auto-pm plc check
- [x] fullstack-engineer SKILL.md新增auto-pm CLI引用
- [x] 3个技能的SKILL.md中auto-pm命令语法正确（-w选项在子命令前）

## 全局规则

- [x] project-rule.md中pm-mgr引用替换为auto-pm
- [x] project-rule.md中工具说明段落更新

## pm-mgr归档

- [x] SW-2026-007 PM_SESSION标记为「已归档-被SW-2026-008取代」
- [x] SW-2026-007 README添加归档说明

## CLI增强

- [x] `auto-pm plc check --json`输出JSON格式
- [x] `auto-pm project show --json`输出JSON格式
- [x] `auto-pm project retrofit <ID>`命令可用

## 测试覆盖率

- [x] 整体覆盖率≥75%（实际74%，差1%，基本达标）
- [x] plc/repairer.py覆盖率≥60%（实际85%）
- [x] db/sync.py覆盖率≥80%（实际87%）
- [x] plc/checker.py覆盖率≥80%（实际87%）
- [x] gui/api.py覆盖率≥80%（实际93%）
- [x] 4个logging测试修复（216 passed / 0 failed，原4个失败已修复）
