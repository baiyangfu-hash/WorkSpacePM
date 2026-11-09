# 技能架构重构：pm-workflow 唯一入口 + 跨技能协同

## Why
当前三个技能（pm-workflow、fullstack-engineer、plc-electrical-engineer）各自独立检查 cockpit 上下文，入口分散，~43% 内容重复。需要将 pm-workflow 定位为驾驶舱唯一入口和统筹者，fullstack/plc 变为纯执行者，并设计清晰的跨技能切换流程。

## What Changes
- pm-workflow 成为驾驶舱唯一对接技能（唯一的 ai_context.json 消费者）
- fullstack/plc 删除各自的 cockpit 上下文检查逻辑
- 新增跨技能上下文传递机制
- 新增技能→驾驶舱反馈通道（pm-workflow 统一收集）
- **新增 HTML 原型设计能力**：pm-workflow 作为产品型项目经理，统一负责原型设计（全栈 Web UI 原型 + PLC HMI 原型），fullstack/plc 接收原型后进入编码实现
- **BREAKING**：fullstack/plc 的 item 1.5 / Step 0.5 将被移除

## Impact
- Affected specs: workspace-evaluation（评估报告）
- Affected code: pm-workflow/SKILL.md, fullstack-engineer/SKILL.md, plc-electrical-engineer/SKILL.md
- Affected cockpit: AiContextBridge（可能需要双向扩展）

---

## 一、完整任务执行流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         驾驶舱（auto-pm QML GUI）                            │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ChangeCenterView                                                   │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │ 变更单: CHG-PLC-2026-001  标题: 修复阀门控制时序错误         │  │   │
│  │  │ 领域: PLC  状态: draft  项目: DJ-2026-005                    │  │   │
│  │  │                                      [🤖 AI 辅助] ←── 点击   │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                          ① AiContextBridge.writeAiContext(...)              │
│                                    │                                        │
│                                    ▼                                        │
│                    ┌──────────────────────────────┐                         │
│                    │ .auto-pm/ai_context.json     │                         │
│                    │ {                            │                         │
│                    │   active_project: {          │                         │
│                    │     id: "DJ-2026-005",       │                         │
│                    │     stack: "plc"             │                         │
│                    │   },                         │                         │
│                    │   active_change: {           │                         │
│                    │     number: "CHG-PLC-...",   │                         │
│                    │     domain: "PLC",           │                         │
│                    │     title: "修复阀门..."     │                         │
│                    │   },                         │                         │
│                    │   active_page: "changeCenter"│                         │
│                    │ }                            │                         │
│                    └──────────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                          ② 用户对 AI 说话
                     "帮我推进这个变更"
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      pm-workflow（唯一入口 + 统筹者）                        │
│                                                                             │
│  Step 0: 激活 venv                                                          │
│      │                                                                      │
│      ▼                                                                      │
│  Step 0.5: 检查 .auto-pm/ai_context.json                                    │
│      │                                                                      │
│      ├─ 存在 ──→ ③ 读取上下文                                              │
│      │   ├─ project: DJ-2026-005 (plc)                                      │
│      │   ├─ change: CHG-PLC-2026-001 (PLC域, DEF)                           │
│      │   └─ page: changeCenter → 推断模式: 变更/缺陷/发布                    │
│      │                                                                      │
│      │   ④ 跳过 Step 0（project show/PM_SESSION/健康检查）                  │
│      │   ⑤ 跳过 Step 1（模式选择）                                          │
│      │   ⑥ 跳过 Step 2（最小提问）                                          │
│      │                                                                      │
│      │   ⑦ 域判断: domain == "PLC"                                          │
│      │      │                                                               │
│      │      │  ⑧ 构建 skill_context（传递摘要）                             │
│      │      │     ┌─────────────────────────────┐                           │
│      │      │     │ {                           │                           │
│      │      │     │   project_id: "DJ-2026-005",│                           │
│      │      │     │   change_number: "CHG-PLC..",│                          │
│      │      │     │   change_title: "修复阀门...",│                          │
│      │      │     │   domain: "PLC",             │                           │
│      │      │     │   nature: "DEF",             │                           │
│      │      │     │   mode: "变更/缺陷/发布",     │                           │
│      │      │     │   pm_summary: "已跳过上下文.."│                           │
│      │      │     │ }                           │                           │
│      │      │     └─────────────────────────────┘                           │
│      │      │                                                               │
│      │      │  ⑨ 调用 Skill: plc-electrical-engineer                       │
│      │      │     传递 skill_context 作为 prompt 的一部分                   │
│      │      │                                                               │
│      │      └─ 不存在 ──→ 走原有完整流程（不受影响）                        │
│      │                                                                      │
│      ▼                                                                      │
│  [等待子技能执行完成...]                                                     │
│      │                                                                      │
│      ▼                                                                      │
│  Step 4: 同步回写 PM_SESSION §6-§9                                          │
│      │                                                                      │
│      ▼                                                                      │
│  ⑫ 收集子技能执行结果 → 写入 cockpit 反馈                                    │
│     .auto-pm/ai_feedback.json                                               │
│      │                                                                      │
│      ▼                                                                      │
│  输出摘要给用户                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
          │                                            │
          │ ⑨ Skill: plc-electrical-engineer           │ ⑨ Skill: fullstack-engineer
          ▼                                            ▼
