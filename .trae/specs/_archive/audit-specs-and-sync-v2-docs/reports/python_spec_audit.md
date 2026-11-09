# Python 规范体系审查报告 - auto-pm V2.0

> **审查日期**: 2026-06-21
> **审查范围**: Python 规范体系（210/211/215/220）与 auto-pm V2.0 代码遵循度 + spec_registry.json 一致性核查
> **审查人**: 规范审查专家（AI）
> **工作空间根**: `c:\Users\fubai\Desktop\My_Workspace`
> **被审查项目**: `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`

---

## 1. 审查概述

### 1.1 审查目标

1. 核对 Python 规范体系（210/211/215/220）与 auto-pm V2.0 实际代码的遵循度
2. 核查 `spec_registry.json` 中 spec 条目的路径、版本、frontmatter 一致性
3. 识别 Python 规范缺口（PySide6/Click CLI/GUI 测试等专项规范）
4. 输出修订建议清单（按 P0/P1/P2 优先级分类）

### 1.2 审查方法

- **静态阅读**: 逐行阅读 4 份 Python 规范文件 + 3 份 auto-pm 代码样本 + INT 文档 + pyproject.toml
- **路径核查**: 用 Glob 工具抽样核查 10 个 spec 条目的 `canonical_path` 是否实际存在
- **frontmatter 核查**: 抽样核查 5 个规范文件的 YAML frontmatter 与 registry 元数据一致性
- **代码扫描**: 用 Grep 统计 `except Exception as e`、`async def` 等模式的出现频次
- **范围边界**: 仅审查和分析，不修改任何规范文件或代码文件

### 1.3 审查对象清单

| 类别 | 文件 | 版本 |
|------|------|------|
| 规范 | `210_Python编程规范_DEV.md` | V1.1.0 |
| 规范 | `211_Python代码审查规范_DEV.md` | V1.0.0 |
| 规范 | `215_Python接口文档模板_INT.md` | V1.0.0 |
| 规范 | `220_Python项目打包规范_DEV.md` | V2.2.0 |
| 代码样本 | `auto_pm/ui/main_window.py` | V2.0 |
| 代码样本 | `auto_pm/core/project_service.py` | V2.0 |
| 代码样本 | `auto_pm/change/change_service.py` | V2.0 |
| 配置 | `pyproject.toml` | 0.1.0 |
| 文档 | `00_项目基础信息/002_接口文档_INT.md` | V2.0.0 |
| 注册表 | `00_Obsidian_Base全局规范文件仓库/spec_registry.json` | 1.0.0 (last_updated 2026-05-27) |

### 1.4 总体结论

| 维度 | 遵循度评级 | 关键问题数 |
|------|-----------|-----------|
| 210 编程规范 | 🟡 部分遵循 | 3 处偏离（常量集中、异步优先、行长度） |
| 211 代码审查规范 | 🟢 基本符合 | 1 处偏离（宽泛异常捕获） |
| 215 接口文档模板 | 🟢 符合 | 模板对 CLI/Service API 适配不足 |
| 220 打包规范 | 🔴 不适用 | 规范与实际打包模式不匹配（exe vs hatchling） |
| spec_registry 一致性 | 🟡 基本一致 | 2 处缺口（SW-2026-008 未注册、SW-2026-007 未标 deprecated） |

---

## 2. Python 规范审查发现

### 2.1 DEV-210 Python 编程规范 V1.1.0

#### 2.1.1 命名规范（§4）— 🟢 符合

抽样核对结果：

| 规范条目 | 实际代码示例 | 结论 |
|---------|------------|------|
| §4.1 局部变量 snake_case | `main_window.py:81` `self._workspace_root = workspace_root or os.getcwd()` | ✓ |
| §4.1 常量 SNAKE_CASE | `main_window.py:75-77` `WINDOW_TITLE / WINDOW_WIDTH / WINDOW_HEIGHT` | ✓ |
| §4.3 类命名 CamelCase | `MainWindow / ProjectService / ChangeService` | ✓ |
| §4.4 模块命名 snake_case | `main_window.py / project_service.py / change_service.py` | ✓ |
| §4.5 包命名 snake_case | `auto_pm.ui / auto_pm.core / auto_pm.change` | ✓ |

#### 2.1.2 代码风格（§5）— 🟡 部分偏离

| 规范条目 | 实际情况 | 偏离说明 |
|---------|---------|---------|
| §5.1 4 空格缩进 | ✓ 符合 | - |
| §5.2 行长度不超过 79 字符 | 🔴 偏离 | `main_window.py:79` `def __init__(self, workspace_root: str = "", parent: QWidget | None = None) -> None:` 长度约 95 字符；`project_service.py:88-93` `list_projects_filtered` 签名跨多行。现代 Python 项目（ruff/black 默认）通常用 88 字符，**规范 §5.2 的 79 字符阈值已过时**。 |
| §5.3 空行 | ✓ 符合 | - |
| §5.5 注释 | ✓ 符合 | 模块/类/方法 docstring 完备 |

#### 2.1.3 Service 层架构模式（§14）— 🟡 部分偏离

