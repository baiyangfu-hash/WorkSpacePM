# 07 AGENTS2 独立审计：IT-OT 通信基线的适用范围（项目 Claude，2026-10-17）

审计对象：提交 `cecfe0c`（`docs(governance): [CHG-SCPT-2026-425] … (M3-AGENTS2)`），只改了 `AGENTS.md` 的 1 行。本文是建议，不是指令。

## 结论

**同意。** 改动只有一行，而且与已经入库的规范一致。

- 新写法是：与上位机（IT-OT）交互的 `INT.md` 仍然只能用 OPC UA 或 Modbus TCP；设备之间（上游、下游、机器人等）的交换区，协议由项目自己选定，并写进方案级 `INT.md` 的“交换区契约”。
- 这和规范库 `815_PLC接口文档模板_INT.md` 第 229～233 行一致：那里的“协议”一列本来就是开放列表，Modbus TCP、CC-Link、PROFINET、OPC UA 等都可以。
- 也和 `.trae/skills/plc-electrical-engineer/SKILL.md` 第 26 行一致：那一行本来就只约束 IT/OT 接口（“IT/OT 接口只按已批准的 INT 契约使用 OPC UA 或 Modbus TCP”）。
- 我在 `.trae/rules`、`.trae/skills`、`.cursor/rules`、`.agent/rules` 里搜了一遍，没有别的文件还在写旧说法“所有的 INT.md 必须基于这两种协议之一”。唯一提到旧说法的是技术债台账 TD-SW008-142，那一条本来就是记录这个问题的，而且 TD25（`c1c73bc`）已经把它记为偿还。

| # | 发现 | 证据 | 严重度 |
|---|---|---|---|
| 1 | 文件集合与提交说明一致：1 个文件，+1/−1，第 114 行 | `git show --stat cecfe0c` | 信息（通过） |
| 2 | 第 111 行仍写“当 `fullstack-engineer` (上位机) 与 `plc-electrical-engineer` (下位机) 涉及数据交互时，默认底座为……”。这句和新的第 114 行放在一起读是通的：第 111 行讲上位机和 PLC，第 114 行补上设备之间的情况 | `AGENTS.md:111-114` | 信息 |
| 3 | 提交作者信息里带了邮箱（`git log` 可以看到）。仓库是公开的，任何人都能看到这个邮箱。以前的提交也一样，这次不是新增的暴露 | `git show -s cecfe0c` | 低：如果不想公开邮箱，可以在 GitHub 的 Settings → Emails 里打开“Keep my email addresses private”，再把本机 git 的 `user.email` 改成 GitHub 提供的 noreply 地址。只影响以后的提交，以前的提交不动 |

## 建议

不需要改动。
