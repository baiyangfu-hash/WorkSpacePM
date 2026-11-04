# PM 规范体系与 auto-pm V2.0 变更管理对接审查报告

## 1. 审查概述

### 1.1 审查目标
审查 PM 规范体系（040/042 变更管理 + 010/016 项目结构）与 auto-pm V2.0 变更管理实现的对接关系，识别规范与实现之间的缺口，输出修订建议清单。

### 1.2 审查范围
| 规范/代码 | 文件路径 | 版本/状态 |
|-----------|----------|-----------|
| CHG-040 变更单模板 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/04_变更管理/040_通用变更单模板_CHG.md` | V2.1.0 |
| PM-042 变更管理流程规范 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/04_变更管理/042_通用变更管理流程规范_PM.md` | V2.2.0 |
| PM-043 变更管理目录结构说明 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/04_变更管理/043_通用变更管理目录结构说明_PM.md` | V2.1.0 |
| PM-010 通用项目管理规范 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/02_规划阶段/010_通用项目管理规范_PM.md` | V1.0.2 |
| PROJ-016 通用项目结构模板 | `00_Obsidian_Base全局规范文件仓库/01_项目管理域/02_规划阶段/016_通用项目结构模板_PROJ.md` | V1.0.0 |
| auto-pm 变更单生成器 | `auto_pm/change/generator.py` | V2.0 |
| auto-pm 变更服务 | `auto_pm/change/change_service.py` | V2.0 |
| auto-pm 变更模型 | `auto_pm/change/models.py` | V2.0 |
| auto-pm 变更解析器 | `auto_pm/change/parser.py` | V2.0 |
| auto-pm 路径解析器 | `auto_pm/change/path_resolver.py` | V2.0 |
| auto-pm 项目模板 | `templates/plc-standard/`、`templates/python-tool/` | Copier |

### 1.3 审查方法
- 逐行比对 040 模板章节结构与 generator.py 输出
- 逐状态比对 042 §5.2 状态机与 models.py STATUS_FLOW
- 逐目录比对 016 §4.1 顶层目录与 auto-pm 模板生成结构及 path_resolver 路径约定
- 核对门禁规则实现与 042 §5.3~§5.7 流程要求

### 1.4 审查结论摘要
共识别 **14 项对接缺口**，按优先级分布：
- **P0（严重，阻断规范一致性）**：3 项
- **P1（重要，影响功能完整性）**：6 项
- **P2（改进，提升规范覆盖度）**：5 项

---

## 2. PM 规范审查发现

### 2.1 CHG-040 变更单模板审查（V2.1.0）

#### 2.1.1 模板章节结构（040 规范定义）
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

#### 2.1.2 auto-pm generator.py 输出结构比对
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

#### 2.1.3 关键发现
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

---

### 2.2 PM-042 变更管理流程规范审查（V2.2.0）

#### 2.2.1 状态机定义（042 §5.2）
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

#### 2.2.2 auto-pm STATUS_FLOW 比对（models.py 第 99-111 行）
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

#### 2.2.3 状态机对接缺口
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

#### 2.2.4 关键发现
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

---

### 2.3 PM-010 通用项目管理规范审查（V1.0.2）

#### 2.3.1 规范内容
010 规范 V1.0.2 共 91 行，内容非常概括，包含 10 个章节：
- §1 文档目的
- §2 适用范围（适用于所有Python和PLC电气工程项目）
- §3 项目管理流程（启动/规划/执行/监控控制/收尾）
- §4 项目管理工具（"使用Python项目管理工具进行项目管理"）
- §5 版本管理（"遵循语义化版本规范"、"使用变更管理模板记录版本变更"）
- §6~§10 质量保证/风险管理/沟通管理/文档管理/附录

#### 2.3.2 关键发现
1. **规范过于简略（P2）**：010 规范作为"通用项目管理规范"总纲，只有 91 行，内容非常概括，没有提供具体的可执行规范条目。auto-pm 的实现实际上是基于 042/043 等更具体的规范，010 规范没有起到指导作用。

