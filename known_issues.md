# Known issues

This file lists what the current version of PGSN does wrong, does silently, or
does not do yet. The language itself is defined in [README-xml.md](README-xml.md)
and [README-api.md](README-api.md); where an entry below disagrees with them,
the README states the intended behavior and the entry describes the deviation.
A Japanese version is [known_issues-ja.md](known_issues-ja.md).

## What the XML compiler drops without a word

The compiler reports malformed syntax, but it ignores some well-formed input it
does not use. A document that relies on one of these does not mean what it
says.

1. **An unknown child element of a GSN element is ignored.** A `<Defeater>`
   misspelled `<Rebuttal>` inside a `<Goal>` gives a goal with one defeater
   fewer and no message. An unknown element where a value is expected (for
   example `<Foo/>` as the content of `<def>`) is reported as `Unknown
   expression`.
2. **An unknown attribute is ignored.** `<get label="k">` is not reported as a
   misspelling; the element fails for want of `key`. An attribute that belongs
   to another element, such as `positional` on `<def>`, is ignored too.
3. **A boolean attribute accepts any value.** `positional` and `recursive`
   take effect only when their value is `true`; any other value (`yes`, `1`)
   is accepted and means false.
4. **A Context or an Assumption inside a `<Solution>` or a `<Defeater>` is
   dropped.** Only `Goal` and `Strategy` take them.
5. **A second support of a Goal is dropped.** A `<Goal>` keeps the first
   support written (`<Strategy>`, `<Solution>`, `<supportedBy>`,
   `<undeveloped/>` or a run of sub-goals) and drops the rest.
6. **A Strategy with both written sub-goals and `<subGoals>` keeps only the
   written ones.** The `<subGoals>` element is dropped, in whichever order the
   two appear, and a mistake inside it (such as an unbound name) goes
   unreported.
7. **Competing descriptions are resolved silently.**
   1. Leading text and a `<description>` element: the element wins and the
      text is dropped.
   2. A `<description>` element followed by text: the text is dropped.
   3. Text written after the support: it is dropped, and the description is
      empty.
   4. Leading text and a value child: the child is dropped.
8. **`<dl>` accepts irregular entries.**
   1. `<dt key="k">text</dt>`: the text is ignored.
   2. `<dt>` and `<dd>` are not told apart: the children are taken two by
      two, the first of each pair as the label and the second as the value.
      So two `<dt>` in a row make the second the value of the first, as a
      string; a `<dd>` with no `<dt>` before it is taken as a label; and a
      last child left without a partner is dropped.
   3. A key given twice: the last entry wins.
9. **`typeOf` on a `<param>` is ignored.** A parameter takes no `typeOf`; check
   the value where it is used.

The XML schema in the repository would reject several of these documents, but
it is experimental: it does not yet describe the language exactly, and `pgsn`
does not validate a document against it.

## Templates and application

10. **An unknown keyword argument is ignored.** `<arg name="zz">` passed to a
    template without a parameter `zz` is dropped, and the template runs with
    its defaults. The Python constructors behave the same way:
    `goal(..., suport=x)` evaluates, and `solution(contexts=...)` drops the
    contexts.
11. **A positional parameter can be passed by name, with the wrong result.**
    The template then receives the record of keyword arguments in place of the
    value. A positional argument given to a template that has only keyword
    parameters stops with the message `unexpected term type App`.
12. **Two definitions cannot refer to each other.** `recursive="true"` makes a
    definition visible in its own value only, so mutual recursion cannot be
    written.

## GSN

13. **Sub-goals written directly under a Goal show up as a Strategy whose
    description is `immediate`.** One or more `<Goal>` elements under a
    `<Goal>`, and an explicit
    application of `immediate`, are supported by a Strategy whose description
    is the string `immediate`. It appears in `pgsn doc`, in the drawing and in
    the identifiers of the GSN check.
14. **`context` and `assumption` drop defeaters (Python API).**
    `context(description="c", defeaters=[...])` evaluates to a context whose
    `defeaters` list is empty.
15. **A record can pass for a GSN node in `python_value`.** `python_value`
    marks a node with a label such as `__Goal__`, so a plain record carrying
    that label and a goal's other labels converts to the same Python value as
    a goal. `gsn_tree` and `gsn_violations` do not take it for one.
