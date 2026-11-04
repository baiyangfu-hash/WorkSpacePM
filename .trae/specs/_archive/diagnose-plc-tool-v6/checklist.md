# Checklist — V8.0.0 重构验证清单

## 阶段一：地基重建

- [x] `pyproject.toml` 存在且包含 `[project]`、`[project.dependencies]`、`[project.scripts]` 节
- [x] `pyproject.toml` 中 `dependencies` 与 `requirements.txt` 一致
- [x] `requirements.txt` 不再包含 PyQt5、QScintilla、loguru、pydantic、pytest-qt
- [x] `requirements.txt` 包含 pywebview 明确版本号
- [x] `lib/` 目录已被记录版本（VENDOR_VERSIONS.md）并删除重复副本
- [x] `config.py` 中不再包含 `VERSION = "1.0.0"` 和 `_get_fallback_logger()`
- [x] `src/core/config.py` 为项目中唯一的 `ConfigLoader` 类
- [x] `VERSION` 仅定义在 `src/core/constants.py` 一处
- [x] `pyproject.toml` 动态读取 `version = {attr = "src.core.constants.VERSION"}`
- [x] `constants.py` 包含 LOG_FORMAT/LOG_DATE_FORMAT/LOG_LEVEL 常量
- [x] `cli.py` 的 `cmd_version` 与 constants.VERSION 一致（均为 6.0.0）

## 阶段二：IPC 网关统一

- [x] `IPCBridge` 类已重命名为 `WebViewBridge`，webview_window.py 从 1703→412行
- [x] `WebViewBridge` 中不再包含任何 deprecated wrapper（20个全部删除）
- [x] `MOCK_PROJECTS`、`MOCK_CHECKERS` 等 Mock 常量已从 `webview_window.py` 中移除
- [x] `APIGateway._dispatch(domain, method, params)` 实现完整路由（line 45-68）
- [x] 每个 Service 在 APIGateway._register_services() 中注册（8个域）
- [x] 统一错误响应格式 `{"success", "data"/"error", "error_code"}`
- [x] `IPCBridge = WebViewBridge` 别名保留向后兼容

## 阶段三：前端重塑

- [x] `js/app.js` 作为单一入口，`window.App` 命名空间暴露模块
- [x] `js/store.js` 提供 `get/set/subscribe/snapshot/update` 接口（非裸对象 state）
- [x] API 层封装：`App.api.call(method, ...args)` 
- [x] `App.views.projectDetail` 注册 16 个函数
- [x] `window` 上全局函数通过向后兼容循环保留
- [x] CSS base.css 新增工程状态/规模/快捷操作/变更台账/暗色主题样式类
- [x] `data-theme="dark"` CSS 规则已定义
- [x] 脚本加载顺序在 index.html 中通过注释和 `<script>` 顺序显式声明

## 阶段四：数据层抽象

- [x] `src/core/repository.py` 存在，`Repository` 类实现 TTL 缓存 + CacheEntry
- [x] `Repository` 提供 CRUD：`read_file/write_file/list_files/count_files` + `invalidate()`
- [x] `Repository.write_file()` 使用 `tempfile.mkstemp` + `os.replace` 原子写入
- [x] `ChangeServiceV2` list_change_requests 使用 `self._repo.list_files()`
- [x] `ChangeServiceV2` _quick_parse_summary 使用 `self._repo.read_file_lines()`
- [x] `ChangeServiceV2` _update_ledger 使用 `self._repo.write_file()`
- [x] `ProjectService` 添加 Repository 依赖注入 `self._repo`

## 阶段五：测试体系

- [x] `.github/workflows/ci.yml` 存在，含 lint + test 双 job
- [x] CI 包含 `ruff check` + `ruff format --check` + `pytest --cov` 步骤
- [x] `conftest.py` 提供 `tmp_workspace`、`sample_project`、`sample_change`、`mock_repository` fixture
- [x] Repository mock 覆盖 `read_file/list_files/get_project_scale` 等核心方法
- [x] `.pre-commit-config.yaml` 存在，含 ruff lint + format hook

## 阶段六：文档与规范

- [x] `src/__init__.py` 含三层架构概述
- [x] `src/services/__init__.py` 含 10 个 Service 清单
- [x] `src/core/__init__.py` 含 6 个模块说明
- [x] `exceptions.py` 末尾含异常类型树（5域15子类）
- [x] pyproject.toml 中 ruff 配置覆盖 lint.select（E/F/I/N/W/UP）
- [x] `.pre-commit-config.yaml` 含 ruff --fix + ruff-format

## 回归基准（R1-R8）

- [x] R1: VERSION 单源在 constants.py（6.0.0），CLI 通过 constants.VERSION 读取
- [x] R2: `ipcGetProjectOverview` 现通过 `_route("project", "get_overview")` 路由
- [x] R3: 变更生命周期相关方法（create/transition/list）通过 APIGateway._dispatch 路由
- [x] R4: Excel 导出方法通过 `_route("project", "export_excel_*")` 路由
- [x] R5: `run_spec_check` 通过 `_route("spec_checker", "run")` 路由
- [x] R6: 前端 index.html 脚本加载顺序保护 + CSS 回退值
- [x] R7: ConfigLoader 单例实现哈希校验 + 文件监听
- [x] R8: `IPCBridge = WebViewBridge` 别名 + `window.*` 全局函数向后兼容循环