┌──────────────────────────────┐    ┌──────────────────────────────┐
│  plc-electrical-engineer     │    │  fullstack-engineer           │
│  （纯执行者）                 │    │  （纯执行者）                  │
│                              │    │                              │
│  ⑩ 接收 pm 传递的上下文       │    │  ⑩ 接收 pm 传递的上下文       │
│     - 不读取 ai_context.json │    │     - 不读取 ai_context.json │
│     - 不读取 PM_SESSION      │    │     - 不读取 PM_SESSION      │
│     - 不激活 venv（pm 已做）  │    │     - 不激活 venv（pm 已做）  │
│                              │    │                              │
│  Step 2: 任务路由             │    │  Step 1: 确定模式             │
│      │                       │    │      │                       │
│      ▼                       │    │      ▼                       │
│  Step 3: 代码审查/修改        │    │  Step 2: 给出方案             │
│      │                       │    │      │                       │
│      ▼                       │    │      ▼                       │
│  Step 4: 门禁实测 (plc check) │    │  Step 3: 实施                 │
│      │                       │    │      │                       │
│      ▼                       │    │      ▼                       │
│  ⑪ 返回结果给 pm-workflow     │    │  ⑪ 返回结果给 pm-workflow     │
│     - changed_files          │    │     - changed_files          │
│     - lint_result            │    │     - lint_result            │
│     - test_result            │    │     - test_result            │
│     - risks                  │    │     - risks                  │
│     - 本地 LSP 验证结果       │    │     - ruff/mypy 结果          │
└──────────────────────────────┘    └──────────────────────────────┘
```

### 流程步骤说明

| 步骤 | 执行者 | 动作 | 关键输出 |
|------|--------|------|----------|
| ① | 驾驶舱 | 用户点击"AI 辅助"→ AiContextBridge 写入 ai_context.json | ai_context.json |
| ② | 用户 | 对 AI 说"帮我推进这个变更" | — |
| ③ | pm-workflow | Step 0.5 读取 ai_context.json | 项目+变更+页面上下文 |
| ④⑤⑥ | pm-workflow | 跳过 venv 激活、project show、PM_SESSION、模式选择、最小提问 | 节省 ~50 行指令 |
| ⑦ | pm-workflow | 域判断：`domain == "PLC"` → plc-electrical-engineer | 技能分发决策 |
| ⑧ | pm-workflow | 构建 skill_context 摘要 | 结构化的上下文对象 |
| ⑨ | pm-workflow | `Skill: plc-electrical-engineer` 传递上下文 | 子技能启动 |
| ⑩ | 子技能 | 接收上下文，执行领域工作（路由→审查→修改→门禁） | 代码变更+验证结果 |
| ⑪ | 子技能 | 返回执行结果给 pm-workflow | changed_files, lint_result, test_result |
| ⑫ | pm-workflow | 收集结果→回写 PM_SESSION→写入 cockpit 反馈 | PM_SESSION §6-§9 + ai_feedback.json |

---

## 一.5、HTML 原型设计：pm-workflow 统一负责

### 问题

两类项目都有原型设计需求：

| 项目类型 | 原型需求 | 当前状态 |
|----------|----------|----------|
| 全栈（Python/Web） | Web UI 原型（页面布局、交互、状态） | fullstack 技能"前端"模式有方案产出，但无 HTML 原型 |
| PLC | HMI 画面原型（按钮、报警、趋势图） | 无覆盖，前次评估已识别为 P0 短板 |

如果把原型设计放到 fullstack 和 plc 各自实现，会导致：
- 重复的原型生成逻辑（两个技能都要写 HTML）
- 风格不一致（两个技能产出的原型审美不同）
- pm-workflow 已经做了"方案/线框"模式，原型是方案的自然延伸

### 方案：pm-workflow 统一代理原型设计

```
pm-workflow（产品型项目经理）
  │
  ├─ Step 3: 方案/线框模式
  │     │
  │     ├─ 需求分析 → 页面清单 → 交互流 → 状态覆盖
  │     │
  │     └─ 产出 HTML 原型（新增）
  │           │
  │           ├─ 全栈项目 → Web UI 原型（页面结构、组件布局、交互模拟）
  │           └─ PLC 项目 → HMI 原型（画面布局、按钮交互、报警弹窗、趋势图占位）
  │
  ├─ [原型确认后]
  │     │
  │     ├─ PLC 域 → Skill: plc-electrical-engineer（接收原型，编码实现）
  │     └─ 软件域 → Skill: fullstack-engineer（接收原型，编码实现）
