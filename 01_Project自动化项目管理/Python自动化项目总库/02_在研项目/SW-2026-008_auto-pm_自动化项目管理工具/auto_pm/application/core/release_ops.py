"""Release operations in Python: build, verify, switch and rollback (D-146 card 2).

A line-by-line port of ``pmf_release_ops.sh`` (D06/D07/69b7ed6), so the cockpit can drive a release on any platform and a cloud session can
test it on a throw-away control root.  The behaviours that the script has, and that the tests here pin one by one:

* **build** writes the manifest entry *before* anything is switched (``deployment_manifest.json`` is replaced atomically); the release id is
  ``<pyproject version>-<first 7 hex of the commit>``; an existing slot or manifest entry is refused.  *New in this port:* when a build
  fails half way, the half-built release folder is removed **and the manifest is restored**, the script left both behind.
* **switch** needs ``active == old``, both releases exact-tree OK, an unused backup folder; it copies the two pointers and the manifest to
  the backup (with ``SHA256SUMS``), then writes ``previous`` first and ``active`` second, each by atomic replace.
* **rollback** restores only the two pointers from the backup, after its SHA-256 check.  The manifest is not restored (a release that was
  installed stays installed) and the database is never touched.
* After a switch or a rollback the runtime identity must name the expected release, with no fallback; the identity reader is injected
  (the real one asks the cockpit, which needs a ledger).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from auto_pm.application.core.release_deploy_check import (
    CONTAINER,
    PROJECT_DIR,
    exact_tree_ok,
    release_id_for,
)

POINTERS = ("previous_release.json", "active_release.json")  # the order they are written in
BACKUP_FILES = ("active_release.json", "previous_release.json", "deployment_manifest.json")
GIT_TIMEOUT_SECONDS = 60

Identity = Callable[[Path], dict[str, Any]]


class ReleaseOpsError(RuntimeError):
    """A release operation was refused or failed; nothing is left half done unless the message says so."""


def container_of(root: Path) -> Path:
    return Path(root) / CONTAINER


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ReleaseOpsError(f"读不出 {path.name}：{error}") from error
    if not isinstance(data, dict):
        raise ReleaseOpsError(f"{path.name} 的顶层不是对象")
    return data


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pointer_release(container: Path, name: str) -> str:
    return str(_read_json(container / name).get("release_id", ""))


def verify(root: Path, release_id: str) -> str:
    """The launcher's exact-tree check of one installed release; raises when it fails."""

    good, detail = exact_tree_ok(container_of(root), release_id)
    if not good:
        raise ReleaseOpsError(f"发布 {release_id} 逐文件校验没过：{detail}")
    return detail


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",  # lenient-decode: git 输出只用来取提交号和展示错误
        timeout=GIT_TIMEOUT_SECONDS, check=False,
    )
    if done.returncode != 0:
        raise ReleaseOpsError(f"git {' '.join(args)} 失败：{done.stderr.strip()}")
    return done.stdout.strip()


