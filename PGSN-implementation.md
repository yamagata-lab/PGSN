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
closed, and the question does not arise. Equality has since been narrowed to
data (§1.5), which refuses a variable for a second reason.

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

### 1.3 The conditional is lazy in its branches

`if_then_else` is not the builtin itself but a three-argument abstraction that
wraps each branch before the builtin sees it:

    λc. λt. λe. IfThenElse c (λ_. t) (λ_. e) undefined

Beta reduction substitutes an argument without evaluating it, so the branches
reach the builtin as they were written. The builtin selects one of the two
abstractions, and the application to a dummy argument forces the one that won.

The wrapping changes nothing when the condition is well behaved. A builtin is
tried before any argument is reduced, so a condition that eventually becomes a
boolean already short-circuits, and always did. What changes is the case where
the condition can never become a boolean. The builtin then never fires, the
evaluator falls through to reducing the arguments of a head it cannot apply,
and both branches are reduced — a branch holding a recursive call unfolds until
the step budget runs out. Under an abstraction there is nothing to reduce
(§1.1), so instead the application stays as it stands and is reported stuck.

This is what makes a missing record key visible where it occurs. A lookup that
cannot proceed reaches a fold as the list being folded; the guard `is_empty
list` cannot proceed either; and the fold now stops. The same holds for a
recursion the author writes themselves, through `<if>` and a recursive binding,
because `<if>` expands to an application of this same term (§4.1). Measured on
such a recursion, guarded by a comparison against a stuck term: 86 s to exhaust
the Python stack, reporting only that the stack was exhausted, against 0.2 s to
a stuck term reported at `<root>.description`.

`Guard` is left as it is. It takes the body it guards as an ordinary argument
and is meant not to fire while its condition is false, so the body is reduced
in exactly the cases the builtin is there to hold back; nothing in the standard
library recurses through it.

A call-by-value machine needs this same wrapping in order not to evaluate both
branches (§1.5), which is why it is worth having before such a machine exists.

### 1.4 What is still slow, and what still diverges

Call by name does not share: a name referred to from N places has its value
reduced N times. Factoring a repeated sub-term out into a `<def>` can
therefore cost more than it saves. This is a property of the evaluator, not of
the translation, and a machine with environments and closures removes it.

A recursion that genuinely does not terminate still does not terminate, and the
step budget is what bounds it. What no longer happens is a recursion running
away over data that is merely stuck. The remaining cost of a stuck term is that
it is found during readback rather than where it arose: `python_value` reports
the path at which it met something that is not a value, which is where the term
came to rest, not where the key was missing.

### 1.5 Notes for a virtual machine

A machine with environments and closures removes substitution, and with it the
shifting. Krivine with updatable thunks (call by need) keeps the present
meaning exactly; CEK (call by value) is simpler but changes it, and needs three
things:

- **Recursion.** The fixed-point combinator in `dsl.py` diverges under call by
  value. Either use the call-by-value fixed-point combinator, or compile a
  recursive binding to a closure whose environment refers to itself, as
  `let rec` does.
- **Conditionals.** Under call by value, a conditional must not evaluate both
  branches, or the base case of every recursion is lost. This one is already
  settled: `if_then_else` wraps its branches and applies the one that wins
  (§1.3), so a machine that evaluates every argument evaluates neither branch,
  and needs no special form for `if`. The price is a closure and an application
  per conditional.
- **Terms that cannot proceed.** PGSN returns them rather than failing, and a
  machine does the same. Reporting an error where a builtin cannot proceed
  would be a change of language, not of implementation. The error belongs to
  readback: `python_value`, and the conversion to GSN built on it, are where a
  value is required, and they report the path at which they met something that
  is not one. `tests/test_stuck.py` states the rule.

Either machine needs a readback layer: what a machine returns is a weak head
normal form, while `python_value` requires the inside of lists, records and
objects to be values as well.

