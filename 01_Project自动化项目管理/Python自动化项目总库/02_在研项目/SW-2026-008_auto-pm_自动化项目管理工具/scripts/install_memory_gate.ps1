<#
.SYNOPSIS
  内存总闸看门狗的计划任务：安装、修复、卸载、查看。用户只在 setup_env.bat 的第 5 步点一次 Windows 的「是否允许」；agent 不运行本脚本。

.DESCRIPTION
  计划任务以 SYSTEM 运行，所以它执行的一切都必须放在只有管理员能写的地方，并且是被核对过的那一份。其余所有事都不需要管理员。

  -Install    （在普通窗口运行，setup_env.bat 第 5 步调用它）
              预备阶段（不需要管理员，不碰 Program Files）：
                a) git 核对：四个文件加钉哈希文件没有未提交改动，HEAD 已经在 origin/main 里（-AllowUnmerged 可跳过，只给开发者）；
                b) 四个文件的合并 SHA-256 等于仓库里钉住的 scripts\memory_gate.pin.json；
                c) 官方嵌入式 Python 3.12.10 下载到当前用户缓存目录并核对写死的 SHA-256（-PythonZip 可指向事先核对过的本地包）；
                d) 试运行：解压到临时目录，核对 python.exe 的 Authenticode 签名、_pth 没打开 import site、真跑一遍 selftest（杀毒拦截在这里就暴露）。
              预备全过后，只弹一次 UAC，由提权窗口做「应用」：
                1) 清掉旧安装或残留（占用、拒绝访问立即停止，报告是哪个文件、哪个进程）；
                2) 建安装目录，**先**对目录本身设一次权限（SYSTEM、Administrators 完全控制，Users 只读，带继承；用 SID，不受系统语言影响），再往里放文件；
                3) 取嵌入式 Python 包、再核对一遍哈希、解压、核对签名；
                4) 复制三个源文件，复制后再核对哈希，写 manifest.json（含配置文件路径）；
                5) 自检，注册开机自启的计划任务（SYSTEM、最高权限）并启动，核对心跳。
              第 2 到 5 步任何一步失败都会自动回滚：停并注销计划任务、取得所有权、删除半装目录。回滚本身失败会明说，用 -Repair。
  -Repair     清理任何残留（空权限目录、半装目录、遗留计划任务）。不依赖已装的 python.exe：停任务、取得所有权、授权、删除、确认目录不存在。
              被冻结的进程：只有看门狗运行过才需要解冻，用状态文件判断；状态文件读不了或有冻结又无法解冻时明说并停下，由用户决定是否加 -ForceDelete。
  -Uninstall  与 -Repair 走同一条清理路径：能解冻就先解冻（resume-all）；python.exe 坏了也不再中止。
  -Status     只读：计划任务状态 + 看门狗自报的状态（含生效阈值、来源和安装文件校验）。
  -Prepare    只做预备阶段并报告，不安装、不弹 UAC（排查用）。

  信任模型：钉住的哈希文件由 PR 修改并走独立审计，所以以后谁能改总闸，等于谁能合并 PR 的人（用户）；agent 只能提 PR，不能自己装，装好的那份也不会自动更新（更新要用户再点一次 UAC）。

  用法（普通窗口，当前目录是仓库里任意位置；通常不用手敲，setup_env.bat 会调用）：
    powershell -ExecutionPolicy Bypass -File scripts\install_memory_gate.ps1 -Install
#>
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Repair,
    [switch]$Uninstall,
    [switch]$Status,
    [switch]$Prepare,
    [switch]$Elevated,
    [switch]$ForceDelete,
    [switch]$AllowUnmerged,
    [string]$PythonZip = "",
    [string]$ExpectedSha256 = "",
    [string]$ResultFile = ""
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
$Repo = Split-Path $PSScriptRoot -Parent
$BundleFiles = @(
    "auto_pm/infrastructure/long_run_core.py",
    "auto_pm/infrastructure/memory_preflight.py",
    "scripts/install_memory_gate.ps1",
    "scripts/memory_gate.py"
)
$CopiedFiles = @("auto_pm/infrastructure/memory_preflight.py", "auto_pm/infrastructure/long_run_core.py", "scripts/memory_gate.py")
$PinRelative = "scripts/memory_gate.pin.json"
$ConfigRelative = "scripts/memory_gate.json"
$script:LogFile = ""

# ---------------------------------------------------------------- small helpers
function Write-Log([string]$Text) {
    Write-Host $Text
    if ($script:LogFile) {
        try { Add-Content -LiteralPath $script:LogFile -Value $Text -Encoding UTF8 } catch { Write-Host "（日志文件写不进去：$($_.Exception.Message)）" }
    }
}

