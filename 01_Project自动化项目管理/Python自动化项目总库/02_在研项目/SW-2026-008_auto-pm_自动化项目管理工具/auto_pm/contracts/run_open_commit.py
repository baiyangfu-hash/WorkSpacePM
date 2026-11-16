"""The one sentence said when someone commits in a station while its Run is open (G 工位止血 3, card 280).

Both the commit hook (which refuses the commit) and ``pm verify`` (which finds the HEAD moved after a commit got through, e.g.
with ``--no-verify``) say exactly this, so a person or an agent reads the same way out in both places: take the commit back
into the index with ``git reset --soft <the commit the Run recorded>`` and hand in again.
"""

from __future__ import annotations


def run_open_commit_hint(run_head: str) -> str:
    """``Run 开着，收口前不要提交；已提交的用 git reset --soft <Run 记的提交号> 撤回后再交卷``, with the Run's commit filled in."""

    return f"Run 开着，收口前不要提交；已提交的用 git reset --soft {run_head or '<Run 记的提交号>'} 撤回后再交卷"