| 规范原则（§14.1） | 实际情况 | 偏离说明 |
|------------------|---------|---------|
| 单一职责 | ✓ `ProjectService` 只管项目 CRUD；`ChangeService` 只管变更单 | - |
| 依赖注入 | ✓ `ProjectService.__init__(self, workspace_root, db=None)` 通过构造函数注入 | - |
| **异步优先**（耗时操作使用 async/await） | 🔴 **偏离** | Grep 扫描 `auto_pm/` 全目录，`^async def` 匹配数为 **0**。所有文件 IO、DB 操作、扫描均为同步实现。规范 §14.1 明确要求"所有文件 IO 操作异步化"，但 auto-pm V2.0 完全未采用 async/await。 |

**Service 结构模板对比**（§14.2）：

规范模板：
```python
class XxxService:
    def __init__(self, config: dict, logger: Logger): ...
    async def execute(self, request: Request) -> Response: ...
```

auto-pm 实际（`project_service.py:30-44`）：
```python
class ProjectService:
    def __init__(self, workspace_root: str, db: DatabaseManager | None = None) -> None: ...
    def list_projects(self, scan_depth: int = 4) -> list[ProjectInfo]: ...
```

差异：① 未使用 async；② 参数为 `workspace_root + db` 而非 `config + logger`；③ logger 通过模块级 `setup_logger()` 获取而非注入。

#### 2.1.4 常量集中管理规范（§15）— 🔴 偏离

规范 §15.1 明确要求："所有项目级常量必须集中在 `src/core/constants.py` 文件中"。

实际情况：
- Grep 搜索 `**/constants.py` 在 auto-pm 项目下 **未找到任何 constants.py 文件**
- 常量分散在各模块：
  - `main_window.py:55-62` `_BUSINESS_LINE_OPTIONS`（业务线选项）
  - `main_window.py:75-77` `WINDOW_TITLE / WINDOW_WIDTH / WINDOW_HEIGHT`
  - `project_service.py:34-36` `COPIER_ANSWERS_FILE / PLC_JSON_FILE / PM_SESSION_PREFIX`
  - `change_service.py:40-49` `_UPDATABLE_FIELDS / _PROTECTED_FIELDS`

**不符合 §15.1 的集中管理要求**。

#### 2.1.5 UI 组件化开发规范（§16）— 🟢 基本符合

规范 §16.1 要求的目录结构 vs auto-pm 实际：

| 规范要求 | auto-pm 实际 | 结论 |
|---------|-------------|------|
| `src/ui/widgets/base/` | `auto_pm/ui/widgets/`（有 filter_bar.py, stats_bar.py） | 🟡 缺少 base/ 子目录 |
| `src/ui/widgets/editors/` | 无 editors/（编辑器组件未实现） | 🟡 缺失 |
| `src/ui/widgets/dialogs/` | `auto_pm/ui/dialogs/`（6 个对话框） | ✓ |
| `src/ui/main_window.py` | `auto_pm/ui/main_window.py` | ✓ |

auto-pm 实际目录更细分（`change_center/`, `global_pages/`, `navigation/`, `project_list/`, `workspace/`），比规范示例更完善，但与规范示例的目录名不完全一致。**建议规范 §16.1 更新示例以反映 auto-pm V2.0 的实际组织方式**。

§16.2 组件开发约定：
- "每个 Widget 独立文件，继承基类" ✓
- "信号(Signal)用于组件间通信" ✓（`main_window.py:170-184` 大量使用 Signal/Slot）
- "样式(QSS)内联或统一资源文件" ✓（`main_window.py:258-293` 内联 QSS）

#### 2.1.6 类型注解（§12）— 🟢 符合

auto-pm V2.0 大量使用类型注解，且采用现代语法：
- `def __init__(self, workspace_root: str = "", parent: QWidget | None = None) -> None:`（`main_window.py:79`）
- `def list_projects(self, scan_depth: int = 4) -> list[ProjectInfo]:`（`project_service.py:48`）
- `from __future__ import annotations`（三个样本文件首行均有）
- pyproject.toml 配置 `mypy.strict = true`（`pyproject.toml:64`）

**类型注解实践优于规范要求**（规范 §12 仅提到"使用类型提示"，未要求 strict）。

### 2.2 DEV-211 Python 代码审查规范 V1.0.0

#### 2.2.1 代码风格检查清单（§6.1）— 🟢 符合

| 检查项 | 实际情况 | 结论 |
|--------|---------|------|
| PEP 8 | pyproject.toml 配置 ruff（`pyproject.toml:48`） | ✓ |
| 4 空格缩进 | ✓ | ✓ |
| 行长度 ≤79 | 🔴 见 §2.1.2 | 偏离（规范阈值过时） |
| 命名规范 | ✓ 见 §2.1.1 | ✓ |
| 注释清晰 | ✓ docstring 完备 | ✓ |

#### 2.2.2 功能实现检查清单（§6.2）— 🟡 部分偏离

| 检查项 | 实际情况 | 结论 |
|--------|---------|------|
| 边界情况处理 | ✓ `project_service.py:421-424` `try/except OSError` 处理目录扫描失败 | ✓ |
| **错误处理完善**（捕获特定异常） | 🔴 **偏离** | Grep 统计 `auto_pm/` 目录下 `except Exception as e` 共 **50 处**（分布在 23 个文件）。例如 `main_window.py:95` `except Exception as e:` 捕获 DB 初始化所有异常；`change_service.py:775` `except Exception as e:` 捕获解析异常。规范 §6.2 要求"错误处理是否完善"，210 §7 要求"明确捕获特定类型的异常，避免捕获所有异常"。**50 处宽泛捕获不符合规范**。 |
| 输入验证 | ✓ `change_service.py:101-104` `validate_domain/validate_business_nature/validate_impact_scope/validate_urgency` | ✓ |

