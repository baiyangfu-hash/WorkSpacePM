"""文档验证档：只改文档/配置/图纸类文件的 Run 也要有合法的质量验证出口（D1，TD-SW008-D1）。

Python 档要求 Run 拥有 ``.py`` 文件才能跑 pytest/Ruff/Mypy；PLC 档要求 PLC 工程内的路径。
一张 scope 里只有 ``README.md`` 的卡两档都进不去，``pm verify`` 永远拒绝，Mission 到不了验收、
也没有收尾路径。本模块补上第三档（``checkpoint-evidence.v4``，领域 ``docs``）：

* 两道进程内静态门：``docs-encoding``（owned 文本文件必须是严格 UTF-8、不含 NUL）
  与 ``docs-syntax``（``.json``/``.toml``/``.yaml`` 能解析，任何文本里没有遗留的合并冲突标记）。
* 收据绑定：owned 范围内每个文件的字节摘要（含 Git 看不见的被忽略文件）和本模块源码摘要，
  任一变化，已存的 Checkpoint 都不能重放。
* 不留旁路（白名单）：owned 范围（含目录里的文件）只允许已知的文档/图纸/配置后缀；
  其它一切（``.py``、``.ps1``、``.scl``、``.sql``、``.exe``、无后缀文件……）文档档都拒绝——
  它们必须走 Python/PLC 档，不能借文档档绕过真正的测试。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from auto_pm.application.core.evidence_collection_service import (
    EvidenceCollection,
    EvidenceCollectionError,
    EvidenceCollectionService,
    PythonQualityGate,
    _canonical_json_payload,
    _collection_payload,
    _PlcGateTimeoutError,
    _quality_gate_payload,
    _quality_gate_timeout_seconds,
    _run_bounded,
    _safe_output_summary,
    _sha256_payload,
)
from auto_pm.contracts.continuity import RunItem

DOCS_CHECKPOINT_SCHEMA = "checkpoint-evidence.v4"
DOCS_ENCODING_COMMAND = "auto_pm.application.core.docs_checkpoint.check_encoding"
DOCS_SYNTAX_COMMAND = "auto_pm.application.core.docs_checkpoint.check_syntax"

# 会被逐字节解码检查的文本后缀（小写）。其余后缀（docx/xlsx/pdf/dwg/图片…）只绑摘要，不解码。
TEXT_SUFFIXES = frozenset(
    {
        ".md", ".mdc", ".txt", ".rst", ".csv", ".json", ".toml", ".yaml", ".yml", ".ini",
        ".cfg", ".xml", ".html", ".htm", ".css", ".svg",
    }
)
# 只摘要不解码的文档/图纸/办公文件后缀（二进制）。
BINARY_DOC_SUFFIXES = frozenset(
    {
        ".pdf", ".doc", ".docx", ".dot", ".dotx", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx",
        ".vsd", ".vsdx", ".dwg", ".dxf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
        ".ico", ".zip",
    }
)
# 白名单：文档档只收这些后缀。其余一律拒绝（含无后缀文件、.py/.ps1/.scl/.sql/.go/.exe/.dll/.pyc…），
# 代码和未知类型必须走 Python/PLC 档，不能借文档档绕开真正的门禁。
DOCS_ALLOWED_SUFFIXES = TEXT_SUFFIXES | BINARY_DOC_SUFFIXES
_CONFLICT_MARKER = re.compile(r"^(?:<{7}|>{7})(?: |$)", re.MULTILINE)


@dataclass(frozen=True)
class DocsQualityReceipt:
    """Content-bound result of the in-process document encoding and syntax gates."""

    run_id: str
    baseline_git_head: str
    candidate_path: str
    project_root: str
    evidence_hash: str
    gates: tuple[PythonQualityGate, ...]
    evidence_current: bool
    evidence_error: str | None
    content_hash: str
    owned_docs_paths: tuple[str, ...]
    input_digests: tuple[tuple[str, str], ...]
    checker_digest: str

    @property
    def status(self) -> str:
        """PASS only for successful static gates and unchanged evidence."""

        if self.evidence_current and self.gates and all(gate.passed for gate in self.gates):
            return "PASS"
        return "FAIL"


@dataclass(frozen=True)
class DocsTargets:
    """The owned document files of one Run, resolved against the governed candidate."""

    owned: tuple[str, ...]
    text_files: tuple[str, ...]
    input_digests: tuple[tuple[str, str], ...]


def docs_targets(run: RunItem, candidate: Path, anchor: Path) -> DocsTargets:
    """Resolve owned paths into the exact files to check; refuse code files and escapes."""

    EvidenceCollectionService._normalize_owned_paths(run.owned_paths)
    owned: list[str] = []
    digests: dict[str, str] = {}
    texts: set[str] = set()
    for raw in run.owned_paths:
        relative = PurePosixPath(str(raw).replace("\\", "/"))
        absolute = candidate.joinpath(*relative.parts).resolve()
        try:
            absolute.relative_to(candidate)
            absolute.relative_to(anchor)
        except ValueError as error:
            raise EvidenceCollectionError(f"文档验证档：owned path 超出 project_root: {relative}") from error
        owned.append(relative.as_posix())
        if not absolute.exists() and not absolute.is_symlink():
            continue  # 被本 Run 删除（或还不存在）：Git 证据会看到；这里没有字节可查
        files = _files_under(absolute) if absolute.is_dir() and not absolute.is_symlink() else [absolute]
        for path in files:
            name = path.relative_to(candidate).as_posix()
            suffix = path.suffix.lower()
            if suffix not in DOCS_ALLOWED_SUFFIXES:
                shown = suffix or "无后缀"
                raise EvidenceCollectionError(
                    f"文档验证档只收文档/图纸/配置类文件，不收（{shown}）: {name}；代码和未知类型必须走 "
                    "Python/PLC 验证档，请把 scope 拆开（文档一张卡、代码一张卡）"
                )
            digests[name] = _file_digest(path)
            if suffix in TEXT_SUFFIXES and not path.is_symlink():
                texts.add(name)
    return DocsTargets(
        owned=tuple(sorted(set(owned))),
        text_files=tuple(sorted(texts)),
        input_digests=tuple(sorted(digests.items())),
    )


def _files_under(directory: Path) -> list[Path]:
    found: list[Path] = []
    for current, names, files in os.walk(directory):
        names[:] = sorted(name for name in names if name != ".git")
        for name in sorted(files):
            found.append(Path(current) / name)
        for name in names:
            if (Path(current) / name).is_symlink():
                found.append(Path(current) / name)  # 目录符号链接只绑目标文字，不进入
    return found


def _file_digest(path: Path) -> str:
    if path.is_symlink():
        return f"symlink:{os.readlink(path)}"
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise EvidenceCollectionError(f"文档验证档：文件无法读取: {path.name}") from error


def checker_digest() -> str:
    """Fingerprint this module's bytes: the rules that produced the verdict."""

    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def gate_plan(candidate: Path, anchor: Path, targets: DocsTargets) -> tuple[tuple[str, tuple[str, ...], Path], ...]:
    """The fixed gates, listed once so producers and replay checks cannot drift."""

    return (
        ("docs-encoding", (DOCS_ENCODING_COMMAND, *targets.text_files), anchor),
        ("docs-syntax", (DOCS_SYNTAX_COMMAND, *targets.text_files), anchor),
    )


