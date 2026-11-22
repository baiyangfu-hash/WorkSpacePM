"""CHG-SCPT-2026-709: the intake card the cockpit writes for the release being deployed (``release_card``).

``release ship`` used to give every deploy the repository card 274, whose path table only lists ``releases/1.3.3-368c1af``; any other
release's Work was outside its card.  These tests pin that the generated card covers what the deploy writes for *this* release, that its
payload list is exactly what the commit's own builder writes, that it passes the real precheck (``test_release_ledger_real_cli.py`` drives
it through ``work create`` too), and that an existing card is reused, never overwritten.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core import release_card, release_deploy
from auto_pm.application.core import release_deploy_check as check
from auto_pm.application.core import release_ops as ops
from auto_pm.application.core import release_wiring as wiring
from auto_pm.application.core.release_deploy import DeployError
from tests.core.test_release_ledger_real_cli import (
    COMMIT,
    CONTAINER,
    OLD,
    PAYLOAD,
    POINTERS,
    RELEASE,
    _control_root,
    _runner,
)


def _rows(card: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in card.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 3 and cells[0].startswith("`"):
            rows[cells[0].strip("`")] = cells[1]
    return rows


def test_the_card_covers_the_three_pointers_the_release_folder_and_every_payload_file_of_this_release(tmp_path: Path) -> None:
    card = _control_root(tmp_path)
    rows = _rows(card)

    assert {f"{CONTAINER}/{name}": "存在" for name in POINTERS}.items() <= rows.items()
    folder = f"{CONTAINER}/releases/{RELEASE}"
    assert rows[folder] == "计划新增", "the Work's scope names the folder as one path; the card must list that path itself"
    assert {f"{folder}/{name}" for name in PAYLOAD} == {path for path in rows if path.startswith(f"{folder}/")}
    assert all(rows[f"{folder}/{name}"] == "计划新增" for name in PAYLOAD)
    assert len(rows) == len(POINTERS) + 1 + len(PAYLOAD)
    head = _git_head(tmp_path)
    text = card.read_text(encoding="utf-8")
    assert f"> 隔离基线：`{head}`" in text and "> 路径根：`.`" in text and "> 档次：核心档" in text and "> 安全回路: 否" in text
    assert "368c1af" not in text and RELEASE in text and COMMIT in text


def test_the_generated_card_passes_the_real_precheck_command(tmp_path: Path) -> None:
    card = _control_root(tmp_path)

    code, output = _runner(tmp_path)(["implementation-card", "precheck", "--card-file", str(card)])

    assert code == 0, output


def test_a_card_already_there_is_reused_byte_for_byte_and_a_foreign_file_is_never_overwritten(tmp_path: Path) -> None:
    card = _control_root(tmp_path)
    before = card.read_bytes()
    _commit_something(tmp_path)  # HEAD moves: a regenerated card would carry another baseline

    again = release_card.ensure_card(tmp_path, release_id=RELEASE, old_release=OLD, commit=COMMIT, files=("other.py",))

    assert again == card and card.read_bytes() == before
    card.write_text("# something else\n", encoding="utf-8")
    with pytest.raises(release_card.ReleaseCardError, match="没有覆盖"):
        release_card.ensure_card(tmp_path, release_id=RELEASE, old_release=OLD, commit=COMMIT, files=PAYLOAD)
    assert card.read_text(encoding="utf-8") == "# something else\n"


def test_an_empty_payload_is_refused_and_writes_no_card(tmp_path: Path) -> None:
    with pytest.raises(release_card.ReleaseCardError, match="没有载荷文件"):
        release_card.ensure_card(tmp_path, release_id=RELEASE, old_release=OLD, commit=COMMIT, files=())
    assert not release_card.card_path(tmp_path, RELEASE).exists()


def test_the_payload_list_is_exactly_what_the_commits_own_builder_writes(tmp_path: Path) -> None:
    """Against this repository's HEAD: the files ``payload_files`` lists are the files ``build`` writes, no more, no fewer."""

    repo = Path(_git(Path(__file__).parent, "rev-parse", "--show-toplevel"))
    commit = _git(repo, "rev-parse", "HEAD")

    listed = release_card.payload_files(repo, commit)

    builder = ops._load_builder(repo, commit, tmp_path)  # noqa: SLF001 - the builder ``build`` itself uses
    try:
        built = builder.build(repo, commit, check.PROJECT_DIR, tmp_path / "out", "9.9.9-test000")
    finally:
        sys.modules.pop("pmf_build", None)
    assert listed == sorted(built.files), "the card would cover a different set of files than the deploy writes"
    assert "release_meta.json" in listed and any(name.startswith("auto_pm/") for name in listed)


