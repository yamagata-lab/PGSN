# PGSN implementation notes

This file explains how the implementation works and why it was built that way:
the XML front end (`src/pgsn/pgsn_xml.py`), the term language and its
evaluator (`src/pgsn/pgsn_term.py`), the derived vocabulary
(`src/pgsn/dsl.py`), and the GSN classes and their rendering
(`src/pgsn/gsn.py`).

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

An application *cannot proceed*, and is called *stuck*, when its head is a
free variable or a builtin that refuses the arguments it was given (§1.4). A
stuck application is part of the result like a value.

This is weaker than a normal form, in which no redex is left anywhere, and
stronger than a weak head normal form, in which a list or record is a value
whatever its contents are. It is exactly what the readers of a result need:
`python_value` converts data, and data lives outside abstractions.

Three things go wrong if evaluation reduces under an abstraction instead.

**Leftmost-outermost is not a normalising strategy here.** The normalisation
theorem holds for the pure lambda calculus, and for rewrite rules whose
patterns are left-normal. The builtins are neither: `Map` inspects its second
argument, and so does `Cons`. In

    map_term (λx. …) (record "items")

the redex that lets `Map` fire is in the right argument, while the leftmost
redex is inside the abstraction on the left. A strategy that takes the
leftmost redex reduces the function body first, with the parameter unknown,
and a recursion over that parameter never ends — even though the whole term
has a normal form, reached by firing `Map` first.

**A rule that inspects an open term breaks confluence.** Under a binder the
arguments of a builtin may be variables. If `equal` answered `equal x "a"` with
`false` there, the answer would not survive putting `"a"` for `x`, and
`map_term (λx. if (equal x "a") "yes" "no")` over `["a"]` could reach `["yes"]`
or `["no"]` depending on the order of evaluation. Evaluation that stays outside
abstractions never asks the question, and `equal` refuses a variable in any
case, since it compares data only (§1.5).

**A function held in data has no normal form.** Lists and records may hold
functions — a module is a record of templates, a class holds its methods and
defaults —
and recursion is encoded with a fixed-point combinator, which has no normal
form of its own. Insisting on a normal form for such a value means not
terminating on it.

The invariant worth keeping in mind: **a builtin reduction must be stable
under substitution**, which is to say it must not inspect a part of a term
that substitution could change. The shape of a list literal and the keys of a
record literal are such parts; a variable is not.

### 1.2 The machine

`fully_eval` runs a lazy Krivine machine: call by need, with environments
indexed by de Bruijn indices, a heap of cells and update markers on the stack.
A term is evaluated under an environment. An application pushes its argument
on the stack, unevaluated, as a thunk that closes over the current
environment; an abstraction takes the argument off the stack into its own
environment; a variable is looked up there. A thunk is a cell that is
evaluated the first time its value is needed and is then overwritten with that
value, so a name used in many places is evaluated once. A thunk whose value is
needed while it is being evaluated depends on itself, and the machine stops
with the same error as an exhausted step budget.

Call by need rather than call by value, because it keeps the meaning of call
by name. An argument that is never used is never evaluated, so an unused
argument that diverges or cannot proceed does no harm, and recursion is
written with the plain fixed-point combinator (`fix` in `dsl.py`). A
call-by-value machine would need another fixed-point combinator or a
recursive binding form, and would change which documents terminate.

**Where evaluation stops.** The machine itself stops at a weak head normal
form. Here and below, *data* is a term with fields: a list, a record, a class
or an object. §1.5 and §1.6 use the narrower sense the language gives the word, in
which only lists, records and base values are data. `normalize` then takes the value to the weak normal form of §1.1: it
forces, in turn, every thunk the value holds outside an abstraction — the
fields of data, and the arguments of an application that cannot proceed. The
fields of data are therefore evaluated only when the data is part of the
result: at the top, inside other data of the result, or at the head of an
application that cannot proceed, which is part of the result too. Data that
is projected is not entered, so taking one definition out of a module
evaluates that definition and none of the others (§3).

**Builtins.** A builtin applied to as many arguments as its arity is strict in
all of them. A frame on the stack holds it while the arguments are evaluated
to weak head normal forms, one after the other, and the builtin is then
applied once. Applied to fewer arguments, it is a value. Data is a builtin
too, applied to a label to project a field, but the data is not one of its
arguments, which is why projection leaves the other fields alone. A builtin
whose answer depends on values inside data — equality of lists and records, a
format string's fields, the members of a class definition — does not call the
machine again to get them. It returns a term that applies an internal builtin
to those fields, and the machine carries on with that term, so those values
are evaluated by the same rules as everything else.

