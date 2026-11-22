"""PGSN XML compiler: purely syntactic mapping from XML to pgsn.dsl Terms.

XML parsing builds a single Term; all evaluation is deferred to fully_eval().
Semantic errors surface as non-terminating reduction.
"""

import copy
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple

from pgsn.config import Config, get_config
from pgsn.jail import JailError, is_within
from pgsn.dsl import (
    variable, string, list_term, record, empty_record, let, let_vars,
    lambda_abs, lambda_abs_keywords, lambda_abs_vars,
    fix, map_term, fold, foldr, concat, cons, head, tail, index, is_empty,
    repeat,
    list_all, integer_sum, integer,
    true, false, if_then_else, guard,
    equal, less_than, plus, minus, times, div, mod,
    define_class, instantiate, type_of, is_subtype,
    base_class, undefined, empty,
    boolean_and, boolean_or, boolean_not,
    has_label, add_attribute, remove_attribute, overwrite_record,
    format_string,
    Term,
)
from pgsn.gsn import (
    goal, strategy, solution, context, assumption, defeater,
    goal_class, strategy_class, solution_class,
    context_class, assumption_class, gsn_class,
    support_class, undeveloped_class, defeater_class,
    undeveloped, immediate, solution_as_goal,
)


class PGSNError(Exception):
    pass


# ------------------------------------------------------------------ #
# The unit of compilation
# ------------------------------------------------------------------ #

class _Unit:
    """One document being compiled: where its imports resolve, and which
    documents are already open around it.

    `cwd` is the directory relative import paths are resolved against, and
    `root` is the boundary they may not cross — the same pair of notions a
    chroot gives a process.  `..` is therefore allowed as long as the result
    stays below `root`.

    `visiting` holds the documents whose compilation encloses this one, the
    entry document included, so that an import returning to one of them is a
    cycle rather than a file to open a second time.

    Entering an import yields a new `_Unit`: a jailed path (``/name/...``)
    switches `root` to that jail's root, while a relative path keeps the
    current `root`.  Crossing from one jail into another is only possible by
    naming the target jail explicitly; a relative path can never climb back
    out into the jail one came from.

    `root` and `cwd` are both None for a document compiled from a string with
    no jail of its own; such a document can only use jailed paths.

    `modules` is shared by every unit of one compilation: the modules compiled
    so far, which the entry document binds once at its head.

    Whatever a compiler needs to know beyond the element in front of it
    belongs here, which is why the compilers below take one of these and
    nothing else.
    """

    __slots__ = ("root", "cwd", "config", "visiting", "modules")

    def __init__(self, root: Path | None, cwd: Path | None, config: Config,
                 visiting: frozenset[Path] = frozenset(),
                 modules: "_Modules | None" = None):
        self.root = root
        self.cwd = cwd
        self.config = config
        self.visiting = visiting
        self.modules = _Modules() if modules is None else modules

    @classmethod
    def for_entry(cls, path: Path, config: Config) -> "_Unit":
        """Unit for an entry document opened by path.

        If the document lives inside a registered jail, that jail confines it.
        Otherwise its own directory becomes an implicit jail, so a document
        opened directly can still import its neighbours but nothing above them.

        The document counts as visiting itself, so an import that comes back
        round to it is reported as the cycle it is.
        """
        parent = path.parent
        root = config.jails.containing_root(path) or parent
        return cls(root=root, cwd=parent, config=config,
                   visiting=frozenset({path}))

    @classmethod
    def for_jail(cls, name: str, config: Config) -> "_Unit":
        """Unit for a document considered to live at the root of a jail."""
        try:
            root = config.jails.root_of(name)
        except JailError as exc:
            raise PGSNError(str(exc)) from None
        return cls(root=root, cwd=root, config=config)

    @classmethod
    def unrooted(cls, config: Config) -> "_Unit":
        """Unit with no directory of its own: jailed paths only."""
        return cls(root=None, cwd=None, config=config)

    def enter(self, spec: str) -> tuple["_Unit", Path]:
        """The unit for an imported file, and the path it was found at.

        Resolving the path and recording that the file is open are one step.
        Every import passes through here, so no document can be entered
        without extending `visiting`, and a cycle is reported before the file
        it would close is read.
        """
        root, path = self._resolve(spec)
        if path in self.visiting:
            raise PGSNError(f"Circular import: {path}")
        return _Unit(root=root, cwd=path.parent, config=self.config,
                     visiting=self.visiting | {path},
                     modules=self.modules), path

    def _resolve(self, spec: str) -> tuple[Path, Path]:
        """The confinement root an import lands in, and the file it names."""
        if not spec:
            raise PGSNError("<from> requires a non-empty 'file' attribute")

        if spec.startswith("/"):
            try:
                return self.config.jails.resolve(spec)
            except JailError as exc:
                raise PGSNError(str(exc)) from None

        if "\\" in spec:
            raise PGSNError(
                f"Unsafe file path: {spec!r} (backslashes are not allowed)")
        if Path(spec).is_absolute() or Path(spec).drive:
            # A drive-qualified path on Windows; '/'-rooted paths went above.
            raise PGSNError(
                f"Unsafe file path: {spec!r} (absolute paths must name a jail)")
        if self.cwd is None or self.root is None:
            raise PGSNError(
                "Relative imports are not allowed here; "
                "use a jailed path '/<jail>/...' instead")

        try:
            candidate = (self.cwd / spec).resolve()
        except (OSError, RuntimeError) as exc:
            raise PGSNError(f"Cannot resolve {spec!r}: {exc}") from None
        if not is_within(candidate, self.root):
            raise PGSNError(
                f"Unsafe file path: {spec!r} escapes {str(self.root)!r}")
        if not candidate.is_file():
            raise PGSNError(f"No such file: {spec!r}")
        return self.root, candidate


class _Modules:
    """The modules one compilation has compiled, each under a name of its own.

    A file is compiled once however many times it is imported, and the entry
    document binds every module it reaches once, at its head; an import is an
    application of that binding to the import's arguments. Embedding the
    module at every import instead made the compiled term, and the time spent
    building it and walking it, grow with the number of import paths -- which
    is exponential in the depth of the imports.

    Moving a module out to the head of the document is sound because a module
    is closed (`_compile_closed_module` rejects one that is not), so nothing between
    the head and the import can capture its names. A file is identified by its
    path together with the root it was reached under, since the root decides
    where the file's own imports may resolve.

    The bindings are kept in the order the modules were finished, and a module
    is finished only after every module it imports, so each binding refers to
    earlier ones only.
    """

    __slots__ = ("_names", "bindings")

    def __init__(self):
        self._names: dict[tuple[Path, Path], str] = {}
        self.bindings: list[tuple[str, Term]] = []

    def name_of(self, root: Path, path: Path) -> str | None:
        return self._names.get((root, path))

    def add(self, root: Path, path: Path, term: Term) -> str:
        # Not an identifier, so no document can write it, and distinct from
        # every reserved alias, which is one.
        name = f"{_RESERVED_PREFIX}module:{len(self.bindings)}"
        self._names[(root, path)] = name
        self.bindings.append((name, term))
        return name

    def names(self) -> set[str]:
        return {name for name, _ in self.bindings}


# ------------------------------------------------------------------ #
# How a document becomes a term
#
# Compilation is four passes, and what separates them is how much each one is
# allowed to know about the element in front of it:
#
#   1. surface syntax   the document as written                (_check_source)
#   2. desugaring       var=, expr=, as=, <if>, <cases>             (_desugar)
#   3. deep syntax      the same document with no shorthand left in it.
#                       Element-specific attributes -- <apply template=>,
#                       <get key= of=>, <send method= to=> -- are not
#                       shorthand and survive this far
#   4. terms            the compilers below read deep syntax     (_expr, _e_*)
#
# The rules in pass 2 are element-agnostic: each reads an attribute and
# rewrites the element carrying it, whatever element that is. `<tag var="x"/>`
# means `<tag><var name="x"/></tag>` for every tag, with no exception to
# remember and none to get wrong. An element-specific attribute is left alone
# until pass 4, where that element's own compiler maps it onto a term.
#
# The order is what keeps the two kinds from interfering. When they were
# interleaved -- expand `expr=`, rewrite `<apply template=>`, expand `var=` --
# the generic rules met elements the specific ones had already restructured,
# and `<apply template="f" var="x"/>` was rejected by a rule that the longhand
# it stands for never met.
# ------------------------------------------------------------------ #


# ------------------------------------------------------------------ #
# Names
#
# A name must be an identifier and must not begin with an underscore.
#
# The identifier part keeps `<var>` and `<expr>` in agreement: an expression is
# parsed by Python's parser, so a name that is not an identifier could be
# introduced by a <def> and then never referred to from an expression.
#
# The underscore is what desugaring reserves for itself. It needs names the
# document cannot rebind — that is what lets `<expr>` promise that `1 + 2` is
# addition — and a prefix no document may use provides them. The check runs
# over the source tree before any expansion, so the names desugaring introduces
# are not themselves subject to it.
# ------------------------------------------------------------------ #