16. **The language is not yet shaped after the GSN metamodel.** The output
    follows GSN v3, but the language does not.
    1. A Goal has a single support; GSN v3 lets several strategies or
       solutions support one goal.
    2. There is no Justification element.
    3. GSN elements have no identifiers a document can refer to. The drawing
       labels them (G1, S1, …), but a label of the drawing cannot be used in
       the document, so a Challenges relationship cannot be the target of
       another.
    4. A defeater's `support` says why the defeater holds, not why it defeats
       its target. GSN makes the supporting side state its reasoning in a
       Strategy and has no counterpart on the attacking side.
17. **Typing is structural only.** A type is satisfied by any class that
    carries its labels, so a `Goal` satisfies `Solution`, and every GSN node,
    `Undeveloped` and `Defeater` included, satisfies `typeOf="Solution"`.
    There is no check that a node is a Goal rather than merely goal-shaped,
    and when two class definitions written in different places are the same
    class is not decided, nor how the provenance of either is established.
    Class names cannot settle it, since names given in documents written apart
    from each other are not unique.

## Evaluation

18. **Memory and time are not limited.** The step budget counts steps, and a
    step has no bound on its cost: an integer squared over and over, or a
    format string that doubles its input, reaches gigabytes within a few
    hundred steps. The budget stops a document that does not terminate; it
    bounds memory and time only for documents that do not grow their values
    that way. Run a document you did not write in a virtual machine or a
    container that limits memory and time.
19. **A value that depends on itself is reported as an exhausted budget.** A
    definition whose value is needed while it is being computed stops with
    the same error as running out of steps.
20. **A deep enough structure stops with Python's `RecursionError`.** The
    evaluator itself does not use the Python stack, but the passes before and
    after it (the XML front end, the removal of names, `python_value`,
    `gsn_tree`) recurse.
21. **The step-limit error is a raw dump.** When the budget runs out, `pgsn`
    prints `Error: ('Reduction did not terminate', …)` followed by the internal
    form of the term, often several kilobytes long. In Python,
    `LambdaInterpreterError.args[0]` is `'Reduction did not terminate'`.
22. **A stuck value is reported where evaluation came to rest, not where the
    cause is.** The message names the first reason in the chain, but the path
    is that of the outer application.
23. **`undefined` cannot be read back.** `python_value` cannot convert
    `undefined` or a constant, and `equal(undefined)(constant("undefined"))` is
    true, so `undefined` cannot be told apart from a constant of that name.

## Error messages

24. **The brace errors of an f-string double the advice.** An unclosed `{`,
    or a `}` that closes no field, in an f-string in `<expr>` is reported with
    `write '{{{{' for a literal brace` (or `'}}}}'`); the escape is `{{` (and
    `}}` for `}`).
25. **A block with bindings and no value is reported as `Unknown expression:
    <def>`.** The message does not say that the value is missing.
26. **A `<param>` in the wrong place in a module is reported as
    `<PGSNModule> takes <def> and <from> before its value, found <param>`,**
    although a module has no value.
27. **Some failures are reported as `unexpected term type App`** rather than
    with the reason, for example an `<object>` whose class has
    `<inherit>Goal</inherit>` (a string where a class is expected); the class
    on its own is reported with the reason.

## Python API

28. **`list_term` and `record` fail on Python values with an empty
    `AssertionError`.** They take terms only; `list_term(["a"])` raises an
    `AssertionError` with no message. Under `python -O` nothing is raised, and
    evaluation fails later with an `AttributeError`.
29. **Building on an evaluated term fails unevenly.** Applying the result of
    `fully_eval()`, or passing it to a constructor, is not supported. Some such
    uses raise an empty `AssertionError`; others happen to work.
30. **The Python API does not check names.** `variable("_x")`,
    `variable("1x")` and `variable("class")` are accepted, although names
    beginning with an underscore are reserved by the processor and the other
    two cannot be written in XML.

## Command line

31. **`--term-name` is accepted for XML input and ignored.** It selects a
    variable of a `.py` input only; with an `.xml` input the progress line
    names the given term, but the document's value is shown.
