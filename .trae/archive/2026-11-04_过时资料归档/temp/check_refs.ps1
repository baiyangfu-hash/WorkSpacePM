$workspace = $PSScriptRoot + '\..\..'
$issues = @()

Write-Host "=== 引用断裂全面检测 ===" -ForegroundColor Cyan

# 1. 检查所有 PM_SESSION 中的 artifact 路径引用
$pmFiles = Get-ChildItem -Path $workspace -Recurse -Filter 'PM_SESSION_*.md' -Depth 3
foreach ($pm in $pmFiles) {
    $content = Get-Content $pm.FullName -Raw
    $dir = $pm.DirectoryName

    # 提取形如 "path/to/file.ext" 的路径引用
    $pathPattern = '(\S+/\S+\.\w{2,5})'
    $matches = [regex]::Matches($content, $pathPattern)
    foreach ($m in $matches) {
        $ref = $m.Groups[1].Value.Trim()
        # 跳过 URL
        if ($ref -match '^https?://') { continue }
        $absPath = Join-Path $dir $ref
        if (-not (Test-Path $absPath)) {
            $issues += @{Type="PM_SESSION"; File=$pm.Name; Path=$ref; Reason="文件不存在"}
        }
    }
}

# 2. 检查 905 规范中的交叉引用
$spec905 = Get-ChildItem -Path $workspace -Recurse -Filter '*905*SCL*编程*.md' -Depth 4 | Select-Object -First 1
if ($spec905) {
    $content905 = Get-Content $spec905.FullName -Raw
    $refs905 = [regex]::Matches($content905, '\[([^\]]+)\]\(([^)]+)\)')
    foreach ($r in $refs905) {
        $linkPath = $r.Groups[2].Value
        if ($linkPath -notmatch '^(http|#)') {
            $absLink = Join-Path $spec905.DirectoryName $linkPath
            if (-not (Test-Path $absLink)) {
                $issues += @{Type="905交叉引用"; File=$spec905.Name; Path=$linkPath; Reason="目标不存在"}
            }
        }
    }
}

# 3. 检查 spec_registry.json 中 canonical_path 对应真实文件
$regPath = Join-Path $workspace '00_Obsidian_Base全局规范文件仓库\spec_registry.json'
$registry = Get-Content $regPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($prop in $registry.PSObject.Properties) {
    $cp = $prop.Value.canonical_path
    if ($cp) {
        $absPath = Join-Path $workspace $cp
        if (-not (Test-Path $absPath)) {
            $issues += @{Type="spec_registry"; File=$prop.Name; Path=$cp; Reason="canonical_path文件不存在"}
        }
    }
}

if ($issues.Count -eq 0) {
    Write-Host "✅ 未发现引用断裂" -ForegroundColor Green
} else {
    Write-Host "🔴 发现 $($issues.Count) 处引用断裂:" -ForegroundColor Red
    $issues | ForEach-Object {
        Write-Host "  [$($_.Type)] $($_.File) -> $($_.Path) : $($_.Reason)" -ForegroundColor Yellow
    }
}