_RESERVED_PREFIX = "_"

# The name an imported module's record is bound to. Reserved, so a document
# can neither read it nor interfere with it.
_MODULE_VAR = _RESERVED_PREFIX + "module"

# Attributes holding the name of a *variable*, by element. `var` is shorthand
# for a <var> child and is accepted on any element, so it is checked
# everywhere. Record labels — <get key=>, <attribute name=>, <dt key=>,
# <send method=> — are a separate namespace and are deliberately not
# reserved.
_NAME_ATTRS: dict[str, tuple[str, ...]] = {
    "def":    ("name", "typeOf"),
    "param":  ("name",),
    "var":    ("name", "typeOf"),
    "from":   ("as",),
    "import": ("name", "as"),
    "apply":  ("template",),
    "get":    ("of",),
    "send":   ("to",),
    # A keyword argument's name has to match a parameter's, so the two share
    # the restriction even though the argument does not bind anything.
    "arg":    ("name",),
}


# The keywords of the expression syntax: Python's, as of Python 3.12, since
# <expr> reads expressions the way Python does. They are not names, so that
# every name a <def> can bind can also be written in an <expr>. The list is
# written out rather than taken from Python, so that PGSN does not change
# when Python does.
_KEYWORDS = frozenset({
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
    "while", "with", "yield",
})


def _is_name(s: str) -> bool:
    """A letter, then letters, digits and underscores; not a keyword.

    Letters are Unicode letters, so a Japanese name is a name.
    """
    return (bool(s) and s[0].isalpha()
            and all(c.isalnum() or c == "_" for c in s)
            and s not in _KEYWORDS)


def _check_name(name: str, where: str = "") -> None:
    if name.startswith(_RESERVED_PREFIX) or not _is_name(name):
        raise _name_error(name, where)


def _name_error(name: str, where: str = "") -> PGSNError:
    if name.startswith(_RESERVED_PREFIX):
        reason = ("a name may not begin with an underscore; "
                  "those are reserved by the implementation")
    elif name in _KEYWORDS:
        reason = ("it is a keyword of the expression syntax, which has "
                  "Python's keywords")
    else:
        reason = ("a name must begin with a letter and continue with letters, "
                  "digits or underscores")
    return PGSNError(f"{name!r} is not a valid name{where}: {reason}.")


def _check_source(elem: ET.Element) -> None:
    """Check the document as written, before any of it is rewritten.

    The check below is only possible here: whether a name is reserved is a
    question about how the document spells it, and desugaring introduces
    reserved names on purpose.
    """
    _check_names(elem)
    for child in elem:
        _check_source(child)


def _check_names(elem: ET.Element) -> None:
    """Reject invalid or reserved names on one element."""
    for attr in ("var",) + _NAME_ATTRS.get(elem.tag, ()):
        value = elem.get(attr)
        if value is None:
            continue
        _check_name(value, f' in <{elem.tag} {attr}="{value}">')


# ------------------------------------------------------------------ #
# <expr>: infix notation for the terms that are already expressible
#
# The text of an <expr> is parsed by the grammar below, a subset of Python's
# expressions read the way Python reads them, and *translated* into the XML
# the document could have written by hand, at the place the <expr> stands: a
# name is a <var>, resolved in the scope of that place like any other.
# Nothing is evaluated, and the grammar has no form that `<apply>`, `<get>`
# or a literal could not write, so the syntax cannot reach anything more.
#
#   expression  := disjunction ("if" disjunction "else" expression)?
#   disjunction := conjunction ("or" conjunction)*
#   conjunction := inversion ("and" inversion)*
#   inversion   := "not" inversion | comparison
#   comparison  := sum (compare_op sum)*          (chains as in Python)
#   sum         := term (("+" | "-") term)*
#   term        := factor (("*" | "//" | "%") factor)*
#   factor      := ("+" | "-") factor | primary
#   primary     := atom ("." word | "(" arguments ")")*
#   arguments   := (argument ("," argument)* ","?)?
#   argument    := expression | name "=" expression
#   atom        := name | "True" | "False" | integer | string+
#                | "(" expression ")"
#
# The parser is PGSN's own rather than Python's, so that the language does
# not change when Python's grammar does.
#
# Operators, `True` and `False` expand to the reserved alias of a builtin, so
# that `1 + 2` means addition whatever the surrounding document binds.
# ------------------------------------------------------------------ #

_BIN_OPS = {"+": "plus", "-": "minus", "*": "times", "//": "div", "%": "mod"}

_COMPARE_OPS = {"==", "!=", "<", "<=", ">", ">="}

_NUMBER = re.compile(r"""
    (?P<float>[0-9][0-9_]*\.[0-9_]*([eE][-+]?[0-9_]+)?
             |\.[0-9][0-9_]*([eE][-+]?[0-9_]+)?
             |[0-9][0-9_]*[eE][-+]?[0-9_]+)
  | (?P<integer>0[xX][0-9a-fA-F_]+|0[oO][0-7_]+|0[bB][01_]+|[0-9][0-9_]*)
""", re.VERBOSE)

_STRING_START = re.compile(r"(?P<prefix>[rRbBuUfF]{0,2})(?P<quote>'''|\"\"\"|'|\")")

_OP = re.compile(r"//|\*\*|==|!=|<=|>=|[-+*%<>()/.,=]")

_WORD = re.compile(r"\w+")

# Python's simple escapes; octal, \x, \u, \U and \N{...} are read separately.
_SIMPLE_ESCAPES = {"\\": "\\", "'": "'", '"': '"', "a": "\a", "b": "\b",
                   "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
                   "\n": ""}


class _Token(NamedTuple):
    kind: str      # "integer", "string", "op" or "word"
    text: str      # the integer's digits, the op or the word
    column: int
    # A string's parts: literal text and the sources of an f-string's fields,
    # as ("text", value) and ("field", source, column of the source).
    parts: tuple = ()


def _reserved(name: str) -> ET.Element:
    """A <var> naming the reserved alias of a builtin.

    Every builtin is bound twice: under its own name, which a document may
    rebind like any other, and under an underscored alias, which it may not,
    because the reserved-name check rejects such names in source documents.
    Desugaring goes through the alias, so `1 + 2` is addition whatever the
    surrounding document binds `plus` to.
    """
    elem = ET.Element("var")
    elem.set("name", _RESERVED_PREFIX + name)
    return elem


def _call_builtin(name: str, *args: ET.Element) -> ET.Element:
    """Build <apply><var name="_..."/><arg>..</arg>..</apply>."""
    apply_elem = ET.Element("apply")
    apply_elem.append(_reserved(name))
    for a in args:
        arg = ET.SubElement(apply_elem, "arg")
        arg.append(a)
    return apply_elem


def _parse_error(source: str, what: str, column: int | None) -> PGSNError:
    where = "at the end" if column is None else f"at column {column + 1}"
    return PGSNError(f"Cannot parse <expr>: {source!r}: {what} {where}")


def _unescape(body: str) -> str:
    """A string literal's body with its backslash escapes resolved, as Python
    resolves them. An escape Python does not know keeps its backslash."""
    out, i = [], 0
    while i < len(body):
        c = body[i]
        if c != "\\" or i + 1 == len(body):
            out.append(c)
            i += 1
            continue
        e = body[i + 1]
        if e in _SIMPLE_ESCAPES:
            out.append(_SIMPLE_ESCAPES[e])
            i += 2
        elif e in "01234567":
            m = re.match(r"[0-7]{1,3}", body[i + 1:])
            out.append(chr(int(m.group(), 8)))
            i += 1 + len(m.group())
        elif e in "xuU":
            width = {"x": 2, "u": 4, "U": 8}[e]
            digits = body[i + 2:i + 2 + width]
            if not re.fullmatch(r"[0-9a-fA-F]{%d}" % width, digits):
                raise PGSNError(f"'\\{e}' needs {width} hexadecimal digits "
                                f"in {body!r}")
            out.append(chr(int(digits, 16)))
            i += 2 + width
        elif e == "N":
            m = re.match(r"\{([^}]*)\}", body[i + 2:])
            char = None
            if m:
                try:
                    char = unicodedata.lookup(m.group(1))
                except KeyError:
                    pass
            if char is None:
                raise PGSNError(f"'\\N' needs the name of a character in "
                                f"braces, in {body!r}")
            out.append(char)
            i += 2 + len(m.group())
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _format_parts(body: str, *, strict: bool) -> list[tuple]:
    """Split text with `{...}` fields into ("text", t) and ("field", src, at).

    `{{` and `}}` are literal braces. A field runs to the `}` that closes it,
    skipping brackets and string literals inside it, so `{f(x)}` and
    `{"}" + x}` are fields. With `strict`, as for an f-string in an <expr>, a
    brace left single is an error; otherwise it is kept as text, for the
    format string to report when the document is evaluated.
    """
    parts: list[tuple] = []
    text, i = [], 0
    while i < len(body):
        if body.startswith(("{{", "}}"), i):
            text.append(body[i:i + 2])
            i += 2
        elif body[i] == "{":
            end = _field_end(body, i + 1)
            if end is None:
                if strict:
                    raise PGSNError(f"{body!r} opens a field with '{{' and "
                                    "does not close it; write '{{{{' for a "
                                    "literal brace")
                text.append(body[i:])
                break
            if text:
                parts.append(("text", "".join(text)))
                text = []
            parts.append(("field", body[i + 1:end], i + 1))
            i = end + 1
        elif body[i] == "}" and strict:
            raise PGSNError(f"{body!r} has a '}}' that closes no field; "
                            "write '}}}}' for a literal brace")
        else:
            text.append(body[i])
            i += 1
    if text:
        parts.append(("text", "".join(text)))
    return parts


