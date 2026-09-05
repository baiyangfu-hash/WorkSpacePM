"""SCL 代码规范静态检查器 (Siemens LSP-905 规范)

扫描 PLC 源码中的 .scl 文件，依据 Obsidian 《905_SCL编程规范_LSP.md》
秒级检查变量作用域前缀 (i_/o_/io_/s_)、ARRAY 类型标识 (arr)、
语法白名单 (严禁 GOTO/REPEAT/指针) 以及状态机安全防护闭环
(CASE 缺失 ELSE 防卡死分支)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SclViolation:
    """SCL 规范违规条目"""

    line_number: int
    rule_id: str  # 例: "LSP-905-VAR-PREFIX", "LSP-905-SYNTAX-GOTO"
    severity: str  # "ERROR" | "WARNING"
    message: str
    code_snippet: str = ""


@dataclass
class SclLintReport:
    """SCL 单文件静态扫描报告"""

    file_path: str
    total_violations: int = 0
    errors_count: int = 0
    warnings_count: int = 0
    violations: list[SclViolation] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return self.errors_count == 0


class SclLinter:
    """SCL 静态规范检查器引擎"""

    # 语法黑名单与工控错误预防正则（LSP-905 / LSP-906）
    GOTO_PATTERN = re.compile(r"\bGOTO\b", re.IGNORECASE)
    REPEAT_PATTERN = re.compile(r"\bREPEAT\b", re.IGNORECASE)
    POINTER_PATTERN = re.compile(r"\^|\bADR\b|\bREF_TO\b", re.IGNORECASE)
    TIME_LITERAL_PATTERN = re.compile(r"\b[Tt]#[0-9a-zA-Z_]+")
    CHINESE_PUNCT_PATTERN = re.compile(r"[，；：\uFF08\uFF09\u3001]")
    TIMER_MISSING_Q_PATTERN = re.compile(r"\bQ\s*=>\s*[,)]")

    # 声明块识别正则
    BLOCK_VAR_INPUT = re.compile(r"^\s*VAR_INPUT\b", re.IGNORECASE)
    BLOCK_VAR_OUTPUT = re.compile(r"^\s*VAR_OUTPUT\b", re.IGNORECASE)
    BLOCK_VAR_IN_OUT = re.compile(r"^\s*VAR_IN_OUT\b", re.IGNORECASE)
    BLOCK_VAR_CONSTANT = re.compile(r"^\s*VAR\s+CONSTANT\b", re.IGNORECASE)
    BLOCK_VAR_STATIC = re.compile(r"^\s*VAR\b", re.IGNORECASE)
    BLOCK_VAR_TEMP = re.compile(r"^\s*VAR_TEMP\b", re.IGNORECASE)
    BLOCK_END_VAR = re.compile(r"^\s*END_VAR\b", re.IGNORECASE)

    # 变量提取正则 (例: i_bStart : BOOL;)
    VAR_DECLARATION_PATTERN = re.compile(r"^\s*([a-zA-Z0-9_]+)\s*:\s*([a-zA-Z0-9_]+)")

    ARRAY_PREFIX_MAP = {
        "VAR_INPUT": ("i_arr", "I_arr"),
        "VAR_OUTPUT": ("o_arr", "O_arr", "q_arr", "Q_arr"),
        "VAR_IN_OUT": ("io_arr", "IO_arr", "iq_arr", "IQ_arr"),
        "VAR": ("s_arr", "S_arr"),
        "VAR_TEMP": ("t_arr", "T_arr", "temp_arr", "TEMP_arr"),
        "VAR_CONSTANT": ("CONST_arr",),
    }

    @classmethod
    def lint_text(cls, text: str, file_path: str = "") -> SclLintReport:
        """对 SCL 文本进行全量静态扫描"""
        report = SclLintReport(file_path=file_path)
        lines = text.splitlines()

        current_block: str | None = None
        in_case_block = False
        case_has_else = False
        case_start_line = 0
        in_multiline_comment = False

        for line_idx, line in enumerate(lines, start=1):
            stripped = line.strip()

            # 处理跨行注释 (* ... *)
            if in_multiline_comment:
                if "*)" in stripped:
                    in_multiline_comment = False
                    # 截取 *) 之后的代码部分
                    line = stripped.split("*)", 1)[1]
                    stripped = line.strip()
                else:
                    continue

            # 跳过单行 // 注释
            if stripped.startswith("//"):
                continue

            # 处理本行开始的 (*
            if "(*" in line:
                if "*)" not in line:
                    in_multiline_comment = True
                    line = line.split("(*", 1)[0]
                    stripped = line.strip()
                else:
                    # 单行内的 (* ... *) 用正则替换掉
                    line = re.sub(r"\(\*.*?\*\)", "", line)
                    stripped = line.strip()

            if not stripped:
                continue

            # 分离代码部分与行尾 // 注释
            code_part = line.split("//")[0].strip()
            if not code_part:
                continue

            # ------------------------------------------------------------------
            # 1. 语法白名单与错误预防校验 (LSP-905 §4 / LSP-906)
            # ------------------------------------------------------------------
            if cls.GOTO_PATTERN.search(code_part):
                report.violations.append(
                    SclViolation(
                        line_number=line_idx,
                        rule_id="LSP-905-SYNTAX-GOTO",
                        severity="ERROR",
                        message="违规使用 GOTO 语法，Siemens LSP 规范强制禁止使用 GOTO",
                        code_snippet=stripped,
                    )
                )

            if cls.REPEAT_PATTERN.search(code_part):
                report.violations.append(
                    SclViolation(
                        line_number=line_idx,
                        rule_id="LSP-905-SYNTAX-REPEAT",
                        severity="WARNING",
                        message="推荐使用 WHILE 或 FOR 循环替代 REPEAT",
                        code_snippet=stripped,
                    )
                )

            if cls.POINTER_PATTERN.search(code_part):
                report.violations.append(
                    SclViolation(
                        line_number=line_idx,
                        rule_id="LSP-905-SYNTAX-POINTER",
                        severity="ERROR",
                        message="禁止使用指针运算 (指针/^/ADR)，请改用 UDT 或结构体",
                        code_snippet=stripped,
                    )
                )

            if cls.TIME_LITERAL_PATTERN.search(code_part):
                report.violations.append(
                    SclViolation(
                        line_number=line_idx,
                        rule_id="LSP-906-TIMER-TIME-LITERAL",
                        severity="ERROR",
                        message="禁止在 SCL 中使用 TIME 类型字面量（如 T#500ms），PT/ET 必须使用 DINT 毫秒整数（LSP-906 §1.1）",
                        code_snippet=stripped,
                    )
                )

            if cls.CHINESE_PUNCT_PATTERN.search(code_part):
                report.violations.append(
                    SclViolation(
                        line_number=line_idx,
                        rule_id="LSP-905-CHINESE-PUNCTUATION",
                        severity="ERROR",
                        message="SCL 代码中包含中文全角标点符号（，/；/：/（）），请替换为英文半角标点",
                        code_snippet=stripped,
                    )
                )

            if cls.TIMER_MISSING_Q_PATTERN.search(code_part):
                report.violations.append(
                    SclViolation(
                        line_number=line_idx,
                        rule_id="LSP-906-TIMER-MISSING-Q",
                        severity="ERROR",
                        message="定时器调用缺少 Q 参数接收变量（禁止空参数 Q => ,）",
                        code_snippet=stripped,
                    )
                )

            # ------------------------------------------------------------------
            # 2. 作用域声明块追踪与变量前缀校验 (LSP-905 §3.1)
            # ------------------------------------------------------------------
            if cls.BLOCK_VAR_INPUT.match(stripped):
                current_block = "VAR_INPUT"
                continue
            elif cls.BLOCK_VAR_OUTPUT.match(stripped):
                current_block = "VAR_OUTPUT"
                continue
            elif cls.BLOCK_VAR_IN_OUT.match(stripped):
                current_block = "VAR_IN_OUT"
                continue
            elif cls.BLOCK_VAR_TEMP.match(stripped):
                current_block = "VAR_TEMP"
                continue
            elif cls.BLOCK_VAR_CONSTANT.match(stripped):
                current_block = "VAR_CONSTANT"
                continue
            elif cls.BLOCK_VAR_STATIC.match(stripped):
                current_block = "VAR"
                continue
            elif cls.BLOCK_END_VAR.match(stripped):
                current_block = None
                continue

            if current_block and ":" in line and not stripped.startswith("END_"):
                var_match = cls.VAR_DECLARATION_PATTERN.match(line)
                if var_match:
                    var_name = var_match.group(1)
                    var_type = var_match.group(2).upper()

                    if current_block == "VAR_INPUT" and not (
                        var_name.startswith("i_") or var_name.startswith("I_")
                    ):
                        report.violations.append(
                            SclViolation(
                                line_number=line_idx,
                                rule_id="LSP-905-VAR-INPUT-PREFIX",
                                severity="ERROR",
                                message=f"输入变量 '{var_name}' 缺失 'i_' 前缀（如 i_bStart）",
                                code_snippet=stripped,
                            )
                        )
                    elif current_block == "VAR_OUTPUT" and not (
                        var_name.startswith("o_")
                        or var_name.startswith("O_")
                        or var_name.startswith("q_")
                        or var_name.startswith("Q_")
                    ):
                        report.violations.append(
                            SclViolation(
                                line_number=line_idx,
                                rule_id="LSP-905-VAR-OUTPUT-PREFIX",
                                severity="ERROR",
                                message=f"输出变量 '{var_name}' 缺失 'o_' 或 'q_' 前缀（如 o_bRunning）",
                                code_snippet=stripped,
                            )
                        )
                    elif current_block == "VAR_IN_OUT" and not (
                        var_name.startswith("io_")
                        or var_name.startswith("IO_")
                        or var_name.startswith("iq_")
                        or var_name.startswith("IQ_")
                    ):
                        report.violations.append(
                            SclViolation(
                                line_number=line_idx,
                                rule_id="LSP-905-VAR-INOUT-PREFIX",
                                severity="ERROR",
                                message=f"双向变量/结构体 '{var_name}' 缺失 'io_' 前缀（如 io_stLayer）",
                                code_snippet=stripped,
                            )
                        )
                    elif current_block == "VAR" and not (
                        var_name.startswith("s_")
                        or var_name.startswith("S_")
                        or var_name.startswith("fb_")
                        or var_name.startswith("FB_")
                        or var_name.startswith("st_")
                        or var_name.startswith("ST_")
                        or var_name.startswith("ast_")
                        or var_name.startswith("AST_")
                    ):
                        report.violations.append(
                            SclViolation(
                                line_number=line_idx,
                                rule_id="LSP-905-VAR-STATIC-PREFIX",
                                severity="WARNING",
                                message=f"静态变量 '{var_name}' 建议补齐 's_' (变量)、'st_' (结构体) 或 'fb_' (实例) 前缀",
                                code_snippet=stripped,
                            )
                        )
                    elif current_block == "VAR_TEMP" and not (
                        var_name.startswith("t_")
                        or var_name.startswith("T_")
                        or var_name.startswith("temp_")
                        or var_name.startswith("TEMP_")
                    ):
                        report.violations.append(
                            SclViolation(
                                line_number=line_idx,
                                rule_id="LSP-905-VAR-TEMP-PREFIX",
                                severity="WARNING",
                                message=f"临时变量 '{var_name}' 建议补齐 't_' 前缀（如 t_bAutoEnable）",
                                code_snippet=stripped,
                            )
                        )

                    if var_type == "ARRAY" and not cls._has_array_type_prefix(
                        current_block, var_name
                    ):
                        expected_prefixes = cls.ARRAY_PREFIX_MAP.get(current_block, ("arr",))
                        expected_text = " / ".join(expected_prefixes)
                        report.violations.append(
                            SclViolation(
                                line_number=line_idx,
                                rule_id="LSP-905-VAR-ARRAY-TYPE-PREFIX",
                                severity="WARNING",
                                message=(
                                    f"数组变量 '{var_name}' 建议使用 '{expected_text}' 类型标识"
                                    "（如 s_arrMesAlarmQueue）"
                                ),
                                code_snippet=stripped,
                            )
                        )

            # ------------------------------------------------------------------
            # 3. 状态机 CASE/OF 完整性与安全闭环检查 (LSP-905 §4)
            # ------------------------------------------------------------------
            if re.search(r"\bCASE\b.*\bOF\b", stripped, re.IGNORECASE):
                in_case_block = True
                case_has_else = False
                case_start_line = line_idx

            if in_case_block:
                if re.search(r"\bELSE\b", stripped, re.IGNORECASE):
                    case_has_else = True
                elif re.search(r"\bEND_CASE\b", stripped, re.IGNORECASE):
                    if not case_has_else:
                        report.violations.append(
                            SclViolation(
                                line_number=case_start_line,
                                rule_id="LSP-905-CASE-NO-ELSE",
                                severity="ERROR",
                                message="状态机 CASE 缺少 ELSE 防死锁容错自愈分支",
                                code_snippet=stripped,
                            )
                        )
                    in_case_block = False

        # 汇总计数
        report.total_violations = len(report.violations)
        report.errors_count = sum(1 for v in report.violations if v.severity == "ERROR")
        report.warnings_count = sum(1 for v in report.violations if v.severity == "WARNING")

        return report

    @classmethod
    def _has_array_type_prefix(cls, current_block: str, var_name: str) -> bool:
        expected_prefixes = cls.ARRAY_PREFIX_MAP.get(current_block)
        if not expected_prefixes:
            return True
        return any(var_name.startswith(prefix) for prefix in expected_prefixes)

    @classmethod
    def lint_file(cls, file_path: Path | str) -> SclLintReport:
        """扫描磁盘上的 .scl 文件"""
        path = Path(file_path)
        if not path.exists():
            return SclLintReport(file_path=str(path))
        try:
            content = (
                path.write_text(encoding="utf-8") if False else path.read_text(encoding="utf-8")
            )
            return cls.lint_text(content, file_path=str(path))
        except Exception as exc:
            rep = SclLintReport(file_path=str(path))
            rep.violations.append(
                SclViolation(
                    line_number=0,
                    rule_id="FILE-READ-ERROR",
                    severity="ERROR",
                    message=f"读取文件失败: {exc}",
                )
            )
            rep.errors_count = 1
            rep.total_violations = 1
            return rep
