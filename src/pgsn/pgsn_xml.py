"""PGSN XML compiler: purely syntactic mapping from XML to pgsn.dsl Terms.

XML parsing builds a single Term; all evaluation is deferred to fully_eval().
No shorthand expansion (var-attribute, def-as) in this implementation.
Semantic errors surface as non-terminating reduction.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from pgsn.config import Config, get_config
from pgsn.jail import JailError, is_within
from pgsn.dsl import (
    variable, string, list_term, record, empty_record, let,
    lambda_abs, lambda_abs_keywords, lambda_abs_vars,
    fix, map_term, fold, foldr, concat, cons, head, tail, index, repeat,
    list_all, integer_sum,
    true, false, if_then_else, guard,
    equal, plus, minus, times, div, mod,
    define_class, instantiate, instance, is_instance, is_subclass,
    base_class, undefined, empty,
    boolean_and, boolean_or, boolean_not,
    has_label, list_labels, add_attribute, remove_attribute, overwrite_record,
    format_string,
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
# File-system view of the document being compiled
# ------------------------------------------------------------------ #

class _Chroot:
    """The file-system view granted to the document being compiled.

    `cwd` is the directory relative import paths are resolved against, and
    `root` is the boundary they may not cross — the same pair of notions a
    chroot gives a process.  `..` is therefore allowed as long as the result
    stays below `root`.

    Entering an import yields a new `_Chroot`: a jailed path (``/name/...``)
    switches `root` to that jail's root, while a relative path keeps the
    current `root`.  Crossing from one jail into another is only possible by
    naming the target jail explicitly; a relative path can never climb back
    out into the jail one came from.

    `root` and `cwd` are both None for a document compiled from a string with
    no jail of its own; such a document can only use jailed paths.
    """

    __slots__ = ("root", "cwd", "config")

    def __init__(self, root: Path | None, cwd: Path | None, config: Config):
        self.root = root
        self.cwd = cwd
        self.config = config

    @classmethod
    def for_entry(cls, path: Path, config: Config) -> "_Chroot":
        """View for an entry document opened by path.

        If the document lives inside a registered jail, that jail confines it.
        Otherwise its own directory becomes an implicit jail, so a document
        opened directly can still import its neighbours but nothing above them.
        """
        parent = path.parent
        root = config.jails.containing_root(path) or parent
        return cls(root=root, cwd=parent, config=config)

    @classmethod
    def for_jail(cls, name: str, config: Config) -> "_Chroot":
        """View for a document considered to live at the root of a jail."""
        try:
            root = config.jails.root_of(name)
        except JailError as exc:
            raise PGSNError(str(exc)) from None
        return cls(root=root, cwd=root, config=config)

    @classmethod
    def unrooted(cls, config: Config) -> "_Chroot":
        """View with no directory of its own: jailed paths only."""
        return cls(root=None, cwd=None, config=config)

    def enter(self, spec: str) -> tuple["_Chroot", Path]:
        """Resolve an import path and return the view for the imported file."""
        if not spec:
            raise PGSNError("<from> requires a non-empty 'file' attribute")

        if spec.startswith("/"):
            try:
                root, path = self.config.jails.resolve(spec)
            except JailError as exc:
                raise PGSNError(str(exc)) from None
            return _Chroot(root=root, cwd=path.parent, config=self.config), path

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
        return _Chroot(root=self.root, cwd=candidate.parent,
                       config=self.config), candidate


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
# ------------------------------------------------------------------ #

_GSN_HEADER_TAGS = {"Goal", "Strategy", "Evidence", "Context", "Assumption"}


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


# Builtins substituted inline during compilation (not at evaluation time).
#
# Every term-valued name the `pgsn` package exports is bound here under the
# same name, so that the two front ends offer the same standard library; see
# tests/test_api_consistency.py, which fails if the two drift apart.
_BUILTINS: dict[str, Term] = {
    "fix": fix, "map_term": map_term, "fold": fold, "foldr": foldr,
    "concat": concat, "list_all": list_all,
    "cons": cons, "head": head, "tail": tail, "index": index, "empty": empty,
    "repeat": repeat, "integer_sum": integer_sum,
    "equal": equal, "guard": guard, "if_then_else": if_then_else,
    "plus": plus, "minus": minus, "times": times, "div": div, "mod": mod,
    "boolean_and": boolean_and, "boolean_or": boolean_or,
    "boolean_not": boolean_not, "true": true, "false": false,
    "has_label": has_label, "list_labels": list_labels,
    "add_attribute": add_attribute, "remove_attribute": remove_attribute,
    "overwrite_record": overwrite_record, "format_string": format_string,
    "empty_record": empty_record, "undefined": undefined,
    "define_class": define_class, "instantiate": instantiate,
    "instance": instance, "is_instance": is_instance,
    "is_subclass": is_subclass, "base_class": base_class,
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


def _text_fields(s: str) -> list[str]:
    """Return the {name} field names in s, honouring Python's {{ }} escaping."""
    import string as _stringmod
    return [fname for _, fname, _, _ in _stringmod.Formatter().parse(s)
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


def _split_args(arg_elems: list[ET.Element], chroot: _Chroot,
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
            positional.append(_content(a, chroot, visiting))
        else:
            keyword[name] = _content(a, chroot, visiting)
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
    return _compile_root(ET.parse(p).getroot(),
                         _Chroot.for_entry(p, cfg), entry=p)


def compile_pgsn_string(xml: str, base_dir: str | Path | None = None, *,
                        config: Config | None = None,
                        jail: str | None = None) -> Term:
    """
    Compile a <PGSN> document from a string.

    Jailed imports (``/<jail>/...``) always work.  Relative imports need a
    directory to resolve against: pass `jail` to place the document at the root
    of a registered jail.  `base_dir` is an internal escape hatch that roots the
    document at an arbitrary directory; it is not part of the public API,
    because it turns any directory into a confinement root without validation.
    """
    cfg = get_config(config)
    if jail is not None:
        if base_dir is not None:
            raise PGSNError("pass either 'jail' or 'base_dir', not both")
        chroot = _Chroot.for_jail(jail, cfg)
    elif base_dir is not None:
        bd = Path(base_dir).resolve()
        chroot = _Chroot(root=bd, cwd=bd, config=cfg)
    else:
        chroot = _Chroot.unrooted(cfg)
    return _compile_root(ET.fromstring(xml), chroot, entry=None)


def _compile_root(root: ET.Element, chroot: _Chroot,
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
    final = _expr(children[-1], chroot, visiting)
    bindings = _bindings(children[:-1], chroot, visiting)
    return _thread_lets(bindings, final)


def _compile_module(root: ET.Element, chroot: _Chroot,
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
            defaults_dict[name] = _content(p, chroot, visiting)
        idx += 1

    body_children = children[idx:]
    export_names = [c.get("name") for c in body_children if c.tag == "def"]

    # Module body: let-chain ending in a record of all exported names
    exports = record({n: variable(n) for n in export_names})
    body = _thread_lets(_bindings(body_children, chroot, visiting), exports)

    arguments = {p: variable(p) for p in params}
    defaults_rec = record(defaults_dict) if defaults_dict else empty_record
    return lambda_abs_keywords(arguments, body, defaults_rec)


# ------------------------------------------------------------------ #
# Binding sequences  (def / from)
# ------------------------------------------------------------------ #

def _bindings(elems: list[ET.Element], chroot: _Chroot,
              visiting: frozenset[Path]) -> list[tuple[str, Term]]:
    result = []
    for elem in elems:
        if elem.tag == "def":
            result.append(_compile_def(elem, chroot, visiting))
        elif elem.tag == "from":
            result.extend(_compile_from(elem, chroot, visiting))
        else:
            raise PGSNError(f"Unexpected element: <{elem.tag}>")
    return result


def _compile_def(elem: ET.Element, chroot: _Chroot,
                 visiting: frozenset[Path]) -> tuple[str, Term]:
    name = elem.get("name")
    term = _content(elem, chroot, visiting)

    if elem.get("recursive", "false").lower() == "true":
        term = fix(lambda_abs(variable(name), term))

    instance_of = elem.get("instanceOf")
    if instance_of:
        cls = _BUILTINS.get(instance_of, variable(instance_of))
        term = guard(is_instance(term, cls))(term)

    return name, term


def _compile_from(elem: ET.Element, chroot: _Chroot,
                  visiting: frozenset[Path]) -> list[tuple[str, Term]]:
    """
    File I/O at compile time (path is a static literal).
    Module application and field access are lazy Terms.
    """
    file_path = elem.get("file", "")
    inner, full = chroot.enter(file_path)
    if full in visiting:
        raise PGSNError(f"Circular import: {full}")

    root = ET.parse(full).getroot()
    if root.tag != "PGSNModule":
        raise PGSNError(f"Expected <PGSNModule> in {file_path!r}")
    _preprocess(root)

    module_term = _compile_module(root, inner, visiting | {full})

    # Args compiled in the caller's scope — they are Terms, not values yet
    args = {a.get("name"): _content(a, chroot, visiting)
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

def _content(parent: ET.Element, chroot: _Chroot,
             visiting: frozenset[Path]) -> Term:
    """Single value from element content: one child expression or bare text."""
    val_children = [c for c in parent if c.tag != "param"]
    if len(val_children) == 1:
        return _expr(val_children[0], chroot, visiting)
    if len(val_children) > 1:
        raise PGSNError(f"Multiple value children in <{parent.tag}>")
    text = (parent.text or "").strip()
    if text:
        return _text_to_term(text)
    raise PGSNError(f"No value in <{parent.tag}>")


def _expr(elem: ET.Element, chroot: _Chroot,
          visiting: frozenset[Path]) -> Term:
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
    return fn(elem, chroot, visiting)


def _e_var(elem: ET.Element, _ch: "_Chroot", _v: frozenset) -> Term:
    return _resolve(elem.get("name"), elem.get("instanceOf"))


def _e_template(elem: ET.Element, chroot: _Chroot,
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
        final = _expr(final_elem, chroot, visiting)
    else:
        final = _text_to_term(elem.text.strip())

    bindings = _bindings(leading, chroot, visiting)
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
            defaults_dict[name] = _expr(pchildren[0], chroot, visiting)
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


def _e_apply(elem: ET.Element, chroot: _Chroot,
             visiting: frozenset[Path]) -> Term:
    children = list(elem)
    if not children:
        raise PGSNError("<apply> needs a function")
    func = _expr(children[0], chroot, visiting)
    positional, keyword = _split_args(children[1:], chroot, visiting)
    if not positional and not keyword:
        raise PGSNError("<apply> needs at least one <arg>")
    # Delegate to Term.__call__: it casts args and builds the keyword Record
    return func(*positional, **keyword)


def _e_class(elem: ET.Element, chroot: _Chroot,
             visiting: frozenset[Path]) -> Term:
    inh = elem.find("inherit")
    kwargs: dict = {
        "inherit": _content(inh, chroot, visiting) if inh is not None else base_class
    }
    attrs = [c.get("name") for c in elem if c.tag == "attribute"]
    defs = {c.get("name"): _content(c, chroot, visiting)
            for c in elem if c.tag == "attribute"
            and (list(c) or (c.text and c.text.strip()))}
    # Methods must be stored as λself.body so that PGSNObject._apply_arg can
    # call (method)(self) to bind the receiver. This mirrors the DSL pattern:
    #   define_class(methods={'m': lambda_abs(self_var, body)})
    _self_var = variable("self")
    methods = {c.get("name"): lambda_abs(_self_var, _e_template(c, chroot, visiting))
               for c in elem if c.tag == "method"}
    if attrs:
        kwargs["attributes"] = list_term(tuple(string(a) for a in attrs))
    if defs:
        kwargs["defaults"] = record(defs)
    if methods:
        kwargs["methods"] = record(methods)
    return define_class(**kwargs)


def _e_object(elem: ET.Element, chroot: _Chroot,
              visiting: frozenset[Path]) -> Term:
    inst = elem.find("instanceOf")
    if inst is None:
        raise PGSNError("<object> requires <instanceOf>")
    return instantiate(
        _content(inst, chroot, visiting),
        record({c.get("name"): _content(c, chroot, visiting)
                for c in elem if c.tag == "attribute"})
    )


def _e_get(elem: ET.Element, chroot: _Chroot,
           visiting: frozenset[Path]) -> Term:
    return _content(elem, chroot, visiting)(string(elem.get("name")))


def _e_send(elem: ET.Element, chroot: _Chroot,
            visiting: frozenset[Path]) -> Term:
    children = list(elem)
    if not children:
        raise PGSNError("<send> needs a receiver")
    # receiver("methodName") triggers PGSNObject._apply_arg which automatically
    # applies self (the receiver) to the method value before returning it.
    method = _expr(children[0], chroot, visiting)(string(elem.get("name")))
    positional, keyword = _split_args(children[1:], chroot, visiting)
    if not positional and not keyword:
        return method
    return method(*positional, **keyword)


def _e_div(elem: ET.Element, chroot: _Chroot,
           visiting: frozenset[Path]) -> Term:
    children = list(elem)
    if not children:
        raise PGSNError("<div> has no value")
    # The final child is the div's value expression (use _expr, not _content)
    final = _expr(children[-1], chroot, visiting)
    bs = _bindings([c for c in children[:-1] if c.tag == "def"], chroot, visiting)
    return _thread_lets(bs, final)


def _e_list(elem: ET.Element, chroot: _Chroot,
            visiting: frozenset[Path]) -> Term:
    return list_term(tuple(
        _content(li, chroot, visiting) for li in elem.findall("li")
    ))


def _e_dict(elem: ET.Element, chroot: _Chroot,
            visiting: frozenset[Path]) -> Term:
    children = list(elem)
    attrs = {}
    for i in range(0, len(children) - 1, 2):
        dt, dd = children[i], children[i + 1]
        key = dt.get("key") or (dt.text or "").strip()
        if not key:
            raise PGSNError("<dt> key must be a string literal")
        attrs[key] = _content(dd, chroot, visiting)
    return record(attrs)


# ------------------------------------------------------------------ #
# GSN node compilers
# ------------------------------------------------------------------ #

def _gsn_header(elem: ET.Element, chroot: _Chroot,
                visiting: frozenset[Path]) -> tuple[Term, list, list]:
    desc_elem = elem.find("description")
    desc = (_content(desc_elem, chroot, visiting) if desc_elem is not None
            else _text_to_term((elem.text or "").strip()))
    contexts = [_e_annotation(c, chroot, visiting, context)
                for c in elem if c.tag == "Context"]
    assumptions = [_e_annotation(c, chroot, visiting, assumption)
                   for c in elem if c.tag == "Assumption"]
    return desc, contexts, assumptions


def _e_annotation(elem: ET.Element, chroot: _Chroot, visiting: frozenset[Path],
                  ctor: Term) -> Term:
    """
    Context and Assumption share the same structure (documentation +
    optional payload). ctor is the constructor (context or assumption).
    """
    desc_elem = elem.find("description")
    val_children = [c for c in elem if c.tag != "description"]
    if desc_elem is not None:
        desc = _content(desc_elem, chroot, visiting)
        val = _expr(val_children[0], chroot, visiting) if val_children else string("")
    elif val_children:
        val = _expr(val_children[0], chroot, visiting)
        desc = _text_to_term((elem.text or "").strip())
    else:
        desc = _text_to_term((elem.text or "").strip())
        val = string("")
    return ctor(description=desc, value=val)


def _e_goal(elem: ET.Element, chroot: _Chroot,
            visiting: frozenset[Path]) -> Term:
    desc, contexts, assumptions = _gsn_header(elem, chroot, visiting)
    body = [c for c in elem if c.tag in _SUPPORT_TAGS]
    support = undeveloped
    if body:
        first = body[0]
        if first.tag == "undeveloped":
            support = undeveloped
        elif first.tag in ("Strategy", "Evidence"):
            support = _expr(first, chroot, visiting)
        elif first.tag == "Goal":
            support = immediate(list_term(tuple(
                _e_goal(c, chroot, visiting) for c in body if c.tag == "Goal"
            )))
        elif first.tag == "supportedBy":
            support = _content(first, chroot, visiting)
    return goal(
        description=desc,
        contexts=list_term(tuple(contexts)),
        assumptions=list_term(tuple(assumptions)),
        support=support,
    )


def _e_strategy(elem: ET.Element, chroot: _Chroot,
                visiting: frozenset[Path]) -> Term:
    desc, _, _ = _gsn_header(elem, chroot, visiting)
    sub_goal_elems = [c for c in elem if c.tag == "Goal"]
    sub_goals_elem = elem.find("subGoals")
    if sub_goal_elems:
        sub_goals = list_term(tuple(
            _e_goal(c, chroot, visiting) for c in sub_goal_elems
        ))
    elif sub_goals_elem is not None:
        sub_goals = _content(sub_goals_elem, chroot, visiting)
    else:
        raise PGSNError("<Strategy> requires sub-goals or <subGoals>")
    return strategy(description=desc, sub_goals=sub_goals)


def _e_evidence(elem: ET.Element, chroot: _Chroot,
                visiting: frozenset[Path]) -> Term:
    desc, _, _ = _gsn_header(elem, chroot, visiting)
    return evidence(description=desc)


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #

def load_xml(path: str | Path, *, config: Config | None = None) -> Term:
    """Compile and fully evaluate a PGSN XML document file.

    Imports inside the document may name files below the jails registered in
    `config`, written as ``/<jail>/sub/file.xml``, and files below the
    document's own confinement root.  Nothing else is reachable.
    """
    return compile_pgsn(path, config=config).fully_eval()


def load_xml_string(xml: str, *, config: Config | None = None,
                    jail: str | None = None) -> Term:
    """Compile and fully evaluate a PGSN XML document held in a string.

    Jailed imports always work.  Pass `jail` to say which jail the document
    should be considered to live in; relative imports then resolve from that
    jail's root.  Without it, relative imports are rejected.
    """
    return compile_pgsn_string(xml, config=config, jail=jail).fully_eval()


def load(path: str | Path, *, config: Config | None = None) -> Term:
    """Deprecated alias of `load_xml`."""
    return load_xml(path, config=config)


def load_string(xml: str, base_dir: str | Path | None = None, *,
                config: Config | None = None, jail: str | None = None) -> Term:
    """Deprecated alias of `load_xml_string`, retaining the `base_dir` form."""
    return compile_pgsn_string(xml, base_dir, config=config,
                               jail=jail).fully_eval()