#### 2.2.3 安全检查清单（§6.4）— 🟢 符合

| 检查项 | 实际情况 | 结论 |
|--------|---------|------|
| 输入数据验证 | ✓ CLI 层 Click Choice 校验 + Service 层 validate_* 函数 | ✓ |
| 敏感信息处理 | ✓ INT 文档 §7 明确"禁止在代码中硬编码密钥/Token/密码" | ✓ |
| 注入攻击风险 | ✓ `path_resolver` 防目录遍历（INT §7） | ✓ |

#### 2.2.4 测试检查清单（§6.5）— 🟢 符合

- `tests/` 目录存在，包含 `change/`, `cli/`, `config/`, `core/`, `db/` 子目录
- pyproject.toml 配置 `pytest-cov`，`--cov=auto_pm/`，目标覆盖率 ≥80%（INT §13）
- 配置 `pytest-qt>=4.4,<5`（`pyproject.toml:47`）支持 GUI 测试

#### 2.2.5 可维护性检查清单（§6.6）— 🟢 符合

- 函数职责单一 ✓
- docstring 完备 ✓
- 模块设计合理（按业务域分包）✓

### 2.3 INT-215 Python 接口文档模板 V1.0.0

#### 2.3.1 章节结构符合度 — 🟢 完全符合

auto-pm INT 文档（`002_接口文档_INT.md`）章节与 215 模板逐项对照：

| 215 模板章节 | auto-pm INT 章节 | 结论 |
|------------|-----------------|------|
| §1 文档基础信息 | §1 文档基础信息 | ✓ |
| §2 变更记录 | §2 变更记录 | ✓ |
| §3 接口概述 | §3 接口概述（含 §3.3 V2.0 变更摘要） | ✓ |
| §4 接口列表 | §4 接口列表（Part A CLI + Part B Service） | ✓ |
| §5 接口详细信息 | §5 接口详细信息（CLI-01~20, SVC-01~20） | ✓ |
| §6 错误码说明 | §6 错误码说明 | ✓ |
| §7 接口安全 | §7 接口安全 | ✓ |
| §8 版本控制 | §8 版本控制 | ✓ |
| §9 接口特性 | §9 接口特性 | ✓ |
| §10 使用方法 | §10 使用方法 | ✓ |
| §11 接口版本兼容性说明 | §11 版本兼容性说明 | ✓ |
| §12 接口时序图 | §12 接口时序图（4 个时序图） | ✓ |
| §13 接口测试 | §13 接口测试 | ✓ |
| §14 注意事项 | §14 注意事项 | ✓ |
| §15 最佳实践 | §15 最佳实践 | ✓ |
| §16 版本详细变更说明 | §16 版本详细变更说明 | ✓ |
| §17 附录 | §17 附录 | ✓ |

**17 个章节全部覆盖，结构完全符合**。

#### 2.3.2 模板适配问题 — 🟡 模板缺陷

215 模板偏向 RESTful API 设计，但 auto-pm 是 CLI + Service API：

| 215 模板字段 | auto-pm 实际 | 适配问题 |
|------------|-------------|---------|
| §4 接口列表含 `URL / 方法(GET/POST/PUT/DELETE)` | auto-pm 用 `命令 / 功能` | 模板字段名不适用 CLI |
| §5.1 接口URL | auto-pm 用 `语法` + `参数` | 模板字段名不适用 |
| §7 接口安全 `JWT令牌 / Authorization: Bearer` | auto-pm 用 `路径校验 / 破坏性操作确认` | 模板示例不适用 |
| §8 版本控制 `URL格式: /api/v1/endpoint` | auto-pm 用语义化版本 | 模板示例不适用 |

**建议 215 模板增加 CLI/Service API 变体章节**，或拆分为 215-A (REST API) / 215-B (CLI/Service API)。

### 2.4 DEV-220 Python 项目打包规范 V2.2.0

#### 2.4.1 规范与实际打包模式不匹配 — 🔴 严重偏离

220 规范的核心是 **PyInstaller exe 打包**（§3："只交付 exe 文件，用户双击即可运行"），但 auto-pm 实际采用 **hatchling + pyproject.toml 的 Python 包打包模式**：

| 220 规范要求 | auto-pm 实际（pyproject.toml） | 偏离说明 |
|------------|------------------------------|---------|
| §5.1 PyInstaller 打包工具 | `[build-system] requires = ["hatchling"]`（`pyproject.toml:1-3`） | 🔴 完全不同 |
| §6.3 `pyinstaller --onefile main.py` | `[project.scripts] auto-pm = "auto_pm.cli.__main__:cli"` | 🔴 入口点配置方式不同 |
| §10.4 交付物 `{项目名称}.exe` | 无 exe，通过 `pip install auto-pm` 安装 | 🔴 交付物形态不同 |
| §11 完整交付物归档（8 大目录） | 无归档结构 | 🔴 不适用 |
| §17 打包后强制验证（CHK-001~007） | 无验证脚本 | 🔴 不适用 |

**根本原因**：220 规范针对的是"绿色 exe 交付"场景（如 SW-2026-004 项目），而 auto-pm 是开发工具，采用标准 Python 包分发模式。**220 规范未覆盖 pyproject.toml + hatchling 打包模式**。

#### 2.4.2 pyproject.toml 配置质量 — 🟢 优秀

