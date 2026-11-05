# 项目根目录结构清理 Spec

## Why

SW-2026-008 auto-pm 项目根目录经专业审查存在结构混乱问题：运行时测试产物被 git 跟踪、设计目录混入工具脚本与过程产物、已废弃文档未清理、配置文件重复且存在双入口冗余。这些问题会误导新人理解项目结构、增加维护成本，需在 V1.0.0 发布基线后做一次结构收口。

## 诊断结论（专业审查）

### 根目录现状

```
SW-2026-008_auto-pm_自动化项目管理工具/
├── auto_pm/                         ✅ 主包（结构清晰）
├── tests/                           ✅ 测试（117 文件，分层合理）
├── templates/                       ✅ Copier 模板
├── scripts/                         ✅ 工具脚本（6 个）
├── 00_项目基础信息/                  ✅ 治理文档
├── 00_项目管理/                      ✅ 项目管理（变更单/台帐/归档）
├── 02_设计/                         ⚠️ 混入非设计产物
├── 09_整改项/                        ⚠️ 与 00_项目管理 职责部分重叠（有归档机制，本次不动）
├── docs/                            ⚠️ 含已废弃文件未清理
├── output/                          🔴 测试产物被 git 跟踪
├── main.py                          ⚠️ 与 __main__.py 双入口
├── .ruff.toml                       ⚠️ 与 pyproject.toml [tool.ruff] 重复
├── .env_template                    ⚠️ 命名不规范
├── pyproject.toml / CHANGELOG.md / README.md / PM_SESSION / Taskfile.yml  ✅
```

### 问题清单（按严重程度）

#### 🔴 P0 - 运行时产物入库（影响仓库正确性）

1. **`output/gui_smoke_chg2/test_result.json` 被 git 跟踪**
   - `.gitignore` 忽略了 `coverage/` 但遗漏 `output/`
   - 该文件是 GUI 冒烟测试运行时产物，不应入库

#### 🟡 P1 - 文档卫生（已废弃/杂散文件未清理）

2. **`docs/` 下 4 个已废弃文件仍被跟踪**
   - `docs/example.md` — README 明确标记"可删除"
   - `docs/gui-prototype/`（DEPRECATED.md + index.html）— 已被 02_设计/006 原型替代
   - `docs/里程碑迭代计划_V2.1.md` — V2.1 历史计划
   - `docs/归档索引.md` — 索引指向部分已废弃内容

3. **`02_设计/` 混入 3 个非设计产物**
   - `02_设计/screenshot_prototype.py` — Playwright 截图脚本，硬编码绝对路径，引用不存在的 `GUI原型.html`，属工具脚本
   - `02_设计/claude_架构评审建议.md` — AI 评审过程产物，非设计真源
   - `02_设计/Html原型预览/check.txt` — grep 输出残留（内容为 HTML 按钮代码片段）

4. **`02_设计/Html原型预览/` 历史 HTML 原型过多**
   - 006-012 共 7 个 HTML 原型，README 只承认 006 为当前真源
   - 007-012（V2-V7）为迭代历史，按文件命名规范应归档而非平铺保留

#### 🟢 P2 - 结构优化（冗余/规范）

5. **`main.py` 与 `auto_pm/__main__.py` 双入口**
   - `main.py` 仅 28 行薄包装：无参数时 append "gui" 再 call cli()
   - `python -m auto_pm` 已可直接运行，README 也只提 `auto-pm` 命令和 `python -m auto_pm`
   - `main.py` 存在导致"如何启动"产生歧义

6. **`.ruff.toml` 与 `pyproject.toml [tool.ruff]` 配置重复**
   - `.ruff.toml`：line-length=100、exclude、lint rules（优先级更高）
   - `pyproject.toml [tool.ruff]`：仅 extend-exclude
   - 双配置源易混淆，应合并到单一来源

7. **`.env_template` 命名不规范**
   - 业界惯例为 `.env.example`

### 不在本次清理范围（需架构决策）

- **`09_整改项/` 与 `00_项目管理/` 职责重叠**：09_整改项 有完善的归档机制和活跃文件（diagnostic_report/CLI测试计划/GUI测试计划），是否合并属架构决策，本次不擅自动。
- **`tests/test_bug*.py` 命名不规范**：历史遗留回归测试，重命名风险大于收益，本次不动。

## What Changes

