"""ST 小解释器：在云端（没有 InoProShop / PLCSIM）直接执行 .scl 源码里的功能块，做逻辑仿真。

只认本仓库安全块用到的一个 ST 子集，够用即可，不是完整的 IEC 61131-3：

* 声明：VAR_INPUT / VAR_OUTPUT / VAR_IN_OUT / VAR / VAR_TEMP / VAR CONSTANT / CONST…END_CONST；
  类型 BOOL、INT、DINT、WORD、DWORD、TIME、STRING[n]、ARRAY[a..b] OF T、功能块实例。
* 语句：赋值、功能块调用（具名参数，``=>`` 取输出）、IF/ELSIF/ELSE、CASE（整数/常量标签、逗号、区间）、FOR、RETURN、空语句。
* 表达式：OR/XOR/AND/NOT、比较、+ - * / MOD、括号、SHL/SHR、常见 *_TO_* 转换、16# 与 DWORD#1 这类字面量。
* 西门子写法的 ``#`` 变量前缀和 ``BEGIN`` 行自动忽略。

计时：``FB_TON`` 用 Python 实现，按仿真时钟 ``Sim.now_ms`` 计真实毫秒（与 SysLib FB_TON V3.0.0 同义：
PT<=0 时 Q 跟随 IN；ET 到 PT 封顶）。``FB_R_TRIG`` / ``FB_F_TRIG`` 也用 Python 实现。其他功能块从源码解释。

用法见 ``test_fb1030_safety_manager.py``。本文件只读源码、不写任何文件。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- 词法

_TOKEN = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<lcomment>//[^\n]*)
  | (?P<bcomment>\(\*.*?\*\))
  | (?P<str>'[^']*')
  | (?P<num>(?:[A-Za-z_]+\#)?(?:16\#[0-9A-Fa-f_]+|2\#[01_]+|\d[\d_]*(?:\.\d+)?)(?!\w))
  | (?P<op>:=|=>|<>|<=|>=|\.\.|[-+*/=<>()\[\],;:.])
  | (?P<id>\#?[A-Za-z_][A-Za-z0-9_]*)
    """,
    re.VERBOSE | re.DOTALL,
)

KEYWORDS = {
    "IF", "THEN", "ELSIF", "ELSE", "END_IF", "CASE", "OF", "END_CASE", "FOR", "TO", "BY", "DO", "END_FOR",
    "AND", "OR", "XOR", "NOT", "MOD", "RETURN", "TRUE", "FALSE", "BEGIN", "WHILE", "END_WHILE",
}


@dataclass
class Tok:
    kind: str  # id / num / str / op / kw / eof
    text: str
    line: int


def tokenize(src: str) -> list[Tok]:
    out: list[Tok] = []
    pos, line = 0, 1
    while pos < len(src):
        m = _TOKEN.match(src, pos)
        if not m:
            raise SyntaxError(f"无法识别的字符 {src[pos]!r}（第 {line} 行）")
        kind = m.lastgroup
        text = m.group(kind)
        if kind == "id":
            text = text.lstrip("#")
            if text.upper() in KEYWORDS:
                kind, text = "kw", text.upper()
        if kind not in ("ws", "lcomment", "bcomment"):
            out.append(Tok(kind, text, line))
        line += text.count("\n") if kind in ("ws", "bcomment") else 0
        pos = m.end()
    out.append(Tok("eof", "", line))
    return out


# --------------------------------------------------------------------------- 类型与值

@dataclass
class TypeSpec:
    name: str  # BOOL / INT / ... / ARRAY / FB 名
    lo: int = 0
    hi: int = 0
    elem: "TypeSpec | None" = None


INT_TYPES = {"INT", "DINT", "SINT", "LINT", "UINT", "UDINT", "USINT", "BYTE", "WORD", "DWORD", "LWORD", "TIME"}
BITS = {"BYTE": 8, "WORD": 16, "DWORD": 32, "LWORD": 64}