Builtins are best given their arguments unevaluated and left to force what
they inspect — that is where the knowledge of which argument is needed already
lives, in `_applicable_args`. Builtins that build a term containing
applications (`Map`, a method call on an object) can return that term for the
machine to continue with, which is what `_apply_args` already does.

Two rules were answered by comparing terms. Both have since been settled, so
neither leaves a machine to decide what it is for two terms to be the same:

- **Equality.** `equal` compares data and declines everything else. A term is
  comparable when it is a base value — a string, an integer, a boolean, a
  named constant — or a list or a record whose components are comparable in
  turn; the leaves of a comparable term are therefore always base values.
  Anything else leaves the application stuck, so the question is refused
  rather than answered wrongly.

  Structural equality of data is well defined. Equality of functions is not
  definable, and comparing closures structurally is meaningless. Comparing
  them by identity is not referentially transparent: `let f = λx.x in equal f
  f` and `equal (λx.x) (λx.x)` would differ. Identity is the worse answer here
  for a second reason: the evaluator does not share, so a binding read twice
  is reduced twice and would carry two identities, where a machine with
  environments and closures would carry one — the sharing a machine adds for
  speed would change what programs mean. And a notation whose premise is that
  code is collected from several places needs the same definition, written in
  two of them, to be the same value. Structure gives that; identity cannot.

  Two consequences were visible in the code. `equal [plus 1 1] [2]` answered
  `false`, because the elements were compared as terms before they had values;
  it waits now, and answers `true`. And `foldr` asked for its base case by
  comparing the list with `empty`, which a list of GSN nodes cannot answer, so
  emptiness is asked directly with `is_empty` — a question about the list and
  not about its elements.
- **Class identity.** A machine does not need one. `is_subclass` walked the
  inheritance chain comparing classes with structural equality, so the same
  class reached along two paths compared unequal once its defaults had been
  reduced to different degrees. `is_instance`, defined in terms of it,
  therefore answered `false` for every class whose defaults hold an
  unevaluated term — `goal_class` among them, through its `undeveloped`
  default. From XML the check was reached through the `instanceOf` attribute,
  which compiled to `guard(is_instance(…))`, so a document that used it on a
  `<Goal>` did not reduce and said nothing about why.

  Both were replaced by `is_subtype`, which compares the attribute and method
  *names* the two classes declare and looks at nothing else. Names belong to
  a class's shape rather than its contents, so the answer is the same however
  far either side has been reduced, and a machine is free to represent a
  class however it likes as long as it can report those names.

  This made typing structural, which is a change of language and not only of
  implementation. `inherit` is not consulted: a class satisfies every type
  whose labels it covers, related to it or not, so a `Goal` satisfies
  `Evidence` by declaring `description` and `defeaters` and more besides.
  What can no longer be asked is which class a value belongs to. The
  inheritance chain is still readable through `python_value`, and `gsn_tree`
  classifies nodes by the names it finds there, but that is a readback
  facility rather than a rule of the language.

  That readback is what a class's name is for. A class carries the name its
  author gave it — `<class name="...">`, or `define_class(name=...)` — and an
  object is reported under it. The name is not inherited, nothing in the
  language compares one class's name with another's, and `is_subtype` does not
  look at it, so it is a label and not an identity. An object whose class has
  no name cannot be converted at all, since there is nothing to report it as:
  a limit of the readback rather than a claim about the value.

  The caveat this left is closed. `equal` accepted classes, since it declined
  only applications and abstractions, so the comparison that was removed was
  one builtin away from returning. A class is not data and neither is an
  object, and `equal` declines both: what makes two classes the same is left
  open (§7) rather than decided here by accident.

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
The check that rejects such names therefore has to run on the document as
written, before desugaring has introduced any of its own (§4.2).

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

## 4. Surface syntax

### 4.1 Conditionals

`<if>` and `<cases>` are expanded before compilation into an application of
`if_then_else`, reached through its reserved alias, so rebinding
`if_then_else` does not change what `<if>` means. That term thunks its own
branches (§1.3), so a conditional written in XML is lazy in its branches
without the expansion having to arrange anything.