function Test-IsAdmin {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-Admin {
    if (-not (Test-IsAdmin)) {
        throw "这一步需要管理员权限；请通过 setup_env.bat 或 -Install / -Repair（会弹一次 Windows 的「是否允许」）。"
    }
}

# Run a native program; never throws on a non-zero exit (the caller decides). Code -1 means the program could not start.
function Invoke-Native([string]$File, [string[]]$Arguments) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $oldEncoding = $null
    try {
        # memory_gate.py prints UTF-8 (Chinese messages); read it as UTF-8. A host without a console cannot change this, which is harmless.
        try { $oldEncoding = [Console]::OutputEncoding; [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { $oldEncoding = $null }
        $text = (& $File @Arguments 2>&1 | Out-String)
        return @{ Code = $LASTEXITCODE; Output = $text.Trim() }
    } catch {
        return @{ Code = -1; Output = $_.Exception.Message }
    } finally {
        $ErrorActionPreference = $previous
        if ($null -ne $oldEncoding) { try { [Console]::OutputEncoding = $oldEncoding } catch { Write-Verbose "console encoding not restored" } }
    }
}

# icacls with a non-zero exit code is always an error here: no /C, no swallowed output.
function Invoke-Icacls([string[]]$Arguments) {
    $result = Invoke-Native "icacls.exe" $Arguments
    if ($result.Code -ne 0) { throw "icacls $($Arguments -join ' ') 失败（退出码 $($result.Code)）：$($result.Output)" }
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

function Read-PinnedHash([string]$Root) {
    $path = Join-Path $Root ($PinRelative -replace "/", "\")
    if (-not (Test-Path -LiteralPath $path)) { throw "仓库里没有钉住的哈希文件 ${PinRelative}（先 git pull 到合并了总闸的 main）。" }
    $pin = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    $value = [string]$pin.bundle_sha256
    if ($value -notmatch '^[0-9a-fA-F]{64}$') { throw "$PinRelative 里的 bundle_sha256 格式不对。" }
    return $value.ToLower()
}

# Processes that run something from inside the install folder: they hold its files open.
function Get-InstallHolders([string]$Folder) {
    $names = @()
    foreach ($proc in (Get-Process -ErrorAction SilentlyContinue)) {
        $path = $null
        try { $path = $proc.Path } catch { $path = $null }
        if ($path -and $path.StartsWith($Folder, [StringComparison]::OrdinalIgnoreCase)) { $names += ("{0}(PID {1})" -f $proc.ProcessName, $proc.Id) }
    }
    return $names
}

# ---------------------------------------------------------------- embedded Python: fetch, check, try
function Get-EmbeddedPythonZip([string]$Target, [string]$LocalZip) {
    if ($EmbedSha256 -notmatch '^[0-9a-f]{64}$') { throw "本脚本里嵌入式 Python 的 SHA-256 还没有填写（PIN-REQUIRED），拒绝安装。" }
    $folder = Split-Path $Target -Parent
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
    if ($LocalZip) {
        if (-not (Test-Path -LiteralPath $LocalZip)) { throw "-PythonZip 指向的文件不存在：$LocalZip" }
        Copy-Item -LiteralPath $LocalZip -Destination $Target -Force
    } elseif (Test-Path -LiteralPath $Target) {
        Write-Log "  用缓存里的 $Target"
    } else {
        if (-not $TlsReady) { throw "没能启用 TLS 1.2，不能下载；请改用 -PythonZip 指向事先核对过的包。" }
        try {
            Invoke-WebRequest -Uri $EmbedUrl -OutFile $Target -UseBasicParsing
        } catch {
            throw "下载嵌入式 Python 失败（$($_.Exception.Message)）；请在能上网的电脑下载并核对后，用 -PythonZip 指定本地包重跑。"
        }
    }
    $have = (Get-FileHash -Algorithm SHA256 -LiteralPath $Target).Hash.ToLower()
    if ($have -ne $EmbedSha256) {
        Remove-Item -LiteralPath $Target -Force
        throw "嵌入式 Python 包的 SHA-256 是 ${have}，不是写死的 ${EmbedSha256}，已删除这个包，拒绝安装。"
    }
}

# Unpack a package into $Folder and check what the installer relies on: the signer of python.exe and that site is not switched on.
function Expand-CheckedPython([string]$Zip, [string]$Folder) {
    Expand-Archive -LiteralPath $Zip -DestinationPath $Folder -Force
    $python = Join-Path $Folder "python.exe"
    $signature = Get-AuthenticodeSignature -LiteralPath $python
    if ($signature.Status -ne "Valid" -or $null -eq $signature.SignerCertificate -or $signature.SignerCertificate.Subject -notmatch '(^|, )O=Python Software Foundation(,|$)') {
        throw "python.exe 的 Authenticode 签名无效或签名者不是 Python Software Foundation（状态 $($signature.Status)），拒绝安装。"
    }
    foreach ($pth in Get-ChildItem -LiteralPath $Folder -Filter "*._pth") {
        if (Select-String -LiteralPath $pth.FullName -Pattern '^\s*import\s+site' -Quiet) { throw "$($pth.Name) 打开了 import site，拒绝安装。" }
    }
}

# ---------------------------------------------------------------- the part that needs no administrator
function Invoke-Prepare([string]$Root, [string]$LocalZip, [bool]$SkipGit) {
    Write-Log "预备 1/4 核对总闸文件与钉住的哈希 ..."
    $pinned = Read-PinnedHash $Root
    $bundle = Get-BundleHash $Root
    if ($bundle.Combined -ne $pinned) {
        throw "四个文件的合并 SHA-256 是 $($bundle.Combined)，仓库里钉住的是 ${pinned}，两者不符。请先 git pull 到最新的 main；若你在改总闸文件，要同时重写钉哈希文件并走 PR。"
    }

    Write-Log "预备 2/4 git 核对（文件无未提交改动，HEAD 已在 origin/main 里）..."
    if ($SkipGit) {
        Write-Log "  已按 -AllowUnmerged 跳过。"
    } elseif (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Log "  警告：没找到 git，无法核对来源，只核对了钉住的哈希。"
    } else {
        $top = Invoke-Native "git" @("-C", $Root, "rev-parse", "--show-toplevel")
        if ($top.Code -ne 0) {
            Write-Log "  警告：这份文件不在 git 检出里，无法核对来源，只核对了钉住的哈希。"
        } else {
            $paths = @($BundleFiles + $PinRelative)
            $dirty = Invoke-Native "git" (@("-C", $Root, "status", "--porcelain", "--") + $paths)
            if ($dirty.Code -ne 0) { throw "git status 失败：$($dirty.Output)" }
            if ($dirty.Output) { throw "总闸文件有未提交的改动，拒绝安装：`n$($dirty.Output)" }
            $merged = Invoke-Native "git" @("-C", $Root, "merge-base", "--is-ancestor", "HEAD", "origin/main")
            if ($merged.Code -eq 1) { throw "当前检出（HEAD）还没有合并进 origin/main：只装已经合并并审计过的版本。先 git pull 到 main；开发者调试可加 -AllowUnmerged。" }
            if ($merged.Code -ne 0) { Write-Log "  警告：没能核对 origin/main（$($merged.Output)），只核对了文件无改动和钉住的哈希。" }
        }
    }

    Write-Log "预备 3/4 取官方嵌入式 Python $EmbedVersion 到当前用户缓存并核对哈希 ..."
    $cache = Join-Path $env:LOCALAPPDATA "AutoPM\cache"
    $zip = Join-Path $cache "python-$EmbedVersion-embed-amd64.zip"
    Get-EmbeddedPythonZip $zip $LocalZip

    Write-Log "预备 4/4 试运行（临时目录里解压、核对签名、真跑一遍自检；不碰 Program Files）..."
    $trial = Join-Path ([IO.Path]::GetTempPath()) ("autopm-gate-prep-" + [Guid]::NewGuid().ToString("N"))
    try {
        Expand-CheckedPython $zip $trial
        $python = Join-Path $trial "python.exe"
        $version = Invoke-Native $python @("-I", "-S", "-B", "-c", "import sys; print(sys.version)")
        if ($version.Code -ne 0) { throw "嵌入式 python.exe 在这台电脑上跑不起来（退出码 $($version.Code)）：$($version.Output)。多半是杀毒软件拦了，请先放行再重跑。" }
        $self = Invoke-Native $python @("-I", "-S", "-B", (Join-Path $Root "scripts\memory_gate.py"), "selftest")
        if ($self.Code -ne 0) { throw "自检没有通过（冻结、解冻要在真进程上生效），没有进入安装：`n$($self.Output)" }
    } finally {
        if (Test-Path -LiteralPath $trial) {
            try { Remove-Item -LiteralPath $trial -Recurse -Force -ErrorAction Stop } catch { Write-Log "  提示：临时目录 $trial 没删干净（$($_.Exception.Message)），可以手动删。" }
        }
    }
    Write-Log "预备阶段全部通过。"
    return @{ Bundle = $bundle; Zip = $zip }
}

# ---------------------------------------------------------------- clean-up: used by rollback, -Repair and -Uninstall
# Stops the task and any watchdog process, takes ownership, thaws if anything is frozen, unregisters the task and deletes the folder.
# Throws with a plain-words reason when it cannot finish; the caller says what to do next.
# SIDs that hold an Allow entry on one item; throws when the ACL cannot be read.
function Get-AllowedSids([string]$Path) {
    $sids = @()
    foreach ($rule in (Get-Acl -LiteralPath $Path -ErrorAction Stop).Access) {
        if ($rule.AccessControlType -ne "Allow") { continue }
        try { $sids += $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } catch { $sids += [string]$rule.IdentityReference }
    }
    return $sids
}

# Every item under (and including) the folder whose ACL cannot be read or has no entry at all.  The folder is listed, never changed.
function Get-TreeAccessProblems([string]$Folder) {
    $problems = @()
    $items = @(Get-Item -LiteralPath $Folder -Force)
    $listErrors = $null
    $items += @(Get-ChildItem -LiteralPath $Folder -Recurse -Force -ErrorAction SilentlyContinue -ErrorVariable listErrors)
    foreach ($item in $items) {
        try {
            if (@((Get-Acl -LiteralPath $item.FullName -ErrorAction Stop).Access).Count -eq 0) { $problems += "$($item.FullName)（权限列表是空的）" }
        } catch {
            $problems += "$($item.FullName)（读不了权限：$($_.Exception.Message)）"
        }
    }
    foreach ($listError in @($listErrors)) { $problems += "列目录出错：$($listError.Exception.Message)" }
    return $problems
}

# One item: owner becomes Administrators first (the take-ownership and restore privileges are switched on by .NET for this), then the ACL is
# replaced by exactly SYSTEM and Administrators, full control.  Two calls, because the second needs the ownership the first gives.
function Set-ItemAdminAccess([IO.FileSystemInfo]$Item) {
    $admins = New-Object Security.Principal.SecurityIdentifier("S-1-5-32-544")
    $system = New-Object Security.Principal.SecurityIdentifier("S-1-5-18")
    $isDir = $Item -is [IO.DirectoryInfo]
    $inherit = [Security.AccessControl.InheritanceFlags]::None
    if ($isDir) { $inherit = [Security.AccessControl.InheritanceFlags]"ContainerInherit,ObjectInherit" }
    if ($isDir) { $ownerOnly = New-Object Security.AccessControl.DirectorySecurity } else { $ownerOnly = New-Object Security.AccessControl.FileSecurity }
    $ownerOnly.SetOwner($admins)
    if ($isDir) { [IO.Directory]::SetAccessControl($Item.FullName, $ownerOnly) } else { [IO.File]::SetAccessControl($Item.FullName, $ownerOnly) }
    if ($isDir) { $rights = New-Object Security.AccessControl.DirectorySecurity } else { $rights = New-Object Security.AccessControl.FileSecurity }
    $rights.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($admins, $system)) {
        $rights.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid, [Security.AccessControl.FileSystemRights]::FullControl, $inherit, [Security.AccessControl.PropagationFlags]::None, [Security.AccessControl.AccessControlType]::Allow)))
    }
    if ($isDir) { [IO.Directory]::SetAccessControl($Item.FullName, $rights) } else { [IO.File]::SetAccessControl($Item.FullName, $rights) }
}

