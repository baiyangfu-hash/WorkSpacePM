"""Tests for encoding_check.py: each test builds a throw-away repository with one planted file.

Run with:  python -m pytest reviews/tools/test_encoding_check.py -q -p no:cacheprovider
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import encoding_check

GOOD = (
    "# 终端控制台动态测试\n"
    "Größe, Straße, Übung (Deutsch); perché, è, città, più (Italiano); élève, ça, où, « guillemets » (Français);\n"
    "日本語のテキストと 한국어 텍스트。\n"
)


def run(cwd: Path, *args: str) -> str:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "PATH": "/usr/bin:/bin", "HOME": str(cwd)}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path):
    run(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "keep.md").write_text("base\n", encoding="utf-8")
    run(tmp_path, "add", "-A")
    run(tmp_path, "commit", "-q", "-m", "base")
    base = run(tmp_path, "rev-parse", "HEAD")

    def change(files: dict[str, bytes]) -> str:
        for name, data in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        run(tmp_path, "add", "-A")
        run(tmp_path, "commit", "-q", "-m", "change")
        return run(tmp_path, "rev-parse", "HEAD")

    def audit(head: str, allowlist: dict[str, str] | None = None):
        paths = encoding_check.changed_paths(tmp_path, base, head)
        return encoding_check.check(tmp_path, head, paths, allowlist or {})

    return {"dir": tmp_path, "base": base, "change": change, "audit": audit}


def test_normal_chinese_german_italian_french_japanese_korean_pass(repo):
    head = repo["change"]({"docs/ok.md": GOOD.encode("utf-8")})
    findings, _ = repo["audit"](head)
    assert findings == []


def test_invalid_utf8_byte_fails_with_file_and_line(repo):
    data = b"line one\nline two\n\x9c\x9f broken\n"
    head = repo["change"]({"docs/bad.md": data})
    findings, _ = repo["audit"](head)
    assert [(f.path, f.line) for f in findings] == [("docs/bad.md", 3)]
    assert "UTF-8" in findings[0].reason


def test_gbk_file_fails(repo):
    head = repo["change"]({"docs/gbk.md": "需求规格说明书\n".encode("gbk")})
    findings, _ = repo["audit"](head)
    assert findings and findings[0].path == "docs/gbk.md"


@pytest.mark.parametrize("codec", ["cp1252", "latin-1"])
def test_double_encoded_chinese_fails(repo, codec):
    # UTF-8 bytes of the text read back as a single-byte charset, then saved as UTF-8 again: valid UTF-8, unreadable text
    garbled = "终端控制台动态测试".encode().decode(codec, errors="ignore")
    head = repo["change"]({"docs/moji.md": f"# title\n{garbled}\n".encode()})
    findings, _ = repo["audit"](head)
    assert [(f.path, f.line) for f in findings] == [("docs/moji.md", 2)], garbled


def test_replacement_character_and_c1_control_and_nul_fail(repo):
    head = repo["change"]({"a.md": "bad�name\n".encode(), "b.md": "x\u0085y\n".encode("utf-8"), "c.txt": b"a\x00b"})
    findings, _ = repo["audit"](head)
    assert sorted(f.path for f in findings) == ["a.md", "b.md", "c.txt"]


def test_non_text_suffix_and_deleted_files_are_ignored(repo):
    head = repo["change"]({"bin/blob.bin": b"\x9c\x9f\xff"})
    assert repo["audit"](head)[0] == []
    run(repo["dir"], "rm", "-q", "bin/blob.bin")
    run(repo["dir"], "commit", "-q", "-m", "rm")
    assert repo["audit"](run(repo["dir"], "rev-parse", "HEAD"))[0] == []


def test_allowlist_passes_only_while_the_content_is_unchanged(repo):
    head = repo["change"]({"old/legacy.md": b"legacy \x9c\x9f\n"})
    blob = run(repo["dir"], "rev-parse", f"{head}:old/legacy.md")
    findings, skipped = repo["audit"](head, {"old/legacy.md": blob})
    assert findings == [] and skipped == ["old/legacy.md"]
    changed = repo["change"]({"old/legacy.md": b"legacy \x9c\x9f edited\n"})
    findings, skipped = repo["audit"](changed, {"old/legacy.md": blob})
    assert [f.path for f in findings] == ["old/legacy.md"] and skipped == []


def test_cli_exit_codes_and_report(repo, capsys):
    good = repo["change"]({"docs/ok.md": GOOD.encode("utf-8")})
    assert encoding_check.main(["--repo", str(repo["dir"]), "--base", repo["base"], "--head", good, "--allowlist", str(repo["dir"] / "none.txt")]) == 0
    bad = repo["change"]({"docs/bad.md": b"x\n\x9c\n"})
    assert encoding_check.main(["--repo", str(repo["dir"]), "--base", good, "--head", bad, "--allowlist", str(repo["dir"] / "none.txt")]) == 1
    assert "`docs/bad.md`:2" in capsys.readouterr().out
    assert encoding_check.main(["--repo", str(repo["dir"]), "--base", "no-such-ref", "--head", bad]) == 2


def test_all_mode_scans_every_text_file(repo):
    head = repo["change"]({"docs/bad.md": b"x\x9c\n"})
    findings, _ = encoding_check.check(repo["dir"], head, encoding_check.all_paths(repo["dir"], head), {})
    assert [f.path for f in findings] == ["docs/bad.md"]


def test_the_real_allowlist_parses_and_names_existing_columns():
    entries = encoding_check.load_allowlist()
    assert entries and all(len(blob) == 40 for blob in entries.values())
