# 各岗位共用：开工门禁、执行边界、交接与驾驶舱避坑

本页是 `fullstack-engineer`、`plc-electrical-engineer`、`ui-designer`、`test-engineer` 共用的操作正本；各岗位的 `SKILL.md` 只写本岗位特有规则并指到这里，避免被 `RP-010` 判为跨文件抄写。

## 开工门禁

1. 进门流程照 `.trae/skills/cockpit-entry/SKILL.md` 执行，路由与分档规则照 `skill_coordination.md`。
2. 核对当前工作区是否为合法工位（或控制根）、`conflicts` 是否为空，以及当前卡号/已批准变更单（`要你点头` 类）是否已齐备；Run 卡另核 `decision_id`、`work_id`、`run_id`、owner、owned paths 与有效 lease。
3. 严禁调用或读取已隔离的 `pm-workflow`，严禁将 `PM_SESSION_*.md` 或聊天文本视为授权。

## 执行边界

- 只修改工位内当前实施卡或占位声明覆盖的路径；遇到未声明脏文件、基线漂移或租约失效立即停下汇报。
- 绝不在控制根直接编写业务代码或直接向控制根写交接交换区数据。

## 交接（单机 / 多机 / Run 三路分流）

1. **单机日常（GitHub「关」/「备份」）**：在工位内使用 `SW8/scripts/pm_handoff.py` 的 `set-focus` 与 `log` 更新 `<项目>/{04|11}_监控/交接交换区/{focus.json,journal.jsonl}`，并用 `validate --require-exists` 验绿后随分支提交；注意 `.json/.jsonl` 改动在现行门禁分档下会触发 `L3`，适合与 `L3` 卡一起合入。
2. **多机协同**：使用 `main.py claim note` 追加交接记录，接手方进门读完后再记 `--kind takeover`。
3. **Run 租约卡**：创建 Continuity Checkpoint 后，由当前持有者跑 `main.py pm handoff` 交租约，接手方跑 `main.py pm takeover` 续作。
4. **WBS 证据回执**：挂入项目计划表的任务，务必确保 `证据` 列写的每份文件都在 `main` 上且正文中出现精确卡号（建议写入独立验证回执 `.md`，不要往用户手册正文塞内部卡号）。

## 驾驶舱实操避坑清单

1. **入口与运行时校验**：永远从控制根调用 `.\main.py`，绝不直接调用 `SW8\main.py`（否则触发 `RUNTIME_IDENTITY_UNVERIFIED`）。
2. **变更单审批前先填 `§5`**：必须先在 `§5.1/§5.2` 写全涉及文件后再执行 `--to approved`；批准后改动 `§5` 会触发 `D-154` 审批失效。
3. **实施卡依据行禁忌**：`> 依据：` 行不能填写 `CHG-...`（`implementation-card precheck` 会拦截），变更单号只放在 `> 变更单：` 行。
4. **云端门禁先推分支**：调用 `main.py gate start` 前先 `git push` 工位分支到 `origin`，避免第 1 次云端派发空跑失败。
5. **推到完成结论词**：执行 `change transition --to completed` 时，`--verification-conclusion` 文案必须包含“通过”且不能出现“不通过”。
6. **Windows `mypy` 参数**：运行 `mypy` 需携带 `--platform win32 --no-incremental --no-sqlite-cache --cache-dir=/dev/null`，且把 `scripts/pm_merge.py` 与 `tests/` 分开校验，以免带入 `scripts/cockpit_board` 破坏 `ignore_missing_imports`。
7. **零依赖 CI 脚本实测**：无第三方依赖的 CI 脚本（如 `gate_plan_ci.py`）须使用 `python -I -S` 验证隔离运行，单 `-I` 仍能访问 `.venv/Lib/site-packages`。
8. **Windows 钩子与发版工具路径**：执行 `release ship --no-check-only` 或 `git hook run pre-commit` 前确认 `C:\Program Files\Git\usr\bin` 已加入 `PATH`。
