# 路线图全量重排 + 规范全量修订 + 文档再同步 Spec

## Why

基于 2026-06-21 完成的规范体系审查（79 条改进建议）和参考项目双重审查（13 条改进建议），用户确认以下决策：

1. **路线图全量重排** — 插入 V2.0.1 基座补齐版，将 79 条建议重新分类到新版本规划
2. **规范向 auto-pm 对齐** — 042/016/040 修订为 auto-pm 实际实现
3. **规范全量修订** — 修订所有问题规范（8+ 个）+ 新增 2 个规范（216/217）
4. **文档再同步** — 路线图重排后再次同步 PRD/PM_SESSION/TEC 等
5. **检查器分步补齐** — plc check 实质化先行，python check 后续
6. **004 安全问题** — auto-pm 吸收时修复

## What Changes

### 1. 路线图全量重排

**新版本规划**（插入 V2.0.1 基座补齐版）：

| 版本 | 主题 | 核心目标 |
|------|------|---------|
| **V2.0.1** | 基座补齐 | site 编码崩溃修复 + plc check 文档实质化检查 + 042/016/040 规范对齐 + 040 §6 影响分析结构补全 |
| V2.1 | 变更管理增强 | 传播链追踪 + 影响分析持久化 + 结构化审批记录 + 变更单编辑补齐 + 004 安全问题吸收修复 |
| V2.2 | 规范中心整合 | spec_registry 管理 + 10 项健康检查 + 索引生成 + Frontmatter 批量管理 + SW-2026-008 注册 + SW-2026-007 deprecated |
| V2.3 | 变量表解析 | 多格式解析 + 编码检测 + 重建/转换 + 变量编辑 + PLC 规范 6 项矛盾修复 + 906 重写 |
| V2.4 | 模板/插件/报告 | 模板 CRUD + 插件 SDK + 报告中心 + 216/217 新规范 + 220 hatchling 扩展 + REQ 模板指引 |
| V2.5 | 系统设置/打包 | Python 项目识别 + python check 命令 + 库项目类型识别 + 用户管理 + PyInstaller 打包 + 旧工具归档 |

**V2.0.1 详细交付物**：

| 交付物 | 验收标准 | 来源 |
|--------|---------|------|
| site 编码崩溃修复 | `python -m auto_pm` 在 Windows GBK 环境下正常运行 | P0-001 |
| plc check 文档实质化检查 | REQ 空模板（占位符>70%）报 FAIL，draft lifecycle 报 WARN | P0-002 |
| 042 V2.3.0 状态机对齐 | 042 §5.2 状态命名改为 draft/submitted/under_review 等 | P0-004 |
| 016 V1.1.0 目录路径统一 | 016 §4.1 变更管理目录改为 00_项目管理/04_变更管理/ | P0-005 |
| 040 §6 影响分析结构补全 | generator.py §6 输出三个子表空表格结构 | P0-006 |
| 906 V2.0.0 重写 | 覆盖 FB_TONR/三段式/批量调用，修正字段名 | P0-010 |
| 905/023 矛盾修复 | 6 项直接矛盾（TIME 字面量/METHOD 命名/中文变量名/字段名）全部修复 | P0-007 |
| SW-2026-008 注册到 registry | spec_registry.json 新增 auto-pm 条目 | P0-008 |
| SW-2026-007 标记 deprecated | spec_registry.json SW-2026-007 lifecycle 改为 deprecated | P0-009 |
| 210/220 过时更新 | 210 行长度阈值更新，220 补充 hatchling 模式 | P1 级 |

### 2. 规范全量修订

**修订清单**（8 个现有规范 + 2 个新规范）：

