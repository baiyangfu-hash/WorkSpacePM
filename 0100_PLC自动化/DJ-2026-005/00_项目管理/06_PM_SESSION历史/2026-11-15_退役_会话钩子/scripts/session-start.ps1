$ErrorActionPreference = "Stop"

function Get-SectionLines {
    param(
        [string[]]$Lines,
        [string]$Heading
    )

    $start = -1
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i].Trim() -eq $Heading) {
            $start = $i
            break
        }
    }

    if ($start -lt 0) {
        return @()
    }

    $result = @()
    for ($i = $start + 1; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match '^##\s+') {
            break
        }
        $result += $Lines[$i]
    }
    return $result
}

function Find-Value {
    param(
        [string[]]$Lines,
        [string]$Prefix
    )

    foreach ($line in $Lines) {
        $trimmed = $line.Trim()
        if ($trimmed.StartsWith($Prefix)) {
            return $trimmed.Substring($Prefix.Length).Trim()
        }
    }
    return ""
}

function Find-RegexValue {
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

function Find-FirstBullet {
    param([string[]]$Lines)

    foreach ($line in $Lines) {
        $trimmed = $line.Trim()
        if ($trimmed.StartsWith("- ")) {
            return $trimmed.Substring(2).Trim()
        }
    }
    return ""
}

$repoRoot = (Resolve-Path ".").Path
$pmSession = Get-ChildItem -Path $repoRoot -Filter "PM_SESSION_*.md" -File | Select-Object -First 1
$handoffDir = Join-Path $repoRoot ".trae\handoffs"
$latestDraft = Join-Path $handoffDir "latest-session-handoff-draft.md"

if (-not $pmSession) {
    @{ additionalContext = "PM_SESSION not found. Create PM_SESSION_<project-id>.md before starting work." } |
        ConvertTo-Json -Compress
    exit 0
}

$rawContent = Get-Content -Path $pmSession.FullName -Raw -Encoding UTF8
$lines = Get-Content -Path $pmSession.FullName -Encoding UTF8
$focusSection = Get-SectionLines -Lines $lines -Heading "## 2. Current Focus（当前焦点）"
$handoffSection = Get-SectionLines -Lines $lines -Heading "## 8. Handoff Notes"
$nextActionSection = Get-SectionLines -Lines $lines -Heading "## 9. Next Actions"

$currentFocus = Find-RegexValue -Content $rawContent -Pattern '^- current_focus:\s*(.+)$'
$milestone = Find-RegexValue -Content $rawContent -Pattern '^- milestone:\s*(.+)$'
$currentState = Find-Value -Lines $handoffSection -Prefix "- current_state:"
$nextFocus = Find-Value -Lines $handoffSection -Prefix "- next_focus:"
$firstAction = Find-FirstBullet -Lines $nextActionSection

$context = 'PM_SESSION continuity mode is enabled.' + "`n" + ('PM_SESSION: ' + $pmSession.Name) + "`n" + ('current_focus: ' + $currentFocus) + "`n" + ('milestone: ' + $milestone) + "`n" + ('handoff.current_state: ' + $currentState) + "`n" + ('handoff.next_focus: ' + $nextFocus) + "`n" + ('next_action: ' + $firstAction) + "`n" + 'Before finishing, update implementation_log / verification_log / handoff_notes / next_actions.'

if (Test-Path $latestDraft) {
    $context = $context + "`n" + ('pending_draft: ' + $latestDraft) + "`n" + 'Check whether the latest handoff draft should be merged by running .github/hooks/scripts/apply-handoff.ps1 before continuing.'
}

@{ additionalContext = $context } | ConvertTo-Json -Compress
