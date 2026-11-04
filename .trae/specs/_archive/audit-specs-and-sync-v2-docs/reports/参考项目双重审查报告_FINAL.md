# 参考项目双重审查报告（FINAL）

> **报告版本**：FINAL
> **审查日期**：2026-06-21
> **审查工具**：auto-pm (SW-2026-008)
> **审查性质**：双重审查（既验证 auto-pm 管理能力，也审查项目自身问题）

---

## 1. 审查概述

### 1.1 审查目标

本次审查为"双重审查"，同时覆盖两个维度：

- **维度一（auto-pm 管理能力验证）**：验证 auto-pm 能否正确识别、管理这三个参考项目（项目列表、元数据读取、规范检查）。
- **维度二（项目自身问题审查）**：审查三个参考项目自身的问题（文档实质化、技术栈一致性、代码安全与规范）。

### 1.2 审查对象

| 项目 ID | 项目类型 | 技术栈 | 路径 |
|---------|----------|--------|------|
| DJ-2026-000 | PLC 正式项目 | plc | `0100_PLC自动化\DJ-2026-000` |
| SysLib | PLC 库项目 | plc | `0100_PLC自动化\01_SharedLibraries\SysLib` |
| SW-2026-004 | Python 项目 | python（auto-pm 识别为 unknown） | `01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-004_Python项目管理工具` |

### 1.3 审查方法

| 步骤 | 方法 |
|------|------|
| 管理能力验证 | 运行 `project list`、`project show <id>`、`plc check <id>` |
| 文档实质化审查 | 读取 PRD/REQ 模板与实际文件，对比占位符比例 |
| 代码问题审查 | 读取关键源码文件（auth、routes、impact_service） |
| 技术栈一致性 | 对比 PRD 声明技术栈与 requirements.txt 实际依赖 |

### 1.4 审查时间

