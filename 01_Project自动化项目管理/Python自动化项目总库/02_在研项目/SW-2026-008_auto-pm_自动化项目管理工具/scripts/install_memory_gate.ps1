<#
.SYNOPSIS
  内存总闸看门狗的计划任务：安装、卸载、查看。-Install / -Uninstall 需要管理员 PowerShell，由用户本人运行（agent 不运行本脚本）。

.DESCRIPTION
  计划任务以 SYSTEM 运行，所以它执行的一切都必须放在只有管理员能写的地方，并且是被核对过的那一份：
  -Install    必须给 -ExpectedSha256（审计过的四个文件的合并哈希，见下）。提权路径里不跑 git（不 fetch、不 status、不 merge-base）：
              只核对四个文件（三个要安装的源文件 + 本脚本自己）的合并 SHA-256 等于 -ExpectedSha256。通过后：
              1) 在 %ProgramFiles%\AutoPM\MemoryGate 建目录并先锁权限（icacls：SYSTEM、Administrators 完全控制，Users 只读；用 SID，不受系统语言影响）；
              2) 取官方嵌入式 Python（固定版本，下载或用 -PythonZip 指定本地包），核对写死在本脚本里的 SHA-256 后解压进该目录，
                 再核对 python.exe 的 Authenticode 签名者是 Python Software Foundation；不用机器上装的 Python，也不用 .venv；
                 下载失败（TLS 不通、被代理拦）时改用 -PythonZip 指向事先核对过的本地包；
              3) 复制三个源文件，复制后再核对一遍哈希，记入 manifest.json；
              4) 用 python -I -S -B 先自检（冻结、解冻都要真生效），通过后注册开机自启的计划任务（SYSTEM、最高权限）并启动。
  -Uninstall  先让看门狗解冻全部进程并退出，再确认解冻，最后删除计划任务和安装目录。解冻没有确认（resume-all 退出码非 0，例如状态文件读不了）就停下，
              什么都不删，提示重跑。只装了一半（没有 Python、没有状态目录、没有计划任务）也能卸干净。
  -Status     只读：计划任务状态 + 看门狗自报的状态（含安装文件的 SHA-256 核对）。

  -ExpectedSha256 怎么得到：在仓库根的「控制根」里运行 python -B scripts\memory_gate.py bundle-hash，它列出四个文件各自的哈希和合并哈希；
  用户只应使用审计报告里写明的那个合并哈希。合并哈希把 CRLF 当作 LF 计算，Windows 和 Linux 检出的结果相同。

  运行前先核对本脚本自己（审计 579 R6）：在资源管理器里按住 Shift 右键仓库的 scripts 文件夹，选「在此处打开 PowerShell 窗口」，运行
    certutil -hashfile install_memory_gate.ps1 SHA256
  输出必须等于 PR 描述里写的「脚本工作区哈希」（Windows 检出的 CRLF 字节），一致才继续。

  用法（管理员 PowerShell，当前目录是仓库里任意位置）：
    powershell -ExecutionPolicy Bypass -File scripts\install_memory_gate.ps1 -Install -ExpectedSha256 <64 位十六进制>
