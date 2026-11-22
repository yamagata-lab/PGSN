# PGSN implementation notes

This document records why the PGSN processor is implemented as it is. It is
written for researchers who want the reasoning behind the design and for
maintainers who will change the code. It is neither the language specification
nor a user guide: README-xml.md / README-ja-xml.md define the XML syntax and
README-api.md / README-ja-api.md the Python API. Where a section gives the
reason for a language rule, the rule itself is defined in the README. Nothing
here is part of the language: it can change without the language changing.
Known issues and open problems are listed in known_issues.md.

The code it describes is the XML front end (`src/pgsn/pgsn_xml.py`), the term
language and its evaluator (`src/pgsn/pgsn_term.py`), the derived vocabulary
(`src/pgsn/dsl.py`), the GSN classes and their rendering (`src/pgsn/gsn.py`),
and the command line (`src/pgsn/cli.py`). Import confinement (jails,
`src/pgsn/jail.py` and `src/pgsn/config.py`) is specified in README-xml.md and
is not discussed here.

**From document to result.** A document goes through these stages:

1. The XML as written, the *surface syntax*, is checked for reserved names (§3.2).
2. *Desugaring* expands the shorthands (`var=`, `expr=`, `as=`, `<if>`, `<cases>`).
3. What is left, the *deep syntax*, is compiled element by element into a term.
   The term is wrapped in a scope that binds the predefined names it uses, and every
   imported module is bound once at the head of the entry point (§4).
4. Names are replaced by de Bruijn indices, and the machine evaluates the term
   to a weak normal form, which it returns as a term (§1).
5. *Readback* converts that term: `python_value` to Python values, and
   `gsn_tree`, `gsn_dot` and `gsn_violations`, built on it, to GSN.

**Terms used below.**

1. A *builtin* is a primitive operation of the machine, such as `Map`, `Cons`
   or `IfThenElse`: it has an arity and is applied once its arguments are
   evaluated (§1.4). A *predefined name* is a name the processor binds for
   every document, such as `map_term`, `if_then_else`, `fold`, `goal` or `fix`.
   Some predefined names denote a builtin; others denote a term built from
   builtins. The READMEs call every predefined name a builtin; this document
   keeps the two apart.
2. *Data* is a base value — a string, an integer, a boolean, a named constant —
   or a list or a record whose components are data. It is what `equal`
   compares (§2.1).
3. A *term with fields* is a list, a record, a class or an object: what the
   class `Data` in `pgsn_term.py` covers.
4. An *entry point* is a file whose root element is `<PGSN>`; a file whose root
   is `<PGSNModule>` is a module and is only imported.
5. *GSN v3* is the GSN Community Standard, Version 3 (SCSC-141C).

In the examples, `λx. t` is an abstraction, `f a b` applies `f` to `a` and
then `b`, and `[a, b]` is a list.

## 1. Evaluation

### 1.1 Evaluation stops at an abstraction

`fully_eval` reduces a term to a **weak normal form**. Everything outside the
body of an abstraction is reduced — the elements of a list, the fields of a
record, the attributes of an object, the arguments of an application that
cannot proceed — while the body of an abstraction is left as it was written.
An abstraction is a value.

An application *cannot proceed*, and is called *stuck*, when its head is a
free variable or a builtin that refuses the arguments it was given (§1.7). A
stuck application is part of the result like a value.

This is weaker than a normal form, in which no redex is left anywhere, and
stronger than a weak head normal form, in which a list or record is a value
whatever its contents are. It is exactly what the functions that read a result
need: `python_value` converts terms with fields, and their fields live outside
abstractions.

Three things go wrong if evaluation reduces under an abstraction instead.

**Leftmost-outermost is not a normalizing strategy here.** The normalization
theorem holds for the pure lambda calculus, and for rewrite rules whose
patterns are left-normal. The builtins are neither: `Map` inspects its second
argument, and so does `Cons`. In

    map_term (λx. foldr f a x) (record "items")

the redex that lets `Map` fire is in the right argument, while the leftmost
redex is inside the abstraction on the left. A strategy that takes the
leftmost redex reduces the function body first, with the parameter unknown.
`foldr` recurses over its list through `fix`, so with `x` unknown that
recursion never ends — even though the whole term has a normal form, reached
by firing `Map` first.

