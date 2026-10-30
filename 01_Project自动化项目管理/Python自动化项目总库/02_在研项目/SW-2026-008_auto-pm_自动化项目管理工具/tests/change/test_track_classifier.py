"""ChangeTrackClassifier 单元测试"""

from __future__ import annotations

from auto_pm.domain.change.track_classifier import ChangeTrack, ChangeTrackClassifier


def test_classify_quick_track() -> None:
    """测试常规缺陷/优化/文档类的局部修改判定为 Quick Track"""
    track = ChangeTrackClassifier.classify(
        domain="PLC",
        nature="DEF",
        scope="LOCAL",
        changed_files=["auto_pm/core/project_service.py"],
    )
    assert track == ChangeTrack.QUICK

    track_opt = ChangeTrackClassifier.classify(
        domain="DOCU",
        nature="OPT",
        scope=["MODULE"],
    )
    assert track_opt == ChangeTrack.QUICK


def test_classify_full_track_by_nature() -> None:
    """测试新建需求 (REQ) 或紧急变更 (EMRG) 强制走 Full Track"""
    req_track = ChangeTrackClassifier.classify(
        domain="PLC",
        nature="REQ",
        scope="LOCAL",
    )
    assert req_track == ChangeTrack.FULL

    emrg_track = ChangeTrackClassifier.classify(
        domain="SCPT",
        nature="EMRG",
        scope="LOCAL",
    )
    assert emrg_track == ChangeTrack.FULL


def test_classify_full_track_by_scope() -> None:
    """测试系统级/跨领域/安全影响强制走 Full Track"""
    sys_track = ChangeTrackClassifier.classify(
        domain="PLC",
        nature="OPT",
        scope="SYSTEM",
    )
    assert sys_track == ChangeTrack.FULL

    cross_track = ChangeTrackClassifier.classify(
        domain="HMI",
        nature="DEF",
        scope=["LOCAL", "CROSS"],
    )
    assert cross_track == ChangeTrack.FULL


def test_classify_full_track_by_sensitive_path() -> None:
    """测试修改技能文件或约束定义强制走 Full Track"""
    skill_track = ChangeTrackClassifier.classify(
        domain="SCPT",
        nature="OPT",
        scope="LOCAL",
        changed_files=[".trae/skills/fullstack-engineer/SKILL.md"],
    )
    assert skill_track == ChangeTrack.FULL

    cst_track = ChangeTrackClassifier.classify(
        domain="SCPT",
        nature="DEF",
        scope="MODULE",
        changed_files=["auto_pm/constraint/definitions/skill_change_requires_chg.yaml"],
    )
    assert cst_track == ChangeTrack.FULL
