"""需求核对单（REQ-<项目号>-<年>_<月>_<序号>）模板与样例的结构检查。

驾驶舱代码冻结到 D09，这里先用测试内的小检查器把规则固定下来（设计稿：项目文件
plans/需求核对单_设计稿_20261022.md）；D09 后做 R01/R02 时把 ``check_checklist`` 和 ``content_fingerprint``
搬进驾驶舱，作为 ``pm req check`` 和确认时算指纹的依据，本文件的反例照搬过去。
"""

import hashlib
import re
from pathlib import Path

import pytest

_WS_ROOT = Path(__file__).resolve().parents[2]
_TPL_DIR = _WS_ROOT / "0100_PLC自动化" / "00_通用规范" / "项目文档模板"
TEMPLATE = _TPL_DIR / "12_需求核对单模板.md"
SAMPLE = _TPL_DIR / "样例" / "REQ-DJ-2026-011-2026_10_000_报警汇总与复位熄灭.md"

SECTIONS = (
    "## 1. 我理解的需求",
    "## 2. 做法要点",
    "## 3. 改动范围（只改这些）",
    "## 4. 不做什么",
    "## 5. 验收标准",
    "## 6. 安全区影响",
    "## 7. 待你回答的问题（0～3 个，每个一句话能答）",
    "## 8. 用户确认（由驾驶舱写入，AI 不填）",
    "## 9. 版本记录",
)
CONFIRM_SECTION = SECTIONS[7]
CONFIRM_PLACEHOLDER = "（由驾驶舱写入）"
MAX_QUESTIONS = 3
CONFIRM_ROWS = ("确认的版本", "内容指纹", "确认人 / 时间", "确认方式")
# AI 起草时只能写这两种状态；“已确认”只由驾驶舱按确认记录写入
DRAFT_STATES = ("待核对", "已作废")
_STATE_LINE = re.compile(r"^> 状态：.*$", re.MULTILINE)
# “怎么判”一栏必须落到其中之一：命令退出码、某项检查或测试通过、明确的现场项、带单位的数值
_JUDGEABLE = re.compile(
    r"退出码|(?:检查|测试|门禁|步骤)[^，。；]*通过|现场（用户|为 TRUE|计数为 \d|\d+(?:\.\d+)?\s*(?:ms|s|秒|毫秒|mm|%|A|V|Hz)"
)
_VAGUE_ONLY = re.compile(r"^(?:正常|能用|没问题|OK|ok|好用|符合要求|满足需求)[。.]?$")


def _section(text: str, heading: str) -> str:
    start = text.index(heading) + len(heading)
    following = [text.find(h, start) for h in SECTIONS if text.find(h, start) != -1]
    return text[start : min(following, default=len(text))]


def _table_rows(block: str) -> list[list[str]]:
    rows = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows[1:]  # 去掉表头