def default_value(t: TypeSpec, sim: "Sim") -> Any:
    n = t.name.upper()
    if n == "BOOL":
        return False
    if n in INT_TYPES:
        return 0
    if n.startswith("STRING"):
        return ""
    if n == "ARRAY":
        return ArrayVal(t.lo, [default_value(t.elem, sim) for _ in range(t.lo, t.hi + 1)])
    if t.name in sim.structs:
        return sim.new_struct(t.name)
    return sim.new_instance(t.name)


class ArrayVal(list):
    """带下界的数组。"""

    def __init__(self, lo: int, items: list[Any]):
        super().__init__(items)
        self.lo = lo


# --------------------------------------------------------------------------- 语法树（用元组表示）

class Parser:
    def __init__(self, toks: list[Tok]):
        self.t = toks
        self.i = 0

    # 基本
    def peek(self, k: int = 0) -> Tok:
        return self.t[self.i + k]

    def take(self) -> Tok:
        tok = self.t[self.i]
        self.i += 1
        return tok

    def accept(self, text: str) -> bool:
        tok = self.peek()
        if tok.kind in ("op", "kw") and tok.text == text or (tok.kind == "id" and tok.text.upper() == text):
            self.i += 1
            return True
        return False

    def expect(self, text: str) -> Tok:
        tok = self.take()
        if not (tok.text == text or tok.text.upper() == text):
            raise SyntaxError(f"第 {tok.line} 行: 期望 {text}, 实际 {tok.text!r}")
        return tok

    def at_word(self, *words: str) -> bool:
        tok = self.peek()
        return tok.kind in ("id", "kw") and tok.text.upper() in words

    # 功能块
    def parse_fb(self) -> dict[str, Any]:
        is_func = self.at_word("FUNCTION")
        self.take()  # FUNCTION_BLOCK / FUNCTION
        name = self.take().text
        decls: dict[str, list[tuple[str, TypeSpec, Any]]] = {}
        if is_func:  # FUNCTION 名 : 返回类型 —— 返回值当作与函数同名的输出变量
            self.expect(":")
            decls["VAR_OUTPUT"] = [(name, self.parse_type(), None)]
        while True:
            if self.at_word("VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR_TEMP", "VAR"):
                sect = self.take().text.upper()
                if sect == "VAR" and self.at_word("CONSTANT"):
                    self.take()
                    sect = "VAR_CONSTANT"
                elif sect == "VAR" and self.at_word("RETAIN"):
                    self.take()
                decls.setdefault(sect, []).extend(self.parse_decl_list("END_VAR"))
            elif self.at_word("CONST"):
                self.take()
                decls.setdefault("VAR_CONSTANT", []).extend(self.parse_decl_list("END_CONST"))
            else:
                break
        self.accept("BEGIN")
        end = "END_FUNCTION" if is_func else "END_FUNCTION_BLOCK"
        body = self.parse_block(end)
        self.expect(end)
        return {"name": name, "decls": decls, "body": body, "is_func": is_func}

    def parse_types(self) -> dict[str, list[tuple[str, TypeSpec, Any]]]:
        """TYPE name : STRUCT ... END_STRUCT; END_TYPE（一个文件可有多个）。"""
        out = {}
        while self.peek().kind != "eof":
            self.expect("TYPE")
            name = self.take().text
            self.expect(":")
            self.expect("STRUCT")
            out[name] = self.parse_decl_list("END_STRUCT")
            self.accept(";")
            self.expect("END_TYPE")
            self.accept(";")
        return out

    def parse_decl_list(self, end: str) -> list[tuple[str, TypeSpec, Any]]:
        out = []
        while not self.at_word(end):
            names = [self.take().text]
            while self.accept(","):
                names.append(self.take().text)
            if self.at_word("AT"):
                self.take()
                self.take()  # %IX0.0 之类, 本解释器不处理地址
            self.expect(":")
            t = self.parse_type()
            init = None
            if self.accept(":="):
                init = self.parse_expr()
            self.expect(";")
            out.extend((n, t, init) for n in names)
        self.take()
        return out

    def parse_type(self) -> TypeSpec:
        tok = self.take()
        n = tok.text.upper()
        if n == "ARRAY":
            self.expect("[")
            lo = self.parse_expr()
            self.expect("..")
            hi = self.parse_expr()
            self.expect("]")
            self.expect("OF")
            elem = self.parse_type()
            return TypeSpec("ARRAY", _const_int(lo), _const_int(hi), elem)
        if n == "STRING" and self.accept("["):
            self.parse_expr()
            self.expect("]")
        return TypeSpec(tok.text)

    # 语句
    def parse_block(self, *ends: str) -> list[Any]:
        stmts = []
        while not self.at_word(*ends) and self.peek().kind != "eof":
            if self.accept(";"):
                continue
            stmts.append(self.parse_stmt())
        return stmts

    def parse_stmt(self) -> Any:
        tok = self.peek()
        line = tok.line
        if self.accept("IF"):
            branches = []
            cond = self.parse_expr()
            self.expect("THEN")
            branches.append((cond, self.parse_block("ELSIF", "ELSE", "END_IF")))
            els: list[Any] = []
            while True:
                if self.accept("ELSIF"):
                    cond = self.parse_expr()
                    self.expect("THEN")
                    branches.append((cond, self.parse_block("ELSIF", "ELSE", "END_IF")))
                elif self.accept("ELSE"):
                    els = self.parse_block("END_IF")
                else:
                    break
            self.expect("END_IF")
            self.accept(";")
            return ("if", branches, els, line)
        if self.accept("CASE"):
            sel = self.parse_expr()
            self.expect("OF")
            cases = []
            els = []
            while not self.at_word("END_CASE"):
                if self.accept("ELSE"):
                    els = self.parse_block("END_CASE")
                    break
                labels = [self.parse_label()]
                while self.accept(","):
                    labels.append(self.parse_label())
                self.expect(":")
                cases.append((labels, self.parse_case_body()))
            self.expect("END_CASE")
            self.accept(";")
            return ("case", sel, cases, els, line)
        if self.accept("FOR"):
            var = self.take().text
            self.expect(":=")
            a = self.parse_expr()
            self.expect("TO")
            b = self.parse_expr()
            step = ("num", 1)
            if self.accept("BY"):
                step = self.parse_expr()
            self.expect("DO")
            body = self.parse_block("END_FOR")
            self.expect("END_FOR")
            self.accept(";")
            return ("for", var, a, b, step, body, line)
        if self.accept("RETURN"):
            self.accept(";")
            return ("return", line)
        target = self.parse_lvalue()
        if self.accept(":="):
            val = self.parse_expr()
            self.expect(";")
            return ("assign", target, val, line)
        if self.accept("("):
            args = self.parse_call_args()
            self.expect(";")
            return ("call", target, args, line)
        raise SyntaxError(f"第 {line} 行: 看不懂的语句 {tok.text!r}")

    def parse_label(self) -> Any:
        a = self.parse_expr()
        if self.accept(".."):
            return ("range", a, self.parse_expr())
        return a

    def parse_case_body(self) -> list[Any]:
        # CASE 分支一直到下一个“标签:”或 ELSE/END_CASE
        stmts = []
        while True:
            if self.at_word("ELSE", "END_CASE"):
                return stmts
            if self._looks_like_label():
                return stmts
            if self.accept(";"):
                continue
            stmts.append(self.parse_stmt())

    def _looks_like_label(self) -> bool:
        j = self.i
        depth = 0
        while True:
            tok = self.t[j]
            if tok.kind == "eof":
                return False
            if tok.text in ("(", "["):
                depth += 1
            elif tok.text in (")", "]"):
                depth -= 1
            elif depth == 0 and tok.text == ":":
                return True
            elif depth == 0 and tok.text in (":=", ";", "=>") or tok.kind == "kw" and tok.text in (
                "IF", "CASE", "FOR", "RETURN", "THEN", "DO"
            ):
                return False
            j += 1

    def parse_call_args(self) -> list[tuple[str, str, Any]]:
        args = []
        if self.accept(")"):
            return args
        while True:
            if self.peek(1).text in (":=", "=>"):
                name = self.take().text
                op = self.take().text
                args.append((name, op, self.parse_lvalue() if op == "=>" else self.parse_expr()))
            else:
                args.append(("", ":=", self.parse_expr()))
            if self.accept(")"):
                return args
            self.expect(",")

    def parse_lvalue(self) -> Any:
        tok = self.take()
        if tok.kind != "id":
            raise SyntaxError(f"第 {tok.line} 行: 期望变量名, 实际 {tok.text!r}")
        node: Any = ("var", tok.text)
        while True:
            if self.peek().text == "." and self.peek(1).kind in ("id", "kw"):
                self.take()
                node = ("member", node, self.take().text)
            elif self.peek().text == "[":
                self.take()
                idx = self.parse_expr()
                self.expect("]")
                node = ("index", node, idx)
            else:
                return node

    # 表达式（优先级从低到高）
    def parse_expr(self) -> Any:
        node = self.parse_xor()
        while self.accept("OR"):
            node = ("bin", "OR", node, self.parse_xor())
        return node

    def parse_xor(self) -> Any:
        node = self.parse_and()
        while self.accept("XOR"):
            node = ("bin", "XOR", node, self.parse_and())
        return node

    def parse_and(self) -> Any:
        node = self.parse_cmp()
        while self.accept("AND") or self.accept("&"):
            node = ("bin", "AND", node, self.parse_cmp())
        return node

    def parse_cmp(self) -> Any:
        node = self.parse_add()
        while self.peek().text in ("=", "<>", "<", ">", "<=", ">="):
            op = self.take().text
            node = ("bin", op, node, self.parse_add())
        return node

    def parse_add(self) -> Any:
        node = self.parse_mul()
        while self.peek().text in ("+", "-"):
            op = self.take().text
            node = ("bin", op, node, self.parse_mul())
        return node

    def parse_mul(self) -> Any:
        node = self.parse_unary()
        while self.peek().text in ("*", "/") or self.at_word("MOD"):
            op = self.take().text.upper()
            node = ("bin", op, node, self.parse_unary())
        return node

    def parse_unary(self) -> Any:
        if self.accept("NOT"):
            return ("not", self.parse_unary())
        if self.accept("-"):
            return ("neg", self.parse_unary())
        return self.parse_primary()

    def parse_primary(self) -> Any:
        tok = self.peek()
        if self.accept("("):
            node = self.parse_expr()
            self.expect(")")
            return node
        if tok.kind == "num":
            self.take()
            return ("num", _parse_num(tok.text))
        if tok.kind == "str":
            self.take()
            return ("num", tok.text[1:-1])
        if tok.kind == "kw" and tok.text in ("TRUE", "FALSE"):
            self.take()
            return ("num", tok.text == "TRUE")
        if tok.kind == "id" and self.peek(1).text == "(":
            name = self.take().text
            self.take()
            return ("func", name.upper(), self.parse_call_args())
        return self.parse_lvalue()


