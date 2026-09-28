"""Implementation card artifacts and exact, read-only authority checks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, StrictUndefined
from pydantic import ValidationError

from auto_pm.contracts.continuity import CheckpointItem, RunState, WorkState
from auto_pm.contracts.implementation_card import CardState, ImplementationCard
from auto_pm.domain.change.decision_service import DecisionError, DecisionService
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    clean_git_environment,
    require_governed_worktree,
    require_safe_workspace_path,
)


class ImplementationCardError(RuntimeError):
    """A card or a canonical fact is incomplete, stale, or mismatched."""


class ImplementationCardService:
    """Store card files only; Continuity and Decision remain external truth."""

    def __init__(self, control_root: str | Path) -> None:
        self.root = Path(control_root).resolve(strict=True)
        self.directory = self.root / ".auto-pm" / "implementation-cards"

    def _target(self, card_id: str) -> Path:
        if re.fullmatch(r"[A-Z][A-Z0-9-]{2,127}", card_id) is None:
            raise ImplementationCardError("invalid card ID")
        return self.directory / f"{card_id}.json"

    def _read(self, card_id: str) -> tuple[ImplementationCard, bytes]:
        target = self._target(card_id)
        try:
            raw = target.read_bytes()
            text = raw.decode("utf-8", errors="replace")
            if "\ufffd" in text:
                raise ImplementationCardError("card is not valid UTF-8")
            def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
                result: dict[str, object] = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError(f"duplicate card field: {key}")
                    result[key] = value
                return result

            card = ImplementationCard.model_validate(json.loads(text, object_pairs_hook=unique_pairs))
        except (OSError, ValidationError, ValueError) as error:
            raise ImplementationCardError(f"card cannot be read: {card_id}: {error}") from error
        if card.card_id != card_id:
            raise ImplementationCardError("card filename and payload identity differ")
        return card, raw

    def load(self, card_id: str) -> ImplementationCard:
        """Read and parse without creating state or directories."""
        return self._read(card_id)[0]

    def validate(self, card_id: str) -> ImplementationCard:
        """Read-only contract, WBS, Git and governed candidate validation."""
        card = self.load(card_id)
        try:
            self._canonical(card, require_base_head=card.state in {
                CardState.DRAFT, CardState.REVIEWED, CardState.APPROVED,
            })
        except (DecisionError, ContinuityStoreError, ControlRootGuardError) as error:
            raise ImplementationCardError(f"canonical authority unavailable: {error}") from error
        return card

    def _validate_external(self, card: ImplementationCard) -> Path:
        card.require_complete()
        try:
            wbs_text = ""
            for reference in card.source_refs:
                kind, relative = reference.split(":", 1)
                target = require_safe_workspace_path(self.root, relative, label="card source_ref")
                metadata = target.stat()
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                    raise ImplementationCardError(f"source ref is not a unique regular file: {relative}")
                raw = target.read_bytes()
                text = raw.decode("utf-8", errors="replace")
                if "\ufffd" in text:
                    raise ImplementationCardError(f"source ref is not valid UTF-8: {relative}")
                if kind == "WBS":
                    self._git(self.root, "ls-files", "--error-unmatch", "--", relative)
                    if self._git(self.root, "status", "--porcelain", "--", relative):
                        raise ImplementationCardError("canonical WBS source has uncommitted changes")
                    wbs_text = text
            def exact_id(value: str) -> bool:
                return re.search(rf"(?<![A-Za-z0-9_-]){re.escape(value)}(?![A-Za-z0-9_-])", wbs_text) is not None

            if not exact_id(card.wbs_item_id) or not exact_id(card.milestone_id):
                raise ImplementationCardError("canonical WBS item or milestone is missing")
            self._git(self.root, "cat-file", "-e", f"{card.base_commit}^{{commit}}")
            worktree = require_governed_worktree(self.root, card.worktree_path)
            if worktree == self.root:
                raise ImplementationCardError("candidate policy requires an isolated worktree")
            head = self._git(worktree, "rev-parse", "HEAD")
            self._git(worktree, "merge-base", "--is-ancestor", card.base_commit, head)
            if card.state in {CardState.DRAFT, CardState.REVIEWED, CardState.APPROVED} and head != card.base_commit:
                raise ImplementationCardError("pre-dispatch candidate HEAD differs from immutable base")
            for gate in card.gates:
                cwd = require_safe_workspace_path(worktree, gate.cwd, label="gate cwd")
                if not cwd.is_dir():
                    raise ImplementationCardError(f"gate cwd is missing: {gate.cwd}")
            return worktree
        except (ControlRootGuardError, OSError) as error:
            raise ImplementationCardError(f"card source/Git/worktree validation failed: {error}") from error

    def _write(self, card: ImplementationCard, previous: bytes | None) -> Path:
        target = self._target(card.card_id)
        self.directory.mkdir(parents=True, exist_ok=True)
        if previous is None and target.exists():
            raise ImplementationCardError("card already exists")
        if previous is not None and (not target.is_file() or target.read_bytes() != previous):
            raise ImplementationCardError("card bytes changed during transition")
        payload = (card.model_dump_json(indent=2) + "\n").encode("utf-8")
        fd, name = tempfile.mkstemp(prefix=f".{card.card_id}.", dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if previous is not None and target.read_bytes() != previous:
                raise ImplementationCardError("card bytes changed during transition")
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return target

    def create(self, card: ImplementationCard) -> tuple[Path, Path]:
        """Create JSON and a template-backed review artifact, never execution objects."""
        if card.state is not CardState.DRAFT:
            raise ImplementationCardError("create requires DRAFT")
        target = self._target(card.card_id)
        markdown = target.with_suffix(".md")
        if target.exists() or markdown.exists():
            raise ImplementationCardError("card artifacts already exist")
        template_path = Path(__file__).resolve().parents[2] / "templates" / "governance" / "implementation_card.md.jinja"
        source = template_path.read_text(encoding="utf-8", errors="replace")
        rendered = Environment(undefined=StrictUndefined, autoescape=False).from_string(source).render(card=card)
        self._write(card, None)
        markdown.write_text(rendered, encoding="utf-8", errors="replace")
        return target, markdown

    def approve(self, card_id: str, *, approver: str, approval_evidence: str) -> ImplementationCard:
        """Record supplied external user approval; an agent cannot sign itself."""
        card, raw = self._read(card_id)
        if card.state not in {CardState.DRAFT, CardState.REVIEWED}:
            raise ImplementationCardError("approval requires DRAFT or REVIEWED card")
        if not approver.strip() or not approval_evidence.strip() or "TODO" in approval_evidence:
            raise ImplementationCardError("external user approval evidence is required")
        if any(token in approver.casefold() for token in ("agent", "model", "codex", "gpt", "assistant")):
            raise ImplementationCardError("model/agent cannot self-approve")
        self._validate_external(card)
        if approval_evidence != card.evidence.decision_id:
            raise ImplementationCardError("approval evidence must reference the card's canonical Decision")
        try:
            decision = DecisionService(self.root).get_decision(approval_evidence)
        except DecisionError as error:
            raise ImplementationCardError(f"external approval evidence unavailable: {error}") from error
        if (
            decision.project_id != card.project_id
            or decision.approver != approver
            or decision.decision_conclusion not in {"approved", "conditionally_approved"}
            or set(card.authorized_paths) != set(decision.approved_files)
        ):
            raise ImplementationCardError("external Decision does not approve this card scope")
        if card.state is CardState.DRAFT:
            card = card.transition(CardState.REVIEWED)
        result = card.model_copy(update={"approval_by": approver, "approval_evidence": approval_evidence})
        result = result.transition(CardState.APPROVED)
        self._write(result, raw)
        return result

    @staticmethod
    def _git(worktree: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(worktree), *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False, env=clean_git_environment(),
        )
        if result.returncode or result.stderr.strip() or "\ufffd" in result.stdout:
            raise ImplementationCardError("Git fact collection failed")
        return result.stdout.strip()

    def _canonical(
        self, card: ImplementationCard, *, require_base_head: bool = True,
    ) -> tuple[Path, ContinuityStore]:
        worktree = self._validate_external(card)
        decision = DecisionService(self.root).get_decision(card.evidence.decision_id)
        store = ContinuityStore(self.root)
        work = store.get_work(card.evidence.work_id)
        run = store.get_run(card.evidence.run_id)
        authorized = set(card.authorized_paths)
        if (
            decision.project_id != card.project_id
            or decision.decision_conclusion not in {"approved", "conditionally_approved"}
            or work.subject_project_id != card.project_id
            or work.authorization_ref != decision.decision_id
            or run.work_id != work.work_id
            or authorized != set(run.owned_paths)
            or authorized != set(work.scope_paths)
            or authorized != set(decision.approved_files)
            or run.git_head != card.base_commit
        ):
            raise ImplementationCardError("Decision/Work/Run project, base or scope mismatch")
        if worktree == self.root or worktree != Path(run.worktree_path).resolve(strict=True):
            raise ImplementationCardError("worktree identity mismatch")
        if require_base_head and self._git(worktree, "rev-parse", "HEAD") != card.base_commit:
            raise ImplementationCardError("candidate has drifted from immutable base")
        return worktree, store

    def dispatch(self, card_id: str) -> dict[str, object]:
        """Emit a bounded package after exact checks; create no Work or Run."""
        card, raw = self._read(card_id)
        if card.state is not CardState.APPROVED or not card.approval_evidence:
            raise ImplementationCardError("dispatch requires external approval")
        try:
            worktree, store = self._canonical(card)
        except (DecisionError, ContinuityStoreError, ControlRootGuardError) as error:
            raise ImplementationCardError(f"canonical authority unavailable: {error}") from error
        work = store.get_work(card.evidence.work_id)
        run = store.get_run(card.evidence.run_id)
        lease = store.get_lease(run.run_id)
        deadline = datetime.fromisoformat(card.stop_lines.deadline_utc.replace("Z", "+00:00"))
        if work.state is not WorkState.IN_PROGRESS or run.state is not RunState.RUNNING:
            raise ImplementationCardError("Work/Run are not current execution states")
        if deadline <= datetime.now(UTC):
            raise ImplementationCardError("execution deadline has passed")
        if len(store.list_runs(work.work_id, include_terminal=True)) > card.stop_lines.max_runs:
            raise ImplementationCardError("max_runs exceeded")
        if datetime.fromisoformat(lease.expires_at) <= datetime.now(UTC) or lease.owner_id != run.executor_id:
            raise ImplementationCardError("lease is expired or mismatched")
        if self._git(worktree, "status", "--porcelain"):
            raise ImplementationCardError("candidate has undeclared dirty files")
        result = card.transition(CardState.DISPATCHED)
        self._write(result, raw)
        return {"schema_version": "implementation_dispatch.v1", "card_id": card_id,
                "project_id": card.project_id, "base_commit": card.base_commit,
                "worktree_path": str(worktree), "owned_paths": card.owned_paths,
                "commit_evidence_paths": card.commit_evidence_paths,
                "authorized_paths": card.authorized_paths,
                "gates": [gate.model_dump() for gate in card.gates],
                "gate_evidence_keys": [self._gate_evidence_key(gate.model_dump_json()) for gate in card.gates],
                "stop_lines": card.stop_lines.model_dump(), "evidence": card.evidence.model_dump(),
                "boundaries": card.boundaries.model_dump()}

    @staticmethod
    def _gate_evidence_key(gate_json: str) -> str:
        return "gate:" + hashlib.sha256(gate_json.encode("utf-8")).hexdigest() + ":exit="

    @classmethod
    def validate_checkpoint_evidence(
        cls, card: ImplementationCard, checkpoint: CheckpointItem, worktree: Path,
    ) -> None:
        """Validate exact gate receipts, repair budget and every owned current byte."""
        expected_gates = {cls._gate_evidence_key(gate.model_dump_json()) + str(gate.expected_exit_code)
                          for gate in card.gates}
        observed_gates = [item for item in checkpoint.evidence if item.startswith("gate:")]
        if len(observed_gates) != len(expected_gates) or set(observed_gates) != expected_gates:
            raise ImplementationCardError("Checkpoint gate receipts are missing, stale or ambiguous")
        healing = [item for item in checkpoint.evidence if item.startswith("healing_attempts:")]
        if len(healing) != 1 or re.fullmatch(r"healing_attempts:[0-9]+", healing[0]) is None:
            raise ImplementationCardError("Checkpoint healing count missing or ambiguous")
        if int(healing[0].split(":", 1)[1]) > card.stop_lines.max_healing_attempts:
            raise ImplementationCardError("Checkpoint exceeds healing budget")
        hashes: dict[str, str] = {}
        for item in checkpoint.evidence:
            if item.startswith("sha256:"):
                parts = item.split(":", 2)
                if len(parts) != 3:
                    raise ImplementationCardError("malformed Checkpoint byte evidence")
                _, path, digest = parts
                if path in hashes or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                    raise ImplementationCardError("ambiguous or invalid Checkpoint byte evidence")
                hashes[path] = digest
        if not hashes or set(hashes) != set(card.authorized_paths):
            raise ImplementationCardError("Checkpoint lacks current-byte coverage")
        for path, digest in hashes.items():
            candidate = worktree / path
            if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != digest:
                raise ImplementationCardError(f"Checkpoint byte evidence stale: {path}")

    def verify(self, card_id: str, *, checkpoint_id: str, final_commit: str) -> ImplementationCard:
        """Require terminal canonical evidence and current bytes, without release actions."""
        card, raw = self._read(card_id)
        if card.state is not CardState.DISPATCHED:
            raise ImplementationCardError("verify requires DISPATCHED card")
        if re.fullmatch(r"[A-Z][A-Z0-9-]{2,127}", checkpoint_id) is None or re.fullmatch(r"[0-9a-f]{40}", final_commit) is None:
            raise ImplementationCardError("explicit Checkpoint and final commit identities are invalid")
        if card.evidence.checkpoint_id not in {"TODO", checkpoint_id} or card.evidence.final_commit not in {"TODO", final_commit}:
            raise ImplementationCardError("supplied terminal identities conflict with card evidence")
        evidence = card.evidence.model_copy(update={"checkpoint_id": checkpoint_id, "final_commit": final_commit})
        card = ImplementationCard.model_validate(card.model_copy(update={"evidence": evidence}).model_dump())
        card.require_terminal_evidence()
        self._validate_external(card)
        # A committed candidate has a different HEAD; verify identity without the base-HEAD gate.
        try:
            decision = DecisionService(self.root).get_decision(card.evidence.decision_id)
            store = ContinuityStore(self.root)
            work = store.get_work(card.evidence.work_id)
            run = store.get_run(card.evidence.run_id)
            checkpoint = store.get_checkpoint(card.evidence.checkpoint_id)
            worktree = require_governed_worktree(self.root, card.worktree_path)
        except (DecisionError, ContinuityStoreError, ControlRootGuardError) as error:
            raise ImplementationCardError(f"terminal authority unavailable: {error}") from error
        final_commit = card.evidence.final_commit
        authorized = set(card.authorized_paths)
        if (
            decision.project_id != card.project_id or work.subject_project_id != card.project_id
            or work.authorization_ref != decision.decision_id or run.work_id != work.work_id
            or worktree == self.root or Path(run.worktree_path).resolve(strict=True) != worktree
            or run.git_head != card.base_commit or set(run.owned_paths) != authorized
            or set(work.scope_paths) != authorized
            or set(decision.approved_files) != authorized
            or checkpoint.run_id != run.run_id or store.latest_checkpoint(run.run_id) != checkpoint
            or checkpoint.git_head not in {card.base_commit, final_commit}
            or not set(checkpoint.dirty_paths).issubset(authorized)
            or len(store.list_runs(work.work_id, include_terminal=True)) > card.stop_lines.max_runs
            or run.state is not RunState.SUCCEEDED
            or work.state not in {WorkState.VERIFYING, WorkState.ACCEPTED}
            or re.fullmatch(r"[0-9a-f]{40}", final_commit) is None
            or self._git(worktree, "rev-parse", "HEAD") != final_commit
            or self._git(worktree, "merge-base", card.base_commit, final_commit) != card.base_commit
            or self._git(worktree, "status", "--porcelain")
        ):
            raise ImplementationCardError("terminal Decision/Work/Run/Checkpoint/commit evidence is stale")
        changed = {
            path for path in self._git(worktree, "diff", "--name-only", "-z", card.base_commit, final_commit).split("\x00")
            if path
        }
        if changed != authorized:
            raise ImplementationCardError("final commit diff must exactly match authorized paths")
        self.validate_checkpoint_evidence(card, checkpoint, worktree)
        result = card.transition(CardState.VERIFYING).transition(CardState.ACCEPTED).transition(CardState.CLOSED)
        self._write(result, raw)
        return result