**Back to a term.** What `fully_eval` returns is a term again. A thunk
that was forced is replaced by its value, and one that was never forced by
the term it was made from, with its environment put in place of its free
indices. The result is the weak normal form, which `python_value` and the GSN
conversions read.

Nothing calls the machine from inside itself, and the machine and `normalize`
are loops. Turning the state back into a term loops over thunks and recurses
only into the syntax of one term at a time, so the depth of the Python stack
does not grow with what the machine evaluates. The passes before and after
evaluation still recurse — the removal of names, `python_value`, `gsn_tree` —
and a structure deep enough for them stops with Python's `RecursionError`.

**Steps.** The budget counts two transitions of the machine: an abstraction
taking an argument off the stack, and a builtin being applied and giving a
result. Pushing an
argument, looking up a variable and updating a cell are not counted. A step
is not a unit of time, since applying a builtin costs whatever the builtin
does.

### 1.3 The conditional is lazy in its branches

`if_then_else` is not the builtin itself but a three-argument abstraction that
wraps each branch before the builtin sees it:

    λc. λt. λe. IfThenElse c (λ_. t) (λ_. e) undefined

A builtin is strict in its arguments (§1.2), so `IfThenElse` handed the
branches as they were written would evaluate both before choosing, and the
base case of every recursion would be lost. Wrapped, each branch is an
abstraction, which is already a value, so evaluating it does nothing. The
builtin selects one of the two abstractions, and the application to a dummy
argument evaluates the one that won.

When the condition never becomes a boolean or an integer (a positive integer
counts as true), the builtin refuses it and the
application cannot proceed. Its arguments are then part of the result (§1.2),
but they are abstractions, so nothing under them is evaluated (§1.1), and the
application is reported stuck where it stands.

This is what makes a missing record key visible where it occurs. A lookup that
cannot proceed reaches a fold as the list being folded; the guard `is_empty
list` cannot proceed either; and the fold stops instead of unfolding its
recursive branch until the step budget runs out. The same holds for a
recursion the author writes themselves, through `<if>` and a recursive
binding, because `<if>` expands to an application of this same term (§4.1).

`Guard` is not wrapped. It takes the body it guards as an ordinary argument,
so the body is evaluated to a weak head normal form even while the condition
is false; nothing in the standard library recurses through it.

### 1.4 A term that cannot proceed is returned

PGSN returns a term that cannot proceed rather than failing on it. Raising an
error where a builtin cannot proceed would change the language, not only the
implementation: an argument that is never used may be stuck without harm, and
so may a field nobody reads. The error belongs to readback. `python_value`,
and the conversion to GSN built on it, are where a value is required, and they
report the path at which they met something that is not one.
`tests/test_stuck.py` states the rule.

What the builtin had to say is kept. A builtin that cannot proceed raises a
`PGSNRuntimeError`; the machine catches it where it applies the builtin, leaves
the application with its arguments, and records the message under `error` in
the application's `meta_info`. Only these are caught. Any other exception is a
fault of the interpreter and escapes, and so do the step budget and Python's
recursion limit, which would stop bounding anything if they turned into stuck
terms.

A builtin that refuses an argument because the argument is itself stuck says
why it is stuck as well. The refusal carries the argument's own reason — the
`cause` it was recorded with, its `error`, or the name of the unbound variable
at its head — and the application records it under `cause`. Every stuck
application therefore knows the first reason in the chain that led to it, at
the cost of one look at the argument, and readback reports it next to the
error: a missing label whose lookup is consed onto a list of defeaters is
reported as `evaluation stopped here: PGSNTypeError: Cons: the second argument
must be a list, got App, which was stuck on PGSNKeyError: Record: there is no
label 'missing'`, rather than as the first half alone. The path reported is
that of the outer application, where evaluation came to rest, not that of the
cause.

### 1.5 Equality compares data only

`equal` compares data and declines everything else, so the evaluator never
has to decide what it is for two terms of any other kind to be the same. A
term is comparable when it is a base value — a string, an integer, a boolean,
a named constant — or a list or a record whose components are comparable in
turn; the leaves of a comparable term are therefore always base values.
Anything else leaves the application stuck, so the question is refused rather
than answered wrongly. Both sides are evaluated in full and checked to be data
before anything is answered, so the answer does not depend on the order of the
components: `equal [goal] empty` is refused, not `false`.

