"""TD-SW008-242: a clone that cannot read the frozen commit says so (and how to fix it); cards in sub-directories are judged the same way.

The refusal itself is unchanged -- a card the machine cannot prove old is still treated as new (fail closed).  Only the message
changes, so nobody edits a perfectly good old card because a shallow clone refused it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from auto_pm.application.core import implementation_card_tier as tier

_GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        [*_GIT, "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    return done.stdout.strip()


def _commit(root: Path, name: str) -> str:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# card\n", encoding="utf-8")
    _git(root, "add", name)
    _git(root, "commit", "-m", name)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    return tmp_path


def _freeze(monkeypatch: pytest.MonkeyPatch, commit: str) -> None:
    monkeypatch.setattr(tier, "CARD_TIER_FROZEN_COMMIT", commit)


def _findings(repo: Path, card: Path) -> list[tuple[str, str, str]]:
    return tier.tier_findings([], [], workspace_root=repo, card_file=card)


def test_a_clone_that_cannot_read_the_frozen_commit_tells_the_user_how_to_fix_it(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _commit(repo, "card.md")
    _freeze(
        monkeypatch, "0" * 40
    )  # what a shallow clone looks like: the commit is simply not there

    (finding,) = _findings(repo, repo / "card.md")

    assert "新卡头部必须写" in finding[2]  # still refused
    assert "git fetch --unshallow" in finding[2] and "00000000" in finding[2]


def test_a_readable_frozen_commit_does_not_add_the_hint(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze(monkeypatch, _commit(repo, "old.md"))
    _commit(repo, "new.md")

    (finding,) = _findings(repo, repo / "new.md")

    assert "新卡头部必须写" in finding[2] and "unshallow" not in finding[2]


def test_frozen_commit_readable_is_false_outside_a_repository_and_when_git_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert tier.frozen_commit_readable(tmp_path / "loose" / "card.md") is False

    def broken(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired("git", 60)

    monkeypatch.setattr("subprocess.run", broken)
    assert tier.frozen_commit_readable(tmp_path / "card.md") is False


def test_a_card_in_a_sub_directory_is_old_when_the_frozen_commit_has_it_and_new_otherwise(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze(monkeypatch, _commit(repo, "02_规划/sub/old.md"))
    _commit(repo, "02_规划/sub/new.md")

    assert tier.card_is_new(repo / "02_规划/sub/old.md") is False
    assert tier.card_is_new(repo / "02_规划/sub/new.md") is True
    # same file name at another depth is a different file, not the old card
    assert tier.card_is_new(repo / "other/old.md") is True


def test_a_declared_tier_is_never_hinted_about_the_clone(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _commit(repo, "card.md")
    _freeze(monkeypatch, "0" * 40)

    assert (
        tier.tier_findings(["> 档次：文档档"], [], workspace_root=repo, card_file=repo / "card.md")
        == []
    )
