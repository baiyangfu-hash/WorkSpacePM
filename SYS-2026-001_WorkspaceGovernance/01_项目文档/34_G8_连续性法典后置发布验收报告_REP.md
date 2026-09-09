# G8 连续性法典后置发布验收报告

> 日期：2026-09-09  
> 结论：`ACCEPTED / EFFECTIVE`  
> 变更：`CHG-SPEC-2026-015`

## 1. 验收结论

G8 在 G7 真实 Dogfood 与运行时生效之后发布正式法典，满足“规范先行、分层分单、后置生效”的治理要求。PM-056 成为跨 Agent 连续性的唯一上位规范；PM-004 已弃用，PM-033/042/046 已完成必要差异修订。整改未扩散至 DEV-300、PLC/LSP、PM-043、PM-045 或全库冷热清洗。

## 2. 生效清单

| 对象 | 生效结果 |
|---|---|
| PM-056 | V1.0.0，`stable / active`，定义 Project/Work/Run/Checkpoint/Handoff/Release、真源、lease、Git 与 fail-closed |
| PM-004 | V1.5.0，`deprecated`，由 PM-056 替代 |
| PM-033 | V2.0.0，平台中立迭代生命周期 |
| PM-042 | V2.5.0，明确 CHG 管授权、Work/Run 管执行 |
| PM-046 | V2.0.0，结构化 Handoff v2 契约 |
| registry/index | 版本、生命周期、替代关系、路径和索引同步 |

## 3. 验证证据

- 目标范围 SHC-001～008、SHC-010：0 项错误，Exit 0。
- `spec_registry.json`：JSON 可解析；PM-056 编号和 canonical path 唯一；active/stable 数量与索引一致。
- 索引链接：PM-004/033/042/046/056 目标均存在。
- active runtime：G7 已验证 `1.3.1-a7dae04` 的 Resume v2、双适配器冷启动、lease 转移和 token 隔离。
- Git：仅按 G8 精确 pathspec 提交，不纳入其他 owner 的脏改动。

## 4. 非目标债务隔离

完整 `spec check` 仍报告 4 项非本法典内容错误：3 项 SHC-011 来自既有 CHANGELOG/PM_SESSION 投影版本漂移；1 项 SHC-017 来自检查器仍硬编码被冻结的 `.trae/skills/pm-workflow` 文档。G8 不修改 PM_SESSION 或 `.trae` 来制造绿灯。SHC-017 必须以独立 CHG-SCPT 修改检查器并重新发布；SHC-011 保持显式债务，待其 owner 在独立变更中处理。

## 5. 最终裁决

- G8：`ACCEPTED / EFFECTIVE`。
- `pm-workflow`：`QUARANTINED / DEPRECATED / DO_NOT_USE`。
- PM 职责：保留，但不由单一 Agent 技能独占。
- 下一合法动作：独立整改硬编码 skill contract 门禁；不得回到旧 P1～P7 或 NG-WP 执行线。
