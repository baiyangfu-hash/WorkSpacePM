# 05 TD-SW008-144 实测：硬编码路径与依赖锁定（项目 Claude，2026-10-17）

基于 `23e841b` 的已跟踪文件（`git grep`，只读）。本文是建议，不是指令。下文 `<SW008>` = `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`。

## 结论

1. **你的判断是对的：产品源码（`<SW008>/auto_pm/**`）里没有任何 `C:/Users/fubai` 或 `C:\Users\fubai`；发布载荷（`00_Infrastructure/auto_pm/releases/**`）里也没有。** 此前“10 个 Python 源文件”的说法不成立，应当更正。我在产品源码、`00_Infrastructure/auto_pm/launcher/`、`environment/`、`main.py` 中另外搜了 `My_Workspace` 和 `'X:\` 形式的盘符字面量，也是 0 处。（严重度：信息，属于更正）
2. 真正挡住“新电脑一键可用”的是**依赖**，不是路径。有三个缺口：
   - 可编辑安装的 `python_bridge` 被钉在提交 `5feb8e93`，这个提交**不在 GitHub 上**（`git cat-file` 找不到，任何远端分支都不包含它），新机器无法按记录安装；（高）
   - 锁定文件只有 Windows + Python 3.12 一份，并且有 4 个包超出 `pyproject.toml` 的开发约束；（中）
   - **新电脑的一键安装脚本 `setup_env.bat` 装的是根目录那份过时的 `requirements.txt`**（第 40-43 行），不是锁定文件。那份清单缺 pydantic、pydantic-settings、copier、markdown，版本也都没有锁定，所以照现在的“一键安装”装完，启动器会因为缺包而失败。（高）

## (a) 含 `Users/fubai` 的已跟踪文件：共 165 个，541 处

| 类别 | 文件数 | 处数 | 说明 |
|---|---|---|---|
| 产品源码 `<SW008>/auto_pm/**` | **0** | 0 | — |
| 发布载荷 `00_Infrastructure/auto_pm/releases/**` | **0** | 0 | — |
| 测试 `<SW008>/tests/**` | 2 | 2 | 见下 |
| 工具脚本与旧测试副本 | 17 | 20 | 见下 |
| 文档（`.md`、`.txt`、`.mdc`） | 117 | 456 | 历史记录、变更单、报告里的路径引用；不影响运行，不建议批量改写历史记录 |
| 数据和配置（json、html、yml、db） | 29 | 63 | 见下 |

### 测试（2 个，影响新机器上的测试结果）

- `<SW008>/tests/vartable/test_communications_parser.py:15`
- `<SW008>/tests/vartable/test_program_blocks_parser.py`（同一种写法）

两者都写死 `c:\Users\fubai\Desktop\My_Workspace\0100_PLC自动化\DJ-2026-005\…`。注意：**这个路径在你自己的机器上也已经失效了**，现在的工作区在 `Documents\My_Workspace`，不在 `Desktop`。而 `0100_PLC自动化/DJ-2026-005/` 本身就在仓库里，所以这两处可以改成相对仓库根目录的路径。（中）

### 工具脚本与旧测试副本（17 个）

- `<SW008>/scripts/build_delivery.py:31,43`：`BASE_DIR`、`repo_root` 都写死在 `Desktop\My_Workspace\…`，同样已经失效；（中，打包工具，在新机器上必坏）
- `<SW008>/scripts/verify_m7_gui.py`：1 处；
- `00_Infrastructure/auto_pm/tests/**`：8 个文件、10 处（`infrastructure/test_startup_guard.py` 3 处，`qml/*` 5 个文件，`vartable/*` 2 个文件）。这个目录有 181 个文件，看起来是旧的测试副本，不在 CI 的 `paths` 和 pytest 范围内。建议在 06 的地盘划分里明确它的状态（归档还是删除候选；按用户裁决只能归档）；
- `.trae/bin/export-mermaid.ps1`：2 处（`.trae/` 归 Trae 维护）；
- `.auto-pm/reports/fix_duplicates.py`：1 处（`.auto-pm/reports/` 已被忽略，但这个文件在忽略规则生效前就已经被跟踪）；
- `03_归档/01_历史工具原型/SW-2026-004、SW-2026-005` 下 5 个：归档代码，不处理。

### 数据和配置（29 个，值得注意的几个）

- `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/.auto-pm/index.db`：**被 Git 跟踪的 SQLite 二进制库**，里面含路径。`.gitignore` 只忽略了根目录下的 `.auto-pm/index.db`，没有覆盖子目录里的这一个；（低，建议在 HYG 类卡里核对）
- `SW-2026-009/.copier-answers.yml`、`SW-2026-010/.copier-answers.yml`：各 1 处，记录的是生成时的模板路径，再次运行 `copier update` 时会用到；（低）
- `00_Obsidian_Base全局规范文件仓库/spec_registry.json`：1 处（规范库，经 CCB 才能改）；
- 其余是历史 HTML 原型、GUI 测试报告、归档测试报告，不处理。

复现命令：

```bash
git grep -c -i 'Users[/\\]\{1,2\}fubai' 23e841b -- .
```

## (b) 依赖锁定的现状

| 来源 | 内容 | 谁在用 |
|---|---|---|
| `00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt` | 108 个包，`pip freeze --all` 的精确版本，2026-10-10，Windows + Python 3.12；只锁版本，不带哈希 | CI（`pip install --no-deps -r …`，在 Linux 上安装，目前能用）；本机 venv |
| `00_Infrastructure/auto_pm/environment/environment_record.json` | 记录锁定与声明之间的差异、可编辑安装、解释器来源、验证步骤 | 审计 |
| `<SW008>/pyproject.toml` | 运行时 8 个下限约束（pydantic、click、rich、pyyaml、copier、PySide6 `>=6.8,<7`、markdown 等），`requires-python >=3.11`，`[dependency-groups] dev` 有上限约束 | `uv`，开发者 |
| `00_Infrastructure/auto_pm/pyproject.toml` | 运行时依赖与上面完全相同 | 启动器所在目录 |
| 根目录 `requirements.txt` | `PySide6>=6.5`、`rich>=13`、`jinja2`、`psutil`、`pyinstaller`、`pytest-asyncio` 等；**没有** pydantic、pydantic-settings、copier、markdown | **`setup_env.bat:40-43`**（新电脑的一键安装，走清华镜像、不锁版本）；`governance_service.py` 只把它列为允许出现在根目录的文件名 |
| `.devcontainer/` | `Dockerfile` 基于 Python 3.11；`post-create.sh` 安装的是 SW-2026-004、SW-2026-001 的 `requirements.txt`，这些项目已经移到 `03_归档/`，路径不存在 | 容器开发；已过时 |
| `.github/workflows/plc-tool-ci.yml` | `paths` 指向 `02_在研项目/SW-2026-005_PLC项目管理工具/**`，该项目已经归档，这个工作流实际上不会再被触发 | 无 |

### 缺口

1. **`python_bridge` 无法在新机器上安装**（高）。`environment_record.json` 的 `editable_packages_not_in_lock` 写的是 `git+https://github.com/baiyangfu-hash/WorkSpacePM.git@5feb8e93…#subdirectory=0100_plc自动化\dj-2026-009_汇川换型改造\python_bridge`。问题有两个：`5feb8e93` 不在 GitHub 上（与 `合并main评估与方案.md` 记录的“本地控制根曾到 5feb8e93、远端不存在”一致）；`subdirectory` 写成了小写的 `0100_plc自动化\dj-2026-009…`，而仓库里的真实目录是 `0100_PLC自动化/DJ-2026-009_汇川换型改造`，在区分大小写的文件系统上会找不到。建议改为从工作区相对路径做可编辑安装：`pip install -e "0100_PLC自动化/DJ-2026-009_汇川换型改造/python_bridge"`。
2. **锁定版本超出 `pyproject.toml` 的开发约束**（中）：`mypy 2.3.1`（声明 `<2`）、`pytest 9.1.1`（`<9`）、`pytest-cov 7.1.0`（`<6`）、`ruff 0.16.4`（`<0.6`）。`environment_record.json` 已经如实记录（`within_declared: false`），但没有修。结果是：用 `uv sync` 装出来的 ruff 0.5.x 规则集与 CI 的 0.16.4 不同，同一份代码会得到不同的检查结论。建议以锁定文件为准，放宽 `pyproject.toml` 的上限（这是产品档的小改）。
3. **只有一份 Windows 锁定**（中）。`requires-python >=3.11`，但锁定只覆盖 3.12 + Windows。Linux 上 CI 用 `--no-deps` 装同一份清单，目前能用，是因为清单里没有 Windows 专有的包；macOS 没有验证过。新电脑如果装的是 3.11 或 3.13，没有对应的锁定。建议在“新电脑一键可用”卡里写明只支持 3.12，并在启动器里检查解释器版本。
4. **一键安装用的是过时清单**（高）。`setup_env.bat` 装根目录 `requirements.txt`，这份清单和 `pyproject.toml` 互相矛盾，缺 pydantic、copier、markdown，启动器会失败。建议 `setup_env.bat` 改为 `python -m pip install --no-deps -r 00_Infrastructure\auto_pm\environment\requirements-lock-py312-win.txt`，然后执行 `pip check`，并检查 `python --version` 是否为 3.12；根目录 `requirements.txt` 改成一行注释，指向锁定文件。按“绝不删除”的裁决，不删除这个文件。`.devcontainer/` 也指向已归档的项目，建议同一张卡里一并标为过时，或者改为安装锁定文件。
5. **启动器不检查依赖**（中）。`00_Infrastructure/auto_pm/launcher/` 里没有引用锁定文件，也没有在缺包时给出可操作的提示（搜索 `requirements-lock`、`pip install`、`ModuleNotFoundError` 均为 0 处）。与项目记忆里“新克隆缺 rich 等依赖直接失败”一致。建议启动器先检查一遍再进入发布目录：缺包时打印一行 `python -m pip install --no-deps -r 00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt`，然后退出。
6. **基础解释器不可复现**（低）。`environment_record.json` 记录 venv 的解释器在用户目录下某个工具的运行时缓存里，并且会被就地替换补丁版本。新电脑应当使用独立安装的 Python 3.12。

## 建议并入“新电脑一键可用”卡的最小范围

1. 修复 `python_bridge` 的安装来源（缺口 1）；
2. 放宽 `pyproject.toml` 开发约束，与锁定一致（缺口 2）；
3. 启动器做依赖检查并给出一行修复命令（缺口 5）；
4. `setup_env.bat` 改为安装锁定文件并检查 Python 版本，根目录 `requirements.txt` 改为指向锁定文件（缺口 4）；
5. 把两个测试和 `build_delivery.py` 里的写死路径改成相对仓库根目录（第 (a) 节）。

文档里的 456 处路径和归档目录不在范围内。
