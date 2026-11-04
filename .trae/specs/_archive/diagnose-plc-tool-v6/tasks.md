# Tasks — V8.0.0 全栈重构执行清单

## 阶段一：地基重建（后端工程化 + 配置统一）

- [x] Task 1.1: 创建 `pyproject.toml`（项目元数据+依赖+工具配置）
  - [x] 1.1.1 `[project]` 节：name="plc-project-mgr", version="8.0.0-dev"
  - [x] 1.1.2 `[project.dependencies]`：pywebview、markdown、openpyxl、python-slugify、pyyaml
  - [x] 1.1.3 `[project.optional-dependencies]`：dev 分组（pytest、pytest-cov、ruff、pre-commit）
  - [x] 1.1.4 `[project.scripts]`：`plc-mgr = "src.main:main"`
  - [x] 1.1.5 `[tool.pytest.ini_options]`：testpaths、pythonpath 配置
  - [x] 1.1.6 `[tool.ruff]`：lint.select + line-length 等

- [x] Task 1.2: 重写 `requirements.txt`
  - [x] 1.2.1 移除 PyQt5、PyQt5-sip、QScintilla、loguru、pydantic、pytest-qt
  - [x] 1.2.2 添加 pywebview 明确版本号
  - [x] 1.2.3 与 pyproject.toml 的 dependencies 保持一致

- [x] Task 1.3: 处理 `lib/` vendorized 依赖目录
  - [x] 1.3.1 将 pywebview/cffi/pythonnet/clr_loader 迁移到 pyproject.toml pip 依赖
  - [x] 1.3.2 删除 `lib/bottle.py` 重复副本
  - [x] 1.3.3 验证 pywebview 从 pip 安装后行为一致
  - [x] 1.3.4 清理整个 lib/ 目录

- [x] Task 1.4: 统一配置系统
  - [x] 1.4.1 删除 `config.py` 中 VERSION/APP_NAME 死代码
  - [x] 1.4.2 合并两套 ConfigLoader，确立 `src/core/config.py` 为唯一实现
  - [x] 1.4.3 VERSION 单一真源存储在 `src/core/constants.py`
  - [x] 1.4.4 `pyproject.toml` 动态读取 VERSION（`attr: src.core.constants.VERSION`）

- [x] Task 1.5: 统一日志系统
  - [x] 1.5.1 删除 `config.py` 中的 `_get_fallback_logger()`
  - [x] 1.5.2 全项目统一使用 `src/utils/logger.py::setup_logger(__name__)`
  - [x] 1.5.3 在 `constants.py` 添加 `LOG_FORMAT` 常量和 `LOG_LEVEL` 配置

## 阶段二：IPC 网关统一

- [x] Task 2.1: 精简 IPCBridge 为 WebViewBridge（适配层 < 100 行）
  - [x] 2.1.1 删除 35+ deprecated wrapper 方法
  - [x] 2.1.2 删除 MOCK_PROJECTS/MOCK_CHECKERS 等 Mock 常量，迁至 `tests/mock_data.py`
  - [x] 2.1.3 保留 pywebview js_api 适配 + 窗口生命周期管理
  - [x] 2.1.4 重命名类为 `WebViewBridge`

- [x] Task 2.2: APIGateway 升级为统一路由
  - [x] 2.2.1 实现 `APIGateway._dispatch(domain, method, params)` 按 domain.method 路由
  - [x] 2.2.2 Service 注册标准化：每个 Service 声明公开接口列表
  - [x] 2.2.3 统一错误响应格式 `{"success", "data"/"error", "error_code"}`
  - [x] 2.2.4 WebViewBridge 中所有 `self._svc.xxx()` 调用改为 `self._gateway._dispatch(domain, method, params)`
  - [x] 2.2.5 验证 JavaScript `_pyapi('ipcGetProjectOverview', path)` 链路正常

## 阶段三：前端重塑

