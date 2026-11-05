# 规范体系审查报告（FINAL）

> **审查日期**: 2026-06-21
> **审查类型**: 规范体系遵循度与一致性审查（只读分析）
> **审查人**: 规范审查专家（AI）
> **工作空间根**: `c:\Users\fubai\Desktop\My_Workspace`
> **报告版本**: V1.0.0
> **整合来源**:
> - Python 规范审查报告（python_spec_audit.md）
> - PLC 规范审查报告（plc_spec_audit.md）
> - PM 规范审查报告（pm_spec_audit.md）

---

## 1. 审查概述

### 1.1 审查目标

本次审查对工作空间内的规范体系进行系统性核查，目标包括：

1. 核对 Python 规范体系（210/211/215/220）与 auto-pm V2.0 实际代码的遵循度
2. 核对 PLC 规范体系（LSP-905/904/903/906/907 + 023/815）的内部一致性及项目遵循度
3. 核对 PM 规范体系（040/042/043/010/016）与 auto-pm V2.0 变更管理实现的对接关系
4. 核查 `spec_registry.json` 中 spec 条目的路径、版本、frontmatter 一致性
5. 识别各域规范缺口（Python 专项规范缺失、PLC 规范过时、PM 对接缺口）
6. 输出修订建议清单（按 P0/P1/P2 优先级分类）

### 1.2 审查范围

| 域 | 规范编号 | 规范数量 |
|----|---------|---------|
| Python | 210 / 211 / 215 / 220 | 4 |
| PLC | LSP-905 / 904 / 903 / 906 / 907 + PLC-023 + INT-815 | 7 |
| PM | CHG-040 / PM-042 / PM-043 / PM-010 / PROJ-016 | 5（任务要求 4 个核心 + 043 辅助） |
| 注册表 | spec_registry.json | 1 |
| **合计** | | **17** |

### 1.3 审查方法

- **静态阅读**: 逐行阅读 16 份规范文件 + auto-pm V2.0 代码样本（main_window.py / project_service.py / change_service.py / generator.py / models.py / parser.py / path_resolver.py）+ INT 文档 + pyproject.toml + 项目模板
- **路径核查**: 用 Glob 工具抽样核查 14 个 spec 条目的 `canonical_path` 是否实际存在
- **frontmatter 核查**: 抽样核查 5 个规范文件的 YAML frontmatter 与 registry 元数据一致性
- **代码扫描**: 用 Grep 统计 `except Exception as e`、`async def` 等模式的出现频次
- **交叉比对**: 比对规范之间的内部一致性（PLC 域 6 项直接矛盾）和规范与实现的一致性（PM 域 14 项对接缺口）
- **工具验证**: 运行 `auto-pm plc check DJ-2026-000 --json` 获取结构合规性报告
- **范围边界**: 仅审查和分析，不修改任何规范文件或代码文件

### 1.4 审查对象清单

#### 1.4.1 Python 规范（4 份）

| 规范编号 | 标题 | 版本 | 文件路径 |
|---------|------|------|---------|
| DEV-210 | Python 编程规范 | V1.1.0 | `01_Project自动化项目管理/00_通用规范/Python开发/210_Python编程规范_DEV.md` |
| DEV-211 | Python 代码审查规范 | V1.0.0 | `01_Project自动化项目管理/00_通用规范/Python开发/211_Python代码审查规范_DEV.md` |
| INT-215 | Python 接口文档模板 | V1.0.0 | `01_Project自动化项目管理/00_通用规范/Python开发/215_Python接口文档模板_INT.md` |
| DEV-220 | Python 项目打包规范 | V2.2.0 | `01_Project自动化项目管理/00_通用规范/Python开发/220_Python项目打包规范_DEV.md` |

#### 1.4.2 PLC 规范（7 份）

| 规范编号 | 标题 | 版本 | 文件路径 |
|---------|------|------|---------|
| LSP-905 | SCL 编程规范 | V1.0.2 | `0100_PLC自动化/00_通用规范/PLC编程/905_SCL编程规范_LSP.md` |
| LSP-904 | SCL 注释规范 | V1.2.0 | `0100_PLC自动化/00_通用规范/PLC编程/904_SCL注释规范_LSP.md` |
| LSP-903 | 定时器使用规范 | V2.1.0 | `0100_PLC自动化/00_通用规范/PLC编程/903_定时器使用规范_LSP.md` |
| LSP-906 | 错误预防规则 | V1.0.0 | `0100_PLC自动化/00_通用规范/PLC编程/906_错误预防规则_LSP.md` |
| LSP-907 | 项目配置规范 | V1.0.0（版本历史 V1.2.0） | `0100_PLC自动化/00_通用规范/PLC编程/907_项目配置规范_LSP.md` |
| PLC-023 | PLC 程序设计文档模板 | V2.0.0 | `0100_PLC自动化/00_通用规范/PLC编程/023_PLC程序设计文档模板_PLC.md` |
| INT-815 | PLC 接口文档模板 | V1.1.0（页脚 V1.0.0） | `0100_PLC自动化/00_通用规范/PLC编程/815_PLC接口文档模板_INT.md` |

#### 1.4.3 PM 规范（4 份核心 + 1 份辅助）

| 规范编号 | 标题 | 版本 | 文件路径 |
|---------|------|------|---------|
| CHG-040 | 通用变更单模板 | V2.1.0 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/04_变更管理/040_通用变更单模板_CHG.md` |
| PM-042 | 通用变更管理流程规范 | V2.2.0 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/04_变更管理/042_通用变更管理流程规范_PM.md` |
| PM-010 | 通用项目管理规范 | V1.0.2 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/02_规划阶段/010_通用项目管理规范_PM.md` |
| PROJ-016 | 通用项目结构模板 | V1.0.0 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/02_规划阶段/016_通用项目结构模板_PROJ.md` |
| PM-043 | 通用变更管理目录结构说明（辅助） | V2.1.0 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/04_变更管理/043_通用变更管理目录结构说明_PM.md` |

#### 1.4.4 注册表

| 文件 | 版本 | last_updated | 路径 |
|------|------|-------------|------|
| spec_registry.json | 1.0.0 | 2026-05-27 | `00_Obsidian_Base全局规范文件仓库/spec_registry.json` |

#### 1.4.5 参考项目

| 项目 | 路径 | 角色 |
|------|------|------|
| SW-2026-008 (auto-pm) | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具` | Python 规范遵循度参考 |
| DJ-2026-000 | `0100_PLC自动化/DJ-2026-000/` | PLC 规范遵循度参考（SysLib 公共库 FB 测试套件） |
| SysLib | `0100_PLC自动化/01_SharedLibraries/SysLib/` | PLC 规范遵循度参考（共享函数库） |

### 1.5 总体结论

| 维度 | 遵循度评级 | 关键问题数 |
|------|-----------|-----------|
| Python 210 编程规范 | 🟡 部分遵循 | 3 处偏离（常量集中、异步优先、行长度） |
| Python 211 代码审查规范 | 🟢 基本符合 | 1 处偏离（宽泛异常捕获 50 处） |
| Python 215 接口文档模板 | 🟢 符合 | 模板对 CLI/Service API 适配不足 |
| Python 220 打包规范 | 🔴 不适用 | 规范与实际打包模式不匹配（exe vs hatchling） |
| PLC LSP-903/904 | 🟢 高质量 | 内部一致性强 |
| PLC LSP-905/906/907/023 | 🔴 多处矛盾 | 6 项直接矛盾 + 严重过时 |
| PLC INT-815 | 🟡 版本号不一致 | frontmatter/页脚矛盾 |
| PM 040/042/010/016 | 🔴 对接缺口 | 14 项对接缺口（P0×3 / P1×6 / P2×5） |
| spec_registry 一致性 | 🟡 基本一致 | 2 处严重缺口 + 1 处版本漂移未修复 |

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

### 2.5 Python 规范遵循度评级汇总

| 规范 | 评级 | 关键问题 |
|------|------|---------|
| 210 编程规范 | 🟡 部分遵循 | 3 处偏离（常量集中、异步优先、行长度） |
| 211 代码审查规范 | 🟢 基本符合 | 1 处偏离（宽泛异常捕获 50 处） |
| 215 接口文档模板 | 🟢 符合 | 模板对 CLI/Service API 适配不足 |
| 220 打包规范 | 🔴 不适用 | 规范与实际打包模式不匹配（exe vs hatchling） |

---

## 3. PLC 规范审查发现

### 3.1 LSP-905 SCL 编程规范 V1.0.2

**规范状态**: 已验证，2026-05-29 更新

**核心规则**:
- 语法白名单原则 (§4): 除明确列出的语法外禁止使用其他 SCL/IEC 语法特性
- 变量命名 (§3.1): `i_`/`o_`/`q_`/`s_`/`fb_`/`CONST_` 前缀, 小驼峰, 禁止中文变量名
- METHOD 命名 (§2.1): 禁止 `CALL_` 前缀
- 定时器调用 (§4.3): 必须包含完整参数 (IN/PT/Q/ET), Q 不能为空
- 标点符号: 必须英文半角

**发现的问题**:

🔴 **P0 - 严重矛盾: §4.3 定时器调用示例使用 TIME 字面量, 与 LSP-903/906 直接冲突**

LSP-905 §4.3 (第 214 行) 示例:
```scl
fb_tActionTimer(IN := FALSE, PT := T#500ms, Q => s_bTimer_Q, ET => q_eElapsed);
```

此示例使用 `PT := T#500ms` (TIME 类型字面量), 但:
- LSP-903 V2.1.0 §2.1 明确规定 PT 参数类型为 **DINT** (扫描周期数)
- LSP-903 §4 错误表 E4 明确禁止 `PT := T#500ms`
- LSP-906 §1.1 明确禁止 TIME 类型字面量赋给 PT 参数
- LSP-907 §2.3 FB_TON 接口规范明确 PT 为 DINT

**结论**: 905 §4.3 示例已过时, 误导开发者使用 TIME 字面量, 必须修订为 DINT 赋值.

🟡 **P1 - §4.1 块结构示例包含 METHODS 语法, 与核心规则表矛盾**

§4.1 (第 163-166 行) 示例使用 `METHODS ... END_METHODS` 声明区, 但 §1 核心规则表 (第 26 行) 注明 "Siemens LSP 插件不支持 METHOD 语法". 此处示例可能误导开发者使用不支持的语法.

🟡 **P1 - §9 相关文档引用过时**

§9 (第 330 行) 引用 `903_Siemens-LSP_Go-Gen_定时器使用规范_DEV.md`, 但实际文件名为 `903_定时器使用规范_LSP.md` (V2.1.0 已从 Go-Gen 方案迁移). 引用路径和名称均过时.

### 3.2 LSP-904 SCL 注释规范 V1.2.0

**规范状态**: 已验证，2026-05-29 更新

**核心规则**:
- §2.0 注释类型分工: 变量/行内用 `//`, 逻辑/流程块用 `(* *)`
- 禁止嵌套注释, 禁止注释内容含 `(*` 或 `*)` 字符串
- 禁止中文标点, 必须英文半角
- region 折叠标记格式: `(* #region ... *)`

**发现的问题**:

🟢 **规范本身质量较高, 内部一致性良好**. V1.2.0 新增的 §2.0 注释类型分工规则清晰, 与实际 SysLib 代码 (FB_1011) 风格一致.

🟡 **P2 - §7.4 region 模板格式与 023 §5.3.2 不一致**

904 §7.4 (第 409 行) 规定 region 格式为 `(* #region ... *)`, 但 023 §5.3.2 (第 196 行) 示例使用 `//#region ...`. 两份规范对 region 标记格式规定不一致, 需统一.

### 3.3 LSP-903 定时器使用规范 V2.1.0

**规范状态**: 已验证，2026-05-31 更新

**核心规则**:
- FB_TON/FB_TONR 来自 SysLib 共享库, PT/ET 为 DINT 类型
- 三段式标准模式 (§3.1): 预赋值 → 全参数调用 → 读输出
- V2.1.0 §3.4: 定时器 `()` 调用必须集中在 FB 顶部无条件批量调用区, 禁止放在 IF/ELSIF/CASE 分支内
- 禁止裸调用, 禁止内联直接传值, 禁止 TIME 字面量

**发现的问题**:

🟢 **规范本身质量最高, 结构完整, 示例丰富**. V2.1.0 的批量无条件调用模式有明确的原理说明和示范案例, 是所有规范中实践指导性最强的.

🔴 **P0 - 903 与 905 §4.3 示例直接冲突** (详见 3.1 节)

🟡 **P1 - §3.4 示例代码中 PT 参数语义说明不够清晰**

§3.4 示例 (第 184 行) `fb_tDebounceExt.PT := i_dDebounceMs;` 中 `i_dDebounceMs` 变量名暗示单位为毫秒, 但 903 §2.1 说明 PT 为 "扫描周期数". 实际 SysLib FB_TON 实现中 PT 是扫描周期计数, 但接口文档 (FB_1011 INT) 第 123 行将 TimeoutMs 描述为 "动作超时时间(ms)". 单位语义存在歧义: PT 到底是毫秒还是扫描周期? 需在规范中明确.

### 3.4 LSP-906 错误预防规则 V1.0.0

**规范状态**: 已验证，2026-05-04 (最旧的规范, 未更新)