def _parse_num(text: str) -> int | float:
    if "#" in text:
        head, _, rest = text.partition("#")
        if head in ("16", "2"):
            return int(rest.replace("_", ""), int(head))
        return _parse_num(rest)  # DWORD#1 / DINT#5 / DWORD#16#FF
    if "." in text:
        return float(text)
    return int(text.replace("_", ""))


def _const_int(node: Any) -> int:
    if node[0] == "num":
        return int(node[1])
    if node[0] == "neg":
        return -_const_int(node[1])
    raise SyntaxError("数组上下界只支持整数常量")


# --------------------------------------------------------------------------- 运行

class _Return(Exception):
    pass


class NativeTON:
    """FB_TON（真实毫秒）。"""

    def __init__(self, sim: "Sim"):
        self.sim = sim
        self.vars = {"IN": False, "PT": 0, "Q": False, "ET": 0}
        self._start: int | None = None

    def call(self) -> None:
        v = self.vars
        pt = v["PT"] if v["PT"] > 0 else 0
        if not v["IN"]:
            self._start = None
            v["Q"], v["ET"] = False, 0
            return
        if pt == 0:
            v["Q"], v["ET"] = True, 0
            return
        if self._start is None:
            self._start = self.sim.now_ms
        et = min(self.sim.now_ms - self._start, pt)
        v["ET"], v["Q"] = et, et >= pt


