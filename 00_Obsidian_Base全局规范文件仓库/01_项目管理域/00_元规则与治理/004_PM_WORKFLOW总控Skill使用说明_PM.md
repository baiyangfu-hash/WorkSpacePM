---
spec_id: PM-004
title: PM_WORKFLOW总控Skill使用说明
version: V1.5.0
domain: pm
lifecycle: deprecated
type: PM_WORKFLOW
status: deprecated
canonical_path: "00_Obsidian_Base全局规范文件仓库/01_项目管理域/00_元规则与治理/004_PM_WORKFLOW总控Skill使用说明_PM.md"
---

# PM_WORKFLOW 总控Skill 使用说明（PM_SESSION 驱动）

> [!WARNING] 已弃用（2026-09-09）
> 本规范依赖的 `pm-workflow` 已停止作为 PM owner、路由入口和规范生命周期 owner。PM_SESSION 也不再是执行状态真源。新工作必须遵循 [[056_跨Agent工作连续性与恢复协议_PM|PM-056]]、PM-033、PM-042 与 PM-046；本文仅保留历史解释，不得用于授权或执行。

## 1. 目标
- 把“需求澄清 → PRD/REQ/DES → 任务拆解 → 变更/迭代/缺陷/交付”固化为可重复流程
- 通过项目根目录的会话文件作为单一真源，保证跨会话连续：`PM_SESSION_<项目编号>.md`
- **作为 Obsidian 全局规范仓库（`00_Obsidian_Base/`）的唯一维护 owner**：凡规范新建、修改或删除，自动完成注册表更新与全局索引同步
- 以本地文档为任务系统主载体，必要时可再同步到 GitHub

## 2. 核心约定
### 2.1 会话文件（强制）
- 每个项目根目录必须存在：`PM_SESSION_<项目编号>.md`
- 项目编号遵循 RULE-001：`[前缀]-YYYY-NNN`（示例：`SW-2026-005`、`DJ-2026-000`）
- 会话文件名采用 A 方案：`PM_SESSION_<项目编号>.md`

### 2.2 单一真源（Single Source of Truth）
- 任何需求/范围/里程碑/风险/未决问题的“当前结论”必须回写到 PM_SESSION
- PRD/REQ/DES/CHG/TEST/交付等产物路径必须登记在 PM_SESSION 的 `Artifacts Index`

### 2.3 Obsidian 全局规范自动同步硬规则
- `pm-workflow` 独占全局规范的生命周期管理（新建、修订、作废、归档、删除）；
- 任何规范变更发生后，PM 技能必须自动执行：
  1. 更新 `00_Obsidian_Base全局规范文件仓库/spec_registry.json`；
  2. 运行 `auto-pm spec index` 自动重新生成 `00_INDEX_全局规范索引.md` 与通用规范 README；
  3. 运行 `auto-pm spec check` 确保全局 0 孤立规范、0 索引断链。

## 3. 总控Skill 做什么
### 3.1 初始化（已有项目/新项目通用）
- 若项目根目录缺少 `PM_SESSION_<项目编号>.md`：自动生成初始化模板
- 自动挂接已有文档（PRD/REQ/DES/变更/测试/交付等）到 `Artifacts Index`
- 生成“当前状态摘要”：当前焦点、进行中事项、下一步、未决问题、风险依赖
- 默认只做项目级最小检查，不把全工作空间巡检作为每轮会话的默认动作

### 3.2 例行更新（每次活动结束必须做）
把所有项目活动统一为 8 类事件（每次只处理一种）：
- Event A：需求新增/需求变更（Scope Change）— 必须前置执行【代码基优先门禁 (Codebase-First Gating)】与《输入齐套性审查》。在研迭代项目强制执行代码基逆向与上下文探路（使用工具检索源码或派发 Grooming 预研子代理），严禁代码盲问（Zero-Stupid-Questions Redline）；只有在代码库探路完毕且仍存在无法推导的真实业务决策/未接线硬件时，方可向用户发起提问
- Event B：迭代推进（Iteration）
- Event C：重构/技术债（Refactor）
- Event D：缺陷审查/修复（Bug）— 必须前置通过工具或 Grooming 预研模式勘测复现路径与涉及源码位置，严禁未经代码查验直接询问用户已有逻辑
- Event E：交付/发布（Delivery）
- Event F：规范巡检（Spec Check）— 规范引用/升级/漂移检查
- Event G：项目初始化（Init）— 空文件夹 → 完整项目骨架
- Event H：旧项目补完（Retrofit）— 已有项目注入连续性机制

