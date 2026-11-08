"""PLC-HMI 概念映射：入口信号校验（进料口先验料，坏料不进产线）

命令行参数在进入解释器时就可能已经损坏：外壳（例如 Windows 上的 Git bash）把很长的命令行转换成 Windows 的
UTF-16 时，若把一个生僻汉字（4 字节字符）从中间截断，Python 收到的参数里就带着孤立的代理字符（如 ``\\ude64``）。
这样的参数一路传到“写文件”那一步才报 ``'utf-8' codec can't encode characters ... surrogates not allowed``，
离根因很远（D-133）。本模块在 CLI 入口先查一遍，坏了就当场拒绝，并指出是第几个参数。

只读检查，不改参数、不尝试修复（修出来的路径可能不是用户要的那一个）。
"""

from __future__ import annotations

from collections.abc import Sequence

ARGV_EXIT_CODE = 2


def _has_lone_surrogate(text: str) -> bool:
    return any("\ud800" <= char <= "\udfff" for char in text)


def broken_argument_message(args: Sequence[str]) -> str | None:
    """The refusal text for the first argument that holds a lone surrogate, or ``None`` when every argument is sound.

    The message names the argument by its position (counted from 1, after the program name) and, when the argument
    is the value of a repeated option such as ``--file``, also by its position among that option's occurrences.
    Everything is shown through ``ascii()``, so printing the message cannot fail on a console that cannot encode it.
    """

    for index, argument in enumerate(args):
        if not _has_lone_surrogate(argument):
            continue
        parts = [f"第 {index + 1} 个命令行参数的编码损坏（含孤立代理字符）：{ascii(argument)}"]
        previous = args[index - 1] if index > 0 else ""
        if previous.startswith("-") and not _has_lone_surrogate(previous):
            nth = sum(1 for earlier in args[:index] if earlier == previous) or 1
            parts.append(f"它是第 {nth} 个 {previous} 的值")
        parts.append(
            "命令没有执行，没有改动任何文件。常见原因：外壳把很长的命令行里的生僻汉字截断了。"
            "请单条重试这个参数，或改用 Python subprocess 传参"
        )
        return "；".join(parts)
    return None