class NativeTrig:
    def __init__(self, sim: "Sim", rising: bool):
        self.vars = {"IN": False, "Q": False}
        self.rising = rising
        self._last = False

    def call(self) -> None:
        cur = bool(self.vars["IN"])
        self.vars["Q"] = (cur and not self._last) if self.rising else (self._last and not cur)
        self._last = cur


class Instance:
    def __init__(self, sim: "Sim", fb: dict[str, Any]):
        self.sim = sim
        self.fb = fb
        self.vars: dict[str, Any] = {}
        self.consts: dict[str, Any] = {}
        for name, t, init in fb["decls"].get("VAR_CONSTANT", []):
            self.consts[name] = self._eval(init) if init is not None else default_value(t, sim)
        for sect, items in fb["decls"].items():
            if sect == "VAR_CONSTANT":
                continue
            for name, t, init in items:
                self.vars[name] = self._make(t, init)
        self._temps = fb["decls"].get("VAR_TEMP", [])

    def _make(self, t: TypeSpec, init: Any) -> Any:
        if t.name.upper() == "ARRAY":
            items = [default_value(t.elem, self.sim) for _ in range(t.lo, t.hi + 1)]
            return ArrayVal(t.lo, items)
        return self._eval(init) if init is not None else default_value(t, self.sim)

    def bind(self, name: str, value: Any) -> None:
        """VAR_IN_OUT 按引用：直接把外部对象挂进来（dict/数组可变，块内改动外部可见）。"""
        self.vars[name] = value

    def call(self) -> None:
        for name, t, init in self._temps:
            self.vars[name] = self._make(t, init)
        try:
            self._exec(self.fb["body"])
        except _Return:
            pass

    # 访问
    def _lookup(self, name: str) -> Any:
        if name in self.vars:
            return self.vars[name]
        if name in self.consts:
            return self.consts[name]
        raise NameError(f"{self.fb['name']}: 未声明的变量 {name}")

    def _get(self, node: Any) -> Any:
        kind = node[0]
        if kind == "var":
            return self._lookup(node[1])
        if kind == "member":
            base = self._get(node[1])
            return base.vars[node[2]] if isinstance(base, (Instance, NativeTON, NativeTrig)) else base[node[2]]
        if kind == "index":
            arr = self._get(node[1])
            idx = int(self._eval(node[2]))
            if not arr.lo <= idx < arr.lo + len(arr):
                raise IndexError(f"{self.fb['name']}: 数组下标越界 {idx}")
            return arr[idx - arr.lo]
        raise TypeError(node)

    def _set(self, node: Any, value: Any) -> None:
        kind = node[0]
        if kind == "var":
            if node[1] in self.consts:
                raise PermissionError(f"{self.fb['name']}: 给常量 {node[1]} 赋值")
            if node[1] not in self.vars:
                raise NameError(f"{self.fb['name']}: 未声明的变量 {node[1]}")
            self.vars[node[1]] = value
        elif kind == "member":
            base = self._get(node[1])
            if isinstance(base, (Instance, NativeTON, NativeTrig)):
                base.vars[node[2]] = value
            else:
                base[node[2]] = value
        elif kind == "index":
            arr = self._get(node[1])
            idx = int(self._eval(node[2]))
            if not arr.lo <= idx < arr.lo + len(arr):
                raise IndexError(f"{self.fb['name']}: 数组下标越界 {idx}")
            arr[idx - arr.lo] = value
        else:
            raise TypeError(node)

    # 语句
    def _exec(self, stmts: list[Any]) -> None:
        for st in stmts:
            kind = st[0]
            if kind == "assign":
                self._set(st[1], self._eval(st[2]))
            elif kind == "call":
                inst = self._get(st[1])
                for name, op, val in st[2]:
                    if op == ":=":
                        inst.vars[name] = self._eval(val)
                inst.call()
                for name, op, val in st[2]:
                    if op == "=>":
                        self._set(val, inst.vars[name])
            elif kind == "if":
                for cond, body in st[1]:
                    if self._eval(cond):
                        self._exec(body)
                        break
                else:
                    self._exec(st[2])
            elif kind == "case":
                sel = self._eval(st[1])
                for labels, body in st[2]:
                    if any(self._label_match(lab, sel) for lab in labels):
                        self._exec(body)
                        break
                else:
                    self._exec(st[3])
            elif kind == "for":
                var, a, b, step = st[1], self._eval(st[2]), self._eval(st[3]), self._eval(st[4])
                i = a
                while (i <= b) if step > 0 else (i >= b):
                    self.vars[var] = i
                    self._exec(st[5])
                    i = self.vars[var] + step
            elif kind == "return":
                raise _Return()
            else:
                raise TypeError(st)

    def _label_match(self, lab: Any, sel: Any) -> bool:
        if lab[0] == "range":
            return self._eval(lab[1]) <= sel <= self._eval(lab[2])
        return self._eval(lab) == sel

    # 表达式
    def _eval(self, node: Any) -> Any:
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind in ("var", "member", "index"):
            return self._get(node)
        if kind == "not":
            v = self._eval(node[1])
            return (not v) if isinstance(v, bool) else (~v & 0xFFFFFFFF)
        if kind == "neg":
            return -self._eval(node[1])
        if kind == "bin":
            op, a, b = node[1], self._eval(node[2]), self._eval(node[3])
            if op == "AND":
                return (a and b) if isinstance(a, bool) else (a & b)
            if op == "OR":
                return (a or b) if isinstance(a, bool) else (a | b)
            if op == "XOR":
                return (a != b) if isinstance(a, bool) else (a ^ b)
            return {
                "=": lambda: a == b, "<>": lambda: a != b, "<": lambda: a < b, ">": lambda: a > b,
                "<=": lambda: a <= b, ">=": lambda: a >= b, "+": lambda: a + b, "-": lambda: a - b,
                "*": lambda: a * b, "/": lambda: int(a / b), "MOD": lambda: a % b,
            }[op]()
        if kind == "func":
            name, args = node[1], [self._eval(v) for _, _, v in node[2]]
            if name == "SHL":
                return (args[0] << args[1]) & 0xFFFFFFFF
            if name == "SHR":
                return (args[0] & 0xFFFFFFFF) >> args[1]
            if name == "LEN":
                return len(args[0])
            if "_TO_" in name:
                return args[0]
            fc = self.sim.funcs.get(name)
            if fc is not None:  # 用户 FC：每次调用新建实例，按引脚名或位置传参
                inst = Instance(self.sim, fc)
                inputs = [n for n, _, _ in fc["decls"].get("VAR_INPUT", [])]
                for pos, (pname, _, _) in enumerate(node[2]):
                    inst.vars[pname or inputs[pos]] = args[pos]
                inst.call()
                return inst.vars[fc["name"]]
            raise NameError(f"不支持的函数 {name}")
        raise TypeError(node)


