# PGSN — Programmable Goal Structuring Notation

PGSN is an XML-based language that extends GSN (Goal Structuring Notation) with programming constructs.
GSN nodes (Goal, Strategy, Evidence) are treated as first-class values and can be combined with variables, templates, and classes.

---

## Document Structure

PGSN has two root elements: `<PGSN>` for standalone documents and `<PGSNModule>` for reusable modules.

### `<PGSN>` — standalone document

Produces a single value. Does **not** accept `<param>`.

```xml
<PGSN>
    <from file="..."/>         <!-- imports (zero or more) -->
    <def name="x">...</def>    <!-- definitions (zero or more) -->
    ...                        <!-- value (exactly one) -->
</PGSN>
```

### `<PGSNModule>` — reusable module

Accepts parameters from the caller. `<param>` must appear first.

```xml
<PGSNModule>
    <param name="p"/>          <!-- parameters (zero or more, must come first) -->
    <from file="..."/>         <!-- imports (zero or more) -->
    <def name="x">...</def>    <!-- definitions (zero or more) -->
</PGSNModule>
```

`import` and `def` elements may be freely interleaved within both forms.

---

## Values

In PGSN, **everything is a value**. Every element that accepts content expects an **expression** — something that evaluates to a value. There are no special "name slots" or "class name strings" built into the language.

