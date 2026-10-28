"""
统一交付物构建脚本 (build_delivery.py)

⚠️ DEPRECATED (V2.4.0): 本脚本已标记为兼容保留。
   推荐使用 auto-pm CLI 替代:
     auto-pm delivery build --version V1.0.0
     auto-pm delivery package --version V1.0.0
     auto-pm delivery status
   详见: 220_Python项目打包规范_DEV §19 + auto-pm delivery --help

基于全局规范: 220_Python项目打包规范_DEV-V2.4.0
强制使用Python zipfile, 禁止PowerShell Compress-Archive

用法 (兼容保留):
    python scripts/build_delivery.py --version V1.0.0              # 完整流程
    python scripts/build_delivery.py --version V1.0.0 --skip-build   # 跳过编译
    python scripts/build_delivery.py --version V1.0.0 --verify-only  # 仅验证已有zip
"""
import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

# ============================================================
# 配置区
# ============================================================
BASE_DIR = Path(__file__).resolve().parents[1]  # scripts/ 的上一级即 SW-2026-008 项目根，不依赖本机路径
SRC_CODE = BASE_DIR
DELIVERY_DIR = BASE_DIR / "06_交付物"
PACK_DIR = BASE_DIR / "06_交付物"  # CHG-SCPT-2026-145: 合并06_交付物打包到06_交付物

PRODUCT_NAME = "Python自动化项目管理系统"
EXE_NAME = "auto-pm.exe"

# 阈值常量
THRESHOLDS = {
    "exe_min_mb": 10,
    "internal_min_files": 400,
    "config_count": 0,
    "delivery_min_files": 500,
    "zip_min_mb": 60,
    "zip_max_mb": 220,
    "zip_normal_min_mb": 100,
    "zip_normal_max_mb": 190,
    "total_min_files": 400,
    "total_max_files": 5000,
    "doc_min_count": 1,
}

MB = 1024 * 1024

# ============================================================
# 颜色输出
# ============================================================
class C:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"

def ok(msg: str) -> None: print(f"{C.GREEN}[PASS]{C.RESET} {msg}")
def fail(msg: str) -> None: print(f"{C.RED}[FAIL]{C.RESET} {msg}")
def warn(msg: str) -> None: print(f"{C.YELLOW}[WARN]{C.RESET} {msg}")
def info(msg: str) -> None: print(f"{C.BLUE}[INFO]{C.RESET}  {msg}")
def skip(msg: str) -> None: print(f"[SKIP]  {msg}")
def header(msg: str) -> None: print(f"\n{C.BOLD}{'='*60}{C.RESET}\n{C.BOLD}=== {msg} ==={C.RESET}\n{C.BOLD}{'='*60}{C.RESET}")

