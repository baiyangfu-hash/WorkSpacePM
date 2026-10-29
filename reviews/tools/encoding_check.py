"""Encoding check for text files in a change: every text file must be strict UTF-8 and free of mojibake.

Why: the readers in this repository open files with ``errors="replace"`` (DEV-ENC-001), which hides a file that is not valid
UTF-8; GitHub then shows it as Latin-1 mojibake (PR #249, roles/plc-electrical-engineer/refs/siemens-lsp-and-testing.md).
This check decodes strictly, so the first bad byte is reported with its line number.

Failures, per file (added, copied, modified or renamed in the change):
  - bytes that are not valid UTF-8 (the main criterion);
  - U+FFFD (an earlier lossy decode), C1 control characters U+0080..U+009F, a NUL byte in a text file;
  - mojibake: valid UTF-8 whose text is UTF-8 bytes read as Latin-1/cp1252 (two or more "lead + continuation" pairs on one line).
Known-bad files are listed in ``encoding_allowlist.txt`` with the blob id; the entry stops applying when the content changes.

Usage:
  python reviews/tools/encoding_check.py --base <base> --head <head> [--repo <dir>]   # files changed between the commits
  python reviews/tools/encoding_check.py --all [--head <ref>] [--repo <dir>]          # every text file at the ref
Exit code: 0 pass, 1 at least one FAIL, 2 usage or Git error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TEXT_SUFFIXES = (
    ".md", ".py", ".json", ".yml", ".yaml", ".txt", ".scl", ".st", ".toml", ".html", ".qml", ".csv",
    ".ps1", ".bat", ".mdc", ".jinja", ".sh", ".cfg", ".ini", ".xml", ".gitignore", ".gitattributes",
)  # fmt: skip
ALLOWLIST = Path(__file__).resolve().parent / "encoding_allowlist.txt"

# cp1252 renders bytes 0x80..0x9f as these characters; Latin-1 renders them as C1 controls (caught separately).
_CONTINUATION = "\u0080-¿ŒœŠšŸŽžƒˆ˜–—‘-‚“-„†-•…‰‹›€™"
# lead bytes 0xc2..0xef of 2- and 3-byte UTF-8 sequences, read as Latin-1: U+00C2..U+00EF
_MOJIBAKE_PAIR = re.compile(f"[Â-ï][{_CONTINUATION}]{{1,2}}")
_C1 = re.compile("[\u0080-\u009f]")


class GitError(RuntimeError):
    pass


@dataclass
class Finding:
    path: str
    line: int
    reason: str


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=repo, capture_output=True, check=False)
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout


def is_text_path(path: str) -> bool:
    return path.lower().endswith(TEXT_SUFFIXES)


def load_allowlist(path: Path = ALLOWLIST) -> dict[str, str]:
    """``<path>\\t<blob id>\\t<reason>`` per line; ``#`` starts a comment."""
    entries: dict[str, str] = {}
    if not path.exists():
        return entries
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            raise ValueError(f"encoding_allowlist.txt: expected '<path>\\t<blob id>\\t<reason>', got {raw!r}")
        entries[parts[0]] = parts[1]
    return entries


def line_of(data: bytes, offset: int) -> int:
    return data.count(b"\n", 0, offset) + 1


def inspect(path: str, data: bytes) -> Finding | None:
    """The first problem in one file's bytes, or None."""
    if b"\x00" in data:
        return Finding(path, line_of(data, data.index(b"\x00")), "含 NUL 字节（UTF-16 或二进制文件，不是 UTF-8 文本）")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        return Finding(path, line_of(data, error.start), f"不是合法 UTF-8（第 {error.start} 字节起，原始字节 {data[error.start:error.start + 4].hex()}）")
    for number, line in enumerate(text.split("\n"), 1):
        if "�" in line:
            return Finding(path, number, "含 U+FFFD 替换字符（曾经被有损解码过）")
        if _C1.search(line):
            return Finding(path, number, "含 C1 控制字符 U+0080～U+009F（Latin-1 误读的特征）")
        if len(_MOJIBAKE_PAIR.findall(line)) >= 2:
            return Finding(path, number, "疑似乱码：UTF-8 字节被当成 Latin-1/cp1252 读出（成串的 Ã、Â、ä、å、ç、è、é 加符号）")
    return None


def changed_paths(repo: Path, base: str, head: str) -> list[str]:
    out = git(repo, "diff", "--name-only", "--diff-filter=ACMR", "-z", base, head)
    return [p for p in out.decode("utf-8", "surrogateescape").split("\0") if p]


def all_paths(repo: Path, ref: str) -> list[str]:
    out = git(repo, "ls-tree", "-r", "--name-only", "-z", ref)
    return [p for p in out.decode("utf-8", "surrogateescape").split("\0") if p]


def check(repo: Path, head: str, paths: list[str], allowlist: dict[str, str]) -> tuple[list[Finding], list[str]]:
    """Returns (findings, allowlisted paths that were skipped)."""
    findings: list[Finding] = []
    skipped: list[str] = []
    for path in paths:
        if not is_text_path(path):
            continue
        spec = f"{head}:{path}"
        try:
            data = git(repo, "show", spec)
        except GitError:
            continue  # a submodule or a path that is not a blob at this ref
        found = inspect(path, data)
        if found is None:
            continue
        if allowlist.get(path) == git(repo, "rev-parse", spec).decode().strip():
            skipped.append(path)
            continue
        findings.append(found)
    return findings, skipped


def render(findings: list[Finding], skipped: list[str], scanned: int) -> str:
    lines = ["## 文本编码检查", "", f"- 检查了 {scanned} 个路径，登记在案的已知问题 {len(skipped)} 个（内容没变才放行）"]
    if not findings:
        lines.append("\n**结论：通过**")
        return "\n".join(lines)
    lines.append(f"\n**结论：不通过**（{len(findings)} 个文件）\n")
    for f in findings:
        lines.append(f"- `{f.path}`:{f.line}：{f.reason}")
    lines.append("\n修法：用 UTF-8 重新保存该文件（不要用 errors=replace 读写）；确属历史遗留的非 UTF-8 文件，才登记进 `reviews/tools/encoding_allowlist.txt`。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文本文件编码检查（严格 UTF-8、无乱码）")
    parser.add_argument("--base", help="变更基线提交")
    parser.add_argument("--head", default="HEAD", help="变更头提交（默认 HEAD）")
    parser.add_argument("--all", action="store_true", help="检查 --head 处的全部文本文件")
    parser.add_argument("--repo", default=".", help="Git 工作树目录")
    parser.add_argument("--allowlist", type=Path, default=ALLOWLIST)
    args = parser.parse_args(argv)
    if not args.all and not args.base:
        parser.error("需要 --base（检查两个提交之间改动的文件）或 --all")
    repo = Path(args.repo)
    try:
        paths = all_paths(repo, args.head) if args.all else changed_paths(repo, args.base, args.head)
        findings, skipped = check(repo, args.head, paths, load_allowlist(args.allowlist))
    except (GitError, ValueError) as error:
        print(f"encoding_check: {error}", file=sys.stderr)
        return 2
    print(render(findings, skipped, sum(1 for p in paths if is_text_path(p))))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
