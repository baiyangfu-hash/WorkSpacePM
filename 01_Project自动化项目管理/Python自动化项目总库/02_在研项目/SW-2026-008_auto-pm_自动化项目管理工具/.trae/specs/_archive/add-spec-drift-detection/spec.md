# auto-pm V2.0.3 规范漂移检测能力补齐 Spec

## 当前开发进度基线（2026-06-24 代码核查）

> **本章节为 spec 强制要求**：任何迭代 spec 必须记录当前代码实际进度，作为后续开发的起点。后续迭代更新必须同步文档（已写入 Trae 规范 `project-rule.md`）。

### 代码规模

| 指标 | 数值 |
|------|------|
| auto_pm/ 源码 | 94 个 .py 文件，18,440 行 |
| tests/ 测试 | 71 个测试文件，980 个 test_ 函数 |
| UI 层占比 | 48%（8,854 行） |

### 版本号现状（混乱）

| 来源 | 版本号 | 问题 |
|------|--------|------|
| pyproject.toml | 0.2.1 | 落后于 CHANGELOG |
| CHANGELOG.md | 0.2.2 | pyproject 未同步 bump |
| PRD frontmatter | V2.0.2 | 文档版本，非产品版本，落后于代码 |
| PM_SESSION §2 | V2.0.1 | 与 §8 矛盾 |
| PM_SESSION §8 | V0.2.2 | 与 §2 矛盾 |

### PRD 路线图完成度

| 版本 | 完成度 | 遗留问题 |
|------|--------|---------|
| V2.0（UI 基座+Bug 修复） | 95% | pywebview 依赖未从 pyproject.toml 移除 |
| V2.0.1（基座补齐） | 70% | D（41 个规范矛盾代码修复）+ E（spec_registry.json 同步）待办 |
| 0.2.2（PLC 模块修复） | 100% | 6 阶段全部交付 |
| V2.0.3（spec drift） | 0% | 本 spec 规划中 |
| V2.1~V2.5 | 部分提前实现 | 验收/归档流程、变量表 Tab 已完成 |

### 里程碑 M1-M4 实际核查

| 里程碑 | 声称状态 | 实际核查 | 差异 |
|--------|---------|---------|------|
| M1-Iter1 版本同步 | ✅ 完成 | ❌ pyproject 仍 0.2.1 | 未同步到 0.2.2 |
| M3-Iter1 ProjectService<200行 | ✅ 完成 | ❌ 560 行 | 拆分不彻底 |
| M3-Iter2 ChangeService<250行 | ✅ 完成 | ❌ 535 行 | 拆分不彻底 |
| M3-Iter5 UI 层去除 DB 访问 | ✅ 完成 | ❌ main_window.py 仍直接创建 DatabaseManager | 未完全去除 |
| 其余 23 项 | ✅ 完成 | ✅ 一致 | — |

### PlcChecker/PlcRepairer 现状

- **PlcChecker**（404 行）：4 项检查（.plc.json/PM_SESSION/PRD/目录结构），**无 spec drift 检查**
- **PlcRepairer**（685 行）：6 项修复（创建文件/目录/字段/重命名），**无 spec drift 修复**
- **PlcService**（128 行）：5 方法封装（check/repair/standardize/check_substance/check_workspace）
- **SubstanceChecker**（244 行）：4 项实质化检查（文档存在/字数/章节/占位符）

## Why

### 问题背景

在 DJ-2026-005 项目审查中发现：auto-pm `plc check --fix` 具备项目结构自动修复能力，但**无法检测和修复规范版本漂移**。PM_SESSION 中的 Spec Snapshot 与 spec_registry.json 存在版本漂移（LSP-906 V1→V2, LSP-907 V1→V1.2.1），但工具未报告也未修复。

### 根因分析

经深度代码核查，auto-pm 当前状态如下：