def _load_builder(repo: Path, commit: str, workdir: Path) -> Any:
    """The frozen commit's **own** ``scripts/pmf_build.py`` (D02/D04): the release is built by the code it ships with."""

    source = _git(repo, "show", f"{commit}:{PROJECT_DIR}/scripts/pmf_build.py")
    path = workdir / "pmf_build.py"
    path.write_text(source + "\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("pmf_build", path)
    if spec is None or spec.loader is None:
        raise ReleaseOpsError("加载不了冻结提交里的 pmf_build.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["pmf_build"] = module
    spec.loader.exec_module(module)
    return module


def build(root: Path, repo: Path, commit_spec: str) -> dict[str, Any]:
    """Install ``releases/<id>`` and its manifest entry from ``commit_spec``; on any failure leave no folder and the old manifest."""

    container = container_of(root)
    manifest_path = container / "deployment_manifest.json"
    commit = _git(repo, "rev-parse", f"{commit_spec}^{{commit}}")
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != "deployment_manifest.v1":
        raise ReleaseOpsError(f"部署清单的 schema_version 不是 deployment_manifest.v1：{manifest.get('schema_version')}")
    release_id = release_id_for(Path(repo), commit)
    if not release_id:
        raise ReleaseOpsError(f"读不出提交 {commit[:12]} 的 pyproject 版本，算不出发布号")
    folder = container / "releases" / release_id
    if release_id in manifest.get("releases", {}) or folder.exists():
        raise ReleaseOpsError(f"发布槽位或清单条目已存在：{release_id}")
    original_manifest = manifest_path.read_bytes()
    with tempfile.TemporaryDirectory(prefix="pmf-build-") as scratch:
        try:
            builder = _load_builder(Path(repo), commit, Path(scratch))
            result = builder.build(Path(repo), commit, PROJECT_DIR, folder, release_id)
            manifest.setdefault("releases", {})[release_id] = result.manifest_entry()
            _atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            listed = _read_json(manifest_path)["releases"][release_id]["files"]
            report = builder.verify(
                folder, listed,
                {"release_id": release_id, "source_commit": commit, "version": builder.project_version(Path(repo), commit, PROJECT_DIR),
                 "built_at": result.built_at},
            )
            if any(report[key] for key in ("missing", "orphans", "mismatch", "meta")):
                raise ReleaseOpsError(f"新发布 {release_id} 的逐文件校验没过：{report}")
            verify(root, release_id)
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            manifest_path.write_bytes(original_manifest)
            raise
        finally:
            sys.modules.pop("pmf_build", None)
    entry = json.dumps(_read_json(manifest_path)["releases"][release_id], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"release_id": release_id, "commit": commit, "files": len(listed), "entry_sha256": hashlib.sha256(entry.encode("utf-8")).hexdigest()}


def _write_pointer(container: Path, slot: str, release_id: str) -> None:
    payload = {
        "schema_version": "release_pointer.v1", "slot": slot, "release_id": release_id, "release_path": release_id,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _atomic_write(container / slot, json.dumps(payload, indent=1) + "\n")


def _identity_matches(identity: dict[str, Any], release_id: str) -> bool:
    return (
        identity.get("configured_release_id") == release_id == identity.get("effective_release_id")
        and not identity.get("runtime_fallback_reason")
    )


def switch(root: Path, new: str, old: str, backup: Path, identity: Identity) -> dict[str, Any]:
    """Back up both pointers and the manifest, then ``previous := old``, ``active := new``; refuse unless everything checks out first."""

    container = container_of(root)
    if pointer_release(container, "active_release.json") != old:
        raise ReleaseOpsError(f"当前有效版本不是 {old}，拒绝切换")
    verify(root, new)
    verify(root, old)
    backup = Path(backup)
    if backup.exists():
        raise ReleaseOpsError(f"备份目录已存在：{backup}")
    backup.mkdir(parents=True)
    for name in BACKUP_FILES:
        shutil.copy2(container / name, backup / name)
    (backup / "SHA256SUMS").write_text("".join(f"{_sha256(backup / name)}  {name}\n" for name in BACKUP_FILES), encoding="utf-8")
    _write_pointer(container, "previous_release.json", old)
    _write_pointer(container, "active_release.json", new)
    if pointer_release(container, "active_release.json") != new or pointer_release(container, "previous_release.json") != old:
        raise ReleaseOpsError("指针写入后读回来不对")
    seen = identity(Path(root))
    if not _identity_matches(seen, new):
        raise ReleaseOpsError(f"切换后运行身份不是 {new}：{seen}")
    return {"active": new, "previous": old, "backup": str(backup), "identity": seen}


def _check_backup_inside_reports(root: Path, backup: Path) -> None:
    """A rollback only trusts a backup that a deploy left under ``<control root>/.auto-pm/reports/`` (symlinks resolved), never an arbitrary folder (D-172)."""

    reports = (Path(root) / ".auto-pm" / "reports").resolve()
    try:
        inside = backup.resolve().relative_to(reports) != Path()
    except ValueError:
        inside = False
    if not inside:
        raise ReleaseOpsError(f"备份目录必须在 {reports} 之下（解析符号链接后），拒绝回退：{backup}")


def _check_backup_sums(backup: Path) -> None:
    """The backup's ``SHA256SUMS`` must list exactly the three backup files, once each, and every hash must match.

    An empty or short file used to pass (nothing to check), which let a doctored pointer through; the old script's
    ``sha256sum -c`` failed on a file with no checksum lines.
    """

    sums = backup / "SHA256SUMS"
    if not sums.is_file():
        raise ReleaseOpsError(f"备份里没有 SHA256SUMS：{backup}")
    try:
        lines = sums.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ReleaseOpsError(f"读不出备份的 SHA256SUMS：{error}") from error
    listed: dict[str, str] = {}
    for line in lines:
        digest, _, name = line.partition("  ")
        if not digest or not name or name in listed:
            raise ReleaseOpsError(f"备份的 SHA256SUMS 有坏行或重复行：{line!r}")
        listed[name] = digest
    if set(listed) != set(BACKUP_FILES):
        raise ReleaseOpsError(f"备份的 SHA256SUMS 必须正好列出 {', '.join(BACKUP_FILES)}，实际是：{', '.join(sorted(listed)) or '空'}")
    for name, digest in listed.items():
        path = backup / name
        if not path.is_file() or _sha256(path) != digest:
            raise ReleaseOpsError(f"备份文件被改过或缺失：{name}")


def rollback(root: Path, backup: Path, identity: Identity) -> dict[str, Any]:
    """Restore both pointers from ``backup`` (after its checksum check).  The manifest and the database stay as they are."""

    container = container_of(root)
    backup = Path(backup)
    _check_backup_inside_reports(root, backup)
    _check_backup_sums(backup)
    target = pointer_release(backup, "active_release.json")
    # The checksums only prove the backup agrees with itself (a hand-made folder can be perfectly consistent), so before a single pointer
    # is written both releases it names must be installed and pass the same exact-tree check the launcher runs (D-172).
    for slot in POINTERS:
        named = pointer_release(backup, slot)
        if not named:
            raise ReleaseOpsError(f"备份里的 {slot} 没写发布号，拒绝回退")
        if not (container / "releases" / named).is_dir():
            raise ReleaseOpsError(f"备份里的 {slot} 指向 {named}，但容器里没装这个发布，拒绝回退")
        verify(root, named)
    for slot in POINTERS:
        shutil.copyfile(backup / slot, container / (slot + ".tmp"))
        os.replace(container / (slot + ".tmp"), container / slot)
    seen = identity(Path(root))
    if not _identity_matches(seen, target):
        raise ReleaseOpsError(f"回退后运行身份不是 {target}：{seen}")
    return {"active": target, "identity": seen}
