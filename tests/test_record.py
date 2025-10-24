from pgsn.dsl import *


def test_record():
    x = constant('x')
    y = constant('y')
    z = constant('z')
    r = record({'x': x, 'y': y, 'z': z})
    k1 = string('x')
    k2 = string('w')
    assert r(k1).eval() == x.eval()
    assert r(k2).eval_or_none() is None


x = variable('x')
y = variable('y')
z = variable('z')
a = variable('a')
b = constant('b')
c = constant('c')
label_1 = string('l1')
label_2 = string('l2')
r1 = record({'l1': a})
r2 = add_attribute(empty_record)(label_2)(r1)
r3 = overwrite_record(r1)(r2)
def test_self_reference1():
    assert set(r3.fully_eval().attributes().keys()) == {'l1', 'l2'}


def test_self_reference2():
    f = lambda_abs_vars((x, y),
                        let(
                            y, add_attribute(y)(label_2)(x),
                            overwrite_record(x)(y)
                        )
                        )
    assert set(f(r1)(r2).fully_eval().attributes().keys()) == {'l1', 'l2'}


def test_self_reference3():
    f1 = lambda_abs_vars((x, y),
                         overwrite_record(x)(add_attribute(y)(label_2)(x))
                         )
    assert set(f1(r1)(r2).fully_eval().attributes().keys()) == {'l1', 'l2'}


def test_self_reference4():
    r = overwrite_record(r1)(add_attribute(r2)(label_2)(r1), )
    assert set(r.fully_eval().attributes().keys()) == {'l1', 'l2'}
