#!/usr/bin/env python3
"""PLC 项目的插件 test 层 (默认 DJ-2026-005): 用"测试用 SysLib 替身计时器"在临时副本里跑 siemens-lsp test.

为什么: SysLib 的 FB_TON / FB_TONR 毫秒版内部调用平台原生 TON, Siemens 语言服务插件的
测试运行时没有原生 TON 实现, 一跑就 panic (STUB BUILTIN: B_TON), 整个测试进程退出.
做法: 在系统临时目录里复制 SysLib 和项目的 PLC_ST, 只把临时副本里的计时器文件换成
本目录 timer/ 下的"按扫描次数计时"替身 (存成 .scl.txt, 避免被 plc check 当成项目源码扫描), 在副本里跑 `siemens-lsp test .`. 仓库里的
.plc.json、SysLib、项目源码一个字都不改, 跑完删掉临时副本; 脚本另外对比运行前后的
文件哈希, 证明原文件没动.

计时行为未验证, 以 PLCSIM 或现场为准.

用法 (在控制根或任意目录):
    python run_plugin_test.py [--project 项目] [--lsp siemens-lsp 路径] [--keep]
--project 默认 DJ-2026-005 (不带这个参数时行为和以前完全一样); 可写项目编号 (如 DJ-2026-009, 在 0100_PLC自动化
下按编号开头找唯一的项目目录) 或项目目录路径. 替身计时器始终取自本目录 timer/, 所有项目共用.
也可用环境变量 SIEMENS_LSP 指定插件命令. 退出码 = 插件 test 的退出码; 2 = 脚本自身出错.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

NOTE = "计时行为未验证, 以 PLCSIM 或现场为准 (本次 test 用的是按扫描次数计时的替身 FB_TON / FB_TONR)"
HERE = Path(__file__).resolve().parent
# 本文件位于 <库根>/DJ-2026-005/05_测试与验证/测试用SysLib/; 替身计时器 (timer/) 在本目录, 各项目共用
DEFAULT_PROJECT = HERE.parents[1]
LIB_ROOT = DEFAULT_PROJECT.parent
SYSLIB = LIB_ROOT / "01_SharedLibraries" / "SysLib"
SWAPPED = ("FB_TON.scl", "FB_TONR.scl")


def resolve_project(value: str | None) -> Path:
    """项目目录: 不带参数用 DJ-2026-005; 带路径用该路径; 带编号在库根下按编号开头找唯一一个."""
    if not value:
        return DEFAULT_PROJECT
    given = Path(value)
    if given.is_dir():
        return given.resolve()
    hits = sorted(p for p in LIB_ROOT.glob(value + "*") if p.is_dir() and p.name.startswith(value))
    exact = [p for p in hits if p.name == value]
    if exact:
        return exact[0]
    if len(hits) != 1:
        raise SystemExit(f"找不到唯一的项目目录: {value} (在 {LIB_ROOT} 下匹配到 {len(hits)} 个)")
    return hits[0]


def _digest(paths: list[Path]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in paths:
        out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "<missing>"
    return out


def _guarded_files(project: Path) -> list[Path]:
    plc_dir = project / "02_PLC程序" / "PLC_ST"
    files = [project / ".plc.json", plc_dir / ".plc.json"]
    files += [SYSLIB / "timer" / n for n in SWAPPED]
    files += sorted(plc_dir.rglob("*.scl"))
    return files


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lsp", default=os.environ.get("SIEMENS_LSP", "siemens-lsp"), help="siemens-lsp 命令")
    ap.add_argument("--keep", action="store_true", help="保留临时副本 (排查用)")
    ap.add_argument("--project", default=None, help="项目编号或项目目录路径 (默认 DJ-2026-005)")
    args = ap.parse_args()

    project = resolve_project(args.project)
    plc_dir = project / "02_PLC程序" / "PLC_ST"

    for need in (project / ".plc.json", SYSLIB, plc_dir, HERE / "timer" / (SWAPPED[0] + ".txt"), HERE / "timer" / (SWAPPED[1] + ".txt")):
        if not need.exists():
            print(f"缺少 {need}", file=sys.stderr)
            return 2

    before = _digest(_guarded_files(project))
    tmp = Path(tempfile.mkdtemp(prefix=f"plugin_test_{project.name.split('_')[0]}_"))
    rc = 2
    try:
        # 保持与仓库相同的相对布局: <tmp>/<项目目录名> 与 <tmp>/01_SharedLibraries/SysLib
        t_proj = tmp / project.name
        t_lib = tmp / "01_SharedLibraries" / "SysLib"
        shutil.copytree(SYSLIB, t_lib)
        (t_proj / "02_PLC程序").mkdir(parents=True)
        shutil.copy2(project / ".plc.json", t_proj / ".plc.json")
        t_plc = t_proj / "02_PLC程序" / "PLC_ST"
        shutil.copytree(plc_dir, t_plc)
        for name in SWAPPED:
            shutil.copy2(HERE / "timer" / (name + ".txt"), t_lib / "timer" / name)

        print(f"[临时副本] {tmp}")
        print(f"[命令] {args.lsp} test .  (cwd={t_plc})")
        print(f"[说明] {NOTE}")
        proc = subprocess.run(
            [args.lsp, "test", "."], cwd=t_plc, capture_output=True, encoding="utf-8", errors="replace"
        )
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        rc = proc.returncode
    except FileNotFoundError as exc:
        print(f"找不到插件命令: {exc}", file=sys.stderr)
        rc = 2
    finally:
        if args.keep:
            print(f"[保留] {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
        after = _digest(_guarded_files(project))
        changed = [k for k in before if before[k] != after.get(k)]
        if changed:
            print("原文件被改动 (不应发生):", *changed, sep="\n  ", file=sys.stderr)
            rc = 2
        else:
            print(f"[原文件校验] {len(before)} 个文件运行前后哈希一致, 仓库未被改动")
    print(f"[结论] 插件 test 退出码 {rc}。{NOTE}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