每个事件结束后，总控Skill会：
- 生成/更新对应文档产物（PRD/REQ/DES/CHG/TEST/交付）
- 生成/更新任务拆解（Epic/Feature/Story/Enabler/Test）
- 回写 PM_SESSION 的当前状态与对应日志（change_log / iteration_log / bug_log / refactor_log / release_log）
- 默认只验证当前项目 `PM_SESSION` 与直接关联文档引用
- 只有在用户明确要求或发生规范变更时，才执行全工作空间规范巡检

## 4. 推荐口令（新对话也适用）
### 4.1 进入/初始化项目
- `pm: 进入 <项目根目录绝对路径>`
- `pm: 初始化 <项目编号> <项目根目录绝对路径>`

### 4.2 事件触发（选一条即可）
- `pm: 本轮目标 <一句话>`
- `pm: 需求变更 <一句话>`
- `pm: 迭代开始 <里程碑/版本> <一句话目标>`
- `pm: 报Bug <一句话>；复现=<可选>`
- `pm: 重构提案 <一句话>`
- `pm: 交付准备 <版本号> <范围一句话>`
- `pm: 健康检查 当前项目`
- `pm: 健康检查 全工作空间`
- `pm: 规范巡检 <check-id>`

## 5. 与本仓库模板的映射
### 5.1 需求与设计
- PRD：使用 [PRD-001 产品需求文档模板](../01_启动阶段/001_产品需求文档模板_PRD.md)
- REQ：使用 [REQ-020 需求分析文档模板](../02_规划阶段/020_通用需求分析文档模板_REQ.md) 或 [REQ-028 迭代SRS模板](../02_规划阶段/028_迭代需求规格说明书模板_REQ.md)
- DES：使用 [DES-021 详细设计说明书模板](../02_规划阶段/021_通用详细设计说明书模板_DES.md)
- TECH：使用 [TECH-014 技术方案模板](../02_规划阶段/014_技术方案文档模板_TECH.md)

### 5.2 计划、里程碑与迭代
- 迭代计划：使用 [PM-027 迭代项目计划模板](../02_规划阶段/027_迭代项目计划模板_PM.md)
- 里程碑清单：使用 [PM-030 迭代里程碑清单模板](../02_规划阶段/030_迭代里程碑清单模板_PM.md)
- 迭代流程SOP：使用 [PM-033 功能模块迭代流程标准](../02_规划阶段/033_功能模块迭代流程标准_PM.md)

### 5.3 变更、缺陷、测试与交付
- 变更核心规范：使用 [004 文档版本管理与变更核心规范](../04_变更管理/004_通用项目文档版本管理与变更核心规范_DEV.md)
- 变更单/台账/流程：使用 [040 变更单模板](../04_变更管理/040_通用变更单模板_CHG.md)、[041 版本变更台账模板](../04_变更管理/041_通用版本变更台账模板_CHG.md)、[042 变更管理流程规范](../04_变更管理/042_通用变更管理流程规范_PM.md)
- 缺陷追踪：使用 [019 缺陷跟踪表模板](../03_执行管控/019_缺陷跟踪表模板_BUG.md)
- 测试报告：使用 [018 测试报告模板](../03_执行管控/018_测试报告模板_TEST.md)
- 交付规范：使用 [030 通用项目交付规范](../03_执行管控/030_通用项目交付规范_DEV.md)

