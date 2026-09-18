# PGSN Python API

Everything supported is reachable from the top-level package:

```python
import pgsn
```

`pgsn.__all__` is the complete public surface. Anything not listed there — including the submodules `pgsn.dsl`, `pgsn.gsn`, `pgsn.pgsn_term`, `pgsn.pgsn_xml`, `pgsn.dcom`, `pgsn.helpers` and `pgsn.cli` — is implementation detail and may change without notice.

There are two ways in: build a term in Python, or load one from an XML document. Both produce a `Term`, and everything downstream is the same.

- [Terms and evaluation](#terms-and-evaluation)
- [Building constants and terms](#building-constants-and-terms)
- [Builtin terms](#builtin-terms)
- [GSN constructors](#gsn-constructors)
- [Reading results](#reading-results)
- [Loading XML](#loading-xml)
- [Errors](#errors)

---

## Terms and evaluation

`Term` is the type of every PGSN value. Terms are immutable and are built by composition; nothing is computed until you ask for it.

### Application

Calling a term applies it. Positional arguments are applied one at a time; keyword arguments are collected into a single record and applied last.

```python
pgsn.plus(pgsn.integer(1))(pgsn.integer(2))   # curried
pgsn.plus(pgsn.integer(1), pgsn.integer(2))   # same thing
pgsn.goal(description=..., support=...)       # keyword record
```

Python values are cast automatically where a term is expected, so `pgsn.string("a")` and `"a"` are interchangeable as arguments.

### Evaluation

```python
term.eval()                  # one reduction step
term.fully_eval()            # reduce to a weak normal form, default steps=1000000
term.fully_eval(steps=5000)  # with an explicit budget
```

`fully_eval` returns the term unchanged if it is already a weak normal form. Evaluation does not enter the body of a function — a function is a value — while the elements of a list, the fields of a record and the attributes of an object are reduced throughout, which is what `python_value` needs. The `steps` budget bounds the number of reductions, not wall-clock time: a term that grows as it reduces can exhaust your patience well before it exhausts the budget. A term with unbound variables, or one applied to the wrong kind of argument, does not fail — it simply gets stuck, and the stuck term is what you get back. [PGSN-implementation.md](PGSN-implementation.md) explains the choice.

---

## Building constants and terms

### Literals

| Function | Builds |
|----------|--------|
| `string(s)` | a string |
| `integer(i)` | an integer |
| `boolean(b)` | a boolean |
| `list_term((t1, t2, ...))` | a list, from a **tuple** of terms |
| `record({"k": t, ...})` | a record |
| `variable(name)` | a variable |
| `constant(name)` | an opaque constant |

### Abstraction and binding

| Function | Meaning |
|----------|---------|
| `lambda_abs(v, body)` | one-parameter function |
| `lambda_abs_vars((v1, v2, ...), body)` | curried multi-parameter function |
| `lambda_abs_keywords(arguments, body, defaults)` | keyword-argument function; `arguments` maps names to variables, `defaults` is a record |
| `let(v, t, body)` | bind `v` to `t` inside `body` |
| `let_vars(((v1, t1), ...), body)` | several bindings at once |
| `fix(f)` | fixed point, for recursion |

```python
x = pgsn.variable("x")
double = pgsn.lambda_abs(x, pgsn.plus(x)(x))
pgsn.python_value(double(pgsn.integer(21)).fully_eval())   # 42
```

---

## Builtin terms

These are terms, not Python functions: they are values you apply. XML exposes exactly the same names — see [README-xml.md](README-xml.md).

**Lists** — `cons`, `head`, `tail`, `index`, `is_empty`, `concat`, `map_term`, `fold`, `foldr`, `list_all`, `empty`

**Booleans** — `true`, `false`, `if_then_else`, `boolean_and`, `boolean_or`, `boolean_not`, `equal`, `less_than`, `guard`

**Integers** — `plus`, `minus`, `times`, `div`, `mod`, `integer_sum`, `repeat`

**Records** — `has_label`, `list_labels`, `add_attribute`, `remove_attribute`, `overwrite_record`, `empty_record`

**Strings** — `format_string`

**Classes and objects** — `define_class`, `instantiate`, `type_of`, `is_subtype`, `base_class`

**Other** — `fix`, `undefined`

Note that `fold` takes its arguments as `fold(f)(accumulator)(list)`, and `repeat(f, accumulator, n)` applies `f` to the accumulator `n` times.

`fold` is another name for `foldr`; there is no left fold. It folds from the right, and `f` receives an element first and the accumulator second, so `fold(f)(z)([x1, x2])` is `f(x1)(f(x2)(z))`.

---

## GSN constructors

Each constructor takes keyword arguments and returns a term.

| Constructor | Arguments |
|-------------|-----------|
| `goal` | `description`, `support`, `contexts` (default empty), `assumptions` (default empty), `defeaters` (default empty) |
| `strategy` | `description`, `sub_goals`, `contexts` (default empty), `assumptions` (default empty), `defeaters` (default empty) |
| `evidence` | `description`, `defeaters` (default empty) |
| `context` | `description` |
| `assumption` | `description` |
| `defeater` | `description`, `support` (default undeveloped), `defeaters` (default empty) |

`support` has no default: an unsupported goal is written explicitly with `support=pgsn.undeveloped`.

`contexts` and `assumptions` belong to a goal and to a strategy, which are the two the standard attaches them to. Evidence takes neither.

`defeaters` is the dialectic extension of GSN v3: a defeater records a doubt about the node holding it rather than support for it. Every node type accepts one, and a defeater is itself a node, so challenges nest. The standard has no Defeater element — there a defeater is a Goal or Solution joined to its target by a Challenges relationship — but a language of values has no edges to carry that relationship, so PGSN makes the challenging role a class. One class covers both rebutting and undercutting defeaters: fill in `support` for a defeater that argues its case, leave it out for one that merely states an objection.

Two helpers cover common shapes:

- `immediate(goals)` — a strategy that simply carries a list of sub-goals
- `evidence_as_goal(ev)` — a goal whose description and support both come from an evidence node

```python
import pgsn

g = pgsn.goal(
    description="System is secure",
    contexts=pgsn.list_term((pgsn.context(description="Deployment: cloud"),)),
    support=pgsn.strategy(
        description="Argue over properties",
        sub_goals=pgsn.list_term((
            pgsn.goal(description="Input is validated",
                      support=pgsn.evidence(description="Static analysis report")),
            pgsn.goal(description="Output is sanitised",
                      support=pgsn.undeveloped),
        )),
    ),
)
print(pgsn.gsn_tree(g.fully_eval()).show(stdout=False, sorting=False))
```

```
Goal: System is secure
├── Context: Deployment: cloud
└── Strategy: Argue over properties
    ├── Goal: Input is validated
    │   └── Evidence: Static analysis report
    └── Goal: Output is sanitised
        └── Undeveloped:
```

### Classes

The class values behind the constructors are `gsn_class`, `goal_class`, `strategy_class`, `evidence_class`, `context_class`, `assumption_class`, `defeater_class`, `support_class` and `undeveloped_class`. Use them with `define_class` to derive your own node types:

```python
my_goal_class = pgsn.define_class(
    name="OwnedGoal",
    inherit=pgsn.goal_class,
    attributes=pgsn.list_term((pgsn.string("owner"),)),
)
```

`name` is what the class is called, and an object is reported under it — the
`__ClassName__` key below. It is a label and nothing compares it, but a class
whose instances you mean to read back needs one, since there would otherwise
be nothing to report them as. It is not inherited.

`type_of` returns the class of an object and `is_subtype` compares two classes,
so a value is checked against a type like this, `node` being a term you have
built:

```python
pgsn.is_subtype(pgsn.type_of(node))(pgsn.goal_class).fully_eval().value
```

Typing is structural: `is_subtype` compares the attribute and method names the
two classes declare, and `inherit` plays no part. A class of your own
satisfies `evidence_class` by carrying `description` and `defeaters`, and a
goal satisfies it too, since it declares those and more. There is no predicate
that asks which class a value belongs to: two copies of one class cannot be
relied on to compare equal, so the answer would depend on where the copies
came from.
To ask where a class came from, read the inheritance chain off the object:

```python
pgsn.python_value(node.fully_eval(),
                  with_inherit_chain=True)["__parent_classes__"]
```

### Templates

A GSN template is an ordinary function returning a node, so `map_term` expands one over a list:

```python
x = pgsn.variable("x")
template = pgsn.lambda_abs(
    x, pgsn.goal(description=x, support=pgsn.evidence(description=x)))

requirements = pgsn.list_term((pgsn.string("R1"), pgsn.string("R2")))
goals = pgsn.map_term(template)(requirements)
```

---

## Reading results

Evaluate first; these functions expect an evaluated term.

### `python_value(term, with_inherit_chain=False)`

Converts a term to plain Python data — `dict`, `list`, `str`, `int`, `bool`. Object nodes carry a `__ClassName__` marker key, so an evaluated goal comes back with the keys `description`, `support`, `contexts`, `assumptions`, `defeaters` and `__Goal__`. Pass `with_inherit_chain=True` to also get `__parent_classes__`.

Raises `ValueError` if the term is not fully evaluated; the message names the path to the offending node, which is the fastest way to find a stuck sub-term. It raises as well for an object whose class has no name, there being no marker key to give it.

### `gsn_tree(term)`

Returns a [treelib](https://treelib.readthedocs.io/) `Tree`.

```python
tree = pgsn.gsn_tree(evaluated)
print(tree.show(stdout=False, sorting=False))   # text rendering
tree.to_json(sort=False)                        # JSON rendering
```

treelib sorts siblings by tag unless told otherwise, so ask it not to: the order of a list is part of what the document says, and `python_value` reports that order. `pgsn doc` passes the same options.

### `gsn_dot(term, layout_attrs=None)`

Returns a `graphviz.Digraph` with GSN node shapes applied. `layout_attrs` overrides the defaults (`rankdir`, `splines`, `nodesep`, `ranksep`).

```python
dot = pgsn.gsn_dot(evaluated, {"rankdir": "LR"})
dot.render("out", format="svg", cleanup=True)
```

### `save_gsn(term, filename, image_format="png", view=False, cleanup=True)`

Renders straight to a file.

---

## Loading XML

```python
term = pgsn.load_xml("main.xml")
term = pgsn.load_xml_string(source)
```

Both compile *and* evaluate, returning a weak normal form. The document syntax is described in [README-xml.md](README-xml.md).

Both also take `steps`, which bounds the evaluation exactly as it does in `fully_eval`. Omitting it leaves the default budget in place, and there is one such budget: the same number the `pgsn` command starts from, so a document the command evaluates is one a program evaluates too. A document large enough to exhaust it is not thereby wrong, so a caller who knows better says so:

```python
term = pgsn.load_xml("big.xml", steps=5_000_000)
```

### Jails

A document can import other documents, and what it may reach is controlled by a *jail table*. A jail is a named directory root; the document names it as the first component of an absolute-looking path:

```xml
<from file="/lib/security.xml" import="secureGoal"/>
```

```python
cfg = pgsn.Config(jails={"lib": "/opt/pgsn-lib"})
term = pgsn.load_xml("main.xml", config=cfg)
```

A document opened by path that lies in no registered jail is confined to its own directory. Relative imports may use `..` as long as they stay inside the confinement root, symbolic links are expanded before that check, and a module reached through a jail cannot climb back out of it.

#### `Jails(roots)`

An immutable table built from a mapping of name to path. Roots are validated and resolved once, at construction time; a missing directory raises `JailError` immediately rather than at import time. Names may contain letters, digits, `_` and `-`.

```python
jails = pgsn.Jails({"lib": "/opt/pgsn-lib", "proj": "./modules"})
jails.names            # ('lib', 'proj')
"lib" in jails         # True
jails.root_of("lib")   # PosixPath('/opt/pgsn-lib')
```

#### `Config(jails=None)`

Immutable settings. Accepts a `Jails` or a plain mapping. `config.jails` reads the table back, and `config.replace(jails=...)` derives a variant.

#### `configure(config=None, *, jails=None)` and `get_config(config=None)`

`configure` installs the default configuration used when a call omits `config`; it may be called more than once. `get_config` returns the current default, or validates and returns the configuration you pass it.

```python
pgsn.configure(jails={"lib": "/opt/pgsn-lib"})
pgsn.load_xml("main.xml")        # uses the default
pgsn.load_xml("other.xml", config=other_cfg)   # overrides it
```

The default is a convenience, not a security boundary. What confines a document is the `Jails` table in the configuration actually used for that call. Untrusted input to PGSN is XML, and XML cannot reach these functions.

#### `load_xml_string(xml, *, config=None, jail=None, steps=None)`

A document held in a string has no directory of its own, so relative imports are rejected unless you say which jail it should be considered to live in:

```python
pgsn.load_xml_string(source, config=cfg, jail="lib")
```

Jailed imports (`/lib/...`) work either way.

---

## Errors

`PGSNError` covers everything raised while compiling a document: malformed syntax, unknown elements, circular imports, and every rejected import path. `JailError` covers invalid jail definitions — it is raised by `Jails` at construction time, and is converted to `PGSNError` when it happens during compilation, so catching `PGSNError` around a load is sufficient.

```python
try:
    term = pgsn.load_xml(path, config=cfg)
except pgsn.PGSNError as e:
    print(f"could not load {path}: {e}")
```
