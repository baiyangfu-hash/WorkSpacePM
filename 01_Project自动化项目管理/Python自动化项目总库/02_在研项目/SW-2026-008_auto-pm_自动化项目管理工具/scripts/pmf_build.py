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
import json
import platform
import re
import subprocess
import sys
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
#: ``release_meta.json`` 允许出现的全部键；多出来的键视为篡改
META_KNOWN_KEYS = ("schema_version", "release_id", "source_commit", "version", "built_at", "builder")
META_REQUIRED_KEYS = ("schema_version", "release_id", "source_commit", "version", "built_at")
#: 记录里的缩写提交号至少这么长才算前缀匹配（再短的前缀对不上任何东西）
MIN_COMMIT_PREFIX = 7
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
    """取 ``<commit>:<project_root>`` 下的 ``auto_pm`` 与 ``templates``：用 ``ls-tree`` 列目录、``cat-file --batch`` 读 blob，字节与提交里的完全一致。

    不用 ``git archive``：它会按构建机器的 ``core.autocrlf`` 与 eol 属性转换换行，同一提交在不同机器上得到不同字节。
    """
    root = project_root.rstrip("/")
    for name in PAYLOAD_DIRS:
        listed = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{commit}:{root}/{name}"], capture_output=True)
        if listed.returncode != 0:
            raise BuildError("missing-payload-dir", f"{name}/ is not in {commit[:8]}:{project_root}")
    raw = _git(repo, "ls-tree", "-r", "-z", "--full-tree", commit, "--", *[f"{root}/{name}" for name in PAYLOAD_DIRS])
    wanted: list[tuple[str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, _, path = record.partition(b"\t")
        mode, kind, oid = meta.decode("ascii").split()
        rel = path.decode("utf-8")[len(root) + 1:]
        if kind != "blob" or mode not in ("100644", "100755"):
            raise BuildError("unsupported-member", f"{rel} is a link, a submodule or a special file")
        if "__pycache__" in PurePosixPath(rel).parts or rel.endswith(".pyc"):
            continue
        wanted.append((rel, oid))
    done = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], input=("".join(f"{oid}\n" for _rel, oid in wanted)).encode("ascii"), capture_output=True)
    if done.returncode != 0:
        raise BuildError("git-failed", f"git cat-file --batch: {done.stderr.decode('utf-8', errors='replace').strip()[:300]}")
    out, cursor = done.stdout, 0
    files: dict[str, bytes] = {}
    for rel, oid in wanted:
        newline = out.index(b"\n", cursor)
        header = out[cursor:newline].decode("ascii").split()
        if len(header) != 3 or header[0] != oid or header[1] != "blob":
            raise BuildError("git-failed", f"unexpected cat-file header for {rel}: {' '.join(header)}")
        size = int(header[2])
        files[rel] = out[newline + 1:newline + 1 + size]
        cursor = newline + 1 + size + 1
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


def compare_meta(recorded: dict[str, object], rebuilt: dict[str, object], *, complete: bool = False) -> list[str]:
    """记录与重建结果不同的身份键名（``builder`` 不比较）。

    默认只比较记录里写了的键；``complete=True``（记录是一份完整的 release_meta.json）时键集合也必须相同。
    ``source_commit`` 允许记录里是缩写，但缩写至少 ``MIN_COMMIT_PREFIX`` 位且必须是重建值的前缀（反过来也一样）。
    """
    problems: set[str] = set()
    left, right = meta_identity(recorded), meta_identity(rebuilt)
    keys = set(left) | set(right) if complete else set(left)
    for key in keys:
        value, other = left.get(key), right.get(key)
        if key == "source_commit" and isinstance(value, str) and isinstance(other, str):
            short, long_ = sorted((value, other), key=len)
            if len(short) < MIN_COMMIT_PREFIX or not long_.startswith(short):
                problems.add(key)
        elif key not in left or key not in right or value != other:
            problems.add(key)
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
    ``__pycache__``/``*.pyc`` 不算载荷，单列在 ``bytecode``；命令行只要它非空就判不通过（与稳定启动器的精确树校验一致）。
    """
    actual: dict[str, str] = {}
    bytecode: list[str] = []
    for path in sorted(output.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(output).as_posix()
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            # 不算载荷，但必须报出来：稳定启动器把发布目录里的缓存判为未登记节点，校验“通过”而启动失败就是 D08 的坑。
            bytecode.append(relative)
            continue
        actual[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
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
            meta_problems.extend(f"unexpected-key:{key}" for key in sorted(set(meta) - set(META_KNOWN_KEYS)))
            meta_problems.extend(f"missing-key:{key}" for key in META_REQUIRED_KEYS if key not in meta and key != "schema_version")
            if recorded_meta is not None:
                meta_problems.extend(key for key in compare_meta(recorded_meta, meta) if key not in meta_problems and f"missing-key:{key}" not in meta_problems)
        elif meta is not None:
            meta_problems.append("unparsable")
    if manifest_files is None:
        return {"missing": [], "orphans": [], "mismatch": [], "meta": meta_problems, "bytecode": bytecode, "files": [str(len(actual))]}
    return {
        "missing": sorted(set(manifest_files) - set(actual)),
        "orphans": sorted(set(actual) - set(manifest_files)),
        "mismatch": sorted(k for k in manifest_files if k in actual and k != META_NAME and manifest_files[k] != actual[k]),
        "meta": meta_problems,
        "bytecode": bytecode,
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
        clean = not report["missing"] and not report["orphans"] and not report["mismatch"] and not report["meta"] and not report["bytecode"]
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
