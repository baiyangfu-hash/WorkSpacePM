"""Find newly added files that the repository's own ignore rules say must not be tracked (TD-SW008-115).

An ignore rule only stops *untracked* files, so a file added with ``git add -f`` (or in a PR whose author never saw
the rule) walks straight in.  The commit hook and pr-gate both call :func:`ignored_among` on the paths a change
*adds*; files that are already tracked are never looked at here, so the existing backlog is untouched.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from auto_pm.infrastructure.git_timeout import run_git_bounded_text


class IgnoreScanError(RuntimeError):
    """``git check-ignore`` itself failed; callers must treat that as a refusal, not as "nothing found"."""


@dataclass(frozen=True)
class IgnoredFile:
    path: str
    source: str  # ".gitignore:129"
    pattern: str


def ignored_among(repo: Path, paths: Sequence[str]) -> list[IgnoredFile]:
    """The paths among ``paths`` that an ignore rule matches, whether or not they are in the index."""

    if not paths:
        return []
    result = run_git_bounded_text(
        ["git", "check-ignore", "--no-index", "-v", "-n", "-z", "--stdin"],
        default_timeout=120.0,
        error_cls=IgnoreScanError,
        where=repo,
        cwd=str(repo),
        input="\0".join(paths) + "\0",
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise IgnoreScanError(f"git check-ignore 失败（exit {result.returncode}）：{result.stderr.strip()}")
    fields = result.stdout.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    if len(fields) % 4 != 0:
        raise IgnoreScanError("git check-ignore 输出格式不完整")
    hits: list[IgnoredFile] = []
    for index in range(0, len(fields), 4):
        source, line, pattern, path = fields[index : index + 4]
        # An empty pattern means "no rule"; a leading "!" is a re-include rule, i.e. the file is allowed.
        if pattern and not pattern.startswith("!"):
            hits.append(IgnoredFile(path, f"{source}:{line}", pattern))
    return hits
