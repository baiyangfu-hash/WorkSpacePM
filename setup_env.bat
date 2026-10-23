@echo off
chcp 65001 >nul
title Auto-PM 研发工作台 - 环境初始化向导

echo ==============================================================================
echo        Auto-PM 工业级 AI 研发工作台 - 一键环境初始化向导
echo ==============================================================================
echo.

:: 1. 检查 Python：锁定文件只覆盖 Python 3.12（requirements-lock-py312-win.txt）
set "PY_EXE="
python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
if %errorlevel% equ 0 set "PY_EXE=python"
if not defined PY_EXE py -3.12 -c "import sys" >nul 2>&1 && set "PY_EXE=py -3.12"
if not defined PY_EXE (
    echo [错误] 未找到 Python 3.12。依赖锁定文件只覆盖 Python 3.12，请安装 3.12 并勾选 "Add Python to PATH"。
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] 正在检测 Python 版本...
%PY_EXE% --version

:: 2. 创建虚拟环境
if not exist ".venv" (
    echo [2/4] 正在创建专属虚拟环境 .venv ...
    %PY_EXE% -m venv .venv
    if %errorlevel% neq 0 (
        echo [错误] 创建虚拟环境失败，请检查 Python 权限。
        pause
        exit /b 1
    )
) else (
    echo [2/4] 虚拟环境 .venv 已存在，跳过创建。
)

:: 3. 激活虚拟环境并安装依赖
echo [3/4] 正在激活虚拟环境并安装核心依赖库...
call .venv\Scripts\activate.bat
python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 已有的 .venv 不是 Python 3.12。请把 .venv 改名备份（例如 .venv.old）后重新运行本脚本。
    pause
    exit /b 1
)
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet

set "LOCK_FILE=00_Infrastructure\auto_pm\environment\requirements-lock-py312-win.txt"
if not exist "%LOCK_FILE%" (
    echo [错误] 依赖锁定文件缺失: %LOCK_FILE%
    pause
    exit /b 1
)
echo 正在按锁定文件安装依赖（精确版本，不解析新依赖）...
python -m pip install --no-deps -r "%LOCK_FILE%" -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败，请检查网络后重新运行本脚本。
    pause
    exit /b 1
)
python -m pip check
if %errorlevel% neq 0 (
    echo [错误] 依赖一致性检查未通过（pip check），请把上面的输出发给维护者。
    pause
    exit /b 1
)

:: 4. 校验稳定入口（运行时通过 manifest 校验的 active release，不安装平铺源码）
set "STABLE_LAUNCHER=00_Infrastructure\auto_pm\launcher\launch.py"
set "ACTIVE_POINTER=00_Infrastructure\auto_pm\active_release.json"
set "DEPLOYMENT_MANIFEST=00_Infrastructure\auto_pm\deployment_manifest.json"
if not exist "%STABLE_LAUNCHER%" (
    echo [错误] 稳定入口缺失: %STABLE_LAUNCHER%
    pause
    exit /b 1
)
if not exist "%ACTIVE_POINTER%" (
    echo [错误] active release 指针缺失: %ACTIVE_POINTER%
    pause
    exit /b 1
)
if not exist "%DEPLOYMENT_MANIFEST%" (
    echo [错误] 部署 manifest 缺失: %DEPLOYMENT_MANIFEST%
    pause
    exit /b 1
)
echo [4/4] 稳定入口已就绪: %STABLE_LAUNCHER%
echo       运行时将由 stable launcher 校验 active release；不安装研发平铺源码。

echo.
echo ==============================================================================
echo  [成功] Auto-PM 工作台环境已成功就绪！
echo.
echo  • 启动桌面驾驶舱：双击运行 "双击启动驾驶舱.bat" 或执行 "python main.py"
echo  • 运行 CLI：执行 "python main.py --help"（统一经过 stable launcher）
echo  • 运行全量单测：pytest
echo  • 运行规范体检：python main.py spec sync（统一经过 stable launcher）
echo ==============================================================================
echo.
pause