## 6. 本地文档同步建议（云盘/多端）
### 6.1 推荐组合（稳定）
- 文本类（md/json/yaml）：使用 Git 管理历史；云盘做镜像备份
- 二进制附件（图片/安装包/导出文件）：放云盘，并在 PM_SESSION 的 `Artifacts Index` 登记路径

### 6.2 仅云盘同步（可用但需纪律）
- 同一时间只允许一个设备编辑同一个 `PM_SESSION_<项目编号>.md`
- 发现冲突文件：以“最新 last_updated 的主文件”为准，将差异合并后删除冲突副本

## 7. 最小落地清单（建议复制到项目 README）
- [ ] 项目根目录存在 `PM_SESSION_<项目编号>.md`
- [ ] PM_SESSION 已登记 PRD/REQ/DES/变更/测试/交付的路径
- [ ] 任一需求变更/bug/重构/迭代/交付后，PM_SESSION 的 Logs 有新增一条记录

## 8. auto-pm spec — 规范治理与自动修复

`auto-pm`（SW-2026-008）已吸收原 `specmgr` 能力；PM 角色统一通过 `python -m auto_pm` 执行规范治理。

### 8.0 使用边界

- 日常 PM 会话：默认只做项目级最小检查，重点验证当前项目 `PM_SESSION` 与直接文档引用
- 规范治理任务：当用户明确要求全仓巡检，或本轮属于规范变更/版本升级时，再执行全工作空间检查
- 规范真源修订后：必须执行 `spec index` 或 `spec sync`，禁止手工拼接 `00_INDEX_全局规范索引.md`

### 8.1 基本用法

```bash
# 运行规范健康检查
python -m auto_pm -w <工作空间根目录> spec check

# 仅检查特定检查项
python -m auto_pm -w <工作空间根目录> spec check -c SHC-002 -c SHC-007

# 仅检查当前项目 PM_SESSION 及其直接引用
python -m auto_pm -w <工作空间根目录> spec check --scope project --project-root <项目根目录>

# JSON 格式输出
python -m auto_pm -w <工作空间根目录> spec check --format json

# 只看 warning 及以上
python -m auto_pm -w <工作空间根目录> spec check --severity warning
```

### 8.2 自动修复

```bash
# 预览可自动修复的问题（不实际修改文件）
python -m auto_pm -w <工作空间根目录> spec check --fix --dry-run

# 执行自动修复（当前支持 SHC-002 / SHC-007）
python -m auto_pm -w <工作空间根目录> spec check --fix

# frontmatter 同步：默认预览，带 --fix 才写入
python -m auto_pm -w <工作空间根目录> spec frontmatter
python -m auto_pm -w <工作空间根目录> spec frontmatter --fix
```

### 8.3 索引与报告

```bash
# 重新编译全局索引
python -m auto_pm -w <工作空间根目录> spec index
python -m auto_pm -w <工作空间根目录> spec index --domain plc

# 一键执行 frontmatter + index + check 收口
python -m auto_pm -w <工作空间根目录> spec sync

# 生成规范元数据汇总报告
python -m auto_pm -w <工作空间根目录> spec report
python -m auto_pm -w <工作空间根目录> spec report --format json

# 结构巡检（重复编号、孤立规范、schema 漂移等）
python -m auto_pm -w <工作空间根目录> spec lint --format json
```

### 8.4 常见检查项说明

| 检查ID | 问题类型 | 处理方式 |
|--------|---------|---------|
| SHC-002 | 版本漂移（frontmatter版本 ≠ 注册表版本） | 优先统一注册表与 frontmatter，再执行 `spec check --fix` |
| SHC-007 | frontmatter 缺失或不完整 | 用 `spec frontmatter --fix` 从注册表回填 |
| SHC-004 | 索引链接失效 | 运行 `spec index` 或 `spec sync` 重新生成 |
| SHC-005 | 规范未在注册表登记 | 补登记 `spec_registry.json` 后再运行 `spec check` |
| SHC-008 | 规则文件引用未注册规范 | 更新规则文件引用或补齐规范登记 |

## 9. auto-pm project / pm-session — 项目连续性工具链