尽管不符合 220 规范，auto-pm 的 pyproject.toml 配置质量很高：

| 配置项 | 实际内容 | 评价 |
|--------|---------|------|
| 构建后端 | hatchling | ✓ 现代 PEP 621 标准 |
| Python 版本 | `>=3.11` | ✓ |
| 依赖管理 | `dependencies` + `dependency-groups.dev` | ✓ PEP 735 标准 |
| 类型检查 | `mypy.strict = true` | ✓ 严格模式 |
| 代码风格 | `ruff>=0.5,<0.6` | ✓ 现代工具 |
| 测试 | `pytest + pytest-cov + pytest-qt` | ✓ GUI 测试支持 |
| 提交规范 | `commitizen>=3,<4` | ✓ 约定式提交 |
| 安全扫描 | `safety>=3.2.9,<4` | ✓ |
| 覆盖率 | `--cov=auto_pm/` + html/xml/term 报告 | ✓ |

**auto-pm 的 pyproject.toml 可作为 220 规范补充"Python 包打包模式"章节的参考样板**。

---

## 3. spec_registry.json 一致性核查结果

### 3.1 registry 基本信息

- **文件路径**: `00_Obsidian_Base全局规范文件仓库/spec_registry.json`
- **版本**: 1.0.0
- **last_updated**: 2026-05-27
- **workspace_root**: `c:\Users\fubai\Desktop\My_Workspace`
- **specs 条目数**: 共 40 个 spec 条目（含 deprecated/archived）
- **域分布**: pm / plc / python / cross-domain

### 3.2 canonical_path 路径存在性核查（抽样 10 个）

| spec_id | canonical_path（相对路径） | 实际存在 | 结论 |
|---------|--------------------------|---------|------|
| DEV-210 | `01_Project自动化项目管理/00_通用规范/Python开发/210_Python编程规范_DEV.md` | ✓ | ✓ |
| DEV-211 | `01_Project自动化项目管理/00_通用规范/Python开发/211_Python代码审查规范_DEV.md` | ✓ | ✓ |
| INT-215 | `01_Project自动化项目管理/00_通用规范/Python开发/215_Python接口文档模板_INT.md` | ✓ | ✓ |
| DEV-220 | `01_Project自动化项目管理/00_通用规范/Python开发/220_Python项目打包规范_DEV.md` | ✓ | ✓ |
| LSP-905 | `0100_PLC自动化/00_通用规范/PLC编程/905_SCL编程规范_LSP.md` | ✓ | ✓ |
| PM-042 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/04_变更管理/042_通用变更管理流程规范_PM.md` | ✓ | ✓ |
| CHG-040 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/04_变更管理/040_通用变更单模板_CHG.md` | ✓ | ✓ |
| SW-2026-006 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-006_规范管理工具/01_需求与设计/01-产品需求文档_PRD.md` | ✓ | ✓ |
| SW-2026-007 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-007_pm工作流工具链/README.md` | ✓ | ✓ |
| DEV-801 | `00_Obsidian_Base全局规范文件仓库/_archive/deprecated/801_PLC变量命名与功能块命名规范_DEV.md` | ✓ | ✓ |

**补充核查**：

| spec_id | canonical_path | 实际存在 | 结论 |
|---------|---------------|---------|------|
| DEV-001 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/00_元规则与治理/001_通用项目名称命名规范_DEV.md` | ✓ | ✓ |
| TOOL-902 | `00_Obsidian_Base全局规范文件仓库/03_执行过程/01_代码开发/02_工具使用规范/902_Git使用指南.md` | ✓ | ✓ |
| PLC-023 | `0100_PLC自动化/00_通用规范/PLC编程/023_PLC程序设计文档模板_PLC.md` | ✓ | ✓ |
| PM-050 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/05_收尾验收/050_通用验收核验报告模板_PM.md` | ✓ | ✓ |

**路径核查结论**: 抽样 14 个 spec 条目，**全部路径存在**，canonical_path 准确率 100%。

### 3.3 frontmatter 与 registry 元数据一致性核查（抽样 5 个）

| spec_id | 字段 | registry 值 | frontmatter 值 | 结论 |
|---------|------|------------|---------------|------|
| DEV-210 | version | V1.1.0 | V1.1.0 | ✓ |
| DEV-210 | lifecycle | stable | stable | ✓ |
| DEV-210 | aliases | ["CODE-210"] | **无 aliases 字段** | 🟡 registry 有 aliases 但 frontmatter 无 |
| DEV-211 | version | V1.0.0 | V1.0.0 | ✓ |
| DEV-211 | lifecycle | stable | stable | ✓ |
| DEV-211 | aliases | ["CODE-211"] | **无 aliases 字段** | 🟡 同上 |
| DEV-220 | version | V2.2.0 | V2.2.0 | ✓ |
| DEV-220 | lifecycle | stable | stable | ✓ |
| DEV-220 | aliases | ["CODE-220"] | **无 aliases 字段** | 🟡 同上 |
| PM-042 | version | V2.2.0 | V2.2.0 | ✓ |
| PM-042 | lifecycle | stable | stable | ✓ |
| PM-042 | aliases | 无 | 无 | ✓ |
| LSP-905 | version | V1.0.2 | V1.0.2 | ✓ |
| LSP-905 | lifecycle | stable | stable | ✓ |
| LSP-905 | replaces | [DEV-801, DEV-810] | [DEV-801, DEV-810] | ✓ |
| DEV-001 | version | V1.0.2 | V1.0.2 | ✓ |
| DEV-001 | lifecycle | stable | stable | ✓ |
| DEV-001 | aliases | ["RULE-001"] | **无 aliases 字段** | 🟡 同上 |
| DEV-801 | version | V1.0.5 | **无 YAML frontmatter**（仅 Markdown 文档标识 `DEV-V1.0.5`） | 🔴 frontmatter 缺失 |
| DEV-801 | lifecycle | deprecated | **无 frontmatter** | 🔴 无法校验 |
| DEV-801 | drift_warning | "项目级副本版本已演化至 V1.0.7" | 文档标识为 V1.0.5 | 🔴 版本漂移已记录但未修复 |

