import os
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
WORKSPACE_ROOT = SCRIPT_DIR.parent.parent
BASE = WORKSPACE_ROOT / "0100_PLC自动化"

TARGETS = [
    "01_SharedLibraries/SysLib/actuator/FB_1013_NinetyDegreeTransfer.scl",
    "DJ-2026-005/02_PLC程序/通用ST程序及变量表/conveyor/FB_1002_SingleLayerConveyor_BufferFraming.scl",
    "DJ-2026-005/02_PLC程序/通用ST程序及变量表/pickplace/FB_1003_PickPlace_BufferFraming.scl",
    "01_SharedLibraries/SysLib/types/ST_ServoAxis.scl",
    "DJ-2026-005/02_PLC程序/通用ST程序及变量表/feeder/FB_1004_GlueMachineFeeder_BufferFraming.scl",
    "DJ-2026-000/OB1/OB1.scl",
    "DJ-2026-005/02_PLC程序/通用ST程序及变量表/OB1/OB1.scl",
    "DJ-2026-000/FB100/FB_ValveControl.scl",
]

VAR_COMMENT_RE = re.compile(
    r"^(\s*)(\w+\s*:\s*(?:BOOL|INT|DINT|REAL|TIME|WORD|BYTE|STRING)\s*;)\s*\(\*\s*(.*?)\s*\*\)",
    re.MULTILINE,
)

stats = {"，": 0, "。": 0, "var_comment": 0}

for rel_path in TARGETS:
    file_path = BASE / rel_path
    if not file_path.exists():
        print(f"  SKIP (not found): {rel_path}")
        continue

    content = file_path.read_text(encoding="utf-8")
    original = content

    content, n1 = re.subn(r"，", ",", content)
    content, n2 = re.subn(r"。", ".", content)
    stats["，"] += n1
    stats["。"] += n2

    if "FB_1013_NinetyDegreeTransfer" in str(file_path):
        content, n3 = VAR_COMMENT_RE.subn(r"\1\2 // \3", content)
        stats["var_comment"] += n3

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        changes = []
        if n1:
            changes.append(f"，×{n1}")
        if n2:
            changes.append(f"。×{n2}")
        if "FB_1013" in str(file_path) and n3:
            changes.append(f"(* *)→// ×{n3}")
        print(f"  FIXED: {rel_path} ({', '.join(changes)})")
    else:
        print(f"  OK (no changes): {rel_path}")

print(f"\n=== Summary ===")
print(f"  Chinese comma ， → , : {stats['，']} replacements")
print(f"  Chinese period 。 → . : {stats['。']} replacements")
print(f"  Var comment (* *) → // : {stats['var_comment']} replacements")