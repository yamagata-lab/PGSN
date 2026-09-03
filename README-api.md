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
term.fully_eval()            # reduce to a normal form, default steps=100000
term.fully_eval(steps=5000)  # with an explicit budget
```

`fully_eval` returns the term unchanged if it is already in normal form. The `steps` budget bounds the number of reductions, not wall-clock time: a term that grows as it reduces can exhaust your patience well before it exhausts the budget. A term with unbound variables, or one applied to the wrong kind of argument, does not fail — it simply gets stuck, and the stuck term is what you get back.

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

**Lists** — `cons`, `head`, `tail`, `index`, `concat`, `map_term`, `fold`, `foldr`, `list_all`, `empty`

**Booleans** — `true`, `false`, `if_then_else`, `boolean_and`, `boolean_or`, `boolean_not`, `equal`, `less_than`, `guard`

**Integers** — `plus`, `minus`, `times`, `div`, `mod`, `integer_sum`, `repeat`

**Records** — `has_label`, `list_labels`, `add_attribute`, `remove_attribute`, `overwrite_record`, `empty_record`

**Strings** — `format_string`

**Classes and objects** — `define_class`, `instantiate`, `instance`, `is_instance`, `is_subclass`, `base_class`

**Other** — `fix`, `undefined`

Note that `fold` takes its arguments as `fold(f)(accumulator)(list)`, and `repeat(f, accumulator, n)` applies `f` to the accumulator `n` times.

---

## GSN constructors

Each constructor takes keyword arguments and returns a term.

| Constructor | Arguments |
|-------------|-----------|
| `goal` | `description`, `support`, `contexts` (default empty), `assumptions` (default empty) |
| `strategy` | `description`, `sub_goals` |
| `evidence` | `description` |
| `context` | `description`, `value` (default `""`) |
| `assumption` | `description`, `value` (default `""`) |
| `defeater`, `rebuttal`, `undercutter` | `description`, `support` (default undeveloped), `defeaters` (default empty) |

`support` has no default: an unsupported goal is written explicitly with `support=pgsn.undeveloped`.

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
print(pgsn.gsn_tree(g.fully_eval()).show(stdout=False))
```

```
Goal: System is secure
├── Context: Deployment: cloud
│   └── value:
└── Strategy: Argue over properties
    ├── Goal: Input is validated
    │   └── Evidence: Static analysis report
    └── Goal: Output is sanitised
        └── Undeveloped:
```

### Classes

The class values behind the constructors are `gsn_class`, `goal_class`, `strategy_class`, `evidence_class`, `context_class`, `assumption_class`, `support_class` and `undeveloped_class`. Use them with `define_class` to derive your own node types, and with `is_instance` to check one:

```python
my_goal_class = pgsn.define_class(
    inherit=pgsn.goal_class,
    attributes=pgsn.list_term((pgsn.string("owner"),)),
)
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

Evaluate first; these functions expect a term in normal form.

### `python_value(term, with_inherit_chain=False)`

Converts a term to plain Python data — `dict`, `list`, `str`, `int`, `bool`. Object nodes carry a `__ClassName__` marker key, so an evaluated goal comes back with the keys `description`, `support`, `contexts`, `assumptions` and `__Goal__`. Pass `with_inherit_chain=True` to also get `__parent_classes__`.

Raises `ValueError` if the term is not fully evaluated; the message names the path to the offending node, which is the fastest way to find a stuck sub-term.

### `gsn_tree(term)`

Returns a [treelib](https://treelib.readthedocs.io/) `Tree`.

```python
tree = pgsn.gsn_tree(evaluated)
print(tree.show(stdout=False))   # text rendering
tree.to_json()                   # JSON rendering
```

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

Both compile *and* fully evaluate, returning a normal form. The document syntax is described in [README-xml.md](README-xml.md).

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

#### `load_xml_string(xml, *, config=None, jail=None)`

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