**A rule that inspects an open term breaks confluence.** Under a binder the
arguments of a builtin may be variables. If `equal` answered `equal x "a"` with
`false` there, the answer would not survive putting `"a"` for `x`, and
`map_term (λx. if (equal x "a") "yes" "no")` over `["a"]` could reach `["yes"]`
or `["no"]` depending on the order of evaluation. Evaluation that stays outside
abstractions never asks the question, and `equal` refuses a variable in any
case, since it compares data only (§2.1).

**A function held in a term with fields has no normal form.** Lists and
records may hold functions — a module is a record of templates, a class holds
its methods and defaults — and recursion is encoded with a fixed-point
combinator, which has no normal form of its own. Insisting on a normal form for
such a value means not terminating on it.

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

### 1.3 Where evaluation stops

The machine itself stops at a weak head normal form. The machine's `normalize` then takes the
value to the weak normal form of §1.1: it forces, in turn, every thunk the
value holds outside an abstraction — the fields of a term with fields, and the
arguments of an application that cannot proceed. The fields are therefore
evaluated only when the term that holds them is part of the result: at the
top, inside another term with fields of the result, or at the head of an
application that cannot proceed, which is part of the result too. A term with
fields that is projected is not entered, so taking one definition out of a
module evaluates that definition and none of the others (§4).

### 1.4 Builtins are strict

A builtin applied to as many arguments as its arity is strict in all of them.
A frame on the stack holds it while the arguments are evaluated to weak head
normal forms, one after the other, and the builtin is then applied once.
Applied to fewer arguments, it is a value.

A term with fields is applied like a builtin: to a label or an index, to
project a field. The term itself is not one of the arguments, which is why
projection leaves the other fields alone.

A builtin whose answer depends on values inside a term with fields — equality
of lists and records, a format string's fields, the members of a class
definition — does not call the machine again to get them. It returns a term
that applies an internal builtin to those fields, and the machine carries on
with that term, so those values are evaluated by the same rules as everything
else.

### 1.5 Back to a term

What `fully_eval` returns is a term again. A thunk that was forced is replaced
by its value; one that was never forced is replaced by the term it was made
from, with its environment substituted for its free indices. The result is the
weak normal form, which readback reads. (The method that does this is
`_Machine.readback`; it is not what this document calls readback.)

Nothing calls the machine from inside itself, and the machine and `normalize`
are loops. Turning the state back into a term loops over thunks and recurses
only into the syntax of one term at a time, so the depth of the Python stack
does not grow with what the machine evaluates.

### 1.6 Steps

The budget counts two transitions of the machine: an abstraction taking an
argument off the stack, and a builtin being applied and giving a result.
Pushing an argument, looking up a variable and updating a cell are not
counted. A step is therefore not a unit of time, since applying a builtin
costs whatever the builtin does.

### 1.7 A term that cannot proceed is returned

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
the application's `meta_info`. Only `PGSNRuntimeError` and its subclasses are
caught. Any other exception is a fault of the interpreter and escapes, and so
do the step budget and Python's recursion limit, which would stop bounding
anything if they turned into stuck terms.

A builtin that refuses an argument because the argument is itself stuck says
why it is stuck as well. The refusal carries the argument's own reason — the
`cause` it was recorded with, its `error`, or the name of the unbound variable
at its head — and the application records it under `cause`. Every stuck
application therefore knows the first reason in the chain that led to it, at
the cost of one look at the argument, and readback reports it next to the
error. A missing label whose lookup is consed onto a list of defeaters is
reported as

    evaluation stopped here: PGSNTypeError: Cons: the second argument must be a list, got App, which was stuck on PGSNKeyError: Record: there is no label 'missing'

rather than as the first half alone. The path reported is that of the outer
application, where evaluation came to rest, not that of the cause.

### 1.8 The conditional is lazy in its branches

`if_then_else` is not the builtin itself but a three-argument abstraction that
wraps each branch before the builtin sees it:

    λc. λt. λe. IfThenElse c (λ_. t) (λ_. e) undefined

A builtin is strict in its arguments (§1.4), so `IfThenElse` handed the
branches as they were written would evaluate both before choosing, and the
base case of every recursion would be lost. Wrapped, each branch is an
abstraction, which is already a value, so evaluating it does nothing. The
builtin selects one of the two abstractions, and the application to a dummy
argument evaluates the one that won.

When the condition never becomes a boolean or an integer (a positive integer
counts as true), the builtin refuses it and the application cannot proceed.
Its arguments are then part of the result (§1.3), but they are abstractions,
so nothing under them is evaluated (§1.1), and the application is reported
stuck where it stands (§1.7).