| 维度 | 现状 | 问题 |
|------|------|------|
| pyproject.toml 版本 | 0.2.1 | 与 CHANGELOG 最新 0.2.2 不一致 |
| CHANGELOG 最新版本 | 0.2.2 | 含 Phase 1-6 完整记录 |
| PRD 文档版本 | V2.0.2 | 路线图重排版，**无 V2.0.2 产品版本定义** |
| 里程碑迭代计划 | M1-M4 全部完成 | 875/875 测试通过 |
| PlcChecker 检查项 | .plc.json/PM_SESSION/PRD/目录结构 | **无规范漂移检测** |
| PlcRepairer 修复项 | 创建缺失文件/目录/字段/重命名 | **无规范漂移修复** |
| specmgr (SW-2026-006) | **未安装** | `No module named specmgr` |
| PRD V2.2 规划 | 吸收 specmgr + 规范漂移检测 | **未实现，排在 V2.2** |

**核心矛盾**：用户期望 auto-pm 能自动检测和修复规范漂移，但该能力在 PRD 路线图中排在 V2.2（吸收 specmgr 后），当前版本（0.2.2/里程碑M4完成）尚未到达。

### 为什么不等到 V2.2

1. **V2.2 依赖 specmgr 完整吸收**，工作量大，周期长
2. **规范漂移检测是高频需求**——每次规范修订后所有项目都需检查
3. **PlcChecker 架构已具备扩展点**——新增检查项成本低
4. **spec_registry.json 已存在**——无需等待 specmgr 迁移

## What Changes

### 新增能力：规范漂移检测（PlcChecker 扩展）

- 在 `plc check` 中新增 `Spec Snapshot` 检查项
- 解析 PM_SESSION 中的 Spec Snapshot 表格，对比 spec_registry.json
- 主版本漂移=FAIL，次版本漂移=WARN，补丁漂移=WARN

### 新增能力：规范漂移修复（PlcRepairer 扩展）

- 在 `plc check --fix` 和 `plc repair` 中新增 Spec Snapshot 修复
- 从 spec_registry.json 读取最新版本，更新 PM_SESSION 中的 Spec Snapshot 表格
- 仅更新版本号，不修改源码

### 版本号统一与文档同步（强制）

- pyproject.toml: 0.2.1 → 0.2.3（跳过 0.2.2，因 CHANGELOG 已记录）
- CHANGELOG: 新增 [0.2.3] 条目
- PRD: V2.0.2 → V2.0.3（新增 V2.0.3 路线图章节）
- PM_SESSION: 统一 §2/§8 版本号为 V0.2.3
- **新增变更记录文件**：在项目根目录 `00_项目基础信息/` 下新增 `005_变更记录_CHG.md`，记录本次 V2.0.3 的所有变更

### 文档同步强制规则（写入 Trae 规范）

将以下规则追加到 `c:\Users\fubai\Desktop\My_Workspace\.trae\rules\project-rule.md`：

> **迭代文档同步规则（强制）**
> 1. 任何迭代 spec 必须包含"当前开发进度基线"章节，记录代码实际进度
> 2. 迭代完成后必须同步更新：pyproject.toml 版本号、CHANGELOG、PRD 路线图、PM_SESSION
> 3. pyproject.toml 版本号必须与 CHANGELOG 最新条目一致
> 4. PM_SESSION §2（Current Focus）与 §8（Handoff Notes）版本号必须一致
> 5. 里程碑迭代计划的"已完成"标注必须经过代码核查，禁止仅凭声明标记完成

## Impact

- **Affected specs**：
  - SW-2026-008 PRD V2.0.2 → V2.0.3（新增 V2.0.3 章节）
  - `.trae/specs/rebuild-auto-pm-v2-unified/` 现有 spec 不变
- **Affected code**：
  - `auto_pm/plc/checker.py`（新增 Spec Snapshot 检查项）
  - `auto_pm/plc/repairer.py`（新增 Spec Snapshot 修复逻辑）
  - `auto_pm/plc/models.py`（新增漂移相关数据类）
  - `auto_pm/plc/spec_snapshot.py`（**新建**：Spec Snapshot 解析器）
  - `pyproject.toml`（版本号 0.2.1 → 0.2.3）
  - `CHANGELOG.md`（新增 [0.2.3] 条目）
- **不影响**：
  - PlcChecker 现有 4 项检查逻辑不变
  - PlcRepairer 现有修复逻辑不变
  - CLI 接口不变（`--fix` 已有）
  - GUI 不变

## ADDED Requirements

### Requirement: 规范漂移检测

The system SHALL detect specification version drift by comparing PM_SESSION Spec Snapshot against spec_registry.json.