**核心规则**:
- §1.1: PT/ET 是 DINT, 禁止 TIME 字面量
- §1.2: 定时器调用必须包含所有参数, Q 不能省略
- §2.1: 禁止修改 `.plc-out` 自动生成文件
- §3.1: `.plc.json` 必须配置 **libraryDirectories**
- §4.1: METHOD 名称不使用 CALL_ 前缀
- §5.1/5.2: 禁止 INT→TIME 隐式转换, 禁止 TIME 字面量赋给 DINT 参数

**发现的问题**:

🔴 **P0 - 严重矛盾: §3.1 使用 `libraryDirectories` 字段名, 与 LSP-907 §1.2 直接冲突**

LSP-906 §3.1 (第 87 行) 规定: ".plc.json 必须配置 libraryDirectories", 并在第 106-108 行示例中使用:
```json
{
  "libraryDirectories": [
    "../01_SharedLibraries/SysLib"
  ]
}
```

但 LSP-907 §1.2 (第 39 行) 明确规定: "**字段名必须为 `libraries`, 不是 `libraryDirectories`(后者不是 Siemens LSP 的有效字段)**", 并在 §1.3 错误表中将 "使用 libraryDirectories(无效字段名)" 列为常见错误.

**结论**: 906 §3.1 的字段名规定是错误的, 与 907 和实际项目配置 (DJ-2026-000 和 SysLib 均使用 `libraries`) 矛盾. 必须修订.

🔴 **P0 - 906 V1.0.0 严重过时, 未覆盖 V2.0+ 实践新问题**

906 V1.0.0 发布于 2026-05-04, 是所有规范中最旧的. 此后 903 经历了 V2.0.0 (2026-05-31) 和 V2.1.0 (2026-05-31) 两次重大修订, 但 906 未同步更新. 缺失内容包括:
- 未覆盖 FB_TONR 使用规范 (仅提及 FB_TON)
- 未覆盖三段式调用模式 (903 V2.0.0 §3.1)
- 未覆盖无条件批量调用模式 (903 V2.1.0 §3.4)
- 未覆盖 E7 错误: 定时器调用放在条件分支内 (903 V2.1.0 新增)
- §3.1 字段名错误 (libraryDirectories vs libraries)
- §6 检查清单未对齐 903 V2.1.0 的新检查项

🟡 **P1 - §1.1 示例变量名 `q_eElapsed` 不符合 905 §3.1 前缀规范**

906 §1.1 (第 28 行) 示例使用 `q_eElapsed` 作为 ET 接收变量, 但 905 §3.1 规定 `q_` 前缀用于 "Query - 查询变量 (只读输出)", 而 ET 是定时器的 OUTPUT. 实际 SysLib 代码使用 `s_dExtDebounceEt` (s_ 前缀 + d 后缀表示 DINT), 符合规范. 906 示例应更新.

### 3.5 LSP-907 项目配置规范 V1.0.0 / 版本历史显示 V1.2.0

**规范状态**: 已验证, 版本历史最新为 V1.2.0 (2026-05-07)

**核心规则**:
- §1.1: `.plc.json` 必填字段 name/description/version/libraries
- §1.2: 字段名必须为 `libraries`, 不是 `libraryDirectories`
- §2: SysLib 共享库引用规范, FB_TON 接口 (PT/ET 为 DINT)
- §3.1: 标准 PLC 项目目录布局 (00_项目管理/01_需求与设计/02_PLC程序/...)
- §5: 多项目共享库访问最佳实践

**发现的问题**:

🔴 **P0 - 版本号不一致: frontmatter 与版本历史矛盾**

文件 frontmatter (第 4 行) 声明 `version: "V1.0.0"`, 但 §6 版本历史 (第 390 行) 显示最新版本为 V1.2.0 (2026-05-07). frontmatter 版本号未同步更新, 会导致规范注册表 (spec_registry) 读取到错误版本.

🟡 **P1 - §3.1 标准目录布局与 DJ-2026-000 实际结构差异较大**

907 §3.1 规定标准布局为 `00_项目管理/01_需求与设计/02_PLC程序/通用ST程序及变量表/...`, 但 DJ-2026-000 实际结构为扁平的 `DB1/FB100/OB1/PRD/Test/` (`.plc.json` 在项目根目录). 不过 `auto-pm plc check` 报告显示 DJ-2026-000 结构检查全部通过 (pass=13), 说明 auto-pm 的检查标准与 907 §3.1 文档描述存在差异. 需确认 907 §3.1 是否为强制要求还是推荐布局.

🟡 **P1 - §2.2 FB_TON 定位规则步骤 1 引用错误字段名**

§2.2 (第 115 行) 步骤 1 写道 "检查 `.plc.json` 是否包含 `libraryDirectories` 配置", 但 §1.2 已明确字段名应为 `libraries`. 此处为内部自相矛盾.

🟢 **§1.2 libraries 字段规定正确, 与实际项目一致**. DJ-2026-000 和 SysLib 的 `.plc.json` 均使用 `libraries` 字段.

### 3.6 PLC-023 PLC 程序设计文档模板 V2.0.0

**规范状态**: stable, 2026-04-25 (基于 DJ-2026-005 项目实践)

**核心规则**:
- §4.4: 三层解耦架构 (主控调度层/业务功能块层/基础服务层)
- §5.3: Region 标记编号体系 (100~900)
- §6.1.5: FB 标准化文件头格式 (8 个必填项)
- §6.4: 定时器/计数器简化命名 (`t` + 功能描述)
- §6.5: IEC 61131-3 ST 语言编程规范
- §15: 代码审查检查清单

**发现的问题**:

🔴 **P0 - 严重矛盾: §6.4.2 和 §6.5.2 使用 TIME 字面量, 与 LSP-903/906 直接冲突**

023 §6.4.2 (第 518 行) 示例:
```st
s_tAction.tPt := T#3S;
```

023 §6.5.2 (第 580 行) 示例:
```st
s_t动作定时器(IN := TRUE, PT := T#2000ms);
```

两处均使用 TIME 字面量 (`T#3S`, `T#2000ms`), 但 903/906 明确禁止 TIME 字面量, 要求 DINT 赋值. 023 作为文档模板, 其示例会直接被开发者模仿, 必须修订.

🔴 **P0 - 严重矛盾: §6.5.2 METHOD 使用 CALL_ 前缀, 与 LSP-905 §2.1 直接冲突**

023 §6.5.2 (第 558 行) 示例:
```st
METHOD CALL_自动模式状态机 : VOID
```

但 905 §2.1 明确规定 "METHOD 名称不应使用 CALL_ 前缀", 并在错误示例中展示 `METHOD CALL_AutoModeStateMachine : VOID` 为禁止写法. 023 的示例恰好是 905 禁止的错误写法.

🔴 **P0 - 严重矛盾: §5.3.2 使用中文变量名, 与 LSP-905 §3.3 直接冲突**

023 §5.3.2 (第 199-206 行) 示例使用中文变量名:
```st
i_b使能     : BOOL;
i_b自动模式 : BOOL;
s_i步序   : INT;
s_t动作定时器 : TON;
```

但 905 §3.3 明确 "禁止中文变量名", 并在错误示例中展示 `运行标志 : BOOL` 为禁止写法. 023 的示例违反 905 强制规则.

🟡 **P1 - §6.4.1 定时器命名前缀与 905 §3.1 不一致**

023 §6.4.1 (第 500 行) 规定定时器实例命名格式为 `t` + 功能描述 (如 `tStartDelay`), 但 905 §3.1 规定 FB 实例使用 `fb_` 前缀 (如 `fb_tActionTimer`). 实际 SysLib 代码 (FB_1011) 使用 `fb_tDebounceExt` (fb_ 前缀), 遵循 905 而非 023. 两份规范对定时器实例命名前缀规定不一致.

🟡 **P1 - §6.4.2 成员访问简写与 903 和实际代码不一致**

023 §6.4.2 (第 514-519 行) 规定成员访问使用简写 `.tIn`/`.tQ`/`.tPt`/`.tEt`, 但 903 和实际 SysLib 代码均使用全名 `.IN`/`.Q`/`.PT`/`.ET`. 023 的简写规范未被任何项目采用, 且与 903 示例矛盾.

🟡 **P1 - §5.3.2 region 标记格式与 904 §7.4 不一致**

023 §5.3.2 (第 196 行) 使用 `//#region 100_VAR_INPUT` 格式, 但 904 §7.4 (第 409 行) 规定 region 格式为 `(* #region ... *)`. 两份规范对 region 标记格式规定不一致.

🟡 **P2 - §5.2 程序调用关系图中 METHOD 命名使用 CALL_ 前缀**

023 §5.2 (第 162-163 行) 调用关系图标注 "METHOD: CALL_自动模式状态机", 同样违反 905 §2.1.

### 3.7 INT-815 PLC 接口文档模板 V1.1.0

**规范状态**: stable, 2026-04-25 更新

**核心规则**:
- §1: 文档基础信息
- §4: 接口列表
- §5: 功能块接口 (输入字段/INOUT 字段/输出字段表格)
- §6: 通信接口 (Modbus/OPC UA)
- §7: 硬件接口
- §8: 错误码说明

**发现的问题**:

🟡 **P1 - 版本号不一致: frontmatter/变更记录与页脚矛盾**

文件 frontmatter (第 5 行) 声明 `version: "V1.1.0"`, §2 变更记录 (第 28 行) 最新为 V1.1.0, 但文末页脚 (第 371 行) 写 `**文档版本**: V1.0.0`. 页脚版本号未同步更新.

🟡 **P2 - 模板章节结构未被 SysLib FB_1011 接口文档严格遵循**

815 模板规定章节为: §1 文档基础信息 / §2 变更记录 / §3 接口概述 / §4 接口列表 / §5 功能块接口 / §6 通信接口 / §7 硬件接口...

但 SysLib FB_1011 接口文档实际章节为: §0 文档基础信息 / §0.1 电磁阀类型定义 / §1 功能概述 / §2 接口定义 / §3 信号处理流水线 / §4 行为逻辑 / §5 接口交互协议 / §6 报警码 / §7 接口版本兼容性说明 / §8 关联文档

FB_1011 接口文档内容质量高, 但章节编号和结构与 815 模板差异较大. 需确认 815 是否为强制模板还是参考结构.

🟢 **815 模板本身内容完整, 覆盖功能块/通信/硬件三类接口**. 输入/输出字段表格设计 (含触发条件列) 实用性强.

### 3.8 PLC 规范间矛盾汇总（6 项直接矛盾）

| 编号 | 矛盾类型 | 涉及规范 | 具体冲突 |
|------|---------|---------|---------|
| C-01 | TIME 字面量 | 905 §4.3 vs 903/906 | 905 示例用 `T#500ms`, 903/906 禁止 |
| C-02 | TIME 字面量 | 023 §6.4.2/§6.5.2 vs 903/906 | 023 示例用 `T#3S`/`T#2000ms`, 903/906 禁止 |
| C-03 | METHOD 命名 | 023 §6.5.2 vs 905 §2.1 | 023 用 `CALL_` 前缀, 905 禁止 |
| C-04 | 中文变量名 | 023 §5.3.2 vs 905 §3.3 | 023 示例用中文变量名, 905 禁止 |
| C-05 | .plc.json 字段名 | 906 §3.1 vs 907 §1.2 | 906 用 `libraryDirectories`, 907 用 `libraries` |
| C-06 | 907 内部矛盾 | 907 §2.2 vs §1.2 | 907 §2.2 步骤 1 引用 `libraryDirectories`, §1.2 禁止 |

### 3.9 项目遵循度核查

#### 3.9.1 DJ-2026-000 项目结构合规性（auto-pm plc check）

运行 `auto-pm -w "<工作空间根>" plc check DJ-2026-000 --json` 结果:
- **pass=13, warn=0, fail=0**
- 所有检查项通过: `.plc.json` 配置、libraries 路径、PM_SESSION、PRD 目录及四件套 (REQ/INT/DSN/TEC)、标准目录结构

#### 3.9.2 DJ-2026-000/FB_ValveControl.scl 遵循度

🔴 **P0 - 变量命名完全不符合 LSP-905 §3.1 前缀规范**

905 §3.1 强制要求 `i_`/`o_`/`s_`/`fb_` 前缀, 但 FB_ValveControl 所有变量均无前缀:

| 实际变量名 | 应为 (905 规范) | 位置 |
|-----------|----------------|------|
| `AutoManual` | `i_bAutoManual` | 第 28 行 VAR_INPUT |
| `OpenCmd` | `i_bOpenCmd` | 第 33 行 VAR_INPUT |
| `CloseCmd` | `i_bCloseCmd` | 第 34 行 VAR_INPUT |
| `OverCurrent` | `i_bOverCurrent` | 第 39 行 VAR_INPUT |
| `OpenLimit` | `i_bOpenLimit` | 第 40 行 VAR_INPUT |
| `CloseLimit` | `i_bCloseLimit` | 第 41 行 VAR_INPUT |
| `FaultReset` | `i_bFaultReset` | 第 46 行 VAR_INPUT |
| `FaultStatus` | `o_bFaultStatus` | 第 53 行 VAR_OUTPUT |
| `ValveOpen` | `o_bValveOpen` | 第 54 行 VAR_OUTPUT |
| `ValveClose` | `o_bValveClose` | 第 55 行 VAR_OUTPUT |
| `ValveState` | `o_iValveState` / `s_iValveState` | 第 56/64 行 |
| `OpenCmd_R` | `s_bOpenCmdR` | 第 67 行 VAR |
| `CloseCmd_R` | `s_bCloseCmdR` | 第 68 行 VAR |
| `FaultLocked` | `s_bFaultLocked` | 第 70 行 VAR |