This is what makes a missing record label visible where it occurs. A lookup
that cannot proceed reaches a fold as the list being folded; the test
`is_empty list` cannot proceed either; and the fold stops instead of unfolding
its recursive branch until the step budget runs out. The same holds for a
recursion the author writes themselves, through `<if>` and a recursive
binding, because `<if>` expands to an application of this same term (§5.2).

`Guard` is not wrapped. It takes the body it guards as an ordinary argument,
so the body is evaluated to a weak head normal form even while the condition
is false; no predefined name recurses through it.

## 2. Equality and types

### 2.1 Equality compares data only

`equal` compares data and declines everything else, so the evaluator never
has to decide what it is for two terms of any other kind to be the same. The
leaves of data are always base values. Anything else leaves the application
stuck, so the question is refused rather than answered wrongly. Both sides are
evaluated in full and checked to be data before anything is answered, so the
answer does not depend on the order of the components: `equal [goal] empty` is
refused, not `false`.

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

### 2.2 Classes have no identity

PGSN does not decide when two classes are the same: there is nothing to decide
it by. A structural comparison of classes would have to compare their defaults
and methods. Methods are functions, which have no equality, and a default can
be an object (`goal_class` defaults `support` to `undeveloped`), which is not
data. Comparing the terms as they stand instead would make the answer depend
on how far evaluation had got. So a type is checked with `is_subtype`, which
compares the attribute and method *names* the two classes declare and looks at
nothing else. Names belong to a class's shape rather than its contents, so the
answer is the same however far either side has been evaluated, and the
evaluator is free to represent a class however it likes as long as it can
report those names. From XML the check is reached through `typeOf`, which
compiles to `guard (is_subtype (type_of v) T) v`. A `<param>` takes no `typeOf`:
a parameter is bound by an abstraction, so a check on it would have to be
planted in the body, and the author can write it there where the value is
used.

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
makes two classes the same is left open (known_issues.md) rather than decided
by accident.

## 3. Names and scope

### 3.1 Predefined names are ordinary bindings

A name is always compiled to a variable, and what it refers to is decided by
the enclosing bindings. The predefined names are supplied by a scope that
wraps each compilation unit — the entry point and each module it imports. A
predefined name is therefore an ordinary
binding: a `<def>` or a parameter with the same name shadows it, as any
binding shadows an outer one.

Only the names a unit actually leaves free are bound. Binding the whole table
instead would mean the same thing — a name never mentioned cannot be observed —
but every compiled document, and every module in it, would then carry every
predefined name, in its term and in the JSON that `pgsn compile` writes. Real
documents bind a handful.

The free names are found with `Term.free_variables()`, the same traversal that
name removal depends on, so nothing new has to be trusted.

### 3.2 Reserved names

`1 + 2` written in `expr=` or `<expr>` must mean addition whatever the
surrounding document has bound `plus` to. Each predefined name is therefore
bound under two names: its own, which a document may rebind like any other,
and a reserved alias, which it may not, because names beginning with an
underscore are rejected in source documents. Desugaring goes through the
reserved alias. The check that rejects such names therefore has to run on the
document as written, before desugaring has introduced any of its own (§5.1).
Because desugaring reaches the predefined names this way, the language needs
no element for naming one past a rebinding.

Which alias belongs to which predefined name is an implementation detail and
is deliberately absent from the documentation, this file included. What the
language guarantees is only that a name beginning with an underscore is
reserved.

### 3.3 Rebinding is shadowing

The bindings of a block fold into nested `let`s, so a later binding covers an
earlier one and nothing is overwritten. The value of a binding is read in the
scope before it, which is why `<def name="x"><var name="x"/></def>` refers to
the outer `x` and why self-reference needs `recursive="true"`, which wraps the
value in `fix` (§1.2).

## 4. Modules

A `<from>` is resolved at compile time: the file is read and compiled into the
module — an abstraction over its parameters, returning a record of its exported
names. The whole import graph becomes one term. Each file is compiled once for
each root it is reached under (normally once), however many times and from
however many places it is imported, and the entry point binds each module once
at its head, in an order in which a module comes after every module it
imports; an import is an application of that binding to the arguments given.
Embedding the module at every import instead makes the compiled term grow with
the number of import paths, which a chain of files each importing the next
twice makes exponential in its depth, and the step budget does not bound it,
since it applies only to evaluation.

