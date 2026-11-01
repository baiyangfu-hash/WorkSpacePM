param(
    [string]$InputFile,
    [string]$OutputFile,
    [ValidateSet("png","svg","pdf")][string]$Format = "png",
    [int]$Width = 2400,
    [double]$Scale = 2.0
)

$ErrorActionPreference = "Stop"

# 不写死用户名：从当前用户目录推出；需要时可用环境变量 MERMAID_MMDC 指定 mmdc.cmd
$TRAE_NODE = Join-Path $env:USERPROFILE ".trae-cn\binaries\node"
$NODE = Join-Path $TRAE_NODE "versions\24.13.0\node.exe"
if ($env:MERMAID_MMDC) { $MMDC = $env:MERMAID_MMDC } else { $MMDC = Join-Path $TRAE_NODE "global\mmdc.cmd" }

if (-not (Test-Path $MMDC)) {
    Write-Host "[ERROR] mmdc not found. Run install first." -ForegroundColor Red
    exit 1
}

if (-not $InputFile) {
    Write-Host ""
    Write-Host "=== Mermaid 一键导出工具 ===" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "用法:" -ForegroundColor Yellow
    Write-Host "  .\export-mermaid.ps1 -InputFile <文件.mmd>" -ForegroundColor White
    Write-Host "  .\export-mermaid.ps1 -InputFile <文件.mmd> -Format svg" -ForegroundColor White
    Write-Host "  .\export-mermaid.ps1 -InputFile <文件.mmd> -Width 3000 -Scale 3" -ForegroundColor White
    Write-Host ""
    Write-Host "批量导出当前目录所有 .mmd:" -ForegroundColor Yellow
    Write-Host "  Get-ChildItem *.mmd | ForEach-Object { .\export-mermaid.ps1 `\$_.FullName }" -ForegroundColor White
    Write-Host ""
    exit 0
}

if (-not (Test-Path $InputFile)) {
    Write-Host "[ERROR] File not found: $InputFile" -ForegroundColor Red
    exit 1
}

if (-not $OutputFile) {
    $base = [System.IO.Path]::GetFileNameWithoutExtension($InputFile)
    $dir = Split-Path $InputFile
    $OutputFile = Join-Path $dir "$base.$Format"
}

Write-Host "[INFO] Input:  $InputFile" -ForegroundColor Gray
Write-Host "[INFO] Output: $OutputFile ($Format, ${Width}px, ${Scale}x)" -ForegroundColor Gray

& $MMDC -i $InputFile -o $OutputFile -w $Width -b white -s $Scale 2>&1 | ForEach-Object { Write-Host $_ }

if (Test-Path $OutputFile) {
    $size = [math]::Round((Get-Item $OutputFile).Length / 1KB, 1)
    Write-Host "[OK] Exported: $OutputFile ($size KB)" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Export failed" -ForegroundColor Red
    exit 1
}