#>
[CmdletBinding(DefaultParameterSetName = "Status")]
param(
    [Parameter(ParameterSetName = "Install", Mandatory = $true)][switch]$Install,
    [Parameter(ParameterSetName = "Install", Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedSha256,
    [Parameter(ParameterSetName = "Install")][string]$PythonZip = "",
    [Parameter(ParameterSetName = "Uninstall", Mandatory = $true)][switch]$Uninstall,
    [Parameter(ParameterSetName = "Status", Mandatory = $true)][switch]$Status
)

$ErrorActionPreference = "Stop"

# Windows PowerShell 5.1 may default to old TLS; the download needs 1.2. If this fails, use -PythonZip with a package checked beforehand.
$TlsReady = $true
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {
    $TlsReady = $false
    Write-Warning "无法启用 TLS 1.2（$($_.Exception.Message)）：不能联网下载，请改用 -PythonZip 指向事先核对过的 python-3.12.10-embed-amd64.zip。"
}

# 官方嵌入式 Python：版本固定（与 CI 相同的 3.12.10），哈希写死。取不到匹配的包就不安装。
$EmbedVersion = "3.12.10"
$EmbedUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
# SHA-256 of python-3.12.10-embed-amd64.zip: computed 2026-11-03 (MST) on the laptop by M3 from the official python.org URL above;
# the python.org page lists MD5 fe8ef205f2e9c3ba44d0cf9954e1abd3 and the download is 11133606 bytes (both matched). Second, independent check at install time:
# python.exe must carry a valid Authenticode signature of Python Software Foundation (Windows certificate chain, not the web site).
$EmbedSha256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"

$TaskName = "AutoPM-MemoryGate"
$Dest = Join-Path $env:ProgramFiles "AutoPM\MemoryGate"
$StateDir = Join-Path $Dest "state"
$InstalledGate = Join-Path $Dest "scripts\memory_gate.py"
$InstalledPython = Join-Path $Dest "python\python.exe"
$Repo = Split-Path $PSScriptRoot -Parent
$BundleFiles = @(
    "auto_pm/infrastructure/long_run_core.py",
    "auto_pm/infrastructure/memory_preflight.py",
    "scripts/install_memory_gate.ps1",
    "scripts/memory_gate.py"
)
$CopiedFiles = @("auto_pm/infrastructure/memory_preflight.py", "auto_pm/infrastructure/long_run_core.py", "scripts/memory_gate.py")

function Assert-Admin {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "请用管理员 PowerShell 运行本脚本（开始菜单里右键 Windows PowerShell，选「以管理员身份运行」）。"
    }
}

# SHA-256 of a file with CRLF read as LF (Latin-1 keeps one character per byte), the same as memory_gate.py's bundle-hash.
function Get-NormalizedSha256([string]$Path) {
    $latin1 = [Text.Encoding]::GetEncoding(28591)
    $text = $latin1.GetString([IO.File]::ReadAllBytes($Path)).Replace("`r`n", "`n")
    $sha = [Security.Cryptography.SHA256]::Create()
    return ([BitConverter]::ToString($sha.ComputeHash($latin1.GetBytes($text))) -replace "-", "").ToLower()
}

function Get-BundleHash([string]$Root) {
    $lines = @{}
    $text = ""
    foreach ($relative in $BundleFiles) {
        $digest = Get-NormalizedSha256 (Join-Path $Root ($relative -replace "/", "\"))
        $lines[$relative] = $digest
        $text += ("{0}  {1}`n" -f $digest, $relative)
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    $combined = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text))) -replace "-", "").ToLower()
    return @{ Combined = $combined; Files = $lines }
}

if ($Status) {
    Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Get-ScheduledTaskInfo | Format-List TaskName, LastRunTime, LastTaskResult, NextRunTime
    & $InstalledPython -I -S -B $InstalledGate status
    exit $LASTEXITCODE
}

Assert-Admin