`<else>` is required in both. A conditional without it can be written — the
term simply cannot proceed when no case matches — but a term that cannot
proceed surfaces far from the mistake, and no author means "none of these, and
nothing else either".

### 4.2 Shorthands

`expr=` and `var=` are accepted wherever a value is expected, rather than on
one element. A shorthand that works in a single place is a rule to remember; a
shorthand that works everywhere a value is expected rides on a rule that
already exists.

That promise is kept by the order of the passes, not only by the rules. A
document becomes a term in four stages, alternating between a form the
document takes and a pass over it: the surface syntax as written; desugaring;
the deep syntax that pass leaves behind; and the compilers that read deep
syntax and build terms.

What separates the two passes is how much each is allowed to know about the
element in front of it. Desugaring knows nothing: every rule reads an
attribute and rewrites whatever element carries it. The compilers know one
element each, which is why deep syntax can still carry the attributes that
belong to a single element — `template` on `<apply>`, `key` and `of` on
`<get>`, `method` and `to` on `<send>`. Those are not shorthand, and nothing
before their own element's compiler touches them.

The two kinds of rule used to be interleaved: expand `expr=`, rewrite the
element-specific attributes, expand `var=`. The generic rules then met
elements the specific ones had already restructured, and the result was an
asymmetry with no rule behind it. `<apply template="f" var="x"/>` was
rejected, because rewriting `template` had already inserted a child and the
`var` rule refused to expand beside one, while `<get label="k" var="r"/>` —
`label` being the spelling of what is now `key` —
the same combination, on an element whose rewriting happened to rename an
attribute rather than add a child — quietly worked. Ordering the passes
removes the question rather than answering it: a shorthand now expands to
exactly the longhand it stands for, on every element, and the two spellings
are judged by the same compiler afterwards. Where that expansion is not
meaningful, the error comes from the element's compiler and says the same
thing for both spellings.

Two consequences are worth recording. An `<apply>` with no arguments is the
function itself rather than an error: application is binary, so an empty
argument list applies nothing, and `<apply template="f"/>` is another way of
writing `<var name="f"/>`. And anything that is not an `<arg>` in an argument
list is now an error where it used to be skipped — skipping is precisely what
would turn `<apply template="f" var="x"/>` into an application of `f` to
nothing at all.

### 4.3 Content is a sequence of items

Bare text is a string, and that holds wherever a value is expected. Making it
hold everywhere took a content model rather than a rule: the content of an
element is a sequence of items in document order — each child element, and
each run of text between them.

The sequence is what matters, because a value written after a binding is not
the text of the element. XML puts it in the *tail* of the binding, so

```xml
<div><def name="x"><num>1</num></def>hello</div>
```

has no text on `<div>` at all: `hello` hangs off `<def>`. Every reader that
asked for `elem.text` therefore missed exactly the values that follow a
binding — which is where a block's value always is. Reading content in one
place, as a sequence, removes the class of mistake rather than its instances:
a block is its bindings and then its last item, an application is its first
item and then its arguments, and each item is a child element or a run of
text, indifferently.

The positions this settled were the value of `<PGSN>` and of `<div>` after a
binding, a `<div>` holding nothing but text, the body of a `<template>` or a
`<method>` after its parameters, and the function of an `<apply>` and the
receiver of a `<send>`. Applying a string is stuck rather than useful, but
the document now means what it says, and the stuck term is reported with the
position it came to rest at.

### 4.4 The schema describes the surface syntax

`PGSN.rng` is asked about the document an author wrote, shorthands and all, so
it has to describe the surface form rather than what desugaring leaves behind.
Two decisions follow.

A shorthand attribute stands in place of the content it abbreviates, so it is
written as a *choice* against that content rather than as an addition to it.
The schema used to declare `template` on `<apply>`, `of` on `<get>` and `to`
on `<send>` as optional attributes beside a required value — which is the
mistake §4.2 describes, made a second time in another notation.