- **审查日期**：2026-06-21
- **执行环境**：
  - 虚拟环境：`c:\Users\fubai\Desktop\My_Workspace\.venv\`（Python 3.11.9，pip 24.0）
  - auto-pm 项目路径：`01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-008_auto-pm_自动化项目管理工具`

### 1.5 关键环境问题（影响所有 auto-pm 命令执行）

直接运行 `python -m auto_pm` 会因 site 模块初始化失败而崩溃：

```
Fatal Python error: init_import_site: Failed to import the site module
UnicodeDecodeError: 'gbk' codec can't decode byte 0xaa in position 48: illegal multibyte sequence
```

- 该错误发生在 Python 解释器加载 site 模块阶段（`site.addpackage` 处理 .pth 文件时），早于任何 auto-pm 代码执行。
- 设置 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`、`python -X utf8` 均无效（site 模块在环境变量生效前即崩溃）。
- 检查 `.venv\Lib\site-packages\` 仅发现两个 ASCII 编码的 .pth 文件（`a1_coverage.pth`、`distutils-precedence.pth`），未定位到含 0xaa 字节的源头。
- **绕过方案**：使用 `python -S`（跳过 site 模块）+ 手动注入 site-packages 路径的方式执行 auto-pm 命令：

  ```
  python -S -c "import sys; sys.path.insert(0, r'...site-packages'); from auto_pm.cli.__main__ import cli; cli(['-w', r'...', 'project', 'list'], standalone_mode=False)"
  ```

- 本报告所有 auto-pm 命令输出均基于此绕过方案取得。该环境问题本身已作为改进建议记录（见 §5 P0-1）。

---

## 2. DJ-2026-000 双重审查发现

### 2.1 auto-pm 管理能力验证结果

#### 2.1.1 project list（识别能力）

```
┃ DJ-2026… ┃ DJ-2026… ┃ plc ┃ V1.0.0 ┃ plc_json ┃ 0100_PL… ┃
```

- **结论**：✅ 能识别。DJ-2026-000 被正确识别为 `plc` 技术栈，来源 `plc_json`。
- **异常**：列表中版本显示为 `V1.0.0`，但 `project show` 与 `.plc.json` 实际值为 `2.0.0`（见 2.1.2），存在版本显示不一致。

#### 2.1.2 project show DJ-2026-000（元数据读取）

```
项目ID: DJ-2026-000
名称:   DJ-2026-000
技术栈: plc
版本:   2.0.0
描述:   SysLib公共库FB测试套件 - 验证FB_1011/FB_1012/FB_1014等共享库功能块
来源:   plc_json
路径:   c:\Users\fubai\Desktop\My_Workspace\0100_PLC自动化\DJ-2026-000
```

- **结论**：✅ 元数据读取正确。版本、描述、路径均与 `.plc.json` 一致。
- **问题**：`名称` 字段值为 `DJ-2026-000`，与项目 ID 完全相同，未填写实际项目名称（应为"SysLib公共库FB测试套件"之类）。`.plc.json` 中也只有 `name: "DJ-2026-000"`，未区分 ID 与名称。

#### 2.1.3 plc check DJ-2026-000（LSP-907 检查）

```
项目检查完成: DJ-2026-000 - pass=13 warn=0 fail=0
Pass=13 Warn=0 Fail=0 -> ALL PASS
```

| 检查项 | 状态 | 说明 |
|--------|------|------|
| .plc.json | PASS | 配置完整: name=DJ-2026-000, version=2.0.0 |
| .plc.json libraries[../01_SharedLibraries/SysLib] | PASS | 库路径有效 |
| PM_SESSION | PASS | PM_SESSION_DJ-2026-000.md 存在 |
| PRD 目录 | PASS | PRD/ 目录存在 |
| PRD/需求分析文档_REQ.md | PASS | 存在 |
| PRD/接口文档_INT.md | PASS | 存在 |
| PRD/详细设计说明书_DSN.md | PASS | 存在 |
| PRD/技术方案文档_TEC.md | PASS | 存在 |
| 目录 02_PLC程序/通用ST程序及变量表 | PASS | 存在 |
| 目录 03_HMI设计 | PASS | 存在 |
| 目录 04_现场调试 | PASS | 存在 |
| 目录 04_变更管理 | PASS | 存在 |
| 目录 PRD | PASS | 存在 |

- **结论**：✅ 13 项全部 PASS。
- **关键缺陷**：所有 PRD 文档检查项仅验证"文件存在"，不验证"内容实质化"。REQ 文档全是"待填写"占位符仍判 PASS（详见 2.2）。

### 2.2 项目自身问题：REQ 空模板问题

#### 2.2.1 实际 REQ 文件内容

文件：`0100_PLC自动化\DJ-2026-000\PRD\需求分析文档_REQ.md`

该文档共 47 行，实质内容全部为占位符：

| 章节 | 内容 |
|------|------|
| 3.1 项目来源 | 待填写 |
| 3.2 业务目标 | 待填写 |
| 4.1 核心功能 | 待填写 |
| 4.2 非功能需求 | 待填写 |
| 5. 接口需求 | 待填写 |
| 6. 约束条件 | 待填写 |
| 编制人 | 待填写 |
| 审核人 | 待填写 |

文档 frontmatter 标注 `lifecycle: draft`，但 auto-pm 的 plc check 未对此做任何提示。

#### 2.2.2 版本显示不一致问题

- `project list` 显示版本：`V1.0.0`
- `project show` 显示版本：`2.0.0`
- `.plc.json` 实际值：`2.0.0`

同一项目在 list 与 show 两个命令间版本显示不一致，存在显示逻辑 bug。

### 2.3 根因分析

**根因一：auto-pm 模板未引导实质化填写**

模板文件：`SW-2026-008.../templates/plc-standard/template/PRD/需求分析文档_REQ.md.jinja`

模板内容同样全是占位符（`待定义`、`待补充`），仅提供骨架结构，未提供：
- 填写指引（每个字段应填什么、如何判断填好）
- 示例值（不同业务线/技术栈的参考样例）
- 完成度校验提示（哪些字段为必填、哪些可留空）

模板片段：

```jinja
### 1.2 项目目标
- 待定义

