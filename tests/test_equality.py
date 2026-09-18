"""Equality is defined on data, and on nothing else.

`Equal` used to decline only applications and abstractions, so it fired on
whatever else it was handed and compared the two terms as they stood.  A list
whose elements were still to be reduced was answered about before the elements
had values -- `equal [plus 1 1] [2]` was `false` -- and a class was answered
about at all, which is the structural comparison of classes that `is_subclass`
was removed for (PGSN-implementation.md §1.5).

A term is comparable now when its leaves are all base values: a base value
itself, or a list or a record built out of comparable components.  Anything
else leaves the application stuck, so the question is refused rather than
answered wrongly.
"""

import pytest

from pgsn import pgsn_term
from pgsn.dsl import (boolean, concat, constant, empty, equal, false, fold,
                      integer, is_empty, lambda_abs, list_term, plus, record,
                      string, true, undefined, variable)
from pgsn.gsn import goal, goal_class

_x = variable('x')
_identity = lambda_abs(_x, _x)
# `undefined` takes no argument, so the application never reduces.
_stuck = undefined(integer(0))


def _answer(term, steps=10000) -> bool:
    """The boolean `term` reduces to.  Fails if it does not reduce to one."""
    result = term.fully_eval(steps=steps)
    assert isinstance(result, pgsn_term.Boolean), result
    return result.value


def _is_stuck(term, steps=10000) -> bool:
    """Did the comparison refuse to answer?"""
    return isinstance(term.fully_eval(steps=steps), pgsn_term.App)


# ---------------------------------------------------------------------------
# Base values
# ---------------------------------------------------------------------------

def test_strings_compare():
    assert _answer(equal(string('a'))(string('a'))) is True
    assert _answer(equal(string('a'))(string('b'))) is False


def test_integers_compare():
    assert _answer(equal(integer(1))(integer(1))) is True
    assert _answer(equal(integer(1))(integer(2))) is False


def test_booleans_compare():
    assert _answer(equal(true)(true)) is True
    assert _answer(equal(true)(false)) is False
    assert _answer(equal(boolean(False))(false)) is True


def test_constants_compare():
    assert _answer(equal(undefined)(undefined)) is True
    assert _answer(equal(constant('a'))(constant('a'))) is True
    assert _answer(equal(constant('a'))(constant('b'))) is False


def test_values_of_different_base_types_are_unequal():
    """Both sides are data, so the question has an answer, and it is no."""
    assert _answer(equal(integer(1))(string('1'))) is False
    assert _answer(equal(true)(integer(1))) is False


# ---------------------------------------------------------------------------
# Data built out of base values
# ---------------------------------------------------------------------------

def test_lists_of_base_values_compare():
    assert _answer(equal(empty)(empty)) is True
    assert _answer(equal(list_term((string('a'), integer(1))))
                   (list_term((string('a'), integer(1))))) is True
    assert _answer(equal(list_term((string('a'),)))
                   (list_term((string('b'),)))) is False
    assert _answer(equal(list_term((string('a'),)))(empty)) is False


def test_nested_lists_compare():
    nested = list_term((list_term((integer(1),)), empty))
    other = list_term((list_term((integer(2),)), empty))
    assert _answer(equal(nested)(nested)) is True
    assert _answer(equal(nested)(other)) is False


def test_records_of_base_values_compare():
    r = record({'a': integer(1), 'b': string('x')})
    assert _answer(equal(r)(r)) is True
    assert _answer(equal(r)(record({'a': integer(2), 'b': string('x')}))) is False


def test_records_with_different_labels_are_unequal():
    assert _answer(equal(record({'a': integer(1)}))
                   (record({'b': integer(1)}))) is False


def test_the_elements_are_compared_as_values_not_as_terms():
    """The bug this file is named after: `equal [1 + 1] [2]` said `false`.

    The comparison now waits until the elements have values, which is what the
    evaluator does to the inside of a list anyway, and then answers `true`.
    """
    computed = list_term((plus(integer(1))(integer(1)),))
    assert _answer(equal(computed)(list_term((integer(2),)))) is True


# ---------------------------------------------------------------------------
# Everything else is refused
# ---------------------------------------------------------------------------

def test_functions_are_not_compared():
    assert _is_stuck(equal(_identity)(_identity))


def test_a_list_holding_a_function_is_not_compared():
    holds_a_function = list_term((_identity,))
    assert _is_stuck(equal(holds_a_function)(holds_a_function))


def test_a_record_holding_a_function_is_not_compared():
    holds_a_function = record({'f': _identity})
    assert _is_stuck(equal(holds_a_function)(holds_a_function))


def test_a_stuck_term_is_not_compared():
    assert _is_stuck(equal(_stuck)(_stuck))
    assert _is_stuck(equal(_stuck)(string('a')))


def test_classes_are_not_compared():
    """`is_subclass` was removed for comparing classes structurally; `equal`
    accepted them until now, so the comparison was one builtin away."""
    assert _is_stuck(equal(goal_class)(goal_class))


def test_objects_are_not_compared():
    node = goal(description="System is secure")
    assert _is_stuck(equal(node)(node))


# ---------------------------------------------------------------------------
# `is_empty`, and the fold that needs it
# ---------------------------------------------------------------------------

def test_is_empty_answers_about_the_list_only():
    assert _answer(is_empty(empty)) is True
    assert _answer(is_empty(list_term((integer(1),)))) is False
    # The elements are never looked at, so what they are does not matter.
    assert _answer(is_empty(list_term((_identity,)))) is False


def test_is_empty_declines_a_non_list():
    assert _is_stuck(is_empty(string('a')))
    assert _is_stuck(is_empty(_stuck))


def test_a_fold_over_a_list_of_functions_terminates():
    """Why `is_empty` had to exist.

    `foldr` asked `equal list empty` for its base case.  With equality
    restricted to data, a list of anything else -- a list of functions here, a
    list of GSN nodes in every real document -- would have left that
    comparison stuck and the fold with it.
    """
    result = concat(list_term((_identity,)))(empty).fully_eval(steps=1000)
    assert isinstance(result, pgsn_term.List)
    assert len(result.terms) == 1


def test_a_fold_over_a_list_of_nodes_terminates():
    nodes = list_term((goal(description="a"), goal(description="b")))
    result = concat(nodes)(empty).fully_eval(steps=10000)
    assert isinstance(result, pgsn_term.List)
    assert len(result.terms) == 2


def test_a_fold_over_a_stuck_list_still_terminates():
    """`is_empty` declines a term that is not a list, exactly as the old
    comparison against `empty` did, so the recursive branch stays unexpanded.
    """
    fold(plus)(integer(0))(_stuck).fully_eval(steps=1000)