Structural equality of data is well defined. Equality of functions is not
definable, and comparing closures structurally is meaningless. Comparing them
by identity is not referentially transparent: `let f = λx.x in equal f f` and
`equal (λx.x) (λx.x)` would differ. Identity is the worse answer here for a
second reason: the machine holds a binding read twice in one cell, so identity
would make sharing, which is there for speed, change what a document means.
And a notation whose premise is that code is collected from several places
needs the same definition, written in two of them, to be the same value.
Structure gives that; identity cannot.

The components are compared once they have values, so `equal [plus 1 1] [2]`
is `true`. And `foldr` asks for its base case with `is_empty`, a question about
the list and not about its elements, since a list of GSN nodes cannot be
compared with `empty`.

### 1.6 Classes have no identity

There is none to decide. A structural comparison of classes would have to
compare their defaults and methods. Methods are functions, which have no
equality, and defaults hold objects (`defeater_class`'s `undeveloped`), which are
not data. Comparing the terms as they stand instead would make the answer
depend on how far evaluation had got. So a type is checked with `is_subtype`,
which compares the attribute and method *names* the two classes declare and
looks at nothing else. Names belong to a class's shape rather than its
contents, so the answer is the same however far either side has been
evaluated, and the evaluator is free to represent a class however it likes as
long as it can report those names. From XML the check is reached through
`typeOf`, which compiles to `guard(is_subtype(…))`.

Typing is therefore structural. `inherit` is not consulted: a class satisfies
every type whose labels it covers, related to it or not, so a `Goal` satisfies
`Solution` by declaring `description` and `defeaters` and more besides. What
cannot be asked is which class a value belongs to. The inheritance chain is
still readable through `python_value`, and `gsn_tree` classifies nodes by the
names it finds there, but that is a readback facility rather than a rule of
the language.

That readback is what a class's name is for. A class carries the name its
author gave it — `<class name="...">`, or `define_class(name=...)` — and an
object is reported under it. The name is not inherited, nothing in the
language compares one class's name with another's, and `is_subtype` does not
look at it, so it is a label and not an identity. An object whose class has no
name cannot be converted at all, since there is nothing to report it as: a
limit of the readback rather than a claim about the value.

A class is not data and neither is an object, and `equal` declines both, so
the structural comparison of classes cannot come back through equality: what
makes two classes the same is left open (§7) rather than decided by accident.

## 2. Names and scope

### 2.1 Builtins are ordinary bindings

A name is always compiled to a variable, and what it refers to is decided by
the enclosing bindings. The builtins are supplied by a scope that wraps each
compilation unit. A builtin's name is therefore an ordinary binding: a `<def>`
or a parameter named after a builtin shadows it, as any binding shadows an
outer one.

Only the names a unit actually leaves free are bound. Binding the whole table
instead would mean the same thing — a name never mentioned cannot be observed —
but every compiled document, and every module in it, would then carry every
builtin, in its term and in the JSON that `pgsn compile` writes. Real documents
bind a handful.

The free names are found with `Term.free_variables()`, the same traversal that
name removal depends on, so nothing new has to be trusted.

### 2.2 Reserved names

An expression written in `expr=` or `<expr>` must mean addition whatever the
surrounding document has bound `plus` to. Each builtin is therefore bound under
two names: its own, which a document may rebind like any other, and a reserved
alias, which it may not, because names beginning with an underscore are
rejected in source documents. Desugaring goes through the reserved alias.
The check that rejects such names therefore has to run on the document as
written, before desugaring has introduced any of its own (§4.2). Because
desugaring reaches builtins this way, the language needs no element for naming
a builtin past a rebinding.

Which alias belongs to which builtin is an implementation detail and is
deliberately absent from the documentation, this file included. What the
language guarantees is only that a name beginning with an underscore is
reserved.

### 2.3 Names are identifiers

`<expr>` is parsed by Python's parser, so a name that Python cannot parse as
an identifier could be introduced by a `<def>` and then never referred to from
an expression. The check is `str.isidentifier()` plus the underscore rule, so
it is not restricted to ASCII: a Japanese name is a name. Python's keywords
pass that check and still cannot be written in an expression, so a binding
named `lambda` or `if` can be referred to with `<var>` only.

### 2.4 Rebinding is shadowing

The bindings of a block fold into nested `let`s, so a later binding covers an
earlier one and nothing is overwritten. The value of a binding is read in the
scope before it, which is why `<def name="x"><var name="x"/></def>` refers to
the outer `x` and why self-reference needs `recursive="true"`.

## 3. Modules

A `<from>` is resolved at compile time: the file is read and compiled into the
module — an abstraction over its parameters, returning a record of its exported
names. The whole import graph becomes one term. Each file is compiled once,
however many times and from however many places it is imported, and the entry
document binds each module once at its head, in an order in which a module
comes after every module it imports; an import is an application of that
binding to the arguments given. Embedding the module at every import instead
makes the compiled term grow with the number of import paths, which a chain of
files each importing the next twice makes exponential in its depth, and the
step budget does not bound it, since it applies only to evaluation.

At evaluation an import is a thunk like any other binding, so it is evaluated
once however many times the imported name is used. The module evaluates to a
record, and projecting a name from it evaluates that name's definition and
none of the others (§1.2), so a module costs what the document uses of it.

Each module carries a builtin scope of its own, and a module that still has a
free name once its builtins are bound is rejected. Moving the module to the
head of the document is what makes this necessary: the compiled term still
refers to variables by name (names become de Bruijn indices only at
evaluation), so a free name in a module would be bound by whatever happens to
be in scope at the head. Rejecting it keeps the importing document's names out
of the module, so a module imported with the same arguments means the same in
every document that imports it. A `<PGSN>` document may still leave a name free;
nothing moves it, and the readback reports the name.

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
document takes and a pass over it: the surface syntax as written, where the
reserved-name check runs (§2.2); desugaring;
the deep syntax that pass leaves behind; and the compilers that read deep
syntax and build terms.

What separates the two passes is how much each is allowed to know about the
element in front of it. Desugaring knows nothing: every rule reads an
attribute and rewrites whatever element carries it. The compilers know one
element each, which is why deep syntax can still carry the attributes that
belong to a single element — `template` on `<apply>`, `key` and `of` on
`<get>`, `method` and `to` on `<send>`. Those are not shorthand, and nothing
before their own element's compiler touches them.

The order is what keeps the two kinds of rule apart. Run after an
element-specific rewrite, a generic rule would meet an element already
restructured. Rewriting `template=` inserts a child, and `var=` beside content
is an error, so the shorthand would fail on one element and work on another,
with no rule behind the difference. With every generic rule first, a shorthand
expands to exactly the longhand it stands for, on every element, and both
spellings are judged by the same compiler. Where the expansion is not
meaningful, as in `<apply template="f" var="x"/>`, the error comes from that
compiler and is the same for both spellings.

Two consequences are worth recording. An `<apply>` with no arguments is the
function itself rather than an error: application is binary, so an empty
argument list applies nothing, and `<apply template="f"/>` is another way of
writing `<var name="f"/>`. And anything that is not an `<arg>` in an argument
list is an error rather than something skipped, since skipping is what would
turn `<apply template="f" var="x"/>` into an application of `f` to nothing at
all.

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

has no text on `<div>` at all: `hello` hangs off `<def>`. A reader that asked
for `elem.text` would miss exactly the values that follow a binding, which is
where a block's value always is. Reading content in one place (`_items`), as a
sequence, removes that class of mistake: a block is its bindings and then its
last item, an application is its first item and then its arguments, and each
item is a child element or a run of text, indifferently.

The positions that depend on this are the value of `<PGSN>` and of `<div>`
after a binding, a `<div>` holding only text, the body of a `<template>` or a
`<method>` after its parameters, the function of an `<apply>` and the receiver
of a `<send>`. Text in the function position is a string, so applying it is
stuck, and the stuck term is reported where it came to rest.

### 4.4 The schema describes the surface syntax

The schema is experimental. It does not yet describe the language exactly, and
`pgsn` does not validate against it; `README-xml.md` is what defines the syntax.

`PGSN.rng` is asked about the document an author wrote, shorthands and all, so
it has to describe the surface form rather than what desugaring leaves behind.
Two decisions follow.

An attribute that stands for content is written as a *choice* against that
content, not as an addition to it. That holds for the shorthands (`var=`,
`expr=`), which stand for the whole content, and for the element-specific
attributes `template` on `<apply>`, `of` on `<get>` and `to` on `<send>`, each
of which stands for one item: the function or the receiver. Declared as an
optional attribute beside a required value, such an attribute would admit a
document that gives the item twice and reject none.

`as` names an element to wrap the content in, so what follows it is that
element's content model. Each element's content is therefore a named pattern
that the element and `as` both refer to. What RELAX NG cannot say is which
element `as` named, because a schema cannot branch on an attribute's value. So
the `as` branch accepts the content model of any element. The content is
checked against whichever model it matches, not the one `as` names: a document
may write a `<dl>`'s content under `as="ol"` and the schema will not object,
though the compiler will.

Validating is worth the trouble because it catches what evaluating cannot. The
compiler ignores a child element it does not recognise, so a `<Defeater>`
spelled `<Rebuttal>` yields a document with one defeater fewer and no
complaint, while the schema rejects it. `tests/test_schema.py` runs every file
under `examples/` through the validator, and is the only thing that keeps the
schema in step with the compiler.

### 4.5 A record label is spelled `key`

A record label is a string in a namespace of its own. Where a label is written
as an attribute it is spelled `key`: `<dt key=>` builds an entry and
`<get key=>` reads it back, so a label is read with the word it was written
with, and one concept has one spelling to remember. A `<dt>` may also give its
label as text. `name` has the other job, which is to name a thing:
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

The compiler drops attributes it does not know without a word, so a misspelt
label attribute (`<get label="k">`) is not reported as such: the element fails
for want of a `key`. That is the same gap §7 describes for an unrecognised
child element, and validating before compiling closes both.

### 4.6 A list is ordered, and there is one kind of it

Sub-goals, contexts, assumptions and defeaters are `List` terms, and the order
of their elements is part of what a document says.

The GSN Community Standard does not settle it. It defines the node types and
the SupportedBy and InContextOf relations, and assigns no meaning to the order
of siblings; ordering there is a matter of layout. So the question is PGSN's to
answer, not a point of conformance.

The answer is that the order is part of what the document says. It is the
reading that costs nothing — a document that does not care about the order of
its sub-goals loses nothing by having it preserved — while the other reading
costs the author the ability to say "these hazards in this order", which no
notation gives back.

`python_value` reports the elements in document order. The renderers would
not unless asked: `gsn_tree` builds a `treelib.Tree`, and treelib sorts
siblings by tag unless told otherwise, which would reach `tree.show`
(`pgsn doc`), `tree.to_json` (`pgsn doc -d json`) and the `expand_tree` walk in
`gsn_dot` (`pgsn render`). Every renderer therefore asks treelib not to sort.
The option is passed at the call, not hidden in a subclass of `Tree`: `gsn_tree`
returns treelib's own tree, and a caller who renders it passes `sorting=False`
(or `sort=False` to `to_json`) the way `pgsn doc` does. Wrapping the library to
change its defaults would make our tree something the reader has to learn
before trusting treelib's documentation about it.

Within a node, the children a renderer reports are the node's attributes, whose
order is the order the record was built in rather than anything sorted. The
constructors in `gsn.py` write them in one order for that reason: what the node
is stated in the context of, then what challenges it, then what it rests on.

There is one list element, `<ol>`, and it is ordered. A document that writes
`<ul>`, or `as="ul"`, is told the expression is unknown. An unordered list
compiling to the same `List` would let a document state a distinction the
compiler discards, and authors would come to depend on the order it kept, so a
set added later would silently reorder their documents. A set needs more than
a tag: an equality on its elements, which data has and functions and nodes do
not (§1.5), and a canonical order to render it in. If one is wanted it gets its
own element and its own term type, so that no existing document changes
meaning under it.

## 5. GSN classes

GSN v3 has no Defeater element. In the standard a defeater is an ordinary goal
or solution joined to its target by a Challenges relationship, and the
rebutting/undercutting distinction is read from the argument rather than from
the notation. A term language has no edges to carry a relationship, so PGSN
makes the challenging role a class. This is a deviation, and it is marked as
one in the code and in the READMEs.

One class is enough. A defeater that argues its case fills in `support`; one
that only raises an objection leaves it undeveloped.

A Context or an Assumption attaches to a Goal or a Strategy in the standard,
and to nothing else, so `goal_class` and `strategy_class` declare `contexts`
and `assumptions` and `solution_class` does not. `examples/Figure6` is the
standard's Figure 6, where an assumption hangs off the strategy. A Context or
an Assumption written inside a `<Solution>` has nowhere to go, and the compiler
drops it without a word.

### 5.1 The output follows GSN v3 where the language does not

The language is not yet shaped after the GSN metamodel, and changing it is
left to a later version. What the evaluated structure is drawn and checked as
follows the standard already, so that a reader of the output meets GSN v3 and
not PGSN's encoding of it.

**Undeveloped.** `undeveloped` is a value, written where a goal's support or a
strategy's sub-goal would go. The drawing does not show it as an element of its
own: it is absorbed into the element that holds it, which gets the standard's
◇ under its box. A defeater left without support gets no ◇, since the standard
gives the decorator to goals and strategies only.

**Identifiers.** The standard requires every element to have one. The drawing
heads each box with an identifier made from its type and its position among the
elements of that type, in document order: G, S, Sn, C, A, and CG for a
defeater, after the standard's own examples of a challenging goal. These are
labels of the drawing, not names in the document. Nothing in a document refers
to an element: an element is a value, and the language gives values no
identity (§1.6, §7).

**Relationships.** SupportedBy has a solid arrowhead, InContextOf a hollow one,
and a defeater's Challenges a dashed line with an open arrowhead, pointing at
what it challenges. An Assumption is marked with an A. A defeater is drawn as a
dashed hexagon, which is PGSN's own shape: the standard draws a challenging
element as an ordinary goal or solution.

**Validity.** A document can put any value in any position, so a structure can
evaluate and still not be one the standard allows: text where a goal's support
belongs, a strategy with no sub-goal, a goal where a defeater belongs.
`gsn_violations` checks the evaluated structure against the rules of the
standard that a document can break, walking it in the order `gsn_tree` does, so
that the identifiers it reports are the ones the drawing shows. The check runs
on the result, not on the document, because which value lands in which
position is known only after evaluation. `pgsn doc` and `pgsn render` print a
breach as a warning and go on; under `--strict` they stop and write nothing.

## 6. Measurements

The twenty-four entry points under `examples/` are compiled, evaluated and
converted with `python_value` in about 0.54 s altogether. The slowest five are the
four EU AI Act cases, whose imports reach three modules deep, and SolarWinds,
the largest document without imports:

| document | time | steps |
|---|---|---|
| `EU_AI_ACT/case_proctoring.xml` | 0.11 s | 8,459 |
| `EU_AI_ACT/case_recruitment_ai.xml` | 0.07 s | 4,521 |
| `EU_AI_ACT/case_medical_ai.xml` | 0.07 s | 4,429 |
| `EU_AI_ACT/case_gpai_system.xml` | 0.06 s | 4,388 |
| `SolarWinds.xml` | 0.05 s | 1,933 |

The steps are those of §1.2, well inside the default budget of a million.
Sharing is what keeps a module cheap: a document that uses an imported name
fifty times takes as many steps as one that uses it once, and a definition of
the module that the document does not use takes none.

`tests/test_examples.py` evaluates every entry point without fixing what they
produce, since they are material rather than specification. The four EU AI Act
cases are marked `slow` and run only under `pytest -m slow`.

## 7. Open questions

- Typing is structural, so a type is satisfied by any class that carries its
  labels, and a `Goal` satisfies `Solution`. Whether a nominal check is wanted
  as well — "this node is a Goal, not merely goal-shaped" — is open. A class
  carries the name its author gave it (§1.6), but that name is a label for
  readback: nothing in the language compares one with another, and names given
  in documents written apart from each other are not unique. The inheritance
  chain holds the real answer, and only the readback can see it. Behind the
  check is a larger question that is not yet formulated: what it is for two
  definitions collected from different places to be the same, and how the
  provenance of either is established.
- A GSN element's compiler picks out the children it knows by tag, so a child
  it does not know is neither read nor refused. `PGSN.rng` rejects an
  unrecognised child (§4.4), but validating is a separate step that nobody is
  obliged to take. Validating before compiling would close the gap where it
  opens, and would stop the tag sets the compilers filter on from being the
  only thing that decides what a document may contain. It is also why
  `"builtin"` stays in `_VALUE_TAGS` although there is no `<builtin>` element:
  a GSN element with neither leading text nor a `<description>` takes a lone
  value child as its description, and listing the tag there makes `<builtin>`
  in that position an unknown expression rather than nothing. In an element
  that has a description it is dropped like any other unknown child.
- GSN elements have no identifiers a document can use. The standard requires
  them, and the drawing supplies them (§5.1), but a drawing's labels cannot
  be referred to, and that is also what keeps a Challenges relationship from
  being addressable.
- A step of the budget has no bound on its cost (§1.2). An integer squared
  over and over, or a format string that doubles its input, reaches gigabytes
  within a few hundred steps, so the budget bounds how long a document runs
  only for documents that do not grow their values that way.
- A defeater's `support` says why the defeater holds, not why it defeats its
  target. GSN makes the supporting side state its reasoning in a Strategy, and
  has no counterpart on the attacking side.
- `pgsn render` output quality, and an OMG-format output, are being considered
  separately.