🔴 **P0 - 重复变量声明 (编译错误风险)**

`ValveState` 同时声明在:
- VAR_OUTPUT (第 56 行): `ValveState : INT := 0;`
- VAR (第 64 行): `ValveState : INT := 0;`

这是重复声明, 在严格编译器下会报错. 且 BEGIN 区 (第 86 行) 写 `#ValveState := 0;` 时无法区分写入哪个变量.

🔴 **P0 - 文件头注释格式不符合 904 §2.0 和 023 §6.1.5**

904 §2.0 规定功能块头部用 `(* *)` 块注释, 023 §6.1.5 规定 FB 源文件开头必须包含标准 `(* *)` 注释块 (8 个必填项). 但 FB_ValveControl.scl 第 1-21 行文件头全部使用 `//` 单行注释, 且缺少 023 §6.1.5 要求的必填项:
- ❌ 缺少 "功能块名称" (标准格式)
- ❌ 缺少 "项目编号"
- ❌ 缺少 "遵循规范" 引用
- ❌ 缺少 "架构特点" 说明

🟡 **P1 - 逻辑/流程块注释使用 `//` 而非 `(* *)`**

🟡 **P1 - 无 Region 标记 (023 §5.3)**

🟡 **P1 - 无定时器使用 (LSP-903 N/A)** — 作为阀门控制功能块, 缺少开阀/关阀超时检测, 存在功能缺陷.

🟢 **标点符号合规**: 全文使用英文半角标点 ✅
🟢 **无 GOTO/标签语法** ✅
🟢 **无中文变量名** ✅ (但缺少前缀)
🟢 **无嵌套注释** ✅

#### 3.9.3 DJ-2026-000/OB1.scl 遵循度

🔴 **P0 - 内联定时器逻辑使用旧版 Go-Gen 计数器方案, 违反 LSP-903 V2.0+**

OB1.scl 第 40-61 行包含两段内联定时器逻辑:
```scl
// 定时器A (回归参考)
IF GlobalVars.Hmibutton[7] THEN
    GlobalVars.Counter_A := GlobalVars.Counter_A + 1;
    IF GlobalVars.Counter_A >= 50 THEN
        GlobalVars.bOut_A := TRUE;
        GlobalVars.Counter_A := 50;
    END_IF;
ELSE
    GlobalVars.bOut_A := FALSE;
    GlobalVars.Counter_A := 0;
END_IF;
```

这是 903 V1.0.0 (已废弃) 的 Go-Gen 纯逻辑计数器方案. 903 V2.0.0+ 已迁移到 SysLib FB_TON/FB_TONR 调用约定, 903 §1.2 明确标注 V1.0.0 为 "已废弃". 该代码违反 903 V2.0+ 规范.

注: 代码注释标注 "回归参考", 说明是保留的旧测试代码. 但从规范遵循度角度, 仍为违规.

🔴 **P0 - 文件头注释格式不符合 904 §2.0 和 023 §6.1.5**

🟡 **P1 - 变量命名不符合 905 §3.1 前缀规范**

🟡 **P1 - 无 Region 标记 (023 §5.3)**

🟢 **标点符号合规** ✅
🟢 **无 GOTO/标签语法** ✅
🟢 **FB 调用示例正确**: OB1 正确调用 FB_ValveControl 和 SysLib 的 FB_1011/FB_1012/FB_1014, 使用 `GlobalVars.` 前缀的全局变量映射, 符合 023 §4.4 IO 解耦原则 ✅

#### 3.9.4 DJ-2026-000 PRD 文档遵循度

🔴 **P0 - REQ.md 内容严重缺失, 仅为骨架**（文档仅 47 行，大部分章节为"待填写"）

🟡 **P1 - 未遵循 023 模板结构**

🔴 **P0 - INT.md 内容严重缺失, 仅为骨架**（文档仅 41 行，接口表全部为"待填写"）

🟡 **P1 - 未遵循 815 模板结构**

#### 3.9.5 SysLib/FB_1011_CylinderControl.scl 遵循度（正面案例）

**这是规范遵循度最高的 FB, 作为正面案例**.

✅ **文件头注释格式合规 (904 §2.0 + 023 §6.1.5)** — 第 1-56 行使用标准 `(* *)` 块注释，包含功能块名称、描述、版本、来源、遵循规范（LSP-905-V1.0.2, LSP-904-V1.2.0, LSP-903-V2.1.0）、适用场景、映射说明、防呆机制、运行模式说明、V9.2.0~V13.0.0 变更记录

✅ **变量命名完全合规 (905 §3.1)** — `i_stCmd` / `q_stSts` / `fb_tDebounceExt` / `fb_tTimeout` / `s_bExtDebounced` / `s_dExtDebounceEt` / `s_iLatchedSolenoidType`

✅ **定时器使用完全合规 (903 V2.1.0)** — 批量调用区在 FB 顶部无条件执行；三段式模式；使用 FB_TON/FB_TONR；PT/ET 为 DINT；无裸调用；定时器调用不在 IF/ELSIF/CASE 分支内

✅ **注释分工合规 (904 §2.0)** — 变量行内注释用 `//`；逻辑/流程块用 `(* *)`；无嵌套注释

✅ **标点符号合规**: 全文英文半角 ✅
✅ **无 GOTO/标签语法** ✅
✅ **无中文变量名** ✅
✅ **无 CALL_ 前缀 METHOD** ✅

🟡 **P2 - 未使用 Region 标记 (023 §5.3)** — 考虑到 023 与 904 对 region 格式规定本身不一致，此项为低优先级

🟡 **P2 - 使用 `VAR_INPUT CONSTANT` 模式, 905 未覆盖** — 第 60 行 `VAR_INPUT CONSTANT` 是防止 FB 内部篡改输入结构体的特殊模式, 905 §4.1 块结构示例未涉及此语法. 建议在 905 中补充说明.

### 3.10 PLC 规范遵循度评级汇总

#### 规范遵循度评分

| 对象 | 905 命名 | 904 注释 | 903 定时器 | 906 错误预防 | 907 配置 | 023 文档头 | 815 接口 | 综合 |
|------|:-------:|:-------:|:---------:|:----------:|:-------:|:---------:|:-------:|:----:|
| FB_1011 (SysLib) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | A |
| FB_ValveControl (DJ-2026-000) | ❌ | ❌ | N/A | 🟡 | ✅ | ❌ | ❌ | D |
| OB1 (DJ-2026-000) | ❌ | ❌ | ❌ | 🟡 | ✅ | ❌ | - | D |

#### 规范质量评分

| 规范 | 内部一致性 | 时效性 | 实践指导性 | 综合评价 |
|------|:---------:|:-----:|:---------:|:-------:|
| LSP-903 V2.1.0 | ✅ | ✅ | ✅ | A (最佳) |
| LSP-904 V1.2.0 | ✅ | ✅ | ✅ | A |
| LSP-905 V1.0.2 | 🟡 (§4.3) | 🟡 (§9) | ✅ | B |
| LSP-907 V1.2.0 | 🟡 (§2.2) | 🟡 (frontmatter) | ✅ | B |
| INT-815 V1.1.0 | ✅ | 🟡 (页脚) | ✅ | B |
| PLC-023 V2.0.0 | ❌ (多处) | 🟡 | ✅ | C (需大修) |
| LSP-906 V1.0.0 | ❌ (§3.1) | ❌ (过时) | 🟡 | D (需重写) |

---

## 4. PM 规范审查发现

### 4.1 CHG-040 变更单模板审查（V2.1.0）

#### 4.1.1 模板章节结构（040 规范定义）

040 模板定义了 12 个一级章节：
- §1 文档基础信息
- §2 版本变更记录
- §3 变更基本信息（3.0 编号与项目、3.1 技术领域、3.2 业务性质、3.3 影响范围、3.4 申请信息）
- §4 变更原因
- §5 变更内容（5.1 变更前、5.2 变更后）
- §6 变更影响分析（**6.1 项目约束影响、6.2 技术领域影响、6.3 变更传播链**）
- §7 变更实施计划
- §8 变更审批（8.1 审批流程、8.2 审批结论）
- §9 变更实施记录
- §10 变更验证（**10.1 验证项清单、10.2 跨领域联动验证、10.3 验证结论**）
- §11 版本详细变更说明
- §12 附录（12.1 填写指南、12.2 参考资料、12.3 联系方式）

#### 4.1.2 auto-pm generator.py 输出结构比对

| 章节 | 040 模板 | generator.py 输出 | 差异 |
|------|----------|------------------|------|
| §1 文档基础信息 | ✓ | ✓（第 43-49 行） | 文档版本号 V1.0.0 ≠ 规范 V2.1.0 |
| §2 版本变更记录 | ✓ | ✓（第 51-55 行） | 一致 |
| §3.0~3.4 基本信息 | ✓ | ✓（第 57-83 行） | §3.4 多出"变更状态"字段（规范未定义） |
| §4 变更原因 | ✓ | ✓（第 84-93 行） | 一致 |
| §5.1/5.2 变更内容 | 含"相关截图/附件"、"预期效果" | 仅"涉及文件/交付物"、"关键参数/配置"（第 96-110 行） | **字段缺失** |
| §6 影响分析 | 6.1/6.2/6.3 三个子表 | **仅输出"（待填写）"**（第 111-113 行） | **结构完全缺失** |
| §7 实施计划 | ✓ | ✓（第 115-119 行） | 一致（空表格） |
| §8.1/8.2 审批 | ✓ | ✓（第 121-131 行） | 一致 |
| §9 实施记录 | ✓ | ✓（第 133-137 行） | 一致（空表格） |
| §10 验证 | 10.1/10.2/10.3 三节 | **仅 10.1/10.2 两节**（第 139-149 行） | **§10.2 跨领域联动验证被跳过，§10.3 验证结论错位为 §10.2** |
| §11 版本详细变更说明 | ✓ | **缺失**，直接跳到 §11 附录 | **章节缺失** |
| §12 附录 | 12.1/12.2/12.3 | §11 附录仅"（待填写）"（第 151-153 行） | **章节编号错位 + 内容缺失** |

#### 4.1.3 关键发现

1. **§6 影响分析结构缺失（P0）**：generator.py 第 111-113 行仅输出 `## 6. 变更影响分析\n\n（待填写）`，未生成 §6.1 项目约束影响表（5 维度×4 级程度）、§6.2 技术领域影响表（7 领域逐项评估）、§6.3 变更传播链（可视化路径+关联变更单清单）的空表格结构。这导致：
   - 用户需手动添加这些表格，违背"开箱即用"原则
   - parser.py 无法从 §6 提取影响分析数据（无结构可解析）
   - 042 §5.4 要求的"跨领域影响评估"无法在变更单中落地

2. **§10 章节编号错位（P1）**：040 模板定义 §10.1 验证项清单、§10.2 跨领域联动验证、§10.3 验证结论，但 generator.py 输出 §10.1 验证项清单、§10.2 验证结论（跳过跨领域联动验证）。这会导致：
   - parser.py 的 `_extract_verification_conclusion` 方法（parser.py 第 428-465 行）在匹配 §10.2 时会匹配到"验证结论"而非规范定义的"跨领域联动验证"
   - 跨领域联动验证环节在生成的变更单中无落脚点

3. **§11 版本详细变更说明缺失（P1）**：generator.py 未生成 §11 版本详细变更说明章节，直接输出 §11 附录（待填写）。040 模板的 §11 是版本详细变更说明（含 V1.0.0/V1.1.0/V2.0.0 等历史版本说明），§12 才是附录。

4. **§3.4 "变更状态"字段为 auto-pm 扩展（P2）**：generator.py 第 82 行在 §3.4 增加 `| 变更状态 | {cr.status} |`，这是 040 模板中没有的字段。这是 auto-pm 为状态持久化（change_service.py 第 597-612 行 `_update_status_field`）而扩展的字段，属于合理实现，但未在 040 模板中定义，导致规范与实现不一致。

5. **文档版本号不一致（P2）**：generator.py 第 47 行输出 `**文档版本**：V1.0.0`，而 040 模板当前版本是 V2.1.0。生成的变更单版本号与规范版本不匹配，影响规范版本追溯。

6. **§5 字段简化（P2）**：generator.py 的 §5.1/5.2 只输出"涉及文件/交付物"和"关键参数/配置"两行，缺少 040 模板中的"相关截图/附件"（§5.1）和"预期效果"（§5.2）字段。

### 4.2 PM-042 变更管理流程规范审查（V2.2.0）

#### 4.2.1 状态机定义（042 §5.2）

042 V2.2.0 §5.2 定义了 12 个状态的状态机（含看板列标识）：
```
pending_analysis → analyzing → pending_approval → approving → 
pending_implementation → implementing → pending_acceptance → accepting → 
completed → archived / closed
rejected → closed
```

看板列状态标识（042 第 116-128 行）：

| 看板列 | 状态标识 |
|--------|----------|
| 待评估 | `pending_analysis` |
| 评估中 | `analyzing` |
| 待审批 | `pending_approval` |
| 审批中 | `approving` |
| 待实施 | `pending_implementation` |
| 实施中 | `implementing` |
| 待验收 | `pending_acceptance` |
| 验收中 | `accepting` |
| 已完成 | `completed` |
| 已关闭 | `closed` |
| 已拒绝 | `rejected` |
| 已归档 | `archived` |

#### 4.2.2 auto-pm STATUS_FLOW 比对（models.py 第 99-111 行）

