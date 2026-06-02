"""PGSN XML compiler: purely syntactic mapping from XML to pgsn.dsl Terms.

XML parsing builds a single Term; all evaluation is deferred to fully_eval().
No shorthand expansion (var-attribute, def-as) in this implementation.
Semantic errors surface as non-terminating reduction.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from pgsn.dsl import (
    variable, string, list_term, record, empty_record, let,
    lambda_abs, lambda_abs_keywords,
    fix, map_term, fold, concat, cons, head, tail, index,
    true, false, if_then_else, guard,
    equal, plus, minus, times, div, mod,
    define_class, instantiate, is_instance, is_subclass,
    base_class, undefined, empty,
    boolean_and, boolean_or, boolean_not,
    has_label, list_labels, add_attribute, remove_attribute, overwrite_record,
    format_string,
)
from pgsn.gsn import (
    goal, strategy, evidence, context, assumption,
    goal_class, strategy_class, evidence_class,
    context_class, assumption_class, gsn_class,
    undeveloped, immediate,
)
import pgsn.pgsn_term as _term


class PGSNError(Exception):
    pass


# Builtins substituted inline during compilation (not at evaluation time)
_BUILTINS: dict[str, _term.Term] = {
    "fix": fix, "map_term": map_term, "fold": fold, "concat": concat,
    "cons": cons, "head": head, "tail": tail, "index": index,
    "equal": equal, "guard": guard, "if_then_else": if_then_else,
    "plus": plus, "minus": minus, "times": times, "div": div, "mod": mod,
    "boolean_and": boolean_and, "boolean_or": boolean_or,
    "boolean_not": boolean_not, "true": true, "false": false,
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
    "gsn_class": gsn_class, "goal_class": goal_class,
    "strategy_class": strategy_class, "evidence_class": evidence_class,
    "context_class": context_class, "assumption_class": assumption_class,
}

_SUPPORT_TAGS = {"Strategy", "Evidence", "Goal", "supportedBy", "undeveloped"}


def _resolve(name: str, instance_of: str | None = None) -> _term.Term:
    """Builtins are substituted inline; other names become free variables."""
    term = _BUILTINS.get(name, variable(name))
    if instance_of:
        cls = _BUILTINS.get(instance_of, variable(instance_of))
        term = guard(is_instance(term, cls))(term)
    return term


def _thread_lets(bindings: list[tuple[str, _term.Term]],
                 body: _term.Term) -> _term.Term:
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

def compile_pgsn(path: str | Path) -> _term.Term:
    """Compile a <PGSN> document file into a single Term (no evaluation)."""
    p = Path(path).resolve()
    return _compile_root(ET.parse(p).getroot(), p.parent)


def compile_pgsn_string(xml: str, base_dir: str | Path | None = None) -> _term.Term:
    """
    Compile a <PGSN> document from a string.
    Imports are disallowed unless base_dir is given to resolve relative paths.
    """
    bd = Path(base_dir).resolve() if base_dir is not None else None
    return _compile_root(ET.fromstring(xml), bd)


def _compile_root(root: ET.Element, base_dir: Path | None) -> _term.Term:
    """Compile a parsed <PGSN> root element against a base directory."""
    if root.tag != "PGSN":
        raise PGSNError(f"Expected <PGSN>, got <{root.tag}>")
    children = list(root)
    # The final value may be a bare text node (no child elements)
    if not children:
        text = (root.text or "").strip()
        if text:
            return string(text)
        raise PGSNError("<PGSN> has no value")
    final = _expr(children[-1], base_dir, frozenset())
    bindings = _bindings(children[:-1], base_dir, frozenset())
    return _thread_lets(bindings, final)


def _compile_module(root: ET.Element, base_dir: Path | None,
                    visiting: frozenset[Path]) -> _term.Term:
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
              visiting: frozenset[Path]) -> list[tuple[str, _term.Term]]:
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
                 visiting: frozenset[Path]) -> tuple[str, _term.Term]:
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
                  visiting: frozenset[Path]) -> list[tuple[str, _term.Term]]:
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
             visiting: frozenset[Path]) -> _term.Term:
    """Single value from element content: one child expression or bare text."""
    val_children = [c for c in parent if c.tag != "param"]
    if len(val_children) == 1:
        return _expr(val_children[0], base_dir, visiting)
    if len(val_children) > 1:
        raise PGSNError(f"Multiple value children in <{parent.tag}>")
    text = (parent.text or "").strip()
    if text:
        return string(text)
    raise PGSNError(f"No value in <{parent.tag}>")


def _expr(elem: ET.Element, base_dir: Path | None,
          visiting: frozenset[Path]) -> _term.Term:
    dispatch = {
        "var":      _e_var,
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
    }
    fn = dispatch.get(elem.tag)
    if fn is None:
        raise PGSNError(f"Unknown expression: <{elem.tag}>")
    return fn(elem, base_dir, visiting)


def _e_var(elem: ET.Element, _bd: Path, _v: frozenset) -> _term.Term:
    return _resolve(elem.get("name"), elem.get("instanceOf"))


def _e_template(elem: ET.Element, base_dir: Path | None,
                visiting: frozenset[Path]) -> _term.Term:
    params = [(c.get("name"), c) for c in elem if c.tag == "param"]
    body_elems = [c for c in elem if c.tag != "param"]

    if body_elems:
        body = _expr(body_elems[0], base_dir, visiting)
    elif elem.text and elem.text.strip():
        body = string(elem.text.strip())
    else:
        raise PGSNError("<template> has no body")

    if not params:
        return body

    defaults_dict = {}
    for name, pelem in params:
        pchildren = [c for c in pelem if c.tag != "param"]
        if pchildren:
            defaults_dict[name] = _expr(pchildren[0], base_dir, visiting)
        elif pelem.text and pelem.text.strip():
            defaults_dict[name] = string(pelem.text.strip())

    return lambda_abs_keywords(
        {name: variable(name) for name, _ in params},
        body,
        record(defaults_dict) if defaults_dict else empty_record,
    )


def _e_apply(elem: ET.Element, base_dir: Path | None,
             visiting: frozenset[Path]) -> _term.Term:
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
             visiting: frozenset[Path]) -> _term.Term:
    inh = elem.find("inherit")
    kwargs: dict = {
        "inherit": _content(inh, base_dir, visiting) if inh is not None else base_class
    }
    attrs = [c.get("name") for c in elem if c.tag == "attribute"]
    defs = {c.get("name"): _content(c, base_dir, visiting)
            for c in elem if c.tag == "attribute"
            and (list(c) or (c.text and c.text.strip()))}
    methods = {c.get("name"): _e_template(c, base_dir, visiting)
               for c in elem if c.tag == "method"}
    if attrs:
        kwargs["attributes"] = list_term(tuple(string(a) for a in attrs))
    if defs:
        kwargs["defaults"] = record(defs)
    if methods:
        kwargs["methods"] = record(methods)
    return define_class(**kwargs)


def _e_object(elem: ET.Element, base_dir: Path | None,
              visiting: frozenset[Path]) -> _term.Term:
    inst = elem.find("instanceOf")
    if inst is None:
        raise PGSNError("<object> requires <instanceOf>")
    return instantiate(
        _content(inst, base_dir, visiting),
        record({c.get("name"): _content(c, base_dir, visiting)
                for c in elem if c.tag == "attribute"})
    )


def _e_get(elem: ET.Element, base_dir: Path | None,
           visiting: frozenset[Path]) -> _term.Term:
    return _content(elem, base_dir, visiting)(string(elem.get("name")))


def _e_send(elem: ET.Element, base_dir: Path | None,
            visiting: frozenset[Path]) -> _term.Term:
    children = list(elem)
    if not children:
        raise PGSNError("<send> needs a receiver")
    method = _expr(children[0], base_dir, visiting)(string(elem.get("name")))
    positional, keyword = _split_args(children[1:], base_dir, visiting)
    if not positional and not keyword:
        return method
    return method(*positional, **keyword)


def _e_div(elem: ET.Element, base_dir: Path | None,
           visiting: frozenset[Path]) -> _term.Term:
    children = list(elem)
    if not children:
        raise PGSNError("<div> has no value")
    # The final child is the div's value expression (use _expr, not _content)
    final = _expr(children[-1], base_dir, visiting)
    bs = _bindings([c for c in children[:-1] if c.tag == "def"], base_dir, visiting)
    return _thread_lets(bs, final)


def _e_list(elem: ET.Element, base_dir: Path | None,
            visiting: frozenset[Path]) -> _term.Term:
    return list_term(tuple(
        _content(li, base_dir, visiting) for li in elem.findall("li")
    ))


def _e_dict(elem: ET.Element, base_dir: Path | None,
            visiting: frozenset[Path]) -> _term.Term:
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
                visiting: frozenset[Path]) -> tuple[_term.Term, list, list]:
    desc_elem = elem.find("description")
    desc = (_content(desc_elem, base_dir, visiting) if desc_elem is not None
            else string((elem.text or "").strip()))
    contexts = [_e_annotation(c, base_dir, visiting, context)
                for c in elem if c.tag == "Context"]
    assumptions = [_e_annotation(c, base_dir, visiting, assumption)
                   for c in elem if c.tag == "Assumption"]
    return desc, contexts, assumptions


def _e_annotation(elem: ET.Element, base_dir: Path | None, visiting: frozenset[Path],
                  ctor: _term.Term) -> _term.Term:
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
        desc = string((elem.text or "").strip())
    else:
        desc = string((elem.text or "").strip())
        val = string("")
    return ctor(description=desc, value=val)


def _e_goal(elem: ET.Element, base_dir: Path | None,
            visiting: frozenset[Path]) -> _term.Term:
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
                visiting: frozenset[Path]) -> _term.Term:
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
                visiting: frozenset[Path]) -> _term.Term:
    desc, _, _ = _gsn_header(elem, base_dir, visiting)
    return evidence(description=desc)


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #

def load(path: str | Path) -> _term.Term:
    """Compile and fully evaluate a PGSN XML document file."""
    return compile_pgsn(path).fully_eval()


def load_string(xml: str, base_dir: str | Path | None = None) -> _term.Term:
    """Compile and fully evaluate a PGSN XML document from a string.

    Imports are disallowed unless base_dir is provided.
    """
    return compile_pgsn_string(xml, base_dir).fully_eval()