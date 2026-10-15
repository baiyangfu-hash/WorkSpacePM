"""PMF 可复现构建入口（WBS D02）。

只从一个**已提交**的 Git 提交构建发布载荷（``auto_pm`` 与 ``templates``），因此工作树是否 dirty、有没有未跟踪文件都不影响结果；
输入不是提交对象、载荷缺必需入口、载荷里有指向载荷之外的 ``auto_pm`` 导入、输出目录已存在，一律拒绝。
同一提交两次构建得到相同的文件清单与相同的 ``release_meta.json``（``built_at`` 取提交时间，不取当前时间）。
“可复现”的判据：载荷文件逐字节相同，且 ``release_meta.json`` 除 ``builder.*``（构建机器的解释器版本等）外相同；``verify`` 据此忽略 ``builder.*``。

本脚本只**构建**，不触碰 ``active_release.json``、``previous_release.json``，也不写 ``deployment_manifest.json``：
切换与回退是 D06、D07 的事，需要用户另行授权。

用法::

    python scripts/pmf_build.py build  --repo <仓库根> --commit <提交> --project-root <仓库内的相对路径> --output <新目录> [--release-id ID]
    python scripts/pmf_build.py verify --output <目录> [--manifest <deployment_manifest.json> --release-id ID]

退出码：0 成功；2 被拒绝（原因写在标准输出的 JSON 里）；3 输入错误。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import platform
import re
import subprocess
import sys
import tarfile
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

PAYLOAD_DIRS = ("auto_pm", "templates")
REQUIRED_FILES = ("auto_pm/__init__.py", "auto_pm/__main__.py")
#: ``auto_pm/__init__.py`` 把这些分层目录加进包搜索路径（PEP 420），``auto_pm.core`` 因此解析到 ``auto_pm/application/core``
IMPORT_ROOTS = ("auto_pm", "auto_pm/domain", "auto_pm/infrastructure", "auto_pm/application", "auto_pm/ui")
META_SCHEMA = "release_metadata.v1"
META_NAME = "release_meta.json"
#: ``release_meta.json`` 里允许因机器而异的键：判可复现与 ``verify`` 时不比较
META_VOLATILE_KEYS = ("builder",)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class BuildError(Exception):
    """构建被拒绝：``code`` 是稳定的机器可读原因，``details`` 是人读的补充。"""

    def __init__(self, code: str, details: str = "") -> None:
        super().__init__(f"{code}: {details}" if details else code)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class BuildResult:
    release_id: str
    source_commit: str
    version: str
    built_at: str
    files: dict[str, str]
    output: Path

    def manifest_entry(self) -> dict[str, object]:
        """与 ``deployment_manifest.v1`` 里一个发布条目同形（键排序、路径排序）。"""
        return {"source_commit": self.source_commit, "version": self.version, "built_at": self.built_at, "files": dict(sorted(self.files.items()))}


def _git(repo: Path, *args: str) -> bytes:
    done = subprocess.run(["git", "-C", str(repo), "-c", "core.quotePath=false", *args], capture_output=True)
    if done.returncode != 0:
        raise BuildError("git-failed", f"git {' '.join(args)}: {done.stderr.decode('utf-8', errors='replace').strip()[:300]}")
    return done.stdout


def resolve_commit(repo: Path, rev: str) -> str:
    """把 ``rev`` 解析成 40 位提交号；不是提交对象（含不存在）就拒绝。"""
    done = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"], capture_output=True)
    commit = done.stdout.decode("utf-8", errors="replace").strip()
    if done.returncode != 0 or not _SHA_RE.match(commit):
        raise BuildError("not-a-commit", f"{rev!r} is not a commit object of {repo}")
    return commit


def commit_time(repo: Path, commit: str) -> str:
    """提交时间（UTC，秒）；``built_at`` 用它而不是当前时间，所以构建可复现。"""
    seconds = int(_git(repo, "show", "-s", "--format=%ct", commit).decode("ascii").strip())
    return datetime.fromtimestamp(seconds, UTC).isoformat(timespec="seconds")


def project_version(repo: Path, commit: str, project_root: str) -> str:
    raw = _git(repo, "show", f"{commit}:{project_root.rstrip('/')}/pyproject.toml")
    try:
        version = tomllib.loads(raw.decode("utf-8-sig"))["project"]["version"]
    except (KeyError, tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise BuildError("version-unreadable", f"pyproject.toml of {commit[:8]}: {type(exc).__name__}") from exc
    if not isinstance(version, str) or not version:
        raise BuildError("version-unreadable", "project.version is not a non-empty string")
    return version


def export_payload(repo: Path, commit: str, project_root: str) -> dict[str, bytes]:
    """用 ``git archive`` 取 ``<commit>:<project_root>`` 下的 ``auto_pm`` 与 ``templates``；字节级、不经过工作树。"""
    for name in PAYLOAD_DIRS:
        listed = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{commit}:{project_root.rstrip('/')}/{name}"], capture_output=True)
        if listed.returncode != 0:
            raise BuildError("missing-payload-dir", f"{name}/ is not in {commit[:8]}:{project_root}")
    raw = _git(repo, "archive", "--format=tar", f"{commit}:{project_root.rstrip('/')}", *PAYLOAD_DIRS)
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        for member in tar.getmembers():
            if member.isdir():
                continue
            if not member.isfile():
                raise BuildError("unsupported-member", f"{member.name} is a link or special file")
            parts = PurePosixPath(member.name).parts
            if "__pycache__" in parts or member.name.endswith(".pyc"):
                continue
            extracted = tar.extractfile(member)
            assert extracted is not None
            files[member.name] = extracted.read()
    return files


def check_required(files: dict[str, bytes]) -> None:
    missing = [name for name in REQUIRED_FILES if name not in files]
    if missing:
        raise BuildError("missing-required-file", ", ".join(missing))
    if not any(name.startswith("templates/") for name in files):
        raise BuildError("missing-templates", "the payload has no file under templates/")


def unresolved_imports(files: dict[str, bytes]) -> list[tuple[str, str]]:
    """载荷里每个 ``auto_pm`` 导入都必须解析到载荷内的模块或包；返回解析不到的 (文件, 模块)。"""
    names = set(files)
    dirs: set[str] = set()
    for name in names:
        parent = PurePosixPath(name).parent
        while str(parent) not in (".", ""):
            dirs.add(str(parent))
            parent = parent.parent

    def resolves(module: str) -> bool:
        parts = module.split(".")[1:]
        if not parts:
            return True
        rel = "/".join(parts)
        return any(f"{base}/{rel}.py" in names or f"{base}/{rel}/__init__.py" in names or f"{base}/{rel}" in dirs for base in IMPORT_ROOTS)

    problems: list[tuple[str, str]] = []
    for name in sorted(names):
        if not name.endswith(".py"):
            continue
        try:
            tree = ast.parse(files[name].decode("utf-8-sig"))
        except (SyntaxError, UnicodeDecodeError):
            problems.append((name, "<unparsable>"))
            continue
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names if alias.name == "auto_pm" or alias.name.startswith("auto_pm.")]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and (node.module == "auto_pm" or node.module.startswith("auto_pm.")):
                modules = [node.module]
            problems.extend((name, module) for module in modules if not resolves(module))
    return sorted(set(problems))


def release_meta(release_id: str, commit: str, version: str, built_at: str) -> dict[str, object]:
    return {
        "schema_version": META_SCHEMA,
        "release_id": release_id,
        "source_commit": commit,
        "version": version,
        "built_at": built_at,
        "builder": {
            "interpreter": platform.python_version(),
            "description": "PMF D02 deterministic export: git archive <commit>:<project root> auto_pm templates; built_at = commit time; payload from git objects only",
        },
    }


def meta_identity(meta: dict[str, object]) -> dict[str, object]:
    """``release_meta.json`` 去掉因机器而异的键（``builder``）之后的身份部分。"""
    return {key: value for key, value in meta.items() if key not in META_VOLATILE_KEYS}


def compare_meta(recorded: dict[str, object], rebuilt: dict[str, object]) -> list[str]:
    """记录里写了的身份键与重建结果不同的键名（``builder`` 不比较；``source_commit`` 允许记录里是缩写，即重建值的前缀）。"""
    problems: list[str] = []
    for key, value in meta_identity(recorded).items():
        other = rebuilt.get(key)
        if key == "source_commit" and isinstance(value, str) and isinstance(other, str):
            if not value or not (other.startswith(value) or value.startswith(other)):
                problems.append(key)
        elif other != value:
            problems.append(key)
    return sorted(problems)


def build(repo: Path, commit_rev: str, project_root: str, output: Path, release_id: str | None = None) -> BuildResult:
    """构建并写出载荷；任何拒绝条件成立时**不写任何文件**。"""
    repo = repo.resolve()
    commit = resolve_commit(repo, commit_rev)
    if output.exists():
        raise BuildError("output-exists", str(output))
    version = project_version(repo, commit, project_root)
    built_at = commit_time(repo, commit)
    files = export_payload(repo, commit, project_root)
    check_required(files)
    problems = unresolved_imports(files)
    if problems:
        raise BuildError("unresolved-import", "; ".join(f"{name} -> {module}" for name, module in problems[:10]))
    rid = release_id or f"{version}-{commit[:7]}"
    meta_bytes = (json.dumps(release_meta(rid, commit, version, built_at), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    files[META_NAME] = meta_bytes
    for name, data in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    return BuildResult(rid, commit, version, built_at, manifest, output)


def verify(output: Path, manifest_files: dict[str, str] | None = None, recorded_meta: dict[str, object] | None = None) -> dict[str, list[str]]:
    """重算 ``output`` 下每个文件的 SHA-256 并与清单比较；没有给清单时只返回文件数。

    ``release_meta.json`` 不按整文件哈希比较（它带构建机器的解释器版本）：检查它可解析、``schema_version`` 正确，
    给了 ``recorded_meta`` 时再比较记录里写了的身份键（``builder`` 除外）。载荷文件的任何不同仍是 ``mismatch``。
    """
    actual: dict[str, str] = {}
    for path in sorted(output.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            actual[path.relative_to(output).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    meta_problems: list[str] = []
    if META_NAME in actual:
        try:
            meta = json.loads((output / META_NAME).read_text(encoding="utf-8"))
        except ValueError:
            meta = None
            meta_problems.append("unparsable")
        if isinstance(meta, dict):
            if meta.get("schema_version") != META_SCHEMA:
                meta_problems.append("schema_version")
            if recorded_meta is not None:
                meta_problems.extend(key for key in compare_meta(recorded_meta, meta) if key not in meta_problems)
        elif meta is not None:
            meta_problems.append("unparsable")
    if manifest_files is None:
        return {"missing": [], "orphans": [], "mismatch": [], "meta": meta_problems, "files": [str(len(actual))]}
    return {
        "missing": sorted(set(manifest_files) - set(actual)),
        "orphans": sorted(set(actual) - set(manifest_files)),
        "mismatch": sorted(k for k in manifest_files if k in actual and k != META_NAME and manifest_files[k] != actual[k]),
        "meta": meta_problems,
        "files": [str(len(actual))],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "pmf build")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--repo", required=True)
    b.add_argument("--commit", required=True)
    b.add_argument("--project-root", required=True)
    b.add_argument("--output", required=True)
    b.add_argument("--release-id")
    v = sub.add_parser("verify")
    v.add_argument("--output", required=True)
    v.add_argument("--manifest")
    v.add_argument("--release-id")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build(Path(args.repo), args.commit, args.project_root, Path(args.output), args.release_id)
            print(json.dumps({"ok": True, "release_id": result.release_id, "source_commit": result.source_commit, "version": result.version, "built_at": result.built_at,
                              "files": len(result.files), "output": str(result.output)}, ensure_ascii=False))
            return 0
        entry_files: dict[str, str] | None = None
        recorded: dict[str, object] | None = None
        if args.manifest:
            if not args.release_id:
                print(json.dumps({"ok": False, "code": "input-error", "details": "--release-id is required with --manifest"}, ensure_ascii=False))
                return 3
            entry = json.loads(Path(args.manifest).read_text(encoding="utf-8"))["releases"][args.release_id]
            entry_files = entry["files"]
            recorded = {"release_id": args.release_id, **{k: entry[k] for k in ("source_commit", "version", "built_at") if k in entry}}
        report = verify(Path(args.output), entry_files, recorded)
        clean = not report["missing"] and not report["orphans"] and not report["mismatch"] and not report["meta"]
        print(json.dumps({"ok": clean, **report}, ensure_ascii=False))
        return 0 if clean else 2
    except BuildError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "details": exc.details}, ensure_ascii=False))
        return 2
    except (OSError, KeyError, ValueError) as exc:
        print(json.dumps({"ok": False, "code": "input-error", "details": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 3


if __name__ == "__main__":
    sys.exit(main())
