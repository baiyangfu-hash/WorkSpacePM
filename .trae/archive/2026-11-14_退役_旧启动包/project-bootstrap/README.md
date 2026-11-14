# Project Bootstrap

This directory stores reusable continuity assets for new projects.

## Available Types

- `software`
- `plc`
- `sys`

Each type provides:

- `PM_SESSION_TEMPLATE.md`
- `hooks/hooks.json`
- `hooks/README.md`
- `hooks/scripts/session-start.ps1`
- `hooks/scripts/agent-stop.ps1`
- `hooks/scripts/session-end.ps1`
- `hooks/scripts/apply-handoff.ps1`

## Intended Flow

Use the workspace bootstrap script:

```powershell
powershell -ExecutionPolicy Bypass -File .trae/bin/bootstrap-project-continuity.ps1 -ProjectRoot "<project-root>" -ProjectId "<project-id>" -ProjectName "<project-name>" -ProjectType <software|plc|sys>
```

The bootstrap script will:

- create `PM_SESSION_<project-id>.md`
- create `.trae/handoffs/`
- install `.github/hooks/`
- keep the project aligned with the continuity workflow used by existing projects

## Notes

- `software` is based on the structure used by `SW-2026-005_PLC项目管理工具`
- `plc` is based on the structure used by `DJ-2026-005`
- `sys` is for system-level governance projects (cross-domain, workspace-wide)
- Review the generated PM_SESSION content after bootstrap and fill the placeholders before active development starts