- [x] Task 3.1: JS 模块化（IIFE + 命名空间，不引入框架）
  - [x] 3.1.1 创建 `js/app.js` 单一入口 + `window.App` 命名空间注册
  - [x] 3.1.2 `state.js` → `store.js`：将裸对象升级为 Store 类（get/set/subscribe）
  - [x] 3.1.3 API 层封装：`App.api.call(method, ...args)` 替代全局 `_pyapi()`
  - [x] 3.1.4 views/*.js 中 50+ 全局函数迁移至命名空间模块（如 `App.views.projectDetail.render()`）
  - [x] 3.1.5 全局 `window.xxx` 函数通过 `App.legacy.*` 桥接保持过渡兼容

- [x] Task 3.2: innerHTML → 模板系统
  - [x] 3.2.1 审计所有 innerHTML 赋值点（预估 ~60 处），建立审计清单
  - [x] 3.2.2 所有用户可控内容注入前通过 `_escHtml()` 转义（含 Markdown 渲染内容）
  - [x] 3.2.3 引入 `<template>` 标签 + `cloneNode` 替代字符串拼接 HTML

- [x] Task 3.3: CSS 工程化
  - [x] 3.3.1 消除 views/*.js 中 570+ 行内联 `style="..."`，迁移到 CSS 类
  - [x] 3.3.2 扩展 CSS 变量体系从 ~9 个到 ~30 个，覆盖全部视觉属性
  - [x] 3.3.3 实现 `data-theme="light|dark"` 双主题切换
  - [x] 3.3.4 脚本加载顺序治理：HTML 中明确声明依赖关系

## 阶段四：数据层抽象

- [x] Task 4.1: 创建 `src/core/repository.py`（Repository 模式）
  - [x] 4.1.1 实现 `Repository` 类：TTL 缓存 + mtime 失效检测
  - [x] 4.1.2 实现标准化 CRUD：`list/get/save/delete` + `invalidate(cache_key)`
  - [x] 4.1.3 实现 `atomic_write(path, content)`：temp file + atomic rename

- [x] Task 4.2: 重构 ChangeServiceV2 通过 Repository
  - [x] 4.2.1 `list_change_requests()` 通过 Repository 查询，命中缓存不读文件系统
  - [x] 4.2.2 `_quick_parse_summary()` 移至 Repository 层，单次批量解析 + 缓存
  - [x] 4.2.3 变更单写入使用 `Repository.atomic_write()`

- [x] Task 4.3: 重构 ProjectService 通过 Repository
  - [x] 4.3.1 `rglob("*.scl")` 扫描结果缓存到 Repository
  - [x] 4.3.2 项目卡片数据通过 Repository 获取，TTL=300s

## 阶段五：测试体系完善

- [x] Task 5.1: CI/CD 基础设施
  - [x] 5.1.1 创建 `.github/workflows/ci.yml`：`ruff check` + `pytest --cov`
  - [x] 5.1.2 覆盖率门禁：新增代码 ≥ 80%

- [x] Task 5.2: 测试结构优化
  - [x] 5.2.1 添加 `conftest.py` fixture 共享（`tmp_workspace`, `sample_project`, `sample_change`）
  - [x] 5.2.2 Repository mock 使 Service 测试不依赖真实文件系统
  - [x] 5.2.3 创建 `.pre-commit-config.yaml`

## 阶段六：文档与规范内化

- [x] Task 6.1: 文档补全
  - [x] 6.1.1 每个 `__init__.py` 添加模块概述 docstring
  - [x] 6.1.2 每个 Service 公开方法添加 Google-style docstring
  - [x] 6.1.3 `exceptions.py` 集中说明所有异常类型和语义

- [x] Task 6.2: 规范自动化
  - [x] 6.2.1 ruff 配置覆盖命名/导入/类型注解规则
  - [x] 6.2.2 pre-commit hook 自动格式修复

# Task Dependencies

```
阶段一 ──→ 阶段二 ──→ 阶段四 ──→ 阶段五、六
               ↘
                阶段三（可并行）
```

- [Task 1.1~1.5] 无依赖，全部可并行 ✅
- [Task 2.1] 依赖 [1.3, 1.4] ✅
- [Task 2.2] 依赖 [2.1] ✅
- [Task 3.1~3.3] 无外部依赖，可与阶段二并行 ✅
- [Task 4.1~4.3] 依赖 [阶段二] ✅
- [Task 5.1~5.2] 依赖 [阶段四] ✅
- [Task 6.1~6.2] 依赖 [阶段五] ✅