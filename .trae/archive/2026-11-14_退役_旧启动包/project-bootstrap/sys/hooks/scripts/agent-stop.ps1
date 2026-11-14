$ErrorActionPreference = "Stop"

$projectType = if ($env:PROJECT_TYPE) { $env:PROJECT_TYPE } else { "generic" }
$verifyHint = if ($env:VERIFY_HINT) { $env:VERIFY_HINT } else { "Update PM_SESSION before ending the session." }
$repoRoot = (Resolve-Path ".").Path
$pmSession = Get-ChildItem -Path $repoRoot -Filter "PM_SESSION_*.md" -File | Select-Object -First 1
$latestDraft = Join-Path $repoRoot ".trae\handoffs\latest-session-handoff-draft.md"
$draftStatus = if (Test-Path $latestDraft) { "draft_exists" } else { "draft_missing" }

$message = "[agentStop] project_type: $projectType" + "`n" + "[agentStop] PM_SESSION: $($pmSession.Name)" + "`n" + "[agentStop] handoff_status: $draftStatus" + "`n" + "[agentStop] If a latest draft exists, review it and run .github/hooks/scripts/apply-handoff.ps1 when the draft is ready to merge." + "`n" + "[agentStop] $verifyHint"

Write-Output $message
