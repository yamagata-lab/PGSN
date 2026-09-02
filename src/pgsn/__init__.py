"""PGSN — a programming language for GSN generation and manipulation.

This module is the public API.  It exposes three groups of names:

* constructors for PGSN constants and terms, and the builtin terms they
  combine with (`string`, `record`, `lambda_abs`, `map_term`, ...);
* constructors for GSN nodes and classes, together with the functions that
  turn an evaluated term into something readable (`python_value`, `gsn_tree`,
  `gsn_dot`, `save_gsn`);
* the XML front end (`load_xml`, `load_xml_string`) and its configuration
  (`Config`, `Jails`, `configure`).

Everything else in the `pgsn` package is implementation detail.  The submodules
`pgsn.dsl`, `pgsn.gsn`, `pgsn.pgsn_term`, `pgsn.pgsn_xml`, `pgsn.dcom`,
`pgsn.helpers` and `pgsn.cli` are internal: their contents may change without
notice, and importing from them directly is unsupported.

Loading XML is confined by a jail table.  A jail is a named directory root, and
a document reaches files inside one by writing ``/<jail>/sub/file.xml``::

    import pgsn

    cfg = pgsn.Config(jails={"lib": "/opt/pgsn-lib"})
    term = pgsn.load_xml("main.xml", config=cfg)
    print(pgsn.gsn_tree(term).show(stdout=False))

Nothing outside a registered jail — or outside the document's own directory —
can be imported.
"""

from pgsn.config import Config, configure, get_config
from pgsn.jail import Jails, JailError

from pgsn.dsl import (
    # Terms and variables
    Term,
    variable,
    constant,
    # Constants
    string,
    integer,
    boolean,
    true,
    false,
    undefined,
    # Aggregates
    list_term,
    record,
    empty,
    empty_record,
    # Abstraction and binding
    lambda_abs,
    lambda_abs_vars,
    lambda_abs_keywords,
    let,
    let_vars,
    fix,
    # Control
    if_then_else,
    guard,
    equal,
    boolean_and,
    boolean_or,
    boolean_not,
    # Arithmetic
    plus,
    minus,
    times,
    div,
    mod,
    integer_sum,
    repeat,
    # Lists
    cons,
    head,
    tail,
    index,
    map_term,
    fold,
    foldr,
    concat,
    list_all,
    # Records
    has_label,
    list_labels,
    add_attribute,
    remove_attribute,
    overwrite_record,
    format_string,
    # Classes and objects
    base_class,
    define_class,
    instantiate,
    instance,
    is_instance,
    is_subclass,
    # Conversion
    python_value,
)

from pgsn.gsn import (
    # GSN node constructors
    goal,
    strategy,
    evidence,
    context,
    assumption,
    undeveloped,
    immediate,
    evidence_as_goal,
    # GSN classes
    gsn_class,
    goal_class,
    strategy_class,
    evidence_class,
    context_class,
    assumption_class,
    support_class,
    undeveloped_class,
    # Rendering
    gsn_tree,
    gsn_dot,
    save_gsn,
)

from pgsn.pgsn_xml import PGSNError, load_xml, load_xml_string

__all__ = [
    # Configuration
    "Config",
    "configure",
    "get_config",
    "Jails",
    "JailError",
    # XML front end
    "load_xml",
    "load_xml_string",
    "PGSNError",
    # Terms and variables
    "Term",
    "variable",
    "constant",
    # Constants
    "string",
    "integer",
    "boolean",
    "true",
    "false",
    "undefined",
    # Aggregates
    "list_term",
    "record",
    "empty",
    "empty_record",
    # Abstraction and binding
    "lambda_abs",
    "lambda_abs_vars",
    "lambda_abs_keywords",
    "let",
    "let_vars",
    "fix",
    # Control
    "if_then_else",
    "guard",
    "equal",
    "boolean_and",
    "boolean_or",
    "boolean_not",
    # Arithmetic
    "plus",
    "minus",
    "times",
    "div",
    "mod",
    "integer_sum",
    "repeat",
    # Lists
    "cons",
    "head",
    "tail",
    "index",
    "map_term",
    "fold",
    "foldr",
    "concat",
    "list_all",
    # Records
    "has_label",
    "list_labels",
    "add_attribute",
    "remove_attribute",
    "overwrite_record",
    "format_string",
    # Classes and objects
    "base_class",
    "define_class",
    "instantiate",
    "instance",
    "is_instance",
    "is_subclass",
    # GSN node constructors
    "goal",
    "strategy",
    "evidence",
    "context",
    "assumption",
    "undeveloped",
    "immediate",
    "evidence_as_goal",
    # GSN classes
    "gsn_class",
    "goal_class",
    "strategy_class",
    "evidence_class",
    "context_class",
    "assumption_class",
    "support_class",
    "undeveloped_class",
    # Conversion and rendering
    "python_value",
    "gsn_tree",
    "gsn_dot",
    "save_gsn",
]
