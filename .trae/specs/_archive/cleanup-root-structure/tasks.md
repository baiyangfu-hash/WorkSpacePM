# Tasks

- [x] Task 1: P0 修复 — gitignore output/ 并取消跟踪测试产物
  - [x] SubTask 1.1: 在 `.gitignore` 新增 `output/` 规则（放在 pytest 区块附近）
  - [x] SubTask 1.2: `git rm --cached output/gui_smoke_chg2/test_result.json` 取消跟踪（保留本地文件）
  - [x] SubTask 1.3: 验证 `git status` 显示该文件为 deleted（仅索引），本地文件仍在

- [x] Task 2: P1 清理 — 删除 docs/ 下 4 个废弃文件
  - [x] SubTask 2.1: 删除 `docs/example.md`（README 标记"可删除"）
  - [x] SubTask 2.2: 删除 `docs/gui-prototype/` 整个目录（DEPRECATED.md + index.html）
  - [x] SubTask 2.3: 删除 `docs/里程碑迭代计划_V2.1.md`（V2.1 历史计划）
  - [x] SubTask 2.4: 删除 `docs/归档索引.md`（索引指向部分已废弃内容）
  - [x] SubTask 2.5: 若 docs/ 删除后为空，保留空目录或删除整个 docs/（视情况）

- [x] Task 3: P1 清理 — 移除 02_设计/ 杂散文件
  - [x] SubTask 3.1: 删除 `02_设计/screenshot_prototype.py`（Playwright 截图脚本，引用不存在的 GUI原型.html）
  - [x] SubTask 3.2: 删除 `02_设计/claude_架构评审建议.md`（AI 评审过程产物）
  - [x] SubTask 3.3: 删除 `02_设计/Html原型预览/check.txt`（grep 输出残留）

- [x] Task 4: P1 归档 — 02_设计/Html原型预览/ 历史 HTML 原型归档
  - [x] SubTask 4.1: 创建 `02_设计/Html原型预览/archive/` 目录
  - [x] SubTask 4.2: 将 007-012 共 6 个 HTML 原型（V2-V7）移入 archive/
  - [x] SubTask 4.3: 保留 `006_UI架构原型.html` 在 Html原型预览/ 根级作为当前真源

- [x] Task 5: P2 优化 — 删除 main.py 并合并 GUI 逻辑到 __main__.py
  - [x] SubTask 5.1: 在 `auto_pm/__main__.py` 的 `if __name__ == "__main__"` 块中，新增无参数自动启动 GUI 逻辑（`if len(sys.argv) == 1: sys.argv.append("gui")`），放在 `_fix_windows_encoding()` 调用之前、`cli()` 调用之前
  - [x] SubTask 5.2: 确认 `auto_pm/__main__.py` 现有编码修复逻辑（PYTHONUTF8=1 + _fix_windows_encoding）保持不变
  - [x] SubTask 5.3: 删除根目录 `main.py`
  - [x] SubTask 5.4: 确认 pyproject.toml [project.scripts] 仍指向 `auto_pm.cli.__main__:cli`（不变）

- [x] Task 6: P2 优化 — 合并 ruff 配置到 pyproject.toml
  - [x] SubTask 6.1: 将 `.ruff.toml` 的全部配置（exclude、line-length=100、lint select/ignore、format）合并到 `pyproject.toml [tool.ruff]` 段
  - [x] SubTask 6.2: 保留 pyproject.toml 现有的 `extend-exclude = ["02_设计", "scratch_*.py"]`，与 .ruff.toml 的 exclude 合并为完整列表
  - [x] SubTask 6.3: 删除 `.ruff.toml`
  - [x] SubTask 6.4: 运行 `ruff check .` 验证配置合并后行为不变（无新增报错）

- [x] Task 7: P2 优化 — 重命名 .env_template 为 .env.example
  - [x] SubTask 7.1: 重命名 `.env_template` → `.env.example`
  - [x] SubTask 7.2: 全局搜索 `.env_template` 引用并更新（若 README 或代码中有引用）

- [x] Task 8: 同步更新 README.md
  - [x] SubTask 8.1: 更新"项目结构"章节，移除 main.py、.ruff.toml，修正 docs/ 描述
  - [x] SubTask 8.2: 更新"已废弃文档"表格，移除已删除的 docs/ 条目
  - [x] SubTask 8.3: 更新"文档导航"章节，移除 docs/归档索引.md 引用
  - [x] SubTask 8.4: 确认 README 中无对 .env_template、main.py、.ruff.toml 的残留引用

- [x] Task 9: 验证 — 门禁检查与回归
  - [x] SubTask 9.1: 运行 `python -m auto_pm --help` 确认入口正常
  - [x] SubTask 9.2: 运行 `python -m auto_pm gui` 确认无参数 GUI 启动正常（验证 main.py 删除后入口不缺失）
  - [x] SubTask 9.3: 运行 `ruff check .` + `ruff format --check .` 确认配置合并后无报错
  - [x] SubTask 9.4: 运行 `mypy auto_pm` 确认类型检查不受影响
  - [x] SubTask 9.5: 运行快速测试 `pytest tests/ -x --no-cov -q` 确认无回归

# Task Dependencies

- Task 5（删 main.py）需先确认 SubTask 5.3（__main__ 无参 GUI 逻辑），否则入口缺失
- Task 6（合并 ruff）依赖 Task 3/4 完成（避免清理中反复调整 exclude）
- Task 8（更新 README）依赖 Task 1-7 全部完成（确保引用一致）
- Task 9（验证）依赖 Task 1-8 全部完成
- Task 1/2/3/4/7 可并行执行（互不依赖）