# The whole tree, folder by folder from the top (a folder is made listable before its children are read).  Returns one line of what was done.
function Set-TreeAdminAccess([string]$Folder) {
    $done = 0
    $failed = @()
    $queue = New-Object 'System.Collections.Generic.Queue[System.IO.FileSystemInfo]'
    $queue.Enqueue((Get-Item -LiteralPath $Folder -Force))
    while ($queue.Count -gt 0) {
        $item = $queue.Dequeue()
        $isLink = (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
        if ($isLink) { $failed += "$($item.FullName)（是符号链接/联接点，不跟进）"; continue }
        try { Set-ItemAdminAccess $item; $done++ } catch { $failed += "$($item.FullName)（$($_.Exception.Message)）" }
        if ($item -is [IO.DirectoryInfo]) {
            $listErrors = $null
            foreach ($child in @(Get-ChildItem -LiteralPath $item.FullName -Force -ErrorAction SilentlyContinue -ErrorVariable listErrors)) { $queue.Enqueue($child) }
            foreach ($listError in @($listErrors)) { $failed += "列目录出错：$($listError.Exception.Message)" }
        }
    }
    return ("逐个设置：成功 {0} 个，失败 {1} 个{2}" -f $done, $failed.Count, $(if ($failed.Count -gt 0) { "（" + (($failed | Select-Object -First 3) -join " ｜ ") + "）" } else { "" }))
}

# After the install: nothing under the install folder may have an empty or unreadable ACL, and the three files the task runs must be
# open to SYSTEM and Administrators.  An empty ACL makes the folder impossible to clean up later, so it fails the install (which rolls back).
function Assert-InstalledAcls([string]$Folder) {
    $problems = @(Get-TreeAccessProblems $Folder)
    if ($problems.Count -gt 0) { throw "安装后 $($problems.Count) 个条目的权限是空的或读不了，拒绝继续（例如 $($problems[0])）。" }
    foreach ($relative in @("python\python.exe", "scripts\memory_gate.py", "manifest.json")) {
        $path = Join-Path $Folder $relative
        if (-not (Test-Path -LiteralPath $path)) { throw "安装后 $path 不存在。" }
        $sids = @(Get-AllowedSids $path)
        foreach ($need in @("S-1-5-18", "S-1-5-32-544")) {
            if ($sids -notcontains $need) { throw "安装后 $path 的权限里没有 $need 的允许项（现有：$($sids -join ', ')），拒绝继续。" }
        }
    }
}

# Gives Administrators ownership of, and full control over, everything under a leftover folder, whatever its ACLs look like
# (an empty ACL, an owner that no longer exists, a deny entry).  Every step's exit code is kept and returned as one text line:
# a failing step does not stop the next one (a later step can succeed where an earlier one failed), but the caller reports
# all of them if the folder still cannot be deleted - nothing is swallowed.
function Reset-FolderAccess([string]$Folder) {
    $admins = "*S-1-5-32-544"
    $steps = @(
        @{ Name = "takeown /R"; File = "takeown.exe"; Arguments = @("/F", $Folder, "/A", "/R", "/D", "Y") },
        @{ Name = "icacls /setowner"; File = "icacls.exe"; Arguments = @($Folder, "/setowner", $admins, "/T", "/C") },
        @{ Name = "icacls /reset"; File = "icacls.exe"; Arguments = @($Folder, "/reset", "/T", "/C") },
        @{ Name = "icacls /grant"; File = "icacls.exe"; Arguments = @($Folder, "/grant", "${admins}:(OI)(CI)F", "/T", "/C") }
    )
    # Our own parent folder is checked the same way (one level, never recursively); it only matters if it was left damaged.
    $parent = Split-Path -Parent $Folder
    if ((Split-Path -Leaf $parent) -eq "AutoPM" -and (Test-Path -LiteralPath $parent)) {
        $steps = @(
            @{ Name = "takeown 上一级"; File = "takeown.exe"; Arguments = @("/F", $parent, "/A") },
            @{ Name = "icacls /reset 上一级"; File = "icacls.exe"; Arguments = @($parent, "/reset") }
        ) + $steps
    }
    $trace = @()
    foreach ($step in $steps) {
        $result = Invoke-Native $step.File $step.Arguments
        $trace += ("{0} 退出码 {1}" -f $step.Name, $result.Code)
        if ($result.Code -ne 0) { Write-Log ("  {0} 退出码 {1}：{2}" -f $step.Name, $result.Code, $result.Output) }
    }
    # An exit code of 0 proved nothing on the laptop (11-04): icacls with the carry-on switch reported success while the files kept an empty ACL.
    # So the result is judged by looking at every item's ACL, and what is still wrong is fixed item by item through .NET.
    $problems = @(Get-TreeAccessProblems $Folder)
    $trace += "命令执行后仍有问题的条目 $($problems.Count) 个"
    if ($problems.Count -gt 0) {
        Write-Log "  命令退出码正常，但还有 $($problems.Count) 个条目的权限不对（例如 $($problems[0])），改为逐个条目设置 ..."
        $trace += (Set-TreeAdminAccess $Folder)
        $problems = @(Get-TreeAccessProblems $Folder)
        $trace += "逐个设置后仍有问题的条目 $($problems.Count) 个" + $(if ($problems.Count -gt 0) { "（" + (($problems | Select-Object -First 3) -join " ｜ ") + "）" } else { "" })
    }
    return ($trace -join "；")
}

# Last resort for a folder the normal delete cannot remove: mirror an empty folder over it with the backup privilege (/B), then remove the shell.
function Clear-FolderWithBackupRights([string]$Folder) {
    $empty = Join-Path ([IO.Path]::GetTempPath()) ("AutoPM-empty-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $empty | Out-Null
    try {
        $mirror = Invoke-Native "robocopy.exe" @($empty, $Folder, "/MIR", "/B", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
        $note = "robocopy 退出码 $($mirror.Code)"
        if ($mirror.Code -ge 8 -or $mirror.Code -lt 0) { Write-Log "  ${note}：$($mirror.Output)" }
        try { Remove-Item -LiteralPath $Folder -Recurse -Force -ErrorAction Stop } catch { $note = $note + "，之后删除仍失败：" + $_.Exception.Message }
        return $note
    } finally {
        Remove-Item -LiteralPath $empty -Recurse -Force -ErrorAction Stop
    }
}

# One line for the error message: who owns the folder and who has what on it (read through icacls, which also works when Get-Acl is refused).
function Get-OwnerAndAcl([string]$Folder) {
    $shown = Invoke-Native "icacls.exe" @($Folder)
    $owner = ""
    try { $owner = (Get-Acl -LiteralPath $Folder -ErrorAction Stop).Owner } catch { $owner = "读不出所有者（$($_.Exception.Message)）" }
    $lines = @(($shown.Output -split "`n") | ForEach-Object { $_.Trim() } | Where-Object { $_ } | Select-Object -First 6)
    return "所有者 $owner；icacls 退出码 $($shown.Code)：$($lines -join ' | ')"
}

function Remove-GateInstallation([string]$Folder, [string]$Name, [bool]$Force) {
    $stateDir = Join-Path $Folder "state"
    $python = Join-Path $Folder "python\python.exe"
    $gate = Join-Path $Folder "scripts\memory_gate.py"
    $access = "没有执行（目录不存在）"

    if (Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue) {
        if (Test-Path -LiteralPath $stateDir) {
            try {
                New-Item -ItemType File -Force -Path (Join-Path $stateDir "STOP") | Out-Null
                Start-Sleep -Seconds 10
            } catch {
                Write-Log "  没能写 STOP 文件（$($_.Exception.Message)），改为直接停任务。"
            }
        }
        Stop-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $Folder) {
        foreach ($proc in (Get-Process -ErrorAction SilentlyContinue)) {
            $path = $null
            try { $path = $proc.Path } catch { $path = $null }
            if ($path -and $path.StartsWith($Folder, [StringComparison]::OrdinalIgnoreCase)) {
                Write-Log "  停止仍在运行的 $($proc.ProcessName)（PID $($proc.Id)）"
                Stop-Process -Id $proc.Id -Force -ErrorAction Stop
            }
        }
        # Ownership and rights first: a folder left with an empty ACL (or owned by nobody who can act) cannot even be read until this is done.
        $access = Reset-FolderAccess $Folder

        # Thaw only if the watchdog ever ran (state file), and say so plainly when that cannot be decided.
        $statePath = Join-Path $stateDir "state.json"
        $frozen = 0
        $unknown = $false
        if (Test-Path -LiteralPath $statePath) {
            try {
                $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($null -ne $state.frozen) { $frozen = @($state.frozen).Count }
            } catch {
                $unknown = $true
            }
        }
        if ($frozen -gt 0 -or $unknown) {
            $thawed = $false
            if ((Test-Path -LiteralPath $python) -and (Test-Path -LiteralPath $gate)) {
                $resume = Invoke-Native $python @("-I", "-S", "-B", $gate, "resume-all")
                $thawed = ($resume.Code -eq 0)
                if (-not $thawed) { Write-Log "  resume-all 退出码 $($resume.Code)：$($resume.Output)" }
            }
            if (-not $thawed) {
                $why = if ($unknown) { "状态文件读不了，不知道有没有进程被冻结" } else { "状态文件里有 $frozen 个被冻结的进程树，但已装的 python.exe 跑不了，没法解冻" }
                if (-not $Force) {
                    throw "${why}，所以没有删除任何东西。被冻结的进程只是暂停：重启电脑会结束它们（未保存内容会丢）。你决定可以接受时，加 -ForceDelete 重跑；不接受就先在任务管理器里处理这些进程。"
                }
                Write-Log "  警告：${why}；按 -ForceDelete 继续删除，被冻结的进程会保持暂停，直到被关闭或重启。"
            }
        }
    }

    if (Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction Stop
        if (Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue) { throw "计划任务 $Name 没能注销。" }
    }
    if (Test-Path -LiteralPath $Folder) {
        $failure = ""
        try { Remove-Item -LiteralPath $Folder -Recurse -Force -ErrorAction Stop } catch { $failure = $_.Exception.Message }
        if (Test-Path -LiteralPath $Folder) {
            # Second way in: robocopy /B works through the backup/restore privileges of an elevated token, so it is not stopped by an ACL that names nobody.
            Write-Log "  普通删除没成功（${failure}），改用备份权限清空 ..."
            $failure = $failure + " ／ " + (Clear-FolderWithBackupRights $Folder)
        }
        if (Test-Path -LiteralPath $Folder) {
            $left = @(Get-ChildItem -LiteralPath $Folder -Recurse -Force -ErrorAction SilentlyContinue | Select-Object -First 5 -ExpandProperty FullName)
            $holders = @(Get-InstallHolders $Folder)
            $owner = Get-OwnerAndAcl $Folder
            throw "安装目录 $Folder 没能删除：${failure}。还留着：$($left -join '; ')。占用它的进程：$(if ($holders) { $holders -join ', ' } else { '没找到（可能是杀毒软件或资源管理器占用）' })。改权限的每一步：$access。目录现状：$owner。"
        }
    }
}

# After the folder is locked down: nobody but SYSTEM and Administrators may hold a write-capable right on it.
function Assert-DestLocked([string]$Folder) {
    $writeBits = [Security.AccessControl.FileSystemRights]::WriteData -bor [Security.AccessControl.FileSystemRights]::AppendData -bor `
        [Security.AccessControl.FileSystemRights]::Delete -bor [Security.AccessControl.FileSystemRights]::ChangePermissions -bor `
        [Security.AccessControl.FileSystemRights]::TakeOwnership
    foreach ($rule in (Get-Acl -LiteralPath $Folder).Access) {
        if ($rule.AccessControlType -ne "Allow") { continue }
        $sid = [string]$rule.IdentityReference
        try { $sid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } catch { $sid = [string]$rule.IdentityReference }
        if ($sid -eq "S-1-5-18" -or $sid -eq "S-1-5-32-544") { continue }
        if (($rule.FileSystemRights -band $writeBits) -ne 0) { throw "$Folder 上 $($rule.IdentityReference) 仍有写权限（$($rule.FileSystemRights)），权限设置不对，拒绝继续。" }
    }
}

# ---------------------------------------------------------------- the part that needs the administrator (one UAC)
function Invoke-Apply([string]$Root, [string]$Expected, [string]$Zip) {
    Assert-Admin
    if ($PSCommandPath -ne (Join-Path $PSScriptRoot "install_memory_gate.ps1")) { throw "请直接运行仓库里的 scripts\install_memory_gate.ps1。" }
    if ($Expected -notmatch '^[0-9a-fA-F]{64}$') { throw "提权阶段没有收到合法的 -ExpectedSha256；请通过 -Install 运行。" }
    Write-Log "1/6 在提权窗口里再核对一遍要安装的文件 ..."
    $bundle = Get-BundleHash $Root
    if ($bundle.Combined -ne $Expected.ToLower() -or $bundle.Combined -ne (Read-PinnedHash $Root)) {
        throw "四个文件的合并 SHA-256 是 $($bundle.Combined)，与预备阶段核对过的、仓库钉住的不一致（文件在预备之后被改动），拒绝安装。"
    }
    $installedPython = Join-Path $Dest "python\python.exe"
    $installedGate = Join-Path $Dest "scripts\memory_gate.py"
    $stateDir = Join-Path $Dest "state"

    try {
        Write-Log "2/6 清掉旧安装或残留（有就清，占用或拒绝访问会在这里停下并说明）..."
        Remove-GateInstallation $Dest $TaskName $false

        Write-Log "3/6 建安装目录并先锁权限 $Dest ..."
        New-Item -ItemType Directory -Force -Path $Dest | Out-Null
        Invoke-Icacls @($Dest, "/setowner", "*S-1-5-32-544")
        Invoke-Icacls @($Dest, "/inheritance:r", "/grant:r", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F", "*S-1-5-32-545:(OI)(CI)RX")
        Assert-DestLocked $Dest
        New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

        Write-Log "4/6 放入嵌入式 Python ${EmbedVersion}（锁好权限之后才解压，复制后再核对哈希）..."
        $zipInDest = Join-Path $Dest "python-embed.zip"
        Copy-Item -LiteralPath $Zip -Destination $zipInDest -Force
        $have = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipInDest).Hash.ToLower()
        if ($have -ne $EmbedSha256) { throw "嵌入式 Python 包复制后的 SHA-256 是 ${have}，不是写死的 ${EmbedSha256}（预备之后被改动），拒绝安装。" }
        Expand-CheckedPython $zipInDest (Join-Path $Dest "python")
        Remove-Item -LiteralPath $zipInDest -Force

        Write-Log "5/6 复制三个源文件并再核对一遍，写 manifest.json ..."
        $files = [ordered]@{}
        foreach ($relative in $CopiedFiles) {
            $target = Join-Path $Dest ($relative -replace "/", "\")
            New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
            Copy-Item -LiteralPath (Join-Path $Root ($relative -replace "/", "\")) -Destination $target -Force
            if ((Get-NormalizedSha256 $target) -ne $bundle.Files[$relative]) { throw "$relative 复制后的哈希与核对过的不一致（复制过程中被改动），拒绝安装。" }
            $files[$relative] = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLower()
        }
        $manifest = [ordered]@{
            files = $files
            bundle_sha256 = $bundle.Combined
            embedded_python_sha256 = $EmbedSha256
            installed_at = (Get-Date).ToString("o")
            python = $installedPython
            config_path = (Join-Path $Root ($ConfigRelative -replace "/", "\"))
        } | ConvertTo-Json -Depth 4
        [IO.File]::WriteAllText((Join-Path $Dest "manifest.json"), $manifest, (New-Object Text.UTF8Encoding($false)))
        Assert-DestLocked $Dest
        Assert-InstalledAcls $Dest

        Write-Log "6/6 自检、注册计划任务 ${TaskName}（开机自启，SYSTEM，最高权限）并启动 ..."
        $self = Invoke-Native $installedPython @("-I", "-S", "-B", $installedGate, "selftest")
        if ($self.Code -ne 0) { throw "安装后的自检没有通过：`n$($self.Output)" }
        $action = New-ScheduledTaskAction -Execute $installedPython -Argument ('-I -S -B "{0}" run --require-manifest' -f $installedGate) -WorkingDirectory $Dest
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
            -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
        Start-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 12
        $gateStatus = Invoke-Native $installedPython @("-I", "-S", "-B", $installedGate, "status")
        if ($gateStatus.Code -ne 0) { throw "计划任务已注册，但看门狗没有上报心跳（看 ${stateDir}\gate.log）：$($gateStatus.Output)" }
        Write-Log $gateStatus.Output
    } catch {
        $reason = $_.Exception.Message
        Write-Log "安装失败：$reason"
        Write-Log "开始回滚（停并注销计划任务、删半装目录）..."
        try {
            Remove-GateInstallation $Dest $TaskName $false
            Write-Log "已回滚：没有留下计划任务，也没有留下 ${Dest}。"
        } catch {
            Write-Log "回滚没有清干净：$($_.Exception.Message)"
            Write-Log "请在普通窗口运行：powershell -ExecutionPolicy Bypass -File scripts\install_memory_gate.ps1 -Repair"
        }
        throw "安装没有完成：$reason"
    }
    Write-Log "已安装并在运行。"
}

# One UAC prompt: start this same script elevated with the mode switch and what it was told in the unprivileged phase.
function Start-ElevatedSelf([string[]]$Switches, [hashtable]$Values) {
    $self = (Get-Process -Id $PID).Path
    $parts = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"{0}"' -f $PSCommandPath)) + $Switches + @("-Elevated")
    foreach ($key in $Values.Keys) { if ($Values[$key]) { $parts += @("-$key", ('"{0}"' -f $Values[$key])) } }
    try {
        $proc = Start-Process -FilePath $self -ArgumentList ($parts -join " ") -Verb RunAs -Wait -PassThru
    } catch {
        throw "没有点「是」，或系统拒绝了提权（$($_.Exception.Message)）。什么都没有安装，也没有改动；需要时重跑 setup_env.bat。"
    }
    return $proc.ExitCode
}

function Show-Status {
    $installedPython = Join-Path $Dest "python\python.exe"
    $installedGate = Join-Path $Dest "scripts\memory_gate.py"
    Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Get-ScheduledTaskInfo | Format-List TaskName, LastRunTime, LastTaskResult, NextRunTime | Out-Host
    if (-not (Test-Path -LiteralPath $installedPython)) {
        Write-Host "总闸没有安装（$Dest 里没有 python.exe）。"
        return 1
    }
    $result = Invoke-Native $installedPython @("-I", "-S", "-B", $installedGate, "status")
    Write-Host $result.Output
    return $result.Code
}

# Tests dot-source this file to reach the functions above; nothing below runs then.
if ($MyInvocation.InvocationName -eq ".") { return }

# ---------------------------------------------------------------- entry
$modes = @($Install, $Repair, $Uninstall, $Status, $Prepare) | Where-Object { $_ }
if (@($modes).Count -gt 1) { throw "一次只能用一个模式：-Install、-Repair、-Uninstall、-Status、-Prepare。" }
if (@($modes).Count -eq 0) { $Status = [switch]$true }

if ($Status) {
    exit (Show-Status)
}

if ($ResultFile) { $script:LogFile = $ResultFile }

if ($Prepare) {
    [void](Invoke-Prepare $Repo $PythonZip $AllowUnmerged.IsPresent)
    exit 0
}

if ($Install -and -not $Elevated) {
    try {
        $prepared = Invoke-Prepare $Repo $PythonZip $AllowUnmerged.IsPresent
    } catch {
        Write-Host "预备没有通过，没有改动 Program Files：$($_.Exception.Message)"
        exit 1
    }
    $log = Join-Path $env:LOCALAPPDATA "AutoPM\cache\install-result.log"
    Set-Content -LiteralPath $log -Value "" -Encoding UTF8
    if (Test-IsAdmin) {
        $script:LogFile = $log
        try { Invoke-Apply $Repo $prepared.Bundle.Combined $prepared.Zip } catch { Write-Host $_.Exception.Message; exit 1 }
        exit 0
    }
    Write-Host ""
    Write-Host "预备全部通过。下一步 Windows 会弹一次「是否允许」，请点「是」（只做安装，不会做别的）。"
    try {
        $code = Start-ElevatedSelf @("-Install") @{ ExpectedSha256 = $prepared.Bundle.Combined; PythonZip = $prepared.Zip; ResultFile = $log }
    } catch {
        Write-Host $_.Exception.Message
        exit 1
    }
    Write-Host "---- 提权窗口的记录 ----"
    Get-Content -LiteralPath $log -Encoding UTF8 | ForEach-Object { Write-Host $_ }
    Write-Host "---- 复核（普通权限，只读）----"
    $verdict = Show-Status
    if ($code -eq 0 -and $verdict -eq 0) {
        Write-Host "总闸已安装并在运行。"
        exit 0
    }
    Write-Host "总闸没有装好：见上面的记录。残留可用 -Repair 清理。"
    exit 1
}

if ($Install -and $Elevated) {
    try {
        Invoke-Apply $Repo $ExpectedSha256 $PythonZip
        Start-Sleep -Seconds 3
        exit 0
    } catch {
        Write-Log "失败：$($_.Exception.Message)"
        Read-Host "按回车关闭这个窗口"
        exit 1
    }
}

# -Repair / -Uninstall: same clean-up path. Elevate once if this is a normal window.
if (-not (Test-IsAdmin)) {
    try {
        $log = Join-Path $env:LOCALAPPDATA "AutoPM\cache\cleanup-result.log"
        New-Item -ItemType Directory -Force -Path (Split-Path $log -Parent) | Out-Null
        Set-Content -LiteralPath $log -Value "" -Encoding UTF8
        $switches = @($(if ($Repair) { "-Repair" } else { "-Uninstall" }))
        if ($ForceDelete) { $switches += "-ForceDelete" }
        Write-Host "Windows 会弹一次「是否允许」，请点「是」。"
        $code = Start-ElevatedSelf $switches @{ ResultFile = $log }
    } catch {
        Write-Host $_.Exception.Message
        exit 1
    }
    Get-Content -LiteralPath $log -Encoding UTF8 | ForEach-Object { Write-Host $_ }
    exit $code
}

try {
    Write-Log "清理 $Dest 和计划任务 $TaskName ..."
    Remove-GateInstallation $Dest $TaskName $ForceDelete.IsPresent
    Write-Log "已清理：计划任务不存在，$Dest 不存在；被冻结的进程已全部解冻或已按你的选择处理。"
    if ($Elevated) { Start-Sleep -Seconds 3 }
    exit 0
} catch {
    Write-Log "没有清理完：$($_.Exception.Message)"
    if ($Elevated) { Read-Host "按回车关闭这个窗口" }
    exit 1
}
