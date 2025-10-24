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