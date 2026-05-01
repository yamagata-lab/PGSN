This repo. is obsolute.  The up-to-date one is https://github.com/yamagata-lab/PGSN


# PGSN: Programmable Goal Structuring Notation

Functional Programming for Assurance Case Generation

[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## What is PGSN?

**PGSN** is a functional programming language and platform for constructing and transforming structured assurance cases based on the **Goal Structuring Notation (GSN)**.
Unlike standard GSN, which primarily consists of static diagrams, PGSN allows dynamic and structured generation of argument elements using a functional and object-oriented programming language.

**PGSN** is currently implemented as an **embedded language in Python**, but other implementations are planned.

## Key Features

-  **GSN Modeling Using Functional Programming**: Write assurance cases as functional programs
-  **Reusable**: Build assurance structures compositionally
-  **Object-Oriented**: Class/inheritance for reusable node types
-  **Security Aware**: PGSN terms are executed in a resource-limited interpreter, ensuring safe evaluation of third-party code.

## Installation

For users

```shell
pip install git+https://github.com/yoriyuki/pgsn.git
```

For developers who want modify the library
```bash
git clone https://github.com/yoriyuki/PGSN.git
cd PGSN
pip install -e .
```

Or using conda
```bash
git clone https://github.com/yoriyuki/PGSN.git
cd PGSN
conda env create -f environment.yml -n PGSN
```

## Command-line interface

```shell
PGSN % pgsn doc examples/cli.py   
Generating 'None' from 'examples/cli.py'
Evaluating term 'main'...
Goal: System is secure
└── Strategy: Break into sub-goals
    ├── Goal: Input validated
    │   └── Evidence: Static analysis passed
    └── Goal: Output sanitized
        └── Evidence: Fuzzing test succeeded

Done.
````

Use "pgsn --help" for other command and option

## Example

```python
from pgsn.gsn import *
from pgsn.dsl import *

g = goal(
    description="System is secure",
    support=strategy(
        description="Break into sub-goals",
        sub_goals=[
            goal(description="Input validated",
                 support=evidence(description="Static analysis passed")),
            goal(description="Output sanitized",
                 support=evidence(description="Fuzzing test succeeded"))
        ]
    )
)

gsn_tree(g.fully_eval()).show()
```

From the project root,
```shell
% python examples/gsn.py
Goal: System is secure
└── Strategy: Break into sub-goals    pyproject-build    python             python3            python3.1          python3.12-config  
    ├── Goal: Input validated
    │   └── Evidence: Static analysis passed
    └── Goal: Output sanitized
        └── Evidence: Fuzzing test succeeded
```

## Advanced Examples

### Example 1: Reusable Goal Template with Evidence

Define a reusable function that generates a goal node supported by an evidence node with the same description.

```python
from pgsn.dsl import *
from pgsn.gsn import *

# Define a reusable goal+evidence template
mk_goal_with_evidence = lambda_abs_keywords(
    {"desc": variable("desc")},
    goal(
        description=variable("desc"),
        support=evidence(description=variable("desc"))
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

gsn_tree(top.fully_eval()).show()
```

### Example 2: Auto-expanding Multiple Goals with `map_term`

Use `map_term` to generate multiple sub-goals from a list of requirements dynamically.

```python
from pgsn.dsl import *
from pgsn.gsn import *

requirements = ["Firewall enabled", "Encrypted communication", "Access control active"]


goal_template = lambda_abs(variable("desc"),
    goal(description=variable("desc"),
         support=evidence(description=variable("desc")))
)

goals = map_term(goal_template, requirements)

secure_goal = goal(
    description="Security requirements fulfilled",
    support=immediate(goals)
)

gsn_tree(secure_goal.fully_eval()).show()
```

### Example 3: Class-based Node Composition Using Object System

Use `object_term.py` to define a custom goal class and instantiate it with additional metadata.

```python
from pgsn.dsl import *
from pgsn.gsn import *

# Define a custom subclass of Goal
CustomGoal = define_class(inherit=goal_class, name="GoalWithProject", attributes=["project"])

g = instantiate(CustomGoal, description="Secure connection established",
                project='Alpha',
                support=evidence(description="Verified by audit"))

gsn_tree(g.fully_eval()).show()
```

These advanced examples demonstrate how to:

| Purpose | Technique |
|---------|-----------|
| Template reuse | Define lambda abstractions and keyword arguments |
| Bulk generation | Use `map_term` over lists |
| Metadata handling | Extend GSN nodes via custom classes |

You can adapt these techniques to build domain-specific GSN templates, automate assurance case generation, or validate structural constraints programmatically.

## Summary of Common Constructs

| Construct                    | Description                             |
|-----------------------------|-----------------------------------------|
| `goal(...)`                 | Defines a GSN Goal                      |
| `strategy(...)`             | Logical inference for a Goal            |
| `evidence(...)`             | Data supporting a Goal                  |
| `context(...)`              | Context for a Goal or Strategy          |
| `assumption(...)`           | Declares an assumption                  |
| `immediate(...)`            | Binds sub-goals directly                |
| `map_term(...)`             | Functional mapping over list_term       |
| `lambda_abs(...)`           | Lambda abstraction (positional)         |
| `lambda_abs_keywords(...)`  | Lambda abstraction (keyword args)       |
| `define_class(...)`         | Defines a new object-based Goal class   |
| `instantiate(...)`          | Instantiates an object-based Goal       |

## Architecture

| Layer    | Component          | Purpose                          |
|----------|--------------------|----------------------------------|
| Core     | `pgsn_term.py`     | Lambda calculus interpreter      |
| DSL      | `dsl.py`, `gsn.py` | Human-friendly API to define GSN |


##  License

MIT License – see [LICENSE](LICENSE).

Copyright: National Institute of Advanced Industrial Science and Technology (AIST) 2023-2024,
Yoriyuki Yamagata 2025
