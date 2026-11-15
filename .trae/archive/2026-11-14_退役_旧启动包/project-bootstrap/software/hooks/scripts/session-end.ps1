$ErrorActionPreference = "Stop"

function Find-Value {
    param(
        [string]$Content,
        [string]$Pattern
    )

    $match = [regex]::Match($Content, $Pattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)
    if ($match.Success) {
        return $match.Groups[1].Value.Trim()
    }
    return ""
}

$repoRoot = (Resolve-Path ".").Path
$projectType = if ($env:PROJECT_TYPE) { $env:PROJECT_TYPE } else { "generic" }
$verifyHint = if ($env:VERIFY_HINT) { $env:VERIFY_HINT } else { "Update PM_SESSION before ending the session." }
$draftSubdir = if ($env:DRAFT_SUBDIR) { $env:DRAFT_SUBDIR } else { ".trae/handoffs" }
$draftDir = Join-Path $repoRoot $draftSubdir

New-Item -ItemType Directory -Force -Path $draftDir | Out-Null

$pmSession = Get-ChildItem -Path $repoRoot -Filter "PM_SESSION_*.md" -File | Select-Object -First 1
$pmSessionName = if ($pmSession) { $pmSession.Name } else { "(PM_SESSION not found)" }
$currentFocus = ""

if ($pmSession) {
    $content = Get-Content -Path $pmSession.FullName -Raw -Encoding UTF8
    $currentFocus = Find-Value -Content $content -Pattern '^- current_focus:\s*(.+)$'
}

# ── pytest 门禁拦截与自愈 ────────────────────────────────
$testFailed = $false
$testSummary = ""
$blockerText = ""
$notVerifiedText = ""

# 自动寻找 .venv 目录，向上层目录寻找
$venvDir = ""
$curDir = $repoRoot
while ($curDir -ne "" -and $curDir -ne $null) {
    $tempVenv = Join-Path $curDir ".venv"
    if (Test-Path $tempVenv) {
        $venvDir = $tempVenv
        break
    }
    $parentDir = Split-Path $curDir -Parent
    if ($parentDir -eq $curDir) {
        break
    }
    $curDir = $parentDir
}

if ($venvDir -ne "") {
    $pytestExe = ""
    if (Test-Path (Join-Path $venvDir "Scripts\pytest.exe")) {
        $pytestExe = Join-Path $venvDir "Scripts\pytest.exe"
    } elseif (Test-Path (Join-Path $venvDir "bin\pytest")) {
        $pytestExe = Join-Path $venvDir "bin\pytest"
    }

    if ($pytestExe -ne "") {
        Write-Output "[sessionEnd] 正在运行 pytest 单元测试回归检查..."
        $tempOut = [System.IO.Path]::GetTempFileName()
        $process = Start-Process -FilePath $pytestExe -ArgumentList "--no-cov", "-q" -NoNewWindow -PassThru -RedirectStandardOutput $tempOut -Wait
        $exitCode = $process.ExitCode
        $pytestOutput = Get-Content -Path $tempOut -Raw
        Remove-Item -Path $tempOut -Force

        if ($exitCode -ne 0) {
            $testFailed = $true
            # 仅提取 pytest 输出的最后几行（如 summary 信息）以防止 draft 膨胀
            $lines = $pytestOutput -split "`r?`n"
            $lastLines = @()
            $startCapture = $false
            foreach ($line in $lines) {
                if ($line -match '===.*failed') {
                    $startCapture = $true
                }
                if ($startCapture -or $line -match 'failed' -or $line -match 'error') {
                    $lastLines += $line
                }
            }
            if ($lastLines.Count -eq 0) {
                $startIndex = [Math]::Max(0, $lines.Count - 5)
                for ($i = $startIndex; $i -lt $lines.Count; $i++) {
                    $lastLines += $lines[$i]
                }
            }
            $testSummary = $lastLines -join "`r`n"
            Write-Output "[sessionEnd] ❌ 警告: 单元测试失败！"
            Write-Output $testSummary
        } else {
            Write-Output "[sessionEnd] ✅ pytest 单元测试全部通过。"
        }
    }
}

if ($testFailed) {
    $currentFocus = "[WARNING: TEST FAILING] " + $currentFocus
    $blockerText = "    - ❌ pytest 单元测试回归失败！错误摘要:`r`n" + $testSummary.Replace("`n", "`n      ")
    $notVerifiedText = "    - Code changes (due to test failures)"
} else {
    $blockerText = "    - "
    $notVerifiedText = "    - "
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$generatedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$draftName = "$timestamp--session-handoff-draft.md"
$draftPath = Join-Path $draftDir $draftName
$latestPath = Join-Path $draftDir "latest-session-handoff-draft.md"

$draft = @"
# Session Handoff Draft

- generated_at: $generatedAt
- draft_source: $draftName
- project_type: $projectType
- pm_session: $pmSessionName
- current_focus: $currentFocus

## 6. Implementation Log
- <YYYY-MM-DD> | skill=<fullstack-engineer/plc-electrical-engineer/pm-workflow> | mode=<mode>
  - goal:
  - changed_files:
    - 
  - artifacts:
    - 
  - impact:
  - risks:

## 7. Verification Log
- <YYYY-MM-DD>
  - verified:
    - 
  - not_verified:
$notVerifiedText
  - method:
    - 
  - blocker:
$blockerText

## 8. Handoff Notes
- <YYYY-MM-DD> | from=<skill-name>
  - current_state:
  - next_focus:
  - watchouts:
    - 
  - read_first:
    - 

## 9. Next Actions
- [P1] <next-action> | precondition=<precondition> | done_when=<done-condition>
- [P2] <next-action> | precondition=<precondition> | done_when=<done-condition>
- [P3] <next-action> | precondition=<precondition> | done_when=<done-condition>

## Reminder

$verifyHint

Next step: review this draft, then run .github/hooks/scripts/apply-handoff.ps1 to append it into PM_SESSION.
"@

Set-Content -Path $draftPath -Value $draft -Encoding UTF8
Set-Content -Path $latestPath -Value $draft -Encoding UTF8

Write-Output "[sessionEnd] Draft created: $draftPath"
Write-Output "[sessionEnd] Latest draft: $latestPath"
Write-Output "[sessionEnd] $verifyHint"
