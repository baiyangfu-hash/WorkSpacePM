"""Cross-check the release records: manifest, release folders, release_meta.json, annotations and Git (TD-SW008-109/110).

Five records say which release is which, and until now nothing compared them:

* ``deployment_manifest.json``  - one entry per release (``source_commit``, sometimes ``source_tree``);
* ``releases/<id>/``            - the payload folders, each with its own ``release_meta.json``;
* ``active_release.json`` / ``previous_release.json`` - the two pointers;
* ``release_annotations.json``  - which releases may be rolled back to, and the corrections of wrong manifest values;
* Git                           - the commit the release was built from.

The rules of ``release_annotations.json`` (``rules``) were only a convention.  This module turns them into a read-only
check: it never writes a file, never touches a payload byte, and returns ``fail`` only for a contradiction that makes the
release record untrustworthy.  Records that are merely missing (a release nobody annotated yet) are warnings, so the check
does not go red on a state that is not wrong, only undocumented.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

POINTER_NAMES = ("active_release.json", "previous_release.json")
KNOWN_STATUS = frozenset({"active", "previous", "verified_historical", "archive_unverified"})
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_HEX = re.compile(r"^[0-9a-f]+$")
MIN_PREFIX = 7
GIT_TIMEOUT_SECONDS = 30


def _load(path: Path, failures: list[str]) -> dict[str, Any] | None:
    """Strict UTF-8 JSON object; a file that exists but cannot be read is a failure, a missing file is ``None``."""

    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        failures.append(f"{path.name} 读不出来（不是有效的 JSON 或含坏字节）")
        return None
    if not isinstance(data, dict):
        failures.append(f"{path.name} 的顶层不是对象")
        return None
    return data


def _text(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _same_commit(left: str, right: str) -> bool:
    """Equal, or one is a prefix (at least seven hex characters) of the other: a short SHA is the same commit as its expansion."""

    if not left or not right:
        return False
    short, long_ = sorted((left, right), key=len)
    return len(short) >= MIN_PREFIX and bool(_HEX.match(short)) and long_.startswith(short)


def _git(root: str, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", root, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _corrections(entry: dict[str, Any]) -> list[dict[str, Any]]:
    raw = entry.get("corrections")
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _check_annotation_entry(release: str, entry: dict[str, Any], failures: list[str]) -> None:
    """The annotation record must not contradict itself (the file's own rules)."""

    status = entry.get("status")
    if status not in KNOWN_STATUS:
        failures.append(
            f"release_annotations.json：{release} 的 status “{status}” 不在 {sorted(KNOWN_STATUS)} 里"
        )
    if entry.get("exact_tree_ok") is False and status != "archive_unverified":
        failures.append(
            f"release_annotations.json：{release} 的 exact_tree_ok 为 false，status 必须是 archive_unverified，现在是 {status}"
        )
    if status == "archive_unverified" and entry.get("rollback_eligible") is not False:
        failures.append(
            f"release_annotations.json：{release} 是 archive_unverified，rollback_eligible 必须是 false"
        )
    if not _FULL_SHA.match(_text(entry.get("source_commit"))):
        failures.append(
            f"release_annotations.json：{release} 的 source_commit 不是 40 位完整提交号"
        )


def _resolve_commit(
    release: str,
    source: str,
    manifest_value: str,
    entry: dict[str, Any] | None,
    failures: list[str],
) -> None:
    """Does a recorded commit value agree with the annotated full commit (or with a documented correction)?"""

    if not manifest_value:
        failures.append(f"{source}：{release} 没有 source_commit")
        return
    suffix = release.rsplit("-", 1)[-1].lower()
    if _HEX.match(suffix) and not manifest_value.startswith(suffix[:MIN_PREFIX]):
        failures.append(
            f"{source}：{release} 的 source_commit {manifest_value[:12]} 和版本号后缀 {suffix} 对不上"
        )
    if entry is None:
        return
    full = _text(entry.get("source_commit"))
    if _same_commit(manifest_value, full):
        return
    for fix in _corrections(entry):
        if (
            fix.get("field") == "source_commit"
            and _text(fix.get("manifest_value")) == manifest_value
            and _text(fix.get("correct_value")) == full
        ):
            return
    failures.append(
        f"{source}：{release} 记的 source_commit {manifest_value[:12]} 与 release_annotations.json 里的 {full[:12]} 对不上，"
        "又没有对应的 corrections 更正记录"
    )


def check_release_consistency(root: str) -> dict[str, Any]:
    """Compare the release records under ``<root>/00_Infrastructure/auto_pm``.  Read-only.

    ``status`` is ``info`` (no release records here), ``ok``, ``warn`` (undocumented but not contradictory) or ``fail``.
    """

    base = Path(root) / "00_Infrastructure" / "auto_pm"
    failures: list[str] = []
    warnings: list[str] = []
    if not (base / "deployment_manifest.json").exists():
        return {
            "status": "info",
            "failures": [],
            "warnings": ["本机没有 deployment_manifest.json（不是控制根或还没部署）"],
        }

    manifest_doc = _load(base / "deployment_manifest.json", failures)
    annotations_doc = _load(base / "release_annotations.json", failures)
    pointers = {name: _load(base / name, failures) for name in POINTER_NAMES}
    releases = manifest_doc.get("releases") if manifest_doc else None
    if not isinstance(releases, dict):
        if manifest_doc is not None:
            failures.append("deployment_manifest.json 没有 releases 对象")
        return {"status": "fail", "failures": failures, "warnings": warnings}

    annotated: dict[str, dict[str, Any]] = {}
    if annotations_doc is None:
        warnings.append("没有 release_annotations.json：没有任何版本有回退资格的书面标注")
    else:
        raw = annotations_doc.get("releases")
        for release, entry in raw.items() if isinstance(raw, dict) else []:
            if isinstance(entry, dict):
                annotated[release] = entry
                _check_annotation_entry(release, entry, failures)

    folder = base / "releases"
    on_disk = (
        {item.name for item in folder.iterdir() if item.is_dir()} if folder.is_dir() else set()
    )
    for release in sorted(on_disk - set(releases)):
        failures.append(f"releases/{release} 有载荷目录，但 deployment_manifest.json 没有登记")
    for release in sorted(set(releases) - on_disk):
        failures.append(f"deployment_manifest.json 登记了 {release}，但 releases/ 下没有它的目录")

    for release, record in sorted(releases.items()):
        if not isinstance(record, dict):
            failures.append(f"deployment_manifest.json：{release} 的记录不是对象")
            continue
        entry = annotated.get(release)
        if entry is None:
            warnings.append(
                f"{release} 没有在 release_annotations.json 里标注（回退资格没有书面依据）"
            )
        value = _text(record.get("source_commit"))
        _resolve_commit(release, "deployment_manifest.json", value, entry, failures)
        if value and not _FULL_SHA.match(value) and entry is None:
            warnings.append(f"{release} 在 manifest 里只写了短提交号 {value}，也没有标注可展开")
        meta = (
            _load(folder / release / "release_meta.json", failures) if release in on_disk else None
        )
        if meta is not None:
            meta_value = _text(meta.get("source_commit"))
            _resolve_commit(
                release, f"releases/{release}/release_meta.json", meta_value, entry, failures
            )
            if value and meta_value and not _same_commit(value, meta_value):
                failures.append(
                    f"{release}：manifest 的 source_commit {value[:12]} 与载荷里的 release_meta.json {meta_value[:12]} 不一致"
                )
            if _text(meta.get("release_id")) not in ("", release.lower()):
                failures.append(
                    f"releases/{release}/release_meta.json 的 release_id 是 {meta.get('release_id')}，与目录名不一致"
                )

    for name, pointer in pointers.items():
        if pointer is None:
            continue
        release = pointer.get("release_id")
        if not isinstance(release, str) or release not in releases:
            failures.append(f"{name} 指向 {release}，deployment_manifest.json 里没有这个版本")
            continue
        entry = annotated.get(release)
        if entry is not None and (
            entry.get("status") == "archive_unverified" or entry.get("exact_tree_ok") is False
        ):
            role = "当前版本" if name.startswith("active") else "回退目标"
            failures.append(
                f"{name}：{release} 在 release_annotations.json 里标为不可用（archive_unverified 或 exact-tree 不通过），不能作{role}"
            )

    _check_against_git(root, releases, pointers, failures, warnings)
    status = "fail" if failures else ("warn" if warnings else "ok")
    return {"status": status, "failures": failures, "warnings": warnings}


def _check_against_git(
    root: str,
    releases: dict[str, Any],
    pointers: dict[str, dict[str, Any] | None],
    failures: list[str],
    warnings: list[str],
) -> None:
    """For the two pointed releases, the commit must exist in this clone and, when the manifest records a tree, match it."""

    wanted = {p.get("release_id") for p in pointers.values() if p}
    for release in sorted(
        r for r in wanted if isinstance(r, str) and isinstance(releases.get(r), dict)
    ):
        commit = _text(releases[release].get("source_commit"))
        if not _HEX.match(commit) or len(commit) < MIN_PREFIX:
            continue
        resolved = _git(root, "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}")
        if resolved is None:
            warnings.append(
                f"{release}：本机 Git 里找不到提交 {commit[:12]}（没 fetch，或源码从未推上 origin）"
            )
            continue
        tree = _text(releases[release].get("source_tree"))
        actual = _git(root, "rev-parse", f"{commit}^{{tree}}")
        if tree and actual and tree != actual.lower():
            failures.append(
                f"{release}：manifest 记的 source_tree {tree[:12]} 与提交 {commit[:12]} 实际的树 {actual[:12]} 不一致"
            )
