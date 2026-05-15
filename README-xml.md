# PGSN — Programmable Goal Structuring Notation

PGSN is an XML-based language that extends GSN (Goal Structuring Notation) with programming constructs.
GSN nodes (Goal, Strategy, Evidence) are treated as first-class values and can be combined with variables, templates, and classes.

---

## Document Structure

The root element of a PGSN document is `<PGSN>`, structured as follows:

```xml
<PGSN>
    <param name="p"/>          <!-- parameters (zero or more) -->
    <from file="..."/>         <!-- imports (zero or more) -->
    <def name="x">...</def>    <!-- definitions (zero or more) -->
    ...                        <!-- value (exactly one) -->
</PGSN>
```

`import` and `def` elements may be freely interleaved.

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

`param` declares variables that this PGSN module receives from the outside.
Parameters must appear at the top of `<PGSN>`, before any imports or definitions.

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

The `as` attribute on `def` allows the wrapping element type (tag name) to be omitted.
This is also expanded by the preprocessor.

```xml
<!-- full form -->
<def name="myGoal"><Goal>...</Goal></def>

<!-- shorthand -->
<def name="myGoal" as="Goal">...</def>
```

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

---

## Variables (var)

References a previously defined name.

```xml
<var name="x"/>

<!-- with explicit type -->
<var name="x" instanceOf="MyClass"/>
```

---

## Templates and Application

### Template Definition (template)

Defines a function as a value (equivalent to a lambda expression).

```xml
<!-- no parameters -->
<template>expr</template>

<!-- with parameters; default values are optional -->
<template>
    <param name="arg1">default_expr</param>
    <param name="arg2"/>
    body_expr
</template>
```

### Template Application (apply)

Applies a template to arguments.

```xml
<apply>
    expr               <!-- the template to apply -->
    <arg name="arg1">expr1</arg>
    <arg name="arg2">expr2</arg>
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

### Attribute Access (get)

```xml
<get name="attr">expr</get>
```

### Method Invocation (send)

```xml
<send name="methodName">
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

### Dictionary (dl)

Keys can be arbitrary expressions or string literals via the `key` attribute.

```xml
<dl>
    <dt>key_expr</dt><dd>value_expr</dd>   <!-- expression key -->
    <dt key="name"/><dd>value_expr</dd>    <!-- string key -->
</dl>
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

<!-- Assumption: a named proposition accepted without proof.
     A variable reference is required. -->
<Assumption>description text<var name="A1"/></Assumption>
<Assumption var="A1"/>    <!-- shorthand -->
```

**Context vs Assumption**

- `Context` describes the situation or subject matter in which the argument is made. It accepts any expression as its value — variable references, objects, lists, and so on — making it suitable for referencing external data or runtime information.
- `Assumption` introduces a free variable that must be bound somewhere in the document by `def` or `param`. The value bound to that variable may be `undeveloped`, indicating that the justification for the assumption is acknowledged but deferred. This is an intentional design choice: every assumption must have an explicit owner in the argument structure.

### Goal

```xml
<Goal>
    <description>System X is secure</description>
    <Context>certified under standard XXXX</Context>
    <Assumption>no zero-day attacks<var name="A1"/></Assumption>

    <!-- body: exactly one of the following -->
    <Strategy>...</Strategy>              <!-- supported by a Strategy -->
    <Evidence>...</Evidence>              <!-- supported by Evidence -->
    <Goal>...</Goal>                      <!-- supported by sub-goals (one or more) -->
    <supportedBy var="strategy1"/>        <!-- supported by a variable reference -->
    <undeveloped/>                        <!-- not yet developed -->
</Goal>
```

### Strategy

```xml
<Strategy>
    argument
    <!-- body: exactly one of the following -->
    <Goal>...</Goal>           <!-- sub-goals (one or more) -->
    <subGoals var="goals"/>    <!-- sub-goals via variable reference -->
</Strategy>
```

A set (`ul`) can be passed to `subGoals` to specify sub-goals dynamically.

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

```xml
<def name="GoalWithURL">
    <class>
        <inherit>Goal</inherit>
        <attribute name="URL"/>
    </class>
</def>

<def name="myGoal" as="GoalWithURL">
    System X is secure
    <attribute name="URL">https://example.com/evidence</attribute>
    <undeveloped/>
</def>
```

---

## Module Example

A complete example combining parameters and imports.

```xml
<PGSN>
    <!-- receive an assumption from the caller -->
    <param name="A1" instanceOf="Assumption"/>

    <!-- bring in a goal from another file -->
    <from file="security.pgsn" import="secureGoal" as="G1"/>

    <!-- bind the Assumption via supportedBy -->
    <def name="mainStrategy" as="Strategy">
        verified through testing and review
        <subGoals>
            <ul>
                <li var="G1"/>
            </ul>
        </subGoals>
    </def>

    <Goal>
        <description>the system is secure</description>
        <Assumption>no zero-day attacks<var name="A1"/></Assumption>
        <Strategy var="mainStrategy"/>
    </Goal>
</PGSN>
```