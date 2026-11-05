# SW-2026-005 PLC项目管理工具 — V8.0.0 全栈重构技术方案

**诊断日期**: 2026-06-03  
**诊断范围**: 完整源码审计（backend ~40 .py文件, frontend ~30 .js/.css文件, 28 测试文件）  
**诊断立场**: 长期架构可持续演进，不追求短期上线  
**参照基准**: V7.0.0架构设计文档、210 Python编码规范、project-rule全局开发规则

---

## 一、现状：V6.0.0 技术债务全景图

### 1.1 架构实现 vs 设计偏差

项目有一份优秀的 [V7.0.0架构设计文档](file:///c:/Users/fubai/Desktop/My_Workspace/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-005_PLC项目管理工具/01_项目文档/02_规划过程/007_架构设计文档_ARCH-V7.0.0.md)，定义了清晰的三层架构（Presentation → Service → Core → Infrastructure）和 6 条核心设计原则。但实际代码与设计的差距巨大：

| V7.0.0 设计目标 | 当前实现状态 | 完成度 |
|:--|:--|:--|
| Repository 数据访问层 | 0% — Service 直接 `open()`/`rglob()` 操作文件系统 | 0% |
| APIGateway 统一 IPC | `api_gateway.py` 框架已写，但 IPCBridge（1700行）仍在用 | 20% |
| 单一真源枚举 | `_DescribedEnum` 基类已建立，但 `BUSINESS_LINE_DESC` 等映射表未删除 | 60% |
| 前端模块化 | `state.js` 有集中 Store，但 50+ 全局函数仍在 `window` 上 | 25% |
| CSS 变量体系 | `variables.css` 定义了变量，但 570+ 行内联 `style="..."` 未消除 | 20% |
| 异常层次全覆盖 | `PLCToolError` 体系已建立，但 services 仍有 92 处 broad Exception | 70% |
| `except: pass` 清零 | 已完成 — 搜索未发现暴力 pass 模式 | 100% |
| **加权平均** | | **~35%** |

### 1.2 核心病灶清单

#### 病灶 A：依赖管理彻底失控
```
requirements.txt 声明:
  PyQt5 + QScintilla          ← 完全不使用
  loguru                       ← 代码用标准 logging
  pydantic                     ← 无任何 import
  pytest-qt                    ← 无 Qt 测试

实际运行时依赖（全部 vendorized 在 lib/）:
  pywebview + cffi + pythonnet + clr_loader + pycparser  ← 无版本追溯
  bottle.py × 2 (lib/bottle.py + lib/bin/bottle.py)      ← 重复副本
  proxy_tools/                                             ← 用途不明
```

`pip install -r requirements.txt` 会安装一堆无用的 Qt 库，而真正的运行时依赖根本无法通过 pip 管理。

#### 病灶 B：IPC 桥接 1700 行巨石类

`webview_window.py` 中的 `IPCBridge` 类包含：
- ~40 个 API 方法与 35+ deprecated wrapper
- 硬编码的 Mock 数据（`MOCK_PROJECTS`、`MOCK_CHECKERS` 等）
- 4 条独立的 `_safe_call` 执行链
- 直接 import Service 并调用内部方法
- 与 `api_gateway.py` 的 `APIGateway` 功能完全重复

#### 病灶 C：前端无工程化

- **50+ 全局函数**：`window.switchTab`、`window.openChangeModal`、`window.renderProjectOverview` 等全部裸露在全局作用域
- **innerHTML 拼接渲染**：每处 HTML 生成都是字符串拼接，无模板、无组件、无类型检查
- **无构建工具**：JS 文件通过 `<script>` 标签按加载顺序隐式依赖（`utils.js` → `state.js` → `api.js` → `router.js` → 各 view）
- **CSS 体系断裂**：虽有 CSS 自定义变量体系规划，实际 570+ 行内联 `style="..."` 导致主题无法统一切换

#### 病灶 D：版本号三处不一致
- `config.py:13` → `VERSION = "1.0.0"`（死代码）
- `src/core/constants.py` → `VERSION = "6.0.0"`（CLI 使用）
- `config/app_config.json` → `"version": "6.0.0"`（ConfigLoader 读这里）

#### 病灶 E：配置系统碎片化
存在 3 套并发配置加载器：
1. `config.py/ConfigLoader` — 从 app_config.json 加载
2. `src/core/config.py/ConfigLoader` — 另一套实现，路径计算方式不同
3. `data/settings.json` — 运行时用户设置

两套 `ConfigLoader` 都有 `load()`/`get()`/`save()` 方法但互不知晓对方的存在。

#### 病灶 F：前端 XSS 风险
变更单内容是用户编辑的 Markdown，经过 `marked.js` 渲染后通过 `innerHTML` 注入 DOM。虽然 `_escHtml()` 函数存在，但覆盖范围不确定 — 需要逐点审计所有 `innerHTML` 赋值。

#### 病灶 G：Markdown 即数据库 — 无缓存无索引
`ChangeServiceV2` 每次请求都 `rglob("*.md")` 然后逐文件 `read()` 前 50 行做字符串匹配提取元数据。项目数量增长后性能为 O(n×m)（n=变更单数，m=每次请求的查询条件）。

---

## 二、V8.0.0 长期解决方案

### 2.1 方案总览

**V7.0.0 是诊断文档，V8.0.0 是执行方案**。V8.0.0 以 V7.0.0 的设计为基础，补充以下未覆盖的领域：

| 领域 | V7.0.0 覆盖 | V8.0.0 新增 |
|:--|:--|:--|
| 依赖管理 | 未触及 | 完全重写，pyproject.toml + pip-tools |
| 项目工程化 | 未触及 | pyproject.toml、构建、打包、CLI入口 |
| 前端架构 | 模块化+CSS变量 | 开发服务器、构建打包、ESM、模板引擎 |
| 测试体系 | 未提及 | pytest 配置、CI/CD、覆盖率门禁 |
| vendorized lib/ | 未触及 | 全部迁移到 pip 依赖 |
| 开发环境 | 未提及 | dev 依赖分离、pre-commit hooks |

### 2.2 分阶段执行路线

#### 阶段一：地基重建（后端工程化 + 配置统一）

目标：建立现代化的 Python 项目基础设施，消除当前所有 "找不到版本"、"装不上依赖"、"跑不起来" 的风险。

**具体内容**：

1. **创建 `pyproject.toml`**，包含：
   - `[project]` 元数据（name、version 统一为 8.0.0-dev）
   - `[project.dependencies]`：pywebview、markdown、openpyxl、python-slugify、pyyaml
   - `[project.optional-dependencies]`：dev（pytest、pytest-cov、ruff、pre-commit）
   - `[project.scripts]`：`plc-mgr = "src.main:main"` 作为 CLI 入口
   - `[tool.pytest.ini_options]`：测试配置
   - `[tool.ruff]`：代码规范检查

2. **重写 `requirements.txt`**：
   - 移除 PyQt5、QScintilla、loguru、pydantic、pytest-qt
   - 新增 pywebview（明确版本号）
   - 使用 `pip-compile` 生成带 hash 的锁定文件

3. **删除 `lib/` 目录**：
   - 将 pywebview、cffi、pythonnet、clr_loader 等迁移到 pyproject.toml 依赖
   - 删除重复的 `bottle.py` 副本
   - 如果 pywebview 需要特殊补丁，用 `patch` 或 monkey-patch 方式管理而非源码拷贝

4. **统一配置系统**：
   - 删除 `config.py` 中的 `VERSION = "1.0.0"` 死代码
   - 合并两套 `ConfigLoader`：`src/core/config.py` 为唯一实现
   - `VERSION` 单一真源存储在 `src/core/constants.py`（被 pyproject.toml 动态读取）
   - 添加 `src/core/config.py::ConfigLoader.get_version()` 从 constants 读取而非 JSON

5. **统一日志系统**：
   - 删除 `config.py` 中的 `_get_fallback_logger()` 临时方案
   - 全项目统一使用 `src/utils/logger.py::setup_logger(__name__)`
   - 添加 `src/core/constants.py::LOG_FORMAT` 定义统一格式

#### 阶段二：IPC 网关统一

目标：消除 1700 行 IPCBridge 与 80 行 APIGateway 的双轨并行，建立统一的 API 调用链路。

**具体内容**：

6. **重构 API 调用链路**：
   ```
   Frontend JS                     Backend Python
   ────────────                    ──────────────
   _pyapi('method', ...args)  →    WebViewBridge (适配层，~50行)
                                        ↓
                                   APIGateway._dispatch(domain, method, params)
                                        ↓
                                   ServiceRegistry[domain].method(**params)
                                        ↓
                                   返回 {success, data/error, error_code}
   ```

7. **精简 IPCBridge**：
   - 删除所有 deprecated wrapper（35+ 个）
   - 删除 `MOCK_*` 常量，迁移到 `tests/mock_data.py`
   - 仅保留 pywebview 适配逻辑（`WebViewBridge` 类，< 100 行）
   - 所有业务方法通过 `APIGateway._dispatch()` 路由

8. **Service 注册标准化**：
   - 每个 Service 在 `__init__.py` 中声明公开接口列表
   - `APIGateway._dispatch()` 做方法存在性校验
   - 统一错误响应格式：`{"success": False, "error": "...", "error_code": "..."}`

#### 阶段三：前端重塑

目标：从 "原型模式" 升级到 "可维护的前端工程"。

**具体内容**：

9. **模块化改造（不引入框架，最低成本）**：
   - 使用 IIFE + 显式暴露模式替代全局函数
   - 每个 view 文件为一个模块，挂载在命名空间 `App.views.projectDetail` 下
   - `state.js` 升级为 `Store` 类，提供 `get/set/subscribe` 接口
   - API 调用统一通过 `App.api.call(method, ...args)` 而非全局 `_pyapi`

10. **模板系统替代 innerHTML 拼接**：
    - 引入轻量模板方案（`<template>` 标签 + `cloneNode` 或 Handlebar-lite）
    - 所有用户可控内容通过 `_escHtml()` 转义后再注入
    - 逐点审计所有 `innerHTML` 赋值点（估计 ~60 处），确保 XSS 防护

11. **CSS 工程化**：
    - 消除 `renderProjectOverview` 等视图中的内联 `style="..."`（570+ 行）
    - 将所有内联样式迁移到对应的 CSS 类，定义在 `components/*.css` 中
    - CSS 自定义变量体系覆盖 100% 的视觉属性（已完成 ~9 个变量，需扩展到 ~30 个）
    - 支持 light/dark 双主题切换（通过 `data-theme` 属性切换）

12. **脚本加载顺序治理**：
    - 当前 8 个 JS 文件通过 `<script>` 顺序隐式依赖
    - 改为单一入口 `app.js`，使用 ES modules 或至少明确的依赖声明注释
    - 如不引入构建工具：手动维护加载顺序，顶级 IIFE 包裹，window.App 暴露

#### 阶段四：数据层抽象

目标：实现 V7.0.0 中设计的 Repository 模式，Service 不再直接操作文件系统。

**具体内容**：

13. **创建 `src/core/repository.py`**：
    ```python
    class Repository:
        """文件系统数据访问层 — 统一缓存/索引/查询"""
        
        # 缓存: TTL + 基于 mtime 的失效检测
        # 索引: 项目变更单列表预建索引，避免 rglob
        # 查询: 标准化的 list/get/save/delete CRUD
        # 事务: 写操作使用原子写入（temp file + rename）
    ```

14. **重构 ChangeServiceV2**：
    - `list_change_requests()` → 通过 Repository 查询，命中缓存时不读文件系统
    - `_quick_parse_summary()` → 移至 Repository 层，单次批量解析 + 缓存
    - 变更单写入使用 `Repository.atomic_write()` 防止中途崩溃损坏数据

15. **重构 ProjectService**：
    - `rglob("*.scl")` 扫描 → Repository 缓存项目规模统计
    - 项目卡片数据 → 通过 Repository 获取，缓存 TTL=300s

#### 阶段五：测试体系完善

目标：从 "有测试" 到 "测试驱动开发"。

**具体内容**：

16. **CI/CD 基础设施**：
    - GitHub Actions workflow：`push` 时运行 `ruff check` + `pytest --cov`
    - 覆盖率门禁：新增代码覆盖率 ≥ 80%
    - PR 模板包含测试检查清单

17. **测试结构优化**：
    - 引入 `conftest.py` fixture 共享（`tmp_workspace`、`sample_project`、`sample_change`）
    - `Repository` mock 使得 Service 测试不依赖真实文件系统
    - 前端测试：引入基本的 HTML fixture + DOM 操作测试

#### 阶段六：文档与规范内化

目标：代码即文档，规范内化到工具中。

**具体内容**：

18. **模块级文档字符串**：
    - 每个 `__init__.py` 包含模块概述
    - 每个 Service 的公开方法包含完整的 Google-style docstring
    - 异常列表在 `exceptions.py` 中集中说明

19. **210 编码规范自动化**：
    - 通过 `ruff` 配置强制执行命名、导入排序、类型注解检查
    - pre-commit hook 在提交前自动修复格式问题

---

## 三、文件级影响清单

### 删除

| 文件 | 原因 |
|:--|:--|
| `config.py`（顶层） | 配置碎片化，与 `src/core/config.py` 合并 |
| `lib/bottle.py`（重复副本） | 保留一份即可 |
| `lib/` 整个目录（分析后） | 迁移到 pip 依赖 |
| `ui_prototype/js/api.js` 中的全局 _pyapi | 下沉到 App.api 模块 |
| `src/services/change_service.py`（旧版） | V1 已弃用，V2 完全替代 |

### 新增

| 文件 | 说明 |
|:--|:--|
| `pyproject.toml` | 统一项目元数据 + 依赖 + 工具配置 |
| `src/core/repository.py` | 数据访问层抽象 |
| `src/ui/webview_bridge.py` | 精简版 pywebview 适配（< 100 行） |
| `ui_prototype/js/app.js` | 单一 JS 入口 + 模块注册 |
| `ui_prototype/js/store.js` | 状态管理（替代 state.js 的裸对象） |
| `.github/workflows/ci.yml` | CI/CD |
| `.pre-commit-config.yaml` | pre-commit hooks |

### 大幅修改

| 文件 | 预计行数变化 |
|:--|:--|
| `src/ui/webview_window.py` | 1700 → ~400 行（仅保留窗口管理 + WebViewBridge） |
| `src/services/change_service_v2.py` | 重构为通过 Repository 访问文件系统 |
| `ui_prototype/js/views/*.js` | 50+ 全局函数 → 命名空间模块 |
| `src/core/constants.py` | 统一所有枚举 + VERSION + LOG_FORMAT |
| `src/core/exceptions.py` | 补全异常错误码映射 |

---

## 四、风险与缓解

| 风险 | 等级 | 缓解 |
|:--|:--|:--|
| lib/ 迁移导致 pywebview 行为变化 | 中 | 保留 lib/ 副本作为回退，逐步验证 |
| 前端模块化后全局变量引用断裂 | 中 | 保留 `window.App` 桥接，渐进式迁移 |
| Repository 缓存导致数据不一致 | 低 | mtime-based 缓存失效 + 手动 `repo.invalidate()` API |
| 大面积重构引入回归 | 低 | 逐阶段重构，每个阶段独立验证测试通过 |

---

## 五、不可破坏行为清单（回归基准）

从 V7.0.0 继承并扩充，以下场景在重构全程必须保持通过：

| # | 场景 | 验证方式 |
|:--|:--|:--|
| R1 | CLI `--version` 正确输出版本号 | `python -m src.main --version` |
| R2 | `ipcGetProjectOverview(project_path)` 返回有效 JSON | API 调用测试 |
| R3 | 变更单从创建到关闭的完整生命周期 | 集成测试 |
| R4 | Excel 导出含正确格式和数据 | 单元测试 |
| R5 | `check` 命令扫描报告含 8 类检查结果 | CLI 集成测试 |
| R6 | 前端页面在 pywebview 中正常渲染，无 JS 错误 | 手动回归 |
| R7 | 配置热加载：修改 app_config.json 后新值生效 | 单元测试 |
| R8 | 向后兼容：`_pyapi(legacy_method)` 调用不 crash | 适配层测试 |