`auto-pm` 同时吸收了原 `pm-mgr` 的项目骨架、补完、快照与 PM_SESSION 工具链；不再维护独立 `pm-mgr` 命令。

### 9.1 项目级命令

| 命令 | 用途 | 说明 |
|------|------|------|
| `python -m auto_pm -w <ws> project create <项目ID>` | 初始化新项目骨架 | 按技术栈生成目录、README 与元数据 |
| `python -m auto_pm -w <ws> project retrofit <项目ID>` | 旧项目补完连续性机制 | 补 `.copier-answers.yml`、PLC 标志文件等 |
| `python -m auto_pm -w <ws> project show <项目ID>` | 查看项目元数据 | 用于驾驶舱 / CLI 上下文恢复 |
| `python -m auto_pm -w <ws> project snapshot <项目ID>` | 刷新 PM_SESSION Spec Snapshot | 使版本基线对齐 `spec_registry.json` |

### 9.2 PM_SESSION 命令

| 命令 | 用途 | 说明 |
|------|------|------|
| `python -m auto_pm -w <ws> pm-session check --project-root <项目根目录>` | 检查单项目 PM_SESSION 健康度 | 校验章节完整性、体积与行数阈值 |
| `python -m auto_pm -w <ws> pm-session check` | 巡检全工作空间 PM_SESSION | 递归扫描 `PM_SESSION_*.md` |
| `python -m auto_pm -w <ws> pm-session archive --project-root <项目根目录> --section 6` | 归档指定章节 | 控制 PM_SESSION 主文件长度 |
| `python -m auto_pm -w <ws> pm-session archive --auto` | 自动批量归档超限 PM_SESSION | 收口历史日志和 handoff 条目 |

### 9.3 Snapshot 规范列表

| 项目类型 | 包含的规范 |
|---------|-----------|
| software | PROJ-016, PRD-001, DEV-031, DEV-032, DEV-210, DEV-211, DEV-220, INT-215, DEV-004, CHG-040, CHG-041, PM-042 |
| plc | PROJ-016, REQ-020, LSP-905, LSP-904, LSP-903, LSP-906, LSP-907, INT-815, PLC-023, DEV-004, CHG-040, CHG-041, PM-042 |

## 10. PM_SESSION 完整模板结构

PM_SESSION 文件包含以下10个章节，所有章节均为必填：

| 章节 | 标题 | 必填字段 | 说明 |
|------|------|---------|------|
| §0 | Meta | project_id, project_name, project_root, last_updated, owners | 项目元信息 |
| §1 | Positioning | one_liner, users, non_goals | 项目定位与边界 |
| §2 | Current Focus | current_focus, milestone, acceptance | 当前焦点与里程碑 |
| §3 | Status Summary | in_progress, next_up, open_questions, risks_dependencies | 状态摘要 |
| §4 | Artifacts Index | prd, req, des, test, delivery 等 | 文档产物索引 |
| §5 | Logs | change_log, iteration_log, bug_log, refactor_log, release_log, spec_change_log | 事件日志（只追加） |
| §6 | Implementation Log | date, skill, mode, goal, changed_files, impact, risks | 实现记录 |
| §7 | Verification Log | verified, not_verified, method, blocker | 验证记录 |
| §8 | Handoff Notes | current_state, next_focus, watchouts, read_first | 交接摘要 |
| §9 | Next Actions | ≥3条，带 precondition + done_when | 下一步行动 |

此外，PM_SESSION 应包含 **Spec Snapshot** 区块（位于 §0 之后或文件末尾），记录项目初始化时锁定的规范版本基线，供后续 `auto-pm spec check` / `project snapshot` 检测并收敛版本漂移。

### 10.1 日志回写规则

- 每次事件处理完必须回写 PM_SESSION
- §5 Logs 只追加，不覆盖历史
- §6 Implementation Log 由 fullstack-engineer / plc-electrical-engineer 技能执行后回写
- §7 Verification Log 记录验证结果和阻塞项
- §8 Handoff Notes 确保下次会话可快速恢复上下文