class Sim:
    """仿真器：装源码、建实例、推进时钟。"""

    def __init__(self) -> None:
        self.now_ms = 0
        self.fbs: dict[str, dict[str, Any]] = {}
        self.structs: dict[str, list[tuple[str, TypeSpec, Any]]] = {}
        self.funcs: dict[str, dict[str, Any]] = {}  # 键为大写函数名

    def load(self, path: Path) -> None:
        src = path.read_text(encoding="utf-8")
        parser = Parser(tokenize(src))
        if parser.at_word("TYPE"):
            self.structs.update(parser.parse_types())
            return
        fb = parser.parse_fb()
        if fb["is_func"]:
            self.funcs[fb["name"].upper()] = fb
        else:
            self.fbs[fb["name"]] = fb

    def new_struct(self, type_name: str) -> dict[str, Any]:
        holder = Instance.__new__(Instance)  # 只借用初值求值
        holder.sim, holder.vars, holder.consts, holder.fb = self, {}, {}, {"name": type_name}
        return {
            name: (holder._eval(init) if init is not None else default_value(t, self))
            for name, t, init in self.structs[type_name]
        }

    def new_instance(self, type_name: str) -> Any:
        if type_name == "FB_TON":
            return NativeTON(self)
        if type_name in ("FB_R_TRIG", "R_TRIG"):
            return NativeTrig(self, True)
        if type_name in ("FB_F_TRIG", "F_TRIG"):
            return NativeTrig(self, False)
        if type_name in self.fbs:
            return Instance(self, self.fbs[type_name])
        raise NameError(f"未装载的类型 {type_name}")
