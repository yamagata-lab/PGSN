# PGSN: Programmable Goal Structuring Notation

Functional Programming for Assurance Case Generation

[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## What is PGSN?

**PGSN** is a functional programming language and platform for constructing and transforming structured assurance cases based on the **Goal Structuring Notation (GSN)**.
Unlike standard GSN, which primarily consists of static diagrams, PGSN allows dynamic and structured generation of argument elements using a functional and object-oriented programming language.

**PGSN** comes in two forms: a DSL embedded in Python, and an XML syntax
evaluated by the `pgsn` command. Either one can express a whole assurance case
on its own. [README-api.md](README-api.md) is the reference for the Python API
and [README-xml.md](README-xml.md) for the XML syntax.

---

## Key Features

- **GSN Modeling Using Functional Programming**: Write assurance cases as functional programs
- **Reusable**: Build assurance structures compositionally
- **Object-Oriented**: Class/inheritance for reusable node types
- **Confined**: an XML document has no way to reach outside itself — there is no file, network or system access in the language — and the only files it may import are under its own directory or a directory root granted to it. Evaluation is bounded by a step budget. A `.py` input is different: it is a Python program, and `pgsn` runs it with your privileges, so run only `.py` files you trust.

---

## Installation

For users

```shell
pip install git+https://github.com/yamagata-lab/pgsn.git
```

For developers who want to modify the library
```bash
git clone https://github.com/yamagata-lab/PGSN.git
cd PGSN
pip install -e '.[dev]'
```

`pgsn render` and `gsn_dot` need the Graphviz programs (`dot`), which pip does not install: get them from your system's package manager, or use the conda environment below, which includes them.

Or using conda
```bash
git clone https://github.com/yamagata-lab/PGSN.git
cd PGSN
conda env create -f environment.yml -n PGSN
conda activate PGSN
pip install -e '.[dev]'
```

---

## Command-line interface

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

`pgsn doc` evaluates it and prints the structure as a tree:

```shell
% pgsn doc examples/gsn.xml
Generating 'None' from 'examples/gsn.xml'
Evaluating term 'main'...
Goal: System is secure
└── Strategy: Break into sub-goals
    ├── Goal: Input validated
    │   └── Solution: Static analysis passed
    └── Goal: Output sanitized
        └── Solution: Fuzzing test succeeded

Done.
```

A `.py` input is a Python program that binds the term to show to `main` (another name with `--term-name`); see [Example](#example). `pgsn render` draws the same structure as SVG, PNG or PDF, and `pgsn --help` lists the other commands and options. When a command fails, it prints `Error:` and exits with status 1. A usage error, such as a missing input file or a malformed `--jail`, exits with status 2.

### Checking against GSN

`pgsn doc` and `pgsn render` check the evaluated structure against the rules of GSN v3 that a document can break, and report each breach as a warning naming the element's identifier and its path:

```shell
Warning: S1 at <root>.support: a strategy relates a goal to supporting goals, but this one has none
```

The rules: a goal is supported by a strategy, a solution or sub-goals, and a strategy by goals; the contexts of an element are Context nodes and its assumptions Assumption nodes; a strategy has at least one sub-goal; what challenges an element is a defeater; every element's description is a non-blank string; the structure is headed by a goal. With `--strict` a breach is an error: the command writes nothing and exits with status 1.

### Jails for XML imports

An XML document may import other documents. By default it can only reach files under its own directory. To grant access to a shared library of modules, register it as a *jail* — a named directory root — and refer to it from the document as `/<name>/...`:

```shell
PGSN % pgsn doc main.xml --jail lib=/opt/pgsn-lib
```

```xml
<from file="/lib/security.xml" import="secureGoal"/>
```

`--jail` may be given more than once, and applies to `.xml` input only. Nothing outside the document's own directory and the registered jails can be imported: `..` may not leave the enclosing root, and symbolic links are expanded before that check. See [README-xml.md](README-xml.md) for the full rules.

---

## Public API

`import pgsn` gives you the supported interface:

```python
import pgsn

cfg = pgsn.Config(jails={"lib": "/opt/pgsn-lib"})
term = pgsn.load_xml("main.xml", config=cfg)
print(pgsn.gsn_tree(term).show(stdout=False, sorting=False))
```

It exposes constructors for PGSN constants and terms (`string`, `record`, `lambda_abs`, `map_term`, ...), constructors for GSN nodes and classes (`goal`, `strategy`, `solution`, `goal_class`, ...), the conversion and rendering functions (`python_value`, `gsn_tree`, `gsn_dot`, `save_gsn`), and the XML front end with its configuration (`load_xml`, `load_xml_string`, `Config`, `Jails`, `configure`).

Everything else in the package — `pgsn.dsl`, `pgsn.gsn`, `pgsn.pgsn_term`, `pgsn.pgsn_xml`, `pgsn.helpers`, `pgsn.cli` — is internal and may change without notice.

[README-api.md](README-api.md) is the full reference.

---

## Example

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

This is the case of [Command-line interface](#command-line-interface), written in Python. `examples/gsn.py` binds it to `main`, so `pgsn doc examples/gsn.py` prints the same tree.

---

## Advanced Examples

### Example 1: Reusable Goal Template with a Solution

Define a reusable function that generates a goal node supported by a solution node with the same description.

```python
from pgsn import *

# Define a reusable goal+solution template
mk_goal_with_evidence = lambda_abs_keywords(
    {"desc": variable("desc")},
    goal(
        description=variable("desc"),
        support=solution(description=variable("desc"))
    )
)

# Apply the template to multiple goals
g1 = mk_goal_with_evidence(desc="No hardcoded passwords")
g2 = mk_goal_with_evidence(desc="Input sanitized")
g3 = mk_goal_with_evidence(desc="Logging enabled")

# Compose a top-level goal with a strategy
top = goal(
    description="System is secure",
    support=strategy(
        description="Apply security principles",
        sub_goals=[g1, g2, g3]
    )
)

gsn_tree(top.fully_eval()).show(sorting=False)
```

---

### Example 2: Auto-expanding Multiple Goals with `map_term`

Use `map_term` to generate multiple sub-goals from a list of requirements dynamically.

```python
from pgsn import *

requirements = ["Firewall enabled", "Encrypted communication", "Access control active"]


goal_template = lambda_abs(variable("desc"),
    goal(description=variable("desc"),
         support=solution(description=variable("desc")))
)

goals = map_term(goal_template, requirements)

secure_goal = goal(
    description="Security requirements fulfilled",
    support=immediate(goals)
)

gsn_tree(secure_goal.fully_eval()).show(sorting=False)
```

---

### Example 3: Class-based Node Composition Using Object System

Define a custom goal class and instantiate it with additional metadata.

```python
from pgsn import *

# Define a custom subclass of Goal
CustomGoal = define_class(inherit=goal_class, name="GoalWithProject", attributes=["project"])

g = instantiate(CustomGoal, description="Secure connection established",
                project='Alpha',
                support=solution(description="Verified by audit"))

gsn_tree(g.fully_eval()).show(sorting=False)
```

---

## Summary of Techniques

| Purpose                      | Technique                                   |
|------------------------------|---------------------------------------------|
| Reusing a template           | Lambda abstraction with keyword parameters  |
| Generating structure in bulk | List expansion with `map_term`              |
| Attaching metadata           | Class definition and `instantiate`          |

You can adapt these techniques to build domain-specific GSN templates, automate assurance case generation, or validate structural constraints programmatically.

---

## Summary of Common Constructs

| Construct                    | Description                             |
|-----------------------------|-----------------------------------------|
| `goal(...)`                 | Defines a GSN Goal                      |
| `strategy(...)`             | Logical inference for a Goal            |
| `solution(...)`             | Reference to evidence for a Goal        |
| `context(...)`              | Context for a Goal or Strategy          |
| `assumption(...)`           | Declares an assumption                  |
| `defeater(...)`             | Challenges the node holding it          |
| `undeveloped`               | Marks a goal as not yet supported       |
| `immediate(...)`            | Binds sub-goals directly                |
| `map_term(...)`             | Functional mapping over list_term       |
| `lambda_abs(...)`           | Lambda abstraction (positional)         |
| `lambda_abs_keywords(...)`  | Lambda abstraction (keyword args)       |
| `define_class(...)`         | Defines a class (`inherit=` names its parent) |
| `instantiate(...)`          | Instantiates a class                    |

---

## Architecture

| Layer          | Component              | Purpose                                       |
|----------------|------------------------|-----------------------------------------------|
| Core           | `pgsn_term.py`         | Lambda calculus interpreter                   |
| Python DSL     | `dsl.py`, `gsn.py`     | Builds GSN nodes from a program               |
| XML front end  | `pgsn_xml.py`          | Compiles the XML syntax onto the core         |
| Sandbox        | `jail.py`, `config.py` | Confines what an import may reach             |
| CLI            | `cli.py`               | `pgsn doc`, `pgsn render`, `pgsn compile`     |


---

## License

MIT License – see [LICENSE](LICENSE).

Copyright: National Institute of Advanced Industrial Science and Technology (AIST) 2023-2024,  
Yoriyuki Yamagata 2025-