**frontmatter 核查结论**:
- **version/lifecycle**: 5 个抽样中 4 个完全一致（DEV-801 因无 frontmatter 无法校验）
- **aliases**: registry 中 4 个 spec 有 aliases（DEV-001→RULE-001, DEV-210→CODE-210, DEV-211→CODE-211, DEV-220→CODE-220），但对应 frontmatter **均无 aliases 字段** — 这是结构不一致，但可能是设计如此（aliases 仅在 registry 管理）
- **DEV-801**: 文件无 YAML frontmatter，只有普通 Markdown 文档标识，无法通过 specmgr frontmatter 校验

### 3.4 不一致条目识别

#### 3.4.1 🔴 P0 严重缺口：SW-2026-008 (auto-pm) 未在 registry 注册

Grep 搜索 `SW-2026-008` 在 `spec_registry.json` 中 **无任何匹配**。

但根据 `project-rule.md`："auto-pm（SW-2026-008）" 是当前工作空间的核心工具，且 INT 文档（`002_接口文档_INT.md`）frontmatter 明确标注 `project_id: "SW-2026-008"`。

**影响**: specmgr 无法发现和管理 auto-pm 项目的规范条目；与 SW-2026-006 (SpecMgr)、SW-2026-007 (pm-mgr) 已注册形成对比。

#### 3.4.2 🔴 P0 严重缺口：SW-2026-007 (pm-mgr) 未标记为 deprecated

`spec_registry.json:1265-1283` 中 SW-2026-007 仍为 `lifecycle: stable`，但 `project-rule.md` 明确记载："pm-mgr（SW-2026-007）已被 auto-pm（SW-2026-008）取代"。

**应修改**: `lifecycle: stable` → `deprecated`，并添加 `replaced_by: ["SW-2026-008"]`。

#### 3.4.3 🟡 P1 版本漂移：DEV-801 drift_warning 未修复

`spec_registry.json:1177` 记录：`"drift_warning": "项目级副本DJ-2026-005/01_需求与设计/10_编程及变量规范/801_...版本已演化至V1.0.7，frontmatter版本需同步更新"`。

但 registry 中 DEV-801 的 version 仍为 `V1.0.5`，canonical_path 指向的归档文件 frontmatter 也无 YAML（仅 Markdown 标识 `DEV-V1.0.5`）。drift_warning 自 2026-05-27 记录至今未处理。

#### 3.4.4 🟡 P1 registry 时效性：last_updated 2026-05-27

registry `last_updated` 为 2026-05-27，但 auto-pm V2.0 完成于 2026-06-19（INT 文档创建日期）。registry 未反映 V2.0 后的规范变更。

#### 3.4.5 🟢 P2 结构不一致：aliases 字段未在 frontmatter 同步

4 个 spec（DEV-001, DEV-210, DEV-211, DEV-220）在 registry 中有 aliases，但对应规范文件的 YAML frontmatter 无 aliases 字段。若 specmgr 的 frontmatter 校验要求 aliases 双向同步，则需补充；若 aliases 仅 registry 维护，则无需修改。

---

## 4. 规范缺口识别

### 4.1 缺失的 Python 专项规范

