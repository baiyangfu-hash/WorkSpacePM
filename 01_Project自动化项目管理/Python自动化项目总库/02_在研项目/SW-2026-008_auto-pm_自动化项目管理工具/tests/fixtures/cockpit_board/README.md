# 驾驶舱总控屏契约样本（CHG-SCPT-2026-628 骨架 B）

`readers.py` 的解析测试（`tests/core/test_cockpit_board_readers.py`）读这里的样本。

- 真实输出（云端控制根 2026-11-11 用源码 `main.py` 只读命令采集，空账本）：`orient.json`（`pm orient SW-2026-008 --json`，read_set 截到 2 条）、`worktree_list_empty.json`、`worktree_sweep.json`（items 截到 3 条）、`project_list.json`（截到 2 个项目）、`plc_check.json`（`plc check DJ-2026-000 --json`）、`pm_inbox.json`、三个 `stderr_*.txt`（命令不存在、没有账本、orient 的启动提示）。
- 合成样本（云端没有账本，字段照 CLI 源码 `pm_switch._board_payload`、`pm.pending_pm`、`long_run_service.list_tasks`、`worktree._station_json` 写）：`pm_missions.json`、`pm_pending.json`、`long_run_status.json`、`worktree_list.json`。

真实账本下的样本由本机补采（变更单清单“留给本机”第 3 条），补采后替换合成样本，不改测试的断言口径。
