# F26 复现：台账对账与 change verify 都不看 continuity.db

被测：main `17b5faf5`，部署版 `1.3.3-d8f7c8b`（2026-10-30）

前置：continuity 里已有记录（本轮的 W-P2-R1/R2/R3、R-P2-R1/R2/R3），它们在 `.auto-pm/continuity.db`。

```bash
cd /workspace
.venv/bin/python main.py ledger reconcile ZZ-2026-902           # exit 0：台账缺失 0 / 多余 0 / 状态不一致 0
.venv/bin/python main.py change verify ZZ-2026-902 --ledger-check  # exit 0：门禁通过
```

两条对账都只比对「变更单文件 ↔ 台账」，对 continuity 的 Work/Run 零感知，故结果恒为 0 差异。

结论：台账（change/ledger）与 continuity 是两本互不知晓的账；上轮 F9（Workspace Registry 与 project 登记两本账）是同类问题的另一处。
