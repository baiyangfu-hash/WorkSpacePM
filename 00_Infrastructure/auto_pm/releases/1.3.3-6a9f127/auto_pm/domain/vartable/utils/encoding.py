"""PLC-HMI 概念映射：SFB 库函数（编码检测（自动检测变量表文件编码））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

文件编码检测工具

V2.3 Week1 T03：不依赖 chardet 的轻量编码检测。

检测策略（按优先级）：
1. BOM 检测：UTF-8 BOM / UTF-16 LE BOM / UTF-16 BE BOM / UTF-32 BOM
2. 常见编码尝试：utf-8 → utf-8-sig → gbk → gb2312 → latin-1（最后兜底）
3. 无效字符校验：解码后检查是否含 U+FFFD 替换字符

不引入 chardet 依赖，因为工作空间 venv 未安装。
若后续需更精准检测，可在 Week2 pip install chardet 后扩展。
"""

from __future__ import annotations

from pathlib import Path

# BOM 标记（按长度降序排列，避免短 BOM 误匹配长 BOM）
_BOM_MARKERS: tuple[tuple[bytes, str], ...] = (
    (b"\xef\xbb\xbf", "utf-8-sig"),  # UTF-8 BOM (3 bytes)
    (b"\xff\xfe", "utf-16-le"),  # UTF-16 LE BOM (2 bytes)
    (b"\xfe\xff", "utf-16-be"),  # UTF-16 BE BOM (2 bytes)
    (b"\xff\xfe\x00\x00", "utf-32-le"),  # UTF-32 LE BOM (4 bytes)
    (b"\x00\x00\xfe\xff", "utf-32-be"),  # UTF-32 BE BOM (4 bytes)
)

# 常见编码尝试顺序（无 BOM 时按序尝试）
_FALLBACK_ENCODINGS: tuple[str, ...] = (
    "utf-8",
    "gbk",
    "gb2312",
    "latin-1",  # 最后兜底，绝不会失败但可能含 U+FFFD
)

# 支持的编码列表（供 CLI 展示）
SUPPORTED_ENCODINGS: tuple[str, ...] = (
    "utf-8",
    "utf-8-sig",
    "gbk",
    "gb2312",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
    "latin-1",
)


def detect_encoding(file_path: str | Path) -> str:
    """检测文件编码

    Args:
        file_path: 文件路径

    Returns:
        检测到的编码名称（标准化小写）

    Raises:
        FileNotFoundError: 文件不存在
        OSError: 文件读取失败
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 读取全部内容,BOM 检测在 content 上进行
    with path.open("rb") as f:
        content = f.read()

    # 1. BOM 检测
    for bom, encoding in _BOM_MARKERS:
        if content.startswith(bom):
            return encoding

    # 2. 无 BOM，按常见编码尝试
    for encoding in _FALLBACK_ENCODINGS:
        try:
            decoded = content.decode(encoding)
            # 校验是否含替换字符（说明编码错误但未抛异常）
            if "\ufffd" not in decoded:
                return encoding
        except (UnicodeDecodeError, LookupError):
            continue

    # 3. 兜底返回 utf-8（可能含 U+FFFD）
    return "utf-8"


def read_file_with_detection(file_path: str | Path) -> tuple[str, str]:
    """自动检测编码并读取文件

    Args:
        file_path: 文件路径

    Returns:
        (文件内容, 检测到的编码)

    Raises:
        FileNotFoundError: 文件不存在
        OSError: 文件读取失败
    """
    encoding = detect_encoding(file_path)
    path = Path(file_path)
    try:
        return path.read_text(encoding=encoding), encoding
    except UnicodeDecodeError:
        # 检测失败，用 latin-1 兜底（绝不会失败）
        return path.read_text(encoding="latin-1"), "latin-1"


def normalize_encoding(encoding: str) -> str:
    """标准化编码名称

    Args:
        encoding: 原始编码名称

    Returns:
        标准化后的编码名称（小写）
    """
    if not encoding:
        return "utf-8"

    normalized = encoding.lower().replace("_", "-")

    # 常见别名映射
    alias_map = {
        "utf8": "utf-8",
        "utf8sig": "utf-8-sig",
        "utf16": "utf-16",
        "utf16le": "utf-16-le",
        "utf16be": "utf-16-be",
        "gb18030": "gbk",
        "chinese": "gbk",
    }
    return alias_map.get(normalized, normalized)
