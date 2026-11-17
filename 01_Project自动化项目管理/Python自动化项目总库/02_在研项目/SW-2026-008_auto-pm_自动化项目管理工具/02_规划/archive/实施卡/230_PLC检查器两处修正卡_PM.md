# PLC 检查器两处修正卡

> 卡片编号：`CARD-PLC-CHECKER-FIX V1.0`
> 隔离基线：`db0a51c9514827960cd4c1d6f6189c561993ec7a`（`main`）
> 路径根：`.`
> 档次：核心档
> 安全回路: 否

本卡只给 `main.py pr open` 提供“可改范围”，由云端会话起草。本卡改的是驾驶舱的 PLC 检查器代码和测试，不碰任何 PLC 项目文件，所以安全回路填“否”；但 `auto_pm/` 和 `tests/` 是受保护路径，PR 需要用户“规则批准 <头提交号>”，合并后还要再发一版，运行中的驾驶舱才生效，今天不会发版。

修两处检查器缺陷（都由 DJ-2026-011 的 TIA 实测和 plc check 暴露）：
1. SclLinter 读 .scl 用严格 UTF-8，遇到“带 BOM 且 BOM 紧贴首行代码”的文件，BOM 被当成首行字符，误报 `LSP-905-STRUCT-NO-BLOCK`。TIA 要求 .scl 带 BOM，所以带 BOM 是正确写法，该修的是检查器：读文件时按带 BOM 的方式解码（utf-8-sig），仍保持“解不了码要报出来”的严格性。
2. 接口文档检查 `scheme_doc.py` 只把“数据块里声明的 FB 实例”算作代码里的实例。#539 把实例搬进了 FB_9001_TestBench 的静态区（多重实例，TIA 推荐写法），INT 文档的实例表已写对，却被报“文档有、代码无”。修法：FB 静态区里 FB 类型的变量也计入代码实例，名称用“FB 名.变量名”，沿用现有短名匹配逻辑。不改 INT 文档、不改表头去躲检查。

| 路径 | 基线状态 | 用途 |
|---|---|---|
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/scl_linter.py` | 存在 | 读 .scl 改为带 BOM 的严格 UTF-8 解码，BOM 紧贴首行代码不再误报 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/domain/plc/scheme_doc.py` | 存在 | FB 静态区里的 FB 类型变量（多重实例）也计入代码实例 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_scl_linter.py` | 存在 | 新增“首行即代码的带 BOM 文件 0 违规”用例，并保留“坏编码仍报错”的反例 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_scheme_doc.py` | 存在 | 新增“实例在 FB 静态区时与 INT 表一致”用例，并保留“表里写了但代码没有仍报”的反例 |

PR 另需：同类排查——全库里还有哪些检查器按严格 UTF-8 读 .scl/.db/.md 而没处理 BOM，清单写进 PR 描述，范围外的另记；若查出的同类文件不在上表，先补充本卡再改。

## 验收
- `.venv\Scripts\python.exe -m pytest {worktree}/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_scl_linter.py -q => 0`
- `.venv\Scripts\python.exe -m pytest {worktree}/01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/plc/test_scheme_doc.py -q => 0`
- 用于对照：改动前先在基线上写好失败的用例（红），改后转绿，证据写进 PR。
- `main.py plc check DJ-2026-011` 不能作为本卡验收：检查器改动要发版后才在运行的驾驶舱里生效。

## 未核实
- 部署副本 `00_Infrastructure/auto_pm/auto_pm/domain/plc/` 是否在本卡里同步，以发布流程为准，本卡只改源码。
- scheme_doc 的修法对 CODESYS（InoProShop）项目里 FB 静态区写法是否同样成立，未核实。
