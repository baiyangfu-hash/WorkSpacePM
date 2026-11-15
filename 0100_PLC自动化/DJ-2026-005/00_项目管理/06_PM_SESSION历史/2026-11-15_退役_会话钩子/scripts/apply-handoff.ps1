param(
    [string]$DraftPath = ".trae/handoffs/latest-session-handoff-draft.md"
)

$ErrorActionPreference = "Stop"

function Get-MetadataValue {
    param(
        [string]$Content,
        [string]$Key
    )

    $pattern = '(?m)^- ' + [regex]::Escape($Key) + ':\s*(.+)$'
    $match = [regex]::Match($Content, $pattern)
    if ($match.Success) {
        return $match.Groups[1].Value.Trim()
    }
    return ""
}

function Get-SectionContent {
    param(
        [string]$Content,
        [string]$Header
    )

    $pattern = '(?ms)^' + [regex]::Escape($Header) + '\s*\r?\n(.*?)(?=^##\s+\d+\.|\z)'
    $match = [regex]::Match($Content, $pattern)
    if (-not $match.Success) {
        throw "Section not found: $Header"
    }

    return $match.Groups[1].Value.Trim("`r", "`n")
}

function Assert-ReadySection {
    param(
        [string]$SectionName,
        [string]$SectionContent
    )

    if ([string]::IsNullOrWhiteSpace($SectionContent)) {
        throw "Section is empty: $SectionName"
    }

    $blockedTokens = @(
        "<YYYY-MM-DD>",
        "<next-action>",
        "<precondition>",
        "<done-condition>",
        "<skill-name>",
        "<mode>"
    )

    foreach ($token in $blockedTokens) {
        if ($SectionContent.Contains($token)) {
            throw "Section contains unresolved placeholder '$token': $SectionName"
        }
    }
}

function Append-SectionEntry {
    param(
        [string]$Content,
        [string]$Header,
        [string]$Entry
    )

    $pattern = '(?ms)^' + [regex]::Escape($Header) + '\s*\r?\n(.*?)(?=^##\s+\d+\.|\z)'
    $match = [regex]::Match($Content, $pattern)
    if (-not $match.Success) {
        throw "Target PM_SESSION section not found: $Header"
    }

    $bodyIndex = $match.Groups[1].Index
    $bodyLength = $match.Groups[1].Length
    $before = $Content.Substring(0, $bodyIndex)
    $body = $match.Groups[1].Value.TrimEnd("`r", "`n")
    $after = $Content.Substring($bodyIndex + $bodyLength)

    $newBody = if ([string]::IsNullOrWhiteSpace($body)) {
        $Entry.Trim()
    }
    else {
        $body + "`r`n" + $Entry.Trim()
    }

    return $before + $newBody + "`r`n" + $after.TrimStart("`r", "`n")
}

$repoRoot = (Resolve-Path ".").Path
$resolvedDraftPath = if ([System.IO.Path]::IsPathRooted($DraftPath)) { $DraftPath } else { Join-Path $repoRoot $DraftPath }

if (-not (Test-Path $resolvedDraftPath)) {
    throw "Draft not found: $resolvedDraftPath"
}

$draftContent = Get-Content -Path $resolvedDraftPath -Raw -Encoding UTF8
$pmSessionName = Get-MetadataValue -Content $draftContent -Key "pm_session"
$draftSource = Get-MetadataValue -Content $draftContent -Key "draft_source"

if ([string]::IsNullOrWhiteSpace($pmSessionName)) {
    throw "Draft metadata 'pm_session' is missing."
}

if ([string]::IsNullOrWhiteSpace($draftSource)) {
    $draftSource = [System.IO.Path]::GetFileName($resolvedDraftPath)
}

$pmSessionPath = Join-Path $repoRoot $pmSessionName
if (-not (Test-Path $pmSessionPath)) {
    throw "PM_SESSION target not found: $pmSessionPath"
}

$pmSessionContent = Get-Content -Path $pmSessionPath -Raw -Encoding UTF8
if ($pmSessionContent.Contains("draft_source: $draftSource")) {
    throw "Draft already merged into PM_SESSION: $draftSource"
}

$implementationBlock = Get-SectionContent -Content $draftContent -Header "## 6. Implementation Log"
$verificationBlock = Get-SectionContent -Content $draftContent -Header "## 7. Verification Log"
$handoffBlock = Get-SectionContent -Content $draftContent -Header "## 8. Handoff Notes"
$nextActionBlock = Get-SectionContent -Content $draftContent -Header "## 9. Next Actions"

Assert-ReadySection -SectionName "Implementation Log" -SectionContent $implementationBlock
Assert-ReadySection -SectionName "Verification Log" -SectionContent $verificationBlock
Assert-ReadySection -SectionName "Handoff Notes" -SectionContent $handoffBlock
Assert-ReadySection -SectionName "Next Actions" -SectionContent $nextActionBlock

if (-not $implementationBlock.Contains("draft_source: $draftSource")) {
    $implementationBlock = $implementationBlock.TrimEnd("`r", "`n") + "`r`n  - draft_source: $draftSource"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path ([System.IO.Path]::GetDirectoryName($pmSessionPath)) (([System.IO.Path]::GetFileNameWithoutExtension($pmSessionPath)) + ".bak-$timestamp.md")
Copy-Item -Path $pmSessionPath -Destination $backupPath -Force

$updatedContent = $pmSessionContent
$updatedContent = Append-SectionEntry -Content $updatedContent -Header "## 6. Implementation Log" -Entry $implementationBlock
$updatedContent = Append-SectionEntry -Content $updatedContent -Header "## 7. Verification Log" -Entry $verificationBlock
$updatedContent = Append-SectionEntry -Content $updatedContent -Header "## 8. Handoff Notes" -Entry $handoffBlock
$updatedContent = Append-SectionEntry -Content $updatedContent -Header "## 9. Next Actions" -Entry $nextActionBlock

Set-Content -Path $pmSessionPath -Value $updatedContent -Encoding UTF8

Write-Output "[applyHandoff] Draft merged into PM_SESSION."
Write-Output "[applyHandoff] pm_session: $pmSessionPath"
Write-Output "[applyHandoff] backup: $backupPath"
Write-Output "[applyHandoff] draft: $resolvedDraftPath"
