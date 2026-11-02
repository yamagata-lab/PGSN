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
from pgsn.dsl import (base_class, define_class, div, equal, format_string,
                      if_then_else, index, integer, integer_sum, is_subtype,
                      lambda_abs,
                      less_than, list_term, map_term, minus, mod, plus,
                      python_value, record, remove_attribute, string, true,
                      undefined, variable)
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
    # A class definition that would break the invariants of PGSNClass: a
    # default that names no attribute, or a name that is both an attribute
    # and a method.
    "a default that names no attribute": define_class(inherit=base_class,
                                                      defaults=record({'a': true}),
                                                      attributes=[], methods={}),
    "an attribute that is also a method": define_class(inherit=base_class,
                                                       attributes=['m'],
                                                       methods={'m': _identity}),
    "a method already inherited as an attribute": define_class(inherit=_attributes_only,
                                                               methods={'a': _identity}),
    "an attribute already inherited as a method": define_class(inherit=_with_a_method,
                                                               attributes=['m']),
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


# ---------------------------------------------------------------------------
# The term evaluation comes to rest on
# ---------------------------------------------------------------------------
#
# Each case pairs a term with the exact term its evaluation stops at. The
# expected term is written by hand, so a change to where evaluation stops, or
# to what it leaves around a stuck application, shows up here.

_thunk = variable('_thunk')

SHAPES = {
    "a builtin keeps arguments it declines":
        (div(1)(0),
         div(1)(0)),
    "arguments are reduced before the builtin declines them":
        (div(plus(1)(2))(minus(1)(1)),
         div(3)(0)),
    "an argument is substituted, then reduced":
        (lambda_abs(_x, div(_x)(0))(plus(1)(2)),
         div(3)(0)),
    "arguments beyond the arity are reduced too":
        (div(1)(0)(plus(1)(2)),
         div(1)(0)(3)),
    "a stuck head keeps its arguments, reduced":
        (record({'a': integer(1)})('b')(plus(1)(1)),
         record({'a': integer(1)})('b')(2)),
    "a stuck argument blocks the builtin that needs it":
        (plus(div(1)(0))(plus(1)(1)),
         plus(div(1)(0))(2)),
    "a stuck argument blocks every builtin above it":
        (plus(1)(plus(2)(div(1)(0))),
         plus(1)(plus(2)(div(1)(0)))),
    "a free variable as head":
        (variable('f')(plus(1)(1)),
         variable('f')(2)),
    "a stuck term is copied wherever it is used":
        (lambda_abs(_x, list_term((_x, _x)))(div(1)(0)),
         list_term((div(1)(0), div(1)(0)))),
    "the other elements of a list are reduced":
        (list_term((plus(1)(1), div(1)(0), plus(2)(2))),
         list_term((integer(2), div(1)(0), integer(4)))),
    "the other fields of a record are reduced":
        (record({'a': plus(1)(1), 'b': div(1)(0)}),
         record({'a': integer(2), 'b': div(1)(0)})),
    "a stuck condition leaves both branches unevaluated":
        (if_then_else(div(1)(0))(plus(1)(1))(plus(2)(2)),
         pgsn_term.IfThenElse.named()(div(1)(0))
         (lambda_abs(_thunk, plus(1)(1)))
         (lambda_abs(_thunk, plus(2)(2)))
         (undefined)),
    "the branch taken is stuck":
        (if_then_else(true)(div(1)(0))(2),
         div(1)(0)),
    "map leaves the stuck element in place":
        (map_term(lambda_abs(_x, div(6)(_x)))(list_term((integer(1), integer(0), integer(2)))),
         list_term((integer(6), div(6)(0), integer(3)))),
    "fold stops at the stuck element and keeps the rest of the sum":
        (integer_sum(list_term((integer(1), div(1)(0), integer(3)))),
         plus(1)(plus(div(1)(0))(3))),
}


@pytest.mark.parametrize("term, expected", SHAPES.values(), ids=SHAPES.keys())
def test_evaluation_comes_to_rest_on(term, expected):
    assert _evaluate(term) == expected.remove_name()