2. **适用范围描述与实际不符（P2）**：010 §2 声明"适用于所有Python和PLC电气工程项目的管理过程"，但内容中没有覆盖 PLC 项目的特殊管理要求（如 LSP-907 规范引用）。

3. **PM_SESSION 文件未定义（P2）**：auto-pm 模板生成的 `PM_SESSION_*.md` 文件是 pm-workflow 技能的单一真源（python-tool 模板 PM_SESSION 第 1-65 行），但 010 规范中没有定义这个文件的角色和结构。

---

### 2.4 PROJ-016 通用项目结构模板审查（V1.0.0）

#### 2.4.1 规范定义的目录结构（016 §4.1）
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

#### 2.4.2 auto-pm 实际使用的目录路径
| 代码位置 | 路径定义 | 用途 |
|----------|----------|------|
| change_service.py 第 519-524 行 `_get_change_file_path` | `00_项目管理/04_变更管理/01_变更单/CHG-{DOMAIN}/` | 变更单文件存放 |
| path_resolver.py 第 126-131 行 `_CHANGE_SEARCH_PATHS` | PLC: `00_项目管理/04_变更管理/01_变更单`<br>通用: `01_项目文档/03_执行过程/02_变更管理` | 变更单搜索 |
| path_resolver.py 第 189-191 行 `find_ledger_file` | `00_项目管理/04_变更管理/04_变更记录/01_版本变更台帐.md` | 台帐查找 |
| path_resolver.py 第 109-116 行 `_PROJ_SEARCH_PATHS` | PLC: `00_项目管理/01_立项与需求`<br>通用: `00_项目基础信息` | 立项表查找 |

#### 2.4.3 关键发现
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

---

## 3. auto-pm 变更管理实现与 PM-042 对接分析

### 3.1 状态机对接分析

#### 3.1.1 状态流转合法性校验
auto-pm 通过 `validate_status_transition`（models.py 第 198-208 行）校验状态流转合法性，使用 STATUS_FLOW 字典定义允许的流转。该校验机制符合 042 §5.2"变更单只能向前移动到相邻状态，不能跳跃"的要求。

#### 3.1.2 状态持久化机制
auto-pm 通过 `_update_status_field`（change_service.py 第 597-612 行）将状态写入 §3.4 "变更状态"字段，parser.py 通过 `_read_explicit_status`（parser.py 第 346-358 行）优先读取该字段。这种持久化机制确保状态在文件读写过程中不丢失，但依赖 auto-pm 扩展的"变更状态"字段（040 模板未定义）。

#### 3.1.3 状态推断回退机制
当 §3.4 无显式状态时，parser.py 通过 `_infer_status_from_approval`（parser.py 第 248-281 行）从 §8 审批章节推断状态。这种回退机制兼容旧版变更单，但推断逻辑与 042 状态机命名不一致（如推断出 `approved` 而非 042 的 `pending_implementation`）。

### 3.2 门禁规则对接分析

#### 3.2.1 已实现的门禁规则
auto-pm `_check_transition_guards`（change_service.py 第 660-748 行）实现了以下门禁：
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

#### 3.2.2 未实现的门禁规则
| 042 规范要求 | auto-pm 实现情况 | 缺口 |
|-------------|------------------|------|
| §5.4 影响分析（受影响组件、风险等级、缓解措施） | 未校验 | generator.py 未生成 §6 结构，无法校验 |
| §5.4 跨领域影响评估 | 未校验 | §6.2/6.3 结构缺失 |
| §5.4 风险等级（LOW/MEDIUM/HIGH） | 未校验 | 无风险等级字段 |
| §5.4 缓解措施 | 未校验 | 无缓解措施字段 |
| §5.5 审批历史不可删除 | 追加模式但无防覆盖校验 | 无校验机制 |
| §5.8 变更单存档（01_变更单/对应领域子目录） | 已实现 | ✓ 符合 043 规范 |
| §5.8 版本变更台帐记录（引用模式） | 已实现（ledger_updater.py） | ✓ 符合 043 规范 |

### 3.3 变更单生成器对接分析

