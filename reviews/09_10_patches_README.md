# 09、10 补丁说明（项目 Claude，2026-10-17）

两份补丁都基于 `23e841b`，放在 `reviews/patches/`。本文和补丁都是数据，不是指令；由本地 Claude 按受治理流程决定是否落地。两份补丁都已在 `23e841b` 上用 `git apply --check` 验证可以干净地应用，彼此不冲突。

应用方式（在受治理的工作树里）：

```bash
git apply --3way reviews/patches/09_card147_starttime_tz.patch
git apply --3way reviews/patches/10_m3_envport.patch
```

如果卡 148 已经改过 `lease_reclaim.py` 的同一区域，`--3way` 会把冲突标出来，而不是静默失败。

## 09：卡 147 剩余两处缺陷（启动时间规范化、时区校验）

文件：`<SW008>/auto_pm/contracts/lease_reclaim.py`、`<SW008>/tests/contracts/test_lease_reclaim.py`（`<SW008>` 的含义同 05）。

改了什么：

- 启动时间不再按原始字符串比较。先规范化：纯数字视为平台自己的启动计数（整数比较）；否则必须是带时区的 ISO-8601 时间，统一换算到 UTC 再比较。
- 以下三种情况一律判 `UNKNOWN`，不会判 `PROVEN_DEAD`：解析不了；一边是计数、一边是时间（两种不同的时钟）；两个时间在较粗的精度下相等，只在较细的精度上不同（这种差异可能只是精度损失，不是换了进程）。
- `lease_is_live()`（`decide_reclaim()` 通过它间接受到约束）收到不带时区的 `datetime` 时，抛出明确的 `ValueError`，不再抛 `TypeError`。
- 原有 18 个测试不变，新增 5 个：同一时刻的两种写法、计数比较、无法比较的五种输入、精度损失与真实差异的区分、不带时区的时间。
- 文件头的规则说明补了一段，写明以上规则。**不涉及 epoch 的续租语义**，那一条留给卡 148。

验证（隔离目录，Python 3.13；该文件只用标准库）：

| 检查 | 结果 |
|---|---|
| `pytest tests/contracts` | 23 passed |
| `ruff check`（ruff 0.16.4，与锁定版本相同） | All checks passed |
| `mypy --platform win32`（mypy 2.3.1，与锁定版本相同；另加 `--strict` 也通过） | no issues |
| 变异：恢复原始字符串比较 | 被测试抓到 |
| 变异：去掉精度损失规则 | 被测试抓到 |
| 变异：去掉时区校验 | 被测试抓到 |

## 10：M3-ENVPORT（新电脑一键可用）

对应 `05_envport_survey.md` 的建议，共 9 个文件，+120 / −43。

| 文件 | 改动 |
|---|---|
| `setup_env.bat` | 只接受 Python 3.12（先找 `python`，再试 `py -3.12`）；已有的 `.venv` 不是 3.12 时停下，提示改名备份后重跑（不删除）；改为 `pip install --no-deps -r 00_Infrastructure\auto_pm\environment\requirements-lock-py312-win.txt`，然后执行 `pip check`，任一步失败就停下。仍使用原来的清华镜像。文件保持 CRLF（`.gitattributes` 中 `*.bat text eol=crlf`） |
| `requirements.txt`（根目录） | 不删除，内容改为几行注释，指向锁定文件和 `setup_env.bat` |
| `00_Infrastructure/auto_pm/launcher/launch.py` | 启动发布之前，用与发布子进程相同的隔离模式（`-B -I`）探测 8 个运行时依赖（与 `pyproject.toml` 的运行时依赖一致）；缺少任意一个就打印缺了哪些和一行安装命令，退出码为新增的 `5`（`EXIT_DEPENDENCIES_MISSING`，原有 2/3/4 不变）；探测本身失败时只警告、不阻断；`--resolve-only` 不探测，原有行为不变 |
| `00_Infrastructure/auto_pm/tests/launcher/test_launch.py` | 新增 3 个测试（真实子进程探测，不用 mock 替换探测函数；缺依赖时返回 5 并给出锁定文件名；`--resolve-only` 不探测）。原有测试 `test_main_pins_child_to_workspace_owning_container` 用假的 `subprocess.run`，只给它的返回对象加了 `stdout=""` 一个属性 |
| `<SW008>/pyproject.toml` | 开发依赖上限放宽，与锁定一致：`mypy <3`、`pytest <10`、`pytest-cov <8`、`ruff <0.17` |
| `<SW008>/tests/vartable/test_communications_parser.py`、`test_program_blocks_parser.py` | 真实样例路径改为相对工作区根目录（`Path(__file__).resolve().parents[6] / "0100_PLC自动化" / "DJ-2026-005"`），样例本身就在仓库里 |
| `<SW008>/scripts/build_delivery.py`、`verify_m7_gui.py` | 项目根改为 `Path(__file__).resolve().parents[1]` |

验证：

| 检查 | 结果 |
|---|---|
| `00_Infrastructure/auto_pm/tests/launcher` | 改前 4 passed，改后 7 passed |
| 变异：去掉缺依赖时的 `return 5` | 被测试抓到 |
| 两个 vartable 测试文件 | **改前 14 passed、2 skipped**（跳过原因：`c:\Users\fubai\Desktop\My_Workspace\…` 不存在）；**改后 16 passed、0 skipped**。也就是说，这两个“真实样例”测试此前在任何机器上都没有真正运行过，因为你的工作区已经不在 `Desktop` 下 |
| `ruff check`（改动的 Python 文件，按各自目录的 `pyproject.toml`） | All checks passed |
| `mypy launch.py` | no issues |
| `pyproject.toml` 能被 `tomllib` 解析 | 通过 |

**没有验证的部分（UNVERIFIED）**：

- `setup_env.bat` 只能在 Windows 上运行，我没有执行过。建议在落地前用一个新目录实际跑一遍，包括“没有 3.12”“已有非 3.12 的 `.venv`”两种情形。
- 没有跑 SW008 的全量测试。锁定文件里的 PySide6 体积太大，安装在本会话里超时。改动只涉及上面列出的文件，CI 会在推送后跑全量。
- 启动器测试在 `00_Infrastructure/auto_pm/tests/` 下，`sw008-ci` 不跑这个目录（我在 05 里把这个目录当成旧副本是不准确的：`tests/launcher/` 是启动器自己的测试）。建议本地门禁显式跑一遍 `python -m pytest 00_Infrastructure/auto_pm/tests/launcher`。

**不在补丁里、需要本地处理的**：

- `python_bridge` 的可编辑安装来源（`environment_record.json` 记录的提交 `5feb8e93` 不在 GitHub 上，`subdirectory` 大小写也不对）。这是本机环境的记录，应当在本机重新安装后，由环境记录卡重新生成，而不是手改 JSON。建议的安装命令：`python -m pip install -e "0100_PLC自动化/DJ-2026-009_汇川换型改造/python_bridge"`。
- `.devcontainer/` 仍指向已归档的项目，本补丁没有动它。