`as` names an element to wrap the content in, so what follows it is that
element's content model. Each element's content is therefore a named pattern
that the element and `as` both refer to. What RELAX NG cannot say is which
element `as` named, because a schema cannot branch on an attribute's value. So
the `as` branch is the choice of every content model, and each is still
checked internally: a document may write a `<dl>`'s content under `as="ol"`
and the schema will not object, though the compiler will.

Validating is worth the trouble because it catches what evaluating cannot. The
compiler ignores a child element it does not recognise, so a `<Defeater>`
spelled `<Rebuttal>` yields a document with one defeater fewer and no
complaint, while the schema rejects it. `tests/test_schema.py` runs every
example through the validator for that reason, and to keep the schema from
drifting again: it had drifted badly, four of the twenty-six documents
validating when the test was written.

### 4.5 A record label is spelled `key`

A record label is a string in a namespace of its own, and it used to be written
differently in almost every element that takes one: `key` on `<dt>`, `label` on
`<get>`, `name` on `<attribute>`, `method` on `<send>`, the text of a `<dt>`, or
a string value passed to the record itself. Six spellings for one concept leave
no rule to remember, so the wrong guess is the normal case — and the wrong guess
used to fail without naming the attribute it was about.

`key` is now the spelling wherever a record label is written as such: `<dt key=>`
builds an entry and `<get key=>` reads it back, so a label is read with the word
it was written with. `name` keeps the other job, which is to name a thing:
bindings (`<def>`, `<param>`, `<var>`, `<arg>`), the class's own name, and the
members a class declares (`<attribute name=>`, `<method name=>`). A declaration
names a member the way a lambda names a parameter; the selection that reads it
back indexes a record, and indexes carry `key`. `method` stays on `<send>`
because `<send>` is not selection: it is selection followed by application, and
`<send method="m" to="obj"><arg>…</arg></send>` is the same term as
`<apply><get key="m" of="obj"/><arg>…</arg></apply>`.

Selecting a field remains an application of the record to a string, so a
computed label needs nothing new — it is written as that application. The
attribute holds a literal, which is why it is an attribute and not a value
position.

The old spelling is not carried as an error. While the language is young
enough to rename things, a document written against the old one is told
nothing about the rename: `label` is an unknown attribute, unknown attributes
are dropped in silence, and the element then fails for want of a `key`. That
silence is the same gap §7 describes for an unrecognised child element, and
validating before compiling is what closes both.

### 4.6 A list is ordered, and there is one kind of it

Sub-goals, contexts, assumptions and defeaters are `List` terms, and nothing in
the language used to say whether the order of their elements carried meaning.
The implementation answered the question twice, differently. `python_value`
returned the elements in the order the document gave them, while every
rendering path sorted them alphabetically: `gsn_tree` builds a `treelib.Tree`,
and treelib sorts siblings by tag unless told otherwise. That reached
`tree.show` (`pgsn doc`), `tree.to_json` (`pgsn doc -d json`) and the
`expand_tree` walk in `gsn_dot` (`pgsn render`), so all three command-line
outputs reordered what the Python API did not.

The GSN Community Standard does not settle it. It defines the node types and
the SupportedBy and InContextOf relations, and assigns no meaning to the order
of siblings; ordering there is a matter of layout. So the question is PGSN's to
answer, not a point of conformance.

The answer is that the order is part of what the document says. It is the
reading that costs nothing — a document that does not care about the order of
its sub-goals loses nothing by having it preserved — while the other reading
costs the author the ability to say "these hazards in this order", which no
notation gives back. Every renderer therefore asks treelib not to sort. The
option is passed at the call, not hidden in a subclass of `Tree`: `gsn_tree`
returns treelib's own tree, and a caller who renders it passes `sorting=False`
(or `sort=False` to `to_json`) the way `pgsn doc` does. Wrapping the library to
change its defaults would make our tree something the reader has to learn
before trusting treelib's documentation about it.