#### 3.3.1 符合 040 模板的部分
- §1~§5 章节结构基本符合（除 §5 字段简化、§3.4 扩展字段）
- §7~§9 章节结构符合
- §3.1/3.2/3.3 选择表格渲染符合（使用 ☑/□ 标记）
- 变更编号格式 `CHG-{DOMAIN}-{YYYY}-{XXX}` 符合 040 §3.0

#### 3.3.2 不符合 040 模板的部分
- §6 影响分析结构完全缺失（仅输出"待填写"）
- §10 章节编号错位（跳过 §10.2 跨领域联动验证）
- §11 版本详细变更说明缺失
- §12 附录错位为 §11
- 文档版本号 V1.0.0 ≠ 规范 V2.1.0
- §5 字段简化（缺"相关截图/附件"、"预期效果"）

---

## 4. 对接缺口识别

### 4.1 P0 级缺口（严重，阻断规范一致性）

#### 缺口 P0-1：042 状态机命名与 auto-pm STATUS_FLOW 完全不一致
- **规范侧**：042 V2.2.0 §5.2 定义 12 个状态（pending_analysis/analyzing/pending_approval/approving/pending_implementation/implementing/pending_acceptance/accepting/completed/closed/rejected/archived）
- **实现侧**：auto-pm STATUS_FLOW 定义 11 个状态（draft/submitted/under_review/approved/conditionally_approved/rejected/implementing/pending_acceptance/accepting/completed/closed）
- **影响**：变更单文件中写入的状态值与 042 规范看板列标识不匹配；前端看板渲染需额外映射层；auto-pm 代码注释声称"对齐 PM-042 §5.2"但实际未对齐
- **证据**：models.py 第 93-98 行注释"对齐 PM-042 §5.2 状态机"，第 99-111 行 STATUS_FLOW 命名与 042 第 116-128 行看板列标识不一致

#### 缺口 P0-2：016 变更管理目录路径与 auto-pm 实现不一致
- **规范侧**：016 §4.1 定义变更管理目录为 `06_变更管理/`
- **实现侧**：auto-pm 使用三套路径（`00_项目管理/04_变更管理/01_变更单/`、`01_项目文档/03_执行过程/02_变更管理/`、`00_项目管理/04_变更管理/04_变更记录/`），均非 016 定义的 `06_变更管理/`
- **影响**：016 规范与 auto-pm 的变更单存放路径完全不一致；auto-pm 实际遵循 043 规范而非 016 规范；016 规范作为"通用项目结构模板"失去指导意义
- **证据**：016 第 52 行 `06_变更管理/`；change_service.py 第 519-524 行 `_get_change_file_path`；path_resolver.py 第 126-131 行 `_CHANGE_SEARCH_PATHS`

#### 缺口 P0-3：040 模板 §6 影响分析结构在 generator.py 中缺失
- **规范侧**：040 §6 定义 §6.1 项目约束影响表、§6.2 技术领域影响表、§6.3 变更传播链三个子表
- **实现侧**：generator.py 第 111-113 行仅输出 `## 6. 变更影响分析\n\n（待填写）`
- **影响**：用户需手动添加 §6 表格结构；parser.py 无法从 §6 提取影响分析数据；042 §5.4 要求的"跨领域影响评估"无法在变更单中落地；门禁规则无法校验影响分析
- **证据**：generator.py 第 111-113 行；040 第 104-148 行 §6 完整结构

### 4.2 P1 级缺口（重要，影响功能完整性）

#### 缺口 P1-1：040 模板 §10 章节编号错位
- **规范侧**：040 §10 定义 §10.1 验证项清单、§10.2 跨领域联动验证、§10.3 验证结论
- **实现侧**：generator.py 第 139-149 行输出 §10.1 验证项清单、§10.2 验证结论（跳过跨领域联动验证）
- **影响**：parser.py `_extract_verification_conclusion`（parser.py 第 428-465 行）匹配 §10.2 时会匹配到"验证结论"而非规范定义的"跨领域联动验证"；跨领域联动验证环节无落脚点
- **证据**：generator.py 第 139-149 行；040 第 180-199 行 §10 完整结构