# ============================================================
# Step 1: 编译检查
# ============================================================
def step1_build_check(args: argparse.Namespace) -> bool:
    header("Step 1: 编译检查")
    exe_src = SRC_CODE / "dist" / "auto-pm" / EXE_NAME

    if args.verify_only:
        skip("verify-only 模式, 跳过编译检查")
        return True

    if args.skip_build:
        if exe_src.exists():
            size_mb = exe_src.stat().st_size / MB
            if size_mb >= THRESHOLDS["exe_min_mb"]:
                ok(f"exe存在且大小正常: {size_mb:.2f} MB (>{THRESHOLDS['exe_min_mb']}MB)")
                return True
            else:
                fail(f"exe太小: {size_mb:.2f} MB (<{THRESHOLDS['exe_min_mb']}MB), 需要重新编译")
                return False
        else:
            fail(f"exe不存在: {exe_src}")
            return False

    # 执行 PyInstaller 编译
    info("执行 PyInstaller 编译...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--noconfirm",
        "--clean",
        "--name", "auto-pm",
        "--add-data", "auto_pm/ui/qml;auto_pm/ui/qml",
        "--add-data", "templates;templates",
        "main.py"
    ]
    info(f"命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(SRC_CODE), capture_output=True, text=True, encoding="utf-8", errors="replace")

    if result.returncode != 0:
        fail(f"PyInstaller 编译失败:\n{result.stderr[-800:]}")
        return False

    if exe_src.exists():
        size_mb = exe_src.stat().st_size / MB
        ok(f"编译成功: {size_mb:.2f} MB")
        return True
    else:
        fail("编译完成但未找到exe")
        return False

# ============================================================
# Step 2: 更新交付物目录
# ============================================================
def step2_update_delivery(args: argparse.Namespace) -> tuple[bool, list[Path]]:
    header("Step 2: 更新06_交付物/")
    copied = []

    # 创建目标目录
    exe_dst_dir = DELIVERY_DIR / "01_可执行文件"
    if exe_dst_dir.exists():
        shutil.rmtree(exe_dst_dir)
    exe_dst_dir.mkdir(parents=True, exist_ok=True)

    # 2.1 复制整个 auto-pm/ 编译输出目录
    exe_src_dir = SRC_CODE / "dist" / "auto-pm"
    if exe_src_dir.exists():
        info(f"复制编译文件夹 {exe_src_dir} -> {exe_dst_dir} ...")
        shutil.copytree(str(exe_src_dir), str(exe_dst_dir), dirs_exist_ok=True)
        exe_path = exe_dst_dir / EXE_NAME
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / MB
            ok(f"exe: {size_mb:.2f} MB")
            copied.append(exe_path)
        else:
            fail(f"复制后 exe 不存在: {exe_path}")
            return False, copied
    else:
        fail(f"源编译目录不存在: {exe_src_dir}")
        return False, copied

    # 2.2 复制发布说明文档和 README.md
    docs_dst = DELIVERY_DIR / "02_发布说明"
    docs_dst.mkdir(parents=True, exist_ok=True)

    # 复制 CHANGELOG.md 和 README.md
    for doc in ["CHANGELOG.md", "README.md"]:
        src_f = BASE_DIR / doc
        dst_f = DELIVERY_DIR / doc
        if src_f.exists():
            shutil.copy2(str(src_f), str(dst_f))
            ok(f"复制文档: {doc}")

    # 复制标准的更新说明与交付清单
    expected_docs = [
        f"{args.version}_更新说明.md",
        f"01_交付清单_DEL-{args.version}.md"
    ]
    for doc_name in expected_docs:
        src_f = BASE_DIR / "02_发布说明" / doc_name
        dst_f = docs_dst / doc_name
        if src_f.exists():
            shutil.copy2(str(src_f), str(dst_f))
            ok(f"复制发布文档: {doc_name}")
        else:
            warn(f"未找到发布文档: {doc_name}")

    return True, copied

# ============================================================
# Step 3: 交付物目录校验
# ============================================================
def step3_verify_delivery() -> bool:
    header("Step 3: 交付物目录校验")
    checks_passed = 0
    checks_total = 4

    # CHK-D1: exe存在且大小
    exe_path = DELIVERY_DIR / "01_可执行文件" / EXE_NAME
    if exe_path.exists() and exe_path.stat().st_size > THRESHOLDS["exe_min_mb"] * MB:
        size_mb = exe_path.stat().st_size / MB
        ok(f"[D1] exe: {size_mb:.2f} MB OK")
        checks_passed += 1
    else:
        fail("[D1] exe missing or too small")

    # CHK-D2: _internal 存在且有足够文件
    internal_dir = DELIVERY_DIR / "01_可执行文件" / "_internal"
    if internal_dir.exists():
        icount = sum(len(files) for _, _, files in os.walk(internal_dir))
        if icount >= THRESHOLDS["internal_min_files"]:
            ok(f"[D2] _internal: {icount} files OK")
            checks_passed += 1
        else:
            warn(f"[D2] _internal too few: {icount} files (<{THRESHOLDS['internal_min_files']})")
    else:
        fail("[D2] _internal directory missing")

    # CHK-D3: 发布说明存在
    docs_dir = DELIVERY_DIR / "02_发布说明"
    if docs_dir.exists() and any(docs_dir.iterdir()):
        dcount = len(list(docs_dir.iterdir()))
        ok(f"[D3] docs: {dcount} files OK")
        checks_passed += 1
    else:
        warn("[D3] docs directory empty")

    # CHK-D4: 总文件数
    total_files = sum(len(files) for _, _, files in os.walk(DELIVERY_DIR))
    if total_files >= THRESHOLDS["delivery_min_files"]:
        ok(f"[D4] total files: {total_files} OK")
        checks_passed += 1
    else:
        fail(f"[D4] total files: {total_files} too few (<{THRESHOLDS['delivery_min_files']})")

    status = f"{checks_passed}/{checks_total}"
    if checks_passed == checks_total:
        ok(f"verify result: {status} PASS")
        return True
    else:
        fail(f"verify result: {status} FAIL")
        return False

# ============================================================
# Step 4: 打包zip (强制Python zipfile)
# ============================================================
def step4_package(args: argparse.Namespace) -> Path | None:
    header("Step 4: 打包zip (Python zipfile.ZIP_DEFLATED)")
    date_str = datetime.now().strftime("%Y%m%d")
    zip_name = f"{PRODUCT_NAME}_{args.version}_{date_str}.zip"
    PACK_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = PACK_DIR / zip_name

    if args.verify_only:
        if not zip_path.exists():
            fail(f"待验证的 zip 不存在: {zip_path}")
            return None
        skip(f"verify-only 模式, 使用已有 zip: {zip_name}")
        return zip_path

    if zip_path.exists():
        zip_path.unlink()
        info("已删除旧 zip")

    file_count = 0
    try:
        with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(str(DELIVERY_DIR)):
                for fn in files:
                    fp = os.path.join(root, fn)
                    arcname = os.path.relpath(fp, str(DELIVERY_DIR))
                    zf.write(fp, arcname)
                    file_count += 1
    except Exception as e:
        fail(f"打包失败: {e}")
        return None

    zip_size = zip_path.stat().st_size / MB
    ok(f"打包完成: {zip_name}")
    info(f"  文件数: {file_count}")
    info(f"  大小: {zip_size:.2f} MB")
    return zip_path

# ============================================================
# Step 5: ZIP校验 (7项CHK)
# ============================================================
def step5_verify_zip(zip_path: Path | None) -> bool:
    header("Step 5: ZIP校验 (7项CHK)")
    if not zip_path or not zip_path.exists():
        fail("无有效 zip 路径")
        return False

    results: dict[str, list[str]] = {"pass": [], "warn": [], "fail": []}

    with zipfile.ZipFile(str(zip_path), 'r') as zf:
        names = zf.namelist()

        # CHK-001: 总文件数
        total = len(names)
        if total < THRESHOLDS["total_min_files"]:
            results["fail"].append(f"[CHK-001] 文件数过少: {total} (<{THRESHOLDS['total_min_files']})")
        elif total > THRESHOLDS["total_max_files"]:
            results["fail"].append(f"[CHK-001] 文件数过多: {total} (>{THRESHOLDS['total_max_files']})")
        else:
            results["pass"].append(f"[CHK-001] 文件数: {total}")

        # CHK-002: ZIP 大小
        zip_size = zip_path.stat().st_size / MB
        if zip_size < THRESHOLDS["zip_min_mb"]:
            results["fail"].append(f"[CHK-002] ZIP 过小: {zip_size:.2f}MB (<{THRESHOLDS['zip_min_mb']}MB)")
        elif zip_size > THRESHOLDS["zip_max_mb"]:
            results["fail"].append(f"[CHK-002] ZIP 过大: {zip_size:.2f}MB (>{THRESHOLDS['zip_max_mb']}MB)")
        elif THRESHOLDS["zip_normal_min_mb"] <= zip_size <= THRESHOLDS["zip_normal_max_mb"]:
            results["pass"].append(f"[CHK-002] ZIP 大小: {zip_size:.2f}MB (正常范围)")
        else:
            results["warn"].append(f"[CHK-002] ZIP 大小: {zip_size:.2f}MB (可接受)")

        # CHK-003: exe 存在且大小
        exe_files = [n for n in names if n.endswith(EXE_NAME)]
        if not exe_files:
            results["fail"].append(f"[CHK-003] 缺少 {EXE_NAME} 文件!")
        else:
            exe_info = zf.getinfo(exe_files[0])
            exe_mb = exe_info.file_size / MB
            if exe_mb < THRESHOLDS["exe_min_mb"]:
                results["fail"].append(f"[CHK-003] exe 过小: {exe_mb:.2f}MB")
            else:
                results["pass"].append(f"[CHK-003] exe: {exe_mb:.2f}MB")

        # CHK-004: _internal 文件数
        internal_count = len([n for n in names if '_internal/' in n])
        if internal_count < THRESHOLDS["internal_min_files"]:
            results["fail"].append(f"[CHK-004] _internal: {internal_count} 文件 (<{THRESHOLDS['internal_min_files']})")
        else:
            results["pass"].append(f"[CHK-004] _internal: {internal_count} 文件")

        # CHK-005: 关键文档
        found_docs = sum(1 for n in names if n.endswith('.md'))
        if found_docs < THRESHOLDS["doc_min_count"]:
            results["warn"].append(f"[CHK-005] 文档: 仅找到 {found_docs} 个 md 文件")
        else:
            results["pass"].append(f"[CHK-005] 文档: 找到 {found_docs} 个 md 文件")

        # CHK-006: 配置文件数校验（不适用，标记通过）
        results["pass"].append("[CHK-006] config: not required")

        # CHK-007: 一级目录结构
        top_dirs = set()
        for n in names:
            parts = n.replace('\\', '/').split('/')
            if len(parts) >= 2:
                top_dirs.add(parts[0])
        expected = {'01_可执行文件'}
        missing = expected - top_dirs
        if missing:
            results["fail"].append(f"[CHK-007] missing top dir: {missing}")
        else:
            results["pass"].append(f"[CHK-007] top dir complete ({sorted(top_dirs)})")

    # 输出结果
    for r in results["pass"]:
        ok(r)
    for r in results["warn"]:
        warn(r)
    for r in results["fail"]:
        fail(r)

    status = "FAIL" if results["fail"] else ("WARN" if results["warn"] else "PASS")
    info(f"> Standard ZIP validation: {status} (Pass:{len(results['pass'])} Warn:{len(results['warn'])} Fail:{len(results['fail'])})")

    return len(results["fail"]) == 0

# ============================================================
# Step 6: 输出报告
# ============================================================
def step6_report(results: dict[str, Any]) -> bool:
    header("Step 6: 构建报告")

    all_pass = all(results.values())
    status_icon = "[APPROVED]" if all_pass else "[BLOCKED]"
    status_text = "RELEASE APPROVED" if all_pass else "RELEASE BLOCKED"

    report = f"""
{'='*60}
{status_icon} DELIVERY BUILD REPORT - {results.get('version','?')}_{datetime.now().strftime('%Y%m%d')}
{'='*60}
  Step 1 [编译]:  {'PASS' if results.get('s1') else ('SKIP' if results.get('s1_skip') else 'FAIL')}
  Step 2 [更新]:  {'PASS' if results.get('s2') else 'FAIL'}
  Step 3 [校验]:  {'PASS' if results.get('s3') else 'FAIL'}
  Step 4 [打包]:  {'PASS' if results.get('s4') else 'FAIL'}
  Step 5 [验证]:  {'PASS' if results.get('s5') else 'FAIL'}
{'='*60}
  >>> Final Status: {status_icon} {status_text}
{'='*60}
"""
    print(report)
    return all_pass

# ============================================================
# Main
# ============================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        description="SW-2026-008 交付物构建工具 — 基于 220_Python项目打包规范_V2.3.0"
    )
    parser.add_argument("--version", required=True, help="目标版本号 (如 V1.0.0)")
    parser.add_argument("--skip-build", action="store_true", help="跳过 PyInstaller 编译步骤")
    parser.add_argument("--verify-only", action="store_true", help="仅验证已有 zip")
    args = parser.parse_args()

    results = {"version": args.version}

    # Step 1
    r1 = step1_build_check(args)
    results["s1"] = r1
    results["s1_skip"] = args.skip_build or args.verify_only
    if not r1 and not (args.skip_build or args.verify_only):
        step6_report(results)
        sys.exit(1)

    # Step 2
    r2, _ = step2_update_delivery(args)
    results["s2"] = r2
    if not r2 and not args.verify_only:
        step6_report(results)
        sys.exit(1)

    # Step 3
    if not args.verify_only:
        r3 = step3_verify_delivery()
        results["s3"] = r3
        if not r3:
            step6_report(results)
            sys.exit(1)
    else:
        results["s3"] = True

    # Step 4
    zip_path = step4_package(args)
    results["s4"] = zip_path is not None

    # Step 5
    if zip_path:
        r5 = step5_verify_zip(zip_path)
        results["s5"] = r5
    else:
        results["s5"] = False

    # Step 6
    success = step6_report(results)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
