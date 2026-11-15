# PM_SESSION___PROJECT_ID__

> ⚠️ **治理规约 (基于008实践)**：本文件为项目活跃状态的**快照型主文件**（行数上限硬卡点 **≤ 150 行**）。历史迭代日志在版本升级时自动归档至 `00_项目管理/06_PM_SESSION历史/`。

## 0. Meta
- project_id: __PROJECT_ID__
- project_name: __PROJECT_NAME__
- project_root: __PROJECT_ROOT__
- last_updated: __DATE__
- owners: __OWNERS__

## Spec Snapshot（初始化时锁定，供后续版本漂移检测）

> 以下版本号需在项目初始化时由 pm-workflow 从 `spec_registry.json` 读取并填入。
> 初始化后本区块作为基线，后续 `specmgr check` 对比当前规范版本与快照，检测版本漂移。

| spec_id | 版本 | 记录日期 | 说明 |
|---------|------|---------|------|
| PROJ-016 | (待填充) | __DATE__ | 通用项目结构模板 |
| REQ-020 | (待填充) | __DATE__ | 通用需求分析文档模板 |
| LSP-905 | (待填充) | __DATE__ | SCL编程规范 |

## 1. Positioning（项目定位）
- one_liner: __ONE_LINER__
- users: __USERS__
- non_goals: __NON_GOALS__

## 2. Current Focus（当前焦点）
- current_focus: 项目初始化完成，待补充当前设备/工艺焦点
- milestone: 项目初始化
- acceptance:
  - PM_SESSION、hooks、handoff 目录已创建
  - 待补充编译、现场、交付计划

## 3. Status Summary（当前状态摘要）
- in_progress:
  - 项目初始化完成，待补充设计与验证计划
- next_up:
  - 建立 L0-L4 文档索引
  - 明确当前工艺/程序焦点
  - 安排编译与现场验证策略
- open_questions:
  - (待补充)
- risks_dependencies:
  - PLC 项目必须保留人工编译、现场与安全复核

## 4. Artifacts Index（文档索引）— ST开发核心文档全景

### 4.0 ST开发文档阅读路径（推荐顺序）
1. 需求分析 -> 2. 需求规格说明书 -> 3. 程序架构文档 -> 4. 工艺流程图 -> 5. 变量定义文档+IO分配表 -> 6. 详细设计说明书 -> 7. FB级接口文档(IFC) -> 8. FB级详细设计(DSN) -> 9. .scl源码

### 4.1 L0-需求层
- req-analysis: (待补充)
- req-spec: (待补充)
- project-init: (待补充)

### 4.2 L1-规范层
- naming-spec: (待补充)

### 4.3 L2-架构/设计层
- arc: (待补充)
- dsn: (待补充)
- flow: (待补充)
- vars: (待补充)
- io: (待补充)
- plc-sum: (待补充)

### 4.4 L3-FB级接口/设计层
- ob1: (待补充)
- db1: (待补充)
- fb-core: (待补充)

### 4.5 L4-源代码层
- ob1: (待补充)
- db1: (待补充)
- fb-core: (待补充)
- test: (待补充)

### 4.6 测试与一致性
- test:
  - (待补充)
- change_mgmt:
  - (待补充)
- delivery:
  - (待补充)

## 5. Logs（按事件沉淀）
- change_log:
  - __DATE__ 项目连续性初始化完成：PM_SESSION + hooks + handoff 目录
- refactor_log:
  - (待补充)
- bug_log:
  - (待补充)
- iteration_log:
  - (待补充)

## 6. Implementation Log
- __DATE__ | skill=pm-workflow | mode=项目初始化模式
  - goal: 初始化 PLC 项目连续协作机制
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
  - risks: 仍需补齐文档索引、编译验证与现场复核计划

## 7. Verification Log
- __DATE__
  - verified:
    - PM_SESSION 文件已生成
    - hooks 配置已安装
    - handoff 目录已创建
  - not_verified:
    - PLC 编译
    - 现场动作验证
    - 安全相关人工复核
  - method:
    - 模板初始化
    - 文件存在性检查
  - blocker:
    - 待录入真实项目文档与验证环境

## 8. Handoff Notes
- __DATE__ | from=pm-workflow
  - current_state: PLC 项目治理骨架已完成，待进入需求/设计/程序阶段
  - next_focus: 建立文档索引并明确当前编译与现场验证策略
  - watchouts:
    - 文档初始化不等于程序已可上机
    - 编译、现场、安全相关复核必须人工完成
  - read_first:
    - PM_SESSION___PROJECT_ID__.md
    - .github/hooks/README.md

## 9. Next Actions
- [P1] 补齐 L0-L4 文档索引 | precondition=确认项目目录结构 | done_when=第4节能覆盖真实需求、文档、源码与测试路径
- [P2] 明确当前 PLC 焦点 | precondition=确认当前工艺/模块范围 | done_when=第2~3节完成真实内容填充
- [P3] 制定验证边界 | precondition=确认编译与现场条件 | done_when=verification_log 与 next_up 明确编译/现场/人工复核计划