#### 缺口 P1-2：040 模板 §11 版本详细变更说明章节缺失
- **规范侧**：040 §11 是版本详细变更说明（含 V1.0.0/V1.1.0/V2.0.0 历史版本说明），§12 才是附录
- **实现侧**：generator.py 未生成 §11 版本详细变更说明，直接输出 §11 附录（待填写）
- **影响**：生成的变更单缺少版本详细变更说明章节；章节编号错位（附录从 §12 错位为 §11）
- **证据**：generator.py 第 151-153 行；040 第 201-234 行 §11 版本详细变更说明

#### 缺口 P1-3：016 规范未覆盖 PLC 项目结构
- **规范侧**：016 V1.0.0 在 2026-03-14 明确"删除所有PLC相关内容，只保留Python部分"
- **实现侧**：auto-pm 同时支持 PLC 和 Python 两种技术栈的项目骨架生成，plc-standard 模板生成 `02_PLC程序/`、`03_HMI设计/`、`04_变更管理/`、`04_现场调试/`、`PRD/` 等目录
- **影响**：PLC 项目结构无通用规范依据；016 规范作为"通用项目结构模板"适用范围受限
- **证据**：016 第 26 行"删除所有PLC相关内容"；plc-standard 模板 copier.yml 第 1 行"用于生成符合 LSP-907 规范的 PLC 项目骨架"

#### 缺口 P1-4：python-tool 模板未生成 016 规范要求的完整目录结构
- **规范侧**：016 §4.1 要求 11 个顶层目录（00~10）
- **实现侧**：python-tool 模板只生成 `00_项目基础信息/`（1 个）+ `<package_name>/`（flat layout）+ `tests/`
- **影响**：生成的 Python 项目缺少 `01_项目文档/`、`05_部署文档/`、`06_变更管理/`、`07_交付文档/`、`08_技术知识库/` 等目录；与 016 规范要求不符
- **证据**：python-tool 模板 LS 结果；016 第 36-60 行 11 个顶层目录

#### 缺口 P1-5：042 archived 状态在 auto-pm 中缺失
- **规范侧**：042 §5.2 明确定义 `completed → archived` 和 `archived → [*]` 的流转
- **实现侧**：auto-pm STATUS_FLOW 中没有 archived 状态，completed 只能流转到 closed；STATUS_LABELS 也没有 archived 标签
- **影响**：变更单无法走归档流程；与 042 规范的"归档是最终状态"要求不符
- **证据**：models.py 第 99-111 行 STATUS_FLOW 无 archived；042 第 144-148 行状态机图

#### 缺口 P1-6：042 风险等级和缓解措施字段未在 auto-pm 中实现
- **规范侧**：042 §5.4.4 要求"风险等级分为：低（LOW）、中（MEDIUM）、高（HIGH）"和"必须制定相应的缓解措施"
- **实现侧**：auto-pm 无风险等级字段和缓解措施字段的定义和校验
- **影响**：042 §5.4 影响分析要求无法在 auto-pm 中落地；门禁规则无法校验风险等级和缓解措施
- **证据**：change_service.py 第 660-748 行 `_check_transition_guards` 无风险等级校验；042 第 184-185 行风险等级要求

### 4.3 P2 级缺口（改进，提升规范覆盖度）

#### 缺口 P2-1：042 AI辅助开发场景未在 auto-pm 中实现
- **规范侧**：042 V2.1.0 §11 新增 3 个 AI 辅助开发场景（§11.1 AI辅助代码生成、§11.2 批量规范同步、§11.3 自动化测试触发）
- **实现侧**：auto-pm 没有实现这些场景的自动化支持
- **影响**：042 §11 的自动化场景规范无法在 auto-pm 中落地
- **证据**：042 第 377-426 行 §11 完整内容；auto-pm 无对应实现

#### 缺口 P2-2：010 规范过于简略
- **规范侧**：010 V1.0.2 共 91 行，内容非常概括
- **实现侧**：auto-pm 的实现基于 042/043 等更具体的规范
- **影响**：010 规范作为"总纲"没有起到指导作用
- **证据**：010 全文 91 行

