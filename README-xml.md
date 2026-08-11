# PGSN — Programmable Goal Structuring Notation

PGSN is an XML-based language that extends GSN (Goal Structuring Notation) with programming constructs.
GSN nodes (Goal, Strategy, Evidence) are treated as first-class values and can be combined with variables, templates, and classes.

## Table of Contents

1. [Document Structure](#1-document-structure)
2. [Values, Variables, and Definitions](#2-values-variables-and-definitions)
   - [2.1 Everything Is a Value](#21-everything-is-a-value)
   - [2.2 Variable References and the `var=` Shorthand](#22-variable-references-and-the-var-shorthand)
   - [2.3 Definitions (`def`)](#23-definitions-def)
   - [2.4 Local Scope (`div`)](#24-local-scope-div)
   - [2.5 Runtime Type Checks (`instanceOf`)](#25-runtime-type-checks-instanceof)
3. [Data Types](#3-data-types)
   - [3.1 Integers, Strings, and Booleans](#31-integers-strings-and-booleans)
   - [3.2 Set and List (`ul`, `ol`)](#32-set-and-list-ul-ol)
   - [3.3 Record (`dl`)](#33-record-dl)
4. [Expressions and Control Flow](#4-expressions-and-control-flow)
   - [4.1 Format Strings in Text](#41-format-strings-in-text)
   - [4.2 The `<expr>` Element](#42-the-expr-element)
   - [4.3 Conditionals (`if`)](#43-conditionals-if)
   - [4.4 Multi-way Conditionals (`cases`)](#44-multi-way-conditionals-cases)
5. [Templates and Application](#5-templates-and-application)
   - [5.1 Template Definition (`template`)](#51-template-definition-template)
   - [5.2 Template Application (`apply`)](#52-template-application-apply)
6. [Classes and Objects](#6-classes-and-objects)
   - [6.1 Class Definition (`class`)](#61-class-definition-class)
   - [6.2 Object Instantiation (`object`)](#62-object-instantiation-object)
   - [6.3 Key Access (`get`)](#63-key-access-get)
   - [6.4 Method Invocation (`send`)](#64-method-invocation-send)
7. [GSN Nodes](#7-gsn-nodes)
   - [7.1 Common Header (`gsn_header`)](#71-common-header-gsn_header)
   - [7.2 GSN Leading Text as Description](#72-gsn-leading-text-as-description)
   - [7.3 Goal](#73-goal)
   - [7.4 Strategy](#74-strategy)
   - [7.5 Evidence](#75-evidence)
8. [Extending GSN via Classes](#8-extending-gsn-via-classes)
9. [Modules, Parameters, and Imports](#9-modules-parameters-and-imports)
   - [9.1 `<PGSNModule>`](#91-pgsnmodule)
   - [9.2 Parameters (`param`)](#92-parameters-param)
   - [9.3 Import (`from`)](#93-import-from)
10. [Module Example](#10-module-example)
- [Appendix: Built-in Reference](#appendix-built-in-reference)

---

## 1. Document Structure

A PGSN document is a single `<PGSN>` element: zero or more `<def>` (and `<from>` import) elements, followed by exactly one value expression — the result of the whole document.

```xml
<PGSN>
    <from file="..."/>         <!-- imports (zero or more) -->
    <def name="x">...</def>    <!-- definitions (zero or more) -->
    ...                        <!-- value (exactly one) -->
</PGSN>
```

`<from>` and `<def>` elements may be freely interleaved with each other, but must all come before the final value.

> Reusable modules that accept parameters from a caller use `<PGSNModule>` instead of `<PGSN>`. See [9. Modules, Parameters, and Imports](#9-modules-parameters-and-imports).

---

## 2. Values, Variables, and Definitions

### 2.1 Everything Is a Value

In PGSN, **everything is a value**. Every element that accepts content expects an **expression** — something that evaluates to a value. There are no special "name slots" or "class name strings" built into the language.

> **Key principle: bare text becomes a String literal.**
> When you write text directly inside an element, it is parsed as a `String` value (with one exception: text that parses as an integer becomes an `Integer` instead — see [3.1 Integers, Strings, and Booleans](#31-integers-strings-and-booleans)).
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

### 2.2 Variable References and the `var=` Shorthand

`<var>` references a previously defined name.

```xml
<var name="x"/>

<!-- with explicit type -->
<var name="x" instanceOf="MyClass"/>
```

When an element's content is a single variable reference, the `var` attribute can be used as shorthand. This is expanded by a preprocessor before evaluation, and works the same way on every element that accepts an expression — including `<get>`/`<send>` receivers, `<if>`/`<case>` conditions, `<li>`, `<Context>`/`<Assumption>`, attribute defaults, and more.

```xml
<!-- full form -->
<tag><var name="x"/></tag>

<!-- shorthand -->
<tag var="x"/>
```

> For the full list of predefined names (arithmetic, list/record operations, GSN constructors, classes, and so on), see [Appendix: Built-in Reference](#appendix-built-in-reference). Reference them with `<var name="..."/>` and apply them via `apply` — see [5. Templates and Application](#5-templates-and-application).

### 2.3 Definitions (`def`)

`def` binds a name to a value. PGSN is purely functional, so rebinding is not allowed.

```xml
<def name="x">expr</def>
```

#### `as` Attribute (Shorthand)

The `as` attribute on `def` lets you omit the wrapping element type (tag name).
This is also expanded by the preprocessor before compilation.

```xml
<!-- full form -->
<def name="myGoal"><Goal>...</Goal></def>

<!-- shorthand -->
<def name="myGoal" as="Goal">...</def>
```

`<def name="x" as="T">C</def>` is purely syntactic: the preprocessor rewrites it to `<def name="x"><T>C</T></def>` before compilation. Any tag name that is valid in that position can be used — including user-defined class instantiation tags like `object`. The only restriction is that tags requiring a mandatory attribute of their own (such as `var`, `get`, and `send`, which require `name=`) cannot be used, because the desugared form would be missing that attribute.

### 2.4 Local Scope (`div`)

Use `<def>` elements inside a `<div>` to scope definitions locally. The final child of `<div>` (after any `<def>`s) is its value.

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

### 2.5 Runtime Type Checks (`instanceOf`)

The `instanceOf` attribute on `def` or `var` adds a runtime type check: the value must be an instance of the specified class.
The attribute value is a **variable name** that refers to a class expression.
For complex class expressions (e.g. a computed class), use the `<instanceOf>` child element form instead — see [6.1 Class Definition](#61-class-definition-class) and [6.2 Object Instantiation](#62-object-instantiation-object) for where `<instanceOf>` is used as an element.

> **PGSN has no class names.** Classes are ordinary values bound to variables.
> `instanceOf="x"` means "the variable `x`", not a string literal class name.

```xml
<!-- myClass must be a variable bound to a class definition -->
<def name="x" instanceOf="myClass">...</def>

<!-- same for var references -->
<var name="x" instanceOf="myClass"/>

<!-- for complex class expressions, use the child element form -->
<instanceOf><apply template="computeClass"><arg>...</arg></apply></instanceOf>
```

---

## 3. Data Types

### 3.1 Integers, Strings, and Booleans

Plain text inside an element becomes a value, following the rule from [2.1 Everything Is a Value](#21-everything-is-a-value): text that parses as an integer becomes an `Integer`; any other text becomes a `String`.

```xml
<def name="n">42</def>        <!-- Integer 42 -->
<def name="s">hello</def>     <!-- String "hello" -->
```

There is no literal text syntax for `Boolean` values; use the built-in `true`/`false`, referenced with `<var>`, `<expr>`, or the `var=` shorthand (see [Appendix: Built-in Reference](#appendix-built-in-reference)).

```xml
<var name="true"/>
<expr>true</expr>
```

### 3.2 Set and List (`ul`, `ol`)

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

### 3.3 Record (`dl`)

`<dl>` produces a `Record` — a set of named values, accessed via [`get`](#63-key-access-get). Keys can be arbitrary expressions or string literals via the `key` attribute.

```xml
<dl>
    <dt>key_expr</dt><dd>value_expr</dd>   <!-- expression key -->
    <dt key="name"/><dd>value_expr</dd>    <!-- string key -->
</dl>
```

---

## 4. Expressions and Control Flow

### 4.1 Format Strings in Text

Wherever text is allowed, you can embed in-scope variables with the `{name}` notation.
This is expanded by the preprocessor into a `format_string` application. To write a literal brace, escape it as `{{` or `}}`.

```xml
<template>
    <param name="c" positional="true"/>
    <Evidence>Test result for component {c}</Evidence>
</template>
```

`{...}` is not limited to a bare variable name — it accepts a small expression language: arithmetic (`+`, `-`, `*`, `/`, `%`), comparisons (`==`, `!=`, `<`, `<=`, `>`, `>=`), boolean operators (`and`, `or`, `not`), and integer literals. The expression is evaluated and the result is **always converted to a string** and interpolated into the text — `{x == 1}` becomes the text `"True"` or `"False"`, not a Boolean value.

```xml
<Evidence>Component {c}: {count + 1} of {total}</Evidence>
<Goal>{n} is within range: {n >= 0 and n < 100}</Goal>
```

If you need the **raw, non-string value** of an expression — for example, a Boolean to use as a condition in `if_then_else` — use a standalone `<expr>` element (below) instead of `{...}`.

### 4.2 The `<expr>` Element

The same mini-expression language is available as a standalone element. Unlike `{...}`, it returns the expression's value as-is (Boolean, Integer, etc.), making it usable anywhere a value is expected, not just inside text:

```xml
<expr>x + y * 2</expr>
<expr>n == 0</expr>
<expr>a >= 0 and a < 100</expr>
```

### 4.3 Conditionals (`if`)

`<if cond="...">` is shorthand for `if_then_else`. The `cond` attribute is parsed by the same mini-expression language as `<expr>`, so it can be a plain variable name or an arithmetic/comparison/boolean expression. `<then>` is required; `<else>` may be omitted (in which case `undefined` is used for the else-branch).

```xml
<if cond="n == 0">
    <then><Evidence>Base case verified</Evidence></then>
    <else><undeveloped/></else>
</if>
```

A general expression used as a Goal's support — such as the `<if>` above — must be wrapped in `<supportedBy>`; see [7.3 Goal](#73-goal).

#### `<cond>` Child Element

When the condition doesn't fit comfortably in an attribute string — for example, to use `var=` shorthand or an arbitrary expression such as `<apply>` — write `<cond>` as a child element instead of the `cond` attribute. It accepts any expression (`val_pat`), including the `var=` shorthand:

```xml
<if>
    <cond var="flag"/>
    <then>yes</then>
    <else>no</else>
</if>

<if>
    <cond><apply template="greater_than"><arg var="x"/><arg>3</arg></apply></cond>
    <then>big</then>
    <else>small</else>
</if>
```

### 4.4 Multi-way Conditionals (`cases`)

For a cascade of conditions — like Python's `match`, Lisp's `cond`, or a C `switch` — use `<cases>` instead of nesting `<if>`s. Each `<case>` is a sibling, giving a flat list of conditions rather than a nested tree:

```xml
<cases>
    <case cond="n == 0">zero</case>
    <case cond="n == 1">one</case>
    <case cond="n == 2">two</case>
    <else>many</else>
</cases>
```

Each `<case>` supplies its condition the same way as `<if>` — either a `cond` attribute or a `<cond>` child element (useful for `var=` shorthand or an arbitrary expression). Unlike `<if>`'s `<then>`, **a `<case>`'s body is its own remaining content** — there is no `<then>` wrapper:

```xml
<cases>
    <case cond="false">first</case>
    <case><cond var="flag"/>second</case>
    <else>third</else>
</cases>
```

`<case>`s are checked in order; `<else>` (or `undefined` if omitted) is used if none match. Internally this expands to the same nested `if_then_else` chain as nested `<if>`/`<else>`, but the XML surface is a flat list of siblings.

---

## 5. Templates and Application

### 5.1 Template Definition (`template`)

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

### 5.2 Template Application (`apply`)

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

Example (mapping a template over a list — see [Appendix: Built-in Reference](#appendix-built-in-reference) for `map_term` and other built-ins):

```xml
<apply>
    <var name="map_term"/>
    <arg var="someTemplate"/>     <!-- first argument (the template) -->
    <arg><ol><li>a</li><li>b</li></ol></arg>  <!-- second argument (the list) -->
</apply>
```

---

## 6. Classes and Objects

### 6.1 Class Definition (`class`)

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
> `<inherit>`, `<instanceOf>`, and the `instanceOf` attribute all accept
> **expressions that evaluate to a class**, not string literals.
> Writing `<inherit>SomeClass</inherit>` is a text node and becomes
> `"SomeClass"` as a string value, which is not a class — use `<inherit var="someClass"/>`
> (or any other expression) instead. See also [2.5 Runtime Type Checks (instanceOf)](#25-runtime-type-checks-instanceof).

### 6.2 Object Instantiation (`object`)

```xml
<object>
    <instanceOf var="MyClass"/>
    <attribute name="attr1">value</attribute>
</object>
```

### 6.3 Key Access (`get`)

`get` works on both `Record` (see [3.3 Record](#33-record-dl)) and `PGSNObject`. The `label` attribute names the key (`name` is accepted as an internal-style alias). The receiver is the element's content: either `var="..."` — the same `var=` shorthand from [2.2](#22-variable-references-and-the-var-shorthand), expanding to `<var name="..."/>` — or any expression as a child element. Internally it applies the receiver to the string key as a positional argument, so it is completely equivalent to an `apply` with a plain-text `arg`.

```xml
<!-- var= shorthand for a variable receiver -->
<get label="description" var="my_goal"/>

<!-- receiver as a child expression -->
<get label="description"><apply template="getGoal"/></get>

<!-- Record key access — all three forms are equivalent -->
<get label="x" var="my_record"/>
<get label="x"><var name="my_record"/></get>
<apply><var name="my_record"/><arg>x</arg></apply>
```

### 6.4 Method Invocation (`send`)

```xml
<send method="methodName" var="receiverVar">
    <arg name="arg1">expr1</arg>
</send>
```

The `method` attribute names the method (`name` is accepted as an internal-style alias). The receiver is the element's content: `var="..."` shorthand for a variable reference, or any expression as the first child element when the receiver is more than a plain variable:

```xml
<send method="methodName">
    receiver_expr
    <arg name="arg1">expr1</arg>
</send>
```

---

## 7. GSN Nodes

GSN nodes are first-class values in PGSN and can be extended through class inheritance (see [8. Extending GSN via Classes](#8-extending-gsn-via-classes)).

### 7.1 Common Header (`gsn_header`)

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

### 7.2 GSN Leading Text as Description

For GSN header elements (`Goal`, `Strategy`, `Evidence`, `Context`, `Assumption`), leading plain text is automatically treated as the `description`. When the element also has child elements (such as a nested `<Strategy>`), the text is lifted into a `<description>` element by the preprocessor. `{name}` expansion (see [4.1 Format Strings in Text](#41-format-strings-in-text)) applies here too.

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

### 7.3 Goal

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

> **Note: general expressions as support must use `<supportedBy>`**
> A `<Goal>`'s body must be exactly one of the alternatives shown above. A general
> expression — such as an [`<if>`/`<cases>`](#4-expressions-and-control-flow) that
> evaluates to a Strategy, Evidence, or `<undeveloped/>` depending on a condition —
> is therefore wrapped in `<supportedBy>`, which accepts any expression:
>
> ```xml
> <Goal>
>     System is secure
>     <supportedBy>
>         <if cond="hasEvidence == 1">
>             <then><Evidence>Audit passed</Evidence></then>
>             <else><undeveloped/></else>
>         </if>
>     </supportedBy>
> </Goal>
> ```
>
> `<undeveloped/>` itself is a `GSNNode`, so it can also appear directly as an
> `<if>`/`<case>` branch value, as shown above — not just as a `<Goal>`'s direct,
> unwrapped body.

### 7.4 Strategy

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

### 7.5 Evidence

```xml
<Evidence>
    <description>test result report</description>
    <Context>description of the test environment</Context>
</Evidence>
```

---

## 8. Extending GSN via Classes

GSN nodes can be extended through class inheritance (see [6. Classes and Objects](#6-classes-and-objects)).
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

## 9. Modules, Parameters, and Imports

When a program grows beyond a single file, PGSN provides `<PGSNModule>` (an alternative root element to `<PGSN>`) along with `param` and `from` (import) to declare reusable, parameterized modules and bring names in from other files.

### 9.1 `<PGSNModule>`

Unlike `<PGSN>` (which ends with a single value, see [1. Document Structure](#1-document-structure)), `<PGSNModule>` accepts parameters from the caller and does not itself produce a final value — it only contributes definitions for importers.

```xml
<PGSNModule>
    <param name="p"/>          <!-- parameters (zero or more, must come first) -->
    <from file="..."/>         <!-- imports (zero or more) -->
    <def name="x">...</def>    <!-- definitions (zero or more) -->
</PGSNModule>
```

`<param>` must appear first; `<from>` and `<def>` may be freely interleaved after it.

### 9.2 Parameters (`param`)

`param` declares variables that a `<PGSNModule>` receives from the caller.
Parameters are only valid inside `<PGSNModule>` and must appear before any `<from>` or `<def>` elements.

```xml
<!-- Assumption is a built-in alias for assumption_class -->
<param name="A1" instanceOf="Assumption"/>

<!-- with a default value -->
<param name="threshold">100</param>
```

### 9.3 Import (`from`)

Brings names from external PGSN files into scope. For security reasons, the `file` attribute must be either a relative path (resolved against the importing file's own directory; `..` is forbidden, so a document can never reach above its own directory tree) or a jail-based absolute path (see below).

#### Single import

```xml
<from file="security.pgsn" import="secureGoal" as="G1"/>
```

#### Multiple imports

```xml
<from file="evidence.pgsn">
    <import name="auditEvidence"/>
    <import name="testReport" as="TR"/>
</from>
```

#### Import with parameters

```xml
<from file="other.pgsn">
    <import name="someGoal" as="G2"/>
    <arg name="A1" var="A1"/>
    <arg name="threshold" var="threshold"/>
</from>
```

#### Jail-based absolute import

A `file` value starting with `/` is not a literal filesystem path. Instead, its first path segment names a *jail*: a trusted `{name: directory}` entry supplied by whoever invokes the compiler (`compile_pgsn(path, jails={...})`, `load(path, jails={...})`, or the `pgsn` CLI's repeatable `--jail NAME=PATH` option) — never something the PGSN document itself can define. The remaining segments resolve as a path under that jail's directory, with the same `..`-forbidden rule as a relative import.

```xml
<!-- resolves to <jails["cases"]>/numpy.xml -->
<from file="/cases/numpy.xml" import="secureGoal" as="G1"/>

<!-- subdirectories under the jail are fine -->
<from file="/cases/pkgs/numpy.xml" import="secureGoal" as="G1"/>
```

This lets a top-level document reach files placed anywhere on disk — for example, assurance-case files an external tool (such as a pip-integration layer) collects outside the document's own directory tree — without the document ever holding a real, literal absolute filesystem path. If the referenced jail name isn't in the table the caller supplied, compilation fails with `Unknown jail: '<name>'`. A plain relative `file` (no leading `/`) is unaffected and keeps resolving against the importing file's own directory, so both forms may appear in the same document.

---

## 10. Module Example

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

---

## Appendix: Built-in Reference

The following names are predefined; reference them with `<var name="..."/>` (or the `var=` shorthand, or `template="..."` on `<apply>`) and apply them via [`apply`](#52-template-application-apply).

- List operations: `cons`, `head`, `tail`, `index`, `concat`, `map_term`, `fold`
- Booleans: `true`, `false`, `if_then_else`, `boolean_and`, `boolean_or`, `boolean_not`, `boolean_xor`, `implies`, `equal`, `guard`
- Integers: `plus`, `minus`, `times`, `div`, `mod`, `less_than`, `less_eq`, `greater_than`, `greater_eq`
- Records: `has_label`, `list_labels`, `add_attribute`, `remove_attribute`, `overwrite_record`
- Strings: `format_string`
- Classes / objects: `define_class`, `instantiate`, `is_instance`, `is_subclass`, `base_class`
- Misc: `fix`, `undefined`
- GSN constructors: `goal`, `strategy`, `evidence`, `context`, `assumption`, `undeveloped`, `immediate`, `evidence_as_goal`
- GSN classes (long form): `goal_class`, `strategy_class`, `evidence_class`, `context_class`, `assumption_class`, `gsn_class`, `support_class`, `undeveloped_class`
- GSN classes (short aliases): `Goal`, `Strategy`, `Evidence`, `Context`, `Assumption`, `GSN`, `Support`