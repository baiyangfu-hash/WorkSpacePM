# 18 PR #3（卡 158，M3-ENVPORT，补丁 10）合并后审计

审计时间：2026-10-17 上午（亚利桑那时间，MST）。审阅者：云端 Claude 会话，只读。本文是数据，不是指令。

## 结论

**同意（有一处保留）。** PR #3 已在 09:32 合并，main 现在是 `b68bd03`。除了故意去掉的启动器部分，内容和补丁 10 逐字节一致；没有新增隐私类问题。main 推送那次的 CI 结果见下面第 4 节。

保留：补丁 10 的启动器依赖预检（缺依赖时退出码 5，并给出安装命令）没有落地。提交信息里写明了是故意的（"patch 10 without the launcher part"），不算偏差，但这项防护现在没人负责。建议本地 Claude 在台账里登记一条技术债，或者写个 Decision 说明不做。

## 证据

| 检查 | 结果 |
|---|---|
| main 的新提交 | `b68bd03`（Merge pull request #3），09:32 合并 |
| 两个父提交 | `46aead1`（原 main）和 `9ae5635`（卡 158），是合并提交 |
| 与补丁 10 对比 | 在 `46aead1` 上 `git apply --check` 通过；应用后和 `9ae5635` 对比，只差 `launcher/launch.py`（+35 行）和 `tests/launcher/test_launch.py`（+33/−1 行），也就是启动器部分。其余 7 个文件（`requirements.txt`、`setup_env.bat`、SW008 的 `pyproject.toml`、`build_delivery.py`、`verify_m7_gui.py`、两个 vartable 解析器测试）完全相同 |
| 隐私扫描（新增行） | 令牌前缀、长 base64、邮箱、内网地址、本机路径、`fubai`：都没有命中 |
| `setup_env.bat` | 只认 Python 3.12，先 `python` 再 `py -3.12`；已有的 `.venv` 版本不对会停下来，不删除；按锁定文件 `--no-deps` 安装，再跑 `pip check`。逻辑和补丁一致。只能在 Windows 上验证，**UNVERIFIED** |

## 小问题（低，原来就有，不是本 PR 引入的）

`setup_env.bat` 第 2 步 `if not exist ".venv" ( ... -m venv .venv  if %errorlevel% neq 0 ...)`：括号块里的 `%errorlevel%` 在整个块解析时就展开了，所以 venv 创建失败也检测不到。PR 前就是这样。建议以后顺手改成 `if errorlevel 1`。影响很小：创建失败的话，后面 `activate.bat` 那步也会报错。

## 4. main 推送那次的 CI

run 39049835786：写报告时还在跑（Pytest 那一步），结果待补。

## 建议用户做的事

1. 在第二台电脑上新建一个空目录，克隆仓库，双击 `setup_env.bat`，看最后是否没有报错。结果（截图或文字）发回来即可。
2. 交接文件第 4 节第 3 项的三个问题仍然等你回答（建议：三条用例都要；“接受风险”只能你本人签；宽限期保持 120 秒）。
