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
try {
    & $python $entry @args
    # 直接运行时用 exit 交回退出码（失败必须非 0）；只有被点号引用（. .\pm-as-trae.ps1）时才不 exit，免得关掉调用者的终端
    if ($MyInvocation.InvocationName -ne '.') { exit $LASTEXITCODE }
}
finally {
    if ($null -eq $previous) {
        Remove-Item Env:AUTO_PM_AGENT -ErrorAction SilentlyContinue
    }
    else {
        $env:AUTO_PM_AGENT = $previous
    }
}