### 1.3 项目范围
- 待定义

## 2. 功能需求
### 2.2 功能详细描述
待补充
```

**根因二：auto-pm 检查器只验存在性不验内容**

`plc check` 对 `PRD/需求分析文档_REQ.md` 的检查逻辑仅为"文件是否存在"，不检查：
- 占位符比例（"待填写"/"待定义"占比）
- 必填字段是否仍为占位符
- 文档生命周期状态（draft/review/stable）是否与项目阶段匹配

**根因三：用户未填写**

项目初始化后，REQ 文档停留在模板初始状态，未进行实质化填写。这是用户侧问题，但工具侧缺乏提醒机制放大了该问题。

### 2.4 改进建议（针对 DJ-2026-000）

| 建议 | 说明 |
|------|------|
| REQ 实质化 | 将 REQ 文档中的"待填写"替换为实际项目背景、功能需求等内容 |
| 名称字段修正 | `.plc.json` 的 `name` 应填写实际项目名称（如"SysLib公共库FB测试套件"），而非复用项目 ID |
| 版本显示一致性 | 修复 `project list` 与 `project show` 的版本显示不一致问题（list 显示 V1.0.0，show 显示 2.0.0） |

---

## 3. SysLib 双重审查发现

### 3.1 auto-pm 管理能力验证结果

#### 3.1.1 project list / project show（识别能力）

```
项目ID: SysLib
名称:   SysLib
技术栈: plc
版本:   1.0.0
描述:   PLC共享函数库 - 定时器、计数器、边沿检测、时间转换等基础功能块
来源:   plc_json
路径:   c:\Users\fubai\Desktop\My_Workspace\0100_PLC自动化\01_SharedLibraries\SysLib
```

- **结论**：✅ 能识别。SysLib 被正确识别为 `plc` 技术栈。

#### 3.1.2 plc check SysLib（LSP-907 检查）

```
项目检查完成: SysLib - pass=12 warn=1 fail=0
Pass=12 Warn=1 Fail=0 -> ALL PASS
```

| 检查项 | 状态 | 说明 |
|--------|------|------|
| .plc.json | PASS | 配置完整: name=SysLib, version=1.0.0 |
| **.plc.json libraries** | **WARN** | **未配置 libraries 字段，引用 SysLib 时需添加（LSP-907 §1.2）** |
| PM_SESSION | PASS | PM_SESSION_SysLib.md 存在 |
| PRD/需求分析文档_REQ.md | PASS | 存在 |
| PRD/接口文档_INT.md | PASS | 存在 |
| PRD/详细设计说明书_DSN.md | PASS | 存在 |
| PRD/技术方案文档_TEC.md | PASS | 存在 |
| 其余目录检查 | PASS | 存在 |

- **结论**：✅ 12 PASS + 1 WARN。
- **误报问题**：SysLib 本身是**库项目**（被其他项目引用的共享库），其 `.plc.json` 中 `libraries: []` 为空是合理的——它不引用其他库，而是被 DJ-2026-000 等项目引用。但 auto-pm 仍对"未配置 libraries 字段"发出 WARN，属于**库项目场景的误报**。

### 3.2 项目自身问题

#### 3.2.1 REQ 空模板问题（同 DJ-2026-000）

文件：`0100_PLC自动化\01_SharedLibraries\SysLib\PRD\需求分析文档_REQ.md`

内容与 DJ-2026-000 的 REQ 完全相同——全部为"待填写"占位符，`lifecycle: draft`。根因同 §2.3。

#### 3.2.2 .plc.json 配置

```json
{
  "name": "SysLib",
  "description": "PLC共享函数库 - 定时器、计数器、边沿检测、时间转换等基础功能块",
  "version": "1.0.0",
  "libraries": []
}
```

- `libraries: []` 为空数组，对库项目本身合理。
- 缺少标识"本项目是库项目"的字段（如 `project_type: "library"`），导致 auto-pm 无法区分"库项目"与"应用项目"，进而产生 3.1.2 的误报。

### 3.3 库项目管理差异分析

#### 3.3.1 SysLib 的实际结构

SysLib 作为共享函数库，其内部按功能分类组织了多个 FB/FC：

| 分类 | 内容 | 文档情况 |
|------|------|----------|
| actuator/ | FB_1011_CylinderControl、FB_1012_ConveyorMotor、FB_1013_NinetyDegreeTransfer、FB_1014_StationConveyor | 每个 FB 有独立 PRD/ 目录，含 REQ/INT/DSN/TEC 文档 |
| communication/ | FB_1020_EquipmentHandshake | 有 IFC/DSN 文档 |
| convert/ | FC_DINT_TO_TIME 等 4 个转换函数 | 无独立文档 |
| counter/ | FB_CTD/FB_CTU/FB_CTUD | 无独立文档 |
| edge/ | FB_F_TRIG/FB_R_TRIG | 无独立文档 |
| timer/ | FB_TOF/FB_TON/FB_TONR/FB_TP | 无独立文档 |
| types/ | ST_Cylinder 等 9 个结构体 | 仅 README.md |

#### 3.3.2 auto-pm 对库项目管理的缺失

| 维度 | 当前表现 | 缺失能力 |
|------|----------|----------|
| 项目类型识别 | 不区分库项目与应用项目 | 无法识别 `project_type: library`，对库项目套用应用项目检查规则 |
| libraries 误报 | 对 SysLib 的空 libraries 发 WARN | 库项目本身不应要求 libraries 字段 |
| FB 级文档检查 | 不检查 | SysLib 有 4 个 actuator FB 各带完整 PRD 文档，auto-pm 不检查 FB 级文档完整性 |
| 库版本管理 | 不检查 | SysLib 各 FB 有独立版本号（V13.0.0 等），auto-pm 不追踪 FB 级版本 |
| 引用关系追踪 | 仅检查 libraries 路径有效 | 不反向追踪"哪些项目引用了 SysLib"（DJ-2026-000 引用 SysLib，但 SysLib 侧无记录） |

### 3.4 正面发现：FB 接口文档质量极高

以 `FB_1011_CylinderControl/PRD/接口文档_INT.md` 为例，该文档质量极高：

- 文档版本 V13.0.0，lifecycle: stable
- 完整的变更记录（V9.2.0 ~ V13.0.0 共 5 个版本记录）
- 详细的电磁阀类型定义表、真值表、极性取反说明
- 关联源码与结构体版本号
- 遵循规范标注（LSP-905-V1.0.2, LSP-904-V1.2.0, LSP-903-V2.1.0）

这与项目级 REQ 文档的"全待填写"形成鲜明对比：**FB 级文档实质化良好，项目级文档停留在模板**。

### 3.5 改进建议（针对 SysLib）

| 建议 | 说明 |
|------|------|
| REQ 实质化 | 填写 SysLib 的实际需求（覆盖哪些功能块、适用 PLC 型号、性能要求等） |
| 增加项目类型字段 | `.plc.json` 增加 `project_type: "library"` 标识，区分库项目与应用项目 |
| 补充 convert/counter/edge/timer 文档 | 这些 FB/FC 无独立 PRD 文档，建议补充至少接口文档 |

---

## 4. SW-2026-004 双重审查发现

### 4.1 auto-pm 管理能力验证结果

#### 4.1.1 project list / project show（识别能力）

```
项目ID: SW-2026-004
名称:   SW-2026-004_Python项目管理工具
技术栈: unknown
版本:
描述:
来源:   pm_session
路径:   c:\Users\fubai\Desktop\My_Workspace\01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-004_Python项目管理工具
```

- **结论**：⚠️ 能识别但技术栈丢失。项目被识别（来源 `pm_session`），但：
  - 技术栈显示为 `unknown`（实际是 Python 项目）
  - 版本为空
  - 描述为空

#### 4.1.2 技术栈识别失败的根因

| 检查项 | 结果 |
|--------|------|
| PM_SESSION 文件 | ❌ 不存在（项目根目录及子目录均未找到 `PM_SESSION_SW-2026-004.md`） |
| pyproject.toml | ❌ 不存在（auto-pm 的 python-tool 模板会生成 `pyproject.toml.jinja`，但本项目无此文件） |
| .plc.json | ❌ 不存在（本项目是 Python 项目，不应有 .plc.json） |
| 项目结构 | 不符合 auto-pm python-tool 模板（无 `{{ package_name }}/` 结构，无 `.copier-answers.yml`） |

auto-pm 仅通过目录命名约定（`SW-2026-004_*`）和 pm_session 启发式识别到该项目，但无法判定技术栈，因此标记为 `unknown`。

**影响**：由于技术栈为 `unknown`，auto-pm 无法对本项目执行 Python 规范检查（`plc check` 仅适用于 plc 项目，Python 项目无对应检查命令可用）。

#### 4.1.3 技术栈不符检测能力

| 维度 | PRD 声明 | 实际代码 | auto-pm 能否识别 |
|------|----------|----------|------------------|
| GUI 框架 | PyQt5（PRD §1 第20行） | PyQt5==5.15.10（requirements.txt 第1行） | ❌ 无法识别（技术栈为 unknown） |
| GUI 框架（PRD 内部矛盾） | PySide6（PRD §2.2 第44行） | PyQt5 | ❌ 无法识别 PRD 内部矛盾 |
| Web 框架 | Flask/Django（PRD §2.2 第44行） | Flask==3.0.2（requirements.txt 第2行） | ❌ 无法识别 |

PRD 自身存在技术栈声明矛盾：第20行写 `PyQt5`，第44行写 `PySide6`。实际代码使用 `PyQt5`。auto-pm 完全无法检测此类不符，因为：

1. 项目技术栈被识别为 `unknown`，不触发任何技术栈相关检查。
2. auto-pm 没有"PRD 声明技术栈 vs 实际依赖一致性检查"能力。

### 4.2 项目自身问题清单

#### 4.2.1 PRD 声明 PySide6 实际 PyQt5（文档矛盾）

文件：`00_项目基础信息\01-产品需求文档_PRD.md`

| 位置 | 声明 |
|------|------|
| 第20行 | `**产品类型**：本地桌面应用（PyQt5） + CLI命令行工具` |
| 第44行 | `软件开发（SW）：Python Web(Flask/Django)、Python GUI(PySide6)、Python数据分析` |

PRD 内部对 GUI 框架的声明矛盾：第20行说 PyQt5，第44行说 PySide6。实际 `requirements.txt` 使用 `PyQt5==5.15.10`。

#### 4.2.2 UserStore 硬编码 + 密码明文写在注释（安全问题）

文件：`03_主程序\01_主程序核心代码\src\api\auth.py`

```python
# 第25行注释
# ==================== 用户存储（临时，生产环境应使用数据库） ====================

