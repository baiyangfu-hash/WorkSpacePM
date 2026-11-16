"""签 Decision 时核登记表字段，和登记表模型用同一个来源（DJ-2026-005 试车新债一）。

起因：CHG-SCPT-2026-650 给登记表模型 ``WorkspaceProjectMapping`` 加了 kind、status、status_before_delete，写登记表的
``WorkspaceRegistryService`` 按模型核；签 Decision 的 ``DecisionService._registered_project_root`` 却另抄了一份 6 个字段的
白名单，没跟上。登记表只要有一条带新栏，所有 Decision 都签不出来，``pm approve`` 停在半路（底稿
``plans/驾驶舱新债_DJ005试车_20261116/`` 新债一、二）。现在那份白名单从模型取，这里核：

1. 按模型逐字段造一条登记表（模型以后再加字段，这里自动带上），签一张规划 Decision 签得出来。
2. 用驾驶舱自己的登记服务改过登记表（新登记、删除、归档、重新启用）之后，照样签得出来。
3. 严格性不变：缺必填、多一个模型里没有的字段、顶层多一个键，都拒，拒绝原文点名哪一条、哪个字段。
4. 源码扫描：``auto_pm`` 和 ``scripts`` 里没有把登记表字段名列成一组的手抄名单（这一类写法回不来）；
   ``decision_service.py`` 里只有一处读登记表。
5. 新债二的出口：签 Decision 在半路失败（变更单已推到已批准、Decision 号已预留）后，把问题修好，用**同一条**用户原话
   凭据重跑就接着签完；换一条凭据被拒。这是 CHG-PLC-2026-022 在本单发版后的恢复办法，这里实跑核实。
"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args

import pytest

from auto_pm.application.core.pm_facade_service import PmFacadeError
from auto_pm.application.core.workspace_registry_service import WorkspaceRegistryService
from auto_pm.contracts.workspace_context import WorkspaceProjectMapping, WorkspaceRegistry
from auto_pm.domain.change.decision_service import DecisionService, DecisionValidationError
from tests.core.test_pm_pending_scope_card import EVIDENCE, _Env, _env
from tests.core.test_pm_run_e2e import PROJECT_ID
from tests.core.test_workspace_registry_service import _anchor

PROJECT = Path(__file__).resolve().parents[2]
REGISTRY = Path("SYS-2026-001_WorkspaceGovernance") / "workspace_registry.json"
DELETED_PROJECT = "SW-GONE-001"
OTHER_EVIDENCE = "user-confirmation:2026-11-16T02:22:56Z"


def _rewrite(root: Path, change: Callable[[dict[str, Any]], None]) -> None:
    path = root / REGISTRY
    payload = json.loads(path.read_text(encoding="utf-8"))
    change(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _entry(payload: dict[str, Any], project_id: str = PROJECT_ID) -> dict[str, Any]:
    (entry,) = [item for item in payload["projects"] if item["project_id"] == project_id]
    assert isinstance(entry, dict)
    return entry


def every_field(entry: dict[str, Any]) -> dict[str, Any]:
    """The entry with every field the model has; a choice field gets its first non-empty value."""

    full = dict(entry)
    for name, field in WorkspaceProjectMapping.model_fields.items():
        if name not in full:
            choices = [value for value in get_args(field.annotation) if value]
            full[name] = choices[0] if choices else ""
    return full


def _signed(env: _Env, request_id: str) -> str:
    env.draft(request_id)
    card = env.submit(request_id).card
    result = env.approve(request_id, card.plan_hash)
    assert env.chg_status(card.change_id) == "approved"
    assert (env.root / ".auto-pm" / "decisions" / f"{result.decision_id}.json").is_file()
    assert env.store.get_mission(result.mission_id).authority.decision_id == result.decision_id
    return result.decision_id


def _decision_files(env: _Env) -> list[Path]:
    return sorted((env.root / ".auto-pm" / "decisions").glob("*.json"))


# ---- 1、2：带新栏的登记表照样签得出 Decision -------------------------------------------------------------------


def test_a_registry_with_every_model_field_signs_a_decision(tmp_path: Path) -> None:
    env = _env(tmp_path)

    def widen(payload: dict[str, Any]) -> None:
        payload["projects"] = [every_field(item) for item in payload["projects"]]
        payload["projects"].append(
            {"project_id": DELETED_PROJECT, "project_root": DELETED_PROJECT, "development_root": DELETED_PROJECT,
             "kind": "tool", "status": "deleted", "status_before_delete": "paused"}
        )

    _rewrite(env.root, widen)
    entry = _entry(json.loads((env.root / REGISTRY).read_text(encoding="utf-8")))
    assert set(entry) == set(WorkspaceProjectMapping.model_fields)

    _signed(env, "REQ-REG-FIELDS-001")


def test_the_cockpits_own_registry_writes_still_let_a_decision_be_signed(tmp_path: Path) -> None:
    """The user's register / delete / restore / archive / reactivate leave the new fields in the file; signing must not care."""

    env = _env(tmp_path)
    service = WorkspaceRegistryService(env.root)
    _anchor(env.root / "SW-NEW-001", "SW-NEW-001")
    service.register("SW-NEW-001", "SW-NEW-001")  # no --kind/--status: the two keys are written all the same
    assert {"kind", "status"} <= set(_entry(json.loads((env.root / REGISTRY).read_text(encoding="utf-8")), "SW-NEW-001"))
    assert service.mark_deleted("SW-NEW-001") is not None
    assert service.mark_restored("SW-NEW-001") is not None
    assert service.mark_deleted("SW-NEW-001") is not None  # deleted again: status_before_delete is in the file when signing
    assert service.set_status(PROJECT_ID, "archived", only_from=("active",)) is not None
    assert service.set_status(PROJECT_ID, "active", only_from=("archived",)) is not None

    _signed(env, "REQ-REG-FIELDS-002")


