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
    - 
  - method:
    - 
  - blocker:
    - 

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
