# 2026-11-04 归档：gui_test_report

> 只移动、不删除、不改文件字节（git 记录为 100% 重命名）。恢复：`git mv` 回 `04_监控/02_整改项/gui_test_report`。

| 旧路径（相对母体根目录） | 现路径（本目录下） | 为什么过时 | 证据 |
|---|---|---|---|
| `04_监控/02_整改项/gui_test_report/GUI测试报告_V0.9.2.md` | `GUI测试报告_V0.9.2.md` | 2026-07 的 V0.9.2 GUI 测试报告，当前基线是 1.3.3 | 文件名即版本；全库只被旧 PM_SESSION 归档和历史工具原型里的文字提到 |
| `04_监控/02_整改项/gui_test_report/test_result.json` | `test_result.json` | 同一轮测试的结果 | 同上 |
| `04_监控/02_整改项/gui_test_report/2026-07-13/test_result.json` | `2026-07-13/test_result.json` | 2026-07-13 的结果 | 同上 |
| `04_监控/02_整改项/gui_test_report/2026-07-13-v2/test_result.json` | `2026-07-13-v2/test_result.json` | 2026-07-13 第二轮结果 | 同上 |

核对：代码、测试、工作流都没有读 `gui_test_report`（只有 `05_收尾/02_PM_SESSION归档/` 里两份旧归档和 `03_归档/` 下的历史原型提到名字，属历史记录，原样保留）。
