# Hooks Usage

This project enables PM_SESSION continuity automation through three hook events and one manual merge script.

## Files

- `hooks.json`
- `scripts/session-start.ps1`
- `scripts/agent-stop.ps1`
- `scripts/session-end.ps1`
- `scripts/apply-handoff.ps1`

## What Each Hook Does

### `sessionStart`

- Reads `PM_SESSION_<project-id>.md`
- Restores `current_focus`, `milestone`, latest handoff hints, and next action
- Warns if `.trae/handoffs/latest-session-handoff-draft.md` exists and may still need to be merged

### `agentStop`

- Reminds the agent to update `PM_SESSION`
- Shows whether a latest draft exists
- Reminds PLC-project verification items such as compile checks, field verification, and manual safety review

### `sessionEnd`

- Creates `.trae/handoffs/<timestamp>--session-handoff-draft.md`
- Refreshes `.trae/handoffs/latest-session-handoff-draft.md`
- Records the target `PM_SESSION` and the draft file name inside the draft

## Manual Merge Step

This automation intentionally does not write directly into `PM_SESSION` on session end.

Use:

```powershell
powershell -ExecutionPolicy Bypass -File .github/hooks/scripts/apply-handoff.ps1
```

What it does:

- reads the latest draft
- validates sections `6` to `9`
- creates a backup of `PM_SESSION`
- appends the reviewed handoff into `PM_SESSION`

## Handoff Directory

- Latest draft:
  - `.trae/handoffs/latest-session-handoff-draft.md`
- Timestamped drafts:
  - `.trae/handoffs/*.md`

## Important Boundary

- The draft is only a starting point
- Review the content before applying it
- Documentation consistency does not equal machine-ready PLC logic
- Compile checks, field verification, and safety review must still be done manually