def check_checklist(text: str, *, template: bool = False) -> list[str]:
    """返回所有不合格项；空列表表示合格。``template`` 为真时允许占位符、不要求勾安全区。"""

    errors: list[str] = []
    title = re.search(
        r"^# 需求核对单 REQ-(?:<项目号>|[A-Z]{2,3}-\d{4}-\d{3})-(<年>_<月>_<序号>|\d{4}_\d{2}_\d{3})：\S", text, re.MULTILINE
    )
    if title is None:
        errors.append("标题须为“# 需求核对单 REQ-<项目号>-<年>_<月>_<序号>：<主题>”，序号三位、每月从 000 起")
    for field in ("项目", "提出", "版本", "状态", "起草", "用户原话"):
        if not re.search(rf"^> {field}：\S", text, re.MULTILINE):
            errors.append(f"头部缺少“{field}”")
    if not template:
        state = re.search(r"^> 状态：(.*)$", text, re.MULTILINE)
        if state is not None and state.group(1).strip() not in DRAFT_STATES:
            errors.append(f"状态只能写“待核对”或“已作废”，“已确认”只由驾驶舱写入：{state.group(1).strip()}")
        if not re.search(r"^> 版本：V\d+（上一版：", text, re.MULTILINE):
            errors.append("版本须写成 Vn（上一版：…）")
        if not re.search(r"^> 用户原话：「[^<」][^」]*」", text, re.MULTILINE):
            errors.append("用户原话须一字不改放在「」里")
        raised = re.search(r"^> 提出：([^<\s　][^　]*)　(\d{4})-(\d{2})-\d{2} \d{2}:\d{2}", text, re.MULTILINE)
        if raised is None:
            errors.append("“提出”须写提出人和提出时间（YYYY-MM-DD HH:MM）")
        elif title is not None:
            year, month, _seq = title.group(1).split("_")
            if (year, month) != (raised.group(2), raised.group(3)) or not 1 <= int(month) <= 12:
                errors.append(f"编号的年月 {year}_{month} 与提出时间 {raised.group(2)}-{raised.group(3)} 不一致")
    positions = [text.find(h) for h in SECTIONS]
    for heading, pos in zip(SECTIONS, positions):
        if pos == -1:
            errors.append(f"缺少一节：{heading}")
    if errors:
        return errors
    if positions != sorted(positions):
        errors.append("九节顺序不对")

    for row in _table_rows(_section(text, SECTIONS[4])):
        judge = row[-1] if row else ""
        if not template and (not _JUDGEABLE.search(judge) or _VAGUE_ONLY.match(judge)):
            errors.append(f"验收第 {row[0]} 条“怎么判”不是机器能判的，也没写明现场项：{judge or '（空）'}")

    ticks = re.findall(r"^- \[[xX]\] (不涉及|涉及)", _section(text, SECTIONS[5]), re.MULTILINE)
    if len(ticks) > 1 or (not template and len(ticks) != 1):
        errors.append("安全区影响须且只能勾一项")
    if ticks == ["不涉及"] and not re.search(r"^- \[[xX]\] 不涉及。理由：\S", _section(text, SECTIONS[5]), re.MULTILINE):
        errors.append("勾了“不涉及”须写理由")

    questions = [row for row in _table_rows(_section(text, SECTIONS[6])) if re.fullmatch(r"Q\d+", row[0])]
    if len(questions) > MAX_QUESTIONS:
        errors.append(f"待回答问题最多 {MAX_QUESTIONS} 个，现有 {len(questions)} 个")
    for row in questions:
        if not template and (len(row) < 3 or not row[1] or not row[2]):
            errors.append(f"问题 {row[0]} 须有问题和建议答案")

    for row in _table_rows(_section(text, SECTIONS[8])):
        if not template and (len(row) < 5 or not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", row[1]) or not row[2]):
            errors.append(f"版本记录 {row[0] if row else ''} 须写时间（YYYY-MM-DD HH:MM）和谁提的")

    confirm_rows = _table_rows(_section(text, CONFIRM_SECTION))
    if tuple(row[0] for row in confirm_rows) != CONFIRM_ROWS:
        errors.append("“用户确认”一节必须原样保留四行：" + "、".join(CONFIRM_ROWS))
    for row in confirm_rows:
        if row[-1] != CONFIRM_PLACEHOLDER:
            errors.append(f"“用户确认”一节只能由驾驶舱写入，AI 填了：{row[0]}")
    return errors


def content_fingerprint(text: str) -> str:
    """确认时记录的内容指纹：头部“状态”一行和第 8 节（都由驾驶舱写）不计入，其余改一个字指纹就变。

    换行统一成 LF、去掉 UTF-8 BOM：用户用记事本打开再保存，旧确认不会因此失效。
    """

    body = _STATE_LINE.sub("> 状态：", text.lstrip("\ufeff").replace("\r\n", "\n"))
    start = body.index(CONFIRM_SECTION)
    end = body.index(SECTIONS[8], start)
    # 第 8 节只有表格行由驾驶舱写；表格外多出的字照样计入，确认后再加内容指纹就变
    prose = "\n".join(line for line in body[start:end].splitlines() if not line.lstrip().startswith("|"))
    return hashlib.sha256((body[:start] + prose + body[end:]).encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def sample_text() -> str:
    return SAMPLE.read_text(encoding="utf-8", errors="replace")


def test_template_is_well_formed():
    assert check_checklist(TEMPLATE.read_text(encoding="utf-8", errors="replace"), template=True) == []


def test_sample_passes(sample_text):
    assert check_checklist(sample_text) == []


def test_sample_is_one_page(sample_text):
    body = re.sub(r"<!--.*?-->", "", sample_text, flags=re.DOTALL)
    assert len([line for line in body.splitlines() if line.strip()]) <= 70


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("退出码 0 |\n| 2 | 文档检查", "正常 |\n| 2 | 文档检查", "不是机器能判的"),
        ("用户原话：「", "用户原话：", "用户原话"),
        ("- [x] 不涉及", "- [ ] 不涉及", "只能勾一项"),
        ("- [ ] 涉及（急停", "- [x] 涉及（急停", "只能勾一项"),
        (
            "理由：报警灯只是指示，不进任何停机或联锁；复位只清报警灯的锁存，不复位急停和安全继电器（前提见 Q2）。",
            "理由：",
            "须写理由",
        ),
        ("| 确认人 / 时间 | （由驾驶舱写入） |", "| 确认人 / 时间 | baiyang 2026-10-22 |", "只能由驾驶舱写入"),
        ("## 6. 安全区影响", "## 6. 安全影响", "缺少一节"),
        ("> 版本：V1（上一版：无）", "> 版本：最新", "Vn"),
        ("> 状态：待核对", "> 状态：已确认", "只由驾驶舱写入"),
        ("越界检查通过", "看起来通过", "不是机器能判的"),
        ("REQ-DJ-2026-011-2026_10_000", "REQ-DJ-2026-011-2026_11_000", "不一致"),
        ("REQ-DJ-2026-011-2026_10_000", "REQ-DJ-2026-011-2026_10_1000", "序号三位"),
        ("REQ-DJ-2026-011-2026_10_000", "REQ-DJ-2026-011-001", "序号三位"),
        ("> 提出：baiyang（我方电气）　2026-10-22 09:00", "> 提出：2026-10-22", "提出人和提出时间"),
        ("| V1 | 2026-10-22 09:00 | baiyang |", "| V1 | 2026-10-22 | |", "谁提的"),
    ],
)
def test_mutations_are_rejected(sample_text, old, new, expected):
    assert old in sample_text
    errors = check_checklist(sample_text.replace(old, new, 1))
    assert any(expected in e for e in errors), errors


