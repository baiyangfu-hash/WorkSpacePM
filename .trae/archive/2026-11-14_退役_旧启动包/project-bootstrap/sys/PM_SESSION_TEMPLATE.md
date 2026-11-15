# PM_SESSION___PROJECT_ID__

## 0. Meta
- project_id: __PROJECT_ID__
- project_name: __PROJECT_NAME__
- project_root: __PROJECT_ROOT__
- last_updated: __DATE__
- owners: __OWNERS__

## 1. Positioning（项目定位）
- one_liner: __ONE_LINER__
- users: __USERS__
- non_goals: __NON_GOALS__
- key_principle: __KEY_PRINCIPLE__

## 2. Current Focus（当前焦点）
- current_focus: 项目初始化完成，等待补充首轮目标
- milestone: 项目初始化
- acceptance: PM_SESSION、hooks、handoff 目录已创建

## 3. Status Summary（当前状态摘要）
- in_progress:
  - 项目初始化完成，待补充本轮任务
- next_up:
  - 明确治理范围
  - 补齐路线图、风险台账与变更准入规则
- open_questions:
  - (待补充)
- risks_dependencies:
  - (待补充)
- spec_compliance:
  - last_check: __DATE__
  - result: 待首次检查

## 4. Artifacts Index（文档索引）
- charter:
  - (待补充)
- req:
  - (待补充)
- des:
  - (待补充)
- roadmap:
  - (待补充)
- risk:
  - (待补充)
- governance_rule:
  - (待补充)
- archived:
  - (待补充)

## 5. Logs（按事件沉淀）
- change_log:
  - __DATE__ 项目连续性初始化完成：PM_SESSION + hooks + handoff 目录
- iteration_log:
  - (待补充)
- bug_log:
  - (待补充)
- refactor_log:
  - (待补充)
- release_log:
  - (待补充)
- spec_change_log:
  - (待补充)

## 6. Implementation Log
- __DATE__ | skill=pm-workflow | mode=项目初始化模式
  - goal: 初始化系统级治理项目连续协作机制
  - changed_files:
    - PM_SESSION___PROJECT_ID__.md
    - .github/hooks/hooks.json
    - .github/hooks/scripts/session-start.ps1
    - .github/hooks/scripts/agent-stop.ps1
    - .github/hooks/scripts/session-end.ps1
    - .github/hooks/scripts/apply-handoff.ps1
  - artifacts:
    - .github/hooks/README.md
  - impact: 项目已具备 PM_SESSION 驱动的持续协作能力
  - risks: 仍需补充真实治理范围、文档索引和验证计划

## 7. Verification Log
- __DATE__
  - verified:
    - PM_SESSION 文件已生成
    - hooks 配置已安装
    - handoff 目录已创建
  - not_verified:
    - 治理范围与边界
    - 风险与变更闭环
  - method:
    - 模板初始化
    - 文件存在性检查
  - blocker:
    - 待录入真实项目上下文

## 8. Handoff Notes
- __DATE__ | from=pm-workflow
  - current_state: 项目治理骨架已完成，待进入治理实施阶段
  - next_focus: 补齐项目定位、文档索引和首轮治理目标
  - watchouts:
    - 初始化模板不等于项目内容已齐备
  - read_first:
    - PM_SESSION___PROJECT_ID__.md
    - .github/hooks/README.md

## 9. Next Actions
- [P1] 补齐项目定位与目标 | precondition=确认治理范围 | done_when=第1~3节完成真实内容填充
- [P2] 建立文档索引 | precondition=确认现有文档位置 | done_when=第4节 artifacts index 可追溯
- [P3] 启动首轮治理迭代 | precondition=PM_SESSION 基础字段完成 | done_when=形成明确 current_focus 与 next_up

## Spec Snapshot（初始化时锁定，供后续版本漂移检测）

| spec_id | 版本 | 记录日期 | 说明 |
|---------|------|---------|------|
| DEV-001 | (待填充) | __DATE__ | 通用项目名称命名规范 |
| DEV-002 | (待填充) | __DATE__ | 通用项目工作流命名规范 |
| DEV-003 | (待填充) | __DATE__ | 跨资源库命名统一规范 |
| PM-004 | (待填充) | __DATE__ | PM_WORKFLOW总控Skill使用说明 |
| PROJ-016 | (待填充) | __DATE__ | 通用项目结构模板 |