def check_encoding(candidate: Path, text_files: tuple[str, ...]) -> tuple[str, int | None]:
    """Every owned text file must be strict UTF-8 without NUL bytes (DEV-ENC-001)."""

    problems: list[str] = []
    for name in text_files:
        data = (candidate / name).read_bytes()
        if b"\0" in data:
            problems.append(f"{name}: 含 NUL 字节，不是文本文件")
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as error:
            problems.append(f"{name}: 不是合法 UTF-8（第 {error.start} 字节附近），请另存为 UTF-8")
    lines = [*problems, f"checked {len(text_files)} text files, {len(problems)} problems"]
    return "\n".join(lines), (1 if problems else 0)


def check_syntax(candidate: Path, text_files: tuple[str, ...]) -> tuple[str, int | None]:
    """JSON/TOML/YAML must parse; no leftover merge-conflict markers in any text file."""

    problems: list[str] = []
    for name in text_files:
        try:
            text = (candidate / name).read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue  # docs-encoding 已经报告这个文件
        suffix = PurePosixPath(name).suffix.lower()
        try:
            if suffix == ".json":
                json.loads(text.lstrip("﻿"))
            elif suffix == ".toml":
                tomllib.loads(text.lstrip("﻿"))
            elif suffix in {".yaml", ".yml"}:
                list(yaml.safe_load_all(text))
        except (ValueError, yaml.YAMLError) as error:
            problems.append(f"{name}: {suffix[1:]} 语法错误: {str(error).splitlines()[0] if str(error) else error}")
        if _CONFLICT_MARKER.search(text):
            problems.append(f"{name}: 含未解决的合并冲突标记（<<<<<<< 或 >>>>>>>）")
    lines = [*problems, f"checked {len(text_files)} text files, {len(problems)} problems"]
    return "\n".join(lines), (1 if problems else 0)