# 第36-47行：硬编码用户名和密码哈希
self._users: Dict[str, Dict[str, Any]] = {
    "admin": {
        "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYA.qGZvKG6G",  # admin123
        "role": "admin",
        "enabled": True
    },
    "user": {
        "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYA.qGZvKG6G",  # 同样使用admin123，实际应不同
        "role": "user",
        "enabled": True
    }
}

# 第80行：全局单例
user_store = UserStore()
```

**问题**：

1. **密码明文泄露在注释中**：第38行注释 `# admin123`、第43行注释 `# 同样使用admin123` 直接暴露了明文密码，违反安全红线（禁止在代码中硬编码密码、禁止在日志/注释中输出敏感信息）。
2. **硬编码用户凭证**：用户名、密码哈希、角色全部硬编码在源码中，未使用数据库存储。
3. **admin 与 user 使用相同密码**：两个账户密码哈希完全相同（均为 admin123），违背最小权限原则。
4. **内存存储不持久化**：`UserStore` 为内存字典，`add_user`/`update_password` 的修改在进程重启后丢失。
5. **全局单例**：`user_store = UserStore()` 全局实例，难以测试和替换。

#### 4.2.3 API 路由无 auth 保护（安全漏洞）

抽查三个路由文件：

| 路由文件 | 是否导入 auth | 是否使用 @auth_required | 问题 |
|----------|--------------|----------------------|------|
| routes/projects.py | ✅ 是（第12行） | ✅ 是（第18、59行） | 无 |
| routes/defects.py | ❌ 否 | ❌ 否 | **所有接口无认证保护** |
| routes/library_changes.py | ❌ 否 | ❌ 否 | **所有接口无认证保护** |

