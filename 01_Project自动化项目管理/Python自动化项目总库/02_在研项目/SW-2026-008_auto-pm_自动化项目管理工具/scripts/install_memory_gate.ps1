<#
.SYNOPSIS
  内存总闸看门狗的计划任务：安装、卸载、查看。需要管理员 PowerShell，由用户本人运行（agent 不运行本脚本）。

.DESCRIPTION
  -Install    先用无害的假进程自检（冻结、解冻都要真生效），通过后注册开机自启的计划任务（SYSTEM、最高权限、失败 1 分钟后重启，最多 3 次）并立即启动。
  -Uninstall  先让看门狗停下，再解冻所有被它冻结的进程，最后删除计划任务。
  -Status     只读：计划任务状态 + 看门狗自报的状态。

  用法（管理员 PowerShell，在仓库任意目录）：
    powershell -ExecutionPolicy Bypass -File scripts\install_memory_gate.ps1 -Install
#>
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$TaskName = "AutoPM-MemoryGate"
$Gate = Join-Path $PSScriptRoot "memory_gate.py"
$StateDir = Join-Path $env:ProgramData "auto_pm\memory-gate"

function Find-Python {
    if ($Python) { return $Python }
    $dir = $PSScriptRoot
    while ($dir) {
        $candidate = Join-Path $dir ".venv\Scripts\python.exe"
        if (Test-Path $candidate) { return $candidate }
        $parent = Split-Path $dir -Parent
        if (-not $parent -or $parent -eq $dir) { break }
        $dir = $parent
    }
    throw "找不到 .venv\Scripts\python.exe；请用 -Python 指定解释器的完整路径。"
}

function Assert-Admin {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "请用管理员 PowerShell 运行本脚本（开始菜单里右键 Windows PowerShell，选“以管理员身份运行”）。"
    }
}

if (($Install.IsPresent + $Uninstall.IsPresent + $Status.IsPresent) -ne 1) {
    throw "请只指定 -Install、-Uninstall、-Status 其中一个。"
}
$Py = Find-Python

if ($Status) {
    Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Get-ScheduledTaskInfo | Format-List TaskName, LastRunTime, LastTaskResult, NextRunTime
    & $Py -B $Gate status
    exit $LASTEXITCODE
}

Assert-Admin

if ($Install) {
    Write-Host "1/3 自检：用无害的假进程走一遍 冻结 -> 解冻 ..."
    & $Py -B $Gate selftest
    if ($LASTEXITCODE -ne 0) { throw "自检没有通过，没有安装。请把上面的输出原样发给 Claude。" }
    Write-Host "2/3 注册计划任务 $TaskName（开机自启，SYSTEM，最高权限）..."
    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
    Remove-Item (Join-Path $StateDir "STOP") -ErrorAction SilentlyContinue
    $action = New-ScheduledTaskAction -Execute $Py -Argument ('-B "{0}" run' -f $Gate) -WorkingDirectory (Split-Path $PSScriptRoot -Parent)
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Write-Host "3/3 启动并核对 ..."
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 12
    & $Py -B $Gate status
    if ($LASTEXITCODE -ne 0) { throw "计划任务已注册，但看门狗没有上报心跳；看 $StateDir\gate.log。" }
    Write-Host "已安装并在运行。卸载：powershell -ExecutionPolicy Bypass -File scripts\install_memory_gate.ps1 -Uninstall"
    exit 0
}

# -Uninstall: stop the watchdog first (so it cannot freeze again), then unfreeze everything it froze, then remove the task.
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $StateDir "STOP") | Out-Null
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 6
& $Py -B $Gate resume-all
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "已卸载；被冻结的进程已全部解冻。"