# Where Python raises an exception of its own, the builtin declines instead,
# and evaluation comes to rest on the term itself.
_one_two = list_term((integer(1), integer(2)))
_a_is_one = record({'a': integer(1)})

DECLINED_INSTEAD_OF_FAILING = {
    "index out of range": index(_one_two)(5),
    "negative index out of range": index(_one_two)(-3),
    "removing an absent label": remove_attribute(_a_is_one)('b'),
    "positional field in a format string": format_string('{0}')(_a_is_one),
    "attribute reference in a format string": format_string('{a.b}')(_a_is_one),
}


@pytest.mark.parametrize("term", DECLINED_INSTEAD_OF_FAILING.values(),
                         ids=DECLINED_INSTEAD_OF_FAILING.keys())
def test_a_builtin_declines_instead_of_failing(term):
    assert _evaluate(term) == term.remove_name()


# ---------------------------------------------------------------------------
# A stuck application says why
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("term", [*STUCK.values(), *DECLINED_INSTEAD_OF_FAILING.values()],
                         ids=[*STUCK.keys(), *DECLINED_INSTEAD_OF_FAILING.keys()])
def test_a_stuck_application_records_the_reason(term):
    assert _evaluate(term).meta_info["error"].startswith("PGSN")


def test_the_reason_is_the_one_where_evaluation_stopped():
    stuck = _evaluate(record({'a': integer(1)})('b'))
    assert stuck.meta_info["error"] == "PGSNKeyError: Record: there is no label 'b'"


def test_an_argument_declined_on_the_way_leaves_no_reason():
    """A builtin declines an argument that is not reduced yet, too, but that
    is not where evaluation stops."""
    term = _evaluate(record({'a': plus(plus(1)(2))(3)}))
    assert "error" not in term.attributes()['a'].meta_info


def test_the_reason_is_not_shared_with_other_terms():
    _evaluate(div(1)(0))
    assert "error" not in div(1)(1).remove_name().meta_info
    assert "error" not in integer(0).remove_name().meta_info


def test_readback_shows_the_reason():
    with pytest.raises(ValueError, match="PGSNValueError: Div: division by zero"):
        python_value(_evaluate(div(1)(0)))


# ---------------------------------------------------------------------------
# A fault of the interpreter is not a stuck term
# ---------------------------------------------------------------------------

class _Broken(pgsn_term.ConstMixin, pgsn_term.Unary):

    def _apply_arg(self, arg):
        raise RuntimeError("a fault of the interpreter")


def test_a_fault_of_the_interpreter_escapes():
    with pytest.raises(RuntimeError, match="a fault of the interpreter"):
        _evaluate(_Broken.named()(integer(1)))


# A list applied to an integer is indexed as `index` indexes it: from the end
# when the integer is negative, as in Python, and stuck outside the list.
@pytest.mark.parametrize("i", (2, -3))
def test_a_list_applied_out_of_range_is_stuck(i):
    assert _evaluate(_one_two(i)) == _one_two(i).remove_name()


@pytest.mark.xfail(strict=True, reason="a list applied to a negative integer is stuck")
@pytest.mark.parametrize("i, expected", ((-1, 2), (-2, 1)))
def test_a_list_applied_to_a_negative_integer_counts_from_the_end(i, expected):
    assert _evaluate(_one_two(i)) == integer(expected).remove_name()


# A builtin is handed every pending argument and consumes as many as its arity;
# the rest are applied to its result. These two wait for exactly their arity
# instead, so they stop one application early. The result cannot be applied
# either, so only the place where evaluation stops differs.
@pytest.mark.xfail(strict=True, reason="Formatter declines arguments beyond its arity")
def test_formatter_applies_with_arguments_beyond_its_arity():
    term = format_string('{a}')(_a_is_one)(plus(1)(1))
    assert _evaluate(term) == string('1')(2).remove_name()


@pytest.mark.xfail(strict=True, reason="IsSubtype declines arguments beyond its arity")
def test_is_subtype_applies_with_arguments_beyond_its_arity():
    term = is_subtype(_attributes_only)(base_class)(plus(1)(1))
    assert _evaluate(term) == true(2).remove_name()
