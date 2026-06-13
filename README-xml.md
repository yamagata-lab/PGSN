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

A value in PGSN is any expression or variable reference.

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
<param name="A1" instanceOf="Assumption"/>

<!-- with a default value -->
<param name="threshold">100</param>
```

---

## Import (from)

Brings names from external PGSN files into scope. For security reasons, only relative file paths are allowed.

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

---

## Definitions (def)

`def` binds a name to a value. PGSN is purely functional, so rebinding is not allowed.

```xml
<def name="x">expr</def>
```

### `as` Attribute (Shorthand)

The `as` attribute on `def` lets you omit the wrapping element type (tag name).
This is also expanded by the preprocessor.

```xml
<!-- full form -->
<def name="myGoal"><Goal>...</Goal></def>

<!-- shorthand -->
<def name="myGoal" as="Goal">...</def>
```

`as` accepts only **built-in tag names** (`Goal`, `Strategy`, `Evidence`, `template`, `class`, `object`, `div`, `apply`, `ul`, `ol`, `dl`).
User-defined class names (e.g. `GoalWithURL`) cannot be used with `as`
(see "Extending GSN via Classes" below).

> **Design invariant**
> `<def name="x" as="T">C</def>` is valid if and only if its desugared form `<def name="x"><T>C</T></def>` is valid.
> Consequently, tags whose element carries a required attribute (`name`) — namely `var`, `get`, and `send` — cannot be used with `as`, because the desugared `<send>C</send>` would be missing its required attribute.

### `instanceOf` Attribute

Used to explicitly declare the type of the defined value.

```xml
<def name="x" instanceOf="MyClass">...</def>
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

Local `def` elements can also appear directly inside a `<template>` body, before the final value expression. This avoids the need for a wrapping `<div>`.

```xml
<template>
    <param name="x"/>
    <def name="doubled"><apply><var name="plus"/><arg var="x"/><arg var="x"/></apply></def>
    <var name="doubled"/>   <!-- final value -->
</template>
```

---

## Variables (var)

References a previously defined name.

```xml
<var name="x"/>

<!-- with explicit type -->
<var name="x" instanceOf="MyClass"/>
```

### Built-ins

The following names are predefined; reference them with `<var name="..."/>` and apply them via `apply`.

- List operations: `cons`, `head`, `tail`, `index`, `concat`, `map_term`, `fold`
- Booleans: `true`, `false`, `if_then_else`, `boolean_and`, `boolean_or`, `boolean_not`, `equal`, `guard`
- Integers: `plus`, `minus`, `times`, `div`, `mod`
- Records: `has_label`, `list_labels`, `add_attribute`, `remove_attribute`, `overwrite_record`
- Strings: `format_string`
- Classes / objects: `define_class`, `instantiate`, `is_instance`, `is_subclass`, `base_class`
- Misc: `fix`, `undefined`
- GSN: `goal`, `strategy`, `evidence`, `context`, `assumption`, `undeveloped`, `immediate`, `evidence_as_goal`, and the classes (`goal_class`, etc.)

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
    <inherit>ParentClass</inherit>    <!-- inheritance (optional) -->
    <attribute name="attr1">default_value</attribute>
    <attribute name="attr2"/>         <!-- no default value -->
    <method name="m">
        <param name="p1">default</param>
        <param name="p2"/>
        body_expr
    </method>
</class>
```

### Object Instantiation (object)

```xml
<object>
    <instanceOf>MyClass</instanceOf>
    <attribute name="attr1">value</attribute>
</object>
```

### Key Access (get)

`get` works on both `Record` and `PGSNObject`. Internally it applies `expr` to the string key `name` as a positional argument, so it is completely equivalent to an `apply` with a plain-text `arg`.

```xml
<!-- PGSNObject attribute access -->
<get name="description"><var name="myGoal"/></get>

<!-- Record key access (the two forms below are equivalent) -->
<get name="x"><var name="myRecord"/></get>
<apply><var name="myRecord"/><arg>x</arg></apply>
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
<Context><get name="version">expr</get></Context>      <!-- expression -->

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

---

## Extending GSN via Classes

GSN nodes can be extended through class inheritance.
Instantiate the extended class with `<object>` (listing its attributes explicitly).

```xml
<!-- a class inheriting Goal, adding a URL attribute -->
<def name="GoalWithURL" as="class">
    <inherit>Goal</inherit>
    <attribute name="URL"/>
</def>

<!-- instantiation (object form) -->
<object>
    <instanceOf>GoalWithURL</instanceOf>
    <attribute name="description">System X is secure</attribute>
    <attribute name="URL">https://example.com/evidence</attribute>
    <attribute name="support" var="undeveloped"/>
</object>
```

> The shorthand of writing a user-defined class name in the `as` attribute (e.g. `<def name="myGoal" as="GoalWithURL">...`) is not supported.
> Since `as` is limited to built-in tag names, use the `<object>` form above to instantiate an extended class.

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