"""驾驶舱总控屏（PySide6）——分层包。

    theme.py        颜色、字体、间距、圆角的唯一定义处；改一处全界面生效。
    viewmodel.py    纯 Python：把 pm_dashboard 读出来的数据算成画面要显示的东西（健康、问题三档、
                    要你出手、六项检查三态、工程工位六步）。不 import Qt，可单独测试。
    policy.py       按钮白名单、禁用词、永不加的动作。测试按它清点。
    actions.py      工程工位的本机动作（跑检查、写 BC 行、判在线）：唯一允许起子进程和写文件的地方。
    widgets/        每个画面一个文件，只画 viewmodel 给的数据，不算业务。
    app.py          主窗口：模式切换、后台读取、把 viewmodel 交给画面。

设计稿：/mnt/project-files/plans/驾驶舱总控屏设计_20261022.md（共享文件夹）。
"""