def _run_gate(candidate: Path, name: str, command: tuple[str, ...], root: Path, text_files: tuple[str, ...]) -> PythonQualityGate:
    def judge() -> tuple[str, int | None]:
        return (check_encoding if name == "docs-encoding" else check_syntax)(candidate, text_files)

    try:
        output, exit_code = _run_bounded(judge, _quality_gate_timeout_seconds())
    except _PlcGateTimeoutError as error:
        output, exit_code = f"timeout: {error}", None
    except Exception as error:
        output, exit_code = f"launch error: {error}", None
    return PythonQualityGate(
        name=name,
        command=command,
        cwd=str(root),
        exit_code=exit_code,
        output_digest=hashlib.sha256(output.encode("utf-8")).hexdigest(),
        output_summary=_safe_output_summary(output),
    )


def validate_project_root(collector: EvidenceCollectionService, run: RunItem, project_root: str | Path) -> Path:
    """Require every owned path to sit under the supplied project root (and hold no code file)."""

    candidate, anchor = collector._quality_context(run, project_root)
    docs_targets(run, candidate, anchor)
    return anchor


def run_gates(collector: EvidenceCollectionService, run: RunItem, project_root: str | Path) -> DocsQualityReceipt:
    """Run both document gates on the governed candidate and bind the result."""

    candidate, anchor = collector._quality_context(run, project_root)
    targets = docs_targets(run, candidate, anchor)
    before = collector.collect(run)
    digest = checker_digest()
    gates = tuple(
        _run_gate(candidate, name, command, root, targets.text_files)
        for name, command, root in gate_plan(candidate, anchor, targets)
    )
    evidence_current = False
    evidence_error: str | None = None
    try:
        after = collector.collect(run)
        after_targets = docs_targets(run, candidate, anchor)
        evidence_current = (
            hmac.compare_digest(before.content_hash, after.content_hash)
            and after_targets.input_digests == targets.input_digests
        )
        if not evidence_current:
            evidence_error = "质量门执行期间 Run evidence 或文档输入已变化"
    except EvidenceCollectionError as error:
        evidence_error = f"质量门后 Run evidence 无法复核: {error}"
    fields = dict(
        run_id=run.run_id,
        baseline_git_head=run.git_head,
        candidate_path=str(candidate),
        project_root=str(anchor),
        evidence_hash=before.content_hash,
        gates=gates,
        evidence_current=evidence_current,
        evidence_error=evidence_error,
        owned_docs_paths=targets.owned,
        input_digests=targets.input_digests,
        checker_digest=digest,
    )
    return DocsQualityReceipt(content_hash=receipt_hash(**fields), **fields)  # type: ignore[arg-type]


def receipt_payload_fields(
    *,
    run_id: str,
    baseline_git_head: str,
    candidate_path: str,
    project_root: str,
    evidence_hash: str,
    gates: tuple[PythonQualityGate, ...],
    evidence_current: bool,
    evidence_error: str | None,
    owned_docs_paths: tuple[str, ...],
    input_digests: tuple[tuple[str, str], ...],
    checker_digest: str,
) -> dict[str, object]:
    """One exact schema for receipt hashing and checkpoint serialization."""

    return {
        "domain": "docs",
        "run_id": run_id,
        "baseline_git_head": baseline_git_head,
        "candidate_path": candidate_path,
        "project_root": project_root,
        "evidence_hash": evidence_hash,
        "gates": [_quality_gate_payload(gate) for gate in gates],
        "evidence_current": evidence_current,
        "evidence_error": evidence_error,
        "owned_docs_paths": list(owned_docs_paths),
        "input_digests": [{"path": path, "sha256": digest} for path, digest in input_digests],
        "checker_digest": checker_digest,
    }


def receipt_hash(**fields: object) -> str:
    """Hash the fixed receipt payload used by ``checkpoint-evidence.v4``."""

    return _sha256_payload(receipt_payload_fields(**fields))  # type: ignore[arg-type]


def _receipt_fields(receipt: DocsQualityReceipt) -> dict[str, object]:
    return {
        "run_id": receipt.run_id,
        "baseline_git_head": receipt.baseline_git_head,
        "candidate_path": receipt.candidate_path,
        "project_root": receipt.project_root,
        "evidence_hash": receipt.evidence_hash,
        "gates": receipt.gates,
        "evidence_current": receipt.evidence_current,
        "evidence_error": receipt.evidence_error,
        "owned_docs_paths": receipt.owned_docs_paths,
        "input_digests": receipt.input_digests,
        "checker_digest": receipt.checker_digest,
    }


def receipt_is_current(
    collector: EvidenceCollectionService, run: RunItem, project_root: str | Path, receipt: DocsQualityReceipt
) -> bool:
    """Whether a docs receipt still describes the current Run and its inputs."""

    candidate, _ = collector._verified_candidate(run)
    anchor = Path(project_root).resolve()
    if (
        receipt.run_id != run.run_id
        or receipt.baseline_git_head != run.git_head
        or receipt.candidate_path != str(candidate)
        or receipt.project_root != str(anchor)
        or receipt.status != "PASS"
    ):
        return False
    try:
        targets = docs_targets(run, candidate, anchor)
        expected = tuple((n, c, str(r)) for n, c, r in gate_plan(candidate, anchor, targets))
        if (
            tuple((g.name, g.command, g.cwd) for g in receipt.gates) != expected
            or receipt.owned_docs_paths != targets.owned
            or receipt.input_digests != targets.input_digests
            or receipt.checker_digest != checker_digest()
            or not hmac.compare_digest(receipt.content_hash, receipt_hash(**_receipt_fields(receipt)))
        ):
            return False
        current = collector.collect(run)
    except EvidenceCollectionError:
        return False
    return hmac.compare_digest(receipt.evidence_hash, current.content_hash)