#### 缺口 P2-3：PM_SESSION 文件未在 010/016 规范中定义
- **规范侧**：010/016 规范均未定义 PM_SESSION 文件
- **实现侧**：auto-pm 两个模板都生成 `PM_SESSION_{{ project_id }}.md.jinja` 文件，作为 pm-workflow 技能的单一真源
- **影响**：PM_SESSION 文件的角色和结构无规范依据
- **证据**：python-tool 模板 PM_SESSION 第 1-65 行；plc-standard 模板 PM_SESSION 第 1-48 行；010/016 规范无 PM_SESSION 定义

#### 缺口 P2-4：generator.py 文档版本号与 040 模板不一致
- **规范侧**：040 模板当前版本 V2.1.0
- **实现侧**：generator.py 第 47 行输出 `**文档版本**：V1.0.0`
- **影响**：生成的变更单版本号与规范版本不匹配，影响规范版本追溯
- **证据**：generator.py 第 47 行；040 第 4 行 `version: "V2.1.0"`

#### 缺口 P2-5：040 模板 §3.4 "变更状态"字段为 auto-pm 扩展未在规范中定义
- **规范侧**：040 §3.4 申请信息表无"变更状态"字段
- **实现侧**：generator.py 第 82 行在 §3.4 增加 `| 变更状态 | {cr.status} |`
- **影响**：规范与实现不一致；该字段是 auto-pm 状态持久化的关键，应在规范中明确定义
- **证据**：generator.py 第 82 行；040 第 67-73 行 §3.4 无"变更状态"字段

---

## 5. 修订建议清单（按优先级分类）

### 5.1 P0 级修订建议（严重，必须修复）

#### 建议 P0-1：统一 042 状态机命名与 auto-pm STATUS_FLOW
**修订方向**（二选一）：
- **方案A（规范侧修订）**：042 V2.3.0 将状态机命名改为 auto-pm 的 `draft/submitted/under_review/approved/conditionally_approved/rejected/implementing/pending_acceptance/accepting/completed/closed/archived`，并补充 `conditionally_approved` 和 `archived` 状态的定义和流转
- **方案B（实现侧修订）**：auto-pm STATUS_FLOW 改为 042 的 `pending_analysis/analyzing/pending_approval/approving/pending_implementation/implementing/pending_acceptance/accepting/completed/closed/rejected/archived`，并移除 `conditionally_approved` 或在 042 中补充定义

**推荐方案A**，理由：
1. auto-pm 的 `draft/submitted/under_review` 命名更符合软件工程惯例
2. `conditionally_approved` 状态在 040 §8.2 审批结论中已有"有条件通过"选项，应在 042 状态机中补充
3. 042 的 `pending_analysis/analyzing` 区分度不高，可合并为 `draft/submitted`
4. 修订影响面：042 规范 §5.2 状态机图、看板列标识、STATUS_LABELS 中文标签

**涉及文件**：
- `042_通用变更管理流程规范_PM.md`（§5.2 状态机、看板列）
- `auto_pm/change/models.py`（STATUS_FLOW、STATUS_LABELS 注释更新）
- `auto_pm/change/parser.py`（状态推断逻辑）

#### 建议 P0-2：统一 016 变更管理目录路径与 auto-pm 实现
**修订方向**：016 V1.1.0 将变更管理目录从 `06_变更管理/` 改为 `00_项目管理/04_变更管理/`（与 043 V2.1.0 和 auto-pm 实现一致），并引用 043 规范作为详细目录结构依据。

**涉及文件**：
- `016_通用项目结构模板_PROJ.md`（§4.1 顶层目录结构、§4.2 目录说明）

#### 建议 P0-3：generator.py 补全 §6 影响分析结构
**修订方向**：generator.py `render` 方法（第 26-162 行）在 §6 部分补全 040 模板定义的三个子表结构：
- §6.1 项目约束影响表（5 维度×4 级程度）
- §6.2 技术领域影响表（7 领域逐项评估+关联变更单号）
- §6.3 变更传播链（可视化路径+关联变更单清单）

