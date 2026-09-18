"""A term that cannot proceed is returned, not reported.

Evaluation never fails on a term it cannot reduce: a builtin handed arguments
it has no answer for leaves the application as it stands, and evaluation
returns whatever it came to rest on. The error is raised by readback --
`python_value`, and the conversion to GSN built on it -- which is where a
value is required, and which reports the path at which it met something that
is not one.

The rule holds for any evaluator, a virtual machine included
(PGSN-implementation.md §1.5). It is what lets a document with a gap be
evaluated as far as it goes, and it separates "no answer" from a wrong answer
or a crash.
"""

import pytest

from pgsn import pgsn_term
from pgsn.dsl import (base_class, define_class, div, equal, integer,
                      lambda_abs, less_than, list_term, mod, python_value,
                      record, string, true, undefined, variable)
from pgsn.gsn import goal, gsn_tree, undeveloped

_x = variable('x')
_self = variable('self')
_identity = lambda_abs(_x, _x)

_a = string('a')
_attributes_only = define_class(inherit=base_class,
                                defaults=record({'a': true}),
                                attributes=['a'], methods={})
_with_a_method = define_class(inherit=base_class,
                              defaults=record({'a': true}),
                              attributes=['a'],
                              methods={'m': lambda_abs(_self, _self(_a))})


# One term per way a builtin can decline its arguments.
STUCK = {
    # `undefined` takes no argument, so the application never reduces.
    "undefined": undefined(integer(0)),
    "missing record key": record({'a': integer(1)})(string('b')),
    "ordering non-integers": less_than(string('a'))(string('b')),
    "comparing functions": equal(_identity)(_identity),
    "division by zero": div(integer(1))(integer(0)),
    "modulo by zero": mod(integer(1))(integer(0)),
    "missing attribute": _attributes_only({})(string('b')),
    "missing key on an object with methods": _with_a_method({})(string('b')),
}


def _evaluate(term: pgsn_term.Term) -> pgsn_term.Term:
    return term.fully_eval(steps=10000)


# ---------------------------------------------------------------------------
# Evaluation returns the term
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("term", STUCK.values(), ids=STUCK.keys())
def test_evaluation_returns_a_stuck_term(term):
    assert isinstance(_evaluate(term), pgsn_term.App)


# ---------------------------------------------------------------------------
# Readback reports it, with the path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("term", STUCK.values(), ids=STUCK.keys())
def test_readback_reports_a_stuck_term(term):
    with pytest.raises(ValueError, match=r"at path '<root>'"):
        python_value(_evaluate(term))


def test_readback_reports_the_path_into_a_record():
    term = record({'ok': integer(1), 'gap': STUCK["missing record key"]})
    with pytest.raises(ValueError, match=r"at path '<root>\.gap'"):
        python_value(_evaluate(term))


def test_readback_reports_the_path_into_a_list():
    term = list_term((integer(1), STUCK["missing record key"]))
    with pytest.raises(ValueError, match=r"at path '<root>\[1\]'"):
        python_value(_evaluate(term))


def test_a_stuck_term_is_evaluated_around():
    """What can be reduced is, even beside a term that cannot."""
    term = _evaluate(list_term((div(integer(6))(integer(3)),
                                STUCK["missing record key"])))
    assert term.terms[0].value == 2
    assert isinstance(term.terms[1], pgsn_term.App)


def test_conversion_to_gsn_reports_a_stuck_term():
    node = _evaluate(goal(description=STUCK["missing record key"],
                          support=undeveloped))
    with pytest.raises(ValueError, match=r"at path '<root>\.description'"):
        gsn_tree(node)
