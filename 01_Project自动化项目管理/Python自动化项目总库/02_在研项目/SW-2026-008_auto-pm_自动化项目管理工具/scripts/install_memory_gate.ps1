<#
.SYNOPSIS
  内存总闸看门狗的计划任务：安装、卸载、查看。-Install / -Uninstall 需要管理员 PowerShell，由用户本人运行（agent 不运行本脚本）。

.DESCRIPTION
  计划任务以 SYSTEM 运行，所以它执行的代码不能放在用户可写的地方（否则能改文件的人就等于拿到 SYSTEM）。
  -Install    把 memory_gate.py、memory_preflight.py、long_run_core.py 复制到 %ProgramFiles%\AutoPM\MemoryGate，只给 SYSTEM 和
              Administrators 完全控制、Users 只读；记下三个文件的 SHA-256（manifest.json）；用系统安装的 Python（不用 .venv）先自检
              （冻结、解冻都要真生效），通过后注册开机自启的计划任务并启动。以后更新只能由管理员重跑 -Install。
  -Uninstall  先让看门狗解冻全部进程并退出，再确认解冻，最后删除计划任务和安装目录。
  -Status     只读：计划任务状态 + 看门狗自报的状态（含安装文件的 SHA-256 核对）。

  解释器必须在只有管理员能写的位置（如 C:\Program Files\Python312）。如果你的 Python 装在用户目录里，加 -CopyPython，
  脚本会把那个 Python 整个复制进安装目录再用（不能是 .venv 里的）。

  用法（管理员 PowerShell，在仓库任意目录）：
    powershell -ExecutionPolicy Bypass -File scripts\install_memory_gate.ps1 -Install
#>
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status,
    [string]$Python = "",
    [switch]$CopyPython
)

$ErrorActionPreference = "Stop"
$TaskName = "AutoPM-MemoryGate"
$Dest = Join-Path $env:ProgramFiles "AutoPM\MemoryGate"
$StateDir = Join-Path $Dest "state"
$InstalledGate = Join-Path $Dest "scripts\memory_gate.py"
$Repo = Split-Path $PSScriptRoot -Parent
$Sources = [ordered]@{
    "scripts\memory_gate.py"                        = Join-Path $PSScriptRoot "memory_gate.py"
    "auto_pm\infrastructure\memory_preflight.py"    = Join-Path $Repo "auto_pm\infrastructure\memory_preflight.py"
    "auto_pm\infrastructure\long_run_core.py"       = Join-Path $Repo "auto_pm\infrastructure\long_run_core.py"
}

function Assert-Admin {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "请用管理员 PowerShell 运行本脚本（开始菜单里右键 Windows PowerShell，选“以管理员身份运行”）。"
    }
}

# True when ordinary users (or the owner, if it is not an administrator) can change what is at $Path or any folder above it.
function Test-UserWritable([string]$Path) {
    $ordinary = @("S-1-5-32-545", "S-1-1-0", "S-1-5-11", "S-1-5-4")      # Users, Everyone, Authenticated Users, INTERACTIVE
    $trusted = @("S-1-5-18", "S-1-5-32-544", "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464")
    $bits = [int][Security.AccessControl.FileSystemRights]::WriteData -bor [int][Security.AccessControl.FileSystemRights]::AppendData `
        -bor [int][Security.AccessControl.FileSystemRights]::Delete -bor [int][Security.AccessControl.FileSystemRights]::ChangePermissions `
        -bor [int][Security.AccessControl.FileSystemRights]::TakeOwnership
    $current = $Path
    while ($current) {
        $acl = Get-Acl -LiteralPath $current
        $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
        if ($trusted -notcontains $owner) { return $true }
        foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
            if ($rule.AccessControlType -eq "Allow" -and ($ordinary -contains $rule.IdentityReference.Value) -and (([int]$rule.FileSystemRights -band $bits) -ne 0)) { return $true }
        }
        $parent = Split-Path $current -Parent
        if (-not $parent -or $parent -eq $current) { break }
        $current = $parent
    }
    return $false
}

function Find-SystemPython {
    if ($Python) { return (Resolve-Path -LiteralPath $Python).Path }
    $found = $null
    if (Get-Command py.exe -ErrorAction SilentlyContinue) { $found = (& py.exe -3 -c "import sys; print(sys.executable)") 2>$null }
    if (-not $found) { $cmd = Get-Command python.exe -ErrorAction SilentlyContinue; if ($cmd) { $found = $cmd.Source } }
    if (-not $found) { throw "找不到系统安装的 Python；请用 -Python 指定 python.exe 的完整路径。" }
    return $found.Trim()
}