**问题**：

1. `defects.py` 完全未导入 `auth_required`，所有缺陷管理接口（GET/POST/PUT/DELETE）可被未认证访问。
2. `library_changes.py` 同样未导入 `auth_required`，总库变更创建/查询接口无认证。
3. 同一项目内 auth 保护策略不一致，部分接口安全、部分接口裸奔，属于安全漏洞。

#### 4.2.4 影响分析结果未持久化（功能未完成）

文件：`03_主程序\01_主程序核心代码\src\services\impact_service.py`

```python
# 第40-46行：创建 ImpactAssessment 对象
assessment = ImpactAssessment(
    assessment_id=assessment_id,
    change_id=change_id,
    affected_components=affected_components,
    risk_level=risk_level,
    mitigation_plan=mitigation_plan
)

# 第48行：注释明确承认未保存
# 这里需要实现保存逻辑，暂时返回结果

# 第50-57行：仅返回字典，不持久化
return {
    "assessment_id": assessment_id,
    "change_id": change_id,
    ...
}
```

**问题**：

1. `ImpactAssessment` 对象创建后未调用任何 DAO/Repository 保存方法，直接被丢弃。
2. 第48行注释 `# 这里需要实现保存逻辑，暂时返回结果` 明确承认这是未完成功能。
3. 影响分析结果无法追溯——每次查询变更影响都需重新分析，历史评估结果丢失。
4. `assessment_id` 使用 `uuid.uuid4().hex[:8]` 生成，因未持久化，重启后无法通过 ID 查询。

