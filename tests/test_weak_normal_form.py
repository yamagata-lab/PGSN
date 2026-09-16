"""Evaluation stops at an abstraction: the result is a weak normal form.

The evaluator used to reduce the body of an abstraction before anything was
applied to it. A builtin waiting for a later argument, as map_term waits for
its list, then had its function argument reduced first, with the parameter
still unknown.
"""
from pgsn.dsl import (concat, empty, equal, if_then_else, lambda_abs,
                      map_term, record, variable)
from pgsn.pgsn_term import cast, value_of


def _behind_a_lookup(value):
    # Not yet a value, so map_term has to wait for it.
    return record({"items": value})("items")


def test_map_term_does_not_reduce_its_function_first():
    # With x unknown, the recursion in concat unfolded without end.
    x = variable("x")
    g = lambda_abs(x, concat(x("a"))(empty))
    items = cast([{"a": []}], is_named=True)
    assert value_of(map_term(g)(_behind_a_lookup(items)), steps=200) == [[]]


def test_equal_does_not_see_a_bound_variable():
    # With x unknown, equal compared the variable itself with "a" and fixed
    # the answer to "no" before any element was substituted.
    x = variable("x")
    g = lambda_abs(x, if_then_else(equal(x)("a"))("yes")("no"))
    items = cast(["a"], is_named=True)
    assert value_of(map_term(g)(_behind_a_lookup(items)), steps=200) == ["yes"]