| 规范 | 修订类型 | 核心变更 |
|------|---------|---------|
| 042 V2.2.0 → V2.3.0 | 对齐 auto-pm | 状态机命名改为 draft/submitted/under_review 等，补充 conditionally_approved/archived |
| 016 V1.0.0 → V1.1.0 | 对齐 auto-pm | 变更管理目录改为 00_项目管理/04_变更管理/，引用 043 规范 |
| 040 | 补全 | §6 影响分析三个子表结构（generator.py 同步补全） |
| 906 V1.0.0 → V2.0.0 | 重写 | 覆盖 FB_TONR/三段式/批量调用，修正 libraryDirectories → libraries |
| 905 | 矛盾修复 | §4.3 定时器示例改用 FC_INT_TO_TIME，删除 TIME 字面量 |
| 023 V2.0.0 → V2.1.0 | 矛盾修复 | §6.4.2/§6.5.2 定时器示例改用 FC_INT_TO_TIME，METHOD 删除 CALL_ 前缀，删除中文变量名 |
| 210 V1.1.0 → V1.2.0 | 过时更新 | §5.2 行长度阈值从 79 调整为 120，补充 PySide6/Click CLI 模式说明 |
| 220 V2.2.0 → V2.3.0 | 扩展 | 补充 hatchling + pyproject.toml 打包模式，不仅限 PyInstaller |
| **216（新增）** | 新增 | PySide6 GUI 开发规范（信号槽/布局/多角色适配/测试） |
| **217（新增）** | 新增 | Click CLI 开发规范（命令组/参数/帮助文本/测试） |

### 3. 文档再同步

路线图重排后需要再次同步的文档：

| 文档 | 同步内容 |
|------|---------|
| PRD §6 | 路线图从 V2.0~V2.5 重排为 V2.0.1~V2.5，新增 V2.0.1 基座补齐版 |
| PM_SESSION | 当前焦点/下一步/状态摘要更新 |
| TEC | 补充 V2.0.1 技术决策（编码崩溃修复方案、检查器深度增强方案） |
| spec_registry.json | 新增 SW-2026-008 条目，SW-2026-007 标记 deprecated |

## Impact

- **Affected specs**：
  - 042/016/040/906/905/023/210/220 → 全量修订
  - 216/217 → 新增规范
  - spec_registry.json → 同步更新
  - PRD/PM_SESSION/TEC → 路线图重排后再次同步
- **Affected code**：
  - auto_pm/change/generator.py → §6 影响分析结构补全
  - auto_pm/change/parser.py → §6 解析逻辑
  - auto_pm/plc/checker.py（或等效文件）→ 文档实质化检查
  - auto_pm 启动入口 → 编码崩溃修复
- **Affected docs**：
  - PRD §6 路线图重排
  - PM_SESSION 焦点/下一步更新
  - TEC 技术决策补充
  - 8 个规范文件修订 + 2 个新规范文件

## ADDED Requirements

### Requirement: V2.0.1 基座补齐版

系统 SHALL 在 V2.0.1 版本中交付基座补齐能力，确保 auto-pm 在 Windows GBK 环境下稳定运行，plc check 能验证文档实质化，规范体系与 auto-pm 实现对齐。

#### Scenario: site 编码崩溃修复
- **WHEN** 在 Windows GBK 环境下运行 `python -m auto_pm`
- **THEN** 程序正常启动，不报 `UnicodeDecodeError: 'gbk' codec can't decode` 错误
- **AND** 所有 CLI 命令（project list/show/plc check 等）正常运行

#### Scenario: plc check 文档实质化检查
- **WHEN** 运行 `auto-pm plc check <project_id>` 且项目 REQ 文档占位符比例 > 70%
- **THEN** 检查结果报 FAIL，提示"需求文档内容未实质化"
- **WHEN** 项目 REQ 文档占位符比例 30%~70%
- **THEN** 检查结果报 WARN，提示"需求文档存在较多占位符"
- **WHEN** 项目 frontmatter lifecycle 为 draft
- **THEN** 检查结果报 WARN，提示"文档仍在草稿阶段"

#### Scenario: 042 状态机对齐
- **WHEN** 修订 042 规范
- **THEN** §5.2 状态机命名改为 draft/submitted/under_review/approved/conditionally_approved/rejected/implementing/pending_acceptance/accepting/completed/closed/archived
- **AND** 补充 conditionally_approved 和 archived 状态的定义和流转规则
- **AND** 更新看板列标识和 STATUS_LABELS 中文标签

#### Scenario: 016 目录路径统一
- **WHEN** 修订 016 规范
- **THEN** §4.1 变更管理目录从 06_变更管理/ 改为 00_项目管理/04_变更管理/
- **AND** 引用 043 规范作为详细目录结构依据
- **AND** 明确 PLC 项目与 Python 项目的变更管理目录差异

#### Scenario: 040 §6 影响分析结构补全
- **WHEN** 运行 `auto-pm change create` 生成变更单
- **THEN** §6 部分输出三个子表空表格结构（§6.1 项目约束影响表/§6.2 技术领域影响表/§6.3 变更传播链）
- **AND** parser.py 能解析 §6 数据