function Installed-Python {
    $manifest = Join-Path $Dest "manifest.json"
    if (-not (Test-Path $manifest)) { throw "没有安装（找不到 $manifest）。" }
    return (Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json).python
}

if (($Install.IsPresent + $Uninstall.IsPresent + $Status.IsPresent) -ne 1) {
    throw "请只指定 -Install、-Uninstall、-Status 其中一个。"
}

if ($Status) {
    Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Get-ScheduledTaskInfo | Format-List TaskName, LastRunTime, LastTaskResult, NextRunTime
    & (Installed-Python) -I -B $InstalledGate status
    exit $LASTEXITCODE
}

Assert-Admin

if ($Install) {
    Write-Host "1/5 选解释器 ..."
    $Py = Find-SystemPython
    if ((Test-Path (Join-Path (Split-Path $Py -Parent) "pyvenv.cfg")) -or (Test-Path (Join-Path (Split-Path $Py -Parent | Split-Path -Parent) "pyvenv.cfg"))) {
        throw "$Py 是虚拟环境里的解释器；请用系统安装的 Python（-Python 指定）。"
    }
    $PyHome = Split-Path $Py -Parent
    if (Test-UserWritable $PyHome) {
        if (-not $CopyPython) {
            throw "$PyHome 普通用户能写，SYSTEM 任务不能用它。请换 C:\Program Files 下的 Python（-Python），或加 -CopyPython 把它复制进安装目录。"
        }
    }

    Write-Host "2/5 复制到 $Dest 并锁权限 ..."
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 8
    New-Item -ItemType Directory -Force -Path $Dest, $StateDir | Out-Null
    foreach ($old in @("scripts", "auto_pm", "python", "manifest.json")) { Remove-Item -LiteralPath (Join-Path $Dest $old) -Recurse -Force -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath (Join-Path $StateDir "STOP") -ErrorAction SilentlyContinue
    foreach ($relative in $Sources.Keys) {
        $target = Join-Path $Dest $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -LiteralPath $Sources[$relative] -Destination $target -Force
    }
    if ($CopyPython -and (Test-UserWritable $PyHome)) {
        Copy-Item -LiteralPath $PyHome -Destination (Join-Path $Dest "python") -Recurse -Force
        $Py = Join-Path $Dest "python\python.exe"
    }
    icacls $Dest /setowner "*S-1-5-32-544" /T /C | Out-Null
    icacls $Dest /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-32-545:(OI)(CI)RX" /T /C | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls 没有设置成功，没有安装。" }

    Write-Host "3/5 记下文件的 SHA-256（manifest.json）..."
    $files = [ordered]@{}
    foreach ($relative in $Sources.Keys) {
        $files[$relative.Replace("\", "/")] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Dest $relative)).Hash.ToLower()
    }
    $json = [ordered]@{ files = $files; installed_at = (Get-Date).ToString("o"); python = $Py } | ConvertTo-Json -Depth 4
    [IO.File]::WriteAllText((Join-Path $Dest "manifest.json"), $json, (New-Object Text.UTF8Encoding($false)))

    Write-Host "4/5 自检：用无害的假进程走一遍 冻结 -> 解冻（用的就是将要安装的那份文件）..."
    & $Py -I -B $InstalledGate selftest
    if ($LASTEXITCODE -ne 0) { throw "自检没有通过，没有注册计划任务。请把上面的输出原样发给 Claude。" }

    Write-Host "5/5 注册计划任务 $TaskName（开机自启，SYSTEM，最高权限）并启动 ..."
    $action = New-ScheduledTaskAction -Execute $Py -Argument ('-I -B "{0}" run --require-manifest' -f $InstalledGate) -WorkingDirectory $Dest
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 12
    & $Py -I -B $InstalledGate status
    if ($LASTEXITCODE -ne 0) { throw "计划任务已注册，但看门狗没有上报心跳；看 $StateDir\gate.log。" }
    Write-Host "已安装并在运行。更新代码要重跑 -Install；卸载：powershell -ExecutionPolicy Bypass -File scripts\install_memory_gate.ps1 -Uninstall"
    exit 0
}

# -Uninstall: ask the watchdog to stop (it unfreezes everything before it exits), check again, then remove the task and the folder.
$Py = Installed-Python
New-Item -ItemType File -Force -Path (Join-Path $StateDir "STOP") | Out-Null
Start-Sleep -Seconds 10
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
& $Py -I -B $InstalledGate resume-all
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $Dest -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "已卸载；被冻结的进程已全部解冻。"