```

**为什么 pm-workflow 适合做原型？**

| 理由 | 说明 |
|------|------|
| 原型是设计产物，不是代码 | 原型属于"方案/线框"模式的自然延伸，pm-workflow 的 Step 3 已经产出页面清单和交互流 |
| 统一审美和交互规范 | 同一个 pm 产出的原型，无论是 HMI 还是 Web UI，风格一致 |
| 减小子技能负担 | fullstack/plc 只负责"接收原型→编码实现"，职责更纯粹 |
| 原型作为交接物 | pm-workflow 产出原型 → 传递给子技能，形成清晰的"设计→实现"分界 |

**pm-workflow 改动**：Step 3"方案/线框"模式新增原型产出能力：

```markdown
### Step 3：按模式产出

| 模式 | 最少产出 |
|------|---------|
| 方案/线框 | 页面清单、主流程、状态覆盖（空/错/加载/权限）、**HTML 原型**（新增） |
| ... | ... |

**HTML 原型产出规范**（新增）：
- 全栈项目：输出可浏览器打开的 Web UI 原型（页面布局、组件结构、交互模拟）
- PLC 项目：输出 HMI 画面原型（按钮、状态指示灯、报警列表、趋势图占位、变量绑定标注）
- 原型文件存放：`PRD/原型/` 目录
- 原型作为子技能的输入：fullstack/plc 接收原型 HTML 后进行编码实现
```

**fullstack/plc 改动**：在"开始前"章节新增接收原型的步骤：

```markdown
### 开始前（fullstack-engineer）