- **新增 `.gitignore` 规则**：忽略 `output/` 目录
- **从 git 移除** `output/gui_smoke_chg2/test_result.json`（保留本地文件）
- **删除 `docs/` 下 4 个废弃文件**：example.md、gui-prototype/、里程碑迭代计划_V2.1.md、归档索引.md
- **从 `02_设计/` 移除 3 个杂散文件**：screenshot_prototype.py、claude_架构评审建议.md、Html原型预览/check.txt
- **归档 `02_设计/Html原型预览/` 历史 HTML 原型**：007-012 移入 `02_设计/Html原型预览/archive/`，仅保留 006 为当前真源
- **删除 `main.py`，合并 GUI 便利逻辑到 `auto_pm/__main__.py`**：将"无参数自动启动 GUI"逻辑（`sys.argv` 为空时 append "gui"）合并到 `auto_pm/__main__.py`，统一使用 `python -m auto_pm` 入口。保留 `auto_pm/__main__.py` 现有的编码修复逻辑（PYTHONUTF8=1 + _fix_windows_encoding）
- **合并 ruff 配置**：将 `.ruff.toml` 内容并入 `pyproject.toml [tool.ruff]`，删除 `.ruff.toml`
- **重命名 `.env_template` → `.env.example`**
- **同步更新 README.md**：移除已删除文件的引用，修正项目结构说明

## Impact

- Affected specs: 无（纯文件结构清理，不涉及功能 spec）
- Affected code:
  - `.gitignore`（新增 output/ 规则）
  - `pyproject.toml`（合并 ruff 配置）
  - `README.md`（更新结构说明与文档导航表）
  - `main.py`（删除）
  - `.ruff.toml`（删除）
  - `.env_template` → `.env.example`（重命名）
- 风险评估：低风险。所有变更为文件移动/删除/配置合并，不涉及业务逻辑。ruff 配置合并后行为不变（line-length=100 保持）。删除 main.py 不影响已安装的 `auto-pm` 命令（pyproject scripts 指向 auto_pm.cli.__main__:cli）。

## ADDED Requirements

### Requirement: 仓库整洁性基线

项目根目录 SHALL 只包含必要的顶层条目：主包、测试、模板、脚本、配置、治理文档、设计文档。运行时产物 SHALL 被 gitignore，已废弃文档 SHALL 被删除或归档，配置 SHALL 单一来源。

#### Scenario: 运行时产物不入库
- **WHEN** 运行 GUI 冒烟测试生成 output/ 目录
- **THEN** output/ 被 .gitignore 忽略，不进入版本库

#### Scenario: 单一 ruff 配置来源
- **WHEN** 开发者查看 ruff 配置
- **THEN** 仅在 pyproject.toml [tool.ruff] 中存在配置，无 .ruff.toml 重复文件

#### Scenario: 单一 Python 入口
- **WHEN** 开发者启动应用
- **THEN** 通过 `python -m auto_pm` 或 `auto-pm` 命令启动，根目录无 main.py 冗余入口

## MODIFIED Requirements

### Requirement: 项目根目录结构

根目录顶层条目应精简为：

```
auto_pm/  tests/  templates/  scripts/  docs/(仅活跃)  00_项目基础信息/  00_项目管理/  02_设计/  09_整改项/
pyproject.toml  CHANGELOG.md  README.md  PM_SESSION_SW-2026-008.md  Taskfile.yml
.gitignore  .pre-commit-config.yaml  .copier-answers.yml  .env.example
```

（移除：main.py、.ruff.toml、output/、.env_template；清理 docs/ 与 02_设计/ 杂散文件）

## REMOVED Requirements

### Requirement: main.py 统一入口
**Reason**: 与 `auto_pm/__main__.py` 功能重复。`main.py` 缺失 PYTHONUTF8=1 和 _fix_windows_encoding() 编码修复，在 Windows GBK 终端下会崩溃；`auto_pm/__main__.py` 是 `python -m auto_pm`（项目规定主要调用方式）的必需载体。
**Migration**: 将 main.py 的"无参数自动启动 GUI"逻辑合并到 `auto_pm/__main__.py`（`sys.argv` 长度为 1 时 append "gui"），保留 __main__ 现有编码修复。若有用户脚本调用 `python main.py`，改为 `python -m auto_pm` 或 `python -m auto_pm gui`。
