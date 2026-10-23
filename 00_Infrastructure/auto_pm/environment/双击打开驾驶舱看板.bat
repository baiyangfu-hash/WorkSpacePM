@echo off
chcp 65001 >nul
title 驾驶舱总控屏

rem 驾驶舱总控屏：项目经理看板只读；工程工位只做本机检查和追加一行 BC（先预览）。没有执行、合并、删除、切换按钮。
rem 脚本在 SW-2026-008 源码目录 scripts\pm_dashboard_gui.py，不在 releases\ 里，不走发布切换。
rem 这个 bat 放在控制根\00_Infrastructure\auto_pm\environment\（控制根白名单不收新文件），往上三级就是控制根。
rem 想放桌面：右键这个 bat，“发送到 - 桌面快捷方式”，别把 bat 本身拷出去。
rem 路径用纯英文通配符找，避免中文路径在不同代码页下读错。

cd /d "%~dp0..\..\.."
set "ROOT=%CD%"
set PYTHONDONTWRITEBYTECODE=1

set "SCRIPT="
for /d %%A in ("%ROOT%\01_Project*") do for /d %%B in ("%%~A\Python*") do for /d %%C in ("%%~B\02_*") do for /d %%D in ("%%~C\SW-2026-008_*") do if exist "%%~D\scripts\pm_dashboard_gui.py" set "SCRIPT=%%~D\scripts\pm_dashboard_gui.py"
if not defined SCRIPT (
    echo [提示] 没找到总控屏脚本 scripts\pm_dashboard_gui.py，请确认这个 bat 在 控制根\00_Infrastructure\auto_pm\environment\ 里，且仓库已更新。
    pause
    exit /b 1
)

set "PYTHON_EXE="
set "PYTHONW_EXE="
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
if exist ".venv\Scripts\pythonw.exe" set "PYTHONW_EXE=.venv\Scripts\pythonw.exe"
if not defined PYTHON_EXE (
    python --version >nul 2>&1 && set "PYTHON_EXE=python"
    where pythonw >nul 2>&1 && set "PYTHONW_EXE=pythonw"
)
if not defined PYTHON_EXE (
    echo [提示] 没找到 Python，请先双击 setup_env.bat 配好环境。
    pause
    exit /b 1
)

"%PYTHON_EXE%" -B -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    echo [提示] 这台电脑的 Python 没装 PySide6，请先双击 setup_env.bat 配好环境。
    pause
    exit /b 1
)

rem 有 pythonw 就不留黑窗口；启动出错的原因写在系统临时目录的“驾驶舱总控屏_启动错误.txt”。
if defined PYTHONW_EXE (
    start "" "%PYTHONW_EXE%" -B "%SCRIPT%" --root "%ROOT%"
    exit /b 0
)
"%PYTHON_EXE%" -B "%SCRIPT%" --root "%ROOT%"
if errorlevel 1 pause
exit /b 0
