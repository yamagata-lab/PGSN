# PGSN implementation notes

This file records how the implementation works and why it was built that way.
It is for people working on the front end (`src/pgsn/pgsn_xml.py`), the term
language and evaluator (`src/pgsn/pgsn_term.py`), the derived vocabulary
(`src/pgsn/dsl.py`) and the GSN classes (`src/pgsn/gsn.py`), and for anyone
replacing the evaluator with a virtual machine.

The language itself is documented elsewhere: README-xml.md / README-ja-xml.md
for the surface syntax, README-api.md / README-ja-api.md for the Python API.
Nothing here is part of the language: it can change without the language
changing.

## 1. Evaluation

### 1.1 Evaluation stops at an abstraction

`fully_eval` reduces a term to a **weak normal form**. Everything outside the
body of an abstraction is reduced — the elements of a list, the fields of a
record, the attributes of an object, the arguments of an application that
cannot proceed — while the body of an abstraction is left as it was written.
An abstraction is a value.

This is weaker than a normal form, in which no redex is left anywhere, and
stronger than a weak head normal form, in which a list or record is a value
whatever its contents are. It is exactly what the readers of a result need:
`python_value` converts data, and data lives outside abstractions.

Three things go wrong if evaluation reduces under an abstraction instead.

**Leftmost-outermost is not a normalising strategy here.** The normalisation
theorem holds for the pure lambda calculus, and for rewrite rules whose
patterns are left-normal. The builtins are neither: `Map` inspects its second
argument, `Cons` its second, `Fold` its third. In

    map_term (λx. …) (record "items")

the redex that lets `Map` fire is in the right argument, while the leftmost
redex is inside the abstraction on the left. A strategy that takes the
leftmost redex reduces the function body first, with the parameter unknown,
and a recursion over that parameter never ends — even though the whole term
has a normal form, reached by firing `Map` first.

**A rule that inspects an open term breaks confluence.** `Equal` used to fire
on any argument that was not an application or an abstraction, a bound
variable included, so `equal x "a"` reduced to `false` under a binder. That is
not a rewrite rule: it does not survive the substitution of `"a"` for `x`.
Evaluating `map_term (λx. if (equal x "a") "yes" "no")` over `["a"]` could
therefore reach `["yes"]` or `["no"]` depending on the order of reduction.
With evaluation stopping at abstractions, every term the evaluator reduces is
closed, and the question does not arise.

**A function held in data has no normal form.** Lists and records may hold
functions — a module is a record of templates, a class is a record of methods —
and recursion is encoded with a fixed-point combinator, which has no normal
form of its own. Insisting on a normal form for such a value means not
terminating on it.

The invariant worth keeping in mind: **a builtin reduction must be stable
under substitution**, which is to say it must not inspect a part of a term
that substitution could change. The shape of a list literal and the keys of a
record literal are such parts; a variable is not. In a weak evaluator this
holds for free, because every term reduced is closed.

### 1.2 Substitution carries a free-variable bound

Beta reduction substitutes an argument without evaluating it (call by name),
and de Bruijn indices mean each substitution that crosses an abstraction
shifts the argument. Every term therefore caches `free_bound()`: one more than
the largest de Bruijn index free in it, `0` if the term is closed. `shift` and
`subst` return "unchanged" as soon as the bound shows that nothing inside can
move.

Before this, a substitution that crossed N abstractions shifted the whole
argument N times, whether or not the variable occurred below, and the walk
followed the expanded tree rather than the shared graph. On
`examples/SolarWinds.xml` over 99% of the evaluation time was spent shifting.
The arguments substituted at the root are mostly closed, so both costs now
stop at the first node: that example went from 396 s to 0.9 s, with
byte-identical output.

### 1.3 What is still slow, and what still diverges

Call by name does not share: a name referred to from N places has its value
reduced N times. Factoring a repeated sub-term out into a `<def>` can
therefore cost more than it saves. This is a property of the evaluator, not of
the translation, and a machine with environments and closures removes it.