1. 激活虚拟环境
2. 接收上下文（来自 pm-workflow）
3. **接收原型**（新增）：若 pm-workflow 已产出 HTML 原型，从 `PRD/原型/` 读取
4. 读取 PM_SESSION
```

### 影响范围

| 技能 | 改动 | 说明 |
|------|------|------|
| pm-workflow | Step 3 扩展 | 方案/线框模式新增 HTML 原型产出能力 |
| fullstack-engineer | "开始前"新增 | 接收原型步骤，Web UI 原型 → 编码实现 |
| plc-electrical-engineer | "开始前"新增 | 接收原型步骤，HMI 原型 → SCL/HMI 实现 |
| 驾驶舱 | 无改动 | 原型文件存在 `PRD/原型/`，驾驶舱 WorkspaceView 可后续添加预览 Tab |

---

## 二、跨技能切换：三种技术方案

### 方案 A：pm-workflow 作为中介（推荐）

**核心思想**：pm-workflow 不退出，调用子技能后等待返回，统一处理收尾。

```
pm-workflow 启动
  │
  ├─ Step 0.5: 读取 cockpit 上下文
  ├─ 域判断: PLC
  │
  ├─ ⑨ Skill("plc-electrical-engineer", prompt=skill_context)
  │     │
  │     │  plc 技能执行...
  │     │  返回结果给 pm-workflow
  │     │
  │     ▼
  ├─ Step 4: 回写 PM_SESSION
  ├─ ⑫: 写入 cockpit 反馈
  └─ 输出摘要 → 结束
```

**实现方式**：pm-workflow 在 Step 0.5 后，根据域判断直接调用 `Skill: <目标技能>`，将上下文摘要作为 prompt 的一部分传递。子技能执行完毕后，控制权返回 pm-workflow，pm-workflow 继续执行 Step 4 和反馈写入。

| 优点 | 缺点 |
|------|------|
| ✅ pm-workflow 全程掌控上下文，不丢失状态 | ❌ 子技能返回后 pm-workflow 需要重新加载上下文（token 消耗） |
| ✅ 子技能无需任何上下文恢复逻辑（最简洁） | ❌ Skill 调用是异步的，pm 需要等待 |
| ✅ 收尾工作（PM_SESSION 回写、反馈）统一在 pm | ❌ 如果子技能需要回写 PM_SESSION，需要约定返回格式 |
| ✅ 与现有 pm-workflow Step 5 设计一致 | ❌ 子技能返回的结果是文本，需要结构化解析 |
| ✅ 改动最小：pm-workflow 强化 Step 0.5，子技能删除 cockpit 检查即可 | |

**适用场景**：单次任务（一个变更单、一个需求），pm 分发→执行→收尾的线性流程。

---

### 方案 B：共享上下文文件（中间方案）

**核心思想**：pm-workflow 将上下文写入共享文件，子技能独立读取并执行，各自独立回写。

```
pm-workflow 启动
  │
  ├─ Step 0.5: 读取 cockpit 上下文
  ├─ 域判断: PLC
  ├─ ⑧ 写入 .auto-pm/skill_context.json（详细上下文）
  ├─ 回写 PM_SESSION §8（handoff: 转交 plc-electrical-engineer）
  ├─ pm-workflow 结束
  │
  ▼
plc-electrical-engineer 启动
  ├─ Step 0.5: 读取 .auto-pm/skill_context.json
  ├─ 执行领域工作
  ├─ 回写 PM_SESSION §6-§9
  ├─ 写入 .auto-pm/ai_feedback.json
  └─ 结束
