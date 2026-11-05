# DJ011 INT 实例表对齐卡

> 卡片编号：`CARD-DJ011-INT V1.0`
> 隔离基线：`db0a51c9514827960cd4c1d6f6189c561993ec7a`（`main`）
> 路径根：`.`
> 档次：一档小卡（只改一个文档）
> 安全回路: 是

本卡只给 `main.py pr open` 提供“可改范围”，由云端会话起草，不改任何代码。011 没有标定安全区，按安全区处理：PR 写“安全回路: 是”，等用户“安全签字 <头提交号>”，agent 不自己签字。

背景：#539 把 FB 实例从各 DB 搬到了 FB_9001_TestBench 的多重实例和 DB_TestBench，接口文档 INT 的“FB 实例表”还是旧写法，`plc check DJ-2026-011` 因此有一条警告（“接口文档 INT ↔ 代码 [FB 实例]：文档有、代码无”）。本卡只改文档，让 INT 与代码一致，消掉这条警告。

| 路径 | 基线状态 | 用途 |
|---|---|---|
| `0100_PLC自动化/DJ-2026-011_驾驶舱A6PLC续作验证套件/PRD/接口文档_INT.md` | 存在 | “FB 实例表”改成与 FB_9001_TestBench 多重实例和 DB_TestBench 一致 |

## 验收
- `.venv\Scripts\python.exe main.py plc check DJ-2026-011 => 0`，原文贴进 PR，并说明那条 INT 警告是否消失；没跑就在 PR 第一行写“未经 LSP 检查”。
- `.venv\Scripts\python.exe main.py doc check => 0`。

## 未核实
- 另一条 WARN（Spec Snapshot 次版本漂移）不在本卡范围。
