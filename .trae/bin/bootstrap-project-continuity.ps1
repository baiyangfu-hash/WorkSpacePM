param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,

    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [Parameter(Mandatory = $true)]
    [string]$ProjectName,

    [Parameter(Mandatory = $true)]
    [ValidateSet("software", "plc", "sys")]
    [string]$ProjectType,

    [string]$Owners = "Pending",
    [string]$OneLiner = "Pending",
    [string]$Users = "Pending",
    [string]$NonGoals = "Pending",
    [string]$KeyPrinciple = "Pending",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Ensure-Directory {
    param([string]$PathValue)
    if (-not (Test-Path $PathValue)) {
        New-Item -ItemType Directory -Force -Path $PathValue | Out-Null
    }
}

function Copy-DirectoryContent {
    param([string]$Source, [string]$Destination)
    Ensure-Directory -PathValue $Destination
    Copy-Item -Path (Join-Path $Source "*") -Destination $Destination -Recurse -Force
}

function Replace-TemplateValues {
    param([string]$TemplateContent, [hashtable]$Tokens)
    $result = $TemplateContent
    foreach ($key in $Tokens.Keys) {
        $result = $result.Replace($key, $Tokens[$key])
    }
    return $result
}

function Fill-SpecSnapshot {
    param([string]$PmSessionContent, [string]$Type)

    $specRegistryPath = Join-Path $workspaceRoot "00_Obsidian_Base全局规范文件仓库\spec_registry.json"
    if (-not (Test-Path $specRegistryPath)) {
        Write-Warning "[bootstrap] Spec registry not found, skipping snapshot auto-fill"
        return $PmSessionContent
    }

    try {
        $registry = Get-Content -Path $specRegistryPath -Raw -Encoding UTF8 | ConvertFrom-Json

        $specIds = if ($Type -eq "software") {
            @("PROJ-016", "PRD-001", "DEV-031", "DEV-032")
        } elseif ($Type -eq "plc") {
            @("PROJ-016", "REQ-020", "LSP-905")
        } else {
            @("DEV-001", "DEV-002", "DEV-003", "PM-004", "PROJ-016")
        }

        $result = $PmSessionContent
        foreach ($id in $specIds) {
            if ($registry.specs.PSObject.Properties[$id]) {
                $spec = $registry.specs.$id
                $version = $spec.version
                $result = $result -replace "\| $id \| \(待填充\) \|", "| $id | $version |"
                Write-Host "[bootstrap] Spec Snapshot: $id -> $version"
            } else {
                Write-Host "[bootstrap] Spec '$id' not found in registry"
            }
        }
        return $result
    } catch {
        Write-Warning "[bootstrap] Failed to fill Spec Snapshot: $_"
        return $PmSessionContent
    }
}

$resolvedProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$templateRoot = Join-Path $workspaceRoot (Join-Path ".trae\project-bootstrap" $ProjectType)

if (-not (Test-Path $templateRoot)) {
    throw "Bootstrap template root not found: $templateRoot"
}

$pmSessionTarget = Join-Path $resolvedProjectRoot ("PM_SESSION_" + $ProjectId + ".md")
$hooksTargetRoot = Join-Path $resolvedProjectRoot ".github\hooks"
$handoffTargetRoot = Join-Path $resolvedProjectRoot ".trae\handoffs"

if ((Test-Path $pmSessionTarget) -and (-not $Force)) {
    throw "PM_SESSION already exists. Use -Force to overwrite: $pmSessionTarget"
}

$tokens = @{
    "__PROJECT_ID__" = $ProjectId
    "__PROJECT_NAME__" = $ProjectName
    "__PROJECT_ROOT__" = $resolvedProjectRoot
    "__DATE__" = (Get-Date -Format "yyyy-MM-dd")
    "__OWNERS__" = $Owners
    "__ONE_LINER__" = $OneLiner
    "__USERS__" = $Users
    "__NON_GOALS__" = $NonGoals
    "__KEY_PRINCIPLE__" = $KeyPrinciple
}

$pmSessionTemplatePath = Join-Path $templateRoot "PM_SESSION_TEMPLATE.md"
$pmSessionTemplate = Get-Content -Path $pmSessionTemplatePath -Raw -Encoding UTF8
$pmSessionContent = Replace-TemplateValues -TemplateContent $pmSessionTemplate -Tokens $tokens
$pmSessionContent = Fill-SpecSnapshot -PmSessionContent $pmSessionContent -Type $ProjectType