At evaluation an import is a thunk like any other binding, so it is evaluated
once however many times the imported name is used. The module evaluates to a
record, and projecting a name from it evaluates that name's definition and
none of the others (§1.3), so a module costs what the document uses of it.

Each module carries a scope of predefined names of its own, and a module that
still has a free name once they are bound is rejected. Moving the module to the
head of the document is what makes this necessary: the compiled term still
refers to variables by name (names become de Bruijn indices only at
evaluation), so a free name in a module would be bound by whatever happens to
be in scope at the head. Rejecting it keeps the importing document's names out
of the module, so a module imported with the same arguments means the same in
every document that imports it. A `<PGSN>` document may still leave a name
free; nothing moves it, and readback reports the name.

A `<from>` used as a binding (one with `import`) binds the applied module to a reserved name and
projects each imported name from it, so the module occupies one position in the
compiled term however many names are taken from it. Rebinding that reserved
name for the next `<from>` in the same block is harmless, because each
projection reads the binding nearest to it.

## 5. Surface syntax

### 5.1 The order of the passes

`expr=` and `var=` are accepted wherever a value is expected, rather than on
one element. A shorthand that works in a single place is a rule to remember; a
shorthand that works everywhere a value is expected rides on a rule that
already exists.

The promise that a shorthand works everywhere is kept by the order of the
passes (stages 1–3 of the introduction), not only by the rules. What separates
desugaring from compilation is how much each is allowed to know about the
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

### 5.2 Conditionals

`<if>` and `<cases>` are expanded before compilation into an application of
`if_then_else`, reached through its reserved alias, so rebinding
`if_then_else` does not change what `<if>` means. That term thunks its own
branches (§1.8), so a conditional written in XML is lazy in its branches
without the expansion having to arrange anything.

`<else>` is required in both. A conditional without it can be written — the
term simply cannot proceed when no case matches — but a term that cannot
proceed surfaces far from the mistake, and no author means "none of these, and
nothing else either".

### 5.3 Content is a sequence of items

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

### 5.4 A record label is spelled `key`

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

### 5.5 Expressions are read as Python reads them

`<expr>` takes a part of Python's expressions with Python's meaning:
precedence, chained comparisons, the conditional expression, calls, attribute
access, Python's integer and string literals and f-strings. The parser is a
small recursive-descent one in `pgsn_xml.py` rather than Python's own, and the
keywords are written out as those of Python 3.12, so the language does not
change when Python's grammar does.

An expression is expanded into the XML it abbreviates, where it stands, so a
name in it resolves as a `<var>` would at that place. A name is a letter
followed by letters, digits and underscores, letters being Unicode letters, so
a Japanese name is a name; Python's keywords are not names. The parser checks a
name with the same function the attributes are checked with, so every name a
`<def>` can bind can be written in an expression. Operators, `True` and
`False` go through the reserved aliases (§3.2) and always mean the predefined
operations. `/` is rejected rather than read as `//`, so that it stays free for
true division should a floating point type be added.

A field of bare text is an expression too, read by the same parser, and the
fields of text and of an f-string are found by one scanner. The two differ in
when a mistake is reported. An f-string is part of an `<expr>`, whose syntax is
checked at compile time. Text is not: a field that does not parse, and a brace
left single, stay in the format string as written, and `format_string` reports
them when the document is evaluated. A field that is a name is passed under
that name, so `{x}` compiles to a lookup of `x` and nothing more.

### 5.6 The schema describes the surface syntax

The schema `PGSN.rng` is experimental; README-xml.md is what defines the
syntax.

The schema is asked about the document an author wrote, shorthands and all, so
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

Validating is worth the trouble because it catches what evaluating cannot: the
compiler ignores a child element or an attribute it does not recognize, and the
schema rejects both (known_issues.md). `tests/test_schema.py` runs every file
under `examples/` through the validator when one is installed, and is the only
thing that keeps the schema in step with the compiler. Validating before
compiling would close the gap where it opens, and would stop the tag sets the
compilers filter on from being the only thing that decides what a document may
contain.

`"builtin"` stays in `_VALUE_TAGS` although there is no `<builtin>` element. A
GSN element with neither leading text nor a `<description>` takes a lone value
child as its description, and listing the tag there makes `<builtin>` in that
position an unknown expression rather than nothing. In an element that has a
description it is dropped like any other unknown child.

### 5.7 A list is ordered, and there is one kind of it

Sub-goals, contexts, assumptions and defeaters are `List` terms, and the order
of their elements is part of what a document says.

