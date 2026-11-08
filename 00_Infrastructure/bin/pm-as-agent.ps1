# 以指定 agent 的身份运行驾驶舱命令（任何 agent 通用）：只在这一条命令期间带上 AUTO_PM_AGENT=<基名[:备注]>，命令结束立刻还原。
# 命令只认冒号前面那段（基名，见 AGENTS.md WS-001 的工位与前缀表：claude、trae、cursor、vscode、codex）；冒号后只是备注。
# 用法（在控制根）：  .\00_Infrastructure\bin\pm-as-agent.ps1 cursor pm orient <项目编号> --json
#                     .\00_Infrastructure\bin\pm-as-agent.ps1 trae:cn pm orient <项目编号> --json
# 为什么需要：只有 Claude Code 和 Codex 自带环境变量能被认出；其他 agent 不声明身份，会被当成用户本人，
# 用户本人才能签的批准和风险签字（pm approve、pm accept、pm sign-risk）就拦不住它。
# 不要在终端里长期设置 AUTO_PM_AGENT：用户自己在同一个终端敲口令的命令会被当成 agent 拒绝。
# 需要用户本人敲口令的命令（pm approve、pm accept、pm sign-risk）不要用这个脚本运行（带标记会被拒绝）。
# 非 Windows 的 shell：同样只对单条命令设置，例如  AUTO_PM_AGENT=cursor python main.py pm orient <项目编号> --json
$ErrorActionPreference = "Stop"

if ($args.Count -lt 2) {
    Write-Error "用法：pm-as-agent.ps1 <基名[:备注]> <main.py 的参数...>，例如 pm-as-agent.ps1 cursor pm orient <项目编号> --json"
    exit 2
}
$agent = [string]$args[0]
$rest = @($args | Select-Object -Skip 1)

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $root ".venv\Scripts\python.exe"
$entry = Join-Path $root "main.py"

$previous = $env:AUTO_PM_AGENT
$env:AUTO_PM_AGENT = $agent
$stopPreference = $ErrorActionPreference
try {
    # D-132：Windows PowerShell 5.1 在 Stop 下会把原生命令写到 stderr 的每一行（如启动器的 "launcher: release verified…"）
    # 升级成终止错误，命令其实已跑完，脚本却中途退出并返回 -1。调用原生命令这一小段改回 Continue，成败只看退出码。
    $ErrorActionPreference = "Continue"
    & $python $entry @rest
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $stopPreference
    # 直接运行时用 exit 交回退出码（失败必须非 0）；只有被点号引用（. .\pm-as-agent.ps1）时才不 exit，免得关掉调用者的终端
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