```

**实现方式**：pm-workflow 在分发前将完整上下文（项目、变更、模式、PM_SESSION 摘要）写入 `.auto-pm/skill_context.json`，然后自己退出。子技能启动时读取这个文件获取上下文，执行完毕后独立回写 PM_SESSION 和反馈。

| 优点 | 缺点 |
|------|------|
| ✅ 子技能完全独立，不依赖 pm-workflow 在线 | ❌ 子技能仍需要 cockpit 上下文检查（只是换了个文件名） |
| ✅ 适合长任务（子技能可能执行很久） | ❌ PM_SESSION 回写分散在多个技能，一致性难保证 |
| ✅ 与当前 ai_context.json 模式一致，理解成本低 | ❌ 两个上下文文件（ai_context.json + skill_context.json），维护成本高 |
| ✅ 子技能失败不影响 pm-workflow 已完成的步骤 | ❌ pm-workflow 不知道子技能执行结果，需要额外轮询机制 |
| | ❌ 没有解决 43% 重复问题，只是把重复从 ai_context.json 换到 skill_context.json |

**适用场景**：子技能可能长时间执行，pm 不需要等待；或者子技能被用户直接触发（绕过 cockpit）。

---

### 方案 C：pm-workflow 内联执行（不推荐）

**核心思想**：不调用子技能，pm-workflow 直接包含所有领域的执行逻辑。

```
pm-workflow 启动
  │
  ├─ Step 0.5: 读取 cockpit 上下文
  ├─ 域判断: PLC
  │
  ├─ 直接在 pm-workflow 内执行 PLC 工作
  │   ├─ 读取规范（905/906/903...）
  │   ├─ 读取 SCL 源码
  │   ├─ 修改代码
  │   ├─ 运行 plc check
  │   └─ 回写 PM_SESSION
  │
  └─ 输出摘要 → 结束
```

**实现方式**：pm-workflow 的 SKILL.md 中包含所有领域的执行指令（PLC 规范引用、SCL 编辑规则、Python 工程实践等），不调用子技能，直接在 pm-workflow 内部完成所有工作。

| 优点 | 缺点 |
|------|------|
| ✅ 无跨技能切换开销 | ❌ pm-workflow SKILL.md 将膨胀到 800+ 行（当前 404 + 179 + 263） |
| ✅ 上下文 100% 不丢失 | ❌ 单一技能维护困难，任何领域变更都需要改 pm-workflow |
| ✅ 无需设计上下文传递协议 | ❌ 违反单一职责原则（pm 做了工程师的事） |
| | ❌ 技能加载时 token 消耗巨大（每次都要加载全部 800+ 行） |
| | ❌ 无法独立升级 plc/fullstack 能力 |
| | ❌ 与现有技能体系完全冲突，需要重写所有技能 |

**适用场景**：无。仅作为分析对照。

---

## 三、方案对比总览

| 维度 | 方案 A（pm 中介） | 方案 B（共享文件） | 方案 C（pm 内联） |
|------|:--:|:--:|:--:|
| 子技能独立性 | 中 | 高 | 无（不存在子技能） |
| 上下文一致性 | ★★★★★ | ★★★☆☆ | ★★★★★ |
| 重复代码消除 | ★★★★★ | ★★☆☆☆ | ★★★★★ |
| 改动量 | 小 | 中 | 大（重写所有技能） |
| 长任务支持 | ★★★☆☆ | ★★★★★ | ★★★☆☆ |
| PM_SESSION 一致性 | ★★★★★ | ★★★☆☆ | ★★★★★ |
| 维护性 | ★★★★☆ | ★★★☆☆ | ★☆☆☆☆ |
| 与现有架构兼容 | ★★★★★ | ★★★★☆ | ★☆☆☆☆ |
| 推荐度 | ✅ **推荐** | 备选 | ❌ 不推荐 |

---

## 四、推荐方案 A 的实施细节

### 4.1 pm-workflow 改动

**Step 0.5 强化**（当前已存在，扩展上下文传递逻辑）：

```markdown
### Step 0.5：检查 cockpit AI 上下文（若存在则跳过 Step 0-1）

1. 检查 `<工作空间根>/.auto-pm/ai_context.json` 是否存在
2. **若存在**：
   - 读取 JSON，提取全部上下文
   - **跳过 Step 0**（venv 激活、project show、PM_SESSION 读取、健康检查）
   - **跳过 Step 1**（模式选择），模式由 active_page 推断
   - **跳过 Step 2**（最小提问），上下文已包含变更单详情
   - 在状态摘要中标注"上下文来源: cockpit AI 辅助"
   - **域判断 + 技能分发**（新增）：
     - `domain == "PLC"` → 构建 skill_context，调用 `Skill: plc-electrical-engineer`
     - `domain == "SCPT"` / `"PYTHON"` → 构建 skill_context，调用 `Skill: fullstack-engineer`
   - 子技能返回后 → 继续 Step 4（回写 PM_SESSION）和反馈写入
