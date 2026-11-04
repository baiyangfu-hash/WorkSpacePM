# Tasks

## V1.1.0 — 技能对接 + 测试达标

- [x] Task 1: 更新PRD文档至V1.1.0
  - [x] SubTask 1.1: 更新§1.3 Success Criteria，标注实际指标和偏差
  - [x] SubTask 1.2: 更新§2.2 User Stories，标注US-01~US-07完成状态和偏差
  - [x] SubTask 1.3: 新增US-08(GUI)、US-09(SQLite缓存)、US-10(Pydantic模型)
  - [x] SubTask 1.4: 更新§3.1架构图，反映实际代码结构
  - [x] SubTask 1.5: 更新§3.2 CLI命令设计，补充gui/change transition等
  - [x] SubTask 1.6: 更新§3.3模板系统，标记plc-syslib-fb为未实现
  - [x] SubTask 1.7: 新增§3.5数据真源策略（三源并存职责表）
  - [x] SubTask 1.8: 新增§3.6工具链关系（auto-pm取代pm-mgr/plc-check）
  - [x] SubTask 1.9: 新增§6迭代路线图（V1.1.0~V1.4.0）
  - [x] SubTask 1.10: 新增§7技能对接方案（3个技能的调用映射表）
  - [x] SubTask 1.11: 更新§4 Non-Goals，补充V1.1.0不做的事项
  - [x] SubTask 1.12: 更新§5 Risks，补充技能对接风险

- [x] Task 2: pm-workflow技能SKILL.md更新
  - [x] SubTask 2.1: 将`pm-mgr -w "<ws>" detect`替换为`auto-pm project show <ID>`
  - [x] SubTask 2.2: 将`pm-mgr -w "<ws>" init`替换为`auto-pm project create --stack <plc|python> --id <ID> --name <NAME>`
  - [x] SubTask 2.3: 将`pm-mgr -w "<ws>" retrofit`替换为`auto-pm project retrofit <ID>`
  - [x] SubTask 2.4: 将`pm-mgr -w "<ws>" check`替换为`auto-pm plc check <ID>`
  - [x] SubTask 2.5: 将`pm-mgr -w "<ws>" snapshot`替换为`auto-pm project show <ID>`
  - [x] SubTask 2.6: 更新工具说明段落，标注pm-mgr已废弃、auto-pm为替代

- [x] Task 3: plc-electrical-engineer技能SKILL.md更新
  - [x] SubTask 3.1: 将`plc-check <project_root>`替换为`auto-pm plc check <ID> --json`
  - [x] SubTask 3.2: 新增`auto-pm plc repair <ID> --rename`修复命令引用
  - [x] SubTask 3.3: 新增`auto-pm plc standardize <ID> --apply`标准化命令引用
  - [x] SubTask 3.4: 保留`plc-var-parser`独立引用不变
  - [x] SubTask 3.5: 更新工具说明段落，标注plc-check已废弃

- [x] Task 4: fullstack-engineer技能SKILL.md更新
  - [x] SubTask 4.1: 新增`auto-pm project list`用于了解工作空间项目
  - [x] SubTask 4.2: 新增`auto-pm project show <ID> --json`用于读取项目元数据
  - [x] SubTask 4.3: 新增`auto-pm project create --stack python`用于创建Python项目
  - [x] SubTask 4.4: 新增`auto-pm change create --pid <ID>`用于创建变更单

- [x] Task 5: 全局规则更新
  - [x] SubTask 5.1: 更新`project-rule.md`中pm-mgr引用为auto-pm
  - [x] SubTask 5.2: 更新`project-rule.md`中specmgr/auto-pm工具说明段落

- [x] Task 6: pm-mgr项目归档
  - [x] SubTask 6.1: 在SW-2026-007项目PM_SESSION中标记为「已归档-被SW-2026-008取代」
  - [x] SubTask 6.2: 在SW-2026-007项目README中添加归档说明

- [x] Task 7: auto-pm CLI增强（技能对接前置）
  - [x] SubTask 7.1: `auto-pm plc check`新增`--json`输出格式，便于技能解析
  - [x] SubTask 7.2: `auto-pm project show`新增`--json`输出格式
  - [x] SubTask 7.3: 新增`auto-pm project retrofit <ID>`命令（为已有项目补全.copier-answers.yml）

- [x] Task 8: 测试覆盖率提升至≥75%
  - [x] SubTask 8.1: 补充`plc/repairer.py`测试（14%→85%）
  - [x] SubTask 8.2: 补充`db/sync.py`测试（60%→87%）
  - [x] SubTask 8.3: 补充`plc/checker.py`测试（62%→87%）
  - [x] SubTask 8.4: 补充`gui/api.py`测试（71%→93%）
  - [x] SubTask 8.5: 修复logging/path_resolver测试失败

## V1.2.0 — Python子命令实现

- [ ] Task 9: `python init`命令实现
  - [ ] SubTask 9.1: 将`python init <ID>`改为调用Copier python-tool模板（与`project create --stack python`共享逻辑）
  - [ ] SubTask 9.2: 添加`--template`选项支持不同Python项目类型

- [ ] Task 10: `python check`命令实现
  - [ ] SubTask 10.1: 实现210规范基础检查（pyproject.toml/README/tests/命名规范）
  - [ ] SubTask 10.2: 实现`--json`输出格式

## V1.3.0 — plc-syslib-fb模板

- [ ] Task 11: plc-syslib-fb Copier模板
  - [ ] SubTask 11.1: 创建`templates/plc-syslib-fb/copier.yml`
  - [ ] SubTask 11.2: 创建SysLib FB项目骨架模板文件
  - [ ] SubTask 11.3: 更新`plc check`支持syslib_fb项目类型
  - [ ] SubTask 11.4: 端到端验证

## V1.4.0 — 高级特性

- [ ] Task 12: GUI增强
  - [ ] SubTask 12.1: 变更单创建/流转GUI
  - [ ] SubTask 12.2: 项目概览看板

- [ ] Task 13: 便捷命令
  - [ ] SubTask 13.1: `auto-pm project scan`一键扫描+缓存同步
  - [ ] SubTask 13.2: `auto-pm project retrofit <ID>`为已有项目补全元数据

# Task Dependencies

- [Task 7] depends on [Task 1] — CLI增强需PRD先确认规格 ✅
- [Task 2, 3, 4] depends on [Task 7] — 技能更新需auto-pm CLI先支持--json和retrofit ✅
- [Task 5, 6] depends on [Task 2, 3, 4] — 归档和规则更新需技能更新完成后进行 ✅
- [Task 8] independent — 可与Task 1~7并行 ✅
- [Task 9, 10] depends on [Task 1] — V1.2.0需PRD先更新
- [Task 11] depends on [Task 1] — V1.3.0需PRD先更新
