"""The intake card of one release, written by the cockpit at the moment of a real deploy (CHG-SCPT-2026-709).

``release deploy`` books the release as a write Work, and a write Work needs an implementation card whose path table covers what the
deploy writes: the three pointer files (``deployment_manifest.json`` is the manifest) and everything under ``releases/<release id>/``.
``release ship`` used to hand every deploy the same repository card (``274_RELEASE-368c1af入账卡_PM.md``), which only lists the files of
``releases/1.3.3-368c1af`` and so could never cover the next release.  Here the card is generated for the release being deployed, in the
format of cards 274/295, and kept at ``.auto-pm/release-candidates/<release id>/release_card.md`` beside the gate verdict and the audit
signoff.  The payload list is taken from the commit's **own** ``scripts/pmf_build.py`` (the same builder that will write the folder),
plus the release meta file; the folder itself is listed too, because the Work's scope names it as one path.

A card that is already there is reused unchanged, so a resumed deploy precheck runs against the same bytes the Work was opened with.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from auto_pm.application.core import release_deploy_check as check
from auto_pm.application.core import release_ops as ops

CANDIDATES_DIR = Path(".auto-pm") / "release-candidates"
CARD_NAME = "release_card.md"
CONTAINER = "00_Infrastructure/auto_pm"
POINTERS = ("active_release.json", "previous_release.json", "deployment_manifest.json")


class ReleaseCardError(RuntimeError):
    """The card cannot be generated; the message says why.  Nothing has been written to the books or the pointers."""


def card_path(root: Path, release_id: str) -> Path:
    return Path(root) / CANDIDATES_DIR / release_id / CARD_NAME


def payload_files(repo: Path, commit: str) -> list[str]:
    """Release-relative paths ``build`` will write for ``commit``: the commit's own builder's payload plus its meta file."""

    with tempfile.TemporaryDirectory(prefix="pmf-card-") as scratch:
        try:
            builder = ops._load_builder(Path(repo), commit, Path(scratch))  # noqa: SLF001 - the same frozen builder ``build`` uses
            files = list(builder.export_payload(Path(repo), commit, check.PROJECT_DIR))
            meta = str(builder.META_NAME)
        except Exception as error:  # noqa: BLE001 - any failure to list the payload stops the deploy before the books
            raise ReleaseCardError(f"列不出提交 {commit[:12]} 的载荷文件：{type(error).__name__}: {error}") from error
        finally:
            sys.modules.pop("pmf_build", None)
    if not files:
        raise ReleaseCardError(f"提交 {commit[:12]} 没有载荷文件")
    return sorted({*files, meta})


def _baseline(root: Path) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", errors="replace",  # lenient-decode: only a commit id is read
        stdin=subprocess.DEVNULL, timeout=60, check=False,
    )
    baseline = done.stdout.strip()
    if done.returncode != 0 or len(baseline) != 40:
        raise ReleaseCardError(f"读不出控制根的 HEAD，入账卡没法写隔离基线：{(done.stderr or done.stdout).strip()[-200:]}")
    return baseline


def render(*, release_id: str, old_release: str, commit: str, baseline: str, files: Sequence[str]) -> str:
    """The card text, in the format of cards 274/295: header lines, one paragraph, and the path table."""

    if not files:
        raise ReleaseCardError(f"发布 {release_id} 没有载荷文件，入账卡没有可列的路径")
    folder = f"{CONTAINER}/releases/{release_id}"
    pointer_use = f"发布指针/清单（现行改成 {release_id}，上一版改成 {old_release}；清单加 {release_id} 一条）"
    rows = [f"| `{CONTAINER}/{name}` | 存在 | {pointer_use} |" for name in POINTERS]
    rows.append(f"| `{folder}` | 计划新增 | 发布 {release_id} 的目录（建账时 Work 的可改范围按目录写） |")
    rows += [f"| `{folder}/{name}` | 计划新增 | 发布 {release_id} 的载荷文件 |" for name in sorted(files)]
    return "\n".join([
        f"# RELEASE-{release_id} 入账卡（驾驶舱生成）",
        "",
        f"> 卡片编号：`CARD-RELEASE-{release_id}-DEPLOY V1.0`",
        f"> 隔离基线：`{baseline}`（控制根 HEAD）",
        "> 路径根：`.`",
        "> 档次：核心档",
        "> 安全回路: 否",
        "",
        f"本卡由驾驶舱在真发版（release deploy、release ship）时按发布号现场生成（CHG-SCPT-2026-709），只给这次发布建账（写入型 Work 的可改范围）"
        f"和切换后的卡预检用。发布 {release_id}（提交 {commit}），上一版 {old_release}。路径表：三个指针（deployment_manifest.json 是清单）、"
        f"发布目录本身，以及这次提交自己的 scripts/pmf_build.py 列出的 {len(files)} 个载荷文件（含发布元数据文件）。本卡不碰 PLC 程序文件，安全回路填“否”。",
        "",
        "| 路径 | 基线状态 | 用途 |",
        "|---|---|---|",
        *rows,
        "",
    ])


def ensure_card(
    root: Path, *, release_id: str, old_release: str, commit: str, files: Sequence[str] | None = None,
) -> Path:
    """The card of ``release_id`` under the control root ``root``: reused if it is already there, generated otherwise."""

    path = card_path(root, release_id)
    if path.is_file():
        head = path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]  # lenient-decode: only the title line is compared
        if head != [f"# RELEASE-{release_id} 入账卡（驾驶舱生成）"]:
            raise ReleaseCardError(f"{path} 已存在但不是发布 {release_id} 的入账卡，没有覆盖；请先看一眼再挪走")
        return path
    listed = list(files) if files is not None else payload_files(Path(root), commit)
    if not listed:
        raise ReleaseCardError(f"发布 {release_id} 没有载荷文件，入账卡没有可列的路径")
    text = render(release_id=release_id, old_release=old_release, commit=commit, baseline=_baseline(Path(root)), files=listed)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".md.tmp")
    partial.write_text(text, encoding="utf-8")
    partial.replace(path)
    return path