def test_more_than_three_questions_rejected(sample_text):
    extra = "| Q3 | 甲？ | 甲 | |\n| Q4 | 乙？ | 乙 | |\n"
    mutated = sample_text.replace("\n## 8. 用户确认", extra + "\n## 8. 用户确认", 1)
    assert any("最多 3 个" in e for e in check_checklist(mutated))


def test_question_without_suggested_answer_rejected(sample_text):
    mutated = sample_text.replace("| 继续亮，按复位才灭（锁存） |", "|  |", 1)
    assert any("建议答案" in e for e in check_checklist(mutated))


def test_fingerprint_ignores_confirm_area_only(sample_text):
    base = content_fingerprint(sample_text)
    filled = sample_text.replace("| 确认的版本 | （由驾驶舱写入） |", "| 确认的版本 | V1 |", 1)
    assert content_fingerprint(filled) == base
    assert content_fingerprint(sample_text.replace("16 路报警", "8 路报警", 1)) != base
    assert content_fingerprint(sample_text.replace("\n", "\r\n")) == base
    assert content_fingerprint("\ufeff" + sample_text) == base
    assert content_fingerprint(sample_text.replace("> 状态：待核对", "> 状态：已确认", 1)) == base
    assert (
        content_fingerprint(sample_text.replace("| V1 | 2026-10-22 09:00 | baiyang |", "| V1 | 2026-10-22 09:01 | baiyang |", 1))
        != base
    )
    # 确认区表格外塞进去的字不能躲开指纹
    smuggled = sample_text.replace("| 确认方式 | （由驾驶舱写入） |\n", "| 确认方式 | （由驾驶舱写入） |\n\n另加：报警改成 8 路。\n", 1)
    assert smuggled != sample_text and content_fingerprint(smuggled) != base


@pytest.mark.parametrize("keep", [0, 3])
def test_confirm_area_rows_cannot_be_deleted(sample_text, keep):
    rows = [f"| {name} | {CONFIRM_PLACEHOLDER} |\n" for name in CONFIRM_ROWS]
    mutated = sample_text
    for row in rows[keep:]:
        assert row in mutated
        mutated = mutated.replace(row, "", 1)
    assert any("原样保留四行" in e for e in check_checklist(mutated))
