"""doctor: the five release records must not contradict each other (TD-SW008-109 / TD-SW008-110)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from auto_pm.infrastructure.release_consistency import check_release_consistency

BASE = Path("00_Infrastructure") / "auto_pm"
OLD = "1.3.1-aaaaaaa"
NEW = "1.3.2-bbbbbbb"
OLD_SHA = "aaaaaaa" + "1" * 33
NEW_SHA = "bbbbbbb" + "2" * 33


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _annotation(
    commit: str, status: str, *, exact: bool = True, rollback: bool = False
) -> dict[str, Any]:
    return {
        "source_commit": commit,
        "status": status,
        "exact_tree_ok": exact,
        "rollback_eligible": rollback,
        "corrections": [],
    }


def _build(
    root: Path,
    *,
    manifest: dict[str, Any],
    annotations: dict[str, Any],
    active: str = NEW,
    previous: str = OLD,
) -> None:
    base = root / BASE
    _write(base / "deployment_manifest.json", {"releases": manifest})
    _write(base / "release_annotations.json", {"releases": annotations})
    _write(base / "active_release.json", {"release_id": active})
    _write(base / "previous_release.json", {"release_id": previous})
    for release, record in manifest.items():
        _write(
            base / "releases" / release / "release_meta.json",
            {"release_id": release, "source_commit": record["source_commit"]},
        )


@pytest.fixture
def records(tmp_path: Path) -> Path:
    _build(
        tmp_path,
        manifest={OLD: {"source_commit": OLD_SHA}, NEW: {"source_commit": NEW_SHA}},
        annotations={
            OLD: _annotation(OLD_SHA, "previous", rollback=True),
            NEW: _annotation(NEW_SHA, "active"),
        },
    )
    return tmp_path


def _reload(root: Path, name: str) -> dict[str, Any]:
    return json.loads((root / BASE / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _mutate(root: Path, name: str, change: Any) -> None:
    data = _reload(root, name)
    change(data)
    _write(root / BASE / name, data)


def _agrees(result: dict[str, Any]) -> bool:
    """No contradiction and nothing undocumented; the only tolerated note is that this fake checkout has no such commit."""

    return result["failures"] == [] and all("找不到提交" in item for item in result["warnings"])


def test_consistent_records_agree(records: Path) -> None:
    result = check_release_consistency(str(records))
    assert _agrees(result) and result["status"] in ("ok", "warn")


def test_no_manifest_is_info_not_a_failure(tmp_path: Path) -> None:
    assert check_release_consistency(str(tmp_path))["status"] == "info"


def test_an_unannotated_release_is_only_a_warning(records: Path) -> None:
    _mutate(records, "release_annotations.json", lambda d: d["releases"].pop(NEW))
    result = check_release_consistency(str(records))
    assert result["status"] == "warn" and result["failures"] == []
    assert NEW in result["warnings"][0]


def test_a_pointer_at_an_archive_unverified_release_fails(records: Path) -> None:
    def archive(d: dict[str, Any]) -> None:
        d["releases"][OLD].update(
            status="archive_unverified", exact_tree_ok=False, rollback_eligible=False
        )

    _mutate(records, "release_annotations.json", archive)
    result = check_release_consistency(str(records))
    assert result["status"] == "fail"
    assert any(
        "previous_release.json" in item and "回退目标" in item for item in result["failures"]
    )


def test_the_active_pointer_at_an_unusable_release_fails(records: Path) -> None:
    def archive(d: dict[str, Any]) -> None:
        d["releases"][NEW].update(
            status="archive_unverified", exact_tree_ok=False, rollback_eligible=False
        )

    _mutate(records, "release_annotations.json", archive)
    assert any(
        "active_release.json" in item and "当前版本" in item
        for item in check_release_consistency(str(records))["failures"]
    )


def test_a_pointer_at_a_release_missing_from_the_manifest_fails(records: Path) -> None:
    _write(records / BASE / "previous_release.json", {"release_id": "1.0.0-ccccccc"})
    assert any(
        "previous_release.json" in item and "1.0.0-ccccccc" in item
        for item in check_release_consistency(str(records))["failures"]
    )


def test_a_payload_folder_without_a_manifest_entry_fails(records: Path) -> None:
    (records / BASE / "releases" / "1.0.0-ddddddd").mkdir()
    assert any(
        "1.0.0-ddddddd" in item for item in check_release_consistency(str(records))["failures"]
    )


def test_a_manifest_entry_without_a_payload_folder_fails(records: Path) -> None:
    _mutate(
        records,
        "deployment_manifest.json",
        lambda d: d["releases"].update({"1.0.0-eeeeeee": {"source_commit": "eeeeeee" + "3" * 33}}),
    )
    assert any(
        "1.0.0-eeeeeee" in item and "没有它的目录" in item
        for item in check_release_consistency(str(records))["failures"]
    )


def test_a_short_manifest_sha_is_normalised_against_the_annotation(records: Path) -> None:
    _mutate(
        records,
        "deployment_manifest.json",
        lambda d: d["releases"][NEW].update(source_commit=NEW_SHA[:8]),
    )
    _write(
        records / BASE / "releases" / NEW / "release_meta.json",
        {"release_id": NEW, "source_commit": NEW_SHA[:8]},
    )
    assert _agrees(check_release_consistency(str(records)))


def test_a_short_manifest_sha_that_disagrees_with_the_annotation_fails(records: Path) -> None:
    other = NEW_SHA[:7] + "9" * 33
    _mutate(
        records,
        "release_annotations.json",
        lambda d: d["releases"][NEW].update(source_commit=other),
    )
    assert any("对不上" in item for item in check_release_consistency(str(records))["failures"])


def test_a_wrong_manifest_commit_needs_a_matching_correction(records: Path) -> None:
    wrong = OLD_SHA[:7] + "7" * 33
    _mutate(
        records,
        "deployment_manifest.json",
        lambda d: d["releases"][OLD].update(source_commit=wrong),
    )
    _write(
        records / BASE / "releases" / OLD / "release_meta.json",
        {"release_id": OLD, "source_commit": wrong},
    )
    assert check_release_consistency(str(records))["status"] == "fail"

    def correct(d: dict[str, Any]) -> None:
        d["releases"][OLD]["corrections"] = [
            {
                "field": "source_commit",
                "manifest_value": wrong,
                "correct_value": OLD_SHA,
                "reason": "typo",
            }
        ]

    _mutate(records, "release_annotations.json", correct)
    assert _agrees(check_release_consistency(str(records)))


def test_a_correction_for_a_different_wrong_value_does_not_cover_this_one(records: Path) -> None:
    wrong = OLD_SHA[:7] + "7" * 33
    _mutate(
        records,
        "deployment_manifest.json",
        lambda d: d["releases"][OLD].update(source_commit=wrong),
    )
    _write(
        records / BASE / "releases" / OLD / "release_meta.json",
        {"release_id": OLD, "source_commit": wrong},
    )

    def correct(d: dict[str, Any]) -> None:
        d["releases"][OLD]["corrections"] = [
            {
                "field": "source_commit",
                "manifest_value": OLD_SHA[:7] + "8" * 33,
                "correct_value": OLD_SHA,
            }
        ]

    _mutate(records, "release_annotations.json", correct)
    assert check_release_consistency(str(records))["status"] == "fail"


def test_a_payload_release_meta_that_disagrees_with_the_manifest_fails(records: Path) -> None:
    _write(
        records / BASE / "releases" / NEW / "release_meta.json",
        {"release_id": NEW, "source_commit": NEW_SHA[:7] + "5" * 33},
    )
    assert any(
        "release_meta.json" in item for item in check_release_consistency(str(records))["failures"]
    )


def test_manifest_and_payload_must_agree_even_without_an_annotation(records: Path) -> None:
    _mutate(records, "release_annotations.json", lambda d: d["releases"].pop(NEW))
    _write(
        records / BASE / "releases" / NEW / "release_meta.json",
        {"release_id": NEW, "source_commit": NEW_SHA[:7] + "5" * 33},
    )
    assert any("不一致" in item for item in check_release_consistency(str(records))["failures"])


def test_a_release_meta_with_the_wrong_release_id_fails(records: Path) -> None:
    _write(
        records / BASE / "releases" / NEW / "release_meta.json",
        {"release_id": OLD, "source_commit": NEW_SHA},
    )
    assert any("release_id" in item for item in check_release_consistency(str(records))["failures"])


def test_a_commit_that_contradicts_the_release_suffix_fails(records: Path) -> None:
    mismatch = "ccccccc" + "4" * 33
    _mutate(
        records,
        "deployment_manifest.json",
        lambda d: d["releases"][NEW].update(source_commit=mismatch),
    )
    assert any("后缀" in item for item in check_release_consistency(str(records))["failures"])


@pytest.mark.parametrize(
    ("change", "needle"),
    [
        (
            lambda e: e.update(
                status="archive_unverified", rollback_eligible=True, exact_tree_ok=False
            ),
            "rollback_eligible",
        ),
        (lambda e: e.update(exact_tree_ok=False, status="verified_historical"), "exact_tree_ok"),
        (lambda e: e.update(status="whatever"), "status"),
        (lambda e: e.update(source_commit="abc"), "40 位"),
    ],
)
def test_a_self_contradicting_annotation_fails(records: Path, change: Any, needle: str) -> None:
    _mutate(records, "release_annotations.json", lambda d: change(d["releases"]["1.3.1-aaaaaaa"]))
    assert any(needle in item for item in check_release_consistency(str(records))["failures"])


@pytest.mark.parametrize(
    "name", ["deployment_manifest.json", "release_annotations.json", "active_release.json"]
)
def test_an_unreadable_record_fails_instead_of_being_skipped(records: Path, name: str) -> None:
    (records / BASE / name).write_bytes(b"{\xff not json")
    assert check_release_consistency(str(records))["status"] == "fail"


def test_a_missing_annotation_file_is_a_warning(records: Path) -> None:
    (records / BASE / "release_annotations.json").unlink()
    result = check_release_consistency(str(records))
    assert result["status"] == "warn" and result["failures"] == []


def test_the_records_are_never_written(records: Path) -> None:
    before = {p: p.read_bytes() for p in (records / BASE).rglob("*") if p.is_file()}
    check_release_consistency(str(records))
    assert before == {p: p.read_bytes() for p in (records / BASE).rglob("*") if p.is_file()}


def _commit(repo: Path) -> tuple[str, str]:
    env = ["-c", "user.name=ci", "-c", "user.email=ci@example.invalid"]
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    (repo / "payload.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "payload.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), *env, "commit", "-q", "-m", "m"], check=True)
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.strip()
    return sha, tree


def test_git_agrees_with_the_manifest_tree(tmp_path: Path) -> None:
    sha, tree = _commit(tmp_path)
    renamed = f"1.3.2-{sha[:7]}"  # the release id suffix must belong to the commit
    _build(
        tmp_path,
        manifest={
            OLD: {"source_commit": OLD_SHA},
            renamed: {"source_commit": sha, "source_tree": tree},
        },
        annotations={
            OLD: _annotation(OLD_SHA, "previous", rollback=True),
            renamed: _annotation(sha, "active"),
        },
        active=renamed,
    )
    result = check_release_consistency(str(tmp_path))
    assert result["failures"] == [], result


def test_a_manifest_tree_that_git_contradicts_fails(tmp_path: Path) -> None:
    sha, _ = _commit(tmp_path)
    renamed = f"1.3.2-{sha[:7]}"
    _build(
        tmp_path,
        manifest={
            OLD: {"source_commit": OLD_SHA},
            renamed: {"source_commit": sha, "source_tree": "0" * 40},
        },
        annotations={
            OLD: _annotation(OLD_SHA, "previous", rollback=True),
            renamed: _annotation(sha, "active"),
        },
        active=renamed,
    )
    assert any(
        "source_tree" in item for item in check_release_consistency(str(tmp_path))["failures"]
    )


def test_a_commit_git_cannot_find_is_only_a_warning(records: Path) -> None:
    subprocess.run(["git", "-C", str(records), "init", "-q"], check=True)
    result = check_release_consistency(str(records))
    assert result["status"] == "warn" and result["failures"] == []
    assert any("找不到提交" in item for item in result["warnings"])


def test_the_real_release_records_of_this_repository_have_no_contradiction() -> None:
    root = Path(__file__).resolve()
    while root != root.parent and not (root / BASE / "deployment_manifest.json").exists():
        root = root.parent
    if not (root / BASE / "deployment_manifest.json").exists():
        pytest.skip("not inside the workspace checkout")
    assert check_release_consistency(str(root))["failures"] == []


def test_the_doctor_command_exits_nonzero_on_a_contradiction(
    records: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    # The pointer-versus-Git check has its own tests; here only the record cross-check may decide the exit code.
    monkeypatch.setattr(
        "auto_pm.ui.cli.doctor.check_release_pointers",
        lambda root: {"status": "info", "reasons": [], "ref": ""},
    )

    from auto_pm.ui.cli.doctor import doctor_command

    _mutate(
        records,
        "release_annotations.json",
        lambda d: d["releases"][OLD].update(
            status="archive_unverified", exact_tree_ok=False, rollback_eligible=False
        ),
    )
    result = CliRunner().invoke(doctor_command, ["-w", str(records)])
    assert result.exit_code == 1, result.output
    assert "发布记录自相矛盾" in result.output