# ---- 3：严格性不变，拒绝原文点名 -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "said"),
    [
        (lambda payload: _entry(payload).update(bogus="x"), f"{PROJECT_ID} 缺 无，多出 bogus"),
        (lambda payload: _entry(payload).pop("development_root"), f"{PROJECT_ID} 缺 development_root，多出 无"),
        (lambda payload: payload.update(extra=[]), "顶层字段不完整或未知"),
        (lambda payload: payload.pop("schema_version"), "顶层字段不完整或未知"),
        (lambda payload: _entry(payload).update(kind="not-a-kind"), "schema 无效"),
    ],
    ids=["unknown-field", "missing-required", "unknown-top-level", "missing-top-level", "bad-value"],
)
def test_the_check_stays_strict_and_names_what_is_wrong(
    tmp_path: Path, change: Callable[[dict[str, Any]], None], said: str
) -> None:
    env = _env(tmp_path)
    _rewrite(env.root, change)
    with pytest.raises(DecisionValidationError, match="Workspace Registry") as caught:
        DecisionService(env.root)._registered_project_root(PROJECT_ID)
    assert said in str(caught.value)


def test_the_allowed_fields_are_the_models_fields() -> None:
    from auto_pm.domain.change import decision_service as module

    assert module._REGISTRY_PROJECT_FIELDS == set(WorkspaceProjectMapping.model_fields)
    assert module._REGISTRY_TOP_FIELDS == set(WorkspaceRegistry.model_fields)
    assert module._REGISTRY_REQUIRED_PROJECT_FIELDS == {
        name for name, field in WorkspaceProjectMapping.model_fields.items() if field.is_required()
    }


# ---- 4：手抄的字段名单回不来 ---------------------------------------------------------------------------------------

FIELDS = frozenset(WorkspaceProjectMapping.model_fields)


def copied_field_groups(source: str, filename: str = "<memory>") -> list[int]:
    """Lines of a set/list/tuple literal naming three or more registry fields: a second copy of the model's field list."""

    lines: list[int] = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        if isinstance(node, ast.Set | ast.List | ast.Tuple):
            named = {item.value for item in node.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)}
            if len(named & FIELDS) >= 3:
                lines.append(node.lineno)
    return lines


def test_no_hand_copied_registry_field_list_in_the_package_or_the_scripts() -> None:
    found = {
        str(path.relative_to(PROJECT)): lines
        for folder in ("auto_pm", "scripts")
        for path in sorted((PROJECT / folder).rglob("*.py"))
        if (lines := copied_field_groups(path.read_text(encoding="utf-8-sig"), str(path)))
    }
    assert found == {}, f"登记表的字段只认 contracts.workspace_context 的模型，别再抄一份：{found}"


@pytest.mark.parametrize(
    "snippet",
    [
        'required = {"project_id", "project_root", "development_root"}',
        'allowed = ["control_project_id", "control_pm_session", "runtime_root", "kind"]',
        'KEYS = ("project_id", "kind", "status")',
    ],
)
def test_mutation_each_copied_list_is_caught(snippet: str) -> None:
    assert copied_field_groups(snippet) == [1]


def test_label_pairs_are_not_a_copied_list() -> None:
    source = 'for label, raw in (("project_root", a), ("development_root", b)):\n    pass\n'
    assert copied_field_groups(source) == []


def test_the_decision_service_reads_the_registry_in_one_place() -> None:
    source = (PROJECT / "auto_pm" / "domain" / "change" / "decision_service.py").read_text(encoding="utf-8")
    assert source.count('"workspace_registry.json"') == 1


# ---- 5：新债二的出口：半路失败后用同一条凭据重跑能续做 ------------------------------------------------------------


def test_a_decision_that_failed_half_way_resumes_with_the_same_words_only(tmp_path: Path) -> None:
    env = _env(tmp_path)
    request_id = "REQ-REG-RESUME-001"
    env.draft(request_id)
    card = env.submit(request_id).card
    _rewrite(env.root, lambda payload: _entry(payload).update(bogus="x"))  # stands for what broke on DJ-2026-005

    with pytest.raises(PmFacadeError, match="多出 bogus"):
        env.approve(request_id, card.plan_hash)
    # The half-written state CHG-PLC-2026-022 is in: CHG approved, Decision number reserved, no Decision, no Mission.
    assert env.chg_status(card.change_id) == "approved"
    assert env.count("planning_draft_decision_bindings") == 1
    assert _decision_files(env) == []
    assert env.count("mission_items") == 0

    _rewrite(env.root, lambda payload: _entry(payload).pop("bogus"))
    with pytest.raises(PmFacadeError, match="不同批准"):
        env.approve(request_id, card.plan_hash, evidence=OTHER_EVIDENCE)
    assert _decision_files(env) == []
    assert env.count("mission_items") == 0

    result = env.approve(request_id, card.plan_hash, evidence=EVIDENCE)
    assert [path.stem for path in _decision_files(env)] == [result.decision_id]
    decision = env.facade._decisions.get_decision(result.decision_id)
    assert decision.metadata["planning_approval"]["approval_evidence_ref"] == EVIDENCE
    assert env.store.get_mission(result.mission_id).authority.decision_id == result.decision_id
    assert env.store.get_work(result.work_id).subject_project_id == PROJECT_ID
    assert env.count("planning_draft_decision_bindings") == 1
    assert env.chain_is_intact()