def _field_end(body: str, i: int) -> int | None:
    """Where the field starting at `i` ends: the index of its closing `}`."""
    depth, quote = 0, None
    while i < len(body):
        c = body[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif c == "}":
            if depth == 0:
                return i
            depth -= 1
        i += 1
    return None


def _scan_string(source: str, pos: int) -> tuple[_Token, int] | None:
    """The string literal starting at `pos`, and where it ends, if one does."""
    m = _STRING_START.match(source, pos)
    if m is None:
        return None
    prefix, quote = m.group("prefix").lower(), m.group("quote")
    if prefix not in ("", "r", "u", "f", "rf", "fr", "b", "rb", "br"):
        return None
    if "b" in prefix:
        raise _parse_error(source, "PGSN has no bytes", pos)
    i = m.end()
    while i < len(source):
        if source.startswith(quote, i):
            break
        if source[i] == "\\":
            i += 1
        elif source[i] == "\n" and len(quote) == 1:
            raise _parse_error(source, "a string ends at the end of its line",
                               pos)
        i += 1
    else:
        raise _parse_error(source, "a string is not closed", pos)
    body, end = source[m.end():i], i + len(quote)
    raw, formatted = "r" in prefix, "f" in prefix
    if not formatted:
        value = body if raw else _unescape(body)
        return _Token("string", value, pos, (("text", value),)), end
    parts = []
    for part in _format_parts(body, strict=True):
        if part[0] == "text":
            literal = part[1].replace("{{", "{").replace("}}", "}")
            parts.append(("text", literal if raw else _unescape(literal)))
        else:
            parts.append(("field", part[1], m.end() + part[2]))
    return _Token("string", "", pos, tuple(parts)), end


def _tokens(source: str) -> list[_Token]:
    tokens, pos = [], 0
    while pos < len(source):
        if source[pos].isspace():
            pos += 1
            continue
        string = _scan_string(source, pos)
        if string is not None:
            token, pos = string
            tokens.append(token)
            continue
        m = _NUMBER.match(source, pos)
        if m and m.group("float"):
            raise _parse_error(source, "PGSN has no floating point numbers",
                               pos)
        if m:
            try:
                int(m.group(), 0)
            except ValueError:
                raise _parse_error(source, f"{m.group()!r} is not an integer "
                                   "as Python writes one", pos) from None
            tokens.append(_Token("integer", m.group(), pos))
            pos = m.end()
            continue
        m = _OP.match(source, pos) or _WORD.match(source, pos)
        if m is None:
            raise _parse_error(source, f"unexpected {source[pos]!r}", pos)
        kind = "op" if _OP.match(source, pos) else "word"
        tokens.append(_Token(kind, m.group(), pos))
        pos = m.end()
    return tokens


class _ExprParser:
    """Recursive descent over the grammar at the head of this section."""

    def __init__(self, source: str):
        self.source = source
        self.tokens = _tokens(source)
        self.pos = 0

    def parse(self) -> ET.Element:
        if not self.tokens:
            raise PGSNError("<expr> is empty")
        result = self.expression()
        if self.pos < len(self.tokens):
            raise self.unexpected()
        return result

    # -- tokens ------------------------------------------------------- #

    def peek(self, ahead: int = 0) -> _Token | None:
        i = self.pos + ahead
        return self.tokens[i] if i < len(self.tokens) else None

    def at(self, kind: str, *texts: str, ahead: int = 0) -> bool:
        token = self.peek(ahead)
        return (token is not None and token.kind == kind
                and (not texts or token.text in texts))

    def take(self) -> _Token:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def expect(self, kind: str, text: str) -> None:
        if not self.at(kind, text):
            raise self.unexpected()
        self.take()

    def unexpected(self) -> PGSNError:
        token = self.peek()
        if token is None:
            return _parse_error(self.source, "the expression stops", None)
        what = token.text if token.kind != "string" else "a string"
        return _parse_error(self.source, f"unexpected {what!r}", token.column)

    # -- grammar ------------------------------------------------------ #

    def expression(self) -> ET.Element:
        value = self.disjunction()
        if not self.at("word", "if"):
            return value
        self.take()
        condition = self.disjunction()
        self.expect("word", "else")
        # if_then_else takes its branches unevaluated, so only the one chosen
        # is evaluated, as in Python.
        return _call_builtin("if_then_else", condition, value,
                             self.expression())

    def disjunction(self) -> ET.Element:
        result = self.conjunction()
        while self.at("word", "or"):
            self.take()
            result = _call_builtin("boolean_or", result, self.conjunction())
        return result

    def conjunction(self) -> ET.Element:
        result = self.inversion()
        while self.at("word", "and"):
            self.take()
            result = _call_builtin("boolean_and", result, self.inversion())
        return result

    def inversion(self) -> ET.Element:
        if self.at("word", "not"):
            self.take()
            return _call_builtin("boolean_not", self.inversion())
        return self.comparison()

    def comparison(self) -> ET.Element:
        """`a < b < c` is `a < b and b < c`, as in Python."""
        left = self.sum()
        result = None
        while self.at("op", *_COMPARE_OPS):
            op = self.take().text
            right = self.sum()
            step = _translate_compare(op, left, right)
            result = step if result is None else _call_builtin(
                "boolean_and", result, step)
            left = copy.deepcopy(right)
        return left if result is None else result

    def sum(self) -> ET.Element:
        result = self.term()
        while self.at("op", "+", "-"):
            op = self.take().text
            result = _call_builtin(_BIN_OPS[op], result, self.term())
        return result

    def term(self) -> ET.Element:
        result = self.factor()
        while self.at("op", "*", "//", "%", "/"):
            op = self.take().text
            if op == "/":
                raise PGSNError(
                    "'/' is not defined in <expr>. PGSN has integers only, so "
                    "write '//' for integer division; '/' is reserved for true "
                    "division should a floating point type be added.")
            result = _call_builtin(_BIN_OPS[op], result, self.factor())
        return result

    def factor(self) -> ET.Element:
        if self.at("op", "-"):
            self.take()
            zero = ET.Element("num")
            zero.text = "0"
            return _call_builtin("minus", zero, self.factor())
        if self.at("op", "+"):
            self.take()
            return self.factor()
        value = self.primary()
        if self.at("op", "**"):
            raise PGSNError("'**' is not defined in <expr>: PGSN has no "
                            "builtin for powers.")
        return value

    def primary(self) -> ET.Element:
        value = self.atom()
        while True:
            if self.at("op", "."):
                self.take()
                token = self.peek()
                if (token is None or token.kind != "word"
                        or token.text in _KEYWORDS or token.text[0].isdigit()):
                    raise self.unexpected()
                self.take()
                # A record label is not a name: it reads a field, as <get>.
                get = ET.Element("get")
                get.set("key", token.text)
                get.append(value)
                value = get
            elif self.at("op", "("):
                self.take()
                value = self.call(value)
            else:
                return value

    def call(self, function: ET.Element) -> ET.Element:
        """`f(a, k=b)` is <apply> with the same arguments; `f()` passes the
        empty keyword record, as in the Python API."""
        application = ET.Element("apply")
        application.append(function)
        keywords: set[str] = set()
        while not self.at("op", ")"):
            arg = ET.SubElement(application, "arg")
            if self.at("word") and self.at("op", "=", ahead=1):
                name = self.take().text
                self.take()
                _check_name(name, " in <expr>")
                if name in keywords:
                    raise PGSNError(f"the keyword argument {name!r} is given "
                                    f"twice in <expr>: {self.source!r}")
                keywords.add(name)
                arg.set("name", name)
            elif keywords:
                raise PGSNError("a positional argument follows a keyword "
                                f"argument in <expr>: {self.source!r}")
            arg.append(self.expression())
            if not self.at("op", ","):
                break
            self.take()
        self.expect("op", ")")
        if len(application) == 1:
            ET.SubElement(application, "arg")
        return application

    def atom(self) -> ET.Element:
        token = self.peek()
        if token is None:
            raise self.unexpected()
        match token.kind:
            case "integer":
                self.take()
                elem = ET.Element("num")
                elem.text = str(int(token.text, 0))
                return elem
            case "string":
                parts = []
                while self.at("string"):
                    parts.extend(self.take().parts)
                return _translate_string(parts, self.source)
            case "word" if token.text in ("True", "False"):
                self.take()
                return _reserved(token.text.lower())
            case "word" if token.text == "None":
                raise PGSNError(
                    f"None has no counterpart in PGSN: {self.source!r}")
            case "word" if token.text not in _KEYWORDS:
                self.take()
                _check_name(token.text, " in <expr>")
                elem = ET.Element("var")
                elem.set("name", token.text)
                return elem
            case "op" if token.text == "(":
                self.take()
                inner = self.expression()
                self.expect("op", ")")
                return inner
        raise self.unexpected()


def _translate_compare(op: str, left: ET.Element,
                       right: ET.Element) -> ET.Element:
    """Derive every comparison from `equal` and `less_than`."""
    match op:
        case "==":
            return _call_builtin("equal", left, right)
        case "!=":
            return _call_builtin("boolean_not",
                                 _call_builtin("equal", left, right))
        case "<":
            return _call_builtin("less_than", left, right)
        case ">":
            return _call_builtin("less_than", right, left)
        case "<=":
            # a <= b is not (b < a); using or would evaluate both sides.
            return _call_builtin("boolean_not",
                                 _call_builtin("less_than", right, left))
        case ">=":
            return _call_builtin("boolean_not",
                                 _call_builtin("less_than", left, right))
    raise AssertionError(op)  # only _COMPARE_OPS reach here


def _field_label(source: str, i: int) -> str:
    """The record label a field's value is passed under: the name itself when
    the field is a name, as bare text has always done, else a reserved one."""
    source = source.strip()
    return source if _is_plain_name(source) else f"{_RESERVED_PREFIX}e{i}"


def _is_plain_name(source: str) -> bool:
    return not source.startswith(_RESERVED_PREFIX) and _is_name(source)


def _translate_string(parts: list[tuple], source: str) -> ET.Element:
    """Adjacent literals joined, and an f-string's fields given to
    `format_string`.

    The template of the format string holds labels and nothing else, so a
    field that is an expression is passed under a generated label. A field's
    conversion (`!r`) or format specification (`:>4`) has no counterpart in a
    format string, so it is refused.
    """
    template: list[str] = []
    fields: dict[str, ET.Element] = {}
    for part in parts:
        if part[0] == "text":
            template.append(part[1].replace("{", "{{").replace("}", "}}"))
            continue
        field_source = part[1]
        if not field_source.strip():
            raise PGSNError(f"an f-string has an empty field in <expr>: "
                            f"{source!r}")
        try:
            value = _ExprParser(field_source).parse()
        except PGSNError:
            if re.search(r"![rsa]\s*$|:[^}]*$|=\s*$", field_source):
                raise PGSNError(
                    "a conversion (!r), a format specification (:>4) or a "
                    "'=' is not allowed in an f-string field in <expr>: "
                    f"{source!r}") from None
            raise
        label = _field_label(field_source, len(fields))
        fields.setdefault(label, value)
        template.append("{" + label + "}")
    text_elem = ET.Element("str")
    if not fields:
        text_elem.text = "".join(
            part[1] for part in parts)
        return text_elem
    text_elem.text = "".join(template)
    record_elem = ET.Element("dl")
    for label, value in fields.items():
        dt = ET.SubElement(record_elem, "dt")
        dt.text = label
        dd = ET.SubElement(record_elem, "dd")
        dd.append(value)
    return _call_builtin("format_string", text_elem, record_elem)


def _replace_with(elem: ET.Element, replacement: ET.Element) -> None:
    """Become `replacement`, in place.

    Rewriting is done in place because an element does not know its parent:
    every rule here is handed the element to rewrite, not the list holding it.
    """
    elem.tag = replacement.tag
    elem.attrib.clear()
    elem.attrib.update(replacement.attrib)
    elem.text = replacement.text
    elem[:] = list(replacement)


def _expand_expr(elem: ET.Element) -> None:
    """Replace an <expr> element, in place, with the XML it stands for."""
    if len(elem):
        raise PGSNError("<expr> takes an expression as text, not child elements")
    _replace_with(elem, _ExprParser((elem.text or "").strip()).parse())


def _move_content(src: ET.Element, dst: ET.Element) -> None:
    """Transplant whatever `src` says its value is into `dst`.

    A value can be given as text, as a child element, or through the `var` and
    `expr` shorthands, and a wrapper like <cond> is transparent to all four.
    """
    dst.text = src.text
    for shorthand in ("var", "expr"):
        if shorthand in src.attrib:
            dst.set(shorthand, src.attrib[shorthand])
    for child in list(src):
        dst.append(child)


def _one_child(elem: ET.Element, tag: str, owner: str) -> ET.Element:
    found = [c for c in elem if c.tag == tag]
    if len(found) != 1:
        raise PGSNError(
            f"<{owner}> needs exactly one <{tag}>, found {len(found)}")
    return found[0]


def _expand_if(elem: ET.Element) -> None:
    """<if><cond/><then/><else/> -> an application of the builtin."""
    known = {"cond", "then", "else"}
    unexpected = [c.tag for c in elem if c.tag not in known]
    if unexpected:
        raise PGSNError(
            f"<if> takes <cond>, <then> and <else>; found <{unexpected[0]}>")
    parts = [_one_child(elem, tag, "if") for tag in ("cond", "then", "else")]
    _rewrite_as_conditional(elem, parts)


def _expand_cases(elem: ET.Element) -> None:
    """<cases> is a chain of <case>s ending in an <else>, which is required:
    a conditional with nothing to fall back on would simply get stuck."""
    known = {"case", "else"}
    unexpected = [c.tag for c in elem if c.tag not in known]
    if unexpected:
        raise PGSNError(
            f"<cases> takes <case> and <else>; found <{unexpected[0]}>")
    cases = [c for c in elem if c.tag == "case"]
    if not cases:
        raise PGSNError("<cases> needs at least one <case>")
    if not len(elem) or elem[-1].tag != "else":
        raise PGSNError("<cases> must end in an <else>")

    fallback = elem[-1]
    for case in cases:
        unexpected = [c.tag for c in case if c.tag not in {"cond", "then"}]
        if unexpected:
            raise PGSNError(
                f"<case> takes <cond> and <then>; found <{unexpected[0]}>")

    # Built from the last case outwards, so each conditional is the else of
    # the one before it. `result` is always a wrapper holding the value, the
    # shape the rewriting below expects.
    result = fallback
    for case in reversed(cases):
        branch = ET.Element("if")
        _rewrite_as_conditional(
            branch, [_one_child(case, "cond", "case"),
                     _one_child(case, "then", "case"), result])
        result = ET.Element("else")
        result.append(branch)
    _replace_with(elem, result[0])


def _rewrite_as_conditional(elem: ET.Element, parts: list[ET.Element]) -> None:
    """Turn `elem` into `if_then_else` applied to the three parts.

    The builtin is reached through its reserved name, so `<if>` keeps meaning
    a conditional in a scope that binds `if_then_else` to something else.
    """
    application = ET.Element("apply")
    application.append(_reserved("if_then_else"))
    for part in parts:
        arg = ET.SubElement(application, "arg")
        _move_content(part, arg)
    _replace_with(elem, application)


def _desugar(elem: ET.Element) -> None:
    """Expand the element-agnostic shorthands, in place, everywhere.

    Every rule here rewrites the element that carries it without asking what
    element it is. Nothing element-specific belongs in this pass: see the note
    at the head of the file.
    """
    # <expr> becomes the XML it stands for. That expansion holds no shorthand
    # of its own, so the recursion stops here.
    if elem.tag == "expr":
        _expand_expr(elem)
        return

    # A conditional becomes an application of the builtin, which is then
    # desugared like any other element: its branches may hold more shorthand.
    if elem.tag == "if":
        _expand_if(elem)
    elif elem.tag == "cases":
        _expand_cases(elem)

    # The attribute shorthands. Each says in an attribute what the element's
    # content would otherwise say. `expr=` leaves an <expr> behind for the
    # recursion below, so both spellings of an expression share one expansion.
    _expand_expr_attribute(elem)
    _expand_as_attribute(elem)
    _expand_var_attribute(elem)

    for child in elem:
        _desugar(child)


def _reject_own_content(elem: ET.Element, attr: str) -> None:
    """A shorthand attribute stands for content, so it cannot sit beside it."""
    if len(elem) or (elem.text and elem.text.strip()):
        article = "an" if attr.startswith(("a", "e", "i", "o", "u")) else "a"
        raise PGSNError(
            f"<{elem.tag}> has both {article} {attr!r} attribute and content "
            f"of its own; the attribute is shorthand for the content.")


def _expand_expr_attribute(elem: ET.Element) -> None:
    """<tag expr="1 + 2"/> -> <tag><expr>1 + 2</expr></tag>"""
    if "expr" not in elem.attrib:
        return
    _reject_own_content(elem, "expr")
    ET.SubElement(elem, "expr").text = elem.attrib.pop("expr")


def _expand_var_attribute(elem: ET.Element) -> None:
    """<tag var="x"/> -> <tag><var name="x"/></tag>"""
    if "var" not in elem.attrib:
        return
    _reject_own_content(elem, "var")
    ET.SubElement(elem, "var").set("name", elem.attrib.pop("var"))


# `as` renames an imported name on <from> and <import>. Everywhere else it
# names an element to wrap the content in, which is what lets a <def> hold a
# list or a record without a nesting level whose only job is to be there.
_AS_RENAMES = {"from", "import"}


def _expand_as_attribute(elem: ET.Element) -> None:
    """<tag as="dl">..</tag> -> <tag><dl>..</dl></tag>"""
    if elem.tag in _AS_RENAMES or "as" not in elem.attrib:
        return
    wrapper = ET.Element(elem.attrib.pop("as"))
    wrapper.text, elem.text = elem.text, None
    for child in list(elem):
        elem.remove(child)
        wrapper.append(child)
    elem.append(wrapper)


# The builtins, bound around each compilation unit by `_builtin_scope`.
#
# Every term-valued name the `pgsn` package exports is bound here under the
# same name, so that the two front ends offer the same standard library; see
# tests/test_api_consistency.py, which fails if the two drift apart.
_BUILTINS: dict[str, Term] = {
    "fix": fix, "map_term": map_term, "fold": fold, "foldr": foldr,
    "concat": concat, "list_all": list_all,
    "cons": cons, "head": head, "tail": tail, "index": index, "empty": empty,
    "is_empty": is_empty,
    "repeat": repeat, "integer_sum": integer_sum,
    "equal": equal, "less_than": less_than,
    "guard": guard, "if_then_else": if_then_else,
    "plus": plus, "minus": minus, "times": times, "div": div, "mod": mod,
    "boolean_and": boolean_and, "boolean_or": boolean_or,
    "boolean_not": boolean_not, "true": true, "false": false,
    "has_label": has_label,
    "add_attribute": add_attribute, "remove_attribute": remove_attribute,
    "overwrite_record": overwrite_record, "format_string": format_string,
    "empty_record": empty_record, "undefined": undefined,
    "define_class": define_class, "instantiate": instantiate,
    "type_of": type_of, "is_subtype": is_subtype, "base_class": base_class,
    "goal": goal, "strategy": strategy, "solution": solution,
    "context": context, "assumption": assumption,
    "defeater": defeater,
    "immediate": immediate, "undeveloped": undeveloped,
    "solution_as_goal": solution_as_goal,
    "gsn_class": gsn_class, "goal_class": goal_class,
    "strategy_class": strategy_class, "solution_class": solution_class,
    "context_class": context_class, "assumption_class": assumption_class,
    "support_class": support_class, "undeveloped_class": undeveloped_class,
    "defeater_class": defeater_class,
    # Intuitive aliases for GSN class values
    "Goal": goal_class, "Strategy": strategy_class, "Solution": solution_class,
    "Context": context_class, "Assumption": assumption_class,
    "GSN": gsn_class, "Support": support_class,
    "Defeater": defeater_class,
}

_SUPPORT_TAGS = {"Strategy", "Solution", "Goal", "supportedBy", "undeveloped"}


def _text_to_term(s: str, unit: "_Unit | None" = None) -> Term:
    """Turn user text into a Term.

    Text is a string. A `{...}` in it is a field: what stands between the
    braces is an expression, read as in <expr>, and its value is put in its
    place by `format_string`; `{{` and `}}` are the braces themselves. Text is
    not checked at compile time: a field that cannot be read as an expression,
    and a brace left single, stay in the format string as written, and
    `format_string` reports them when the document is evaluated.
    """
    if "{" not in s and "}" not in s:
        return string(s)
    template: list[str] = []
    fields: dict[str, Term] = {}
    for part in _format_parts(s, strict=False):
        if part[0] == "text":
            template.append(part[1])
            continue
        source = part[1]
        try:
            value = _ExprParser(source.strip()).parse()
        except PGSNError:
            template.append("{" + source + "}")
            continue
        label = _field_label(source, len(fields))
        if label not in fields:
            fields[label] = (variable(label) if label == source.strip()
                             else _expr(value, unit))
        template.append("{" + label + "}")
    return format_string(string("".join(template)))(
        record(fields) if fields else empty_record)


def _resolve(name: str, type_name: str | None = None) -> Term:
    """Every name becomes a variable; nothing is substituted inline.

    What a name denotes is decided by the binder structure around it, and by
    the builtin scope that `_builtin_scope` wraps every compilation unit in.
    A document that binds `head` therefore means its own `head`, rather than
    silently getting the builtin.
    """
    term = variable(name)
    if type_name:
        term = _typed(term, type_name)
    return term


def _typed(term: Term, type_name: str) -> Term:
    """`typeOf`: let the value through only if it satisfies the named type.

    The guard stalls on false, which is how a failed check shows itself: the
    document does not reduce. The type is a variable like any other, so what
    it denotes follows the same scoping as every other name.
    """
    return guard(is_subtype(type_of(term), variable(type_name)))(term)


def _builtin_scope(body: Term) -> Term:
    """Wrap a compilation unit in the scope that gives the builtins meaning.

    Every builtin is bound under two names: its own, which the document may
    rebind like any other, and an underscored alias, which it may not, since
    the reserved-name check rejects such names in source documents. The effect
    is that of an implicit ``<def name="plus"><var name="_plus"/></def>`` at
    the head of every document — a document binding `plus` shadows it, while
    desugaring keeps reaching the builtin through `_plus`.

    Only the names the unit actually leaves free are bound. Binding the whole
    table instead would be equivalent — a name the document never mentions
    cannot be observed — but every compiled document, and every module in it,
    would then carry every builtin, in its term and in the JSON that
    `pgsn compile` writes. A document mentions a handful.

    Which names are free is not decided here. `Term.free_variables` already
    answers it, and has to be right anyway: removing names before evaluation
    depends on the same answer.
    """
    bindings = []
    for spelling in sorted(body.free_variables()):
        term = _BUILTINS.get(spelling.removeprefix(_RESERVED_PREFIX))
        if term is not None:
            bindings.append((variable(spelling), term))
    return let_vars(tuple(bindings), body) if bindings else body


def _thread_lets(bindings: list[tuple[str, Term]], body: Term) -> Term:
    """Fold a binding list into nested let expressions around body."""
    for name, term in reversed(bindings):
        body = let(variable(name), term, body)
    return body


def _keyword_abs(params: list[ET.Element], body: Term, unit: _Unit) -> Term:
    """Abstract `body` over keyword parameters, with the defaults they carry.

    A parameter whose content is a value gives the default for its name; one
    without has none, and an application that leaves it out leaves the name
    unbound. <PGSNModule> and <template> are abstractions of the same shape,
    so they are built the same way.
    """
    defaults = {p.get("name"): _content(p, unit) for p in params if _items(p)}
    return lambda_abs_keywords(
        {p.get("name"): variable(p.get("name")) for p in params},
        body,
        record(defaults) if defaults else empty_record)


def _split_args(items: list[ET.Element | str], unit: _Unit,
                owner: str) -> tuple[list, dict, bool]:
    """
    Collect <arg> children into positional and keyword groups, and say whether
    the keyword record is passed.
    Positional args (no name) must precede keyword args, as in Python.

    The `<arg>` elements are the parameters passed, and one with nothing in it
    passes nothing: a parameter left without a value takes its default. So an
    empty `<arg name="x"/>` leaves `x` at its default, and an empty unnamed
    `<arg/>` passes the keyword record with nothing in it, so that the keyword
    parameters all take their defaults -- `<apply template="f"><arg/></apply>`
    is `f()` in Python. Either counts as a keyword argument, so it comes after
    the positional ones.

    Anything that is not an <arg> is an error rather than something to skip.
    Desugaring expands `var` and `expr` into a child of their own, so skipping
    would turn `<apply template="f" var="x"/>` into an application of `f` to
    nothing at all.
    """
    positional, keyword, record_passed = [], {}, False
    for a in items:
        if isinstance(a, str):
            raise PGSNError(
                f"<{owner}> takes its arguments as <arg> children, "
                f"found the text {a!r}")
        if a.tag != "arg":
            raise PGSNError(
                f"<{owner}> takes its arguments as <arg> children, "
                f"found <{a.tag}>")
        name = a.get("name")
        if name is None and _items(a):
            if record_passed:
                raise PGSNError("positional arg after keyword arg")
            positional.append(_content(a, unit))
        else:
            if _items(a):
                keyword[name] = _content(a, unit)
            record_passed = True
    return positional, keyword, record_passed


# ------------------------------------------------------------------ #
# Document compilers
# ------------------------------------------------------------------ #

def compile_pgsn(path: str | Path, *, config: Config | None = None) -> Term:
    """Compile a <PGSN> document file into a single Term (no evaluation).

    The document is confined to the jail it lives in, or — if it lives in no
    registered jail — to its own directory.
    """
    cfg = get_config(config)
    p = Path(path).resolve()
    return _compile_root(ET.parse(p).getroot(), _Unit.for_entry(p, cfg))


def compile_pgsn_string(xml: str, *, config: Config | None = None,
                        jail: str | None = None) -> Term:
    """Compile a <PGSN> document held in a string into a single Term.

    A document that is not a file has no directory of its own, so there is
    nothing for a relative import to resolve against. Jailed imports
    (``/<jail>/...``) always work; `jail` places the document at the root of a
    registered jail, which is what gives relative imports a meaning as well.
    Naming a directory directly is deliberately not offered: it would make a
    confinement root out of a path nobody registered as one.
    """
    cfg = get_config(config)
    unit = _Unit.for_jail(jail, cfg) if jail is not None else _Unit.unrooted(cfg)
    return _compile_root(ET.fromstring(xml), unit)


def _compile_root(root: ET.Element, unit: _Unit) -> Term:
    """Compile a parsed <PGSN> root element in the unit it was opened as."""
    if root.tag != "PGSN":
        raise PGSNError(f"Expected <PGSN>, got <{root.tag}>")
    _check_source(root)
    _desugar(root)
    body = _builtin_scope(_block(_items(root), unit, "PGSN"))
    # Every module the document reaches, bound once (see _Modules).
    return _thread_lets(unit.modules.bindings, body)


def _compile_module(root: ET.Element, unit: _Unit) -> Term:
    """Compile <PGSNModule> to a function from its arguments to its exports.

    The exports are a record of every name the module's block binds with a
    <def>, so taking a name out of a module is reading a label off a record,
    and the module itself is a value like any other.
    """
    param_elems, items = _split_params(root)
    exports = record({i.get("name"): variable(i.get("name")) for i in items
                      if isinstance(i, ET.Element) and i.tag == "def"})
    body = _thread_lets(_bindings(items, unit, "PGSNModule"), exports)
    # A module is a separate lexical scope, so it needs the builtin scope of
    # its own; the importing document's cannot reach inside it. The wrapping
    # sits outside the abstraction, so the bindings are reduced once rather
    # than once per application.
    return _builtin_scope(_keyword_abs(param_elems, body, unit))


# ------------------------------------------------------------------ #
# Binding sequences  (def / from)
# ------------------------------------------------------------------ #

def _bindings(items: list[ET.Element | str], unit: _Unit,
              owner: str) -> list[tuple[str, Term]]:
    """The bindings a block opens with, in order."""
    result = []
    for item in items:
        if isinstance(item, str):
            raise PGSNError(
                f"<{owner}> has text where a binding was expected: {item!r}. "
                f"A block is bindings and then one value, so only its last "
                f"item is its value.")
        if item.tag == "def":
            result.append(_compile_def(item, unit))
        elif item.tag == "from":
            result.extend(_compile_from(item, unit))
        else:
            raise PGSNError(
                f"<{owner}> takes <def> and <from> before its value, "
                f"found <{item.tag}>")
    return result


def _compile_def(elem: ET.Element, unit: _Unit) -> tuple[str, Term]:
    name = elem.get("name")
    term = _content(elem, unit)

    if elem.get("recursive", "false").lower() == "true":
        term = fix(lambda_abs(variable(name), term))

    type_name = elem.get("typeOf")
    if type_name:
        term = _typed(term, type_name)

    return name, term


def _module_record(elem: ET.Element, unit: _Unit) -> Term:
    """The record a `<from>` denotes: its module applied to its arguments.

    File I/O happens here, at compile time, because the path is a static
    literal. The module is compiled the first time its file is imported and
    bound at the head of the entry document (see _Modules); the import is an
    application of that binding, an ordinary Term that is not evaluated.
    """
    file_path = elem.get("file", "")
    inner, full = unit.enter(file_path)

    name = unit.modules.name_of(inner.root, full)
    if name is None:
        name = unit.modules.add(inner.root, full,
                                _compile_closed_module(file_path, full, inner))

    # Args compiled in the caller's scope — they are Terms, not values yet
    args = {a.get("name"): _content(a, unit) for a in elem.findall("arg")}
    return variable(name)(record(args))


def _compile_closed_module(file_path: str, full: Path, unit: _Unit) -> Term:
    """Compile the module in `full`, which must be closed."""
    root = ET.parse(full).getroot()
    if root.tag != "PGSNModule":
        raise PGSNError(f"Expected <PGSNModule> in {file_path!r}")
    _check_source(root)
    _desugar(root)

    module_term = _compile_module(root, unit)
    # A module takes values from its importer only through its parameters, so
    # a component's argument is the same in every system that imports it with
    # the same arguments. A name the module left free would be bound by
    # whatever happened to be in scope where the module ends up, since nothing
    # in the compiled term marks it as the module's own. The only free names a
    # closed module has are the bindings of the modules it imports.
    free = module_term.free_variables() - unit.modules.names()
    if free:
        raise PGSNError(
            f"The module {file_path!r} uses "
            f"{', '.join(repr(n) for n in sorted(free))}, which it neither "
            f"defines nor takes as a parameter. A module receives values from "
            f"the document that imports it only through its parameters.")
    return module_term


def _e_from(elem: ET.Element, unit: _Unit) -> Term:
    """`<from>` in a value position is the module's record.

        <def name="lib"><from file="lib.xml"/></def>
        <get key="secureGoal" of="lib"/>

    A module is therefore an ordinary value: it can be bound, passed to a
    template, or held in a list, like anything else. Selecting names out of it
    at the point of import remains available and is what `<import>` is for,
    but that form binds names and so belongs in a binding position.
    """
    if elem.get("import") is not None or elem.find("import") is not None:
        raise PGSNError(
            "<from> used as a value denotes the whole module, so it takes no "
            "'import'. Either drop the import and select from the record with "
            "<get>, or move the <from> into a binding position.")
    if elem.get("as") is not None:
        raise PGSNError(
            "'as' renames an imported name, and <from> used as a value "
            "imports none. Bind the module with <def> instead.")
    return _module_record(elem, unit)


def _compile_from(elem: ET.Element, unit: _Unit) -> list[tuple[str, Term]]:
    """`<from>` in a binding position: bring selected names into scope.

    The applied module is bound to a name of its own and each import projects
    a field off that name, so the module occupies one position in the compiled
    term however many names are taken from it. The name is reserved, so no
    document can refer to it, and rebinding it for the next `<from>` in the
    same block is harmless: each projection reads the binding nearest to it.
    """
    single = elem.get("import")
    if single:
        wanted = [(elem.get("as", single), single)]
    else:
        wanted = [(imp.get("as", imp.get("name")), imp.get("name"))
                  for imp in elem.findall("import")]
    if not wanted:
        raise PGSNError(
            "<from> in a binding position needs an 'import'. To bind the "
            "module itself, write it as a value: "
            '<def name="..."><from file="..."/></def>.')

    module = variable(_MODULE_VAR)
    return ([(_MODULE_VAR, _module_record(elem, unit))]
            + [(alias, module(string(exported))) for alias, exported in wanted])


# ------------------------------------------------------------------ #
# Content
#
# The content of an element is a sequence of items in document order: each
# child element, and each run of text between them. Bare text is a string, so
# a run of text is a value like any other and stands wherever a child could:
# `<div>hello</div>` and `<div><str>hello</str></div>` are one document
# written two ways.
#
# Reading content in one place is what keeps that promise. It used to be read
# where it was needed, and each reader saw a different part of it: a value
# written after a binding is the tail of the binding rather than the text of
# the element, so every reader that looked at `elem.text` missed it, and a
# reader that looked at child elements alone missed bare text entirely.
# ------------------------------------------------------------------ #

def _items(parent: ET.Element) -> list[ET.Element | str]:
    """The content of an element, in document order."""
    items: list[ET.Element | str] = []
    text = (parent.text or "").strip()
    if text:
        items.append(text)
    for child in parent:
        items.append(child)
        tail = (child.tail or "").strip()
        if tail:
            items.append(tail)
    return items


def _item(item: ET.Element | str, unit: _Unit) -> Term:
    """The term an item stands for."""
    if isinstance(item, str):
        return _text_to_term(item, unit)
    return _expr(item, unit)


def _content(parent: ET.Element, unit: _Unit) -> Term:
    """The single value an element's content stands for.

    Empty content is the empty string, as bare text is a string: in XML an
    element with nothing in it holds the empty text. What the empty string
    then fails to be is reported with the output, not here.
    """
    items = _items(parent)
    if len(items) == 1:
        return _item(items[0], unit)
    if items:
        raise PGSNError(f"Multiple values in <{parent.tag}>")
    return _text_to_term("")


def _split_params(parent: ET.Element) -> tuple[list[ET.Element],
                                               list[ET.Element | str]]:
    """The <param> elements a definition opens with, and the rest of it."""
    items = _items(parent)
    params: list[ET.Element] = []
    while items and isinstance(items[0], ET.Element) and items[0].tag == "param":
        params.append(items.pop(0))
    return params, items


def _block(items: list[ET.Element | str], unit: _Unit, owner: str) -> Term:
    """Any number of bindings, then the value they are in scope for.

    `<PGSN>`, `<div>` and a template body are all this shape, and the value
    is simply the last item -- a child element or a run of text. An empty
    one is the empty string, as empty content is everywhere.
    """
    if not items:
        return _text_to_term("")
    return _thread_lets(_bindings(items[:-1], unit, owner),
                        _item(items[-1], unit))


def _expr(elem: ET.Element, unit: _Unit) -> Term:
    """The term an element in a value position stands for.

    Which elements those are is `_COMPILERS`, at the foot of this file: it can
    only be written once every compiler it names exists, and an element this
    pass does not know is an error rather than something to skip.
    """
    compiler = _COMPILERS.get(elem.tag)
    if compiler is None:
        raise PGSNError(f"Unknown expression: <{elem.tag}>")
    return compiler(elem, unit)


def _e_var(elem: ET.Element, _unit: _Unit) -> Term:
    """A reference to a name.

    `as="var"` produces a `<var>` with no name, since `as` moves the content
    and leaves the attributes where they were, so the message says so.
    """
    name = elem.get("name")
    if name is None:
        raise PGSNError(
            "<var> needs a 'name' attribute naming the variable, as in "
            '<var name="x"/>. as="var" cannot supply it: `as` moves the '
            "content and leaves the attributes behind.")
    return _resolve(name, elem.get("typeOf"))


def _e_num(elem: ET.Element, _unit: _Unit) -> Term:
    """An integer literal. Bare text is a String, so numbers are written out."""
    if len(elem):
        raise PGSNError("<num> takes text, not child elements")
    text = (elem.text or "").strip()
    try:
        return integer(int(text))
    except ValueError:
        raise PGSNError(f"<num> is not an integer: {text!r}") from None


def _e_str(elem: ET.Element, _unit: _Unit) -> Term:
    """A verbatim string literal.

    Unlike bare text, the content is taken exactly as written: whitespace is
    kept and `{...}` is not interpolated. This is what `<expr>` expands string
    literals into, and what makes a template for `format_string` expressible.
    """
    if len(elem):
        raise PGSNError("<str> takes text, not child elements")
    return string(elem.text or "")


def _e_template(elem: ET.Element, unit: _Unit) -> Term:
    """A function: the parameters it opens with, then the block it stands for.

    A parameter is a keyword parameter unless it says `positional="true"`.
    The two kinds become two layers of abstraction -- positional outside,
    keyword within -- which is the order `Term.__call__` unwinds them in: it
    strips the positional arguments before passing the record of keyword ones.
    """
    param_elems, items = _split_params(elem)
    # The body is a block like <div> and <PGSN>: bindings, then one value.
    term = _block(items, unit, elem.tag)
    if not param_elems:
        return term

    positional, keyword = _split_param_kinds(param_elems)
    if keyword:
        term = _keyword_abs(keyword, term, unit)
    if positional:
        term = lambda_abs_vars(
            tuple(variable(p.get("name")) for p in positional), term)
    return term


def _split_param_kinds(params: list[ET.Element]
                       ) -> tuple[list[ET.Element], list[ET.Element]]:
    """Separate the positional parameters from the keyword ones, in order.

    Positional parameters come first, as in Python, and carry no default:
    there is nothing for a default to stand in for when the argument is
    reached by position rather than by name.
    """
    positional: list[ET.Element] = []
    keyword: list[ET.Element] = []
    for param in params:
        name = param.get("name")
        if param.get("positional", "false").lower() != "true":
            keyword.append(param)
            continue
        if keyword:
            raise PGSNError(
                f"Positional param '{name}' must come before keyword params")
        if _items(param):
            raise PGSNError(
                f"Positional param '{name}' must not have a default value")
        positional.append(param)
    return positional, keyword


def _callee(elem: ET.Element, unit: _Unit, attr: str,
            noun: str) -> tuple[Term, list[ET.Element | str]]:
    """What an application applies, and the items left over to be arguments.

    The callee is named by an attribute of the element's own -- `<apply
    template="f">`, `<send to="obj">` -- or else it is the first item of the
    content. Those attributes fill one slot rather than standing for the whole
    content, so they are element-specific and survive desugaring; see the note
    at the head of the file.
    """
    items = _items(elem)
    named = elem.get(attr)
    if named is not None:
        return _resolve(named), items
    if items:
        return _item(items[0], unit), items[1:]
    raise PGSNError(f"<{elem.tag}> needs {noun}")


def _applied(func: Term, items: list[ET.Element | str], unit: _Unit,
             owner: str) -> Term:
    """`func` applied to the `<arg>` items, of which there may be none.

    An empty argument list is not an error. Application is binary, so applying
    a function to nothing is the function: `<apply template="f"/>` is `f`.
    """
    positional, keyword, record_passed = _split_args(items, unit, owner)
    applied = func(*positional) if positional else func
    return applied(record(keyword)) if record_passed else applied


def _e_apply(elem: ET.Element, unit: _Unit) -> Term:
    """An application. The function is `template=`, or else the first child."""
    func, items = _callee(elem, unit, "template", "a function")
    return _applied(func, items, unit, "apply")


def _e_class(elem: ET.Element, unit: _Unit) -> Term:
    """A class definition.

    `name` is what the class is called, not what it is bound to: a binding is
    a name in a scope, while this name travels with the value and is what an
    instance of the class is reported as. It is a label rather than an
    identifier, so it is not subject to the reserved-name check, and it is not
    inherited -- a subclass that wants a name of its own says so.
    """
    inh = elem.find("inherit")
    kwargs: dict = {
        "inherit": _content(inh, unit) if inh is not None else base_class
    }
    class_name = elem.get("name")
    if class_name is not None:
        kwargs["name"] = string(class_name)
    attributes = [c for c in elem if c.tag == "attribute"]
    defaults = {c.get("name"): _content(c, unit)
                for c in attributes if _items(c)}
    # Methods must be stored as λself.body so that PGSNObject._apply_arg can
    # call (method)(self) to bind the receiver. This mirrors the DSL pattern:
    #   define_class(methods={'m': lambda_abs(self_var, body)})
    self_var = variable("self")
    methods = {c.get("name"): lambda_abs(self_var, _e_template(c, unit))
               for c in elem if c.tag == "method"}
    if attributes:
        kwargs["attributes"] = list_term(
            tuple(string(c.get("name")) for c in attributes))
    if defaults:
        kwargs["defaults"] = record(defaults)
    if methods:
        kwargs["methods"] = record(methods)
    return define_class(**kwargs)


def _e_object(elem: ET.Element, unit: _Unit) -> Term:
    inst = elem.find("instanceOf")
    if inst is None:
        raise PGSNError("<object> requires <instanceOf>")
    return instantiate(
        _content(inst, unit),
        record({c.get("name"): _content(c, unit)
                for c in elem if c.tag == "attribute"})
    )


def _e_get(elem: ET.Element, unit: _Unit) -> Term:
    """Read a label off a record. The receiver is `of=`, or else the content.

    A record label is not a name in the sense the reserved-name check means:
    it is a string the record was built with, so it is spelled `key` -- as on
    the `<dt>` that builds the entry this reads back -- and left out of the
    check.
    """
    key = elem.get("key")
    if key is None:
        raise PGSNError(
            "<get> needs a 'key' naming the field to read, as in "
            '<get key="description" of="node"/>')
    receiver = elem.get("of")
    if receiver is None:
        return _content(elem, unit)(string(key))
    if len(elem) or (elem.text and elem.text.strip()):
        raise PGSNError(
            "<get> has both an 'of' attribute and a receiver of its own; "
            "the attribute is shorthand for the receiver.")
    return _resolve(receiver)(string(key))


def _e_send(elem: ET.Element, unit: _Unit) -> Term:
    """Call a method. The receiver is `to=`, or else the first child.

    receiver("methodName") triggers PGSNObject._apply_arg, which applies self
    (the receiver) to the method value before returning it. A method called
    without arguments is that value.
    """
    method = elem.get("method")
    if method is None:
        raise PGSNError(
            "<send> needs a 'method' naming the method to call, as in "
            '<send method="greet" to="obj"/>')
    receiver, items = _callee(elem, unit, "to", "a receiver")
    return _applied(receiver(string(method)), items, unit, "send")


def _e_div(elem: ET.Element, unit: _Unit) -> Term:
    return _block(_items(elem), unit, "div")


def _e_list(elem: ET.Element, unit: _Unit) -> Term:
    return list_term(tuple(_content(li, unit) for li in elem.findall("li")))


def _e_dict(elem: ET.Element, unit: _Unit) -> Term:
    children = list(elem)
    attrs = {}
    for i in range(0, len(children) - 1, 2):
        dt, dd = children[i], children[i + 1]
        key = dt.get("key") or (dt.text or "").strip()
        if not key:
            raise PGSNError("<dt> key must be a string literal")
        attrs[key] = _content(dd, unit)
    return record(attrs)


# ------------------------------------------------------------------ #
# GSN node compilers
# ------------------------------------------------------------------ #

# Tags that stand for a value, as opposed to the tags that give a GSN node its
# structure. A lone value child of a GSN header is its description.
_VALUE_TAGS = {"var", "num", "str", "builtin", "apply", "get", "send",
               "div", "ol", "dl", "template", "class", "object"}


class _Header(NamedTuple):
    """The parts every GSN node is written with: what the node says, and the
    annotations and challenges hung off it.

    Each field is already a PGSN list, which is what the constructors in
    `gsn.py` take. A node with no place for one of them -- a <Solution>
    carries no <Context> -- simply leaves that field unread.
    """

    description: Term
    contexts: Term
    assumptions: Term
    defeaters: Term


def _header_description(elem: ET.Element, unit: _Unit) -> Term:
    """The description of a GSN header element.

    Written as a `<description>` element, as the element's leading text, or —
    when neither is present — as a single value child, so that a computed
    description can be given directly:

        <Solution><expr>f"test report {i}"</expr></Solution>
    """
    desc_elem = elem.find("description")
    if desc_elem is not None:
        return _content(desc_elem, unit)
    text = (elem.text or "").strip()
    if text:
        return _text_to_term(text, unit)
    values = [c for c in elem if c.tag in _VALUE_TAGS]
    if len(values) == 1:
        return _expr(values[0], unit)
    if len(values) > 1:
        raise PGSNError(
            f"<{elem.tag}> has several value children; "
            "put the description in a <description> element")
    return _text_to_term("")


def _gsn_header(elem: ET.Element, unit: _Unit) -> _Header:
    """Read the parts of a GSN node that every GSN node has."""
    return _Header(
        description=_header_description(elem, unit),
        contexts=list_term(tuple(_e_annotation(c, unit, context)
                                 for c in elem if c.tag == "Context")),
        assumptions=list_term(tuple(_e_annotation(c, unit, assumption)
                                    for c in elem if c.tag == "Assumption")),
        defeaters=list_term(tuple(_e_defeater(c, unit)
                                  for c in elem if c.tag == "Defeater")))


def _support_of(elem: ET.Element, unit: _Unit) -> Term:
    """What supports a node: its first support-bearing child, or nothing.

    A node with nothing under it is undeveloped, which is also what
    `<undeveloped/>` says in so many words. Sub-goals written directly under a
    node are gathered into one immediate strategy, that being the shorthand
    for an inference which needs no name of its own.
    """
    body = [c for c in elem if c.tag in _SUPPORT_TAGS]
    if not body:
        return undeveloped
    first = body[0]
    match first.tag:
        case "Strategy" | "Solution":
            return _expr(first, unit)
        case "Goal":
            return immediate(list_term(tuple(
                _e_goal(c, unit) for c in body if c.tag == "Goal")))
        case "supportedBy":
            return _content(first, unit)
        case _:  # <undeveloped/>
            return undeveloped


def _e_defeater(elem: ET.Element, unit: _Unit) -> Term:
    """A defeater challenging the node that holds it.

    It is written like any other GSN node — a description, and optionally a
    support of its own and further defeaters challenging it in turn:

        <Defeater>hazard H4 is unmitigated
          <Solution>incident report 2026-03</Solution>
        </Defeater>
    """
    header = _gsn_header(elem, unit)
    return defeater(description=header.description,
                    support=_support_of(elem, unit),
                    defeaters=header.defeaters)


def _e_annotation(elem: ET.Element, unit: _Unit, ctor: Term) -> Term:
    """An annotation built by `ctor`, which is `context` or `assumption`.

    Both are documentation nodes: each carries a statement and nothing else.
    The statement can be written as plain text, as a <description> child, or
    as an expression -- which is what `var=` and `expr=` expand to -- and all
    three land in `description`.
    """
    desc_elem = elem.find("description")
    other = [c for c in elem if c.tag != "description"]
    if desc_elem is not None:
        if other:
            raise PGSNError(
                f"<{elem.tag}> carries both a <description> and <{other[0].tag}>; "
                f"it holds a single statement, so give it only one")
        desc = _content(desc_elem, unit)
    elif other:
        if elem.text and elem.text.strip():
            raise PGSNError(
                f"<{elem.tag}> carries both text and <{other[0].tag}>; "
                f"it holds a single statement, so give it only one")
        if len(other) > 1:
            raise PGSNError(
                f"<{elem.tag}> holds a single statement, but was given "
                f"{len(other)} children")
        desc = _expr(other[0], unit)
    else:
        desc = _text_to_term((elem.text or "").strip(), unit)
    return ctor(description=desc)


def _e_goal(elem: ET.Element, unit: _Unit) -> Term:
    """A goal: the claim, whatever supports it, and whatever is attached."""
    header = _gsn_header(elem, unit)
    return goal(description=header.description,
                contexts=header.contexts,
                assumptions=header.assumptions,
                defeaters=header.defeaters,
                support=_support_of(elem, unit))


def _e_strategy(elem: ET.Element, unit: _Unit) -> Term:
    """A strategy: the inference, and the sub-goals it breaks a claim into."""
    header = _gsn_header(elem, unit)
    return strategy(description=header.description,
                    sub_goals=_sub_goals(elem, unit),
                    contexts=header.contexts,
                    assumptions=header.assumptions,
                    defeaters=header.defeaters)


def _sub_goals(elem: ET.Element, unit: _Unit) -> Term:
    """The sub-goals of a strategy, written out or computed.

    Writing them out as <Goal> children is the common case; <subGoals> holds a
    value instead, which is how a strategy over a generated list is expressed.
    An <undeveloped/> stands among the sub-goals for the part of the strategy
    not developed yet, which is how a strategy is left undeveloped: GSN v3
    lets the undeveloped decorator apply to strategies as well as goals.
    """
    written = [c for c in elem if c.tag in ("Goal", "undeveloped")]
    if written:
        return list_term(tuple(_e_goal(c, unit) if c.tag == "Goal"
                               else undeveloped for c in written))
    computed = elem.find("subGoals")
    if computed is not None:
        # <subGoals> requires a list, so its empty content is the empty
        # list rather than the empty string.
        return _content(computed, unit) if _items(computed) else empty
    raise PGSNError("<Strategy> requires sub-goals or <subGoals>")


def _e_solution(elem: ET.Element, unit: _Unit) -> Term:
    """Solution: a reference to an evidence item, and whatever challenges it."""
    header = _gsn_header(elem, unit)
    return solution(description=header.description,
                    defeaters=header.defeaters)


# ------------------------------------------------------------------ #
# The elements that stand for a value
# ------------------------------------------------------------------ #

_COMPILERS = {
    "var":      _e_var,
    "from":     _e_from,
    "num":      _e_num,
    "str":      _e_str,
    "template": _e_template,
    "apply":    _e_apply,
    "class":    _e_class,
    "object":   _e_object,
    "get":      _e_get,
    "send":     _e_send,
    "div":      _e_div,
    "ol":       _e_list,
    "dl":       _e_dict,
    "Goal":     _e_goal,
    "Strategy": _e_strategy,
    "Solution": _e_solution,
    "Defeater": _e_defeater,
}


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #

def load_xml(path: str | Path, *, config: Config | None = None,
             steps: int | None = None) -> Term:
    """Compile and fully evaluate a PGSN XML document file.

    Imports inside the document may name files below the jails registered in
    `config`, written as ``/<jail>/sub/file.xml``, and files below the
    document's own confinement root.  Nothing else is reachable.

    `steps` bounds the evaluation as it does in `Term.fully_eval`, and
    omitting it leaves that method's own budget in place.  A document large
    enough to exhaust it is not thereby wrong, so the budget belongs to the
    caller: the `pgsn` command sets its own, and this is where a program
    says the same thing.
    """
    compiled = compile_pgsn(path, config=config)
    if steps is None:
        return compiled.fully_eval()
    return compiled.fully_eval(steps=steps)


def load_xml_string(xml: str, *, config: Config | None = None,
                    jail: str | None = None,
                    steps: int | None = None) -> Term:
    """Compile and fully evaluate a PGSN XML document held in a string.

    Jailed imports always work.  Pass `jail` to say which jail the document
    should be considered to live in; relative imports then resolve from that
    jail's root.  Without it, relative imports are rejected.

    `steps` is as in `load_xml`.
    """
    compiled = compile_pgsn_string(xml, config=config, jail=jail)
    if steps is None:
        return compiled.fully_eval()
    return compiled.fully_eval(steps=steps)