| 缺口编号 | 缺口名称 | 优先级 | 说明 | 建议规范编号 |
|---------|---------|--------|------|------------|
| GAP-01 | **PySide6 GUI 开发规范** | P0 | auto-pm V2.0 采用 PySide6（`pyproject.toml:22` `PySide6>=6.8,<7`），但 210 §16 仅泛泛提及"PyQt/PySide"，未覆盖：Signal/Slot 通信约定、QSS 样式管理、QThread 异步模式、角色-Tab 映射模式、QMainWindow 布局约定。auto-pm INT §15 提及"View 不直接持有其他 View 引用，通过 Signal/Slot 通信""长时间操作使用 QThread"等最佳实践，但这些未沉淀为规范。 | 216_PySide6_GUI开发规范_DEV.md |
| GAP-02 | **Click CLI 开发规范** | P0 | auto-pm 有 20 个 CLI 命令（INT Part A），采用 Click（`pyproject.toml:17` `click>=8.1.7`），但无 Click CLI 设计规范：命令分组约定、`-w` 全局参数位置、Choice 枚举校验、退出码约定、Rich 表格输出格式、子命令嵌套深度。 | 217_Click_CLI开发规范_DEV.md |
| GAP-03 | **GUI 测试规范（pytest-qt）** | P1 | auto-pm 配置 `pytest-qt>=4.4,<5`（`pyproject.toml:47`），09_整改项/ 下有大量 GUI 测试日志（迭代1~4），但 211 §6.5 测试检查清单未覆盖 GUI 测试：qtbot fixture 使用、信号断言、QTimer 延迟、避免真实文件 IO 的 mock 策略。DEV-032 GUI测试方案标准偏方案级，缺 pytest-qt 代码级规范。 | 218_GUI测试规范_DEV.md |
| GAP-04 | **pyproject.toml 打包规范（hatchling 模式）** | P0 | 220 规范仅覆盖 PyInstaller exe 打包，未覆盖 auto-pm 采用的 hatchling + pyproject.toml + PEP 621 打包模式。需补充：`[build-system]` 配置、`[project.scripts]` 入口点、`[dependency-groups]` 开发依赖、`[tool.mypy]` / `[tool.ruff]` / `[tool.pytest]` 工具链配置标准。 | 220 章节扩展或 221_pyproject配置规范_DEV.md |
| GAP-05 | **Pydantic v2 模型规范** | P1 | auto-pm 使用 `pydantic>=2.10.6`（`pyproject.toml:15`），models/ 下有 dto.py/enums.py/project.py 等，但 210 未覆盖 Pydantic v2 模型设计：BaseModel 配置、字段验证器、DTO 与领域模型分离、序列化约定。 | 210 §18 扩展或 219_Pydantic模型规范_DEV.md |
| GAP-06 | **SQLite + Repository 模式规范** | P1 | auto-pm 采用 SQLite 缓存 + Repository 模式（`db/repository.py`, `db/connection.py`），但 210 §14 Service 层架构未覆盖数据访问层：Repository 基类设计、连接池管理、WAL 模式、增量同步策略。 | 210 §14 扩展或 222_数据访问层规范_DEV.md |

### 4.2 过时规范条目

| 规范编号 | 过时条目 | 说明 | 建议 |
|---------|---------|------|------|
| 210 §5.2 | "每行代码长度不超过 79 字符" | 现代 Python 项目（ruff/black 默认 88 字符）普遍放宽；auto-pm 实际行长远超 79。PEP 8 本身也建议 99 字符为上限。 | 更新为 "不超过 88 字符（ruff/black 默认），最长不超过 99 字符" |
| 210 §14.1 | "异步优先：耗时操作使用 async/await" | auto-pm V2.0 完全未采用 async，且 GUI 程序通过 QThread 处理耗时操作。规范未考虑 PySide6 的 QThread 替代方案。 | 补充"GUI 程序可使用 QThread 替代 async/await"或降低"异步优先"为"建议" |
| 210 §15.1 | "所有项目级常量必须集中在 `src/core/constants.py`" | auto-pm 采用 `auto_pm/config/app_config.py` 而非 `src/core/constants.py`，路径前缀不适用。 | 更新路径为 "`<package>/config/constants.py` 或 `<package>/core/constants.py`" |
| 210 §16.1 | UI 目录结构示例 `src/ui/widgets/base/`, `src/ui/widgets/editors/` | auto-pm 实际目录更细分（change_center/, global_pages/, navigation/, project_list/, workspace/），且无 src/ 前缀。 | 更新示例为 auto-pm V2.0 实际结构 |
| 215 §4 | 接口列表字段 `URL / 方法(GET/POST/PUT/DELETE)` | 仅适用 REST API，不适用 CLI/Service API。 | 拆分为 REST 变体和 CLI/Service 变体 |
| 220 全文 | PyInstaller exe 打包 | 不适用开发工具类 Python 项目（如 auto-pm 用 hatchling）。 | 补充"Python 包打包模式"章节 |
| 211 §6.2 | "错误处理是否完善"（未明确禁止 `except Exception`） | auto-pm 有 50 处 `except Exception as e`，规范未明确量化阈值。 | 补充"宽泛异常捕获应控制在 X% 以内，关键业务路径必须捕获特定异常" |

---

## 5. 修订建议清单（按优先级分类）

### 5.1 P0 优先级（必须修复，影响规范有效性或工具链运转）

