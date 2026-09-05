@echo off
chcp 65001 >nul
title Auto-PM 研发工作台 - 环境初始化向导

echo ==============================================================================
echo        Auto-PM 工业级 AI 研发工作台 - 一键环境初始化向导
echo ==============================================================================
echo.

:: 1. 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python 环境！请先安装 Python 3.11+ 并勾选 "Add Python to PATH"。
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] 正在检测 Python 版本...
python --version

:: 2. 创建虚拟环境
if not exist ".venv" (
    echo [2/4] 正在创建专属虚拟环境 (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [错误] 创建虚拟环境失败，请检查 Python 权限。
        pause
        exit /b 1
    )
) else (
    echo [2/4] 虚拟环境 (.venv) 已存在，跳过创建。
)

:: 3. 激活虚拟环境并安装依赖
echo [3/4] 正在激活虚拟环境并安装核心依赖库...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet

if exist "requirements.txt" (
    echo 正在从 requirements.txt 安装依赖...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)

:: 4. auto-pm 核心模块由稳定部署容器双槽指针按需加载（NG-WP-13）
::    不再执行 editable/.pth 安装，也不回退旧母体路径；main.py 启动时自动解析
::    00_Infrastructure/auto_pm/active_release.json 指向的 release。

echo.
echo ==============================================================================
echo  [成功] Auto-PM 工作台环境已成功就绪！
echo.
echo  • 启动桌面驾驶舱：双击运行 "双击启动驾驶舱.bat" 或执行 "python main.py"
echo  • 运行全量单测：pytest
echo ==============================================================================
echo.
pause
