# 2026-11-04 .trae 旧资料归档 · 索引

> 只移动、不删除、不改一个字节（git 记录为 100% 重命名）。依据：用户 2026-11-04 全权委托处理（过时文件清单第 2 节）；`.trae/` 属受保护路径，本次移动由用户的委托授权，PR 里已点名。
> 恢复方法：`git mv <现路径> <旧路径>`。母体里同批归档的内容见 `01_Project自动化项目管理/…/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/archive/2026-11-04_产品档与旧资料归档/INDEX.md`。

## 1. `.trae/documents/`（5 份，2026-08-25～27 的审查与 RFC 草稿）→ 本目录 `documents/`

| 文件 | 为什么过时 |
|---|---|
| `AI_工作流底层架构升级方案_RFC_20260827.md` | 当时 pm-workflow/PM_SESSION 体系的方案，两者已于 2026-09-09 / 10-10 退役 |
| `AI工作流子代理物理隔离RFC核对与落地计划_20260826.md` | 同上；子代理隔离已写进 AGENTS.md 现行规则 |
| `PM_PLC全栈_驾驶舱_Obsidian联合工作流缺陷分析_20260827.md` | 8 月缺陷分析，建立在已退役的 pm-workflow 三技能体系上（是否逐条处理完未逐条核对） |
| `工作空间审查计划_auto-pm规范驾驶舱与技能一致性_20260825.md` | 8 月审查计划，建立在已退役的 pm-workflow 体系上 |
| `工作空间问题审查与P0P1修复计划_20260826.md` | 同上，计划里引用的 `pm-workflow` 技能目录已删除 |

证据：5 份文件名在仓库其他位置没有任何引用（只有它们互相引用；`.dockerignore` 里的 `.trae/documents/` 是忽略规则，无影响）。

## 2. `.trae/temp/`（3 个临时脚本）→ 本目录 `temp/`

`check_refs.ps1`、`check_scl_comments.ps1`、`fix_scl_comments.py`：目录名即“临时”；全库没有引用这三个文件（`role_pack_service.py` 里的 `_check_refs_equal` 是同名巧合，无关）。**只核了文件名和引用，没有逐个读内容。**

## 3. `.trae/specs/` 旧规格（23 套）→ `.trae/specs/_archive/<名>/`（和已有的 19 套放在一起）

最后一条日期在 2026-06-03～2026-07-23（多数套内没写日期）。套内文件互相用路径文字引用，原样保留。

audit-specs-and-sync-v2-docs、cleanup-root-structure、deep-audit-auto-pm-plc-readiness、develop-gui-v2-modular、diagnose-plc-tool-v6、diagnose-plc-tool-v8-gap、diagnose-redesign-v9、execute-auto-pm-v2-test-plan、feasibility-backend-frontend-separation、fix-auto-pm-five-bugs、fix-gui-data-flow、fix-gui-root-cause、fix-plc-module-and-rebuild-templates、fix-project-detail-data-reliability、impl-fb1014-stationconveyor-v2、iterate-plc-tool-v7-arch、plan-plc-tool-full-diagnostic-testing、pm-toolchain-eval、redesign-ui-ide-layout、roadmap-reorder-and-spec-revision、skill-architecture-redesign、update-prd-v1.1.0、workspace-evaluation。

证据：除这些套互相引用外，全库没有文件引用它们；`AGENTS.md`、`.trae/rules`、`.trae/skills`、`.cursor`、`.agent`、`.agents` 里没有 `trae/specs` 的路径引用；代码和测试里只有一个 `.gitkeep` 模板路径和一个测试用假路径，与这些套无关。

## 4. 没动的

`.trae/specs/_archive/` 里原有的 19 套、`.trae/rules`、`.trae/skills`、`.trae/skills_archive`、`.trae/bin`、`.trae/project-bootstrap`。
