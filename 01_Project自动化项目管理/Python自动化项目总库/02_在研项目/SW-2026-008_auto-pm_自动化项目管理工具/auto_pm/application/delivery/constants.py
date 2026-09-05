"""交付物模块常量定义

定义目录名、文件名模板、默认阈值、命名格式等。
"""

from __future__ import annotations

# 目录名
DIR_DELIVERY = "06_交付物"
DIR_PACKAGE = (
    "06_交付物"  # CHG-SCPT-2026-145: 合并06_交付物打包到06_交付物，ZIP直接存放于06_交付物/根目录
)
DIR_ARCHIVE = "archive"
DIR_EXECUTABLE = "01_可执行文件"
DIR_RELEASE_NOTES = "02_发布说明"

# 归档说明文件名
ARCHIVE_INFO_FILENAME = "archive_info.md"
ARCHIVE_MANIFEST_FILENAME = "archive_manifest.md"

# 交付物打包命名模板
# {product_name}_V{version}_{date}.zip
PACKAGE_NAME_TEMPLATE = "{product_name}_V{version}_{date}.zip"

# 归档子目录命名模板
# V{version}_{date}
ARCHIVE_DIR_TEMPLATE = "V{version}_{date}"

# 默认产品名称（可从 pyproject.toml 读取）
DEFAULT_PRODUCT_NAME = "auto-pm"

# --- 验证阈值（从 220 规范提取） ---

# 交付物目录校验 (D-checks)
DCHECK_EXE_MIN_MB = 10
DCHECK_INTERNAL_MIN_FILES = 400
DCHECK_DELIVERY_MIN_FILES = 500

# ZIP 校验 (CHK-checks)
CHK_TOTAL_MIN_FILES = 400
CHK_TOTAL_MAX_FILES = 5000
CHK_ZIP_MIN_MB = 80
CHK_ZIP_MAX_MB = 220
CHK_ZIP_NORMAL_MIN_MB = 150
CHK_ZIP_NORMAL_MAX_MB = 170
CHK_EXE_MIN_MB = 10
CHK_EXE_MAX_MB = 100
CHK_DOC_MIN_COUNT = 1

# 默认归档保留数量
DEFAULT_ARCHIVE_KEEP = 5

MB = 1024 * 1024
