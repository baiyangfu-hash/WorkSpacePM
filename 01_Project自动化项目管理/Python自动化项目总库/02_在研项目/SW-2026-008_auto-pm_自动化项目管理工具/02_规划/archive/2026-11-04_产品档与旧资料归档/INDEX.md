# 2026-11-04 产品档与旧资料归档 · 索引

> 本目录文件只移动、不删除、不改一个字节（git 记录为 100% 重命名）。归档依据见 `/mnt/project-files/archive-review` 的过时文件清单第 2 节；用户 2026-11-04 全权委托处理。
> 恢复方法：`git mv <现路径> <旧路径>`。以下“旧路径”均相对母体根目录（SW-2026-008_auto-pm_自动化项目管理工具/）。
> 配套归档（仓库根 `.trae/` 下的旧资料）见仓库根 `.trae/archive/2026-11-04_过时资料归档/INDEX.md`。

## 1. 母体产品档文件（现路径在本目录 `files/` 下）

| 旧路径 | 现路径（本目录下） | 为什么过时 | 证据 |
|---|---|---|---|
| `Taskfile.yml` | `files/Taskfile.yml` | 文件头自己写“仅供母体开发回退参考”（A2-4 标注，2026-09-06），日常入口已是驾驶舱 `main.py` | 全库只有它引用自己调用的两个脚本；`python_service.py` 等引用的是 `templates/python-tool/template/Taskfile.yml.jinja`（生成项目用的模板），不是这个文件 |
| `scripts/pre_closure_gate.py` | `files/scripts/pre_closure_gate.py` | 只被母体 Taskfile 调用，驾驶舱已有 `pm verify`/门禁取代 | 全库引用只有 Taskfile 和历史清单 |
| `scripts/ruff_baseline_check.py` | `files/scripts/ruff_baseline_check.py` | 同上，且它读的 `reports/ruff_extended_baseline…` 目录在母体里已不存在，CI 直接跑 `ruff check` | 全库引用只有 Taskfile 和历史清单 |
| `scripts/gui_visual_reporter.py` | `files/scripts/gui_visual_reporter.py` | 全库零调用 | 只有自己文件头的用法示例和历史清单 |
| `scripts/verify_m7_gui.py` | `files/scripts/verify_m7_gui.py` | M7 阶段的一次性 GUI 核验脚本 | 只被实施卡 158、CHG-SCPT-2026-426、几份 DEC/审计报告当历史提及，没有代码或测试调用 |
| `scripts/diag_change_cross_project_bug.py` | `files/scripts/diag_change_cross_project_bug.py` | 一次性缺陷诊断脚本，缺陷已修 | 只出现在旧 PM_SESSION 归档里 |
| `.vscode/launch.json` | `files/vscode_launch.json` | 启动的 `auto_pm.cli.__main__` 模块不存在，示例命令是模板残留 | 源码里没有 `auto_pm/cli/` 目录，只有 `auto_pm/__main__.py`；母体 `.gitignore` 里 `!.vscode/launch.json*` 例外规则保留不动（无害） |
| `.github/pull_request_template.md` | `files/github_pull_request_template.md` | GitHub 只认仓库根 `.github/` 的模板，母体这份不生效，且与根目录那份内容不同 | 内容只有两行（`Fixes #...`、`## Changelog`） |

没动的相邻文件：`scripts/figure_consistency_check.py`（测试在导入）、其他仍被 CI/测试/驾驶舱使用的脚本、`.pre-commit-config.yaml`（待确认）。

## 2. 母体 `.trae/specs/` 旧规格（现路径：母体 `.trae/specs/_archive/<名>/`）

7 套，最后一条日期都在 2026-06-22～2026-07-26，早于当前驾驶舱体系。套内文件互相用路径文字引用其他套（如 `.trae/specs/rebuild-auto-pm-v2-unified`），这些文字原样保留，指向的是移动前的位置。

| 旧路径（`.trae/specs/` 下） | 现路径（`.trae/specs/_archive/` 下） | 备注 |
|---|---|---|
| `add-spec-drift-detection/` | 同名 | 套内最晚日期 2026-06-24 |
| `audit-cockpit-and-skills/` | 同名 | 2026-07-26 |
| `deep-tech-debt-audit-v1.1.0/` | 同名 | 2026-07-25 |
| `fix-v091-diagnostic-quick-wins/` | 同名 | 套内无日期 |
| `rebuild-auto-pm-v2-unified/` | 同名 | 2026-06-22；其他规格里有路径文字引用 |
| `refresh-auto-pm-docs-and-tests/` | 同名 | 套内无日期 |
| `v2.1-change-management-enhancement/` | 同名 | 2026-06-27；旧 PM_SESSION 归档里有历史提及 |

## 3. 没改的历史引用（保持原样，不算断链）

- 实施卡 158、`05_收尾/002_验收核验报告_PM.md`、`CHG-SCPT-2026-426`、`CHANGELOG.md`、旧 PM_SESSION 归档、`.auto-pm/artifacts/sw-2026-008/NG-WP-11/source_manifest.csv`、`.auto-pm/decisions/DEC-20260910-7E8F0EF4.json`、`DEC-20261017-M3ENVP01.json`、`DEC-20261029-38E743C7.json`、`reviews/18_audit_pr3_envport.md`：都是历史记录，里面写的旧路径不改。

## 4. 核对记录

- 归档前重新查过全库引用（排除各 `archive/`、`releases/`）：没有任何 workflow、测试、`auto_pm` 代码在运行时读取上面这些文件。
- CI 的 `ruff`/`mypy` 只扫 `auto_pm tests`，不受影响。
- 分档表（`tests/tools/tier_core_list.json`）里 `PRODUCT-TASKFILE`、`PRODUCT-SCRIPTS`、`PRODUCT-VSCODE`、`PRODUCT-GITHUB` 四条规则没改（规则指向的是以后可能再出现的同类文件）。
