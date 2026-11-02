# 发版 7 门禁工具（审计用，草稿）

只含工具与卡草稿，不含发布内容；不开 PR。来源：笔记本 `.auto-pm/reports/m3-rel7/`（被 git 忽略），这里是为云端审计留的副本。

- `219_M3-REL7_第七次发版候选门禁实施卡_PM.md`：卡草稿，SHA-256 见线程（带最终例外的彩排尚待重跑，卡的“演练事实”一栏已如实写明）。
- `rel7_gates.py.txt`（审计副本，运行时是 .py）：判卷脚本。窄例外写死在这里：`KNOWN_STUCK_RUN`、`orient_ok`、`orient_cases`；G8 判卷要求 14 个反例全部符合预期。
- `G8_orient_exception_cases_result.json`：14 个反例按当前代码算出的结果（got 与 expected 逐条相等）。
- `rel7_exception_patch.py.txt`、`derive_rel7.py.txt`：把例外加进判卷脚本的派生工具。
- `rel7_config.json`、`reference_manifest.json`：冻结提交 `d671611a` 与参考字节指纹。
