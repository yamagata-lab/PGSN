# PGSN: Programmable Goal Structuring Notation

Functional Programming for Assurance Case Generation

[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## What is PGSN?

PGSN lets you write a GSN (Goal Structuring Notation) assurance case as a program. Instead of drawing every goal by hand, you define a pattern once — a goal template, a class of goal with extra fields — and generate the argument from it, for example one sub-goal per requirement in a list.

PGSN comes in two forms, and either one can express a whole assurance case on its own:

- **XML**, evaluated by the `pgsn` command. An XML document is confined: it cannot read files, use the network or call the system. PGSN does not limit the memory or the time a document uses, however, so run a document you did not write in a virtual machine or a container that limits them. [README-xml.md](README-xml.md) is the reference.
- **Python**, as a library embedded in Python. It has the full power of Python, so use it for code you trust. [README-api.md](README-api.md) is the reference.

[README-ja.md](README-ja.md) is the Japanese version of this document.

## Key features

- **Assurance cases as functional programs**: goals, strategies and solutions are values that can be named, passed to templates and generated from lists.
- **Reusable**: build assurance structures from parts, and import parts from other files.
- **Object-oriented**: define new node types by inheriting from the GSN classes.
- **GSN v3 output**: `pgsn render` draws the result after the GSN Community Standard, Version 3, including the dialectic extension (defeaters), and `pgsn doc` and `pgsn render` check the result against the standard's structural rules.
- **Confined XML**: an XML document cannot read files, use the network or call the system. It can import only from its own directory or from directories you grant (jails). Evaluation has a step limit, which stops a document that does not terminate; it does not limit memory or time, since a single step can cost any amount.
- **Python when you trust the code**: a `.py` input is an ordinary Python program, run with your privileges. Run only `.py` files you trust.

## Installation

**Users:**

```shell
pip install git+https://github.com/yamagata-lab/PGSN.git
```

**Developers** (editable install):

```shell
git clone https://github.com/yamagata-lab/PGSN.git
cd PGSN
pip install -e '.[dev]'
```

**Developers, with conda** (also installs Graphviz):

```shell
git clone https://github.com/yamagata-lab/PGSN.git
cd PGSN
conda env create -f environment.yml -n PGSN
conda activate PGSN
pip install -e '.[dev]'
```

Drawing needs the Graphviz programs (`dot`): `pgsn render`, `save_gsn`, and rendering the graph that `gsn_dot` returns. pip does not install them; get them from your system's package manager, or use the conda environment above.

## Quick start

An XML document, `examples/gsn.xml`:

```xml
<PGSN>
    <Goal>
        System is secure
        <Strategy>
            Break into sub-goals
            <Goal>Input validated<Solution>Static analysis passed</Solution></Goal>
            <Goal>Output sanitized<Solution>Fuzzing test succeeded</Solution></Goal>
        </Strategy>
    </Goal>
</PGSN>
```

`pgsn doc` evaluates the document and writes the resulting argument as a text tree to the file given by `-o` (`-o -` prints it):

```console
$ pgsn doc examples/gsn.xml -o -
Evaluating term 'main'...
Goal: System is secure
└── Strategy: Break into sub-goals
    ├── Goal: Input validated
    │   └── Solution: Static analysis passed
    └── Goal: Output sanitized
        └── Solution: Fuzzing test succeeded

Done.
```

`pgsn render` draws the same argument:

```console
$ pgsn render examples/gsn.xml -o gsn -f png     # writes gsn.png
```

Both check the result against the rules of GSN v3 and print a warning for each element that breaks one; `--strict` makes a breach an error. [Checking against GSN v3](README-xml.md#checking-against-gsn-v3) lists the rules.

## The same case in Python

```python
from pgsn import *

g = goal(
    description="System is secure",
    support=strategy(
        description="Break into sub-goals",
        sub_goals=[
            goal(description="Input validated",
                 support=solution(description="Static analysis passed")),
            goal(description="Output sanitized",
                 support=solution(description="Fuzzing test succeeded"))
        ]
    )
)

gsn_tree(g.fully_eval()).show(sorting=False)
```

This builds the same assurance case as `examples/gsn.xml`. The `pgsn` command also accepts a `.py` input: it runs the program and shows the value of its variable `main` (choose another variable with `--term-name`). `examples/gsn.py` assigns the case above to `main`, so `pgsn doc examples/gsn.py -o -` prints the same tree. A `.py` input is an ordinary Python program run with your privileges, so run only files you trust.

## Going further

Three techniques cover most uses:

| Purpose | Technique | Example |
|---|---|---|
| Reusing a pattern | a template with parameters | `examples/secure_with_template.xml` |
| Generating structure from a list | `map_term`, which applies a template to every item of a list | `examples/map_term.xml` |
| Attaching extra data to nodes | a class inheriting from a GSN class | `examples/custom_goal.xml` |

Each example has a Python version beside it (`examples/secure_with_template.py`, `examples/map_term.py`, `examples/custom_goal.py`).

### A reusable goal template

A template that makes a goal supported by a solution with the same description, applied three times:

```xml
<PGSN>
    <def name="mkGoalWithEvidence" as="template">
        <param name="desc"/>
        <Goal>{desc}<Solution>{desc}</Solution></Goal>
    </def>

    <def name="g1" as="apply"><var name="mkGoalWithEvidence"/><arg name="desc">No hardcoded passwords</arg></def>
    <def name="g2" as="apply"><var name="mkGoalWithEvidence"/><arg name="desc">Input sanitized</arg></def>
    <def name="g3" as="apply"><var name="mkGoalWithEvidence"/><arg name="desc">Logging enabled</arg></def>

    <Goal>
        System is secure
        <Strategy>
            Apply security principles
            <subGoals><ol><li var="g1"/><li var="g2"/><li var="g3"/></ol></subGoals>
        </Strategy>
    </Goal>
</PGSN>
```

### One goal per requirement

`map_term` applies the template to every requirement in the list:

```xml
<PGSN>
    <def name="goalTemplate" as="template">
        <param name="desc" positional="true"/>
        <Goal>{desc}<Solution>{desc}</Solution></Goal>
    </def>

    <def name="goals" as="apply">
        <var name="map_term"/>
        <arg var="goalTemplate"/>
        <arg><ol>
            <li>Firewall enabled</li>
            <li>Encrypted communication</li>
            <li>Access control active</li>
        </ol></arg>
    </def>

    <Goal>
        Security requirements fulfilled
        <supportedBy><apply><var name="immediate"/><arg var="goals"/></apply></supportedBy>
    </Goal>
</PGSN>
```

`immediate` makes a strategy that just carries the listed sub-goals; it appears in the output as a Strategy labeled `immediate`.

### A custom goal class with extra data

A class that inherits from `Goal` and adds a `project` attribute:

```xml
<PGSN>
    <def name="GoalWithProject">
        <class name="GoalWithProject">
            <inherit var="Goal"/>
            <attribute name="project"/>
        </class>
    </def>

    <object>
        <instanceOf var="GoalWithProject"/>
        <attribute name="description">Secure connection established</attribute>
        <attribute name="project">Alpha</attribute>
        <attribute name="support"><Solution>Verified by audit</Solution></attribute>
    </object>
</PGSN>
```

## Command line

| Command | What it does |
|---|---|
| `pgsn doc FILE -o OUT` | evaluates the document and writes it as a text tree (`-d json` for JSON); `-o -` is standard output |
| `pgsn render FILE -o NAME -f svg\|png\|pdf` | evaluates the document and draws it; `NAME` is given without an extension. `--label-width N` wraps labels at `N` columns |
| `pgsn compile FILE -o OUT` | compiles the document to JSON |

`pgsn --help` and `pgsn COMMAND --help` list every option. The options shared by `doc` and `render`:

- `-s`, `--steps N` sets the step limit of the evaluation.
- `--strict` makes a breach of the GSN v3 rules an error: the command writes nothing and exits with status 1.
- `--jail NAME=DIR` grants access to a directory of shared modules (below).

When a command fails, it prints `Error:` and exits with status 1. A usage error, such as a missing input file, a `pgsn doc` without `-o` or a malformed `--jail`, exits with status 2.

### Jails for XML imports

An XML document may import other documents. By default it can only reach files under its own directory. To grant access to a shared library of modules, register it as a *jail* — a named directory root — and refer to it from the document as `/<name>/...`:

```console
$ pgsn doc main.xml -o - --jail lib=/opt/pgsn-lib
```

```xml
<from file="/lib/security.xml" import="secureGoal"/>
```

Here `/opt/pgsn-lib` and `main.xml` stand for your own directory and document. `--jail` may be given more than once, and applies to `.xml` input only. Nothing outside the document's own directory and the registered jails can be imported: `..` cannot climb above the document's own directory (or above the jail it lives in), and symbolic links are expanded before that check. [README-xml.md](README-xml.md#import-paths-and-jails) gives the full rules.

## Using PGSN from Python

`import pgsn` is the supported interface. Everything in `pgsn.__all__` is public; everything else, including all submodules (`pgsn.dsl`, `pgsn.gsn`, …), is internal and may change without notice. Load an XML document with `pgsn.load_xml`, or build terms in Python as above:

```python
import pgsn

term = pgsn.load_xml("examples/gsn.xml")
print(pgsn.gsn_tree(term).show(stdout=False, sorting=False))
```

[README-api.md](README-api.md) is the reference.

## Documentation

| Document | For |
|---|---|
| [README-xml.md](README-xml.md) | the XML syntax: a guided start and the reference |
| [README-api.md](README-api.md) | the Python API |
| [known_issues.md](known_issues.md) | what the current version does wrong or does not do yet |
| `examples/` | runnable documents, from small ones to the EU AI Act case generator |
| [PGSN-implementation.md](PGSN-implementation.md) | why the processor is implemented as it is, for contributors |

Each document has a Japanese version (`README-ja.md`, `README-ja-xml.md`, `README-ja-api.md`, `known_issues-ja.md`).

## License

MIT License – see [LICENSE](LICENSE).

Copyright: National Institute of Advanced Industrial Science and Technology (AIST) 2023-2024,  
Yoriyuki Yamagata 2025-