auto-pm 定义的 STATUS_FLOW：
```python
STATUS_FLOW = {
    "draft": {"submitted"},
    "submitted": {"under_review", "draft"},
    "under_review": {"approved", "conditionally_approved", "rejected", "submitted"},
    "approved": {"implementing"},
    "conditionally_approved": {"implementing"},
    "implementing": {"pending_acceptance", "approved"},
    "pending_acceptance": {"accepting"},
    "accepting": {"completed", "implementing"},
    "completed": {"closed"},
    "rejected": {"draft"},
    "closed": set(),
}
```

#### 4.2.3 状态机对接缺口

| 042 规范状态 | auto-pm 状态 | 对接情况 |
|-------------|-------------|----------|
| pending_analysis | draft | **命名不一致** |
| analyzing | submitted | **命名不一致**（语义偏移） |
| pending_approval | under_review | **命名不一致** |
| approving | （无对应） | **auto-pm 缺少审批中状态** |
| pending_implementation | approved/conditionally_approved | **命名不一致 + auto-pm 多出 conditionally_approved** |
| implementing | implementing | ✓ 一致 |
| pending_acceptance | pending_acceptance | ✓ 一致 |
| accepting | accepting | ✓ 一致 |
| completed | completed | ✓ 一致 |
| closed | closed | ✓ 一致 |
| rejected | rejected | ✓ 一致 |
| archived | （无对应） | **auto-pm 缺少 archived 状态** |
| （无对应） | conditionally_approved | **042 规范未定义此状态** |

#### 4.2.4 关键发现

1. **状态命名体系完全不一致（P0）**：042 V2.2.0 状态机使用 `pending_analysis/analyzing/pending_approval/approving/pending_implementation` 命名，auto-pm 使用 `draft/submitted/under_review/approved` 命名。两套命名体系完全不同，且 auto-pm 代码注释（models.py 第 93-98 行）声称"对齐 PM-042 §5.2 状态机"，但实际命名与规范不一致。这会导致：
   - 变更单文件中写入的状态值（如 `draft`）与 042 规范看板列标识（`pending_analysis`）不匹配
   - 前端看板渲染时无法直接使用 042 规范定义的看板列标识
   - STATUS_LABELS（models.py 第 117-129 行）的中文标签与 042 看板列说明不完全对应

2. **archived 状态缺失（P1）**：042 §5.2 明确定义 `completed → archived` 和 `archived → [*]` 的流转，但 auto-pm 的 STATUS_FLOW 中没有 archived 状态，completed 只能流转到 closed。auto-pm 的 STATUS_LABELS 也没有 archived 标签。这导致变更单无法走归档流程，与 042 规范的"归档是最终状态"要求不符。

3. **conditionally_approved 状态为 auto-pm 扩展（P1）**：auto-pm 定义了 `conditionally_approved`（有条件批准）状态，但 042 V2.2.0 规范中没有此状态。040 模板 §8.2 审批结论中确实有"有条件通过(附条件)"选项，但 042 状态机没有对应的状态节点。这是规范层面的缺口，需要 042 补充定义。

4. **门禁规则不完整（P1）**：
   - 042 §5.4 要求"影响分析：系统自动分析受影响的组件、风险等级和缓解措施"和"跨领域影响评估"，但 auto-pm 的 `_check_transition_guards`（change_service.py 第 660-748 行）没有对 §6 影响分析的校验（因为 generator.py 根本没生成 §6 的结构）
   - 042 §5.4.4 要求"风险等级分为：低（LOW）、中（MEDIUM）、高（HIGH）"和"必须制定相应的缓解措施"，但 auto-pm 没有风险等级字段和缓解措施字段的校验
   - 042 §5.5 要求"审批历史不可删除，只能追加"，auto-pm 的 `_append_to_approval_table` 方法是追加模式（符合规范），但没有校验机制防止外部覆盖

5. **AI辅助开发场景未实现（P2）**：042 V2.1.0 §11 新增了 3 个 AI 辅助开发场景的变更管理流程：
   - §11.1 AI辅助代码生成场景（按差异项数量 </5/5-20/>20 分级审批）
   - §11.2 批量规范同步场景（高/中/低影响评估）
   - §11.3 自动化测试触发场景（单元/集成/回归测试触发规则）
   但 auto-pm 没有实现这些场景的自动化支持，门禁规则中也没有对应的简化流程。

6. **看板状态映射缺失（P2）**：042 §5.2 定义了 12 个看板列状态标识，但 auto-pm 的 STATUS_LABELS 只有 11 个状态标签，且命名与看板列标识不一致。前端看板渲染时需要额外的映射层。

### 4.3 PM-010 通用项目管理规范审查（V1.0.2）

#### 4.3.1 规范内容

010 规范 V1.0.2 共 91 行，内容非常概括，包含 10 个章节：
- §1 文档目的
- §2 适用范围（适用于所有Python和PLC电气工程项目）
- §3 项目管理流程（启动/规划/执行/监控控制/收尾）
- §4 项目管理工具（"使用Python项目管理工具进行项目管理"）
- §5 版本管理（"遵循语义化版本规范"、"使用变更管理模板记录版本变更"）
- §6~§10 质量保证/风险管理/沟通管理/文档管理/附录

#### 4.3.2 关键发现

1. **规范过于简略（P2）**：010 规范作为"通用项目管理规范"总纲，只有 91 行，内容非常概括，没有提供具体的可执行规范条目。auto-pm 的实现实际上是基于 042/043 等更具体的规范，010 规范没有起到指导作用。

2. **适用范围描述与实际不符（P2）**：010 §2 声明"适用于所有Python和PLC电气工程项目的管理过程"，但内容中没有覆盖 PLC 项目的特殊管理要求（如 LSP-907 规范引用）。

3. **PM_SESSION 文件未定义（P2）**：auto-pm 模板生成的 `PM_SESSION_*.md` 文件是 pm-workflow 技能的单一真源（python-tool 模板 PM_SESSION 第 1-65 行），但 010 规范中没有定义这个文件的角色和结构。

### 4.4 PROJ-016 通用项目结构模板审查（V1.0.0）

#### 4.4.1 规范定义的目录结构（016 §4.1）

016 V1.0.0 定义了 11 个顶层目录：
```
项目名称/
├── 00_项目基础信息/
├── 01_项目文档/
├── 02_开发文件/（含 src/、tests/、docs/、scripts/）
├── 03_测试文档/
├── 04_主程序/
├── 05_部署文档/
├── 06_变更管理/          ← 变更管理目录
├── 07_交付文档/
├── 08_技术知识库/
├── 09_文档模板/
└── 10_资源与工具/
```

#### 4.4.2 auto-pm 实际使用的目录路径

| 代码位置 | 路径定义 | 用途 |
|----------|----------|------|
| change_service.py 第 519-524 行 `_get_change_file_path` | `00_项目管理/04_变更管理/01_变更单/CHG-{DOMAIN}/` | 变更单文件存放 |
| path_resolver.py 第 126-131 行 `_CHANGE_SEARCH_PATHS` | PLC: `00_项目管理/04_变更管理/01_变更单`<br>通用: `01_项目文档/03_执行过程/02_变更管理` | 变更单搜索 |
| path_resolver.py 第 189-191 行 `find_ledger_file` | `00_项目管理/04_变更管理/04_变更记录/01_版本变更台帐.md` | 台帐查找 |
| path_resolver.py 第 109-116 行 `_PROJ_SEARCH_PATHS` | PLC: `00_项目管理/01_立项与需求`<br>通用: `00_项目基础信息` | 立项表查找 |

#### 4.4.3 关键发现

1. **变更管理目录路径三套不一致（P0）**：
   - 016 规范定义：`06_变更管理/`
   - auto-pm PLC 项目实现：`00_项目管理/04_变更管理/01_变更单/CHG-{DOMAIN}/`（遵循 PM-043 V2.1.0）
   - auto-pm 通用项目实现：`01_项目文档/03_执行过程/02_变更管理/`
   - **三套路径完全不一致**。auto-pm 实际遵循的是 043 规范（PM-043 V2.1.0）而非 016 规范。016 规范的 `06_变更管理/` 在 auto-pm 中从未使用。

2. **016 规范未覆盖 PLC 项目结构（P1）**：016 V1.0.0 在 2026-03-14 明确"删除所有PLC相关内容，只保留Python部分"（016 第 26 行），但 auto-pm 同时支持 PLC 和 Python 两种技术栈的项目骨架生成。016 规范没有覆盖 PLC 项目的结构要求，PLC 项目结构实际由 LSP-907 规范定义，但 016 没有引用或对接 LSP-907。

3. **python-tool 模板未生成 016 规范要求的完整目录（P1）**：
   - 016 规范要求 11 个顶层目录（00~10）
   - auto-pm python-tool 模板只生成 `00_项目基础信息/`（1 个）+ `<package_name>/`（flat layout 包目录）+ `tests/`
   - 缺失：`01_项目文档/`、`02_开发文件/`（被 flat layout 替代）、`03_测试文档/`（被 tests/ 替代）、`04_主程序/`、`05_部署文档/`、`06_变更管理/`、`07_交付文档/`、`08_技术知识库/`、`09_文档模板/`、`10_资源与工具/`
   - auto-pm python-tool 模板采用 flat layout（包目录直接在根目录），与 016 规范的 `02_开发文件/src/` 嵌套结构不一致

4. **plc-standard 模板目录结构无 016 规范依据（P1）**：
   - plc-standard 模板生成的目录（`02_PLC程序/`、`03_HMI设计/`、`04_变更管理/`、`04_现场调试/`、`PRD/`）在 016 规范中没有定义
   - 这些目录结构来自 LSP-907 规范（PLC 技术栈规范），plc-standard 模板 copier.yml 第 1 行注释"用于生成符合 LSP-907 规范的 PLC 项目骨架"
   - 016 规范作为"通用项目结构模板"没有引用或对接 LSP-907，导致 PLC 项目结构无通用规范依据

5. **PM_SESSION 文件未在 016 规范中定义（P2）**：auto-pm 两个模板都生成 `PM_SESSION_{{ project_id }}.md.jinja` 文件，但 016 规范没有定义这个文件的角色和结构。

### 4.5 auto-pm 变更管理实现与 PM-042 对接分析

#### 4.5.1 状态机对接分析

**状态流转合法性校验**：auto-pm 通过 `validate_status_transition`（models.py 第 198-208 行）校验状态流转合法性，使用 STATUS_FLOW 字典定义允许的流转。该校验机制符合 042 §5.2"变更单只能向前移动到相邻状态，不能跳跃"的要求。

**状态持久化机制**：auto-pm 通过 `_update_status_field`（change_service.py 第 597-612 行）将状态写入 §3.4 "变更状态"字段，parser.py 通过 `_read_explicit_status`（parser.py 第 346-358 行）优先读取该字段。这种持久化机制确保状态在文件读写过程中不丢失，但依赖 auto-pm 扩展的"变更状态"字段（040 模板未定义）。

**状态推断回退机制**：当 §3.4 无显式状态时，parser.py 通过 `_infer_status_from_approval`（parser.py 第 248-281 行）从 §8 审批章节推断状态。这种回退机制兼容旧版变更单，但推断逻辑与 042 状态机命名不一致（如推断出 `approved` 而非 042 的 `pending_implementation`）。

#### 4.5.2 门禁规则对接分析

**已实现的门禁规则**：

| 目标状态 | 门禁条件 | 042 规范依据 |
|----------|----------|-------------|
| submitted | §3 全部填写 + §4 非空 | §5.3 变更申请要求 |
| approved | §8.1 有审批记录 + 审批人非空 | §5.5 审批要求 |
| conditionally_approved | 同 approved + comment 非空 | §5.5 审批要求（040 §8.2 有条件通过） |
| rejected | 审批人 + comment 非空 | §5.5 审批要求 |
| implementing（路径A） | §7 实施计划至少一条任务 | §5.6 实施要求 |
| implementing（路径B返工） | 无额外门禁 | §5.2 验证不通过返工 |
| pending_acceptance | §9 实施记录至少一条 | §5.6 实施完成要求 |
| accepting | 无额外门禁 | §5.7 验证开始 |
| completed | verification_conclusion 必须为"全部通过" | §5.7 验证通过要求 |

**未实现的门禁规则**：

| 042 规范要求 | auto-pm 实现情况 | 缺口 |
|-------------|------------------|------|
| §5.4 影响分析（受影响组件、风险等级、缓解措施） | 未校验 | generator.py 未生成 §6 结构，无法校验 |
| §5.4 跨领域影响评估 | 未校验 | §6.2/6.3 结构缺失 |
| §5.4 风险等级（LOW/MEDIUM/HIGH） | 未校验 | 无风险等级字段 |
| §5.4 缓解措施 | 未校验 | 无缓解措施字段 |
| §5.5 审批历史不可删除 | 追加模式但无防覆盖校验 | 无校验机制 |
| §5.8 变更单存档（01_变更单/对应领域子目录） | 已实现 | ✓ 符合 043 规范 |
| §5.8 版本变更台帐记录（引用模式） | 已实现（ledger_updater.py） | ✓ 符合 043 规范 |

#### 4.5.3 变更单生成器对接分析

**符合 040 模板的部分**：
- §1~§5 章节结构基本符合（除 §5 字段简化、§3.4 扩展字段）
- §7~§9 章节结构符合
- §3.1/3.2/3.3 选择表格渲染符合（使用 ☑/□ 标记）
- 变更编号格式 `CHG-{DOMAIN}-{YYYY}-{XXX}` 符合 040 §3.0

