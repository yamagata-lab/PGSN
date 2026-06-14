"""PGSN XML compiler: purely syntactic mapping from XML to pgsn.dsl Terms.

XML parsing builds a single Term; all evaluation is deferred to fully_eval().
No shorthand expansion (var-attribute, def-as) in this implementation.
Semantic errors surface as non-terminating reduction.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from pgsn.dsl import (
    variable, string, list_term, record, empty_record, let,
    lambda_abs, lambda_abs_keywords, lambda_abs_vars,
    fix, repeat, map_term, fold, foldr, concat, cons, head, tail, index,
    true, false, if_then_else, guard,
    equal, plus, minus, times, div, mod,
    less_than, less_eq, greater_than, greater_eq,
    define_class, instantiate, is_instance, is_subclass,
    base_class, undefined, empty,
    boolean_and, boolean_or, boolean_not, boolean_xor, implies,
    has_label, list_labels, add_attribute, remove_attribute, overwrite_record,
    format_string, integer, list_all, integer_sum, instance,
    Term,
)
from pgsn.gsn import (
    goal, strategy, evidence, context, assumption,
    goal_class, strategy_class, evidence_class,
    context_class, assumption_class, gsn_class,
    support_class, undeveloped_class,
    undeveloped, immediate, evidence_as_goal,
)


class PGSNError(Exception):
    pass


# ------------------------------------------------------------------ #
# Shorthand preprocessor
#
# Expands shorthands in place on the ElementTree, before compilation,
# so the compiler proper never sees them:
#   1. def-as:          <def as="T">..</def>         ->  <def><T>..</T></def>
#   2. var-attribute:   <tag var="x"/>               ->  <tag><var name="x"/></tag>
#   3. GSN text:        <Goal>txt<Strategy/>          ->  <Goal><description>txt</description><Strategy/>
#   4. apply template:  <apply template="f">...</apply>
#                                                    ->  <apply><var name="f"/>...</apply>
#   5. get label/of:    <get label="x" of="obj"/>    ->  <get name="x"><var name="obj"/></get>
#   6. send method/to:  <send method="m" to="obj">   ->  <send name="m"><var name="obj"/>...
#                       (label/method are user-facing; name= is internal)
#   7. if/cond/else:    <if cond="...">...</if>      ->  if_then_else application
#                       (see _take_cond_arg below)
#   8. cases/case/else: <cases><case cond="...">..   ->  nested if_then_else chain
#                       (see _build_cases_chain below)
# ------------------------------------------------------------------ #

_GSN_HEADER_TAGS = {"Goal", "Strategy", "Evidence", "Context", "Assumption"}


def _take_cond_arg(elem: ET.Element) -> ET.Element:
    """Extract the condition of an <if> or <case> element as an <arg>.

    The condition is either:
      - a `cond` attribute, parsed by the mini-expression language (same as
        <expr>), or
      - a <cond> child element holding any expression (val_pat) — useful
        for var= shorthand or expressions too complex for an attribute.

    The source attribute/element is consumed (removed) from `elem`. If a
    <cond> child is removed, its `.tail` text (text following </cond> in
    the source) is preserved by merging it into `elem`'s remaining content
    — this matters for <case>, where that text is part of the case's body.
    """
    if "cond" in elem.attrib:
        cond_text = elem.attrib.pop("cond")
        expr_elem = ET.Element("expr")
        expr_elem.text = cond_text
        arg = ET.Element("arg")
        arg.append(expr_elem)
        return arg
    cond_elem = elem.find("cond")
    if cond_elem is None:
        raise PGSNError(
            f"<{elem.tag}> requires a 'cond' attribute or <cond> child element")
    siblings = list(elem)
    idx = siblings.index(cond_elem)
    elem.remove(cond_elem)
    if cond_elem.tail:
        if idx == 0:
            elem.text = (elem.text or "") + cond_elem.tail
        else:
            prev = siblings[idx - 1]
            prev.tail = (prev.tail or "") + cond_elem.tail
        cond_elem.tail = None
    cond_elem.tag = "arg"
    return cond_elem


def _build_cases_chain(case_elems: list[ET.Element],
                       base_else_arg: ET.Element) -> ET.Element:
    """Build the nested if_then_else chain for a <cases> element's <case>s.

    Each <case> supplies its condition (cond= attribute or <cond> child) and
    its body is the *remaining content* of the <case> element itself — there
    is no <then> wrapper, unlike <if>.

    Returns an <arg> element holding the else-branch content for the level
    above: either `base_else_arg` itself (if no <case>s remain) or an
    <apply> wrapping the first <case> with the rest of the chain as its
    else-branch.
    """
    if not case_elems:
        return base_else_arg

    first, *rest = case_elems
    cond_arg = _take_cond_arg(first)

    # The remaining content of <case> (after removing <cond> if present) is
    # the case's value — rename <case> -> <arg> directly, no <then> wrapper.
    first.tag = "arg"
    then_arg = first

    inner_else_arg = _build_cases_chain(rest, base_else_arg)

    func_var = ET.Element("var")
    func_var.set("name", "if_then_else")

    apply_elem = ET.Element("apply")
    apply_elem.append(func_var)
    apply_elem.append(cond_arg)
    apply_elem.append(then_arg)
    apply_elem.append(inner_else_arg)

    result_arg = ET.Element("arg")
    result_arg.append(apply_elem)
    return result_arg


def _preprocess(elem: ET.Element) -> None:
    """Recursively expand shorthand notations in place."""
    # def-as: wrap the def body in an element named by the `as` attribute
    if elem.tag == "def" and "as" in elem.attrib:
        tag = elem.attrib.pop("as")
        wrapper = ET.Element(tag)
        # Move def's text and children into the wrapper
        wrapper.text = elem.text
        elem.text = None
        for child in list(elem):
            elem.remove(child)
            wrapper.append(child)
        elem.append(wrapper)

    # if/cond/else: <if cond="...">...</if> expands to if_then_else.
    #
    #   <if cond="n == 0">              <if><cond var="x"/>
    #       <then>a</then>                  <then>a</then>
    #       <else>b</else>                  <else>b</else>
    #   </if>                            </if>
    #
    # The condition is either a `cond` attribute (parsed by the same
    # mini-expression language as <expr>) or a <cond> child element holding
    # any expression (val_pat) — useful when var= shorthand or a complex
    # expression doesn't fit in an attribute string.
    #
    # <then> is required; <else> may be omitted (defaults to
    # <var name="undefined"/>). For a cascade of conditions, use <cases>
    # instead (below).
    if elem.tag == "if":
        then_elem = elem.find("then")
        if then_elem is None:
            raise PGSNError("<if> requires a <then> element")

        cond_arg = _take_cond_arg(elem)

        elem.remove(then_elem)
        then_elem.tag = "arg"

        else_elem = elem.find("else")
        if else_elem is not None:
            elem.remove(else_elem)
            else_elem.tag = "arg"
            else_arg = else_elem
        else:
            else_arg = ET.Element("arg")
            undef_var = ET.Element("var")
            undef_var.set("name", "undefined")
            else_arg.append(undef_var)

        func_var = ET.Element("var")
        func_var.set("name", "if_then_else")

        # Rebuild <if> as <apply>
        elem.tag = "apply"
        elem.text = None
        for c in list(elem):
            elem.remove(c)
        elem.append(func_var)
        elem.append(cond_arg)
        elem.append(then_elem)
        elem.append(else_arg)

    # cases: a flat cascade of conditions, like Python's match / Lisp's cond.
    #
    #   <cases>
    #       <case cond="n == 0">zero</case>
    #       <case><cond var="flag"/>complex condition case</case>
    #       <else>many</else>
    #   </cases>
    #
    # Each <case> supplies its condition (cond= attribute or <cond> child,
    # same as <if>) and its body is the case element's own remaining
    # content — there is no <then> wrapper. <case>s are checked in order;
    # <else> (or <var name="undefined"/> if omitted) is used if none match.
    # Internally this expands to the same nested if_then_else chain as a
    # cascade of <if>/<else><if>, but the XML surface is a flat list of
    # siblings.
    if elem.tag == "cases":
        case_elems = elem.findall("case")
        if not case_elems:
            raise PGSNError("<cases> requires at least one <case> element")
        for c in case_elems:
            elem.remove(c)

        else_elem = elem.find("else")
        if else_elem is not None:
            elem.remove(else_elem)
            else_elem.tag = "arg"
            base_else_arg = else_elem
        else:
            base_else_arg = ET.Element("arg")
            undef_var = ET.Element("var")
            undef_var.set("name", "undefined")
            base_else_arg.append(undef_var)

        result_arg = _build_cases_chain(case_elems, base_else_arg)
        apply_elem = result_arg.find("apply")

        # Rebuild <cases> as <apply>
        elem.tag = "apply"
        elem.text = None
        for c in list(elem):
            elem.remove(c)
        for c in list(apply_elem):
            elem.append(c)

    # apply template="f": insert <var name="f"/> as the first child
    if elem.tag == "apply" and "template" in elem.attrib:
        name = elem.attrib.pop("template")
        var_elem = ET.Element("var")
        var_elem.set("name", name)
        elem.insert(0, var_elem)

    # get label="x" of="obj": rename label->name, insert <var name="obj"/> as child
    if elem.tag == "get" and "label" in elem.attrib:
        label = elem.attrib.pop("label")
        elem.set("name", label)
        if "of" in elem.attrib:
            receiver = elem.attrib.pop("of")
            var_elem = ET.Element("var")
            var_elem.set("name", receiver)
            elem.insert(0, var_elem)

    # send method="m" to="obj": rename method->name, insert <var name="obj"/> first
    if elem.tag == "send" and "method" in elem.attrib:
        method = elem.attrib.pop("method")
        elem.set("name", method)
        if "to" in elem.attrib:
            receiver = elem.attrib.pop("to")
            var_elem = ET.Element("var")
            var_elem.set("name", receiver)
            elem.insert(0, var_elem)

    # var-attribute: <tag var="x"/> -> <tag><var name="x"/></tag>
    # (skip apply and send which handle var-like attrs above)
    if "var" in elem.attrib:
        if len(elem) > 0:
            raise PGSNError(
                f"<{elem.tag}> has both a 'var' attribute and child elements")
        name = elem.attrib.pop("var")
        var_elem = ET.SubElement(elem, "var")
        var_elem.set("name", name)

    # GSN leading text -> <description>: only for GSN header elements that
    # have other children (so the text is the header's description, not the
    # element's whole value). A text-only GSN element keeps its text as-is.
    if (elem.tag in _GSN_HEADER_TAGS and elem.find("description") is None
            and elem.text and elem.text.strip() and len(elem) > 0):
        desc = ET.Element("description")
        desc.text = elem.text.strip()
        elem.text = None
        elem.insert(0, desc)

    # Recurse into children (after potential restructuring above)
    for child in elem:
        _preprocess(child)


# Builtins substituted inline during compilation (not at evaluation time)
_BUILTINS: dict[str, Term] = {
    "fix": fix, "repeat": repeat,
    "map_term": map_term, "fold": fold, "foldr": foldr, "concat": concat,
    "cons": cons, "head": head, "tail": tail, "index": index,
    "list_all": list_all, "integer_sum": integer_sum, "instance": instance,
    "equal": equal, "guard": guard, "if_then_else": if_then_else,
    "plus": plus, "minus": minus, "times": times, "div": div, "mod": mod,
    "less_than": less_than, "less_eq": less_eq,
    "greater_than": greater_than, "greater_eq": greater_eq,
    "boolean_and": boolean_and, "boolean_or": boolean_or,
    "boolean_not": boolean_not, "boolean_xor": boolean_xor,
    "implies": implies, "true": true, "false": false,
    "has_label": has_label, "list_labels": list_labels,
    "add_attribute": add_attribute, "remove_attribute": remove_attribute,
    "overwrite_record": overwrite_record, "format_string": format_string,
    "undefined": undefined,
    "define_class": define_class, "instantiate": instantiate,
    "is_instance": is_instance, "is_subclass": is_subclass,
    "base_class": base_class,
    "goal": goal, "strategy": strategy, "evidence": evidence,
    "context": context, "assumption": assumption,
    "immediate": immediate, "undeveloped": undeveloped,
    "evidence_as_goal": evidence_as_goal,
    "gsn_class": gsn_class, "goal_class": goal_class,
    "strategy_class": strategy_class, "evidence_class": evidence_class,
    "context_class": context_class, "assumption_class": assumption_class,
    "support_class": support_class, "undeveloped_class": undeveloped_class,
    # Intuitive aliases for GSN class values
    "Goal": goal_class, "Strategy": strategy_class, "Evidence": evidence_class,
    "Context": context_class, "Assumption": assumption_class,
    "GSN": gsn_class, "Support": support_class,
}

_SUPPORT_TAGS = {"Strategy", "Evidence", "Goal", "supportedBy", "undeveloped"}


import ast as _ast
import string as _stringmod


def _ast_to_term(node: _ast.expr) -> Term:
    """Convert a Python AST expression node to a PGSN Term.

    Supports: variable names, integer/string literals, arithmetic (+,-,*,/,%),
    equality (==, !=), and parenthesised sub-expressions.
    Raises PGSNError for unsupported constructs.
    """
    match node:
        case _ast.Name(id=name):
            return _resolve(name)
        case _ast.Constant(value=v) if isinstance(v, int):
            return integer(v)
        case _ast.Constant(value=v) if isinstance(v, str):
            return string(v)
        case _ast.BinOp(left=l, op=_ast.Add(), right=r):
            return plus(_ast_to_term(l), _ast_to_term(r))
        case _ast.BinOp(left=l, op=_ast.Sub(), right=r):
            return minus(_ast_to_term(l), _ast_to_term(r))
        case _ast.BinOp(left=l, op=_ast.Mult(), right=r):
            return times(_ast_to_term(l), _ast_to_term(r))
        case _ast.BinOp(left=l, op=_ast.Div(), right=r):
            return div(_ast_to_term(l), _ast_to_term(r))
        case _ast.BinOp(left=l, op=_ast.Mod(), right=r):
            return mod(_ast_to_term(l), _ast_to_term(r))
        case _ast.Compare(left=l, ops=[_ast.Eq()], comparators=[r]):
            return equal(_ast_to_term(l), _ast_to_term(r))
        case _ast.Compare(left=l, ops=[_ast.NotEq()], comparators=[r]):
            return boolean_not(equal(_ast_to_term(l), _ast_to_term(r)))
        case _ast.Compare(left=l, ops=[_ast.Lt()], comparators=[r]):
            return less_than(_ast_to_term(l), _ast_to_term(r))
        case _ast.Compare(left=l, ops=[_ast.LtE()], comparators=[r]):
            return less_eq(_ast_to_term(l), _ast_to_term(r))
        case _ast.Compare(left=l, ops=[_ast.Gt()], comparators=[r]):
            return greater_than(_ast_to_term(l), _ast_to_term(r))
        case _ast.Compare(left=l, ops=[_ast.GtE()], comparators=[r]):
            return greater_eq(_ast_to_term(l), _ast_to_term(r))
        case _ast.UnaryOp(op=_ast.USub(), operand=o):
            return minus(integer(0), _ast_to_term(o))
        case _ast.UnaryOp(op=_ast.Not(), operand=o):
            return boolean_not(_ast_to_term(o))
        case _ast.BoolOp(op=_ast.And(), values=values):
            terms = [_ast_to_term(v) for v in values]
            result = terms[0]
            for t in terms[1:]:
                result = boolean_and(result, t)
            return result
        case _ast.BoolOp(op=_ast.Or(), values=values):
            terms = [_ast_to_term(v) for v in values]
            result = terms[0]
            for t in terms[1:]:
                result = boolean_or(result, t)
            return result
        case _:
            raise PGSNError(
                f"Unsupported expression in {{...}}: {_ast.unparse(node)!r}")


def _parse_expr(s: str) -> Term:
    """Parse a mini-expression string into a PGSN Term."""
    try:
        tree = _ast.parse(s.strip(), mode='eval')
        return _ast_to_term(tree.body)
    except SyntaxError as e:
        raise PGSNError(f"Syntax error in expression {s!r}: {e}")


def _text_fields(s: str) -> list[str]:
    """Return the raw {field} strings from s, honouring {{ }} escaping.

    Each field may be a plain name or a mini-expression like 'x + 1'.
    """
    return [fname for _, fname, _, _ in _stringmod.Formatter().parse(s)
            if fname is not None and fname != ""]


def _field_to_term(field: str) -> tuple[str, Term]:
    """Convert one {field} string to (placeholder_name, Term).

    Simple identifiers become variable references; anything containing an
    operator is parsed as a mini-expression and bound to an auto-generated
    placeholder name so format_string can interpolate it.
    """
    field = field.strip()
    # Simple identifier — keep as-is for format_string placeholder
    if field.isidentifier():
        return field, _resolve(field)
    # Expression — parse and bind to a synthetic placeholder
    placeholder = f"_e{abs(hash(field)) % 100000}"
    return placeholder, _parse_expr(field)


def _text_to_term(s: str) -> Term:
    """
    Turn user text into a PGSN Term.

    Rules applied in order:
    1. Plain integer text (e.g. "42") → Integer(42).
    2. {name} or {expr} fields → format_string application.
       Each field may be a plain variable name or a mini-expression
       (arithmetic / equality) parsed by _ast_to_term. The result is always
       stringified and interpolated into the text (Jinja-style). If you need
       the raw, non-string value of an expression (e.g. a Boolean condition),
       use a standalone <expr>...</expr> element instead of {...}.
    3. {{ }} escape sequences with no fields → format_string with empty record.
    4. Plain text → String.
    """
    # Integer literal
    try:
        return integer(int(s.strip()))
    except ValueError:
        pass

    raw_fields = _text_fields(s)
    if raw_fields:
        # Map each raw field to (placeholder, term), rewriting the template
        # string when a field is a complex expression.
        bindings: dict[str, Term] = {}
        fmt = s
        for raw in raw_fields:
            placeholder, term = _field_to_term(raw)
            bindings[placeholder] = term
            if raw != placeholder:
                # Replace the expression with the synthetic placeholder name
                fmt = fmt.replace("{" + raw + "}", "{" + placeholder + "}")
        args = record(bindings)
        return format_string(string(fmt))(args)

    if "{{" in s or "}}" in s:
        # Escape sequences only — resolve {{ -> { etc.
        return format_string(string(s))(empty_record)

    return string(s)


def _resolve(name: str, instance_of: str | None = None) -> Term:
    """Builtins are substituted inline; other names become free variables."""
    term = _BUILTINS.get(name, variable(name))
    if instance_of:
        cls = _BUILTINS.get(instance_of, variable(instance_of))
        term = guard(is_instance(term, cls))(term)
    return term


def _thread_lets(bindings: list[tuple[str, Term]],
                 body: Term) -> Term:
    """Fold a binding list into nested let expressions around body."""
    for name, term in reversed(bindings):
        body = let(variable(name), term, body)
    return body


def _split_args(arg_elems: list[ET.Element], base_dir: Path | None,
                visiting: frozenset[Path]) -> tuple[list, dict]:
    """
    Collect <arg> children into positional and keyword groups.
    Positional args (no name) must precede keyword args, as in Python.
    Application itself is delegated to Term.__call__.
    """
    positional, keyword = [], {}
    for a in arg_elems:
        if a.tag != "arg":
            continue
        name = a.get("name")
        if name is None:
            if keyword:
                raise PGSNError("positional arg after keyword arg")
            positional.append(_content(a, base_dir, visiting))
        else:
            keyword[name] = _content(a, base_dir, visiting)
    return positional, keyword


# ------------------------------------------------------------------ #
# Document compilers
# ------------------------------------------------------------------ #

def compile_pgsn(path: str | Path) -> Term:
    """Compile a <PGSN> document file into a single Term (no evaluation)."""
    p = Path(path).resolve()
    return _compile_root(ET.parse(p).getroot(), p.parent, entry=p)


def compile_pgsn_string(xml: str, base_dir: str | Path | None = None) -> Term:
    """
    Compile a <PGSN> document from a string.
    Imports are disallowed unless base_dir is given to resolve relative paths.
    """
    bd = Path(base_dir).resolve() if base_dir is not None else None
    return _compile_root(ET.fromstring(xml), bd, entry=None)


def _compile_root(root: ET.Element, base_dir: Path | None,
                  entry: Path | None = None) -> Term:
    """Compile a parsed <PGSN> root element against a base directory.

    The entry file path (when known) seeds the visiting set so that an
    import cycle returning to the entry document is detected as such.
    """
    if root.tag != "PGSN":
        raise PGSNError(f"Expected <PGSN>, got <{root.tag}>")
    _preprocess(root)
    children = list(root)
    # The final value may be a bare text node (no child elements)
    if not children:
        text = (root.text or "").strip()
        if text:
            return _text_to_term(text)
        raise PGSNError("<PGSN> has no value")
    visiting = frozenset({entry}) if entry is not None else frozenset()
    final = _expr(children[-1], base_dir, visiting)
    bindings = _bindings(children[:-1], base_dir, visiting)
    return _thread_lets(bindings, final)


def _compile_module(root: ET.Element, base_dir: Path | None,
                    visiting: frozenset[Path]) -> Term:
    """
    Compile <PGSNModule> to a keyword-lambda Term.
    When applied to a Record of args, yields a Record of exported names.
    """
    children = list(root)
    idx, params, defaults_dict = 0, [], {}

    while idx < len(children) and children[idx].tag == "param":
        p = children[idx]
        name = p.get("name")
        params.append(name)
        if list(p) or (p.text and p.text.strip()):
            defaults_dict[name] = _content(p, base_dir, visiting)
        idx += 1

    body_children = children[idx:]
    export_names = [c.get("name") for c in body_children if c.tag == "def"]

    # Module body: let-chain ending in a record of all exported names
    exports = record({n: variable(n) for n in export_names})
    body = _thread_lets(_bindings(body_children, base_dir, visiting), exports)

    arguments = {p: variable(p) for p in params}
    defaults_rec = record(defaults_dict) if defaults_dict else empty_record
    return lambda_abs_keywords(arguments, body, defaults_rec)


# ------------------------------------------------------------------ #
# Binding sequences  (def / from)
# ------------------------------------------------------------------ #

def _bindings(elems: list[ET.Element], base_dir: Path | None,
              visiting: frozenset[Path]) -> list[tuple[str, Term]]:
    result = []
    for elem in elems:
        if elem.tag == "def":
            result.append(_compile_def(elem, base_dir, visiting))
        elif elem.tag == "from":
            result.extend(_compile_from(elem, base_dir, visiting))
        else:
            raise PGSNError(f"Unexpected element: <{elem.tag}>")
    return result


def _compile_def(elem: ET.Element, base_dir: Path | None,
                 visiting: frozenset[Path]) -> tuple[str, Term]:
    name = elem.get("name")
    term = _content(elem, base_dir, visiting)

    if elem.get("recursive", "false").lower() == "true":
        term = fix(lambda_abs(variable(name), term))

    instance_of = elem.get("instanceOf")
    if instance_of:
        cls = _BUILTINS.get(instance_of, variable(instance_of))
        term = guard(is_instance(term, cls))(term)

    return name, term


def _compile_from(elem: ET.Element, base_dir: Path | None,
                  visiting: frozenset[Path]) -> list[tuple[str, Term]]:
    """
    File I/O at compile time (path is a static literal).
    Module application and field access are lazy Terms.
    """
    file_path = elem.get("file", "")
    if base_dir is None:
        raise PGSNError("imports are not allowed without a base directory")
    if not file_path or Path(file_path).is_absolute() or ".." in Path(file_path).parts:
        raise PGSNError(f"Unsafe file path: {file_path!r}")

    full = (base_dir / file_path).resolve()
    if full in visiting:
        raise PGSNError(f"Circular import: {full}")

    root = ET.parse(full).getroot()
    if root.tag != "PGSNModule":
        raise PGSNError(f"Expected <PGSNModule> in {file_path!r}")
    _preprocess(root)

    module_term = _compile_module(root, full.parent, visiting | {full})

    # Args compiled in the caller's scope — they are Terms, not values yet
    args = {a.get("name"): _content(a, base_dir, visiting)
            for a in elem.findall("arg")}
    applied = module_term(record(args))

    single = elem.get("import")
    if single:
        return [(elem.get("as", single), applied(string(single)))]
    return [(imp.get("as", imp.get("name")), applied(string(imp.get("name"))))
            for imp in elem.findall("import")]


# ------------------------------------------------------------------ #
# Expression compilers
# ------------------------------------------------------------------ #

def _content(parent: ET.Element, base_dir: Path | None,
             visiting: frozenset[Path]) -> Term:
    """Single value from element content: one child expression or bare text."""
    val_children = [c for c in parent if c.tag != "param"]
    if len(val_children) == 1:
        return _expr(val_children[0], base_dir, visiting)
    if len(val_children) > 1:
        raise PGSNError(f"Multiple value children in <{parent.tag}>")
    text = (parent.text or "").strip()
    if text:
        return _text_to_term(text)
    raise PGSNError(f"No value in <{parent.tag}>")


def _expr(elem: ET.Element, base_dir: Path | None,
          visiting: frozenset[Path]) -> Term:
    dispatch = {
        "var":      _e_var,
        "expr":     _e_expr,
        "template": _e_template,
        "apply":    _e_apply,
        "class":    _e_class,
        "object":   _e_object,
        "get":      _e_get,
        "send":     _e_send,
        "div":      _e_div,
        "ul":       _e_list,
        "ol":       _e_list,
        "dl":       _e_dict,
        "Goal":     _e_goal,
        "Strategy": _e_strategy,
        "Evidence": _e_evidence,
        "undeveloped": _e_undeveloped,
    }
    fn = dispatch.get(elem.tag)
    if fn is None:
        raise PGSNError(f"Unknown expression: <{elem.tag}>")
    return fn(elem, base_dir, visiting)


def _e_expr(elem: ET.Element, _bd: Path, _v: frozenset) -> Term:
    """<expr>x + y * 2</expr> — compile a mini-expression to a Term."""
    text = (elem.text or "").strip()
    if not text:
        raise PGSNError("<expr> is empty")
    return _parse_expr(text)


def _e_var(elem: ET.Element, _bd: Path, _v: frozenset) -> Term:
    return _resolve(elem.get("name"), elem.get("instanceOf"))


def _e_template(elem: ET.Element, base_dir: Path | None,
                visiting: frozenset[Path]) -> Term:
    params = [(c.get("name"), c) for c in elem if c.tag == "param"]
    body_elems = [c for c in elem if c.tag != "param"]

    # Split body into leading defs and the final value expression,
    # mirroring the structure of <div> and <PGSN>.
    if body_elems and body_elems[-1].tag != "def":
        final_elem = body_elems[-1]
        leading = body_elems[:-1]
    elif elem.text and elem.text.strip():
        final_elem = None
        leading = []
    else:
        raise PGSNError("<template> has no body")

    # Validate: everything before the final value must be a <def>
    for c in leading:
        if c.tag != "def":
            raise PGSNError(
                f"<{c.tag}> must come after all <def>s in <template>")

    if final_elem is not None:
        final = _expr(final_elem, base_dir, visiting)
    else:
        final = _text_to_term(elem.text.strip())

    bindings = _bindings(leading, base_dir, visiting)
    body = _thread_lets(bindings, final)

    if not params:
        return body

    # Separate positional params (positional="true") from keyword params.
    # Positional must all come before keyword params (Python convention).
    positional_params = []
    keyword_params = []
    seen_keyword = False
    for name, pelem in params:
        is_pos = pelem.get("positional", "false").lower() == "true"
        if is_pos:
            if seen_keyword:
                raise PGSNError(
                    f"Positional param '{name}' must come before keyword params")
            # Positional params must not carry a default value
            pchildren = [c for c in pelem if c.tag != "param"]
            if pchildren or (pelem.text and pelem.text.strip()):
                raise PGSNError(
                    f"Positional param '{name}' must not have a default value")
            positional_params.append(name)
        else:
            seen_keyword = True
            keyword_params.append((name, pelem))

    # Build default values dict for keyword params
    defaults_dict = {}
    for name, pelem in keyword_params:
        pchildren = [c for c in pelem if c.tag != "param"]
        if pchildren:
            defaults_dict[name] = _expr(pchildren[0], base_dir, visiting)
        elif pelem.text and pelem.text.strip():
            defaults_dict[name] = _text_to_term(pelem.text.strip())

    # Build the term: keyword layer first (innermost), then positional layer
    # wrapping it. This matches Term.__call__ which strips positional args
    # before passing the keyword Record.
    if keyword_params:
        t = lambda_abs_keywords(
            {name: variable(name) for name in [n for n, _ in keyword_params]},
            body,
            record(defaults_dict) if defaults_dict else empty_record,
        )
    else:
        t = body

    if positional_params:
        t = lambda_abs_vars(
            tuple(variable(name) for name in positional_params),
            t,
        )

    return t


def _e_apply(elem: ET.Element, base_dir: Path | None,
             visiting: frozenset[Path]) -> Term:
    children = list(elem)
    if not children:
        raise PGSNError("<apply> needs a function")
    func = _expr(children[0], base_dir, visiting)
    positional, keyword = _split_args(children[1:], base_dir, visiting)
    if not positional and not keyword:
        raise PGSNError("<apply> needs at least one <arg>")
    # Delegate to Term.__call__: it casts args and builds the keyword Record
    return func(*positional, **keyword)


def _e_class(elem: ET.Element, base_dir: Path | None,
             visiting: frozenset[Path]) -> Term:
    inh = elem.find("inherit")
    kwargs: dict = {
        "inherit": _content(inh, base_dir, visiting) if inh is not None else base_class
    }
    attrs = [c.get("name") for c in elem if c.tag == "attribute"]
    defs = {c.get("name"): _content(c, base_dir, visiting)
            for c in elem if c.tag == "attribute"
            and (list(c) or (c.text and c.text.strip()))}
    # Methods must be stored as λself.body so that PGSNObject._apply_arg can
    # call (method)(self) to bind the receiver. This mirrors the DSL pattern:
    #   define_class(methods={'m': lambda_abs(self_var, body)})
    _self_var = variable("self")
    methods = {c.get("name"): lambda_abs(_self_var, _e_template(c, base_dir, visiting))
               for c in elem if c.tag == "method"}
    if attrs:
        kwargs["attributes"] = list_term(tuple(string(a) for a in attrs))
    if defs:
        kwargs["defaults"] = record(defs)
    if methods:
        kwargs["methods"] = record(methods)
    return define_class(**kwargs)


def _e_object(elem: ET.Element, base_dir: Path | None,
              visiting: frozenset[Path]) -> Term:
    inst = elem.find("instanceOf")
    if inst is None:
        raise PGSNError("<object> requires <instanceOf>")
    return instantiate(
        _content(inst, base_dir, visiting),
        record({c.get("name"): _content(c, base_dir, visiting)
                for c in elem if c.tag == "attribute"})
    )


def _e_get(elem: ET.Element, base_dir: Path | None,
           visiting: frozenset[Path]) -> Term:
    return _content(elem, base_dir, visiting)(string(elem.get("name")))


def _e_send(elem: ET.Element, base_dir: Path | None,
            visiting: frozenset[Path]) -> Term:
    children = list(elem)
    if not children:
        raise PGSNError("<send> needs a receiver")
    # receiver("methodName") triggers PGSNObject._apply_arg which automatically
    # applies self (the receiver) to the method value before returning it.
    method = _expr(children[0], base_dir, visiting)(string(elem.get("name")))
    positional, keyword = _split_args(children[1:], base_dir, visiting)
    if not positional and not keyword:
        return method
    return method(*positional, **keyword)


def _e_div(elem: ET.Element, base_dir: Path | None,
           visiting: frozenset[Path]) -> Term:
    children = list(elem)
    if not children:
        raise PGSNError("<div> has no value")
    # The final child is the div's value expression (use _expr, not _content)
    final = _expr(children[-1], base_dir, visiting)
    bs = _bindings([c for c in children[:-1] if c.tag == "def"], base_dir, visiting)
    return _thread_lets(bs, final)


def _e_list(elem: ET.Element, base_dir: Path | None,
            visiting: frozenset[Path]) -> Term:
    return list_term(tuple(
        _content(li, base_dir, visiting) for li in elem.findall("li")
    ))


def _e_dict(elem: ET.Element, base_dir: Path | None,
            visiting: frozenset[Path]) -> Term:
    children = list(elem)
    attrs = {}
    for i in range(0, len(children) - 1, 2):
        dt, dd = children[i], children[i + 1]
        key = dt.get("key") or (dt.text or "").strip()
        if not key:
            raise PGSNError("<dt> key must be a string literal")
        attrs[key] = _content(dd, base_dir, visiting)
    return record(attrs)


# ------------------------------------------------------------------ #
# GSN node compilers
# ------------------------------------------------------------------ #

def _gsn_header(elem: ET.Element, base_dir: Path | None,
                visiting: frozenset[Path]) -> tuple[Term, list, list]:
    desc_elem = elem.find("description")
    desc = (_content(desc_elem, base_dir, visiting) if desc_elem is not None
            else _text_to_term((elem.text or "").strip()))
    contexts = [_e_annotation(c, base_dir, visiting, context)
                for c in elem if c.tag == "Context"]
    assumptions = [_e_annotation(c, base_dir, visiting, assumption)
                   for c in elem if c.tag == "Assumption"]
    return desc, contexts, assumptions


def _e_annotation(elem: ET.Element, base_dir: Path | None, visiting: frozenset[Path],
                  ctor: Term) -> Term:
    """
    Context and Assumption share the same structure (documentation +
    optional payload). ctor is the constructor (context or assumption).
    """
    desc_elem = elem.find("description")
    val_children = [c for c in elem if c.tag != "description"]
    if desc_elem is not None:
        desc = _content(desc_elem, base_dir, visiting)
        val = _expr(val_children[0], base_dir, visiting) if val_children else string("")
    elif val_children:
        val = _expr(val_children[0], base_dir, visiting)
        desc = _text_to_term((elem.text or "").strip())
    else:
        desc = _text_to_term((elem.text or "").strip())
        val = string("")
    return ctor(description=desc, value=val)


def _e_goal(elem: ET.Element, base_dir: Path | None,
            visiting: frozenset[Path]) -> Term:
    desc, contexts, assumptions = _gsn_header(elem, base_dir, visiting)
    body = [c for c in elem if c.tag in _SUPPORT_TAGS]
    support = undeveloped
    if body:
        first = body[0]
        if first.tag == "undeveloped":
            support = undeveloped
        elif first.tag in ("Strategy", "Evidence"):
            support = _expr(first, base_dir, visiting)
        elif first.tag == "Goal":
            support = immediate(list_term(tuple(
                _e_goal(c, base_dir, visiting) for c in body if c.tag == "Goal"
            )))
        elif first.tag == "supportedBy":
            support = _content(first, base_dir, visiting)
    return goal(
        description=desc,
        contexts=list_term(tuple(contexts)),
        assumptions=list_term(tuple(assumptions)),
        support=support,
    )


def _e_strategy(elem: ET.Element, base_dir: Path | None,
                visiting: frozenset[Path]) -> Term:
    desc, _, _ = _gsn_header(elem, base_dir, visiting)
    sub_goal_elems = [c for c in elem if c.tag == "Goal"]
    sub_goals_elem = elem.find("subGoals")
    if sub_goal_elems:
        sub_goals = list_term(tuple(
            _e_goal(c, base_dir, visiting) for c in sub_goal_elems
        ))
    elif sub_goals_elem is not None:
        sub_goals = _content(sub_goals_elem, base_dir, visiting)
    else:
        raise PGSNError("<Strategy> requires sub-goals or <subGoals>")
    return strategy(description=desc, sub_goals=sub_goals)


def _e_evidence(elem: ET.Element, base_dir: Path | None,
                visiting: frozenset[Path]) -> Term:
    desc, _, _ = _gsn_header(elem, base_dir, visiting)
    return evidence(description=desc)


def _e_undeveloped(elem: ET.Element, _bd: Path | None,
                   _v: frozenset[Path]) -> Term:
    """<undeveloped/> as a general expression — the same `undeveloped`
    builtin used as <Goal>'s direct-support shorthand, but usable anywhere
    an expression is expected (e.g. <if>/<cases> branches inside
    <supportedBy>)."""
    return undeveloped


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #

def load(path: str | Path) -> Term:
    """Compile and fully evaluate a PGSN XML document file."""
    return compile_pgsn(path).fully_eval()


def load_string(xml: str, base_dir: str | Path | None = None) -> Term:
    """Compile and fully evaluate a PGSN XML document from a string.

    Imports are disallowed unless base_dir is provided.
    """
    return compile_pgsn_string(xml, base_dir).fully_eval()