Recursion in `dsl.py` is built from a fixed-point combinator and a
conditional, so a recursion whose guard never becomes a boolean unfolds
forever. At the top level this happens only after an error — a record without
the key that was asked for leaves a lookup that cannot proceed, and if that
stuck term reaches `foldr` as the list being folded, the fold unfolds instead
of stopping. The `Fold` builtin, which waits for a list and otherwise does not
fire, does not have this behaviour; making `foldr` the builtin would turn such
errors into a stuck term reported at once. The step budget bounds the damage
either way.

### 1.4 Notes for a virtual machine

A machine with environments and closures removes substitution, and with it the
shifting. Krivine with updatable thunks (call by need) keeps the present
meaning exactly; CEK (call by value) is simpler but changes it, and needs three
things:

- **Recursion.** The fixed-point combinator in `dsl.py` diverges under call by
  value. Either use the call-by-value fixed-point combinator, or compile a
  recursive binding to a closure whose environment refers to itself, as
  `let rec` does.
- **Conditionals.** Under call by value, a conditional must not evaluate both
  branches, or the base case of every recursion is lost. Either the machine
  treats a saturated conditional as control flow, the way a compiler treats
  `if`, or the front end passes the branches as thunks and the chosen one is
  applied. The first keeps the language unchanged; the second keeps the machine
  free of special forms.
- **Terms that cannot proceed.** PGSN returns them rather than failing. A
  machine may instead report an error at the point where a builtin cannot
  proceed, which is more informative, but it is a change of language, not of
  implementation.

Either machine needs a readback layer: what a machine returns is a weak head
normal form, while `python_value` requires the inside of lists, records and
objects to be values as well.

Builtins are best given their arguments unevaluated and left to force what
they inspect — that is where the knowledge of which argument is needed already
lives, in `_applicable_args`. Builtins that build a term containing
applications (`Map`, a method call on an object) can return that term for the
machine to continue with, which is what `_apply_args` already does.

Two rules need a decision before they can be implemented in a machine, because
both are currently answered by comparing terms:

- **Equality.** Structural equality of data is well defined. Equality of
  functions is not definable, and comparing closures structurally is
  meaningless. Comparing them by identity is not referentially transparent:
  `let f = λx.x in equal f f` and `equal (λx.x) (λx.x)` would differ.
- **Class identity.** `is_subclass` compares classes structurally, so the same
  class reached along two paths compares unequal when its defaults have been
  reduced to different degrees. This is why `is_instance` answers `false` for
  classes carrying unevaluated defaults. A class needs an identity that does
  not depend on evaluation: a label given at compile time, derived from where
  the class is defined, is stable under both substitution and specialisation.

## 2. Names and scope

### 2.1 Builtins are ordinary bindings

A name is always compiled to a variable, and what it refers to is decided by
the enclosing bindings. The builtins are supplied by a scope that wraps each
compilation unit. Earlier the compiler substituted builtin names inline, which
made them impossible to bind: a `<def>` or a parameter named after a builtin
produced a binding nobody could refer to, silently.

Only the names a unit actually leaves free are bound. Binding the whole table
instead would mean the same thing — a name never mentioned cannot be observed —
but the builtin terms are large, every binding substitutes its value through
the body, and a chain deep enough to hold all of them exhausts the
interpreter's stack. A document that mentions dozens of builtins can still
reach that limit; real documents bind a handful.

The free names are found with `Term.free_variables()`, the same traversal that
name removal depends on, so nothing new has to be trusted.

### 2.2 Reserved names

An expression written in `expr=` or `<expr>` must mean addition whatever the
surrounding document has bound `plus` to. Each builtin is therefore bound under
two names: its own, which a document may rebind like any other, and a reserved
alias, which it may not, because names beginning with an underscore are
rejected in source documents. Desugaring goes through the reserved alias.

Which alias belongs to which builtin is an implementation detail and is
deliberately absent from the documentation, this file included. What the
language guarantees is only that a name beginning with an underscore is
reserved.

### 2.3 Names are identifiers

`<expr>` is parsed by Python's parser, so a name that Python cannot parse as
an identifier could be introduced by a `<def>` and then never referred to from
an expression. The check is `str.isidentifier()` plus the underscore rule, so
it is not restricted to ASCII: a Japanese name is a name.

