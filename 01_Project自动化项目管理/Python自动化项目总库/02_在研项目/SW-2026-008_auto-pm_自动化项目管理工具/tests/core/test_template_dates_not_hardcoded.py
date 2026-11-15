"""新建项目里的日期都是生成那天，模板里不写死日期（D-387）。

旧的 PLC 标准项目模板把立项表 ``created_date`` 写死成 2026-08-23，另有十几个文件的 ``created``、
立项日期、台账更新日期也写死；用 ``now()`` 的 16 处在 copier 去掉 ``now`` 以后会退回写死的
2026-08-23。这里用产品自己的 ``TemplateService`` 真生成一遍，逐个文件找日期：除了下面白名单里
标准功能块自带的设计历史，只许出现生成当天。摄取 AutoShop 工程生成的文档同样核一遍。
只读本项目 templates/ 下的模板，生成结果写在临时目录。
"""

from __future__ import annotations

import csv
import re
import warnings
from datetime import date
from pathlib import Path

from auto_pm.application.core.template_service import TemplateService
from auto_pm.application.plc.ingest_service import PlcIngestService

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
DATE = re.compile(r"\b20\d{2}-[01]\d-[0-3]\d\b")

# 标准功能块从基准项目带过来的设计历史（谁、哪一版、依据什么规范），不是新项目的日期，保留原样。
BLOCK_HISTORY = {
    "02_PLC程序/PLC_ST/05_公共报警/PRD/变更记录_CHG-FB2001-CommonAlarm.md": {
        "2026-05-17",
        "2026-04-27",
    },
    "02_PLC程序/PLC_ST/05_公共报警/PRD/详细设计说明书_DSN-FB2001-CommonAlarm.md": {
        "2026-05-18",
        "2026-05-04",
    },
    "02_PLC程序/PLC_ST/05_公共报警/PRD/接口文档_IFC-FB2001-CommonAlarm.md": {"2026-05-17"},
    "02_PLC程序/PLC_ST/01_外部设备交互/PRD/变更记录_CHG-FB3001-ExternalInteraction.md": {
        "2026-08-22"
    },
}


def _today_set(before: date, after: date) -> set[str]:
    return {before.isoformat(), after.isoformat()}


def test_templates_do_not_use_deprecated_now() -> None:
    """``now()`` 会被 copier 去掉，去掉后退回写死的日期；统一用 ``'%Y-%m-%d' | strftime``。"""
    offenders = [
        str(p.relative_to(TEMPLATES_DIR))
        for p in TEMPLATES_DIR.rglob("*.jinja")
        if "now()" in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert offenders == []


def test_plc_standard_project_dates_are_generation_day(tmp_path: Path) -> None:
    dest = tmp_path / "DJ-2026-903"
    before = date.today()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        TemplateService(str(TEMPLATES_DIR)).copy_template(
            "plc-standard-project",
            str(dest),
            {"project_id": "DJ-2026-903", "project_name": "日期核对"},
        )
    after = date.today()
    today = _today_set(before, after)

    assert not [w for w in caught if "'now' will be removed" in str(w.message)]

    wrong: list[str] = []
    seen_today = 0
    for path in sorted(dest.rglob("*")):
        if not path.is_file() or path.suffix not in {
            ".md",
            ".scl",
            ".yml",
            ".yaml",
            ".csv",
            ".json",
        }:
            continue
        rel = path.relative_to(dest).as_posix()
        allowed = today | BLOCK_HISTORY.get(rel, set())
        for found in DATE.findall(path.read_text(encoding="utf-8", errors="replace")):
            if found in today:
                seen_today += 1
            elif found not in allowed:
                wrong.append(f"{rel}: {found}")
    assert wrong == []
    assert seen_today > 0

    proj = dest / "00_项目管理" / "01_立项与需求" / "003_DJ-2026-903_项目立项表_PROJ.md"
    head = proj.read_text(encoding="utf-8")
    assert any(f"created_date: {d}" in head for d in today), head[:400]


def test_ingested_docs_are_dated_ingest_day(tmp_path: Path) -> None:
    src = tmp_path / "src_autoshop" / "2_PLC"
    src.mkdir(parents=True)
    with open(src / "AlarmTable.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Type", "Address", "Comment"])
        writer.writerow(["g_bEStopAlarm", "BOOL", "M100.0", "急停报警触发"])
        writer.writerow(["X_Start", "BOOL", "X0", "启动按钮"])
    target = tmp_path / "0100_PLC自动化" / "DJ-TEST-387"
    target.mkdir(parents=True)

    before = date.today()
    res = PlcIngestService(workspace_root=str(tmp_path)).ingest_autoshop_project(
        source_dir=str(tmp_path / "src_autoshop"),
        target_project_path=str(target),
        project_id="DJ-TEST-387",
        project_name="日期核对",
    )
    today = _today_set(before, date.today())
    assert res.success is True

    docs = sorted((target / "02_PLC程序" / "程序文档").glob("*.md"))
    assert docs
    for doc in docs:
        found = set(DATE.findall(doc.read_text(encoding="utf-8")))
        assert found and found <= today, (doc.name, found)