### 4.3 改进建议（针对 SW-2026-004）

| 优先级 | 建议 | 说明 |
|--------|------|------|
| P0 | 移除 auth.py 中的密码明文注释 | 第38、43行注释 `# admin123` 必须删除，违反安全红线 |
| P0 | UserStore 改用数据库存储 | 替换内存字典为 DAO 持久化，参考项目中已有的 `change_dao.py` 模式 |
| P0 | 补全 defects.py / library_changes.py 的 auth 保护 | 所有写接口至少加 `@auth_required`，管理操作加 `@role_required` |
| P1 | 实现影响分析持久化 | impact_service.py 第48行，调用 ImpactAssessment 对应的 DAO 保存 |
| P1 | 修正 PRD 技术栈声明 | 统一为 PyQt5（与 requirements.txt 一致），或迁移到 PySide6 后更新 PRD |
| P1 | 补充 pyproject.toml | 使 auto-pm 能识别技术栈为 python，启用 Python 规范检查 |

---

## 5. auto-pm 改进建议汇总（按优先级分类）

### 5.1 P0（高优先级 - 阻断使用或安全风险）

| 编号 | 问题描述 | 改进建议 | 建议纳入版本 | 依据 | 涉及项目 |
|------|----------|----------|--------------|------|----------|
| P0-1 | `python -m auto_pm` 因 site 模块 GBK 编码崩溃，标准命令完全无法运行，需 `python -S` 绕过 | 修复 site 模块加载阶段的编码处理；或在 auto-pm 启动脚本中显式设置 `PYTHONUTF8=1` 并提供 `.pth` 文件清理工具；定位含 0xaa 字节的 .pth 文件并修复 | SW-2026-008 下一迭代 | 严重影响可用性，标准命令完全无法运行 | auto-pm 自身 |
| P0-2 | plc check 仅验证 PRD 文档"存在性"，不验证"内容实质化"，REQ 全为"待填写"仍 PASS | plc check 增加"文档实质化"检查：①占位符比例检查（"待填写"/"待定义"占比 > 50% 则 WARN）；②必填字段检查；③lifecycle 状态与项目阶段匹配检查 | SW-2026-008 下一迭代 | 检查结果误导用户认为文档已就绪 | DJ-2026-000、SysLib |
| P0-3 | Python 项目无任何规范检查命令可用，SW-2026-004 技术栈识别为 unknown | 增加 `auto-pm python check <id>` 命令，覆盖：①pyproject.toml 完整性；②依赖安全扫描；③PRD 技术栈一致性；④代码规范（ruff/flake8 集成） | SW-2026-008 下一迭代 | Python 项目完全无法用 auto-pm 检查 | SW-2026-004 |