**不符合 040 模板的部分**：
- §6 影响分析结构完全缺失（仅输出"待填写"）
- §10 章节编号错位（跳过 §10.2 跨领域联动验证）
- §11 版本详细变更说明缺失
- §12 附录错位为 §11
- 文档版本号 V1.0.0 ≠ 规范 V2.1.0
- §5 字段简化（缺"相关截图/附件"、"预期效果"）

### 4.6 PM 对接缺口识别（14 项）

#### 4.6.1 P0 级缺口（严重，阻断规范一致性）— 3 项

**缺口 P0-1：042 状态机命名与 auto-pm STATUS_FLOW 完全不一致**
- **规范侧**：042 V2.2.0 §5.2 定义 12 个状态（pending_analysis/analyzing/pending_approval/approving/pending_implementation/implementing/pending_acceptance/accepting/completed/closed/rejected/archived）
- **实现侧**：auto-pm STATUS_FLOW 定义 11 个状态（draft/submitted/under_review/approved/conditionally_approved/rejected/implementing/pending_acceptance/accepting/completed/closed）
- **影响**：变更单文件中写入的状态值与 042 规范看板列标识不匹配；前端看板渲染需额外映射层；auto-pm 代码注释声称"对齐 PM-042 §5.2"但实际未对齐
- **证据**：models.py 第 93-98 行注释"对齐 PM-042 §5.2 状态机"，第 99-111 行 STATUS_FLOW 命名与 042 第 116-128 行看板列标识不一致

**缺口 P0-2：016 变更管理目录路径与 auto-pm 实现不一致**
- **规范侧**：016 §4.1 定义变更管理目录为 `06_变更管理/`
- **实现侧**：auto-pm 使用三套路径（`00_项目管理/04_变更管理/01_变更单/`、`01_项目文档/03_执行过程/02_变更管理/`、`00_项目管理/04_变更管理/04_变更记录/`），均非 016 定义的 `06_变更管理/`
- **影响**：016 规范与 auto-pm 的变更单存放路径完全不一致；auto-pm 实际遵循 043 规范而非 016 规范；016 规范作为"通用项目结构模板"失去指导意义
- **证据**：016 第 52 行 `06_变更管理/`；change_service.py 第 519-524 行 `_get_change_file_path`；path_resolver.py 第 126-131 行 `_CHANGE_SEARCH_PATHS`

**缺口 P0-3：040 模板 §6 影响分析结构在 generator.py 中缺失**
- **规范侧**：040 §6 定义 §6.1 项目约束影响表、§6.2 技术领域影响表、§6.3 变更传播链三个子表
- **实现侧**：generator.py 第 111-113 行仅输出 `## 6. 变更影响分析\n\n（待填写）`
- **影响**：用户需手动添加 §6 表格结构；parser.py 无法从 §6 提取影响分析数据；042 §5.4 要求的"跨领域影响评估"无法在变更单中落地；门禁规则无法校验影响分析
- **证据**：generator.py 第 111-113 行；040 第 104-148 行 §6 完整结构

#### 4.6.2 P1 级缺口（重要，影响功能完整性）— 6 项

**缺口 P1-1：040 模板 §10 章节编号错位**
- **规范侧**：040 §10 定义 §10.1 验证项清单、§10.2 跨领域联动验证、§10.3 验证结论
- **实现侧**：generator.py 第 139-149 行输出 §10.1 验证项清单、§10.2 验证结论（跳过跨领域联动验证）
- **影响**：parser.py `_extract_verification_conclusion`（parser.py 第 428-465 行）匹配 §10.2 时会匹配到"验证结论"而非规范定义的"跨领域联动验证"；跨领域联动验证环节无落脚点
- **证据**：generator.py 第 139-149 行；040 第 180-199 行 §10 完整结构

**缺口 P1-2：040 模板 §11 版本详细变更说明章节缺失**
- **规范侧**：040 §11 是版本详细变更说明（含 V1.0.0/V1.1.0/V2.0.0 历史版本说明），§12 才是附录
- **实现侧**：generator.py 未生成 §11 版本详细变更说明，直接输出 §11 附录（待填写）
- **影响**：生成的变更单缺少版本详细变更说明章节；章节编号错位（附录从 §12 错位为 §11）
- **证据**：generator.py 第 151-153 行；040 第 201-234 行 §11 版本详细变更说明

**缺口 P1-3：016 规范未覆盖 PLC 项目结构**
- **规范侧**：016 V1.0.0 在 2026-03-14 明确"删除所有PLC相关内容，只保留Python部分"
- **实现侧**：auto-pm 同时支持 PLC 和 Python 两种技术栈的项目骨架生成，plc-standard 模板生成 `02_PLC程序/`、`03_HMI设计/`、`04_变更管理/`、`04_现场调试/`、`PRD/` 等目录
- **影响**：PLC 项目结构无通用规范依据；016 规范作为"通用项目结构模板"适用范围受限
- **证据**：016 第 26 行"删除所有PLC相关内容"；plc-standard 模板 copier.yml 第 1 行"用于生成符合 LSP-907 规范的 PLC 项目骨架"

**缺口 P1-4：python-tool 模板未生成 016 规范要求的完整目录结构**
- **规范侧**：016 §4.1 要求 11 个顶层目录（00~10）
- **实现侧**：python-tool 模板只生成 `00_项目基础信息/`（1 个）+ `<package_name>/`（flat layout）+ `tests/`
- **影响**：生成的 Python 项目缺少 `01_项目文档/`、`05_部署文档/`、`06_变更管理/`、`07_交付文档/`、`08_技术知识库/` 等目录；与 016 规范要求不符
- **证据**：python-tool 模板 LS 结果；016 第 36-60 行 11 个顶层目录

**缺口 P1-5：042 archived 状态在 auto-pm 中缺失**
- **规范侧**：042 §5.2 明确定义 `completed → archived` 和 `archived → [*]` 的流转
- **实现侧**：auto-pm STATUS_FLOW 中没有 archived 状态，completed 只能流转到 closed；STATUS_LABELS 也没有 archived 标签
- **影响**：变更单无法走归档流程；与 042 规范的"归档是最终状态"要求不符
- **证据**：models.py 第 99-111 行 STATUS_FLOW 无 archived；042 第 144-148 行状态机图

**缺口 P1-6：042 风险等级和缓解措施字段未在 auto-pm 中实现**
- **规范侧**：042 §5.4.4 要求"风险等级分为：低（LOW）、中（MEDIUM）、高（HIGH）"和"必须制定相应的缓解措施"
- **实现侧**：auto-pm 无风险等级字段和缓解措施字段的定义和校验
- **影响**：042 §5.4 影响分析要求无法在 auto-pm 中落地；门禁规则无法校验风险等级和缓解措施
- **证据**：change_service.py 第 660-748 行 `_check_transition_guards` 无风险等级校验；042 第 184-185 行风险等级要求

#### 4.6.3 P2 级缺口（改进，提升规范覆盖度）— 5 项

**缺口 P2-1：042 AI辅助开发场景未在 auto-pm 中实现**
- **规范侧**：042 V2.1.0 §11 新增 3 个 AI 辅助开发场景（§11.1 AI辅助代码生成、§11.2 批量规范同步、§11.3 自动化测试触发）
- **实现侧**：auto-pm 没有实现这些场景的自动化支持
- **影响**：042 §11 的自动化场景规范无法在 auto-pm 中落地
- **证据**：042 第 377-426 行 §11 完整内容；auto-pm 无对应实现

**缺口 P2-2：010 规范过于简略**
- **规范侧**：010 V1.0.2 共 91 行，内容非常概括
- **实现侧**：auto-pm 的实现基于 042/043 等更具体的规范
- **影响**：010 规范作为"总纲"没有起到指导作用
- **证据**：010 全文 91 行

**缺口 P2-3：PM_SESSION 文件未在 010/016 规范中定义**
- **规范侧**：010/016 规范均未定义 PM_SESSION 文件
- **实现侧**：auto-pm 两个模板都生成 `PM_SESSION_{{ project_id }}.md.jinja` 文件，作为 pm-workflow 技能的单一真源
- **影响**：PM_SESSION 文件的角色和结构无规范依据
- **证据**：python-tool 模板 PM_SESSION 第 1-65 行；plc-standard 模板 PM_SESSION 第 1-48 行；010/016 规范无 PM_SESSION 定义

**缺口 P2-4：generator.py 文档版本号与 040 模板不一致**
- **规范侧**：040 模板当前版本 V2.1.0
- **实现侧**：generator.py 第 47 行输出 `**文档版本**：V1.0.0`
- **影响**：生成的变更单版本号与规范版本不匹配，影响规范版本追溯
- **证据**：generator.py 第 47 行；040 第 4 行 `version: "V2.1.0"`

**缺口 P2-5：040 模板 §3.4 "变更状态"字段为 auto-pm 扩展未在规范中定义**
- **规范侧**：040 §3.4 申请信息表无"变更状态"字段
- **实现侧**：generator.py 第 82 行在 §3.4 增加 `| 变更状态 | {cr.status} |`
- **影响**：规范与实现不一致；该字段是 auto-pm 状态持久化的关键，应在规范中明确定义
- **证据**：generator.py 第 82 行；040 第 67-73 行 §3.4 无"变更状态"字段

---

## 5. spec_registry.json 一致性核查结果

### 5.1 registry 基本信息

- **文件路径**: `00_Obsidian_Base全局规范文件仓库/spec_registry.json`
- **版本**: 1.0.0
- **last_updated**: 2026-05-27
- **workspace_root**: `c:\Users\fubai\Desktop\My_Workspace`
- **specs 条目数**: 共 40 个 spec 条目（含 deprecated/archived）
- **域分布**: pm / plc / python / cross-domain

### 5.2 canonical_path 路径存在性核查（抽样 14 个）

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
| DEV-001 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/00_元规则与治理/001_通用项目名称命名规范_DEV.md` | ✓ | ✓ |
| TOOL-902 | `00_Obsidian_Base全局规范文件仓库/03_执行过程/01_代码开发/02_工具使用规范/902_Git使用指南.md` | ✓ | ✓ |
| PLC-023 | `0100_PLC自动化/00_通用规范/PLC编程/023_PLC程序设计文档模板_PLC.md` | ✓ | ✓ |
| PM-050 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/05_收尾验收/050_通用验收核验报告模板_PM.md` | ✓ | ✓ |

**路径核查结论**: 抽样 14 个 spec 条目，**全部路径存在**，canonical_path 准确率 100%。

### 5.3 frontmatter 与 registry 元数据一致性核查（抽样 5 个）

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

### 5.4 关键缺口

#### 5.4.1 🔴 P0 严重缺口：SW-2026-008 (auto-pm) 未在 registry 注册

Grep 搜索 `SW-2026-008` 在 `spec_registry.json` 中 **无任何匹配**。

但根据 `project-rule.md`："auto-pm（SW-2026-008）" 是当前工作空间的核心工具，且 INT 文档（`002_接口文档_INT.md`）frontmatter 明确标注 `project_id: "SW-2026-008"`。

**影响**: specmgr 无法发现和管理 auto-pm 项目的规范条目；与 SW-2026-006 (SpecMgr)、SW-2026-007 (pm-mgr) 已注册形成对比。

#### 5.4.2 🔴 P0 严重缺口：SW-2026-007 (pm-mgr) 未标记为 deprecated

`spec_registry.json:1265-1283` 中 SW-2026-007 仍为 `lifecycle: stable`，但 `project-rule.md` 明确记载："pm-mgr（SW-2026-007）已被 auto-pm（SW-2026-008）取代"。

**应修改**: `lifecycle: stable` → `deprecated`，并添加 `replaced_by: ["SW-2026-008"]`。

#### 5.4.3 🟡 P1 版本漂移：DEV-801 drift_warning 未修复

`spec_registry.json:1177` 记录：`"drift_warning": "项目级副本DJ-2026-005/01_需求与设计/10_编程及变量规范/801_...版本已演化至V1.0.7，frontmatter版本需同步更新"`。

但 registry 中 DEV-801 的 version 仍为 `V1.0.5`，canonical_path 指向的归档文件 frontmatter 也无 YAML（仅 Markdown 标识 `DEV-V1.0.5`）。drift_warning 自 2026-05-27 记录至今未处理。

#### 5.4.4 🟡 P1 registry 时效性：last_updated 2026-05-27

registry `last_updated` 为 2026-05-27，但 auto-pm V2.0 完成于 2026-06-19（INT 文档创建日期）。registry 未反映 V2.0 后的规范变更。

#### 5.4.5 🟢 P2 结构不一致：aliases 字段未在 frontmatter 同步

4 个 spec（DEV-001, DEV-210, DEV-211, DEV-220）在 registry 中有 aliases，但对应规范文件的 YAML frontmatter 无 aliases 字段。若 specmgr 的 frontmatter 校验要求 aliases 双向同步，则需补充；若 aliases 仅 registry 维护，则无需修改。

---

## 6. 规范缺口识别

### 6.1 Python 侧缺失专项规范