**涉及文件**：
- `auto_pm/change/generator.py`（第 111-113 行 §6 渲染逻辑）

### 5.2 P1 级修订建议（重要，应修复）

#### 建议 P1-1：generator.py 修正 §10 章节编号
**修订方向**：generator.py 第 139-149 行将 §10 改为三节结构：
- §10.1 验证项清单
- §10.2 跨领域联动验证
- §10.3 验证结论

**涉及文件**：
- `auto_pm/change/generator.py`（第 139-149 行 §10 渲染逻辑）
- `auto_pm/change/parser.py`（`_extract_verification_conclusion` 方法适配 §10.3）

#### 建议 P1-2：generator.py 补全 §11 版本详细变更说明
**修订方向**：generator.py 在 §10 之后、附录之前补全 §11 版本详细变更说明章节，附录改为 §12。

**涉及文件**：
- `auto_pm/change/generator.py`（第 151-153 行 §11 附录渲染逻辑）

#### 建议 P1-3：016 规范补充 PLC 项目结构定义
**修订方向**：016 V1.1.0 恢复 PLC 项目结构定义，或引用 LSP-907 规范作为 PLC 项目结构的详细依据，使 016 规范覆盖 PLC 和 Python 两种技术栈。

**涉及文件**：
- `016_通用项目结构模板_PROJ.md`（§4 项目结构模板、§5 Python项目源代码结构）

#### 建议 P1-4：python-tool 模板补全 016 规范要求的目录结构
**修订方向**：python-tool 模板补全 016 规范要求的目录（至少 `06_变更管理/`、`07_交付文档/`、`08_技术知识库/`），或在 016 规范中明确 Python 项目可简化哪些目录。

**涉及文件**：
- `templates/python-tool/template/`（补全目录）
- `016_通用项目结构模板_PROJ.md`（明确简化规则）

#### 建议 P1-5：auto-pm 补充 archived 状态
**修订方向**：auto-pm STATUS_FLOW 补充 `archived` 状态，定义 `completed → archived` 流转；STATUS_LABELS 补充 `archived: "已归档"` 标签。

**涉及文件**：
- `auto_pm/change/models.py`（第 99-111 行 STATUS_FLOW、第 117-129 行 STATUS_LABELS）

#### 建议 P1-6：auto-pm 实现风险等级和缓解措施字段
**修订方向**：
- 040 模板 §6.1 项目约束影响表增加"风险等级"和"缓解措施"字段
- auto-pm generator.py 在 §6.1 表格中渲染风险等级和缓解措施字段
- auto-pm parser.py 解析风险等级和缓解措施字段
- auto-pm `_check_transition_guards` 增加 submitted 状态的风险等级校验

**涉及文件**：
- `040_通用变更单模板_CHG.md`（§6.1 项目约束影响表）
- `auto_pm/change/generator.py`（§6.1 渲染逻辑）
- `auto_pm/change/parser.py`（§6.1 解析逻辑）
- `auto_pm/change/change_service.py`（`_check_transition_guards` 风险等级校验）

### 5.3 P2 级修订建议（改进，可修复）

#### 建议 P2-1：auto-pm 实现 042 §11 AI辅助开发场景
**修订方向**：auto-pm 实现 042 §11 定义的 3 个 AI 辅助开发场景的自动化支持：
- §11.1 AI辅助代码生成场景（差异项数量分级审批）
- §11.2 批量规范同步场景（影响评估+同步记录）
- §11.3 自动化测试触发场景（测试类型触发规则）

**涉及文件**：
- `auto_pm/change/`（新增 AI 场景模块）

#### 建议 P2-2：010 规范补充可执行条目
**修订方向**：010 V1.1.0 补充具体的可执行规范条目，引用 042/043/016 等具体规范作为详细依据，使 010 规范起到总纲指导作用。

**涉及文件**：
- `010_通用项目管理规范_PM.md`（全文扩充）

