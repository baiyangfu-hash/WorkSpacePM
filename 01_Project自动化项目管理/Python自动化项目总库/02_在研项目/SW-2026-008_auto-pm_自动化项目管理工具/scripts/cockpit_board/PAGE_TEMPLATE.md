# 补一页的模板（驾驶舱总控屏，骨架 D 之后）

给接手补页面的 agent（Trae、Claude 等）照着做。每一步做完再做下一步；哪一步漏了，测试会红。
像在 PLC 程序里加一个新工位：先在 IO 表里登记点位，再写读取，再画 HMI 画面，最后做联调记录。

## 0. 先看三份真源

- `flow/commands_map.json`：要读的命令必须是 `read` 类；带写开关（如 `--apply`、`--fix`）的不许带。
- `flow/pages.json`：每页读哪条命令、空态和错态文案。
- `README.md` 第 2、3、7 节：哪个文件管什么、画面规矩（没检查不显示 0 或绿）。

## 1. 声明命令（`flow/pages.json`）

在 `pages` 里加一项，或给已有的页加一条 `reads`：

```json
{"key": "<页键>", "group": "日常 | 受管项目 | 驾驶舱", "title": "<页名>",
 "reads": [{"command": "<命令>", "args": ["--project-id", "<PID>"], "reader": "<读法名>"}],
 "empty_text": "<读到了但没有内容时的话>", "error_text": "<读不到时的话>"}
```

- `<PID>` 会换成要读的项目号；不要项目号的命令就不写它。
- 文案里不许有“0”“通过”“正常”（契约测试会扫）。

## 2. 解析（`readers.py`）

- 加一个 `parse_<读法名>(text) -> Parsed`，在 `READERS` 里登记同名键。
- 认得的格式拆成字段；认不得的返回 `unreadable("哪里不对")`，不猜、不补 0。
- 不 import `auto_pm`，不起子进程、不读写文件。
- 样本放 `tests/fixtures/cockpit_board/`：正常、缺字段、命令不存在三类，测试在 `tests/core/test_cockpit_board_readers.py`。

## 3. 画（`widgets/<页键>.py`）

```python
from cockpit_board.widgets import common as c


def summarize(reader: str, data: dict) -> list[tuple[str, str]]:
    """读法 → 几行“名字 → 值”；纯函数，测试直接调。"""
    if reader == "<读法名>":
        rows = data.get("items") or []
        return [("条目", c.count_text(rows, "条"))]  # 空列表写“没有”，不写 0
    return []


class XxxPage(c.ReadPage):
    def __init__(self) -> None:
        super().__init__("<页键>", "<页名>", "<这页回答的一个问题>", (
            ("<还没做的功能>", "<为什么还没做>", "<以后读的命令，可空>"),
        ))

    def summary(self, reader: str, data: dict) -> list[tuple[str, str]]:
        return summarize(reader, data)
```

- 命令的 `null` 字段用 `c.flag_text` 显示“没检查”，不当成“没有”。
- 不写颜色（只在 `theme.py`），不起子进程、不写文件（只在 `actions.py`）。
- 页面上不放按钮。要按钮就是另一张单：先在 `policy.py` 白名单加字，按钮背后的命令在 `commands_map.json` 里必须是 `write` 或 `user_only`。

## 4. 挂上（`shell.py`、`policy.py`、`app.py`）

1. `shell.PAGES` 加一行 `PageSpec("<页键>", "<侧栏字>", "<组>", "<提示>")`；提示里不许有 `policy.NEVER` 和禁用词。
2. `policy.PM_BUTTONS` 加侧栏字。
3. `app.CockpitWindow.__init__`：建页、放进 `self.read_pages`（读命令的页）、`self.router.register`。
   读命令、存快照、断网退回快照都由 `app.read_page` 统一做，页面不用管。

## 5. 测试（`tests/core/test_cockpit_board_pages.py`）

至少四条：

- 读到：用真样本，要点画对。
- 读不懂、命令不存在、断网：画三态标签，不画要点，页面上不出现“0”和“读到了”。
- 没项目号：要项目号的命令不读，写“没读”。
- 页面上没有按钮。

跑：

```
cd <源码>/scripts
QT_QPA_PLATFORM=offscreen python -m pytest -q ../tests/core/test_cockpit_board*.py ../tests/core/test_pm_dashboard_gui.py ../tests/core/test_pm_dashboard.py
cd .. && ruff check scripts tests && python -m mypy --platform win32 scripts/cockpit_board
```

## 6. 截图自查

改了布局就离屏截图自己看一遍（1366×768 和 1920×1080，浅色和深色），附在 PR 里：

```
QT_QPA_PLATFORM=offscreen python scripts/pm_dashboard_gui.py --root <控制根> --screenshot <前缀>.png
```

读命令的页要真账本才有内容，`--screenshot` 只截不起命令的页；读命令的页在本机打开窗口看。
