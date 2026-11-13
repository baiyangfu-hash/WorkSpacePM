"""“工具”页和“流程图”页的按钮规矩。测试按这里清点，改规矩只改这里（决定类按钮的规矩仍在 policy.py）。"""

from __future__ import annotations

from cockpit_board import policy

# 工具页：窗口里允许出现的按钮文字只有这些。每个都对应 tool_actions.TOOLS 里的一条命令，或“打开高级工作台”。
TOOL_BUTTONS = frozenset({
    "变更单", "决策", "变量表", "入箱",  # 前四个页签
    "列出变更单", "查看这张", "预览命令", "创建变更单", "转状态",
    "列出决策", "查看这个决策",
    "选择文件…", "在项目里找", "查重",
    "记入收件箱",
    "项目", "新建项目", "登记",  # 第五个页签和它的两个运行键（CHG-SCPT-2026-654）
    "打开高级工作台",
})

# 顶栏里多出来的两个页面入口（app.py 的页面按钮；policy.PM_BUTTONS 管其余顶栏按钮）。
NAV_BUTTONS = frozenset({"流程图", "工具"})

# 流程图页的按钮文字来自 flow/graphs.json 里各图的 title（任务、工作项、执行、变更单），测试按数据文件清点，不在这里写死。

# 按钮文字和提示里不许出现的词：永远不加的（policy.NEVER）再加几个“做决定”的字眼——工具页不做决定。
TOOL_FORBIDDEN_WORDS = tuple(sorted(set(policy.NEVER) | {"批准", "同意", "退回", "开工", "验收", "收口", "放行"}))