#### Scenario: 无漂移
- **WHEN** PM_SESSION Spec Snapshot 中所有规范版本与 spec_registry.json 一致
- **THEN** 检查项 `Spec Snapshot` 状态为 PASS

#### Scenario: 主版本漂移
- **WHEN** PM_SESSION 记录 LSP-906 V1.0.0，spec_registry.json 为 V2.0.0
- **THEN** 检查项 `Spec Snapshot` 状态为 FAIL，消息含 "LSP-906: V1.0.0 → V2.0.0 (主版本漂移)"

#### Scenario: 次版本漂移
- **WHEN** PM_SESSION 记录 LSP-907 V1.0.0，spec_registry.json 为 V1.2.1
- **THEN** 检查项 `Spec Snapshot` 状态为 WARN，消息含 "LSP-907: V1.0.0 → V1.2.1 (次版本漂移)"

#### Scenario: Spec Snapshot 缺失
- **WHEN** PM_SESSION 中无 Spec Snapshot 表格
- **THEN** 检查项 `Spec Snapshot` 状态为 WARN，消息含 "PM_SESSION 缺少 Spec Snapshot 表格"

#### Scenario: spec_registry.json 缺失
- **WHEN** 工作空间中找不到 spec_registry.json
- **THEN** 检查项 `Spec Snapshot` 状态为 WARN，消息含 "未找到 spec_registry.json，跳过漂移检测"

### Requirement: 规范漂移自动修复

The system SHALL auto-fix specification version drift by updating PM_SESSION Spec Snapshot to match spec_registry.json when `--fix` is enabled.

#### Scenario: 自动修复漂移
- **WHEN** 用户执行 `plc check --fix` 且检测到版本漂移
- **THEN** PM_SESSION 中的 Spec Snapshot 表格版本号更新为 spec_registry.json 的最新版本
- **AND** 修复结果记录 "更新 N 条规范版本: LSP-906 V1.0.0→V2.0.0, LSP-907 V1.0.0→V1.2.1"

#### Scenario: dry-run 预览
- **WHEN** 用户执行 `plc repair --dry-run` 且检测到版本漂移
- **THEN** 输出预览 "将更新 N 条规范版本"，但不修改文件

### Requirement: Spec Snapshot 解析器

The system SHALL parse PM_SESSION Spec Snapshot table into structured data.

#### Scenario: 标准表格格式
- **WHEN** PM_SESSION 含 `## Spec Snapshot` 章节下的 Markdown 表格（列：规范编号/版本号/状态）
- **THEN** 解析为 `dict[str, str]`（规范ID→版本号）

#### Scenario: 非标准格式
- **WHEN** PM_SESSION 的 Spec Snapshot 格式不规范（无表格/列名不匹配）
- **THEN** 返回空 dict，检查项报 WARN "Spec Snapshot 格式无法解析"

## MODIFIED Requirements

### Requirement: PlcChecker 检查项

原 PlcChecker 检查 4 项（.plc.json/PM_SESSION/PRD/目录结构）。V2.0.3 新增第 5 项 `Spec Snapshot`，在 PM_SESSION 检查通过后执行。

### Requirement: PlcRepairer 修复项

原 PlcRepairer 修复 4 类问题。V2.0.3 新增 Spec Snapshot 漂移修复，在 PM_SESSION 修复后执行。

## Assumptions & Decisions

1. **PM_SESSION Spec Snapshot 格式**：假设为 `## Spec Snapshot` 或类似标题下的 Markdown 表格，列名含"规范编号"/"版本号"关键词。需正则解析，容忍列名变体。
2. **spec_registry.json 路径**：工作空间根目录下 `00_Obsidian_Base全局规范文件仓库/spec_registry.json`。
3. **漂移严重级别**：主版本（V1→V2）=FAIL，次版本（V1.0→V1.2）=WARN，补丁版本（V1.0.0→V1.0.1）=WARN。
4. **修复范围**：仅更新 PM_SESSION 中的 Spec Snapshot 版本号，不修改源码、不修改 spec_registry.json。
5. **不引入 specmgr 依赖**：V2.2 再正式吸收 specmgr，本次仅实现基础漂移检测。
6. **版本号语义**：pyproject.toml 0.2.3 对应 PRD V2.0.3（产品版本 V2.0.x 系列，x=3 表示第三个增量）。