### 5.2 P1（中优先级 - 管理能力缺失）

| 编号 | 问题描述 | 改进建议 | 建议纳入版本 | 依据 | 涉及项目 |
|------|----------|----------|--------------|------|----------|
| P1-1 | 不区分库项目与应用项目，对 SysLib 的空 libraries 误报 WARN | `.plc.json` 增加 `project_type: "library" \| "application"` 字段；plc check 根据 project_type 跳过库项目不必要的检查项 | SW-2026-008 下一迭代 | 库项目应有不同检查规则 | SysLib |
| P1-2 | 不检查 FB 级文档完整性，SysLib 有 4 个 actuator FB 各带完整 PRD 但 auto-pm 不检查 | 增加 FB 级文档检查：扫描 `actuator/`、`communication/` 等子目录下的 FB_*/PRD/ 目录，验证 REQ/INT/DSN/TEC 文档存在性与实质化 | SW-2026-008 下一迭代 | FB 级文档是库项目的核心资产 | SysLib |
| P1-3 | 无"PRD 声明技术栈 vs 实际依赖一致性检查"能力，SW-2026-004 PRD 声明 PySide6/PyQt5 矛盾且实际用 PyQt5，auto-pm 无法发现 | 增加 tech_stack_consistency 检查器：解析 PRD 中声明的技术栈关键字，对比 requirements.txt/pyproject.toml 实际依赖，发现不一致或 PRD 内部矛盾时 WARN | SW-2026-008 下一迭代 | PRD 与代码技术栈漂移会导致开发误导 | SW-2026-004 |
| P1-4 | project list 与 project show 版本显示不一致，DJ-2026-000 在 list 显示 V1.0.0，show 显示 2.0.0 | 修复 project list 的版本读取逻辑，确保与 project show 一致（应都读取 `.plc.json` 的 version 字段） | SW-2026-008 下一迭代 | 同一项目版本显示不一致影响信任度 | DJ-2026-000 |
| P1-5 | REQ 模板全为"待定义"占位符，无引导用户实质化填写 | REQ 模板增加：①每个字段的填写指引注释；②不同业务线/技术栈的示例值；③必填字段标记；④完成度自检清单 | SW-2026-008 下一迭代 | 模板缺乏引导导致用户停留在初始状态 | DJ-2026-000、SysLib |
| P1-6 | Python 项目识别能力缺失，SW-2026-004 无 pyproject.toml 导致技术栈识别为 unknown | 增加 Python 项目识别：①探测 pyproject.toml/setup.py/requirements.txt；②即使无 pyproject.toml，存在 requirements.txt 也应识别为 python 技术栈 | SW-2026-008 下一迭代 | Python 项目识别失败导致后续检查无法执行 | SW-2026-004 |