def build_evidence(collection: EvidenceCollection, receipt: DocsQualityReceipt) -> str:
    """Build the canonical ``checkpoint-evidence.v4`` envelope for a docs Run."""

    if (
        receipt.status != "PASS"
        or not receipt.evidence_current
        or receipt.run_id != collection.run_id
        or receipt.baseline_git_head != collection.git_head
        or receipt.candidate_path != collection.worktree_path
        or not hmac.compare_digest(receipt.evidence_hash, collection.content_hash)
        or not hmac.compare_digest(receipt.content_hash, receipt_hash(**_receipt_fields(receipt)))
    ):
        raise EvidenceCollectionError("自动 Checkpoint 的文档质量收据与当前 evidence 不一致")
    unsigned = {
        "schema_version": DOCS_CHECKPOINT_SCHEMA,
        "collection": _collection_payload(collection),
        "collection_hash": collection.content_hash,
        "quality_receipt": {**receipt_payload_fields(**_receipt_fields(receipt)), "status": receipt.status},  # type: ignore[arg-type]
        "receipt_hash": receipt.content_hash,
    }
    return _canonical_json_payload({**unsigned, "envelope_hash": _sha256_payload(unsigned)})


def evidence_is_current(
    serialized: str,
    envelope: dict[str, object],
    collection: EvidenceCollection,
    run: RunItem,
    project_root: str | Path,
) -> bool:
    """Recompute targets, gates, inputs and rule bytes before replaying a stored v4 envelope."""

    if set(envelope) != {
        "schema_version", "collection", "collection_hash", "quality_receipt",
        "receipt_hash", "envelope_hash",
    }:
        return False
    unsigned = {key: value for key, value in envelope.items() if key != "envelope_hash"}
    if (
        serialized != _canonical_json_payload(envelope)
        or envelope["schema_version"] != DOCS_CHECKPOINT_SCHEMA
        or not isinstance(envelope["envelope_hash"], str)
        or envelope["envelope_hash"] != _sha256_payload(unsigned)
        or envelope["collection"] != _collection_payload(collection)
        or envelope["collection_hash"] != collection.content_hash
    ):
        return False
    payload = envelope["quality_receipt"]
    if not isinstance(payload, dict) or set(payload) != {
        "domain", "run_id", "baseline_git_head", "candidate_path", "project_root",
        "evidence_hash", "gates", "evidence_current", "evidence_error",
        "owned_docs_paths", "input_digests", "checker_digest", "status",
    }:
        return False
    candidate = Path(collection.worktree_path).resolve()
    anchor = Path(project_root).resolve()
    try:
        anchor.relative_to(candidate)
        targets = docs_targets(run, candidate, anchor)
    except (EvidenceCollectionError, ValueError):
        return False
    if (
        payload["domain"] != "docs"
        or payload["run_id"] != run.run_id
        or payload["baseline_git_head"] != run.git_head
        or payload["candidate_path"] != collection.worktree_path
        or payload["project_root"] != str(anchor)
        or payload["evidence_hash"] != collection.content_hash
        or payload["owned_docs_paths"] != list(targets.owned)
        or payload["input_digests"] != [{"path": p, "sha256": d} for p, d in targets.input_digests]
        or payload["checker_digest"] != checker_digest()
        or payload["evidence_current"] is not True
        or payload["evidence_error"] is not None
        or payload["status"] != "PASS"
    ):
        return False
    if envelope["receipt_hash"] != _sha256_payload(
        {key: value for key, value in payload.items() if key != "status"}
    ):
        return False
    gates = payload["gates"]
    expected = tuple((n, list(c), str(r)) for n, c, r in gate_plan(candidate, anchor, targets))
    return (
        isinstance(gates, list)
        and len(gates) == len(expected)
        and all(
            isinstance(gate, dict)
            and set(gate) == {"name", "command", "cwd", "exit_code", "output_digest", "output_summary"}
            and (gate["name"], gate["command"], gate["cwd"]) == expected[index]
            and type(gate["exit_code"]) is int
            and gate["exit_code"] == 0
            and isinstance(gate["output_digest"], str)
            and bool(gate["output_digest"])
            and isinstance(gate["output_summary"], str)
            for index, gate in enumerate(gates)
        )
    )
