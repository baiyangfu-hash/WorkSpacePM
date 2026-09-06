@echo off
chcp 65001 >nul
title Auto-PM 工业级桌面驾驶舱

cd /d "%~dp0"

set "PYTHON_EXE="
set "EXIT_CODE=0"
set "WORKSPACE_DIR=%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    goto :launch
)

python --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python"
    goto :launch
)

echo.
echo ==============================================================================
echo [提示] 未检测到可用的 Python 环境！
echo 请先双击运行 "setup_env.bat" 进行一键配置与依赖安装。
echo ==============================================================================
echo.
echo 按任意键关闭窗口...
pause >nul
exit /b 1

:launch
"%PYTHON_EXE%" main.py %*
set "EXIT_CODE=%ERRORLEVEL%"

if %EXIT_CODE% equ 0 goto :clean_exit

echo.
echo ==============================================================================
echo [错误] Auto-PM 桌面驾驶舱异常退出 [退出码: %EXIT_CODE%]
echo 详细错误报告与堆栈日志已保存至:
echo   %WORKSPACE_DIR%.auto-pm\logs\startup_crash.log
echo ==============================================================================
echo.
echo 请根据上方日志排查原因。按任意键关闭窗口...
pause >nul
exit /b %EXIT_CODE%

:clean_exit
exit /b 0