Ensure-Directory -PathValue $resolvedProjectRoot
Ensure-Directory -PathValue (Join-Path $resolvedProjectRoot ".github")
Ensure-Directory -PathValue (Join-Path $resolvedProjectRoot ".trae")
Ensure-Directory -PathValue $handoffTargetRoot

Set-Content -Path $pmSessionTarget -Value $pmSessionContent -Encoding UTF8
Copy-DirectoryContent -Source (Join-Path $templateRoot "hooks") -Destination $hooksTargetRoot

# ---- Project Directory Structure ----

$script:SW_DIRS = @(
    "00_项目基础信息",
    "01_项目文档\01_需求",
    "01_项目文档\02_规划过程",
    "01_项目文档\03_执行过程",
    "03_主程序\01_主程序核心代码\src",
    "03_主程序\01_主程序核心代码\tests",
    "resources\fonts",
    "resources\icons",
    "resources\styles"
)

$script:PLC_DIRS = @(
    "00_项目管理\01_立项与需求",
    "00_项目管理\04_变更管理\01_变更单\CHG-PLC",
    "00_项目管理\04_变更管理\01_变更单\CHG-ELEC",
    "00_项目管理\04_变更管理\01_变更单\CHG-DOCU",
    "00_项目管理\04_变更管理\04_变更记录",
    "01_需求与设计",
    "02_PLC程序\程序文档",
    "02_PLC程序\通用ST程序及变量表\DB1",
    "02_PLC程序\通用ST程序及变量表\OB1",
    "02_PLC程序\通用ST程序及变量表\common",
    "02_PLC程序\通用ST程序及变量表\conveyor",
    "02_PLC程序\通用ST程序及变量表\pickplace",
    "02_PLC程序\通用ST程序及变量表\feeder",
    "02_PLC程序\通用ST程序及变量表\external",
    "02_PLC程序\通用ST程序及变量表\Test",
    "02_PLC程序\通用ST程序及变量表\PRD-SRC",
    "03_HMI设计",
    "04_现场调试",
    "05_测试与验证",
    "06_文档与交付\05_交付资源",
    "06_文档与交付\操作手册",
    "07_技术支持",
    "08_备件管理",
    "09_项目总结",
    "10_知识库",
    "export"
)

$script:SYS_DIRS = @(
    "00_项目基础信息",
    "01_项目文档"
)

function New-ProjectStructure {
    param([string]$Type)
    $dirs = if ($Type -eq "software") { $script:SW_DIRS } elseif ($Type -eq "plc") { $script:PLC_DIRS } else { $script:SYS_DIRS }
    foreach ($d in $dirs) {
        Ensure-Directory -PathValue (Join-Path $resolvedProjectRoot $d)
    }
}

# ---- Skeleton File Generation ----

