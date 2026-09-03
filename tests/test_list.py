from pgsn import dsl
from pgsn.dsl import *
from src.pgsn.pgsn_term import List


def test_list():
    x = constant('x')
    y = constant('y')
    z = constant('z')
    ll = list_term((x, y, z))
    assert ll.terms == (x, y, z)
    i = integer(1)
    assert ll(i).eval().name == 'y'


def _is_one():
    n = variable('n')
    return lambda_abs(n, equal(n)(integer(1)))


def _all_of(*values):
    items = list_term(tuple(integer(v) for v in values))
    return python_value(list_all(_is_one(), items).fully_eval(steps=5000))


def test_list_all_holds_for_every_element():
    assert _all_of(1, 1, 1) is True


def test_list_all_fails_on_a_counterexample():
    assert _all_of(1, 2, 1) is False


def test_list_all_is_vacuously_true_on_the_empty_list():
    assert _all_of() is True