#### 建议 P2-3：010/016 规范定义 PM_SESSION 文件角色
**修订方向**：010 或 016 规范补充 PM_SESSION 文件的定义，包括角色（pm-workflow 技能单一真源）、结构（9 个章节）、命名规则（`PM_SESSION_<project_id>.md`）。

**涉及文件**：
- `010_通用项目管理规范_PM.md` 或 `016_通用项目结构模板_PROJ.md`（新增 PM_SESSION 章节）

#### 建议 P2-4：generator.py 文档版本号对齐 040 模板
**修订方向**：generator.py 第 47 行将 `**文档版本**：V1.0.0` 改为 `**文档版本**：V2.1.0`（或动态读取 040 模板版本号）。

**涉及文件**：
- `auto_pm/change/generator.py`（第 47 行）

#### 建议 P2-5：040 模板 §3.4 定义"变更状态"字段
**修订方向**：040 V2.2.0 在 §3.4 申请信息表中增加"变更状态"字段定义，明确该字段由 auto-pm 状态流转时自动写入，值为 STATUS_FLOW 中的合法状态标识。

**涉及文件**：
- `040_通用变更单模板_CHG.md`（§3.4 申请信息表）

---

## 6. 范围边界确认

### 6.1 审查范围
本次审查仅对 PM 规范体系（040/042/043/010/016）与 auto-pm V2.0 变更管理实现进行对接关系分析，**未修改任何规范文件本身**，**未修改任何 auto-pm 代码文件**。

### 6.2 未涉及范围
- 未涉及 LSP-907（PLC 技术栈规范）与 auto-pm plc-standard 模板的详细对接审查
- 未涉及 210/211/220（Python 技术栈规范）与 auto-pm python-tool 模板的详细对接审查
- 未涉及 041（版本变更台帐模板）与 auto-pm ledger_updater.py 的详细对接审查
- 未涉及 044/045（变更管理文档版本控制/流程执行指南）的审查
- 未涉及 auto-pm UI 层（ui/ 目录）与规范对接的审查
- 未涉及 auto-pm DB 层（db/ 目录）与规范对接的审查

### 6.3 文件读取状态
所有审查涉及的文件均已成功读取，无读取失败情况：
- ✓ 040_通用变更单模板_CHG.md（276 行）
- ✓ 042_通用变更管理流程规范_PM.md（481 行）
- ✓ 043_通用变更管理目录结构说明_PM.md（194 行）
- ✓ 010_通用项目管理规范_PM.md（91 行）
- ✓ 016_通用项目结构模板_PROJ.md（357 行）
- ✓ auto_pm/change/generator.py（210 行）
- ✓ auto_pm/change/change_service.py（845 行）
- ✓ auto_pm/change/models.py（208 行）
- ✓ auto_pm/change/parser.py（508 行）
- ✓ auto_pm/change/path_resolver.py（213 行）
- ✓ auto_pm/core/project_service.py（570 行）
- ✓ auto_pm/cli/project.py（350 行）
- ✓ auto_pm/cli/plc/__init__.py（278 行）
- ✓ templates/plc-standard/copier.yml
- ✓ templates/python-tool/copier.yml
- ✓ templates/python-tool/README.md
- ✓ templates/python-tool/template/PM_SESSION_{{ project_id }}.md.jinja
- ✓ templates/plc-standard/template/PM_SESSION_{{ project_id }}.md.jinja

### 6.4 建议后续工作
1. 优先处理 P0 级缺口（3 项），确保规范与实现的一致性
2. 在 P0 修复后处理 P1 级缺口（6 项），提升功能完整性
3. 根据资源情况处理 P2 级缺口（5 项），提升规范覆盖度
4. 建议在修订 042/040/016 规范时同步更新 spec_registry.json 中的版本号
5. 建议在修订 auto-pm 代码后补充对应的单元测试用例

---

**报告生成时间**：2026-06-21
**审查人**：PM 规范审查专家（Trae AI 辅助）
**报告版本**：V1.0.0
**审查范围**：PM 规范体系（040/042/043/010/016）与 auto-pm V2.0 变更管理实现对接
