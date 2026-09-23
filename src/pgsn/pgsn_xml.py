"""PGSN XML compiler: purely syntactic mapping from XML to pgsn.dsl Terms.

XML parsing builds a single Term; all evaluation is deferred to fully_eval().
Semantic errors surface as non-terminating reduction.
"""

import ast
import xml.etree.ElementTree as ET
from pathlib import Path
from string import Formatter
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
    has_label, list_labels, add_attribute, remove_attribute, overwrite_record,
    format_string,
    Term,
)
from pgsn.gsn import (
    goal, strategy, evidence, context, assumption, defeater,
    goal_class, strategy_class, evidence_class,
    context_class, assumption_class, gsn_class,
    support_class, undeveloped_class, defeater_class,
    undeveloped, immediate, evidence_as_goal,
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

    Whatever a compiler needs to know beyond the element in front of it
    belongs here, which is why the compilers below take one of these and
    nothing else.
    """

    __slots__ = ("root", "cwd", "config", "visiting")

    def __init__(self, root: Path | None, cwd: Path | None, config: Config,
                 visiting: frozenset[Path] = frozenset()):
        self.root = root
        self.cwd = cwd
        self.config = config
        self.visiting = visiting

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
                     visiting=self.visiting | {path}), path

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


def _name_error(name: str, where: str = "") -> PGSNError:
    if name.startswith(_RESERVED_PREFIX):
        reason = ("a name may not begin with an underscore; "
                  "those are reserved by the implementation")
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
        if value.startswith(_RESERVED_PREFIX) or not value.isidentifier():
            raise _name_error(value, f' in <{elem.tag} {attr}="{value}">')


# ------------------------------------------------------------------ #
# <expr>: infix notation for the terms that are already expressible
#
# The text of an <expr> is parsed with Python's own parser and the resulting
# syntax tree is *translated* into the XML the document could have written by
# hand. Nothing is evaluated, and no node type is translated unless it appears
# in the tables below, so the syntax cannot reach anything `<apply>` could not.
#
# Operators expand to the reserved alias of a builtin, so that `1 + 2` means
# addition whatever the surrounding document happens to bind.
# ------------------------------------------------------------------ #

_BIN_OPS = {
    ast.Add: "plus",
    ast.Sub: "minus",
    ast.Mult: "times",
    # `//` is integer division. `/` is left unassigned so that it can mean
    # true division if PGSN ever gains a floating point type.
    ast.FloorDiv: "div",
    ast.Mod: "mod",
}

_BOOL_OPS = {ast.And: "boolean_and", ast.Or: "boolean_or"}


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


def _expr_error(node: ast.AST) -> PGSNError:
    return PGSNError(
        f"{type(node).__name__} is not allowed in <expr>. The expression "
        "syntax covers arithmetic, comparison, boolean operators and "
        "f-strings; use <apply>, <get> or <ol>/<dl> for anything else.")


def _translate(node: ast.AST) -> ET.Element:
    """Translate one allowed AST node into the XML element it stands for."""
    match node:
        case ast.Expression():
            return _translate(node.body)

        case ast.Constant(value=bool() as b):
            # Checked before int: in Python, bool is a subclass of int.
            return _reserved("true" if b else "false")

        case ast.Constant(value=int() as i):
            elem = ET.Element("num")
            elem.text = str(i)
            return elem

        case ast.Constant(value=str() as s):
            elem = ET.Element("str")
            elem.text = s
            return elem

        case ast.Name():
            if node.id.startswith(_RESERVED_PREFIX):
                raise _name_error(node.id)
            elem = ET.Element("var")
            elem.set("name", node.id)
            return elem

        case ast.BinOp() if type(node.op) in _BIN_OPS:
            return _call_builtin(_BIN_OPS[type(node.op)],
                                 _translate(node.left), _translate(node.right))

        case ast.BinOp(op=ast.Div()):
            raise PGSNError(
                "'/' is not defined in <expr>. PGSN has integers only, so "
                "write '//' for integer division; '/' is reserved for true "
                "division should a floating point type be added.")

        case ast.UnaryOp(op=ast.USub()):
            zero = ET.Element("num")
            zero.text = "0"
            return _call_builtin("minus", zero, _translate(node.operand))

        case ast.UnaryOp(op=ast.Not()):
            return _call_builtin("boolean_not", _translate(node.operand))

        case ast.BoolOp() if type(node.op) in _BOOL_OPS:
            name = _BOOL_OPS[type(node.op)]
            result = _translate(node.values[0])
            for value in node.values[1:]:
                result = _call_builtin(name, result, _translate(value))
            return result

        case ast.Compare():
            if len(node.ops) != 1:
                raise PGSNError(
                    "chained comparison is not allowed in <expr>; "
                    "write it with 'and'")
            return _translate_compare(node.ops[0],
                                      _translate(node.left),
                                      _translate(node.comparators[0]))

        case ast.JoinedStr():
            return _translate_fstring(node)

        case _:
            raise _expr_error(node)


def _translate_compare(op: ast.cmpop, left: ET.Element,
                       right: ET.Element) -> ET.Element:
    """Derive every comparison from `equal` and `less_than`."""
    match op:
        case ast.Eq():
            return _call_builtin("equal", left, right)
        case ast.NotEq():
            return _call_builtin("boolean_not",
                                 _call_builtin("equal", left, right))
        case ast.Lt():
            return _call_builtin("less_than", left, right)
        case ast.Gt():
            return _call_builtin("less_than", right, left)
        case ast.LtE():
            # a <= b is not (b < a); using or would evaluate both sides.
            return _call_builtin("boolean_not",
                                 _call_builtin("less_than", right, left))
        case ast.GtE():
            return _call_builtin("boolean_not",
                                 _call_builtin("less_than", left, right))
        case _:
            raise _expr_error(op)


def _translate_fstring(node: ast.JoinedStr) -> ET.Element:
    """Expand an f-string into an application of `format_string`.

    Each interpolated expression is bound to a generated name in a record, and
    the template refers to that name, so `str.format` never sees an expression.
    Literal text is escaped, since the template is a format string.
    """
    template: list[str] = []
    fields: list[tuple[str, ET.Element]] = []

    for part in node.values:
        match part:
            case ast.Constant(value=str() as text):
                template.append(text.replace("{", "{{").replace("}", "}}"))
            case ast.FormattedValue():
                name = f"_e{len(fields)}"
                fields.append((name, _translate(part.value)))
                spec = ""
                if part.format_spec is not None:
                    spec = _constant_format_spec(part.format_spec)
                conversion = ""
                if part.conversion != -1:
                    conversion = "!" + chr(part.conversion)
                template.append("{" + name + conversion + spec + "}")
            case _:
                raise _expr_error(part)

    text_elem = ET.Element("str")
    text_elem.text = "".join(template)
    if not fields:
        return text_elem

    record_elem = ET.Element("dl")
    for name, value in fields:
        dt = ET.SubElement(record_elem, "dt")
        dt.text = name
        dd = ET.SubElement(record_elem, "dd")
        dd.append(value)
    return _call_builtin("format_string", text_elem, record_elem)


def _constant_format_spec(spec: ast.JoinedStr) -> str:
    """Accept `{x:>3}` but not a spec that is itself computed."""
    parts = []
    for piece in spec.values:
        if not isinstance(piece, ast.Constant) or not isinstance(piece.value, str):
            raise PGSNError(
                "a computed format specification is not allowed in <expr>")
        parts.append(piece.value)
    return ":" + "".join(parts)


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
    source = (elem.text or "").strip()
    if not source:
        raise PGSNError("<expr> is empty")
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise PGSNError(f"Cannot parse <expr>: {source!r}: {exc.msg}") from None

    _replace_with(elem, _translate(tree))


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


# Builtins substituted inline during compilation (not at evaluation time).
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
    "has_label": has_label, "list_labels": list_labels,
    "add_attribute": add_attribute, "remove_attribute": remove_attribute,
    "overwrite_record": overwrite_record, "format_string": format_string,
    "empty_record": empty_record, "undefined": undefined,
    "define_class": define_class, "instantiate": instantiate,
    "type_of": type_of, "is_subtype": is_subtype, "base_class": base_class,
    "goal": goal, "strategy": strategy, "evidence": evidence,
    "context": context, "assumption": assumption,
    "defeater": defeater,
    "immediate": immediate, "undeveloped": undeveloped,
    "evidence_as_goal": evidence_as_goal,
    "gsn_class": gsn_class, "goal_class": goal_class,
    "strategy_class": strategy_class, "evidence_class": evidence_class,
    "context_class": context_class, "assumption_class": assumption_class,
    "support_class": support_class, "undeveloped_class": undeveloped_class,
    "defeater_class": defeater_class,
    # Intuitive aliases for GSN class values
    "Goal": goal_class, "Strategy": strategy_class, "Evidence": evidence_class,
    "Context": context_class, "Assumption": assumption_class,
    "GSN": gsn_class, "Support": support_class,
    "Defeater": defeater_class,
}

_SUPPORT_TAGS = {"Strategy", "Evidence", "Goal", "supportedBy", "undeveloped"}


def _text_fields(s: str) -> list[str]:
    """Return the {name} field names in s, honouring Python's {{ }} escaping."""
    return [fname for _, fname, _, _ in Formatter().parse(s)
            if fname is not None and fname != ""]


def _text_to_term(s: str) -> Term:
    """
    Turn user text into a Term. If it contains {name} fields, build a
    format_string application binding each field to the variable of that name.
    If it contains {{ }} escapes but no fields, still run format_string so
    the escapes are resolved ({{ -> {, }} -> }).
    Plain text with no braces at all becomes a String directly.
    Escaping follows Python's str.format ({{ -> {).
    """
    fields = _text_fields(s)
    if fields:
        args = record({name: variable(name) for name in fields})
        return format_string(string(s))(args)
    if "{{" in s or "}}" in s:
        # No variable fields but escape sequences present — run format_string
        # with an empty record so {{ }} are resolved to literal braces.
        return format_string(string(s))(empty_record)
    return string(s)


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
    cannot be observed — but ruinous: the builtin terms are large, every
    binding substitutes its value through the body, and a chain deep enough to
    hold them all exhausts the interpreter's stack, since every traversal of a
    term recurses. A document mentions a handful.

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
                owner: str) -> tuple[list, dict]:
    """
    Collect <arg> children into positional and keyword groups.
    Positional args (no name) must precede keyword args, as in Python.
    Application itself is delegated to Term.__call__.

    Anything that is not an <arg> is an error rather than something to skip.
    Desugaring expands `var` and `expr` into a child of their own, so skipping
    would turn `<apply template="f" var="x"/>` into an application of `f` to
    nothing at all.
    """
    positional, keyword = [], {}
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
        if name is None:
            if keyword:
                raise PGSNError("positional arg after keyword arg")
            positional.append(_content(a, unit))
        else:
            keyword[name] = _content(a, unit)
    return positional, keyword


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
    return _builtin_scope(_block(_items(root), unit, "PGSN"))


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
    literal. The application itself is an ordinary Term and is not evaluated.
    """
    file_path = elem.get("file", "")
    inner, full = unit.enter(file_path)

    root = ET.parse(full).getroot()
    if root.tag != "PGSNModule":
        raise PGSNError(f"Expected <PGSNModule> in {file_path!r}")
    _check_source(root)
    _desugar(root)

    module_term = _compile_module(root, inner)

    # Args compiled in the caller's scope — they are Terms, not values yet
    args = {a.get("name"): _content(a, unit) for a in elem.findall("arg")}
    return module_term(record(args))


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
        return _text_to_term(item)
    return _expr(item, unit)


def _content(parent: ET.Element, unit: _Unit) -> Term:
    """The single value an element's content stands for."""
    items = _items(parent)
    if len(items) == 1:
        return _item(items[0], unit)
    if items:
        raise PGSNError(f"Multiple values in <{parent.tag}>")
    raise PGSNError(f"No value in <{parent.tag}>")


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
    is simply the last item -- a child element or a run of text.
    """
    if not items:
        raise PGSNError(f"<{owner}> has no value")
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
    return _resolve(elem.get("name"), elem.get("typeOf"))


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
    positional, keyword = _split_args(items, unit, owner)
    if not positional and not keyword:
        return func
    # Delegate to Term.__call__: it casts args and builds the keyword Record
    return func(*positional, **keyword)


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
    `gsn.py` take. A node with no place for one of them -- an <Evidence>
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

        <Evidence><expr>f"test report {i}"</expr></Evidence>
    """
    desc_elem = elem.find("description")
    if desc_elem is not None:
        return _content(desc_elem, unit)
    text = (elem.text or "").strip()
    if text:
        return _text_to_term(text)
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
        case "Strategy" | "Evidence":
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
          <Evidence>incident report 2026-03</Evidence>
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
        desc = _text_to_term((elem.text or "").strip())
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
    """
    written = [c for c in elem if c.tag == "Goal"]
    if written:
        return list_term(tuple(_e_goal(c, unit) for c in written))
    computed = elem.find("subGoals")
    if computed is not None:
        return _content(computed, unit)
    raise PGSNError("<Strategy> requires sub-goals or <subGoals>")


def _e_evidence(elem: ET.Element, unit: _Unit) -> Term:
    """Evidence: a solution, and whatever challenges it."""
    header = _gsn_header(elem, unit)
    return evidence(description=header.description,
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
    "Evidence": _e_evidence,
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
