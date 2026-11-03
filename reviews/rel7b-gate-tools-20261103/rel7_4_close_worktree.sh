#!/usr/bin/env bash
# M3-REL7 (card 219 V1.1) - remove this card's own candidate worktree after its branch is pushed.
# Refuses when: the worktree has uncommitted or untracked changes; its HEAD is not contained in the named remote branch; the Run is not terminal.
set -euo pipefail
export PATH="/usr/bin:/mingw64/bin:$PATH"
ROOT=/c/Users/fubai/Documents/My_Workspace; cd "$ROOT"
WT=.auto-pm/worktrees/m3-rel7b; RUN=RUN-SW008-M3-REL7-002; REMOTE="${1:?usage: $0 <remote branch, e.g. origin/claude/pr-...>}"
PY="$ROOT/.venv/Scripts/python.exe"
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ -d "$WT" ]] || { echo "WORKTREE_ALREADY_GONE $WT"; exit 0; }
case "$(pwd -P)/" in "$(cd "$WT" && pwd -P)/"*) die "the shell is inside the worktree";; esac
[[ -z "$(git -C "$WT" status --porcelain --untracked-files=all)" ]] || die "the worktree has uncommitted or untracked changes"
git fetch -q origin "${REMOTE#origin/}" || die "cannot fetch $REMOTE"
git merge-base --is-ancestor "$(git -C "$WT" rev-parse HEAD)" "$REMOTE" || die "HEAD of $WT is not in $REMOTE (push first)"
st="$("$PY" -B -c 'import sqlite3,sys;c=sqlite3.connect("file:.auto-pm/continuity.db?mode=ro",uri=True);r=c.execute("select state from run_items where run_id=?",(sys.argv[1],)).fetchone();print(r[0] if r else "NONE")' "$RUN")"
case "$st" in SUCCEEDED|CANCELLED|FAILED) ;; *) die "Run $RUN is $st, not terminal";; esac
git worktree remove "$WT"
git worktree prune
echo "WORKTREE_REMOVED $WT (HEAD in $REMOTE; Run $RUN $st)"