| 缺口编号 | 缺口名称 | 优先级 | 说明 | 建议规范编号 |
|---------|---------|--------|------|------------|
| GAP-01 | **PySide6 GUI 开发规范** | P0 | auto-pm V2.0 采用 PySide6（`pyproject.toml:22` `PySide6>=6.8,<7`），但 210 §16 仅泛泛提及"PyQt/PySide"，未覆盖：Signal/Slot 通信约定、QSS 样式管理、QThread 异步模式、角色-Tab 映射模式、QMainWindow 布局约定。auto-pm INT §15 提及"View 不直接持有其他 View 引用，通过 Signal/Slot 通信""长时间操作使用 QThread"等最佳实践，但这些未沉淀为规范。 | 216_PySide6_GUI开发规范_DEV.md |
| GAP-02 | **Click CLI 开发规范** | P0 | auto-pm 有 20 个 CLI 命令（INT Part A），采用 Click（`pyproject.toml:17` `click>=8.1.7`），但无 Click CLI 设计规范：命令分组约定、`-w` 全局参数位置、Choice 枚举校验、退出码约定、Rich 表格输出格式、子命令嵌套深度。 | 217_Click_CLI开发规范_DEV.md |
| GAP-03 | **GUI 测试规范（pytest-qt）** | P1 | auto-pm 配置 `pytest-qt>=4.4,<5`（`pyproject.toml:47`），09_整改项/ 下有大量 GUI 测试日志（迭代1~4），但 211 §6.5 测试检查清单未覆盖 GUI 测试：qtbot fixture 使用、信号断言、QTimer 延迟、避免真实文件 IO 的 mock 策略。DEV-032 GUI测试方案标准偏方案级，缺 pytest-qt 代码级规范。 | 218_GUI测试规范_DEV.md |
| GAP-04 | **pyproject.toml 打包规范（hatchling 模式）** | P0 | 220 规范仅覆盖 PyInstaller exe 打包，未覆盖 auto-pm 采用的 hatchling + pyproject.toml + PEP 621 打包模式。需补充：`[build-system]` 配置、`[project.scripts]` 入口点、`[dependency-groups]` 开发依赖、`[tool.mypy]` / `[tool.ruff]` / `[tool.pytest]` 工具链配置标准。 | 220 章节扩展或 221_pyproject配置规范_DEV.md |
| GAP-05 | **Pydantic v2 模型规范** | P1 | auto-pm 使用 `pydantic>=2.10.6`（`pyproject.toml:15`），models/ 下有 dto.py/enums.py/project.py 等，但 210 未覆盖 Pydantic v2 模型设计：BaseModel 配置、字段验证器、DTO 与领域模型分离、序列化约定。 | 210 §18 扩展或 219_Pydantic模型规范_DEV.md |
| GAP-06 | **SQLite + Repository 模式规范** | P1 | auto-pm 采用 SQLite 缓存 + Repository 模式（`db/repository.py`, `db/connection.py`），但 210 §14 Service 层架构未覆盖数据访问层：Repository 基类设计、连接池管理、WAL 模式、增量同步策略。 | 210 §14 扩展或 222_数据访问层规范_DEV.md |

### 6.2 Python 侧过时规范条目

| 规范编号 | 过时条目 | 说明 | 建议 |
|---------|---------|------|------|
| 210 §5.2 | "每行代码长度不超过 79 字符" | 现代 Python 项目（ruff/black 默认 88 字符）普遍放宽；auto-pm 实际行长远超 79。PEP 8 本身也建议 99 字符为上限。 | 更新为 "不超过 88 字符（ruff/black 默认），最长不超过 99 字符" |
| 210 §14.1 | "异步优先：耗时操作使用 async/await" | auto-pm V2.0 完全未采用 async，且 GUI 程序通过 QThread 处理耗时操作。规范未考虑 PySide6 的 QThread 替代方案。 | 补充"GUI 程序可使用 QThread 替代 async/await"或降低"异步优先"为"建议" |
| 210 §15.1 | "所有项目级常量必须集中在 `src/core/constants.py`" | auto-pm 采用 `auto_pm/config/app_config.py` 而非 `src/core/constants.py`，路径前缀不适用。 | 更新路径为 "`<package>/config/constants.py` 或 `<package>/core/constants.py`" |
| 210 §16.1 | UI 目录结构示例 `src/ui/widgets/base/`, `src/ui/widgets/editors/` | auto-pm 实际目录更细分（change_center/, global_pages/, navigation/, project_list/, workspace/），且无 src/ 前缀。 | 更新示例为 auto-pm V2.0 实际结构 |
| 215 §4 | 接口列表字段 `URL / 方法(GET/POST/PUT/DELETE)` | 仅适用 REST API，不适用 CLI/Service API。 | 拆分为 REST 变体和 CLI/Service 变体 |
| 220 全文 | PyInstaller exe 打包 | 不适用开发工具类 Python 项目（如 auto-pm 用 hatchling）。 | 补充"Python 包打包模式"章节 |
| 211 §6.2 | "错误处理是否完善"（未明确禁止 `except Exception`） | auto-pm 有 50 处 `except Exception as e`，规范未明确量化阈值。 | 补充"宽泛异常捕获应控制在 X% 以内，关键业务路径必须捕获特定异常" |

### 6.3 PLC 侧规范过时与矛盾

#### 6.3.1 规范间直接矛盾（6 项 P0）

详见 §3.8 节矛盾汇总表（C-01 ~ C-06）。

#### 6.3.2 规范版本过时汇总

| 编号 | 规范 | 问题 | 优先级 |
|------|------|------|--------|
| V-01 | 906 V1.0.0 | 未覆盖 FB_TONR/三段式/批量调用模式, 字段名错误 | P0 |
| V-02 | 905 §4.3 | 定时器示例使用 TIME 字面量, 未对齐 903 V2.1.0 | P0 |
| V-03 | 023 §6.4/§6.5 | 定时器示例/METHOD 命名/变量名均过时 | P0 |
| V-04 | 905 §9 | 相关文档引用路径过时 (903 文件名变更) | P1 |
| V-05 | 907 §2.1 | SysLib 库结构描述不完整 (缺 actuator/communication/types) | P2 |

#### 6.3.3 规范版本号不一致

| 编号 | 规范 | 问题 |
|------|------|------|
| B-01 | 907 | frontmatter V1.0.0 vs 版本历史 V1.2.0 |
| B-02 | 815 | frontmatter V1.1.0 vs 页脚 V1.0.0 |

#### 6.3.4 PLC 规范覆盖缺口

