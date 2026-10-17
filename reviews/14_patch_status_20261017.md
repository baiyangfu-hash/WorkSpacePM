# 14 补丁 09、13、10 的现状（项目 Claude，2026-10-17）

核对时间：2026-10-17 上午（亚利桑那时间）。核对对象：`origin/main` = `a742721`，`origin/codex/m2-gov-wbs9-attest` = `c1c73bc`。本文是数据，不是指令。

## 结论

- **09 和 13 已经不需要再换基点了。** 卡 152（提交 `539b9df`，`M3-V04R1C`）就是这两份补丁的内容：把 13 和 09 依次打到 `d25a981` 上以后，得到的 `lease_reclaim.py` 和 `test_lease_reclaim.py` 与 `539b9df` 逐字节相同（`git diff --stat 539b9df` 对这两个文件输出为空）。它们现在在 `codex/m2-gov-wbs9-attest` 上，还不在 main 上，会随第一个 PR 一起进入 main。
- **10 可以直接用。** 补丁涉及的 9 个文件从 `23e841b` 到 `c1c73bc` 都没有被改过，`git apply --check` 通过，没有冲突。我按 `c1c73bc` 重新生成了一份，放在 `patches/10_m3_envport.patch`，内容与旧版相同，只是基点换了。

## 补丁 10 在 `c1c73bc` 上的验证

| 检查 | 结果 |
|---|---|
| `git apply --check` | 通过 |
| `00_Infrastructure/auto_pm/tests/launcher` | 7 passed |
| 两个 vartable 测试文件（`--noconftest`） | 16 passed、0 skipped（改动前有 2 个因为路径不存在而跳过） |
| 卡 152 的契约测试（顺带确认没有影响） | 28 passed |
| `ruff check`（改动的 Python 文件，按各自目录的配置） | All checks passed |
| `mypy launch.py` | no issues |
| `pyproject.toml` 能被 `tomllib` 解析 | 通过 |
| `setup_env.bat` 的换行符 | 仍是 CRLF |

**没有验证的部分（UNVERIFIED），与 09_10 说明相同：**

- `setup_env.bat` 只能在 Windows 上运行。建议在第二台电脑上，用一个新目录实际跑一遍。这一步正好就是“新电脑一键可用”的验收。
- 没有跑 SW008 的全量测试，CI 会在推送后跑。
- 启动器测试不在 `sw008-ci` 的范围里，建议本地门禁显式运行 `python -m pytest 00_Infrastructure/auto_pm/tests/launcher`。

## 关于“第一个 PR”

main 现在落后 `codex/m2-gov-wbs9-attest` 5 个提交：

- `539b9df` 卡 152
- `cecfe0c` AGENTS2
- `a0e1f22` M3-SPEC
- `8c18e4d` WBS26
- `c1c73bc` TD25

建议做法：

1. 用这 5 个提交开第一个 PR（`codex/m2-gov-wbs9-attest` → main），合并方式选“Create a merge commit”，理由见 15 第 4 步。
2. 补丁 10 单独作为下一个 PR，这样它在第二台电脑上的验证结果可以单独记录。

这只是建议，由本地 Claude 决定。