function New-SkeletonFiles {
    param([string]$Type)
    $today = Get-Date -Format 'yyyy-MM-dd'

    $swTree = @'
```
├── 00_项目基础信息/     # 立项表、项目章程
├── 01_项目文档/         # PRD、DES、API、测试文档
├── 03_主程序/           # 源代码、测试
├── resources/           # 字体、图标、样式
├── .github/hooks/       # 协作自动化
└── PM_SESSION_*.md      # 项目状态单一真源
```
'@

    $plcTree = @'
```
├── 00_项目管理/         # 立项、需求、变更管理
├── 01_需求与设计/       # 需求规格、方案设计
├── 02_PLC程序/          # PLC源码、程序文档
├── 03_HMI设计/          # HMI源程序与文档
├── 04_现场调试/         # 调试计划、问题跟踪
├── 05_测试与验证/       # 测试报告
├── 06_文档与交付/       # 操作手册、交付清单
├── .github/hooks/       # 协作自动化
└── PM_SESSION_*.md      # 项目状态单一真源
```
'@

    $sysTree = @'
```
├── 00_项目基础信息/     # 项目章程、基本信息
├── 01_项目文档/         # 方案、路线图、风险、准入规则
├── .github/hooks/       # 协作自动化
├── .trae/handoffs/      # 会话交接草稿
└── PM_SESSION_*.md      # 项目状态单一真源
```
'@

    $swSpecs = @'
- `PROJ-016` 通用项目结构模板
- `PRD-001` 产品需求文档模板
- `DEV-031` 通用测试规范
- `DEV-032` GUI测试方案标准
'@

    $plcSpecs = @'
- `PROJ-016` 通用项目结构模板
- `REQ-020` 通用需求分析文档模板
- PLC编程规范（参考 `0100_PLC自动化/00_通用规范/`）
'@

    $sysSpecs = @'
- `DEV-001` 通用项目名称命名规范
- `DEV-002` 通用项目工作流命名规范
- `DEV-003` 跨资源库命名统一规范
- `PM-004` PM_WORKFLOW总控Skill使用说明
- `PROJ-016` 通用项目结构模板
'@

    $typeLabel = if ($Type -eq 'software') { '软件/产品化项目' } elseif ($Type -eq 'plc') { 'PLC/电气交付项目' } else { '系统级治理项目' }
    $treeBlock = if ($Type -eq 'software') { $swTree } elseif ($Type -eq 'plc') { $plcTree } else { $sysTree }
    $specBlock = if ($Type -eq 'software') { $swSpecs } elseif ($Type -eq 'plc') { $plcSpecs } else { $sysSpecs }

    $readmeLines = @(
        "# $ProjectName",
        "",
        "- **项目编号**: $ProjectId",
        "- **项目类型**: $typeLabel",
        "- **创建日期**: $today",
        "- **负责人**: $Owners",
        "",
        "## 项目简介",
        "",
        $OneLiner,
        "",
        "## 目录结构",
        "",
        $treeBlock,
        "",
        "## 参考规范",
        "",
        $specBlock
    )
    $readmeContent = $readmeLines -join "`n"
    Set-Content -Path (Join-Path $resolvedProjectRoot "README.md") -Value $readmeContent -Encoding UTF8

    Set-Content -Path (Join-Path $resolvedProjectRoot ".gitignore") -Value ".venv/`n__pycache__/`n.pytest_cache/`n.DS_Store`n" -Encoding UTF8

    if ($Type -eq "software") {
        $pyprojectDir = Join-Path $resolvedProjectRoot "03_主程序\01_主程序核心代码"
        $pyprojectLines = @(
            "[project]",
            "name = `"$ProjectId`"",
            "version = `"0.1.0`"",
            "description = `"$OneLiner`"",
            "requires-python = `">=3.11`"",
            "",
            "[project.scripts]",
            "# TODO: 添加入口脚本",
            "",
            "[tool.pytest.ini_options]",
            "testpaths = [`"tests`"]"
        )
        $pyprojectContent = $pyprojectLines -join "`n"
        Set-Content -Path (Join-Path $pyprojectDir "pyproject.toml") -Value $pyprojectContent -Encoding UTF8

        Set-Content -Path (Join-Path $pyprojectDir "src\__init__.py") -Value "# $ProjectId`n" -Encoding UTF8
        Set-Content -Path (Join-Path $pyprojectDir "tests\__init__.py") -Value "# $ProjectId tests`n" -Encoding UTF8
        Set-Content -Path (Join-Path $resolvedProjectRoot "resources\fonts\.gitkeep") -Value "" -Encoding UTF8
        Set-Content -Path (Join-Path $resolvedProjectRoot "resources\icons\.gitkeep") -Value "" -Encoding UTF8

        # Copy document templates with placeholder replacement
        $templatesSrc = Join-Path $templateRoot "templates"
        if (Test-Path $templatesSrc) {
            $swTemplateMap = @{
                "00_立项表.md" = "00_项目基础信息\立项表.md"
                "01_PRD.md" = "01_项目文档\01_需求\PRD.md"
                "02_测试计划.md" = "01_项目文档\03_执行过程\测试计划.md"
            }
            foreach ($srcName in $swTemplateMap.Keys) {
                $srcPath = Join-Path $templatesSrc $srcName
                $dstPath = Join-Path $resolvedProjectRoot $swTemplateMap[$srcName]
                if (Test-Path $srcPath) {
                    $templateContent = Get-Content -Path $srcPath -Raw -Encoding UTF8
                    $templateContent = Replace-TemplateValues -TemplateContent $templateContent -Tokens $tokens
                    Ensure-Directory -PathValue (Split-Path $dstPath -Parent)
                    Set-Content -Path $dstPath -Value $templateContent -Encoding UTF8
                    Write-Output "[bootstrap] Template: $srcName -> $($swTemplateMap[$srcName])"
                }
            }
        }
    } elseif ($Type -eq "plc") {
        $plcDir = Join-Path $resolvedProjectRoot "02_PLC程序\通用ST程序及变量表"
        $plcConfigLines = @(
            "{",
            "  `"project_id`": `"$ProjectId`",",
            "  `"project_name`": `"$ProjectName`",",
            "  `"version`": `"0.1.0`",",
            "  `"plc_model`": `"待确认`",",
            "  `"description`": `"$OneLiner`"",
            "}"
        )
        $plcConfigContent = $plcConfigLines -join "`n"
        Set-Content -Path (Join-Path $plcDir ".plc.json") -Value $plcConfigContent -Encoding UTF8

        $ledgerDir = Join-Path $resolvedProjectRoot "00_项目管理\04_变更管理\04_变更记录"
        $ledgerLines = @(
            "# 版本变更台帐",
            "",
            "| 序号 | 变更单号 | 日期 | 变更类型 | 变更原因 | 变更内容 | 版本 | 变更人员 |",
            "|------|---------|------|----------|----------|----------|------|----------|",
            "| 1 | | $today | 初始创建 | 项目初始化 | 创建项目骨架 | V0.1.0 | $Owners |"
        )
        $ledgerContent = $ledgerLines -join "`n"
        Set-Content -Path (Join-Path $ledgerDir "00_版本变更台帐.md") -Value $ledgerContent -Encoding UTF8

        # Copy document templates with placeholder replacement
        $templatesSrc = Join-Path $templateRoot "templates"
        if (Test-Path $templatesSrc) {
            $plcTemplateMap = @{
                "00_立项表.md" = "00_项目管理\01_立项与需求\立项表.md"
                "01_需求分析.md" = "01_需求与设计\需求分析.md"
                "02_IO分配表.md" = "02_PLC程序\程序文档\IO分配表.md"
                "03_PLC设计总文档.md" = "02_PLC程序\程序文档\PLC设计总文档.md"
                "04_调试计划.md" = "04_现场调试\调试计划.md"
                "05_问题跟踪.md" = "05_测试与验证\问题跟踪.md"
            }
            foreach ($srcName in $plcTemplateMap.Keys) {
                $srcPath = Join-Path $templatesSrc $srcName
                $dstPath = Join-Path $resolvedProjectRoot $plcTemplateMap[$srcName]
                if (Test-Path $srcPath) {
                    $templateContent = Get-Content -Path $srcPath -Raw -Encoding UTF8
                    $templateContent = Replace-TemplateValues -TemplateContent $templateContent -Tokens $tokens
                    Ensure-Directory -PathValue (Split-Path $dstPath -Parent)
                    Set-Content -Path $dstPath -Value $templateContent -Encoding UTF8
                    Write-Output "[bootstrap] Template: $srcName -> $($plcTemplateMap[$srcName])"
                }
            }
        }
    } else {
        $charterPath = Join-Path $resolvedProjectRoot "00_项目基础信息\01_项目章程_PM.md"
        $charterLines = @(
            "# $ProjectName 项目章程",
            "",
            "| 字段 | 内容 |",
            "|------|------|",
            "| 项目编号 | $ProjectId |",
            "| 项目名称 | $ProjectName |",
            "| 启动日期 | $today |",
            "| 负责人 | $Owners |",
            "",
            "## 项目简介",
            "",
            $OneLiner
        )
        $charterContent = $charterLines -join "`n"
        Set-Content -Path $charterPath -Value $charterContent -Encoding UTF8
    }
}

New-ProjectStructure -Type $ProjectType
New-SkeletonFiles -Type $ProjectType

Write-Output "[bootstrap] Project continuity initialized."
Write-Output "[bootstrap] project_root: $resolvedProjectRoot"
Write-Output "[bootstrap] project_type: $ProjectType"
Write-Output "[bootstrap] pm_session: $pmSessionTarget"
Write-Output "[bootstrap] hooks: $hooksTargetRoot"
Write-Output "[bootstrap] handoffs: $handoffTargetRoot"
