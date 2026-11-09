# Checklist

## P0 运行时产物治理
- [x] `.gitignore` 包含 `output/` 规则
- [x] `git ls-files output/` 返回空（test_result.json 已取消跟踪）
- [x] 本地 output/gui_smoke_chg2/test_result.json 文件仍存在（仅取消跟踪未删除）

## P1 文档卫生
- [x] `docs/example.md` 已删除
- [x] `docs/gui-prototype/` 目录已删除
- [x] `docs/里程碑迭代计划_V2.1.md` 已删除
- [x] `docs/归档索引.md` 已删除
- [x] `02_设计/screenshot_prototype.py` 已删除
- [x] `02_设计/claude_架构评审建议.md` 已删除
- [x] `02_设计/Html原型预览/check.txt` 已删除
- [x] `02_设计/Html原型预览/` 根级仅保留 006_UI架构原型.html
- [x] `02_设计/Html原型预览/archive/` 包含 007-012 共 6 个历史 HTML 原型

## P2 结构优化
- [x] 根目录无 `main.py`（已删除）
- [x] `auto_pm/__main__.py` 的 `if __name__ == "__main__"` 块包含无参数自动启动 GUI 逻辑（`len(sys.argv) == 1` 时 append "gui"）
- [x] `auto_pm/__main__.py` 编码修复逻辑（PYTHONUTF8=1 + _fix_windows_encoding）保持不变
- [x] 根目录无 `.ruff.toml`（已删除）
- [x] `pyproject.toml [tool.ruff]` 包含完整的 exclude + line-length + lint + format 配置
- [x] `.env_template` 已重命名为 `.env.example`
- [x] 全局无 `.env_template` 残留引用

## 入口与配置正确性
- [x] `python -m auto_pm --help` 正常输出帮助信息
- [x] `python -m auto_pm`（无参数）能正常启动 GUI（GUI 逻辑已合并到 __main__.py，代码核查通过）
- [x] `python -m auto_pm gui` 能正常启动 GUI（显式参数，gui 子命令已注册）
- [x] `ruff check .` 无新增报错（11 个预存问题经配置等价性核查确认非本次引入）
- [x] `ruff format --check .` 通过（无新增格式问题，预存格式问题非本次引入）
- [x] `mypy auto_pm` 无新增类型错误（4 errors ≤ 基线 5 errors）

## 文档同步
- [x] README.md"项目结构"章节无 main.py / .ruff.toml / output/ 引用
- [x] README.md"已废弃文档"表格已移除 docs/ 已删除条目
- [x] README.md"文档导航"无 docs/归档索引.md 引用
- [x] README.md 无 .env_template / main.py / .ruff.toml 残留引用

## 回归验证
- [x] 快速测试 `pytest tests/ -x --no-cov -q` 全部通过（1300 passed, 2 skipped）
- [x] `git status` 显示的变更仅限本次清理范围（无意外文件改动）
