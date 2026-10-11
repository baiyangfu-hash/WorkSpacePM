"""Scan every line ADDED by the commits in <base_ref>..HEAD for provider-shaped secrets.

usage: secret_scan.py <base_ref>

Walks the commits one by one (`git log -p`), so a secret that was added and removed again
inside the range is still found.  Prints only "[pattern] path @commit xN"; values are never
printed or logged.  Strict provider patterns only: generic "password = ..." assignments are
not scanned here because they produce false positives in lease-token code.
"""
from __future__ import annotations

import re
import subprocess
import sys

PATTERNS = {
    "github-token": re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}"),
    "aws-access-key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private-key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "url-credentials": re.compile(r"https?://[^/@\s:]+:[^/@\s]+@"),
}


def main(base: str) -> int:
    out = subprocess.run(
        ["git", "-c", "core.quotepath=off", "log", "-p", "--unified=0", "--no-color",
         "--format=@@commit %h", f"{base}..HEAD"],
        capture_output=True, encoding="utf-8", errors="replace", check=True,
    ).stdout
    hits: dict[tuple[str, str, str], int] = {}
    commit, path = "?", "?"
    for line in out.splitlines():
        if line.startswith("@@commit "):
            commit = line[9:]
        elif line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+") and not line.startswith("+++"):
            for name, pat in PATTERNS.items():
                if pat.search(line):
                    key = (name, path, commit)
                    hits[key] = hits.get(key, 0) + 1
    for (name, path, commit), n in sorted(hits.items()):
        print(f"SECRET-SHAPED [{name}] {path} @{commit} x{n}")
    print(f"secret scan: {len(hits)} location(s) flagged in {base}..HEAD")
    return 1 if hits else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
