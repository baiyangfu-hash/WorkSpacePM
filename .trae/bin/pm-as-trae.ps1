# 以 Trae 的身份运行驾驶舱命令：只在这一条命令期间带上 AUTO_PM_AGENT=trae:cn，命令结束立刻还原。
# 命令只认冒号前面那段（trae），所以 Trae 国际版和 CN 版都用同一个值；后缀只是备注。
# 用法（在控制根）：  .\.trae\bin\pm-as-trae.ps1 pm orient <项目编号> --json
# 不要在终端里长期设置这个变量：用户自己在同一个终端敲口令的命令（pm approve / pm accept / pm sign-risk）会被当成 agent 拒绝。
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $root ".venv\Scripts\python.exe"
$entry = Join-Path $root "main.py"

$previous = $env:AUTO_PM_AGENT
$env:AUTO_PM_AGENT = "trae:cn"
$stopPreference = $ErrorActionPreference
try {
    # D-142（同 D-132）：Windows PowerShell 5.1 在 Stop 下会把原生命令写到 stderr 的每一行升级成终止错误；调用方用 2>&1 或
    # 2> 文件 收 stderr 时还会被包成 NativeCommandError。所以调用这一小段改回 Continue，自己把原生 stderr 合进管道、转回
    # 普通文本写到真正的 stderr，成败只看退出码（管道最后一环是 ForEach-Object，$LASTEXITCODE 仍是原生命令的）。
    $ErrorActionPreference = "Continue"
    & $python $entry @args 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) { [Console]::Error.WriteLine($_.ToString()) } else { $_ }
    }
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $stopPreference
    # 直接运行时用 exit 交回退出码（失败必须非 0）；只有被点号引用（. .\pm-as-trae.ps1）时才不 exit，免得关掉调用者的终端
    if ($MyInvocation.InvocationName -ne '.') { exit $exitCode }
}
finally {
    $ErrorActionPreference = $stopPreference
    if ($null -eq $previous) {
        Remove-Item Env:AUTO_PM_AGENT -ErrorAction SilentlyContinue
    }
    else {
        $env:AUTO_PM_AGENT = $previous
    }
}