#### Scenario: 906 重写
- **WHEN** 修订 906 规范
- **THEN** 版本升级到 V2.0.0
- **AND** 覆盖 FB_TONR/三段式/批量调用模式
- **AND** 修正 libraryDirectories → libraries
- **AND** 与 903/905 不再矛盾

#### Scenario: 905/023 矛盾修复
- **WHEN** 修订 905 和 023 规范
- **THEN** 6 项直接矛盾全部修复（TIME 字面量/METHOD 命名/中文变量名/字段名）
- **AND** 所有规范间示例代码一致

#### Scenario: spec_registry.json 同步
- **WHEN** 更新 spec_registry.json
- **THEN** 新增 SW-2026-008 (auto-pm) 条目
- **AND** SW-2026-007 (pm-mgr) lifecycle 改为 deprecated

### Requirement: 规范全量修订

系统 SHALL 全量修订所有问题规范，确保规范体系与 auto-pm V2.0 实现一致，并新增 PySide6 GUI 和 Click CLI 专项规范。

#### Scenario: 210/220 过时更新
- **WHEN** 修订 210 和 220 规范
- **THEN** 210 §5.2 行长度阈值从 79 调整为 120
- **AND** 210 补充 PySide6/Click CLI 模式说明
- **AND** 220 补充 hatchling + pyproject.toml 打包模式

#### Scenario: 216 PySide6 GUI 开发规范新增
- **WHEN** 创建 216 规范
- **THEN** 覆盖信号槽机制/布局管理/多角色适配/QThread/GUI 测试等
- **AND** 注册到 spec_registry.json

#### Scenario: 217 Click CLI 开发规范新增
- **WHEN** 创建 217 规范
- **THEN** 覆盖命令组/参数定义/帮助文本/CLI 测试等
- **AND** 注册到 spec_registry.json

### Requirement: 文档再同步

系统 SHALL 在路线图重排后再次同步项目文档，确保文档反映最新版本规划。

#### Scenario: PRD §6 路线图重排
- **WHEN** 同步 PRD 文档
- **THEN** §6 路线图从 V2.0~V2.5 重排为 V2.0.1~V2.5
- **AND** 新增 V2.0.1 基座补齐版的交付物和验收标准
- **AND** V2.1 变更管理增强增加 004 安全问题吸收修复

#### Scenario: PM_SESSION 更新
- **WHEN** 同步 PM_SESSION
- **THEN** 当前焦点更新为 V2.0.1 基座补齐
- **AND** 下一步更新为 V2.0.1 各交付物
- **AND** 状态摘要反映路线图重排

#### Scenario: TEC 技术决策补充
- **WHEN** 同步 TEC 文档
- **THEN** 补充 V2.0.1 技术决策（编码崩溃修复方案、检查器深度增强方案）

## MODIFIED Requirements

### Requirement: SW-2026-008 迭代路线图

原 V2.0~V2.5 六个版本路线图重排为 V2.0.1~V2.5 七个版本，插入 V2.0.1 基座补齐版作为最高优先级。

## REMOVED Requirements

无（本 spec 不移除任何需求，仅重排和修订）

## Out of Scope

- 不修改 DJ-2026-000/SysLib 的 REQ 实际内容
- 不修复 SW-2026-004 的安全问题（V2.1 吸收时修复）

## Implementation Status (2026-06-22 更新)

本 spec 原定仅规划不实施代码变更，但 V2.0.1-A/C 已完成代码实施：

- **V2.0.1-A** ✅ 已完成: site 模块 GBK 编码崩溃修复（auto_pm/__main__.py + cli/__main__.py）
- **V2.0.1-C** ✅ 已完成: 042/016 规范对齐代码实施（19 项冲突修复，5 文件修改，105 测试通过）
  - enums.py: ChangeStatus 新增 archived
  - models.py: STATUS_FLOW/STATUS_LABELS 新增 archived
  - change_service.py: archived 门禁+流转+rejected→draft comment+conditionally_approved→implementing comment+审批环节中文化+Python 项目路径支持
  - parser.py: conditionally_approved 推断路径
  - path_resolver.py: find_ledger_file 双路径搜索
- **V2.0.1-B** 待实施: plc check 文档实质化检查
- **V2.0.1-D** 待实施: 906/905/023 PLC 规范矛盾代码修复（41 个代码片段）
- **V2.0.1-E** 待实施: spec_registry.json 同步