Within a node, the children a renderer reports are the node's attributes, whose
order is the order the record was built in rather than anything sorted. The
constructors in `gsn.py` write them in one order for that reason: what the node
is stated in the context of, then what challenges it, then what it rests on.

`ul` is gone. It compiled to the same `List` as `ol` while standing for a set,
and `README-xml.md` told authors to use `ol` "when order matters" — so a
document could express the distinction and the compiler would discard it. Now
there is one list element and it is ordered. The tag is simply not in the
language: a document that writes it is told that the expression is unknown,
which is what the language is young enough for. `as="ul"` fails with it, since
the shorthand expands to the element before anything reads it.

Keeping `ul` as an alias would have been the cheaper change and the worse one.
Authors would have come to depend on the order it preserved — every example
that passes sub-goals through a list was written with it — and a set added
later would silently reorder their documents. A set also needs more than a tag:
an equality on its elements, which data has and functions and nodes do not
(§1.5), and a canonical order to render it in. If one is ever wanted it gets its own element
and its own term type, so that no existing document changes meaning under it.

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

A Context or an Assumption attaches to a Goal or a Strategy in the standard,
and to nothing else. Only `goal_class` declared them, so the ones written on a
strategy were read and then dropped, silently: `examples/Figure6` is the
standard's Figure 6, where an assumption hangs off the strategy, and it was
losing that assumption and a context besides. `strategy_class` declares them
now. `evidence_class` does not, because the standard attaches nothing to a
Solution, and `PGSN.rng` rejects one written there — the compiler has nowhere
to put it and would say nothing.

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

Thunked branches (§1.3) change no output and cost no measurable time: every
entry point under `examples/` produced a byte-identical document before and
after, and the slowest of them, SolarWinds, took 0.84 s against 0.85 s. What
they change is the stuck case. A fold over a term that cannot proceed ran for
81 s before exhausting the Python stack; it now stops at once.

Where the examples stand now: the nineteen entry points under `examples/`
evaluate in 0.96 s altogether, 0.70 s of which is SolarWinds. The test suite
evaluates every one of them (`tests/test_examples.py`) without fixing what
they produce, since they are material rather than specification.

## 7. Open questions

- Typing is structural, so a type is satisfied by any class that carries its
  labels, and a `Goal` satisfies `Evidence`. Whether a nominal check is wanted
  as well — "this node is a Goal, not merely goal-shaped" — is open. A class
  carries the name its author gave it (§1.5), but that name is a label for
  readback: nothing in the language compares one with another, and names given
  in documents written apart from each other are not unique. The inheritance
  chain holds the real answer, and only the readback can see it. Behind the
  check is a larger question that is not yet formulated: what it is for two
  definitions collected from different places to be the same, and how the
  provenance of either is established.
- A GSN element's compiler picks out the children it knows by tag, so a child
  it does not know is neither read nor refused: a `<Goal>` whose `<Defeater>`
  is spelled `<Rebuttal>` compiles to a goal with one defeater fewer and says
  nothing. `PGSN.rng` rejects it (§4.4), but validating is a separate step that
  nobody is obliged to take. Validating before compiling would close the gap
  where it opens, and would stop the tag sets the compilers filter on from
  being the only thing that decides what a document may contain. It is also
  what keeps `"builtin"` in `_VALUE_TAGS`: the element was removed and the
  entry is stale, but it is the only reason `<builtin>` inside a GSN element is
  an error rather than nothing at all.
- GSN elements have no identifiers, which the standard requires, and which is
  also what keeps a Challenges relationship from being addressable.
- A defeater's `support` says why the defeater holds, not why it defeats its
  target. GSN makes the supporting side state its reasoning in a Strategy, and
  has no counterpart on the attacking side.
- `pgsn render` output quality, and an OMG-format output, are being considered
  separately.