def test_an_unknown_commit_stops_the_card_and_nothing_is_written(tmp_path: Path) -> None:
    _control_root(tmp_path)
    with pytest.raises(release_card.ReleaseCardError, match="列不出提交"):
        release_card.ensure_card(tmp_path, release_id="1.3.3-fffffff", old_release=OLD, commit="f" * 40)
    assert not release_card.card_path(tmp_path, "1.3.3-fffffff").exists()


def test_a_real_deploy_without_a_card_file_that_cannot_write_the_card_stops_before_the_books_with_pointers_unmoved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _control_root(tmp_path)
    pointers = {name: (tmp_path / CONTAINER / name).read_bytes() for name in POINTERS}
    report = check.Preflight(release_id="1.3.3-fffffff", commit="f" * 40, active_release=OLD)
    monkeypatch.setattr(wiring, "hook_dry_run", lambda _root: (True, "hook covered in test_release_wiring"))

    with pytest.raises(DeployError, match="入账卡没生成") as caught:
        wiring.real_deploy(tmp_path, report, approver="baiyang", confirm_ref="user-confirmation:2026-11-17T03:26:28Z", card_file=None,
                           drill_script=tmp_path / "drill.py")

    assert caught.value.pointers_moved is False and caught.value.rolled_back is False  # the CLI exits 2: nothing deployed
    assert {name: (tmp_path / CONTAINER / name).read_bytes() for name in POINTERS} == pointers
    assert not (tmp_path / ".auto-pm" / "decisions").exists() or not any((tmp_path / ".auto-pm" / "decisions").iterdir())
    assert json.loads((tmp_path / CONTAINER / "active_release.json").read_text(encoding="utf-8"))["release_id"] == OLD


def test_a_real_deploy_without_a_card_file_books_with_the_card_it_generated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Audit M16: the generated card must reach the plan (the books) and the post-switch card precheck, not just the disk."""

    _control_root(tmp_path)  # writes the 1.3.3-dad7036 card; this deploy is another release, so its card is generated here
    release = "1.3.3-abcdef0"
    monkeypatch.setattr(release_card, "payload_files", lambda _repo, _commit: list(PAYLOAD))
    monkeypatch.setattr(wiring, "hook_dry_run", lambda _root: (True, "hook covered in test_release_wiring"))
    seen: dict[str, Any] = {}

    def capture(plan: Any, **kwargs: Any) -> Any:
        seen["plan"], seen["checks"] = plan, kwargs["checks"]
        raise DeployError("captured", pointers_moved=False)

    monkeypatch.setattr(release_deploy, "deploy", capture)  # release_wiring calls it as rd.deploy
    drill = tmp_path / "drill.py"
    drill.write_text("print('drill')\n", encoding="utf-8")

    report = check.Preflight(release_id=release, commit="abcdef0" + "1" * 33, active_release=OLD)
    with pytest.raises(DeployError, match="captured"):
        wiring.real_deploy(tmp_path, report, approver="baiyang",
                           confirm_ref="user-confirmation:2026-11-17T03:26:28Z", card_file=None, drill_script=drill)

    card = release_card.card_path(tmp_path, release)
    assert card.is_file() and seen["plan"].card_file == card
    assert f"{CONTAINER}/releases/{release}/release_meta.json" in _rows(card)


def test_a_full_size_card_from_this_repositorys_payload_passes_the_real_precheck(tmp_path: Path) -> None:
    """The card as the deploy writes it, with every payload file of this repository's HEAD (hundreds of rows), not a handful."""

    repo = Path(_git(Path(__file__).parent, "rev-parse", "--show-toplevel"))
    files = release_card.payload_files(repo, _git(repo, "rev-parse", "HEAD"))
    _control_root(tmp_path)
    card = release_card.ensure_card(tmp_path, release_id="1.3.3-abcdef0", old_release=OLD, commit="abcdef0" + "1" * 33, files=files)

    code, output = _runner(tmp_path)(["implementation-card", "precheck", "--card-file", str(card)])

    assert len(files) > 100 and len(_rows(card)) == len(POINTERS) + 1 + len(files)
    assert code == 0, output[-2000:]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout.strip()


def _git_head(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD")


def _commit_something(root: Path) -> None:
    (root / "later.txt").write_text("later\n", encoding="utf-8")
    _git(root, "add", "later.txt")
    _git(root, "-c", "user.name=Deploy Test", "-c", "user.email=deploy@example.invalid", "commit", "-q", "-m", "later")