GSN v3 does not settle whether the order of siblings means anything. It
defines the node types and the SupportedBy and InContextOf relations, and
assigns no meaning to the order of siblings; ordering there is a matter of
layout. So the question is PGSN's to answer, not a point of conformance.

The answer is that the order is part of what the document says. It is the
reading that costs nothing — a document that does not care about the order of
its sub-goals loses nothing by having it preserved — while the other reading
costs the author the ability to say "these hazards in this order", which no
notation gives back. How the renderers keep the order is in §6.3.

There is one list element, `<ol>`, and it is ordered. A document that writes
`<ul>`, or `as="ul"`, is told the expression is unknown. An unordered list
compiling to the same `List` would let a document state a distinction the
compiler discards, and authors would come to depend on the order it kept, so a
set added later would silently reorder their documents. A set needs more than
a tag: an equality on its elements, which data has and functions and nodes do
not (§2.1), and a canonical order to render it in. If one is wanted it gets its
own element and its own term type, so that no existing document changes
meaning under it.

## 6. GSN classes and output

### 6.1 One Defeater class; contexts attach to goals and strategies

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
standard's Figure 6, where an assumption hangs off the strategy.

### 6.2 The output follows GSN v3

The drawing and the validity check follow the standard, so a reader of the
output meets GSN v3 rather than PGSN's encoding of it.

**Undeveloped.** `undeveloped` is a value, written where a goal's support or a
strategy's sub-goal would go. The drawing does not show it as an element of its
own: it is absorbed into the element that holds it, which gets the standard's
◇ under its box. A defeater left without support gets no ◇, since the standard
gives the decorator to goals and strategies only.

**Identifiers.** The standard requires every element to have one. The drawing
heads each box with an identifier made from its type and its position among the
elements of that type, in the order the drawing walks the structure: depth
first, and within a node its contexts, assumptions and defeaters before its
support. The prefixes are G, S, Sn, C, A, and CG for a defeater, after the
standard's own examples of a challenging goal. These are labels of the drawing,
not names in the document. Nothing in a document refers to an element: an
element is a value, and the language gives values no identity (§2.2).

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

### 6.3 The renderers keep the order

`python_value` reports the elements of a list in document order (§5.7). The
renderers would not unless asked: `gsn_tree` builds a `treelib.Tree`, and
treelib sorts siblings by tag unless told otherwise, which would reach
`tree.show` (`pgsn doc`), `tree.to_json` (`pgsn doc -d json`) and the
`expand_tree` walk in `gsn_dot` (`pgsn render`). Every renderer therefore asks
treelib not to sort. The option is passed at the call, not hidden in a subclass
of `Tree`: `gsn_tree` returns treelib's own tree, and a caller who renders it
passes `sorting=False` (or `sort=False` to `to_json`) the way `pgsn doc` does.
Wrapping the library to change its defaults would make our tree something the
reader has to learn before trusting treelib's documentation about it.

Within a node, the children a renderer reports are the node's attributes, whose
order is the order the record was built in rather than anything sorted. The
constructors in `gsn.py` write them in one order for that reason: what the node
is stated in the context of, then what challenges it, then what it rests on.

## 7. Measurements

The twenty-four entry points under `examples/` are compiled, evaluated and
converted with `python_value` in about 0.54 s altogether (one process, one run
after another, rendering excluded; MacBook Air, Python 3.12, commit `a3faff5`).
The slowest five are the four full EU AI Act cases, which import the full Act,
and SolarWinds, the largest document without imports:

| document | time | steps |
|---|---|---|
| `EU_AI_ACT/case_proctoring.xml` | 0.11 s | 8,459 |
| `EU_AI_ACT/case_recruitment_ai.xml` | 0.07 s | 4,521 |
| `EU_AI_ACT/case_medical_ai.xml` | 0.07 s | 4,429 |
| `EU_AI_ACT/case_gpai_system.xml` | 0.06 s | 4,388 |
| `SolarWinds.xml` | 0.05 s | 1,933 |

The steps are those of §1.6, well inside the default budget of a million.
Sharing is what keeps a module cheap: a name imported with
`<from … import=…>` and used fifty times takes as many steps as one used once,
and a definition of the module that the document does not use takes none.

`tests/test_examples.py` evaluates every entry point without fixing what they
produce, since they are material rather than specification. The four full EU
AI Act cases are marked `slow` and run only under `pytest -m slow`.