> **Key principle: bare text becomes a String literal.**
> When you write text directly inside an element, it is parsed as a `String` value.
> `<inherit>Goal</inherit>` does not refer to the Goal class — it produces the
> string `"Goal"`, which is not a class. To refer to a variable, use `<var>` or
> the `var=` shorthand attribute.

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
| bare text | a `String`. Leading and trailing whitespace is removed, and `{name}` fields are interpolated — see [Format Strings in Text](#format-strings-in-text) |
| `<num>3</num>` | an `Integer`. PGSN has no floating point numbers |
| `<str> a {b} </str>` | a `String`, taken exactly as written: whitespace is kept and `{...}` is not interpolated |

`<num>` matters because bare text stays a string even when it looks like a number, which is what lets a goal say `2024 audit passed` without the year turning into an integer. The arithmetic builtins only accept integers, so `<arg>3</arg>` gives them a string and leaves the term unreduced; write `<arg><num>3</num></arg>`.

The builtins are ordinary bindings in the outermost scope, so `<var name="plus"/>` reaches the builtin unless something nearer binds that name.

### Expressions (expr)

Writing arithmetic with `<apply>` is heavy, so `<expr>` accepts the usual infix notation:

```xml
<def name="next"><expr>i + 1</expr></def>
<def name="label"><expr>f"component {i} of {total}"</expr></def>
```

`<expr>` is a shorthand and nothing more. It is expanded before compilation begins into an application of the corresponding builtin, so nothing is reachable through an expression that is not reachable without one.

**What may appear in an expression**

| | |
|---|---|
| literals | `3`, `"text"`, `True`, `False` |
| variables | `i` — becomes `<var name="i"/>` |
| arithmetic | `+`, `-`, `*`, `//`, `%`, and unary `-` |
| comparison | `==`, `!=`, `<`, `<=`, `>`, `>=` |
| boolean | `and`, `or`, `not` |
| f-strings | `f"component {i} of {total}"`, including format specifications such as `{i:>3}` |

Everything else is rejected with an error naming what was found. There are no function calls, no attribute access and no subscripting: use `<apply>`, `<get>` and the list elements, which state plainly what they do.

**Three things to know**

`<` must be escaped in XML. Write `i &lt; n`, or wrap the expression in `CDATA`:

```xml
<expr>i &lt; n</expr>
<expr><![CDATA[i < n]]></expr>
```

`>` needs no escaping, so `n > i` is often the easier way to say the same thing.

`//` is integer division: `7 // 2` is `3`. `/` is rejected rather than treated as a synonym, so that it stays available for true division if PGSN ever gains a floating point type.

Ordering compares integers only. `"a" < "b"` does not reduce; equality, however, works on any value, so `"a" == "a"` is `True`.

**Operators cannot be redefined.** `1 + 2` is addition even inside a scope that binds the name `plus`.

### Names

A *name* is what `<def>` and `<param>` introduce and what `<var>` refers to. The same rule applies to every attribute that holds one: `name` on `<def>`, `<param>` and `<var>`, `typeOf` on `<def>` and `<var>`, `as` on `<from>` and `<import>`, `template` on `<apply>`, `of` on `<get>`, `to` on `<send>`, `name` on `<arg>`, and the `var` shorthand attribute.

A name must begin with a letter and may continue with letters, digits and underscores. Letters are not restricted to ASCII, so `ゴール` is a name. A name may **not** begin with an underscore; those are reserved by the implementation.

The rule is the same one Python uses for identifiers, and deliberately so: an [expression](#expressions-expr) is parsed by Python's parser, so a name that could not appear in an expression would be unreachable from one.

Record labels are a different namespace and are unrestricted: `name` on `<get>` and `<send>`, `name` on `<attribute>`, and `key` on `<dt>` are arbitrary strings.

### Conditionals (if, cases)

`if_then_else` is a builtin and can be applied like any other, but a two-way choice written that way is hard to read. `<if>` says the same thing with the parts named:

```xml
<if>
    <cond expr="i &lt; threshold"/>
    <then>within budget</then>
    <else>over budget</else>
</if>
```

`<else>` is required. The branch not taken is not evaluated, so a conditional can guard a recursion.

For a chain of conditions, `<cases>` takes the first `<case>` whose `<cond>` holds, and falls back to `<else>`:

```xml
<cases>
    <case><cond expr="severity == 0"/><then>negligible</then></case>
    <case><cond expr="severity &lt; 3"/><then>tolerable</then></case>
    <else>unacceptable</else>
</cases>
```

`<else>` is required here too. Without one, a `<cases>` that matched nothing would produce a term that simply gets stuck, and the mistake would surface far from where it was made.

Each of `<cond>`, `<then>` and `<else>` is a wrapper holding a value, so any of the ways of writing a value work inside one, including the `var` and `expr` shorthands.

Both forms are shorthands, expanded before compilation into an application of the `if_then_else` builtin, and both reach it in a way no binding can intercept — `<if>` means a conditional even in a scope that binds the name `if_then_else`.

### Shorthand for Expressions

Where an element's content is a single expression, the `expr` attribute says the same thing as an `<expr>` child. Like `var`, it is expanded by the preprocessor, so the two spellings are the same thing written two ways.

```xml
<!-- full form -->
<arg><expr>i + 1</expr></arg>

<!-- shorthand -->
<arg expr="i + 1"/>
```

An element may not carry both the attribute and content of its own. Two details of XML are worth remembering: `<` must be written `&lt;` inside an attribute value, and an f-string needs the attribute quoted with `'` so that its own `"` survive.

```xml
<def name="label" expr='f"component {i}"'/>
<li expr="i &lt; n"/>
```

### Shorthand for Variable References

When an element's content is a single variable reference, the `var` attribute can be used as shorthand.
This is expanded by a preprocessor before evaluation.

```xml
<!-- full form -->
<tag><var name="x"/></tag>

<!-- shorthand -->
<tag var="x"/>
```

---

## Parameters (param)

`param` declares variables that a `<PGSNModule>` receives from the caller.
Parameters are only valid inside `<PGSNModule>` and must appear before any `<from>` or `<def>` elements.

```xml
<param name="A1"/>

<!-- with a default value -->
<param name="threshold">100</param>
```

---

## Import (from)

Brings names from external PGSN files into scope. A document can only reach files it has been granted access to; see [Import paths and jails](#import-paths-and-jails) below.

### Single import

```xml
<from file="security.pgsn" import="secureGoal" as="G1"/>
```

### Multiple imports

```xml
<from file="evidence.pgsn">
    <import name="auditEvidence"/>
    <import name="testReport" as="TR"/>
</from>
```

### Import with parameters

```xml
<from file="other.pgsn">
    <import name="someGoal" as="G2"/>
    <arg name="A1" var="A1"/>
    <arg name="threshold" var="threshold"/>
</from>
```

### The module itself

A `<from>` written where a value is expected denotes the module's record, with nothing selected out of it. A module is then an ordinary value: bind it with `<def>`, hold it in a list, pass it to a template.

```xml
<def name="lib"><from file="security.pgsn"/></def>
<get label="secureGoal" of="lib"/>
```

Selecting a name at the point of import is what the forms above are for, so the two spellings do not mix: a `<from>` used as a value takes no `import`, and a `<from>` used as a binding needs one.

### Import paths and jails

A document is confined to a directory tree, and `file` may only name a file inside it. There are two ways to write a path.

**Relative paths** are resolved against the directory of the document doing the importing:

```xml
<from file="modules/security.pgsn" import="secureGoal"/>
<from file="../shared/evidence.pgsn" import="auditEvidence"/>
```

`..` is permitted, but only as long as the result stays inside the confinement root. The root of a document opened directly by path is the directory that document lives in, so by default a document can reach its neighbours and their subdirectories, and nothing above them.

**Jailed paths** start with `/` and name a *jail* — a directory root registered by whoever runs PGSN:

```xml
<from file="/lib/security.pgsn" import="secureGoal"/>
```

Here `lib` is a jail name, not a directory on disk. It is resolved against the jail table supplied on the command line or through the API:

```console
$ pgsn doc main.xml --jail lib=/opt/pgsn-lib
```

```python
import pgsn

cfg = pgsn.Config(jails={"lib": "/opt/pgsn-lib"})
term = pgsn.load_xml("main.xml", config=cfg)
```

A document has no way to name a jail that was not registered, and no way to reach the real filesystem layout behind one. Jail names may contain letters, digits, `_` and `-` only.

Once an import crosses into a jail, that jail becomes the confinement root for the imported module. A module inside a jail may import its neighbours relatively, but cannot climb out with `..` — not even back into the tree of the document that imported it. Crossing from one jail to another always requires naming the target jail explicitly.

The following are rejected:

| Path | Reason |
|------|--------|
| `../../etc/passwd` | leaves the confinement root |
| `/etc/passwd` | `etc` is not a registered jail |
| `/lib/../secret.pgsn` | `..` is not allowed in a jailed path |
| `/lib/link.pgsn` where `link.pgsn` is a symlink out of the jail | resolves outside the jail root |
| `C:\lib\mod.pgsn` | absolute paths must name a jail |

Symbolic links are expanded before the containment check, so a link planted inside a jail cannot be used to escape it.

---

## Definitions (def)

`def` binds a name to a value.

A name may be bound more than once in the same block; a later binding shadows an earlier one from that point on. Nothing is mutated — the earlier binding still holds wherever it was already visible — so this is shadowing, not assignment. In particular a binding's own value is read in the scope *before* it, which means `<def name="x"><var name="x"/></def>` refers to the outer `x` rather than to itself; use `recursive="true"` for self-reference.

The builtin names are bound the same way, in the outermost scope, so a document is free to bind `head` or `goal` to something of its own.

```xml
<def name="x">expr</def>
```

### `as` Attribute (Shorthand)

The `as` attribute on `def` lets you omit the wrapping element type (tag name).
This is also expanded by the preprocessor before compilation.

```xml
<!-- full form -->
<def name="myGoal"><Goal>...</Goal></def>

<!-- shorthand -->
<def name="myGoal" as="Goal">...</def>
```

`<def name="x" as="T">C</def>` is purely syntactic: the preprocessor rewrites it to `<def name="x"><T>C</T></def>` before compilation. Any tag name that is valid in that position can be used — including user-defined class instantiation tags like `object`. The only restriction is that tags requiring a mandatory attribute of their own (such as `var`, `get`, and `send`, which require `name=`) cannot be used, because the desugared form would be missing that attribute.

### `typeOf` Attribute

Checks a value against a type. `<def>` and `<var>` both take it; the attribute
value is a **variable name** bound to a class.

```xml
<def name="g" typeOf="Goal">
    <Goal><description>system is safe</description><undeveloped/></Goal>
</def>

<var name="g" typeOf="Goal"/>
```

**Typing is structural.** A value satisfies a type when its class declares at
least the attributes and methods the type declares. Where the class came from
does not enter into it: a class of your own that carries `description` and
`defeaters` satisfies `Evidence` without inheriting from it, and a `Goal`
satisfies `Evidence` too, since it declares those labels and more. Nothing
compares class *identities*, which is what makes the answer independent of
how far evaluation has gone.

A check that fails does not raise. The guard behind it simply does not
reduce, so the document stalls and the readback reports the path.

`<param>` does not take `typeOf`: a parameter is bound by a lambda, and a
guard on it would have to be planted in the body. Check the value where it is
used instead.

### Local Definitions

Use `<def>` elements inside a `<div>` to scope definitions locally.

```xml
<div>
    <def name="x">expr1</def>
    <def name="y">expr2</def>
    expr   <!-- the value of the div -->
</div>
```

`<def>` elements can also appear directly inside a `<template>` body, before the final value expression. This avoids the need for a wrapping `<div>`.

```xml
<template>
    <param name="x"/>
    <def name="doubled"><apply><var name="plus"/><arg var="x"/><arg var="x"/></apply></def>
    <var name="doubled"/>   <!-- final value -->
</template>
```

### Local Definitions (div)

Use `div` to scope definitions locally.

```xml
<div>
    <def name="x">expr1</def>
    <def name="y">expr2</def>
    expr   <!-- the value of the div -->
</div>
```

---

## Variables (var)

References a previously defined name.

```xml
<var name="x"/>

<!-- with a type check -->
<var name="x" typeOf="MyClass"/>
```

### Built-ins

The following names are predefined; reference them with `<var name="..."/>` and apply them via `apply`. They are exactly the term-valued names exported by the `pgsn` Python package, so anything usable from Python is usable here under the same name.

- List operations: `cons`, `head`, `tail`, `index`, `concat`, `map_term`, `fold`, `foldr`, `list_all`, `empty`
- Booleans: `true`, `false`, `if_then_else`, `boolean_and`, `boolean_or`, `boolean_not`, `equal`, `less_than`, `guard`
- Integers: `plus`, `minus`, `times`, `div`, `mod`, `integer_sum`
- Records: `has_label`, `list_labels`, `add_attribute`, `remove_attribute`, `overwrite_record`, `empty_record`
- Strings: `format_string`
- Classes / objects: `define_class`, `instantiate`, `type_of`, `is_subtype`, `base_class`
- Misc: `fix`, `repeat`, `undefined`
- GSN constructors: `goal`, `strategy`, `evidence`, `context`, `assumption`, `defeater`, `undeveloped`, `immediate`, `evidence_as_goal`
- GSN classes (long form): `goal_class`, `strategy_class`, `evidence_class`, `context_class`, `assumption_class`, `defeater_class`, `gsn_class`, `support_class`, `undeveloped_class`
- GSN classes (short aliases): `Goal`, `Strategy`, `Evidence`, `Context`, `Assumption`, `Defeater`, `GSN`, `Support`

Example (mapping a template over a list):

```xml
<apply>
    <var name="map_term"/>
    <arg var="someTemplate"/>     <!-- first argument (the template) -->
    <arg><ol><li>a</li><li>b</li></ol></arg>  <!-- second argument (the list) -->
</apply>
```

---

## Templates and Application

### Template Definition (template)

Defines a function as a value (equivalent to a lambda expression).
Parameters (`param`) come in two kinds: **positional** and **keyword**.

- A `param` marked `positional="true"` is **positional**.
- A `param` without it is a **keyword** parameter.
- As in Python, all positional parameters are declared **before** any keyword parameters (a positional parameter may not follow a keyword parameter).
- **Positional parameters may not have a default value** (defaults are a keyword-only feature).
- A given parameter is not meant to be passed both positionally and by keyword; each parameter is fixed to one kind at declaration time.

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

### Template Application (apply)

Applies a template to arguments.
`arg` elements come as **positional** (no `name`) and **keyword** (with `name`); list all positional arguments first, then the keyword arguments.

```xml
<apply>
    expr                      <!-- the template to apply -->
    <arg>expr1</arg>          <!-- positional (interpreted by declaration order) -->
    <arg>expr2</arg>
    <arg name="opt">expr3</arg>  <!-- keyword argument -->
</apply>
```

When the function is a named variable, the `template` attribute provides a shorthand that avoids the inner `<var>` element:

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

---

## Classes and Objects

### Class Definition (class)

```xml
<class>
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

> **Note: PGSN has no class names.**
> Classes are ordinary values; there is no registry of named classes.
> `<inherit>` and `<instanceOf>` both accept **expressions that evaluate to a
> class**, not string literals.
> Writing `<inherit>SomeClass</inherit>` is a text node and becomes
> `"SomeClass"` as a string value, which is not a class — use `<inherit var="someClass"/>`
> (or any other expression) instead.

> **Note: a type is not a class.**
> `is_subtype` compares the attribute and method *names* two classes declare,
> and `inherit` plays no part in it. So a class satisfies every type whose
> labels it covers, related to it or not, and asking which class a value
> belongs to has no answer — only asking what it carries does. The predicates
> that did compare classes, `is_instance` and `is_subclass`, are gone: class
> equality was structural, so two copies of one class compared unequal once
> evaluation had reduced them to different degrees. `<instanceOf>` inside
> `<object>` names the class to instantiate and is a different thing again.

### Object Instantiation (object)

```xml
<object>
    <instanceOf var="MyClass"/>
    <attribute name="attr1">value</attribute>
</object>
```

### Key Access (get)

`get` works on both `Record` and `PGSNObject`. The `label` attribute names the key; `of` is a shorthand for a variable receiver. Internally it applies the receiver to the string key as a positional argument, so it is completely equivalent to an `apply` with a plain-text `arg`.

```xml
<!-- shorthand: label= names the key, of= names the receiver variable -->
<get label="description" of="my_goal"/>

<!-- when the receiver is a complex expression, use a child element -->
<get label="description"><apply template="getGoal"/></get>

<!-- Record key access — all three forms are equivalent -->
<get label="x" of="my_record"/>
<get label="x"><var name="my_record"/></get>
<apply><var name="my_record"/><arg>x</arg></apply>
```

### Method Invocation (send)

```xml
<send method="methodName" to="receiverVar">
    <arg name="arg1">expr1</arg>
</send>
```

The `method` attribute names the method; `to` is a shorthand for a variable receiver.
When the receiver is a complex expression rather than a plain variable, omit `to` and write the receiver as the first child element:

```xml
<send method="methodName">
    receiver_expr
    <arg name="arg1">expr1</arg>
</send>
```

---

## Data Types

### Set (ul) and List (ol)

```xml
<ul>
    <li>expr1</li>
    <li var="x"/>    <!-- shorthand -->
</ul>

<ol>
    <li>expr1</li>
    <li>expr2</li>
</ol>
```

`ul` and `ol` are structurally identical in XML, but use `ol` when order matters (e.g. a list passed to `map_term`).

### Dictionary (dl)

Keys can be arbitrary expressions or string literals via the `key` attribute.

```xml
<dl>
    <dt>key_expr</dt><dd>value_expr</dd>   <!-- expression key -->
    <dt key="name"/><dd>value_expr</dd>    <!-- string key -->
</dl>
```

### Format Strings in Text

Wherever text is allowed, you can embed in-scope variables with the `{name}` notation.
This is expanded by the preprocessor into a `format_string` application. To write a literal brace, escape it as `{{` or `}}`.

```xml
<template>
    <param name="c" positional="true"/>
    <Evidence>Test result for component {c}</Evidence>
</template>
```

### GSN Leading Text as Description

For GSN header elements (`Goal`, `Strategy`, `Evidence`, `Context`, `Assumption`), leading plain text is automatically treated as the `description`. When the element also has child elements (such as a nested `<Strategy>`), the text is lifted into a `<description>` element by the preprocessor. `{name}` expansion applies here too.

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

A header with no leading text takes a single value child as its description, so a computed description needs no `<description>` wrapper:

```xml
<Evidence><expr>f"test report {i}"</expr></Evidence>
```

A header carrying more than one value child is an error; say which one is the description by writing it out.

---

## GSN Nodes

GSN nodes are first-class values in PGSN and can be extended through class inheritance.

### Common Header (gsn_header)

Goal, Strategy, and Evidence all share the same header structure.

```xml
<!-- description: either a description element or plain text -->
<description>description text</description>

<!-- Context: the setting in which the argument holds.
     Accepts any expression as a value. -->
<Context>textual description</Context>
<Context var="someObject"/>                            <!-- variable reference -->
<Context><get label="version">expr</get></Context>      <!-- expression -->

<!-- Assumption: an assumption the argument relies on.
     Like Context, accepts any expression as a value. -->
<Assumption>no zero-day attacks</Assumption>
<Assumption var="someObject"/>                         <!-- variable reference -->
```

**Context vs Assumption**

`Context` and `Assumption` are both documentation elements attached to the header; each holds a single value (text, a variable reference, an object, a list, and so on).

- `Context` describes the setting or subject matter in which the argument is made.
- `Assumption` states an assumption the argument relies on.

### Goal

```xml
<Goal>
    <description>System X is secure</description>
    <Context>certified under standard XXXX</Context>
    <Assumption>no zero-day attacks</Assumption>

    <!-- body: exactly one of the following -->
    <Strategy>...</Strategy>              <!-- supported by a Strategy -->
    <Evidence>...</Evidence>              <!-- supported by Evidence -->
    <Goal>...</Goal>                      <!-- supported by sub-goals (one or more) -->
    <supportedBy var="strategy1"/>        <!-- supported by a variable reference -->
    <undeveloped/>                        <!-- not yet developed -->
</Goal>
```

> **Note: writing sub-goals directly is sugar**
> Listing several `<Goal>` elements directly under a Goal is expanded by the preprocessor into a wrap by `immediate` (a special Strategy that bundles sub-goals).
> In the PGSN core, a Goal's support must be either a Strategy or Evidence.
> To support a Goal with a list of goals computed at runtime, apply `immediate` explicitly to turn it into a Strategy.
>
> ```xml
> <Goal>
>     Security requirements fulfilled
>     <supportedBy>
>         <apply><var name="immediate"/><arg var="goals"/></apply>
>     </supportedBy>
> </Goal>
> ```

### Strategy

```xml
<Strategy>
    argument
    <!-- body: exactly one of the following -->
    <Goal>...</Goal>           <!-- sub-goals (one or more) -->
    <subGoals var="goals"/>    <!-- sub-goals via variable reference -->
</Strategy>
```

A set (`ul`) or list (`ol`) can be passed to `subGoals` to specify sub-goals dynamically.

```xml
<Strategy>
    argument
    <subGoals>
        <ul>
            <li var="goal1"/>
            <li var="goal2"/>
        </ul>
    </subGoals>
</Strategy>
```

### Evidence

```xml
<Evidence>
    <description>test result report</description>
    <Context>description of the test environment</Context>
</Evidence>
```

### Defeaters

GSN v3 adds a dialectic extension: a *defeater* records a doubt about part of an argument rather than support for it. Any GSN node can hold defeaters, and a defeater is itself a GSN node, so it can be challenged in turn.

```xml
<Goal>the system is safe
    <Defeater>hazard H4 is unmitigated
        <Evidence>incident report 2026-03</Evidence>
    </Defeater>
    <Defeater>the test suite is out of date
        <Defeater>it was refreshed in revision 7</Defeater>
    </Defeater>
    <Evidence>test report</Evidence>
</Goal>
```

A `<Defeater>` is written like any other GSN node: leading text or a `<description>` gives the description, a nested `<Evidence>`, `<Strategy>`, `<Goal>` or `<supportedBy>` gives its support, and nested `<Defeater>` elements challenge it. Support is optional and defaults to undeveloped: a defeater that argues its case fills it in, one that merely states an objection leaves it out.

Defeaters attach to strategies and to evidence as well as to goals:

```xml
<Strategy>argue over each hazard
    <Defeater>the hazard list is incomplete</Defeater>
    <Goal>H1 is mitigated<Evidence>report H1</Evidence></Goal>
</Strategy>
```

The corresponding builtin is `defeater`, with the class value `defeater_class`. In a rendered graph a defeater is drawn as a hexagon with a broken outline, and the challenge is drawn with a dashed arrow, so that it does not read as SupportedBy.

The standard has no Defeater element of its own: a defeater there is an ordinary Goal or Solution joined to its target by a Challenges relationship, and the literature's rebutting/undercutting distinction is read off the argument rather than off the notation. PGSN makes the challenging role a class instead, because a term language has no edges to carry a relationship. One class covers both kinds.

---

## Extending GSN via Classes

GSN nodes can be extended through class inheritance.
Instantiate the extended class with `<object>` (listing its attributes explicitly).

```xml
<!-- a class inheriting Goal, adding a URL attribute -->
<def name="GoalWithURL" as="class">
    <inherit var="Goal"/>
    <attribute name="URL"/>
</def>

<!-- instantiation (object form) -->
<object>
    <instanceOf var="GoalWithURL"/>
    <attribute name="description">System X is secure</attribute>
    <attribute name="URL">https://example.com/evidence</attribute>
    <attribute name="support" var="undeveloped"/>
</object>
```


---

## Module Example

A complete example combining parameters and imports.

```xml
<PGSNModule>
    <!-- receive a threshold from the caller -->
    <param name="threshold">100</param>

    <!-- bring in a goal from another file -->
    <from file="security.pgsn" import="secureGoal" as="G1"/>

    <def name="mainStrategy" as="Strategy">
        verified through testing and review
        <subGoals>
            <ul>
                <li var="G1"/>
            </ul>
        </subGoals>
    </def>

    <def name="main" as="Goal">
        <description>the system is secure</description>
        <Assumption>no zero-day attacks</Assumption>
        <supportedBy var="mainStrategy"/>
    </def>
</PGSNModule>
```

A module that receives `param` values uses `<PGSNModule>` rather than `<PGSN>` (which ends with a single value); `param` may appear only at the top of `<PGSNModule>`.