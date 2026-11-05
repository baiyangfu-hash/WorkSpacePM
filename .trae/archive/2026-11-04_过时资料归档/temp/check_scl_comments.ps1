# SCL 注释合规检查脚本 (基于 904 V1.2.0)
$workspace = $PSScriptRoot + '\..\..\0100_PLC自动化'
$results = @()

$sclFiles = Get-ChildItem -Path $workspace -Recurse -Filter '*.scl' -Depth 6

Write-Host "=== SCL 注释合规检查 (904规范 V1.2.0) ===" -ForegroundColor Cyan
Write-Host "检查文件数: $($sclFiles.Count)`n" -ForegroundColor White

foreach ($file in $sclFiles) {
    $lines = Get-Content $file.FullName
    $inBlockComment = $false
    $blockCommentStartLine = 0

    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        $lineNum = $i + 1
        
        # 追踪块注释状态
        if ($line -match '\(\*' -and $line -notmatch '\*\)' -and $line -notmatch '\(\*.*\*\)') {
            $inBlockComment = $true
            $blockCommentStartLine = $lineNum
        }
        if ($line -match '\*\)' -and $inBlockComment -and $line -notmatch '\(\*') {
            $inBlockComment = $false
        }

        # Rule 1: 中文标点检测 (在注释内外都查)
        if ($line -match '[\uFF0C\uFF1A\u3002\uFF1B\u3001\uFF08\uFF09]') {
            $bad = [regex]::Matches($line, '[\uFF0C\uFF1A\u3002\uFF1B\u3001\uFF08\uFF09]') | ForEach-Object { $_.Value }
            $results += @{
                File = $file.Name
                Line = $lineNum
                Type = "R1-中文标点"
                Detail = "发现中文标点: $($bad -join ' ') - $($line.Trim().Substring(0, [Math]::Min($line.Trim().Length, 80)))"
            }
        }

        # Rule 2: 嵌套注释检测
        if ($line -match '\(\*[^)]*\(\*') {
            $results += @{
                File = $file.Name
                Line = $lineNum
                Type = "R2-嵌套注释"
                Detail = "疑似嵌套 (* ... (* ... - $($line.Trim().Substring(0, [Math]::Min($line.Trim().Length, 80)))"
            }
        }

        # Rule 3: 注释内容含 (* 或 *) 标记字符串
        if ($inBlockComment -and $lineNum -gt $blockCommentStartLine) {
            if ($line -match '\(\*' -and $line -notmatch '\*\)') {
                # 块注释内不应该再出现 (*
            }
            if ($line -match '\*\)' -and $lineNum -gt ($blockCommentStartLine + 1)) {
                $results += @{
                    File = $file.Name
                    Line = $lineNum
                    Type = "R3-注释内容含标记"
                    Detail = "块注释内(行$blockCommentStartLine起)疑似包含 *) 字符串 (如果非结束标记则为高危!)"
                }
            }
        }

        # Rule 4 (新): 变量声明行用了 (* *) 而非 // (904 V1.2.0 §2.0)
        if ($line -match '\(\*.*\*\).*:\s*(BOOL|INT|DINT|REAL|TIME|WORD|BYTE|STRING)\s*;' -or
            $line -match ':\s*(BOOL|INT|DINT|REAL|TIME|WORD|BYTE|STRING)\s*;.*\(\*.*\*\)') {
            $results += @{
                File = $file.Name
                Line = $lineNum
                Type = "R4-变量注释应用//"
                Detail = "变量声明行使用了(* *)块注释, 应改用 // : $($line.Trim().Substring(0, [Math]::Min($line.Trim().Length, 80)))"
            }
        }

        # Rule 5: 大段逻辑用 // 逐行写 (超过5行连续 // 开头的注释)
        # 这个需要上下文判断, 暂做标记
    }
}

if ($results.Count -eq 0) {
    Write-Host "✅ 所有 .scl 文件注释合规!" -ForegroundColor Green
} else {
    Write-Host "🔴 发现 $($results.Count) 处注释不合规:" -ForegroundColor Red
    Write-Host ""
    $grouped = $results | Group-Object -Property File
    foreach ($g in $grouped) {
        Write-Host "--- $($g.Name) ($($g.Count)处) ---" -ForegroundColor Yellow
        $g.Group | ForEach-Object {
            $color = if ($_.Type -eq 'R4-变量注释应用//') { 'Magenta' } else { 'White' }
            Write-Host "  L$($_.Line): [$($_.Type)] $($_.Detail)" -ForegroundColor $color
        }
        Write-Host ""
    }

    Write-Host ""
    Write-Host "=== 规则摘要 ===" -ForegroundColor Cyan
    $typeGrouped = $results | Group-Object -Property Type
    foreach ($tg in $typeGrouped) {
        Write-Host "  $($tg.Name): $($tg.Count)处" -ForegroundColor White
    }
}