if ($Install) {
    Write-Host "1/6 核对要安装的文件 ..."
    if ($EmbedSha256 -notmatch '^[0-9a-f]{64}$') { throw "本脚本里嵌入式 Python 的 SHA-256 还没有填写（PIN-REQUIRED），拒绝安装。" }
    if ($PSCommandPath -ne (Join-Path $PSScriptRoot "install_memory_gate.ps1")) { throw "请直接运行仓库里的 scripts\install_memory_gate.ps1。" }
    $bundle = Get-BundleHash $Repo
    if ($bundle.Combined -ne $ExpectedSha256.ToLower()) {
        throw "四个文件的合并 SHA-256 是 $($bundle.Combined)，与 -ExpectedSha256 不符，拒绝安装。"
    }

    Write-Host "2/6 建安装目录并先锁权限 $Dest ..."
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 8
    New-Item -ItemType Directory -Force -Path $Dest, $StateDir | Out-Null
    icacls $Dest /setowner "*S-1-5-32-544" /T /C | Out-Null
    icacls $Dest /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-32-545:(OI)(CI)RX" /T /C | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls 没有设置成功，没有安装。" }
    foreach ($old in @("scripts", "auto_pm", "python", "manifest.json", "python-embed.zip")) { Remove-Item -LiteralPath (Join-Path $Dest $old) -Recurse -Force -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath (Join-Path $StateDir "STOP") -ErrorAction SilentlyContinue

    Write-Host "3/6 取官方嵌入式 Python $EmbedVersion 并核对哈希 ..."
    $zip = Join-Path $Dest "python-embed.zip"
    if ($PythonZip) {
        Copy-Item -LiteralPath $PythonZip -Destination $zip -Force
    } else {
        if (-not $TlsReady) { throw "没能启用 TLS 1.2，不能下载；请改用 -PythonZip 指向事先核对过的包。" }
        try {
            Invoke-WebRequest -Uri $EmbedUrl -OutFile $zip -UseBasicParsing
        } catch {
            throw "下载嵌入式 Python 失败（$($_.Exception.Message)）；请在能上网的电脑下载并核对后，用 -PythonZip 指定本地包重跑。"
        }
    }
    $have = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLower()
    if ($have -ne $EmbedSha256) {
        Remove-Item -LiteralPath $zip -Force
        throw "嵌入式 Python 包的 SHA-256 是 ${have}，不是写死的 ${EmbedSha256}，拒绝安装。"
    }
    Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $Dest "python") -Force
    Remove-Item -LiteralPath $zip -Force
    $signature = Get-AuthenticodeSignature -LiteralPath $InstalledPython
    if ($signature.Status -ne "Valid" -or $null -eq $signature.SignerCertificate -or $signature.SignerCertificate.Subject -notmatch '(^|, )O=Python Software Foundation(,|$)') {
        throw "python.exe 的 Authenticode 签名无效或签名者不是 Python Software Foundation（状态 $($signature.Status)），拒绝安装。"
    }
    foreach ($pth in Get-ChildItem -LiteralPath (Join-Path $Dest "python") -Filter "*._pth") {
        if (Select-String -LiteralPath $pth.FullName -Pattern '^\s*import\s+site' -Quiet) { throw "$($pth.Name) 打开了 import site，拒绝安装。" }
    }

    Write-Host "4/6 复制三个源文件并再核对一遍 ..."
    $files = [ordered]@{}
    foreach ($relative in $CopiedFiles) {
        $target = Join-Path $Dest ($relative -replace "/", "\")
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -LiteralPath (Join-Path $Repo ($relative -replace "/", "\")) -Destination $target -Force
        if ((Get-NormalizedSha256 $target) -ne $bundle.Files[$relative]) { throw "$relative 复制后的哈希与核对过的不一致（复制过程中被改动），拒绝安装。" }
        $files[$relative] = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLower()
    }
    $json = [ordered]@{ files = $files; bundle_sha256 = $bundle.Combined; embedded_python_sha256 = $EmbedSha256; installed_at = (Get-Date).ToString("o"); python = $InstalledPython } | ConvertTo-Json -Depth 4
    [IO.File]::WriteAllText((Join-Path $Dest "manifest.json"), $json, (New-Object Text.UTF8Encoding($false)))
    icacls $Dest /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-32-545:(OI)(CI)RX" /T /C | Out-Null

    Write-Host "5/6 自检：用无害的假进程走一遍 冻结 -> 解冻（用的就是将要安装的那份文件和那个 Python）..."
    & $InstalledPython -I -S -B $InstalledGate selftest
    if ($LASTEXITCODE -ne 0) { throw "自检没有通过，没有注册计划任务。请把上面的输出原样发给 Claude。" }

    Write-Host "6/6 注册计划任务 ${TaskName}（开机自启，SYSTEM，最高权限）并启动 ..."
    $action = New-ScheduledTaskAction -Execute $InstalledPython -Argument ('-I -S -B "{0}" run --require-manifest' -f $InstalledGate) -WorkingDirectory $Dest
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 12
    & $InstalledPython -I -S -B $InstalledGate status
    if ($LASTEXITCODE -ne 0) { throw "计划任务已注册，但看门狗没有上报心跳；看 $StateDir\gate.log。" }
    Write-Host "已安装并在运行。更新代码要重跑 -Install（带新的 -ExpectedSha256）；卸载：powershell -ExecutionPolicy Bypass -File scripts\install_memory_gate.ps1 -Uninstall"
    exit 0
}

# -Uninstall: ask the watchdog to stop (it unfreezes everything before it exits), check again, then remove the task and the folder.
# Works on a half-finished install too: every step checks that what it touches exists.
if (Test-Path -LiteralPath $StateDir) {
    New-Item -ItemType File -Force -Path (Join-Path $StateDir "STOP") | Out-Null
    Start-Sleep -Seconds 10
}
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ((Test-Path -LiteralPath $InstalledPython) -and (Test-Path -LiteralPath $InstalledGate)) {
    & $InstalledPython -I -S -B $InstalledGate resume-all
    if ($LASTEXITCODE -ne 0) {
        throw "resume-all 返回 ${LASTEXITCODE}：没有确认被冻结的进程已全部解冻（状态文件读不了？），所以没有删除计划任务和安装目录。请稍后重新运行 -Uninstall，或先手动运行：`"$InstalledPython`" -I -S -B `"$InstalledGate`" resume-all"
    }
} else {
    Write-Host "没有找到已安装的 Python 或看门狗脚本（可能只装了一半），跳过解冻步骤。"
}
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $Dest) {
    icacls $Dest /setowner "*S-1-5-32-544" /T /C | Out-Null
    icacls $Dest /grant "*S-1-5-32-544:(OI)(CI)F" /T /C | Out-Null
    Remove-Item -LiteralPath $Dest -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $Dest) { throw "安装目录 $Dest 没能删除干净（可能有文件被占用）；重启后再运行 -Uninstall。" }
}
Write-Host "已卸载；被冻结的进程已全部解冻。"