| 编号 | 缺口描述 | 建议补充位置 |
|------|---------|-------------|
| G-01 | `VAR_INPUT CONSTANT` 模式未在 905 中说明 | 905 §4.1 块结构 |
| G-02 | PT 参数单位语义不明 (毫秒 vs 扫描周期) | 903 §2.1 或 907 §2.3 |
| G-03 | 定时器实例命名前缀冲突 (fb_ vs t) 未裁决 | 905 §3.1 或 023 §6.4.1 |
| G-04 | 成员访问简写 (tIn/tQ vs IN/Q) 未裁决 | 023 §6.4.2 或 903 |
| G-05 | region 标记格式冲突 (//#region vs (* #region *)) 未裁决 | 904 §7.4 或 023 §5.3 |
| G-06 | 815 模板章节结构是否强制未明确 | 815 §1 |
| G-07 | 907 §3.1 目录布局是否强制未明确 | 907 §3.1 |

### 6.4 PM 侧对接缺口

PM 侧共识别 14 项对接缺口，详见 §4.6 节（P0×3 / P1×6 / P2×5）。

核心问题归纳：
1. **状态机命名体系不一致**（042 vs auto-pm STATUS_FLOW）
2. **变更管理目录路径三套不一致**（016 vs 043 vs auto-pm 通用项目实现）
3. **040 模板 §6 影响分析结构在 generator.py 中完全缺失**
4. **016 规范未覆盖 PLC 项目结构**（已删除 PLC 内容但 auto-pm 仍生成 PLC 项目）
5. **042 §5.4 风险等级和缓解措施字段未在 auto-pm 中实现**

---

## 7. 修订建议清单

### 7.1 P0 优先级（必须修复，影响规范有效性或工具链运转）

#### 7.1.1 Python 域 P0 建议

| 编号 | 建议项 | 影响范围 | 具体操作 | 建议纳入版本 |
|------|--------|---------|---------|------------|
| PY-P0-01 | **注册 SW-2026-008 (auto-pm) 到 spec_registry.json** | spec_registry.json | 新增 `SW-2026-008` 条目：`canonical_path` 指向 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/README.md`，`version: V2.0.0`，`domain: cross-domain`，`lifecycle: stable`，`tags: ["auto-pm","CLI","GUI","项目管理","跨域"]`，`replaces: ["SW-2026-007"]` | registry 1.0.1 |
| PY-P0-02 | **将 SW-2026-007 (pm-mgr) 标记为 deprecated** | spec_registry.json | 修改 SW-2026-007 条目：`lifecycle: stable` → `deprecated`，添加 `replaced_by: ["SW-2026-008"]`，添加 `drift_warning: "已被 auto-pm (SW-2026-008) 取代，详见 project-rule.md"` | registry 1.0.1 |
| PY-P0-03 | **新增 216_PySide6 GUI 开发规范** | Python 规范体系 | 新建规范，覆盖：Signal/Slot 通信约定、QSS 样式管理、QThread 异步模式、QMainWindow 布局、角色-Tab 映射、View 间解耦。参考 auto-pm V2.0 实践（INT §15 最佳实践） | 216 V1.0.0 |
| PY-P0-04 | **新增 217_Click CLI 开发规范** | Python 规范体系 | 新建规范，覆盖：命令分组、全局参数位置（`-w` 在子命令前）、Choice 枚举校验、退出码约定（0/1）、Rich 表格输出、子命令嵌套深度。参考 auto-pm 20 个 CLI 命令实践 | 217 V1.0.0 |
| PY-P0-05 | **扩展 220 打包规范：补充 pyproject.toml + hatchling 模式** | 220 规范 | 在 220 新增 §18 "Python 包打包模式（pyproject.toml）"章节，覆盖：`[build-system]`、`[project.scripts]`、`[dependency-groups]`、`[tool.mypy/ruff/pytest]` 配置标准。以 auto-pm pyproject.toml 为参考样板 | 220 V2.3.0 |
| PY-P0-06 | **更新 210 §5.2 行长度阈值** | 210 规范 | 将"不超过 79 字符"更新为"不超过 88 字符（ruff/black 默认），最长不超过 99 字符" | 210 V1.2.0 |

#### 7.1.2 PLC 域 P0 建议

| 编号 | 建议项 | 影响范围 | 具体操作 | 建议纳入版本 |
|------|--------|---------|---------|------------|
| PLC-P0-01 | 修订 905 §4.3 定时器调用示例: 将 `PT := T#500ms` 改为 `PT := 500` (DINT), 对齐 903 V2.1.0 | 905 | 修订 §4.3 示例 | 905 V1.0.3 |
| PLC-P0-02 | 修订 906 §3.1: 将 `libraryDirectories` 改为 `libraries`, 对齐 907 §1.2 | 906 | 修订 §3.1 字段名 | 906 V2.0.0 |
| PLC-P0-03 | 修订 906 整体至 V2.0.0: 补充 FB_TONR/三段式/批量调用模式/E7 错误, 对齐 903 V2.1.0 | 906 | 整体重写 | 906 V2.0.0 |
| PLC-P0-04 | 修订 023 §6.4.2: 将 `s_tAction.tPt := T#3S` 改为 DINT 赋值 | 023 | 修订 §6.4.2 示例 | 023 V2.0.1 |
| PLC-P0-05 | 修订 023 §6.5.2: 将 `PT := T#2000ms` 改为 DINT 赋值 | 023 | 修订 §6.5.2 示例 | 023 V2.0.1 |
| PLC-P0-06 | 修订 023 §6.5.2: 将 `METHOD CALL_自动模式状态机` 改为 `METHOD AutoModeStateMachine`, 对齐 905 §2.1 | 023 | 修订 §6.5.2 METHOD 命名 | 023 V2.0.1 |
| PLC-P0-07 | 修订 023 §5.3.2: 将中文变量名改为英文小驼峰 + 前缀, 对齐 905 §3.1/§3.3 | 023 | 修订 §5.3.2 示例 | 023 V2.0.1 |
| PLC-P0-08 | 修订 907 §2.2 步骤 1: 将 `libraryDirectories` 改为 `libraries` | 907 | 修订 §2.2 步骤 1 | 907 V1.2.1 |

#### 7.1.3 PM 域 P0 建议

| 编号 | 建议项 | 影响范围 | 具体操作 | 建议纳入版本 |
|------|--------|---------|---------|------------|
| PM-P0-01 | **统一 042 状态机命名与 auto-pm STATUS_FLOW** | 042 + auto-pm models.py | **推荐方案A（规范侧修订）**：042 V2.3.0 将状态机命名改为 auto-pm 的 `draft/submitted/under_review/approved/conditionally_approved/rejected/implementing/pending_acceptance/accepting/completed/closed/archived`，并补充 `conditionally_approved` 和 `archived` 状态的定义和流转。理由：① auto-pm 命名更符合软件工程惯例；② `conditionally_approved` 在 040 §8.2 已有"有条件通过"选项；③ 042 的 `pending_analysis/analyzing` 区分度不高。涉及：042 §5.2 状态机图、看板列标识、STATUS_LABELS 中文标签；auto_pm/change/models.py（STATUS_FLOW、STATUS_LABELS 注释更新）；auto_pm/change/parser.py（状态推断逻辑） | 042 V2.3.0 |
| PM-P0-02 | **统一 016 变更管理目录路径与 auto-pm 实现** | 016 | 016 V1.1.0 将变更管理目录从 `06_变更管理/` 改为 `00_项目管理/04_变更管理/`（与 043 V2.1.0 和 auto-pm 实现一致），并引用 043 规范作为详细目录结构依据 | 016 V1.1.0 |
| PM-P0-03 | **generator.py 补全 §6 影响分析结构** | auto_pm/change/generator.py | generator.py `render` 方法（第 26-162 行）在 §6 部分补全 040 模板定义的三个子表结构：§6.1 项目约束影响表（5 维度×4 级程度）、§6.2 技术领域影响表（7 领域逐项评估+关联变更单号）、§6.3 变更传播链（可视化路径+关联变更单清单） | auto-pm V2.0.1 |

### 7.2 P1 优先级（应修复，提升规范覆盖度）

#### 7.2.1 Python 域 P1 建议

| 编号 | 建议项 | 影响范围 | 具体操作 | 建议纳入版本 |
|------|--------|---------|---------|------------|
| PY-P1-01 | **更新 210 §14.1 异步优先原则** | 210 规范 | 补充："GUI 程序可使用 QThread 替代 async/await 处理耗时操作"，或将"异步优先"降级为"建议"而非"原则" | 210 V1.2.0 |
| PY-P1-02 | **更新 210 §15.1 常量文件路径** | 210 规范 | 将 `src/core/constants.py` 更新为 `<package>/config/constants.py` 或 `<package>/core/constants.py`，适配现代 Python 包结构 | 210 V1.2.0 |
| PY-P1-03 | **更新 210 §16.1 UI 目录结构示例** | 210 规范 | 用 auto-pm V2.0 实际结构（change_center/global_pages/navigation/project_list/workspace/dialogs/widgets/models）替换过时的 `src/ui/widgets/base/editors/dialogs/` 示例 | 210 V1.2.0 |
| PY-P1-04 | **新增 218_GUI 测试规范（pytest-qt）** | Python 规范体系 | 新建规范，覆盖：qtbot fixture、信号断言（`qtbot.waitSignal`）、QTimer 延迟、mock 文件 IO、避免真实 DB。参考 auto-pm 09_整改项/迭代1~4 测试日志 | 218 V1.0.0 |
| PY-P1-05 | **新增 219_Pydantic v2 模型规范** | Python 规范体系 | 新建规范，覆盖：BaseModel 配置、字段验证器、DTO 与领域模型分离、序列化约定。参考 auto-pm models/ 目录 | 219 V1.0.0 |
| PY-P1-06 | **扩展 210 §14：补充 Repository 数据访问层模式** | 210 规范 | 在 §14 新增 §14.3 "Repository 数据访问层"，覆盖：Repository 基类、连接管理、WAL 模式、增量同步。参考 auto-pm db/ 目录 | 210 V1.2.0 |
| PY-P1-07 | **更新 215 接口文档模板：增加 CLI/Service API 变体** | 215 规范 | 在 §4/§5 增加变体说明："REST API 用 URL/方法；CLI 用命令/语法；Service API 用类/方法签名" | 215 V1.1.0 |
| PY-P1-08 | **更新 211 §6.2：量化宽泛异常捕获阈值** | 211 规范 | 补充："`except Exception` 应控制在总 except 子句的 20% 以内，关键业务路径（Service 层核心方法）必须捕获特定异常" | 211 V1.1.0 |
| PY-P1-09 | **修复 DEV-801 drift_warning** | spec_registry.json + DEV-801 文件 | 为 DEV-801 归档文件补充 YAML frontmatter（`spec_id, title, version, domain, lifecycle: deprecated, replaced_by: [LSP-905]`），或确认 drift_warning 所述的项目级副本 V1.0.7 是否需单独注册 | registry 1.0.1 |
| PY-P1-10 | **更新 spec_registry.json last_updated** | spec_registry.json | 完成 PY-P0-01/PY-P0-02 后，将 `last_updated` 更新为当前日期 | registry 1.0.1 |

#### 7.2.2 PLC 域 P1 建议

| 编号 | 建议项 | 影响范围 | 具体操作 | 建议纳入版本 |
|------|--------|---------|---------|------------|
| PLC-P1-01 | 修订 907 frontmatter version: 从 V1.0.0 更新为 V1.2.0 | 907 | 修订 frontmatter | 907 V1.2.1 |
| PLC-P1-02 | 修订 815 页脚版本: 从 V1.0.0 更新为 V1.1.0 | 815 | 修订页脚 | 815 V1.1.1 |
| PLC-P1-03 | 修订 905 §9: 更新 903 引用路径为 `903_定时器使用规范_LSP.md` | 905 | 修订 §9 引用 | 905 V1.0.3 |
| PLC-P1-04 | 裁决定时器实例命名前缀: 统一为 `fb_t` (fb_ 前缀, 符合 905 §3.1), 更新 023 §6.4.1 | 905, 023 | 裁决并更新 | 023 V2.0.1 |
| PLC-P1-05 | 裁决定时器成员访问: 统一为全名 `.IN`/`.Q`/`.PT`/`.ET` (符合 903 和实际代码), 更新 023 §6.4.2 | 023, 903 | 裁决并更新 | 023 V2.0.1 |
| PLC-P1-06 | 裁决 region 标记格式: 统一为 `(* #region ... *)` (符合 904 §7.4), 更新 023 §5.3.2 | 904, 023 | 裁决并更新 | 023 V2.0.1 |
| PLC-P1-07 | 修订 906 §1.1 示例变量名: `q_eElapsed` 改为 `s_dElapsed` (s_ 前缀 + d 后缀 DINT) | 906 | 修订示例 | 906 V2.0.0 |
| PLC-P1-08 | 修订 905 §4.1: 补充 `VAR_INPUT CONSTANT` 模式说明 | 905 | 补充说明 | 905 V1.0.3 |
| PLC-P1-09 | 明确 903 PT 参数单位语义: 是毫秒还是扫描周期数 | 903 | 明确语义 | 903 V2.1.1 |
| PLC-P1-10 | 修订 DJ-2026-000/FB_ValveControl.scl: 添加 i_/o_/s_ 前缀 | DJ-2026-000 | 修订代码 | DJ-2026-000 V2.0.1 |
| PLC-P1-11 | 修订 DJ-2026-000/FB_ValveControl.scl: 修复 ValveState 重复声明 | DJ-2026-000 | 修订代码 | DJ-2026-000 V2.0.1 |
| PLC-P1-12 | 修订 DJ-2026-000/FB_ValveControl.scl: 文件头改为 `(* *)` 块, 补充 023 §6.1.5 必填项 | DJ-2026-000 | 修订代码 | DJ-2026-000 V2.0.1 |
| PLC-P1-13 | 修订 DJ-2026-000/OB1.scl: 内联定时器逻辑改为 FB_TON 调用, 对齐 903 V2.1.0 | DJ-2026-000 | 修订代码 | DJ-2026-000 V2.0.1 |
| PLC-P1-14 | 修订 DJ-2026-000/OB1.scl: 文件头改为 `(* *)` 块, 补充 023 §6.1.5 必填项 | DJ-2026-000 | 修订代码 | DJ-2026-000 V2.0.1 |
| PLC-P1-15 | 补充 DJ-2026-000 PRD/REQ.md 和 INT.md 内容, 对齐 023/815 模板 | DJ-2026-000 | 补充文档 | DJ-2026-000 V2.0.1 |

#### 7.2.3 PM 域 P1 建议

| 编号 | 建议项 | 影响范围 | 具体操作 | 建议纳入版本 |
|------|--------|---------|---------|------------|
| PM-P1-01 | **generator.py 修正 §10 章节编号** | auto_pm/change/generator.py + parser.py | generator.py 第 139-149 行将 §10 改为三节结构：§10.1 验证项清单、§10.2 跨领域联动验证、§10.3 验证结论；parser.py `_extract_verification_conclusion` 方法适配 §10.3 | auto-pm V2.0.1 |
| PM-P1-02 | **generator.py 补全 §11 版本详细变更说明** | auto_pm/change/generator.py | generator.py 在 §10 之后、附录之前补全 §11 版本详细变更说明章节，附录改为 §12 | auto-pm V2.0.1 |
| PM-P1-03 | **016 规范补充 PLC 项目结构定义** | 016 | 016 V1.1.0 恢复 PLC 项目结构定义，或引用 LSP-907 规范作为 PLC 项目结构的详细依据，使 016 规范覆盖 PLC 和 Python 两种技术栈 | 016 V1.1.0 |
| PM-P1-04 | **python-tool 模板补全 016 规范要求的目录结构** | templates/python-tool + 016 | python-tool 模板补全 016 规范要求的目录（至少 `06_变更管理/`、`07_交付文档/`、`08_技术知识库/`），或在 016 规范中明确 Python 项目可简化哪些目录 | auto-pm V2.0.1 + 016 V1.1.0 |
| PM-P1-05 | **auto-pm 补充 archived 状态** | auto_pm/change/models.py | auto-pm STATUS_FLOW 补充 `archived` 状态，定义 `completed → archived` 流转；STATUS_LABELS 补充 `archived: "已归档"` 标签 | auto-pm V2.0.1 |
| PM-P1-06 | **auto-pm 实现风险等级和缓解措施字段** | 040 + auto-pm generator/parser/change_service | 040 模板 §6.1 项目约束影响表增加"风险等级"和"缓解措施"字段；auto-pm generator.py 在 §6.1 表格中渲染风险等级和缓解措施字段；parser.py 解析；`_check_transition_guards` 增加 submitted 状态的风险等级校验 | 040 V2.2.0 + auto-pm V2.0.1 |

### 7.3 P2 优先级（可优化，提升规范一致性）

#### 7.3.1 Python 域 P2 建议

| 编号 | 建议项 | 影响范围 | 具体操作 | 建议纳入版本 |
|------|--------|---------|---------|------------|
| PY-P2-01 | **同步 aliases 字段到 frontmatter** | 4 个规范文件 | 若 specmgr 要求 aliases 双向同步，则为 DEV-001/DEV-210/DEV-211/DEV-220 的 frontmatter 补充 `aliases` 字段；若仅 registry 维护，则在 210 规范中说明 | 210 V1.2.0 |
| PY-P2-02 | **210 §12 类型注解：提升为 strict 要求** | 210 规范 | 将"使用类型提示"更新为"使用类型提示且启用 mypy strict 模式"，对齐 auto-pm 实践 | 210 V1.2.0 |
| PY-P2-03 | **211 §7.1 工具清单更新** | 211 规范 | 补充 ruff（替代 flake8 + black 的现代工具）、mypy strict、pytest-qt、safety 等工具，对齐 auto-pm pyproject.toml 工具链 | 211 V1.1.0 |
| PY-P2-04 | **220 §13 章节编号修复** | 220 规范 | 220 规范 §13 标题为"常见问题"但内部子节编号为 12.1~12.7（`220:570-663`），且 §12.6 重复出现两次（`220:618` 和 `220:641`），需修复编号 | 220 V2.3.0 |
| PY-P2-05 | **220 §14 版本变更说明编号错乱** | 220 规范 | §14 内部出现 V2.1.0/V1.0.0/V1.1.0/V1.2.0 锚点（`220:1067-1100`），但 §2 版本变更记录中 V2.0.0/V2.1.0/V2.2.0 才是最新，锚点顺序混乱需整理 | 220 V2.3.0 |
| PY-P2-06 | **210 §17.2 常见问题解决方案表** | 210 规范 | 补充"宽泛异常捕获"行：问题=捕获 Exception，解决方案=捕获特定异常并记录日志，示例=`except (OSError, json.JSONDecodeError) as e` | 210 V1.2.0 |

#### 7.3.2 PLC 域 P2 建议

| 编号 | 建议项 | 影响范围 | 具体操作 | 建议纳入版本 |
|------|--------|---------|---------|------------|
| PLC-P2-01 | 修订 907 §2.1: 补充 SysLib 实际目录结构 (actuator/communication/types) | 907 | 修订 §2.1 | 907 V1.2.1 |
| PLC-P2-02 | 修订 SysLib/.plc.json: 统一为标准 JSON 缩进格式 | SysLib | 修订 .plc.json 格式 | SysLib V1.0.1 |
| PLC-P2-03 | 明确 815 模板章节结构是否为强制要求 | 815 | 明确强制性 | 815 V1.1.1 |
| PLC-P2-04 | 明确 907 §3.1 目录布局是否为强制要求 | 907 | 明确强制性 | 907 V1.2.1 |
| PLC-P2-05 | 修订 023 §5.2 调用关系图: 移除 METHOD 的 CALL_ 前缀 | 023 | 修订 §5.2 | 023 V2.0.1 |
| PLC-P2-06 | 修订 905 §4.1: 确认 METHODS/END_METHODS 语法是否支持, 或移除示例 | 905 | 修订 §4.1 | 905 V1.0.3 |
| PLC-P2-07 | 统一 .plc.json version 字段格式: 是否需要 V 前缀 (V2.0.0 vs 2.0.0) | 907 | 统一格式 | 907 V1.2.1 |

#### 7.3.3 PM 域 P2 建议

| 编号 | 建议项 | 影响范围 | 具体操作 | 建议纳入版本 |
|------|--------|---------|---------|------------|
| PM-P2-01 | **auto-pm 实现 042 §11 AI辅助开发场景** | auto_pm/change/ | auto-pm 实现 042 §11 定义的 3 个 AI 辅助开发场景的自动化支持：§11.1 AI辅助代码生成场景（差异项数量分级审批）、§11.2 批量规范同步场景（影响评估+同步记录）、§11.3 自动化测试触发场景（测试类型触发规则） | auto-pm V2.1.0 |
| PM-P2-02 | **010 规范补充可执行条目** | 010 | 010 V1.1.0 补充具体的可执行规范条目，引用 042/043/016 等具体规范作为详细依据，使 010 规范起到总纲指导作用 | 010 V1.1.0 |
| PM-P2-03 | **010/016 规范定义 PM_SESSION 文件角色** | 010 或 016 | 010 或 016 规范补充 PM_SESSION 文件的定义，包括角色（pm-workflow 技能单一真源）、结构（9 个章节）、命名规则（`PM_SESSION_<project_id>.md`） | 010 V1.1.0 或 016 V1.1.0 |
| PM-P2-04 | **generator.py 文档版本号对齐 040 模板** | auto_pm/change/generator.py | generator.py 第 47 行将 `**文档版本**：V1.0.0` 改为 `**文档版本**：V2.1.0`（或动态读取 040 模板版本号） | auto-pm V2.0.1 |
| PM-P2-05 | **040 模板 §3.4 定义"变更状态"字段** | 040 | 040 V2.2.0 在 §3.4 申请信息表中增加"变更状态"字段定义，明确该字段由 auto-pm 状态流转时自动写入，值为 STATUS_FLOW 中的合法状态标识 | 040 V2.2.0 |

### 7.4 修订建议统计汇总

| 优先级 | Python 域 | PLC 域 | PM 域 | 合计 |
|--------|----------|--------|--------|------|
| P0（严重） | 6 | 8 | 3 | **17** |
| P1（重要） | 10 | 15 | 6 | **31** |
| P2（改进） | 6 | 7 | 5 | **18** |
| **合计** | **22** | **30** | **14** | **66** |

---

## 8. 范围边界确认

### 8.1 已完成的工作

#### 8.1.1 Python 域审查工作
- ✅ 阅读 4 份 Python 规范文件（210/211/215/220）完整内容
- ✅ 阅读 3 份 auto-pm V2.0 代码样本（main_window.py / project_service.py / change_service.py）
- ✅ 阅读 auto-pm INT 文档（002_接口文档_INT.md）和 pyproject.toml
- ✅ 阅读 spec_registry.json 完整内容（40 个 spec 条目）
- ✅ 抽样核查 14 个 spec 条目的 canonical_path 路径存在性（100% 存在）
- ✅ 抽样核查 5 个规范文件的 YAML frontmatter 与 registry 元数据一致性
- ✅ Grep 扫描 auto-pm 代码的 async/except Exception 模式
- ✅ 识别 6 个 Python 规范缺口 + 7 个过时条目
- ✅ 输出 6 条 P0 + 10 条 P1 + 6 条 P2 修订建议

#### 8.1.2 PLC 域审查工作
- ✅ 读取并分析 7 份 PLC 规范文件 (LSP-905/904/903/906/907 + 023/815)
- ✅ 核查 DJ-2026-000 项目 (FB_ValveControl.scl/OB1.scl/.plc.json/PRD) 遵循度
- ✅ 核查 SysLib 项目 (FB_1011_CylinderControl.scl/.plc.json/PRD) 遵循度
- ✅ 运行 `auto-pm plc check DJ-2026-000 --json` 获取结构合规性报告
- ✅ 识别 6 项规范间直接矛盾 (C-01 ~ C-06)
- ✅ 识别 5 项规范版本过时问题 (V-01 ~ V-05)
- ✅ 识别 2 项版本号不一致问题 (B-01 ~ B-02)
- ✅ 识别 7 项规范覆盖缺口 (G-01 ~ G-07)
- ✅ 输出 30 项修订建议 (P0×8 / P1×15 / P2×7)

#### 8.1.3 PM 域审查工作
- ✅ 阅读 4 份 PM 规范文件（040/042/010/016）+ 1 份辅助规范（043）完整内容
- ✅ 阅读 auto-pm V2.0 变更管理实现代码（generator.py / change_service.py / models.py / parser.py / path_resolver.py）
- ✅ 阅读 auto-pm 项目骨架模板（python-tool / plc-standard 的 copier.yml + PM_SESSION 模板）
- ✅ 比对 040 模板与 generator.py 输出结构（12 个章节逐项对照）
- ✅ 比对 042 状态机与 auto-pm STATUS_FLOW（12 个状态逐项对照）
- ✅ 比对 016 目录结构与 auto-pm 实际使用的三套路径
- ✅ 分析 auto-pm 门禁规则与 042 §5.4/§5.5 要求的对接情况
- ✅ 识别 14 项 PM 对接缺口（P0×3 / P1×6 / P2×5）
- ✅ 输出 14 项修订建议（P0×3 / P1×6 / P2×5）

#### 8.1.4 spec_registry.json 一致性核查工作
- ✅ 阅读 spec_registry.json 完整内容（40 个 spec 条目）
- ✅ 抽样核查 14 个 spec 条目的 canonical_path 路径存在性（100% 存在）
- ✅ 抽样核查 5 个规范文件的 YAML frontmatter 与 registry 元数据一致性
- ✅ 识别 2 项 P0 严重缺口（SW-2026-008 未注册、SW-2026-007 未标记 deprecated）
- ✅ 识别 2 项 P1 版本漂移/时效性问题（DEV-801 drift_warning 未修复、registry last_updated 过时）
- ✅ 识别 1 项 P2 结构不一致问题（aliases 字段未在 frontmatter 同步）

### 8.2 未做的事项（范围边界）

#### 8.2.1 未修改的内容
- ❌ **未修改任何规范文件本身**（Python: 210/211/215/220；PLC: LSP-905/904/903/906/907 + 023/815；PM: 040/042/043/010/016）
- ❌ **未修改 spec_registry.json**（仅审查，未注册 SW-2026-008，未改 SW-2026-007 状态，未修复 DEV-801 drift_warning）
- ❌ **未修改任何 auto-pm 代码文件**（仅阅读分析 generator.py / change_service.py / models.py / parser.py / path_resolver.py / project_service.py / main_window.py 等）
- ❌ **未修改任何项目源码**（DJ-2026-000/SysLib 的 .scl/.plc.json/PRD 文件保持原样）
- ❌ **未创建新规范文件**（216/217/218/219/221/222 仅作为建议提出，未实际创建）
- ❌ **未修改任何配置文件**（pyproject.toml / copier.yml 等保持原样）

本次审查为**纯只读分析**，所有修订建议均记录在本报告中，待项目负责人确认后再执行修订。

#### 8.2.2 未涵盖的范围
- 未审查 LSP-908（Siemens Language Support 使用指南 TOOL），因任务子任务未要求
- 未审查 SysLib 的 FB_1012/FB_1013/FB_1014/FB_1020 等其他 FB 的遵循度（仅以 FB_1011 为代表）
- 未审查 DJ-2026-000 的 Test/ 目录测试用例
- 未审查 SysLib 的 timer/counter/edge/convert 等基础库 FB
- 未涉及 041（版本变更台帐模板）与 auto-pm ledger_updater.py 的详细对接审查
- 未涉及 044/045（变更管理文档版本控制/流程执行指南）的审查
- 未涉及 auto-pm UI 层（ui/ 目录）与规范对接的详细审查
- 未涉及 auto-pm DB 层（db/ 目录）与规范对接的详细审查
- GlobalVars.db 为二进制文件，无法直接读取分析

### 8.3 审查限制

1. **代码样本有限**：Python 域仅深度阅读 3 个核心代码文件（main_window.py / project_service.py / change_service.py），未覆盖 db/、cli/、plc/、models/ 等全部模块，规范遵循度评估基于样本推断
2. **frontmatter 核查样本有限**：仅核查 5 个规范文件的 frontmatter，未覆盖全部 40 个 spec 条目
3. **未运行时验证**：除 `auto-pm plc check DJ-2026-000 --json` 外，未实际运行 specmgr check / specmgr frontmatter / auto-pm 其他命令验证工具链一致性
4. **DEV-801 项目级副本未核查**：drift_warning 提及的 `DJ-2026-005/01_需求与设计/10_编程及变量规范/801_...` 路径未实际核查
5. **PLC 项目遵循度样本有限**：仅以 FB_1011（SysLib 正面案例）和 FB_ValveControl/OB1（DJ-2026-000 反面案例）为代表，未覆盖所有 FB
6. **PM 对接审查聚焦变更管理**：仅审查变更管理（change/）模块与 040/042/043 的对接，未审查 project_service.py 与 010/016 的全面对接
7. **规范版本号核查基于 frontmatter**：部分规范文件（如 DEV-801）无 YAML frontmatter，仅能通过 Markdown 文档标识核查版本，可能存在遗漏

### 8.4 建议后续工作

1. **优先处理 P0 级建议（17 项）**：确保规范有效性、工具链运转和规范一致性
   - Python 域 P0×6：注册 SW-2026-008、deprecated SW-2026-007、新增 216/217 规范、扩展 220、更新 210 §5.2
   - PLC 域 P0×8：修订 905/906/023/907 的直接矛盾和严重过时问题
   - PM 域 P0×3：统一 042 状态机命名、统一 016 变更管理目录、补全 generator.py §6 结构
2. **在 P0 修复后处理 P1 级建议（31 项）**：提升规范覆盖度和功能完整性
3. **根据资源情况处理 P2 级建议（18 项）**：提升规范一致性和细节完善
4. **同步更新 spec_registry.json**：在修订规范时同步更新版本号、last_updated、lifecycle 状态
5. **补充单元测试用例**：在修订 auto-pm 代码后补充对应的单元测试，确保不引入回归
6. **建立规范版本漂移监控**：定期运行 `specmgr check` 和 `specmgr frontmatter` 检测版本漂移

---

## 附录：审查统计汇总

### A.1 修订建议统计

| 优先级 | Python 域 | PLC 域 | PM 域 | 合计 |
|--------|----------|--------|--------|------|
| P0（严重） | 6 | 8 | 3 | **17** |
| P1（重要） | 10 | 15 | 6 | **31** |
| P2（改进） | 6 | 7 | 5 | **18** |
| **合计** | **22** | **30** | **14** | **66** |

### A.2 规范遵循度评级汇总

| 域 | 规范/对象 | 评级 | 关键问题 |
|----|----------|------|---------|
| Python | 210 编程规范 | 🟡 部分遵循 | 3 处偏离（常量集中、异步优先、行长度） |
| Python | 211 代码审查规范 | 🟢 基本符合 | 1 处偏离（宽泛异常捕获 50 处） |
| Python | 215 接口文档模板 | 🟢 符合 | 模板对 CLI/Service API 适配不足 |
| Python | 220 打包规范 | 🔴 不适用 | 规范与实际打包模式不匹配（exe vs hatchling） |
| PLC | LSP-903 V2.1.0 | ✅ A（最佳） | 规范质量最高 |
| PLC | LSP-904 V1.2.0 | ✅ A | 内部一致性良好 |
| PLC | LSP-905 V1.0.2 | 🟡 B | §4.3 示例过时、§9 引用过时 |
| PLC | LSP-907 V1.2.0 | 🟡 B | frontmatter 版本号不一致、§2.2 内部矛盾 |
| PLC | INT-815 V1.1.0 | 🟡 B | 页脚版本号不一致 |
| PLC | PLC-023 V2.0.0 | 🔴 C（需大修） | 多处直接矛盾（TIME 字面量、CALL_ 前缀、中文变量名） |
| PLC | LSP-906 V1.0.0 | 🔴 D（需重写） | §3.1 字段名错误、整体过时未覆盖 V2.0+ 实践 |
| PLC | FB_1011 (SysLib) | ✅ A | 正面案例，规范遵循度最高 |
| PLC | FB_ValveControl (DJ-2026-000) | 🔴 D | 命名/注释/文档头全面不合规 |
| PLC | OB1 (DJ-2026-000) | 🔴 D | 内联定时器逻辑违反 903 V2.0+ |
| PM | 040/042/010/016 | 🔴 对接缺口 | 14 项对接缺口（P0×3 / P1×6 / P2×5） |
| 注册表 | spec_registry.json | 🟡 基本一致 | 2 处严重缺口 + 1 处版本漂移未修复 |

### A.3 直接矛盾与缺口统计

| 类型 | 数量 | 编号范围 |
|------|------|---------|
| PLC 规范间直接矛盾 | 6 项 | C-01 ~ C-06 |
| PLC 规范版本过时 | 5 项 | V-01 ~ V-05 |
| PLC 版本号不一致 | 2 项 | B-01 ~ B-02 |
| PLC 规范覆盖缺口 | 7 项 | G-01 ~ G-07 |
| Python 规范缺口 | 6 项 | GAP-01 ~ GAP-06 |
| Python 过时条目 | 7 项 | - |
| PM 对接缺口 | 14 项 | P0×3 / P1×6 / P2×5 |
| spec_registry 缺口 | 5 项 | P0×2 / P1×2 / P2×1 |

---

**报告生成时间**：2026-06-21
**审查人**：规范审查专家（Trae AI 辅助）
**报告版本**：V1.0.0
**审查类型**：规范体系遵循度与一致性审查（只读分析）
**工作空间根**：`c:\Users\fubai\Desktop\My_Workspace`
**整合来源**：
- Python 规范审查报告（python_spec_audit.md）
- PLC 规范审查报告（plc_spec_audit.md）
- PM 规范审查报告（pm_spec_audit.md）

**本报告为纯只读分析输出，未修改任何规范文件、代码文件或配置文件。所有修订建议待项目负责人确认后再执行。**