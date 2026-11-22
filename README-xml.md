# PGSN XML syntax

This document defines the XML syntax of PGSN, which extends GSN (Goal Structuring Notation) with programming constructs: GSN elements are values that can be named, passed to templates, generated from lists and extended with classes. It is the reference for the syntax; where the processor behaves otherwise, the deviation is listed in [known_issues.md](known_issues.md). [README.md](README.md) explains how to install and run `pgsn`, and [README-ja-xml.md](README-ja-xml.md) is the Japanese version of this document.

The first two sections are a guided start: [A first argument](#a-first-argument) and [GSN elements](#gsn-elements). The rest is a reference. [Elements at a glance](#elements-at-a-glance) at the end lists every element and attribute.

Contents:

1. [A first argument](#a-first-argument)
2. [GSN elements](#gsn-elements)
3. [Values](#values)
4. [Names and definitions](#names-and-definitions)
5. [Shorthand attributes](#shorthand-attributes)
6. [Expressions (expr)](#expressions-expr)
7. [Conditionals (if, cases)](#conditionals-if-cases)
8. [Templates and application](#templates-and-application)
9. [Classes and objects](#classes-and-objects)
10. [Documents and modules](#documents-and-modules)
11. [Builtins](#builtins)
12. [Principles](#principles)
13. [Elements at a glance](#elements-at-a-glance)

---

## A first argument

A document is a `<PGSN>` element whose content is one value, here a goal. An element's leading text is its description, and the elements nested inside it say what supports it, what context it is stated in and what challenges it:

```xml
<PGSN>
    <Goal>
        The braking system is acceptably safe
        <Context>Braking system, release 2.1</Context>
        <Strategy>
            Argue over each identified hazard
            <Assumption>The hazard list is complete</Assumption>
            <Goal>Hazard H1 (loss of braking) is mitigated
                <Solution>Fault tree analysis FTA-1</Solution>
            </Goal>
            <Goal>Hazard H2 (unintended braking) is mitigated
                <Defeater>The analysis predates the last design change</Defeater>
                <Solution>Test report TR-7</Solution>
            </Goal>
            <Goal>Hazard H3 (delayed braking) is mitigated</Goal>
        </Strategy>
    </Goal>
</PGSN>
```

`pgsn doc` evaluates the document and prints the argument as a tree (`pgsn render` draws it):

```console
$ pgsn doc braking.xml -o -
Evaluating term 'main'...
Goal: The braking system is acceptably safe
├── Context: Braking system, release 2.1
└── Strategy: Argue over each identified hazard
    ├── Assumption: The hazard list is complete
    ├── Goal: Hazard H1 (loss of braking) is mitigated
    │   └── Solution: Fault tree analysis FTA-1
    ├── Goal: Hazard H2 (unintended braking) is mitigated
    │   ├── Defeater: The analysis predates the last design change
    │   │   └── Undeveloped: 
    │   └── Solution: Test report TR-7
    └── Goal: Hazard H3 (delayed braking) is mitigated
        └── Undeveloped: 

Done.
```

H3 has no support, so it is undeveloped. The defeater raises a doubt without arguing for it, so it is undeveloped too.

So far this is plain GSN written in XML. What PGSN adds is that the three hazard goals need not be written out one by one. The document below keeps the hazards in a list, defines the shape of a hazard goal once as a *template*, and applies the template to every item of the list with `map_term`:

```xml
<PGSN>
    <def name="hazards"><ol>
        <li><dl><dt>name</dt><dd>H1 (loss of braking)</dd><dt>evidence</dt><dd>Fault tree analysis FTA-1</dd></dl></li>
        <li><dl><dt>name</dt><dd>H2 (unintended braking)</dd><dt>evidence</dt><dd>Test report TR-7</dd></dl></li>
        <li><dl><dt>name</dt><dd>H3 (delayed braking)</dd><dt>evidence</dt><dd>Timing analysis TA-2</dd></dl></li>
    </ol></def>

    <def name="mitigated" as="template">
        <param name="h" positional="true"/>
        <Goal>Hazard {h.name} is mitigated
            <Solution>{h.evidence}</Solution>
        </Goal>
    </def>

    <Goal>
        The braking system is acceptably safe
        <Strategy>
            Argue over each identified hazard
            <subGoals expr="map_term(mitigated, hazards)"/>
        </Strategy>
    </Goal>
</PGSN>
```

```console
$ pgsn doc braking2.xml -o -
Evaluating term 'main'...
Goal: The braking system is acceptably safe
└── Strategy: Argue over each identified hazard
    ├── Goal: Hazard H1 (loss of braking) is mitigated
    │   └── Solution: Fault tree analysis FTA-1
    ├── Goal: Hazard H2 (unintended braking) is mitigated
    │   └── Solution: Test report TR-7
    └── Goal: Hazard H3 (delayed braking) is mitigated
        └── Solution: Timing analysis TA-2

Done.
```

The pieces used here are described in the reference: `<def>` in [Definitions](#definitions-def), `<ol>` and `<dl>` in [Lists](#lists-ol) and [Records](#records-dl), `{h.name}` in [Format strings in text](#format-strings-in-text), `<template>` in [Templates and application](#templates-and-application), `<param>` and `positional` in [Parameters](#parameters-param), `map_term` in [Builtins](#builtins), and the `as` and `expr` attributes in [Shorthand attributes](#shorthand-attributes). A template can also live in a file of its own and be imported by several documents; see [Documents and modules](#documents-and-modules).

---

## GSN elements

GSN elements are values: they can be bound to names, held in lists, passed to templates and returned from them. The examples below refer to named values with the `var` attribute, short for `<var name="…"/>` ([Shorthand attributes](#shorthand-attributes)). GSN v3 elements that PGSN does not have, such as Justification, are listed in [known_issues.md](known_issues.md).

### Descriptions

Every GSN element (`Goal`, `Strategy`, `Solution`, `Defeater`, `Context`, `Assumption`) has a description. Its leading text is the description, whether or not the element also has child elements, and writing a `<description>` element says the same thing. `{...}` fields are filled in as in any text ([Format strings in text](#format-strings-in-text)).

```xml
<!-- these two forms are equivalent -->
<Goal>
    System {name} is secure
    <undeveloped/>
</Goal>

<Goal>
    <description>System {name} is secure</description>
    <undeveloped/>
</Goal>
```

An element with no leading text takes a single value child as its description, so a computed description needs no `<description>` wrapper:

```xml
<Solution><expr>f"test report {i}"</expr></Solution>
```

An element with more than one value child is an error; put the description in a `<description>` element.

A description that is empty or blank, `<description/>` included, is not a compile error. It is the empty string ([Literals](#literals)), and the [GSN check](#checking-against-gsn-v3) reports it, as it does a blank description computed while the document is evaluated.

### Goal

```xml
<Goal>
    <description>System X is secure</description>
    <Context>certified under standard XXXX</Context>
    <Assumption>no zero-day attacks</Assumption>

    <!-- support: one of the following -->
    <Strategy>...</Strategy>              <!-- supported by a Strategy -->
    <Solution>...</Solution>              <!-- supported by a Solution -->
    <Goal>...</Goal>                      <!-- supported by sub-goals (one or more) -->
    <supportedBy var="strategy1"/>        <!-- supported by a computed value -->
    <undeveloped/>                        <!-- not yet developed -->
</Goal>
```

A goal has exactly one support. A `<Goal>` with none is undeveloped, as if `<undeveloped/>` were written.

One or more `<Goal>` elements written directly under a Goal are shorthand: they are wrapped by `immediate`, which makes a Strategy holding them. How that Strategy shows in the output is listed in [known_issues.md](known_issues.md). To support a goal with a list of goals computed while the document is evaluated, apply `immediate` to the list yourself:

```xml
<Goal>
    Security requirements fulfilled
    <supportedBy>
        <apply><var name="immediate"/><arg var="goals"/></apply>
    </supportedBy>
</Goal>
```

### Strategy

```xml
<Strategy>
    argument
    <!-- sub-goals: one of the following -->
    <Goal>...</Goal>           <!-- sub-goals written out (one or more) -->
    <subGoals var="goals"/>    <!-- sub-goals computed as a list -->
</Strategy>
```

A Strategy must have sub-goals: a `<Strategy>` with neither `<Goal>` children nor `<subGoals>` is a compile error (`<Strategy> requires sub-goals or <subGoals>`). To leave a strategy open, write `<undeveloped/>` among its sub-goals, alone or beside `<Goal>` elements. The strategy is then undeveloped, which GSN v3 allows for strategies as well as goals, and the drawing marks it with the undeveloped decorator.

```xml
<Strategy>argue over each hazard<undeveloped/></Strategy>
```

`<subGoals>` takes a list (`ol`), so sub-goals can be computed:

```xml
<Strategy>
    argument
    <subGoals>
        <ol>
            <li var="goal1"/>
            <li var="goal2"/>
        </ol>
    </subGoals>
</Strategy>
```

To list goals held in variables, use `<subGoals>` as above. `<Goal var="g"/>` does not mean the goal `g`: it makes a new goal whose description is the value of `g` ([Shorthand attributes](#shorthand-attributes)).

### Solution

A Solution presents a reference to an evidence item, as in GSN v3. It carries a description, and defeaters if its adequacy is challenged.

```xml
<Solution>
    <description>test result report</description>
    <Defeater>the report predates the last release</Defeater>
</Solution>
```

### Context and Assumption

```xml
<!-- Context: the setting in which the argument holds -->
<Context>textual description</Context>
<Context var="someObject"/>                            <!-- variable reference -->
<Context><get key="version" of="release"/></Context>  <!-- expression -->

<!-- Assumption: an assumption the argument relies on -->
<Assumption>no zero-day attacks</Assumption>
<Assumption var="someObject"/>                         <!-- variable reference -->
```

- `Context` describes the setting or subject matter in which the argument is made.
- `Assumption` states an assumption the argument relies on.

A `Context` or an `Assumption` is written inside a `Goal` or a `Strategy`, the two elements GSN v3 attaches them to; a strategy carries the assumption its reasoning depends on. `Solution` and `Defeater` take neither. `<Context>` and `<Assumption>` are not values on their own: to compute one, apply the builtin `context` or `assumption`.

Each holds a single value: text, a variable reference, an object, a list and so on. The [GSN check](#checking-against-gsn-v3), however, reports any value that is not a non-blank string, since GSN gives every element a statement.

### Defeater

GSN v3 adds a dialectic extension: a *defeater* records a doubt about part of an argument rather than support for it. Any Goal, Strategy, Solution or Defeater can hold defeaters, and a defeater can be challenged in turn.

```xml
<Goal>the system is safe
    <Defeater>hazard H4 is unmitigated
        <Solution>incident report 2026-03</Solution>
    </Defeater>
    <Defeater>the test suite is out of date
        <Defeater>it was refreshed in revision 7</Defeater>
    </Defeater>
    <Solution>test report</Solution>
</Goal>
```

A `<Defeater>` is written like a goal: leading text or a `<description>` gives the description, a nested `<Solution>`, `<Strategy>`, `<Goal>` or `<supportedBy>` gives its support, and nested `<Defeater>` elements challenge it. Support is optional and defaults to undeveloped: a defeater that argues its case fills it in, and one that merely states an objection leaves it out.

Defeaters attach to strategies and to solutions as well as to goals:

```xml
<Strategy>argue over each hazard
    <Defeater>the hazard list is incomplete</Defeater>
    <Goal>H1 is mitigated<Solution>report H1</Solution></Goal>
</Strategy>
```

The corresponding builtin is `defeater`, with the class value `defeater_class`.

The Defeater element is PGSN's own. GSN v3 has no Defeater element: a defeater there is an ordinary Goal or Solution joined to its target by a Challenges relationship. [PGSN-implementation.md](PGSN-implementation.md) explains why PGSN makes the challenging role an element.

### What each element takes

| Element | Description | Context, Assumption | Defeater | Support |
|---|---|---|---|---|
| `Goal` | yes | yes | yes | one of `Strategy`, `Solution`, `Goal`…, `supportedBy`, `undeveloped`; none means undeveloped |
| `Strategy` | yes | yes | yes | `Goal`… and `undeveloped`, or `subGoals`; required |
| `Solution` | yes | no | yes | none |
| `Defeater` | yes | no | yes | optional: `Solution`, `Strategy`, `Goal`…, `supportedBy`; none means undeveloped |
| `Context`, `Assumption` | yes | no | no | none |

A GSN element evaluates to an object of a GSN class, whose attributes can be read with [`<get>`](#reading-a-label-get) and listed in an [`<object>`](#objects-object):

| Class | Attributes |
|---|---|
| `Goal` | `description`, `contexts`, `assumptions`, `defeaters`, `support` |
| `Strategy` | `description`, `contexts`, `assumptions`, `defeaters`, `sub_goals` |
| `Solution`, `Context`, `Assumption` | `description`, `defeaters` |
| `Defeater` | `description`, `defeaters`, `support` |

`Context` and `Assumption` declare `defeaters`, but neither element takes a `<Defeater>`.

### Checking against GSN v3

A document can put any value in any position, so a structure can evaluate and still not be one the GSN Community Standard, Version 3 (GSN v3) allows. `pgsn doc` and `pgsn render` check the result against the rules a document can break, and print a warning for each element that breaks one, with its identifier and its position in the tree:

```xml
<PGSN><Goal>System is secure<Strategy>Break into sub-goals<subGoals><ol/></subGoals></Strategy></Goal></PGSN>
```

```console
$ pgsn doc check.xml -o -
Evaluating term 'main'...
Warning: S1 at <root>.support: a strategy relates a goal to supporting goals, but this one has none
Goal: System is secure
└── Strategy: Break into sub-goals

Done.
```

The rules are:

1. A goal is supported by a strategy, a solution or sub-goals, and a strategy by goals.
2. The contexts of an element are Context nodes, and its assumptions are Assumption nodes.
3. A strategy has at least one sub-goal.
4. What challenges an element is a defeater.
5. Every element's description is a non-blank string.
6. The structure is headed by a goal.

With `--strict` a breach is an error: the command writes nothing and exits with status 1. The same check is available in Python as `gsn_violations` ([README-api.md](README-api.md#reading-results)).

### How the output is drawn

`pgsn render` draws the result after GSN v3:

- Each element is headed by an identifier made of a prefix and a number: G for a goal, S for a strategy, Sn for a solution, C for a context, A for an assumption and CG for a defeater. Elements of each kind are numbered in the order the drawing walks the structure: depth first, and within an element its contexts, assumptions and defeaters before its support. The warnings of the GSN check use the same identifiers. They are labels of the drawing, not names a document can refer to.
- An undeveloped goal or strategy gets the ◇ decorator under its box; `undeveloped` is not drawn as an element of its own. A defeater without support gets no decorator.
- SupportedBy has a solid arrowhead and InContextOf a hollow one. An Assumption is marked with an A.
- A defeater is drawn as a hexagon with a broken outline, and its Challenges relationship as a dashed line with an open arrowhead pointing at what it challenges, so that it does not read as SupportedBy. The hexagon is PGSN's own shape: GSN v3 draws a challenging element as an ordinary goal or solution.

---

## Values

Every element that accepts content expects an **expression**: something that evaluates to a value. There are no special name slots and no class-name strings.

The examples in this section bind names with `<def name="x">` and refer to them with `<var name="x"/>`; [Names and definitions](#names-and-definitions) describes the two.

> **Key principle: bare text becomes a String literal.**
> When you write text directly inside an element, it is a `String` value.
> `<li>goal1</li>` does not refer to a goal bound to `goal1` — it is the string
> `"goal1"`. To refer to a variable, use `<var>` or the `var=` shorthand
> attribute.

```xml
<!-- WRONG: the sub-goal is the string "goal1", not the goal bound to goal1;
     the GSN check warns "a strategy is supported by goals, not by text" -->
<subGoals><ol><li>goal1</li></ol></subGoals>

<!-- CORRECT: var= is shorthand for a variable reference -->
<subGoals><ol><li var="goal1"/></ol></subGoals>
```

The same holds for classes: `<inherit>Goal</inherit>` produces the string `"Goal"`, which is not a class.

```xml
<!-- WRONG: text content becomes the string "Goal", not the class itself -->
<inherit>Goal</inherit>

<!-- CORRECT: var= is shorthand for a variable reference -->
<inherit var="Goal"/>

<!-- CORRECT: full form -->
<inherit><var name="Goal"/></inherit>

<!-- CORRECT: any expression that evaluates to a class works -->
<inherit><apply template="makeBaseClass"><arg>...</arg></apply></inherit>
```

### Literals

Bare text is a string, so the other literal forms are written out.

| Element | Value |
|---------|-------|
| bare text | a `String`. Leading and trailing whitespace is removed, and `{...}` fields are filled in — see [Format strings in text](#format-strings-in-text) |
| `<num>3</num>` | an `Integer`: a decimal integer such as `-3` or `1_000`. PGSN has no floating point numbers |
| `<str> a {b} </str>` | a `String`, taken exactly as written: whitespace is kept and `{...}` is not filled in |

Empty content is the empty string as well: `<li/>`, `<dd/>`, `<def name="x"/>` and `<description/>` each stand for `""`, since an element with nothing in it holds the empty text. `<x/>` and `<x></x>` are the same. There are two exceptions. An element whose content must be a list, `<ol/>` or `<subGoals/>`, stands for the empty list. An empty `<arg>` passes nothing, so the parameter takes its default (see [Template application](#template-application-apply)).

`<num>` matters because bare text stays a string even when it looks like a number, which is what lets a goal say `2024 audit passed` without the year turning into an integer. The arithmetic builtins only accept integers, so `<arg>3</arg>` hands them a string and the sum is never computed; write `<arg><num>3</num></arg>`.

### Format strings in text

Wherever text stands for a value, a field `{...}` puts a value into it. What stands between the braces is an expression, as in [`<expr>`](#expressions-expr), so `{c}` is the variable `c`, `{n + 1}` is one more than `n` and `{h.name}` is the label `name` of the record `h`. The value of a field must be a string, an integer or a boolean. To write a literal brace, escape it as `{{` or `}}`. The text becomes an application of the builtin `format_string`.

Text is not checked when the document is compiled. A field that cannot be read as an expression, and a brace left single, stay in the text as written, and `pgsn doc` reports them when the document is evaluated.

```xml
<template>
    <param name="c" positional="true"/>
    <Solution>Test result for component {c}</Solution>
</template>
```

### Lists (ol)

```xml
<ol>
    <li>expr1</li>
    <li var="x"/>    <!-- shorthand -->
</ol>
```

`ol` is the only list element, and the order of its items is part of what the document says: every rendering reports them in the order they were written. There is no set.

### Records (dl)

A record maps labels to values. A label is a string literal, written as the text of a `<dt>` or as its `key` attribute. It is not an expression, so a record whose labels are computed is built with the builtin `add_attribute` instead.

```xml
<dl>
    <dt>name</dt><dd>value_expr</dd>       <!-- label as text -->
    <dt key="name"/><dd>value_expr</dd>    <!-- the same label -->
</dl>
```

A record is read with [`<get>`](#reading-a-label-get).

---

## Names and definitions

### Names

A *name* is what `<def>` and `<param>` introduce and what `<var>` refers to. A *label* is what a record or an object is read at. The two follow different rules:

| Holds a name | Holds a label |
|---|---|
| `name` on `<def>`, `<param>`, `<var>` and `<arg>` | `key` on `<get>` and `<dt>` |
| `typeOf` on `<def>` and `<var>` | `method` on `<send>` |
| `as` on `<from>` and `<import>` | `name` on `<attribute>` and `<method>` |
| `template` on `<apply>`, `of` on `<get>`, `to` on `<send>` | `name` on `<class>` (what the class is called) |
| the `var` shorthand attribute | |

A name must begin with a letter and may continue with letters, digits and underscores. Letters are not restricted to ASCII, so `ゴール` is a name. A name may **not** begin with an underscore; those are reserved by the processor. Python's keywords — `and`, `if`, `lambda`, `None`, `True` and the rest — are not names either, because an [expression](#expressions-expr) has them as its keywords; every name a `<def>` can bind can then be written in an expression. Python's soft keywords, such as `match` and `type`, are names.

A label is an arbitrary string.

### Definitions (def)

`<def>` binds a name to a value for the rest of the block it is in:

```xml
<def name="x">expr</def>
```

A name may be bound more than once in the same block; a later binding shadows an earlier one from that point on. Nothing is changed — the earlier binding still holds wherever it was already visible — so this is shadowing, not assignment. A binding's own value is read in the scope *before* it, which means `<def name="x"><var name="x"/></def>` refers to the outer `x` rather than to itself; see [Recursive definitions](#recursive-definitions) for self-reference.

The builtin names are bound the same way, in the outermost scope, so a document is free to bind `head` or `goal` to something of its own.

### Local definitions

Use `<def>` elements inside a `<div>` to scope definitions locally. The last item of the `<div>` is its value. A `<from>` may stand among the `<def>` elements; the names it imports are bound for the rest of the block.

```xml
<div>
    <def name="x">expr1</def>
    <def name="y">expr2</def>
    expr   <!-- the value of the div -->
</div>
```

`<def>` elements can also appear directly inside a `<template>` body, before the final value expression, without a wrapping `<div>`:

```xml
<template>
    <param name="x"/>
    <def name="doubled"><apply><var name="plus"/><arg var="x"/><arg var="x"/></apply></def>
    <var name="doubled"/>   <!-- final value -->
</template>
```

### Recursive definitions

`recursive="true"` makes a definition visible inside its own value, so a template can call itself:

```xml
<def name="countdown" recursive="true" as="template">
    <param name="n" positional="true"/>
    <if>
        <cond expr="n == 0"/>
        <then><ol/></then>
        <else expr="cons(n, countdown(n - 1))"/>
    </if>
</def>
```

The recursion must stop through a conditional ([`<if>` or `<cases>`](#conditionals-if-cases)): only the branch taken is evaluated. Only the definition itself is made visible; mutual recursion is listed in [known_issues.md](known_issues.md).

### Variables (var)

`<var>` refers to a name bound earlier, or to a [builtin](#builtins).

```xml
<var name="x"/>

<!-- with a type check -->
<var name="x" typeOf="MyClass"/>
```

### Type checks (typeOf)

`typeOf` checks a value against a type. `<def>` and `<var>` both take it; the attribute value is a **name** bound to a class.

```xml
<def name="g" typeOf="Goal">
    <Goal><description>system is safe</description><undeveloped/></Goal>
</def>

<var name="g" typeOf="Goal"/>
```

**Typing is structural.** A value satisfies a type when its class declares at least the attributes and methods the type declares. Where the class came from does not enter into it: a class of your own that carries `description` and `defeaters` satisfies `Solution` without inheriting from it, and a `Goal` satisfies `Solution` too, since it declares those labels and more. Nothing compares class *identities*, which is what makes the answer the same whichever copy of a class is asked about.

A check that fails does not raise an error at that point. The value simply does not pass, so the document has no value to give, and `pgsn doc` names the path at which it stopped ([Principles](#principles)).

`<param>` does not take `typeOf`; check the value where it is used instead.

---

## Shorthand attributes

A shorthand attribute stands for content: the element is the same as the element with that content written out. Every shorthand can be written on any element that takes content, unless the table says otherwise.

| Attribute | Stands for | Where |
|---|---|---|
| `var="x"` | the content `<var name="x"/>` | any element with content |
| `expr="e"` | the content `<expr>e</expr>` | any element with content |
| `as="T"` | wrapping the content in `<T>…</T>` | any element with content except `<from>` and `<import>`, where `as` renames |
| `template="f"` | `<var name="f"/>` as the function | `<apply>` |
| `of="r"` | `<var name="r"/>` as the receiver | `<get>` |
| `to="o"` | `<var name="o"/>` as the receiver | `<send>` |
| `key="k"` | the text `k` | `<dt>` |

An element may not carry `var` or `expr` and content of its own (`<li> has both an 'expr' attribute and content of its own`).

### var

```xml
<!-- full form -->
<tag><var name="x"/></tag>

<!-- shorthand -->
<tag var="x"/>
```

### expr

```xml
<!-- full form -->
<arg><expr>i + 1</expr></arg>

<!-- shorthand -->
<arg expr="i + 1"/>
```

Two details of XML are worth remembering: `<` must be written `&lt;` inside an attribute value, and an f-string needs the attribute quoted with `'` so that the double quotes inside it do not end the attribute.

```xml
<def name="label" expr='f"component {i}"'/>
<li expr="i &lt; n"/>
```

### as

`as` names the element to wrap the content in, so the wrapper need not be written out:

```xml
<!-- full form -->
<def name="myGoal"><Goal>...</Goal></def>

<!-- shorthand -->
<def name="myGoal" as="Goal">...</def>
```

Any tag that is valid in that position can be named, `object` and `ol` and `Goal` alike.

- **Exception:** on `<from>` and `<import>`, `as` renames an imported name instead.
- **Restriction:** a tag that requires an attribute of its own cannot be named — `var` requires `name`, `get` requires `key`, `send` requires `method`, and a named `class` requires `name` — because `as` moves the content and leaves the attributes where they were.

---

## Expressions (expr)

Writing arithmetic with `<apply>` is heavy, so `<expr>` accepts expressions written as in Python:

```xml
<def name="next"><expr>i + 1</expr></def>
<def name="label"><expr>f"component {i} of {total}"</expr></def>
<def name="size"><expr>"large" if count > 10 else "small"</expr></def>
```

`<expr>` is a shorthand and nothing more. Before compilation it is expanded, where it stands, into the elements it abbreviates: an operator into an application of the corresponding builtin, a name into a `<var>`, a call into an `<apply>`, an attribute into a `<get>`. So a name in an expression means what `<var>` would mean at that place, and nothing is reachable through an expression that is not reachable without one.

### What may appear in an expression

The grammar is a subset of Python's expression syntax, read the way Python reads it.

| | |
|---|---|
| integers | `3`, `1_000`, `0x1F`, `0o17`, `0b101` |
| strings | `"text"`, `'text'`, `"""text"""`, `r"\d"`, with Python's escapes; adjacent strings are joined |
| f-strings | `f"component {i} of {total}"`, `f"{i + 1} left"` |
| booleans | `True`, `False` |
| names | `i` — becomes `<var name="i"/>` |
| arithmetic | `+`, `-`, `*`, `//`, `%`, and unary `-` and `+` |
| comparison | `==`, `!=`, `<`, `<=`, `>`, `>=`, chained as in Python: `a < b < c` is `a < b and b < c` |
| boolean | `and`, `or`, `not` |
| conditional | `x if c else y` — only the branch chosen is evaluated |
| calls | `f(x, k=1)` — becomes `<apply>`; `f()` takes every keyword parameter at its default |
| attributes | `r.key` — becomes `<get key="key">`; `obj.m(x)` calls a method |
| parentheses | `(i + 1) * 2` |

The operators bind as in Python: the conditional loosest, then `or`, `and`, `not`, the comparisons, `+` and `-`, `*`, `//` and `%`, the unary operators, and calls and attributes tightest.

Everything else is rejected with an error naming what was found. In particular there is no subscripting (`xs[0]`), no list, dict or tuple display (`[a, b]`; build lists with `<ol>`), no `lambda`, no comprehension, no `in` or `is`, and no `None`, which has no counterpart in PGSN. A floating point number is an error, since PGSN has none, and so is `**`, for which there is no builtin.

An f-string field is an expression. A conversion (`!r`), a format specification (`:>4`) and a `=` have no counterpart in a format string, so they are errors, as is a brace left single; `{{` and `}}` are the braces themselves. A field may hold a string literal in the other quote.

`True` and `False` always mean the booleans, as the operators always mean the builtins. `true` and `false` are the names those builtins are bound to, like any other name.

### Three things to know

`<` must be escaped in XML. Write `i &lt; n`, or wrap the expression in `CDATA`:

```xml
<expr>i &lt; n</expr>
<expr><![CDATA[i < n]]></expr>
```

`>` needs no escaping, so `n > i` is often the easier way to say the same thing.

`//` is integer division: `7 // 2` is `3`. `//` and `%` round toward negative infinity, as in Python, so `-7 // 2` is `-4`. `/` is rejected rather than treated as a synonym.

**Operators cannot be redefined.** `1 + 2` is addition even inside a scope that binds the name `plus`.

### Comparing values

Ordering (`<`, `<=`, `>`, `>=`) compares integers only, so `"a" < "b"` has no value.

Equality (`==`, `!=`) compares data: base values — a string, an integer, a boolean, `undefined` — and lists and records built out of them. So `"a" == "a"` is `True`, while two functions, two classes or two GSN elements have no value when compared, just as `"a" < "b"` has none.

To test whether a list is empty, apply `is_empty`. Comparing the list with `empty` answers only for a list of data.

---

## Conditionals (if, cases)

`if_then_else` is a builtin and can be applied like any other, but a two-way choice written that way is hard to read. `<if>` says the same thing with the parts named:

```xml
<if>
    <cond expr="i &lt; threshold"/>
    <then>within budget</then>
    <else>over budget</else>
</if>
```

`<else>` is required. The branch not taken is not evaluated, so a conditional can stop a recursion.

For a chain of conditions, `<cases>` takes the first `<case>` whose `<cond>` holds, and falls back to `<else>`:

```xml
<cases>
    <case><cond expr="severity == 0"/><then>negligible</then></case>
    <case><cond expr="severity &lt; 3"/><then>tolerable</then></case>
    <else>unacceptable</else>
</cases>
```

`<else>` is required here too. Without one, a `<cases>` that matched nothing would have no value to give, and the mistake would surface far from where it was made.

A condition is a boolean or an integer. A positive integer counts as true, and zero or a negative integer as false; `and`, `or` and `not` treat integers the same way. Any other condition, a string for example, leaves the conditional without a value.

Each of `<cond>`, `<then>` and `<else>` is a wrapper holding a value, so any of the ways of writing a value work inside one, including the `var` and `expr` shorthands.

Both forms stand for an application of the `if_then_else` builtin, and both reach it in a way no binding can intercept — `<if>` means a conditional even in a scope that binds the name `if_then_else`.

---

## Templates and application

### Parameters (param)

`<param>` declares a name bound from outside the element that holds it. Three elements take parameters: a `<template>`, which receives them from the `<apply>` that calls it, a `<method>`, which receives them from the `<send>` that invokes it, and a `<PGSNModule>`, which receives them from the document that imports it. Parameters come first, before anything else in the element.

```xml
<param name="A1"/>

<!-- with a default value -->
<param name="threshold">100</param>
```

A parameter is **positional** or **keyword**:

- A `param` marked `positional="true"` is **positional**.
- A `param` without it is a **keyword** parameter.
- As in Python, all positional parameters are declared **before** any keyword parameters.
- **Positional parameters may not have a default value**; defaults are a keyword-only feature.
- A positional parameter must be passed positionally, and a keyword parameter by name.

### Template definition (template)

`<template>` makes a function as a value.

```xml
<!-- no parameters -->
<template>expr</template>

<!-- positional parameter -->
<template>
    <param name="x" positional="true"/>
    body_expr
</template>

<!-- keyword parameters (defaults optional) -->
<template>
    <param name="arg1">default_expr</param>
    <param name="arg2"/>
    body_expr
</template>

<!-- mixed: positional first, then keyword -->
<template>
    <param name="x" positional="true"/>
    <param name="opt">default_expr</param>
    body_expr
</template>
```

### Template application (apply)

`<apply>` applies a template to arguments. An `<arg>` is **positional** without `name` and **keyword** with it; list all positional arguments first, then the keyword arguments.

```xml
<apply>
    expr                      <!-- the template to apply -->
    <arg>expr1</arg>          <!-- positional (matched in declaration order) -->
    <arg>expr2</arg>
    <arg name="opt">expr3</arg>  <!-- keyword argument -->
</apply>
```

When the function is a named variable, the `template` attribute avoids the inner `<var>` element:

```xml
<!-- shorthand -->
<apply template="funcname">
    <arg>expr1</arg>
</apply>

<!-- equivalent full form -->
<apply>
    <var name="funcname"/>
    <arg>expr1</arg>
</apply>
```

**Keyword arguments are passed all at once.** A template with keyword parameters receives them together, as one argument, after its positional ones. A keyword parameter left out of the call takes its default. But a call that passes no keyword argument at all leaves the template waiting for them: the result is still a function, and `pgsn doc` reports `a function is not a value; an argument may be missing`. An empty `<arg>` passes nothing and counts as the keyword argument: an empty `<arg name="x"/>` leaves `x` at its default, and an empty unnamed `<arg/>` lets every keyword parameter take its default. It comes after the positional arguments:

```xml
<apply template="f"><arg/></apply>                    <!-- every keyword parameter at its default -->
<apply template="f"><arg>expr1</arg><arg/></apply>    <!-- a positional argument, then the defaults -->
```

In an expression, `f(x)` on a template with keyword parameters is likewise still a function; write `f(x, k=…)`, or `f(x)()` to take the defaults.

An `<apply>` without any `<arg>` is the function itself: `<apply template="f"/>` and `<var name="f"/>` are the same.

---

## Classes and objects

### Class definition (class)

```xml
<class name="ClassName">                  <!-- what the class is called (optional) -->
    <!-- inherit accepts any expression that evaluates to a class.
         var= is the common shorthand for a variable reference. -->
    <inherit var="ParentClass"/>          <!-- inheritance (optional) -->
    <attribute name="attr1">default_value</attribute>
    <attribute name="attr2"/>             <!-- no default value -->
    <method name="m">
        <!-- 'self' refers to the receiver object and is always available in
             the method body without being declared as a param. -->
        <param name="p1">default</param>
        <param name="p2"/>
        body_expr   <!-- may use <var name="self"/> to access the receiver -->
    </method>
</class>
```

> **Note: a class's name is a label, not a way of referring to it.**
> Classes are ordinary values and there is no registry to look a name up in:
> `<inherit>` and `<instanceOf>` both accept **expressions that evaluate to a
> class**, not string literals. `<inherit>SomeClass</inherit>` is the string
> `"SomeClass"`, which is not a class — use `<inherit var="SomeClass"/>`
> (or any other expression) instead.
>
> What `name=` gives the class is what it is *called*: it travels with the
> value and is what an instance of the class is reported as, where the name a
> `<def>` introduces is a name in a scope. Nothing compares the two, and
> nothing compares one class's name with another's. A class may have no name,
> but then an instance of it cannot be printed or drawn, since there is
> nothing to report it as. The `as="class"` shorthand cannot carry attributes,
> so a named class is written in the long form:
> `<def name="C"><class name="C">…</class></def>`.

> **Note: a type is not a class.**
> `is_subtype` compares the attribute and method *names* two classes declare,
> and `inherit` plays no part in it. So a class satisfies every type whose
> labels it covers, related to it or not, and there is no way to ask which
> class a value belongs to — only what it carries. `<instanceOf>` inside
> `<object>` names the class to instantiate and is a different thing again.

### Objects (object)

```xml
<object>
    <instanceOf var="MyClass"/>
    <attribute name="attr1">value</attribute>
</object>
```

An `<object>` must give every attribute of the class that has no default, and no attribute the class does not declare. Otherwise the object has no value.

### Reading a label (get)

`<get>` reads a label of a record or an object. The `key` attribute names the label, and `of` names a variable holding the receiver. The three forms below are the same, since reading a label is applying the record to it:

```xml
<get key="x" of="my_record"/>
<get key="x"><var name="my_record"/></get>
<apply><var name="my_record"/><arg>x</arg></apply>
```

When the receiver is a complex expression, write it as the child element:

```xml
<get key="description"><apply template="getGoal"><arg>G1</arg></apply></get>
```

A record carries the labels it was built with, and reading a label it does not carry gives no value. The document then has no value at all, and `pgsn doc` reports the path at which evaluation stopped ([Principles](#principles)). A misspelled label therefore cannot pass on as a silent gap, which is what makes it safe for a template to read a record it did not build itself.

### Method invocation (send)

```xml
<send method="methodName" to="receiverVar">
    <arg name="arg1">expr1</arg>
</send>
```

The `method` attribute names the method; `to` names a variable holding the receiver. When the receiver is a complex expression rather than a plain variable, omit `to` and write the receiver as the first child element:

```xml
<send method="methodName">
    receiver_expr
    <arg name="arg1">expr1</arg>
</send>
```

### Extending GSN

The GSN classes can be extended through inheritance. Instantiate the extended class with `<object>`, listing the attributes the class gives no default (see [What each element takes](#what-each-element-takes) for the attributes of the GSN classes). The class is written in the long form, because a class that will be instantiated needs a name of its own and `as` cannot carry one.

```xml
<!-- a class inheriting Goal, adding a URL attribute -->
<def name="GoalWithURL">
    <class name="GoalWithURL">
        <inherit var="Goal"/>
        <attribute name="URL"/>
    </class>
</def>

<!-- instantiation -->
<object>
    <instanceOf var="GoalWithURL"/>
    <attribute name="description">System X is secure</attribute>
    <attribute name="URL">https://example.com/evidence</attribute>
    <attribute name="support" var="undeveloped"/>
</object>
```

---

## Documents and modules

`pgsn` accepts a document whose file name ends in `.xml`. Its root element is `<PGSN>` or `<PGSNModule>`.

### `<PGSN>` — a document with a value

A `<PGSN>` document has one value, which `pgsn doc` prints and `pgsn render` draws. It does **not** accept `<param>`.

```xml
<PGSN>
    <from file="..."/>         <!-- imports (zero or more) -->
    <def name="x">...</def>    <!-- definitions (zero or more) -->
    ...                        <!-- value (exactly one) -->
</PGSN>
```

### `<PGSNModule>` — a reusable module

A module has no value of its own: it provides definitions for other documents to import, and may take parameters from them. `<param>` elements come first.

```xml
<PGSNModule>
    <param name="p"/>          <!-- parameters (zero or more, must come first) -->
    <from file="..."/>         <!-- imports (zero or more) -->
    <def name="x">...</def>    <!-- definitions (zero or more) -->
</PGSNModule>
```

`<from>` and `<def>` elements may be freely interleaved in both forms. A module cannot be given to `pgsn doc` directly (`Expected <PGSN>, got <PGSNModule>`); import it from a `<PGSN>` document.

**A module is closed.** Every name it uses is one of its parameters, one it defines or imports, or a builtin, so it receives values from the document that imports it only through its parameters. A module that uses any other name is rejected when it is imported, with the name in the message. A `<PGSN>` document is not held to this: a name it leaves unbound stops the evaluation, as described under [Principles](#principles).

### Import (from)

`<from>` brings names defined in another file into scope. A document can only reach files it has been granted access to; see [Import paths and jails](#import-paths-and-jails).

```xml
<!-- one name, renamed -->
<from file="security.xml" import="secureGoal" as="G1"/>

<!-- several names -->
<from file="evidence.xml">
    <import name="auditEvidence"/>
    <import name="testReport" as="TR"/>
</from>

<!-- with parameters for the module -->
<from file="other.xml">
    <import name="someGoal" as="G2"/>
    <arg name="A1" var="A1"/>
    <arg name="threshold" var="threshold"/>
</from>
```

### The module as a value

A `<from>` written where a value is expected denotes the module's record, with nothing selected out of it. A module is then an ordinary value: bind it with `<def>`, hold it in a list, pass it to a template.

```xml
<def name="lib"><from file="security.xml"/></def>
<get key="secureGoal" of="lib"/>
```

Selecting a name at the point of import is what the forms above are for, so the two spellings do not mix: a `<from>` used as a value takes no `import`, and a `<from>` used as a binding needs one.

### Example

A module that takes a threshold and imports a goal from another file:

```xml
<PGSNModule>
    <!-- receive a threshold from the caller -->
    <param name="threshold">100</param>

    <!-- bring in a goal from another file -->
    <from file="security.xml" import="secureGoal" as="G1"/>

    <def name="mainStrategy" as="Strategy">
        verified through testing and review
        <subGoals>
            <ol>
                <li var="G1"/>
            </ol>
        </subGoals>
    </def>

    <def name="main" as="Goal">
        <description>the system is secure</description>
        <Assumption>no zero-day attacks</Assumption>
        <Assumption>at most {threshold} requests per second</Assumption>
        <supportedBy var="mainStrategy"/>
    </def>
</PGSNModule>
```

A `<PGSN>` document that imports `main` from it, with a threshold of its own, and has it as its value:

```xml
<PGSN>
    <from file="module.xml" import="main">
        <arg name="threshold"><num>5</num></arg>
    </from>
    <var name="main"/>
</PGSN>
```

### Import paths and jails

A document is confined to a directory tree, its *confinement root*, and `file` may only name a file inside it. There are two ways to write a path.

**Relative paths** are resolved against the directory of the document doing the importing:

```xml
<from file="modules/security.xml" import="secureGoal"/>
<from file="../shared/evidence.xml" import="auditEvidence"/>
```

`..` is permitted, but only as long as the result stays inside the confinement root. The root of a document opened directly by path is the registered jail that contains it, if there is one, and otherwise the directory the document lives in, so by default a document can reach its neighbors and their subdirectories, and nothing above them.

**Jailed paths** start with `/` and name a *jail* — a directory root registered by whoever runs PGSN:

```xml
<from file="/lib/security.xml" import="secureGoal"/>
```

Here `lib` is a jail name, not a directory on disk. It is resolved against the jail table supplied on the command line or through the API (replace `/opt/pgsn-lib` with an existing directory of shared modules):

```console
$ pgsn doc main.xml -o - --jail lib=/opt/pgsn-lib
```

```python
import pgsn

cfg = pgsn.Config(jails={"lib": "/opt/pgsn-lib"})
term = pgsn.load_xml("main.xml", config=cfg)
```

A document has no way to name a jail that was not registered, and no way to reach the real filesystem layout behind one. Jail names may contain only ASCII letters, digits, `_` and `-`.

Once an import crosses into a jail, that jail becomes the confinement root for the imported module. A module inside a jail may import its neighbors relatively, but cannot climb out with `..` — not even back into the tree of the document that imported it. Crossing from one jail to another always requires naming the target jail explicitly.

The following are rejected:

| Path | Reason |
|------|--------|
| `../../etc/passwd` | leaves the confinement root |
| `/etc/passwd` | `etc` is not a registered jail |
| `/lib/../secret.xml` | `..` is not allowed in a jailed path |
| `/lib/link.xml` where `link.xml` is a symlink out of the jail | resolves outside the jail root |
| `C:\lib\mod.xml` | backslashes are not allowed |

Symbolic links are expanded before the containment check, so a link planted inside a jail cannot be used to escape it.

---

## Builtins

The following names are predefined; refer to them with `<var name="..."/>` and apply them with `<apply>` or in an `<expr>`. Each, except the short class aliases, which exist only in XML, is the builtin term the `pgsn` Python package exports under the same name, and [README-api.md](README-api.md#builtin-terms) gives the arguments each takes. The Python functions that build terms (`string`, `lambda_abs`, `let`, …) and the loading functions have no XML counterpart, because the XML elements do their work.

| Kind | Names |
|---|---|
| Lists | `cons`, `head`, `tail`, `index`, `is_empty`, `concat`, `map_term`, `fold`, `foldr`, `list_all`, `empty` |
| Booleans | `true`, `false`, `if_then_else`, `boolean_and`, `boolean_or`, `boolean_not`, `equal`, `less_than`, `guard` |
| Integers | `plus`, `minus`, `times`, `div`, `mod`, `integer_sum`, `repeat` |
| Records | `has_label`, `add_attribute`, `remove_attribute`, `overwrite_record`, `empty_record` |
| Strings | `format_string` |
| Classes and objects | `define_class`, `instantiate`, `type_of`, `is_subtype`, `base_class` |
| Other | `fix`, `undefined` |
| GSN constructors | `goal`, `strategy`, `solution`, `context`, `assumption`, `defeater`, `undeveloped`, `immediate`, `solution_as_goal` |
| GSN classes | `goal_class`, `strategy_class`, `solution_class`, `context_class`, `assumption_class`, `defeater_class`, `gsn_class`, `support_class`, `undeveloped_class` |
| GSN classes, short aliases | `Goal`, `Strategy`, `Solution`, `Context`, `Assumption`, `Defeater`, `GSN`, `Support` |

Example (mapping a template over a list):

```xml
<apply>
    <var name="map_term"/>
    <arg var="someTemplate"/>                 <!-- first argument: the template -->
    <arg><ol><li>a</li><li>b</li></ol></arg>  <!-- second argument: the list -->
</apply>
```

---

## Principles

Five properties hold everywhere in the language; the sections above describe the syntax that expresses them.

**Everything is a value.** A Goal, a Strategy, a Solution, a class, a template — each is a value like a string or a list, and can be bound to a name, held in a list, passed to a template or returned from one. Wherever an element takes content, it takes an expression.

**Nothing changes.** A `<def>` binds a name for the scope that follows it and never changes what an earlier binding meant; binding the same name again shadows it rather than assigns to it. A document therefore has one value, and has the same value however many times it is evaluated.

**A missing value is reported where it is needed, not where it occurs.** Reading a name that is not defined, a record label that does not exist, or a value that fails a `typeOf` check is not an error at that point: the part of the argument that depends on it simply has no value. When `pgsn doc` or `pgsn render` needs that value to print or draw the argument, it reports an error with the path to the place where the value is missing, for example

    Error: PGSN term cannot be converted to a Python value at path '<root>.support': name 's' is not defined. Term (first 200 chars): …

A template that has not been given all its arguments is not a value either, and is reported the same way. A part that nothing needs is never evaluated, so a mistake in it goes unreported. Malformed XML and refused imports are different: they are reported as soon as the document is read.

**The only way out is `import`, and it is confined.** A document reads no file, reaches no network and consults no clock. Its one connection to anything outside itself is `<from>`, which may name only a file inside the directory tree the document is confined to, or inside a jail registered by whoever ran PGSN. See [Import paths and jails](#import-paths-and-jails). Confinement concerns what a document can reach, not what it consumes: PGSN does not limit the memory or the time a document uses, so run a document you did not write in a virtual machine or a container that limits them.

**Only data can be compared.** Equality compares base values — strings, integers, booleans, `undefined` — and the lists and records built out of them. Two functions, two classes or two GSN elements have no value when compared. A value carries no address and no timestamp, so a copy cannot be told apart from the original, and neither can two elements written with the same description. See [Comparing values](#comparing-values).

---

## Elements at a glance

The attribute column lists each element's own attributes. Any element with content also takes the [shorthand attributes](#shorthand-attributes) `var`, `expr` and `as`.

| Element | Content | Attributes | Section |
|---|---|---|---|
| `<PGSN>` | `<from>` and `<def>`, then one value | – | [Documents and modules](#documents-and-modules) |
| `<PGSNModule>` | `<param>`, then `<from>` and `<def>` | – | [Documents and modules](#documents-and-modules) |
| `<from>` | `<import>` and `<arg>`, or nothing | `file`, `import`, `as` | [Import](#import-from) |
| `<import>` | empty | `name`, `as` | [Import](#import-from) |
| `<def>` | one value | `name`, `typeOf`, `recursive` | [Definitions](#definitions-def) |
| `<var>` | empty | `name`, `typeOf` | [Variables](#variables-var) |
| `<div>` | `<from>` and `<def>`, then one value | – | [Local definitions](#local-definitions) |
| `<num>` | a decimal integer | – | [Literals](#literals) |
| `<str>` | text, taken as written | – | [Literals](#literals) |
| `<expr>` | an expression | – | [Expressions](#expressions-expr) |
| `<ol>` | `<li>` | – | [Lists](#lists-ol) |
| `<li>` | one value | – | [Lists](#lists-ol) |
| `<dl>` | `<dt>` and `<dd>` in pairs | – | [Records](#records-dl) |
| `<dt>` | the label as text, or empty | `key` | [Records](#records-dl) |
| `<dd>` | one value | – | [Records](#records-dl) |
| `<if>` | `<cond>`, `<then>`, `<else>` | – | [Conditionals](#conditionals-if-cases) |
| `<cases>` | `<case>`, then `<else>` | – | [Conditionals](#conditionals-if-cases) |
| `<case>` | `<cond>`, `<then>` | – | [Conditionals](#conditionals-if-cases) |
| `<cond>`, `<then>`, `<else>` | one value | – | [Conditionals](#conditionals-if-cases) |
| `<template>` | `<param>`, then `<from>` and `<def>`, then one value | – | [Template definition](#template-definition-template) |
| `<param>` | a default value, or empty | `name`, `positional` | [Parameters](#parameters-param) |
| `<apply>` | the function (or `template=`), then `<arg>` | `template` | [Template application](#template-application-apply) |
| `<arg>` | one value, or empty | `name` | [Template application](#template-application-apply) |
| `<class>` | `<inherit>`, `<attribute>`, `<method>` | `name` | [Class definition](#class-definition-class) |
| `<inherit>` | a class | – | [Class definition](#class-definition-class) |
| `<attribute>` | a default value or an attribute's value, or empty | `name` | [Class definition](#class-definition-class), [Objects](#objects-object) |
| `<method>` | `<param>`, then `<from>` and `<def>`, then one value | `name` | [Class definition](#class-definition-class) |
| `<object>` | `<instanceOf>`, then `<attribute>` | – | [Objects](#objects-object) |
| `<instanceOf>` | a class | – | [Objects](#objects-object) |
| `<get>` | the receiver (or `of=`) | `key`, `of` | [Reading a label](#reading-a-label-get) |
| `<send>` | the receiver (or `to=`), then `<arg>` | `method`, `to` | [Method invocation](#method-invocation-send) |
| `<Goal>` | description, `<Context>`, `<Assumption>`, `<Defeater>`, one support | – | [Goal](#goal) |
| `<Strategy>` | description, `<Context>`, `<Assumption>`, `<Defeater>`, sub-goals | – | [Strategy](#strategy) |
| `<Solution>` | description, `<Defeater>` | – | [Solution](#solution) |
| `<Defeater>` | description, `<Defeater>`, an optional support | – | [Defeater](#defeater) |
| `<Context>`, `<Assumption>` | one value | – | [Context and Assumption](#context-and-assumption) |
| `<description>` | one value | – | [Descriptions](#descriptions) |
| `<supportedBy>` | a support | – | [Goal](#goal) |
| `<subGoals>` | a list of goals | – | [Strategy](#strategy) |
| `<undeveloped/>` | empty | – | [Goal](#goal), [Strategy](#strategy) |