### 5.3 P2（低优先级 - 体验优化）

| 编号 | 问题描述 | 改进建议 | 建议纳入版本 | 依据 | 涉及项目 |
|------|----------|----------|--------------|------|----------|
| P2-1 | project show 未提示名称=ID 的情况，DJ-2026-000 名称与 ID 相同未填写实际名称 | project show 检测到 name == id 时输出 WARN："项目名称与 ID 相同，建议填写实际项目名称" | SW-2026-008 后续迭代 | 提醒用户完善元数据 | DJ-2026-000 |
| P2-2 | REQ 文档 lifecycle: draft 但 plc check 无任何提示 | plc check 读取文档 frontmatter 的 lifecycle 字段，draft 状态文档在项目进入测试/发布阶段时 WARN | SW-2026-008 后续迭代 | 文档生命周期管理 | DJ-2026-000、SysLib |
| P2-3 | 不支持库项目反向引用追踪，DJ-2026-000 引用 SysLib 但 SysLib 侧无反向引用记录 | 建立 workspace 级引用关系索引：扫描所有项目的 libraries 字段，生成反向引用图，project show 时显示"被 N 个项目引用" | SW-2026-008 后续迭代 | 库项目影响分析需要 | SysLib |
| P2-4 | project list 表格版本列被截断，无法完整查看版本号 | project list 增加宽格式选项 `--wide` 或自动适应终端宽度，完整显示版本号 | SW-2026-008 后续迭代 | 体验优化 | 全部 |

### 5.4 改进建议优先级分布

| 优先级 | 数量 | 涉及领域 |
|--------|------|----------|
| P0 | 3 | 环境崩溃、文档实质化检查、Python 检查命令 |
| P1 | 6 | 库项目管理、FB 级检查、技术栈一致性、版本显示、模板引导、Python 识别 |
| P2 | 4 | 名称提示、lifecycle 提示、反向引用、表格显示 |
| **合计** | **13** | — |

---

## 6. 范围边界确认

### 6.1 本次审查的范围

- ✅ 运行 auto-pm 命令验证管理能力（project list / show / plc check）
- ✅ 读取并审查三个项目的文档与代码文件
- ✅ 分析问题根因并提出改进建议
- ✅ 输出审查报告到指定文件

### 6.2 本次审查未做的事项（边界确认）

- ❌ **未修改任何项目代码**：DJ-2026-000、SysLib、SW-2026-004 的所有文件均保持原样，未做任何编辑。
- ❌ **未修改 auto-pm 代码**：仅运行 auto-pm 命令进行验证，未修改其源码。
- ❌ **未修复环境问题**：site 模块 GBK 编码崩溃仅通过 `python -S` 绕过，未修复根因。
- ❌ **未运行测试**：未执行任何项目的测试套件。
- ❌ **未提交 Git 变更**：未执行任何 git add/commit/push 操作。

### 6.3 审查局限性

1. **编码问题影响**：由于 `python -m auto_pm` 无法直接运行，所有命令通过 `python -S` 绕过方式执行，可能与标准运行环境行为有细微差异（site 模块未加载），但核心功能验证结果可信。
2. **路由抽查范围**：SW-2026-004 的 routes 目录共 9 个文件，本次仅抽查 3 个（projects.py、defects.py、library_changes.py），其余路由（libraries.py、library_dashboard.py、plugins.py、specs.py、templates.py）未逐一检查 auth 保护情况。
3. **FB 级文档抽查范围**：SysLib 仅深入读取了 FB_1011_CylinderControl 的接口文档，其余 FB（1012/1013/1014/1020）仅确认文件存在，未深入审查内容质量。

---

*报告结束*