| 编号 | 建议项 | 影响范围 | 具体操作 |
|------|--------|---------|---------|
| P0-01 | **注册 SW-2026-008 (auto-pm) 到 spec_registry.json** | spec_registry.json | 新增 `SW-2026-008` 条目：`canonical_path` 指向 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/README.md`，`version: V2.0.0`，`domain: cross-domain`，`lifecycle: stable`，`tags: ["auto-pm","CLI","GUI","项目管理","跨域"]`，`replaces: ["SW-2026-007"]` |
| P0-02 | **将 SW-2026-007 (pm-mgr) 标记为 deprecated** | spec_registry.json | 修改 SW-2026-007 条目：`lifecycle: stable` → `deprecated`，添加 `replaced_by: ["SW-2026-008"]`，添加 `drift_warning: "已被 auto-pm (SW-2026-008) 取代，详见 project-rule.md"` |
| P0-03 | **新增 216_PySide6 GUI 开发规范** | Python 规范体系 | 新建规范，覆盖：Signal/Slot 通信约定、QSS 样式管理、QThread 异步模式、QMainWindow 布局、角色-Tab 映射、View 间解耦。参考 auto-pm V2.0 实践（INT §15 最佳实践） |
| P0-04 | **新增 217_Click CLI 开发规范** | Python 规范体系 | 新建规范，覆盖：命令分组、全局参数位置（`-w` 在子命令前）、Choice 枚举校验、退出码约定（0/1）、Rich 表格输出、子命令嵌套深度。参考 auto-pm 20 个 CLI 命令实践 |
| P0-05 | **扩展 220 打包规范：补充 pyproject.toml + hatchling 模式** | 220 规范 | 在 220 新增 §18 "Python 包打包模式（pyproject.toml）"章节，覆盖：`[build-system]`、`[project.scripts]`、`[dependency-groups]`、`[tool.mypy/ruff/pytest]` 配置标准。以 auto-pm pyproject.toml 为参考样板 |
| P0-06 | **更新 210 §5.2 行长度阈值** | 210 规范 | 将"不超过 79 字符"更新为"不超过 88 字符（ruff/black 默认），最长不超过 99 字符" |

### 5.2 P1 优先级（应修复，提升规范覆盖度）

| 编号 | 建议项 | 影响范围 | 具体操作 |
|------|--------|---------|---------|
| P1-01 | **更新 210 §14.1 异步优先原则** | 210 规范 | 补充："GUI 程序可使用 QThread 替代 async/await 处理耗时操作"，或将"异步优先"降级为"建议"而非"原则" |
| P1-02 | **更新 210 §15.1 常量文件路径** | 210 规范 | 将 `src/core/constants.py` 更新为 `<package>/config/constants.py` 或 `<package>/core/constants.py`，适配现代 Python 包结构 |
| P1-03 | **更新 210 §16.1 UI 目录结构示例** | 210 规范 | 用 auto-pm V2.0 实际结构（change_center/global_pages/navigation/project_list/workspace/dialogs/widgets/models）替换过时的 `src/ui/widgets/base/editors/dialogs/` 示例 |
| P1-04 | **新增 218_GUI 测试规范（pytest-qt）** | Python 规范体系 | 新建规范，覆盖：qtbot fixture、信号断言（`qtbot.waitSignal`）、QTimer 延迟、mock 文件 IO、避免真实 DB。参考 auto-pm 09_整改项/迭代1~4 测试日志 |
| P1-05 | **新增 219_Pydantic v2 模型规范** | Python 规范体系 | 新建规范，覆盖：BaseModel 配置、字段验证器、DTO 与领域模型分离、序列化约定。参考 auto-pm models/ 目录 |
| P1-06 | **扩展 210 §14：补充 Repository 数据访问层模式** | 210 规范 | 在 §14 新增 §14.3 "Repository 数据访问层"，覆盖：Repository 基类、连接管理、WAL 模式、增量同步。参考 auto-pm db/ 目录 |
| P1-07 | **更新 215 接口文档模板：增加 CLI/Service API 变体** | 215 规范 | 在 §4/§5 增加变体说明："REST API 用 URL/方法；CLI 用命令/语法；Service API 用类/方法签名" |
| P1-08 | **更新 211 §6.2：量化宽泛异常捕获阈值** | 211 规范 | 补充："`except Exception` 应控制在总 except 子句的 20% 以内，关键业务路径（Service 层核心方法）必须捕获特定异常" |
| P1-09 | **修复 DEV-801 drift_warning** | spec_registry.json + DEV-801 文件 | 为 DEV-801 归档文件补充 YAML frontmatter（`spec_id, title, version, domain, lifecycle: deprecated, replaced_by: [LSP-905]`），或确认 drift_warning 所述的项目级副本 V1.0.7 是否需单独注册 |
| P1-10 | **更新 spec_registry.json last_updated** | spec_registry.json | 完成 P0-01/P0-02 后，将 `last_updated` 更新为当前日期 |

### 5.3 P2 优先级（可优化，提升规范一致性）

| 编号 | 建议项 | 影响范围 | 具体操作 |
|------|--------|---------|---------|
| P2-01 | **同步 aliases 字段到 frontmatter** | 4 个规范文件 | 若 specmgr 要求 aliases 双向同步，则为 DEV-001/DEV-210/DEV-211/DEV-220 的 frontmatter 补充 `aliases` 字段；若仅 registry 维护，则在 210 规范中说明 |
| P2-02 | **210 §12 类型注解：提升为 strict 要求** | 210 规范 | 将"使用类型提示"更新为"使用类型提示且启用 mypy strict 模式"，对齐 auto-pm 实践 |
| P2-03 | **211 §7.1 工具清单更新** | 211 规范 | 补充 ruff（替代 flake8 + black 的现代工具）、mypy strict、pytest-qt、safety 等工具，对齐 auto-pm pyproject.toml 工具链 |
| P2-04 | **220 §13 章节编号修复** | 220 规范 | 220 规范 §13 标题为"常见问题"但内部子节编号为 12.1~12.7（`220:570-663`），且 §12.6 重复出现两次（`220:618` 和 `220:641`），需修复编号 |
| P2-05 | **220 §14 版本变更说明编号错乱** | 220 规范 | §14 内部出现 V2.1.0/V1.0.0/V1.1.0/V1.2.0 锚点（`220:1067-1100`），但 §2 版本变更记录中 V2.0.0/V2.1.0/V2.2.0 才是最新，锚点顺序混乱需整理 |
| P2-06 | **210 §17.2 常见问题解决方案表** | 210 规范 | 补充"宽泛异常捕获"行：问题=捕获 Exception，解决方案=捕获特定异常并记录日志，示例=`except (OSError, json.JSONDecodeError) as e` |

---

## 6. 范围边界确认

### 6.1 已完成的工作

- ✅ 阅读 4 份 Python 规范文件（210/211/215/220）完整内容
- ✅ 阅读 3 份 auto-pm V2.0 代码样本（main_window.py / project_service.py / change_service.py）
- ✅ 阅读 auto-pm INT 文档（002_接口文档_INT.md）和 pyproject.toml
- ✅ 阅读 spec_registry.json 完整内容（40 个 spec 条目）
- ✅ 抽样核查 14 个 spec 条目的 canonical_path 路径存在性（100% 存在）
- ✅ 抽样核查 5 个规范文件的 YAML frontmatter 与 registry 元数据一致性
- ✅ Grep 扫描 auto-pm 代码的 async/except Exception 模式
- ✅ 识别 6 个 Python 规范缺口 + 7 个过时条目
- ✅ 输出 6 条 P0 + 10 条 P1 + 6 条 P2 修订建议

### 6.2 未做的事项（范围边界）

- ❌ **未修改任何规范文件**（210/211/215/220 保持原样）
- ❌ **未修改 spec_registry.json**（仅审查，未注册 SW-2026-008，未改 SW-2026-007 状态）
- ❌ **未修改任何 auto-pm 代码文件**（仅阅读分析）
- ❌ **未创建新规范文件**（216/217/218/219 仅作为建议提出，未实际创建）
- ❌ **未运行 specmgr / auto-pm 工具**（仅静态分析）

### 6.3 审查限制

1. **代码样本有限**: 仅深度阅读 3 个代码文件，未覆盖 db/、cli/、plc/、models/ 等模块，规范遵循度评估基于样本推断
2. **frontmatter 核查样本有限**: 仅核查 5 个规范文件的 frontmatter，未覆盖全部 40 个 spec 条目
3. **未运行时验证**: 未实际运行 specmgr check / auto-pm 命令验证工具链一致性
4. **DEV-801 项目级副本未核查**: drift_warning 提及的 `DJ-2026-005/01_需求与设计/10_编程及变量规范/801_...` 路径未实际核查

---

## 附录 A：审查证据索引

### A.1 规范文件路径

| 规范 | 绝对路径 |
|------|---------|
| 210 | `c:\Users\fubai\Desktop\My_Workspace\01_Project自动化项目管理\00_通用规范\Python开发\210_Python编程规范_DEV.md` |
| 211 | `c:\Users\fubai\Desktop\My_Workspace\01_Project自动化项目管理\00_通用规范\Python开发\211_Python代码审查规范_DEV.md` |
| 215 | `c:\Users\fubai\Desktop\My_Workspace\01_Project自动化项目管理\00_通用规范\Python开发\215_Python接口文档模板_INT.md` |
| 220 | `c:\Users\fubai\Desktop\My_Workspace\01_Project自动化项目管理\00_通用规范\Python开发\220_Python项目打包规范_DEV.md` |

### A.2 代码样本路径

| 文件 | 绝对路径 |
|------|---------|
| main_window.py | `c:\Users\fubai\Desktop\My_Workspace\01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-008_auto-pm_自动化项目管理工具\auto_pm\ui\main_window.py` |
| project_service.py | `c:\Users\fubai\Desktop\My_Workspace\01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-008_auto-pm_自动化项目管理工具\auto_pm\core\project_service.py` |
| change_service.py | `c:\Users\fubai\Desktop\My_Workspace\01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-008_auto-pm_自动化项目管理工具\auto_pm\change\change_service.py` |
| pyproject.toml | `c:\Users\fubai\Desktop\My_Workspace\01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-008_auto-pm_自动化项目管理工具\pyproject.toml` |
| INT 文档 | `c:\Users\fubai\Desktop\My_Workspace\01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-008_auto-pm_自动化项目管理工具\00_项目基础信息\002_接口文档_INT.md` |

### A.3 注册表路径

| 文件 | 绝对路径 |
|------|---------|
| spec_registry.json | `c:\Users\fubai\Desktop\My_Workspace\00_Obsidian_Base全局规范文件仓库\spec_registry.json` |

### A.4 关键代码行引用

| 发现 | 文件:行号 | 内容摘要 |
|------|----------|---------|
| 类型注解现代语法 | `main_window.py:79` | `def __init__(self, workspace_root: str = "", parent: QWidget | None = None) -> None:` |
| 宽泛异常捕获 | `main_window.py:95` | `except Exception as e:` |
| 宽泛异常捕获 | `change_service.py:775` | `except Exception as e:` |
| 常量分散 | `main_window.py:55-62` | `_BUSINESS_LINE_OPTIONS` 模块级常量 |
| 常量分散 | `project_service.py:34-36` | `COPIER_ANSWERS_FILE / PLC_JSON_FILE / PM_SESSION_PREFIX` |
| 依赖注入 | `project_service.py:38` | `def __init__(self, workspace_root: str, db: DatabaseManager | None = None)` |
| 同步实现（无 async） | `project_service.py:48` | `def list_projects(self, scan_depth: int = 4) -> list[ProjectInfo]:` |
| Signal/Slot 通信 | `main_window.py:170-184` | `projectSelected.connect / page_switch_requested.connect` |
| hatchling 打包 | `pyproject.toml:1-3` | `[build-system] requires = ["hatchling"]` |
| mypy strict | `pyproject.toml:64` | `strict = true` |
| pytest-qt 配置 | `pyproject.toml:47` | `"pytest-qt>=4.4,<5"` |

---

**报告结束**

> 本报告由规范审查专家于 2026-06-21 生成，仅用于审查目的，未修改任何规范文件或代码文件。