### 2.4 Rebinding is shadowing

The bindings of a block fold into nested `let`s, so a later binding covers an
earlier one and nothing is overwritten. The value of a binding is read in the
scope before it, which is why `<def name="x"><var name="x"/></def>` refers to
the outer `x` and why self-reference needs `recursive="true"`.

### 2.5 The `<builtin>` tag was removed

It existed only so that an expression could reach an operator that the document
had not rebound. The reserved aliases do that, so the tag had no remaining
purpose.

## 3. Modules

A `<from>` is resolved at compile time: the file is read, compiled, and the
module — an abstraction over its parameters, returning a record of its exported
names — is embedded in the importing term, applied to the arguments given. A
module inside a module is embedded the same way, so the whole import graph
becomes one term. Each module carries a builtin scope of its own, so the
importing document's names cannot reach inside it.

Nothing is cached: the same file imported from two places is read and compiled
twice. Under call by name the module body is also evaluated once per imported
name, and once more per use of that name.

A binding-position `<from>` binds the applied module to a reserved name and
projects each imported name from it, so the module occupies one position in the
compiled term however many names are taken from it. Rebinding that reserved
name for the next `<from>` in the same block is harmless, because each
projection reads the binding nearest to it.

## 4. Conditionals and shorthands

`<if>` and `<cases>` are expanded before compilation into an application of the
conditional builtin, reached through its reserved alias, so rebinding
`if_then_else` does not change what `<if>` means.

`<else>` is required in both. A conditional without it can be written — the
term simply cannot proceed when no case matches — but a term that cannot
proceed surfaces far from the mistake, and no author means "none of these, and
nothing else either".

`expr=` and `var=` are accepted wherever a value is expected, rather than on
one element. A shorthand that works in a single place is a rule to remember; a
shorthand that works everywhere a value is expected rides on a rule that
already exists.

## 5. GSN classes

GSN v3 has no Defeater element. In the standard a defeater is an ordinary goal
or solution joined to its target by a Challenges relationship, and the
rebutting/undercutting distinction is read from the argument rather than from
the notation. A term language has no edges to carry a relationship, so PGSN
makes the challenging role a class. This is a deviation, and it is marked as
one in the code and in the READMEs.

One class is enough. A defeater that argues its case fills in `support`; one
that only raises an objection leaves it undeveloped. Separate rebuttal and
undercutter classes were tried and removed.

## 6. Measurements

`examples/SolarWinds.xml`, 3,289 nodes after compilation, no imports, many
repeated references to the same `<def>`:

| | time |
|---|---|
| before the free-variable bound | 396 s |
| after | 0.9 s |

The profile behind the first figure: `shift_or_none` accounted for 99.7% of the
time, called about 159 million times, along a path from the reduction of an
application through substitution into an abstraction. The term itself stayed
around 2,000–3,000 nodes as a graph, while the tree it would expand to peaked
at 97,000 — the shift and substitution walked the expanded tree, and repeated
it at every abstraction.

The count of reduction steps is not a measure of work: a step reduces one redex
in an application, but advances every element of a list and every field of a
record. SolarWinds completes in 487 steps at the root.

## 7. Open questions

- `PGSN.rng` has fallen behind the language: it does not model the shorthands
  expanded before compilation, and `<classdef>` is not in its vocabulary. Only
  4 of the 35 documents under `examples/` and `xml/` validate against it. A
  test that validates every example would keep it from drifting again.
- A record label can be spelled six ways (`key`, `name`, `label`, `method`, the
  text of a `<dt>`, a string value). Narrowing `name` to identifiers and `label`
  to record labels is a breaking change, so it waits for 0.1.0.
- GSN elements have no identifiers, which the standard requires, and which is
  also what keeps a Challenges relationship from being addressable.
- A defeater's `support` says why the defeater holds, not why it defeats its
  target. GSN makes the supporting side state its reasoning in a Strategy, and
  has no counterpart on the attacking side.
- `pgsn render` output quality, and an OMG-format output, are being considered
  separately.