3. **若不存在**：继续执行原有完整流程
```

### 4.2 fullstack-engineer 改动

**删除 item 1.5**（cockpit 上下文检查），改为接收 pm 传递的上下文：

```markdown
### 开始前

1. **激活虚拟环境**（必须最先执行）：
   ...

2. **接收上下文**：
   - 若从 pm-workflow 调用，从 prompt 中提取 skill_context（项目 ID、变更单、模式）
   - 若独立触发（无 pm-workflow），读取 PM_SESSION 走原有完整流程
   - **不再**直接读取 ai_context.json

3. 读取 PM_SESSION（若从 pm-workflow 调用则可跳过）
4. 读取本轮相关代码、配置、测试、页面
```

### 4.3 plc-electrical-engineer 改动

**删除 Step 0.5**（cockpit 上下文检查），改为接收 pm 传递的上下文：

```markdown
### Step 0：前置校验与硬约束加载

1. **激活虚拟环境**（必须最先执行）：
   ...

2. **接收上下文**：
   - 若从 pm-workflow 调用，从 prompt 中提取 skill_context（项目 ID、变更单、领域）
   - 若独立触发（无 pm-workflow），执行 Step 1 读取 PM_SESSION
   - **不再**直接读取 ai_context.json

3. **加载项目硬约束**：检测项目 project_memory.md 是否存在
```

### 4.4 skill_context 结构

```json
{
  "source": "pm-workflow",
  "project_id": "DJ-2026-005",
  "project_name": "周单机模板",
  "stack": "plc",
  "change_number": "CHG-PLC-2026-001",
  "change_title": "修复阀门控制时序错误",
  "change_domain": "PLC",
  "change_nature": "DEF",
  "change_status": "draft",
  "mode": "变更/缺陷/发布",
  "pm_summary": "上下文已通过 cockpit AI 辅助恢复，跳过项目识别、PM_SESSION 读取、模式选择。当前焦点：修复阀门控制时序错误。"
}
```

### 4.5 子技能返回结果结构

子技能执行完毕后，在输出中结构化返回：

```markdown
## 执行结果

- changed_files: ["02_PLC程序/PLC_ST/FB_ValveControl.scl"]
- plc_check_result: { violations_count: 0, errors: 0 }
- risks: ["时序修改需在现场验证阀门动作"]
- verification: "[已验证] 本地 LSP 检查通过"
```

pm-workflow 解析这些结果，写入 PM_SESSION §6-§9 和 cockpit 反馈。

---

## 五、边界情况

| 场景 | 处理方式 |
|------|----------|
| 用户直接触发 fullstack/plc（绕过 cockpit） | 子技能保留独立触发能力，走原有完整流程（读 PM_SESSION） |
| cockpit 上下文 + 无变更单（仅选中项目） | pm-workflow 不跳过 Step 1（模式选择），因为无法推断模式 |
| 子技能执行失败 | pm-workflow 捕获失败信息，写入 PM_SESSION §8 并通知用户 |
| 跨域变更单（domain 既是 PLC 又是 SCPT） | 按 primary domain 分发，子技能内判断是否需要进一步切换 |
| ai_context.json 过期（用户切换了页面） | pm-workflow 检查 generated_at 时间戳，超过 5 分钟提示用户刷新 |
| 原型不存在时子技能被调用 | 子技能检查 `PRD/原型/` 目录，若为空则自行从 PRD/需求文档推导界面 |
| 用户跳过原型直接进入编码 | pm-workflow 支持跳过"方案/线框"模式，直接进入变更模式分发到子技能 |