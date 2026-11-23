# PGSN Python API

Everything supported is reachable from the top-level package:

```python
import pgsn
```

`pgsn.__all__` is the complete public surface. Anything not listed there — including the submodules `pgsn.dsl`, `pgsn.gsn`, `pgsn.pgsn_term`, `pgsn.pgsn_xml`, `pgsn.helpers`, `pgsn.config`, `pgsn.jail` and `pgsn.cli` — is implementation detail and may change without notice. Besides the functions and terms below, it holds `__version__` and `LABEL_WIDTH`, the column at which node labels are wrapped by default (the default of `label_width` in `gsn_dot` and `save_gsn`, and of `pgsn render --label-width`).

There are two ways in: load an XML document, which `load_xml` compiles and evaluates for you, or build a term in Python and evaluate it with `fully_eval()`. Either way you end with an evaluated term, and the functions under [Reading results](#reading-results) take it from there. Where the package behaves otherwise than described here, the deviation is listed in [known_issues.md](known_issues.md). [README-ja-api.md](README-ja-api.md) is the Japanese version of this document.

Contents:

1. [Quick start](#quick-start)
2. [Terms and evaluation](#terms-and-evaluation)
3. [Building terms](#building-terms)
4. [Builtin terms](#builtin-terms)
5. [GSN nodes](#gsn-nodes)
6. [Classes and objects](#classes-and-objects)
7. [Reading results](#reading-results)
8. [Loading XML](#loading-xml)
9. [Configuration and jails](#configuration-and-jails)
10. [Errors](#errors)

---

## Quick start

Load an XML document and read the result:

```python
import pgsn

result = pgsn.load_xml("examples/gsn.xml")              # compiled and evaluated
print(pgsn.gsn_tree(result).show(stdout=False, sorting=False))
data = pgsn.python_value(result)                        # plain dicts and lists
problems = pgsn.gsn_violations(result)                  # breaches of GSN v3
```

Build the same structure in Python instead, then evaluate it once:

```python
g = pgsn.goal(
    description="System is secure",
    support=pgsn.strategy(
        description="Break into sub-goals",
        sub_goals=[
            pgsn.goal(description="Input validated",
                      support=pgsn.solution(description="Static analysis passed")),
            pgsn.goal(description="Output sanitized",
                      support=pgsn.solution(description="Fuzzing test succeeded")),
        ],
    ),
)
result = g.fully_eval()
print(pgsn.gsn_tree(result).show(stdout=False, sorting=False))
```

```
Goal: System is secure
└── Strategy: Break into sub-goals
    ├── Goal: Input validated
    │   └── Solution: Static analysis passed
    └── Goal: Output sanitized
        └── Solution: Fuzzing test succeeded
```

---

## Terms and evaluation

`Term` is the type of every PGSN value. Terms are immutable and are built by composition; nothing is computed until you ask for it.

### Application

Calling a term applies it. Positional arguments are applied one at a time; keyword arguments are collected into a single record and applied last.

```python
pgsn.plus(pgsn.integer(1))(pgsn.integer(2))   # one argument at a time
pgsn.plus(pgsn.integer(1), pgsn.integer(2))   # the same, all at once
pgsn.goal(description=..., support=...)       # keyword record
```

A record or an object is read by applying it to a label: `pgsn.record({"a": pgsn.integer(1)})("a")` evaluates to `1`, and a goal applied to `"description"` gives its description.

A Python value passed as an argument is made into a term: `str` becomes `string`, `int` becomes `integer`, `bool` becomes `boolean`, `list` and `tuple` become `list_term`, and `dict` becomes `record`, recursively. Any other Python value raises `TypeError`. `list_term` and `record` themselves take terms only: `pgsn.list_term((pgsn.string("a"),))`.

### Evaluation

```python
term.fully_eval()            # evaluate the whole term, with the default limit steps=1000000
term.fully_eval(steps=5000)  # with a limit of your own
```

Build the whole term first, then evaluate it once. What evaluation returns is a result to read: pass it to `python_value`, `gsn_tree` or a renderer. Applying it to something, or passing it as an argument to build another term, is not supported.

`steps` stops a term that does not terminate. One step is one application, by the evaluator, of a function or a builtin to its arguments, and evaluation stops with the error described under [Errors](#errors) when the limit is reached. It does not limit memory or time, since a single step can cost any amount. The default is enough for ordinary documents; raise it only when a large one reaches it. How steps are counted may change in a future version.

### When evaluation cannot go on

A mistake in the term — a label the record does not have, an argument of the wrong kind, a name that is not defined — does not stop evaluation with an error. That part of the term is left as it is, *stuck*, and the error comes when you read the result: [`python_value`](#python_valueterm-with_inherit_chainfalse) raises `ValueError` and names the path at which evaluation could not go on. A stuck part that nothing reads does no harm. [PGSN-implementation.md](PGSN-implementation.md) explains why.

---

## Building terms

### Data, variables and constants

| Function | Builds |
|----------|--------|
| `string(s)` | a string |
| `integer(i)` | an integer |
| `boolean(b)` | a boolean |
| `list_term((t1, t2, ...))` | a list, from a **tuple** of terms |
| `record({"k": t, ...})` | a record, from a dict of terms |
| `variable(name)` | a variable |
| `constant(name)` | an opaque constant |

### Functions and bindings

| Function | Meaning |
|----------|---------|
| `lambda_abs(v, body)` | a function of one parameter |
| `lambda_abs_vars((v1, v2, ...), body)` | a function of several parameters, applied one at a time |
| `lambda_abs_keywords(arguments, body, defaults=empty record)` | a function of keyword parameters; `arguments` maps names to variables, `defaults` is a record of default values |
| `let(v, t, body)` | bind `v` to `t` inside `body` |
| `let_vars(((v1, t1), ...), body)` | several bindings at once |

Recursion uses the builtin [`fix`](#builtin-terms).

```python
x = pgsn.variable("x")
double = pgsn.lambda_abs(x, pgsn.plus(x)(x))
pgsn.python_value(double(pgsn.integer(21)).fully_eval())   # 42

n = pgsn.variable("n")
inc = pgsn.lambda_abs_keywords({"n": n}, pgsn.plus(n)(1),
                               pgsn.record({"n": pgsn.integer(1)}))
pgsn.python_value(inc().fully_eval())      # 2: n takes its default
pgsn.python_value(inc(n=5).fully_eval())   # 6

f = pgsn.variable("f")
fact = pgsn.fix(pgsn.lambda_abs_vars((f, n),
    pgsn.if_then_else(pgsn.equal(n)(0))(1)(pgsn.times(n)(f(pgsn.minus(n)(1))))))
pgsn.python_value(fact(5).fully_eval())    # 120
```

A keyword parameter without a default that the call leaves out has no value, and the application is stuck.

### Templates

A GSN template is an ordinary function returning a node, so `map_term` expands one over a list:

```python
x = pgsn.variable("x")
template = pgsn.lambda_abs(
    x, pgsn.goal(description=x, support=pgsn.solution(description=x)))

goals = pgsn.map_term(template)(["R1", "R2"])
top = pgsn.goal(description="All requirements are met",
                support=pgsn.immediate(goals))
```

---

## Builtin terms

These are terms, not Python functions: they are values you apply, one argument at a time or all at once. XML binds the same builtins under the same names, and adds the short class aliases `Goal`, `Strategy`, … — see [README-xml.md](README-xml.md#builtins).

| Builtin | Applied as | Result |
|---|---|---|
| `cons` | `cons(x)(xs)` | `xs` with `x` in front |
| `head`, `tail` | `head(xs)`, `tail(xs)` | the first element; the rest of the list |
| `index` | `index(xs)(i)` | the `i`-th element, counting from 0; a negative `i` counts from the end, as in Python |
| `is_empty` | `is_empty(xs)` | whether `xs` is empty |
| `concat` | `concat(xs)(ys)` | `xs` followed by `ys` |
| `map_term` | `map_term(f)(xs)` | `f` applied to every element |
| `fold`, `foldr` | `fold(f)(z)(xs)` | a right fold: `fold(f)(z)([x1, x2])` is `f(x1)(f(x2)(z))`. `fold` is another name for `foldr`; there is no left fold |
| `list_all` | `list_all(p)(xs)` | whether `p` holds for every element |
| `empty` | `empty` | the empty list |
| `true`, `false` | | the booleans |
| `if_then_else` | `if_then_else(c)(a)(b)` | `a` if `c` holds, otherwise `b`; only the branch chosen is evaluated |
| `boolean_and`, `boolean_or`, `boolean_not` | `boolean_and(a)(b)`, `boolean_not(a)` | the logical operations |
| `equal` | `equal(a)(b)` | whether two pieces of data are equal; anything other than data is stuck |
| `less_than` | `less_than(a)(b)` | whether `a < b`, for integers |
| `guard` | `guard(c)(v)` | `v` if `c` is true; otherwise stuck |
| `plus`, `minus`, `times` | `plus(a)(b)` | integer arithmetic |
| `div`, `mod` | `div(a)(b)` | Python's `//` and `%`: `div(-7)(2)` is `-4`, `mod(-7)(2)` is `1`. Division by zero is stuck |
| `integer_sum` | `integer_sum(xs)` | the sum of a list of integers |
| `repeat` | `repeat(f)(z)(n)` | `f` applied to `z`, `n` times |
| `has_label` | `has_label(r)(k)` | whether the record `r` has the label `k` |
| `add_attribute` | `add_attribute(r)(k)(v)` | `r` with the label `k` set to `v` |
| `remove_attribute` | `remove_attribute(r)(k)` | `r` without the label `k` |
| `overwrite_record` | `overwrite_record(r)(s)` | `r` with the labels of `s` added; those of `s` win |
| `empty_record` | `empty_record` | the record with no labels |
| `format_string` | `format_string(t)(r)` | the string `t` with each `{label}` replaced from the record `r`: `format_string("{a}-{b}")({"a": "x", "b": 2})` is `"x-2"` |
| `define_class`, `instantiate`, `type_of`, `is_subtype`, `base_class` | | see [Classes and objects](#classes-and-objects) |
| `fix` | `fix(f)` | the fixed point of `f`, for recursion (see the example under [Functions and bindings](#functions-and-bindings)) |
| `undefined` | `undefined` | a named constant |

---

## GSN nodes

Each constructor takes keyword arguments and returns a term.

| Constructor | Arguments |
|-------------|-----------|
| `goal` | `description`, `support`, `contexts` (default empty), `assumptions` (default empty), `defeaters` (default empty) |
| `strategy` | `description`, `sub_goals`, `contexts` (default empty), `assumptions` (default empty), `defeaters` (default empty) |
| `solution` | `description`, `defeaters` (default empty) |
| `context` | `description` |
| `assumption` | `description` |
| `defeater` | `description`, `support` (default undeveloped), `defeaters` (default empty) |

`undeveloped` is a value, not a constructor: the support of a goal that is not developed yet. `support` has no default, so an unsupported goal is written with `support=pgsn.undeveloped`.

`contexts` and `assumptions` belong to a goal and to a strategy, the two node types GSN v3 attaches them to. A solution takes neither.

`defeaters` is the dialectic extension of GSN v3: a defeater records a doubt about the node holding it rather than support for it. A goal, a strategy, a solution and a defeater can each hold defeaters, so challenges nest. Fill in `support` for a defeater that argues its case, and leave it out for one that merely states an objection. The Defeater node is PGSN's own: GSN v3 has no such element, and [PGSN-implementation.md](PGSN-implementation.md) explains the choice.

Two helpers cover common shapes:

- `immediate(goals)` — a strategy that simply carries a list of sub-goals. How it shows in the output is listed in [known_issues.md](known_issues.md).
- `solution_as_goal(s)` — a goal whose description and support both come from a solution node.

```python
import pgsn

g = pgsn.goal(
    description="System is secure",
    contexts=[pgsn.context(description="Deployment: cloud")],
    support=pgsn.strategy(
        description="Argue over properties",
        sub_goals=[
            pgsn.goal(description="Input is validated",
                      support=pgsn.solution(description="Static analysis report")),
            pgsn.goal(description="Output is sanitized",
                      support=pgsn.undeveloped),
        ],
    ),
)
evaluated = g.fully_eval()
print(pgsn.gsn_tree(evaluated).show(stdout=False, sorting=False))
```

```
Goal: System is secure
├── Context: Deployment: cloud
└── Strategy: Argue over properties
    ├── Goal: Input is validated
    │   └── Solution: Static analysis report
    └── Goal: Output is sanitized
        └── Undeveloped:
```

The examples below use `evaluated` from this one.

---

## Classes and objects

The class values behind the GSN constructors are `gsn_class`, `goal_class`, `strategy_class`, `solution_class`, `context_class`, `assumption_class`, `defeater_class`, `support_class` and `undeveloped_class`.

`define_class(name=..., inherit=..., attributes=[...])` makes a class, and `instantiate(cls, **attributes)` makes an object of it. `inherit` is required; use `pgsn.base_class` for a class with no other parent. `attributes` is a list of the labels the class adds. A derived GSN class works with every reader:

```python
owned_goal_class = pgsn.define_class(
    name="OwnedGoal", inherit=pgsn.goal_class, attributes=["owner"])
g = pgsn.instantiate(owned_goal_class, description="Logging enabled",
                     owner="alice", support=pgsn.undeveloped)
pgsn.python_value(g.fully_eval())["owner"]   # 'alice'
```

`name` is the class's name. `python_value` reports an instance under it, as the marker key `__OwnedGoal__`. A class whose instances you want to read back therefore needs a name: `python_value` raises `ValueError` for an instance of a nameless class. The name is not inherited, and nothing compares names.

`type_of` returns the class of an object and `is_subtype` compares two classes, so a value is checked against a type like this:

```python
pgsn.python_value(pgsn.is_subtype(pgsn.type_of(g))(pgsn.goal_class).fully_eval())   # True
```

Typing is structural: `is_subtype` compares the attribute and method names the two classes declare, and `inherit` plays no part. A class of your own satisfies `solution_class` by carrying `description` and `defeaters`, and a goal satisfies it too, since it declares those and more. There is no predicate that asks which class a value belongs to. To ask where a class came from, read the inheritance chain off the object; it starts with the object's own class:

```python
pgsn.python_value(g.fully_eval(), with_inherit_chain=True)["__parent_classes__"]
# ['OwnedGoal', 'Goal', 'GSN_Node', 'BaseClass']
```

---

## Reading results

Evaluate first; these functions expect an evaluated term. Each raises `ValueError` for a term that is not evaluated or is stuck, naming the path where evaluation stopped.

### `python_value(term, with_inherit_chain=False)`

Converts a term to plain Python data — `dict`, `list`, `str`, `int`, `bool`. An object comes back as a `dict` of its attributes with a marker key `__ClassName__` whose value is `True`. An undeveloped goal, for example:

```python
{'description': 'G', 'contexts': [], 'assumptions': [], 'defeaters': [],
 'support': {'defeaters': [], 'description': '', '__Undeveloped__': True},
 '__Goal__': True}
```

Pass `with_inherit_chain=True` to also get `__parent_classes__` on every object, nested ones included.

The `ValueError` message names the path to the offending node, such as `<root>.support` or `<root>.contexts[0]`, which is the fastest way to find a stuck part. It raises as well for an object whose class has no name, there being no marker key to give it, and for a function, a class or a constant, which have no Python counterpart.

### `gsn_tree(term)`

Returns a [treelib](https://treelib.readthedocs.io/) `Tree`.

```python
tree = pgsn.gsn_tree(evaluated)
print(tree.show(stdout=False, sorting=False))   # text rendering
tree.to_json(sort=False)                        # treelib's JSON form
```

treelib sorts siblings by tag unless told otherwise, so pass `sorting=False` to `show` and `sort=False` to `to_json`: the order of a list is part of what the document says, and `python_value` reports that order. `pgsn doc` passes the same options.

### `gsn_dot(term, layout_attrs=None, label_width=40)`

Returns a `graphviz.Digraph` with GSN node shapes applied. `layout_attrs` overrides the defaults (`rankdir`, `splines`, `nodesep`, `ranksep`). Labels are wrapped at `label_width` columns; `0` leaves them on one line. Building the graph does not need Graphviz; rendering it does.

```python
dot = pgsn.gsn_dot(evaluated, {"rankdir": "LR"})
dot.render("out", format="svg", cleanup=True)
```

### `save_gsn(term, filename, image_format="png", view=False, cleanup=True, label_width=40)`

Renders straight to a file and returns `None`. `filename` is given without an extension: `save_gsn(t, "saved")` writes `saved.png`. `view=True` opens the image in a viewer, `cleanup=True` removes the intermediate DOT file, and `label_width` is as in `gsn_dot`. It needs the Graphviz programs.

### `gsn_violations(term)`

Returns the places where an evaluated structure breaks a rule of GSN v3, as a list of `GSNViolation` (`path`, `identifier`, `message`); an empty list means none. `path` uses the notation of `python_value`'s error messages, and `identifier` is the label the drawing gives the element (`G1`, `S1`). The rules are listed in [Checking against GSN v3](README-xml.md#checking-against-gsn-v3).

```python
for v in pgsn.gsn_violations(evaluated):
    print(v)   # S1 at <root>.support: a strategy relates a goal to ...
```

---

## Loading XML

The document syntax is described in [README-xml.md](README-xml.md). The root element must be `<PGSN>`.

### `load_xml(path, *, config=None, steps=None)`

```python
term = pgsn.load_xml("main.xml")
```

### `load_xml_string(xml, *, config=None, jail=None, steps=None)`

```python
term = pgsn.load_xml_string(source)
```

A document held in a string has no directory of its own, so relative imports are rejected unless you say which jail it should be considered to live in (see [Configuration and jails](#configuration-and-jails)):

```python
pgsn.load_xml_string(source, config=cfg, jail="lib")
```

Jailed imports (`/lib/...`) work either way.

### What both return

Both compile *and* evaluate, so what they return is a result, as described under [Evaluation](#evaluation): read it, do not build on it.

Both take `steps`, with the same meaning as in `fully_eval` and the same default, which is also the default of the `pgsn` command. Raise it for a document that needs more:

```python
term = pgsn.load_xml("big.xml", steps=5_000_000)
```

---

## Configuration and jails

A document can import other documents, and what it may reach is controlled by a *jail table*. A jail is a named directory root; the document names it as the first component of an absolute-looking path:

```xml
<from file="/lib/security.xml" import="secureGoal"/>
```

```python
cfg = pgsn.Config(jails={"lib": "/opt/pgsn-lib"})   # an existing directory of shared modules
term = pgsn.load_xml("main.xml", config=cfg)
```

The *confinement root* of a document is the registered jail that contains it or, if none does, the document's own directory.

- Relative imports may use `..` as long as they stay inside the confinement root.
- Symbolic links are expanded before that check.
- A module reached through a jail cannot climb back out of it.

[README-xml.md](README-xml.md#import-paths-and-jails) gives the full rules.

### `Jails(roots=None)`

An immutable table built from a mapping of name to path. Roots are validated and resolved once, at construction time: a relative root is resolved against the current directory, and a missing directory raises `JailError` immediately rather than at import time. Names may contain only ASCII letters, digits, `_` and `-`.

```python
jails = pgsn.Jails({"lib": "/opt/pgsn-lib", "proj": "./modules"})
jails.names            # ('lib', 'proj')
"lib" in jails         # True
jails.root_of("lib")   # PosixPath('/opt/pgsn-lib')
```

`root_of` raises `JailError` for a name that is not in the table. `len()` and iteration work; indexing (`jails["lib"]`) does not.

### `Config(jails=None)`

Immutable settings. Accepts a `Jails` or a plain mapping. `config.jails` reads the table back, and `config.replace(jails=...)` makes a copy with that setting changed.

### `configure(config=None, *, jails=None)` and `get_config(config=None)`

`configure` installs the default configuration used when a call omits `config`, and returns it; it may be called more than once, and `configure()` with no arguments restores the empty default. Pass either a `Config` or individual settings, not both. `get_config` returns the current default, or validates and returns the configuration you pass it.

```python
pgsn.configure(jails={"lib": "/opt/pgsn-lib"})
pgsn.load_xml("main.xml")                      # uses the default
pgsn.load_xml("other.xml", config=other_cfg)   # overrides it for this call
```

The default is a convenience, not a security boundary. What confines a document is the `Jails` table in the configuration actually used for that call. Untrusted input to PGSN is XML, and XML cannot reach these functions. PGSN does not limit the memory or the time an evaluation uses, so evaluate XML you did not write in a virtual machine or a container that limits them.

---

## Errors

| Exception | Raised by | When |
|---|---|---|
| `PGSNError` | `load_xml`, `load_xml_string` | the compiler rejects a well-formed document: an unknown element where a value is expected, an invalid or reserved name, a circular import, a rejected or missing import, a root element other than `<PGSN>` |
| `JailError` | `Jails`, `Config`, `configure`, `Jails.root_of` | a jail table that is not a mapping, an invalid jail name, a missing or non-directory root, an unknown jail name; during compilation it is converted to `PGSNError` |
| `xml.etree.ElementTree.ParseError` | `load_xml`, `load_xml_string` | the document is not well-formed XML |
| `FileNotFoundError` | `load_xml` | the document file itself does not exist |
| `LambdaInterpreterError` | `fully_eval`, `load_xml`, `load_xml_string` | the `steps` limit is reached; `e.args[0]` is `'Reduction did not terminate'` |
| `TypeError` | term construction, `Config`, `configure`, `get_config`, `load_xml`, `load_xml_string` | a Python value with no term counterpart (a `float`, `None`), or a configuration of the wrong kind |
| `ValueError` | `python_value`, `gsn_tree`, `gsn_dot`, `save_gsn`, `gsn_violations` | the result has no value; the message names the path where evaluation stopped |
| `graphviz.ExecutableNotFound` | `save_gsn`, rendering a `gsn_dot` graph | the Graphviz programs are not installed |

```python
try:
    term = pgsn.load_xml(path, config=cfg)
except pgsn.PGSNError as e:
    print(f"could not load {path}: {e}")
```
